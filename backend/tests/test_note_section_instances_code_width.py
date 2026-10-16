"""附注裁剪页章节实例表的编号宽度（disclosure-note-template-word-realignment Phase 3，design §4.1 第 6 项）。

裁剪页首次打开时 ``NoteTrimService._init_from_sections`` 把按报告口径过滤后的**全部**种子章节写进
``note_section_instances``。种子里不带数字序号的叙述性章节以标题作编号（现算最长 42 字），旧列宽 VARCHAR(20)
放不下 ⇒ PostgreSQL 报 22001、整页初始化失败。SQLite 不校验 VARCHAR 长度，所以这里钉 ORM 声明与迁移文件；
真库行为（V188 前 22001 / 后写入成功 / R188 拒绝截断）由 ``test_note_section_instances_v188_pg.py`` 守。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.migration_runner import MigrationRunner
from app.models.note_trim_models import NoteSectionInstance
from app.services.note_section_catalog import filter_template_sections

_BACKEND = Path(__file__).resolve().parents[1]
MIGRATIONS = _BACKEND / "migrations"
V188 = MIGRATIONS / "V188__note_section_instances_section_number_unbounded.sql"
R188 = MIGRATIONS / "R188__note_section_instances_section_number_unbounded.sql"


def _seed_codes(standard: str, scope: str | None) -> list[str]:
    data = json.loads((_BACKEND / "data" / f"note_template_{standard}.json").read_text(encoding="utf-8-sig"))
    return [s.get("section_number", "") for s in filter_template_sections(data.get("sections", []), scope)]


@pytest.mark.parametrize("standard", ["soe", "listed"])
@pytest.mark.parametrize("scope", ["standalone", "consolidated", None])
def test_orm_section_number_holds_every_seed_code(standard: str, scope: str | None) -> None:
    """裁剪页写入的是口径过滤后的全部种子章节：ORM 列宽（None = 不限长）必须放得下其中最长的编号。"""
    codes = _seed_codes(standard, scope)
    assert codes, "种子为空：判据会空转"
    length = NoteSectionInstance.__table__.c.section_number.type.length
    longest = max(codes, key=len)
    assert length is None or length >= len(longest), f"列宽 {length} 放不下 {len(longest)} 字的 {longest}"


def test_seed_really_has_codes_longer_than_old_width() -> None:
    """反向断言：种子里确有超过旧列宽 20 的编号，上一条判据才不是空转（全部 ≤20 时它对 VARCHAR(20) 也绿）。"""
    longest = max(len(c) for std in ("soe", "listed") for scope in ("standalone", "consolidated")
                  for c in _seed_codes(std, scope))
    assert longest > 20


def test_v188_is_unique_and_has_rollback_pair() -> None:
    runner = MigrationRunner(database_url="sqlite+aiosqlite:///:memory:", migrations_dir=MIGRATIONS)
    assert [m.filename for m in runner.scan_migrations() if int(m.version) == 188] == [V188.name]
    assert [m.filename for m in runner.scan_rollback_scripts() if int(m.version) == 188] == [R188.name]


def test_v188_widens_and_r188_restores_with_guard() -> None:
    """两份脚本各是一个 DO 块：V188 只在列仍有上限时放宽为不限长；R188 只在已放宽时恢复，且有超长行即报错不截断。"""
    v = MigrationRunner._split_sql_statements(V188.read_text(encoding="utf-8"))
    r = MigrationRunner._split_sql_statements(R188.read_text(encoding="utf-8"))
    assert len(v) == 1 and len(r) == 1
    assert "character_maximum_length IS NOT NULL" in v[0]
    assert "ALTER COLUMN section_number TYPE VARCHAR;" in v[0]
    assert "character_maximum_length IS NULL" in r[0]
    assert "RAISE EXCEPTION" in r[0] and "length(section_number) > 20" in r[0]
    assert "ALTER COLUMN section_number TYPE VARCHAR(20);" in r[0]
