import asyncio
from imessage_monitor import iMessageMonitor
import subprocess
import aiohttp
import json
import uuid
import re
import os
from typing import Dict, Optional

def load_env():
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

load_env()

# Global authentication/identification variables
AUTH_COOKIE = os.environ.get('AUTH_COOKIE')

USER_NEXTAUTH_ID = os.environ.get('USER_NEXTAUTH_ID')
VISITOR_ID = os.environ.get('VISITOR_ID')

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:141.0) Gecko/20100101 Firefox/141.0'
ACCEPT_LANGUAGE = 'en-US,en;q=0.5'
REFERER_URL = 'https://www.perplexity.ai/'
ORIGIN_URL = 'https://www.perplexity.ai'
PERPLEXITY_REQUEST_REASON = 'perplexity-query-state-provider'

# API Configuration
API_URL = "https://www.perplexity.ai/rest/sse/perplexity_ask"
API_VERSION = "2.18"

# Constants for message handling
GROK_PREFIX = "@grok"
KROG_RESPONSE_PREFIX = "[KROG]: "
DEFAULT_CONTEXT_COUNT = 1
MAX_CONTEXT_COUNT = 10
MAX_BUFFER_SIZE = 10

class MessageBuffer:

    def __init__(self, max_size: int = MAX_BUFFER_SIZE):

        self.buffers: Dict[str, list[str]] = {}

        self.max_size = max_size

    def add_message(self, chat_id: str, message: str):

        if chat_id not in self.buffers:

            self.buffers[chat_id] = []

        self.buffers[chat_id].append(message)

        if len(self.buffers[chat_id]) > self.max_size:

            self.buffers[chat_id].pop(0)

    def get_context(self, chat_id: str, count: int) -> str:

        buffer = self.buffers.get(chat_id, [])

        return "\n".join(buffer[-count:]) if buffer else ""

def combine_streaming_chunks(response_text: str) -> str:
    """
    Collapse all markdown_block.chunks from a streaming-style
    Perplexity response into one string, and extract entry_uuid and read_write_token if present.
    """
    chunks = []
    seen = set()  # Track unique chunks
    for line in response_text.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue

        for block in data.get("blocks", []):
            mb = block.get("markdown_block")
            if mb:
                for chunk in mb.get("chunks", []):
                    if chunk not in seen:
                        chunks.append(chunk)
                        seen.add(chunk)

    return "".join(chunks).strip()

def build_perplexity_payload(query_text: str, model_preference: str, language: str, timezone: str) -> dict:
    frontend_uuid = str(uuid.uuid4())
    frontend_context_uuid = str(uuid.uuid4())
    return {
        "params": {
            "attachments": [],
            "language": language,
            "timezone": timezone,
            "search_focus": "internet",
            "sources": ["web"],
            "search_recency_filter": None,
            "frontend_uuid": frontend_uuid,
            "mode": "copilot",
            "model_preference": model_preference,
            "is_related_query": False,
            "is_sponsored": False,
            "visitor_id": VISITOR_ID,
            "user_nextauth_id": USER_NEXTAUTH_ID,
            "frontend_context_uuid": frontend_context_uuid,
            "prompt_source": "user",
            "query_source": "home",
            "is_incognito": False,
            "use_schematized_api": True,
            "send_back_text_in_streaming_api": False,
            "dsl_query": query_text,
            "skip_search_enabled": True,
            "is_nav_suggestions_disabled": False,
            "version": API_VERSION,
            "target_collection_uuid": os.environ.get('TARGET_COLLECTION_UUID')
        },
        "query_str": query_text
    }

