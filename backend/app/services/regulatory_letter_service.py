"""regulatory_letter_service — A18-2 与监管层沟通函 Word 导出编排

调用共享 docx_template_filler 生成 Word；
导出前执行完整性检查（适用议题已填写、不适用议题删除）。

设计要点（见 .kiro/specs/a18-regulatory-communication/design.md）：
- 颜色语义处理统一由 docx_template_filler.fill_and_export 负责
- 本模块负责：数据组装、完整性检查、模板定位、调用 filler
- 议题数据从 checklist_responses 表加载（item_id LIKE 'A18-2-%'）
- issue_hints 从 issue_tickets 表读取舞弊/违规标题启发式
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.docx_template_filler import (
    export_to_bytes,
    fill_and_export,
)

logger = logging.getLogger(__name__)

# ─── 模板路径 ────────────────────────────────────────────────────────────────

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_PATH = _BACKEND_ROOT / "wp_templates" / "A" / "A18-2 与监管层沟通函 (通用)2019.docx"

# ─── 议题 ID 映射 ────────────────────────────────────────────────────────────

TOPIC_IDS = ["A18-2-001", "A18-2-002", "A18-2-003", "A18-2-004"]
TOPIC_LABELS = ["舞弊", "重大违法行为", "年报信息", "其他事项"]
HEADER_ID = "A18-2-header"

# ─── 红色占位符 ──────────────────────────────────────────────────────────────

_RED_PLACEHOLDER_PATTERNS: list[re.Pattern] = [
    re.compile(r"XX"),
    re.compile(r"201X"),
    re.compile(r"202X"),
    re.compile(r"××"),
]


class RegulatoryLetterService:
    """编排 A18-2 议题数据 → Word 文档"""

    async def check_completeness(
        self, db: AsyncSession, project_id: UUID, wp_id: UUID
    ) -> dict:
        """检查所有适用议题是否已填写。

        Returns:
            {
                has_incomplete: bool,
                count: int,
                incomplete_topics: list[str],
                wp_code: "A18-2",
            }
        """
        responses = await self._load_topic_responses(db, wp_id)
        incomplete_topics: list[str] = []

        for i, topic_id in enumerate(TOPIC_IDS):
            data = responses.get(topic_id)
            if not data:
                # 未填写任何内容 → incomplete
                incomplete_topics.append(TOPIC_LABELS[i])
                continue
            conclusion = data.get("conclusion", "")
            remark = data.get("remark", "")
            # 适用但无内容 → incomplete
            if conclusion == "Y":
                try:
                    parsed = json.loads(remark) if remark else {}
                except (json.JSONDecodeError, TypeError):
                    parsed = {}
                content = parsed.get("content", "")
                if not content or not content.strip():
                    incomplete_topics.append(TOPIC_LABELS[i])

        return {
            "has_incomplete": len(incomplete_topics) > 0,
            "count": len(incomplete_topics),
            "incomplete_topics": incomplete_topics,
            "wp_code": "A18-2",
        }

    async def export_word(
        self, db: AsyncSession, project_id: UUID, wp_id: UUID
    ) -> bytes:
        """导出 A18-2 Word 文档。

        流程：
        1. 加载议题数据 + 表头
        2. 打开模板，调用 fill_and_export 处理颜色语义（红色替换/蓝色删/注释表删）
        3. 将议题内容注入文档
        4. 返回 docx 字节流
        """
        try:
            from docx import Document
        except ImportError:
            raise RuntimeError("python-docx 未安装，无法导出 Word")

        responses = await self._load_topic_responses(db, wp_id)
        header = await self._load_header(db, wp_id)
        project_ctx = await self._load_project_context(db, project_id)

        # 组装 context dict（供 build_replacements 使用）
        context: dict = {
            "client_name": header.get("companyName") or project_ctx.get("client_name", ""),
            "audit_year": header.get("auditYear") or project_ctx.get("audit_year", ""),
        }

        # 打开模板
        if not _TEMPLATE_PATH.exists():
            logger.error("A18-2 Word 模板不存在: %s", _TEMPLATE_PATH)
            raise FileNotFoundError(f"模板不存在: {_TEMPLATE_PATH}")

        doc = Document(str(_TEMPLATE_PATH))

        # 调用 filler 处理颜色语义（蓝删/红替换转黑/注释表删）
        doc, _fill_result = fill_and_export(doc, context)

        # 注入议题内容（适用议题追加描述段落）
        self._inject_topic_content(doc, responses)

        # 导出为 bytes
        return export_to_bytes(doc)

    def _inject_topic_content(self, doc, responses: dict[str, dict]) -> None:
        """将议题描述内容追加到文档末尾（简化版：适用议题逐段写入）"""
        for i, topic_id in enumerate(TOPIC_IDS):
            data = responses.get(topic_id)
            if not data:
                continue
            conclusion = data.get("conclusion", "")
            if conclusion != "Y":
                continue
            try:
                parsed = json.loads(data.get("remark", "{}"))
            except (json.JSONDecodeError, TypeError):
                parsed = {}
            content = parsed.get("content", "")
            if not content:
                continue
            # 议题3 radio choice prepend
            radio = parsed.get("radioChoice", "")
            if radio and i == 2:
                radio_labels = {
                    "no_inconsistency": "未发现重大不一致",
                    "minor_uncorrected": "存在不一致但不重大且未更正",
                    "major_corrected": "存在不一致且重大但已更正",
                }
                content = f"结论：{radio_labels.get(radio, radio)}\n{content}"
            # Add paragraph (simplified — full implementation matches template sections)
            p = doc.add_paragraph()
            p.add_run(f"【{TOPIC_LABELS[i]}】").bold = True
            doc.add_paragraph(content)

    # ─── Private helpers ─────────────────────────────────────────────────────

    async def _load_topic_responses(
        self, db: AsyncSession, wp_id: UUID
    ) -> dict[str, dict]:
        """加载 A18-2 议题响应数据"""
        result = await db.execute(
            text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE 'A18-2-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        rows = result.mappings().all()
        return {
            r["item_id"]: {"conclusion": r["conclusion"], "remark": r["remark"]}
            for r in rows
        }

    async def _load_header(self, db: AsyncSession, wp_id: UUID) -> dict:
        """加载 A18-2 表头数据"""
        result = await db.execute(
            text(
                "SELECT remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = :item_id"
            ),
            {"wp_id": str(wp_id), "item_id": HEADER_ID},
        )
        row = result.scalar_one_or_none()
        if row:
            try:
                return json.loads(row)
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

    async def _load_project_context(
        self, db: AsyncSession, project_id: UUID
    ) -> dict:
        """加载项目上下文（公司名、审计年度）"""
        result = await db.execute(
            text(
                "SELECT client_name, audit_period_end "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(project_id)},
        )
        row = result.mappings().first()
        if not row:
            return {}
        audit_year = ""
        if row["audit_period_end"]:
            audit_year = str(row["audit_period_end"].year)
        return {"client_name": row["client_name"] or "", "audit_year": audit_year}


# ─── Module-level convenience functions ──────────────────────────────────────


async def a18_export_word(db: AsyncSession, project_id: UUID, wp_id: UUID) -> bytes:
    """模块级快捷函数"""
    return await RegulatoryLetterService().export_word(db, project_id, wp_id)


async def a18_check_incomplete(db: AsyncSession, project_id: UUID, wp_id: UUID) -> dict:
    """模块级快捷函数"""
    return await RegulatoryLetterService().check_completeness(db, project_id, wp_id)


# ─── A8 其他信息步骤建议 ─────────────────────────────────────────────────────


async def get_a8_step_suggestion(
    db: AsyncSession, project_id: UUID
) -> dict:
    """读取 A8 程序表 seq 3/4/5 的完成状态，映射到议题3 radio 建议值。

    A8 步骤含义：
    - seq 3/4/5 对应年报其他信息审核程序
    - 全部 completed → "no_inconsistency"
    - 有 in_progress → "minor_uncorrected"
    - 有 pending/未完成 → 无建议

    Returns:
        {"suggested_radio": str | None, "a8_status": dict}
    """
    # 读取 A8 程序表响应
    result = await db.execute(
        text(
            "SELECT item_id, conclusion FROM checklist_responses cr "
            "JOIN wp_index wi ON cr.wp_id = wi.id "
            "WHERE wi.project_id = :pid AND wi.wp_code = 'A8' "
            "AND item_id IN ('A8-seq-3', 'A8-seq-4', 'A8-seq-5')"
        ),
        {"pid": str(project_id)},
    )
    rows = result.mappings().all()

    if not rows:
        return {"suggested_radio": None, "a8_status": {}}

    status_map = {r["item_id"]: r["conclusion"] for r in rows}
    statuses = list(status_map.values())

    suggested = None
    if all(s == "completed" for s in statuses):
        suggested = "no_inconsistency"
    elif any(s == "in_progress" for s in statuses):
        suggested = "minor_uncorrected"

    return {"suggested_radio": suggested, "a8_status": status_map}
