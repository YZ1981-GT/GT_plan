"""合并附注单元格公式、差额与「按公式填入」（spec consol-elimination-single-source-push 任务 7，design §七，ADR-CSP-005）。

- 公式存 ``consol_note_formula``（模板级，soe / listed），语法同报表公式（``TB`` / ``SUM_TB`` / ``REPORT`` / ``ROW``）。
- 求值与合并报表同一函数：附注单元格作为「排在全部报表行之后」的伪行交给 ``report_values`` / ``node_report``，
  所以 ``REPORT('BS-002')`` 取到的就是同一节点同一度量的报表行值（design §7.2）。
- 种子只写两类可确定的公式（ADR-CSP-005），其余单元格保持手工：
  (a) 章节名 = 资产负债表 / 利润表项目名 ⇒ 该章主表唯一「合计」行、唯一期末列（利润表项目取本期列）⇒ ``REPORT('行次')``；
  (b) 表行对上单体附注模板行的科目码，且这些科目都是该章报表行公式的取数项 ⇒ 按报表公式的系数取这些科目
      （``TB('1601') - TB('1602')``）。科目不在报表行取数范围内的行不种 —— 单体模板的科目码有语义不符的
      （受限资产、供应商融资列报项目、备抵科目相加、6701 / 6702 互换），照搬就是错数。
  表头含空列名 / 多级表头 / 多个期末列 / 多个合计行 ⇒ 列或行不确定，不种并记原因。
- 种子幂等：只写 ``source='seed'``；人工公式（``manual``）不覆盖；人工删掉的种子不再补回；模板里已不存在的种子删除。
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.schemas.consol_context import ConsolContext
    from app.services.consol_tree_service import TreeNode

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_push_models import NOTE_TEMPLATE_TYPES, ConsolNoteFormula
from app.services.consol_calc_basis import (
    MEASURE_ADJUSTMENT,
    MEASURE_CONSOLIDATED,
    MEASURE_ELIM_EQUITY,
    MEASURE_ELIM_TRADE,
    MEASURE_INDIVIDUAL,
    node_measures,
    to_cents,
)
from app.services.consol_elimination_sheet_service import row_name_key
from app.services.consol_group_tree import KIND_AGGREGATE
from app.services.consol_report_values import (
    ReportRow,
    RowValue,
    analyze_formula,
    canonical_formula,
    load_report_rows,
    node_report,
    report_values,
    row_account_terms,
    term_matches,
)
from app.services.consol_tree_service import iter_nodes

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
NOTE_ROW_TYPE = "consol_note"   # 不在 REPORT_TYPE_ORDER 里 ⇒ ordered_rows 排在全部报表行之后
KIND_REPORT_TOTAL = "report_total"
KIND_ACCOUNT_CODES = "account_codes"
KIND_LABELS = {KIND_REPORT_TOTAL: "章节合计取报表行", KIND_ACCOUNT_CODES: "表行取科目"}
SOURCE_LABELS = {"seed": "自动种子", "manual": "人工"}

CLOSING_HEADERS = frozenset({"期末余额", "期末数", "期末", "期末金额", "期末账面价值", "期末公允价值"})
PERIOD_HEADERS = frozenset({"本期发生额", "本期金额", "本期数", "本年发生额", "本年金额", "本年数"})
TOTAL_LABELS = frozenset({"合计", "总计"})
SEED_REPORT_TYPES = frozenset({"balance_sheet", "income_statement"})
MAX_ROW_INDEX = 999


class NoteFormulaError(ValueError):
    """请求与模板 / 企业树不符；``status`` 供路由转 400 / 404 / 409。"""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


def note_template_type(value: str | None) -> str:
    """项目模板类型 / 合并口径 ⇒ 合并附注模板（上市版 ⇒ listed，其余 ⇒ soe，与 ``consol_standard`` 同一判定）。"""
    text = (value or "").strip().lower()
    return "listed" if text in ("listed", "listed_consolidated") else "soe"


# ─────────────────────────────── 模板装载（mtime 缓存，只读） ───────────────────────────────

_JSON_CACHE: dict[Path, tuple[float, Any]] = {}


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    hit = _JSON_CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    data = json.loads(path.read_text(encoding="utf-8"))
    _JSON_CACHE[path] = (mtime, data)
    return data


def multi_header_to_column_groups(
    multi_header: list[list[str]] | None,
) -> list[dict] | None:
    """从 multi_header 推导 _column_groups（与单体附注模板同格式）。

    算法：第一行的非空连续区间 = 一个分组（空字符串表示被同组合并）。
    第一列（标签列）跳过。包含 span=1 的分组（与单体附注模板一致）。
    无 multi_header 或只有一行 ⇒ 返回 None。

    >>> multi_header_to_column_groups([
    ...     ["账  龄", "期末数", "", "期初数", ""],
    ...     ["", "账面余额", "坏账准备", "账面余额", "坏账准备"],
    ... ])
    [{'group': '期末数', 'start': 1, 'span': 2}, {'group': '期初数', 'start': 3, 'span': 2}]
    """
    if not multi_header or len(multi_header) < 2:
        return None
    row0 = multi_header[0]
    groups: list[dict] = []
    i = 1  # 跳过标签列（col 0）
    while i < len(row0):
        text = (row0[i] or "").strip()
        if text:
            span = 1
            while i + span < len(row0) and not (row0[i + span] or "").strip():
                span += 1
            groups.append({"group": text, "start": i, "span": span})
            i += span
        else:
            i += 1
    return groups if groups else None


_TOTAL_PATTERN = re.compile(r"^(合\s*计|小\s*计|合\s+计|小\s+计)$")
_SUBTOTAL_KEYWORDS = {"小  计", "小 计", "小计"}


def _infer_row_type(label: str) -> str:
    """从行首列文本推导 row_type（data/total/subtotal）。"""
    text = (label or "").strip()
    if not text:
        return "data"
    if _TOTAL_PATTERN.match(text):
        return "total"
    if text in _SUBTOTAL_KEYWORDS or text.startswith("小计"):
        return "subtotal"
    return "data"


def _ensure_columns(section: dict) -> None:
    """自动从 headers 生成 columns 列元数据（如果缺失）。"""
    if section.get("columns"):
        return
    headers = section.get("headers")
    if not isinstance(headers, list) or not headers:
        return
    cols = []
    for i, h in enumerate(headers):
        col: dict = {"key": h, "label": h}
        if i == 0:
            col["is_label"] = True
            col["flat"] = True
        cols.append(col)
    section["columns"] = cols


def _is_embedded_header_row(row: list, headers: list) -> bool:
    """检测 rows 中的一行是否是嵌入的子表头（而非数据行）。

    判据：row[0] 与 headers[0] 文字相同（去空白和 HTML 标签后），
    说明 rows 把 headers 列名重复了一遍作为子表头行。
    """
    if not isinstance(row, list) or not row or not headers:
        return False
    import re
    clean = lambda s: re.sub(r"<br\s*/?>", "", re.sub(r"[\s\u3000]+", "", str(s or "")))
    return clean(row[0]) == clean(headers[0]) and bool(clean(row[0]))


def _ensure_row_types(section: dict) -> None:
    """自动为 rows 中的每一行推导 _row_type（不改原数组结构，附加到 section）。

    CP-04 扩展：检测 rows 前几行是否是嵌入的子表头（合并附注模板的常见形态），
    标注为 ``header`` 类型，同时记录 ``_header_row_indexes`` 供前端分离渲染。
    """
    rows = section.get("rows")
    if not isinstance(rows, list) or not rows:
        return
    # 如果已有 _row_types 则不覆盖
    if section.get("_row_types"):
        return
    headers = section.get("headers", [])
    row_types = []
    header_row_indexes = []
    for i, row in enumerate(rows):
        if isinstance(row, list) and row:
            # 只检查前 3 行，且必须从第 0 行连续开始
            if i <= 2 and i == len(header_row_indexes) and _is_embedded_header_row(row, headers):
                row_types.append("header")
                header_row_indexes.append(i)
            else:
                row_types.append(_infer_row_type(str(row[0])))
        else:
            row_types.append("data")
    section["_row_types"] = row_types
    if header_row_indexes:
        section["_header_row_indexes"] = header_row_indexes


def _safe_float(val: Any) -> float | None:
    """安全转 float，空串/非数字返 None。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "").replace("，", "")
    if not s:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def backfill_total_rows(
    rows: list[list],
    row_types: list[str] | None = None,
) -> bool:
    """对合计行（total/subtotal）自动按同列数据行求和回填。

    row_types 与 rows 等长，标识每行类型。未提供时从行首列文本推导。
    返回是否有值被回填。

    算法：遇到 total/subtotal 行时，向上搜索该行之前的连续 data 行（遇到
    上一个 total/subtotal 停止），对每列求和写入合计行。
    只回填空值（空串或 None），已有值的单元格不覆盖。
    """
    if not rows:
        return False
    if not row_types:
        row_types = [_infer_row_type(str(r[0]) if r else "") for r in rows]

    changed = False
    for ri, rtype in enumerate(row_types):
        if rtype not in ("total", "subtotal"):
            continue
        row = rows[ri]
        # 向上收集数据行范围（从 ri-1 向上到上一个 total/subtotal 或行首）
        data_start = ri
        for j in range(ri - 1, -1, -1):
            if row_types[j] in ("total", "subtotal"):
                break
            data_start = j

        # 对每个数值列（跳过首列标签）求和
        num_cols = len(row)
        for ci in range(1, num_cols):
            # 只回填空值单元格
            existing = row[ci] if ci < len(row) else ""
            if _safe_float(existing) is not None:
                continue  # 已有值，不覆盖
            col_sum = 0.0
            has_data = False
            for j in range(data_start, ri):
                if j >= len(rows):
                    break
                dr = rows[j]
                if ci >= len(dr):
                    continue
                v = _safe_float(dr[ci])
                if v is not None:
                    col_sum += v
                    has_data = True
            if has_data:
                # 写入合计值（格式化为字符串，与模板格式一致）
                while len(row) <= ci:
                    row.append("")
                row[ci] = str(col_sum) if col_sum != int(col_sum) else str(int(col_sum))
                changed = True

    return changed


