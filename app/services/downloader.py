import asyncio
import base64
import logging
import os
import re
import tempfile
import atexit
from typing import Optional
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

URL_REGEX = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)

class DownloaderService:
    """Service to handle Telegram media downloads and web media downloads via yt-dlp."""

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
    async def download_web_media(url: str, output_dir: str) -> str:
        """
        Downloads video or audio from web URLs (YouTube, Twitter/X, TikTok, Instagram, etc.) using yt-dlp.
        Returns the absolute path of the downloaded file.
        """
        os.makedirs(output_dir, exist_ok=True)
        outtmpl = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': outtmpl,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'max_filesize': 50 * 1024 * 1024,  # 50 MB limit
        }

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

        logger.info(f"Downloading media from URL: {url} via yt-dlp...")

        def _do_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                # If downloaded file has different extension (e.g. mkv/webm), locate actual downloaded file
                if os.path.exists(filename):
                    return filename
                # Search for file matching id
                file_id = info.get("id")
                for f in os.listdir(output_dir):
                    if file_id in f:
                        return os.path.join(output_dir, f)
                raise RuntimeError(f"Could not locate downloaded file for {url}")

        try:
            downloaded_path = await asyncio.to_thread(_do_download)
            logger.info(f"Web media downloaded successfully: {downloaded_path}")
            return downloaded_path
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
