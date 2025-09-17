"""Minimal iMessage Monitor - Only functions used in groq.py"""

import asyncio
import sqlite3
import time
import queue
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import plistlib
import re
from collections import deque
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler, FileSystemEvent


# Date/Time Conversion
def datetime_to_apple_timestamp(dt: datetime) -> int:
    """Convert datetime to Apple timestamp format."""
    apple_epoch = datetime(2001, 1, 1)
    diff = dt - apple_epoch
    return int(diff.total_seconds() * 1_000_000_000)


@dataclass
class AppleConfig:
    chat_db_path: str
    attachments_path: str
    permissions_check: bool = True


@dataclass
class MonitoringConfig:
    poll_interval_seconds: int = 3
    max_batch_size: int = 100
    enable_real_time: bool = True


@dataclass
class ContactFilter:
    outbound_behavior: str = "none"
    outbound_ids: List[str] = None
    inbound_behavior: str = "none"
    inbound_ids: List[str] = None

    def __post_init__(self):
        if self.outbound_ids is None:
            self.outbound_ids = []
        if self.inbound_ids is None:
            self.inbound_ids = []


@dataclass
class DateRange:
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


@dataclass
class OutboundConfig:
    method: str = "applescript"
    rate_limit_per_minute: int = 30


@dataclass
class Config:
    apple: AppleConfig
    monitoring: MonitoringConfig
    contacts: ContactFilter
    date_range: DateRange
    outbound: OutboundConfig

    @classmethod
    def default(cls) -> 'Config':
        return cls(
            apple=AppleConfig(
                chat_db_path=str(Path.home() / "Library" / "Messages" / "chat.db"),
                attachments_path=str(Path.home() / "Library" / "Messages" / "Attachments")
            ),
            monitoring=MonitoringConfig(),
            contacts=ContactFilter(),
            date_range=DateRange(),
            outbound=OutboundConfig()
        )


def should_include_message(message: Dict[str, Any], contact_filter: ContactFilter) -> bool:
    chat_id = message.get('chat_identifier') or message.get('chat_guid')
    if chat_id:
        is_outbound = message.get('is_from_me', False)
        if is_outbound:
            behavior = contact_filter.outbound_behavior
            ids_list = contact_filter.outbound_ids
        else:
            behavior = contact_filter.inbound_behavior
            ids_list = contact_filter.inbound_ids
        if behavior == "whitelist" and chat_id not in ids_list:
            return False
        elif behavior == "blacklist" and chat_id in ids_list:
            return False
        if behavior in ["whitelist", "blacklist"]:
            return True
    individual_id = message.get('handle_id_str') or message.get('uncanonicalized_id')
    if not individual_id:
        return True
    is_outbound = message.get('is_from_me', False)
    if is_outbound:
        behavior = contact_filter.outbound_behavior
        ids_list = contact_filter.outbound_ids
    else:
        behavior = contact_filter.inbound_behavior
        ids_list = contact_filter.inbound_ids
    if behavior == "none":
        return True
    elif behavior == "whitelist":
        return individual_id in ids_list
    elif behavior == "blacklist":
        return individual_id not in ids_list
    else:
        return True


def apply_contact_filter(messages: List[Dict[str, Any]], contact_filter: Optional[ContactFilter]) -> List[Dict[str, Any]]:
    if not contact_filter:
        return messages
    if (contact_filter.outbound_behavior == "none" and
        contact_filter.inbound_behavior == "none"):
        return messages
    return [msg for msg in messages if should_include_message(msg, contact_filter)]


def decode_attributed_body(attributed_body: bytes) -> Optional[str]:
    if not attributed_body:
        return None
    try:
        attributed_body_str = attributed_body.decode('utf-8', errors='replace')
        if "NSNumber" in attributed_body_str:
            attributed_body_str = attributed_body_str.split("NSNumber")[0]
            if "NSString" in attributed_body_str:
                attributed_body_str = attributed_body_str.split("NSString")[1]
                if "NSDictionary" in attributed_body_str:
                    attributed_body_str = attributed_body_str.split("NSDictionary")[0]
                    attributed_body_str = attributed_body_str[6:-12]
                    return attributed_body_str.strip()
        text_matches = re.findall(r'[\x20-\x7E]{2,}', attributed_body_str)
        if text_matches:
            return max(text_matches, key=len).strip()
        return None
    except Exception as e:
        return None


def decode_binary_plist(data: bytes) -> Optional[Dict]:
    if not data:
        return None
    try:
        return plistlib.loads(data)
    except Exception as e:
        return None


