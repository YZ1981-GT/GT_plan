"""序时账增量追加：在 staged 数据集内合并基准版本，不改 active 数据。"""
from __future__ import annotations

from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import ImportBatch, ImportStatus
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services._ledger_dataset_merge_copy import dialect_name as _dialect_name
from app.services._ledger_dataset_merge_tables import (
    PERIODIC_MODELS as _PERIODIC_MODELS,
    SNAPSHOT_MODELS as _SNAPSHOT_MODELS,
    ProgressCallback,
    _merge_account_chart,
    _merge_direction_overrides,
    _merge_periodic_table,
    _merge_snapshot_table,
)
from app.services._ledger_dataset_merge_types import (
    BalanceCarryConfirmationRequired,
    BaseDatasetChangedError,
    MergeReport,
    MergeRowCountError,
    TableMergeReport,
)

DATASET_BOUND_TABLES = MappingProxyType({
    "periodic": ("tb_ledger", "tb_aux_ledger"),
    "snapshot": ("tb_balance", "tb_aux_balance", "account_chart", "direction_override"),
    "not_import_product": (
        "_sign_migration_backup",
        "activation_records",
        "interim_survival_checks",
        "sampling_records",
        "workpaper_row_name_mapping_target",
    ),
})

async def assert_base_is_active(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    base_dataset_id: UUID,
    lock: bool = False,
) -> LedgerDataset:
    stmt = (
        sa.select(LedgerDataset)
        .where(
            LedgerDataset.project_id == project_id,
            LedgerDataset.year == year,
            LedgerDataset.status == DatasetStatus.active,
        )
        .order_by(LedgerDataset.activated_at.desc().nullslast(), LedgerDataset.created_at.desc())
    )
    if lock and _dialect_name(db) == "postgresql":
        stmt = stmt.with_for_update()
    active = (await db.execute(stmt)).scalars().first()
    if active is None or active.id != base_dataset_id:
        actual = str(active.id) if active is not None else "无"
        raise BaseDatasetChangedError(
            f"基准版本已变化，请重新追加（提交时 {base_dataset_id}，当前 {actual}）"
        )
    return active


