"""LLM 结构化输出 Pydantic 模型集中定义。

三个场景共用：
- DocRecognitionResult  → wp_document_recognizer（底稿附件识别，活链路核心交付）
- EvidenceOcrResult     → wp_evidence_ocr_service（证据 OCR 凭证字段提取）
- TsjReviewResult       → tsj_structured_output_service（审计复核结构化发现）

所有字段设为 `str | None = None` 以保证提取鲁棒性——LLM 可能对部分字段
无法提取，返回 None 优于校验失败重试。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 底稿文档识别（wp_document_recognizer._llm_recognize）
# ---------------------------------------------------------------------------


class DocRecognitionResult(BaseModel):
    """底稿附件文档识别结果。

    doc_type: 识别出的文档类型（voucher/invoice/warehouse/bank_receipt）
    fields:   动态字段字典，键集与 DOC_TYPE_FIELDS[doc_type] 对应，值为提取文本或 None
    """

    doc_type: str | None = None
    fields: dict[str, str | None] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 证据 OCR 凭证字段提取（wp_evidence_ocr_service._ocr_and_recognize）
# ---------------------------------------------------------------------------


class EvidenceOcrResult(BaseModel):
    """记账凭证 OCR 结构化提取结果。

    对应 VOUCHER_FIELDS 8 个标准字段，LLM 从凭证图片/文本中提取。
    """

    voucher_no: str | None = None
    """凭证号"""
    voucher_date: str | None = None
    """凭证日期"""
    debit_amount: str | None = None
    """借方金额"""
    credit_amount: str | None = None
    """贷方金额"""
    summary: str | None = None
    """摘要"""
    account_name: str | None = None
    """科目名称"""
    preparer: str | None = None
    """制单人"""
    reviewer: str | None = None
    """复核人"""


# ---------------------------------------------------------------------------
# TSJ 审计复核结构化发现（tsj_structured_output_service）
# ---------------------------------------------------------------------------


class TsjFinding(BaseModel):
    """单条审计复核发现。

    与 STRUCTURED_OUTPUT_INSTRUCTION 中定义的 JSON 结构对齐，
    每条代表一个审计问题/风险点。
    """

    issue_type: str | None = None
    """问题类型（如：计算错误/披露不充分/分类不当）"""
    severity: str | None = None
    """严重程度（如：high/medium/low）"""
    sheet: str | None = None
    """涉及的工作表名称"""
    cell_range: str | None = None
    """涉及的单元格范围（如 A1:C5）"""
    description: str | None = None
    """问题描述"""
    evidence_ref: str | None = None
    """证据引用（底稿索引号或文档引用）"""
    remediation: str | None = None
    """建议整改措施"""


class TsjReviewResult(BaseModel):
    """TSJ 审计复核结构化输出结果。

    包含一组审计发现，由 LLM 从复核对话中提取。
    即使 tsj 场景暂为孤儿（零调用方），模型定义供 spec-5 DSPy 复用
    及未来 tsj review 链路真正接线时使用。
    """

    findings: list[TsjFinding] = Field(default_factory=list)
