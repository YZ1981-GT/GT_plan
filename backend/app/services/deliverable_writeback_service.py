"""出品物回填服务：合规护栏分类 + 冲突检测 + 留痕。

Spec: deliverable-lineage-and-writeback
Design:
- 组件「6. DeliverableWritebackService」
- 「回填合规护栏设计」（需求 6 核心）
- 「三方比对冲突检测」（需求 8）
- 组件 6 第 9 步 留痕（需求 9）

本模块承载 Phase 3 核心逻辑：
- _classify_change: 变更项字段分类（TEXT/TABLE/TITLE）
- _detect_conflict: 三方比对冲突检测
- _log_writeback: TraceEventService 留痕集成
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from io import BytesIO
from typing import TypedDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.deliverable_section_state_service import (
    DeliverableSectionStateService,
    compute_snapshot_hash_from_parts,
)
from app.services.trace_event_service import trace_event_service

logger = logging.getLogger(__name__)


# ─── 合规护栏分类枚举与类型 ──────────────────────────────────────────────────


class ChangeKind(str, Enum):
    """变更项分类（Property 16 核心）。"""

    TEXT = "text"  # 文字说明 → 放行写回 text_content
    TABLE = "table"  # 表格数字 → 拒绝（金额严禁倒灌）
    TITLE = "title"  # 章节标题 → 忽略不回填


# 拒绝原因：中文指引（需求 6.3/6.6）
_TABLE_REJECTION_REASON = "金额变更须通过调整分录（AJE/RJE）修正，不可从出品物回填"
_TITLE_REJECTION_REASON = "章节标题由系统生成，不可从出品物回填"


class ChangeClassification(TypedDict):
    """单个变更项的分类结果。"""

    kind: ChangeKind
    section_code: str
    content: str
    rejection_reason: str | None  # Non-None for TABLE/TITLE


class WritebackConflict(TypedDict):
    """冲突呈现三方内容（需求 8.2）。"""

    section_code: str
    deliverable_value: str  # 出品物侧编辑值（本次下载提取）
    upstream_value: str  # 上游当前值（DB disclosure_notes.text_content）
    baseline_value: str  # 生成时基线值（按 source_snapshot_hash 对应版本）


class WritebackFailure(TypedDict):
    """写入未生效的章节（spec deliverable-lineage-wiring-… 需求 5.1）。

    与 ``skipped``（未参与写入）和 ``rejected``（护栏主动拒绝）语义不同：
    本类是**尝试写入但影响 0 行** —— 历史缺陷是这类被静默计入 ``written`` 并
    Toast「已成功回填 N 个章节」，而 DB 里什么都没变。
    """

    section_code: str
    reason: str


class WritebackResult(TypedDict):
    """回填结果。

    五类 section_code 集合两两不交（Property 10）：
    written / rejected / conflicts / skipped / failed。
    """

    written: list[str]  # 成功写回且**影响行数 > 0** 的 section_code
    rejected: list[ChangeClassification]  # 被护栏拒绝的变更
    conflicts: list[WritebackConflict]  # 待裁决的冲突
    skipped: list[str]  # 跳过的 section_code（如锚点丢失）
    failed: list[WritebackFailure]  # 尝试写入但影响 0 行（需求 5.1）
    trace_id: str | None  # 留痕 trace_id


#: 上游无对应记录时的失败原因（需求 5.1：必须给可读原因，不能静默成功）
_NO_UPSTREAM_ROW_REASON = (
    "上游附注中找不到该章节记录（未生成或已删除），回填未写入任何数据；"
    "请先在附注模块生成该章节后重试"
)


# ─── DeliverableWritebackService ─────────────────────────────────────────────


TERMINAL_STATUSES = frozenset({"signed", "confirmed", "archived"})


class DeliverableWritebackService:
    """出品物回填管道核心服务。

    集成合规护栏（Task 12）、冲突检测（Task 14）、留痕（Task 15）。
    显式按钮触发，不自动回填。
    Task 13: 完整回填主流程（diff→护栏→写回→留痕）。
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._section_state_service = DeliverableSectionStateService(db)
        #: 上一次 `_extract_sections_from_docx` 解析出的 section_code → 块 XML。
        #: 供第 4a 步护栏分类按**块内结构**定位（需求 8.5：不得用正则猜测）。
        #: 每次 extract 覆盖式重置，避免跨次回填串味。
        self._last_block_xml: dict[str, str] = {}
        #: 当前回填的上游适配器（Wave 3 Task 18）。默认附注 —— 与抽适配器之前的
        #: 硬编码行为等价，使**直接调用** `_write_text_content` 的既有测试零改动。
        #: `writeback()` 会在主流程里按 doc_type 覆盖它。
        from app.services.writeback_target_adapters import DisclosureNoteAdapter

        self._adapter: Any = DisclosureNoteAdapter(db)

    # ─── Task 12.1: 合规护栏分类 ──────────────────────────────────────────────

    def _classify_change(
        self,
        section_code: str,
        old_note_text: str | None,
        new_block_xml: str,
    ) -> list[ChangeClassification]:
        """对一个章节块内的变更项分类。

        判定依据（按块内结构定位，非正则猜测）（需求 6.1~6.6, 7.5）：
        - 章节块内的「表格元素」(<w:tbl>) 中的数字单元格 → TABLE
        - 章节标题段落（块首标题行，由 {{seq:}} 编号 + section 名构成）→ TITLE
        - 其余正文段落（叙述性文字）→ TEXT

        Args:
            section_code: 章节编码
            old_note_text: 原 DB text_content（基线）
            new_block_xml: 新的块内 XML 文本

        Returns:
            list of ChangeClassification，每项对应一类变更
        """
        from xml.etree import ElementTree as ET

        classifications: list[ChangeClassification] = []

        # 命名空间定义
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        # 解析 XML 块
        try:
            # 包装为有效 XML（块可能不是完整文档）
            wrapped = f"<root xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>{new_block_xml}</root>"
            root = ET.fromstring(wrapped)
        except ET.ParseError:
            # XML 解析失败，将整个内容视为 TEXT
            logger.warning(
                "XML parse failed for section %s, treating as TEXT",
                section_code,
            )
            text_content = new_block_xml.strip()
            if text_content and text_content != (old_note_text or "").strip():
                classifications.append(
                    ChangeClassification(
                        kind=ChangeKind.TEXT,
                        section_code=section_code,
                        content=text_content,
                        rejection_reason=None,
                    )
                )
            return classifications

        # 1. 检测表格元素 <w:tbl>
        tables = root.findall(".//w:tbl", ns)
        if tables:
            # 检查表格中是否有数字单元格
            has_numeric_cells = False
            table_text_parts: list[str] = []
            for tbl in tables:
                cells = tbl.findall(".//w:tc", ns)
                for cell in cells:
                    cell_text = "".join(
                        t.text or ""
                        for t in cell.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
                    ).strip()
                    if cell_text:
                        table_text_parts.append(cell_text)
                    # 数字判定：去除千分符/负号/小数点后是否纯数字
                    cleaned = cell_text.replace(",", "").replace("，", "").replace("-", "").replace(".", "")
                    if cleaned and cleaned.isdigit() and len(cleaned) >= 1:
                        has_numeric_cells = True

            if has_numeric_cells:
                # 表格含数字 → TABLE 拒绝
                classifications.append(
                    ChangeClassification(
                        kind=ChangeKind.TABLE,
                        section_code=section_code,
                        content=" | ".join(table_text_parts) or "[表格数据]",
                        rejection_reason=_TABLE_REJECTION_REASON,
                    )
                )

        # 2. 检测标题段落（块首段落含 {{seq:}} 或是编号+名称格式）
        paragraphs = root.findall("w:p", ns)
        text_paragraphs: list[str] = []

        for i, para in enumerate(paragraphs):
            para_text = "".join(
                t.text or ""
                for t in para.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
            ).strip()

            if not para_text:
                continue

            # 块首标题判定：首个非空段落 + 匹配标题模式
            if i == 0 or (i <= 1 and not text_paragraphs):
                if _is_title_paragraph(para_text, section_code):
                    classifications.append(
                        ChangeClassification(
                            kind=ChangeKind.TITLE,
                            section_code=section_code,
                            content=para_text,
                            rejection_reason=_TITLE_REJECTION_REASON,
                        )
                    )
                    continue

            # 非标题、非表格内的段落 → 候选 TEXT
            # 排除属于 <w:tbl> 内部的段落
            is_in_table = any(
                ancestor.tag == f"{{{ns['w']}}}tbl"
                for ancestor in _iter_ancestors_elem(para, root)
            )
            if not is_in_table:
                text_paragraphs.append(para_text)

        # 3. 文字段落汇总作为 TEXT 变更
        if text_paragraphs:
            combined_text = "\n".join(text_paragraphs)
            old_text = (old_note_text or "").strip()
            new_text = combined_text.strip()

            if new_text != old_text:
                classifications.append(
                    ChangeClassification(
                        kind=ChangeKind.TEXT,
                        section_code=section_code,
                        content=new_text,
                        rejection_reason=None,
                    )
                )

        return classifications

    # ─── Task 14.1: 三方比对冲突检测 ─────────────────────────────────────────

    async def _detect_conflict(
        self,
        word_export_task_id: UUID,
        project_id: UUID,
        year: int,
        section_code: str,
        deliverable_text: str,
    ) -> WritebackConflict | None:
        """三方比对冲突检测。

        冲突判定（Property 19）：current_db_hash ≠ baseline_hash
        → 上游在出品物生成后被独立修改。

        Args:
            word_export_task_id: 出品物标识
            project_id: 项目 ID
            year: 年度
            section_code: 章节编码
            deliverable_text: 出品物侧当前编辑值

        Returns:
            WritebackConflict 如有冲突，None 如无冲突
        """
        import sqlalchemy as sa

        from app.models.audit_platform_models import DeliverableSectionState

        # 1. 读取基线 hash（生成时快照）
        state_stmt = sa.select(
            DeliverableSectionState.source_snapshot_hash,
            DeliverableSectionState.last_writeback_baseline_hash,
        ).where(
            DeliverableSectionState.word_export_task_id == word_export_task_id,
            DeliverableSectionState.section_code == section_code,
        )
        state_result = await self.db.execute(state_stmt)
        state_row = state_result.first()

        if state_row is None:
            # 无基线记录 → 视为无冲突（首次回填无参照）
            return None

        baseline_hash = state_row.source_snapshot_hash

        # 2. 计算当前 DB 内容 hash
        current_hash = await self._section_state_service.compute_source_snapshot_hash(
            project_id, year, section_code
        )

        # 3. 冲突判定：current_db_hash ≠ baseline_hash
        if current_hash == baseline_hash:
            # 上游未变 → 无冲突，可直接写回
            return None

        # 4. 上游已变 → 检查是否幂等（双方改成一样）
        #    上游读取走适配器（Wave 3 Task 18）：报告正文的上游是
        #    AuditReport.report_body_json.sections，不是 disclosure_notes。
        upstream_value = await self._adapter.read_upstream(
            project_id, year, section_code
        )

        if _normalize_text(deliverable_text) == _normalize_text(upstream_value):
            # 双方改成一样 → 幂等跳过（实质无冲突）
            return None

        # 5. 真冲突 → 呈现三方内容
        # baseline_value: 基线时刻的 text_content（近似用 hash 对应时的值，
        # 实际中可从 trace_events 回溯，此处简化为标注"生成时基线"）
        # 由于我们不单独存储基线文本（只存 hash），baseline_value 以
        # "基线已变更，hash={baseline_hash}" 标注；
        # 在实际实现中可从 trace_events 或 version 链恢复完整文本。
        # 此处用上游值近似减去变更（设计简化）
        baseline_value = f"[生成时基线 hash={baseline_hash[:16]}...]"

        return WritebackConflict(
            section_code=section_code,
            deliverable_value=deliverable_text,
            upstream_value=upstream_value,
            baseline_value=baseline_value,
        )

    async def _resolve_conflict_and_write(
        self,
        word_export_task_id: UUID,
        project_id: UUID,
        year: int,
        section_code: str,
        resolution: str,
        conflict: WritebackConflict,
        actor_id: UUID,
    ) -> tuple[str | None, int]:
        """裁决冲突并写回 + 更新基线。

        Args:
            resolution: "deliverable" | "upstream" | 自定义文本
            conflict: 冲突三方内容

        Returns:
            ``(写回的值, 受影响行数)``。选择 ``upstream`` 时值为 None 且行数记 1
            （「保留上游」是有效裁决，不是失败）；写 DB 但影响 0 行时行数为 0，
            **此时不更新基线**（需求 5.4）。
        """
        import sqlalchemy as sa

        from app.models.audit_platform_models import DeliverableSectionState

        # 确定写回值
        if resolution == "upstream":
            # 保留上游值 → 不修改 DB，但更新基线
            write_value = None
        elif resolution == "deliverable":
            write_value = conflict["deliverable_value"]
        else:
            # 自定义文本
            write_value = resolution

        # 写回上游（如非 upstream 裁决）—— 走适配器，不硬编码 DisclosureNote
        rowcount = 1  # upstream 裁决不写库，视为有效裁决
        if write_value is not None:
            rowcount = await self._adapter.write_upstream(
                project_id, year, section_code, write_value
            )
            if rowcount == 0:
                logger.warning(
                    "writeback: 冲突裁决写入章节 %s 影响 0 行，不更新基线",
                    section_code,
                )
                return None, 0

        # 更新基线 hash（需求 8.6）
        new_hash = await self._section_state_service.compute_source_snapshot_hash(
            project_id, year, section_code
        )
        update_baseline_stmt = (
            sa.update(DeliverableSectionState)
            .where(
                DeliverableSectionState.word_export_task_id == word_export_task_id,
                DeliverableSectionState.section_code == section_code,
            )
            .values(
                source_snapshot_hash=new_hash,
                last_writeback_baseline_hash=new_hash,
                is_stale=False,
            )
        )
        await self.db.execute(update_baseline_stmt)
        await self.db.flush()

        return write_value, rowcount

    # ─── Task 15.1: TraceEventService 留痕 ───────────────────────────────────

    async def _log_writeback(
        self,
        *,
        project_id: UUID,
        word_export_task_id: UUID,
        section_code: str,
        actor_id: UUID,
        action: str,
        before_text: str | None,
        after_text: str | None,
        content_hash: str | None = None,
        version_no: int | None = None,
        rejection_reason: str | None = None,
        trace_id: str | None = None,
    ) -> str:
        """回填/冲突裁决留痕（需求 9.1/9.2/9.3/7.7/8.5）。

        每次回填/冲突裁决写回经 TraceEventService.write 记录：
        - before/after snapshot + content_hash（需求 9.1/9.2）
        - 操作人/时间/出品物标识与版本/section_code（需求 9.2）
        - 被护栏拒绝的变更同样留痕 + 拒绝原因（需求 9.3）
        - 复用既有"写入失败不阻断主业务"语义

        Args:
            project_id: 项目 ID
            word_export_task_id: 出品物标识
            section_code: 章节编码
            actor_id: 操作人 ID
            action: 动作描述（writeback/conflict_resolution/rejected）
            before_text: 变更前内容
            after_text: 变更后内容
            content_hash: 内容哈希
            version_no: 出品物版本号
            rejection_reason: 拒绝原因（被拒变更留痕用）
            trace_id: 可选指定 trace_id（同一批次共享）

        Returns:
            trace_id
        """
        before_snapshot = {
            "section_code": section_code,
            "text_content": before_text or "",
            "word_export_task_id": str(word_export_task_id),
        }
        after_snapshot = {
            "section_code": section_code,
            "text_content": after_text or "",
            "word_export_task_id": str(word_export_task_id),
        }

        if rejection_reason:
            after_snapshot["rejection_reason"] = rejection_reason
            after_snapshot["rejected"] = True

        # 计算 content_hash（如未提供）
        if content_hash is None and after_text is not None:
            content_hash = compute_snapshot_hash_from_parts(
                section_code=section_code,
                text_content=after_text,
                table_data=None,
                audited_amounts=[],
            )

        # 确定 event_type
        if rejection_reason:
            event_type = "deliverable.writeback.rejected"
        elif action == "conflict_resolution":
            event_type = "deliverable.writeback.conflict_resolved"
        else:
            event_type = "deliverable.writeback.written"

        result_trace_id = await trace_event_service.write(
            db=self.db,
            project_id=project_id,
            event_type=event_type,
            object_type="deliverable_section",
            object_id=word_export_task_id,
            actor_id=actor_id,
            action=action,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            content_hash=content_hash,
            version_no=version_no,
            trace_id=trace_id,
        )

        return result_trace_id

    # ─── Task 13.1: 章节级 diff ──────────────────────────────────────────────

    async def _extract_sections_from_docx(
        self, docx_bytes: bytes
    ) -> dict[str, str]:
        """下载 docx → 按章节区间切块 → 提取 TEXT 段落文字。

        定位走 ``resolve_section_blocks``（锚点优先、``##SECTION:`` 标记回退）：
        **交付 docx 的 ``##SECTION:`` 标记在导出末尾已被 remove_section_markers 清掉**，
        只用 scan_section_blocks 会恒得空 dict → 回填永远「无变更」且不报错
        （历史缺陷即此）。

        Returns:
            {section_code: normalized_text} 仅含章节区间内的正文段落文字。
        """
        from docx import Document
        from docx.oxml.ns import qn
        from lxml import etree

        from app.services.section_anchor_utils import resolve_section_blocks

        doc = Document(BytesIO(docx_bytes))
        mode, blocks = resolve_section_blocks(doc)
        if mode == "none":
            logger.warning(
                "writeback: 交付 docx 既无章节锚点也无 ##SECTION 标记，无法定位章节；"
                "该交付件可能生成于锚点接线之前，请重新生成后再回填"
            )
            return {}
        logger.info("writeback: 章节定位模式=%s blocks=%d", mode, len(blocks))

        ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        sections: dict[str, str] = {}
        self._last_block_xml = {}

        for block in blocks:
            text_parts: list[str] = []
            xml_parts: list[str] = []
            for el in block.elements:
                # 块内原始 XML 留给护栏分类（需求 8.5：按块内结构定位，不用正则猜）
                try:
                    xml_parts.append(
                        etree.tostring(el, encoding="unicode")
                    )
                except Exception:  # noqa: BLE001 — 单个元素序列化失败不影响文字提取
                    pass
                if el.tag == qn("w:p"):
                    para_text = "".join(
                        t.text or ""
                        for t in el.iter(f"{{{ns_w}}}t")
                    ).strip()
                    # 排除 SECTION 标记行和标题行
                    if para_text and not para_text.startswith("##"):
                        if not _is_title_paragraph(para_text, block.section_code):
                            text_parts.append(para_text)
                # 表格跳过（仅提取 TEXT 段落）
            sections[block.section_code] = _normalize_text("\n".join(text_parts))
            self._last_block_xml[block.section_code] = "".join(xml_parts)

        return sections

    def _compute_section_diff(
        self,
        docx_sections: dict[str, str],
        db_sections: dict[str, str],
    ) -> dict[str, tuple[str, str]]:
        """文本比对：返回 {section_code: (docx_text, db_text)} 仅含变更章节。

        对同一 section_code，normalize 后 docx_text ≠ db_text → 视为变更。
        仅出品物中存在且 DB 中也存在的章节参与比对。
        """
        diff: dict[str, tuple[str, str]] = {}
        for code, docx_text in docx_sections.items():
            db_text = db_sections.get(code, "")
            normalized_docx = _normalize_text(docx_text)
            normalized_db = _normalize_text(db_text)
            if normalized_docx != normalized_db:
                diff[code] = (docx_text, db_text)
        return diff

    # ─── Task 13.2: writeback 主流程 ─────────────────────────────────────────

    async def writeback(
        self,
        word_export_task_id: UUID,
        project_id: UUID,
        year: int,
        actor_id: UUID,
        *,
        resolutions: dict[str, str] | None = None,
        docx_bytes: bytes | None = None,
    ) -> WritebackResult:
        """完整回填主流程（需求 7）。

        步骤:
        0. 终态检查（signed/confirmed/archived → 拒绝）
        1. 下载当前 docx
        2. scan_section_blocks 按锚点分块 → 提取 TEXT 段落
        3. 加载 DB text_content → 章节级 diff
        4. 对变更章节逐一：护栏分类 → 冲突检测 → 写回/拒绝/跳过
        5. 裁决冲突（若 resolutions 提供）
        6. 留痕
        7. 返回 WritebackResult

        Args:
            word_export_task_id: 出品物标识
            project_id: 项目 ID
            year: 年度
            actor_id: 操作人 ID
            resolutions: 冲突裁决 {section_code: "deliverable"|"upstream"|自定义文本}
            docx_bytes: 可选 docx 字节（测试注入）

        Returns:
            WritebackResult
        """
        import sqlalchemy as sa
        import uuid as uuid_mod


        # ─── 0. 终态检查 ─────────────────────────────────────────────────────
        terminal = await self._check_terminal_status(word_export_task_id)
        if terminal:
            raise ValueError(
                f"该出品物已{terminal}，不可回填或刷新；"
                "如需修改请走撤回/解锁流程"
            )

        # ─── 1. 下载当前 docx ────────────────────────────────────────────────
        if docx_bytes is None:
            docx_bytes = await self._download_current_docx(word_export_task_id)

        if docx_bytes is None:
            # 下载失败 → 保留原值（需求 7.8）
            logger.error(
                "writeback: 下载 docx 失败 task=%s, 保留原值",
                word_export_task_id,
            )
            return WritebackResult(
                written=[],
                rejected=[],
                conflicts=[],
                skipped=[],
                failed=[],
                trace_id=None,
            )

        # ─── 1.5 选上游适配器（Wave 3 Task 18 / 需求 9.2、9.5）────────────────
        #
        # 历史实现把 DisclosureNote 硬编码在五处 → 报告正文交付件点回填也去写
        # disclosure_notes（章节标识 `opinion` 与附注章节号不是同一命名空间）
        # ⇒ UPDATE 恒 0 行，而 rowcount 未检查时还报「回填成功」。
        adapter = await self._resolve_adapter(word_export_task_id)
        if adapter is None:
            logger.warning(
                "writeback: 该交付件类型不支持回填 task=%s", word_export_task_id
            )
            return WritebackResult(
                written=[], rejected=[], conflicts=[], skipped=[], failed=[],
                trace_id=None,
            )
        self._adapter = adapter

        # ─── 2. 按锚点分块 + 提取 TEXT ─────────────────────────────────────
        try:
            docx_sections = await self._extract_sections_for(adapter, docx_bytes)
        except Exception as exc:
            logger.error(
                "writeback: docx 解析失败 task=%s: %s, 保留原值",
                word_export_task_id,
                exc,
            )
            return WritebackResult(
                written=[],
                rejected=[],
                conflicts=[],
                skipped=[],
                failed=[],
                trace_id=None,
            )

        if not docx_sections:
            return WritebackResult(
                written=[],
                rejected=[],
                conflicts=[],
                skipped=[],
                failed=[],
                trace_id=None,
            )

        # ─── 3. 加载上游当前文字 + diff ─────────────────────────────────────
        db_sections: dict[str, str] = {}
        section_codes = list(docx_sections.keys())

        for code in section_codes:
            db_sections[code] = await adapter.read_upstream(project_id, year, code)

        diff = self._compute_section_diff(docx_sections, db_sections)

        if not diff:
            return WritebackResult(
                written=[],
                rejected=[],
                conflicts=[],
                skipped=[],
                failed=[],
                trace_id=None,
            )

        # ─── 4. 逐章节处理 ──────────────────────────────────────────────────
        written: list[str] = []
        rejected: list[ChangeClassification] = []
        failed: list[WritebackFailure] = []
        conflicts: list[WritebackConflict] = []
        skipped: list[str] = []
        trace_id = str(uuid_mod.uuid4())

        for code, (docx_text, db_text) in diff.items():
            # 锚点丢失检测：若该 section_code 不在 docx_sections 中 → 跳过
            # （此处 diff 保证都在 docx_sections，但做防御）
            if code not in docx_sections:
                skipped.append(code)
                continue

            # 4a. 护栏分类（需求 8.1：必须调用护栏，不得硬编码为纯文字变更）
            #
            # 🔴 历史缺陷：此处曾硬编码 `[ChangeClassification(kind=TEXT, ...)]` 并注释
            # 「简化」，于是 130 行的 `_classify_change`（TABLE/TITLE 拒绝 + 拒绝留痕，
            # design 标「审计底线 Property 16」）**全仓零生产调用方** → `rejected` 恒空、
            # 需求 8.4 的被拒变更留痕从未产生。表格/标题写不进去只是因为提取阶段过滤掉了，
            # 不是护栏在起作用 —— 一旦提取逻辑放宽，数字就能直接写回上游。
            block_xml = self._last_block_xml.get(code, "")
            if block_xml:
                classifications = self._classify_change(code, db_text, block_xml)
            else:
                # 拿不到块 XML（序列化失败等）→ 退回文字分类，但记 warning：
                # 此时护栏对表格/标题不设防，属可观测的降级而非静默。
                logger.warning(
                    "writeback: 章节 %s 无块 XML，护栏降级为纯文字分类", code
                )
                classifications = [
                    ChangeClassification(
                        kind=ChangeKind.TEXT,
                        section_code=code,
                        content=docx_text,
                        rejection_reason=None,
                    )
                ]

            if not classifications:
                # 护栏判定「无实质变更」（如仅空白差异）→ 跳过，不写不拒
                skipped.append(code)
                continue

            # 对每个分类做处理
            for cls_item in classifications:
                if cls_item["kind"] == ChangeKind.TABLE:
                    rejected.append(cls_item)
                    # 留痕：被拒变更（需求 9.3）
                    await self._log_writeback(
                        project_id=project_id,
                        word_export_task_id=word_export_task_id,
                        section_code=code,
                        actor_id=actor_id,
                        action="rejected",
                        before_text=db_text,
                        after_text=docx_text,
                        rejection_reason=cls_item["rejection_reason"],
                        trace_id=trace_id,
                    )
                    continue

                if cls_item["kind"] == ChangeKind.TITLE:
                    rejected.append(cls_item)
                    await self._log_writeback(
                        project_id=project_id,
                        word_export_task_id=word_export_task_id,
                        section_code=code,
                        actor_id=actor_id,
                        action="rejected",
                        before_text=db_text,
                        after_text=docx_text,
                        rejection_reason=cls_item["rejection_reason"],
                        trace_id=trace_id,
                    )
                    continue

                # TEXT → 4b. 冲突检测
                if resolutions and code in resolutions:
                    # 有裁决 → 执行裁决
                    conflict = await self._detect_conflict(
                        word_export_task_id, project_id, year, code, docx_text
                    )
                    if conflict:
                        _value, rowcount = await self._resolve_conflict_and_write(
                            word_export_task_id,
                            project_id,
                            year,
                            code,
                            resolutions[code],
                            conflict,
                            actor_id,
                        )
                        if rowcount == 0:
                            failed.append(
                                WritebackFailure(
                                    section_code=code,
                                    reason=_NO_UPSTREAM_ROW_REASON,
                                )
                            )
                            await self._log_writeback(
                                project_id=project_id,
                                word_export_task_id=word_export_task_id,
                                section_code=code,
                                actor_id=actor_id,
                                action="rejected",
                                before_text=db_text,
                                after_text=docx_text,
                                rejection_reason=_NO_UPSTREAM_ROW_REASON,
                                trace_id=trace_id,
                            )
                            continue
                        written.append(code)
                        await self._log_writeback(
                            project_id=project_id,
                            word_export_task_id=word_export_task_id,
                            section_code=code,
                            actor_id=actor_id,
                            action="conflict_resolution",
                            before_text=db_text,
                            after_text=docx_text,
                            trace_id=trace_id,
                        )
                    else:
                        # 无冲突但有 resolution → 直接写
                        rowcount = await self._write_text_content(
                            project_id, year, code, docx_text, word_export_task_id
                        )
                        if rowcount == 0:
                            failed.append(
                                WritebackFailure(
                                    section_code=code,
                                    reason=_NO_UPSTREAM_ROW_REASON,
                                )
                            )
                            await self._log_writeback(
                                project_id=project_id,
                                word_export_task_id=word_export_task_id,
                                section_code=code,
                                actor_id=actor_id,
                                action="rejected",
                                before_text=db_text,
                                after_text=docx_text,
                                rejection_reason=_NO_UPSTREAM_ROW_REASON,
                                trace_id=trace_id,
                            )
                            continue
                        written.append(code)
                        await self._log_writeback(
                            project_id=project_id,
                            word_export_task_id=word_export_task_id,
                            section_code=code,
                            actor_id=actor_id,
                            action="writeback",
                            before_text=db_text,
                            after_text=docx_text,
                            trace_id=trace_id,
                        )
                else:
                    # 无裁决 → 检测冲突
                    conflict = await self._detect_conflict(
                        word_export_task_id, project_id, year, code, docx_text
                    )
                    if conflict:
                        conflicts.append(conflict)
                    else:
                        # 无冲突 → 直接写回
                        rowcount = await self._write_text_content(
                            project_id, year, code, docx_text, word_export_task_id
                        )
                        if rowcount == 0:
                            # 需求 5.1：影响 0 行不得计入 written（历史缺陷：静默成功）
                            failed.append(
                                WritebackFailure(
                                    section_code=code,
                                    reason=_NO_UPSTREAM_ROW_REASON,
                                )
                            )
                            await self._log_writeback(
                                project_id=project_id,
                                word_export_task_id=word_export_task_id,
                                section_code=code,
                                actor_id=actor_id,
                                action="rejected",
                                before_text=db_text,
                                after_text=docx_text,
                                rejection_reason=_NO_UPSTREAM_ROW_REASON,
                                trace_id=trace_id,
                            )
                            continue
                        written.append(code)
                        # 触发 NOTE_SECTION_SAVED 事件（需求 7.6）
                        await self._emit_note_saved(
                            project_id, year, code, word_export_task_id
                        )
                        await self._log_writeback(
                            project_id=project_id,
                            word_export_task_id=word_export_task_id,
                            section_code=code,
                            actor_id=actor_id,
                            action="writeback",
                            before_text=db_text,
                            after_text=docx_text,
                            trace_id=trace_id,
                        )

        return WritebackResult(
            written=written,
            rejected=rejected,
            conflicts=conflicts,
            skipped=skipped,
            failed=failed,
            trace_id=trace_id,
        )

    # ─── Private helpers for writeback ───────────────────────────────────────

    async def _check_terminal_status(self, word_export_task_id: UUID) -> str | None:
        """检查出品物是否处于终态。"""
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
        """下载出品物当前最新版本 docx。"""
        from pathlib import Path

        from sqlalchemy import text

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
            return None

        file_path = Path(row[0])
        if not file_path.exists():
            return None

        return file_path.read_bytes()

    async def _resolve_adapter(self, word_export_task_id: UUID):
        """按交付件 doc_type 取上游适配器（Wave 3 Task 18）。

        取不到 doc_type 时**回退附注适配器** —— 与引入前行为等价（历史实现即硬编码
        附注），保证「读不到元数据」不会让既有附注回填突然失效；
        真正的门控在端点层（`deliverable_capabilities` 的 400 校验）。
        """
        import sqlalchemy as sa

        from app.models.phase13_models import WordExportTask
        from app.services.writeback_target_adapters import (
            DisclosureNoteAdapter,
            get_writeback_adapter,
        )

        try:
            stmt = sa.select(WordExportTask.doc_type).where(
                WordExportTask.id == word_export_task_id
            )
            result = await self.db.execute(stmt)
            doc_type = result.scalar_one_or_none()
        except Exception:  # noqa: BLE001 — 读不到不阻断，退回既有行为
            logger.warning(
                "writeback: 读取 doc_type 失败，回退附注适配器 task=%s",
                word_export_task_id,
                exc_info=True,
            )
            return DisclosureNoteAdapter(self.db)

        if doc_type is None:
            return DisclosureNoteAdapter(self.db)
        return get_writeback_adapter(self.db, doc_type)

    async def _extract_sections_for(self, adapter, docx_bytes: bytes) -> dict[str, str]:
        """按适配器种类提取章节文字。

        附注侧仍走 ``_extract_sections_from_docx`` —— 它同时采集块 XML 供护栏使用
        （护栏需要 ``w:tbl`` 结构，适配器协议只返回文字，故不能收进适配器）。
        """
        from app.services.writeback_target_adapters import DisclosureNoteAdapter

        if isinstance(adapter, DisclosureNoteAdapter):
            return await self._extract_sections_from_docx(docx_bytes)
        # 其他上游：护栏降级为纯文字分类（报告正文段落无表格数字回写场景）
        self._last_block_xml = {}
        return await adapter.extract_sections(docx_bytes)

    async def _write_text_content(
        self,
        project_id: UUID,
        year: int,
        section_code: str,
        new_text: str,
        word_export_task_id: UUID,
    ) -> int:
        """写回上游 + 更新基线。

        上游由 ``self._adapter`` 决定（附注 / 报告正文），**不再硬编码 DisclosureNote**。

        Returns:
            受影响行数。**0 表示上游无对应记录 → 调用方必须计入 ``failed`` 而非
            ``written``**（需求 5.1）；此时不更新基线 hash（需求 5.4），否则会把
            「没写进去」记成「已同步」。
        """
        import sqlalchemy as sa

        from app.models.audit_platform_models import DeliverableSectionState

        adapter = self._adapter
        rowcount = await adapter.write_upstream(
            project_id, year, section_code, new_text
        )
        if rowcount == 0:
            logger.warning(
                "writeback: 章节 %s 写入影响 0 行（上游%s无对应记录），"
                "不计入成功、不更新基线",
                section_code,
                adapter.upstream_label,
            )
            return 0

        # 更新基线 hash
        new_hash = await self._section_state_service.compute_source_snapshot_hash(
            project_id, year, section_code
        )
        update_baseline = (
            sa.update(DeliverableSectionState)
            .where(
                DeliverableSectionState.word_export_task_id == word_export_task_id,
                DeliverableSectionState.section_code == section_code,
            )
            .values(
                source_snapshot_hash=new_hash,
                last_writeback_baseline_hash=new_hash,
                is_stale=False,
            )
        )
        await self.db.execute(update_baseline)
        await self.db.flush()
        return rowcount

    async def _emit_note_saved(
        self,
        project_id: UUID,
        year: int,
        section_code: str,
        word_export_task_id: UUID,
    ) -> None:
        """触发 NOTE_SECTION_SAVED 事件，携带 writeback_source_deliverable_id（需求 7.6/4.9）。

        注意：``event_bus.publish`` 仅接受单个 ``EventPayload`` 位置参数。
        下游 ``_on_upstream_changed_mark_deliverable_stale`` handler 从
        ``payload.extra`` 读取 ``section_code`` 与 ``writeback_source_deliverable_id``，
        二者必须同处 extra（早期误传裸 dict + 关键字参数会抛 TypeError 被静默吞掉，
        导致回写后其他出品物章节不被标 stale → 联动链断裂）。
        """
        try:
            from app.services.event_bus import event_bus
            from app.models.audit_platform_schemas import EventPayload, EventType

            await event_bus.publish(
                EventPayload(
                    event_type=EventType.NOTE_SECTION_SAVED,
                    project_id=project_id,
                    year=year,
                    extra={
                        "section_code": section_code,
                        "writeback_source_deliverable_id": str(word_export_task_id),
                    },
                )
            )
        except Exception as exc:
            # 事件发布失败不阻断主业务
            logger.warning(
                "Failed to emit NOTE_SECTION_SAVED for section %s: %s",
                section_code,
                exc,
            )


