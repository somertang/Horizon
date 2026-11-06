"""Baidu hot search scraper implementation via Tophub."""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from bs4 import BeautifulSoup
import httpx

from .base import BaseScraper, FetchResult
from ..models import BaiduConfig, ContentItem, SourceType

logger = logging.getLogger(__name__)

TOPHUB_BAIDU_URL = "https://tophub.today/n/Jb0vmloB1G"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class BaiduScraper(BaseScraper):
    """Scraper for Baidu trending hot search items via Tophub."""

    def __init__(self, config: BaiduConfig, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.config = config

    async def fetch(self, since: Optional[datetime] = None) -> FetchResult:
        result = FetchResult()
        if not self.config.enabled:
            return result

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        url = getattr(self.config, "api_url", None) or TOPHUB_BAIDU_URL

        try:
            resp = await self.client.get(url, headers=headers, timeout=12.0)
            resp.raise_for_status()
            html_text = resp.text
        except Exception as exc:
            logger.warning("Failed to fetch Baidu hot list from Tophub: %s", exc)
            result.fail("network", exc)
            return result

        soup = BeautifulSoup(html_text, "html.parser")
        rows = soup.find_all("tr")
        if not rows:
            logger.info("No Baidu hot items found on page.")
            return result

        now = datetime.now(timezone.utc)
        items: List[ContentItem] = []
        limit = self.config.fetch_limit or 15

        for row in rows:
            if len(items) >= limit:
                break
            tds = row.find_all("td")
            if len(tds) < 2:
                continue

            rank_text = tds[0].get_text(strip=True).rstrip(".")
            title_cell = tds[1]
            title = title_cell.get_text(strip=True)
            a_tag = title_cell.find("a")
            link = a_tag.get("href") if a_tag else ""

            if not title or not link:
                continue

            item_id = f"baidu-hot-{title}"
            content = f"【百度实时热搜】: {title}"
            if rank_text:
                content += f"\n【榜单排名】: 第 {rank_text} 位"

            items.append(
                ContentItem(
                    id=item_id,
                    source_type=SourceType.BAIDU,
                    title=title,
                    url=link,
                    content=content,
                    author="百度热搜榜",
                    published_at=now,
                    fetched_at=now,
                    metadata={
                        "rank": rank_text,
                        "source": "baidu_hot_tophub",
                    },
                    profile=self.config.profile,
                )
            )

        result.items = items
        logger.info("Fetched %d Baidu hot items from Tophub successfully.", len(items))
        return result
