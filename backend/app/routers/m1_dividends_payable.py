"""M1 应付股利（利润）— 导入导出三级端点 + 外币折算 + 股利测算 + 公式验证

6个端点：
- POST /api/m1-dividends-payable/{wp_id}/export-template    多sheet空白模板xlsx
- POST /api/m1-dividends-payable/{wp_id}/export-data         当前数据xlsx
- POST /api/m1-dividends-payable/{wp_id}/import-data         解析xlsx写入（multipart）
- POST /api/m1-dividends-payable/{wp_id}/validate-formulas   校验负债类公式方向（期末=期初+贷-借）
- GET  /api/m1-dividends-payable/{wp_id}/fx-calculation      外币折算结果（M1-4）
- GET  /api/m1-dividends-payable/{wp_id}/dividend-calculation 股利测算结果（M1-5）

科目编码: 2232应付股利（贷方/负债类）
公式方向: 期末=期初+贷方-借方（宣告在贷方增加，实际支付在借方减少）
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 7.7
"""

from __future__ import annotations

import inspect
import logging
import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.m1_dividends_payable_service import (
    EXPORT_SHEETS,
    calc_fx_conversion,
    calc_dividend_estimation,
    export_data,
    export_template,
    import_data,
    validate_liability_formulas,
)

from app.routers.wp_render_strategies._x3_adjustment_import_export import (
    X3_SHEET_SPECS,
    X3ContractError,
    attach_shape_a_routes,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/m1-dividends-payable",
    tags=["M1 应付股利"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# X-3 调整分录汇总表 —— 形态 A 三态 + 形态 B 的 `sheet` 分派
# spec: x3-adjustment-entry-import-export 任务 5.2（R4.1 / R4.2 / R4.3 / R4.4 / R1.6）
# ═══════════════════════════════════════════════════════════════════════════════

#: 本模块的短前缀 = catalog `import_export.api_prefix`，单份 UI 与批量两条通路共用它。
_IE_API_PREFIX = "m1"

#: 本前缀的 X-3 sheet 码 —— 从 `X3_SHEET_SPECS`（Key_Ledger 单一真源）按短前缀**反查**。
#: 🔴 本模块内不写 X-3 字面量：写死一份即成后端第二真源，前端改键时不会打红。
#: 反查为空 ⇒ 下面 `attach_shape_a_routes` 立即抛 `X3ContractError`（fail-loud，不静默少端点）。
_X3_CODES: frozenset[str] = frozenset(
    code for code, spec in X3_SHEET_SPECS.items() if spec.api_prefix == _IE_API_PREFIX
)

#: 形态 B（长前缀）三态端点服务的业务表码 —— 从 service 既有 `EXPORT_SHEETS` **派生**，
#: 故 sheet 码仍只写一次（在 service），本模块不抄第二份。
#:
#: 🔴 派生失败必须**立即抛**而不是留一个错的白名单：前端 `useM1ImportExport` 一直在传该值
#:    （`M1TabDetail` / `M1TabFxRate` / `M1TabDividendCalc` 各传自己那张表的码），白名单错了
#:    会让线上导入导出全落进下面的 400 分支 —— 接口红但四层守卫全绿，属最贵的一类。
_LEGACY_SHEETS: frozenset[str] = frozenset(EXPORT_SHEETS)
_LEGACY_SHAPE_BAD = sorted(
    s for s in _LEGACY_SHEETS if not re.fullmatch(rf"{_IE_API_PREFIX.upper()}-\d+", s)
)
if not _LEGACY_SHEETS or _LEGACY_SHAPE_BAD:
    raise X3ContractError(
        f"{_IE_API_PREFIX} 既有 sheet 白名单从 EXPORT_SHEETS 派生失败: "
        f"取值 {sorted(_LEGACY_SHEETS)}，非法项 {_LEGACY_SHAPE_BAD}，"
        f"期望非空且全为 {_IE_API_PREFIX.upper()}-N 形态"
    )

#: 本前缀 sheet 白名单的**唯一真源**（R4.4）= 形态 B 的三张业务表 + 形态 A 的 X-3。
#:
#: 🔴 既有形态 B handler 此前**完全不声明** `sheet`（FastAPI 静默丢弃前端传的值 ⇒ 三张表
#:    的导出内容都是同一个三 sheet workbook），该存量缺陷登记在 `Deviation_Registry` G6，
#:    本任务**不修**：`sheet` 落在 `_LEGACY_SHEETS` 时仍逐字走既有路径（产物不变，R1.6）。
#:    本任务只新增两件事：X-3 委派共享实现 + 未登记值 400。
IE_SHEETS: frozenset[str] = _LEGACY_SHEETS | _X3_CODES

attach_shape_a_routes(router, api_prefix=_IE_API_PREFIX, sheets=_X3_CODES)

#: 形态 A 三态端点的可调用对象（挂载后按路径后缀反查）。
#: 🔴 委派必须落到**同一个** callable 上，不抄一份编排（10MB 上限 / 解析失败转 400 /
#:    残留清理策略 / 响应载荷）：抄一份就是 R1.5 禁的第三套实现，两侧此后各自漂移。
_X3_SHAPE_A: dict[str, Any] = {
    str(getattr(route, "path", "")).rsplit("/", 1)[-1]: route.endpoint
    for route in router.routes
    if str(getattr(route, "path", "")).startswith(
        f"/api/workpapers/{{wp_id}}/{_IE_API_PREFIX}/"
    )
}
if len(_X3_SHAPE_A) != 3:
    raise X3ContractError(
        f"{_IE_API_PREFIX} 形态 A 三态端点反查到 {sorted(_X3_SHAPE_A)}（期望 3 条）"
    )


def _requires_x3(sheet: str | None) -> bool:
    """形态 B handler 的 `sheet` 三分支判定（R4.1 / R4.2 / R1.6）。

    - `None` ⇒ False：既有调用方不传该参数，走**逐字不变**的既有路径；
    - 值 ∈ `IE_SHEETS` 且为 X-3 ⇒ True：委派共享实现；
    - 值 ∈ `IE_SHEETS` 的其余业务表 ⇒ False：既有路径，产物与施加前逐字节相同；
    - 值 ∉ `IE_SHEETS` ⇒ 400（文案沿用共享实现 `_validate_sheet`）。

    🔴 未登记值刻意**不**回退成「导出全部 sheet」：那是 E6 存量缺陷的形态，
       200 + 错内容比 400 难查一个量级（父 spec 在 L4-3 上踩过）。
    """
    if sheet is None:
        return False
    if sheet not in IE_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(IE_SHEETS)}")
    return sheet in _X3_CODES


async def _x3_delegate(action: str, **kwargs: Any) -> Any:
    """把请求交给形态 A 的同名端点（= 共享实现的那个 callable）。

    调用方没给的**非依赖**参数从共享实现签名的默认值剥出（`Query(...)` 包装 → `.default`）：
    🔴 不剥而直接调用，`strategy` 会拿到 `Query` 包装对象本身 ⇒ 共享实现的
       `_should_purge_residual` 比对 `== "overwrite"` 不成立 ⇒ 残留族键不清 = 幽灵行，
       而接口仍 200。这类默认值只有共享实现一份，本模块不抄第二份。
    签名要求的参数本模块给不出时**抛 500**，不静默传个占位值。
    """
    endpoint = _X3_SHAPE_A[action]
    for name, par in inspect.signature(endpoint).parameters.items():
        if name in kwargs:
            continue
        raw = par.default
        if raw is inspect.Parameter.empty or getattr(raw, "dependency", None) is not None:
            raise HTTPException(
                500, f"X-3 委派缺参: {action} 的 {name!r} 须由本模块提供（共享实现签名已变）"
            )
        value = getattr(raw, "default", raw)
        if value is Ellipsis or type(value).__name__ == "PydanticUndefinedType":
            raise HTTPException(
                500, f"X-3 委派缺参: {action} 的 {name!r} 是必填项（共享实现签名已变）"
            )
        kwargs[name] = value
    return await endpoint(**kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class ValidateFormulasRequest(BaseModel):
    """负债类公式方向验证请求"""
    begin: float = Field(..., description="期初余额")
    credit: float = Field(0.0, description="贷方发生额（宣告分配）")
    debit: float = Field(0.0, description="借方发生额（实际支付）")
    reportedEnd: float | None = Field(None, description="报告期末余额（可选，用于差异校验）")


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助：从 wp_id 获取 project_id 和 year
# ═══════════════════════════════════════════════════════════════════════════════


async def _get_wp_context(wp_id: str, db: AsyncSession) -> dict[str, Any]:
    """从 wp_id 取关联的 project_id 和 audit_year."""
    result = await db.execute(
        sa.text("""
            SELECT wp.project_id, p.audit_year
            FROM working_paper wp
            JOIN projects p ON p.id = wp.project_id
            WHERE wp.id = :wp_id
        """),
        {"wp_id": wp_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, f"底稿不存在: {wp_id}")
    return {
        "project_id": row.project_id,
        "year": int(row.audit_year or 2025),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/export-template")
async def m1_export_template(
    wp_id: str,
    sheet: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（3个sheet：M1-2明细表 / M1-4外币汇率 / M1-5股利测算）

    `sheet` 为 additive 可选参数（任务 5.2）：不传或传业务表码 ⇒ 行为与施加前逐字相同。

    Requirements: 7.7
    """
    if _requires_x3(sheet):
        return await _x3_delegate(
            "export-template", wp_id=wp_id, sheet=sheet, current_user=current_user
        )
    buffer = await export_template(wp_id, db)
    filename = "M1应付股利_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/export-data")
async def m1_export_data(
    wp_id: str,
    sheet: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（3个sheet：M1-2明细表 / M1-4外币汇率 / M1-5股利测算）

    `sheet` 为 additive 可选参数（任务 5.2）：不传或传业务表码 ⇒ 行为与施加前逐字相同。

    Requirements: 7.7
    """
    if _requires_x3(sheet):
        return await _x3_delegate(
            "export-data", wp_id=wp_id, sheet=sheet, db=db, current_user=current_user
        )
    buffer = await export_data(wp_id, db)
    filename = "M1应付股利_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def m1_import_data(
    wp_id: str,
    sheet: str | None = Query(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（支持3个sheet：M1-2/M1-4/M1-5）

    `sheet` 为 additive 可选参数（任务 5.2）：不传或传业务表码 ⇒ 行为与施加前逐字相同。

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 7.7
    """
    if _requires_x3(sheet):
        return await _x3_delegate(
            "import-data",
            wp_id=wp_id,
            sheet=sheet,
            file=file,
            db=db,
            current_user=current_user,
        )
    content = await file.read()
    try:
        result = await import_data(wp_id, content, db)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 公式验证（负债类：期末=期初+贷方-借方）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/validate-formulas")
async def m1_validate_formulas(
    wp_id: str,
    request: ValidateFormulasRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """校验负债类公式方向（期末=期初+贷方-借方）

    应付股利为贷方/负债类科目：
    - 宣告分配时贷方增加
    - 实际支付时借方减少
    - 期末余额 = 期初 + 贷方发生额 - 借方发生额

    Requirements: 7.7
    """
    result = validate_liability_formulas(
        begin=request.begin,
        credit=request.credit,
        debit=request.debit,
        reported_end=request.reportedEnd,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 外币折算（M1-4）
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/fx-calculation")
async def m1_fx_calculation(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """外币折算计算结果（M1-4外币汇率测算表）

    对外币股东的应付股利按期末即期汇率折算本位币，
    计算汇兑差异 = 折算本位币 - 账面本位币。

    Returns:
        {
            items: list[{shareholder, currency, original_amount, rate, converted, booked, fx_diff}],
            total_fx_diff: float,
            has_material_diff: bool
        }

    Requirements: 7.7 (M1-4)
    """
    ctx = await _get_wp_context(wp_id, db)
    project_id = ctx["project_id"]

    result = await calc_fx_conversion(db, project_id, wp_id)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 股利测算（M1-5）
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/dividend-calculation")
async def m1_dividend_calculation(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """股利测算计算结果（M1-5应付股利测算表）

    接收M6利润分配的可供分配利润，按分配比例测算应宣告股利，
    与账面宣告比较差异。

    Returns:
        {
            items: list[{shareholder, distributable_profit, ratio, estimated_dividend, booked_dividend, diff}],
            total_estimated: float,
            total_booked: float,
            total_diff: float,
            has_material_diff: bool
        }

    Requirements: 7.7 (M1-5)
    """
    ctx = await _get_wp_context(wp_id, db)
    project_id = ctx["project_id"]

    result = await calc_dividend_estimation(db, project_id, wp_id)
    return result
