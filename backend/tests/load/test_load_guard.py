"""容量压测专用库硬闸门（spec platform-heavy-jobs-and-capacity-closure 任务 0.3 / R1.2）。"""

from __future__ import annotations

import pytest

from tests.load.load_guard import (
    LoadGuardError,
    evaluate_load_target,
    require_safe_load_target,
)


def test_read_only_load_is_allowed_without_any_disposable_declaration():
    decision = evaluate_load_target({})
    assert decision.allow_writes is False
    assert decision.disposable_db_url is None


def test_write_load_requires_disposable_env_flag():
    with pytest.raises(LoadGuardError, match="GT_LOAD_DISPOSABLE_ENV=YES"):
        evaluate_load_target({"GT_LOAD_ALLOW_WRITES": "1"})


def test_write_load_requires_explicit_disposable_db_url():
    with pytest.raises(LoadGuardError, match="GT_LOAD_DISPOSABLE_DB_URL"):
        evaluate_load_target({
            "GT_LOAD_ALLOW_WRITES": "1",
            "GT_LOAD_DISPOSABLE_ENV": "YES",
        })


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://u:p@db:5432/audit_platform",
        "postgresql://u:p@localhost/postgres",
        "postgresql://u:p@host/gt_plan_dev",
        "postgresql://u:p@host/metabase_app",
    ],
)
def test_write_load_refuses_shared_or_default_databases(url):
    with pytest.raises(LoadGuardError, match="共享|默认"):
        evaluate_load_target({
            "GT_LOAD_ALLOW_WRITES": "1",
            "GT_LOAD_DISPOSABLE_ENV": "YES",
            "GT_LOAD_DISPOSABLE_DB_URL": url,
        })


def test_write_load_refuses_when_disposable_equals_running_database():
    with pytest.raises(LoadGuardError, match="同一个库"):
        evaluate_load_target({
            "GT_LOAD_ALLOW_WRITES": "1",
            "GT_LOAD_DISPOSABLE_ENV": "YES",
            "GT_LOAD_DISPOSABLE_DB_URL": "postgresql://u:p@host/gt_capacity_blast",
            "DATABASE_URL": "postgresql+asyncpg://u:p@host/gt_capacity_blast",
        })


def test_write_load_passes_with_declared_disposable_blast_database():
    decision = require_safe_load_target({
        "GT_LOAD_ALLOW_WRITES": "1",
        "GT_LOAD_DISPOSABLE_ENV": "YES",
        "GT_LOAD_DISPOSABLE_DB_URL": "postgresql+asyncpg://u:p@host:5432/gt_capacity_blast",
        "DATABASE_URL": "postgresql+asyncpg://u:p@host/audit_platform",
    })
    assert decision.allow_writes is True
    assert decision.disposable_db_url.endswith("gt_capacity_blast")
