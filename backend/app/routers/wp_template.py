"""底稿模板 API 路由

- POST   /api/templates              — 上传模板
- GET    /api/templates              — 模板列表
- GET    /api/templates/{code}       — 获取模板详情
- POST   /api/templates/{code}/versions — 创建新版本
- DELETE /api/templates/{id}         — 删除模板
- GET    /api/template-sets          — 模板集列表
- GET    /api/template-sets/{id}     — 模板集详情
- POST   /api/template-sets          — 创建模板集
- PUT    /api/template-sets/{id}     — 更新模板集
- POST   /api/template-sets/seed     — 初始化内置模板集

Validates: Requirements 1.1-1.8
"""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WpIndex, WorkingPaper, WpStatus, WpSourceType
from app.models.workpaper_schemas import TemplateResponse, TemplateSetResponse
from app.services.template_engine import TemplateEngine
import sqlalchemy as sa

router = APIRouter(tags=["templates"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class TemplateUploadRequest(BaseModel):
    template_code: str
    template_name: str
    audit_cycle: str | None = None
    applicable_standard: str | None = None
    description: str | None = None
    named_ranges: list[dict] | None = None


class VersionCreateRequest(BaseModel):
    change_type: str = "minor"  # "major" or "minor"


class TemplateSetCreateRequest(BaseModel):
    set_name: str
    template_codes: list[str] | None = None
    applicable_audit_type: str | None = None
    applicable_standard: str | None = None
    description: str | None = None


class TemplateSetUpdateRequest(BaseModel):
    set_name: str | None = None
    template_codes: list[str] | None = None
    applicable_audit_type: str | None = None
    applicable_standard: str | None = None
    description: str | None = None


class GenerateWorkpapersRequest(BaseModel):
    template_set_id: UUID
    year: int = 2025


# ---------------------------------------------------------------------------
# Template endpoints
# ---------------------------------------------------------------------------


@router.post("/api/templates", response_model=TemplateResponse)
async def upload_template(
    data: TemplateUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传模板文件（MVP: 仅保存元数据）"""
    engine = TemplateEngine()
    template = await engine.upload_template(
        db=db,
        template_code=data.template_code,
        template_name=data.template_name,
        audit_cycle=data.audit_cycle,
        applicable_standard=data.applicable_standard,
        description=data.description,
        named_ranges=data.named_ranges,
    )
    await db.commit()
    return template


@router.get("/api/templates", response_model=list[TemplateResponse])
async def list_templates(
    audit_cycle: str | None = None,
    applicable_standard: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """模板列表（支持按循环、准则筛选）"""
    engine = TemplateEngine()
    return await engine.list_templates(
        db=db,
        audit_cycle=audit_cycle,
        applicable_standard=applicable_standard,
    )


@router.get("/api/templates/{code}", response_model=TemplateResponse)
async def get_template(
    code: str,
    version: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取模板详情（默认最新版本）"""
    engine = TemplateEngine()
    tpl = await engine.get_template(db=db, template_code=code, version=version)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"模板 {code} 不存在")
    return tpl


@router.post("/api/templates/{code}/versions", response_model=TemplateResponse)
async def create_version(
    code: str,
    data: VersionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新版本"""
    engine = TemplateEngine()
    try:
        tpl = await engine.create_version(
            db=db,
            template_code=code,
            change_type=data.change_type,
        )
        await db.commit()
        return tpl
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/templates/{template_id}")
async def delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除模板（校验无引用）"""
    engine = TemplateEngine()
    try:
        await engine.delete_template(db=db, template_id=template_id)
        await db.commit()
        return {"message": "模板已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Template set endpoints
# ---------------------------------------------------------------------------


@router.get("/api/template-sets", response_model=list[TemplateSetResponse])
async def list_template_sets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """模板集列表"""
    engine = TemplateEngine()
    return await engine.get_template_sets(db=db)


@router.get("/api/template-sets/{set_id}", response_model=TemplateSetResponse)
async def get_template_set(
    set_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """模板集详情"""
    engine = TemplateEngine()
    ts = await engine.get_template_set(db=db, set_id=set_id)
    if ts is None:
        raise HTTPException(status_code=404, detail="模板集不存在")
    return ts


@router.post("/api/template-sets", response_model=TemplateSetResponse)
async def create_template_set(
    data: TemplateSetCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建模板集"""
    engine = TemplateEngine()
    ts = await engine.create_template_set(
        db=db,
        set_name=data.set_name,
        template_codes=data.template_codes,
        applicable_audit_type=data.applicable_audit_type,
        applicable_standard=data.applicable_standard,
        description=data.description,
    )
    await db.commit()
    return ts


@router.put("/api/template-sets/{set_id}", response_model=TemplateSetResponse)
async def update_template_set(
    set_id: UUID,
    data: TemplateSetUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新模板集"""
    engine = TemplateEngine()
    try:
        ts = await engine.update_template_set(
            db=db,
            set_id=set_id,
            set_name=data.set_name,
            template_codes=data.template_codes,
            applicable_audit_type=data.applicable_audit_type,
            applicable_standard=data.applicable_standard,
            description=data.description,
        )
        await db.commit()
        return ts
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/template-sets/seed")
async def seed_template_sets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """初始化6个内置模板集（幂等）"""
    engine = TemplateEngine()
    created = await engine.seed_builtin_template_sets(db=db)
    await db.commit()
    return {"message": f"已创建 {len(created)} 个内置模板集", "count": len(created)}


# ---------------------------------------------------------------------------
# Generate project workpapers
# ---------------------------------------------------------------------------


@router.post("/api/projects/{project_id}/working-papers/generate")
async def generate_project_workpapers(
    project_id: UUID,
    data: GenerateWorkpapersRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从模板集生成项目底稿

    如果请求体已携带 template_set_id（用户在前端弹窗选择了模板集），
    跳过 wizard_state 的前置检查——因为用户已做出选择，不强制要求走向导步骤。
    """
    from app.services.prerequisite_checker import PrerequisiteChecker

    # 仅在请求未携带 template_set_id 时检查 wizard 前置条件
    if not data.template_set_id:
        check = await PrerequisiteChecker().check(db, project_id, data.year, "generate_workpapers")
        if not check["ok"]:
            raise HTTPException(status_code=400, detail=check)

    engine = TemplateEngine()
    try:
        workpapers = await engine.generate_project_workpapers(
            db=db,
            project_id=project_id,
            template_set_id=data.template_set_id,
            year=data.year,
        )
        await db.commit()
        return {
            "message": f"已生成 {len(workpapers)} 个底稿",
            "created": len(workpapers),
            "count": len(workpapers),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class GenerateFromCodesRequest(BaseModel):
    wp_codes: list[str]
    year: int = 2025


@router.post("/api/projects/{project_id}/working-papers/generate-from-codes")
async def generate_from_codes(
    project_id: UUID,
    data: GenerateFromCodesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从推荐的底稿编码列表直接生成底稿文件（不需要模板集）

    改造要点（wp-generation-pipeline spec）：
    - 前置门禁：trial_balance > 0 行
    - savepoint 隔离：单条失败不影响整批
    - populate_parsed_data：填充 html_data 供渲染器消费
    - 结构化返回：created/skipped/failures + codes 列表
    """
    import json
    import logging
    import os
    import shutil
    from pathlib import Path

    from app.services.prerequisite_checker import PrerequisiteChecker
    from app.services.wp_parsed_data_service import populate_parsed_data

    _logger = logging.getLogger(__name__)

    # [新增] 前置门禁
    check = await PrerequisiteChecker().check(db, project_id, data.year, "generate_from_codes")
    if not check["ok"]:
        raise HTTPException(status_code=422, detail=check)

    lib_path = Path(__file__).parent.parent.parent / "data" / "gt_template_library.json"
    template_lib: dict[str, dict] = {}
    if lib_path.exists():
        try:
            with open(lib_path, "r", encoding="utf-8-sig") as f:
                lib_data = json.load(f)
            for item in lib_data.get("templates", lib_data) if isinstance(lib_data, dict) else lib_data:
                template_lib[item.get("code", item.get("wp_code", ""))] = item
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("加载模板库 JSON 失败: %s", e)

    project_wp_dir = Path("storage") / "projects" / str(project_id) / "workpapers"
    created = 0
    skipped = 0
    failures: list[dict] = []
    created_codes: list[str] = []
    skipped_codes: list[str] = []

    for code in data.wp_codes:
        # 检查是否已存在
        existing = await db.execute(
            sa.select(WpIndex).where(
                WpIndex.project_id == project_id,
                WpIndex.wp_code == code,
                WpIndex.is_deleted == sa.false(),
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            skipped_codes.append(code)
            continue

        # [新增] savepoint 隔离单条处理
        try:
            async with db.begin_nested():
                lib_entry = template_lib.get(code, {})
                wp_name = lib_entry.get("name", lib_entry.get("wp_name", f"底稿{code}"))
                cycle = lib_entry.get("cycle_prefix", code[0] if code else "X")

                # 创建 wp_index
                wp_index = WpIndex(
                    project_id=project_id,
                    wp_code=code,
                    wp_name=wp_name,
                    audit_cycle=cycle,
                    status=WpStatus.not_started,
                )
                db.add(wp_index)
                await db.flush()

                # 文件目录
                cycle_dir = project_wp_dir / cycle
                cycle_dir.mkdir(parents=True, exist_ok=True)
                dest_file = cycle_dir / f"{code}.xlsx"

                # 复制模板文件（优先从知识库底稿模板目录查找）
                copied = False
                src_path = lib_entry.get("file_path", "")
                template_name = lib_entry.get("name", "") or wp_name

                # 1. 知识库底稿模板目录
                kb_base = Path(os.path.expanduser("~/.gt_audit_helper/knowledge/workpaper_templates"))
                kb_file = kb_base / cycle / f"{template_name}.xlsx" if template_name else None
                if src_path:
                    kb_file_by_name = kb_base / cycle / Path(src_path).name
                else:
                    kb_file_by_name = None

                for candidate in [kb_file, kb_file_by_name]:
                    if candidate and candidate.exists():
                        shutil.copy2(candidate, dest_file)
                        copied = True
                        break

                # 2. 回退：从原始模板路径查找（项目根目录）
                if not copied and src_path:
                    src = Path(src_path)
                    if not src.exists():
                        root_src = Path(__file__).resolve().parent.parent.parent.parent / src_path
                        if root_src.exists():
                            src = root_src
                    if src.exists():
                        shutil.copy2(src, dest_file)
                        copied = True

                if not copied:
                    try:
                        import openpyxl
                        wb = openpyxl.Workbook()
                        ws = wb.active
                        ws.title = code
                        ws["A1"] = f"底稿编号: {code}"
                        ws["A2"] = f"底稿名称: {wp_name}"
                        ws["A3"] = f"审计年度: {data.year}"
                        wb.save(str(dest_file))
                        wb.close()
                    except Exception:
                        dest_file.write_bytes(b"")

                # 创建 working_paper
                wp = WorkingPaper(
                    project_id=project_id,
                    wp_index_id=wp_index.id,
                    file_path=str(dest_file),
                    source_type=WpSourceType.template,
                    file_version=1,
                    created_by=current_user.id,
                )
                db.add(wp)

                # 底稿快照绑定
                try:
                    from app.services.dataset_query import bind_to_active_dataset
                    await bind_to_active_dataset(db, wp, project_id, data.year)
                except Exception as _bind_err:
                    _logger.warning("dataset binding failed for wp %s: %s", code, _bind_err)

                # 填充底稿表头
                try:
                    from app.services.wp_header_service import fill_workpaper_header
                    await fill_workpaper_header(
                        db=db, project_id=project_id, wp_id=wp.id,
                        file_path=str(dest_file), wp_code=code, wp_name=wp_name,
                        cycle=cycle,
                    )
                except Exception as _e:
                    _logger.warning("fill header failed for %s: %s", code, _e)

                # [新增] 填充 parsed_data（核心产物）
                await populate_parsed_data(db, wp, code, wp_name, cycle)

            created += 1
            created_codes.append(code)
        except Exception as e:
            failures.append({"wp_code": code, "error": str(e)})
            _logger.warning("generate failed for %s: %s", code, e)

    await db.commit()
    return {
        "created": created,
        "skipped": skipped,
        "created_codes": created_codes,
        "skipped_codes": skipped_codes,
        "failures": failures,
        "message": f"已生成 {created} 个底稿，跳过 {skipped} 个，失败 {len(failures)} 个",
    }


class CreateCustomWorkpaperRequest(BaseModel):
    wp_code: str
    wp_name: str
    audit_cycle: str | None = None
    year: int = 2025


class CustomBatchItem(BaseModel):
    wp_code: str
    wp_name: str
    audit_cycle: str | None = None


class CreateCustomBatchRequest(BaseModel):
    items: list[CustomBatchItem] = []
    year: int = 2025


class CustomBatchPreviewRequest(BaseModel):
    items: list[CustomBatchItem] = []


#: 单次批量上限，**与前端 `customWpBatchParse.MAX_BATCH_ITEMS` 交叉锁死**。
#:
#: 🔴 两侧不等的后果：前端放行 300 条、后端 422 整批拒绝 → 用户白填一屏清单。
#: 守卫读前端源码比对该常量值（改一侧另一侧必红）。
#: 🔴 超限返 422 且**不静默截断** —— 截断会让用户以为整份清单都创建了。
MAX_BATCH_ITEMS = 200

#: 底稿编号字符集，**与前端 `customWpBatchParse.WP_CODE_RE` 交叉锁死**。
#: 字母/数字开头，其后可含字母数字中划线下划线点，总长 ≤32。
WP_CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9\-_.]{0,31}$"


async def _custom_code_exists(
    db: AsyncSession, project_id: UUID, wp_code: str
) -> bool:
    """该项目下是否已存在此底稿编号。"""
    existing = await db.execute(
        sa.select(WpIndex.id).where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code == wp_code,
            WpIndex.is_deleted == sa.false(),
        )
    )
    return existing.scalar_one_or_none() is not None


async def _create_one_custom_workpaper(
    db: AsyncSession,
    *,
    project_id: UUID,
    wp_code: str,
    wp_name: str,
    audit_cycle: str | None,
    year: int,
    created_by: UUID | None,
) -> dict:
    """创建**一个**自定义底稿（单条端点与批量端点的唯一实现）。

    🔴 抽出这个共享函数是为了满足 R8.7/R8.9：批量与单条**必须共用同一份创建逻辑**。
    两份实现会漂移 —— 平台已有多起「同一语义两处各写一份，修一处另一处不动」的实证
    （如 `fill_report_formulas.py` vs `ReportFormulaService`）。守卫会断言批量路径
    确实调用本函数（变异「批量另写一份」必须打红）。

    🔴 **不 commit**：事务边界由调用方决定 —— 批量端点要在最外层一次 commit，
    每条用 savepoint 隔离；本函数内部 commit 会破坏 per-item 回滚语义。

    Raises:
        ValueError: 编号已存在（调用方决定映射成 409 还是 skipped）
    """
    from pathlib import Path

    if await _custom_code_exists(db, project_id, wp_code):
        raise ValueError(f"底稿编号 {wp_code} 已存在")

    cycle = audit_cycle or (wp_code[0] if wp_code else "X")

    wp_index = WpIndex(
        project_id=project_id,
        wp_code=wp_code,
        wp_name=wp_name,
        audit_cycle=cycle,
        status=WpStatus.not_started,
    )
    db.add(wp_index)
    await db.flush()

    # 创建空白 xlsx（sheet 名恒取 wp_code —— render 只读 html_data[wp_code]）
    project_wp_dir = Path("storage") / "projects" / str(project_id) / "workpapers"
    cycle_dir = project_wp_dir / cycle
    cycle_dir.mkdir(parents=True, exist_ok=True)
    dest_file = cycle_dir / f"{wp_code}.xlsx"

    try:
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = wp_code
        wb.save(str(dest_file))
        wb.close()
    except Exception:
        dest_file.write_bytes(b"")

    wp = WorkingPaper(
        project_id=project_id,
        wp_index_id=wp_index.id,
        file_path=str(dest_file),
        source_type=WpSourceType.manual,
        file_version=1,
        created_by=created_by,
    )
    db.add(wp)
    await db.flush()

    # F50 / Sprint 8.17: 自定义底稿同样绑定当前 active dataset
    try:
        from app.services.dataset_query import bind_to_active_dataset

        await bind_to_active_dataset(db, wp, project_id, year)
    except Exception as _bind_err:
        import logging

        logging.getLogger(__name__).warning(
            "dataset binding failed for custom wp %s: %s", wp_code, _bind_err
        )

    # 自定义底稿强制写入标准表头（is_custom=True）
    try:
        from app.services.wp_header_service import fill_workpaper_header

        await fill_workpaper_header(
            db=db,
            project_id=project_id,
            wp_id=wp.id,
            file_path=str(dest_file),
            wp_code=wp_code,
            wp_name=wp_name,
            cycle=cycle,
            is_custom=True,
        )
    except Exception as _e:
        import logging

        logging.getLogger(__name__).warning(
            "fill custom header failed for %s: %s", wp_code, _e
        )

    # 🔴 投影 parsed_data（必须在 fill_workpaper_header 之后、commit 之前）
    #
    # 改造前 create_custom_workpaper 不填 parsed_data ⇒ html_data.cells 为空
    # ⇒ GtGridSheet.hasData = keys(cells)>0 && maxRow>0 恒 false
    # ⇒ 网格恒显示「此表格底稿模板暂无内容」，且公式选址列表为空（选不了目标格）。
    #
    # 顺序原因：表头由 fill_workpaper_header 写进 xlsx，投影必须在其后才能读到表头格；
    # 放到 commit 之后则本次请求的投影不落库。
    try:
        from app.services.custom_workpaper_projection import refresh_custom_projection

        refresh_custom_projection(wp, wp_code)
    except Exception as _proj_err:
        import logging

        logging.getLogger(__name__).warning(
            "custom projection failed for %s: %s", wp_code, _proj_err
        )

    return {
        "wp_id": str(wp.id),
        "wp_code": wp_code,
        "wp_name": wp_name,
        "file_path": str(dest_file),
    }


@router.post("/api/projects/{project_id}/working-papers/create-custom")
async def create_custom_workpaper(
    project_id: UUID,
    data: CreateCustomWorkpaperRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建自定义底稿（用户自建，非模板生成）

    自动填充致同标准表头（编制单位/审计期间/索引号/交叉索引等）。

    🔴 响应形状保持不变（既有前端调用方零改动）；创建逻辑委托
    `_create_one_custom_workpaper`，与批量端点共用同一份实现。
    """
    try:
        result = await _create_one_custom_workpaper(
            db,
            project_id=project_id,
            wp_code=data.wp_code,
            wp_name=data.wp_name,
            audit_cycle=data.audit_cycle,
            year=data.year,
            created_by=current_user.id,
        )
    except ValueError as e:
        # 单条端点沿用既有 409 语义（批量端点则映射成 skipped）
        raise HTTPException(status_code=409, detail=str(e))

    await db.commit()
    return {
        **result,
        "message": "自定义底稿创建成功，表头已自动填充",
    }


@router.post("/api/projects/{project_id}/working-papers/create-custom-batch/preview")
async def preview_custom_workpaper_batch(
    project_id: UUID,
    data: CustomBatchPreviewRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """批量创建**预览**（只读）。

    🔴 **绝不写库** —— 调用前后 `wp_index` / `working_paper` 行数必须不变（Property 11）。
    R8.2「不得直接开始创建」靠本端点成立：前端拿它的逐行结论渲染预览表格。

    🔴 `duplicate_db` 只有后端能判（前端 `validateItems` 只管格式与清单内重号）。

    status 取值：`ok` / `duplicate_input` / `duplicate_db` / `invalid`
    """
    if len(data.items or []) > MAX_BATCH_ITEMS:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"单次最多 {MAX_BATCH_ITEMS} 条，收到 {len(data.items or [])} 条",
                "overflow": True,
                "max_items": MAX_BATCH_ITEMS,
            },
        )

    results: list[dict] = []
    seen: set[str] = set()

    for item in data.items or []:
        code = (item.wp_code or "").strip()
        name = (item.wp_name or "").strip()
        cycle = (item.audit_cycle or "").strip() or (code[0] if code else "")

        if not code or not name:
            results.append({
                "wp_code": code, "wp_name": name, "audit_cycle": cycle,
                "status": "invalid", "reason": "编号与名称均不能为空",
            })
            continue
        if not re.fullmatch(WP_CODE_PATTERN, code):
            results.append({
                "wp_code": code, "wp_name": name, "audit_cycle": cycle,
                "status": "invalid",
                "reason": "编号只能含字母/数字/中划线/下划线/点，且以字母或数字开头（≤32 字符）",
            })
            continue
        # 🔴 清单内重号按**归一后**的键判（大小写不敏感），与前端
        # `normalizeWpCode` 同口径 —— 两侧不一致会出现「前端说重复、后端说都能建」，
        # 用户最后拿到两份只差大小写的底稿。
        # 🔴 但**库内**存在性检查（`_custom_code_exists`）仍是精确匹配：那是既有单条
        # `create-custom` 端点的行为，改成大小写不敏感会让历史上能创建的组合突然 409。
        if code.upper() in seen:
            results.append({
                "wp_code": code, "wp_name": name, "audit_cycle": cycle,
                "status": "duplicate_input", "reason": "清单内编号重复（大小写不敏感）",
            })
            continue
        seen.add(code.upper())
        if await _custom_code_exists(db, project_id, code):
            results.append({
                "wp_code": code, "wp_name": name, "audit_cycle": cycle,
                "status": "duplicate_db", "reason": "该项目下编号已存在，创建时将跳过",
            })
            continue
        results.append({
            "wp_code": code, "wp_name": name, "audit_cycle": cycle,
            "status": "ok", "reason": None,
        })

    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "duplicate_input": sum(1 for r in results if r["status"] == "duplicate_input"),
        "duplicate_db": sum(1 for r in results if r["status"] == "duplicate_db"),
        "invalid": sum(1 for r in results if r["status"] == "invalid"),
    }
    return {"results": results, "summary": summary}


@router.post("/api/projects/{project_id}/working-papers/create-custom-batch")
async def create_custom_workpaper_batch(
    project_id: UUID,
    data: CreateCustomBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量创建自定义底稿。

    🔴 **per-item savepoint**（`begin_nested`）+ per-item try/except：一条失败只回滚
    该条，其余照常创建，最外层一次 commit。范式取自同文件 `generate_from_codes`。
    没有 savepoint 时一条失败会让**整批**回滚 —— 用户重试还是同样失败，无从下手。

    🔴 三态可分：`created` / `skipped`（编号已存在）/ `failed`（带原因）。
    编号已存在归 **skipped 而非 failed** —— 它是幂等重跑的正常结果，混进 failed
    会让用户以为出错了。
    """
    # 🔴 上限与格式判据必须与 preview 端点**逐字一致**，否则出现
    #    「preview 说 ok、create 却 422/failed」的不一致体验（用户已按预览确认过）。
    if len(data.items or []) > MAX_BATCH_ITEMS:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"单次最多 {MAX_BATCH_ITEMS} 条，收到 {len(data.items or [])} 条",
                "overflow": True,
                "max_items": MAX_BATCH_ITEMS,
            },
        )

    created: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    results: list[dict] = []
    seen: set[str] = set()

    for item in data.items or []:
        code = (item.wp_code or "").strip()
        name = (item.wp_name or "").strip()
        if not code or not name:
            failed.append({"wp_code": code, "reason": "编号与名称均不能为空"})
            results.append({"wp_code": code, "status": "failed", "reason": "编号与名称均不能为空"})
            continue
        if not re.fullmatch(WP_CODE_PATTERN, code):
            reason = "编号只能含字母/数字/中划线/下划线/点，且以字母或数字开头（≤32 字符）"
            failed.append({"wp_code": code, "reason": reason})
            results.append({"wp_code": code, "status": "failed", "reason": reason})
            continue
        # 🔴 清单内重号按**归一后**的键（大小写不敏感），与 preview 端点及前端
        #    `normalizeWpCode` 同口径；库内存在性仍走 `_custom_code_exists` 精确匹配。
        if code.upper() in seen:
            skipped.append({"wp_code": code, "reason": "清单内编号重复（大小写不敏感）"})
            results.append({
                "wp_code": code, "status": "skipped", "reason": "清单内编号重复（大小写不敏感）",
            })
            continue
        seen.add(code.upper())

        try:
            async with db.begin_nested():
                one = await _create_one_custom_workpaper(
                    db,
                    project_id=project_id,
                    wp_code=code,
                    wp_name=name,
                    audit_cycle=item.audit_cycle,
                    year=data.year,
                    created_by=current_user.id,
                )
            created.append(one)
            results.append({"wp_code": code, "status": "created", "reason": None})
        except ValueError as dup_err:
            # 编号已存在 → skipped（幂等重跑的正常结果，不是错误）
            skipped.append({"wp_code": code, "reason": str(dup_err)})
            results.append({"wp_code": code, "status": "skipped", "reason": str(dup_err)})
        except Exception as e:  # noqa: BLE001 — 单条失败不阻断整批
            import logging

            logging.getLogger(__name__).warning(
                "batch custom create failed wp_code=%s: %s", code, e
            )
            failed.append({"wp_code": code, "reason": str(e)})
            results.append({"wp_code": code, "status": "failed", "reason": str(e)})

    await db.commit()
    return {
        "created": len(created),
        "skipped": len(skipped),
        "failed": len(failed),
        "created_items": created,
        "skipped_items": skipped,
        "failed_items": failed,
        "results": results,
        "message": (
            f"已创建 {len(created)} 个，跳过 {len(skipped)} 个，失败 {len(failed)} 个"
        ),
    }
