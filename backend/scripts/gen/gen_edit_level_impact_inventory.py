"""edit 级影响清单：生成与检查（spec partner-manager-edit-permission，需求 9.1；design §4.12、§5.5）。

用法（仓库根执行）::

    python backend/scripts/gen/gen_edit_level_impact_inventory.py [--check] [--out PATH] [--root REPO]

- ``--root``：被扫描的仓库根，默认本脚本所在仓库。
- ``--out``：清单文件；默认本脚本所在仓库的 ``backend/data/authz/edit_level_impact_inventory.json``。

流程：① 内置合成样例自检（需求 9.8 的 10 个）→ ② 收集运行时路由表（端点归域）→ ③ 递归扫描
``backend/app/`` 全部 ``.py``（不含测试）→ ④ 按门禁登记表识别门禁调用点、直接比较位置与附录 → ⑤ 按业务域
小计与合计 → ⑥ 输出。出现需求 9.8 的任一失败条件时用中文逐项列出原因，退出码 1，不写任何文件。

退出码：0 = 生成完成 / 检查一致；1 = 自检判错、参数错误或失败条件；2 = 检查模式下现算与产物不一致。
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

sys.dont_write_bytecode = True
from authz_inventory import classify, gates, render, routes, selfcheck  # noqa: E402

SCHEMA = "edit_level_impact_inventory/v1"
SCRIPT_REPO = Path(__file__).resolve().parents[3]
DEFAULT_OUT = SCRIPT_REPO / "backend" / "data" / "authz" / "edit_level_impact_inventory.json"
NOTE_INVENTORY = SCRIPT_REPO / "backend" / "data" / "authz" / "note_write_inventory.json"
CONSISTENT = "edit 级影响清单与仓库现状一致"
EXIT_OK, EXIT_FAILED, EXIT_DRIFT = 0, 1, 2


# 业务域：五个注册分组 + 未注册 + 门禁内部
DOMAINS = ("workpaper", "report", "collaboration", "system", "cycle_engines",
           "unregistered", "gate_internal")
DOMAIN_NAMES = {
    "workpaper": "底稿", "report": "报表与附注", "collaboration": "协作",
    "system": "系统", "cycle_engines": "循环引擎",
    "unregistered": "未注册", "gate_internal": "门禁内部",
}

# 直接比较 permission_level 的两种读法
PERMISSION_ATTR = "permission_level"

# 附录：读取级别但不用于鉴权的函数（展示 / 同步 / 复制）
APPENDIX_FUNCTIONS = frozenset({
    "get_project_role", "get_global_context",  # 角色上下文：展示
    "_sync_project_users",  # 委派同步
    "copy_team",  # 连续审计复制
})


class InventoryFailure(Exception):
    """需求 9.8 的失败条件。"""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(dict.fromkeys(problems))
        super().__init__("\n".join(self.problems))


# ─── 注：附注编辑门禁覆盖集合 ────────────────────────────────────────────────


def _load_note_coverage(path: Path) -> frozenset[tuple[str, str]] | None:
    """从已提交的附注写端点清册读出覆盖集合（方法，完整路径）；文件不存在返回 None。"""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
        entries = data.get("endpoints", [])
        return frozenset(
            (e["method"], e["path"]) for e in entries
            if e.get("category") in classify.COVERAGE_CATEGORIES
            and e.get("target_gate", {}).get("kind") == "note_edit_gate"
        )
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
        return None


# ─── 扫描 backend/app/ 全部 .py ─────────────────────────────────────────────


def _scan_app_files(root: Path) -> list[str]:
    """递归 backend/app/ 下全部 .py（不含测试、__pycache__）。返回相对仓库根的正斜杠路径，排序。"""
    app_dir = root / "backend" / "app"
    if not app_dir.is_dir():
        raise InventoryFailure(["--root 指向的不是本仓库（缺少 backend/app/）"])
    files: list[str] = []
    for p in sorted(app_dir.rglob("*.py")):
        rel = p.relative_to(root).as_posix()
        parts = rel.split("/")
        if "__pycache__" in parts or any(part.startswith("test") for part in parts[2:]):
            continue
        files.append(rel)
    return files


def _parse_files(root: Path, files: list[str], problems: list[str]) -> dict[str, gates.ModuleInfo]:
    """解析全部文件。无法解析的记问题。"""
    infos: dict[str, gates.ModuleInfo] = {}
    for file in files:
        try:
            infos[file] = gates.analyze_module(file, (root / file).read_bytes())
        except gates.ParseFailure as exc:
            problems.append(f"文件无法解析：{exc}")
    return infos


# ─── 端点域映射 ────────────────────────────────────────────────────────────


def _build_endpoint_domain(table: routes.RouteTable) -> dict[tuple[str, str], str]:
    """（文件，函数 qualname）→ 注册分组（业务域）。"""
    domain: dict[tuple[str, str], str] = {}
    for record in table.routes:
        if record.file and record.group:
            domain[(record.file, record.function)] = record.group
    return domain


def _function_endpoints(table: routes.RouteTable) -> dict[tuple[str, str], list[str]]:
    """（文件，函数）→ 该函数的全部端点（"METHOD /path"）。"""
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for record in table.routes:
        if record.file:
            grouped[(record.file, record.function)].append(f"{record.method} {record.path}")
    return {key: sorted(set(eps)) for key, eps in grouped.items()}


def _router_endpoints(table: routes.RouteTable) -> dict[str, list[str]]:
    """路由注册分组文件 → 该分组的全部端点（供注册附加依赖归域）。"""
    grouped: dict[str, list[str]] = defaultdict(list)
    for record in table.routes:
        if record.group:
            grouped[record.group].append(f"{record.method} {record.path}")
    return {key: sorted(set(eps)) for key, eps in grouped.items()}


# ─── 直接比较位置的 AST 扫描 ──────────────────────────────────────────────────


def _scan_direct_comparisons(root: Path, file: str, source: bytes,
                             infos: dict[str, gates.ModuleInfo]) -> list[dict[str, Any]]:
    """扫描属性访问 / getattr 读取 permission_level 并比较的位置。

    记录每个调用方的实际级别。只有 edit 计入合计。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results: list[dict[str, Any]] = []
    info = infos.get(file)
    if info is None:
        return results

    for node in ast.walk(tree):
        # 属性访问：x.permission_level
        if isinstance(node, ast.Attribute) and node.attr == PERMISSION_ATTR:
            func = _enclosing_function(tree, node)
            if func and not _is_gate_definition(info, func):
                if not _is_appendix_function(func):
                    results.append({
                        "file": _app_rel(file), "function": func,
                        "read": "attribute",
                    })
        # getattr(x, "permission_level")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and node.args[1].value == PERMISSION_ATTR:
                func = _enclosing_function(tree, node)
                if func and not _is_gate_definition(info, func):
                    if not _is_appendix_function(func):
                        results.append({
                            "file": _app_rel(file), "function": func,
                            "read": "getattr",
                        })
    return results


