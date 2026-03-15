from enum import Enum
from typing import Optional

from pydantic import BaseModel


# ── Enums ────────────────────────────────────────────────


class ProxyMode(str, Enum):
    OFF = "off"
    ALWAYS = "always"
    ALLOWLIST = "allowlist"
    FALLBACK = "fallback"


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Job Configuration (saved per job) ────────────────────


class JobConfig(BaseModel):
    image_paths: list[str]            # e.g. ["Images[]", "variants[].Image"]
    products_key: str = ""            # root key holding products array (blank = auto)
    product_id_key: str = ""          # field used as folder name on CDN
    upload_path_prefix: str = "products"
    proxy_mode: ProxyMode = ProxyMode.FALLBACK
    proxy_domains: list[str] = []
    referer: str = ""
    concurrency: int = 20
    chunk_size: int = 1000
    failed_retry_rounds: int = 2      # number of retry passes for failed images
    enable_failed_retry_pass: bool = True  # enable automatic retry for failed images


# ── Job Progress (tracked in memory) ────────────────────


class JobProgress(BaseModel):
    job_id: str
    status: JobStatus
    total_products: int = 0
    processed_products: int = 0
    total_images: int = 0
    succeeded_images: int = 0
    failed_images: int = 0
    skipped_images: int = 0
    created_at: str = ""
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
