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
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))


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
