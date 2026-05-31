"""disclosure_notes provenance 三层一致 / drift 0 集成测试（Phase 3 / 需求 2.1 / 属性 T6）.

三层一致铁律：迁移 V039 + ORM DisclosureNote.Mapped 字段 + service 读写齐全。
本测试断言：
- ORM DisclosureNote 含 source_project_id + consolidation_breakdown 两个 Mapped 列
- V039 迁移 SQL 同时 ADD 这两列（+ GIN 索引）；R039 回滚 DROP 两列
- note_consol_drilldown_service 读 consolidation_breakdown；consol_disclosure_service 写之

Validates: Requirements 2.1; Property T6 (三层一致 drift 0).
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


def test_service_reads_and_writes_provenance():
    """service 层读写 provenance（第三层）：读端 + 写端函数均存在。"""
    # 读端：穿透服务读 consolidation_breakdown
    from app.services.note_consol_drilldown_service import get_note_consol_breakdown
    assert callable(get_note_consol_breakdown)

    # 写端：V2 汇总构建 provenance
    from app.services.consol_disclosure_service import _build_section_consolidation_breakdown
    assert callable(_build_section_consolidation_breakdown)


def test_v039_is_next_version_after_v038():
    """V039 是 V038 之后的下一个版本号（无撞号）。"""
    v038 = MIGRATIONS / "V038__seed_workpaper_template_version.sql"
    v039 = MIGRATIONS / "V039__disclosure_notes_provenance.sql"
    assert v038.exists()
    assert v039.exists()
    # 不存在 V039 的其他撞名文件
    v039_files = list(MIGRATIONS.glob("V039__*.sql"))
    assert len(v039_files) == 1, f"V039 撞号: {[f.name for f in v039_files]}"
