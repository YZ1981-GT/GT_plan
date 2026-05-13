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
    AutoMatchResult,
    MappingCompletionRate,
    MappingInput,
    MappingResponse,
    MappingResult,
    MappingSuggestion,
)
from app.services.event_bus import event_bus
from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.dataset_query import get_active_filter
from app.services.dataset_service import DatasetService

logger = logging.getLogger(__name__)

# Fuzzy match threshold
_FUZZY_THRESHOLD = 0.7


async def _client_account_filters(
    project_id: UUID,
    db: AsyncSession,
    year: int | None = None,
) -> list[Any]:
    filters: list[Any] = [
        AccountChart.project_id == project_id,
        AccountChart.source == AccountSource.client,
        AccountChart.is_deleted == False,  # noqa: E712
    ]
    if year is not None:
        active_dataset_id = await DatasetService.get_active_dataset_id(db, project_id, year)
        if active_dataset_id is not None:
            filters.append(AccountChart.dataset_id == active_dataset_id)
    return filters


async def _resolve_event_year(
    project_id: UUID,
    db: AsyncSession,
    year: int | None = None,
) -> int | None:
    """优先使用显式 year，缺失时再从 ledger_datasets 推断最新 active 年度。"""
    if year is not None:
        return year

    from app.models.dataset_models import DatasetStatus, LedgerDataset
    year_result = await db.execute(
        select(LedgerDataset.year).where(
            LedgerDataset.project_id == project_id,
            LedgerDataset.status == DatasetStatus.active,
        ).order_by(LedgerDataset.year.desc()).limit(1)
    )
    return year_result.scalar_one_or_none()


