# Telethon Spotify Downloader - External Bot Integration

This version uses Telethon to automate your personal Telegram account for interacting with external bots you don't control.

## ⚠️ Security Notice

**This script automates your personal Telegram account.** Please read and understand the security implications:

### Security Considerations

**✅ Strengths:**
- Uses official MTProto protocol (same as Telegram apps)
- Local encrypted session storage
- No third-party credential sharing
- Open source Telethon library

**⚠️ Risks:**
- Script has full access to your Telegram account
- Session files are sensitive (treat like passwords)
- May trigger rate limiting or account restrictions
- Potential Terms of Service considerations

### Security Best Practices

1. **Use a dedicated Telegram account** (strongly recommended)
2. **Protect session files** - stored in `./sessions/` with 0o700 permissions
3. **Conservative rate limiting** - minimum 3 seconds between messages
4. **Monitor for restrictions** - watch for FloodWaitError
5. **Use small batches** - default 10 tracks at a time

## Setup

### 1. Get Telegram API Credentials

1. Go to [https://my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Click "API Development Tools"
4. Create a new application (any name/platform)
5. Save your `api_id` and `api_hash`

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with:
```env
# Spotify API (same as before)
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret

# Telegram API (NEW)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_hash_here
TELEGRAM_PHONE_NUMBER=+1234567890

# External Bot
EXTERNAL_BOT_USERNAME=@your_bot_username

# Safety Settings
DELAY_BETWEEN_REQUESTS=3  # Minimum recommended
FLOOD_WAIT_MULTIPLIER=1.5  # Extra safety margin
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### First Run (Authentication)

```bash
python telethon_downloader.py https://open.spotify.com/playlist/xxxxx
```

On first run:
1. You'll receive a code via Telegram
2. Enter the code when prompted
3. If you have 2FA, enter your password
4. Session saved securely for future use

### Subsequent Runs

```bash
# Process playlist (default 10 tracks per batch)
python telethon_downloader.py https://open.spotify.com/playlist/xxxxx

# Custom batch size
python telethon_downloader.py https://open.spotify.com/playlist/xxxxx --batch-size 5

# Dry run (preview without sending)
python telethon_downloader.py https://open.spotify.com/playlist/xxxxx --dry-run

# Check status
python telethon_downloader.py --status

# Reset progress
python telethon_downloader.py --reset
```

## How It Works

1. **Authentication**: Logs into your Telegram account
2. **Playlist Extraction**: Gets tracks from Spotify API
3. **Batch Processing**: Sends URLs in small batches
4. **Response Monitoring**: Watches for file responses
5. **Automatic Download**: Downloads FLAC files when received
6. **Progress Tracking**: Saves state for resumption

## Safety Features

### Rate Limiting
- Minimum 3-second delay between messages
- Automatic FloodWaitError handling
- Exponential backoff on errors
- Batch processing to reduce load

### Session Security
- Sessions stored in protected directory (mode 0o700)
- Never share or backup session files publicly
- Treat session files like passwords

### Progress Management
- Tracks processed songs
- Resume interrupted sessions
- Skip already downloaded tracks
- Detailed error logging

## File Organization

Downloaded files saved as:
```
downloads/
├── Artist 1 - Song Title.flac
├── Artist 2 - Another Song.flac
└── ...
```

## Troubleshooting

### "FloodWaitError"
- Normal rate limiting response
- Script handles automatically
- Waits required time + safety margin

### "SessionPasswordNeededError"
- You have 2FA enabled
- Enter your password when prompted

### Bot Not Responding
- Verify bot username is correct
- Check bot is accessible
- Some tracks may not be available

### Authentication Issues
- Delete session file to re-authenticate
- Check phone number format (+country code)
- Ensure API credentials are correct

## Alternative Approaches

If security concerns:

1. **Manual Hybrid**: Script prepares URLs, you send manually
2. **Browser Automation**: Selenium with Telegram Web
3. **Desktop Automation**: PyAutoGUI for Telegram Desktop

## Progress Files

- `progress.json`: Tracks processing state
- `sessions/*.session`: Telegram session (sensitive!)
- `downloads/`: Downloaded FLAC files

## Important Reminders

1. **This automates your personal account** - use responsibly
2. **Respect rate limits** - avoid account restrictions
3. **Monitor first batch** - ensure bot responds correctly
4. **Secure session files** - never share or expose
5. **Consider dedicated account** - reduces risk to main account

## Support

For issues:
1. Check bot is responding manually first
2. Verify all credentials are correct
3. Try smaller batch sizes
4. Check `progress.json` for errors
5. Delete session file to re-authenticate if needed