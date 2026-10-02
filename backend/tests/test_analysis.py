import csv
import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analysis import DEMO_PATH
from app.ingestion.validation import AnalysisError, MAX_UPLOAD_BYTES, MAX_ROWS, REQUIRED, ingest_csv
from app.main import create_app
from app.sessions.store import SessionStore

HEADER = ",".join(REQUIRED)
ROW = ["2026-01-01", "P-1", "Notebook", "Stationery", "2", "20.00", "10", "10.00"]


def csv_bytes(rows=None, header=None):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(header or REQUIRED)
    writer.writerows(rows if rows is not None else [ROW])
    return stream.getvalue().encode()


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


def upload(client, payload):
    return client.post("/api/v1/analysis/upload", content=payload, headers={"Content-Type": "text/csv"})


def test_valid_csv_profile_and_normalization(client):
    row = [*ROW]
    row[1] = " 001 "
    second = ["2026-02-02", "P-2", "Mug", "Home", "0", "0.00", "0", "0"]
    response = upload(client, b"\xef\xbb\xbf" + csv_bytes([row, second]))
    assert response.status_code == 201
    body = response.json()
    profile = body["profile"]
    assert profile["row_count"] == 2
    assert profile["product_count"] == 2
    assert profile["category_count"] == 2
    assert profile["date_range"] == {"start": "2026-01-01", "end": "2026-02-02"}
    assert profile["schema"]["version"] == "v1"
    assert profile["data_quality"]["status"] == "valid"
    assert profile["data_quality"]["missing_values"]["supplier"] == 2
    session = client.app.state.sessions.get(body["analysis_id"])
    assert session.dataset.records[0].product_id == "001"
    assert session.dataset.records[0].revenue == Decimal("20.00")
    assert session.dataset.records[0].supplier is None
    with pytest.raises(FrozenInstanceError):
        session.dataset.records[0].units_sold = 999
    fetched = client.get(f"/api/v1/analysis/{body['analysis_id']}")
    assert fetched.json() == body
    assert fetched.headers["cache-control"] == "no-store"
    assert "records" not in fetched.json()


