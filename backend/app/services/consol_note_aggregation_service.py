"""Sprint B.0 — 合并附注从子公司单体附注汇总核心服务.

5 种 aggregation_method: simple_sum / sum_after_elimination /
top_n_after_elimination / weighted_avg / first_n_concat

Validates: Requirements D12, CI-15, CI-16
"""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

AGGREGATION_METHODS = (
    "simple_sum", "sum_after_elimination", "top_n_after_elimination",
    "weighted_avg", "first_n_concat",
)


async def aggregate_section(
    consol_project_id: UUID, section_id: str, year: int,
    method: str = "simple_sum", config: dict | None = None,
    elimination_rules: list[dict] | None = None,
    child_filter: dict | None = None, db: Any = None,
) -> dict | None:
    """从子公司单体附注汇总到合并附注章节."""
    config = config or {}
    elimination_rules = elimination_rules or []
    child_filter = child_filter or {}
    if method not in AGGREGATION_METHODS:
        method = "simple_sum"

    child_projects = await _get_child_projects(consol_project_id, child_filter, db)
    if not child_projects:
        return None
    child_section_data = await _load_child_sections(child_projects, section_id, year, db)
    if not child_section_data:
        return None

    dispatch = {
        "simple_sum": lambda: _simple_sum(child_section_data, config),
        "sum_after_elimination": lambda: _sum_after_elimination(child_section_data, config, elimination_rules),
        "top_n_after_elimination": lambda: _top_n_after_elimination(child_section_data, config, elimination_rules),
        "weighted_avg": lambda: _weighted_avg(child_section_data, config),
        "first_n_concat": lambda: _first_n_concat(child_section_data, config),
    }
    result = dispatch.get(method, dispatch["simple_sum"])()
    if result is None:
        return None
    result["method"] = method
    result["child_count"] = len(child_projects)
    result["section_id"] = section_id
    return result


