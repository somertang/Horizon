"""Zhihu trending hot-list scraper."""

from datetime import datetime, timezone
import hashlib
import logging
from typing import List, Optional

import httpx

from ..models import ContentItem, SourceType, ZhihuConfig
from .base import BaseScraper, FetchResult

logger = logging.getLogger(__name__)


class ZhihuScraper(BaseScraper):
    """Scraper for Zhihu official topstory hot-list endpoint."""

    API_URL = "https://api.zhihu.com/topstory/hot-list"

    def __init__(self, config: ZhihuConfig, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.cfg: ZhihuConfig = config

    def _generate_id(self, item_id: str) -> str:
        h = hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:12]
        return f"zhihu:hot:{item_id}:{h}"

    async def fetch(self, since: datetime) -> FetchResult:
        result = FetchResult()
        if not self.cfg.enabled:
            return result

        try:
            items = await self._fetch_hot_list()
            result.items.extend(items)
            result.successful = 1
        except Exception as exc:
            result.fail("Zhihu Hot", exc)
            logger.warning("Failed to fetch Zhihu hot list: %s", exc)

        return result

    async def _fetch_hot_list(self) -> List[ContentItem]:
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
        }
        response = await self.client.get(self.API_URL, headers=headers, timeout=15.0)
        response.raise_for_status()

        data = response.json()
        raw_items = data.get("data", [])
        limit = self.cfg.fetch_limit or 20

        items: List[ContentItem] = []
        now = datetime.now(timezone.utc)

        for entry in raw_items[:limit]:
            target = entry.get("target", {})
            title = target.get("title", "").strip()
            item_id = str(target.get("id", ""))
            if not title or not item_id:
                continue

            url = f"https://www.zhihu.com/question/{item_id}"
            detail_text = entry.get("detail_text", "")
            excerpt = target.get("excerpt", "").strip()

            content_parts = []
            if detail_text:
                content_parts.append(f"【热度指标】: {detail_text}")
            if excerpt:
                content_parts.append(f"【背景与描述】: {excerpt}")
            content = "\n\n".join(content_parts) if content_parts else title

            items.append(
                ContentItem(
                    id=self._generate_id(item_id),
                    source_type=SourceType.ZHIHU,
                    title=title,
                    url=url,
                    content=content,
                    author="知乎热榜",
                    published_at=now,
                    profile=self.cfg.profile,
                    metadata={
                        "score": detail_text,
                        "question_id": item_id,
                        "category": self.cfg.category or "career-insight",
                        "discussion_url": url,
                    },
                )
            )

        return items
