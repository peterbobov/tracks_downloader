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
