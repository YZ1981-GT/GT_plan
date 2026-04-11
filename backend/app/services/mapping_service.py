"""科目映射引擎 — 自动匹配 + 手动调整 + 完成率

Validates: Requirements 3.1, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""

import logging
from difflib import SequenceMatcher
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountChart,
    AccountMapping,
    AccountSource,
    MappingType,
    TbBalance,
)
from app.models.audit_platform_schemas import (
    MappingCompletionRate,
    MappingInput,
    MappingResponse,
    MappingResult,
    MappingSuggestion,
)
from app.services.event_bus import event_bus
from app.models.audit_platform_schemas import EventPayload, EventType

logger = logging.getLogger(__name__)

# Fuzzy match threshold
_FUZZY_THRESHOLD = 0.7


# ---------------------------------------------------------------------------
# Similarity helpers (stdlib only — no external deps)
# ---------------------------------------------------------------------------


def _jaccard_similarity(a: str, b: str) -> float:
    """Jaccard similarity on character bigrams."""
    if not a or not b:
        return 0.0
    set_a = {a[i : i + 2] for i in range(len(a) - 1)} if len(a) > 1 else {a}
    set_b = {b[i : i + 2] for i in range(len(b) - 1)} if len(b) > 1 else {b}
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _sequence_similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio (Levenshtein-like)."""
    return SequenceMatcher(None, a, b).ratio()


def _fuzzy_score(a: str, b: str) -> float:
    """Combined fuzzy score: max of Jaccard and SequenceMatcher."""
    return max(_jaccard_similarity(a, b), _sequence_similarity(a, b))


# ---------------------------------------------------------------------------
# auto_suggest
# ---------------------------------------------------------------------------


async def auto_suggest(
    project_id: UUID,
    db: AsyncSession,
) -> list[MappingSuggestion]:
    """Auto-matching algorithm by priority:

    1. Code prefix exact match: client code first 4 chars == standard code
    2. Name exact match: client name == standard name
    3. Name fuzzy match: similarity > 0.7
    4. Unmatched: not included in suggestions

    Validates: Requirements 3.1
    """
    # Fetch client accounts
    client_result = await db.execute(
        select(AccountChart).where(
            AccountChart.project_id == project_id,
            AccountChart.source == AccountSource.client,
            AccountChart.is_deleted == False,  # noqa: E712
        ).order_by(AccountChart.account_code)
    )
    client_accounts = client_result.scalars().all()

    # Fetch standard accounts
    std_result = await db.execute(
        select(AccountChart).where(
            AccountChart.project_id == project_id,
            AccountChart.source == AccountSource.standard,
            AccountChart.is_deleted == False,  # noqa: E712
        ).order_by(AccountChart.account_code)
    )
    standard_accounts = std_result.scalars().all()

    if not client_accounts or not standard_accounts:
        return []

    # Build lookup structures
    std_by_code: dict[str, AccountChart] = {a.account_code: a for a in standard_accounts}
    std_by_name: dict[str, AccountChart] = {a.account_name: a for a in standard_accounts}

    suggestions: list[MappingSuggestion] = []

    for client in client_accounts:
        suggestion = _match_single(client, std_by_code, std_by_name, standard_accounts)
        if suggestion:
            suggestions.append(suggestion)

    return suggestions


