"""
In-memory session store for uploaded datasets.

Deployment context: both Streamlit and FastAPI run on a cloud server, so
uploaded data does travel from the user's browser to the server over HTTPS.

Server-side privacy guarantees:
  - Raw data (the DataFrame) is held ONLY in this in-memory store — it is
    never written to disk or persisted to Supabase.
  - Each session is fully isolated: no user can access another user's data.
  - Data is deleted automatically by whichever comes first:
      * explicit session close  (clear_session — called on tab close / logout)
      * TTL expiry              (background reaper, default 30 min inactivity)
      * process exit            (atexit handler wipes the entire store)
  - Supabase receives only lightweight metadata (schema, column profiles,
    prompt history) — zero raw data rows.

Deployment responsibility:
  - Serve the app over HTTPS so data is encrypted in transit.
  - Do not configure any request logging that captures request bodies
    (which would contain the uploaded file bytes).
"""
from __future__ import annotations

import atexit
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

SESSION_TTL_SECONDS = 1800  # evict after 30 minutes of inactivity
_REAPER_INTERVAL   = 60     # reaper runs every 60 s


@dataclass
class _SessionEntry:
    df:            pd.DataFrame
    metadata:      dict[str, Any]   # ValidationReport + DatasetProfile dicts
    dataset_id:    str | None       # Supabase dataset_id once persisted
    created_at:    float = field(default_factory=time.monotonic)
    last_accessed: float = field(default_factory=time.monotonic)


class SessionStore:
    """Thread-safe, in-memory store for user DataFrames."""

    def __init__(self, ttl: int = SESSION_TTL_SECONDS) -> None:
        self._store: dict[str, _SessionEntry] = {}
        self._lock  = threading.Lock()
        self._ttl   = ttl
        # Daemon thread so it never blocks process exit
        self._reaper = threading.Thread(target=self._reap_loop, daemon=True, name="session-reaper")
        self._reaper.start()
        atexit.register(self._on_exit)

    # ── Public API ─────────────────────────────────────────────────────────────

    def create(
        self,
        df: pd.DataFrame,
        metadata: dict[str, Any],
        dataset_id: str | None = None,
    ) -> str:
        """
        Store a DataFrame and return a new session_id.
        Call this immediately after ingestion so the data never sits anywhere else.
        """
        session_id = str(uuid.uuid4())
        with self._lock:
            self._store[session_id] = _SessionEntry(
                df=df,
                metadata=metadata,
                dataset_id=dataset_id,
            )
        return session_id

    def get(self, session_id: str) -> tuple[pd.DataFrame, dict[str, Any]] | None:
        """
        Retrieve (DataFrame, metadata) and refresh the TTL.
        Returns None if the session has expired or does not exist.
        """
        with self._lock:
            entry = self._store.get(session_id)
            if entry is None:
                return None
            entry.last_accessed = time.monotonic()
            return entry.df.copy(), entry.metadata   # copy so callers can't mutate the store

    def update_dataset_id(self, session_id: str, dataset_id: str) -> None:
        """Record the Supabase dataset_id once the metadata row has been persisted."""
        with self._lock:
            entry = self._store.get(session_id)
            if entry:
                entry.dataset_id = dataset_id

    def get_dataset_id(self, session_id: str) -> str | None:
        with self._lock:
            entry = self._store.get(session_id)
            return entry.dataset_id if entry else None

    def clear_session(self, session_id: str) -> None:
        """Explicitly delete a session's data — call this on user logout / tab close."""
        with self._lock:
            self._store.pop(session_id, None)

    def active_count(self) -> int:
        with self._lock:
            return len(self._store)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _reap_loop(self) -> None:
        """Background reaper: evict sessions idle longer than TTL."""
        while True:
            time.sleep(_REAPER_INTERVAL)
            self._evict_expired()

    def _evict_expired(self) -> None:
        cutoff = time.monotonic() - self._ttl
        with self._lock:
            expired = [sid for sid, e in self._store.items() if e.last_accessed < cutoff]
            for sid in expired:
                del self._store[sid]

    def _on_exit(self) -> None:
        """atexit handler — wipe everything when the process shuts down."""
        with self._lock:
            self._store.clear()


# Module-level singleton shared by the FastAPI app and Streamlit frontend
session_store = SessionStore()
