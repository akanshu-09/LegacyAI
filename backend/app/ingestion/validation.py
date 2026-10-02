"""Strict CSV contract, normalization and structural data-quality profile."""

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

REQUIRED = ("date", "product_id", "product_name", "category", "units_sold", "revenue", "inventory", "unit_price")
OPTIONAL = ("supplier", "lead_time_days")
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10_000
MAX_ERRORS = 100
MAX_TEXT_LENGTH = 200
MAX_NUMBER = Decimal("1000000000000")


class AnalysisError(Exception):
    def __init__(self, code: str, message: str, status: int = 422, **details):
        self.status = status
        self.detail = {"code": code, "message": message, **details}


@dataclass(frozen=True)
class Record:
    date: date
    product_id: str
    product_name: str
    category: str
    units_sold: int
    revenue: Decimal
    inventory: int
    unit_price: Decimal
    supplier: str | None
    lead_time_days: int | None


@dataclass(frozen=True)
class Dataset:
    records: tuple[Record, ...]
    profile: dict
    # Conservative reservation covering normalized strings, Decimal objects,
    # duplicate bookkeeping and profile, rather than raw file bytes alone.
    memory_reservation: int


def validate_csv_quotes(text: str) -> None:
    # csv.reader(strict=True) still treats bare quotes in unquoted fields as
    # literal text. Reject that malformed syntax instead of guessing intent.
    state = "start"
    for char in text:
        if state == "quoted":
            if char == '"':
                state = "closed"
        elif state == "closed":
            if char == '"':
                state = "quoted"
            elif char == "," or char in "\r\n":
                state = "start"
            else:
                raise AnalysisError("malformed_csv", "A closing CSV quote must be followed by a delimiter or line ending.")
        elif char == '"':
            if state != "start":
                raise AnalysisError("malformed_csv", "Quotes inside a CSV field must be enclosed and escaped as doubled quotes.")
            state = "quoted"
        elif char == "," or char in "\r\n":
            state = "start"
        else:
            state = "unquoted"
    if state == "quoted":
        raise AnalysisError("malformed_csv", "CSV contains an unterminated quoted field.")