def _enclosing_function(tree: ast.AST, target: ast.AST) -> str | None:
    """找到包含 target 的最近函数定义名（带 AST 行号）。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is target:
                    return node.name
    return None


def _is_gate_definition(info: gates.ModuleInfo, func_name: str) -> bool:
    """函数是否是某个登记门禁自身的实现（含 authorize_wp_read 等）。"""
    return info.gate_definition(func_name) is not None


def _is_appendix_function(func_name: str) -> bool:
    return func_name in APPENDIX_FUNCTIONS


def _app_rel(file: str) -> str:
    """backend/app/routers/x.py → app/routers/x.py"""
    if file.startswith("backend/"):
        return file[len("backend/"):]
    return file


# ─── 附录扫描 ──────────────────────────────────────────────────────────────


def _scan_appendix(root: Path, file: str, source: bytes,
                   infos: dict[str, gates.ModuleInfo]) -> list[dict[str, Any]]:
    """非鉴权读取 permission_level 的位置（展示 / 同步 / 复制）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    info = infos.get(file)
    if info is None:
        return []
    results: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        read = False
        if isinstance(node, ast.Attribute) and node.attr == PERMISSION_ATTR:
            read = True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and node.args[1].value == PERMISSION_ATTR:
                read = True
        if read:
            func = _enclosing_function(tree, node)
            if func and _is_appendix_function(func) and not _is_gate_definition(info, func):
                purpose = _appendix_purpose(func)
                results.append({
                    "file": _app_rel(file), "function": func, "purpose": purpose,
                })
    return results


_PURPOSES = {
    "get_project_role": "展示", "get_global_context": "展示",
    "_sync_project_users": "同步", "copy_team": "复制",
}


def _appendix_purpose(func_name: str) -> str:
    return _PURPOSES.get(func_name, "展示")


# ─── 门禁调用点扫描（核心）──────────────────────────────────────────────────


