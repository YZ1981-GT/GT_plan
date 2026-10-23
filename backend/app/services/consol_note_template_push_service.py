"""集团级附注披露模板下推服务。

合并负责人在合并项目中定义集团模板后，下推到各子企业项目的 disclosure_notes，
预生成行骨架（固定行 + 可选行 + 动态行区），子企业在骨架上填数。

spec: consol-note-template-push-to-subsidiaries
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

VALID_CATEGORIES = ("required", "optional", "dynamic_zone")


# ── 结果 ──


@dataclass
class EntityResult:
    node_key: str
    project_id: UUID | None
    company_name: str = ""
    status: str = "pending"  # success / skipped / failed
    reason: str | None = None


@dataclass
class PushResult:
    section_id: str
    entity_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    skip_count: int = 0
    entities: list[EntityResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "entity_count": self.entity_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "skip_count": self.skip_count,
            "entities": [
                {"node_key": e.node_key, "status": e.status, "reason": e.reason,
                 "company_name": e.company_name}
                for e in self.entities
            ],
        }


# ── 骨架构建 ──


def build_skeleton_rows(template_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从模板行构建子企业附注骨架行。

    固定行 / 可选行 → 带 ``_pushed_row_id`` 标记的空值行；
    dynamic_zone → ``dynamic_zone_marker`` 占位行。
    """
    rows: list[dict[str, Any]] = []
    for tr in template_rows:
        category = tr.get("category", "required")
        rid = tr.get("target_row_id", "")
        if category == "dynamic_zone":
            rows.append({
                "label": "",
                "values": [],
                "row_type": "dynamic_zone_marker",
                "_pushed_row_id": rid,
            })
            continue
        row: dict[str, Any] = {
            "label": tr.get("canonical_name", ""),
            "values": [],
            "row_type": tr.get("row_type", "data"),
            "_pushed_row_id": rid,
            "_pushed_category": category,
        }
        if category == "optional":
            row["_pushed_optional_active"] = True
        rows.append(row)
    return rows


