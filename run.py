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
  --batch-size N     Process N tracks at a time (default: 10)
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
        '--batch-size',
        type=int,
        default=10,
        help='Number of tracks to process in each batch (default: 10)'
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


async def handle_download(args, config: DownloadConfig) -> int:
    """Handle download command"""
    if not args.target or args.target in ['download']:
        print(f"{Fore.RED}Error: Playlist URL required for download{Style.RESET_ALL}")
        print(f"Usage: python run.py <playlist_url> [options]")
        return 1
    
    # Handle 'download <url>' format
    url = args.target
    if args.target == 'download' and len(sys.argv) > 2:
        url = sys.argv[2]
    
    if not url.startswith('https://open.spotify.com/'):
        print(f"{Fore.RED}Error: Invalid Spotify URL{Style.RESET_ALL}")
        print(f"URL should start with: https://open.spotify.com/")
        return 1
    
    try:
        # Update config based on arguments
        config.download_folder = args.output_dir
        config.organize_by_artist = args.organize_by == 'artist'
        config.organize_by_album = args.organize_by == 'album'
        config.create_year_folders = args.year_folders
        config.progress_file = args.progress_file
        
        # Create and initialize downloader
        downloader = await create_downloader(config)
        
        try:
            # Start download
            result = await downloader.download_playlist(
                url,
                dry_run=args.dry_run,
                batch_size=args.batch_size,
                resume=not args.no_resume
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
        config = DownloadConfig.from_env()
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
        # Assume it's a download URL
        return await handle_download(args, config)


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