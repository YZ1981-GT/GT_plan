"""disclosure_notes provenance 列 drift 0 测试（Phase 3 / 需求 2.1 / 属性 T6）.

本测试断言（迁移 V039 与 ORM 一致，无 drift）：
- ORM DisclosureNote 含 source_project_id + consolidation_breakdown 两个 Mapped 列
- V039 迁移 SQL 同时 ADD 这两列（+ GIN 索引）；R039 回滚 DROP 两列

读写这两列的 service（V2 汇总器写、「查看合并明细」读）已于 2026-10-22 随 V2 下线
（spec consol-note-header-library-and-node-reaggregate R6.1）：两列保留（真库 0 行有值），
现无读写方；合并附注个别数在 ``consol_note_data``，按已确认映射从单体附注拉取。

Validates: Requirements 2.1; Property T6 (迁移 / ORM drift 0).
"""
from __future__ import annotations

from pathlib import Path

from app.models.report_models import DisclosureNote

MIGRATIONS = Path(__file__).resolve().parent.parent.parent / "migrations"


def test_orm_has_provenance_columns():
    """ORM DisclosureNote 含 provenance 两列（第一层）。"""
    cols = set(DisclosureNote.__table__.columns.keys())
    assert "source_project_id" in cols
    assert "consolidation_breakdown" in cols


def test_v039_migration_adds_columns():
    """V039 迁移 SQL 同时 ADD source_project_id + consolidation_breakdown + GIN 索引（第二层）。"""
    v039 = MIGRATIONS / "V039__disclosure_notes_provenance.sql"
    assert v039.exists(), "V039 迁移文件缺失"
    sql = v039.read_text(encoding="utf-8").lower()
    assert "add column if not exists source_project_id" in sql
    assert "add column if not exists consolidation_breakdown" in sql
    assert "idx_disclosure_notes_consol_breakdown" in sql
    assert "gin" in sql  # GIN 索引支撑 provenance 查询


def test_r039_rollback_drops_columns():
    """R039 回滚 SQL DROP 两列 + 索引（幂等 IF EXISTS）。"""
    r039 = MIGRATIONS / "R039__disclosure_notes_provenance.sql"
    assert r039.exists(), "R039 回滚文件缺失"
    sql = r039.read_text(encoding="utf-8").lower()
    assert "drop column if exists consolidation_breakdown" in sql
    assert "drop column if exists source_project_id" in sql
    assert "drop index if exists idx_disclosure_notes_consol_breakdown" in sql


def test_v039_is_next_version_after_v038():
    """V039 是 V038 之后的下一个版本号（无撞号）。"""
    v038 = MIGRATIONS / "V038__seed_workpaper_template_version.sql"
    v039 = MIGRATIONS / "V039__disclosure_notes_provenance.sql"
    assert v038.exists()
    assert v039.exists()
    # 不存在 V039 的其他撞名文件
    v039_files = list(MIGRATIONS.glob("V039__*.sql"))
    assert len(v039_files) == 1, f"V039 撞号: {[f.name for f in v039_files]}"
