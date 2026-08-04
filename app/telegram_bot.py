import asyncio
import logging
import os
import shutil
import tempfile
import uuid
import time
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from app.config import settings
from app.services.downloader import DownloaderService
from app.services.media_processor import MediaProcessor
from app.services.stt_service import STTService
from app.services.translator import TranslationService

logger = logging.getLogger("clip_srt_bot")

# Track active jobs to handle callback responses
active_jobs = {}

def clean_old_jobs():
    """Removes temporary directories for jobs older than 1 hour."""
    now = time.time()
    expired = []
    for job_id, job_info in active_jobs.items():
        if now - job_info.get('timestamp', 0) > 3600:
            expired.append(job_id)
    for job_id in expired:
        job_info = active_jobs.pop(job_id, None)
        if job_info and 'work_dir' in job_info:
            logger.info(f"Cleaning up expired job {job_id} at {job_info['work_dir']}")
            shutil.rmtree(job_info['work_dir'], ignore_errors=True)

def srt_to_line_by_line(srt_content: str) -> str:
    """Extracts only text lines from an SRT subtitles format content."""
    lines = []
    current_text = []
    in_text = False
    for line in srt_content.splitlines():
        line_str = line.strip()
        if not line_str:
            if current_text:
                lines.append(" ".join(current_text))
                current_text = []
            in_text = False
            continue
        if line_str.isdigit():
            in_text = False
            continue
        if "-->" in line_str:
            in_text = True
            continue
        if in_text:
            current_text.append(line_str)
    if current_text:
        lines.append(" ".join(current_text))
    return "\n".join(lines)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    welcome_text = (
        "👋 **به ربات زیرنویس‌ساز خوش آمدید!**\n\n"
        "لطفاً یک **ویدیو کوتاه**، **فایل صوتی**، **پیام صوتی** یا یک **لینک ویدیو** (یوتیوب، تیک‌تاک، توییتر، اینستاگرام و غیره) برای من ارسال کنید.\n\n"
        "✨ **کارهایی که من انجام می‌دهم:**\n"
        "۱. استخراج صدا و تبدیل گفتار به متن با **Groq Whisper (whisper-large-v3)**.\n"
        "۲. ترجمه زیرنویس به فارسی روان با **Google Gemini (gemini-2.5-flash)**.\n"
        "۳. امکان انتخاب دریافت ویدیو با زیرنویس سافت‌ساب یا فقط متن ترجمه شده."
    )
    if update.message:
        await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command."""
    help_text = (
        "ℹ️ **راهنمای استفاده از ربات:**\n\n"
        "• **ارسال فایل رسانه:** یک ویدیو، فایل صوتی یا ویس را در چت ارسال کنید.\n"
        "• **ارسال لینک:** لینک ویدیو از یوتیوب، توییتر، تیک‌تاک یا اینستاگرام را بفرستید.\n"
        "• پس از اتمام پردازش و ترجمه، می‌توانید بین دریافت ویدیو با زیرنویس سافت‌ساب یا متن ترجمه شده یکی را انتخاب کنید."
    )
    if update.message:
        await update.message.reply_text(help_text, parse_mode="Markdown")

async def process_media_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Core processor for video/audio attachments or media URLs."""
    if not update.message:
        return

    # Periodically clean expired temporary jobs
    clean_old_jobs()

    # Check API Key configuration
    if not settings.groq_api_key or not settings.gemini_api_key:
        await update.message.reply_text(
            "⚠️ **خطای پیکربندی:** کلیدهای API برای Groq یا Gemini در سرور تنظیم نشده‌اند. لطفاً متغیرهای محیطی را بررسی کنید."
        )
        return

    message = update.message
    status_msg = await message.reply_text("⏳ در حال پردازش درخواست شما...")
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
            await status_msg.edit_text("📥 در حال دانلود ویدیو از تلگرام...")
            await DownloaderService.download_telegram_file(context.bot, message.video.file_id, input_path)

        elif message.document and (message.document.mime_type or "").startswith(("video/", "audio/")):
            is_video = (message.document.mime_type or "").startswith("video/")
            ext = os.path.splitext(message.document.file_name or "media")[1] or (".mp4" if is_video else ".mp3")
            input_path = os.path.join(work_dir, f"input{ext}")
            await status_msg.edit_text("📥 در حال دانلود فایل رسانه از تلگرام...")
            await DownloaderService.download_telegram_file(context.bot, message.document.file_id, input_path)

        elif message.audio or message.voice:
            is_video = False
            file_id = message.audio.file_id if message.audio else message.voice.file_id
            input_path = os.path.join(work_dir, "input.m4a" if message.voice else "input.mp3")
            await status_msg.edit_text("📥 در حال دانلود صدا از تلگرام...")
            await DownloaderService.download_telegram_file(context.bot, file_id, input_path)

        elif message.text:
            url = DownloaderService.extract_url(message.text)
            if not url:
                await status_msg.edit_text("💡 لطفاً یک ویدیو، فایل صوتی یا لینک معتبر ارسال کنید.")
                if os.path.exists(work_dir):
                    shutil.rmtree(work_dir, ignore_errors=True)
                return
            await status_msg.edit_text(f"🌐 در حال دانلود رسانه از لینک: `{url}`...", parse_mode="Markdown")
            input_path = await DownloaderService.download_web_media(url, work_dir)
            is_video = input_path.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".avi"))

        else:
            await status_msg.edit_text("❓ فرمت فایل پشتیبانی نمی‌شود. لطفاً ویدیو، صدا یا لینک ویدیو بفرستید.")
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
            return

        # 2. Extract Audio (16kHz mono MP3)
        audio_path = os.path.join(work_dir, "extracted_audio.mp3")
        await status_msg.edit_text("🎵 در حال استخراج صدا...")
        await MediaProcessor.extract_audio(input_path, audio_path)

        # 3. Speech-to-Text via Groq Whisper-large-v3
        await status_msg.edit_text("🎙️ در حال تبدیل گفتار به متن با Groq Whisper...")
        stt_service = STTService()
        english_srt = await stt_service.transcribe(audio_path)

        # 4. Translation to Persian via Gemini 2.5 Flash
        await status_msg.edit_text("🌐 در حال ترجمه زیرنویس به فارسی با Gemini...")
        translation_service = TranslationService()
        persian_srt = await translation_service.translate_to_persian(english_srt)

        # Save Persian SRT to file
        srt_file_path = os.path.join(work_dir, "subtitles_persian.srt")
        with open(srt_file_path, "w", encoding="utf-8") as f:
            f.write(persian_srt)

        # Store job information for the callback query handler
        active_jobs[job_id] = {
            'work_dir': work_dir,
            'is_video': is_video,
            'srt_file_path': srt_file_path,
            'input_path': input_path,
            'timestamp': time.time()
        }

        # 5. Present the 2 choices using inline keyboard
        keyboard = [
            [
                InlineKeyboardButton("🎥 ویدیو با زیرنویس (Softsub)", callback_data=f"softsub_{job_id}"),
                InlineKeyboardButton("📝 فقط متن ترجمه (خط به خط)", callback_data=f"text_{job_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await status_msg.edit_text(
            "✅ ترجمه با موفقیت انجام شد. لطفاً فرمت خروجی مورد نظر خود را انتخاب کنید:",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ **عملیات با خطا مواجه شد:** {str(e)[:300]}")
        # Clean up directory on failure
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the selection of the output format by the user."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not (data.startswith("softsub_") or data.startswith("text_")):
        return

    action, job_id = data.split("_", 1)
    job_info = active_jobs.get(job_id)

    if not job_info:
        await query.message.reply_text("❌ خطا: اطلاعات این درخواست دیگر در دسترس نیست (احتمالاً منقضی شده است).")
        return

    work_dir = job_info['work_dir']
    srt_file_path = job_info['srt_file_path']
    input_path = job_info['input_path']
    is_video = job_info['is_video']

    # Keep status updated
    status_msg = await query.message.reply_text("⏳ در حال آماده‌سازی فایل انتخابی شما...")

    try:
        if action == "softsub":
            if not is_video:
                await status_msg.edit_text("⚠️ این فایل ویدیو نیست و امکان قرار دادن زیرنویس روی آن وجود ندارد.")
                return

            await status_msg.edit_text("🎬 در حال ریماکس کردن زیرنویس روی ویدیو...")
            output_video_path = os.path.join(work_dir, "subtitled_output.mp4")
            await MediaProcessor.embed_subtitles_soft(input_path, srt_file_path, output_video_path)

            await status_msg.edit_text("📤 در حال ارسال ویدیو بدون فشرده‌سازی...")
            # Send as uncompressed video (document)
            with open(output_video_path, "rb") as vid_file:
                await query.message.reply_document(
                    document=vid_file,
                    filename="subtitled_video.mp4",
                    caption="✅ **ویدیو با زیرنویس سافت‌ساب آماده شد!**"
                )

        elif action == "text":
            await status_msg.edit_text("📝 در حال استخراج متن ترجمه...")
            with open(srt_file_path, "r", encoding="utf-8") as f:
                srt_content = f.read()

            translated_text = srt_to_line_by_line(srt_content)

            if len(translated_text) < 4000:
                await query.message.reply_text(
                    f"📝 **متن ترجمه شده خط به خط:**\n\n{translated_text}"
                )
            else:
                txt_file_path = os.path.join(work_dir, "translation.txt")
                with open(txt_file_path, "w", encoding="utf-8") as tf:
                    tf.write(translated_text)
                with open(txt_file_path, "rb") as tf:
                    await query.message.reply_document(
                        document=tf,
                        filename="translation.txt",
                        caption="📝 **متن ترجمه شده خط به خط**"
                    )

        # Cleanup
        active_jobs.pop(job_id, None)
        shutil.rmtree(work_dir, ignore_errors=True)
        await query.message.delete()  # delete the inline buttons message
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Error handling callback choice {action}: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ خطایی در پردازش و ارسال فایل رخ داد: {str(e)[:300]}")
        # Clean up anyway on error
        active_jobs.pop(job_id, None)
        shutil.rmtree(work_dir, ignore_errors=True)

def create_telegram_application() -> Application:
    """Builds and configures python-telegram-bot Application instance."""
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is missing.")

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()

    # Register Command, Message & Callback Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL | filters.TEXT,
        process_media_job
    ))

    return app
