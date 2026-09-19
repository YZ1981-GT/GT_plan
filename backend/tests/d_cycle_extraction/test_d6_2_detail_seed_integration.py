"""Wave 5 / Task 5.1 —— D6-2 明细表维度归集 render **transient 自动 seed** 集成测试.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/
      (Requirements 4.1–4.7, 5.2, 5.3 / Property 8, 9, 11, 13)

D6 render 在**主开关 ∧ 子开关**（`D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` ∧
`D_CYCLE_DETAIL_SEED_ENABLED`）均开、且 D6-2 明细表**完全空**时，调既有可复用归集
`aggregate_d6_detail_rows`（tb_aux_balance 1141 客户/合同维度，Wave0 抽取的纯函数入口，
复用不新造第 3 套四表库读取）**transient seed** 明细行进 render 返回 `detail_prefill`
——只进返回 payload、**不落 checklist_responses/DB**（对齐 D6 Tier B `adjudication_prefill`）。

覆盖：
  * **Property 8（手工优先 + 子开关门控）**：主 ∧ 子开关 ∧ 明细完全空 → seed；
    D6-2 已有任一行 → 不 seed（不覆盖手工/既有一键取数）；子开关关 → 无 detail seed；
    主开关关（即便子开关开）→ 无 detail seed（被主开关 AND / "发 P0-1、压 P0-2"）。
  * **Property 9（复用既有函数不新造）**：seed 调 `aggregate_d6_detail_rows`（既有归集），
    SQL 命中 tb_aux_balance + 1141（原端点逐字节相同的复用聚合，非新造读取）。
  * **Property 11（fail-open）**：归集查询异常 / 无 aux 数据 → 无 detail_prefill，render 正常。
  * **Property 13（seed 全程 transient 不落库）**：detail seed 只进返回 detail_prefill，
    fake session 无任何 INSERT/UPDATE 写。

fake async session 按 SQL 文本路由（tb_aux_balance 归集查询优先于其它）；Tier A seed 经
monkeypatch `d6.resolve_effective` 置空隔离、Tier B `get_active_filter` monkeypatch + 空
tb_balance 隔离，使 detail seed 断言不受 P0-1/Tier B 干扰。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.routers.wp_render_strategies import _d6_contract_assets as d6
from app.services.d_cycle_extraction import prefill as prefill_mod

_DETAIL_ITEM_ID = "D6-2-rows"


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake async DB —— 按 SQL 文本路由（tb_aux_balance 归集 + 既有 D6 查询）
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
        aux_rows=None,
        raise_on_aux=False,
    ):
        self.checklist_rows = checklist_rows or []
        self.project_row = project_row
        self.tb_row = tb_row
        self.aux_rows = aux_rows or []
        self.raise_on_aux = raise_on_aux
        self.executed_sql: list[str] = []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        self.executed_sql.append(s)
        # 归集查询：tb_aux_balance（先于 tb_balance/trial_balance 判定；三者互不为子串）
        if "tb_aux_balance" in s:
            if self.raise_on_aux:
                raise RuntimeError("tb_aux_balance boom")
            return _FakeResult(rows=self.aux_rows)
        # Tier B 叶子查询：tb_balance（置空隔离，不干扰 detail seed 断言）
        if "tb_balance" in s and "trial_balance" not in s:
            return _FakeResult(rows=[])
        if "checklist_responses" in s:
            return _FakeResult(rows=self.checklist_rows)
        if "related_party_registry" in s:
            return _FakeResult(rows=[])
        if "trial_balance" in s:
            return _FakeResult(one=self.tb_row)
        if "from projects" in s or "projects where" in s:
            return _FakeResult(one=self.project_row)
        return _FakeResult()

    async def rollback(self):
        return None


def _checklist_row(item_id: str, conclusion: str = "", remark: str = ""):
    return SimpleNamespace(item_id=item_id, conclusion=conclusion, remark=remark)


def _aux_row(aux_name, prior, current):
    """tb_aux_balance 1141 归集行（labels: aux_name/prior_balance/current_balance）。"""
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
        aux_rows=aux_rows or [],
        raise_on_aux=raise_on_aux,
    )


def _isolate_p0_1(monkeypatch):
    """隔离 P0-1（Tier A seed）+ Tier B prefill，使 detail seed 断言不受干扰。"""
    import sqlalchemy as sa

    async def _empty_resolve(db, wp_id, wp_code, project_id):
        return []

    async def _fake_filter(db, table, project_id, year, **kw):
        return sa.true()

    monkeypatch.setattr(d6, "resolve_effective", _empty_resolve)
    monkeypatch.setattr(prefill_mod, "get_active_filter", _fake_filter)


def _set_gates(monkeypatch, *, main: bool, sub: bool):
    monkeypatch.setattr(d6.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", main)
    monkeypatch.setattr(d6.settings, "D_CYCLE_DETAIL_SEED_ENABLED", sub)


_AUX = [_aux_row("客户甲合同", 1000.0, 1500.0), _aux_row("客户乙合同", 0.0, 500.0)]


# ---------------------------------------------------------------------------
# Property 8 / 10: 子开关门控（主 ∧ 子 才 seed）
# ---------------------------------------------------------------------------


def test_both_gates_off_no_detail_seed(monkeypatch):
    """主关 + 子关（默认）→ 无 detail_prefill（零回归）。"""
    _set_gates(monkeypatch, main=False, sub=False)
    _isolate_p0_1(monkeypatch)
    result = _run(d6.render(_ctx(_session(aux_rows=_AUX))))
    assert "detail_prefill" not in result


def test_main_off_sub_on_no_detail_seed(monkeypatch):
    """主关 + 子开（子被主 AND）→ 无 detail_prefill（"发 P0-1、压 P0-2" 的反向）。"""
    _set_gates(monkeypatch, main=False, sub=True)
    _isolate_p0_1(monkeypatch)
    result = _run(d6.render(_ctx(_session(aux_rows=_AUX))))
    assert "detail_prefill" not in result


def test_main_on_sub_off_no_detail_seed(monkeypatch):
    """主开 + 子关 → 无 detail_prefill（可"发 P0-1、压 P0-2" / Property 8 / R5.2）。"""
    _set_gates(monkeypatch, main=True, sub=False)
    _isolate_p0_1(monkeypatch)
    result = _run(d6.render(_ctx(_session(aux_rows=_AUX))))
    assert "detail_prefill" not in result


# ---------------------------------------------------------------------------
# Property 8: 主 ∧ 子 + 明细空 → seed；已有行 → 不 seed（手工优先）
# ---------------------------------------------------------------------------


def test_both_on_empty_detail_seeds(monkeypatch):
    """主 ∧ 子开 + 明细完全空 → detail_prefill 含归集明细行（附 source=four-table）。"""
    _set_gates(monkeypatch, main=True, sub=True)
    _isolate_p0_1(monkeypatch)
    result = _run(d6.render(_ctx(_session(aux_rows=_AUX))))
    assert "detail_prefill" in result
    detail = result["detail_prefill"]
    assert isinstance(detail, list)
    assert len(detail) == 2
    # 保持归集顺序 + 字段映射
    assert [r["contractName"] for r in detail] == ["客户甲合同", "客户乙合同"]
    assert detail[0]["priorUnadjusted"] == 1000.0
    assert detail[0]["endUnadjusted"] == 1500.0
    assert detail[1]["endUnadjusted"] == 500.0
    # 来源标注（供前端识别为自动取数）
    assert all(r["source"] == "four-table" for r in detail)
    # 30 列 schema 完整（含来源标注共 31 键）
    assert "seqNo" in detail[0] and "creditRiskGroup" in detail[0]


def test_both_on_existing_rows_no_seed(monkeypatch):
    """D6-2 已有行（非空 JSON 数组）→ 不 seed（手工优先 / Property 8 / R4.2）。"""
    _set_gates(monkeypatch, main=True, sub=True)
    _isolate_p0_1(monkeypatch)
    checklist = [
        _checklist_row(
            _DETAIL_ITEM_ID, remark='[{"rowId":"r1","contractName":"手工录入合同"}]'
        )
    ]
    result = _run(
        d6.render(_ctx(_session(checklist_rows=checklist, aux_rows=_AUX)))
    )
    assert "detail_prefill" not in result


def test_both_on_empty_array_rows_still_seeds(monkeypatch):
    """D6-2-rows 为空数组 "[]" → 视为未填 → 仍 seed。"""
    _set_gates(monkeypatch, main=True, sub=True)
    _isolate_p0_1(monkeypatch)
    checklist = [_checklist_row(_DETAIL_ITEM_ID, remark="[]")]
    result = _run(
        d6.render(_ctx(_session(checklist_rows=checklist, aux_rows=_AUX)))
    )
    assert "detail_prefill" in result
    assert len(result["detail_prefill"]) == 2


# ---------------------------------------------------------------------------
# Property 9: 复用既有归集函数不新造第 3 套四表库读取
# ---------------------------------------------------------------------------


def test_detail_seed_reuses_aggregate_function(monkeypatch):
    """seed 调既有 aggregate_d6_detail_rows（复用不新造 / Property 9 / R4.3, R4.4）。"""
    _set_gates(monkeypatch, main=True, sub=True)
    _isolate_p0_1(monkeypatch)
    called: dict = {}
    orig = d6.aggregate_d6_detail_rows

    async def _spy(db, project_id, **kw):
        called["hit"] = True
        called["project_id"] = project_id
        return await orig(db, project_id, **kw)

    monkeypatch.setattr(d6, "aggregate_d6_detail_rows", _spy)
    db = _session(aux_rows=_AUX)
    result = _run(d6.render(_ctx(db)))
    assert called.get("hit") is True, "detail seed 必须调既有 aggregate_d6_detail_rows"
    assert "detail_prefill" in result
    # 复用既有归集 SQL（tb_aux_balance 1141），非新造第 3 套读取
    assert any("tb_aux_balance" in sql and "1141" in sql for sql in db.executed_sql)


# ---------------------------------------------------------------------------
# Property 11: fail-open（归集异常 / 无数据 → 无 detail_prefill，render 正常）
# ---------------------------------------------------------------------------


def test_aggregation_error_fails_open(monkeypatch):
    """归集查询异常 → fail-open（无 detail_prefill，render 正常返回）。"""
    _set_gates(monkeypatch, main=True, sub=True)
    _isolate_p0_1(monkeypatch)
    result = _run(d6.render(_ctx(_session(raise_on_aux=True))))
    assert "detail_prefill" not in result
    assert "project_context" in result  # render 正常


def test_no_aux_data_no_seed(monkeypatch):
    """无 1141 归集数据 → 无 detail_prefill（aggregate 返回 []，fail-open 空 / R4.5）。"""
    _set_gates(monkeypatch, main=True, sub=True)
    _isolate_p0_1(monkeypatch)
    result = _run(d6.render(_ctx(_session(aux_rows=[]))))
    assert "detail_prefill" not in result


# ---------------------------------------------------------------------------
# Property 13: seed 全程 transient 不落库
# ---------------------------------------------------------------------------


def test_detail_seed_transient_no_db_write(monkeypatch):
    """detail seed 只进返回 detail_prefill，无任何 checklist_responses/DB 写。"""
    _set_gates(monkeypatch, main=True, sub=True)
    _isolate_p0_1(monkeypatch)
    db = _session(aux_rows=_AUX)
    result = _run(d6.render(_ctx(db)))
    assert "detail_prefill" in result  # seed 生效（在返回 payload 中）
    assert all(
        ("insert" not in sql and "update" not in sql) for sql in db.executed_sql
    ), "detail transient seed 不得写 checklist_responses/DB（Property 13）"
