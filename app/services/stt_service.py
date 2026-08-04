import asyncio
import logging
import os
from typing import Dict, Any, List
from groq import Groq

from app.config import settings
from app.utils.srt import format_segments_to_srt

logger = logging.getLogger("clip_srt_bot")

class STTService:
    """Service for speech-to-text using Groq's whisper-large-v3."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.groq_api_key
        if not self.api_key:
            logger.warning("Groq API Key is missing.")
            self.client = None
        else:
            self.client = Groq(api_key=self.api_key)

    async def transcribe(self, audio_file_path: str) -> str:
        """
        Transcribes audio file using Groq whisper-large-v3 with verbose_json.
        Returns standard SRT subtitle text with precise timestamps.
        """
        if not self.client:
            raise RuntimeError("Groq API Key is not configured. Cannot perform speech transcription.")
            
        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"Audio file does not exist: {audio_file_path}")

        logger.info(f"Sending audio file {audio_file_path} to Groq whisper-large-v3...")

        def _do_transcribe():
            with open(audio_file_path, "rb") as audio_file:
                return self.client.audio.transcriptions.create(
                    file=(os.path.basename(audio_file_path), audio_file),
                    model="whisper-large-v3",
                    response_format="verbose_json"
                )

        try:
            transcription = await asyncio.to_thread(_do_transcribe)
        except Exception as e:
            logger.error(f"Groq STT API call failed: {e}")
            raise RuntimeError(f"Groq STT transcription failed: {e}")

        # Extract segments safely
        segments = getattr(transcription, "segments", None)
        if segments is None and isinstance(transcription, dict):
            segments = transcription.get("segments", [])

        if not segments:
            # Fallback to plain text if segments array is missing
            raw_text = getattr(transcription, "text", "") or (transcription.get("text", "") if isinstance(transcription, dict) else "")
            if raw_text:
                return f"1\n00:00:00,000 --> 00:00:10,000\n{raw_text.strip()}"
            raise RuntimeError("Groq transcription returned no segments or speech text.")

        srt_content = format_segments_to_srt(segments)
        logger.info("Groq transcription and SRT formatting completed successfully.")
        return srt_content
