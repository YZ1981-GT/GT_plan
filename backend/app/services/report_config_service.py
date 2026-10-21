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
from app.services.formula_settings.legacy_report import (
    approve_baseline_candidate,
    master_base,
    sync_project_to_global,
    update_row,
)

logger = logging.getLogger(__name__)

SEED_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "report_config_seed.json"

#: 比较类算子 —— 出现即视为「逻辑审核」（勾稽式），不能当自动运算去执行。
_LOGIC_CHECK_TOKENS = ("==", "!=", ">=", "<=", "≈", "≠")

#: 取数函数 —— 出现即视为「自动运算」（从四表/报表行/附注/底稿取值再算）。
_AUTO_CALC_FUNCS = ("TB(", "SUM_TB(", "ROW(", "SUM_ROW(", "NOTE(", "WP(", "AUX(")


def derive_formula_category(formula: str) -> str | None:
    """由公式形态推导 ``formula_category``；判不准返回 ``None``。

    判据（顺序敏感）：

    1. 含比较算子（``==`` / ``>=`` / ``≠`` 等）⇒ ``logic_check``：这类是勾稽校验，
       **绝不能**误标成 ``auto_calc``，否则「应用自动运算」会把校验式拿去当取数执行；
    2. 含取数函数（``TB(`` / ``ROW(`` / ``NOTE(`` …）⇒ ``auto_calc``；
    3. 其余（纯常量、看不出来源的表达式）⇒ ``None``，保持为空。

    🔴 宁缺勿造：错分类比空分类更贵 —— 空分类只是看板上显示「未分类」，
    错分类会进入批量执行链路。

    单一真源：脚本 ``scripts/fix/fix_report_config_formula_category.py`` 与
    service 的 :meth:`ReportConfigService.backfill_formula_categories` 都调本函数。
    """
    expr = (formula or "").strip()
    if not expr:
        return None
    if any(token in expr for token in _LOGIC_CHECK_TOKENS):
        return "logic_check"
    # 单个 `=` 也算比较（排除 `==` 已在上面命中、以及 `>=`/`<=` 的组合形态）
    if "=" in expr.replace(">=", "").replace("<=", "").replace("==", "").replace("!=", ""):
        return "logic_check"
    if any(func in expr.upper() for func in _AUTO_CALC_FUNCS):
        return "auto_calc"
    return None


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
                    # V179: 调整列公式
                    aje_formula=row.get("aje_formula"),
                    rje_formula=row.get("rje_formula"),
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
        """将标准配置**全量**复制为项目级配置（``project:{project_id}``）。

        .. deprecated::
           新调用方请用 :meth:`materialize_project_presets`（``mode='sync'``）：

           * 本方法是**一次性全量**克隆（含无公式的结构行），二次执行直接抛
             ``ValueError`` ⇒ 无法增量补公式，落库量也是前者的数倍；
           * 项目级行的唯一消费方是取数层，只按 ``formula`` 查，结构行落进来
             不改变任何取数结果。

           保留原因：``POST /api/report-config/clone``（``mode='strict'``，默认）
           与 ``backend/tests/test_report_config.py`` 仍依赖这一语义。
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
                # 🔴 分类/说明/来源必须一起克隆：只复制 formula 会让项目级行全变
                # 「未分类」且丢掉编制说明，公式管理中心里看不出这条公式是干什么的。
                formula_category=src.formula_category,
                formula_description=src.formula_description,
                formula_source=src.formula_source,
                # V179: 调整列公式同步克隆
                aje_formula=src.aje_formula,
                rje_formula=src.rje_formula,
                applicable_standard=project_standard,
                is_total_row=src.is_total_row,
                parent_row_code=src.parent_row_code,
                **master_base(src),  # V199：以准则行为基线（跟随全局，全局再改时自动同步）
            )
            self.db.add(clone)
            count += 1

        await self.db.flush()
        return count

    # ------------------------------------------------------------------
    # 公式分类回填（幂等）
    # ------------------------------------------------------------------
    async def backfill_formula_categories(
        self,
        applicable_standard: str | None = None,
        include_project_scoped: bool = False,
    ) -> dict:
        """给「有公式但无分类」的行回填 ``formula_category``（幂等）。

        分类由公式形态推导，见 :func:`derive_formula_category`；推导不出的行**保持
        为空**（宁缺勿造：错分类会让「应用自动运算」把校验式也拿去算）。

        Args:
            applicable_standard: 限定准则；省略则处理全部非项目级口径。
            include_project_scoped: 是否一并处理 ``project:{id}`` 行（默认不处理，
                避免一次调用同时改模板级与各项目级两类数据）。

        Returns:
            ``{scanned, filled, undecided, by_category}``
        """
        stmt = sa.select(ReportConfig).where(
            ReportConfig.is_deleted == sa.false(),
            ReportConfig.formula.isnot(None),
            ReportConfig.formula != "",
            sa.or_(
                ReportConfig.formula_category.is_(None),
                ReportConfig.formula_category == "",
            ),
        )
        if applicable_standard:
            stmt = stmt.where(ReportConfig.applicable_standard == applicable_standard)
        elif not include_project_scoped:
            stmt = stmt.where(ReportConfig.applicable_standard.not_like("project:%"))

        rows = list((await self.db.execute(stmt)).scalars().all())
        filled = 0
        undecided = 0
        by_category: dict[str, int] = {}
        for row in rows:
            category = derive_formula_category(row.formula or "")
            if category is None:
                undecided += 1
                continue
            row.formula_category = category
            by_category[category] = by_category.get(category, 0) + 1
            filled += 1

        await self.db.flush()
        return {
            "scanned": len(rows),
            "filled": filled,
            "undecided": undecided,
            "by_category": by_category,
        }

    # ------------------------------------------------------------------
    # 预设公式落入项目（幂等，可重复执行）
    # ------------------------------------------------------------------
    async def materialize_project_presets(
        self,
        project_id: UUID,
        applicable_standard: str | None = None,
        overwrite: bool = False,
        user_id: UUID | None = None,
    ) -> dict:
        """把标准模板的**预设公式**落成项目级配置（``project:{id}``）。

        与 :meth:`clone_report_config` 的区别（后者是一次性全量克隆、二次执行报错）：

        * **幂等**：已存在的项目级行默认跳过，可重复执行；
        * **只落有公式的行**：项目级行的唯一消费方是取数层
          （``report_account_mapping`` / ``four_table.report_line_accounts`` /
          ``semantic_account_resolver`` / ``i_cycle_accounts`` 都按
          ``applicable_standard = 'project:{id}'`` 优先查 ``formula``），
          无公式的结构行落进来只会翻倍数据量、不改变任何取数结果；
        * **带分类/说明/来源**：公式管理中心要显示这些列。

        Args:
            project_id: 目标项目。
            applicable_standard: 源标准（如 ``soe_standalone``）；省略时按项目派生。
            overwrite: 项目级已有该行时是否用模板公式覆盖。

        Returns:
            ``{standard, project_standard, created, updated, skipped, master_with_formula, events}``；
            ``overwrite`` 覆盖 = 本项目「采用全局」（formula-global-settings-sync）：同时结案该公式位的待确认、
            写带 project_id 的留痕，``events`` 由调用方 commit 后交 ``publish_events``。
        """
        project_standard = f"project:{project_id}"
        standard = applicable_standard or await self.resolve_applicable_standard(
            self.db, project_id
        ) or "enterprise"

        master_rows = [
            r
            for r in await self.list_configs(applicable_standard=standard)
            if (r.formula or "").strip()
        ]

        existing_result = await self.db.execute(
            sa.select(ReportConfig).where(
                ReportConfig.applicable_standard == project_standard,
                ReportConfig.is_deleted == sa.false(),
            )
        )
        existing = {
            (
                r.report_type.value if hasattr(r.report_type, "value") else str(r.report_type),
                r.row_code,
            ): r
            for r in existing_result.scalars().all()
        }

        created = updated = skipped = 0
        adopted: list[tuple[str, str | None, str | None]] = []  # (公式位, 原公式, 新公式)
        for src in master_rows:
            key = (
                src.report_type.value
                if hasattr(src.report_type, "value")
                else str(src.report_type),
                src.row_code,
            )
            hit = existing.get(key)
            if hit is not None:
                if overwrite and hit.formula != src.formula:
                    adopted.append((f"{key[0]}:{src.row_code}", hit.formula, src.formula))
                    hit.formula = src.formula
                    hit.formula_category = src.formula_category
                    hit.formula_description = src.formula_description
                    hit.formula_source = src.formula_source
                    hit.aje_formula = src.aje_formula
                    hit.rje_formula = src.rje_formula
                    for attr, value in master_base(src).items():  # 采用全局 ⇒ 基线 = 全局
                        setattr(hit, attr, value)
                    hit.formula_version = (hit.formula_version or 1) + 1
                    updated += 1
                else:
                    skipped += 1
                continue
            self.db.add(
                ReportConfig(
                    report_type=src.report_type,
                    row_number=src.row_number,
                    row_code=src.row_code,
                    row_name=src.row_name,
                    indent_level=src.indent_level,
                    formula=src.formula,
                    formula_category=src.formula_category,
                    formula_description=src.formula_description,
                    formula_source=src.formula_source,
                    aje_formula=src.aje_formula,
                    rje_formula=src.rje_formula,
                    applicable_standard=project_standard,
                    is_total_row=src.is_total_row,
                    parent_row_code=src.parent_row_code,
                    **master_base(src),
                )
            )
            created += 1

        events: list[dict] = []
        if adopted:
            # overwrite 覆盖 = 本项目采用全局：结案这些公式位的待确认（adopt），写一条项目留痕，
            # 并上报有效定义变化（调用方 commit 后发事件 → 报表重算）。
            from app.services.formula_settings.audit import audit_project, change_entry
            from app.services.formula_settings.pending import close_pending

            slot_keys = [slot for slot, _, _ in adopted]
            await close_pending(self.db, project_id, "report", slot_keys, status="resolved",
                                resolution="adopt", user_id=user_id)
            await audit_project(
                self.db, user_id=user_id, project_id=project_id, domain="report", action="adapt",
                source="materialize_overwrite",
                changes=[change_entry("report", slot, {"formula": old}, {"formula": new})
                         for slot, old, new in adopted])
            events = [{"project_id": str(project_id), "slot_keys": slot_keys}]

        await self.db.flush()
        return {
            "standard": standard,
            "project_standard": project_standard,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "master_with_formula": len(master_rows),
            "events": events,
        }

    # ------------------------------------------------------------------
    # 修改配置行
    # ------------------------------------------------------------------
    async def update_config(
        self,
        config_id: UUID,
        updates: dict,
        user_id: UUID | None = None,
    ) -> ReportConfig:
        """修改报表配置行 —— 经公式设置同步内核（spec formula-global-settings-sync R9）。

        全局行改公式 = 直接发布（全部应用 + 冲突交项目确认）；项目行改公式 = 保存本项目适配；
        改公式须带 ``expected_version``（缺失 428、不一致 409，抛 ``FormulaSettingError``）。
        结构字段（行名 / 缩进 / 合计行 / 父行）直接写。留痕由内核写（带 project_id，
        原写法取 ``row.project_id`` 恒为 None ⇒ 项目「公式历史」查不到）。
        需要传播的调用方改用 ``legacy_report.update_row`` 拿 events，commit 后发布。
        """
        row = await self.get_config(config_id)
        if row is None:
            raise ValueError("配置行不存在")
        return (await update_row(self.db, row, updates, user_id=user_id))["row"]

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
    ) -> dict | None:
        """admin 审核候选：通过则作为全局发布 + 版本号 + append_audit_log；返回发布结果（含 events）。

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
            return None

        # 通过：经同步内核作为全局发布（V199，source=promote）—— 跟随全局的项目自动更新，
        # 改过且不同的项目生成待确认事项；不再只改准则行、让各项目各自不知情。
        candidate.status = "approved"
        published = await approve_baseline_candidate(
            self.db, standard=candidate.standard, report_type=candidate.report_type,
            row_code=candidate.row_code, formula=candidate.candidate_formula, reviewer=reviewer,
            source_project_id=candidate.source_project_id, candidate_id=candidate_id,
        )
        old_formula = published["old_formula"]

        # 版本号递增
        candidate.version = candidate.version + 1

        # 审计留痕（event_type='report_config_changed'）；SAVEPOINT 隔离：失败不让 PG 事务中止
        try:
            from app.services.audit_log_helper import append_audit_log

            async with self.db.begin_nested():
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
        return published

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
        """主模板更新同步到项目 —— 经同步内核（spec formula-global-settings-sync R9.2）。

        跟随全局的行（本项目 == 基线）改为当前全局；已一致只更新基线；改过且不同的行
        ``keep_local=True`` 生成待确认事项（🔴 原实现只清过期标记了事，项目永远不知道主模板改了），
        ``keep_local=False`` 直接采用全局。没有本项目行的公式位本就读全局，不再复制。

        Returns:
            本项目公式被改为全局的行数（待确认 / 只更新基线的行不计；明细见 ``sync_project_to_global``）
        """
        result = await sync_project_to_global(
            self.db, project_id=project_id, standard=standard, keep_local=keep_local,
        )
        return result["updated"]
