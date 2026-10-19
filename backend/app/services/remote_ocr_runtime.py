"""远程 PaddleX OCR runtime（/ocr 与 /layout-parsing）。"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.models.ai_model_options import AIDeployment
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.services.ai_model_secret_service import decrypt_api_key
from app.services.llm_endpoint_policy import (
    LLMEndpointPolicyError,
    describe_network_failure,
    resolve_endpoint,
    validate_endpoint_structure,
)
from app.services.llm_provider_registry import provider_profile
from app.services.llm_runtime import deployment_of

_ALLOWED_CAPABILITIES = {"ocr", "layout_parsing"}
_ALLOWED_PROTOCOLS = {"local", "paddlex_json"}
_ALLOWED_AUTH = {"none", "bearer", "x_api_key", "api_key", "custom_header"}
_HEADER_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,126}$")
_FORBIDDEN_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "cookie"}


class RemoteOCRRuntimeError(RuntimeError):
    """``kind`` 与 ``LLMRuntimeError`` 同一口径：unavailable 表示服务当前不可用（启用本机行时可带提示）。"""

    def __init__(self, code: str, message: str, *, kind: str = "config"):
        self.code = code
        self.kind = kind
        super().__init__(message)


@dataclass(frozen=True)
class RemoteOCRConfig:
    model_id: UUID
    model_name: str
    capability: str
    protocol: str
    endpoint_url: str | None
    api_path: str | None
    auth_scheme: str
    auth_header_name: str | None
    api_key: str | None
    timeout_seconds: int
    deployment: str = AIDeployment.server.value

    @property
    def is_remote(self) -> bool:
        return self.protocol == "paddlex_json"

    @property
    def identity(self) -> str:
        """冷却与状态缓存的候选身份（不含密钥）。"""
        return f"paddleocr|{self.endpoint_url}{self.api_path or ''}|{self.model_name}"


def _normalize_api_path(path: str | None, capability: str) -> str:
    expected = "/layout-parsing" if capability == "layout_parsing" else "/ocr"
    value = str(path or expected).strip()
    if value != expected:
        raise RemoteOCRRuntimeError(
            "invalid_api_path", f"{capability} 接口路径必须是 {expected}"
        )
    return value


def _auth_headers(config: RemoteOCRConfig) -> dict[str, str]:
    if config.auth_scheme == "none":
        return {}
    if not config.api_key:
        raise RemoteOCRRuntimeError("api_key_required", "远程 OCR 尚未配置 API Key")
    if config.auth_scheme == "bearer":
        return {"Authorization": f"Bearer {config.api_key}"}
    if config.auth_scheme == "x_api_key":
        return {"X-API-Key": config.api_key}
    if config.auth_scheme == "api_key":
        return {"api-key": config.api_key}
    name = str(config.auth_header_name or "").strip()
    if not _HEADER_NAME.fullmatch(name) or name.lower() in _FORBIDDEN_HEADERS:
        raise RemoteOCRRuntimeError("invalid_auth_header", "自定义认证 Header 名称非法")
    return {name: config.api_key}


def resolve_ocr_config_from_model(model: AIModelConfig) -> RemoteOCRConfig:
    if model.model_type != AIModelType.ocr or model.provider != AIProvider.paddleocr:
        raise RemoteOCRRuntimeError("unsupported_ocr_provider", "仅 PaddleOCR 配置可用于 OCR runtime")
    capability = str(model.ocr_capability or "")
    protocol = str(model.ocr_protocol or "")
    auth_scheme = str(model.auth_scheme or "none")
    if capability not in _ALLOWED_CAPABILITIES:
        raise RemoteOCRRuntimeError("invalid_ocr_capability", "OCR 能力配置非法")
    if protocol not in _ALLOWED_PROTOCOLS:
        raise RemoteOCRRuntimeError("invalid_ocr_protocol", "OCR 协议配置非法")
    if auth_scheme not in _ALLOWED_AUTH:
        raise RemoteOCRRuntimeError("invalid_auth_scheme", "OCR 认证方式非法")

    endpoint = None
    api_path = None
    key = None
    if protocol == "paddlex_json":
        try:
            endpoint = validate_endpoint_structure(
                model.endpoint_url or "", provider_profile(AIProvider.paddleocr)
            )
            key = decrypt_api_key(model.api_key_ciphertext)
        except ValueError as exc:
            raise RemoteOCRRuntimeError("invalid_ocr_config", str(exc)) from exc
        api_path = _normalize_api_path(model.api_path, capability)
    timeout = model.request_timeout_seconds or (120 if capability == "layout_parsing" else 60)
    config = RemoteOCRConfig(
        model_id=model.id,
        model_name=model.model_name,
        capability=capability,
        protocol=protocol,
        endpoint_url=endpoint,
        api_path=api_path,
        auth_scheme=auth_scheme,
        auth_header_name=model.auth_header_name,
        api_key=key,
        timeout_seconds=int(timeout),
        deployment=deployment_of(model),
    )
    _auth_headers(config)
    return config


@dataclass(frozen=True)
class OCRRouteCandidate:
    """OCR 路由候选（ADR-ROUTE-009）。

    ``config`` 为远程 PaddleX（环回端点也算本机）；为空且无 ``error`` 表示本机进程内引擎链
    （PaddleOCR / Tesseract / MinerU，或旧 ``OCR_SERVICE_URL`` 容器）。
    """

    capability: str
    deployment: str
    model_name: str
    model_id: UUID | None = None
    config: RemoteOCRConfig | None = None
    error: RemoteOCRRuntimeError | None = None
    implicit: bool = False  # 无启用行时的本机进程内引擎兜底

    @property
    def local_engine(self) -> bool:
        return self.error is None and (self.config is None or not self.config.is_remote)

    @property
    def identity(self) -> str:
        if self.config is not None and self.config.is_remote:
            return self.config.identity
        if self.local_engine:
            return f"ocr-local|{self.capability}"
        return f"ocr-invalid|{self.model_id}|{self.model_name}"

    @property
    def label(self) -> str:
        if self.local_engine:
            return "本机 OCR 引擎"
        where = "本机" if self.deployment == AIDeployment.local.value else "服务器"
        return f"{where} OCR「{self.model_name}」"


async def _enabled_ocr_rows(db: AsyncSession, capability: str) -> list[AIModelConfig]:
    result = await db.execute(
        select(AIModelConfig).where(
            AIModelConfig.model_type == AIModelType.ocr,
            AIModelConfig.ocr_capability == capability,
            AIModelConfig.is_active.is_(True),
            AIModelConfig.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


async def resolve_ocr_route(
    capability: str, *, db: AsyncSession | None = None
) -> list[OCRRouteCandidate]:
    """按「本机 → 服务器」排序的已启用 OCR 候选。

    无启用行：文字识别回落本机进程内引擎（与旧行为一致），版面解析返回空（没有本机实现）。
    """
    if capability not in _ALLOWED_CAPABILITIES:
        raise RemoteOCRRuntimeError("invalid_ocr_capability", "OCR 能力配置非法")
    if db is not None:
        rows = await _enabled_ocr_rows(db, capability)
    else:
        async with async_session() as session:
            rows = await _enabled_ocr_rows(session, capability)
    deployments = [deployment_of(row) for row in rows]
    if len(deployments) != len(set(deployments)):
        raise RemoteOCRRuntimeError(
            "multiple_active_ocr", "同一 OCR 能力的同一部署位置存在多个启用模型"
        )
    if not rows:
        if capability == "ocr":
            return [OCRRouteCandidate(capability, AIDeployment.local.value, "本机 OCR 引擎", implicit=True)]
        return []
    candidates: list[OCRRouteCandidate] = []
    for row in rows:
        try:
            config = resolve_ocr_config_from_model(row)
        except RemoteOCRRuntimeError as exc:
            candidates.append(
                OCRRouteCandidate(capability, deployment_of(row), row.model_name, row.id, None, exc)
            )
        else:
            candidates.append(
                OCRRouteCandidate(capability, config.deployment, row.model_name, row.id, config)
            )
    return sorted(candidates, key=lambda c: 0 if c.deployment == AIDeployment.local.value else 1)


def _file_type(filename: str) -> int:
    return 0 if Path(filename).suffix.lower() == ".pdf" else 1


def _object(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _decode_ocr_result(result: dict) -> dict:
    text_lines: list[str] = []
    regions: list[dict] = []
    for page in result.get("ocrResults", []):
        page_obj = _object(page)
        pruned = _object(page_obj.get("prunedResult")) or page_obj
        texts = pruned.get("rec_texts") or []
        scores = pruned.get("rec_scores") or []
        boxes = pruned.get("rec_polys") or pruned.get("rec_boxes") or []
        for index, text in enumerate(texts):
            value = str(text or "").strip()
            if not value:
                continue
            text_lines.append(value)
            regions.append({
                "text": value,
                "box": boxes[index] if index < len(boxes) else [],
                "confidence": scores[index] if index < len(scores) else None,
            })
    return {"text": "\n".join(text_lines), "regions": regions, "layout_blocks": []}


def _decode_layout_result(result: dict) -> dict:
    text_lines: list[str] = []
    regions: list[dict] = []
    blocks: list[dict] = []
    pages = result.get("layoutParsingResults") or result.get("layoutResults") or []
    if not pages and result.get("parsing_res_list"):
        pages = [result]
    for page in pages:
        page_obj = _object(page)
        pruned = _object(page_obj.get("prunedResult")) or page_obj
        page_index = pruned.get("page_index", page_obj.get("page_index"))
        for block in pruned.get("parsing_res_list", []):
            item = _object(block)
            content = str(item.get("block_content") or "").strip()
            normalized = {
                "page_index": page_index,
                "label": item.get("block_label"),
                "text": content,
                "box": item.get("block_bbox") or [],
                "order": item.get("block_order"),
            }
            blocks.append(normalized)
            if content:
                text_lines.append(content)
                regions.append({
                    "text": content,
                    "box": normalized["box"],
                    "confidence": None,
                    "label": normalized["label"],
                })
    return {"text": "\n".join(text_lines), "regions": regions, "layout_blocks": blocks}


def decode_paddlex_response(data: object, capability: str) -> dict:
    body = _object(data)
    if not body or body.get("errorCode") not in {0, "0"}:
        raise RemoteOCRRuntimeError("ocr_upstream_error", "远程 OCR 返回业务错误")
    result = body.get("result")
    if not isinstance(result, dict):
        raise RemoteOCRRuntimeError("ocr_schema_error", "远程 OCR 响应缺少 result")
    normalized = (
        _decode_layout_result(result)
        if capability == "layout_parsing"
        else _decode_ocr_result(result)
    )
    normalized.update({
        "engine": "paddleocr_remote",
        "capability": capability,
    })
    return normalized


async def recognize_remote_bytes(
    config: RemoteOCRConfig,
    content: bytes,
    *,
    filename: str,
) -> dict:
    if not config.is_remote or not config.endpoint_url or not config.api_path:
        raise RemoteOCRRuntimeError("ocr_not_remote", "OCR 配置不是远程 PaddleX 服务")
    max_bytes = int(settings.MAX_UPLOAD_SIZE_MB) * 1024 * 1024
    if len(content) > max_bytes:
        raise RemoteOCRRuntimeError(
            "ocr_file_too_large", "OCR 文件超过平台上传大小限制", kind="request"
        )
    try:
        safe = await resolve_endpoint(
            config.endpoint_url, provider_profile(AIProvider.paddleocr)
        )
    except LLMEndpointPolicyError as exc:
        raise RemoteOCRRuntimeError(
            "ocr_endpoint_blocked", f"远程 OCR 端点不可用：{exc}", kind="unavailable"
        ) from exc
    endpoint = safe.url
    connect_timeout = 10.0
    if config.deployment == AIDeployment.local.value:
        connect_timeout = min(connect_timeout, float(settings.LLM_LOCAL_CONNECT_TIMEOUT_SECONDS))
    payload = {
        "file": base64.b64encode(content).decode("ascii"),
        "fileType": _file_type(filename),
        "visualize": False,
    }
    try:
        async with httpx.AsyncClient(
            base_url=endpoint.rstrip("/") + "/",
            headers=_auth_headers(config),
            timeout=httpx.Timeout(config.timeout_seconds, connect=connect_timeout),
            follow_redirects=False,
            mounts={},
            trust_env=False,
            transport=safe.transport(),
        ) as client:
            response = await client.post(config.api_path.lstrip("/"), json=payload)
    except httpx.TimeoutException as exc:
        detail = await describe_network_failure(endpoint, exc)
        raise RemoteOCRRuntimeError(
            "ocr_timeout", f"远程 OCR 调用超时：{detail}", kind="unavailable"
        ) from exc
    except httpx.HTTPError as exc:
        detail = await describe_network_failure(endpoint, exc)
        raise RemoteOCRRuntimeError(
            "ocr_unreachable", f"远程 OCR 服务不可达：{detail}", kind="unavailable"
        ) from exc
    if response.status_code in {401, 403}:
        raise RemoteOCRRuntimeError("ocr_auth_failed", "远程 OCR 认证失败，请检查 API Key")
    if response.status_code == 422:
        # PaddleX 对无法解码或过小的文件回 422 `Invalid input file`（2026-10-19 实测 1x1 PNG）。
        raise RemoteOCRRuntimeError("ocr_http_error", "远程 OCR 返回 HTTP 422（文件格式或尺寸不被接受）")
    if response.status_code >= 500:
        raise RemoteOCRRuntimeError(
            "ocr_http_error", f"远程 OCR 返回 HTTP {response.status_code}", kind="unavailable"
        )
    if response.status_code >= 400:
        raise RemoteOCRRuntimeError("ocr_http_error", f"远程 OCR 返回 HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise RemoteOCRRuntimeError("ocr_schema_error", "远程 OCR 未返回 JSON") from exc
    return decode_paddlex_response(data, config.capability)


async def recognize_remote_file(config: RemoteOCRConfig, file_path: str) -> dict:
    path = Path(file_path)
    content = await asyncio.to_thread(path.read_bytes)
    return await recognize_remote_bytes(config, content, filename=path.name)


# 连接测试图：240x64 黑白 PNG，内容 "GT OCR 2026"（459 字节，不含任何项目数据）。
# 原 1x1 PNG 会被 PaddleX 拒为 HTTP 422 `Invalid input file`（ADR-LLM-016）；
# 两条企业 OCR（/ocr、/layout-parsing）对本图均返回 200 并原样识别出文字。
_TEST_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAPAAAABAAQAAAAAM5MdKAAABkklEQVR42u2UsW4TQRBA365Pui2i3JUuEHc1VQqKFCFcwXcgl5QpU0TyJo2pkD8hyo9kjShS8A3oBBaCbm0o7qT1DsWeI0uxqCgovNVIb3a0b2a0Svjb0RzwAf873JteKVhYFnalLBvDDQu7KQFEnOpAIoVQeSrxKjKl8iMR0eAEINIJP8DjJXKP9xHIYOZnXU54/SZW75SUKB/O2sp/awGNjI8c0Lm3YXIGl3w39mOcXH4qAE2sNcCKorPPoYEMBY0x6eUNqYxRlACn9PyykA/eqk2SnuOtr4V58g4WgCXZDYDbZmzKfV17T7rw8Lt7ikU9hj4M+LreSSihB5iPvuwrPoE1IPVRkbq2e5QvYPkCYtMO3kx3uLHwAFsfTZaCZ4QP9GQOmQM/961Dh4ZYA18fcWpEpBMUtASXM//MRcK6FYCClbEe5Qev5KdRyzWAae6y2zuwrOGV1Lz0aZks004kkAfylcyk5Ypzcjcs0wSbBjrCpPFqzqHO0tPGOYByF7gTCIC6tjAeA+rwaR7w/4H/AJ6Aninm8oR1AAAAAElFTkSuQmCC"
)


async def probe_remote_ocr(config: RemoteOCRConfig) -> None:
    """用内置测试图走生产同一 adapter（连接测试与路由状态共用）。"""
    if not config.is_remote:
        raise RemoteOCRRuntimeError("ocr_not_remote", "本地 OCR 不使用远程连接测试")
    await recognize_remote_bytes(config, _TEST_PNG, filename="connection-test.png")


async def test_remote_ocr_model(model: AIModelConfig) -> None:
    """使用无项目数据的内置 PNG 走生产同一 adapter。"""
    await probe_remote_ocr(resolve_ocr_config_from_model(model))
