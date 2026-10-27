"""路由模块挂载守卫（spec attachment-inline-preview 走查发现）

E1-10 账户清单 / E1-11 账户承诺书 / E1-18 征信报告三个识别端点 2026-07 建好后一直没登记进
``router_registry``，前端一调就 404，三个「OCR」按钮恒报识别失败（附件也建不出来，小眼睛无从显示）。
既有的 ``test_router_registry_completeness.py`` 跳过 ``_`` 开头的模块（``wp_render_strategies/_*.py`` 全在此列），
所以没抓到；本守卫补上这块，并以「有没有路由在服务」为准（被统一实现顶替的旧模块不算缺失）。

判据：
  A. ``app.routers.**`` 里定义了 ``router`` 的模块，每条路由（方法 + 路径）都要有应用路由在服务：
     端点函数被挂上（身份口径：include_router 复制路由对象但端点函数是同一个，不受挂载前缀影响），
     或同方法同路径（原样 / 加 ``/api``）已由别的模块提供（被统一实现顶替的旧模块）。
     都不满足 = 调用即 404。
  B. 既有的无人服务路由冻结在 ``_KNOWN_UNSERVED``（只许删）：条目须仍然无人服务（修好了就删）。
  C. 三个 E1 识别端点必须由各自模块的端点函数服务（身份口径），不许被同路径的别的实现顶替后悄悄漂走。
  D. 扫描器自检：合成一个没挂上的路由模块必须被抓到；扫描面不塌缩。
"""
from __future__ import annotations

import importlib
import pkgutil
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

# 冻结：既有的无人服务路由（与附件无关的各循环导入导出端点，前端调用同样 404）。
# 归属各循环导入导出收口，只许删不许加；修好一条（登记进 router_registry 或改走统一实现）即删一条。
_KNOWN_UNSERVED: dict[tuple[str, str], str] = {
    ("POST", "/api/workpapers/{wp_id}/h5/export-template"): "H5 导入导出模块未登记",
    ("POST", "/api/workpapers/{wp_id}/h5/export-data"): "H5 导入导出模块未登记",
    ("POST", "/api/workpapers/{wp_id}/h5/import-data"): "H5 导入导出模块未登记",
    ("POST", "/api/workpapers/{wp_id}/h7/export-template"): "H7 只有导入由 h7_biological_assets 提供",
    ("POST", "/api/workpapers/{wp_id}/h7/export-data"): "H7 只有导入由 h7_biological_assets 提供",
    ("POST", "/api/workpapers/{wp_id}/h9/export-template"): "H9 导入导出模块未登记",
    ("POST", "/api/workpapers/{wp_id}/h9/export-data"): "H9 导入导出模块未登记",
    ("POST", "/api/workpapers/{wp_id}/h9/import-data"): "H9 导入导出模块未登记",
    ("POST", "/api/workpapers/{wp_id}/l1/export-template"): "L1 只有导入由 l1_short_term_loans 提供",
    ("POST", "/api/workpapers/{wp_id}/l1/export-data"): "L1 只有导入由 l1_short_term_loans 提供",
    ("POST", "/api/workpapers/{wp_id}/l3/export-template"): "L3 只有导入由 l3_long_term_loans 提供",
    ("POST", "/api/workpapers/{wp_id}/l3/export-data"): "L3 只有导入由 l3_long_term_loans 提供",
    ("POST", "/api/workpapers/{wp_id}/l5/export-template"): "L5 只有导入由 l5_long_term_payables 提供",
    ("POST", "/api/workpapers/{wp_id}/l5/export-data"): "L5 只有导入由 l5_long_term_payables 提供",
    ("POST", "/api/workpapers/{wp_id}/l7/export-template"): "L7 导入导出模块未登记",
    ("POST", "/api/workpapers/{wp_id}/l7/export-data"): "L7 导入导出模块未登记",
    ("POST", "/api/workpapers/{wp_id}/l7/import-data"): "L7 导入导出模块未登记",
    ("POST", "/api/workpapers/{wp_id}/l8/export-template"): "L8 导入导出模块未登记",
    ("POST", "/api/workpapers/{wp_id}/l8/export-data"): "L8 导入导出模块未登记",
    ("POST", "/api/workpapers/{wp_id}/l8/import-data"): "L8 导入导出模块未登记",
    ("POST", "/api/workpapers/{wp_id}/n4/export-template"): "N4 导入导出模块未登记（前端另走 /api/n4/…）",
    ("POST", "/api/workpapers/{wp_id}/n4/export-data"): "N4 导入导出模块未登记（前端另走 /api/n4/…）",
    ("POST", "/api/workpapers/{wp_id}/n4/import-data"): "N4 导入导出模块未登记（前端另走 /api/n4/…）",
}

