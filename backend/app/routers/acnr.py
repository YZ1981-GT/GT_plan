"""ACNR API — lookup / resolve / entries / anchors / resolve-instance / coverage

M0: 只读端点（lookup/resolve/entries/anchors），读取 global_catalog.json。
M1: resolve-instance（运行时查 WpIndex → ProjectBinding → wp_id）。
M3: coverage 覆盖度报表端点。

响应经 ResponseWrapperMiddleware 包为 {code, message, data} 信封。
注册到 router_registry/system.py §133。

Requirements: 2.1, 2.2, 2.3, 2.4, 4.4, 4.6, 5.1, 5.3, 5.6, 6.1, 6.2, 6.3, 6.4, 13.1
"""
from dataclasses import asdict
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.services.acnr.auth import check_project_access, verify_wp_binding
from app.services.acnr.catalog import (
    get_catalog,
    list_cells,
    list_sheets,
    lookup,
)
from app.services.acnr.resolver import full_resolve, resolve_instance
from app.services.acnr.overlay import (
    apply_project_overlay,
    remove_project_overlay,
    ensure_cache_loaded,
    OverlayPatch,
)
from app.services.acnr.overlay_repository import OverlayRevisionConflict


# ─── Request/Response Models ──────────────────────────────────────────────────


class AcnrResolveRequest(BaseModel):
    """POST /api/acnr/resolve 请求体 — 四种语法 + 可选项目/域上下文。"""

    uri: Optional[str] = None
    formula_ref: Optional[str] = None
    addr_id: Optional[str] = None
    index_ref: Optional[str] = None
    # Req-1.2: project_id 透传给 full_resolve（触发 L2/L3）
    project_id: Optional[str] = None
    # Req-1.3: wp_id 透传给 full_resolve 的 explicit_wp_id 参数
    wp_id: Optional[str] = None
    # Req-1.5: domain 提示（非 wp 域委托 V1）
    domain: Optional[str] = None


class AcnrResolveResponse(BaseModel):
    """POST /api/acnr/resolve 统一响应 — wp/非wp 同一 schema (Req-1.5)。"""

    found: bool
    addr_id: Optional[str] = None
    entry_type: Optional[str] = None
    cell_address: Optional[str] = None
    semantic_label: Optional[str] = None
    formula_ref: Optional[str] = None
    uri: Optional[str] = None
    jump_route: Optional[str] = None
    wp_id: Optional[str] = None
    error: Optional[str] = None
    candidates: Optional[list] = None
    source_layer: Optional[str] = None

router = APIRouter(prefix="/api/acnr", tags=["ACNR-地址坐标名称注册中心"])


# ─── Internal Helpers ─────────────────────────────────────────────────────────


def _extract_sheet_code(body: AcnrResolveRequest) -> str | None:
    """从请求体中推导 sheet_code，用于 binding 校验。

    推导逻辑：
    - addr_id "D2/D2-2/E100" → "D2-2"（第二段）
    - uri "wp://D2/明细表D2-2#E100" → 需解析（复杂，降级不校验）
    - formula_ref "WP('D2','明细表D2-2','E100')" → 需解析
    - index_ref "cell:D2-2!E100" → "D2-2"（冒号后感叹号前）

    仅对能简单推导的场景校验，无法推导时返回 None（不阻断请求）。
    """
    if body.addr_id:
        parts = body.addr_id.split("/")
        if len(parts) >= 2:
            return parts[1]

    if body.index_ref and ":" in body.index_ref:
        # "cell:D2-2!E100" → "D2-2"
        after_colon = body.index_ref.split(":", 1)[1]
        if "!" in after_colon:
            return after_colon.split("!", 1)[0]
        return after_colon

    return None


@router.get("/lookup")
async def acnr_lookup(
    wp_code: str | None = Query(None, description="父底稿码，如 D2"),
    sheet: str | None = Query(None, description="sheet_code 或别名，如 D2-2"),
    cell_desc: str | None = Query(None, description="单元格地址或语义描述，如 E100"),
    _user=Depends(get_current_user),
):
    """正向查找：按 wp_code / sheet / cell_desc 组合查询。

    命中: {found:true, addr_id, entry_type, ...}
    未命中: {found:false, candidates:[{addr_id, display_label, score}]}（≤5）
    多命中: {found:false, error:"ambiguous", candidates:[...]}
    """
    return lookup(wp_code=wp_code, sheet=sheet, cell_desc=cell_desc)