def consol_note_tables(template_type: str) -> list[dict]:
    """合并附注表格模板（``consol_note_sections_{tt}.json``，一项一张表）。调用方不得修改返回值。"""
    data = _load_json(DATA_DIR / f"consol_note_sections_{template_type}.json")
    sections = data if isinstance(data, list) else []
    for section in sections:
        if not isinstance(section, dict):
            continue
        # 自动补齐 _column_groups
        if not section.get("_column_groups"):
            mh = section.get("multi_header")
            if mh:
                groups = multi_header_to_column_groups(mh)
                if groups:
                    section["_column_groups"] = groups
        # 自动补齐 columns 列元数据
        _ensure_columns(section)
        # 自动推导 _row_types
        _ensure_row_types(section)
    return sections


def single_note_sections(template_type: str) -> list[dict]:
    """单体附注模板章节（``note_template_{tt}.json``，表行带 ``account_codes``）。"""
    data = _load_json(DATA_DIR / f"note_template_{template_type}.json")
    return data.get("sections", []) if isinstance(data, dict) else []


def find_table(template_type: str, section_id: str) -> dict | None:
    return next((t for t in consol_note_tables(template_type) if t.get("section_id") == section_id), None)


# ─────────────────────────────── 规范化 ───────────────────────────────

_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_WS = re.compile(r"[\s\u3000]+")


def header_key(value: Any) -> str:
    return _WS.sub("", _BR.sub("", str(value or "")))


def label_key(value: Any) -> str:
    """行标签比较键：与报表行名同一规范化（去空白、行首序号与 △ * 减： 其中：… 标记）。"""
    return row_name_key(value)


def _first_cell(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("label") or row.get("name") or "")
    if isinstance(row, (list, tuple)) and row:
        return str(row[0] or "")
    return ""


# ─────────────────────────────── 种子规划（纯函数） ───────────────────────────────


@dataclass(frozen=True)
class SeedCell:
    section_id: str
    row_index: int
    col_index: int
    formula: str
    kind: str
    description: str


@dataclass
class SeedPlan:
    template_type: str
    cells: list[SeedCell] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)   # {section_id, parent_section, reason}

    def count(self, kind: str) -> int:
        return sum(1 for c in self.cells if c.kind == kind)

    def tables(self, kind: str) -> int:
        return len({c.section_id for c in self.cells if c.kind == kind})


def report_rows_by_name(rows: Iterable[ReportRow]) -> tuple[dict[str, ReportRow], dict[str, str]]:
    """资产负债表 / 利润表有公式的行按行名分组：唯一（同名各行公式相同）⇒ 取第一行；公式不同 ⇒ 不确定并给原因。"""
    groups: dict[str, list[ReportRow]] = {}
    for row in rows:
        text = (row.formula or "").strip()
        if row.report_type not in SEED_REPORT_TYPES or not text or analyze_formula(text).error:
            continue
        groups.setdefault(label_key(row.row_name), []).append(row)
    unique: dict[str, ReportRow] = {}
    ambiguous: dict[str, str] = {}
    for key, members in groups.items():
        if not key:
            continue
        if len({canonical_formula(r.formula) for r in members}) == 1:
            unique[key] = members[0]
        else:
            ambiguous[key] = "、".join(f"{r.row_code}={canonical_formula(r.formula)}" for r in members)
    return unique, ambiguous


