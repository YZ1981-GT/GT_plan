"""AI服务统一抽象层 — 屏蔽底层模型差异

提供统一的 AI 能力接口：
- chat_completion: LLM对话（本机优先路由，支持同步和SSE流式输出）
- embedding: 文本向量化（单一启用模型，不跨模型兜底）
- ocr_recognize: OCR文字识别
- get_active_model: 路由中排在最前的已启用模型
- switch_model: 启用模型参与路由（含可用性验证）
- health_check: 检查所有AI引擎状态
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AIModelConfig, AIModelType, AIProvider
from app.models.ai_model_options import AIDeployment
from app.services.llm_route import route_chat_stream, route_chat_sync
from app.services.llm_runtime import (
    LLMRuntimeError,
    deployment_of,
    embedding as runtime_embedding,
    enabled_model_rows,
    merge_system_messages,
    resolve_config_from_model,
    resolve_route,
    resolve_runtime_config,
    test_runtime_config,
)

logger = logging.getLogger(__name__)


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
    """最近一次模型验证失败的稳定 code 与可展示原因（不含上游正文或密钥）。

    ``kind`` 与 ``LLMRuntimeError.kind`` 同口径：``unavailable`` 表示服务当前不可用，
    启用本机模型时允许带提示启用（调用时自动走服务器兜底）。
    """

    code: str
    message: str
    kind: str = "config"


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
        # 本机模型「当前不可用但已启用」时的提示（R4.2）。
        self.last_validation_warning: ModelValidationFailure | None = None

    # -------------------------------------------------------------------------
    # 模型管理
    # -------------------------------------------------------------------------

    async def get_active_model(
        self,
        model_type: AIModelType,
        *,
        ocr_capability: str | None = None,
    ) -> AIModelConfig | None:
        """路由中排在最前的已启用模型（本机优先）；OCR 可按能力槽查询。

        V197 起同类型可同时启用本机与服务器各一条，不能再假设「只有一行」。
        """
        rows = await enabled_model_rows(self.db, model_type, ocr_capability=ocr_capability)
        if not rows:
            return None
        rows.sort(key=lambda row: 0 if deployment_of(row) == AIDeployment.local.value else 1)
        return rows[0]

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
        """启用模型参与路由；只 flush，由 router 统一 commit（ADR-ROUTE-002）。

        只替换同类型（OCR 同能力槽）同部署位置的那一条；向量只保留一条。服务器模型必须通过
        真实连接测试；本机模型仅因「当前不可用」失败时仍启用，并在 ``last_validation_warning``
        留提示（调用时自动走服务器兜底）。
        """
        self.last_validation_warning = None
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
        deployment = deployment_of(model)
        if not await self._validate_model(model):
            failure = self.last_validation_error
            local = deployment == AIDeployment.local.value
            is_preset = model.preset_key is not None
            # 本机模型 / 企业预设模型仅因「当前不可达」时仍允许启用
            can_skip = (
                failure is not None
                and failure.kind == "unavailable"
                and (local or is_preset)
            )
            if not can_skip:
                return False
            self.last_validation_warning = failure
            self.last_validation_error = None

        deactivate_conditions = [
            AIModelConfig.model_type == model_type,
            AIModelConfig.is_deleted.is_(False),
            AIModelConfig.id != model.id,
        ]
        if model_type == AIModelType.ocr:
            if not model.ocr_capability:
                raise ModelValidationError("OCR 模型缺少 capability")
            deactivate_conditions.append(
                AIModelConfig.ocr_capability == model.ocr_capability
            )
        if model_type != AIModelType.embedding:
            deactivate_conditions.append(AIModelConfig.deployment == deployment)
        await self.db.execute(
            update(AIModelConfig)
            .where(*deactivate_conditions)
            .values(is_active=False)
        )
        model.deployment = deployment
        model.is_active = True
        await self.db.flush()
        return True

    async def disable_model(self, model: AIModelConfig) -> None:
        """停用：退出路由（不做验证）；只 flush，由 router 统一 commit。"""
        model.is_active = False
        await self.db.flush()

    @staticmethod
    async def route_slot_taken(
        db: AsyncSession,
        *,
        model_type: AIModelType,
        deployment: str,
        ocr_capability: str | None = None,
        exclude_id: Any = None,
    ) -> bool:
        """同一路由位置（V197 唯一约束口径）是否已有其他已启用模型。"""
        conditions = [
            AIModelConfig.model_type == model_type,
            AIModelConfig.is_active.is_(True),
            AIModelConfig.is_deleted.is_(False),
        ]
        if exclude_id is not None:
            conditions.append(AIModelConfig.id != exclude_id)
        if model_type == AIModelType.ocr:
            conditions.append(AIModelConfig.ocr_capability == ocr_capability)
        if model_type != AIModelType.embedding:
            conditions.append(AIModelConfig.deployment == deployment)
        result = await db.execute(select(AIModelConfig.id).where(*conditions).limit(1))
        return result.first() is not None

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
            # 本机行代表进程内引擎链（PaddleOCR / Tesseract / MinerU 或 OCR 容器），与路由同一判定。
            from app.services.unified_ocr_service import UnifiedOCRService

            status = await UnifiedOCRService().local_engine_status()
            if status["available"]:
                return True
            self.last_validation_error = ModelValidationFailure(
                "engine_unavailable", f"本机 OCR 引擎不可用：{status['reason']}", "unavailable"
            )
            logger.warning("Local OCR validation failed: %s", status["reason"])
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
        kind = getattr(exc, "kind", None)
        kind = kind if isinstance(kind, str) and kind else "config"
        if isinstance(code, str) and code:
            self.last_validation_error = ModelValidationFailure(code, str(exc), kind)
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
        """按本机优先路由完成对话（无启用模型时回落 `.env`）；``model`` 只作优先提示。"""
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
            route = await resolve_route(self.db, AIModelType.chat, requested_model=model)
            return await route_chat_sync(
                route,
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
            route = await resolve_route(self.db, AIModelType.chat, requested_model=model)
            async for chunk in route_chat_stream(
                route,
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

    async def health_check(self, *, public: bool = False) -> dict[str, Any]:
        """由路由状态派生健康结果（兼容既有字段，另附 ``routes``），不泄漏凭证。

        ``public=True``（未鉴权的 ``/api/ai/health``，大量页面挂载即调用）只探测对话、
        不返回端点地址；其余类只读缓存与实际调用记录。
        """
        from app.services.model_route_status import KINDS, collect_route_status

        status = await collect_route_status(
            self.db,
            probe_kinds=("chat",) if public else KINDS,
            include_endpoints=not public,
        )
        routes = {item["kind"]: item for item in status["routes"]}

        def _summary(kind: str) -> tuple[str, dict[str, Any] | None]:
            route = routes.get(kind) or {}
            effective = route.get("effective")
            candidates = route.get("candidates") or []
            if effective is not None:
                return "healthy", effective
            if any(item["status"] == "unknown" for item in candidates):
                return "unknown", candidates[0] if candidates else None
            return "unavailable", candidates[0] if candidates else None

        def _runtime_view(entry: dict[str, Any] | None, model_type: AIModelType):
            if entry is None:
                return None
            view = {
                "model_id": entry.get("model_id"),
                "model_name": entry.get("model_name"),
                "model_type": model_type.value,
                "provider": entry.get("provider"),
                "source": entry.get("source"),
                "reasoning_effort": entry.get("reasoning_effort"),
                "deployment": entry.get("deployment"),
            }
            if not public:
                view["endpoint_url"] = entry.get("endpoint")
            return view

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

        chat_status, chat_entry = _summary("chat")
        embedding_status, embedding_entry = _summary("embedding")
        ocr_status, _ = _summary("ocr")
        chroma_status = "unknown" if public else await _probe_chroma()
        chat_config = _runtime_view(chat_entry, AIModelType.chat)
        embedding_config = _runtime_view(embedding_entry, AIModelType.embedding)
        chat_provider = chat_config.get("provider") if chat_config else None
        return {
            "llm_status": chat_status,
            "embedding_status": embedding_status,
            # 兼容 UnifiedAIService 和既有前端字段。
            "vllm_status": chat_status if chat_provider != AIProvider.ollama.value else "unavailable",
            "ollama_status": chat_status if chat_provider == AIProvider.ollama.value else "unavailable",
            # V197 起表示「OCR 文字识别路由可用」（本机或服务器任一），不再只看本机 PaddleOCR。
            "paddleocr_status": ocr_status,
            "chromadb_status": chroma_status,
            "active_chat_model": chat_config.get("model_name") if chat_config else None,
            "active_embedding_model": embedding_config.get("model_name") if embedding_config else None,
            "chat_config": chat_config,
            "embedding_config": embedding_config,
            "routes": status["routes"],
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

        from app.services.llm_runtime import classify_model_deployment

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
                model.deployment = classify_model_deployment(model)
                if model.is_active and await AIService.route_slot_taken(
                    db, model_type=model.model_type, deployment=model.deployment,
                    ocr_capability=model.ocr_capability,
                ):
                    # 种子不得挤掉用户已启用的同位置模型（唯一约束同 V197）。
                    model.is_active = False
                db.add(model)

        await db.flush()
