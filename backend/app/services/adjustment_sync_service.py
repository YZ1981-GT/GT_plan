"""底稿调整分录 → 集中式登记 汇聚服务

spec: workpaper-adjustment-centralization + chain-closure-phase3-push-rollout Task 5

把各循环底稿调整分录 tab（存 checklist_responses JSON）的一组分录，汇聚为集中式
`adjustments`/`adjustment_entry` 记录（`origin='workpaper'`），供 Adjustments.vue 集中
审阅/导出/溯源，并支持集中复核状态回流底稿。

关键约束：
- **幂等** by `source_ref = {wp_id}:{item_id}`：重存更新、删除清理、approved 锁定。
- **内容签名去重**（ADR-P3-008）：同一 source_ref 再次同步时，先比内容签名
  （类型+摘要+逐行科目/名称/报表行/借/贷）。相同 → 不写库、不换编号、原样返回；
  不同 → 原地更新（保组号与编号，软删旧行写新行），pending_review/rejected 回 draft；
  approved → APPROVED_LOCKED 拒绝。
- **不发 ADJUSTMENT_CREATED 事件**：workpaper origin 调整已由审定表 writeback 体现在
  `trial_balance.audited_amount`，不再经 recalc 路径写 `aje_adjustment`（Req4 消除双计）。
- **零回归**：只新增汇聚通道，既有底稿→审定表→TB 链路一行不改。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountChart,
    AccountSource,
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    ReviewStatus,
)
from app.models.audit_platform_schemas import (
    AdjustmentGroupResponse,
    AdjustmentSyncRequest,
)
from app.services.adjustment_service import AdjustmentService


class AdjustmentSyncError(ValueError):
    """汇聚业务错误（携错误码供 router 转 4xx）。"""

    def __init__(self, code: str, message: str, detail: object | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


class AdjustmentSyncService:
    """底稿调整 → 集中登记 汇聚。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._adj = AdjustmentService(db)

    @staticmethod
    def build_source_ref(wp_id: UUID | str, item_id: str) -> str:
        return f"{wp_id}:{item_id}"

    # ------------------------------------------------------------------
    # 内容签名（ADR-P3-008）
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_content_signature(
        adjustment_type: "AdjustmentType",
        description: str | None,
        resolved_codes: list[str],
        line_items: list,
    ) -> str:
        """内容签名 = sha256(类型 + 摘要 + 逐行：科目/名称/报表行/借/贷)。

        用于判断底稿分录内容是否有变化。签名相同 → 不写库；不同 → 原地更新。
        金额一律 quantize 到 2 位小数后再 str，消除 SQLite 往返后精度漂移。
        """
        parts: list[str] = [
            str(adjustment_type.value if hasattr(adjustment_type, "value") else adjustment_type),
            description or "",
        ]
        _q = Decimal("0.01")
        for code, li in zip(resolved_codes, line_items):
            d = (li.debit_amount or Decimal(0))
            c = (li.credit_amount or Decimal(0))
            parts.append("|".join([
                code,
                (li.account_name or "").strip(),
                (li.report_line_code or "").strip(),
                str(Decimal(str(d)).quantize(_q)),
                str(Decimal(str(c)).quantize(_q)),
            ]))
        raw = "\n".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _compute_existing_signature(
        adj_rows: list["Adjustment"],
        entry_rows: list["AdjustmentEntry"],
    ) -> str:
        """从已存在的 ORM 行计算内容签名（与请求签名同口径）。"""
        if not adj_rows:
            return ""
        head = adj_rows[0]
        parts: list[str] = [
            str(head.adjustment_type.value if hasattr(head.adjustment_type, "value") else head.adjustment_type),
            head.description or "",
        ]
        _q = Decimal("0.01")
        # entry_rows 已按 line_no 排序
        for e in entry_rows:
            d = (e.debit_amount or Decimal(0))
            c = (e.credit_amount or Decimal(0))
            parts.append("|".join([
                e.standard_account_code or "",
                (e.account_name or "").strip(),
                (e.report_line_code or "").strip(),
                str(Decimal(str(d)).quantize(_q)),
                str(Decimal(str(c)).quantize(_q)),
            ]))
        raw = "\n".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    # ------------------------------------------------------------------
    # sync_from_workpaper
    # ------------------------------------------------------------------
    async def sync_from_workpaper(
        self,
        project_id: UUID,
        data: AdjustmentSyncRequest,
        user_id: UUID,
    ) -> AdjustmentGroupResponse:
        """底稿分录组 → 集中登记（幂等 by source_ref + 内容签名去重）。

        ADR-P3-008：
        - 相同内容 → 不写库、不换编号、原样返回
        - 不同内容 → 原地更新（保 entry_group_id 与 adjustment_no），
          pending_review/rejected 回 draft 并清复核信息；approved → APPROVED_LOCKED
        - 新建 → 正常建组
        """
        source_ref = self.build_source_ref(data.wp_id, data.item_id)

        # 1. 借贷平衡校验
        total_debit = sum((li.debit_amount or Decimal("0")) for li in data.line_items)
        total_credit = sum((li.credit_amount or Decimal("0")) for li in data.line_items)
        if total_debit != total_credit:
            raise AdjustmentSyncError(
                "UNBALANCED",
                f"借贷不平衡：借方合计 {total_debit}，贷方合计 {total_credit}，"
                f"差额 {total_debit - total_credit}",
            )

        # 2. 科目解析（code 优先，account_name fallback），收集 unresolved
        resolved, unresolved = await self._resolve_account_codes(project_id, data.line_items)
        if unresolved:
            raise AdjustmentSyncError(
                "UNRESOLVED_ACCOUNTS",
                "以下明细行无法解析标准科目，请补全科目编码：" + "、".join(unresolved),
                detail={"unresolved": unresolved},
            )

        # 3. 计算请求的内容签名
        new_sig = self._compute_content_signature(
            data.adjustment_type, data.description, resolved, data.line_items,
        )

        # 4. 幂等：查 source_ref 活跃分录组
        existing_rows = await self._get_active_rows_by_source_ref(project_id, source_ref)
        if existing_rows:
            status = existing_rows[0].review_status
            group_id = existing_rows[0].entry_group_id
            adj_no = existing_rows[0].adjustment_no

            # approved → 拒绝
            if status == ReviewStatus.approved:
                raise AdjustmentSyncError(
                    "APPROVED_LOCKED",
                    "该底稿调整已在集中登记复核通过，需先撤回复核方可重新同步。",
                    detail={"entry_group_id": str(group_id)},
                )

            # 协作锁（adjustment-collaboration-and-propagation）
            from app.services.adjustment_collaboration_service import (
                has_active_collaboration,
            )
            if await has_active_collaboration(self.db, project_id, group_id):
                raise AdjustmentSyncError(
                    "COLLABORATION_LOCKED",
                    "该分录组存在进行中的协作补充，需待协作确认/退回后方可重新同步。",
                    detail={"entry_group_id": str(group_id)},
                )

            # 比较内容签名 —— 相同则不写库、不换编号
            old_entries = await self._adj._get_entry_rows(group_id)
            old_sig = self._compute_existing_signature(existing_rows, old_entries)
            if new_sig == old_sig:
                return self._adj._build_group_response(
                    group_id, adj_no, existing_rows[0].adjustment_type,
                    existing_rows[0].description, status,
                    existing_rows, old_entries,
                    existing_rows[0].created_by,
                )

            # 内容变化 → 原地更新（保组号与编号，软删旧行写新行）
            # pending_review / rejected 回 draft 并清复核信息
            for row in existing_rows:
                row.soft_delete()
            for e in old_entries:
                e.soft_delete()
            await self.db.flush()

            # 写入新行（复用组号 + 编号）
            return await self._write_group_rows(
                project_id=project_id,
                data=data,
                resolved=resolved,
                source_ref=source_ref,
                user_id=user_id,
                entry_group_id=group_id,
                adjustment_no=adj_no,
            )

        # 5. 新建分录组
        adjustment_no = await self._adj._next_adjustment_no(
            project_id, data.year, data.adjustment_type
        )
        entry_group_id = uuid.uuid4()
        return await self._write_group_rows(
            project_id=project_id,
            data=data,
            resolved=resolved,
            source_ref=source_ref,
            user_id=user_id,
            entry_group_id=entry_group_id,
            adjustment_no=adjustment_no,
        )

    # ------------------------------------------------------------------
    # _write_group_rows（内部：写入一组 Adjustment + AdjustmentEntry 行）
    # ------------------------------------------------------------------
    async def _write_group_rows(
        self,
        *,
        project_id: UUID,
        data: AdjustmentSyncRequest,
        resolved: list[str],
        source_ref: str,
        user_id: UUID,
        entry_group_id: UUID,
        adjustment_no: str,
    ) -> AdjustmentGroupResponse:
        """写入新分录组行。抽取自 sync_from_workpaper 以消除新建/更新的代码重复。"""
        adj_rows: list[Adjustment] = []
        entry_rows: list[AdjustmentEntry] = []
        for idx, (li, code) in enumerate(zip(data.line_items, resolved), start=1):
            adj = Adjustment(
                project_id=project_id,
                year=data.year,
                company_code=data.company_code,
                adjustment_no=adjustment_no,
                adjustment_type=data.adjustment_type,
                description=data.description,
                account_code=code,
                account_name=li.account_name,
                debit_amount=li.debit_amount,
                credit_amount=li.credit_amount,
                entry_group_id=entry_group_id,
                review_status=ReviewStatus.draft,
                origin="workpaper",
                source_ref=source_ref,
                created_by=user_id,
            )
            self.db.add(adj)
            await self.db.flush()

            entry = AdjustmentEntry(
                adjustment_id=adj.id,
                entry_group_id=entry_group_id,
                line_no=idx,
                standard_account_code=code,
                account_name=li.account_name,
                report_line_code=li.report_line_code,
                debit_amount=li.debit_amount,
                credit_amount=li.credit_amount,
            )
            self.db.add(entry)
            adj_rows.append(adj)
            entry_rows.append(entry)

        await self.db.flush()

        return self._adj._build_group_response(
            entry_group_id, adjustment_no, data.adjustment_type,
            data.description, ReviewStatus.draft, adj_rows, entry_rows, user_id,
        )

    # ------------------------------------------------------------------
    # remove_by_source_ref
    # ------------------------------------------------------------------
    async def remove_by_source_ref(self, project_id: UUID, source_ref: str) -> int:
        """底稿删除该分录组时软删除对应集中条目。返回软删行数。"""
        rows = await self._get_active_rows_by_source_ref(project_id, source_ref)
        if not rows:
            return 0
        group_id = rows[0].entry_group_id
        for row in rows:
            row.soft_delete()
        for e in await self._adj._get_entry_rows(group_id):
            e.soft_delete()
        await self.db.flush()
        return len(rows)

    # ------------------------------------------------------------------
    # get_status_by_source_ref（回流）
    # ------------------------------------------------------------------
    async def get_status_by_source_ref(
        self, project_id: UUID, source_ref: str
    ) -> dict | None:
        """回流：返回集中条目的复核状态/驳回原因/编号，供底稿侧只读展示。"""
        rows = await self._get_active_rows_by_source_ref(project_id, source_ref)
        if not rows:
            return None
        head = rows[0]
        # 协作状态回流（P1-6）：供底稿侧显示"协作中/已确认"+ 重新同步前覆盖保护（P1-5）。
        # 懒导入避免循环依赖；查询失败不阻断状态回流。
        collaboration_status: str | None = None
        try:
            from app.services.adjustment_collaboration_service import (
                AdjustmentCollaborationService,
            )
            collab = await AdjustmentCollaborationService(self.db).get_latest_by_group(
                project_id, head.entry_group_id
            )
            if collab is not None:
                collaboration_status = collab.status
        except Exception:  # noqa: BLE001
            collaboration_status = None
        return {
            "entry_group_id": str(head.entry_group_id),
            "adjustment_no": head.adjustment_no,
            "adjustment_type": (
                head.adjustment_type.value
                if hasattr(head.adjustment_type, "value")
                else head.adjustment_type
            ),
            "review_status": (
                head.review_status.value
                if hasattr(head.review_status, "value")
                else head.review_status
            ),
            "rejection_reason": head.rejection_reason,
            "source_wp_code": source_ref.split(":", 1)[0] if source_ref else None,
            "collaboration_status": collaboration_status,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _get_active_rows_by_source_ref(
        self, project_id: UUID, source_ref: str
    ) -> list[Adjustment]:
        q = (
            sa.select(Adjustment)
            .where(
                Adjustment.project_id == project_id,
                Adjustment.source_ref == source_ref,
                Adjustment.is_deleted == sa.false(),
            )
            .order_by(Adjustment.created_at)
        )
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def _resolve_account_codes(
        self, project_id: UUID, line_items
    ) -> tuple[list[str], list[str]]:
        """解析每行标准科目编码。

        返回 (resolved_codes 与 line_items 顺序对齐, unresolved_labels)。
        - standard_account_code 提供且存在于标准科目表 → 直接用
        - 否则按 account_name 在标准科目表精确匹配（唯一）→ 填 code
        - 仍无法解析 → 计入 unresolved
        """
        ac = AccountChart.__table__

        # 预取所有已提供的候选 code 是否为标准科目
        provided_codes = {
            (li.standard_account_code or "").strip()
            for li in line_items
            if (li.standard_account_code or "").strip()
        }
        valid_codes: set[str] = set()
        if provided_codes:
            r = await self.db.execute(
                sa.select(ac.c.account_code).where(
                    ac.c.project_id == project_id,
                    ac.c.source == AccountSource.standard.value,
                    ac.c.is_deleted == sa.false(),
                    ac.c.account_code.in_(list(provided_codes)),
                )
            )
            valid_codes = {row.account_code for row in r.fetchall()}

        # 预取所有需按名称解析的 name → code（唯一匹配）
        names_to_resolve = {
            (li.account_name or "").strip()
            for li in line_items
            if not (li.standard_account_code or "").strip() and (li.account_name or "").strip()
        }
        name_map: dict[str, list[str]] = {}
        if names_to_resolve:
            r = await self.db.execute(
                sa.select(ac.c.account_name, ac.c.account_code).where(
                    ac.c.project_id == project_id,
                    ac.c.source == AccountSource.standard.value,
                    ac.c.is_deleted == sa.false(),
                    ac.c.account_name.in_(list(names_to_resolve)),
                )
            )
            for row in r.fetchall():
                name_map.setdefault(row.account_name, []).append(row.account_code)

        resolved: list[str] = []
        unresolved: list[str] = []
        for li in line_items:
            code = (li.standard_account_code or "").strip()
            name = (li.account_name or "").strip()
            if code and code in valid_codes:
                resolved.append(code)
                continue
            # name 唯一匹配
            candidates = name_map.get(name, [])
            if name and len(candidates) == 1:
                resolved.append(candidates[0])
                continue
            resolved.append("")  # 占位，保持与 line_items 对齐
            label = code or name or f"第{len(resolved)}行"
            unresolved.append(label)
        return resolved, unresolved
