"""Maimai career hot topic scraper via Tophub."""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from bs4 import BeautifulSoup
import httpx

from .base import BaseScraper, FetchResult
from ..models import ContentItem, MaimaiConfig, SourceType

logger = logging.getLogger(__name__)

TOPHUB_MAIMAI_URL = "https://tophub.today/n/2me3DQrowj"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class MaimaiScraper(BaseScraper):
    """Scraper for Maimai career trending topics."""

    def __init__(self, config: MaimaiConfig, http_client: httpx.AsyncClient):
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

        try:
            resp = await self.client.get(TOPHUB_MAIMAI_URL, headers=headers, timeout=12.0)
            resp.raise_for_status()
            html_text = resp.text
        except Exception as exc:
            logger.warning("Failed to fetch Maimai hot list: %s", exc)
            result.fail("network", exc)
            return result

        soup = BeautifulSoup(html_text, "html.parser")
        rows = soup.find_all("tr")
        if not rows:
            logger.info("No Maimai hot topics found on page.")
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
            url = a_tag.get("href") if a_tag else ""

            if not title or not url:
                continue

            item_id = f"maimai-hot-{title}"
            content = f"【脉脉职场热议】: {title}"
            if rank_text:
                content += f"\n【热榜排名】: 第 {rank_text} 位"

            items.append(
                ContentItem(
                    id=item_id,
                    source_type=SourceType.MAIMAI,
                    title=title,
                    url=url,
                    content=content,
                    author="脉脉职场热榜",
                    published_at=now,
                    fetched_at=now,
                    metadata={
                        "rank": rank_text,
                        "source": "maimai_hot",
                    },
                    profile=self.config.profile,
                )
            )

        result.items = items
        logger.info("Fetched %d Maimai hot topics successfully.", len(items))
        return result
