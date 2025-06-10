#!/usr/bin/env python3
"""
File Manager Module

Handles file operations including:
- Download management and organization
- Filename sanitization and collision handling
- Directory structure creation
- Duplicate detection
- Metadata preservation
"""

import re
import hashlib
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime

from .spotify_api import Track


@dataclass
class FileConfig:
    """Configuration for file management"""
    download_folder: str = "./downloads"
    organize_by_artist: bool = True
    organize_by_album: bool = False
    create_year_folders: bool = False
    max_filename_length: int = 200
    preserve_original_filename: bool = False
    allowed_extensions: List[str] = None
    
    def __post_init__(self):
        if self.allowed_extensions is None:
            self.allowed_extensions = ['.flac', '.mp3', '.wav', '.m4a', '.ogg']


@dataclass
class DownloadResult:
    """Result of a download operation"""
    success: bool
    filepath: Optional[Path] = None
    error_message: Optional[str] = None
    file_size: int = 0
    duration: float = 0.0
    already_exists: bool = False


class FileManager:
    """Manages file downloads and organization"""
    
    def __init__(self, config: FileConfig):
        self.config = config
        self.download_folder = Path(config.download_folder)
        self.download_folder.mkdir(exist_ok=True, parents=True)
        
        # Statistics
        self.download_stats = {
            'total_downloaded': 0,
            'total_size_bytes': 0,
            'duplicates_skipped': 0,
            'errors': 0
        }
    
    @staticmethod
    def sanitize_filename(filename: str, max_length: int = 200) -> str:
        """Sanitize filename for safe file system use"""
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '')
        
        # Replace multiple spaces with single space
        filename = re.sub(r'\s+', ' ', filename)
        
        # Remove leading/trailing dots and spaces
        filename = filename.strip('. ')
        
        # Limit length while preserving extension
        if len(filename) > max_length:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            max_name_length = max_length - len(ext) - 1 if ext else max_length
            filename = name[:max_name_length].rstrip()
            if ext:
                filename += f'.{ext}'
        
        # Ensure filename is not empty
        if not filename or filename in ['.', '..']:
            filename = 'untitled'
        
        return filename
    
    def get_organized_path(self, track: Track, filename: str) -> Path:
        """Get the organized file path based on configuration"""
        base_path = self.download_folder
        
        # Clean up data for folder names
        artist_name = self.sanitize_filename(track.artists[0] if track.artists else "Unknown Artist", 50)
        album_name = self.sanitize_filename(track.album, 50) if track.album else "Unknown Album"
        
        # Extract year from release date if available
        year = ""
        if track.release_date:
            try:
                year = track.release_date.split('-')[0]
            except:
                pass
        
        # Build path based on organization settings
        if self.config.organize_by_artist:
            base_path = base_path / artist_name
            
            if self.config.organize_by_album:
                album_folder = f"{album_name}"
                if year and self.config.create_year_folders:
                    album_folder = f"{year} - {album_name}"
                base_path = base_path / album_folder
            elif year and self.config.create_year_folders:
                base_path = base_path / year
        
        # Create directory if it doesn't exist
        base_path.mkdir(parents=True, exist_ok=True)
        
        return base_path / filename
    
    def generate_filename(self, track: Track, original_filename: Optional[str] = None) -> str:
        """Generate filename for track"""
        if self.config.preserve_original_filename and original_filename:
            return self.sanitize_filename(original_filename, self.config.max_filename_length)
        
        # Generate filename from track metadata
        artist_part = ", ".join(track.artists) if track.artists else "Unknown Artist"
        track_name = track.name or "Unknown Track"
        
        # Create filename: "Artist - Track Name.ext"
        base_filename = f"{artist_part} - {track_name}"
        
        # Determine extension from original filename or default to .flac
        extension = ".flac"
        if original_filename:
            original_path = Path(original_filename)
            if original_path.suffix.lower() in self.config.allowed_extensions:
                extension = original_path.suffix.lower()
        
        filename = f"{base_filename}{extension}"
        return self.sanitize_filename(filename, self.config.max_filename_length)
    
    def check_file_exists(self, track: Track, original_filename: Optional[str] = None) -> Optional[Path]:
        """Check if file already exists, return path if found"""
        filename = self.generate_filename(track, original_filename)
        filepath = self.get_organized_path(track, filename)
        
        # Check exact match
        if filepath.exists():
            return filepath
        
        # Check for files with same track ID in download history
        # This would require integration with progress tracker
        return None
    
    def get_download_path(self, track: Track, original_filename: Optional[str] = None) -> Path:
        """Get the full download path for a track"""
        filename = self.generate_filename(track, original_filename)
        return self.get_organized_path(track, filename)
    
    def handle_filename_collision(self, filepath: Path) -> Path:
        """Handle filename collisions by adding numeric suffix"""
        if not filepath.exists():
            return filepath
        
        base_path = filepath.parent
        name_stem = filepath.stem
        extension = filepath.suffix
        
        counter = 1
        while True:
            new_name = f"{name_stem} ({counter}){extension}"
            new_path = base_path / new_name
            
            if not new_path.exists():
                return new_path
            
            counter += 1
            
            # Safety check to prevent infinite loop
            if counter > 1000:
                # Use timestamp as last resort
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                new_name = f"{name_stem}_{timestamp}{extension}"
                return base_path / new_name
    
    def validate_file(self, filepath: Path, min_size_bytes: int = 1024) -> bool:
        """Validate downloaded file"""
        if not filepath.exists():
            return False
        
        # Check file size
        if filepath.stat().st_size < min_size_bytes:
            return False
        
        # Check file extension
        if filepath.suffix.lower() not in self.config.allowed_extensions:
            return False
        
        # Additional validation could include:
        # - Audio file format validation
        # - Duration checks
        # - Corruption detection
        
        return True
    
    def move_to_organized_location(self, temp_path: Path, track: Track, 
                                 original_filename: Optional[str] = None) -> DownloadResult:
        """Move file from temporary location to organized location"""
        try:
            # Generate final path
            final_path = self.get_download_path(track, original_filename)
            
            # Handle filename collisions
            if final_path.exists():
                # Check if it's the same file (by size and content hash)
                if self._files_are_identical(temp_path, final_path):
                    temp_path.unlink()  # Remove temp file
                    self.download_stats['duplicates_skipped'] += 1
                    return DownloadResult(
                        success=True,
                        filepath=final_path,
                        already_exists=True,
                        file_size=final_path.stat().st_size
                    )
                else:
                    # Different file with same name
                    final_path = self.handle_filename_collision(final_path)
            
            # Move file to final location
            final_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.rename(final_path)
            
            # Validate the moved file
            if not self.validate_file(final_path):
                final_path.unlink()
                self.download_stats['errors'] += 1
                return DownloadResult(
                    success=False,
                    error_message="File validation failed after move"
                )
            
            # Update statistics
            file_size = final_path.stat().st_size
            self.download_stats['total_downloaded'] += 1
            self.download_stats['total_size_bytes'] += file_size
            
            return DownloadResult(
                success=True,
                filepath=final_path,
                file_size=file_size
            )
            
        except Exception as e:
            self.download_stats['errors'] += 1
            return DownloadResult(
                success=False,
                error_message=f"Error moving file: {e}"
            )
    
    def _files_are_identical(self, path1: Path, path2: Path) -> bool:
        """Check if two files are identical by size and hash"""
        try:
            # Quick size check first
            if path1.stat().st_size != path2.stat().st_size:
                return False
            
            # Hash comparison for smaller files
            if path1.stat().st_size < 50 * 1024 * 1024:  # 50MB
                return self._get_file_hash(path1) == self._get_file_hash(path2)
            
            # For larger files, assume they're different if sizes match
            # (to avoid long hash computation)
            return True
            
        except Exception:
            return False
    
    def _get_file_hash(self, filepath: Path, chunk_size: int = 8192) -> str:
        """Get MD5 hash of file"""
        hasher = hashlib.md5()
        
        with open(filepath, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        
        return hasher.hexdigest()
    
    def cleanup_temp_files(self, temp_dir: Optional[Path] = None):
        """Clean up temporary files"""
        if temp_dir is None:
            temp_dir = self.download_folder / "temp"
        
        if temp_dir.exists():
            for temp_file in temp_dir.glob("*"):
                try:
                    if temp_file.is_file():
                        temp_file.unlink()
                except Exception as e:
                    print(f"Warning: Could not clean up {temp_file}: {e}")
    
    def get_stats(self) -> Dict:
        """Get download statistics"""
        stats = self.download_stats.copy()
        
        # Add human-readable size
        size_mb = stats['total_size_bytes'] / (1024 * 1024)
        stats['total_size_mb'] = round(size_mb, 2)
        
        return stats
    
    def get_downloaded_files(self) -> List[Path]:
        """Get list of all downloaded files"""
        files = []
        
        for ext in self.config.allowed_extensions:
            files.extend(self.download_folder.rglob(f"*{ext}"))
        
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    
    def find_duplicates(self) -> List[Tuple[Path, Path]]:
        """Find potential duplicate files based on filename similarity"""
        files = self.get_downloaded_files()
        duplicates = []
        
        for i, file1 in enumerate(files):
            for file2 in files[i+1:]:
                # Compare normalized filenames
                name1 = self._normalize_filename(file1.stem)
                name2 = self._normalize_filename(file2.stem)
                
                # Check similarity (simple string matching)
                if self._similarity_ratio(name1, name2) > 0.9:
                    duplicates.append((file1, file2))
        
        return duplicates
    
    def _normalize_filename(self, filename: str) -> str:
        """Normalize filename for duplicate detection"""
        # Convert to lowercase
        filename = filename.lower()
        
        # Remove common patterns
        patterns_to_remove = [
            r'\s*\([^)]*\)\s*',  # Remove parentheses content
            r'\s*\[[^\]]*\]\s*',  # Remove brackets content
            r'\s*-\s*copy\s*',    # Remove "copy" indicators
            r'\s+',               # Normalize whitespace
        ]
        
        for pattern in patterns_to_remove:
            filename = re.sub(pattern, ' ', filename)
        
        return filename.strip()
    
    def _similarity_ratio(self, str1: str, str2: str) -> float:
        """Calculate similarity ratio between two strings"""
        # Simple implementation - could use more sophisticated algorithms
        if str1 == str2:
            return 1.0
        
        # Calculate Jaccard similarity
        set1 = set(str1.split())
        set2 = set(str2.split())
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0.0


def create_file_manager(download_folder: str = "./downloads", **kwargs) -> FileManager:
    """Factory function to create FileManager instance"""
    config = FileConfig(download_folder=download_folder, **kwargs)
    return FileManager(config)


if __name__ == "__main__":
    # Example usage
    from .spotify_api import Track
    
    # Create test track
    track = Track(
        id="test123",
        name="Test Song",
        artists=["Test Artist", "Featured Artist"],
        album="Test Album",
        url="https://open.spotify.com/track/test123",
        duration_ms=210000,
        release_date="2023-01-15"
    )
    
    # Create file manager
    file_manager = create_file_manager(
        download_folder="./test_downloads",
        organize_by_artist=True,
        organize_by_album=True,
        create_year_folders=True
    )
    
    # Test filename generation
    filename = file_manager.generate_filename(track, "original_file.flac")
    print(f"Generated filename: {filename}")
    
    # Test organized path
    path = file_manager.get_organized_path(track, filename)
    print(f"Organized path: {path}")
    
    # Show stats
    print(f"Stats: {file_manager.get_stats()}")