def value_column(
    headers: Sequence[Any],
    report_type: str,
    column_groups: Sequence[dict] | None = None,
) -> tuple[int | None, str | None]:
    """取数列：资产负债表项目取唯一期末列，利润表项目取唯一本期列。

    优先按 ``_column_groups`` 分组名定位（与单体附注同结构），
    降级到 ``headers`` 关键词匹配。多级表头有 ``_column_groups`` 后不再因空列名拒绝。
    """
    what = "期末" if report_type == "balance_sheet" else "本期"
    wanted_groups = CLOSING_HEADERS if report_type == "balance_sheet" else PERIOD_HEADERS

    # ── 路径 A：按 _column_groups 定位 ──
    if column_groups:
        hits = [g for g in column_groups if header_key(g.get("group", "")) in wanted_groups]
        if len(hits) == 1:
            return hits[0]["start"], None
        if len(hits) > 1:
            return None, f"_column_groups 中{what}分组不止一个"
        # 无命中 ⇒ 降级到路径 B

    # ── 路径 B：按 headers 关键词匹配 ──
    keys = [header_key(h) for h in headers]
    if any(not k for k in keys[1:]):
        return None, "表头有空列名（多级表头未展开），列不确定"
    hits_idx = [i for i, k in enumerate(keys) if i and k in wanted_groups]
    if not hits_idx:
        return None, f"没有{what}列（表头：{'、'.join(keys[1:])}）"
    if len(hits_idx) > 1:
        return None, f"{what}列不止一个"
    return hits_idx[0], None


def total_row(rows: Sequence[Any]) -> tuple[int | None, str | None]:
    hits = [i for i, r in enumerate(rows) if label_key(_first_cell(r)) in TOTAL_LABELS]
    if not hits:
        return None, "没有合计行"
    if len(hits) > 1:
        return None, "合计行不止一个"
    return hits[0], None


def _single_table(chapter_key: str, title: str, chapter_size: int, single: Sequence[dict]) -> dict | None:
    """单体附注模板里对应的表：章节名（或科目名）相同、表名相同；两边都只有一张表时不要求表名相同。"""
    for sec in single:
        if chapter_key not in {label_key(sec.get("section_title")), label_key(sec.get("account_name"))}:
            continue
        tables = sec.get("tables") or []
        named = [t for t in tables if label_key(t.get("name")) == label_key(title)]
        if named:
            return named[0]
        if len(tables) == 1 and chapter_size == 1:
            return tables[0]
    return None


def _term_formula(parts: list[tuple[Decimal, str, str]]) -> str:
    out = ""
    for coef, code, column in parts:
        call = f"TB('{code}','{column}')"
        if coef > 0:
            out += call if not out else f" + {call}"
        else:
            out += f"-{call}" if not out else f" - {call}"
    return out


def _codes_formula(codes: Sequence[str], terms: dict[tuple, Decimal]) -> tuple[str | None, str | None]:
    """表行科目 ⇒ 按报表行公式的系数与取数列取数；每个科目须恰落在报表行一个取数项里且系数为 ±1。"""
    parts: list[tuple[Decimal, str, str]] = []
    for code in codes:
        code = str(code or "").strip()
        hits = [(t, c) for t, c in terms.items() if term_matches(t, code)]
        if len(hits) != 1:
            return None, f"科目 {code} 不在该章报表行的取数范围内" if not hits else f"科目 {code} 落在报表行多个取数项里"
        term, coef = hits[0]
        if abs(coef) != 1:
            return None, f"科目 {code} 在报表行公式里的系数是 {coef}"
        parts.append((coef, code, term[-1]))   # 取数项末位即取数列（tb / sum_tb 同形）
    return (_term_formula(parts), None) if parts else (None, "没有科目")


def plan_seed(
    template_type: str,
    tables: Sequence[dict],
    single: Sequence[dict],
    report_rows: Sequence[ReportRow],
) -> SeedPlan:
    """两类种子公式（纯函数，design §7.1 + 本任务的可确定性约束）。同一单元格两类都中 ⇒ 取第一类。"""
    plan = SeedPlan(template_type)
    lines, ambiguous = report_rows_by_name(report_rows)
    terms_of = row_account_terms(report_rows)
    chapters: dict[str, list[dict]] = {}
    for t in tables:
        chapters.setdefault(t.get("parent_section") or "", []).append(t)
    taken: set[tuple[str, int, int]] = set()

    def skip(table: dict, reason: str) -> None:
        plan.skipped.append({"section_id": table.get("section_id"), "parent_section": table.get("parent_section"),
                             "title": table.get("title"), "reason": reason})

    def add(cell: SeedCell) -> None:
        key = (cell.section_id, cell.row_index, cell.col_index)
        if key not in taken:
            taken.add(key)
            plan.cells.append(cell)

    for chapter, members in chapters.items():
        key = label_key(chapter)
        row = lines.get(key)
        if row is None:
            if key in ambiguous:
                skip(members[0], f"同名报表行公式不一致（{ambiguous[key]}），不确定取哪一行")
            continue
        # (a) 主表（该章第一张表）合计行 ⇒ 报表行
        main = members[0]
        col, why_col = value_column(main.get("headers") or [], row.report_type, main.get("_column_groups"))
        total, why_total = total_row(main.get("rows") or [])
        if col is None or total is None:
            skip(main, why_col or why_total or "")
        else:
            add(SeedCell(main["section_id"], total, col, f"REPORT('{row.row_code}')", KIND_REPORT_TOTAL,
                         f"自动种子：「{chapter}」合计 = 合并报表 {row.row_code}「{row.row_name}」"))
        # (b) 表行对上单体模板行的科目码，且科目都是本章报表行的取数项（按报表公式系数）
        terms = terms_of.get(row.row_code)
        if not terms:
            continue
        for table in members:
            source = _single_table(key, table.get("title") or "", len(members), single)
            if source is None:
                continue
            codes_of = {label_key(r.get("label")): r.get("account_codes") or []
                        for r in source.get("rows") or [] if isinstance(r, dict)}
            col, why_col = value_column(table.get("headers") or [], row.report_type, table.get("_column_groups"))
            for i, cells in enumerate(table.get("rows") or []):
                codes = codes_of.get(label_key(_first_cell(cells)))
                if not codes:
                    continue
                if col is None:
                    skip(table, why_col or "")
                    break
                formula, why = _codes_formula(codes, terms)
                if formula is None:
                    skip(table, f"「{_first_cell(cells).strip()}」{why}")
                    continue
                add(SeedCell(table["section_id"], i, col, formula, KIND_ACCOUNT_CODES,
                             f"自动种子：「{_first_cell(cells).strip()}」= 科目 {'、'.join(codes)}"
                             f"（按合并报表 {row.row_code} 的取数口径）"))
    return plan


