"""D 循环公式预设守卫 —— spec Task 21（Property 16~20）。

覆盖四类「配置错了但四层验证全绿」的缺陷：

1. **sheet 名贴错标签** —— `sheet` 是运行时匹配键（`page_key` 由 `wp_code` + sheet
   派生），写成源 xlsx 里不存在的 tab 名 ⇒ 该块永不命中、公式管理页空白，而任何
   语法校验都不会报错。判据 = openpyxl 直读 `wb.sheetnames`（含 hidden）。
2. **科目码贴错循环** —— 平台既有测试只校验「预设能加载 / 锚点合法 / 函数受支持」，
   **从不校验码是不是本循环的科目**（D6 曾把 `1402 在途物资` 当合同资产、D5 引用
   全库零命中的码），故此处按 `report_config` 报表行的科目集交叉锁死。
3. **`WP()` 成环** —— 审定表引用明细表、明细表反向引用审定表 ⇒ 求值时无限递归。
4. **`PLACEHOLDER` 变逃逸阀** —— 逐条登记理由，未登记即打红。

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 5.1, 5.3, 5.4, 5.8, 5.9
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

BACKEND = Path(__file__).resolve().parents[1]
MAPPING_PATH = BACKEND / "data" / "prefill_formula_mapping.json"
TEMPLATE_DIR = BACKEND / "wp_templates"

D_WP_RE = re.compile(r"^D[0-7]$")

# ── 源 xlsx 披露 tab 名（openpyxl 直读实证；六种括号写法并存，禁「统一」）──────
EXPECTED_DISCLOSURE_SHEETS: dict[str, tuple[str, str]] = {
    "D1": ("附注披露信息（上市公司）", "附注披露信息（国企）"),
    "D2": ("附注披露信息(上市公司)", "附注披露信息(国企)"),
    "D3": ("附注披露信息(上市公司)", "附注披露信息(国企)"),
    "D5": ("附注披露信息（上市公司）", "附注披露信息（国企）"),
    "D6": ("附注披露信息(上市公司）", "附注披露信息（国企）"),
    "D7": ("附注披露信息(上市公司)", "附注披露信息(国企)"),
}

# 各循环允许出现的科目码（与 render 的 report_line_accounts 解析结果一致）
ALLOWED_ACCOUNT_CODES: dict[str, set[str]] = {
    "D0": {"1121", "1122"},  # 函证循环，覆盖应收票据 + 应收账款
    "D1": {"1121", "1231-01"},
    # 6702 = 信用减值损失（应收款项减值按金融工具准则计入该科目）。
    # 🔴 **不含 6602** —— 那是管理费用，改造前 D2-3 误用它并把 description 写成
    #    「信用减值损失」；也不含 6701（资产减值损失，走存货/长期资产）。
    "D2": {"1122", "1231-02", "6702"},
    "D3": {"2203"},
    "D4": {"6001", "6051", "6401", "6402"},
    "D5": {"1124"},
    "D6": {"1141", "1142", "1231-05"},
    "D7": {"2205", "2204"},
}

# prefill 引擎词汇表（**不是** formula_engine 的 _REGISTRY —— 两者不同）
PREFILL_FUNCS: set[str] = {
    "TB", "TB_SUM", "SUM_TB", "ADJ", "PREV", "WP",
    "LEDGER", "LEDGER_DETAIL", "AUX", "PLACEHOLDER", "NOTE", "TB_AUX",
}

# PLACEHOLDER 逐条登记理由（防它变成逃逸阀）。key = (wp_code, sheet, cell_ref)
_D5_REASON = (
    "1124 应收款项融资在活体 account_chart 两个 source 零命中、account_mapping 零反解、"
    "tb_balance 零数据行 —— 本平台在册项目无此业务，属业务事实而非错码"
)

PLACEHOLDER_REGISTRY: dict[tuple[str, str, str], str] = {
    # ── D5 披露表（Task 20）────────────────────────────────────────────────
    ("D5", "附注披露信息（上市公司）", "期末账面价值"): _D5_REASON,
    ("D5", "附注披露信息（国企）", "期末账面价值"): f"同上市侧：{_D5_REASON}",
    # ── D5 审定表与明细块（Task 18c / Task 19）─────────────────────────────
    ("D5", "审定表D5", "期初余额"): _D5_REASON,
    ("D5", "审定表D5", "未审数"): _D5_REASON,
    ("D5", "审定表D5", "AJE调整"): _D5_REASON,
    ("D5", "审定表D5", "RJE调整"): _D5_REASON,
    ("D5", "应收款项融资明细表D5-2", "期末合计"): _D5_REASON,
    (
        "D5",
        "应收款项融资公允价值测算表D5-4",
        "公允价值合计",
    ): f"{_D5_REASON}；且公允价值本身属估值判断，四表无对应字段",
    # ── D2 本期核销（Task 18d）────────────────────────────────────────────
    (
        "D2",
        "坏账准备明细表D2-3",
        "本期核销",
    ): (
        "无法用单条 LEDGER() 表达：_resolve_ledger_formula 是 account_code 精确等于、非前缀"
        "匹配，而 tb_ledger.account_code 是客户原始码（点号体系），标准码 1231-02（横杠）命中"
        "不了；退回父码 1231 又会把 D1/D6/K1 等循环的坏账核销一并算进 D2"
    ),
}


@pytest.fixture(scope="module")
def mappings() -> list[dict[str, Any]]:
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return data["mappings"]


@pytest.fixture(scope="module")
def d_blocks(mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [b for b in mappings if D_WP_RE.match(str(b.get("wp_code") or ""))]
    assert out, "D 类预设块为空 —— 抽取失效（字段名是 wp_code 不是 wp）"
    return out


@pytest.fixture(scope="module")
def source_sheet_names() -> dict[str, set[str]]:
    """各 D 循环源 xlsx 的全部 tab 名（含 hidden）。openpyxl 直读。"""
    openpyxl = pytest.importorskip("openpyxl")
    out: dict[str, set[str]] = {}
    for p in sorted(TEMPLATE_DIR.rglob("*.xlsx")):
        if p.name.startswith("~$"):
            continue
        m = re.match(r"^(D\d)", p.name)
        if not m:
            continue
        wp = m.group(1)
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        try:
            out.setdefault(wp, set()).update(wb.sheetnames)
        finally:
            wb.close()
    assert out, "未读到任何 D 类源模板 —— 路径或命名规则已变"
    return out


def _cells(block: dict[str, Any]) -> list[dict[str, Any]]:
    return list(block.get("cells") or [])


def _funcs_in(formula: str) -> set[str]:
    return set(re.findall(r"\b([A-Z][A-Z_]*)\s*\(", formula or ""))


def _codes_in(formula: str) -> set[str]:
    """抽公式里的科目码。

    🔴 **区间端点不算被引用科目** —— `TB_SUM('1401~1499')` 的两端是边界，
    按单码正则抽会把上界当成「引用了别的循环科目」误报（平台已登记该坑）。
    """
    f = formula or ""
    # 先整体消费区间形态
    f = re.sub(r"\b(?:SUM_TB|TB_SUM)\s*\(\s*'[^']*~[^']*'", "", f)
    return set(re.findall(r"'(\d{4}(?:-\d{2})?)'", f))


# ══════════════════════════════════════════════════════════════════════════════
# Property 16: 每个 D 块的 sheet 必须是源 xlsx 里真实存在的 tab
# ══════════════════════════════════════════════════════════════════════════════


def test_every_sheet_exists_in_source_template(
    d_blocks: list[dict[str, Any]], source_sheet_names: dict[str, set[str]]
) -> None:
    """Property 16：sheet 名贴错标签 = 该块永不命中（公式管理页空白），无任何报错。"""
    bad: list[str] = []
    for b in d_blocks:
        wp = str(b["wp_code"])
        sheet = str(b.get("sheet") or "")
        known = source_sheet_names.get(wp)
        if known is None:
            bad.append(f"{wp}: 源模板未找到（无法判定 sheet={sheet!r}）")
            continue
        if sheet not in known:
            bad.append(f"{wp}: sheet={sheet!r} 不在源 xlsx tab 名集合中")
    assert not bad, "sheet 名与源模板不符：\n" + "\n".join(bad)


def test_source_sheet_probe_is_not_empty(source_sheet_names: dict[str, set[str]]) -> None:
    """反向自检：源 tab 名集合非空且覆盖全部 D 循环，否则上一条断言是空转。"""
    assert len(source_sheet_names) >= 7, f"只读到 {sorted(source_sheet_names)}"
    for wp in ("D1", "D2", "D3", "D5", "D6", "D7"):
        assert source_sheet_names.get(wp), f"{wp} 源 tab 名为空"


# ══════════════════════════════════════════════════════════════════════════════
# Property 17: 12 张披露 sheet 预设齐备且 sheet 名逐字正确
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("wp", sorted(EXPECTED_DISCLOSURE_SHEETS))
def test_disclosure_presets_present_for_each_cycle(
    wp: str, d_blocks: list[dict[str, Any]]
) -> None:
    """Property 17：改造前只有 D4 有披露预设，其余 12 张全空白。"""
    listed, soe = EXPECTED_DISCLOSURE_SHEETS[wp]
    have = {str(b.get("sheet")) for b in d_blocks if str(b["wp_code"]) == wp}
    for sheet in (listed, soe):
        assert sheet in have, f"{wp} 缺披露预设块：{sheet!r}（现有 {sorted(have)}）"


def test_disclosure_sheet_names_are_not_normalized(d_blocks: list[dict[str, Any]]) -> None:
    """🔴 括号宽窄逐字取源模板，禁「统一」。

    D6 上市侧是**前半角后全角** `(上市公司）` —— 这是源 xlsx 的事实。任何
    「统一成全角」的批量改写都会让 D6 上市披露预设永不命中。
    """
    d6_listed = [
        b for b in d_blocks if str(b["wp_code"]) == "D6" and "上市" in str(b.get("sheet"))
    ]
    assert d6_listed, "D6 上市披露块缺失"
    assert str(d6_listed[0]["sheet"]) == "附注披露信息(上市公司）", (
        "D6 上市侧 sheet 名被「统一」了 —— 源 xlsx 实为前半角后全角"
    )

    # 三种写法必须同时存在于 D 类块里（证明没被统一）
    sheets = {str(b.get("sheet")) for b in d_blocks}
    assert "附注披露信息（上市公司）" in sheets, "全角写法丢失（D1/D4/D5）"
    assert "附注披露信息(上市公司)" in sheets, "半角写法丢失（D2/D3/D7）"
    assert "附注披露信息(上市公司）" in sheets, "混合写法丢失（D6）"


def test_hidden_legacy_disclosure_sheets_have_no_presets(
    d_blocks: list[dict[str, Any]]
) -> None:
    """D2 的 4 张 hidden 旧版披露表不得建预设（会在公式管理页凭空多出四张表）。"""
    forbidden = {"附注披露信息(上市公司）D2-1", "附注披露信息（国企）D2-1"}
    hit = {str(b.get("sheet")) for b in d_blocks} & forbidden
    assert not hit, f"hidden 旧版披露表被建了预设：{sorted(hit)}"


# ══════════════════════════════════════════════════════════════════════════════
# Property 18: 科目码不得跨循环污染
# ══════════════════════════════════════════════════════════════════════════════


def test_account_codes_belong_to_cycle(d_blocks: list[dict[str, Any]]) -> None:
    """Property 18：D6 曾把 `1402 在途物资`（存货）当合同资产 —— 语法校验查不出。"""
    bad: list[str] = []
    for b in d_blocks:
        wp = str(b["wp_code"])
        allowed = ALLOWED_ACCOUNT_CODES.get(wp)
        if allowed is None:
            bad.append(f"{wp}: 未登记允许科目集")
            continue
        declared = {str(c) for c in (b.get("account_codes") or [])}
        extra = declared - allowed
        if extra:
            bad.append(f"{wp} {b.get('sheet')!r}: account_codes 越界 {sorted(extra)}")
        for cell in _cells(b):
            codes = _codes_in(str(cell.get("formula") or ""))
            out = codes - allowed
            if out:
                bad.append(
                    f"{wp} {b.get('sheet')!r} [{cell.get('cell_ref')}]: 公式引用非本循环科目 {sorted(out)}"
                )
    assert not bad, "科目码跨循环污染：\n" + "\n".join(bad)


def test_range_endpoints_are_not_treated_as_codes() -> None:
    """反向自检：`TB_SUM('6001~6099')` 的上界不得被当成被引用科目。"""
    assert _codes_in("=TB_SUM('6001~6099','本期发生额')") == set()
    # 但区间之外的单码仍要抽到
    assert _codes_in("=TB('1141','期末余额')-TB('1142','期末余额')") == {"1141", "1142"}


# ══════════════════════════════════════════════════════════════════════════════
# Property 19: WP() 联动不得成环
# ══════════════════════════════════════════════════════════════════════════════


def test_wp_references_are_acyclic(d_blocks: list[dict[str, Any]]) -> None:
    """Property 19：明细表禁反向引用审定表（求值时无限递归）。"""
    edges: set[tuple[str, str]] = set()
    for b in d_blocks:
        src = f"{b['wp_code']}::{b.get('sheet')}"
        for cell in _cells(b):
            for m in re.finditer(
                r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'", str(cell.get("formula") or "")
            ):
                edges.add((src, f"{m.group(1)}::{m.group(2)}"))

    # 环检测（DFS）
    adj: dict[str, set[str]] = {}
    for a, b_ in edges:
        adj.setdefault(a, set()).add(b_)

    state: dict[str, int] = {}
    cycles: list[str] = []

    def dfs(node: str, trail: list[str]) -> None:
        state[node] = 1
        for nxt in sorted(adj.get(node, ())):
            if state.get(nxt) == 1:
                cycles.append(" -> ".join(trail + [node, nxt]))
            elif state.get(nxt, 0) == 0:
                dfs(nxt, trail + [node])
        state[node] = 2

    for n in sorted(adj):
        if state.get(n, 0) == 0:
            dfs(n, [])

    assert not cycles, "WP() 引用成环：\n" + "\n".join(cycles)


def test_detail_blocks_do_not_reference_own_adjudication(
    d_blocks: list[dict[str, Any]]
) -> None:
    """明细表块不得引用**本循环自己的**审定表（成环的具体形态）。

    🔴 **跨循环引用审定表是合法的，不得一并禁掉**（首版判据过严，实测打红了正确配置）：
    `D0 核实被函证单位信息D0-2` 引用 `WP('D2','审定表D2-1',…)` 是函证覆盖率计算的
    正当需要（函证金额 ÷ 应收账款审定数），两者不在同一 wp_code 下、不构成环。
    """
    bad: list[str] = []
    for b in d_blocks:
        wp = str(b["wp_code"])
        sheet = str(b.get("sheet") or "")
        if "审定表" in sheet or "附注" in sheet:
            continue
        for cell in _cells(b):
            f = str(cell.get("formula") or "")
            for m in re.finditer(r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'", f):
                target_wp, target_sheet = m.group(1), m.group(2)
                if target_wp == wp and "审定表" in target_sheet:
                    bad.append(f"{wp} {sheet!r} -> {target_sheet!r}（同循环，成环）")
    assert not bad, "明细表反向引用本循环审定表：\n" + "\n".join(bad)


def test_cross_cycle_adjudication_reference_is_allowed(
    d_blocks: list[dict[str, Any]]
) -> None:
    """反向锁死：D0 函证覆盖率对 D2 审定表的跨循环引用必须仍在（防被「顺手清掉」）。"""
    hit = [
        b
        for b in d_blocks
        if str(b["wp_code"]) == "D0"
        and any(
            "WP('D2','审定表D2-1'" in str(c.get("formula") or "").replace(" ", "")
            for c in _cells(b)
        )
    ]
    assert hit, (
        "D0 对 D2 审定表的跨循环 WP() 引用不见了 —— 它是函证覆盖率的分母，"
        "属正当跨循环引用，不是成环"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Property 20: 公式语法 + PLACEHOLDER 登记
# ══════════════════════════════════════════════════════════════════════════════


def test_formula_functions_are_supported(d_blocks: list[dict[str, Any]]) -> None:
    """Property 20：函数名必须在 prefill 引擎词汇表内。"""
    bad: list[str] = []
    for b in d_blocks:
        for cell in _cells(b):
            f = str(cell.get("formula") or "")
            assert f.startswith("="), f"{b['wp_code']} {cell.get('cell_ref')}: 公式未以 = 开头"
            unknown = _funcs_in(f) - PREFILL_FUNCS
            if unknown:
                bad.append(f"{b['wp_code']} {b.get('sheet')!r} [{cell.get('cell_ref')}]: {sorted(unknown)}")
    assert not bad, "未知函数：\n" + "\n".join(bad)


def test_placeholder_cells_are_registered(d_blocks: list[dict[str, Any]]) -> None:
    """每个 PLACEHOLDER 必须逐条登记理由（≥20 字且含实证词），防它变逃逸阀。"""
    unregistered: list[str] = []
    for b in d_blocks:
        for cell in _cells(b):
            if str(cell.get("formula_type")) != "PLACEHOLDER":
                continue
            key = (str(b["wp_code"]), str(b.get("sheet")), str(cell.get("cell_ref")))
            reason = PLACEHOLDER_REGISTRY.get(key)
            if not reason:
                unregistered.append(f"{key}")
            elif len(reason) < 20:
                unregistered.append(f"{key}（理由过短：{reason!r}）")
    assert not unregistered, "PLACEHOLDER 未登记理由：\n" + "\n".join(unregistered)


def test_placeholder_registry_has_no_stale_entries(d_blocks: list[dict[str, Any]]) -> None:
    """反向锁死：登记表里不得有已改成真公式的条目（否则常量沉积成死配置）。"""
    actual: set[tuple[str, str, str]] = set()
    for b in d_blocks:
        for cell in _cells(b):
            if str(cell.get("formula_type")) == "PLACEHOLDER":
                actual.add((str(b["wp_code"]), str(b.get("sheet")), str(cell.get("cell_ref"))))
    stale = set(PLACEHOLDER_REGISTRY) - actual
    assert not stale, f"PLACEHOLDER 登记表有过期条目（该格已改成真公式）：{sorted(stale)}"


def test_cell_refs_unique_within_block(d_blocks: list[dict[str, Any]]) -> None:
    """同一块内 cell_ref 不得重复 —— 它同时是手工覆盖键，重复会互相遮蔽。"""
    bad: list[str] = []
    for b in d_blocks:
        refs = [str(c.get("cell_ref")) for c in _cells(b)]
        dupes = {r for r in refs if refs.count(r) > 1}
        if dupes:
            bad.append(f"{b['wp_code']} {b.get('sheet')!r}: {sorted(dupes)}")
    assert not bad, "cell_ref 重复：\n" + "\n".join(bad)


def test_prev_targets_are_real_sheets(
    d_blocks: list[dict[str, Any]], source_sheet_names: dict[str, set[str]]
) -> None:
    """`PREV()` 的 (wp_code, sheet) 必须指向源 xlsx 里**真实存在**的 tab。

    🔴 **不要求指向自己所在 sheet**（首版判据过严，打红了 6 处正确配置）——
    「明细表/分析表取上年审定数」是平台既有范式（`PREV('D2','审定表D2-1','审定数')`），
    跨 sheet 取上年完全合法。

    真正的缺陷形态是**指向不存在的 tab**（平台已实证一例：`PREV('E1','分析程序E1-3',…)`
    而源 xlsx 无该 tab ⇒ 该式永远取不到值且不报错）。
    """
    bad: list[str] = []
    for b in d_blocks:
        wp, sheet = str(b["wp_code"]), str(b.get("sheet"))
        for cell in _cells(b):
            for m in re.finditer(
                r"PREV\(\s*'([^']+)'\s*,\s*'([^']+)'", str(cell.get("formula") or "")
            ):
                t_wp, t_sheet = m.group(1), m.group(2)
                known = source_sheet_names.get(t_wp)
                if known is None:
                    bad.append(f"{wp} {sheet!r} [{cell.get('cell_ref')}]: PREV 目标循环 {t_wp} 无源模板")
                elif t_sheet not in known:
                    bad.append(
                        f"{wp} {sheet!r} [{cell.get('cell_ref')}]: "
                        f"PREV('{t_wp}','{t_sheet}') 目标 tab 在源 xlsx 中不存在"
                    )
    assert not bad, "PREV 指向不存在的 tab：\n" + "\n".join(bad)


def test_prev_cross_sheet_pattern_is_preserved(d_blocks: list[dict[str, Any]]) -> None:
    """反向锁死：「明细表/分析表 PREV 指向本循环审定表」这一既有范式必须仍在。

    若哪天被「统一成指向自己 sheet」，上年审定数会取到明细表自己的上年值（口径不同），
    该断言会打红提醒。
    """
    cross = [
        (str(b["wp_code"]), str(b.get("sheet")))
        for b in d_blocks
        if "审定表" not in str(b.get("sheet") or "")
        and any(
            re.search(r"PREV\(\s*'[^']+'\s*,\s*'[^']*审定表", str(c.get("formula") or ""))
            for c in _cells(b)
        )
    ]
    assert cross, "跨 sheet PREV 范式全部消失 —— 上年审定数口径可能被改错"


def test_idempotent_script_reports_zero_debt() -> None:
    """幂等脚本 `--check` 必须 0 欠账（与守卫双向锁死）。"""
    import subprocess
    import sys as _sys

    r = subprocess.run(
        [_sys.executable, str(BACKEND / "scripts" / "fix" / "fix_d_cycle_disclosure_presets.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=str(BACKEND.parent),
    )
    assert r.returncode == 0, f"幂等脚本报欠账：\n{r.stdout}\n{r.stderr}"
