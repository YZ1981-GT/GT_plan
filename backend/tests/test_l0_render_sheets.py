"""L0 隐藏 sheet 不进 render-config —— 复合键 skip 判定的守卫。

spec: l0-confirmation-source-alignment，Task 19（Property 25 / 26 / 27）

背景（2026-08-05 实证）
----------------------
`函证差异检查表（示例）` 在**三处**函证模板里的可见性不同：

| 模板 | sheet_state |
|---|---|
| `L0 债务循环函证.xlsx` | **hidden** |
| `D0 收入循环函证.xlsx` | visible |
| `F0 存货循环函证.xlsx` | visible |

而 `wp_render_config.py` 改造前的三条 skip 判定（完整 sheet_name / 尾码 / 首码）
**都不带 wp_code 维度** → 按裸 sheet 名标 `skip` 会连 D0/F0 的真实页签一起杀掉。
故新增第四条 `{wp_code}-{sheet_name}` 复合键判定，**接在三条之后**（既有命中路径优先）。

守卫形态
--------
复刻 `wp_render_config.py` 的**四段** skip 判定（前三段与
`test_e0_hidden_sheets_skipped.py` 的 `is_skipped` 同构，第四段是本 spec 新增），
对 L0/D0/F0 三册源模板逐 sheet 双向断言：

- L0 的 hidden sheet → 必须被 skip（漏配即红）
- L0 的 visible sheet → 必须**不**被 skip（误伤即红）
- D0/F0 的 `函证差异检查表（示例）` → 必须**不**被 skip（Property 26 的核心）

反向自检（Property 26）
-----------------------
`test_bare_key_would_kill_d0_f0` 用**裸键替身** override 复现「按裸名标 skip」的
错误落法，断言 D0/F0 的真实页签确实会被杀掉 —— 证明复合键不是多余设计。
不做磁盘变异（`wp_code_overrides.json` 是多 spec 共同改动的热点文件，
memory 已记「变异脚本被中断会留下残留」）。
"""
from __future__ import annotations

import re
from pathlib import Path

import openpyxl
import pytest

from app.routers.wp_render_config import _SHEET_CODE_RE
from app.services.wp_classification_service import refresh_wp_code_overrides

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TPL_DIR = _REPO_ROOT / "backend" / "wp_templates"

_L0_XLSX = _TPL_DIR / "L" / "L0 债务循环函证.xlsx"
_D0_XLSX = _TPL_DIR / "D" / "D0 收入循环函证.xlsx"
_F0_XLSX = _TPL_DIR / "F" / "F0 存货循环函证.xlsx"

#: 三册共有的那张歧义 sheet（L0 hidden / D0·F0 visible）
_AMBIGUOUS_SHEET = "函证差异检查表（示例）"

#: L0 源模板实测：10 张 sheet = 9 visible + 1 hidden
#: （数量锚点作反向自检：路径错 → 空集合 → 双向断言恒真）
_L0_TOTAL = 10
_L0_VISIBLE = 9

#: L0 的 9 张可见 sheet（顺序同源 xlsx；Property 25 逐位比对）
_L0_EXPECTED_VISIBLE: list[str] = [
    "底稿目录",
    "函证程序表F0A",
    "函证结果汇总表L0-1",
    "核实被函证单位信息L0-2",
    "跟函函证过程控制L0-3",
    "函证差异调节表L0-4",
    "长期应付款替代程序L0-5",
    "邮件传真回函可靠性验证L0-6",
    "函证程序舞弊风险评价表L0-7",
]


# ─── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def overrides() -> dict[str, str]:
    return refresh_wp_code_overrides()


def _sheet_states(xlsx: Path) -> list[tuple[str, str]]:
    assert xlsx.exists(), f"源模板不存在：{xlsx}"
    wb = openpyxl.load_workbook(xlsx)
    try:
        return [(name, wb[name].sheet_state) for name in wb.sheetnames]
    finally:
        wb.close()


@pytest.fixture(scope="module")
def l0_states() -> list[tuple[str, str]]:
    return _sheet_states(_L0_XLSX)


@pytest.fixture(scope="module")
def d0_states() -> list[tuple[str, str]]:
    return _sheet_states(_D0_XLSX)


@pytest.fixture(scope="module")
def f0_states() -> list[tuple[str, str]]:
    return _sheet_states(_F0_XLSX)


# ─── skip 判定复刻（四段，顺序与生产代码一致） ──────────────────────────────


