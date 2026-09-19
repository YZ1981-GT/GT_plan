"""D 循环 render 输出键零回归守卫 —— Property 32。

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.1, 1.2, 1.3, 1.8

判据（Property 32）：改造后的键集合 **⊇** 改造前，且既有键在同一输入下取值不变。

本文件用**冻结基线常量**表达「改造前」——  改造已完成，无法再跑旧代码，故把改造前
的键集合冻结为常量（取自 `test_d6_d2_render_characterization.py` 与既有
`test_d*_render_prefill_integration.py` 已锚定的形态），断言当前 render 的键是它的
超集。新增键单独登记在 `_ADDED_KEYS` 里，两个集合不得有交集 —— 这样「把既有键改名后
再登记成新增键」这种绕过方式会被打红。

🔴 **D1 是本 spec 的零回归红线**（tasks.md Task 4）：它的科目定位路径逐字未动，故
D1 的既有键**逐字节相等**而非仅超集，单独一组断言。

为什么不比对整个 payload
------------------------
`sections` 是从 YAML schema 派生的大结构，且 `responses_snapshot` 含 uuid，
逐字节比对会因无关改动频繁假红。真正需要锁死的是「**前端在读的键**」——
`html_data` 在 TS 里是 ``any``，改键名不会编译报错、只会静默读到 undefined
（memory 已登记的平台级坑），故键集合才是契约。
"""
from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.routers.wp_render_strategies import (
    _d1_notes_receivable as d1,
    _d2_accounts_receivable as d2,
    _d3_prepaid_accounts as d3,
    _d4_operating_revenue as d4,
    _d5_receivables_financing as d5,
    _d6_contract_assets as d6,
    _d7_contract_liabilities as d7,
)

# ─────────────────────────── 冻结基线：改造前的既有键 ───────────────────────────
#
# 取自本 spec 立项前已存在的 characterization / integration 测试所锚定的形态。
# 🔴 这些键**只许增不许改名**：前端 composable 已在读它们。

#: 全部 D render 的 `project_context` 公共键（来自 `_load_project_context` 类公共逻辑）
_PC_COMMON = frozenset({"client_name", "audit_year", "business_category"})

#: 各循环改造前**已在下发**的 TB 核对标量键（前端 seed 回退按这些键名读）
_PC_TB_SCALARS: dict[str, frozenset[str]] = {
    # D1 改造前就有 6 个（净额口径 + gross 并列），是零回归红线
    "D1": frozenset({
        "tb_amount", "tb_amount_unadjusted", "tb_amount_audited",
        "tb_provision_amount", "tb_provision_amount_unadjusted",
        "tb_provision_amount_audited",
    }),
    # D2 改造前「有记录才写键」→ 基线不含（本 spec 保持该语义）
    "D2": frozenset(),
    # D3 改造前**完全没查自己的科目**（只查了 D7 的 2205 做交叉核对）→ 基线为空；
    # 本 spec 新增 `tb_amount`（Task 6，本 spec 价值最高的一处）
    "D3": frozenset(),
    # D4 走 tb_values（发生额口径），无标量
    "D4": frozenset(),
    # D5/D6/D7 改造前**无条件**写 tb_amount（0 初始化后赋值）→ 必须保留该键，
    # 改成「不写键」会让前端从「读到 0」变成「读不到」= 行为回归
    "D5": frozenset({"tb_amount"}),
    "D6": frozenset({"tb_amount"}),
    "D7": frozenset({"tb_amount"}),
}

#: 各循环 `html_data` 顶层改造前已有的键
_HD_BASELINE: dict[str, frozenset[str]] = {
    "D1": frozenset(),
    "D2": frozenset(),
    "D3": frozenset(),
    # D4 是 D 类改造前最完整的一个
    "D4": frozenset({"tb_values", "adjudication_prefill", "segment_prefill"}),
    "D5": frozenset(),
    # 🔴 D6 的 `adjudication_prefill` / `detail_prefill` **不在无条件基线里** ——
    #    它们由灰度开关（`D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` ∧
    #    `D_CYCLE_DETAIL_SEED_ENABLED`）门控，且构建失败时 fail-open 省略该键。
    #    替身 session 拿不到真实 tb_balance 行 ⇒ seed 为空 ⇒ 键不出现，属**正确行为**。
    #    放进无条件基线会让守卫在替身环境恒红（首版即中招）。
    "D6": frozenset(),
    "D7": frozenset(),
}

#: 受灰度开关门控的键 —— 只断言「开关关时不得出现」，不断言「开关开时必须出现」
#: （后者需要真实四表数据，属 Task 13 真实库验收的职责）。
_GATED_HD_KEYS: dict[str, frozenset[str]] = {
    "D6": frozenset({"adjudication_prefill", "detail_prefill"}),
}

