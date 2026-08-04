import asyncio
import logging
from google import genai
from google.genai import types

from app.config import settings
from app.utils.srt import clean_srt_response

logger = logging.getLogger("clip_srt_bot")

class TranslationService:
    """Service for translating SRT subtitles into Persian using Google Gemini-2.5-Flash."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.gemini_api_key
        if not self.api_key:
            logger.warning("Gemini API Key is missing.")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)

    async def translate_to_persian(self, srt_content: str) -> str:
        """
        Translates input SRT content into fluent Persian (Farsi) using gemini-2.5-flash.
        Preserves exact timestamps and line numbering.
        """
        if not self.client:
            raise RuntimeError("Gemini API Key is not configured. Cannot perform translation.")

        if not srt_content.strip():
            raise ValueError("Input SRT content is empty.")

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

        logger.info("Sending SRT content to Gemini (gemini-2.5-flash) for Persian translation...")

        def _do_translate():
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            return response.text

        try:
            raw_response = await asyncio.to_thread(_do_translate)
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise RuntimeError(f"Gemini translation error: {e}")

        if not raw_response:
            raise RuntimeError("Gemini returned empty translation response.")

        clean_srt = clean_srt_response(raw_response)
        logger.info("Persian subtitle translation completed successfully.")
        return clean_srt
