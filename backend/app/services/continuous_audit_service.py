"""连续审计服务 — Phase 10 Task 2.1-2.2

一键创建当年项目，继承上年配置/数据/底稿。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, ProjectUser
from app.models.base import ProjectStatus
from app.models.audit_platform_models import (
    AccountMapping, TrialBalance, Adjustment, AdjustmentEntry,
    UnadjustedMisstatement,
)

logger = logging.getLogger(__name__)


class ContinuousAuditService:
    """连续审计服务"""

    async def create_next_year(
        self,
        db: AsyncSession,
        prior_project_id: UUID,
        copy_team: bool = True,
        copy_mapping: bool = True,
        copy_procedures: bool = True,
    ) -> dict[str, Any]:
        """一键创建当年项目

        继承：basic_info, account_mapping, team, trial_balance(audited→opening),
              adjustments(is_continuous), unadjusted_misstatements(carry_forward)
        """
        # 1. 获取上年项目
        result = await db.execute(
            sa.select(Project).where(Project.id == prior_project_id, Project.is_deleted == sa.false())
        )
        prior = result.scalar_one_or_none()
        if not prior:
            raise ValueError("上年项目不存在")

        # 推算当年年度（平台统一年度解析优先；缺失时退回向导数据，最后才用当前年）
        from app.services.project_audit_year import resolve_project_audit_year

        ws = prior.wizard_state or {}
        basic_info = ws.get("steps", {}).get("basic_info", {}).get("data", {})
        prior_year = (
            resolve_project_audit_year(prior)
            or basic_info.get("audit_year")
            or datetime.now(timezone.utc).year
        )
        new_year = int(prior_year) + 1
        inherited_template_type = basic_info.get("template_type") or prior.template_type
        inherited_report_scope = basic_info.get("report_scope") or prior.report_scope
        inherited_company_code = basic_info.get("company_code") or prior.company_code
        inherited_parent_company_name = basic_info.get("parent_company_name") or prior.parent_company_name
        inherited_parent_company_code = basic_info.get("parent_company_code") or prior.parent_company_code
        inherited_ultimate_company_name = basic_info.get("ultimate_company_name") or prior.ultimate_company_name
        inherited_ultimate_company_code = basic_info.get("ultimate_company_code") or prior.ultimate_company_code
        # consol-tree-three-code-autobuild 需求 7.4：继承与上级关系（上级代码为空则无关系；
        # 上年缺关系的历史数据按企业名称补默认，保持「有上级 ⇔ 有关系」不变式）
        from app.services.group_relation import resolve_relation

        inherited_relation_to_parent = resolve_relation(
            basic_info.get("relation_to_parent") or prior.relation_to_parent,
            inherited_parent_company_code,
            prior.client_name,
            inherited_company_code,
        )

        # 物化年度写入后唯一索引生效：同企业同年度同口径已有项目 ⇒ 400 而不是 IntegrityError 500
        if inherited_company_code:
            from app.services.uniqueness_checker import check_uniqueness

            is_unique, uniqueness_error = await check_uniqueness(
                inherited_company_code, new_year, inherited_report_scope or "standalone", db
            )
            if not is_unique:
                raise ValueError(
                    f"{new_year} 年度{uniqueness_error or '已存在该单位该年度的项目'}，不能重复创建"
                )

        # 2. 创建新项目
        new_project = Project(
            name=f"{prior.client_name}_{new_year}",
            client_name=prior.client_name,
            project_type=prior.project_type,
            status=ProjectStatus.created,
            manager_id=prior.manager_id,
            partner_id=prior.partner_id,
            company_code=inherited_company_code,
            template_type=inherited_template_type,
            report_scope=inherited_report_scope,
            # 物化年度列必须写：唯一索引 (company_code, audit_year, report_scope) 与
            # 企业树按年度分组都依赖它（原实现漏写 ⇒ 新项目游离于唯一性与集团树之外）
            audit_year=new_year,
            parent_company_name=inherited_parent_company_name,
            parent_company_code=inherited_parent_company_code,
            relation_to_parent=inherited_relation_to_parent,
            ultimate_company_name=inherited_ultimate_company_name,
            ultimate_company_code=inherited_ultimate_company_code,
            # parent_project_id 是派生值（ADR-CTREE-001），不复制上年值 —— 上年值指向
            # 上年度的合并项目，由 group_links.sync_group_links 按新年度重算。
            consol_level=prior.consol_level,
        )
        db.add(new_project)
        await db.flush()
        # 需求 7.2 / 7.4：新年度的派生链接按三码重算（不串用上年链接）
        from app.services.group_links import sync_group_links

        await sync_group_links(db, new_year)

        # 设置 prior_year_project_id（通过 raw SQL 因为 ORM 模型可能还没有这个字段）
        await db.execute(
            sa.text("UPDATE projects SET prior_year_project_id = :prior_id WHERE id = :new_id"),
            {"prior_id": str(prior_project_id), "new_id": str(new_project.id)},
        )

        # 复制 wizard_state（更新年度 + 集团关系）。必须深拷贝：浅拷贝时 steps 字典与上年
        # 项目共享，给新项目写年度会把上年项目内存里的 wizard_state 一起改掉。
        import copy as _copy

        new_basic_info = {
            **basic_info,
            "audit_year": new_year,
            "relation_to_parent": inherited_relation_to_parent,
        }
        new_ws = _copy.deepcopy(ws)
        if "steps" in new_ws and "basic_info" in new_ws["steps"]:
            new_ws["steps"]["basic_info"]["data"] = new_basic_info
        new_project.wizard_state = new_ws

        items_copied = {}

        # 3. 复制科目映射
        if copy_mapping:
            result = await db.execute(
                sa.select(AccountMapping).where(
                    AccountMapping.project_id == prior_project_id,
                    AccountMapping.is_deleted == sa.false(),
                )
            )
            mappings = result.scalars().all()
            count = 0
            for m in mappings:
                # 字段名以 ORM 为准（原实现用 client_account_code / confidence 等不存在的属性，
                # 上年只要有一条映射就 AttributeError ⇒ 整个接口 500；
                # consol-tree-three-code-autobuild 任务 3.6 真库回滚探针复现）
                new_m = AccountMapping(
                    project_id=new_project.id,
                    original_account_code=m.original_account_code,
                    original_account_name=m.original_account_name,
                    standard_account_code=m.standard_account_code,
                    mapping_type=m.mapping_type,
                    created_by=m.created_by,
                )
                db.add(new_m)
                count += 1
            items_copied["account_mapping"] = count

        # 4. 复制团队委派
        if copy_team:
            result = await db.execute(
                sa.select(ProjectUser).where(
                    ProjectUser.project_id == prior_project_id,
                    ProjectUser.is_deleted == sa.false(),
                )
            )
            users = result.scalars().all()
            count = 0
            for u in users:
                new_u = ProjectUser(
                    project_id=new_project.id,
                    user_id=u.user_id,
                    role=u.role,
                    permission_level=u.permission_level,
                    scope_cycles=u.scope_cycles,
                    scope_accounts=u.scope_accounts,
                )
                db.add(new_u)
                count += 1
            items_copied["team_assignments"] = count

        # 5. 试算表审定数 → 当年期初（只取上年度的行：其他年度的行改写成 new_year 会撞
        #    唯一索引 (project_id, year, company_code, standard_account_code)）
        result = await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == prior_project_id,
                TrialBalance.year == int(prior_year),
                TrialBalance.is_deleted == sa.false(),
            )
        )
        tb_rows = result.scalars().all()
        count = 0
        for tb in tb_rows:
            new_tb = TrialBalance(
                project_id=new_project.id,
                year=new_year,
                company_code=tb.company_code,
                standard_account_code=tb.standard_account_code,
                account_name=tb.account_name,
                account_category=tb.account_category,
                opening_balance=tb.audited_amount,  # 上年审定 → 当年期初
                unadjusted_amount=None,
            )
            db.add(new_tb)
            count += 1
        items_copied["trial_balance"] = count

        # 6. 连续调整分录结转
        result = await db.execute(
            sa.select(Adjustment).where(
                Adjustment.project_id == prior_project_id,
                Adjustment.is_deleted == sa.false(),
                # is_continuous 字段可能还不存在，用 raw SQL 兜底
            )
        )
        adj_rows = result.scalars().all()
        adj_count = 0
        for adj in adj_rows:
            # 检查 is_continuous（通过 dict 访问避免 ORM 字段不存在的问题）
            is_cont = getattr(adj, "is_continuous", False)
            if not is_cont:
                continue
            new_group_id = uuid.uuid4()
            new_adj = Adjustment(
                project_id=new_project.id,
                year=new_year,
                company_code=adj.company_code,
                adjustment_no=adj.adjustment_no,
                adjustment_type=adj.adjustment_type,
                description=f"[结转] {adj.description or ''}",
                account_code=adj.account_code,
                account_name=adj.account_name,
                debit_amount=adj.debit_amount,
                credit_amount=adj.credit_amount,
                entry_group_id=new_group_id,
                created_by=adj.created_by,
            )
            db.add(new_adj)
            adj_count += 1
        items_copied["adjustments_carried"] = adj_count

        # 7. 未更正错报结转
        result = await db.execute(
            sa.select(UnadjustedMisstatement).where(
                UnadjustedMisstatement.project_id == prior_project_id,
                UnadjustedMisstatement.is_deleted == sa.false(),
            )
        )
        mis_rows = result.scalars().all()
        mis_count = 0
        for mis in mis_rows:
            new_mis = UnadjustedMisstatement(
                project_id=new_project.id,
                year=new_year,
                misstatement_description=f"[上年结转] {mis.misstatement_description}",
                affected_account_code=mis.affected_account_code,
                affected_account_name=mis.affected_account_name,
                misstatement_amount=mis.misstatement_amount,
                misstatement_type=mis.misstatement_type,
                management_reason=mis.management_reason,
                is_carried_forward=True,
                prior_year_id=mis.id,
            )
            db.add(new_mis)
            mis_count += 1
        items_copied["misstatements_carried"] = mis_count

        # 8. 附注裁剪方案结转（可选项：放在 SAVEPOINT 里，失败只回滚本步，不毒化主事务）
        #
        # 原实现对 note_wp_mapping / procedure_instances / note_trim_schemes 执行一条语法残缺的
        # INSERT…SELECT（缺右括号与列清单，且未传参），每次必失败。PG 上事务内任一语句失败即
        # 中止整个事务，try/except 吞掉异常后路由照常 commit —— PG 对已中止事务的 COMMIT
        # 等于 ROLLBACK ⇒ 新项目与前 7 步复制的数据全部静默丢失，接口却返回 200 和新项目 id。
        # 现改为：
        # - note_trim_schemes：按 ORM 逐行复制（字段简单、无跨年外键）；
        # - procedure_instances：不结转 —— 行内 parent_id 指向上年实例、wp_id 指向上年底稿、
        #   status/execution_status 是上年执行结果，整行照抄会造出跨年引用，需单独设计重映射
        #   （登记在 spec consol-tree-three-code-autobuild design §十二 范围外事项）；
        # - note_wp_mapping：真库无此表，删除。
        from app.models.note_trim_models import NoteTrimScheme

        try:
            async with db.begin_nested():
                result = await db.execute(
                    sa.select(NoteTrimScheme).where(
                        NoteTrimScheme.project_id == prior_project_id,
                        NoteTrimScheme.is_deleted == sa.false(),
                    )
                )
                trim_count = 0
                for scheme in result.scalars().all():
                    db.add(NoteTrimScheme(
                        project_id=new_project.id,
                        template_type=scheme.template_type,
                        scheme_name=scheme.scheme_name,
                        trim_data=_copy.deepcopy(scheme.trim_data),
                        created_by=scheme.created_by,
                    ))
                    trim_count += 1
                await db.flush()
            items_copied["note_trim_schemes"] = trim_count
        except Exception:  # noqa: BLE001 — 可选结转失败不应让整个建下年项目失败
            logger.warning("附注裁剪方案结转失败（已回滚本步，主流程继续）", exc_info=True)
            items_copied["note_trim_schemes"] = 0

        await db.flush()

        logger.info(
            "create_next_year: prior=%s → new=%s, year=%d, items=%s",
            prior_project_id, new_project.id, new_year, items_copied,
        )
        return {
            "new_project_id": str(new_project.id),
            "prior_year_project_id": str(prior_project_id),
            "new_year": new_year,
            "items_copied": items_copied,
        }


# ---------------------------------------------------------------------------
# Round 4 需求 4: 上年底稿对比 — 独立函数（非类方法，供 router 直接调用）
# ---------------------------------------------------------------------------


async def get_prior_year_workpaper(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
) -> dict[str, Any] | None:
    """获取上年同 wp_code 的底稿元数据

    流程：
    1. 通过 wp_id 获取当前底稿关联的 WpIndex.wp_code
    2. 通过 project_id 获取 prior_year_project_id
    3. 在上年项目中查找同 wp_code 的底稿（通过 WpIndex join）
    4. 返回 {wp_id, wp_code, file_url, conclusion, audited_amount} 或 None
    """
    from app.models.workpaper_models import WorkingPaper, WpIndex

    # 1. 获取当前底稿的 wp_code（通过 WpIndex）
    result = await db.execute(
        sa.select(WpIndex.wp_code)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WorkingPaper.id == wp_id)
    )
    row = result.first()
    if not row:
        return None
    wp_code = row[0]

    # 2. 获取 prior_year_project_id
    result = await db.execute(
        sa.text("SELECT prior_year_project_id FROM projects WHERE id = :pid"),
        {"pid": str(project_id)},
    )
    row = result.first()
    if not row or not row[0]:
        return None
    prior_project_id = row[0]

    # 3. 在上年项目中查找同 wp_code 的底稿（通过 WpIndex join）
    result = await db.execute(
        sa.select(WorkingPaper)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == prior_project_id,
            WpIndex.wp_code == wp_code,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    prior_wp = result.first()
    if not prior_wp:
        return None

    # 4. 构建返回数据
    parsed = prior_wp.parsed_data or {}
    return {
        "wp_id": str(prior_wp.id),
        "wp_code": wp_code,
        "file_url": f"/api/projects/{prior_project_id}/workpapers/{prior_wp.id}/download-file",
        "conclusion": parsed.get("conclusion"),
        "audited_amount": parsed.get("audited_amount"),
    }