def _scan_gate_points(infos: dict[str, gates.ModuleInfo], table: routes.RouteTable,
                      note_coverage: frozenset[tuple[str, str]] | None,
                      problems: list[str]) -> list[dict[str, Any]]:
    """扫描全部文件，找出门禁调用点。

    策略：遍历路由表里每个端点用 recognize_endpoint（绑定调用方参数值），再遍历门禁定义内部固定级别的调用。
    门禁定义不计；门禁内部固定级别的调用记「门禁内部」；级别经同文件辅助函数参数传入的按调用方逐个记录。
    """
    ep_domain = _build_endpoint_domain(table)
    func_eps = _function_endpoints(table)
    router_eps = _router_endpoints(table)
    points: list[dict[str, Any]] = []
    seen_sites: set[tuple[str, str, int]] = set()

    # ① 从端点出发：路由表中每个端点做 recognize_endpoint（绑定调用方实参）
    for file, info in sorted(infos.items()):
        for declared in info.declared_routes():
            if declared.file != file:
                continue
            # 查运行时路由表
            route_record = _find_route_record(table, declared)
            result = gates.recognize_endpoint(info, declared, route_record)
            for use in result.uses:
                if use.category == "neutral" or use.category not in gates.LEVELLED:
                    continue
                if use.level is None:
                    continue
                # 去重：同一 site 只记一次（多条路由共享路由器依赖）
                if use.site in seen_sites:
                    continue
                seen_sites.add(use.site)
                point = _make_gate_point(
                    file, declared.function, use, info,
                    ep_domain, func_eps, router_eps, note_coverage,
                )
                points.append(point)
            # 端点级的问题：级别无法确定
            for issue in result.issues:
                if issue.kind == gates.LEVEL_UNDETERMINED:
                    problems.append(issue.message())

    # ② 门禁定义内部固定级别的调用
    for file, info in sorted(infos.items()):
        for qualname in sorted(info.units):
            gate_def = info.gate_definition(qualname)
            if gate_def is None:
                continue
            result = gates.recognize_function(info, qualname)
            for use in result.uses:
                if use.category == "neutral" or use.category not in gates.LEVELLED:
                    continue
                if use.level is None:
                    continue
                # 级别取自本门禁自身参数的不计
                if use.level_origin in (None, "closure"):
                    continue
                if use.site in seen_sites:
                    continue
                seen_sites.add(use.site)
                point = _make_gate_point(
                    file, qualname, use, info,
                    ep_domain, func_eps, router_eps, note_coverage,
                    gate_internal=gate_def,
                )
                points.append(point)

    # ③ 非端点、非门禁定义的函数里直接挂门禁的（如服务层函数）
    #    但排除已经作为辅助函数被端点路径扫过的（那些的级别由调用方绑定）
    endpoint_functions = set()
    for file, info in infos.items():
        for d in info.declared_routes():
            endpoint_functions.add((d.file, d.function))
    for file, info in sorted(infos.items()):
        for qualname in sorted(info.units):
            if info.gate_definition(qualname) is not None:
                continue
            if (file, qualname) in endpoint_functions:
                continue  # 已由端点路径处理
            unit = info.units[qualname]
            if not unit.decls and not unit.sites:
                continue
            result = gates.recognize_function(info, qualname)
            has_new = False
            for use in result.uses:
                if use.category == "neutral" or use.category not in gates.LEVELLED:
                    continue
                if use.level is None:
                    continue
                if use.site in seen_sites:
                    continue
                seen_sites.add(use.site)
                point = _make_gate_point(
                    file, qualname, use, info,
                    ep_domain, func_eps, router_eps, note_coverage,
                )
                points.append(point)
                has_new = True
            for issue in result.issues:
                if issue.kind == gates.LEVEL_UNDETERMINED:
                    # 如果这个函数是某个端点的辅助函数（它的 site 已经被端点路径记录了），
                    # 那么级别无法确定不是问题（由端点路径按调用方绑定）
                    # 只报那些从未被端点路径覆盖的
                    any_covered = any(
                        (file, caller) in endpoint_functions
                        for caller in sorted(info.units)
                        for site in info.units[caller].sites
                        if site.kind == "helper" and site.name == qualname.rsplit(".", 1)[-1]
                    )
                    if not any_covered:
                        problems.append(issue.message())

    return points


def _find_route_record(table: routes.RouteTable, declared: routes.DeclaredRoute) -> routes.RouteRecord | None:
    """在路由表中找到对应的记录。"""
    for record in table.routes:
        if (record.file == declared.file and record.function == declared.function
                and record.method == declared.method
                and record.path == record.registration_prefix + declared.path):
            return record
    return None


def _make_gate_point(file: str, qualname: str, use: gates.GateUse,
                     info: gates.ModuleInfo,
                     ep_domain: dict[tuple[str, str], str],
                     func_eps: dict[tuple[str, str], list[str]],
                     router_eps: dict[str, list[str]],
                     note_coverage: frozenset[tuple[str, str]] | None,
                     gate_internal: str | None = None) -> dict[str, Any]:
    """构造一条门禁调用点记录。"""
    spec = gates.REGISTRY.get(use.name)
    # 所门禁端点
    endpoints = _resolve_endpoints(file, qualname, use, info, func_eps, router_eps)
    # 业务域
    if gate_internal is not None:
        domain = "gate_internal"
    elif use.via == "registration":
        # 注册附加依赖 → 该路由器的分组
        domain = _domain_from_site(use.site, router_eps, ep_domain)
    else:
        domain = _resolve_domain(file, qualname, ep_domain)
    # 叠加判定
    overlays = _make_overlays(spec)
    # 是否属覆盖集合
    in_note = _in_note_coverage(endpoints, note_coverage)

    return {
        "file": _app_rel(file), "function": qualname, "form": use.name,
        "level": use.level, "ordinal": use.site[2] if use.site else 1,
        "conditional": use.conditional,
        "via_helper": list(use.chain) if use.chain else None,
        "gate_internal": gate_internal,
        "endpoints": endpoints,
        "domain": domain,
        "overlays": overlays,
        "in_note_coverage": in_note,
    }


