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
from typing import Dict, Optional, Callable, Tuple
from dataclasses import dataclass

from fuzzywuzzy import fuzz

from telethon import TelegramClient, events

from .constants import TelegramConstants, MatchingWeights
from .utils import clear_print, normalize_text, strip_bot_artifacts
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
    delay_between_requests: float = TelegramConstants.DEFAULT_DELAY_BETWEEN_REQUESTS
    max_retries: int = TelegramConstants.DEFAULT_MAX_RETRIES
    flood_wait_multiplier: float = TelegramConstants.FLOOD_WAIT_MULTIPLIER
    response_timeout: int = TelegramConstants.DEFAULT_RESPONSE_TIMEOUT


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

        # Tracking with async lock for thread-safe access
        self.pending_responses: Dict[str, PendingRequest] = {}
        self._pending_lock = asyncio.Lock()
        self.client: Optional[TelegramClient] = None

        # Debug mode
        self.debug_mode = False

        # Callbacks
        self.on_file_downloaded: Optional[Callable] = None
        self.on_download_failed: Optional[Callable] = None
        self.on_bot_response: Optional[Callable] = None

    def _clear_print(self, message: str) -> None:
        """Print message after clearing any download progress line"""
        clear_print(message)
    
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
        # Proactive cleanup of expired requests (thread-safe)
        async with self._pending_lock:
            self._cleanup_expired_requests_unlocked()

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
    
    def _extract_button_text(self, event) -> str:
        """Extract text from button message for matching (button labels + message text)"""
        parts = []
        if event.message.text:
            parts.append(event.message.text)
        if event.message.buttons:
            for row in event.message.buttons:
                if isinstance(row, list):
                    for btn in row:
                        if hasattr(btn, 'text') and btn.text:
                            parts.append(btn.text)
                elif hasattr(row, 'text') and row.text:
                    parts.append(row.text)
        return ' '.join(parts)

    def _find_best_matching_request_by_text_unlocked(self, button_text: str) -> Optional[PendingRequest]:
        """
        Find best matching pending request using button/message text similarity.

        Note: Must be called while holding self._pending_lock.
        """
        self._cleanup_expired_requests_unlocked()

        if not self.pending_responses:
            return None

        best_match = None
        best_score = 0.0
        best_request_id = None

        for request_id, request in self.pending_responses.items():
            spotify_full = f"{request.track.artist_string} - {request.track.name}"
            score = fuzz.token_sort_ratio(
                normalize_text(button_text),
                normalize_text(spotify_full)
            )

            if self.debug_mode:
                print(f"{Fore.MAGENTA}  Button match: {score:.0f}% - {spotify_full}{Style.RESET_ALL}")

            if score > best_score:
                best_score = score
                best_match = request
                best_request_id = request_id

        if best_score >= TelegramConstants.CONFIDENCE_THRESHOLD and best_match:
            del self.pending_responses[best_request_id]
            return best_match

        # Single pending request — no ambiguity
        if len(self.pending_responses) == 1:
            return self._find_matching_request_unlocked()

        # Multiple requests, low confidence — don't guess
        if self.debug_mode:
            print(f"{Fore.YELLOW}→ No confident button match among {len(self.pending_responses)} pending "
                  f"(best: {best_score:.0f}%){Style.RESET_ALL}")
        return None

    def _find_request_by_reply_id_unlocked(self, reply_to_msg_id: int) -> Optional[PendingRequest]:
        """
        Find pending request by the message ID it replies to.

        The bot replies to our original message, so we can match exactly
        by checking which pending request has that message_id.

        Note: Must be called while holding self._pending_lock.
        """
        for request_id, request in self.pending_responses.items():
            if request.message_id == reply_to_msg_id:
                del self.pending_responses[request_id]
                return request
        return None

    async def _handle_button_response(self, event):
        """Handle button responses from bot (track options)"""
        # Check if this is a confirmation/download message (photo + buttons)
        # These should not consume pending requests from track selection
        if isinstance(event.message.media, MessageMediaPhoto):
            await self._handle_download_confirmation(event)
            return

        # Try matching by reply-to message ID first (most reliable)
        reply_to_msg_id = None
        if event.message.reply_to:
            reply_to_msg_id = event.message.reply_to.reply_to_msg_id

        async with self._pending_lock:
            matched_request = None

            # Method 1: Match by reply-to message ID (exact)
            if reply_to_msg_id:
                matched_request = self._find_request_by_reply_id_unlocked(reply_to_msg_id)
                if matched_request and self.debug_mode:
                    print(f"{Fore.MAGENTA}DEBUG: Matched by reply_to_msg_id {reply_to_msg_id}{Style.RESET_ALL}")

            # Method 2: Content-based matching (fallback)
            if not matched_request:
                button_text = self._extract_button_text(event)
                if button_text and len(self.pending_responses) > 1:
                    matched_request = self._find_best_matching_request_by_text_unlocked(button_text)
                else:
                    matched_request = self._find_matching_request_unlocked()

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
                async with self._pending_lock:
                    self.pending_responses[new_key] = new_request

        except Exception as e:
            print(f"{Fore.RED}Error clicking button for {track_name}: {e}{Style.RESET_ALL}")
            if self.on_download_failed:
                await self.on_download_failed(matched_request.track, f"Failed to select track option: {e}")
    
    async def _handle_download_confirmation(self, event):
        """
        Handle download confirmation messages (photo + buttons).

        The bot sends these after track selection with a "💾 Скачать страницу"
        button. We should NOT consume a track selection pending request here.
        Instead, click the download button if present.
        """
        # Look for the download button (Скачать = download)
        download_clicked = False
        if event.message.buttons:
            for row_idx, row in enumerate(event.message.buttons):
                buttons = row if isinstance(row, list) else [row]
                for btn_idx, btn in enumerate(buttons):
                    if hasattr(btn, 'text') and btn.text and 'скачать' in btn.text.lower():
                        try:
                            await event.message.click(data=btn.data if hasattr(btn, 'data') else None)
                            if self.debug_mode:
                                self._clear_print(f"{Fore.MAGENTA}DEBUG: Clicked download button: {btn.text}{Style.RESET_ALL}")
                            download_clicked = True
                        except Exception as e:
                            if self.debug_mode:
                                print(f"{Fore.MAGENTA}DEBUG: Error clicking download button: {e}{Style.RESET_ALL}")
                        break
                if download_clicked:
                    break

        if not download_clicked and self.debug_mode:
            button_text = self._extract_button_text(event)
            print(f"{Fore.MAGENTA}DEBUG: Confirmation message with no download button. Buttons: {button_text}{Style.RESET_ALL}")

    async def _handle_nothing_found_response(self, event):
        """Handle 'nothing found' image responses from bot"""
        # Try reply-to matching first, then FIFO
        reply_to_msg_id = None
        if event.message.reply_to:
            reply_to_msg_id = event.message.reply_to.reply_to_msg_id

        async with self._pending_lock:
            matched_request = None
            if reply_to_msg_id:
                matched_request = self._find_request_by_reply_id_unlocked(reply_to_msg_id)
            if not matched_request:
                matched_request = self._find_matching_request_unlocked()

        if not matched_request:
            if self.debug_mode:
                print(f"{Fore.MAGENTA}DEBUG: Received image but no matching request found. Pending: {len(self.pending_responses)}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Received image but no matching request found{Style.RESET_ALL}")
            # Try to clean up any orphaned requests
            async with self._pending_lock:
                self._cleanup_orphaned_requests_unlocked()
            return

        track = matched_request.track
        track_name = matched_request.track_name

        # Log that track was not found
        self._clear_print(f"{Fore.YELLOW}⚠ Track not available: {track_name}{Style.RESET_ALL}")

        # Ensure the request is removed from pending responses
        # (should already be done in _find_matching_request, but double-check)
        if self.debug_mode:
            print(f"{Fore.MAGENTA}DEBUG: Pending responses after nothing found: {len(self.pending_responses)}{Style.RESET_ALL}")

        # Notify about unavailable track
        if self.on_download_failed:
            await self.on_download_failed(track, "Track not found by bot")

        # Clean up any orphaned requests after failure
        async with self._pending_lock:
            self._cleanup_orphaned_requests_unlocked()
    
    async def _handle_file_response(self, event):
        """Handle file responses from bot"""
        # Extract filename and metadata for smart matching
        filename, metadata = self._extract_filename_and_metadata(event.message.document, "unknown")

        # Find matching pending request using smart content-based matching (thread-safe)
        async with self._pending_lock:
            matched_request = self._find_best_matching_request_unlocked(filename, metadata)

        if not matched_request:
            print(f"{Fore.YELLOW}Received file '{filename}' but no matching request found{Style.RESET_ALL}")
            # Clean up any orphaned pending responses that might match this file
            async with self._pending_lock:
                self._cleanup_orphaned_requests_unlocked()
            return

        track = matched_request.track
        track_name = matched_request.track_name

        # Notify about file reception with smart match info
        self._clear_print(f"{Fore.CYAN}Received file for: {track_name} → {filename}{Style.RESET_ALL}")

        # Handle the download directly
        if self.on_file_downloaded:
            await self.on_file_downloaded(event.message, filename, track, track_name)
    
    def _find_matching_request_unlocked(self) -> Optional[PendingRequest]:
        """
        Find matching pending request (FIFO approach).

        Note: Must be called while holding self._pending_lock.
        """
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
    
    def _calculate_track_similarity(self, bot_filename: str, bot_metadata: Dict,
                                      spotify_artist: str, spotify_title: str) -> float:
        """
        Calculate similarity score between bot response and Spotify track.

        Uses weighted scoring across filename, performer, and title matching.
        """
        scores = []

        spotify_artist_clean = normalize_text(spotify_artist)
        spotify_title_clean = normalize_text(spotify_title)
        spotify_full = f"{spotify_artist_clean} - {spotify_title_clean}"

        # Score 1: Filename vs full track name (most reliable)
        if bot_filename:
            # Strip bot-added artifacts (track number prefix, hash suffix) before matching
            bot_filename_stripped = strip_bot_artifacts(bot_filename)
            bot_filename_clean = normalize_text(bot_filename_stripped)
            filename_score = fuzz.token_sort_ratio(bot_filename_clean, spotify_full)
            scores.append(('filename', filename_score, MatchingWeights.FILENAME_WEIGHT))

            # Also try just the title part
            title_score = fuzz.token_sort_ratio(bot_filename_clean, spotify_title_clean)
            scores.append(('filename_title', title_score, MatchingWeights.FILENAME_TITLE_WEIGHT))

        # Score 2: Audio metadata performer vs Spotify artist
        if bot_metadata.get('performer'):
            performer_clean = normalize_text(bot_metadata['performer'])
            performer_score = fuzz.token_sort_ratio(performer_clean, spotify_artist_clean)
            scores.append(('performer', performer_score, MatchingWeights.PERFORMER_WEIGHT))

        # Score 3: Audio metadata title vs Spotify title
        if bot_metadata.get('title'):
            title_clean = normalize_text(bot_metadata['title'])
            title_score = fuzz.token_sort_ratio(title_clean, spotify_title_clean)
            scores.append(('title', title_score, MatchingWeights.TITLE_WEIGHT))

        # Calculate weighted average
        if not scores:
            return 0.0

        total_weighted = sum(score * weight for _, score, weight in scores)
        total_weight = sum(weight for _, _, weight in scores)

        return total_weighted / total_weight if total_weight > 0 else 0.0
    
    def _find_best_matching_request_unlocked(self, bot_filename: str, bot_metadata: Dict) -> Optional[PendingRequest]:
        """
        Find best matching request using content similarity.

        Note: Must be called while holding self._pending_lock.
        """
        # Clean up expired requests first
        self._cleanup_expired_requests_unlocked()

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
        if best_score >= TelegramConstants.CONFIDENCE_THRESHOLD and best_match:
            if self.debug_mode:
                print(f"{Fore.GREEN}✓ Smart match: {best_score:.1f}% confidence{Style.RESET_ALL}")
            # Remove the matched request
            del self.pending_responses[best_request_id]
            return best_match

        # Only fall back to FIFO if there's exactly 1 pending request (no ambiguity)
        if len(self.pending_responses) == 1:
            if self.debug_mode:
                print(f"{Fore.YELLOW}→ Single pending request, using FIFO fallback (best score: {best_score:.1f}%){Style.RESET_ALL}")
            return self._find_matching_request_unlocked()

        # Multiple pending requests with low confidence — don't guess
        if self.debug_mode:
            print(f"{Fore.YELLOW}→ No confident match among {len(self.pending_responses)} pending requests "
                  f"(best score: {best_score:.1f}%). Skipping file.{Style.RESET_ALL}")
        self._clear_print(f"{Fore.YELLOW}⚠ Could not match file '{bot_filename}' to any pending track "
                          f"(best: {best_score:.0f}% confidence){Style.RESET_ALL}")
        return None
    
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
        """
        Send track URL to external bot with rate limiting.

        Args:
            track: The track to send to the bot

        Returns:
            True if message was sent successfully, False otherwise
        """
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

                # Track pending response with unique key including track ID (thread-safe)
                request_key = f"msg_{message.id}_{track.id[:8]}"
                async with self._pending_lock:
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
                timeout=self.config.response_timeout  # Use configurable timeout
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
    
    async def flush_pending_for_tracks(self, track_ids: set[str]) -> int:
        """
        Remove pending requests for specific track IDs.

        Called between batches to prevent stale requests from polluting
        the next batch's response matching.

        Returns number of flushed requests.
        """
        async with self._pending_lock:
            to_remove = [
                msg_id for msg_id, request in self.pending_responses.items()
                if request.track.id in track_ids
            ]
            for msg_id in to_remove:
                del self.pending_responses[msg_id]
            if to_remove and self.debug_mode:
                print(f"{Fore.YELLOW}Flushed {len(to_remove)} stale pending requests from previous batch{Style.RESET_ALL}")
            return len(to_remove)

    async def get_pending_count(self) -> int:
        """Get number of pending responses (thread-safe)"""
        async with self._pending_lock:
            self._cleanup_expired_requests_unlocked()
            return len(self.pending_responses)

    def _cleanup_expired_requests_unlocked(self) -> None:
        """
        Clean up expired pending requests.

        Note: Must be called while holding self._pending_lock.
        """
        cutoff_time = datetime.now() - timedelta(seconds=self.config.response_timeout)
        expired_ids = [
            msg_id for msg_id, request in self.pending_responses.items()
            if request.sent_at <= cutoff_time
        ]

        if expired_ids and self.debug_mode:
            print(f"{Fore.YELLOW}Cleaning up {len(expired_ids)} expired requests{Style.RESET_ALL}")

        for msg_id in expired_ids:
            del self.pending_responses[msg_id]

    def _cleanup_orphaned_requests_unlocked(self) -> None:
        """
        Clean up orphaned requests that might be causing issues.

        Note: Must be called while holding self._pending_lock.
        """
        if len(self.pending_responses) > TelegramConstants.MAX_PENDING_REQUESTS:
            # Keep only the most recent requests
            sorted_requests = sorted(
                self.pending_responses.items(),
                key=lambda x: x[1].sent_at,
                reverse=True
            )

            # Clear all and keep only recent ones
            self.pending_responses.clear()
            for msg_id, request in sorted_requests[:TelegramConstants.KEEP_RECENT_REQUESTS]:
                self.pending_responses[msg_id] = request

            if self.debug_mode:
                print(f"{Fore.YELLOW}Cleaned up orphaned requests, keeping "
                      f"{TelegramConstants.KEEP_RECENT_REQUESTS} most recent{Style.RESET_ALL}")
    
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

        pending_count = await self.get_pending_count()
        while pending_count > 0 and (time.time() - start_time) < timeout_seconds:
            self._clear_print(f"{Fore.YELLOW}Waiting for {pending_count} pending responses...{Style.RESET_ALL}")
            await asyncio.sleep(5)
            pending_count = await self.get_pending_count()

        remaining = await self.get_pending_count()
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