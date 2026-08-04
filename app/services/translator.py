import asyncio
import logging
import threading
from typing import Optional
from groq import Groq

try:
    from google import genai
except ImportError:
    genai = None

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
    """Service for translating SRT subtitles into Persian using Groq API (llama-3.3-70b-versatile) with optional Gemini fallback."""

    _counter_lock = threading.Lock()
    _key_index = 0

    def __init__(self, api_key: Optional[str] = None):
        self.explicit_key = api_key

    @classmethod
    def get_next_gemini_api_key(cls) -> Optional[str]:
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
        Translates input SRT content into fluent Persian (Farsi) using Groq API (llama-3.3-70b-versatile).
        Preserves exact timestamps and line numbering.
        Falls back to Gemini API if configured and Groq fails.
        """
        if not srt_content.strip():
            raise ValueError("Input SRT content is empty.")

        system_prompt = (
            "You are a professional subtitle translator.\n"
            "Translate the text in the SRT subtitle file into fluent, natural, and modern Persian (Farsi).\n\n"
            "STRICT INSTRUCTIONS:\n"
            "1. Keep exact same numeric sequence and timestamp ranges (`HH:MM:SS,mmm --> HH:MM:SS,mmm`).\n"
            "2. Translate only the subtitle text lines into Persian.\n"
            "3. Do NOT alter timestamps or subtitle block structure.\n"
            "4. Output ONLY valid SRT content without any markdown intro/outro or explanations."
        )

        user_prompt = f"INPUT SRT:\n{srt_content}"

        # 1. Primary: Try Groq API
        groq_key = self.explicit_key or settings.groq_api_key
        if groq_key:
            masked = mask_key(groq_key)
            logger.info(f"Sending SRT content to Groq API (llama-3.3-70b-versatile) using key [{masked}]...")

            def _do_groq_translate(key: str):
                client = Groq(api_key=key)
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                )
                return response.choices[0].message.content

            try:
                raw_response = await asyncio.to_thread(_do_groq_translate, groq_key)
                if raw_response:
                    clean_srt = clean_srt_response(raw_response)
                    logger.info("Persian subtitle translation completed successfully via Groq AI.")
                    return clean_srt
            except Exception as e:
                logger.warning(f"Groq API translation failed with key [{masked}]: {e}")
                if not settings.get_gemini_api_keys():
                    raise RuntimeError(f"Groq translation error: {e}")

        # 2. Secondary: Fallback to Gemini API if keys are available
        gemini_keys = settings.get_gemini_api_keys()
        if gemini_keys and genai is not None:
            max_attempts = len(gemini_keys)
            last_exception = None
            for attempt in range(max_attempts):
                api_key = self.get_next_gemini_api_key()
                if not api_key:
                    break

                masked = mask_key(api_key)
                logger.info(f"Fallback: Sending SRT content to Gemini using key [{masked}] (attempt {attempt + 1}/{max_attempts})...")

                def _do_gemini_translate(key: str):
                    client = genai.Client(api_key=key)
                    full_prompt = f"{system_prompt}\n\n{user_prompt}"
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=full_prompt,
                    )
                    return response.text

                try:
                    raw_response = await asyncio.to_thread(_do_gemini_translate, api_key)
                    if raw_response:
                        clean_srt = clean_srt_response(raw_response)
                        logger.info(f"Persian subtitle translation completed successfully via Gemini fallback with key [{masked}].")
                        return clean_srt
                except Exception as e:
                    logger.warning(f"Gemini API fallback call failed with key [{masked}]: {e}")
                    last_exception = e

            raise RuntimeError(f"Translation failed on both Groq and Gemini. Last Gemini error: {last_exception}")

        raise RuntimeError("No valid API Key (GROQ_API_KEY) configured for translation.")
