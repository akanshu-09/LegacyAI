"""Versioned analysis API. Raw CSV avoids multipart buffering/dependencies."""

from pathlib import Path

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app.ingestion.validation import AnalysisError, MAX_UPLOAD_BYTES, ingest_csv
from app.analytics.metrics import calculate_analytics
from app.detectors.engine import detect_issues
from app.schemas.ai import DecisionReasoning
from app.verification.verifier import verify_claims
from app.reasoning.provider import get_reasoner, ProviderError
from app.ask.intent import classify_intent
from app.ask.engine import execute_ask

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])
DEMO_PATH = Path(__file__).resolve().parents[2] / "data" / "demo_business.csv"


async def _process_decision(analysis_id: str, issue_id: str, request: Request, reasoner_override=None):
    store = request.app.state.sessions
    session = store.get(analysis_id)
    detection = detect_issues(session.dataset.records)
    issues_list = detection.get("issues", [])
    evidence_list = detection.get("evidence", [])
    evaluations_list = detection.get("evaluations", [])

    issue = next((i for i in issues_list if i.get("issue_id") == issue_id), None)
    if not issue:
        eval_item = next((e for e in evaluations_list if issue_id in e.get("issue_ids", []) or e.get("entity_id") == issue_id), None)
        if eval_item and eval_item.get("status") == "unsupported":
            metadata = store.describe(analysis_id)
            reasoning = DecisionReasoning(
                summary="LegacyAI abstained from generating recommendations because the issue is in an unsupported evaluation state.",
                root_causes=[],
                recommendation={"action": "Abstain", "target": eval_item.get("entity_name", "Target product"), "timeframe_days": 14},
                assumptions=[],
                uncertainties=[f"Unsupported reason: {eval_item.get('reason')}"],
                what_would_change_this_decision=["Provide continuous daily sales observations and fresh inventory snapshot."],
                evidence_ids=[],
                abstain=True,
                abstain_reason=f"Issue evaluation status is unsupported: {eval_item.get('reason')}"
            )
            verification = verify_claims(reasoning, {"issue_id": issue_id}, [])
            return {
                "analysis_id": analysis_id,
                "expires_at": metadata["expires_at"],
                "issue_id": issue_id,
                "issue": {
                    "issue_id": issue_id,
                    "title": f"Unsupported issue ({eval_item.get('issue_type')})",
                    "severity": "UNSUPPORTED",
                    "entity_name": eval_item.get("entity_name"),
                    "summary": f"Detection is unsupported due to: {eval_item.get('reason')}",
                    "evidence_ids": []
                },
                "ai_available": True,
                "ai_error": None,
                "reasoning": reasoning.model_dump(),
                "verification": verification.model_dump(),
                "cited_evidence": []
            }
        raise AnalysisError("issue_not_found", f"No issue found with ID '{issue_id}' for this analysis session.", 404)

    issue_evidence = [ev for ev in evidence_list if ev.get("evidence_id") in set(issue.get("evidence_ids", []))]
    metadata = store.describe(analysis_id)

    try:
        reasoner = reasoner_override if reasoner_override is not None else get_reasoner()
        reasoning = await reasoner.generate_decision(
            issue=issue,
            evidence=issue_evidence,
            context={"total_rows": len(session.dataset.records)}
        )
        verification = verify_claims(reasoning, issue, issue_evidence)
        valid_set = set(verification.valid_citations)
        cited_evidence = [ev for ev in issue_evidence if ev.get("evidence_id") in valid_set]
        if not cited_evidence:
            cited_evidence = issue_evidence

        return {
            "analysis_id": analysis_id,
            "expires_at": metadata["expires_at"],
            "issue_id": issue_id,
            "issue": issue,
            "ai_available": True,
            "ai_error": None,
            "reasoning": reasoning.model_dump(),
            "verification": verification.model_dump(),
            "cited_evidence": cited_evidence
        }
    except ProviderError as exc:
        return {
            "analysis_id": analysis_id,
            "expires_at": metadata["expires_at"],
            "issue_id": issue_id,
            "issue": issue,
            "ai_available": False,
            "ai_error": str(exc.message),
            "reasoning": None,
            "verification": {
                "status": "unverified",
                "details": [f"AI decision reasoning unavailable: {exc.message}"],
                "valid_citations": [],
                "invalid_citations": []
            },
            "cited_evidence": issue_evidence
        }


