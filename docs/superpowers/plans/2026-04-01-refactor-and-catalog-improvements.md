# Refactor & Catalog Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the Spotify downloader with clean module boundaries, eliminate dead code, and make "download only missing tracks" the default behavior with Spotify ID-based dedup.

**Architecture:** Thin CLI (`run.py`) → orchestrator (`src/downloader.py`) → specialized modules (catalog, telegram, file manager). Catalog uses SQLite with `spotify_id` as primary dedup key, `artist:title` hash as fallback with auto-backfill.

**Tech Stack:** Python 3.12+, SQLite, Telethon, Spotipy, mutagen, fuzzywuzzy, colorama

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Delete | `spotify_downloader.py` | Legacy — uses wrong Telegram API |
| Delete | `telethon_downloader.py` | Legacy — old monolithic version |
| Delete | `telegram_monitor.py` | Legacy — experimental webhook approach |
| Delete | `src/missing_tracks.py` | Absorbed by catalog lookup chain |
| Rename | `src/main.py` → `src/downloader.py` | Orchestrator |
| Modify | `src/catalog.py` | Add `spotify_id`, WAL mode, lookup chain |
| Modify | `src/file_manager.py` | Remove catalog awareness |
| Modify | `src/spotify_api.py` | Use `utils.sanitize_filename` |
| Modify | `src/utils.py` | Add canonical `sanitize_filename` |
| Modify | `src/constants.py` | Update `DEFAULT_BATCH_SIZE` to 3 |
| Modify | `run.py` | Thin CLI, simplified flags |
| Modify | `pyproject.toml` | Version bump |

---

### Task 1: Delete legacy files

**Files:**
- Delete: `spotify_downloader.py`
- Delete: `telethon_downloader.py`
- Delete: `telegram_monitor.py`

- [ ] **Step 1: Delete the three legacy files**

```bash
rm spotify_downloader.py telethon_downloader.py telegram_monitor.py
```

- [ ] **Step 2: Verify no imports reference them**

```bash
cd /Users/peterbobov/coding/spotify_downloader && grep -r "import.*spotify_downloader\|import.*telethon_downloader\|import.*telegram_monitor" src/ run.py
```

Expected: no matches.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "chore: delete legacy files (spotify_downloader.py, telethon_downloader.py, telegram_monitor.py)"
```

---

### Task 2: Add `sanitize_filename` to `src/utils.py`

**Files:**
- Modify: `src/utils.py` (add function after line 171)
- Modify: `src/constants.py:50-66` (already has `FileConstants`)

- [ ] **Step 1: Add `sanitize_filename` to `src/utils.py`**

Add at the end of the file:

```python
def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """
    Sanitize a string for use as a filename.

    Removes invalid filesystem characters, collapses whitespace,
    and truncates to max_length.

    Args:
        filename: The raw filename string
        max_length: Maximum allowed length (default: 200)

    Returns:
        Filesystem-safe filename string
    """
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')

    # Remove control characters
    filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)

    # Collapse whitespace
    filename = re.sub(r'\s+', ' ', filename).strip()

    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')

    return filename[:max_length]
```

- [ ] **Step 2: Verify utils module loads**

```bash
cd /Users/peterbobov/coding/spotify_downloader && uv run python -c "from src.utils import sanitize_filename; print(sanitize_filename('Test <File>: Name?.flac'))"
```

Expected: `Test File Name.flac`

- [ ] **Step 3: Commit**

```bash
git add src/utils.py && git commit -m "feat: add canonical sanitize_filename to utils"
```

---

### Task 3: Update `src/spotify_api.py` to use `utils.sanitize_filename`

**Files:**
- Modify: `src/spotify_api.py:54-57` (`filename_safe_name` property)
- Modify: `src/spotify_api.py:170-185` (`sanitize_filename` static method — keep but delegate)

- [ ] **Step 1: Update imports in `src/spotify_api.py`**

Add at the top of the file, after the existing imports (after line 24):

```python
from src.utils import sanitize_filename as _sanitize_filename
```

- [ ] **Step 2: Replace `Track.filename_safe_name` property**

Replace lines 54-57:

```python
    @property
    def filename_safe_name(self) -> str:
        """Return filename-safe version of track name"""
        return SpotifyExtractor.sanitize_filename(f"{self.artist_string} - {self.name}")
