"""AI服务统一抽象层 — 屏蔽底层模型差异

提供统一的 AI 能力接口：
- chat_completion: LLM对话，支持同步和SSE流式输出
- embedding: 文本向量化
- ocr_recognize: OCR文字识别
- get_active_model: 获取当前激活的模型
- switch_model: 切换模型（含可用性验证）
- health_check: 检查所有AI引擎状态
"""

import asyncio
import json
import logging
from datetime import datetime
import logging
from datetime import datetime
from typing import Any, AsyncGenerator
from uuid import UUID

import httpx

try:
    import paddleocr  # type: ignore
except ImportError:
    paddleocr = None  # type: ignore

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AIModelConfig, AIModelType, AIProvider

logger = logging.getLogger(__name__)

# 全局 PaddleOCR 实例（延迟初始化）
_paddle_ocr: "paddleocr.PaddleOCR | None" = None


def _get_paddle_ocr() -> "paddleocr.PaddleOCR":
    """延迟初始化 PaddleOCR 实例"""
    global _paddle_ocr
    if _paddle_ocr is None:
        _paddle_ocr = paddleocr.PaddleOCR(
            use_angle_cls=True,
            lang="ch",
            use_gpu=False,
            show_log=False,
        )
    return _paddle_ocr


# ============================================================================
# 异常定义
# ============================================================================


class AIServiceUnavailableError(Exception):
    """AI服务不可用"""
    pass


class ModelNotFoundError(Exception):
    """模型未找到"""
    pass


class ModelValidationError(Exception):
    """模型验证失败"""
    pass


# ============================================================================
# 辅助函数
# ============================================================================


async def _get_ollama_client() -> httpx.AsyncClient:
    """获取 Ollama HTTP 客户端"""
    return httpx.AsyncClient(
        base_url=settings.OLLAMA_BASE_URL,
        timeout=httpx.Timeout(60.0, connect=10.0),
    )


async def _get_chromadb_client() -> httpx.AsyncClient:
    """获取 ChromaDB HTTP 客户端"""
    return httpx.AsyncClient(
        base_url=settings.CHROMADB_URL,
        timeout=httpx.Timeout(30.0, connect=10.0),
    )


# ============================================================================
# AIService 类
# ============================================================================


