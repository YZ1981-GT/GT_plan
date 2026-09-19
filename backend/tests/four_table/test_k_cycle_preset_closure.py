"""K 循环公式预设收口守卫（Task 11 / Task 13）—— Property 18~25。

判据真源：
- sheet 名 → `backend/wp_templates/K/*.xlsx` 的 openpyxl `wb.sheetnames`（运行时权威）
- 科目族 → `four_table/k_cycle_specs.K_CYCLE_SPECS`（声明真源）
- 期间字面量 → `app/services/formula_engine.COLUMN_ALIASES`（已注册集合）

每条守卫都配反向自检（复现旧缺陷形态必打红），见各 `*_self_check`。

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 6.1~6.13 / Property 18, 19, 20, 21, 22, 23, 24, 25
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS

_ROOT = Path(__file__).resolve().parents[3]
_MAPPING = _ROOT / "backend/data/prefill_formula_mapping.json"
_TPL_DIR = _ROOT / "backend/wp_templates/K"

#: 项目专属辅助项编码形态（Property 22）—— 写死它们会让预设对其余项目静默返 0
_AUX_CODE_RE = re.compile(r"\b(?:YG\d+|SKT\d+|A\d{3})\b")

#: 合法 `formula_type`（与 `formula_management/preset_library` 词汇表一致）。
#:
#: `PLACEHOLDER` 是 Requirement 6.5 明确允许的形态 —— 列名尚未在 `COLUMN_ALIASES`
#: 注册时，用它 + description 写明真源，而不是硬塞一个注册名把错误固化。
#: K0 的两条 `K0-1-matrix-*-book_amount` 走的就是这条（函证枢纽的账面额来自 K1/K3）。
_LEGAL_TYPES = {
    "TB",
    "TB_SUM",
    "ADJ",
    "PREV",
    "WP",
    "AUX",
    "LEDGER_DETAIL",
    "PLACEHOLDER",
}


# ─────────────────────────────────────────────────────────────────────────────
# fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def raw_text() -> str:
    return _MAPPING.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def k_blocks(raw_text: str) -> list[dict]:
    data = json.loads(raw_text)
    return [
        b
        for b in data["mappings"]
        if str(b.get("wp_code", "")).upper().startswith("K")
    ]


@pytest.fixture(scope="module")
def real_sheets() -> set[str]:
    """源 xlsx 真实 tab 名（含隐藏）。空集时整体 skip，避免空转。"""
    from openpyxl import load_workbook

    out: set[str] = set()
    for f in sorted(_TPL_DIR.glob("*.xlsx")):
        if f.name.startswith("~$"):
            continue
        wb = load_workbook(f, read_only=True, data_only=True)
        out.update(wb.sheetnames)
        wb.close()
    return out


@pytest.fixture(scope="module")
def registered_columns() -> set[str]:
    from app.services.formula_engine import COLUMN_ALIASES

    cols: set[str] = set()
    for k, v in COLUMN_ALIASES.items():
        cols.add(str(k))
        if isinstance(v, str):
            cols.add(v)
        elif isinstance(v, (list, tuple, set)):
            cols.update(str(x) for x in v)
    return cols


def _cells(b: dict) -> list[dict]:
    return b.get("cells") or b.get("entries") or []


def _sheet_args(formula: str) -> list[str]:
    """取 `PREV()`/`WP()` 的第二实参（sheet 名）。"""
    return [
        m.group(1)
        for m in re.finditer(r"(?:PREV|WP)\(\s*'[^']*'\s*,\s*'([^']*)'", str(formula or ""))
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 判据基础设施自检（防整体空转）
# ─────────────────────────────────────────────────────────────────────────────


def test_fixtures_are_nonempty(k_blocks, real_sheets, registered_columns):
    """三个判据源都必须非空 —— 任一为空会让下面全部断言空转。"""
    assert len(k_blocks) >= 20, f"K 预设块过少（{len(k_blocks)}），判据源可疑"
    assert len(real_sheets) >= 80, f"源 xlsx tab 名过少（{len(real_sheets)}）"
    assert "本期发生额" in registered_columns, "COLUMN_ALIASES 未注册「本期发生额」"
    assert "期末余额" in registered_columns


# ─────────────────────────────────────────────────────────────────────────────
# Property 19：formula_type 齐备
# ─────────────────────────────────────────────────────────────────────────────


def test_every_cell_has_formula_type(k_blocks):
    """K 前缀全部预设块的每个 cell 必须有 `formula_type`。"""
    missing = [
        (b.get("wp_code"), b.get("sheet"), c.get("cell_ref"))
        for b in k_blocks
        for c in _cells(b)
        if (c.get("formula") or "") and not c.get("formula_type")
    ]
    assert not missing, f"缺 formula_type 的 cell（{len(missing)} 个）：{missing[:10]}"


def test_formula_types_are_legal(k_blocks):
    """`formula_type` 取值都在合法集合内（不新增未登记类型）。"""
    illegal = [
        (b.get("wp_code"), c.get("cell_ref"), c.get("formula_type"))
        for b in k_blocks
        for c in _cells(b)
        if c.get("formula_type") and c["formula_type"] not in _LEGAL_TYPES
    ]
    assert not illegal, f"非法 formula_type：{illegal}"


def test_formula_type_matches_formula(k_blocks):
    """`formula_type` 与公式里的函数名一致（防贴错标签）。"""
    mismatched = []
    for b in k_blocks:
        for c in _cells(b):
            f, t = str(c.get("formula") or ""), str(c.get("formula_type") or "")
            if not f or not t:
                continue
            if f"{t}(" not in f:
                mismatched.append((b.get("wp_code"), c.get("cell_ref"), t, f))
    assert not mismatched, f"formula_type 与公式不符：{mismatched}"


# ─────────────────────────────────────────────────────────────────────────────
# Property 23：sheet 名逐字对齐源 xlsx
# ─────────────────────────────────────────────────────────────────────────────


def test_block_sheet_exists_in_source(k_blocks, real_sheets):
    """每个块的 `sheet` 必须是源 xlsx 真实 tab 名（空格是源模板事实，须保留）。"""
    bad = [
        (b.get("wp_code"), b.get("sheet"))
        for b in k_blocks
        if str(b.get("sheet", "")) not in real_sheets
    ]
    assert not bad, (
        f"block.sheet 在源 xlsx 不存在 ⇒ 该块运行时永不命中：{bad}"
    )


def test_formula_sheet_args_exist_in_source(k_blocks, real_sheets):
    """`PREV()`/`WP()` 的 sheet 实参也必须是真实 tab 名。

    实测踩过：K5 的 `PREV('K5','审定表K5-1',…)` 丢了空格（源真名「审定表 K5-1」），
    指向不存在的 tab ⇒ 该引用永不命中，而 JSON 里是字符串、静态检查查不出。
    """
    # 跨循环引用（如 K8 引 H1 的折旧分配表）不在 K 目录，按前缀放行
    bad = []
    for b in k_blocks:
        for c in _cells(b):
            for arg in _sheet_args(c.get("formula")):
                if arg in real_sheets:
                    continue
                if re.match(r"^[A-Z]\d", arg) and not arg.startswith("K"):
                    continue  # 跨循环 tab（H1-13 等），不在 K 目录
                if "K" not in arg:
                    continue  # 形如「审定表」的跨循环泛引用（J1/I1），另案
                bad.append((b.get("wp_code"), c.get("cell_ref"), arg))
    assert not bad, f"公式实参 sheet 名在源 xlsx 不存在：{bad}"


def test_source_template_really_has_spaced_tabs(real_sheets):
    """反向自检：源 xlsx 里**确实**存在带空格的 tab 名。

    防有人把空格当笔误、连同源模板一起「清理」掉 —— 那样上面两条会全绿而实际全错。
    """
    spaced = {s for s in real_sheets if re.search(r"表\s+K\d", s)}
    assert spaced, "源 xlsx 里没有带空格的 tab 名 —— 请复核，勿据此放宽空格判据"
    assert "审定表 K5-1" in real_sheets
    assert "明细表 K5-2" in real_sheets


# ─────────────────────────────────────────────────────────────────────────────
# Property 20：损益类口径
# ─────────────────────────────────────────────────────────────────────────────


def _is_pl_block(b: dict) -> bool:
    accts = [str(a) for a in (b.get("account_codes") or [])]
    return bool(accts) and all(a.startswith("6") for a in accts)


def test_pl_blocks_use_occurrence_caliber(k_blocks):
    """损益类块不得用余额口径（费用是发生额、不结转余额）。"""
    bad = [
        (b.get("wp_code"), b.get("sheet"), c.get("cell_ref"), c.get("formula"))
        for b in k_blocks
        if _is_pl_block(b)
        for c in _cells(b)
        if re.search(r"'(?:期初余额|期末余额)'", str(c.get("formula") or ""))
    ]
    assert not bad, f"损益类误用余额口径：{bad}"


def test_pl_prior_period_goes_through_prev(k_blocks):
    """损益类的「期初」格必须走 `PREV()`，不得与「未审数」共用同一个 `TB()`。"""
    offenders = []
    for b in k_blocks:
        if not _is_pl_block(b):
            continue
        by_ref = {str(c.get("cell_ref") or ""): str(c.get("formula") or "") for c in _cells(b)}
        for ref, f in by_ref.items():
            if "期初" not in ref:
                continue
            if "PREV(" not in f:
                offenders.append((b.get("wp_code"), b.get("sheet"), ref, f))
                continue
            # 且不得与别的格公式逐字相同
            same = [r for r, g in by_ref.items() if r != ref and g == f]
            if same:
                offenders.append(
                    (b.get("wp_code"), b.get("sheet"), ref, f"与 {same} 逐字相同")
                )
    assert not offenders, f"损益类期初格口径错：{offenders}"


def test_prev_is_fail_closed_and_registered_as_out_of_scope():
    """🔴 `PREV()` **当前恒返 None**（fail-closed）—— 本条钉死这个事实，防误判。

    这条守卫的价值不在「检查预设写得对不对」，而在**防止下一个人误以为 `PREV()` 能
    取到上年数**。实证（`prefill_engine._resolve_prev_formula` 的实现与 docstring）：

    - `working_paper` / `wp_index` **都没有 `year` 列**，底稿的年度维度只在 project 层；
    - 改造前的实现声称「从上年底稿取值」，但查询里**没有任何 year 条件**，
      取值又走真实库零命中的 `parsed_data['cells']` ⇒ 表面恒返 None；
    - 全平台 161 条 `PREV()` 里 **117 条**第三参是「审定数」，若哪天有人把
      `cells` 链「修通」而不修年度维度，它会取到**本年**值并显示在「上年数」列 ——
      那是数字级错误，比现在的恒空危险得多；
    - 故该函数 fail-closed：宁缺勿造，绝不回退本年值。跨年度取数需数据模型变更，
      已登记在 `prefill_anchor_map.OUT_OF_SCOPE_CHANGES['prev_year_dimension']`。

    **对本 spec 的含义**：Task 11 把 K8/K9/K10~K13 六个「期初余额」格从
    `TB('6xxx', …)` 改成 `PREV(…)` 后，这些格**取不到数**。这是有意的改进 ——
    改前它们与「未审数」格公式**逐字相同**（本期发生额冒充期初数 = 错数，会被
    审计师当真并污染同比分析），改后是显示空、由审计师手工填。
    """
    import inspect

    from app.services import prefill_anchor_map as pam
    from app.services.prefill_engine import _resolve_prev_formula

    body = inspect.getsource(_resolve_prev_formula)
    stripped = re.sub(r'"""[\s\S]*?"""', "", body)
    assert re.search(r"return\s+None", stripped), (
        "`_resolve_prev_formula` 不再 fail-closed。若已实现真正的跨年度取数，"
        "请同时更新本守卫与 OUT_OF_SCOPE_CHANGES 登记；若只是把 cells 链修通而"
        "**没有**加年度条件，那会取到本年值冒充上年数 —— 必须回退。"
    )
    out_of_scope = getattr(pam, "OUT_OF_SCOPE_CHANGES", {})
    assert "prev_year_dimension" in out_of_scope, (
        "跨年度取数的登记条目消失了 —— 该缺口必须一直有案可查"
    )


def test_prev_third_arg_is_chinese_anchor_name(k_blocks):
    """`PREV()` 第三参是**底稿业务锚点名**（中文列/格名），不是预设 cell_ref。

    这条把「第三参该长什么样」钉死，避免有人按 cell_ref 的形态去改它。
    实测全平台第三参形态：`审定数`(117) / `期末账面价值`(12) / `未审数`(6) …
    —— 都是底稿里的**列名**，与预设 cell_ref 是两套命名。
    """
    bad = []
    for b in k_blocks:
        for c in _cells(b):
            for m in re.finditer(
                r"PREV\(\s*'[^']*'\s*,\s*'[^']*'\s*,\s*'([^']*)'", str(c.get("formula") or "")
            ):
                arg = m.group(3 - 2)  # 第三参
                if not arg.strip() or not re.search(r"[\u4e00-\u9fff]", arg):
                    bad.append((b.get("wp_code"), c.get("cell_ref"), arg))
    assert not bad, f"PREV 第三参不是中文业务锚点名：{bad}"


# ─────────────────────────────────────────────────────────────────────────────
# Property 21：列名已注册
# ─────────────────────────────────────────────────────────────────────────────


def test_period_literals_are_registered(k_blocks, registered_columns):
    """`TB()`/`TB_SUM()`/`AUX()` 用的期间字面量必须在 `COLUMN_ALIASES` 已注册。"""
    unknown = []
    for b in k_blocks:
        for c in _cells(b):
            f = str(c.get("formula") or "")
            for fn, args in re.findall(r"\b(TB|TB_SUM|AUX)\(([^)]*)\)", f):
                parts = re.findall(r"'([^']*)'", args)
                idx = 3 if fn == "AUX" else 1
                if len(parts) > idx and parts[idx] not in registered_columns:
                    unknown.append(
                        (b.get("wp_code"), c.get("cell_ref"), parts[idx])
                    )
    assert not unknown, f"未注册的期间/列字面量：{unknown}"


# ─────────────────────────────────────────────────────────────────────────────
# Property 22：无项目专属污染
# ─────────────────────────────────────────────────────────────────────────────


def test_no_project_specific_aux_codes(k_blocks):
    """预设不得含具体辅助项编码 —— `AUX()` 第三参精确匹配、不支持通配。"""
    polluted = [
        (b.get("wp_code"), b.get("sheet"), c.get("cell_ref"))
        for b in k_blocks
        for c in _cells(b)
        if _AUX_CODE_RE.search(str(c.get("formula") or ""))
        or _AUX_CODE_RE.search(str(c.get("cell_ref") or ""))
    ]
    assert not polluted, (
        "预设含写死的项目专属辅助项编码 ⇒ 换项目即静默返 0："
        f"{polluted}"
    )


def test_aux_removal_is_documented(k_blocks):
    """被清空 cells 的块必须有 `_aux_removal_note` 留痕（区别于「被误清空」）。"""
    silent = [
        (b.get("wp_code"), b.get("sheet"))
        for b in k_blocks
        if not _cells(b) and not b.get("_aux_removal_note")
    ]
    assert not silent, f"块 cells 为空且无移除留痕：{silent}"


def test_aux_code_regex_actually_matches():
    """反向自检：判据正则真的能识别那三种编码形态（否则上面两条空转）。"""
    for sample in ("SKT211", "YG01", "YG02", "A001", "A011"):
        assert _AUX_CODE_RE.search(f"AUX('1221','x','{sample}','期末余额')"), sample
    # 且不误伤正常科目码与 tab 名
    for ok in ("1221", "2241", "6601", "审定表K5-1", "IMP-007"):
        assert not _AUX_CODE_RE.search(ok), f"误伤 {ok}"


# ─────────────────────────────────────────────────────────────────────────────
# Property 24：月度覆盖 12 月
# ─────────────────────────────────────────────────────────────────────────────


def test_monthly_detail_covers_twelve_months(k_blocks):
    """K8/K9 的 `LEDGER_DETAIL` 月度块必须覆盖 1~12 月。"""
    month_re = re.compile(r"_(\d{1,2})月_合计$")
    checked = 0
    for b in k_blocks:
        months = {
            int(m.group(1))
            for c in _cells(b)
            if (m := month_re.search(str(c.get("cell_ref") or "")))
        }
        if not months:
            continue
        checked += 1
        assert months == set(range(1, 13)), (
            f"{b.get('wp_code')} | {b.get('sheet')} 月度不全：{sorted(months)}"
        )
    assert checked >= 2, f"月度块扫描面为 {checked}（应至少 K8/K9 两块）—— 判据可疑"


# ─────────────────────────────────────────────────────────────────────────────
# Property 18：预设科目与 wp_code 一致
# ─────────────────────────────────────────────────────────────────────────────


def test_block_accounts_belong_to_own_cycle(k_blocks):
    """每块的 `account_codes` 必须属于该 wp_code 的科目族（声明真源）。"""
    offenders = []
    for b in k_blocks:
        wc = str(b.get("wp_code", "")).upper()
        spec = K_CYCLE_SPECS.get(wc)
        if spec is None or not spec.fallback_standard:
            continue
        # 允许集 = 兜底原值 + 附加单列码 + **备抵兜底码**
        # （初版漏了 fallback_provision ⇒ K1 的备抵 `1231-03` 被误报为「不属本循环」）
        allowed = {
            spec.fallback_standard,
            *spec.extra_standard_codes,
            *spec.fallback_provision,
        }
        if wc == "K6":
            allowed |= {"1482", "2245"}  # K6 一循环管资产/备抵/负债三侧
        for a in b.get("account_codes") or []:
            code = str(a).strip()
            if code and not any(code.startswith(x) for x in allowed):
                offenders.append((wc, b.get("sheet"), code, sorted(allowed)))
    assert not offenders, f"预设科目不属本循环：{offenders}"


def test_wp_name_matches_cycle_account(k_blocks):
    """`wp_name` 必须含本循环科目名（防 K8 块写「管理费用」这类跨循环贴错）。"""
    offenders = []
    for b in k_blocks:
        wc = str(b.get("wp_code", "")).upper()
        spec = K_CYCLE_SPECS.get(wc)
        name = str(b.get("wp_name") or "")
        if spec is None or not name:
            continue
        # 只查「明显是别的循环科目名」这一类
        others = {
            s.account_name
            for c, s in K_CYCLE_SPECS.items()
            if c != wc and s.account_name != spec.account_name
        }
        wrong = [o for o in others if o in name and spec.account_name not in name]
        if wrong:
            offenders.append((wc, b.get("sheet"), name, wrong))
    assert not offenders, f"wp_name 贴了别的循环的科目名：{offenders}"


def test_dead_k8_analysis_block_stays_removed(k_blocks):
    """K8「分析程序K8-3」死块已删，不得重新引入。

    源 xlsx 无该 tab（真名是「调整分录汇总K8-3」/「实质性分析K8-4」）⇒ 永不命中；
    且它当年的 `wp_name='管理费用分析程序'` + `account_codes=['6601','6602','6603']`
    跨了销售/管理/财务三费。三个 cell 语义已被「实质性分析K8-4」块完全覆盖。
    """
    revived = [
        (b.get("wp_code"), b.get("sheet"))
        for b in k_blocks
        if b.get("wp_code") == "K8" and str(b.get("sheet", "")) == "分析程序K8-3"
    ]
    assert not revived, f"K8 死块被重新引入：{revived}"


# ─────────────────────────────────────────────────────────────────────────────
# Property 25：幂等与 round-trip
# ─────────────────────────────────────────────────────────────────────────────


def test_round_trip_is_byte_identical(raw_text):
    """`json.dumps(indent=2)+换行` 必须逐字复现原文。

    不成立时幂等脚本一写盘就会重排整个 429KB 文件、把并发会话的成果卷进 diff。
    """
    rebuilt = json.dumps(json.loads(raw_text), ensure_ascii=False, indent=2) + "\n"
    assert rebuilt == raw_text, (
        "round-trip 不逐字一致 —— 幂等脚本写盘会重排全文（差 "
        f"{len(rebuilt) - len(raw_text)} 字符）"
    )


def test_fix_script_is_idempotent(raw_text):
    """对当前数据再跑一次 `apply_fixes` 必须零变更（--check 归零）。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_k_fix", _ROOT / "backend/scripts/fix/fix_k_cycle_prefill_presets.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    changes = mod.apply_fixes(json.loads(raw_text))
    assert changes == [], f"幂等性破坏，仍有 {len(changes)} 项欠账：{changes[:8]}"


