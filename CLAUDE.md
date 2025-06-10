# Spotify DJ Track Automation

## Overview
Automate the process of downloading DJ tracks from Spotify playlists using an external Telegram bot. This script will:
1. Extract all track URLs from a Spotify playlist
2. Send each URL to the external Telegram bot automatically via your user account
3. Monitor and download the returned FLAC files
4. Organize them in a folder structure

## Requirements
- Python 3.7+
- Spotify Developer Account (for API access)
- Telegram API credentials (api_id, api_hash from my.telegram.org)
- Phone number for Telegram account verification
- Access to existing external Telegram bot that converts Spotify links to FLAC files

## Important: External Bot Limitation
Since you're using an external bot (not your own), traditional Bot API approaches won't work. The solution uses **Telethon** to automate your personal Telegram account to send messages to the external bot.

## Setup Instructions

### 1. Spotify API Setup
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Note your `Client ID` and `Client Secret`

### 2. Telegram API Setup (Critical for External Bot)
1. Go to [https://my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Create a new application
4. Note your `api_id` and `api_hash`
5. Have your phone number ready for verification

### 3. Install Dependencies
```bash
pip install telethon spotipy python-dotenv
```

## Security Considerations

### Telethon Security Assessment
**Telethon is secure when used properly**, but involves automating your personal Telegram account:

**Security Strengths:**
- Uses official MTProto protocol (same as Telegram apps)
- Local encrypted session storage
- Open source and well-audited
- No third-party credential sharing

**Security Risks:**
- Script has full access to your Telegram account
- Session files must be protected (treat like passwords)
- Automation may trigger rate limiting or account flags
- Potential Terms of Service considerations

### Security Best Practices

#### 1. Credential Protection
- Store API credentials in environment variables
- Never commit credentials to version control
- Use `.env` files with proper `.gitignore`

#### 2. Session File Security
- Store session files in protected directories (mode 0o700)
- Don't share or backup session files publicly
- Consider using a dedicated Telegram account for automation

#### 3. Rate Limiting (Critical)
- Minimum 2-3 seconds between messages
- Handle FloodWaitError exceptions properly
- Monitor for temporary bans or restrictions
- Process in smaller batches if needed

#### 4. Conservative Usage
- Personal use only (avoid commercial automation)
- Reasonable message volumes
- Normal user behavior patterns

## Implementation Plan

### Phase 1: Basic Automation
Create a Python script using Telethon that:
- Connects to Telegram using your user account
- Extracts playlist track URLs from Spotify API
- Sends URLs to external bot with proper rate limiting
- Monitors chat for file responses from bot
- Downloads available FLAC files

### Phase 2: Enhanced Features
- Progress tracking and resumption capability
- Robust error handling and retry logic
- FloodWaitError handling for rate limiting
- Batch processing with conservative delays
- File naming and organization system
- Comprehensive success/failure reporting
- Session management and security

## Key Considerations

### Rate Limiting (Critical for Account Safety)
- Minimum 2-3 seconds between messages (non-negotiable)
- Handle Telegram's FloodWaitError exceptions
- Respect daily/hourly message limits
- Monitor for temporary account restrictions
- Use exponential backoff for retries

### Error Handling
- Not all tracks will have FLAC files available
- Network timeouts and connection issues
- Invalid Spotify URLs or private tracks
- Telegram rate limiting and temporary bans
- Session expiration and re-authentication

### File Management
- Automatic folder creation
- Duplicate file detection
- Proper file naming (artist - title.flac)
- Progress logging

## Usage Workflow

1. **Setup**: Configure Telegram API credentials and Spotify API
2. **Authentication**: Log in to Telegram account (first-time phone verification)
3. **Input**: Provide Spotify playlist URL and external bot username
4. **Extract**: Get all track URLs from playlist via Spotify API
5. **Process**: Send each URL to external bot via your Telegram account
6. **Monitor**: Wait for and capture file responses from bot
7. **Download**: Save FLAC files with proper naming
8. **Organize**: Structure files in designated folders
9. **Report**: Generate summary of successful/failed downloads

## Expected Challenges

- **Account Security**: Protecting session files and API credentials
- **Rate Limiting**: Balancing automation speed vs Telegram restrictions
- **External Bot Dependency**: Relying on third-party bot availability and response
- **File Availability**: Not all tracks available as FLAC from external source
- **Monitoring Complexity**: Detecting bot responses in real-time chat
- **Session Management**: Handling authentication and re-authentication

## Success Metrics

- Reduced manual work from hours to minutes
- High success rate for available tracks
- Proper file organization and naming
- Resumable process for large playlists

## Next Steps

1. **Security Setup**: Create dedicated Telegram account (recommended) or secure main account
2. **API Configuration**: Set up Spotify API and Telegram API credentials
3. **Environment Setup**: Configure secure credential storage and session management
4. **Basic Implementation**: Test Telethon connection and basic message sending
5. **Spotify Integration**: Implement playlist URL extraction
6. **Bot Communication**: Develop external bot messaging with rate limiting
7. **File Monitoring**: Create system to detect and download bot responses
8. **Testing**: Start with small playlists (5-10 tracks) before scaling
9. **Full Deployment**: Process complete 100+ track playlists safely

## Security Recommendations

### Essential Security Measures
- **Use environment variables** for all API credentials
- **Secure session storage** in protected directories
- **Conservative rate limiting** (3+ seconds between messages)
- **Consider dedicated account** for automation to reduce risk
- **Monitor for FloodWaitError** and handle gracefully
- **Regular session cleanup** and security reviews

### Alternative Approaches (If Security Concerns)
1. **Browser Automation** (Selenium with Telegram Web) - Less account risk
2. **Manual Hybrid** (Script prepares URLs, manual sending) - No automation risk
3. **Desktop Automation** (PyAutoGUI for Telegram Desktop) - Middle ground

### Risk Mitigation
- Start with small batches to test bot responses
- Monitor account for any restrictions or warnings
- Keep backups of successful downloads
- Have fallback manual process ready

## Safety Features

- **Dry run mode** to test automation without sending messages
- **Progress saving** to resume interrupted sessions safely
- **Configurable delays** and conservative timeouts
- **Session encryption** and secure credential management
- **FloodWaitError handling** to prevent account restrictions
- **Detailed logging** for troubleshooting and security monitoring
- **Batch size limits** to prevent overwhelming external bot
- **Account safety checks** before and during automation

## Local Session Security

### When Running Locally
**Risk Level: LOW** - Session files are as secure as:
- Browser saved passwords
- SSH keys in ~/.ssh/
- Any desktop app login tokens

### Session File Details
- Size: ~50-200KB SQLite database
- Location: ./sessions/ (protected directory)
- Contains: Encrypted auth keys (not passwords)
- Can: Send messages, download files
- Cannot: Change password, add devices, access secret chats

### Best Practices for Local Use
```bash
# Check session directory permissions
ls -la sessions/  # Should show drwx------ (700)

# Never copy sessions to:
- Cloud storage (Dropbox, Google Drive)
- Git repositories
- Shared folders
- Backup services

# Monitor active sessions in Telegram app:
Settings → Privacy → Active Sessions

# Emergency revoke if needed:
- Terminate session from Telegram app
- Session instantly invalidated
```

### Practical Security
For local personal use, session security is equivalent to any authenticated desktop application. Main rule: treat `sessions/` folder like your `.ssh/` folder - keep it local and protected.

## Quick Start Commands

```bash
# First run (with authentication)
python telethon_downloader.py https://open.spotify.com/playlist/xxxxx

# Subsequent runs
python telethon_downloader.py <playlist_url> --batch-size 10

# Dry run to preview
python telethon_downloader.py <playlist_url> --dry-run

# Check progress
python telethon_downloader.py --status

# Reset progress
python telethon_downloader.py --reset
```

## Current Implementation Status (v2.0.0 - Modular Architecture)

✅ **Completed:**
- **Modular Architecture**: Separated concerns into distinct modules
- **Enhanced Spotify API**: Support for playlists, albums, and tracks with caching
- **Advanced Telegram Client**: Secure session management with Telethon
- **Smart File Management**: Organized downloads with duplicate detection
- **Comprehensive Progress Tracking**: Resume capability and detailed reporting
- **CLI Interface**: User-friendly command-line tool with multiple commands
- **Rate Limiting**: Conservative approach to protect Telegram account
- **Error Handling**: Robust retry logic and graceful failure handling

📁 **Project Structure:**
```
spotify_downloader/
├── src/                        # Modular components
│   ├── __init__.py
│   ├── spotify_api.py         # Spotify API interactions
│   ├── telegram_client.py     # Telegram/Telethon handling
│   ├── file_manager.py        # Download organization
│   ├── progress_tracker.py    # Session & progress management
│   └── main.py               # Main orchestrator
├── run.py                     # CLI entry point
├── telethon_downloader.py     # Legacy monolithic version
├── requirements.txt           # Python dependencies
├── .env.example              # Configuration template
├── .gitignore                # Security exclusions
└── README.md                 # User documentation
```

## Quick Start with New Architecture

```bash
# Setup virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure credentials in .env file
cp .env.example .env
# Edit .env with your API credentials

# Run commands
python run.py --help                                          # Show help
python run.py https://open.spotify.com/playlist/xxxxx         # Download playlist
python run.py https://open.spotify.com/playlist/xxxxx --dry-run  # Preview tracks
python run.py status                                          # Check progress
python run.py report                                          # Generate report
```

## New Features in v2.0.0

### 1. **Modular Architecture**
- Clean separation of concerns
- Easy to test and maintain
- Reusable components
- Better error isolation

### 2. **Enhanced Spotify Support**
- Playlist extraction with pagination
- Album support
- Individual track support
- Response caching for performance
- Retry logic with exponential backoff

### 3. **Advanced File Management**
- Configurable organization (by artist/album/year)
- Smart filename generation
- Duplicate detection (file hash comparison)
- Collision handling
- File validation

### 4. **Session Management**
- Complete session persistence
- Resume interrupted downloads
- Track-level status tracking
- Detailed progress reporting
- Export capabilities

### 5. **CLI Features**
- Multiple commands (download, status, reset, report)
- Flexible options (batch size, organization, output directory)
- Dry run mode for testing
- Comprehensive help system

### 6. **Security Enhancements**
- Protected session storage (0o700 permissions)
- Environment-based configuration
- No hardcoded credentials
- Conservative rate limiting
- Secure credential validation

## Configuration Options

### Environment Variables (.env)
```bash
# Spotify API (Required)
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret

# Telegram API (Required)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE_NUMBER=+1234567890
EXTERNAL_BOT_USERNAME=@your_bot

# Optional Settings
DOWNLOAD_FOLDER=./downloads
DELAY_BETWEEN_REQUESTS=3.0
MAX_RETRIES=3
RESPONSE_TIMEOUT=60
```

### Command Line Options
- `--dry-run`: Preview without downloading
- `--batch-size N`: Process N tracks at a time
- `--no-resume`: Start fresh (ignore previous session)
- `--organize-by [artist|album|none]`: File organization
- `--year-folders`: Create year-based folders
- `--output-dir DIR`: Custom download directory

## Architecture Benefits

1. **Maintainability**: Each module has a single responsibility
2. **Testability**: Components can be tested in isolation
3. **Extensibility**: Easy to add new features or storage backends
4. **Reliability**: Better error handling and recovery
5. **Performance**: Caching and optimized operations
6. **Security**: Centralized credential management

## Future Enhancements

- [ ] Web UI for easier interaction
- [ ] Multiple bot support
- [ ] Playlist monitoring for new tracks
- [ ] Audio format conversion
- [ ] Metadata tagging
- [ ] Cloud storage integration
- [ ] Docker containerization
- [ ] API rate limit visualization