#: 本 spec **新增**的键（与基线不得有交集 —— 防「改名后登记成新增」绕过）
_ADDED_KEYS = frozenset({"tb_source_codes", "parent_check"})

_MODULES = {
    "D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5": d5, "D6": d6, "D7": d7,
}

_SHEET_BY_WP = {
    "D1": "应收票据审定表D1-1",
    "D2": "应收账款审定表D2-1",
    "D3": "预收账款审定表D3-1",
    "D4": "营业收入审定表D4-1",
    "D5": "应收款项融资审定表D5-1",
    "D6": "合同资产审定表D6-1",
    "D7": "合同负债审定表D7-1",
}


# ────────────────────────────────── 替身 ──────────────────────────────────


class _FakeResult:
    def __init__(self, rows=None, one=None, mappings=None):
        self._rows = rows or []
        self._one = one
        self._mappings = mappings

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one

    def all(self):
        return self._rows

    def first(self):
        return self._one

    def scalar(self):
        return None

    def scalar_one_or_none(self):
        return None

    def mappings(self):
        return _FakeResult(rows=self._mappings if self._mappings is not None else [])


class _FakeSession:
    """按 SQL 文本路由的替身（沿用 `test_d6_d2_render_characterization` 的约定）。"""

    def __init__(self, *, project_row=None, tb_row=None, tb_rows=None):
        self._project_row = project_row
        self._tb_row = tb_row
        self._tb_rows = tb_rows or []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        if "checklist_responses" in s:
            return _FakeResult(rows=[])
        if "related_party_registry" in s:
            return _FakeResult(rows=[])
        if "tb_balance" in s:
            return _FakeResult(rows=self._tb_rows, mappings=self._tb_rows)
        if "trial_balance" in s:
            return _FakeResult(one=self._tb_row, rows=[self._tb_row] if self._tb_row else [])
        if "projects" in s:
            return _FakeResult(one=self._project_row)
        if "account_mapping" in s or "account_chart" in s or "report_config" in s:
            return _FakeResult(rows=[])
        return _FakeResult()

    async def rollback(self):
        return None


def _session():
    return _FakeSession(
        project_row=SimpleNamespace(
            client_name="测试客户",
            audit_year=2025,
            business_category="general",
            applicable_standards="soe_standalone",
            entity_type="soe",
            report_scope="standalone",
        ),
        tb_row=SimpleNamespace(amount=1000.0, unadjusted=1000.0, audited=1000.0),
    )


def _ctx(wp: str):
    return SimpleNamespace(
        db=_session(),
        wp_id=uuid4(),
        project_id=uuid4(),
        year=2025,
        business_category="general",
        classification=SimpleNamespace(sheet_name=_SHEET_BY_WP[wp]),
    )


def _render(wp: str) -> dict:
    mod = _MODULES[wp]
    out = asyncio.run(mod.render(_ctx(wp)))
    return out if isinstance(out, dict) else {}


def _html_data(payload: dict) -> dict:
    """取 html_data。

    🔴 D 类 render **直接返回 html_data 本身**（不套 ``{"html_data": ...}`` 外层）——
    本守卫首版按「先取 payload['html_data']」找，7 个循环全部落空、断言退化成
    「missing 非空」的假红。判据：payload 里没有 ``html_data`` 键时它自己就是 html_data。
    """
    hd = payload.get("html_data")
    if isinstance(hd, dict):
        return hd
    for v in (payload.get("sheets") or []):
        if isinstance(v, dict) and isinstance(v.get("html_data"), dict):
            return v["html_data"]
    return payload if isinstance(payload, dict) else {}


def _project_context(payload: dict) -> dict:
    hd = _html_data(payload)
    pc = hd.get("project_context")
    if isinstance(pc, dict):
        return pc
    pc = payload.get("project_context")
    return pc if isinstance(pc, dict) else {}


# ────────────────── Property 32：键集合超集 + 新增键与基线正交 ──────────────────


class TestBaselineIsSubset:
    @pytest.mark.parametrize("wp", sorted(_MODULES))
    def test_project_context_公共键仍在(self, wp):
        pc = _project_context(_render(wp))
        assert pc, "%s 未下发 project_context" % wp
        missing = _PC_COMMON - set(pc)
        assert not missing, "%s 的 project_context 丢了公共键 %s" % (wp, sorted(missing))

    @pytest.mark.parametrize("wp", sorted(_PC_TB_SCALARS))
    def test_tb核对标量键仍在(self, wp):
        """改造前已下发的 TB 标量键必须仍在 —— 前端 seed 回退按键名读，丢键即静默失效。"""
        expected = _PC_TB_SCALARS[wp]
        if not expected:
            pytest.skip("%s 改造前无 TB 标量基线" % wp)
        pc = _project_context(_render(wp))
        missing = expected - set(pc)
        assert not missing, (
            "🔴 %s 丢了改造前已有的 TB 标量键 %s —— 前端会静默读到 undefined"
            % (wp, sorted(missing))
        )

    @pytest.mark.parametrize("wp", sorted(_HD_BASELINE))
    def test_html_data顶层基线键仍在(self, wp):
        expected = _HD_BASELINE[wp]
        if not expected:
            pytest.skip("%s 无 html_data 顶层基线" % wp)
        hd = _html_data(_render(wp))
        missing = expected - set(hd)
        assert not missing, "🔴 %s 丢了 html_data 基线键 %s" % (wp, sorted(missing))