# ─────────────────────────────────────────────────────────────────────────────
# Property 26 / 27 / 28：披露块覆盖面、无环、sheet 名逐字（Task 12）
# ─────────────────────────────────────────────────────────────────────────────

_DISCLOSURE_PREFIX = "附注披露信息"

#: 变体后缀 —— 披露块 cell_ref 必须带它，否则 `convert_prefill_presets` 撞键丢条目
_VARIANT_SUFFIXES = ("_上市", "_国企")


def _disclosure_blocks(k_blocks: list[dict]) -> list[dict]:
    return [b for b in k_blocks if str(b.get("sheet", "")).startswith(_DISCLOSURE_PREFIX)]


@pytest.fixture(scope="module")
def source_disclosure_sheets(real_sheets) -> set[str]:
    """源 xlsx 里的披露 sheet **真名集合**（去重后只有 8 种写法）。"""
    return {s for s in real_sheets if s.startswith(_DISCLOSURE_PREFIX)}


@pytest.fixture(scope="module")
def source_disclosure_pairs() -> set[tuple[str, str]]:
    """源 xlsx 的 ``{(wp_code, sheet 真名)}`` 对 —— 26 个。

    🔴 判覆盖面必须用**对**而不是 sheet 名集合：同一个写法（如
    `附注披露信息（上市公司）`）在 K10/K11/K12/K13… 多个工作簿里重复出现，
    集合去重后只剩 8 种写法，拿它当分母会把 26 个块误判成「多了 18 个」。
    """
    from openpyxl import load_workbook

    out: set[tuple[str, str]] = set()
    for f in sorted(_TPL_DIR.glob("*.xlsx")):
        if f.name.startswith("~$"):
            continue
        wp = f.name.split()[0].upper()
        wb = load_workbook(f, read_only=True, data_only=True)
        try:
            for n in wb.sheetnames:
                if n.startswith(_DISCLOSURE_PREFIX):
                    out.add((wp, n))
        finally:
            wb.close()
    return out


