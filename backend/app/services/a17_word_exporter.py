"""a17_word_exporter — A17-1 重大事项概要 Word 导出编排

调用共享 docx_template_filler 生成 Word；
导出前执行完整性检查（蓝色提示已删、XX/红色替换完成）。

设计要点（见 .kiro/specs/a17-summary-workpaper/design.md）：
- 颜色语义处理统一由 docx_template_filler.fill_and_export 负责，本模块不重复实现
- 本模块负责：数据组装、完整性检查、模板定位、调用 filler
- 章节数据从 checklist_responses 表加载（item_id LIKE 'A17-1-ch%'）
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.a17_summary_service import get_chapter_definitions
from app.services.docx_template_filler import (
    ColorSemanticsConfig,
    export_to_bytes,
    fill_and_export,
)

logger = logging.getLogger(__name__)

# ─── 模板路径 ────────────────────────────────────────────────────────────────

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_PATH = _BACKEND_ROOT / "wp_templates" / "A" / "A17-1 重大事项概要汇总.docx"

# ─── 完整性检查：红色占位符正则 ──────────────────────────────────────────────

# 红色占位符模式：XX/201X 年份、××公司 等未替换标记
_RED_PLACEHOLDER_PATTERNS: list[re.Pattern] = [
    re.compile(r"XX"),
    re.compile(r"201X"),
    re.compile(r"202X"),
    re.compile(r"××"),
]

# 蓝色编制提示模式：【注：...】或【...】
_BLUE_GUIDANCE_PATTERN = re.compile(r"【[^】]*】")


# ─── HTML → docx 转换引擎 ────────────────────────────────────────────────────


def _html_to_docx(doc, html_content: str) -> None:
    """将 HTML 内容转换为 Word 文档元素。

    支持:
    - h3/h4 → Heading 3/4 样式段落
    - ul/ol → 列表段落（List Bullet / List Number）
    - strong → bold run
    - em → italic run
    - table → Table 对象
    - br → 换行
    - p/div → 普通段落
    - 不支持的标签 → 静默跳过（保留其文本内容）

    Requirements: 1.6
    """
    from html.parser import HTMLParser

    class _DocxHtmlParser(HTMLParser):
        def __init__(self, document):
            super().__init__()
            self.doc = document
            self.current_paragraph = None
            self.tag_stack: list[str] = []
            self.list_stack: list[str] = []  # 'ul' or 'ol'
            self.table_data: list[list[str]] = []
            self.current_row: list[str] = []
            self.current_cell_text = ""
            self.in_table = False

        def handle_starttag(self, tag: str, attrs):
            tag = tag.lower()
            self.tag_stack.append(tag)

            if tag in ("h3", "h4"):
                level = 3 if tag == "h3" else 4
                self.current_paragraph = self.doc.add_paragraph(style=f"Heading {level}")
            elif tag == "p":
                if not self.in_table:
                    self.current_paragraph = self.doc.add_paragraph()
            elif tag == "div":
                if not self.in_table:
                    self.current_paragraph = self.doc.add_paragraph()
            elif tag in ("ul", "ol"):
                self.list_stack.append(tag)
            elif tag == "li":
                list_type = self.list_stack[-1] if self.list_stack else "ul"
                style = "List Number" if list_type == "ol" else "List Bullet"
                try:
                    self.current_paragraph = self.doc.add_paragraph(style=style)
                except KeyError:
                    # 如果样式不存在，使用普通段落加前缀
                    self.current_paragraph = self.doc.add_paragraph()
            elif tag == "table":
                self.in_table = True
                self.table_data = []
            elif tag == "tr":
                self.current_row = []
            elif tag in ("td", "th"):
                self.current_cell_text = ""
            elif tag == "br":
                if self.current_paragraph is not None:
                    self.current_paragraph.add_run("\n")
            # strong/em/b/i 不创建新段落，在 handle_data 中通过 tag_stack 判断格式

        def handle_endtag(self, tag: str):
            tag = tag.lower()

            if tag in ("td", "th"):
                self.current_row.append(self.current_cell_text)
                self.current_cell_text = ""
            elif tag == "tr":
                self.table_data.append(self.current_row)
                self.current_row = []
            elif tag == "table":
                self._flush_table()
                self.in_table = False
            elif tag in ("ul", "ol"):
                if self.list_stack:
                    self.list_stack.pop()
            elif tag in ("h3", "h4", "p", "div", "li"):
                self.current_paragraph = None

            if self.tag_stack and self.tag_stack[-1] == tag:
                self.tag_stack.pop()

        def handle_data(self, data: str):
            if self.in_table:
                self.current_cell_text += data
                return

            text = data
            if not text:
                return

            if self.current_paragraph is None:
                # 顶层文本，创建段落
                self.current_paragraph = self.doc.add_paragraph()

            run = self.current_paragraph.add_run(text)

            # 根据 tag_stack 设置格式
            if "strong" in self.tag_stack or "b" in self.tag_stack:
                run.bold = True
            if "em" in self.tag_stack or "i" in self.tag_stack:
                run.italic = True

        def _flush_table(self):
            """将收集的表格数据写入 Word Table 对象"""
            if not self.table_data:
                return
            rows = len(self.table_data)
            cols = max((len(row) for row in self.table_data), default=0)
            if rows == 0 or cols == 0:
                return

            table = self.doc.add_table(rows=rows, cols=cols)
            table.style = "Table Grid"
            for r_idx, row_data in enumerate(self.table_data):
                for c_idx, cell_text in enumerate(row_data):
                    if c_idx < cols:
                        table.rows[r_idx].cells[c_idx].text = cell_text

    # 如果内容不含 HTML 标签，按纯文本处理（兼容旧数据）
    if not re.search(r"<[a-zA-Z][^>]*>", html_content):
        for line in html_content.split("\n"):
            stripped = line.strip()
            if stripped:
                doc.add_paragraph(stripped)
        return

    parser = _DocxHtmlParser(doc)
    parser.feed(html_content)


# ─── 公共类 ──────────────────────────────────────────────────────────────────


class A17WordExporter:
    """编排 A17-1 章节数据 → Word 文档"""

    async def check_completeness(
        self, db: AsyncSession, project_id: UUID, wp_id: UUID
    ) -> dict:
        """检查所有必填章节是否已填写，返回完整性报告。

        检查规则（requirements §4 text classification）：
        - 空必填章节 → incomplete
        - 内容含蓝色提示标记【注：...】 → 不应出现在导出内容中（warning）
        - 内容含红色占位符 XX/201X → 用户未替换（incomplete）

        Returns:
            {
                complete: bool,
                missing_chapters: list[str],
                red_placeholder_chapters: list[str],
                blue_guidance_chapters: list[str],
                wp_code: "A17-1",
            }
        """
        chapters = get_chapter_definitions()
        required_chapters = [ch for ch in chapters if ch.get("required")]

        # 加载已填写的章节响应
        responses = await self._load_chapter_responses(db, wp_id)

        missing_chapters: list[str] = []
        red_placeholder_chapters: list[str] = []
        blue_guidance_chapters: list[str] = []

        for ch in required_chapters:
            ch_id = ch["id"]
            content = responses.get(ch_id, "")

            # 空内容 → 缺失
            if not content or not content.strip():
                missing_chapters.append(f"{ch['seq']}. {ch['title']}")
                continue

            # 红色占位符检查
            for pattern in _RED_PLACEHOLDER_PATTERNS:
                if pattern.search(content):
                    red_placeholder_chapters.append(f"{ch['seq']}. {ch['title']}")
                    break

            # 蓝色提示检查
            if _BLUE_GUIDANCE_PATTERN.search(content):
                blue_guidance_chapters.append(f"{ch['seq']}. {ch['title']}")

        complete = (
            len(missing_chapters) == 0
            and len(red_placeholder_chapters) == 0
        )

        return {
            "complete": complete,
            "missing_chapters": missing_chapters,
            "red_placeholder_chapters": red_placeholder_chapters,
            "blue_guidance_chapters": blue_guidance_chapters,
            "wp_code": "A17-1",
        }

    async def export_word(
        self, db: AsyncSession, project_id: UUID, wp_id: UUID
    ) -> bytes:
        """导出 A17-1 为 Word 文档。

        步骤:
        1. 加载章节响应数据
        2. 加载项目上下文（client_name, audit_year）
        3. 定位模板文件
        4. 调用 docx_template_filler 处理颜色语义 + 占位符
        5. 将章节内容写入文档对应位置（HTML→docx 转换）
        6. 自动触发一致性校验（warn 不阻断）
        7. 返回 docx 字节流
        """
        try:
            from docx import Document
        except ImportError:
            raise RuntimeError("python-docx 未安装，无法导出 Word")

        # 1. 加载章节响应
        responses = await self._load_chapter_responses(db, wp_id)

        # 2. 加载项目上下文
        context = await self._load_project_context(db, project_id)

        # 3. 定位模板
        if not _TEMPLATE_PATH.is_file():
            logger.warning("A17-1 模板文件不存在: %s，使用空白文档", _TEMPLATE_PATH)
            doc = Document()
        else:
            doc = Document(str(_TEMPLATE_PATH))

        # 4. 调用 filler 处理颜色语义（蓝删 / 红替换转黑 / 注释表删）
        doc, fill_result = fill_and_export(doc, context)

        # 5. 将章节内容追加到文档末尾（HTML→docx 增强转换）
        self._inject_chapter_content(doc, responses)

        # 6. 自动触发一致性校验（仅记录日志，不阻断导出）
        try:
            from app.services.a17_consistency_checker import check_consistency

            # 查询 project.business_category
            proj_result = await db.execute(
                text("SELECT business_category FROM project WHERE id = :pid"),
                {"pid": str(project_id)},
            )
            proj_row = proj_result.fetchone()
            business_category = proj_row.business_category if proj_row else None

            check_results = check_consistency(responses, business_category)
            error_results = [r for r in check_results if r.severity == "error"]
            if error_results:
                logger.warning(
                    "A17-1 导出时一致性校验发现 %d 个 error 级别问题: %s",
                    len(error_results),
                    [r.rule_id for r in error_results],
                )
        except Exception as e:
            logger.debug("导出时一致性校验失败（不阻断）: %s", e)

        # 7. 导出为 bytes
        return export_to_bytes(doc)

    # ─── 私有方法 ──────────────────────────────────────────────────────────

    async def _load_chapter_responses(
        self, db: AsyncSession, wp_id: UUID
    ) -> dict[str, str]:
        """从 checklist_responses 加载 A17-1 章节填写内容。

        item_id 格式: A17-1-ch01 ~ A17-1-ch16
        内容存储在 remark 字段中（正文 textarea 内容）。
        """
        result = await db.execute(
            text("""
                SELECT item_id, remark
                FROM checklist_responses
                WHERE wp_id = :wp_id
                  AND item_id LIKE 'A17-1-ch%'
                ORDER BY item_id
            """),
            {"wp_id": str(wp_id)},
        )
        rows = result.fetchall()
        return {row.item_id: (row.remark or "") for row in rows}

    async def _load_project_context(
        self, db: AsyncSession, project_id: UUID
    ) -> dict:
        """加载项目数据用于占位符替换。"""
        result = await db.execute(
            text("""
                SELECT client_name, audit_period_end
                FROM projects
                WHERE id = :project_id
            """),
            {"project_id": str(project_id)},
        )
        row = result.fetchone()
        if row is None:
            return {}

        audit_year = ""
        if row.audit_period_end:
            audit_year = str(row.audit_period_end.year)

        return {
            "client_name": row.client_name or "",
            "audit_year": audit_year,
        }

    def _inject_chapter_content(
        self, doc, responses: dict[str, str]
    ) -> None:
        """将章节填写内容注入到文档中。

        增强版：解析 HTML 内容，将 h3/h4 → Heading 样式，
        ul/ol → 列表段落，strong → bold run，em → italic run，
        table → Table 对象。不支持的标签静默跳过。
        """
        chapters = get_chapter_definitions()

        for ch in chapters:
            ch_id = ch["id"]
            content = responses.get(ch_id, "")
            if not content or not content.strip():
                continue

            # 添加章节标题
            heading = f"{ch['seq']}. {ch['title']}"
            doc.add_paragraph(heading, style="Heading 2")

            # 解析 HTML 内容并转换为 Word 元素
            _html_to_docx(doc, content)


# ─── 分发注册接口（供 wp_export_word_service 调用）──────────────────────────


_exporter = A17WordExporter()


async def a17_export_word(
    db: AsyncSession, project_id: UUID, wp_id: UUID
) -> bytes:
    """分发入口：导出 A17-1 Word。"""
    return await _exporter.export_word(db, project_id, wp_id)


async def a17_check_incomplete(
    db: AsyncSession, project_id: UUID, wp_id: UUID
) -> dict:
    """分发入口：A17-1 完整性检查。

    返回 CheckIncompleteResponse 兼容 schema:
    {complete, missing_fields, wp_code, reason}
    """
    report = await _exporter.check_completeness(db, project_id, wp_id)

    # 转换为统一 schema
    missing_fields: list[str] = []
    reasons: list[str] = []

    if report["missing_chapters"]:
        missing_fields.extend(report["missing_chapters"])
        reasons.append(f"缺失 {len(report['missing_chapters'])} 个必填章节")

    if report["red_placeholder_chapters"]:
        missing_fields.extend(
            [f"[未替换] {ch}" for ch in report["red_placeholder_chapters"]]
        )
        reasons.append(f"{len(report['red_placeholder_chapters'])} 个章节含未替换占位符")

    if report["blue_guidance_chapters"]:
        reasons.append(
            f"{len(report['blue_guidance_chapters'])} 个章节含编制提示（导出时自动删除）"
        )

    return {
        "complete": report["complete"],
        "missing_fields": missing_fields,
        "wp_code": "A17-1",
        "reason": "；".join(reasons) if reasons else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# A17-2-1 KAM (关键审计事项) Word 导出
# ═══════════════════════════════════════════════════════════════════════════════

import json
from dataclasses import dataclass

_KAM_TEMPLATE_PATH = _BACKEND_ROOT / "wp_templates" / "A" / "A17-2-1 重大事项概要—关键审计事项.docx"


@dataclass
class KamRemarkParsed:
    """KAM remark JSON 解析结果。"""

    situation: str = ""
    reason: str = ""
    response: str = ""
    refs: str = ""
    wording_review: str = "pending"  # pending|done|na
    governance_confirmed: bool = False


def _parse_kam_remark(remark_json: str | None) -> KamRemarkParsed:
    """安全解析 KAM remark JSON 字段。"""
    if not remark_json:
        return KamRemarkParsed()
    try:
        data = json.loads(remark_json)
        if not isinstance(data, dict):
            return KamRemarkParsed()
        return KamRemarkParsed(
            situation=str(data.get("situation") or ""),
            reason=str(data.get("reason") or ""),
            response=str(data.get("response") or ""),
            refs=str(data.get("refs") or ""),
            wording_review=str(data.get("wording_review") or "pending"),
            governance_confirmed=bool(data.get("governance_confirmed")),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return KamRemarkParsed()


_WORDING_LABELS = {"pending": "待审核", "done": "已完成", "na": "不适用"}


class A17KamExporter:
    """编排 A17-2-1 KAM 数据 → Word 文档。"""

    async def check_completeness(
        self, db: AsyncSession, project_id: UUID, wp_id: UUID
    ) -> dict:
        """KAM 完整性检查：至少 1 条 KAM、每条必填字段齐全。"""
        entries = await self._load_kam_entries(db, wp_id)

        missing_fields: list[str] = []

        if not entries:
            missing_fields.append("至少需要 1 条 KAM 记录")

        for item_id, title, remark_json, _wp_ref in entries:
            seq = item_id.replace("A17-2-1-KAM-", "")
            label = title or f"KAM-{seq}"
            remark = _parse_kam_remark(remark_json)
            if not title:
                missing_fields.append(f"{label}: 缺少标题")
            if not remark.situation:
                missing_fields.append(f"{label}: 缺少情况描述")
            if not remark.reason:
                missing_fields.append(f"{label}: 缺少确定为KAM的原因")
            if not remark.response:
                missing_fields.append(f"{label}: 缺少审计应对")

        return {
            "complete": len(missing_fields) == 0,
            "missing_fields": missing_fields,
            "wp_code": "A17-2-1",
            "reason": f"{len(missing_fields)} 项未完成" if missing_fields else None,
        }

    async def export_word(
        self, db: AsyncSession, project_id: UUID, wp_id: UUID
    ) -> bytes:
        """导出 A17-2-1 KAM 为 Word 文档。"""
        try:
            from docx import Document
            from docx.shared import Pt
        except ImportError:
            raise RuntimeError("python-docx 未安装，无法导出 Word")

        entries = await self._load_kam_entries(db, wp_id)
        context = await self._load_project_context(db, project_id)

        # 使用模板或空白文档
        if _KAM_TEMPLATE_PATH.is_file():
            doc = Document(str(_KAM_TEMPLATE_PATH))
            doc, _ = fill_and_export(doc, context)
        else:
            logger.warning("A17-2-1 模板不存在: %s，使用空白文档", _KAM_TEMPLATE_PATH)
            doc = Document()
            doc.add_heading("关键审计事项 (KAM)", level=1)

        # 为每条 KAM 生成内容表格
        for idx, (item_id, title, remark_json, wp_ref) in enumerate(entries, 1):
            remark = _parse_kam_remark(remark_json)
            self._add_kam_section(doc, idx, title or "未命名", wp_ref or "", remark)

        return export_to_bytes(doc)

    # ─── 私有方法 ──────────────────────────────────────────────────────

    async def _load_kam_entries(
        self, db: AsyncSession, wp_id: UUID
    ) -> list[tuple[str, str, str, str]]:
        """加载 KAM 条目列表。返回 (item_id, conclusion, remark, wp_ref)。"""
        result = await db.execute(
            text("""
                SELECT item_id, conclusion, remark, wp_ref
                FROM checklist_responses
                WHERE wp_id = :wp_id
                  AND item_id LIKE 'A17-2-1-KAM%'
                ORDER BY item_id
            """),
            {"wp_id": str(wp_id)},
        )
        return [
            (row.item_id, row.conclusion or "", row.remark or "", row.wp_ref or "")
            for row in result.fetchall()
        ]

    async def _load_project_context(
        self, db: AsyncSession, project_id: UUID
    ) -> dict:
        """复用 A17-1 的项目上下文加载逻辑。"""
        return await _exporter._load_project_context(db, project_id)

    def _add_kam_section(
        self,
        doc,
        seq: int,
        title: str,
        wp_ref: str,
        remark: KamRemarkParsed,
    ) -> None:
        """为文档添加一条 KAM 的表格区块。"""
        # 标题段落
        doc.add_heading(f"KAM {seq}: {title}", level=2)

        # 表格：每行一个字段
        rows_data = [
            ("引用底稿", wp_ref),
            ("情况描述", remark.situation),
            ("确定为KAM的原因", remark.reason),
            ("审计应对", remark.response),
            ("底稿引用说明", remark.refs),
            ("措辞审核", _WORDING_LABELS.get(remark.wording_review, "待审核")),
            ("治理层确认", "是" if remark.governance_confirmed else "否"),
        ]

        table = doc.add_table(rows=len(rows_data), cols=2)
        table.style = "Table Grid"
        for i, (label, value) in enumerate(rows_data):
            table.rows[i].cells[0].text = label
            table.rows[i].cells[1].text = value or ""

        # 段落间距
        doc.add_paragraph("")


# ─── KAM 分发入口 ────────────────────────────────────────────────────────────

_kam_exporter = A17KamExporter()


async def a17_kam_export_word(
    db: AsyncSession, project_id: UUID, wp_id: UUID
) -> bytes:
    """分发入口：导出 A17-2-1 KAM Word。"""
    return await _kam_exporter.export_word(db, project_id, wp_id)


async def a17_kam_check_incomplete(
    db: AsyncSession, project_id: UUID, wp_id: UUID
) -> dict:
    """分发入口：A17-2-1 KAM 完整性检查。"""
    return await _kam_exporter.check_completeness(db, project_id, wp_id)
