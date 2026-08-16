"""Wave 5 / Task 5.1 —— D6-2 明细表维度归集 render transient 自动 seed 集成测试.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/
      (Requirements 4.1-4.7, 5.2, 5.3 / Property 8, 9, 11, 13)

覆盖：
  * **Property 8（手工优先 + 子开关门控）**：明细自动 seed 仅在 主开关 ∧
    `D_CYCLE_DETAIL_SEED_ENABLED` ∧ D6-2 明细表完全空 时并入 `detail_prefill`；
    已有任一行 → 不 seed；子开关关 / 主开关关 → 无 detail seed。
  * **Property 9（复用不新造）**：明细 seed 调既有 `aggregate_d6_detail_rows`
    （tb_aux_balance 1141 客户/合同维度），不新造第 3 套四表库读取。
  * **Property 11（fail-open）**：归集查询异常 → 空 detail seed（省略 detail_prefill），
    不阻断 render。
  * **Property 13（transient 不落库）**：detail_prefill 只进 render 返回 payload，
    render 全程无 checklist_responses 写库（INSERT/UPDATE/DELETE）。

fake async session 按 SQL 文本路由（新增 tb_aux_balance 路由供 aggregate_d6_detail_rows），
复用 test_d6_render_prefill_integration.py 脚手架范式。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.routers.wp_render_strategies import _d6_contract_assets as d6

# characterization 基线顶层键
_BASELINE_KEYS = {
    "sections",
    "adjudication_config",
    "ecl_config",
    "project_context",
    "disclosure_visibility",
    "responses_snapshot",
}


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake async DB —— 按 SQL 文本路由（新增 tb_aux_balance 供明细归集）
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
    def __init__(
        self,
        *,
        checklist_rows=None,
        project_row=None,
        tb_row=None,
        rp_rows=None,
        aux_rows=None,
        raise_on_aux=False,
    ):
        self.checklist_rows = checklist_rows or []
        self.project_row = project_row
        self.tb_row = tb_row
        self.rp_rows = rp_rows or []
        self.aux_rows = aux_rows or []
        self.raise_on_aux = raise_on_aux
        self.executed_sql: list[str] = []

    async def execute(self, stmt, params=None):
        s = str(stmt)
        self.executed_sql.append(s)
        low = s.lower()
        # 明细归集：SELECT ... FROM tb_aux_balance（先判，避免与 trial_balance 混淆）
        if "tb_aux_balance" in low:
            if self.raise_on_aux:
                raise RuntimeError("tb_aux_balance boom")
            return _FakeResult(rows=self.aux_rows)
        # Tier B prefill 叶子查询：tb_balance（本测未启主开关的 prefill 路径，返空）
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
    """aggregate_d6_detail_rows 的 tb_aux_balance 归集行（aux_name/prior_balance/current_balance）。"""
    return SimpleNamespace(
        aux_name=aux_name, prior_balance=prior, current_balance=current
    )


def _ctx(db):
    return SimpleNamespace(
        db=db,
        wp_id=uuid4(),
        project_id=uuid4(),
        year=2025,
        business_category="general",
        classification=SimpleNamespace(sheet_name="合同资产明细表D6-2"),
    )


def _session(*, checklist_rows=None, aux_rows=None, raise_on_aux=False):
    return _FakeSession(
        checklist_rows=checklist_rows or [],
        project_row=SimpleNamespace(
            client_name="测试客户",
            audit_year=2025,
            business_category="general",
            applicable_standards="listed",
        ),
        tb_row=SimpleNamespace(
            amount=98765.43,
            unadjusted=98765.43,
            audited=98765.43,
        ),
        rp_rows=[SimpleNamespace(name="关联方甲", relation_type="subsidiary")],
        aux_rows=aux_rows or [],
        raise_on_aux=raise_on_aux,
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
# Property 8 / 10: 子开关门控（发 P0-1、压 P0-2）
# ---------------------------------------------------------------------------


def test_both_flags_off_no_detail_prefill(monkeypatch):
    """主开关关（默认）→ 无 detail_prefill（基线零回归）。"""
    _main_off(monkeypatch)
    _sub_off(monkeypatch)
    result = _run(d6.render(_ctx(_session(aux_rows=[_aux("客户A", current=1000.0)]))))
    assert "detail_prefill" not in result
    assert set(result.keys()) == _BASELINE_KEYS


def test_main_on_sub_off_no_detail_prefill(monkeypatch):
    """主开关开、子开关关 → 无 detail seed（"发 P0-1、压 P0-2" / R5.2 / Property 8）。"""
    _main_on(monkeypatch)
    _sub_off(monkeypatch)
    result = _run(d6.render(_ctx(_session(aux_rows=[_aux("客户A", current=1000.0)]))))
    assert "detail_prefill" not in result


def test_sub_on_main_off_no_detail_prefill(monkeypatch):
    """子开关开、主开关关 → 无 detail seed（被主开关 AND 门控 / R5.2）。"""
    _main_off(monkeypatch)
    _sub_on(monkeypatch)
    result = _run(d6.render(_ctx(_session(aux_rows=[_aux("客户A", current=1000.0)]))))
    assert "detail_prefill" not in result


# ---------------------------------------------------------------------------
# Property 9: 主 ∧ 子全开 + 明细空 → seed（复用既有归集不新造）
# ---------------------------------------------------------------------------


def test_both_on_empty_detail_seeds(monkeypatch):
    """主 ∧ 子全开 + D6-2 明细空 → detail_prefill 含归集行 + source="four-table"。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    aux = [
        _aux("客户A", prior=800.0, current=1000.0),
        _aux("客户B", prior=200.0, current=300.0),
    ]
    result = _run(d6.render(_ctx(_session(aux_rows=aux))))
    assert "detail_prefill" in result
    prefill = result["detail_prefill"]
    assert isinstance(prefill, list)
    assert len(prefill) == 2
    # 归集 30 列 schema + source 标注
    first = prefill[0]
    assert first["source"] == "four-table"
    assert first["customerName"] == "客户A"
    assert first["contractName"] == "客户A"
    assert first["priorUnadjusted"] == 800.0
    assert first["endUnadjusted"] == 1000.0
    assert first["seqNo"] == 1
    # additive：既有键保留
    assert _BASELINE_KEYS.issubset(set(result.keys()))


