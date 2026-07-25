"""Tests for structured reconciliation findings (Task 2.1).

验证 `build_cycle_reconciliation_findings` / `build_d2_reconciliation_findings`
结构化产出与对应文本版**共用同一核心计算与判定口径**（单一判定口径，Property 5 / Req4.2）：

- 结构化 finding 的 passed/diff 与文本版描述的平衡/不平衡结论一致
- 不在注册表 wp_code → 返回 []
- 缺一侧数据 → 对应 finding passed=None（未覆盖）
- 审定↔TB 不一致 → passed=False + severity=blocking
- fail-open：核心计算异常 → 返回 []

主体走纯映射/格式化函数（`_map_*` / `_format_*`）配合手工构造中间数据，
不依赖 DB；公共 async 入口的短路/fail-open 走 asyncio.run + monkeypatch。
"""
from __future__ import annotations

import asyncio

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import app.services.cycle_review_context as cyc
import app.services.d2_review_context as d2mod
from app.services.cycle_review_context import (
    _CycleReconData,
    _format_cycle_recon_text,
    _map_cycle_recon_findings,
    build_cycle_reconciliation_findings,
)
from app.services.d2_review_context import (
    _D2ReconData,
    _format_d2_recon_text,
    _map_d2_recon_findings,
    build_d2_reconciliation_findings,
)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _find(findings: list[dict], code: str) -> dict | None:
    return next((f for f in findings if f["code"] == code), None)


def _codes(findings: list[dict]) -> set[str]:
    return {f["code"] for f in findings}


# ═══════════════════════════════════════════════════════════════════════════
# K/N 循环结构化产出
# ═══════════════════════════════════════════════════════════════════════════


def test_cycle_all_balanced():
    """审定↔明细↔TB 全平衡 → DETAIL/TB passed=True，ADJ 为 info(None)。"""
    cfg = cyc._REGISTRY["K9"]  # 损益类（发生额）
    data = _CycleReconData(
        cycle="K9", cfg=cfg,
        audited_total=1000.0, detail_total=1000.0, has_detail=True,
        tb={"unadjusted": 800.0, "audited": 1000.0},
    )
    findings = _map_cycle_recon_findings(data)
    assert _codes(findings) == {"K9-RECON-DETAIL", "K9-RECON-TB", "K9-RECON-ADJ"}

    detail = _find(findings, "K9-RECON-DETAIL")
    assert detail["passed"] is True
    assert detail["diff"] == 0.0
    assert detail["check_type"] == "cross_ref"
    assert detail["severity"] == "warning"

    tb = _find(findings, "K9-RECON-TB")
    assert tb["passed"] is True
    assert tb["diff"] == 0.0
    assert tb["check_type"] == "balance"
    assert tb["severity"] == "blocking"

    adj = _find(findings, "K9-RECON-ADJ")
    assert adj["passed"] is None
    assert adj["diff"] == 200.0  # 1000 审定 - 800 未审
    assert adj["check_type"] == "analysis"
    assert adj["severity"] == "info"

    # 口径一致：finding 平衡 ⟺ 文本版平衡/一致
    text = _format_cycle_recon_text(data)
    assert "✓ 平衡" in text
    assert "✓ 一致" in text
    assert "✗ 不平衡" not in text
    assert "✗ 不一致" not in text


def test_cycle_detail_imbalanced_passed_false():
    """审定↔明细不平衡 → DETAIL passed=False，文本版 ✗ 不平衡。"""
    cfg = cyc._REGISTRY["K1"]  # 资产类（期末余额）
    data = _CycleReconData(
        cycle="K1", cfg=cfg,
        audited_total=1000.0, detail_total=900.0, has_detail=True, tb=None,
    )
    findings = _map_cycle_recon_findings(data)
    detail = _find(findings, "K1-RECON-DETAIL")
    assert detail["passed"] is False
    assert detail["diff"] == 100.0
    assert detail["actual"] == 1000.0
    assert detail["expected"] == 900.0
    # tb=None → 无 TB / ADJ finding
    assert _find(findings, "K1-RECON-TB") is None
    assert _find(findings, "K1-RECON-ADJ") is None

    text = _format_cycle_recon_text(data)
    assert "✗ 不平衡" in text