def aggregate_cell(
    child_values: list[Decimal | float | int | None],
    method: str = "simple_sum",
    elimination_amount: Decimal | float | int | None = None,
) -> Decimal | None:
    """聚合单个 cell 的子公司值."""
    valid = [Decimal(str(v)) for v in child_values if v is not None]
    if not valid:
        return None
    if method in ("simple_sum", "sum_after_elimination", "top_n_after_elimination"):
        total = sum(valid, Decimal("0"))
        if method == "sum_after_elimination" and elimination_amount is not None:
            total -= Decimal(str(elimination_amount))
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if method == "weighted_avg":
        avg = sum(valid, Decimal("0")) / len(valid)
        return avg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return sum(valid, Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# B.0.4 模糊合并同名算法
# ---------------------------------------------------------------------------

def fuzzy_merge_same_label(rows: list[dict], threshold: float = 0.85) -> list[dict]:
    """合并不同子公司与同一外部客户的行（label 相似度 ≥ threshold）."""
    if not rows:
        return []
    merged: list[dict] = []
    used: set[int] = set()
    for i, row_a in enumerate(rows):
        if i in used:
            continue
        label_a = row_a.get("label", "")
        group = [row_a]
        used.add(i)
        for j in range(i + 1, len(rows)):
            if j in used:
                continue
            if _label_similarity(label_a, rows[j].get("label", "")) >= threshold:
                group.append(rows[j])
                used.add(j)
        merged.append(group[0] if len(group) == 1 else _merge_row_group(group))
    return merged


def _label_similarity(a: str, b: str) -> float:
    """计算两个 label 的相似度（0~1），用 difflib.SequenceMatcher."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _merge_row_group(group: list[dict]) -> dict:
    """合并一组相似行：取第一个 label，values 求和."""
    result = {"label": group[0].get("label", ""), "values": {},
              "sources": [r.get("source_project") for r in group]}
    for row in group:
        for col_id, val in (row.get("values") or {}).items():
            if val is None:
                continue
            current = result["values"].get(col_id, Decimal("0"))
            try:
                result["values"][col_id] = current + Decimal(str(val))
            except Exception:
                if col_id not in result["values"]:
                    result["values"][col_id] = val
    return result


# ---------------------------------------------------------------------------
# B.0.5 多层合并 lineage 链（DAG 校验）
# ---------------------------------------------------------------------------

async def validate_lineage_dag(project_id: UUID, db: Any = None) -> bool:
    """校验多层合并 lineage 链无环（CI-16）."""
    visited: set[UUID] = set()
    current = project_id
    while current is not None:
        if current in visited:
            logger.error("Cycle detected in lineage chain at project %s", current)
            return False
        visited.add(current)
        current = await _get_parent_project_id(current, db)
    return True


async def get_lineage_chain(project_id: UUID, db: Any = None) -> list[UUID]:
    """获取从当前项目到最顶层的 lineage 链 [self, parent, grandparent, ...]."""
    chain: list[UUID] = []
    visited: set[UUID] = set()
    current: UUID | None = project_id
    while current is not None:
        if current in visited:
            break
        visited.add(current)
        chain.append(current)
        current = await _get_parent_project_id(current, db)
    return chain


# ---------------------------------------------------------------------------
# 内部聚合方法
# ---------------------------------------------------------------------------

def _simple_sum(child_data: list[dict], config: dict) -> dict:
    rows = _collect_all_rows(child_data)
    if config.get("merge_same_label_threshold"):
        rows = fuzzy_merge_same_label(rows, threshold=config["merge_same_label_threshold"])
    return {"rows": rows, "elimination_applied": False, "provenance": _build_provenance(child_data)}


def _sum_after_elimination(child_data: list[dict], config: dict, elimination_rules: list[dict]) -> dict:
    rows = _collect_all_rows(child_data)
    rows = fuzzy_merge_same_label(rows, threshold=config.get("merge_same_label_threshold", 0.85))
    elim = _calculate_elimination_from_rules(elimination_rules)
    for row in rows:
        if row.get("is_total"):
            for col_id, val in (row.get("values") or {}).items():
                if val is not None and elim:
                    try:
                        row["values"][col_id] = Decimal(str(val)) - elim
                    except Exception:
                        pass
    return {"rows": rows, "elimination_applied": True,
            "elimination_amount": str(elim) if elim else "0",
            "provenance": _build_provenance(child_data)}


def _top_n_after_elimination(child_data: list[dict], config: dict, elimination_rules: list[dict]) -> dict:
    rows = _collect_all_rows(child_data)
    rows = fuzzy_merge_same_label(rows, threshold=config.get("merge_same_label_threshold", 0.85))
    elim = _calculate_elimination_from_rules(elimination_rules)
    sort_col = config.get("sort_column", "col_amount_end")
    rows.sort(key=lambda r: abs(Decimal(str(r.get("values", {}).get(sort_col, 0) or 0))), reverse=True)
    top_n = config.get("top_n", 5)
    return {"rows": rows[:top_n], "elimination_applied": bool(elimination_rules),
            "elimination_amount": str(elim) if elim else "0",
            "total_rows_before_top_n": len(rows), "provenance": _build_provenance(child_data)}


def _weighted_avg(child_data: list[dict], config: dict) -> dict:
    rows: list[dict] = []
    total_weight = Decimal("0")
    for entry in child_data:
        weight = Decimal(str(entry.get("ownership_ratio", 1.0)))
        total_weight += weight
        for row in entry.get("rows", []):
            wr = {"label": row.get("label", ""), "values": {}, "source_project": entry.get("project_id")}
            for col_id, val in (row.get("values") or {}).items():
                if val is not None:
                    try:
                        wr["values"][col_id] = Decimal(str(val)) * weight
                    except Exception:
                        wr["values"][col_id] = val
            rows.append(wr)
    merged = fuzzy_merge_same_label(rows, threshold=config.get("merge_same_label_threshold", 0.85))
    if total_weight and total_weight != Decimal("0"):
        for row in merged:
            for col_id, val in (row.get("values") or {}).items():
                if isinstance(val, Decimal):
                    row["values"][col_id] = (val / total_weight).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"rows": merged, "elimination_applied": False, "provenance": _build_provenance(child_data)}


def _first_n_concat(child_data: list[dict], config: dict) -> dict:
    n = config.get("first_n", 5)
    texts = [{"project_id": str(e.get("project_id", "")), "company_name": e.get("company_name", ""),
              "text": e.get("text_content", "")} for e in child_data[:n] if e.get("text_content")]
    return {"rows": [], "texts": texts, "elimination_applied": False, "provenance": _build_provenance(child_data)}


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _collect_all_rows(child_data: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for entry in child_data:
        for row in entry.get("rows", []):
            row_copy = dict(row)
            row_copy["source_project"] = entry.get("project_id")
            rows.append(row_copy)
    return rows


def _build_provenance(child_data: list[dict]) -> list[dict]:
    return [{"project_id": str(e.get("project_id", "")), "company_name": e.get("company_name", ""),
             "row_count": len(e.get("rows", []))} for e in child_data]


def _calculate_elimination_from_rules(elimination_rules: list[dict]) -> Decimal:
    total = Decimal("0")
    for rule in elimination_rules:
        amount = rule.get("amount") or rule.get("elimination_amount") or 0
        try:
            total += Decimal(str(amount))
        except Exception:
            pass
    return total


async def _get_child_projects(consol_project_id: UUID, child_filter: dict, db: Any = None) -> list[dict]:
    """获取合并项目的子公司列表."""
    if child_filter.get("subsidiaries"):
        return [{"project_id": UUID(sid) if isinstance(sid, str) else sid}
                for sid in child_filter["subsidiaries"]]
    if db is None:
        return []
    try:
        from app.services.consol_tree_service import build_tree, get_descendants
        tree = await build_tree(db, consol_project_id)
        if tree is None:
            return []
        descendants = get_descendants(tree)
        return [{"project_id": n.project_id, "company_name": n.company_name,
                 "company_code": n.company_code} for n in descendants]
    except Exception as err:
        logger.warning("Failed to get child projects: %s", err)
        return []


async def _load_child_sections(
    child_projects: list[dict], section_id: str, year: int, db: Any = None,
) -> list[dict]:
    """加载子公司单体附注的对应章节数据."""
    if db is None:
        return []
    results: list[dict] = []
    try:
        from sqlalchemy import text
        for child in child_projects:
            pid = child["project_id"]
            row = await db.execute(
                text("SELECT table_data, text_content FROM disclosure_notes "
                     "WHERE project_id = :pid AND year = :year "
                     "AND section_id = :sid AND is_deleted = false LIMIT 1"),
                {"pid": str(pid), "year": year, "sid": section_id},
            )
            record = row.first()
            if record:
                rows = _extract_rows_from_table_data(record[0] or {})
                results.append({"project_id": pid, "company_name": child.get("company_name", ""),
                                "rows": rows, "text_content": record[1] or "",
                                "ownership_ratio": child.get("ownership_ratio", 1.0)})
    except Exception as err:
        logger.warning("Failed to load child sections: %s", err)
    return results


def _extract_rows_from_table_data(table_data: dict) -> list[dict]:
    """从 table_data 提取行数据."""
    if not isinstance(table_data, dict):
        return []
    result: list[dict] = []
    for row in table_data.get("rows", []):
        if not isinstance(row, dict):
            continue
        result.append({"label": row.get("label", ""),
                       "values": row.get("cells") or row.get("values") or {},
                       "row_type": row.get("row_type", "data"),
                       "is_total": row.get("row_type") == "total"})
    return result


async def _get_parent_project_id(project_id: UUID, db: Any = None) -> UUID | None:
    """获取项目的 parent_project_id."""
    if db is None:
        return None
    try:
        from sqlalchemy import text
        row = await db.execute(
            text("SELECT parent_project_id FROM projects WHERE id = :pid AND is_deleted = false"),
            {"pid": str(project_id)},
        )
        record = row.first()
        if record and record[0]:
            return UUID(str(record[0])) if isinstance(record[0], str) else record[0]
    except Exception:
        pass
    return None
