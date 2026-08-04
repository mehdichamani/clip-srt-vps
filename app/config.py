import logging
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("clip_srt_bot")

class Settings(BaseSettings):
    telegram_bot_token: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    render_external_url: str = ""
    webhook_secret: Optional[str] = None
    port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def validate_keys(self) -> bool:
        """Validates that all required API keys are configured."""
        missing = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.groq_api_key:
            missing.append("GROQ_API_KEY")
        if not self.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        
        if missing:
            logger.error(f"Missing required environment variables: {', '.join(missing)}")
            return False
        return True

settings = Settings()
