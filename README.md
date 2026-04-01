# Spotify Playlist Downloader v3.0.0

Automated FLAC downloader for Spotify playlists using [@LosslessRobot](https://t.me/LosslessRobot) Telegram bot. Only downloads tracks not already in your library.

## Quick Start

```bash
# Install dependencies
uv sync

# Configure credentials
cp .env.example .env
# Edit .env with your API credentials

# Optional: index existing music library
uv run python run.py catalog

# Download missing tracks from a playlist
uv run python run.py "https://open.spotify.com/playlist/xxxxx"
```

## How It Works

1. Fetches playlist tracks from Spotify API
2. Checks each track against local catalog (`spotify_id` first, then `artist:title` hash)
3. Shows summary: "45 total, 12 in library, 33 to download"
4. Sends missing track URLs to [@LosslessRobot](https://t.me/LosslessRobot) via your Telegram account
5. Auto-clicks bot response buttons, downloads FLAC files
6. Organizes files as `{music_library}/Playlist Name/Artist - Track.flac`
7. Auto-catalogs downloaded tracks for future dedup

## Setup

### API Credentials

**Spotify:** [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) → Create App → note Client ID and Secret

**Telegram:** [my.telegram.org](https://my.telegram.org) → API development tools → note api_id and api_hash

**Bot:** Start a chat with [@LosslessRobot](https://t.me/LosslessRobot) and send `/start`

### Configuration (.env)

```bash
# Required
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE_NUMBER=+1234567890
EXTERNAL_BOT_USERNAME=@LosslessRobot

# Optional
MUSIC_LIBRARY_PATH=./music
DELAY_BETWEEN_REQUESTS=3.0
MAX_RETRIES=3
RESPONSE_TIMEOUT=600
```

## Usage

```bash
# Download missing tracks (default behavior)
uv run python run.py "https://open.spotify.com/playlist/xxxxx"

# Preview without downloading
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --dry-run

# Control batch size (default: 3)
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --batch-size 5

# Sequential processing (one track at a time)
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --sequential

# Process a slice of the playlist
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --start-from 16 --limit 15

# Debug output
uv run python run.py "https://open.spotify.com/playlist/xxxxx" --debug

# Rebuild catalog from existing files on disk
uv run python run.py catalog

# Check session progress
uv run python run.py status

# Reset session
uv run python run.py reset
```

## CLI Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview tracks without downloading |
| `--batch-size N` | Tracks per batch (default: 3) |
| `--limit N` | Maximum tracks to process |
| `--start-from N` | Start from track N (1-indexed) |
| `--sequential` | Process one track at a time |
| `--debug` | Enable debug logging |

## File Organization

```
music/
└── Playlist Name/
    ├── Barry Can't Swim - Different.flac
    ├── mischluft - Call Me Babe.flac
    └── Vladimir Dubyshkin - the rothschild party.flac
```

## Architecture

```
run.py              → Thin CLI (arg parsing, display)
src/downloader.py   → Orchestrator (fetch → check → download → catalog)
src/catalog.py      → SQLite track database (spotify_id + artist:title dedup)
src/telegram_client.py → Bot communication & response matching
src/file_manager.py → File operations (move, rename, collisions)
src/spotify_api.py  → Spotify API with caching
src/progress_tracker.py → Session persistence & resume
```

## Security

- Credentials in `.env` (gitignored)
- Telegram sessions encrypted locally in `./sessions/`
- 3-second delays between requests to protect account
- Flood wait handling with backoff

## Limitations

- Depends on [@LosslessRobot](https://t.me/LosslessRobot) availability
- Not all tracks available as FLAC
- Telegram rate limits apply

## Legal

Personal use only. Respect Spotify ToS, Telegram ToS, copyright laws, and bot operator rules.
