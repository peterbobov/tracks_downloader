# Spotify DJ Track Downloader

Automate downloading DJ tracks from Spotify playlists using your Telegram bot.

## Features

- Extract all tracks from Spotify playlists
- Automatically send track URLs to your Telegram bot
- Monitor and download FLAC file responses
- Progress tracking and resume capability
- Batch processing with rate limiting
- Colored terminal output for better visibility

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Run basic downloader:**
   ```bash
   python spotify_downloader.py <playlist_url>
   ```

4. **Run with Telegram monitoring (recommended):**
   ```bash
   python telegram_monitor.py <playlist_url>
   ```

## Setup

### Spotify API
1. Visit [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create new app
3. Copy Client ID and Client Secret to `.env`

### Telegram Bot
1. Get bot token from BotFather
2. Get your chat ID (send message to bot, check API)
3. Add to `.env` file

## Usage Examples

**Basic download:**
```bash
python spotify_downloader.py https://open.spotify.com/playlist/xxxxx
```

**Dry run (preview tracks):**
```bash
python spotify_downloader.py https://open.spotify.com/playlist/xxxxx --dry-run
```

**Check progress:**
```bash
python spotify_downloader.py --status
```

**Reset progress:**
```bash
python spotify_downloader.py --reset
```

**Enhanced mode with Telegram monitoring:**
```bash
python telegram_monitor.py https://open.spotify.com/playlist/xxxxx
```

## File Structure

```
spotify_downloader/
├── spotify_downloader.py    # Basic downloader
├── telegram_monitor.py      # Enhanced with file monitoring
├── requirements.txt         # Dependencies
├── .env.example            # Configuration template
├── .env                    # Your configuration (create this)
├── progress.json           # Progress tracking
└── downloads/              # Downloaded files
```

## Configuration Options

Edit `.env` file:

- `SPOTIFY_CLIENT_ID`: Your Spotify app client ID
- `SPOTIFY_CLIENT_SECRET`: Your Spotify app client secret
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- `TELEGRAM_CHAT_ID`: Your chat ID with the bot
- `DOWNLOAD_FOLDER`: Where to save files (default: ./downloads)
- `DELAY_BETWEEN_REQUESTS`: Seconds between requests (default: 3)
- `MAX_RETRIES`: Maximum retry attempts (default: 3)
- `REQUEST_TIMEOUT`: Request timeout in seconds (default: 30)

## Progress Tracking

The downloader saves progress to `progress.json`:
- Tracks already processed (won't re-download)
- Failed tracks with reasons
- Downloaded file paths

Resume interrupted sessions by running the same command again.

## Troubleshooting

**Bot not responding:**
- Check bot token and chat ID
- Ensure bot is started (/start command)
- Verify you're using correct chat

**Spotify API errors:**
- Verify Client ID and Secret
- Check playlist is public or you have access
- Ensure playlist URL is correct format

**Download failures:**
- Not all tracks available as FLAC
- Bot may have rate limits
- Network timeouts - will retry

## Limitations

- Bot response monitoring in basic mode is simplified
- telegram_monitor.py provides better file detection
- Respect rate limits to avoid bans
- Some tracks may not be available

## Safety Features

- Automatic progress saving
- Resume capability
- Duplicate detection
- Safe file naming
- Error logging

## Tips

1. Start with small playlists for testing
2. Use dry-run mode to preview
3. Monitor first few downloads manually
4. Adjust delays if getting rate limited
5. Check progress.json if issues occur