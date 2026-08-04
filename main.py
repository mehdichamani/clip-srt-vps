import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, status
from telegram import Update

from app.config import settings
from app.telegram_bot import create_telegram_application

# Configure Structured Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("clip_srt_bot")

ptb_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to handle Telegram Bot initialization & Webhook registration."""
    global ptb_app
    logger.info("Starting up Clip SRT Bot v2...")
    
    settings.validate_keys()
    
    # Initialize Telegram Bot Application
    ptb_app = create_telegram_application()
    await ptb_app.initialize()
    await ptb_app.start()

    # Automatically set Telegram Webhook URL if RENDER_EXTERNAL_URL is provided
    if settings.render_external_url:
        base_url = settings.render_external_url.rstrip("/")
        webhook_url = f"{base_url}/webhook"
        logger.info(f"Setting Telegram webhook URL to: {webhook_url}")
        
        kwargs = {"url": webhook_url}
        if settings.webhook_secret:
            kwargs["secret_token"] = settings.webhook_secret
            
        await ptb_app.bot.set_webhook(**kwargs)
    else:
        logger.warning(
            "RENDER_EXTERNAL_URL is not configured. Telegram webhook URL was not auto-set. "
            "Please set RENDER_EXTERNAL_URL in your environment or set webhook manually."
        )

    yield

    # Clean shutdown
    logger.info("Shutting down Telegram Bot Application...")
    if ptb_app:
        await ptb_app.stop()
        await ptb_app.shutdown()
    logger.info("Shutdown complete.")

app = FastAPI(
    title="Clip SRT Bot v2",
    description="Cloud-native Telegram Bot for video subtitle generation and Persian translation",
    version="2.0.0",
    lifespan=lifespan
)

@app.get("/")
@app.get("/health")
async def health_check():
    """Health check endpoint for Render service monitoring."""
    return {
        "status": "healthy",
        "service": "clip-srt-bot-v2",
        "webhook_configured": bool(settings.render_external_url)
    }

@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None)
):
    """Explicit Telegram Webhook endpoint receiving HTTP POST updates."""
    if not ptb_app:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram Application is not initialized."
        )

    # Optional Webhook secret validation
    if settings.webhook_secret and x_telegram_bot_api_secret_token != settings.webhook_secret:
        logger.warning("Received webhook request with invalid secret token.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid secret token"
        )

    try:
        data = await request.json()
        update = Update.de_json(data, ptb_app.bot)
        # Process update asynchronously in background task to avoid Telegram webhook timeout
        asyncio.create_task(ptb_app.process_update(update))
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing Telegram webhook update: {e}", exc_info=True)
        return {"status": "error", "detail": str(e)}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
