"""公式设置业务错误（design §10 错误码）。路由层统一转成 HTTP 响应，文案中文。"""
from __future__ import annotations

from typing import Any


class FormulaSettingError(Exception):
    status_code = 400
    code = "FORMULA_SETTING_INVALID"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None,
                 detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.detail = detail or {}

    def to_detail(self) -> dict[str, Any]:
        return {"error_code": self.code, "message": self.message, **self.detail}


class VersionRequired(FormulaSettingError):
    status_code = 428
    code = "FORMULA_VERSION_REQUIRED"


class VersionConflict(FormulaSettingError):
    status_code = 409
    code = "FORMULA_VERSION_CONFLICT"


class SyncItemStale(FormulaSettingError):
    status_code = 409
    code = "FORMULA_SYNC_ITEM_STALE"


class DomainNotFound(FormulaSettingError):
    status_code = 404
    code = "FORMULA_SETTING_DOMAIN_UNKNOWN"


class Forbidden(FormulaSettingError):
    status_code = 403
    code = "FORMULA_SETTING_FORBIDDEN"


class NotFound(FormulaSettingError):
    status_code = 404
    code = "FORMULA_SETTING_NOT_FOUND"


class DomainNotApplicable(FormulaSettingError):
    status_code = 422
    code = "FORMULA_DOMAIN_NOT_APPLICABLE"
