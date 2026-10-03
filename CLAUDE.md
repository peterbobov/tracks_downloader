# Spotify DJ Track Automation

## Overview
Automate the process of downloading DJ tracks from Spotify playlists using an external Telegram bot. This script will:
1. Extract all track URLs from a Spotify playlist
2. Send each URL to the external Telegram bot automatically via your user account
3. Monitor and download the returned FLAC files
4. Organize them in a folder structure

## Requirements
- Python 3.12+
- uv (Python package manager)
- ffmpeg (`brew install ffmpeg`) for AIFF conversion
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
uv sync
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

## Quick Start Commands (v3.1.0)

```bash
# Download missing tracks from playlist (default behavior)
uv run python run.py "https://open.spotify.com/playlist/xxxxx"

# Preview tracks without downloading
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --dry-run

# Control batch size (default: 3)
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --batch-size 5

# Sequential processing
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --sequential

# Process a slice of the playlist
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --start-from 16 --limit 15

# Debug mode
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --debug

# Also download tracks that only fuzzy-match the library
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --include-similar

# Keep FLAC instead of converting to AIFF
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --keep-flac

# Rebuild catalog from disk
uv run python run.py catalog

# Check session progress
uv run python run.py status

# Reset session
uv run python run.py reset
```

## Current Implementation Status (v3.0.0 - Clean Architecture & Smart Dedup)

### Architecture
- **Thin CLI** (`run.py`) — only parses args, delegates to orchestrator
- **Orchestrator** (`src/downloader.py`) — owns full flow: fetch → catalog check → download → catalog new
- **Catalog** (`src/catalog.py`) — SQLite with `spotify_id` as primary dedup key, normalized `artist:title` hash fallback, then fuzzy `find_similar`
- **Telegram Client** (`src/telegram_client.py`) — bot communication and response matching. Spotify URLs are sent directly (bot no longer resolves Tidal links). When the bot answers with a search-results menu (`Artist - Title [m:ss]` rows), `pick_search_result` clicks the one row whose artist/base title match and whose length is within 3s of Spotify's; if none fits the track fails. "💾 Скачать страницу" (downloads the whole results page) and other menus are never clicked. Received files are matched to the clicked row by audio tags + length (`file_matches_selection`); files matched by name must also be within 3s of the Spotify length (`duration_agrees`)
- **File Manager** (`src/file_manager.py`) — file operations only, no catalog awareness
- **Converter** (`src/converter.py`) — FLAC → AIFF (ffmpeg + mutagen tag/art copy), verifies then deletes FLAC
- **Spotify API** (`src/spotify_api.py`) — playlist/album/track extraction with caching

### Key Features
- **Download only missing tracks by default** — no special flags needed
- **Three-tier dedup** — `spotify_id` → normalized `artist:title` hash (accents/punctuation ignored: "Naté" = "Nate", "A, B" = "A & B") → fuzzy `match_score`. Fuzzy hits are skipped as "probably in library" and listed with their file path; `--include-similar` downloads them anyway. Fuzzy matching never equates different versions: titles must carry the same version markers (remix/extended/edit/dub/...), and remixes must match on remixer too
- **Dry run shows real plan** — `--dry-run` runs the library check, so it lists only what would actually be downloaded
- **Self-healing catalog** — backfills Spotify IDs on `artist:title` hash matches; `run.py catalog` rescans preserve existing Spotify IDs; entries whose file was deleted are dropped on lookup; when two files share artist:title, a lossless copy (FLAC/AIFF/WAV) is never replaced by a lossy one
- **Catalog schema versioning** — `PRAGMA user_version`; v2 recomputed all track IDs with `normalize_for_match` (merging rows that collide)
- **Auto-cataloging** — downloaded tracks automatically indexed with Spotify ID
- **WAL mode SQLite** — prevents database lock issues
- **Unified filename sanitization** — single implementation in `src/utils.py`
- **Default batch size 3** — matches bot reliability
- **AIFF output by default** — each downloaded FLAC is converted to AIFF (same bit depth/sample rate, tags + cover art copied) and the FLAC deleted; on failure the FLAC is kept. Existing library files are never converted. 
- **Rekordbox playlist file** — every run writes `<playlist>/<playlist>.m3u8` (UTF-8, absolute paths, Spotify order) covering all playlist tracks found in the library, including ones that live in other folders. Import in Rekordbox via File → Import → Playlist (dragging the folder only gets newly downloaded tracks)

