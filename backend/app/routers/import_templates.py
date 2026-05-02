"""统一导入模板 API — 模板下载 + 格式校验 + 数据解析

为所有业务数据提供标准化的导入入口：
  GET  /api/import-templates/{type}/download  — 下载标准模板
  POST /api/import-templates/{type}/validate  — 上传校验（不入库）
  POST /api/import-templates/{type}/import    — 校验+入库
  GET  /api/import-templates/types             — 获取所有支持的导入类型
"""

from __future__ import annotations

import io
import logging
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.import_template_service import (
    IMPORT_TYPE_LABELS,
    TEMPLATE_COLUMNS,
    ImportType,
    generate_template,
    parse_import_data,
    validate_import_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/import-templates", tags=["导入模板"])


@router.get("/types")
async def list_import_types(
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """获取所有支持的导入类型及其列定义"""
    result = []
    for t in ImportType:
        cols = TEMPLATE_COLUMNS.get(t, [])
        result.append({
            "type": t.value,
            "label": IMPORT_TYPE_LABELS.get(t, t.value),
            "columns": [
                {"name": c[0], "required": c[1], "data_type": c[2], "example": c[3]}
                for c in cols
            ],
        })
    return result


@router.get("/{import_type}/download")
async def download_template(
    import_type: ImportType,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """下载标准导入模板 Excel 文件"""
    label = IMPORT_TYPE_LABELS.get(import_type, import_type.value)
    try:
        content = generate_template(import_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # RFC 5987 编码中文文件名，兼容所有浏览器
    filename_encoded = quote(f"{label}导入模板.xlsx")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}",
        },
    )


@router.post("/{import_type}/validate")
async def validate_file(
    import_type: ImportType,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    """上传 Excel 文件并校验格式（不入库）"""
    content = await _read_upload(file)
    result = validate_import_file(import_type, content, file.filename or "")
    return result.to_dict()


@router.post("/{import_type}/import")
async def import_data(
    import_type: ImportType,
    file: UploadFile = File(...),
    project_id: UUID | None = Query(None, description="项目ID"),
    year: int | None = Query(None, description="年度"),
    sub_type: str | None = Query(None, description="子类型"),
    mode: str = Query("append", description="导入模式: append(追加) / overwrite(覆盖)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """校验 + 导入数据到系统（事务保护，全部成功或全部回滚）"""
    content = await _read_upload(file)

    # 1. 校验
    validation = validate_import_file(import_type, content, file.filename or "")
    if not validation.valid:
        return {
            "success": False,
            "message": "文件格式校验未通过",
            "validation": validation.to_dict(),
        }

    # 2. 解析（复用已读取的 file_bytes，不再重新读文件）
    rows = parse_import_data(import_type, content)
    if not rows:
        return {
            "success": False,
            "message": "文件中没有有效数据",
            "validation": validation.to_dict(),
        }

    # 3. 事务保护：分发到业务服务入库
    try:
        result = await _dispatch_import(
            import_type=import_type,
            rows=rows,
            project_id=project_id,
            year=year,
            sub_type=sub_type,
            mode=mode,
            user=current_user,
            db=db,
        )
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.exception("导入失败: %s", e)
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")

    label = IMPORT_TYPE_LABELS.get(import_type, import_type.value)
    return {
        "success": True,
        "message": f"成功导入 {result['imported']} 条{label}数据"
                   + (f"，{result['skipped']} 条跳过" if result.get("skipped") else "")
                   + (f"，{result['failed']} 条失败" if result.get("failed") else ""),
        "imported_count": result["imported"],
        "skipped_count": result.get("skipped", 0),
        "failed_count": result.get("failed", 0),
        "failed_rows": result.get("failed_rows", [])[:20],
        "validation": validation.to_dict(),
    }


async def _read_upload(file: UploadFile) -> bytes:
    """读取上传文件并校验基本格式"""
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 或 .xls 格式")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件大小超过 50MB 限制")
    return content


# ── 分发 + 各类型导入实现 ──────────────────────────────────


async def _dispatch_import(
    *,
    import_type: ImportType,
    rows: list[dict],
    project_id: UUID | None,
    year: int | None,
    sub_type: str | None,
    mode: str,
    user: User,
    db: AsyncSession,
) -> dict:
    """根据导入类型分发到对应的业务服务，返回 {imported, skipped, failed, failed_rows}"""

    def _require_project() -> UUID:
        if not project_id:
            raise HTTPException(status_code=400, detail=f"{IMPORT_TYPE_LABELS.get(import_type, '')}导入需要指定 project_id")
        return project_id

    y = year or 2025

    if import_type == ImportType.adjustments:
        return await _import_adjustments(rows, _require_project(), y, user, db)
    elif import_type == ImportType.report:
        return await _import_report(rows, _require_project(), y, sub_type, db)
    elif import_type == ImportType.disclosure_note:
        return await _import_disclosure_notes(rows, _require_project(), y, db)
    elif import_type == ImportType.workpaper:
        return await _import_workpapers(rows, _require_project(), y, user, db)
    elif import_type == ImportType.formula:
        return await _import_formulas(rows, _require_project(), y, sub_type, db)
    elif import_type == ImportType.staff:
        return await _import_staff(rows, user, db)
    elif import_type == ImportType.trial_balance:
        return await _import_trial_balance(rows, _require_project(), y, db)

    raise HTTPException(status_code=400, detail=f"暂不支持 {import_type.value} 类型的导入")


def _safe_float(val: any, default: float = 0.0) -> float:
    """安全转换数值，支持千分位逗号"""
    if val is None:
        return default
    try:
        return float(str(val).replace(",", "").replace("，", "").replace("¥", "").replace("$", "").strip() or default)
    except (ValueError, TypeError):
        return default


def _safe_int(val: any, default: int = 0) -> int:
    try:
        return int(float(str(val).strip() or default))
    except (ValueError, TypeError):
        return default


async def _import_adjustments(
    rows: list[dict], project_id: UUID, year: int, user: User, db: AsyncSession,
) -> dict:
    """导入调整分录"""
    from app.services.adjustment_service import AdjustmentService
    svc = AdjustmentService(db)
    imported, failed, failed_rows = 0, 0, []
    for i, row in enumerate(rows, 1):
        try:
            await svc.create_adjustment(
                project_id=project_id,
                year=year,
                data={
                    "entry_number": str(row.get("分录编号", "") or ""),
                    "adjustment_type": str(row.get("调整类型", "AJE") or "AJE").upper(),
                    "debit_account_code": str(row.get("借方科目代码", "") or ""),
                    "debit_account_name": str(row.get("借方科目名称", "") or ""),
                    "debit_amount": _safe_float(row.get("借方金额")),
                    "credit_account_code": str(row.get("贷方科目代码", "") or ""),
                    "credit_account_name": str(row.get("贷方科目名称", "") or ""),
                    "credit_amount": _safe_float(row.get("贷方金额")),
                    "description": str(row.get("摘要", "") or ""),
                    "prepared_by": str(row.get("编制人", "") or "") or user.username,
                },
                user_id=user.id,
            )
            imported += 1
        except Exception as e:
            failed += 1
            failed_rows.append({"row": i, "error": str(e)})
            logger.warning("调整分录导入第 %d 行失败: %s", i, e)
    return {"imported": imported, "skipped": 0, "failed": failed, "failed_rows": failed_rows}


async def _import_report(
    rows: list[dict], project_id: UUID, year: int, sub_type: str | None, db: AsyncSession,
) -> dict:
    from app.services.report_engine import ReportEngine
    engine = ReportEngine(db)
    imported, failed, failed_rows = 0, 0, []
    for i, row in enumerate(rows, 1):
        try:
            await engine.upsert_report_cell(
                project_id=project_id,
                year=year,
                report_type=sub_type or "balance_sheet",
                line_number=_safe_int(row.get("行次")),
                current_amount=_safe_float(row.get("本期金额")),
                prior_amount=_safe_float(row.get("上期金额")),
            )
            imported += 1
        except Exception as e:
            failed += 1
            failed_rows.append({"row": i, "error": str(e)})
    return {"imported": imported, "skipped": 0, "failed": failed, "failed_rows": failed_rows}


async def _import_disclosure_notes(
    rows: list[dict], project_id: UUID, year: int, db: AsyncSession,
) -> dict:
    from app.services.disclosure_engine import DisclosureEngine
    engine = DisclosureEngine(db)
    imported, failed, failed_rows = 0, 0, []
    for i, row in enumerate(rows, 1):
        try:
            await engine.upsert_note_row(
                project_id=project_id,
                year=year,
                section_code=str(row.get("章节编号", "") or ""),
                table_code=str(row.get("表格编号", "") or ""),
                row_name=str(row.get("行名称", "") or ""),
                ending_balance=_safe_float(row.get("期末余额")),
                beginning_balance=_safe_float(row.get("期初余额")),
                increase=_safe_float(row.get("本期增加")),
                decrease=_safe_float(row.get("本期减少")),
            )
            imported += 1
        except Exception as e:
            failed += 1
            failed_rows.append({"row": i, "error": str(e)})
    return {"imported": imported, "skipped": 0, "failed": failed, "failed_rows": failed_rows}


async def _import_workpapers(
    rows: list[dict], project_id: UUID, year: int, user: User, db: AsyncSession,
) -> dict:
    from app.services.working_paper_service import WorkingPaperService
    svc = WorkingPaperService(db)
    imported, failed, failed_rows = 0, 0, []
    for i, row in enumerate(rows, 1):
        try:
            await svc.upsert_wp_row(
                project_id=project_id,
                year=year,
                wp_code=str(row.get("底稿编码", "") or ""),
                wp_name=str(row.get("底稿名称", "") or ""),
                row_index=_safe_int(row.get("行序号")),
                row_name=str(row.get("行名称", "") or ""),
                unadjusted=_safe_float(row.get("未审数")),
                adjustment=_safe_float(row.get("调整数")),
                audited=_safe_float(row.get("审定数")),
                note=str(row.get("说明", "") or ""),
                user_id=user.id,
            )
            imported += 1
        except Exception as e:
            failed += 1
            failed_rows.append({"row": i, "error": str(e)})
    return {"imported": imported, "skipped": 0, "failed": failed, "failed_rows": failed_rows}


async def _import_formulas(
    rows: list[dict], project_id: UUID, year: int, sub_type: str | None, db: AsyncSession,
) -> dict:
    from app.services.formula_unified import save_formula_batch
    formulas = []
    for row in rows:
        formulas.append({
            "formula_id": str(row.get("公式编号", "") or ""),
            "module": str(row.get("适用模块", "report") or "report"),
            "report_type": str(row.get("报表类型", "") or sub_type or ""),
            "line_or_section": str(row.get("行次/章节", "") or ""),
            "column": str(row.get("列标识", "") or ""),
            "expression": str(row.get("公式表达式", "") or ""),
            "description": str(row.get("说明", "") or ""),
        })
    try:
        count = await save_formula_batch(project_id, year, formulas, db)
        return {"imported": count, "skipped": 0, "failed": 0, "failed_rows": []}
    except Exception as e:
        return {"imported": 0, "skipped": 0, "failed": len(formulas), "failed_rows": [{"row": 0, "error": str(e)}]}


async def _import_staff(rows: list[dict], user: User, db: AsyncSession) -> dict:
    from app.services.staff_service import StaffService
    svc = StaffService(db)
    imported, skipped, failed, failed_rows = 0, 0, 0, []
    for i, row in enumerate(rows, 1):
        name = str(row.get("姓名", "") or "").strip()
        if not name:
            skipped += 1
            continue
        try:
            await svc.create_staff(
                data={
                    "name": name,
                    "employee_id": str(row.get("工号", "") or ""),
                    "department": str(row.get("部门", "") or ""),
                    "position": str(row.get("职级", "") or ""),
                    "partner_name": str(row.get("所属合伙人", "") or ""),
                    "specialty": str(row.get("专业领域", "") or ""),
                    "phone": str(row.get("联系电话", "") or ""),
                    "email": str(row.get("邮箱", "") or ""),
                },
                created_by=user.id,
            )
            imported += 1
        except Exception as e:
            failed += 1
            failed_rows.append({"row": i, "error": str(e)})
    return {"imported": imported, "skipped": skipped, "failed": failed, "failed_rows": failed_rows}


async def _import_trial_balance(
    rows: list[dict], project_id: UUID, year: int, db: AsyncSession,
) -> dict:
    from app.services.trial_balance_service import TrialBalanceService
    svc = TrialBalanceService(db)
    imported, failed, failed_rows = 0, 0, []
    for i, row in enumerate(rows, 1):
        try:
            await svc.upsert_trial_balance_row(
                project_id=project_id,
                year=year,
                account_code=str(row.get("科目代码", "") or ""),
                account_name=str(row.get("科目名称", "") or ""),
                direction=str(row.get("方向", "") or ""),
                category=str(row.get("科目类别", "") or ""),
                beginning_balance=_safe_float(row.get("期初余额")),
                debit_amount=_safe_float(row.get("本期借方")),
                credit_amount=_safe_float(row.get("本期贷方")),
                ending_balance=_safe_float(row.get("期末余额")),
                unadjusted_amount=_safe_float(row.get("未审数")),
                adjustment_amount=_safe_float(row.get("调整数")),
                audited_amount=_safe_float(row.get("审定数")),
            )
            imported += 1
        except Exception as e:
            failed += 1
            failed_rows.append({"row": i, "error": str(e)})
    return {"imported": imported, "skipped": 0, "failed": failed, "failed_rows": failed_rows}
