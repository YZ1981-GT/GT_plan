"""D 循环 adapter 接线（d1~d7）— Task 2.2

逐 api_prefix 映射到既有单表 I/E 底层函数（复用，不重写列格式）。
每个 adapter 将 bulk 层的统一签名 (db, wp_id, sheet_code, mode/strategy)
转换为对应 _{cycle}_import_export.py 端点函数的调用。

核心铁律：
  - 不新造 xlsx 列格式，100% 复用现有端点
  - service 只 flush 不 commit
  - 行数超限 → partial + row_limit_exceeded 告警

Requirements: 1.3, 2.1
"""
from __future__ import annotations

import io
import logging
from typing import Any, Literal

from starlette.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.bulk_tab.single_tab_adapter import (
    AdapterSpec,
    TabImportResult,
    make_import_result_from_legacy,
    register_adapter,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _read_streaming_response(resp: StreamingResponse) -> bytes:
    """从 StreamingResponse 提取 body bytes（内存中 BytesIO）。"""
    chunks: list[bytes] = []
    async for chunk in resp.body_iterator:  # type: ignore[union-attr]
        if isinstance(chunk, str):
            chunks.append(chunk.encode("utf-8"))
        else:
            chunks.append(chunk)
    return b"".join(chunks)


def _make_upload_file(xlsx_bytes: bytes, sheet_code: str):
    """构造一个 starlette UploadFile 实例，供端点函数直调。"""
    from starlette.datastructures import UploadFile

    return UploadFile(
        filename=f"{sheet_code}.xlsx",
        file=io.BytesIO(xlsx_bytes),
    )


class _DummyUser:
    """用于绕过端点函数中的 current_user 参数（bulk 层已在路由级做权限校验）。"""

    id = "bulk-import-export"
    username = "bulk-system"
    role = "admin"


_DUMMY_USER = _DummyUser()


# ---------------------------------------------------------------------------
# D1 adapter
# ---------------------------------------------------------------------------


async def _d1_export(
    db: AsyncSession, wp_id: str, sheet_code: str, mode: Literal["template", "data"]
) -> bytes:
    from app.routers.wp_render_strategies._d1_import_export import (
        d1_export_template,
        d1_export_data,
    )

    if mode == "template":
        resp = await d1_export_template(
            wp_id=wp_id, sheet=sheet_code, include_guidance=False, db=db, current_user=_DUMMY_USER
        )
    else:
        resp = await d1_export_data(wp_id=wp_id, sheet=sheet_code, db=db, current_user=_DUMMY_USER)
    return await _read_streaming_response(resp)


async def _d1_import(
    db: AsyncSession, wp_id: str, sheet_code: str, xlsx_bytes: bytes, strategy: str
) -> TabImportResult:
    from app.routers.wp_render_strategies._d1_import_export import d1_import_data

    file = _make_upload_file(xlsx_bytes, sheet_code)
    try:
        result = await d1_import_data(
            wp_id=wp_id, sheet=sheet_code, file=file, db=db, current_user=_DUMMY_USER
        )
    except Exception as e:
        logger.warning("d1 import_data failed for sheet=%s: %s", sheet_code, e)
        return TabImportResult(status="failed", errors=[str(e)])

    if isinstance(result, dict):
        return _convert_import_response(result)
    return TabImportResult(status="success")


# ---------------------------------------------------------------------------
# D2 adapter
# ---------------------------------------------------------------------------


async def _d2_export(
    db: AsyncSession, wp_id: str, sheet_code: str, mode: Literal["template", "data"]
) -> bytes:
    from app.routers.wp_render_strategies._d2_import_export import (
        export_template,
        export_data,
    )

    if mode == "template":
        resp = await export_template(wp_id=wp_id, sheet=sheet_code, db=db)
    else:
        resp = await export_data(
            wp_id=wp_id, sheet=sheet_code, db=db, current_user=_DUMMY_USER
        )
    return await _read_streaming_response(resp)


async def _d2_import(
    db: AsyncSession, wp_id: str, sheet_code: str, xlsx_bytes: bytes, strategy: str
) -> TabImportResult:
    from app.routers.wp_render_strategies._d2_import_export import import_data

    file = _make_upload_file(xlsx_bytes, sheet_code)
    try:
        result = await import_data(
            wp_id=wp_id, sheet=sheet_code, file=file, db=db, current_user=_DUMMY_USER
        )
    except Exception as e:
        logger.warning("d2 import_data failed for sheet=%s: %s", sheet_code, e)
        return TabImportResult(status="failed", errors=[str(e)])

    if isinstance(result, dict):
        return _convert_import_response(result)
    return TabImportResult(status="success")


# ---------------------------------------------------------------------------
# D3 adapter
# ---------------------------------------------------------------------------


async def _d3_export(
    db: AsyncSession, wp_id: str, sheet_code: str, mode: Literal["template", "data"]
) -> bytes:
    from app.routers.wp_render_strategies._d3_import_export import (
        d3_export_template,
        d3_export_data,
    )

    if mode == "template":
        resp = await d3_export_template(
            wp_id=wp_id, sheet=sheet_code, db=db, current_user=_DUMMY_USER
        )
    else:
        resp = await d3_export_data(
            wp_id=wp_id, sheet=sheet_code, db=db, current_user=_DUMMY_USER
        )
    return await _read_streaming_response(resp)


async def _d3_import(
    db: AsyncSession, wp_id: str, sheet_code: str, xlsx_bytes: bytes, strategy: str
) -> TabImportResult:
    from app.routers.wp_render_strategies._d3_import_export import d3_import_data

    file = _make_upload_file(xlsx_bytes, sheet_code)
    try:
        result = await d3_import_data(
            wp_id=wp_id, sheet=sheet_code, file=file, db=db, current_user=_DUMMY_USER
        )
    except Exception as e:
        logger.warning("d3 import_data failed for sheet=%s: %s", sheet_code, e)
        return TabImportResult(status="failed", errors=[str(e)])

    if isinstance(result, dict):
        return _convert_import_response(result)
    return TabImportResult(status="success")


# ---------------------------------------------------------------------------
# D4 adapter
# ---------------------------------------------------------------------------


async def _d4_export(
    db: AsyncSession, wp_id: str, sheet_code: str, mode: Literal["template", "data"]
) -> bytes:
    from app.routers.wp_render_strategies._d4_import_export import (
        d4_export_template,
        d4_export_data,
    )

    if mode == "template":
        resp = await d4_export_template(
            wp_id=wp_id, sheet=sheet_code, include_guidance=False, db=db,
            current_user=_DUMMY_USER
        )
    else:
        resp = await d4_export_data(
            wp_id=wp_id, sheet=sheet_code, db=db, current_user=_DUMMY_USER
        )
    return await _read_streaming_response(resp)


async def _d4_import(
    db: AsyncSession, wp_id: str, sheet_code: str, xlsx_bytes: bytes, strategy: str
) -> TabImportResult:
    from app.routers.wp_render_strategies._d4_import_export import d4_import_data

    file = _make_upload_file(xlsx_bytes, sheet_code)
    try:
        result = await d4_import_data(
            wp_id=wp_id, sheet=sheet_code, file=file, db=db, current_user=_DUMMY_USER
        )
    except Exception as e:
        logger.warning("d4 import_data failed for sheet=%s: %s", sheet_code, e)
        return TabImportResult(status="failed", errors=[str(e)])

    if isinstance(result, dict):
        return _convert_import_response(result)
    return TabImportResult(status="success")


# ---------------------------------------------------------------------------
# D5 adapter
# ---------------------------------------------------------------------------


async def _d5_export(
    db: AsyncSession, wp_id: str, sheet_code: str, mode: Literal["template", "data"]
) -> bytes:
    from app.routers.wp_render_strategies._d5_import_export import (
        d5_export_template,
        d5_export_data,
    )

    if mode == "template":
        # D5 export_template 不需要 db 参数
        resp = await d5_export_template(
            wp_id=wp_id, sheet=sheet_code, include_guidance=False,
            current_user=_DUMMY_USER,
        )
    else:
        resp = await d5_export_data(
            wp_id=wp_id, sheet=sheet_code, db=db, current_user=_DUMMY_USER
        )
    return await _read_streaming_response(resp)


async def _d5_import(
    db: AsyncSession, wp_id: str, sheet_code: str, xlsx_bytes: bytes, strategy: str
) -> TabImportResult:
    from app.routers.wp_render_strategies._d5_import_export import d5_import_data

    file = _make_upload_file(xlsx_bytes, sheet_code)
    try:
        result = await d5_import_data(
            wp_id=wp_id, sheet=sheet_code, file=file, db=db, current_user=_DUMMY_USER
        )
    except Exception as e:
        logger.warning("d5 import_data failed for sheet=%s: %s", sheet_code, e)
        return TabImportResult(status="failed", errors=[str(e)])

    if isinstance(result, dict):
        return _convert_import_response(result)
    return TabImportResult(status="success")


# ---------------------------------------------------------------------------
# D6 adapter
# ---------------------------------------------------------------------------


async def _d6_export(
    db: AsyncSession, wp_id: str, sheet_code: str, mode: Literal["template", "data"]
) -> bytes:
    from app.routers.wp_render_strategies._d6_import_export import (
        d6_export_template,
        d6_export_data,
    )

    if mode == "template":
        # D6 export_template 不需要 db 参数
        resp = await d6_export_template(
            wp_id=wp_id, sheet=sheet_code, include_guidance=False,
            current_user=_DUMMY_USER,
        )
    else:
        resp = await d6_export_data(
            wp_id=wp_id, sheet=sheet_code, db=db, current_user=_DUMMY_USER
        )
    return await _read_streaming_response(resp)


async def _d6_import(
    db: AsyncSession, wp_id: str, sheet_code: str, xlsx_bytes: bytes, strategy: str
) -> TabImportResult:
    from app.routers.wp_render_strategies._d6_import_export import d6_import_data

    file = _make_upload_file(xlsx_bytes, sheet_code)
    try:
        result = await d6_import_data(
            wp_id=wp_id, sheet=sheet_code, file=file, db=db, current_user=_DUMMY_USER
        )
    except Exception as e:
        logger.warning("d6 import_data failed for sheet=%s: %s", sheet_code, e)
        return TabImportResult(status="failed", errors=[str(e)])

    if isinstance(result, dict):
        return _convert_import_response(result)
    return TabImportResult(status="success")


# ---------------------------------------------------------------------------
# D7 adapter
# ---------------------------------------------------------------------------


async def _d7_export(
    db: AsyncSession, wp_id: str, sheet_code: str, mode: Literal["template", "data"]
) -> bytes:
    from app.routers.wp_render_strategies._d7_import_export import (
        d7_export_template,
        d7_export_data,
    )

    if mode == "template":
        # D7 export_template 不需要 db 参数
        resp = await d7_export_template(
            wp_id=wp_id, sheet=sheet_code, include_guidance=False,
            current_user=_DUMMY_USER,
        )
    else:
        resp = await d7_export_data(
            wp_id=wp_id, sheet=sheet_code, db=db, current_user=_DUMMY_USER
        )
    return await _read_streaming_response(resp)


async def _d7_import(
    db: AsyncSession, wp_id: str, sheet_code: str, xlsx_bytes: bytes, strategy: str
) -> TabImportResult:
    from app.routers.wp_render_strategies._d7_import_export import d7_import_data

    file = _make_upload_file(xlsx_bytes, sheet_code)
    try:
        result = await d7_import_data(
            wp_id=wp_id, sheet=sheet_code, file=file, db=db, current_user=_DUMMY_USER
        )
    except Exception as e:
        logger.warning("d7 import_data failed for sheet=%s: %s", sheet_code, e)
        return TabImportResult(status="failed", errors=[str(e)])

    if isinstance(result, dict):
        return _convert_import_response(result)
    return TabImportResult(status="success")


# ---------------------------------------------------------------------------
# Import response conversion helper
# ---------------------------------------------------------------------------


def _convert_import_response(result: dict[str, Any]) -> TabImportResult:
    """将现有端点的响应 dict 转为 TabImportResult。

    现有端点返回格式多样：
      - {"data": {"rowCount": N, "fieldCount": M, ...}}
      - {"ok": True/False, "imported_count": N, "errors": [...]}
      - {"code": 400, "message": "列名不匹配", ...}
    """
    # 检测错误码响应
    code = result.get("code")
    if code and code >= 400:
        msg = result.get("message", "import failed")
        return TabImportResult(status="failed", errors=[msg])

    # 检测 "data" 封装格式（最常见）
    data = result.get("data")
    if isinstance(data, dict):
        row_count = data.get("rowCount", 0)
        warning = data.get("warning", "")
        warnings_list: list[str] = []
        if warning:
            warnings_list.append(warning)
        # skipped columns
        skipped = data.get("skippedColumns") or data.get("skipped_columns") or []
        if skipped:
            warnings_list.append(f"跳过的列: {', '.join(skipped)}")

        if row_count == 0 and warning:
            return TabImportResult(status="failed", warnings=warnings_list, errors=[warning])

        if row_count > 0 and warnings_list:
            return TabImportResult(
                status="partial", rows_imported=row_count, warnings=warnings_list
            )

        return TabImportResult(status="success", rows_imported=row_count)

    # 兼容 legacy 格式
    if "ok" in result or "imported_count" in result:
        return make_import_result_from_legacy(result)

    # 默认当成功
    return TabImportResult(status="success")


# ---------------------------------------------------------------------------
# Registry registration — 模块导入即注册 d1~d7
# ---------------------------------------------------------------------------


def register_d_cycle_adapters() -> None:
    """将 d1~d7 适配器注册到 IE_ADAPTER_REGISTRY。"""
    register_adapter("d1", AdapterSpec(export_fn=_d1_export, import_fn=_d1_import))
    register_adapter("d2", AdapterSpec(export_fn=_d2_export, import_fn=_d2_import))
    register_adapter("d3", AdapterSpec(export_fn=_d3_export, import_fn=_d3_import))
    register_adapter("d4", AdapterSpec(export_fn=_d4_export, import_fn=_d4_import))
    register_adapter("d5", AdapterSpec(export_fn=_d5_export, import_fn=_d5_import))
    register_adapter("d6", AdapterSpec(export_fn=_d6_export, import_fn=_d6_import))
    register_adapter("d7", AdapterSpec(export_fn=_d7_export, import_fn=_d7_import))
    logger.info("Registered D-cycle adapters: d1~d7")


# 模块导入时自动注册
register_d_cycle_adapters()
