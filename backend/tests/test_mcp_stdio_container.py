"""Managed stdio MCP container lifecycle."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "mcp_stdio_container.py"
_spec = importlib.util.spec_from_file_location("mcp_stdio_container", MODULE_PATH)
assert _spec and _spec.loader
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)


def _item(name: str, labels: dict[str, str] | None = None, *, image: str | None = None,
          cmd: list[str] | None = None, mounts: list | None = None) -> dict:
    return {
        "Name": f"/{name}",
        "Created": "2026-10-29T00:00:00Z",
        "Config": {
            "Labels": labels or {},
            "Image": image or mcp.POSTGRES_IMAGE,
            "Cmd": cmd or ["--access-mode=restricted"],
        },
        "Mounts": mounts or [],
    }


def test_current_process_has_stable_creation_token() -> None:
    first = mcp._process_start_token(os.getpid())
    second = mcp._process_start_token(os.getpid())
    assert first and second == first
    assert mcp._process_start_token(0) is None


def test_managed_janitor_only_removes_dead_exact_owner(monkeypatch) -> None:
    base = {
        mcp.MANAGED_LABEL: "true",
        mcp.WORKSPACE_LABEL: mcp.WORKSPACE_ID,
    }
    rows = [
        _item("stale", {**base, mcp.OWNER_PID_LABEL: "10", mcp.OWNER_START_LABEL: "old"}),
        _item("live", {**base, mcp.OWNER_PID_LABEL: "20", mcp.OWNER_START_LABEL: "same"}),
        _item("self", {**base, mcp.OWNER_PID_LABEL: "30", mcp.OWNER_START_LABEL: "gone", mcp.SESSION_LABEL: "s"}),
    ]
    removed: list[str] = []
    monkeypatch.setattr(mcp, "_container_ids", lambda *filters: ["1", "2", "3"])
    monkeypatch.setattr(mcp, "_inspect", lambda ids: rows)
    monkeypatch.setattr(mcp, "_process_start_token", lambda pid: {10: None, 20: "same", 30: None}[pid])
    monkeypatch.setattr(mcp, "_remove_container", lambda name: removed.append(name) or True)

    assert mcp.cleanup_stale_managed(exclude_session="s") == ["stale"]
    assert removed == ["stale"]


def test_legacy_cleanup_is_conservative_and_honours_keep(monkeypatch) -> None:
    rows = [
        _item("candidate"),
        _item("managed", {mcp.MANAGED_LABEL: "true"}),
        _item("mounted", mounts=[{"Source": "x"}]),
        _item("wrong-mode", cmd=["--access-mode=unrestricted"]),
    ]
    monkeypatch.setattr(mcp, "_container_ids", lambda *filters: ["1", "2", "3", "4"])
    monkeypatch.setattr(mcp, "_inspect", lambda ids: rows)
    assert mcp.cleanup_legacy(apply=False, keep=set()) == ["candidate"]
    assert mcp.cleanup_legacy(apply=False, keep={"candidate"}) == []


def test_run_uses_labels_and_environment_name_not_secret(monkeypatch) -> None:
    captured: list[str] = []
    cleaned: list[str] = []

    class DummyProcess:
        def __init__(self, command):
            captured.extend(command)
        def wait(self): return 0
        def poll(self): return 0
        def terminate(self): raise AssertionError("completed child must not be terminated")

    monkeypatch.setenv("DATABASE_URI", "postgresql://secret-value")
    monkeypatch.setattr(mcp, "_process_start_token", lambda pid: "creation-token")
    monkeypatch.setattr(mcp, "cleanup_stale_managed", lambda **kwargs: [])
    monkeypatch.setattr(mcp.subprocess, "Popen", DummyProcess)
    monkeypatch.setattr(mcp, "_cleanup_own", lambda name: cleaned.append(name))

    assert mcp.run_server("postgres") == 0
    command = " ".join(captured)
    assert "secret-value" not in command
    assert "-e DATABASE_URI" in command
    assert f"{mcp.MANAGED_LABEL}=true" in command
    assert f"{mcp.WORKSPACE_LABEL}={mcp.WORKSPACE_ID}" in command
    assert mcp.POSTGRES_IMAGE in captured
    assert "--access-mode=restricted" in captured
    assert cleaned and cleaned[0].startswith("gt-plan-postgres-mcp-")
