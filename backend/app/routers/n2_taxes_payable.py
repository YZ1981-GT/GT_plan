"""N2 应交税费 — 导入导出三级端点 + AI辅助 + TB回写 + OCR识别

6个端点：
- GET  /api/n2-taxes-payable/{wp_id}/export-template   多税种分sheet空白模板xlsx
- GET  /api/n2-taxes-payable/{wp_id}/export-data        当前数据xlsx（多税种分sheet）
- POST /api/n2-taxes-payable/{wp_id}/import-data        解析xlsx写入（multipart）
- POST /api/n2-taxes-payable/{wp_id}/ai-assist          AI辅助（section-based）
- PUT  /api/n2-taxes-payable/{wp_id}/tb-writeback       TB回写（科目2221，贷方/负债类）
- POST /api/n2-taxes-payable/{wp_id}/contract-ocr       OCR识别（行级附件）

科目编码: 2221应交税费（**贷方/负债类**）
公式方向: 期末=期初+贷方-借方（负债类！2221贷方科目）
多税种: 增值税/城建税/教育费附加/地方教育附加/房产税/土增税/所得税/其他
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 3.4
"""

from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import aiofiles
import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/n2-taxes-payable",
    tags=["N2 应交税费"],
)

# 支持的多税种sheet编码
SUPPORTED_SHEETS = {"N2-2", "N2-6", "N2-8", "N2-9", "N2-10"}

# AI超时（秒）
_AI_TIMEOUT = 30.0


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class TBWritebackRequest(BaseModel):
    """TB回写请求（科目2221应交税费）"""
    audited_amount: float = Field(description="审定金额（期末余额）")
    account_code: str = Field("2221", description="科目编码，默认2221")


class TBWritebackResponse(BaseModel):
    """TB回写响应"""
    message: str = Field("回写成功")
    account_code: str = Field(description="科目编码")
    audited_amount: str = Field(description="回写后审定金额")


class N2AiAssistRequest(BaseModel):
    """AI辅助生成请求"""
    section: str = Field(description="目标section标识")
    existingContent: str = Field("", description="现有内容")
    relatedContext: dict[str, Any] = Field(default_factory=dict, description="关联上下文")


class N2AiAssistResponse(BaseModel):
    """AI辅助生成响应"""
    content: str = Field(description="生成内容")
    sources: list[str] = Field(default_factory=list)


