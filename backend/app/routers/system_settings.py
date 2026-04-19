"""系统设置 API — 运行时配置查看与修改

GET  /api/settings          — 获取当前系统配置（脱敏）
PUT  /api/settings          — 更新可修改的配置项
GET  /api/settings/health   — 各服务连通性检查
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import settings
from app.deps import get_current_user, require_role
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["system-settings"])


# 可由前端修改的配置项白名单
_EDITABLE_KEYS = {
    "LLM_BASE_URL", "LLM_API_KEY", "DEFAULT_CHAT_MODEL", "DEFAULT_EMBEDDING_MODEL",
    "LLM_TEMPERATURE", "LLM_MAX_TOKENS", "LLM_ENABLE_THINKING",
    "OLLAMA_BASE_URL", "ONLYOFFICE_URL",
    "OCR_DEFAULT_ENGINE", "OCR_PADDLE_ENABLED", "OCR_TESSERACT_ENABLED",
    "PAPERLESS_URL", "PAPERLESS_TOKEN",
    "MAX_UPLOAD_SIZE_MB", "LOGIN_MAX_ATTEMPTS", "LOGIN_LOCK_MINUTES",
    "EVENT_DEBOUNCE_MS", "FORMULA_EXECUTE_TIMEOUT",
}

# 需要脱敏的字段（只显示前4位 + ***）
_SENSITIVE_KEYS = {"JWT_SECRET_KEY", "LLM_API_KEY", "PAPERLESS_TOKEN", "ENCRYPTION_KEY"}


def _mask(value: str) -> str:
    if not value or len(value) <= 4:
        return "***"
    return value[:4] + "***"


def _get_settings_dict() -> dict[str, Any]:
    """获取当前配置，敏感字段脱敏"""
    result = {}
    for key in sorted(settings.model_fields.keys()):
        val = getattr(settings, key, None)
        if key.upper() in _SENSITIVE_KEYS and isinstance(val, str):
            result[key] = _mask(val)
        else:
            result[key] = val
    return result


class SettingsUpdateRequest(BaseModel):
    """更新配置请求 — key-value 对"""
    updates: dict[str, Any]


@router.get("")
async def get_system_settings(
    current_user: User = Depends(get_current_user),
):
    """获取当前系统配置（敏感字段脱敏）"""
    config = _get_settings_dict()

    # 按分组组织
    groups = {
        "database": {k: config[k] for k in ["DATABASE_URL", "REDIS_URL"] if k in config},
        "security": {k: config[k] for k in [
            "JWT_SECRET_KEY", "JWT_ALGORITHM", "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
            "JWT_REFRESH_TOKEN_EXPIRE_DAYS", "LOGIN_MAX_ATTEMPTS", "LOGIN_LOCK_MINUTES",
            "ENCRYPTION_KEY",
        ] if k in config},
        "llm": {k: config[k] for k in [
            "LLM_BASE_URL", "LLM_API_KEY", "DEFAULT_CHAT_MODEL", "DEFAULT_EMBEDDING_MODEL",
            "LLM_TEMPERATURE", "LLM_MAX_TOKENS", "LLM_ENABLE_THINKING", "OLLAMA_BASE_URL",
        ] if k in config},
        "storage": {k: config[k] for k in [
            "STORAGE_ROOT", "ATTACHMENT_PRIMARY_STORAGE", "ATTACHMENT_FALLBACK_TO_LOCAL",
            "ATTACHMENT_LOCAL_STORAGE_ROOT", "MAX_UPLOAD_SIZE_MB",
        ] if k in config},
        "ocr": {k: config[k] for k in [
            "OCR_DEFAULT_ENGINE", "OCR_PADDLE_ENABLED", "OCR_TESSERACT_ENABLED",
            "OCR_TESSERACT_LANG", "OCR_CONFIDENCE_THRESHOLD",
        ] if k in config},
        "services": {k: config[k] for k in [
            "ONLYOFFICE_URL", "WOPI_BASE_URL", "PAPERLESS_URL", "PAPERLESS_TOKEN",
            "PAPERLESS_TIMEOUT", "MINERU_ENABLED", "MINERU_API_URL", "CHROMADB_URL",
        ] if k in config},
        "performance": {k: config[k] for k in [
            "EVENT_DEBOUNCE_MS", "FORMULA_EXECUTE_TIMEOUT",
        ] if k in config},
    }

    return {
        "groups": groups,
        "editable_keys": sorted(_EDITABLE_KEYS),
        "jwt_secure": settings.is_jwt_key_secure,
    }


@router.put("")
async def update_system_settings(
    req: SettingsUpdateRequest,
    current_user: User = Depends(require_role(["admin"])),
):
    """更新可修改的配置项（仅 admin）

    注意：运行时修改仅影响当前进程，重启后恢复 .env 值。
    持久化需手动修改 .env 文件。
    """
    updated = {}
    rejected = {}

    for key, value in req.updates.items():
        upper_key = key.upper()
        if upper_key not in _EDITABLE_KEYS:
            rejected[key] = "不允许修改此配置项"
            continue

        # 查找 settings 中对应的属性名（小写）
        attr_name = None
        for field_name in settings.model_fields:
            if field_name.upper() == upper_key:
                attr_name = field_name
                break

        if attr_name is None:
            rejected[key] = "配置项不存在"
            continue

        try:
            # 类型转换
            current_val = getattr(settings, attr_name)
            if isinstance(current_val, bool):
                value = str(value).lower() in ("true", "1", "yes")
            elif isinstance(current_val, int):
                value = int(value)
            elif isinstance(current_val, float):
                value = float(value)
            else:
                value = str(value)

            object.__setattr__(settings, attr_name, value)
            updated[key] = value
            logger.info("Config updated: %s = %s (by %s)", key, value, current_user.username)
        except Exception as e:
            rejected[key] = str(e)

    return {
        "updated": updated,
        "rejected": rejected,
        "message": f"已更新 {len(updated)} 项" + (f"，{len(rejected)} 项被拒绝" if rejected else ""),
    }


@router.get("/health")
async def check_services_health(
    current_user: User = Depends(get_current_user),
):
    """各外部服务连通性检查"""
    import asyncio
    import httpx

    results = {}

    async def check_url(name: str, url: str, path: str = ""):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url + path)
                results[name] = {"status": "ok", "code": r.status_code, "url": url}
        except Exception as e:
            results[name] = {"status": "error", "error": str(e)[:100], "url": url}

    tasks = [
        check_url("postgresql", f"http://localhost:5432", ""),  # TCP check below
        check_url("redis", f"http://localhost:6380", ""),
        check_url("vllm", settings.LLM_BASE_URL.replace("/v1", ""), "/health"),
        check_url("ollama", settings.OLLAMA_BASE_URL, "/api/tags"),
        check_url("onlyoffice", settings.ONLYOFFICE_URL, "/healthcheck"),
    ]

    if settings.PAPERLESS_URL:
        tasks.append(check_url("paperless", settings.PAPERLESS_URL, "/api/"))

    # PG 和 Redis 用数据库连接检查更准确
    try:
        from app.core.database import get_db
        from sqlalchemy import text
        async for db in get_db():
            await db.execute(text("SELECT 1"))
            results["postgresql"] = {"status": "ok", "url": "localhost:5432"}
            break
    except Exception as e:
        results["postgresql"] = {"status": "error", "error": str(e)[:100]}

    try:
        from app.core.redis import get_redis
        async for redis in get_redis():
            await redis.ping()
            results["redis"] = {"status": "ok", "url": "localhost:6380"}
            break
    except Exception as e:
        results["redis"] = {"status": "error", "error": str(e)[:100]}

    # 其他 HTTP 服务并发检查
    await asyncio.gather(*tasks[2:], return_exceptions=True)

    return {"services": results}
