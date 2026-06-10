"""Contract test: feature_flags DDL ↔ ORM 零 drift.

验证 V068 DDL 定义的列集合与 FeatureFlag ORM 模型完全一致（包含 TimestampMixin 的
created_at / updated_at），确保三层一致铁律不被破坏。

Validates: Requirements 9.5 (feature_flags 数据层三层一致)
"""

from app.models.audit_platform_models import FeatureFlag


def test_feature_flags_orm_columns():
    """Verify ORM model has all expected columns matching V068 DDL."""
    mapper = FeatureFlag.__table__
    column_names = {c.name for c in mapper.columns}
    expected = {
        "id",
        "flag_key",
        "description",
        "enabled",
        "rollout_percentage",
        "whitelist_user_ids",
        "created_at",
        "updated_at",
    }
    assert expected == column_names, (
        f"Column mismatch: expected={sorted(expected)}, got={sorted(column_names)}"
    )


def test_feature_flags_primary_key():
    """Verify primary key is 'id' column."""
    pk_cols = [c.name for c in FeatureFlag.__table__.primary_key.columns]
    assert pk_cols == ["id"]


def test_feature_flags_unique_constraint_on_flag_key():
    """Verify flag_key has unique constraint (matching DDL UNIQUE)."""
    col = FeatureFlag.__table__.c.flag_key
    # Column-level unique=True or table-level UniqueConstraint
    assert col.unique is True, "flag_key must have unique=True to match DDL"


def test_feature_flags_tablename():
    """Verify __tablename__ matches DDL table name."""
    assert FeatureFlag.__tablename__ == "feature_flags"


def test_feature_flags_rollout_percentage_type():
    """Verify rollout_percentage uses SmallInteger matching DDL SMALLINT."""
    import sqlalchemy as sa

    col = FeatureFlag.__table__.c.rollout_percentage
    assert isinstance(col.type, sa.SmallInteger), (
        f"rollout_percentage should be SmallInteger, got {type(col.type)}"
    )


def test_feature_flags_enabled_default():
    """Verify enabled column server_default is 'false' matching DDL."""
    col = FeatureFlag.__table__.c.enabled
    assert col.server_default is not None
    # server_default.arg.text contains the SQL expression
    assert "false" in str(col.server_default.arg).lower()
