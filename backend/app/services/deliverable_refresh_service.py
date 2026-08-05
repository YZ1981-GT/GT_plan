"""出品物增量刷新服务：单章节/批量刷新（需求 5）。

Spec: deliverable-lineage-and-writeback
Design: 组件「7. 单章节增量刷新」

复用 scan_section_blocks / delete_section_block 定位目标块；
不全量重生成整份文档（需求 5.1）。
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import TypedDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.deliverable_section_state_service import DeliverableSectionStateService

logger = logging.getLogger(__name__)


# ─── Terminal statuses (reuse same constant) ─────────────────────────────────

TERMINAL_STATUSES = frozenset({"signed", "confirmed", "archived"})


# ─── Result types ────────────────────────────────────────────────────────────


class RefreshResult(TypedDict):
    """刷新结果。"""

    version_no: int | None  # 新版本号（成功时）
    refreshed: list[str]  # 成功刷新的 section_code
    skipped: list[str]  # 跳过的 section_code（锚点丢失等）
    requires_confirm: bool  # 是否需要用户确认覆盖人工编辑
    pending_confirm_sections: list[str]  # 等待确认的章节列表


# ─── DeliverableRefreshService ───────────────────────────────────────────────


class DeliverableRefreshService:
    """出品物单/批量章节增量刷新服务。

    复用 scan_section_blocks 定位目标块 + delete_section_block 删除旧内容，
    用最新 disclosure_notes 重新填充。不全量重生成（需求 5.1）。
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._section_state_service = DeliverableSectionStateService(db)

    async def refresh_section(
        self,
        word_export_task_id: UUID,
        project_id: UUID,
        year: int,
        section_code: str,
        actor_id: UUID,
        *,
        confirm_overwrite: bool = False,
        docx_bytes: bytes | None = None,
    ) -> RefreshResult:
        """单章节增量刷新（需求 5）：

        0. 终态检查（signed/confirmed/archived → 拒绝）
        1. 下载当前 docx，scan_section_blocks 经 Section_Anchor 定位目标块
        2. 若覆盖用户已编辑内容 → requires_confirm=True 返回（前端弹确认）
        3. delete_section_block + 用最新 disclosure_notes 内容重新填充
        4. 仅更新该章节 source_snapshot_hash + 清 stale
        5. 经 DeliverableService 创建新版本 version_no+1

        Args:
            word_export_task_id: 出品物标识
            project_id: 项目 ID
            year: 年度
            section_code: 要刷新的章节编码
            actor_id: 操作人 ID
            confirm_overwrite: 用户是否确认覆盖人工编辑
            docx_bytes: 可选的 docx 字节（测试注入，生产环境从存储下载）

        Returns:
            RefreshResult
        """
        import sqlalchemy as sa

        from app.models.report_models import DisclosureNote

        # ─── 0. 终态检查 ─────────────────────────────────────────────────────
        terminal = await self._check_terminal(word_export_task_id)
        if terminal:
            raise ValueError(
                f"该出品物已{terminal}，不可回填或刷新；"
                "如需修改请走撤回/解锁流程"
            )

        # ─── 1. 获取当前 docx 并定位目标章节块 ───────────────────────────────
        if docx_bytes is None:
            docx_bytes = await self._download_current_docx(word_export_task_id)

        if docx_bytes is None:
            return RefreshResult(
                version_no=None,
                refreshed=[],
                skipped=[section_code],
                requires_confirm=False,
                pending_confirm_sections=[],
            )

        from docx import Document

        from app.services.section_anchor_utils import resolve_section_blocks

        doc = Document(BytesIO(docx_bytes))
        # 锚点优先、##SECTION 标记回退：交付 docx 的标记在导出末尾已被清掉，
        # 只用 scan_section_blocks 会恒得空 → 刷新永远走「锚点丢失 skip」（历史缺陷）。
        locate_mode, blocks = resolve_section_blocks(doc)
        target_block = next(
            (b for b in blocks if b.section_code == section_code), None
        )

        if target_block is None:
            logger.warning(
                "refresh_section: 定位失败 mode=%s section=%s（该交付件可能生成于"
                "锚点接线之前，请重新生成后再刷新）",
                locate_mode,
                section_code,
            )
            return RefreshResult(
                version_no=None,
                refreshed=[],
                skipped=[section_code],
                requires_confirm=False,
                pending_confirm_sections=[],
            )

        # ─── 2. 检测人工编辑冲突（需求 5.5） ────────────────────────────────
        if not confirm_overwrite:
            has_user_edits = await self._detect_user_edits(
                word_export_task_id, project_id, year, section_code, target_block
            )
            if has_user_edits:
                return RefreshResult(
                    version_no=None,
                    refreshed=[],
                    skipped=[],
                    requires_confirm=True,
                    pending_confirm_sections=[section_code],
                )

        # ─── 3. 获取最新 disclosure_notes 内容并重填 ─────────────────────────
        latest_text = await self._latest_note_text(project_id, year, section_code)

        # 就地替换块内容（需求 4.5）：先在原位置插入新段落、再删旧元素，
        # 保证该章节在文档中的位置不变（旧实现用 doc.add_paragraph 追加到文末）。
        rendered_hash = self._replace_block_content(
            target_block, latest_text or "", locate_mode
        )

        # ─── 4. 更新该章节 source_snapshot_hash + Rendered_Block_Hash + 清 stale ──
        new_hash = await self._section_state_service.compute_source_snapshot_hash(
            project_id, year, section_code
        )
        await self._section_state_service.clear_section_stale(
            word_export_task_id,
            section_code,
            new_hash,
            rendered_block_hash=rendered_hash,
        )

        # ─── 5. 创建新版本 ──────────────────────────────────────────────────
        from app.services.deliverable_service import DeliverableService

        deliverable_svc = DeliverableService(self.db)

        # 序列化更新后的 docx
        output = BytesIO()
        doc.save(output)
        new_docx_bytes = output.getvalue()

        # render_and_store 一次性完成 建版本 + 落盘 + 绑哈希（旧实现误调
        # 不存在的 store_version_file → AttributeError，因测试 mock 把该方法
        # 编进去才漏抓；single-section 刷新路径实际从未真正落盘）。
        store_result = await deliverable_svc.render_and_store(
            word_export_task_id,
            docx_bytes=new_docx_bytes,
            user_id=actor_id,
            created_via="refresh_section",
        )

        return RefreshResult(
            version_no=store_result.version.version_no,
            refreshed=[section_code],
            skipped=[],
            requires_confirm=False,
            pending_confirm_sections=[],
        )

    async def refresh_all_stale_sections(
        self,
        word_export_task_id: UUID,
        project_id: UUID,
        year: int,
        actor_id: UUID,
        *,
        confirm_overwrite: bool = False,
        docx_bytes: bytes | None = None,
    ) -> RefreshResult:
        """批量刷新所有 stale 章节（需求 5.7）。

        逐章节复用 refresh_section 逻辑，保留未过期且已人工编辑的章节；
        覆盖人工编辑按 5.5 统一提示确认。
        主流程开头同样做终态检查（需求 11.1/11.3）。
        """
        # 终态检查
        terminal = await self._check_terminal(word_export_task_id)
        if terminal:
            raise ValueError(
                f"该出品物已{terminal}，不可回填或刷新；"
                "如需修改请走撤回/解锁流程"
            )

        # 获取所有 stale 章节
        states = await self._section_state_service.get_section_states(
            word_export_task_id
        )
        stale_codes = [s["section_code"] for s in states if s.get("is_stale")]

        if not stale_codes:
            return RefreshResult(
                version_no=None,
                refreshed=[],
                skipped=[],
                requires_confirm=False,
                pending_confirm_sections=[],
            )

        # 下载 docx 一次（避免每章节重复下载）
        if docx_bytes is None:
            docx_bytes = await self._download_current_docx(word_export_task_id)

        if docx_bytes is None:
            return RefreshResult(
                version_no=None,
                refreshed=[],
                skipped=stale_codes,
                requires_confirm=False,
                pending_confirm_sections=[],
            )

        # 🔴 全部章节在**同一份 doc** 上替换后**只落一个版本**。
        # 旧实现是逐章节调 refresh_section 且每次都传同一份原始 docx_bytes：
        # 每次从原始字节重新解析 → 上一章节的替换结果被丢弃 → 最终版本只含
        # 最后一个章节的刷新，其余全部丢失；同时产生 N 个版本污染版本链。
        from docx import Document

        from app.services.section_anchor_utils import resolve_section_blocks

        doc = Document(BytesIO(docx_bytes))
        locate_mode, blocks = resolve_section_blocks(doc)
        block_map = {b.section_code: b for b in blocks}

        refreshed: list[str] = []
        skipped: list[str] = []
        pending_confirm: list[str] = []
        new_hashes: dict[str, str] = {}

        for code in stale_codes:
            block = block_map.get(code)
            if block is None:
                logger.warning(
                    "refresh_all_stale_sections: 定位失败 mode=%s section=%s",
                    locate_mode,
                    code,
                )
                skipped.append(code)
                continue

            if not confirm_overwrite:
                has_user_edits = await self._detect_user_edits(
                    word_export_task_id, project_id, year, code, block
                )
                if has_user_edits:
                    pending_confirm.append(code)
                    continue

            latest_text = await self._latest_note_text(project_id, year, code)
            new_hashes[code] = self._replace_block_content(
                block, latest_text, locate_mode
            )
            refreshed.append(code)

        # 有待确认章节且未确认 → 整批不写入（避免半写状态）
        if pending_confirm and not confirm_overwrite:
            return RefreshResult(
                version_no=None,
                refreshed=[],
                skipped=skipped,
                requires_confirm=True,
                pending_confirm_sections=pending_confirm,
            )

        if not refreshed:
            return RefreshResult(
                version_no=None,
                refreshed=[],
                skipped=skipped,
                requires_confirm=False,
                pending_confirm_sections=[],
            )

        # 逐章节更新基线，再整份落一个新版本
        for code in refreshed:
            new_hash = await self._section_state_service.compute_source_snapshot_hash(
                project_id, year, code
            )
            await self._section_state_service.clear_section_stale(
                word_export_task_id,
                code,
                new_hash,
                rendered_block_hash=new_hashes.get(code),
            )

        from app.services.deliverable_service import DeliverableService

        output = BytesIO()
        doc.save(output)
        store_result = await DeliverableService(self.db).render_and_store(
            word_export_task_id,
            docx_bytes=output.getvalue(),
            user_id=actor_id,
            created_via="refresh_stale",
        )

        return RefreshResult(
            version_no=store_result.version.version_no,
            refreshed=refreshed,
            skipped=skipped,
            requires_confirm=False,
            pending_confirm_sections=[],
        )

    async def _latest_note_text(
        self, project_id: UUID, year: int, section_code: str
    ) -> str:
        """读取该章节当前 DB 文字（刷新写入源）。"""
        import sqlalchemy as sa

        from app.models.report_models import DisclosureNote

        stmt = sa.select(DisclosureNote.text_content).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == section_code,
            DisclosureNote.is_deleted == sa.false(),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() or ""

    # ─── Private helpers ─────────────────────────────────────────────────────

    async def _check_terminal(self, word_export_task_id: UUID) -> str | None:
        """检查出品物是否处于终态。返回状态名（如 signed）或 None。"""
        from sqlalchemy import text

        result = await self.db.execute(
            text("SELECT status FROM word_export_task WHERE id = :tid"),
            {"tid": str(word_export_task_id)},
        )
        row = result.first()
        if row is None:
            return None
        status = row[0]
        return status if status in TERMINAL_STATUSES else None

    async def _download_current_docx(self, word_export_task_id: UUID) -> bytes | None:
        """下载出品物当前最新版本 docx。

        从本地文件系统读取（DeliverableService.store 时写入的路径）。
        """
        from sqlalchemy import text

        # 查找最新版本的文件路径
        result = await self.db.execute(
            text(
                "SELECT file_path FROM word_export_task_versions "
                "WHERE word_export_task_id = :tid "
                "ORDER BY version_no DESC LIMIT 1"
            ),
            {"tid": str(word_export_task_id)},
        )
        row = result.first()
        if row is None or not row[0]:
            logger.warning(
                "No version file found for task %s", word_export_task_id
            )
            return None

        from pathlib import Path

        file_path = Path(row[0])
        if not file_path.exists():
            logger.warning(
                "Version file not found on disk: %s", file_path
            )
            return None

        return file_path.read_bytes()

    async def _detect_user_edits(
        self,
        word_export_task_id: UUID,
        project_id: UUID,
        year: int,
        section_code: str,
        target_block,
    ) -> bool:
        """检测用户是否对该章节做过人工编辑（需求 4.2/4.3/4.4）。

        判据：当前块内文字的 Rendered_Block_Hash ≠ 上次生成/刷新时记录的
        ``deliverable_section_state.rendered_block_hash``。

        🔴 **不能拿 ``source_snapshot_hash`` 来比** —— 它是「DB 源数据域」
        （``sha256(json{section_code,text_content,table_data,audited_amounts})``），
        与「块内渲染文字域」根本不是一回事，两者永远不等 ⇒ 刷新恒返回
        ``requires_confirm=True``（历史缺陷即此，用户每次刷新都被要求确认覆盖）。

        Rendered_Block_Hash 为 NULL（存量交付件）⇒ 判定无人工编辑（fail-open，
        与引入前行为一致，需求 4.4）。
        """
        import sqlalchemy as sa

        from app.models.audit_platform_models import DeliverableSectionState
        from app.services.section_anchor_utils import block_text_hash

        stmt = sa.select(DeliverableSectionState.rendered_block_hash).where(
            DeliverableSectionState.word_export_task_id == word_export_task_id,
            DeliverableSectionState.section_code == section_code,
        )
        result = await self.db.execute(stmt)
        baseline_block_hash = result.scalar_one_or_none()

        if not baseline_block_hash:
            # 无渲染基线（存量交付件 / 首次）→ 视为无人工编辑
            return False

        # 与导出侧共用同一个哈希函数（禁各写一份，否则哈希域必然漂移）
        current_block_hash = block_text_hash(list(target_block.elements))
        return current_block_hash != baseline_block_hash

    def _replace_block_content(
        self,
        target_block,
        text_content: str,
        locate_mode: str,
    ) -> str:
        """就地替换章节块内容，返回新内容的 Rendered_Block_Hash（需求 4.5/4.6）。

        算法（顺序关键）：
        1. 先在**原位置**插入新段落 —— anchor 模式插到锚点区间内（有内容控件时插进
           ``w:sdtContent`` 内部，新内容才被 Tag 覆盖）；marker 模式插到开标记之后；
        2. 再删除旧内容元素。

        先插后删是为了保住位置：旧实现 ``doc.add_paragraph`` 把刷新后的章节追加到
        **文档末尾**（注释自承认「实际生产中应在删除前记录位置并 insertbefore」），
        刷新一次章节顺序就乱。

        Returns:
            新写入内容的规范化 sha256（与导出侧同函数），供更新基线。
        """
        from docx.oxml import OxmlElement

        from app.services.section_anchor_utils import (
            anchor_block_content_host,
            block_text_hash,
        )

        lines = [ln.strip() for ln in (text_content or "").split("\n") if ln.strip()]

        def _new_paragraph(text: str):
            p = OxmlElement("w:p")
            r = OxmlElement("w:r")
            t = OxmlElement("w:t")
            t.text = text
            t.set(
                "{http://www.w3.org/XML/1998/namespace}space", "preserve"
            )
            r.append(t)
            p.append(r)
            return p

        old_elements = list(getattr(target_block, "elements", None) or [])
        new_paragraphs = [_new_paragraph(line) for line in lines]

        if locate_mode == "anchor":
            host, children = anchor_block_content_host(target_block)
            if children:
                anchor_el = children[0]
                for p in new_paragraphs:
                    anchor_el.addprevious(p)
            else:
                # 空区间：紧跟 bookmarkStart 之后逆序插入以保持先后顺序
                start_el = target_block.start_el
                for p in reversed(new_paragraphs):
                    start_el.addnext(p)
            # 删除旧内容（仅区间内内容元素；书签与内容控件外壳保留）
            for el in children:
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)
        else:
            # marker 模式：开闭标记保留，只换标记之间的内容
            open_el = getattr(target_block, "open_el", None)
            inner = [
                el
                for el in old_elements
                if el is not open_el
                and el is not getattr(target_block, "close_el", None)
            ]
            if open_el is not None:
                for p in reversed(new_paragraphs):
                    open_el.addnext(p)
            for el in inner:
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)

        # 用与导出侧完全一致的口径算新哈希（只取 w:p、排除 ## 标记行）
        return block_text_hash(new_paragraphs)
