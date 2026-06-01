"""列级契约测试（pg_only + sqlglot）：裸 SQL 中 `别名.列` 引用 ⊆ 真实 PG 表的列。

**为什么需要**：表级契约（test_raw_sql_schema_contract）只防「查不存在的表」，
但连续多轮 500 中**过半是「查不存在的列」**（users.display_name /
issue_tickets.is_deleted / Adjustment.entry_number / trial_balance.closing_balance
/ DisclosureNote.section_code 等）。纯静态解析无法把 `SELECT a,b,c` 的每列归到
具体表，故本测试需 **live PG**（标 pg_only，CI 的 backend-tests job 连真实 PG 跑）：
用 sqlglot 解析裸 SQL → 解析 FROM/JOIN 的表别名映射 → 校验每个 `别名.列`
引用的列在该真实表中存在。

只校验**带别名限定**的列引用（`t.col`），无限定列无法可靠归属故跳过（保守，零误报优先）。

**Validates**: GET 巡检复盘元反思「CI SQL 列引用 ⊆ 真实 schema 契约检查」（列级补全）
"""

from __future__ import annotations

import asyncio
import os

import pytest

# 复用表级契约测试的源码扫描 helper
from tests.test_raw_sql_schema_contract import (
    _iter_python_files,
    _extract_sql_strings,
    REPO_ROOT,
)

pytestmark = pytest.mark.pg_only

# 列引用校验白名单：以下「别名.列」即使不在 schema 也不报。
# 仅限「已确认运行时有守卫(try/except 或列存在性检查)且对应功能 schema 从未建」的存量债务，
# 或 PG 计算列/函数别名。每条须注明原因，修复后删除。
_COLUMN_ALLOWLIST: set[str] = {
    # QC-19/QC-20 程序裁剪治理（gate_rules_phase14）：真实 ProcedureInstance 只有
    # status='skip'/skip_reason/wp_id，无 trim_category(mandatory/conditional)/
    # trim_status/trim_evidence_refs 这套粒度——该治理功能 schema 从未建，规则被
    # try/except 守卫不会 500（静默跳过）。属功能缺失债务，非简单改名可修，登记待专项。
    "procedure_instances.working_paper_id",
    "procedure_instances.trim_category",
    "procedure_instances.trim_status",
    "procedure_instances.trim_evidence_refs",
    "procedure_instances.name",
    # QC-26 附注关键披露来源映射（gate_rules_phase14）：disclosure_notes 无
    # is_key_disclosure/source_cells 列，已加运行时「列存在性检查」守卫(cols_exist<2 跳过)
    # 不会 500。该披露治理 schema 未建，属债务。
    "disclosure_notes.is_key_disclosure",
    "disclosure_notes.source_cells",
    "disclosure_notes.title",  # QC-26 同段，真实列是 section_title；整段已守卫为债务
}


def _load_pg_schema_sync() -> dict[str, set[str]]:
    """连真实 PG（复用项目 asyncpg/SQLAlchemy 栈），返回 {表名: {列名}}（全小写）。"""
    from sqlalchemy import text
    from app.core.database import async_session

    async def _load() -> dict[str, set[str]]:
        schema: dict[str, set[str]] = {}
        async with async_session() as db:
            rows = (await db.execute(text("""
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
            """))).fetchall()
        for tbl, col in rows:
            schema.setdefault(tbl.lower(), set()).add(col.lower())
        return schema

    return asyncio.run(_load())


def _check_sql_columns(sql: str, schema: dict[str, set[str]]) -> list[str]:
    """解析单条 SQL，返回违规的 `别名.列` 列表（列在真实表中不存在）。"""
    import sqlglot
    from sqlglot import exp

    try:
        trees = sqlglot.parse(sql, read="postgres")
    except Exception:
        return []  # 解析失败（含 :param 占位/动态拼接）→ 跳过，不误报

    violations: list[str] = []
    for tree in trees:
        if tree is None:
            continue
        for scope_sql in [tree]:
            # 别名 → 真实表名（仅收 FROM/JOIN 的实体表，排除子查询/CTE）
            alias_to_table: dict[str, str] = {}
            cte_names = {
                c.alias_or_name.lower()
                for c in scope_sql.find_all(exp.CTE)
            }
            for tbl in scope_sql.find_all(exp.Table):
                name = (tbl.name or "").lower()
                if not name or name in cte_names:
                    continue
                alias = (tbl.alias or tbl.name or "").lower()
                alias_to_table[alias] = name

            # 遍历所有带限定的列引用 alias.col
            for col in scope_sql.find_all(exp.Column):
                tbl_alias = (col.table or "").lower()
                col_name = (col.name or "").lower()
                if not tbl_alias or not col_name:
                    continue
                real_table = alias_to_table.get(tbl_alias)
                if real_table is None:
                    continue  # 别名指向子查询/CTE/未知 → 跳过
                if real_table not in schema:
                    continue  # 表本身不存在 → 由表级测试/ phantom 债务覆盖
                if col_name == "*":
                    continue
                if col_name not in schema[real_table]:
                    key = f"{real_table}.{col_name}"
                    if key not in _COLUMN_ALLOWLIST:
                        violations.append(key)
    return violations


def test_raw_sql_qualified_columns_exist_in_pg():
    """裸 SQL 中每个 `别名.列` 引用的列都必须存在于对应真实 PG 表。

    失败即意味着某处裸 SQL 查了不存在的列 —— 运行时必 UndefinedColumn 500
    （且会污染 PG 事务致后续查询级联崩）。
    """
    schema = _load_pg_schema_sync()
    assert len(schema) > 50, f"PG schema 表数异常少（{len(schema)}），疑连库失败"

    findings: dict[str, set[str]] = {}  # 违规列 -> 文件集
    for fpath in _iter_python_files():
        try:
            source = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(fpath.relative_to(REPO_ROOT))
        for sql in _extract_sql_strings(source):
            for bad in _check_sql_columns(sql, schema):
                findings.setdefault(bad, set()).add(rel)

    assert not findings, (
        "发现裸 SQL 引用了真实 PG 表中不存在的列（运行时会 UndefinedColumn 500）：\n"
        + "\n".join(
            f"  🔴 {col}\n     引用于: {sorted(files)}"
            for col, files in sorted(findings.items())
        )
        + "\n\n修复：改正列名 / 补迁移加列；若为 PG 计算列误判，加入 _COLUMN_ALLOWLIST。"
    )
