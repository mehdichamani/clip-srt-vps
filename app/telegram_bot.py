import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import settings
from app.services.downloader import DownloaderService
from app.services.media_processor import MediaProcessor
from app.services.stt_service import STTService
from app.services.translator import TranslationService

logger = logging.getLogger("clip_srt_bot")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    welcome_text = (
        "👋 **Welcome to Clip SRT Bot v2!**\n\n"
        "Send me any **short video**, **audio file**, **voice message**, or a **video link** (YouTube, TikTok, Twitter/X, etc.).\n\n"
        "✨ **What I do:**\n"
        "1. Extract audio & transcribe speech using **Groq Whisper (whisper-large-v3)**.\n"
        "2. Translate subtitles to natural **Persian (Farsi)** using **Google Gemini (gemini-2.5-flash)**.\n"
        "3. Fast remux soft subtitles into your video and return both the video and the `.srt` file!"
    )
    if update.message:
        await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command."""
    help_text = (
        "ℹ️ **How to use Clip SRT Bot v2:**\n\n"
        "• **Upload Media:** Send a video, audio, or voice note directly in chat.\n"
        "• **Send Link:** Paste a video link from YouTube, Twitter, TikTok, or Instagram.\n"
        "• The bot will automatically generate Persian soft subtitles and return the subtitled video + SRT file."
    )
    if update.message:
        await update.message.reply_text(help_text, parse_mode="Markdown")

async def process_media_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Core processor for video/audio attachments or media URLs."""
    if not update.message:
        return

    # Check API Key configuration
    if not settings.groq_api_key or not settings.gemini_api_key:
        await update.message.reply_text(
            "⚠️ **Configuration Error:** API keys for Groq or Gemini are missing on the server. Please check environment variables."
        )
        return

    message = update.message
    status_msg = await message.reply_text("⏳ Processing your request...")
    job_id = str(uuid.uuid4())[:8]
    work_dir = os.path.join(tempfile.gettempdir(), f"clip_srt_{job_id}")
    os.makedirs(work_dir, exist_ok=True)

    input_path: Optional[str] = None
    is_video = False

    try:
        # 1. Determine input source (Telegram File or Web URL)
        if message.video:
            is_video = True
            ext = ".mp4"
            input_path = os.path.join(work_dir, f"input{ext}")
            await status_msg.edit_text("📥 Downloading video from Telegram...")
            await DownloaderService.download_telegram_file(context.bot, message.video.file_id, input_path)

        elif message.document and (message.document.mime_type or "").startswith(("video/", "audio/")):
            is_video = (message.document.mime_type or "").startswith("video/")
            ext = os.path.splitext(message.document.file_name or "media")[1] or (".mp4" if is_video else ".mp3")
            input_path = os.path.join(work_dir, f"input{ext}")
            await status_msg.edit_text("📥 Downloading media file from Telegram...")
            await DownloaderService.download_telegram_file(context.bot, message.document.file_id, input_path)

        elif message.audio or message.voice:
            is_video = False
            file_id = message.audio.file_id if message.audio else message.voice.file_id
            input_path = os.path.join(work_dir, "input.m4a" if message.voice else "input.mp3")
            await status_msg.edit_text("📥 Downloading audio from Telegram...")
            await DownloaderService.download_telegram_file(context.bot, file_id, input_path)

        elif message.text:
            url = DownloaderService.extract_url(message.text)
            if not url:
                await status_msg.edit_text("💡 Please send a video file, audio note, or a valid URL link.")
                return
            await status_msg.edit_text(f"🌐 Downloading media from link: `{url}`...", parse_mode="Markdown")
            input_path = await DownloaderService.download_web_media(url, work_dir)
            is_video = input_path.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".avi"))

        else:
            await status_msg.edit_text("❓ Unsupported media format. Please send a video, audio, or video link.")
            return

        # 2. Extract Audio (16kHz mono MP3)
        audio_path = os.path.join(work_dir, "extracted_audio.mp3")
        await status_msg.edit_text("🎵 Extracting audio stream (16kHz mono MP3)...")
        await MediaProcessor.extract_audio(input_path, audio_path)

        # 3. Speech-to-Text via Groq Whisper-large-v3
        await status_msg.edit_text("🎙️ Transcribing speech with Groq Whisper (`whisper-large-v3`)...", parse_mode="Markdown")
        stt_service = STTService()
        english_srt = await stt_service.transcribe(audio_path)

        # 4. Translation to Persian via Gemini 2.5 Flash
        await status_msg.edit_text("🌐 Translating subtitles to Persian using Gemini (`gemini-2.5-flash`)...", parse_mode="Markdown")
        translation_service = TranslationService()
        persian_srt = await translation_service.translate_to_persian(english_srt)

        # Save Persian SRT to file
        srt_file_path = os.path.join(work_dir, "subtitles_persian.srt")
        with open(srt_file_path, "w", encoding="utf-8") as f:
            f.write(persian_srt)

        # 5. Soft Subtitle Remuxing & Delivery
        if is_video:
            output_video_path = os.path.join(work_dir, "subtitled_output.mp4")
            await status_msg.edit_text("🎬 Remuxing soft subtitles into video...")
            await MediaProcessor.embed_subtitles_soft(input_path, srt_file_path, output_video_path)

            await status_msg.edit_text("📤 Uploading subtitled video...")
            with open(output_video_path, "rb") as vid_file:
                await message.reply_video(
                    video=vid_file,
                    caption="✅ **Subtitled Video Ready!** (Soft subtitles included)",
                    parse_mode="Markdown"
                )
        
        # Always send the SRT file as attachment as well
        with open(srt_file_path, "rb") as srt_file:
            await message.reply_document(
                document=srt_file,
                filename="subtitles_fa.srt",
                caption="📝 **Persian Subtitles (.srt)**"
            )

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ **Processing Failed:** {str(e)[:300]}")

    finally:
        # Cleanup temporary files
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)

def create_telegram_application() -> Application:
    """Builds and configures python-telegram-bot Application instance."""
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is missing.")

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()

    # Register Command & Message Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL | filters.TEXT,
        process_media_job
    ))

    return app
