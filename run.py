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
    response = input(f"{Fore.YELLOW}This will delete all progress data. Continue? (yes/no): {Style.RESET_ALL}")
    
    if response.lower() not in ['yes', 'y']:
        print("Reset cancelled.")
        return 0
    
    try:
        downloader = SpotifyDownloader(config)
        downloader.reset_progress()
        print(f"{Fore.GREEN}Progress data reset successfully{Style.RESET_ALL}")
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


async def handle_check_missing(url: str, config: DownloadConfig) -> int:
    """Handle check-missing command"""
    try:
        from fuzzywuzzy import fuzz
        from pathlib import Path
        
        # Create downloader (we only need Spotify API, not Telegram)
        downloader = SpotifyDownloader(config)
        
        print(f"{Fore.CYAN}Fetching playlist tracks from Spotify...{Style.RESET_ALL}")
        
        # Extract tracks from Spotify
        tracks = downloader.spotify.extract_tracks(url)
        if not tracks:
            print(f"{Fore.RED}Error: Could not extract tracks from URL{Style.RESET_ALL}")
            return 1
        
        print(f"{Fore.GREEN}Found {len(tracks)} tracks in playlist{Style.RESET_ALL}")
        
        # Get download folder
        download_folder = Path(config.download_folder)
        if not download_folder.exists():
            print(f"{Fore.RED}Error: Download folder does not exist: {download_folder}{Style.RESET_ALL}")
            return 1
        
        # Get all .flac files in download folder (recursively)
        existing_files = list(download_folder.rglob("*.flac"))
        existing_filenames = [f.stem for f in existing_files]  # Without .flac extension
        
        print(f"{Fore.CYAN}Found {len(existing_files)} FLAC files in download folder{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Checking for missing tracks (90% similarity threshold)...{Style.RESET_ALL}\n")
        
        missing_tracks = []
        found_tracks = []
        
        for i, track in enumerate(tracks, 1):
            expected_filename = f"{track.artist_string} - {track.name}"
            
            # Find best match using fuzzy string matching
            best_score = 0
            best_match = None
            
            for existing_filename in existing_filenames:
                score = fuzz.ratio(expected_filename.lower(), existing_filename.lower())
                if score > best_score:
                    best_score = score
                    best_match = existing_filename
            
            # 90% confidence threshold
            if best_score >= 90:
                found_tracks.append({
                    'position': i,
                    'track': track,
                    'expected': expected_filename,
                    'found': best_match,
                    'score': best_score
                })
            else:
                missing_tracks.append({
                    'position': i,
                    'track': track,
                    'expected': expected_filename,
                    'best_match': best_match,
                    'score': best_score
                })
        
        # Display results
        print(f"{Fore.GREEN}✓ FOUND TRACKS ({len(found_tracks)}/{len(tracks)}):{Style.RESET_ALL}")
        for found in found_tracks[:5]:  # Show first 5 found tracks
            print(f"  [{found['position']:3d}] {found['expected']} (match: {found['score']}%)")
        if len(found_tracks) > 5:
            print(f"  ... and {len(found_tracks) - 5} more found tracks")
        
        print(f"\n{Fore.RED}✗ MISSING TRACKS ({len(missing_tracks)}/{len(tracks)}):{Style.RESET_ALL}")
        if missing_tracks:
            for missing in missing_tracks:
                best_info = f" (best match: {missing['best_match']} - {missing['score']}%)" if missing['best_match'] else ""
                print(f"  [{missing['position']:3d}] {missing['expected']}{best_info}")
        else:
            print(f"  {Fore.GREEN}🎉 All tracks found!{Style.RESET_ALL}")
        
        print(f"\n{Fore.CYAN}SUMMARY:{Style.RESET_ALL}")
        print(f"  Total tracks: {len(tracks)}")
        print(f"  Found: {len(found_tracks)} ({len(found_tracks)/len(tracks)*100:.1f}%)")
        print(f"  Missing: {len(missing_tracks)} ({len(missing_tracks)/len(tracks)*100:.1f}%)")
        
        return 0
        
    except ImportError:
        print(f"{Fore.RED}Error: fuzzywuzzy library required for check-missing command{Style.RESET_ALL}")
        print("Install it with: pip install fuzzywuzzy python-levenshtein")
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