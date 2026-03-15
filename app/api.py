"""
api.py – FastAPI router: create jobs, poll progress, download results.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.jobs import job_manager
from app.models import JobConfig, ProxyMode
from app.pipeline import process_job

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


# ── Web UI ───────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── Jobs API ─────────────────────────────────────────────


@router.post("/v1/jobs")
async def create_job(
    file: UploadFile = File(...),
    image_paths: str = Form(...),
    products_key: str = Form(""),
    product_id_key: str = Form(""),
    upload_path_prefix: str = Form("products"),
    proxy_mode: str = Form("fallback"),
    proxy_domains: str = Form(""),
    referer: str = Form(""),
    concurrency: int = Form(20),
    chunk_size: int = Form(1000),
    failed_retry_rounds: int = Form(2),
    enable_failed_retry_pass: bool = Form(True),
):
    # Parse multi-line or comma-separated image paths
    paths = [p.strip() for p in image_paths.replace(",", "\n").split("\n") if p.strip()]
    if not paths:
        raise HTTPException(400, "At least one image path is required")

    domains = [d.strip() for d in proxy_domains.split(",") if d.strip()]

    config = JobConfig(
        image_paths=paths,
        products_key=products_key,
        product_id_key=product_id_key,
        upload_path_prefix=upload_path_prefix,
        proxy_mode=ProxyMode(proxy_mode),
        proxy_domains=domains,
        referer=referer,
        concurrency=min(concurrency, 50),
        chunk_size=min(chunk_size, 5000),
        failed_retry_rounds=max(0, min(failed_retry_rounds, 10)),
        enable_failed_retry_pass=enable_failed_retry_pass,
    )

    # Create job & save uploaded file
    job_id = job_manager.create_job(config)
    job_dir = job_manager.get_job_dir(job_id)

    input_path = os.path.join(job_dir, "input.json")
    content = await file.read()
    with open(input_path, "wb") as f:
        f.write(content)

    # Launch background processing
    asyncio.create_task(process_job(job_id))

    return {"job_id": job_id, "status": "queued"}


@router.get("/v1/jobs/{job_id}")
async def get_job_status(job_id: str):
    progress = job_manager.get_progress(job_id)
    if not progress:
        raise HTTPException(404, "Job not found")
    return progress.model_dump()


@router.get("/v1/jobs/{job_id}/result")
async def download_result(job_id: str):
    path = os.path.join(job_manager.get_job_dir(job_id), "result.json")
    if not os.path.exists(path):
        raise HTTPException(404, "Result not ready yet")
    return FileResponse(path, filename=f"result_{job_id}.json", media_type="application/json")


@router.get("/v1/jobs/{job_id}/errors")
async def download_errors(job_id: str):
    path = os.path.join(job_manager.get_job_dir(job_id), "errors.json")
    if not os.path.exists(path):
        raise HTTPException(404, "Error report not ready yet")
    return FileResponse(path, filename=f"errors_{job_id}.json", media_type="application/json")


@router.post("/v1/jobs/{job_id}/retry-from-errors")
async def retry_from_errors(job_id: str):
    """Create a new job that retries all failed images from an existing job."""
    from app.pipeline import process_job_retry_from_errors

    source_job_dir = job_manager.get_job_dir(job_id)
    
    if not os.path.exists(os.path.join(source_job_dir, "errors.json")):
        raise HTTPException(404, "errors.json not found for this job")
    if not os.path.exists(os.path.join(source_job_dir, "input.json")):
        raise HTTPException(404, "input.json not found for this job")
    
    try:
        config = job_manager.get_config(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Job config not found")

    new_job_id = job_manager.create_job(config)
    new_job_dir = job_manager.get_job_dir(new_job_id)

    import shutil
    shutil.copy(
        os.path.join(source_job_dir, "input.json"),
        os.path.join(new_job_dir, "input.json")
    )
    shutil.copy(
        os.path.join(source_job_dir, "errors.json"),
        os.path.join(new_job_dir, "source_errors.json")
    )

    asyncio.create_task(process_job_retry_from_errors(new_job_id))

    return {
        "job_id": new_job_id,
        "status": "queued",
        "source_job_id": job_id,
        "message": "Retry job created - will process failed images only"
    }
