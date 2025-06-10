#!/usr/bin/env python3
"""
Progress Tracker Module

Handles progress tracking and session management including:
- Session state persistence
- Download progress tracking
- Resume capability
- Statistics and reporting
- Error tracking and retry logic
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

from .spotify_api import Track


class TrackStatus(Enum):
    """Status of track processing"""
    PENDING = "pending"
    SENT_TO_BOT = "sent_to_bot"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TrackProgress:
    """Progress information for a single track"""
    track_id: str
    track_name: str
    track_url: str
    status: TrackStatus
    attempts: int = 0
    last_attempt: Optional[str] = None
    error_message: Optional[str] = None
    file_path: Optional[str] = None
    file_size: int = 0
    download_time: float = 0.0
    sent_to_bot_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class SessionProgress:
    """Progress information for entire session"""
    session_id: str
    playlist_url: str
    playlist_name: str
    total_tracks: int
    started_at: str
    last_updated: str
    completed_at: Optional[str] = None
    tracks: Dict[str, TrackProgress] = None
    
    def __post_init__(self):
        if self.tracks is None:
            self.tracks = {}


class ProgressTracker:
    """Manages progress tracking and session persistence"""
    
    def __init__(self, progress_file: str = "progress.json"):
        self.progress_file = Path(progress_file)
        self.current_session: Optional[SessionProgress] = None
        
        # Statistics
        self._stats_cache = None
        self._stats_last_updated = 0
    
    def start_session(self, playlist_url: str, playlist_name: str, tracks: List[Track]) -> str:
        """Start a new download session"""
        session_id = self._generate_session_id()
        
        self.current_session = SessionProgress(
            session_id=session_id,
            playlist_url=playlist_url,
            playlist_name=playlist_name,
            total_tracks=len(tracks),
            started_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            tracks={}
        )
        
        # Initialize track progress
        for track in tracks:
            track_progress = TrackProgress(
                track_id=track.id,
                track_name=f"{track.artist_string} - {track.name}",
                track_url=track.url,
                status=TrackStatus.PENDING
            )
            self.current_session.tracks[track.id] = track_progress
        
        self.save_progress()
        return session_id
    
    def load_session(self, session_id: Optional[str] = None) -> Optional[SessionProgress]:
        """Load existing session from file"""
        if not self.progress_file.exists():
            return None
        
        try:
            with open(self.progress_file, 'r') as f:
                data = json.load(f)
            
            # Handle legacy format or find specific session
            if session_id:
                # Look for specific session (future enhancement)
                session_data = data  # For now, assume single session
            else:
                # Load most recent session
                session_data = data
            
            # Convert tracks dict to TrackProgress objects
            tracks = {}
            for track_id, track_data in session_data.get('tracks', {}).items():
                track_data['status'] = TrackStatus(track_data['status'])
                tracks[track_id] = TrackProgress(**track_data)
            
            session_data['tracks'] = tracks
            self.current_session = SessionProgress(**session_data)
            
            return self.current_session
            
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            print(f"Warning: Could not load progress file: {e}")
            return None
    
    def save_progress(self):
        """Save current session progress to file"""
        if not self.current_session:
            return
        
        self.current_session.last_updated = datetime.now().isoformat()
        
        # Convert to dict for JSON serialization
        session_dict = asdict(self.current_session)
        
        # Convert TrackProgress objects and enums to dicts
        tracks_dict = {}
        for track_id, track_progress in self.current_session.tracks.items():
            track_dict = asdict(track_progress)
            track_dict['status'] = track_progress.status.value
            tracks_dict[track_id] = track_dict
        
        session_dict['tracks'] = tracks_dict
        
        try:
            # Atomic write to prevent corruption
            temp_file = self.progress_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(session_dict, f, indent=2)
            
            temp_file.rename(self.progress_file)
            
        except Exception as e:
            print(f"Warning: Could not save progress: {e}")
    
    def update_track_status(self, track_id: str, status: TrackStatus, 
                          error_message: Optional[str] = None,
                          file_path: Optional[str] = None,
                          file_size: int = 0):
        """Update status of a specific track"""
        if not self.current_session or track_id not in self.current_session.tracks:
            return
        
        track = self.current_session.tracks[track_id]
        old_status = track.status
        
        # Update status
        track.status = status
        track.last_attempt = datetime.now().isoformat()
        
        # Increment attempt counter for retries
        if status == TrackStatus.FAILED:
            track.attempts += 1
            track.error_message = error_message
        elif status == TrackStatus.COMPLETED:
            track.completed_at = datetime.now().isoformat()
            track.file_path = file_path
            track.file_size = file_size
            track.error_message = None
        elif status == TrackStatus.SENT_TO_BOT:
            track.sent_to_bot_at = datetime.now().isoformat()
        
        self.save_progress()
        self._invalidate_stats_cache()
    
    def mark_track_sent(self, track_id: str):
        """Mark track as sent to bot"""
        self.update_track_status(track_id, TrackStatus.SENT_TO_BOT)
    
    def mark_track_downloading(self, track_id: str):
        """Mark track as currently downloading"""
        self.update_track_status(track_id, TrackStatus.DOWNLOADING)
    
    def mark_track_completed(self, track_id: str, file_path: str, file_size: int = 0):
        """Mark track as successfully completed"""
        self.update_track_status(
            track_id, 
            TrackStatus.COMPLETED, 
            file_path=file_path,
            file_size=file_size
        )
    
    def mark_track_failed(self, track_id: str, error_message: str):
        """Mark track as failed"""
        self.update_track_status(track_id, TrackStatus.FAILED, error_message=error_message)
    
    def mark_track_skipped(self, track_id: str, reason: str):
        """Mark track as skipped"""
        self.update_track_status(track_id, TrackStatus.SKIPPED, error_message=reason)
    
    def get_tracks_by_status(self, status: TrackStatus) -> List[TrackProgress]:
        """Get all tracks with specific status"""
        if not self.current_session:
            return []
        
        return [
            track for track in self.current_session.tracks.values()
            if track.status == status
        ]
    
    def get_pending_tracks(self) -> List[TrackProgress]:
        """Get tracks that still need processing"""
        return self.get_tracks_by_status(TrackStatus.PENDING)
    
    def get_failed_tracks(self) -> List[TrackProgress]:
        """Get tracks that failed processing"""
        return self.get_tracks_by_status(TrackStatus.FAILED)
    
    def get_completed_tracks(self) -> List[TrackProgress]:
        """Get successfully completed tracks"""
        return self.get_tracks_by_status(TrackStatus.COMPLETED)
    
    def get_retryable_tracks(self, max_attempts: int = 3) -> List[TrackProgress]:
        """Get failed tracks that can be retried"""
        failed_tracks = self.get_failed_tracks()
        return [track for track in failed_tracks if track.attempts < max_attempts]
    
    def get_session_stats(self) -> Dict:
        """Get comprehensive session statistics"""
        # Use cache if recent
        current_time = time.time()
        if (self._stats_cache and 
            current_time - self._stats_last_updated < 5):  # 5 second cache
            return self._stats_cache
        
        if not self.current_session:
            return {}
        
        tracks = self.current_session.tracks.values()
        
        # Count by status
        status_counts = {}
        for status in TrackStatus:
            status_counts[status.value] = len(self.get_tracks_by_status(status))
        
        # Calculate completion percentage
        total = self.current_session.total_tracks
        completed = status_counts[TrackStatus.COMPLETED.value]
        failed = status_counts[TrackStatus.FAILED.value]
        skipped = status_counts[TrackStatus.SKIPPED.value]
        processed = completed + failed + skipped
        
        completion_percentage = (processed / total * 100) if total > 0 else 0
        success_rate = (completed / processed * 100) if processed > 0 else 0
        
        # Calculate total download size
        total_size = sum(
            track.file_size for track in tracks 
            if track.status == TrackStatus.COMPLETED and track.file_size > 0
        )
        
        # Calculate session duration
        started = datetime.fromisoformat(self.current_session.started_at)
        if self.current_session.completed_at:
            ended = datetime.fromisoformat(self.current_session.completed_at)
        else:
            ended = datetime.now()
        
        duration = ended - started
        
        stats = {
            'session_id': self.current_session.session_id,
            'playlist_name': self.current_session.playlist_name,
            'total_tracks': total,
            'completed': completed,
            'failed': failed,
            'skipped': skipped,
            'pending': status_counts[TrackStatus.PENDING.value],
            'sent_to_bot': status_counts[TrackStatus.SENT_TO_BOT.value],
            'downloading': status_counts[TrackStatus.DOWNLOADING.value],
            'processed': processed,
            'completion_percentage': round(completion_percentage, 1),
            'success_rate': round(success_rate, 1),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'session_duration': str(duration).split('.')[0],  # Remove microseconds
            'started_at': self.current_session.started_at,
            'last_updated': self.current_session.last_updated,
            'completed_at': self.current_session.completed_at,
            'is_completed': processed == total
        }
        
        # Cache the results
        self._stats_cache = stats
        self._stats_last_updated = current_time
        
        return stats
    
    def complete_session(self):
        """Mark session as completed"""
        if self.current_session:
            self.current_session.completed_at = datetime.now().isoformat()
            self.save_progress()
            self._invalidate_stats_cache()
    
    def reset_progress(self):
        """Reset all progress data"""
        if self.progress_file.exists():
            self.progress_file.unlink()
        
        self.current_session = None
        self._invalidate_stats_cache()
    
    def get_resume_info(self) -> Optional[Dict]:
        """Get information about resumable session"""
        session = self.load_session()
        if not session:
            return None
        
        stats = self.get_session_stats()
        
        if stats['is_completed']:
            return None  # Session already completed
        
        return {
            'session_id': session.session_id,
            'playlist_name': session.playlist_name,
            'playlist_url': session.playlist_url,
            'total_tracks': session.total_tracks,
            'pending_count': stats['pending'],
            'failed_count': stats['failed'],
            'completed_count': stats['completed'],
            'started_at': session.started_at,
            'can_resume': stats['pending'] > 0 or stats['failed'] > 0
        }
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"session_{timestamp}"
    
    def _invalidate_stats_cache(self):
        """Invalidate statistics cache"""
        self._stats_cache = None
        self._stats_last_updated = 0
    
    def export_report(self, output_file: Optional[str] = None) -> str:
        """Export detailed progress report"""
        if not self.current_session:
            return "No active session to report on."
        
        stats = self.get_session_stats()
        
        report_lines = [
            "=" * 60,
            f"SPOTIFY DOWNLOADER PROGRESS REPORT",
            "=" * 60,
            f"Session ID: {stats['session_id']}",
            f"Playlist: {stats['playlist_name']}",
            f"Started: {stats['started_at']}",
            f"Duration: {stats['session_duration']}",
            "",
            "SUMMARY:",
            f"  Total Tracks: {stats['total_tracks']}",
            f"  Completed: {stats['completed']} ({stats['success_rate']:.1f}%)",
            f"  Failed: {stats['failed']}",
            f"  Skipped: {stats['skipped']}",
            f"  Pending: {stats['pending']}",
            f"  Overall Progress: {stats['completion_percentage']:.1f}%",
            f"  Total Size: {stats['total_size_mb']} MB",
            "",
        ]
        
        # Add failed tracks details
        failed_tracks = self.get_failed_tracks()
        if failed_tracks:
            report_lines.extend([
                "FAILED TRACKS:",
                "-" * 40
            ])
            for track in failed_tracks[:10]:  # Show first 10
                report_lines.append(f"  {track.track_name}")
                report_lines.append(f"    Error: {track.error_message}")
                report_lines.append(f"    Attempts: {track.attempts}")
                report_lines.append("")
        
        report = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report)
        
        return report


def create_progress_tracker(progress_file: str = "progress.json") -> ProgressTracker:
    """Factory function to create ProgressTracker instance"""
    return ProgressTracker(progress_file)


if __name__ == "__main__":
    # Example usage
    from .spotify_api import Track
    
    # Create test tracks
    tracks = [
        Track(
            id="track1",
            name="Test Song 1",
            artists=["Artist 1"],
            album="Test Album",
            url="https://open.spotify.com/track/track1",
            duration_ms=180000
        ),
        Track(
            id="track2", 
            name="Test Song 2",
            artists=["Artist 2"],
            album="Test Album",
            url="https://open.spotify.com/track/track2",
            duration_ms=210000
        )
    ]
    
    # Create progress tracker
    tracker = create_progress_tracker("test_progress.json")
    
    # Start session
    session_id = tracker.start_session(
        "https://open.spotify.com/playlist/test",
        "Test Playlist",
        tracks
    )
    
    print(f"Started session: {session_id}")
    
    # Simulate progress
    tracker.mark_track_sent("track1")
    tracker.mark_track_completed("track1", "/downloads/artist1-song1.flac", 5000000)
    tracker.mark_track_failed("track2", "Bot did not respond")
    
    # Show stats
    stats = tracker.get_session_stats()
    print(f"Progress: {stats['completion_percentage']:.1f}%")
    print(f"Success rate: {stats['success_rate']:.1f}%")
    
    # Generate report
    report = tracker.export_report()
    print(report)