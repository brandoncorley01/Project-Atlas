import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)
from app.routers import ai, alerts, dashboard, engine, health, internal, me, news, parlays, performance, providers, signals, watchlist

app = FastAPI(
    title="Project Atlas API",
    description="Decision intelligence API for Project Atlas",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if not isinstance(detail, str):
        detail = str(detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url.path)
    message = str(exc).strip() or exc.__class__.__name__
    return JSONResponse(
        status_code=500,
        content={"detail": message},
    )

API_PREFIX = "/api/v1"

_DEV_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def _cors_origins() -> list[str]:
    origins = list(settings.cors_origin_list)
    for origin in _DEV_ORIGINS:
        if origin not in origins:
            origins.append(origin)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=(
        r"https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?"
        r"|https://.*\.vercel\.app"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=API_PREFIX, tags=["health"])
app.include_router(me.router, prefix=API_PREFIX, tags=["auth"])
app.include_router(dashboard.router, prefix=API_PREFIX, tags=["dashboard"])
app.include_router(engine.router, prefix=f"{API_PREFIX}/engine", tags=["engine"])
app.include_router(providers.router, prefix=API_PREFIX, tags=["providers"])
app.include_router(signals.router, prefix=f"{API_PREFIX}/signals", tags=["signals"])
app.include_router(parlays.router, prefix=API_PREFIX, tags=["parlays"])
app.include_router(news.router, prefix=API_PREFIX, tags=["news"])
app.include_router(watchlist.router, prefix=API_PREFIX, tags=["watchlist"])
app.include_router(alerts.router, prefix=API_PREFIX, tags=["alerts"])
app.include_router(performance.router, prefix=API_PREFIX, tags=["performance"])
app.include_router(ai.router, prefix=API_PREFIX, tags=["ai"])
app.include_router(internal.router, prefix=API_PREFIX, tags=["internal"])


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "Project Atlas API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": f"{API_PREFIX}/health",
    }
