"""试算表「科目明细」公式：项目级覆盖 + 自定义新增（spec formula-global-settings-sync Phase 4）。

公式管理中心「试算平衡表 > 科目明细」节点按科目动态生成 ``TB('科目','期末余额')`` 预设；
用户可覆盖某科目的公式、或新增自定义公式行。2026-10-20 起存 ``formula_setting``（tb_detail 域，
全局 + 本项目两层，带版本与留痕），不再写 ``projects.wizard_state``（V199 已迁入旧数据）。

路径与响应形状不变（``/api/report-config/tb-detail-formulas/{project_id}``；本路由自带完整前缀，在
``router_registry/report.py`` §4 紧随 report_config 注册 —— 前后端路由守卫按文件内 prefix 静态抽取，
经父路由 include 的子路由它们看不到），响应另带 ``layers``（公式位 → 层级）与 ``loaded``
（公式位 → 版本令牌，PUT 时原样带回）。
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import Project, User
from app.services.formula_settings import tb_detail
from app.services.formula_settings.errors import FormulaSettingError
from app.services.formula_settings.propagation import publish_events

router = APIRouter(prefix="/api/report-config", tags=["report-config"])


class TbDetailFormulaItem(BaseModel):
    row_code: str
    row_name: str | None = None
    formula: str | None = None
    # 用户要求：分类默认为自动运算类型
    formula_category: str | None = "auto_calc"
    formula_description: str | None = None


class TbDetailFormulasPayload(BaseModel):
    # overrides：科目编码 → 覆盖项（覆盖默认 TB() 预设）
    overrides: dict[str, TbDetailFormulaItem] = {}
    # added：用户新增的自定义公式行
    added: list[TbDetailFormulaItem] = []
    # 读接口下发的版本令牌，原样带回（差量写入 + 并发冲突判定）
    loaded: dict[str, str] | None = None


async def _project_or_404(db: AsyncSession, project_id: UUID) -> None:
    found = (await db.execute(sa.select(Project.id).where(
        Project.id == project_id, Project.is_deleted == sa.false()))).scalar_one_or_none()
    if found is None:
        raise HTTPException(status_code=404, detail="项目不存在")


@router.get("/tb-detail-formulas/{project_id}")
async def get_tb_detail_formulas(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    # Task 5.2 / ADR-FMC-06：path 有 {project_id}，readonly 项目级鉴权
    current_user: User = Depends(require_project_access("readonly")),
):
    """读取本项目生效的科目明细公式覆盖 + 自定义新增（全局 + 本项目）；无配置时返回空结构。"""
    await _project_or_404(db, project_id)
    return await tb_detail.load(db, project_id)


@router.put("/tb-detail-formulas/{project_id}")
async def save_tb_detail_formulas(
    project_id: UUID,
    body: TbDetailFormulasPayload,
    db: AsyncSession = Depends(get_db),
    # formula-global-settings-sync R6.1 / R11.1：写本项目适配 = 项目 edit（与表间审核 / overrides 同口径）。
    # 旧写法叠加 require_role(admin/partner/signing_partner/manager)：按 ROLE_MAP 合伙人 / 经理是
    # review 级会被 edit 门挡、审计员又被角色门挡 ⇒ 实际只有 admin 能存。改为纯项目级 edit。
    current_user: User = Depends(require_project_access("edit")),
):
    """保存科目明细公式（整表语义；按载入时的版本令牌差量写本项目适配，缺令牌 428、过期 409）。"""
    await _project_or_404(db, project_id)
    try:
        result = await tb_detail.save(
            db, project_id,
            overrides={code: item.model_dump() for code, item in (body.overrides or {}).items()},
            added=[item.model_dump() for item in (body.added or [])],
            loaded=body.loaded, user_id=current_user.id,
        )
    except FormulaSettingError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from None
    await db.commit()
    await publish_events(result["events"], domain="tb_detail", source="tb_detail_edit")
    changed = sorted({s for ev in result["events"] for s in ev.get("slot_keys", [])})
    return {**await tb_detail.load(db, project_id), "changed_slot_keys": changed, "message": "科目明细公式已保存"}
