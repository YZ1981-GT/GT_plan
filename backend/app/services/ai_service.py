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
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator
from uuid import UUID

import httpx

try:
    import paddleocr  # type: ignore
except Exception:
    paddleocr = None  # type: ignore

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AIModelConfig, AIModelType, AIProvider
from app.services.llm_runtime import (
    LLMRuntimeError,
    chat_stream as runtime_chat_stream,
    chat_sync as runtime_chat_sync,
    embedding as runtime_embedding,
    merge_system_messages,
    probe_runtime_config,
    resolve_config_from_model,
    resolve_runtime_config,
    test_runtime_config,
)

logger = logging.getLogger(__name__)

# 全局 PaddleOCR 实例（延迟初始化）
_paddle_ocr: "paddleocr.PaddleOCR | None" = None


def _get_paddle_ocr() -> "paddleocr.PaddleOCR":
    """延迟初始化 PaddleOCR 实例"""
    global _paddle_ocr
    if paddleocr is None:
        raise AIServiceUnavailableError(
            "PaddleOCR 未安装（当前 Python 环境无 paddleocr 包）"
        )
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


@dataclass(frozen=True)
class ModelValidationFailure:
    """最近一次模型验证失败的稳定 code 与可展示原因（不含上游正文或密钥）。"""

    code: str
    message: str


# ============================================================================
# 辅助函数
# ============================================================================


async def _get_ollama_client() -> httpx.AsyncClient:
    """获取 Ollama HTTP 客户端（备用）"""
    return httpx.AsyncClient(
        base_url=settings.OLLAMA_BASE_URL,
        timeout=httpx.Timeout(60.0, connect=10.0),
        mounts={},
        trust_env=False,
    )


async def _get_llm_client() -> httpx.AsyncClient:
    """获取 LLM HTTP 客户端（默认 vLLM OpenAI 兼容 API）。

    此函数是无 DB 上下文的兜底路径，从全局 settings 读配置。
    有 DB session 的场景应优先用 build_client_for_model(active_model)。
    """
    return httpx.AsyncClient(
        base_url=settings.LLM_BASE_URL,
        headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
        timeout=httpx.Timeout(120.0, connect=10.0),
        mounts={},
        trust_env=False,
    )


async def _get_embedding_client() -> httpx.AsyncClient:
    """获取 Embedding HTTP 客户端（独立 bge-m3 服务，端口 8101）"""
    return httpx.AsyncClient(
        base_url=settings.LLM_EMBEDDING_BASE_URL,
        headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
        timeout=httpx.Timeout(30.0, connect=5.0),
        mounts={},
        trust_env=False,
    )


def _merge_system_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """向后兼容旧测试/调用方；实现委派给统一 runtime。"""
    return merge_system_messages(messages)


async def _get_chromadb_client() -> httpx.AsyncClient:
    """获取 ChromaDB HTTP 客户端（健康检查用短超时，避免拖慢 /api/ai/health）"""
    return httpx.AsyncClient(
        base_url=settings.CHROMADB_URL,
        timeout=httpx.Timeout(2.0, connect=1.0),
        mounts={},
        trust_env=False,
    )


# ============================================================================
# AIService 类
# ============================================================================


