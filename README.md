# Spotify Playlist Downloader v2.1.0

🎵 **Automated FLAC downloader for Spotify playlists using Telegram bot integration**

Automate the process of downloading high-quality FLAC files from Spotify playlists using the [@LosslessRobot](https://t.me/LosslessRobot) Telegram bot. This tool handles the complete workflow: extracting playlist tracks, sending them to the bot, automatically clicking response buttons, and downloading the resulting FLAC files.

## ✨ Key Features

- 🤖 **Interactive Bot Support** - Automatically handles [@LosslessRobot](https://t.me/LosslessRobot) button responses
- 📁 **Smart Organization** - Files organized by playlist name with clean "Artist - Track.flac" naming
- ⚡ **Flexible Processing** - Sequential or parallel modes, chunked downloads for large playlists
- 🔄 **Resume Capability** - Intelligent progress tracking with session recovery
- 🛡️ **Robust Error Handling** - Handles timeouts, failures, and "not found" responses gracefully
- 🎯 **Batch Processing** - True batch completion before moving to next set of tracks
- 🐛 **Debug Mode** - Optional detailed logging for troubleshooting

## 🚀 Quick Start

### 1. Setup Environment
```bash
# Clone and setup
git clone <your-repo-url>
cd spotify_downloader

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Get API Credentials

#### Spotify API Setup
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Click **"Create App"**
3. Fill in app details (name: "Playlist Downloader", description: "Personal use")
4. Note your **Client ID** and **Client Secret**

#### Telegram API Setup  
1. Go to [https://my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Click **"API development tools"**
4. Create a new application:
   - **App title**: Spotify Downloader
   - **Short name**: spotifydl  
   - **Platform**: Desktop
5. Note your **api_id** (number) and **api_hash** (string)

#### Bot Setup
1. Start a chat with [@LosslessRobot](https://t.me/LosslessRobot) on Telegram
2. Send `/start` to activate the bot
3. The bot username to use: `@LosslessRobot`

### 3. Configure Credentials
```bash
# Copy example configuration
cp .env.example .env

# Edit .env with your credentials (use your favorite editor)
nano .env
```

Add your real credentials to `.env`:
```bash
# Spotify API Credentials  
SPOTIFY_CLIENT_ID=your_actual_client_id_here
SPOTIFY_CLIENT_SECRET=your_actual_client_secret_here

# Telegram API Configuration
TELEGRAM_API_ID=your_actual_api_id_here
TELEGRAM_API_HASH=your_actual_api_hash_here  
TELEGRAM_PHONE_NUMBER=+1234567890

# External Bot Configuration
EXTERNAL_BOT_USERNAME=@LosslessRobot
```

### 4. First Run (Authentication)
```bash
# Test with a single track first
python run.py "https://open.spotify.com/playlist/xxxxx" --limit 1

# You'll be prompted to enter the Telegram verification code sent to your phone
```

## 📖 Usage Examples

### Basic Usage
```bash
# Download entire playlist
python run.py "https://open.spotify.com/playlist/xxxxx"

# Preview tracks without downloading  
python run.py "https://open.spotify.com/playlist/xxxxx" --dry-run

# Test with single track
python run.py "https://open.spotify.com/playlist/xxxxx" --limit 1
```

### Advanced Options
```bash
# Sequential processing (cleaner progress display)
python run.py "https://open.spotify.com/playlist/xxxxx" --sequential

# Chunked processing (recommended for large playlists)
python run.py "https://open.spotify.com/playlist/xxxxx" --start-from 1 --limit 15 --batch-size 5
python run.py "https://open.spotify.com/playlist/xxxxx" --start-from 16 --limit 15 --batch-size 5

# Debug mode for troubleshooting
python run.py "https://open.spotify.com/playlist/xxxxx" --debug

# Custom batch size and output directory
python run.py "https://open.spotify.com/playlist/xxxxx" --batch-size 3 --output-dir ./music
```

### Session Management
```bash
# Check current progress
python run.py status

# Generate detailed report
python run.py report

# Reset all progress
python run.py reset
```

## 🛠️ Command Line Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview tracks without downloading |
| `--limit N` | Limit to first N tracks (for testing) |
| `--start-from N` | Start from track number N (1-based) |
| `--batch-size N` | Process N tracks at a time (default: 10) |
| `--sequential` | Process tracks one at a time (cleaner progress) |
| `--debug` | Enable detailed debug logging |
| `--no-resume` | Don't resume previous session |
| `--output-dir DIR` | Set download directory |

## 📁 File Organization

Files are automatically organized as:
```
downloads/
└── Playlist Name/
    ├── Artist - Track Name.flac
    ├── Another Artist - Another Track.flac
    └── ...
```

Example:
```
downloads/
└── Vol rise/
    ├── Barry Can't Swim - Different.flac
    ├── mischluft - Call Me Babe.flac
    └── Vladimir Dubyshkin - the rothschild party.flac
```

## 🔧 How It Works

1. **Extract playlist tracks** from Spotify API
2. **Send track URLs** to [@LosslessRobot](https://t.me/LosslessRobot) via your Telegram account
3. **Auto-click first option** when bot provides track choices
4. **Download FLAC files** when bot responds with audio
5. **Handle failures gracefully** when tracks aren't found
6. **Organize files** with clean naming in playlist folders

## ⚙️ Configuration Options

The `.env` file supports these options:

```bash
# Spotify API (Required)
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret

# Telegram API (Required)  
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE_NUMBER=+1234567890
EXTERNAL_BOT_USERNAME=@LosslessRobot

# Optional Settings
DOWNLOAD_FOLDER=./downloads
DELAY_BETWEEN_REQUESTS=3.0
MAX_RETRIES=3
RESPONSE_TIMEOUT=300
FLOOD_WAIT_MULTIPLIER=1.5
```

## 🔍 Processing Modes

### Parallel Mode (Default)
- Sends multiple tracks simultaneously with delays
- Faster for large playlists
- Progress bars may overlap

### Sequential Mode (`--sequential`)
- Processes one track at a time
- Cleaner progress display  
- Safer for account limits

### Chunked Processing
Perfect for large playlists:
```bash
# Process tracks 1-15
python run.py "playlist_url" --start-from 1 --limit 15 --batch-size 5

# Process tracks 16-30  
python run.py "playlist_url" --start-from 16 --limit 15 --batch-size 5

# Continue with tracks 31-45
python run.py "playlist_url" --start-from 31 --limit 15 --batch-size 5
```

## 🛡️ Security & Safety

### Account Safety
- **3-second delays** between requests (configurable)
- **Conservative rate limiting** to protect your Telegram account
- **Flood wait handling** with exponential backoff
- **Session file encryption** (stored in `./sessions/`)

### Data Protection
- Credentials stored in `.env` (never committed to git)
- Session files are gitignored and encrypted
- No hardcoded credentials in source code

### Best Practices
1. **Start with small playlists** (5-10 tracks) for testing
2. **Use `--dry-run`** to preview before downloading
3. **Monitor first few downloads** manually
4. **Respect the bot's limits** - don't spam requests
5. **Keep credentials secure** - never share `.env` or `sessions/`

## 📊 Progress Tracking

The system maintains detailed progress in `progress.json`:
- ✅ **Completed tracks** with file paths and sizes
- ❌ **Failed tracks** with error reasons  
- ⏳ **Pending tracks** ready to retry
- 📈 **Session statistics** and timing

Resume interrupted sessions by running the same command again.

## 🐛 Troubleshooting

### Common Issues

**"Failed to initialize Telegram client"**
- Check your `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`
- Ensure phone number format: `+1234567890`
- Delete `sessions/` folder and re-authenticate

**"Bot not responding"**
- Verify `@LosslessRobot` is spelled correctly
- Check that you've started the bot with `/start`
- Try `--debug` mode to see detailed logs

**"Download timeout"** 
- Large files (40-50MB) can take time
- Check internet connection
- Bot might be rate-limited, try again later

**"Track not found"**
- Not all tracks are available as FLAC
- Bot will show "nothing found" image - this is normal
- Track will be marked as failed and skipped

### Debug Mode
```bash
python run.py "playlist_url" --debug --limit 1
```
Shows detailed logs including:
- Message types received from bot
- Button detection and clicking
- Download progress and file verification
- Progress tracking updates

## 🚫 Limitations

- **External bot dependency** - Relies on [@LosslessRobot](https://t.me/LosslessRobot) availability
- **FLAC availability** - Not all tracks available in lossless format
- **Rate limits** - Telegram has daily/hourly message limits
- **Account risk** - Using automation on personal account (minimal with conservative settings)

## 📜 Version History

### v2.1.0 (June 2025) - Interactive Bot Support
- ✅ Full interactive bot support with automatic button clicking
- ✅ Enhanced progress tracking and download management
- ✅ Playlist-based file organization
- ✅ Flexible processing modes (sequential/parallel/chunked)
- ✅ Debug mode and comprehensive error handling

### v2.0.0 - Modular Architecture  
- ✅ Complete rewrite with modular design
- ✅ Advanced CLI interface
- ✅ Session management and resume capability

## 🤝 Contributing

This project is designed for personal use with [@LosslessRobot](https://t.me/LosslessRobot). Contributions welcome for:
- Bug fixes and improvements
- Better error handling
- Additional bot support
- Documentation updates

## ⚖️ Legal Notice

This tool is for personal use only. Respect:
- Spotify's Terms of Service
- Telegram's Terms of Service  
- Copyright laws in your jurisdiction
- Bot operator's rules and limits

## 🙏 Acknowledgments

- **[@LosslessRobot](https://t.me/LosslessRobot)** - The Telegram bot that makes this possible
- **Telethon** - Excellent Telegram client library
- **Spotipy** - Spotify Web API wrapper