"""W6 业务对象 → 科目（advanced-query-linkage-closure design §3.12，ADR-AQL-20）。

业务页行级「按此查询明细」要把一个业务对象（底稿编码、报表行、附注章节）换成试算表 / 账簿的科目谓词。
这些换算只在这里实现一次，前端只传对象键（design §6「业务对象 → 科目」行）。三条解析各自的权威定义：

* 底稿编码 → 科目：``data/wp_account_mapping.json``（与循环映射同一文件，路径取 ``mapping_service._get_wp_mapping_path()``）。
* 报表行 → 科目：该行 ``financial_report.source_accounts``（报表生成时写下的取数科目），单码按前缀、``起~止`` 按 BETWEEN，
  与 ``ReportFormulaParser._get_tb_rows_prefix`` / ``_resolve_sum_tb`` 同口径。
* 附注章节 → 科目：章节 → 底稿编码 → 上面的 JSON。章节 → 底稿编码有两个来源，取并集：
  1. ``wp_account_mapping.json`` 自带的 ``note_section_soe`` / ``note_section_listed`` / ``note_section`` 字段（按章节编号匹配）；
  2. ``note_account_mappings`` 表（design 原定的唯一来源，按章节标题匹配 ``{准则}_standalone``）。
  **偏离设计并写明原因**：共享库现查 ``note_account_mappings`` **0 行**（``template_type`` 取值集合为空），只用它的话每个章节
  都会落到 ``NOTE_SECTION_NO_ACCOUNTS``，功能对任何真实项目都是死路；JSON 侧现查可解析 47 / 166 个章节（重药控股安徽 2025）。
  表仍保留在链路里：一旦被填充就自动生效（有回滚事务用例钉住这条支路真的接着）。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, NamedTuple

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.note_account_mapping import NoteAccountMapping
from app.models.report_models import DisclosureNote, FinancialReport
from app.services.custom_query.param_sql_builder import build_portable_filter

#: 一次解析最多回显的科目码（design §3.12：``meta.entry_accounts`` 排序后最多 50 个）
MAX_ENTRY_ACCOUNTS = 50
#: 章节 → 底稿编码时按准则取的字段。**刻意不用**同文件里的通用 ``note_section``：它现查在 96 个有值的行中有 80 行
#: 与两套准则字段都不一致（``D3`` 与 ``D6`` 的通用编号都写成「五、18」而两者的准则编号各不相同），属过时字段，
#: 用它会把章节解析到别的底稿上。两套准则字段之间现查无不一致冲突（同一编号在 soe / listed 下指向不同底稿的有 0 个）。
_SECTION_FIELD_BY_STANDARD = {"soe": "note_section_soe", "listed": "note_section_listed"}


class ReportRowNotGenerated(Exception):
    """本项目该年度没有生成这一报表行。"""


class ReportRowNoAccounts(Exception):
    """该报表行没有直接取数的科目（合计行、矩阵报表行等）。"""


class NoteSectionNotFound(Exception):
    """本项目该年度没有这个附注章节。"""


class NoteSectionNoAccounts(Exception):
    """该附注章节没有登记对应科目。"""


class NoteSectionAccounts(NamedTuple):
    title: str
    wp_codes: tuple[str, ...]
    codes: tuple[str, ...]


class _WpMappingIndex(NamedTuple):
    by_code: dict[str, tuple[str, ...]]
    #: (准则, 章节编号) → 底稿编码；准则分开存，避免一套准则的编号命中另一套的行
    sections: dict[tuple[str, str], tuple[str, ...]]


_CACHE: dict[Path, tuple[float, int, _WpMappingIndex]] = {}


def _mapping_path() -> Path:
    from app.services import mapping_service

    return Path(mapping_service._get_wp_mapping_path())


def _build_index(rows: list[dict[str, Any]]) -> _WpMappingIndex:
    by_code: dict[str, tuple[str, ...]] = {}
    sections: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        code = str(row.get("wp_code") or "").strip()
        if not code:
            continue
        codes = tuple(
            str(c).strip() for c in (row.get("account_codes") or []) if str(c).strip()
        )
        by_code[code] = codes
        for standard, field in _SECTION_FIELD_BY_STANDARD.items():
            section = str(row.get(field) or "").strip()
            if section:
                sections.setdefault((standard, section), set()).add(code)
    return _WpMappingIndex(by_code, {k: tuple(sorted(v)) for k, v in sections.items()})


def _index() -> _WpMappingIndex:
    """按文件 mtime + 大小缓存的底稿映射索引（映射表是人工维护的数据文件，改动后自动重读）。"""
    path = _mapping_path()
    stat = path.stat()
    cached = _CACHE.get(path)
    if cached is not None and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
        return cached[2]
    payload = json.loads(path.read_text(encoding="utf-8"))
    index = _build_index(payload.get("mappings") or [])
    _CACHE[path] = (stat.st_mtime, stat.st_size, index)
    return index


def codes_for_wp_code(wp_code: str) -> tuple[str, ...]:
    """底稿编码 → 标准科目码：编码精确匹配，没有登记该子编码时退到主编码（第一个「-」之前）。

    ``E1`` → 1001 / 1002 / 1012；``E1-2`` → 1001（自己有登记）；``E1-9`` → 退到 ``E1``；``A1`` → 空（沟通类底稿无科目）。
    """
    code = str(wp_code or "").strip()
    if not code:
        return ()
    by_code = _index().by_code
    if code in by_code:
        return by_code[code]
    main = code.split("-", 1)[0]
    return by_code.get(main, ())


def _standard(template_type: str) -> str:
    """只有 listed 与 soe 两套编号（与 ``ref_context`` 的 ``template_type`` 同口径）。"""
    return "listed" if template_type == "listed" else "soe"


def wp_codes_for_note_section(section: str, template_type: str) -> tuple[str, ...]:
    """附注章节编号 → 底稿编码（JSON 侧）：只按本准则的字段匹配。"""
    key = str(section or "").strip()
    if not key:
        return ()
    return _index().sections.get((_standard(template_type), key), ())


def _standard_variant(template_type: str) -> str:
    """``note_account_mappings.template_type`` 的取值（表里只有 standalone 变体；合并版无底稿映射）。"""
    return f"{_standard(template_type)}_standalone"


async def codes_for_note_section(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    section: str,
    template_type: str,
) -> NoteSectionAccounts:
    """附注章节 → 科目。章节不存在抛 :class:`NoteSectionNotFound`，解析不出科目抛 :class:`NoteSectionNoAccounts`。"""
    key = str(section or "").strip()
    title = (
        await db.execute(
            sa.select(DisclosureNote.section_title).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == int(year),
                DisclosureNote.note_section == key,
                DisclosureNote.is_deleted.is_(False),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if title is None:
        raise NoteSectionNotFound(key)

    wp_codes = set(wp_codes_for_note_section(key, template_type))
    mapped = (
        await db.execute(
            sa.select(NoteAccountMapping.wp_code).where(
                NoteAccountMapping.note_section_code == title,
                NoteAccountMapping.template_type == _standard_variant(template_type),
                NoteAccountMapping.wp_code.isnot(None),
            )
        )
    ).scalars().all()
    wp_codes.update(str(code).strip() for code in mapped if str(code or "").strip())

    codes: set[str] = set()
    for code in wp_codes:
        codes.update(codes_for_wp_code(code))
    if not codes:
        raise NoteSectionNoAccounts(key)
    return NoteSectionAccounts(str(title), tuple(sorted(wp_codes)), tuple(sorted(codes)))


def _source_account_predicate(column: ColumnElement, token: str) -> ColumnElement | None:
    """单个取数科目 → 谓词：``起~止`` 为区间（BETWEEN），否则按前缀。"""
    value = str(token or "").strip()
    if not value:
        return None
    if "~" in value:
        start, _, end = value.partition("~")
        start, end = start.strip(), end.strip()
        if not start or not end:
            return None
        return column.between(start, end)
    return build_portable_filter(column, "prefix", value, allow_internal=True)


async def report_row_predicate(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    year: int,
    report_type: str,
    row_code: str,
    column: ColumnElement,
) -> tuple[ColumnElement, dict[str, Any]]:
    """报表行 → 试算表科目谓词 + ``{codes, formula}``。

    行不存在抛 :class:`ReportRowNotGenerated`；``source_accounts`` 不是数组或为空抛 :class:`ReportRowNoAccounts`
    （JSONB 里的 JSON ``null`` 读出来就是 ``None``，合计行多数如此）。
    """
    row = (
        await db.execute(
            sa.select(FinancialReport.source_accounts, FinancialReport.formula_used).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == int(year),
                sa.cast(FinancialReport.report_type, sa.Text) == report_type,
                FinancialReport.row_code == str(row_code or "").strip(),
                FinancialReport.is_deleted.is_(False),
            ).limit(1)
        )
    ).first()
    if row is None:
        raise ReportRowNotGenerated(row_code)
    sources, formula = row[0], row[1]
    if not isinstance(sources, list) or not sources:
        raise ReportRowNoAccounts(row_code)

    clauses, codes = [], []
    for token in sources:
        clause = _source_account_predicate(column, token)
        if clause is None:
            continue
        clauses.append(clause)
        codes.append(str(token).strip())
    if not clauses:
        raise ReportRowNoAccounts(row_code)
    predicate = clauses[0] if len(clauses) == 1 else sa.or_(*clauses)
    return predicate, {"codes": codes, "formula": formula}