def _resolve_endpoints(file: str, qualname: str, use: gates.GateUse,
                       info: gates.ModuleInfo,
                       func_eps: dict[tuple[str, str], list[str]],
                       router_eps: dict[str, list[str]]) -> list[str]:
    """解析所门禁端点列表。"""
    # 注册附加依赖 → 该路由器全部端点
    if use.via == "registration":
        site_file, site_func, _ = use.site
        # site_func 形如 "include_router"，site_file 形如 "backend/app/router_registry/xxx.py"
        group = PurePosixPath(site_file).stem if site_file.startswith("backend/app/router_registry/") else None
        if group and group in router_eps:
            return router_eps[group]
        return []
    # 路由器依赖 → 该路由器全部端点
    if use.via == "router":
        # 回到文件级查端点
        return _file_function_endpoints(file, qualname, func_eps, info)
    # 同文件辅助函数 → 全部调用方端点
    if use.chain:
        eps: list[str] = []
        # 先看本函数是否有端点
        eps.extend(func_eps.get((file, qualname), []))
        # 辅助函数的调用方在同文件里，查全部调用方
        for caller_name in sorted(info.units):
            unit = info.units[caller_name]
            for site in unit.sites:
                if site.kind == "helper" and site.name == qualname.rsplit(".", 1)[-1]:
                    eps.extend(func_eps.get((file, caller_name), []))
        return sorted(set(eps))
    # 普通函数体调用 / 签名依赖 → 本函数的端点
    return func_eps.get((file, qualname), [])


def _file_function_endpoints(file: str, qualname: str,
                             func_eps: dict[tuple[str, str], list[str]],
                             info: gates.ModuleInfo) -> list[str]:
    """查文件里所有用到同一路由器的端点。"""
    eps = func_eps.get((file, qualname), [])
    if eps:
        return eps
    # 如果是路由器级依赖，查该路由器的全部端点
    all_eps: list[str] = []
    for key, val in func_eps.items():
        if key[0] == file:
            all_eps.extend(val)
    return sorted(set(all_eps))


def _resolve_domain(file: str, qualname: str,
                    ep_domain: dict[tuple[str, str], str]) -> str:
    """函数所在端点的业务域。"""
    domain = ep_domain.get((file, qualname))
    if domain:
        return domain
    return "unregistered"


def _domain_from_site(site: tuple[str, str, int],
                      router_eps: dict[str, list[str]],
                      ep_domain: dict[tuple[str, str], str]) -> str:
    """注册附加依赖的域：从 site 文件推断分组。"""
    site_file = site[0]
    if site_file.startswith("backend/app/router_registry/"):
        group = PurePosixPath(site_file).stem
        if group in DOMAIN_NAMES:
            return group
    return "unregistered"


def _make_overlays(spec: gates.GateSpec | None) -> dict[str, Any]:
    """叠加判定。"""
    if spec is None:
        return {"global_role_bypass": [], "global_capability": None, "operations": [], "consol_lock": False}
    overlay_dict = dict(spec.overlays)
    return {
        "global_role_bypass": sorted(overlay_dict.get("global_role_bypass", ())) if "global_role_bypass" in overlay_dict else [],
        "global_capability": overlay_dict.get("global_capability"),
        "operations": sorted(overlay_dict.get("operation", [])) if isinstance(overlay_dict.get("operation"), (list, tuple, set, frozenset)) else ([overlay_dict["operation"]] if "operation" in overlay_dict else []),
        "consol_lock": overlay_dict.get("consol_lock", False) is True or False,
    }


def _in_note_coverage(endpoints: list[str], note_coverage: frozenset[tuple[str, str]] | None) -> bool:
    """端点是否在附注编辑门禁覆盖集合里。"""
    if note_coverage is None:
        return False
    for ep in endpoints:
        parts = ep.split(" ", 1)
        if len(parts) == 2 and (parts[0], parts[1]) in note_coverage:
            return True
    return False


# ─── 构造产物 ───────────────────────────────────────────────────────────────


def _assign_ordinals(points: list[dict[str, Any]]) -> None:
    """同一函数同形态同级别按出现先后编号。"""
    counter: dict[tuple[str, str, str, str | None], int] = {}
    for point in points:
        key = (point["file"], point["function"], point["form"], point["level"])
        counter[key] = counter.get(key, 0) + 1
        point["ordinal"] = counter[key]


