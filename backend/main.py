
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router
from backend.core.config import get_settings
from backend.core.logging import configure_logging


settings = get_settings()
configure_logging(settings.root_dir)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="AI-powered generic compliance document decoder for Sahl.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# Serve frontend static files
for folder_name in ("css", "js", "assets"):
    folder_path = FRONTEND_DIR / folder_name
    if folder_path.is_dir():
        app.mount(
            f"/{folder_name}",
            StaticFiles(directory=folder_path),
            name=folder_name,
        )


@app.get("/", include_in_schema=False)
def home():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.is_file():
        return {
            "status": "error",
            "message": "Frontend index.html was not found.",
        }
    return FileResponse(index_file)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }
