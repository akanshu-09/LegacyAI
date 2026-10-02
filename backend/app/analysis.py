"""Versioned analysis API. Raw CSV avoids multipart buffering/dependencies."""

from pathlib import Path

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app.ingestion.validation import AnalysisError, MAX_UPLOAD_BYTES, ingest_csv
from app.analytics.metrics import calculate_analytics
from app.detectors.engine import detect_issues

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])
DEMO_PATH = Path(__file__).resolve().parents[2] / "data" / "demo_business.csv"


@router.post("/upload", status_code=201)
async def upload(request: Request):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in ("text/csv", "application/octet-stream"):
        raise AnalysisError("unsupported_media_type", "Send the CSV as the request body with Content-Type: text/csv.", 415)
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            length = int(declared_length)
            if length < 0:
                raise ValueError
        except ValueError:
            raise AnalysisError("invalid_content_length", "Content-Length must be a nonnegative integer.", 400) from None
        if length > MAX_UPLOAD_BYTES:
            raise AnalysisError("upload_too_large", "CSV must be at most 2 MiB.", 413)
    # Bound the accumulated body even when Content-Length is absent or inaccurate.
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_UPLOAD_BYTES:
            raise AnalysisError("upload_too_large", "CSV must be at most 2 MiB.", 413)
        body.extend(chunk)
    dataset = await run_in_threadpool(ingest_csv, bytes(body))
    return request.app.state.sessions.create(dataset, "upload")


@router.post("/demo", status_code=201)
def demo(request: Request):
    try:
        if not DEMO_PATH.is_file():
            raise AnalysisError("demo_unavailable", "Synthetic demo data is unavailable. Check the repository data directory.", 503)
        with DEMO_PATH.open("rb") as file:
            payload = file.read(MAX_UPLOAD_BYTES + 1)
    except OSError:
        raise AnalysisError("demo_unavailable", "Synthetic demo data could not be read. Check the repository data directory.", 503) from None
    return request.app.state.sessions.create(ingest_csv(payload), "demo")


@router.get("/{analysis_id}")
def profile(analysis_id: str, request: Request):
    return request.app.state.sessions.describe(analysis_id)


@router.get("/{analysis_id}/analytics")
def analytics(analysis_id: str, request: Request):
    store = request.app.state.sessions
    session = store.get(analysis_id)
    result = calculate_analytics(session.dataset.records)
    # No cache or lifetime extension; reject expiry/release during computation.
    metadata = store.describe(analysis_id)
    return {"analysis_id": analysis_id, "expires_at": metadata["expires_at"], **result}


@router.delete("/{analysis_id}", status_code=204)
def release(analysis_id: str, request: Request):
    request.app.state.sessions.delete(analysis_id)
    return Response(status_code=204)


@router.get("/{analysis_id}/issues")
def issues(analysis_id: str, request: Request):
    store = request.app.state.sessions
    session = store.get(analysis_id)
    result = detect_issues(session.dataset.records)
    metadata = store.describe(analysis_id)
    return {"analysis_id": analysis_id, "expires_at": metadata["expires_at"], **result}
