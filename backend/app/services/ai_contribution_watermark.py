"""AI 贡献声明水印工具 — R3 Sprint 4 Task 23

提供文本级 AI 贡献声明，用于在文档（简报、年报、AI 补注）中
标注 AI 辅助生成的内容。

实际 PDF 水印集成延迟到 pdf_export_engine 调用时执行，
本模块仅提供文本声明生成工具函数。
"""

from __future__ import annotations

from datetime import datetime, timezone


# 默认声明模板
_AI_CONTRIBUTION_STATEMENT_TEMPLATE = (
    "本文档部分内容由 AI 辅助生成，已经人工审核确认。"
    "AI 模型：{model_name}，生成时间：{timestamp}。"
)

# 简短声明（用于页脚/水印）
_AI_CONTRIBUTION_SHORT_TEMPLATE = (
    "AI 辅助生成（{model_name}），已人工审核"
)


def add_ai_contribution_watermark(
    content: str,
    model_name: str = "Qwen3.5-27B",
    timestamp: str | None = None,
    position: str = "both",
) -> str:
    """在文本内容前后添加 AI 贡献声明。

    Args:
        content: 原始文本内容
        model_name: AI 模型名称，默认 "Qwen3.5-27B"
        timestamp: 生成时间字符串，默认当前 UTC 时间
        position: 声明位置
            - "prepend": 仅在开头添加
            - "append": 仅在末尾添加
            - "both": 开头和末尾都添加（默认）

    Returns:
        添加了 AI 贡献声明的文本内容
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    statement = _AI_CONTRIBUTION_STATEMENT_TEMPLATE.format(
        model_name=model_name,
        timestamp=timestamp,
    )

    separator = "\n" + "─" * 40 + "\n"

    if position == "prepend":
        return statement + separator + content
    elif position == "append":
        return content + separator + statement
    else:  # "both"
        return statement + separator + content + separator + statement


def generate_ai_contribution_statement(
    model_name: str = "Qwen3.5-27B",
    timestamp: str | None = None,
) -> str:
    """生成独立的 AI 贡献声明文本（不附加到内容）。

    用于 PDF 水印、页眉页脚等场景，由调用方决定如何嵌入。

    Args:
        model_name: AI 模型名称
        timestamp: 生成时间字符串，默认当前 UTC 时间

    Returns:
        AI 贡献声明文本
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return _AI_CONTRIBUTION_STATEMENT_TEMPLATE.format(
        model_name=model_name,
        timestamp=timestamp,
    )


def generate_short_statement(model_name: str = "Qwen3.5-27B") -> str:
    """生成简短 AI 贡献声明（用于水印/页脚）。

    Args:
        model_name: AI 模型名称

    Returns:
        简短声明文本
    """
    return _AI_CONTRIBUTION_SHORT_TEMPLATE.format(model_name=model_name)