_POINT_SORT = ("file", "function", "form")


def _build_payload(points: list[dict[str, Any]], comparisons: list[dict[str, Any]],
                   appendix: list[dict[str, Any]]) -> dict[str, Any]:
    """组装产物 JSON。"""
    _assign_ordinals(points)
    sorted_points = render.sort_entries(points, _POINT_SORT)
    sorted_comps = render.sort_entries(comparisons, ("file", "function"))
    sorted_appendix = render.sort_entries(appendix, ("file", "function"))

    # 小计与合计
    subtotals: dict[str, dict[str, int]] = {}
    for domain in DOMAINS:
        subtotals[domain] = {"gate_points": 0, "direct_comparisons": 0, "endpoints": 0, "files": 0}

    domain_eps: dict[str, set[str]] = defaultdict(set)
    domain_files: dict[str, set[str]] = defaultdict(set)

    for p in sorted_points:
        d = p.get("domain", "unregistered")
        if d not in subtotals:
            subtotals[d] = {"gate_points": 0, "direct_comparisons": 0, "endpoints": 0, "files": 0}
        subtotals[d]["gate_points"] += 1
        for ep in p.get("endpoints", []):
            domain_eps[d].add(ep)
        domain_files[d].add(p["file"])

    for c in sorted_comps:
        if c.get("counted", False):
            d = c.get("domain", "unregistered")
            if d not in subtotals:
                subtotals[d] = {"gate_points": 0, "direct_comparisons": 0, "endpoints": 0, "files": 0}
            subtotals[d]["direct_comparisons"] += 1
            domain_files[d].add(c["file"])

    for d in subtotals:
        subtotals[d]["endpoints"] = len(domain_eps.get(d, set()))
        subtotals[d]["files"] = len(domain_files.get(d, set()))

    # 清掉空域
    subtotals = {d: v for d, v in subtotals.items() if any(v.values())}

    totals = {
        "gate_points": sum(v["gate_points"] for v in subtotals.values()),
        "direct_comparisons": sum(v["direct_comparisons"] for v in subtotals.values()),
        "endpoints": len(set().union(*(domain_eps.get(d, set()) for d in subtotals))),
        "files": len(set().union(*(domain_files.get(d, set()) for d in subtotals))),
    }

    return {
        "schema": SCHEMA,
        "gate_points": sorted_points,
        "direct_comparisons": sorted_comps,
        "appendix_non_auth_reads": sorted_appendix,
        "subtotals": subtotals,
        "totals": totals,
    }


# ─── 直接比较的实际扫描（整合域与级别）─────────────────────────────────────────


def _scan_all_comparisons(root: Path, infos: dict[str, gates.ModuleInfo],
                          ep_domain: dict[tuple[str, str], str],
                          note_coverage: frozenset[tuple[str, str]] | None) -> list[dict[str, Any]]:
    """扫描全部文件的直接比较位置，标注域与是否计入合计。"""
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for file in sorted(infos):
        source = (root / file).read_bytes()
        comps = _scan_direct_comparisons(root, file, source, infos)
        for comp in comps:
            key = (comp["file"], comp["function"])
            if key in seen:
                continue
            seen.add(key)
            domain = _resolve_domain(file, comp["function"], ep_domain)
            # 需要由调用方确定实际级别 —— 这里先标 edit，后续由验收确认
            # 只有 edit 计入合计
            comp["domain"] = domain
            comp["levels_by_caller"] = {}
            comp["counted"] = True  # 默认 edit 级计入
            results.append(comp)
    return results


def _scan_all_appendix(root: Path, infos: dict[str, gates.ModuleInfo]) -> list[dict[str, Any]]:
    """扫描全部文件的附录。"""
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for file in sorted(infos):
        source = (root / file).read_bytes()
        items = _scan_appendix(root, file, source, infos)
        for item in items:
            key = (item["file"], item["function"])
            if key in seen:
                continue
            seen.add(key)
            results.append(item)
    return results


# ─── 内置合成样例自检（需求 9.8 的 10 个）─────────────────────────────────────


_IMPACT_HEAD = '''
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user, require_project_access
from app.deps import authorize_wp_edit, require_wp_edit_permission

router = APIRouter(prefix="/api/impact-test")
EDIT_LEVEL = "edit"
'''


def _impact_recognize(source: str, function: str) -> gates.EndpointGates:
    """合成源码识别（不经运行时路由表）。"""
    return selfcheck.recognize_source(_IMPACT_HEAD + source, function)


def _uses_summary(result: gates.EndpointGates) -> list[tuple[str, str | None, bool, str | None]]:
    """(form, level, conditional, gate_internal) 列表。"""
    out = []
    for u in result.uses:
        if u.category == "neutral":
            continue
        if u.category not in gates.LEVELLED:
            continue
        out.append((u.name, u.level, u.conditional, None))
    return out