```

With:

```python
    @property
    def filename_safe_name(self) -> str:
        """Return filename-safe version of track name"""
        return _sanitize_filename(f"{self.artist_string} - {self.name}")
```

- [ ] **Step 3: Replace `SpotifyExtractor.sanitize_filename`**

Replace the static method at lines 170-185 to delegate:

```python
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename. Delegates to utils.sanitize_filename."""
        return _sanitize_filename(filename)
```

- [ ] **Step 4: Verify**

```bash
cd /Users/peterbobov/coding/spotify_downloader && uv run python -c "from src.spotify_api import Track; t = Track(id='x', name='Test?', artists=['A'], album='B', url='u', duration_ms=1000); print(t.filename_safe_name)"
```

Expected: `A - Test`

- [ ] **Step 5: Commit**

```bash
git add src/spotify_api.py && git commit -m "refactor: delegate sanitize_filename to utils in spotify_api"
```

---

### Task 4: Update `src/file_manager.py` — remove catalog, use shared sanitize

**Files:**
- Modify: `src/file_manager.py`

- [ ] **Step 1: Update imports**

Replace the imports at lines 1-22. Remove the catalog imports and add utils:

```python
from src.utils import sanitize_filename as _sanitize_filename
```

Remove these lines:
```python
from src.catalog import LibraryCatalog, create_catalog
```

- [ ] **Step 2: Replace `sanitize_filename` static method (lines 73-99)**

Replace with delegation:

```python
    @staticmethod
    def sanitize_filename(filename: str, max_length: int = 200) -> str:
        """Sanitize filename. Delegates to utils.sanitize_filename."""
        return _sanitize_filename(filename, max_length)
```

- [ ] **Step 3: Remove `enable_catalog` method (lines 105-107)**

Delete:
```python
    def enable_catalog(self, catalog: LibraryCatalog):
        """Enable catalog integration for downloaded tracks"""
        self.catalog = catalog
```

- [ ] **Step 4: Remove catalog from `__init__` (line 63)**

Remove `self.catalog = None` from `__init__`.

- [ ] **Step 5: Remove catalog calls from `move_to_organized_location` (lines 253-259)**

In `move_to_organized_location`, remove the catalog block:

```python
            # Add to catalog if enabled
            if self.catalog:
                try:
                    self.catalog.add_track(str(final_path), self.current_playlist_name)
                except Exception as e:
                    print(f"  Warning: Failed to add to catalog: {e}")
```

- [ ] **Step 6: Verify module loads**

```bash
cd /Users/peterbobov/coding/spotify_downloader && uv run python -c "from src.file_manager import FileManager; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add src/file_manager.py && git commit -m "refactor: remove catalog awareness from file_manager, use shared sanitize_filename"
```

---

### Task 5: Add `spotify_id` to catalog schema + WAL mode + migration

**Files:**
- Modify: `src/catalog.py:80-115` (`_init_database`)
- Modify: `src/catalog.py:117-126` (`generate_track_id`)
- Modify: `src/catalog.py:225-276` (`add_track`)
- Modify: `src/catalog.py:313-325` (`find_track`)

- [ ] **Step 1: Update `_init_database` (lines 80-115)**

Add WAL mode and `spotify_id` column. Replace the method:

```python
    def _init_database(self):
        """Initialize the SQLite database schema with migration support"""
        with self._get_connection() as conn:
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")

            conn.execute('''
                CREATE TABLE IF NOT EXISTS tracks (
                    id TEXT PRIMARY KEY,
                    spotify_id TEXT,
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
                )
            ''')

            # Create indexes
            conn.execute('CREATE INDEX IF NOT EXISTS idx_artist ON tracks(artist)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_title ON tracks(title)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_playlist_source ON tracks(playlist_source)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_file_path ON tracks(file_path)')
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_spotify_id ON tracks(spotify_id)')

            # Migration: add spotify_id column if upgrading from older schema
            cursor = conn.execute("PRAGMA table_info(tracks)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'spotify_id' not in columns:
                conn.execute('ALTER TABLE tracks ADD COLUMN spotify_id TEXT')
                conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_spotify_id ON tracks(spotify_id)')

            conn.commit()
```

- [ ] **Step 2: Add `find_track_by_spotify_id` method**

Add after `find_track` (after line 325):

```python
    def find_track_by_spotify_id(self, spotify_id: str) -> Optional[CatalogTrack]:
        """Find a track by its Spotify ID.

        Args:
            spotify_id: The Spotify track ID

        Returns:
            CatalogTrack if found and file exists, None otherwise
        """
        if not spotify_id:
            return None

        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT * FROM tracks WHERE spotify_id = ?',
                (spotify_id,)
            )
            row = cursor.fetchone()
            if row:
                track = CatalogTrack(*row)
                if Path(track.file_path).exists():
                    return track
                # Stale entry — file no longer exists
                self.remove_track_by_path(track.file_path)
            return None
```

- [ ] **Step 3: Add `backfill_spotify_id` method**

Add after the new method:

```python
    def backfill_spotify_id(self, track_id: str, spotify_id: str) -> bool:
        """Backfill spotify_id for an existing track matched by artist:title hash.

        Args:
            track_id: The MD5 hash track ID
            spotify_id: The Spotify track ID to store

        Returns:
            True if updated, False otherwise
        """
        if not spotify_id:
            return False

        try:
            with self._get_connection() as conn:
                conn.execute(
                    'UPDATE tracks SET spotify_id = ? WHERE id = ? AND spotify_id IS NULL',
                    (spotify_id, track_id)
                )
                conn.commit()
                return conn.total_changes > 0
        except Exception:
            return False
```

- [ ] **Step 4: Update `add_track` to accept `spotify_id`**

In the `add_track` method (lines 225-276), update the signature and INSERT statement.

Change the method signature from:
```python
    def add_track(self, file_path: str, playlist_source: str = None) -> Optional[CatalogTrack]:
```
To:
```python
    def add_track(self, file_path: str, playlist_source: str = None, spotify_id: str = None) -> Optional[CatalogTrack]:
```

In the INSERT statement inside `add_track`, add `spotify_id` to the columns and values. Find the existing INSERT:
```python
                conn.execute('''
                    INSERT OR REPLACE INTO tracks
                    (id, title, artist, album, file_path, playlist_source,
                     date_added, file_size, duration_seconds, file_format, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    track_id,
```

Update to:
```python
                conn.execute('''
                    INSERT OR REPLACE INTO tracks
                    (id, spotify_id, title, artist, album, file_path, playlist_source,
                     date_added, file_size, duration_seconds, file_format, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    track_id,
                    spotify_id,
```

- [ ] **Step 5: Update `CatalogTrack` dataclass (lines 29-42)**

Add `spotify_id` field after `id`:

```python
@dataclass
class CatalogTrack:
    """Data class representing a cataloged track"""
    id: str
    spotify_id: Optional[str]
    title: str
    artist: str
    album: str
    file_path: str
    playlist_source: str
    date_added: str
    file_size: int
    duration_seconds: int
    file_format: str
    metadata_json: str
```

Add the import at the top of the file:
```python
from typing import Optional, Dict, List
```

- [ ] **Step 6: Verify catalog works with new schema**

```bash
cd /Users/peterbobov/coding/spotify_downloader && uv run python -c "
from src.catalog import LibraryCatalog
import tempfile, os
db = tempfile.mktemp(suffix='.db')
cat = LibraryCatalog(db)
print('Schema OK')
os.unlink(db)
"
```

Expected: `Schema OK`

- [ ] **Step 7: Commit**

```bash
git add src/catalog.py && git commit -m "feat: add spotify_id to catalog schema with WAL mode and migration"
```

---

### Task 6: Update `src/constants.py` — batch size to 3

**Files:**
- Modify: `src/constants.py:73`

- [ ] **Step 1: Change `DEFAULT_BATCH_SIZE`**

Change line 73 from:
```python
    DEFAULT_BATCH_SIZE: int = 10
```
To:
```python
    DEFAULT_BATCH_SIZE: int = 3
```

- [ ] **Step 2: Commit**

```bash
git add src/constants.py && git commit -m "chore: change default batch size from 10 to 3"
```

---

### Task 7: Delete `src/missing_tracks.py`

**Files:**
- Delete: `src/missing_tracks.py`
- Modify: any files importing it

- [ ] **Step 1: Check for imports of missing_tracks**

```bash
cd /Users/peterbobov/coding/spotify_downloader && grep -r "missing_tracks" src/ run.py
```

- [ ] **Step 2: Remove all imports of `missing_tracks`**

Remove any `from src.missing_tracks import ...` lines found in `run.py` or other files.

- [ ] **Step 3: Delete the file**

```bash
rm src/missing_tracks.py
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: delete missing_tracks.py (absorbed by catalog)"
```

---

### Task 8: Rename `src/main.py` to `src/downloader.py` and refactor orchestrator

This is the largest task. The orchestrator gets catalog-first logic baked into its default flow.

**Files:**
- Rename: `src/main.py` → `src/downloader.py`
- Modify: `src/downloader.py` — add catalog lookup in download flow

- [ ] **Step 1: Rename the file**

```bash
cd /Users/peterbobov/coding/spotify_downloader && git mv src/main.py src/downloader.py
```

- [ ] **Step 2: Update imports in `src/downloader.py`**

At the top of the file, ensure catalog is imported. Find the existing imports and update:

```python
from src.catalog import LibraryCatalog, create_catalog
```

If `from src.file_manager import FileManager` references `enable_catalog`, remove that call later.

- [ ] **Step 3: Update `__init__` to own catalog directly**

In `SpotifyDownloader.__init__` (lines 195-240), the downloader already creates a catalog. Ensure it no longer passes it to file_manager. Find and remove any line like:

```python
self.file_manager.enable_catalog(self.catalog)
```

The catalog should be stored as `self.catalog` on the downloader itself.

- [ ] **Step 4: Add catalog-first check to `_start_new_session`**

In `_start_new_session` (lines 298-355), after tracks are fetched from Spotify, add the catalog check before processing. Find the section after tracks are extracted (around line 330-340) and add:

```python
        # Check catalog — skip tracks we already have
        if not dry_run:
            missing_tracks = []
            skipped = 0
            for track in tracks:
                # Check by spotify_id first
                found = self.catalog.find_track_by_spotify_id(track.id)
                if found:
                    skipped += 1
                    continue

                # Fallback: check by artist:title hash
                hash_id = LibraryCatalog.generate_track_id(track.artist_string, track.name)
                found = self.catalog.find_track(track.name, track.artist_string)
                if found:
                    # Backfill spotify_id
                    self.catalog.backfill_spotify_id(hash_id, track.id)
                    skipped += 1
                    continue

                missing_tracks.append(track)

            print(f"\n  Total: {len(tracks)} tracks")
            print(f"  Already in library: {skipped}")
            print(f"  To download: {len(missing_tracks)}")

            if not missing_tracks:
                print("\n  All tracks already in library!")
                return {"total": len(tracks), "skipped": skipped, "downloaded": 0}

            tracks = missing_tracks
```

- [ ] **Step 5: Add catalog entry after successful download**

In `_handle_file_downloaded` (lines 729-803), after the file is moved to its organized location, add:

```python
        # Add to catalog with spotify_id
        try:
            self.catalog.add_track(
                str(final_path),
                playlist_source=self.progress.current_session.get('playlist_name', ''),
                spotify_id=track.id
            )
        except Exception as e:
            if self.debug:
                print(f"  Warning: Failed to catalog track: {e}")
```

Find where `move_to_organized_location` returns successfully and add this after it.

- [ ] **Step 6: Update `DownloadConfig` default batch_size**

In the `DownloadConfig` dataclass (line 52):

Change:
```python
    batch_size: int = 10
```
To:
```python
    batch_size: int = 3
```

- [ ] **Step 7: Verify module loads**

```bash
cd /Users/peterbobov/coding/spotify_downloader && uv run python -c "from src.downloader import SpotifyDownloader, DownloadConfig; print('OK')"
```

Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "refactor: rename main.py to downloader.py, add catalog-first download flow"
```

---

### Task 9: Rewrite `run.py` as thin CLI

**Files:**
- Modify: `run.py` (full rewrite)

- [ ] **Step 1: Rewrite `run.py`**

Replace the entire file with a thin CLI that delegates to the orchestrator. The key changes:
- Replace `from src.main import` with `from src.downloader import`
- Remove `handle_check_missing` (~190 lines)
- Remove `handle_download_missing` (~214 lines)
- Remove `handle_catalog_library` (~52 lines)
- Remove `handle_report` (~21 lines)
- Simplify `create_parser` — remove `--check-missing`, `--download-missing`, `--catalog-library`, `--no-resume`, `--organize-by`, `--year-folders`, `--output-dir`
- Keep: `--dry-run`, `--batch-size`, `--limit`, `--start-from`, `--debug`, `--sequential`
- Add `catalog` as a subcommand target (like `status` and `reset`)
- Simplify `handle_download` — the downloader now handles missing-track logic internally

```python
#!/usr/bin/env python3
"""
Spotify DJ Track Automation - CLI Entry Point

