"""FastAPI modular monolith: health and deterministic ingestion."""

import os
import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.analysis import router
from app.ingestion.validation import AnalysisError
from app.sessions.store import SessionStore

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def create_app(*, session_store: SessionStore | None = None) -> FastAPI:
    store = session_store if session_store is not None else SessionStore()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async def sweep():
            while True:
                await asyncio.sleep(60)
                store.cleanup()

        task = asyncio.create_task(sweep())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            store.clear()

    app = FastAPI(title="LegacyAI", version="0.2.0", lifespan=lifespan)
    app.state.sessions = store
    app.include_router(router)

    @app.exception_handler(AnalysisError)
    async def analysis_error(request, exc):
        return JSONResponse(status_code=exc.status, content={"error": exc.detail})

    @app.middleware("http")
    async def no_store_analysis(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/analysis"):
            response.headers["Cache-Control"] = "no-store"
        return response
    origins = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "legacyai-backend"}

    return app


app = create_app()