@pytest.mark.parametrize("payload,code", [
    (b"", "empty_csv"),
    (b" \n", "empty_csv"),
    ((HEADER + "\n").encode(), "empty_csv"),
    ((Path(__file__).parent / "fixtures" / "missing_columns.csv").read_bytes(), "invalid_schema"),
    ((HEADER + '\n"unterminated').encode(), "malformed_csv"),
    ((HEADER + "\n" + ",".join(ROW[:-1])).encode(), "validation_failed"),
    (b"\xff\xfeinvalid", "invalid_encoding"),
    ((HEADER + "\n\x00").encode(), "malformed_csv"),
])
def test_bad_csv(client, payload, code):
    response = upload(client, payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert client.app.state.sessions._sessions == {}


@pytest.mark.parametrize("column,value,code", [
    ("date", "01/02/2026", "invalid_date"),
    ("date", "2026-02-30", "invalid_date"),
    ("units_sold", "many", "invalid_integer"),
    ("units_sold", "1.5", "invalid_integer"),
    ("units_sold", "-1", "invalid_integer"),
    ("inventory", "-1", "invalid_integer"),
    ("revenue", "-10", "invalid_decimal"),
    ("unit_price", "-1", "invalid_decimal"),
    ("revenue", "NaN", "invalid_decimal"),
    ("revenue", "Infinity", "invalid_decimal"),
    ("revenue", "1e5", "invalid_decimal"),
    ("revenue", "12.345", "invalid_decimal"),
    ("revenue", "1,000", "invalid_decimal"),
    ("inventory", "1000000000001", "invalid_integer"),
    ("unit_price", "1000000000001", "invalid_decimal"),
    ("product_name", "x" * 201, "invalid_text"),
    ("product_name", "bad\tname", "invalid_text"),
    ("product_id", "", "missing_value"),
    ("date", "", "missing_value"),
    ("revenue", " ", "missing_value"),
])
def test_invalid_field(client, column, value, code):
    row = [*ROW]
    row[REQUIRED.index(column)] = value
    response = upload(client, csv_bytes([row]))
    assert response.status_code == 422
    issue = response.json()["error"]["errors"][0]
    assert issue == {"row": 2, "column": column, "code": code, "message": issue["message"]}


def test_optional_missing_values_preserved(client):
    response = upload(client, csv_bytes([[*ROW, "", ""]], [*REQUIRED, "supplier", "lead_time_days"]))
    assert response.status_code == 201
    quality = response.json()["profile"]["data_quality"]
    assert quality["missing_values"]["supplier"] == 1
    assert quality["missing_values"]["lead_time_days"] == 1
    assert quality["warnings"]


def test_reordered_columns_quoted_text_and_exact_decimals(client):
    row = [*ROW]
    row[2] = "Notebook, blue"
    row[5] = "0.10"
    response = upload(client, csv_bytes([list(reversed(row))], list(reversed(REQUIRED))))
    assert response.status_code == 201
    record = client.app.state.sessions.get(response.json()["analysis_id"]).dataset.records[0]
    assert record.product_name == "Notebook, blue"
    assert record.revenue == Decimal("0.10")


@pytest.mark.parametrize("name", ['bare"quote', '"closed"junk', ' "misplaced"'])
def test_malformed_quote_syntax_is_rejected(client, name):
    payload = (HEADER + "\n" + ",".join([*ROW[:2], name, *ROW[3:]]) + "\n").encode()
    response = upload(client, payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "malformed_csv"
    assert not client.app.state.sessions._sessions


def test_properly_escaped_quotes_are_preserved(client):
    row = [*ROW]
    row[2] = 'Notebook "blue", edition'
    response = upload(client, csv_bytes([row]))
    assert response.status_code == 201
    record = client.app.state.sessions.get(response.json()["analysis_id"]).dataset.records[0]
    assert record.product_name == row[2]


def test_blank_record_is_not_silently_dropped(client):
    response = upload(client, csv_bytes() + b"\n")
    assert response.status_code == 422
    assert response.json()["error"]["errors"][0]["code"] == "row_width"


def test_invalid_optional_lead_time(client):
    response = upload(client, csv_bytes([[*ROW, "-3"]], [*REQUIRED, "lead_time_days"]))
    assert response.status_code == 422
    assert response.json()["error"]["errors"][0]["column"] == "lead_time_days"


def test_duplicates_rejected_after_normalization(client):
    row = [*ROW]
    row[1] = " P-1 "
    row[5] = "20"
    response = upload(client, csv_bytes([ROW, row]))
    assert response.status_code == 422
    detail = response.json()["error"]
    assert detail["data_quality"]["duplicate_rows"] == 1
    assert detail["errors"][0]["code"] == "duplicate_row"
    assert not client.app.state.sessions._sessions


def test_conflicting_product_labels(client):
    row = [*ROW]
    row[2] = "Different name"
    response = upload(client, csv_bytes([ROW, row]))
    assert response.json()["error"]["errors"][0]["code"] == "conflicting_product"


def test_conflicting_daily_observations_rejected(client):
    row = [*ROW]
    row[5] = "21.00"
    response = upload(client, csv_bytes([ROW, row]))
    assert response.status_code == 422
    detail = response.json()["error"]
    assert detail["data_quality"]["conflicting_product_date_rows"] == 1
    assert detail["errors"][0]["code"] == "conflicting_product_date"


@pytest.mark.parametrize("header", [[*REQUIRED, "other"], [*REQUIRED, "date"], ["Date", *REQUIRED[1:]]])
def test_schema_never_guesses(client, header):
    response = upload(client, csv_bytes(header=header))
    assert response.json()["error"]["code"] == "invalid_schema"


def test_oversized_and_unsupported_upload(client):
    assert upload(client, b"x" * (MAX_UPLOAD_BYTES + 1)).status_code == 413
    response = client.post("/api/v1/analysis/upload", content=b"x", headers={"Content-Type": "application/json"})
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_invalid_content_length(client):
    response = client.post("/api/v1/analysis/upload", content=csv_bytes(), headers={
        "Content-Type": "text/csv", "Content-Length": "-1",
    })
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_content_length"


def test_chunked_oversize_without_content_length(client):
    def chunks():
        yield b"x" * MAX_UPLOAD_BYTES
        yield b"x"
    assert upload(client, chunks()).status_code == 413


def test_row_limit_and_bounded_errors(client):
    response = upload(client, csv_bytes([ROW] * (MAX_ROWS + 1)))
    assert response.status_code == 413
    response = upload(client, csv_bytes([ROW] * 102))
    detail = response.json()["error"]
    assert len(detail["errors"]) == 100
    assert detail["errors_truncated"] is True
    assert detail["data_quality"]["error_count"] == 101


def test_exact_byte_and_row_limits_are_accepted(client):
    rows = [[*ROW[:1], f"P-{index}", *ROW[2:]] for index in range(MAX_ROWS)]
    base = csv_bytes(rows)
    padding, extra = divmod(MAX_UPLOAD_BYTES - len(base), MAX_ROWS)
    for index, row in enumerate(rows):
        row[3] += " " * (padding + (index < extra))
    boundary = csv_bytes(rows)
    assert len(boundary) == MAX_UPLOAD_BYTES
    response = upload(client, boundary)
    assert response.status_code == 201
    assert response.json()["profile"]["row_count"] == MAX_ROWS
    assert upload(client, boundary + b"\n").status_code == 413


def test_streamed_limit_enforced_despite_understated_content_length(client):
    response = client.post("/api/v1/analysis/upload", content=b"x" * (MAX_UPLOAD_BYTES + 1), headers={
        "Content-Type": "text/csv", "Content-Length": "1",
    })
    assert response.status_code == 413


def test_sessions_are_isolated_and_releasable(client):
    first = upload(client, csv_bytes()).json()
    second_row = ["2026-03-01", "Other", "Bottle", "Home", "1", "1", "1", "1"]
    second = upload(client, csv_bytes([second_row])).json()
    assert first["analysis_id"] != second["analysis_id"]
    assert client.get(f"/api/v1/analysis/{first['analysis_id']}").json()["profile"] == first["profile"]
    second["profile"]["row_count"] = 99
    assert client.get(f"/api/v1/analysis/{second['analysis_id']}").json()["profile"]["row_count"] == 1
    assert client.delete(f"/api/v1/analysis/{first['analysis_id']}").status_code == 204
    assert client.get(f"/api/v1/analysis/{first['analysis_id']}").status_code == 404
    assert client.get(f"/api/v1/analysis/{second['analysis_id']}").status_code == 200
    assert client.get("/api/v1/analysis/unknown").json()["error"]["code"] == "analysis_unavailable"


def test_expiry_cleanup_and_capacity():
    now = [1000.0]
    store = SessionStore(clock=lambda: now[0], ttl=30, max_sessions=1)
    with TestClient(create_app(session_store=store)) as client:
        first = upload(client, csv_bytes()).json()
        assert upload(client, csv_bytes()).status_code == 503
        now[0] += 30
        assert client.get(f"/api/v1/analysis/{first['analysis_id']}").status_code == 404
        assert not store._sessions
        assert upload(client, csv_bytes()).status_code == 201
        now[0] += 31
        assert store.cleanup() == 1
        assert store.cleanup() == 0
    assert not store._sessions


def test_memory_capacity_and_shutdown():
    store = SessionStore(max_reserved_bytes=1)
    with TestClient(create_app(session_store=store)) as client:
        assert upload(client, csv_bytes()).status_code == 503
    store = SessionStore()
    with TestClient(create_app(session_store=store)) as client:
        upload(client, csv_bytes())
        assert len(store._sessions) == 1
    assert not store._sessions


def test_wall_clock_adjustments_do_not_change_absolute_lifetime():
    elapsed = [0.0]
    wall = [1_000_000.0]
    store = SessionStore(clock=lambda: elapsed[0], wall_clock=lambda: wall[0])
    first = store.create(ingest_csv(csv_bytes()), "upload")
    wall[0] -= 3600
    elapsed[0] = 1799
    assert store.describe(first["analysis_id"])["expires_at"] == first["expires_at"]
    wall[0] += 7200
    assert store.describe(first["analysis_id"])["expires_at"] == first["expires_at"]
    elapsed[0] = 1800
    with pytest.raises(AnalysisError) as failure:
        store.get(first["analysis_id"])
    assert failure.value.status == 404
    assert not store._sessions


def test_concurrent_creation_respects_default_20_session_limit():
    store = SessionStore()
    dataset = ingest_csv(csv_bytes())

    def create(_):
        try:
            return store.create(dataset, "upload")
        except AnalysisError as failure:
            assert failure.detail["code"] == "session_capacity"
            return None

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(create, range(40)))
    created = [result for result in results if result is not None]
    assert len(created) == len(store._sessions) == 20
    ids = {result["analysis_id"] for result in created}
    assert len(ids) == 20
    assert all(len(key) == 43 for key in ids)  # 32 random bytes, URL-safe base64.
    released = created[0]["analysis_id"]
    store.delete(released)
    replacement = store.create(dataset, "upload")
    assert replacement["analysis_id"] not in ids
    assert released not in store._sessions
    assert len(store._sessions) == 20


def test_default_64_mib_budget_and_delete_release():
    # Increase only the count cap to exercise the independent production byte cap.
    store = SessionStore(max_sessions=100)
    dataset = ingest_csv(csv_bytes())
    ids = [store.create(dataset, "upload")["analysis_id"] for _ in range(31)]
    assert sum(s.dataset.memory_reservation for s in store._sessions.values()) <= 64 * 1024 * 1024
    with pytest.raises(AnalysisError) as failure:
        store.create(dataset, "upload")
    assert failure.value.status == 503
    store.delete(ids[0])
    assert ids[0] not in store._sessions
    assert store.create(dataset, "upload")["analysis_id"] not in ids
    assert len(store._sessions) == 31


def test_api_delete_releases_capacity():
    store = SessionStore(max_reserved_bytes=ingest_csv(csv_bytes()).memory_reservation)
    with TestClient(create_app(session_store=store)) as client:
        first = upload(client, csv_bytes()).json()
        assert upload(client, csv_bytes()).status_code == 503
        assert client.delete(f"/api/v1/analysis/{first['analysis_id']}").status_code == 204
        assert not store._sessions
        assert upload(client, csv_bytes()).status_code == 201


def test_demo_is_deterministic_and_uses_same_validation(client):
    first = client.post("/api/v1/analysis/demo")
    second = client.post("/api/v1/analysis/demo")
    assert first.status_code == second.status_code == 201
    assert first.json()["analysis_id"] != second.json()["analysis_id"]
    assert first.json()["profile"] == second.json()["profile"]
    profile = first.json()["profile"]
    assert profile["row_count"] == 540
    assert profile["product_count"] == 6
    assert profile["category_count"] == 3
    assert profile["date_range"] == {"start": "2026-01-01", "end": "2026-03-31"}
    assert profile == ingest_csv(DEMO_PATH.read_bytes()).profile


def test_unavailable_demo_has_structured_error(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.analysis.DEMO_PATH", tmp_path / "missing.csv")
    response = client.post("/api/v1/analysis/demo")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "demo_unavailable"


@pytest.mark.parametrize("operation", ["open", "is_file"])
def test_demo_read_error_does_not_expose_filesystem_details(client, monkeypatch, operation):
    def deny_read(*args, **kwargs):
        raise PermissionError("private filesystem path and internal details")

    monkeypatch.setattr(Path, operation, deny_read)
    response = client.post("/api/v1/analysis/demo")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "demo_unavailable"
    assert "private filesystem" not in response.text


def test_cors_preflight_and_error_response(client):
    for method in ("POST", "DELETE"):
        response = client.options("/api/v1/analysis/upload", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        })
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    blocked = client.options("/api/v1/analysis/upload", headers={
        "Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST",
    })
    assert blocked.status_code == 400
    assert "access-control-allow-origin" not in blocked.headers
    response = client.post("/api/v1/analysis/upload", content=b"", headers={
        "Content-Type": "text/csv", "Origin": "http://localhost:5173",
    })
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["cache-control"] == "no-store"


def test_delete_response_cors_and_disallowed_preflight_method(client):
    first = upload(client, csv_bytes()).json()
    response = client.delete(f"/api/v1/analysis/{first['analysis_id']}", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["cache-control"] == "no-store"
    response = client.options("/api/v1/analysis/upload", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "PUT",
    })
    assert response.status_code == 400


def test_binary_content_is_validated_not_trusted_by_media_type(client):
    response = client.post("/api/v1/analysis/upload", content=b"PK\x00fake workbook", headers={
        "Content-Type": "application/octet-stream",
    })
    assert response.status_code == 422
    response = client.post("/api/v1/analysis/upload", content=csv_bytes(), headers={
        "Content-Type": "application/octet-stream",
    })
    assert response.status_code == 201