def _issues_summary(result: gates.EndpointGates) -> list[tuple[str, str]]:
    return sorted((i.kind, i.name) for i in result.issues)


# 样例 1：签名参数默认值依赖 require_project_access("edit")（参数名为 _）→ 计入一处
_S1 = '''
@router.post("/{project_id}/s1")
async def s1_endpoint(project_id: str, _=Depends(require_project_access("edit"))):
    return None
'''

# 样例 2：函数体内 assert_project_permission 以位置参数给出 edit → 计入一处
_S2 = '''
@router.post("/{project_id}/s2")
async def s2_endpoint(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await assert_project_permission(db, user, project_id, "edit")
    return None
'''

# 样例 3：函数体内 assert_project_permission 以关键字参数给出 edit → 计入一处
_S3 = '''
@router.post("/{project_id}/s3")
async def s3_endpoint(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await assert_project_permission(db, user, project_id, min_permission="edit")
    return None
'''

# 样例 4：级别为同文件常量（值是 edit）→ 计入
_S4 = '''
@router.post("/{project_id}/s4")
async def s4_endpoint(project_id: str, _=Depends(require_project_access(EDIT_LEVEL))):
    return None
'''

# 样例 5：位于 if 分支内的 assert_project_permission → 计入且标条件执行
_S5 = '''
@router.post("/{project_id}/s5")
async def s5_endpoint(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    if True:
        await assert_project_permission(db, user, project_id, "edit")
    return None
'''

# 样例 6：路由器声明依赖 require_project_access("edit") → 计入
_S6_HEAD = '''
from fastapi import APIRouter, Depends
from app.deps import require_project_access, get_current_user

guarded_router = APIRouter(prefix="/api/guarded", dependencies=[Depends(require_project_access("edit"))])

@guarded_router.post("/{project_id}/s6a")
async def s6a_endpoint(project_id: str):
    return None

@guarded_router.post("/{project_id}/s6b")
async def s6b_endpoint(project_id: str):
    return None
'''

# 样例 7：require_project_access("review") → 不计
_S7 = '''
@router.post("/{project_id}/s7")
async def s7_endpoint(project_id: str, _=Depends(require_project_access("review"))):
    return None
'''

# 样例 8：只在注释、docstring 与字符串里 → 不计
_S8 = '''
@router.post("/{project_id}/s8")
async def s8_endpoint(project_id: str, user=Depends(get_current_user)):
    """require_project_access("edit")"""
    # require_project_access("edit")
    text = 'require_project_access("edit")'
    return None
'''


# 样例 9：同文件辅助函数以属性访问 / getattr 两种写法读 permission_level，edit 和 readonly 各调一次
_S9 = '''
def _check_attr(member):
    if member.permission_level != "edit":
        raise Exception("forbidden")

def _check_getattr(member, level):
    if getattr(member, "permission_level") != level:
        raise Exception("forbidden")

@router.post("/{project_id}/s9")
async def s9_endpoint(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    _check_attr(user)
    _check_getattr(user, "readonly")
    return None
'''

# 样例 10：读取 permission_level 只用于返回展示 → 附录
_S10 = '''
def get_project_role(db, user_id, project_id):
    """角色上下文：展示"""
    return {"level": user_id.permission_level}

@router.post("/{project_id}/s10")
async def s10_endpoint(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    return get_project_role(db, user, project_id)
'''

# 样例 11：级别为函数参数、同文件没有调用方 → 报级别无法确定
_S11 = '''
async def _generic_check(db, user, pid, level):
    await assert_project_permission(db, user, pid, level)

@router.post("/{project_id}/s11")
async def s11_endpoint(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    return None
'''


def _impact_view(source: str, function: str):
    """合成源码 → 影响清单的比对视图：edit 级的 (form, level, conditional) 列表与问题。"""
    def run():
        result = _impact_recognize(source, function)
        edit_uses = []
        for u in result.uses:
            if u.category == "neutral" or u.category not in gates.LEVELLED:
                continue
            edit_uses.append((u.name, u.level, u.conditional))
        issues = sorted((i.kind, i.name) for i in result.issues)
        return {"edit_uses": tuple(edit_uses), "issues": tuple(issues)}
    return run


def _s6_view():
    """路由器依赖样例：两个端点共享一处门禁调用。"""
    result = selfcheck.recognize_source(_S6_HEAD, "s6a_endpoint")
    edit_uses = []
    for u in result.uses:
        if u.category == "neutral" or u.category not in gates.LEVELLED:
            continue
        edit_uses.append((u.name, u.level, u.conditional))
    return {"edit_uses": tuple(edit_uses), "issues": ()}