Downloads DJ tracks from Spotify playlists via Telegram bot.
Only downloads tracks not already in your library.
"""

import sys
import asyncio
import argparse
from pathlib import Path

from dotenv import load_dotenv
from colorama import init as colorama_init, Fore, Style

load_dotenv()
colorama_init()


def print_banner():
    """Print application banner"""
    print(f"\n{Fore.CYAN}{'='*50}")
    print(f"  Spotify DJ Track Automation v3.0.0")
    print(f"{'='*50}{Style.RESET_ALL}\n")


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser with simplified flags"""
    parser = argparse.ArgumentParser(
        description="Download missing tracks from Spotify playlists via Telegram bot",
        add_help=True,
    )

    parser.add_argument(
        'target',
        nargs='?',
        help='Spotify playlist/album/track URL, or command: status, reset, catalog'
    )

    parser.add_argument('--dry-run', action='store_true',
                        help='Preview tracks without downloading')
    parser.add_argument('--batch-size', type=int, default=None,
                        help='Tracks per batch (default: 3)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Maximum number of tracks to process')
    parser.add_argument('--start-from', type=int, default=1,
                        help='Start from track N (1-indexed)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug output')
    parser.add_argument('--sequential', action='store_true',
                        help='Process tracks one at a time')
    parser.add_argument('--version', action='store_true',
                        help='Show version')

    return parser


