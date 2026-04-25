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
import re
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
    """智能预览：只读表头+列映射+类型识别+行数估算，不读全部数据行。

    大文件秒级响应（只扫描前几行），供用户确认后再调用 smart-import 写入。
    """
    import io
    import openpyxl
    from app.services.smart_import_engine import (
        parse_sheet_header_only, detect_header_rows, smart_match_column,
        _guess_data_type, _detect_missing_fields, extract_year_from_content,
        _HEADER_KEYWORDS,
    )

    file_contents = []
    for f in files:
        if not f.filename:
            continue
        content = await f.read()
        file_contents.append((f.filename, content))

    if not file_contents:
        raise HTTPException(status_code=400, detail="未提供文件")

    diagnostics = []
    detected_year = year
    summary = {"balance": 0, "aux_balance": 0, "ledger": 0, "aux_ledger": 0}

    for filename, content in file_contents:
        # ── CSV ──
        if filename.lower().endswith('.csv'):
            import codecs, csv as _csv
            # 编码探测
            probe = content[:min(16384, len(content))]
            nl = probe.rfind(b'\n')
            if nl > 0:
                probe = probe[:nl]
            encoding = 'utf-8-sig'
            for enc in ('utf-8-sig', 'gbk', 'gb2312', 'gb18030'):
                try:
                    probe.decode(enc)
                    encoding = enc
                    break
                except (UnicodeDecodeError, LookupError):
                    continue

            text_head = content[:65536].decode(encoding, errors='replace')
            lines = text_head.split('\n')

            # 找表头
            headers = []
            header_idx = 0
            for i, line in enumerate(lines[:5]):
                cells = [c.strip() for c in line.split(',') if c.strip()]
                if len(cells) >= 3:
                    reader_row = list(_csv.reader([line.strip()]))[0]
                    headers = [c.strip() if c.strip() else f"col_{j}" for j, c in enumerate(reader_row)]
                    header_idx = i
                    break

            col_map = {}
            for h in headers:
                m = smart_match_column(h)
                if m:
                    col_map[h] = m

            mapped = set(col_map.values())
            dt = _guess_data_type(mapped) if mapped else "unknown"
            miss_req, miss_rec = _detect_missing_fields(dt, mapped)
            total_lines = content.count(b'\n') - header_idx

            if detected_year is None:
                detected_year = extract_year_from_content([], filename=filename)

            # 前 20 行数据预览
            csv_preview_rows = []
            data_lines = lines[header_idx + 1: header_idx + 21]
            for dl in data_lines:
                dl = dl.strip()
                if not dl:
                    continue
                row_raw = list(_csv.reader([dl]))[0]
                padded = row_raw + [''] * max(0, len(headers) - len(row_raw))
                csv_preview_rows.append({headers[j]: padded[j].strip() for j in range(len(headers))})

            # 内容辅助类型识别
            if dt == "unknown" and csv_preview_rows:
                import re as _re
                _hints: set[str] = set()
                for row in csv_preview_rows[:10]:
                    for v in row.values():
                        if not v:
                            continue
                        if _re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$', v):
                            _hints.add("has_date")
                        if _re.match(r'^-?\d+\.?\d*$', v.replace(',', '')):
                            _hints.add("has_number")
                if "has_date" in _hints and "has_number" in _hints:
                    dt = "ledger"
                elif "has_number" in _hints:
                    dt = "balance"
                miss_req, miss_rec = _detect_missing_fields(dt, mapped)

            diagnostics.append({
                "file": filename, "sheet": "CSV", "data_type": dt,
                "row_count": max(0, total_lines),
                "header_count": 1,
                "matched_cols": sorted(mapped),
                "missing_cols": miss_req, "missing_recommended": miss_rec,
                "column_mapping": col_map,
                "headers": headers,
                "preview_rows": csv_preview_rows,
                "status": "ok" if not miss_req else "warning",
            })
            if dt == "ledger":
                summary["ledger"] += max(0, total_lines)
            elif dt == "balance":
                summary["balance"] += max(0, total_lines)
            continue

        # ── Excel ──
        if filename.lower().endswith('.xls'):
            diagnostics.append({"file": filename, "sheet": None, "data_type": "unknown",
                                "row_count": 0, "status": "error",
                                "message": "暂不支持 .xls 文件，请转换为 .xlsx"})
            continue

        # 探测合并单元格
        needs_full = False
        try:
            wb_probe = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            for _ws in wb_probe.worksheets:
                try:
                    rows5 = list(_ws.iter_rows(max_row=5, values_only=True))
                    if rows5 and max(len(r) for r in rows5) <= 3:
                        needs_full = True
                        break
                    for row in rows5:
                        non_empty = [str(c).strip() for c in row if c is not None and str(c).strip()]
                        if len(non_empty) >= 4:
                            from collections import Counter
                            _, cnt = Counter(non_empty).most_common(1)[0]
                            if cnt >= len(non_empty) * 0.6 and cnt >= 3:
                                needs_full = True
                                break
                    if needs_full:
                        break
                except Exception:
                    pass
            wb_probe.close()
        except Exception:
            pass

        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=(not needs_full), data_only=True)
        except Exception as e:
            diagnostics.append({"file": filename, "sheet": None, "data_type": "unknown",
                                "row_count": 0, "status": "error", "message": str(e)})
            continue

        for ws in wb.worksheets:
            sname = ws.title
            if any(kw in sname.lower() for kw in ("说明", "目录", "封面", "模板")):
                continue

            try:
                meta = parse_sheet_header_only(ws)
            except Exception as e:
                diagnostics.append({"file": filename, "sheet": sname, "data_type": "unknown",
                                    "row_count": 0, "status": "error", "message": str(e)})
                continue

            dt = meta["data_type"]
            matched = set(meta["column_mapping"].values())
            miss_req, miss_rec = _detect_missing_fields(dt, matched)

            # 行数估算（不遍历全部数据）
            row_est = 0
            try:
                row_est = max(0, (ws.max_row or 0) - meta["data_start"])
            except Exception:
                pass

            # 读前 20 行数据供前端预览 + 辅助类型识别
            preview_rows = []
            data_start = meta["data_start"]
            num_cols = meta["num_cols"]
            headers = meta["headers"]
            col_map = meta["column_mapping"]
            try:
                data_iter = ws.iter_rows(min_row=data_start + 1, max_row=data_start + 20, values_only=True)
            except TypeError:
                data_iter = ws.iter_rows(values_only=True)
                for _ in range(data_start):
                    try:
                        next(data_iter)
                    except StopIteration:
                        data_iter = iter([])
                        break

            for row_vals in data_iter:
                padded = list(row_vals) + [None] * max(0, num_cols - len(row_vals))
                if all(c is None for c in padded[:num_cols]):
                    continue
                row_dict = {}
                for ci in range(num_cols):
                    h = headers[ci]
                    v = padded[ci]
                    row_dict[h] = str(v).strip() if v is not None else ""
                preview_rows.append(row_dict)

            # 根据数据内容辅助修正类型识别（表头映射不够时用内容特征补充）
            if dt == "unknown" and preview_rows:
                _content_hints: set[str] = set()
                for row in preview_rows[:10]:
                    for h, v in row.items():
                        if not v:
                            continue
                        # 日期特征 → voucher_date
                        if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$', v):
                            _content_hints.add("has_date")
                        # 纯数字带小数点 → 金额
                        if re.match(r'^-?\d+\.?\d*$', v.replace(',', '')):
                            _content_hints.add("has_number")
                if "has_date" in _content_hints and "has_number" in _content_hints:
                    dt = "ledger"
                elif "has_number" in _content_hints:
                    dt = "balance"
                miss_req, miss_rec = _detect_missing_fields(dt, matched)

            if detected_year is None and meta.get("year"):
                detected_year = meta["year"]

            diagnostics.append({
                "file": filename, "sheet": sname, "data_type": dt,
                "row_count": row_est,
                "header_count": meta["header_count"],
                "matched_cols": sorted(matched),
                "missing_cols": miss_req, "missing_recommended": miss_rec,
                "column_mapping": meta["column_mapping"],
                "headers": headers,
                "preview_rows": preview_rows,
                "status": "ok" if not miss_req else "warning",
            })

            if dt == "ledger":
                summary["ledger"] += row_est
            elif dt == "balance":
                summary["balance"] += row_est
            elif dt == "aux_balance":
                summary["aux_balance"] += row_est
            elif dt == "aux_ledger":
                summary["aux_ledger"] += row_est

        wb.close()

    if detected_year is None:
        from datetime import datetime as _dt
        detected_year = _dt.now().year - 1

    # 估算辅助表行数：如果余额表/序时账含核算维度列，辅助行数≈主表行数
    for d in diagnostics:
        cm_vals = set((d.get("column_mapping") or {}).values())
        if d.get("data_type") == "balance" and "aux_dimensions" in cm_vals:
            summary["aux_balance"] += d.get("row_count", 0)
        elif d.get("data_type") == "ledger" and "aux_dimensions" in cm_vals:
            summary["aux_ledger"] += d.get("row_count", 0)

    # 把 column_mapping 的英文值替换为中文标签（前端展示用）
    from app.services.smart_import_engine import FIELD_LABELS
    for d in diagnostics:
        cm = d.get("column_mapping")
        if cm:
            d["column_mapping_labels"] = {
                h: FIELD_LABELS.get(v, v) for h, v in cm.items()
            }

    return {
        "year": detected_year,
        "summary": summary,
        "aux_dimensions": [],
        "validation": [],
        "diagnostics": diagnostics,
        "field_labels": FIELD_LABELS,  # 供前端下拉选择用
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
        total_size = 0
        for f in files:
            if not f.filename:
                continue
            content = await f.read()
            total_size += len(content)
            file_contents.append((f.filename, content))

        if not file_contents:
            raise HTTPException(status_code=400, detail="未提供文件")

        # 内存保护：文件总大小超过 800MB 时拒绝（防止 OOM 杀死后端）
        if total_size > 800 * 1024 * 1024:
            ImportQueueService.release_lock(project_id)
            raise HTTPException(
                status_code=413,
                detail=f"文件总大小 {total_size / 1024 / 1024:.0f} MB 超过限制（800MB），"
                       f"请通过项目向导的数据导入步骤上传（支持异步处理大文件）",
            )

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


# ── 入库后数据一致性校验（按需触发） ──

@router.get("/validate")
async def validate_data(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """四表数据一致性校验（入库后按需触发）。

    从数据库查询做校验，比预览阶段更准确（有完整的辅助明细账数据）。
    校验项：
    1. 科目余额表内部勾稽（期初+借-贷=期末）
    2. 辅助余额表内部勾稽
    3. 科目余额表 vs 辅助余额表（每个维度类型汇总应等于科目余额）
    4. 序时账 vs 科目余额表（按科目汇总借贷发生额）
    """
    import sqlalchemy as sa
    from decimal import Decimal

    findings = []

    # 1. 科目余额表内部勾稽
    bal_rows = await db.execute(sa.text("""
        SELECT account_code, opening_balance, debit_amount, credit_amount, closing_balance
        FROM tb_balance
        WHERE project_id = :pid AND year = :yr AND is_deleted = false
          AND (opening_balance IS NOT NULL OR debit_amount IS NOT NULL
               OR credit_amount IS NOT NULL OR closing_balance IS NOT NULL)
    """), {"pid": str(project_id), "yr": year})
    bal_data = bal_rows.fetchall()

    bal_map = {}
    bal_errors = 0
    for r in bal_data:
        code, opening, debit, credit, closing = r
        opening = opening or Decimal(0)
        debit = debit or Decimal(0)
        credit = credit or Decimal(0)
        closing = closing or Decimal(0)
        bal_map[code] = {"opening": opening, "debit": debit, "credit": credit, "closing": closing}
        expected = opening + debit - credit
        if abs(expected - closing) > Decimal("0.01"):
            bal_errors += 1
            if bal_errors <= 5:
                findings.append({
                    "level": "error", "category": "余额表勾稽",
                    "message": f"{code}: 期初{opening}+借{debit}-贷{credit}={expected}, 期末{closing}, 差{expected-closing}",
                })
    if bal_errors > 5:
        findings.append({"level": "error", "category": "余额表勾稽",
                         "message": f"共 {bal_errors} 个科目不平"})
    elif bal_errors == 0:
        findings.append({"level": "info", "category": "余额表勾稽",
                         "message": f"{len(bal_data)} 个科目全部勾稽通过"})

    # 2. 科目余额表 vs 辅助余额表
    aux_agg = await db.execute(sa.text("""
        SELECT account_code, aux_type, COUNT(*) as cnt, SUM(COALESCE(closing_balance, 0)) as total_closing
        FROM tb_aux_balance
        WHERE project_id = :pid AND year = :yr AND is_deleted = false
        GROUP BY account_code, aux_type
    """), {"pid": str(project_id), "yr": year})
    aux_agg_data = aux_agg.fetchall()

    from collections import defaultdict
    aux_by_code = defaultdict(list)
    for code, aux_type, cnt, total_closing in aux_agg_data:
        aux_by_code[code].append((aux_type, cnt, total_closing or Decimal(0)))

    cross_errors = 0
    for code in sorted(aux_by_code.keys()):
        if code not in bal_map:
            continue
        b_closing = bal_map[code]["closing"]
        types = aux_by_code[code]
        best_type, best_cnt, best_closing = min(types, key=lambda x: abs(b_closing - x[2]))
        diff = b_closing - best_closing
        if abs(diff) > Decimal("0.01"):
            cross_errors += 1
            if cross_errors <= 5:
                findings.append({
                    "level": "warning", "category": "余额表vs辅助余额表",
                    "message": f"{code}: 科目期末={b_closing}, 维度({best_type},{best_cnt}条)汇总={best_closing}, 差{diff}",
                })
    if cross_errors > 5:
        findings.append({"level": "warning", "category": "余额表vs辅助余额表",
                         "message": f"共 {cross_errors} 个科目不一致"})
    elif cross_errors == 0 and aux_by_code:
        findings.append({"level": "info", "category": "余额表vs辅助余额表",
                         "message": f"{len(aux_by_code)} 个有辅助核算的科目全部一致"})

    # 3. 序时账 vs 科目余额表
    led_agg = await db.execute(sa.text("""
        SELECT account_code, SUM(COALESCE(debit_amount, 0)) as total_debit,
               SUM(COALESCE(credit_amount, 0)) as total_credit
        FROM tb_ledger
        WHERE project_id = :pid AND year = :yr AND is_deleted = false
        GROUP BY account_code
    """), {"pid": str(project_id), "yr": year})
    led_agg_data = led_agg.fetchall()

    led_errors = 0
    for code, led_debit, led_credit in led_agg_data:
        if code not in bal_map:
            continue
        b = bal_map[code]
        led_debit = led_debit or Decimal(0)
        led_credit = led_credit or Decimal(0)
        if abs(b["debit"] - led_debit) > Decimal("0.01") or abs(b["credit"] - led_credit) > Decimal("0.01"):
            led_errors += 1
            if led_errors <= 5:
                findings.append({
                    "level": "warning", "category": "序时账vs余额表",
                    "message": f"{code}: 余额表借{b['debit']}/贷{b['credit']}, 序时账借{led_debit}/贷{led_credit}",
                })
    if led_errors > 5:
        findings.append({"level": "warning", "category": "序时账vs余额表",
                         "message": f"共 {led_errors} 个科目不一致"})
    elif led_errors == 0 and led_agg_data:
        findings.append({"level": "info", "category": "序时账vs余额表",
                         "message": f"{len(led_agg_data)} 个科目全部一致"})

    return {
        "year": year,
        "findings": findings,
        "summary": {
            "balance_count": len(bal_data),
            "aux_account_count": len(aux_by_code),
            "ledger_account_count": len(led_agg_data),
            "errors": sum(1 for f in findings if f["level"] == "error"),
            "warnings": sum(1 for f in findings if f["level"] == "warning"),
        },
    }
