"""合并附注明细来源扫描、结构指纹、建议与预览 service（Phase 2 Task 8~14）。

spec: consol-note-detail-template-and-mapping

纯函数不依赖 DB 的部分放模块顶层；需要 DB 的放 async 函数。
Service 只 flush 不 commit。
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_note_mapping_models import (
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)
from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 行标签提取（复用 consol_note_formula_service 口径）
# ═══════════════════════════════════════════════════════════════════════════════


def _first_cell(row: Any) -> str:
    """提取行标签——兼容 list 和 dict 两种行形态。"""
    if isinstance(row, dict):
        return str(row.get("label") or row.get("name") or "")
    if isinstance(row, (list, tuple)) and row:
        return str(row[0] or "")
    return ""


def _row_type(row: Any) -> str:
    if isinstance(row, dict):
        rt = str(row.get("row_type", "data")).strip()
        if rt in ("total", "subtotal"):
            return rt
        if rt not in ("data", ""):
            # 非标准类型（如 header）——不做标签推导，直接归为 data
            return "data"
        label = str(row.get("label") or "").strip().replace("\u3000", "").replace(" ", "")
        if label in ("合计", "合\u3000计"):
            return "total"
        if label == "小计":
            return "subtotal"
        return "data"
    if isinstance(row, (list, tuple)) and row:
        label = str(row[0] or "").strip().replace("\u3000", "").replace(" ", "")
        if label in ("合计", "合\u3000计"):
            return "total"
        if label == "小计":
            return "subtotal"
    return "data"


def _stable_key(row: Any) -> str:
    """提取稳定行键（row_id / item_id），没有则返回空串。"""
    if isinstance(row, dict):
        for key in ("row_id", "item_id", "id", "uuid"):
            val = row.get(key)
            if val and str(val).strip():
                return str(val).strip()
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 结构指纹（R2.1 / D§三）
# ═══════════════════════════════════════════════════════════════════════════════


def extract_source_rows(rows: list[Any]) -> list[dict[str, str]]:
    """从 table_data.rows 提取结构信息（不含金额）。

    返回 ``[{label, row_type, key}]``。
    """
    items: list[dict[str, str]] = []
    seen: dict[str, int] = {}
    for row in rows:
        label = _first_cell(row).strip()
        rt = _row_type(row)
        sk = _stable_key(row)
        if not sk:
            count = seen.get(label, 0)
            seen[label] = count + 1
            sk = f"{label}#{count}"
        items.append({"label": label, "row_type": rt, "key": sk})
    return items


def compute_source_structure_hash(section_id: str, rows: list[Any]) -> str:
    """计算来源结构指纹（SHA-256）。排除金额，只含标签/行类型/键。"""
    items = extract_source_rows(rows)
    payload = json.dumps(
        {"section_id": section_id, "items": items},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def group_entities_by_structure(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按 source_structure_hash 分组。

    输入：``[{node_key, project_id, company_name, section_id, rows, hash}]``
    输出：``[{hash, section_id, source_rows, entities: [{node_key, project_id, company_name}]}]``
    """
    groups: dict[str, dict[str, Any]] = {}
    for entity in entities:
        h = entity["hash"]
        if h not in groups:
            groups[h] = {
                "hash": h,
                "section_id": entity["section_id"],
                "source_rows": extract_source_rows(entity["rows"]),
                "entities": [],
            }
        groups[h]["entities"].append({
            "node_key": entity["node_key"],
            "project_id": str(entity["project_id"]),
            "company_name": entity.get("company_name", ""),
        })
    return list(groups.values())


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 来源读取（R2.1 / D§五.4 preview 前置）
# ═══════════════════════════════════════════════════════════════════════════════


