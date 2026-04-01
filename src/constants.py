#!/usr/bin/env python3
"""
Constants Module

Centralized configuration constants for the spotify_downloader project.
Removes magic numbers and strings scattered throughout the codebase.
"""

from typing import List, Set


class TelegramConstants:
    """Constants related to Telegram client operations"""

    # Response timeout for waiting on bot responses (5 minutes for large files)
    DEFAULT_RESPONSE_TIMEOUT: int = 300

    # Confidence threshold for smart track matching (percentage)
    CONFIDENCE_THRESHOLD: float = 70.0

    # Maximum pending requests before cleanup is triggered
    MAX_PENDING_REQUESTS: int = 50

    # Number of recent requests to keep after cleanup
    KEEP_RECENT_REQUESTS: int = 30

    # Default delay between requests to avoid rate limiting (seconds)
    DEFAULT_DELAY_BETWEEN_REQUESTS: float = 3.0

    # Maximum retries for failed requests
    DEFAULT_MAX_RETRIES: int = 3

    # Multiplier for flood wait time
    FLOOD_WAIT_MULTIPLIER: float = 1.5


class CatalogConstants:
    """Constants related to catalog operations"""

    # File size threshold for hash comparison (50 MB)
    HASH_COMPARISON_SIZE_THRESHOLD: int = 50 * 1024 * 1024

    # Default folder names to ignore when parsing metadata
    IGNORED_FOLDER_NAMES: Set[str] = {'downloads', 'music', '.', '..', 'temp'}

    # Similarity threshold for fuzzy matching (percentage)
    FUZZY_MATCH_THRESHOLD: float = 90.0


class FileConstants:
    """Constants related to file operations"""

    # Maximum filename length (characters)
    MAX_FILENAME_LENGTH: int = 200

    # Maximum attempts for filename collision handling
    MAX_COLLISION_ATTEMPTS: int = 1000

    # Minimum valid file size (1 KB)
    MIN_VALID_FILE_SIZE: int = 1024

    # Supported audio file extensions
    SUPPORTED_EXTENSIONS: List[str] = ['.flac', '.mp3', '.wav', '.m4a', '.ogg']

    # Invalid characters for filenames
    INVALID_FILENAME_CHARS: str = '<>:"/\\|?*'


class BatchConstants:
    """Constants related to batch processing"""

    # Default batch size for processing tracks
    DEFAULT_BATCH_SIZE: int = 3

    # Default batch timeout (seconds) - 5 minutes per batch
    # This is the time to wait before moving to next batch, not a hard failure
    DEFAULT_BATCH_TIMEOUT: int = 300

    # Maximum batch timeout (seconds) - 10 minutes
    MAX_BATCH_TIMEOUT: int = 600

    # Minimum batch timeout per track (seconds)
    # e.g., batch of 5 tracks = 5 * 60 = 300 seconds minimum
    MIN_TIMEOUT_PER_TRACK: int = 60

    # Interval for checking batch completion (seconds)
    BATCH_CHECK_INTERVAL: int = 5

    # Interval for checking individual track completion (seconds)
    TRACK_CHECK_INTERVAL: int = 2


class DisplayConstants:
    """Constants related to display and UI"""

    # Width for clearing console lines
    CLEAR_LINE_WIDTH: int = 80

    # Maximum tracks to show in preview
    MAX_PREVIEW_TRACKS: int = 20

    # Maximum missing tracks to show in list
    MAX_MISSING_TRACKS_DISPLAY: int = 10


class MatchingWeights:
    """Weights for track matching algorithm"""

    # Weight for filename matching
    FILENAME_WEIGHT: float = 0.6

    # Weight for title-only filename matching
    FILENAME_TITLE_WEIGHT: float = 0.3

    # Weight for performer/artist matching
    PERFORMER_WEIGHT: float = 0.4

    # Weight for title matching
    TITLE_WEIGHT: float = 0.5


# Environment variable names
class EnvVars:
    """Environment variable names"""

    SPOTIFY_CLIENT_ID = 'SPOTIFY_CLIENT_ID'
    SPOTIFY_CLIENT_SECRET = 'SPOTIFY_CLIENT_SECRET'
    TELEGRAM_API_ID = 'TELEGRAM_API_ID'
    TELEGRAM_API_HASH = 'TELEGRAM_API_HASH'
    TELEGRAM_PHONE_NUMBER = 'TELEGRAM_PHONE_NUMBER'
    EXTERNAL_BOT_USERNAME = 'EXTERNAL_BOT_USERNAME'
    DOWNLOAD_FOLDER = 'DOWNLOAD_FOLDER'
    MUSIC_LIBRARY_PATH = 'MUSIC_LIBRARY_PATH'
    DELAY_BETWEEN_REQUESTS = 'DELAY_BETWEEN_REQUESTS'
    MAX_RETRIES = 'MAX_RETRIES'
    RESPONSE_TIMEOUT = 'RESPONSE_TIMEOUT'


# Default values for optional configuration
class Defaults:
    """Default values for configuration"""

    DOWNLOAD_FOLDER = './downloads'
    MUSIC_LIBRARY_PATH = './music'
    DELAY_BETWEEN_REQUESTS = 3.0
    MAX_RETRIES = 3
    RESPONSE_TIMEOUT = 600
    SESSION_DIR = './sessions'
    PROGRESS_FILE = 'progress.json'
