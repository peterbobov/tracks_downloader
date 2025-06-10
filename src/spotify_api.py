#!/usr/bin/env python3
"""
Spotify API Module

Handles all Spotify Web API interactions including:
- Playlist extraction
- Album extraction  
- Track information retrieval
- Search functionality
- Caching and rate limiting
"""

import re
import time
import json
import pickle
from pathlib import Path
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
from datetime import datetime, timedelta

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from spotipy.exceptions import SpotifyException


@dataclass
class Track:
    """Data class representing a Spotify track"""
    id: str
    name: str
    artists: List[str]
    album: str
    url: str
    duration_ms: int
    popularity: int = 0
    explicit: bool = False
    preview_url: Optional[str] = None
    release_date: str = ""
    isrc: Optional[str] = None

    @property
    def artist_string(self) -> str:
        """Return artists as comma-separated string"""
        return ", ".join(self.artists)

    @property
    def duration_formatted(self) -> str:
        """Return duration in MM:SS format"""
        minutes = self.duration_ms // 60000
        seconds = (self.duration_ms % 60000) // 1000
        return f"{minutes}:{seconds:02d}"

    @property
    def filename_safe_name(self) -> str:
        """Return filename-safe version of track name"""
        return SpotifyExtractor.sanitize_filename(f"{self.artist_string} - {self.name}")


class SpotifyCache:
    """Simple file-based cache for Spotify API responses"""
    
    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_ttl = timedelta(hours=24)  # Cache for 24 hours
    
    def _get_cache_path(self, key: str) -> Path:
        """Get cache file path for given key"""
        return self.cache_dir / f"{key}.pkl"
    
    def get(self, key: str) -> Optional[Dict]:
        """Get cached data if valid"""
        cache_file = self._get_cache_path(key)
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'rb') as f:
                data = pickle.load(f)
            
            # Check if cache is still valid
            if datetime.now() - data['timestamp'] < self.cache_ttl:
                return data['content']
            else:
                # Remove expired cache
                cache_file.unlink()
                return None
                
        except (pickle.PickleError, KeyError, OSError):
            # Remove corrupted cache
            if cache_file.exists():
                cache_file.unlink()
            return None
    
    def set(self, key: str, content: Dict):
        """Cache data with timestamp"""
        cache_file = self._get_cache_path(key)
        
        data = {
            'timestamp': datetime.now(),
            'content': content
        }
        
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(data, f)
        except (pickle.PickleError, OSError):
            pass  # Fail silently if caching fails


