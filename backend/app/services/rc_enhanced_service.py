"""Phase 15: 复核对话增强服务

对齐 v2 5.9.14~5.9.17:
- 关闭态消息写入阻断
- 参与者管理
- 取证导出留痕
"""
import uuid
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trace_event_service import trace_event_service, generate_trace_id

logger = logging.getLogger(__name__)


class RCEnhancedService:
    """复核对话增强服务"""

    async def check_closed_state_guard(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        message_type: str,
    ) -> None:
        """关闭态消息写入阻断（对齐 v2 5.9.16.5）

        status IN ('closed','resolved') 且 message_type='text' → 422
        """
        stmt = text("""
            SELECT status FROM review_conversations WHERE id = :cid LIMIT 1
        """)
        result = await db.execute(stmt, {"cid": str(conversation_id)})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="RC_NOT_FOUND")

        status = row[0]
        if status in ("closed", "resolved") and message_type == "text":
            raise HTTPException(status_code=422, detail={
                "error_code": "RC_CONVERSATION_CLOSED",
                "message": "会话已关闭，禁止发送普通消息",
                "recommended_action": "请创建新会话或申请重开",
            })

    async def add_participant(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        is_required_ack: bool = False,
    ) -> dict:
        """添加参与者（对齐 v2 5.9.16.1）"""
        # 检查是否已存在
        stmt = text("""
            SELECT id FROM review_conversation_participants
            WHERE conversation_id = :cid AND user_id = :uid AND is_deleted = false
            LIMIT 1
        """)
        result = await db.execute(stmt, {"cid": str(conversation_id), "uid": str(user_id)})
        if result.fetchone():
            return {"status": "already_exists"}

        participant_id = uuid.uuid4()
        stmt = text("""
            INSERT INTO review_conversation_participants
            (id, conversation_id, user_id, participant_role, is_required_ack, joined_at, is_deleted, created_at, updated_at)
            VALUES (:id, :cid, :uid, :role, :ack, NOW(), false, NOW(), NOW())
        """)
        await db.execute(stmt, {
            "id": str(participant_id),
            "cid": str(conversation_id),
            "uid": str(user_id),
            "role": role,
            "ack": is_required_ack,
        })
        await db.flush()
        return {"id": str(participant_id), "status": "added"}

    async def remove_participant(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """移除参与者（软删除）"""
        stmt = text("""
            UPDATE review_conversation_participants
            SET is_deleted = true, left_at = NOW(), updated_at = NOW()
            WHERE conversation_id = :cid AND user_id = :uid AND is_deleted = false
        """)
        await db.execute(stmt, {"cid": str(conversation_id), "uid": str(user_id)})
        await db.flush()

    async def export_evidence(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        purpose: str,
        receiver: str,
        export_scope: str,
        mask_policy: str,
        include_hash_manifest: bool,
        requested_by: uuid.UUID,
    ) -> dict:
        """取证导出（对齐 v2 5.9.14.6）"""
        # 必填校验
        if not purpose or not receiver or not mask_policy:
            raise HTTPException(status_code=400, detail={
                "error_code": "RC_REQUIRED_FIELD_MISSING",
                "message": "导出必须填写 purpose/receiver/mask_policy",
            })

        # 获取会话信息
        stmt = text("SELECT project_id FROM review_conversations WHERE id = :cid")
        result = await db.execute(stmt, {"cid": str(conversation_id)})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="RC_NOT_FOUND")
        project_id = row[0]

        # 构建导出内容（简化：序列化消息列表）
        msg_stmt = text("""
            SELECT id, sender_id, content, message_type, created_at
            FROM review_messages
            WHERE conversation_id = :cid
            ORDER BY created_at ASC
        """)
        msg_result = await db.execute(msg_stmt, {"cid": str(conversation_id)})
        messages = msg_result.fetchall()

        export_content = json.dumps([
            {"id": str(m[0]), "sender": str(m[1]), "content": m[2], "type": m[3], "at": str(m[4])}
            for m in messages
        ], ensure_ascii=False)

        file_hash = hashlib.sha256(export_content.encode()).hexdigest()
        export_id = f"exp_rc_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        trace_id = generate_trace_id()

        # 写入 review_conversation_exports
        stmt = text("""
            INSERT INTO review_conversation_exports
            (id, export_id, conversation_id, project_id, requested_by,
             export_scope, purpose, receiver, mask_policy, include_hash_manifest,
             file_hash, trace_id, status, created_at)
            VALUES (:id, :eid, :cid, :pid, :rby,
                    :scope, :purpose, :receiver, :mask, :hash_flag,
                    :fhash, :tid, 'ready', NOW())
        """)
        await db.execute(stmt, {
            "id": str(uuid.uuid4()),
            "eid": export_id,
            "cid": str(conversation_id),
            "pid": str(project_id),
            "rby": str(requested_by),
            "scope": export_scope,
            "purpose": purpose,
            "receiver": receiver,
            "mask": mask_policy,
            "hash_flag": include_hash_manifest,
            "fhash": file_hash,
            "tid": trace_id,
        })
        await db.flush()

        # 写 trace_events
        await trace_event_service.write(
            db=db,
            project_id=project_id,
            event_type="rc_evidence_exported",
            object_type="conversation",
            object_id=conversation_id,
            actor_id=requested_by,
            action=f"export_evidence:{export_scope}",
            reason_code="RC_EXPORT_EVIDENCE",
            trace_id=trace_id,
        )

        return {
            "export_id": export_id,
            "file_url": f"/api/exports/{export_id}/download",
            "hash": file_hash,
            "trace_id": trace_id,
        }


rc_enhanced_service = RCEnhancedService()
