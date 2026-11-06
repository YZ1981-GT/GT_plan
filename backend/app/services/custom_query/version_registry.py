"""高级查询来源到版本分量的单一登记表。

本模块只声明来源、表、依据和中文标签，不执行查询。业务视图复用
``source_registry`` 的实际登记，构建器复用 ``table_whitelist``，避免版本口径
与查询白名单各自漂移。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.services.custom_query import source_registry as sources
from app.services.custom_query.entry_filters import REPORT_TYPES
from app.services.custom_query.table_whitelist import DATASET_SCOPED_TABLES, TABLE_WHITELIST

Basis = Literal["dataset", "content", "row_version", "timestamp", "scope"]


@dataclass(frozen=True)
class VersionDeclaration:
    key: str
    table: str
    label: str
    basis: Basis
    scope_kind: str = "project_year"
    fallback_table: str | None = None


# 表名只来自这里或 TABLE_WHITELIST，绝不来自请求。
_BUSINESS_BY_SOURCE: dict[str, tuple[VersionDeclaration, ...]] = {
    "trial_balance": (VersionDeclaration("trial_balance", "trial_balance", "试算平衡表", "content"),),
    "account_balance": (VersionDeclaration("account_balance", "ledger_datasets", "账套数据集", "dataset", fallback_table="tb_balance"),),
    "ledger_entries": (VersionDeclaration("ledger_entries", "ledger_datasets", "账套数据集", "dataset", fallback_table="tb_ledger"),),
    "aux_balance": (VersionDeclaration("aux_balance", "ledger_datasets", "账套数据集", "dataset", fallback_table="tb_aux_balance"),),
    "aux_ledger": (VersionDeclaration("aux_ledger", "ledger_datasets", "账套数据集", "dataset", fallback_table="tb_aux_ledger"),),
    "workpaper": (
        VersionDeclaration("workpaper", "working_paper", "底稿", "row_version", scope_kind="project"),
        VersionDeclaration("wp_index", "wp_index", "底稿索引", "content", scope_kind="project"),
    ),
    "workhours": (VersionDeclaration("workhours", "work_hours", "工时", "content"),),
    "report": (
        VersionDeclaration("financial_report", "financial_report", "报表", "content"),
        VersionDeclaration("report_config", "report_config", "报表配置", "standard"),
    ),
    "report_lines": (VersionDeclaration("report_config", "report_config", "报表行次配置", "content", scope_kind="standard"),),
    "adjustment": (VersionDeclaration("adjustments", "adjustments", "调整分录", "content"),),
    "adj_aje": (VersionDeclaration("adjustments", "adjustments", "调整分录", "content"),),
    "adj_rje": (VersionDeclaration("adjustments", "adjustments", "调整分录", "content"),),
    "tb_summary": (VersionDeclaration("consol_worksheet_data", "consol_worksheet_data", "合并工作底稿", "row_version"),),
    "worksheet": (VersionDeclaration("consol_worksheet_data", "consol_worksheet_data", "合并工作底稿", "row_version"),),
    "disclosure": (
        VersionDeclaration("disclosure_notes", "disclosure_notes", "附注", "row_version"),
        VersionDeclaration("consol_note_data", "consol_note_data", "合并附注", "row_version"),
    ),
    "disclosure_note": (
        VersionDeclaration("disclosure_notes", "disclosure_notes", "附注", "row_version"),
        VersionDeclaration("consol_note_data", "consol_note_data", "合并附注", "row_version"),
    ),
}

# 对外保留可检查的两张登记表。业务表包含解析后的别名和前缀，构建器表逐项覆盖白名单。
BUSINESS_VERSION_REGISTRY = dict(_BUSINESS_BY_SOURCE)
BUILDER_VERSION_REGISTRY: dict[str, tuple[VersionDeclaration, ...]] = {}
for _table, _meta in TABLE_WHITELIST.items():
    _basis: Basis = "dataset" if _table in DATASET_SCOPED_TABLES else (
        "row_version" if _table in {"working_paper", "disclosure_notes", "projects"} else "content"
    )
    BUILDER_VERSION_REGISTRY[_table] = (VersionDeclaration(
        key=f"builder:{_table}", table=_table, label=str(_meta["label"]), basis=_basis,
        scope_kind="project" if _table in {"working_paper", "disclosure_notes", "projects"} else "project_year",
        fallback_table=_table if _basis == "dataset" else None,
    ),)

# JSONB 大列是行版本，不能改成 content：内容摘要会把整个 JSON 读入数据库聚合。
JSONB_ROW_VERSION_TABLES = frozenset({
    "working_paper", "disclosure_notes", "consol_note_data", "consol_worksheet_data", "projects",
})


def _canonical_source(source: str) -> str:
    key = (source or "").strip()
    if key.startswith("consol_unit:"):
        kind = key.split(":", 2)[-1]
        return sources.CONSOL_UNIT_KINDS.get(kind, kind)
    if key.startswith("workpaper:"):
        return "workpaper"
    if key.startswith("disclosure_note:"):
        return "disclosure_note"
    if key.startswith(sources.REPORT_SOURCE_PREFIX):
        return "report"
    if key.startswith("ws_"):
        return "worksheet"
    return sources.SOURCE_ALIASES.get(key, key)


def declarations_for_business(source: str, *, acnr_targets: bool = False) -> tuple[VersionDeclaration, ...]:
    """返回业务视图来源的版本分量声明。"""
    declarations = list(BUSINESS_VERSION_REGISTRY.get(_canonical_source(source), ()))
    if not declarations:
        # 未知源由查询源解析器负责 400；这里 fail closed，不能无分量地声称新鲜。
        raise KeyError(f"业务源未登记版本分量：{source}")
    if acnr_targets and not any(d.table == "working_paper" for d in declarations):
        declarations.append(VersionDeclaration("acnr_targets", "working_paper", "底稿", "row_version", scope_kind="project"))
    return tuple(declarations)


def declarations_for_builder(tables: list[str] | tuple[str, ...] | set[str]) -> tuple[VersionDeclaration, ...]:
    """按构建器实际基表及 JOIN 表逐项返回版本分量。"""
    out: list[VersionDeclaration] = []
    for table in dict.fromkeys(str(t) for t in tables):
        try:
            out.extend(BUILDER_VERSION_REGISTRY[table])
        except KeyError as exc:
            raise KeyError(f"构建器表未登记版本分量：{table}") from exc
    return tuple(out)


def _assert_registry_complete() -> None:
    """登记期完整性守卫；任务 M7 会删除一项并要求此守卫打红。"""
    problems: list[str] = []
    for key in sources.SOURCE_REGISTRY:
        if key not in BUSINESS_VERSION_REGISTRY:
            problems.append(f"SOURCE_REGISTRY:{key}")
    for alias, target in sources.SOURCE_ALIASES.items():
        if target not in BUSINESS_VERSION_REGISTRY:
            problems.append(f"SOURCE_ALIASES:{alias}->{target}")
    for key in sources.JSON_SOURCES:
        if key not in BUSINESS_VERSION_REGISTRY:
            problems.append(f"JSON_SOURCES:{key}")
    for prefix, _target in sources.JSON_PREFIXES:
        if not any(k.startswith(prefix) or k == "worksheet" for k in BUSINESS_VERSION_REGISTRY):
            problems.append(f"JSON_PREFIXES:{prefix}")
    if "workpaper_cells" not in {sources.WORKPAPER_CELLS[0], "workpaper_cells"}:
        problems.append("WORKPAPER_CELLS")
    if "workpaper" not in BUSINESS_VERSION_REGISTRY:
        problems.append("WORKPAPER_CELLS:workpaper")
    for kind, target in sources.CONSOL_UNIT_KINDS.items():
        if target not in BUSINESS_VERSION_REGISTRY:
            problems.append(f"CONSOL_UNIT_KINDS:{kind}->{target}")
    for report_type in REPORT_TYPES:
        if f"report_{report_type}" not in BUSINESS_VERSION_REGISTRY and "report" not in BUSINESS_VERSION_REGISTRY:
            problems.append(f"REPORT_TYPES:{report_type}")
    for table in TABLE_WHITELIST:
        if not BUILDER_VERSION_REGISTRY.get(table):
            problems.append(f"TABLE_WHITELIST:{table}")
    for table in JSONB_ROW_VERSION_TABLES:
        declarations = [d for values in BUILDER_VERSION_REGISTRY.values() for d in values if d.table == table]
        declarations += [d for values in BUSINESS_VERSION_REGISTRY.values() for d in values if d.table == table]
        if any(d.basis == "content" for d in declarations):
            problems.append(f"JSONB_CONTENT:{table}")
    if problems:
        raise AssertionError("高级查询版本登记不完整：" + "；".join(sorted(problems)))


_assert_registry_complete()

__all__ = [
    "Basis", "VersionDeclaration", "BUSINESS_VERSION_REGISTRY", "BUILDER_VERSION_REGISTRY",
    "JSONB_ROW_VERSION_TABLES", "declarations_for_business", "declarations_for_builder",
    "_assert_registry_complete",
]
