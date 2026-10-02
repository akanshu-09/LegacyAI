"""Opaque IDs, immutable records, absolute expiry, and bounded reservations."""

import copy
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Callable

from app.ingestion.validation import AnalysisError, Dataset

SESSION_TTL_SECONDS = 1800
MAX_SESSIONS = 20
MAX_RESERVED_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Session:
    dataset: Dataset
    source: str
    expires_at: float
    deadline: float


class SessionStore:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], float] = time.time, ttl: int = SESSION_TTL_SECONDS,
                 max_sessions: int = MAX_SESSIONS, max_reserved_bytes: int = MAX_RESERVED_BYTES):
        self.clock = clock
        self.wall_clock = wall_clock
        self.ttl = ttl
        self.max_sessions = max_sessions
        self.max_reserved_bytes = max_reserved_bytes
        self._sessions: dict[str, Session] = {}
        self._lock = RLock()

    def cleanup(self) -> int:
        with self._lock:
            expired = [key for key, session in self._sessions.items() if session.deadline <= self.clock()]
            for key in expired:
                del self._sessions[key]
            return len(expired)

    def create(self, dataset: Dataset, source: str) -> dict:
        with self._lock:
            self.cleanup()
            reserved = sum(s.dataset.memory_reservation for s in self._sessions.values())
            if len(self._sessions) >= self.max_sessions or reserved + dataset.memory_reservation > self.max_reserved_bytes:
                raise AnalysisError("session_capacity", "Temporary session capacity is full. Release an existing session or try after expiry.", 503)
            key = secrets.token_urlsafe(32)
            # Copy profile so no caller can mutate another session through shared dictionaries.
            stored = Dataset(dataset.records, copy.deepcopy(dataset.profile), dataset.memory_reservation)
            self._sessions[key] = Session(stored, source, self.wall_clock() + self.ttl, self.clock() + self.ttl)
            return self.describe(key)

    def get(self, key: str) -> Session:
        with self._lock:
            self.cleanup()
            session = self._sessions.get(key)
            if session is None:
                raise AnalysisError("analysis_unavailable", "Analysis session is unknown or expired. Upload again or load the demo.", 404)
            return session

    def describe(self, key: str) -> dict:
        with self._lock:
            session = self.get(key)
            return {"analysis_id": key, "expires_at": datetime.fromtimestamp(session.expires_at, timezone.utc).isoformat(),
                    "source": session.source, "profile": copy.deepcopy(session.dataset.profile)}

    def delete(self, key: str):
        with self._lock:
            self.get(key)
            del self._sessions[key]

    def clear(self):
        with self._lock:
            self._sessions.clear()
