#!/usr/bin/env python3
import os
import sys
import time
import json
import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests
from telegram import Bot
from telegram.error import TelegramError
from dotenv import load_dotenv
from colorama import init, Fore, Style
from tqdm import tqdm

# Initialize colorama for colored output
init()

class SpotifyDownloader:
    def __init__(self):
        load_dotenv()
        
        # Spotify configuration
        self.spotify_client_id = os.getenv('SPOTIFY_CLIENT_ID')
        self.spotify_client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        
        # Telegram configuration
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # Download configuration
        self.download_folder = Path(os.getenv('DOWNLOAD_FOLDER', './downloads'))
        self.delay_between_requests = int(os.getenv('DELAY_BETWEEN_REQUESTS', 3))
        self.max_retries = int(os.getenv('MAX_RETRIES', 3))
        self.request_timeout = int(os.getenv('REQUEST_TIMEOUT', 30))
        
        # Progress tracking
        self.progress_file = Path('progress.json')
        self.progress_data = self.load_progress()
        
        # Initialize APIs
        self.spotify = self.init_spotify()
        self.telegram_bot = Bot(token=self.telegram_bot_token)
        
        # Create download folder
        self.download_folder.mkdir(exist_ok=True)
    
    def init_spotify(self) -> spotipy.Spotify:
        """Initialize Spotify API client"""
        auth_manager = SpotifyClientCredentials(
            client_id=self.spotify_client_id,
            client_secret=self.spotify_client_secret
        )
        return spotipy.Spotify(auth_manager=auth_manager)
    
    def load_progress(self) -> Dict:
        """Load progress from file"""
        if self.progress_file.exists():
            with open(self.progress_file, 'r') as f:
                return json.load(f)
        return {
            'processed_tracks': [],
            'failed_tracks': [],
            'downloaded_files': []
        }
    
    def save_progress(self):
        """Save progress to file"""
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress_data, f, indent=2)
    
    def extract_playlist_id(self, playlist_url: str) -> str:
        """Extract playlist ID from Spotify URL"""
        # Handle various Spotify URL formats
        patterns = [
            r'playlist/([a-zA-Z0-9]+)',
            r'playlist:([a-zA-Z0-9]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, playlist_url)
            if match:
                return match.group(1)
        
        # If no pattern matches, assume it's already an ID
        return playlist_url
    
    def get_playlist_tracks(self, playlist_id: str) -> List[Dict]:
        """Get all tracks from a Spotify playlist"""
        tracks = []
        offset = 0
        limit = 100
        
        print(f"{Fore.CYAN}Fetching playlist tracks...{Style.RESET_ALL}")
        
        while True:
            try:
                results = self.spotify.playlist_tracks(
                    playlist_id, 
                    offset=offset, 
                    limit=limit
                )
                
                for item in results['items']:
                    if item['track'] and item['track']['id']:
                        track_info = {
                            'id': item['track']['id'],
                            'name': item['track']['name'],
                            'artists': [artist['name'] for artist in item['track']['artists']],
                            'url': item['track']['external_urls']['spotify']
                        }
                        tracks.append(track_info)
                
                if results['next'] is None:
                    break
                    
                offset += limit
                
            except Exception as e:
                print(f"{Fore.RED}Error fetching playlist: {e}{Style.RESET_ALL}")
                break
        
        print(f"{Fore.GREEN}Found {len(tracks)} tracks{Style.RESET_ALL}")
        return tracks
    
    async def send_to_telegram(self, track_url: str) -> Optional[str]:
        """Send track URL to Telegram bot and wait for response"""
        try:
            # Send the Spotify URL to the bot
            await self.telegram_bot.send_message(
                chat_id=self.telegram_chat_id,
                text=track_url
            )
            
            # Wait for bot to process (this is simplified - in reality you'd need to monitor for file responses)
            await asyncio.sleep(5)
            
            # Check for new messages/files from bot
            # This would need to be implemented based on your bot's response pattern
            
            return None  # Placeholder - would return file info if available
            
        except TelegramError as e:
            print(f"{Fore.RED}Telegram error: {e}{Style.RESET_ALL}")
            return None
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe file system use"""
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '')
        
        # Limit length
        if len(filename) > 200:
            filename = filename[:200]
        
        return filename.strip()
    
    def download_file(self, url: str, filepath: Path) -> bool:
        """Download file from URL"""
        try:
            response = requests.get(url, stream=True, timeout=self.request_timeout)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(filepath, 'wb') as f:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=filepath.name) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            
            return True
            
        except Exception as e:
            print(f"{Fore.RED}Download error: {e}{Style.RESET_ALL}")
            if filepath.exists():
                filepath.unlink()
            return False
    
    async def process_track(self, track: Dict) -> bool:
        """Process a single track"""
        track_id = track['id']
        
        # Skip if already processed
        if track_id in self.progress_data['processed_tracks']:
            return True
        
        # Format track info
        artists = ', '.join(track['artists'])
        track_name = f"{artists} - {track['name']}"
        
        print(f"\n{Fore.YELLOW}Processing: {track_name}{Style.RESET_ALL}")
        
        # Send to Telegram bot
        file_info = await self.send_to_telegram(track['url'])
        
        if file_info:
            # Download the file
            filename = self.sanitize_filename(f"{track_name}.flac")
            filepath = self.download_folder / filename
            
            if self.download_file(file_info['url'], filepath):
                self.progress_data['processed_tracks'].append(track_id)
                self.progress_data['downloaded_files'].append(str(filepath))
                self.save_progress()
                print(f"{Fore.GREEN}✓ Downloaded: {filename}{Style.RESET_ALL}")
                return True
        
        # Track failed or not available
        self.progress_data['failed_tracks'].append({
            'id': track_id,
            'name': track_name,
            'reason': 'Not available or download failed'
        })
        self.save_progress()
        return False
    
    async def process_playlist(self, playlist_url: str, dry_run: bool = False):
        """Process entire playlist"""
        # Extract playlist ID
        playlist_id = self.extract_playlist_id(playlist_url)
        
        # Get playlist info
        try:
            playlist_info = self.spotify.playlist(playlist_id)
            playlist_name = playlist_info['name']
            print(f"\n{Fore.CYAN}Playlist: {playlist_name}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Owner: {playlist_info['owner']['display_name']}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Tracks: {playlist_info['tracks']['total']}{Style.RESET_ALL}\n")
        except Exception as e:
            print(f"{Fore.RED}Error accessing playlist: {e}{Style.RESET_ALL}")
            return
        
        # Get all tracks
        tracks = self.get_playlist_tracks(playlist_id)
        
        if dry_run:
            print(f"\n{Fore.YELLOW}DRY RUN MODE - No files will be downloaded{Style.RESET_ALL}")
            for i, track in enumerate(tracks, 1):
                artists = ', '.join(track['artists'])
                print(f"{i}. {artists} - {track['name']}")
            return
        
        # Process tracks
        successful = 0
        failed = 0
        
        for i, track in enumerate(tracks, 1):
            print(f"\n{Fore.CYAN}[{i}/{len(tracks)}]{Style.RESET_ALL}")
            
            try:
                success = await self.process_track(track)
                if success:
                    successful += 1
                else:
                    failed += 1
                
                # Delay between requests
                if i < len(tracks):
                    print(f"Waiting {self.delay_between_requests} seconds...")
                    await asyncio.sleep(self.delay_between_requests)
                    
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Process interrupted. Progress saved.{Style.RESET_ALL}")
                break
            except Exception as e:
                print(f"{Fore.RED}Error processing track: {e}{Style.RESET_ALL}")
                failed += 1
        
        # Final report
        print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Successful downloads: {successful}{Style.RESET_ALL}")
        print(f"{Fore.RED}Failed downloads: {failed}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Progress saved to: {self.progress_file}{Style.RESET_ALL}")
    
    def show_status(self):
        """Show current progress status"""
        print(f"\n{Fore.CYAN}Current Status:{Style.RESET_ALL}")
        print(f"Processed tracks: {len(self.progress_data['processed_tracks'])}")
        print(f"Downloaded files: {len(self.progress_data['downloaded_files'])}")
        print(f"Failed tracks: {len(self.progress_data['failed_tracks'])}")
        
        if self.progress_data['failed_tracks']:
            print(f"\n{Fore.YELLOW}Failed tracks:{Style.RESET_ALL}")
            for track in self.progress_data['failed_tracks']:
                print(f"- {track['name']} ({track['reason']})")
    
    def reset_progress(self):
        """Reset progress data"""
        self.progress_data = {
            'processed_tracks': [],
            'failed_tracks': [],
            'downloaded_files': []
        }
        self.save_progress()
        print(f"{Fore.GREEN}Progress reset successfully{Style.RESET_ALL}")


async def main():
    """Main entry point"""
    downloader = SpotifyDownloader()
    
    if len(sys.argv) < 2:
        print(f"{Fore.CYAN}Spotify Playlist Downloader{Style.RESET_ALL}")
        print(f"\nUsage:")
        print(f"  python spotify_downloader.py <playlist_url> [options]")
        print(f"\nOptions:")
        print(f"  --dry-run    Show tracks without downloading")
        print(f"  --status     Show current progress status")
        print(f"  --reset      Reset progress data")
        print(f"\nExample:")
        print(f"  python spotify_downloader.py https://open.spotify.com/playlist/xxxxx")
        return
    
    command = sys.argv[1]
    
    if command == '--status':
        downloader.show_status()
    elif command == '--reset':
        downloader.reset_progress()
    else:
        # Process playlist
        playlist_url = command
        dry_run = '--dry-run' in sys.argv
        
        await downloader.process_playlist(playlist_url, dry_run)


if __name__ == "__main__":
    asyncio.run(main())