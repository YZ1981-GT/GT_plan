"""
TSJ 结构化输出服务

LLM 复核结果解析为结构化 JSON（findings 数组），逐条写入 AiContent；
解析失败时 fallback 为纯文本存储，确保不丢数据。
"""

import json
import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    AIConfirmationStatus,
    AIContent,
    AIContentType,
    ConfidenceLevel,
)
from app.services.wp_ai_service import wrap_ai_output_with_log

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Task 3.1: 结构化输出指令
# --------------------------------------------------------------------------

STRUCTURED_OUTPUT_INSTRUCTION = """
请严格按以下 JSON 格式输出复核发现，不要输出任何其他内容：

```json
{
  "findings": [
    {
      "issue_type": "数值错误|逻辑错误|披露缺失|证据不足",
      "severity": "high|medium|low",
      "sheet": "工作表名称",
      "cell_range": "B5:D5",
      "description": "问题描述",
      "evidence_ref": "D2-3!B5",
      "remediation": "整改建议"
    }
  ]
}
```

规则：
- issue_type 必须是以下之一：数值错误、逻辑错误、披露缺失、证据不足
- severity 必须是 high、medium、low 之一
- 如果没有发现问题，返回空数组 {"findings": []}
- 不要在 JSON 外添加任何解释文字
""".strip()


def build_structured_prompt(base_prompt: str, workpaper_content: str) -> str:
    """
    将结构化输出指令附加到基础 prompt 后面。

    Args:
        base_prompt: TSJ 提示词原文
        workpaper_content: 底稿文本内容

    Returns:
        完整 prompt（含结构化输出要求）
    """
    return (
        f"{base_prompt}\n\n"
        f"---\n## 底稿内容\n\n{workpaper_content}\n\n"
        f"---\n## 输出格式要求\n\n{STRUCTURED_OUTPUT_INSTRUCTION}"
    )


# --------------------------------------------------------------------------
# Task 3.2: 解析 JSON 并写入 AiContent
# --------------------------------------------------------------------------

# 匹配 markdown 代码块中的 JSON
_CODE_BLOCK_PATTERN = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL
)
# 匹配最外层 {...}
_JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def parse_findings_json(response_text: str) -> list[dict] | None:
    """
    从 LLM 响应中提取结构化 findings JSON。

    尝试顺序：
    1. 直接 json.loads 整段文本
    2. 提取 ```json ... ``` 代码块
    3. 查找最外层 {...} 模式

    Args:
        response_text: LLM 原始响应文本

    Returns:
        findings 列表，解析失败返回 None
    """
    if not response_text or not response_text.strip():
        return None

    # 策略 1: 直接解析
    parsed = _try_parse(response_text.strip())
    if parsed is not None:
        return parsed

    # 策略 2: 提取代码块
    match = _CODE_BLOCK_PATTERN.search(response_text)
    if match:
        parsed = _try_parse(match.group(1).strip())
        if parsed is not None:
            return parsed

    # 策略 3: 查找 {...} 模式
    match = _JSON_OBJECT_PATTERN.search(response_text)
    if match:
        parsed = _try_parse(match.group(0))
        if parsed is not None:
            return parsed

    return None


def _try_parse(text: str) -> list[dict] | None:
    """尝试解析 JSON 文本为 findings 列表。"""
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "findings" in data:
            findings = data["findings"]
            if isinstance(findings, list):
                return findings
        # 如果顶层就是数组
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _severity_to_confidence(severity: str) -> ConfidenceLevel:
    """将 severity 映射为 confidence_level。"""
    mapping = {"high": ConfidenceLevel.high, "medium": ConfidenceLevel.medium}
    return mapping.get(severity, ConfidenceLevel.low)