def test_cycle_tb_mismatch_blocking():
    """审定↔TB 不一致 → passed=False + severity=blocking，文本版 ✗ 不一致。"""
    cfg = cyc._REGISTRY["K9"]
    data = _CycleReconData(
        cycle="K9", cfg=cfg,
        audited_total=1000.0, detail_total=1000.0, has_detail=True,
        tb={"unadjusted": 800.0, "audited": 1200.0},
    )
    findings = _map_cycle_recon_findings(data)
    tb = _find(findings, "K9-RECON-TB")
    assert tb["passed"] is False
    assert tb["severity"] == "blocking"
    assert tb["diff"] == round(1000.0 - 1200.0, 2)  # -200.0
    # 明细仍平衡
    assert _find(findings, "K9-RECON-DETAIL")["passed"] is True

    text = _format_cycle_recon_text(data)
    assert "✗ 不一致" in text


def test_cycle_detail_missing_one_side_uncovered():
    """明细缺失（仅审定表有数据）→ DETAIL passed=None（未覆盖）。"""
    cfg = cyc._REGISTRY["K3"]
    data = _CycleReconData(
        cycle="K3", cfg=cfg,
        audited_total=500.0, detail_total=0.0, has_detail=False, tb=None,
    )
    findings = _map_cycle_recon_findings(data)
    detail = _find(findings, "K3-RECON-DETAIL")
    assert detail is not None
    assert detail["passed"] is None
    assert detail["actual"] == 500.0
    assert detail["expected"] is None


def test_cycle_tb_not_written_back_uncovered():
    """审定表已填但 TB 审定=0（尚未回写）→ TB passed=None，ADJ 展示未审。"""
    cfg = cyc._REGISTRY["K9"]
    data = _CycleReconData(
        cycle="K9", cfg=cfg,
        audited_total=1000.0, detail_total=1000.0, has_detail=True,
        tb={"unadjusted": 800.0, "audited": 0.0},
    )
    findings = _map_cycle_recon_findings(data)
    tb = _find(findings, "K9-RECON-TB")
    assert tb["passed"] is None
    assert tb["severity"] == "blocking"
    adj = _find(findings, "K9-RECON-ADJ")
    assert adj["passed"] is None
    assert adj["expected"] == 800.0  # 未审
    assert "尚未回写" in adj["message"]


def test_cycle_no_data_empty():
    """既无审定/明细、也无 TB → 空列表，文本版空串。"""
    cfg = cyc._REGISTRY["K9"]
    data = _CycleReconData(
        cycle="K9", cfg=cfg,
        audited_total=0.0, detail_total=0.0, has_detail=False, tb=None,
    )
    assert _map_cycle_recon_findings(data) == []
    assert _format_cycle_recon_text(data) == ""


def test_cycle_not_in_registry_returns_empty():
    """不在注册表的 wp_code → 返回 []（不触 DB，注册表判定先短路）。"""
    assert asyncio.run(build_cycle_reconciliation_findings("wp-1", "X99")) == []
    assert asyncio.run(build_cycle_reconciliation_findings("wp-1", "foobar")) == []
    assert asyncio.run(build_cycle_reconciliation_findings("wp-1", "")) == []


def test_cycle_fail_open_returns_empty(monkeypatch):
    """核心计算抛异常 → fail-open 返回 []。"""

    async def _boom(wp_id, wp_code):  # noqa: ANN001
        raise RuntimeError("db down")

    monkeypatch.setattr(cyc, "_compute_cycle_reconciliation", _boom)
    assert asyncio.run(build_cycle_reconciliation_findings("wp-1", "K9-1")) == []


