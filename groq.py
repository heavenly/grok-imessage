import asyncio
from imessage_monitor import iMessageMonitor
import subprocess
import aiohttp
import json
import re
import os
import sqlite3
import pathlib
import getpass
import string
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

# API Configuration for local Jan.ai
JAN_API_URL = "http://localhost:1337/v1/chat/completions"  # Adjust port if needed

# Constants for message handling
GROK_PREFIX = "@grok"
KROG_RESPONSE_PREFIX = "[KROG]: "
DEFAULT_CONTEXT_COUNT = 1
MAX_CONTEXT_COUNT = 10
MAX_BUFFER_SIZE = 10

def get_phone_from_handle_id(handle_id: int) -> str:
    """
    Get the phone number/email from handle table using handle_id (ROWID).
    """
    db_path = pathlib.Path.home() / "Library/Messages/chat.db"
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM handle WHERE ROWID = ?", (handle_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else str(handle_id)
    except Exception as e:
        print(f"Error querying handle: {e}")
        return str(handle_id)

def get_contact_name(phone: str) -> str:
    """
    Get the first name for a phone number from Contacts using AppleScript.
    Returns the phone number if not found.
    """
    applescript = f'''
    tell application "Contacts"
        try
            set thePerson to first person whose value of phones contains "{phone}"
            set firstName to first name of thePerson
            if firstName is not "" then
                return firstName
            else
                return name of thePerson
            end if
        on error
            return "{phone}"
        end try
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-s", "o", "-e", applescript],
            capture_output=True,
            text=True,
            check=True
        )
        name = result.stdout.strip()
        return name if name else phone
    except subprocess.CalledProcessError:
        return phone

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



async def query_jan(prompt: str) -> Optional[str]:
    """
    Send a query to local Jan.ai server.

    Args:
        prompt (str): The prompt to send

    Returns:
        str: The AI response text
    """
    system_prompt = """
    You are krog, an AI model stored in iMessage chats. 
    Always respond in lowercase. Be concise. 
    Do not give extra fluff. Do not give any citations unless the user asks.
    Do not use punctuation or grammar. 
    If the user asks for citations, give raw links."""
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "model": "jan-nano-128k-Q4_K_S",
        "stream": False
    }

    headers = {
        'Authorization': f'Bearer {os.environ.get("JAN_BEARER_TOKEN")}',
        'Content-Type': 'application/json'
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(JAN_API_URL, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except aiohttp.ClientError as e:
        print(f"Error querying Jan.ai: {e}")
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

    def _build_grok_prompt(self, context: str, user_question: str, sender_name: str, context_count: int) -> str:
        return f"""
[CONTEXT]: "{context}"  # Formatted as a sequence like: user: data user: data (up to 10 messages)

[USER {sender_name}]: {user_question}

Respond helpfully and truthfully.
Use the given context only if it is directly relevant to answering the user's question—do not hallucinate or add unverified information. 
If context is used, reference only the specific messages needed and avoid unnecessary details.
At the end of your message, append: "used {context_count} message(s) of context." where {context_count} is the number of context messages you actually referenced (0 if none).
"""



    async def _send_response(self, chat_id: str, response: str):
        try:
            group_guid = f"iMessage;+;{chat_id}"
            await send_imessage_to_group(group_guid, KROG_RESPONSE_PREFIX + str(response))
        except subprocess.CalledProcessError as e:
            print(f"Error sending iMessage: {e}")

    async def handle_message(self, message):
        """Handle new messages with filtering."""
        message_str = self._clean_message(message)
        sender_id = message.get('handle_id', 'Unknown')
        if isinstance(sender_id, int):
            if sender_id == 0:
                sender_name = getpass.getuser().title().split()[0]
            else:
                sender_phone = get_phone_from_handle_id(sender_id)
                sender_name = get_contact_name(sender_phone)
        else:
            sender_name = sender_id
        print(f"[iMessage] {sender_name}: {message_str}")

        chat_id = message["chat_identifier"]
        if self._should_buffer(message_str):
            self.message_buffer.add_message(chat_id, f"{sender_name}: {message_str}")

        try:
            if message_str.startswith(GROK_PREFIX):
                cleaned_question, context_count = self._parse_grok_command(message_str)
                context = self.message_buffer.get_context(chat_id, context_count)
                prompt = self._build_grok_prompt(context, cleaned_question, sender_name, context_count)
                text = await query_jan(prompt)
                if text is None:
                    return
                await self._send_response(chat_id, text)
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