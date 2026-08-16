import asyncio
import base64
import logging
import os
import re
import tempfile
import atexit
import urllib.request
from typing import Optional, Tuple
import yt_dlp
from telegram import Bot
from app.config import settings

logger = logging.getLogger("clip_srt_bot")

_temp_cookie_files = set()

def _cleanup_temp_cookies():
    while _temp_cookie_files:
        try:
            path = _temp_cookie_files.pop()
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.error(f"Error cleaning up temp cookie file {path}: {e}")

atexit.register(_cleanup_temp_cookies)

def get_cookies_content(cookies_str: str) -> str:
    cookies_str = cookies_str.strip()
    if not cookies_str:
        return ""
    if '#' in cookies_str or '\t' in cookies_str:
        return cookies_str
    try:
        padded_str = cookies_str
        missing_padding = len(padded_str) % 4
        if missing_padding:
            padded_str += '=' * (4 - missing_padding)
        decoded_bytes = base64.b64decode(padded_str, validate=True)
        return decoded_bytes.decode('utf-8')
    except Exception:
        return cookies_str

def _setup_cookie_file(ydl_opts: dict) -> Optional[str]:
    """Applies cookie configuration to ydl_opts and returns temp_cookie_path if created."""
    temp_cookie_path = None
    if settings.instagram_cookies:
        try:
            cookie_content = get_cookies_content(settings.instagram_cookies)
            if cookie_content:
                with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as f:
                    f.write(cookie_content)
                    temp_cookie_path = f.name
                _temp_cookie_files.add(temp_cookie_path)
                ydl_opts['cookiefile'] = temp_cookie_path
                logger.info("Using temporary cookie file created from INSTAGRAM_COOKIES environment variable.")
        except Exception as e:
            logger.error(f"Failed to create temporary cookie file: {e}")
    else:
        local_cookies = 'cookies.txt'
        if os.path.exists(local_cookies):
            ydl_opts['cookiefile'] = local_cookies
            logger.info("Using local cookies.txt file.")
    return temp_cookie_path

URL_REGEX = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)

class DownloaderService:
    """Service to handle Telegram media downloads and web media downloads via yt-dlp."""

    @staticmethod
    def sanitize_filename(channel: Optional[str] = None, title: Optional[str] = None, ext: str = ".mkv") -> str:
        r"""
        Sanitizes channel and title into clean OS filename `{channel_name} - {title}{ext}` or `{title}{ext}`.
        Strips illegal characters (/, \, :, *, ?, ", <, >, |) and limits total base name length to ~100 chars.
        """
        ch_clean = (channel or "").strip()
        ti_clean = (title or "").strip()

        if not ch_clean:
            ch_clean = "Unknown Channel"
        if not ti_clean:
            ti_clean = "Video"

        if channel is None and ti_clean != "Video":
            raw_name = ti_clean
        else:
            raw_name = f"{ch_clean} - {ti_clean}"

        # Strip illegal characters: /, \, :, *, ?, ", <, >, |, control characters
        sanitized = re.sub(r'[/\\:*?"<>|]', '', raw_name)
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        if not sanitized:
            sanitized = "Unknown Channel - Video"

        # Limit total file name length to ~100 characters max
        if len(sanitized) > 100:
            sanitized = sanitized[:100].strip()

        if not ext.startswith("."):
            ext = f".{ext}"

        return f"{sanitized}{ext}"

    @staticmethod
    def extract_url(text: str) -> Optional[str]:
        """Extracts the first valid HTTP/HTTPS URL from a text message."""
        if not text:
            return None
        match = URL_REGEX.search(text)
        return match.group(0) if match else None

    @staticmethod
    async def download_telegram_file(bot: Bot, file_id: str, destination_path: str) -> str:
        """Downloads a file directly from Telegram servers."""
        logger.info(f"Downloading Telegram file_id={file_id} to {destination_path}")
        tg_file = await bot.get_file(file_id)
        await tg_file.download_to_drive(custom_path=destination_path)
        logger.info(f"Telegram file saved to {destination_path}")
        return destination_path

    @staticmethod
    async def fetch_web_thumbnail(url: str, output_path: str) -> Optional[str]:
        """
        Fetches web media thumbnail without downloading the video payload.
        Saves thumbnail image to output_path and returns output_path if successful.
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        temp_cookie_path = _setup_cookie_file(ydl_opts)

        def _get_thumb():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None
                thumb_url = info.get('thumbnail')
                if not thumb_url and info.get('thumbnails'):
                    thumb_url = info['thumbnails'][-1].get('url')
                if not thumb_url:
                    return None

                req = urllib.request.Request(
                    thumb_url,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(req, timeout=10) as resp, open(output_path, 'wb') as f:
                    f.write(resp.read())

                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    logger.info(f"Web thumbnail downloaded successfully to {output_path}")
                    return output_path
                return None

        try:
            return await asyncio.to_thread(_get_thumb)
        except Exception as e:
            logger.warning(f"Could not fetch web thumbnail for {url}: {e}")
            return None
        finally:
            if temp_cookie_path:
                try:
                    if os.path.exists(temp_cookie_path):
                        os.remove(temp_cookie_path)
                    _temp_cookie_files.discard(temp_cookie_path)
                except Exception as e:
                    logger.error(f"Failed to remove temporary cookie file {temp_cookie_path}: {e}")

    @staticmethod
    async def download_web_media(url: str, output_dir: str) -> Tuple[str, str, str]:
        """
        Downloads video or audio from web URLs (YouTube, Twitter/X, TikTok, Instagram, etc.) using yt-dlp.
        Returns a tuple of (downloaded_path, title, channel).
        """
        os.makedirs(output_dir, exist_ok=True)
        outtmpl = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best',
            'outtmpl': outtmpl,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'max_filesize': 50 * 1024 * 1024,  # 50 MB limit
        }

        temp_cookie_path = _setup_cookie_file(ydl_opts)

        logger.info(f"Downloading media from URL: {url} via yt-dlp...")

        def _do_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise RuntimeError(f"Could not extract info for URL {url}")

                if 'entries' in info and info['entries']:
                    info = info['entries'][0]

                title = info.get("title") or info.get("fulltitle") or "Video"
                channel = info.get("channel") or info.get("uploader") or info.get("uploader_id") or "Unknown Channel"

                filename = ydl.prepare_filename(info)
                # If downloaded file has different extension (e.g. mkv/webm), locate actual downloaded file
                if os.path.exists(filename):
                    return filename, str(title), str(channel)

                # Search for file matching id
                file_id = info.get("id")
                if file_id:
                    for f in os.listdir(output_dir):
                        if file_id in f:
                            return os.path.join(output_dir, f), str(title), str(channel)

                raise RuntimeError(f"Could not locate downloaded file for {url}")

        try:
            downloaded_path, title, channel = await asyncio.to_thread(_do_download)
            logger.info(f"Web media downloaded successfully: {downloaded_path} (Title: {title}, Channel: {channel})")
            return downloaded_path, title, channel
        except Exception as e:
            logger.error(f"yt-dlp download failed for {url}: {e}")
            raise RuntimeError(f"Media download failed: {str(e)[:200]}")
        finally:
            if temp_cookie_path:
                try:
                    if os.path.exists(temp_cookie_path):
                        os.remove(temp_cookie_path)
                    _temp_cookie_files.discard(temp_cookie_path)
                except Exception as e:
                    logger.error(f"Failed to remove temporary cookie file {temp_cookie_path}: {e}")