async def _publish_mapping_changed(
    project_id: UUID,
    db: AsyncSession,
    account_codes: list[str] | None = None,
    year: int | None = None,
) -> None:
    """发布 MAPPING_CHANGED 事件（显式 year 优先，缺失时回退推断）。"""
    try:
        normalized_codes = [code for code in (account_codes or []) if code]
        resolved_year = await _resolve_event_year(project_id, db, year=year)

        payload = EventPayload(
            event_type=EventType.MAPPING_CHANGED,
            project_id=project_id,
            year=resolved_year,
            account_codes=normalized_codes or None,
        )
        await event_bus.publish(payload)
        logger.info("MAPPING_CHANGED 事件已发布: project=%s, year=%s, codes=%s", project_id, resolved_year, normalized_codes or None)
    except Exception as e:
        logger.warning("MAPPING_CHANGED 事件发布失败（不影响映射）: %s", e)



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
    year: int | None = None,
) -> list[MappingSuggestion]:
    """Auto-matching algorithm by priority:

    1. Code prefix exact match: client code first 4 chars == standard code
    2. Name exact match: client name == standard name
    3. Name fuzzy match: similarity > 0.7
    4. Unmatched: not included in suggestions

    Validates: Requirements 3.1
    """
    # Fetch client accounts
    client_filters = await _client_account_filters(project_id, db, year)
    client_result = await db.execute(
        select(AccountChart).where(*client_filters).order_by(AccountChart.account_code)
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


# ---------------------------------------------------------------------------
# auto_match — auto-suggest + auto-save in one step
# ---------------------------------------------------------------------------


async def _generate_client_accounts_from_balance(
    project_id: UUID,
    db: AsyncSession,
    year: int | None = None,
) -> int:
    """从 tb_balance 自动生成客户科目到 account_chart。

    当 account_chart 为空时调用，从已导入的余额表中提取唯一科目编码+名称，
    按编码规则推断 category（1xxx=资产/2xxx=负债/3xxx=权益/5xxx=收入/6xxx=费用）。
    """
    import uuid as _uuid
    from app.models.audit_platform_models import AccountCategory

    # 获取 active dataset 的余额表科目
    tbl = TbBalance.__table__
    active_filter = await get_active_filter(db, tbl, project_id, year or 2025)

    result = await db.execute(
        select(
            tbl.c.account_code,
            tbl.c.account_name,
        )
        .where(active_filter)
        .distinct()
        .order_by(tbl.c.account_code)
    )
    balance_accounts = result.fetchall()

    if not balance_accounts:
        return 0

    # 获取 active dataset_id
    dataset_id = await DatasetService.get_active_dataset_id(db, project_id, year or 2025)

    # 按编码首位推断 category
    def _infer_category(code: str) -> str:
        if not code:
            return AccountCategory.asset.value
        first = code[0]
        if first == '1':
            return AccountCategory.asset.value
        elif first == '2':
            return AccountCategory.liability.value
        elif first == '3':
            return AccountCategory.equity.value
        elif first in ('5', '4'):
            return AccountCategory.revenue.value
        elif first == '6':
            return AccountCategory.expense.value
        return AccountCategory.asset.value

    count = 0
    for row in balance_accounts:
        code = row.account_code
        name = row.account_name or code
        cat = _infer_category(code)

        # 检查是否已存在
        existing = await db.execute(
            select(AccountChart.id).where(
                AccountChart.project_id == project_id,
                AccountChart.account_code == code,
                AccountChart.source == AccountSource.client,
                AccountChart.is_deleted == False,  # noqa: E712
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            continue

        db.add(AccountChart(
            id=_uuid.uuid4(),
            project_id=project_id,
            account_code=code,
            account_name=name,
            source=AccountSource.client,
            category=cat,
            dataset_id=dataset_id,
        ))
        count += 1

    if count > 0:
        await db.flush()
        logger.info(
            "Generated %d client accounts from tb_balance for project %s",
            count, project_id,
        )

    return count


async def auto_match(
    project_id: UUID,
    db: AsyncSession,
    year: int | None = None,
) -> AutoMatchResult:
    """Auto-match and directly save all mappings.

    如果 account_chart 中没有客户科目，自动从 tb_balance 生成。
    然后运行 auto_suggest + 保存映射。
    """
    # 先检查是否有客户科目，没有则从 tb_balance 自动生成
    total_client = await _count_client_accounts(project_id, db, year=year)
    if total_client == 0:
        await _generate_client_accounts_from_balance(project_id, db, year=year)

    suggestions = await auto_suggest(project_id, db, year=year)

    # Get existing mappings to skip
    existing_result = await db.execute(
        select(AccountMapping.original_account_code).where(
            AccountMapping.project_id == project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
        )
    )
    existing_codes = {row[0] for row in existing_result.all()}

    saved = 0
    skipped = 0
    details: list[MappingSuggestion] = []

    for s in suggestions:
        if s.original_account_code in existing_codes:
            skipped += 1
            # Still include in details for display
            details.append(s)
            continue

        # Save mapping
        mapping_type = MappingType.auto_exact if s.confidence >= 0.92 else MappingType.auto_fuzzy
        record = AccountMapping(
            project_id=project_id,
            original_account_code=s.original_account_code,
            original_account_name=s.original_account_name,
            standard_account_code=s.suggested_standard_code,
            mapping_type=mapping_type,
        )
        db.add(record)
        saved += 1
        details.append(s)

    if saved > 0:
        await db.flush()
        await db.commit()
        await _publish_mapping_changed(project_id, db, account_codes=None, year=year)

    total_client = await _count_client_accounts(project_id, db, year=year)
    mapped_count = await _count_mapped_accounts(project_id, db)
    rate = (mapped_count / total_client * 100) if total_client > 0 else 0.0
    unmatched = total_client - mapped_count

    return AutoMatchResult(
        saved_count=saved,
        skipped_count=skipped,
        unmatched_count=unmatched,
        total_client=total_client,
        completion_rate=round(rate, 2),
        details=details,
    )


def _extract_level1_code(code: str) -> str:
    """Extract level-1 account code from a client code.

    Handles multiple formats:
    - "6401.01" → "6401"  (dot-separated)
    - "6401-01" → "6401"  (dash-separated)
    - "640101"  → "6401"  (concatenated, first 4 digits)
    - "6401"    → "6401"  (already level-1)
    """
    # Strip leading/trailing whitespace
    code = code.strip()
    # If contains dot or dash, take the part before first separator
    for sep in (".", "-"):
        if sep in code:
            return code.split(sep)[0]
    # Pure digits: take first 4 chars as level-1 code
    return code[:4] if len(code) >= 4 else code


def _match_single(
    client: AccountChart,
    std_by_code: dict[str, AccountChart],
    std_by_name: dict[str, AccountChart],
    standard_accounts: list[AccountChart],
) -> MappingSuggestion | None:
    """Try to match a single client account against standard accounts."""
    code = client.account_code
    name = client.account_name
    # Normalize: strip dots/dashes for lookup (e.g. "6401.01" → "640101")
    normalized = code.replace(".", "").replace("-", "").strip()

    # Priority 0: Full code exact match (e.g. "221101" → "221101 工资")
    if normalized in std_by_code:
        std = std_by_code[normalized]
        return MappingSuggestion(
            original_account_code=code,
            original_account_name=name,
            suggested_standard_code=std.account_code,
            suggested_standard_name=std.account_name,
            confidence=1.0,
            match_method="exact_code",
        )

    # Priority 1a: First-4-digit prefix match (e.g. "640101" → "6401")
    prefix = normalized[:4] if len(normalized) >= 4 else normalized
    if prefix in std_by_code:
        std = std_by_code[prefix]
        return MappingSuggestion(
            original_account_code=code,
            original_account_name=name,
            suggested_standard_code=std.account_code,
            suggested_standard_name=std.account_name,
            confidence=0.98,
            match_method="prefix",
        )

    # Priority 1b: Level-1 code from separator (e.g. "6401.01" → "6401")
    level1 = _extract_level1_code(code)
    if level1 != prefix and level1 in std_by_code:
        std = std_by_code[level1]
        return MappingSuggestion(
            original_account_code=code,
            original_account_name=name,
            suggested_standard_code=std.account_code,
            suggested_standard_name=std.account_name,
            confidence=0.96,
            match_method="level1_prefix",
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

    # Priority 2b: Name contains match — client name like "主营业务成本-累计折旧费"
    # should match standard "主营业务成本" (strip suffix after dash/hyphen)
    base_name = name.split("-")[0].split("—")[0].split("－")[0].strip()
    if base_name != name and base_name in std_by_name:
        std = std_by_name[base_name]
        return MappingSuggestion(
            original_account_code=code,
            original_account_name=name,
            suggested_standard_code=std.account_code,
            suggested_standard_name=std.account_name,
            confidence=0.92,
            match_method="base_name",
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
    skip_event: bool = False,
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
    old_standard_code = record.standard_account_code if record else None

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

    if not skip_event:
        changed_codes = list(dict.fromkeys([
            code for code in [old_standard_code, mapping.standard_account_code] if code
        ]))
        await _publish_mapping_changed(
            project_id, db,
            account_codes=changed_codes,
            year=mapping.year,
        )

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
    explicit_years = [m.year for m in mappings if m.year is not None]
    event_year = explicit_years[0] if explicit_years else None
    if len(set(explicit_years)) > 1:
        logger.warning("batch_confirm 收到多个 year，使用第一个: project=%s, years=%s", project_id, sorted(set(explicit_years)))
    for m in mappings:
        await save_mapping(project_id, m, db, skip_event=True)
        confirmed += 1

    # 批量确认涉及面较广，统一触发全量重算更稳妥
    if confirmed > 0:
        await _publish_mapping_changed(project_id, db, account_codes=None, year=event_year)

    # Calculate completion rate
    total_client = await _count_client_accounts(project_id, db, year=event_year)
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
    year: int | None = None,
) -> MappingCompletionRate:
    """Completion rate = mapped_count / total_client_accounts * 100%.

    Also returns unmapped_with_balance: list of unmapped client accounts
    that have non-zero balances in tb_balance.

    Validates: Requirements 3.5, 3.6
    """
    total_client = await _count_client_accounts(project_id, db, year=year)
    mapped_count = await _count_mapped_accounts(project_id, db)
    rate = (mapped_count / total_client * 100) if total_client > 0 else 0.0

    # Find unmapped client accounts with non-zero balances
    unmapped_with_balance = await _get_unmapped_with_balance(project_id, db, year=year)

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
    year: int | None = None,
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
    await _publish_mapping_changed(
        project_id,
        db,
        account_codes=[old_code, new_standard_code],
        year=year,
    )

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


async def _count_client_accounts(project_id: UUID, db: AsyncSession, year: int | None = None) -> int:
    """Count total client accounts for a project."""
    client_filters = await _client_account_filters(project_id, db, year)
    result = await db.execute(
        select(func.count(AccountChart.id)).where(*client_filters)
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
    year: int | None = None,
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
    client_filters = await _client_account_filters(project_id, db, year)
    client_result = await db.execute(
        select(AccountChart).where(*client_filters)
    )
    client_accounts = client_result.scalars().all()

    unmapped_codes = [
        a.account_code for a in client_accounts if a.account_code not in mapped_codes
    ]

    if not unmapped_codes:
        return []

    # Check which unmapped accounts have non-zero balances
    balance_filters: list[Any] = [
        TbBalance.project_id == project_id,
        TbBalance.account_code.in_(unmapped_codes),
        TbBalance.closing_balance != Decimal("0"),
    ]
    if year is not None:
        balance_filters.append(await get_active_filter(db, TbBalance.__table__, project_id, year))
    else:
        # year 未知时，查询所有 active 数据集对应的行
        from app.models.dataset_models import DatasetStatus, LedgerDataset
        ds_result = await db.execute(
            select(LedgerDataset.year).where(
                LedgerDataset.project_id == project_id,
                LedgerDataset.status == DatasetStatus.active,
            )
        )
        active_years = [row[0] for row in ds_result.all()]
        if active_years:
            # 使用最新 active 年度的过滤条件
            latest_year = max(active_years)
            balance_filters.append(await get_active_filter(db, TbBalance.__table__, project_id, latest_year))
        else:
            # 无 active 数据集时降级为 project_id 过滤
            balance_filters.append(TbBalance.project_id == project_id)
    balance_result = await db.execute(
        select(
            TbBalance.account_code,
            TbBalance.account_name,
            TbBalance.closing_balance,
        ).where(*balance_filters)
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


# ---------------------------------------------------------------------------
# scope_cycles → 科目编码映射（Phase 11 Task 7.2）
# ---------------------------------------------------------------------------

_WP_MAPPING_PATH = None


def _get_wp_mapping_path():
    global _WP_MAPPING_PATH
    if _WP_MAPPING_PATH is None:
        from pathlib import Path
        _WP_MAPPING_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "wp_account_mapping.json"
    return _WP_MAPPING_PATH


async def get_codes_by_cycles(project_id: UUID, cycles: list[str]) -> set[str]:
    """根据审计循环列表，返回对应的标准科目编码集合。

    通过 wp_account_mapping.json 的 cycle→account_codes 映射。
    """
    import json
    mapping_path = _get_wp_mapping_path()
    if not mapping_path.exists():
        return set()
    with open(mapping_path, encoding="utf-8-sig") as f:
        mappings = json.load(f)
    items = mappings if isinstance(mappings, list) else mappings.get("mappings", [])
    codes: set[str] = set()
    for m in items:
        if m.get("cycle") in cycles:
            codes.update(m.get("account_codes", []))
    return codes


async def get_sections_by_cycles(project_id: UUID, cycles: list[str]) -> set[str]:
    """根据审计循环列表，返回对应的附注章节编号集合。

    通过 wp_account_mapping.json 的 cycle→note_section 映射。
    """
    import json
    mapping_path = _get_wp_mapping_path()
    if not mapping_path.exists():
        return set()
    with open(mapping_path, encoding="utf-8-sig") as f:
        mappings = json.load(f)
    sections: set[str] = set()
    items = mappings if isinstance(mappings, list) else mappings.get("mappings", [])
    for m in items:
        if m.get("cycle") in cycles:
            ns = m.get("note_section")
            if ns:
                sections.add(ns)
    return sections
