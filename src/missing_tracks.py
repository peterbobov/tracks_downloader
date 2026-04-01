#!/usr/bin/env python3
"""
Missing Tracks Analysis Module

Provides unified logic for detecting and analyzing missing tracks from playlists.
Used by both --check-missing and --download-missing commands to avoid code duplication.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from colorama import Fore, Style

from .spotify_api import Track
from .catalog import LibraryCatalog

try:
    from fuzzywuzzy import fuzz
    FUZZYWUZZY_AVAILABLE = True
except ImportError:
    FUZZYWUZZY_AVAILABLE = False


@dataclass
class TrackMatch:
    """Represents a matched track in the library"""
    position: int
    track: Track
    expected_filename: str
    found_filename: Optional[str]
    method: str  # 'catalog' or 'folder'
    location: Optional[str]
    score: float


@dataclass
class MissingTrack:
    """Represents a track that's missing from the library"""
    position: int
    track: Track
    expected_filename: str
    best_match: Optional[str]
    best_location: Optional[str]
    score: float


@dataclass
class AnalysisResult:
    """Result of analyzing missing tracks"""
    total_tracks: int
    found_tracks: List[TrackMatch]
    missing_tracks: List[MissingTrack]
    found_in_catalog: int
    found_in_folder: int
    playlist_name: Optional[str]

    @property
    def found_count(self) -> int:
        return len(self.found_tracks)

    @property
    def missing_count(self) -> int:
        return len(self.missing_tracks)

    @property
    def found_percentage(self) -> float:
        if self.total_tracks == 0:
            return 0.0
        return (self.found_count / self.total_tracks) * 100

    @property
    def missing_percentage(self) -> float:
        if self.total_tracks == 0:
            return 0.0
        return (self.missing_count / self.total_tracks) * 100


