"""迁移分句：UTF-8 BOM 与引号内分号（2026-11-03 共享库 V236 / V248 / V249 三条迁移失败的根因）。

- V248 / V249 文件以 BOM 开头，第一条语句带着 \\ufeff 送进 PG ⇒ syntax error at or near "\\ufeff"；
- V236 的 ``COMMENT ... IS '…; …'`` 在字符串里的分号处被切开 ⇒ unterminated quoted string。

执行器失败后「继续后续迁移」，所以这三条在共享库静默缺失（formula_push_state.provenance /
note_formula_run / ai_chat_runs.context_request_snapshot），读写它们的功能整体报错。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.migration_runner import MigrationRunner

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
split = MigrationRunner._split_sql_statements


def test_leading_bom_is_not_sent_to_the_database():
    stmts = split("\ufeff-- 注释\nALTER TABLE t ADD COLUMN IF NOT EXISTS c JSONB NULL;\n")
    assert stmts == ["-- 注释\nALTER TABLE t ADD COLUMN IF NOT EXISTS c JSONB NULL"]


def test_semicolon_inside_string_literal_does_not_split():
    sql = "COMMENT ON COLUMN t.c IS\n    'IDs for restart recovery; no content';\nSELECT 1;\n"
    assert split(sql) == ["COMMENT ON COLUMN t.c IS\n    'IDs for restart recovery; no content'", "SELECT 1"]


def test_doubled_quote_is_an_escape_not_a_terminator():
    assert split("SELECT 'it''s; fine';SELECT 2;") == ["SELECT 'it''s; fine'", "SELECT 2"]


def test_escape_string_backslash_quote_stays_inside_literal():
    assert split("SELECT E'a\\'; b';SELECT 3;") == ["SELECT E'a\\'; b'", "SELECT 3"]
    # 普通字符串里反斜杠不是转义（standard_conforming_strings=on）：'C:\' 在第二个引号处结束
    assert split("SELECT 'C:\\';SELECT 4;") == ["SELECT 'C:\\'", "SELECT 4"]
    # 标识符尾字母 e 不是 E'' 前缀
    assert split("SELECT name'x\\';SELECT 5;") == ["SELECT name'x\\'", "SELECT 5"]


def test_semicolon_inside_quoted_identifier_does_not_split():
    assert split('CREATE TABLE "we;ird" (id int);SELECT 6;') == ['CREATE TABLE "we;ird" (id int)', "SELECT 6"]


def test_quotes_inside_comments_and_dollar_blocks_do_not_open_a_literal():
    sql = (
        "-- it's a comment; still a comment\n"
        "/* don't ; split */ SELECT 7;\n"
        "DO $$ BEGIN RAISE NOTICE 'x; y'; END $$;\n"
        "SELECT 8;\n"
    )
    stmts = split(sql)
    assert len(stmts) == 3
    assert stmts[1] == "DO $$ BEGIN RAISE NOTICE 'x; y'; END $$"
    assert stmts[2] == "SELECT 8"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("V236__ai_chat_run_context_request_snapshot.sql", 2),
        ("V248__formula_push_provenance.sql", 1),
        ("V249__note_formula_runs.sql", 2),
    ],
)
def test_real_files_that_failed_on_the_shared_database(name: str, expected: int):
    stmts = split((MIGRATIONS / name).read_text(encoding="utf-8"))
    assert len(stmts) == expected
    assert not any(s.startswith("\ufeff") for s in stmts)
    if name.startswith("V236"):
        assert stmts[1].rstrip().endswith("no content or permission claims'")


def test_no_migration_statement_starts_with_bom_or_ends_inside_a_literal():
    """全量：每个 V / R 文件分句后没有以 BOM 开头的语句，也没有吞到文件尾的未闭合字符串。"""
    offenders: list[str] = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        stmts = split(path.read_text(encoding="utf-8"))
        if any(s.startswith("\ufeff") for s in stmts):
            offenders.append(f"{path.name}: BOM")
        # 语句若停在未闭合的字符串 / 标识符 / 块注释 / 美元引号里，补上的分号会被吞掉、分不出第二条
        for s in stmts:
            if split(s + "\n;\nSELECT 1;") != [s, "SELECT 1"]:
                offenders.append(f"{path.name}: 未闭合引号 {s[:60]!r}")
                break
    assert offenders == []
