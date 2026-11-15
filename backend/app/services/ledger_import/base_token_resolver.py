"""从当前 active 数据集解析 base token（spec 任务 8 / design §5）。

detect 与 submit 必须拿**同一份** base token，否则三次 CAS 没有基准。
本模块是唯一解析入口：任何调用方（detect / submit / seal / activation）都走它，
避免「一处按 active 查、另一处按 force_dataset_id 查」导致两边算出的 token 不同。

🔴 只读：不创建、不修改数据集。
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ledger_import.attempt_service import BaseToken


async def resolve_base_token(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
) -> BaseToken:
    """取当前 active 数据集的 UUID 与其单位合同 digest。

    口径与 `DatasetService.get_active_dataset_id` 一致（`status=active`，
    按 `activated_at DESC NULLS LAST, created_at DESC` 取最新）。
    `unit_contract_digest` 从 `source_summary.unit_normalization.contract.contract_digest`
    读——与 `dataset_unit_contract._is_valid_contract` 同一字段。

    无 active 时返回 `BaseToken(None, None)`（首次导入是合法状态）。
    """
    from app.models.dataset_models import DatasetStatus, LedgerDataset

    stmt = (
        sa.select(LedgerDataset.id, LedgerDataset.source_summary)
        .where(
            LedgerDataset.project_id == project_id,
            LedgerDataset.year == year,
            LedgerDataset.status == DatasetStatus.active,
        )
        .order_by(
            LedgerDataset.activated_at.desc().nulls_last(),
            LedgerDataset.created_at.desc(),
        )
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return BaseToken(dataset_id=None, unit_contract_digest=None)
    dataset_id, summary = row
    digest: str | None = None
    if isinstance(summary, dict):
        normalization = summary.get("unit_normalization")
        if isinstance(normalization, dict):
            contract = normalization.get("contract")
            if isinstance(contract, dict):
                raw = contract.get("contract_digest")
                if isinstance(raw, str) and len(raw) == 64:
                    digest = raw
    return BaseToken(dataset_id=dataset_id, unit_contract_digest=digest)
