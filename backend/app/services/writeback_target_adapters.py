"""回填上游适配器 —— 按 doc_type 决定「读/写哪个上游」与「怎么从 docx 提章节」。

Spec: deliverable-lineage-wiring-and-writeback-closure — Wave 3 Task 18 / 需求 9.2、9.3、9.5

为什么要抽这层：历史实现把 ``DisclosureNote`` 硬编码在回填主流程的**五个地方**
（提取 / 读上游 / 写上游 / 冲突检测读上游 / 裁决写上游），于是

- 报告正文交付件点回填时同样去写 ``disclosure_notes``（章节标识是 ``opinion`` 这类
  英文标识，与附注章节号不是同一命名空间）⇒ UPDATE 恒 0 行；
- 而 Wave 1 之前 rowcount 还没被检查 ⇒ **静默报「回填成功 N 个章节」**。

适配器把「上游是什么」收敛成一个对象，主流程只按 doc_type 选一次。

**附注适配器的行为必须与抽取前逐字节等价** —— 它是既有唯一路径，
`test_deliverable_writeback_rowcount.py` / `test_deliverable_lineage_e2e.py` 是其锚点。
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class WritebackTargetAdapter(Protocol):
    """回填上游读写协议。

    实现方只负责「上游」这一侧；护栏分类 / 冲突检测 / 留痕 / rowcount 语义
    全部留在 ``DeliverableWritebackService``（它们与上游种类无关）。
    """

    #: 供日志与错误文案使用的中文上游名（如「附注」「报告正文」）。
    upstream_label: str

    async def extract_sections(self, docx_bytes: bytes) -> dict[str, str]:
        """交付 docx → ``{section_code: 正文文字}``。"""
        ...

    async def read_upstream(
        self, project_id: UUID, year: int, section_code: str
    ) -> str:
        """读上游当前文字；无记录返回 ``""``。"""
        ...

    async def write_upstream(
        self, project_id: UUID, year: int, section_code: str, new_text: str
    ) -> int:
        """写上游；返回**受影响行数**。

        0 表示上游无对应记录 ⇒ 调用方必须计入 ``failed`` 而非 ``written``（需求 5.1）。
        """
        ...


# ---------------------------------------------------------------------------
# 附注（既有唯一路径，行为逐字节不变）
# ---------------------------------------------------------------------------


class DisclosureNoteAdapter:
    """附注适配器：读写 ``disclosure_notes.text_content``。

    抽取自原 ``DeliverableWritebackService`` 内联实现，**逻辑逐字保留**
    （含 ``is_deleted == false()`` 过滤与 rowcount 语义）。
    """

    upstream_label = "附注"

    def __init__(self, db: AsyncSession):
        self.db = db

    async def extract_sections(self, docx_bytes: bytes) -> dict[str, str]:
        # 附注侧的提取逻辑与块 XML 采集耦合在服务里（护栏需要块 XML），
        # 故由服务直接调用其 `_extract_sections_from_docx`；此处不重复实现。
        raise NotImplementedError(
            "附注提取由 DeliverableWritebackService._extract_sections_from_docx 承担"
        )

    async def read_upstream(
        self, project_id: UUID, year: int, section_code: str
    ) -> str:
        from app.models.report_models import DisclosureNote

        stmt = sa.select(DisclosureNote.text_content).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == section_code,
            DisclosureNote.is_deleted == sa.false(),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() or ""

    async def write_upstream(
        self, project_id: UUID, year: int, section_code: str, new_text: str
    ) -> int:
        from app.models.report_models import DisclosureNote

        stmt = (
            sa.update(DisclosureNote)
            .where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.note_section == section_code,
                DisclosureNote.is_deleted == sa.false(),
            )
            .values(text_content=new_text)
        )
        result = await self.db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)


# ---------------------------------------------------------------------------
# 报告正文（Wave 3 新增）
# ---------------------------------------------------------------------------


#: **不可回填**的报告正文章节（需求 9.4：由数据派生 / 模板固定的段落）。
#:
#: 判据来自源模板逐字核对（`backend/data/audit_report_templates/report_body/*.docx`）：
#:
#: - ``mgmt_responsibility`` / ``cpa_responsibility``：**准则规定的标准表述**，
#:   四份模板（A/B/C/D）逐字相同、只有 ``{{company_short_name}}`` 一个占位符。
#:   审计师改这两段等于偏离准则用语，必须走模板变更而非交付件编辑。
#: - ``signature``：签章段由 ``firm_name`` / ``report_number`` / ``report_date``
#:   等占位符填充，是数据派生结果（改文字不改数据 = 与库里事实不符）。
#:
#: **刻意不含**的章节（它们本就是人工撰写、回填的主要价值所在）：
#: ``opinion``（意见段虽有标准句式但含项目特定表述）/ ``basis`` /
#: ``kam``（关键审计事项全靠人工撰写）/ ``emphasis`` / ``other_info`` /
#: ``other_matter`` / 三个 ``*_basis``（保留、否定、无法表示意见的基础，
#: 逐项目描述具体事项）。
DERIVED_REPORT_BODY_SECTIONS: frozenset[str] = frozenset(
    {
        "mgmt_responsibility",
        "cpa_responsibility",
        "signature",
    }
)


class ReportBodyAdapter:
    """报告正文适配器：读写 ``AuditReport.report_body_json["sections"]``。

    需求 9.2 明确：报告正文回填 **SHALL NOT** 写 ``DisclosureNote``。

    🔴 为什么写 JSONB 的一个数组元素而不是独立表：Word 模板模式下段落文字原本
    **只在 docx 里**（真实库实证 ``report_body_json`` 只有 6 个元数据键），
    Wave 3 Task 17 已把 ``sections`` 作为 additive 键落进去 —— 它就是段落文字的
    唯一 DB 落点，也是需求 9.6「重新生成后保留人工文字」的物理前提。

    🔴 rowcount 语义与附注侧对齐：``sections`` 里找不到该 ``section_id`` 时返回 **0**
    （不新增元素）—— 交付件里有、DB 里没有，说明该版本生成于 Task 17 接线之前，
    应如实落 ``failed`` 让用户重新生成，而不是凭空造一个章节。
    """

    upstream_label = "报告正文"

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def is_derived_section(section_code: str) -> bool:
        """该章节是否为「派生/模板固定」段落 ⇒ 不可回填（需求 9.4）。"""
        return section_code in DERIVED_REPORT_BODY_SECTIONS

    async def extract_sections(self, docx_bytes: bytes) -> dict[str, str]:
        from io import BytesIO

        from docx import Document

        from app.services.report_body_section_blocks import (
            extract_report_body_sections,
        )

        return extract_report_body_sections(Document(BytesIO(docx_bytes)))

    async def _get_report(self, project_id: UUID, year: int):
        from app.models.report_models import AuditReport

        stmt = sa.select(AuditReport).where(
            AuditReport.project_id == project_id,
            AuditReport.year == year,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def read_upstream(
        self, project_id: UUID, year: int, section_code: str
    ) -> str:
        report = await self._get_report(project_id, year)
        body = report.report_body_json if report is not None else None
        if not isinstance(body, dict):
            return ""
        for sec in body.get("sections") or []:
            if isinstance(sec, dict) and sec.get("section_id") == section_code:
                return sec.get("content") or ""
        return ""

    async def write_upstream(
        self, project_id: UUID, year: int, section_code: str, new_text: str
    ) -> int:
        if section_code in DERIVED_REPORT_BODY_SECTIONS:
            # 需求 9.4：由数据派生 / 模板固定的段落不可回填。
            # 拒绝留痕由主流程按 rowcount==0 落 failed 桶承担。
            logger.warning(
                "writeback(报告正文): 章节 %s 属派生/模板固定段落，拒绝回填（需求 9.4）",
                section_code,
            )
            return 0

        report = await self._get_report(project_id, year)
        if report is None:
            logger.warning(
                "writeback(报告正文): 项目 %s/%s 无 audit_report 记录", project_id, year
            )
            return 0

        body = report.report_body_json
        if not isinstance(body, dict):
            logger.warning(
                "writeback(报告正文): report_body_json 不是对象，拒绝写入 %s",
                section_code,
            )
            return 0

        sections = body.get("sections")
        if not isinstance(sections, list):
            logger.warning(
                "writeback(报告正文): report_body_json 无 sections 数组"
                "（该版本生成于段落锚点接线之前），章节 %s 不写入，请重新生成报告正文",
                section_code,
            )
            return 0

        idx = next(
            (
                i
                for i, sec in enumerate(sections)
                if isinstance(sec, dict) and sec.get("section_id") == section_code
            ),
            None,
        )
        if idx is None:
            logger.warning(
                "writeback(报告正文): sections 中无章节 %s，不新增元素（如实记失败）",
                section_code,
            )
            return 0

        if (sections[idx].get("content") or "") == new_text:
            # 幂等：内容一致仍算写入成功（与 SQL UPDATE 同值时 rowcount=1 的语义对齐）
            return 1

        # 🔴🔴 必须**深拷贝构造新结构**，不能就地改 `sections[idx]["content"]`。
        #
        # 两层坑叠加（2026-08-04 实测：内存对象看着已更新、DB 列仍是旧值）：
        # ① 未声明 MutableDict 的 JSON/JSONB 列，就地改嵌套对象不会被标脏；
        # ② 即便随后整体重赋值 `report.report_body_json = {**body, ...}`，由于
        #    `body` 就是 ORM 持有的那个 dict、其嵌套元素已被就地改过，
        #    **新值与 ORM 记录的旧值 `==` 相等** ⇒ 工作单元判「无净变更」⇒ 不发 UPDATE。
        #
        # 深拷贝让「旧值」保持原样，新旧不等 ⇒ 必然发 UPDATE。
        new_sections = [
            {**sec, "content": new_text}
            if i == idx and isinstance(sec, dict)
            else (dict(sec) if isinstance(sec, dict) else sec)
            for i, sec in enumerate(sections)
        ]
        report.report_body_json = {**body, "sections": new_sections}
        await self.db.flush()
        return 1


# ---------------------------------------------------------------------------
# 选择器
# ---------------------------------------------------------------------------

#: doc_type → 适配器类。与 ``deliverable_capabilities.WRITEBACK_SUPPORTED_DOC_TYPES``
#: 必须一致（守卫交叉锁死）：能力矩阵说支持回填的类型，这里必须有适配器，反之亦然。
ADAPTER_BY_DOC_TYPE: dict[str, type] = {
    "disclosure_notes": DisclosureNoteAdapter,
    "audit_report": ReportBodyAdapter,
}


def get_writeback_adapter(db: AsyncSession, doc_type: str | None):
    """按 doc_type 取回填适配器；未支持的类型返回 ``None``。

    返回 None 时调用方应拒绝回填（端点层已有 400 门控，这里是第二道闸）。
    """
    cls = ADAPTER_BY_DOC_TYPE.get(doc_type or "")
    return cls(db) if cls is not None else None