def merge_rows(
    template_rows: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """增量合并：模板行 + 子企业已有行。

    - 有 ``_pushed_row_id`` 匹配的现有行：保留金额，更新行名
    - 模板新增行：插入空值行
    - 用户新增行（无 ``_pushed_row_id``）：放在动态行区（或末尾）
    """
    existing_by_id: dict[str, dict[str, Any]] = {}
    user_added: list[dict[str, Any]] = []
    for r in existing_rows:
        rid = r.get("_pushed_row_id")
        if rid:
            existing_by_id[rid] = r
        else:
            user_added.append(r)

    merged: list[dict[str, Any]] = []
    user_inserted = False

    for tr in template_rows:
        rid = tr.get("target_row_id", "")
        category = tr.get("category", "required")

        if category == "dynamic_zone":
            # 动态行区：插入用户新增的行 + 占位标记
            if not user_inserted:
                merged.extend(user_added)
                user_inserted = True
            merged.append({
                "label": "",
                "values": [],
                "row_type": "dynamic_zone_marker",
                "_pushed_row_id": rid,
            })
            continue

        existing = existing_by_id.get(rid)
        if existing:
            # 保留已有金额，更新行名和类别
            existing["label"] = tr.get("canonical_name", existing.get("label", ""))
            existing["_pushed_category"] = category
            if category == "optional" and "_pushed_optional_active" not in existing:
                existing["_pushed_optional_active"] = True
            merged.append(existing)
        else:
            # 新增行
            row: dict[str, Any] = {
                "label": tr.get("canonical_name", ""),
                "values": [],
                "row_type": tr.get("row_type", "data"),
                "_pushed_row_id": rid,
                "_pushed_category": category,
            }
            if category == "optional":
                row["_pushed_optional_active"] = True
            merged.append(row)

    # 剩余用户行追加末尾
    if not user_inserted:
        merged.extend(user_added)

    return merged


# ── 下推主流程 ──


async def push_template_to_subsidiaries(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str,
    year: int,
    template_version_id: UUID,
    pushed_by: UUID | None = None,
    activate_lock: bool = True,
) -> PushResult:
    """下推集团模板到各子企业。

    1. 加载模板版本
    2. 遍历企业树数据叶子
    3. 逐家写骨架 / 增量合并
    4. 可选：激活结构锁
    5. 记录日志
    """
    from app.models.consol_note_mapping_models import ConsolNoteDetailTemplateVersion

    # 1. 加载模板
    version = (await db.execute(
        sa.select(ConsolNoteDetailTemplateVersion).where(
            ConsolNoteDetailTemplateVersion.id == template_version_id,
        )
    )).scalar_one_or_none()
    if version is None:
        raise ValueError(f"模板版本 {template_version_id} 不存在")

    template_rows: list[dict[str, Any]] = version.rows if isinstance(version.rows, list) else []
    if not template_rows:
        raise ValueError("模板没有行定义")

    # 2. 遍历企业树
    from app.services.consol_calc_basis import data_leaves
    from app.services.consol_tree_service import build_tree

    tree = await build_tree(db, consol_project_id)
    if tree is None:
        raise ValueError("无法构建企业树")

    leaves = [leaf for leaf in data_leaves(tree) if leaf.project_id is not None]
    result = PushResult(section_id=section_id, entity_count=len(leaves))

    # 3. 逐家下推
    for leaf in leaves:
        er = EntityResult(
            node_key=leaf.node_key,
            project_id=leaf.project_id,
            company_name=getattr(leaf, "company_name", "") or "",
        )
        try:
            await _push_to_one(db, leaf.project_id, section_id, year, template_rows)
            er.status = "success"
            result.success_count += 1
        except Exception as exc:
            logger.warning("下推到 %s 失败: %s", leaf.node_key, exc)
            er.status = "failed"
            er.reason = str(exc)[:200]
            result.failure_count += 1
        result.entities.append(er)

    # 4. 激活结构锁（锁固定行）
    if activate_lock and result.success_count > 0:
        try:
            await _activate_structure_lock(
                db, consol_project_id, section_id, template_version_id, leaves, pushed_by,
            )
        except Exception as exc:
            logger.warning("激活结构锁失败: %s", exc)

    # 5. 记录日志
    await _record_push_log(
        db, consol_project_id, section_id, template_version_id,
        pushed_by, result,
    )
    await db.flush()

    return result


async def _push_to_one(
    db: AsyncSession,
    project_id: UUID,
    section_id: str,
    year: int,
    template_rows: list[dict[str, Any]],
) -> None:
    """向一家子企业下推骨架。"""
    from app.models.disclosure_note_models import DisclosureNote
    from app.services.consol_note_section_mapping import resolve_mapping_entry

    # 按模板类型查子企业的附注模板口径
    entry = resolve_mapping_entry("soe", section_id) or resolve_mapping_entry("listed", section_id)
    standalone_section = (entry or {}).get("standalone_note_section") or section_id

    note = (await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == standalone_section,
            DisclosureNote.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()

    if note is None:
        # 新建骨架
        skeleton = build_skeleton_rows(template_rows)
        table_data = {
            "_tables": [{
                "name": (entry or {}).get("consol_title") or section_id,
                "headers": ["项目"],
                "rows": skeleton,
            }],
        }
        new_note = DisclosureNote(
            project_id=project_id,
            year=year,
            note_section=standalone_section,
            section_title=(entry or {}).get("standalone_section_title") or "",
            table_data=table_data,
            is_empty=False,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(new_note)
    else:
        # 增量合并
        td = note.table_data if isinstance(note.table_data, dict) else {}
        tables = td.get("_tables") or []
        if tables and isinstance(tables[0], dict):
            existing_rows = tables[0].get("rows") or []
            tables[0]["rows"] = merge_rows(template_rows, existing_rows)
        else:
            # 没有 _tables：创建
            skeleton = build_skeleton_rows(template_rows)
            td["_tables"] = [{
                "name": (entry or {}).get("consol_title") or section_id,
                "headers": ["项目"],
                "rows": skeleton,
            }]
        note.table_data = td
        note.updated_at = datetime.now(timezone.utc)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(note, "table_data")

    await db.flush()


async def _activate_structure_lock(
    db: AsyncSession,
    consol_project_id: UUID,
    section_id: str,
    template_version_id: UUID,
    leaves: list[Any],
    locked_by: UUID | None,
) -> None:
    """激活结构锁——复用 V200 consol_note_structure_lock 表。"""
    try:
        from app.models.consol_note_mapping_models import (
            ConsolNoteStructureLock,
            ConsolNoteStructureLockEntity,
        )
    except ImportError:
        logger.info("结构锁模型未导入，跳过激活")
        return

    # 查现有锁
    existing = (await db.execute(
        sa.select(ConsolNoteStructureLock).where(
            ConsolNoteStructureLock.consol_project_id == consol_project_id,
            ConsolNoteStructureLock.section_id == section_id,
            ConsolNoteStructureLock.is_active == sa.true(),
        )
    )).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing is not None:
        # 更新版本
        existing.locked_version_id = template_version_id
        existing.locked_by = locked_by
        existing.locked_at = now
    else:
        lock = ConsolNoteStructureLock(
            consol_project_id=consol_project_id,
            section_id=section_id,
            locked_version_id=template_version_id,
            lock_scope="rows_only",
            locked_by=locked_by,
            locked_at=now,
            is_active=True,
        )
        db.add(lock)
        await db.flush()

        # 展开关联企业
        for leaf in leaves:
            if leaf.project_id is not None:
                db.add(ConsolNoteStructureLockEntity(
                    lock_id=lock.id,
                    entity_project_id=leaf.project_id,
                    entity_node_key=leaf.node_key,
                ))

    await db.flush()


async def _record_push_log(
    db: AsyncSession,
    consol_project_id: UUID,
    section_id: str,
    template_version_id: UUID,
    pushed_by: UUID | None,
    result: PushResult,
) -> None:
    """记录下推日志。"""
    failures = [
        {"node_key": e.node_key, "reason": e.reason}
        for e in result.entities if e.status == "failed"
    ]
    await db.execute(
        sa.text("""
            INSERT INTO consol_note_template_push_log
            (consol_project_id, section_id, template_version_id, pushed_by,
             entity_count, success_count, failure_count, failures)
            VALUES (:pid, :sid, :tvid, :by, :ec, :sc, :fc, :f::jsonb)
        """),
        {
            "pid": consol_project_id,
            "sid": section_id,
            "tvid": template_version_id,
            "by": pushed_by,
            "ec": result.entity_count,
            "sc": result.success_count,
            "fc": result.failure_count,
            "f": __import__("json").dumps(failures, ensure_ascii=False),
        },
    )
