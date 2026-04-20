"""科目表管理 API 路由

Validates: Requirements 2.2, 2.5, 2.6
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import (
    AccountChartResponse,
    AccountImportResult,
    AccountTreeNode,
)
from app.models.core import User
from app.services import account_chart_service

router = APIRouter(prefix="/api/projects", tags=["account-chart"])


@router.get(
    "/{project_id}/account-chart/standard",
    response_model=list[AccountChartResponse],
)
async def get_standard_chart(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AccountChartResponse]:
    """获取项目的标准科目表。

    如果尚未加载，则根据项目会计准则自动加载标准科目模板。

    Validates: Requirements 2.2
    """
    # Always try incremental load (adds missing standard accounts)
    from app.services.project_wizard_service import get_wizard_state
    state = await get_wizard_state(project_id, db)
    accounting_standard = "enterprise"  # default
    basic_info = state.steps.get("basic_info")
    if basic_info and basic_info.data:
        accounting_standard = basic_info.data.get("accounting_standard", "enterprise")

    return await account_chart_service.load_standard_template(
        project_id, accounting_standard, db
    )


@router.post("/{project_id}/account-chart/preview")
async def preview_file(
    project_id: UUID,
    file: UploadFile = File(...),
    skip_rows: int | None = Query(default=None, description="跳过前N行，None=自动检测表头"),
    current_user: User = Depends(get_current_user),
):
    """Preview uploaded file: return first 20 rows per sheet + auto-matched column mapping.

    大文件优化：使用 smart_import_engine 的智能表头检测（支持双行合并表头），
    只读取前 20 行数据用于预览，不加载全部数据。
    """
    import io
    import openpyxl
    from app.services.smart_import_engine import (
        detect_header_rows, merge_header_rows, smart_match_column, _guess_data_type,
    )
    from app.services.account_chart_service import _COLUMN_MAP, _match_column, _guess_file_type

    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")

    content = await file.read()
    filename_lower = file.filename.lower()

    if filename_lower.endswith(".csv"):
        # CSV 用原有逻辑（小文件）—— 需要 seek 回起点因为 content 已经 read 过
        await file.seek(0)
        return await account_chart_service.preview_file(file, skip_rows=skip_rows)

    # Excel：小文件用完整模式（正确处理合并单元格），大文件用 read_only（快速）
    file_size_mb = len(content) / 1024 / 1024
    use_full_mode = file_size_mb < 10  # 10MB 以下用完整模式

    try:
        if use_full_mode:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        else:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法打开文件: {e}")

    sheets = []
    for ws in wb.worksheets:
        name_lower = ws.title.lower()
        if any(kw in name_lower for kw in ("说明", "目录", "封面")):
            continue

        max_col = ws.max_column or 50  # read_only 模式下可能没有 max_column

        # 第一步：读前 10 行原始数据（供用户确认表头位置）
        raw_rows = []
        if use_full_mode:
            for row_idx in range(1, min(11, (ws.max_row or 1) + 1)):
                row_vals = []
                for col in range(1, max_col + 1):
                    v = ws.cell(row_idx, col).value
                    row_vals.append(str(v).strip() if v is not None else "")
                raw_rows.append(row_vals)
        else:
            # read_only 模式用 iter_rows
            for i, row in enumerate(ws.iter_rows(max_row=10, values_only=True)):
                raw_rows.append([str(c).strip() if c else "" for c in row])

        # 第二步：智能检测表头位置
        hs, hc = detect_header_rows(ws)
        headers = merge_header_rows(ws, hs, hc)

        # 第三步：列名映射
        column_mapping = {}
        for h in headers:
            mapped = smart_match_column(h)
            if not mapped:
                mapped = _match_column(h)
            if mapped:
                column_mapping[h] = mapped

        # 第四步：读前 20 行数据（表头之后）
        data_start = hs + hc
        num_cols = len(headers)
        rows = []
        if use_full_mode:
            for row_idx in range(data_start + 1, min(data_start + 21, (ws.max_row or 0) + 1)):
                row_dict = {}
                all_none = True
                for col in range(1, num_cols + 1):
                    v = ws.cell(row_idx, col).value
                    h = headers[col - 1] if col - 1 < len(headers) else f"col_{col}"
                    row_dict[h] = str(v).strip() if v is not None else ""
                    if v is not None:
                        all_none = False
                if not all_none:
                    rows.append(row_dict)
        else:
            # read_only 模式
            count = 0
            for i, row_vals in enumerate(ws.iter_rows(values_only=True)):
                if i < data_start:
                    continue
                if count >= 20:
                    break
                padded = list(row_vals) + [None] * max(0, num_cols - len(row_vals))
                if all(c is None for c in padded[:num_cols]):
                    continue
                row_dict = {}
                for j in range(num_cols):
                    h = headers[j]
                    row_dict[h] = str(padded[j]).strip() if padded[j] is not None else ""
                rows.append(row_dict)
                count += 1

        total_rows = max(0, (ws.max_row or 0) - data_start) if use_full_mode else 0

        mapped_cols = set(column_mapping.values())
        file_type = _guess_data_type(mapped_cols) if mapped_cols else "unknown"

        sheets.append({
            "sheet_name": ws.title,
            "headers": headers,
            "rows": rows,
            "total_rows": total_rows,
            "column_mapping": column_mapping,
            "file_type_guess": file_type,
            "header_count": hc,
            "header_start": hs,
            "raw_first_rows": raw_rows,  # 前 10 行原始数据
        })

    wb.close()

    if not sheets:
        raise HTTPException(status_code=400, detail="文件中未解析到有效数据")

    return {"sheets": sheets, "active_sheet": 0}


@router.post(
    "/{project_id}/account-chart/import",
    response_model=AccountImportResult,
)
async def import_client_chart(
    project_id: UUID,
    file: UploadFile = File(...),
    column_mapping: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AccountImportResult:
    """导入科目表 + 四表数据。

    使用 smart_import_engine 统一处理（支持双行合并表头、核算维度拆分）。
    """
    import json

    parsed_mapping = None
    if column_mapping:
        try:
            parsed_mapping = json.loads(column_mapping)
        except (json.JSONDecodeError, TypeError):
            pass

    content = await file.read()
    filename = file.filename or "upload.xlsx"

    # 用 smart_import_engine 解析
    from app.services.smart_import_engine import smart_parse_files, write_four_tables

    parsed = smart_parse_files(
        [(filename, content)],
        custom_mapping=parsed_mapping,
    )

    # 1. 从余额表数据中提取科目表（account_code + account_name 去重）
    from app.services.account_chart_service import _infer_category, _infer_direction, _infer_level
    from app.models.audit_platform_models import AccountChart, AccountCategory, AccountSource
    import sqlalchemy as sa

    seen_codes = set()
    records = []
    by_category: dict[str, int] = {}

    for row in parsed["balance_rows"]:
        code = str(row.get("account_code", "")).strip()
        name = str(row.get("account_name", "")).strip()
        if not code or not name or code in seen_codes:
            continue
        seen_codes.add(code)
        category = _infer_category(code, name)
        direction = _infer_direction(category)
        level = row.get("level") or _infer_level(code, None)
        records.append(AccountChart(
            project_id=project_id, account_code=code, account_name=name,
            direction=direction, level=level, category=category,
            source=AccountSource.client,
        ))
        by_category[category.value] = by_category.get(category.value, 0) + 1

    # 也从序时账中提取科目
    for row in parsed["ledger_rows"]:
        code = str(row.get("account_code", "")).strip()
        name = str(row.get("account_name", "")).strip()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        if name:
            category = _infer_category(code, name)
            direction = _infer_direction(category)
            records.append(AccountChart(
                project_id=project_id, account_code=code, account_name=name,
                direction=direction, level=_infer_level(code, None), category=category,
                source=AccountSource.client,
            ))
            by_category[category.value] = by_category.get(category.value, 0) + 1

    # 写入科目表（先删旧数据）
    if records:
        tbl = AccountChart.__table__
        await db.execute(
            sa.update(tbl).where(tbl.c.project_id == project_id, tbl.c.source == "client")
            .values(is_deleted=True)
        )
        db.add_all(records)
        await db.commit()

    # 2. 写入四表数据
    data_sheets: dict[str, int] = {}
    if parsed["balance_rows"] or parsed["ledger_rows"]:
        try:
            from app.services.import_queue_service import ImportQueueService

            def _on_progress(stage: str, current: int, total: int, msg: str):
                pct = min(99, int(current / max(total, 1) * 100))
                ImportQueueService.update_progress(project_id, pct, msg)

            imported = await write_four_tables(
                project_id, parsed["year"],
                parsed["balance_rows"], parsed["aux_balance_rows"],
                parsed["ledger_rows"], parsed["aux_ledger_rows"],
                db,
                progress_callback=_on_progress,
            )
            data_sheets = imported
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("四表导入失败: %s", e)

    return AccountImportResult(
        total_imported=len(records),
        by_category=by_category,
        errors=[],
        data_sheets_imported=data_sheets,
    )


@router.post("/{project_id}/account-chart/import-async")
async def import_async(
    project_id: UUID,
    file: UploadFile = File(...),
    column_mapping: str | None = Form(None),
    current_user: User = Depends(get_current_user),
):
    """异步导入：立即返回任务ID，后台处理，前端轮询进度。

    适合大文件（>10MB），避免 HTTP 超时。
    """
    import asyncio
    import json
    from app.services.import_queue_service import ImportQueueService

    # 获取导入锁
    ok, msg = ImportQueueService.acquire_lock(project_id, str(current_user.id))
    if not ok:
        raise HTTPException(status_code=409, detail=msg)

    content = await file.read()
    filename = file.filename or "upload.xlsx"
    parsed_mapping = None
    if column_mapping:
        try:
            parsed_mapping = json.loads(column_mapping)
        except (json.JSONDecodeError, TypeError):
            pass

    # 后台任务
    async def _do_import():
        from app.core.database import async_session
        from app.services.smart_import_engine import smart_parse_files, write_four_tables
        from app.services.account_chart_service import _infer_category, _infer_direction, _infer_level
        from app.models.audit_platform_models import AccountChart, AccountSource
        import sqlalchemy as sa

        try:
            ImportQueueService.update_progress(project_id, 5, "正在解析文件...")

            parsed = smart_parse_files([(filename, content)], custom_mapping=parsed_mapping)

            ImportQueueService.update_progress(
                project_id, 20,
                f"解析完成: 余额表{len(parsed['balance_rows'])}行, 序时账{len(parsed['ledger_rows'])}行"
            )

            async with async_session() as db:
                # 科目表
                seen = set()
                records = []
                for row in parsed["balance_rows"] + parsed["ledger_rows"]:
                    code = str(row.get("account_code", "")).strip()
                    name = str(row.get("account_name", "")).strip()
                    if not code or not name or code in seen:
                        continue
                    seen.add(code)
                    cat = _infer_category(code, name)
                    records.append(AccountChart(
                        project_id=project_id, account_code=code, account_name=name,
                        direction=_infer_direction(cat), level=_infer_level(code, None),
                        category=cat, source=AccountSource.client,
                    ))

                if records:
                    tbl = AccountChart.__table__
                    await db.execute(sa.update(tbl).where(
                        tbl.c.project_id == project_id, tbl.c.source == "client"
                    ).values(is_deleted=True))
                    db.add_all(records)
                    await db.commit()

                ImportQueueService.update_progress(project_id, 30, f"科目表: {len(records)}个, 开始写入四表...")

                # 四表
                def _on_progress(stage, current, total, msg):
                    pct = 30 + min(65, int(current / max(total, 1) * 65))
                    ImportQueueService.update_progress(project_id, pct, msg)

                imported = await write_four_tables(
                    project_id, parsed["year"],
                    parsed["balance_rows"], parsed["aux_balance_rows"],
                    parsed["ledger_rows"], parsed["aux_ledger_rows"],
                    db, progress_callback=_on_progress,
                )

                ImportQueueService.update_progress(project_id, 100, f"导入完成: {imported}")

        except Exception as e:
            import traceback
            logger_name = __name__
            import logging
            logging.getLogger(logger_name).error("异步导入失败: %s\n%s", e, traceback.format_exc())
            ImportQueueService.update_progress(project_id, -1, f"导入失败: {e}")
        finally:
            # 延迟释放锁（让前端有时间读取最终状态）
            await asyncio.sleep(3)
            ImportQueueService.release_lock(project_id)

    # 启动后台任务
    asyncio.create_task(_do_import())

    return {
        "status": "accepted",
        "message": "导入任务已提交，请轮询进度",
        "project_id": str(project_id),
    }


@router.get(
    "/{project_id}/account-chart/client",
    response_model=dict[str, list[AccountTreeNode]],
)
async def get_client_chart(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, list[AccountTreeNode]]:
    """获取客户科目表（树形结构按类别分组）。

    Validates: Requirements 2.6
    """
    return await account_chart_service.get_client_chart_tree(project_id, db)


# ── 列映射保存/加载（持久化到 wizard_state） ──

from pydantic import BaseModel as _BaseModel


class SaveColumnMappingRequest(_BaseModel):
    """保存列映射"""
    file_type: str  # account_chart / ledger / balance / aux_balance
    sheet_name: str | None = None
    mapping: dict[str, str]  # {原列名: 标准字段名}


class ReferenceMatchRequest(_BaseModel):
    """参照匹配请求"""
    source_project_id: str
    source_year: int | None = None


@router.post("/{project_id}/column-mappings")
async def save_column_mapping(
    project_id: UUID,
    body: SaveColumnMappingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存用户确认的列映射（持久化到项目 wizard_state）"""
    from sqlalchemy import select
    from app.models.core import Project

    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    project = result.scalar_one_or_none()
    if not project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="项目不存在")

    # 保存到 wizard_state.column_mappings
    state = project.wizard_state or {}
    if "column_mappings" not in state:
        state["column_mappings"] = {}

    key = f"{body.file_type}"
    if body.sheet_name:
        key = f"{body.file_type}:{body.sheet_name}"
    state["column_mappings"][key] = body.mapping
    project.wizard_state = state

    await db.commit()
    return {"saved": True, "key": key, "field_count": len(body.mapping)}


