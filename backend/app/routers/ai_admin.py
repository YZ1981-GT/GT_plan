"""AI服务管理 API

覆盖：
- GET  /api/ai/health - AI引擎健康检查
- GET  /api/ai/models - 模型列表
- PUT  /api/ai/models/{id}/activate - 激活模型
- POST /api/ai/evaluate - LLM能力评估
"""

from __future__ import annotations

import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models import AIModelConfig, AIModelType, User
from app.models.ai_schemas import (
    AIEvaluationRequest,
    AIEvaluationResult,
    AIHealthResponse,
    AIModelActivateRequest,
    AIModelConfigResponse,
    AIModelCreate,
)
from app.services.ai_service import AIService
from app.services.unified_ai_service import UnifiedAIService

router = APIRouter(
    prefix="/api/ai",
    tags=["AI管理"],
)


@router.get("/health", response_model=AIHealthResponse)
async def check_ai_health(db: AsyncSession = Depends(get_db)):
    """
    AI引擎健康检查

    检查 Ollama、PaddleOCR、ChromaDB 三个引擎的状态
    """
    svc = AIService(db)
    result = await svc.health_check()
    return AIHealthResponse(**result)


@router.get("/models", response_model=list[AIModelConfigResponse])
async def list_models(db: AsyncSession = Depends(get_db)):
    """获取可用模型列表"""
    svc = AIService(db)
    models = await svc.get_all_models()
    return [AIModelConfigResponse.model_validate(m) for m in models]


@router.post("/models", response_model=AIModelConfigResponse)
async def create_model(
    data: AIModelCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    创建新的AI模型配置
    """
    from uuid import UUID
    from app.models import AIModelConfig

    # 检查是否已存在同名同类型模型
    existing = await db.execute(
        select(AIModelConfig).where(
            AIModelConfig.model_name == data.model_name,
            AIModelConfig.model_type == data.model_type,
            AIModelConfig.is_deleted == False,  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"模型 {data.model_name}（{data.model_type.value}）已存在",
        )

    model = AIModelConfig(
        model_name=data.model_name,
        model_type=data.model_type,
        provider=data.provider,
        endpoint_url=data.endpoint_url,
        is_active=data.is_active,
        context_window=data.context_window,
        performance_notes=data.performance_notes,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return AIModelConfigResponse.model_validate(model)


@router.get("/models/{model_id}", response_model=AIModelConfigResponse)
async def get_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    获取单个模型配置详情
    """
    result = await db.execute(
        select(AIModelConfig).where(
            AIModelConfig.id == model_id,
            AIModelConfig.is_deleted == False,  # noqa: E712
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    return AIModelConfigResponse.model_validate(model)


@router.put("/models/{model_id}/activate")
async def activate_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    激活指定模型（含10秒可用性验证）

    验证通过后自动禁用同类型其他模型
    """
    # 获取模型
    result = await db.execute(
        select(AIModelConfig).where(
            AIModelConfig.id == model_id,
            AIModelConfig.is_deleted == False,  # noqa: E712
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    svc = AIService(db)

    # 执行切换（含验证）
    success = await svc.switch_model(model.model_name, model.model_type)

    if success:
        return {
            "message": "模型激活成功",
            "model_name": model.model_name,
            "model_type": model.model_type.value,
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=f"模型 {model.model_name} 可用性验证失败，请检查服务状态",
        )


@router.post("/evaluate", response_model=AIEvaluationResult)
async def evaluate_llm(
    request: AIEvaluationRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    LLM能力评估

    使用审计领域测试问题集评估模型能力
    """
    svc = AIService(db)

    # 获取当前激活的chat模型
    active_model = await svc.get_active_model(AIModelType.chat)
    model_name = active_model.model_name if active_model else "qwen2.5:7b"

    total_questions = len(request.questions)
    details = []
    total_time = 0.0

    for i, question in enumerate(request.questions):
        start = time.time()
        try:
            # 构建审计域提示
            messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的审计助手，请简洁准确地回答以下审计相关问题。",
                },
                {"role": "user", "content": question},
            ]

            response_text = await svc.chat_completion(
                messages,
                model=model_name,
                stream=False,
                temperature=0.3,
                max_tokens=200,
            )

            elapsed = time.time() - start
            total_time += elapsed

            # 计算简单相似度（如果提供了期望答案）
            score = None
            if request.expected_answers and i < len(request.expected_answers):
                expected = request.expected_answers[i]
                expected_words = set(expected.lower().split())
                response_words = set(response_text.lower().split())
                if expected_words:
                    score = len(expected_words & response_words) / len(expected_words)

            details.append({
                "question": question,
                "response": response_text,
                "response_time": round(elapsed, 2),
                "similarity_score": score,
            })

        except Exception as e:
            details.append({
                "question": question,
                "response": f"Error: {str(e)}",
                "response_time": round(time.time() - start, 2),
                "similarity_score": None,
            })

    avg_time = total_time / total_questions if total_questions > 0 else 0

    # 计算整体准确率
    scores = [d["similarity_score"] for d in details if d["similarity_score"] is not None]
    accuracy = sum(scores) / len(scores) if scores else None

    return AIEvaluationResult(
        model_name=model_name,
        total_questions=total_questions,
        accuracy_score=accuracy,
        avg_response_time=round(avg_time, 2),
        domain_scores={"审计判断": accuracy if accuracy else 0.0},
        details=details,
    )
