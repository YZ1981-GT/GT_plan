"""穿透查询 API 路由

高性能四表联查：余额→序时账→凭证、余额→辅助余额→辅助明细

- GET /api/projects/{id}/ledger/penetrate          — 统一穿透查询
- GET /api/projects/{id}/ledger/balance             — 科目余额
- GET /api/projects/{id}/ledger/entries/{code}      — 序时账明细
- GET /api/projects/{id}/ledger/voucher/{no}        — 凭证分录
- GET /api/projects/{id}/ledger/aux-balance/{code}  — 辅助余额
- GET /api/projects/{id}/ledger/aux-entries/{code}  — 辅助明细
- DELETE /api/projects/{id}/ledger/cache             — 清除缓存

Validates: Requirements 15.1-15.4
"""

from __future__ import annotations

import io
import urllib.parse
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.core.redis import get_redis
from app.services.ledger_penetration_service import LedgerPenetrationService

router = APIRouter(prefix="/api/projects/{project_id}/ledger", tags=["ledger-penetration"])


def _svc(db: AsyncSession, redis) -> LedgerPenetrationService:
    return LedgerPenetrationService(db, redis)


@router.get("/penetrate")
async def penetrate(
    project_id: UUID,
    year: int = Query(...),
    account_code: str | None = None,
    drill_level: str = "all",
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 100,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """统一穿透查询（带缓存）"""
    svc = _svc(db, redis)
    return await svc.penetrate_cached(
        project_id, year, account_code, drill_level,
        date_from, date_to, page, page_size,
    )


@router.get("/balance")
async def get_balance(
    project_id: UUID,
    year: int = Query(...),
    account_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """科目余额汇总"""
    svc = _svc(db, None)
    return await svc.get_balance_summary(project_id, year, account_code)


@router.get("/opening-balance/{account_code}")
async def get_opening_balance(
    project_id: UUID,
    account_code: str,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取科目期初余额（用于序时账 running_balance 计算）"""
    svc = _svc(db, None)
    opening = await svc.get_account_opening_balance(project_id, year, account_code)
    return {"opening_balance": float(opening), "account_code": account_code}


@router.get("/entries/{account_code}")
async def get_ledger_entries(
    project_id: UUID,
    account_code: str,
    year: int = Query(...),
    date_from: str | None = None,
    date_to: str | None = None,
    cursor: str | None = Query(None, description="游标分页: date|id 格式"),
    limit: int = Query(100, ge=1, le=1000),
    page: int = 1,
    page_size: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """序时账明细（按科目穿透）— 支持游标分页和传统分页

    当提供 cursor 参数时使用游标分页（推荐大数据量场景），
    否则使用传统 OFFSET 分页。
    """
    svc = _svc(db, None)
    # 优先使用游标分页（首次请求不传 cursor 也走游标分页，用 limit 控制条数）
    if cursor is not None or limit != 100:
        return await svc.get_ledger_entries_cursor(
            project_id, year, account_code,
            cursor=cursor, limit=limit,
            date_from=date_from, date_to=date_to,
        )
    return await svc.get_ledger_entries(
        project_id, year, account_code, date_from, date_to, page, page_size,
    )


@router.get("/voucher/{voucher_no}")
async def get_voucher_entries(
    project_id: UUID,
    voucher_no: str,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """凭证分录明细（按凭证号穿透）"""
    svc = _svc(db, None)
    return await svc.get_voucher_entries(project_id, year, voucher_no)


@router.get("/aux-balance-summary")
async def get_aux_balance_summary(
    project_id: UUID,
    year: int = Query(...),
    dim_type: Optional[str] = Query(None, description="维度类型"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """辅助余额汇总（预计算，按维度+科目+辅助编码分组）。

    前端树形视图用这个接口，不再加载12万行原始数据。
    返回：维度类型列表 + 汇总行数据
    """
    import sqlalchemy as sa

    # 维度类型列表（含各类型的记录数）
    r = await db.execute(sa.text("""
        SELECT dim_type, SUM(record_count) as total_records, COUNT(*) as group_count
        FROM tb_aux_balance_summary
        WHERE project_id = :pid AND year = :yr
        GROUP BY dim_type ORDER BY total_records DESC
    """), {"pid": str(project_id), "yr": year})
    dim_types = [{"type": row[0], "total_records": int(row[1]), "group_count": int(row[2])} for row in r.fetchall()]

    # 如果只请求维度类型列表（不需要行数据）
    if dim_type == "__types_only__":
        return {"dim_types": dim_types, "rows": [], "total": 0}

    # 汇总数据（按维度类型筛选）
    params: dict = {"pid": str(project_id), "yr": year}
    sql = """
        SELECT dim_type, account_code, account_name, aux_code, aux_name,
               record_count, opening_balance, debit_amount, credit_amount, closing_balance
        FROM tb_aux_balance_summary
        WHERE project_id = :pid AND year = :yr
    """
    if dim_type:
        sql += " AND dim_type = :dt"
        params["dt"] = dim_type
    sql += " ORDER BY account_code, aux_code"

    r = await db.execute(sa.text(sql), params)
    rows = [
        {
            "dim_type": row[0], "account_code": row[1], "account_name": row[2],
            "aux_code": row[3], "aux_name": row[4], "record_count": row[5],
            "opening_balance": float(row[6]) if row[6] else 0,
            "debit_amount": float(row[7]) if row[7] else 0,
            "credit_amount": float(row[8]) if row[8] else 0,
            "closing_balance": float(row[9]) if row[9] else 0,
        }
        for row in r.fetchall()
    ]

    return {"dim_types": dim_types, "rows": rows, "total": len(rows)}


@router.get("/aux-balance-paged")
async def get_aux_balance_paged(
    project_id: UUID,
    year: int = Query(...),
    dim_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    filter: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """辅助余额表分页查询（后端筛选+分页，前端不加载全量数据）"""
    import sqlalchemy as sa
    from app.models.audit_platform_models import TbAuxBalance
    tbl = TbAuxBalance.__table__

    where = [tbl.c.project_id == project_id, tbl.c.year == year, tbl.c.is_deleted == sa.false()]
    if dim_type and dim_type != '全部':
        where.append(tbl.c.aux_type == dim_type)
    if search:
        kw = f"%{search}%"
        where.append(sa.or_(
            tbl.c.account_code.ilike(kw), tbl.c.account_name.ilike(kw),
            tbl.c.aux_name.ilike(kw), tbl.c.aux_code.ilike(kw),
        ))
    if filter == "closing":
        where.append(tbl.c.closing_balance != 0)
    elif filter == "opening":
        where.append(tbl.c.opening_balance != 0)
    elif filter == "changed":
        where.append(sa.or_(tbl.c.debit_amount != 0, tbl.c.credit_amount != 0))

    # 总数
    count_r = await db.execute(sa.select(sa.func.count()).select_from(
        sa.select(tbl.c.id).where(*where).subquery()
    ))
    total = count_r.scalar() or 0

    # 分页数据
    stmt = (
        sa.select(
            tbl.c.account_code, tbl.c.account_name, tbl.c.aux_type,
            tbl.c.aux_code, tbl.c.aux_name, tbl.c.opening_balance,
            tbl.c.debit_amount, tbl.c.credit_amount, tbl.c.closing_balance,
            tbl.c.aux_dimensions_raw,
        )
        .where(*where)
        .order_by(tbl.c.account_code, tbl.c.aux_type, tbl.c.aux_code)
        .offset((page - 1) * page_size).limit(page_size)
    )
    result = await db.execute(stmt)
    rows = [dict(r._mapping) for r in result.fetchall()]

    return {"rows": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/aux-balance-detail")
async def get_aux_balance_detail(
    project_id: UUID,
    year: int = Query(...),
    account_code: str = Query(...),
    dim_type: str = Query(...),
    aux_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """辅助余额明细查询（树形展开时按需加载）"""
    import sqlalchemy as sa
    from app.models.audit_platform_models import TbAuxBalance
    tbl = TbAuxBalance.__table__

    where = [
        tbl.c.project_id == project_id, tbl.c.year == year,
        tbl.c.is_deleted == sa.false(), tbl.c.account_code == account_code,
        tbl.c.aux_type == dim_type,
    ]
    if aux_code:
        where.append(tbl.c.aux_code == aux_code)

    stmt = sa.select(
        tbl.c.account_code, tbl.c.account_name, tbl.c.aux_type,
        tbl.c.aux_code, tbl.c.aux_name, tbl.c.opening_balance,
        tbl.c.debit_amount, tbl.c.credit_amount, tbl.c.closing_balance,
        tbl.c.aux_dimensions_raw,
    ).where(*where).order_by(tbl.c.aux_code)

    result = await db.execute(stmt)
    return [dict(r._mapping) for r in result.fetchall()]


@router.get("/aux-balance-all")
async def get_all_aux_balance(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """全量辅助余额（所有科目的辅助核算维度）"""
    svc = _svc(db, None)
    return await svc.get_all_aux_balance(project_id, year)


@router.get("/aux-balance/{account_code}")
async def get_aux_balance(
    project_id: UUID,
    account_code: str,
    year: int = Query(...),
    aux_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """辅助余额（按科目穿透到辅助维度）"""
    svc = _svc(db, None)
    return await svc.get_aux_balance(project_id, year, account_code, aux_type)


@router.get("/aux-entries/{account_code}")
async def get_aux_ledger_entries(
    project_id: UUID,
    account_code: str,
    year: int = Query(...),
    aux_type: str | None = None,
    aux_code: str | None = None,
    cursor: str | None = Query(None, description="游标分页: date|id 格式"),
    limit: int = Query(100, ge=1, le=1000),
    page: int = 1,
    page_size: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """辅助明细账（按辅助维度穿透）— 支持游标分页和传统分页"""
    svc = _svc(db, None)
    if cursor is not None:
        return await svc.get_aux_ledger_entries_cursor(
            project_id, year, account_code,
            cursor=cursor, limit=limit,
            aux_type=aux_type, aux_code=aux_code,
        )
    return await svc.get_aux_ledger_entries(
        project_id, year, account_code, aux_type, aux_code, page, page_size,
    )


@router.delete("/cache")
async def clear_cache(
    project_id: UUID,
    year: int = Query(...),
    redis=Depends(get_redis),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """清除穿透查询缓存"""
    svc = _svc(db, redis)
    count = await svc.invalidate_cache(project_id, year)
    return {"cleared": count, "message": f"已清除 {count} 条缓存"}


@router.post("/upload")
async def upload_data(
    project_id: UUID,
    year: int = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """上传四表数据文件（支持历史年度）。

    自动识别 Excel 中的余额表/序时账/辅助账 sheet 并导入。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    content = await file.read()
    from app.services.account_chart_service import _auto_import_data_sheets
    result, diagnostics = await _auto_import_data_sheets(
        project_id, content, year=year, db=db,
    )
    return {
        "imported": result,
        "diagnostics": diagnostics,
        "year": year,
        "file_name": file.filename,
    }


@router.post("/upload-multi")
async def upload_multi_files(
    project_id: UUID,
    year: int = Query(...),
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """上传多个四表数据文件（支持多个序时账文件合并导入）。

    适用场景：序时账按月份分多个文件导出（如1-10月、11-12月）。
    所有文件的数据会合并到同一个项目和年度。
    """
    if not files:
        raise HTTPException(status_code=400, detail="未提供文件")

    from app.services.account_chart_service import _auto_import_data_sheets

    all_results: dict[str, int] = {}
    all_diagnostics: list[dict] = []
    file_names: list[str] = []

    for file in files:
        if not file.filename:
            continue
        content = await file.read()
        result, diagnostics = await _auto_import_data_sheets(
            project_id, content, year=year, db=db,
        )
        file_names.append(file.filename)
        for dt, count in result.items():
            all_results[dt] = all_results.get(dt, 0) + count
        all_diagnostics.extend(diagnostics)

    return {
        "imported": all_results,
        "diagnostics": all_diagnostics,
        "year": year,
        "file_names": file_names,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 智能导入（通用引擎，支持双行表头 + 核算维度拆分 + 多文件多年度）
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/smart-preview")
async def smart_preview(
    project_id: UUID,
    files: list[UploadFile] = File(...),
    year: Optional[int] = Query(None, description="指定年度（不指定则自动提取）"),
    current_user: User = Depends(require_project_access("readonly")),
):
    """智能预览：解析多个文件，返回识别结果 + 维度信息 + 校验结果。

    不写入数据库，供用户确认后再调用 smart-import 写入。
    """
    from app.services.smart_import_engine import smart_parse_files

    file_contents = []
    for f in files:
        if not f.filename:
            continue
        content = await f.read()
        file_contents.append((f.filename, content))

    if not file_contents:
        raise HTTPException(status_code=400, detail="未提供文件")

    result = smart_parse_files(file_contents, year_override=year)

    # 辅助明细账行数从 diagnostics 中汇总（预览时不实际生成辅助明细行）
    aux_ledger_est = 0
    for d in result.get("diagnostics", []):
        aux_ledger_est += d.get("aux_ledger_count", 0)

    return {
        "year": result["year"],
        "summary": {
            "balance": len(result["balance_rows"]),
            "aux_balance": len(result["aux_balance_rows"]),
            "ledger": len(result["ledger_rows"]),
            "aux_ledger": aux_ledger_est,
        },
        "aux_dimensions": result["aux_dimensions"],
        "validation": result["validation"],
        "diagnostics": result["diagnostics"],
    }


@router.post("/smart-import")
async def smart_import(
    project_id: UUID,
    files: list[UploadFile] = File(...),
    year: Optional[int] = Query(None, description="指定年度（不指定则自动提取）"),
    custom_mapping: Optional[str] = Query(None, description="自定义列映射JSON"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """智能导入：解析多个文件并写入数据库。

    并发控制：同一项目同一时间只允许一个导入任务。
    """
    import json
    from app.services.import_queue_service import ImportQueueService

    file_label = files[0].filename or "upload.xlsx"
    if len(files) > 1:
        file_label = f"{file_label} 等{len(files)}个文件"

    ok, msg, job_batch_id = await ImportQueueService.acquire_lock(
        project_id,
        str(current_user.id),
        db,
        source_type="smart_import",
        file_name=file_label,
        year=year or 0,
    )
    if not ok:
        raise HTTPException(status_code=409, detail=msg)

    try:
        file_contents = []
        for f in files:
            if not f.filename:
                continue
            content = await f.read()
            file_contents.append((f.filename, content))

        if not file_contents:
            raise HTTPException(status_code=400, detail="未提供文件")

        mapping = None
        if custom_mapping:
            try:
                mapping = json.loads(custom_mapping)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="自定义列映射JSON格式错误")

        ImportQueueService.update_progress(
            project_id,
            2,
            f"开始导入 {len(file_contents)} 个文件…",
        )

        def _on_progress(pct: int, msg: str):
            ImportQueueService.update_progress(project_id, pct, msg)

        from app.services.smart_import_engine import smart_import_streaming
        result = await smart_import_streaming(
            project_id=project_id,
            file_contents=file_contents,
            db=db,
            year_override=year,
            custom_mapping=mapping,
            progress_callback=_on_progress,
        )

        result_payload = {
            "imported": result["data_sheets_imported"],
            "year": result["year"],
            "diagnostics": result["sheet_diagnostics"],
            "errors": result["errors"],
            "batch_id": str(job_batch_id) if job_batch_id is not None else None,
        }
        total_records = sum(
            int(v) for v in result["data_sheets_imported"].values() if isinstance(v, int)
        )
        if job_batch_id is not None:
            await ImportQueueService.complete_job(
                project_id,
                job_batch_id,
                db,
                message=f"导入完成: {result['data_sheets_imported']}",
                result=result_payload,
                year=result["year"],
                record_count=total_records,
            )
        return result_payload
    except Exception as e:
        failure_payload = {
            "imported": {},
            "year": None,
            "diagnostics": [],
            "errors": [f"导入失败: {e}"],
            "batch_id": str(job_batch_id) if job_batch_id is not None else None,
        }
        if job_batch_id is not None:
            await ImportQueueService.fail_job(
                project_id,
                job_batch_id,
                db,
                message=f"导入失败: {e}",
                result=failure_payload,
            )
        else:
            ImportQueueService.release_lock(project_id)
        raise


@router.get("/years")
async def get_available_years(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取该项目有数据的年度列表"""
    import sqlalchemy as sa
    from app.models.audit_platform_models import TbBalance
    tbl = TbBalance.__table__
    result = await db.execute(
        sa.select(sa.distinct(tbl.c.year))
        .where(tbl.c.project_id == project_id, tbl.c.is_deleted == sa.false())
        .order_by(tbl.c.year.desc())
    )
    years = [row[0] for row in result.fetchall()]
    return {"years": years}


@router.get("/stats")
async def get_data_stats(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取四表数据统计（行数、最后导入时间）"""
    import sqlalchemy as sa
    from app.models.audit_platform_models import TbBalance, TbAuxBalance, TbLedger, TbAuxLedger, ImportBatch

    stats = {}
    for name, model in [("balance", TbBalance), ("aux_balance", TbAuxBalance),
                         ("ledger", TbLedger), ("aux_ledger", TbAuxLedger)]:
        tbl = model.__table__
        r = await db.execute(
            sa.select(sa.func.count()).where(
                tbl.c.project_id == project_id, tbl.c.year == year, tbl.c.is_deleted == sa.false()
            )
        )
        stats[name] = r.scalar() or 0

    # 最后导入时间
    r = await db.execute(
        sa.select(ImportBatch.completed_at)
        .where(ImportBatch.project_id == project_id, ImportBatch.year == year)
        .order_by(ImportBatch.completed_at.desc())
        .limit(1)
    )
    last_import = r.scalar()

    return {
        "year": year,
        "counts": stats,
        "total": sum(stats.values()),
        "last_import": last_import.isoformat() if last_import else None,
    }


@router.get("/export-ledger/{account_code}")
async def export_ledger_excel(
    project_id: UUID,
    account_code: str,
    year: int = Query(...),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """导出序时账为 Excel（含期初余额行+月小计+累计余额）"""
    from fastapi.responses import StreamingResponse
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    from app.models.audit_platform_models import TbLedger, TbBalance
    import sqlalchemy as sa
    from decimal import Decimal

    # 获取期初余额
    tbl_b = TbBalance.__table__
    if account_code.endswith('*'):
        prefix = account_code[:-1]
        code_filter_b = tbl_b.c.account_code.like(prefix + '%')
    else:
        code_filter_b = (tbl_b.c.account_code == account_code)
    ob_r = await db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(tbl_b.c.opening_balance), 0))
        .where(tbl_b.c.project_id == project_id, tbl_b.c.year == year, code_filter_b, tbl_b.c.is_deleted == sa.false())
    )
    opening = float(ob_r.scalar() or 0)

    # 获取序时账数据
    tbl = TbLedger.__table__
    if account_code.endswith('*'):
        code_filter = tbl.c.account_code.like(prefix + '%')
    else:
        code_filter = (tbl.c.account_code == account_code)
    where = [tbl.c.project_id == project_id, tbl.c.year == year, code_filter, tbl.c.is_deleted == sa.false()]
    if date_from:
        where.append(tbl.c.voucher_date >= date_from)
    if date_to:
        where.append(tbl.c.voucher_date <= date_to)
    stmt = (
        sa.select(tbl.c.voucher_date, tbl.c.voucher_no, tbl.c.summary,
                   tbl.c.debit_amount, tbl.c.credit_amount, tbl.c.counterpart_account)
        .where(*where).order_by(tbl.c.voucher_date, tbl.c.voucher_no)
    )
    result = await db.execute(stmt)
    rows = result.fetchall()

    wb = openpyxl.Workbook()
    ws = wb.active
    acct_label = account_code.replace('*', '')
    ws.title = f"序时账_{acct_label}"

    headers = ["日期", "凭证号", "摘要", "借方", "贷方", "余额", "对方科目"]
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="F0ECF7", end_color="F0ECF7", fill_type="solid")
    for col, h in enumerate(headers, 1):
        cell = ws.cell(1, col, h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # 期初余额行
    opening_font = Font(bold=True, italic=True, color="4B2D77")
    ws.cell(2, 1, "")
    ws.cell(2, 2, "")
    ws.cell(2, 3, "期初余额")
    ws.cell(2, 6, opening)
    for c in range(1, 8):
        ws.cell(2, c).font = opening_font

    subtotal_font = Font(bold=True)
    subtotal_fill = PatternFill(start_color="FEF6E6", end_color="FEF6E6", fill_type="solid")

    balance = opening
    month_debit = 0.0
    month_credit = 0.0
    last_month = ""
    excel_row = 3

    for row in rows:
        vd = row[0]
        vd_str = vd.isoformat() if hasattr(vd, 'isoformat') else str(vd or '')
        month = vd_str[:7]
        d = float(row[3] or 0)
        c = float(row[4] or 0)
        balance += d - c
        month_debit += d
        month_credit += c

        if not last_month:
            last_month = month

        # 月份变化时插入上月小计
        if month != last_month and last_month:
            ws.cell(excel_row, 3, f"{last_month} 本月合计")
            ws.cell(excel_row, 4, month_debit - d)
            ws.cell(excel_row, 5, month_credit - c)
            ws.cell(excel_row, 6, balance - d + c)
            for col in range(1, 8):
                ws.cell(excel_row, col).font = subtotal_font
                ws.cell(excel_row, col).fill = subtotal_fill
            excel_row += 1
            month_debit = d
            month_credit = c
            last_month = month

        ws.cell(excel_row, 1, vd_str)
        ws.cell(excel_row, 2, row[1])
        ws.cell(excel_row, 3, row[2])
        ws.cell(excel_row, 4, d if d else None)
        ws.cell(excel_row, 5, c if c else None)
        ws.cell(excel_row, 6, balance)
        ws.cell(excel_row, 7, row[5])
        excel_row += 1

    # 最后一个月的小计
    if rows:
        ws.cell(excel_row, 3, f"{last_month} 本月合计")
        ws.cell(excel_row, 4, month_debit)
        ws.cell(excel_row, 5, month_credit)
        ws.cell(excel_row, 6, balance)
        for col in range(1, 8):
            ws.cell(excel_row, col).font = subtotal_font
            ws.cell(excel_row, col).fill = subtotal_fill

    widths = [12, 12, 30, 16, 16, 16, 16]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = w

    for col in [4, 5, 6]:
        for r in range(2, excel_row + 1):
            ws.cell(r, col).number_format = '#,##0.00'

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"序时账_{acct_label}_{year}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"},
    )


@router.get("/export-balance")
async def export_balance_excel(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """导出科目余额表为 Excel"""
    from fastapi.responses import StreamingResponse
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from app.models.audit_platform_models import TbBalance
    import sqlalchemy as sa

    tbl = TbBalance.__table__
    stmt = (
        sa.select(
            tbl.c.account_code, tbl.c.account_name, tbl.c.level,
            tbl.c.opening_balance, tbl.c.debit_amount,
            tbl.c.credit_amount, tbl.c.closing_balance,
        )
        .where(tbl.c.project_id == project_id, tbl.c.year == year, tbl.c.is_deleted == sa.false())
        .order_by(tbl.c.account_code)
    )
    result = await db.execute(stmt)
    rows = result.fetchall()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "科目余额表"

    headers = ["科目编号", "科目名称", "级次", "期初余额", "借方发生额", "贷方发生额", "期末余额"]
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="F0ECF7", end_color="F0ECF7", fill_type="solid")
    for col, h in enumerate(headers, 1):
        cell = ws.cell(1, col, h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    level1_font = Font(bold=True)
    level1_fill = PatternFill(start_color="F8F5FC", end_color="F8F5FC", fill_type="solid")

    for idx, row in enumerate(rows, 2):
        level = row[2] or 1
        ws.cell(idx, 1, row[0])
        ws.cell(idx, 2, row[1])
        ws.cell(idx, 3, level)
        ws.cell(idx, 4, float(row[3]) if row[3] else None)
        ws.cell(idx, 5, float(row[4]) if row[4] else None)
        ws.cell(idx, 6, float(row[5]) if row[5] else None)
        ws.cell(idx, 7, float(row[6]) if row[6] else None)
        # 一级科目加粗+浅紫背景
        if level == 1:
            for c in range(1, 8):
                ws.cell(idx, c).font = level1_font
                ws.cell(idx, c).fill = level1_fill

    widths = [16, 24, 6, 16, 16, 16, 16]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = w

    for col in [4, 5, 6, 7]:
        for row_idx in range(2, len(rows) + 2):
            ws.cell(row_idx, col).number_format = '#,##0.00'

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"科目余额表_{year}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"},
    )


@router.get("/export-aux-balance")
async def export_aux_balance_excel(
    project_id: UUID,
    year: int = Query(...),
    dim_type: Optional[str] = Query(None, description="维度类型筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    filter: Optional[str] = Query(None, description="筛选条件: closing/opening/changed"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """导出辅助余额表为 Excel（支持当前视图条件）"""
    from fastapi.responses import StreamingResponse
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    from app.models.audit_platform_models import TbAuxBalance
    import sqlalchemy as sa

    tbl = TbAuxBalance.__table__
    stmt = (
        sa.select(
            tbl.c.account_code, tbl.c.account_name,
            tbl.c.aux_type, tbl.c.aux_code, tbl.c.aux_name,
            tbl.c.opening_balance, tbl.c.debit_amount,
            tbl.c.credit_amount, tbl.c.closing_balance,
            tbl.c.aux_dimensions_raw,
        )
        .where(tbl.c.project_id == project_id, tbl.c.year == year, tbl.c.is_deleted == sa.false())
        .order_by(tbl.c.account_code, tbl.c.aux_type, tbl.c.aux_code)
    )
    if dim_type:
        stmt = stmt.where(tbl.c.aux_type == dim_type)
    if search:
        kw = f"%{search}%"
        stmt = stmt.where(sa.or_(
            tbl.c.account_code.ilike(kw), tbl.c.account_name.ilike(kw),
            tbl.c.aux_name.ilike(kw), tbl.c.aux_code.ilike(kw),
        ))
    if filter == "closing":
        stmt = stmt.where(tbl.c.closing_balance != 0)
    elif filter == "opening":
        stmt = stmt.where(tbl.c.opening_balance != 0)
    elif filter == "changed":
        stmt = stmt.where(sa.or_(tbl.c.debit_amount != 0, tbl.c.credit_amount != 0))

    result = await db.execute(stmt)
    rows = result.fetchall()

    # 生成 Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "辅助余额表"

    headers = ["科目编号", "科目名称", "辅助类型", "辅助编码", "辅助名称", "关联维度", "期初余额", "借方发生额", "贷方发生额", "期末余额"]
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="F0ECF7", end_color="F0ECF7", fill_type="solid")
    for col, h in enumerate(headers, 1):
        cell = ws.cell(1, col, h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # 按 account_code + aux_code 分组，插入小计行
    from collections import OrderedDict
    from decimal import Decimal

    subtotal_font = Font(bold=True)
    subtotal_fill = PatternFill(start_color="FEF6E6", end_color="FEF6E6", fill_type="solid")

    groups = OrderedDict()  # key -> list of row tuples
    for row in rows:
        key = f"{row[0]}|{row[3]}"  # account_code|aux_code
        if key not in groups:
            groups[key] = []
        groups[key].append(row)

    excel_row = 2
    for key, group_rows in groups.items():
        # 多条时先写小计行
        if len(group_rows) > 1:
            s_open = sum(float(r[5] or 0) for r in group_rows)
            s_debit = sum(float(r[6] or 0) for r in group_rows)
            s_credit = sum(float(r[7] or 0) for r in group_rows)
            s_close = sum(float(r[8] or 0) for r in group_rows)
            first = group_rows[0]
            ws.cell(excel_row, 1, first[0])
            ws.cell(excel_row, 2, first[1])
            ws.cell(excel_row, 3, first[2])
            ws.cell(excel_row, 4, first[3])
            ws.cell(excel_row, 5, f"{first[4]} 小计({len(group_rows)}条)")
            ws.cell(excel_row, 6, "")
            ws.cell(excel_row, 7, s_open)
            ws.cell(excel_row, 8, s_debit)
            ws.cell(excel_row, 9, s_credit)
            ws.cell(excel_row, 10, s_close)
            for col in range(1, 11):
                ws.cell(excel_row, col).font = subtotal_font
                ws.cell(excel_row, col).fill = subtotal_fill
            excel_row += 1

        # 写明细行
        for row in group_rows:
            ws.cell(excel_row, 1, row[0])
            ws.cell(excel_row, 2, row[1])
            ws.cell(excel_row, 3, row[2])
            ws.cell(excel_row, 4, row[3])
            ws.cell(excel_row, 5, row[4])
            raw = row[9] or ""
            if raw and dim_type:
                parts = [p.strip() for p in raw.split(";") if p.strip() and not p.strip().startswith(dim_type + ":")]
                ws.cell(excel_row, 6, "; ".join(parts))
            else:
                ws.cell(excel_row, 6, raw)
            ws.cell(excel_row, 7, float(row[5]) if row[5] else None)
            ws.cell(excel_row, 8, float(row[6]) if row[6] else None)
            ws.cell(excel_row, 9, float(row[7]) if row[7] else None)
            ws.cell(excel_row, 10, float(row[8]) if row[8] else None)
            excel_row += 1

    total_rows = excel_row - 1

    # 设置列宽
    widths = [14, 18, 10, 14, 24, 40, 16, 16, 16, 16]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = w

    # 数字格式
    for col in [7, 8, 9, 10]:
        for row_idx in range(2, total_rows + 1):
            ws.cell(row_idx, col).number_format = '#,##0.00'

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"辅助余额表_{dim_type or '全部'}_{year}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"},
    )
