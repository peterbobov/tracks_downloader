#!/usr/bin/env python3
import os
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from colorama import init, Fore, Style

# Initialize colorama
init()

class TelegramMonitor:
    def __init__(self):
        load_dotenv()
        
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.download_folder = Path(os.getenv('DOWNLOAD_FOLDER', './downloads'))
        
        # Queue for tracking sent URLs and their responses
        self.pending_urls = {}
        self.response_queue = asyncio.Queue()
        
        # Create download folder
        self.download_folder.mkdir(exist_ok=True)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages from bot"""
        message = update.message
        
        # Check if message is from our bot
        if str(message.chat_id) != self.chat_id:
            return
        
        # Handle text messages (might be errors or status updates)
        if message.text:
            print(f"{Fore.YELLOW}Bot message: {message.text}{Style.RESET_ALL}")
            
            # Check if this is a response to a pending URL
            for url, data in self.pending_urls.items():
                if url in message.text or data['track_name'] in message.text:
                    await self.response_queue.put({
                        'type': 'text',
                        'url': url,
                        'message': message.text,
                        'timestamp': datetime.now()
                    })
                    break
        
        # Handle document/file messages
        if message.document:
            file_name = message.document.file_name
            file_id = message.document.file_id
            file_size = message.document.file_size
            
            print(f"{Fore.GREEN}File received: {file_name} ({file_size} bytes){Style.RESET_ALL}")
            
            # Find which URL this file corresponds to
            matched_url = None
            for url, data in self.pending_urls.items():
                # Match by track name in filename
                if data['track_name'].lower() in file_name.lower():
                    matched_url = url
                    break
            
            if matched_url:
                await self.response_queue.put({
                    'type': 'file',
                    'url': matched_url,
                    'file_id': file_id,
                    'file_name': file_name,
                    'file_size': file_size,
                    'timestamp': datetime.now()
                })
            else:
                print(f"{Fore.YELLOW}Warning: Received file but couldn't match to pending URL{Style.RESET_ALL}")
    
    async def download_file(self, bot: Bot, file_id: str, file_path: Path) -> bool:
        """Download file from Telegram"""
        try:
            file = await bot.get_file(file_id)
            await file.download_to_drive(file_path)
            return True
        except Exception as e:
            print(f"{Fore.RED}Error downloading file: {e}{Style.RESET_ALL}")
            return False
    
    async def send_url_and_wait(self, bot: Bot, url: str, track_info: Dict, timeout: int = 60) -> Optional[Dict]:
        """Send URL to bot and wait for file response"""
        track_name = f"{', '.join(track_info['artists'])} - {track_info['name']}"
        
        # Add to pending URLs
        self.pending_urls[url] = {
            'track_name': track_name,
            'track_info': track_info,
            'sent_at': datetime.now()
        }
        
        try:
            # Send URL to bot
            await bot.send_message(chat_id=self.chat_id, text=url)
            print(f"{Fore.CYAN}Sent: {track_name}{Style.RESET_ALL}")
            
            # Wait for response with timeout
            start_time = asyncio.get_event_loop().time()
            
            while asyncio.get_event_loop().time() - start_time < timeout:
                try:
                    # Check for response (non-blocking with short timeout)
                    response = await asyncio.wait_for(
                        self.response_queue.get(), 
                        timeout=1.0
                    )
                    
                    if response['url'] == url:
                        # Found matching response
                        del self.pending_urls[url]
                        return response
                    else:
                        # Put it back if not matching
                        await self.response_queue.put(response)
                        
                except asyncio.TimeoutError:
                    # Continue waiting
                    continue
            
            # Timeout reached
            print(f"{Fore.YELLOW}Timeout waiting for: {track_name}{Style.RESET_ALL}")
            del self.pending_urls[url]
            return None
            
        except Exception as e:
            print(f"{Fore.RED}Error processing {track_name}: {e}{Style.RESET_ALL}")
            if url in self.pending_urls:
                del self.pending_urls[url]
            return None
    
    async def start_monitoring(self):
        """Start the Telegram monitoring application"""
        app = Application.builder().token(self.bot_token).build()
        
        # Add message handler
        app.add_handler(MessageHandler(filters.ALL, self.handle_message))
        
        # Start polling
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        print(f"{Fore.GREEN}Telegram monitor started{Style.RESET_ALL}")
        
        return app


class EnhancedSpotifyDownloader:
    """Enhanced downloader that integrates with Telegram monitoring"""
    
    def __init__(self, telegram_monitor: TelegramMonitor):
        load_dotenv()
        
        self.monitor = telegram_monitor
        self.bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
        self.download_folder = Path(os.getenv('DOWNLOAD_FOLDER', './downloads'))
        self.delay_between_requests = int(os.getenv('DELAY_BETWEEN_REQUESTS', 3))
        
        # Import spotify functionality from main downloader
        from spotify_downloader import SpotifyDownloader
        self.spotify_downloader = SpotifyDownloader()
    
    async def process_track_with_monitoring(self, track: Dict) -> bool:
        """Process track with Telegram monitoring"""
        track_name = f"{', '.join(track['artists'])} - {track['name']}"
        
        # Send URL and wait for response
        response = await self.monitor.send_url_and_wait(
            self.bot, 
            track['url'], 
            track,
            timeout=60
        )
        
        if response and response['type'] == 'file':
            # Download the file
            filename = self.spotify_downloader.sanitize_filename(
                response['file_name'] or f"{track_name}.flac"
            )
            filepath = self.download_folder / filename
            
            success = await self.monitor.download_file(
                self.bot,
                response['file_id'],
                filepath
            )
            
            if success:
                print(f"{Fore.GREEN}✓ Downloaded: {filename}{Style.RESET_ALL}")
                return True
        
        return False
    
    async def process_playlist_with_monitoring(self, playlist_url: str):
        """Process playlist with Telegram monitoring"""
        # Get playlist tracks
        playlist_id = self.spotify_downloader.extract_playlist_id(playlist_url)
        tracks = self.spotify_downloader.get_playlist_tracks(playlist_id)
        
        # Start Telegram monitoring
        app = await self.monitor.start_monitoring()
        
        try:
            # Process tracks
            successful = 0
            failed = 0
            
            for i, track in enumerate(tracks, 1):
                print(f"\n{Fore.CYAN}[{i}/{len(tracks)}]{Style.RESET_ALL}")
                
                # Skip if already processed
                if track['id'] in self.spotify_downloader.progress_data['processed_tracks']:
                    print(f"{Fore.YELLOW}Already processed, skipping{Style.RESET_ALL}")
                    successful += 1
                    continue
                
                success = await self.process_track_with_monitoring(track)
                
                if success:
                    successful += 1
                    self.spotify_downloader.progress_data['processed_tracks'].append(track['id'])
                else:
                    failed += 1
                    self.spotify_downloader.progress_data['failed_tracks'].append({
                        'id': track['id'],
                        'name': f"{', '.join(track['artists'])} - {track['name']}",
                        'reason': 'No file received from bot'
                    })
                
                self.spotify_downloader.save_progress()
                
                # Delay between requests
                if i < len(tracks):
                    await asyncio.sleep(self.delay_between_requests)
            
            # Final report
            print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}Successful downloads: {successful}{Style.RESET_ALL}")
            print(f"{Fore.RED}Failed downloads: {failed}{Style.RESET_ALL}")
            
        finally:
            # Stop monitoring
            await app.updater.stop()
            await app.stop()
            await app.shutdown()


async def main():
    """Main entry point for enhanced downloader"""
    import sys
    
    if len(sys.argv) < 2:
        print(f"{Fore.CYAN}Enhanced Spotify Downloader with Telegram Monitoring{Style.RESET_ALL}")
        print(f"\nUsage:")
        print(f"  python telegram_monitor.py <playlist_url>")
        return
    
    playlist_url = sys.argv[1]
    
    # Create monitor and enhanced downloader
    monitor = TelegramMonitor()
    downloader = EnhancedSpotifyDownloader(monitor)
    
    # Process playlist
    await downloader.process_playlist_with_monitoring(playlist_url)


if __name__ == "__main__":
    asyncio.run(main())