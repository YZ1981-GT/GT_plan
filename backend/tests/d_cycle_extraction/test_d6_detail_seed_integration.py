"""Wave 5 / Task 5.1 —— D6-2 明细表维度归集 render transient 自动 seed 集成测试.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/
      (Requirements 4.1-4.7, 5.2, 5.3 / Property 8, 9, 11, 13)
      .kiro/specs/_archive/71-formula-fetch-and-wp-generation-defect-closure/（R7.2）

覆盖：
  * **Property 8（手工优先 + 子开关门控）**：明细自动 seed 仅在 主开关 ∧
    `D_CYCLE_DETAIL_SEED_ENABLED` ∧ D6-2 明细表完全空 时并入 `detail_prefill`；
    已有任一行 → 不 seed（且不去归集）；子开关关 / 主开关关 → 无 detail seed。
  * **Property 9（复用不新造）**：明细 seed 经 `aggregate_d6_detail_rows` → D 循环 aux 归集统一
    入口 `aggregate_d_cycle_aux(项目, 年度, "D6")`，年度取 render 上下文。
  * **Property 11（fail-open）**：归集异常 → 省略 detail_prefill，不阻断 render。
  * **Property 13（transient 不落库）**：detail_prefill 只进 render 返回 payload。

🔴 R7.2：seed 原先不传年度 ⇒ 共享件按 `year = 0` 过滤 ⇒ 真实数据上恒空；本文件原用例按旧裸 SQL
的文本路由造数，四表库迁移后归集在替身上恒空，seed 相关 3 条一直红、其余「不 seed」用例空转通过。
现 render 层替换归集统一入口并断言入参；`test_seed_chain_on_sqlite_reads_render_year` 用真 SQLite
行跑通 seed → 归集全链。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.routers.wp_render_strategies import _d6_contract_assets as d6
from tests.d_cycle_extraction._aux_sqlite import aux_row, run_on_aux_rows
from tests.d_cycle_extraction._endpoint_doubles import patch_d_cycle_aux_aggregation

# characterization 基线顶层键
_BASELINE_KEYS = {
    "sections",
    "adjudication_config",
    "ecl_config",
    "project_context",
    "disclosure_visibility",
    "responses_snapshot",
}
_SEED_ROW_KEYS = {
    "rowId", "seqNo", "contractName", "customerName", "priorUnadjusted", "source_kind", "source",
}


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake async DB —— 按 SQL 文本路由 render 其余查询（归集走统一入口替身）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _FakeSession:
    def __init__(self, *, checklist_rows=None, project_row=None, tb_row=None, rp_rows=None):
        self.checklist_rows = checklist_rows or []
        self.project_row = project_row
        self.tb_row = tb_row
        self.rp_rows = rp_rows or []
        self.executed_sql: list[str] = []

    async def execute(self, stmt, params=None):
        s = str(stmt)
        self.executed_sql.append(s)
        low = s.lower()
        # Tier B prefill 叶子查询：tb_balance（本测未启 prefill 路径，返空）
        if "tb_balance" in low and "trial_balance" not in low:
            return _FakeResult(rows=[])
        if "checklist_responses" in low:
            return _FakeResult(rows=self.checklist_rows)
        if "related_party_registry" in low:
            return _FakeResult(rows=self.rp_rows)
        if "trial_balance" in low:
            return _FakeResult(one=self.tb_row)
        if "from projects" in low or "projects where" in low:
            return _FakeResult(one=self.project_row)
        return _FakeResult()

    async def rollback(self):
        return None


def _checklist_row(item_id: str, conclusion: str = "", remark: str = ""):
    return SimpleNamespace(item_id=item_id, conclusion=conclusion, remark=remark)


def _aux(aux_name, *, prior=0.0, current=0.0):
    """归集统一入口返回的条目 (aux_name, opening, debit, credit, closing)。"""
    return (aux_name, prior, 0.0, 0.0, current)


def _ctx(db, *, year=2025):
    return SimpleNamespace(
        db=db,
        wp_id=uuid4(),
        project_id=uuid4(),
        year=year,
        business_category="general",
        classification=SimpleNamespace(sheet_name="合同资产明细表D6-2"),
    )


def _session(*, checklist_rows=None):
    return _FakeSession(
        checklist_rows=checklist_rows or [],
        project_row=SimpleNamespace(
            client_name="测试客户",
            audit_year=2025,
            business_category="general",
            applicable_standards="listed",
        ),
        tb_row=SimpleNamespace(amount=98765.43, unadjusted=98765.43, audited=98765.43),
        rp_rows=[SimpleNamespace(name="关联方甲", relation_type="subsidiary")],
    )


def _main_on(monkeypatch):
    monkeypatch.setattr(d6.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)


def _main_off(monkeypatch):
    monkeypatch.setattr(d6.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)


def _sub_on(monkeypatch):
    monkeypatch.setattr(d6.settings, "D_CYCLE_DETAIL_SEED_ENABLED", True)


def _sub_off(monkeypatch):
    monkeypatch.setattr(d6.settings, "D_CYCLE_DETAIL_SEED_ENABLED", False)


# ---------------------------------------------------------------------------
# Property 8 / 10: 子开关门控（发 P0-1、压 P0-2）—— 门关时连归集都不调
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("main, sub", [(False, False), (True, False), (False, True)])
def test_gate_off_no_detail_prefill_and_no_aggregation(monkeypatch, main, sub):
    """主 ∧ 子任一关 → 无 detail_prefill，且不触发归集（基线零回归 / R5.2 / Property 8）。"""
    (_main_on if main else _main_off)(monkeypatch)
    (_sub_on if sub else _sub_off)(monkeypatch)
    calls = patch_d_cycle_aux_aggregation(monkeypatch, [_aux("客户A", current=1000.0)])
    result = _run(d6.render(_ctx(_session())))
    assert "detail_prefill" not in result
    assert calls == []
    if not main:
        assert set(result.keys()) == _BASELINE_KEYS


# ---------------------------------------------------------------------------
# Property 9: 主 ∧ 子全开 + 明细空 → seed（经归集统一入口，年度取 render 上下文）
# ---------------------------------------------------------------------------


def test_both_on_empty_detail_seeds(monkeypatch):
    """主 ∧ 子全开 + D6-2 明细空 → detail_prefill = 录入列 + source="four-table"。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    calls = patch_d_cycle_aux_aggregation(monkeypatch, [
        _aux("客户A", prior=800.0, current=1000.0),
        _aux("客户B", prior=200.0, current=300.0),
    ])
    ctx = _ctx(_session())
    result = _run(d6.render(ctx))
    assert calls == [{"project_id": str(ctx.project_id), "year": 2025, "wp_code": "D6"}]
    prefill = result["detail_prefill"]
    assert [r["customerName"] for r in prefill] == ["客户A", "客户B"]
    first = prefill[0]
    assert set(first) == _SEED_ROW_KEYS, "只写录入列（账龄 / 派生列交前端 recalc）"
    assert first["source"] == "four-table"
    assert first["contractName"] == "客户A"
    assert first["priorUnadjusted"] == 800.0
    assert first["seqNo"] == 1
    assert _BASELINE_KEYS.issubset(set(result.keys()))


