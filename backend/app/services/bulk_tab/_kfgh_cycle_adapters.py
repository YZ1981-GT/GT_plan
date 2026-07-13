"""K/F/G/H 循环 adapter 接线 — Task 8.1（Phase 2 扩循环）

镜像 `_d_cycle_adapters.py` 的结构与铁律，把 bulk 层的统一签名
`(db, wp_id, sheet_code, mode/strategy)` 映射到 K/F/G/H 各循环既有单表
I/E 端点（`_{cycle}_import_export.py`）——100% 复用其 workbook 构建/解析逻辑，
不重写列格式、不新造 xlsx。

与 D 循环的差异（为什么用表驱动 + 通用包装，而非 52 个手写函数）：
  K/F/G/H 的 I/E 端点分两个家族：
    - 手写族：命名函数（如 g4_main_export_template），同 D 模式。
    - 工厂族：`create_cycle_import_export_router(tag, api_prefix, specs)` 生成的
      闭包端点（k1~k13、g1/g2/g3/g5/g9/g10/g12/g13/g14、h1~h8、f4/f5 等），
      函数无导出名。
  两族都把三端点注册在 `module.router` 上，路径形如
  `/api/workpapers/{wp_id}/{api_prefix}/{export-template|export-data|import-data}`。
  因此统一用「按路由后缀提取 endpoint 闭包 + 按签名传参」的通用包装，既覆盖手写族
  也覆盖工厂族，避免 52 份重复样板。每个 endpoint 直调（绕过 FastAPI DI），
  db/current_user 显式传入，与 `_d_cycle_adapters` 直调命名函数语义一致。

api_prefix 约定：注册键 = 单表 I/E 端点 URL 中的 `{api_prefix}` 段
（也是 ACNR manifest entry 的 api_prefix 字段）。

核心铁律（同 D）：
  - 复用单表 I/E 执行层，不重写 xlsx 列格式
  - service 只 flush 不 commit（这里不写库，仅转调端点函数）
  - 空表 → skipped（复用 `_convert_import_response` 语义）
  - endpoint 缺失/签名不兼容 → import 返回 failed，不整包崩

Requirements: 7.1
"""
from __future__ import annotations

import importlib
import inspect
import logging
from typing import Any, Callable, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.bulk_tab.single_tab_adapter import (
    AdapterSpec,
    TabImportResult,
    register_adapter,
)

