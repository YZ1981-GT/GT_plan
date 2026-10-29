"""所有 public.dataset_id 表必须在增量合并归类清单中，清单不得陈旧。"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.ledger_dataset_merge import DATASET_BOUND_TABLES


def _classified() -> set[str]:
    groups = [set(values) for values in DATASET_BOUND_TABLES.values()]
    assert all(groups[i].isdisjoint(groups[j]) for i in range(len(groups)) for j in range(i + 1, len(groups)))
    return set().union(*groups)


def test_classification_has_expected_behavioral_groups():
    assert set(DATASET_BOUND_TABLES) == {"periodic", "snapshot", "not_import_product"}
    assert set(DATASET_BOUND_TABLES["periodic"]) == {"tb_ledger", "tb_aux_ledger"}
    assert {"tb_balance", "tb_aux_balance", "account_chart", "direction_override"} == set(
        DATASET_BOUND_TABLES["snapshot"]
    )
    assert "interim_survival_checks" in DATASET_BOUND_TABLES["not_import_product"]
    assert len(_classified()) == sum(len(values) for values in DATASET_BOUND_TABLES.values())


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_postgres_dataset_id_tables_equal_classification():
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        pytest.skip("需要真实 PostgreSQL")
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(sa.text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema='public' AND column_name='dataset_id' ORDER BY table_name"
            ))
            actual = {str(name) for name in rows.scalars().all()}
    finally:
        await engine.dispose()
    expected = _classified()
    assert actual == expected, {
        "unclassified": sorted(actual - expected),
        "stale_entries": sorted(expected - actual),
    }
