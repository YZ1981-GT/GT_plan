"""合并附注映射规则模板服务——从项目规则提升为可复用模板、查找、建议。

spec: consol-note-mapping-reuse-and-reference-push Phase 2 Task 3~5

Service 只 flush 不 commit（router 层 commit）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_note_mapping_models import (
    ConsolNoteMappingRule,
)
from app.models.consol_note_mapping_template_models import (
    ConsolNoteMappingRuleTemplate,
)

logger = logging.getLogger(__name__)


# ─── 错误 ────────────────────────────────────────────────────────────────────


class MappingTemplateError(Exception):
    """映射规则模板操作错误。"""

    def __init__(self, status: int, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 提升规则为模板（US-1）
# ═══════════════════════════════════════════════════════════════════════════════


async def promote_rule_to_template(
    db: AsyncSession,
    *,
    rule_id: UUID,
    promoted_by: UUID,
) -> dict[str, Any]:
    """将项目级映射规则提升为规则模板。

    校验：
    1. 规则必须是 active 的
    2. 规则的映射完整性（无 target_row_id=None 的条目）
    3. 规则尚未被提升过（promoted_to_template_id 非空→409）
    4. 同 template_type+section_id+hash 已有 active 模板→升版（旧版停用）
    """
    rule = (await db.execute(
        sa.select(ConsolNoteMappingRule).where(ConsolNoteMappingRule.id == rule_id)
    )).scalar_one_or_none()
    if rule is None:
        raise MappingTemplateError(404, "RULE_NOT_FOUND", "映射规则不存在")
    if not rule.is_active:
        raise MappingTemplateError(400, "RULE_INACTIVE", "只能提升活跃的映射规则")

    # 校验映射完整性
    mappings = rule.mappings if isinstance(rule.mappings, list) else []
    incomplete = [
        m for m in mappings
        if m.get("mapping_action") != "ignore" and not m.get("target_row_id")
    ]
    if incomplete:
        raise MappingTemplateError(
            400, "INCOMPLETE_MAPPING",
            f"映射不完整：{len(incomplete)} 条来源行未指定目标行",
            {"incomplete_labels": [m.get("source_label", "") for m in incomplete]},
        )

    # 校验重复提升
    if rule.promoted_to_template_id is not None:
        raise MappingTemplateError(
            409, "ALREADY_PROMOTED",
            "该规则已提升为模板",
            {"template_id": str(rule.promoted_to_template_id)},
        )

    # 需要读 template_type——从绑定的模板版本中获取
    from app.models.consol_note_mapping_models import ConsolNoteDetailTemplateVersion
    from app.models.consol_note_mapping_models import ConsolNoteDetailTemplate

    version = (await db.execute(
        sa.select(ConsolNoteDetailTemplateVersion).where(
            ConsolNoteDetailTemplateVersion.id == rule.template_version_id
        )
    )).scalar_one_or_none()
    if version is None:
        raise MappingTemplateError(500, "VERSION_MISSING", "关联的模板版本不存在")

    template = (await db.execute(
        sa.select(ConsolNoteDetailTemplate).where(
            ConsolNoteDetailTemplate.id == version.template_id
        )
    )).scalar_one_or_none()
    if template is None:
        raise MappingTemplateError(500, "TEMPLATE_MISSING", "关联的模板不存在")

    template_type = template.template_type

    # 提取 account_code_hints（从模板版本的 rows 中读 recommended_account_codes）
    account_code_hints: dict[str, list[str]] = {}
    if isinstance(version.rows, list):
        for row in version.rows:
            if isinstance(row, dict):
                codes = row.get("recommended_account_codes")
                rid = row.get("target_row_id")
                if codes and rid:
                    account_code_hints[str(rid)] = codes

    # 查是否已有同 template_type+section_id+hash 的 active 模板
    existing = (await db.execute(
        sa.select(ConsolNoteMappingRuleTemplate).where(
            ConsolNoteMappingRuleTemplate.template_type == template_type,
            ConsolNoteMappingRuleTemplate.section_id == rule.section_id,
            ConsolNoteMappingRuleTemplate.source_structure_hash == rule.source_structure_hash,
            ConsolNoteMappingRuleTemplate.is_active == sa.true(),
        ).order_by(ConsolNoteMappingRuleTemplate.version_number.desc())
    )).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing is not None:
        # 升版：停用旧版
        existing.is_active = False
        await db.flush()
        new_version = existing.version_number + 1
    else:
        new_version = 1

    tmpl = ConsolNoteMappingRuleTemplate(
        template_type=template_type,
        section_id=rule.section_id,
        source_structure_hash=rule.source_structure_hash,
        version_number=new_version,
        mappings=mappings,
        account_code_hints=account_code_hints if account_code_hints else None,
        source_project_id=rule.project_id,
        source_rule_id=rule.id,
        promoted_by=promoted_by,
        promoted_at=now,
    )
    db.add(tmpl)
    await db.flush()

    # 标记源规则已提升
    rule.promoted_to_template_id = tmpl.id
    await db.flush()

    return {
        "action": "promoted",
        "template_id": str(tmpl.id),
        "template_type": template_type,
        "section_id": tmpl.section_id,
        "source_structure_hash": tmpl.source_structure_hash,
        "version_number": tmpl.version_number,
        "mapping_count": len(mappings),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 查找（US-2 辅助）
# ═══════════════════════════════════════════════════════════════════════════════


async def find_template_for_hash(
    db: AsyncSession,
    *,
    template_type: str,
    section_id: str,
    source_structure_hash: str,
) -> dict[str, Any] | None:
    """按结构指纹精确查找规则模板（最新活跃版本）。"""
    tmpl = (await db.execute(
        sa.select(ConsolNoteMappingRuleTemplate).where(
            ConsolNoteMappingRuleTemplate.template_type == template_type,
            ConsolNoteMappingRuleTemplate.section_id == section_id,
            ConsolNoteMappingRuleTemplate.source_structure_hash == source_structure_hash,
            ConsolNoteMappingRuleTemplate.is_active == sa.true(),
        ).order_by(ConsolNoteMappingRuleTemplate.version_number.desc())
    )).scalar_one_or_none()
    if tmpl is None:
        return None
    return _tmpl_to_dict(tmpl)


async def find_templates_for_section(
    db: AsyncSession,
    *,
    template_type: str,
    section_id: str,
) -> list[dict[str, Any]]:
    """列出某章节的所有活跃规则模板。"""
    result = await db.execute(
        sa.select(ConsolNoteMappingRuleTemplate).where(
            ConsolNoteMappingRuleTemplate.template_type == template_type,
            ConsolNoteMappingRuleTemplate.section_id == section_id,
            ConsolNoteMappingRuleTemplate.is_active == sa.true(),
        ).order_by(ConsolNoteMappingRuleTemplate.version_number.desc())
    )
    return [_tmpl_to_dict(t) for t in result.scalars().all()]


async def get_template(
    db: AsyncSession,
    template_id: UUID | str,
) -> dict[str, Any] | None:
    """获取单个规则模板详情。"""
    if isinstance(template_id, str):
        template_id = UUID(template_id)
    tmpl = (await db.execute(
        sa.select(ConsolNoteMappingRuleTemplate).where(
            ConsolNoteMappingRuleTemplate.id == template_id,
            ConsolNoteMappingRuleTemplate.is_active == sa.true(),
        )
    )).scalar_one_or_none()
    if tmpl is None:
        return None
    return _tmpl_to_dict(tmpl)


async def list_templates(
    db: AsyncSession,
    *,
    template_type: str | None = None,
    section_id: str | None = None,
) -> list[dict[str, Any]]:
    """列出规则模板（可按 template_type/section_id 筛选）。"""
    q = sa.select(ConsolNoteMappingRuleTemplate).where(
        ConsolNoteMappingRuleTemplate.is_active == sa.true(),
    )
    if template_type:
        q = q.where(ConsolNoteMappingRuleTemplate.template_type == template_type)
    if section_id:
        q = q.where(ConsolNoteMappingRuleTemplate.section_id == section_id)
    q = q.order_by(
        ConsolNoteMappingRuleTemplate.section_id,
        ConsolNoteMappingRuleTemplate.version_number.desc(),
    )
    result = await db.execute(q)
    return [_tmpl_to_dict(t) for t in result.scalars().all()]


async def deactivate_template(
    db: AsyncSession,
    template_id: UUID | str,
) -> dict[str, Any]:
    """停用规则模板（soft delete）。"""
    if isinstance(template_id, str):
        template_id = UUID(template_id)
    tmpl = (await db.execute(
        sa.select(ConsolNoteMappingRuleTemplate).where(
            ConsolNoteMappingRuleTemplate.id == template_id,
        )
    )).scalar_one_or_none()
    if tmpl is None:
        raise MappingTemplateError(404, "TEMPLATE_NOT_FOUND", "规则模板不存在")
    if not tmpl.is_active:
        raise MappingTemplateError(409, "ALREADY_INACTIVE", "规则模板已停用")
    tmpl.is_active = False
    await db.flush()
    return {"action": "deactivated", "template_id": str(tmpl.id)}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 从模板库生成映射建议（US-2 核心）
# ═══════════════════════════════════════════════════════════════════════════════


async def suggest_from_templates(
    db: AsyncSession,
    *,
    template_type: str,
    section_id: str,
    source_groups: list[dict[str, Any]],
    fuzzy_threshold: float = 0.75,
) -> list[dict[str, Any]]:
    """从规则模板库生成映射建议。

    匹配策略：
    1. 精确匹配：source_structure_hash 完全一致 → confidence=0.92
    2. 逐行模糊：hash 不匹配时，逐行用 SequenceMatcher → confidence=max(ratio, threshold)

    返回 ``[{source_label, suggested_target, confidence, match_type, candidates}]``
    """
    # 收集所有来源标签（去重保序）
    all_labels: list[str] = []
    label_hashes: dict[str, str] = {}  # label → 该 label 所在 group 的 hash
    seen: set[str] = set()
    for group in source_groups:
        group_hash = group.get("hash", "")
        for sr in group.get("source_rows", []):
            label = sr.get("label", "").strip()
            if label and label not in seen:
                all_labels.append(label)
                label_hashes[label] = group_hash
                seen.add(label)

    if not all_labels:
        return []

    # 收集所有唯一 hash
    unique_hashes = list({g.get("hash", "") for g in source_groups if g.get("hash")})

    # 精确 hash 匹配
    hash_templates: dict[str, ConsolNoteMappingRuleTemplate] = {}
    if unique_hashes:
        result = await db.execute(
            sa.select(ConsolNoteMappingRuleTemplate).where(
                ConsolNoteMappingRuleTemplate.template_type == template_type,
                ConsolNoteMappingRuleTemplate.section_id == section_id,
                ConsolNoteMappingRuleTemplate.source_structure_hash.in_(unique_hashes),
                ConsolNoteMappingRuleTemplate.is_active == sa.true(),
            )
        )
        for t in result.scalars().all():
            # 同 hash 取最高版本
            existing = hash_templates.get(t.source_structure_hash)
            if existing is None or t.version_number > existing.version_number:
                hash_templates[t.source_structure_hash] = t

    # 所有章节的模板（用于模糊匹配）
    section_templates = await find_templates_for_section(
        db, template_type=template_type, section_id=section_id,
    )

    # 构建模板 mappings 的 source_label → target 索引
    tmpl_label_index: dict[str, dict[str, Any]] = {}
    for tmpl_dict in section_templates:
        for m in tmpl_dict.get("mappings", []):
            sl = str(m.get("source_label", "")).strip()
            if sl and sl not in tmpl_label_index and m.get("target_row_id"):
                tmpl_label_index[sl] = m

    suggestions: list[dict[str, Any]] = []
    for label in all_labels:
        group_hash = label_hashes.get(label, "")

        # 1. 精确 hash 匹配
        if group_hash in hash_templates:
            tmpl = hash_templates[group_hash]
            # 在模板的 mappings 中找这个 label
            mapping_hit = None
            for m in (tmpl.mappings if isinstance(tmpl.mappings, list) else []):
                if str(m.get("source_label", "")).strip() == label:
                    mapping_hit = m
                    break
            if mapping_hit and mapping_hit.get("target_row_id"):
                suggestions.append({
                    "source_label": label,
                    "suggested_target": {
                        "target_row_id": mapping_hit["target_row_id"],
                        "canonical_name": mapping_hit.get("canonical_name"),
                    },
                    "confidence": 0.92,
                    "match_type": "rule_template",
                    "candidates": [],
                    "template_id": str(tmpl.id),
                    "template_version": tmpl.version_number,
                })
                continue

        # 2. 逐行模糊匹配（查所有模板的 mappings）
        best_ratio = 0.0
        best_mapping: dict[str, Any] | None = None
        candidates: list[dict[str, Any]] = []
        for tmpl_label, tmpl_mapping in tmpl_label_index.items():
            ratio = SequenceMatcher(None, label, tmpl_label).ratio()
            if ratio >= fuzzy_threshold:
                candidates.append({
                    "source_label": tmpl_label,
                    "target_row_id": tmpl_mapping.get("target_row_id"),
                    "ratio": round(ratio, 3),
                })
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_mapping = tmpl_mapping

        if best_mapping is not None:
            suggestions.append({
                "source_label": label,
                "suggested_target": {
                    "target_row_id": best_mapping["target_row_id"],
                    "canonical_name": best_mapping.get("canonical_name"),
                },
                "confidence": round(best_ratio, 3),
                "match_type": "rule_template",
                "candidates": candidates,
            })
            continue

        # 未匹配——交给调用方的后续匹配级别
        # 不在此处生成 manual 条目，由 suggest_template_rows 统一兜底

    return suggestions


# ─── 内部辅助 ────────────────────────────────────────────────────────────────


def _tmpl_to_dict(tmpl: ConsolNoteMappingRuleTemplate) -> dict[str, Any]:
    return {
        "id": str(tmpl.id),
        "template_type": tmpl.template_type,
        "section_id": tmpl.section_id,
        "source_structure_hash": tmpl.source_structure_hash,
        "version_number": tmpl.version_number,
        "mappings": tmpl.mappings if isinstance(tmpl.mappings, list) else [],
        "account_code_hints": tmpl.account_code_hints if isinstance(tmpl.account_code_hints, dict) else {},
        "source_project_id": str(tmpl.source_project_id) if tmpl.source_project_id else None,
        "source_rule_id": str(tmpl.source_rule_id) if tmpl.source_rule_id else None,
        "promoted_by": str(tmpl.promoted_by) if tmpl.promoted_by else None,
        "promoted_at": tmpl.promoted_at.isoformat() if tmpl.promoted_at else None,
        "is_active": tmpl.is_active,
    }
