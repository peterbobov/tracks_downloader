#!/usr/bin/env python3
"""
Link Converter Module

Converts Spotify tracks to Tidal URLs using:
1. ISRC lookup via Tidal API (exact match, preferred)
2. Artist + title search via Tidal API (fallback)

Caches results in the catalog database.
"""

import time
from typing import Optional, Dict, List

import requests

from .spotify_api import Track


TIDAL_API_URL = "https://listen.tidal.com/v1"
TIDAL_CLIENT_TOKEN = "CzET4vdadNUFQ5JU"

# Be respectful — 0.5s between requests
REQUEST_INTERVAL = 0.5


class LinkConverter:
    """Converts Spotify tracks to Tidal URLs via Tidal API with caching."""

    def __init__(self, catalog=None):
        self.catalog = catalog
        self._last_request_time = 0.0
        self._session = requests.Session()
        self._session.headers.update({
            "x-tidal-token": TIDAL_CLIENT_TOKEN,
            "User-Agent": "SpotifyDownloader/3.0",
        })

    def _rate_limit(self):
        """Brief pause between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _lookup_by_isrc(self, isrc: str) -> Optional[str]:
        """Look up Tidal track by ISRC code (exact match)."""
        if not isrc:
            return None

        self._rate_limit()
        try:
            resp = self._session.get(
                f"{TIDAL_API_URL}/tracks",
                params={"isrc": isrc, "countryCode": "US"},
                timeout=10,
            )
            if resp.status_code != 200:
                return None

            items = resp.json().get("items", [])
            if items:
                return f"https://tidal.com/browse/track/{items[0]['id']}"
            return None
        except Exception:
            return None

    def _search_by_name(self, artist: str, title: str) -> Optional[str]:
        """Search Tidal by artist + title (fallback)."""
        self._rate_limit()
        try:
            query = f"{artist} {title}"
            resp = self._session.get(
                f"{TIDAL_API_URL}/search",
                params={
                    "query": query,
                    "type": "TRACKS",
                    "limit": 1,
                    "countryCode": "US",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                return None

            items = resp.json().get("tracks", {}).get("items", [])
            if items:
                return f"https://tidal.com/browse/track/{items[0]['id']}"
            return None
        except Exception:
            return None

    def _fetch_tidal_url(self, track: Track) -> Optional[str]:
        """
        Get Tidal URL for a track. Tries ISRC first, then name search.

        Returns:
            Tidal URL if found, None if not on Tidal
        """
        # Try ISRC first (exact match)
        if track.isrc:
            url = self._lookup_by_isrc(track.isrc)
            if url:
                return url

        # Fallback to name search
        return self._search_by_name(track.artist_string, track.name)

    def get_tidal_url(self, track: Track) -> Optional[str]:
        """Get Tidal URL for a track, checking cache first."""
        # Check cache
        if self.catalog:
            cached = self.catalog.get_tidal_url(track.id)
            if cached:
                return cached

        # Fetch from Tidal API
        tidal_url = self._fetch_tidal_url(track)

        # Cache result
        if self.catalog and tidal_url:
            self.catalog.set_tidal_url(track.id, tidal_url)

        return tidal_url

    def convert_tracks(self, tracks: List[Track], debug: bool = False) -> Dict[str, Optional[str]]:
        """
        Convert a list of tracks to Tidal URLs with progress display.

        Returns:
            Dict mapping spotify track ID -> tidal URL (or None if not found)
        """
        results = {}
        cached = 0
        fetched = 0
        not_found = 0

        # First pass: check cache
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
            print(f"  {cached} from cache, {len(uncached_tracks)} to look up...")

        if uncached_tracks:
            print(f"  Looking up {len(uncached_tracks)} tracks via Tidal API...")

        # Second pass: fetch from Tidal API
        for i, track in enumerate(uncached_tracks, 1):
            track_name = f"{track.artist_string} - {track.name}"
            if debug:
                print(f"  [{i}/{len(uncached_tracks)}] {track_name}", end="")

            tidal_url = self._fetch_tidal_url(track)

            if tidal_url:
                results[track.id] = tidal_url
                fetched += 1
                if self.catalog:
                    self.catalog.set_tidal_url(track.id, tidal_url)
                if debug:
                    print(" -> OK")
            else:
                results[track.id] = None
                not_found += 1
                if debug:
                    print(" -> not found")

            # Progress every 10 tracks (non-debug)
            if not debug and i % 10 == 0:
                print(f"  Progress: {i}/{len(uncached_tracks)}...")

        print(f"  Tidal links: {cached} cached, {fetched} found, {not_found} not on Tidal")
        return results
