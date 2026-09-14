"""SingleTabIeAdapter — 屏蔽执行层差异，统一 export/import 接口。

给定 (wp_id, api_prefix, sheet_code, mode)，产出/解析该 Tab 的 xlsx，
**复用单表 I/E 执行层**（直调各循环 _{cycle}_import_export.py 的 workbook
构建/解析纯函数，避免自调 HTTP）。

差异循环通过注册表 IE_ADAPTER_REGISTRY[api_prefix] 适配；
未注册 → 调用方标 skip_reason=no_adapter（fail-soft）。

冲突策略在 adapter 的解析→写库阶段应用（见 ConflictResolver，Task 3.1 实现）。

核心铁律：
  - service 只 flush 不 commit
  - 行数超限 → partial + row_limit_exceeded 告警，不整包失败
  - 未注册 prefix → skip_reason=no_adapter

Requirements: 1.3, 2.1, 2.7
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Literal, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

# 冲突策略类型（Req 8.1–8.3）
ConflictStrategy = Literal["overwrite", "fill-empty", "reject"]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class TabImportResult:
    """单 Tab 导入结果。

    status:
      - success: 全部行成功写入
      - partial: 部分行成功（如超行数限制截断）
      - failed: 该 sheet 导入失败（解析错误/冲突拒绝等）
    """

    status: Literal["success", "partial", "failed"]
    rows_imported: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class AdapterSpec(NamedTuple):
    """注册表中每个 api_prefix 对应的适配器规格。

    export_fn: async (db, wp_id, sheet_code, mode) -> bytes
    import_fn: async (db, wp_id, sheet_code, xlsx_bytes, strategy) -> TabImportResult
    """

    export_fn: Callable[
        [AsyncSession, str, str, Literal["template", "data"]],
        Coroutine[Any, Any, bytes],
    ]
    import_fn: Callable[
        [AsyncSession, str, str, bytes, ConflictStrategy],
        Coroutine[Any, Any, TabImportResult],
    ]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# api_prefix → AdapterSpec 注册表
# Task 2.2 逐 prefix 注册 d1~d7 的具体实现
IE_ADAPTER_REGISTRY: dict[str, AdapterSpec] = {}


def register_adapter(api_prefix: str, adapter: AdapterSpec) -> None:
    """注册一个 api_prefix 的 I/E 适配器。"""
    IE_ADAPTER_REGISTRY[api_prefix] = adapter


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROW_LIMIT = 500


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def export_tab(
    db: AsyncSession,
    wp_id: str,
    api_prefix: str,
    sheet_code: str,
    mode: Literal["template", "data"],
) -> bytes:
    """导出单个 Tab 为 xlsx bytes。

    直调 IE_ADAPTER_REGISTRY[api_prefix] 的 export_fn 获取工作簿字节流。

    Args:
        db: Async database session（只 flush 不 commit）。
        wp_id: 底稿实例 UUID。
        api_prefix: 循环 API 前缀（如 "d2"）。
        sheet_code: Sheet 编码（如 "D2-2"）。
        mode: "template" 或 "data"。

    Returns:
        xlsx 文件字节流。

    Raises:
        KeyError: api_prefix 未注册时抛出（调用方应捕获并标 skip_reason=no_adapter）。
        Exception: 底层 I/E 逻辑抛出的其他异常（格式错误、DB 错误等）。
    """
    adapter = IE_ADAPTER_REGISTRY.get(api_prefix)
    if adapter is None:
        raise KeyError(
            f"IE_ADAPTER_REGISTRY 未注册 api_prefix='{api_prefix}'，"
            f"sheet_code='{sheet_code}' 将被标记为 skip_reason=no_adapter"
        )

    logger.debug(
        "export_tab: wp_id=%s api_prefix=%s sheet=%s mode=%s",
        wp_id, api_prefix, sheet_code, mode,
    )

    return await adapter.export_fn(db, wp_id, sheet_code, mode)


async def import_tab(
    db: AsyncSession,
    wp_id: str,
    api_prefix: str,
    sheet_code: str,
    xlsx_bytes: bytes,
    strategy: ConflictStrategy = "overwrite",
) -> TabImportResult:
    """导入单个 Tab 的 xlsx 数据。

    解析 xlsx → 经 ConflictResolver（Task 3.1）处理冲突 → 写库（只 flush 不 commit）；
    返回行数/错误/超限告警。

    Args:
        db: Async database session（只 flush 不 commit）。
        wp_id: 底稿实例 UUID。
        api_prefix: 循环 API 前缀（如 "d2"）。
        sheet_code: Sheet 编码（如 "D2-2"）。
        xlsx_bytes: xlsx 文件字节流。
        strategy: 冲突策略 "overwrite"/"fill-empty"/"reject"。

    Returns:
        TabImportResult 含 status/rows_imported/warnings/errors。

    Raises:
        KeyError: api_prefix 未注册时抛出（调用方应捕获并标 skip_reason=no_adapter）。
    """
    adapter = IE_ADAPTER_REGISTRY.get(api_prefix)
    if adapter is None:
        raise KeyError(
            f"IE_ADAPTER_REGISTRY 未注册 api_prefix='{api_prefix}'，"
            f"sheet_code='{sheet_code}' 将被标记为 skip_reason=no_adapter"
        )

    logger.debug(
        "import_tab: wp_id=%s api_prefix=%s sheet=%s strategy=%s",
        wp_id, api_prefix, sheet_code, strategy,
    )

    return await adapter.import_fn(db, wp_id, sheet_code, xlsx_bytes, strategy)


# ---------------------------------------------------------------------------
# Generic adapter helpers (shared by cycle-specific adapters in Task 2.2)
# ---------------------------------------------------------------------------


def workbook_to_bytes(wb: Any) -> bytes:
    """将 openpyxl Workbook 序列化为 bytes。"""
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def make_import_result_from_legacy(
    response: dict[str, Any],
    *,
    row_limit: int = ROW_LIMIT,
) -> TabImportResult:
    """将现有单表 I/E 端点的返回 dict 转换为 TabImportResult。

    现有端点返回格式一般为：
      {"ok": True/False, "imported_count": N, "errors": [...], "warning": "..."}
    """
    ok = response.get("ok", True)
    imported = response.get("imported_count", 0)
    errors = response.get("errors", [])
    warnings_list: list[str] = []

    # 行数超限告警
    warning_str = response.get("warning", "")
    if warning_str:
        warnings_list.append(warning_str)

    # skipped columns 告警
    skipped_warnings = response.get("warnings", [])
    if skipped_warnings:
        warnings_list.extend(skipped_warnings)

    # 判断 status
    if not ok and errors:
        return TabImportResult(
            status="failed",
            rows_imported=0,
            warnings=warnings_list,
            errors=errors,
        )

    if imported > 0 and (warning_str or imported >= row_limit):
        return TabImportResult(
            status="partial",
            rows_imported=imported,
            warnings=warnings_list if warnings_list else [f"row_limit_exceeded: {imported} >= {row_limit}"],
            errors=errors,
        )

    return TabImportResult(
        status="success",
        rows_imported=imported,
        warnings=warnings_list,
        errors=errors,
    )
