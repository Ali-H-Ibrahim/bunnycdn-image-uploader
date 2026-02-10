import os

from pydantic_settings import BaseSettings

# Resolve .env relative to project root (parent of app/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_FILE = os.path.join(_PROJECT_ROOT, ".env")


class Settings(BaseSettings):
    # BunnyCDN
    bunny_storage_zone: str = ""
    bunny_access_key: str = ""
    bunny_cdn_base_url: str = ""   # e.g. https://your-zone.b-cdn.net  (leave empty to use storage URL)

    # Proxy
    proxy_url: str = ""

    # Defaults
    default_proxy_mode: str = "fallback"
    default_concurrency: int = 20
    default_chunk_size: int = 1000
    max_retries: int = 3
    download_timeout: int = 30

    # Storage
    jobs_dir: str = os.path.join(_PROJECT_ROOT, "jobs")

    model_config = {"env_file": _ENV_FILE, "env_file_encoding": "utf-8"}


settings = Settings()
