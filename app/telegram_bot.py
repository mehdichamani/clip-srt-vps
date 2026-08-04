import asyncio
import html
import logging
import os
import shutil
import tempfile
import uuid
import time
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
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
from app.utils.srt import merge_bilingual_srt, srt_to_alternating_text

logger = logging.getLogger("clip_srt_bot")

# Track active jobs to handle callback responses and retries
active_jobs = {}
MAX_TG_FILE_SIZE = 20 * 1024 * 1024  # 20 MB Telegram Bot API limit

async def safe_edit_text(message, text: str, **kwargs):
    """Safely edits a Telegram message text, suppressing 'Message is not modified' error."""
    try:
        return await message.edit_text(text, **kwargs)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return message
        raise e


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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    welcome_text = (
        "👋 <b>به ربات زیرنویس‌ساز خوش آمدید!</b>\n\n"
        "لطفاً یک <b>ویدیو کوتاه</b>، <b>فایل صوتی</b>، <b>پیام صوتی</b> یا یک <b>لینک ویدیو</b> (اینستاگرام، یوتیوب، تیک‌تاک، توییتر و ...) ارسال کنید.\n\n"
        "✨ <b>امکانات ربات:</b>\n"
        "۱. استخراج صدا و تبدیل گفتار به متن با <b>Groq Whisper (whisper-large-v3)</b>.\n"
        "۲. ترجمه زیرنویس به فارسی روان با <b>Google Gemini (gemini-2.5-flash)</b> به صورت خط به خط متناوب.\n"
        "۳. امکان انتخاب دریافت ویدیو به صورت فایل با زیرنویس سافت‌ساب یا فقط متن ترجمه شده.\n\n"
        "📖 جهت مشاهده راهنما و فرمت‌های پشتیبانی شده: /help\n"
        "ℹ️ درباره توسعه‌دهنده و پروژه: /about"
    )
    if update.message:
        await update.message.reply_text(welcome_text, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command with detailed input documentation."""
    help_text = (
        "📖 <b>راهنمای جامع استفاده از ربات زیرنویس‌ساز</b>\n\n"
        "📥 <b>ورودی‌های پشتیبانی شده:</b>\n\n"
        "۱. <b>ارسال مستقیم فایل رسانه:</b>\n"
        "• <b>ویدیوها:</b> MP4, MKV, MOV, AVI, WEBM, FLV, M4V (حداکثر ۲۰ مگابایت)\n"
        "• <b>صوت و ویس:</b> MP3, WAV, AAC, M4A, FLAC, OGG, OPUS و ویس‌های تلگرام\n\n"
        "۲. <b>ارسال لینک رسانه (بدون محدودیت حجم):</b>\n"
        "• <b>اینستاگرام:</b> ریلمز (Reels)، پست‌ها و کلیپ‌های IGTV\n"
        "• <b>یوتیوب:</b> ویدیوهای اصلی و یوتیوب شورتس (Shorts)\n"
        "• <b>تیک‌تاک & توییتر (X):</b> کلیپ‌ها و ویدیوهای توییت شده\n"
        "• <b>لینک مستقیم دانلود:</b> فایل‌های مستقیم .mp4 و .mp3\n\n"
        "⚙️ <b>دستورات ربات:</b>\n"
        "• /start - شروع به کار و معرفی اولیه\n"
        "• /help - راهنمای جامع و فرمت‌های پشتیبانی شده\n"
        "• /about - شناسنامه سازنده، سورس‌کد و تکنولوژی‌ها\n\n"
        "🔄 <b>مراحل پردازش:</b>\n"
        "۱. ارسال فایل یا لینک ⬅️ ۲. استخراج صدا و تبدیل گفتار به متن ⬅️ ۳. ترجمه فارسی خط به خط ⬅️ ۴. انتخاب خروجی (ویدیو زیرنویس‌دار یا متن ترجمه)."
    )
    if update.message:
        await update.message.reply_text(help_text, parse_mode="HTML")

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /about command for developer branding and system specs."""
    about_text = (
        "👤 <b>درباره ربات و شناسنامه توسعه‌دهنده</b>\n\n"
        "👨‍💻 <b>توسعه‌دهنده:</b> مهدی چمنی\n"
        "📧 <b>ایمیل:</b> <code>mahdi.chamani20@gmail.com</code>\n"
        "💬 <b>تلگرام:</b> <a href=\"https://t.me/mehdichamanni\">@mehdichamanni</a>\n\n"
        "📦 <b>مخزن گیت‌هاب (GitHub):</b>\n"
        "🔗 <a href=\"https://github.com/mehdichamani/clip-srt-vps\">github.com/mehdichamani/clip-srt-vps</a>\n\n"
        "🛠 <b>تکنولوژی‌های استفاده شده (Tech Stack):</b>\n"
        "• <b>دانلود رسانه:</b> yt-dlp & PTB API\n"
        "• <b>پردازش رسانه:</b> FFmpeg (16kHz Audio Extraction & Soft Subtitle Remuxing)\n"
        "• <b>تبدیل گفتار به متن (STT):</b> Groq Whisper API (whisper-large-v3) / OpenAI\n"
        "• <b>ترجمه هوشمند:</b> Google Gemini API (gemini-2.5-flash) / Groq / OpenAI\n"
        "• <b>سرور & وب‌هوک:</b> FastAPI + Uvicorn + python-telegram-bot\n\n"
        "☁️ <b>میزبانی:</b> hosted by <a href=\"https://render.com\">render.com</a>"
    )
    if update.message:
        await update.message.reply_text(about_text, parse_mode="HTML", disable_web_page_preview=True)


async def process_media_job(update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: Optional[str] = None) -> None:
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
    
    if not job_id:
        job_id = str(uuid.uuid4())[:8]
        
    work_dir = os.path.join(tempfile.gettempdir(), f"clip_srt_{job_id}")
    os.makedirs(work_dir, exist_ok=True)

    # Save initial job info with update object for retries
    active_jobs[job_id] = {
        'update': update,
        'work_dir': work_dir,
        'timestamp': time.time()
    }

    input_path: Optional[str] = None
    is_video = False

    try:
        # 1. Determine input source (Telegram File or Web URL)
        if message.video:
            if message.video.file_size and message.video.file_size > MAX_TG_FILE_SIZE:
                await safe_edit_text(
                    status_msg,
                    "⚠️ <b>حجم فایل بیش از ۲۰ مگابایت است:</b>\n\n"
                    "به دلیل محدودیت‌های تلگرام، امکان دانلود مستقیم فایل‌های بالای ۲۰ مگابایت توسط ربات‌ها وجود ندارد.\n\n"
                    "💡 <b>راهکار:</b> لطفاً <b>لینک مستقیم ویدیو</b> (از یوتیوب، اینستاگرام، تیک‌تاک و ...) را ارسال کنید تا بدون محدودیت پردازش شود.",
                    parse_mode="HTML"
                )
                active_jobs.pop(job_id, None)
                if os.path.exists(work_dir):
                    shutil.rmtree(work_dir, ignore_errors=True)
                return

            is_video = True
            ext = ".mp4"
            input_path = os.path.join(work_dir, f"input{ext}")
            await safe_edit_text(status_msg, "📥 در حال دانلود ویدیو از تلگرام...")
            await DownloaderService.download_telegram_file(context.bot, message.video.file_id, input_path)

        elif message.document and (message.document.mime_type or "").startswith(("video/", "audio/")):
            if message.document.file_size and message.document.file_size > MAX_TG_FILE_SIZE:
                await safe_edit_text(
                    status_msg,
                    "⚠️ <b>حجم فایل بیش از ۲۰ مگابایت است:</b>\n\n"
                    "به دلیل محدودیت‌های تلگرام، امکان دانلود مستقیم فایل‌های بالای ۲۰ مگابایت توسط ربات‌ها وجود ندارد.\n\n"
                    "💡 <b>راهکار:</b> لطفاً <b>لینک مستقیم ویدیو</b> را ارسال کنید تا بدون محدودیت پردازش شود.",
                    parse_mode="HTML"
                )
                active_jobs.pop(job_id, None)
                if os.path.exists(work_dir):
                    shutil.rmtree(work_dir, ignore_errors=True)
                return

            is_video = (message.document.mime_type or "").startswith("video/")
            ext = os.path.splitext(message.document.file_name or "media")[1] or (".mp4" if is_video else ".mp3")
            input_path = os.path.join(work_dir, f"input{ext}")
            await safe_edit_text(status_msg, "📥 در حال دانلود فایل رسانه از تلگرام...")
            await DownloaderService.download_telegram_file(context.bot, message.document.file_id, input_path)

        elif message.audio or message.voice:
            audio_obj = message.audio or message.voice
            if audio_obj and audio_obj.file_size and audio_obj.file_size > MAX_TG_FILE_SIZE:
                await safe_edit_text(
                    status_msg,
                    "⚠️ <b>حجم فایل صوتی بیش از ۲۰ مگابایت است:</b>\nلطفاً لینک مستقیم فایل صوتی یا ویدیو را ارسال کنید.",
                    parse_mode="HTML"
                )
                active_jobs.pop(job_id, None)
                if os.path.exists(work_dir):
                    shutil.rmtree(work_dir, ignore_errors=True)
                return

            is_video = False
            file_id = message.audio.file_id if message.audio else message.voice.file_id
            input_path = os.path.join(work_dir, "input.m4a" if message.voice else "input.mp3")
            await safe_edit_text(status_msg, "📥 در حال دانلود صدا از تلگرام...")
            await DownloaderService.download_telegram_file(context.bot, file_id, input_path)

        elif message.text:
            url = DownloaderService.extract_url(message.text)
            if not url:
                await safe_edit_text(status_msg, "💡 لطفاً یک ویدیو، فایل صوتی یا لینک معتبر ارسال کنید.")
                active_jobs.pop(job_id, None)
                if os.path.exists(work_dir):
                    shutil.rmtree(work_dir, ignore_errors=True)
                return
            await safe_edit_text(status_msg, f"🌐 در حال دانلود رسانه از لینک: `{url}`...", parse_mode="Markdown")
            input_path = await DownloaderService.download_web_media(url, work_dir)
            is_video = input_path.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".avi"))

        else:
            await safe_edit_text(status_msg, "❓ فرمت فایل پشتیبانی نمی‌شود. لطفاً ویدیو، صدا یا لینک ویدیو بفرستید.")
            active_jobs.pop(job_id, None)
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
            return

        # 2. Extract Audio (16kHz mono MP3)
        audio_path = os.path.join(work_dir, "extracted_audio.mp3")
        await safe_edit_text(status_msg, "🎵 در حال استخراج صدا...")
        await MediaProcessor.extract_audio(input_path, audio_path)

        # 3. Speech-to-Text via Groq Whisper-large-v3
        await safe_edit_text(status_msg, "🎙️ در حال تبدیل گفتار به متن با Groq Whisper...")
        stt_service = STTService()
        english_srt = await stt_service.transcribe(audio_path)

        # 4. Translation to Persian via Gemini 2.5 Flash
        await safe_edit_text(status_msg, "🌐 در حال ترجمه زیرنویس به فارسی با Gemini...")
        translation_service = TranslationService()
        persian_srt = await translation_service.translate_to_persian(english_srt)

        # 5. Format into line-by-line alternating subtitles (Line 1: Original, Line 2: Persian)
        bilingual_srt = merge_bilingual_srt(english_srt, persian_srt)

        srt_file_path = os.path.join(work_dir, "subtitles_bilingual.srt")
        with open(srt_file_path, "w", encoding="utf-8") as f:
            f.write(bilingual_srt)

        # Store job information for the callback query handler
        active_jobs[job_id].update({
            'is_video': is_video,
            'srt_file_path': srt_file_path,
            'input_path': input_path,
            'timestamp': time.time()
        })

        # Send a NEW message to notify completion and ask for format selection
        keyboard = [
            [
                InlineKeyboardButton("🎥 ویدیو با زیرنویس (Softsub)", callback_data=f"softsub_{job_id}"),
                InlineKeyboardButton("📝 فقط متن ترجمه (خط به خط)", callback_data=f"text_{job_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text(
            "✅ ترجمه با موفقیت انجام شد. لطفاً فرمت خروجی مورد نظر خود را انتخاب کنید:",
            reply_markup=reply_markup
        )

    except BadRequest as br_err:
        err_msg = str(br_err)
        if "message is not modified" in err_msg.lower():
            logger.debug(f"Ignored 'Message is not modified' error: {br_err}")
            return
        logger.error(f"Telegram BadRequest in process_media_job: {br_err}")
        if "file is too big" in err_msg.lower():
            user_msg = (
                "⚠️ <b>حجم فایل بیش از حد مجاز تلگرام است:</b>\n\n"
                "تلگرام اجازه دانلود فایل‌های بالای ۲۰ مگابایت را به ربات‌ها نمی‌دهد.\n"
                "💡 <b>راهکار:</b> لطفاً <b>لینک مستقیم ویدیو</b> را ارسال کنید."
            )
        else:
            user_msg = f"❌ <b>خطای درخواست تلگرام:</b>\n<code>{html.escape(err_msg[:300])}</code>"
        
        await message.reply_text(user_msg, parse_mode="HTML")
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        # Send a NEW message with HTML-escaped error details and Retry button
        retry_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f"retry_{job_id}")]
        ])
        safe_err = html.escape(str(e)[:300])
        await message.reply_text(
            f"❌ <b>عملیات با خطا مواجه شد:</b>\n<code>{safe_err}</code>\n\nمی‌توانید با دکمه زیر مجدداً تلاش کنید:",
            reply_markup=retry_keyboard,
            parse_mode="HTML"
        )
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles callback buttons: Retry and output format selection."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not (data.startswith("softsub_") or data.startswith("text_") or data.startswith("retry_")):
        return

    # Handle Retry action
    if data.startswith("retry_"):
        _, job_id = data.split("_", 1)
        job_info = active_jobs.get(job_id)
        if not job_info or 'update' not in job_info:
            await query.message.reply_text("❌ خطا: اطلاعات این درخواست دیگر در دسترس نیست (احتمالاً منقضی شده است). لطفاً فایل یا لینک را دوباره ارسال کنید.")
            return
        
        orig_update = job_info['update']
        if 'work_dir' in job_info and os.path.exists(job_info['work_dir']):
            shutil.rmtree(job_info['work_dir'], ignore_errors=True)
            
        await query.message.reply_text("🔄 در حال تلاش مجدد برای پردازش...")
        await process_media_job(orig_update, context, job_id=job_id)
        return

    action, job_id = data.split("_", 1)
    job_info = active_jobs.get(job_id)

    if not job_info or 'srt_file_path' not in job_info:
        await query.message.reply_text("❌ خطا: اطلاعات این درخواست دیگر در دسترس نیست (احتمالاً منقضی شده است). لطفاً فایل را دوباره ارسال کنید.")
        return

    work_dir = job_info['work_dir']
    srt_file_path = job_info['srt_file_path']
    input_path = job_info['input_path']
    is_video = job_info['is_video']

    try:
        if action == "softsub":
            if not is_video:
                await query.message.reply_text("⚠️ این فایل ویدیو نیست و امکان قرار دادن زیرنویس روی آن وجود ندارد.")
                return

            status_msg = await query.message.reply_text("🎬 در حال ریماکس کردن زیرنویس سافت‌ساب روی ویدیو...")
            output_video_path = os.path.join(work_dir, "subtitled_output.mp4")
            await MediaProcessor.embed_subtitles_soft(input_path, srt_file_path, output_video_path)

            # Always send clip output explicitly as document attachment (send_document / reply_document)
            with open(output_video_path, "rb") as vid_file:
                await query.message.reply_document(
                    document=vid_file,
                    filename="subtitled_video.mp4",
                    caption="✅ **ویدیو با زیرنویس سافت‌ساب آماده شد!**"
                )

        elif action == "text":
            with open(srt_file_path, "r", encoding="utf-8") as f:
                srt_content = f.read()

            translated_text = srt_to_alternating_text(srt_content)

            if len(translated_text) < 4000:
                await query.message.reply_text(
                    f"📝 **متن ترجمه شده خط به خط (زبان اصلی / فارسی):**\n\n{translated_text}"
                )
            else:
                txt_file_path = os.path.join(work_dir, "translation.txt")
                with open(txt_file_path, "w", encoding="utf-8") as tf:
                    tf.write(translated_text)
                with open(txt_file_path, "rb") as tf:
                    await query.message.reply_document(
                        document=tf,
                        filename="translation.txt",
                        caption="📝 **متن ترجمه شده خط به خط (زبان اصلی / فارسی)**"
                    )

        # Clean up job directory after success
        active_jobs.pop(job_id, None)
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"Error handling callback choice {action}: {e}", exc_info=True)
        retry_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f"retry_{job_id}")]
        ])
        safe_err = html.escape(str(e)[:300])
        await query.message.reply_text(
            f"❌ <b>خطایی در پردازش و ارسال فایل رخ داد:</b>\n<code>{safe_err}</code>\n\nمی‌توانید مجدداً تلاش کنید:",
            reply_markup=retry_keyboard,
            parse_mode="HTML"
        )

def create_telegram_application() -> Application:
    """Builds and configures python-telegram-bot Application instance."""
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is missing.")

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()

    # Register Command, Message & Callback Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL | filters.TEXT,
        process_media_job
    ))

    return app

