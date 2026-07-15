"""Task 2.1 — 动态迁移编号分配 + evidence-governance 迁移约定守卫测试。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 2.1 (Wave 1)
Requirements: R14
Design: §8.1

覆盖：
  * analyze_migration_state / next_available_version 纯函数（含 pending benign、
    applied-missing / duplicate / failure 三类 blocking）。
  * 对真实 backend/migrations 目录扫描：确认无重复号、可算出下一可用 V。
  * lint_migration_sql：additive-only / 可重复检测 / FK ON DELETE RESTRICT，
    并对真实 V103/V104/V105 做回归。
  * 真实 PG16 状态一致性（read-only，非 PG 环境自动 skip）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.evidence_governance.migration_allocation import (
    MigrationStateInconsistency,
    MigrationStateReport,
    analyze_migration_state,
    format_version,
    lint_migration_sql,
    next_available_version,
    normalize_version,
    parse_dir_versions,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


# ---------------------------------------------------------------------------
# 版本号规范化
# ---------------------------------------------------------------------------

class TestNormalize:
    @pytest.mark.parametrize("raw,expected", [
        ("102", 102), ("V102", 102), (102, 102),
        ("V105__evidence_governance_role_eqcr_enum.sql", 105),
        ("v007", 7),
    ])
    def test_normalize(self, raw, expected):
        assert normalize_version(raw) == expected

    def test_format(self):
        assert format_version(106) == "V106"
        assert format_version(6) == "V006"

    def test_parse_dir_versions_ignores_non_migrations(self):
        by = parse_dir_versions(["V001__x.sql", "README.md", "V002__y.sql", "notes.txt"])
        assert set(by) == {1, 2}


# ---------------------------------------------------------------------------
# 状态分析（纯函数）
# ---------------------------------------------------------------------------

class TestAnalyzeState:
    def test_pending_is_benign_not_blocking(self):
        """目录有 V103/V104/V105、DB 只到 V102 —— pending，不阻断，下一可用=106。"""
        dir_files = [f"V{ i :03d}__x.sql" for i in range(1, 106)]
        applied = {str(i) for i in range(1, 103)}  # 1..102
        report = analyze_migration_state(dir_files, applied)
        assert report.is_consistent
        assert report.dir_highest == 105
        assert report.applied_highest == 102
        assert report.pending_versions == [103, 104, 105]
        assert report.next_available == 106
        assert report.blocking_reasons == []

    def test_fully_applied_next_is_highest_plus_one(self):
        dir_files = [f"V{i:03d}__x.sql" for i in range(1, 106)]
        applied = {str(i) for i in range(1, 106)}
        report = analyze_migration_state(dir_files, applied)
        assert report.is_consistent
        assert report.pending_versions == []
        assert report.next_available == 106

    def test_applied_missing_in_dir_blocks(self):
        """DB 已应用 V200 但目录没有 —— blocking。"""
        dir_files = [f"V{i:03d}__x.sql" for i in range(1, 106)]
        applied = {str(i) for i in range(1, 103)} | {"200"}
        report = analyze_migration_state(dir_files, applied)
        assert not report.is_consistent
        assert report.applied_missing_in_dir == [200]
        assert report.next_available is None

    def test_failure_record_blocks(self):
        dir_files = [f"V{i:03d}__x.sql" for i in range(1, 106)]
        applied = {str(i) for i in range(1, 103)}
        report = analyze_migration_state(dir_files, applied, failure_versions={"104"})
        assert not report.is_consistent
        assert report.failure_versions == ["104"]
        assert any("failures" in r or "失败" in r for r in report.blocking_reasons)

    def test_duplicate_versions_block(self):
        dir_files = ["V001__a.sql", "V040__a.sql", "V040__b.sql"]
        report = analyze_migration_state(dir_files, {"1"})
        assert not report.is_consistent
        assert report.duplicate_versions == [40]

    def test_next_available_raises_on_inconsistency(self):
        dir_files = ["V001__a.sql", "V040__a.sql", "V040__b.sql"]
        with pytest.raises(MigrationStateInconsistency):
            next_available_version(dir_files, {"1"})

    def test_next_available_ok(self):
        dir_files = [f"V{i:03d}__x.sql" for i in range(1, 106)]
        applied = {str(i) for i in range(1, 103)}
        assert next_available_version(dir_files, applied) == 106


# ---------------------------------------------------------------------------
# 真实迁移目录
# ---------------------------------------------------------------------------

class TestRealMigrationsDir:
    def test_dir_scans_and_has_no_duplicates(self):
        filenames = [p.name for p in MIGRATIONS_DIR.glob("V*.sql")]
        by = parse_dir_versions(filenames)
        dupes = {v: names for v, names in by.items() if len(names) > 1}
        assert dupes == {}, f"重复版本号：{dupes}"

    def test_dir_highest_is_at_least_105(self):
        filenames = [p.name for p in MIGRATIONS_DIR.glob("V*.sql")]
        by = parse_dir_versions(filenames)
        assert max(by) >= 105  # V105 eqcr enum 已由 Task 1.1 加入

    def test_next_available_from_dir_when_fully_applied(self):
        """把整个目录视为已应用 —— 下一可用 = 目录最高 + 1（allocation 契约演示）。"""
        filenames = [p.name for p in MIGRATIONS_DIR.glob("V*.sql")]
        by = parse_dir_versions(filenames)
        applied = {str(v) for v in by}
        nxt = next_available_version(filenames, applied)
        assert nxt == max(by) + 1


# ---------------------------------------------------------------------------
# 约定 lint
# ---------------------------------------------------------------------------

class TestLint:
    def test_additive_clean_passes(self):
        sql = """
        CREATE TABLE IF NOT EXISTS foo (
            id UUID PRIMARY KEY,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_foo ON foo(project_id);
        """
        assert lint_migration_sql(sql) == []

    def test_drop_table_flagged(self):
        assert lint_migration_sql("DROP TABLE legacy_x;", require_fk_restrict=False)

    def test_drop_column_flagged(self):
        assert lint_migration_sql(
            "ALTER TABLE foo DROP COLUMN legacy_col;", require_fk_restrict=False
        )

    def test_create_table_without_ine_flagged(self):
        v = lint_migration_sql("CREATE TABLE foo (id UUID);", require_fk_restrict=False)
        assert any("CREATE TABLE" in x for x in v)

    def test_fk_without_restrict_flagged(self):
        sql = "CREATE TABLE IF NOT EXISTS foo (pid UUID REFERENCES projects(id));"
        v = lint_migration_sql(sql)
        assert any("RESTRICT" in x for x in v)

    def test_fk_restrict_ok(self):
        sql = ("CREATE TABLE IF NOT EXISTS foo "
               "(pid UUID REFERENCES projects(id) ON DELETE RESTRICT);")
        assert lint_migration_sql(sql) == []

    def test_add_column_guarded_by_info_schema_ok(self):
        sql = """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_name='foo' AND column_name='bar') THEN
                ALTER TABLE foo ADD COLUMN bar TEXT;
            END IF;
        END $$;
        """
        assert lint_migration_sql(sql, require_fk_restrict=False) == []

    def test_comment_with_drop_not_flagged(self):
        sql = "-- this migration does not DROP TABLE anything\nSELECT 1;"
        assert lint_migration_sql(sql, require_fk_restrict=False) == []

    def test_real_v105_enum_only_additive(self):
        """V105 是 enum-only（ADD VALUE IF NOT EXISTS），无 FK/表；additive 通过。"""
        sql = (MIGRATIONS_DIR / "V105__evidence_governance_role_eqcr_enum.sql").read_text(
            encoding="utf-8"
        )
        assert lint_migration_sql(sql, require_fk_restrict=False) == []

    def test_real_v104_additive_repeatable(self):
        """V104 全部 information_schema 守卫 + CREATE TABLE/INDEX IF NOT EXISTS。"""
        sql = (MIGRATIONS_DIR / "V104__formula_runtime_outbox.sql").read_text(
            encoding="utf-8"
        )
        # V104 的 FK 不属于本 spec 的 evidence-governance 表，跳过 FK RESTRICT 检查；
        # 只验证 additive + 可重复检测。
        v = lint_migration_sql(sql, require_fk_restrict=False)
        assert v == [], f"V104 违反 additive/repeatable：{v}"


# ---------------------------------------------------------------------------
# 真实 PG16 状态一致性（read-only；非 PG 环境 skip）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_real_db_state_is_consistent():
    """对真实数据库做只读状态核验：applied ⊆ dir、无失败记录 → 一致，可算下一可用 V。

    这是 design §8.1「先调 migration status + 扫描目录、不一致即停」的可执行守卫。
    """
    from sqlalchemy import text

    from app.core.database import engine

    if engine.dialect.name != "postgresql":
        pytest.skip("状态一致性核验需真实 PostgreSQL（read-only）")

    async with engine.begin() as conn:
        applied_rows = await conn.execute(text("SELECT version FROM schema_version"))
        applied = {str(normalize_version(r[0])) for r in applied_rows.fetchall()}
        fail_rows = await conn.execute(
            text("SELECT version FROM schema_migration_failures")
        )
        failures = {str(normalize_version(r[0])) for r in fail_rows.fetchall()}

    filenames = [p.name for p in MIGRATIONS_DIR.glob("V*.sql")]
    report: MigrationStateReport = analyze_migration_state(filenames, applied, failures)

    # pending（目录 > DB）是 benign，不阻断；但 applied-missing / failure / dup 阻断。
    assert report.is_consistent, (
        "迁移状态不一致，停止实施并人工解决：\n" + "\n".join(report.blocking_reasons)
    )
    assert report.next_available is not None
    assert report.next_available == report.dir_highest + 1
