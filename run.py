#!/usr/bin/env python3
"""
Spotify Downloader - Entry Point Script

Command-line interface for the modular Spotify downloader.
Provides easy-to-use commands for downloading playlists, checking status,
and managing download sessions.
"""

import sys
import asyncio
import argparse
from pathlib import Path
from typing import Optional

from colorama import init, Fore, Style

# Add src to path to import modules
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.main import SpotifyDownloader, DownloadConfig, create_downloader

# Initialize colorama
init()


def print_banner():
    """Print application banner"""
    banner = f"""
{Fore.CYAN}┌─────────────────────────────────────────────────────────────┐
│                    Spotify Track Downloader                 │
│                     Modular Architecture                    │
└─────────────────────────────────────────────────────────────┘{Style.RESET_ALL}

{Fore.YELLOW}Features:{Style.RESET_ALL}
✓ Secure Telegram integration with Telethon
✓ Intelligent file organization and naming
✓ Progress tracking and resume capability
✓ Rate limiting and flood protection
✓ Batch processing for large playlists
✓ Comprehensive error handling and reporting

{Fore.YELLOW}Security:{Style.RESET_ALL}
✓ Local session storage with proper permissions
✓ No credentials stored in plain text
✓ Conservative rate limiting to protect your account
✓ Secure API credential management
"""
    print(banner)


