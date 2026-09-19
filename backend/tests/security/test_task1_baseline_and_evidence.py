"""Task 1 self-tests: entry-coverage ledger, baseline contracts, evidence writer.

These are pure (no DB, no full-app import) so they run fast and are safe under
the SQLite conftest. They validate:
  * the committed ledger JSON is valid and honours baseline invariants
    (every wp-bound entry is `unmigrated`, unique route+method, V112 head);
  * the scanner classification helpers behave correctly and produce valid JSON
    from a synthetic app;
  * the evidence writer is append-only, recomputes SHA-256/size and rejects
    `..` / absolute artifact paths.
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from app.security import baseline_contracts as bc
from app.security import entry_coverage_scanner as scanner
from app.security import evidence_manifest as ev


# ---------------------------------------------------------------------------
# Committed ledger
# ---------------------------------------------------------------------------
def _load_committed_ledger() -> dict:
    return json.loads(scanner.LEDGER_PATH.read_text(encoding="utf-8"))


def test_committed_ledger_is_valid_json_and_honours_baseline_invariants():
    ledger = _load_committed_ledger()
    assert ledger["spec"] == "procedure-delegation-visibility-isolation"
    assert ledger["migration_head"] == "V112"
    problems = scanner.validate_ledger(ledger)
    assert problems == [], f"ledger invariants violated: {problems}"


def test_committed_ledger_has_no_duplicate_route_method():
    ledger = _load_committed_ledger()
    seen: set[tuple[str, str]] = set()
    for e in ledger["entries"]:
        if e["kind"] == "http":
            key = (e["route"], e["method"])
            assert key not in seen, f"duplicate route+method in ledger: {key}"
            seen.add(key)


def test_committed_ledger_wp_bound_entries_unmigrated_or_have_test_ids():
    """Migration-aware anti-fake-pass invariant.

    Each wp-bound entry is either still at baseline (gate AND matrix both
    ``unmigrated``) or fully migrated (both non-``unmigrated`` AND carrying
    non-empty stable ``test_ids``). Tasks 9/10/11 migrate their own entries
    incrementally; a migrated entry without test evidence is a fake-pass.
    """
    ledger = _load_committed_ledger()
    wp_bound = [e for e in ledger["entries"] if e.get("wp_bound")]
    assert wp_bound, "expected some wp-bound entries in the baseline"
    for e in wp_bound:
        gate_base = e["gate"] == "unmigrated"
        matrix_base = e["matrix"] == "unmigrated"
        if gate_base or matrix_base:
            assert gate_base and matrix_base, (
                f"half-migrated: {e['entrypoint']} gate={e['gate']} matrix={e['matrix']}"
            )
        else:
            assert e.get("test_ids"), (
                f"fake-pass (migrated, no test_ids): {e['entrypoint']}"
            )


def test_committed_ledger_records_key_wp_families_and_workers():
    ledger = _load_committed_ledger()
    families = {e["family"] for e in ledger["entries"] if e.get("wp_bound")}
    # Render / AI / attachment / OnlyOffice-WOPI current gaps must be present.
    for fam in ("render_config", "ai", "attachment", "onlyoffice_wopi", "checklist", "procedure_task"):
        assert fam in families, f"missing wp-bound family {fam} in baseline ledger"
    # Non-HTTP executors must be inventoried, incl. the procedure dispatcher.
    workers = [e for e in ledger["entries"] if e["kind"] in ("worker", "retry", "dead_letter")]
    assert workers, "expected worker/retry/dead-letter entries"
    disp = [e for e in workers if "procedure_dispatcher_worker" in e["entrypoint"]]
    # Baseline (Task 1) recorded the dispatcher as ``unmigrated``. Task 16
    # finalises the ledger and resolves every wp-bound entry: the dispatcher is
    # classified ``native_authz`` (delivers task-assignment notification signals,
    # no 底稿正文; events enqueued only by authorized delegation transactions).
    # The invariant the baseline cares about is that the dispatcher stays
    # inventoried + wp_bound with a resolved (non-empty) classification.
    assert disp and disp[0]["wp_bound"]
    assert disp[0]["gate"] in ("unmigrated", "native_authz", "gated")


# ---------------------------------------------------------------------------
# Classifier helpers + synthetic-app scan producing valid JSON
# ---------------------------------------------------------------------------
def test_is_wp_bound_signals():
    assert scanner.is_wp_bound("/api/workpapers/{wp_id}/render-config", ["wp_id"], "m")
    assert scanner.is_wp_bound("/wopi/files/{file_id}", ["file_id"], "m")
    assert scanner.is_wp_bound("/api/attachments/{attachment_id}/download", ["attachment_id"], "m")
    assert scanner.is_wp_bound("/api/projects/{project_id}/bulk-tab/export-data", ["project_id"], "m")
    # project-level ledger import without a wp signal is NOT wp-bound
    assert not scanner.is_wp_bound("/api/projects/{project_id}/import", ["project_id"], "m")
    assert not scanner.is_wp_bound("/api/version", [], "app.main")


def test_classify_family_and_action():
    assert scanner.classify_family("/api/workpapers/{wp_id}/render-config", "GET", ["wp_id"], True) == "render_config"
    assert scanner.classify_family("/api/workpapers/{wp_id}/ai/generate-text", "POST", ["wp_id"], True) == "ai"
    assert scanner.classify_family("/api/workpapers/{wp_id}/sheets/{s}/onlyoffice-callback", "POST", ["wp_id", "s"], True) == "callback"
    assert scanner.classify_family("/api/projects/{project_id}/import", "POST", ["project_id"], False) == "non_wp_bound"
    assert scanner.classify_action("GET", "render_config") == "read"
    assert scanner.classify_action("POST", "export") == "export"


def _fake_route(path: str, methods, module: str, name: str):
    def _ep():
        return None

    _ep.__module__ = module
    _ep.__qualname__ = name
    _ep.__name__ = name
    return types.SimpleNamespace(path=path, methods=set(methods), endpoint=_ep)


def test_scanner_builds_valid_json_from_synthetic_app():
    fake_app = types.SimpleNamespace(
        routes=[
            _fake_route("/api/workpapers/{wp_id}/render-config", ["GET"], "app.routers.wp_render_config", "get_render_config"),
            _fake_route("/api/projects/{project_id}/import", ["POST"], "app.routers.data_import", "do_import"),
            _fake_route("/api/workpapers/{wp_id}/render-config", ["GET"], "app.routers.dup", "dup"),  # duplicate
        ]
    )
    ledger = scanner.build_ledger(app=fake_app)
    # Round-trips through JSON cleanly.
    dumped = json.dumps(ledger, ensure_ascii=False)
    assert json.loads(dumped)["spec"] == "procedure-delegation-visibility-isolation"
    # Unique route+method despite the duplicate registration.
    http = [e for e in ledger["entries"] if e["kind"] == "http"]
    keys = [(e["route"], e["method"]) for e in http]
    assert len(keys) == len(set(keys))
    dup = [e for e in http if e["route"].endswith("render-config")][0]
    assert dup["wp_bound"] and dup["gate"] == "unmigrated"
    assert dup.get("duplicate_registration") is True
    assert scanner.validate_ledger(ledger) == []


# ---------------------------------------------------------------------------
# Baseline contracts
# ---------------------------------------------------------------------------
def test_baseline_working_paper_is_singular():
    problems = bc.verify_orm_table_names()
    assert problems == [], f"ORM table-name baseline violated: {problems}"


def test_baseline_verify_ok_and_head_v112():
    assert bc.MIGRATION_HEAD == "V112"
    assert bc.verify_baseline() == []
    snap = bc.get_baseline()
    assert snap["tables"]["working_paper"] == "singular"
    assert "working_papers" in snap["forbidden_table_names"]
    # Known gaps recorded honestly (never marked implemented).
    assert snap["known_gaps"]["wp_bound_gate"] == "unmigrated"
    assert snap["known_gaps"]["action_matrix"] == "unmigrated"
    assert snap["traceback_temp_log"] == "_render_config_500.log"


# ---------------------------------------------------------------------------
# Evidence manifest writer: append-only + hash/size + path safety
# ---------------------------------------------------------------------------
def test_is_unsafe_rel_path():
    assert ev.is_unsafe_rel_path("../secret.txt")
    assert ev.is_unsafe_rel_path("evidence/../../etc/passwd")
    assert ev.is_unsafe_rel_path("/abs/path")
    assert ev.is_unsafe_rel_path("C:/abs/win")
    assert not ev.is_unsafe_rel_path("evidence/artifacts/task1/x.json")


def test_append_only_retains_failed_runs(tmp_path: Path):
    spec_dir = tmp_path
    (spec_dir / "evidence" / "artifacts").mkdir(parents=True)
    art = spec_dir / "evidence" / "artifacts" / "a.json"
    art.write_text('{"k":1}', encoding="utf-8")
    manifest = spec_dir / "evidence" / "manifest.json"

    r1 = ev.append_run(
        task_id="1", status="failed",
        artifacts=["evidence/artifacts/a.json"],
        manifest_path=manifest, spec_dir=spec_dir,
    )
    r2 = ev.append_run(
        task_id="1", status="passed",
        artifacts=["evidence/artifacts/a.json"],
        manifest_path=manifest, spec_dir=spec_dir,
    )
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 2
    # First (failed) run retained and unchanged.
    assert data["runs"][0]["run_id"] == r1["run_id"]
    assert data["runs"][0]["status"] == "failed"
    assert data["runs"][1]["run_id"] == r2["run_id"]
    assert data["runs"][1]["status"] == "passed"


def test_sha256_size_recompute_and_precheck(tmp_path: Path):
    spec_dir = tmp_path
    (spec_dir / "evidence" / "artifacts").mkdir(parents=True)
    art = spec_dir / "evidence" / "artifacts" / "a.json"
    payload = b'{"hello":"world"}'
    art.write_bytes(payload)
    manifest = spec_dir / "evidence" / "manifest.json"

    run = ev.append_run(
        task_id="1", status="passed",
        artifacts=["evidence/artifacts/a.json"],
        manifest_path=manifest, spec_dir=spec_dir,
    )
    import hashlib
    assert run["artifacts"][0]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert run["artifacts"][0]["size"] == len(payload)

    # Precheck passes when nothing changed.
    # (schema not present in tmp — precheck reports schema missing; use spec schema.)
    assert ev.precheck(manifest_path=manifest, schema_path=ev.SCHEMA_PATH, spec_dir=spec_dir) == []

    # Tamper the artifact -> precheck must detect SHA/size mismatch.
    art.write_bytes(payload + b"tampered")
    problems = ev.precheck(manifest_path=manifest, schema_path=ev.SCHEMA_PATH, spec_dir=spec_dir)
    assert any("SHA-256 mismatch" in p or "size mismatch" in p for p in problems)


def test_append_run_rejects_dotdot_and_absolute(tmp_path: Path):
    spec_dir = tmp_path
    (spec_dir / "evidence").mkdir(parents=True)
    manifest = spec_dir / "evidence" / "manifest.json"
    with pytest.raises(ValueError):
        ev.append_run(
            task_id="1", status="passed",
            artifacts=["../escape.json"],
            manifest_path=manifest, spec_dir=spec_dir,
        )
    with pytest.raises(ValueError):
        ev.append_run(
            task_id="1", status="passed",
            artifacts=[{"path": "/abs/escape.json"}],
            manifest_path=manifest, spec_dir=spec_dir,
        )


def test_append_run_rejects_invalid_status(tmp_path: Path):
    spec_dir = tmp_path
    (spec_dir / "evidence").mkdir(parents=True)
    with pytest.raises(ValueError):
        ev.append_run(
            task_id="1", status="bogus",
            manifest_path=spec_dir / "evidence" / "manifest.json",
            spec_dir=spec_dir,
        )


def test_committed_manifest_and_schema_precheck_ok():
    """The committed evidence manifest + schema must pass precheck."""
    assert ev.SCHEMA_PATH.exists(), "evidence schema must exist"
    assert ev.MANIFEST_PATH.exists(), "evidence manifest must exist"
    problems = ev.precheck()
    assert problems == [], f"committed evidence precheck failed: {problems}"
