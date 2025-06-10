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
from typing import Dict, Optional, AsyncGenerator, Callable
from dataclasses import dataclass

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import DocumentAttributeFilename, DocumentAttributeAudio
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
    response_timeout: int = 60


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
        
        # Callbacks
        self.on_file_downloaded: Optional[Callable] = None
        self.on_download_failed: Optional[Callable] = None
        self.on_bot_response: Optional[Callable] = None
    
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
        # Check if message has a document (file)
        if event.message.document:
            await self._handle_file_response(event)
        
        # Handle text responses (errors or status)
        elif event.message.text:
            if self.on_bot_response:
                await self.on_bot_response(event.message.text)
            print(f"{Fore.YELLOW}Bot response: {event.message.text}{Style.RESET_ALL}")
    
    async def _handle_file_response(self, event):
        """Handle file responses from bot"""
        # Find matching pending request
        matched_request = self._find_matching_request()
        
        if not matched_request:
            print(f"{Fore.YELLOW}Received file but no matching request found{Style.RESET_ALL}")
            return
        
        track = matched_request.track
        track_name = matched_request.track_name
        
        # Determine filename
        filename = self._extract_filename(event.message.document, track_name)
        
        # Notify about file reception
        print(f"{Fore.CYAN}Received file for: {track_name}{Style.RESET_ALL}")
        
        # Return the event and metadata for external handling
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
    
    def _extract_filename(self, document, fallback_name: str) -> str:
        """Extract filename from document or generate fallback"""
        # Try to get filename from document attributes
        for attr in document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name
            elif isinstance(attr, DocumentAttributeAudio):
                if hasattr(attr, 'title') and attr.title:
                    return f"{attr.title}.flac"
        
        # Fallback to track name
        return f"{fallback_name}.flac"
    
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
                
                # Track pending response
                self.pending_responses[message.id] = PendingRequest(
                    track=track,
                    track_name=track_name,
                    sent_at=datetime.now(),
                    message_id=message.id
                )
                
                print(f"{Fore.CYAN}Sent: {track_name}{Style.RESET_ALL}")
                
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
            print(f"{Fore.CYAN}Downloading: {filepath.name}{Style.RESET_ALL}")
            
            def default_progress(current, total):
                if progress_callback:
                    progress_callback(current, total)
                else:
                    percent = (current / total) * 100 if total > 0 else 0
                    print(f"\rProgress: {current}/{total} bytes ({percent:.1f}%)", end='')
            
            await self.client.download_media(
                message,
                file=str(filepath),
                progress_callback=default_progress
            )
            
            print()  # New line after progress
            return True
            
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
        cutoff_time = datetime.now() - timedelta(seconds=self.config.response_timeout)
        expired_ids = [
            msg_id for msg_id, request in self.pending_responses.items()
            if request.sent_at <= cutoff_time
        ]
        
        for msg_id in expired_ids:
            del self.pending_responses[msg_id]
        
        return len(self.pending_responses)
    
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
            print(f"{Fore.YELLOW}Waiting for {self.get_pending_count()} pending responses...{Style.RESET_ALL}")
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