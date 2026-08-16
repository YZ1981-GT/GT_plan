"""L 循环公式预设守卫的**判据层**（常量 + 纯函数 + 数据加载器）。

由 `test_l_preset_account_coherence.py` 拆出 —— 原单文件 1082 行超平台 800 行门禁
（`.git-hooks/pre-commit` 拒绝提交）。拆分**逐字迁移**，不改任何判据语义：
常量、正则、纯函数、加载器、`evaluate_block_*` 五个判据函数全部原样搬来，
`__all__` 保持不变。测试用例、fixture、失败消息组装留在测试文件里。

为什么按「判据 / 用例」这条线切：判据是**可被别处复用的纯函数**（本文件原 docstring
即声明了这一意图），而 fixture 与 `pytest.fail` 消息组装是测试专属基础设施。
按这条线切之后两侧各自内聚，且判据可被幂等脚本 import（见下方注记）。

🔴 注记（2026-08-15 实测）：原 docstring 声称「Wave 2 的幂等脚本直接 import 复用，
避免同一判据两处各写一份」，但实测 `fix_l_cycle_prefill_presets.py` **并未 import**，
而是自己写了一份 `_ANY_CODE_ARG_RE`（两处各一份，正是原意图要防的）。
本次拆分只做文件切分、不顺手改那个脚本；该重复属既有欠账，另行处置。

spec: .kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/
      Requirements 3.1~3.8 / Design Property 1~6
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__ = [
    "FormulaCodes",
    "CrossCycleAllowance",
    "CROSS_CYCLE_ALLOWLIST",
    "WP_CODES_WITHOUT_SPEC",
    "OUT_OF_SCOPE_WP_CODES",
    "CLEAN_BLOCK_BASELINE",
    "PLACEHOLDER_MIN_DESC_CHARS",
    "extract_formula_codes",
    "extract_prev_targets",
    "parent_code",
    "is_code_allowed",
    "codes_within_range",
    "evaluate_range_health",
    "detect_description_label_conflicts",
    "build_label_index",
    "build_code_owner_index",
    "load_l_cycle_specs",
    "load_l_prefill_blocks",
    "load_visible_sheet_names",
    "evaluate_block_code_coherence",
    "evaluate_block_description_coherence",
    "evaluate_block_sheet_existence",
    "evaluate_block_prev_targets",
    "evaluate_block_range_health",
]

# ---------------------------------------------------------------------------
# 路径（从仓库根跑 pytest；本文件在 backend/tests/l_cycle_extraction/ 下）
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PREFILL_PATH = BACKEND_ROOT / "data" / "prefill_formula_mapping.json"
TEMPLATE_DIR = BACKEND_ROOT / "wp_templates" / "L"

L_WP_CODE_RE = re.compile(r"^L\d$")

PLACEHOLDER_MIN_DESC_CHARS = 30
MIN_REASON_CHARS = 20
MIN_L_BLOCK_COUNT = 15

_CLASS_A = "【类 A 独立口径判据】"
_CLASS_B = "【类 B 被测实现】"
_WAVE1_RED = "这是预期的 Wave 1 打红结果（Wave 2 Task 4/5 修复）"


# ---------------------------------------------------------------------------
# 登记表
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CrossCycleAllowance:
    """跨循环引用白名单条目。每条必须带理由字符串。"""

    codes: frozenset
    labels: frozenset
    reason: str


CROSS_CYCLE_ALLOWLIST = {
    ("L1", "利息测算表L1-5"): CrossCycleAllowance(
        codes=frozenset({"6603"}),
        labels=frozenset({"财务费用"}),
        reason=(
            "短期借款利息测算表要按月取财务费用（6603）的利息支出发生额，"
            "与短期借款本金一起反算实际利率并与合同利率比较；源模板 利息测算表L1-5 "
            "即按此编制，故 L1 块引用 6603 与提及科目名 财务费用 都是合法的审计口径。"
        ),
    ),
    ("L3", "利息测算表L3-5"): CrossCycleAllowance(
        codes=frozenset({"6603"}),
        labels=frozenset({"财务费用"}),
        reason=(
            "长期借款利息测算表要按月取财务费用（6603）的利息支出发生额，"
            "与长期借款本金一起反算实际利率并核对资本化与费用化的划分；"
            "源模板 利息测算表L3-5 即按此编制，故 L3 块引用 6603 是合法的审计口径。"
        ),
    ),
}

#: 本 spec 范围外的缺陷登记（**按 wp_code 粒度**，非按块）。
#:
#: 🔴 粒度选择的实测依据（2026-08-16）：先按「块」登记过 `("L0","审定表L0-1")`，
#: 结果配上「不得过期」自检后无法同时对两个状态成立 —— 共享工作树里另一条并发流
#: 已把该块迁为 `函证结果汇总表L0-1`（未提交）⇒ 登记表在工作树里是过期的、
#: 在 HEAD 里是必需的，同一份判据两处结论相反。改按 wp_code 粒度后无此脆性：
#: 块在则豁免、块被修好后也无需清理条目。
#:
#: 语义上 wp_code 粒度也更贴 spec：Requirement 11.1 是「涉及 L0 函证循环则不改任何
#: L0 组件与配置」——整个循环范围外，不是某一块范围外。
#:
#: 具体已知缺陷（供 owner 方接手时定位，本 spec 不处置）：
#:   L0/审定表L0-1  ①sheet 不在 L0 源 xlsx 的 9 张 visible tab 内（真实 tab 是
#:                    '函证结果汇总表L0-1'）⇒ 预设永远匹配不到底稿 sheet；
#:                  ②TB_SUM('2001~2501') 病态区间横跨 L1(2001)/L2(2231)/L3(2501)，
#:                    与本 spec 已删的幽灵块 'L1/分析程序L1-3' 是同一错误形态。
#: owner: l0-confirmation-source-alignment（已归档，需另立任务重开）
OUT_OF_SCOPE_WP_CODES = {
    "L0": (
        "L0 债务循环函证枢纽，spec Requirement 11.1 明确范围外（已由归档 spec "
        "l0-confirmation-source-alignment 收口）。其预设块存在 sheet 名不实与病态区间"
        "两处真实缺陷（详见上方注释），本 spec 只登记不处置 —— 改它属越权，"
        "且实测另一条并发流正在修。owner: l0-confirmation-source-alignment。"
    ),
}

WP_CODES_WITHOUT_SPEC = {
    "L0": (
        "L0 是债务循环函证枢纽，不对应单一科目，L_CYCLE_SPECS 无该键；"
        "其预设块按函证品种同时引用 2701 长期应付款与 2502 应付债券等多个循环的科目，"
        "属正常编制，故不对它做本循环科目一致性判定（只保留 PLACEHOLDER 说明长度要求）。"
    ),
}

# 本来正确、守卫必须放行的块（零回归对照）。
# Wave 2 的 Task 4/5 不移动也不改写这些块，故本基线跨 Wave 有效。
CLEAN_BLOCK_BASELINE = frozenset(
    {
        ("L1", "审定表L1-1"),
        ("L3", "审定表L3-1"),
        ("L8", "审定表L8-1"),
        ("L1", "明细表L1-2"),
        ("L3", "明细表L3-2"),
        ("L8", "明细表L8-2"),
        ("L1", "利息测算表L1-5"),
        ("L3", "利息测算表L3-5"),
    }
)


# ---------------------------------------------------------------------------
# 纯函数：抽科目码 / 区间校验 / description 科目名冲突检测
# ---------------------------------------------------------------------------

# 区间函数：两种词汇表并存（预设侧用 TB_SUM，report_config 侧用 SUM_TB），两个都要认
_RANGE_RE = re.compile(r"\b(?:TB_SUM|SUM_TB)\s*\(\s*'([^']*)~([^']*)'")
# 首实参是科目码的函数
_CODE_RE = re.compile(r"\b(TB|ADJ|AUX|LEDGER_DETAIL|LEDGER)\s*\(\s*'([^']*)'")
# 首实参不是科目码的函数（PREV/WP 首实参是 wp_code，PLACEHOLDER 首实参是自由文本）
_PREV_RE = re.compile(r"\bPREV\s*\(\s*'([^']*)'\s*,\s*'([^']*)'")
_CODE_SHAPE_RE = re.compile(r"^\d{4}(?:\.\d+)*$")


@dataclass(frozen=True)
class FormulaCodes:
    """一条公式里抽出的科目码。

    ranges   -- 区间形态的上下界元组，**不是**被引用科目
    singles  -- 消费掉区间之后剩余的单码（含点号子科目形态）
    malformed -- 落在科目码位置但形态不合法的实参
    residual -- 区间被整体替换掉之后的公式文本（供自检）
    """

    ranges: tuple
    singles: tuple
    malformed: tuple
    residual: str


def extract_formula_codes(formula: str) -> FormulaCodes:
    """从公式抽科目码。先整体消费区间形态，再抽剩余单码。

    这个顺序是结构性保证：区间上下界永远进不了 singles，故不会被误判成
    "引用了别的循环科目"。
    """
    text = formula or ""
    ranges = tuple(
        (m.group(1).strip(), m.group(2).strip()) for m in _RANGE_RE.finditer(text)
    )
    residual = _RANGE_RE.sub(" ", text)

    singles = []
    malformed = []
    for m in _CODE_RE.finditer(residual):
        raw = m.group(2).strip()
        if _CODE_SHAPE_RE.match(raw):
            singles.append(raw)
        else:
            malformed.append(raw)
    return FormulaCodes(ranges, tuple(singles), tuple(malformed), residual)


def extract_prev_targets(formula: str) -> tuple:
    """抽 PREV() 的（wp_code, sheet 名）二元组。"""
    return tuple(
        (m.group(1).strip(), m.group(2).strip())
        for m in _PREV_RE.finditer(formula or "")
    )


def parent_code(code: str) -> str:
    """去掉点号子级得到父级科目码。TB('2501.01') 的父码是 2501。"""
    return (code or "").split(".", 1)[0].strip()


def is_code_allowed(code: str, allowed_codes) -> bool:
    """子科目前缀合法：去掉点号子级后的父码属于 allowed_codes 即放行。"""
    allowed = set(allowed_codes or ())
    if not allowed:
        return False
    return parent_code(code) in allowed


def codes_within_range(lo: str, hi: str, codes) -> tuple:
    """返回落在 [lo, hi] 闭区间内的科目码（按父码比较）。

    lo/hi 形态异常时保守返回全部 codes（宁可打红也不放过病态区间）。
    """
    lo_s, hi_s = (lo or "").strip(), (hi or "").strip()
    if not (lo_s.isdigit() and hi_s.isdigit()):
        return tuple(sorted(set(codes)))
    lo_i, hi_i = int(lo_s), int(hi_s)
    if lo_i > hi_i:
        lo_i, hi_i = hi_i, lo_i
    hit = []
    for c in codes:
        p = parent_code(c)
        if p.isdigit() and lo_i <= int(p) <= hi_i:
            hit.append(c)
    return tuple(sorted(set(hit)))


def evaluate_range_health(lo: str, hi: str, own_wp_code: str, code_owner: dict) -> tuple:
    """区间健全性：不得横跨两个 L 循环，也不得只落在别的循环上。"""
    hits = codes_within_range(lo, hi, code_owner.keys())
    owners = sorted({code_owner[c] for c in hits})
    problems = []
    if len(owners) > 1:
        detail = "、".join(f"{c}（{code_owner[c]}）" for c in hits)
        problems.append(
            f"区间 '{lo}~{hi}' 横跨 {len(owners)} 个 L 循环（{'、'.join(owners)}），"
            f"会把这些循环的科目一起扫进合计: {detail}。"
            "病态区间必须拆成离散 TB() 或收窄到本循环科目族。"
        )
    elif owners and owners[0] != own_wp_code:
        problems.append(
            f"区间 '{lo}~{hi}' 只落在 {owners[0]} 循环的科目上，"
            f"而本块 wp_code={own_wp_code}，取数口径与所属循环不符。"
        )
    return tuple(problems)


def detect_description_label_conflicts(
    description: str,
    expected_label: str,
    known_labels,
    allowed_labels=(),
) -> tuple:
    """检测 description 里出现的、与本块科目名冲突的已登记科目中文名。

    只在"已登记的 L 循环科目中文名"这个闭集合内判定（该集合由 L_CYCLE_SPECS 派生，
    不手写第二份），故别的循环的科目名（如 租赁负债 / 预计负债）不在此判据覆盖内,
    它们由科目码判据兜住。
    """
    text = description or ""
    allowed = set(allowed_labels or ())
    if expected_label:
        allowed.add(expected_label)
    return tuple(
        sorted(lb for lb in (known_labels or ()) if lb and lb not in allowed and lb in text)
    )


def build_label_index(specs: dict) -> dict:
    """科目中文名 -> wp_code。由 L_CYCLE_SPECS 派生，禁手写第二份。"""
    return {spec.account_label: wp for wp, spec in specs.items() if spec.account_label}


def build_code_owner_index(specs: dict) -> dict:
    """兜底科目码 -> wp_code。"""
    index = {}
    for wp, spec in specs.items():
        for code in spec.fallback_codes or ():
            index[code] = wp
    return index


# ---------------------------------------------------------------------------
# 数据加载（生产模块一律在函数内 import，禁模块顶层）
# ---------------------------------------------------------------------------


def _ensure_backend_on_path() -> None:
    root = str(BACKEND_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def load_l_cycle_specs() -> dict:
    """import 生产真源 L_CYCLE_SPECS。失败一律 fail（不 skip）。"""
    _ensure_backend_on_path()
    try:
        from app.services.l_cycle_extraction.account_scope import L_CYCLE_SPECS
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"{_CLASS_A} 无法 import 生产真源 "
            f"app.services.l_cycle_extraction.account_scope.L_CYCLE_SPECS: {exc!r}。"
            "注意：本项目有两个同名导出，four_table/l_cycle_specs.py 那份只被测试与 L0 消费，"
            "render 真实消费的是 l_cycle_extraction/account_scope.py 这份，判据必须锁后者。"
        )
    return dict(L_CYCLE_SPECS)


def load_l_prefill_blocks() -> list:
    """加载 prefill_formula_mapping.json 里的 L 类块（含 L0）。"""
    if not PREFILL_PATH.exists():
        pytest.fail(f"{_CLASS_A} 公式预设数据文件不存在: {PREFILL_PATH}")
    try:
        data = json.loads(PREFILL_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"{_CLASS_A} 公式预设数据文件解析失败 {PREFILL_PATH}: {exc!r}")
    mappings = data.get("mappings")
    if not isinstance(mappings, list):
        pytest.fail(
            f"{_CLASS_A} 顶层 mappings 不是数组（实际 {type(mappings).__name__}）；"
            "字段名是 mappings，块内 sheet 字段名是 sheet 不是 sheet_name。"
        )
    return [b for b in mappings if L_WP_CODE_RE.match(str(b.get("wp_code") or ""))]


def load_visible_sheet_names() -> dict:
    """openpyxl 实时直读源 xlsx 的 visible sheet 名（hidden 不算）。

    判据必须实时直读，不写死清单。空格、半角括号、同名 sheet 都按原样返回，
    比较时用精确相等（不 strip），否则会把 ' 短期借款实质性程序表L1A' 这类
    首字符带空格的真实 tab 名判成不存在。
    """
    if not TEMPLATE_DIR.exists():
        pytest.fail(f"{_CLASS_A} L 类源模板目录不存在: {TEMPLATE_DIR}")
    try:
        from openpyxl import load_workbook
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"{_CLASS_A} 无法 import openpyxl: {exc!r}")

    result = {}
    for path in sorted(TEMPLATE_DIR.glob("*.xlsx")):
        if path.name.startswith("~$"):
            continue  # WPS/Excel 打开时的锁文件
        code = path.stem.split(" ", 1)[0].strip()
        wb = load_workbook(path, read_only=True)
        try:
            names = tuple(
                ws.title for ws in wb.worksheets if ws.sheet_state == "visible"
            )
        finally:
            wb.close()
        result[code] = names
    return result


# ---------------------------------------------------------------------------
# 块级判据（可复用，Wave 2 幂等脚本 import 这几个）
# ---------------------------------------------------------------------------


def _block_key(block: dict) -> tuple:
    return (str(block.get("wp_code") or ""), str(block.get("sheet") or ""))


def _fmt_key(key: tuple) -> str:
    return f"{key[0]} / {key[1]}"


def evaluate_block_code_coherence(
    block: dict,
    specs: dict,
    allowlist: dict | None = None,
    without_spec: dict | None = None,
) -> tuple:
    """Property 1 / 2 / 6：cells 公式实参必须属于本循环科目族。

    PLACEHOLDER 类型放行，但要求 description 长度不少于
    PLACEHOLDER_MIN_DESC_CHARS 字（否则"写不成公式"会退化成逃逸阀）。
    """
    allowlist = CROSS_CYCLE_ALLOWLIST if allowlist is None else allowlist
    without_spec = WP_CODES_WITHOUT_SPEC if without_spec is None else without_spec

    wp, sheet = _block_key(block)
    allowance = allowlist.get((wp, sheet))
    extra_codes = set(allowance.codes) if allowance else set()
    spec = specs.get(wp)

    problems = []
    if spec is None and wp not in without_spec:
        problems.append(
            f"wp_code {wp} 既不在 L_CYCLE_SPECS 也未在 WP_CODES_WITHOUT_SPEC 登记，"
            "无法判定其合法科目集"
        )

    for cell in block.get("cells") or []:
        ref = str(cell.get("cell_ref") or "")
        ftype = str(cell.get("formula_type") or "")
        desc = str(cell.get("description") or "")
        formula = str(cell.get("formula") or "")

        if ftype == "PLACEHOLDER":
            n = len(desc.strip())
            if n < PLACEHOLDER_MIN_DESC_CHARS:
                problems.append(
                    f"cell {ref}: formula_type=PLACEHOLDER 放行，但 description 只有 {n} 字，"
                    f"少于 {PLACEHOLDER_MIN_DESC_CHARS} 字，必须写明该格为什么写不成公式以及取数真源"
                )
            continue

        if spec is None:
            continue

        allowed = set(spec.fallback_codes or ()) | extra_codes
        codes = extract_formula_codes(formula)
        for bad in codes.malformed:
            problems.append(
                f"cell {ref}: 科目码位置的实参 {bad!r} 不是合法科目码形态; formula={formula}"
            )
        for code in codes.singles:
            if not is_code_allowed(code, allowed):
                allowed_txt = "、".join(sorted(allowed)) if allowed else "空（宁缺勿造）"
                problems.append(
                    f"cell {ref}: 公式引用科目 {code}（父码 {parent_code(code)}）"
                    f"不属于本循环 {wp}（{spec.account_label}）的合法科目集 [{allowed_txt}]; "
                    f"formula={formula}"
                )
    return tuple(problems)


def evaluate_block_description_coherence(
    block: dict,
    specs: dict,
    allowlist: dict | None = None,
) -> tuple:
    """Property 3：description 里的科目中文名必须与本块 account_label 一致。"""
    allowlist = CROSS_CYCLE_ALLOWLIST if allowlist is None else allowlist
    wp, sheet = _block_key(block)
    spec = specs.get(wp)
    if spec is None:
        return ()

    label_index = build_label_index(specs)
    known = set(label_index)
    allowance = allowlist.get((wp, sheet))
    allowed_labels = set(allowance.labels) if allowance else set()

    problems = []
    for cell in block.get("cells") or []:
        ref = str(cell.get("cell_ref") or "")
        desc = str(cell.get("description") or "")
        for lb in detect_description_label_conflicts(
            desc, spec.account_label, known, allowed_labels
        ):
            problems.append(
                f"cell {ref}: description 出现已登记科目名 {lb!r}"
                f"（属 {label_index[lb]} 循环），而本块 wp_code={wp} 的科目名是 "
                f"{spec.account_label!r}; description={desc!r}"
            )
    return tuple(problems)


def evaluate_block_sheet_existence(
    block: dict, visible_sheets: dict, out_of_scope=None
) -> tuple:
    """Property 4：块的 sheet 必须是该 wp_code 源 xlsx 的真实 visible tab。"""
    wp, sheet = _block_key(block)
    registry = OUT_OF_SCOPE_WP_CODES if out_of_scope is None else out_of_scope
    if wp in registry:
        return ()
    names = visible_sheets.get(wp)
    if names is None:
        return (f"源模板目录里找不到 wp_code={wp} 对应的 xlsx，无法校验 sheet {sheet!r}",)
    if sheet in names:
        return ()
    near = [n for n in names if n.strip() == sheet.strip() or sheet.strip() in n]
    hint = f"；形近的真实 tab: {near}" if near else ""
    return (
        f"sheet {sheet!r} 不在 {wp} 源 xlsx 的 visible tab 集合内"
        f"（共 {len(names)} 张）{hint}",
    )


def evaluate_block_prev_targets(block: dict, visible_sheets: dict) -> tuple:
    """Property 4（后半）：PREV() 第二实参必须是该 wp_code 源 xlsx 真实 tab 名。"""
    wp, sheet = _block_key(block)
    problems = []
    for cell in block.get("cells") or []:
        ref = str(cell.get("cell_ref") or "")
        formula = str(cell.get("formula") or "")
        for target_wp, target_sheet in extract_prev_targets(formula):
            names = visible_sheets.get(target_wp)
            if names is None:
                problems.append(
                    f"cell {ref}: PREV 指向 wp_code={target_wp}，源模板目录里没有对应 xlsx; "
                    f"formula={formula}"
                )
                continue
            if target_sheet not in names:
                near = [n for n in names if n.strip() == target_sheet.strip()]
                hint = f"；形近的真实 tab: {near}" if near else ""
                problems.append(
                    f"cell {ref}: PREV 第二实参 {target_sheet!r} 不是 {target_wp} 源 xlsx 的"
                    f"真实 visible tab{hint}; formula={formula}"
                )
    _ = sheet, wp
    return tuple(problems)


def evaluate_block_range_health(block: dict, specs: dict, out_of_scope=None) -> tuple:
    """Property 5：区间函数不得跨循环。"""
    wp, _sheet = _block_key(block)
    registry = OUT_OF_SCOPE_WP_CODES if out_of_scope is None else out_of_scope
    if wp in registry:
        return ()
    code_owner = build_code_owner_index(specs)
    problems = []
    for cell in block.get("cells") or []:
        ref = str(cell.get("cell_ref") or "")
        formula = str(cell.get("formula") or "")
        for lo, hi in extract_formula_codes(formula).ranges:
            for msg in evaluate_range_health(lo, hi, wp, code_owner):
                problems.append(f"cell {ref}: {msg} formula={formula}")
    return tuple(problems)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


