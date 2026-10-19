"""``ai_model_config`` 运行选项的取值域与路由约束。

取值域（推理强度 / OCR 能力槽 / OCR 协议 / 认证方式 / 部署位置）在库里都是 VARCHAR，
不建 PG 枚举类型；取值与迁移里的 CHECK 约束逐值一致：

- ``reasoning_effort``：V193 ``ck_ai_model_reasoning_effort``，V196 增加 ``xhigh``
- ``ocr_capability`` / ``ocr_protocol`` / ``auth_scheme``：V193 同名 ``ck_ai_model_*``
- ``deployment``：V197 ``ck_ai_model_deployment``

枚举只在接口层做入参校验（``routers/ai_models.py``），ORM 列仍按字符串读写。
从 ``ai_models.py`` 抽出是为了不让 ORM 聚合文件继续膨胀（行数门禁基线 1537）。
"""

import enum
import ipaddress
from urllib.parse import urlsplit

from sqlalchemy import Index, text


class ReasoningEffort(str, enum.Enum):
    """OpenAI-compatible 推理强度；None 表示不发送该参数。

    xhigh：企业 qwen3.8 网关实测支持 low / medium / xhigh（默认 xhigh），不接受 high（V196）。
    """
    low = "low"
    medium = "medium"
    high = "high"
    xhigh = "xhigh"


class OCRCapability(str, enum.Enum):
    """远程 OCR 的独立能力槽。"""
    ocr = "ocr"
    layout_parsing = "layout_parsing"


class OCRProtocol(str, enum.Enum):
    """OCR transport adapter。"""
    local = "local"
    paddlex_json = "paddlex_json"


class AIAuthScheme(str, enum.Enum):
    """外部 OCR 服务认证头白名单。"""
    none = "none"
    bearer = "bearer"
    x_api_key = "x_api_key"
    api_key = "api_key"
    custom_header = "custom_header"


class AIDeployment(str, enum.Enum):
    """部署位置（V197）：路由按「本机 → 服务器」顺序选择已启用模型。"""
    local = "local"
    server = "server"


def endpoint_is_loopback(endpoint: str | None) -> bool:
    """端点主机字面量是否为本机环回（localhost / 127.0.0.0/8 / ::1）。

    只看字面量、不做 DNS 解析：企业网关在内网解析到私网地址也属于服务器。
    与 V197 回填用的正则同一口径（``localhost.localdomain`` 之类不算本机）。
    """
    host = (urlsplit(str(endpoint or "").strip()).hostname or "").lower()
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def classify_deployment(*, endpoint_url: str | None, ocr_protocol: str | None = None) -> str:
    """部署位置唯一判定：进程内 OCR 引擎或环回端点为本机，其余为服务器。

    ``endpoint_url`` 须是实际生效的端点（行内为空时传 provider 默认端点）。
    """
    if ocr_protocol == OCRProtocol.local.value:
        return AIDeployment.local.value
    if endpoint_is_loopback(endpoint_url):
        return AIDeployment.local.value
    return AIDeployment.server.value


def active_route_indexes() -> tuple[Index, ...]:
    """启用唯一约束（与 V197 逐条一致）。

    - chat：本机、服务器各最多一条启用；
    - embedding：只一条启用（向量必须同一模型，不跨模型兜底）；
    - ocr：每个能力槽本机、服务器各最多一条启用。
    """
    def _where(model_type: str) -> dict[str, object]:
        return {
            "postgresql_where": text(
                f"is_active = true AND is_deleted = false AND model_type = '{model_type}'"
            ),
            "sqlite_where": text(
                f"is_active = 1 AND is_deleted = 0 AND model_type = '{model_type}'"
            ),
        }

    return (
        Index(
            "uq_ai_model_config_active_chat_route", "model_type", "deployment",
            unique=True, **_where("chat"),
        ),
        Index(
            "uq_ai_model_config_active_embedding", "model_type",
            unique=True, **_where("embedding"),
        ),
        Index(
            "uq_ai_model_config_active_ocr_route", "ocr_capability", "deployment",
            unique=True, **_where("ocr"),
        ),
    )
