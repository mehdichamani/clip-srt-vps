import unittest
from unittest.mock import patch, MagicMock
import asyncio

from app.config import Settings
from app.services.translator import TranslationService


class TestGroqTranslator(unittest.TestCase):

    @patch("app.services.translator.Groq")
    @patch("app.services.translator.settings")
    def test_translate_to_persian_groq_success(self, mock_settings, mock_groq_cls):
        mock_settings.groq_api_key = "gsk_test_key_12345"
        mock_settings.get_gemini_api_keys.return_value = []

        mock_groq_instance = MagicMock()
        mock_groq_cls.return_value = mock_groq_instance

        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content="1\n00:00:01,000 --> 00:00:04,000\nسلام دنیا!"))
        ]
        mock_groq_instance.chat.completions.create.return_value = mock_completion

        translator = TranslationService()
        sample_srt = "1\n00:00:01,000 --> 00:00:04,000\nHello World!"

        result = asyncio.run(translator.translate_to_persian(sample_srt))

        self.assertIn("سلام دنیا!", result)
        mock_groq_cls.assert_called_once_with(api_key="gsk_test_key_12345")
        mock_groq_instance.chat.completions.create.assert_called_once()

    @patch("app.services.translator.GoogleTranslator")
    def test_translate_to_persian_google_success(self, mock_translator_cls):
        mock_translator_instance = MagicMock()
        mock_translator_cls.return_value = mock_translator_instance
        mock_translator_instance.translate_batch.return_value = ["سلام دنیا!"]

        translator = TranslationService()
        sample_srt = "1\n00:00:01,000 --> 00:00:04,000\nHello World!"

        result = asyncio.run(translator.translate_to_persian(sample_srt, engine="google"))

        self.assertIn("سلام دنیا!", result)
        self.assertIn("00:00:01,000 --> 00:00:04,000", result)
        mock_translator_cls.assert_called_once_with(source="auto", target="fa")
        mock_translator_instance.translate_batch.assert_called_once_with(["Hello World!"])


if __name__ == "__main__":
    unittest.main()

