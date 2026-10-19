"""``ai_model_config`` 运行选项的取值域（推理强度 / OCR 能力槽 / OCR 协议 / 认证方式）。

这些列在库里是 VARCHAR，不建 PG 枚举类型；取值与迁移里的 CHECK 约束逐值一致：

- ``reasoning_effort``：V193 ``ck_ai_model_reasoning_effort``，V196 增加 ``xhigh``
- ``ocr_capability`` / ``ocr_protocol`` / ``auth_scheme``：V193 同名 ``ck_ai_model_*``

枚举只在接口层做入参校验（``routers/ai_models.py``），ORM 列仍按字符串读写。
从 ``ai_models.py`` 抽出是为了不让 ORM 聚合文件继续膨胀（行数门禁基线 1537）。
"""

import enum


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