📁 **Project Structure:**
```
spotify_downloader/
├── src/
│   ├── __init__.py
│   ├── spotify_api.py         # Spotify API interactions
│   ├── telegram_client.py     # Telegram/Telethon handling
│   ├── file_manager.py        # Download organization
│   ├── converter.py           # FLAC → AIFF conversion
│   ├── catalog.py             # SQLite track database with spotify_id
│   ├── progress_tracker.py    # Session & progress management
│   ├── downloader.py          # Main orchestrator
│   ├── utils.py               # Shared utilities
│   └── constants.py           # Configuration constants
├── tests/                     # pytest suite (uv run pytest)
├── run.py                     # Thin CLI entry point
├── catalog.db                 # SQLite track catalog (auto-created)
├── pyproject.toml             # Project config and dependencies (uv)
├── .env.example               # Configuration template
└── .gitignore                 # Security exclusions
```

## Quick Start

```bash
# Install dependencies
uv sync

# Configure credentials in .env file
cp .env.example .env
# Edit .env with your API credentials and set MUSIC_LIBRARY_PATH=./music

# Optional: catalog existing music (one-time setup)
uv run python run.py catalog

# Download missing tracks from a playlist
uv run python run.py "https://open.spotify.com/playlist/xxxxx"

# Preview first
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --dry-run
```

## Configuration

### Environment Variables (.env)
```bash
# Spotify API (Required)
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret

# Telegram API (Required)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE_NUMBER=+1234567890
EXTERNAL_BOT_USERNAME=@your_bot  # set bot Quality to "High (16bit)" — script converts FLAC → AIFF

# Optional Settings
MUSIC_LIBRARY_PATH=./music
DELAY_BETWEEN_REQUESTS=3.0
MAX_RETRIES=3
RESPONSE_TIMEOUT=600
```

### CLI Options
- `--dry-run`: Preview tracks without downloading
- `--batch-size N`: Tracks per batch (default: 3)
- `--limit N`: Maximum tracks to process
- `--start-from N`: Start from track N (1-indexed)
- `--sequential`: Process one track at a time
- `--keep-flac`: Skip AIFF conversion, keep downloaded FLACs
- `--include-similar`: Also download tracks that only fuzzy-match an existing library file
- `--debug`: Enable debug output

## Version History

### v3.1.0 (October 2026) - AIFF Output
- Added `src/converter.py`: downloaded FLACs are converted to AIFF and replaced (lossless, tags + art preserved)
- Catalog/progress record the `.aiff` path so dedup keeps working
- Catalog reads ID3 tags from AIFF; `.aiff`/`.aif` added to supported extensions
- Added `--keep-flac` flag and pytest suite
- Back to sending Spotify URLs; removed Tidal conversion (`src/link_converter.py`)
- Fixed: search-results menu was treated as a "download confirmation" and "Скачать страницу" clicked, downloading ~6 wrong versions per track; now picks one result by artist/title/duration
- Added `<playlist>.m3u8` export for Rekordbox import
- Fixed: catalog rescan could keep an MP3 over a FLAC of the same track
- Fixed: file sent after a selection was dropped when its label differed from Spotify's name; files of a different length are never matched to a track
- Matching: accent/punctuation-insensitive track IDs (schema v2 migration), fuzzy "probably in library" tier with version-marker guard, `--include-similar` flag
- Fixed: hash-match Spotify ID backfill never worked (swapped title/artist args)
- Fixed: `run.py catalog` rescan wiped stored Spotify IDs
- Fixed: `--dry-run` skipped the library check; `find_track` returned entries for deleted files
### v3.0.0 (April 2026) - Clean Architecture & Smart Dedup
- Deleted 3 legacy files, deleted `missing_tracks.py`
- Renamed `main.py` → `downloader.py`
- Added `spotify_id` column to catalog with WAL mode and migration
- Catalog-first download flow: checks `spotify_id` → `artist:title` hash → download
- Auto-backfills `spotify_id` on hash matches (self-healing catalog)
- Auto-catalogs downloaded tracks with Spotify ID
- Rewrote `run.py` as thin CLI (~160 lines, down from ~960)
- Unified `sanitize_filename` into `src/utils.py`
- Removed catalog awareness from `file_manager.py`
- Default batch size changed from 10 to 3
- Removed flags: `--check-missing`, `--download-missing`, `--catalog-library`, `--no-resume`, `--organize-by`, `--year-folders`, `--output-dir`
- Removed `report` subcommand
### v2.x (December 2025)
- Smart track matching with fuzzy string matching
- Interactive bot support with button clicking
- Memory leak fixes, request management improvements
- Playlist-based file organization
- SQLite catalog database with metadata extraction
- Missing track detection and download-missing workflow