"""合伙人一键刷新编排器（Draft Refresh Service）.

公式管理库（formula-management-library）设计 Components §1。把当前
``wp_render_config.py`` 的 ``refresh_audit_sheet_from_ledger``（仅
``Depends(get_current_user)``，无角色限制）收敛为**合伙人专属**的一键刷新编排器，
补齐初稿（Draft）语义、幂等、四表库前置校验、审计留痕、覆盖团队编辑前确认与可回滚快照。

编排流程（门禁在 router 层用 ``require_role`` 施加）::

    precheck  →  preview_overwrites  →  refresh（snapshot + draft + audit）  →  rollback

工程铁律：service 只 ``flush`` 不 ``commit``（router 层 commit）；四表库取数经
``get_active_filter`` 统一入口，禁止裸写 ``is_deleted==False``。

本模块实现 **Task 5.1 precheck**（四表库完整度前置校验）、
**Task 5.2 preview_overwrites**（团队人工编辑覆盖清单）、
**Task 5.3 refresh**（幂等编排 + Draft 标记 + 审计留痕）与
**Task 5.4 rollback**（依据回滚快照恢复刷新前状态 + 审计标 ``rolled_back``）。
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    TbAuxBalance,
    TbBalance,
    TbLedger,
    TrialBalance,
)
from app.models.workpaper_models import (
    DraftMarker,
    DraftRefreshAudit,
    DraftRefreshSnapshot,
)
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)

# 四表库表名 → 中文标签（缺失清单展示用）
TABLE_LABELS: dict[str, str] = {
    "trial_balance": "试算表",
    "tb_balance": "科目余额表",
    "tb_ledger": "序时账",
    "tb_aux_balance": "辅助余额表",
}


@dataclass
class PrecheckItem:
    """一条前置校验结果项（缺失/告警），含表名 + 说明.

    Attributes:
        table: 四表库物理表名（如 ``tb_balance``）。
        label: 表的中文标签（如 ``科目余额表``）。
        message: 面向合伙人的中文说明（缺失原因 / 告警内容）。
    """

    table: str
    label: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"table": self.table, "label": self.label, "message": self.message}


@dataclass
class PrecheckResult:
    """一键刷新四表库完整度前置校验结果.

    - ``blocking`` 非空 → 阻断刷新，调用方不得执行任何数据写入（Req 2.2）。
    - ``warnings`` 为非阻断告警（如个别辅助维度缺失），允许合伙人确认后继续（Req 2.5）。
    """

    blocking: list[PrecheckItem] = field(default_factory=list)
    warnings: list[PrecheckItem] = field(default_factory=list)

    @property
    def can_refresh(self) -> bool:
        """blocking 为空即可继续刷新（Req 2.4）。"""
        return not self.blocking

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_refresh": self.can_refresh,
            "blocking": [i.to_dict() for i in self.blocking],
            "warnings": [i.to_dict() for i in self.warnings],
        }


@dataclass
class OverwriteItem:
    """一条将被一键刷新覆盖的人工编辑清单项（Req 4.3）。

    合伙人一键刷新时，若某数据单元已被人工编辑（``draft_marker.state='human_edited'``），
    刷新会覆盖它。本项供合伙人在确认覆盖前审阅：明确"哪张底稿、哪个单元、谁编辑的"
    将被覆盖，避免误删团队成果。

    Attributes:
        unit_scope: 数据单元定位（``draft_marker.unit_scope`` 原值，如
            ``audit_sheet:{wp_id}:{cell}`` / ``report:{row_code}``）。
        domain: 从 ``unit_scope`` 解析的域前缀（如 ``audit_sheet`` / ``report`` / ``note``）。
        workpaper: 从 ``unit_scope`` 解析的底稿标识（如 wp_id 段）；无法解析为 ``None``。
        cell: 从 ``unit_scope`` 解析的单元/行标识（如 cell 坐标或 row_code）；无则 ``None``。
        editor_id: 人工编辑者标识。``draft_marker`` 表未落编辑者列，预览阶段暂为 ``None``；
            实际覆盖时由 ``refresh`` 写入 ``draft_refresh_snapshot.editor_id``（Task 5.3）。
        marker_id: 对应 ``draft_marker`` 行主键，供刷新/回滚关联。
    """

    unit_scope: str
    domain: str
    workpaper: str | None
    cell: str | None
    editor_id: UUID | None
    marker_id: UUID

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_scope": self.unit_scope,
            "domain": self.domain,
            "workpaper": self.workpaper,
            "cell": self.cell,
            "editor_id": str(self.editor_id) if self.editor_id else None,
            "marker_id": str(self.marker_id),
        }


@dataclass
class RefreshUnit:
    """一个由一键刷新生成/覆盖的初稿单元（Task 5.3 输入）。

    上游生成器（报表引擎 / 审定表回写 / 附注执行器）产出每个初稿单元后交给编排器
    ``refresh`` 统一处理：幂等短路、覆盖排除、快照、打 Draft 标记、审计留痕。本编排层
    不重复生成逻辑（生成归各引擎任务 7/8/9），只负责围绕生成结果的治理动作。

    Attributes:
        unit_scope: 数据单元定位（与 ``draft_marker.unit_scope`` 同格式，如
            ``audit_sheet:{wp_id}:{cell}`` / ``report:{row_code}``）。
        before_value: 覆盖前内容（供回滚快照）。为 ``None`` 表示该单元为新建（无既有值
            可覆盖），不写回滚快照。
        after_value: 生成的初稿值（供留痕/统计，编排层不落库到具体数据表）。
        editor_id: 若该单元原为人工编辑（``human_edited``），其编辑者标识，写入回滚快照
            的 ``editor_id`` 以备追溯（Req 4.3）。
    """

    unit_scope: str
    before_value: dict | list | None = None
    after_value: dict | list | None = None
    editor_id: UUID | None = None


@dataclass
class RefreshResult:
    """一键刷新编排结果（Task 5.3 返回）。

    Attributes:
        tb_snapshot_hash: 本次四表库快照指纹（幂等键）。
        scope: 归一化后的刷新范围键（写入审计的 ``scope`` 列）。
        status: ``success`` | ``idempotent_hit`` | ``blocked``。
        refresh_id: 本次（或幂等命中的上次）审计记录主键；``blocked`` 时为 ``None``。
        idempotent: 是否为幂等短路命中（相同 hash + scope 的成功记录）。
        affected_count: 实际刷新（写入 Draft 标记）的单元数。
        refreshed_units: 实际刷新的单元 ``unit_scope`` 列表。
        skipped_human_edited: 未确认覆盖而被跳过的人工编辑单元 ``unit_scope`` 列表。
        snapshotted_units: 覆盖前写入回滚快照的单元 ``unit_scope`` 列表。
        blocking: 前置校验阻断项（``status='blocked'`` 时非空）。
        stale_marked_count: 生成初稿后经既有 ``prefill_stale`` 机制标为过时的底稿数
            （Req 25.5，复用 recalc/stale 通道触发受影响单元过时刷新，不自建）。
    """

    tb_snapshot_hash: str
    scope: str
    status: str
    refresh_id: UUID | None = None
    idempotent: bool = False
    affected_count: int = 0
    refreshed_units: list[str] = field(default_factory=list)
    skipped_human_edited: list[str] = field(default_factory=list)
    snapshotted_units: list[str] = field(default_factory=list)
    blocking: list[dict] = field(default_factory=list)
    stale_marked_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tb_snapshot_hash": self.tb_snapshot_hash,
            "scope": self.scope,
            "status": self.status,
            "refresh_id": str(self.refresh_id) if self.refresh_id else None,
            "idempotent": self.idempotent,
            "affected_count": self.affected_count,
            "refreshed_units": list(self.refreshed_units),
            "skipped_human_edited": list(self.skipped_human_edited),
            "snapshotted_units": list(self.snapshotted_units),
            "blocking": [dict(b) for b in self.blocking],
            "stale_marked_count": self.stale_marked_count,
        }


@dataclass
class PresetApplication:
    """按 page_key 套用预设库为初稿公式的结果（Task 14.2 / Req 22.4, 22.6）。

    一键刷新 / 底稿生成时，对每个目标页面（page_key）查预设库：**已预设（presetted）**
    页面把其预设公式转为初稿单元（``RefreshUnit``，``after_value`` 承载预设表达式/类型/
    引用，来源标 ``preset``）作为初稿公式的来源之一（Req 22.4）；**未预设（pending）**
    页面直接跳过，保留现状不生成任何单元（增量交付，无回归，Req 22.6）。

    Attributes:
        units: 由已预设页面套用生成的初稿单元集合，交 ``refresh`` 统一编排（打 Draft/审计）。
        presetted_pages: 命中预设并套用的页面 page_key 列表。
        pending_pages: 无预设、被跳过保留现状的页面 page_key 列表（无回归）。

    ``preset_count`` 为套用的预设公式条目总数（= ``len(units)``）。
    """

    units: list[RefreshUnit] = field(default_factory=list)
    presetted_pages: list[str] = field(default_factory=list)
    pending_pages: list[str] = field(default_factory=list)

    @property
    def preset_count(self) -> int:
        return len(self.units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_count": self.preset_count,
            "presetted_pages": list(self.presetted_pages),
            "pending_pages": list(self.pending_pages),
        }


@dataclass
class RestoredUnit:
    """回滚时恢复的一个单元的刷新前内容（Task 5.4 返回）。

    编排层不直接改写具体数据表（与 ``refresh`` 对称：生成归各引擎、编排层只治理
    marker/snapshot/audit）。回滚时把每个单元的刷新前内容（``before_value``）连同
    人工编辑者标识回给调用方（router / 上游引擎），由其把实际数据单元恢复到刷新前状态。

    Attributes:
        unit_scope: 数据单元定位（与 ``draft_marker.unit_scope`` 同格式）。
        before_value: 覆盖前内容（来自 ``draft_refresh_snapshot.before_value``），供调用方
            据以恢复实际数据单元。
        editor_id: 被覆盖的人工编辑者标识（``draft_refresh_snapshot.editor_id``，可能为
            ``None``）。
    """

    unit_scope: str
    before_value: dict | list
    editor_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_scope": self.unit_scope,
            "before_value": self.before_value,
            "editor_id": str(self.editor_id) if self.editor_id else None,
        }


@dataclass
class RollbackResult:
    """一键刷新回滚编排结果（Task 5.4 返回）。

    Attributes:
        refresh_id: 被回滚的刷新批次审计主键。
        status: ``rolled_back``（本次成功回滚）| ``not_found``（无此刷新记录）|
            ``already_rolled_back``（该刷新此前已回滚，本次幂等空操作）。
        restored_count: 依据回滚快照恢复内容的单元数（供调用方恢复实际数据表）。
        restored_units: 恢复刷新前内容的单元清单（``RestoredUnit``，含 before_value +
            editor_id），交调用方据以恢复实际数据。
        restored_markers: 由刷新覆盖既有内容、本次将 ``draft_marker`` 状态恢复到刷新前的
            单元 ``unit_scope`` 列表。
        removed_markers: 由刷新新建（刷新前不存在既有内容/标记）、本次删除以恢复刷新前
            "无标记"状态的单元 ``unit_scope`` 列表。
    """

    refresh_id: UUID
    status: str
    restored_count: int = 0
    restored_units: list[RestoredUnit] = field(default_factory=list)
    restored_markers: list[str] = field(default_factory=list)
    removed_markers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "refresh_id": str(self.refresh_id),
            "status": self.status,
            "restored_count": self.restored_count,
            "restored_units": [u.to_dict() for u in self.restored_units],
            "restored_markers": list(self.restored_markers),
            "removed_markers": list(self.removed_markers),
        }


def _parse_unit_scope(unit_scope: str) -> tuple[str, str | None, str | None]:
    """解析 ``unit_scope`` 为 (domain, workpaper, cell)。

    约定格式（见 DraftMarker.unit_scope 注释）：
    - ``audit_sheet:{wp_id}:{cell}`` / ``workpaper:{wp_id}:{cell}`` → 底稿 + 单元格
    - ``report:{row_code}`` / ``note:{...}`` → 域 + 行/section 标识（无独立底稿段）

    Returns:
        (domain, workpaper, cell)：无法解析的段返回 ``None``。
    """
    parts = unit_scope.split(":")
    domain = parts[0]
    if domain in ("audit_sheet", "workpaper") and len(parts) >= 3:
        return domain, parts[1], ":".join(parts[2:])
    if len(parts) >= 2:
        return domain, None, ":".join(parts[1:])
    return domain, None, None


class DraftRefreshService:
    """合伙人专属一键刷新编排器。

    门禁在 router 层用 ``require_role(["partner", "signing_partner"])`` 施加，
    本 service 负责 precheck → diff → snapshot → generate → audit → recalc/stale 的编排。
    service 只 ``flush``，router ``commit``。

    **一键刷新（本编排器）与普通 recalc 的语义区分（Req 25.6）**：

    - **普通 recalc**（``POST /api/.../trial-balance/recalc``，团队成员可触发）：仅重算
      既有公式 / 试算表未审→调整→审定链，**不生成初稿、不打 Draft 标记**，无角色门禁
      （仅需项目编辑权）。
    - **一键刷新**（本编排器，合伙人专属，Req 1 角色门禁）：从四表库未审数**生成初稿**、
      为受影响单元**打 Draft 标记**（``draft_marker.state='draft'``）、写审计留痕，并在生成
      初稿后经 :meth:`trigger_recalc` **复用既有 ``prefill_stale`` + ``/trial-balance/recalc``
      机制**触发受影响单元的过时刷新（Req 25.5），使初稿与四表库未审数保持一致——不自建
      并行的过时追踪。
    """

    async def precheck(
        self,
        db: AsyncSession,
        *,
        project_id: UUID,
        year: int,
    ) -> PrecheckResult:
        """四表库数据完整度前置校验（Req 2.1~2.5）。

        复用 ``report_trace.py`` /
        ``consol_completeness_service.check_subsidiary_completeness`` 的数据完整度前置
        校验口径：以 ``get_active_filter`` 统一入口按 (project_id, year) 计数，非阻断项
        进 ``warnings``（不阻断刷新），必需数据缺失进 ``blocking``（阻断刷新）。

        校验口径：
        - **blocking（必需，缺失即阻断）**：
            * ``tb_balance``（科目余额表）—— 生成未审报表/审定表初稿的核心余额源。
            * ``trial_balance``（试算表）—— 报表/审定表取数的标准化叶子源。
        - **warnings（非阻断告警，允许继续）**：
            * ``tb_ledger``（序时账）缺失 —— 损益类科目发生额取数受影响。
            * ``tb_aux_balance``（辅助余额表）缺失 —— 个别辅助维度取数受影响（Req 2.5）。
            * ``trial_balance`` 有行但未审数（unadjusted_amount）全为空/0 —— 初稿可能为空。

        Args:
            db: 数据库会话（只读，本方法不写入）。
            project_id: 目标项目。
            year: 目标年度。

        Returns:
            PrecheckResult：``blocking`` 非空时调用方不得执行任何写入（Req 2.2）。
        """
        result = PrecheckResult()

        tb_balance_count = await self._count_rows(db, TbBalance, project_id, year)
        trial_balance_count = await self._count_rows(db, TrialBalance, project_id, year)
        tb_ledger_count = await self._count_rows(db, TbLedger, project_id, year)
        tb_aux_count = await self._count_rows(db, TbAuxBalance, project_id, year)

        # ── blocking：核心余额源缺失 → 阻断 ──
        if tb_balance_count == 0:
            result.blocking.append(
                PrecheckItem(
                    table="tb_balance",
                    label=TABLE_LABELS["tb_balance"],
                    message="科目余额表无该项目/年度数据，无法据以生成初稿",
                )
            )
        if trial_balance_count == 0:
            result.blocking.append(
                PrecheckItem(
                    table="trial_balance",
                    label=TABLE_LABELS["trial_balance"],
                    message="试算表无该项目/年度数据，报表/审定表取数缺失叶子源",
                )
            )

        # ── warnings：次级来源缺失，非阻断 ──
        if tb_ledger_count == 0:
            result.warnings.append(
                PrecheckItem(
                    table="tb_ledger",
                    label=TABLE_LABELS["tb_ledger"],
                    message="序时账无该项目/年度数据，损益类科目发生额取数将不可用",
                )
            )
        if tb_aux_count == 0:
            result.warnings.append(
                PrecheckItem(
                    table="tb_aux_balance",
                    label=TABLE_LABELS["tb_aux_balance"],
                    message="辅助余额表无该项目/年度数据，个别辅助维度取数将不可用",
                )
            )

        # ── warning：试算表有行但未审数为空/全 0（初稿可能为空）──
        if trial_balance_count > 0:
            has_unadjusted = await self._has_nonzero_unadjusted(db, project_id, year)
            if not has_unadjusted:
                result.warnings.append(
                    PrecheckItem(
                        table="trial_balance",
                        label=TABLE_LABELS["trial_balance"],
                        message="试算表未审数（unadjusted_amount）全部为空或 0，初稿可能为空",
                    )
                )

        return result

    # ── 内部计数辅助（统一经 get_active_filter，禁止裸写 is_deleted==False）──

    @staticmethod
    async def _count_rows(
        db: AsyncSession,
        model: type,
        project_id: UUID,
        year: int,
    ) -> int:
        """统计某四表库表在 (project_id, year) 下的有效行数（经 get_active_filter）。"""
        active_filter = await get_active_filter(db, model.__table__, project_id, year)
        stmt = sa.select(sa.func.count()).select_from(model).where(active_filter)
        return int((await db.execute(stmt)).scalar() or 0)

    @staticmethod
    async def _has_nonzero_unadjusted(
        db: AsyncSession,
        project_id: UUID,
        year: int,
    ) -> bool:
        """试算表当年是否存在非空且非 0 的未审数（unadjusted_amount）。"""
        active_filter = await get_active_filter(
            db, TrialBalance.__table__, project_id, year
        )
        stmt = (
            sa.select(sa.func.count())
            .select_from(TrialBalance)
            .where(
                active_filter,
                TrialBalance.unadjusted_amount.isnot(None),
                TrialBalance.unadjusted_amount != 0,
            )
        )
        return int((await db.execute(stmt)).scalar() or 0) > 0

    # ── 以下方法在 Task 5.2~5.4 实现，此处预留骨架 ────────────────────

    async def preview_overwrites(
        self,
        db: AsyncSession,
        *,
        project_id: UUID,
        year: int,
        scope: str | Sequence[str] | None = None,
    ) -> list[OverwriteItem]:
        """返回将被一键刷新覆盖的人工编辑清单，供合伙人确认（Req 4.3）。

        人工编辑标记的**唯一权威来源**是 ``draft_marker`` 表：一个数据单元被人工修改后，
        其 ``state`` 置为 ``'human_edited'``（Req 3.4）。一键刷新（未 ``confirm_overwrite``）
        默认只刷新非人工编辑单元（Req 4.4）；本方法把落在刷新范围内的 ``human_edited``
        单元列出，供合伙人在覆盖前审阅"底稿/单元/编辑者"。

        Args:
            db: 数据库会话（只读，本方法不写入）。
            project_id: 目标项目。
            year: 目标年度。
            scope: 刷新范围过滤。语义为对 ``unit_scope`` 的**前缀匹配**：
                - ``None`` → 返回该 (project_id, year) 下全部 ``human_edited`` 单元；
                - ``str`` → 仅返回 ``unit_scope`` 以该前缀开头的单元
                  （如 ``"report"`` 命中 ``report:BS-1``，``"audit_sheet"`` 命中
                  ``audit_sheet:{wp_id}:{cell}``，``"audit_sheet:{wp_id}"`` 命中某底稿）；
                - ``Sequence[str]`` → 命中任一前缀即返回（多勾选范围，配合 Req 19）。
                空字符串前缀视为不过滤该项。

        Returns:
            按 ``unit_scope`` 升序排列的 ``OverwriteItem`` 列表；无被覆盖项时返回空列表。
        """
        active_filter = DraftMarker.state == "human_edited"
        stmt = (
            sa.select(DraftMarker)
            .where(
                DraftMarker.project_id == project_id,
                DraftMarker.year == year,
                active_filter,
            )
            .order_by(DraftMarker.unit_scope.asc())
        )
        markers = (await db.execute(stmt)).scalars().all()

        prefixes = self._normalize_scope(scope)

        items: list[OverwriteItem] = []
        for marker in markers:
            if prefixes is not None and not any(
                marker.unit_scope.startswith(p) for p in prefixes
            ):
                continue
            domain, workpaper, cell = _parse_unit_scope(marker.unit_scope)
            items.append(
                OverwriteItem(
                    unit_scope=marker.unit_scope,
                    domain=domain,
                    workpaper=workpaper,
                    cell=cell,
                    editor_id=None,  # draft_marker 未落编辑者列；覆盖时由 refresh 记入快照
                    marker_id=marker.id,
                )
            )
        return items

    @staticmethod
    def _normalize_scope(
        scope: str | Sequence[str] | None,
    ) -> list[str] | None:
        """把 scope 参数归一化为前缀列表；``None`` 表示不过滤（返回全部）。

        空字符串或全空的可迭代项被剔除（视为不过滤）。
        """
        if scope is None:
            return None
        if isinstance(scope, str):
            return [scope] if scope else None
        prefixes = [str(s) for s in scope if s]
        return prefixes or None

    # ── 预设套用（Task 14.2 / Req 22.4, 22.6） ──────────────────────

    def build_preset_draft_units(
        self,
        page_keys: Sequence[str],
        *,
        preset_index: dict[str, list] | None = None,
    ) -> PresetApplication:
        """按 page_key 查预设库，把已预设页面的预设公式套用为初稿单元（Req 22.4）。

        复用 Task 14.1 的 ``preset_library``（``build_preset_index`` / ``find_presets_for_page``）：

        - **已预设页面（presetted）**：为其每条预设公式生成一个初稿 ``RefreshUnit``，
          ``unit_scope`` = ``{page_key}:{target_cell}``，``after_value`` 承载预设表达式 /
          三类型（``formula_type``）/ 引用（``refs``，ACNR addr_id/formula_ref）/ 来源
          （``source='preset'``）——作为初稿公式的来源之一（Req 22.4）。
        - **未预设页面（pending）**：不生成任何单元，直接跳过保留现状（增量交付，无回归，
          Req 22.6），仅计入 ``pending_pages`` 供进度可见。

        本方法为纯映射（不触库、不 flush）：产出的 ``units`` 交 :meth:`refresh` 统一编排
        （幂等 / 覆盖排除 / 快照 / 打 Draft / 审计）。预设库读取失败时对该页容错跳过（无回归）。

        Args:
            page_keys: 目标页面标识列表（``workpaper:{wp_code}`` / ``report:{...}`` /
                ``note:{...}``）。重复 page_key 只处理一次。
            preset_index: 预先构建的 page_key→预设条目索引（批量套用时传入以复用）；
                缺省则按需构建一次。

        Returns:
            PresetApplication：``units`` + presetted/pending 页面清单。
        """
        from app.services.formula_management.preset_library import (
            build_preset_index,
            find_presets_for_page,
        )

        if preset_index is None:
            try:
                preset_index = build_preset_index()
            except Exception as exc:  # noqa: BLE001 — 预设库不可用不阻断刷新（无回归）
                logger.warning(
                    "预设库构建失败，按页跳过预设套用（保留现状，Req 22.6）: %s: %s",
                    type(exc).__name__,
                    exc,
                )
                preset_index = {}

        application = PresetApplication()
        for page_key in dict.fromkeys(page_keys):  # 去重且保序
            presets = find_presets_for_page(page_key, index=preset_index)
            if not presets:
                # 未预设页面 → 跳过保留现状（无回归，Req 22.6）
                application.pending_pages.append(page_key)
                continue
            application.presetted_pages.append(page_key)
            for preset in presets:
                application.units.append(
                    RefreshUnit(
                        unit_scope=f"{page_key}:{preset.target_cell}",
                        before_value=None,
                        after_value={
                            "source": "preset",
                            "page_key": page_key,
                            "target_cell": preset.target_cell,
                            "expression": preset.expression,
                            "formula_type": preset.formula_type,
                            "refs": preset.refs,
                        },
                    )
                )
        return application

    async def refresh_with_presets(
        self,
        db: AsyncSession,
        *,
        project_id: UUID,
        year: int,
        operator: Any,
        scope: str | Sequence[str],
        page_keys: Sequence[str],
        extra_units: Sequence[RefreshUnit] = (),
        confirm_overwrite: bool = False,
        preset_index: dict[str, list] | None = None,
    ) -> tuple[RefreshResult, PresetApplication]:
        """一键刷新 / 底稿生成时按 page_key 套用预设库为初稿公式后编排刷新（Req 22.4, 22.6）。

        把 :meth:`build_preset_draft_units` 产出的预设初稿单元与上游引擎产出的 ``extra_units``
        （报表 / 审定表 / 附注生成结果）合并后交 :meth:`refresh` 统一编排。未预设页面（pending）
        不产生单元、保留现状（无回归）。刷新审计明细追加本次预设套用统计（presetted/pending）。

        Args:
            db: 数据库会话（service 只 flush，router commit）。
            project_id / year / operator / scope / confirm_overwrite: 同 :meth:`refresh`。
            page_keys: 需按预设库套用的目标页面。
            extra_units: 上游引擎产出的非预设初稿单元（与预设单元合并编排）。
            preset_index: 可选预设索引复用（见 :meth:`build_preset_draft_units`）。

        Returns:
            (RefreshResult, PresetApplication)：刷新结果 + 预设套用明细。
        """
        application = self.build_preset_draft_units(page_keys, preset_index=preset_index)
        all_units: list[RefreshUnit] = [*application.units, *extra_units]

        result = await self.refresh(
            db,
            project_id=project_id,
            year=year,
            operator=operator,
            scope=scope,
            units=all_units,
            confirm_overwrite=confirm_overwrite,
        )

        # 在刷新审计明细追加预设套用统计（presetted/pending 页面），进度可见（Req 22.6）。
        # 幂等命中 / 阻断分支无本次审计行可补，跳过（不影响幂等语义）。
        if result.status == "success" and result.refresh_id is not None:
            audit = (
                await db.execute(
                    sa.select(DraftRefreshAudit).where(
                        DraftRefreshAudit.id == result.refresh_id
                    )
                )
            ).scalar_one_or_none()
            if audit is not None:
                # JSONB 需赋新对象触发脏标记（就地改 dict 不一定被 ORM 追踪）。
                audit.detail = {**(audit.detail or {}), "preset_application": application.to_dict()}
                await db.flush()

        return result, application

    async def refresh(
        self,
        db: AsyncSession,
        *,
        project_id: UUID,
        year: int,
        operator: Any,
        scope: str | Sequence[str],
        units: Sequence[RefreshUnit] = (),
        confirm_overwrite: bool = False,
    ) -> RefreshResult:
        """幂等编排：precheck → 幂等短路 → diff/snapshot → 打 Draft → 审计留痕（Req 3/4）。

        编排步骤（对应 Task 5.3 ①~⑤）：

        1. **① 计算 tb_snapshot_hash**（四表库快照指纹）；先跑 precheck，blocking 非空则
           返回 ``status='blocked'`` 且**不执行任何数据写入**（Req 2.2 防御性二次校验）。
        2. **幂等短路**：命中相同 ``tb_snapshot_hash`` + ``scope`` 的成功审计记录时，直接
           返回上次结果标识（``status='idempotent_hit'``，Req 3.1），不重复写入。
        3. **② 覆盖排除**：未 ``confirm_overwrite`` 时复用 ``preview_overwrites`` 取出范围内
           ``human_edited`` 单元，从待刷新集合中排除，仅刷新非人工编辑单元（Req 4.4）。
        4. **③ 覆盖前快照**：对将覆盖既有内容的单元（存在 draft_marker 或带 before_value）
           写 ``draft_refresh_snapshot`` 回滚快照（Req 4.2），人工编辑者写入 ``editor_id``。
        5. **④ 打 Draft 标记**：为刷新单元 upsert ``draft_marker`` ``state='draft'``（Req 3.2），
           关联本次 ``refresh_id``。
        6. **⑤ 审计留痕**：写不可篡改 ``draft_refresh_audit``（操作者/时间/project_id/year/
           scope/受影响数，Req 4.1/4.6）。

        工程铁律：service 只 ``flush`` 不 ``commit``（router 层 commit）。

        Args:
            db: 数据库会话。
            project_id: 目标项目。
            year: 目标年度。
            operator: 触发刷新的合伙人（``User``，取 ``id`` / ``role``）。
            scope: 刷新范围（单值或多值，归一化为审计 scope 键）。
            units: 上游生成器产出的初稿单元集合（生成归各引擎任务，此处仅编排）。
            confirm_overwrite: 是否确认覆盖人工编辑单元；``False`` 时仅刷新非人工编辑单元。

        Returns:
            RefreshResult：含幂等标识、受影响数、跳过/快照单元清单。
        """
        scope_key = self._scope_key(scope)
        snapshot_hash = await self._compute_tb_snapshot_hash(db, project_id, year)

        # ── ① 前置校验（防御性二次校验；blocking → 不写任何数据）──
        precheck = await self.precheck(db, project_id=project_id, year=year)
        if not precheck.can_refresh:
            return RefreshResult(
                tb_snapshot_hash=snapshot_hash,
                scope=scope_key,
                status="blocked",
                blocking=[i.to_dict() for i in precheck.blocking],
            )

        # ── 幂等短路：相同 hash + scope 的成功记录 → 返回上次结果标识（Req 3.1）──
        prior = await self._find_idempotent_hit(
            db, project_id=project_id, year=year,
            scope_key=scope_key, snapshot_hash=snapshot_hash,
        )
        if prior is not None:
            return RefreshResult(
                tb_snapshot_hash=snapshot_hash,
                scope=scope_key,
                status="idempotent_hit",
                refresh_id=prior.id,
                idempotent=True,
                affected_count=prior.affected_count,
            )

        # ── ② 覆盖排除：未确认覆盖 → 排除范围内 human_edited 单元（Req 4.4）──
        human_edited: set[str] = set()
        if not confirm_overwrite:
            overwrites = await self.preview_overwrites(
                db, project_id=project_id, year=year, scope=scope,
            )
            human_edited = {o.unit_scope for o in overwrites}

        # ── 审计记录先行插入（append-only）：作为快照/标记的 refresh_id 归属 ──
        operator_id, operator_role = self._operator_fields(operator)
        audit = DraftRefreshAudit(
            project_id=project_id,
            year=year,
            operator_id=operator_id,
            operator_role=operator_role,
            operated_at=datetime.now(timezone.utc),
            scope=scope_key,
            tb_snapshot_hash=snapshot_hash,
            affected_count=0,
            result_status="success",
            detail={},
        )
        db.add(audit)
        await db.flush()  # 取得 audit.id，供 snapshot/marker 外键关联

        refreshed: list[str] = []
        skipped: list[str] = []
        snapshotted: list[str] = []

        # 预取范围内既有 draft_marker，减少逐单元查询
        existing_markers = await self._load_markers(
            db, project_id=project_id, year=year,
            unit_scopes=[u.unit_scope for u in units],
        )

        for unit in units:
            # 未确认覆盖时跳过人工编辑单元（保留其值不变，Req 4.4）
            if not confirm_overwrite and unit.unit_scope in human_edited:
                skipped.append(unit.unit_scope)
                continue

            marker = existing_markers.get(unit.unit_scope)

            # ── ③ 覆盖前写回滚快照（存在既有单元或带 before_value 即视为覆盖）──
            is_overwrite = marker is not None or unit.before_value is not None
            if is_overwrite:
                # 人工编辑者标识由上游按 unit.editor_id 提供（draft_marker 未落编辑者列）；
                # 覆盖人工编辑单元时写入快照以备追溯（Req 4.3）。
                db.add(
                    DraftRefreshSnapshot(
                        refresh_id=audit.id,
                        unit_scope=unit.unit_scope,
                        before_value=self._snapshot_before_value(unit, marker),
                        editor_id=unit.editor_id,
                    )
                )
                snapshotted.append(unit.unit_scope)

            # ── ④ 生成初稿 → 打 Draft 标记（Req 3.2）──
            now = datetime.now(timezone.utc)
            if marker is None:
                db.add(
                    DraftMarker(
                        project_id=project_id,
                        year=year,
                        unit_scope=unit.unit_scope,
                        state="draft",
                        refresh_id=audit.id,
                    )
                )
            else:
                marker.state = "draft"
                marker.refresh_id = audit.id
                marker.updated_at = now
            refreshed.append(unit.unit_scope)

        # ── ⑥ 生成初稿后触发受影响单元过时刷新（Req 25.5）──
        # 复用既有 prefill_stale + /trial-balance/recalc 机制（不自建）：把受影响底稿标
        # prefill_stale=True，使下游经既有 recalc/stale 通道反映"初稿已由四表库未审数重生成、
        # 需重算对齐"。仅在实际生成初稿（refreshed 非空）时触发。
        stale_marked = 0
        if refreshed:
            stale_marked = await self.trigger_recalc(db, project_id=project_id)

        # ── ⑤ 回填审计受影响数 + 明细（append-only，仅补本行统计字段）──
        audit.affected_count = len(refreshed)
        audit.detail = {
            "refreshed_units": refreshed,
            "skipped_human_edited": skipped,
            "snapshotted_units": snapshotted,
            "confirm_overwrite": confirm_overwrite,
            "stale_marked_count": stale_marked,
        }
        await db.flush()

        return RefreshResult(
            tb_snapshot_hash=snapshot_hash,
            scope=scope_key,
            status="success",
            refresh_id=audit.id,
            idempotent=False,
            affected_count=len(refreshed),
            refreshed_units=refreshed,
            skipped_human_edited=skipped,
            snapshotted_units=snapshotted,
            stale_marked_count=stale_marked,
        )

    async def trigger_recalc(
        self,
        db: AsyncSession,
        *,
        project_id: UUID,
        account_codes: Sequence[str] | None = None,
    ) -> int:
        """一键刷新生成初稿后，触发受影响单元的过时刷新（Req 25.5）。

        **复用既有过时/重算机制，不自建并行追踪**：直接调用 ``prefill_engine.mark_stale``
        （数据导入 / 调整分录变更等既有事件链使用的同一 helper）把受影响底稿标
        ``prefill_stale=True``。前端既有 ``useStaleStatus.recalc`` + ``/trial-balance/recalc``
        通道据此反映过时状态并可由团队成员触发重算，使初稿与四表库未审数对齐。

        **与普通 recalc 的语义区分（Req 25.6）**：本方法仅由合伙人专属一键刷新在生成初稿
        （打 Draft 标记）后调用，触发的是"过时刷新"信号；普通 recalc（团队可触发的
        ``/trial-balance/recalc``）仅重算既有公式、既不生成初稿也不打 Draft 标记。两者共用
        同一 ``prefill_stale`` / recalc 底层机制，避免并行实现。

        工程铁律：``mark_stale`` 仅执行 UPDATE 不 ``commit``；本方法只 ``flush``，
        由 router 层统一 ``commit``。

        Args:
            db: 数据库会话。
            project_id: 目标项目（``prefill_stale`` 按项目粒度标记，与既有
                ``_mark_workpapers_stale_all`` 数据源变更语义一致）。
            account_codes: 可选，按科目缩小过时范围（复用 ``mark_stale`` 的
                ``account_codes`` 过滤）；``None`` 时按项目全量标记。

        Returns:
            被标为过时（``prefill_stale=True``）的底稿行数；触发失败时返回 0（fail-open）。
        """
        from app.services.prefill_engine import mark_stale

        codes = list(account_codes) if account_codes else None
        # 过时刷新是一键刷新后的**次要下游信号**，不应因其失败而回滚合伙人已生成的初稿。
        # 用 SAVEPOINT 隔离：mark_stale 失败仅回滚该嵌套事务，外层刷新事务保持可用
        # （fail-open，与 event_handlers 对 mark_stale 失败记 degraded 不阻断的语义一致）。
        try:
            async with db.begin_nested():
                count = await mark_stale(db, project_id, codes)
            return count
        except Exception as exc:  # noqa: BLE001 — 过时刷新失败不阻断一键刷新
            logger.warning(
                "一键刷新生成初稿后触发过时刷新失败（不阻断刷新，Req 25.5）: %s: %s",
                type(exc).__name__,
                exc,
            )
            return 0

    async def mark_human_edited(
        self,
        db: AsyncSession,
        *,
        project_id: UUID,
        year: int,
        unit_scope: str,
    ) -> DraftMarker:
        """将某数据单元的 Draft 标记更新为 ``human_edited``（Req 3.4）。

        初稿单元被人工修改时调用：若已有 ``draft_marker`` 则置 ``state='human_edited'``；
        若不存在（人工新建非初稿单元）则创建一条 ``human_edited`` 标记，使前端可据 ``state``
        区分"初稿"与"已人工介入"（Req 3.5），并使后续一键刷新在未确认覆盖时避开它（Req 4.4）。

        service 只 flush，router commit。
        """
        marker = (
            await db.execute(
                sa.select(DraftMarker).where(
                    DraftMarker.project_id == project_id,
                    DraftMarker.year == year,
                    DraftMarker.unit_scope == unit_scope,
                )
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if marker is None:
            marker = DraftMarker(
                project_id=project_id,
                year=year,
                unit_scope=unit_scope,
                state="human_edited",
            )
            db.add(marker)
        else:
            marker.state = "human_edited"
            marker.updated_at = now
        await db.flush()
        return marker

    # ── refresh 内部辅助 ────────────────────────────────────────────

    @staticmethod
    def _scope_key(scope: str | Sequence[str]) -> str:
        """把 scope 归一化为稳定的审计键：排序去重后以 ``,`` 连接。

        使 ``["note", "report"]`` 与 ``["report", "note"]`` 得到同一键，保证幂等匹配一致。
        """
        if isinstance(scope, str):
            return scope
        parts = sorted({str(s) for s in scope if str(s)})
        return ",".join(parts)

    @staticmethod
    def _operator_fields(operator: Any) -> tuple[UUID, str]:
        """从 operator（User）取 (operator_id, operator_role)。role 兼容枚举/字符串。"""
        operator_id = operator.id
        role = getattr(operator, "role", None)
        role_str = getattr(role, "value", None) or str(role)
        return operator_id, role_str

    async def _find_idempotent_hit(
        self,
        db: AsyncSession,
        *,
        project_id: UUID,
        year: int,
        scope_key: str,
        snapshot_hash: str,
    ) -> DraftRefreshAudit | None:
        """查找相同 (project_id, year, scope, tb_snapshot_hash) 的最近一次成功刷新。"""
        stmt = (
            sa.select(DraftRefreshAudit)
            .where(
                DraftRefreshAudit.project_id == project_id,
                DraftRefreshAudit.year == year,
                DraftRefreshAudit.scope == scope_key,
                DraftRefreshAudit.tb_snapshot_hash == snapshot_hash,
                DraftRefreshAudit.result_status == "success",
            )
            .order_by(DraftRefreshAudit.operated_at.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalars().first()

    async def _load_markers(
        self,
        db: AsyncSession,
        *,
        project_id: UUID,
        year: int,
        unit_scopes: Sequence[str],
    ) -> dict[str, DraftMarker]:
        """按 unit_scope 批量预取范围内既有 draft_marker。"""
        if not unit_scopes:
            return {}
        stmt = sa.select(DraftMarker).where(
            DraftMarker.project_id == project_id,
            DraftMarker.year == year,
            DraftMarker.unit_scope.in_(list(set(unit_scopes))),
        )
        rows = (await db.execute(stmt)).scalars().all()
        return {m.unit_scope: m for m in rows}

    @staticmethod
    def _snapshot_before_value(
        unit: RefreshUnit,
        marker: DraftMarker | None,
    ) -> dict | list:
        """构造回滚快照的 before_value（覆盖前内容）。

        优先用上游提供的 ``before_value``；否则以既有 draft_marker 的状态元信息兜底
        （至少可回滚 Draft 标记状态）。始终返回可 JSON 序列化的结构。
        """
        if unit.before_value is not None:
            return unit.before_value
        if marker is not None:
            return {
                "marker_state": marker.state,
                "marker_refresh_id": str(marker.refresh_id) if marker.refresh_id else None,
            }
        return {}

    async def _compute_tb_snapshot_hash(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
    ) -> str:
        """计算四表库快照指纹（幂等键，Req 3.1）。

        = ``sha256`` of sorted 四表库 (project_id, year) 下所有有效行的
        ``(table, code, amount, direction, aux_type)`` 元组序列化文本。四表列不同，
        按各自语义映射到统一四元组：

        - ``trial_balance``：code=standard_account_code，amount=unadjusted_amount（初稿源），
          无 direction / aux_type。
        - ``tb_balance``：code=account_code，amount=closing_balance，direction=closing_direction。
        - ``tb_ledger``：code=account_code，amount=``debit:credit``，direction=entry_direction。
        - ``tb_aux_balance``：code=account_code，amount=closing_balance，
          direction=closing_direction，aux_type=aux_type。

        取数统一经 ``get_active_filter``（禁止裸写 ``is_deleted==False``），排序后哈希，
        保证相同数据 → 相同指纹（确定性），任一行变更 → 指纹改变。
        """
        rows: list[tuple[str, str, str, str, str]] = []

        # trial_balance
        tb_filter = await get_active_filter(
            db, TrialBalance.__table__, project_id, year
        )
        for code, amt in (
            await db.execute(
                sa.select(
                    TrialBalance.standard_account_code,
                    TrialBalance.unadjusted_amount,
                ).where(tb_filter)
            )
        ).all():
            rows.append(("TB", self._s(code), self._n(amt), "", ""))

        # tb_balance
        bal_filter = await get_active_filter(
            db, TbBalance.__table__, project_id, year
        )
        for code, amt, direction in (
            await db.execute(
                sa.select(
                    TbBalance.account_code,
                    TbBalance.closing_balance,
                    TbBalance.closing_direction,
                ).where(bal_filter)
            )
        ).all():
            rows.append(("BAL", self._s(code), self._n(amt), self._s(direction), ""))

        # tb_ledger（损益取发生额：借/贷分别纳入指纹）
        led_filter = await get_active_filter(
            db, TbLedger.__table__, project_id, year
        )
        for code, dr, cr, direction, vno, vseq in (
            await db.execute(
                sa.select(
                    TbLedger.account_code,
                    TbLedger.debit_amount,
                    TbLedger.credit_amount,
                    TbLedger.entry_direction,
                    TbLedger.voucher_no,
                    TbLedger.entry_seq,
                ).where(led_filter)
            )
        ).all():
            # 序时账多行同科目，纳入凭证号/序号避免聚合丢失明细
            code_key = f"{self._s(code)}#{self._s(vno)}#{self._s(vseq)}"
            amount = f"{self._n(dr)}:{self._n(cr)}"
            rows.append(("LED", code_key, amount, self._s(direction), ""))

        # tb_aux_balance（按 aux_type 分组维度纳入指纹）
        aux_filter = await get_active_filter(
            db, TbAuxBalance.__table__, project_id, year
        )
        for code, amt, direction, aux_type, aux_code in (
            await db.execute(
                sa.select(
                    TbAuxBalance.account_code,
                    TbAuxBalance.closing_balance,
                    TbAuxBalance.closing_direction,
                    TbAuxBalance.aux_type,
                    TbAuxBalance.aux_code,
                ).where(aux_filter)
            )
        ).all():
            code_key = f"{self._s(code)}#{self._s(aux_code)}"
            rows.append(
                ("AUX", code_key, self._n(amt), self._s(direction), self._s(aux_type))
            )

        rows.sort()
        serialized = "\n".join("|".join(r) for r in rows)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _s(value: Any) -> str:
        """None → 空串，其余 → str（确定性序列化）。"""
        return "" if value is None else str(value)

    @staticmethod
    def _n(value: Any) -> str:
        """数值确定性序列化：None → 空串；Decimal → 定点表示（消除 100.0 vs 100.00 差异）。"""
        if value is None:
            return ""
        if isinstance(value, Decimal):
            return format(value.normalize(), "f")
        return str(value)

    async def rollback(
        self,
        db: AsyncSession,
        *,
        refresh_id: UUID,
        operator: Any,
    ) -> RollbackResult:
        """依据某次刷新的回滚快照恢复刷新前数据状态（Req 4.5）。

        回滚编排步骤（与 ``refresh`` 对称）：

        1. **定位刷新批次**：按 ``refresh_id`` 取 ``draft_refresh_audit``；不存在 → 返回
           ``status='not_found'``（不写任何数据）。
        2. **幂等守卫**：若该刷新的 ``result_status`` 已是 ``'rolled_back'`` → 返回
           ``status='already_rolled_back'`` 的空操作结果，避免重复恢复（回滚可安全重放）。
        3. **恢复 marker 状态**：取本次刷新写入的回滚快照（``draft_refresh_snapshot``）与被本次
           刷新打标（``refresh_id == audit.id``）的 ``draft_marker``：
           - 有对应快照（刷新前有既有内容）→ 依快照恢复 marker 状态：
             * 快照 ``before_value`` 含 ``marker_state``（刷新前 marker 元信息）→ 精确还原
               ``state`` / ``refresh_id``；
             * 快照 ``before_value`` 为业务数据（``confirm_overwrite`` 覆盖人工编辑）→ 依快照
               ``editor_id`` 还原（有编辑者 → ``human_edited``，否则 ``draft``），``refresh_id``
               置空。
           - 无对应快照（刷新新建的全新单元，刷新前不存在）→ 删除该 marker，恢复"无标记"。
        4. **回给调用方恢复实际数据**：把每条快照的 ``before_value`` + ``editor_id`` 汇入
           ``restored_units``，交 router / 上游引擎据以把实际数据单元恢复到刷新前状态
           （编排层不直接改写具体数据表，与 ``refresh`` 对称）。
        5. **审计标记**：把该刷新审计记录 ``result_status`` 标为 ``'rolled_back'``，并在
           ``detail.rollback`` 追加本次回滚的操作者/时间/恢复数（保留原留痕，不删除历史）。
           标为 ``rolled_back`` 后，该记录不再参与 ``refresh`` 幂等短路（仅匹配
           ``result_status='success'``），使回滚后同快照再次刷新会真正重新执行。

        工程铁律：service 只 ``flush`` 不 ``commit``（router 层 commit）。

        Args:
            db: 数据库会话。
            refresh_id: 待回滚的刷新批次审计主键。
            operator: 触发回滚的合伙人（``User``，取 ``id`` / ``role``）。

        Returns:
            RollbackResult：含恢复的单元清单（供调用方恢复实际数据）与 marker 变更统计。
        """
        # ① 定位刷新批次
        audit = (
            await db.execute(
                sa.select(DraftRefreshAudit).where(DraftRefreshAudit.id == refresh_id)
            )
        ).scalar_one_or_none()
        if audit is None:
            return RollbackResult(refresh_id=refresh_id, status="not_found")

        # ② 幂等守卫：已回滚过 → 空操作
        if audit.result_status == "rolled_back":
            return RollbackResult(refresh_id=refresh_id, status="already_rolled_back")

        # ③ 取回滚快照（unit_scope → snapshot）
        snapshots = (
            await db.execute(
                sa.select(DraftRefreshSnapshot).where(
                    DraftRefreshSnapshot.refresh_id == refresh_id
                )
            )
        ).scalars().all()
        snap_by_unit = {s.unit_scope: s for s in snapshots}

        # 取被本次刷新打标的 draft_marker（refresh_id == audit.id）
        markers = (
            await db.execute(
                sa.select(DraftMarker).where(DraftMarker.refresh_id == refresh_id)
            )
        ).scalars().all()

        now = datetime.now(timezone.utc)
        restored_markers: list[str] = []
        removed_markers: list[str] = []

        for marker in markers:
            snap = snap_by_unit.get(marker.unit_scope)
            if snap is None:
                # 刷新新建的全新单元（刷新前无既有内容/标记）→ 删除，恢复"无标记"
                await db.delete(marker)
                removed_markers.append(marker.unit_scope)
                continue

            before = snap.before_value
            if isinstance(before, dict) and "marker_state" in before:
                # 刷新前 marker 元信息 → 精确还原
                marker.state = before["marker_state"]
                prior_refresh_id = before.get("marker_refresh_id")
                marker.refresh_id = (
                    UUID(prior_refresh_id) if prior_refresh_id else None
                )
            else:
                # 覆盖人工编辑单元（快照存业务数据）→ 依 editor_id 还原刷新前标记
                marker.state = "human_edited" if snap.editor_id is not None else "draft"
                marker.refresh_id = None
            marker.updated_at = now
            restored_markers.append(marker.unit_scope)

        # ④ 汇总恢复内容，交调用方恢复实际数据单元
        restored_units = [
            RestoredUnit(
                unit_scope=s.unit_scope,
                before_value=s.before_value,
                editor_id=s.editor_id,
            )
            for s in snapshots
        ]

        # ⑤ 审计标记 result_status='rolled_back' + 追加回滚留痕（保留原 detail）
        operator_id, operator_role = self._operator_fields(operator)
        audit.result_status = "rolled_back"
        # JSONB 需赋新对象触发脏标记（就地改 dict 不一定被 ORM 追踪）
        audit.detail = {
            **(audit.detail or {}),
            "rollback": {
                "operator_id": str(operator_id),
                "operator_role": operator_role,
                "rolled_back_at": now.isoformat(),
                "restored_count": len(restored_units),
                "restored_markers": restored_markers,
                "removed_markers": removed_markers,
            },
        }
        await db.flush()

        return RollbackResult(
            refresh_id=refresh_id,
            status="rolled_back",
            restored_count=len(restored_units),
            restored_units=restored_units,
            restored_markers=restored_markers,
            removed_markers=removed_markers,
        )