# 复用 D 循环 adapter 的共享辅助（StreamingResponse→bytes / UploadFile 构造 /
# dummy user / 端点响应 dict→TabImportResult 转换，含空表 skipped 语义）。
from app.services.bulk_tab._d_cycle_adapters import (
    _DUMMY_USER,
    _convert_import_response,
    _make_upload_file,
    _read_streaming_response,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# api_prefix → I/E 端点模块 映射（K/F/G/H 全量）
#
# 值为 `app.routers.wp_render_strategies.<module>` 的模块名（不含包前缀）。
# 由 `backend/app/routers/wp_render_strategies/_*_import_export.py` 枚举得出，
# 覆盖手写族与工厂族。仅收录真正暴露三端点（export-template/export-data/
# import-data）的循环，其余（无 I/E 端点）不登记。
# ---------------------------------------------------------------------------

_MODULE_PKG = "app.routers.wp_render_strategies."

_PREFIX_TO_MODULE: dict[str, str] = {
    # ── F 循环 ────────────────────────────────────────────────────────────
    "f0": "_f0_import_export",
    "f1": "_f1_import_export",
    "f2": "_f2_import_export",
    "f2-spe": "_f2_special_import_export",
    "f2-st": "_f2_stocktake_import_export",
    "f2-val": "_f2_valuation_import_export",
    "f3": "_f3_import_export",
    "f4": "_f4_import_export",
    "f5": "_f5_import_export",
    # ── G 循环 ────────────────────────────────────────────────────────────
    "g0": "_g0_confirmation_import_export",
    "g1": "_g1_trading_financial_assets_import_export",
    "g2": "_g2_interest_receivable_import_export",
    "g3": "_g3_dividend_receivable_import_export",
    "g4-ecl": "_g4_bond_investment_ecl_import_export",
    "g4-main": "_g4_bond_investment_main_import_export",
    "g4-sppi": "_g4_bond_investment_sppi_import_export",
    "g5": "_g5_long_term_receivable_import_export",
    "g6-ecl": "_g6_other_bond_investment_ecl_import_export",
    "g6-main": "_g6_other_bond_investment_main_import_export",
    "g6-sppi": "_g6_other_bond_investment_sppi_import_export",
    "g7-main": "_g7_long_term_equity_main_import_export",
    "g7-equity-method": "_g7_long_term_equity_method_import_export",
    "g7-sub": "_g7_long_term_equity_subsidiary_import_export",
    "g8": "_g8_other_equity_instruments_import_export",
    "g9": "_g9_other_noncurrent_financial_import_export",
    "g10": "_g10_trading_financial_liabilities_import_export",
    "g11": "_g11_investment_income_import_export",
    "g12": "_g12_net_hedge_gains_import_export",
    "g13": "_g13_fair_value_changes_import_export",
    "g14": "_g14_credit_impairment_loss_import_export",
    # ── H 循环 ────────────────────────────────────────────────────────────
    "h0": "_h0_confirmation_import_export",
    "h1": "_h1_import_export",
    "h2": "_h2_import_export",
    "h3": "_h3_import_export",
    "h4": "_h4_import_export",
    "h6": "_h6_import_export",
    "h8": "_h8_import_export",
    "h10": "_h10_asset_disposal_income_import_export",
    # ── K 循环 ────────────────────────────────────────────────────────────
    "k0": "_k0_confirmation_import_export",
    "k1": "_k1_import_export",
    "k2": "_k2_import_export",
    "k3": "_k3_import_export",
    "k4": "_k4_import_export",
    "k5": "_k5_import_export",
    "k6": "_k6_import_export",
    "k7": "_k7_import_export",
    "k8": "_k8_import_export",
    "k9": "_k9_import_export",
    "k10": "_k10_import_export",
    "k11": "_k11_import_export",
    "k12": "_k12_import_export",
    "k13": "_k13_import_export",
    # ── C / E / I / J / L 循环（wp_render_strategies 统一族，路径同构 ─────────
    #     `/api/workpapers/{wp_id}/{api_prefix}/{suffix}`）。
    #     api_prefix = URL 路径段（高置信从 endpoint path 推出）。
    #     j3 路径异形（/import-export/{template|export|import}）→ 见 _j3 bespoke。
    #     M/N/S 独立路由族（/api/{module}/{wp_id}/{suffix}）结构不同 + api_prefix
    #     由 ACNR catalog 决定 → 不在此投机注册，见 §Notes / eval 文档。
    "c24-journal": "_c24_import_export",
    "e1": "_e1_import_export",
    "i1": "_i1_import_export",
    "i2": "_i2_import_export",
    "i3": "_i3_import_export",
    "i4": "_i4_import_export",
    "i5": "_i5_import_export",
    "i6": "_i6_import_export",
    "j1": "_j1_import_export",
    "j2": "_j2_import_export",
    "l0": "_l0_confirmation_import_export",
}


# ---------------------------------------------------------------------------
# 通用端点提取 + 签名感知调用
# ---------------------------------------------------------------------------

# 各端点 URL 后缀
_SUFFIX_TEMPLATE = "export-template"
_SUFFIX_DATA = "export-data"
_SUFFIX_IMPORT = "import-data"


def _endpoint_for(module: Any, api_prefix: str, suffix: str) -> Callable[..., Any] | None:
    """从 `module.router.routes` 提取匹配 `/{api_prefix}/{suffix}` 的 endpoint 闭包。

    手写族与工厂族都把端点注册在 `module.router` 上，故按路由路径后缀提取即可
    统一覆盖两族。
    """
    router = getattr(module, "router", None)
    if router is None:
        return None
    want = f"/{api_prefix}/{suffix}"
    for route in getattr(router, "routes", []):
        path = getattr(route, "path", "")
        if path.endswith(want):
            return getattr(route, "endpoint", None)
    return None


async def _call_endpoint(
    endpoint: Callable[..., Any],
    *,
    db: AsyncSession,
    wp_id: str,
    sheet_code: str,
    upload_file: Any | None = None,
) -> Any:
    """按 endpoint 实际签名传参并 await（绕过 FastAPI DI，显式注入 db/user）。

    仅传入端点签名中真实存在的参数，兼容各循环签名差异
    （有的 export_template 不取 db、有的取 include_guidance 等）。
    """
    params = inspect.signature(endpoint).parameters
    kwargs: dict[str, Any] = {}
    if "wp_id" in params:
        kwargs["wp_id"] = wp_id
    if "sheet" in params:
        kwargs["sheet"] = sheet_code
    elif "sheet_code" in params:
        kwargs["sheet_code"] = sheet_code
    if "db" in params:
        kwargs["db"] = db
    if "current_user" in params:
        kwargs["current_user"] = _DUMMY_USER
    if "include_guidance" in params:
        kwargs["include_guidance"] = False
    if upload_file is not None and "file" in params:
        kwargs["file"] = upload_file
    return await endpoint(**kwargs)


def _make_export_fn(api_prefix: str, module_name: str):
    """构造某 api_prefix 的 export_fn（template/data 共用，按 mode 选端点）。"""

    async def export_fn(
        db: AsyncSession,
        wp_id: str,
        sheet_code: str,
        mode: Literal["template", "data"],
    ) -> bytes:
        module = importlib.import_module(_MODULE_PKG + module_name)
        suffix = _SUFFIX_TEMPLATE if mode == "template" else _SUFFIX_DATA
        endpoint = _endpoint_for(module, api_prefix, suffix)
        if endpoint is None:
            raise RuntimeError(
                f"api_prefix='{api_prefix}' 模块 {module_name} 未找到 {suffix} 端点"
            )
        resp = await _call_endpoint(endpoint, db=db, wp_id=wp_id, sheet_code=sheet_code)
        return await _read_streaming_response(resp)

    return export_fn


def _make_import_fn(api_prefix: str, module_name: str):
    """构造某 api_prefix 的 import_fn（解析响应 dict → TabImportResult）。"""

    async def import_fn(
        db: AsyncSession,
        wp_id: str,
        sheet_code: str,
        xlsx_bytes: bytes,
        strategy: str,
    ) -> TabImportResult:
        module = importlib.import_module(_MODULE_PKG + module_name)
        endpoint = _endpoint_for(module, api_prefix, _SUFFIX_IMPORT)
        if endpoint is None:
            return TabImportResult(
                status="failed",
                errors=[f"api_prefix='{api_prefix}' 模块 {module_name} 未找到 import-data 端点"],
            )
        upload = _make_upload_file(xlsx_bytes, sheet_code)
        try:
            result = await _call_endpoint(
                endpoint, db=db, wp_id=wp_id, sheet_code=sheet_code, upload_file=upload
            )
        except Exception as e:  # noqa: BLE001 — 单 sheet 失败逐条记，不整包崩
            logger.warning(
                "%s import_data failed for sheet=%s: %s", api_prefix, sheet_code, e
            )
            return TabImportResult(status="failed", errors=[str(e)])

        if isinstance(result, dict):
            return _convert_import_response(result)
        return TabImportResult(status="success")

    return import_fn


# ---------------------------------------------------------------------------
# J3 bespoke adapter（路径异形：/import-export/{template|export|import}）
#
# J3 的 I/E 路由 prefix=`/api/workpapers/{wp_id}/import-export`，端点后缀为
# `/template`、`/export`、`/import`（非统一族的 export-template/export-data/
# import-data），故通用 `_endpoint_for` 无法按 `/{prefix}/{suffix}` 提取。
# 直调其命名函数（export_template/export_data/import_data），api_prefix 键取 "j3"。
# ---------------------------------------------------------------------------


async def _j3_export(
    db: AsyncSession, wp_id: str, sheet_code: str, mode: Literal["template", "data"]
) -> bytes:
    from app.routers.wp_render_strategies._j3_import_export import (
        export_template as _j3_tpl,
        export_data as _j3_data,
    )

    if mode == "template":
        resp = await _j3_tpl(wp_id=wp_id, user=_DUMMY_USER)
    else:
        resp = await _j3_data(wp_id=wp_id, db=db, user=_DUMMY_USER)
    return await _read_streaming_response(resp)


async def _j3_import(
    db: AsyncSession, wp_id: str, sheet_code: str, xlsx_bytes: bytes, strategy: str
) -> TabImportResult:
    from app.routers.wp_render_strategies._j3_import_export import import_data as _j3_imp

    upload = _make_upload_file(xlsx_bytes, sheet_code)
    try:
        result = await _j3_imp(wp_id=wp_id, file=upload, db=db, user=_DUMMY_USER)
    except Exception as e:  # noqa: BLE001
        logger.warning("j3 import_data failed for sheet=%s: %s", sheet_code, e)
        return TabImportResult(status="failed", errors=[str(e)])
    if isinstance(result, dict):
        return _convert_import_response(result)
    return TabImportResult(status="success")


# ---------------------------------------------------------------------------
# 注册 — 模块导入即注册（K/F/G/H + C/E/I/J/L wp_render_strategies 统一族）
# ---------------------------------------------------------------------------


def register_kfgh_cycle_adapters() -> None:
    """将 wp_render_strategies I/E 统一族的全部 api_prefix 适配器注册到 registry。

    覆盖 F/G/H/K（Task 8.1）+ C24/E1/I/J1/J2/L0（补齐，同构路径通用包装）
    + J3（异形路径，bespoke）。D 循环由 `_d_cycle_adapters` 单独注册。
    M/N/S 独立路由族不在此（见文件头 §说明）。
    """
    for api_prefix, module_name in _PREFIX_TO_MODULE.items():
        register_adapter(
            api_prefix,
            AdapterSpec(
                export_fn=_make_export_fn(api_prefix, module_name),
                import_fn=_make_import_fn(api_prefix, module_name),
            ),
        )
    # J3 bespoke（异形路径）
    register_adapter("j3", AdapterSpec(export_fn=_j3_export, import_fn=_j3_import))

    logger.info(
        "Registered wp_render_strategies I/E adapters: %d prefixes (+ j3 bespoke)",
        len(_PREFIX_TO_MODULE),
    )


# 模块导入时自动注册
register_kfgh_cycle_adapters()
