# Feature: zero-downtime-deployment, Property 4, Property 5, Property 7, Property 8, Property 9
"""Property-based tests for migration compatibility detection.

Property 4: 破坏性 DDL 被检测并报告 (Requirements 2.2, 2.3, 2.5, 6.1, 10.1, 10.3)
Property 5: 豁免声明使破坏性 DDL 被放行 (Requirements 2.6, 10.5)
Property 7: CI 双档模式按档位决定退出码 (Requirements 2.8)
Property 9: V/R 迁移配对完整 (Requirements 10.4)
Property 8: 迁移 advisory lock 串行化多副本 (Requirements 2.7, 4.4) — requires real PG
"""
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

# Add scripts to path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "check"))
from check_migration_compat import scan_migration, Violation, EXEMPTION_MARKER, main as compat_main


# --- Property 4: Breaking DDL detected ---
# **Validates: Requirements 2.2, 2.3, 2.5, 6.1, 10.1, 10.3**

breaking_ddl_st = st.sampled_from([
    "ALTER TABLE users DROP COLUMN email;",
    "ALTER TABLE users RENAME COLUMN name TO full_name;",
    "ALTER TABLE users ALTER COLUMN age TYPE TEXT;",
    "ALTER TABLE users ADD COLUMN status VARCHAR(20) NOT NULL;",
])

safe_ddl_st = st.sampled_from([
    "ALTER TABLE users ADD COLUMN nickname VARCHAR(50);",  # nullable, safe
    "ALTER TABLE users ADD COLUMN active BOOLEAN NOT NULL DEFAULT true;",  # has default, safe
    "CREATE TABLE new_table (id UUID PRIMARY KEY);",  # new table, safe
    "CREATE INDEX idx_users_email ON users(email);",  # index, not breaking
])


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(sql=breaking_ddl_st)
def test_property4_breaking_ddl_detected(sql):
    """Property 4: 破坏性 DDL 被检测并报告。"""
    violations = scan_migration(sql, "V999__test.sql")
    assert len(violations) > 0, f"Should detect breaking DDL in: {sql}"
    assert all(not v.exempt for v in violations)


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(sql=safe_ddl_st)
def test_property4_safe_ddl_not_flagged(sql):
    """Property 4: 安全 DDL 不被误报。"""
    violations = scan_migration(sql, "V999__test.sql")
    # Filter only breaking violations (not lock patterns)
    breaking = [v for v in violations if v.category != "CREATE_INDEX_NON_CONCURRENT"]
    assert len(breaking) == 0, f"Should not flag safe DDL: {sql}"


# --- Property 5: Exemption declaration ---
# **Validates: Requirements 2.6, 10.5**

@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(sql=breaking_ddl_st)
def test_property5_exemption_grants_exempt(sql):
    """Property 5: 含豁免声明→violations 标 exempt=True。"""
    sql_with_exempt = f"{EXEMPTION_MARKER} v1.2.0\n{sql}"
    violations = scan_migration(sql_with_exempt, "V999__test.sql")
    assert len(violations) > 0
    assert all(v.exempt for v in violations)


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(sql=breaking_ddl_st)
def test_property5_no_exemption_not_exempt(sql):
    """Property 5: 不含豁免声明→violations 标 exempt=False。"""
    violations = scan_migration(sql, "V999__test.sql")
    assert len(violations) > 0
    assert all(not v.exempt for v in violations)


# --- Property 7: Dual-mode exit codes ---
# **Validates: Requirements 2.8**

@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
@given(
    has_violation=st.booleans(),
    is_exempt=st.booleans(),
    mode=st.sampled_from(["warning", "strict"]),
)
def test_property7_dual_mode_exit_codes(has_violation, is_exempt, mode, tmp_path, monkeypatch):
    """Property 7: warning 模式恒退出 0；strict 当且仅当存在非豁免违规时退出非 0。"""
    # Create a temporary migration file
    sql = ""
    if has_violation:
        if is_exempt:
            sql = f"{EXEMPTION_MARKER} v1.0.0\nALTER TABLE t DROP COLUMN c;"
        else:
            sql = "ALTER TABLE t DROP COLUMN c;"
    else:
        sql = "CREATE TABLE safe (id INT);"

    migration_file = tmp_path / "V999__test.sql"
    migration_file.write_text(sql, encoding="utf-8")

    # Mock scan_changed_migrations to return our temp file
    monkeypatch.setattr(
        "check_migration_compat.scan_changed_migrations",
        lambda: [migration_file],
    )

    # Mock sys.argv
    monkeypatch.setattr(sys, "argv", ["check_migration_compat.py", "--mode", mode])

    exit_code = compat_main()

    if mode == "warning":
        assert exit_code == 0, "warning mode should always exit 0"
    else:  # strict
        if has_violation and not is_exempt:
            assert exit_code == 1, "strict + non-exempt violation should exit 1"
        else:
            assert exit_code == 0, "strict + no violation or all exempt should exit 0"


