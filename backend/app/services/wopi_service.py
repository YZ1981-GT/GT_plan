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
from pathlib import Path
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.config import settings
from app.models.workpaper_models import WorkingPaper
# 🔴 Task 12（workpaper-html-onlyoffice-bidirectional-writeback-closure）：
# WOPI 的三处路径解析（check_file_info / get_file / put_file）改为委托统一
# canonical resolver。改造前三处各写一份 `Path(file_path)` + `.exists()` +
# `parent.parent.parent` 回退 —— 既漏了 `Path('')` 判 True 的语义坑，也完全没有
# 路径边界（Requirement 9.6 / Property 42）。
from app.services.workpaper_sync.canonical_paths import (
    BACKEND_ROOT as _BACKEND_ROOT,
    is_within_any_legacy_root,
    legacy_project_storage_root,
)
from app.services.wp_export.wp_file_resolver import resolve_wp_file

logger = logging.getLogger(__name__)


def _resolve_put_target(file_id: UUID, raw_file_path: str) -> Path:
    """WOPI PutFile 的写入目标绝对路径（边界内），越界即 `PermissionError`。

    分两支：

    * 文件**已存在** ⇒ 直接用统一 resolver 的结果（同一份判据，读写不分叉）；
    * 文件**还不存在**（首次保存）⇒ resolver 的 `is_file()` 判据用不上，只能做
      「相对 backend 根归一 + 边界校验」。这一支必须单独存在：把它省掉会让首次
      保存无路径可写，而共用 `is_file()` 判据又会让首次保存永远失败。

    `path_rejected` / `type_mismatch` 抬成 `PermissionError` 而不是
    `FileNotFoundError`：越界写入是安全事件，不是「文件找不到」。
    """
    existing = resolve_wp_file(raw_file_path, wp_code=None, allow_template_fallback=False)
    if existing.path is not None:
        return existing.path
    if existing.verdict in ("path_rejected", "type_mismatch"):
        logger.error(
            "WOPI put_file: 写入目标被拒 wp=%s verdict=%s raw=%r",
            file_id, existing.verdict, raw_file_path,
        )
        raise PermissionError(
            f"底稿文件路径不可用于写入: {existing.reason}（{existing.verdict}）"
        )
    candidate = Path(str(raw_file_path))
    resolved = (
        candidate if candidate.is_absolute() else _BACKEND_ROOT / candidate
    ).resolve()
    if not is_within_any_legacy_root(resolved):
        logger.error(
            "WOPI put_file: 首次保存目标越界 wp=%s raw=%r resolved=%s",
            file_id, raw_file_path, resolved,
        )
        raise PermissionError(f"底稿文件路径越界，拒绝写入: {raw_file_path}")
    return resolved

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
        gate_allow: bool = True,
    ) -> dict:
        """WOPI CheckFileInfo: 返回文件元数据（含真实文件大小）。

        ``UserCanWrite = gate allow ∩ file state ∩ lock``（procedure-delegation-visibility-isolation
        Task 11 / Req 10 / Design C11）：``gate_allow`` 为统一门写授权结果，与文件状态、锁合取。
        """
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == file_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise FileNotFoundError(f"底稿不存在: {file_id}")

        # 真实文件大小 —— 走统一 canonical resolver（Task 12）
        # 🔴 改造前此处是 `Path(wp.file_path)` + `.exists()` + 自写 `parent.parent.parent`
        #    回退：`Path('')` 的 `.exists()` 返回 True ⇒ 空 file_path 的底稿会把**当前
        #    目录**的 stat 当成文件大小；且没有任何路径边界（Property 42）。
        file_size = 0
        resolution = resolve_wp_file(
            wp.file_path, wp_code=None, allow_template_fallback=False
        )
        if resolution.path is not None:
            file_size = resolution.path.stat().st_size
        elif wp.file_path:
            logger.warning(
                "WOPI check_file_info: 底稿文件不可达 wp=%s verdict=%s reason=%s",
                file_id, resolution.verdict, resolution.reason,
            )

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

        # UserCanWrite = gate allow ∩ file state ∩ lock（Task 11 / Design C11）。
        # 上面 can_write 已含 file state ∩ lock；此处再合取门写授权 gate_allow。
        if can_write and not gate_allow:
            can_write = False
            readonly_reason = "无底稿写权限"

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
        """WOPI GetFile: 返回文件真实二进制内容。

        路径解析走统一 canonical resolver（Task 12）：`allow_template_fallback=False`
        —— 下载「这份底稿」与「一份空白模板」是两件事，WOPI 不做模板兜底。
        """
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == file_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise FileNotFoundError(f"底稿不存在: {file_id}")

        if not wp.file_path:
            raise FileNotFoundError(f"底稿文件路径为空: {file_id}")

        resolution = resolve_wp_file(
            wp.file_path, wp_code=None, allow_template_fallback=False
        )
        if resolution.path is None:
            raise FileNotFoundError(
                f"底稿文件不可达: {wp.file_path}（{resolution.verdict}: {resolution.reason}）"
            )
        return resolution.path.read_bytes()

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

        # 写入目标同样经统一 canonical resolver 归一（Task 12）。
        # 🔴 写路径的边界判定比读路径更重要：改造前 `Path(wp.file_path)` 对
        #    `../../` 或项目外绝对路径会直接 `mkdir` + `write_bytes`，把 OO 回传
        #    的字节写到存储根之外（Property 42 的写侧反例）。
        fp = _resolve_put_target(file_id, wp.file_path)
        fp.parent.mkdir(parents=True, exist_ok=True)

        # 2. 版本快照（保存前备份当前版本）
        #
        # 🔴 Task 19：快照名从 `wp.file_version` 换成**本次保存前的 content revision**。
        #    WOPI 迁入统一 revision 域后不再推进 `file_version`，若快照名继续用它，
        #    `{stem}_v1.xlsx` 会被每一次保存覆盖 —— 备份看着在、实际只剩最后一份。
        #    快照名必须绑在**真正在动的**那个计数器上。
        pre_save_revision = int(getattr(wp, "content_revision", 0) or 0)
        # 单一声明处：保存前备份与 hash-mismatch 回滚必须指向**同一个**文件名。
        # 两处各拼一遍 f-string 时，回滚分支（只在写盘校验失败时才走）会静默找不到快照。
        snapshot_name = f"{fp.stem}_r{pre_save_revision}{fp.suffix}"
        if fp.exists():
            snapshot_dir = fp.parent / ".versions"
            snapshot_dir.mkdir(exist_ok=True)
            shutil.copy2(fp, snapshot_dir / snapshot_name)
            logger.info("version snapshot: %s → %s", fp.name, snapshot_name)

        # 3. 幂等检查（如果内容与当前文件完全相同，跳过写入）
        content_hash = hashlib.sha256(content).hexdigest()
        if fp.exists():
            existing_hash = hashlib.sha256(fp.read_bytes()).hexdigest()
            if existing_hash == content_hash:
                logger.info("put_file IDEMPOTENT: wp=%s hash=%s (skip write)", file_id, content_hash[:12])
                return {
                    # 幂等路径不产生新内容版本，回传**当前** content revision
                    # （回传 file_version 会让客户端拿到一个已经冻结的数）。
                    "version": pre_save_revision,
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
            snapshot_path = snapshot_dir / snapshot_name
            if snapshot_path.exists():
                shutil.copy2(snapshot_path, fp)
                logger.info("restored from snapshot after hash mismatch")
            raise RuntimeError("文件写入完整性校验失败，已从快照恢复")

        # 5. 更新数据库 —— Task 19：迁入统一 business revision 域
        #
        # 改造前这里是 `wp.file_version += 1`：WOPI PutFile 自己推进一个跨通道版本
        # 计数器，绕过统一提交入口（Requirement 2.2 明列 WOPI）。改造后：
        #
        #   * 权威内容 = 刚落盘并已通过 hash 校验的 OOXML **本体字节**，原样提交为
        #     `authoritative_payload`（Requirement 2.11：不得被 JSON projection
        #     writer 改写）；
        #   * business content revision 由 `ContentMutationService.commit(...)` 的
        #     CAS 唯一推进；`file_version` 一个字都不碰；
        #   * `updated_at` / `prefill_stale` 仍在这里写 —— 它们是 Requirement 2.1
        #     明列的**非**内容非版本字段（副作用），与 revision 无关。
        #
        # 冲突语义：WOPI 协议没有 expected-revision 通道（Office online 不会带我们的
        # revision 回来），所以这里用「读到的当前值」当 expected。真并发下 CAS 会命中
        # 0 行并抛 `RevisionConflictError`，转成 PermissionError（WOPI 的 409 语义）。
        from app.services.workpaper_sync.content_mutation import WOPI as _WOPI_SOURCE
        from app.services.workpaper_sync.models import (
            RevisionConflictError as _RevisionConflictError,
        )
        from app.services.workpaper_sync.writer_migration import (
            build_content_mutation_service_writer,
            opaque_entry_id,
        )

        wp.updated_at = datetime.now(timezone.utc)
        wp.prefill_stale = True
        await db.flush()

        _writer = build_content_mutation_service_writer(db)
        _entry_id = opaque_entry_id(wp_code=None, wp_id=file_id)
        old_version = await _writer.current_revision(file_id)
        new_content_revision = old_version + 1

        # 6. 审计留痕 —— **在**内容 commit 之前入库
        #
        # 🔴 顺序不是风格问题：`commit_bytes` 是这笔事务的唯一提交出口，写在它之后的
        #    `db.add(log)` 会落到**下一个**事务里，而 WOPI router 并不一定再提交一次
        #    ⇒ 审计日志静默丢失。放在之前，「内容 + 审计日志 + content version +
        #    revision + 耐久事件」同生共死（Requirement 13.1）。
        try:
            from app.models.core import Log
            log = Log(
                action_type="workpaper_online_save",
                object_type="working_paper",
                object_id=file_id,
                new_value={
                    "old_version": old_version,
                    "new_version": new_content_revision,
                    "version_domain": "content_revision",
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

        try:
            _receipt = await _writer.commit_bytes(
                project_id=wp.project_id,
                wp_id=file_id,
                entry_id=_entry_id,
                source=_WOPI_SOURCE,
                payload=content,
                document_type=fp.suffix.lstrip(".").lower() or "xlsx",
                expected_revision=old_version,
                # Task 65：authority model 由 lane 登记决定（`wopi_put_file` →
                # `opaque_single_onlyoffice`），不再由调用点传身份参数。
                substrate_path=fp,
                lane_id="wopi_put_file",
            )
        except _RevisionConflictError as exc:
            raise PermissionError(
                "内容版本冲突：其他会话在本次 PutFile 期间修改了该底稿，请重新打开后再保存"
            ) from exc
        await _writer.publish_committed_events(_receipt)
        new_content_revision = _receipt.revision

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
                    # Task 19：WOPI 不再推进 file_version；下游按唯一 business
                    # content revision 刷新（键名保留兼容，装的是 content_revision）。
                    "file_version": new_content_revision,
                    "content_revision": new_content_revision,
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
                                    from app.services.wp_parsed_data_service import (
                                        touch_after_parsed_data_commit,
                                    )

                                    await touch_after_parsed_data_commit(
                                        _wp_obj,
                                        source="wopi_fine_extract",
                                    )
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
                    # 🔴 Task 12：`fp` 现在是**绝对**路径（统一 resolver 的后置条件），
                    #    改造前是 `Path(wp.file_path)` 的相对路径。故基准也必须换成
                    #    绝对的 `BACKEND_ROOT/storage/projects/{pid}`，否则
                    #    `relative_to` 恒抛 ValueError 并被下方 except 吞成
                    #    「cloud sync failed」——典型的 fail-open 静默失效。
                    project_root = legacy_project_storage_root(wp.project_id)
                    try:
                        rel_path = str(fp.relative_to(project_root))
                    except ValueError:
                        rel_path = fp.name
                    await cloud_svc.sync_single_file(wp.project_id, pname, yr, fp, rel_path)
        except Exception as e:
            logger.warning("cloud sync after online save failed: %s", e)

        logger.info(
            "put_file SUCCESS: wp=%s v%d→v%d size=%d hash=%s",
            file_id, old_version, new_content_revision, len(content), content_hash[:12],
        )

        # ── Phase 16: 版本链写入 ──
        try:
            from app.services.version_line_service import version_line_service
            await version_line_service.write_stamp(
                db=db,
                project_id=wp.project_id,
                object_type="workpaper",
                object_id=file_id,
                version_no=new_content_revision,
                source_snapshot_id=content_hash[:16],
            )
        except Exception as _vl_err:
            logger.warning("version_line write_stamp failed: %s", _vl_err)

        return {
            "version": new_content_revision,
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
