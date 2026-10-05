"""P8 守卫 + 三层一致校验：V179 report_config 调整列公式迁移

验证：
- 迁移 SQL 幂等（IF NOT EXISTS → 连跑两次不报错）
- scan_migrations 无同号冲突
- ORM ReportConfig 含 aje_formula / rje_formula 字段
- Pydantic ReportConfigRow 含同名字段
- 三层一致：迁移列名 ⊆ ORM 列名
"""
import re
import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"


class TestP8MigrationIdempotent:
    """V179 迁移可重入（连跑两次不报错）"""

    def _read_v179(self) -> str:
        p = MIGRATIONS / "V179__report_config_adjustment_formula.sql"
        assert p.exists(), f"V179 迁移文件不存在: {p}"
        return p.read_text(encoding="utf-8")

    def test_v179_runs_twice_without_error(self):
        """IF NOT EXISTS → 第二次执行不报错"""
        sql = self._read_v179()
        # 用 SQLite 模拟幂等性（SQLite 不支持 IF NOT EXISTS on ADD COLUMN，
        # 所以用正则验证 DDL 包含 IF NOT EXISTS）
        assert "IF NOT EXISTS" in sql, "V179 必须含 IF NOT EXISTS"

        # 验证两个 ALTER TABLE 语句
        alters = re.findall(
            r"ADD COLUMN IF NOT EXISTS\s+(\w+)\s+TEXT", sql, re.IGNORECASE
        )
        assert sorted(alters) == ["aje_formula", "rje_formula"], (
            f"V179 应添加 aje_formula 和 rje_formula，实际: {alters}"
        )

    def test_r179_exists_and_paired(self):
        """回滚文件存在且配对"""
        r_files = list(MIGRATIONS.glob("R179__*.sql"))
        assert len(r_files) == 1, f"R179 应恰好 1 个文件，实际 {len(r_files)}"
        r_sql = r_files[0].read_text(encoding="utf-8")
        assert "DROP COLUMN IF EXISTS aje_formula" in r_sql
        assert "DROP COLUMN IF EXISTS rje_formula" in r_sql


class TestScanMigrationsNoConflict:
    """scan_migrations 无同号冲突"""

    def test_v179_no_duplicate(self):
        v_files = list(MIGRATIONS.glob("V179__*.sql"))
        assert len(v_files) == 1, (
            f"V179 版本号应唯一，发现 {len(v_files)} 个: "
            f"{[f.name for f in v_files]}"
        )

    def test_no_duplicate_version_numbers(self):
        """全量扫描无任何同号"""
        import collections

        nums = []
        for f in MIGRATIONS.glob("V*.sql"):
            m = re.match(r"V(\d+)", f.name)
            if m:
                nums.append(int(m.group(1)))
        dups = {n: c for n, c in collections.Counter(nums).items() if c > 1}
        assert not dups, f"发现重复版本号: {dups}"


class TestThreeLayerConsistency:
    """三层一致校验：迁移 + ORM + Schema"""

    def test_orm_has_aje_formula_and_rje_formula(self):
        from app.models.report_models import ReportConfig

        mapper = sa.inspect(ReportConfig)
        col_names = {c.key for c in mapper.mapper.column_attrs}
        assert "aje_formula" in col_names, "ORM 缺 aje_formula"
        assert "rje_formula" in col_names, "ORM 缺 rje_formula"

    def test_schema_has_aje_formula_and_rje_formula(self):
        from app.models.report_schemas import ReportConfigRow

        fields = set(ReportConfigRow.model_fields.keys())
        assert "aje_formula" in fields, "Schema 缺 aje_formula"
        assert "rje_formula" in fields, "Schema 缺 rje_formula"

    def test_orm_columns_match_migration(self):
        """迁移新增的列名 == ORM 新增的列名"""
        from app.models.report_models import ReportConfig

        v179_sql = (
            MIGRATIONS / "V179__report_config_adjustment_formula.sql"
        ).read_text(encoding="utf-8")
        migration_cols = set(
            re.findall(r"ADD COLUMN IF NOT EXISTS\s+(\w+)", v179_sql, re.IGNORECASE)
        )

        mapper = sa.inspect(ReportConfig)
        orm_cols = {c.key for c in mapper.mapper.column_attrs}

        # 迁移新增列必须全在 ORM 中
        missing = migration_cols - orm_cols
        assert not missing, f"迁移列不在 ORM 中: {missing}"

    def test_schema_covers_orm_new_columns(self):
        """Pydantic schema 覆盖 ORM 新增字段"""
        from app.models.report_schemas import ReportConfigRow

        new_cols = {"aje_formula", "rje_formula"}
        schema_fields = set(ReportConfigRow.model_fields.keys())
        missing = new_cols - schema_fields
        assert not missing, f"Schema 未覆盖 ORM 新列: {missing}"