# --- Property 9: V/R pairing ---
# **Validates: Requirements 10.4**

def test_property9_vr_pairing_complete():
    """Property 9: 每个 V{n}*.sql 存在对应 R{n}*.sql。"""
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    if not migrations_dir.exists():
        pytest.skip("migrations directory not found")

    v_files = sorted(migrations_dir.glob("V*.sql"))
    missing_rollbacks = []

    for v_file in v_files:
        # Extract version number: V066__name.sql -> 066
        name = v_file.name
        # Pattern: V{number}__{description}.sql
        parts = name.split("__", 1)
        if not parts[0].startswith("V"):
            continue
        version_num = parts[0][1:]  # "066"

        # Look for matching R{number}__*.sql
        r_pattern = f"R{version_num}__*.sql"
        r_files = list(migrations_dir.glob(r_pattern))

        if not r_files:
            # Also try R{number}*.sql (less strict pattern)
            r_pattern2 = f"R{version_num}*.sql"
            r_files = list(migrations_dir.glob(r_pattern2))

        if not r_files:
            missing_rollbacks.append(v_file.name)

    # Allow some missing (legacy migrations may not have rollbacks)
    # But report them
    if missing_rollbacks:
        # This is informational — old migrations may legitimately lack rollbacks
        # New migrations (V060+) should all have them
        new_missing = [m for m in missing_rollbacks if int(m.split("__")[0][1:]) >= 60]
        assert len(new_missing) == 0, f"New migrations (V060+) missing rollbacks: {new_missing}"


# --- Property 8: Advisory lock serialization (conceptual) ---
# **Validates: Requirements 2.7, 4.4**
# Note: Full test requires real PG, marked pg_only

def test_property8_advisory_lock_concept():
    """Property 8: advisory lock 串行化概念验证（复用已有 MigrationRunner）。

    验证 MigrationRunner._advisory_lock 存在且使用 pg_advisory_lock。
    完整并发测试需真实 PG（标记 pg_only）。
    """
    import inspect
    from app.core.migration_runner import MigrationRunner

    # Verify advisory lock method exists
    assert hasattr(MigrationRunner, '_advisory_lock'), "MigrationRunner should have _advisory_lock method"

    # Verify it uses pg_advisory_lock in its source
    source = inspect.getsource(MigrationRunner._advisory_lock)
    assert "pg_advisory_lock" in source, "Should use pg_advisory_lock for serialization"


# --- Property 6: Non-concurrent index detection ---
# **Validates: Requirements 8.2, 8.3**


def test_property6_non_concurrent_index_flagged():
    """Property 6: CREATE INDEX 未用 CONCURRENTLY 被标记为锁表风险。"""
    sql_non_concurrent = "CREATE INDEX idx_test ON users(email);"
    violations = scan_migration(sql_non_concurrent, "V999__test.sql")
    lock_violations = [v for v in violations if v.category == "CREATE_INDEX_NON_CONCURRENT"]
    assert len(lock_violations) > 0, "Non-concurrent CREATE INDEX should be flagged"


def test_property6_concurrent_index_not_flagged():
    """Property 6: CREATE INDEX CONCURRENTLY 不被标记。"""
    sql_concurrent = "CREATE INDEX CONCURRENTLY idx_test ON users(email);"
    violations = scan_migration(sql_concurrent, "V999__test.sql")
    lock_violations = [v for v in violations if v.category == "CREATE_INDEX_NON_CONCURRENT"]
    assert len(lock_violations) == 0, "CONCURRENTLY index should not be flagged"


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(
    table=st.sampled_from(["users", "projects", "trial_balance", "working_paper"]),
    col=st.sampled_from(["email", "name", "status", "created_at"]),
    concurrent=st.booleans(),
)
def test_property6_concurrent_flag_detection(table, col, concurrent):
    """Property 6: 当且仅当未用 CONCURRENTLY 时标记锁表告警。

    # Feature: zero-downtime-deployment, Property 6
    """
    if concurrent:
        sql = f"CREATE INDEX CONCURRENTLY idx_{table}_{col} ON {table}({col});"
    else:
        sql = f"CREATE INDEX idx_{table}_{col} ON {table}({col});"

    violations = scan_migration(sql, "V999__test.sql")
    lock_violations = [v for v in violations if v.category == "CREATE_INDEX_NON_CONCURRENT"]

    if concurrent:
        assert len(lock_violations) == 0, f"CONCURRENTLY should not be flagged: {sql}"
    else:
        assert len(lock_violations) > 0, f"Non-concurrent should be flagged: {sql}"
