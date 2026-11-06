"""Weibo hot search scraper implementation."""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import quote

import httpx

from .base import BaseScraper, FetchResult
from ..models import ContentItem, SourceType, WeiboConfig

logger = logging.getLogger(__name__)

WEIBO_HOT_URL = "https://weibo.com/ajax/side/hotSearch"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class WeiboScraper(BaseScraper):
    """Scraper for Weibo trending/hot search topics."""

    def __init__(self, config: WeiboConfig, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.config = config

    async def fetch(self, since: Optional[datetime] = None) -> FetchResult:
        result = FetchResult()
        if not self.config.enabled:
            return result

        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://weibo.com/",
            "Accept": "application/json, text/plain, */*",
        }

        try:
            resp = await self.client.get(WEIBO_HOT_URL, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch Weibo hot list: %s", exc)
            result.fail("network", exc)
            return result

        realtime_items = data.get("data", {}).get("realtime", [])
        if not realtime_items:
            logger.info("No Weibo hot items returned from API.")
            return result

        now = datetime.now(timezone.utc)
        items: List[ContentItem] = []
        limit = self.config.fetch_limit or 15

        for item in realtime_items[:limit]:
            word = item.get("word") or item.get("note")
            if not word:
                continue

            raw_hot = item.get("num") or item.get("raw_hot") or 0
            tag = item.get("label_name") or item.get("icon_desc") or item.get("category", "")
            search_url = f"https://s.weibo.com/weibo?q={quote(word)}"
            item_id = f"weibo-hot-{word}"

            content = f"【微博实时热搜】: {word}\n【热度数值】: {raw_hot:,} 热度"
            if tag:
                content += f"\n【分类标签】: {tag}"

            items.append(
                ContentItem(
                    id=item_id,
                    source_type=SourceType.WEIBO,
                    title=word,
                    url=search_url,
                    content=content,
                    author="微博热搜榜",
                    published_at=now,
                    fetched_at=now,
                    metadata={
                        "raw_hot": raw_hot,
                        "category_tag": tag,
                        "source": "weibo_hot",
                    },
                    profile=self.config.profile,
                )
            )

        result.items = items
        logger.info("Fetched %d Weibo hot items successfully.", len(items))
        return result
