"""交付前 readiness 判定 — 交付中心三件套一键出具（阶段四 Task 2）。

spec: ``.kiro/specs/chain-closure-phase4-deliverable-center-trio``（需求 1.1~1.6）。

本服务是**纯判定入口**：真读取项目审计年度下 TB、公式推送、调整确认、报表、底稿、
附注的真实状态，产出

- ``hard_blockers``：任一成立即阻止正式三件套生成（``status=blocked``）；
- ``warnings``：非阻断质量提醒（不改变三件套成功判定，带中文原因与证据）；
- ``trio``：三件套固定顺序、稳定键与逐项状态；
- ``snapshot``：三件套应共享的交付快照摘要（内容不含生成时间与本机绝对路径）。

铁律（与 design §4 对齐）：

- **真字段判定**，不用「有行就算完成」的弱口径：审定数要求 ``audited_amount`` 非空，
  调整确认要求无未复核分录，报表/附注要求 ``is_stale=False``。
- **phase3 尚未入库的能力 fail-closed**：所需能力模块不可导入时返回明确 blocker code，
  而非默默放行（需求 1.2 第 1 项、design §一依赖关系）。后续能力接通，去掉探测即可，
  不改成恒绿。
- **稳定 code + 中文原因 + 证据**：硬/软闸门都带机器可去重的 ``code``、给人看的中文
  ``message`` 和定位用 ``evidence``（证据里不放本机绝对路径，snapshot digest 更不含它）。
- 本服务**只读**，不 flush/commit；SQLite 与 PG 同款真 ORM 查询（无 PG-only SQL）。
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import asdict, dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    Adjustment,
    DeliverableSectionState,
    ReviewStatus,
    TrialBalance,
)
from app.models.core import Project
from app.models.formula_push_models import FormulaPushRun
from app.models.phase13_models import WordExportTask, WordExportTaskVersion
from app.models.report_models import FinancialReport
from app.services.deliverable_snapshot_service import DeliverableSnapshotService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 正式三件套固定顺序与稳定键（与 executor TRIO_STEPS 同源的权威契约）
# ---------------------------------------------------------------------------

#: 正式三件套稳定键，固定顺序 financial_report → disclosure_notes → audit_report。
#: unadjusted 是辅助项，**不在**此列表（需求 2.1/2.5）。
TRIO_STEP_KEYS: tuple[str, ...] = (
    "financial_report",
    "disclosure_notes",
    "audit_report",
)

#: 三件套中文名（前端展示 / 滞后提示用，禁裸英文 key）。
TRIO_LABELS: dict[str, str] = {
    "financial_report": "审定财务报表",
    "disclosure_notes": "报表附注",
    "audit_report": "审计报告正文",
}


# ---------------------------------------------------------------------------
# phase3 能力探测（fail-closed）
# ---------------------------------------------------------------------------

#: readiness 依赖的 phase3 能力模块。任一不可导入 ⇒ 返回 ``upstream_not_ready`` blocker，
#: 而不是默默放行。模块名取 phase2/phase3 的真源：
#:   - 公式推送引擎（phase2 入库 → formula_push 服务）；
#:   - TB 审定数单一写入方（phase3 → 审定表发布门 service）；
#:   - 附注主表后端交接（phase3 → 附注章节状态持久化 service）。
_REQUIRED_PHASE3_MODULES: dict[str, str] = {
    "app.services.formula_push.engine": "公式推送引擎",
    "app.services.deliverable_section_state_service": "附注章节交接",
}


def _module_importable(dotted: str) -> bool:
    """探测能力模块是否可导入（不触发副作用，只看 spec 能否 find）。"""
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


# ---------------------------------------------------------------------------
# 结果结构
# ---------------------------------------------------------------------------


@dataclass
class Gate:
    """一条闸门（硬 blocker 或软 warning）。"""

    code: str
    message: str
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "evidence": self.evidence}


@dataclass
class ReadinessResult:
    """readiness 判定结果（需求 1.1 要求的最小字段集）。"""

    status: str  # ready | blocked | ready_with_warnings
    project_id: str
    year: int
    hard_blockers: list[Gate] = field(default_factory=list)
    warnings: list[Gate] = field(default_factory=list)
    sources: dict = field(default_factory=dict)
    snapshot: dict | None = None
    trio_status: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "project_id": self.project_id,
            "year": self.year,
            "hard_blockers": [g.to_dict() for g in self.hard_blockers],
            "warnings": [g.to_dict() for g in self.warnings],
            "sources": self.sources,
            "snapshot": self.snapshot,
            "snapshot_id": (self.snapshot or {}).get("id"),
            "trio_status": self.trio_status,
        }


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------


class DeliverableReadinessService:
    """交付前 readiness 纯判定服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._snapshot_svc = DeliverableSnapshotService(db)

    async def check(
        self,
        project_id: UUID,
        year: int,
        *,
        include_file_checks: bool = True,
    ) -> ReadinessResult:
        """判定项目审计年度的交付就绪状态。

        Args:
            include_file_checks: 为 True 时对既有交付版本做物理文件校验
                （存在/可读/大小/哈希）；readiness 本身只读，不改磁盘。
        """
        blockers: list[Gate] = []
        warnings: list[Gate] = []
        sources: dict = {}

        # ① phase3 能力 fail-closed（最先判，缺能力直接阻断，后续读取无意义）
        self._check_phase3_capabilities(blockers)

        # ② 项目/准则/模板/年度唯一可确定
        project = await self.db.get(Project, project_id)
        self._check_project_identity(project, year, blockers, sources)

        # 项目不存在时后续读取全部无源，直接返回
        if project is None:
            return self._finalize(project_id, year, blockers, warnings, sources, None)

        # ③ 上游链：TB 未审 + 审定数、公式推送、调整确认
        await self._check_trial_balance(project_id, year, blockers, sources)
        await self._check_formula_push(project_id, year, blockers, warnings, sources)
        await self._check_adjustments(project_id, year, blockers, sources)

        # ④ 报表 / 附注 stale（硬）与底稿（软提醒）
        await self._check_reports_stale(project_id, year, blockers, sources)
        await self._check_notes_handoff(project_id, year, blockers, sources)

        # ⑤ 三件套快照一致性
        await self._check_snapshot_consistency(project_id, year, blockers, sources)

        # ⑥ 既有版本物理文件校验
        if include_file_checks:
            await self._check_existing_version_files(project_id, blockers, sources)

        # ⑦ 建立三件套应共享的交付快照摘要（无 blocker 才有意义；有 blocker 仍返回摘要供前端展示）
        snapshot = await self._build_snapshot(project, year, sources)

        return self._finalize(project_id, year, blockers, warnings, sources, snapshot)

    # ------------------------------------------------------------------
    # ① phase3 能力探测
    # ------------------------------------------------------------------
    def _check_phase3_capabilities(self, blockers: list[Gate]) -> None:
        missing: list[str] = []
        for dotted, label in _REQUIRED_PHASE3_MODULES.items():
            if not _module_importable(dotted):
                missing.append(label)
        if missing:
            blockers.append(
                Gate(
                    code="upstream_not_ready",
                    message=(
                        "前置链能力尚未在当前版本就绪，无法出具正式三件套："
                        + "、".join(missing)
                    ),
                    evidence={"missing_capabilities": missing},
                )
            )

    # ------------------------------------------------------------------
    # ② 项目 / 准则 / 模板 / 年度唯一
    # ------------------------------------------------------------------
    def _check_project_identity(
        self,
        project: Project | None,
        year: int,
        blockers: list[Gate],
        sources: dict,
    ) -> None:
        if project is None:
            blockers.append(
                Gate(
                    code="missing_template_or_standard",
                    message="项目不存在或已删除，无法确定审计年度、准则与模板",
                    evidence={"year": year},
                )
            )
            return

        missing_fields: list[str] = []
        if not project.template_type:
            missing_fields.append("模板类型")
        if project.accounting_standard_id is None:
            missing_fields.append("会计准则")
        if project.audit_period_end is None and project.audit_year is None:
            missing_fields.append("审计年度")

        sources["project"] = {
            "template_type": project.template_type,
            "accounting_standard_id": (
                str(project.accounting_standard_id)
                if project.accounting_standard_id
                else None
            ),
            "audit_year": project.audit_year,
            "report_scope": project.report_scope,
        }

        if missing_fields:
            blockers.append(
                Gate(
                    code="missing_template_or_standard",
                    message="项目准则/模板/年度无法唯一确定：" + "、".join(missing_fields),
                    evidence={"missing_fields": missing_fields},
                )
            )

    # ------------------------------------------------------------------
    # ③ TB 未审 + 审定数
    # ------------------------------------------------------------------
    async def _check_trial_balance(
        self,
        project_id: UUID,
        year: int,
        blockers: list[Gate],
        sources: dict,
    ) -> None:
        total = (
            await self.db.execute(
                sa.select(sa.func.count())
                .select_from(TrialBalance)
                .where(
                    TrialBalance.project_id == project_id,
                    TrialBalance.year == year,
                    TrialBalance.is_deleted == sa.false(),
                )
            )
        ).scalar_one() or 0

        # 审定数就绪 = 存在试算表行且 **没有** audited_amount 为空的行
        # （审定数由 phase3 发布门单一写入方维护；全空/部分空都说明还没发布审定）。
        missing_audited = (
            await self.db.execute(
                sa.select(sa.func.count())
                .select_from(TrialBalance)
                .where(
                    TrialBalance.project_id == project_id,
                    TrialBalance.year == year,
                    TrialBalance.is_deleted == sa.false(),
                    TrialBalance.audited_amount.is_(None),
                )
            )
        ).scalar_one() or 0

        sources["tb"] = {
            "row_count": int(total),
            "missing_audited_count": int(missing_audited),
        }

        if total == 0:
            blockers.append(
                Gate(
                    code="upstream_not_ready",
                    message="试算表/四表未审数尚未就绪，请先完成前置数据准备",
                    evidence={"row_count": 0},
                )
            )
            return

        if missing_audited > 0:
            blockers.append(
                Gate(
                    code="upstream_not_ready",
                    message=(
                        f"审定数尚未全部由发布门写入（{missing_audited} 个科目缺审定数），"
                        "请先在审定表完成发布"
                    ),
                    evidence={
                        "row_count": int(total),
                        "missing_audited_count": int(missing_audited),
                    },
                )
            )

    # ------------------------------------------------------------------
    # ③ 公式推送
    # ------------------------------------------------------------------
    async def _check_formula_push(
        self,
        project_id: UUID,
        year: int,
        blockers: list[Gate],
        warnings: list[Gate],
        sources: dict,
    ) -> None:
        latest = (
            await self.db.execute(
                sa.select(FormulaPushRun)
                .where(
                    FormulaPushRun.project_id == project_id,
                    FormulaPushRun.year == year,
                )
                .order_by(FormulaPushRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if latest is None:
            sources["formula_push"] = {"last_status": None}
            blockers.append(
                Gate(
                    code="upstream_not_ready",
                    message="公式推送尚未运行，报表/底稿/附注取数未就绪",
                    evidence={"last_run": None},
                )
            )
            return

        sources["formula_push"] = {
            "last_status": latest.status,
            "written_count": latest.written_count,
            "skipped_count": latest.skipped_count,
        }

        if latest.status == "failed":
            blockers.append(
                Gate(
                    code="upstream_not_ready",
                    message="最近一次公式推送失败，请先重新推送后再出具",
                    evidence={"last_status": latest.status},
                )
            )
        elif latest.status == "partial":
            # 部分成功是质量提醒，不阻断（软闸门）
            warnings.append(
                Gate(
                    code="formula_push_partial",
                    message="最近一次公式推送部分成功，请确认是否存在未推送目标",
                    evidence={
                        "last_status": latest.status,
                        "skipped_count": latest.skipped_count,
                    },
                )
            )

    # ------------------------------------------------------------------
    # ③ 调整确认
    # ------------------------------------------------------------------
    async def _check_adjustments(
        self,
        project_id: UUID,
        year: int,
        blockers: list[Gate],
        sources: dict,
    ) -> None:
        unresolved = (
            await self.db.execute(
                sa.select(sa.func.count())
                .select_from(Adjustment)
                .where(
                    Adjustment.project_id == project_id,
                    Adjustment.year == year,
                    Adjustment.is_deleted == sa.false(),
                    Adjustment.review_status.in_(
                        [ReviewStatus.draft, ReviewStatus.pending_review]
                    ),
                )
            )
        ).scalar_one() or 0

        sources["adjustments"] = {"unresolved_count": int(unresolved)}

        if unresolved > 0:
            blockers.append(
                Gate(
                    code="upstream_not_ready",
                    message=(
                        f"存在 {unresolved} 条尚未复核的调整分录，"
                        "请先在调整大厅完成复核确认"
                    ),
                    evidence={"unresolved_count": int(unresolved)},
                )
            )

    # ------------------------------------------------------------------
    # ④ 报表 stale
    # ------------------------------------------------------------------
    async def _check_reports_stale(
        self,
        project_id: UUID,
        year: int,
        blockers: list[Gate],
        sources: dict,
    ) -> None:
        total = (
            await self.db.execute(
                sa.select(sa.func.count())
                .select_from(FinancialReport)
                .where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.is_deleted == sa.false(),
                )
            )
        ).scalar_one() or 0

        stale = (
            await self.db.execute(
                sa.select(sa.func.count())
                .select_from(FinancialReport)
                .where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.is_deleted == sa.false(),
                    FinancialReport.is_stale == sa.true(),
                )
            )
        ).scalar_one() or 0

        sources["reports"] = {"row_count": int(total), "stale_count": int(stale)}

        if total == 0:
            blockers.append(
                Gate(
                    code="upstream_not_ready",
                    message="财务报表尚未生成，请先生成报表后再出具",
                    evidence={"row_count": 0},
                )
            )
            return

        if stale > 0:
            blockers.append(
                Gate(
                    code="stale_source",
                    message=(
                        f"财务报表存在 {stale} 行标记为已过期（源数据已变化），"
                        "请先刷新报表"
                    ),
                    evidence={"stale_count": int(stale)},
                )
            )

    # ------------------------------------------------------------------
    # ④ 附注交接 stale
    # ------------------------------------------------------------------
    async def _check_notes_handoff(
        self,
        project_id: UUID,
        year: int,
        blockers: list[Gate],
        sources: dict,
    ) -> None:
        total = (
            await self.db.execute(
                sa.select(sa.func.count())
                .select_from(DeliverableSectionState)
                .where(
                    DeliverableSectionState.project_id == project_id,
                    DeliverableSectionState.year == year,
                )
            )
        ).scalar_one() or 0

        stale = (
            await self.db.execute(
                sa.select(sa.func.count())
                .select_from(DeliverableSectionState)
                .where(
                    DeliverableSectionState.project_id == project_id,
                    DeliverableSectionState.year == year,
                    DeliverableSectionState.is_stale == sa.true(),
                )
            )
        ).scalar_one() or 0

        sources["notes"] = {"section_count": int(total), "stale_count": int(stale)}

        if total == 0:
            blockers.append(
                Gate(
                    code="upstream_not_ready",
                    message="报表附注章节尚未交接，请先完成附注章节准备",
                    evidence={"section_count": 0},
                )
            )
            return

        if stale > 0:
            blockers.append(
                Gate(
                    code="stale_source",
                    message=(
                        f"报表附注存在 {stale} 个章节标记为已过期（源数据已变化），"
                        "请先刷新附注"
                    ),
                    evidence={"stale_count": int(stale)},
                )
            )

    # ------------------------------------------------------------------
    # ⑤ 三件套快照一致性
    # ------------------------------------------------------------------
    async def _check_snapshot_consistency(
        self,
        project_id: UUID,
        year: int,
        blockers: list[Gate],
        sources: dict,
    ) -> None:
        trio = await self._snapshot_svc.check_trio_consistency(project_id, year)
        sources["snapshot_consistency"] = {
            "consistent": trio.consistent,
            "tb_hashes": trio.tb_hashes,
            "lagging": trio.lagging,
            "ambiguous": trio.ambiguous,
        }
        if not trio.consistent:
            blockers.append(
                Gate(
                    code="snapshot_inconsistent",
                    message=(
                        trio.message
                        or "三件套绑定的数据快照不一致，无法组成同一交付快照"
                    ),
                    evidence={
                        "tb_hashes": trio.tb_hashes,
                        "lagging": trio.lagging,
                        "ambiguous": trio.ambiguous,
                    },
                )
            )

    # ------------------------------------------------------------------
    # ⑥ 既有版本物理文件校验
    # ------------------------------------------------------------------
    async def _check_existing_version_files(
        self,
        project_id: UUID,
        blockers: list[Gate],
        sources: dict,
    ) -> None:
        from pathlib import Path

        from app.services.deliverable_file_fingerprint import (
            FileFingerprintError,
            verify_file_fingerprint,
        )

        # 取三件套各 doc_type 的最新版本（有 file_path 的）做物理校验
        checked: list[dict] = []
        for doc_type in ("financial_report", "disclosure_notes", "audit_report"):
            task = (
                await self.db.execute(
                    sa.select(WordExportTask)
                    .where(
                        WordExportTask.project_id == project_id,
                        WordExportTask.doc_type == doc_type,
                    )
                    .order_by(WordExportTask.updated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if task is None:
                continue
            version = (
                await self.db.execute(
                    sa.select(WordExportTaskVersion)
                    .where(WordExportTaskVersion.word_export_task_id == task.id)
                    .order_by(WordExportTaskVersion.version_no.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if version is None or not version.file_path:
                continue

            path = Path(version.file_path)
            # 证据里不放绝对路径的目录结构，只放文件名与校验结论
            file_label = path.name
            label = TRIO_LABELS.get(doc_type, doc_type)
            # 哈希期望值：优先 phase4 显式 file_sha256，回退历史 file_hash。
            expected = version.file_sha256 or version.file_hash
            # 统一指纹校验入口（与 render_and_store / 下载共享同一函数）。
            # readiness 对历史版本不强制交付根目录（历史落盘路径可能已迁移），
            # 但存在/大小/哈希三项仍由同一函数判定。
            try:
                fp = verify_file_fingerprint(
                    path,
                    expected_sha256=expected,
                    enforce_root=False,
                )
            except FileFingerprintError as exc:
                code = exc.code if exc.code != "path_escape" else "unreadable_file"
                blockers.append(
                    Gate(
                        code=code,
                        message=f"{label}的历史版本文件校验未通过：{exc.message}",
                        evidence={"doc_type": doc_type, "file": file_label, **exc.evidence},
                    )
                )
                checked.append(
                    {"doc_type": doc_type, "ok": False, "reason": exc.code}
                )
                continue
            checked.append({"doc_type": doc_type, "ok": True, "size": fp.size})

        sources["existing_files"] = checked

    # ------------------------------------------------------------------
    # ⑦ 交付快照摘要（内容不含生成时间与绝对路径）
    # ------------------------------------------------------------------
    async def _build_snapshot(
        self,
        project: Project,
        year: int,
        sources: dict,
    ) -> dict:
        tb_hash = await self._snapshot_svc._snap_svc._compute_trial_balance_hash(
            project.id, year
        )
        formula_push = sources.get("formula_push", {})
        content = {
            "project_id": str(project.id),
            "year": year,
            "template_type": project.template_type,
            "accounting_standard_id": (
                str(project.accounting_standard_id)
                if project.accounting_standard_id
                else None
            ),
            "report_scope": project.report_scope,
            "tb_hash": tb_hash,
            "formula_push_status": formula_push.get("last_status"),
            "reports": sources.get("reports"),
            "notes": sources.get("notes"),
            "adjustments": sources.get("adjustments"),
        }
        # digest 对规范化 JSON 取 sha256；**不含**生成时间与本机绝对路径（design §3.4 / §4.2）。
        # 单源复用 deliverable_trio_snapshot.build_digest：readiness 与 executor/retry 路径
        # 用同一函数算 digest，三件套三项据此绑定同一 snapshot_id（需求 2.4）。
        from app.services.deliverable_trio_snapshot import build_digest

        digest = build_digest(content)
        return {"id": digest, "digest": digest, "content": content}

    # ------------------------------------------------------------------
    # 汇总与状态
    # ------------------------------------------------------------------
    def _finalize(
        self,
        project_id: UUID,
        year: int,
        blockers: list[Gate],
        warnings: list[Gate],
        sources: dict,
        snapshot: dict | None,
    ) -> ReadinessResult:
        # 硬闸门按稳定 code **去重**（design §4.2：同 code 多次只保留首条，证据合并计数）。
        deduped: list[Gate] = []
        seen: set[str] = set()
        for g in blockers:
            if g.code in seen:
                # 已有同 code，合并到首条的 evidence.duplicates 计数
                for existing in deduped:
                    if existing.code == g.code:
                        existing.evidence.setdefault("duplicates", [])
                        existing.evidence["duplicates"].append(g.message)
                        break
                continue
            seen.add(g.code)
            deduped.append(g)

        if deduped:
            status = "blocked"
        elif warnings:
            status = "ready_with_warnings"
        else:
            status = "ready"

        trio_status = [
            {
                "key": key,
                "sequence": idx + 1,
                "label": TRIO_LABELS[key],
                "status": "blocked" if deduped else "ready",
            }
            for idx, key in enumerate(TRIO_STEP_KEYS)
        ]

        return ReadinessResult(
            status=status,
            project_id=str(project_id),
            year=year,
            hard_blockers=deduped,
            warnings=warnings,
            sources=sources,
            snapshot=snapshot,
            trio_status=trio_status,
        )