def _preset_disclosure_pairs(k_blocks: list[dict]) -> set[tuple[str, str]]:
    return {
        (str(b.get("wp_code", "")).upper(), str(b.get("sheet", "")))
        for b in _disclosure_blocks(k_blocks)
    }


def test_all_disclosure_sheets_have_presets(k_blocks, source_disclosure_pairs):
    """Property 26：源 xlsx 的每张披露 sheet 都要有预设块。

    分母用 ``(wp_code, sheet)`` **对**而非 sheet 名集合 —— 见
    `source_disclosure_pairs` docstring。
    """
    assert len(source_disclosure_pairs) >= 20, (
        f"源 xlsx 披露 sheet 只读到 {len(source_disclosure_pairs)} 张，判据源可疑"
    )
    missing = sorted(source_disclosure_pairs - _preset_disclosure_pairs(k_blocks))
    assert not missing, f"披露 sheet 无预设块（Requirement 7.1 禁沉默）：{missing}"


def test_disclosure_block_count_matches_source(k_blocks, source_disclosure_pairs):
    """披露块数与源 xlsx 张数一致（不多不少 —— 多出来的必是贴错 sheet 名）。"""
    blocks = _disclosure_blocks(k_blocks)
    extra = sorted(_preset_disclosure_pairs(k_blocks) - source_disclosure_pairs)
    assert not extra, f"披露块指向源 xlsx 不存在的 (wp_code, sheet)：{extra}"
    assert len(blocks) == len(source_disclosure_pairs), (
        f"披露块 {len(blocks)} 个 vs 源 xlsx {len(source_disclosure_pairs)} 张"
        "（一 sheet 一块，多出来的必是重复建块）"
    )


