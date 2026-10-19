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

from app.core.config import settings
from app.core.database import async_session
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.services.ai_model_secret_service import decrypt_api_key
from app.services.llm_endpoint_policy import (
    describe_network_failure,
    resolve_endpoint,
    validate_endpoint_structure,
)
from app.services.llm_provider_registry import provider_profile

_ALLOWED_CAPABILITIES = {"ocr", "layout_parsing"}
_ALLOWED_PROTOCOLS = {"local", "paddlex_json"}
_ALLOWED_AUTH = {"none", "bearer", "x_api_key", "api_key", "custom_header"}
_HEADER_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,126}$")
_FORBIDDEN_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "cookie"}


class RemoteOCRRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
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

    @property
    def is_remote(self) -> bool:
        return self.protocol == "paddlex_json"


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
    )
    _auth_headers(config)
    return config


async def get_active_ocr_config(capability: str) -> RemoteOCRConfig | None:
    """按 capability 读取 active OCR；local 或无记录返回 None。"""
    if capability not in _ALLOWED_CAPABILITIES:
        raise RemoteOCRRuntimeError("invalid_ocr_capability", "OCR 能力配置非法")
    async with async_session() as db:
        result = await db.execute(
            select(AIModelConfig).where(
                AIModelConfig.model_type == AIModelType.ocr,
                AIModelConfig.ocr_capability == capability,
                AIModelConfig.is_active.is_(True),
                AIModelConfig.is_deleted.is_(False),
            )
        )
        rows = list(result.scalars().all())
    if len(rows) > 1:
        raise RemoteOCRRuntimeError("multiple_active_ocr", "同一 OCR 能力存在多个激活模型")
    if not rows:
        return None
    config = resolve_ocr_config_from_model(rows[0])
    return config if config.is_remote else None


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
        raise RemoteOCRRuntimeError("ocr_file_too_large", "OCR 文件超过平台上传大小限制")
    safe = await resolve_endpoint(
        config.endpoint_url, provider_profile(AIProvider.paddleocr)
    )
    endpoint = safe.url
    payload = {
        "file": base64.b64encode(content).decode("ascii"),
        "fileType": _file_type(filename),
        "visualize": False,
    }
    try:
        async with httpx.AsyncClient(
            base_url=endpoint.rstrip("/") + "/",
            headers=_auth_headers(config),
            timeout=httpx.Timeout(config.timeout_seconds, connect=10.0),
            follow_redirects=False,
            mounts={},
            trust_env=False,
            transport=safe.transport(),
        ) as client:
            response = await client.post(config.api_path.lstrip("/"), json=payload)
    except httpx.TimeoutException as exc:
        detail = await describe_network_failure(endpoint, exc)
        raise RemoteOCRRuntimeError("ocr_timeout", f"远程 OCR 调用超时：{detail}") from exc
    except httpx.HTTPError as exc:
        detail = await describe_network_failure(endpoint, exc)
        raise RemoteOCRRuntimeError("ocr_unreachable", f"远程 OCR 服务不可达：{detail}") from exc
    if response.status_code in {401, 403}:
        raise RemoteOCRRuntimeError("ocr_auth_failed", "远程 OCR 认证失败，请检查 API Key")
    if response.status_code == 422:
        # PaddleX 对无法解码或过小的文件回 422 `Invalid input file`（2026-10-19 实测 1x1 PNG）。
        raise RemoteOCRRuntimeError("ocr_http_error", "远程 OCR 返回 HTTP 422（文件格式或尺寸不被接受）")
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


async def recognize_with_active_remote_ocr(
    file_path: str, *, capability: str = "ocr"
) -> dict | None:
    config = await get_active_ocr_config(capability)
    if config is None:
        return None
    return await recognize_remote_file(config, file_path)


# 连接测试图：240x64 黑白 PNG，内容 "GT OCR 2026"（459 字节，不含任何项目数据）。
# 原 1x1 PNG 会被 PaddleX 拒为 HTTP 422 `Invalid input file`（ADR-LLM-016）；
# 两条企业 OCR（/ocr、/layout-parsing）对本图均返回 200 并原样识别出文字。
_TEST_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAPAAAABAAQAAAAAM5MdKAAABkklEQVR42u2UsW4TQRBA365Pui2i3JUuEHc1VQqKFCFcwXcgl5QpU0TyJo2pkD8hyo9kjShS8A3oBBaCbm0o7qT1DsWeI0uxqCgovNVIb3a0b2a0Svjb0RzwAf873JteKVhYFnalLBvDDQu7KQFEnOpAIoVQeSrxKjKl8iMR0eAEINIJP8DjJXKP9xHIYOZnXU54/SZW75SUKB/O2sp/awGNjI8c0Lm3YXIGl3w39mOcXH4qAE2sNcCKorPPoYEMBY0x6eUNqYxRlACn9PyykA/eqk2SnuOtr4V58g4WgCXZDYDbZmzKfV17T7rw8Lt7ikU9hj4M+LreSSihB5iPvuwrPoE1IPVRkbq2e5QvYPkCYtMO3kx3uLHwAFsfTZaCZ4QP9GQOmQM/961Dh4ZYA18fcWpEpBMUtASXM//MRcK6FYCClbEe5Qev5KdRyzWAae6y2zuwrOGV1Lz0aZks004kkAfylcyk5Ypzcjcs0wSbBjrCpPFqzqHO0tPGOYByF7gTCIC6tjAeA+rwaR7w/4H/AJ6Aninm8oR1AAAAAElFTkSuQmCC"
)


async def test_remote_ocr_model(model: AIModelConfig) -> None:
    """使用无项目数据的内置 PNG 走生产同一 adapter。"""
    config = resolve_ocr_config_from_model(model)
    if not config.is_remote:
        raise RemoteOCRRuntimeError("ocr_not_remote", "本地 OCR 不使用远程连接测试")
    await recognize_remote_bytes(config, _TEST_PNG, filename="connection-test.png")
