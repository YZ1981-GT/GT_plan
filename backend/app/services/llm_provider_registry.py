"""LLM provider 元数据单一真源。"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.ai_models import AIModelType, AIProvider


@dataclass(frozen=True)
class ProviderProfile:
    provider: AIProvider
    label: str
    default_endpoint: str
    requires_api_key: bool
    api_key_header: str | None
    supported_types: tuple[AIModelType, ...]
    description: str
    official_hosts: tuple[str, ...] = ()
    official_host_suffixes: tuple[str, ...] = ()
    expected_path_prefix: str = ""
    allow_public_custom_host: bool = False
    allow_loopback: bool = False

    def to_public_dict(self) -> dict[str, object]:
        return {
            "value": self.provider.value,
            "label": self.label,
            "default_endpoint": self.default_endpoint,
            "requires_api_key": self.requires_api_key,
            "supported_types": [item.value for item in self.supported_types],
            "description": self.description,
        }


_CHAT_EMBED = (AIModelType.chat, AIModelType.embedding)

PROVIDER_PROFILES: dict[AIProvider, ProviderProfile] = {
    AIProvider.openai_compatible: ProviderProfile(
        AIProvider.openai_compatible,
        "OpenAI 兼容（vLLM / OpenAI / LiteLLM）",
        "http://localhost:8100/v1",
        False,
        "Authorization",
        _CHAT_EMBED,
        "本地 vLLM 或任意经安全策略放行的 OpenAI 兼容 API",
        allow_public_custom_host=True,
        allow_loopback=True,
    ),
    AIProvider.deepseek: ProviderProfile(
        AIProvider.deepseek, "DeepSeek", "https://api.deepseek.com", True,
        "Authorization", _CHAT_EMBED, "DeepSeek 官方 OpenAI 兼容 API",
        official_hosts=("api.deepseek.com",),
    ),
    AIProvider.qwen: ProviderProfile(
        AIProvider.qwen, "通义千问（阿里云）", "", True,
        "Authorization", _CHAT_EMBED,
        "阿里云百炼 workspace 专属 OpenAI 兼容端点（需填写 WorkspaceId）",
        official_hosts=("dashscope.aliyuncs.com",),
        official_host_suffixes=(".maas.aliyuncs.com",),
        expected_path_prefix="/compatible-mode/v1",
    ),
    AIProvider.zhipu: ProviderProfile(
        AIProvider.zhipu, "智谱 AI（GLM）",
        "https://open.bigmodel.cn/api/paas/v4", True,
        "Authorization", _CHAT_EMBED, "智谱开放平台 OpenAI 兼容 API",
        official_hosts=("open.bigmodel.cn",), expected_path_prefix="/api/paas/v4",
    ),
    AIProvider.azure_openai: ProviderProfile(
        AIProvider.azure_openai, "Azure OpenAI（v1）", "", True,
        "api-key", _CHAT_EMBED, "仅支持 Azure /openai/v1 API",
        official_host_suffixes=(".openai.azure.com",),
        expected_path_prefix="/openai/v1",
    ),
    AIProvider.custom: ProviderProfile(
        AIProvider.custom, "自定义 OpenAI 兼容服务", "", False,
        "Authorization", _CHAT_EMBED, "公网 HTTPS 或服务端 allowlist 中的私有端点",
        allow_public_custom_host=True,
    ),
    AIProvider.ollama: ProviderProfile(
        AIProvider.ollama, "Ollama（本地 /v1）", "http://localhost:11434/v1", False,
        None, _CHAT_EMBED, "Ollama OpenAI-compatible /v1 接口",
        expected_path_prefix="/v1", allow_loopback=True,
    ),
    AIProvider.paddleocr: ProviderProfile(
        AIProvider.paddleocr, "PaddleOCR（本地 / PaddleX 远程）", "", False, None,
        (AIModelType.ocr,), "本地 PaddleOCR 或 PaddleX JSON OCR/版面解析服务",
        allow_public_custom_host=True,
    ),
}


def provider_profile(provider: AIProvider | str) -> ProviderProfile:
    """取得 provider 配置；未知值 fail-closed。"""
    try:
        key = provider if isinstance(provider, AIProvider) else AIProvider(provider)
        return PROVIDER_PROFILES[key]
    except (ValueError, KeyError) as exc:
        raise ValueError(f"未支持的 AI provider: {provider}") from exc


def public_provider_list() -> list[dict[str, object]]:
    """供管理前端使用的稳定投影，不含安全策略和 header 内部细节。"""
    return [profile.to_public_dict() for profile in PROVIDER_PROFILES.values()]
