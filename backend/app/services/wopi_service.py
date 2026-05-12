"""WOPI Host 服务 — 文件元信息查询、读取、写入、锁管理、访问令牌

保留向后兼容（底稿编辑已迁移至 Univer 纯前端方案）。
企业级实现：
- check_file_info: 从 working_paper 表获取元数据
- get_file: 从本地磁盘读取底稿文件
- put_file: 企业级保存（锁校验→版本快照→写入→哈希校验→DB更新→审计留痕→事件发布）
- lock/unlock/refresh_lock: Redis 优先 + 内存降级
- generate_access_token / validate_access_token: 复用 JWT 模块
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.config import settings
from app.models.workpaper_models import WorkingPaper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lock store — Redis 分布式锁（生产环境）+ 内存锁（降级/开发环境）
# Phase 9 Task 9.3: 从纯内存锁升级为 Redis 分布式锁
# ---------------------------------------------------------------------------

_locks: dict[str, dict[str, Any]] = {}
_LOCK_TTL_SECONDS = 30 * 60  # 30 minutes
_MAX_CONCURRENT_EDITORS = 5  # 同一底稿最大并发编辑人数

_redis_client = None

def _get_redis():
    """延迟获取 Redis 客户端"""
    global _redis_client
    if _redis_client is None:
        try:
            from app.core.redis import redis_client
            _redis_client = redis_client
        except Exception:
            _redis_client = False  # 标记不可用
    return _redis_client if _redis_client is not False else None

async def _redis_lock(file_key: str, lock_id: str) -> dict:
    """Redis 分布式锁实现"""
    r = _get_redis()
    if not r:
        return {"fallback": True}
    try:
        key = f"wopi:lock:{file_key}"
        existing = await r.get(key)
        if existing:
            existing_id = existing.decode() if isinstance(existing, bytes) else existing
            if existing_id != lock_id:
                return {"success": False, "status": 409, "existing_lock": existing_id, "message": "文件已被其他用户锁定"}
        await r.set(key, lock_id, ex=_LOCK_TTL_SECONDS)
        return {"success": True, "message": "锁定成功（Redis）"}
    except Exception:
        return {"fallback": True}

async def _redis_unlock(file_key: str, lock_id: str) -> dict:
    """Redis 解锁"""
    r = _get_redis()
    if not r:
        return {"fallback": True}
    try:
        key = f"wopi:lock:{file_key}"
        existing = await r.get(key)
        if existing:
            existing_id = existing.decode() if isinstance(existing, bytes) else existing
            if existing_id != lock_id:
                return {"success": False, "status": 409, "existing_lock": existing_id, "message": "lock_id 不匹配"}
        await r.delete(key)
        return {"success": True, "message": "锁已释放（Redis）"}
    except Exception:
        return {"fallback": True}


class WOPIHostService:
    """WOPI Host 服务

    Validates: Requirements 3.1, 3.2, 3.3, 3.7
    """

    # ------------------------------------------------------------------
    # 9.1  check_file_info / get_file / put_file
    # ------------------------------------------------------------------

    async def check_file_info(
        self,
        db: AsyncSession,
        file_id: UUID,
        user_id: UUID | None = None,
    ) -> dict:
        """WOPI CheckFileInfo: 返回文件元数据（含真实文件大小）。"""
        from pathlib import Path

        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == file_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise FileNotFoundError(f"底稿不存在: {file_id}")

        # 真实文件大小
        file_size = 0
        if wp.file_path:
            fp = Path(wp.file_path)
            if not fp.exists():
                fp = Path(__file__).resolve().parent.parent.parent / wp.file_path
            if fp.exists():
                file_size = fp.stat().st_size

        info = {
            "BaseFileName": Path(wp.file_path).name if wp.file_path else f"{file_id}.xlsx",
            "Size": file_size,
            "OwnerId": str(wp.created_by) if wp.created_by else "",
            "Version": str(wp.file_version),
            "UserCanWrite": True,  # 下方动态覆盖
            "UserCanNotWriteRelative": True,
            "SupportsLocks": True,
            "UserFriendlyName": str(user_id) if user_id else "",
        }

        # ── Phase 14: 动态 UserCanWrite 判定（对齐 v2 WP-ENT-03） ──
        can_write = True  # 默认可写，仅特定场景限制为只读
        readonly_reason = ""

        wp_status = getattr(wp, 'status', None)
        wp_status_val = wp_status.value if hasattr(wp_status, 'value') else str(wp_status or 'draft')

        # 签字窗口/归档：全员只读
        if wp_status_val in ('archived', 'review_passed'):
            can_write = False
            readonly_reason = "底稿已归档或复核通过"
        else:
            # 检查锁持有者（其他用户持锁时只读）
            lock_holder = _locks.get(str(file_id))
            if lock_holder and user_id and lock_holder.get("user_id") != str(user_id):
                can_write = False
                readonly_reason = "其他用户正在编辑"

        info["UserCanWrite"] = can_write
        if not can_write:
            info["ReadOnly"] = True
            info["ReadOnlyReason"] = readonly_reason

        # ── Phase 14: 写 trace_events ──
        try:
            from app.services.trace_event_service import trace_event_service
            await trace_event_service.write(
                db=db,
                project_id=getattr(wp, 'project_id', None) or user_id,
                event_type="wopi_access",
                object_type="workpaper",
                object_id=file_id,
                actor_id=user_id or file_id,
                action=f"check_file_info:{'write' if can_write else 'readonly'}",
                decision="allow" if can_write else "block",
                reason_code=readonly_reason if readonly_reason else None,
            )
        except Exception:
            pass  # trace 写入失败不阻断

        # 记录编辑会话打开事件
        try:
            from app.models.core import Log
            log = Log(
                user_id=user_id,
                action_type="workpaper_online_open",
                object_type="working_paper",
                object_id=file_id,
                new_value={"file_version": wp.file_version, "file_size": file_size},
            )
            db.add(log)
            await db.flush()
        except Exception:
            pass  # 不阻断主流程

        return info

    async def get_file(self, db: AsyncSession, file_id: UUID) -> bytes:
        """WOPI GetFile: 返回文件真实二进制内容。"""
        from pathlib import Path

        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == file_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise FileNotFoundError(f"底稿不存在: {file_id}")

        if not wp.file_path:
            raise FileNotFoundError(f"底稿文件路径为空: {file_id}")

        fp = Path(wp.file_path)
        if not fp.exists():
            # 尝试相对于 backend/ 目录查找
            backend_fp = Path(__file__).resolve().parent.parent.parent / wp.file_path
            if backend_fp.exists():
                fp = backend_fp
            else:
                raise FileNotFoundError(f"底稿文件不存在: {wp.file_path}")

        return fp.read_bytes()

    async def put_file(
        self,
        db: AsyncSession,
        file_id: UUID,
        content: bytes,
        lock_id: str | None = None,
    ) -> dict:
        """WOPI PutFile: 企业级保存 — 锁校验+版本快照+写入+哈希校验+审计留痕+事件发布。"""
        import hashlib
        import shutil
        from pathlib import Path

        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == file_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise FileNotFoundError(f"底稿不存在: {file_id}")

        # 归档后只读，禁止在线保存
        from app.models.workpaper_models import WpFileStatus as _WpFileStatus
        if wp.status == _WpFileStatus.archived:
            raise PermissionError("底稿已归档，不允许修改")

        # 1. 锁校验（Redis 优先，内存降级）
        file_key = str(file_id)
        if lock_id:
            # 检查 Redis 锁
            r = _get_redis()
            if r:
                try:
                    redis_key = f"wopi:lock:{file_key}"
                    existing = await r.get(redis_key)
                    if existing:
                        existing_id = existing.decode() if isinstance(existing, bytes) else existing
                        if existing_id != lock_id:
                            raise PermissionError(f"锁冲突: 期望 {lock_id}，实际 {existing_id}")
                except PermissionError:
                    raise
                except Exception:
                    pass  # Redis 不可用，降级到内存锁
            # 内存锁检查
            if file_key in _locks:
                lock_info = _locks[file_key]
                if lock_info["lock_id"] != lock_id:
                    raise PermissionError("锁冲突: lock_id 不匹配")

        if not wp.file_path:
            raise FileNotFoundError(f"底稿文件路径为空: {file_id}")

        fp = Path(wp.file_path)
        fp.parent.mkdir(parents=True, exist_ok=True)

        # 2. 版本快照（保存前备份当前版本）
        if fp.exists():
            snapshot_dir = fp.parent / ".versions"
            snapshot_dir.mkdir(exist_ok=True)
            snapshot_name = f"{fp.stem}_v{wp.file_version}{fp.suffix}"
            shutil.copy2(fp, snapshot_dir / snapshot_name)
            logger.info("version snapshot: %s → %s", fp.name, snapshot_name)

        # 3. 幂等检查（如果内容与当前文件完全相同，跳过写入）
        content_hash = hashlib.sha256(content).hexdigest()
        if fp.exists():
            existing_hash = hashlib.sha256(fp.read_bytes()).hexdigest()
            if existing_hash == content_hash:
                logger.info("put_file IDEMPOTENT: wp=%s hash=%s (skip write)", file_id, content_hash[:12])
                return {
                    "version": wp.file_version,
                    "content_hash": content_hash,
                    "file_size": len(content),
                    "message": "文件内容未变化，跳过写入",
                    "idempotent": True,
                }

        # 4. 写入文件
        fp.write_bytes(content)

        # 5. 哈希校验（写入后验证完整性）
        written_hash = hashlib.sha256(fp.read_bytes()).hexdigest()
        if written_hash != content_hash:
            logger.error("CRITICAL: hash mismatch after write! file=%s expected=%s actual=%s",
                         fp, content_hash, written_hash)
            # 尝试从快照恢复
            snapshot_dir = fp.parent / ".versions"
            snapshot_name = f"{fp.stem}_v{wp.file_version}{fp.suffix}"
            snapshot_path = snapshot_dir / snapshot_name
            if snapshot_path.exists():
                shutil.copy2(snapshot_path, fp)
                logger.info("restored from snapshot after hash mismatch")
            raise RuntimeError("文件写入完整性校验失败，已从快照恢复")

        # 5. 更新数据库
        old_version = wp.file_version
        wp.file_version += 1
        wp.updated_at = datetime.now(timezone.utc)
        wp.prefill_stale = True
        await db.flush()

        # 6. 审计留痕
        try:
            from app.models.core import Log
            log = Log(
                action_type="workpaper_online_save",
                object_type="working_paper",
                object_id=file_id,
                new_value={
                    "old_version": old_version,
                    "new_version": wp.file_version,
                    "file_size": len(content),
                    "content_hash": content_hash,
                    "lock_id": lock_id,
                    "save_method": "wopi_put_file",
                },
            )
            db.add(log)
            await db.flush()
        except Exception as e:
            logger.warning("audit log for online save failed: %s", e)

        # 7. 发布 WORKPAPER_SAVED 事件（异步，不阻塞保存响应）
        try:
            import asyncio as _asyncio
            from app.models.audit_platform_schemas import EventType, EventPayload
            from app.services.event_bus import event_bus
            payload = EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=wp.project_id,
                extra={
                    "wp_id": str(file_id),
                    "file_version": wp.file_version,
                    "trigger": "wopi_online_save",
                    "content_hash": content_hash,
                },
            )
            _asyncio.create_task(event_bus.publish(payload))
        except Exception as e:
            logger.warning("event publish after online save failed: %s", e)

        # 7b. 自动解析 parsed_data（非阻塞，用独立 session 避免主请求 session 关闭后失效）
        try:
            from app.services.prefill_engine import parse_workpaper_real

            async def _auto_parse():
                try:
                    from app.core.database import async_session
                    async with async_session() as parse_db:
                        await parse_workpaper_real(parse_db, wp.project_id, file_id)
                        await parse_db.commit()
                except Exception as _e:
                    logger.warning("auto parse background failed: %s", _e)

            _asyncio.create_task(_auto_parse())
        except Exception as e:
            logger.warning("auto parse after online save failed: %s", e)

        # 7c. 自动重建 structure.json（编辑保存后坐标同步）
        try:
            from app.services.wp_structure_bridge import generate_structure_for_workpaper
            from app.models.workpaper_models import WpIndex as _WpIndex
            idx_r = await db.execute(
                sa.select(_WpIndex.wp_code).where(_WpIndex.id == wp.wp_index_id)
            )
            _wp_code = idx_r.scalar_one_or_none() or ""
            if _wp_code:
                # 非阻塞：后台生成
                def _rebuild_structure():
                    try:
                        generate_structure_for_workpaper(
                            str(fp), _wp_code, str(wp.project_id)
                        )
                        logger.info("structure.json rebuilt after WOPI save: wp=%s", file_id)
                    except Exception as _se:
                        logger.warning("structure rebuild failed: %s", _se)
                import threading
                threading.Thread(target=_rebuild_structure, daemon=True).start()
        except Exception as e:
            logger.warning("structure rebuild setup failed: %s", e)

        # 7d. 自动执行精细化审计检查（非阻塞，用独立 session）
        try:
            from app.services.wp_fine_rule_engine import load_fine_rule, extract_with_fine_rule
            # _wp_code 在 7c 中已获取
            _fine_wp_code = _wp_code if '_wp_code' in dir() else ""
            if not _fine_wp_code:
                _idx_r2 = await db.execute(
                    sa.select(_WpIndex.wp_code).where(_WpIndex.id == wp.wp_index_id)
                )
                _fine_wp_code = _idx_r2.scalar_one_or_none() or ""
            if _fine_wp_code and load_fine_rule(_fine_wp_code):
                async def _auto_fine_extract():
                    try:
                        from app.core.database import async_session
                        async with async_session() as fine_db:
                            data = extract_with_fine_rule(
                                str(fp), _fine_wp_code, str(wp.project_id)
                            )
                            if "error" not in data:
                                from sqlalchemy.orm.attributes import flag_modified
                                _wp_r = await fine_db.execute(
                                    sa.select(WorkingPaper).where(WorkingPaper.id == file_id)
                                )
                                _wp_obj = _wp_r.scalar_one_or_none()
                                if _wp_obj:
                                    pd = _wp_obj.parsed_data or {}
                                    pd["fine_checks"] = data.get("checks", [])
                                    pd["fine_summary"] = data.get("summary", {})
                                    pd["fine_extracted_at"] = datetime.now(timezone.utc).isoformat()
                                    _wp_obj.parsed_data = pd
                                    flag_modified(_wp_obj, "parsed_data")
                                    await fine_db.commit()
                                    logger.info("auto fine-extract after WOPI save: wp=%s checks=%d",
                                                file_id, len(data.get("checks", [])))
                    except Exception as _fe:
                        logger.warning("auto fine-extract failed: %s", _fe)

                _asyncio.create_task(_auto_fine_extract())
        except Exception as e:
            logger.warning("auto fine-extract setup failed: %s", e)

        # 8. 云端双写（非阻塞）
        try:
            from app.services.cloud_storage_service import CloudStorageService, CLOUD_SYNC_ON_UPLOAD
            if CLOUD_SYNC_ON_UPLOAD:
                from app.models.core import Project
                proj_r = await db.execute(sa.select(Project).where(Project.id == wp.project_id))
                proj = proj_r.scalar_one_or_none()
                if proj:
                    cloud_svc = CloudStorageService()
                    pname = proj.client_name or "unknown"
                    ws = proj.wizard_state or {}
                    yr = ws.get("steps", {}).get("basic_info", {}).get("data", {}).get("audit_year", 2025)
                    rel_path = str(fp.relative_to(Path("storage") / "projects" / str(wp.project_id)))
                    await cloud_svc.sync_single_file(wp.project_id, pname, yr, fp, rel_path)
        except Exception as e:
            logger.warning("cloud sync after online save failed: %s", e)

        logger.info(
            "put_file SUCCESS: wp=%s v%d→v%d size=%d hash=%s",
            file_id, old_version, wp.file_version, len(content), content_hash[:12],
        )

        # ── Phase 16: 版本链写入 ──
        try:
            from app.services.version_line_service import version_line_service
            await version_line_service.write_stamp(
                db=db,
                project_id=wp.project_id,
                object_type="workpaper",
                object_id=file_id,
                version_no=wp.file_version,
                source_snapshot_id=content_hash[:16],
            )
        except Exception as _vl_err:
            logger.warning("version_line write_stamp failed: %s", _vl_err)

        return {
            "version": wp.file_version,
            "content_hash": content_hash,
            "file_size": len(content),
            "message": "文件保存成功",
        }

    # ------------------------------------------------------------------
    # 9.2  Lock management (in-memory dict for MVP)
    # ------------------------------------------------------------------

    def lock(self, file_id: UUID, lock_id: str) -> dict:
        """WOPI Lock: 获取排他锁。优先 Redis，降级内存。

        Validates: Requirements 3.3, Phase 9 Task 9.3
        """
        import asyncio
        file_key = str(file_id)

        # 尝试 Redis 分布式锁
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在异步上下文中，无法同步调用 — 降级到内存锁
                pass
            else:
                result = loop.run_until_complete(_redis_lock(file_key, lock_id))
                if not result.get("fallback"):
                    return result
        except Exception:
            pass

        # 降级：内存锁
        now = time.time()
        if file_key in _locks:
            existing = _locks[file_key]
            if existing["expires_at"] > now:
                if existing["lock_id"] != lock_id:
                    return {"success": False, "status": 409, "existing_lock": existing["lock_id"], "message": "文件已被其他用户锁定"}
                existing["expires_at"] = now + _LOCK_TTL_SECONDS
                return {"success": True, "message": "锁已刷新"}
            del _locks[file_key]

        _locks[file_key] = {"lock_id": lock_id, "expires_at": now + _LOCK_TTL_SECONDS}
        return {"success": True, "message": "锁定成功"}

    def unlock(self, file_id: UUID, lock_id: str) -> dict:
        """WOPI Unlock: 释放锁。

        Validates: Requirements 3.3
        """
        file_key = str(file_id)

        if file_key not in _locks:
            return {"success": True, "message": "无锁可释放"}

        existing = _locks[file_key]
        if existing["lock_id"] != lock_id:
            return {
                "success": False,
                "status": 409,
                "existing_lock": existing["lock_id"],
                "message": "lock_id 不匹配",
            }

        del _locks[file_key]
        return {"success": True, "message": "锁已释放"}

    def refresh_lock(self, file_id: UUID, lock_id: str) -> dict:
        """WOPI RefreshLock: 延长锁超时。

        Validates: Requirements 3.3
        """
        file_key = str(file_id)

        if file_key not in _locks:
            return {
                "success": False,
                "status": 409,
                "message": "锁不存在",
            }

        existing = _locks[file_key]
        if existing["lock_id"] != lock_id:
            return {
                "success": False,
                "status": 409,
                "existing_lock": existing["lock_id"],
                "message": "lock_id 不匹配",
            }

        existing["expires_at"] = time.time() + _LOCK_TTL_SECONDS
        return {"success": True, "message": "锁已刷新"}

    # ------------------------------------------------------------------
    # 9.3  Access token (JWT)
    # ------------------------------------------------------------------

    @staticmethod
    def generate_access_token(
        user_id: UUID,
        project_id: UUID,
        file_id: UUID,
        expires_minutes: int = 15,  # 短 TTL：15 分钟（WOPI 专用，前端需定时刷新）
    ) -> str:
        """生成 WOPI 访问令牌 (JWT)。

        Validates: Requirements 3.2
        """
        expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        payload = {
            "sub": str(user_id),
            "project_id": str(project_id),
            "file_id": str(file_id),
            "exp": expire,
            "type": "wopi",
        }
        return jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

    @staticmethod
    def validate_access_token(token: str) -> dict:
        """校验 WOPI 访问令牌。

        Validates: Requirements 3.2
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            if payload.get("type") != "wopi":
                raise ValueError("非 WOPI 令牌")
            return {
                "user_id": payload["sub"],
                "project_id": payload.get("project_id"),
                "file_id": payload.get("file_id"),
            }
        except JWTError as e:
            raise ValueError(f"令牌无效: {e}")


def clear_locks() -> None:
    """Clear all locks (for testing)."""
    _locks.clear()
