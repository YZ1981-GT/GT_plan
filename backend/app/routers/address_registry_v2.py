"""Address Registry V2: 三级地址解析 + stale 传播链路

@see address_registry — 本模块=静态依赖图（stale 影响分析用，linkage_graph 离线产物）

提供：
- GET /api/address-registry/v2/resolve?wp_code=...&sheet=...&cell_desc=...   语义→物理
- GET /api/address-registry/v2/stale-impact?wp_code=...&sheet=...&cell=...   单元格变更影响范围（BFS下游）
- GET /api/address-registry/v2/dependencies?wp_code=...                       底稿的全部依赖
- POST /api/address-registry/v2/notify-cell-change                            已停用（410）

规范身份（spec acnr-foundation-defect-closure T21 / 需求 9.1~9.2）：四个读端点（/resolve、/anchors、
/stale-impact、/dependencies）的每个节点与边两端追加 addr_id / sheet_addr_id / unresolved_code /
unresolved_reason（经 ``acnr.v2_canonical``，addr_id 与 unresolved_reason 恰有其一，只增）；/resolve 的
包含匹配只作候选（matched=false、candidate=true、match_kind="contains"）。
- GET /api/address-registry/v2/anchors?wp_code=...&sheet=...                  查询某 sheet 的语义锚点
- GET /api/address-registry/v2/stats                                          全局统计

鉴权结论（spec acnr-foundation-defect-closure D8 / 需求 10.4~10.5，T25）：
- notify-cell-change 已下线（410，不触达数据）；本模块不再有「带 project_id 的无鉴权写端点」。
- /stats、/resolve、/anchors、/stale-impact、/dependencies 只读模块级静态依赖图（入参是 wp_code/sheet/
  cell_desc，不带 project_id、不写项目数据），维持仅登录（get_current_user）即可。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pathlib import Path
import json
from typing import Any, Optional

from app.deps import get_current_user
from app.services.acnr import v2_canonical

router = APIRouter(prefix="/api/address-registry/v2", tags=["地址坐标-变更影响分析(V2/linkage)"])

# 模块级缓存
_L2_CACHE: Optional[dict] = None
_RESOLVED_CACHE: Optional[dict] = None
_DEPS_CACHE: Optional[dict] = None
_CWR_CACHE: Optional[dict] = None


def _load() -> tuple[dict, dict, dict, dict]:
    global _L2_CACHE, _RESOLVED_CACHE, _DEPS_CACHE, _CWR_CACHE
    base = Path(__file__).parent.parent.parent / "data"
    if _L2_CACHE is None:
        _L2_CACHE = json.loads((base / "address_registry_l2_semantic.json").read_bytes())
    if _RESOLVED_CACHE is None:
        _RESOLVED_CACHE = json.loads((base / "address_registry_resolved_refs.json").read_bytes())
    if _DEPS_CACHE is None:
        _DEPS_CACHE = json.loads((base / "address_registry_l3_dependencies.json").read_bytes())
    if _CWR_CACHE is None:
        _CWR_CACHE = json.loads((base / "cross_wp_references.json").read_bytes())
    return _L2_CACHE, _RESOLVED_CACHE, _DEPS_CACHE, _CWR_CACHE


def _ref_end(end: dict) -> dict:
    """resolved ref 的一端 → 响应里的端点 dict（旧字段）。"""
    return {
        "wp_code": end.get("wp_code"),
        "sheet": end.get("sheet"),
        "cell": end.get("cell"),
        "match_type": end.get("match_type"),
    }


def _end_identity(body: dict, end: dict) -> dict:
    """边端点追加规范字段：底稿端点经 v2_canonical，附注 / 报表端点给非底稿原因（T21 / 需求 9.1）。"""
    if end.get("wp_code"):
        return v2_canonical.annotate(body, end.get("wp_code"), end.get("sheet"), end.get("cell"))
    body.update(v2_canonical.non_workpaper_node(end.get("target_module")).response_fields())
    return body


@router.get("/stats")
async def get_stats(user=Depends(get_current_user)) -> dict:
    """全局地址注册表统计"""
    l2, resolved, deps, cwr = _load()
    return {
        "l2_wp_codes": len(l2),
        "l2_total_anchors": sum(
            len(s.get("anchors", {}))
            for files in l2.values()
            for sheets in files.values()
            for s in sheets.values()
        ),
        "resolved_refs": resolved.get("stats", {}),
        "cross_sheet_dependencies": deps.get("stats", {}),
        "cwr_total": len(cwr.get("references", [])),
    }


@router.get("/resolve")
async def resolve_address(
    wp_code: str = Query(..., description="底稿编码"),
    sheet: str = Query("", description="sheet 名（可模糊）"),
    cell_desc: str = Query("", description="单元格描述（如'销售费用折旧'或'E10'）"),
    user=Depends(get_current_user),
) -> dict:
    """语义描述 → 物理坐标。

    T21 / 需求 9.2：先找精确命中（sheet 相等或未给、描述相等），返回 ``matched=true``、``match_kind="exact"``；
    只有包含匹配（sheet 或描述互相包含）时返回 ``matched=false``、``candidate=true``、``match_kind="contains"``。
    每个结果都带规范字段 addr_id / sheet_addr_id / unresolved_code / unresolved_reason（只增）。
    """
    l2, resolved, _, _ = _load()
    if wp_code not in l2:
        raise HTTPException(404, f"wp_code {wp_code} not found in registry")

    def _hit(exact: bool, body: dict) -> dict:
        body.update({"matched": exact, "match_kind": "exact" if exact else "contains"})
        if not exact:
            body["candidate"] = True
        return v2_canonical.annotate(body, wp_code, body.get("sheet"), body.get("cell"))

    candidate: dict | None = None
    # 在 resolved 中查找已解析项（命中 cwr）
    for r in resolved.get("resolved", []):
        src = r.get("source", {})
        src_sheet = src.get("sheet", "") or ""
        if src.get("wp_code") != wp_code or (cell_desc and cell_desc != src.get("description_cell", "")):
            continue
        sheet_exact = not sheet or sheet == src_sheet
        if not sheet_exact and not (sheet in src_sheet or src_sheet in sheet):
            continue
        body = {
            "wp_code": wp_code,
            "file": src.get("file"),
            "sheet": src.get("sheet"),
            "cell": src.get("cell"),
            "matched_anchor": src.get("matched_anchor"),
            "match_type": src.get("match_type"),
            "ref_id": r.get("ref_id"),
        }
        if sheet_exact:
            return _hit(True, body)
        candidate = candidate or body

    # 兜底：直接在 L2 中查找
    files = l2.get(wp_code, {})
    for fname, sheets in files.items():
        for sn, sd in sheets.items():
            sheet_exact = not sheet or sheet == sn
            if not sheet_exact and sheet not in sn and sn not in sheet:
                continue
            anchors = sd.get("anchors", {})
            if cell_desc in anchors:
                body = {
                    "wp_code": wp_code,
                    "file": fname,
                    "sheet": sn,
                    "cell": anchors[cell_desc],
                    "matched_anchor": cell_desc,
                    "match_type": "direct_l2_lookup",
                }
                if sheet_exact:
                    return _hit(True, body)
                candidate = candidate or body
                continue
            # 包含匹配：只作候选
            for anc, c in anchors.items():
                if cell_desc and (cell_desc in anc or anc in cell_desc) and candidate is None:
                    candidate = {
                        "wp_code": wp_code,
                        "file": fname,
                        "sheet": sn,
                        "cell": c,
                        "matched_anchor": anc,
                        "match_type": "contains_l2_lookup",
                    }
                    break

    if candidate is not None:
        return _hit(False, candidate)
    return {"matched": False, "wp_code": wp_code, "sheet_hint": sheet, "cell_desc": cell_desc}


@router.get("/anchors")
async def list_anchors(
    wp_code: str = Query(...),
    sheet: str = Query("", description="可选 sheet 过滤"),
    user=Depends(get_current_user),
) -> dict:
    """查询某底稿（或某 sheet）的语义锚点列表"""
    l2, _, _, _ = _load()
    if wp_code not in l2:
        return {"wp_code": wp_code, "anchors": []}

    result = []
    for fname, sheets in l2[wp_code].items():
        for sn, sd in sheets.items():
            if sheet and sheet not in sn and sn not in sheet:
                continue
            anchors = sd.get("anchors", {})
            for anchor, cell in anchors.items():
                result.append(v2_canonical.annotate({
                    "file": fname,
                    "sheet": sn,
                    "anchor": anchor,
                    "cell": cell,
                }, wp_code, sn, cell))

    return {"wp_code": wp_code, "anchors": result, "total": len(result)}


@router.get("/stale-impact")
async def stale_impact(
    wp_code: str = Query(..., description="变更的底稿编码"),
    sheet: str = Query("", description="变更的 sheet（可选）"),
    cell: str = Query("", description="变更的单元格（可选）"),
    max_depth: int = Query(3, description="BFS 最大深度"),
    user=Depends(get_current_user),
) -> dict:
    """计算单元格变更的下游影响范围（BFS）"""
    _, resolved, deps, _ = _load()

    affected: list[dict] = []
    visited: set[str] = set()

    # 起点
    queue: list[tuple[str, str, str, int, str]] = [(wp_code, sheet, cell, 0, "")]
    # (wp, sheet, cell, depth, via)

    while queue:
        cur_wp, cur_sheet, cur_cell, depth, via = queue.pop(0)
        node_key = f"{cur_wp}|{cur_sheet}|{cur_cell}"
        if node_key in visited or depth > max_depth:
            continue
        visited.add(node_key)

        # 1) 通过 resolved（CWR）查找源-目标
        for r in resolved.get("resolved", []):
            src = r.get("source", {})
            if src.get("wp_code") != cur_wp:
                continue
            # 单元格匹配（如果调用方未指定 cell，则只看 wp 级）
            if cur_cell and src.get("cell") != cur_cell and src.get("description_cell") != cur_cell:
                continue
            if cur_sheet and src.get("sheet") != cur_sheet and cur_sheet not in src.get("sheet", ""):
                continue

            for t in r.get("targets", []):
                if "wp_code" in t and t.get("match_type") not in ("module", "unmatched"):
                    tgt = v2_canonical.annotate({
                        "wp_code": t["wp_code"],
                        "file": t.get("file"),
                        "sheet": t.get("sheet"),
                        "cell": t.get("cell"),
                        "matched_anchor": t.get("matched_anchor"),
                        "depth": depth + 1,
                        "via_ref": r.get("ref_id"),
                        "description": r.get("description"),
                        "severity": r.get("severity"),
                        "match_type": t.get("match_type"),
                    }, t["wp_code"], t.get("sheet"), t.get("cell"))
                    affected.append(tgt)
                    queue.append((t["wp_code"], t.get("sheet", ""), t.get("cell", ""), depth + 1, r.get("ref_id", "")))
                elif "target_module" in t:
                    affected.append({
                        "target_module": t["target_module"],
                        "target_type": t.get("target_type"),
                        "note_section_code": t.get("note_section_code"),
                        "report_row_code": t.get("report_row_code"),
                        "depth": depth + 1,
                        "via_ref": r.get("ref_id"),
                        "description": r.get("description"),
                        "severity": r.get("severity"),
                        **v2_canonical.non_workpaper_node(t["target_module"]).response_fields(),
                    })

        # 2) 通过 L3 跨工作表公式依赖
        for d in deps.get("dependencies", []):
            if d.get("source_wp") != cur_wp:
                continue
            if cur_sheet and d.get("source_sheet") != cur_sheet:
                continue
            if cur_cell and d.get("source_cell") != cur_cell:
                continue
            affected.append(v2_canonical.annotate({
                "wp_code": cur_wp,  # 同底稿内跨 sheet
                "sheet": d.get("target_sheet"),
                "cell": d.get("target_cell"),
                "depth": depth + 1,
                "via_formula": d.get("formula"),
                "description": "跨工作表公式引用",
                "match_type": "formula_dep",
            }, cur_wp, d.get("target_sheet"), d.get("target_cell")))

    return {
        "source": v2_canonical.canonical_node(wp_code, sheet, cell).response_fields(),
        "wp_code": wp_code,
        "sheet": sheet,
        "cell": cell,
        "max_depth": max_depth,
        "total_affected": len(affected),
        "affected": affected[:200],  # 截断防爆
    }


@router.get("/dependencies")
async def get_dependencies(
    wp_code: str = Query(...),
    user=Depends(get_current_user),
) -> dict:
    """获取某底稿的全部依赖（上游+下游）"""
    _, resolved, deps, _ = _load()

    upstream: list[dict] = []
    downstream: list[dict] = []

    for r in resolved.get("resolved", []):
        src = r.get("source", {})
        if src.get("wp_code") == wp_code:
            for t in r.get("targets", []):
                downstream.append({
                    "ref_id": r.get("ref_id"),
                    "description": r.get("description"),
                    "severity": r.get("severity"),
                    "target": _end_identity({
                        "wp_code": t.get("wp_code") or t.get("target_module"),
                        "sheet": t.get("sheet"),
                        "cell": t.get("cell"),
                        "match_type": t.get("match_type"),
                    }, t),
                    "source": _end_identity(_ref_end(src), src),
                })
        for t in r.get("targets", []):
            if t.get("wp_code") == wp_code:
                upstream.append({
                    "ref_id": r.get("ref_id"),
                    "description": r.get("description"),
                    "severity": r.get("severity"),
                    "source": _end_identity(_ref_end(src), src),
                    "target": _end_identity(_ref_end(t), t),
                })

    formula_deps = [
        {
            **d,
            "source_identity": v2_canonical.canonical_node(
                d.get("source_wp"), d.get("source_sheet"), d.get("source_cell")).response_fields(),
            "target_identity": v2_canonical.canonical_node(
                d.get("source_wp"), d.get("target_sheet"), d.get("target_cell")).response_fields(),
        }
        for d in [x for x in deps.get("dependencies", []) if x.get("source_wp") == wp_code][:50]
    ]

    return {
        "wp_code": wp_code,
        "upstream": upstream,
        "downstream": downstream,
        "formula_dependencies": formula_deps,
        "stats": {
            "upstream_count": len(upstream),
            "downstream_count": len(downstream),
            "formula_deps_count": len(formula_deps),
        },
    }


@router.post("/notify-cell-change")
async def notify_cell_change(
    user=Depends(get_current_user),
) -> dict:
    """已停用（spec acnr-foundation-defect-closure D8 / 需求 10）。

    原实现无项目鉴权即按任意 project_id 写 stale（年度写死 2025），属越权写
    （IDOR）。前端已无调用方。改走带项目鉴权的 ``POST /api/linkage-bus/impact``。
    仅保留登录校验（未登录 401）、不触达任何数据。
    """
    raise HTTPException(
        status_code=410,
        detail={
            "error_code": "ENDPOINT_GONE",
            "message": "该接口已停用，请改用 /api/linkage-bus/impact",
        },
    )
