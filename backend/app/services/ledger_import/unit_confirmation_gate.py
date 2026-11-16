"""账套导入提交的单位确认合同门。

该模块只负责解析已存在的 ``UnitConfirmationInput`` wire contract 和
判断直传文件是否具备可验证的预览令牌。它不创建 bundle、队列锁或导入作业，
因此缺合同时可以在所有写入动作之前 fail closed。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.ledger_unit_contract import UnitConfirmationInput

SOURCE_UNIT_CONFIRMATION_REQUIRED = "SOURCE_UNIT_CONFIRMATION_REQUIRED"
UNIT_CONFIRMATION_INVALID = "UNIT_CONFIRMATION_INVALID"


def parse_unit_confirmation(
    value: UnitConfirmationInput | Mapping[str, Any] | str | None,
) -> UnitConfirmationInput | None:
    """严格解析 multipart JSON 或 v2 已解析的单位确认合同。

    不接受空字符串、非对象或额外字段；摘要格式和确认值由
    ``UnitConfirmationInput`` 自己校验，避免调用方用字符串包含判断放行。
    """
    if value is None:
        return None
    if isinstance(value, UnitConfirmationInput):
        return value

    payload: Any = value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise _invalid("unit_confirmation 必须是合法 JSON 对象") from exc

    if not isinstance(payload, Mapping):
        raise _invalid("unit_confirmation 必须是 JSON 对象")

    try:
        return UnitConfirmationInput.model_validate(dict(payload))
    except ValidationError as exc:
        fields = [
            {"loc": list(error.get("loc", ())), "message": error.get("msg", "合同字段无效")}
            for error in exc.errors()
        ]
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": UNIT_CONFIRMATION_INVALID,
                "message": "金额单位确认合同无效，请重新预览并确认",
                "errors": fields,
            },
        ) from exc


def require_direct_file_confirmation(
    *,
    files: list[Any] | None = None,
    file: Any | None = None,
    upload_token: str | None = None,
    unit_confirmation: UnitConfirmationInput | Mapping[str, Any] | str | None = None,
) -> UnitConfirmationInput | None:
    """为兼容 multipart 提交建立直传文件合同门。

    只有不含直接文件的 bundle-only 请求保留旧兼容行为；一旦请求带文件，
    必须同时带预览产生的 ``upload_token`` 和经 schema 校验的确认合同。
    缺少合同在任何 bundle/job/四表写入前返回 428。
    """
    parsed = parse_unit_confirmation(unit_confirmation)
    has_direct_file = bool(files) or file is not None
    if has_direct_file and (not upload_token or parsed is None):
        raise HTTPException(
            status_code=428,
            detail={
                "error_code": SOURCE_UNIT_CONFIRMATION_REQUIRED,
                "message": "直接上传提交必须携带预览令牌和金额单位确认合同，请先预览并确认后重试",
                "next_step": "请先调用对应的 preview 接口，再使用返回的 upload_token 和 unit_confirmation 提交",
            },
        )
    return parsed


def confirmation_options(value: UnitConfirmationInput | None) -> dict[str, Any]:
    """把已验证合同转为可安全写入 ImportJob.options 的 JSON。"""
    if value is None:
        return {}
    return {"unit_confirmation": value.model_dump(mode="json")}


def _invalid(message: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"error_code": UNIT_CONFIRMATION_INVALID, "message": message},
    )