def _match_single(
    client: AccountChart,
    std_by_code: dict[str, AccountChart],
    std_by_name: dict[str, AccountChart],
    standard_accounts: list[AccountChart],
) -> MappingSuggestion | None:
    """Try to match a single client account against standard accounts."""
    code = client.account_code
    name = client.account_name
    prefix = code[:4] if len(code) >= 4 else code

    # Priority 1: Code prefix exact match
    if prefix in std_by_code:
        std = std_by_code[prefix]
        return MappingSuggestion(
            original_account_code=code,
            original_account_name=name,
            suggested_standard_code=std.account_code,
            suggested_standard_name=std.account_name,
            confidence=1.0,
            match_method="prefix",
        )

    # Priority 2: Name exact match
    if name in std_by_name:
        std = std_by_name[name]
        return MappingSuggestion(
            original_account_code=code,
            original_account_name=name,
            suggested_standard_code=std.account_code,
            suggested_standard_name=std.account_name,
            confidence=0.95,
            match_method="exact_name",
        )

    # Priority 3: Name fuzzy match
    best_score = 0.0
    best_std: AccountChart | None = None
    for std in standard_accounts:
        score = _fuzzy_score(name, std.account_name)
        if score > best_score:
            best_score = score
            best_std = std

    if best_std and best_score >= _FUZZY_THRESHOLD:
        return MappingSuggestion(
            original_account_code=code,
            original_account_name=name,
            suggested_standard_code=best_std.account_code,
            suggested_standard_name=best_std.account_name,
            confidence=round(best_score, 2),
            match_method="fuzzy_name",
        )

    # Priority 4: Unmatched — no suggestion returned
    return None


# ---------------------------------------------------------------------------
# save_mapping
# ---------------------------------------------------------------------------


async def save_mapping(
    project_id: UUID,
    mapping: MappingInput,
    db: AsyncSession,
) -> AccountMapping:
    """Save a single mapping to account_mapping table.

    Supports many-to-one: multiple client accounts → one standard account.

    Validates: Requirements 3.3, 3.4
    """
    # Check if mapping already exists for this original code
    existing = await db.execute(
        select(AccountMapping).where(
            AccountMapping.project_id == project_id,
            AccountMapping.original_account_code == mapping.original_account_code,
            AccountMapping.is_deleted == False,  # noqa: E712
        )
    )
    record = existing.scalar_one_or_none()

    if record:
        # Update existing mapping
        record.standard_account_code = mapping.standard_account_code
        record.original_account_name = mapping.original_account_name
        record.mapping_type = mapping.mapping_type
    else:
        record = AccountMapping(
            project_id=project_id,
            original_account_code=mapping.original_account_code,
            original_account_name=mapping.original_account_name,
            standard_account_code=mapping.standard_account_code,
            mapping_type=mapping.mapping_type,
        )
        db.add(record)

    await db.flush()
    await db.commit()
    await db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# batch_confirm
# ---------------------------------------------------------------------------


async def batch_confirm(
    project_id: UUID,
    mappings: list[MappingInput],
    db: AsyncSession,
) -> MappingResult:
    """Batch confirm mappings, return completion rate.

    Validates: Requirements 3.5
    """
    confirmed = 0
    for m in mappings:
        await save_mapping(project_id, m, db)
        confirmed += 1

    # Calculate completion rate
    total_client = await _count_client_accounts(project_id, db)
    mapped_count = await _count_mapped_accounts(project_id, db)
    rate = (mapped_count / total_client * 100) if total_client > 0 else 0.0

    return MappingResult(
        confirmed_count=confirmed,
        total_count=total_client,
        completion_rate=round(rate, 2),
    )


# ---------------------------------------------------------------------------
# get_completion_rate
# ---------------------------------------------------------------------------


async def get_completion_rate(
    project_id: UUID,
    db: AsyncSession,
) -> MappingCompletionRate:
    """Completion rate = mapped_count / total_client_accounts * 100%.

    Also returns unmapped_with_balance: list of unmapped client accounts
    that have non-zero balances in tb_balance.

    Validates: Requirements 3.5, 3.6
    """
    total_client = await _count_client_accounts(project_id, db)
    mapped_count = await _count_mapped_accounts(project_id, db)
    rate = (mapped_count / total_client * 100) if total_client > 0 else 0.0

    # Find unmapped client accounts with non-zero balances
    unmapped_with_balance = await _get_unmapped_with_balance(project_id, db)

    return MappingCompletionRate(
        mapped_count=mapped_count,
        total_count=total_client,
        completion_rate=round(rate, 2),
        unmapped_with_balance=unmapped_with_balance,
    )


