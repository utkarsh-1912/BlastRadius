"""
A small SQLite-backed audit trail for past review runs.

This is intentionally NOT the source of truth for an in-progress run — the
live `ReviewRun` object in `main.py`'s in-memory `_RUNS` dict is, since only
that object holds the live `BlastRadiusResult`/`AttachedPolicy` references
`commit_and_verify()` needs. This store exists so that:
  - past reviews survive an API server restart, for audit/history purposes
  - a "History" view can list what was reviewed, proposed, and decided,
    without needing every run to still be live in memory

A run persisted here can be viewed but not re-approved after a restart —
approving requires the live in-memory object. This is a deliberate
limitation (see README), not an oversight: re-approving a stale snapshot
without re-running the replay against current IAM/CloudTrail state would
defeat the entire point of Blast Radius.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "blast_radius_history.sqlite3")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY,
            request_text TEXT NOT NULL,
            status TEXT NOT NULL,
            role_name TEXT,
            safe_count INTEGER NOT NULL DEFAULT 0,
            unsafe_count INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            run_json TEXT NOT NULL
        )
        """
    )
    return conn


def save_run(run_dict: dict) -> None:
    """Upsert a run's full to_dict() snapshot. Called after every state
    transition (created, approved, rejected, verified, failed) so history
    always reflects the latest known state."""
    conn = _connect()
    try:
        now = time.time()
        existing = conn.execute("SELECT created_at FROM reviews WHERE id = ?", (run_dict["id"],)).fetchone()
        created_at = existing[0] if existing else now
        conn.execute(
            """
            INSERT INTO reviews (id, request_text, status, role_name, safe_count, unsafe_count, created_at, updated_at, run_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status, safe_count=excluded.safe_count, unsafe_count=excluded.unsafe_count,
                updated_at=excluded.updated_at, run_json=excluded.run_json
            """,
            (
                run_dict["id"],
                run_dict["request_text"],
                run_dict["status"],
                (run_dict.get("understood") or {}).get("role_name") or (run_dict.get("understood") or {}).get("role_prefix"),
                len(run_dict.get("safe_changes", [])),
                len(run_dict.get("unsafe_candidates", [])),
                created_at,
                now,
                json.dumps(run_dict),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_runs(limit: int = 50) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, request_text, status, role_name, safe_count, unsafe_count, created_at, updated_at "
            "FROM reviews ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "request_text": r[1],
                "status": r[2],
                "role_name": r[3],
                "safe_count": r[4],
                "unsafe_count": r[5],
                "created_at": r[6],
                "updated_at": r[7],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_run(run_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute("SELECT run_json FROM reviews WHERE id = ?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()
