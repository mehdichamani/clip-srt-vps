import unittest
from unittest.mock import patch
import os

from app.config import Settings
from app.services.translator import TranslationService, mask_key


class TestGeminiRoundRobin(unittest.TestCase):

    def test_mask_key(self):
        self.assertEqual(mask_key(""), "None")
        self.assertEqual(mask_key("12345"), "12...45")
        self.assertEqual(mask_key("AIzaSy1234567890abcdef"), "AIzaSy...cdef")

    def test_get_gemini_api_keys_single(self):
        s = Settings(gemini_api_key="key1", gemini_api_keys="")
        self.assertEqual(s.get_gemini_api_keys(), ["key1"])

    def test_get_gemini_api_keys_comma_separated(self):
        s = Settings(gemini_api_key="key1, key2 , key3 ", gemini_api_keys="")
        self.assertEqual(s.get_gemini_api_keys(), ["key1", "key2", "key3"])

    def test_get_gemini_api_keys_both(self):
        s = Settings(gemini_api_key="key1,key2", gemini_api_keys="key3, key4, key1")
        # key1 is deduplicated
        self.assertEqual(s.get_gemini_api_keys(), ["key3", "key4", "key1", "key2"])

    def test_round_robin_rotation(self):
        test_settings = Settings(gemini_api_key="", gemini_api_keys="keyA,keyB,keyC")
        with patch("app.services.translator.settings", test_settings):
            # Reset index for deterministic test
            TranslationService._key_index = 0
            
            self.assertEqual(TranslationService.get_next_api_key(), "keyA")
            self.assertEqual(TranslationService.get_next_api_key(), "keyB")
            self.assertEqual(TranslationService.get_next_api_key(), "keyC")
            self.assertEqual(TranslationService.get_next_api_key(), "keyA")
            self.assertEqual(TranslationService.get_next_api_key(), "keyB")


if __name__ == "__main__":
    unittest.main()
