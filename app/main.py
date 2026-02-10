"""
main.py – FastAPI application entry point.

Run with:  python run.py
   or:     uvicorn app.main:app --reload
"""

import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router

# ── Logging ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# ── App ──────────────────────────────────────────────────

app = FastAPI(title="Image Processor", version="1.0.0")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
static_dir = os.path.join(_PROJECT_ROOT, "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(router)
