"""PG SQL 软删守卫（需求 17.3；spec formula-hub-integrity-closure 任务 40）。

扫描 ``tests/formula_hub/*_pg.py`` 与 ``gold_report_evaluator.py`` 中的原生 SQL 文本（``text(...)``
的参数与多行字符串里的 SQL），断言每条引用 ``is_deleted`` 列的表都带有 ``is_deleted`` 条件。
附违规样本自检：一条 **故意缺少** ``is_deleted`` 条件的 SQL 必须被守卫检出。
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_TARGETS = sorted(_HERE.glob("*_pg.py")) + [_HERE / "gold_report_evaluator.py"]


def _extract_sql_literals(source: str) -> list[tuple[int, str]]:
    """从 Python 源码里提取 ``text(...)`` 调用的字符串参数与 ``\"\"\"...SELECT...\"\"\"`` 多行字符串。

    返回 ``(起始行号, SQL 文本)`` 列表。
    """
    results: list[tuple[int, str]] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        # text("SELECT ...")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "text":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    results.append((arg.lineno, arg.value))
                elif isinstance(arg, ast.JoinedStr):
                    # f-string inside text(): reconstruct with placeholders
                    parts = []
                    for v in arg.values:
                        if isinstance(v, ast.Constant):
                            parts.append(str(v.value))
                        else:
                            parts.append("{...}")
                    results.append((arg.lineno, "".join(parts)))
        # Multiline strings containing SELECT (heuristic)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 40:
            upper = node.value.upper()
            if "SELECT" in upper and "FROM" in upper:
                results.append((node.lineno, node.value))
    return results


# 已知的表名模式（带 is_deleted 列的表）
_SOFT_DELETE_TABLES = re.compile(
    r"\b(?:projects|working_paper|wp_index|attachments|formula_setting|formula_sync_item"
    r"|report_config|financial_report|formula_template|formula_publish"
    r"|wp_formula|trial_balance|audit_log_entries)\b",
    re.IGNORECASE,
)

# 检查 SQL 里的 FROM/JOIN 后面的表名
_FROM_TABLE = re.compile(
    r"(?:FROM|JOIN)\s+(\w+)", re.IGNORECASE,
)

# is_deleted 条件模式
_IS_DELETED_COND = re.compile(
    r"is_deleted\s*(?:=|IS)\s*(?:false|FALSE|true|TRUE|:?\w+)|NOT\s+\w+\.is_deleted|\bis_deleted\b",
    re.IGNORECASE,
)

# 已知合法的测试夹具 SQL（读/写受控测试数据，不需要 is_deleted 条件）→ (文件名, 表名, 行为说明)
_KNOWN_FIXTURE_SQL: set[tuple[str, str]] = {
    ("test_attachment_lineage_isolation_pg.py", "attachments"),   # 读刚创建的附件 file_name
    ("test_attachment_lineage_migration_pg.py", "attachments"),   # 孤儿计数（刻意查全部）
    ("test_pending_revision_concurrency_pg.py", "formula_sync_item"),  # 读受控夹具的全部行
    ("test_report_false_fresh_guard_pg.py", "trial_balance"),     # 复制试算表行做测试夹具
}


def _check_sql(sql: str) -> list[str]:
    """返回 SQL 中引用了带 ``is_deleted`` 列的表、但未带 ``is_deleted`` 条件的违规表名列表。"""
    # 找出 FROM/JOIN 后面的表名
    tables_in_sql = {m.group(1).lower() for m in _FROM_TABLE.finditer(sql)}
    # 哪些表有 is_deleted 列
    soft_delete_tables = {t for t in tables_in_sql if _SOFT_DELETE_TABLES.search(t)}
    if not soft_delete_tables:
        return []
    # 检查是否有 is_deleted 条件
    if _IS_DELETED_COND.search(sql):
        return []
    return sorted(soft_delete_tables)


# ─── 违规样本自检 ─────────────────────────────────────────────────────────────

_VIOLATION_SAMPLE = "SELECT id, name FROM projects WHERE client_name = 'test'"
_CLEAN_SAMPLE = "SELECT id, name FROM projects WHERE is_deleted = false AND client_name = 'test'"


def test_violation_sample_is_detected() -> None:
    """守卫必须能检出违规样本（故意缺少 ``is_deleted`` 的 SQL）。"""
    violations = _check_sql(_VIOLATION_SAMPLE)
    assert "projects" in violations, f"违规样本未被检出：{violations}"


def test_clean_sample_passes() -> None:
    """带 ``is_deleted`` 条件的 SQL 不应被检出。"""
    violations = _check_sql(_CLEAN_SAMPLE)
    assert violations == [], f"合规样本被误报：{violations}"


def test_known_fixture_sql_still_exist() -> None:
    """已知夹具豁免条目不得失效（文件或 SQL 被删时条目变陈旧）。"""
    for path in _TARGETS:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        sqls = _extract_sql_literals(source)
        flagged_tables: set[str] = set()
        for _, sql in sqls:
            flagged_tables.update(_check_sql(sql))
        for fname, table in list(_KNOWN_FIXTURE_SQL):
            if fname == path.name and table not in flagged_tables:
                pytest.fail(f"_KNOWN_FIXTURE_SQL 条目 ({fname!r}, {table!r}) 已不再被检出，请删除")


# ─── 主守卫 ──────────────────────────────────────────────────────────────────


def test_pg_sql_excludes_soft_deleted() -> None:
    """扫描 ``tests/formula_hub/*_pg.py`` 与 ``gold_report_evaluator.py`` 中的 SQL，
    断言引用带 ``is_deleted`` 列的表时都带 ``is_deleted`` 条件。
    """
    all_violations: list[str] = []
    scanned = 0
    for path in _TARGETS:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        sqls = _extract_sql_literals(source)
        scanned += len(sqls)
        for lineno, sql in sqls:
            violations = _check_sql(sql)
            for table in violations:
                if (path.name, table) in _KNOWN_FIXTURE_SQL:
                    continue
                all_violations.append(f"{path.name}:{lineno} 表 [{table}] 缺 is_deleted 条件")
    assert scanned > 0, f"未扫描到 SQL：目标文件 {[p.name for p in _TARGETS]}"
    assert all_violations == [], (
        f"以下 SQL 引用了带 is_deleted 列的表但未排除软删行：\n" + "\n".join(all_violations)
    )
