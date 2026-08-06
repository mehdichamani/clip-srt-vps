import asyncio
import logging
import threading
from typing import Optional
from groq import Groq

try:
    from google import genai
except ImportError:
    genai = None

from deep_translator import GoogleTranslator

from app.config import settings
from app.utils.srt import clean_srt_response, parse_srt_blocks

logger = logging.getLogger("clip_srt_bot")


def mask_key(key: str) -> str:
    """Masks an API key for safe logging output."""
    if not key:
        return "None"
    if len(key) <= 10:
        return key[:2] + "..." + key[-2:]
    return key[:6] + "..." + key[-4:]


class TranslationService:
    """Service for translating SRT subtitles into Persian using Google Translate or AI models (Groq/Gemini)."""

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

    async def translate_to_persian(self, srt_content: str, engine: str = "ai") -> str:
        """
        Translates input SRT content into Persian (Farsi).
        
        Args:
            srt_content: Raw SRT subtitle content.
            engine: "google" for Google Translate, or "ai" for Groq AI (with Gemini fallback).
        """
        if not srt_content.strip():
            raise ValueError("Input SRT content is empty.")

        if engine == "google":
            return await self.translate_with_google(srt_content)
        else:
            return await self.translate_with_ai(srt_content)

    async def translate_with_google(self, srt_content: str) -> str:
        """
        Translates SRT content to Persian block-by-block using Google Translate (deep-translator).
        Preserves exact timestamps and indices while preventing hallucinations/truncation.
        """
        blocks = parse_srt_blocks(srt_content)
        if not blocks:
            raise ValueError("Failed to parse SRT blocks for Google Translation.")

        logger.info(f"Translating {len(blocks)} subtitle blocks using Google Translate API...")

        def _do_google_translate(blocks_list):
            translator = GoogleTranslator(source="auto", target="fa")
            texts = [b["text"] for b in blocks_list]
            
            # Batch translate in chunks of 50 to avoid request length limits
            chunk_size = 50
            translated_texts = []
            for i in range(0, len(texts), chunk_size):
                chunk = texts[i:i + chunk_size]
                res = translator.translate_batch(chunk)
                if isinstance(res, list):
                    translated_texts.extend([str(t) if t else "" for t in res])
                else:
                    translated_texts.extend(chunk)

            translated_blocks = []
            for idx, b in enumerate(blocks_list):
                trans_text = translated_texts[idx] if idx < len(translated_texts) else b["text"]
                translated_blocks.append(
                    f"{b['index']}\n{b['time']}\n{trans_text}\n"
                )
            return "\n".join(translated_blocks)

        try:
            result = await asyncio.to_thread(_do_google_translate, blocks)
            logger.info("Persian subtitle translation completed successfully via Google Translate.")
            return result
        except Exception as e:
            logger.error(f"Google Translate failed: {e}")
            raise RuntimeError(f"Google Translate error: {e}")

    async def translate_with_ai(self, srt_content: str) -> str:
        """
        Translates input SRT content into fluent Persian (Farsi) using Groq API (openai/gpt-oss-120b).
        Preserves exact timestamps and line numbering.
        Falls back to Gemini API if configured and Groq fails.
        """
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
        model_name = settings.groq_translate_model or "openai/gpt-oss-120b"
        if groq_key:
            masked = mask_key(groq_key)
            logger.info(f"Sending SRT content to Groq API ({model_name}) using key [{masked}]...")

            def _do_groq_translate(key: str):
                client = Groq(api_key=key)
                response = client.chat.completions.create(
                    model=model_name,
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