def get_recent_messages(db_path: str, limit: int = 50, offset: int = 0, date_range: Optional[DateRange] = None, contact_filter: Optional[ContactFilter] = None) -> List[Dict[str, Any]]:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        date_conditions = []
        query_params = []
        if date_range:
            if date_range.start_date:
                start_timestamp = datetime_to_apple_timestamp(date_range.start_date)
                date_conditions.append("m.date >= ?")
                query_params.append(start_timestamp)
            if date_range.end_date:
                end_timestamp = datetime_to_apple_timestamp(date_range.end_date)
                date_conditions.append("m.date <= ?")
                query_params.append(end_timestamp)
        where_clause = ""
        if date_conditions:
            where_clause = "WHERE " + " AND ".join(date_conditions)
        query = f"""
        SELECT
            m.ROWID as message_id,
            m.guid as message_guid,
            m.text as message_text,
            m.attributedBody,
            m.payload_data,
            m.date,
            m.date_read,
            m.date_delivered,
            m.is_from_me,
            m.is_read,
            m.is_delivered,
            m.is_sent,
            m.service,
            m.account,
            m.handle_id,
            m.cache_has_attachments,
            m.message_summary_info,
            m.balloon_bundle_id,
            m.associated_message_guid,
            m.associated_message_type,
            m.expressive_send_style_id,
            m.reply_to_guid,
            m.thread_originator_guid,
            m.is_audio_message,
            m.group_title,
            m.group_action_type,
            h.id as handle_id_str,
            h.service as handle_service,
            h.country as handle_country,
            h.uncanonicalized_id,
            c.guid as chat_guid,
            c.chat_identifier,
            c.service_name as chat_service,
            c.display_name as chat_display_name,
            c.room_name,
            c.style as chat_style,
            c.properties as chat_properties,
            c.group_id,
            c.is_archived,
            GROUP_CONCAT(a.guid) as attachment_guids,
            GROUP_CONCAT(a.filename) as attachment_filenames,
            GROUP_CONCAT(a.mime_type) as attachment_mime_types,
            GROUP_CONCAT(a.total_bytes) as attachment_sizes,
            GROUP_CONCAT(a.is_sticker) as attachment_is_stickers
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
        LEFT JOIN chat c ON cmj.chat_id = c.ROWID
        LEFT JOIN message_attachment_join maj ON m.ROWID = maj.message_id
        LEFT JOIN attachment a ON maj.attachment_id = a.ROWID
        {where_clause}
        GROUP BY m.ROWID
        ORDER BY m.date DESC
        LIMIT ? OFFSET ?
        """
        query_params.extend([limit, offset])
        cursor.execute(query, query_params)
        results = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        messages = []
        for row in results:
            message_dict = dict(zip(columns, row))
            if message_dict['attributedBody']:
                message_dict['decoded_attributed_body'] = decode_attributed_body(message_dict['attributedBody'])
            if message_dict['payload_data']:
                message_dict['decoded_payload_data'] = decode_binary_plist(message_dict['payload_data'])
            if message_dict['message_summary_info']:
                message_dict['decoded_message_summary_info'] = decode_binary_plist(message_dict['message_summary_info'])
            if message_dict['chat_properties']:
                message_dict['decoded_chat_properties'] = decode_binary_plist(message_dict['chat_properties'])
            if message_dict['attachment_guids']:
                attachments = []
                guids = message_dict['attachment_guids'].split(',')
                filenames = (message_dict['attachment_filenames'] or '').split(',')
                mime_types = (message_dict['attachment_mime_types'] or '').split(',')
                sizes = (message_dict['attachment_sizes'] or '').split(',')
                is_stickers = (message_dict['attachment_is_stickers'] or '').split(',')
                for i, guid in enumerate(guids):
                    attachment = {
                        'guid': guid,
                        'filename': filenames[i] if i < len(filenames) else None,
                        'mime_type': mime_types[i] if i < len(mime_types) else None,
                        'size': int(sizes[i]) if i < len(sizes) and sizes[i].isdigit() else None,
                        'is_sticker': bool(int(is_stickers[i])) if i < len(is_stickers) and is_stickers[i].isdigit() else False
                    }
                    attachments.append(attachment)
                message_dict['parsed_attachments'] = attachments
            messages.append(message_dict)
        conn.close()
        if contact_filter:
            messages = apply_contact_filter(messages, contact_filter)
        return messages
    except sqlite3.Error as e:
        return []
    except Exception as e:
        return []