async def handle_download(args):
    """Handle playlist download — only downloads missing tracks"""
    from src.downloader import SpotifyDownloader, DownloadConfig

    try:
        config = DownloadConfig.from_env()
    except ValueError as e:
        print(f"{Fore.RED}Configuration error: {e}{Style.RESET_ALL}")
        sys.exit(1)

    downloader = SpotifyDownloader(config)

    try:
        await downloader.initialize()

        if args.debug:
            downloader.set_debug_mode(True)

        result = await downloader.download_playlist(
            playlist_url=args.target,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            limit=args.limit,
            sequential=args.sequential,
            start_from=args.start_from,
        )

        # Print summary
        if result and not args.dry_run:
            print(f"\n{Fore.GREEN}{'='*50}")
            print(f"  Download Complete")
            print(f"{'='*50}{Style.RESET_ALL}")
            downloaded = result.get('downloaded', 0)
            failed = result.get('failed', 0)
            skipped = result.get('skipped', 0)
            if downloaded:
                print(f"  {Fore.GREEN}Downloaded: {downloaded}{Style.RESET_ALL}")
            if skipped:
                print(f"  {Fore.YELLOW}Already in library: {skipped}{Style.RESET_ALL}")
            if failed:
                print(f"  {Fore.RED}Failed: {failed}{Style.RESET_ALL}")

    finally:
        await downloader.cleanup()


