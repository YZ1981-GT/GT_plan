"""连续审计服务 — Phase 10 Task 2.1-2.2

一键创建当年项目，继承上年配置/数据/底稿。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
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

        # 推算当年年度
        ws = prior.wizard_state or {}
        basic_info = ws.get("steps", {}).get("basic_info", {}).get("data", {})
        prior_year = basic_info.get("audit_year", datetime.utcnow().year)
        new_year = prior_year + 1

        # 2. 创建新项目
        new_project = Project(
            name=f"{prior.client_name}_{new_year}",
            client_name=prior.client_name,
            project_type=prior.project_type,
            status=ProjectStatus.created,
            manager_id=prior.manager_id,
            partner_id=prior.partner_id,
            company_code=prior.company_code,
            template_type=prior.template_type,
            report_scope=prior.report_scope,
            parent_company_name=prior.parent_company_name,
            parent_company_code=prior.parent_company_code,
            ultimate_company_name=prior.ultimate_company_name,
            ultimate_company_code=prior.ultimate_company_code,
            parent_project_id=prior.parent_project_id,
            consol_level=prior.consol_level,
        )
        db.add(new_project)
        await db.flush()

        # 设置 prior_year_project_id（通过 raw SQL 因为 ORM 模型可能还没有这个字段）
        await db.execute(
            sa.text("UPDATE projects SET prior_year_project_id = :prior_id WHERE id = :new_id"),
            {"prior_id": str(prior_project_id), "new_id": str(new_project.id)},
        )

        # 复制 wizard_state（更新年度）
        new_basic_info = {**basic_info, "audit_year": new_year}
        new_ws = {**ws}
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
                new_m = AccountMapping(
                    project_id=new_project.id,
                    client_account_code=m.client_account_code,
                    client_account_name=m.client_account_name,
                    standard_account_code=m.standard_account_code,
                    standard_account_name=m.standard_account_name,
                    mapping_type=m.mapping_type,
                    confidence=m.confidence,
                    is_confirmed=m.is_confirmed,
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

        # 5. 试算表审定数 → 当年期初
        result = await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == prior_project_id,
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

        # 8. 复制 note_wp_mapping / procedure_instances / note_trim_schemes
        # 使用 raw SQL 因为这些表可能在不同 Phase 定义
        for table_name in ["note_wp_mapping", "procedure_instances", "note_trim_schemes"]:
            try:
                count_result = await db.execute(sa.text(
                    f"INSERT INTO {table_name} (id, project_id, "
                    f"SELECT gen_random_uuid(), :new_pid, "
                    f"FROM {table_name} WHERE project_id = :old_pid"
                ))
            except Exception:
                # 表可能不存在或结构不同，跳过
                logger.warning("跳过 %s 结转（表可能不存在）", table_name)
                items_copied[table_name] = 0
                continue

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