class RealtimeStrategy:
    def start(self, db_path: str, callback: Callable[[], None]) -> bool:
        pass
    def stop(self) -> None:
        pass
    def is_active(self) -> bool:
        pass
    def get_stats(self) -> Dict[str, Any]:
        pass


class QueueBasedMessageWatcher(FileSystemEventHandler):
    def __init__(self, message_queue: queue.Queue, name: str = "QueueWatcher"):
        super().__init__()
        self.message_queue = message_queue
        self.name = name
        self._last_modification_time = 0
        self._debounce_interval = 0.1
        self._event_count = 0
        self._queue_puts = 0
        self._start_time = time.time()

    def on_any_event(self, event: FileSystemEvent):
        self._event_count += 1
        if not event.is_directory:
            self._check_database_file_event(event)

    def _check_database_file_event(self, event: FileSystemEvent):
        file_path = str(event.src_path)
        file_name = Path(file_path).name
        db_files = ['chat.db', 'chat.db-wal', 'chat.db-shm', 'chat.db-journal']
        is_db_file = any(file_name == db_file for db_file in db_files)
        if is_db_file:
            current_time = time.time()
            time_since_last = current_time - self._last_modification_time
            if time_since_last >= self._debounce_interval:
                self._last_modification_time = current_time
                self._queue_puts += 1
                try:
                    event_data = {
                        'timestamp': current_time,
                        'file_name': file_name,
                        'event_type': event.event_type,
                        'event_id': self._queue_puts
                    }
                    self.message_queue.put_nowait(event_data)
                except queue.Full:
                    pass
                except Exception:
                    pass

    def get_stats(self) -> Dict[str, Any]:
        runtime = time.time() - self._start_time
        return {
            'name': self.name,
            'runtime_seconds': runtime,
            'total_events': self._event_count,
            'queue_puts': self._queue_puts,
            'events_per_second': self._event_count / runtime if runtime > 0 else 0,
            'queue_puts_per_second': self._queue_puts / runtime if runtime > 0 else 0
        }


class QueueBasedRealtimeStrategy(RealtimeStrategy):
    def __init__(self):
        self.observer: Optional[PollingObserver] = None
        self.watcher: Optional[QueueBasedMessageWatcher] = None
        self.message_queue: Optional[queue.Queue] = None
        self._queue_processor_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._callback: Optional[Callable[[], None]] = None
        self._queue_events_processed = 0

    def start(self, db_path: str, callback: Callable[[], None]) -> bool:
        if self.observer:
            return False
        try:
            self.message_queue = queue.Queue(maxsize=100)
            self._callback = callback
            db_path_obj = Path(db_path)
            watch_directory = db_path_obj.parent
            if not watch_directory.exists():
                return False
            self.watcher = QueueBasedMessageWatcher(self.message_queue, "RealtimeQueue")
            self.observer = PollingObserver(timeout=0.1)
            self.observer.schedule(self.watcher, str(watch_directory), recursive=False)
            self.observer.start()
            self._is_running = True
            self._queue_processor_task = asyncio.create_task(self._queue_processor())
            # Real-time monitoring started
            return True
        except Exception as e:
            self.stop()
            return False

    def stop(self) -> None:
        self._is_running = False
        if self._queue_processor_task:
            self._queue_processor_task.cancel()
            self._queue_processor_task = None
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None
        if self.message_queue:
            while not self.message_queue.empty():
                try:
                    self.message_queue.get_nowait()
                    self.message_queue.task_done()
                except queue.Empty:
                    break
            self.message_queue = None
        self.watcher = None
        self._callback = None

    def is_active(self) -> bool:
        return (self.observer is not None and
                self.observer.is_alive() if self.observer else False)

    def get_stats(self) -> Dict[str, Any]:
        stats = {
            'strategy': 'queue_based',
            'is_active': self.is_active(),
            'queue_events_processed': self._queue_events_processed,
            'queue_size': self.message_queue.qsize() if self.message_queue else 0
        }
        if self.watcher:
            watcher_stats = self.watcher.get_stats()
            stats.update(watcher_stats)
        return stats

    async def _queue_processor(self):
        while self._is_running:
            try:
                event_data = self.message_queue.get_nowait()
                self._queue_events_processed += 1
                if self._callback:
                    try:
                        await self._callback()
                    except Exception as e:
                        pass  # Error in real-time callback
                self.message_queue.task_done()
            except queue.Empty:
                await asyncio.sleep(0.1)
            except Exception as e:
                await asyncio.sleep(0.1)