# ─────────────────────────────── 种子落库（幂等） ───────────────────────────────


@dataclass
class SeedResult:
    template_type: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    kept_manual: int = 0
    suppressed: int = 0            # 人工删过的单元格：不再补回
    skipped: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in (
            "template_type", "created", "updated", "unchanged", "removed", "kept_manual", "suppressed", "skipped")}


async def _advisory(db: AsyncSession, key: str) -> None:
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key})


def _check_template(template_type: str) -> str:
    if template_type not in NOTE_TEMPLATE_TYPES:
        raise NoteFormulaError(f"模板类型只能是 {'/'.join(NOTE_TEMPLATE_TYPES)}，收到 {template_type!r}")
    return template_type


async def seed_note_formulas(
    db: AsyncSession, template_type: str, *, report_rows: Sequence[ReportRow] | None = None,
) -> SeedResult:
    """两类种子公式落库（只 flush）：新建 / 按规则更新 ``source='seed'``；人工公式不动；
    人工删过（该单元格有已删记录）的不补回；本次规则不再产出的种子行删除（种子是派生数据，不留软删记录，
    所以「已删记录」恒为人工删除）。"""
    tt = _check_template(template_type)
    if report_rows is None:
        report_rows = await load_report_rows(db, f"{tt}_consolidated")
    plan = plan_seed(tt, consol_note_tables(tt), single_note_sections(tt), report_rows)
    await _advisory(db, f"consol_note_seed:{tt}")
    existing = (await db.execute(
        sa.select(ConsolNoteFormula).where(ConsolNoteFormula.template_type == tt)
    )).scalars().all()
    active = {(f.section_id, f.row_index, f.col_index): f for f in existing if not f.is_deleted}
    deleted = {(f.section_id, f.row_index, f.col_index) for f in existing if f.is_deleted}
    result = SeedResult(tt, skipped=plan.skipped)
    now = datetime.now(timezone.utc)  # 显式时间：服务端默认值 flush 后读取会在异步会话里懒加载
    planned = {(c.section_id, c.row_index, c.col_index): c for c in plan.cells}
    for key, cell in planned.items():
        row = active.get(key)
        if row is None:
            if key in deleted:
                result.suppressed += 1
                continue
            db.add(ConsolNoteFormula(
                template_type=tt, section_id=cell.section_id, row_index=cell.row_index, col_index=cell.col_index,
                formula=cell.formula, source="seed", description=cell.description, created_at=now, updated_at=now,
            ))
            result.created += 1
        elif row.source != "seed":
            result.kept_manual += 1
        elif (row.formula, row.description) != (cell.formula, cell.description):
            row.formula, row.description, row.updated_at = cell.formula, cell.description, now
            result.updated += 1
        else:
            result.unchanged += 1
    for key, row in active.items():
        if row.source == "seed" and key not in planned:
            await db.delete(row)
            result.removed += 1
    await db.flush()
    return result


_SEEDED: dict[str, tuple] = {}


def _seed_signature(template_type: str, rows: Sequence[ReportRow]) -> tuple:
    files = (DATA_DIR / f"consol_note_sections_{template_type}.json", DATA_DIR / f"note_template_{template_type}.json")
    mtimes = tuple(p.stat().st_mtime if p.exists() else 0 for p in files)
    return mtimes, hash(tuple((r.report_type, r.row_code, r.row_name, r.formula) for r in rows))


async def ensure_seeded(db: AsyncSession, template_type: str) -> SeedResult | None:
    """按需种子化（读公式 / 求值前调用，只 flush，调用方提交）：模板文件与合并口径报表配置都没变、
    且库里已有该模板的记录 ⇒ 跳过。种子写在 SAVEPOINT 里：并发撞唯一索引只回滚这一段，不毒化调用方事务。"""
    tt = _check_template(template_type)
    rows = await load_report_rows(db, f"{tt}_consolidated")
    signature = _seed_signature(tt, rows)
    # 库里有任何记录（含人工删除的）⇒ 已种子化过；本进程用同一签名跑过 ⇒ 规则产出不变
    has_rows = (await db.execute(sa.select(ConsolNoteFormula.id).where(
        ConsolNoteFormula.template_type == tt,
    ).limit(1))).first() is not None
    if has_rows and _SEEDED.get(tt) == signature:
        return None
    try:
        async with db.begin_nested():
            result = await seed_note_formulas(db, tt, report_rows=rows)
    except IntegrityError:
        return None   # 另一请求同时在种子化：它会写入，下一次读再核对
    _SEEDED[tt] = signature
    return result


# ─────────────────────────────── 公式增删改 ───────────────────────────────


def formula_to_dict(f: ConsolNoteFormula, table: dict | None = None) -> dict:
    headers = (table or {}).get("headers") or []
    rows = (table or {}).get("rows") or []
    col_name = header_key(headers[f.col_index]) if 0 <= f.col_index < len(headers) else f"第 {f.col_index} 列"
    row_label = _first_cell(rows[f.row_index]).strip() if 0 <= f.row_index < len(rows) else ""
    return {
        "id": str(f.id),
        "template_type": f.template_type,
        "section_id": f.section_id,
        "row_index": f.row_index,
        "col_index": f.col_index,
        "row_label": row_label or None,
        "col_name": col_name,
        "position": f"第 {f.row_index + 1} 行 · {col_name}" + (f"（{row_label}）" if row_label else ""),
        "formula": f.formula,
        "source": f.source,
        "source_label": SOURCE_LABELS.get(f.source, f.source),
        "description": f.description,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        "updated_by": str(f.updated_by) if f.updated_by else None,
    }


def validate_note_formula(formula: str) -> str:
    """附注公式按合并报表口径检查：能求值（取数函数、行引用形态）⇒ 去首尾空白的原文；否则 ``NoteFormulaError``。
    存原文（求值时由 ``analyze_formula`` 规范化）；行引用是否存在、取数列是否在口径内要在求值时才知道
    （依赖报表配置与本树科目），那里逐单元格给原因。"""
    text = (formula or "").strip()
    if not text:
        raise NoteFormulaError("公式不能为空")
    if len(text) > 2000:
        raise NoteFormulaError("公式过长（上限 2000 字符）")
    shape = analyze_formula(text)
    if shape.error:
        raise NoteFormulaError(f"公式不能在合并口径求值：{shape.error}")
    return text


