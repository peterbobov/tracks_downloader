#!/usr/bin/env python3
"""
Telegram Client Module

Handles all Telegram interactions using Telethon including:
- Secure session management
- Bot communication with rate limiting
- File download monitoring
- FloodWait error handling
"""

import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, AsyncGenerator, Callable, Tuple
from dataclasses import dataclass

from fuzzywuzzy import fuzz

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import (
    DocumentAttributeFilename, 
    DocumentAttributeAudio,
    MessageMediaPhoto,
    KeyboardButtonCallback
)
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from colorama import Fore, Style

from .spotify_api import Track


@dataclass
class TelegramConfig:
    """Configuration for Telegram client"""
    api_id: int
    api_hash: str
    phone_number: str
    bot_username: str
    session_dir: str = "./sessions"
    delay_between_requests: float = 3.0
    max_retries: int = 3
    flood_wait_multiplier: float = 1.5
    response_timeout: int = 300  # 5 minutes for large file downloads


@dataclass
class PendingRequest:
    """Represents a pending request to the bot"""
    track: Track
    track_name: str
    sent_at: datetime
    message_id: int


class TelegramMessenger:
    """Handles all Telegram communication via Telethon"""
    
    def __init__(self, config: TelegramConfig):
        self.config = config
        
        # Session management
        self.session_dir = Path(config.session_dir)
        self.session_dir.mkdir(mode=0o700, exist_ok=True)
        self.session_file = self.session_dir / 'spotify_downloader.session'
        
        # Tracking
        self.pending_responses: Dict[int, PendingRequest] = {}
        self.client: Optional[TelegramClient] = None
        
        # Debug mode
        self.debug_mode = False
        
        # Callbacks
        self.on_file_downloaded: Optional[Callable] = None
        self.on_download_failed: Optional[Callable] = None
        self.on_bot_response: Optional[Callable] = None
    
    def _clear_print(self, message: str):
        """Print message after clearing any download progress line"""
        print(f"\r{' ' * 80}\r{message}")
    
    async def initialize(self) -> bool:
        """Initialize and authenticate Telegram client"""
        print(f"{Fore.CYAN}Initializing secure Telegram client...{Style.RESET_ALL}")
        
        try:
            # Create client with session file
            self.client = TelegramClient(
                str(self.session_file),
                self.config.api_id,
                self.config.api_hash,
                system_version="4.16.30-vxCUSTOM"  # Mimic regular client
            )
            
            # Connect and authenticate
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                await self._authenticate()
            
            print(f"{Fore.GREEN}✓ Connected to Telegram{Style.RESET_ALL}")
            
            # Verify bot exists
            await self._verify_bot()
            
            # Set up event handlers
            self._setup_event_handlers()
            
            return True
            
        except Exception as e:
            print(f"{Fore.RED}Failed to initialize Telegram client: {e}{Style.RESET_ALL}")
            return False
    
    async def _authenticate(self):
        """Handle first-time authentication"""
        print(f"{Fore.YELLOW}First time authentication required{Style.RESET_ALL}")
        await self.client.send_code_request(self.config.phone_number)
        
        try:
            code = input(f"{Fore.CYAN}Enter the code you received: {Style.RESET_ALL}")
            await self.client.sign_in(self.config.phone_number, code)
        except SessionPasswordNeededError:
            password = input(f"{Fore.CYAN}Two-factor authentication enabled. Enter password: {Style.RESET_ALL}")
            await self.client.sign_in(password=password)
    
    async def _verify_bot(self):
        """Verify that the external bot exists and is accessible"""
        try:
            bot_entity = await self.client.get_entity(self.config.bot_username)
            print(f"{Fore.GREEN}✓ Found bot: {bot_entity.username}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}Error: Could not find bot {self.config.bot_username}{Style.RESET_ALL}")
            raise
    
    def _setup_event_handlers(self):
        """Set up event handlers for monitoring bot responses"""
        @self.client.on(events.NewMessage(from_users=self.config.bot_username))
        async def response_handler(event):
            await self._handle_bot_response(event)
    
    async def _handle_bot_response(self, event):
        """Handle responses from the bot"""
        # Proactive cleanup of expired requests
        self._cleanup_expired_requests()
        
        if self.debug_mode:
            pending_count = len(self.pending_responses)
            print(f"{Fore.MAGENTA}DEBUG: Received message type - Document: {bool(event.message.document)}, "
                  f"Buttons: {bool(event.message.buttons)}, Photo: {isinstance(event.message.media, MessageMediaPhoto)}, "
                  f"Text: {bool(event.message.text)}, Pending: {pending_count}{Style.RESET_ALL}")
        
        # Check if message has a document (file)
        if event.message.document:
            if self.debug_mode:
                print(f"{Fore.MAGENTA}DEBUG: Document detected - MIME: {event.message.document.mime_type}, "
                      f"Size: {event.message.document.size:,} bytes{Style.RESET_ALL}")
            await self._handle_file_response(event)
        
        # Check if message has inline keyboard buttons (track options)
        elif event.message.buttons:
            if self.debug_mode:
                print(f"{Fore.MAGENTA}DEBUG: Buttons detected - Count: {len(event.message.buttons)}{Style.RESET_ALL}")
            await self._handle_button_response(event)
        
        # Check if message has an image (nothing found response)
        elif isinstance(event.message.media, MessageMediaPhoto):
            if self.debug_mode:
                print(f"{Fore.MAGENTA}DEBUG: Photo detected (nothing found){Style.RESET_ALL}")
            await self._handle_nothing_found_response(event)
        
        # Handle text responses (errors or status)
        elif event.message.text:
            if self.debug_mode:
                print(f"{Fore.MAGENTA}DEBUG: Text message detected: {event.message.text[:100]}{Style.RESET_ALL}")
            if self.on_bot_response:
                await self.on_bot_response(event.message.text)
            print(f"{Fore.YELLOW}Bot response: {event.message.text}{Style.RESET_ALL}")
        
        elif self.debug_mode:
            print(f"{Fore.MAGENTA}DEBUG: Unknown message type detected{Style.RESET_ALL}")
    
    async def _handle_button_response(self, event):
        """Handle button responses from bot (track options)"""
        # Find matching pending request
        matched_request = self._find_matching_request()
        
        if not matched_request:
            print(f"{Fore.YELLOW}Received buttons but no matching request found{Style.RESET_ALL}")
            return
        
        track_name = matched_request.track_name
        
        # Log button options received
        self._clear_print(f"{Fore.CYAN}Bot found options for: {track_name}{Style.RESET_ALL}")
        
        # Click the first button automatically
        try:
            if event.message.buttons and len(event.message.buttons) > 0:
                first_row = event.message.buttons[0]
                if isinstance(first_row, list) and len(first_row) > 0:
                    first_button = first_row[0]
                else:
                    first_button = first_row
                
                # Click the button to select track
                await event.message.click(0)  # Click first button (index 0)
                self._clear_print(f"{Fore.GREEN}✓ Selected first option for: {track_name}{Style.RESET_ALL}")
                
                # Create new pending request for the file download with updated timestamp
                # Use consistent key format with track ID
                new_key = f"msg_{event.message.id}_{matched_request.track.id[:8]}"
                new_request = PendingRequest(
                    track=matched_request.track,
                    track_name=matched_request.track_name,
                    sent_at=datetime.now(),  # Reset timestamp for file download phase
                    message_id=event.message.id
                )
                self.pending_responses[new_key] = new_request
                
        except Exception as e:
            print(f"{Fore.RED}Error clicking button for {track_name}: {e}{Style.RESET_ALL}")
            if self.on_download_failed:
                await self.on_download_failed(matched_request.track, f"Failed to select track option: {e}")
    
    async def _handle_nothing_found_response(self, event):
        """Handle 'nothing found' image responses from bot"""
        # Find matching pending request
        matched_request = self._find_matching_request()
        
        if not matched_request:
            print(f"{Fore.YELLOW}Received image but no matching request found{Style.RESET_ALL}")
            return
        
        track = matched_request.track
        track_name = matched_request.track_name
        
        # Log that track was not found
        self._clear_print(f"{Fore.YELLOW}⚠ Track not available: {track_name}{Style.RESET_ALL}")
        
        # Notify about unavailable track
        if self.on_download_failed:
            await self.on_download_failed(track, "Track not found by bot")
    
    async def _handle_file_response(self, event):
        """Handle file responses from bot"""
        # Extract filename and metadata for smart matching
        filename, metadata = self._extract_filename_and_metadata(event.message.document, "unknown")
        
        # Find matching pending request using smart content-based matching
        matched_request = self._find_best_matching_request(filename, metadata)
        
        if not matched_request:
            print(f"{Fore.YELLOW}Received file '{filename}' but no matching request found{Style.RESET_ALL}")
            # Clean up any orphaned pending responses that might match this file
            self._cleanup_orphaned_requests()
            return
        
        track = matched_request.track
        track_name = matched_request.track_name
        
        # Notify about file reception with smart match info
        self._clear_print(f"{Fore.CYAN}Received file for: {track_name} → {filename}{Style.RESET_ALL}")
        
        # Handle the download directly
        if self.on_file_downloaded:
            await self.on_file_downloaded(event.message, filename, track, track_name)
    
    def _find_matching_request(self) -> Optional[PendingRequest]:
        """Find matching pending request (FIFO approach)"""
        cutoff_time = datetime.now() - timedelta(seconds=self.config.response_timeout)
        
        # Find the oldest valid request (FIFO)
        oldest_request = None
        oldest_msg_id = None
        
        for msg_id, request in list(self.pending_responses.items()):
            if request.sent_at > cutoff_time:
                if oldest_request is None or request.sent_at < oldest_request.sent_at:
                    oldest_request = request
                    oldest_msg_id = msg_id
            else:
                # Remove expired requests
                del self.pending_responses[msg_id]
        
        if oldest_request and oldest_msg_id:
            del self.pending_responses[oldest_msg_id]
            return oldest_request
        
        return None
    
    def _calculate_track_similarity(self, bot_filename: str, bot_metadata: Dict, spotify_artist: str, spotify_title: str) -> float:
        """Calculate similarity score between bot response and Spotify track"""
        scores = []
        
        # Clean up text for better matching
        def clean_text(text):
            return text.lower().replace('feat.', 'featuring').replace('&', 'and').strip()
        
        spotify_artist_clean = clean_text(spotify_artist)
        spotify_title_clean = clean_text(spotify_title)
        spotify_full = f"{spotify_artist_clean} - {spotify_title_clean}"
        
        # Score 1: Filename vs full track name (most reliable)
        if bot_filename:
            bot_filename_clean = clean_text(bot_filename.replace('.flac', '').replace('.mp3', ''))
            filename_score = fuzz.token_sort_ratio(bot_filename_clean, spotify_full)
            scores.append(('filename', filename_score, 0.6))  # High weight for filename
            
            # Also try just the title part
            title_score = fuzz.token_sort_ratio(bot_filename_clean, spotify_title_clean)
            scores.append(('filename_title', title_score, 0.3))
        
        # Score 2: Audio metadata performer vs Spotify artist
        if bot_metadata.get('performer'):
            performer_clean = clean_text(bot_metadata['performer'])
            performer_score = fuzz.token_sort_ratio(performer_clean, spotify_artist_clean)
            scores.append(('performer', performer_score, 0.4))
        
        # Score 3: Audio metadata title vs Spotify title
        if bot_metadata.get('title'):
            title_clean = clean_text(bot_metadata['title'])
            title_score = fuzz.token_sort_ratio(title_clean, spotify_title_clean)
            scores.append(('title', title_score, 0.5))
        
        # Calculate weighted average
        if not scores:
            return 0.0
        
        total_weighted = sum(score * weight for _, score, weight in scores)
        total_weight = sum(weight for _, _, weight in scores)
        
        return total_weighted / total_weight if total_weight > 0 else 0.0
    
    def _find_best_matching_request(self, bot_filename: str, bot_metadata: Dict) -> Optional[PendingRequest]:
        """Find best matching request using content similarity"""
        # Clean up expired requests first
        self._cleanup_expired_requests()
        
        if not self.pending_responses:
            return None
        
        best_match = None
        best_score = 0.0
        best_request_id = None
        match_details = []
        
        # Score all pending requests
        for request_id, request in self.pending_responses.items():
            spotify_artist = request.track.artist_string
            spotify_title = request.track.name
            
            score = self._calculate_track_similarity(
                bot_filename, bot_metadata, 
                spotify_artist, spotify_title
            )
            
            match_details.append((request_id, score, f"{spotify_artist} - {spotify_title}"))
            
            if score > best_score:
                best_score = score
                best_match = request
                best_request_id = request_id
        
        # Debug output
        if self.debug_mode and match_details:
            print(f"{Fore.MAGENTA}DEBUG: Smart matching for '{bot_filename}':{Style.RESET_ALL}")
            for req_id, score, track_name in sorted(match_details, key=lambda x: x[1], reverse=True):
                print(f"{Fore.MAGENTA}  {score:5.1f}% - {track_name}{Style.RESET_ALL}")
            if best_match:
                print(f"{Fore.MAGENTA}  → Best match: {best_score:.1f}% confidence{Style.RESET_ALL}")
        
        # Use smart match if confidence is high enough
        confidence_threshold = 70.0
        if best_score >= confidence_threshold and best_match:
            if self.debug_mode:
                print(f"{Fore.GREEN}✓ Smart match: {best_score:.1f}% confidence{Style.RESET_ALL}")
            # Remove the matched request
            del self.pending_responses[best_request_id]
            return best_match
        
        # Fall back to FIFO if no good smart match
        if self.debug_mode:
            print(f"{Fore.YELLOW}→ Falling back to FIFO (best score: {best_score:.1f}%){Style.RESET_ALL}")
        
        return self._find_matching_request()
    
    def _extract_filename(self, document, fallback_name: str) -> str:
        """Extract filename from document or generate fallback"""
        filename, _ = self._extract_filename_and_metadata(document, fallback_name)
        return filename
    
    def _extract_filename_and_metadata(self, document, fallback_name: str) -> Tuple[str, Dict]:
        """Extract filename and metadata from document for smart matching"""
        filename = None
        metadata = {}
        
        # Try to get filename and metadata from document attributes
        for attr in document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                filename = attr.file_name
            elif isinstance(attr, DocumentAttributeAudio):
                if hasattr(attr, 'title') and attr.title:
                    metadata['title'] = attr.title
                    if not filename:
                        filename = f"{attr.title}.flac"
                if hasattr(attr, 'performer') and attr.performer:
                    metadata['performer'] = attr.performer
                if hasattr(attr, 'duration') and attr.duration:
                    metadata['duration'] = attr.duration
        
        # Fallback to track name if no filename found
        if not filename:
            filename = f"{fallback_name}.flac"
        
        return filename, metadata
    
    async def send_track_to_bot(self, track: Track) -> bool:
        """Send track URL to external bot with rate limiting"""
        if not self.client:
            raise RuntimeError("Telegram client not initialized")
        
        track_name = f"{track.artist_string} - {track.name}"
        
        for attempt in range(self.config.max_retries):
            try:
                # Send message to bot
                message = await self.client.send_message(
                    self.config.bot_username,
                    track.url
                )
                
                # Track pending response with unique key including track ID
                request_key = f"msg_{message.id}_{track.id[:8]}"
                self.pending_responses[request_key] = PendingRequest(
                    track=track,
                    track_name=track_name,
                    sent_at=datetime.now(),
                    message_id=message.id
                )
                
                self._clear_print(f"{Fore.CYAN}Sent: {track_name}{Style.RESET_ALL}")
                
                # Rate limiting delay
                await asyncio.sleep(self.config.delay_between_requests)
                
                return True
                
            except FloodWaitError as e:
                await self._handle_flood_wait(e)
                continue
                
            except Exception as e:
                print(f"{Fore.RED}Error sending message (attempt {attempt + 1}): {e}{Style.RESET_ALL}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(5)
                continue
        
        return False
    
    async def _handle_flood_wait(self, e: FloodWaitError):
        """Handle Telegram flood wait errors safely"""
        wait_time = e.seconds * self.config.flood_wait_multiplier
        print(f"{Fore.YELLOW}Rate limited! Waiting {wait_time:.0f} seconds...{Style.RESET_ALL}")
        
        # Show progress for long waits
        if wait_time > 10:
            print(f"{Fore.YELLOW}Waiting", end="")
            for _ in range(int(wait_time)):
                await asyncio.sleep(1)
                print(".", end="", flush=True)
            print(f" Done!{Style.RESET_ALL}")
        else:
            await asyncio.sleep(wait_time)
    
    async def download_file(self, message, filepath: Path, progress_callback: Optional[Callable] = None) -> bool:
        """Download file from Telegram message"""
        if not self.client:
            raise RuntimeError("Telegram client not initialized")
        
        try:
            self._clear_print(f"{Fore.CYAN}Downloading: {filepath.name}{Style.RESET_ALL}")
            
            def default_progress(current, total):
                if progress_callback:
                    progress_callback(current, total)
                else:
                    percent = (current / total) * 100 if total > 0 else 0
                    print(f"\rProgress: {current}/{total} bytes ({percent:.1f}%)", end='')
            
            # Add timeout for large file downloads
            await asyncio.wait_for(
                self.client.download_media(
                    message,
                    file=str(filepath),
                    progress_callback=default_progress
                ),
                timeout=300  # 5 minute timeout
            )
            
            print()  # New line after progress
            
            # Verify file was downloaded completely
            if not filepath.exists():
                print(f"{Fore.RED}Download failed: File does not exist{Style.RESET_ALL}")
                return False
            
            file_size = filepath.stat().st_size
            if file_size == 0:
                print(f"{Fore.RED}Download failed: File is empty{Style.RESET_ALL}")
                filepath.unlink()
                return False
            
            self._clear_print(f"{Fore.GREEN}✓ Download complete: {file_size:,} bytes{Style.RESET_ALL}")
            return True
            
        except asyncio.TimeoutError:
            print(f"{Fore.RED}Download timeout: File too large or connection slow{Style.RESET_ALL}")
            if filepath.exists():
                filepath.unlink()
            return False
        except Exception as e:
            print(f"{Fore.RED}Download error: {e}{Style.RESET_ALL}")
            if filepath.exists():
                filepath.unlink()
            return False
    
    async def send_batch_to_bot(self, tracks: list[Track], batch_delay: float = 10.0) -> Dict[str, int]:
        """Send multiple tracks to bot with batch processing"""
        results = {"success": 0, "failed": 0}
        
        for i, track in enumerate(tracks):
            print(f"\n{Fore.CYAN}[{i+1}/{len(tracks)}]{Style.RESET_ALL}")
            
            if await self.send_track_to_bot(track):
                results["success"] += 1
            else:
                results["failed"] += 1
            
            # Additional delay between batches if specified
            if i < len(tracks) - 1 and batch_delay > 0:
                await asyncio.sleep(batch_delay)
        
        return results
    
    def get_pending_count(self) -> int:
        """Get number of pending responses"""
        # Clean up expired requests first
        self._cleanup_expired_requests()
        return len(self.pending_responses)
    
    def _cleanup_expired_requests(self):
        """Clean up expired pending requests"""
        cutoff_time = datetime.now() - timedelta(seconds=self.config.response_timeout)
        expired_ids = [
            msg_id for msg_id, request in self.pending_responses.items()
            if request.sent_at <= cutoff_time
        ]
        
        if expired_ids and self.debug_mode:
            print(f"{Fore.YELLOW}Cleaning up {len(expired_ids)} expired requests{Style.RESET_ALL}")
        
        for msg_id in expired_ids:
            del self.pending_responses[msg_id]
    
    def _cleanup_orphaned_requests(self):
        """Clean up orphaned requests that might be causing issues"""
        if len(self.pending_responses) > 50:  # If we have too many pending
            # Keep only the most recent 30 requests
            sorted_requests = sorted(
                self.pending_responses.items(), 
                key=lambda x: x[1].sent_at, 
                reverse=True
            )
            
            # Clear all and keep only recent ones
            self.pending_responses.clear()
            for msg_id, request in sorted_requests[:30]:
                self.pending_responses[msg_id] = request
            
            if self.debug_mode:
                print(f"{Fore.YELLOW}Cleaned up orphaned requests, keeping 30 most recent{Style.RESET_ALL}")
    
    def set_callbacks(self, 
                     on_file_downloaded: Optional[Callable] = None,
                     on_download_failed: Optional[Callable] = None,
                     on_bot_response: Optional[Callable] = None):
        """Set callback functions for various events"""
        self.on_file_downloaded = on_file_downloaded
        self.on_download_failed = on_download_failed
        self.on_bot_response = on_bot_response
    
    async def cleanup(self):
        """Clean up resources"""
        if self.client:
            await self.client.disconnect()
            self.client = None
    
    async def wait_for_responses(self, timeout_seconds: int = 30):
        """Wait for pending responses to be processed"""
        start_time = time.time()
        
        while self.get_pending_count() > 0 and (time.time() - start_time) < timeout_seconds:
            self._clear_print(f"{Fore.YELLOW}Waiting for {self.get_pending_count()} pending responses...{Style.RESET_ALL}")
            await asyncio.sleep(5)
        
        remaining = self.get_pending_count()
        if remaining > 0:
            print(f"{Fore.YELLOW}Timeout reached. {remaining} responses still pending.{Style.RESET_ALL}")


def create_telegram_config(api_id: int, api_hash: str, phone_number: str, 
                          bot_username: str, **kwargs) -> TelegramConfig:
    """Factory function to create TelegramConfig"""
    return TelegramConfig(
        api_id=api_id,
        api_hash=api_hash,
        phone_number=phone_number,
        bot_username=bot_username,
        **kwargs
    )


async def create_telegram_messenger(config: TelegramConfig) -> TelegramMessenger:
    """Factory function to create and initialize TelegramMessenger"""
    messenger = TelegramMessenger(config)
    
    if await messenger.initialize():
        return messenger
    else:
        raise RuntimeError("Failed to initialize Telegram messenger")


if __name__ == "__main__":
    # Example usage
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    async def main():
        config = create_telegram_config(
            api_id=int(os.getenv('TELEGRAM_API_ID')),
            api_hash=os.getenv('TELEGRAM_API_HASH'),
            phone_number=os.getenv('TELEGRAM_PHONE_NUMBER'),
            bot_username=os.getenv('EXTERNAL_BOT_USERNAME')
        )
        
        messenger = await create_telegram_messenger(config)
        
        # Example: Send a test message
        from .spotify_api import Track
        
        test_track = Track(
            id="test",
            name="Test Track",
            artists=["Test Artist"],
            album="Test Album",
            url="https://open.spotify.com/track/test",
            duration_ms=180000
        )
        
        success = await messenger.send_track_to_bot(test_track)
        print(f"Message sent successfully: {success}")
        
        await messenger.cleanup()
    
    asyncio.run(main())