def test_both_on_no_aux_data_no_seed(monkeypatch):
    """主 ∧ 子全开 + tb_aux_balance 无归集数据 → 无 detail_prefill（不阻断 render）。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    result = _run(d6.render(_ctx(_session(aux_rows=[]))))
    assert "detail_prefill" not in result
    assert _BASELINE_KEYS.issubset(set(result.keys()))


# ---------------------------------------------------------------------------
# Property 8: 手工优先（D6-2 已有行 → 不 seed）
# ---------------------------------------------------------------------------


def test_both_on_existing_rows_no_seed(monkeypatch):
    """D6-2-rows 非空数组（已有行）→ 不 seed（手工优先，不覆盖 / R4.2）。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    checklist = [
        _checklist_row("D6-2-rows", remark='[{"rowId":"r1","customerName":"手工客户"}]'),
    ]
    result = _run(
        d6.render(_ctx(_session(checklist_rows=checklist, aux_rows=[_aux("客户A", current=999.0)])))
    )
    assert "detail_prefill" not in result


def test_both_on_empty_array_marker_seeds(monkeypatch):
    """D6-2-rows = "[]"（空数组标记）→ 视为空 → 仍 seed。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    checklist = [_checklist_row("D6-2-rows", remark="[]")]
    result = _run(
        d6.render(_ctx(_session(checklist_rows=checklist, aux_rows=[_aux("客户A", current=999.0)])))
    )
    assert "detail_prefill" in result
    assert len(result["detail_prefill"]) == 1


# ---------------------------------------------------------------------------
# Property 11: fail-open（归集异常 → 空 seed，不阻断 render）
# ---------------------------------------------------------------------------


def test_aggregation_error_fails_open(monkeypatch):
    """主 ∧ 子全开 + tb_aux_balance 查询异常 → fail-open（省略 detail_prefill，render 正常）。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    result = _run(d6.render(_ctx(_session(aux_rows=[], raise_on_aux=True))))
    assert "detail_prefill" not in result
    # render 未被阻断：基线键齐全
    assert _BASELINE_KEYS.issubset(set(result.keys()))


# ---------------------------------------------------------------------------
# Property 13: transient 不落库（render 全程无 checklist_responses 写库）
# ---------------------------------------------------------------------------


def test_detail_seed_transient_not_persisted(monkeypatch):
    """detail_prefill 只进返回 payload；render 全程无 INSERT/UPDATE/DELETE（不落库）。"""
    _main_on(monkeypatch)
    _sub_on(monkeypatch)
    session = _session(aux_rows=[_aux("客户A", current=1000.0)])
    result = _run(d6.render(_ctx(session)))
    assert "detail_prefill" in result  # seed 生效
    # render 执行的 SQL 全为只读 SELECT，无任何写库
    for sql in session.executed_sql:
        low = sql.lower().strip()
        assert not low.startswith("insert"), f"render 不应 INSERT（transient 不落库）: {sql}"
        assert not low.startswith("update"), f"render 不应 UPDATE（transient 不落库）: {sql}"
        assert not low.startswith("delete"), f"render 不应 DELETE（transient 不落库）: {sql}"


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