class SpotifyExtractor:
    """Main class for Spotify API interactions"""
    
    def __init__(self, client_id: str, client_secret: str, enable_cache: bool = True):
        self.client_id = client_id
        self.client_secret = client_secret
        self.enable_cache = enable_cache
        
        # Initialize cache
        self.cache = SpotifyCache() if enable_cache else None
        
        # Initialize Spotify client with app-only auth (for public content)
        self._init_client()
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests
    
    def _init_client(self):
        """Initialize Spotify client with Client Credentials flow"""
        auth_manager = SpotifyClientCredentials(
            client_id=self.client_id,
            client_secret=self.client_secret
        )
        self.spotify = spotipy.Spotify(auth_manager=auth_manager)
    
    def _rate_limit(self):
        """Ensure we don't exceed rate limits"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def _make_request(self, func, *args, **kwargs):
        """Make rate-limited request with retry logic"""
        self._rate_limit()
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except SpotifyException as e:
                if e.http_status == 429:  # Rate limited
                    retry_after = int(e.headers.get('Retry-After', 60))
                    print(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                elif e.http_status in [500, 502, 503, 504]:  # Server errors
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        print(f"Server error. Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                        continue
                raise
        
        raise Exception(f"Max retries exceeded for Spotify request")
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename for safe file system use"""
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '')
        
        # Replace multiple spaces with single space
        filename = re.sub(r'\s+', ' ', filename)
        
        # Limit length
        if len(filename) > 200:
            filename = filename[:200]
        
        return filename.strip()
    
    def extract_spotify_id(self, url: str, content_type: str) -> str:
        """Extract Spotify ID from URL"""
        patterns = {
            'playlist': r'playlist/([a-zA-Z0-9]+)',
            'album': r'album/([a-zA-Z0-9]+)',
            'track': r'track/([a-zA-Z0-9]+)',
            'artist': r'artist/([a-zA-Z0-9]+)'
        }
        
        pattern = patterns.get(content_type)
        if not pattern:
            raise ValueError(f"Unsupported content type: {content_type}")
        
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        
        # If no match found, assume the URL is already just the ID
        return url
    
    def _track_from_api_data(self, track_data: Dict) -> Track:
        """Convert Spotify API track data to Track object"""
        return Track(
            id=track_data['id'],
            name=track_data['name'],
            artists=[artist['name'] for artist in track_data['artists']],
            album=track_data['album']['name'],
            url=track_data['external_urls']['spotify'],
            duration_ms=track_data['duration_ms'],
            popularity=track_data.get('popularity', 0),
            explicit=track_data.get('explicit', False),
            preview_url=track_data.get('preview_url'),
            release_date=track_data['album'].get('release_date', ''),
            isrc=track_data.get('external_ids', {}).get('isrc')
        )
    
    def get_playlist_tracks(self, playlist_url: str) -> List[Track]:
        """Get all tracks from a Spotify playlist"""
        playlist_id = self.extract_spotify_id(playlist_url, 'playlist')
        
        # Check cache first
        cache_key = f"playlist_{playlist_id}"
        if self.cache:
            cached_data = self.cache.get(cache_key)
            if cached_data:
                return [Track(**track_data) for track_data in cached_data]
        
        tracks = []
        offset = 0
        limit = 100
        
        print(f"Fetching playlist tracks from Spotify API...")
        
        while True:
            try:
                results = self._make_request(
                    self.spotify.playlist_tracks,
                    playlist_id,
                    offset=offset,
                    limit=limit
                )
                
                for item in results['items']:
                    if item['track'] and item['track']['id']:
                        track = self._track_from_api_data(item['track'])
                        tracks.append(track)
                
                if results['next'] is None:
                    break
                
                offset += limit
                
            except Exception as e:
                print(f"Error fetching playlist tracks: {e}")
                break
        
        # Cache the results
        if self.cache and tracks:
            track_data = [track.__dict__ for track in tracks]
            self.cache.set(cache_key, track_data)
        
        print(f"Found {len(tracks)} tracks in playlist")
        return tracks
    
    def get_album_tracks(self, album_url: str) -> List[Track]:
        """Get all tracks from a Spotify album"""
        album_id = self.extract_spotify_id(album_url, 'album')
        
        # Check cache first
        cache_key = f"album_{album_id}"
        if self.cache:
            cached_data = self.cache.get(cache_key)
            if cached_data:
                return [Track(**track_data) for track_data in cached_data]
        
        tracks = []
        
        try:
            # Get album info
            album_info = self._make_request(self.spotify.album, album_id)
            
            # Get all tracks from album
            results = self._make_request(self.spotify.album_tracks, album_id)
            
            for track_data in results['items']:
                # Album tracks don't include full track info, so we need to get it
                full_track = self._make_request(self.spotify.track, track_data['id'])
                track = self._track_from_api_data(full_track)
                tracks.append(track)
            
            # Handle pagination if needed
            while results['next']:
                results = self._make_request(self.spotify.next, results)
                for track_data in results['items']:
                    full_track = self._make_request(self.spotify.track, track_data['id'])
                    track = self._track_from_api_data(full_track)
                    tracks.append(track)
        
        except Exception as e:
            print(f"Error fetching album tracks: {e}")
            return []
        
        # Cache the results
        if self.cache and tracks:
            track_data = [track.__dict__ for track in tracks]
            self.cache.set(cache_key, track_data)
        
        print(f"Found {len(tracks)} tracks in album")
        return tracks
    
    def get_track_info(self, track_url: str) -> Optional[Track]:
        """Get information for a single track"""
        track_id = self.extract_spotify_id(track_url, 'track')
        
        # Check cache first
        cache_key = f"track_{track_id}"
        if self.cache:
            cached_data = self.cache.get(cache_key)
            if cached_data:
                return Track(**cached_data[0]) if cached_data else None
        
        try:
            track_data = self._make_request(self.spotify.track, track_id)
            track = self._track_from_api_data(track_data)
            
            # Cache the result
            if self.cache:
                self.cache.set(cache_key, [track.__dict__])
            
            return track
            
        except Exception as e:
            print(f"Error fetching track info: {e}")
            return None
    
    def search_tracks(self, query: str, limit: int = 20) -> List[Track]:
        """Search for tracks by query"""
        try:
            results = self._make_request(
                self.spotify.search,
                query,
                type='track',
                limit=limit
            )
            
            tracks = []
            for track_data in results['tracks']['items']:
                track = self._track_from_api_data(track_data)
                tracks.append(track)
            
            return tracks
            
        except Exception as e:
            print(f"Error searching tracks: {e}")
            return []
    
    def get_playlist_info(self, playlist_url: str) -> Dict:
        """Get playlist metadata"""
        playlist_id = self.extract_spotify_id(playlist_url, 'playlist')
        
        try:
            playlist_info = self._make_request(self.spotify.playlist, playlist_id)
            return {
                'id': playlist_info['id'],
                'name': playlist_info['name'],
                'description': playlist_info.get('description', ''),
                'owner': playlist_info['owner']['display_name'],
                'total_tracks': playlist_info['tracks']['total'],
                'public': playlist_info['public'],
                'url': playlist_info['external_urls']['spotify']
            }
        except Exception as e:
            print(f"Error fetching playlist info: {e}")
            return {}
    
    def detect_content_type(self, url: str) -> str:
        """Detect content type from Spotify URL"""
        if 'playlist' in url:
            return 'playlist'
        elif 'album' in url:
            return 'album'
        elif 'track' in url:
            return 'track'
        elif 'artist' in url:
            return 'artist'
        else:
            raise ValueError(f"Cannot detect content type from URL: {url}")
    
    def extract_tracks(self, url: str) -> List[Track]:
        """Universal method to extract tracks from any Spotify URL"""
        content_type = self.detect_content_type(url)
        
        if content_type == 'playlist':
            return self.get_playlist_tracks(url)
        elif content_type == 'album':
            return self.get_album_tracks(url)
        elif content_type == 'track':
            track = self.get_track_info(url)
            return [track] if track else []
        else:
            raise ValueError(f"Unsupported content type for track extraction: {content_type}")


def create_spotify_extractor(client_id: str, client_secret: str) -> SpotifyExtractor:
    """Factory function to create SpotifyExtractor instance"""
    return SpotifyExtractor(client_id, client_secret)


if __name__ == "__main__":
    # Example usage
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    client_id = os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your .env file")
        exit(1)
    
    extractor = SpotifyExtractor(client_id, client_secret)
    
    # Example: Get tracks from a playlist
    playlist_url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"  # Example playlist
    tracks = extractor.get_playlist_tracks(playlist_url)
    
    print(f"Found {len(tracks)} tracks:")
    for i, track in enumerate(tracks[:5], 1):  # Show first 5
        print(f"{i}. {track.artist_string} - {track.name}")