async def load_entity_source_rows(
    db: AsyncSession,
    entity_project_id: UUID,
    section_id: str,
    year: int,
) -> list[Any]:
    """从单个子企业的 disclosure_notes 读取来源行。"""
    note = (await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == entity_project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == section_id,
            DisclosureNote.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if note is None or not isinstance(note.table_data, dict):
        return []
    return note.table_data.get("rows", [])


async def scan_all_entities(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str,
    year: int,
) -> list[dict[str, Any]]:
    """扫描所有数据叶子企业，返回含 hash 的实体列表。"""
    from app.services.consol_calc_basis import data_leaves
    from app.services.consol_tree_service import build_tree

    tree = await build_tree(db, consol_project_id)
    if tree is None:
        return []

    entities: list[dict[str, Any]] = []
    # TODO: N+1 查询——叶子企业多时应改为 IN 批查 disclosure_notes
    for leaf in data_leaves(tree):
        if leaf.project_id is None:
            continue
        rows = await load_entity_source_rows(db, leaf.project_id, section_id, year)
        h = compute_source_structure_hash(section_id, rows)
        entities.append({
            "node_key": leaf.node_key,
            "project_id": leaf.project_id,
            "company_name": getattr(leaf, "company_name", "") or "",
            "section_id": section_id,
            "rows": rows,
            "hash": h,
        })
    return entities


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 模板建议算法（R1.1 / D§六）
# ═══════════════════════════════════════════════════════════════════════════════


def suggest_template_rows(
    source_groups: list[dict[str, Any]],
    *,
    existing_template_rows: list[dict[str, Any]] | None = None,
    history_mappings: list[dict[str, Any]] | None = None,
    rule_template_suggestions: list[dict[str, Any]] | None = None,
    previous_year_suggestions: list[dict[str, Any]] | None = None,
    fuzzy_threshold: float = 0.75,
) -> list[dict[str, Any]]:
    """生成模板建议行列表。

    每条来源标签经七级匹配：
    1. 精确匹配目标 canonical_name
    2. 别名匹配 aliases
    3. 规则模板库匹配（rule_template_suggestions，confidence=0.92）
    4. 上年同集团项目匹配（previous_year_suggestions，confidence=0.88）
    5. 模糊匹配（SequenceMatcher ≥ threshold）
    6. 历史规则复用
    7. 未匹配 → 建议新增

    返回 ``[{source_label, suggested_target, confidence, match_type, candidates}]``
    """
    template_rows = existing_template_rows or []
    history = history_mappings or []

    # 构建规则模板建议索引（source_label → suggestion）
    rule_tmpl_index: dict[str, dict[str, Any]] = {}
    for s in (rule_template_suggestions or []):
        sl = str(s.get("source_label", "")).strip()
        if sl and s.get("suggested_target"):
            rule_tmpl_index[sl] = s

    # 构建上年项目建议索引
    prev_year_index: dict[str, dict[str, Any]] = {}
    for s in (previous_year_suggestions or []):
        sl = str(s.get("source_label", "")).strip()
        if sl and s.get("suggested_target"):
            prev_year_index[sl] = s

    # 收集所有来源标签（去重保序）
    all_labels: list[str] = []
    seen: set[str] = set()
    for group in source_groups:
        for sr in group.get("source_rows", []):
            label = sr["label"]
            if label and label not in seen:
                all_labels.append(label)
                seen.add(label)

    # 构建目标索引
    name_to_target: dict[str, dict[str, Any]] = {}
    alias_to_target: dict[str, dict[str, Any]] = {}
    for tr in template_rows:
        cn = str(tr.get("canonical_name", "")).strip()
        if cn:
            name_to_target[cn] = tr
        for alias in tr.get("aliases", []):
            a = str(alias).strip()
            if a:
                alias_to_target[a] = tr

    # 历史映射索引
    history_index: dict[str, str] = {}
    for hm in history:
        sl = str(hm.get("source_label", "")).strip()
        trid = str(hm.get("target_row_id", "")).strip()
        if sl and trid:
            history_index[sl] = trid

    suggestions: list[dict[str, Any]] = []
    for label in all_labels:
        # 1. 精确匹配 canonical_name
        if label in name_to_target:
            suggestions.append(_suggestion(
                label, name_to_target[label], "exact", 1.0,
            ))
            continue

        # 2. 别名匹配
        if label in alias_to_target:
            suggestions.append(_suggestion(
                label, alias_to_target[label], "alias", 0.95,
            ))
            continue

        # 3. 规则模板库匹配（confidence=0.92）
        if label in rule_tmpl_index:
            s = rule_tmpl_index[label]
            suggestions.append({
                "source_label": label,
                "suggested_target": s["suggested_target"],
                "confidence": s.get("confidence", 0.92),
                "match_type": "rule_template",
                "candidates": s.get("candidates", []),
                **({"template_id": s["template_id"]} if "template_id" in s else {}),
            })
            continue

        # 4. 上年同集团项目匹配（confidence=0.88）
        if label in prev_year_index:
            s = prev_year_index[label]
            suggestions.append({
                "source_label": label,
                "suggested_target": s["suggested_target"],
                "confidence": s.get("confidence", 0.88),
                "match_type": "previous_year",
                "candidates": s.get("candidates", []),
            })
            continue

        # 5. 模糊匹配
        best_ratio = 0.0
        best_target: dict[str, Any] | None = None
        candidates: list[dict[str, Any]] = []
        for tr in template_rows:
            cn = str(tr.get("canonical_name", ""))
            ratio = SequenceMatcher(None, label, cn).ratio()
            if ratio >= fuzzy_threshold:
                candidates.append({"target": tr, "ratio": round(ratio, 3)})
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_target = tr
            for alias in tr.get("aliases", []):
                r2 = SequenceMatcher(None, label, str(alias)).ratio()
                if r2 >= fuzzy_threshold and r2 > best_ratio:
                    best_ratio = r2
                    best_target = tr
                    candidates.append({"target": tr, "ratio": round(r2, 3)})

        if best_target is not None:
            suggestions.append(_suggestion(
                label, best_target, "fuzzy", round(best_ratio, 3), candidates,
            ))
            continue

        # 6. 历史规则复用
        if label in history_index:
            target_row_id = history_index[label]
            # 在模板中找到对应行
            for tr in template_rows:
                if str(tr.get("target_row_id", "")) == target_row_id:
                    suggestions.append(_suggestion(
                        label, tr, "history", 0.85,
                    ))
                    break
            else:
                suggestions.append({
                    "source_label": label,
                    "suggested_target": None,
                    "confidence": 0.0,
                    "match_type": "manual",
                    "candidates": [],
                })
            continue

        # 7. 未匹配
        suggestions.append({
            "source_label": label,
            "suggested_target": None,
            "confidence": 0.0,
            "match_type": "manual",
            "candidates": [],
        })

    return suggestions


def _suggestion(
    label: str,
    target: dict[str, Any],
    match_type: str,
    confidence: float,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "source_label": label,
        "suggested_target": {
            "target_row_id": target.get("target_row_id"),
            "canonical_name": target.get("canonical_name"),
        },
        "confidence": confidence,
        "match_type": match_type,
        "candidates": candidates or [],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Preview（R4.1 / D§四）
# ═══════════════════════════════════════════════════════════════════════════════


async def preview_detail_refresh(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    year: int,
) -> dict[str, Any]:
    """预览明细刷新——只读，不写数据，生成 preview_token。

    返回 ``{preview_token, section_id, year, groups, stale_entities, suggestions, template_binding}``
    """
    # 1. 扫描来源
    entities = await scan_all_entities(
        db, consol_project_id=project_id, section_id=section_id, year=year,
    )
    groups = group_entities_by_structure(entities)

    # 2. 读取当前模板绑定
    binding = (await db.execute(
        sa.select(ConsolNoteTemplateBinding).where(
            ConsolNoteTemplateBinding.project_id == project_id,
            ConsolNoteTemplateBinding.section_id == section_id,
        )
    )).scalar_one_or_none()

    template_version_id: str | None = None
    template_rows: list[dict[str, Any]] = []
    if binding is not None:
        template_version_id = str(binding.template_version_id)
        from app.models.consol_note_mapping_models import ConsolNoteDetailTemplateVersion
        version = (await db.execute(
            sa.select(ConsolNoteDetailTemplateVersion).where(
                ConsolNoteDetailTemplateVersion.id == binding.template_version_id,
            )
        )).scalar_one_or_none()
        if version is not None and isinstance(version.rows, list):
            template_rows = version.rows

    # 3. 检测 stale 绑定（只读——标记在返回值中，不写数据库；实际 stale 标记在 confirm/apply 阶段）
    stale_entities: list[dict[str, Any]] = []
    for entity in entities:
        existing_binding = (await db.execute(
            sa.select(ConsolNoteMappingBinding).where(
                ConsolNoteMappingBinding.project_id == project_id,
                ConsolNoteMappingBinding.section_id == section_id,
                ConsolNoteMappingBinding.entity_node_key == entity["node_key"],
            )
        )).scalar_one_or_none()
        if existing_binding is not None:
            if existing_binding.bound_source_hash != entity["hash"]:
                stale_entities.append({
                    "node_key": entity["node_key"],
                    "company_name": entity.get("company_name", ""),
                    "old_hash": existing_binding.bound_source_hash,
                    "new_hash": entity["hash"],
                    "status": "stale",
                })

    # 4. 读取历史映射
    history: list[dict[str, Any]] = []
    rules: list[Any] = []
    if template_version_id:
        rules = (await db.execute(
            sa.select(ConsolNoteMappingRule).where(
                ConsolNoteMappingRule.project_id == project_id,
                ConsolNoteMappingRule.section_id == section_id,
                ConsolNoteMappingRule.is_active == sa.true(),
            )
        )).scalars().all()
        for rule in rules:
            for m in (rule.mappings if isinstance(rule.mappings, list) else []):
                history.append(m)

    # 5. 生成建议
    suggestions = suggest_template_rows(
        groups,
        existing_template_rows=template_rows,
        history_mappings=history,
    )

    # 6. 为每组标注映射状态
    for group in groups:
        group_hash = group["hash"]
        # 查找该组是否已有规则
        existing_rule = None
        for rule in (rules if template_version_id else []):
            if rule.source_structure_hash == group_hash:
                existing_rule = rule
                break
        group["has_rule"] = existing_rule is not None
        group["rule_id"] = str(existing_rule.id) if existing_rule else None
        # 所有企业都已确认且非 stale？
        stale_keys = {se["node_key"] for se in stale_entities}
        group["all_confirmed"] = (
            existing_rule is not None
            and all(e["node_key"] not in stale_keys for e in group["entities"])
        )

    # 7. 生成 preview_token
    token_data = {
        "project_id": str(project_id),
        "section_id": section_id,
        "year": year,
        "entity_hashes": {e["node_key"]: e["hash"] for e in entities},
        "template_version_id": template_version_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    preview_token = hashlib.sha256(
        json.dumps(token_data, sort_keys=True).encode()
    ).hexdigest()[:32] + secrets.token_hex(8)

    return {
        "preview_token": preview_token,
        "project_id": str(project_id),
        "section_id": section_id,
        "year": year,
        "template_version_id": template_version_id,
        "template_rows": template_rows,
        "groups": groups,
        "stale_entities": stale_entities,
        "suggestions": suggestions,
        "entity_count": len(entities),
        "group_count": len(groups),
        "stale_count": len(stale_entities),
        # 存 token_data 供 apply 校验
        "_token_data": token_data,
    }


async def suggest_template_for_section(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    year: int,
) -> dict[str, Any]:
    """扫描来源并生成模板行建议（不含规则匹配，只做频率+模糊分析）。"""
    entities = await scan_all_entities(
        db, consol_project_id=project_id, section_id=section_id, year=year,
    )
    groups = group_entities_by_structure(entities)

    # 统计所有行标签出现频率和金额占比
    label_stats: dict[str, dict[str, Any]] = {}
    for entity in entities:
        for row in entity["rows"]:
            label = _first_cell(row).strip()
            rt = _row_type(row)
            if not label:
                continue
            if label not in label_stats:
                # row_type 取首次出现的值（同标签在不同企业可能标不同类型，以首次为准）
                label_stats[label] = {"count": 0, "row_type": rt, "total_amount": 0.0}
            label_stats[label]["count"] += 1
            # 尝试提取金额
            if isinstance(row, dict):
                vals = row.get("values") or row.get("cells") or {}
                if isinstance(vals, dict):
                    for v in vals.values():
                        try:
                            label_stats[label]["total_amount"] += abs(float(v))
                        except (TypeError, ValueError):
                            pass
            elif isinstance(row, (list, tuple)):
                for v in row[1:]:
                    try:
                        label_stats[label]["total_amount"] += abs(float(str(v).replace(",", "")))
                    except (TypeError, ValueError):
                        pass

    # 按频率降序排列，合计行放最后
    sorted_labels = sorted(
        label_stats.items(),
        key=lambda x: (x[1]["row_type"] == "total", -x[1]["count"], -x[1]["total_amount"]),
    )

    suggested_rows: list[dict[str, Any]] = []
    for i, (label, stats) in enumerate(sorted_labels):
        suggested_rows.append({
            "canonical_name": label,
            "aliases": [],
            "sort_order": i * 10,
            "row_type": stats["row_type"],
            "frequency": stats["count"],
            "total_amount": round(stats["total_amount"], 2),
            "entity_total": len(entities),
        })

    return {
        "section_id": section_id,
        "entity_count": len(entities),
        "group_count": len(groups),
        "suggested_rows": suggested_rows,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 上年同集团项目映射匹配（V200 spec: consol-note-mapping-reuse-and-reference-push）
# ═══════════════════════════════════════════════════════════════════════════════


async def find_previous_year_rules(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str,
    source_structure_hash: str,
) -> list[dict[str, Any]]:
    """查找同集团上年项目的确认过的映射规则。

    ⚠ projects 表无 client_id 字段，按双条件定位同集团：
    1. 主条件：projects.client_name 精确匹配（同一审计客户名称相同）
    2. 辅条件：projects.ultimate_company_code 非空且一致（最终控制方代码）
    两个条件取 OR。

    步骤：
    1. 读当前项目的 client_name + ultimate_company_code
    2. 查满足双条件的其他合并项目，按 audit_period_end DESC 排序
    3. 在上年项目中查 section_id + source_structure_hash 匹配的 active rule

    返回 ``[{source_label, suggested_target, confidence, match_type}]``
    格式与 suggest_template_rows 的 suggestions 兼容，可直接传入 previous_year_suggestions。
    """
    from app.models.core import Project
    from app.models.consol_note_mapping_models import ConsolNoteMappingRule

    # 1. 读当前项目信息
    current = (await db.execute(
        sa.select(Project.client_name, Project.ultimate_company_code).where(
            Project.id == consol_project_id
        )
    )).one_or_none()
    if current is None:
        return []

    client_name, ultimate_code = current.client_name, current.ultimate_company_code

    # 2. 查同集团其他合并项目
    conditions = [
        Project.id != consol_project_id,
        Project.is_deleted == sa.false(),
    ]
    # 双条件 OR：client_name 或 ultimate_company_code
    or_clauses = [Project.client_name == client_name]
    if ultimate_code:
        or_clauses.append(
            sa.and_(
                Project.ultimate_company_code.isnot(None),
                Project.ultimate_company_code == ultimate_code,
            )
        )
    conditions.append(sa.or_(*or_clauses))

    peer_projects = (await db.execute(
        sa.select(Project.id).where(*conditions)
        .order_by(Project.audit_period_end.desc().nullslast())
        .limit(10)  # 性能限制：只查最近 10 个项目
    )).scalars().all()

    if not peer_projects:
        return []

    # 3. 查上年项目中匹配的 active rule
    rules = (await db.execute(
        sa.select(ConsolNoteMappingRule).where(
            ConsolNoteMappingRule.project_id.in_(peer_projects),
            ConsolNoteMappingRule.section_id == section_id,
            ConsolNoteMappingRule.source_structure_hash == source_structure_hash,
            ConsolNoteMappingRule.is_active == sa.true(),
        ).order_by(ConsolNoteMappingRule.confirmed_at.desc().nullslast())
        .limit(1)
    )).scalars().all()

    if not rules:
        return []

    rule = rules[0]
    mappings = rule.mappings if isinstance(rule.mappings, list) else []

    # 转换为 suggestions 格式
    suggestions: list[dict[str, Any]] = []
    for m in mappings:
        sl = str(m.get("source_label", "")).strip()
        target_row_id = m.get("target_row_id")
        if not sl or not target_row_id:
            continue
        if m.get("mapping_action") == "ignore":
            continue
        suggestions.append({
            "source_label": sl,
            "suggested_target": {
                "target_row_id": target_row_id,
                "canonical_name": m.get("canonical_name"),
            },
            "confidence": 0.88,
            "match_type": "previous_year",
            "candidates": [],
        })

    return suggestions