# ---------------------------------------------------------------------------
# update_mapping
# ---------------------------------------------------------------------------


async def update_mapping(
    project_id: UUID,
    mapping_id: UUID,
    new_standard_code: str,
    db: AsyncSession,
) -> AccountMapping:
    """Update mapping, publish MAPPING_CHANGED event (log for now).

    Validates: Requirements 3.7
    """
    result = await db.execute(
        select(AccountMapping).where(
            AccountMapping.id == mapping_id,
            AccountMapping.project_id == project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="映射记录不存在")

    old_code = record.standard_account_code
    record.standard_account_code = new_standard_code
    record.mapping_type = MappingType.manual

    await db.flush()
    await db.commit()
    await db.refresh(record)

    # Publish mapping changed event (旧+新标准科目都需要重算)
    logger.info(
        "MAPPING_CHANGED: project=%s, mapping=%s, old=%s, new=%s",
        project_id,
        mapping_id,
        old_code,
        new_standard_code,
    )
    payload = EventPayload(
        event_type=EventType.MAPPING_CHANGED,
        project_id=project_id,
        account_codes=[old_code, new_standard_code],
    )
    await event_bus.publish(payload)

    return record


# ---------------------------------------------------------------------------
# get_mappings
# ---------------------------------------------------------------------------


async def get_mappings(
    project_id: UUID,
    db: AsyncSession,
) -> list[MappingResponse]:
    """Get all mappings for a project.

    Validates: Requirements 3.8
    """
    result = await db.execute(
        select(AccountMapping).where(
            AccountMapping.project_id == project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
        ).order_by(AccountMapping.original_account_code)
    )
    mappings = result.scalars().all()
    return [MappingResponse.model_validate(m) for m in mappings]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _count_client_accounts(project_id: UUID, db: AsyncSession) -> int:
    """Count total client accounts for a project."""
    result = await db.execute(
        select(func.count(AccountChart.id)).where(
            AccountChart.project_id == project_id,
            AccountChart.source == AccountSource.client,
            AccountChart.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one()


async def _count_mapped_accounts(project_id: UUID, db: AsyncSession) -> int:
    """Count mapped accounts for a project."""
    result = await db.execute(
        select(func.count(AccountMapping.id)).where(
            AccountMapping.project_id == project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one()


async def _get_unmapped_with_balance(
    project_id: UUID,
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """Get unmapped client accounts that have non-zero balances.

    Validates: Requirements 3.6
    """
    # Get all mapped original codes
    mapped_result = await db.execute(
        select(AccountMapping.original_account_code).where(
            AccountMapping.project_id == project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
        )
    )
    mapped_codes = {row[0] for row in mapped_result.all()}

    # Get client accounts
    client_result = await db.execute(
        select(AccountChart).where(
            AccountChart.project_id == project_id,
            AccountChart.source == AccountSource.client,
            AccountChart.is_deleted == False,  # noqa: E712
        )
    )
    client_accounts = client_result.scalars().all()

    unmapped_codes = [
        a.account_code for a in client_accounts if a.account_code not in mapped_codes
    ]

    if not unmapped_codes:
        return []

    # Check which unmapped accounts have non-zero balances
    balance_result = await db.execute(
        select(
            TbBalance.account_code,
            TbBalance.account_name,
            TbBalance.closing_balance,
        ).where(
            TbBalance.project_id == project_id,
            TbBalance.account_code.in_(unmapped_codes),
            TbBalance.is_deleted == False,  # noqa: E712
            TbBalance.closing_balance != Decimal("0"),
        )
    )
    rows = balance_result.all()

    return [
        {
            "account_code": row.account_code,
            "account_name": row.account_name,
            "closing_balance": str(row.closing_balance) if row.closing_balance else "0",
        }
        for row in rows
    ]
