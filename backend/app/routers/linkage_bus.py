"""统一联动总线 API — Unified Linkage Bus

GET  /api/linkage-bus/graph         — 获取统一依赖图
GET  /api/linkage-bus/resolve       — 语义 URI → 物理坐标
POST /api/linkage-bus/override      — 用户手动校正
GET  /api/linkage-bus/override      — 列出所有 overrides
DELETE /api/linkage-bus/override    — 删除 override
POST /api/linkage-bus/header-rule   — 设置表头规则
GET  /api/linkage-bus/header-rule   — 列出所有 header rules
GET  /api/linkage-bus/health        — 引擎健康检查
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.linkage_graph_builder import LinkageGraphBuilder
from app.services.linkage_label_resolver import LinkageLabelResolver
from app.services.stale_propagation_engine import stale_engine

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/linkage-bus",
    tags=["linkage-bus"],
)

# ─── Pydantic Models ─────────────────────────────────────────────


class OverrideRequest(BaseModel):
    wp_code: str
    sheet_name: str
    label: str
    row: int
    col: int


class OverrideDeleteRequest(BaseModel):
    wp_code: str
    sheet_name: str
    label: str


class HeaderRuleRequest(BaseModel):
    wp_code: str
    sheet_name: str
    data_start_row: int
    col_header_row: int | None = None
    col_headers: dict[str, int] | None = None
    row_headers: dict[str, int] | None = None


class ImpactRequest(BaseModel):
    source_uri: str
    project_id: str
    year: int


# ─── Endpoints ───────────────────────────────────────────────────


@router.post("/impact")
async def stale_impact(
    body: ImpactRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """BFS 下游影响分析（替代 /v2/notify-cell-change）。

    接收变更源 URI，执行 BFS 传播，写 DB stale 标记，SSE 推送前端。
    降级模式下返回 503。
    """
    if stale_engine.is_degraded:
        raise HTTPException(
            status_code=503,
            detail="Stale propagation engine is in degraded mode",
        )

    result = await stale_engine.on_change(
        source_uri=body.source_uri,
        project_id=body.project_id,
        year=body.year,
    )
    return result


@router.get("/graph")
async def get_unified_graph(
    rebuild: bool = Query(False, description="是否强制重新构建"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """获取统一依赖图（全局）。

    如果 rebuild=true，则从 6 个数据源重新构建。
    否则尝试读取已缓存的 unified_dependency_graph.json。
    """
    import json
    from pathlib import Path

    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    graph_path = data_dir / "unified_dependency_graph.json"

    if not rebuild and graph_path.exists():
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            return graph
        except (json.JSONDecodeError, OSError):
            pass

    # Rebuild
    builder = LinkageGraphBuilder(db=db)
    graph = await builder.build()
    return graph


@router.get("/resolve")
async def resolve_label(
    project_id: str = Query(..., description="项目 ID"),
    wp_code: str = Query(..., description="底稿编码"),
    sheet_name: str = Query(..., description="Sheet 名称"),
    label: str = Query(..., description="语义标签"),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """语义 URI → 物理坐标解析。

    三层优先级：override → header_rule → heuristic
    """
    resolver = LinkageLabelResolver()
    result = await resolver.resolve(project_id, wp_code, sheet_name, label)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Cannot resolve label '{label}' for {wp_code}:{sheet_name}",
        )

    return {
        "uri": f"{wp_code}:{sheet_name}:{label}",
        "row": result["row"],
        "col": result["col"],
        "source": result["source"],
    }


@router.post("/override")
async def create_override(
    body: OverrideRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """用户手动校正：指定 label 对应的物理坐标。"""
    resolver = LinkageLabelResolver()
    override = await resolver.add_override(
        wp_code=body.wp_code,
        sheet_name=body.sheet_name,
        label=body.label,
        row=body.row,
        col=body.col,
    )
    return {"message": "Override created", "override": override}


@router.get("/override")
async def list_overrides(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """列出所有用户手动校正。"""
    resolver = LinkageLabelResolver()
    overrides = resolver.list_overrides()
    return {"items": overrides, "total": len(overrides)}


@router.delete("/override")
async def delete_override(
    wp_code: str = Query(...),
    sheet_name: str = Query(...),
    label: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """删除用户手动校正。"""
    resolver = LinkageLabelResolver()
    deleted = resolver.delete_override(wp_code, sheet_name, label)
    if not deleted:
        raise HTTPException(status_code=404, detail={"message": "覆盖记录不存在", "message_en": "Override not found"})
    return {"message": "Override deleted"}


@router.post("/header-rule")
async def create_header_rule(
    body: HeaderRuleRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """设置表头规则（用户指定 data_start_row）。"""
    resolver = LinkageLabelResolver()
    rule = resolver.add_header_rule(
        wp_code=body.wp_code,
        sheet_name=body.sheet_name,
        data_start_row=body.data_start_row,
        col_header_row=body.col_header_row,
        col_headers=body.col_headers,
        row_headers=body.row_headers,
    )
    return {"message": "Header rule created", "rule": rule}


@router.get("/header-rule")
async def list_header_rules(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """列出所有表头规则。"""
    resolver = LinkageLabelResolver()
    rules = resolver.list_header_rules()
    return {"items": rules, "total": len(rules)}


@router.get("/audit-log")
async def get_audit_log(
    project_id: str = Query(None, description="按项目 ID 过滤"),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """获取联动传播审计日志（分页）。

    Sprint 4 Task 4.8：返回最近的 stale 传播事件记录。
    """
    from sqlalchemy import text as sa_text

    try:
        # 构建查询
        where_clause = ""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if project_id:
            where_clause = "WHERE project_id = :project_id"
            params["project_id"] = project_id

        # 查询总数
        count_sql = f"SELECT COUNT(*) FROM linkage_audit_log {where_clause}"
        count_result = await db.execute(sa_text(count_sql), params)
        total = count_result.scalar() or 0

        # 查询数据
        data_sql = (
            f"SELECT id, source_uri, affected_count, duration_ms, project_id, created_at "
            f"FROM linkage_audit_log {where_clause} "
            f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        )
        result = await db.execute(sa_text(data_sql), params)
        rows = result.fetchall()

        items = [
            {
                "id": str(row[0]),
                "source_uri": row[1],
                "affected_count": row[2],
                "duration_ms": row[3],
                "project_id": str(row[4]) if row[4] else None,
                "created_at": row[5].isoformat() if row[5] else None,
            }
            for row in rows
        ]

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        # 表不存在时返回空结果（首次部署前表可能未创建）
        logger.warning("audit-log query failed (table may not exist): %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "warning": "Audit log table not yet initialized",
        }


@router.get("/health")
async def health_check(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """引擎健康检查。"""
    import json
    from pathlib import Path

    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    graph_path = data_dir / "unified_dependency_graph.json"
    overrides_path = data_dir / "address_label_overrides.json"

    status = "healthy"
    details: dict[str, Any] = {}

    # Check graph file
    if graph_path.exists():
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            details["graph_nodes"] = len(graph.get("nodes", []))
            details["graph_edges"] = len(graph.get("edges", []))
        except Exception:
            status = "degraded"
            details["graph_error"] = "Failed to parse unified_dependency_graph.json"
    else:
        status = "degraded"
        details["graph_error"] = "unified_dependency_graph.json not found"

    # Check overrides file
    if overrides_path.exists():
        try:
            overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
            details["overrides_count"] = len(overrides.get("overrides", []))
            details["header_rules_count"] = len(overrides.get("header_rules", []))
        except Exception:
            details["overrides_error"] = "Failed to parse address_label_overrides.json"
    else:
        details["overrides_count"] = 0
        details["header_rules_count"] = 0

    details["timestamp"] = time.time()

    return {"status": status, "details": details}


# ─── Sprint 5: 公式穿透 API ─────────────────────────────────────────────────


@router.get("/formula-usage")
async def get_formula_usage(
    formula_uri: str = Query(..., description="公式 URI，如 TB:1122::期末余额"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """从公式找引用方：查询谁引用了指定 URI。

    使用 FormulaReverseIndex 查询反向索引，返回引用方列表。
    """
    from app.services.formula_reverse_index import get_reverse_index

    index = await get_reverse_index(db=db)

    referencing_uris = index.query(formula_uri)

    # Parse each URI into structured reference info
    references = []
    for uri in referencing_uris:
        parts = uri.split(":", 3)
        module = parts[0] if len(parts) > 0 else ""
        code = parts[1] if len(parts) > 1 else ""
        sheet = parts[2] if len(parts) > 2 else ""
        label = parts[3] if len(parts) > 3 else ""
        references.append({
            "uri": uri,
            "module": module,
            "code": code,
            "sheet": sheet,
            "label": label,
        })

    return {
        "uri": formula_uri,
        "references": references,
        "total": len(references),
    }


@router.get("/formulas-for")
async def get_formulas_for(
    wp_code: str = Query(None, description="底稿编码，如 D2"),
    module: str = Query(None, description="模块标识，如 WP/REPORT/NOTE"),
    code: str = Query(None, description="模块内编码"),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """从文档找公式：查询指定文档/模块的所有公式边。

    搜索 unified_dependency_graph.json 中 target 以给定前缀开头的边。
    """
    import json
    from pathlib import Path

    # Determine the target prefix to search for
    if wp_code:
        target_prefix = f"WP:{wp_code}:"
    elif module and code:
        target_prefix = f"{module.upper()}:{code}:"
    else:
        raise HTTPException(
            status_code=400,
            detail="Must provide either wp_code or both module and code",
        )

    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    graph_path = data_dir / "unified_dependency_graph.json"

    if not graph_path.exists():
        return {"target": target_prefix, "formulas": [], "total": 0}

    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"target": target_prefix, "formulas": [], "total": 0}

    edges = data.get("edges", [])
    formulas = []
    for edge in edges:
        target = edge.get("target", "")
        if target.startswith(target_prefix):
            formulas.append({
                "source_uri": edge.get("source", ""),
                "target_uri": target,
                "formula_text": edge.get("formula", ""),
                "type": edge.get("type", "data_flow"),
            })

    return {
        "target": target_prefix,
        "formulas": formulas,
        "total": len(formulas),
    }


@router.get("/cell-detail")
async def get_cell_detail(
    wp_code: str = Query(..., description="底稿编码"),
    sheet_name: str = Query("", description="Sheet 名称"),
    label: str = Query("", description="语义标签"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """单元格完整公式详情：上游来源、下游去向、公式文本、stale 状态。"""
    import json
    from pathlib import Path

    # Construct the cell URI
    cell_uri = f"WP:{wp_code}:{sheet_name}:{label}"

    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    graph_path = data_dir / "unified_dependency_graph.json"

    upstream: list[dict[str, str]] = []
    downstream: list[dict[str, str]] = []
    formula_text = ""

    # Load dependency graph for upstream/downstream
    if graph_path.exists():
        try:
            data = json.loads(graph_path.read_text(encoding="utf-8"))
            edges = data.get("edges", [])

            for edge in edges:
                source = edge.get("source", "")
                target = edge.get("target", "")

                # Upstream: edges where this cell is the target (data flows INTO this cell)
                if target == cell_uri or (sheet_name == "" and target.startswith(f"WP:{wp_code}:")):
                    parts = source.split(":", 3)
                    upstream.append({
                        "uri": source,
                        "module": parts[0] if len(parts) > 0 else "",
                        "code": parts[1] if len(parts) > 1 else "",
                        "sheet": parts[2] if len(parts) > 2 else "",
                        "label": parts[3] if len(parts) > 3 else "",
                    })
                    if edge.get("formula"):
                        formula_text = edge["formula"]

                # Downstream: edges where this cell is the source (data flows FROM this cell)
                if source == cell_uri or (sheet_name == "" and source.startswith(f"WP:{wp_code}:")):
                    parts = target.split(":", 3)
                    downstream.append({
                        "uri": target,
                        "module": parts[0] if len(parts) > 0 else "",
                        "code": parts[1] if len(parts) > 1 else "",
                        "sheet": parts[2] if len(parts) > 2 else "",
                        "label": parts[3] if len(parts) > 3 else "",
                    })
        except (json.JSONDecodeError, OSError):
            pass

    # Also check reverse index for downstream references
    from app.services.formula_reverse_index import get_reverse_index
    index = await get_reverse_index(db=db)
    reverse_refs = index.query(cell_uri)
    for ref_uri in reverse_refs:
        parts = ref_uri.split(":", 3)
        ref_entry = {
            "uri": ref_uri,
            "module": parts[0] if len(parts) > 0 else "",
            "code": parts[1] if len(parts) > 1 else "",
            "sheet": parts[2] if len(parts) > 2 else "",
            "label": parts[3] if len(parts) > 3 else "",
        }
        # Avoid duplicates
        if ref_entry not in downstream:
            downstream.append(ref_entry)

    # Check stale status from DB
    is_stale = False
    try:
        from sqlalchemy import text as sa_text

        result = await db.execute(
            sa_text(
                "SELECT wp.prefill_stale FROM working_paper wp "
                "JOIN wp_index idx ON wp.wp_index_id = idx.id "
                "WHERE idx.wp_code = :wp_code LIMIT 1"
            ),
            {"wp_code": wp_code},
        )
        row = result.fetchone()
        if row:
            is_stale = bool(row[0])
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    return {
        "uri": cell_uri,
        "upstream": upstream,
        "downstream": downstream,
        "formula": formula_text,
        "is_stale": is_stale,
    }
