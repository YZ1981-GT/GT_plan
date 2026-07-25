"""D/F/G/H… 各循环底稿「公式管理」取数/计算/逻辑审核公式目录（只读 surfacing）。

背景：E1 货币资金已在 wp_formula.py 内以 `_E1_SHEET_FORMULAS` 逐 sheet surface 取数/计算/
逻辑审核公式（对齐 E1-1 标准）。本模块把同一范式推广到其他循环（D/F/G/H…），让公式管理
中心底稿节点对每张 sheet 都能体现其取数逻辑。

铁律（与 E1 一致）：
- 公式文案严格与各循环 `useX{n}FormulaEngine.ts` / `useX{n}Adjudication.ts` /
  `useX{n}CrossSheet.ts` 同源，**不臆造**；来源列注明所属 composable / sheet。
- 分类：取数（跨 sheet / 四表库）/ 计算（表间计算）/ logic_check（逻辑审核）。
- 每条按 `sheet_codes:[sheet_code]` 逐 sheet 归属，前端按选中 sheet 过滤。

结构：CYCLE_SHEET_FORMULAS[base_wp_code][sheet_code] = [(项目名, 公式, 分类, 说明, 来源), ...]
  base_wp_code 如 "D2" / "F1" / "G7" / "H1"（wp_code 去掉尾部 -N / A 后缀）。
"""

from __future__ import annotations

SheetFormula = tuple[str, str, str, str, str]
CycleCatalog = dict[str, dict[str, list[SheetFormula]]]

# 各循环家族目录（逐家族在独立模块维护，避免单文件过大 + 并发冲突）
CYCLE_SHEET_FORMULAS: CycleCatalog = {}


def _merge(catalog: CycleCatalog) -> None:
    """把某家族目录并入总目录（同 base 时浅合并 sheet 键）。"""
    for base, sheets in catalog.items():
        CYCLE_SHEET_FORMULAS.setdefault(base, {}).update(sheets)


# ── 逐家族并入（新增家族只需在此 import + _merge） ──
try:
    from app.routers.wp_surfaced_d import CATALOG as _D_CATALOG

    _merge(_D_CATALOG)
except Exception:  # noqa: BLE001 — 家族目录缺失/加载失败不影响其他家族
    pass

try:
    from app.routers.wp_surfaced_f import CATALOG as _F_CATALOG

    _merge(_F_CATALOG)
except Exception:  # noqa: BLE001
    pass

try:
    from app.routers.wp_surfaced_g import CATALOG as _G_CATALOG

    _merge(_G_CATALOG)
except Exception:  # noqa: BLE001
    pass

try:
    from app.routers.wp_surfaced_h import CATALOG as _H_CATALOG

    _merge(_H_CATALOG)
except Exception:  # noqa: BLE001
    pass

try:
    from app.routers.wp_surfaced_i import CATALOG as _I_CATALOG

    _merge(_I_CATALOG)
except Exception:  # noqa: BLE001
    pass

try:
    from app.routers.wp_surfaced_j import CATALOG as _J_CATALOG

    _merge(_J_CATALOG)
except Exception:  # noqa: BLE001
    pass

try:
    from app.routers.wp_surfaced_k import CATALOG as _K_CATALOG

    _merge(_K_CATALOG)
except Exception:  # noqa: BLE001
    pass

try:
    from app.routers.wp_surfaced_l import CATALOG as _L_CATALOG

    _merge(_L_CATALOG)
except Exception:  # noqa: BLE001
    pass

try:
    from app.routers.wp_surfaced_m import CATALOG as _M_CATALOG

    _merge(_M_CATALOG)
except Exception:  # noqa: BLE001
    pass

try:
    from app.routers.wp_surfaced_n import CATALOG as _N_CATALOG

    _merge(_N_CATALOG)
except Exception:  # noqa: BLE001
    pass

try:
    from app.routers.wp_surfaced_i import CATALOG as _I_CATALOG

    _merge(_I_CATALOG)
except Exception:  # noqa: BLE001
    pass

try:
    from app.routers.wp_surfaced_j import CATALOG as _J_CATALOG

    _merge(_J_CATALOG)
except Exception:  # noqa: BLE001
    pass

try:
    from app.routers.wp_surfaced_n import CATALOG as _N_CATALOG

    _merge(_N_CATALOG)
except Exception:  # noqa: BLE001
    pass