def ingest_csv(payload: bytes) -> Dataset:
    if len(payload) > MAX_UPLOAD_BYTES:
        raise AnalysisError("upload_too_large", "CSV must be at most 2 MiB.", 413)
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AnalysisError("invalid_encoding", "Use a UTF-8 encoded CSV.") from None
    if not text.strip():
        raise AnalysisError("empty_csv", "CSV must contain a header and at least one data row.")
    if "\x00" in text:
        raise AnalysisError("malformed_csv", "CSV must not contain null bytes.")
    validate_csv_quotes(text)

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        columns = next(reader)
    except (csv.Error, StopIteration):
        raise AnalysisError("malformed_csv", "Could not read the CSV header.") from None
    missing = sorted(set(REQUIRED) - set(columns))
    unknown = sorted(set(columns) - set(REQUIRED + OPTIONAL))
    duplicate_columns = sorted(key for key, count in Counter(columns).items() if count > 1)
    schema = {
        "version": "v1", "columns": columns, "recognized_columns": [c for c in columns if c in REQUIRED + OPTIONAL],
        "missing_required_columns": missing, "unknown_columns": unknown,
        "duplicate_columns": duplicate_columns, "absent_optional_columns": [c for c in OPTIONAL if c not in columns],
    }
    if missing or unknown or duplicate_columns:
        raise AnalysisError("invalid_schema", "Use exact V1 column names; missing, unknown or repeated headers are not accepted.", schema=schema)

    errors: list[dict] = []
    error_count = 0
    missing_values = dict.fromkeys(REQUIRED + OPTIONAL, 0)
    records = []
    seen = set()
    seen_days = set()
    duplicate_count = 0
    conflicting_day_count = 0
    row_count = 0
    whitespace_count = 0
    product_labels: dict[str, tuple[str, str]] = {}

    def error(row: int, column: str | None, code: str, message: str):
        nonlocal error_count
        error_count += 1
        if len(errors) < MAX_ERRORS:
            errors.append({"row": row, "column": column, "code": code, "message": message})

    try:
        for row_number, cells in enumerate(reader, start=2):
            row_count += 1
            if row_count > MAX_ROWS:
                raise AnalysisError("too_many_rows", "CSV must contain at most 10,000 data rows.", 413)
            if len(cells) != len(columns):
                error(row_number, None, "row_width", "Row must contain exactly one value per header column.")
                continue
            values = dict(zip(columns, cells))
            normalized = {column: values.get(column, "").strip() for column in REQUIRED + OPTIONAL}
            whitespace_count += sum(values[c] != values[c].strip() for c in values)
            for column, value in normalized.items():
                if not value:
                    missing_values[column] += 1
                    if column in REQUIRED:
                        error(row_number, column, "missing_value", "Required value must not be blank.")
            before = error_count
            parsed = {}
            for column, value in normalized.items():
                if not value:
                    parsed[column] = None
                    continue
                if column == "date":
                    try:
                        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                            raise ValueError
                        parsed[column] = date.fromisoformat(value)
                    except ValueError:
                        error(row_number, column, "invalid_date", "Use a valid ISO date: YYYY-MM-DD.")
                elif column in ("units_sold", "inventory", "lead_time_days"):
                    if not re.fullmatch(r"[0-9]+", value) or len(value) > 13 or int(value) > MAX_NUMBER:
                        error(row_number, column, "invalid_integer", "Use a nonnegative whole number no greater than 1,000,000,000,000.")
                    else:
                        parsed[column] = int(value)
                elif column in ("revenue", "unit_price"):
                    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value) or len(value) > 16 or Decimal(value) > MAX_NUMBER:
                        error(row_number, column, "invalid_decimal", "Use a nonnegative decimal with at most two decimal places, no greater than 1,000,000,000,000.")
                    else:
                        parsed[column] = Decimal(value)
                else:
                    if len(value) > MAX_TEXT_LENGTH or any(ord(char) < 32 or ord(char) == 127 for char in value):
                        error(row_number, column, "invalid_text", "Use at most 200 characters without control characters.")
                    else:
                        parsed[column] = value
            if error_count != before or any(parsed.get(column) is None for column in REQUIRED):
                continue
            record = Record(**parsed)
            labels = (record.product_name, record.category)
            if record.product_id in product_labels and product_labels[record.product_id] != labels:
                error(row_number, "product_id", "conflicting_product", "A product_id must use the same product_name and category throughout the dataset.")
            product_labels[record.product_id] = labels
            if record in seen:
                duplicate_count += 1
                error(row_number, None, "duplicate_row", "Exact normalized duplicate row; resolve it in the source CSV before uploading.")
            elif (record.date, record.product_id) in seen_days:
                conflicting_day_count += 1
                error(row_number, None, "conflicting_product_date", "Only one daily observation per product is supported. Resolve conflicting product/date rows upstream.")
            seen.add(record)
            seen_days.add((record.date, record.product_id))
            records.append(record)
    except csv.Error:
        raise AnalysisError("malformed_csv", "CSV quoting or field format is malformed.", row=reader.line_num) from None
    if row_count == 0:
        raise AnalysisError("empty_csv", "CSV contains a header but no data rows.", schema=schema)
    quality = {
        "status": "invalid" if error_count else "valid",
        "missing_values": missing_values,
        "duplicate_rows": duplicate_count,
        "conflicting_product_date_rows": conflicting_day_count,
        "duplicate_policy": "reject", "required_missing_policy": "reject", "optional_missing_policy": "preserve_null",
        "whitespace_trimmed_values": whitespace_count,
        "error_count": error_count,
    }
    if error_count:
        raise AnalysisError("validation_failed", "Dataset rejected. Correct the listed issues and upload again; no session was created.", errors=errors, errors_truncated=error_count > MAX_ERRORS, row_count=row_count, schema=schema, data_quality=quality)
    warnings = []
    if any(missing_values[c] for c in OPTIONAL):
        warnings.append("Optional missing values are preserved as null; no values were inferred.")
    if whitespace_count:
        warnings.append("Leading/trailing value whitespace was trimmed; headers were not renamed.")
    quality["warnings"] = warnings
    dates = [record.date for record in records]
    profile = {
        "row_count": row_count, "product_count": len({record.product_id for record in records}),
        "category_count": len({record.category for record in records}),
        "date_range": {"start": min(dates).isoformat(), "end": max(dates).isoformat()},
        "schema": schema, "data_quality": quality,
    }
    return Dataset(tuple(records), profile, MAX_UPLOAD_BYTES + len(records) * 4096)