@router.post("/{analysis_id}/decisions/{issue_id}")
async def decision_by_issue_id(analysis_id: str, issue_id: str, request: Request):
    return await _process_decision(analysis_id, issue_id, request)


@router.post("/{analysis_id}/decisions")
async def decision_body(analysis_id: str, request: Request):
    try:
        body = await request.json()
        issue_id = body.get("issue_id")
        if not issue_id:
            raise ValueError
    except Exception:
        raise AnalysisError("invalid_request_body", "Request body must be JSON containing 'issue_id'.", 400) from None
    return await _process_decision(analysis_id, issue_id, request)



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


@router.post("/{analysis_id}/ask")
async def ask(analysis_id: str, request: Request):
    store = request.app.state.sessions
    session = store.get(analysis_id)
    try:
        body = await request.json()
        question = body.get("question", "").strip()
        if not question:
            raise ValueError
    except Exception:
        raise AnalysisError("invalid_request_body", "Request body must be JSON containing a non-empty 'question' string.", 400) from None

    intent = classify_intent(question, session.dataset.records)
    factual_finding, evidence_list, default_rec = execute_ask(session.dataset.records, intent)
    metadata = store.describe(analysis_id)

    if not intent.supported or intent.intent_type == "unsupported":
        return {
            "analysis_id": analysis_id,
            "expires_at": metadata["expires_at"],
            "question": question,
            "intent": intent.model_dump(),
            "factual_finding": factual_finding.model_dump(),
            "ai_available": True,
            "ai_error": None,
            "explanation": "LegacyAI abstained from answering this question because the requested topic or metric is not present in the verified dataset.",
            "recommendation": None,
            "verification": {
                "status": "verified",
                "details": ["Explicit abstention verified for unsupported question."],
                "valid_citations": [],
                "invalid_citations": []
            },
            "evidence": []
        }

    virtual_issue = {
        "issue_id": f"ASK-{hash(question) & 0xFFFFFFFF}",
        "title": f"Question: {question}",
        "summary": factual_finding.finding,
        "entity_name": intent.target_entity or "Business Overview",
        "severity": "LOW",
        "evidence_ids": [ev["evidence_id"] for ev in evidence_list]
    }

    try:
        reasoner = get_reasoner()
        reasoning = await reasoner.generate_decision(
            issue=virtual_issue,
            evidence=evidence_list,
            context={"question": question, "intent": intent.intent_type}
        )
        verification = verify_claims(reasoning, virtual_issue, evidence_list)
        valid_set = set(verification.valid_citations)
        cited_evidence = [ev for ev in evidence_list if ev.get("evidence_id") in valid_set]
        if not cited_evidence:
            cited_evidence = evidence_list

        rec = default_rec
        if reasoning.recommendation and reasoning.recommendation.action:
            rec = {
                "action": reasoning.recommendation.action,
                "target": reasoning.recommendation.target,
                "timeframe_days": reasoning.recommendation.timeframe_days
            }

        return {
            "analysis_id": analysis_id,
            "expires_at": metadata["expires_at"],
            "question": question,
            "intent": intent.model_dump(),
            "factual_finding": factual_finding.model_dump(),
            "ai_available": True,
            "ai_error": None,
            "explanation": reasoning.summary,
            "recommendation": rec,
            "verification": verification.model_dump(),
            "evidence": cited_evidence
        }
    except ProviderError as exc:
        return {
            "analysis_id": analysis_id,
            "expires_at": metadata["expires_at"],
            "question": question,
            "intent": intent.model_dump(),
            "factual_finding": factual_finding.model_dump(),
            "ai_available": False,
            "ai_error": str(exc.message),
            "explanation": factual_finding.finding,
            "recommendation": default_rec,
            "verification": {
                "status": "unverified",
                "details": [f"AI explanation unavailable ({exc.message}). Displaying deterministic Python finding."],
                "valid_citations": [],
                "invalid_citations": []
            },
            "evidence": evidence_list
        }

