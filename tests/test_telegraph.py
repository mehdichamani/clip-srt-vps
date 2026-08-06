import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.telegraph import TelegraphService


class TestTelegraphService(unittest.TestCase):

    @patch("app.services.telegraph.httpx.AsyncClient")
    def test_create_page_success(self, mock_async_client_cls):
        mock_client = AsyncMock()
        mock_async_client_cls.return_value.__aenter__.return_value = mock_client

        # Mock createAccount response
        mock_resp_acc = MagicMock()
        mock_resp_acc.json.return_value = {
            "ok": True,
            "result": {"access_token": "dummy_token"}
        }

        # Mock createPage response
        mock_resp_page = MagicMock()
        mock_resp_page.json.return_value = {
            "ok": True,
            "result": {"url": "https://telegra.ph/test-page-08-06"}
        }

        mock_client.post.side_effect = [mock_resp_acc, mock_resp_page]

        title = "تست عنوان مقاله"
        content = "خط اول متن\nخط دوم متن"
        url = asyncio.run(TelegraphService.create_page(title, content, author_name="@testbot", footer_text="پاورقی تست"))

        self.assertEqual(url, "https://telegra.ph/test-page-08-06")
        self.assertEqual(mock_client.post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