async def write_findings_to_ai_content(
    db: AsyncSession,
    project_id: UUID,
    workpaper_id: UUID,
    wp_code: str,
    findings: list[dict],
    audit_cycle: str | None = None,
) -> list[AIContent]:
    """
    将每条 finding 写入一条 AIContent 记录。

    Args:
        db: 数据库会话
        project_id: 项目 ID
        workpaper_id: 底稿 ID
        wp_code: 底稿编码（如 D2-3）
        findings: 解析后的 findings 列表
        audit_cycle: 审计循环名称

    Returns:
        写入的 AIContent 记录列表
    """
    results: list[AIContent] = []

    for finding in findings:
        description = finding.get("description", "")
        remediation = finding.get("remediation", "")
        content_text = f"{description}\n整改建议：{remediation}" if remediation else description

        sheet = finding.get("sheet", "")
        cell_range = finding.get("cell_range", "")
        # target_cell 前缀化编码: {wp_code}:{sheet}:{cell_range}
        target_cell = f"{wp_code}:{sheet}:{cell_range}" if sheet and cell_range else ""

        ai_content = AIContent(
            project_id=project_id,
            workpaper_id=workpaper_id,
            content_type=AIContentType.risk_alert,
            content_text=content_text,
            data_sources={
                "issue_type": finding.get("issue_type", ""),
                "severity": finding.get("severity", "medium"),
                "sheet": sheet,
                "cell_range": cell_range,
                "evidence_ref": finding.get("evidence_ref", ""),
                "audit_cycle": audit_cycle,
                "review_type": "structured",
                "target_cell": target_cell,
            },
            generation_model="unknown",
            generation_time=datetime.now(timezone.utc),
            confidence_level=_severity_to_confidence(
                finding.get("severity", "medium")
            ),
            confirmation_status=AIConfirmationStatus.pending,
        )
        db.add(ai_content)
        results.append(ai_content)

        # Task 4.1: 同时写入 ai_content_log 以触发 AIContentMustBeConfirmedRule 门禁
        try:
            await wrap_ai_output_with_log(
                content=content_text,
                db=db,
                project_id=project_id,
                instance_type="workpaper",
                instance_id=workpaper_id,
            )
        except Exception as e:
            logger.warning(f"wrap_ai_output_with_log failed for finding: {e}")

    if results:
        await db.commit()
        for r in results:
            await db.refresh(r)

    logger.info(
        f"结构化复核写入完成: project={project_id}, wp={workpaper_id}, "
        f"findings={len(results)}"
    )
    return results


# --------------------------------------------------------------------------
# Task 3.3: 解析失败 fallback
# --------------------------------------------------------------------------


async def process_review_response(
    db: AsyncSession,
    project_id: UUID,
    workpaper_id: UUID,
    wp_code: str,
    response_text: str,
    audit_cycle: str | None = None,
) -> list[AIContent]:
    """
    处理 LLM 复核响应：优先结构化解析，失败则 fallback 纯文本存储。

    Args:
        db: 数据库会话
        project_id: 项目 ID
        workpaper_id: 底稿 ID
        wp_code: 底稿编码
        response_text: LLM 原始响应
        audit_cycle: 审计循环名称

    Returns:
        写入的 AIContent 记录列表（结构化时多条，fallback 时单条）
    """
    # 尝试结构化解析
    findings = parse_findings_json(response_text)

    if findings is not None:
        logger.info(
            f"结构化解析成功: {len(findings)} 条发现, "
            f"project={project_id}, wp={workpaper_id}"
        )
        return await write_findings_to_ai_content(
            db=db,
            project_id=project_id,
            workpaper_id=workpaper_id,
            wp_code=wp_code,
            findings=findings,
            audit_cycle=audit_cycle,
        )

    # Fallback: 纯文本存储（不丢数据）
    logger.warning(
        f"结构化解析失败，fallback 纯文本存储: "
        f"project={project_id}, wp={workpaper_id}, "
        f"response_length={len(response_text)}"
    )

    ai_content = AIContent(
        project_id=project_id,
        workpaper_id=workpaper_id,
        content_type=AIContentType.risk_alert,
        content_text=response_text,
        data_sources={
            "audit_cycle": audit_cycle,
            "review_type": "unstructured_fallback",
            "parse_failed": True,
        },
        generation_model="unknown",
        generation_time=datetime.now(timezone.utc),
        confidence_level=ConfidenceLevel.medium,
        confirmation_status=AIConfirmationStatus.pending,
    )
    db.add(ai_content)

    # Task 4.1: fallback 路径同样写入 ai_content_log 以触发确认流门禁
    try:
        await wrap_ai_output_with_log(
            content=response_text,
            db=db,
            project_id=project_id,
            instance_type="workpaper",
            instance_id=workpaper_id,
        )
    except Exception as e:
        logger.warning(f"wrap_ai_output_with_log failed for fallback: {e}")

    await db.commit()
    await db.refresh(ai_content)

    return [ai_content]
