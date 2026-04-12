"""预置 AI 模型配置初始数据

在应用启动或首次运行时调用 seed_ai_models() 插入默认 AI 模型配置。
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIModelConfig, AIModelType, AIProvider

logger = logging.getLogger(__name__)

# 默认 AI 模型配置
DEFAULT_MODELS = [
    {
        "model_name": "qwen2.5:7b",
        "model_type": AIModelType.chat,
        "provider": AIProvider.ollama,
        "endpoint_url": None,
        "is_active": True,
        "context_window": 8192,
        "performance_notes": "通义千问2.5，7B参数，适合审计对话和分析",
    },
    {
        "model_name": "nomic-embed-text",
        "model_type": AIModelType.embedding,
        "provider": AIProvider.ollama,
        "endpoint_url": None,
        "is_active": False,
        "context_window": 8192,
        "performance_notes": "Nomic 文本嵌入模型，适合知识库语义检索",
    },
    {
        "model_name": "paddleocr",
        "model_type": AIModelType.ocr,
        "provider": AIProvider.paddleocr,
        "endpoint_url": None,
        "is_active": False,
        "context_window": None,
        "performance_notes": "百度 PaddleOCR，中英文识别，适合发票/单据 OCR",
    },
]


async def seed_ai_models(db: AsyncSession) -> list[AIModelConfig]:
    """
    预置 AI 模型配置。

    仅插入不存在的记录，已存在的记录不会被覆盖。

    Returns:
        所有（已存在 + 新插入的）模型列表
    """
    results: list[AIModelConfig] = []

    for model_data in DEFAULT_MODELS:
        # 检查是否已存在
        result = await db.execute(
            select(AIModelConfig).where(
                AIModelConfig.model_name == model_data["model_name"],
                AIModelConfig.model_type == model_data["model_type"],
                AIModelConfig.is_deleted == False,  # noqa: E712
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"模型已存在，跳过: {existing.model_name} ({existing.model_type.value})")
            results.append(existing)
        else:
            model = AIModelConfig(**model_data)
            db.add(model)
            logger.info(f"插入新模型: {model.model_name} ({model.model_type.value})")
            results.append(model)

    await db.commit()

    # 刷新以获取 created_at 等自动字段
    for model in results:
        await db.refresh(model)

    return results


async def ensure_active_chat_model(db: AsyncSession) -> AIModelConfig | None:
    """
    确保至少有一个激活的 chat 模型。

    如果没有激活的 chat 模型，将 qwen2.5:7b 设为激活。
    """
    result = await db.execute(
        select(AIModelConfig).where(
            AIModelConfig.model_type == AIModelType.chat,
            AIModelConfig.is_active == True,  # noqa: E712
            AIModelConfig.is_deleted == False,  # noqa: E712
        )
    )
    active = result.scalar_one_or_none()

    if active:
        return active

    # 没有激活的 chat 模型，激活 qwen2.5:7b
    result = await db.execute(
        select(AIModelConfig).where(
            AIModelConfig.model_name == "qwen2.5:7b",
            AIModelConfig.model_type == AIModelType.chat,
            AIModelConfig.is_deleted == False,  # noqa: E712
        )
    )
    model = result.scalar_one_or_none()
    if model:
        model.is_active = True
        await db.commit()
        await db.refresh(model)
        logger.info("已激活 qwen2.5:7b 作为默认 chat 模型")
    return model
