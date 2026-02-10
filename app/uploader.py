"""
uploader.py – Upload image bytes to BunnyCDN Storage.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class BunnyUploader:
    """Async client for Bunny Storage API (PUT)."""

    def __init__(self, storage_zone: str, access_key: str, cdn_base_url: str = ""):
        self.storage_zone = storage_zone
        self.access_key = access_key
        self.cdn_base_url = cdn_base_url.rstrip("/")
        self.storage_url = f"https://storage.bunnycdn.com/{storage_zone}"
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120))

    async def close(self):
        await self.client.aclose()

    async def upload(self, data: bytes, path: str, filename: str) -> dict:
        """
        Upload *data* to  /{storage_zone}/{path}/{filename}.
        Returns {"status": "ok", "url": "<public_url>"} on success.
        """
        url = f"{self.storage_url}/{path}/{filename}"
        headers = {
            "AccessKey": self.access_key,
            "Content-Type": "application/octet-stream",
        }

        try:
            resp = await self.client.put(url, content=data, headers=headers)
            resp.raise_for_status()

            if self.cdn_base_url:
                public_url = f"{self.cdn_base_url}/{path}/{filename}"
            else:
                public_url = url

            return {"status": "ok", "url": public_url}

        except Exception as exc:
            logger.error("Upload failed for %s/%s: %s", path, filename, exc)
            return {"status": "failed", "error": str(exc)}
