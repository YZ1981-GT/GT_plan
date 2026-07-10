"""ACNR 只读 API — lookup / resolve / entries / anchors

首期 M0 只读端点，读取 global_catalog.json 提供统一解析服务。
响应经 ResponseWrapperMiddleware 包为 {code, message, data} 信封。

注册到 router_registry/system.py §133。

Requirements: 2.1, 2.2, 2.3, 2.4, 5.1, 5.3, 5.6
"""
from fastapi import APIRouter, Depends, Query

from app.deps import get_current_user
from app.services.acnr.catalog import (
    list_cells,
    list_sheets,
    lookup,
    resolve,
)

router = APIRouter(prefix="/api/acnr", tags=["ACNR-地址坐标名称注册中心"])


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


@router.get("/resolve")
async def acnr_resolve(
    uri: str | None = Query(None, description="五域 URI，如 wp://D2/明细表D2-2#E100"),
    formula_ref: str | None = Query(None, description="公式引用，如 WP('D2','明细表D2-2','E100')"),
    addr_id: str | None = Query(None, description="addr_id，如 D2/D2-2/E100"),
    index_ref: str | None = Query(None, description="索引语法，如 cell:D2-2!E100"),
    _user=Depends(get_current_user),
):
    """统一解析：接受四种语法之一，返回 canonical addr_id + 物理格。

    首期 M0 只读 L1（无 project_id / wp_id 解析）。

    命中: {found:true, addr_id, entry_type, cell_address, semantic_label, formula_ref, uri, jump_route}
    未命中: {found:false, candidates:[...]}（≤5）
    多命中: {found:false, error:"ambiguous", candidates:[...]}
    """
    return resolve(uri=uri, formula_ref=formula_ref, addr_id=addr_id, index_ref=index_ref)


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
