# Clip SRT Bot v2 🎬📝

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED.svg)](https://www.docker.com/)
[![Render](https://img.shields.io/badge/Render-Deploy-black.svg)](https://render.com/)
[![Developer](https://img.shields.io/badge/Developer-Mehdi%20Chamani-orange.svg)](https://t.me/mehdichamanni)

[English](#english) | [فارسی](#فارسی)

---

<a name="english"></a>
## 🇬🇧 English Documentation

### 🌟 Overview & Key Features

**clip-srt-vps** is a lightweight, cloud-native Telegram bot and web service built with Python, FastAPI, and `python-telegram-bot`. It leverages state-of-the-art AI APIs (Groq Whisper, Google Gemini, OpenAI) and FFmpeg to extract audio, generate precise subtitle transcriptions, translate subtitles into fluent line-by-line Persian, and soft-embed subtitles into video clips on the fly.

- **Cloud-Native AI Workloads:** Uses Groq Whisper (`whisper-large-v3`) for lightning-fast speech-to-text with word-level timestamps.
- **Fluent Persian Translation:** Uses Google Gemini (`gemini-2.5-flash`) or OpenAI models for natural Persian translation while preserving `.srt` timing.
- **Line-by-Line Subtitles:** Produces alternating original language / Persian translation subtitles.
- **Fast Soft-Subtitle Embedding:** Soft-embeds subtitles into MP4/MOV containers via FFmpeg without full video re-encoding.
- **Web Video Download Support:** Downloads videos directly from social media platforms using `yt-dlp`.
- **Telegram Bot Webhook Integration:** Powered by FastAPI with automatic webhook setup on startup.

---

### 📂 Supported Input Files & Link Formats

#### Supported Media Upload Formats
You can directly upload media files to the bot (up to the Telegram 20 MB API limit):
- **Video Extensions:** `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`, `.flv`, `.m4v`
- **Audio & Voice Extensions:** `.mp3`, `.wav`, `.aac`, `.m4a`, `.flac`, `.ogg`, `.opus`, Telegram Voice messages (`.ogg`)

#### Supported Social Media & URL Links
Send video or audio URLs directly in chat for seamless processing without file size limits:
- **Instagram:** Reels, Posts, IGTV clips
- **YouTube:** YouTube Shorts, standard YouTube Videos
- **TikTok:** Public video clips
- **Twitter / X:** Video tweets
- **Direct Web Links:** Any publicly downloadable `.mp4`, `.mp3`, `.mkv` direct file URLs

---

### 🚀 Deployment Guide

#### 1. Deployment via Docker

```bash
# Clone the repository
git clone https://github.com/mehdichamani/clip-srt-vps.git
cd clip-srt-vps

# Build the Docker image
docker build -t clip-srt-vps .

# Run the container
docker run -d \
  --name clip-srt-bot \
  -p 8000:8000 \
  -e TELEGRAM_BOT_TOKEN="your_telegram_bot_token" \
  -e GROQ_API_KEY="your_groq_api_key" \
  -e GEMINI_API_KEY="your_gemini_api_key" \
  -e RENDER_EXTERNAL_URL="https://your-domain-or-ngrok.com" \
  clip-srt-vps
```

#### 2. VPS Deployment (Ubuntu / Debian)

```bash
# Install system dependencies
sudo apt-get update && sudo apt-get install -y ffmpeg python3-pip python3-venv git

# Clone repository & setup venv
git clone https://github.com/mehdichamani/clip-srt-vps.git
cd clip-srt-vps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your credentials

# Run application with Uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000
```

#### 3. Render Web Service Deployment

1. Create a new **Web Service** on [Render Dashboard](https://dashboard.render.com/).
2. Connect repository `https://github.com/mehdichamani/clip-srt-vps`.
3. Set Environment to **Python 3**.
4. Set **Build Command**:
   ```bash
   apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt
   ```
5. Set **Start Command**:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```

---

### 🔑 Environment Variables Reference

| Variable | Required | Description | Example |
| :--- | :---: | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | **Yes** | Telegram Bot token from [@BotFather](https://t.me/BotFather) | `123456789:ABCdef...` |
| `GROQ_API_KEY` | **Yes** | Groq API Key from [Groq Console](https://console.groq.com/) | `gsk_...` |
| `GEMINI_API_KEY` | **Yes** | Google Gemini API key from [Google AI Studio](https://aistudio.google.com/) | `AIzaSy...` |
| `OPENAI_API_KEY` | Optional | OpenAI API key (if using OpenAI services) | `sk-...` |
| `RENDER_EXTERNAL_URL` | **Yes** | Public HTTPS domain URL for Webhook setup (No trailing slash) | `https://clip-srt-bot-v2.onrender.com` |
| `WEBHOOK_SECRET` | Optional | Secret token for secure webhook authorization | `secret_token_123` |
| `INSTAGRAM_COOKIES` | Optional | Netscape format cookies content or file path for Instagram `yt-dlp` auth | `cookies.txt` content |
| `PORT` | Optional | Server listening port (Defaults to `8000`) | `8000` |

---

### 👤 Developer & Repository Branding

- **Repository:** [mehdichamani/clip-srt-vps](https://github.com/mehdichamani/clip-srt-vps)
- **Developer:** **Mehdi Chamani** (مهدی چمنی)
- **Email:** `mahdi.chamani20@gmail.com`
- **Telegram:** [@mehdichamanni](https://t.me/mehdichamanni)

---

<a name="فارسی"></a>
## 🇮🇷 راهنمای فارسی (Persian Documentation)

### 🌟 معرفی پروژه و امکانات

**clip-srt-vps** یک ربات تلگرام و سرویس ابری سبک و هوشمند است که با زبان پایتون، فریم‌ورک FastAPI و کتابخانه `python-telegram-bot` توسعه یافته است. این ربات با بهره‌گیری از هوش مصنوعی Groq Whisper، Google Gemini و FFmpeg، صدا را استخراج کرده، زیرنویس دقیق را تولید می‌کند، آن را به فارسی روان ترجمه کرده و زیرنویس سافت‌ساب را روی ویدیو متصل می‌نماید.

- **تبدیل گفتار به متن هوشمند:** استفاده از Groq Whisper (`whisper-large-v3`) برای استخراج متن و زمان‌بندی دقیق زیرنویس.
- **ترجمه فارسی روان:** ترجمه خط به خط با Google Gemini (`gemini-2.5-flash`) با حفظ کامل زمان‌بندی فایل `.srt`.
- **نمایش متناوب زیرنویس:** تولید زیرنویس دو زبانه (زبان اصلی / فارسی متناوب).
- **الصاق سریع زیرنویس سافت‌ساب:** الصاق زیرنویس روی ویدیو با FFmpeg بدون افت کیفیت و رندر طولانی.
- **دانلود از شبکه‌های اجتماعی:** پشتیبانی از دریافت ویدیو از لینک‌های مختلف با `yt-dlp`.
- **معماری وب‌هوک:** پاسخ‌دهی سریع بر پایه FastAPI و ثبت خودکار Webhook.

---

### 📂 فرمت‌ها و لینک‌های پشتیبانی شده

#### فایل‌های قابل ارسال مستقیم
امکان ارسال مستقیم فایل به ربات (تا سقف محدودیت ۲۰ مگابایت تلگرام):
- **فرمت‌های ویدیو:** `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`, `.flv`, `.m4v`
- **فرمت‌های صوتی و ویس:** `.mp3`, `.wav`, `.aac`, `.m4a`, `.flac`, `.ogg`, `.opus`, ویس‌های تلگرام

#### لینک‌های پشتیبانی شده
ارسال لینک ویدیو یا صوت بدون محدودیت حجم فایل:
- **اینستاگرام:** ریلمز (Reels)، پست‌ها، و ویدیوهای IGTV
- **یوتیوب:** ویدیوهای اصلی و یوتیوب شورتس (Shorts)
- **تیک‌تاک:** کلیپ‌های ویدئویی تیک‌تاک
- **توییتر / ایکس:** ویدیوهای پست شده در Twitter/X
- **لینک‌های مستقیم:** تمامی لینک‌های مستقیم قابل دانلود با پسوند `.mp4` و `.mp3`

---

### 🚀 راهنمای استقرار و راه‌اندازی

#### ۱. راه‌اندازی با داکر (Docker)

```bash
# دریافت مخزن
git clone https://github.com/mehdichamani/clip-srt-vps.git
cd clip-srt-vps

# ساخت ایمیج داکر
docker build -t clip-srt-vps .

# اجرای کانتینر
docker run -d \
  --name clip-srt-bot \
  -p 8000:8000 \
  -e TELEGRAM_BOT_TOKEN="توکن_ربات_تلگرام" \
  -e GROQ_API_KEY="کلید_گرواک" \
  -e GEMINI_API_KEY="کلید_جمینای" \
  -e RENDER_EXTERNAL_URL="https://your-domain.com" \
  clip-srt-vps
```

#### ۲. راه‌اندازی روی سرور مجازی (VPS)

```bash
# نصب پیش‌نیازهای سیستم‌عامل
sudo apt-get update && sudo apt-get install -y ffmpeg python3-pip python3-venv git

# دریافت پروژه و فعال‌سازی محیط مجازی
git clone https://github.com/mehdichamani/clip-srt-vps.git
cd clip-srt-vps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# تنظیم متغیرهای محیطی
cp .env.example .env
# ویرایش فایل .env و وارد کردن کلیدها

# اجرای برنامه
uvicorn main:app --host 0.0.0.0 --port 8000
```

#### ۳. استقرار روی Render.com

۱. وارد داشبورد [Render.com](https://dashboard.render.com/) شوید و یک **Web Service** جدید بسازید.
۲. مخزن `https://github.com/mehdichamani/clip-srt-vps` را متصل کنید.
۳. محیط اجرای برنامه را روی **Python 3** قرار دهید.
۴. **دستور ساخت (Build Command):**
   ```bash
   apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt
   ```
۵. **دستور اجرا (Start Command):**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```

---

### 👤 شناسنامه سازنده و مخزن

- **توسعه‌دهنده:** **مهدی چمنی**
- **ایمیل:** `mahdi.chamani20@gmail.com`
- **تلگرام:** [@mehdichamanni](https://t.me/mehdichamanni)
- **مخزن گیت‌هاب:** [https://github.com/mehdichamani/clip-srt-vps](https://github.com/mehdichamani/clip-srt-vps)
- **میزبانی شده در:** [Render.com](https://render.com)
