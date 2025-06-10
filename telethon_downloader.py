#!/usr/bin/env python3
import os
import sys
import time
import json
import asyncio
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import DocumentAttributeFilename, DocumentAttributeAudio
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
from colorama import init, Fore, Style
from tqdm import tqdm

# Initialize colorama
init()

class TelethonSpotifyDownloader:
    def __init__(self):
        load_dotenv()
        
        # Spotify configuration
        self.spotify_client_id = os.getenv('SPOTIFY_CLIENT_ID')
        self.spotify_client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        
        # Telegram configuration
        self.api_id = int(os.getenv('TELEGRAM_API_ID'))
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone_number = os.getenv('TELEGRAM_PHONE_NUMBER')
        self.bot_username = os.getenv('EXTERNAL_BOT_USERNAME', '@your_bot_username')
        
        # Security: Store session in protected directory
        self.session_dir = Path('./sessions')
        self.session_dir.mkdir(mode=0o700, exist_ok=True)
        self.session_file = self.session_dir / 'spotify_downloader.session'
        
        # Download configuration
        self.download_folder = Path(os.getenv('DOWNLOAD_FOLDER', './downloads'))
        self.delay_between_requests = float(os.getenv('DELAY_BETWEEN_REQUESTS', 3))
        self.max_retries = int(os.getenv('MAX_RETRIES', 3))
        self.flood_wait_multiplier = float(os.getenv('FLOOD_WAIT_MULTIPLIER', 1.5))
        
        # Progress tracking
        self.progress_file = Path('progress.json')
        self.progress_data = self.load_progress()
        
        # Response tracking
        self.pending_responses = {}
        self.response_timeout = 60  # seconds
        
        # Initialize Spotify
        self.spotify = self.init_spotify()
        
        # Create download folder
        self.download_folder.mkdir(exist_ok=True)
        
        # Telegram client (initialized in async context)
        self.client = None
    
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
            'downloaded_files': [],
            'last_run': None,
            'total_downloads': 0
        }
    
    def save_progress(self):
        """Save progress to file"""
        self.progress_data['last_run'] = datetime.now().isoformat()
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress_data, f, indent=2)
    
    async def init_client(self):
        """Initialize Telegram client with security considerations"""
        print(f"{Fore.CYAN}Initializing secure Telegram client...{Style.RESET_ALL}")
        
        # Create client with session file
        self.client = TelegramClient(
            str(self.session_file),
            self.api_id,
            self.api_hash,
            system_version="4.16.30-vxCUSTOM"  # Mimic regular client
        )
        
        # Connect and authenticate
        await self.client.connect()
        
        if not await self.client.is_user_authorized():
            print(f"{Fore.YELLOW}First time authentication required{Style.RESET_ALL}")
            await self.client.send_code_request(self.phone_number)
            
            try:
                code = input(f"{Fore.CYAN}Enter the code you received: {Style.RESET_ALL}")
                await self.client.sign_in(self.phone_number, code)
            except SessionPasswordNeededError:
                password = input(f"{Fore.CYAN}Two-factor authentication enabled. Enter password: {Style.RESET_ALL}")
                await self.client.sign_in(password=password)
        
        print(f"{Fore.GREEN}✓ Connected to Telegram{Style.RESET_ALL}")
        
        # Verify bot exists
        try:
            bot_entity = await self.client.get_entity(self.bot_username)
            print(f"{Fore.GREEN}✓ Found bot: {bot_entity.username}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}Error: Could not find bot {self.bot_username}{Style.RESET_ALL}")
            raise
    
    def extract_playlist_id(self, playlist_url: str) -> str:
        """Extract playlist ID from Spotify URL"""
        patterns = [
            r'playlist/([a-zA-Z0-9]+)',
            r'playlist:([a-zA-Z0-9]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, playlist_url)
            if match:
                return match.group(1)
        
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
                            'url': item['track']['external_urls']['spotify'],
                            'duration_ms': item['track']['duration_ms']
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
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe file system use"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '')
        
        if len(filename) > 200:
            filename = filename[:200]
        
        return filename.strip()
    
    async def handle_flood_wait(self, e: FloodWaitError):
        """Handle Telegram flood wait errors safely"""
        wait_time = e.seconds * self.flood_wait_multiplier
        print(f"{Fore.YELLOW}Rate limited! Waiting {wait_time:.0f} seconds...{Style.RESET_ALL}")
        
        # Show progress bar for long waits
        if wait_time > 10:
            for _ in tqdm(range(int(wait_time)), desc="Waiting", unit="s"):
                await asyncio.sleep(1)
        else:
            await asyncio.sleep(wait_time)
    
    async def send_track_to_bot(self, track: Dict) -> bool:
        """Send track URL to external bot with rate limiting"""
        track_name = f"{', '.join(track['artists'])} - {track['name']}"
        
        for attempt in range(self.max_retries):
            try:
                # Send message to bot
                message = await self.client.send_message(
                    self.bot_username,
                    track['url']
                )
                
                # Track pending response
                self.pending_responses[message.id] = {
                    'track': track,
                    'track_name': track_name,
                    'sent_at': datetime.now(),
                    'message_id': message.id
                }
                
                print(f"{Fore.CYAN}Sent: {track_name}{Style.RESET_ALL}")
                return True
                
            except FloodWaitError as e:
                await self.handle_flood_wait(e)
                continue
                
            except Exception as e:
                print(f"{Fore.RED}Error sending message (attempt {attempt + 1}): {e}{Style.RESET_ALL}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(5)
                continue
        
        return False
    
    async def download_file(self, message, filepath: Path) -> bool:
        """Download file from Telegram message"""
        try:
            # Download with progress bar
            print(f"{Fore.CYAN}Downloading: {filepath.name}{Style.RESET_ALL}")
            
            await self.client.download_media(
                message,
                file=str(filepath),
                progress_callback=lambda current, total: 
                    print(f"\rProgress: {current}/{total} bytes ({current/total*100:.1f}%)", end='')
            )
            
            print()  # New line after progress
            return True
            
        except Exception as e:
            print(f"{Fore.RED}Download error: {e}{Style.RESET_ALL}")
            if filepath.exists():
                filepath.unlink()
            return False
    
    async def monitor_bot_responses(self):
        """Monitor for file responses from bot"""
        @self.client.on(events.NewMessage(from_users=self.bot_username))
        async def handler(event):
            # Check if message has a document (file)
            if event.message.document:
                # Find matching pending request
                matched_request = None
                
                # Check recent pending requests (within timeout)
                cutoff_time = datetime.now() - timedelta(seconds=self.response_timeout)
                
                for msg_id, request in list(self.pending_responses.items()):
                    if request['sent_at'] > cutoff_time:
                        # Try to match by timing or content
                        matched_request = request
                        del self.pending_responses[msg_id]
                        break
                
                if matched_request:
                    track = matched_request['track']
                    track_name = matched_request['track_name']
                    
                    # Determine filename
                    filename = None
                    for attr in event.message.document.attributes:
                        if isinstance(attr, DocumentAttributeFilename):
                            filename = attr.file_name
                            break
                    
                    if not filename:
                        filename = f"{track_name}.flac"
                    
                    filename = self.sanitize_filename(filename)
                    filepath = self.download_folder / filename
                    
                    # Download file
                    if await self.download_file(event.message, filepath):
                        self.progress_data['processed_tracks'].append(track['id'])
                        self.progress_data['downloaded_files'].append(str(filepath))
                        self.progress_data['total_downloads'] += 1
                        self.save_progress()
                        print(f"{Fore.GREEN}✓ Downloaded: {filename}{Style.RESET_ALL}")
                    else:
                        self.progress_data['failed_tracks'].append({
                            'id': track['id'],
                            'name': track_name,
                            'reason': 'Download failed'
                        })
                        self.save_progress()
            
            # Handle text responses (errors or status)
            elif event.message.text:
                print(f"{Fore.YELLOW}Bot response: {event.message.text}{Style.RESET_ALL}")
    
    async def process_playlist(self, playlist_url: str, dry_run: bool = False, batch_size: int = 10):
        """Process playlist with batch processing and safety features"""
        # Initialize client
        await self.init_client()
        
        # Set up response monitoring
        await self.monitor_bot_responses()
        
        # Get playlist info
        playlist_id = self.extract_playlist_id(playlist_url)
        
        try:
            playlist_info = self.spotify.playlist(playlist_id)
            playlist_name = playlist_info['name']
            print(f"\n{Fore.CYAN}Playlist: {playlist_name}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Owner: {playlist_info['owner']['display_name']}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Tracks: {playlist_info['tracks']['total']}{Style.RESET_ALL}\n")
        except Exception as e:
            print(f"{Fore.RED}Error accessing playlist: {e}{Style.RESET_ALL}")
            return
        
        # Get tracks
        tracks = self.get_playlist_tracks(playlist_id)
        
        if dry_run:
            print(f"\n{Fore.YELLOW}DRY RUN MODE - No messages will be sent{Style.RESET_ALL}")
            for i, track in enumerate(tracks, 1):
                artists = ', '.join(track['artists'])
                print(f"{i}. {artists} - {track['name']}")
            return
        
        # Safety check
        print(f"\n{Fore.YELLOW}Security Notice:{Style.RESET_ALL}")
        print(f"- Messages will be sent from your personal account")
        print(f"- Minimum {self.delay_between_requests}s delay between messages")
        print(f"- Processing in batches of {batch_size}")
        print(f"- Session stored securely in: {self.session_file}")
        
        confirm = input(f"\n{Fore.CYAN}Continue? (yes/no): {Style.RESET_ALL}")
        if confirm.lower() != 'yes':
            print("Cancelled.")
            return
        
        # Process tracks in batches
        successful = 0
        failed = 0
        
        for batch_start in range(0, len(tracks), batch_size):
            batch_end = min(batch_start + batch_size, len(tracks))
            batch = tracks[batch_start:batch_end]
            
            print(f"\n{Fore.CYAN}Processing batch {batch_start//batch_size + 1} ({batch_start + 1}-{batch_end} of {len(tracks)}){Style.RESET_ALL}")
            
            for i, track in enumerate(batch):
                global_index = batch_start + i + 1
                
                # Skip if already processed
                if track['id'] in self.progress_data['processed_tracks']:
                    print(f"{Fore.YELLOW}[{global_index}/{len(tracks)}] Already processed, skipping{Style.RESET_ALL}")
                    successful += 1
                    continue
                
                print(f"\n{Fore.CYAN}[{global_index}/{len(tracks)}]{Style.RESET_ALL}")
                
                # Send to bot
                if await self.send_track_to_bot(track):
                    # Wait before next message
                    if i < len(batch) - 1 or batch_end < len(tracks):
                        await asyncio.sleep(self.delay_between_requests)
                else:
                    failed += 1
                    self.progress_data['failed_tracks'].append({
                        'id': track['id'],
                        'name': f"{', '.join(track['artists'])} - {track['name']}",
                        'reason': 'Failed to send message'
                    })
                    self.save_progress()
            
            # Wait for responses from this batch
            if batch_end < len(tracks):
                print(f"{Fore.YELLOW}Waiting for bot responses before next batch...{Style.RESET_ALL}")
                await asyncio.sleep(10)
        
        # Wait for final responses
        print(f"\n{Fore.YELLOW}Waiting for remaining bot responses...{Style.RESET_ALL}")
        await asyncio.sleep(30)
        
        # Final report
        successful = len(self.progress_data['processed_tracks'])
        print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Total processed: {successful}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Downloaded files: {self.progress_data['total_downloads']}{Style.RESET_ALL}")
        print(f"{Fore.RED}Failed: {len(self.progress_data['failed_tracks'])}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Progress saved to: {self.progress_file}{Style.RESET_ALL}")
    
    def show_status(self):
        """Show current progress status"""
        print(f"\n{Fore.CYAN}Current Status:{Style.RESET_ALL}")
        print(f"Processed tracks: {len(self.progress_data['processed_tracks'])}")
        print(f"Downloaded files: {self.progress_data['total_downloads']}")
        print(f"Failed tracks: {len(self.progress_data['failed_tracks'])}")
        
        if self.progress_data['last_run']:
            print(f"Last run: {self.progress_data['last_run']}")
        
        if self.progress_data['failed_tracks']:
            print(f"\n{Fore.YELLOW}Failed tracks:{Style.RESET_ALL}")
            for track in self.progress_data['failed_tracks'][-10:]:  # Show last 10
                print(f"- {track['name']} ({track['reason']})")
    
    def reset_progress(self):
        """Reset progress data"""
        self.progress_data = {
            'processed_tracks': [],
            'failed_tracks': [],
            'downloaded_files': [],
            'last_run': None,
            'total_downloads': 0
        }
        self.save_progress()
        print(f"{Fore.GREEN}Progress reset successfully{Style.RESET_ALL}")
    
    async def cleanup(self):
        """Clean up resources"""
        if self.client:
            await self.client.disconnect()


async def main():
    """Main entry point"""
    downloader = TelethonSpotifyDownloader()
    
    if len(sys.argv) < 2:
        print(f"{Fore.CYAN}Telethon Spotify Downloader (External Bot){Style.RESET_ALL}")
        print(f"\nUsage:")
        print(f"  python telethon_downloader.py <playlist_url> [options]")
        print(f"\nOptions:")
        print(f"  --dry-run       Show tracks without sending messages")
        print(f"  --batch-size N  Process N tracks at a time (default: 10)")
        print(f"  --status        Show current progress status")
        print(f"  --reset         Reset progress data")
        print(f"\nSecurity:")
        print(f"  - Uses your personal Telegram account")
        print(f"  - Minimum 3s delay between messages")
        print(f"  - Session stored securely")
        print(f"\nExample:")
        print(f"  python telethon_downloader.py https://open.spotify.com/playlist/xxxxx")
        return
    
    command = sys.argv[1]
    
    try:
        if command == '--status':
            downloader.show_status()
        elif command == '--reset':
            downloader.reset_progress()
        else:
            # Process playlist
            playlist_url = command
            dry_run = '--dry-run' in sys.argv
            
            # Extract batch size
            batch_size = 10
            for i, arg in enumerate(sys.argv):
                if arg == '--batch-size' and i + 1 < len(sys.argv):
                    batch_size = int(sys.argv[i + 1])
            
            await downloader.process_playlist(playlist_url, dry_run, batch_size)
    
    finally:
        await downloader.cleanup()


if __name__ == "__main__":
    asyncio.run(main())