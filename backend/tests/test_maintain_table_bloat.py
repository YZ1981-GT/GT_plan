"""Safety contract for ``scripts/ops/maintain_table_bloat.py``."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "backend" / "scripts" / "ops" / "maintain_table_bloat.py"
_spec = importlib.util.spec_from_file_location("maintain_table_bloat", MODULE_PATH)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _snapshot(*, rows: int = 907, digest: str = "digest", logical_bytes: int = 10_000) -> dict:
    return {
        "captured_at": "2026-10-29T00:00:00+00:00",
        "logical": {"exact_rows": rows, "row_digest": digest, "logical_bytes": logical_bytes},
        "sizes": {"heap_bytes": 300, "index_bytes": 200, "total_bytes": 510, "toast_bytes": 10},
        "columns": [{"ordinal_position": 1, "column_name": "id"}],
        "constraints": [{"conname": "checklist_responses_pkey", "contype": "p", "convalidated": True,
                         "definition": "PRIMARY KEY (id)"}],
        "indexes": [{"name": "checklist_responses_pkey", "indisvalid": True, "indisready": True,
                     "indisunique": True, "size_bytes": 200,
                     "definition": "CREATE UNIQUE INDEX checklist_responses_pkey ON public.checklist_responses (id)"}],
    }


def _safety(*, safe: bool = True) -> dict:
    return {"captured_at": "2026-10-29T00:00:00+00:00", "safe": safe,
            "long_transactions": [] if safe else [{"pid": 99}], "prepared_transactions": [], "target_locks": []}


def _args(tmp_path: Path, *, apply: bool = False) -> argparse.Namespace:
    return SimpleNamespace(table=mod.TARGET, apply=apply, confirm=mod.CONFIRMATION if apply else "",
                           backup_root=tmp_path, docker_container="audit-postgres", max_transaction_age=60,
                           lock_timeout_ms=5000, statement_timeout_seconds=1800, analyze_ledgers=True)


def test_cli_is_dry_run_by_default_and_apply_needs_exact_confirmation() -> None:
    args = mod._parser().parse_args([])
    assert args.table == "checklist_responses" and args.apply is False
    with pytest.raises(SystemExit, match="VACUUM_FULL_CHECKLIST_RESPONSES"):
        mod._validate_args(mod._parser().parse_args(["--apply", "--confirm", "wrong"]))
    ok = mod._parser().parse_args(["--apply", "--confirm", mod.CONFIRMATION])
    mod._validate_args(ok)


def test_pg_dump_command_is_custom_table_scoped_and_never_exposes_password() -> None:
    url = make_url("postgresql+asyncpg://alice:top-secret@db.example:5544/audit_platform")
    command, env = mod._local_dump_command(url)
    joined = " ".join(command)
    assert command[0] == "pg_dump"
    assert "-Fc" in command
    assert command[command.index("-t") + 1] == "public.checklist_responses"
    assert "top-secret" not in joined
    assert env["PGPASSWORD"] == "top-secret"
    recovery = mod._recovery_guidance(url, Path("D:/safe/checklist.dump"), "audit-postgres")
    assert "top-secret" not in json.dumps(recovery)
    assert "--single-transaction" in recovery["local"]


def test_logical_and_catalog_verification_ignores_only_physical_index_size() -> None:
    before = _snapshot()
    after = json.loads(json.dumps(before))
    after["indexes"][0]["size_bytes"] = 1
    after["sizes"].update({"heap_bytes": 1, "index_bytes": 1, "total_bytes": 3})
    assert mod._same_logical(before, after) == (True, [])

    after["logical"]["row_digest"] = "changed"
    ok, failures = mod._same_logical(before, after)
    assert ok is False and "logical.row_digest changed" in failures


def test_dry_run_never_creates_backup_or_calls_vacuum(tmp_path, monkeypatch) -> None:
    async def state(_url, _age):
        return _snapshot(), _safety(), {"system_identifier": "1", "database_name": "audit_platform",
                                        "database_user": "postgres"}

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("dry-run must not vacuum")

    monkeypatch.setattr(mod, "_read_state", state)
    monkeypatch.setattr(mod, "_vacuum", forbidden)
    result = __import__("asyncio").run(mod.run(_args(tmp_path)))
    assert result == 0 and list(tmp_path.iterdir()) == []


def test_apply_backs_up_and_verifies_before_vacuum(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    states = iter([
        (_snapshot(), _safety(), {"system_identifier": "1", "database_name": "audit_platform",
                                  "database_user": "postgres"}),
        (_snapshot(), _safety(), {"system_identifier": "1", "database_name": "audit_platform",
                                  "database_user": "postgres"}),
        (_snapshot(), _safety(), {"system_identifier": "1", "database_name": "audit_platform",
                                  "database_user": "postgres"}),
    ])

    async def state(_url, _age):
        return next(states)

    def dump(_url, output, _identity, _container):
        calls.append("dump")
        output.write_bytes(b"custom-dump")
        return {"path": str(output), "size_bytes": 11, "sha256": "x", "mode": "test"}

    def verify(_path, _container):
        calls.append("verify")
        return {"pg_restore_list_ok": True, "has_table": True, "has_table_data": True}

    async def vacuum(_url, _lock, _statement, analyze):
        calls.append("vacuum")
        assert calls == ["dump", "verify", "vacuum"]
        return list(mod.LEDGER_TABLES) if analyze else []

    monkeypatch.setattr(mod, "_read_state", state)
    monkeypatch.setattr(mod, "_dump_table", dump)
    monkeypatch.setattr(mod, "_verify_dump", verify)
    monkeypatch.setattr(mod, "_vacuum", vacuum)
    result = __import__("asyncio").run(mod.run(_args(tmp_path, apply=True)))
    assert result == 0
    manifests = list(tmp_path.glob("checklist_responses_*/manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "verified" and manifest["verification"] == {"ok": True, "failures": []}
    assert manifest["analyzed_ledgers"] == list(mod.LEDGER_TABLES)


def test_apply_fails_closed_on_long_transaction_before_backup(tmp_path, monkeypatch) -> None:
    async def state(_url, _age):
        return _snapshot(), _safety(safe=False), {"system_identifier": "1", "database_name": "audit_platform",
                                                   "database_user": "postgres"}

    monkeypatch.setattr(mod, "_read_state", state)
    result = __import__("asyncio").run(mod.run(_args(tmp_path, apply=True)))
    assert result == 2 and list(tmp_path.iterdir()) == []
