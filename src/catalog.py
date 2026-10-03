#!/usr/bin/env python3
"""
Music Library Catalog Module

Handles track cataloging and database management including:
- SQLite database for track indexing
- Library scanning and metadata extraction
- Track lookup and duplicate detection
- Statistics and reporting across entire library
"""

import sqlite3
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import re

from fuzzywuzzy import fuzz

from .constants import FileConstants
from .utils import normalize_for_match

try:
    from mutagen import File as MutagenFile
    from mutagen.flac import FLAC
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False


# Catalog schema version (PRAGMA user_version)
# 2: track IDs use normalize_for_match (accent/punctuation-insensitive)
# 3: normalize_for_match transliterates ø/æ/ß/ł/... (IDs recomputed)
SCHEMA_VERSION = 3

# Formats preferred over lossy copies of the same track
LOSSLESS_EXTENSIONS = {'.flac', '.aiff', '.aif', '.wav'}

# Minimum match_score to treat a library track as "probably the same"
SIMILARITY_THRESHOLD = 90

# Title words that mark a distinct version (remix, extended, ...) of a track
VERSION_MARKERS = {
    'remix', 'rmx', 'mix', 'edit', 'version', 'extended', 'rework', 'dub', 'vip',
    'bootleg', 'radio', 'club', 'instrumental', 'acapella', 'live', 'cover',
    'flip', 'refix', 'reprise', 'remake', 'mashup',
}

# Featured-artist suffixes: "(feat. X)", "[ft. X]", "feat. X"
_FEAT_PATTERN = re.compile(
    r'[(\[]\s*(?:feat|ft|featuring)\b[^)\]]*[)\]]'
    r'|\s(?:feat|ft|featuring)\b\.?\s.*?(?=\s-\s|[(\[]|$)',
    re.IGNORECASE,
)


def core_title(title: str) -> str:
    """Normalized title without featured artists, remaster notes or 'original mix'"""
    result = normalize_for_match(_FEAT_PATTERN.sub(' ', title or ''))
    result = re.sub(r'\boriginal mix\b', ' ', result)
    result = re.sub(r'\b(?:\d{4} )?remaster(?:ed)?(?: \d{4})?(?: version)?\b', ' ', result)
    return ' '.join(result.split())


def match_score(title_a: str, artist_a: str, title_b: str, artist_b: str) -> float:
    """
    Similarity (0-100) between two tracks for duplicate detection.

    Titles must carry the same version markers (a remix never matches the
    original, an extended never matches a radio edit). Without markers, an
    extra subtitle on one side is tolerated; with markers, the whole title
    (including remixer) must match closely. Artists must overlap.
    """
    core_a, core_b = core_title(title_a), core_title(title_b)
    if not core_a or not core_b:
        return 0

    markers_a = VERSION_MARKERS.intersection(core_a.split())
    markers_b = VERSION_MARKERS.intersection(core_b.split())
    if markers_a != markers_b:
        return 0

    if markers_a:
        title_score = fuzz.token_sort_ratio(core_a, core_b)
    else:
        title_score = fuzz.token_set_ratio(core_a, core_b)

    artist_score = fuzz.token_set_ratio(normalize_for_match(artist_a), normalize_for_match(artist_b))
    return min(title_score, artist_score)


@dataclass
class CatalogTrack:
    """Track entry in the catalog database"""
    id: str  # MD5 hash of title + artist
    spotify_id: Optional[str]  # Raw Spotify track ID
    title: str
    artist: str
    album: Optional[str]
    file_path: str
    playlist_source: Optional[str]  # Which playlist it came from
    date_added: str
    file_size: int
    duration_seconds: Optional[int] = None
    file_format: Optional[str] = None
    metadata_json: Optional[str] = None  # JSON string of additional metadata


@dataclass
class CatalogStats:
    """Statistics about the music library catalog"""
    total_tracks: int
    total_size_bytes: int
    unique_artists: int
    unique_albums: int
    playlists: List[str]
    file_formats: Dict[str, int]
    newest_track: Optional[str]
    oldest_track: Optional[str]
    
    @property
    def total_size_mb(self) -> float:
        return round(self.total_size_bytes / (1024 * 1024), 2)
    
    @property
    def total_size_gb(self) -> float:
        return round(self.total_size_bytes / (1024 * 1024 * 1024), 2)


