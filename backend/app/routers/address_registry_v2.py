"""Address Registry V2: 三级地址解析 + stale 传播链路

提供：
- GET /api/address-registry/v2/resolve?wp_code=...&sheet=...&cell_desc=...   语义→物理
- GET /api/address-registry/v2/stale-impact?wp_code=...&sheet=...&cell=...   单元格变更影响范围（BFS下游）
- GET /api/address-registry/v2/dependencies?wp_code=...                       底稿的全部依赖
- POST /api/address-registry/v2/notify-cell-change                            通知单元格变更（触发 stale）
- GET /api/address-registry/v2/anchors?wp_code=...&sheet=...                  查询某 sheet 的语义锚点
- GET /api/address-registry/v2/stats                                          全局统计
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pathlib import Path
import json
from typing import Any, Optional

from app.deps import get_current_user

router = APIRouter(prefix="/api/address-registry/v2", tags=["address-registry-v2"])

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
    """语义描述 → 物理坐标"""
    l2, resolved, _, _ = _load()
    if wp_code not in l2:
        raise HTTPException(404, f"wp_code {wp_code} not found in registry")

    # 在 resolved 中查找已解析项（命中 cwr）
    for r in resolved.get("resolved", []):
        src = r.get("source", {})
        if (src.get("wp_code") == wp_code
                and (not sheet or sheet in src.get("sheet", "") or src.get("sheet", "") in sheet)
                and (not cell_desc or cell_desc == src.get("description_cell", ""))):
            return {
                "matched": True,
                "wp_code": wp_code,
                "file": src.get("file"),
                "sheet": src.get("sheet"),
                "cell": src.get("cell"),
                "matched_anchor": src.get("matched_anchor"),
                "match_type": src.get("match_type"),
                "ref_id": r.get("ref_id"),
            }

    # 兜底：直接在 L2 中查找
    files = l2.get(wp_code, {})
    for fname, sheets in files.items():
        for sn, sd in sheets.items():
            if sheet and sheet not in sn and sn not in sheet:
                continue
            anchors = sd.get("anchors", {})
            if cell_desc in anchors:
                return {
                    "matched": True,
                    "wp_code": wp_code,
                    "file": fname,
                    "sheet": sn,
                    "cell": anchors[cell_desc],
                    "matched_anchor": cell_desc,
                    "match_type": "direct_l2_lookup",
                }
            # 包含匹配
            for anc, c in anchors.items():
                if cell_desc and (cell_desc in anc or anc in cell_desc):
                    return {
                        "matched": True,
                        "wp_code": wp_code,
                        "file": fname,
                        "sheet": sn,
                        "cell": c,
                        "matched_anchor": anc,
                        "match_type": "contains_l2_lookup",
                    }

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
                result.append({
                    "file": fname,
                    "sheet": sn,
                    "anchor": anchor,
                    "cell": cell,
                })

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
                    tgt = {
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
                    }
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
                    })

        # 2) 通过 L3 跨工作表公式依赖
        for d in deps.get("dependencies", []):
            if d.get("source_wp") != cur_wp:
                continue
            if cur_sheet and d.get("source_sheet") != cur_sheet:
                continue
            if cur_cell and d.get("source_cell") != cur_cell:
                continue
            affected.append({
                "wp_code": cur_wp,  # 同底稿内跨 sheet
                "sheet": d.get("target_sheet"),
                "cell": d.get("target_cell"),
                "depth": depth + 1,
                "via_formula": d.get("formula"),
                "description": "跨工作表公式引用",
                "match_type": "formula_dep",
            })

    return {
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
                    "target": {
                        "wp_code": t.get("wp_code") or t.get("target_module"),
                        "sheet": t.get("sheet"),
                        "cell": t.get("cell"),
                        "match_type": t.get("match_type"),
                    },
                })
        for t in r.get("targets", []):
            if t.get("wp_code") == wp_code:
                upstream.append({
                    "ref_id": r.get("ref_id"),
                    "description": r.get("description"),
                    "severity": r.get("severity"),
                    "source": {
                        "wp_code": src.get("wp_code"),
                        "sheet": src.get("sheet"),
                        "cell": src.get("cell"),
                        "match_type": src.get("match_type"),
                    },
                })

    formula_deps = [
        d for d in deps.get("dependencies", [])
        if d.get("source_wp") == wp_code
    ][:50]

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
    body: dict,
    user=Depends(get_current_user),
) -> dict:
    """通知单元格变更，返回 stale 传播链路（前端编辑器调用）"""
    wp_code = body.get("wp_code", "")
    sheet = body.get("sheet", "")
    cell = body.get("cell", "")
    max_depth = int(body.get("max_depth", 3))

    if not wp_code:
        raise HTTPException(400, "wp_code is required")

    # 直接复用 stale-impact
    impact = await stale_impact(wp_code, sheet, cell, max_depth, user)

    # TODO: 这里可加事件总线广播 (event_bus.publish('CELL_CHANGED', ...))
    # 让 outbox/SSE 自动推送 stale 标记给所有打开了下游底稿的客户端

    return {
        "ok": True,
        "wp_code": wp_code,
        "sheet": sheet,
        "cell": cell,
        "stale_targets": impact.get("affected", []),
        "total_affected": impact.get("total_affected"),
        "message": f"已识别 {impact.get('total_affected')} 个下游影响点",
    }
