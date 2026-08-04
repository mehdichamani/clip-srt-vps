# Clip SRT Bot v2 🎬📝

A lightweight, cloud-native Python Telegram bot designed to run seamlessly on free hosting platforms (such as **Render Web Services**) without requiring Docker or local heavy machine-learning models.

---

## ✨ Features

- **Fast & Light Cloud Native Stack:** Uses cloud APIs for AI workloads, eliminating heavy local dependencies.
- **Telegram Webhook Architecture:** Built with **FastAPI**, **Uvicorn**, and `python-telegram-bot` (v20+ async) with automatic webhook registration on startup.
- **Fast Speech-to-Text (STT):** Uses official `groq` SDK calling `whisper-large-v3` with `verbose_json` for precise timestamps.
- **Natural Persian Translation:** Uses official `google-genai` SDK calling `gemini-2.5-flash` to translate subtitles into fluent, natural spoken Persian while strictly preserving `.srt` timestamps.
- **Fast Soft-Subtitle Embedding:** Uses FFmpeg to extract 16kHz mono audio and remux soft subtitles into video containers (`mov_text`) without slow re-encoding.
- **Web & Attachment Downloads:** Supports direct video/audio uploads as well as web video URLs via `yt-dlp`.

---

## 🛠️ Architecture & Service Assignments

| Component | Technology / Library | Purpose |
| :--- | :--- | :--- |
| **Web Server & Webhook** | FastAPI + Uvicorn + `python-telegram-bot` v20+ | Handles Telegram update webhook at `POST /webhook` |
| **Downloader** | `yt-dlp` + PTB File Download API | Handles Telegram attachments and web links |
| **Media Processing** | FFmpeg (subprocess) | Audio extraction (16kHz mono) & fast soft subtitle remuxing |
| **Transcription (STT)** | Groq SDK (`groq.Groq`) - `whisper-large-v3` | Fast timestamped transcription |
| **Translation** | Google GenAI SDK (`google.genai.Client`) - `gemini-2.5-flash` | Persian translation in valid `.srt` format |

---

## 🚀 Quick Deployment Guide (Render Web Service)

### Step 1: Fork or Upload to GitHub

Push this repository (or the `clip-srt-bot-v2` directory) to GitHub.

### Step 2: Create a New Web Service on Render

1. Go to [Render Dashboard](https://dashboard.render.com/) and click **New +** -> **Web Service**.
2. Connect your GitHub repository.
3. Choose **Python 3** environment.
4. Set **Build Command**:
   ```bash
   apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt
   ```
5. Set **Start Command**:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```

### Step 3: Configure Environment Variables

Add the following Environment Variables in Render:

| Key | Description | Example |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Token from Telegram [@BotFather](https://t.me/BotFather) | `123456789:ABCdef...` |
| `GROQ_API_KEY` | Groq API Key from [Groq Console](https://console.groq.com/) | `gsk_...` |
| `GEMINI_API_KEY` | Google Gemini API key from [Google AI Studio](https://aistudio.google.com/) | `AIzaSy...` |
| `RENDER_EXTERNAL_URL` | Your Render public service URL (No trailing slash) | `https://clip-srt-bot-v2.onrender.com` |
| `WEBHOOK_SECRET` | *(Optional)* Secret token for webhook authorization | `random_secret_str` |

> **Note:** Upon deployment, the app will read `RENDER_EXTERNAL_URL` and automatically set the Telegram webhook on startup!

---

## 💻 Local Development Setup

### 1. Clone & Install Dependencies

```bash
cd clip-srt-bot-v2
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

### 3. Run Web Server

```bash
uvicorn main:app --reload --port 8000
```

To test webhooks locally, use **ngrok**:

```bash
ngrok http 8000
```
Then set `RENDER_EXTERNAL_URL=https://<your-ngrok-subdomain>.ngrok-free.app` in `.env` and restart uvicorn.

---

## 🧪 Verification & Health Check

Test server health by navigating to:
```http
GET http://localhost:8000/health
```
Output:
```json
{
  "status": "healthy",
  "service": "clip-srt-bot-v2",
  "webhook_configured": true
}
```

---

## 📜 License

MIT License