def test_seed_uses_render_year(monkeypatch):
    """归集年度 = render 上下文年度（原先漏传 ⇒ 按 year=0 查、真实数据上恒空）。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    calls = patch_d_cycle_aux_aggregation(monkeypatch, [_aux("客户A", prior=1.0)])
    _run(d6.render(_ctx(_session(), year=2024)))
    assert [c["year"] for c in calls] == [2024]


def test_seed_without_year_skips_aggregation(monkeypatch):
    """render 无审计年度 → 不 seed、不去归集（拿不到年度就无从按年过滤）。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    calls = patch_d_cycle_aux_aggregation(monkeypatch, [_aux("客户A", prior=1.0)])
    result = _run(d6.render(_ctx(_session(), year=None)))
    assert "detail_prefill" not in result
    assert calls == []


def test_both_on_no_aux_data_no_seed(monkeypatch):
    """主 ∧ 子全开 + 归集无数据 → 无 detail_prefill（不阻断 render）。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    calls = patch_d_cycle_aux_aggregation(monkeypatch, [])
    result = _run(d6.render(_ctx(_session())))
    assert len(calls) == 1
    assert "detail_prefill" not in result
    assert _BASELINE_KEYS.issubset(set(result.keys()))


# ---------------------------------------------------------------------------
# Property 8: 手工优先（D6-2 已有行 → 不 seed）
# ---------------------------------------------------------------------------


def test_both_on_existing_rows_no_seed(monkeypatch):
    """D6-2-rows 非空数组（已有行）→ 不 seed、不归集（手工优先，不覆盖 / R4.2）。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    calls = patch_d_cycle_aux_aggregation(monkeypatch, [_aux("客户A", current=999.0)])
    checklist = [
        _checklist_row("D6-2-rows", remark='[{"rowId":"r1","customerName":"手工客户"}]'),
    ]
    result = _run(d6.render(_ctx(_session(checklist_rows=checklist))))
    assert "detail_prefill" not in result
    assert calls == []