def test_cycle_public_entrypoints_share_core(monkeypatch):
    """文本版与结构化版共用同一核心：同一 _CycleReconData → 结论一致。"""
    cfg = cyc._REGISTRY["K9"]
    data = _CycleReconData(
        cycle="K9", cfg=cfg,
        audited_total=1000.0, detail_total=900.0, has_detail=True,
        tb={"unadjusted": 800.0, "audited": 1200.0},
    )

    async def _fixed(wp_id, wp_code):  # noqa: ANN001
        return data

    monkeypatch.setattr(cyc, "_compute_cycle_reconciliation", _fixed)
    text = asyncio.run(cyc.build_cycle_reconciliation_context("wp", "K9-1"))
    findings = asyncio.run(cyc.build_cycle_reconciliation_findings("wp", "K9-1"))

    detail = _find(findings, "K9-RECON-DETAIL")
    tb = _find(findings, "K9-RECON-TB")
    # 结构化不平衡 ⟺ 文本版不平衡
    assert (detail["passed"] is False) == ("✗ 不平衡" in text)
    assert (tb["passed"] is False) == ("✗ 不一致" in text)


@settings(max_examples=5)
@given(
    audited=st.floats(min_value=0.01, max_value=1e7, allow_nan=False, allow_infinity=False),
    detail=st.floats(min_value=0.01, max_value=1e7, allow_nan=False, allow_infinity=False),
)
def test_cycle_detail_finding_matches_text_verdict(audited, detail):
    """PBT：DETAIL finding.passed 与文本版平衡结论恒一致（单一判定口径）。"""
    cfg = cyc._REGISTRY["K9"]
    data = _CycleReconData(
        cycle="K9", cfg=cfg,
        audited_total=round(audited, 2), detail_total=round(detail, 2),
        has_detail=True, tb=None,
    )
    findings = _map_cycle_recon_findings(data)
    text = _format_cycle_recon_text(data)
    detail_f = _find(findings, "K9-RECON-DETAIL")
    if detail_f["passed"]:
        assert "✓ 平衡" in text and "✗ 不平衡" not in text
    else:
        assert "✗ 不平衡" in text


# ═══════════════════════════════════════════════════════════════════════════
# D2 富勾稽结构化产出
# ═══════════════════════════════════════════════════════════════════════════


def test_d2_all_balanced():
    """D2-1↔D2-2 / D2-2↔TB / D2-3↔D2-9 全平衡。"""
    data = _D2ReconData(
        detail_total=500.0, adj_total=500.0, tb_amount=500.0,
        bd_current=10.0, ecl_total=10.0, writeoff_warn=None,
    )
    findings = _map_d2_recon_findings(data)
    assert _codes(findings) == {"D2-RECON-DETAIL", "D2-RECON-TB", "D2-RECON-ECL"}
    assert _find(findings, "D2-RECON-DETAIL")["passed"] is True
    assert _find(findings, "D2-RECON-TB")["passed"] is True
    assert _find(findings, "D2-RECON-ECL")["passed"] is True

    tb = _find(findings, "D2-RECON-TB")
    assert tb["severity"] == "blocking"
    assert tb["check_type"] == "balance"
    ecl = _find(findings, "D2-RECON-ECL")
    assert ecl["check_type"] == "reconciliation"

    text = _format_d2_recon_text(data)
    assert "✓ 平衡" in text
    assert "✓ 一致" in text
    assert "✗ 不平衡" not in text
    assert "✗ 不一致" not in text


def test_d2_tb_mismatch_blocking():
    """D2-2↔TB(1122) 不一致 → passed=False + severity=blocking。"""
    data = _D2ReconData(
        detail_total=500.0, adj_total=500.0, tb_amount=600.0,
        bd_current=0.0, ecl_total=0.0, writeoff_warn=None,
    )
    findings = _map_d2_recon_findings(data)
    tb = _find(findings, "D2-RECON-TB")
    assert tb["passed"] is False
    assert tb["severity"] == "blocking"
    assert tb["diff"] == round(500.0 - 600.0, 2)  # -100.0
    # 明细平衡
    assert _find(findings, "D2-RECON-DETAIL")["passed"] is True

    text = _format_d2_recon_text(data)
    assert "✗ 不平衡" in text


