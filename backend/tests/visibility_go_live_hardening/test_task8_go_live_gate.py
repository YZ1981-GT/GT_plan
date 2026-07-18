# Feature: visibility-isolation-go-live-hardening — Task 8 执行 Go_Live_Gate 并关闭规格
"""Task 8 / Requirements 7.5, 7.6, 7.7, 7.8, 7.9, 7.10.

终局门（H7 Go_Live_Gate）在 Task 1–7 全部 latest-run passed 后的**最终**评估：

  * 聚合 Task 1–7 的 latest-run-per-task；逐 run 重算 artifact SHA-256/size；
    拒绝 `..`/绝对路径/缺 artifact（复用 completion_guard 机制）；
  * 6 个 Go_Live_Item(GLI-1..6 → Task 2..7) 均有最新 passed run 且非 smoke 冒充
    → 全部 LIVE/ACCEPTED；
  * 两条残留环境 GAP(GLI-4 6000 诚实外推 / GLI-6 PR 未实际开启)被**透明 surface**
    在 report.residual_gaps 中（不掩盖、不伪造），且各自的 evidence marker 在其
    latest-run notes 中被检出（registry 不与证据漂移）；
  * spec 自身 precheck() 返回 []（含 Task 8 run 追加后仍干净）。

绝不假绿：本测试断言的是真实 LIVE 结论；若任一 item 最新 run 非 passed、或残留 GAP
registry 与证据漂移、或 artifact 完整性不符，门必阻断，本测试即失败。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.security import go_live_evidence as gle
from app.security import go_live_gate as glg


# ---------------------------------------------------------------------------
# 1. 终局门在 6 项均 live-accepted 时判定 LIVE（7.5/7.7）
# ---------------------------------------------------------------------------
def test_gate_is_live_all_six_items_accepted():
    res = glg.evaluate()
    assert res.live is True, f"gate must be LIVE; problems={res.problems}"
    assert res.blocked is False
    assert res.report["verdict"] == "live"
    assert res.report["go_live_items_total"] == 6
    assert res.report["go_live_items_live"] == 6

    states = {row["id"]: row["state"] for row in res.report["go_live_items"]}
    assert set(states) == {"GLI-1", "GLI-2", "GLI-3", "GLI-4", "GLI-5", "GLI-6"}
    assert all(v == "live-accepted" for v in states.values()), states
    assert res.problems == []


# ---------------------------------------------------------------------------
# 2. latest-run artifact 完整性 + 路径安全（7.3/7.4）
# ---------------------------------------------------------------------------
def test_gate_recomputes_latest_artifacts_clean():
    res = glg.evaluate()
    verified = res.report["latest_artifacts_verified"]
    assert verified["clean"] is True
    # Task 1..7 each contribute at least one hash-pinned artifact.
    assert verified["checked"] >= 7


# ---------------------------------------------------------------------------
# 3. 残留环境 GAP 被透明 surface 且与证据一致（7.7/7.8/7.9 — 不掩盖不伪造）
# ---------------------------------------------------------------------------
def test_residual_gaps_surfaced_not_hidden():
    res = glg.evaluate()
    gaps = {g["item"]: g for g in res.report["residual_gaps"]}
    assert set(gaps) == {"GLI-4", "GLI-6"}, "both documented environment GAPs must surface"

    # GLI-4: 6000 honest-extrapolation, explicitly permitted by R4.2.
    g4 = gaps["GLI-4"]
    assert g4["evidence_marker_detected"] is True
    assert g4["latest_run_status"] == "passed"
    assert "Honest_Extrapolation" in g4["conformance"] or "外推" in g4["summary"]

    # GLI-6: PR not opened — must NOT be silently passed over.
    g6 = gaps["GLI-6"]
    assert g6["evidence_marker_detected"] is True
    assert g6["latest_run_status"] == "passed"
    assert "未实际开启" in g6["summary"]

    # Stance is explicit and non-blocking (surface, not block).
    assert "surface-not-block" in res.report["residual_gap_stance"]
    assert res.report["residual_gaps_count"] == 2


def test_residual_gap_registry_cannot_drift_from_evidence():
    """若 curated GAP 在其 Task 最新 run notes 中找不到 marker，门必阻断（fail-closed）。"""
    res = glg.evaluate()
    # All curated GAPs are detected in the live evidence → no drift problem raised.
    assert not any("registry 与证据漂移" in p for p in res.problems)


# ---------------------------------------------------------------------------
# 4. smoke 未冒充验收（7.9）
# ---------------------------------------------------------------------------
def test_no_item_uses_smoke_as_acceptance():
    res = glg.evaluate()
    states = {row["id"]: row["state"] for row in res.report["go_live_items"]}
    assert "smoke-not-accepted" not in states.values()


# ---------------------------------------------------------------------------
# 5. Task 8 run 已 append 且 spec precheck 干净（7.10）
# ---------------------------------------------------------------------------
def test_task8_run_recorded_and_precheck_clean():
    problems = gle.precheck()
    assert problems == [], f"this spec's precheck must be clean, got: {problems}"

    manifest = json.loads(gle.MANIFEST_PATH.read_text(encoding="utf-8"))
    t8 = [r for r in manifest["runs"] if str(r["task_id"]).startswith("8.")]
    assert t8, "Task 8 Go_Live_Gate run must be recorded"
    latest = t8[-1]
    assert latest["status"] == "passed"
    assert set(latest["criterion_ids"]) >= {"7.5", "7.6", "7.7", "7.8", "7.9", "7.10"}
    assert latest["artifacts"], "Task 8 run must pin the gate report artifact"


def test_task8_gate_report_artifact_matches_evaluation():
    """pinned Task 8 报告 artifact 的 verdict/live 计数与实时评估一致（确定性）。"""
    path = gle.SPEC_DIR / "evidence/artifacts/task8/go_live_gate_report.json"
    assert path.exists(), "Task 8 gate report artifact must exist"
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["verdict"] == "live"
    assert report["go_live_items_live"] == 6
    assert report["residual_gaps_count"] == 2