def test_disclosure_sheet_names_are_verbatim(k_blocks, real_sheets):
    """Property 28：披露块 sheet 名逐字等于源 xlsx（K 有 6 种括号写法，禁归一）。"""
    bad = [
        (b.get("wp_code"), b.get("sheet"))
        for b in _disclosure_blocks(k_blocks)
        if str(b.get("sheet", "")) not in real_sheets
    ]
    assert not bad, f"披露块 sheet 名不在源 xlsx（永不命中）：{bad}"


def test_source_really_has_six_bracket_variants(source_disclosure_sheets):
    """反向自检：源 xlsx 里**确实**存在多种括号写法。

    防有人把括号「统一」掉之后，上一条仍全绿而实际已与源模板脱节。
    """
    assert len(source_disclosure_sheets) >= 4, "披露 sheet 名种类过少，判据可疑"
    # 半角 ( 与全角 （ 都必须出现过
    assert any("(" in s for s in source_disclosure_sheets), "源 xlsx 无半角括号写法"
    assert any("（" in s for s in source_disclosure_sheets), "源 xlsx 无全角括号写法"
    # 「国有企业」与「国企」两种写法都在（K7 是「国有企业」）
    assert any("国有企业" in s for s in source_disclosure_sheets)
    assert any(
        "国企" in s and "国有企业" not in s for s in source_disclosure_sheets
    )


