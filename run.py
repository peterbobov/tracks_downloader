#!/usr/bin/env python3
"""
Spotify DJ Track Automation - CLI Entry Point

Downloads DJ tracks from Spotify playlists via Telegram bot.
Only downloads tracks not already in your library.
"""

import sys
import asyncio
import argparse
from pathlib import Path

from dotenv import load_dotenv
from colorama import init as colorama_init, Fore, Style

load_dotenv()
colorama_init()


def print_banner():
    """Print application banner"""
    print(f"\n{Fore.CYAN}{'='*50}")
    print(f"  Spotify DJ Track Automation v3.0.0")
    print(f"{'='*50}{Style.RESET_ALL}\n")


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser with simplified flags"""
    parser = argparse.ArgumentParser(
        description="Download missing tracks from Spotify playlists via Telegram bot",
        add_help=True,
    )

    parser.add_argument(
        'target',
        nargs='?',
        help='Spotify playlist/album/track URL, or command: status, reset, catalog'
    )

    parser.add_argument('--dry-run', action='store_true',
                        help='Preview tracks without downloading')
    parser.add_argument('--batch-size', type=int, default=None,
                        help='Tracks per batch (default: 3)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Maximum number of tracks to process')
    parser.add_argument('--start-from', type=int, default=1,
                        help='Start from track N (1-indexed)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug output')
    parser.add_argument('--sequential', action='store_true',
                        help='Process tracks one at a time')
    parser.add_argument('--version', action='store_true',
                        help='Show version')

    return parser


async def handle_download(args):
    """Handle playlist download — only downloads missing tracks"""
    from src.downloader import SpotifyDownloader, DownloadConfig

    try:
        config = DownloadConfig.from_env()
    except ValueError as e:
        print(f"{Fore.RED}Configuration error: {e}{Style.RESET_ALL}")
        sys.exit(1)

    downloader = SpotifyDownloader(config)

    try:
        await downloader.initialize()

        if args.debug:
            downloader.set_debug_mode(True)

        result = await downloader.download_playlist(
            playlist_url=args.target,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            limit=args.limit,
            sequential=args.sequential,
            start_from=args.start_from,
        )

        # Print summary
        if result and not args.dry_run:
            print(f"\n{Fore.GREEN}{'='*50}")
            print(f"  Download Complete")
            print(f"{'='*50}{Style.RESET_ALL}")
            downloaded = result.get('downloaded', 0)
            failed = result.get('failed', 0)
            skipped = result.get('skipped', 0)
            if downloaded:
                print(f"  {Fore.GREEN}Downloaded: {downloaded}{Style.RESET_ALL}")
            if skipped:
                print(f"  {Fore.YELLOW}Already in library: {skipped}{Style.RESET_ALL}")
            if failed:
                print(f"  {Fore.RED}Failed: {failed}{Style.RESET_ALL}")

    finally:
        await downloader.cleanup()


async def handle_status(args):
    """Show current session status"""
    from src.downloader import SpotifyDownloader, DownloadConfig

    try:
        config = DownloadConfig.from_env()
    except ValueError as e:
        print(f"{Fore.RED}Configuration error: {e}{Style.RESET_ALL}")
        sys.exit(1)

    downloader = SpotifyDownloader(config)
    status = downloader.get_status()

    if not status:
        print(f"{Fore.YELLOW}No active session found.{Style.RESET_ALL}")
        return

    print(f"\n{Fore.CYAN}Session Status:{Style.RESET_ALL}")
    for key, value in status.items():
        print(f"  {key}: {value}")


async def handle_reset(args):
    """Reset current session"""
    from src.downloader import SpotifyDownloader, DownloadConfig

    try:
        config = DownloadConfig.from_env()
    except ValueError as e:
        print(f"{Fore.RED}Configuration error: {e}{Style.RESET_ALL}")
        sys.exit(1)

    downloader = SpotifyDownloader(config)
    downloader.reset_progress()
    print(f"{Fore.GREEN}Session reset successfully.{Style.RESET_ALL}")


async def handle_catalog(args):
    """Rebuild catalog from music library on disk"""
    from src.catalog import LibraryCatalog
    from src.downloader import DownloadConfig

    try:
        config = DownloadConfig.from_env()
    except ValueError as e:
        print(f"{Fore.RED}Configuration error: {e}{Style.RESET_ALL}")
        sys.exit(1)

    library_path = config.music_library_path
    if not Path(library_path).exists():
        print(f"{Fore.RED}Music library path not found: {library_path}{Style.RESET_ALL}")
        sys.exit(1)

    print(f"Scanning music library: {library_path}")

    catalog = LibraryCatalog()
    added, errors = catalog.scan_library(Path(library_path))
    print(f"\n{Fore.GREEN}Catalog rebuilt:{Style.RESET_ALL}")
    print(f"  Tracks indexed: {added}")
    print(f"  Errors: {errors}")


async def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()

    if args.version:
        print("spotify-downloader v3.0.0")
        return

    if not args.target:
        parser.print_help()
        return

    print_banner()

    # Route to handler
    if args.target == 'status':
        await handle_status(args)
    elif args.target == 'reset':
        await handle_reset(args)
    elif args.target == 'catalog':
        await handle_catalog(args)
    elif args.target.startswith('http'):
        await handle_download(args)
    else:
        print(f"{Fore.RED}Unknown command or invalid URL: {args.target}{Style.RESET_ALL}")
        parser.print_help()


if __name__ == '__main__':
    asyncio.run(main())