class AIService:
    """AI服务统一抽象层"""

    def __init__(self, db: AsyncSession):
        self.db = db
        # switch_model 保持 bool 契约；失败原因留在这里供 router 返回给用户。
        self.last_validation_error: ModelValidationFailure | None = None

    # -------------------------------------------------------------------------
    # 模型管理
    # -------------------------------------------------------------------------

    async def get_active_model(
        self,
        model_type: AIModelType,
        *,
        ocr_capability: str | None = None,
    ) -> AIModelConfig | None:
        """获取 active model；OCR 可按 capability 独立查询。"""
        conditions = [
            AIModelConfig.model_type == model_type,
            AIModelConfig.is_active.is_(True),
            AIModelConfig.is_deleted.is_(False),
        ]
        if model_type == AIModelType.ocr and ocr_capability:
            conditions.append(AIModelConfig.ocr_capability == ocr_capability)
        result = await self.db.execute(select(AIModelConfig).where(*conditions))
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
        """验证并切换 active model；只 flush，由 router 统一 commit。"""
        result = await self.db.execute(
            select(AIModelConfig).where(
                AIModelConfig.model_name == model_name,
                AIModelConfig.model_type == model_type,
                AIModelConfig.is_deleted.is_(False),
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ModelNotFoundError(f"Model not found: {model_name} ({model_type})")
        if not await self._validate_model(model):
            return False

        deactivate_conditions = [
            AIModelConfig.model_type == model_type,
            AIModelConfig.is_deleted.is_(False),
        ]
        if model_type == AIModelType.ocr:
            if not model.ocr_capability:
                raise ModelValidationError("OCR 模型缺少 capability")
            deactivate_conditions.append(
                AIModelConfig.ocr_capability == model.ocr_capability
            )
        await self.db.execute(
            update(AIModelConfig)
            .where(*deactivate_conditions)
            .values(is_active=False)
        )
        model.is_active = True
        await self.db.flush()
        return True

    async def _validate_model(self, model: AIModelConfig) -> bool:
        """通过生产同一 runtime 验证模型；不复制 provider 分支。

        失败原因写入 ``self.last_validation_error``：只返回 False 会让激活接口只能报
        笼统的「检查端点、模型名和凭证」，网络/代理问题被误读成 Key 错误（2026-10-19）。
        """
        self.last_validation_error = None
        if model.provider == AIProvider.paddleocr:
            if model.ocr_protocol == "paddlex_json":
                try:
                    from app.services.remote_ocr_runtime import test_remote_ocr_model

                    await test_remote_ocr_model(model)
                    return True
                except Exception as exc:
                    self._record_validation_failure(exc, "ocr_validation_failed")
                    logger.warning(
                        "Remote PaddleOCR validation failed model=%s code=%s",
                        model.model_name,
                        self.last_validation_error.code,
                    )
                    return False
            try:
                _get_paddle_ocr()
                return True
            except Exception as exc:
                self.last_validation_error = ModelValidationFailure(
                    "engine_unavailable", "本地 PaddleOCR 引擎不可用（未安装或初始化失败）"
                )
                logger.warning("PaddleOCR validation failed: %s", type(exc).__name__)
                return False
        try:
            config = resolve_config_from_model(model)
            await test_runtime_config(config)
            return True
        except (LLMRuntimeError, ValueError) as exc:
            self._record_validation_failure(exc, "invalid_model_config")
            logger.warning(
                "AI model validation failed provider=%s model=%s code=%s",
                model.provider.value,
                model.model_name,
                self.last_validation_error.code,
            )
            return False

    def _record_validation_failure(self, exc: Exception, fallback_code: str) -> None:
        # runtime 异常的 message 已保证不含上游正文与密钥；其他异常只暴露类型。
        code = getattr(exc, "code", None)
        if isinstance(code, str) and code:
            self.last_validation_error = ModelValidationFailure(code, str(exc))
        elif isinstance(exc, ValueError):
            self.last_validation_error = ModelValidationFailure(fallback_code, str(exc))
        else:
            self.last_validation_error = ModelValidationFailure(
                fallback_code, f"验证过程出错（{type(exc).__name__}）"
            )

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
        """使用 DB active model（无记录时 env fallback）完成对话。"""
        if stream:
            return self._chat_stream(model, messages, temperature, max_tokens)
        return await self._chat_sync(model, messages, temperature, max_tokens)

    async def _chat_sync(
        self,
        model: str | None,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        try:
            config = await resolve_runtime_config(
                self.db, AIModelType.chat, requested_model=model
            )
            return await runtime_chat_sync(
                config,
                messages,
                temperature=temperature,
                max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            )
        except LLMRuntimeError as exc:
            raise AIServiceUnavailableError(str(exc)) from exc

    async def _chat_stream(
        self,
        model: str | None,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
    ) -> AsyncGenerator[str, None]:
        try:
            config = await resolve_runtime_config(
                self.db, AIModelType.chat, requested_model=model
            )
            async for chunk in runtime_chat_stream(
                config,
                messages,
                temperature=temperature,
                max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            ):
                yield chunk
        except LLMRuntimeError as exc:
            raise AIServiceUnavailableError(str(exc)) from exc

    # -------------------------------------------------------------------------
    # Embedding 向量化
    # -------------------------------------------------------------------------

    async def embedding(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """使用 active embedding model 生成向量。"""
        try:
            config = await resolve_runtime_config(
                self.db, AIModelType.embedding, requested_model=model
            )
            return await runtime_embedding(config, text)
        except LLMRuntimeError as exc:
            raise AIServiceUnavailableError(str(exc)) from exc

    # -------------------------------------------------------------------------
    # OCR 识别
    # -------------------------------------------------------------------------

    async def ocr_recognize(self, image_path: str) -> dict[str, Any]:
        """
        OCR文字识别 — 代理到 UnifiedOCRService（带双引擎兜底）

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
            from app.services.unified_ocr_service import OCREngine, UnifiedOCRService

            ocr_svc = UnifiedOCRService()
            result = await ocr_svc.recognize(image_path, mode=OCREngine.AUTO)

            # 统一返回格式（UnifiedOCRService 用 "box"，AIService 约定用 "bbox"）
            return {
                "text": result["text"],
                "regions": [
                    {
                        "text": r["text"],
                        "bbox": r.get("box", []),
                        "confidence": r.get("confidence", 0.0),
                    }
                    for r in result.get("regions", [])
                ],
            }

        except Exception as e:
            logger.error(f"OCR recognition failed for {image_path}: {e}")
            raise AIServiceUnavailableError(f"OCR failed: {e}")

    # -------------------------------------------------------------------------
    # 健康检查
    # -------------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """按当前 active chat/embedding 配置检查健康状态，不泄漏凭证。"""

        async def _resolve_model(model_type: AIModelType):
            try:
                return await resolve_runtime_config(self.db, model_type)
            except Exception as exc:
                logger.debug(
                    "%s runtime config failed: %s",
                    model_type.value,
                    type(exc).__name__,
                )
                return None

        async def _probe_model(config):
            if config is None:
                return "unavailable", None
            try:
                status = "healthy" if await probe_runtime_config(config) else "unavailable"
            except Exception as exc:
                logger.debug("runtime health probe failed: %s", type(exc).__name__)
                status = "unavailable"
            safe = config.safe_dict()
            safe.pop("has_api_key", None)
            return status, safe

        async def _probe_paddle() -> str:
            if paddleocr is None:
                return "unavailable"
            try:
                _get_paddle_ocr()
                return "healthy"
            except Exception as exc:
                logger.debug("PaddleOCR health failed: %s", type(exc).__name__)
                return "unavailable"

        async def _probe_chroma() -> str:
            try:
                async with await _get_chromadb_client() as client:
                    response = await asyncio.wait_for(
                        client.get("/api/v1/heartbeat"), timeout=0.8
                    )
                    return "healthy" if response.status_code == 200 else "unavailable"
            except Exception as exc:
                logger.debug("ChromaDB health failed: %s", type(exc).__name__)
                return "unavailable"

        # AsyncSession 不支持并发 execute：先顺序解析 DB 配置，再并行做纯网络探针。
        chat_runtime = await _resolve_model(AIModelType.chat)
        embedding_runtime = await _resolve_model(AIModelType.embedding)
        (chat_status, chat_config), (embedding_status, embedding_config), paddle_status, chroma_status = await asyncio.gather(
            _probe_model(chat_runtime),
            _probe_model(embedding_runtime),
            _probe_paddle(),
            _probe_chroma(),
        )
        chat_provider = chat_config.get("provider") if chat_config else None
        return {
            "llm_status": chat_status,
            "embedding_status": embedding_status,
            # 兼容 UnifiedAIService 和既有前端字段。
            "vllm_status": chat_status if chat_provider != AIProvider.ollama.value else "unavailable",
            "ollama_status": chat_status if chat_provider == AIProvider.ollama.value else "unavailable",
            "paddleocr_status": paddle_status,
            "chromadb_status": chroma_status,
            "active_chat_model": chat_config.get("model_name") if chat_config else None,
            "active_embedding_model": embedding_config.get("model_name") if embedding_config else None,
            "chat_config": chat_config,
            "embedding_config": embedding_config,
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
                "model_name": "Kbenkhaled/Qwen3.5-27B-NVFP4",
                "model_type": AIModelType.chat,
                "provider": AIProvider.openai_compatible,
                "endpoint_url": "http://localhost:8100/v1",
                "is_active": True,
                "context_window": 32768,
                "performance_notes": "Qwen3.5-27B NVFP4量化，本地vLLM推理，128K上下文",
            },
            {
                "model_name": "BAAI/bge-m3",
                "model_type": AIModelType.embedding,
                "provider": AIProvider.openai_compatible,
                "endpoint_url": "http://localhost:8101/v1",
                "is_active": True,
                "context_window": 8192,
                "performance_notes": "bge-m3 本地 vLLM Embedding 服务",
            },
            {
                "model_name": "paddleocr",
                "model_type": AIModelType.ocr,
                "provider": AIProvider.paddleocr,
                "endpoint_url": None,
                "ocr_capability": "ocr",
                "ocr_protocol": "local",
                "auth_scheme": "none",
                "is_active": False,
                "context_window": None,
                "performance_notes": "百度PaddleOCR，中英文识别",
            },
        ]

        from app.services.ai_model_presets import ENTERPRISE_MODEL_PRESETS

        default_models.extend(
            [preset.orm_values() for preset in ENTERPRISE_MODEL_PRESETS]
        )

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

        await db.flush()
