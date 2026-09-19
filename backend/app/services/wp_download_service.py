"""底稿下载与导入服务 — Phase 10 Task 1.1-1.2

提供底稿批量打包下载（含预填充）和离线编辑回传（含版本冲突检测）。
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.wp_export.self_evidence import (
    build_self_evidence_banner,
    needs_self_evidence,
)
from app.services.wp_export.wp_file_resolver import VERDICT_LABELS, resolve_wp_file

logger = logging.getLogger(__name__)

STORAGE_ROOT = Path("storage")

#: ZIP 内跳过清单的文件名（下划线前缀让它排在循环目录之前，用户一眼能看到）
_SKIPPED_MANIFEST_NAME = "_未导出清单.txt"

#: 自证边车文件后缀 —— 与底稿同名、同目录，紧邻可见。
#:
#: 🔴 为什么用边车 txt 而不是往 xlsx 里盖章（2026-08-10 实证裁决）：
#: `backend/wp_templates/` 下 351 个 xlsx 里 **182 个含 drawing / 50 个含 media /
#: 1 个含 chart**，而 openpyxl 的读-改-写 round-trip **会丢弃**图形、图片、图表。
#: 批量打包若为盖一行自证而把这些模板过一遍 openpyxl，等于用「说明清楚了」
#: 换「模板内容被削」——代价完全不划算。
#: 故批量路径保持 `zf.write` 原字节不动，自证走同名边车 + `_未导出清单.txt` 两处。
_SELF_EVIDENCE_SIDECAR_SUFFIX = ".自证说明.txt"

#: 每个 verdict 档的处置建议 —— 单一真源（R1.5）。
#:
#: 🔴 键集必须覆盖 `WP_FILE_VERDICTS` 里除 `file` 之外的全部档位：清单按
#: 「出现的档位」逐条取建议，缺键会退到 `_VERDICT_ADVICE_FALLBACK`，
#: 那是兜底而非正解 —— 守卫按「建议条数 ≥ 档位数」断言，新增 verdict 档
#: 若忘了补建议，条数仍够但内容是兜底话术，故另有守卫扫键集完整性。
_VERDICT_ADVICE: dict[str, str] = {
    "empty": (
        "该底稿尚未生成实体文件（file_path 为空）。"
        "请在底稿列表中打开并保存一次，或用「生成底稿」重新生成后再导出。"
    ),
    "missing": (
        "路径已配置但磁盘上找不到文件（可能被移动或清理）。"
        "请用「生成底稿」重新生成，或联系管理员核查存储。"
    ),
    "template_fallback": (
        "ZIP 内该份是**空白模板**而非您的录入内容。"
        "若底稿界面已有数据，请改用底稿页的「导出数据」获取含录入内容的版本。"
    ),
    # ── Task 12（workpaper-html-onlyoffice-bidirectional-writeback-closure）新增两档 ──
    "path_rejected": (
        "该底稿的文件路径指向存储根之外（历史脏数据或被人工改过），"
        "已按安全策略拒绝读取。请用「生成底稿」重新生成，或联系管理员核查该底稿的 "
        "file_path。"
    ),
    "type_mismatch": (
        "该底稿所需格式与磁盘上的文件类型不符（例如需要 Word 却只找到 Excel），"
        "已拒绝用异类型文件凑数。请联系管理员补齐该底稿编码对应格式的模板。"
    ),
}

#: 未登记档位的兜底建议（出现即说明 `_VERDICT_ADVICE` 该补键了）
_VERDICT_ADVICE_FALLBACK = "请在底稿列表中打开该底稿核查，或联系管理员。"


def _render_sidecar(
    *,
    banner: str,
    wp_code: str,
    wp_name: str,
    raw_path: str | None,
) -> str:
    """渲染单份底稿的自证边车内容。

    文案主体（`banner`）来自 `self_evidence` 共享件，本函数只做排版与排查信息，
    **不硬写任何自证中文**（R1.3：守卫扫本文件源码钉死）。
    """
    lines = [
        banner,
        "",
        f"底稿：{wp_code} {wp_name}",
    ]
    if raw_path:
        lines.append(f"原始 file_path：{raw_path}")
    lines.append("")
    lines.append("（本说明由系统在导出时生成，与同名底稿文件一并放置便于对照）")
    return "\n".join(lines) + "\n"


def _render_skipped_manifest(
    *,
    project_id: UUID,
    total: int,
    written: int,
    skipped: list[dict[str, str]],
) -> str:
    """把跳过的底稿渲染成人可读清单（写进 ZIP 根目录）。

    🔴 为什么必须写进 ZIP 而不是只记后端日志：审计师拿到 ZIP 只看到少了底稿，
    既不知道少了哪些、也不知道原因（"很多模板导不出来都是空的"）。清单让
    「导出不全」这件事自证，而不是让人以为内容本来就空。
    """
    by_verdict: dict[str, list[dict[str, str]]] = {}
    for item in skipped:
        by_verdict.setdefault(item.get("verdict", "missing"), []).append(item)

    # `template_fallback` 实际**进了** ZIP（内容是空白模板），与真正未导出的分开计数，
    # 否则"未导出 N 份"会与 ZIP 里的文件数矛盾，用户对不上账。
    fallback_n = len(by_verdict.get("template_fallback", []))
    missing_n = len(skipped) - fallback_n

    lines = [
        "底稿批量导出 — 内容提示清单",
        "",
        f"项目：{project_id}",
        f"应导出：{total} 份    已写入 ZIP：{written} 份",
        f"未导出（无文件）：{missing_n} 份    已导出但为空白模板：{fallback_n} 份",
        "",
        "明细（按原因分组）：",
    ]

    for verdict, items in sorted(by_verdict.items()):
        label = VERDICT_LABELS.get(verdict, verdict)
        lines.append("")
        lines.append(f"【{label}】共 {len(items)} 份")
        for item in items:
            cycle = item.get("audit_cycle") or "其他"
            lines.append(
                f"  - {cycle} / {item.get('wp_code', '')} {item.get('wp_name', '')}"
                f"    原因：{item.get('reason', '')}"
            )

    # ─── 处置建议：**逐档给**，条数恒等于出现的档位数（R1.5）───────────────
    # 🔴 改造前是写死的 2 条 bullet 覆盖 3 个档位，一旦三档同时出现就
    #    "建议条数 < 档位数"，等于有档位无处置指引。现在从 `_VERDICT_ADVICE`
    #    单一真源按出现的档位取，结构上保证一一对应。
    lines.append("")
    lines.append("处置建议：")
    for verdict in sorted(by_verdict):
        label = VERDICT_LABELS.get(verdict, verdict)
        advice = _VERDICT_ADVICE.get(verdict, _VERDICT_ADVICE_FALLBACK)
        lines.append(f"  · 「{label}」→ {advice}")

    return "\n".join(lines) + "\n"


class WpDownloadService:
    """底稿下载服务"""

    async def download_single(
        self, db: AsyncSession, project_id: UUID, wp_id: UUID,
    ) -> dict[str, Any]:
        """单个底稿下载，返回文件路径和元数据"""
        result = await db.execute(
            sa.select(WorkingPaper, WpIndex)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(WorkingPaper.id == wp_id,
                   WorkingPaper.project_id == project_id,
                   WorkingPaper.is_deleted == sa.false())
        )
        row = result.first()
        if not row:
            raise ValueError("底稿不存在")
        wp, idx = row

        # 🔴 路径解析统一委托共享件 resolve_wp_file（四种 file_path 形态 + 模板库回退）。
        #    此处原有一段自写的「相对 backend/ 再试一次」回退，而紧邻的 download_pack
        #    没有 —— 同一语义两处各写一份、只有一处做了回退，正是本次缺陷的成因之一。
        res = resolve_wp_file(wp.file_path, wp_code=idx.wp_code)
        if res.path is None:
            raise ValueError(f"底稿文件不存在: {res.reason}（file_path={wp.file_path!r}）")

        # 扩展名按解析到的真实文件取（docx 底稿不能一律叫 .xlsx）
        suffix = res.path.suffix or ".xlsx"
        return {
            "file_path": str(res.path),
            "file_name": f"{idx.wp_code}_{idx.wp_name}{suffix}",
            "file_version": wp.file_version,
            "wp_id": str(wp.id),
            "resolved_verdict": res.verdict,
        }

    async def download_pack(
        self,
        db: AsyncSession,
        project_id: UUID,
        wp_ids: list[UUID],
        include_prefill: bool = True,
    ) -> io.BytesIO:
        """批量打包下载为 ZIP

        目录结构: {audit_cycle}/{wp_code}_{wp_name}.xlsx
        """
        result = await db.execute(
            sa.select(WorkingPaper, WpIndex)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.id.in_(wp_ids),
                WorkingPaper.is_deleted == sa.false(),
            )
        )
        rows = result.all()
        if not rows:
            raise ValueError("未找到可下载的底稿")

        written = 0
        skipped: list[dict[str, str]] = []
        #: 进了 ZIP 但内容是空白模板的底稿（`template_fallback`）——
        #: 它们不属"未导出"，但对用户同样是"打开是空的"，故一并进清单（R1.4）。
        fallback_noted: list[dict[str, str]] = []
        seen_arc: dict[str, int] = {}

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for wp, idx in rows:
                # 🔴 路径解析走共享件：覆盖空串 / wp_templates 相对 / storage 相对 /
                #    绝对路径四种形态，并在不可达时回退模板库（空白模板仍比空目录有用）。
                res = resolve_wp_file(wp.file_path, wp_code=idx.wp_code)

                # 🔴 兜底红线：解析结果必须是**文件**。
                #    原实现只判 `Path(wp.file_path).exists()`，而 `Path("")` 会被
                #    规范成 `WindowsPath(".")` 且 `.exists()` 为 True ⇒ zf.write 把
                #    整个进程 cwd 写成一个「目录条目」，解压出来就是空文件夹。
                #    这条 is_file() 判断即便将来路径解析又出新形态也不会再产出空条目。
                if res.path is None or not res.path.is_file():
                    logger.warning(
                        "download_pack 跳过底稿: wp_code=%s verdict=%s file_path=%r",
                        idx.wp_code, res.verdict, wp.file_path,
                    )
                    skipped.append(
                        {
                            "wp_code": idx.wp_code or "",
                            "wp_name": idx.wp_name or "",
                            "audit_cycle": idx.audit_cycle or "",
                            "verdict": res.verdict,
                            "reason": res.reason,
                        }
                    )
                    continue

                cycle = idx.audit_cycle or "其他"
                suffix = res.path.suffix or ".xlsx"
                arc_name = f"{cycle}/{idx.wp_code}_{idx.wp_name}{suffix}"
                # 同 wp_code 多份（历史遗留双命名族）会撞 arcname，ZIP 里同名条目
                # 解压时互相覆盖 → 加序号后缀而不是静默丢弃。
                if arc_name in seen_arc:
                    seen_arc[arc_name] += 1
                    stem = f"{idx.wp_code}_{idx.wp_name}({seen_arc[arc_name]})"
                    arc_name = f"{cycle}/{stem}{suffix}"
                else:
                    seen_arc[arc_name] = 1

                zf.write(res.path, arc_name)
                written += 1

                # ─── 自证边车（R1.1 / R1.4）────────────────────────────
                # 🔴 `verdict == 'template_fallback'` 的底稿**进了 ZIP 但是空白模板**。
                #    改造前它既不进跳过清单（清单只收 path 不可达的），产物里也没有
                #    任何说明 ⇒ 用户看到一堆空模板，误认为"底稿本来就没数据"。
                #    真实库这一档 1670 份，正是用户反馈的主要来源。
                kind = needs_self_evidence(
                    verdict=res.verdict,
                    html_data=None,       # 打包路径不读 html_data（原字节直传）
                    has_entry_rows=False,  # 同上：不查库，避免 N+1
                )
                if kind is not None:
                    banner = build_self_evidence_banner(
                        kind=kind,
                        verdict=res.verdict,
                        detail=f"{idx.wp_code} {idx.wp_name}",
                    )
                    zf.writestr(
                        f"{arc_name}{_SELF_EVIDENCE_SIDECAR_SUFFIX}",
                        _render_sidecar(
                            banner=banner,
                            wp_code=idx.wp_code or "",
                            wp_name=idx.wp_name or "",
                            raw_path=res.raw,
                        ).encode("utf-8"),
                    )
                    # 同时进清单，让"少了什么/为什么"在一个地方看全（R1.4）
                    fallback_noted.append(
                        {
                            "wp_code": idx.wp_code or "",
                            "wp_name": idx.wp_name or "",
                            "audit_cycle": cycle,
                            "verdict": res.verdict,
                            "reason": res.reason,
                        }
                    )

            # 🔴 清单必须进 ZIP：原实现只写后端 warning 日志，用户下载完
            #    完全不知道少了哪些底稿、为什么少（"导出来是空的"无从排查）。
            #    且必须把 `template_fallback` 一并列出 —— 它们**进了** ZIP，
            #    所以不在 `skipped` 里，但内容是空白模板，对用户同样是"没数据"。
            skipped = skipped + fallback_noted
            if skipped:
                zf.writestr(
                    _SKIPPED_MANIFEST_NAME,
                    _render_skipped_manifest(
                        project_id=project_id,
                        total=len(rows),
                        written=written,
                        skipped=skipped,
                    ).encode("utf-8"),
                )

        buf.seek(0)
        logger.info(
            "download_pack: project=%s, total=%d, written=%d, skipped=%d, size=%d bytes",
            project_id, len(rows), written, len(skipped), buf.getbuffer().nbytes,
        )
        return buf


class WpUploadService:
    """底稿导入服务（离线编辑回传）"""

    async def check_version_conflict(
        self, db: AsyncSession, wp_id: UUID, uploaded_version: int,
    ) -> dict[str, Any]:
        """检查版本冲突"""
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )
        wp = result.scalar_one_or_none()
        if not wp:
            raise ValueError("底稿不存在")

        has_conflict = uploaded_version < wp.file_version
        return {
            "has_conflict": has_conflict,
            "uploaded_version": uploaded_version,
            "server_version": wp.file_version,
            "wp_id": str(wp.id),
        }

    async def upload_file(
        self,
        db: AsyncSession,
        project_id: UUID,
        wp_id: UUID,
        file_content: bytes,
        uploaded_version: int,
        force_overwrite: bool = False,
    ) -> dict[str, Any]:
        """上传底稿文件

        Args:
            force_overwrite: True 时强制覆盖（忽略版本冲突）
        """
        result = await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.project_id == project_id,
            )
        )
        wp = result.scalar_one_or_none()
        if not wp:
            raise ValueError("底稿不存在")

        # 版本冲突检测
        #
        # 🔴 Task 19：比对目标换成 `working_paper.content_revision`（唯一 business
        #    content revision 域）。改造前比 `file_version` —— 那个计数器同时被 WOPI、
        #    另一条 upload 路径与 storage 快照推进，跨域比较必然造假冲突。
        #    这里只是「早失败 + 给用户可读信息」；真正的并发裁决是下方 commit 事务内的
        #    CAS（两者缺一不可，与 wp_html_save 的 Step 2b 同形）。
        server_content_revision = int(getattr(wp, "content_revision", 0) or 0)
        if not force_overwrite and uploaded_version < server_content_revision:
            return {
                "status": "conflict",
                "uploaded_version": uploaded_version,
                "server_version": server_content_revision,
                "message": (
                    f"版本冲突: 上传版本 {uploaded_version} < 服务器版本 "
                    f"{server_content_revision}"
                ),
            }

        # 写入文件
        file_path = Path(wp.file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(file_content)

        # ─── Task 19：迁入统一 business revision 域（Requirement 2.2 / Property 61）───
        #
        # 改造前是 `wp.file_version += 1` + `await db.flush()`：离线上传自己推进一个
        # 跨通道版本计数器，与 `WorkingPaperService.upload_offline_edit` **争同一个
        # 计数器**（清册原话），而文件写入与版本递增不是一个原子单元。
        #
        # 改造后：上传的 OOXML 字节就是权威内容本体，原样提交为
        # `authoritative_payload`；business content revision 由
        # `ContentMutationService.commit(...)` 的 CAS 唯一推进；`updated_at` /
        # `prefill_stale` 仍在这里写（Requirement 2.1 明列的非内容非版本副作用字段）。
        from app.services.workpaper_sync.content_mutation import UPLOAD as _UPLOAD_SOURCE
        from app.services.workpaper_sync.models import (
            RevisionConflictError as _RevisionConflictError,
        )
        from app.services.workpaper_sync.writer_migration import (
            build_content_mutation_service_writer,
            opaque_entry_id,
        )

        wp.updated_at = datetime.now(timezone.utc)
        wp.prefill_stale = True  # 标记需要重新解析
        await db.flush()

        _writer = build_content_mutation_service_writer(db)
        _expected_revision = await _writer.current_revision(wp_id)
        try:
            _receipt = await _writer.commit_bytes(
                project_id=project_id,
                wp_id=wp_id,
                entry_id=opaque_entry_id(wp_code=None, wp_id=wp_id),
                source=_UPLOAD_SOURCE,
                payload=file_content,
                document_type=file_path.suffix.lstrip(".").lower() or "xlsx",
                expected_revision=_expected_revision,
                # Task 65：authority model 由 lane 登记决定（`offline_upload` →
                # `opaque_single_onlyoffice`），不再由调用点传身份参数。
                substrate_path=file_path,
                lane_id="offline_upload",
            )
        except _RevisionConflictError:
            # 真并发：CAS 命中 0 行。返回与既有「版本冲突」同形的结构化结果，
            # 调用方（router）的分支不用改。窄捕获 —— 不得把发布失败也吞成冲突。
            return {
                "status": "conflict",
                "uploaded_version": uploaded_version,
                "server_version": _expected_revision,
                "message": (
                    f"版本冲突: 其他会话在本次上传期间修改了该底稿"
                    f"（服务器内容版本 {_expected_revision}）"
                ),
            }
        await _writer.publish_committed_events(_receipt)
        new_content_revision = _receipt.revision

        # 双写云端（非阻塞，失败只记日志）
        try:
            from app.services.cloud_storage_service import CloudStorageService, CLOUD_SYNC_ON_UPLOAD
            if CLOUD_SYNC_ON_UPLOAD:
                cloud_svc = CloudStorageService()
                # 获取项目信息
                import sqlalchemy as sa
                from app.models.core import Project
                proj_r = await db.execute(sa.select(Project).where(Project.id == project_id))
                proj = proj_r.scalar_one_or_none()
                if proj:
                    pname = proj.client_name or "unknown"
                    ws = proj.wizard_state or {}
                    yr = ws.get("steps", {}).get("basic_info", {}).get("data", {}).get("audit_year", 2025)
                    rel_path = str(file_path.relative_to(Path("storage") / "projects" / str(project_id)))
                    await cloud_svc.sync_single_file(project_id, pname, yr, file_path, rel_path)
        except Exception as e:
            logger.warning("cloud sync on upload failed (non-blocking): %s", e)

        # 触发解析关键单元格 → 回写 parsed_data（使用真实解析引擎）
        try:
            from app.services.prefill_engine import parse_workpaper_real
            from app.services.task_center import create_task, update_task, TaskType, TaskStatus
            parse_task_id = create_task(TaskType.parse_workpaper, project_id=str(project_id), object_id=str(wp_id))
            update_task(parse_task_id, TaskStatus.processing)
            parse_result = await parse_workpaper_real(db=db, project_id=project_id, wp_id=wp_id)
            update_task(parse_task_id, TaskStatus.success, result=parse_result)
            logger.info("parse after upload: wp=%s result=%s", wp_id, parse_result.get("status"))
        except Exception as e:
            try:
                update_task(parse_task_id, TaskStatus.failed, error=str(e))
            except Exception as ue:
                logger.debug("更新 parse 任务状态失败 wp=%s: %s", wp_id, ue)
            logger.warning("parse after upload failed (non-blocking): %s", e)

        # ── Phase 16: 离线冲突细粒度检测 ──
        try:
            from app.services.offline_conflict_service import offline_conflict_service
            conflicts = await offline_conflict_service.detect(db, project_id, wp_id)
            if conflicts:
                logger.info(f"[CONFLICT] detected {len(conflicts)} field-level conflicts for wp={wp_id}")
        except Exception as _conflict_err:
            logger.warning(f"[CONFLICT] detect failed (non-blocking): {_conflict_err}")

        # ── Phase 16: 版本链写入 ──
        try:
            from app.services.version_line_service import version_line_service
            await version_line_service.write_stamp(
                db=db,
                project_id=project_id,
                object_type="workpaper",
                object_id=wp_id,
                version_no=new_content_revision,
            )
        except Exception as _vl_err:
            logger.warning(f"[VERSION_LINE] write_stamp failed (non-blocking): {_vl_err}")

        # 发布 WORKPAPER_SAVED 事件 → 级联更新试算表和报表
        try:
            from app.models.audit_platform_schemas import EventType, EventPayload
            from app.services.event_bus import event_bus
            payload = EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=project_id,
                extra={
                    "wp_id": str(wp_id),
                    # Task 19：键名保留兼容，值是唯一 business content revision。
                    "file_version": new_content_revision,
                    "content_revision": new_content_revision,
                    "trigger": "upload",
                },
            )
            await event_bus.publish(payload)
            logger.info("event WORKPAPER_SAVED published: wp=%s", wp_id)
        except Exception as e:
            logger.warning("event publish failed (non-blocking): %s", e)

        logger.info(
            "upload_file: wp=%s, new_content_revision=%d, size=%d bytes",
            wp_id, new_content_revision, len(file_content),
        )

        # ── 三式联动：自动生成 structure.json ──
        try:
            from app.services.wp_structure_bridge import generate_structure_for_workpaper
            # 获取底稿编号
            from app.models.workpaper_models import WpIndex
            idx_r = await db.execute(
                sa.select(WpIndex.wp_code).where(WpIndex.id == wp.wp_index_id)
            )
            wp_code = idx_r.scalar_one_or_none() or ""
            generate_structure_for_workpaper(
                str(file_path), wp_code, str(project_id)
            )
            logger.info("structure.json generated after upload: wp=%s", wp_id)
        except Exception as _struct_err:
            logger.warning("structure generation after upload failed (non-blocking): %s", _struct_err)

        return {
            "status": "success",
            "wp_id": str(wp.id),
            "new_version": new_content_revision,
            "content_revision": new_content_revision,
            "content_version_id": str(_receipt.content_version_id),
            "file_size": len(file_content),
        }