def _check_cell(template_type: str, section_id: str, row_index: int, col_index: int) -> dict:
    table = find_table(template_type, section_id)
    if table is None:
        raise NoteFormulaError(f"合并附注模板（{template_type}）中没有表格 {section_id}", status=404)
    width = len(table.get("headers") or [])
    if not 1 <= col_index < width:
        raise NoteFormulaError(f"列号 {col_index} 超出表格范围（第 1~{width - 1} 列；第 0 列是项目名）")
    if not 0 <= row_index <= MAX_ROW_INDEX:
        raise NoteFormulaError(f"行号须在 0~{MAX_ROW_INDEX} 之间")
    return table


async def list_note_formulas(db: AsyncSession, template_type: str, section_id: str | None = None) -> dict:
    tt = _check_template(template_type)
    await ensure_seeded(db, tt)
    stmt = sa.select(ConsolNoteFormula).where(
        ConsolNoteFormula.template_type == tt, ConsolNoteFormula.is_deleted == sa.false(),
    )
    if section_id:
        stmt = stmt.where(ConsolNoteFormula.section_id == section_id)
    formulas = (await db.execute(stmt)).scalars().all()
    tables = {t.get("section_id"): t for t in consol_note_tables(tt)}
    order = {sid: i for i, sid in enumerate(tables)}
    formulas = sorted(formulas, key=lambda f: (order.get(f.section_id, len(order)), f.section_id, f.row_index, f.col_index))
    by_section: dict[str, list[dict]] = {}
    for f in formulas:
        by_section.setdefault(f.section_id, []).append(formula_to_dict(f, tables.get(f.section_id)))
    sections = [
        {
            "section_id": sid,
            "title": (tables.get(sid) or {}).get("title"),
            "parent_section": (tables.get(sid) or {}).get("parent_section"),
            "formulas": items,
        }
        for sid, items in by_section.items()
    ]
    return {"template_type": tt, "count": len(formulas), "sections": sections}


async def create_note_formula(
    db: AsyncSession, *, template_type: str, section_id: str, row_index: int, col_index: int,
    formula: str, description: str | None, user_id: UUID | None,
) -> ConsolNoteFormula:
    tt = _check_template(template_type)
    _check_cell(tt, section_id, row_index, col_index)
    text = validate_note_formula(formula)
    dup = (await db.execute(sa.select(ConsolNoteFormula.id).where(
        ConsolNoteFormula.template_type == tt, ConsolNoteFormula.section_id == section_id,
        ConsolNoteFormula.row_index == row_index, ConsolNoteFormula.col_index == col_index,
        ConsolNoteFormula.is_deleted == sa.false(),
    ))).first()
    if dup is not None:
        raise NoteFormulaError("该单元格已有公式，请直接修改", status=409)
    now = datetime.now(timezone.utc)  # 显式给时间：服务端默认值 flush 后是过期属性，异步会话里读它会触发懒加载
    row = ConsolNoteFormula(
        template_type=tt, section_id=section_id, row_index=row_index, col_index=col_index, formula=text,
        source="manual", description=(description or "").strip() or None, updated_by=user_id,
        created_at=now, updated_at=now,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise NoteFormulaError("该单元格已有公式，请刷新后修改", status=409) from exc
    return row


async def _get_formula(db: AsyncSession, formula_id: UUID) -> ConsolNoteFormula:
    row = await db.get(ConsolNoteFormula, formula_id)
    if row is None or row.is_deleted:
        raise NoteFormulaError("公式不存在", status=404)
    return row


async def update_note_formula(
    db: AsyncSession, formula_id: UUID, *, formula: str | None, description: str | None, user_id: UUID | None,
) -> ConsolNoteFormula:
    """改公式 ⇒ 来源变为人工（之后种子不再覆盖）。只改说明不改来源。"""
    row = await _get_formula(db, formula_id)
    if formula is not None:
        text = validate_note_formula(formula)
        if canonical_formula(text) != canonical_formula(row.formula):   # 只差空白 ⇒ 不算改
            row.formula = text
            row.source = "manual"
    if description is not None:
        row.description = description.strip() or None
    row.updated_by = user_id
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return row


async def delete_note_formula(db: AsyncSession, formula_id: UUID, *, user_id: UUID | None) -> ConsolNoteFormula:
    """软删（保留记录 ⇒ 种子不再补回该单元格，design「不覆盖人工」）。"""
    row = await _get_formula(db, formula_id)
    row.is_deleted = True
    row.updated_by = user_id
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return row


# ─────────────────────────────── 求值：附注差额（四度量 + 子节点贡献） ───────────────────────────────

NOTE_MEASURES: tuple[tuple[str, str], ...] = (
    (MEASURE_INDIVIDUAL, "个别数汇总"),
    (MEASURE_ADJUSTMENT, "调整"),
    ("elimination", "抵销"),
    (MEASURE_CONSOLIDATED, "合并数"),
)


def _cell_code(row_index: int, col_index: int) -> str:
    # 「~」排在全部报表行次之后：SUM_ROW('BS-001','BS-999') 这类区间不会把附注伪行算进去
    return f"~N:{row_index}:{col_index}"


def note_rows(formulas: Sequence[Any]) -> list[ReportRow]:
    """附注单元格 ⇒ 伪报表行（类型不在报表求值顺序里 ⇒ 排在全部报表行之后，``REPORT()`` 取到同一次求值的行值）。"""
    return [
        ReportRow(NOTE_ROW_TYPE, _cell_code(f.row_index, f.col_index), "", f.row_index * 1000 + f.col_index, f.formula)
        for f in formulas
    ]


def _amount(value: RowValue | None) -> str | None:
    return None if value is None or value.amount is None else str(value.amount)


async def note_cell_values(
    report_rows: Sequence[ReportRow],
    formulas: Sequence[Any],
    node_measure_values: dict[str, dict[str, Decimal]],
    *,
    categories: dict | None = None,
    children: Sequence[tuple[str, dict[str, Decimal]]] = (),
) -> list[dict]:
    """附注单元格四度量（纯求值，design §7.2）。抵销 = 权益抵销 + 往来交易抵销（两项都有值时才相加）。

    ``children``：直接子节点 (node_key, 合并数度量)；线性公式各子节点之和 = 该单元格合并数（同报表差额表 P4）。
    """
    rows = [*report_rows, *note_rows(formulas)]
    by_measure = await node_report(rows, node_measure_values, categories=categories)
    per_child = [
        (key, await report_values(rows, values, categories=categories, require_linear=True))
        for key, values in children
    ]
    out = []
    for f in formulas:
        code = _cell_code(f.row_index, f.col_index)
        cells = {m: by_measure[m][code] for m in by_measure}
        eq, tr = cells[MEASURE_ELIM_EQUITY], cells[MEASURE_ELIM_TRADE]
        elimination = None if eq.amount is None or tr.amount is None else to_cents(eq.amount + tr.amount)
        reasons = list(dict.fromkeys(v.reason for v in cells.values() if v.reason))
        out.append({
            "row_index": f.row_index,
            "col_index": f.col_index,
            "formula": f.formula,
            "source": getattr(f, "source", None),
            MEASURE_INDIVIDUAL: _amount(cells[MEASURE_INDIVIDUAL]),
            MEASURE_ADJUSTMENT: _amount(cells[MEASURE_ADJUSTMENT]),
            MEASURE_ELIM_EQUITY: _amount(eq),
            MEASURE_ELIM_TRADE: _amount(tr),
            "elimination": None if elimination is None else str(elimination),
            MEASURE_CONSOLIDATED: _amount(cells[MEASURE_CONSOLIDATED]),
            "linear": cells[MEASURE_CONSOLIDATED].linear,
            "note": "；".join(reasons) or None,
            "children": {key: _amount(values.get(code)) for key, values in per_child},
        })
    return out


async def resolve_note_template_type(
    db: AsyncSession, project_id: UUID, requested: str | None = None,
) -> str:
    """解析项目实际合并附注模板，并拒绝显式口径冲突。"""
    from app.services.consol_report_values import resolve_consol_standard

    actual = note_template_type(await resolve_consol_standard(db, project_id))
    if requested and note_template_type(requested) != actual:
        label = "上市版" if actual == "listed" else "国企版"
        raise NoteFormulaError(
            f"本项目合并附注按{label}模板（{actual}），不能按 {requested} 取数"
        )
    return actual


async def _project_template(db: AsyncSession, project_id: UUID, standard: str | None) -> str:
    """附注模板随项目口径；保留内部旧名称供现有调用方使用。"""
    return await resolve_note_template_type(db, project_id, standard)


async def _active_formulas(db: AsyncSession, template_type: str, section_id: str) -> list[ConsolNoteFormula]:
    return list((await db.execute(sa.select(ConsolNoteFormula).where(
        ConsolNoteFormula.template_type == template_type,
        ConsolNoteFormula.section_id == section_id,
        ConsolNoteFormula.is_deleted == sa.false(),
    ).order_by(ConsolNoteFormula.row_index, ConsolNoteFormula.col_index))).scalars().all())


async def _context(
    db: AsyncSession,
    project_id: UUID,
    year: int | None,
    *,
    context: "ConsolContext | None" = None,
    tree: "TreeNode | None" = None,
):
    from app.services.consol_context_service import validate_context
    from app.services.consol_report_view_service import load_view_context

    if context is not None:
        if year is None:
            year = context.year
        validate_context(context, project_id, year, tree=tree)
    ctx = await load_view_context(
        db,
        project_id,
        year,
        context=context,
        tree=tree,
    )
    if ctx is None:
        raise NoteFormulaError("只有合并报表项目有合并附注差额（项目不存在、不是合并项目或没有审计年度）", status=404)
    return ctx


async def _note_data_record(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
    *,
    node_key: str | None,
    is_root_consol: bool,
) -> ConsolNoteData | None:
    """按节点读取附注行；legacy NULL 回退只允许已验证的树根合并节点。"""
    target = (
        ConsolNoteData.node_key.is_(None)
        if node_key is None
        else ConsolNoteData.node_key == node_key
    )
    record = (await db.execute(sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == project_id,
        ConsolNoteData.year == year,
        ConsolNoteData.section_id == section_id,
        target,
    ))).scalar_one_or_none()
    if record is not None or not node_key or not is_root_consol:
        return record

    return (await db.execute(sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == project_id,
        ConsolNoteData.year == year,
        ConsolNoteData.section_id == section_id,
        ConsolNoteData.node_key.is_(None),
    ))).scalar_one_or_none()


