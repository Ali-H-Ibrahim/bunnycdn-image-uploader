"""
pipeline.py – Core processing: load JSON ➜ download images ➜ upload to CDN ➜ save result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re

from app.config import settings
import mimetypes

from app.downloader import DownloadResult, ImageDownloader, generate_filename
from app.jobs import job_manager
from app.models import JobStatus
from app.parsing import (
    REMOVE_MARKER,
    SOURCE_FILE,
    SOURCE_INVALID,
    SOURCE_URL,
    cleanup_removed_images,
    extract_image_locations,
    update_image_url,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif", ".bmp", ".tiff", ".tif"}
from app.uploader import BunnyUploader

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────


def _sanitize(value: str) -> str:
    """Make a string safe for use as a path segment."""
    return re.sub(r"[^\w\-.]", "_", str(value)).strip("_")[:100] or "unknown"


def _product_id(product: dict, id_key: str, index: int) -> str:
    """Derive a short folder name for a product."""
    # Explicit key
    if id_key and id_key in product:
        v = str(product[id_key])
        if v and v.lower() != "nan":
            return _sanitize(v)

    # Auto-detect common fields
    for key in ("Web SKU", "Amazon ASIN", "sku", "SKU", "id", "asin", "ASIN"):
        if key in product:
            v = str(product[key])
            if v and v.lower() != "nan":
                return _sanitize(v)

    return f"product_{index}"


# ── Input / Output ───────────────────────────────────────


class InputData:
    """Wrapper that keeps the original JSON structure intact."""

    def __init__(self, raw, products: list, wrapper_key: str | None):
        self.raw = raw                # original parsed JSON
        self.products = products      # reference into raw
        self.wrapper_key = wrapper_key


def load_input(filepath: str, products_key: str = "") -> InputData:
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

    if isinstance(data, list):
        return InputData(data, data, None)

    if isinstance(data, dict):
        if products_key and products_key in data:
            return InputData(data, data[products_key], products_key)

        # Auto-detect first key whose value is a list of dicts
        for key, value in data.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return InputData(data, value, key)

        raise ValueError(
            f"Cannot auto-detect products array. Top-level keys: {list(data.keys())}"
        )

    raise ValueError("JSON must be an array of products or an object containing one")


def save_output(filepath: str, input_data: InputData):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(input_data.raw, f, ensure_ascii=False, indent=2)


# ── Main Entry Point ────────────────────────────────────


async def process_job(job_id: str):
    """Background task that processes an entire job."""
    try:
        config = job_manager.get_config(job_id)
        job_dir = job_manager.get_job_dir(job_id)
        input_path = os.path.join(job_dir, "input.json")

        job_manager.update_status(job_id, JobStatus.PROCESSING)

        # ── Load input ───────────────────────────────────
        input_data = await asyncio.to_thread(load_input, input_path, config.products_key)
        products = input_data.products

        # ── Count total images ───────────────────────────
        total_images = 0
        for product in products:
            for path_str in config.image_paths:
                total_images += len(extract_image_locations(product, path_str))

        job_manager.set_totals(job_id, len(products), total_images)
        logger.info("Job %s: %d products, %d images", job_id, len(products), total_images)

        # ── Init clients ─────────────────────────────────
        downloader = ImageDownloader(
            proxy_url=settings.proxy_url,
            proxy_mode=config.proxy_mode.value,
            proxy_domains=config.proxy_domains,
            referer=config.referer,
            timeout=settings.download_timeout,
            max_retries=settings.max_retries,
        )
        uploader = BunnyUploader(
            storage_zone=settings.bunny_storage_zone,
            access_key=settings.bunny_access_key,
            cdn_base_url=settings.bunny_cdn_base_url,
        )

        all_errors: list[dict] = []
        semaphore = asyncio.Semaphore(config.concurrency)

        # ── Process in chunks ────────────────────────────
        for chunk_start in range(0, len(products), config.chunk_size):
            chunk_end = min(chunk_start + config.chunk_size, len(products))
            chunk = products[chunk_start:chunk_end]
            logger.info("Job %s: chunk [%d:%d]", job_id, chunk_start, chunk_end)

            # Build tasks for every image in this chunk
            tasks: list[asyncio.Task] = []
            for local_idx, product in enumerate(chunk):
                global_idx = chunk_start + local_idx
                pid = _product_id(product, config.product_id_key, global_idx)

                for path_str in config.image_paths:
                    for loc in extract_image_locations(product, path_str):
                        tasks.append(
                            asyncio.create_task(
                                _process_image(
                                    sem=semaphore,
                                    loc=loc,
                                    product=product,
                                    product_id=pid,
                                    upload_prefix=config.upload_path_prefix,
                                    downloader=downloader,
                                    uploader=uploader,
                                    product_index=global_idx,
                                    errors=all_errors,
                                    job_id=job_id,
                                )
                            )
                        )

            # Wait for all images in the chunk
            await asyncio.gather(*tasks)

            # Cleanup: remove failed/invalid entries from products
            for product in chunk:
                cleanup_removed_images(product, config.image_paths)

            # Mark products as processed
            for _ in chunk:
                job_manager.increment_processed(job_id)

        # ── Cleanup & save ───────────────────────────────
        await downloader.close()
        await uploader.close()

        await asyncio.to_thread(
            save_output, os.path.join(job_dir, "result.json"), input_data
        )
        await asyncio.to_thread(
            _save_errors, os.path.join(job_dir, "errors.json"), all_errors
        )

        job_manager.complete_job(job_id)
        logger.info("Job %s: completed", job_id)

    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        job_manager.complete_job(job_id, error_message=str(exc))


def _read_local_file(filepath: str) -> DownloadResult:
    """Read a local image file and return a DownloadResult."""
    filepath = filepath.strip()
    if not os.path.exists(filepath):
        return DownloadResult(status="not_found", error_type="not_found",
                              error_message=f"File not found: {filepath}")

    ext = os.path.splitext(filepath)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        return DownloadResult(status="failed", error_type="not_image",
                              error_message=f"Not a recognized image file ({ext}): {filepath}")

    try:
        with open(filepath, "rb") as f:
            data = f.read()
        content_type = mimetypes.guess_type(filepath)[0] or ""
        return DownloadResult(status="ok", data=data, content_type=content_type, attempts=1)
    except Exception as exc:
        return DownloadResult(status="failed", error_type="read_error",
                              error_message=f"Cannot read file: {exc}")


def _save_errors(filepath: str, errors: list[dict]):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)


# ── Single Image Processing ─────────────────────────────


async def _process_image(
    sem: asyncio.Semaphore,
    loc,
    product: dict,
    product_id: str,
    upload_prefix: str,
    downloader: ImageDownloader,
    uploader: BunnyUploader,
    product_index: int,
    errors: list[dict],
    job_id: str,
):
    async with sem:
        # ── Invalid source ───────────────────────────────
        if loc.source_type == SOURCE_INVALID:
            job_manager.increment_failed(job_id)
            errors.append({
                "product_index": product_index,
                "product_id": product_id,
                "image_path": loc.path_display,
                "source_url": loc.original_url,
                "status": "failed",
                "error_type": "invalid_source",
                "http_status": None,
                "error_message": f"Not a valid URL or file path: {loc.original_url!r}",
                "stage": "validation",
                "attempts": 0,
                "used_proxy": False,
            })
            update_image_url(product, loc.keys, REMOVE_MARKER)
            return

        # ── Read image data (URL or local file) ──────────
        if loc.source_type == SOURCE_FILE:
            read_result = await asyncio.to_thread(
                _read_local_file, loc.original_url
            )
        else:
            read_result = await downloader.download(loc.original_url)

        if read_result.status == "not_found":
            job_manager.increment_skipped(job_id)
            errors.append(_error_dict(
                product_index, product_id, loc, "not_found", "not_found",
                404 if loc.source_type == SOURCE_URL else None,
                "Image not found" if loc.source_type == SOURCE_URL
                    else f"File not found: {loc.original_url}",
                "download" if loc.source_type == SOURCE_URL else "read_file",
                read_result,
            ))
            update_image_url(product, loc.keys, REMOVE_MARKER)
            return

        if read_result.status != "ok":
            job_manager.increment_failed(job_id)
            errors.append(_error_dict(
                product_index, product_id, loc, "failed", read_result.error_type,
                read_result.http_status, read_result.error_message,
                "download" if loc.source_type == SOURCE_URL else "read_file",
                read_result,
            ))
            update_image_url(product, loc.keys, REMOVE_MARKER)
            return

        # ── Upload ───────────────────────────────────────
        filename = generate_filename(read_result.data, read_result.content_type)
        upload_path = f"{upload_prefix}/{product_id}"

        upload_result = await uploader.upload(read_result.data, upload_path, filename)

        if upload_result["status"] != "ok":
            job_manager.increment_failed(job_id)
            errors.append(_error_dict(
                product_index, product_id, loc, "failed", "upload_error",
                None, upload_result.get("error", "Upload failed"), "upload",
                read_result,
            ))
            update_image_url(product, loc.keys, REMOVE_MARKER)
            return

        # ── Success ──────────────────────────────────────
        update_image_url(product, loc.keys, upload_result["url"])
        job_manager.increment_succeeded(job_id)


def _error_dict(
    product_index, product_id, loc, status, error_type,
    http_status, message, stage, dl_result,
) -> dict:
    return {
        "product_index": product_index,
        "product_id": product_id,
        "image_path": loc.path_display,
        "source_url": loc.original_url,
        "status": status,
        "error_type": error_type,
        "http_status": http_status,
        "error_message": message,
        "stage": stage,
        "attempts": dl_result.attempts,
        "used_proxy": dl_result.used_proxy,
    }