# ─── 辅助函数 ────────────────────────────────────────────────────────────────


def _normalize_text(text: str) -> str:
    """规范化文本：去首尾空白、统一换行、合并连续空白。

    用于 diff 比较，消除格式噪声。
    """
    import re

    if not text:
        return ""
    # 统一换行
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 合并连续空白（保留换行符）
    text = re.sub(r"[^\S\n]+", " ", text)
    # 合并连续换行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_title_paragraph(para_text: str, section_code: str) -> bool:
    """判断段落是否为章节标题（块首标题行）。

    标题模式：
    - 含 {{seq:}} 占位符（编号模板）
    - 编号 + 名称格式（如 "（一）货币资金"、"1. 应收账款"）
    - 编号后跟中文字符（确保是真正的标题而非数值内容）
    """
    import re

    # {{seq:}} 占位符 → 明确标题
    if "{{seq:" in para_text:
        return True

    # 中文数字编号模式（一）（二）...
    if re.match(r"^[（(][一二三四五六七八九十百千万]+[）)]", para_text):
        return True

    # 阿拉伯数字编号模式：数字 + 分隔符 + 中文/字母名称
    # 要求分隔符后紧跟的是中文字符或字母（排除纯数字如 "0.0"）
    if re.match(r"^\d+[.、．]\s*[\u4e00-\u9fff\u3400-\u4dbfA-Za-z]", para_text):
        return True

    # section_code 中的编号前缀匹配（仅匹配数字+分隔符+中文字符的模式）
    code_parts = section_code.split("、")
    if len(code_parts) >= 2:
        sub_number = code_parts[-1]
        # 检查是否以该数字开头并后跟中文标题
        if re.match(
            rf"^{re.escape(sub_number)}[.、．]\s*[\u4e00-\u9fff\u3400-\u4dbfA-Za-z]",
            para_text,
        ):
            return True

    return False


def _iter_ancestors(element, root):
    """简化版祖先迭代（XML ElementTree 不直接支持 parent 遍历）。"""
    # ElementTree 不维护 parent 引用，此处返回空列表
    # 实际实现中应使用 lxml 或手动构建 parent map
    return []


def _iter_ancestors_elem(element, root):
    """构建 parent map 并迭代祖先元素。"""
    parent_map = {c: p for p in root.iter() for c in p}
    ancestors = []
    current = element
    while current in parent_map:
        current = parent_map[current]
        ancestors.append(current)
    return ancestors