@router.get("/{project_id}/column-mappings")
async def get_column_mappings(
    project_id: UUID,
    file_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取已保存的列映射"""
    from sqlalchemy import select
    from app.models.core import Project

    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    project = result.scalar_one_or_none()
    if not project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="项目不存在")

    state = project.wizard_state or {}
    mappings = state.get("column_mappings", {})

    if file_type:
        # 过滤指定文件类型
        filtered = {k: v for k, v in mappings.items() if k.startswith(file_type)}
        return filtered
    return mappings


@router.get("/{project_id}/column-mappings/reference-projects")
async def get_reference_projects(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取可参照的项目列表（有已保存列映射的其他项目）"""
    from sqlalchemy import select, func, cast, String
    from app.models.core import Project

    # 查找所有有 column_mappings 的项目（排除当前项目）
    result = await db.execute(
        select(Project.id, Project.name, Project.client_name, Project.wizard_state)
        .where(
            Project.id != project_id,
            Project.is_deleted == False,  # noqa: E712
            Project.wizard_state.isnot(None),
        )
        .order_by(Project.created_at.desc())
        .limit(20)
    )
    projects = []
    for row in result.all():
        ws = row.wizard_state or {}
        mappings = ws.get("column_mappings", {})
        if mappings:
            projects.append({
                "id": str(row.id),
                "name": row.name,
                "client_name": row.client_name,
                "mapping_count": len(mappings),
                "file_types": list(set(k.split(":")[0] for k in mappings.keys())),
            })
    return projects


@router.post("/{project_id}/column-mappings/reference-copy")
async def reference_copy_mappings(
    project_id: UUID,
    body: ReferenceMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从其他项目参照复制列映射"""
    from sqlalchemy import select
    from app.models.core import Project

    # 获取源项目的映射
    source = await db.execute(
        select(Project).where(Project.id == UUID(body.source_project_id))
    )
    source_project = source.scalar_one_or_none()
    if not source_project or not source_project.wizard_state:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="源项目不存在或无映射数据")

    source_mappings = (source_project.wizard_state or {}).get("column_mappings", {})
    if not source_mappings:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="源项目无已保存的列映射")

    # 复制到目标项目
    target = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )
    target_project = target.scalar_one_or_none()
    if not target_project:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="目标项目不存在")

    state = target_project.wizard_state or {}
    if "column_mappings" not in state:
        state["column_mappings"] = {}
    state["column_mappings"].update(source_mappings)
    target_project.wizard_state = state

    await db.commit()
    return {
        "copied": True,
        "source_project": body.source_project_id,
        "mapping_count": len(source_mappings),
    }


class AccountUpdateItem(_BaseModel):
    """单个科目更新"""
    account_code: str
    account_name: str | None = None
    direction: str | None = None


class BatchUpdateRequest(_BaseModel):
    """批量更新科目"""
    updates: list[AccountUpdateItem]


@router.put("/{project_id}/account-chart/batch-update")
async def batch_update_accounts(
    project_id: UUID,
    body: BatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """批量更新客户科目（名称、借贷方向）"""
    from app.models.audit_platform_models import AccountChart, AccountSource, AccountDirection

    updated = 0
    for item in body.updates:
        result = await db.execute(
            select(AccountChart).where(
                AccountChart.project_id == project_id,
                AccountChart.account_code == item.account_code,
                AccountChart.source == AccountSource.client,
                AccountChart.is_deleted == False,  # noqa: E712
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            continue

        if item.account_name is not None:
            row.account_name = item.account_name
        if item.direction is not None:
            try:
                row.direction = AccountDirection(item.direction)
            except ValueError:
                pass
        updated += 1

    await db.commit()
    return {"updated": updated, "total": len(body.updates)}
