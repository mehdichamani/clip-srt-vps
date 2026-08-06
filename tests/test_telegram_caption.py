import unittest
import asyncio
from unittest.mock import MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.telegram_bot import get_message_footer


class TestTelegramCaptionTemplate(unittest.TestCase):

    def setUp(self):
        self.context = MagicMock()
        self.context.bot = MagicMock()
        self.context.bot.username = "instazirnevisbot"

    def test_caption_template_default_values(self):
        footer = asyncio.run(get_message_footer(self.context, title="Video title", channel="Unknown Channel"))
        expected = (
            "📺 کانال:\n\n"
            "✍️ ترجمه و زیرنویس شده توسط @instazirnevisbot"
        )
        self.assertEqual(footer, expected)

    def test_caption_template_with_channel(self):
        footer = asyncio.run(get_message_footer(self.context, channel="TechChannel"))
        expected = (
            "📺 کانال: TechChannel\n\n"
            "✍️ ترجمه و زیرنویس شده توسط @instazirnevisbot"
        )
        self.assertEqual(footer, expected)

    def test_caption_template_removes_title_and_success_banner(self):
        footer = asyncio.run(get_message_footer(self.context, title="Video by Username", channel="MyChannel"))
        self.assertNotIn("🎬 عنوان:", footer)
        self.assertNotIn("Video by Username", footer)
        self.assertNotIn("✅ ویدیو با زیرنویس سافتساب آماده شد!", footer)
        self.assertNotIn("🏷️ موضوع:", footer)
        self.assertIn("📺 کانال: MyChannel", footer)
        self.assertIn("✍️ ترجمه و زیرنویس شده توسط @instazirnevisbot", footer)


if __name__ == "__main__":
    unittest.main()
