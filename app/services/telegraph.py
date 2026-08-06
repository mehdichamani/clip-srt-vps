import json
import logging
from typing import Optional, List
import httpx

logger = logging.getLogger("telegraph_service")

_TELEGRAPH_ACCESS_TOKEN: Optional[str] = None


class TelegraphService:
    """Service to interact with Telegraph API (telegra.ph) for Instant View articles."""

    @classmethod
    async def get_access_token(cls) -> str:
        global _TELEGRAPH_ACCESS_TOKEN
        if _TELEGRAPH_ACCESS_TOKEN:
            return _TELEGRAPH_ACCESS_TOKEN

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post("https://api.telegra.ph/createAccount", data={
                "short_name": "InstaZirnevis",
                "author_name": "@instazirnevisbot"
            })
            data = resp.json()
            if data.get("ok"):
                _TELEGRAPH_ACCESS_TOKEN = data["result"]["access_token"]
                return _TELEGRAPH_ACCESS_TOKEN
            raise RuntimeError(f"Telegraph createAccount failed: {data}")

    @classmethod
    async def create_page(
        cls,
        title: str,
        text_content: str,
        author_name: str = "@instazirnevisbot",
        footer_text: Optional[str] = None
    ) -> str:
        """
        Creates a Telegraph page with Instant View support and returns the page URL.
        """
        token = await cls.get_access_token()

        lines = [line.strip() for line in text_content.split('\n') if line.strip()]

        nodes: List[dict] = []
        for line in lines:
            nodes.append({
                "tag": "p",
                "children": [line]
            })

        if footer_text:
            nodes.append({"tag": "hr"})
            nodes.append({"tag": "p", "children": [footer_text]})

        clean_title = (title.strip() if title and title.strip() else "خلاصه و زیرنویس")[:256]

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post("https://api.telegra.ph/createPage", data={
                "access_token": token,
                "title": clean_title,
                "author_name": author_name,
                "content": json.dumps(nodes),
                "return_content": False
            })
            data = resp.json()
            if data.get("ok"):
                page_url = data["result"]["url"]
                logger.info(f"Telegraph page created successfully: {page_url}")
                return page_url
            else:
                raise RuntimeError(f"Telegraph createPage API error: {data}")