def test_disclosure_cell_refs_carry_variant_suffix(k_blocks):
    """披露块 cell_ref 必须带变体后缀。

    🔴 `preset_library.convert_prefill_presets()` 按 ``(page_key, target_cell)``
    **二元组**去重，而 ``page_key`` 不含 sheet ⇒ 同循环 listed/soe 两块用相同
    cell_ref 时第二个被**静默丢弃**。实测 D1/D2/G14 的既有披露块正是这种撞键状态
    （只是它们没守卫），K1 靠 `test_k1_no_dedup_collision_within_page_key` 抓出。
    """
    bad: list[tuple] = []
    for b in _disclosure_blocks(k_blocks):
        for c in b.get("cells") or []:
            ref = str(c.get("cell_ref") or "")
            if ref and not ref.endswith(_VARIANT_SUFFIXES):
                bad.append((b.get("wp_code"), b.get("sheet"), ref))
    assert not bad, f"披露块 cell_ref 缺变体后缀（会撞键静默丢条目）：{bad[:10]}"


def test_disclosure_cell_refs_unique_per_wp(k_blocks):
    """同一 wp_code 下披露块的 cell_ref 全局唯一（撞键即静默丢弃）。"""
    from collections import Counter

    per_wp: dict[str, Counter] = {}
    for b in _disclosure_blocks(k_blocks):
        wp = str(b.get("wp_code"))
        cnt = per_wp.setdefault(wp, Counter())
        for c in b.get("cells") or []:
            cnt[str(c.get("cell_ref"))] += 1
    dups = {wp: {k: v for k, v in c.items() if v > 1} for wp, c in per_wp.items()}
    dups = {wp: d for wp, d in dups.items() if d}
    assert not dups, f"披露块 cell_ref 撞键：{dups}"


