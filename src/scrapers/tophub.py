"""Generic Tophub (今日热榜) node scraper.

Many Chinese media sites no longer publish stable RSS feeds, while Tophub keeps
public node pages with ranked headlines and direct links back to the publisher.
This scraper handles any Tophub node listed in configuration, so a single source
type covers several sites without adding one scraper per site.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper, FetchResult
from ..models import ContentItem, SourceType, TophubConfig, TophubNodeConfig

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class TophubScraper(BaseScraper):
    """Scraper for configured Tophub nodes."""

    def __init__(self, config: TophubConfig, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.tophub_config = config

    async def fetch(self, since: Optional[datetime] = None) -> FetchResult:
        result = FetchResult()
        if not self.tophub_config.enabled:
            return result

        for node in self.tophub_config.nodes:
            if node.enabled:
                await result.collect(node.name, self._fetch_node(node))

        return result

    async def _fetch_node(self, node: TophubNodeConfig) -> List[ContentItem]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        resp = await self.client.get(str(node.url), headers=headers, timeout=20.0)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        now = datetime.now(timezone.utc)
        limit = node.fetch_limit or 20
        items: List[ContentItem] = []

        for row in soup.find_all("tr"):
            if len(items) >= limit:
                break

            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            rank = cells[0].get_text(strip=True).rstrip(".")

            # Node layouts differ: some put the headline in the second cell,
            # others add a cover image column first. Pick the longest linked
            # text cell so both shapes work.
            best: Optional[tuple[str, str]] = None
            for cell in cells[1:]:
                link_tag = cell.find("a")
                href = link_tag.get("href") if link_tag else None
                if not href:
                    continue
                text = cell.get_text(" ", strip=True)
                if not text:
                    continue
                if best is None or len(text) > len(best[0]):
                    best = (text, str(href))

            if best is None:
                continue

            title, url = best
            content = f"【{node.name}】: {title}"
            if rank:
                content += f"\n【榜单排名】: 第 {rank} 位"

            items.append(
                ContentItem(
                    id=f"tophub-{node.name}-{title}",
                    source_type=SourceType.TOPHUB,
                    title=title,
                    url=url,
                    content=content,
                    author=node.name,
                    published_at=now,
                    fetched_at=now,
                    metadata={
                        "rank": rank,
                        "source": "tophub",
                        "node": node.name,
                    },
                    profile=node.profile,
                )
            )

        logger.info("Fetched %d items from Tophub node %s.", len(items), node.name)
        return items
