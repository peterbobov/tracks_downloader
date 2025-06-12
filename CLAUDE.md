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

## Quick Start Commands (v2.1.4)

```bash
# Setup virtual environment
source .venv/bin/activate

# Basic download
python run.py "https://open.spotify.com/playlist/xxxxx"

# Check which tracks are missing (NEW!)
python run.py "https://open.spotify.com/playlist/xxxxx" --check-missing

# Preview tracks without downloading
python run.py "https://open.spotify.com/playlist/xxxxx" --dry-run

# Test with single track
python run.py "https://open.spotify.com/playlist/xxxxx" --limit 1

# Sequential processing (cleaner progress)
python run.py "https://open.spotify.com/playlist/xxxxx" --sequential

# Chunked processing (recommended for large playlists)
python run.py "https://open.spotify.com/playlist/xxxxx" --start-from 1 --limit 15 --batch-size 5
python run.py "https://open.spotify.com/playlist/xxxxx" --start-from 16 --limit 15 --batch-size 5

# Debug mode for troubleshooting
python run.py "https://open.spotify.com/playlist/xxxxx" --debug

# Check progress
python run.py status

# Reset progress
python run.py reset
```

## Current Implementation Status (v2.1.4 - Enhanced UX & Missing Track Detection)

✅ **Enhanced UX & Missing Track Detection Features:**
- **@LosslessRobot Integration**: Fully optimized for [@LosslessRobot](https://t.me/LosslessRobot) Telegram bot
- **Smart Track Matching**: Content-based matching eliminates race conditions in parallel processing
- **Clean Terminal Output**: All system messages properly clear progress lines for clean display
- **Missing Track Detection**: New `--check-missing` flag with 90% fuzzy matching and position numbers
- **Duplicate Message Prevention**: Batch progress only shows when status actually changes
- **Fixed Request Key Management**: Consistent key formats prevent delayed file orphaning
- **Intelligent File Assignment**: Tracks get correct names regardless of bot response order
- **Fuzzy String Matching**: Handles naming variations between Spotify and bot responses
- **Memory Leak Fixed**: Resolved critical issue causing hangs after ~35 tracks
- **Interactive Bot Support**: Complete button-based bot interaction workflow
- **Request Management**: Enhanced queue limits (50→30) for better delayed file handling
- **Security Hardened**: Protected against credential exposure with proper .gitignore
- **Large File Downloads**: Successfully handles 40-50MB FLAC files with 5-minute timeouts
- **Automatic Button Clicking**: Intelligently selects first option from bot responses
- **Enhanced Progress Tracking**: Fixed premature completion and lost track issues
- **Playlist-Based Organization**: Files organized by playlist name with clean filenames
- **Flexible Processing Modes**: Sequential vs parallel processing options (parallel now safe!)
- **Chunked Download Support**: Process large playlists in manageable segments
- **True Batch Processing**: Waits for complete batch before proceeding
- **Advanced Debug Mode**: Shows match scores, pending counts, and cleanup operations
- **Large Playlist Support**: Can now process full 90+ track playlists reliably with correct naming
- **Comprehensive CLI**: Advanced command-line options for all use cases

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

## Recent Updates (December 2025)

### v2.1.4 - UI/UX Improvements & Missing Track Detection
**Enhanced user experience with cleaner output and missing track detection**

#### 🎨 **Clean Terminal Output**
- **Progress Line Clearing**: All system messages now properly clear download progress lines before displaying
- **Duplicate Message Prevention**: Batch progress messages no longer spam when status hasn't changed
- **Consistent Formatting**: All status messages use consistent `_clear_print()` helper for clean display
- **Improved Spacing**: Fixed messy overlapping text between progress indicators

#### 🔍 **Missing Track Detection**
- **New `--check-missing` Flag**: Check which tracks are missing from download folder using fuzzy matching
- **90% Similarity Threshold**: Uses intelligent string matching to handle filename variations
- **Position-Based Listing**: Shows playlist position numbers for easy identification of missing tracks
- **Comprehensive Report**: Displays found vs missing tracks with detailed statistics and match confidence

#### 🐛 **Critical Bug Fixes**
- **Fixed Request Key Management**: Resolved inconsistent key formats (`msg_` vs `file_`) that caused delayed files to be orphaned
- **Queue Size Optimization**: Increased pending request limits from 20→10 to 50→30 for better delayed file handling
- **Consistent Key Format**: Button responses now maintain same key format throughout track lifecycle

#### ✨ **Enhanced Features**
```bash
# Check missing tracks with new flag syntax
python run.py "https://open.spotify.com/playlist/xxxxx" --check-missing

# Clean progress output - no more messy overlapping text
Progress: 12345/67890 bytes (18.2%)
✓ Downloaded: Track Name.flac (45,123,456 bytes)
Batch progress: 3/5 tracks completed
```

#### 🔧 **Technical Improvements**
- **Unified Progress Display**: Both telegram_client.py and main.py use `_clear_print()` helper
- **Smart Duplicate Prevention**: Tracks last batch progress message to avoid redundant output
- **Better File Matching**: Recursive .flac file scanning with fuzzy string matching
- **Robust Error Handling**: Graceful handling of missing download folders and library dependencies

### v2.1.3 - Smart Track Matching Revolution
**Eliminated race conditions with intelligent content-based track matching**

#### 🎯 **Smart Matching Algorithm**
- **Content-Based Matching**: Replaced FIFO with fuzzy string matching using bot filenames and metadata
- **Multi-Factor Scoring**: Analyzes filename, audio metadata (performer, title), and duration against Spotify data
- **Confidence Thresholds**: 70% confidence required for smart match, falls back to FIFO for edge cases
- **Race Condition Elimination**: Tracks correctly assigned regardless of bot response order

#### 🔧 **Technical Implementation**
- **Enhanced Metadata Extraction**: `_extract_filename_and_metadata()` extracts rich audio metadata from bot responses
- **Similarity Scoring**: `_calculate_track_similarity()` with weighted algorithm (filename 60%, performer 40%, title 50%)
- **Smart Request Matching**: `_find_best_matching_request()` finds highest scoring match above threshold
- **Text Normalization**: Handles variations like "feat."/"featuring", "&"/"and" for better matching

#### 🚀 **Benefits for Parallel Processing**
- **No More Wrong Names**: Tracks get correct filenames even when bot responds out of order
- **Maintains Speed**: Full parallel processing benefits without accuracy loss
- **Handles Variations**: Works with slight naming differences between Spotify and bot
- **Debug Visibility**: Shows match scores and decisions in debug mode

#### 📊 **Matching Process**
```
Bot Response: "AADJA - Neuro Erotic.flac"
Pending: ["AADJA - Neuro Erotic", "DJ Sodeyama - Miles Pt.2", ...]
Scores: [100% AADJA match, 15% DJ Sodeyama match, ...]
→ Smart match: 100% confidence ✓
```

### v2.1.2 - Critical Memory Leak Fix
**Fixed critical memory leak causing downloads to stall after ~35 tracks**

#### 🐛 **Critical Bug Fixes**
- **Memory Leak Resolution**: Fixed pending request accumulation that caused bot to hang after processing ~35 tracks
- **Request Cleanup**: Implemented proper cleanup in `_handle_file_response` method that was missing despite comments
- **Orphaned Request Management**: Added `_cleanup_orphaned_requests()` to prevent request queue overflow
- **Proactive Cleanup**: Now cleans up expired requests on every bot response, not just when checking count

#### 🔧 **Enhanced Request Management**
- **Better Request Keys**: Changed from simple message IDs to unique keys (`msg_{id}_{track_id}`) to prevent conflicts
- **Debug Monitoring**: Enhanced debug mode to show pending request counts and cleanup operations
- **Safeguard Limits**: Automatic cleanup when pending requests exceed 20 (keeps 10 most recent)
- **Improved Stability**: Prevents indefinite hanging on large playlists by maintaining clean request queue

### v2.1.1 - Security Hardening & Production Readiness
**Critical security fixes and production-ready release for [@LosslessRobot](https://t.me/LosslessRobot)**

#### 🔒 **Security Fixes**
- **Credential Exposure Fix**: Removed accidentally tracked .cache file containing Spotify access token
- **Enhanced .gitignore**: Added .cache to prevent future Spotify token exposure
- **Credential Rotation**: Successfully rotated Spotify API credentials
- **Public Release Ready**: Repository secured for public visibility

#### 🤖 **Production Bot Integration**
- **@LosslessRobot Support**: Fully tested and optimized for [@LosslessRobot](https://t.me/LosslessRobot) Telegram bot
- **Real-World Testing**: Successfully processed 101-track playlists with 48MB+ FLAC downloads
- **Reliable Button Automation**: Automatic first-option selection with robust error handling
- **Interactive Flow Mastery**: Complete support for bot's URL → Buttons → File workflow

### v2.1.0 - Interactive Bot Support & Enhanced Features
**Major update with full interactive bot support and advanced download control**

#### ✅ **Interactive Bot Flow Implementation**
- **Button Response Handling**: Automatically detects and clicks first option when bot provides track choices
- **"Nothing Found" Detection**: Gracefully handles bot's image responses when tracks aren't available
- **Sequential Flow Support**: Complete support for bot's interactive workflow (URL → Buttons → File)

#### ✅ **Advanced Download Management**
- **Progress Tracking Fixes**: Resolved issues where downloads would complete session prematurely
- **Timeout Handling**: 5-minute timeouts for large file downloads (40-50MB FLAC files)
- **Download Verification**: File size and existence validation before marking tracks complete
- **Lost Track Prevention**: Fixed issue where tracks could get stuck in "sent_to_bot" status

#### ✅ **Flexible Processing Options**
- **Sequential Mode**: `--sequential` for one-track-at-a-time processing (cleaner progress display)
- **Parallel Mode**: Default fast processing for large playlists
- **Chunked Downloads**: `--start-from N` and `--limit N` for processing playlists in manageable chunks
- **True Batch Processing**: Waits for entire batch completion before starting next batch

#### ✅ **Enhanced File Organization**
- **Playlist-Based Folders**: Files organized in folders named after playlist (e.g., "Vol rise/")
- **Clean Filenames**: "Artist - Track Name.flac" format with filesystem-safe character handling
- **Collision Prevention**: Smart handling of duplicate filenames

#### ✅ **Debug & Monitoring Features**
- **Debug Mode**: `--debug` flag for detailed logging when troubleshooting
- **Real-time Progress**: Live updates on batch completion and download progress
- **Comprehensive Reporting**: Detailed session statistics and file organization

### v2.0.1 - Security Fix & Dry Run Enhancement
- **Security Incident**: Accidentally exposed Spotify credentials were removed
- **Repository Reset**: Clean history with no exposed credentials
- **Dry Run Mode**: Now works without Telegram credentials for testing
- **Git Configuration**: Proper author attribution setup

### Dry Run Testing
Successfully tested with a 101-track playlist:
```bash
python run.py "https://open.spotify.com/playlist/3i1D6J1DTyoGfaXMvz5M8E" --dry-run
# Output: Found 101 tracks from "Vol rise" playlist
```

## Security Best Practices Learned

1. **Never edit .env.example with real credentials**
   - Always use placeholder values in example files
   - Real credentials go only in .env (which is gitignored)

2. **Quick Response to Credential Exposure**
   - Immediately revoke exposed credentials
   - Clean repository history or create fresh repository
   - Update all affected credentials

3. **Git Configuration**
   ```bash
   git config user.name "Your Name"
   git config user.email "your-email@example.com"
   ```

## Future Enhancements

- [ ] Web UI for easier interaction
- [ ] Multiple bot support
- [ ] Playlist monitoring for new tracks
- [ ] Audio format conversion
- [ ] Metadata tagging
- [ ] Cloud storage integration
- [ ] Docker containerization
- [ ] API rate limit visualization
- [ ] Automatic credential validation on startup