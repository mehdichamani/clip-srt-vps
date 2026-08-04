import asyncio
import logging
import threading
from typing import Optional
from google import genai
from google.genai import types

from app.config import settings
from app.utils.srt import clean_srt_response

logger = logging.getLogger("clip_srt_bot")


def mask_key(key: str) -> str:
    """Masks an API key for safe logging output."""
    if not key:
        return "None"
    if len(key) <= 10:
        return key[:2] + "..." + key[-2:]
    return key[:6] + "..." + key[-4:]


class TranslationService:
    """Service for translating SRT subtitles into Persian using Google Gemini-2.5-Flash with Round-Robin key rotation."""

    _counter_lock = threading.Lock()
    _key_index = 0

    def __init__(self, api_key: Optional[str] = None):
        self.explicit_key = api_key

    @classmethod
    def get_next_api_key(cls) -> Optional[str]:
        """Gets the next API key in round-robin order from configured Gemini keys."""
        keys = settings.get_gemini_api_keys()
        if not keys:
            return None
        with cls._counter_lock:
            key = keys[cls._key_index % len(keys)]
            cls._key_index = (cls._key_index + 1) % len(keys)
            return key

    async def translate_to_persian(self, srt_content: str) -> str:
        """
        Translates input SRT content into fluent Persian (Farsi) using gemini-2.5-flash.
        Preserves exact timestamps and line numbering.
        Rotates through configured Gemini API keys using round-robin.
        """
        if not srt_content.strip():
            raise ValueError("Input SRT content is empty.")

        available_keys = [self.explicit_key] if self.explicit_key else settings.get_gemini_api_keys()
        if not available_keys:
            raise RuntimeError("Gemini API Key is not configured. Cannot perform translation.")

        max_attempts = len(available_keys)
        last_exception = None

        prompt = f"""You are a professional subtitle translator.
Translate the text in the following SRT subtitle file into fluent, natural, and modern Persian (Farsi).

STRICT INSTRUCTIONS:
1. Keep exact same numeric sequence and timestamp ranges (`HH:MM:SS,mmm --> HH:MM:SS,mmm`).
2. Translate only the subtitle text lines into Persian.
3. Do NOT alter timestamps or subtitle block structure.
4. Output ONLY valid SRT content without any markdown intro/outro or explanations.

INPUT SRT:
{srt_content}
"""

        for attempt in range(max_attempts):
            api_key = self.explicit_key or self.get_next_api_key()
            if not api_key:
                break

            masked = mask_key(api_key)
            logger.info(f"Sending SRT content to Gemini (gemini-2.5-flash) using key [{masked}] (attempt {attempt + 1}/{max_attempts})...")

            def _do_translate(key: str):
                client = genai.Client(api_key=key)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                return response.text

            try:
                raw_response = await asyncio.to_thread(_do_translate, api_key)
                if not raw_response:
                    raise RuntimeError("Gemini returned empty translation response.")

                clean_srt = clean_srt_response(raw_response)
                logger.info(f"Persian subtitle translation completed successfully with key [{masked}].")
                return clean_srt
            except Exception as e:
                logger.warning(f"Gemini API call failed with key [{masked}]: {e}")
                last_exception = e
                if self.explicit_key:
                    break

        logger.error(f"All Gemini API attempts failed. Last error: {last_exception}")
        raise RuntimeError(f"Gemini translation error: {last_exception}")

