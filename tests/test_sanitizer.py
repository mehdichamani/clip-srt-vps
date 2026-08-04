import unittest
import os
import sys

# Ensure app package can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.downloader import DownloaderService

class TestDownloaderSanitization(unittest.TestCase):

    def test_sanitize_filename_basic(self):
        result = DownloaderService.sanitize_filename("BBC News", "Breaking News Today")
        self.assertEqual(result, "BBC News - Breaking News Today.mkv")

    def test_sanitize_filename_illegal_chars(self):
        result = DownloaderService.sanitize_filename("Channel: 100?", 'Title with / \\ * ? " < > | illegal chars')
        self.assertEqual(result, "Channel 100 - Title with illegal chars.mkv")

    def test_sanitize_filename_fallbacks(self):
        result = DownloaderService.sanitize_filename(None, "")
        self.assertEqual(result, "Unknown Channel - Video.mkv")

        result2 = DownloaderService.sanitize_filename("   ", None)
        self.assertEqual(result2, "Unknown Channel - Video.mkv")

    def test_sanitize_filename_length_limit(self):
        channel = "A" * 60
        title = "B" * 60
        result = DownloaderService.sanitize_filename(channel, title)
        base_name = result[:-4]  # Remove .mkv
        self.assertTrue(len(base_name) <= 100)
        self.assertTrue(result.endswith(".mkv"))

if __name__ == "__main__":
    unittest.main()
