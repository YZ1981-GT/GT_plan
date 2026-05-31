"""报表格式配置服务

功能：
- 加载种子数据到 report_config 表
- 克隆标准配置为项目级配置
- 查询/修改报表配置
- 主模板回填：suggest_to_master / review_candidate / diff_vs_master / apply_master_update
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
import json
from pathlib import Path
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReportType, ReportConfig, ReportConfigBaseline

logger = logging.getLogger(__name__)

SEED_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "report_config_seed.json"


@dataclass
class ConfigDiff:
    """项目级 vs 主模板差异条目"""

    row_code: str
    report_type: str
    project_formula: str | None
    master_formula: str | None
    diff_type: str  # "modified" | "project_only" | "master_only"


class ReportConfigService:
    """报表格式配置服务"""

    VALID_STANDARDS = {"soe_consolidated", "soe_standalone", "listed_consolidated", "listed_standalone", "enterprise"}

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    async def resolve_applicable_standard(db: AsyncSession, project_id: UUID) -> str:
        """从项目配置动态确定报表标准。

        映射规则：template_type (soe/listed) + report_scope (consolidated/standalone)
        组合为 "soe_consolidated" / "listed_standalone" 等，降级为 "enterprise"。
        """
        from app.models.core import Project
        result = await db.execute(
            sa.select(Project.template_type, Project.report_scope).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
        row = result.one_or_none()
        if not row:
            return "enterprise"
        template_type = row[0] or "soe"
        report_scope = row[1] or "standalone"
        standard = f"{template_type}_{report_scope}"
        return standard if standard in ReportConfigService.VALID_STANDARDS else "enterprise"

    # ------------------------------------------------------------------
    # 加载种子数据
    # ------------------------------------------------------------------
    async def load_seed_data(self) -> int:
        """将种子 JSON 加载到 report_config 表，返回插入行数。
        跳过已存在的行（按 report_type + row_code + applicable_standard 判重）。
        """
        with open(SEED_DATA_PATH, encoding="utf-8-sig") as f:
            seed = json.load(f)

        count = 0
        for report_block in seed:
            report_type = report_block["report_type"]
            standard = report_block["applicable_standard"]
            for row in report_block["rows"]:
                # 检查是否已存在
                existing = await self.db.execute(
                    sa.select(ReportConfig.id).where(
                        ReportConfig.report_type == FinancialReportType(report_type),
                        ReportConfig.row_code == row["row_code"],
                        ReportConfig.applicable_standard == standard,
                        ReportConfig.is_deleted == sa.false(),
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    continue

                rc = ReportConfig(
                    report_type=FinancialReportType(report_type),
                    row_number=row["row_number"],
                    row_code=row["row_code"],
                    row_name=row["row_name"],
                    indent_level=row.get("indent_level", 0),
                    formula=row.get("formula"),
                    formula_category=row.get("formula_category"),
                    formula_description=row.get("formula_description"),
                    formula_source=row.get("formula_source"),
                    applicable_standard=standard,
                    is_total_row=row.get("is_total_row", False),
                    parent_row_code=row.get("parent_row_code"),
                )
                self.db.add(rc)
                count += 1

        await self.db.flush()
        return count

    # ------------------------------------------------------------------
    # 查询配置列表
    # ------------------------------------------------------------------
    async def list_configs(
        self,
        report_type: FinancialReportType | None = None,
        applicable_standard: str = "enterprise",
    ) -> list[ReportConfig]:
        """查询报表配置行列表"""
        q = (
            sa.select(ReportConfig)
            .where(
                ReportConfig.applicable_standard == applicable_standard,
                ReportConfig.is_deleted == sa.false(),
            )
            .order_by(ReportConfig.report_type, ReportConfig.row_number)
        )
        if report_type is not None:
            q = q.where(ReportConfig.report_type == report_type)

        result = await self.db.execute(q)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # 查询单行详情
    # ------------------------------------------------------------------
    async def get_config(self, config_id: UUID) -> ReportConfig | None:
        """按 ID 查询单行配置"""
        result = await self.db.execute(
            sa.select(ReportConfig).where(
                ReportConfig.id == config_id,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # 克隆配置
    # ------------------------------------------------------------------
    async def clone_report_config(
        self,
        project_id: UUID,
        applicable_standard: str = "enterprise",
    ) -> int:
        """将标准配置复制为项目级配置。

        项目级配置的 applicable_standard 格式为 "project:{project_id}"，
        支持后续自定义修改而不影响标准模板。
        返回克隆的行数。
        """
        project_standard = f"project:{project_id}"

        # 检查是否已克隆
        existing = await self.db.execute(
            sa.select(sa.func.count()).select_from(ReportConfig).where(
                ReportConfig.applicable_standard == project_standard,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        if (existing.scalar() or 0) > 0:
            raise ValueError("该项目已存在克隆配置，请勿重复克隆")

        # 加载标准配置
        source_rows = await self.list_configs(applicable_standard=applicable_standard)
        if not source_rows:
            raise ValueError(f"未找到标准 '{applicable_standard}' 的配置数据")

        count = 0
        for src in source_rows:
            clone = ReportConfig(
                report_type=src.report_type,
                row_number=src.row_number,
                row_code=src.row_code,
                row_name=src.row_name,
                indent_level=src.indent_level,
                formula=src.formula,
                applicable_standard=project_standard,
                is_total_row=src.is_total_row,
                parent_row_code=src.parent_row_code,
            )
            self.db.add(clone)
            count += 1

        await self.db.flush()
        return count

    # ------------------------------------------------------------------
    # 修改配置行
    # ------------------------------------------------------------------
    async def update_config(
        self,
        config_id: UUID,
        updates: dict,
        user_id: UUID | None = None,
    ) -> ReportConfig:
        """修改报表配置行"""
        row = await self.get_config(config_id)
        if row is None:
            raise ValueError("配置行不存在")

        # 记录变更前的值（审计留痕）
        old_values = {}
        allowed_fields = {"row_name", "indent_level", "formula", "is_total_row", "parent_row_code", "formula_category", "formula_description", "formula_source"}
        for key, value in updates.items():
            if key in allowed_fields:
                old_values[key] = getattr(row, key, None)
                setattr(row, key, value)

        # 公式变更审计留痕（统一走哈希链 append_audit_log）
        if old_values and user_id:
            try:
                from app.services.audit_log_helper import append_audit_log

                old_formula = str(old_values.get("formula", "")) if old_values.get("formula") is not None else ""
                new_formula = str(updates.get("formula", "")) if updates.get("formula") is not None else ""
                await append_audit_log(self.db, {
                    "user_id": user_id,
                    "project_id": row.project_id if hasattr(row, "project_id") else None,
                    "action": "formula.changed",
                    "resource_type": "report_config",
                    "resource_id": str(config_id),
                    "details": {
                        "event_type": "formula_changed",
                        "module": "report",
                        "row_code": row.row_code,
                        "action": "update",
                        "old_formula": old_formula,
                        "new_formula": new_formula,
                        "result_value": "",
                        "trace": [],
                        "_diff": {k: {"old": str(old_values.get(k)), "new": str(updates.get(k))} for k in old_values if old_values[k] != updates.get(k)},
                    },
                })
            except Exception:
                pass  # 审计留痕失败不阻断业务

        await self.db.flush()

        # 主模板更新事件：非 project:* 才发 REPORT_CONFIG_MASTER_UPDATED（需求 2.1）
        if not row.applicable_standard.startswith("project:"):
            try:
                from app.models.audit_platform_schemas import EventPayload, EventType
                from app.services.event_bus import event_bus

                await event_bus.publish(EventPayload(
                    event_type=EventType.REPORT_CONFIG_MASTER_UPDATED,
                    project_id=user_id or config_id,  # fallback: config_id as UUID placeholder
                    extra={
                        "standard": row.applicable_standard,
                        "report_type": row.report_type.value if hasattr(row.report_type, "value") else str(row.report_type),
                        "row_code": row.row_code,
                        "config_id": str(config_id),
                    },
                ))
            except Exception:
                pass  # 事件发布失败不阻断业务

        return row

    # ------------------------------------------------------------------
    # 主模板回填：suggest_to_master
    # ------------------------------------------------------------------
    async def suggest_to_master(
        self,
        project_id: UUID,
        row_code: str,
        report_type: str,
        standard: str,
        candidate_formula: str | None = None,
        submitted_by: UUID | None = None,
    ) -> UUID:
        """项目级优化提交为主模板候选（写 ReportConfigBaseline status=pending）。

        Args:
            project_id: 来源项目 ID
            row_code: 配置行编码
            report_type: 报表类型
            standard: 目标 standard（如 soe_consolidated）
            candidate_formula: 候选公式（若为 None 则从项目级配置读取）
            submitted_by: 提交人 ID

        Returns:
            新建候选记录的 UUID
        """
        # 若未指定候选公式，从项目级配置读取
        if candidate_formula is None:
            project_standard = f"project:{project_id}"
            result = await self.db.execute(
                sa.select(ReportConfig.formula).where(
                    ReportConfig.applicable_standard == project_standard,
                    ReportConfig.row_code == row_code,
                    ReportConfig.is_deleted == sa.false(),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(f"项目 {project_id} 中未找到 row_code={row_code} 的配置")
            candidate_formula = row

        candidate = ReportConfigBaseline(
            standard=standard,
            report_type=report_type,
            row_code=row_code,
            candidate_formula=candidate_formula,
            source_project_id=project_id,
            status="pending",
            version=1,
            submitted_by=submitted_by,
        )
        self.db.add(candidate)
        await self.db.flush()
        return candidate.id

    # ------------------------------------------------------------------
    # 主模板回填：review_candidate
    # ------------------------------------------------------------------
    async def review_candidate(
        self,
        candidate_id: UUID,
        approved: bool,
        reviewer: UUID,
    ) -> None:
        """admin 审核候选：通过则合并回 standard 级 + 版本号 + append_audit_log。

        Args:
            candidate_id: 候选记录 ID
            approved: 是否通过
            reviewer: 审核人 ID
        """
        result = await self.db.execute(
            sa.select(ReportConfigBaseline).where(
                ReportConfigBaseline.id == candidate_id
            )
        )
        candidate = result.scalar_one_or_none()
        if candidate is None:
            raise ValueError(f"候选记录 {candidate_id} 不存在")
        if candidate.status != "pending":
            raise ValueError(f"候选记录状态为 {candidate.status}，仅 pending 可审核")

        candidate.reviewed_by = reviewer

        if not approved:
            candidate.status = "rejected"
            await self.db.flush()
            return

        # 通过：合并回 standard 级
        candidate.status = "approved"

        # 查找 standard 级对应行
        master_result = await self.db.execute(
            sa.select(ReportConfig).where(
                ReportConfig.applicable_standard == candidate.standard,
                ReportConfig.row_code == candidate.row_code,
                ReportConfig.report_type == FinancialReportType(candidate.report_type),
                ReportConfig.is_deleted == sa.false(),
            )
        )
        master_row = master_result.scalar_one_or_none()

        old_formula = ""
        if master_row:
            old_formula = master_row.formula or ""
            master_row.formula = candidate.candidate_formula
        else:
            # standard 级不存在该行（理论上不应发生，但防御性处理）
            logger.warning(
                "standard 级未找到 %s/%s/%s，跳过合并",
                candidate.standard, candidate.report_type, candidate.row_code,
            )

        # 版本号递增
        candidate.version = candidate.version + 1

        # 审计留痕（event_type='report_config_changed'）
        try:
            from app.services.audit_log_helper import append_audit_log

            await append_audit_log(self.db, {
                "user_id": reviewer,
                "project_id": candidate.source_project_id,
                "action": "report_config.review_approved",
                "resource_type": "report_config_baseline",
                "resource_id": str(candidate_id),
                "details": {
                    "event_type": "report_config_changed",
                    "sub_action": "review_approved",
                    "standard": candidate.standard,
                    "report_type": candidate.report_type,
                    "row_code": candidate.row_code,
                    "candidate_id": str(candidate_id),
                    "old_formula": old_formula,
                    "new_formula": candidate.candidate_formula or "",
                },
            })
        except Exception:
            logger.exception("review_candidate 审计留痕失败")

        await self.db.flush()

    # ------------------------------------------------------------------
    # 主模板回填：diff_vs_master
    # ------------------------------------------------------------------
    async def diff_vs_master(
        self,
        project_id: UUID,
        standard: str,
    ) -> list[ConfigDiff]:
        """项目级 vs 主模板差异（仿 diff_baseline）。

        Args:
            project_id: 项目 ID
            standard: 对比的 standard（如 soe_consolidated）

        Returns:
            差异列表
        """
        project_standard = f"project:{project_id}"

        # 加载项目级配置
        proj_result = await self.db.execute(
            sa.select(ReportConfig).where(
                ReportConfig.applicable_standard == project_standard,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        proj_rows = {
            (r.report_type.value if hasattr(r.report_type, "value") else str(r.report_type), r.row_code): r
            for r in proj_result.scalars().all()
        }

        # 加载 standard 级配置
        master_result = await self.db.execute(
            sa.select(ReportConfig).where(
                ReportConfig.applicable_standard == standard,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        master_rows = {
            (r.report_type.value if hasattr(r.report_type, "value") else str(r.report_type), r.row_code): r
            for r in master_result.scalars().all()
        }

        diffs: list[ConfigDiff] = []

        # 项目有、主模板也有 → 比较公式
        for key, proj_row in proj_rows.items():
            master_row = master_rows.get(key)
            if master_row is None:
                diffs.append(ConfigDiff(
                    row_code=key[1],
                    report_type=key[0],
                    project_formula=proj_row.formula,
                    master_formula=None,
                    diff_type="project_only",
                ))
            elif proj_row.formula != master_row.formula:
                diffs.append(ConfigDiff(
                    row_code=key[1],
                    report_type=key[0],
                    project_formula=proj_row.formula,
                    master_formula=master_row.formula,
                    diff_type="modified",
                ))

        # 主模板有、项目没有
        for key, master_row in master_rows.items():
            if key not in proj_rows:
                diffs.append(ConfigDiff(
                    row_code=key[1],
                    report_type=key[0],
                    project_formula=None,
                    master_formula=master_row.formula,
                    diff_type="master_only",
                ))

        return diffs

    # ------------------------------------------------------------------
    # 主模板回填：apply_master_update
    # ------------------------------------------------------------------
    async def apply_master_update(
        self,
        project_id: UUID,
        standard: str,
        *,
        keep_local: bool = True,
    ) -> int:
        """主模板更新同步到项目（保留项目本地覆盖）。

        Args:
            project_id: 项目 ID
            standard: 源 standard（如 soe_consolidated）
            keep_local: 若为 True，不覆盖项目已自定义的行（公式与主模板不同的行视为本地覆盖）

        Returns:
            实际同步更新的行数
        """
        project_standard = f"project:{project_id}"

        # 加载项目级配置
        proj_result = await self.db.execute(
            sa.select(ReportConfig).where(
                ReportConfig.applicable_standard == project_standard,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        proj_rows = {
            (r.report_type.value if hasattr(r.report_type, "value") else str(r.report_type), r.row_code): r
            for r in proj_result.scalars().all()
        }

        # 加载 standard 级配置（主模板）
        master_result = await self.db.execute(
            sa.select(ReportConfig).where(
                ReportConfig.applicable_standard == standard,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        master_rows = list(master_result.scalars().all())

        updated_count = 0

        for master_row in master_rows:
            key = (
                master_row.report_type.value if hasattr(master_row.report_type, "value") else str(master_row.report_type),
                master_row.row_code,
            )
            proj_row = proj_rows.get(key)

            if proj_row is None:
                # 项目没有该行 → 新增（从主模板同步）
                new_row = ReportConfig(
                    report_type=master_row.report_type,
                    row_number=master_row.row_number,
                    row_code=master_row.row_code,
                    row_name=master_row.row_name,
                    indent_level=master_row.indent_level,
                    formula=master_row.formula,
                    applicable_standard=project_standard,
                    is_total_row=master_row.is_total_row,
                    parent_row_code=master_row.parent_row_code,
                    is_stale=False,
                )
                self.db.add(new_row)
                updated_count += 1
            else:
                # 项目已有该行
                if keep_local and proj_row.formula != master_row.formula:
                    # 本地覆盖保留：公式不同说明项目已自定义，不覆盖
                    # 但清除 is_stale 标记（用户已知晓差异）
                    proj_row.is_stale = False
                    continue

                if not keep_local or proj_row.formula == master_row.formula:
                    # 非本地覆盖 或 公式相同（可能其他字段变了）→ 同步
                    proj_row.formula = master_row.formula
                    proj_row.row_name = master_row.row_name
                    proj_row.indent_level = master_row.indent_level
                    proj_row.is_total_row = master_row.is_total_row
                    proj_row.parent_row_code = master_row.parent_row_code
                    proj_row.is_stale = False
                    updated_count += 1

        await self.db.flush()
        return updated_count
