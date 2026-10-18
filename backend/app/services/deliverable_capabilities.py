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
#:
#: 🔴 **附注（disclosure_notes）已下线**（spec deliverable-writeback-and-online-edit-integrity 方向裁定，2026-10-17 用户确认）：
#: 附注唯一权威源是底稿披露表的单项推送（底稿 → 附注），交付中心是附注的只读下游出口。让审计师在交付 Word 改字再回填附注
#: 是逆流（下游改上游、可能与底稿事实不符）。附注要改内容回底稿改；交付导出前有一致性确认闸门
#: （见 deliverable_note_consistency）。
#:
#: 只保留 ``audit_report``：报告正文段落文字就在交付件里、不来自底稿→附注推送链，回填不构成逆流
#: （写 AuditReport.report_body_json.sections，派生 / 模板固定段落仍拒绝，见 writeback_target_adapters）。
WRITEBACK_SUPPORTED_DOC_TYPES: Final[frozenset[str]] = frozenset(
    {
        "audit_report",
    }
)

#: 支持「章节级增量刷新」的 doc_type（需要 Section_Anchor + 章节状态）。
SECTION_REFRESH_SUPPORTED_DOC_TYPES: Final[frozenset[str]] = frozenset(
    {
        "disclosure_notes",
    }
)

#: 支持「章节溯源」的 doc_type（US-8）：有 Section_Anchor + 章节状态，可按章节回溯上游。
#:
#: 附注 / 报告正文都有章节结构（附注章节号 / 报告正文段落），交付时落 deliverable_section_state，
#: 故可溯源。财务报表（xlsx）**不支持**：报表按报表行取数、无章节锚点，其章节状态任务恒 0 行，
#: 面板只会显示空下拉 + 「请重新生成」误导（历史缺陷）。改为显式说明「报表按行取数、去报表页穿透」。
LINEAGE_SUPPORTED_DOC_TYPES: Final[frozenset[str]] = frozenset(
    {
        "disclosure_notes",
        "audit_report",
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


def supports_lineage(doc_type: str | None) -> bool:
    """该交付件类型是否支持章节溯源（US-8）。"""
    return (doc_type or "") in LINEAGE_SUPPORTED_DOC_TYPES


def lineage_unsupported_message(doc_type: str | None) -> str:
    """不支持溯源时的可读说明（中文，指明正确查数路径）。"""
    dt = doc_type or ""
    if dt.startswith("financial_report"):
        return "财务报表按报表行取数，没有章节溯源；数字来源请在「财务报表」页穿透查看。"
    return "该交付件类型不支持章节溯源。"


def writeback_unsupported_message(doc_type: str | None) -> str:
    """不支持回填时的可读错误文案（中文，指明替代路径）。"""
    dt = doc_type or "未知"
    if dt in WRITEBACK_FORBIDDEN_DOC_TYPES:
        return (
            f"该交付件类型（{dt}）不支持回填：财务报表数字只能由试算表与调整分录派生，"
            "请通过调整分录（AJE/RJE）修正后重新生成报表"
        )
    if dt == "disclosure_notes":
        return (
            "附注不支持从交付件回填：附注内容来源于底稿披露表的推送（底稿 → 附注）。"
            "请回对应底稿修改并点「同步到附注」，再从交付中心重新导出附注。"
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