def is_skipped(
    sheet_name: str,
    ovr: dict[str, str],
    wp_code: str | None = None,
) -> str | None:
    """复刻 `wp_render_config.py` 的四段 skip 判定。

    返回命中的判定名（`full_name` / `tail_code` / `head_code` / `compound`），
    未命中返回 `None` —— 返回**命中路径名**而不是 bool，
    使 Property 27「既有路径优先」可被直接断言。
    """
    # 1) 完整 sheet_name 精确匹配
    if ovr.get(sheet_name) == "skip":
        return "full_name"
    # 2) 尾部编码
    m = _SHEET_CODE_RE.search(sheet_name)
    if m and ovr.get(m.group(1)) == "skip":
        return "tail_code"
    # 3) 编码在开头（仅当尾码未匹配到时才尝试，与生产代码一致）
    if not m:
        m2 = re.match(r"([A-Z]\d+(?:-\d+)*)", sheet_name)
        if m2 and ovr.get(m2.group(1)) == "skip":
            return "head_code"
    # 4) 复合键（本 spec 新增，接在三条之后）
    if wp_code and ovr.get(f"{wp_code}-{sheet_name}") == "skip":
        return "compound"
    return None


class TestSkipPredicateSelfCheck:
    """判定函数自身的反向自检 —— 防「判定恒 None → 双向断言全绿」的空转。"""

    def test_full_name_path_reachable(self, overrides):
        """全名路径确实可命中（拿一个已知全名 skip 条目验证）。"""
        full_name_keys = [
            k for k, v in overrides.items()
            if v == "skip" and not re.fullmatch(r"[A-Z]\d+(?:-\d+)*[A-Z]?", k)
            and "-" not in k
        ]
        assert full_name_keys, "override 里没有任何『非编码形态』的 skip 键，判定 1 无法验证"

    def test_compound_path_reachable(self, overrides):
        """复合键路径确实可命中 —— 本 spec 的核心条目必须在册。"""
        key = f"L0-{_AMBIGUOUS_SHEET}"
        assert overrides.get(key) == "skip", (
            f"复合键 {key!r} 未登记为 skip → Property 25 的 L0 断言会变成空转。"
            "请检查 backend/app/data/wp_code_overrides.json"
        )

    def test_unknown_sheet_not_skipped(self, overrides):
        """无关 sheet 名不得被判 skip（判定不是恒真）。"""
        assert is_skipped("这是一个不存在的表名XYZ", overrides, "L0") is None


class TestSourceTemplateFacts:
    """Property 25 / 26 的事实基础 —— 三册模板的可见性分布。"""

    def test_l0_sheet_counts(self, l0_states):
        assert len(l0_states) == _L0_TOTAL, [n for n, _ in l0_states]
        visible = [n for n, st in l0_states if st == "visible"]
        assert len(visible) == _L0_VISIBLE, visible

    def test_l0_ambiguous_sheet_is_hidden(self, l0_states):
        states = dict(l0_states)
        assert _AMBIGUOUS_SHEET in states, f"L0 源 xlsx 无此 tab：{_AMBIGUOUS_SHEET}"
        assert states[_AMBIGUOUS_SHEET] == "hidden", (
            f"L0 的 {_AMBIGUOUS_SHEET} 实为 {states[_AMBIGUOUS_SHEET]}"
            "（本 spec 的前提是它在 L0 为 hidden）"
        )

    def test_d0_ambiguous_sheet_is_visible(self, d0_states):
        states = dict(d0_states)
        assert states.get(_AMBIGUOUS_SHEET) == "visible", (
            f"D0 的 {_AMBIGUOUS_SHEET} 实为 {states.get(_AMBIGUOUS_SHEET)!r}"
            "（若它在 D0 也是 hidden，裸键 skip 就不再有害，本 spec 的复合键设计需重议）"
        )

    def test_f0_ambiguous_sheet_is_visible(self, f0_states):
        states = dict(f0_states)
        assert states.get(_AMBIGUOUS_SHEET) == "visible", (
            f"F0 的 {_AMBIGUOUS_SHEET} 实为 {states.get(_AMBIGUOUS_SHEET)!r}"
        )

    def test_l0_visible_sheets_match_expected_list(self, l0_states):
        """可见 sheet 清单逐位相等（顺序亦一致）—— 前端守卫的交叉锁死源。"""
        visible = [n for n, st in l0_states if st == "visible"]
        assert visible == _L0_EXPECTED_VISIBLE, visible


