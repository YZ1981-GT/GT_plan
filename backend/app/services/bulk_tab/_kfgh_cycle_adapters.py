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
# 值有两种形态，由 `_resolve_module_path` 统一解析：
#   ① **相对名**（不含 `.`）—— `app.routers.wp_render_strategies.<module>` 下的工厂/
#      手写族模块，如 `_k1_import_export`。由
#      `backend/app/routers/wp_render_strategies/_*_import_export.py` 枚举得出。
#   ② **完整点路径**（含 `.`）—— 专属 router 模块，如
#      `app.routers.l2_interest_payable`。用于形态 A 端点由专属 router 自己提供的
#      前缀（X-3 调整分录的 16 个短前缀），使界面（单份 UI）与批量（bulk）两条通路
#      解析到**同一个端点函数对象**，避免 split-brain（GS6
#      `test_x3_adapter_host_same_module` 钉死该不变量）。
#
# 仅收录真正暴露三端点（export-template/export-data/import-data）的循环，
# 其余（无 I/E 端点）不登记。
# ---------------------------------------------------------------------------

_MODULE_PKG = "app.routers.wp_render_strategies."


def _resolve_module_path(value: str) -> str:
    """`_PREFIX_TO_MODULE` 的值 → 可 `import_module` 的模块点路径。

    含 `.` ⇒ 已是完整点路径（专属 router 模块），原样返回；否则拼 `_MODULE_PKG`
    前缀（工厂/手写族的相对名）。两种形态并存，故拼接只此一处。
    """
    return value if "." in value else _MODULE_PKG + value


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
    # ── L 循环 ────────────────────────────────────────────────────────────
    #   `l2` / `l6` 指专属 router（X-3 调整分录形态 A 由它们自己提供，两路同源）
    "l1": "_l1_import_export",
    "l2": "app.routers.l2_interest_payable",
    "l3": "_l3_import_export",
    "l4": "_l4_import_export",
    "l5": "_l5_import_export",
    "l6": "app.routers.l6_special_payables",
    "l7": "_l7_import_export",
    "l8": "_l8_import_export",
    # ── M 循环（M1~M10 全部指专属 router，两路同源）─────────────────────────
    "m1": "app.routers.m1_dividends_payable",
    "m2": "app.routers.m2_paid_in_capital",
    "m3": "app.routers.m3_treasury_stock",
    "m4": "app.routers.m4_capital_reserve",
    "m5": "app.routers.m5_surplus_reserve",
    "m6": "app.routers.m6_retained_earnings",
    "m7": "app.routers.m7_special_reserve",
    "m8": "app.routers.m8_general_risk_reserve",
    "m9": "app.routers.m9_other_comprehensive_income",
    "m10": "app.routers.m10_other_equity_instruments",
    # ── N 循环（`n4` 无 X-3 作业面，仍指工厂）──────────────────────────────
    "n1": "app.routers.n1_deferred_tax_assets",
    "n2": "app.routers.n2_taxes_payable",
    "n3": "app.routers.n3_deferred_tax_liabilities",
    "n4": "_n4_import_export",
    "n5": "app.routers.n5_income_tax_expense",
    # ── H 补充 ────────────────────────────────────────────────────────────
    "h5": "_h5_import_export",
    "h7": "_h7_import_export",
    "h9": "_h9_import_export",
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
    strategy: str | None = None,
) -> Any:
    """按 endpoint 实际签名传参并 await（绕过 FastAPI DI，显式注入 db/user）。

    仅传入端点签名中真实存在的参数，兼容各循环签名差异
    （有的 export_template 不取 db、有的取 include_guidance 等）。

    🔴 `strategy` 必须与 `sheet`/`include_guidance`/`file` 同款按签名探测后**显式传入**：
       不传的话该形参会落到端点默认值 `Query("overwrite")` 这个 `FieldInfo` 对象本身
       （**不是**字符串 `"overwrite"`），后果两条且方向相反于直觉 ——
       ① `resolve_conflict` 对未知策略走防御性 `else` ⇒ 合并语义**恰好**等同 overwrite，
          于是用户在批量对话框里选的 `fill-empty` / `reject` 被静默丢掉：`reject` 本该
          整表拒绝以防覆盖已编制内容，实际却按覆盖写入 = 静默数据丢失；
       ② `_should_purge_residual` 比对 `== "overwrite"` 对 `FieldInfo` 不成立 ⇒ bulk
          **从不清**残留族键（导入行数变少时留幽灵行），而界面通路会清 ⇒ 两条通路库态分叉。
       带 `strategy` 形参的端点当前恰为 16 个 X-3 短前缀，其余 73 键签名里没有这个形参 ⇒
       探测为假、`kwargs` 逐字不变（`test_x3_bulk_strategy_parity` 双向锁死这两侧）。
       `strategy is None` 时（导出通路）一律不传，与施加前逐字相同。
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
    if strategy is not None and "strategy" in params:
        kwargs["strategy"] = strategy
    return await endpoint(**kwargs)


def _make_export_fn(api_prefix: str, module_name: str):
    """构造某 api_prefix 的 export_fn（template/data 共用，按 mode 选端点）。"""

    async def export_fn(
        db: AsyncSession,
        wp_id: str,
        sheet_code: str,
        mode: Literal["template", "data"],
    ) -> bytes:
        module = importlib.import_module(_resolve_module_path(module_name))
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
        module = importlib.import_module(_resolve_module_path(module_name))
        endpoint = _endpoint_for(module, api_prefix, _SUFFIX_IMPORT)
        if endpoint is None:
            return TabImportResult(
                status="failed",
                errors=[f"api_prefix='{api_prefix}' 模块 {module_name} 未找到 import-data 端点"],
            )
        upload = _make_upload_file(xlsx_bytes, sheet_code)
        try:
            result = await _call_endpoint(
                endpoint,
                db=db,
                wp_id=wp_id,
                sheet_code=sheet_code,
                upload_file=upload,
                strategy=strategy,
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