def test_both_on_empty_array_marker_seeds(monkeypatch):
    """D6-2-rows = "[]"（空数组标记）→ 视为空 → 仍 seed。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    patch_d_cycle_aux_aggregation(monkeypatch, [_aux("客户A", current=999.0)])
    checklist = [_checklist_row("D6-2-rows", remark="[]")]
    result = _run(d6.render(_ctx(_session(checklist_rows=checklist))))
    assert len(result["detail_prefill"]) == 1


# ---------------------------------------------------------------------------
# Property 11: fail-open（归集异常 → 空 seed，不阻断 render）
# ---------------------------------------------------------------------------


def test_aggregation_error_fails_open(monkeypatch):
    """主 ∧ 子全开 + 归集抛异常 → fail-open（省略 detail_prefill，render 正常）。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    calls = patch_d_cycle_aux_aggregation(monkeypatch, [], raise_exc=RuntimeError("aux boom"))
    result = _run(d6.render(_ctx(_session())))
    assert len(calls) == 1, "确实走到了归集（否则 fail-open 断言空转）"
    assert "detail_prefill" not in result
    assert _BASELINE_KEYS.issubset(set(result.keys()))


# ---------------------------------------------------------------------------
# Property 13: transient 不落库（render 全程无写库）
# ---------------------------------------------------------------------------


def test_detail_seed_transient_not_persisted(monkeypatch):
    """detail_prefill 只进返回 payload；render 全程无 INSERT/UPDATE/DELETE（不落库）。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    patch_d_cycle_aux_aggregation(monkeypatch, [_aux("客户A", current=1000.0)])
    session = _session()
    result = _run(d6.render(_ctx(session)))
    assert "detail_prefill" in result  # seed 生效
    for sql in session.executed_sql:
        low = sql.lower().strip()
        assert not low.startswith(("insert", "update", "delete")), f"render 不应写库: {sql}"


# ---------------------------------------------------------------------------
# 全链：seed → aggregate_d6_detail_rows → 共享件 ORM 查询（真 SQLite 行）
# ---------------------------------------------------------------------------


def test_seed_chain_on_sqlite_reads_render_year():
    """真 SQLite 行跑 seed 全链：只取 render 年度的行（漏传年度时本用例恒空、必红）。"""
    pid = uuid4()
    rows = [
        aux_row("客户甲", project_id=pid, opening=100, closing=150, year=2025),
        aux_row("客户乙", project_id=pid, opening=30, closing=40, year=2024),
    ]

    async def _seed(db):
        ctx = SimpleNamespace(db=db, project_id=pid, year=2025)
        return await d6._seed_d6_detail_prefill(ctx, {})

    seeded = _run(run_on_aux_rows(rows, _seed))
    assert [(r["customerName"], r["priorUnadjusted"], r["source"]) for r in seeded] == [
        ("客户甲", 100.0, "four-table"),
    ]


# ---------------------------------------------------------------------------
# 判空 helper 稳健性单测（缺失/空/[]/null/{}/非空/无法解析）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snapshot, expected_empty",
    [
        ({}, True),  # 缺失
        ({"D6-2-rows": {"remark": ""}}, True),  # 空串
        ({"D6-2-rows": {"remark": "[]"}}, True),  # 空数组
        ({"D6-2-rows": {"remark": "null"}}, True),  # null
        ({"D6-2-rows": {"remark": "{}"}}, True),  # 空对象标记
        ({"D6-2-rows": {"remark": '[{"rowId":"r1"}]'}}, False),  # 非空数组
        ({"D6-2-rows": {"remark": "not-json-非空"}}, False),  # 无法解析非空 → 保守非空
        ({"D6-2-rows": "not-a-dict"}, True),  # 非 dict 值 → 视为缺失
    ],
)
def test_detail_rows_empty_robust(snapshot, expected_empty):
    assert d6._detail_rows_empty(snapshot) is expected_empty
