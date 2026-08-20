import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.config import settings

logger = logging.getLogger("clip_srt_bot")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


class CookieManager:
    """
    Manages Netscape cookies persistence and retrieval with PostgreSQL hybrid storage
    and fallback to local file storage (.tmp/cookies_store.json).
    """

    def __init__(self, fallback_filepath: str = ".tmp/cookies_store.json"):
        self.fallback_filepath = fallback_filepath
        self._lock = threading.Lock()
        self._db_initialized = False

    def _normalize_db_url(self) -> Optional[str]:
        """Ensures connection URI uses postgresql:// scheme expected by psycopg2."""
        url = settings.database_url
        if not url:
            return None
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    def init_db(self) -> bool:
        """Initializes PostgreSQL table schema for cookies if DATABASE_URL is configured."""
        if not PSYCOPG2_AVAILABLE:
            return False

        db_url = self._normalize_db_url()
        if not db_url:
            logger.info("DATABASE_URL not configured. CookieManager using file storage fallback.")
            return False

        try:
            with psycopg2.connect(db_url, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS cookies_store (
                            id INT PRIMARY KEY DEFAULT 1,
                            mode VARCHAR(32) NOT NULL DEFAULT 'general',
                            general_cookies TEXT DEFAULT '',
                            youtube_cookies TEXT DEFAULT '',
                            instagram_cookies TEXT DEFAULT '',
                            updated_at DOUBLE PRECISION DEFAULT 0,
                            CONSTRAINT single_row_cookie CHECK (id = 1)
                        );
                    """)
                conn.commit()
            self._db_initialized = True
            logger.info("PostgreSQL database initialized successfully for CookieManager.")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL database for CookieManager: {e}")
            self._db_initialized = False
            return False

    @property
    def is_db_active(self) -> bool:
        """Returns True if PostgreSQL DB is configured and initialized."""
        return self._db_initialized and bool(self._normalize_db_url())

    def _get_db_connection(self):
        """Helper to return a new PostgreSQL connection if database is active."""
        if not self.is_db_active:
            return None
        db_url = self._normalize_db_url()
        try:
            return psycopg2.connect(db_url, connect_timeout=5)
        except Exception as e:
            logger.error(f"PostgreSQL connection error in CookieManager: {e}")
            return None

    def _read_fallback_file(self) -> Dict[str, Any]:
        """Reads cookie data from the fallback JSON file."""
        if not os.path.exists(self.fallback_filepath):
            return {
                "mode": "general",
                "general_cookies": "",
                "youtube_cookies": "",
                "instagram_cookies": "",
                "updated_at": 0
            }
        try:
            with open(self.fallback_filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading cookies fallback file: {e}")
            return {
                "mode": "general",
                "general_cookies": "",
                "youtube_cookies": "",
                "instagram_cookies": "",
                "updated_at": 0
            }

    def _write_fallback_file(self, data: Dict[str, Any]) -> None:
        """Writes cookie data to the fallback JSON file."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.fallback_filepath)), exist_ok=True)
            with open(self.fallback_filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error writing cookies fallback file: {e}")

    @staticmethod
    def count_cookies(cookie_text: Optional[str]) -> int:
        """Counts valid non-comment Netscape cookie lines in raw cookie text."""
        if not cookie_text:
            return 0
        count = 0
        for line in cookie_text.strip().splitlines():
            line_str = line.strip()
            if line_str and not line_str.startswith("#"):
                # Netscape cookie format has at least 7 tab-delimited or space-delimited fields
                parts = line_str.split("\t")
                if len(parts) >= 6 or len(line_str.split()) >= 6:
                    count += 1
                else:
                    count += 1
        return count

    def get_cookies_data(self) -> Dict[str, Any]:
        """Returns the full cookies configuration dictionary."""
        conn = self._get_db_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT mode, general_cookies, youtube_cookies, instagram_cookies, updated_at FROM cookies_store WHERE id = 1")
                    row = cur.fetchone()
                    if row:
                        data = dict(row)
                        return {
                            "mode": data.get("mode") or "general",
                            "general_cookies": data.get("general_cookies") or "",
                            "youtube_cookies": data.get("youtube_cookies") or "",
                            "instagram_cookies": data.get("instagram_cookies") or "",
                            "updated_at": data.get("updated_at") or 0
                        }
            except Exception as e:
                logger.error(f"Error reading cookies from PostgreSQL: {e}")
            finally:
                conn.close()

        with self._lock:
            return self._read_fallback_file()

    def save_cookies_data(
        self,
        mode: str = "general",
        general_cookies: Optional[str] = None,
        youtube_cookies: Optional[str] = None,
        instagram_cookies: Optional[str] = None
    ) -> Dict[str, Any]:
        """Saves or updates cookie configuration in PostgreSQL and fallback file."""
        now = time.time()
        current = self.get_cookies_data()

        updated = {
            "mode": mode if mode in ("general", "platform") else current.get("mode", "general"),
            "general_cookies": general_cookies.strip() if general_cookies is not None else current.get("general_cookies", ""),
            "youtube_cookies": youtube_cookies.strip() if youtube_cookies is not None else current.get("youtube_cookies", ""),
            "instagram_cookies": instagram_cookies.strip() if instagram_cookies is not None else current.get("instagram_cookies", ""),
            "updated_at": now
        }

        conn = self._get_db_connection()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO cookies_store (id, mode, general_cookies, youtube_cookies, instagram_cookies, updated_at)
                            VALUES (1, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                mode = EXCLUDED.mode,
                                general_cookies = EXCLUDED.general_cookies,
                                youtube_cookies = EXCLUDED.youtube_cookies,
                                instagram_cookies = EXCLUDED.instagram_cookies,
                                updated_at = EXCLUDED.updated_at;
                        """, (
                            updated["mode"],
                            updated["general_cookies"],
                            updated["youtube_cookies"],
                            updated["instagram_cookies"],
                            updated["updated_at"]
                        ))
                logger.info("Cookies configuration saved to PostgreSQL.")
            except Exception as e:
                logger.error(f"Error saving cookies to PostgreSQL: {e}")
            finally:
                conn.close()

        with self._lock:
            self._write_fallback_file(updated)

        return updated

    def clear_cookies(self, target: str = "all") -> Dict[str, Any]:
        """
        Clears cookies for general, youtube, instagram, or all.
        target can be 'all', 'general', 'youtube', or 'instagram'.
        """
        current = self.get_cookies_data()
        if target == "all":
            current["general_cookies"] = ""
            current["youtube_cookies"] = ""
            current["instagram_cookies"] = ""
        elif target == "general":
            current["general_cookies"] = ""
        elif target == "youtube":
            current["youtube_cookies"] = ""
        elif target == "instagram":
            current["instagram_cookies"] = ""
        
        return self.save_cookies_data(
            mode=current.get("mode", "general"),
            general_cookies=current.get("general_cookies", ""),
            youtube_cookies=current.get("youtube_cookies", ""),
            instagram_cookies=current.get("instagram_cookies", "")
        )

    def get_active_cookie_content(self, url: Optional[str] = None) -> str:
        """
        Returns combined cookie text based on active mode and optional URL target.
        If mode is 'general', returns general_cookies.
        If mode is 'platform', returns youtube + instagram combined (or specific if needed).
        """
        data = self.get_cookies_data()
        mode = data.get("mode", "general")

        if mode == "general":
            return (data.get("general_cookies") or "").strip()
        else:
            parts = []
            yt = (data.get("youtube_cookies") or "").strip()
            ig = (data.get("instagram_cookies") or "").strip()
            if yt:
                parts.append(yt)
            if ig:
                parts.append(ig)
            return "\n".join(parts)


cookie_manager = CookieManager()