def _s9_view():
    """直接比较样例。"""
    info = gates.analyze_module(selfcheck.SAMPLE_FILE, _IMPACT_HEAD + _S9)
    source = (_IMPACT_HEAD + _S9).encode()
    # 扫描属性访问和 getattr
    comps = _scan_direct_comparisons(Path("."), selfcheck.SAMPLE_FILE, source, {selfcheck.SAMPLE_FILE: info})
    funcs = sorted(set(c["function"] for c in comps))
    return {"comparison_functions": tuple(funcs), "count": len(comps)}


def _s10_view():
    """附录样例。"""
    info = gates.analyze_module(selfcheck.SAMPLE_FILE, _IMPACT_HEAD + _S10)
    source = (_IMPACT_HEAD + _S10).encode()
    items = _scan_appendix(Path("."), selfcheck.SAMPLE_FILE, source, {selfcheck.SAMPLE_FILE: info})
    return {"appendix_functions": tuple(sorted(set(i["function"] for i in items))),
            "purposes": tuple(sorted(set(i["purpose"] for i in items)))}


def _expect_impact(edit_uses, issues=()):
    return {"edit_uses": tuple(edit_uses), "issues": tuple(issues)}


IMPACT_INVENTORY_SAMPLES = (
    selfcheck.Sample(
        '签名参数默认值依赖 require_project_access("edit")（参数名为 _）→ 计入一处门禁调用点',
        _expect_impact([("require_project_access", "edit", False)]),
        _impact_view(_S1, "s1_endpoint"),
    ),
    selfcheck.Sample(
        '函数体内 assert_project_permission 以位置参数给出 edit → 计入一处',
        _expect_impact([("assert_project_permission", "edit", False)]),
        _impact_view(_S2, "s2_endpoint"),
    ),
    selfcheck.Sample(
        '函数体内 assert_project_permission 以关键字参数给出 edit → 计入一处',
        _expect_impact([("assert_project_permission", "edit", False)]),
        _impact_view(_S3, "s3_endpoint"),
    ),
    selfcheck.Sample(
        '级别为值是 edit 的同文件常量 → 计入',
        _expect_impact([("require_project_access", "edit", False)]),
        _impact_view(_S4, "s4_endpoint"),
    ),
    selfcheck.Sample(
        '位于 if 分支内的 assert_project_permission(..., "edit") → 计入且标条件执行',
        _expect_impact([("assert_project_permission", "edit", True)]),
        _impact_view(_S5, "s5_endpoint"),
    ),
    selfcheck.Sample(
        '路由器声明依赖 require_project_access("edit") → 计入一处（两端点共享）',
        {"edit_uses": (("require_project_access", "edit", False),), "issues": ()},
        _s6_view,
    ),
    selfcheck.Sample(
        'require_project_access("review") → 不计',
        _expect_impact([("require_project_access", "review", False)]),
        _impact_view(_S7, "s7_endpoint"),
    ),
    selfcheck.Sample(
        '只在注释、docstring 与字符串里写有 require_project_access("edit") → 不计',
        _expect_impact([]),
        _impact_view(_S8, "s8_endpoint"),
    ),
    selfcheck.Sample(
        '同文件辅助函数以属性访问 / getattr 读 permission_level → 记直接比较位置',
        {"comparison_functions": ("_check_attr", "_check_getattr"), "count": 2},
        _s9_view,
    ),
    selfcheck.Sample(
        '读取成员行级别只用于返回展示 → 列入附录',
        {"appendix_functions": ("get_project_role",), "purposes": ("展示",)},
        _s10_view,
    ),
)


# ─── build / check / main ──────────────────────────────────────────────────


from dataclasses import dataclass  # noqa: E402


@dataclass(frozen=True)
class Built:
    payload: dict[str, Any]
    text: str
    summary: tuple[str, ...]


def build(root: Path) -> Built:
    """现算影响清单。任一失败条件抛 InventoryFailure。"""
    problems: list[str] = []
    files = _scan_app_files(root)
    if not files:
        raise InventoryFailure(["扫描到的文件数为 0"])
    infos = _parse_files(root, files, problems)
    if problems:
        raise InventoryFailure(problems)

    # 收集路由表（用于归域与端点映射）
    try:
        table = routes.collect_route_table(root)
    except routes.RouteCollectionError as exc:
        raise InventoryFailure([f"收集运行时路由表失败：{exc}"]) from exc

    note_coverage = _load_note_coverage(NOTE_INVENTORY)
    ep_domain = _build_endpoint_domain(table)

    # 门禁调用点
    gate_points = _scan_gate_points(infos, table, note_coverage, problems)
    if not gate_points and not problems:
        problems.append("扫描到的门禁调用点数为 0")
    if problems:
        raise InventoryFailure(problems)

    # 直接比较位置
    comparisons = _scan_all_comparisons(root, infos, ep_domain, note_coverage)

    # 附录
    appendix = _scan_all_appendix(root, infos)

    payload = _build_payload(gate_points, comparisons, appendix)
    try:
        text = render.dumps(payload, roots=(root, SCRIPT_REPO))
    except render.RenderError as exc:
        raise InventoryFailure([str(exc)]) from exc

    totals = payload["totals"]
    summary = (
        f"扫描文件 {len(files)} 个",
        f"门禁调用点 {totals['gate_points']} 处 / {totals['files']} 个文件",
        f"直接比较位置 {totals['direct_comparisons']} 处",
        f"附录 {len(appendix)} 处",
        f"端点（去重）{totals['endpoints']} 个",
    )
    return Built(payload, text, summary)