def test_d2_ecl_mismatch():
    """D2-3↔D2-9 坏账↔ECL 不一致 → passed=False。"""
    data = _D2ReconData(
        detail_total=500.0, adj_total=500.0, tb_amount=500.0,
        bd_current=10.0, ecl_total=15.0, writeoff_warn=None,
    )
    findings = _map_d2_recon_findings(data)
    ecl = _find(findings, "D2-RECON-ECL")
    assert ecl["passed"] is False
    assert ecl["diff"] == round(15.0 - 10.0, 2)  # 5.0

    text = _format_d2_recon_text(data)
    assert "✗ 不一致" in text


def test_d2_detail_missing_one_side_uncovered():
    """D2 审定分项全空但明细有数据 → DETAIL passed=None（未覆盖）。"""
    data = _D2ReconData(
        detail_total=500.0, adj_total=0.0, tb_amount=0.0,
        bd_current=0.0, ecl_total=0.0, writeoff_warn=None,
    )
    findings = _map_d2_recon_findings(data)
    detail = _find(findings, "D2-RECON-DETAIL")
    assert detail["passed"] is None
    assert detail["actual"] is None
    assert detail["expected"] == 500.0
    # tb_amount=0 且 detail 有值 → TB 缺一侧 passed=None
    tb = _find(findings, "D2-RECON-TB")
    assert tb["passed"] is None


def test_d2_no_data_empty():
    """全空 → []，文本版仅标题不注入（空串）。"""
    data = _D2ReconData(
        detail_total=0.0, adj_total=0.0, tb_amount=0.0,
        bd_current=0.0, ecl_total=0.0, writeoff_warn=None,
    )
    assert _map_d2_recon_findings(data) == []
    assert _format_d2_recon_text(data) == ""


def test_d2_fail_open_returns_empty(monkeypatch):
    """核心计算抛异常 → fail-open 返回 []。"""

    async def _boom(wp_id):  # noqa: ANN001
        raise RuntimeError("db down")

    monkeypatch.setattr(d2mod, "_compute_d2_reconciliation", _boom)
    assert asyncio.run(build_d2_reconciliation_findings("wp-1")) == []


def test_d2_public_entrypoints_share_core(monkeypatch):
    """D2 文本版与结构化版共用同一核心：同一 _D2ReconData → 结论一致。"""
    data = _D2ReconData(
        detail_total=500.0, adj_total=450.0, tb_amount=600.0,
        bd_current=10.0, ecl_total=15.0, writeoff_warn=None,
    )

    async def _fixed(wp_id):  # noqa: ANN001
        return data

    monkeypatch.setattr(d2mod, "_compute_d2_reconciliation", _fixed)
    text = asyncio.run(d2mod.build_d2_reconciliation_context("wp"))
    findings = asyncio.run(d2mod.build_d2_reconciliation_findings("wp"))

    detail = _find(findings, "D2-RECON-DETAIL")
    tb = _find(findings, "D2-RECON-TB")
    ecl = _find(findings, "D2-RECON-ECL")
    assert (detail["passed"] is False) == ("✗ 不平衡" in text)
    # TB 与 ECL 各自的不一致标记
    assert tb["passed"] is False
    assert ecl["passed"] is False


@settings(max_examples=5)
@given(
    detail=st.floats(min_value=0.01, max_value=1e7, allow_nan=False, allow_infinity=False),
    adj=st.floats(min_value=0.01, max_value=1e7, allow_nan=False, allow_infinity=False),
)
def test_d2_detail_finding_matches_text_verdict(detail, adj):
    """PBT：D2-RECON-DETAIL finding.passed 与文本版结论恒一致。"""
    data = _D2ReconData(
        detail_total=round(detail, 2), adj_total=round(adj, 2), tb_amount=0.0,
        bd_current=0.0, ecl_total=0.0, writeoff_warn=None,
    )
    findings = _map_d2_recon_findings(data)
    text = _format_d2_recon_text(data)
    detail_f = _find(findings, "D2-RECON-DETAIL")
    if detail_f["passed"]:
        assert "✓ 平衡" in text and "✗ 不平衡" not in text
    else:
        assert "✗ 不平衡" in text