def print_help():
    """Print detailed help information"""
    help_text = f"""
{Fore.CYAN}USAGE:{Style.RESET_ALL}
  python run.py <playlist_url> [options]
  python run.py <command> [options]

{Fore.CYAN}COMMANDS:{Style.RESET_ALL}
  download <url>     Download tracks from Spotify playlist/album
  status             Show current download progress
  reset              Reset all progress data
  report [file]      Generate detailed progress report
  help               Show this help message

{Fore.CYAN}OPTIONS:{Style.RESET_ALL}
  --dry-run          Preview tracks without downloading
  --check-missing    Check which tracks are missing from download folder
  --batch-size N     Process N tracks at a time (default: 10)
  --limit N          Limit to first N tracks (for testing)
  --start-from N     Start from track number N (1-based, default: 1)
  --debug            Enable detailed debug logging
  --sequential       Process tracks one at a time (cleaner progress, slower)
  --no-resume        Don't resume previous session
  --organize-by      artist|album|none (default: artist)
  --year-folders     Create year-based folders
  --output-dir DIR   Set download directory

{Fore.CYAN}EXAMPLES:{Style.RESET_ALL}
  # Download a playlist
  python run.py https://open.spotify.com/playlist/xxxxx

  # Preview tracks without downloading
  python run.py https://open.spotify.com/playlist/xxxxx --dry-run

  # Process in smaller batches
  python run.py https://open.spotify.com/playlist/xxxxx --batch-size 5

  # Test with just first track
  python run.py https://open.spotify.com/playlist/xxxxx --limit 1

  # Enable debug logging
  python run.py https://open.spotify.com/playlist/xxxxx --debug

  # Sequential processing for cleaner progress
  python run.py https://open.spotify.com/playlist/xxxxx --sequential

  # Download tracks 16-30 (chunked processing)
  python run.py https://open.spotify.com/playlist/xxxxx --start-from 16 --limit 15
  
  # Check which tracks are missing from downloads
  python run.py https://open.spotify.com/playlist/xxxxx --check-missing
  
  # Download only missing tracks (with approval prompt)
  python run.py https://open.spotify.com/playlist/xxxxx --download-missing
  
  # Catalog existing music library
  python run.py --catalog-library --output-dir ./music

  # Download to specific directory with year folders
  python run.py https://open.spotify.com/playlist/xxxxx --output-dir ./music --year-folders

  # Check current progress
  python run.py status

  # Generate detailed report
  python run.py report downloads_report.txt

{Fore.CYAN}SETUP:{Style.RESET_ALL}
  1. Create .env file with your API credentials:
     SPOTIFY_CLIENT_ID=your_client_id
     SPOTIFY_CLIENT_SECRET=your_client_secret
     TELEGRAM_API_ID=your_api_id
     TELEGRAM_API_HASH=your_api_hash
     TELEGRAM_PHONE_NUMBER=+1234567890
     EXTERNAL_BOT_USERNAME=@your_bot

  2. First run will require Telegram authentication

{Fore.CYAN}SECURITY NOTES:{Style.RESET_ALL}
  • Uses your personal Telegram account to send messages
  • Session files are stored securely with proper permissions
  • Minimum 3-second delay between messages for account safety
  • All credentials should be stored in .env file (never commit this!)
  • Monitor your Telegram account for any unusual activity

{Fore.YELLOW}For detailed documentation, see: README.md{Style.RESET_ALL}
"""
    print(help_text)


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser"""
    parser = argparse.ArgumentParser(
        description="Spotify Track Downloader - Automated playlist downloading via Telegram",
        add_help=False
    )
    
    # Positional argument for URL or command
    parser.add_argument(
        'target',
        nargs='?',
        help='Spotify playlist/album URL or command (download, status, reset, report, help)'
    )
    
    # Download options
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview tracks without sending messages'
    )
    
    parser.add_argument(
        '--check-missing',
        action='store_true',
        help='Check which tracks are missing from download folder'
    )
    
    parser.add_argument(
        '--catalog-library',
        action='store_true',
        help='Scan music library and populate catalog database'
    )
    
    parser.add_argument(
        '--download-missing',
        action='store_true',
        help='Download only tracks that are missing from your library (with approval prompt)'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Number of tracks to process in each batch (default: 10)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of tracks to process (for testing)'
    )
    
    parser.add_argument(
        '--start-from',
        type=int,
        default=1,
        help='Track number to start from (1-based index, default: 1)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable detailed debug logging'
    )
    
    parser.add_argument(
        '--sequential',
        action='store_true',
        help='Process tracks one at a time (cleaner progress, slower)'
    )
    
    parser.add_argument(
        '--no-resume',
        action='store_true',
        help='Start fresh session instead of resuming'
    )
    
    # File organization options
    parser.add_argument(
        '--organize-by',
        choices=['artist', 'album', 'none'],
        default='artist',
        help='How to organize downloaded files (default: artist)'
    )
    
    parser.add_argument(
        '--year-folders',
        action='store_true',
        help='Create year-based folder structure'
    )
    
    parser.add_argument(
        '--output-dir',
        default='./downloads',
        help='Download directory (default: ./downloads)'
    )
    
    # Session management
    parser.add_argument(
        '--progress-file',
        default='progress.json',
        help='Progress tracking file (default: progress.json)'
    )
    
    # Other options
    parser.add_argument(
        '--help', '-h',
        action='store_true',
        help='Show detailed help message'
    )
    
    parser.add_argument(
        '--version',
        action='store_true',
        help='Show version information'
    )
    
    return parser


async def handle_download(args, config: DownloadConfig, url: str = None) -> int:
    """Handle download command"""
    # Use provided URL or get from args
    if not url:
        url = args.target
    
    if not url or url in ['download']:
        print(f"{Fore.RED}Error: Playlist URL required for download{Style.RESET_ALL}")
        print(f"Usage: python run.py <playlist_url> [options]")
        return 1
    
    # Handle 'download <url>' format
    if args.target == 'download' and len(sys.argv) > 2:
        url = sys.argv[2]
    
    if not url.startswith('https://open.spotify.com/'):
        print(f"{Fore.RED}Error: Invalid Spotify URL{Style.RESET_ALL}")
        print(f"URL should start with: https://open.spotify.com/")
        return 1
    
    # Check if this is a check-missing request
    if hasattr(args, 'check_missing') and args.check_missing:
        return await handle_check_missing(url, config)
    
    # Check if this is a download-missing request
    if hasattr(args, 'download_missing') and args.download_missing:
        return await handle_download_missing(args, config, url)
    
    try:
        # Update config based on arguments
        config.download_folder = args.output_dir
        config.organize_by_artist = args.organize_by == 'artist'
        config.organize_by_album = args.organize_by == 'album'
        config.create_year_folders = args.year_folders
        config.progress_file = args.progress_file
        
        # Create downloader (don't initialize Telegram for dry run)
        downloader = SpotifyDownloader(config)
        
        # Set debug mode if requested
        if hasattr(args, 'debug') and args.debug:
            downloader.set_debug_mode(True)
        
        # Only initialize Telegram if not dry run
        if not args.dry_run:
            if not await downloader.initialize():
                return {"success": False, "error": "Failed to initialize Telegram client"}
        
        try:
            # Start download
            result = await downloader.download_playlist(
                url,
                dry_run=args.dry_run,
                batch_size=args.batch_size,
                resume=not args.no_resume,
                limit=args.limit,
                sequential=args.sequential,
                start_from=args.start_from
            )
            
            if result['success']:
                if args.dry_run:
                    print(f"\n{Fore.GREEN}Dry run completed successfully{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.GREEN}Download completed successfully{Style.RESET_ALL}")
                return 0
            else:
                print(f"\n{Fore.RED}Download failed: {result.get('error', 'Unknown error')}{Style.RESET_ALL}")
                return 1
                
        finally:
            await downloader.cleanup()
    
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Download interrupted by user{Style.RESET_ALL}")
        if 'downloader' in locals():
            await downloader.cleanup()
        return 130
    
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        return 1


async def handle_status(config: DownloadConfig) -> int:
    """Handle status command"""
    try:
        downloader = SpotifyDownloader(config)
        status = downloader.get_status()
        
        if not status:
            print(f"{Fore.YELLOW}No active download session found{Style.RESET_ALL}")
            return 0
        
        print(f"\n{Fore.CYAN}Current Download Status:{Style.RESET_ALL}")
        print(f"  Session: {status['session_id']}")
        print(f"  Playlist: {status['playlist_name']}")
        print(f"  Progress: {status['completed']}/{status['total_tracks']} ({status['completion_percentage']}%)")
        print(f"  Success Rate: {status['success_rate']}%")
        print(f"  Failed: {status['failed']}")
        print(f"  Pending: {status['pending']}")
        print(f"  Total Size: {status['total_size_mb']} MB")
        print(f"  Duration: {status['session_duration']}")
        print(f"  Last Updated: {status['last_updated']}")
        
        if status['is_completed']:
            print(f"\n{Fore.GREEN}✓ Session completed{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}Session in progress...{Style.RESET_ALL}")
        
        return 0
        
    except Exception as e:
        print(f"{Fore.RED}Error getting status: {e}{Style.RESET_ALL}")
        return 1


async def handle_reset(config: DownloadConfig) -> int:
    """Handle reset command"""
    response = input(f"{Fore.YELLOW}This will delete all progress data and cached playlist data. Continue? (yes/no): {Style.RESET_ALL}")
    
    if response.lower() not in ['yes', 'y']:
        print("Reset cancelled.")
        return 0
    
    try:
        downloader = SpotifyDownloader(config)
        downloader.reset_progress()
        
        # Also clear Spotify API cache
        from pathlib import Path
        import shutil
        cache_dir = Path("./cache")
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            print(f"{Fore.GREEN}Spotify cache cleared{Style.RESET_ALL}")
        
        print(f"{Fore.GREEN}Progress data and cache reset successfully{Style.RESET_ALL}")
        return 0
        
    except Exception as e:
        print(f"{Fore.RED}Error resetting progress: {e}{Style.RESET_ALL}")
        return 1


async def handle_report(args, config: DownloadConfig) -> int:
    """Handle report command"""
    try:
        downloader = SpotifyDownloader(config)
        
        # Determine output file
        output_file = None
        if len(sys.argv) > 2 and not sys.argv[2].startswith('--'):
            output_file = sys.argv[2]
        
        report = downloader.export_report(output_file)
        
        if output_file:
            print(f"{Fore.GREEN}Report exported to: {output_file}{Style.RESET_ALL}")
        else:
            print(report)
        
        return 0
        
    except Exception as e:
        print(f"{Fore.RED}Error generating report: {e}{Style.RESET_ALL}")
        return 1


async def handle_catalog_library(args, config: DownloadConfig) -> int:
    """Handle catalog-library command"""
    try:
        from pathlib import Path
        
        # Import catalog module
        sys.path.insert(0, str(Path(__file__).parent / 'src'))
        from src.catalog import create_catalog
        
        # Get library path from config
        library_path = Path(config.music_library_path)
        if not library_path.exists():
            print(f"{Fore.RED}Error: Music library path does not exist: {library_path}{Style.RESET_ALL}")
            return 1
        
        print(f"{Fore.CYAN}Scanning music library: {library_path}{Style.RESET_ALL}")
        
        # Create catalog
        catalog = create_catalog()
        
        # Scan library
        added_count, error_count = catalog.scan_library(library_path)
        
        print(f"\n{Fore.GREEN}Library catalog completed:{Style.RESET_ALL}")
        print(f"  Added: {added_count} tracks")
        print(f"  Errors: {error_count} files")
        
        # Show catalog stats
        stats = catalog.get_stats()
        print(f"\n{Fore.CYAN}Catalog Statistics:{Style.RESET_ALL}")
        print(f"  Total tracks: {stats.total_tracks}")
        print(f"  Total size: {stats.total_size_gb:.2f} GB")
        print(f"  Unique artists: {stats.unique_artists}")
        print(f"  Unique albums: {stats.unique_albums}")
        print(f"  Playlists: {len(stats.playlists)}")
        
        if stats.playlists:
            print(f"  Playlist sources: {', '.join(stats.playlists[:5])}")
            if len(stats.playlists) > 5:
                print(f"    ... and {len(stats.playlists) - 5} more")
        
        if stats.file_formats:
            print(f"  File formats: {dict(stats.file_formats)}")
        
        return 0
        
    except ImportError as e:
        print(f"{Fore.RED}Error: Missing required library for catalog functionality{Style.RESET_ALL}")
        print(f"Install missing dependencies: pip install mutagen")
        return 1
    except Exception as e:
        print(f"{Fore.RED}Error cataloging library: {e}{Style.RESET_ALL}")
        return 1


async def handle_download_missing(args, config: DownloadConfig, url: str) -> int:
    """Handle download-missing command with verbose preview and user approval"""
    try:
        from fuzzywuzzy import fuzz
        from pathlib import Path
        
        # Import catalog module
        sys.path.insert(0, str(Path(__file__).parent / 'src'))
        from src.catalog import create_catalog
        
        print(f"{Fore.CYAN}🔍 Analyzing playlist to identify missing tracks...{Style.RESET_ALL}")
        
        # Create downloader (we need Spotify API to get tracks)
        downloader = SpotifyDownloader(config)
        
        # Extract tracks from Spotify
        tracks = downloader.spotify.extract_tracks(url)
        if not tracks:
            print(f"{Fore.RED}Error: Could not extract tracks from URL{Style.RESET_ALL}")
            return 1
        
        # Get playlist info for playlist name
        playlist_info = downloader.spotify.get_playlist_info(url)
        playlist_name = playlist_info['name'] if playlist_info else None
        
        print(f"{Fore.GREEN}Found {len(tracks)} tracks in playlist{Style.RESET_ALL}")
        if playlist_name:
            print(f"{Fore.CYAN}Playlist: {playlist_name}{Style.RESET_ALL}")
        
        # Get music library folder
        library_folder = Path(config.music_library_path)
        if not library_folder.exists():
            print(f"{Fore.RED}Error: Music library path does not exist: {library_folder}{Style.RESET_ALL}")
            return 1
        
        # Create catalog for database queries
        catalog = create_catalog()
        
        print(f"{Fore.YELLOW}Checking existing tracks...{Style.RESET_ALL}")
        
        missing_tracks = []
        found_tracks = []
        
        # If playlist name is available, check specific playlist folder
        playlist_folder = None
        if playlist_name:
            playlist_folder = library_folder / downloader.file_manager.sanitize_filename(playlist_name, 100)
        
        for i, track in enumerate(tracks, 1):
            expected_filename = f"{track.artist_string} - {track.name}"
            found = False
            
            # Check catalog database first
            catalog_track = catalog.find_track(track.name, track.artist_string)
            if catalog_track and Path(catalog_track.file_path).exists():
                found = True
                found_tracks.append(track)
                continue
            
            # If not in catalog, check folder scanning with fuzzy matching
            search_paths = [library_folder]
            if playlist_folder and playlist_folder.exists():
                search_paths.insert(0, playlist_folder)  # Check playlist folder first
            
            best_score = 0
            
            for search_path in search_paths:
                # Get all audio files in this path
                for ext in ['.flac', '.mp3', '.wav', '.m4a', '.ogg']:
                    for file_path in search_path.rglob(f"*{ext}"):
                        filename = file_path.stem  # Without extension
                        score = fuzz.ratio(expected_filename.lower(), filename.lower())
                        
                        if score > best_score:
                            best_score = score
                        
                        # If we find a very high match, consider it found
                        if score >= 90:
                            found = True
                            break
                    
                    if found:
                        break
                
                # If we found a good match in playlist folder, don't search library
                if found and search_path == playlist_folder:
                    break
            
            if found:
                found_tracks.append(track)
            else:
                missing_tracks.append(track)
        
        # Show analysis results
        print(f"\n{Fore.CYAN}📊 ANALYSIS RESULTS:{Style.RESET_ALL}")
        print(f"  Total tracks in playlist: {len(tracks)}")
        print(f"  Already in library: {len(found_tracks)} ({len(found_tracks)/len(tracks)*100:.1f}%)")
        print(f"  Missing tracks: {len(missing_tracks)} ({len(missing_tracks)/len(tracks)*100:.1f}%)")
        
        if not missing_tracks:
            print(f"\n{Fore.GREEN}🎉 All tracks are already in your library!{Style.RESET_ALL}")
            return 0
        
        # Show verbose information about what will be downloaded
        print(f"\n{Fore.YELLOW}📋 MISSING TRACKS TO DOWNLOAD:{Style.RESET_ALL}")
        
        # Show first 10 missing tracks with details
        for i, track in enumerate(missing_tracks[:10], 1):
            duration = f"{track.duration_ms // 60000}:{(track.duration_ms % 60000) // 1000:02d}" if track.duration_ms else "Unknown"
            print(f"  {i:2d}. {Fore.WHITE}{track.artist_string} - {track.name}{Style.RESET_ALL}")
            if track.album:
                print(f"      Album: {track.album} | Duration: {duration}")
            else:
                print(f"      Duration: {duration}")
        
        if len(missing_tracks) > 10:
            print(f"      ... and {len(missing_tracks) - 10} more tracks")
        
        # Show download details
        print(f"\n{Fore.CYAN}📥 DOWNLOAD DETAILS:{Style.RESET_ALL}")
        if playlist_name:
            destination_folder = f"{config.music_library_path}/{playlist_name}/"
            print(f"  Destination: {destination_folder}")
        else:
            print(f"  Destination: {config.music_library_path}/Unknown Playlist/")
        
        print(f"  File format: FLAC (high quality)")
        print(f"  Batch size: {args.batch_size} tracks at a time")
        print(f"  Processing mode: {'Sequential' if args.sequential else 'Parallel'}")
        print(f"  Rate limiting: {config.delay_between_requests}s between requests")
        
        # Estimate download time
        estimated_minutes = len(missing_tracks) * config.delay_between_requests / 60
        if args.sequential:
            estimated_minutes *= 1.5  # Sequential takes longer
        
        print(f"  Estimated time: ~{estimated_minutes:.0f} minutes")
        
        # Security warning
        print(f"\n{Fore.YELLOW}⚠️  SECURITY NOTICE:{Style.RESET_ALL}")
        print(f"  - Messages will be sent from your personal Telegram account")
        print(f"  - Conservative rate limiting protects your account")
        print(f"  - Progress will be saved and can be resumed if interrupted")
        
        # User approval prompt
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        response = input(f"{Fore.CYAN}📥 Download {len(missing_tracks)} missing tracks? (yes/no): {Style.RESET_ALL}").strip().lower()
        
        if response not in ['yes', 'y']:
            print(f"{Fore.YELLOW}Download cancelled by user{Style.RESET_ALL}")
            return 0
        
        print(f"\n{Fore.GREEN}🚀 Starting download of missing tracks...{Style.RESET_ALL}")
        
        # Initialize downloader for actual download
        if not await downloader.initialize():
            return 1
        
        # Set debug mode if requested
        if hasattr(args, 'debug') and args.debug:
            downloader.set_debug_mode(True)
        
        # Set playlist name for file organization
        if playlist_name:
            downloader.file_manager.set_playlist_name(playlist_name)
        
        try:
            # Create a custom session for missing tracks only
            session_id = downloader.progress_tracker.start_session(
                url, playlist_name or "Missing Tracks Download", missing_tracks
            )
            downloader.current_session_id = session_id
            
            # Process only the missing tracks
            result = await downloader._process_tracks(
                missing_tracks, 
                args.batch_size, 
                args.sequential
            )
            
            if result['success']:
                print(f"\n{Fore.GREEN}✅ Missing tracks download completed successfully!{Style.RESET_ALL}")
                
                # Show final summary
                stats = result.get('stats', {})
                if stats:
                    print(f"\n{Fore.CYAN}📊 DOWNLOAD SUMMARY:{Style.RESET_ALL}")
                    print(f"  Successfully downloaded: {stats.get('completed', 0)} tracks")
                    print(f"  Failed: {stats.get('failed', 0)} tracks")
                    print(f"  Total size: {stats.get('total_size_mb', 0)} MB")
                
                return 0
            else:
                print(f"\n{Fore.RED}❌ Download failed: {result.get('error', 'Unknown error')}{Style.RESET_ALL}")
                return 1
                
        finally:
            await downloader.cleanup()
    
    except ImportError as e:
        missing_lib = "fuzzywuzzy" if "fuzz" in str(e) else "mutagen"
        print(f"{Fore.RED}Error: {missing_lib} library required for download-missing command{Style.RESET_ALL}")
        if missing_lib == "fuzzywuzzy":
            print("Install it with: pip install fuzzywuzzy python-levenshtein")
        else:
            print("Install it with: pip install mutagen")
        return 1
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Download interrupted by user{Style.RESET_ALL}")
        if 'downloader' in locals():
            await downloader.cleanup()
        return 130
    except Exception as e:
        print(f"{Fore.RED}Error in download-missing: {e}{Style.RESET_ALL}")
        return 1


async def handle_check_missing(url: str, config: DownloadConfig) -> int:
    """Handle check-missing command using both catalog database and folder scanning"""
    try:
        from fuzzywuzzy import fuzz
        from pathlib import Path
        
        # Import catalog module
        sys.path.insert(0, str(Path(__file__).parent / 'src'))
        from src.catalog import create_catalog
        
        # Create downloader (we only need Spotify API, not Telegram)
        downloader = SpotifyDownloader(config)
        
        print(f"{Fore.CYAN}Fetching playlist tracks from Spotify...{Style.RESET_ALL}")
        
        # Extract tracks from Spotify
        tracks = downloader.spotify.extract_tracks(url)
        if not tracks:
            print(f"{Fore.RED}Error: Could not extract tracks from URL{Style.RESET_ALL}")
            return 1
        
        # Get playlist info for playlist name
        playlist_info = downloader.spotify.get_playlist_info(url)
        playlist_name = playlist_info['name'] if playlist_info else None
        
        print(f"{Fore.GREEN}Found {len(tracks)} tracks in playlist{Style.RESET_ALL}")
        if playlist_name:
            print(f"{Fore.CYAN}Playlist: {playlist_name}{Style.RESET_ALL}")
        
        # Get music library folder
        library_folder = Path(config.music_library_path)
        if not library_folder.exists():
            print(f"{Fore.RED}Error: Music library path does not exist: {library_folder}{Style.RESET_ALL}")
            return 1
        
        # Create catalog for database queries
        catalog = create_catalog()
        
        print(f"{Fore.YELLOW}Checking tracks using both catalog database and folder scanning...{Style.RESET_ALL}\n")
        
        missing_tracks = []
        found_tracks = []
        found_in_catalog = []
        found_in_folder = []
        
        # Prepare expected tracks list for catalog lookup
        expected_tracks = [(track.name, track.artist_string) for track in tracks]
        
        # Check catalog database first
        catalog_missing = catalog.get_missing_tracks(expected_tracks)
        catalog_missing_set = set(catalog_missing)
        
        # If playlist name is available, also check specific playlist folder
        playlist_folder = None
        if playlist_name:
            playlist_folder = library_folder / downloader.file_manager.sanitize_filename(playlist_name, 100)
        
        for i, track in enumerate(tracks, 1):
            expected_filename = f"{track.artist_string} - {track.name}"
            track_tuple = (track.name, track.artist_string)
            found_method = None
            found_location = None
            confidence = 0
            
            # Check catalog database first
            catalog_track = catalog.find_track(track.name, track.artist_string)
            if catalog_track and Path(catalog_track.file_path).exists():
                found_method = "catalog"
                found_location = catalog_track.file_path
                confidence = 100  # Exact match in catalog
                found_tracks.append({
                    'position': i,
                    'track': track,
                    'expected': expected_filename,
                    'found': Path(found_location).name,
                    'method': found_method,
                    'location': found_location,
                    'score': confidence
                })
                found_in_catalog.append(catalog_track)
                continue
            
            # If not in catalog, check folder scanning with fuzzy matching
            search_paths = [library_folder]
            if playlist_folder and playlist_folder.exists():
                search_paths.insert(0, playlist_folder)  # Check playlist folder first
            
            best_score = 0
            best_match = None
            best_location = None
            
            for search_path in search_paths:
                # Get all audio files in this path
                for ext in ['.flac', '.mp3', '.wav', '.m4a', '.ogg']:
                    for file_path in search_path.rglob(f"*{ext}"):
                        filename = file_path.stem  # Without extension
                        score = fuzz.ratio(expected_filename.lower(), filename.lower())
                        
                        if score > best_score:
                            best_score = score
                            best_match = filename
                            best_location = str(file_path)
                        
                        # If we find a very high match in playlist folder, prefer it
                        if score >= 95 and search_path == playlist_folder:
                            break
                
                # If we found a good match in playlist folder, don't search library
                if best_score >= 90 and search_path == playlist_folder:
                    break
            
            # 90% confidence threshold for folder matching
            if best_score >= 90:
                found_method = "folder"
                found_tracks.append({
                    'position': i,
                    'track': track,
                    'expected': expected_filename,
                    'found': best_match,
                    'method': found_method,
                    'location': best_location,
                    'score': best_score
                })
                found_in_folder.append({
                    'track': track,
                    'file_path': best_location,
                    'score': best_score
                })
            else:
                missing_tracks.append({
                    'position': i,
                    'track': track,
                    'expected': expected_filename,
                    'best_match': best_match,
                    'best_location': best_location,
                    'score': best_score
                })
        
        # Display results
        print(f"{Fore.GREEN}✓ FOUND TRACKS ({len(found_tracks)}/{len(tracks)}):{Style.RESET_ALL}")
        
        if found_in_catalog:
            print(f"\n{Fore.CYAN}  Found in catalog database ({len(found_in_catalog)}):{Style.RESET_ALL}")
            for found in [f for f in found_tracks if f['method'] == 'catalog'][:3]:
                print(f"    [{found['position']:3d}] {found['expected']} → {found['found']}")
            if len(found_in_catalog) > 3:
                print(f"    ... and {len(found_in_catalog) - 3} more in catalog")
        
        if found_in_folder:
            print(f"\n{Fore.CYAN}  Found by folder scanning ({len(found_in_folder)}):{Style.RESET_ALL}")
            for found in [f for f in found_tracks if f['method'] == 'folder'][:3]:
                folder_name = Path(found['location']).parent.name
                print(f"    [{found['position']:3d}] {found['expected']} → {found['found']} ({found['score']}%) in {folder_name}/")
            if len(found_in_folder) > 3:
                print(f"    ... and {len(found_in_folder) - 3} more by folder scan")
        
        print(f"\n{Fore.RED}✗ MISSING TRACKS ({len(missing_tracks)}/{len(tracks)}):{Style.RESET_ALL}")
        if missing_tracks:
            for missing in missing_tracks[:10]:  # Show first 10 missing tracks
                best_info = f" (closest: {missing['best_match']} - {missing['score']}%)" if missing['best_match'] else ""
                print(f"  [{missing['position']:3d}] {missing['expected']}{best_info}")
            if len(missing_tracks) > 10:
                print(f"  ... and {len(missing_tracks) - 10} more missing tracks")
        else:
            print(f"  {Fore.GREEN}🎉 All tracks found!{Style.RESET_ALL}")
        
        print(f"\n{Fore.CYAN}SUMMARY:{Style.RESET_ALL}")
        print(f"  Total tracks: {len(tracks)}")
        print(f"  Found in catalog: {len(found_in_catalog)}")
        print(f"  Found by folder scan: {len(found_in_folder)}")
        print(f"  Total found: {len(found_tracks)} ({len(found_tracks)/len(tracks)*100:.1f}%)")
        print(f"  Missing: {len(missing_tracks)} ({len(missing_tracks)/len(tracks)*100:.1f}%)")
        
        # Suggest catalog update if many tracks found by folder scan
        if len(found_in_folder) > 0:
            print(f"\n{Fore.YELLOW}💡 Tip: {len(found_in_folder)} tracks were found by folder scanning but not in catalog.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}   Run: python run.py --catalog-library to update your catalog database{Style.RESET_ALL}")
        
        return 0
        
    except ImportError as e:
        missing_lib = "fuzzywuzzy" if "fuzz" in str(e) else "mutagen"
        print(f"{Fore.RED}Error: {missing_lib} library required for check-missing command{Style.RESET_ALL}")
        if missing_lib == "fuzzywuzzy":
            print("Install it with: pip install fuzzywuzzy python-levenshtein")
        else:
            print("Install it with: pip install mutagen")
        return 1
    except Exception as e:
        print(f"{Fore.RED}Error checking missing tracks: {e}{Style.RESET_ALL}")
        return 1


def print_version():
    """Print version information"""
    print(f"{Fore.CYAN}Spotify Downloader v2.0.0{Style.RESET_ALL}")
    print(f"Modular architecture with secure Telegram integration")


async def main() -> int:
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Handle special commands first
    if args.help:
        print_help()
        return 0
    
    if args.version:
        print_version()
        return 0
    
    # Handle catalog-library command (doesn't require target)
    if hasattr(args, 'catalog_library') and args.catalog_library:
        # Load config for library path
        try:
            config = DownloadConfig.from_env(dry_run=True)  # Use dry_run config
        except ValueError as e:
            print(f"{Fore.RED}Configuration Error: {e}{Style.RESET_ALL}")
            print("MUSIC_LIBRARY_PATH is required for catalog functionality")
            return 1
        return await handle_catalog_library(args, config)
    
    if not args.target:
        print_banner()
        print(f"{Fore.YELLOW}Use --help for detailed usage information{Style.RESET_ALL}")
        return 0
    
    # Load configuration
    try:
        # Check if we're doing a dry run
        is_dry_run = args.dry_run if hasattr(args, 'dry_run') else False
        config = DownloadConfig.from_env(dry_run=is_dry_run)
    except ValueError as e:
        print(f"{Fore.RED}Configuration Error: {e}{Style.RESET_ALL}")
        print(f"Please check your .env file and ensure all required variables are set.")
        return 1
    
    # Handle commands
    if args.target == 'status':
        return await handle_status(config)
    elif args.target == 'reset':
        return await handle_reset(config)
    elif args.target == 'report':
        return await handle_report(args, config)
    elif args.target == 'help':
        print_help()
        return 0
    else:
        # Assume it's a download URL (first argument as URL)
        return await handle_download(args, config, args.target)


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted by user{Style.RESET_ALL}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Fore.RED}Unexpected error: {e}{Style.RESET_ALL}")
        sys.exit(1)