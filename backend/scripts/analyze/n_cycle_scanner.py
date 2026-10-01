# -*- coding: utf-8 -*-
"""N 循环（税费）双向回写 spec 扫描器 —— 共同判据的唯一可执行实现。

spec: `.kiro/specs/n-cycle-sync-foundation-and-first-canary`（foundation Task 1）
被 `n1-n3-host-inline-router-and-shared-adoption` 与
`n2-n5-json-table-identity-and-cross-entry-readonly` 两份 lane spec 共用。

═══ 为什么是独立模块而不是写在测试里 ═══════════════════════════════════════════

三份 spec 的判据共享同一套扫描口径（NC-5 域口径 / NC-7 removeRow 归类 /
NC-17 漏加小计双条件 / NC-32 超列引用三族 …）。若各测试文件各写一份，口径会漂移，
而「口径漂移」恰恰是本系列反复踩的坑（见 memory.md 方法论铁律 ②④⑮）。

═══ 纪律 ═══════════════════════════════════════════════════════════════════

1. 本模块**只负责现算**，不含任何期望值常量；期望值只出现在调用方的比对等式里。
2. 所有扫描先剥注释（`strip_comments`，同长空白替换保留行号）。
3. 行数口径统一 `len(text.split("\\n"))`（`splitlines()` 恒少 1）。
4. 每个「结构性零」扫描函数都必须能在他域样本上命中（变异证明由调用方负责构造）。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator

# ─── 路径常量 ────────────────────────────────────────────────────────────────
_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"
SYNC_DIR = WP_COMPONENTS / "sync"
TEMPLATE_DIR = BACKEND / "wp_templates"
N_TEMPLATE_DIR = TEMPLATE_DIR / "N"
TEMPLATE_INDEX = TEMPLATE_DIR / "_index.json"

SLICE_PATH = DATA / "workpaper_sync_n_cycle_manifest_slice.json"
DELETION_PLAN_PATH = DATA / "workpaper_sync_n_cycle_deletion_plan.json"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
PARADIGM_PATH = DATA / "workpaper_sync_migration_paradigm.json"

SOURCE_SUFFIXES = (".ts", ".vue", ".js")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def count_lines(text: str) -> int:
    """行数口径：`len(text.split("\\n"))`（铁律 ⑩）。"""
    return len(text.split("\n"))


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 注释剥离（NC-3 / NC-5 的前置）
# ═══════════════════════════════════════════════════════════════════════════
def _blank_keep_newlines(match: re.Match[str]) -> str:
    """同长空白替换：非换行字符换成空格，行号与列号都不变。"""
    return re.sub(r"[^\n]", " ", match.group(0))


def strip_comments(source: str) -> str:
    """剥块注释 / HTML 注释 / 行注释，行号保持不变。

    行注释用 `(?<![:\\w"'`\\\\])//` 避开 URL 的 `https://` 与字符串里的 `//`。
    """
    source = re.sub(r"/\*.*?\*/", _blank_keep_newlines, source, flags=re.S)
    source = re.sub(r"<!--.*?-->", _blank_keep_newlines, source, flags=re.S)
    source = re.sub(
        r"(?<![:\w\"'`\\])//[^\n]*", lambda m: " " * len(m.group(0)), source
    )
    return source


# ═══════════════════════════════════════════════════════════════════════════
# NC-5 · N 域文件集三路取并（🔴 M 轮缺小写分支，漏 35 个文件）
# ═══════════════════════════════════════════════════════════════════════════
_DIR_SEG_RE = re.compile(r"[/\\]n[1-5][/\\]")
_UPPER_NAME_RE = re.compile(r"^(?:use|Gt)?N[1-5](?![0-9])(?:[A-Z]|[-.]|$)")
_LOWER_NAME_RE = re.compile(r"^n[1-5][A-Z]")
_NCYCLE_NAME_RE = re.compile(r"^nCycle")
_N_KEY_REF_RE = re.compile(r"\bN[1-5]-")

#: 判定分支名 → 判定函数（文件名 / posix 路径 / 原文）
DomainBranch = Callable[[str, str, str], bool]

DOMAIN_BRANCHES: dict[str, DomainBranch] = {
    "seg": lambda name, posix, text: bool(_DIR_SEG_RE.search(posix)),
    "upper": lambda name, posix, text: bool(_UPPER_NAME_RE.match(name)),
    "lower": lambda name, posix, text: bool(_LOWER_NAME_RE.match(name)),
    "ref": lambda name, posix, text: bool(
        _NCYCLE_NAME_RE.match(name) and _N_KEY_REF_RE.search(text)
    ),
}


def is_test_path(path: Path) -> bool:
    posix = path.as_posix()
    return (
        "__tests__" in posix
        or "/tests/" in posix
        or path.name.endswith(".spec.ts")
        or path.name.endswith(".test.ts")
    )


def iter_frontend_sources() -> Iterator[Path]:
    for p in FRONTEND.rglob("*"):
        if p.is_file() and p.suffix in SOURCE_SUFFIXES:
            yield p


@dataclass(frozen=True)
class DomainFile:
    """N 域文件及其命中的判定分支。"""

    path: Path
    branches: frozenset[str]
    is_test: bool

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def rel(self) -> str:
        return self.path.relative_to(ROOT).as_posix()


def scan_domain_files(branches: Iterable[str] | None = None) -> list[DomainFile]:
    """现算 N 域文件集。

    `branches` 为 None 时用全部四路（strict 正口径）；传子集可做变异证明
    （如去掉 `lower` 分支观察漏检量）。
    """
    active = tuple(DOMAIN_BRANCHES) if branches is None else tuple(branches)
    for b in active:
        if b not in DOMAIN_BRANCHES:
            raise ValueError(f"未知判定分支 {b!r}")
    out: list[DomainFile] = []
    for p in iter_frontend_sources():
        name = p.name
        posix = p.as_posix()
        text: str | None = None
        hit: set[str] = set()
        for b in active:
            if b == "ref":
                if not _NCYCLE_NAME_RE.match(name):
                    continue
                if text is None:
                    text = read_text(p)
            if DOMAIN_BRANCHES[b](name, posix, text or ""):
                hit.add(b)
        if hit:
            out.append(DomainFile(p, frozenset(hit), is_test_path(p)))
    return sorted(out, key=lambda d: d.path.as_posix())


def production_files(files: Iterable[DomainFile]) -> list[DomainFile]:
    return [f for f in files if not f.is_test]


def test_files(files: Iterable[DomainFile]) -> list[DomainFile]:
    return [f for f in files if f.is_test]


def loose_only_files() -> list[Path]:
    """宽口径独有文件：文件名任意位置含 `N[1-5]` 但四路 strict 全不命中。

    返回集合非空即说明 strict 口径漏了东西（NC-5 的 `loose_only = 0` 判据）。
    🔴 排除 N 域以外的同形命名（如 `useG9L3…`）—— 这里只认 `N[1-5]` 紧跟大写/分隔符，
    且文件必须真的引用 N 键，否则就是别域的巧合命名。
    """
    strict = {f.path for f in scan_domain_files()}
    loose_re = re.compile(r"N[1-5](?![0-9])(?:[A-Z]|FormData|DualMode|Tab|Sheet)")
    out: list[Path] = []
    for p in iter_frontend_sources():
        if p in strict or is_test_path(p):
            continue
        if not loose_re.search(p.name):
            continue
        if _N_KEY_REF_RE.search(read_text(p)):
            out.append(p)
    return sorted(out)


# ═══════════════════════════════════════════════════════════════════════════
# 源码站点扫描基元
# ═══════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Site:
    """一个源码命中站点（文件 + 行号 + 该行文本）。"""

    rel: str
    line: int
    text: str
    extra: tuple[tuple[str, str], ...] = ()

    def __str__(self) -> str:  # pragma: no cover - 仅调试输出用
        return f"{self.rel}#L{self.line}"


def stripped_sources(files: Iterable[DomainFile]) -> dict[str, str]:
    """文件相对路径 → 剥注释后的源码（行号不变）。"""
    return {f.rel: strip_comments(read_text(f.path)) for f in files}


def scan_regex(sources: dict[str, str], pattern: re.Pattern[str] | str) -> list[Site]:
    """在已剥注释的源码上逐行扫正则，返回站点列表。"""
    rx = re.compile(pattern) if isinstance(pattern, str) else pattern
    out: list[Site] = []
    for rel, text in sorted(sources.items()):
        for i, line in enumerate(text.split("\n"), start=1):
            if rx.search(line):
                out.append(Site(rel, i, line.rstrip()))
    return out


def scan_literal(sources: dict[str, str], literal: str) -> list[Site]:
    """逐行扫字面量（已剥注释 ⇒ 命中即代码）。"""
    out: list[Site] = []
    for rel, text in sorted(sources.items()):
        for i, line in enumerate(text.split("\n"), start=1):
            if literal in line:
                out.append(Site(rel, i, line.rstrip()))
    return out


def count_literal_code_vs_comment(
    files: Iterable[DomainFile], literal: str
) -> tuple[list[Site], list[Site]]:
    """返回 (代码命中, 注释命中)。

    NC-3 的核心：端点字面量判据必须先剥注释，否则迁移注释会被当成违规站点。
    """
    code: list[Site] = []
    comment: list[Site] = []
    for f in sorted(files, key=lambda d: d.rel):
        raw = read_text(f.path)
        bare = strip_comments(raw)
        raw_lines = raw.split("\n")
        bare_lines = bare.split("\n")
        for i, (rl, bl) in enumerate(zip(raw_lines, bare_lines), start=1):
            in_raw = literal in rl
            in_bare = literal in bl
            if in_bare:
                code.append(Site(f.rel, i, rl.rstrip()))
            elif in_raw:
                comment.append(Site(f.rel, i, rl.rstrip()))
    return code, comment


# ═══════════════════════════════════════════════════════════════════════════
# NC-6 / NC-8 · 行身份六族
# ═══════════════════════════════════════════════════════════════════════════
#: 六族正则。口径写在这里，调用方只消费结果 —— 任何口径调整都只有这一处。
ROW_IDENTITY_PATTERNS: dict[str, re.Pattern[str]] = {
    # 族 A：位置化**持久化键**（item_id 模板里带数组下标）
    # 🔴 与「位置化渲染键」分开计数：前者一落库就串行，后者只影响 DOM diff。
    "A_positional_persistence_key": re.compile(
        r"\$\{\s*(?:ITEM_PREFIX|PREFIX)\s*\}\s*-\s*\$\{\s*(?:i|idx|index|n)\s*\}"
    ),
    # 族 A'：位置化**渲染键**（`key:` / `:key` 上的下标派生值）
    "A2_positional_render_key": re.compile(
        r"\b(?:key|rowKey|rowId)\s*:\s*`[^`\n]*\$\{\s*(?:i|idx|index|n)\s*\}"
    ),
    # 族 B：数组位置寻址（按下标 update / remove / 槽写 / filter / splice）
    "B_array_position_addressing": re.compile(
        r"(?:function\s+(?:update|set|remove|delete)\w*\s*\(\s*(?:rowIndex|index|idx)\b)"
        r"|(?:const\s+(?:update|set|remove|delete)\w*\s*=\s*\(\s*(?:rowIndex|index|idx)\b)"
        r"|(?:\b(?:currentRows|rows|list|items|manualRows|projects|entries)\s*\.?value?\s*\[\s*(?:rowIndex|index|idx|i)\s*\])"
        r"|(?:\.filter\(\s*\([^)\n]*\b(?:i|idx|index)\b[^)\n]*\)\s*=>[^\n]*\b(?:i|idx|index)\s*!==)"
        r"|(?:\.splice\(\s*(?:rowIndex|index|idx|i)\b)"
    ),
    # 族 C：展示序号（`seq` / `index: i + 1` 之类，**不是**缺陷，是反向判据）
    "C_display_sequence": re.compile(
        r"\b(?:seq|序号|rowNo|no)\s*:\s*(?:i|idx|index)\s*\+\s*1"
        r"|\bindex\s*:\s*(?:i|idx)\s*\+\s*1"
    ),
    # 族 D：熵键（Date.now / Math.random 生成的不透明 id）
    "D_entropy_key": re.compile(r"Date\.now\(\)|Math\.random\(\)"),
    # 族 E：稳定行身份（按 rowId / rowKey / .id 寻址或赋值）—— 正面样板
    "E_stable_identity": re.compile(
        r"\b(?:rowId|rowKey)\b|\br\.id\b|\brow\.id\b|\.id\s*===|id\s*:\s*r\.id\b"
    ),
    # M 轮形态：`row-${n}` 中缀（N 域应为 0，须配变异证明）
    "M_row_infix_template": re.compile(r"`[^`\n]*row-\$\{\s*(?:i|idx|index|n)\s*\}"),
}


def scan_row_identity_families(
    sources: dict[str, str],
) -> dict[str, list[Site]]:
    """六族逐族现算。返回 族名 → 站点列表。"""
    return {
        family: scan_regex(sources, rx)
        for family, rx in ROW_IDENTITY_PATTERNS.items()
    }


# ═══════════════════════════════════════════════════════════════════════════
# NC-7 · `removeRow` 签名族四元组
# ═══════════════════════════════════════════════════════════════════════════
_REMOVE_CALL_RE = re.compile(
    r"\b(remove|delete)(\w*)(?:Row|Rows|Entry|Project|Item|Line)?\s*\(\s*([^)\n]*)\)"
)
_REMOVE_DECL_RE = re.compile(
    r"(?:function\s+|const\s+)(remove\w*|delete\w*)\s*(?:=\s*)?\(\s*([^)\n]*)\)"
)
_BY_ROWID_RE = re.compile(r"rowId\b|rowKey\b|\.id\b|\bid\b")
#: 🔴 `[Ii]ndex` 必须认大写 I —— `rowIndex` 用小写 `index` 扫是 **0 命中**，
#  会被兜到 `other` 桶里（实测本域 4 处 `rowIndex: number` 全被误归类）。
_BY_INDEX_RE = re.compile(r"[Ii]ndex|idx|\$index|\.length|\bi\b")


def classify_remove_arg(first_arg: str) -> str:
    """NC-7 四元组归类：by_rowid / by_index / other。

    🔴 顺序重要：先判 rowid（`rowId` 内含 `id`），再判 index。
    """
    arg = first_arg.strip()
    if not arg:
        return "other"
    if _BY_ROWID_RE.search(arg):
        return "by_rowid"
    if _BY_INDEX_RE.search(arg):
        return "by_index"
    return "other"


@dataclass(frozen=True)
class RemoveCall:
    rel: str
    line: int
    signature: str
    first_arg: str
    kind: str


def scan_remove_row_calls(sources: dict[str, str]) -> list[RemoveCall]:
    """现算所有 remove*/delete* 的**声明**站点并按首参归类。

    只数声明（`function removeRow(...)` / `const removeRow = (...)`），不数调用点 ——
    调用点会把同一个语义重复计数，而「按什么寻址」是声明决定的。
    """
    out: list[RemoveCall] = []
    for rel, text in sorted(sources.items()):
        for i, line in enumerate(text.split("\n"), start=1):
            m = _REMOVE_DECL_RE.search(line)
            if not m:
                continue
            name, args = m.group(1), m.group(2)
            first = args.split(",")[0]
            out.append(
                RemoveCall(rel, i, f"{name}({args.strip()})", first, classify_remove_arg(first))
            )
    return out


def remove_call_histogram(calls: Iterable[RemoveCall]) -> dict[str, int]:
    hist = {"by_index": 0, "by_rowid": 0, "other": 0}
    for c in calls:
        hist[c.kind] += 1
    return hist


# ═══════════════════════════════════════════════════════════════════════════
# 模板层（openpyxl）
# ═══════════════════════════════════════════════════════════════════════════
def iter_template_files() -> list[Path]:
    """N 册全集（跳 `~$` Office 锁文件）。"""
    if not N_TEMPLATE_DIR.is_dir():
        return []
    return sorted(
        p
        for p in N_TEMPLATE_DIR.glob("*.xlsx")
        if not p.name.startswith("~$")
    )


def col_letters_to_index(letters: str) -> int:
    """`A` → 1，`AA` → 27。"""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


@dataclass
class SheetFacts:
    workbook: str
    sheet: str
    max_row: int
    max_col: int
    last_value_row: int
    last_value_col: int
    formula_cells: int
    bare_if_cells: int
    hidden: bool
    footer_raw: str


def load_workbook(path: Path, data_only: bool = False):
    from openpyxl import load_workbook as _lw

    return _lw(path, data_only=data_only, read_only=False, keep_vba=False)


def workbook_sheet_facts(path: Path) -> list[SheetFacts]:
    """逐 sheet 现算几何与公式口径。

    口径（NC-25 / NF-P4）：`data_only=False` + `isinstance(v, str) and v.startswith("=")`
    且 `len(v) > 1`。`data_only=True` 下同口径应得 0（反证）。
    """
    wb = load_workbook(path)
    out: list[SheetFacts] = []
    try:
        for ws in wb.worksheets:
            formula = 0
            bare_if = 0
            lvr = 0
            lvc = 0
            for row in ws.iter_rows():
                for cell in row:
                    v = cell.value
                    if v is None:
                        continue
                    if cell.row > lvr:
                        lvr = cell.row
                    if cell.column > lvc:
                        lvc = cell.column
                    if isinstance(v, str) and v.startswith("=") and len(v) > 1:
                        formula += 1
                        if _BARE_IF_RE.search(v):
                            bare_if += 1
            out.append(
                SheetFacts(
                    workbook=path.name,
                    sheet=ws.title,
                    max_row=ws.max_row or 0,
                    max_col=ws.max_column or 0,
                    last_value_row=lvr,
                    last_value_col=lvc,
                    formula_cells=formula,
                    bare_if_cells=bare_if,
                    hidden=ws.sheet_state != "visible",
                    footer_raw=_raw_footer(ws),
                )
            )
    finally:
        wb.close()
    return out


#: 裸 IF = 没有 IFERROR 包裹的 IF（除零 / #REF! 会直接外泄）
_BARE_IF_RE = re.compile(r"(?<!ERROR\()\bIF\(")


def _raw_footer(ws) -> str:
    """🔴 NC-36 / 铁律 ⑰：`ws.oddFooter` 在部分册上解析失败后**静默返回空**。

    这里直接取 openpyxl 的 HeaderFooter 字符串表示（`.text` 三段拼接），
    读不到就返回空串，由调用方按「空分母 vs 真空」区分。
    """
    try:
        hf = ws.oddFooter
        parts = [getattr(hf, side).text or "" for side in ("left", "center", "right")]
        return "".join(parts)
    except Exception:  # pragma: no cover - 解析失败是被观测对象本身
        return ""


def formula_cells_with_data_only(path: Path) -> int:
    """反证口径：`data_only=True` 下同一判据应得 0。"""
    wb = load_workbook(path, data_only=True)
    n = 0
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    v = cell.value
                    if isinstance(v, str) and v.startswith("=") and len(v) > 1:
                        n += 1
    finally:
        wb.close()
    return n


# ═══════════════════════════════════════════════════════════════════════════
# NC-32 · 超列引用三族（🔴 wp_code 与 Excel A1 引用语法同形）
# ═══════════════════════════════════════════════════════════════════════════
_A1_REF = r"\$?[A-Z]{1,3}\$?\d+"
#: 🔴 必须把「sheet 限定段 **连同它后面的引用**」一起剔掉。
#  只剔 `'...'!` 会把 `='明细表N2-2'!M10` 的 `M10` 留下来，然后拿**本表**的
#  max_column 去判它越界 —— 正是 L 轮误报①（越界引用须按**目标 sheet** 判）的同型。
#  N2 附注披露（国企）靠这一条差出 39 处假阳（56 → 17）。
_QUOTED_SHEET_RE = re.compile(rf"'[^']*'!{_A1_REF}(?::{_A1_REF})?")
_CJK_SHEET_RE = re.compile(
    rf"[^\s\-+*/(),:=<>!&'\"]*[\u4e00-\u9fff][^\s\-+*/(),:=<>!'\"]*!{_A1_REF}(?::{_A1_REF})?"
)
_FUNC_NAME_RE = re.compile(r"\b[A-Z][A-Z0-9.]*\(")
_COL_REF_RE = re.compile(r"(?<![A-Z0-9_!$])(\$?)([A-Z]{1,3})(\$?)(\d+)")


def clean_formula_for_col_scan(formula: str) -> str:
    """剔除「sheet 限定段 + 其引用」、函数名 —— 不剔则误报 176（NC-32）。"""
    f = _QUOTED_SHEET_RE.sub(_blank_keep_newlines, formula)
    f = _CJK_SHEET_RE.sub(_blank_keep_newlines, f)
    f = _FUNC_NAME_RE.sub(lambda m: " " * len(m.group(0)), f)
    return f


@dataclass(frozen=True)
class OverflowRef:
    workbook: str
    sheet: str
    cell: str
    formula: str
    ref_col: str
    ref_row: int
    max_col: int
    family: str


def _is_range_end(cleaned: str, start: int) -> bool:
    """该引用是否是区间终点（`:` 紧邻其前）。"""
    j = start - 1
    while j >= 0 and cleaned[j] in " $":
        j -= 1
    return j >= 0 and cleaned[j] == ":"


def scan_overflow_col_refs(path: Path) -> tuple[list[OverflowRef], int]:
    """返回 (正确口径命中列表, 错口径命中数)。

    正确口径：先 `clean_formula_for_col_scan`，再比对 `col_index > sheet.max_column`。
    错口径：不做任何剔除 —— 中文 sheet 名里的 `N2-1` 会被当列引用，用于防未来放宽正则。
    """
    wb = load_workbook(path)
    hits: list[OverflowRef] = []
    wrong = 0
    try:
        for ws in wb.worksheets:
            max_col = ws.max_column or 0
            for row in ws.iter_rows():
                for cell in row:
                    v = cell.value
                    if not (isinstance(v, str) and v.startswith("=") and len(v) > 1):
                        continue
                    for m in _COL_REF_RE.finditer(v):
                        if col_letters_to_index(m.group(2)) > max_col:
                            wrong += 1
                    cleaned = clean_formula_for_col_scan(v)
                    for m in _COL_REF_RE.finditer(cleaned):
                        letters = m.group(2)
                        if col_letters_to_index(letters) <= max_col:
                            continue
                        family = "B_range_end" if _is_range_end(cleaned, m.start()) else "A_pending"
                        hits.append(
                            OverflowRef(
                                workbook=path.name,
                                sheet=ws.title,
                                cell=cell.coordinate,
                                formula=v,
                                ref_col=letters,
                                ref_row=int(m.group(4)),
                                max_col=max_col,
                                family=family,
                            )
                        )
    finally:
        wb.close()
    return classify_overflow_families(hits), wrong


def classify_overflow_families(hits: list[OverflowRef]) -> list[OverflowRef]:
    """把 `A_pending` 再分 A1（有反向分母 ⇒ 真缺陷录入事故）/ A2（整列同形 ⇒ 结构残留）。

    判据：同一 (册, sheet, 公式格所在列) 上的 pending 命中数 ≥ 2 ⇒ A2（无反向分母）；
    == 1 ⇒ A1（同列其余行是正确形态 ⇒ 有强反向分母）。
    """
    from collections import Counter

    key = lambda h: (h.workbook, h.sheet, re.match(r"[A-Z]+", h.cell).group(0))  # noqa: E731
    counts = Counter(key(h) for h in hits if h.family == "A_pending")
    out: list[OverflowRef] = []
    for h in hits:
        if h.family != "A_pending":
            out.append(h)
            continue
        fam = "A2_structural_residue" if counts[key(h)] >= 2 else "A1_real_defect"
        out.append(
            OverflowRef(
                h.workbook, h.sheet, h.cell, h.formula, h.ref_col,
                h.ref_row, h.max_col, fam,
            )
        )
    return out


def overflow_family_histogram(hits: Iterable[OverflowRef]) -> dict[str, int]:
    from collections import Counter

    c = Counter(h.family for h in hits)
    return {
        "A1_real_defect": c.get("A1_real_defect", 0),
        "A2_structural_residue": c.get("A2_structural_residue", 0),
        "B_range_end": c.get("B_range_end", 0),
    }


# ═══════════════════════════════════════════════════════════════════════════
# NC-9 · definedName 断链 / NC-36 · footer 三形态
# ═══════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class DefinedNameFact:
    workbook: str
    name: str
    value: str
    broken: bool


def scan_defined_names(path: Path) -> list[DefinedNameFact]:
    wb = load_workbook(path)
    out: list[DefinedNameFact] = []
    try:
        for name, dn in wb.defined_names.items():
            value = str(getattr(dn, "value", "") or "")
            out.append(
                DefinedNameFact(path.name, name, value, "#REF!" in value)
            )
    finally:
        wb.close()
    return out


#: footer 三形态：含斜杠的完整形态 / 缺斜杠的 `&P&N` / 空
FOOTER_FORM_WITH_SLASH = "with_separator"
FOOTER_FORM_MISSING_SLASH = "missing_separator"
FOOTER_FORM_EMPTY = "empty"


def classify_footer(raw: str) -> str:
    if not raw.strip():
        return FOOTER_FORM_EMPTY
    if "&P" in raw and "&N" in raw:
        between = raw.split("&P", 1)[1].split("&N", 1)[0]
        if not between.strip():
            return FOOTER_FORM_MISSING_SLASH
    return FOOTER_FORM_WITH_SLASH


# ═══════════════════════════════════════════════════════════════════════════
# NC-17 · 「合计漏加小计」双条件 / NC-20 · 倒挤减法链 / NC-35 · 幽灵列
# ═══════════════════════════════════════════════════════════════════════════
#: NC-17 / T-15：七种「合计/小计」标签字面量，🔴 禁去空格归一化
TOTAL_LABEL_LITERALS: tuple[str, ...] = (
    "合计", "小计", "总计", "合  计", "小  计", "合 计", "小 计",
)


def first_nonempty_cell_in_row(ws, row_idx: int):
    """🔴 NC-17 / T-15：标签定位用「首个非空列」而非限 A 列（`N5-5` r63 在 B 列）。"""
    for cell in ws[row_idx]:
        if cell.value is not None and str(cell.value).strip():
            return cell
    return None


@dataclass(frozen=True)
class TotalLabelSite:
    workbook: str
    sheet: str
    row: int
    col: str
    label: str


def scan_total_labels(path: Path) -> list[TotalLabelSite]:
    wb = load_workbook(path)
    out: list[TotalLabelSite] = []
    try:
        for ws in wb.worksheets:
            for row_idx in range(1, (ws.max_row or 0) + 1):
                cell = first_nonempty_cell_in_row(ws, row_idx)
                if cell is None:
                    continue
                text = str(cell.value).strip()
                if text in TOTAL_LABEL_LITERALS:
                    out.append(
                        TotalLabelSite(
                            path.name, ws.title, row_idx,
                            cell.column_letter, text,
                        )
                    )
    finally:
        wb.close()
    return out


_SUM_RANGE_RE = re.compile(r"SUM\(\s*\$?([A-Z]{1,3})\$?(\d+)\s*:\s*\$?([A-Z]{1,3})\$?(\d+)\s*\)")
_CELL_ADD_CHAIN_RE = re.compile(r"^=\s*\$?[A-Z]{1,3}\$?\d+(?:\s*\+\s*\$?[A-Z]{1,3}\$?\d+)+$")


def scan_missing_subtotal(path: Path) -> tuple[list[TotalLabelSite], list[TotalLabelSite]]:
    """NC-17 双条件判据。

    返回 (严格口径命中, 粗口径命中)。
    - 粗口径 cond1：合计行所属连续段区间内存在小计行。
    - 严格口径 = cond1 **且** cond2（同一合计行内跨列公式写法不一致）。
      🔴 缺 cond2 必误报 —— N1 两张附注披露的四个独立段落都是「同行全列写法一致」。
    """
    wb = load_workbook(path)
    rough: list[TotalLabelSite] = []
    strict: list[TotalLabelSite] = []
    try:
        for ws in wb.worksheets:
            labels = []
            for row_idx in range(1, (ws.max_row or 0) + 1):
                cell = first_nonempty_cell_in_row(ws, row_idx)
                if cell is None:
                    continue
                text = str(cell.value).strip()
                if text in TOTAL_LABEL_LITERALS:
                    labels.append((row_idx, text, cell.column_letter))
            subtotal_rows = [r for r, t, _ in labels if t.replace(" ", "") == "小计"]
            total_rows = [(r, t, c) for r, t, c in labels if t.replace(" ", "") != "小计"]
            for r, t, c in total_rows:
                lower = [s for s in subtotal_rows if s < r]
                if not lower:
                    continue
                site = TotalLabelSite(path.name, ws.title, r, c, t)
                rough.append(site)
                shapes = set()
                for cell in ws[r]:
                    v = cell.value
                    if isinstance(v, str) and v.startswith("="):
                        shapes.add("sum" if "SUM(" in v.upper() else "chain")
                if len(shapes) > 1:
                    strict.append(site)
    finally:
        wb.close()
    return strict, rough


_SUB_CHAIN_RE = re.compile(
    r"^=\s*\$?[A-Z]{1,3}\$?\d+(?:\s*[-+]\s*\$?[A-Z]{1,3}\$?\d+){1,}$"
)


@dataclass(frozen=True)
class SubtractionChain:
    workbook: str
    sheet: str
    cell: str
    formula: str
    in_total_row: bool
    vertical: bool


def scan_subtraction_chains(path: Path) -> tuple[list[SubtractionChain], list[SubtractionChain]]:
    """倒挤减法链：返回 (严格口径命中, 形态候选)。

    候选 = 纯单元格加减链且含至少一个 `-`。
    严格 = 候选 ∧ 落在「合计/小计」标签行 ∧ **纵向**（被减数在同一列）。
    🔴 两条收窄各有对象：
      - 不要求「合计行」会把 `N5-8 H10~H38` 那 29 行逐行核对公式全判成缺陷；
      - 不要求「纵向」会把同行跨列的差额计算（`=C12-B12+…`）判成倒挤，
        而倒挤的定义是「用总额减去已知明细得出剩余项」⇒ 必然是同列上下关系。
    """
    wb = load_workbook(path)
    cands: list[SubtractionChain] = []
    strict: list[SubtractionChain] = []
    try:
        for ws in wb.worksheets:
            total_rows: set[int] = set()
            for row_idx in range(1, (ws.max_row or 0) + 1):
                c = first_nonempty_cell_in_row(ws, row_idx)
                if c is not None and str(c.value).strip() in TOTAL_LABEL_LITERALS:
                    total_rows.add(row_idx)
            for row in ws.iter_rows():
                for cell in row:
                    v = cell.value
                    if not (isinstance(v, str) and v.startswith("=")):
                        continue
                    compact = v.replace(" ", "")
                    if "-" not in compact or not _SUB_CHAIN_RE.match(compact):
                        continue
                    own_col = re.match(r"[A-Z]+", cell.coordinate).group(0)
                    ref_cols = {
                        m.group(2) for m in _COL_REF_RE.finditer(compact)
                    }
                    item = SubtractionChain(
                        path.name,
                        ws.title,
                        cell.coordinate,
                        v,
                        cell.row in total_rows,
                        ref_cols == {own_col},
                    )
                    cands.append(item)
                    if item.in_total_row and item.vertical:
                        strict.append(item)
    finally:
        wb.close()
    return strict, cands


# ═══════════════════════════════════════════════════════════════════════════
# NC-35 · 超宽表与幽灵行列
# ═══════════════════════════════════════════════════════════════════════════
def ghost_geometry(facts: Iterable[SheetFacts]) -> dict[str, int]:
    """幽灵列 / 幽灵行统计。遍历上界一律取 `last_value_*`（决策 6）。"""
    ghost_col_sheets = [f for f in facts if f.max_col > f.last_value_col]
    ghost_row_sheets = [f for f in facts if f.max_row > f.last_value_row]
    return {
        "sheets_with_ghost_cols": len(ghost_col_sheets),
        "sheets_with_ghost_rows": len(ghost_row_sheets),
        "max_ghost_cols": max((f.max_col - f.last_value_col for f in facts), default=0),
        "max_ghost_rows": max((f.max_row - f.last_value_row for f in facts), default=0),
    }


def wide_sheets(facts: Iterable[SheetFacts], threshold: int = 200) -> list[SheetFacts]:
    """超宽表（`max_col >= threshold`）—— Excel 旧版列上限痕迹。"""
    return [f for f in facts if f.max_col >= threshold]


# ═══════════════════════════════════════════════════════════════════════════
# 门面：一次收集全部模板事实（测试用 module fixture 调用一次）
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class TemplateFacts:
    sheets: list[SheetFacts] = field(default_factory=list)
    overflow: list[OverflowRef] = field(default_factory=list)
    overflow_wrong_caliber: int = 0
    defined_names: list[DefinedNameFact] = field(default_factory=list)
    total_labels: list[TotalLabelSite] = field(default_factory=list)
    missing_subtotal_strict: list[TotalLabelSite] = field(default_factory=list)
    missing_subtotal_rough: list[TotalLabelSite] = field(default_factory=list)
    sub_chain_strict: list[SubtractionChain] = field(default_factory=list)
    sub_chain_candidates: list[SubtractionChain] = field(default_factory=list)
    sha256: dict[str, str] = field(default_factory=dict)
    sizes: dict[str, int] = field(default_factory=dict)


def collect_template_facts() -> TemplateFacts:
    tf = TemplateFacts()
    for path in iter_template_files():
        tf.sha256[path.name] = sha256_of(path)
        tf.sizes[path.name] = path.stat().st_size
        tf.sheets.extend(workbook_sheet_facts(path))
        hits, wrong = scan_overflow_col_refs(path)
        tf.overflow.extend(hits)
        tf.overflow_wrong_caliber += wrong
        tf.defined_names.extend(scan_defined_names(path))
        tf.total_labels.extend(scan_total_labels(path))
        s, r = scan_missing_subtotal(path)
        tf.missing_subtotal_strict.extend(s)
        tf.missing_subtotal_rough.extend(r)
        s2, c2 = scan_subtraction_chains(path)
        tf.sub_chain_strict.extend(s2)
        tf.sub_chain_candidates.extend(c2)
    return tf


# ═══════════════════════════════════════════════════════════════════════════
# NC-5 / NC-29 · orphan 可达性（statement-position import 边）
# ═══════════════════════════════════════════════════════════════════════════
#: `from '…'` 可独占一行（多行 import），故逐行扫 `from` 子句而不是整条 import 语句。
#  🔴 排除**双引号字符串内**的匹配：`workpaperSyncLegacyBaseline.generated.ts` 的
#  JSON `"snippet"` 字段里含完整 `from '...'` 形态，不剔会把它算成真实边。
_FROM_CLAUSE_RE = re.compile(r"(?<!\\)from\s+'([^']+)'")
_IMPORT_CALL_RE = re.compile(r"import\s*\(\s*'([^']+)'\s*\)")


def _resolve_specifier(importer: Path, spec: str) -> Path | None:
    """把 import 说明符解析成绝对路径（按**路径**比较，不按 stem）。"""
    if spec.startswith("@/"):
        base = FRONTEND / spec[2:]
    elif spec.startswith("."):
        base = (importer.parent / spec).resolve()
    else:
        return None
    for cand in (base, base.with_suffix(".ts"), base.with_suffix(".vue"), base / "index.ts"):
        if cand.is_file():
            return cand
    return base.with_suffix(".ts")


def build_import_graph() -> dict[Path, set[Path]]:
    """全前端 import 图：被引模块 → 引用它的文件集合。"""
    graph: dict[Path, set[Path]] = {}
    for p in iter_frontend_sources():
        text = strip_comments(read_text(p))
        for line in text.split("\n"):
            if '"' in line and "from" in line and "'" not in line:
                continue
            for rx in (_FROM_CLAUSE_RE, _IMPORT_CALL_RE):
                for m in rx.finditer(line):
                    target = _resolve_specifier(p, m.group(1))
                    if target is None:
                        continue
                    graph.setdefault(target, set()).add(p)
    return graph


@dataclass(frozen=True)
class ModuleReachability:
    rel: str
    lines: int
    production_consumers: tuple[str, ...]
    test_consumers: tuple[str, ...]

    @property
    def is_orphan(self) -> bool:
        return not self.production_consumers and not self.test_consumers


def module_reachability(paths: Iterable[Path], graph: dict[Path, set[Path]] | None = None) -> list[ModuleReachability]:
    g = graph if graph is not None else build_import_graph()
    out: list[ModuleReachability] = []
    for p in sorted(paths):
        consumers = g.get(p, set())
        prod = tuple(
            sorted(c.relative_to(ROOT).as_posix() for c in consumers if not is_test_path(c))
        )
        tst = tuple(
            sorted(c.relative_to(ROOT).as_posix() for c in consumers if is_test_path(c))
        )
        out.append(
            ModuleReachability(
                p.relative_to(ROOT).as_posix(),
                count_lines(read_text(p)) if p.is_file() else 0,
                prod,
                tst,
            )
        )
    return out


def n_domain_orphans(graph: dict[Path, set[Path]] | None = None) -> list[ModuleReachability]:
    """N 域零边模块全集（🔴 不止 dual-mode —— 只扫 `useN*DualMode.ts` 会把 8 报成 3）。"""
    g = graph if graph is not None else build_import_graph()
    candidates = [
        f.path
        for f in production_files(scan_domain_files())
        if f.path.suffix == ".ts" and f.path.parent == WP_COMPOSABLES
    ]
    return [m for m in module_reachability(candidates, g) if m.is_orphan]
