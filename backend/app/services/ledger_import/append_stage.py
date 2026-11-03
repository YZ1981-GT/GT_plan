"""v2 管线的 staged 追加、差异报告与完整数据集校验编排。"""
from __future__ import annotations

from typing import Any, Awaitable, Callable
from uuid import UUID

from app.models.dataset_models import LedgerDataset
from app.services.dataset_service import DatasetService

ProgressCallback = Callable[[int, str], Awaitable[None]]
PhaseMarker = Callable[[str], None]
_TABLES = ("tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger")


def staged_source_summary(
    amount_unit: str | None,
    append_options: dict[str, Any] | None,
) -> dict[str, Any] | None:
    summary: dict[str, Any] = {}
    if amount_unit:
        summary["amount_unit"] = amount_unit
    if append_options:
        summary["append_request"] = dict(append_options)
    return summary or None


def expected_base_id(append_options: dict[str, Any] | None) -> UUID | None:
    value = append_options.get("base_dataset_id") if append_options else None
    return UUID(str(value)) if value else None


async def prepare_staged_append(
    *,
    session_factory,
    staged_dataset_id: UUID,
    project_id: UUID,
    year: int,
    append_options: dict[str, Any] | None,
    force_activate: bool,
    file_counts: tuple[int, int, int, int],
    progress: ProgressCallback,
    mark_phase: PhaseMarker,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]], tuple[int, int, int, int]]:
    append_report: dict[str, Any] | None = None
    table_counts = dict(zip(_TABLES, file_counts, strict=True))
    base_id = expected_base_id(append_options)
    if base_id is not None:
        from app.services.ledger_dataset_merge import merge_into_staged

        async def report_month(table_name: str, index: int, total: int) -> None:
            await progress(82, f"继承 {table_name}：第 {index}/{total} 月")

        await progress(82, "合并上一版本未覆盖月份")
        async with session_factory() as db:
            merged = await merge_into_staged(
                db,
                staged_id=staged_dataset_id,
                base_id=base_id,
                project_id=project_id,
                year=year,
                strategy=str(append_options["strategy"]),
                balance_carry_confirmed=bool(append_options.get("balance_carry_confirmed")),
                progress_callback=report_month,
            )
            append_report = merged.to_dict()
            table_counts = {name: merged.tables[name].actual_rows for name in _TABLES}
            await db.commit()
        mark_phase("append_merge_done")
    elif append_options:
        append_report = dict(append_options)

    from app.services.ledger_dataset_voucher_diff import build_and_store_voucher_diff

    async with session_factory() as db:
        staged = await db.get(LedgerDataset, staged_dataset_id)
        if staged is not None and append_report and base_id is None:
            staged.source_summary = {**(staged.source_summary or {}), "append": append_report}
        diff_base_id = base_id or (staged.previous_dataset_id if staged else None)
        voucher_diff = await build_and_store_voucher_diff(
            db, staged_dataset_id=staged_dataset_id, base_dataset_id=diff_base_id,
        )
        await db.commit()

    findings: list[dict[str, Any]] = []
    if append_report and base_id is not None:
        from app.services.import_validation_service import ImportValidationService

        async with session_factory() as db:
            business = await ImportValidationService.run_dataset_business_validation(
                db, project_id=project_id, year=year, dataset_id=staged_dataset_id,
            )
            findings = [item.to_dict() for item in business]
        gate = ImportValidationService.evaluate_activation(findings, force=force_activate)
        if not gate.get("allowed"):
            async with session_factory() as db:
                await DatasetService.mark_failed(db, staged_dataset_id, cleanup_rows=True)
                await db.commit()
            messages = [item.get("message", "合并后校验未通过") for item in gate.get("blocking_findings", [])]
            raise RuntimeError(f"合并后完整账套校验失败：{'; '.join(messages[:3])}")

    counts = tuple(table_counts[name] for name in _TABLES)
    return append_report, voucher_diff, findings, counts


__all__ = ["expected_base_id", "prepare_staged_append", "staged_source_summary"]
