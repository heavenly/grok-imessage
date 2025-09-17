# Grok iMessage Bot 🤖

An intelligent iMessage automation bot that integrates with Perplexity AI (Grok) to provide conversational AI responses in iMessage group chats. The bot automatically cleans up conversation threads after each interaction to maintain a tidy workspace.

## ✨ Features

- **Real-time iMessage Monitoring**: Continuously monitors iMessage conversations for trigger commands
- **AI-Powered Responses**: Leverages Perplexity AI (Grok) for intelligent, context-aware responses
- **Context Preservation**: Maintains conversation context across multiple messages
- **Automatic Thread Cleanup**: Automatically deletes processed threads to keep your Perplexity workspace organized
- **Async Processing**: Non-blocking architecture ensures responsive message handling
- **Group Chat Support**: Works seamlessly with iMessage group conversations

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+**
- **macOS** (required for iMessage integration)
- **Perplexity AI Account** with API access
- **Messages.app** permissions

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/heavenly/grok-imessage.git
   cd grok-imessage
   ```

2. **Install dependencies:**
   ```bash
   pip install aiohttp requests
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your credentials:
   ```env
   # Perplexity.ai Authentication (get from browser dev tools)
   AUTH_COOKIE=your_auth_cookie_here
   USER_NEXTAUTH_ID=your_user_id_here
   VISITOR_ID=your_visitor_id_here

   # iMessage Configuration
   CHAT_IDENTIFIER=your_chat_identifier_here
   GROUP_GUID=your_group_guid_here

   # Perplexity Collection UUID
   TARGET_COLLECTION_UUID=your_collection_uuid_here
   ```

4. ctrl+f find REPLACE_WITH_YOUR_SLUG and replace with your collection slug id
### Authentication Setup

1. **Log into Perplexity.ai** in your browser
2. **Open Developer Tools** (F12)
3. **Navigate to Application/Storage > Cookies**
4. **Copy the required values:**
   - `AUTH_COOKIE`: Full cookie string from perplexity.ai
   - `USER_NEXTAUTH_ID`: User identifier
   - `VISITOR_ID`: Visitor tracking ID

## 📱 Usage

### Starting the Bot

```bash
python groq.py
```

### Triggering Responses

Send messages starting with `@grok` in your iMessage group chat:

```
@grok What is the capital of France?
@grok Explain quantum computing ~5m
@grok Summarize our conversation ~10m
```

### Context Commands

- `@grok [question]` - Basic query
- `@grok [question] ~[number]m` - Include last N messages as context
- `@grok [question] ~[number]M` - Include last N messages as context (alternative syntax)

### Response Format

The bot responds with:
```
[KROG]: [AI Response]
used X message(s) of context.
```

## 🏗️ Architecture

### Core Components

1. **iMessageDaemon Class**
   - Main orchestration class
   - Manages message monitoring and processing

2. **Message Processing Pipeline**
   ```
   iMessage Received → Parse Command → Query Perplexity → Send Response → Cleanup Threads
   ```

3. **Async Architecture**
   - Non-blocking HTTP requests with `aiohttp`
   - Background task processing
   - Concurrent thread cleanup

### Key Files

- `groq.py` - Main bot implementation
- `.env` - Environment configuration (not in repo)
- `.env.example` - Configuration template
- `.gitignore` - Security exclusions

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `AUTH_COOKIE` | Perplexity authentication cookie | ✅ |
| `USER_NEXTAUTH_ID` | User identifier | ✅ |
| `VISITOR_ID` | Visitor tracking ID | ✅ |
| `CHAT_IDENTIFIER` | iMessage chat identifier | ✅ |
| `GROUP_GUID` | iMessage group GUID | ✅ |
| `TARGET_COLLECTION_UUID` | Perplexity collection UUID | ✅ |

### Message Buffer Settings

```python
DEFAULT_CONTEXT_COUNT = 1      # Default messages to include
MAX_CONTEXT_COUNT = 10         # Maximum context messages
MAX_BUFFER_SIZE = 10          # Message buffer size
```

## 🔒 Security

### Protected Files

- `.env` - Authentication credentials
- Sensitive cookies and tokens
- Personal identifiers

## 🛠️ Development

### Project Structure

```
grok-imessage/
├── groq.py                 # Main bot implementation
├── .env.example           # Configuration template
├── .gitignore            # Security exclusions
├── README.md             # This file
└── __pycache__/          # Python cache (ignored)
```

### Dependencies

- `aiohttp` - Async HTTP client
- `requests` - HTTP client (legacy)
- `asyncio` - Async programming
- `threading` - Background processing
- `json` - JSON handling
- `uuid` - Unique identifier generation

### Extending the Bot

#### Adding New Commands

```python
def _parse_custom_command(self, message_str: str) -> tuple[str, dict]:
    # Parse custom command format
    # Return: (cleaned_message, command_options)
    pass
```

#### Custom Response Processing

```python
async def _custom_response_handler(self, response: str) -> str:
    # Process AI response
    # Return: formatted_response
    pass
```

## 🚨 Troubleshooting

### Common Issues

**"Permission denied" for Messages.app**
```bash
# Grant accessibility permissions
System Preferences → Security & Privacy → Privacy → Accessibility
# Add Python/Messages.app
```

**Authentication errors**
- Verify `.env` credentials are current
- Check Perplexity.ai session is active
- Refresh authentication cookies

**iMessage not responding**
- Ensure Messages.app is running
- Check chat identifiers in `.env`
- Verify group chat permissions

### Debug Mode

Enable verbose logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📊 Performance

- **Response Time**: ~2-5 seconds per query
- **Memory Usage**: ~50MB baseline
- **Concurrent Processing**: Handles multiple chats simultaneously
- **Cleanup Frequency**: Automatic after each response

---
