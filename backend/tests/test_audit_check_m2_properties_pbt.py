"""audit-check-review-gate-hardening Task 4.4 — M2 上报/fail-open PBT + 去重优先级单测

覆盖 design 的 Correctness Properties（hypothesis max_examples=5，conftest fast profile
已全局收敛，此处显式 `@settings(max_examples=5)` 更稳）：

- P6（上报按 source 命名空间替换，Req4.1/3.3）：
  - P6a 同一底稿同一 source 再次上报 → 覆盖该 source 旧项不累积（直接测 report 端点
    `report_audit_checks` 的 upsert 纯逻辑，参考 test_audit_check_report_endpoint.py 的
    mock 模式）。随机 source（∈ FRONTEND_REPORTABLE_SOURCES）+ 随机 items 列表，
    模拟"两次上报同 source" → 断言最终该 source 项数 == 第二次 items 数。
  - P6b recompute 保留 S6：`recompute_workpaper` 只清后端自算 source（S1-S5），已上报
    source（S6）原样保留。构造 `wp.parsed_data.audit_checks` 含随机 S6 项 + 随机
    fine_checks，S2 monkeypatch 返 [] → 断言重算后全部 S6 项仍在。

- P7（聚合 fail-open，Req4.5/2.4）：`recompute_project` 中随机一个项目级来源（S3
  note_validation / S4 qc / S5 unadjusted_misstatement）抛异常 → 不整体抛、其余来源项
  仍产出（异常来源相关项被隔离）。hypothesis 泛化到随机来源 + 随机异常。

- Property 5（去重优先级 cycle_recon > fine_rule，Req4.3）：单测 `_merge_dedup`——
  同一 (wp_code, 审定↔TB 语义) 同时有 cycle_recon（code 含 `-RECON-TB`）+ fine_rule
  （check_type=balance，code 含 CHK-01）→ 只保留 cycle_recon，丢弃 fine_rule；反例：
  语义键为 None 的项（拿不准）全保留（不误删）。

async 端点/聚合器函数由同步 hypothesis @given 测试通过 `asyncio.run` 驱动（hypothesis 与
async def / function-scoped async fixture 不兼容，用同步包装 + 每 example 独立事件循环最稳）；
纯 async 单测标 `@pytest.mark.asyncio`（本仓库 asyncio_mode=auto）。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, strategies as st

import app.routers.audit_check as router_mod
from app.routers.audit_check import (
    ReportAuditChecksRequest,
    ReportedCheckItem,
    report_audit_checks,
)
from app.services.audit_check import (
    AuditCheckAggregator,
    AuditCheckSource,
    ProjectCheckSummary,
)
from app.services.audit_check.aggregator import _merge_dedup
from app.services.audit_check.models import (
    FRONTEND_REPORTABLE_SOURCES,
    PROJECT_WP_CODE,
    AuditCheckItem,
)


# ═══════════════════════════════════════════════════════════════════
# 共享 mock 夹具（对齐 test_audit_check_report_endpoint / test_audit_check_aggregator）
# ═══════════════════════════════════════════════════════════════════

class _WP:
    def __init__(self, parsed_data, wp_id):
        self.id = wp_id
        self.parsed_data = parsed_data
        self.wp_index_id = uuid4()


class _IDX:
    def __init__(self, wp_code):
        self.wp_code = wp_code


def _make_report_db(first_row):
    """mock AsyncSession：`(await db.execute(...)).first()` 返回给定 row。"""
    db = AsyncMock()
    result = MagicMock()
    result.first.return_value = first_row
    db.execute.return_value = result
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


async def _report(wp, idx, source, items):
    """直接 await report 端点函数（patch flag_modified 为 no-op，wp 非 ORM 实例）。"""
    db = _make_report_db((wp, idx))
    body = ReportAuditChecksRequest(
        source=source,
        items=[ReportedCheckItem(**it) for it in items],
    )
    with patch.object(router_mod, "flag_modified", lambda *a, **k: None):
        return await report_audit_checks(
            project_id=uuid4(),
            wp_id=wp.id,
            body=body,
            db=db,
            current_user=None,
        )


# ═══════════════════════════════════════════════════════════════════
# hypothesis 策略
# ═══════════════════════════════════════════════════════════════════

_REPORTABLE_SOURCES = sorted(FRONTEND_REPORTABLE_SOURCES)

_reported_item = st.fixed_dictionaries({
    "code": st.text(min_size=1, max_size=8),
    "passed": st.sampled_from([True, False, None]),
    "severity": st.sampled_from(["blocking", "warning", "info"]),
    "check_type": st.sampled_from(["balance", "reconciliation", "cross_ref"]),
    "message": st.text(max_size=12),
})

# S6 缓存项（code 唯一，便于断言"每一条都保留"）
_s6_cached = st.lists(
    st.tuples(
        st.text(min_size=1, max_size=6),
        st.sampled_from(_REPORTABLE_SOURCES),
    ),
    unique_by=lambda t: t[0],
    max_size=5,
)

# fine_checks 项（S1）
_fine_check = st.fixed_dictionaries({
    "code": st.text(min_size=1, max_size=6),
    "type": st.sampled_from(["aging", "balance", "cross_ref", "completeness"]),
    "passed": st.sampled_from([True, False]),
    "severity": st.sampled_from(["blocking", "warning", "info"]),
    "message": st.text(max_size=10),
})


# ═══════════════════════════════════════════════════════════════════
# P6a — 上报按 source 命名空间替换幂等（Req4.1/3.3）
# ═══════════════════════════════════════════════════════════════════

class TestP6ReportUpsertIdempotent:
    """P6a：同一底稿同一 source 两次上报 → 覆盖不累积（最终该 source 项数 == 第二次 items 数）。"""

    @given(
        source=st.sampled_from(_REPORTABLE_SOURCES),
        first=st.lists(_reported_item, max_size=5),
        second=st.lists(_reported_item, max_size=5),
    )
    @settings(max_examples=5)
    def test_same_source_report_overwrites_not_accumulate(self, source, first, second):
        async def _inner():
            wp = _WP({}, uuid4())
            idx = _IDX("E1")

            # 第一次上报
            await _report(wp, idx, source, first)
            same_after_first = [
                c for c in wp.parsed_data["audit_checks"] if c["source"] == source
            ]
            assert len(same_after_first) == len(first)

            # 第二次上报同 source → 覆盖旧项（不累积）
            r2 = await _report(wp, idx, source, second)
            same_after_second = [
                c for c in wp.parsed_data["audit_checks"] if c["source"] == source
            ]
            # 不变量：最终该 source 项数 == 第二次 items 数（非 first+second）
            assert len(same_after_second) == len(second)
            # wp 起始为空、全程仅此一个 source → total 亦等于第二次 items 数
            assert r2["total_checks"] == len(second)
            # 每条补齐服务端归属（source/wp_id/produced_at）
            for c in same_after_second:
                assert c["source"] == source
                assert c["wp_id"] == str(wp.id)
                assert c["produced_at"]

        asyncio.run(_inner())

    @given(items=st.lists(_reported_item, min_size=1, max_size=5))
    @settings(max_examples=5)
    def test_repeated_identical_report_is_idempotent(self, items):
        """同一 items 重复上报多次 → 项数恒等于单次 items 数（幂等，绝不翻倍）。"""
        async def _inner():
            wp = _WP({}, uuid4())
            idx = _IDX("G7")
            source = AuditCheckSource.REPORT_CROSS_CHECK.value
            for _ in range(3):
                await _report(wp, idx, source, items)
            same = [c for c in wp.parsed_data["audit_checks"] if c["source"] == source]
            assert len(same) == len(items)

        asyncio.run(_inner())


# ═══════════════════════════════════════════════════════════════════
# P6b — recompute 保留 S6（Req3.3/4.1）
# ═══════════════════════════════════════════════════════════════════

class TestP6RecomputeRetainsS6:
    """P6b：recompute_workpaper 只清后端自算 source（S1-S5），已上报 source（S6）原样保留。"""

    @given(s6=_s6_cached, fine_checks=st.lists(_fine_check, max_size=4))
    @settings(max_examples=5)
    def test_recompute_preserves_all_reported_s6_items(self, s6, fine_checks):
        async def _inner():
            s6_dicts = [
                {
                    "code": code,
                    "source": source,
                    "wp_code": "G7",
                    "wp_id": "wp-1",
                    "check_type": "cross_ref",
                    "severity": "warning",
                    "passed": False,
                    "message": "reported",
                    "produced_at": "2026-07-24T00:00:00",
                }
                for code, source in s6
            ]
            pd = {
                "fine_checks": fine_checks,
                "fine_extracted_at": "2026-07-20T00:00:00",
                "audit_checks": list(s6_dicts),
            }
            wp = MagicMock()
            wp.id = "wp-1"
            wp.parsed_data = pd
            idx = MagicMock()
            idx.wp_code = "G7"  # 不在 cycle registry；S2 亦被 patch 为 []
            db = MagicMock()
            db.flush = AsyncMock(return_value=None)

            with patch(
                "app.services.audit_check.aggregator.build_cycle_reconciliation_findings",
                AsyncMock(return_value=[]),
            ), patch(
                "app.services.audit_check.aggregator.build_d2_reconciliation_findings",
                AsyncMock(return_value=[]),
            ):
                items = await AuditCheckAggregator().recompute_workpaper(
                    db, wp, idx, year=2025
                )

            result_codes = {it.code for it in items}
            # 不变量：每一条 S6 上报项（code 唯一）在重算后仍存在
            for code, source in s6:
                assert code in result_codes, f"S6 项 {code}/{source} 被 recompute 丢弃"
                match = next(it for it in items if it.code == code)
                assert match.source == source
                assert match.source in FRONTEND_REPORTABLE_SOURCES
            # 写缓存也含全部 S6 code
            cached_codes = {c["code"] for c in wp.parsed_data["audit_checks"]}
            for code, _ in s6:
                assert code in cached_codes

        asyncio.run(_inner())


# ═══════════════════════════════════════════════════════════════════
# P7 — 聚合 fail-open（Req4.5/2.4）
# ═══════════════════════════════════════════════════════════════════

def _project_item(source: str, *, passed) -> AuditCheckItem:
    return AuditCheckItem(
        code=f"{source.upper()}-1",
        source=source,
        wp_code=PROJECT_WP_CODE,
        wp_id=None,
        severity="warning",
        check_type=source,
        description="",
        message="",
        produced_at="2026-07-24T00:00:00",
        passed=passed,
    )


class TestP7ProjectFailOpen:
    """P7：recompute_project 中随机一个项目级来源抛异常 → 不整体抛，其余来源仍产出。"""

    @given(
        which=st.sampled_from(["note", "qc", "misstatement"]),
        exc_type=st.sampled_from([RuntimeError, ValueError, KeyError, TypeError]),
        exc_msg=st.text(max_size=12),
    )
    @settings(max_examples=5)
    def test_random_project_source_raises_others_survive(self, which, exc_type, exc_msg):
        async def _inner():
            note_mock = AsyncMock(return_value=[
                _project_item(AuditCheckSource.NOTE_VALIDATION.value, passed=False)])
            qc_mock = AsyncMock(return_value=[
                _project_item(AuditCheckSource.QC.value, passed=False)])
            ms_mock = AsyncMock(return_value=[
                _project_item(AuditCheckSource.UNADJUSTED_MISSTATEMENT.value, passed=True)])

            exc = exc_type(exc_msg or "boom")
            if which == "note":
                note_mock = AsyncMock(side_effect=exc)
            elif which == "qc":
                qc_mock = AsyncMock(side_effect=exc)
            else:
                ms_mock = AsyncMock(side_effect=exc)

            # 无 per-wp 底稿（首查 .all() 返 []），仅测项目级 S3/S4/S5 fail-open
            db = AsyncMock()
            result = MagicMock()
            result.all.return_value = []
            db.execute.return_value = result
            db.flush = AsyncMock()

            with patch(
                "app.services.audit_check.aggregator._build_note_validation_items",
                note_mock,
            ), patch(
                "app.services.audit_check.aggregator._build_qc_items",
                qc_mock,
            ), patch(
                "app.services.audit_check.aggregator._build_misstatement_items",
                ms_mock,
            ):
                # 不变量①：随机来源抛异常，recompute_project 不整体抛
                summary = await AuditCheckAggregator().recompute_project(
                    db, uuid4(), 2025
                )

            # 不变量②：其余两个来源的项仍产出（每来源恰 1 项 → 存活 2 项）
            assert isinstance(summary, ProjectCheckSummary)
            assert summary.total == 2, (
                f"期望存活 2 项（异常来源={which} 被隔离），实得 {summary.total}"
            )

        asyncio.run(_inner())

    @given(exc_msg=st.text(max_size=12))
    @settings(max_examples=5)
    def test_all_project_sources_raise_still_no_throw(self, exc_msg):
        """极端：S3/S4/S5 全部抛异常 → 仍不整体抛，返回空汇总（total=0）。"""
        async def _inner():
            boom = AsyncMock(side_effect=RuntimeError(exc_msg or "boom"))
            db = AsyncMock()
            result = MagicMock()
            result.all.return_value = []
            db.execute.return_value = result
            db.flush = AsyncMock()

            with patch(
                "app.services.audit_check.aggregator._build_note_validation_items", boom,
            ), patch(
                "app.services.audit_check.aggregator._build_qc_items", boom,
            ), patch(
                "app.services.audit_check.aggregator._build_misstatement_items", boom,
            ):
                summary = await AuditCheckAggregator().recompute_project(
                    db, uuid4(), 2025
                )
            assert isinstance(summary, ProjectCheckSummary)
            assert summary.total == 0

        asyncio.run(_inner())


# ═══════════════════════════════════════════════════════════════════
# Property 5 — 去重优先级 cycle_recon > fine_rule（Req4.3）
# ═══════════════════════════════════════════════════════════════════

def _cycle_item(code, *, check_type="balance", severity="blocking", passed=False):
    return AuditCheckItem(
        code=code,
        source=AuditCheckSource.CYCLE_RECON.value,
        wp_code="K9-1",
        severity=severity,
        check_type=check_type,
        description="",
        message="",
        produced_at="",
        passed=passed,
    )


def _fine_item(code, *, check_type="balance", severity="blocking", passed=True):
    return AuditCheckItem(
        code=code,
        source=AuditCheckSource.FINE_RULE.value,
        wp_code="K9-1",
        severity=severity,
        check_type=check_type,
        description="",
        message="",
        produced_at="",
        passed=passed,
    )


class TestProperty5DedupPriority:
    """Property 5：同一 (wp_code, 审定↔TB 语义) cycle_recon 覆盖 fine_rule；拿不准全保留。"""

    def test_tb_semantic_cycle_recon_supersedes_fine_rule(self):
        """审定↔TB：cycle_recon(-RECON-TB) 覆盖 fine_rule(CHK-01/balance)，只保留 cycle_recon。"""
        cyc = _cycle_item("K9-RECON-TB")
        fr = _fine_item("K9-CHK-01")
        merged = _merge_dedup([fr, cyc])
        assert cyc in merged
        assert fr not in merged
        # 顺序无关：反向输入结果一致
        merged2 = _merge_dedup([cyc, fr])
        assert cyc in merged2
        assert fr not in merged2

    def test_tb_semantic_keeps_fine_rule_when_no_cycle_counterpart(self):
        """无同语义 cycle_recon 时 fine_rule(CHK-01) 保留（保守不误删）。"""
        fr = _fine_item("K9-CHK-01")
        merged = _merge_dedup([fr])
        assert fr in merged

    def test_none_semantic_items_all_preserved(self):
        """反例：语义键为 None 的项（拿不准）全部保留，绝不误删。

        - cycle_recon 信息项 RECON-ADJ（无对应 fine_rule）→ None
        - fine_rule 非 CHK-01/CHK-03 项（如 CHK-09 aging）→ None
        - S6 上报项 → None（不参与 fine_rule/cycle_recon 去重）
        """
        adj = _cycle_item("K9-RECON-ADJ", check_type="analysis", severity="info",
                          passed=None)
        other_fine = _fine_item("K9-CHK-09", check_type="aging", severity="warning",
                                passed=True)
        reported = AuditCheckItem(
            code="G7-REPORT-1", source=AuditCheckSource.REPORT_CROSS_CHECK.value,
            wp_code="G7", severity="warning", check_type="cross_ref",
            description="", message="", produced_at="", passed=False,
        )
        items = [adj, other_fine, reported]
        merged = _merge_dedup(items)
        # 一个不少（AuditCheckItem 为不可哈希 dataclass，用 membership + 长度校验）
        assert len(merged) == len(items)
        for it in items:
            assert it in merged

    def test_detail_semantic_dedup_does_not_touch_tb_or_none(self):
        """审定↔明细语义去重独立：不误伤 TB 语义项，也不误删 None 语义项。"""
        detail_cyc = AuditCheckItem(
            code="D2-RECON-DETAIL", source=AuditCheckSource.CYCLE_RECON.value,
            wp_code="D2", severity="warning", check_type="cross_ref",
            description="", message="", produced_at="", passed=False,
        )
        detail_fr = AuditCheckItem(
            code="D2-CHK-03", source=AuditCheckSource.FINE_RULE.value,
            wp_code="D2", severity="warning", check_type="cross_ref",
            description="", message="", produced_at="", passed=True,
        )
        unrelated_none = _fine_item("D2-CHK-09", check_type="aging", passed=True)
        merged = _merge_dedup([detail_fr, detail_cyc, unrelated_none])
        assert detail_cyc in merged
        assert detail_fr not in merged  # 同 detail 语义被 cycle 覆盖
        assert unrelated_none in merged  # None 语义保留

    def test_different_wp_code_not_deduped(self):
        """不同 wp_code 即使同语义也不互相去重（语义键含 wp_code）。"""
        cyc_a = _cycle_item("A-RECON-TB")
        cyc_a.wp_code = "K9-1"
        fr_b = _fine_item("B-CHK-01")
        fr_b.wp_code = "K1-1"  # 不同底稿
        merged = _merge_dedup([fr_b, cyc_a])
        # 不同 wp_code → 无覆盖关系，两者都保留
        assert cyc_a in merged
        assert fr_b in merged
