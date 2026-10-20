"""模型路由状态：每类「本机 → 服务器」候选的可用性与当前生效（ADR-ROUTE-010）。

探测与生产走同一 transport、同一候选身份：探测成功会清除该候选的冷却记录、失败会写入冷却，
所以「检测状态」也是让路由立刻重新尝试本机的入口。结果按候选缓存（对话 / 向量 / 本机 OCR
30 秒、远程 OCR 60 秒），``refresh=True`` 强刷。只读：不改启用状态、不写库。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_model_options import AIDeployment
from app.models.ai_models import AIModelType
from app.services.llm_endpoint_policy import LLMEndpointPolicyError, describe_network_failure
from app.services.llm_route import candidate_mark, is_cooling, mark_available, mark_unavailable
from app.services.llm_runtime import (
    LLMRuntimeError,
    ResolvedLLMConfig,
    _probe_chat_completion,
    build_runtime_client,
    embedding,
    resolve_route,
)

KINDS: tuple[str, ...] = ("chat", "embedding", "ocr", "layout_parsing")
_LABELS = {
    "chat": "对话模型",
    "embedding": "向量模型",
    "ocr": "OCR 文字识别",
    "layout_parsing": "OCR 版面解析",
}
_POLICY = {"chat": "local_first", "embedding": "single", "ocr": "local_first", "layout_parsing": "local_first"}
_TTL_SHORT = 30.0
_TTL_REMOTE_OCR = 60.0


@dataclass(frozen=True)
class _Probe:
    ok: bool
    reason: str
    latency_ms: int
    checked_at: str
    monotonic: float


_CACHE: dict[str, _Probe] = {}
# 每个候选已完成的探测次数：判断「缓存是否在本次请求开始之后才产生」。不用时间比较 ——
# Windows 上 monotonic 精度约 15.6 ms，同一时钟刻内完成的旧探测会被误当成新的，强刷失效。
_GENERATION: dict[str, int] = {}
_LOCKS: dict[str, asyncio.Lock] = {}
_LOCK_LOOP: list[object] = [None]


def clear_route_status_cache() -> None:
    """测试与运维用：清空探测缓存。"""
    _CACHE.clear()
    _GENERATION.clear()


def _lock_for(identity: str) -> asyncio.Lock:
    # asyncio.Lock 绑定首次使用它的事件循环；循环变化（测试 / 重载）时整体重建。
    loop = asyncio.get_running_loop()
    if _LOCK_LOOP[0] is not loop:
        _LOCKS.clear()
        _LOCK_LOOP[0] = loop
    return _LOCKS.setdefault(identity, asyncio.Lock())


async def _cached_probe(
    identity: str,
    ttl: float,
    refresh: bool,
    probe: Callable[[], Awaitable[tuple[bool, str]]],
    seen: int,
) -> _Probe:
    """同一候选并发只探一次；``refresh`` 只在缓存早于本次请求时才重探。

    ``seen`` = 本次请求开始时该候选已完成的探测次数（请求入口统一取快照：请求先读库再探测，
    在探测这一步才取会把「请求开始之后、轮到自己之前」完成的探测误判为旧结果）。
    """
    async with _lock_for(identity):
        hit = _CACHE.get(identity)
        if hit is not None:
            fresh = time.monotonic() - hit.monotonic < ttl
            # 等锁期间别的请求刚探过（次数增加）⇒ 结果晚于本次请求，强刷也直接复用
            if (not refresh and fresh) or _GENERATION.get(identity, 0) > seen:
                return hit
        started = time.monotonic()
        try:
            ok, reason = await probe()
        except Exception as exc:  # noqa: BLE001 — 探测失败如实记成不可用，不让状态页 500
            ok, reason = False, f"检测出错（{type(exc).__name__}）"
        result = _Probe(
            ok, reason, int((time.monotonic() - started) * 1000),
            datetime.now(timezone.utc).isoformat(), time.monotonic(),
        )
        _CACHE[identity] = result
        _GENERATION[identity] = _GENERATION.get(identity, 0) + 1
        if ok:
            mark_available(identity)
        else:
            mark_unavailable(identity, reason)
        return result


async def _network_reason(endpoint: str, exc: BaseException) -> str:
    if isinstance(exc, LLMEndpointPolicyError):
        return f"端点不可用：{exc}"
    return await describe_network_failure(endpoint, exc)


async def _probe_chat(config: ResolvedLLMConfig) -> tuple[bool, str]:
    """`GET /models` 且模型名在列表内；服务不提供 /models 时改用最小对话探测。"""
    try:
        async with await build_runtime_client(config, timeout=8.0, connect_timeout=5.0) as client:
            response = await client.get("models")
    except (httpx.HTTPError, LLMEndpointPolicyError) as exc:
        return False, await _network_reason(config.endpoint_url, exc)
    if response.status_code in {401, 403}:
        return False, "鉴权失败，请检查 API Key"
    if response.status_code == 404:
        try:
            await _probe_chat_completion(config)
        except LLMRuntimeError as exc:
            return False, str(exc)
        return True, "可用"
    if response.status_code != 200:
        return False, f"服务返回 HTTP {response.status_code}"
    try:
        data = response.json()
    except ValueError:
        return False, "返回的不是 JSON（可能不是 OpenAI 兼容服务）"
    items = data.get("data") if isinstance(data, dict) else None
    ids = [str(item["id"]) for item in items or [] if isinstance(item, dict) and item.get("id")]
    if ids and config.model_name not in ids:
        return False, f"服务未提供模型「{config.model_name}」（现有：{'、'.join(ids[:5])}）"
    return True, "可用"


async def probe_chat_candidate(config: ResolvedLLMConfig) -> tuple[bool, str]:
    """执行前探测一个对话候选（DSH 这类中途不能换模型的调用方用）。

    与状态页共用探测缓存与冷却记录：30 秒内探过就直接用结果；失败写冷却，成功清冷却。
    """
    identity = config.identity
    probe = await _cached_probe(
        identity, _TTL_SHORT, False, lambda: _probe_chat(config), _GENERATION.get(identity, 0)
    )
    return probe.ok, probe.reason


async def _probe_embedding(config: ResolvedLLMConfig) -> tuple[bool, str]:
    """向量必须发真实 /embeddings：本机 8100 的 /models 返回 200 但不提供 /embeddings。"""
    try:
        await embedding(config, "ping", timeout=10.0)
    except LLMRuntimeError as exc:
        return False, str(exc)
    return True, "可用"


async def _probe_ocr_local() -> tuple[bool, str]:
    from app.services.unified_ocr_service import UnifiedOCRService

    status = await UnifiedOCRService().local_engine_status()
    return bool(status["available"]), str(status["reason"])


async def _probe_ocr_remote(config: Any) -> tuple[bool, str]:
    from app.services.remote_ocr_runtime import RemoteOCRRuntimeError, probe_remote_ocr

    try:
        await probe_remote_ocr(config)
    except RemoteOCRRuntimeError as exc:
        return False, str(exc)
    return True, "可用"


@dataclass
class _Slot:
    kind: str
    identity: str
    entry: dict[str, Any]
    ttl: float
    probe: Callable[[], Awaitable[tuple[bool, str]]] | None
    error: str | None = None


def _llm_slots(kind: str, route: list[Any]) -> list[_Slot]:
    probe_fn = _probe_chat if kind == "chat" else _probe_embedding
    slots: list[_Slot] = []
    for candidate in route:
        config = candidate.config
        entry = {
            "model_id": str(candidate.model_id) if candidate.model_id else None,
            "model_name": candidate.model_name,
            "deployment": candidate.deployment,
            "provider": config.provider.value if config else None,
            "endpoint": config.endpoint_url if config else None,
            "source": config.source if config else "database",
            "reasoning_effort": config.reasoning_effort if config else None,
            "implicit": candidate.implicit,
        }
        if config is None:
            reason = str(candidate.error) if candidate.error else "配置无效"
            slots.append(_Slot(kind, candidate.identity, entry, _TTL_SHORT, None, reason))
        else:
            slots.append(
                _Slot(kind, candidate.identity, entry, _TTL_SHORT, lambda c=config: probe_fn(c))
            )
    return slots


def _ocr_slots(kind: str, route: list[Any]) -> list[_Slot]:
    slots: list[_Slot] = []
    for candidate in route:
        config = candidate.config
        remote = config is not None and config.is_remote
        entry = {
            "model_id": str(candidate.model_id) if candidate.model_id else None,
            "model_name": candidate.model_name,
            "deployment": candidate.deployment,
            "provider": "paddleocr",
            "endpoint": f"{config.endpoint_url}{config.api_path or ''}" if remote else None,
            "source": "builtin" if candidate.implicit else "database",
            "reasoning_effort": None,
            "implicit": candidate.implicit,
        }
        if candidate.error is not None:
            slots.append(_Slot(kind, candidate.identity, entry, _TTL_SHORT, None, str(candidate.error)))
        elif remote:
            slots.append(
                _Slot(kind, candidate.identity, entry, _TTL_REMOTE_OCR, lambda c=config: _probe_ocr_remote(c))
            )
        else:
            slots.append(_Slot(kind, candidate.identity, entry, _TTL_SHORT, _probe_ocr_local))
    return slots


def _cooling_reason(identity: str) -> str:
    mark = candidate_mark(identity)
    return f"最近一次调用失败（冷却中）：{mark.reason if mark else ''}"


def _with_call_record(identity: str, ok: bool, reason: str) -> tuple[str, str]:
    """探测（含缓存）成功后又有实际调用失败 ⇒ 以更新的调用记录为准，与路由跳过它的事实一致。

    探测本身会写调用记录，所以「探测成功 + 冷却中」只可能是探测之后的实际调用失败。
    """
    if ok and is_cooling(identity):
        return "unavailable", _cooling_reason(identity)
    return ("available" if ok else "unavailable"), reason


def _passive_status(identity: str) -> tuple[str, str]:
    """未探测时用缓存或实际调用记录；都没有就是「未检测」。"""
    hit = _CACHE.get(identity)
    if hit is not None:
        return _with_call_record(identity, hit.ok, hit.reason)
    if is_cooling(identity):
        return "unavailable", _cooling_reason(identity)
    mark = candidate_mark(identity)
    if mark is not None and mark.ok:
        return "available", "最近一次调用成功"
    return "unknown", "未检测"


async def collect_route_status(
    db: AsyncSession,
    *,
    refresh: bool = False,
    probe_kinds: Iterable[str] = KINDS,
    include_endpoints: bool = True,
) -> dict[str, Any]:
    """汇总四类路由。``probe_kinds`` 之外的类只读缓存与冷却记录，不发请求。"""
    from app.services.remote_ocr_runtime import RemoteOCRRuntimeError, resolve_ocr_route

    probe_set = set(probe_kinds)
    seen = dict(_GENERATION)  # 请求开始时各候选的探测次数（见 _cached_probe）
    slots_by_kind: dict[str, list[_Slot]] = {}
    errors: dict[str, str] = {}
    # AsyncSession 不支持并发：先顺序读库，再并行探测。
    for kind, model_type in (("chat", AIModelType.chat), ("embedding", AIModelType.embedding)):
        try:
            slots_by_kind[kind] = _llm_slots(kind, await resolve_route(db, model_type))
        except LLMRuntimeError as exc:
            slots_by_kind[kind], errors[kind] = [], str(exc)
    for kind in ("ocr", "layout_parsing"):
        try:
            slots_by_kind[kind] = _ocr_slots(kind, await resolve_ocr_route(kind, db=db))
        except RemoteOCRRuntimeError as exc:
            slots_by_kind[kind], errors[kind] = [], str(exc)

    pending = [
        slot for kind in KINDS for slot in slots_by_kind[kind]
        if kind in probe_set and slot.probe is not None
    ]
    probes = await asyncio.gather(*(
        _cached_probe(slot.identity, slot.ttl, refresh, slot.probe, seen.get(slot.identity, 0))
        for slot in pending
    ))
    probed = {id(slot): result for slot, result in zip(pending, probes)}

    routes: list[dict[str, Any]] = []
    for kind in KINDS:
        candidates: list[dict[str, Any]] = []
        for slot in slots_by_kind[kind]:
            entry = dict(slot.entry)
            result = probed.get(id(slot))
            if slot.error is not None:
                status, reason, latency, checked = "unavailable", slot.error, None, None
            elif result is not None:
                status, reason = _with_call_record(slot.identity, result.ok, result.reason)
                latency, checked = result.latency_ms, result.checked_at
            else:
                status, reason = _passive_status(slot.identity)
                hit = _CACHE.get(slot.identity)
                latency, checked = (hit.latency_ms, hit.checked_at) if hit else (None, None)
            entry.update(status=status, reason=reason, latency_ms=latency, checked_at=checked)
            if not include_endpoints:
                entry.pop("endpoint", None)
            candidates.append(entry)
        effective = next((c for c in candidates if c["status"] == "available"), None)
        routes.append({
            "kind": kind,
            "label": _LABELS[kind],
            "policy": _POLICY[kind],
            "effective": effective,
            "candidates": candidates,
            "error": errors.get(kind),
            "has_local": any(c["deployment"] == AIDeployment.local.value for c in candidates),
            "has_server": any(c["deployment"] == AIDeployment.server.value for c in candidates),
        })
    return {"routes": routes, "checked_at": datetime.now(timezone.utc).isoformat()}