async def handle_status(args):
    """Show current session status"""
    from src.downloader import SpotifyDownloader, DownloadConfig

    try:
        config = DownloadConfig.from_env()
    except ValueError as e:
        print(f"{Fore.RED}Configuration error: {e}{Style.RESET_ALL}")
        sys.exit(1)

    downloader = SpotifyDownloader(config)
    status = downloader.get_status()

    if not status:
        print(f"{Fore.YELLOW}No active session found.{Style.RESET_ALL}")
        return

    print(f"\n{Fore.CYAN}Session Status:{Style.RESET_ALL}")
    for key, value in status.items():
        print(f"  {key}: {value}")


async def handle_reset(args):
    """Reset current session"""
    from src.downloader import SpotifyDownloader, DownloadConfig

    try:
        config = DownloadConfig.from_env()
    except ValueError as e:
        print(f"{Fore.RED}Configuration error: {e}{Style.RESET_ALL}")
        sys.exit(1)

    downloader = SpotifyDownloader(config)
    downloader.reset_progress()
    print(f"{Fore.GREEN}Session reset successfully.{Style.RESET_ALL}")


async def handle_catalog(args):
    """Rebuild catalog from music library on disk"""
    from src.catalog import LibraryCatalog
    from src.downloader import DownloadConfig

    try:
        config = DownloadConfig.from_env()
    except ValueError as e:
        print(f"{Fore.RED}Configuration error: {e}{Style.RESET_ALL}")
        sys.exit(1)

    library_path = config.music_library_path
    if not Path(library_path).exists():
        print(f"{Fore.RED}Music library path not found: {library_path}{Style.RESET_ALL}")
        sys.exit(1)

    print(f"Scanning music library: {library_path}")

    catalog = LibraryCatalog()
    stats = catalog.scan_library(library_path)
    print(f"\n{Fore.GREEN}Catalog rebuilt:{Style.RESET_ALL}")
    print(f"  Tracks indexed: {stats.get('added', 0)}")
    print(f"  Skipped (already cataloged): {stats.get('skipped', 0)}")
    print(f"  Errors: {stats.get('errors', 0)}")


