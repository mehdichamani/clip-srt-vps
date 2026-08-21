import logging
from typing import List, Optional, Dict, Any
import httpx
from app.config import settings

logger = logging.getLogger("telegram_rich_service")


class TelegramRichService:
    """Service to send modern Telegram Rich Messages (Bot API 10.1+) with collapsible details and formatted blocks."""

    @classmethod
    async def send_rich_message(cls, chat_id: int | str, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calls the sendRichMessage API method directly using httpx.
        """
        token = settings.telegram_bot_token
        if not token:
            raise RuntimeError("Telegram bot token is not configured in settings.")

        url = f"https://api.telegram.org/bot{token}/sendRichMessage"
        payload = {
            "chat_id": chat_id,
            "rich_message": {
                "blocks": blocks
            }
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if data.get("ok"):
                return data["result"]
            else:
                logger.error(f"sendRichMessage failed: {data}")
                raise RuntimeError(f"Telegram sendRichMessage error: {data.get('description', data)}")

    @classmethod
    def build_bilingual_blocks(
        cls,
        bilingual_srt: str,
        subject: str,
        footer_text: str,
        max_lines_per_section: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Parses alternating bilingual subtitles and builds structured collapsible details blocks.
        """
        blocks: List[Dict[str, Any]] = []

        # 1. Header block
        header_title = subject.strip() if subject and subject.strip() else "خلاصه و متن ترجمه"
        blocks.append({
            "type": "paragraph",
            "text": {
                "type": "bold",
                "text": f"📌 {header_title}"
            }
        })

        # 2. Parse SRT entries into bilingual pairs
        # Format of alternating text or SRT entries
        entries = cls._parse_srt_entries(bilingual_srt)

        if not entries:
            # Fallback if parsing fails or text is simple
            blocks.append({
                "type": "paragraph",
                "text": bilingual_srt[:30000]
            })
        else:
            # Split entries into chunked sections (e.g. 20 subtitle pairs per section)
            chunks = [entries[i:i + max_lines_per_section] for i in range(0, len(entries), max_lines_per_section)]
            num_chunks = len(chunks)

            for idx, chunk in enumerate(chunks, 1):
                inner_blocks: List[Dict[str, Any]] = []
                for entry in chunk:
                    en_text = entry.get("en", "").strip()
                    fa_text = entry.get("fa", "").strip()
                    time_str = entry.get("time", "")

                    if en_text:
                        inner_blocks.append({
                            "type": "paragraph",
                            "text": f"{time_str} {en_text}".strip()
                        })
                    if fa_text:
                        inner_blocks.append({
                            "type": "paragraph",
                            "text": {
                                "type": "bold",
                                "text": f"🇮🇷 {fa_text}"
                            }
                        })

                section_title = f"📂 بخش {idx} از {num_chunks}"
                if chunk and chunk[0].get("time"):
                    start_t = chunk[0]["time"].replace("[", "").replace("]", "").strip()
                    end_t = chunk[-1]["time"].replace("[", "").replace("]", "").strip()
                    section_title += f" ({start_t} ⬅️ {end_t})"

                blocks.append({
                    "type": "details",
                    "summary": section_title,
                    "blocks": inner_blocks,
                    "is_open": (idx == 1)  # Open the first section by default
                })

        # 3. Footer block
        if footer_text:
            blocks.append({
                "type": "paragraph",
                "text": {
                    "type": "code",
                    "text": footer_text
                }
            })

        return blocks

    @classmethod
    def _parse_srt_entries(cls, srt_content: str) -> List[Dict[str, str]]:
        """Parses SRT blocks to extract timing, English line, and Persian translation line."""
        entries: List[Dict[str, str]] = []
        raw_blocks = srt_content.strip().split("\n\n")

        for block in raw_blocks:
            lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
            if len(lines) < 2:
                continue

            # Check if line 0 is numeric index
            time_idx = 1 if lines[0].isdigit() and len(lines) > 2 else 0
            time_line = lines[time_idx] if "-->" in lines[time_idx] else ""
            content_lines = lines[time_idx + 1:] if time_line else lines

            time_label = ""
            if time_line:
                # e.g., '00:00:01,000 --> 00:00:04,500' -> '[00:01]'
                start_part = time_line.split("-->")[0].strip()
                if ":" in start_part:
                    parts = start_part.split(":")
                    if len(parts) >= 2:
                        m = parts[-2]
                        s = parts[-1].split(",")[0].split(".")[0]
                        time_label = f"[{m}:{s}]"

            if len(content_lines) >= 2:
                en = content_lines[0]
                fa = content_lines[1]
                entries.append({"time": time_label, "en": en, "fa": fa})
            elif len(content_lines) == 1:
                entries.append({"time": time_label, "en": content_lines[0], "fa": ""})

        return entries