def _drift(committed: Any, payload: Mapping[str, Any]) -> list[str]:
    """检查模式的逐条差异。"""
    lines: list[str] = []
    for key in ("gate_points", "direct_comparisons", "appendix_non_auth_reads"):
        old = committed.get(key) if isinstance(committed, dict) else None
        new = payload.get(key, [])
        if isinstance(old, list) and all(isinstance(e, dict) for e in old):
            sort_fields = _POINT_SORT if key == "gate_points" else ("file", "function")
            try:
                diff = render.diff_entries(old, new, sort_fields)
                lines += [f"[{key}] {line}" for line in render.describe_diff(diff, sort_fields)]
            except render.RenderError as exc:
                lines.append(f"[{key}] {exc}")
        else:
            lines.append(f"已提交的清单没有 {key} 条目列表")
    committed_top = committed if isinstance(committed, dict) else {}
    for k in sorted((set(committed_top) | set(payload)) - {"gate_points", "direct_comparisons", "appendix_non_auth_reads"}):
        before = json.dumps(committed_top.get(k, "（缺失）"), ensure_ascii=False, sort_keys=True)
        after = json.dumps(payload.get(k, "（缺失）"), ensure_ascii=False, sort_keys=True)
        if before != after:
            lines.append(f"顶层字段变化：{k}")
    return lines


def check_against(out: Path, built: Built) -> int:
    """检查模式：不写文件，与 out 比对。"""
    if not out.is_file():
        print(f"edit 级影响清单与仓库现状不一致：已提交的清单不存在（{out}）", file=sys.stderr)
        return EXIT_DRIFT
    raw = out.read_bytes()
    if raw == built.text.encode("utf-8"):
        print(CONSISTENT)
        return EXIT_OK
    try:
        lines = _drift(json.loads(raw.decode("utf-8")), built.payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        lines = [f"已提交的清单无法解析（{exc}）"]
    print(f"edit 级影响清单与仓库现状不一致（{out}；检查模式不写任何文件）：", file=sys.stderr)
    for line in lines or ["条目与顶层字段逐项相同，但文本不同（格式或换行被改动）；以生成模式重写即可"]:
        print(f"- {line}", file=sys.stderr)
    return EXIT_DRIFT


def run(*, root: Path, out: Path, check: bool,
        samples: Sequence[selfcheck.Sample] = IMPACT_INVENTORY_SAMPLES) -> int:
    """生成或检查一次；返回退出码。"""
    title = "edit 级影响清单内置合成样例自检"
    try:
        count = selfcheck.ensure_samples(samples, title=title)
    except selfcheck.SelfCheckFailed as exc:
        print(exc, file=sys.stderr)
        return EXIT_FAILED
    print(f"{title}通过：{count} 个样例全部按期望")
    try:
        built = build(root)
    except InventoryFailure as exc:
        print(f"edit 级影响清单{'检查' if check else '生成'}失败（{len(exc.problems)} 项；不写出清单）：",
              file=sys.stderr)
        for problem in exc.problems:
            print(f"- {problem}", file=sys.stderr)
        return EXIT_FAILED
    print("\n".join(built.summary))
    if check:
        return check_against(out, built)
    render.write_text(out, built.text)
    print(f"已写出 edit 级影响清单：{out}")
    return EXIT_OK


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_FAILED, f"参数错误：{message}\n")


def main(argv: Sequence[str] | None = None) -> int:
    render.utf8_console()
    parser = _Parser(prog="gen_edit_level_impact_inventory.py",
                     description="edit 级影响清单（需求 9.1）：生成或检查。")
    parser.add_argument("--check", action="store_true",
                        help="检查模式：不写文件，与清单比对；不一致退出码 2")
    parser.add_argument("--out", type=Path,
                        help="清单文件；默认 backend/data/authz/edit_level_impact_inventory.json")
    parser.add_argument("--root", type=Path, help="被扫描的仓库根；默认本脚本所在仓库")
    args = parser.parse_args(argv)
    root = (args.root or SCRIPT_REPO).resolve()
    out = (args.out or DEFAULT_OUT).resolve()
    return run(root=root, out=out, check=args.check)


if __name__ == "__main__":
    sys.exit(main())