class MissingTracksAnalyzer:
    """Analyzes which tracks from a playlist are missing from the library"""

    # Similarity threshold for fuzzy matching
    SIMILARITY_THRESHOLD = 90

    def __init__(self, library_path: Path, catalog: LibraryCatalog,
                 sanitize_func=None):
        """
        Initialize the analyzer.

        Args:
            library_path: Path to the music library
            catalog: LibraryCatalog instance for database lookups
            sanitize_func: Function to sanitize filenames (optional)
        """
        self.library_path = library_path
        self.catalog = catalog
        self.sanitize_func = sanitize_func or self._default_sanitize

    @staticmethod
    def _default_sanitize(name: str, max_length: int = 100) -> str:
        """Default filename sanitization"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '')
        return name[:max_length].strip()

    def analyze(self, tracks: List[Track], playlist_name: Optional[str] = None) -> AnalysisResult:
        """
        Analyze which tracks are missing from the library.

        Args:
            tracks: List of tracks to check
            playlist_name: Optional playlist name for folder-specific search

        Returns:
            AnalysisResult with found and missing tracks
        """
        if not FUZZYWUZZY_AVAILABLE:
            raise ImportError("fuzzywuzzy library required for track analysis")

        found_tracks: List[TrackMatch] = []
        missing_tracks: List[MissingTrack] = []
        found_in_catalog = 0
        found_in_folder = 0

        # Prepare playlist folder path
        playlist_folder = None
        if playlist_name:
            playlist_folder = self.library_path / self.sanitize_func(playlist_name, 100)

        for i, track in enumerate(tracks, 1):
            expected_filename = f"{track.artist_string} - {track.name}"
            result = self._check_track(
                track, expected_filename, i, playlist_folder
            )

            if result['found']:
                found_tracks.append(TrackMatch(
                    position=i,
                    track=track,
                    expected_filename=expected_filename,
                    found_filename=result.get('found_filename'),
                    method=result['method'],
                    location=result.get('location'),
                    score=result.get('score', 100)
                ))
                if result['method'] == 'catalog':
                    found_in_catalog += 1
                else:
                    found_in_folder += 1
            else:
                missing_tracks.append(MissingTrack(
                    position=i,
                    track=track,
                    expected_filename=expected_filename,
                    best_match=result.get('best_match'),
                    best_location=result.get('best_location'),
                    score=result.get('score', 0)
                ))

        return AnalysisResult(
            total_tracks=len(tracks),
            found_tracks=found_tracks,
            missing_tracks=missing_tracks,
            found_in_catalog=found_in_catalog,
            found_in_folder=found_in_folder,
            playlist_name=playlist_name
        )

    def _check_track(self, track: Track, expected_filename: str,
                     position: int, playlist_folder: Optional[Path]) -> Dict[str, Any]:
        """
        Check if a single track exists in the library.

        Returns dict with keys: found, method, location, score, found_filename, best_match
        """
        # Check catalog database first
        catalog_track = self.catalog.find_track(track.name, track.artist_string)
        if catalog_track and Path(catalog_track.file_path).exists():
            return {
                'found': True,
                'method': 'catalog',
                'location': catalog_track.file_path,
                'found_filename': Path(catalog_track.file_path).name,
                'score': 100
            }

        # If not in catalog, check folder scanning with fuzzy matching
        search_paths = [self.library_path]
        if playlist_folder and playlist_folder.exists():
            search_paths.insert(0, playlist_folder)  # Check playlist folder first

        best_score = 0
        best_match = None
        best_location = None

        for search_path in search_paths:
            # Get all audio files in this path
            for ext in ['.flac', '.mp3', '.wav', '.m4a', '.ogg']:
                for file_path in search_path.rglob(f"*{ext}"):
                    filename = file_path.stem  # Without extension
                    score = fuzz.ratio(expected_filename.lower(), filename.lower())

                    if score > best_score:
                        best_score = score
                        best_match = filename
                        best_location = str(file_path)

                    # If we find a very high match in playlist folder, prefer it
                    if score >= 95 and search_path == playlist_folder:
                        break

            # If we found a good match in playlist folder, don't search library
            if best_score >= self.SIMILARITY_THRESHOLD and search_path == playlist_folder:
                break

        if best_score >= self.SIMILARITY_THRESHOLD:
            return {
                'found': True,
                'method': 'folder',
                'location': best_location,
                'found_filename': best_match,
                'score': best_score
            }

        return {
            'found': False,
            'best_match': best_match,
            'best_location': best_location,
            'score': best_score
        }


def print_analysis_results(result: AnalysisResult, verbose: bool = True) -> None:
    """Print analysis results in a formatted way"""
    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}ANALYSIS RESULTS{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")

    print(f"\n  Total tracks in playlist: {result.total_tracks}")
    print(f"  Already in library: {result.found_count} ({result.found_percentage:.1f}%)")
    print(f"  Missing tracks: {result.missing_count} ({result.missing_percentage:.1f}%)")

    if result.found_in_catalog > 0:
        print(f"    - Found in catalog: {result.found_in_catalog}")
    if result.found_in_folder > 0:
        print(f"    - Found by folder scan: {result.found_in_folder}")

    if result.missing_count == 0:
        print(f"\n{Fore.GREEN}All tracks are already in your library!{Style.RESET_ALL}")
        return

    if verbose and result.missing_tracks:
        print(f"\n{Fore.YELLOW}MISSING TRACKS:{Style.RESET_ALL}")
        for i, missing in enumerate(result.missing_tracks[:10], 1):
            print(f"  {i:2d}. {Fore.WHITE}{missing.expected_filename}{Style.RESET_ALL}")
            if missing.track.album:
                duration = _format_duration(missing.track.duration_ms)
                print(f"      Album: {missing.track.album} | Duration: {duration}")

        if len(result.missing_tracks) > 10:
            print(f"      ... and {len(result.missing_tracks) - 10} more tracks")


def _format_duration(duration_ms: Optional[int]) -> str:
    """Format duration in milliseconds to MM:SS"""
    if duration_ms is None:
        return "Unknown"
    minutes = duration_ms // 60000
    seconds = (duration_ms % 60000) // 1000
    return f"{minutes}:{seconds:02d}"


def create_analyzer(library_path: Path, catalog: LibraryCatalog,
                   sanitize_func=None) -> MissingTracksAnalyzer:
    """Factory function to create MissingTracksAnalyzer"""
    return MissingTracksAnalyzer(library_path, catalog, sanitize_func)
