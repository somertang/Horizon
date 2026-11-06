"""YouTube channel scraper implementation."""

import json
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from .base import BaseScraper, FetchResult
from ..models import ContentItem, SourceType, YouTubeConfig

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class YouTubeScraper(BaseScraper):
    """Scraper for YouTube channel videos."""

    def __init__(self, config: YouTubeConfig, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.config = config

    async def fetch(self, since: Optional[datetime] = None) -> FetchResult:
        result = FetchResult()
        if not self.config.enabled:
            return result

        channels = self.config.channels
        if not channels:
            logger.debug("No YouTube channels configured.")
            return result

        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        now = datetime.now(timezone.utc)
        limit = self.config.fetch_limit or 5

        for ch in channels:
            handle = ch.handle.strip()
            if not handle.startswith("@"):
                handle = f"@{handle}"
            ch_name = ch.name or handle
            url = f"https://www.youtube.com/{handle}/videos"

            try:
                resp = await self.client.get(url, headers=headers, timeout=12.0)
                resp.raise_for_status()
                html_text = resp.text
            except Exception as exc:
                logger.warning("Failed to fetch YouTube channel %s: %s", handle, exc)
                result.fail(f"youtube:{handle}", exc)
                continue

            match = re.search(r"ytInitialData\s*=\s*({.+?});</script>", html_text)
            if not match:
                logger.warning("Could not find ytInitialData for YouTube channel %s", handle)
                continue

            try:
                data = json.loads(match.group(1))
            except Exception as exc:
                logger.warning("Failed to parse ytInitialData for %s: %s", handle, exc)
                continue

            found_videos = []
            self._extract_lockup_videos(data, found_videos)

            for title, vid, time_info in found_videos[:limit]:
                item_id = f"youtube-{vid}"
                video_url = f"https://www.youtube.com/watch?v={vid}"
                content = f"【YouTube 视频】: {title}\n【创作者】: {ch_name}"
                if time_info:
                    content += f"\n【发布时效】: {time_info}"

                result.items.append(
                    ContentItem(
                        id=item_id,
                        source_type=SourceType.YOUTUBE,
                        title=title,
                        url=video_url,
                        content=content,
                        author=ch_name,
                        published_at=now,
                        fetched_at=now,
                        metadata={
                            "video_id": vid,
                            "time_info": time_info,
                            "channel": handle,
                            "source": "youtube",
                        },
                        profile=ch.profile or self.config.profile,
                    )
                )
            result.successful += 1

        logger.info("Fetched %d YouTube videos across %d channels.", len(result.items), len(channels))
        return result

    def _extract_lockup_videos(self, obj, out_list):
        if isinstance(obj, dict):
            if "lockupViewModel" in obj:
                vm = obj["lockupViewModel"]
                meta = vm.get("metadata", {}).get("lockupMetadataViewModel", {})
                title = meta.get("title", {}).get("content")
                cmd = (
                    vm.get("rendererContext", {})
                    .get("commandContext", {})
                    .get("onTap", {})
                    .get("innertubeCommand", {})
                )
                vid = cmd.get("watchEndpoint", {}).get("videoId") or vm.get("contentId")

                time_snippet = ""
                badges = meta.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
                for row in badges:
                    for part in row.get("metadataParts", []):
                        t = part.get("text", {}).get("content")
                        if t and any(k in t for k in ["ago", "前", "views", "次观看"]):
                            time_snippet += f" {t}"

                if title and vid:
                    out_list.append((title, vid, time_snippet.strip()))
            for v in obj.values():
                self._extract_lockup_videos(v, out_list)
        elif isinstance(obj, list):
            for it in obj:
                self._extract_lockup_videos(it, out_list)
