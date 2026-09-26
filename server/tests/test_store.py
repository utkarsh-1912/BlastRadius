"""Tests for the SQLite-backed audit history store (agent/store.py)."""
from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """Point the store at a throwaway DB file so tests never touch the real
    history file or leak state between tests."""
    import agent.store as store_module

    monkeypatch.setattr(store_module, "DB_PATH", str(tmp_path / "test_history.sqlite3"))
    yield store_module


def test_save_and_list_run(isolated_store):
    run_dict = {
        "id": "run-1",
        "request_text": "Review IAM access for the data-pipeline-role role.",
        "status": "awaiting_approval",
        "understood": {"role_name": "data-pipeline-role"},
        "safe_changes": [{"action": "s3:DeleteObject"}],
        "unsafe_candidates": [],
    }
    isolated_store.save_run(run_dict)

    runs = isolated_store.list_runs()
    assert len(runs) == 1
    assert runs[0]["id"] == "run-1"
    assert runs[0]["role_name"] == "data-pipeline-role"
    assert runs[0]["safe_count"] == 1
    assert runs[0]["unsafe_count"] == 0


def test_get_run_returns_full_snapshot(isolated_store):
    run_dict = {"id": "run-2", "request_text": "x", "status": "verified", "understood": None, "safe_changes": [], "unsafe_candidates": []}
    isolated_store.save_run(run_dict)
    fetched = isolated_store.get_run("run-2")
    assert fetched == run_dict


def test_get_run_missing_returns_none(isolated_store):
    assert isolated_store.get_run("does-not-exist") is None


def test_save_run_upserts_by_id(isolated_store):
    run_dict = {"id": "run-3", "request_text": "x", "status": "awaiting_approval", "understood": None, "safe_changes": [], "unsafe_candidates": []}
    isolated_store.save_run(run_dict)
    run_dict["status"] = "verified"
    isolated_store.save_run(run_dict)

    runs = isolated_store.list_runs()
    assert len(runs) == 1  # not duplicated
    assert runs[0]["status"] == "verified"


def test_list_runs_orders_most_recently_updated_first(isolated_store):
    import time

    isolated_store.save_run({"id": "a", "request_text": "x", "status": "verified", "understood": None, "safe_changes": [], "unsafe_candidates": []})
    time.sleep(0.01)
    isolated_store.save_run({"id": "b", "request_text": "x", "status": "verified", "understood": None, "safe_changes": [], "unsafe_candidates": []})

    runs = isolated_store.list_runs()
    assert [r["id"] for r in runs] == ["b", "a"]
