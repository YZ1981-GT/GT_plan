"""Wave 4 / Task 5.2 —— D1 应收票据 render 四表库接入（宁缺勿造）+ Tier A 预设集成测试.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/
      (Requirements 1.1, 1.2, 2.3, 3.1, 3.4, 7.1, 7.2, 7.4 / Property 8, 9, 11)

D1 的 KEY BOUNDARY（宁缺勿造 R3.4）：
  * D1-1 审定表按**票据类型固定分类**（银行承兑汇票/商业承兑汇票），分原值/坏账准备/净值
    三区块（`useD1Adjudication` GROSS_ROWS/BAD_DEBT_ROWS/NET_VALUE_ROWS，固定 2 行 × 3 区块，
    **非 D6-1 block1 那种动态叶子行**）。原值未审由 D1-2 按类别明细（`D1-cat-rows`）cross-sheet
    派生、坏账来自减值模型、净值 = 原值−坏账 computed → trial_balance/tb_balance 的 1121
    **只有科目总额、无「原值/坏账/净值 × 银行/商业」组合维度** → 无法把 TB 干净映射到分类行
    → D1 render **不返回 adjudication_prefill**（不臆造）。
  * 因此 D1 render 输出在开关开/关时**逐字节等价**（Property 9 天然成立，零回归）。
  * 唯一可从四表库干净取的是 `D1-adj-tb-amount`（应收票据**净额**）—— 已由 render 的
    `project_context.tb_amount` seed（前端 tbSeedAmount 回退），且注册为 Tier A **可编辑**
    公式 `TB('1121','期末余额') - TB('1231-01','期末余额')`（口径依据见 `_D1_EXPRESSION`）。
  * D1-3 客户明细期后兑付（`importPostSettlementFromLedger` 序时账 1121 贷方）为前端既有
    一键取数，本 render 不介入、不冲突（手工优先精度）。

全部 fake async session（不触发 conftest 真实 SQLite create_all）；直接调 render / router 协程。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import settings
from app.routers import wp_formula as router_mod
from app.routers.wp_render_strategies import _d1_notes_receivable as d1
from app.services.d_cycle_extraction import presets as presets_mod
from app.services.d_cycle_extraction.anchor_registry import is_known_anchor
from app.services.d_cycle_extraction.presets import (
    SOURCE_CUSTOM,
    SOURCE_PRESET,
    load_presets,
    resolve_effective,
    tier_b_provenance,
)
from app.services.wp_formula_eval_service import find_unsupported_formula_functions

_D1_ANCHOR = "D1-adj-tb-amount"
# 🔴 **净额**口径（原值 1121 − 坏账准备 1231-01），非原值。双证：
#   ① 源模板 `审定表D1-1` 的差异数 `E20=E18-E19`，E18 是「三、应收票据净值」小计
#      → 被比较的「试算平衡表数」E19 必然是净额；
#   ② `report_config` 的 BS-005 应收票据在 soe_standalone 下公式正是
#      `TB('1121','期末余额') - TB('1231-01','期末余额')`（报表按净额列示）。
# 原登记的原值口径会让核对行显示一个恰好等于坏账准备的**假差异**
# （实测项目 0ec33ac9：审定净值 19,046,910.15 vs 原值 20,209,198.18，差 1,162,288.03）。
_D1_EXPRESSION = "TB('1121','期末余额') - TB('1231-01','期末余额')"

# D1 render characterization 基线顶层键
_BASELINE_KEYS = {"sheet_name", "project_context", "responses_snapshot"}


def _run(coro):
    return asyncio.run(coro)


def _reset_presets_cache(monkeypatch):
    monkeypatch.setattr(presets_mod, "_cached_mtime", None, raising=False)


# ---------------------------------------------------------------------------
# Fake async DB —— 按 SQL 文本路由（D1 render：checklist / projects / related_party /
# trial_balance）
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
        rp_rows=None,
        tb_row=None,
        tb_provision_row=None,
        tb_balance_rows=None,
    ):
        self.checklist_rows = checklist_rows or []
        self.project_row = project_row
        self.rp_rows = rp_rows or []
        self.tb_row = tb_row
        # 坏账准备（1231-01）行；默认 None → `_seed_tb_provision_amount` 不写键，
        # `_net_tb_amount` 空操作 → 灰度开/关逐字节等价（零回归基线不变）
        self.tb_provision_row = tb_provision_row
        # tb_balance 叶子行（供 seed_d1_detail_rows 的 1121/1231 查询）；默认空 → seed no-op
        self.tb_balance_rows = tb_balance_rows or []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        if "checklist_responses" in s:
            return _FakeResult(rows=self.checklist_rows)
        if "related_party_registry" in s:
            return _FakeResult(rows=self.rp_rows)
        if "trial_balance" in s:
            # 🔴 原值（1121，前缀内联在 SQL 里）与坏账准备（1231-01，走绑定参数 :c0）
            #    是**两个**查询。此前不区分 → 两次都返回同一行，坏账 == 原值
            #    → 净额恒为 0，把 `_net_tb_amount` 的守卫变成噪声。
            wants_provision = any(
                str(v).startswith("1231") for v in (params or {}).values()
            )
            if wants_provision:
                return _FakeResult(one=self.tb_provision_row)
            return _FakeResult(one=self.tb_row)
        if "from projects" in s or "projects where" in s:
            return _FakeResult(one=self.project_row)
        if "tb_balance" in s:
            # seed_d1_detail_rows：按 account_code 前缀路由（1121 原值 / 1231 坏账）
            try:
                compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            except Exception:
                compiled = str(stmt)
            rows = [
                r for r in self.tb_balance_rows
                if str(getattr(r, "code", "")) and (
                    ("1231" in compiled and str(r.code).startswith("1231"))
                    or ("1231" not in compiled and str(r.code).startswith("1121"))
                )
            ]
            return _FakeResult(rows=rows)
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
        classification=SimpleNamespace(sheet_name="应收票据审定表D1-1"),
    )


def _session(*, checklist_rows=None):
    return _FakeSession(
        checklist_rows=checklist_rows or [],
        project_row=SimpleNamespace(
            client_name="测试客户",
            audit_year=2025,
            business_category="general",
        ),
        rp_rows=[SimpleNamespace(name="关联方甲")],
        tb_row=SimpleNamespace(unadjusted=1000.0, audited=1200.0),
    )


def _set_gates(monkeypatch, *, main: bool, detail_seed: bool):
    """显式设定**两个**灰度开关（禁止依赖环境默认值）。

    D1 明细 seed 门控 = 主开关 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`
    ∧ 子开关 `D_CYCLE_DETAIL_SEED_ENABLED`（与 D6-2 同款门控矩阵）。
    两者都必须显式 setattr —— 否则一旦部署环境的 `.env` 打开任一开关，
    这些测试会随环境漂移（本环境为跑 live 实测确实会开），断言即失去意义。
    """
    monkeypatch.setattr(d1.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", main)
    monkeypatch.setattr(d1.settings, "D_CYCLE_DETAIL_SEED_ENABLED", detail_seed)


def _enable_flag(monkeypatch):
    """主开关开、明细 seed 子开关**关** —— 即文档所称「发 P0-1、压 P0-2」。"""
    _set_gates(monkeypatch, main=True, detail_seed=False)


def _disable_flag(monkeypatch):
    """两开关全关（默认态）。"""
    _set_gates(monkeypatch, main=False, detail_seed=False)


def _enable_detail_seed(monkeypatch):
    """主 ∧ 子 全开 —— 明细 seed 真生效。"""
    _set_gates(monkeypatch, main=True, detail_seed=True)


# ---------------------------------------------------------------------------
# Property 9: 灰度零回归 + 宁缺勿造（开关开/关 D1 render 逐字节等价，无 prefill）
# ---------------------------------------------------------------------------


def test_flag_off_baseline_keys_no_prefill(monkeypatch):
    """开关关闭（默认）→ 顶层键 == 基线，无 adjudication_prefill。"""
    _disable_flag(monkeypatch)
    result = _run(d1.render(_ctx(_session())))
    assert set(result.keys()) == _BASELINE_KEYS
    assert "adjudication_prefill" not in result


def test_flag_on_still_no_prefill_ningquewuzao(monkeypatch):
    """开关开启 → D1 **仍不返回** adjudication_prefill 顶层键。

    实证纠正（d1-four-table-extraction-formula-wiring）：D1 四表库取数走 responses_snapshot
    明细行 seed（D1-cat-rows / D1-bd-portfolio-rows），**非** D6 式 adjudication_prefill 顶层键。

    d1-extraction-chain-completion R1.6 起，主开关开时**额外**输出一个 additive 键
    `tb_source_codes`（科目定位溯源：BS-005 → 标准码 → account_mapping → 原始码），
    故顶层键集 == 基线 ∪ {tb_source_codes}；`adjudication_prefill` 仍恒不出现。
    """
    _enable_flag(monkeypatch)
    result = _run(d1.render(_ctx(_session())))
    assert "adjudication_prefill" not in result
    assert set(result.keys()) == _BASELINE_KEYS | {"tb_source_codes"}
    # 取数溯源结构固定，且 fail-open 兜底恒非空
    src = result["tb_source_codes"]
    assert src["gross"] and src["provision"]
    assert src["resolved_from"] in {"report_config", "fallback"}


def test_flag_on_off_byte_equivalent_when_no_tb_leaves(monkeypatch):
    """无 tb 叶子 + D1-cat-rows 已持久化时，开关开/关逐字节等价（seed no-op / 手工优先 / Property 3）。

    注意：本 fake session 不返回 tb_balance 叶子，且 D1-cat-rows 已持久化 → seed 为空操作。
    当 tb 有叶子且未持久化时 seed 会写入（见 test_flag_on_seeds_detail_from_tb_leaves）。

    d1-extraction-chain-completion R1.6/R1.7 起口径细化：**灰度关**输出必须与改动前
    逐字节等价（Property 10，由 test_flag_off_baseline_keys_no_prefill 钉住基线键集）；
    **灰度开**允许多出 additive 的取数溯源键，故此处剥离新增键后再比对逐字节等价。
    """
    checklist = [
        _checklist_row("D1-adj-gross-bank-current-unadj", remark="123456"),
        _checklist_row("D1-cat-rows", remark='[{"category":"银行承兑汇票"}]'),
    ]
    _disable_flag(monkeypatch)
    off = _run(d1.render(_ctx(_session(checklist_rows=list(checklist)))))
    _enable_flag(monkeypatch)
    on = _run(d1.render(_ctx(_session(checklist_rows=list(checklist)))))

    # 灰度关：绝不出现新增键（零回归硬断言）
    assert "tb_source_codes" not in off
    assert not any(k.startswith("tb_provision_amount") for k in off["project_context"])

    stripped = {k: v for k, v in on.items() if k != "tb_source_codes"}
    stripped["project_context"] = {
        k: v
        for k, v in on["project_context"].items()
        if not k.startswith("tb_provision_amount")
    }
    assert off == stripped
    assert "adjudication_prefill" not in on


def test_main_on_sub_off_no_detail_seed(monkeypatch):
    """🔴 主开关开 + 明细 seed 子开关关 + tb **有**叶子 → 一律不 seed（发 P0-1、压 P0-2）。

    子开关 `D_CYCLE_DETAIL_SEED_ENABLED` 的语义是 D 循环通用的「明细表 render 自动 seed」，
    D6-2 早已按「主 ∧ 子」门控。D1 首版只挂主开关 → 运维为启用 Tier A 而开主开关时会**静默**
    连带打开 D1 明细 seed、且无法单独回退。本例锁死该门控矩阵态。
    """
    from app.services.d_cycle_extraction import d1_detail_seed as _seed_mod

    async def _fake_af(*_a, **_k):
        return True

    monkeypatch.setattr(_seed_mod, "get_active_filter", _fake_af)
    _enable_flag(monkeypatch)  # main=True, detail_seed=False

    sess = _session()
    sess.tb_balance_rows = [
        SimpleNamespace(code="1121.01", name="应收票据_银行承兑汇票",
                        opening=100.0, closing=120.0, debit=50.0, credit=30.0),
        SimpleNamespace(code="1231.01", name="坏账准备_应收票据",
                        opening=3000.0, closing=1200.0, debit=0.0, credit=0.0),
    ]
    snap = _run(d1.render(_ctx(sess)))["responses_snapshot"]

    assert "D1-cat-rows" not in snap
    assert "D1-bd-portfolio-rows" not in snap
    # 反向自检：同一 fixture 在子开关开时确实会 seed（否则本例恒真 = 空转）
    _enable_detail_seed(monkeypatch)
    sess2 = _session()
    sess2.tb_balance_rows = list(sess.tb_balance_rows)
    snap2 = _run(d1.render(_ctx(sess2)))["responses_snapshot"]
    assert "D1-cat-rows" in snap2
    assert "D1-bd-portfolio-rows" in snap2


def test_flag_on_seeds_detail_from_tb_leaves(monkeypatch):
    """主 ∧ 子 全开 + tb 有 1121/1231 叶子 + 无持久化 → seed D1-cat-rows / D1-bd-portfolio-rows。

    实证正路：证明 render 端到端接入 seed_d1_detail_rows（原值 fixed-bank/commercial +
    坏账 fixed-portfolio），落 responses_snapshot（transient，供前端 loadFromResponses 消费）。
    """
    import json as _json

    from app.services.d_cycle_extraction import d1_detail_seed as _seed_mod

    async def _fake_af(*_a, **_k):
        return True

    monkeypatch.setattr(_seed_mod, "get_active_filter", _fake_af)
    _enable_detail_seed(monkeypatch)

    tb_leaves = [
        SimpleNamespace(code="1121.01", name="应收票据_银行承兑汇票",
                        opening=100.0, closing=120.0, debit=50.0, credit=30.0),
        SimpleNamespace(code="1121.02", name="应收票据_商业承兑汇票",
                        opening=200.0, closing=150.0, debit=10.0, credit=60.0),
        SimpleNamespace(code="1231.01", name="坏账准备_应收票据",
                        opening=3000.0, closing=1200.0, debit=0.0, credit=0.0),
    ]
    sess = _session()
    sess.tb_balance_rows = tb_leaves
    result = _run(d1.render(_ctx(sess)))
    snap = result["responses_snapshot"]

    assert "adjudication_prefill" not in result  # 仍不用顶层键
    cat = _json.loads(snap["D1-cat-rows"]["remark"])
    assert {r["rowId"] for r in cat} == {"fixed-bank", "fixed-commercial"}
    # roll-forward：opening + debit − credit == closing
    bank = next(r for r in cat if r["rowId"] == "fixed-bank")
    assert round(bank["priorUnadjusted"] + bank["currentIncrease"] - bank["currentDecrease"], 2) == 120.0
    bd = _json.loads(snap["D1-bd-portfolio-rows"]["remark"])
    assert bd[0]["priorUnadjusted"] == 3000.0
    assert bd[0]["currentReversal"] == 1800.0  # 3000 − 1200 净减少 → 转回


# ---------------------------------------------------------------------------
# 宁缺勿造：不臆造分类行未审；与既有 tb_amount seed / D1-cat-rows 共存不冲突
# ---------------------------------------------------------------------------


def test_no_fabricated_classification_rows(monkeypatch):
    """D1 render 不新增任何 D1-adj-(gross|bd)-* 分类未审键到 responses_snapshot。"""
    _enable_flag(monkeypatch)
    result = _run(d1.render(_ctx(_session())))
    snapshot = result["responses_snapshot"]
    fabricated = [
        k
        for k in snapshot
        if k.startswith("D1-adj-gross-") or k.startswith("D1-adj-bd-")
    ]
    assert fabricated == [], "宁缺勿造：不得臆造审定表分类行未审数"


def test_tb_amount_seeded_in_project_context(monkeypatch):
    """既有 TB seed 路径保留：project_context.tb_amount 由 render 提供（审定优先，回退未审）。

    fake session 无 1231-01 坏账行 → `_net_tb_amount` 空操作，tb_amount 保持原值口径
    （净额转换本身由 `test_net_tb_amount_*` 覆盖）。
    """
    _enable_flag(monkeypatch)
    result = _run(d1.render(_ctx(_session())))
    pc = result["project_context"]
    # 审定 1200 优先于未审 1000
    assert pc["tb_amount"] == 1200.0
    assert pc["tb_amount_unadjusted"] == 1000.0
    assert pc["tb_amount_audited"] == 1200.0
    assert "tb_amount_gross" not in pc, "无坏账数据时不得造溯源键（零回归）"


def test_coexist_with_existing_detail_seed(monkeypatch):
    """既有 D1-cat-rows（cross-sheet 明细）/ D1-cust-rows 原样透传，render 不覆盖。

    门控用**主 ∧ 子全开**：手工优先只有在 seed 逻辑真会跑时才有验证意义
    （子开关关时压根不进 seed 分支，本例会退化为恒真）。
    """
    _enable_detail_seed(monkeypatch)
    checklist = [
        _checklist_row("D1-cat-rows", remark='[{"category":"银行承兑汇票","currentUnadjusted":100}]'),
        _checklist_row("D1-cust-rows", remark='[{"customerName":"甲","postSettlement":50}]'),
    ]
    result = _run(d1.render(_ctx(_session(checklist_rows=checklist))))
    snap = result["responses_snapshot"]
    assert snap["D1-cat-rows"]["remark"] == '[{"category":"银行承兑汇票","currentUnadjusted":100}]'
    assert snap["D1-cust-rows"]["remark"] == '[{"customerName":"甲","postSettlement":50}]'


# ---------------------------------------------------------------------------
# Tier A：D1 预设双门 + GET extraction.tierA surface
# ---------------------------------------------------------------------------


def test_d1_preset_passes_both_gates(monkeypatch):
    """D1 预设（净额口径）通过锚点合法性 + 受支持函数双门。"""
    _reset_presets_cache(monkeypatch)
    presets = load_presets("D1")
    assert len(presets) == 1, "D1 应有且仅有 1 条 Tier A 预设（应收票据净额，宁缺勿造）"
    entry = presets[0]
    assert entry["anchor"] == _D1_ANCHOR
    assert entry["expression"] == _D1_EXPRESSION
    assert is_known_anchor("D1", entry["anchor"]) is True
    assert find_unsupported_formula_functions(entry["expression"]) == []
    # 口径守卫：必须同时含原值与坏账准备两项且是减项（原值口径会产生假差异）
    assert "TB('1121'" in entry["expression"] and "- TB('1231-01'" in entry["expression"]
    assert "净额" in entry["description"], "description 须写明净额口径与依据"


def test_resolve_effective_returns_d1_preset(monkeypatch):
    """无用户覆盖 → resolve_effective("D1") 返回该预设，source=preset。"""
    _reset_presets_cache(monkeypatch)
    db = _FormulaFakeSession(wp=_wp(), wp_code="D1", user_formulas=[])
    result = _run(resolve_effective(db, uuid4(), "D1", uuid4()))
    assert len(result) == 1
    b = result[0]
    assert b["anchor"] == _D1_ANCHOR
    assert b["expression"] == _D1_EXPRESSION
    assert b["sheet_name"] == "D1-1"
    assert b["source"] == SOURCE_PRESET
    assert b["tier"] == "A"


def test_resolve_effective_user_override_becomes_custom(monkeypatch):
    """用户同锚点覆盖 → source=custom（读时收敛 Property 5）。"""
    _reset_presets_cache(monkeypatch)
    wp = _wp()
    user = _wp_formula(_D1_ANCHOR, expression="TB('1121','期初余额')", wp=wp)
    db = _FormulaFakeSession(wp=wp, wp_code="D1", user_formulas=[user])
    result = _run(resolve_effective(db, wp.id, "D1", wp.project_id))
    assert len(result) == 1
    assert result[0]["source"] == SOURCE_CUSTOM
    assert result[0]["expression"] == "TB('1121','期初余额')"


def test_get_endpoint_surfaces_d1_preset_in_tier_a(monkeypatch):
    """flag ON + wp_code=D1：GET /formulas 的 extraction.tierA 含 D1-adj-tb-amount。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp = _wp()
    db = _FormulaFakeSession(wp=wp, wp_code="D1", user_formulas=[])
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    assert "extraction" in resp
    ext = resp["extraction"]
    assert ext["wp_code"] == "D1"
    assert ext["enabled"] is True

    tier_a = {b["anchor"]: b for b in ext["tierA"]}
    assert _D1_ANCHOR in tier_a
    binding = tier_a[_D1_ANCHOR]
    assert binding["expression"] == _D1_EXPRESSION
    assert binding["source"] == SOURCE_PRESET
    assert binding["tier"] == "A"
    assert binding["value"] is None  # R5.6：GET 不逐条重求值


def test_get_endpoint_surfaces_d1_tier_b_provenance(monkeypatch):
    """flag ON + wp_code=D1：extraction.tierB 含 D1-3 期后兑付溯源 + D1-1 宁缺勿造声明（只读）。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp = _wp()
    db = _FormulaFakeSession(wp=wp, wp_code="D1", user_formulas=[])
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    tier_b = resp["extraction"]["tierB"]
    anchors = {e["anchor"]: e for e in tier_b}
    assert "D1-cust-rows" in anchors
    assert anchors["D1-cust-rows"]["editable"] is False
    assert anchors["D1-cust-rows"]["tier"] == "B"
    # D1-1 分类不填的诚实声明
    assert any("gross" in a or "分类" in e.get("description", "") for a, e in anchors.items())


def test_flag_off_no_extraction_for_d1(monkeypatch):
    """flag OFF → 无 extraction（零回归 / R7.1）。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    wp = _wp()
    db = _FormulaFakeSession(wp=wp, wp_code="D1", user_formulas=[])
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    assert "extraction" not in resp


# ---------------------------------------------------------------------------
# Tier B 只读溯源（诚实登记 D1-3 期后兑付归集 + D1-1 分类不填声明）
# ---------------------------------------------------------------------------


def test_tier_b_provenance_d1_honest():
    """tier_b_provenance("D1") 登记 tb 叶子取数（D1-2/D1-4）+ 各底稿间连接取数溯源，全部只读。

    实证纠正后（d1-four-table-extraction-formula-wiring）：D1-2 原值 ← tb_balance 1121 叶子、
    D1-4 坏账 ← tb_balance 1231.01；另登记 D1-1←D1-2/D1-4、D1-4↔D1-15、D1-1 表外←D1-8 等
    cross-sheet 连接取数关系。全部 editable=False（复杂归集/cross-sheet 不压成单条公式）。
    """
    entries = tier_b_provenance("D1")
    assert len(entries) >= 6
    for e in entries:
        assert e["editable"] is False
        assert e["source"] == "prefill"
        assert e["tier"] == "B"
        assert e["value"] is None
    anchors = {e["anchor"] for e in entries}
    # 四表库直取来源
    assert "D1-cat-rows" in anchors      # D1-2 原值 ← tb 1121 叶子
    assert "D1-bd-portfolio-rows" in anchors  # D1-4 坏账 ← tb 1231.01
    assert "D1-cust-rows" in anchors     # D1-3 期后兑付 ← 序时账 1121 贷方
    # 连接取数溯源
    assert any("gross" in a for a in anchors)  # D1-1 原值 ← D1-2
    assert any("D1-15" in a for a in anchors)  # D1-4 ↔ D1-15 ECL
    # tb 叶子取数描述可追溯（d1-extraction-chain-completion 起科目由 BS-005 报表映射解析，
    # 故描述不再写死「tb_balance 1121」，但必须同时点明数据源与实证科目）
    cat = next(e for e in entries if e["anchor"] == "D1-cat-rows")
    assert "tb_balance" in cat["description"]
    assert "1121.01" in cat["description"]  # 实证叶子仍须可追溯
    assert "BS-005" in cat["description"]   # 科目定位来源

    # 科目定位链路本身必须有一条只读溯源（审计师据此知道科目是怎么定位的）
    src = next(e for e in entries if e["anchor"] == "tb_source_codes")
    for token in ("BS-005", "report_config", "account_mapping", "fail-open"):
        assert token in src["description"], token

    # D1-4 按票据种类小计块（喂审定表坏账区块）必须登记且声明「不从四表库填」
    nt = next(e for e in entries if e["anchor"] == "D1-bd-notetype-rows")
    assert "不从四表库填" in nt["description"]
    assert "宁缺勿造" in nt["description"]


# ---------------------------------------------------------------------------
# Formula-endpoint fake session（复用 test_d6_tier_a_preset 同款）
# ---------------------------------------------------------------------------


class _FormulaFakeResult:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _FormulaFakeSession:
    def __init__(self, *, wp, wp_code, user_formulas=None):
        self.wp = wp
        self.wp_code = wp_code
        self.user_formulas = user_formulas or []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        if "from wp_index" in s:
            return _FormulaFakeResult(scalar=self.wp_code)
        if "from wp_formula" in s:
            return _FormulaFakeResult(rows=self.user_formulas)
        if "from working_paper" in s:
            if "is_deleted" in s:
                return _FormulaFakeResult(scalar=self.wp)
            return _FormulaFakeResult(scalar=self.wp.project_id)
        return _FormulaFakeResult()

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


def _wp_formula(target_cell, *, expression, sheet_name="D1-1", wp=None):
    return SimpleNamespace(
        id=uuid4(),
        project_id=(wp.project_id if wp else uuid4()),
        wp_id=(wp.id if wp else uuid4()),
        sheet_name=sheet_name,
        target_cell=target_cell,
        expression=expression,
        category=None,
        description="用户覆盖",
        formula_type="auto_calc",
        refs=None,
        issue_description=None,
        hint_text=None,
        last_computed_at=None,
        created_by=None,
        created_at=None,
        updated_at=None,
    )


def _user():
    return SimpleNamespace(id=uuid4(), username="tester")


# ---------------------------------------------------------------------------
# TB 核对回退标量口径（净额，必须与 Tier A 预设同口径）
# ---------------------------------------------------------------------------


def test_net_tb_amount_converts_gross_to_net():
    """`_net_tb_amount` 把 tb_amount 三个口径全部转净额，并留 gross 供溯源。"""
    pc = {
        "tb_amount": 20209198.18,
        "tb_amount_unadjusted": 20209198.18,
        "tb_amount_audited": 20209198.18,
        "tb_provision_amount": 1162288.03,
        "tb_provision_amount_unadjusted": 1162288.03,
        "tb_provision_amount_audited": 1162288.03,
    }
    d1._net_tb_amount(pc)

    # 实测项目 0ec33ac9 的活体值：净额 = 原值 − 坏账准备
    assert round(pc["tb_amount"], 2) == 19046910.15
    assert round(pc["tb_amount_unadjusted"], 2) == 19046910.15
    assert round(pc["tb_amount_audited"], 2) == 19046910.15
    # 原值保留供审定表取数溯源（前端 tbSeedProvenance 消费，非 dead output）
    assert round(pc["tb_amount_gross"], 2) == 20209198.18
    assert round(pc["tb_amount_gross_audited"], 2) == 20209198.18


def test_net_tb_amount_noop_without_provision():
    """无 tb_amount 或无坏账准备 → **完全不动** project_context。

    🔴 后者是零回归要求：该项目没有 1231-01 数据时净额恒等于原值，
    若仍造 `tb_amount_gross` 溯源键，`test_flag_on_off_byte_equivalent_when_no_tb_leaves`
    的灰度开/关逐字节等价即被打破。
    """
    empty: dict = {}
    d1._net_tb_amount(empty)
    assert empty == {}

    no_prov = {"tb_amount": 100.0}
    d1._net_tb_amount(no_prov)
    assert no_prov == {"tb_amount": 100.0}


def test_net_tb_amount_matches_tier_a_preset_semantics(monkeypatch):
    """回退标量与 Tier A 预设**同口径**：都是 原值 − 坏账准备。

    🔴 两者口径分叉是本 spec 实测抓出的缺陷：预设已改净额，而 render 下发的
    seed 回退仍是原值 → 用户在公式管理停用该 Tier A 公式后，核对行回落到原值，
    重现「差异恰好等于坏账准备」的假差异。
    """
    _reset_presets_cache(monkeypatch)
    expression = load_presets("D1")[0]["expression"]
    assert "TB('1121'" in expression and "- TB('1231-01'" in expression

    pc = {"tb_amount": 500.0, "tb_provision_amount": 120.0}
    d1._net_tb_amount(pc)
    assert pc["tb_amount"] == 380.0, "回退标量须与预设一样做减项"
    assert pc["tb_amount_gross"] == 500.0