class TestProperty25HiddenNotRendered:
    """Property 25: L0 render-config sheets 恰 9 项，与可见 sheet 逐字一致。"""

    def test_every_hidden_sheet_is_skipped(self, l0_states, overrides):
        leaked = [
            name for name, st in l0_states
            if st != "visible" and is_skipped(name, overrides, "L0") is None
        ]
        assert not leaked, (
            f"L0 源模板的隐藏 sheet 未被 skip，会渲染成多余页签：{leaked}。"
            "请在 wp_code_overrides.json 按 `L0-{sheet_name}` 复合键标 skip。"
        )

    def test_no_visible_sheet_is_skipped(self, l0_states, overrides):
        killed = [
            name for name, st in l0_states
            if st == "visible" and is_skipped(name, overrides, "L0") is not None
        ]
        assert not killed, (
            f"L0 真实底稿被 skip 误伤：{killed}。"
            "常见成因 = 按尾部编码标 skip 而非完整 sheet_name / 复合键。"
        )

    def test_surviving_sheets_equal_visible_list(self, l0_states, overrides):
        """存活集合 == 可见清单（顺序一致）—— Property 25 的完整断言。"""
        surviving = [
            name for name, _ in l0_states
            if is_skipped(name, overrides, "L0") is None
        ]
        assert surviving == _L0_EXPECTED_VISIBLE, surviving
        assert len(surviving) == _L0_VISIBLE

    def test_l0_hidden_sheet_hit_by_compound_path(self, overrides):
        """L0 的那张 hidden sheet 必须由**复合键**命中（而非其它三条误命中）。

        若它被全名/尾码路径命中，说明有人在裸键上标了 skip → D0/F0 会被误伤。
        """
        hit = is_skipped(_AMBIGUOUS_SHEET, overrides, "L0")
        assert hit == "compound", (
            f"L0 的 {_AMBIGUOUS_SHEET} 由 {hit!r} 路径命中，预期 'compound'。"
            "若是 full_name，说明裸键被标成了 skip → 请查 Property 26。"
        )


class TestProperty26CompoundKeyNotHarmingD0F0:
    """Property 26: 复合键 skip 不误伤同名可见 sheet。"""

    def test_bare_key_is_not_skip(self, overrides):
        """裸键必须仍是 componentType 而不是 skip（D0/F0 的组件来源）。"""
        val = overrides.get(_AMBIGUOUS_SHEET)
        assert val != "skip", (
            f"裸键 {_AMBIGUOUS_SHEET!r} 被标成 skip → D0/F0 的真实页签会被杀掉。"
        )
        assert val == "confirmation-diff-checklist", (
            f"裸键 {_AMBIGUOUS_SHEET!r} 的 componentType 实为 {val!r}，"
            "预期 'confirmation-diff-checklist'（D0/F0 渲染该表的组件来源）"
        )

    def test_d0_ambiguous_sheet_survives(self, overrides):
        assert is_skipped(_AMBIGUOUS_SHEET, overrides, "D0") is None, (
            f"D0 的 {_AMBIGUOUS_SHEET} 被 skip 误伤"
        )

    def test_f0_ambiguous_sheet_survives(self, overrides):
        assert is_skipped(_AMBIGUOUS_SHEET, overrides, "F0") is None, (
            f"F0 的 {_AMBIGUOUS_SHEET} 被 skip 误伤"
        )

    def test_d0_no_visible_sheet_is_skipped(self, d0_states, overrides):
        killed = [
            name for name, st in d0_states
            if st == "visible" and is_skipped(name, overrides, "D0") is not None
        ]
        assert not killed, f"D0 真实底稿被 skip 误伤：{killed}"

    def test_f0_no_visible_sheet_is_skipped(self, f0_states, overrides):
        killed = [
            name for name, st in f0_states
            if st == "visible" and is_skipped(name, overrides, "F0") is not None
        ]
        assert not killed, f"F0 真实底稿被 skip 误伤：{killed}"

    def test_bare_key_would_kill_d0_f0(self, overrides):
        """🔴 反向自检：用**替身 override** 复现「裸键 skip」的错误落法。

        断言 D0/F0 的真实页签确实会被杀掉 → 证明复合键不是多余设计。
        用替身而不做磁盘变异：`wp_code_overrides.json` 是多 spec 热点文件。
        """
        bad = dict(overrides)
        bad[_AMBIGUOUS_SHEET] = "skip"          # 错误落法
        bad.pop(f"L0-{_AMBIGUOUS_SHEET}", None)  # 撤掉复合键

        # L0 侧看起来"也修好了"（这正是它容易被误采纳的原因）
        assert is_skipped(_AMBIGUOUS_SHEET, bad, "L0") == "full_name"
        # 但 D0/F0 的真实页签同时被杀
        assert is_skipped(_AMBIGUOUS_SHEET, bad, "D0") == "full_name", (
            "替身变异未复现误伤 → 本反向自检失效，请检查判定函数"
        )
        assert is_skipped(_AMBIGUOUS_SHEET, bad, "F0") == "full_name"

    def test_compound_key_without_wp_code_is_inert(self, overrides):
        """复合键在 `wp_code` 缺失时不生效（不会误伤未知调用方）。"""
        assert is_skipped(_AMBIGUOUS_SHEET, overrides, None) is None