_E1_OCR = {
    "app.routers.wp_render_strategies._e1_account_list_ocr": ("POST", "/api/workpapers/{wp_id}/e1/account-list-ocr"),
    "app.routers.wp_render_strategies._e1_commit_ocr": ("POST", "/api/workpapers/{wp_id}/e1/commit-ocr"),
    "app.routers.wp_render_strategies._e1_credit_ocr": ("POST", "/api/workpapers/{wp_id}/e1/credit-ocr"),
}


def _app_index(app: FastAPI) -> tuple[set[int], set[tuple[str, str]]]:
    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    return {id(r.endpoint) for r in routes}, {(m, r.path) for r in routes for m in r.methods}


def unserved_routes(app: FastAPI, modules: list[tuple[str, object]]) -> list[tuple[str, str, str]]:
    """（方法, 路径, 模块名）：端点没挂上、同方法同路径（原样 / 加 /api）也没有别的路由在服务。"""
    endpoint_ids, served = _app_index(app)
    out: list[tuple[str, str, str]] = []
    for name, mod in modules:
        router = getattr(mod, "router", None)
        if router is None or not hasattr(router, "routes"):
            continue
        for r in router.routes:
            if not isinstance(r, APIRoute) or id(r.endpoint) in endpoint_ids:
                continue
            for m in sorted(r.methods):
                if (m, r.path) not in served and (m, "/api" + r.path) not in served:
                    out.append((m, r.path, name))
    return out


def _router_modules() -> list[tuple[str, object]]:
    import app.routers as routers_pkg

    return [
        (info.name, importlib.import_module(info.name))
        for info in pkgutil.walk_packages(routers_pkg.__path__, prefix="app.routers.")
    ]


def test_every_router_route_is_served_except_frozen_debt() -> None:
    from app.main import app

    modules = _router_modules()
    assert len(modules) >= 300, f"扫描面塌缩：只扫到 {len(modules)} 个路由模块"
    found = unserved_routes(app, modules)
    new = [f"{m} {p}（{name}）" for m, p, name in found if (m, p) not in _KNOWN_UNSERVED]
    assert not new, "以下路由没挂到应用上（前端调用即 404），请登记进 app/router_registry：\n" + "\n".join(new)
    still = {(m, p) for m, p, _ in found}
    stale = [f"{m} {p}" for (m, p) in _KNOWN_UNSERVED if (m, p) not in still]
    assert not stale, "以下冻结条目已经有路由在服务，请从 _KNOWN_UNSERVED 删除：\n" + "\n".join(stale)


def test_e1_ocr_endpoints_are_served_by_their_own_modules() -> None:
    from app.main import app

    endpoint_ids, _ = _app_index(app)
    problems = []
    for name, (method, path) in _E1_OCR.items():
        router = importlib.import_module(name).router
        own = [r for r in router.routes if isinstance(r, APIRoute) and r.path == path and method in r.methods]
        if len(own) != 1:
            problems.append(f"{name} 里找不到 {method} {path}")
        elif id(own[0].endpoint) not in endpoint_ids:
            problems.append(f"{method} {path} 没由 {name} 的端点函数服务")
    assert not problems, "\n".join(problems)


def test_scanner_catches_unmounted_module_and_accepts_mounted_or_superseded() -> None:
    mounted = APIRouter()
    superseded = APIRouter()
    orphan = APIRouter()

    @mounted.post("/api/workpapers/{wp_id}/x/ok")
    async def ok() -> dict:  # pragma: no cover - 不调用
        return {}

    @superseded.post("/x/same-path")
    async def old_impl() -> dict:  # pragma: no cover
        return {}

    @orphan.post("/api/workpapers/{wp_id}/x/orphan-ocr")
    async def orphan_ocr() -> dict:  # pragma: no cover
        return {}

    app = FastAPI()
    app.include_router(mounted, prefix="")
    replacement = APIRouter()

    @replacement.post("/api/x/same-path")
    async def new_impl() -> dict:  # pragma: no cover
        return {}

    app.include_router(replacement)
    mods = [(n, SimpleNamespace(router=r)) for n, r in (("m.ok", mounted), ("m.old", superseded), ("m.orphan", orphan))]
    assert unserved_routes(app, mods) == [("POST", "/api/workpapers/{wp_id}/x/orphan-ocr", "m.orphan")]
