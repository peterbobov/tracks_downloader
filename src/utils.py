#!/usr/bin/env python3
"""
Shared Utilities Module

Common utilities used across the spotify_downloader project including:
- Console output helpers
- String normalization and matching
- Text formatting utilities
"""

import re
from typing import Optional


def clear_print(message: str, width: int = 80) -> None:
    """
    Print message after clearing any existing progress line.

    Useful for displaying status messages without overlapping
    with download progress indicators.

    Args:
        message: The message to print
        width: Width to clear (default: 80 characters)
    """
    print(f"\r{' ' * width}\r{message}")


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison purposes.

    Handles common variations in track naming:
    - Converts to lowercase
    - Normalizes "feat." variations
    - Normalizes "&" to "and"
    - Strips extra whitespace

    Args:
        text: The text to normalize

    Returns:
        Normalized text string
    """
    result = text.lower()

    # Normalize featuring patterns
    result = re.sub(r'\bfeat\.?\b', 'featuring', result)
    result = re.sub(r'\bft\.?\b', 'featuring', result)

    # Normalize ampersand
    result = result.replace('&', 'and')

    # Remove extra whitespace
    result = re.sub(r'\s+', ' ', result)

    return result.strip()


def strip_bot_artifacts(filename: str) -> str:
    """
    Strip bot-added artifacts from filenames for better matching.

    Bot filenames follow patterns like:
    - 5_Love_Nation_Everything_4_U_Remix_Don_Carlos_Edit_2N3PYW.flac
    - 1-Tiga-Sunglasses-at-Night--Raxon-Remix--9R64DO.flac
    - 20-Aleksi-Per-l--UK74R1512110--Mixed--2DMTIB.flac

    Strips: leading track number + separator, trailing hash code.
    """
    # Remove file extension
    result = re.sub(r'\.(flac|mp3|wav|m4a|ogg)$', '', filename, flags=re.IGNORECASE)

    # Remove leading track number + separator (e.g., "5_", "1-", "20-")
    result = re.sub(r'^\d{1,3}[-_]', '', result)

    # Remove trailing hash code (5-6 alphanumeric chars after last separator)
    # Matches patterns like _2N3PYW, --9R64DO, _QOOD21, -6SZ50C
    result = re.sub(r'[-_]{1,2}[A-Z0-9]{5,7}$', '', result)

    # Replace separators with spaces for matching
    result = result.replace('_', ' ').replace('-', ' ')

    # Collapse multiple spaces
    result = re.sub(r'\s+', ' ', result).strip()

    return result


def normalize_filename(filename: str) -> str:
    """
    Normalize filename for duplicate detection and comparison.

    Removes common noise patterns that don't affect track identity:
    - Content in parentheses (e.g., "(Radio Edit)")
    - Content in brackets (e.g., "[Remastered]")
    - "copy" indicators
    - Extra whitespace

    Args:
        filename: The filename to normalize (without extension)

    Returns:
        Normalized filename string
    """
    result = filename.lower()

    # Remove common patterns
    patterns_to_remove = [
        r'\s*\([^)]*\)\s*',  # Remove parentheses content
        r'\s*\[[^\]]*\]\s*',  # Remove brackets content
        r'\s*-\s*copy\s*',    # Remove "copy" indicators
        r'\s+',               # Normalize whitespace
    ]

    for pattern in patterns_to_remove:
        result = re.sub(pattern, ' ', result)

    return result.strip()


def similarity_ratio(str1: str, str2: str) -> float:
    """
    Calculate similarity ratio between two strings using Jaccard similarity.

    Args:
        str1: First string to compare
        str2: Second string to compare

    Returns:
        Similarity ratio between 0.0 (no similarity) and 1.0 (identical)
    """
    if str1 == str2:
        return 1.0

    # Calculate Jaccard similarity on words
    set1 = set(str1.lower().split())
    set2 = set(str2.lower().split())

    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))

    return intersection / union if union > 0 else 0.0


def format_duration(duration_ms: Optional[int]) -> str:
    """
    Format duration in milliseconds to human-readable MM:SS format.

    Args:
        duration_ms: Duration in milliseconds

    Returns:
        Formatted duration string (e.g., "3:45") or "Unknown" if None
    """
    if duration_ms is None:
        return "Unknown"

    total_seconds = duration_ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    return f"{minutes}:{seconds:02d}"


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in bytes to human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string (e.g., "45.2 MB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate string to maximum length with optional suffix.

    Args:
        text: The text to truncate
        max_length: Maximum allowed length
        suffix: Suffix to append when truncated (default: "...")

    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


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