class N2VoucherOcrResponse(BaseModel):
    """OCR识别响应"""
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    summary: str
    confidence: float


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def n2_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（多税种分sheet）

    Query params:
        sheet: 可选，指定导出单个sheet（N2-2/N2-6/N2-8/N2-9/N2-10）

    Requirements: 3.4
    """
    from app.services.n2_taxes_payable_service import export_template

    if sheet and sheet not in SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(SUPPORTED_SHEETS)}")

    buffer = await export_template(wp_id, db, sheet=sheet)
    filename = f"N2应交税费_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-data")
async def n2_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（多税种分sheet）

    Query params:
        sheet: 可选，指定导出单个sheet（N2-2/N2-6/N2-8/N2-9/N2-10）

    Requirements: 3.4
    """
    from app.services.n2_taxes_payable_service import export_data

    if sheet and sheet not in SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(SUPPORTED_SHEETS)}")

    buffer = await export_data(wp_id, db, sheet=sheet)
    filename = f"N2应交税费_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def n2_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（多税种分sheet）

    Query params:
        sheet: 可选，指定导入目标sheet（N2-2/N2-6/N2-8/N2-9/N2-10）

    验证：文件扩展名(.xlsx/.xls)、列头匹配

    Returns:
        { imported_count: int, message: str, warning?: str }

    Requirements: 3.4
    """
    from app.services.n2_taxes_payable_service import import_data

    if sheet and sheet not in SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(SUPPORTED_SHEETS)}")

    # 文件扩展名校验
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in (".xlsx", ".xls"):
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 .xlsx/.xls")

    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# AI辅助（section-based）
# ═══════════════════════════════════════════════════════════════════════════════

_AI_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 N2《应交税费》。
科目2221应交税费（贷方/负债类），核心关注：
- 各税种应交额的准确性和完整性
- 增值税进销项测算（销项=销售额×税率、应交=销项-进项）
- 城建税/教育费附加计税依据正确性
- 房产税从价/从租计算合规性
- 土地增值税四级累进适用税率正确性
- 出口退税额与批复核对
- 各税种计提与N4税金及附加联动一致性

负债类公式：期末=期初+本期贷方（计提）-本期借方（缴纳）

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adjudication-analysis": (
        "请生成N2-1审定表的审计分析，评价各税种应交额变动合理性，"
        "关注各税种期末余额与申报表数据的差异，以及负债类取数方向的正确性。"
    ),
    "vat-conclusion": (
        "请生成N2-6增值税测算表的审计结论，评价销项税额计算准确性、"
        "进项税额抵扣合规性、进项转出合理性，以及增值税税负率是否处于行业正常区间。"
    ),
    "surtax-conclusion": (
        "请生成N2-8其他税费测算表的审计结论，评价城建税及教育费附加"
        "计税依据取数正确性（应等于增值税+消费税应纳税额）、税率适用合规性。"
    ),
    "property-tax-conclusion": (
        "请生成N2-9房产税测算表的审计结论，评价从价计征（原值×(1-扣除比例)×1.2%）"
        "和从租计征（租金×12%）的计算准确性，以及扣除比例适用的合规性。"
    ),
    "lvt-conclusion": (
        "请生成N2-10土地增值税测算表的审计结论，评价增值额计算准确性、"
        "四级累进税率档次适用正确性、速算扣除系数使用合规性。"
    ),
    "overall-opinion": (
        "请生成N2应交税费的整体审计意见，综合审定表各税种余额分析、"
        "各测算表验证结果、明细表核对情况、税收政策合规检查结论，"
        "形成对科目2221列报与披露的总体结论。"
    ),
}

_SUPPORTED_AI_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/{wp_id}/ai-assist")
async def n2_ai_assist(
    wp_id: str,
    body: N2AiAssistRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> N2AiAssistResponse:
    """AI辅助生成（section-based）

    支持 sections:
    - adjudication-analysis: 审定表分析
    - vat-conclusion: 增值税测算结论
    - surtax-conclusion: 其他税费测算结论
    - property-tax-conclusion: 房产税测算结论
    - lvt-conclusion: 土地增值税测算结论
    - overall-opinion: 整体审计意见

    Requirements: 3.4
    """
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED_AI_SECTIONS:
        raise HTTPException(
            400, f"不支持的 section: {body.section}。支持: {sorted(_SUPPORTED_AI_SECTIONS)}"
        )

    # 加载项目上下文
    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_ai_user_prompt(
        body.section, body.existingContent, body.relatedContext, project_context
    )

    messages = [
        {"role": "system", "content": _AI_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        result = await asyncio.wait_for(
            chat_completion(messages=messages, temperature=0.3, max_tokens=2000),
            timeout=_AI_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "AI 生成超时（30秒），请重试")

    if isinstance(result, str) and result.startswith("["):
        return N2AiAssistResponse(content="", sources=[])

    return N2AiAssistResponse(content=result if isinstance(result, str) else "", sources=[])


# ═══════════════════════════════════════════════════════════════════════════════
# TB回写（科目2221，贷方/负债类）
# ═══════════════════════════════════════════════════════════════════════════════


@router.put("/{wp_id}/tb-writeback")
async def n2_tb_writeback(
    wp_id: str,
    request: TBWritebackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TBWritebackResponse:
    """审定数回写到 trial_balance（科目2221应交税费）

    负债类贷方科目 — 审定数回写后触发 TB 缓存失效。
    前端 useN2FormData.writebackTB(amount) 调用。

    Requirements: 3.4
    """
    from app.models.audit_platform_models import TrialBalance

    # 从 wp_id 获取 project_id
    wp_result = await db.execute(
        sa.text("SELECT project_id FROM working_papers WHERE id = :wp_id"),
        {"wp_id": wp_id},
    )
    wp_row = wp_result.fetchone()
    if not wp_row:
        raise HTTPException(404, f"底稿不存在: {wp_id}")

    project_id = wp_row[0]
    account_code = request.account_code

    # 查找匹配的 trial_balance 行
    stmt = (
        sa.select(TrialBalance)
        .where(
            TrialBalance.project_id == project_id,
            TrialBalance.standard_account_code == account_code,
            TrialBalance.is_deleted == sa.false(),
        )
        .order_by(TrialBalance.year.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if not row:
        raise HTTPException(
            404,
            f"试算表中未找到科目 {account_code}，请先导入试算表数据",
        )

    # 更新 audited_amount（负债类贷方科目：期末余额）
    row.audited_amount = Decimal(str(request.audited_amount))
    await db.flush()
    await db.commit()

    logger.info(
        "N2 TB回写完成: project=%s account=%s amount=%s",
        project_id, account_code, request.audited_amount,
    )

    return TBWritebackResponse(
        message="回写成功",
        account_code=account_code,
        audited_amount=str(row.audited_amount),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# OCR识别（行级附件）
# ═══════════════════════════════════════════════════════════════════════════════

_VOUCHER_FIELDS = {
    "voucherDate": "凭证日期",
    "voucherNo": "凭证编号",
    "taxType": "税种",
    "taxPeriod": "税款所属期间",
    "businessContent": "业务内容/摘要",
    "debitAmount": "借方金额(数字)",
    "creditAmount": "贷方金额(数字)",
    "summary": "识别摘要",
}

_EMPTY_FIELDS = {k: (0 if k in ("debitAmount", "creditAmount") else "") for k in _VOUCHER_FIELDS}


@router.post("/{wp_id}/contract-ocr", response_model=N2VoucherOcrResponse)
async def n2_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> N2VoucherOcrResponse:
    """OCR识别（行级附件） — 税费缴纳凭证/纳税申报表附件

    上传PDF/图片 → OCR识别 → LLM提取税费相关字段 → 返回结构化数据。
    前端通过ElMessageBox确认后merge到对应行。

    Requirements: 3.4
    """
    allowed = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，支持: {', '.join(allowed)}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "vouchers"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{attachment_id}{suffix}"

    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    # OCR识别
    ocr_text = ""
    try:
        ocr_result = await UnifiedOCRService().recognize(str(file_path))
        ocr_text = ocr_result.get("text", "")
    except Exception as e:  # noqa: BLE001
        logger.warning("N2 voucher OCR failed: %s", e)
        return N2VoucherOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY_FIELDS),
            summary="",
            confidence=0,
        )

    if not ocr_text.strip():
        return N2VoucherOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY_FIELDS),
            summary="",
            confidence=0,
        )

    # LLM结构化提取
    extracted = dict(_EMPTY_FIELDS)
    summary = ocr_text[:200].replace("\n", " ")
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是审计凭证识别专家。从OCR文本提取应交税费相关凭证/纳税申报表字段，"
                    f"严格返回JSON：{json.dumps(_VOUCHER_FIELDS, ensure_ascii=False)}"
                ),
            },
            {"role": "user", "content": f"OCR文本：\n{ocr_text[:5000]}"},
        ]
        llm_result = await chat_completion(messages=messages, temperature=0.1, max_tokens=800)
        if isinstance(llm_result, str):
            json_str = llm_result.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                for key in _VOUCHER_FIELDS:
                    if key in parsed and parsed[key] is not None:
                        extracted[key] = parsed[key]
                summary = str(
                    extracted.get("summary")
                    or extracted.get("businessContent")
                    or summary
                )
    except Exception as e:  # noqa: BLE001
        logger.warning("N2 voucher LLM extract failed: %s", e)

    filled = sum(1 for k, v in extracted.items() if v and v != "" and v != 0)
    confidence = round(filled / max(len(_VOUCHER_FIELDS), 1), 2)

    return N2VoucherOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted,
        summary=summary,
        confidence=confidence,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


async def _load_project_context(wp_id: str, db: AsyncSession) -> dict[str, Any]:
    """从 wp_id 加载项目上下文信息供 AI 生成使用。"""
    result = await db.execute(
        sa.text("""
            SELECT p.name AS client_name, p.audit_year, p.industry
            FROM working_papers wp
            JOIN projects p ON p.id = wp.project_id
            WHERE wp.id = :wp_id
        """),
        {"wp_id": wp_id},
    )
    row = result.fetchone()
    if not row:
        return {}
    return {
        "client_name": row.client_name or "",
        "audit_year": str(row.audit_year or ""),
        "industry": row.industry or "",
    }


def _build_ai_user_prompt(
    section: str,
    existing_content: str,
    related_context: dict[str, Any],
    project_context: dict[str, Any],
) -> str:
    """构建AI辅助用户提示词。"""
    parts: list[str] = [f"## 任务\n{_SECTION_PROMPTS.get(section, '请生成审计文本。')}\n"]

    # 项目信息
    ctx_lines = []
    if project_context.get("client_name"):
        ctx_lines.append(f"客户名称：{project_context['client_name']}")
    if project_context.get("audit_year"):
        ctx_lines.append(f"审计年度：{project_context['audit_year']}")
    if project_context.get("industry"):
        ctx_lines.append(f"行业：{project_context['industry']}")
    if ctx_lines:
        parts.append("## 项目信息\n" + "\n".join(ctx_lines) + "\n")

    # 关联上下文
    if related_context:
        parts.append(f"## 关联数据\n{json.dumps(related_context, ensure_ascii=False, indent=2)}\n")

    # 现有内容
    if existing_content.strip():
        parts.append(f"## 现有内容（需要改进/补充）\n{existing_content}\n")

    return "\n".join(parts)