def test_disclosure_blocks_reference_adjudication_one_way(k_blocks):
    """Property 27：披露块**单向**引审定表；不得引明细表（防三角环）。

    环的条件：审定表 → 明细表（既有）+ 明细表 → 披露 → 审定表 会成回路。
    故披露块只许引审定表，不许引明细表。
    """
    no_ref: list[tuple] = []
    detail_ref: list[tuple] = []
    for b in _disclosure_blocks(k_blocks):
        wp = str(b.get("wp_code"))
        formulas = [str(c.get("formula") or "") for c in b.get("cells") or []]
        joined = "\n".join(formulas)
        if not re.search(r"WP\('[^']+','审定表", joined):
            no_ref.append((wp, b.get("sheet")))
        for c in b.get("cells") or []:
            if re.search(r"WP\('[^']+','明细表", str(c.get("formula") or "")):
                detail_ref.append((wp, b.get("sheet"), c.get("cell_ref")))
    assert not detail_ref, (
        "披露块引了明细表 —— 与「审定表→明细表」合成三角环："
        f"{detail_ref[:6]}"
    )
    assert not no_ref, f"披露块缺审定表勾稽：{no_ref[:6]}"


def test_k4_disclosure_has_no_tb_and_is_registered(k_blocks):
    """K4 宁缺勿造：披露块不得含 `TB()`，且必须留登记理由。"""
    k4 = [b for b in _disclosure_blocks(k_blocks) if str(b.get("wp_code")) == "K4"]
    assert len(k4) == 2, f"K4 应有两个变体披露块，实际 {len(k4)}"
    for b in k4:
        for c in b.get("cells") or []:
            assert "TB(" not in str(c.get("formula") or ""), (
                f"K4 披露块含 TB()：{c.get('cell_ref')} —— 其科目在 account_chart "
                "两侧零命中，造 TB() 等于造假数据"
            )
        reason = str(b.get("_no_tb_preset_reason") or "")
        assert len(reason) >= 15, (
            f"K4 披露块缺无预设登记理由（Requirement 7.2 禁沉默）：{b.get('sheet')}"
        )


def test_disclosure_pl_cycles_use_occurrence(k_blocks):
    """损益类披露块用本期发生额，不得用余额口径。"""
    from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS

    bad = []
    for b in _disclosure_blocks(k_blocks):
        spec = K_CYCLE_SPECS.get(str(b.get("wp_code", "")).upper())
        if spec is None or not spec.is_pl:
            continue
        for c in b.get("cells") or []:
            if re.search(r"'(?:期初余额|期末余额)'", str(c.get("formula") or "")):
                bad.append((b.get("wp_code"), c.get("cell_ref")))
    assert not bad, f"损益类披露块误用余额口径：{bad}"


def test_disclosure_fix_script_is_idempotent():
    """`fix_k_cycle_disclosure_presets.py --check` 必须归零。"""
    import subprocess

    r = subprocess.run(
        [
            sys.executable,
            str(_ROOT / "backend/scripts/fix/fix_k_cycle_disclosure_presets.py"),
            "--check",
        ],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, (
        f"披露块幂等脚本 --check 未归零（exit={r.returncode}）：\n"
        f"{(r.stdout or '')[-1200:]}"
    )
