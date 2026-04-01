# Refactor & Catalog Improvements Design

## Goal

Refactor the Spotify downloader to have clean module boundaries, eliminate dead code, and make "download only missing tracks" the default behavior. The catalog becomes the single source of truth for "do I already have this track?" with Spotify track IDs as the primary dedup key.

## Default Behavior

Running `uv run python run.py <playlist_url>`:

1. Fetches tracks from Spotify (including Spotify track IDs)
2. Checks each track against catalog: `spotify_id` first, then `artist:title` hash fallback
3. Backfills `spotify_id` on hash matches (self-healing catalog)
4. Displays summary: "45 total, 12 in library, 33 to download"
5. Downloads only missing tracks in batches of 3
6. Auto-catalogs each downloaded track with its Spotify ID

No special flags needed for this core flow.

## Simplified CLI

```
# Core usage - downloads missing tracks (default)
uv run python run.py <playlist_url>

# Preview only, no download
uv run python run.py <playlist_url> --dry-run

# Control batch size (default: 3)
uv run python run.py <playlist_url> --batch-size 5

# Sequential mode
uv run python run.py <playlist_url> --sequential

# Process a slice of the playlist
uv run python run.py <playlist_url> --start-from 16 --limit 15

# Debug output
uv run python run.py <playlist_url> --debug

# Utility commands
uv run python run.py catalog    # Rebuild catalog from disk
uv run python run.py status     # Show current session progress
uv run python run.py reset      # Reset session
```

### Removed flags

- `--check-missing` — now part of default flow
- `--download-missing` — now default behavior
- `--catalog-library` — becomes `catalog` subcommand
- `--no-resume` — unnecessary
- `--organize-by` — always playlist-based
- `--year-folders` — removed
- `--output-dir` — use `MUSIC_LIBRARY_PATH` env var
- `report` subcommand — unused, removed

## Module Architecture

### `run.py` — CLI only

- Parse arguments
- Call `SpotifyDownloader` methods
- Format and display output
- No imports from `catalog`, `file_manager`, or `telegram_client`

### `src/downloader.py` (renamed from `main.py`) — Orchestrator

- Owns the full flow: fetch → check catalog → download missing → catalog new
- Calls catalog for lookups and backfilling
- Calls telegram client to send/receive
- Calls file manager to move/rename files
- Manages batching, progress, retries

### `src/catalog.py` — Track database

Single source of truth for "do I have this track?"

- SQLite with `spotify_id` column (new)
- Lookup chain: `spotify_id` → `artist:title` hash → not found
- Backfill `spotify_id` on hash match
- `scan_library()` for full rebuild from disk
- Auto-cleanup of stale entries (file no longer exists on disk)
- Exact lookups only, no fuzzy matching

### `src/telegram_client.py` — Bot communication

- Send URLs to bot, handle button responses, receive files
- Smart matching of bot responses to pending requests (stays here — this is about matching bot responses, not library dedup)
- Download progress display

### `src/file_manager.py` — File operations only

- Move temp files to organized location (`{music_library_path}/{playlist_name}/Artist - Title.ext`)
- Sanitize filenames (delegates to `utils.sanitize_filename()`)
- Handle collisions (size/hash comparison, numeric suffixes)
- No catalog awareness — orchestrator coordinates between catalog and file manager
- `move_to_organized_location()` no longer auto-catalogs; orchestrator calls `catalog.add_track()` after successful move

### `src/spotify_api.py` — Unchanged

Already clean. Handles playlist/album/track extraction, caching, pagination.

### `src/progress_tracker.py` — Unchanged

Already clean. Session persistence, track status tracking, resume support. Tracks in-flight download state within a session. The catalog handles cross-session "do I have this?" checks; progress tracker handles within-session "did I already send this to the bot?".

### `src/utils.py` — Shared utilities

- Single `sanitize_filename()` implementation (replaces duplicates in file_manager.py and spotify_api.py; `Track.filename_safe_name` updated to use this)
- `normalize_text()` for string comparison
- Other shared helpers

### `src/constants.py` — Unchanged

Already well-organized. Update `DEFAULT_BATCH_SIZE` from 10 to 3.

### Deleted files

- `spotify_downloader.py` — legacy, uses wrong Telegram API approach
- `telethon_downloader.py` — legacy monolithic version
- `telegram_monitor.py` — legacy experimental approach
- `src/missing_tracks.py` — logic absorbed by catalog's lookup chain

## Catalog Schema

```sql
CREATE TABLE tracks (
    id TEXT PRIMARY KEY,              -- MD5 of "artist:title"
    spotify_id TEXT UNIQUE,           -- raw Spotify ID e.g. 4iV5W9uYEdYUVa79Axb7Rh (nullable for pre-existing)
    title TEXT,
    artist TEXT,
    album TEXT,
    file_path TEXT UNIQUE,
    playlist_source TEXT,
    date_added TEXT,
    file_size INTEGER,
    duration_seconds INTEGER,
    file_format TEXT,
    metadata_json TEXT
);

CREATE INDEX idx_spotify_id ON tracks(spotify_id);
CREATE INDEX idx_artist ON tracks(artist);
CREATE INDEX idx_title ON tracks(title);
CREATE INDEX idx_playlist_source ON tracks(playlist_source);
CREATE INDEX idx_file_path ON tracks(file_path);
```

### Migration

On first run after upgrade, if `spotify_id` column doesn't exist:

1. `ALTER TABLE tracks ADD COLUMN spotify_id TEXT`
2. `CREATE UNIQUE INDEX IF NOT EXISTS idx_spotify_id ON tracks(spotify_id)`

SQLite doesn't support `UNIQUE` constraints in `ALTER TABLE ADD COLUMN`, so the index is created separately. Existing rows get `NULL` for `spotify_id` — backfilled over time as playlists are processed.

## Download Flow

```
run.py: parse args, call downloader.download(playlist_url)
  │
  ├─ spotify_api: fetch playlist tracks (with spotify IDs)
  │
  ├─ catalog: for each track
  │    ├─ spotify_id match? → skip
  │    ├─ artist:title hash match? → backfill spotify_id, skip
  │    └─ no match → add to download queue
  │
  ├─ display: "45 total, 12 in library, 33 to download"
  │
  ├─ telegram_client: send URLs in batches of 3
  │    ├─ send batch → wait for responses → match to tracks
  │    └─ on file received → file_manager moves to final location
  │
  ├─ catalog: add_track() for each successful download (with spotify_id)
  │
  └─ display: summary report
```

## Error Handling

- **Bot fails a track:** Mark failed in progress tracker, continue with batch. Failed tracks shown in final summary.
- **Catalog DB locked:** SQLite WAL mode (set `PRAGMA journal_mode=WAL` on DB init), retry with backoff.
- **File already exists at target path:** Compare size/hash — skip if identical, add suffix if different.
- **Stale catalog entry (file deleted from disk):** Remove entry during lookup, treat as missing.
- **Large files (>50MB):** Use streaming hash instead of skipping comparison (fixes current bug).

## Key Improvements Over Current Code

1. **No flags needed for skip-existing** — default behavior
2. **Spotify ID as primary dedup key** — reliable, no fuzzy matching needed
3. **Self-healing catalog** — backfills Spotify IDs from playlist data over time
4. **Clean module boundaries** — each module has one job
5. **No duplicated code** — single sanitize_filename, single lookup chain
6. **Thin CLI** — run.py only parses args
7. **No dead code** — 3 legacy files deleted, missing_tracks.py absorbed
8. **Default batch size 3** — matches bot reliability
