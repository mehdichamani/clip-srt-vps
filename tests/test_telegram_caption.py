import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.telegram_bot import get_message_footer, get_plain_footer
from app.services.downloader import DownloaderService
from app.services.translator import TranslationService


class TestTelegramCaptionTemplate(unittest.TestCase):

    def setUp(self):
        self.context = MagicMock()
        self.context.bot = AsyncMock()
        self.context.bot.username = "instazirnevisbot"

    def test_caption_template_default_values(self):
        footer = asyncio.run(get_message_footer(self.context, channel="Unknown Channel", translate_method="هوش مصنوعی"))
        expected = (
            "از پیج نامشخص\n"
            "ترجمه شده با هوش مصنوعی توسط ربات @instazirnevisbot"
        )
        self.assertEqual(footer, expected)

    def test_caption_template_with_channel(self):
        footer = asyncio.run(get_message_footer(self.context, channel="top_ai_news", translate_method="مترجم گوگل"))
        expected = (
            "از پیج @top_ai_news\n"
            "ترجمه شده با مترجم گوگل توسط ربات @instazirnevisbot"
        )
        self.assertEqual(footer, expected)

    def test_caption_template_with_handle_channel(self):
        footer = asyncio.run(get_message_footer(self.context, channel="@top_ai_news", translate_method="هوش مصنوعی"))
        expected = (
            "از پیج @top_ai_news\n"
            "ترجمه شده با هوش مصنوعی توسط ربات @instazirnevisbot"
        )
        self.assertEqual(footer, expected)

    def test_plain_footer(self):
        footer = get_plain_footer(channel="@tech_hub", translate_method="مترجم گوگل", bot_username="instazirnevisbot")
        expected = (
            "از پیج @tech_hub\n"
            "ترجمه شده با مترجم گوگل توسط ربات @instazirnevisbot"
        )
        self.assertEqual(footer, expected)

    def test_sanitize_filename_with_subject(self):
        filename_mkv = DownloaderService.sanitize_filename(channel="top_ai_news", title="خبر های مهم این هفته هوش مصنوعی", ext=".mkv")
        self.assertEqual(filename_mkv, "top_ai_news - خبر های مهم این هفته هوش مصنوعی.mkv")

        filename_txt = DownloaderService.sanitize_filename(channel=None, title="خبر های مهم این هفته هوش مصنوعی", ext=".txt")
        self.assertEqual(filename_txt, "خبر های مهم این هفته هوش مصنوعی.txt")

    @patch("app.services.translator.Groq")
    def test_generate_persian_subject_mock(self, mock_groq):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="خبر های مهم هوش مصنوعی"))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq.return_value = mock_client

        srv = TranslationService(api_key="gsk_dummy")
        sample_srt = "1\n00:00:01,000 --> 00:00:03,000\nWelcome to AI news."
        subject = asyncio.run(srv.generate_persian_subject(sample_srt))
        self.assertEqual(subject, "خبر های مهم هوش مصنوعی")


if __name__ == "__main__":
    unittest.main()