class AIService:
    """AI服务统一抽象层"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -------------------------------------------------------------------------
    # 模型管理
    # -------------------------------------------------------------------------

    async def get_active_model(self, model_type: AIModelType) -> AIModelConfig | None:
        """获取当前激活的模型配置"""
        result = await self.db.execute(
            select(AIModelConfig).where(
                AIModelConfig.model_type == model_type,
                AIModelConfig.is_active == True,  # noqa: E712
                AIModelConfig.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_all_models(self) -> list[AIModelConfig]:
        """获取所有模型配置"""
        result = await self.db.execute(
            select(AIModelConfig).where(
                AIModelConfig.is_deleted == False  # noqa: E712
            ).order_by(AIModelConfig.model_type, AIModelConfig.model_name)
        )
        return list(result.scalars().all())

    async def switch_model(
        self,
        model_name: str,
        model_type: AIModelType,
    ) -> bool:
        """
        切换模型，含可用性验证（10秒超时）
        返回 True 表示切换成功，False 表示验证失败
        """
        # 查找目标模型
        result = await self.db.execute(
            select(AIModelConfig).where(
                AIModelConfig.model_name == model_name,
                AIModelConfig.model_type == model_type,
                AIModelConfig.is_deleted == False,  # noqa: E712
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ModelNotFoundError(f"Model not found: {model_name} ({model_type})")

        # 可用性验证
        validation_passed = await self._validate_model(model)
        if not validation_passed:
            return False

        # 禁用同类型的其他模型
        await self.db.execute(
            update(AIModelConfig)
            .where(
                AIModelConfig.model_type == model_type,
                AIModelConfig.is_deleted == False,  # noqa: E712
            )
            .values(is_active=False)
        )

        # 激活目标模型
        model.is_active = True
        await self.db.commit()
        return True

    async def _validate_model(self, model: AIModelConfig) -> bool:
        """验证模型可用性（10秒超时）"""
        if model.provider == AIProvider.paddleocr:
            # PaddleOCR 验证：尝试初始化
            try:
                _get_paddle_ocr()
                return True
            except Exception as e:
                logger.warning(f"PaddleOCR validation failed: {e}")
                return False

        elif model.provider == AIProvider.ollama:
            # Ollama 验证：发送测试请求
            try:
                async with await _get_ollama_client() as client:
                    response = await asyncio.wait_for(
                        client.post(
                            "/api/generate",
                            json={
                                "model": model.model_name,
                                "prompt": "hello",
                                "stream": False,
                            },
                        ),
                        timeout=10.0,
                    )
                    return response.status_code == 200
            except (asyncio.TimeoutError, httpx.HTTPError) as e:
                logger.warning(f"Ollama model validation failed for {model.model_name}: {e}")
                return False

        elif model.provider == AIProvider.openai_compatible:
            # OpenAI 兼容验证
            try:
                async with await _get_ollama_client() as client:
                    endpoint = model.endpoint_url or "/v1/chat/completions"
                    response = await asyncio.wait_for(
                        client.post(
                            endpoint,
                            json={
                                "model": model.model_name,
                                "messages": [{"role": "user", "content": "hi"}],
                                "max_tokens": 5,
                            },
                        ),
                        timeout=10.0,
                    )
                    return response.status_code == 200
            except (asyncio.TimeoutError, httpx.HTTPError) as e:
                logger.warning(f"OpenAI-compatible model validation failed: {e}")
                return False

        return False

    # -------------------------------------------------------------------------
    # LLM 对话
    # -------------------------------------------------------------------------

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        stream: bool = False,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str | AsyncGenerator[str, None]:
        """
        LLM对话，支持同步和SSE流式输出

        Args:
            messages: 对话消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称，默认使用激活的 chat 模型
            stream: 是否流式输出
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            同步模式：完整响应字符串
            流式模式：AsyncGenerator，逐字产出
        """
        # 获取模型
        if model is None:
            active_model = await self.get_active_model(AIModelType.chat)
            if active_model:
                model = active_model.model_name
            else:
                model = settings.DEFAULT_CHAT_MODEL

        if stream:
            return self._chat_stream(model, messages, temperature, max_tokens)
        else:
            return await self._chat_sync(model, messages, temperature, max_tokens)

    async def _chat_sync(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        """同步对话"""
        async with await _get_ollama_client() as client:
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                },
            }
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens

            response = await client.post("/api/chat", json=payload)
            if response.status_code != 200:
                raise AIServiceUnavailableError(
                    f"Ollama returned {response.status_code}"
                )

            data = response.json()
            return data.get("message", {}).get("content", "")

    async def _chat_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
    ) -> AsyncGenerator[str, None]:
        """流式对话"""
        async with await _get_ollama_client() as client:
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": temperature,
                },
            }
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens

            async with client.stream("POST", "/api/chat", json=payload) as response:
                if response.status_code != 200:
                    raise AIServiceUnavailableError(
                        f"Ollama returned {response.status_code}"
                    )

                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

    # -------------------------------------------------------------------------
    # Embedding 向量化
    # -------------------------------------------------------------------------

    async def embedding(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """
        文本向量化

        Args:
            text: 待向量化的文本
            model: embedding模型名称，默认使用激活的 embedding 模型

        Returns:
            嵌入向量列表
        """
        if model is None:
            active_model = await self.get_active_model(AIModelType.embedding)
            if active_model:
                model = active_model.model_name
            else:
                model = settings.DEFAULT_EMBEDDING_MODEL

        async with await _get_ollama_client() as client:
            response = await client.post(
                "/api/embeddings",
                json={
                    "model": model,
                    "prompt": text,
                },
            )
            if response.status_code != 200:
                raise AIServiceUnavailableError(
                    f"Ollama embedding returned {response.status_code}"
                )

            data = response.json()
            return data.get("embedding", [])

    # -------------------------------------------------------------------------
    # OCR 识别
    # -------------------------------------------------------------------------

    async def ocr_recognize(self, image_path: str) -> dict[str, Any]:
        """
        OCR文字识别

        Args:
            image_path: 图片文件路径

        Returns:
            OCR结果字典 {
                "text": str,           # 完整识别文本
                "regions": [           # 文字区域列表
                    {
                        "text": str,
                        "bbox": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]],
                        "confidence": float
                    }
                ]
            }
        """
        try:
            import cv2
            import numpy as np

            ocr = _get_paddle_ocr()

            # PaddleOCR 返回格式: [[box, text, score], ...]
            result = ocr.ocr(image_path, cls=True)

            regions = []
            full_text_parts = []

            if result and result[0]:
                for line in result[0]:
                    box = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                    text = line[1][0]
                    score = line[1][1]

                    regions.append({
                        "text": text,
                        "bbox": box,
                        "confidence": float(score),
                    })
                    full_text_parts.append(text)

            return {
                "text": "\n".join(full_text_parts),
                "regions": regions,
            }

        except Exception as e:
            logger.error(f"OCR recognition failed for {image_path}: {e}")
            raise AIServiceUnavailableError(f"OCR failed: {e}")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """
        检查所有AI引擎健康状态

        Returns:
            健康状态字典
        """
        ollama_status = "unavailable"
        paddleocr_status = "unavailable"
        chromadb_status = "unavailable"
        active_chat_model = None
        active_embedding_model = None

        # 检查 Ollama
        try:
            async with await _get_ollama_client() as client:
                response = await client.get("/api/tags")
                if response.status_code == 200:
                    ollama_status = "healthy"
                    # 获取已安装模型列表
                    models = response.json().get("models", [])
                    if models:
                        # 尝试获取激活的模型
                        chat_model = await self.get_active_model(AIModelType.chat)
                        if chat_model:
                            active_chat_model = chat_model.model_name
                        else:
                            # 使用第一个模型
                            active_chat_model = models[0].get("name", "qwen2.5:7b")

                        embed_model = await self.get_active_model(AIModelType.embedding)
                        if embed_model:
                            active_embedding_model = embed_model.model_name
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")

        # 检查 PaddleOCR
        try:
            _get_paddle_ocr()
            paddleocr_status = "healthy"
        except Exception as e:
            logger.warning(f"PaddleOCR health check failed: {e}")

        # 检查 ChromaDB
        try:
            async with await _get_chromadb_client() as client:
                response = await client.get("/api/v1/heartbeat")
                if response.status_code == 200:
                    chromadb_status = "healthy"
        except Exception as e:
            logger.warning(f"ChromaDB health check failed: {e}")

        return {
            "ollama_status": ollama_status,
            "paddleocr_status": paddleocr_status,
            "chromadb_status": chromadb_status,
            "active_chat_model": active_chat_model,
            "active_embedding_model": active_embedding_model,
            "timestamp": datetime.now().isoformat(),
        }

    # -------------------------------------------------------------------------
    # AI边界检查
    # -------------------------------------------------------------------------

    # AI不可处理的边界任务关键词
    AI_BOUNDARY_KEYWORDS = [
        "审计意见",
        "出具报告",
        "判断是否",
        "决定是否",
        "结论是",
        "最终结论",
        "出具",
        "出具无保留",
        "保留意见",
        "无法表示",
        "否定意见",
        "减值判断",
        "公允价值确定",
        "预计负债估算",
        "舞弊风险识别结论",
        "合并范围判断",
    ]

    def check_boundary(self, task_description: str) -> bool:
        """
        检查请求是否触碰AI不可处理的边界

        Returns:
            True 表示触碰边界，False 表示可以处理
        """
        text = task_description.lower()
        for keyword in self.AI_BOUNDARY_KEYWORDS:
            if keyword.lower() in text:
                return True
        return False

    def get_boundary_response(self) -> str:
        """获取边界触碰时的标准回复"""
        return (
            "此事项需要审计师专业判断，AI仅提供数据参考，不生成结论。"
            "建议您结合项目实际情况和审计准则要求进行判断。"
        )

    # -------------------------------------------------------------------------
    # 预设模型初始化
    # -------------------------------------------------------------------------

    @staticmethod
    async def init_default_models(db: AsyncSession) -> None:
        """初始化默认模型配置（如果不存在）"""
        default_models = [
            {
                "model_name": "qwen2.5:7b",
                "model_type": AIModelType.chat,
                "provider": AIProvider.ollama,
                "endpoint_url": None,
                "is_active": True,
                "context_window": 8192,
                "performance_notes": "通义千问2.5，7B参数，适合审计对话",
            },
            {
                "model_name": "nomic-embed-text",
                "model_type": AIModelType.embedding,
                "provider": AIProvider.ollama,
                "endpoint_url": None,
                "is_active": False,
                "context_window": 8192,
                "performance_notes": "Nomic文本嵌入模型，适合知识库检索",
            },
            {
                "model_name": "paddleocr",
                "model_type": AIModelType.ocr,
                "provider": AIProvider.paddleocr,
                "endpoint_url": None,
                "is_active": False,
                "context_window": None,
                "performance_notes": "百度PaddleOCR，中英文识别",
            },
        ]

        for model_data in default_models:
            # 检查是否已存在
            result = await db.execute(
                select(AIModelConfig).where(
                    AIModelConfig.model_name == model_data["model_name"],
                    AIModelConfig.model_type == model_data["model_type"],
                )
            )
            existing = result.scalar_one_or_none()
            if not existing:
                model = AIModelConfig(**model_data)
                db.add(model)

        await db.commit()