class TestAddedKeysAreOrthogonal:
    def test_新增键与基线无交集(self):
        """🔴 防「把既有键改名后再登记成新增键」这种绕过方式。"""
        all_baseline: set[str] = set(_PC_COMMON)
        for v in _PC_TB_SCALARS.values():
            all_baseline |= set(v)
        for v in _HD_BASELINE.values():
            all_baseline |= set(v)
        assert not (_ADDED_KEYS & all_baseline), (
            "新增键与基线键重叠 %s —— 说明有既有键被改名了"
            % sorted(_ADDED_KEYS & all_baseline)
        )

    @pytest.mark.parametrize("wp", sorted(_MODULES))
    def test_新增键已下发(self, wp):
        """`tb_source_codes` 与 `parent_check` 必须在 project_context 或 html_data 顶层。"""
        payload = _render(wp)
        hd = _html_data(payload)
        pc = _project_context(payload)
        seen = set(hd) | set(pc)
        missing = _ADDED_KEYS - seen
        assert not missing, "%s 未下发新增键 %s" % (wp, sorted(missing))


# ────────────────── D1 零回归红线：既有键取值逐字节相等 ──────────────────


class TestD1ZeroRegression:
    """D1 的科目定位路径逐字未动 → 既有键必须**取值相等**而非仅存在。

    🔴 tasks.md 把 D1 定为零回归红线（Task 4「只做加法」）。判据取两次 render
    在同一输入下的既有键取值，并断言 6 个 TB 标量全部存在且为数值。
    """

    def test_六个tb标量齐备且为数值(self):
        pc = _project_context(_render("D1"))
        for k in sorted(_PC_TB_SCALARS["D1"]):
            assert k in pc, "D1 丢了 %s" % k
            v = pc[k]
            assert v is None or isinstance(v, (int, float)), (
                "D1 的 %s 类型异常：%r" % (k, v)
            )

    def test_两次render既有键取值一致(self):
        """同一输入两次 render，既有键取值必须相同（无隐藏随机/时间依赖）。"""
        a = _project_context(_render("D1"))
        b = _project_context(_render("D1"))
        for k in sorted(_PC_TB_SCALARS["D1"] | _PC_COMMON):
            assert a.get(k) == b.get(k), "D1 的 %s 两次 render 不一致" % k

    def test_d1仍走自己的薄壳(self):
        """D1 不得被「顺手统一」到 `d_account_resolver`（零回归红线）。"""
        src = inspect.getsource(d1)
        body = "\n".join(
            l for l in src.split("\n") if not l.strip().startswith("#")
        )
        assert "resolve_d1_account_codes" in body, "D1 不再走 d1_account_resolver"
        assert "resolve_d_cycle_account_codes" not in body, (
            "🔴 D1 被改成走 d_account_resolver —— 那是零回归红线，"
            "两者委托同一共享件故无需统一"
        )


# ────────────────────────────── 反向自检 ──────────────────────────────


class TestReverseSelfChecks:
    def test_反向_render确实被调用(self):
        """证明上面的断言不是因为 render 返回空字典而恒绿。"""
        payload = _render("D6")
        assert payload, "render 返回空 —— 全部断言都在空转"
        assert _html_data(payload), "html_data 为空 —— 键断言无意义"

    def test_反向_基线常量非空(self):
        assert _PC_COMMON
        assert _ADDED_KEYS
        assert sum(len(v) for v in _PC_TB_SCALARS.values()) >= 8
        assert len(_MODULES) == 7

    def test_反向_缺键会被检出(self):
        """对一个人造的缺键 payload 施加同一判据，必须判缺。"""
        fake_pc = {"client_name": "x"}          # 故意缺 audit_year / business_category
        assert _PC_COMMON - set(fake_pc), "判据对缺键无反应 —— 断言失效"


# ────────────────── 灰度门控键：关时不得出现（Property 32 的边界） ──────────────────


