"""迁移改写报表定义时同一文件须标报表过期（spec formula-hub-integrity-closure 任务 15；需求 5.1 末句；ADR-FHIC-04）。

规则：版本号大于 :data:`SINCE`（205）的 ``backend/migrations/V*.sql`` 中，凡改写报表定义 —— ``UPDATE report_config`` 的
SET 子句给执行字段（报表域 ``exec_fields``：formula / aje_formula / rje_formula / formula_category）赋值，或任何
``INSERT INTO report_config`` —— 同一文件必须含 ``UPDATE financial_report SET … is_stale = true``。比对前去掉 ``--`` /
``/* */`` 注释、转小写、空白归一（注释里的语句不算）；SET 子句到顶层 ``WHERE`` / ``FROM`` / ``RETURNING`` 或 ``;`` 为止
（括号与字符串内的不算）。≤ V205 的历史迁移不追溯：V136 / V137 / V138 / V144 / V145 只改公式不标过期，存量由 D13-A
（计算版本为空即判过期）兜住。

自检：违规 / 合规样本（测试内构造文本；目录级样本写在 pytest 临时目录，不进 migrations 目录）；规则在真实历史迁移上
命中的恰是上面 5 个文件（V199 只回填 ``base_definition``，不算改写）。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.formula_settings.definitions import get_spec

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
SINCE = 205
EXEC_FIELDS = get_spec("report").exec_fields
_VERSION = re.compile(r"^V(\d+)__.+\.sql$")
_ALIAS = r"(?: (?:as )?(?!set\b)\w+)?"
_UPDATE_HEAD = re.compile(rf'\bupdate (?:only )?(?:public\.)?"?report_config"?{_ALIAS} set ')
_INSERT = re.compile(r'\binsert into (?:public\.)?"?report_config"?(?!\w)')
_ASSIGN = re.compile(r'(?<![\w.])(?:\w+\.)?"?(?:' + "|".join(EXEC_FIELDS) + r')"? ?=(?!=)')
_MARK = re.compile(rf'\bupdate (?:only )?(?:public\.)?"?financial_report"?{_ALIAS} set [^;]*?\bis_stale ?= ?true\b')
_SET_END = re.compile(r"'(?:[^']|'')*'|\(|\)|;|\b(?:where|from|returning)\b")


def normalize(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"\s+", " ", sql).strip().lower()


def _set_clause(tail: str) -> str:
    depth = 0
    for m in _SET_END.finditer(tail):
        token = m.group(0)
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(depth - 1, 0)
        elif token == ";" or (depth == 0 and not token.startswith("'")):
            return tail[:m.start()]
    return tail


def rewrites_report_config(sql: str) -> bool:
    text = normalize(sql)
    if _INSERT.search(text):
        return True
    return any(_ASSIGN.search(_set_clause(text[m.end():])) for m in _UPDATE_HEAD.finditer(text))


def marks_reports_stale(sql: str) -> bool:
    return bool(_MARK.search(normalize(sql)))


def violates(sql: str) -> bool:
    return rewrites_report_config(sql) and not marks_reports_stale(sql)


def scan(directory: Path = MIGRATIONS, since: int = SINCE) -> tuple[list[int], list[str]]:
    """返回（扫到的版本号，违规文件名）；只看版本号 > ``since`` 的 ``V*.sql``。"""
    versions, bad = [], []
    for path in sorted(directory.glob("V*.sql")):
        found = _VERSION.match(path.name)
        if not found or int(found.group(1)) <= since:
            continue
        versions.append(int(found.group(1)))
        if violates(path.read_bytes().decode("utf-8-sig")):
            bad.append(path.name)
    return versions, bad


def test_migrations_after_v205_that_rewrite_report_config_mark_reports_stale():
    versions, bad = scan()
    # 分母不空：本 spec 自己的迁移在扫描范围内（2026-10-29 重编号 V206~V208 → V218~V220；
    # 裸数字形态不带 V 前缀，两轮重编号的标识符 / 文件名扫描都没扫到，2026-10-30 补改；
    # 2026-10-31 合入分支头时 V218~V220 已被别的 spec 占用，再改为 V227~V229）
    assert {227, 228, 229} <= set(versions), versions
    assert bad == [], (f"这些迁移改写了 report_config 的报表定义却没有在同一文件把报表行标过期，"
                       f"请补 UPDATE financial_report SET is_stale = true …：{bad}")


#: 名称 → (SQL, 是否改写报表定义, 是否标了过期)
SAMPLES: dict[str, tuple[str, bool, bool]] = {
    "update_formula_unmarked": (
        "UPDATE report_config\n   SET formula = REPLACE(formula, '''1505''', '''1506'''),\n       updated_at = NOW()\n"
        " WHERE row_code = 'BS-022' AND formula LIKE '%1505%';", True, False),
    "update_formula_marked_mixed_case": (
        "Update Report_Config SET FORMULA = NULL WHERE row_code = 'BS-013';\n"
        "update   FINANCIAL_REPORT\n  set IS_STALE=TRUE\n where row_code = 'BS-013' and is_deleted = false;", True, True),
    "insert_unmarked": (
        "INSERT INTO public.report_config (report_type, row_code, row_name) VALUES ('balance_sheet', 'BS-999', 'x');",
        True, False),
    "aje_formula_alias_unmarked": (
        "UPDATE report_config AS rc SET aje_formula = 'ROW(''BS-001'')' FROM projects p "
        "WHERE rc.applicable_standard = 'project:' || p.id;", True, False),
    "mark_only_in_comment": (
        "UPDATE report_config SET formula_category = 'manual' WHERE row_code = 'BS-001';\n"
        "-- UPDATE financial_report SET is_stale = true;\n/* UPDATE financial_report SET is_stale = true; */", True, False),
    "insert_marked_after_other_column": (
        "INSERT INTO report_config (row_code) VALUES ('X');\n"
        "UPDATE financial_report fr SET updated_at = now(), is_stale = true WHERE fr.row_code = 'X';", True, True),
    "formula_only_in_where": (
        "UPDATE report_config SET row_name = '货币资金' WHERE formula IS NULL AND formula_category = 'auto_calc';",
        False, False),
    "base_definition_backfill": (
        "UPDATE report_config AS p SET base_version = g.formula_version, base_definition = jsonb_build_object("
        "'formula', COALESCE(g.formula, '')) FROM report_config AS g WHERE p.row_code = g.row_code;", False, False),
    "rewrite_only_in_comment": (
        "-- UPDATE report_config SET formula = NULL;\n/* INSERT INTO report_config VALUES (1); */\nSELECT 1;", False, False),
    "other_tables": (
        "UPDATE report_config_candidates SET formula = NULL;\nINSERT INTO report_config_history VALUES (1);",
        False, False),
}
VIOLATING = {"update_formula_unmarked", "insert_unmarked", "aje_formula_alias_unmarked", "mark_only_in_comment"}


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_rule_on_samples(name):
    sql, rewrites, marked = SAMPLES[name]
    assert (rewrites_report_config(sql), marks_reports_stale(sql)) == (rewrites, marked)
    assert violates(sql) is (name in VIOLATING)


def test_samples_cover_both_verdicts():
    assert {name for name, (sql, _, _) in SAMPLES.items() if violates(sql)} == VIOLATING
    assert set(SAMPLES) - VIOLATING, "须同时有合规样本"


def test_scan_on_sample_directory(tmp_path):
    """目录级自检：版本号过滤（≤ 205 不看）、按文件判定、BOM 文件可读。"""
    files = {
        "V100__old_rewrite.sql": SAMPLES["update_formula_unmarked"][0],
        "V998__marked.sql": SAMPLES["update_formula_marked_mixed_case"][0],
        "V999__unmarked.sql": "\ufeff" + SAMPLES["insert_unmarked"][0],
        "R999__rollback.sql": SAMPLES["insert_unmarked"][0],
    }
    for name, text in files.items():
        (tmp_path / name).write_bytes(text.encode("utf-8"))
    assert scan(tmp_path) == ([998, 999], ["V999__unmarked.sql"])


def test_rule_on_real_history():
    """规则在真实历史迁移上命中的恰是只改公式的 5 个文件，且它们都没有标过期（≤ V205 不追溯）。"""
    flagged = {}
    for path in sorted(MIGRATIONS.glob("V*.sql")):
        found = _VERSION.match(path.name)
        if found and int(found.group(1)) <= SINCE:
            sql = path.read_bytes().decode("utf-8-sig")
            if rewrites_report_config(sql):
                flagged[int(found.group(1))] = marks_reports_stale(sql)
    assert flagged == {136: False, 137: False, 138: False, 144: False, 145: False}
