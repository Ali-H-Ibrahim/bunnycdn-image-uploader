"""
jobs.py – Lightweight in-memory job manager with disk persistence.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

from app.config import settings
from app.models import JobConfig, JobProgress, JobStatus


class JobManager:
    """Create / track / update processing jobs."""

    def __init__(self):
        self._jobs: dict[str, JobProgress] = {}
        os.makedirs(settings.jobs_dir, exist_ok=True)

    # ── CRUD ─────────────────────────────────────────────

    def create_job(self, config: JobConfig) -> str:
        job_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        job_dir = os.path.join(settings.jobs_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)

        # Persist config to disk
        with open(os.path.join(job_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2)

        self._jobs[job_id] = JobProgress(
            job_id=job_id,
            status=JobStatus.QUEUED,
            created_at=datetime.now().isoformat(),
        )
        return job_id

    def get_progress(self, job_id: str) -> JobProgress | None:
        return self._jobs.get(job_id)

    def get_config(self, job_id: str) -> JobConfig:
        path = os.path.join(settings.jobs_dir, job_id, "config.json")
        with open(path, encoding="utf-8") as f:
            return JobConfig(**json.load(f))

    def get_job_dir(self, job_id: str) -> str:
        return os.path.join(settings.jobs_dir, job_id)

    # ── Status Updates ───────────────────────────────────

    def update_status(self, job_id: str, status: JobStatus):
        if job_id in self._jobs:
            self._jobs[job_id].status = status

    def set_totals(self, job_id: str, total_products: int, total_images: int):
        if job_id in self._jobs:
            self._jobs[job_id].total_products = total_products
            self._jobs[job_id].total_images = total_images

    def increment_processed(self, job_id: str):
        if job_id in self._jobs:
            self._jobs[job_id].processed_products += 1

    def increment_succeeded(self, job_id: str):
        if job_id in self._jobs:
            self._jobs[job_id].succeeded_images += 1

    def increment_failed(self, job_id: str):
        if job_id in self._jobs:
            self._jobs[job_id].failed_images += 1

    def decrement_failed(self, job_id: str):
        if job_id in self._jobs:
            self._jobs[job_id].failed_images = max(0, self._jobs[job_id].failed_images - 1)

    def increment_skipped(self, job_id: str):
        if job_id in self._jobs:
            self._jobs[job_id].skipped_images += 1

    def complete_job(self, job_id: str, error_message: str | None = None):
        if job_id in self._jobs:
            p = self._jobs[job_id]
            p.status = JobStatus.FAILED if error_message else JobStatus.COMPLETED
            p.completed_at = datetime.now().isoformat()
            p.error_message = error_message


# Singleton used across the application
job_manager = JobManager()