async def merge_into_staged(
    db: AsyncSession,
    *,
    staged_id: UUID,
    base_id: UUID,
    project_id: UUID,
    year: int,
    strategy: str,
    balance_carry_confirmed: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> MergeReport:
    """把基准版本未被文件覆盖的数据复制进 staged；只 flush，不 commit。"""
    if strategy not in {"overwrite", "skip"}:
        raise ValueError(f"追加策略必须是 overwrite 或 skip，收到 {strategy!r}")
    staged = await db.get(LedgerDataset, staged_id)
    if staged is None or staged.status != DatasetStatus.staged:
        raise ValueError(f"目标数据集不是 staged：{staged_id}")
    if staged.project_id != project_id or staged.year != year:
        raise ValueError("staged 数据集与项目或年度不一致")
    await assert_base_is_active(
        db,
        project_id=project_id,
        year=year,
        base_dataset_id=base_id,
    )
    if staged.previous_dataset_id not in {None, base_id}:
        raise BaseDatasetChangedError(
            f"staged 数据集基准为 {staged.previous_dataset_id}，不是提交时冻结的 {base_id}"
        )

    inherited_batch = ImportBatch(
        project_id=project_id,
        year=year,
        source_type="append_inherit",
        file_name=f"base_{base_id}",
        data_type="__append_inherit__",
        status=ImportStatus.completed,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(inherited_batch)
    await db.flush()

    reports: dict[str, TableMergeReport] = {}
    id_maps: dict[str, dict[UUID, UUID]] = {}
    for model in _PERIODIC_MODELS:
        report = await _merge_periodic_table(
            db,
            model=model,
            strategy=strategy,
            base_dataset_id=base_id,
            staged_dataset_id=staged_id,
            inherited_batch_id=inherited_batch.id,
            id_maps=id_maps,
            year=year,
            progress_callback=progress_callback,
        )
        reports[model.__tablename__] = report
    for model in _SNAPSHOT_MODELS:
        report = await _merge_snapshot_table(
            db,
            model=model,
            project_id=project_id,
            base_dataset_id=base_id,
            staged_dataset_id=staged_id,
            inherited_batch_id=inherited_batch.id,
            id_maps=id_maps,
        )
        reports[model.__tablename__] = report
    reports["account_chart"] = await _merge_account_chart(
        db,
        project_id=project_id,
        base_dataset_id=base_id,
        staged_dataset_id=staged_id,
        inherited_batch_id=inherited_batch.id,
        id_maps=id_maps,
    )
    reports["direction_override"] = await _merge_direction_overrides(
        db,
        project_id=project_id,
        base_dataset_id=base_id,
        staged_dataset_id=staged_id,
        id_maps=id_maps,
    )

    ledger = reports["tb_ledger"]
    added_months = set(ledger.file_months) - set(ledger.base_months)
    balance_carried = any(reports[name].carried for name in ("tb_balance", "tb_aux_balance"))
    confirmation_required = bool(added_months and balance_carried)
    if confirmation_required and not balance_carry_confirmed:
        raise BalanceCarryConfirmationRequired(
            "余额表未随本次追加更新，试算表仍为上一版本口径；请确认后重新提交"
        )

    file_months = set().union(*(set(reports[name].file_months) for name in DATASET_BOUND_TABLES["periodic"]))
    inherited_months = set().union(
        *(set(reports[name].inherited_months) for name in DATASET_BOUND_TABLES["periodic"])
    )
    skipped_months = set().union(
        *(set(reports[name].skipped_months) for name in DATASET_BOUND_TABLES["periodic"])
    )
    overwritten_months = set().union(
        *(set(reports[name].overwritten_months) for name in DATASET_BOUND_TABLES["periodic"])
    )
    inherited_batch.record_count = sum(report.copied_rows for report in reports.values())

    report = MergeReport(
        strategy=strategy,
        base_dataset_id=base_id,
        staged_dataset_id=staged_id,
        file_months=tuple(sorted(file_months)),
        inherited_months=tuple(sorted(inherited_months)),
        skipped_months=tuple(sorted(skipped_months)),
        overwritten_months=tuple(sorted(overwritten_months)),
        tables=reports,
        inherited_batch_id=inherited_batch.id,
        balance_confirmation_required=confirmation_required,
        balance_carry_confirmed=balance_carry_confirmed,
    )
    staged.previous_dataset_id = base_id
    staged.source_type = "append"
    staged.source_summary = {
        **(staged.source_summary or {}),
        "append": report.to_dict(),
    }
    await db.flush()
    return report


async def freeze_append_options(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    strategy: str | None,
    balance_carry_confirmed: bool = False,
) -> dict[str, Any] | None:
    """提交时冻结 active 基准；没有基准时保留追加意图但按普通首导执行。"""
    if strategy is None:
        return None
    if strategy not in {"overwrite", "skip"}:
        raise ValueError(f"追加策略必须是 overwrite 或 skip，收到 {strategy!r}")
    active_id = (
        await db.execute(
            sa.select(LedgerDataset.id)
            .where(
                LedgerDataset.project_id == project_id,
                LedgerDataset.year == year,
                LedgerDataset.status == DatasetStatus.active,
            )
            .order_by(LedgerDataset.activated_at.desc().nullslast(), LedgerDataset.created_at.desc())
        )
    ).scalars().first()
    return {
        "strategy": strategy,
        "base_dataset_id": str(active_id) if active_id else None,
        "balance_carry_confirmed": bool(balance_carry_confirmed),
        "no_base": active_id is None,
    }


__all__ = [
    "BalanceCarryConfirmationRequired",
    "BaseDatasetChangedError",
    "DATASET_BOUND_TABLES",
    "MergeReport",
    "MergeRowCountError",
    "TableMergeReport",
    "assert_base_is_active",
    "freeze_append_options",
    "merge_into_staged",
]
