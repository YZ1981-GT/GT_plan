"""底稿版本链核心服务 — VersionTrailService

提供快照创建、列表、详情、diff 对比、回滚、生命周期管理。
所有方法操作 checklist_responses 数据层，不依赖 componentType。

核心规范：
- asyncpg 不支持 IN tuple 参数，必须用 = ANY(:list) + list 类型
- service 只 flush 不 commit（调用者控制事务）
- 自动快照 fire-and-forget：失败仅 warning 不阻塞主流程
- data_json 存储完整 checklist_responses 快照
- 2MB 降级存储仅保留 item_id 列表（无 remark 文本）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import WorkpaperSnapshot
# 🔴 Task 19（workpaper-html-onlyoffice-bidirectional-writeback-closure）：
# `rollback_to_snapshot` 是底稿内容恢复路径，必须与 HTML save 共用同一个业务版本域。
from app.services.workpaper_sync.content_mutation import ROLLBACK, html_only_entry_id
from app.services.workpaper_sync.entry_profile import Capability
from app.services.workpaper_sync.writer_migration import (
    build_content_mutation_service_writer,
)

logger = logging.getLogger(__name__)

# 2MB 阈值
_MAX_DATA_SIZE_BYTES = 2 * 1024 * 1024
# 每底稿最多保留最近 N 个版本（含手动/自动），避免 checklist 快照膨胀
_MAX_SNAPSHOTS_PER_WORKPAPER = 5


# ─── Pydantic Models ──────────────────────────────────────────────────────────


class SnapshotCreate(BaseModel):
    """创建快照请求"""

    snapshot_type: str  # manual/auto/auto_sampling/auto_import/review_sign/status_change/rollback
    description: Optional[str] = None
    change_summary: Optional[str] = None


class SnapshotMeta(BaseModel):
    """快照元数据（列表展示用）"""

    id: UUID
    snapshot_type: str
    description: Optional[str] = None
    change_summary: Optional[str] = None
    item_count: int
    data_size_bytes: int
    user_id: UUID
    user_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SnapshotDetail(BaseModel):
    """快照详情（含完整 data_json）"""

    id: UUID
    snapshot_type: str
    description: Optional[str] = None
    change_summary: Optional[str] = None
    item_count: int
    data_size_bytes: int
    data_json: list[dict] | dict
    user_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class DiffItem(BaseModel):
    """单条 diff 记录"""

    item_id: str
    change_type: str  # added/deleted/modified
    field_name: Optional[str] = None  # conclusion/remark/wp_ref (for modified)
    value_a: Optional[str] = None
    value_b: Optional[str] = None


class DiffResult(BaseModel):
    """diff 对比结果"""

    added: list[DiffItem]
    deleted: list[DiffItem]
    modified: list[DiffItem]
    unchanged_count: int
    summary: str  # "新增2项，删除1项，修改3个字段"


class CompareRequest(BaseModel):
    """对比请求"""

    version_a_id: UUID
    version_b_id: UUID


# ─── Service ──────────────────────────────────────────────────────────────────


class VersionTrailService:
    """底稿版本链核心服务

    提供快照创建、列表、详情、diff、回滚、生命周期管理。
    所有方法为静态方法，无状态，便于内部编程式调用。
    """

    @staticmethod
    async def create_snapshot(
        db: AsyncSession,
        project_id: UUID,
        workpaper_id: UUID,
        user_id: UUID,
        snapshot_type: str,
        description: Optional[str] = None,
        change_summary: Optional[str] = None,
    ) -> SnapshotMeta:
        """创建版本快照

        1. 读取当前所有 checklist_responses WHERE wp_id = workpaper_id
        2. 序列化为 JSON array [{item_id, conclusion, remark, wp_ref}, ...]
        3. 计算 data_size_bytes，若 > 2MB 则降级存储（仅 item_id 列表）
        4. 若无 change_summary 且有上一快照，自动计算 diff summary
        5. 执行生命周期清理（仅保留最近 5 个版本）
        6. INSERT into workpaper_snapshots
        """
        # Step 1: 读取当前 checklist_responses
        query = sa.text(
            "SELECT item_id, conclusion, remark, wp_ref "
            "FROM checklist_responses "
            "WHERE wp_id = :workpaper_id"
        )
        result = await db.execute(query, {"workpaper_id": workpaper_id})
        rows = result.mappings().all()

        # Step 2: 序列化为 JSON array
        data: list[dict] = [
            {
                "item_id": str(row["item_id"]),
                "conclusion": row["conclusion"],
                "remark": row["remark"],
                "wp_ref": row["wp_ref"],
            }
            for row in rows
        ]

        # Step 3: 计算 data_size_bytes
        data_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        data_size_bytes = len(data_bytes)
        item_count = len(data)

        # 2MB 降级存储
        data_json: list[dict] | dict
        if data_size_bytes > _MAX_DATA_SIZE_BYTES:
            logger.warning(
                "Snapshot data exceeds 2MB (%d bytes) for wp_id=%s, degrading storage",
                data_size_bytes,
                workpaper_id,
            )
            data_json = {
                "_degraded": True,
                "item_ids": [d["item_id"] for d in data],
                "item_count": item_count,
                "reason": "data_size_exceeds_2MB",
            }
        else:
            data_json = data

        # Step 4: 自动生成 change_summary（若无 caller 提供且有前一快照）
        if not change_summary:
            prev_query = sa.text(
                "SELECT data_json FROM workpaper_snapshots "
                "WHERE workpaper_id = :workpaper_id "
                "ORDER BY created_at DESC LIMIT 1"
            )
            prev_result = await db.execute(prev_query, {"workpaper_id": workpaper_id})
            prev_row = prev_result.mappings().first()
            if prev_row is not None:
                prev_data = prev_row["data_json"]
                # 仅对非降级数据做 diff
                if isinstance(prev_data, list) and isinstance(data_json, list):
                    diff = VersionTrailService.compute_diff_pure(prev_data, data_json)
                    change_summary = diff.summary

        # Step 5: 生命周期清理
        await VersionTrailService.enforce_lifecycle(db, workpaper_id)

        # Step 6: INSERT
        snapshot = WorkpaperSnapshot(
            project_id=project_id,
            workpaper_id=workpaper_id,
            user_id=user_id,
            snapshot_type=snapshot_type,
            description=description,
            change_summary=change_summary,
            data_json=data_json,
            item_count=item_count,
            data_size_bytes=data_size_bytes,
        )
        db.add(snapshot)
        await db.flush()

        return SnapshotMeta(
            id=snapshot.id,
            snapshot_type=snapshot.snapshot_type,
            description=snapshot.description,
            change_summary=snapshot.change_summary,
            item_count=snapshot.item_count,
            data_size_bytes=snapshot.data_size_bytes,
            user_id=snapshot.user_id,
            created_at=snapshot.created_at,
        )

    @staticmethod
    async def create_snapshot_fire_and_forget(
        db: AsyncSession,
        project_id: UUID,
        workpaper_id: UUID,
        user_id: UUID,
        snapshot_type: str,
        description: Optional[str] = None,
    ) -> Optional[SnapshotMeta]:
        """自动快照（fire-and-forget）

        包裹 create_snapshot，异常仅 log warning 不抛出。
        用于抽凭/导入/签字/状态变更等自动触发场景。
        """
        try:
            return await VersionTrailService.create_snapshot(
                db=db,
                project_id=project_id,
                workpaper_id=workpaper_id,
                user_id=user_id,
                snapshot_type=snapshot_type,
                description=description,
            )
        except Exception:
            logger.warning(
                "自动快照创建失败 (fire-and-forget): wp_id=%s, type=%s",
                workpaper_id,
                snapshot_type,
                exc_info=True,
            )
            return None

    # ─── Stubs for other methods (implemented in tasks 2.2–2.6) ───────────

    @staticmethod
    async def list_snapshots(
        db: AsyncSession,
        workpaper_id: UUID,
        project_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SnapshotMeta], int]:
        """分页获取快照列表（按 created_at DESC）"""
        # COUNT(*) 总数
        count_query = sa.text(
            "SELECT COUNT(*) AS total FROM workpaper_snapshots "
            "WHERE workpaper_id = :workpaper_id AND project_id = :project_id"
        )
        count_result = await db.execute(
            count_query,
            {"workpaper_id": workpaper_id, "project_id": project_id},
        )
        total = count_result.scalar_one()

        # 分页查询
        offset = (page - 1) * page_size
        list_query = sa.text(
            "SELECT id, snapshot_type, description, change_summary, "
            "item_count, data_size_bytes, user_id, created_at "
            "FROM workpaper_snapshots "
            "WHERE workpaper_id = :workpaper_id AND project_id = :project_id "
            "ORDER BY created_at DESC "
            "LIMIT :limit OFFSET :offset"
        )
        list_result = await db.execute(
            list_query,
            {
                "workpaper_id": workpaper_id,
                "project_id": project_id,
                "limit": page_size,
                "offset": offset,
            },
        )
        rows = list_result.mappings().all()

        snapshots = [
            SnapshotMeta(
                id=row["id"],
                snapshot_type=row["snapshot_type"],
                description=row["description"],
                change_summary=row["change_summary"],
                item_count=row["item_count"],
                data_size_bytes=row["data_size_bytes"],
                user_id=row["user_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return snapshots, total

    @staticmethod
    async def get_snapshot_detail(
        db: AsyncSession,
        snapshot_id: UUID,
        project_id: UUID,
    ) -> SnapshotDetail:
        """获取快照详情（含 data_json）

        安全隔离：WHERE id AND project_id 双条件查询。
        """
        from fastapi import HTTPException

        query = sa.text(
            "SELECT id, snapshot_type, description, change_summary, "
            "item_count, data_size_bytes, data_json, user_id, created_at "
            "FROM workpaper_snapshots "
            "WHERE id = :snapshot_id AND project_id = :project_id"
        )
        result = await db.execute(
            query, {"snapshot_id": snapshot_id, "project_id": project_id}
        )
        row = result.mappings().first()

        if row is None:
            raise HTTPException(status_code=404, detail="版本快照不存在")

        return SnapshotDetail(
            id=row["id"],
            snapshot_type=row["snapshot_type"],
            description=row["description"],
            change_summary=row["change_summary"],
            item_count=row["item_count"],
            data_size_bytes=row["data_size_bytes"],
            data_json=row["data_json"],
            user_id=row["user_id"],
            created_at=row["created_at"],
        )

    @staticmethod
    async def compute_diff(
        db: AsyncSession,
        version_a_id: UUID,
        version_b_id: UUID,
        project_id: UUID,
    ) -> DiffResult:
        """计算两个快照间的 field-level diff

        1. 读取两个快照 data_json（安全隔离 project_id）
        2. 验证两者属于同一底稿
        3. 验证两者均为 list 类型（非降级存储）
        4. 调用 compute_diff_pure 生成 DiffResult
        """
        from fastapi import HTTPException

        # 读取快照 A
        query_a = sa.text(
            "SELECT id, workpaper_id, data_json FROM workpaper_snapshots "
            "WHERE id = :snapshot_id AND project_id = :project_id"
        )
        result_a = await db.execute(
            query_a, {"snapshot_id": version_a_id, "project_id": project_id}
        )
        row_a = result_a.mappings().first()
        if row_a is None:
            raise HTTPException(status_code=404, detail="版本快照不存在")

        # 读取快照 B
        result_b = await db.execute(
            query_a, {"snapshot_id": version_b_id, "project_id": project_id}
        )
        row_b = result_b.mappings().first()
        if row_b is None:
            raise HTTPException(status_code=404, detail="版本快照不存在")

        # 验证两者属于同一底稿
        if row_a["workpaper_id"] != row_b["workpaper_id"]:
            raise HTTPException(
                status_code=400, detail="只能对比同一底稿的版本"
            )

        data_a = row_a["data_json"]
        data_b = row_b["data_json"]

        # 验证非降级存储（必须是 list 类型）
        if not isinstance(data_a, list):
            raise HTTPException(
                status_code=400,
                detail="版本A为降级存储，无法进行字段级对比",
            )
        if not isinstance(data_b, list):
            raise HTTPException(
                status_code=400,
                detail="版本B为降级存储，无法进行字段级对比",
            )

        return VersionTrailService.compute_diff_pure(data_a, data_b)

    @staticmethod
    def compute_diff_pure(
        data_a: list[dict],
        data_b: list[dict],
    ) -> DiffResult:
        """纯函数版本 diff（不依赖 DB）

        以 item_id 为 key 构建 dict，对比 conclusion/remark/wp_ref 字段。
        """
        dict_a = {d["item_id"]: d for d in data_a}
        dict_b = {d["item_id"]: d for d in data_b}

        keys_a = set(dict_a.keys())
        keys_b = set(dict_b.keys())

        added_ids = keys_b - keys_a
        deleted_ids = keys_a - keys_b
        common_ids = keys_a & keys_b

        added: list[DiffItem] = [
            DiffItem(item_id=item_id, change_type="added")
            for item_id in sorted(added_ids)
        ]
        deleted: list[DiffItem] = [
            DiffItem(item_id=item_id, change_type="deleted")
            for item_id in sorted(deleted_ids)
        ]

        modified: list[DiffItem] = []
        unchanged_count = 0

        compare_fields = ("conclusion", "remark", "wp_ref")
        for item_id in sorted(common_ids):
            row_a = dict_a[item_id]
            row_b = dict_b[item_id]
            item_modified = False
            for field in compare_fields:
                val_a = row_a.get(field)
                val_b = row_b.get(field)
                if val_a != val_b:
                    modified.append(
                        DiffItem(
                            item_id=item_id,
                            change_type="modified",
                            field_name=field,
                            value_a=str(val_a) if val_a is not None else None,
                            value_b=str(val_b) if val_b is not None else None,
                        )
                    )
                    item_modified = True
            if not item_modified:
                unchanged_count += 1

        # 生成摘要
        parts: list[str] = []
        if added:
            parts.append(f"新增{len(added)}项")
        if deleted:
            parts.append(f"删除{len(deleted)}项")
        if modified:
            parts.append(f"修改{len(modified)}个字段")
        summary = "，".join(parts) if parts else "无变更"

        return DiffResult(
            added=added,
            deleted=deleted,
            modified=modified,
            unchanged_count=unchanged_count,
            summary=summary,
        )

    @staticmethod
    async def _load_restore_scope(db: AsyncSession, workpaper_id: UUID) -> str | None:
        """底稿的稳定业务身份 `wp_code`（`entry_id` 的构造材料）。

        `wp_code` 在 `wp_index`，不在 `working_paper`（本仓库 schema 铁律），所以必须
        JOIN。缺行时返回 `None`，由 `html_only_entry_id` 退回 `wp_id` —— V151 的
        `ck_wpssi_entry_non_empty` 不接受空串，凑一个空字符串会在 DB 层炸成一个看不出
        来源的约束错误。
        """
        row = (await db.execute(sa.text(
            "SELECT wi.wp_code AS wp_code FROM working_paper wp "
            "LEFT JOIN wp_index wi ON wi.id = wp.wp_index_id WHERE wp.id = :wid"
        ), {"wid": str(workpaper_id)})).first()
        return row.wp_code if row is not None else None

    @staticmethod
    async def rollback_to_snapshot(
        db: AsyncSession,
        project_id: UUID,
        workpaper_id: UUID,
        snapshot_id: UUID,
        user_id: UUID,
    ) -> SnapshotMeta:
        """回滚到指定快照

        事务内执行：
        1. 验证 snapshot 属于指定 project_id + workpaper_id
        2. 读取目标快照 data_json
        3. 若为降级存储则拒绝回滚
        4. DELETE FROM checklist_responses WHERE wp_id = workpaper_id
        5. INSERT INTO checklist_responses (from snapshot data_json rows)
        6. 创建新快照 snapshot_type='rollback', description="回滚到{ts}的版本"
        7. 🔴 Task 19：经统一入口提交，恰推进一次 `content_revision`

        ═══ 第 7 步为什么必须存在 ═══

        改造前 1~6 步走完只 `flush()`：底稿的**业务内容已经换了一份**（整份
        `checklist_responses` 被删掉重建），而任何版本读者都看不出区别 —— 没有版本字段
        动过，也没有 immutable content version 记录这次应用。于是并发的编辑器仍按旧
        base 提交，把刚刚回滚掉的结论/备注原样写回去，用户看到「回滚没生效」。

        走 projection lane 而不是 authoritative-bytes lane：这条路径恢复的是结构化行
        （`checklist_responses`），手上没有 OOXML 本体可发布成 representation。
        `capability=single_html` 是本调用点的声明；若该底稿其实已发布过 OO
        representation，`commit_html_projection` 会按数据库事实二次拒绝（背着权威
        OOXML 恢复结构化投影 = Requirement 2.11 禁止的形态）。

        Requirements: 2.2、9.11、12.7；Property 61
        """
        from fastapi import HTTPException

        # Step 1: 验证 snapshot 属于指定 project_id + workpaper_id
        query = sa.text(
            "SELECT id, project_id, workpaper_id, data_json, created_at "
            "FROM workpaper_snapshots "
            "WHERE id = :snapshot_id"
        )
        result = await db.execute(query, {"snapshot_id": snapshot_id})
        snapshot_row = result.mappings().first()

        if snapshot_row is None:
            raise HTTPException(status_code=404, detail="版本快照不存在")

        if snapshot_row["project_id"] != project_id:
            raise HTTPException(status_code=403, detail="无权操作此版本")

        if snapshot_row["workpaper_id"] != workpaper_id:
            raise HTTPException(status_code=403, detail="无权操作此版本")

        # Step 2: 读取目标快照 data_json
        data_json = snapshot_row["data_json"]
        target_created_at = snapshot_row["created_at"]

        # Step 3: 若为降级存储则拒绝回滚
        if isinstance(data_json, dict) and data_json.get("_degraded"):
            raise HTTPException(
                status_code=400,
                detail="该版本为降级存储（数据超过2MB），无法回滚",
            )

        # Step 4: DELETE current checklist_responses
        delete_query = sa.text(
            "DELETE FROM checklist_responses WHERE wp_id = :workpaper_id"
        )
        await db.execute(delete_query, {"workpaper_id": workpaper_id})

        # Step 5: INSERT rows from data_json
        if data_json:
            insert_query = sa.text(
                "INSERT INTO checklist_responses "
                "(project_id, wp_id, item_id, conclusion, remark, wp_ref, "
                "updated_by, created_at, updated_at) "
                "VALUES (:project_id, :wp_id, :item_id, :conclusion, :remark, "
                ":wp_ref, :updated_by, now(), now())"
            )
            params = [
                {
                    "project_id": project_id,
                    "wp_id": workpaper_id,
                    "item_id": row["item_id"],
                    "conclusion": row.get("conclusion"),
                    "remark": row.get("remark"),
                    "wp_ref": row.get("wp_ref"),
                    "updated_by": user_id,
                }
                for row in data_json
            ]
            for param in params:
                await db.execute(insert_query, param)

        # Step 6: 创建新快照 snapshot_type='rollback'
        description = f"回滚到{target_created_at}的版本"

        # 计算新快照的 data_size_bytes
        data_bytes = json.dumps(data_json, ensure_ascii=False).encode("utf-8")
        data_size_bytes = len(data_bytes)
        item_count = len(data_json) if isinstance(data_json, list) else 0

        rollback_snapshot = WorkpaperSnapshot(
            project_id=project_id,
            workpaper_id=workpaper_id,
            user_id=user_id,
            snapshot_type="rollback",
            description=description,
            change_summary=None,
            data_json=data_json,
            item_count=item_count,
            data_size_bytes=data_size_bytes,
        )
        db.add(rollback_snapshot)
        # flush（不是 commit）：`SnapshotMeta` 要回传 DB 生成的 `id` / `created_at`。
        # 它必须发生在唯一提交出口**之前** —— 写在之后就落到下一个事务，而 router 不再
        # 提交一次 ⇒ 回滚快照静默丢失（Requirement 13.1）。
        await db.flush()

        # ─── Step 7: 唯一业务 commit（Requirement 2.2 / Property 61）────────────
        # 本方法自己没有 `db.commit()`、没有任何版本字段赋值：整份 checklist_responses
        # 的删除+重建、rollback 快照行、content version、`content_revision` CAS 与 outbox
        # 同生共死。
        scope = await VersionTrailService._load_restore_scope(db, workpaper_id)
        writer = build_content_mutation_service_writer(db)
        receipt = await writer.commit_projection(
            project_id=project_id,
            wp_id=workpaper_id,
            entry_id=html_only_entry_id(wp_code=scope, wp_id=workpaper_id),
            capability=Capability.single_html,
            # 载荷键名沿用 lane 的 `html_data`（= 「本次业务 projection 内容」），但这条
            # writer 恢复的是 checklist 行而不是 sheet 单元格，所以显式套一层具名键：
            # canonical 载荷进内容寻址 digest，事后必须能看出这份 digest 覆盖的是什么。
            html_data={"checklist_responses": data_json or []},
            expected_revision=await writer.current_revision(workpaper_id),
            source=ROLLBACK,
            actor_id=user_id,
            trigger="version_trail_rollback",
        )
        await writer.publish_committed_events(receipt)

        return SnapshotMeta(
            id=rollback_snapshot.id,
            snapshot_type=rollback_snapshot.snapshot_type,
            description=rollback_snapshot.description,
            change_summary=rollback_snapshot.change_summary,
            item_count=rollback_snapshot.item_count,
            data_size_bytes=rollback_snapshot.data_size_bytes,
            user_id=rollback_snapshot.user_id,
            created_at=rollback_snapshot.created_at,
        )

    @staticmethod
    async def enforce_lifecycle(
        db: AsyncSession,
        workpaper_id: UUID,
        max_snapshots: int = _MAX_SNAPSHOTS_PER_WORKPAPER,
    ) -> int:
        """生命周期管理：仅保留最近 max_snapshots 个版本（按 created_at）。

        创建前若已达上限，删除最旧记录腾出空位（不区分 manual/auto）。
        返回被清理的数量。
        """
        count_query = sa.text(
            "SELECT COUNT(*) AS cnt FROM workpaper_snapshots "
            "WHERE workpaper_id = :workpaper_id"
        )
        count_result = await db.execute(count_query, {"workpaper_id": workpaper_id})
        count_row = count_result.mappings().first()
        current_count = int(count_row["cnt"] if count_row else 0)

        if current_count < max_snapshots:
            return 0

        # 即将再插入 1 条：至少腾 1 个空位；若历史已超限则一并压回
        excess = current_count - max_snapshots + 1

        delete_query = sa.text(
            "DELETE FROM workpaper_snapshots "
            "WHERE id IN ("
            "  SELECT id FROM workpaper_snapshots "
            "  WHERE workpaper_id = :workpaper_id "
            "  ORDER BY created_at ASC "
            "  LIMIT :excess"
            ")"
        )
        await db.execute(
            delete_query, {"workpaper_id": workpaper_id, "excess": excess}
        )
        await db.flush()

        logger.info(
            "Lifecycle cleanup: removed %d snapshots for wp_id=%s (keep newest %d)",
            excess,
            workpaper_id,
            max_snapshots,
        )
        return excess
