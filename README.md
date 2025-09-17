# Grok iMessage Bot 🤖

An intelligent iMessage automation bot that integrates with local Jan.ai to provide conversational AI responses in iMessage group chats. The bot automatically cleans up conversation threads after each interaction to maintain a tidy workspace.

## ✨ Features

- **Real-time iMessage Monitoring**: Continuously monitors iMessage conversations for trigger commands
- **AI-Powered Responses**: Leverages local Jan.ai for intelligent, context-aware responses
- **Context Preservation**: Maintains conversation context across multiple messages
- **Automatic Thread Cleanup**: Automatically deletes processed threads to keep your Perplexity workspace organized
- **Async Processing**: Non-blocking architecture ensures responsive message handling
- **Group Chat Support**: Works seamlessly with iMessage group conversations

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+**
- **macOS** (required for iMessage integration)
- **Jan.ai** local server running (download from https://jan.ai/)
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
    # Jan.ai Authentication
    JAN_BEARER_TOKEN=your_jan_bearer_token_here

    # iMessage Configuration
    CHAT_IDENTIFIER=your_chat_identifier_here
    GROUP_GUID=your_group_guid_here
    ```

4. ctrl+f find REPLACE_WITH_YOUR_SLUG and replace with your collection slug id
### Authentication Setup

1. **Install and run Jan.ai** locally
2. **Obtain Bearer Token**: Check Jan.ai documentation or settings for API authentication
3. **Set JAN_BEARER_TOKEN** in your `.env` file

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

Responses will be in lowercase, concise, and without punctuation.

### Context Commands

- `@grok [question]` - Basic query
- `@grok [question] ~[number]m` - Include last N messages as context
- `@grok [question] ~[number]M` - Include last N messages as context (alternative syntax)

### Response Format

The bot responds with:
```
[KROG]: [ai response in lowercase, concise, no punctuation]
used X message(s) of context.
```

## 🏗️ Architecture

### Core Components

1. **iMessageDaemon Class**
   - Main orchestration class
   - Manages message monitoring and processing

2. **Message Processing Pipeline**
    ```
    iMessage Received → Parse Command → Query Jan.ai → Send Response → Cleanup Threads
    ```

3. **Async Architecture**
   - Non-blocking HTTP requests with `aiohttp`
   - Background task processing
   - Concurrent thread cleanup

### Key Files

- `groq.py` - Main bot implementation
- `imessage_monitor.py` - iMessage monitoring module
- `.env` - Environment configuration (not in repo)
- `.env.example` - Configuration template
- `.gitignore` - Security exclusions

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `JAN_BEARER_TOKEN` | Jan.ai API bearer token | ✅ |
| `CHAT_IDENTIFIER` | iMessage chat identifier | ✅ |
| `GROUP_GUID` | iMessage group GUID | ✅ |

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
├── imessage_monitor.py     # iMessage monitoring module
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
- Verify `JAN_BEARER_TOKEN` in `.env` is correct
- Ensure Jan.ai server is running on localhost:1337
- Check Jan.ai API documentation for token setup

**iMessage not responding**
- Ensure Messages.app is running
- Check chat identifiers in `.env`
- Verify group chat permissions

**Jan.ai server issues**
- Confirm Jan.ai is installed and running
- Check server is accessible at http://localhost:1337
- Verify the model "jan-nano-128k-Q4_K_S" is loaded

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
