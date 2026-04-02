#!/usr/bin/env python3
"""
Link Converter Module

Converts Spotify URLs to Tidal URLs using the song.link (Odesli) API.
Caches results in the catalog database to avoid repeated API calls.
"""

import time
import asyncio
from typing import Optional, Dict, List, Tuple

import requests

from .spotify_api import Track


# song.link / Odesli API
ODESLI_API_URL = "https://api.song.link/v1-alpha.1/links"

# Rate limit: ~10 req/min → 6s between requests
MIN_REQUEST_INTERVAL = 6.0


class LinkConverter:
    """Converts Spotify URLs to Tidal URLs via song.link API with caching."""

    def __init__(self, catalog=None, api_key: Optional[str] = None):
        """
        Args:
            catalog: LibraryCatalog instance for caching tidal URLs
            api_key: Odesli API key for higher rate limits
        """
        self.catalog = catalog
        self.api_key = api_key
        self._last_request_time = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "SpotifyDownloader/3.0"})

    def _rate_limit(self):
        """Enforce minimum interval between API requests."""
        # Paid API key allows faster requests
        interval = 1.0 if self.api_key else MIN_REQUEST_INTERVAL
        elapsed = time.time() - self._last_request_time
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_request_time = time.time()

    def _fetch_tidal_url(self, spotify_url: str) -> Optional[str]:
        """
        Fetch Tidal URL from song.link API with retry on rate limit.

        Args:
            spotify_url: Spotify track URL

        Returns:
            Tidal URL if found, None otherwise
        """
        self._rate_limit()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                params = {"url": spotify_url}
                if self.api_key:
                    params["key"] = self.api_key

                resp = self._session.get(
                    ODESLI_API_URL,
                    params=params,
                    timeout=15,
                )

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 15))
                    print(f"  song.link rate limited, waiting {retry_after}s...")
                    time.sleep(retry_after)
                    self._last_request_time = time.time()
                    continue

                if resp.status_code != 200:
                    return None

                data = resp.json()
                tidal_data = data.get("linksByPlatform", {}).get("tidal", {})
                return tidal_data.get("url")

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                return None
            except Exception:
                return None

        return None

    def get_tidal_url(self, track: Track) -> Optional[str]:
        """
        Get Tidal URL for a track, checking cache first.

        Args:
            track: Spotify Track object

        Returns:
            Tidal URL if found, None otherwise
        """
        # Check catalog cache first
        if self.catalog:
            cached = self.catalog.get_tidal_url(track.id)
            if cached:
                return cached

        # Fetch from song.link API
        tidal_url = self._fetch_tidal_url(track.url)

        # Cache result (even None gets cached as empty string to avoid re-fetching)
        if self.catalog and tidal_url:
            self.catalog.set_tidal_url(track.id, tidal_url)

        return tidal_url

    def convert_tracks(self, tracks: List[Track], debug: bool = False) -> Dict[str, Optional[str]]:
        """
        Convert a list of tracks to Tidal URLs with progress display.

        Args:
            tracks: List of Track objects
            debug: Show debug output

        Returns:
            Dict mapping spotify track ID → tidal URL (or None)
        """
        results = {}
        cached = 0
        fetched = 0
        failed = 0

        # First pass: check cache for all tracks
        uncached_tracks = []
        for track in tracks:
            if self.catalog:
                tidal_url = self.catalog.get_tidal_url(track.id)
                if tidal_url:
                    results[track.id] = tidal_url
                    cached += 1
                    continue
            uncached_tracks.append(track)

        if cached and not uncached_tracks:
            print(f"  All {cached} Tidal links found in cache")
            return results

        if cached:
            print(f"  {cached} Tidal links from cache, {len(uncached_tracks)} to look up...")

        # Second pass: fetch uncached from API
        for i, track in enumerate(uncached_tracks, 1):
            track_name = f"{track.artist_string} - {track.name}"
            if debug:
                print(f"  [{i}/{len(uncached_tracks)}] Looking up: {track_name}")

            tidal_url = self._fetch_tidal_url(track.url)

            if tidal_url:
                results[track.id] = tidal_url
                fetched += 1
                if self.catalog:
                    self.catalog.set_tidal_url(track.id, tidal_url)
            else:
                results[track.id] = None
                failed += 1

            # Progress every 10 tracks
            if not debug and i % 10 == 0:
                print(f"  Link conversion: {i}/{len(uncached_tracks)} done...")

        print(f"  Tidal links: {cached} cached, {fetched} converted, {failed} not found (will use Spotify URL)")
        return results