async def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()

    if args.version:
        print("spotify-downloader v3.0.0")
        return

    if not args.target:
        parser.print_help()
        return

    print_banner()

    # Route to handler
    if args.target == 'status':
        await handle_status(args)
    elif args.target == 'reset':
        await handle_reset(args)
    elif args.target == 'catalog':
        await handle_catalog(args)
    elif args.target.startswith('http'):
        await handle_download(args)
    else:
        print(f"{Fore.RED}Unknown command or invalid URL: {args.target}{Style.RESET_ALL}")
        parser.print_help()


if __name__ == '__main__':
    asyncio.run(main())
```

- [ ] **Step 2: Verify CLI help works**

```bash
cd /Users/peterbobov/coding/spotify_downloader && uv run python run.py --help
```

Expected: shows simplified help with no `--check-missing`, `--download-missing`, etc.

- [ ] **Step 3: Verify dry run still works**

```bash
cd /Users/peterbobov/coding/spotify_downloader && uv run python run.py --version
```

Expected: `spotify-downloader v3.0.0`

- [ ] **Step 4: Commit**

```bash
git add run.py && git commit -m "refactor: rewrite run.py as thin CLI layer"
```

---

### Task 10: Update `src/__init__.py` and `pyproject.toml`

**Files:**
- Modify: `src/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update version in `src/__init__.py`**

