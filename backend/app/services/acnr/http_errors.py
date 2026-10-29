"""ACNR 目录版本锁异常到稳定 HTTP 409 信封的映射。"""
from __future__ import annotations

from fastapi import Request
from starlette.responses import JSONResponse

from app.services.acnr import reasons
from app.services.acnr.project_registry_lock import RegistryLockError
from app.services.acnr.resolver import VersionInvalidError, VersionNotFoundError

_ERROR_CODES = {
    "snapshot_missing": "ACNR_REGISTRY_SNAPSHOT_MISSING",
    "snapshot_invalid": "ACNR_REGISTRY_SNAPSHOT_INVALID",
    "lock_failed": "ACNR_REGISTRY_LOCK_FAILED",
}


def _payload(error_code: str, message: str, version: str | None) -> dict[str, object]:
    body: dict[str, object] = {"code": 409, "error_code": error_code, "message": message}
    if version:
        body["version"] = version
    return body


async def registry_lock_error_handler(_request: Request, exc: RegistryLockError) -> JSONResponse:
    """锁前校验或落库失败。``exc.code`` 已由锁服务稳定分类。"""
    code = _ERROR_CODES.get(exc.code, "ACNR_REGISTRY_LOCK_FAILED")
    return JSONResponse(status_code=409, content=_payload(code, exc.message, exc.version))


async def version_not_found_error_handler(_request: Request, exc: VersionNotFoundError) -> JSONResponse:
    """已落库锁指向的快照文件不存在。"""
    message = reasons.REGISTRY_SNAPSHOT_MISSING.format(version=exc.version)
    return JSONResponse(
        status_code=409,
        content=_payload("ACNR_REGISTRY_SNAPSHOT_MISSING", message, exc.version),
    )


async def version_invalid_error_handler(_request: Request, exc: VersionInvalidError) -> JSONResponse:
    """已落库锁指向的快照存在，但内容不能作为目录加载。"""
    message = reasons.REGISTRY_SNAPSHOT_INVALID.format(version=exc.version, detail=exc.detail)
    return JSONResponse(
        status_code=409,
        content=_payload("ACNR_REGISTRY_SNAPSHOT_INVALID", message, exc.version),
    )


__all__ = [
    "registry_lock_error_handler",
    "version_invalid_error_handler",
    "version_not_found_error_handler",
]