@router.post("/resolve")
async def acnr_resolve(
    body: AcnrResolveRequest,
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """统一解析：接受四种语法之一，返回 canonical addr_id + 物理格。

    内部调用 resolver.full_resolve() — 支持 L1/L2/L3 + 非 wp 域委托 V1。
    携带 project_id 时触发 L2 Overlay 与 L3 Runtime 解析。
    携带 wp_id 时透传为 explicit_wp_id 参数。

    命中: {found:true, addr_id, entry_type, cell_address, semantic_label, formula_ref, uri, jump_route, wp_id?, source_layer}
    未命中: {found:false, candidates:[...]}（≤5）
    多命中: {found:false, error:"ambiguous", candidates:[...]}

    Requirements: Req-1.1, Req-1.2, Req-1.3, Req-1.5, Req-3.1, Req-3.2, Req-3.3, Req-3.4
    """
    # ─── Req-3.1: 携带 project_id 时校验项目访问权 ────────────────────────
    if body.project_id:
        try:
            await check_project_access(_user, body.project_id, db)
        except HTTPException:
            # Req-12.3: 记录 auth_reject（不含敏感数据）
            from app.services.acnr.metrics import get_acnr_metrics
            get_acnr_metrics().record_auth_reject(project_id=body.project_id)
            raise

    # ─── Req-3.2: 携带 wp_id 时校验 binding 三元组 ───────────────────────
    # 需要从输入推导 sheet_code 以做 binding 校验
    if body.wp_id and body.project_id:
        # 推导 sheet_code：从 addr_id / uri / formula_ref / index_ref 中提取
        _sheet_code = _extract_sheet_code(body)
        if _sheet_code:
            await verify_wp_binding(body.wp_id, body.project_id, _sheet_code, db)

    result = await full_resolve(
        uri=body.uri,
        formula_ref=body.formula_ref,
        addr_id=body.addr_id,
        index_ref=body.index_ref,
        project_id=body.project_id,
        # Req-1.3: 透传显式 wp_id（binding 已在上方 verify_wp_binding 校验）→
        # 多实例消歧按调用方指定实例解析 wp_id/jump_route
        explicit_wp_id=body.wp_id if (body.wp_id and body.project_id) else None,
        db=db,
    )

    # Convert dataclass to dict, strip None values for cleaner response
    response = asdict(result)

    # ─── Req-3.4: 不携带 project_id 时不返回项目级数据 ────────────────────
    if not body.project_id:
        response.pop("wp_id", None)
        response.pop("jump_route", None)

    return {k: v for k, v in response.items() if v is not None}


# ─── POST /api/acnr/resolve-batch — 批量解析端点 (Req-15.4) ───────────────────


class AcnrResolveBatchItem(BaseModel):
    """批量解析单项 — 四种语法之一。"""

    uri: Optional[str] = None
    formula_ref: Optional[str] = None
    addr_id: Optional[str] = None
    index_ref: Optional[str] = None


class AcnrResolveBatchRequest(BaseModel):
    """POST /api/acnr/resolve-batch 请求体。"""

    items: list[AcnrResolveBatchItem]
    project_id: Optional[str] = None


@router.post("/resolve-batch")
async def acnr_resolve_batch(
    body: AcnrResolveBatchRequest,
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量解析多个地址 — 单次 HTTP 请求解析多条（减少 RTT）。

    接受 items ≤ 50，返回等长结果数组。
    若携带 project_id，项目授权仅校验一次后复用。

    Requirements: Req-15.3, Req-15.4
    """
    # 防滥用：限制 items ≤ 50
    if len(body.items) > 50:
        raise HTTPException(
            status_code=422,
            detail="items 数量不得超过 50",
        )

    if len(body.items) == 0:
        return []

    # 项目授权复用：有 project_id 时校验一次
    if body.project_id:
        try:
            await check_project_access(_user, body.project_id, db)
        except HTTPException:
            from app.services.acnr.metrics import get_acnr_metrics
            get_acnr_metrics().record_auth_reject(project_id=body.project_id)
            raise

    # 循环调 full_resolve
    # Req-17: 创建请求级 instance memo 缓存，在同一 batch 内复用
    # key = "project_id:parent_wp_code:sheet_code"，disambiguation 不缓存
    _instance_memo: dict = {}
    results = []
    for item in body.items:
        try:
            result = await full_resolve(
                uri=item.uri,
                formula_ref=item.formula_ref,
                addr_id=item.addr_id,
                index_ref=item.index_ref,
                project_id=body.project_id,
                db=db,
                _instance_memo=_instance_memo,
            )
            response = asdict(result)
            # 不携带 project_id 时不返回项目级数据
            if not body.project_id:
                response.pop("wp_id", None)
                response.pop("jump_route", None)
            results.append({k: v for k, v in response.items() if v is not None})
        except Exception:
            results.append({"found": False, "error": "resolve_error"})

    return results


# ─── GET /resolve 兼容旧接口（降级为内部 L1 helper）────────────────────────────


@router.get("/resolve")
async def acnr_resolve_get(
    uri: str | None = Query(None, description="五域 URI，如 wp://D2/明细表D2-2#E100"),
    formula_ref: str | None = Query(None, description="公式引用，如 WP('D2','明细表D2-2','E100')"),
    addr_id: str | None = Query(None, description="addr_id，如 D2/D2-2/E100"),
    index_ref: str | None = Query(None, description="索引语法，如 cell:D2-2!E100"),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """兼容旧 GET 接口 — 内部也调 full_resolve（无 project_id/wp_id 时等价纯 L1）。

    Req-1.4: catalog.resolve() 降为内部 L1 helper，不再作为公共端点唯一出口。
    """
    result = await full_resolve(
        uri=uri,
        formula_ref=formula_ref,
        addr_id=addr_id,
        index_ref=index_ref,
        db=db,
    )

    response = asdict(result)
    return {k: v for k, v in response.items() if v is not None}


@router.get("/entries")
async def acnr_entries(
    cycle: str | None = Query(None, description="循环码过滤，如 D"),
    import_export_only: bool = Query(False, description="仅返回启用 import_export 的 sheet"),
    _user=Depends(get_current_user),
):
    """列出 sheet 目录条目（支持按 cycle / import_export 过滤）。"""
    return list_sheets(cycle=cycle, import_export_only=import_export_only)


@router.get("/anchors")
async def acnr_anchors(
    wp_code: str | None = Query(None, description="父底稿码，如 D2"),
    sheet: str | None = Query(None, description="sheet_code，如 D2-2"),
    _user=Depends(get_current_user),
):
    """列出某 sheet 下的坐标锚点（cell 条目）。

    需提供 wp_code + sheet 以定位 sheet 的 addr_id。
    """
    if not sheet:
        return []

    # 通过 lookup 找到 sheet 的 addr_id
    result = lookup(wp_code=wp_code, sheet=sheet)
    if result.get("found") and result.get("entry_type") == "sheet":
        sheet_addr_id = result["addr_id"]
        return list_cells(sheet_addr_id)
    # 如果 lookup 未命中，尝试直接拼 addr_id
    if wp_code:
        sheet_addr_id = f"{wp_code}/{sheet}"
        cells = list_cells(sheet_addr_id)
        if cells:
            return cells
    return []


@router.get("/resolve-instance")
async def acnr_resolve_instance(
    project_id: UUID = Query(..., description="项目 UUID"),
    parent: str = Query(..., description="父底稿码（WP 第一参），如 D2"),
    sheet_code: str = Query(..., description="Tab 编码，如 D2-2"),
    wp_id: UUID | None = Query(None, description="显式 wp_id（多实例消歧时传入）"),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目实例解析 — 唯一 wp_id 出口 (R13.1)。

    经 ProjectBinding 返回 wp_id + jump_route。

    正常: {found:true, wp_id, wp_index_id, jump_route}
    多实例: {found:false, error:"disambiguation", candidates:[...]}
    未找到: {found:false, error:"not_found"}

    Requirements: R6.1, R6.2, R6.3, R6.4, R13.1, Req-3.1, Req-3.2
    """
    # ─── Req-3.1: 校验项目访问权 ─────────────────────────────────────────
    await check_project_access(_user, project_id, db)

    # ─── Req-3.2: 携带 explicit wp_id 时校验 binding 三元组 ──────────────
    if wp_id is not None:
        await verify_wp_binding(wp_id, project_id, sheet_code, db)

    result = await resolve_instance(
        db=db,
        project_id=project_id,
        parent_wp_code=parent,
        sheet_code=sheet_code,
        explicit_wp_id=wp_id,
    )

    if result.found:
        return {
            "found": True,
            "wp_id": str(result.wp_id),
            "wp_index_id": str(result.wp_index_id),
            "jump_route": result.jump_route,
            "parent_wp_code": parent,
            "sheet_code": sheet_code,
        }

    # Error responses
    response: dict = {
        "found": False,
        "error": result.error,
    }
    if result.candidates:
        response["candidates"] = result.candidates
    if result.wp_index_id:
        response["wp_index_id"] = str(result.wp_index_id)

    return response


@router.get("/coverage")
async def acnr_coverage(
    cycle: str | None = Query(None, description="循环码过滤，如 D"),
    _user=Depends(get_current_user),
):
    """覆盖度报表 — 标记 semantic_only=true 需补 A1 的条目。

    统计 cell 坐标覆盖情况，列出所有 semantic_only 条目以便后续补充 A1 地址。

    Returns (data 部分):
    {
        "total_cells": int,          # 总 cell 条目数
        "with_cell_address": int,    # 有 A1 坐标的条目数
        "semantic_only": int,        # semantic_only=true 的条目数
        "coverage_pct": float,       # 覆盖率百分比 (0~100)
        "needs_a1": [{addr_id, semantic_label, parent_addr_id}],  # 需补 A1 的条目
        "by_cycle": {"D": {total, covered, pct}, ...}  # 按循环分组统计
    }

    Requirements: R4.4, R4.6
    """
    cat = get_catalog()

    # 收集所有 cell 条目（可选按 cycle 过滤）
    all_cells: list[dict] = []
    if cycle:
        # 先找属于该循环的 sheet addr_id 集合
        cycle_sheet_ids: set[str] = set()
        for s in cat.sheets_by_addr_id.values():
            if s.get("cycle", "").upper() == cycle.upper():
                cycle_sheet_ids.add(s.get("addr_id", ""))
        # 仅收集属于该循环的 cell
        for sheet_id in cycle_sheet_ids:
            all_cells.extend(cat.cells_by_parent.get(sheet_id, []))
    else:
        all_cells = list(cat.cells_by_addr_id.values())

    total_cells = len(all_cells)
    with_cell_address = 0
    semantic_only_count = 0
    needs_a1: list[dict] = []

    # 按 cycle 分组统计的临时结构
    cycle_stats: dict[str, dict[str, int]] = {}

    for cell in all_cells:
        has_a1 = bool(cell.get("cell_address"))
        is_semantic_only = cell.get("semantic_only", False)

        if has_a1:
            with_cell_address += 1

        # R4.6: semantic_only=true 的条目一律标记需补 A1（无论 A1 是否已存在）
        if is_semantic_only:
            semantic_only_count += 1
            needs_a1.append({
                "addr_id": cell.get("addr_id"),
                "semantic_label": cell.get("semantic_label"),
                "parent_addr_id": cell.get("parent_addr_id"),
            })

        # 按 cycle 分组 — 从 parent_addr_id 关联 sheet 拿 cycle
        parent_id = cell.get("parent_addr_id", "")
        parent_sheet = cat.sheets_by_addr_id.get(parent_id)
        cell_cycle = (parent_sheet.get("cycle", "?") if parent_sheet else "?").upper()

        if cell_cycle not in cycle_stats:
            cycle_stats[cell_cycle] = {"total": 0, "covered": 0}
        cycle_stats[cell_cycle]["total"] += 1
        if has_a1:
            cycle_stats[cell_cycle]["covered"] += 1

    # 计算覆盖率
    coverage_pct = round((with_cell_address / total_cells * 100) if total_cells > 0 else 0.0, 2)

    # 构建 by_cycle 响应
    by_cycle: dict[str, dict] = {}
    for c, stats in sorted(cycle_stats.items()):
        c_total = stats["total"]
        c_covered = stats["covered"]
        by_cycle[c] = {
            "total": c_total,
            "covered": c_covered,
            "pct": round((c_covered / c_total * 100) if c_total > 0 else 0.0, 2),
        }

    return {
        "total_cells": total_cells,
        "with_cell_address": with_cell_address,
        "semantic_only": semantic_only_count,
        "coverage_pct": coverage_pct,
        "needs_a1": needs_a1,
        "by_cycle": by_cycle,
    }


# ─── GET /api/acnr/metrics — 聚合指标端点 (Req-12.4) ─────────────────────────


@router.get("/metrics")
async def acnr_metrics(
    _user=Depends(require_role(["admin", "manager"])),
):
    """ACNR 可观测性 — 返回近期 resolve 聚合指标与告警事件。

    仅 admin / manager 角色可访问（Req-12.4）。

    返回结构:
    {
        "total_calls": int,
        "avg_latency_ms": float,
        "by_result": {"found": N, "miss": N, "ambiguous": N, "fallback": N},
        "by_domain": {"wp": N, "tb": N, ...},
        "by_layer": {"L1_cell": N, "L1_sheet": N, "L2": N, "L3": N, "V1": N},
        "alerts": {
            "total": int,
            "by_type": {"fallback": N, "auth_reject": N, ...},
            "recent": [AlertEvent, ...]
        },
        "recent_records": [ResolveMetricRecord, ...]
    }

    Requirements: Req-12.4
    """
    from app.services.acnr.metrics import get_acnr_metrics

    metrics = get_acnr_metrics()
    return metrics.get_aggregated_metrics()


# ─── Overlay 变更受控入口（R10 — 开放 UI）────────────────────────────────────
# 项目级 overlay（sheet 别名/绑定/自定义补丁）的读/写/删 HTTP 端点。
# 写路径经 apply_project_overlay：capability 校验（manager/partner/signing_partner/
# admin）+ 原子 ON CONFLICT upsert + 可选 CAS（expected_revision）+ 同事务 outbox
# （dispatcher 至少一次投递失效 → durable epoch + SSE 广播）。
# 高并发（数千并发编辑者）安全性由 CAS 乐观并发 + uq_overlay_identity 唯一约束 +
# 单飞缓存加载保证：冲突返回 409，调用方带最新 revision 重试，不静默覆盖。


class AcnrOverlayResponse(BaseModel):
    """单条 overlay 序列化响应。"""

    project_id: str
    addr_id: str
    overlay_type: str
    overrides: dict
    reason: str = ""
    owner: str = ""
    expires_at: Optional[str] = None
    wp_id: Optional[str] = None
    revision: int = 1


class AcnrOverlayApplyRequest(BaseModel):
    """POST /api/acnr/overlay 请求体。"""

    project_id: str
    addr_id: str
    overrides: dict
    overlay_type: str = "cust"
    reason: str = ""
    owner: str = ""
    expires_at: Optional[str] = None
    wp_id: Optional[str] = None
    # 乐观并发：提供则 CAS（仅当当前 revision == expected 才更新，冲突 409）。
    # 并发编辑同一 overlay 时防静默覆盖。
    expected_revision: Optional[int] = None


class AcnrOverlayRemoveRequest(BaseModel):
    """DELETE /api/acnr/overlay 请求体。"""

    project_id: str
    addr_id: str
    overlay_type: str = "cust"


def _serialize_overlay(patch: OverlayPatch) -> dict:
    return {
        "project_id": patch.project_id,
        "addr_id": patch.addr_id,
        "overlay_type": patch.overlay_type,
        "overrides": patch.overrides,
        "reason": patch.reason,
        "owner": patch.owner,
        "expires_at": patch.expires_at,
        "wp_id": patch.wp_id,
        "revision": patch.revision,
    }


@router.get("/overlay")
async def acnr_overlay_list(
    project_id: str = Query(..., description="项目 UUID"),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出项目全部 overlay（read-through：内存缓存缺失时从 PG 加载）。

    Requirements: R10, Req-3.1（项目访问校验）
    """
    await check_project_access(_user, project_id, db)
    patches = await ensure_cache_loaded(db, project_id)
    return [_serialize_overlay(p) for p in patches.values()]


@router.post("/overlay")
async def acnr_overlay_apply(
    body: AcnrOverlayApplyRequest,
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建/更新项目 overlay（受控写入口）。

    - capability 校验（manager/partner/signing_partner/admin）→ 不足 403
    - 原子 upsert + 可选 CAS（expected_revision）→ 冲突 409（并发编辑防覆盖）
    - 同事务写 outbox → dispatcher 至少一次投递失效

    Requirements: R10, R8（CAS 并发安全）, Req-3.1
    """
    await check_project_access(_user, body.project_id, db)
    try:
        patch = await apply_project_overlay(
            db,
            body.project_id,
            body.addr_id,
            body.overrides,
            actor=_user,
            wp_id=body.wp_id,
            reason=body.reason,
            owner=body.owner or getattr(_user, "username", "") or "",
            expires_at=body.expires_at,
            overlay_type=body.overlay_type,
            expected_revision=body.expected_revision,
        )
        await db.commit()
    except OverlayRevisionConflict as exc:
        await db.rollback()
        # 并发编辑冲突：调用方应重新拉取最新 revision 后重试
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"overlay 写入失败: {exc!s}") from exc

    return _serialize_overlay(patch)


@router.delete("/overlay")
async def acnr_overlay_remove(
    body: AcnrOverlayRemoveRequest,
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除项目 overlay（受控删除入口）。

    Requirements: R10, Req-3.1
    """
    await check_project_access(_user, body.project_id, db)
    try:
        deleted = await remove_project_overlay(
            db,
            body.project_id,
            body.addr_id,
            actor=_user,
            overlay_type=body.overlay_type,
        )
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"overlay 删除失败: {exc!s}") from exc

    return {"deleted": deleted, "addr_id": body.addr_id}
