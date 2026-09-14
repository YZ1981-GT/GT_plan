"""抽样批次治理测试（voucher-sampling-hardening Task 7.3）

离线可验：
- 状态机合法转移（Property 10）。
- ORM WorkpaperExtractionLog 已同步 V123 新列（drift 防护）。
- V123 迁移幂等守护 + NOT VALID + 部分唯一索引 + R123 回滚结构。

DB 级约束强制（P9 幂等唯一 / P11 撤销唯一 / P12 CHECK 拒绝）由 V123 的部分唯一索引与
CHECK 约束在 apply 后强制，需 live PG 应用后验证（见迁移文件）。

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6
Properties: Property 10
"""

from __future__ import annotations

from pathlib import Path

from app.models.audit_platform_models import WorkpaperExtractionLog
from app.services.sampling_batch_service import (
    SAMPLING_BATCH_STATUSES,
    is_valid_transition,
    assert_valid_transition,
)

_MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


class TestStateMachine:
    def test_legal_transitions(self):
        assert is_valid_transition("draft", "confirmed")
        assert is_valid_transition("draft", "filled")
        assert is_valid_transition("confirmed", "filled")
        assert is_valid_transition("filled", "undone")

    def test_illegal_transitions_from_terminal(self):
        # filled 仅可转 undone，不可回退
        assert not is_valid_transition("filled", "draft")
        assert not is_valid_transition("filled", "confirmed")
        # undone 为终态
        assert not is_valid_transition("undone", "filled")
        assert not is_valid_transition("undone", "draft")

    def test_unknown_status_illegal(self):
        assert not is_valid_transition("bogus", "filled")
        assert not is_valid_transition("filled", "bogus")

    def test_assert_raises_on_illegal(self):
        import pytest

        with pytest.raises(ValueError):
            assert_valid_transition("undone", "filled")

    def test_status_set(self):
        assert set(SAMPLING_BATCH_STATUSES) == {"draft", "confirmed", "filled", "undone"}


class TestOrmColumnsSynced:
    def test_new_columns_present(self):
        cols = set(WorkpaperExtractionLog.__table__.columns.keys())
        for c in ("batch_id", "idempotency_key", "row_version", "status"):
            assert c in cols, f"ORM 缺列 {c}（与 V123 迁移漂移）"


class TestMigrationStructure:
    def test_v123_migration_idempotent_and_safe(self):
        sql = (_MIGRATIONS / "V123__voucher_sampling_batch_governance.sql").read_text(
            encoding="utf-8"
        )
        # 幂等守护
        assert "IF NOT EXISTS" in sql
        assert "information_schema.columns" in sql
        # CHECK / FK 用 NOT VALID（不校验历史行）
        assert "NOT VALID" in sql
        # 三个 CHECK 约束
        assert "chk_extraction_log_fill_mode" in sql
        assert "chk_extraction_log_type" in sql
        assert "chk_extraction_log_status" in sql
        # user_id FK
        assert "fk_extraction_log_user" in sql
        assert "REFERENCES users" in sql
        # 幂等键唯一 + 撤销唯一 部分索引
        assert "uq_extraction_log_wp_idempotency" in sql
        assert "WHERE idempotency_key IS NOT NULL" in sql
        assert "uq_extraction_log_batch_undone" in sql
        assert "status = 'undone'" in sql

    def test_r123_rollback_present(self):
        sql = (
            _MIGRATIONS / "R123__rollback_voucher_sampling_batch_governance.sql"
        ).read_text(encoding="utf-8")
        assert "DROP COLUMN IF EXISTS batch_id" in sql
        assert "DROP CONSTRAINT IF EXISTS chk_extraction_log_status" in sql
        assert "DROP INDEX IF EXISTS uq_extraction_log_batch_undone" in sql