class LibraryCatalog:
    """Manages the music library catalog database"""
    
    def __init__(self, catalog_path: Optional[str] = None):
        """Initialize catalog with database path"""
        if catalog_path is None:
            catalog_path = "./catalog.db"
        
        self.catalog_path = Path(catalog_path)
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_database()
    
    def _init_database(self):
        """Initialize the SQLite database schema with migration support"""
        with sqlite3.connect(self.catalog_path) as conn:
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    id TEXT PRIMARY KEY,
                    spotify_id TEXT,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    album TEXT,
                    file_path TEXT NOT NULL UNIQUE,
                    playlist_source TEXT,
                    date_added TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    duration_seconds INTEGER,
                    file_format TEXT,
                    metadata_json TEXT
                )
            """)

            # Migration: add spotify_id column if upgrading from older schema
            cursor = conn.execute("PRAGMA table_info(tracks)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'spotify_id' not in columns:
                conn.execute('ALTER TABLE tracks ADD COLUMN spotify_id TEXT')

            # Link cache table — stores Tidal URLs keyed by Spotify track ID
            conn.execute("""
                CREATE TABLE IF NOT EXISTS link_cache (
                    spotify_id TEXT PRIMARY KEY,
                    tidal_url TEXT,
                    cached_at TEXT NOT NULL
                )
            """)

            # Create indexes (after migration so spotify_id column exists)
            conn.execute('CREATE INDEX IF NOT EXISTS idx_artist ON tracks(artist)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_title ON tracks(title)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_playlist_source ON tracks(playlist_source)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_file_path ON tracks(file_path)')
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_spotify_id ON tracks(spotify_id)')

            if conn.execute('PRAGMA user_version').fetchone()[0] < SCHEMA_VERSION:
                self._migrate_track_ids(conn)
                conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')

            conn.commit()

    def _migrate_track_ids(self, conn: sqlite3.Connection) -> None:
        """Recompute track IDs with the current normalization.

        Rows that now share an ID (e.g. "Naté" and "Nate") are merged, keeping
        the one whose file exists, then one with a spotify_id, then the newest;
        the kept row inherits a spotify_id from a merged row if it has none.
        """
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute('SELECT * FROM tracks')]
        conn.row_factory = None

        def preference(row):
            return (Path(row['file_path']).exists(), row['spotify_id'] is not None, row['date_added'] or '')

        best: Dict[str, Dict] = {}
        for row in rows:
            row['id'] = self.generate_track_id(row['title'], row['artist'])
            current = best.get(row['id'])
            if current is None:
                best[row['id']] = row
                continue
            winner, loser = (row, current) if preference(row) > preference(current) else (current, row)
            if winner['spotify_id'] is None:
                winner['spotify_id'] = loser['spotify_id']
            best[row['id']] = winner

        conn.execute('DELETE FROM tracks')
        columns = list(rows[0].keys()) if rows else []
        if columns:
            placeholders = ', '.join('?' for _ in columns)
            conn.executemany(
                f"INSERT INTO tracks ({', '.join(columns)}) VALUES ({placeholders})",
                [tuple(r[c] for c in columns) for r in best.values()],
            )
    
    @staticmethod
    def generate_track_id(title: str, artist: str) -> str:
        """Generate unique track ID from title and artist"""
        # Normalize strings for consistent ID generation (accent/punctuation-insensitive)
        normalized_title = normalize_for_match(title)
        normalized_artist = normalize_for_match(artist)
        
        # Create MD5 hash
        combined = f"{normalized_artist}:{normalized_title}"
        return hashlib.md5(combined.encode('utf-8')).hexdigest()
    
    def extract_metadata(self, file_path: Path) -> Dict:
        """Extract metadata from audio file"""
        metadata = {
            'title': None,
            'artist': None,
            'album': None,
            'duration_seconds': None,
            'file_format': None,
            'extra_metadata': {}
        }
        
        if not MUTAGEN_AVAILABLE:
            # Fallback to filename parsing
            return self._parse_metadata_from_filename(file_path, metadata)
        
        try:
            audio_file = MutagenFile(file_path)
            if audio_file is None:
                return self._parse_metadata_from_filename(file_path, metadata)
            
            # Get basic metadata
            metadata['duration_seconds'] = getattr(audio_file.info, 'length', None)
            if metadata['duration_seconds']:
                metadata['duration_seconds'] = int(metadata['duration_seconds'])
            
            metadata['file_format'] = audio_file.mime[0] if audio_file.mime else file_path.suffix.lower()
            
            # Extract tags based on file type
            if isinstance(audio_file, FLAC):
                metadata['title'] = audio_file.get('TITLE', [None])[0]
                metadata['artist'] = audio_file.get('ARTIST', [None])[0] or audio_file.get('PERFORMER', [None])[0]
                metadata['album'] = audio_file.get('ALBUM', [None])[0]
                
                # Store additional FLAC metadata
                for key in ['DATE', 'GENRE', 'TRACKNUMBER', 'ALBUMARTIST']:
                    if key in audio_file:
                        metadata['extra_metadata'][key] = audio_file[key][0]
            
            elif isinstance(audio_file, MP3) or isinstance(audio_file.tags, ID3):
                metadata['title'] = str(audio_file.get('TIT2', '')) if audio_file.get('TIT2') else None
                metadata['artist'] = str(audio_file.get('TPE1', '')) if audio_file.get('TPE1') else None
                metadata['album'] = str(audio_file.get('TALB', '')) if audio_file.get('TALB') else None
                
                # Store additional ID3 metadata (MP3, AIFF)
                for key in ['TDRC', 'TCON', 'TRCK', 'TPE2']:  # Year, Genre, Track, Album Artist
                    if key in audio_file:
                        metadata['extra_metadata'][key] = str(audio_file[key])
            
            else:
                # Generic handling for other formats
                tags = audio_file.tags
                if tags:
                    metadata['title'] = tags.get('TITLE', [None])[0] if hasattr(tags.get('TITLE', []), '__getitem__') else str(tags.get('TITLE', '')) or None
                    metadata['artist'] = tags.get('ARTIST', [None])[0] if hasattr(tags.get('ARTIST', []), '__getitem__') else str(tags.get('ARTIST', '')) or None
                    metadata['album'] = tags.get('ALBUM', [None])[0] if hasattr(tags.get('ALBUM', []), '__getitem__') else str(tags.get('ALBUM', '')) or None
        
        except Exception:
            # If metadata extraction fails, parse from filename
            pass
        
        # Fallback to filename parsing if no metadata found
        if not metadata['title'] or not metadata['artist']:
            metadata = self._parse_metadata_from_filename(file_path, metadata)
        
        return metadata
    
    def _parse_metadata_from_filename(self, file_path: Path, existing_metadata: Dict) -> Dict:
        """Parse artist and title from filename as fallback"""
        filename = file_path.stem  # Without extension
        
        # Common patterns: "Artist - Title", "Artist_Title", etc.
        separators = [' - ', ' – ', ' — ', '_', ' ~ ']
        
        for separator in separators:
            if separator in filename:
                parts = filename.split(separator, 1)
                if len(parts) == 2:
                    existing_metadata['artist'] = parts[0].strip()
                    existing_metadata['title'] = parts[1].strip()
                    break
        
        # If no separator found, use filename as title and try to get artist from parent folder
        if not existing_metadata['title']:
            existing_metadata['title'] = filename
            # Try to get artist from parent folder name
            parent_name = file_path.parent.name
            if parent_name not in ['downloads', 'music', '.']:
                existing_metadata['artist'] = parent_name
        
        # Set defaults if still empty
        if not existing_metadata['artist']:
            existing_metadata['artist'] = "Unknown Artist"
        if not existing_metadata['title']:
            existing_metadata['title'] = "Unknown Title"
        
        return existing_metadata
    
    def add_track(self, file_path: Path, playlist_source: Optional[str] = None,
                  spotify_id: Optional[str] = None,
                  metadata_override: Optional[Dict] = None) -> bool:
        """Add a track to the catalog"""
        try:
            # Check if file exists
            if not file_path.exists():
                return False
            
            # Extract or use provided metadata
            if metadata_override:
                metadata = metadata_override
            else:
                metadata = self.extract_metadata(file_path)
            
            # Generate track ID
            track_id = self.generate_track_id(metadata['title'], metadata['artist'])

            # One row per artist:title — never let a lossy copy replace an existing lossless one
            if self._existing_copy_is_better(track_id, file_path):
                return True

            # Keep a known spotify_id when re-adding without one (e.g. library rescan)
            if spotify_id is None:
                spotify_id = self._existing_spotify_id(file_path, track_id)
            
            # Prepare track data
            track_data = CatalogTrack(
                id=track_id,
                spotify_id=spotify_id,
                title=metadata['title'],
                artist=metadata['artist'],
                album=metadata.get('album'),
                file_path=str(file_path.absolute()),
                playlist_source=playlist_source,
                date_added=datetime.now().isoformat(),
                file_size=file_path.stat().st_size,
                duration_seconds=metadata.get('duration_seconds'),
                file_format=metadata.get('file_format'),
                metadata_json=json.dumps(metadata.get('extra_metadata', {})) if metadata.get('extra_metadata') else None
            )
            
            # Insert into database
            with sqlite3.connect(self.catalog_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO tracks
                    (id, spotify_id, title, artist, album, file_path, playlist_source, date_added,
                     file_size, duration_seconds, file_format, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    track_data.id, track_data.spotify_id, track_data.title, track_data.artist,
                    track_data.album, track_data.file_path, track_data.playlist_source,
                    track_data.date_added, track_data.file_size, track_data.duration_seconds,
                    track_data.file_format, track_data.metadata_json
                ))
                conn.commit()
            
            return True
            
        except Exception as e:
            print(f"Error adding track to catalog: {e}")
            return False
    
    def scan_library(self, library_path: Path, playlist_name: Optional[str] = None,
                    file_extensions: Optional[List[str]] = None) -> Tuple[int, int]:
        """
        Scan library directory and add all audio files to catalog
        Returns: (added_count, error_count)
        """
        if file_extensions is None:
            file_extensions = FileConstants.SUPPORTED_EXTENSIONS
        
        added_count = 0
        error_count = 0
        
        # Recursively find all audio files
        for ext in file_extensions:
            for file_path in library_path.rglob(f"*{ext}"):
                try:
                    # Determine playlist source from directory structure
                    source = playlist_name
                    if not source:
                        # Use immediate parent directory as playlist source
                        parent_dir = file_path.parent.name
                        if parent_dir not in ['downloads', 'music', '.']:
                            source = parent_dir
                    
                    if self.add_track(file_path, source):
                        added_count += 1
                    else:
                        error_count += 1
                        
                except Exception as e:
                    print(f"Error scanning {file_path}: {e}")
                    error_count += 1
        
        return added_count, error_count
    
    def _existing_copy_is_better(self, track_id: str, file_path: Path) -> bool:
        """True if the catalog already holds a lossless file for this track and the new one is lossy"""
        if file_path.suffix.lower() in LOSSLESS_EXTENSIONS:
            return False
        with sqlite3.connect(self.catalog_path) as conn:
            row = conn.execute('SELECT file_path FROM tracks WHERE id = ?', (track_id,)).fetchone()
        if not row or row[0] == str(file_path.absolute()):
            return False
        existing = Path(row[0])
        return existing.suffix.lower() in LOSSLESS_EXTENSIONS and existing.exists()

    def _existing_spotify_id(self, file_path: Path, track_id: str) -> Optional[str]:
        """Spotify ID already stored for this file or this artist:title, if any"""
        with sqlite3.connect(self.catalog_path) as conn:
            row = conn.execute(
                'SELECT spotify_id FROM tracks WHERE (file_path = ? OR id = ?) '
                'AND spotify_id IS NOT NULL ORDER BY file_path = ? DESC LIMIT 1',
                (str(file_path.absolute()), track_id, str(file_path.absolute()))
            ).fetchone()
        return row[0] if row else None

    def find_similar(self, title: str, artist: str,
                     threshold: float = SIMILARITY_THRESHOLD) -> Optional[Tuple[CatalogTrack, float]]:
        """Best fuzzy match (see match_score) among tracks whose file exists.

        Returns:
            (track, score) for the best match at or above threshold, else None
        """
        artist_tokens = set(normalize_for_match(artist).split())
        if not artist_tokens:
            return None

        best: Optional[Tuple[CatalogTrack, float]] = None
        with sqlite3.connect(self.catalog_path) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute('SELECT * FROM tracks'):
                # Cheap prefilter: artists must share at least one word
                if not artist_tokens & set(normalize_for_match(row['artist']).split()):
                    continue
                score = match_score(title, artist, row['title'], row['artist'])
                if score >= threshold and (best is None or score > best[1]):
                    track = CatalogTrack(**dict(row))
                    if Path(track.file_path).exists():
                        best = (track, score)
        return best

    def find_track(self, title: str, artist: str) -> Optional[CatalogTrack]:
        """Find a track by title and artist"""
        track_id = self.generate_track_id(title, artist)
        
        with sqlite3.connect(self.catalog_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
            row = cursor.fetchone()
            
            if row:
                track = CatalogTrack(**dict(row))
                if Path(track.file_path).exists():
                    return track
                # Stale entry — file no longer exists
                self.remove_track_by_path(track.file_path)

        return None

    def find_track_by_spotify_id(self, spotify_id: str) -> Optional[CatalogTrack]:
        """Find a track by its Spotify ID.

        Args:
            spotify_id: The Spotify track ID

        Returns:
            CatalogTrack if found and file exists, None otherwise
        """
        if not spotify_id:
            return None

        with sqlite3.connect(self.catalog_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                'SELECT * FROM tracks WHERE spotify_id = ?',
                (spotify_id,)
            )
            row = cursor.fetchone()
            if row:
                track = CatalogTrack(**dict(row))
                if Path(track.file_path).exists():
                    return track
                # Stale entry — file no longer exists
                self.remove_track_by_path(track.file_path)
        return None

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
            with sqlite3.connect(self.catalog_path) as conn:
                conn.execute(
                    'UPDATE tracks SET spotify_id = ? WHERE id = ? AND spotify_id IS NULL',
                    (spotify_id, track_id)
                )
                conn.commit()
                return conn.total_changes > 0
        except Exception:
            return False

    def get_tidal_url(self, spotify_id: str) -> Optional[str]:
        """Get cached Tidal URL for a Spotify track ID.

        Returns:
            Tidal URL string if cached, None otherwise
        """
        if not spotify_id:
            return None
        try:
            with sqlite3.connect(self.catalog_path) as conn:
                cursor = conn.execute(
                    'SELECT tidal_url FROM link_cache WHERE spotify_id = ?',
                    (spotify_id,)
                )
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    def set_tidal_url(self, spotify_id: str, tidal_url: str) -> bool:
        """Cache a Tidal URL for a Spotify track ID.

        Returns:
            True if stored, False otherwise
        """
        if not spotify_id or not tidal_url:
            return False
        try:
            with sqlite3.connect(self.catalog_path) as conn:
                conn.execute(
                    'INSERT OR REPLACE INTO link_cache (spotify_id, tidal_url, cached_at) VALUES (?, ?, ?)',
                    (spotify_id, tidal_url, datetime.now().isoformat())
                )
                conn.commit()
                return True
        except Exception:
            return False

    def search_tracks(self, query: str, limit: int = 50) -> List[CatalogTrack]:
        """Search tracks by title or artist"""
        with sqlite3.connect(self.catalog_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM tracks 
                WHERE title LIKE ? OR artist LIKE ?
                ORDER BY artist, title
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", limit))
            
            return [CatalogTrack(**dict(row)) for row in cursor.fetchall()]
    
    def get_tracks_by_playlist(self, playlist_name: str) -> List[CatalogTrack]:
        """Get all tracks from a specific playlist"""
        with sqlite3.connect(self.catalog_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM tracks 
                WHERE playlist_source = ?
                ORDER BY artist, title
            """, (playlist_name,))
            
            return [CatalogTrack(**dict(row)) for row in cursor.fetchall()]
    
    def get_missing_tracks(self, expected_tracks: List[Tuple[str, str]],
                          playlist_name: Optional[str] = None) -> List[Tuple[str, str]]:
        """
        Check which tracks from expected list are missing from catalog.

        Uses batch query to check all tracks in a single database operation,
        avoiding N+1 query performance issues.

        Args:
            expected_tracks: List of (title, artist) tuples
            playlist_name: Optional playlist filter (not currently used)

        Returns:
            List of missing (title, artist) tuples
        """
        if not expected_tracks:
            return []

        # Generate all track IDs for batch lookup
        track_ids = [self.generate_track_id(title, artist) for title, artist in expected_tracks]

        # Single batch query for all tracks
        with sqlite3.connect(self.catalog_path) as conn:
            placeholders = ','.join(['?' for _ in track_ids])
            cursor = conn.execute(
                f"SELECT id, file_path FROM tracks WHERE id IN ({placeholders})",
                track_ids
            )
            existing_tracks = {row[0]: row[1] for row in cursor.fetchall()}

        # Check which tracks are missing or have missing files
        missing = []
        tracks_to_remove = []

        for (title, artist), track_id in zip(expected_tracks, track_ids):
            if track_id in existing_tracks:
                file_path = existing_tracks[track_id]
                # Found in catalog, check if file still exists
                if not Path(file_path).exists():
                    # File is missing, mark for removal
                    tracks_to_remove.append(file_path)
                    missing.append((title, artist))
            else:
                # Not in catalog at all
                missing.append((title, artist))

        # Batch remove tracks with missing files
        if tracks_to_remove:
            self._batch_remove_tracks_by_paths(tracks_to_remove)

        return missing

    def _batch_remove_tracks_by_paths(self, file_paths: List[str]) -> int:
        """
        Remove multiple tracks from catalog by file paths in a single operation.

        Args:
            file_paths: List of file paths to remove

        Returns:
            Number of tracks removed
        """
        if not file_paths:
            return 0

        try:
            with sqlite3.connect(self.catalog_path) as conn:
                placeholders = ','.join(['?' for _ in file_paths])
                cursor = conn.execute(
                    f"DELETE FROM tracks WHERE file_path IN ({placeholders})",
                    file_paths
                )
                conn.commit()
                return cursor.rowcount
        except Exception:
            return 0
    
    def remove_track_by_path(self, file_path: str) -> bool:
        """Remove a track from catalog by file path"""
        try:
            with sqlite3.connect(self.catalog_path) as conn:
                cursor = conn.execute("DELETE FROM tracks WHERE file_path = ?", (file_path,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception:
            return False
    
    def get_stats(self) -> CatalogStats:
        """Get comprehensive catalog statistics"""
        with sqlite3.connect(self.catalog_path) as conn:
            # Basic counts
            total_tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
            total_size_bytes = conn.execute("SELECT SUM(file_size) FROM tracks").fetchone()[0] or 0
            
            # Unique counts
            unique_artists = conn.execute("SELECT COUNT(DISTINCT artist) FROM tracks").fetchone()[0]
            unique_albums = conn.execute("SELECT COUNT(DISTINCT album) FROM tracks WHERE album IS NOT NULL").fetchone()[0]
            
            # Playlists
            playlists_result = conn.execute("SELECT DISTINCT playlist_source FROM tracks WHERE playlist_source IS NOT NULL").fetchall()
            playlists = [row[0] for row in playlists_result]
            
            # File formats
            formats_result = conn.execute("SELECT file_format, COUNT(*) FROM tracks WHERE file_format IS NOT NULL GROUP BY file_format").fetchall()
            file_formats = {row[0]: row[1] for row in formats_result}
            
            # Newest and oldest tracks
            newest_result = conn.execute("SELECT title, artist FROM tracks ORDER BY date_added DESC LIMIT 1").fetchone()
            newest_track = f"{newest_result[0]} - {newest_result[1]}" if newest_result else None
            
            oldest_result = conn.execute("SELECT title, artist FROM tracks ORDER BY date_added ASC LIMIT 1").fetchone()
            oldest_track = f"{oldest_result[0]} - {oldest_result[1]}" if oldest_result else None
            
            return CatalogStats(
                total_tracks=total_tracks,
                total_size_bytes=total_size_bytes,
                unique_artists=unique_artists,
                unique_albums=unique_albums,
                playlists=playlists,
                file_formats=file_formats,
                newest_track=newest_track,
                oldest_track=oldest_track
            )
    
    def cleanup_missing_files(self) -> int:
        """Remove catalog entries for files that no longer exist"""
        removed_count = 0
        
        with sqlite3.connect(self.catalog_path) as conn:
            cursor = conn.execute("SELECT id, file_path FROM tracks")
            tracks_to_remove = []
            
            for row in cursor.fetchall():
                track_id, file_path = row
                if not Path(file_path).exists():
                    tracks_to_remove.append(track_id)
            
            # Remove missing tracks
            for track_id in tracks_to_remove:
                conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
                removed_count += 1
            
            conn.commit()
        
        return removed_count
    
    def export_catalog(self, output_path: Optional[Path] = None) -> str:
        """Export catalog to JSON file"""
        if output_path is None:
            output_path = Path(f"catalog_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        
        with sqlite3.connect(self.catalog_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM tracks ORDER BY artist, title")
            tracks = [dict(row) for row in cursor.fetchall()]
        
        export_data = {
            'export_date': datetime.now().isoformat(),
            'total_tracks': len(tracks),
            'tracks': tracks
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        return str(output_path)


def create_catalog(catalog_path: Optional[str] = None) -> LibraryCatalog:
    """Factory function to create LibraryCatalog instance"""
    return LibraryCatalog(catalog_path)


if __name__ == "__main__":
    # Example usage
    catalog = create_catalog("./test_catalog.db")
    
    # Example: Add a track
    test_file = Path("./test_music/Artist - Song.flac")
    if test_file.exists():
        catalog.add_track(test_file, "Test Playlist")
    
    # Example: Get stats
    stats = catalog.get_stats()
    print(f"Catalog Stats: {stats}")