async def _note_data_record_exact(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
    *,
    node_key: str | None,
) -> ConsolNoteData | None:
    """读取写入目标行，不允许根节点把 legacy 行当成节点行。"""
    target = ConsolNoteData.node_key.is_(None) if node_key is None else ConsolNoteData.node_key == node_key
    return (await db.execute(sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == project_id,
        ConsolNoteData.year == year,
        ConsolNoteData.section_id == section_id,
        target,
    ))).scalar_one_or_none()


async def _copy_note_data_record(
    db: AsyncSession,
    source: ConsolNoteData,
    *,
    project_id: UUID,
    year: int,
    section_id: str,
    node_key: str,
) -> ConsolNoteData:
    """把根节点 legacy 数据复制为节点专属行，避免填入覆盖项目级兼容行。"""
    record = ConsolNoteData(
        project_id=project_id,
        year=year,
        section_id=section_id,
        node_key=node_key,
        data=copy.deepcopy(source.data) if isinstance(source.data, dict) else {},
        is_stale=bool(source.is_stale),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.flush()
    return record


async def note_breakdown(
    db: AsyncSession, project_id: UUID, year: int | None, section_id: str, *,
    node_key: str | None = None, standard: str | None = None,
    _include_internal_scope: bool = False,
    _view_context: "ViewContext | None" = None,
    context: "ConsolContext | None" = None,
    tree: "TreeNode | None" = None,
) -> dict:
    """某章节有公式的单元格：个别数汇总 / 调整 / 抵销 / 合并数，及所选汇总节点各直接子节点的贡献（需求 6.3）。

    ``_view_context``: 预构建的合并计算上下文（批量场景传入避免逐章节重建树）。
    """
    from app.services.consol_report_view_service import ViewError, find_node

    tt = await _project_template(db, project_id, standard)
    table = find_table(tt, section_id)
    if table is None:
        raise NoteFormulaError(f"合并附注模板（{tt}）中没有表格 {section_id}", status=404)
    await ensure_seeded(db, tt)
    ctx = (
        _view_context
        if _view_context is not None
        else await _context(db, project_id, year, context=context, tree=tree)
    )
    try:
        node = find_node(ctx.basis.tree, node_key)
    except ViewError as exc:
        raise NoteFormulaError(str(exc), status=exc.status) from exc
    measures = node_measures(ctx.basis)
    children = [
        (c.node_key, measures[c.node_key][MEASURE_CONSOLIDATED]) for c in node.children
    ] if node.kind == KIND_AGGREGATE else []
    formulas = await _active_formulas(db, tt, section_id)
    cells = await note_cell_values(
        ctx.rows, formulas, measures[node.node_key], categories=ctx.basis.categories, children=children,
    )
    headers = table.get("headers") or []
    rows = table.get("rows") or []
    for cell in cells:
        r, c = cell["row_index"], cell["col_index"]
        cell["row_label"] = _first_cell(rows[r]).strip() if r < len(rows) else None
        cell["col_name"] = header_key(headers[c]) if c < len(headers) else None
    labels = {n.node_key: n.display_name or n.company_name for n in iter_nodes(ctx.basis.tree)}
    is_root_consol = node is ctx.basis.tree and node.role == "consol"
    result = {
        "project_id": str(project_id),
        "year": ctx.year,
        "template_type": tt,
        "section_id": section_id,
        "title": table.get("title"),
        "parent_section": table.get("parent_section"),
        "node_key": node.node_key,
        "node_label": labels.get(node.node_key),
        "columns": [{"key": k, "label": label} for k, label in NOTE_MEASURES],
        "children": [{"node_key": c.node_key, "label": labels.get(c.node_key), "kind": c.kind} for c in node.children]
        if children else [],
        "cells": cells,
    }
    if _include_internal_scope:
        result["_is_root_consol"] = is_root_consol
    return result


# ─────────────────────────────── 按公式填入 ───────────────────────────────


def _manual_cells(data: dict) -> set[tuple[int, int]]:
    """解析人工保护坐标；保护元数据损坏时必须让调用方可观察。"""
    raw = data.get("manual_cells")
    if raw is None:
        return set()
    if not isinstance(raw, list):
        raise NoteFormulaError("manual_cells 必须是数组")

    out: set[tuple[int, int]] = set()
    for index, item in enumerate(raw):
        try:
            if isinstance(item, dict):
                if "row" not in item or "col" not in item:
                    raise ValueError("缺少 row 或 col")
                row_value, col_value = item["row"], item["col"]
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                row_value, col_value = item
            elif isinstance(item, str) and item.count(":") == 1:
                row_value, col_value = item.split(":", 1)
            else:
                raise ValueError("应为 {row, col}、[row, col] 或 row:col")

            if isinstance(row_value, bool) or isinstance(col_value, bool):
                raise ValueError("行列坐标不能是布尔值")
            row, col = int(row_value), int(col_value)
            if row < 0 or col < 0:
                raise ValueError("行列坐标不能为负数")
        except (KeyError, TypeError, ValueError) as exc:
            raise NoteFormulaError(f"manual_cells 第 {index + 1} 项无效：{exc}") from exc
        out.add((row, col))
    return out


def _target_row(out: list[list[str]], template_rows: Sequence[Any], r: int) -> tuple[int | None, str | None]:
    """公式按模板行号登记；已保存数据可能插删过行 ⇒ 按项目名找行：同号同名优先，否则全表唯一同名行。"""
    want = label_key(_first_cell(template_rows[r])) if r < len(template_rows) else None
    if want is None:
        return (r, None) if r < len(out) else (None, f"模板没有第 {r + 1} 行")
    if r < len(out) and label_key(_first_cell(out[r])) == want:
        return r, None
    hits = [i for i, row in enumerate(out) if label_key(_first_cell(row)) == want]
    if len(hits) == 1:
        return hits[0], None
    name = _first_cell(template_rows[r]).strip() or f"第 {r + 1} 行"
    return None, f"已保存数据里找不到唯一的「{name}」行（插删过行），未填入" if not hits else \
        f"已保存数据里「{name}」行不止一个，未填入"


def _row_to_list(row: Any, width: int) -> list[str]:
    """把任意行形态转为定长 list[str]，用于公式填入的内部运算。"""
    if isinstance(row, (list, tuple)):
        cells = [str(v) if v is not None else "" for v in row]
    elif isinstance(row, dict):
        # 对象行按 values/cells dict 的 int 键或顺序值展开
        vals = row.get("values") or row.get("cells") or {}
        if isinstance(vals, dict):
            cells = [str(row.get("label") or "")]
            for i in range(1, width):
                cells.append(str(vals.get(str(i), vals.get(i, ""))))
        else:
            cells = [str(v) if v is not None else "" for v in (list(vals) if isinstance(vals, (list, tuple)) else [])]
    else:
        cells = []
    cells.extend([""] * (width - len(cells)))
    return cells[:width]


def _apply_to_dict_row(orig: dict, flat: list[str], width: int) -> dict:
    """把填入后的 flat list 写回对象行，保持对象行原始键结构。"""
    result = dict(orig)
    vals = orig.get("values") or orig.get("cells") or {}
    val_key = "values" if "values" in orig else "cells" if "cells" in orig else "values"
    if isinstance(vals, dict):
        result["label"] = flat[0] if flat else result.get("label", "")
        new_vals = dict(vals)
        for i in range(1, min(width, len(flat))):
            key = str(i) if str(i) in vals else i if i in vals else str(i)
            new_vals[key] = flat[i]
        result[val_key] = new_vals
    return result


def fill_rows(
    headers: Sequence[Any], rows: Sequence[Any], cells: Sequence[dict], manual: set[tuple[int, int]],
    template_rows: Sequence[Any],
) -> tuple[list, dict]:
    """把合并数写进行数据（纯函数，P10）：手工单元格不动；留空的公式不写（保留原值）并列出原因；
    行按项目名定位（``_target_row``），找不到不写。手工标记按已保存数据的实际行号。
    保持对象/二维数组原形状：若输入行是 dict，填入后还原为 dict。"""
    width = len(headers)
    is_dict_row = [isinstance(r, dict) for r in rows]
    out = [_row_to_list(r, width) for r in rows]
    filled, kept, blank = [], [], []
    for cell in cells:
        r, c = cell["row_index"], cell["col_index"]
        target, why = _target_row(out, template_rows, r)
        where = {"row_index": r, "col_index": c, "target_row": target}
        if target is None:
            blank.append({**where, "reason": why})
            continue
        if (target, c) in manual:
            kept.append({**where, "current": out[target][c], "formula_value": cell.get(MEASURE_CONSOLIDATED)})
            continue
        value = cell.get(MEASURE_CONSOLIDATED)
        if value is None:
            blank.append({**where, "reason": cell.get("note") or "取不到数"})
            continue
        if c >= width:
            blank.append({**where, "reason": f"已保存数据只有 {width} 列"})
            continue
        out[target][c] = value
        filled.append({**where, "value": value})
    # 还原对象行原始形状
    result_rows: list = []
    for i, flat in enumerate(out):
        if i < len(is_dict_row) and is_dict_row[i] and i < len(rows):
            result_rows.append(_apply_to_dict_row(rows[i], flat, width))  # type: ignore[arg-type]
        else:
            result_rows.append(flat)
    return result_rows, {
        "filled": filled,
        "kept_manual": kept,
        "kept_manual_count": len(kept),
        "blank": blank,
    }


async def fill_by_formula(
    db: AsyncSession, project_id: UUID, year: int, section_id: str, *,
    node_key: str | None = None, standard: str | None = None,
    template_type: str | None = None,
    _view_context: "ViewContext | None" = None,
    context: "ConsolContext | None" = None,
    tree: "TreeNode | None" = None,
) -> dict:
    """「按公式填入」：按节点把合并数写入 ``consol_note_data``；旧调用不带节点键时使用项目级兼容行。

    ``_view_context``: 预构建的合并计算上下文（批量场景传入避免逐章节重建树）。
    """
    if standard and template_type and note_template_type(standard) != note_template_type(template_type):
        raise NoteFormulaError(
            f"standard={standard} 与 template_type={template_type} 指向不同附注模板"
        )
    requested_template = template_type or standard
    breakdown = await note_breakdown(
        db, project_id, year, section_id, node_key=node_key, standard=requested_template,
        _include_internal_scope=True,
        _view_context=_view_context,
        context=context,
        tree=tree,
    )
    tt = breakdown["template_type"]
    is_root_consol = bool(breakdown.get("_is_root_consol")) and breakdown["node_key"] == node_key
    table = find_table(tt, section_id) or {}
    source_record = await _note_data_record(
        db, project_id, breakdown["year"], section_id, node_key=node_key,
        is_root_consol=is_root_consol,
    )
    record = source_record
    if node_key is not None:
        # 根节点允许从 legacy NULL 行读取，但写入时必须落到节点专属行。
        record = await _note_data_record_exact(
            db, project_id, breakdown["year"], section_id, node_key=node_key,
        )
        if record is None and source_record is not None and source_record.node_key is None:
            record = await _copy_note_data_record(
                db, source_record, project_id=project_id, year=breakdown["year"],
                section_id=section_id, node_key=node_key,
            )
    data = dict(record.data or {}) if record is not None and isinstance(record.data, dict) else {}
    headers = data.get("headers") or table.get("headers") or []
    rows = data.get("rows") if isinstance(data.get("rows"), list) and data.get("rows") else table.get("rows") or []
    # V182：locked 行整体跳过；locked_cells 合并进 manual 保护集合
    if record is not None and getattr(record, "cell_state", "auto") == "locked":
        return {
            "project_id": str(project_id),
            "year": breakdown["year"],
            "section_id": section_id,
            "node_key": getattr(record, "node_key", node_key),
            "legacy_null": getattr(record, "node_key", node_key) is None,
            "template_type": tt,
            "status": "skipped_locked",
            "record_id": str(record.id) if record.id else None,
            "reason": "整节被锁定（cell_state=locked），公式刷新不改写",
            "filled": [],
            "kept_manual": [],
            "kept_manual_count": 0,
            "blank": [],
            "is_stale": record.is_stale,
            "data": data,
        }
    manual_set = _manual_cells(data)
    # 把 locked_cells 列表中的坐标也加入保护集合
    if record is not None:
        for lc in getattr(record, "locked_cells", None) or []:
            if isinstance(lc, dict) and "row_index" in lc and "col_index" in lc:
                manual_set.add((int(lc["row_index"]), int(lc["col_index"])))
    new_rows, summary = fill_rows(headers, rows, breakdown["cells"], manual_set, table.get("rows") or [])
    data.update({"headers": headers, "rows": new_rows})
    now = datetime.now(timezone.utc)
    # V182：保存公式值快照（用于"当前值 vs 公式值"对比）
    formula_snapshot = {
        "cells": [
            {"row_index": c["row_index"], "col_index": c["col_index"], "value": c.get(MEASURE_CONSOLIDATED)}
            for c in breakdown.get("cells", [])
            if c.get(MEASURE_CONSOLIDATED) is not None
        ],
        "computed_at": now.isoformat(),
    }
    if record is None:
        record = ConsolNoteData(
            project_id=project_id, year=breakdown["year"], section_id=section_id,
            node_key=node_key, data=data, is_stale=False, updated_at=now,
            last_formula_value=formula_snapshot,
        )
        db.add(record)
    else:
        record.data = data
        record.is_stale = False
        record.updated_at = now
        record.last_formula_value = formula_snapshot
    await db.flush()
    return {
        "project_id": str(project_id),
        "year": breakdown["year"],
        "section_id": section_id,
        "node_key": record.node_key,
        "legacy_null": record.node_key is None,
        "template_type": tt,
        "status": "persisted",
        "record_id": str(record.id) if record.id else None,
        **summary,
        "is_stale": False,
        "data": data,
    }


async def fill_note_sections(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_ids: Sequence[str],
    *,
    node_key: str | None = None,
    standard: str | None = None,
    template_type: str | None = None,
    context: "ConsolContext | None" = None,
    tree: "TreeNode | None" = None,
    view_context: "ViewContext | None" = None,
) -> dict:
    """逐章节调用 ``fill_by_formula``，以 SAVEPOINT 隔离单章失败。

    该编排器只负责节点/章节结果和事务边界，金额计算与行形状处理仍全部由
    ``fill_by_formula`` 完成；调用方在拿到结果后统一 commit。
    """
    if standard and template_type and note_template_type(standard) != note_template_type(template_type):
        raise NoteFormulaError(
            f"standard={standard} 与 template_type={template_type} 指向不同附注模板"
        )
    requested_template = template_type or standard
    resolved_template = await resolve_note_template_type(db, project_id, requested_template)

    try:
        view_ctx = view_context
        if view_ctx is None:
            view_ctx = await _context(
                db,
                project_id,
                year,
                context=context,
                tree=tree,
            )
    except Exception:
        if context is not None or tree is not None:
            raise
        # 旧入口保留原有兼容语义：预构建失败时由每个章节自行解析。
        view_ctx = None

    results: list[dict] = []
    failures: list[dict] = []

    for section_id in dict.fromkeys(section_ids):
        try:
            async with db.begin_nested():
                result = await fill_by_formula(
                    db,
                    project_id,
                    year,
                    section_id,
                    node_key=node_key,
                    standard=resolved_template,
                    _view_context=view_ctx,
                    context=context,
                    tree=tree,
                )
            results.append(result)
        except Exception as exc:  # noqa: BLE001 - 单章节失败不能污染其余章节
            failures.append({
                "section_id": section_id,
                "status": "failed",
                "error": str(exc),
            })

    return {
        "project_id": str(project_id),
        "year": year,
        "node_key": node_key,
        "legacy_null": node_key is None,
        "template_type": resolved_template,
        "status": "persisted" if results and not failures else "failed" if failures else "skipped",
        "results": results,
        "failures": failures,
        "sections_processed": len(results) + len(failures),
        "sections_updated": len(results),
    }