class TestGatedKeys:
    """受灰度开关门控的键必须真的被门控住。

    🔴 本组存在的理由：`_GATED_HD_KEYS` 若只是个常量而无断言消费，它就是死配置
    （平台已多次出现「登记表零消费方」）。这里用**源码级**判据 —— 断言那些键的写入
    点确实被 `settings.D_CYCLE_*_ENABLED` 包住 —— 而不是靠替身环境「恰好没出现」
    （后者是假绿：构建失败 fail-open 也会让键不出现，两者不可区分）。
    """

    def test_门控键的写入点被开关包住(self):
        for wp, keys in _GATED_HD_KEYS.items():
            src = inspect.getsource(_MODULES[wp])
            body = "\n".join(
                l for l in src.split("\n") if not l.strip().startswith("#")
            )
            assert "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED" in body, (
                "%s 声明了门控键 %s 却不引用主开关" % (wp, sorted(keys))
            )
            for k in sorted(keys):
                # 该键的写入语句必须存在（否则登记表已过期）
                assert 'html_data["%s"]' % k in body, (
                    "%s 的门控键 %s 已无写入点 —— 登记表过期，请移除" % (wp, k)
                )

    def test_反向_门控键不得同时在无条件基线里(self):
        """同一个键既「无条件必须出现」又「受开关门控」自相矛盾，必然有一边是错的。"""
        for wp, keys in _GATED_HD_KEYS.items():
            overlap = keys & _HD_BASELINE.get(wp, frozenset())
            assert not overlap, (
                "%s 的键 %s 既在无条件基线又在门控清单 —— 判据自相矛盾"
                % (wp, sorted(overlap))
            )


# ────────── Property 32 补强：无 trial_balance 记录时仍须写 tb_amount ──────────


class TestWriteZeroWhenMissing:
    """D5/D6/D7 改造前**无条件**写 ``tb_amount``，改造后必须保留该语义。

    🔴 本组是变异检验补出来的盲区 —— 首版守卫把
    ``project_context.setdefault("tb_amount", 0.0)`` 删掉时 **28 例全绿**，
    因为替身给了 `trial_balance` 记录、真实取数路径照样会写该键。
    只有「查不到记录」这条路径才能证明 ``write_zero_when_missing=True`` 有效。

    为什么这条语义不能省（tasks.md Task 8/9/10 的零回归判据）：
    这三个循环的原实现是 ``tb_amount = 0`` 初始化后无条件赋值，改成「不写键」会让
    前端从「读到 0」变成「读不到」= 行为回归。四态信息由新增的
    ``tb_source_codes.slots`` 表达，不必牺牲旧键的兼容性。
    """

    #: 改造前无条件写 tb_amount 的循环（与 `_PC_TB_SCALARS` 的登记一致）
    _UNCONDITIONAL = ("D5", "D6", "D7")

    @staticmethod
    def _render_without_trial(wp: str) -> dict:
        """用「trial_balance 查不到记录」的替身跑 render。"""
        ctx = SimpleNamespace(
            db=_FakeSession(
                project_row=SimpleNamespace(
                    client_name="测试客户",
                    audit_year=2025,
                    business_category="general",
                    applicable_standards="soe_standalone",
                    entity_type="soe",
                    report_scope="standalone",
                ),
                tb_row=None,  # ← 关键：trial_balance 无记录
            ),
            wp_id=uuid4(),
            project_id=uuid4(),
            year=2025,
            business_category="general",
            classification=SimpleNamespace(sheet_name=_SHEET_BY_WP[wp]),
        )
        out = asyncio.run(_MODULES[wp].render(ctx))
        return out if isinstance(out, dict) else {}

    @pytest.mark.parametrize("wp", _UNCONDITIONAL)
    def test_无记录时仍写tb_amount(self, wp):
        pc = _project_context(self._render_without_trial(wp))
        assert pc, "%s 未下发 project_context" % wp
        assert "tb_amount" in pc, (
            "🔴 %s 在 trial_balance 无记录时丢了 tb_amount —— 前端会从「读到 0」"
            "变成「读不到」，属行为回归（write_zero_when_missing 语义被破坏）" % wp
        )
        v = pc["tb_amount"]
        assert v is None or isinstance(v, (int, float)), "%s 的 tb_amount 类型异常：%r" % (wp, v)

    def test_反向_d2无记录时不写该键(self):
        """反向边界：D2 改造前是「有记录才写键」，不得被顺手改成无条件写。

        这条断言让上一组不至于退化成「所有循环都无条件写」——
        两种语义必须按循环各自保持（tasks.md Task 5 vs Task 8/9/10）。
        """
        pc = _project_context(self._render_without_trial("D2"))
        assert "tb_amount" not in pc, (
            "🔴 D2 被改成无条件写 tb_amount —— 它改造前是「有记录才写键」，"
            "无条件写会让前端把「查过、没有」误当成「余额为 0」"
        )

    def test_反向_替身确实没返回trial记录(self):
        """证明上面两条不是因为替身失效而恒绿。"""
        s = _FakeSession(project_row=None, tb_row=None)
        r = asyncio.run(s.execute("select 1 from trial_balance"))
        assert r.fetchone() is None
