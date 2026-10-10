from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.core.config import get_settings
from backend.core.logging import configure_logging


settings = get_settings()
configure_logging(settings.root_dir)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "AI-powered generic compliance document "
        "decoder for Sahl."
    ),
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }