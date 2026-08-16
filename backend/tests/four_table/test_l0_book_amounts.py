"""test_l0_book_amounts.py — L0-1 矩阵账面金额取数守卫（不连库）.

spec: l0-confirmation-source-alignment
  Requirements 3.3 / 3.4 / 8.1 / 10.1 / 10.4
  Property 11（复用 L 循环规格，不新写科目定位）
  Property 12（「无此科目」与「余额为 0」可区分）

## 真实库实证记录（`verify_l0_book_amounts_live.py --out`，2026-08-05）

11 个「项目 × 年度」组合 × 2 品种 = 22：
- 品种命中 16 / 缺失 6；**`parent_check` 非 0 的组合 = 0**（叶子聚合与父额勾稽全部成立）
- `conflicts` = 0；`resolved_from` 分布 `{account_chart_client: 10,
  account_chart_standard: 6, none: 6}` ⇒ 按科目名在**本项目**科目表定位生效
- 全部命中品种金额为 `0.00` —— postgres 直查证实全库 `2701`/`2502`/`2702` 的
  `closing_balance` 均为 `NULL` 或 `0.00`，即**样本项目确实无债务循环余额**，
  不是取数缺陷（同 F0 那轮「全库零函证明细行」情形，如实报告不用 fixture 冒充）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.services.four_table.l0_book_amounts import (  # noqa: E402
    L0_CATEGORY_BY_NAME,
    L0_MATRIX_CATEGORY_SPECS,
    L0BookAmountResult,
    L0CategorySpec,
    _absent_source,
    _sum_family,
)
from app.services.four_table.l_cycle_specs import L4_SPEC, L5_SPEC  # noqa: E402

MODULE_PATH = _REPO_ROOT / "backend" / "app" / "services" / "four_table" / "l0_book_amounts.py"
HELPERS_PATH = _REPO_ROOT / "backend" / "app" / "routers" / "wp_render_config_helpers.py"
RENDER_CONFIG_PATH = _REPO_ROOT / "backend" / "app" / "routers" / "wp_render_config.py"

#: 源模板 `函证结果汇总表L0-1!E29`/`F29` 逐字（同时是上区 E 列 SUMIF 的 criteria）
EXPECTED_CATEGORIES = ["长期应付款", "应付债券"]

#: 品种 → (报表行, 兜底码)。`report_config` 四准则一致实证
EXPECTED_ROW_CODES = {"长期应付款": ("BS-064", "2701"), "应付债券": ("BS-062", "2502")}

#: 其余六枢纽 —— 注入器必须对它们完全无副作用
OTHER_HUBS = ["D0", "E0", "F0", "G0", "H0", "K0"]


def _strip_comments_and_docstrings(src: str) -> str:
    """剥 `#` 注释与三引号串（含 docstring 与多行溯源文案）。

    🔴 配反向自检 :func:`test_strip_helper_actually_strips`，防剥离失效让断言空转。
    """
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    return re.sub(r"#[^\n]*", "", src)


@pytest.fixture(scope="module")
def module_src() -> str:
    return MODULE_PATH.read_text(encoding="utf-8")


# ─── Property 11：复用 L 循环规格，不新写科目定位 ────────────────────────────


class TestReusesLCycleSpecs:
    def test_two_categories_exact(self):
        assert [c.category for c in L0_MATRIX_CATEGORY_SPECS] == EXPECTED_CATEGORIES

    def test_spec_object_identity_is_l_cycle_specs(self):
        """🔴 `is` 判定 —— 必须是 `l_cycle_specs` 的那两个对象本身，不是复制品。

        复制品会让「改 l_cycle_specs 不影响 L0」，即制造双真源。
        """
        assert L0_CATEGORY_BY_NAME["长期应付款"].spec is L5_SPEC
        assert L0_CATEGORY_BY_NAME["应付债券"].spec is L4_SPEC

    @pytest.mark.parametrize("category", EXPECTED_CATEGORIES)
    def test_row_code_and_fallback(self, category):
        row_code, fallback = EXPECTED_ROW_CODES[category]
        spec = L0_CATEGORY_BY_NAME[category].spec
        assert spec.row_code == row_code
        slots = list(spec.slots)
        assert len(slots) == 1 and slots[0].key == "gross"
        assert tuple(slots[0].fallback_standard_codes) == (fallback,)

    def test_no_net_of_slots(self):
        """两品种均不扣减备抵 —— `BS-064`/`BS-062` 口径都是单码（2702 不减）。"""
        for cat in L0_MATRIX_CATEGORY_SPECS:
            assert cat.net_of_slots == (), f"{cat.category} 不应声明扣减槽"

    def test_no_direct_code_query_forms(self, module_src):
        """取数形态断言：不得出现按码直查（判据落在形态上，不是「源码不含数字」）。

        `formula_hint`/`notes` 逐字写明 `TB('2701')` 口径是**审计追溯能力**，
        一律禁数字会把它们一起禁掉。
        """
        code = _strip_comments_and_docstrings(module_src)
        forbidden = [
            r"LIKE\s*['\"]27",
            r"LIKE\s*['\"]25",
            r"startswith\(\s*['\"]27\d\d",
            r"startswith\(\s*['\"]25\d\d",
            r"filter_by_prefixes\(",
            r"account_code\s*==\s*['\"]\d{4}",
        ]
        for pat in forbidden:
            assert not re.search(pat, code), f"出现按码直查形态: {pat}"

    def test_semantic_resolver_is_the_only_entry(self, module_src):
        code = _strip_comments_and_docstrings(module_src)
        assert code.count("resolve_semantic_accounts(") >= 1
        # 未从别处 import 第二套科目定位
        assert "report_line_accounts" not in code, "不应引入第二套科目定位"
        assert "resolve_report_line_account_codes" not in code

    def test_leaf_aggregation_not_awaited(self, module_src):
        """🔴 `resolve_leaf_totals` / `to_leaf_rows` 是**同步纯函数**，`await` 会抛
        TypeError 并被 except 吞成 warning（G6 曾因此让审定表 TB seed 恒空）。"""
        code = _strip_comments_and_docstrings(module_src)
        assert "await resolve_leaf_totals" not in code
        assert "await to_leaf_rows" not in code

    def test_does_not_pre_select_leaves(self, module_src):
        """🔴 不能先 `select_leaves()` —— `resolve_leaf_totals` 要拿**父科目行**
        当符号约定的判定依据，预先剔除即退化成「原样求和」。"""
        code = _strip_comments_and_docstrings(module_src)
        assert "select_leaves(" not in code

    def test_absolute_applies_to_aggregate_only(self, module_src):
        """`absolute=True` 只作用于聚合结果；不得逐行 `abs()`。"""
        code = _strip_comments_and_docstrings(module_src)
        assert "absolute=True" in code
        assert not re.search(r"abs\(\s*(?:float\()?\s*r(?:ow)?\.", code), "疑似逐行取绝对值"

    def test_strip_helper_actually_strips(self, module_src):
        """反向自检：原始源码确实含被剥离的内容，剥后不含（防断言空转）。"""
        assert "TB('2701'" in module_src, "原文应含溯源文案里的口径说明"
        assert '"""' in module_src
        code = _strip_comments_and_docstrings(module_src)
        assert "🔴 **`2702 未确认融资费用` 不扣减**" not in code, "docstring 未被剥离"


# ─── Property 12：三态可区分 ────────────────────────────────────────────────


class TestThreeStateDistinction:
    def test_absent_source_returns_none_semantics(self):
        cat = L0_CATEGORY_BY_NAME["长期应付款"]
        src = _absent_source(cat, reason="解析失败")
        assert src["found"] is False
        assert src["resolved_from"] == "none"
        assert src["gross"] == []
        assert src["absent_reason"] == "解析失败"
        assert src["parent_check"] == {}

    def test_result_shape(self):
        r = L0BookAmountResult()
        r.amounts["长期应付款"] = None
        r.amounts["应付债券"] = 0.0
        d = r.as_dict()
        # 🔴 `None`（本项目无此科目）与 `0.0`（余额为 0）必须并存且不互相塌陷
        assert d["amounts"]["长期应付款"] is None
        assert d["amounts"]["应付债券"] == 0.0
        assert set(d) == {"amounts", "source_codes", "conflicts"}

    def test_zero_is_not_none(self):
        """反向自检：把 `None` 当 falsy 处理会让两态塌陷（`0.0 or None` 陷阱）。"""
        assert (None or 0.0) == 0.0          # 朴素写法会把 None 变 0.0
        assert 0.0 is not None                # 二者语义不同
        naive = {k: (v or 0.0) for k, v in {"a": None, "b": 0.0}.items()}
        assert naive["a"] == naive["b"], "复现朴素写法的塌陷（守卫据此禁止它）"

    def test_sum_family_on_empty_rows(self):
        total, diffs = _sum_family([], ["2701"])
        assert total == 0.0
        assert diffs == {"2701": 0.0}

    def test_category_spec_is_frozen(self):
        cat = L0_CATEGORY_BY_NAME["应付债券"]
        with pytest.raises(Exception):
            cat.category = "篡改"  # type: ignore[misc]

    def test_notes_carry_audit_trail(self):
        """溯源文案必须写明两条口径（审计追溯能力，不是可选装饰）。"""
        lp = L0_CATEGORY_BY_NAME["长期应付款"]
        blob = " ".join(lp.notes)
        assert "2702" in blob and "不扣减" in blob
        assert "2701.99" in blob and "BS-052" in blob
        assert "BS-064" in lp.formula_hint
        bp = L0_CATEGORY_BY_NAME["应付债券"]
        assert "BS-062" in bp.formula_hint
        assert "利息调整" in " ".join(bp.notes)


# ─── Property 12 / 10.1 / 10.2：注入器契约与零回归 ─────────────────────────


class TestInjectorContract:
    @pytest.fixture(scope="class")
    def helpers_src(self) -> str:
        return HELPERS_PATH.read_text(encoding="utf-8")

    def test_injector_exists(self, helpers_src):
        assert "async def _inject_l0_book_amounts(" in helpers_src

    def test_gate_before_fetch(self, helpers_src):
        """🔴 `wp_code` 前缀门控必须**早于**取数调用，否则为其余六枢纽白跑 DB。"""
        body_start = helpers_src.index("async def _inject_l0_book_amounts(")
        body = helpers_src[body_start:helpers_src.index("def inject_applicable_standards(")]
        gate = body.index('startswith("L0")')
        fetch = body.index("resolve_l0_book_amounts(")
        assert gate < fetch, "门控晚于取数调用"

    def test_writes_only_project_context_keys(self, helpers_src):
        body_start = helpers_src.index("async def _inject_l0_book_amounts(")
        body = helpers_src[body_start:helpers_src.index("def inject_applicable_standards(")]
        assert 'ctx["l0_book_amounts"]' in body
        assert 'ctx["l0_book_source_codes"]' in body
        # 不改 rows / _format
        assert '["rows"]' not in body
        assert '"_format"' not in body

    def test_not_registered_in_renderer_dispatch(self):
        """🔴 `confirmation-summary` 是七枢纽共享 componentType，
        注册进 `RENDERER_DISPATCH` 会让另六个枢纽载荷一起改道。"""
        from app.routers.wp_render_strategies import RENDERER_DISPATCH  # noqa: PLC0415

        assert "confirmation-summary" not in RENDERER_DISPATCH

    def test_hooked_once_in_render_config(self):
        src = RENDER_CONFIG_PATH.read_text(encoding="utf-8")
        assert src.count("await _inject_l0_book_amounts(") == 1
        assert src.count("_inject_l0_book_amounts,") == 1  # import 一次

    @pytest.mark.parametrize("hub", OTHER_HUBS)
    def test_other_hubs_not_mentioned_in_l0_module(self, hub, module_src):
        """L0 取数模块不得引用其余六枢纽（零回归的结构性保证）。"""
        code = _strip_comments_and_docstrings(module_src)
        assert f'"{hub}' not in code, f"L0 模块不应引用 {hub}"

    def test_h0_injector_still_hooked(self):
        """反向断言：并存的 H0 注入器未被本改动挤掉。"""
        src = RENDER_CONFIG_PATH.read_text(encoding="utf-8")
        assert src.count("await _inject_h0_book_amounts(") == 1


class TestInjectorGuardSelfCheck:
    """门控判据的**替身**反向自检 —— 不碰磁盘。

    🔴 为什么用替身而不是磁盘变异：`wp_render_config_helpers.py` 是**共享热点文件**
    （多 spec 同时改），磁盘变异脚本一旦被中断（Ctrl+C），`finally` 的内存备份丢失，
    会把变异状态留在文件里 —— 本轮实测踩过一次：门控行被删且下一轮变异脚本把
    「已删门控」当成了原文基线。共享文件的判据一律用替身验证。
    """

    #: 正确形态：门控在取数之前
    GOOD = (
        'async def _inject_l0_book_amounts(a, b, c, wp_code, sheet_html_data):\n'
        '    if not isinstance(sheet_html_data, dict):\n'
        '        return\n'
        '    if not str(wp_code or "").strip().upper().startswith("L0"):\n'
        '        return\n'
        '    from x import resolve_l0_book_amounts\n'
        '    result = await resolve_l0_book_amounts(ctx)\n'
    )
    #: 缺陷形态一：门控晚于取数（为其余六枢纽白跑 DB）
    LATE_GATE = (
        'async def _inject_l0_book_amounts(a, b, c, wp_code, sheet_html_data):\n'
        '    from x import resolve_l0_book_amounts\n'
        '    result = await resolve_l0_book_amounts(ctx)\n'
        '    if not str(wp_code or "").strip().upper().startswith("L0"):\n'
        '        return\n'
    )
    #: 缺陷形态二：门控整体缺失（本轮真实踩过 —— 变异脚本中断残留）
    NO_GATE = (
        'async def _inject_l0_book_amounts(a, b, c, wp_code, sheet_html_data):\n'
        '    from x import resolve_l0_book_amounts\n'
        '    result = await resolve_l0_book_amounts(ctx)\n'
    )

    @staticmethod
    def _gate_is_before_fetch(body: str) -> bool:
        """与 :meth:`TestInjectorContract.test_gate_before_fetch` 同一判据。"""
        if 'startswith("L0")' not in body:
            return False
        return body.index('startswith("L0")') < body.index("resolve_l0_book_amounts(")

    def test_judgement_accepts_good_form(self):
        assert self._gate_is_before_fetch(self.GOOD)

    def test_judgement_rejects_late_gate(self):
        assert not self._gate_is_before_fetch(self.LATE_GATE)

    def test_judgement_rejects_missing_gate(self):
        assert not self._gate_is_before_fetch(self.NO_GATE)

    def test_real_source_passes_same_judgement(self):
        """替身判据施加于真实源码 —— 与 `test_gate_before_fetch` 互为交叉验证。"""
        src = HELPERS_PATH.read_text(encoding="utf-8")
        start = src.index("async def _inject_l0_book_amounts(")
        body = src[start:src.index("def inject_applicable_standards(")]
        assert self._gate_is_before_fetch(body)
