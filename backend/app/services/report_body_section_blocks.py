"""报告正文（审计报告）段落定位 —— 章节标题 → section_id → 块区间（纯函数）。

Spec: deliverable-lineage-wiring-and-writeback-closure — Wave 3 Task 17 / 需求 9.1

为什么需要独立的定位器（不能复用附注那套）：

- 附注 docx 由平台自己按 ``##SECTION:code##`` 标记生成，章节编码是数据（`八、1`）；
- 报告正文 docx 来自**致同源模板**（`backend/data/audit_report_templates/report_body/*.docx`），
  章节以中文序号标题分节（`一、审计意见` / `二、形成审计意见的基础` …），没有任何机器标记。

**两条源模板实证事实（决定了判据，勿按直觉改）**：

1. **序号会漂移** —— 同一个「管理层和治理层对财务报表的责任」在
   `模板D-无保留意见-简版` 里是 **三、**、在 `模板A-无保留意见-简版` 里是 **五、**
   （因为 A 版多了「关键审计事项」「其他信息」两节）。故**只能按序号后的名称匹配**，
   把序号当 section 标识必错。
2. **docx 标题不带「段」字** —— `SECTION_ID_MAP` 的键是 `审计意见段`，而模板里写的是
   `一、审计意见`。既有 ``ReportBodyService.parse_docx_to_section_ids`` 用
   ``section_name in doc_text`` 匹配，只在 JSON 模式（body 里存着带「段」的 section_name）
   成立；对 Word 模板模式的交付件**恒不命中**。故这里从 ``SECTION_ID_MAP`` 派生一份
   去「段」后的名称表 —— 派生而非另抄，保持单一真源。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.services.report_body_service import SECTION_ID_MAP
from app.services.section_anchor_utils import (
    FOREIGN_ANCHOR_PREFIXES,
    SectionBlock,
)

logger = logging.getLogger(__name__)

#: 报告正文锚点前缀（与附注的 ``sec_`` 区分开，避免两类交付件的 key 空间混淆）。
REPORT_BODY_ANCHOR_PREFIX = "sec_rb_"

# 交叉锁死：本命名空间必须已在 section_anchor_utils 登记为「外域前缀」，
# 否则附注回填的 scan_anchor_blocks 会把报告正文锚点当附注章节码反解
# （最坏情况：把报告正文的文字写进附注）。import 期即失败，不给漂移留窗口。
assert REPORT_BODY_ANCHOR_PREFIX in FOREIGN_ANCHOR_PREFIXES, (
    f"{REPORT_BODY_ANCHOR_PREFIX} 未登记进 section_anchor_utils.FOREIGN_ANCHOR_PREFIXES"
)

#: 由 ``SECTION_ID_MAP`` 派生：去掉尾字「段」后的标题名 → section_id。
#: 派生而非另抄 —— 上游增删章节时这里自动跟随（守卫断言两者条数一致）。
SECTION_NAME_TO_ID: dict[str, str] = {
    (name[:-1] if name.endswith("段") else name): sid
    for name, sid in SECTION_ID_MAP.items()
}

#: 中文序号标题：`一、审计意见` / `十一、其他事项`（全角/半角顿号与空格都容忍）。
_HEADING_RE = re.compile(r"^[一二三四五六七八九十百]+\s*[、.．]\s*(?P<name>.+?)\s*$")

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_P = f"{{{_W}}}p"
_TBL = f"{{{_W}}}tbl"
_T = f"{{{_W}}}t"


def report_body_anchor_name(section_id: str) -> str:
    """由 section_id 派生锚点书签名（确定性、仅 ASCII，Word 书签名安全）。"""
    return f"{REPORT_BODY_ANCHOR_PREFIX}{section_id}"


def section_id_from_report_body_anchor(anchor: str) -> str | None:
    """反解锚点名 → section_id；非本域锚点返回 ``None``。"""
    if not isinstance(anchor, str) or not anchor.startswith(REPORT_BODY_ANCHOR_PREFIX):
        return None
    sid = anchor[len(REPORT_BODY_ANCHOR_PREFIX):]
    return sid or None


def match_section_heading(text: str) -> str | None:
    """判断一个段落文字是否为章节标题；是则返回 section_id。

    只认「中文序号 + 顿号 + 已登记名称」的完整匹配 —— 不做模糊包含，
    否则正文里提到「关键审计事项」的句子会被误判成标题（模板 A 的
    `注册会计师责任` 段末尾就有一句提到「构成关键审计事项」）。
    """
    if not text:
        return None
    m = _HEADING_RE.match(text.strip())
    if not m:
        return None
    return SECTION_NAME_TO_ID.get(m.group("name").strip())


def _para_text(el: Any) -> str:
    return "".join(t.text or "" for t in el.iter(_T)).strip()


@dataclass
class ReportBodySection:
    """报告正文一个章节的块区间。

    Attributes:
        section_id: `opinion` / `basis` / `kam` / …（``SECTION_ID_MAP`` 的值）
        heading_el: 标题段落元素（`一、审计意见`）
        content_els: 该章节的正文元素（**不含标题**），含段落与表格
    """

    section_id: str
    heading_el: Any
    content_els: list[Any]

    @property
    def elements(self) -> list[Any]:
        """标题 + 正文（供锚点区间使用）。"""
        return [self.heading_el, *self.content_els]

    def to_section_block(self) -> SectionBlock:
        """转成 ``write_section_anchors`` 需要的形态（锚点包住标题+正文）。"""
        els = self.elements
        return SectionBlock(
            section_code=self.section_id,
            open_el=els[0],
            close_el=els[-1],
        )

    def text(self) -> str:
        """章节正文文字（**排除标题**）—— 回填与快照哈希的口径。

        排除标题的理由：标题是模板固定文字（且序号随可选段落漂移），
        把它纳入会让「换了个模板变体」被误判成人工编辑。
        """
        parts = [_para_text(el) for el in self.content_els if el.tag == _P]
        return "\n".join(p for p in parts if p)


def scan_report_body_sections(doc: Any) -> list[ReportBodySection]:
    """扫描报告正文 docx，按章节标题切出块区间。

    定位规则：
    - 以匹配 ``match_section_heading`` 的段落为章节起点；
    - 章节内容 = 到**下一个章节标题之前**的全部 body 级 ``w:p`` / ``w:tbl``；
    - 首个标题之前的内容（封面 / 目录 / 收件人）不属于任何章节，丢弃；
    - 同一 section_id 出现多次时**取首个**并 warning（源模板不应如此）。

    Returns:
        按文档顺序排列的章节列表；无任何标题时返回 ``[]``。
    """
    body = doc.element.body
    sections: list[ReportBodySection] = []
    current: ReportBodySection | None = None
    seen: set[str] = set()

    for el in list(body):
        if el.tag == _P:
            sid = match_section_heading(_para_text(el))
            if sid is not None:
                if sid in seen:
                    logger.warning(
                        "report_body: section_id %s 重复出现，取首个", sid
                    )
                    current = None
                    continue
                seen.add(sid)
                current = ReportBodySection(
                    section_id=sid, heading_el=el, content_els=[]
                )
                sections.append(current)
                continue
        if current is not None and el.tag in (_P, _TBL):
            current.content_els.append(el)

    return sections


def extract_report_body_sections(doc: Any) -> dict[str, str]:
    """交付 docx → ``{section_id: 正文文字}``（不含标题）。

    供 confirm 阶段落 ``report_body_json.sections`` 与回填阶段做 diff 共用同一口径 ——
    两侧口径必须同源，否则「刚生成就判有人工编辑」。
    """
    return {s.section_id: s.text() for s in scan_report_body_sections(doc)}


def build_report_body_sections_payload(doc: Any) -> list[dict[str, Any]]:
    """交付 docx → ``report_body_json.sections`` 载荷（additive 键）。

    形态对齐 JSON 模式的 ``{section_id, section_name, content, section_order}``，
    使既有 ``ReportBodyService.get_section`` 等读取端两模式共用。
    """
    id_to_name = {sid: name for name, sid in SECTION_ID_MAP.items()}
    out: list[dict[str, Any]] = []
    for order, sec in enumerate(scan_report_body_sections(doc), start=1):
        out.append(
            {
                "section_id": sec.section_id,
                "section_name": id_to_name.get(sec.section_id, sec.section_id),
                "content": sec.text(),
                "section_order": order,
            }
        )
    return out