async def query_perplexity(query_text: str, model_preference: str = "claude37sonnetthinking", language: str = "en-US", timezone: str = "America/Los_Angeles") -> Optional[str]:
    """
    Send an initial query to Perplexity AI API (with authentication)

    Args:
        query_text (str): The question/query to send
        model_preference (str): Model to use (default: "claude37sonnetthinking")
        language (str): Language preference (default: "en-US")
        timezone (str): Timezone (default: "America/Los_Angeles")

    Returns:
        str: The API response text
    """

    payload = build_perplexity_payload(query_text, model_preference, language, timezone)

    # Use global authentication variables
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',  # Keep as streaming since API returns streaming format
        'stream': "false",
        'User-Agent': USER_AGENT,
        'Accept-Language': ACCEPT_LANGUAGE,
        'Referer': REFERER_URL,
        'Origin': ORIGIN_URL,
        'x-perplexity-request-reason': PERPLEXITY_REQUEST_REASON,
        'Cookie': AUTH_COOKIE,
        'DNT': '1',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Connection': 'keep-alive'
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, headers=headers, data=json.dumps(payload)) as response:
                response.raise_for_status()
                return await response.text()
    except aiohttp.ClientError as e:
        print(f"Error querying Perplexity: {e}")
        return None

async def send_imessage_to_group(group_guid: str, message: str):
    # 1. Escape back-slashes and double-quotes for AppleScript
    safe = (
        message
        .replace("\\", "\\\\")   # back-slashes first
        .replace('"', '\\"')     # then quotes
        .replace("\n", "\\n")    # keep explicit new-line markers
    )

    applescript = f'''
    tell application "Messages"
        set targetChat to chat id "{group_guid}"
        set theText    to "{safe}"
        send theText to targetChat
    end tell
    '''

    # 2. Use osascript -s o to surface any AppleScript error in stdout
    process = await asyncio.create_subprocess_exec(
        "osascript", "-s", "o", "-e", applescript,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await process.wait()
    if process.returncode != 0:
        stdout, stderr = await process.communicate()
        raise subprocess.CalledProcessError(process.returncode, "osascript", output=stdout, stderr=stderr)

class iMessageDaemon:
    def __init__(self):
        self.monitor = None
        self.monitor_thread = None
        self.loop = None
        self.is_running = True
        self.message_buffer = MessageBuffer()
        
        # Start monitoring
        self.run_monitor_in_thread()

    def _clean_message(self, message) -> str:
        message_str = message['decoded_attributed_body'].strip()
        message_str = ''.join(c for c in message_str if c.isprintable())
        return message_str

    def _should_buffer(self, message_str: str) -> bool:
        return not (message_str.startswith(KROG_RESPONSE_PREFIX) or message_str.startswith(GROK_PREFIX))

    def _parse_grok_command(self, message_str: str) -> tuple[str, int]:
        message_str = message_str.replace(GROK_PREFIX, "").strip()
        context_count = DEFAULT_CONTEXT_COUNT
        match = re.search(r'~(\d+)m?M?', message_str)
        if match:
            context_count = int(match.group(1))
            if 1 <= context_count <= MAX_CONTEXT_COUNT:
                message_str = re.sub(r'~\d+m?M?', '', message_str).strip()
            else:
                context_count = DEFAULT_CONTEXT_COUNT
        return message_str, context_count

    def _build_grok_prompt(self, context: str, user_question: str, context_count: int) -> str:
        return f"""
[CONTEXT]: "{context}"

[USER QUESTION]: {user_question}

using the given context if needed, answer the user's question as depicted above.
at the end of your message, append:
"used {context_count} message(s) of context."
"""

    def _deduplicate_response(self, res: str) -> str:
        if len(res) > 0 and res.count(res[:len(res)//2]) == 2 and res[:len(res)//2] == res[len(res)//2:]:
            res = res[:len(res)//2]
        return res

    async def _send_response(self, chat_id: str, response: str):
        try:
            group_guid = f"iMessage;+;{chat_id}"
            await send_imessage_to_group(group_guid, KROG_RESPONSE_PREFIX + str(response))
        except subprocess.CalledProcessError as e:
            print(f"Error sending iMessage: {e}")

    async def handle_message(self, message):
        """Handle new messages with filtering."""
        message_str = self._clean_message(message)
        print(f"[iMessage] {message_str}")

        chat_id = message["chat_identifier"]
        if self._should_buffer(message_str):
            self.message_buffer.add_message(chat_id, message_str)

        try:
            if message_str.startswith(GROK_PREFIX):
                cleaned_question, context_count = self._parse_grok_command(message_str)
                context = self.message_buffer.get_context(chat_id, context_count)
                prompt = self._build_grok_prompt(context, cleaned_question, context_count)
                res = await query_perplexity(prompt, "grok4")
                if res is None:
                    return
                text = combine_streaming_chunks(res)
                text = self._deduplicate_response(text)
                await self._send_response(chat_id, text)
                # Start thread cleanup in background
                asyncio.create_task(self.cleanup_threads())
        except Exception as e:
            print(f"Error processing grok message: {e}")

    async def monitor_loop(self):
        """Async monitoring loop."""
        self.monitor = iMessageMonitor()
        self.monitor.start(message_callback=self._handle_message_sync)

        try:
            while self.is_running:
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Monitor error: {e}")
        finally:
            if self.monitor:
                self.monitor.stop()

    async def list_threads(self):
        """List all threads in the collection."""
        url = "https://www.perplexity.ai/rest/collections/list_collection_threads?collection_slug=groq-bJiBXeZ6TA61QjNdwGvijg&limit=20&filter_by_user=true&filter_by_shared_threads=false&offset=0&version=2.18&source=default"

        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'application/json',
            'Accept-Language': ACCEPT_LANGUAGE,
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Referer': REFERER_URL,
            'x-app-apiclient': 'default',
            'x-app-apiversion': '2.18',
            'x-perplexity-request-endpoint': url,
            'x-perplexity-request-reason': 'space-tabs',
            'x-perplexity-request-try-number': '1',
            'DNT': '1',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Connection': 'keep-alive',
            'Cookie': AUTH_COOKIE,
            'Priority': 'u=4',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'TE': 'trailers'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientError as e:
            print(f"Error listing threads: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {e}")
            return None

    async def delete_thread(self, entry_uuid):
        """Delete a thread by its entry_uuid."""
        url = "https://www.perplexity.ai/rest/thread/delete_thread_by_entry_uuid?version=2.18&source=default"

        headers = {
            'User-Agent': USER_AGENT,
            'Accept': '*/*',
            'Accept-Language': ACCEPT_LANGUAGE,
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Content-Type': 'application/json',
            'Referer': REFERER_URL,
            'x-app-apiclient': 'default',
            'x-app-apiversion': '2.18',
            'x-perplexity-request-endpoint': url,
            'x-perplexity-request-reason': 'thread-item',
            'x-perplexity-request-try-number': '1',
            'Origin': ORIGIN_URL,
            'DNT': '1',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Connection': 'keep-alive',
            'Cookie': AUTH_COOKIE,
            'Priority': 'u=4',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'TE': 'trailers'
        }

        payload = {
            "entry_uuid": entry_uuid,
            "read_write_token": ""
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientError as e:
            print(f"Error deleting thread {entry_uuid}: {e}")
            return None

    async def cleanup_threads(self):
        """List all threads and delete them."""
        print("Starting thread cleanup...")
        threads_data = await self.list_threads()

        if not threads_data:
            print("Failed to fetch threads for cleanup.")
            return

        if not isinstance(threads_data, list):
            print("Unexpected response format for cleanup. Expected a list of threads.")
            return

        print(f"Found {len(threads_data)} threads to delete.")

        for thread in threads_data:
            uuid = thread.get('uuid')
            if not uuid:
                print(f"Warning: Thread missing uuid: {thread}")
                continue

            print(f"Deleting thread with uuid: {uuid}")
            delete_result = await self.delete_thread(uuid)
            if delete_result:
                print(f"Successfully deleted thread {uuid}")
            else:
                print(f"Failed to delete thread {uuid}")

            # Add a small delay to avoid rate limiting
            await asyncio.sleep(0.5)

        print("Finished thread cleanup.")

    def _handle_message_sync(self, message):
        """Synchronous wrapper to create async task for message handling."""
        asyncio.create_task(self.handle_message(message))

    def run_monitor_in_thread(self):
        """Run the async monitor in a separate thread."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self.monitor_loop())
        except Exception as e:
            print(f"Thread error: {e}")
        finally:
            self.loop.close()

if __name__ == "__main__":
    app = iMessageDaemon()