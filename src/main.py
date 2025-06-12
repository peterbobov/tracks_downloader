#!/usr/bin/env python3
"""
Main Orchestrator Module

Coordinates all components to provide the complete download workflow:
- Integrates Spotify API, Telegram client, file manager, and progress tracker
- Provides high-level interface for download operations
- Handles batch processing and error recovery
- Manages the complete download lifecycle
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass

from colorama import init, Fore, Style
from dotenv import load_dotenv

from .spotify_api import SpotifyExtractor, Track, create_spotify_extractor
from .telegram_client import TelegramMessenger, TelegramConfig, create_telegram_messenger
from .file_manager import FileManager, FileConfig, create_file_manager
from .progress_tracker import ProgressTracker, TrackStatus, create_progress_tracker

# Initialize colorama
init()


@dataclass
class DownloadConfig:
    """Configuration for download operations"""
    # Spotify settings
    spotify_client_id: str
    spotify_client_secret: str
    
    # Telegram settings
    telegram_api_id: int
    telegram_api_hash: str
    telegram_phone_number: str
    external_bot_username: str
    
    # Download settings
    download_folder: str = "./downloads"
    delay_between_requests: float = 3.0
    max_retries: int = 3
    batch_size: int = 10
    response_timeout: int = 60
    
    # File organization
    organize_by_artist: bool = True
    organize_by_album: bool = False
    create_year_folders: bool = False
    
    # Session management
    progress_file: str = "progress.json"
    session_dir: str = "./sessions"
    
    @classmethod
    def from_env(cls, dry_run: bool = False) -> 'DownloadConfig':
        """Create config from environment variables"""
        load_dotenv()
        
        # For dry run, only Spotify credentials are required
        if dry_run:
            spotify_vars = ['SPOTIFY_CLIENT_ID', 'SPOTIFY_CLIENT_SECRET']
            missing_spotify = [var for var in spotify_vars if not os.getenv(var)]
            if missing_spotify:
                raise ValueError(f"Missing required Spotify variables: {', '.join(missing_spotify)}")
            
            # Return config with dummy Telegram values for dry run
            return cls(
                spotify_client_id=os.getenv('SPOTIFY_CLIENT_ID'),
                spotify_client_secret=os.getenv('SPOTIFY_CLIENT_SECRET'),
                telegram_api_id=12345,  # Dummy value
                telegram_api_hash="dummy_hash",  # Dummy value
                telegram_phone_number="+1234567890",  # Dummy value
                external_bot_username="@dummy_bot",  # Dummy value
                download_folder=os.getenv('DOWNLOAD_FOLDER', './downloads'),
                delay_between_requests=float(os.getenv('DELAY_BETWEEN_REQUESTS', 3.0)),
                max_retries=int(os.getenv('MAX_RETRIES', 3)),
                response_timeout=int(os.getenv('RESPONSE_TIMEOUT', 60)),
            )
        
        # For actual download, all credentials are required
        required_vars = [
            'SPOTIFY_CLIENT_ID', 'SPOTIFY_CLIENT_SECRET',
            'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 
            'TELEGRAM_PHONE_NUMBER', 'EXTERNAL_BOT_USERNAME'
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return cls(
            spotify_client_id=os.getenv('SPOTIFY_CLIENT_ID'),
            spotify_client_secret=os.getenv('SPOTIFY_CLIENT_SECRET'),
            telegram_api_id=int(os.getenv('TELEGRAM_API_ID')),
            telegram_api_hash=os.getenv('TELEGRAM_API_HASH'),
            telegram_phone_number=os.getenv('TELEGRAM_PHONE_NUMBER'),
            external_bot_username=os.getenv('EXTERNAL_BOT_USERNAME'),
            download_folder=os.getenv('DOWNLOAD_FOLDER', './downloads'),
            delay_between_requests=float(os.getenv('DELAY_BETWEEN_REQUESTS', 3.0)),
            max_retries=int(os.getenv('MAX_RETRIES', 3)),
            response_timeout=int(os.getenv('RESPONSE_TIMEOUT', 60)),
        )


class SpotifyDownloader:
    """Main orchestrator class that coordinates all components"""
    
    def __init__(self, config: DownloadConfig):
        self.config = config
        
        # Initialize components
        self.spotify = create_spotify_extractor(
            config.spotify_client_id,
            config.spotify_client_secret
        )
        
        self.telegram_config = TelegramConfig(
            api_id=config.telegram_api_id,
            api_hash=config.telegram_api_hash,
            phone_number=config.telegram_phone_number,
            bot_username=config.external_bot_username,
            session_dir=config.session_dir,
            delay_between_requests=config.delay_between_requests,
            max_retries=config.max_retries,
            response_timeout=config.response_timeout
        )
        
        self.file_manager = create_file_manager(
            download_folder=config.download_folder,
            organize_by_artist=config.organize_by_artist,
            organize_by_album=config.organize_by_album,
            create_year_folders=config.create_year_folders
        )
        
        self.progress_tracker = create_progress_tracker(config.progress_file)
        
        # Runtime components (initialized during operation)
        self.telegram: Optional[TelegramMessenger] = None
        self.current_session_id: Optional[str] = None
        
        # Debug mode
        self.debug_mode = False
        
        # Progress tracking to avoid duplicates
        self.last_batch_progress_message = ""
        
        # Callbacks for progress reporting
        self.on_track_sent: Optional[Callable] = None
        self.on_track_downloaded: Optional[Callable] = None
        self.on_track_failed: Optional[Callable] = None
    
    def _clear_print(self, message: str):
        """Print message after clearing any download progress line"""
        print(f"\r{' ' * 80}\r{message}")
    
    async def initialize(self) -> bool:
        """Initialize all components"""
        print(f"{Fore.CYAN}Initializing Spotify Downloader...{Style.RESET_ALL}")
        
        try:
            # Initialize Telegram client
            self.telegram = TelegramMessenger(self.telegram_config)
            
            if not await self.telegram.initialize():
                return False
            
            # Set debug mode on telegram client
            self.telegram.debug_mode = self.debug_mode
            
            # Set up Telegram callbacks
            self.telegram.set_callbacks(
                on_file_downloaded=self._handle_file_downloaded,
                on_download_failed=self._handle_download_failed,
                on_bot_response=self._handle_bot_response
            )
            
            print(f"{Fore.GREEN}✓ All components initialized successfully{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            print(f"{Fore.RED}Initialization failed: {e}{Style.RESET_ALL}")
            return False
    
    async def download_playlist(self, playlist_url: str, 
                              dry_run: bool = False,
                              batch_size: Optional[int] = None,
                              resume: bool = True,
                              limit: Optional[int] = None,
                              sequential: bool = False,
                              start_from: int = 1) -> Dict:
        """Download all tracks from a Spotify playlist"""
        
        # Check for resumable session
        if resume:
            resume_info = self.progress_tracker.get_resume_info()
            if resume_info and resume_info['can_resume']:
                print(f"{Fore.YELLOW}Found resumable session:{Style.RESET_ALL}")
                print(f"  Playlist: {resume_info['playlist_name']}")
                print(f"  Progress: {resume_info['completed_count']}/{resume_info['total_tracks']} completed")
                print(f"  Pending: {resume_info['pending_count']} tracks")
                
                if input(f"{Fore.CYAN}Resume previous session? (y/n): {Style.RESET_ALL}").lower() == 'y':
                    return await self._resume_session(dry_run, batch_size, limit, sequential, start_from)
        
        # Start new session
        return await self._start_new_session(playlist_url, dry_run, batch_size, limit, sequential, start_from)
    
    async def _start_new_session(self, playlist_url: str, dry_run: bool, batch_size: Optional[int], limit: Optional[int], sequential: bool, start_from: int) -> Dict:
        """Start a new download session"""
        try:
            # Get playlist info and tracks
            print(f"{Fore.CYAN}Fetching playlist information...{Style.RESET_ALL}")
            
            playlist_info = self.spotify.get_playlist_info(playlist_url)
            if not playlist_info:
                return {"success": False, "error": "Could not fetch playlist information"}
            
            tracks = self.spotify.extract_tracks(playlist_url)
            if not tracks:
                return {"success": False, "error": "No tracks found in playlist"}
            
            # Apply start_from offset (convert from 1-based to 0-based index)
            start_index = max(0, start_from - 1)
            if start_index >= len(tracks):
                return {"success": False, "error": f"Start position {start_from} is beyond playlist length ({len(tracks)} tracks)"}
            
            original_track_count = len(tracks)
            tracks = tracks[start_index:]
            
            if start_from > 1:
                print(f"\n{Fore.YELLOW}Starting from track #{start_from} ({original_track_count - len(tracks)} tracks skipped){Style.RESET_ALL}")
            
            # Apply limit if specified
            if limit and limit > 0:
                tracks = tracks[:limit]
                print(f"{Fore.YELLOW}Limiting to {limit} tracks{Style.RESET_ALL}")
            
            # Display playlist info
            print(f"\n{Fore.CYAN}Playlist: {playlist_info['name']}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Owner: {playlist_info['owner']}{Style.RESET_ALL}")
            if start_from > 1 or (limit and limit > 0):
                print(f"{Fore.CYAN}Processing tracks {start_from}-{start_from + len(tracks) - 1} of {original_track_count} total{Style.RESET_ALL}")
            else:
                print(f"{Fore.CYAN}Tracks: {len(tracks)}{Style.RESET_ALL}")
            
            # Set playlist name for file organization
            self.file_manager.set_playlist_name(playlist_info['name'])
            
            if dry_run:
                return self._dry_run_report(tracks)
            
            # Security confirmation
            if not self._confirm_download(len(tracks), batch_size):
                return {"success": False, "error": "Download cancelled by user"}
            
            # Start progress tracking
            self.current_session_id = self.progress_tracker.start_session(
                playlist_url, playlist_info['name'], tracks
            )
            
            # Process tracks
            return await self._process_tracks(tracks, batch_size or self.config.batch_size, sequential)
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _resume_session(self, dry_run: bool, batch_size: Optional[int], limit: Optional[int], sequential: bool, start_from: int) -> Dict:
        """Resume an existing session"""
        session = self.progress_tracker.load_session()
        if not session:
            return {"success": False, "error": "No session to resume"}
        
        self.current_session_id = session.session_id
        
        # Get pending tracks
        pending_tracks = self.progress_tracker.get_pending_tracks()
        retryable_tracks = self.progress_tracker.get_retryable_tracks()
        
        all_processable = pending_tracks + retryable_tracks
        
        # Apply limit if specified
        if limit and limit > 0:
            all_processable = all_processable[:limit]
            print(f"\n{Fore.YELLOW}Limiting to first {limit} tracks{Style.RESET_ALL}")
        
        if not all_processable:
            print(f"{Fore.GREEN}Session already completed!{Style.RESET_ALL}")
            return {"success": True, "message": "Session already completed"}
        
        print(f"{Fore.CYAN}Resuming session with {len(all_processable)} tracks{Style.RESET_ALL}")
        
        if dry_run:
            track_objects = []
            for track_progress in all_processable:
                track = Track(
                    id=track_progress.track_id,
                    name=track_progress.track_name.split(' - ', 1)[-1],
                    artists=[track_progress.track_name.split(' - ', 1)[0]],
                    album="",
                    url=track_progress.track_url,
                    duration_ms=0
                )
                track_objects.append(track)
            return self._dry_run_report(track_objects)
        
        # Convert track progress back to Track objects for processing
        tracks_to_process = []
        for track_progress in all_processable:
            # Reset failed tracks for retry
            if track_progress.status == TrackStatus.FAILED:
                self.progress_tracker.update_track_status(
                    track_progress.track_id, 
                    TrackStatus.PENDING
                )
            
            # Create minimal Track object for processing
            track = Track(
                id=track_progress.track_id,
                name=track_progress.track_name.split(' - ', 1)[-1],
                artists=[track_progress.track_name.split(' - ', 1)[0]],
                album="",
                url=track_progress.track_url,
                duration_ms=0
            )
            tracks_to_process.append(track)
        
        return await self._process_tracks(tracks_to_process, batch_size or self.config.batch_size, sequential)
    
    def _dry_run_report(self, tracks: List[Track]) -> Dict:
        """Generate dry run report"""
        print(f"\n{Fore.YELLOW}DRY RUN MODE - No messages will be sent{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Would process {len(tracks)} tracks:{Style.RESET_ALL}\n")
        
        for i, track in enumerate(tracks[:20], 1):  # Show first 20
            print(f"{i:3d}. {track.artist_string} - {track.name}")
        
        if len(tracks) > 20:
            print(f"     ... and {len(tracks) - 20} more tracks")
        
        return {
            "success": True,
            "dry_run": True,
            "total_tracks": len(tracks),
            "tracks_shown": min(20, len(tracks))
        }
    
    def _confirm_download(self, track_count: int, batch_size: Optional[int]) -> bool:
        """Get user confirmation for download"""
        effective_batch_size = batch_size or self.config.batch_size
        
        print(f"\n{Fore.YELLOW}Security Notice:{Style.RESET_ALL}")
        print(f"- Messages will be sent from your personal Telegram account")
        print(f"- {self.config.delay_between_requests}s delay between messages")
        print(f"- Processing in batches of {effective_batch_size}")
        print(f"- Session stored securely in: {self.config.session_dir}")
        print(f"- Total tracks to process: {track_count}")
        
        response = input(f"\n{Fore.CYAN}Continue? (yes/no): {Style.RESET_ALL}")
        return response.lower() in ['yes', 'y']
    
    async def _process_tracks(self, tracks: List[Track], batch_size: int, sequential: bool = False) -> Dict:
        """Process tracks in batches"""
        total_tracks = len(tracks)
        successful = 0
        failed = 0
        
        print(f"\n{Fore.CYAN}Starting download process...{Style.RESET_ALL}")
        
        # Process in batches
        for batch_start in range(0, total_tracks, batch_size):
            batch_end = min(batch_start + batch_size, total_tracks)
            batch = tracks[batch_start:batch_end]
            batch_num = (batch_start // batch_size) + 1
            total_batches = (total_tracks + batch_size - 1) // batch_size
            
            print(f"\n{Fore.CYAN}Processing batch {batch_num}/{total_batches} ({batch_start + 1}-{batch_end} of {total_tracks}){Style.RESET_ALL}")
            
            if sequential:
                # Process tracks one by one for cleaner progress display
                for i, track in enumerate(batch):
                    global_index = batch_start + i + 1
                    
                    # Skip if already completed
                    if self._is_track_completed(track.id):
                        print(f"{Fore.YELLOW}[{global_index}/{total_tracks}] Already completed, skipping{Style.RESET_ALL}")
                        successful += 1
                        continue
                    
                    print(f"\n{Fore.CYAN}[{global_index}/{total_tracks}] Processing: {track.artist_string} - {track.name}{Style.RESET_ALL}")
                    
                    # Send to bot
                    if await self.telegram.send_track_to_bot(track):
                        self.progress_tracker.mark_track_sent(track.id)
                        if self.on_track_sent:
                            await self.on_track_sent(track, global_index, total_tracks)
                        
                        # Wait for this specific track to complete before moving to next
                        print(f"{Fore.YELLOW}Waiting for track to complete...{Style.RESET_ALL}")
                        await self._wait_for_track_completion(track.id, timeout=300)
                        
                        # Check if it completed successfully
                        if self._is_track_completed(track.id):
                            successful += 1
                            print(f"{Fore.GREEN}✓ Track completed successfully{Style.RESET_ALL}")
                        else:
                            failed += 1
                            print(f"{Fore.RED}✗ Track failed or timed out{Style.RESET_ALL}")
                    else:
                        failed += 1
                        self.progress_tracker.mark_track_failed(track.id, "Failed to send to bot")
                        if self.on_track_failed:
                            await self.on_track_failed(track, "Failed to send to bot")
            else:
                # Process tracks in parallel (original behavior)
                for i, track in enumerate(batch):
                    global_index = batch_start + i + 1
                    
                    # Skip if already completed
                    if self._is_track_completed(track.id):
                        print(f"{Fore.YELLOW}[{global_index}/{total_tracks}] Already completed, skipping{Style.RESET_ALL}")
                        successful += 1
                        continue
                    
                    print(f"\n{Fore.CYAN}[{global_index}/{total_tracks}] Sending: {track.artist_string} - {track.name}{Style.RESET_ALL}")
                    
                    # Send to bot
                    if await self.telegram.send_track_to_bot(track):
                        self.progress_tracker.mark_track_sent(track.id)
                        if self.on_track_sent:
                            await self.on_track_sent(track, global_index, total_tracks)
                    else:
                        failed += 1
                        self.progress_tracker.mark_track_failed(track.id, "Failed to send to bot")
                        if self.on_track_failed:
                            await self.on_track_failed(track, "Failed to send to bot")
                
                # Wait for ALL tracks in this batch to complete before next batch
                if batch_end < total_tracks:
                    self._clear_print(f"{Fore.YELLOW}Waiting for batch to complete before processing next batch...{Style.RESET_ALL}")
                    await self._wait_for_batch_completion(batch, timeout=600)  # 10 minutes for batch
        
        # Wait for final responses and downloads to complete
        print(f"\n{Fore.YELLOW}Waiting for remaining bot responses...{Style.RESET_ALL}")
        
        # Wait longer and check for downloads more frequently
        total_wait_time = 0
        max_wait_time = 300  # 5 minutes total
        
        while total_wait_time < max_wait_time:
            # Wait for responses
            pending_responses = self.telegram.get_pending_count()
            
            # Check for incomplete tracks (sent_to_bot, downloading, etc.)
            session = self.progress_tracker.current_session
            incomplete_tracks = []
            if session:
                incomplete_tracks = [
                    track for track in session.tracks.values() 
                    if track.status not in [TrackStatus.COMPLETED, TrackStatus.FAILED]
                ]
            
            if pending_responses == 0 and len(incomplete_tracks) == 0:
                print(f"{Fore.GREEN}All responses and downloads completed{Style.RESET_ALL}")
                break
            
            if pending_responses > 0:
                print(f"{Fore.YELLOW}Waiting for {pending_responses} pending responses...{Style.RESET_ALL}")
            
            if len(incomplete_tracks) > 0:
                # Show what we're waiting for
                waiting_for_bot = len([t for t in incomplete_tracks if t.status == TrackStatus.SENT_TO_BOT])
                downloading = len([t for t in incomplete_tracks if t.status == TrackStatus.DOWNLOADING])
                
                if waiting_for_bot > 0:
                    print(f"{Fore.YELLOW}Waiting for {waiting_for_bot} bot responses...{Style.RESET_ALL}")
                if downloading > 0:
                    print(f"{Fore.YELLOW}Waiting for {downloading} downloads to complete...{Style.RESET_ALL}")
            
            await asyncio.sleep(5)
            total_wait_time += 5
        
        if total_wait_time >= max_wait_time:
            print(f"{Fore.RED}Timeout reached after {max_wait_time} seconds{Style.RESET_ALL}")
        
        # Complete session
        self.progress_tracker.complete_session()
        
        # Generate final report
        return self._generate_final_report()
    
    def _is_track_completed(self, track_id: str) -> bool:
        """Check if track is already completed"""
        if not self.current_session_id:
            return False
        
        session = self.progress_tracker.current_session
        if not session or track_id not in session.tracks:
            return False
        
        return session.tracks[track_id].status == TrackStatus.COMPLETED
    
    async def _wait_for_track_completion(self, track_id: str, timeout: int = 300):
        """Wait for a specific track to complete"""
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            session = self.progress_tracker.current_session
            if not session or track_id not in session.tracks:
                break
            
            track_status = session.tracks[track_id].status
            
            # Check if track is completed or failed
            if track_status in [TrackStatus.COMPLETED, TrackStatus.FAILED]:
                break
            
            await asyncio.sleep(2)  # Check every 2 seconds
        
        return self._is_track_completed(track_id)
    
    async def _wait_for_batch_completion(self, batch_tracks: List[Track], timeout: int = 600):
        """Wait for all tracks in a batch to complete (success, fail, or not found)"""
        start_time = time.time()
        batch_track_ids = [track.id for track in batch_tracks]
        
        while (time.time() - start_time) < timeout:
            session = self.progress_tracker.current_session
            if not session:
                break
            
            # Check status of all tracks in this batch
            incomplete_tracks = []
            for track_id in batch_track_ids:
                if track_id in session.tracks:
                    track_status = session.tracks[track_id].status
                    # Track is incomplete if it's still being processed
                    if track_status not in [TrackStatus.COMPLETED, TrackStatus.FAILED]:
                        incomplete_tracks.append(track_id)
            
            if not incomplete_tracks:
                print(f"{Fore.GREEN}✓ Batch completed - all tracks processed{Style.RESET_ALL}")
                break
            
            # Show progress (only if different from last message)
            completed_count = len(batch_track_ids) - len(incomplete_tracks)
            progress_message = f"Batch progress: {completed_count}/{len(batch_track_ids)} tracks completed"
            
            if progress_message != self.last_batch_progress_message:
                print(f"\r{' ' * 80}\r{Fore.YELLOW}{progress_message}{Style.RESET_ALL}")
                self.last_batch_progress_message = progress_message
            
            await asyncio.sleep(5)  # Check every 5 seconds
        
        # Final status check
        session = self.progress_tracker.current_session
        if session:
            final_incomplete = []
            for track_id in batch_track_ids:
                if track_id in session.tracks:
                    track_status = session.tracks[track_id].status
                    if track_status not in [TrackStatus.COMPLETED, TrackStatus.FAILED]:
                        final_incomplete.append(track_id)
            
            if final_incomplete:
                print(f"{Fore.RED}Warning: {len(final_incomplete)} tracks in batch did not complete within timeout{Style.RESET_ALL}")
                # Show which tracks are stuck and their status
                for track_id in final_incomplete:
                    if track_id in session.tracks:
                        track_progress = session.tracks[track_id]
                        print(f"{Fore.RED}  - Stuck track: {track_progress.track_name} (Status: {track_progress.status.value}){Style.RESET_ALL}")
                # Mark them as failed due to timeout
                for track_id in final_incomplete:
                    self.progress_tracker.mark_track_failed(track_id, "Batch timeout")
    
    
    async def _handle_file_downloaded(self, message, filename: str, track: Track, track_name: str):
        """Handle file downloaded from Telegram"""
        self._clear_print(f"{Fore.CYAN}Processing downloaded file: {filename}{Style.RESET_ALL}")
        
        if self.debug_mode:
            print(f"{Fore.MAGENTA}DEBUG: Marking track {track.id} as downloading{Style.RESET_ALL}")
        
        # Update progress immediately
        self.progress_tracker.mark_track_downloading(track.id)
        
        if self.debug_mode:
            print(f"{Fore.MAGENTA}DEBUG: Track marked as downloading{Style.RESET_ALL}")
        
        try:
            # Generate organized file path
            final_path = self.file_manager.get_download_path(track, filename)
            
            # Download file from Telegram
            temp_path = Path(self.config.download_folder) / "temp" / filename
            temp_path.parent.mkdir(exist_ok=True, parents=True)
            
            download_success = await self.telegram.download_file(message, temp_path)
            
            if self.debug_mode:
                print(f"{Fore.MAGENTA}DEBUG: Download success: {download_success}{Style.RESET_ALL}")
            
            if download_success:
                # Move to organized location
                result = self.file_manager.move_to_organized_location(temp_path, track, filename)
                
                if result.success:
                    self.progress_tracker.mark_track_completed(
                        track.id, 
                        str(result.filepath), 
                        result.file_size
                    )
                    self._clear_print(f"{Fore.GREEN}✓ Downloaded: {result.filepath.name} ({result.file_size:,} bytes){Style.RESET_ALL}")
                    
                    if self.on_track_downloaded:
                        await self.on_track_downloaded(track, result.filepath)
                else:
                    error_msg = result.error_message or "Failed to organize file"
                    print(f"{Fore.RED}Failed to organize file: {error_msg}{Style.RESET_ALL}")
                    self.progress_tracker.mark_track_failed(track.id, error_msg)
                    if self.on_track_failed:
                        await self.on_track_failed(track, error_msg)
            else:
                error_msg = "Failed to download from Telegram"
                print(f"{Fore.RED}{error_msg}{Style.RESET_ALL}")
                self.progress_tracker.mark_track_failed(track.id, error_msg)
                if self.on_track_failed:
                    await self.on_track_failed(track, error_msg)
                
        except Exception as e:
            error_msg = f"Error processing download: {e}"
            print(f"{Fore.RED}{error_msg}{Style.RESET_ALL}")
            self.progress_tracker.mark_track_failed(track.id, error_msg)
            if self.on_track_failed:
                await self.on_track_failed(track, error_msg)
    
    async def _handle_download_failed(self, track: Track, error_message: str):
        """Handle download failure"""
        self._clear_print(f"{Fore.RED}Download failed: {track.artist_string} - {track.name}{Style.RESET_ALL}")
        print(f"{Fore.RED}Error: {error_message}{Style.RESET_ALL}")
        
        self.progress_tracker.mark_track_failed(track.id, error_message)
        
        if self.on_track_failed:
            await self.on_track_failed(track, error_message)
    
    async def _handle_bot_response(self, text: str):
        """Handle text responses from bot"""
        print(f"{Fore.YELLOW}Bot: {text}{Style.RESET_ALL}")
    
    def _generate_final_report(self) -> Dict:
        """Generate final download report"""
        stats = self.progress_tracker.get_session_stats()
        file_stats = self.file_manager.get_stats()
        
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}DOWNLOAD COMPLETE{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Completed: {stats['completed']}/{stats['total_tracks']} ({stats['success_rate']:.1f}%){Style.RESET_ALL}")
        print(f"{Fore.RED}Failed: {stats['failed']}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Skipped: {stats['skipped']}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Total Size: {stats['total_size_mb']} MB{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Session Duration: {stats['session_duration']}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Progress saved to: {self.config.progress_file}{Style.RESET_ALL}")
        
        return {
            "success": True,
            "stats": stats,
            "file_stats": file_stats
        }
    
    def get_status(self) -> Dict:
        """Get current download status"""
        return self.progress_tracker.get_session_stats()
    
    def reset_progress(self):
        """Reset all progress data"""
        self.progress_tracker.reset_progress()
        self.current_session_id = None
    
    def export_report(self, output_file: Optional[str] = None) -> str:
        """Export detailed progress report"""
        return self.progress_tracker.export_report(output_file)
    
    async def cleanup(self):
        """Clean up all resources"""
        if self.telegram:
            await self.telegram.cleanup()
        
        # Clean up temporary files
        self.file_manager.cleanup_temp_files()
    
    def set_progress_callbacks(self, 
                             on_track_sent: Optional[Callable] = None,
                             on_track_downloaded: Optional[Callable] = None,
                             on_track_failed: Optional[Callable] = None):
        """Set progress callback functions"""
        self.on_track_sent = on_track_sent
        self.on_track_downloaded = on_track_downloaded  
        self.on_track_failed = on_track_failed
    
    def set_debug_mode(self, enabled: bool):
        """Enable or disable debug logging"""
        self.debug_mode = enabled
        if self.telegram:
            self.telegram.debug_mode = enabled


async def create_downloader(config: Optional[DownloadConfig] = None) -> SpotifyDownloader:
    """Factory function to create and initialize SpotifyDownloader"""
    if config is None:
        config = DownloadConfig.from_env()
    
    downloader = SpotifyDownloader(config)
    
    if await downloader.initialize():
        return downloader
    else:
        raise RuntimeError("Failed to initialize downloader")


if __name__ == "__main__":
    async def main():
        try:
            config = DownloadConfig.from_env()
            downloader = await create_downloader(config)
            
            # Example usage
            playlist_url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
            result = await downloader.download_playlist(playlist_url, dry_run=True)
            
            print(f"Result: {result}")
            
        except Exception as e:
            print(f"Error: {e}")
        finally:
            if 'downloader' in locals():
                await downloader.cleanup()
    
    asyncio.run(main())