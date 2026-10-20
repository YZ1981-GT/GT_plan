"""DSH 模型桥：run 级选候选、转发令牌、请求改写（spec dsh-kb-ocr-local-first-routing ADR-DKR-001~003）。

DSH 子进程的模型服务 ``baseURL`` 指向平台环回转发端点（``routers/dsh_model_forward.py``），Key 位置放
本模块签发的 run 令牌；平台按令牌绑定的候选转发到上游。这样：

- 上游出站复用平台全部保护（端点策略、DNS 复核、fake-IP 兼容）—— Node 直连企业网关在本机代理下
  ``ECONNRESET``（2026-10-20 实测，域名被解析为 fake-IP）；
- 思考参数按候选重写（企业网关只收 low / medium / xhigh，vendor 适配器只会发 low / high / max）；
- 上游 Key 不进子进程环境、不写盘。

一次 run 只用一个候选：执行前探测，选中即写进令牌，运行中不换（ADR-DKR-002）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.core.database import async_session
from app.models.ai_models import AIModelConfig, AIModelType
from app.services.ai_chat.dsh_cordis_policy import validate_model_route
from app.services.ai_chat.engine import EngineFailure
from app.services.ai_chat.run_contract import ChatErrorCode
from app.services.llm_endpoint_policy import is_allowlisted_endpoint
from app.services.llm_route import cooling_notes, plan_attempts
from app.services.llm_runtime import (
    ResolvedLLMConfig,
    RouteCandidate,
    reasoning_fields,
    resolve_route,
)

logger = logging.getLogger("app.services.ai_chat.dsh_engine")

#: 平台环回转发端点前缀（routers/dsh_model_forward.py 用同一常量注册）
FORWARD_PATH = "/api/ai-chat/dsh-llm/v1"
#: DSH 子进程里承载 run 令牌的环境变量名（Cordis 模型服务的 ``apiKeyEnv``）
TOKEN_ENV = "GT_DSH_LLM_TOKEN"
#: 候选没有登记上下文窗口时的保守值（本机 vLLM 当前 max_model_len）
DEFAULT_CONTEXT_WINDOW = 32768
#: 单次输出上限的封顶值（Agent 单步回答 + 工具调用参数足够；vendor 默认 256000 会被 vLLM 拒收）
MAX_OUTPUT_TOKENS = 8192
#: 转发前丢弃的字段：模型名由平台强制，思考参数按候选重写
_DROPPED_FIELDS = frozenset({"model", "thinking", "reasoning_effort", "chat_template_kwargs", "extra_body"})


class DshTokenError(Exception):
    """转发令牌无效（签名不符 / 过期 / 结构错误）。"""


@dataclass(frozen=True)
class DshTokenClaims:
    run_id: UUID
    identity: str
    expires_at: float


@dataclass(frozen=True)
class DshModelRoute:
    """一次 run 选定的模型：配置、上下文窗口与选择过程中跳过的候选（含原因）。"""

    config: ResolvedLLMConfig
    context_window: int
    notes: tuple[str, ...] = ()

    @property
    def model_name(self) -> str:
        return self.config.model_name

    @property
    def deployment(self) -> str:
        return self.config.deployment

    @property
    def identity(self) -> str:
        return self.config.identity

    @property
    def max_output_tokens(self) -> int:
        return max(1024, min(MAX_OUTPUT_TOKENS, self.context_window // 4))


def forward_base_url() -> str:
    """DSH 子进程看到的模型端点：平台自身的环回转发地址（127.0.0.1：后端只监听 IPv4）。"""
    port = int(getattr(settings, "PORT", 9980) or 9980)
    return f"http://127.0.0.1:{port}{FORWARD_PATH}"


def validate_dsh_upstream(endpoint: str) -> list[str]:
    """DSH 可用的上游端点：平台受信清单（企业预设 + ``LLM_ENDPOINT_ALLOWLIST``）或环回 / 内网 IP 字面量。

    比 native 引擎更严：官方公网 API（如 api.deepseek.com）即使配置为服务器候选也不给 DSH 用
    （修订后的 dsh-agent-panel-integration Req 12.1~12.3）。
    """
    if endpoint and is_allowlisted_endpoint(endpoint):
        return []
    return validate_model_route(endpoint)


async def _context_windows(candidates: list[RouteCandidate]) -> dict[UUID, int]:
    ids = [c.model_id for c in candidates if c.model_id is not None]
    if not ids:
        return {}
    async with async_session() as db:
        windows: dict[UUID, int] = {}
        for model_id in ids:
            row = await db.get(AIModelConfig, model_id)
            if row is not None and row.context_window:
                windows[model_id] = int(row.context_window)
        return windows


async def select_run_candidate() -> DshModelRoute:
    """按平台对话路由（本机在前）探测，取第一个可用且端点允许的候选。

    - 路由里没有一个端点允许给 DSH 用 ⇒ ``local_only_violation``（不启动子进程）；
    - 允许的候选都不可用 ⇒ ``engine_unavailable``，原因逐个列出（含冷却跳过的）。
    探测与平台状态页、对话路由共用探测缓存与冷却记录。
    """
    from app.services.model_route_status import probe_chat_candidate

    async with async_session() as db:
        route = await resolve_route(db, AIModelType.chat)
    notes: list[str] = []
    eligible: list[RouteCandidate] = []
    for candidate in route:
        if candidate.config is not None and validate_dsh_upstream(candidate.config.endpoint_url):
            notes.append(f"{candidate.label}：端点不在 DSH 允许范围（只允许平台受信端点）")
            continue
        eligible.append(candidate)
    if not eligible:
        raise EngineFailure(
            ChatErrorCode.local_only_violation,
            "没有可用于 DSH 的对话模型：" + ("；".join(notes) or "未配置"),
        )
    planned = plan_attempts(eligible)
    notes.extend(cooling_notes(eligible, planned))
    windows = await _context_windows(planned)
    for candidate in planned:
        if candidate.config is None:
            notes.append(f"{candidate.label}：{candidate.error or '模型配置无效'}")
            continue
        ok, reason = await probe_chat_candidate(candidate.config)
        if not ok:
            notes.append(f"{candidate.label}：{reason}")
            continue
        if notes:
            logger.warning("DSH 模型兜底：%s；本次由 %s 执行", "；".join(notes), candidate.label)
        window = windows.get(candidate.model_id, DEFAULT_CONTEXT_WINDOW) if candidate.model_id else DEFAULT_CONTEXT_WINDOW
        return DshModelRoute(candidate.config, window, tuple(notes))
    raise EngineFailure(
        ChatErrorCode.engine_unavailable, "没有可用的对话模型：" + "；".join(notes)
    )


async def candidate_for(identity: str) -> ResolvedLLMConfig | None:
    """转发端按令牌里的候选身份重新解析路由；配置被停用 / 修改则找不到（返回 None）。"""
    async with async_session() as db:
        route = await resolve_route(db, AIModelType.chat)
    for candidate in route:
        if candidate.config is not None and candidate.identity == identity:
            return candidate.config
    return None


def rewrite_request(body: dict[str, Any], config: ResolvedLLMConfig) -> dict[str, Any]:
    """DSH 请求体 → 上游请求体：强制模型名，思考参数按候选重写，其余字段（消息 / 工具 / 流式）原样。"""
    payload = {key: value for key, value in body.items() if key not in _DROPPED_FIELDS}
    payload["model"] = config.model_name
    payload.update(reasoning_fields(config))
    return payload


# ---------------------------------------------------------------------------
# 转发令牌（HMAC 签名的 JSON；无状态，多 worker 任一进程都能校验）
# ---------------------------------------------------------------------------


def _signing_key() -> bytes:
    """派生自平台 JWT 密钥（加域分离前缀）：多 worker 进程一致，伪造令牌需要的密钥与伪造登录态相同。

    不能落回源码里的固定常量 —— 那样任何读过源码的本机进程都能签出令牌、借平台的上游 Key 调模型。
    """
    base = str(getattr(settings, "JWT_SECRET_KEY", "") or "")
    if not base:
        raise DshTokenError("平台未配置 JWT_SECRET_KEY，不能签发或校验 DSH 转发令牌")
    return hashlib.sha256(f"dsh-llm-forward:{base}".encode()).digest()


def _sign(data: str) -> str:
    return hmac.new(_signing_key(), data.encode(), hashlib.sha256).hexdigest()


def issue_token(run_id: UUID, identity: str, *, ttl_seconds: int) -> str:
    claims = {"e": int(time.time()) + max(1, int(ttl_seconds)), "i": identity, "r": str(run_id)}
    raw = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    data = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"{data}.{_sign(data)}"


def verify_token(token: str) -> DshTokenClaims:
    data, _, signature = (token or "").partition(".")
    if not data or not signature or not hmac.compare_digest(signature, _sign(data)):
        raise DshTokenError("签名无效")
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
        claims = json.loads(raw)
        parsed = DshTokenClaims(UUID(str(claims["r"])), str(claims["i"]), float(claims["e"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise DshTokenError("结构无效") from exc
    if parsed.expires_at < time.time():
        raise DshTokenError("已过期")
    return parsed


def token_ttl_seconds() -> int:
    """令牌有效期 = run 墙钟上限 + 1 分钟余量（run 结束后进程即被终止）。"""
    return int(getattr(settings, "AI_CHAT_RUN_TIMEOUT_SECONDS", 180)) + 60
