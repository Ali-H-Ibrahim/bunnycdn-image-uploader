"""
downloader.py – Download images with retry, proxy fallback, and extension detection.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────


def guess_extension(content_type: str, data: bytes) -> str:
    """Detect image format from Content-Type header or magic bytes."""
    ct = content_type.lower()
    for mime, ext in (
        ("image/jpeg", "jpg"),
        ("image/png", "png"),
        ("image/webp", "webp"),
        ("image/gif", "gif"),
        ("image/svg+xml", "svg"),
        ("image/avif", "avif"),
    ):
        if mime in ct:
            return ext

    # Fallback: magic bytes
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"

    return "jpg"  # safe default


def generate_filename(data: bytes, content_type: str) -> str:
    file_hash = hashlib.sha1(data).hexdigest()[:12]
    ext = guess_extension(content_type, data)
    return f"{file_hash}.{ext}"


def _auto_referer(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.hostname}/"


def _should_use_proxy(url: str, mode: str, domains: list[str]) -> bool:
    if mode == "off":
        return False
    if mode == "always":
        return True
    if mode == "allowlist":
        hostname = urlparse(url).hostname or ""
        return any(d in hostname for d in domains)
    return False  # "fallback" is handled in download()


# ── Download Result ──────────────────────────────────────


@dataclass
class DownloadResult:
    status: str                          # ok | failed | not_found
    data: bytes | None = None
    content_type: str = ""
    error_type: str = ""
    error_message: str = ""
    http_status: int | None = None
    attempts: int = 0
    used_proxy: bool = False


# ── Downloader ───────────────────────────────────────────


class ImageDownloader:
    """Async image downloader with configurable proxy policy."""

    def __init__(
        self,
        proxy_url: str,
        proxy_mode: str,
        proxy_domains: list[str],
        referer: str,
        timeout: int,
        max_retries: int,
    ):
        self.proxy_mode = proxy_mode
        self.proxy_domains = proxy_domains
        self.referer = referer
        self.max_retries = max_retries

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        self.proxy_client: httpx.AsyncClient | None = None
        if proxy_url:
            self.proxy_client = httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            )

    async def close(self):
        await self.client.aclose()
        if self.proxy_client:
            await self.proxy_client.aclose()

    # ── Public API ───────────────────────────────────────

    async def download(self, url: str) -> DownloadResult:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Referer": self.referer or _auto_referer(url),
        }

        if self.proxy_mode == "fallback":
            # Try direct first
            result = await self._attempt(url, headers, use_proxy=False)
            if result.status == "ok" or result.http_status == 404:
                return result
            # Fallback to proxy
            if self.proxy_client:
                return await self._attempt(url, headers, use_proxy=True)
            return result

        use_proxy = _should_use_proxy(url, self.proxy_mode, self.proxy_domains)
        return await self._attempt(url, headers, use_proxy=use_proxy)

    # ── Internal ─────────────────────────────────────────

    async def _attempt(
        self, url: str, headers: dict, use_proxy: bool
    ) -> DownloadResult:
        client = (
            self.proxy_client if (use_proxy and self.proxy_client) else self.client
        )
        last_error = ""
        last_status: int | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await client.get(url, headers=headers)

                if resp.status_code == 404:
                    return DownloadResult(
                        status="not_found",
                        http_status=404,
                        attempts=attempt,
                        used_proxy=use_proxy,
                    )

                resp.raise_for_status()
                return DownloadResult(
                    status="ok",
                    data=resp.content,
                    content_type=resp.headers.get("content-type", ""),
                    attempts=attempt,
                    used_proxy=use_proxy,
                )

            except httpx.TimeoutException:
                last_error = "Request timed out"
                last_status = None
            except httpx.HTTPStatusError as exc:
                last_error = f"HTTP {exc.response.status_code}"
                last_status = exc.response.status_code
            except Exception as exc:
                last_error = str(exc)

            if attempt < self.max_retries:
                await asyncio.sleep(attempt * 2)  # exponential back-off

        error_type = "timeout" if "timed out" in last_error.lower() else "http_error"
        return DownloadResult(
            status="failed",
            error_type=error_type,
            error_message=last_error,
            http_status=last_status,
            attempts=self.max_retries,
            used_proxy=use_proxy,
        )