class RealtimeMonitor:
    def __init__(self):
        self.strategy: Optional[RealtimeStrategy] = None
        self._backup_polling_used = False

    def start(self, db_path: str, callback: Callable[[], None]) -> bool:
        if self.strategy:
            return False
        queue_strategy = QueueBasedRealtimeStrategy()
        if queue_strategy.start(db_path, callback):
            self.strategy = queue_strategy
            return True
        return False

    def stop(self) -> None:
        if self.strategy:
            self.strategy.stop()
            self.strategy = None
        self._backup_polling_used = False

    def is_active(self) -> bool:
        return self.strategy is not None and self.strategy.is_active()

    def mark_backup_polling_used(self) -> None:
        self._backup_polling_used = True

    def get_stats(self) -> Dict[str, Any]:
        if self.strategy:
            stats = self.strategy.get_stats()
            stats['backup_polling_used'] = self._backup_polling_used
            return stats
        return {
            'strategy': 'none',
            'is_active': False,
            'backup_polling_used': self._backup_polling_used
        }


class iMessageMonitor:
    def __init__(self, config_path: str = None):
        if config_path:
            self.config = Config.from_file(Path(config_path))
        else:
            self.config = Config.default()
        self._is_running = False
        self._monitor_task = None
        self._db_path = str(Path.home() / "Library" / "Messages" / "chat.db")
        self._last_message_id = 0
        self._message_callback = None
        self._large_batch_warning_shown = False
        self._realtime_monitor = RealtimeMonitor()
        if not Path(self._db_path).exists():
            raise FileNotFoundError(f"Messages database not found at {self._db_path}")

    def start(self, message_callback: Optional[Callable] = None) -> bool:
        if self._is_running:
            raise RuntimeError("Monitor is already running")
        self._is_running = True
        self._message_callback = message_callback
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(ROWID) FROM message")
            result = cursor.fetchone()
            self._last_message_id = result[0] if result[0] is not None else 0
            conn.close()
        except Exception as e:
            self._last_message_id = 0
        if message_callback:
            self._monitor_task = asyncio.create_task(self._monitor_loop())
        return True

    def stop(self):
        if not self._is_running:
            return
        self._is_running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None
        self._realtime_monitor.stop()
        self._message_callback = None

    def get_messages_since(self, message_id: int) -> List[Dict[str, Any]]:
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ROWID FROM message
                WHERE ROWID > ?
                ORDER BY date DESC
            """, (message_id,))
            new_message_ids = cursor.fetchall()
            conn.close()
            if not new_message_ids:
                return []
            newest_id = new_message_ids[0][0]
            message_count = len(new_message_ids)
            return get_recent_messages(self._db_path, message_count, contact_filter=self.config.contacts)
        except Exception as e:
            return []

    async def _check_new_messages(self):
        try:
            new_messages = self.get_messages_since(self._last_message_id)
            if new_messages:
                self._last_message_id = new_messages[0]['message_id']
                await self._process_messages_in_batches(new_messages)
        except Exception as e:
            pass

    async def _monitor_loop(self):
        polling_interval = self.config.monitoring.poll_interval_seconds
        realtime_active = False
        if self.config.monitoring.enable_real_time:
            try:
                realtime_active = self._realtime_monitor.start(self._db_path, self._check_new_messages)
                if realtime_active:
                    pass  # Real-time monitoring started
                else:
                    pass  # Failed to start real-time monitoring
            except Exception as e:
                pass
        while self._is_running:
            try:
                if self._realtime_monitor.is_active():
                    new_messages = self.get_messages_since(self._last_message_id)
                    if new_messages:
                        self._last_message_id = new_messages[0]['message_id']
                        await self._process_messages_in_batches(new_messages)
                        self._realtime_monitor.mark_backup_polling_used()
                    await asyncio.sleep(polling_interval)
                else:
                    new_messages = self.get_messages_since(self._last_message_id)
                    if new_messages:
                        self._last_message_id = new_messages[0]['message_id']
                        await self._process_messages_in_batches(new_messages)
                    await asyncio.sleep(polling_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                await asyncio.sleep(polling_interval)

    async def _process_messages_in_batches(self, messages: List[Dict[str, Any]]) -> None:
        if not self._message_callback:
            return
        batch_size = self.config.monitoring.max_batch_size
        if batch_size > 1000 and not self._large_batch_warning_shown:
            self._large_batch_warning_shown = True
        messages_reversed = list(reversed(messages))
        for i in range(0, len(messages_reversed), batch_size):
            batch = messages_reversed[i:i + batch_size]
            for message in batch:
                try:
                    self._message_callback(message)
                except Exception as e:
                    pass
            if i + batch_size < len(messages_reversed):
                await asyncio.sleep(0.1)