class TestProperty27ExistingPathsUnchanged:
    """Property 27: 既有三条判定优先，且全库既有 skip 行为逐条不变。"""

    def test_compound_check_is_last_in_source(self):
        """源码级：复合键判定的位置在既有三条之后。"""
        src = (
            _REPO_ROOT / "backend" / "app" / "routers" / "wp_render_config.py"
        ).read_text(encoding="utf-8")

        i_full = src.find('_WP_CODE_OVERRIDE.get(cls.sheet_name) == "skip"')
        i_tail = src.find('_WP_CODE_OVERRIDE.get(_skip_m.group(1)) == "skip"')
        i_head = src.find('_WP_CODE_OVERRIDE.get(_skip_m2.group(1)) == "skip"')
        i_comp = src.find('_WP_CODE_OVERRIDE.get(f"{wp_code}-{cls.sheet_name}") == "skip"')

        for name, idx in (
            ("full_name", i_full), ("tail_code", i_tail),
            ("head_code", i_head), ("compound", i_comp),
        ):
            assert idx > 0, f"未在 wp_render_config.py 找到 {name} 判定（守卫会空转）"

        assert i_full < i_tail < i_head < i_comp, (
            f"skip 判定顺序错：full={i_full} tail={i_tail} head={i_head} compound={i_comp}。"
            "复合键必须**最后**，否则既有命中路径的优先级被改变（Property 27）。"
        )

    def test_characterization_all_existing_skip_entries_unchanged(self, overrides):
        """characterization：不传 wp_code 时的判定结果 ≡ 改造前的三段判定。

        改造前的行为等价于「四段判定但 wp_code=None」（第四段 inert）。
        对全库既有 skip 键逐条比对 —— 复合键不改变任何既有条目的命中路径。
        """
        # 🔴 覆盖**全部**非复合形态的 skip 键（绝大多数是编码形态如 `A1-11`，
        #    走尾码/首码路径；只按「不含连字符」过滤会只剩 7 条 → characterization 失去意义）。
        legacy_only_skip_keys = [
            k for k, v in overrides.items()
            if v == "skip" and not re.match(r"^[A-Z]\d+[A-Z]?-\D", k)
        ]
        assert len(legacy_only_skip_keys) > 200, (
            f"既有 skip 键样本过少（{len(legacy_only_skip_keys)}）→ characterization 无意义。"
            "全库既有 skip 条目实测 250+，样本骤降说明 overrides 加载异常或过滤器写错。"
        )
        for key in legacy_only_skip_keys:
            # 对这些键本身作为 sheet_name 时，两种调用必须同路径
            without = is_skipped(key, overrides, None)
            with_wp = is_skipped(key, overrides, "ZZ99")  # 不存在的 wp_code
            assert without == with_wp, (
                f"{key!r} 的判定受 wp_code 影响（{without!r} vs {with_wp!r}）→ 既有行为被改变"
            )

    def test_compound_entries_are_scoped(self, overrides):
        """全库复合键 skip 条目一律带 `{wp_code}-` 前缀且指向真实循环。"""
        compound = {
            k: v for k, v in overrides.items()
            if v == "skip" and re.match(r"^[A-Z]\d+[A-Z]?-\D", k)
        }
        assert f"L0-{_AMBIGUOUS_SHEET}" in compound, (
            f"本 spec 的复合键条目不在册：{sorted(compound)[:5]}"
        )
        for key in compound:
            wp, _, sheet = key.partition("-")
            assert wp and sheet, f"复合键形态异常：{key!r}"

    def test_l0_component_types_intact(self, overrides):
        """L0 的九张可见 sheet 的 componentType 映射未被 skip 污染。"""
        expected = {
            "L0": "confirmation-hub",
            "L0A": "a-program-console",
            "L0-1": "confirmation-summary",
            "L0-2": "confirmation-entity-verify",
            "L0-3": "confirmation-followup",
            "L0-4": "confirmation-diff-reconcile",
            "L0-5": "confirmation-alternative-l05",
            "L0-6": "confirmation-reliability",
            "L0-7": "confirmation-fraud-risk",
        }
        for code, ct in expected.items():
            assert overrides.get(code) == ct, (
                f"{code} 的 componentType 实为 {overrides.get(code)!r}，预期 {ct!r}"
            )
