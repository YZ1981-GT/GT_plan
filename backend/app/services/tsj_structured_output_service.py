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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    AIConfirmationStatus,
    AIContent,
    AIContentType,
    ConfidenceLevel,
)
from app.models.v3_refinement_models import AiContentLog
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


class TsjConfirmationLogWriteError(RuntimeError):
    """TSJ 复核结果无法进入可确认日志时的 fail-closed 信号。

    这个异常必须向真实路由冒泡。仅保留 `AIContent` 而没有 `ai_content_log` 会让
    `AIContentMustBeConfirmedRule` 看不见 pending 内容，签字因此错误放行。
    """


async def _log_ai_content(
    *,
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    workpaper_id: UUID,
    content: str,
    target_cell: str | None,
) -> str:
    """原子写一条可确认的 ``ai_content_log`` 并返回真实 ID。

    ``wrap_ai_output_with_log`` 为兼容旧调用方会吞掉内部写入错误，只返回没有
    ``ai_content_log_id`` 的基础 dict。本函数把这类静默失败转为
    :class:`TsjConfirmationLogWriteError`。调用方在自己的外层 SAVEPOINT 内创建
    ``AIContent``，所以错误会撤销**本次全部发现**，而不会留下签字门禁读不到的
    pending 内容。
    """
    try:
        async with db.begin_nested():
            result = await wrap_ai_output_with_log(
                content=content,
                db=db,
                project_id=project_id,
                user_id=user_id,
                instance_type="workpaper",
                instance_id=workpaper_id,
                # 空串要变 None，否则 create() 会拼出末尾带冒号的 target_cell
                target_cell=target_cell or None,
                wp_id=workpaper_id,
            )
            raw_id = result.get("ai_content_log_id")
            try:
                log_id = UUID(str(raw_id))
            except (TypeError, ValueError, AttributeError) as exc:
                raise TsjConfirmationLogWriteError(
                    "wrap_ai_output_with_log 未返回合法 ai_content_log_id"
                ) from exc

            # 不能只信返回值：真实行必须已在同一事务查到，防止未来写入器返回
            # 伪造 ID 或 flush 未生效却把结果宣称为「待确认」。
            exists = await db.scalar(
                select(AiContentLog.id).where(
                    AiContentLog.id == log_id,
                    AiContentLog.project_id == project_id,
                    AiContentLog.user_id == user_id,
                )
            )
            if exists is None or result.get("confirm_action") != "pending":
                raise TsjConfirmationLogWriteError(
                    "ai_content_log 未真实写入 pending 状态"
                )
            return str(log_id)
    except Exception as exc:
        logger.error(
            "TSJ 确认日志写入失败，本次复核将整体回滚：%s "
            "(project_id=%s, workpaper_id=%s, target_cell=%s)",
            exc,
            project_id,
            workpaper_id,
            target_cell,
        )
        raise TsjConfirmationLogWriteError(
            "AI 复核结果未能进入确认流程，请稍后重试"
        ) from exc


async def write_findings_to_ai_content(
    db: AsyncSession,
    project_id: UUID,
    workpaper_id: UUID,
    wp_code: str,
    findings: list[dict],
    audit_cycle: str | None = None,
    *,
    user_id: UUID,
    review_type: str = "structured",
    parse_failed: bool = False,
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
        user_id: 触发本次复核的用户 ID。**必填**（关键字参数）——
            ``wrap_ai_output_with_log`` 缺它就整段跳过写表，签字门禁随之失效；
            设成必填是为了让新调用方无法再漏传。

    Returns:
        写入的 AIContent 记录列表
    """
    if not findings:
        return []

    results: list[AIContent] = []
    # 外层保存点包住本次**全部** AIContent + ai_content_log：确认日志写入失败
    # （`TsjConfirmationLogWriteError`）或其他任何异常都让保存点回滚并原样冒泡，
    # 不会留下 gate 读不到的 pending AIContent，PostgreSQL 上外层会话仍可继续用。
    # 本服务既不 commit 也不 rollback 调用方事务：保存点正常退出时已 flush；真实
    # 路由还要校验 finding 数量与每条 ai_content_log_id，DTO 全部构造成功后才在
    # 请求边界统一 commit，任何失败由路由 rollback。
    async with db.begin_nested():
        for finding in findings:
            description = str(finding.get("description") or "")
            remediation = str(finding.get("remediation") or "")
            content_text = (
                f"{description}\n整改建议：{remediation}"
                if remediation
                else description
            )
            sheet = str(finding.get("sheet") or "")
            cell_range = str(finding.get("cell_range") or "")
            # target_cell 前缀化编码: {wp_code}:{sheet}:{cell_range}
            target_cell = (
                f"{wp_code}:{sheet}:{cell_range}"
                if sheet and cell_range
                else ""
            )
            source_data = {
                "issue_type": str(finding.get("issue_type") or ""),
                "severity": str(finding.get("severity") or "medium"),
                "sheet": sheet,
                "cell_range": cell_range,
                "evidence_ref": str(finding.get("evidence_ref") or ""),
                "audit_cycle": audit_cycle,
                "review_type": review_type,
                "target_cell": target_cell,
            }
            if parse_failed:
                source_data["parse_failed"] = True

            ai_content = AIContent(
                project_id=project_id,
                workpaper_id=workpaper_id,
                content_type=AIContentType.risk_alert,
                content_text=content_text,
                data_sources=source_data,
                generation_model="unknown",
                generation_time=datetime.now(timezone.utc),
                confidence_level=_severity_to_confidence(source_data["severity"]),
                confirmation_status=AIConfirmationStatus.pending,
            )
            db.add(ai_content)
            log_id = await _log_ai_content(
                db=db,
                project_id=project_id,
                user_id=user_id,
                workpaper_id=workpaper_id,
                content=content_text,
                target_cell=target_cell,
            )
            # JSONB 原地 mutate 不会触发 ORM UPDATE；新对象整体赋值，且把前端
            # 确认按钮真正需要的 ai_content_log id 带回 endpoint 响应。
            ai_content.data_sources = {
                **source_data,
                "ai_content_log_id": log_id,
            }
            results.append(ai_content)

    logger.info(
        "结构化复核已写入当前事务，等待调用方提交: project=%s, wp=%s, findings=%s",
        project_id,
        workpaper_id,
        len(results),
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
    *,
    user_id: UUID,
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
        user_id: 触发本次复核的用户 ID（**必填**，透传给 ai_content_log）

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
            user_id=user_id,
        )

    # Fallback 也统一走同一保存点 / 确认日志路径：若日志写失败，本次原文同样不应
    # 以「待确认」的假状态留在 ai_content 表里。用户可重试，不能得到无法确认却
    # 又不阻断签字的半成品。
    logger.warning(
        "结构化解析失败，结果将以可确认的全文记录保存: project=%s, wp=%s, response_length=%s",
        project_id,
        workpaper_id,
        len(response_text),
    )
    return await write_findings_to_ai_content(
        db=db,
        project_id=project_id,
        workpaper_id=workpaper_id,
        wp_code=wp_code,
        findings=[
            {
                "issue_type": "unstructured_fallback",
                "severity": "medium",
                "description": response_text,
                "remediation": "",
                "sheet": "",
                "cell_range": "",
                "evidence_ref": "",
            }
        ],
        audit_cycle=audit_cycle,
        user_id=user_id,
        review_type="unstructured_fallback",
        parse_failed=True,
    )
