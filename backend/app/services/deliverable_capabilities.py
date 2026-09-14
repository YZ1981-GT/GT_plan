"""交付件能力矩阵 —— 哪些 doc_type 支持回填 / 章节增量刷新（单一真源）。

Spec: deliverable-lineage-wiring-and-writeback-closure — Task 8 / 需求 6

为什么要有这个模块：回填与刷新**只对特定 doc_type 有意义**，而历史实现两侧都没门控 ——
`WritebackResultPanel` 挂在 `OnlyOfficeEditor` 上不区分类型，于是财务报表 xlsx 上也出现
「回填到附注模块」按钮；后端亦无校验，全靠前端自觉。

单一真源的必要性：能力矩阵若前后端各写一份，改一处另一处不红（memory 记的双真源漂移
范式）。故这里是**唯一**声明处，前端经 ``DeliverableDTOSchema`` 下发的布尔字段消费。

设计约束：
- **禁止**把 ``financial_report*`` 加入任一集合 —— 报表数字唯一合法来源是试算表 +
  调整分录，允许 xlsx 回写等于绕过调整分录（design §决策；需求 10.1）。
  xlsx 的手工改动走「差异告警」而非回写（Wave 4）。
- ``audit_report``（报告正文）在 Wave 3 段落级回填落地后加入 ``WRITEBACK``；
  当前不支持 —— 其段落标识来自模板 placeholder/OPT，与附注章节号不是同一命名空间，
  写 ``DisclosureNote`` 必然影响 0 行（历史缺陷：仍被报成「回填成功」）。
"""

from __future__ import annotations

from typing import Final

#: 支持「回填到上游」的 doc_type。
#: Wave 3 增加 ``audit_report``（写 AuditReport.report_body_json）。
WRITEBACK_SUPPORTED_DOC_TYPES: Final[frozenset[str]] = frozenset(
    {
        "disclosure_notes",
        # Wave 3 Task 18：报告正文段落级回填（写 AuditReport.report_body_json.sections）。
        # 前提是 Task 17 已给交付 docx 写入 sec_rb_* 段落锚点、且 confirm 时把
        # sections 落进 report_body_json —— 二者缺一则回填恒返回全空/failed。
        "audit_report",
    }
)

#: 支持「章节级增量刷新」的 doc_type（需要 Section_Anchor + 章节状态）。
SECTION_REFRESH_SUPPORTED_DOC_TYPES: Final[frozenset[str]] = frozenset(
    {
        "disclosure_notes",
    }
)

#: 明确**不得**支持单元格/数字回写的 doc_type（守卫用，防后来者"顺手"加进来）。
WRITEBACK_FORBIDDEN_DOC_TYPES: Final[frozenset[str]] = frozenset(
    {
        "financial_report",
        "financial_report_unadjusted",
    }
)


def supports_writeback(doc_type: str | None) -> bool:
    """该交付件类型是否支持回填到上游。"""
    return (doc_type or "") in WRITEBACK_SUPPORTED_DOC_TYPES


def supports_section_refresh(doc_type: str | None) -> bool:
    """该交付件类型是否支持章节级增量刷新。"""
    return (doc_type or "") in SECTION_REFRESH_SUPPORTED_DOC_TYPES


def writeback_unsupported_message(doc_type: str | None) -> str:
    """不支持回填时的可读错误文案（中文，指明替代路径）。"""
    dt = doc_type or "未知"
    if dt in WRITEBACK_FORBIDDEN_DOC_TYPES:
        return (
            f"该交付件类型（{dt}）不支持回填：财务报表数字只能由试算表与调整分录派生，"
            "请通过调整分录（AJE/RJE）修正后重新生成报表"
        )
    return f"该交付件类型（{dt}）不支持回填到上游"


def section_refresh_unsupported_message(doc_type: str | None) -> str:
    """不支持章节刷新时的可读错误文案。"""
    dt = doc_type or "未知"
    if dt in WRITEBACK_FORBIDDEN_DOC_TYPES:
        return (
            f"该交付件类型（{dt}）不支持章节级刷新：报表请用「生成财务报表」整份重新生成"
        )
    return f"该交付件类型（{dt}）不支持章节级增量刷新"
