"""Wave 0 / Task 1.1 —— d-cycle-tier-a-writeback-detail-seed 零回归 characterization 基线.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/  (Requirements 1.6, 5.1, 5.2, 5.3)

本文件锁定本增量 spec 动手前的**当前行为基线**，作为 P0-1/P0-2 实现后的零回归对照：

1. **PUT /formulas auto_calc 走 write_cell_to_parsed_data**（Req1 缺口①的现状）：
   保存 auto_calc 公式时无条件调 `write_cell_to_parsed_data(cell_ref=target_cell)`，
   即便 target_cell 是 D-cycle 锚点（如 `D6-1-tb-amount`，专属组件读 checklist_responses
   而非 parsed_data 网格）也照写 → 写进组件永不读的网格。本 spec Wave1（Task 2.1）将改为
   对 D-cycle 锚点跳过此写并返回 evaluated_value。此基线锁定"改前照写网格"。

2. **GET /formulas 的 Tier A value 恒 None**（Req2 缺口②的现状）：
   `_build_extraction_block` 对每条 Tier A binding `setdefault("value", None)`，从不求值
   → 面板只显示表达式不显示求值结果。本 spec Wave2（Task 3.1）将填真实求值。此基线锁定
   "改前恒 None"。

3. **D6 render 现状（主开关关逐字节等价前置 spec）**：主开关关闭时 render 不含
   `adjudication_prefill` / `detail_prefill`，且无 Tier A transient seed（TB 核对行仍靠
   `project_context.tb_amount`）。本 spec Wave3/5 仅在主开关开时新增 seed。此基线锁定
   "主开关关 = 前置 spec 状态"。

4. **P0-2 子开关 `D_CYCLE_DETAIL_SEED_ENABLED` 默认 False + 被主开关 AND**（Req5.2）：
   新增配置默认关；确认默认（主关+子关）下不改任何现状（零回归），且生效条件 = 主 ∧ 子。

测试用 fake async session（不触发 conftest 真实 SQLite create_all），直接调 router 协程，
绕过 FastAPI Depends。灰度开关经 monkeypatch settings 翻转。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import Settings, settings
from app.routers import wp_formula as router_mod
from app.routers.wp_render_strategies import _d6_contract_assets as d6
from app.services.d_cycle_extraction import presets as presets_mod
from app.services.d_cycle_extraction.presets import SOURCE_PRESET


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake async session（PUT 路径：working_paper / wp_index / wp_formula + commit）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _FakeSession:
    def __init__(self, *, wp, wp_code, user_formulas=None, project_year=None):
        self.wp = wp
        self.wp_code = wp_code
        self.user_formulas = user_formulas or []
        # d-cycle-tier-a-writeback-detail-seed Task 3.1：GET Tier A 求值需 projects.audit_year。
        self.project_year = project_year
        self.committed = False

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        if "from wp_index" in s:
            return _FakeResult(scalar=self.wp_code)
        if "from wp_formula" in s:
            return _FakeResult(rows=self.user_formulas)
        if "from projects" in s:
            return _FakeResult(scalar=self.project_year)
        if "from working_paper" in s:
            if "is_deleted" in s:
                return _FakeResult(scalar=self.wp)
            return _FakeResult(scalar=self.wp.project_id)
        return _FakeResult()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None


def _wp():
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        wp_index_id=uuid4(),
        is_deleted=False,
        parsed_data={},
    )


def _saved_formula(target_cell, *, sheet_name="D6-1", wp=None,
                   formula_type="auto_calc", expression="TB('1141','期末余额')"):
    return SimpleNamespace(
        id=uuid4(),
        project_id=(wp.project_id if wp else uuid4()),
        wp_id=(wp.id if wp else uuid4()),
        sheet_name=sheet_name,
        target_cell=target_cell,
        expression=expression,
        category=None,
        description="用户公式",
        formula_type=formula_type,
        refs=None,
        issue_description=None,
        hint_text=None,
        # V104/V100 生命周期与来源字段（_formula_to_dict 会下发这三个键，
        # 缺则 AttributeError；值取 ORM server_default）
        lifecycle_state="saved",
        definition_version=1,
        formula_source="custom",
        last_computed_at=None,
        created_by=None,
        created_at=None,
        updated_at=None,
    )


def _user():
    return SimpleNamespace(id=uuid4(), username="tester")


def _enable(monkeypatch):
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)


def _disable(monkeypatch):
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)


def _patch_save_path(monkeypatch, *, saved, evaluated=123.45, eval_errors=None):
    """打通 PUT save 路径：过函数门 + 求值 + 记录 write_cell 调用 + 静默 linkage。"""
    monkeypatch.setattr(router_mod, "find_unsupported_formula_functions", lambda expr: [])

    async def _fake_save(*a, **kw):
        return saved, []

    monkeypatch.setattr(router_mod.wp_formula_service, "save", _fake_save)

    async def _fake_eval(*a, **kw):
        return evaluated, (eval_errors or [])

    monkeypatch.setattr(router_mod, "evaluate_wp_formula_expression", _fake_eval)

    calls: list[dict] = []

    def _spy_write(wp, *, sheet_name, cell_ref, value):
        calls.append({"sheet_name": sheet_name, "cell_ref": cell_ref, "value": value})

    monkeypatch.setattr(router_mod, "write_cell_to_parsed_data", _spy_write)

    async def _fake_linkage(*a, **kw):
        return None

    monkeypatch.setattr(
        "app.services.wp_formula_linkage_service.propagate_custom_wp_cell_change",
        _fake_linkage,
    )
    return calls


# ---------------------------------------------------------------------------
# 1. PUT auto_calc 当前走 write_cell_to_parsed_data（改前基线）
# ---------------------------------------------------------------------------


def test_put_auto_calc_currently_writes_parsed_data_for_d_cycle_anchor(monkeypatch):
    """零回归护栏：**主开关关**时保存 D-cycle 锚点 auto_calc
    公式仍照写 parsed_data 网格（前置 spec 状态逐字节等价）。

    Task 2.1 落地后仅在**主开关开**时才对 D-cycle 锚点跳过此写（见
    `test_put_auto_calc_dcycle_anchor_flag_gated_parsed_data_write`）；此处锁"主开关关零回归"。
    """
    _disable(monkeypatch)  # 显式关闭（.env 可能已设为 True，不依赖默认值）
    wp = _wp()
    saved = _saved_formula("D6-1-tb-amount", wp=wp)
    calls = _patch_save_path(monkeypatch, saved=saved, evaluated=98765.43)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])
    body = router_mod.FormulaSaveRequest(
        sheet_name="D6-1", target_cell="D6-1-tb-amount",
        expression="TB('1141','期末余额')", year=2025,
    )

    resp = _run(router_mod.save_formula(wp.id, body, db=db, user=_user()))

    # 当前：write_cell_to_parsed_data 被调用（写进网格），且 cell_ref = 锚点 target_cell
    assert len(calls) == 1
    assert calls[0]["cell_ref"] == "D6-1-tb-amount"
    assert calls[0]["sheet_name"] == "D6-1"
    # 响应含 evaluated_value（str 化）
    assert resp["evaluated_value"] == str(98765.43)
    assert db.committed is True


def test_put_auto_calc_dcycle_anchor_flag_gated_parsed_data_write(monkeypatch):
    """Task 2.1 落地后行为：D-cycle 锚点 auto_calc 保存的 parsed_data 写由主灰度开关门控。

    * 主开关**关**（默认）→ 仍照写 parsed_data（逐字节零回归，本 spec 主开关关 = 前置 spec 状态）。
    * 主开关**开** → 对 D-cycle 锚点**跳过** write_cell_to_parsed_data（决策1 / Property 1）。

    （原基线 `test_put_auto_calc_writes_parsed_data_regardless_of_flag` 锁"无灰度分支恒写"，
    Task 2.1 引入 is_known_anchor 路由后该假设已变，更新为门控行为，同时保住主开关关零回归。）
    """
    # 主开关关：D-cycle 锚点仍写 parsed_data（零回归）
    wp = _wp()
    saved = _saved_formula("D6-1-tb-amount", wp=wp)
    calls_off = _patch_save_path(monkeypatch, saved=saved)
    _disable(monkeypatch)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])
    body = router_mod.FormulaSaveRequest(
        sheet_name="D6-1", target_cell="D6-1-tb-amount",
        expression="TB('1141','期末余额')", year=2025,
    )
    _run(router_mod.save_formula(wp.id, body, db=db, user=_user()))
    assert len(calls_off) == 1, "主开关关时 D-cycle 锚点仍写 parsed_data（零回归）"

    # 主开关开：D-cycle 锚点跳过 parsed_data 写（决策1 / Property 1）
    wp2 = _wp()
    saved2 = _saved_formula("D6-1-tb-amount", wp=wp2)
    calls_on = _patch_save_path(monkeypatch, saved=saved2)
    _enable(monkeypatch)
    db2 = _FakeSession(wp=wp2, wp_code="D6", user_formulas=[])
    _run(router_mod.save_formula(wp2.id, body, db=db2, user=_user()))
    assert len(calls_on) == 0, "主开关开时 D-cycle 锚点跳过 parsed_data 写（决策1）"


def test_put_logic_check_does_not_write_parsed_data(monkeypatch):
    """基线：logic_check 类型不改值（不写网格），且响应无 evaluated_value（零回归护栏）。"""
    wp = _wp()
    saved = _saved_formula("D6-1-tb-amount", wp=wp, formula_type="logic_check")
    calls = _patch_save_path(monkeypatch, saved=saved)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])
    body = router_mod.FormulaSaveRequest(
        sheet_name="D6-1", target_cell="D6-1-tb-amount",
        expression="TB('1141','期末余额')", year=2025,
        formula_type="logic_check",
    )
    resp = _run(router_mod.save_formula(wp.id, body, db=db, user=_user()))
    assert calls == []
    assert "evaluated_value" not in resp


# ---------------------------------------------------------------------------
# 2. GET Tier A value 求值填充（Task 3.1 已落地 / R2）
# ---------------------------------------------------------------------------


def _get_session(wp, wp_code="D6", user_formulas=None, project_year=None):
    return _FakeSession(
        wp=wp, wp_code=wp_code, user_formulas=user_formulas or [],
        project_year=project_year,
    )


def _preset(anchor, *, sheet_name="D6-1", expression="TB('1141','期末余额')"):
    return {
        "wp_code": "D6", "sheet_name": sheet_name, "anchor": anchor,
        "expression": expression, "formula_type": "auto_calc",
        "description": "预设公式", "source": SOURCE_PRESET, "tier": "A",
    }


def test_get_tier_a_value_filled_when_year_and_eval_succeed(monkeypatch):
    """Task 3.1 落地后：flag ON + D6 + 可解析 audit_year + 求值成功 → Tier A value 填真实结果。

    （原基线锁"改前恒 None"，Task 3.1 已把 GET 改为逐条求值填 value；更新为"改后填值"。）
    """
    _enable(monkeypatch)
    wp = _wp()
    monkeypatch.setattr(
        presets_mod, "load_presets",
        lambda code: [dict(b) for b in ({"D6": [_preset("D6-1-tb-amount")]}).get(code, [])],
    )

    from decimal import Decimal

    async def _fake_eval(*a, **kw):
        return Decimal("123456.78"), []

    monkeypatch.setattr(router_mod, "evaluate_wp_formula_expression", _fake_eval)
    db = _get_session(wp, project_year=2025)

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    tier_a = resp["extraction"]["tierA"]
    assert tier_a, "D6 应有 Tier A 预设"
    b = tier_a[0]
    assert b["anchor"] == "D6-1-tb-amount"
    # format_cell_display_value(Decimal('123456.78')) → 123456.78（float，有小数）
    assert b["value"] == 123456.78


def test_get_tier_a_value_none_when_year_unresolvable(monkeypatch):
    """audit_year 拿不到（projects.audit_year 空）→ Tier A value=None（fail-open / R2.3）。"""
    _enable(monkeypatch)
    wp = _wp()
    monkeypatch.setattr(
        presets_mod, "load_presets",
        lambda code: [dict(b) for b in ({"D6": [_preset("D6-1-tb-amount")]}).get(code, [])],
    )
    db = _get_session(wp, project_year=None)  # 项目无 audit_year

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    tier_a = resp["extraction"]["tierA"]
    assert tier_a
    assert tier_a[0]["value"] is None


def test_get_tier_a_value_fail_open_on_eval_error(monkeypatch):
    """求值抛异常 → 该条 value=None（fail-open），不阻断 GET。"""
    _enable(monkeypatch)
    wp = _wp()
    monkeypatch.setattr(
        presets_mod, "load_presets",
        lambda code: [dict(b) for b in ({"D6": [_preset("D6-1-tb-amount")]}).get(code, [])],
    )

    async def _boom(*a, **kw):
        raise RuntimeError("eval boom")

    monkeypatch.setattr(router_mod, "evaluate_wp_formula_expression", _boom)
    db = _get_session(wp, project_year=2025)

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    tier_a = resp["extraction"]["tierA"]
    assert tier_a
    assert tier_a[0]["value"] is None


# ---------------------------------------------------------------------------
# 3. D6 render 主开关关 = 前置 spec 状态（无 prefill / detail_prefill / Tier A seed）
# ---------------------------------------------------------------------------


class _RenderFakeResult:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _RenderSession:
    def __init__(self, *, checklist_rows=None, project_row=None, tb_row=None, rp_rows=None):
        self.checklist_rows = checklist_rows or []
        self.project_row = project_row
        self.tb_row = tb_row
        self.rp_rows = rp_rows or []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        if "checklist_responses" in s:
            return _RenderFakeResult(rows=self.checklist_rows)
        if "related_party_registry" in s:
            return _RenderFakeResult(rows=self.rp_rows)
        if "trial_balance" in s:
            return _RenderFakeResult(one=self.tb_row)
        if "from projects" in s or "projects where" in s:
            return _RenderFakeResult(one=self.project_row)
        return _RenderFakeResult()

    async def rollback(self):
        return None


def _d6_render_ctx():
    db = _RenderSession(
        checklist_rows=[SimpleNamespace(item_id="D6-1-block1-endUnadjusted",
                                        conclusion="", remark="123.45")],
        project_row=SimpleNamespace(client_name="测试客户", audit_year=2025,
                                    business_category="general",
                                    applicable_standards="listed"),
        tb_row=SimpleNamespace(
            amount=98765.43,
            # 取数收敛到共享件 `fetch_trial_balance_amounts` 后统一读这两个
            # 别名（= 真实 DB 的列名）；`amount` 是 D6 改造前裸 SQL 的别名，保留兼容。
            unadjusted=98765.43,
            audited=98765.43,
        ),
        rp_rows=[SimpleNamespace(name="关联方甲", relation_type="subsidiary")],
    )
    return SimpleNamespace(
        db=db, wp_id=uuid4(), project_id=uuid4(), year=2025,
        business_category="general",
        classification=SimpleNamespace(sheet_name="合同资产审定表D6-1"),
    )


def test_d6_render_flag_off_no_prefill_no_detail_seed(monkeypatch):
    """基线：主开关关时 D6 render 无 adjudication_prefill / detail_prefill / Tier A seed。

    TB 核对行仍靠 project_context.tb_amount（本 spec 主开关关必须与此逐字节等价）。
    """
    _disable(monkeypatch)
    result = _run(d6.render(_d6_render_ctx()))
    assert "adjudication_prefill" not in result
    assert "detail_prefill" not in result
    # project_context.tb_amount 仍是 TB 核对行来源（未被 Tier A seed 取代）
    assert result["project_context"]["tb_amount"] == 98765.43
    # responses_snapshot 仅回显 checklist（无公式驱动的 TB 核对行 seed）
    snap = result["responses_snapshot"]
    assert "D6-1-block1-endUnadjusted" in snap
    assert "D6-1-tb-amount" not in snap, "主开关关时不应有 Tier A transient seed"


# ---------------------------------------------------------------------------
# 4. P0-2 子开关默认 False + 被主开关 AND（Req5.2）
# ---------------------------------------------------------------------------


def test_detail_seed_subswitch_default_false():
    """新增配置 D_CYCLE_DETAIL_SEED_ENABLED **代码默认** False（零回归）。

    断言 Settings 类的**声明默认值**而非 `settings` 实例的运行值 —— 后者会被部署环境的
    `.env` 覆盖（本环境为 live 验 D1 明细取数已 opt-in 置 True），读实例会让「代码默认零回归」
    这一意图随环境漂移、误报为回归。同理见下方主开关默认值断言。
    """
    assert Settings.model_fields["D_CYCLE_DETAIL_SEED_ENABLED"].default is False


def test_detail_seed_effective_gate_is_main_and_sub(monkeypatch):
    """P0-2 生效条件 = 主开关 ∧ 子开关（主关则子无效；两者独立可组合）。"""
    def effective():
        return bool(
            settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED
            and settings.D_CYCLE_DETAIL_SEED_ENABLED
        )

    # 默认（主关 + 子关）→ 无效
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    monkeypatch.setattr(settings, "D_CYCLE_DETAIL_SEED_ENABLED", False)
    assert effective() is False
    # 仅子开关开、主开关关 → 仍无效（被主开关 AND 门控，"发 P0-1 压 P0-2"的反向）
    monkeypatch.setattr(settings, "D_CYCLE_DETAIL_SEED_ENABLED", True)
    assert effective() is False
    # 仅主开关开、子开关关 → P0-2 无效（可"发 P0-1、压 P0-2"）
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    monkeypatch.setattr(settings, "D_CYCLE_DETAIL_SEED_ENABLED", False)
    assert effective() is False
    # 主 ∧ 子 全开 → 生效
    monkeypatch.setattr(settings, "D_CYCLE_DETAIL_SEED_ENABLED", True)
    assert effective() is True