```python
__version__ = "3.0.0"
```

- [ ] **Step 2: Update `pyproject.toml`**

Change version:
```toml
version = "3.0.0"
```

Remove `fuzzywuzzy` and `python-levenshtein` from dependencies if no longer used in any src file. Check first:

```bash
cd /Users/peterbobov/coding/spotify_downloader && grep -r "fuzzywuzzy\|fuzz" src/
```

If still used in `telegram_client.py`, keep them. Otherwise remove.

- [ ] **Step 3: Commit**

```bash
git add src/__init__.py pyproject.toml && git commit -m "chore: bump version to 3.0.0"
```

---

### Task 11: Update `CLAUDE.md` with new CLI and architecture

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the Quick Start Commands section**

Replace the quick start commands to reflect the simplified CLI:

```markdown
## Quick Start Commands (v3.0.0)

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

# Rebuild catalog from disk
uv run python run.py catalog

# Check session progress
uv run python run.py status

# Reset session
uv run python run.py reset
```
```

- [ ] **Step 2: Update the project structure section**

```markdown
📁 **Project Structure:**
```
spotify_downloader/
├── src/
│   ├── __init__.py
│   ├── spotify_api.py         # Spotify API interactions
│   ├── telegram_client.py     # Telegram/Telethon handling
│   ├── file_manager.py        # Download organization
│   ├── catalog.py             # SQLite track database with spotify_id
│   ├── progress_tracker.py    # Session & progress management
│   ├── downloader.py          # Main orchestrator
│   ├── utils.py               # Shared utilities
│   └── constants.py           # Configuration constants
├── run.py                     # Thin CLI entry point
├── catalog.db                 # SQLite track catalog (auto-created)
├── pyproject.toml             # Project config and dependencies
├── .env.example               # Configuration template
└── .gitignore                 # Security exclusions
```
```

- [ ] **Step 3: Update implementation status to v3.0.0**

Remove references to deleted files, `--check-missing`, `--download-missing`, `--catalog-library` flags. Update to reflect that "download only missing" is the default behavior.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md && git commit -m "docs: update CLAUDE.md for v3.0.0 architecture"
```

---

### Task 12: Integration test — end-to-end dry run

- [ ] **Step 1: Run a dry-run to verify the full flow works**

```bash
cd /Users/peterbobov/coding/spotify_downloader && uv run python run.py "https://open.spotify.com/playlist/3i1D6J1DTyoGfaXMvz5M8E" --dry-run
```

Expected: Shows track list, no errors about missing imports or modules.

- [ ] **Step 2: Test catalog subcommand**

```bash
cd /Users/peterbobov/coding/spotify_downloader && uv run python run.py catalog
```

Expected: Scans library, shows stats.

- [ ] **Step 3: Test status subcommand**

```bash
cd /Users/peterbobov/coding/spotify_downloader && uv run python run.py status
```

Expected: Shows "No active session" or current session info.

- [ ] **Step 4: Fix any issues found**

If any imports are broken or methods are missing, fix them. Common issues to watch for:
- `from src.main import` → needs to be `from src.downloader import`
- Missing `spotify_id` parameter in catalog calls
- `enable_catalog` references that weren't cleaned up

- [ ] **Step 5: Final commit if fixes were needed**

```bash
git add -A && git commit -m "fix: resolve integration issues from refactor"
```
