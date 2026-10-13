"""合并附注映射规则 CRUD、confirm_mapping 与 stale 检测 service（Phase 3 Task 15~21）。

spec: consol-note-detail-template-and-mapping

Service 只 flush 不 commit（router 层 commit）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_note_mapping_models import (
    ConsolNoteDetailTemplateVersion,
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)

logger = logging.getLogger(__name__)


# ─── 错误 ────────────────────────────────────────────────────────────────────


class MappingRuleError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 映射规则 CRUD（Task 15）
# ═══════════════════════════════════════════════════════════════════════════════


async def create_rule(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    template_version_id: UUID,
    source_structure_hash: str,
    mappings: list[dict[str, Any]],
    confirmed_by: UUID | None = None,
) -> dict[str, Any]:
    """创建映射规则（v1）。"""
    _validate_hash(source_structure_hash)
    _validate_mappings(mappings)
    await _verify_template_version(db, template_version_id)

    rule = ConsolNoteMappingRule(
        project_id=project_id,
        section_id=section_id,
        template_version_id=template_version_id,
        source_structure_hash=source_structure_hash,
        version_number=1,
        mappings=mappings,
        confirmed_by=confirmed_by,
        confirmed_at=datetime.now(timezone.utc) if confirmed_by else None,
        is_active=True,
    )
    db.add(rule)
    await db.flush()
    return _rule_to_dict(rule)


async def upgrade_version(
    db: AsyncSession,
    rule_id: UUID,
    *,
    mappings: list[dict[str, Any]],
    confirmed_by: UUID | None = None,
) -> dict[str, Any]:
    """升版映射规则：停用旧版，创建新版。"""
    old = await _load_active_rule(db, rule_id)
    if old is None:
        raise MappingRuleError(404, "RULE_NOT_FOUND", "映射规则不存在或已停用")
    _validate_mappings(mappings)

    # 停用旧版
    old.is_active = False
    await db.flush()

    now = datetime.now(timezone.utc)
    new_rule = ConsolNoteMappingRule(
        project_id=old.project_id,
        section_id=old.section_id,
        template_version_id=old.template_version_id,
        source_structure_hash=old.source_structure_hash,
        version_number=old.version_number + 1,
        mappings=mappings,
        confirmed_by=confirmed_by,
        confirmed_at=now if confirmed_by else None,
        is_active=True,
    )
    db.add(new_rule)
    await db.flush()

    # 更新引用旧规则的绑定 → 指向新规则
    bindings = (await db.execute(
        sa.select(ConsolNoteMappingBinding).where(
            ConsolNoteMappingBinding.rule_id == old.id,
        )
    )).scalars().all()
    for b in bindings:
        b.rule_id = new_rule.id
    if bindings:
        await db.flush()

    return _rule_to_dict(new_rule)


async def deactivate_rule(
    db: AsyncSession,
    rule_id: UUID,
) -> dict[str, Any]:
    """停用映射规则（不物理删除）。"""
    rule = await _load_active_rule(db, rule_id)
    if rule is None:
        raise MappingRuleError(404, "RULE_NOT_FOUND", "映射规则不存在或已停用")
    rule.is_active = False
    await db.flush()
    return {"id": str(rule_id), "deactivated": True}


async def get_rule_versions(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    source_structure_hash: str | None = None,
) -> list[dict[str, Any]]:
    """获取规则版本历史（含已停用）。"""
    q = sa.select(ConsolNoteMappingRule).where(
        ConsolNoteMappingRule.project_id == project_id,
        ConsolNoteMappingRule.section_id == section_id,
    )
    if source_structure_hash:
        q = q.where(ConsolNoteMappingRule.source_structure_hash == source_structure_hash)
    q = q.order_by(ConsolNoteMappingRule.version_number.desc())
    result = await db.execute(q)
    return [_rule_to_dict(r) for r in result.scalars().all()]


async def get_active_rules(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str | None = None,
) -> list[dict[str, Any]]:
    """列出项目的活跃规则。"""
    q = sa.select(ConsolNoteMappingRule).where(
        ConsolNoteMappingRule.project_id == project_id,
        ConsolNoteMappingRule.is_active == sa.true(),
    )
    if section_id:
        q = q.where(ConsolNoteMappingRule.section_id == section_id)
    q = q.order_by(ConsolNoteMappingRule.section_id, ConsolNoteMappingRule.version_number.desc())
    result = await db.execute(q)
    return [_rule_to_dict(r) for r in result.scalars().all()]


async def get_active_rule_for_hash(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    source_structure_hash: str,
) -> ConsolNoteMappingRule | None:
    """按结构指纹查找活跃规则。"""
    return (await db.execute(
        sa.select(ConsolNoteMappingRule).where(
            ConsolNoteMappingRule.project_id == project_id,
            ConsolNoteMappingRule.section_id == section_id,
            ConsolNoteMappingRule.source_structure_hash == source_structure_hash,
            ConsolNoteMappingRule.is_active == sa.true(),
        ).order_by(ConsolNoteMappingRule.version_number.desc()).limit(1)
    )).scalar_one_or_none()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. confirm_mapping（Task 17~20）
# ═══════════════════════════════════════════════════════════════════════════════


async def confirm_mapping(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    year: int,
    template_version_id: UUID,
    source_structure_hash: str,
    mappings: list[dict[str, Any]],
    entity_node_keys: list[dict[str, Any]],
    excluded_node_keys: list[str] | None = None,
    confirmed_by: UUID | None = None,
    preview_token: str | None = None,
    current_entity_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """确认映射——校验 + 写规则 + 批量绑定。

    Args:
        entity_node_keys: ``[{node_key, project_id, hash}]`` 要绑定的企业列表
        excluded_node_keys: 排除的企业 node_key 列表
        current_entity_hashes: ``{node_key: current_hash}``，用于 409 校验
    """
    _validate_hash(source_structure_hash)
    _validate_mappings(mappings)
    await _verify_template_version(db, template_version_id)

    # 校验模板版本与项目绑定一致
    binding = (await db.execute(
        sa.select(ConsolNoteTemplateBinding).where(
            ConsolNoteTemplateBinding.project_id == project_id,
            ConsolNoteTemplateBinding.section_id == section_id,
        )
    )).scalar_one_or_none()
    if binding is not None and str(binding.template_version_id) != str(template_version_id):
        raise MappingRuleError(
            409, "TEMPLATE_VERSION_CONFLICT",
            "模板版本已变化，请重新预览",
            {"bound": str(binding.template_version_id), "requested": str(template_version_id)},
        )

    # 校验来源结构是否在 preview 后变化
    if current_entity_hashes:
        for ent in entity_node_keys:
            nk = ent["node_key"]
            current = current_entity_hashes.get(nk)
            if current and current != source_structure_hash:
                raise MappingRuleError(
                    409, "SOURCE_STRUCTURE_CONFLICT",
                    f"企业 {nk} 的来源结构已变化，请重新预览",
                    {"node_key": nk, "expected": source_structure_hash, "actual": current},
                )

    excluded = set(excluded_node_keys or [])

    # 查找或创建规则
    existing = await get_active_rule_for_hash(
        db, project_id=project_id, section_id=section_id,
        source_structure_hash=source_structure_hash,
    )
    now = datetime.now(timezone.utc)
    if existing is not None:
        # 升版：停用旧版，将指向旧版的绑定迁移到新版
        old_rule_id = existing.id
        existing.is_active = False
        await db.flush()
        rule = ConsolNoteMappingRule(
            project_id=project_id,
            section_id=section_id,
            template_version_id=template_version_id,
            source_structure_hash=source_structure_hash,
            version_number=existing.version_number + 1,
            mappings=mappings,
            confirmed_by=confirmed_by,
            confirmed_at=now,
            is_active=True,
        )
        db.add(rule)
        await db.flush()
        # 迁移引用旧规则的绑定（本次未传入的企业）
        incoming_keys = {ent["node_key"] for ent in entity_node_keys}
        orphan_bindings = (await db.execute(
            sa.select(ConsolNoteMappingBinding).where(
                ConsolNoteMappingBinding.rule_id == old_rule_id,
            )
        )).scalars().all()
        for ob in orphan_bindings:
            if ob.entity_node_key not in incoming_keys:
                ob.rule_id = rule.id
        if orphan_bindings:
            await db.flush()
    else:
        rule = ConsolNoteMappingRule(
            project_id=project_id,
            section_id=section_id,
            template_version_id=template_version_id,
            source_structure_hash=source_structure_hash,
            version_number=1,
            mappings=mappings,
            confirmed_by=confirmed_by,
            confirmed_at=now,
            is_active=True,
        )
        db.add(rule)
        await db.flush()

    # 批量绑定
    bound_count = 0
    excluded_count = 0
    for ent in entity_node_keys:
        nk = ent["node_key"]
        if nk in excluded:
            excluded_count += 1
            # 标记 excluded
            existing_binding = (await db.execute(
                sa.select(ConsolNoteMappingBinding).where(
                    ConsolNoteMappingBinding.project_id == project_id,
                    ConsolNoteMappingBinding.section_id == section_id,
                    ConsolNoteMappingBinding.entity_node_key == nk,
                )
            )).scalar_one_or_none()
            if existing_binding is not None:
                existing_binding.status = "excluded"
                await db.flush()
            continue

        entity_pid = UUID(ent["project_id"]) if isinstance(ent["project_id"], str) else ent["project_id"]
        entity_hash = ent.get("hash", source_structure_hash)

        existing_binding = (await db.execute(
            sa.select(ConsolNoteMappingBinding).where(
                ConsolNoteMappingBinding.project_id == project_id,
                ConsolNoteMappingBinding.section_id == section_id,
                ConsolNoteMappingBinding.entity_node_key == nk,
            )
        )).scalar_one_or_none()

        if existing_binding is not None:
            existing_binding.rule_id = rule.id
            existing_binding.bound_source_hash = entity_hash
            existing_binding.status = "confirmed"
            existing_binding.bound_at = now
        else:
            db.add(ConsolNoteMappingBinding(
                project_id=project_id,
                section_id=section_id,
                entity_node_key=nk,
                entity_project_id=entity_pid,
                rule_id=rule.id,
                bound_source_hash=entity_hash,
                status="confirmed",
                bound_at=now,
            ))
        bound_count += 1

    await db.flush()

    return {
        "action": "confirmed",
        "rule_id": str(rule.id),
        "version_number": rule.version_number,
        "bound_count": bound_count,
        "excluded_count": excluded_count,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. stale 检测（Task 18）
# ═══════════════════════════════════════════════════════════════════════════════


async def detect_stale_bindings(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    current_hashes: dict[str, str],
) -> list[dict[str, Any]]:
    """比较所有绑定的 bound_source_hash 与当前 hash，批量标记 stale。

    Args:
        current_hashes: ``{entity_node_key: current_source_structure_hash}``

    Returns:
        变为 stale 的绑定列表
    """
    bindings = (await db.execute(
        sa.select(ConsolNoteMappingBinding).where(
            ConsolNoteMappingBinding.project_id == project_id,
            ConsolNoteMappingBinding.section_id == section_id,
            ConsolNoteMappingBinding.status == "confirmed",
        )
    )).scalars().all()

    stale_list: list[dict[str, Any]] = []
    for b in bindings:
        current = current_hashes.get(b.entity_node_key)
        if current is None:
            # 企业不再在合并范围内——跳过，不标 stale。
            # 该企业的绑定在 apply 时自然不会参与汇总（只处理 confirmed 绑定 + 当前范围内的企业）。
            continue
        if current != b.bound_source_hash:
            b.status = "stale"
            stale_list.append({
                "entity_node_key": b.entity_node_key,
                "old_hash": b.bound_source_hash,
                "new_hash": current,
            })

    if stale_list:
        await db.flush()
    return stale_list


async def get_binding_status_summary(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str | None = None,
) -> list[dict[str, Any]]:
    """获取绑定状态汇总。"""
    q = sa.select(ConsolNoteMappingBinding).where(
        ConsolNoteMappingBinding.project_id == project_id,
    )
    if section_id:
        q = q.where(ConsolNoteMappingBinding.section_id == section_id)
    bindings = (await db.execute(q)).scalars().all()
    return [_binding_to_dict(b) for b in bindings]


# ─── 内部辅助 ────────────────────────────────────────────────────────────────


def _validate_hash(h: str) -> None:
    if not h or len(h) != 64:
        raise MappingRuleError(400, "INVALID_HASH", "source_structure_hash 必须是 64 位十六进制")
    try:
        int(h, 16)
    except ValueError:
        raise MappingRuleError(400, "INVALID_HASH", "source_structure_hash 必须是 64 位十六进制")


def _validate_mappings(mappings: list[dict[str, Any]]) -> None:
    if not isinstance(mappings, list):
        raise MappingRuleError(400, "INVALID_MAPPINGS", "mappings 必须是数组")
    valid_actions = {"map", "map_merge", "create", "ignore"}
    for i, m in enumerate(mappings):
        if not isinstance(m, dict):
            raise MappingRuleError(400, "INVALID_MAPPING", f"第 {i+1} 条映射不是对象")
        action = m.get("mapping_action", "")
        if action not in valid_actions:
            raise MappingRuleError(400, "INVALID_ACTION", f"第 {i+1} 条映射 action '{action}' 无效，允许 {valid_actions}")
        if action == "ignore" and not m.get("ignore_reason"):
            raise MappingRuleError(400, "MISSING_IGNORE_REASON", f"第 {i+1} 条映射 action=ignore 必须提供 ignore_reason")
        if action in ("map", "map_merge") and not m.get("target_row_id"):
            raise MappingRuleError(400, "MISSING_TARGET", f"第 {i+1} 条映射 action={action} 必须提供 target_row_id")


async def _verify_template_version(db: AsyncSession, vid: UUID) -> None:
    v = (await db.execute(
        sa.select(ConsolNoteDetailTemplateVersion).where(
            ConsolNoteDetailTemplateVersion.id == vid,
        )
    )).scalar_one_or_none()
    if v is None:
        raise MappingRuleError(404, "VERSION_NOT_FOUND", "模板版本不存在")


async def _load_active_rule(db: AsyncSession, rule_id: UUID) -> ConsolNoteMappingRule | None:
    return (await db.execute(
        sa.select(ConsolNoteMappingRule).where(
            ConsolNoteMappingRule.id == rule_id,
            ConsolNoteMappingRule.is_active == sa.true(),
        )
    )).scalar_one_or_none()


def _rule_to_dict(r: ConsolNoteMappingRule) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "project_id": str(r.project_id),
        "section_id": r.section_id,
        "template_version_id": str(r.template_version_id),
        "source_structure_hash": r.source_structure_hash,
        "version_number": r.version_number,
        "mappings": r.mappings if isinstance(r.mappings, list) else [],
        "confirmed_by": str(r.confirmed_by) if r.confirmed_by else None,
        "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
        "is_active": r.is_active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _binding_to_dict(b: ConsolNoteMappingBinding) -> dict[str, Any]:
    return {
        "id": str(b.id),
        "project_id": str(b.project_id),
        "section_id": b.section_id,
        "entity_node_key": b.entity_node_key,
        "entity_project_id": str(b.entity_project_id),
        "rule_id": str(b.rule_id),
        "bound_source_hash": b.bound_source_hash,
        "status": b.status,
        "bound_at": b.bound_at.isoformat() if b.bound_at else None,
    }
