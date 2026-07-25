"""Wave 1 / Task 2.1 —— D6 render 接入 Tier B `adjudication_prefill` 集成测试.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/
      (Requirements 1.1, 1.5, 1.6, 2.3, 7.1, 7.2 / Property 2, 9)

覆盖：
  * **Property 9（灰度零回归）**：开关关闭（默认）时 `_d6_contract_assets.render` 顶层键
    与 characterization 基线逐字节等价，**不含** `adjudication_prefill`。
  * **开关开启 + block1 空** → 返回 `adjudication_prefill`（叶子子科目行，附 source 标注），
    映射 opening/closing → 期初/期末未审（block1 原值）。
  * **Property 2（手工优先）**：block1 已有非空未审数据（`responses_snapshot` 含
    `D6-1-adj-block1-*-currentUnadjusted` 或 `rowKeys` 非空）时 **不** 返回 adjudication_prefill，
    不覆盖手工/既有一键取数结果。
  * 叶子防双算在 render 集成链路生效（Property 1 复用）。
  * 无子科目 / 取数异常 → fail-open（省略 adjudication_prefill，不阻断 render，Property 4）。

fake async session 按 SQL 文本路由；prefill 的 `get_active_filter` 经 monkeypatch 隔离，
tb_balance 叶子行由 fake session 回 `SELECT ... FROM tb_balance`。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.routers.wp_render_strategies import _d6_contract_assets as d6
from app.services.d_cycle_extraction import prefill as prefill_mod

# characterization 基线顶层键（见 test_d6_d2_render_characterization.py）
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
# Fake async DB —— 按 SQL 文本路由（tb_balance 叶子查询 + 既有 D6 查询）
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
        tb_balance_rows=None,
        raise_on_tb_balance=False,
    ):
        self.checklist_rows = checklist_rows or []
        self.project_row = project_row
        self.tb_row = tb_row
        self.rp_rows = rp_rows or []
        self.tb_balance_rows = tb_balance_rows or []
        self.raise_on_tb_balance = raise_on_tb_balance

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        # prefill 的叶子查询：SELECT ... FROM tb_balance（先于 trial_balance 判定，二者不互为子串）
        if "tb_balance" in s and "trial_balance" not in s:
            if self.raise_on_tb_balance:
                raise RuntimeError("tb_balance boom")
            return _FakeResult(rows=self.tb_balance_rows)
        if "checklist_responses" in s:
            return _FakeResult(rows=self.checklist_rows)
        if "related_party_registry" in s:
            return _FakeResult(rows=self.rp_rows)
        if "trial_balance" in s:
            return _FakeResult(one=self.tb_row)
        if "from projects" in s or "projects where" in s:
            return _FakeResult(one=self.project_row)
        return _FakeResult()

    async def rollback(self):
        return None


def _checklist_row(item_id: str, conclusion: str = "", remark: str = ""):
    return SimpleNamespace(item_id=item_id, conclusion=conclusion, remark=remark)


def _tb_leaf(code, name, *, opening=0.0, closing=0.0, debit=0.0, credit=0.0):
    """prefill 叶子查询返回行（labels: code/name/opening/closing/debit/credit）。"""
    return SimpleNamespace(
        code=code, name=name, opening=opening, closing=closing, debit=debit, credit=credit
    )


def _ctx(db):
    return SimpleNamespace(
        db=db,
        wp_id=uuid4(),
        project_id=uuid4(),
        year=2025,
        business_category="general",
        classification=SimpleNamespace(sheet_name="合同资产审定表D6-1"),
    )


def _session(*, checklist_rows=None, tb_balance_rows=None, raise_on_tb_balance=False):
    return _FakeSession(
        checklist_rows=checklist_rows or [],
        project_row=SimpleNamespace(
            client_name="测试客户",
            audit_year=2025,
            business_category="general",
            applicable_standards="listed",
        ),
        tb_row=SimpleNamespace(amount=98765.43),
        rp_rows=[SimpleNamespace(name="关联方甲", relation_type="subsidiary")],
        tb_balance_rows=tb_balance_rows or [],
        raise_on_tb_balance=raise_on_tb_balance,
    )


def _patch_active_filter(monkeypatch):
    import sqlalchemy as sa

    async def _fake_filter(db, table, project_id, year, **kw):
        return sa.true()

    monkeypatch.setattr(prefill_mod, "get_active_filter", _fake_filter)


def _enable_flag(monkeypatch):
    monkeypatch.setattr(d6.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)


def _disable_flag(monkeypatch):
    monkeypatch.setattr(d6.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)


# ---------------------------------------------------------------------------
# Property 9: 灰度关闭零回归
# ---------------------------------------------------------------------------


def test_flag_off_no_prefill_baseline_equivalent(monkeypatch):
    """开关关闭（默认）→ 顶层键 == characterization 基线，无 adjudication_prefill。"""
    _disable_flag(monkeypatch)
    result = _run(d6.render(_ctx(_session())))
    assert set(result.keys()) == _BASELINE_KEYS
    assert "adjudication_prefill" not in result


def test_flag_off_ignores_tb_balance_rows(monkeypatch):
    """开关关闭时，即便 tb_balance 有叶子子科目，也不返回 adjudication_prefill。"""
    _disable_flag(monkeypatch)
    _patch_active_filter(monkeypatch)
    rows = [_tb_leaf("1402.01", "合同资产-明细", opening=800.0, closing=1000.0)]
    result = _run(d6.render(_ctx(_session(tb_balance_rows=rows))))
    assert "adjudication_prefill" not in result


# ---------------------------------------------------------------------------
# 开关开启 + block1 空 → 返回 adjudication_prefill
# ---------------------------------------------------------------------------


def test_flag_on_returns_prefill_rows(monkeypatch):
    """开关开启 + block1 空 → adjudication_prefill 含叶子行（opening/closing + source）。"""
    _enable_flag(monkeypatch)
    _patch_active_filter(monkeypatch)
    rows = [
        _tb_leaf("1402.01", "工程类合同资产", opening=800.0, closing=1000.0),
        _tb_leaf("1402.02", "服务类合同资产", opening=200.0, closing=300.0),
    ]
    result = _run(d6.render(_ctx(_session(tb_balance_rows=rows))))
    assert "adjudication_prefill" in result
    prefill = result["adjudication_prefill"]
    assert isinstance(prefill, list)
    assert len(prefill) == 2
    # 按 abs(closing) 降序
    assert [r["code"] for r in prefill] == ["1402.01", "1402.02"]
    first = prefill[0]
    assert first["name"] == "工程类合同资产"
    assert first["opening_balance"] == 800.0
    assert first["closing_balance"] == 1000.0
    # 来源标注 + block1 目标（供前端 seed 原值期初/期末未审）
    assert first["source"] == "four-table"
    assert first["block"] == "block1"
    # additive：既有键保留
    assert _BASELINE_KEYS.issubset(set(result.keys()))


def test_flag_on_leaf_only_no_double_count(monkeypatch):
    """render 集成链路叶子防双算（Property 1 复用）：中间级 rollup 不入 prefill。"""
    _enable_flag(monkeypatch)
    _patch_active_filter(monkeypatch)
    rows = [
        _tb_leaf("1402.01", "合同资产-中间级", opening=800.0, closing=1000.0),
        _tb_leaf("1402.01.01", "合同资产-明细", opening=800.0, closing=1000.0),
    ]
    result = _run(d6.render(_ctx(_session(tb_balance_rows=rows))))
    prefill = result["adjudication_prefill"]
    assert len(prefill) == 1
    assert prefill[0]["code"] == "1402.01.01"
    assert sum(r["closing_balance"] for r in prefill) == 1000.0


def test_flag_on_no_subaccounts_fails_open(monkeypatch):
    """开关开 + tb_balance 无子科目 → 无 adjudication_prefill（Property 4，不阻断）。"""
    _enable_flag(monkeypatch)
    _patch_active_filter(monkeypatch)
    result = _run(d6.render(_ctx(_session(tb_balance_rows=[]))))
    assert "adjudication_prefill" not in result
    assert _BASELINE_KEYS.issubset(set(result.keys()))


def test_flag_on_tb_balance_error_fails_open(monkeypatch):
    """开关开 + tb_balance 查询异常 → fail-open（省略 adjudication_prefill，render 正常）。"""
    _enable_flag(monkeypatch)
    _patch_active_filter(monkeypatch)
    result = _run(d6.render(_ctx(_session(raise_on_tb_balance=True))))
    assert "adjudication_prefill" not in result
    assert set(result.keys()) == _BASELINE_KEYS


# ---------------------------------------------------------------------------
# Property 2: 手工优先（block1 已有未审数据 → 不覆盖）
# ---------------------------------------------------------------------------


def test_property2_existing_perfield_unadjusted_blocks_prefill(monkeypatch):
    """block1 某行已有 currentUnadjusted 非空 → 不返回 adjudication_prefill（手工优先）。"""
    _enable_flag(monkeypatch)
    _patch_active_filter(monkeypatch)
    rows = [_tb_leaf("1402.01", "工程类合同资产", opening=800.0, closing=1000.0)]
    checklist = [
        _checklist_row("D6-1-adj-block1-row-abc-currentUnadjusted", remark="500000"),
    ]
    result = _run(
        d6.render(_ctx(_session(checklist_rows=checklist, tb_balance_rows=rows)))
    )
    assert "adjudication_prefill" not in result


def test_property2_existing_rowkeys_blocks_prefill(monkeypatch):
    """block1 行键清单非空 → 视为已建行 → 不预填。"""
    _enable_flag(monkeypatch)
    _patch_active_filter(monkeypatch)
    rows = [_tb_leaf("1402.01", "工程类合同资产", opening=800.0, closing=1000.0)]
    checklist = [
        _checklist_row("D6-1-adj-block1-rowKeys", remark='["row-abc","row-def"]'),
    ]
    result = _run(
        d6.render(_ctx(_session(checklist_rows=checklist, tb_balance_rows=rows)))
    )
    assert "adjudication_prefill" not in result


def test_property2_empty_rowkeys_does_not_block(monkeypatch):
    """block1 行键清单为空数组 → 视为未填 → 仍预填。"""
    _enable_flag(monkeypatch)
    _patch_active_filter(monkeypatch)
    rows = [_tb_leaf("1402.01", "工程类合同资产", opening=800.0, closing=1000.0)]
    checklist = [_checklist_row("D6-1-adj-block1-rowKeys", remark="[]")]
    result = _run(
        d6.render(_ctx(_session(checklist_rows=checklist, tb_balance_rows=rows)))
    )
    assert "adjudication_prefill" in result
    assert len(result["adjudication_prefill"]) == 1


def test_property2_block2_or_note_data_does_not_block(monkeypatch):
    """block2（坏账准备）/ note 文本已填不影响 block1 原值预填（手工优先仅针对 block1）。"""
    _enable_flag(monkeypatch)
    _patch_active_filter(monkeypatch)
    rows = [_tb_leaf("1402.01", "工程类合同资产", opening=800.0, closing=1000.0)]
    checklist = [
        _checklist_row("D6-1-adj-block2-row-x-currentUnadjusted", remark="123"),
        _checklist_row("D6-1-note-conclusion", remark="结论文本"),
        _checklist_row("D6-1-tb-amount", remark="98765.43"),
    ]
    result = _run(
        d6.render(_ctx(_session(checklist_rows=checklist, tb_balance_rows=rows)))
    )
    assert "adjudication_prefill" in result
    assert len(result["adjudication_prefill"]) == 1


def test_property2_block1_adjustment_only_still_prefills(monkeypatch):
    """block1 仅有 AJE/RJE（调整）而无未审数 → 不算「已填未审」→ 仍预填。

    手工优先只看原值未审（priorUnadjusted/currentUnadjusted），审计判断调整不阻断。
    """
    _enable_flag(monkeypatch)
    _patch_active_filter(monkeypatch)
    rows = [_tb_leaf("1402.01", "工程类合同资产", opening=800.0, closing=1000.0)]
    checklist = [
        _checklist_row("D6-1-adj-block1-row-abc-currentAje", remark="100"),
    ]
    result = _run(
        d6.render(_ctx(_session(checklist_rows=checklist, tb_balance_rows=rows)))
    )
    assert "adjudication_prefill" in result
