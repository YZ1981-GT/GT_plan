"""Wave 0 / Task 1.1 —— D6/D2 render 零回归 characterization 基线 + prefill 范式确认.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/  (Requirements 7.1, 7.3)

本文件锁定两件事，作为后续接入 Tier B 预填 + Tier A 公式前的**零回归基线**：

1. **characterization 基线**：锁定当前 D6(`_d6_contract_assets.render`) 与
   D2(`_d2_accounts_receivable.render`) 的返回**键/形状**（sections / adjudication_config /
   ecl_config / project_context[含 tb_amount] / disclosure_visibility / responses_snapshot 等）。
   关键断言：当前 D6/D2 **均未返回 `adjudication_prefill`**（这正是本 spec Req1 要补齐的缺口）。
   接入本 spec 后、灰度开关 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED=False` 时，render 必须与此
   基线逐字节等价（Property 9 / Req7.1）。

2. **`_build_adjudication_prefill` 范式确认（Deliverable 3）**：确认并文档化 K9/K1/N5 三处已证明
   的审定表预填范式——D1–D7 将镜像它（决策1 / 收敛铁律，不造第 3 套四表库读取）：

       async def _build_adjudication_prefill(ctx: RenderContext) -> list | dict | None:
           # ① get_active_filter(db, TbBalance.__table__, project_id, year)  —— 数据集版本过滤
           #    （canonical 异步 4 参签名，K9/K1 用法权威；N5 的 get_active_filter(project_id)
           #     是发散/降级写法，包在 try/except 内，不作为镜像对象）
           # ② 只取叶子子科目（account_code != 前缀 且 非其它 code 前缀）—— 防中间级 rollup 双算
           # ③ 手工优先 —— 仅 checklist_responses 无非空用户值时预填，不覆盖已录入
           # ④ 余额类取 opening/closing_balance；发生额类取 debit/credit_amount
           # ⑤ render 返回 `adjudication_prefill`，前端专属组件无持久化行时据此 seed

   本模块以断言（三处 render 模块均暴露 `_build_adjudication_prefill` 且导入 `get_active_filter`）
   把该范式钉死为参照，防止 D1–D7 接入时偏离。

测试用 fake async session（不依赖真实 PG / SQLite），仅按 SQL 文本路由预置行。
D6/D2 render 均直接用 sa.text 查 trial_balance/projects/related_party_registry，
不经 get_active_filter，故无需 monkeypatch。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.routers.wp_render_strategies import (
    _d2_accounts_receivable as d2,
    _d6_contract_assets as d6,
)


# ---------------------------------------------------------------------------
# Fake async DB —— 按 SQL 文本路由返回可编程结果（对齐 test_f2_render_prefill 约定）
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
    """拦截 execute()，按语句文本返回预置行。"""

    def __init__(self, *, checklist_rows=None, project_row=None, tb_row=None, rp_rows=None):
        self.checklist_rows = checklist_rows or []
        self.project_row = project_row
        self.tb_row = tb_row
        self.rp_rows = rp_rows or []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
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


def _ctx(db):
    return SimpleNamespace(
        db=db,
        wp_id=uuid4(),
        project_id=uuid4(),
        year=2025,
        business_category="general",
        classification=SimpleNamespace(sheet_name="合同资产审定表D6-1"),
    )


def _run(coro):
    return asyncio.run(coro)


def _d6_session():
    return _FakeSession(
        checklist_rows=[_checklist_row("D6-1-block1-endUnadjusted", remark="123.45")],
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
    )


def _d2_session():
    return _FakeSession(
        checklist_rows=[_checklist_row("D2-1-total", remark="1000")],
        project_row=SimpleNamespace(
            client_name="测试客户", audit_year=2025, business_category="general"
        ),
        rp_rows=[SimpleNamespace(name="关联方乙")],
    )


# ---------------------------------------------------------------------------
# D6 characterization 基线
# ---------------------------------------------------------------------------


def test_d6_render_top_level_keys_baseline():
    """D6 render 顶层键锁定（零回归基线）——尚无 adjudication_prefill。

    ⚠️ 本用例**不显式设灰度开关**，故键集随环境（本地 `.env` 置 True）。
    d-cycle-four-table-extraction-and-disclosure-completion R1 起，灰度开时额外输出
    两个 additive 溯源键 `tb_source_codes` / `parent_check`，两者用可选集合表达
    以便本用例在开/关两种环境下都成立。
    """
    result = _run(d6.render(_ctx(_d6_session())))
    base = {
        "sections",
        "adjudication_config",
        "ecl_config",
        "project_context",
        "disclosure_visibility",
        "responses_snapshot",
    }
    optional = {"tb_source_codes", "parent_check"}
    keys = set(result.keys())
    assert base <= keys, "基线键缺失: %s" % (base - keys)
    assert keys - base <= optional, "出现未登记的新增键: %s" % (keys - base - optional)
    # 本 spec Req1 的核心缺口：当前 D6 未返回 adjudication_prefill（接入后灰度关时仍应缺席）
    assert "adjudication_prefill" not in result


def test_d6_render_adjudication_config_shape():
    """审定表三区块固定行结构 + 12 列（合同资产原值/坏账准备/净值）。"""
    result = _run(d6.render(_ctx(_d6_session())))
    cfg = result["adjudication_config"]
    assert [b["blockKey"] for b in cfg["blocks"]] == ["block1", "block2", "block3"]
    assert len(cfg["columns"]) == 12
    assert cfg["columns"][0] == "项目"


def test_d6_render_sections_count():
    """12 个 sheet（程序表 + 审定表 + 明细 + 减值 + ... + 双附注）。"""
    result = _run(d6.render(_ctx(_d6_session())))
    assert len(result["sections"]) == 12
    codes = [s["code"] for s in result["sections"]]
    assert codes[:3] == ["D6A", "D6-1", "D6-2"]


def test_d6_render_project_context_keys():
    """project_context 含 tb_amount / bs_date / related_parties 等（后续 TB↔审定核对依赖）。"""
    result = _run(d6.render(_ctx(_d6_session())))
    pc = result["project_context"]
    for key in (
        "client_name",
        "audit_year",
        "business_category",
        "applicable_standards",
        "bs_date",
        "tb_amount",
        "related_parties",
    ):
        assert key in pc, f"project_context 缺键 {key}"
    assert pc["tb_amount"] == pytest.approx(98765.43)
    assert pc["bs_date"] == "2025-12-31"
    assert pc["related_parties"] == [{"name": "关联方甲", "type": "subsidiary"}]


def test_d6_render_disclosure_visibility_and_snapshot():
    """disclosure_visibility 由 applicable_standards 派生；responses_snapshot 回显 checklist。"""
    result = _run(d6.render(_ctx(_d6_session())))
    assert result["disclosure_visibility"] == {"listed": True, "soe": False}
    snap = result["responses_snapshot"]
    assert "D6-1-block1-endUnadjusted" in snap
    assert snap["D6-1-block1-endUnadjusted"]["remark"] == "123.45"


# ---------------------------------------------------------------------------
# D2 characterization 基线
# ---------------------------------------------------------------------------


def test_d2_render_top_level_keys_baseline():
    """D2 render 顶层键锁定（灰度**关**时）——无 adjudication_prefill / 无 tb_source_codes。"""
    from app.core.config import settings
    old = settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED
    try:
        settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED = False
        result = _run(d2.render(_ctx(_d2_session())))
    finally:
        settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED = old
    assert set(result.keys()) == {"sheet_name", "project_context", "responses_snapshot"}
    assert "adjudication_prefill" not in result


def test_d2_render_project_context_and_snapshot():
    """project_context 含 bs_date / related_parties；responses_snapshot 回显。"""
    result = _run(d2.render(_ctx(_d2_session())))
    pc = result["project_context"]
    for key in ("client_name", "audit_year", "business_category", "bs_date", "related_parties"):
        assert key in pc, f"project_context 缺键 {key}"
    assert pc["bs_date"] == "2025-12-31"
    assert pc["related_parties"] == ["关联方乙"]
    assert "D2-1-total" in result["responses_snapshot"]


def test_d2_render_sheet_name_from_classification():
    """sheet_name 来自 ctx.classification.sheet_name。"""
    result = _run(d2.render(_ctx(_d2_session())))
    assert result["sheet_name"] == "合同资产审定表D6-1"  # 由 _ctx 注入的 classification


# ---------------------------------------------------------------------------
# Deliverable 3 —— `_build_adjudication_prefill` 范式确认（K9/K1/N5 参照钉死）
# ---------------------------------------------------------------------------


def test_reference_prefill_pattern_exists_k9_k1_n5():
    """确认平台仍存在「审定表预填」范式函数 `_build_adjudication_prefill`（D1–D7 参照）。

    范式：render 内 `_build_adjudication_prefill(...)` —— tb_balance 叶子级 SUM +
    手工优先 + 返回 adjudication_prefill。此断言防平台整体丢失该范式。

    🔴 基准模块由 `(k9, k1, n5)` 改为 `(k1, n5, n1)`：**K9 已重构走共享件
    `four_table/pl_render`**（损益类不再 in-module 造 `_build_adjudication_prefill`），
    继续拿它当基准会恒红。K1/N5/N1 仍保留 in-module 范式，是活样本。
    """
    from app.routers.wp_render_strategies import (
        _k1_other_receivables as k1,
        _n1_deferred_tax_assets as n1,
        _n5_income_tax_expense as n5,
    )

    for mod in (k1, n5, n1):
        fn = getattr(mod, "_build_adjudication_prefill", None)
        assert callable(fn), f"{mod.__name__} 缺 _build_adjudication_prefill（范式基准）"


def test_reference_prefill_uses_active_filter():
    """确认 canonical 模块在 render 内绑定 get_active_filter（数据集版本过滤，禁裸 is_deleted）。

    用 `await get_active_filter(ctx.db, TbBalance.__table__, ctx.project_id, ctx.year)`
    —— 这是 D1–D7 应镜像的权威口径。

    🔴 基准由 `(k9, k1)` 改为 `(k1, k2)`：**K9 已重构走 `pl_render`**，其 render 模块
    不再直接 import get_active_filter；K1/K2 仍是 in-module 取数的活样本。
    """
    from app.routers.wp_render_strategies import (
        _k1_other_receivables as k1,
        _k2_other_current_assets as k2,
    )

    for mod in (k1, k2):
        assert hasattr(mod, "get_active_filter"), (
            f"{mod.__name__} 未导入 get_active_filter（Tier B 四表库统一读入口）"
        )
