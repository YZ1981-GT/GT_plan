"""致同企业 AI 模型预设单一真源（不包含任何 API Key）。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models.ai_models import AIModelType, AIProvider


@dataclass(frozen=True)
class AIModelPreset:
    preset_key: str
    id: UUID
    label: str
    model_name: str
    model_type: AIModelType
    provider: AIProvider
    endpoint_url: str
    context_window: int | None = None
    reasoning_effort: str | None = None
    # 该模型服务端实际接受的思考强度；None 表示不限制（非 DB 列，只用于校验与前端选项）。
    reasoning_effort_options: tuple[str, ...] | None = None
    # 「未指定」时服务端采用的默认强度（仅展示用）。
    reasoning_effort_server_default: str | None = None
    ocr_capability: str | None = None
    ocr_protocol: str | None = None
    api_path: str | None = None
    auth_scheme: str | None = None
    request_timeout_seconds: int | None = None
    performance_notes: str = ""

    def orm_values(self) -> dict[str, object]:
        return {
            "id": self.id,
            "preset_key": self.preset_key,
            "model_name": self.model_name,
            "model_type": self.model_type,
            "provider": self.provider,
            "endpoint_url": self.endpoint_url,
            "context_window": self.context_window,
            "reasoning_effort": self.reasoning_effort,
            "ocr_capability": self.ocr_capability,
            "ocr_protocol": self.ocr_protocol,
            "api_path": self.api_path,
            "auth_scheme": self.auth_scheme,
            "request_timeout_seconds": self.request_timeout_seconds,
            "performance_notes": self.performance_notes,
            "is_active": False,
        }


GT_QWEN38 = AIModelPreset(
    "gt_qwen38",
    UUID("71d00d01-a5b3-4ad7-9f2a-000000000001"),
    "致同企业 Qwen 3.8",
    "qwen3.8",
    AIModelType.chat,
    AIProvider.custom,
    "https://ai.gt-china.com.cn:10010/v1",
    context_window=262144,
    # 思考强度默认「未指定」（不发送 reasoning_effort），由用户在配置页选择（V195）。
    reasoning_effort=None,
    # 2026-10-19 实测网关：Supported types are xhigh (default), medium, and low；传 high 返回 400。
    reasoning_effort_options=("low", "medium", "xhigh"),
    reasoning_effort_server_default="xhigh",
    performance_notes="致同企业 OpenAI-compatible 预设；只需录入 API Key",
)

# Qwen 3.7 Max（2026-10-27 用户要求接入）：同一企业网关，OpenAI-compatible，
# 端点走 BUILTIN_TRUSTED_ENDPOINTS 精确放行（llm_endpoint_policy），只需录入 API Key。
# 网关实测思考强度档位与 qwen3.8 相同（low/medium/xhigh，默认 xhigh）。
GT_QWEN37_MAX = AIModelPreset(
    "gt_qwen37_max",
    UUID("71d00d01-a5b3-4ad7-9f2a-000000000004"),
    "致同企业 Qwen 3.7 Max",
    "qwen3.7-max",
    AIModelType.chat,
    AIProvider.custom,
    "https://ai.gt-china.com.cn:10010/v1",
    context_window=262144,
    reasoning_effort=None,
    reasoning_effort_options=("low", "medium", "xhigh"),
    reasoning_effort_server_default="xhigh",
    performance_notes="致同企业 OpenAI-compatible 预设；只需录入 API Key",
)

# 预设除 API Key 外唯一允许用户调整的参数；端点/模型名/鉴权等目的地字段保持锁定。
PRESET_USER_EDITABLE_FIELDS = frozenset({"api_key", "clear_api_key", "reasoning_effort"})
GT_PADDLEOCR_VL16 = AIModelPreset(
    "gt_paddleocrvl_16",
    UUID("71d00d01-a5b3-4ad7-9f2a-000000000002"),
    "致同企业 PaddleOCR-VL 1.6",
    "paddleocrvl-1.6",
    AIModelType.ocr,
    AIProvider.paddleocr,
    "https://ai.gt-china.com.cn:10080",
    ocr_capability="layout_parsing",
    ocr_protocol="paddlex_json",
    api_path="/layout-parsing",
    auth_scheme="bearer",
    request_timeout_seconds=120,
    performance_notes="致同企业版面解析预设；只需录入 API Key",
)
GT_PADDLEOCR_V6 = AIModelPreset(
    "gt_paddleocrv6",
    UUID("71d00d01-a5b3-4ad7-9f2a-000000000003"),
    "致同企业 PaddleOCR v6",
    "paddleocrv6",
    AIModelType.ocr,
    AIProvider.paddleocr,
    "https://ai.gt-china.com.cn:10080",
    ocr_capability="ocr",
    ocr_protocol="paddlex_json",
    api_path="/ocr",
    auth_scheme="bearer",
    request_timeout_seconds=60,
    performance_notes="致同企业文字识别预设；只需录入 API Key",
)

ENTERPRISE_MODEL_PRESETS = (GT_QWEN38, GT_QWEN37_MAX, GT_PADDLEOCR_VL16, GT_PADDLEOCR_V6)
BUILTIN_TRUSTED_ENDPOINTS = frozenset(p.endpoint_url for p in ENTERPRISE_MODEL_PRESETS)
PRESET_BY_KEY = {p.preset_key: p for p in ENTERPRISE_MODEL_PRESETS}
