"""报表行新鲜度判据与定义写入标过期（spec formula-hub-integrity-closure 任务 14 / 15；需求 5.1、5.5；ADR-FHIC-04；D13-A）。

报表行「是否过期」= 已标过期（``is_stale``），或计算版本不是当前版本（``calc_version IS DISTINCT FROM CALC_VERSION``），
或（只对逐行读者）生成时公式文本 ``formula_used`` 与当前生效公式规范化后不同。

- 汇总类读者（计数 / 列表）：:func:`stale_clause`（SQL 表达式，前两条）、:func:`count_summary`；
- 逐行读者（报表视图 / 导出）：:func:`is_effectively_stale` / :func:`row_status`（三条全含），生效公式由
  :func:`load_effective_formulas` 按 ``ReportConfigService.resolve_applicable_standard`` + ``load_effective_report_configs``
  取（与任务 15 定义写入出口标过期同口径）。
- 存量行 ``calc_version`` 为 NULL ⇒ 判过期，由用户逐项目重新生成（D13 选 A；不重新生成真实项目报表，X3）。
- 两种原因读者都展示：``calc_error``（计算失败、保留旧值时写，V229）与 ``blank_reason``（口径性留空，V173）。

读者清单由 ``tests/formula_hub/test_report_freshness_readers.py`` 冻结：读 ``financial_report.is_stale`` 一律经本模块，
不经本模块的原始读须在该清单登记理由。

写入侧（任务 15，需求 5.1 写入部分）：:func:`mark_changed` 由三个定义写入出口（报表域的 ``publish.publish_global`` /
``project_ops.save_overrides`` / ``project_ops.restore_global``）在各自事务内调用，把有效定义真正变化的行及经
``ROW`` / ``SUM_ROW`` 直接或间接引用它们的行标过期（该项目全部年度）；提交后 ``propagation.propagate_report`` 的重算与
事件不变。生成路径写 ``calc_version`` / ``calc_error`` 在 ``report_row_compute.write_row``（任务 16，ADR-FHIC-05）。
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReport
from app.services.formula_settings.definitions import normalize

#: 当前报表计算版本：生成路径成功写库时写入（任务 16）；判据或算法变化时 +1，旧版本算出的行一律判过期。
CALC_VERSION = 2

FormulaKey = tuple[str, str]


def _columns(source: Any = None) -> Any:
    """ORM 类（默认 ``FinancialReport``，可为 ``aliased``）或 Core 表 / 别名（取 ``.c``）。"""
    if source is None:
        return FinancialReport
    return source.c if hasattr(source, "c") else source


def stale_clause(source: Any = None) -> sa.ColumnElement[bool]:
    """汇总类读者的过期判据：``is_stale OR calc_version IS DISTINCT FROM CALC_VERSION``（NULL 判过期，D13-A）。

    ``source``：``FinancialReport``（默认）/ ``aliased(FinancialReport)`` / ``FinancialReport.__table__`` 或其别名。
    """
    cols = _columns(source)
    return sa.or_(cols.is_stale == sa.true(), cols.calc_version.is_distinct_from(CALC_VERSION))


def _get(row: Any, name: str) -> Any:
    return row.get(name) if isinstance(row, Mapping) else getattr(row, name, None)


def normalize_formula(text: str | None) -> str:
    """生成时公式与生效公式比较前的规范化：与公式设置报表域同口径（``definitions.normalize``；None ≡ 空串）。"""
    return normalize("report", {"formula": text})["formula"]


def is_marked_stale(row: Any) -> bool:
    """已标过期（``is_stale``）：stale 重算只选这类行（不因 D13-A 自动重算计算版本为空的存量行，ADR-FHIC-05 / X3）。"""
    return bool(_get(row, "is_stale"))


def is_flag_stale(row: Any, current_version: int = CALC_VERSION) -> bool:
    """:func:`stale_clause` 的逐行版：已标过期，或计算版本不是 ``current_version``（报表依赖缓存同此判据，任务 16）。"""
    return is_marked_stale(row) or _get(row, "calc_version") != current_version


def is_effectively_stale(row: Any, effective_formula: str | None) -> bool:
    """逐行读者的过期判据：:func:`stale_clause` 的两条之一成立，或 ``formula_used`` 与生效公式规范化后不同。

    ``row`` = ``FinancialReport`` 或含同名键的映射；``effective_formula`` = 该行在当前有效定义里的 ``formula``
    （:func:`formula_for`；有效定义里没有该行 ⇒ None，按空公式比较）。
    """
    if is_flag_stale(row):
        return True
    return normalize_formula(_get(row, "formula_used")) != normalize_formula(effective_formula)


def row_status(row: Any, effective_formula: str | None) -> dict[str, Any]:
    """逐行读者展示用：``is_stale``（:func:`is_effectively_stale`）+ ``calc_error`` + ``blank_reason``（两者都给）。"""
    return {
        "is_stale": is_effectively_stale(row, effective_formula),
        "calc_error": _get(row, "calc_error") or None,
        "blank_reason": _get(row, "blank_reason") or None,
    }


def status_note(status: Mapping[str, Any]) -> str:
    """导出用的一格说明：「已过期」「计算失败：…」「留空：…」按此顺序以「；」连接；三者皆无 ⇒ 空串。"""
    parts = ["已过期"] if status.get("is_stale") else []
    if status.get("calc_error"):
        parts.append(f"计算失败：{status['calc_error']}")
    if status.get("blank_reason"):
        parts.append(f"留空：{status['blank_reason']}")
    return "；".join(parts)


def formula_key(report_type: Any, row_code: str | None) -> FormulaKey:
    return (str(getattr(report_type, "value", report_type)), row_code or "")


def formula_for(formulas: Mapping[FormulaKey, str | None], row: Any) -> str | None:
    """在 :func:`load_effective_formulas` 的结果里取 ``row`` 的生效公式（没有该行 ⇒ None）。"""
    return formulas.get(formula_key(_get(row, "report_type"), _get(row, "row_code")))


async def load_effective_formulas(
    db: AsyncSession, project_id: UUID, *, report_type: Any = None,
) -> dict[FormulaKey, str | None]:
    """本项目当前有效报表定义的公式：``{(报表类型值, 行次): formula}``（准则行 ⊕ 本项目行，项目真实准则）。"""
    from app.services.formula_settings.effective_report import load_effective_report_configs
    from app.services.report_config_service import ReportConfigService

    standard = await ReportConfigService.resolve_applicable_standard(db, project_id)
    configs = await load_effective_report_configs(
        db, standard=standard, project_id=project_id, report_type=report_type)
    return {formula_key(c.report_type, c.row_code): c.formula for c in configs}


@dataclass(frozen=True)
class FreshnessCounts:
    """一个项目年度未删报表行的计数：总数 / 过期（:func:`stale_clause`）/ 计算失败 / 口径留空。"""

    total: int
    stale: int
    calc_error: int
    blank: int


async def count_summary(db: AsyncSession, project_id: UUID, year: int) -> FreshnessCounts:
    fr = FinancialReport
    row = (await db.execute(
        sa.select(
            sa.func.count(),
            sa.func.count().filter(stale_clause()),
            sa.func.count().filter(calc_error_clause()),
            sa.func.count().filter(blank_clause()),
        ).select_from(fr).where(fr.project_id == project_id, fr.year == year, fr.is_deleted == sa.false())
    )).one()
    return FreshnessCounts(*(int(v or 0) for v in row))


def calc_error_clause() -> sa.ColumnElement[bool]:
    return FinancialReport.calc_error.is_not(None)


def blank_clause() -> sa.ColumnElement[bool]:
    return FinancialReport.blank_reason.is_not(None)


async def list_rows(
    db: AsyncSession, project_id: UUID, year: int, condition: sa.ColumnElement[bool], *, limit: int = 30,
) -> list[dict[str, Any]]:
    """满足 ``condition``（:func:`stale_clause` / :func:`calc_error_clause` / :func:`blank_clause`）的未删行明细，
    按报表类型、行次排序；每行带 ``is_stale``（:func:`stale_clause`）与两种原因。"""
    fr = FinancialReport
    rows = (await db.execute(
        sa.select(fr.id, fr.report_type, fr.row_code, fr.row_name, stale_clause().label("is_stale"),
                  fr.calc_error, fr.blank_reason)
        .where(fr.project_id == project_id, fr.year == year, fr.is_deleted == sa.false(), condition)
        .order_by(fr.report_type, fr.row_code)
        .limit(limit)
    )).all()
    return [
        {"id": str(r.id), "report_type": str(getattr(r.report_type, "value", r.report_type)),
         "row_code": r.row_code, "row_name": r.row_name, "is_stale": bool(r.is_stale),
         "calc_error": r.calc_error, "blank_reason": r.blank_reason}
        for r in rows
    ]


# ── 写入侧：定义写入出口同事务标过期（任务 15，需求 5.1 写入部分）──────────────────────────────────


def slot_row_codes(slot_keys: Iterable[str]) -> set[str]:
    """报表公式位 ``{报表类型}:{行次}`` → 行次（与 ``propagation.propagate_report`` 同口径；没有行次的不算）。"""
    codes = (str(slot).partition(":")[2] for slot in slot_keys)
    return {code for code in codes if code}


def mark_statement(dialect: str, project_id: UUID, codes: Iterable[str]) -> sa.Update:
    """``UPDATE financial_report SET is_stale = true WHERE project_id = :p AND row_code = ANY(:closure)
    AND is_deleted = false``（不限年度）；非 PostgreSQL（SQLite 单测）用等价的 ``row_code IN (…)``。"""
    fr, values = FinancialReport, sorted(codes)
    if dialect == "postgresql":
        match = fr.row_code == sa.any_(sa.bindparam("closure", values, type_=postgresql.ARRAY(sa.String())))
    else:
        match = fr.row_code.in_(values)
    return (sa.update(fr).where(fr.project_id == project_id, match, fr.is_deleted == sa.false())
            .values(is_stale=True).execution_options(synchronize_session=False))


async def mark_changed(db: AsyncSession, changes: Mapping[UUID, Iterable[str]]) -> dict[UUID, set[str]]:
    """定义写入出口在同一事务内标过期：``changes`` = 项目 → 有效定义真正变化的行次。

    每个项目按 ``ReportConfigService.resolve_applicable_standard`` + ``load_effective_report_configs`` 取写入后的有效定义
    （与 :func:`load_effective_formulas` 同口径），经 ``propagation.report_closure`` 扩成「变化行 ∪ 经 ROW / SUM_ROW
    直接或间接引用它们的行」，把该项目**全部年度**的未删报表行标过期（与 ``propagate_report`` 同口径）。
    只 flush 不 commit：标记随出口所在事务一起提交或回滚。返回各项目的闭包（没有变化行的项目不出现）。
    """
    from app.services.formula_settings.effective_report import load_effective_report_configs
    from app.services.formula_settings.propagation import report_closure
    from app.services.report_config_service import ReportConfigService

    await db.flush()  # 有效定义须读到出口刚写入、尚未提交的定义行
    dialect = db.get_bind().dialect.name
    closures: dict[UUID, set[str]] = {}
    for project_id, codes in changes.items():
        changed = {code for code in codes if code}
        if not changed:
            continue
        standard = await ReportConfigService.resolve_applicable_standard(db, project_id)
        configs = await load_effective_report_configs(db, standard=standard, project_id=project_id)
        closure = report_closure(configs, changed)
        await db.execute(mark_statement(dialect, project_id, closure))
        closures[project_id] = closure
    return closures
