# Feature: visibility-isolation-go-live-hardening — Task 1 证据基线与 Go_Live_Gate 骨架
"""Task 1 / Requirements 7.1, 7.2, 7.3, 7.4.

证明三件事（不触库、纯证据/门逻辑）：

  1. append-only manifest 写入 + precheck 在 **本 spec 自己的** evidence 目录上工作
     （参数化 spec_dir/manifest_path，不改写既有 run，不污染 Parent_Spec manifest）；
  2. 本 spec 基线 run 自身 artifact 的 precheck 干净（相对路径安全 + SHA-256/size 一致）；
  3. H7 Go_Live_Gate 在 6 个 Go_Live_Item 均 built-not-live 时 **诚实 fail-closed 阻断**
     （复用 completion_guard 的 latest-run-per-task + SHA-256/size 重算 + 路径安全）。

绝不假绿：门在基线阶段必须阻断，本测试断言的正是"阻断"这一诚实结论。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.security import evidence_manifest as em
from app.security import go_live_evidence as gle
from app.security import go_live_gate as glg

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BASELINE_REL = "evidence/artifacts/task1/go_live_baseline.json"


# ---------------------------------------------------------------------------
# 1. append-only + precheck on a throwaway (tmp) manifest — parameterized paths
# ---------------------------------------------------------------------------
def _seed_tmp_spec(tmp_path: Path) -> tuple[Path, Path]:
    """Build a minimal spec dir (manifest + one artifact) under tmp_path."""
    evidence = tmp_path / "evidence"
    (evidence / "artifacts" / "t").mkdir(parents=True, exist_ok=True)
    (evidence / "artifacts" / "t" / "a.txt").write_text("alpha", encoding="utf-8")
    (evidence / "artifacts" / "t" / "b.txt").write_text("beta-beta", encoding="utf-8")
    manifest = evidence / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "spec": gle.SPEC_NAME,
                "schema_version": gle.SCHEMA_VERSION,
                "created_at": "2026-01-01T00:00:00+00:00",
                "runs": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path, manifest


def test_append_is_append_only_and_precheck_clean(tmp_path: Path):
    spec_dir, manifest = _seed_tmp_spec(tmp_path)

    r1 = em.append_run(
        task_id="1",
        status="passed",
        artifacts=["evidence/artifacts/t/a.txt"],
        criterion_ids=["7.1"],
        manifest_path=manifest,
        spec_dir=spec_dir,
    )
    assert r1["seq"] == 1
    r1_frozen = json.loads(manifest.read_text(encoding="utf-8"))["runs"][0]

    r2 = em.append_run(
        task_id="1",
        status="passed",
        artifacts=["evidence/artifacts/t/b.txt"],
        criterion_ids=["7.2"],
        manifest_path=manifest,
        spec_dir=spec_dir,
    )
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 2, "append must grow runs, never replace"
    assert r2["seq"] == 2
    # append-only: the first run is byte-for-byte unchanged after the second append.
    assert data["runs"][0] == r1_frozen

    # precheck (path safety + SHA-256/size recompute) is clean against the real schema.
    problems = em.precheck(manifest, gle.SCHEMA_PATH, spec_dir)
    assert problems == [], f"tmp precheck should be clean, got: {problems}"


def test_precheck_and_writer_reject_unsafe_paths(tmp_path: Path):
    spec_dir, manifest = _seed_tmp_spec(tmp_path)
    assert em.is_unsafe_rel_path("../evil.txt") is True
    assert em.is_unsafe_rel_path("C:/abs/evil.txt") is True
    assert em.is_unsafe_rel_path("/abs/evil.txt") is True
    assert em.is_unsafe_rel_path("evidence/artifacts/t/a.txt") is False

    with pytest.raises(ValueError):
        em.append_run(
            task_id="1",
            status="passed",
            artifacts=[{"path": "../escape.txt"}],
            manifest_path=manifest,
            spec_dir=spec_dir,
        )


# ---------------------------------------------------------------------------
# 2. spec-scoped wrapper targets THIS spec, not the parent
# ---------------------------------------------------------------------------
def test_wrapper_is_scoped_to_this_spec_not_parent():
    assert gle.SPEC_NAME == "visibility-isolation-go-live-hardening"
    assert gle.MANIFEST_PATH.parts[-3] == "visibility-isolation-go-live-hardening"
    # Independent of the parent manifest path.
    assert gle.MANIFEST_PATH != em.MANIFEST_PATH
    assert "procedure-delegation-visibility-isolation" not in str(gle.MANIFEST_PATH)
    assert gle.MANIFEST_PATH.exists(), "this spec's manifest must be initialized"
    assert gle.SCHEMA_PATH.exists(), "this spec's schema must be initialized"


def test_real_manifest_precheck_returns_empty():
    """本 spec 自己的 manifest precheck() 返回 [] （其自身 run 的 artifact 全部一致）。"""
    problems = gle.precheck()
    assert problems == [], f"this spec's precheck must be clean, got: {problems}"


# ---------------------------------------------------------------------------
# 3. Go_Live_Gate honestly blocks at baseline (built-not-live)
# ---------------------------------------------------------------------------
def test_go_live_gate_blocks_while_items_built_not_live():
    res = glg.evaluate()
    assert res.live is False, "gate must NOT be live at baseline"
    assert res.blocked is True, "gate must block the go-live claim at baseline"
    assert res.report["verdict"] == "blocked"
    assert res.report["go_live_items_total"] == 6
    assert res.report["go_live_items_live"] == 0

    # every one of the 6 items is built-not-live (Tasks 2..7 have no accepted run).
    states = {row["id"]: row["state"] for row in res.report["go_live_items"]}
    assert set(states) == {"GLI-1", "GLI-2", "GLI-3", "GLI-4", "GLI-5", "GLI-6"}
    assert all(v == "built-not-live" for v in states.values()), states

    # at least the 6 built-not-live problems are reported (7.8), fail-closed.
    assert sum(1 for p in res.problems if "[7.8]" in p) == 6


def test_gate_reuses_artifact_integrity_recompute():
    """门复用 completion_guard 的 SHA-256/size 重算 + 路径安全（latest-run artifact 干净）。"""
    res = glg.evaluate()
    assert res.report["latest_artifacts_verified"]["clean"] is True


# ---------------------------------------------------------------------------
# baseline artifact declares the 6 items built-not-live with BUILT-vs-LIVE distinction
# ---------------------------------------------------------------------------
def test_baseline_artifact_declares_built_not_live():
    path = gle.SPEC_DIR / _BASELINE_REL
    assert path.exists(), "baseline artifact must exist"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["spec"] == "visibility-isolation-go-live-hardening"
    assert "built" in data["distinction"] and "live_accepted" in data["distinction"]
    items = data["go_live_items"]
    assert len(items) == 6
    assert all(it["status"] == "built-not-live" for it in items)
    # cites parent evidence as proof of BUILT (not LIVE).
    assert "procedure-delegation-visibility-isolation" in data["parent_spec"]["name"]
