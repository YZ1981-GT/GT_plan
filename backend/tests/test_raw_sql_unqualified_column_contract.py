"""裸 SQL「无限定列」契约（pg_only + sqlglot）—— deliverable-writeback-and-online-edit-integrity US-7。

**为什么需要**：`test_raw_sql_column_contract` 只校验**带别名限定**的列（`t.col`），
而连续多轮 500 里有一类是**无限定列**查错表 / 查不存在列（`SELECT output_path FROM export_tasks`
真名 file_path；`FROM trial_balance ... debit_amount` 真名在 tb_balance）。本守卫补这一类：

对每个 SELECT/UPDATE/DELETE/INSERT 作用域，**仅当**该作用域只有一张实体表、无子查询 / CTE 时
（否则无限定列无法可靠归属 ⇒ 跳过，保守零误报），校验无限定列 ∈ 该表真实列。
`INSERT INTO t (cols)` 的列同样校验。表名 ∉ 真库 ⇒ 记「幽灵表」（不计列违规）。

**排除**（否则假阳）：
- f-string 插值 `{var}`：Python 变量名注入进 SQL 后被 sqlglot 当列（如 `IN ({placeholders})`）；
- SELECT 列表**显式 AS 别名**（`expr AS name`，裸列不排除）；
- `information_schema.* / pg_catalog.*` 系统 schema 表；
- PG 伪列 / 系统列 / 字面量关键字。

**基线**：`_UNQUALIFIED_BASELINE`（列键 → 引用文件集）。断言两向：
1. 现算违规 ⊆ 基线（新增即红）；
2. 基线每条仍真实出现（修复后必删，防基线腐烂）。

每条基线项的「活 / 死」判定见 design §6 / §10：绝大多数在 `try/except` 守卫下降级（不 500 但功能静默失效），
或在死代码 / pgvector 条件路径里。已修的活路径（export_tasks 下载 500 / eqcr 影子计算借贷表 / wp 质量看板死列）
不在基线中——修一条删一条。

**Validates**: US-7（裸 SQL 无限定列契约），GET 巡检复盘元反思「SQL 列引用 ⊆ 真实 schema」。
"""

from __future__ import annotations

import asyncio
import re

import pytest

from tests.test_raw_sql_schema_contract import (
    _iter_python_files,
    _extract_sql_strings,
    REPO_ROOT,
)

pytestmark = pytest.mark.pg_only

# ── f-string 插值名：{name} / {name.attr} / {name[...]} 的首段标识符（Python 变量，非列）
_BRACE_RE = re.compile(r"\{\s*([a-zA-Z_][a-zA-Z0-9_]*)")

# ── PG 伪列 / 系统列 / 字面量（无限定出现时不校验）
_PSEUDO_COLS = {
    "ctid", "oid", "tableoid", "xmin", "xmax", "cmin", "cmax",
    "current_date", "current_timestamp", "now", "true", "false", "null",
}

# ── 系统 schema：带此 schema 限定的表不是业务实体表
_SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "pg_temp"}


# ─────────────────────────────────────────────────────────────────────────────
# 基线：现存「无限定列」违规（列键 → 引用文件集，路径用正斜杠）。
# 全部为**守卫路径 / 死代码 / pgvector 条件路径**（不 500，但功能静默失效），
# 修复需按真库 schema 重写查询（多属功能语义层改动，超本 spec 范围）。逐条见 design §10。
# 修复任意一条后：现算会少一条 ⇒ 第 2 向断言打红 ⇒ 必须从本基线删除对应项。
# ─────────────────────────────────────────────────────────────────────────────
_UNQUALIFIED_BASELINE: dict[str, set[str]] = {
    # projects 无 audit_report_date / balance_sheet_date（真有 client_name / audit_period_end）；
    # A8-1 / A1-11 render strategy 在 try/except 内降级为默认值（不 500）。
    # （原 projects.industry 一项随 H5 行业检查一并删除：那处其实没有 try/except、每次必 500 ——
    #   spec trim-followup-residual-findings-closure R1.3）
    "projects.audit_report_date": {
        "backend/app/routers/wp_render_strategies/_a81_other_info_representation.py",
    },
    "projects.balance_sheet_date": {
        "backend/app/routers/wp_render_strategies/_a111_subsequent_events_inquiry.py",
    },
    # checklist_responses 无 value / content 列（真实载荷在 remark JSON）；对应 import/export 与 M 系列
    # 服务查询在 try/except 守卫下降级。
    "checklist_responses.value": {
        "backend/app/routers/wp_render_strategies/_e0_send_list.py",
        "backend/app/services/m1_dividends_payable_service.py",
        "backend/app/services/m2_paid_in_capital_service.py",
        "backend/app/services/m6_retained_earnings_service.py",
    },
    "checklist_responses.content": {
        "backend/app/routers/wp_render_strategies/_j2_import_export.py",
    },
    # linkage_service：working_paper 无 wp_code / wp_name（在 wp_index）；trial_balance 无 row_code / row_name。
    # 该服务查询在 try/except 守卫下降级（联动提示缺失，不 500）。
    "working_paper.wp_code": {"backend/app/services/linkage_service.py"},
    "working_paper.wp_name": {"backend/app/services/linkage_service.py"},
    "trial_balance.row_code": {"backend/app/services/linkage_service.py"},
    "trial_balance.row_name": {"backend/app/services/linkage_service.py"},
    # note_ai_assistant：tb_balance 无 aux_* / audited_amount（aux 在 tb_aux_balance、审定数在 trial_balance，
    # 且键名为 standard_account_code）。两处查询均 try/except 返回 None（一致性校核静默不出结果）。
    # 语义层修复需厘清 binding 的 account_code 命名空间，超本 spec 范围。
    "tb_balance.aux_type": {"backend/app/services/note_ai_assistant_service.py"},
    "tb_balance.aux_code": {"backend/app/services/note_ai_assistant_service.py"},
    "tb_balance.aux_name": {"backend/app/services/note_ai_assistant_service.py"},
    "tb_balance.audited_amount": {"backend/app/services/note_ai_assistant_service.py"},
    # audit_log_entries 无 action / created_at / details（真实审计链在 app_audit_log / trace_events）；
    # wp_audit_trail / procedure_trim_engine 的查询在 try/except 守卫下降级。
    "audit_log_entries.action": {"backend/app/services/wp_audit_trail_service.py"},
    "audit_log_entries.created_at": {
        "backend/app/services/procedure_trim_engine.py",
        "backend/app/services/wp_audit_trail_service.py",
    },
    "audit_log_entries.details": {"backend/app/services/wp_audit_trail_service.py"},
    # workpaper_snapshots 真名 workpaper_id / data_json / snapshot_type（无 wp_id / snapshot_data / trigger_event）；
    # search_versions 的调用方 wp_version_search 路由在 try/except 守卫下降级（版本搜索静默返回空）。
    "workpaper_snapshots.wp_id": {"backend/app/services/wp_version_search_service.py"},
    "workpaper_snapshots.snapshot_data": {"backend/app/services/wp_version_search_service.py"},
    "workpaper_snapshots.trigger_event": {"backend/app/services/wp_version_search_service.py"},
    # knowledge_index 原生 vector 列 `embedding` 仅在 pgvector 扩展 + V043 落地后存在（真库未 CREATE EXTENSION）；
    # PgVectorStore 仅当 VECTOR_STORE_BACKEND 选中且扩展可用时才走此路径，否则降级 PgTextStore（embedding_vector 文本列）。
    "knowledge_index.embedding": {"backend/app/services/vector_store.py"},
}

# 幽灵表基线（表名 ∉ 真库，均由 EXISTS / 列存在性守卫先行拦截 ⇒ 不 500）。
_GHOST_TABLE_BASELINE: dict[str, set[str]] = {
    # wp_template_registry 表从未建；两处访问前都先 `SELECT EXISTS(information_schema.tables ...)` 判存在。
    "wp_template_registry": {
        "backend/app/routers/custom_query.py",
        "backend/app/services/wp_template_registry.py",
    },
}


# ─── 检测逻辑（与 Phase E 现算探针逐字一致）────────────────────────────────────


def _brace_names(sql: str) -> set[str]:
    return {m.group(1).lower() for m in _BRACE_RE.finditer(sql)}


def _load_pg_schema_sync() -> dict[str, set[str]]:
    from sqlalchemy import text
    from app.core.database import async_session

    async def _load() -> dict[str, set[str]]:
        schema: dict[str, set[str]] = {}
        async with async_session() as db:
            rows = (await db.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema='public'"
            ))).fetchall()
        for tbl, col in rows:
            schema.setdefault(tbl.lower(), set()).add(col.lower())
        return schema

    from tests._pg_shared_engine import run_and_dispose

    return asyncio.run(run_and_dispose(_load()))  # 用完释放共享连接池（见 tests/_pg_shared_engine.py）


def _entity_tables(stmt) -> dict[str, str]:
    """作用域 FROM/JOIN 的实体表 {alias: table}，排除 CTE 与系统 schema 表。"""
    from sqlglot import exp

    cte_names = {c.alias_or_name.lower() for c in stmt.find_all(exp.CTE)}
    out: dict[str, str] = {}
    for tbl in stmt.find_all(exp.Table):
        name = (tbl.name or "").lower()
        schema = (tbl.db or "").lower()
        if not name or name in cte_names or schema in _SYSTEM_SCHEMAS:
            continue
        alias = (tbl.alias or tbl.name or "").lower()
        out[alias] = name
    return out


def _has_subquery_or_cte(stmt) -> bool:
    from sqlglot import exp

    return bool(list(stmt.find_all(exp.CTE)) or list(stmt.find_all(exp.Subquery)))


def _explicit_aliases(stmt) -> set[str]:
    """SELECT 列表的**显式** AS 别名（裸列不算，避免 over-exclude）。"""
    from sqlglot import exp

    out: set[str] = set()
    sel = stmt.find(exp.Select)
    if sel is None:
        return out
    for proj in sel.expressions:
        if isinstance(proj, exp.Alias) and proj.alias:
            out.add(proj.alias.lower())
    return out


def _check_stmt(stmt, schema, brace_names, ghosts) -> list[tuple[str, str]]:
    """返回该语句的无限定列违规 [(table, col)]；顺带把幽灵表记入 ghosts。"""
    from sqlglot import exp

    violations: list[tuple[str, str]] = []
    tables = _entity_tables(stmt)
    if len(tables) != 1:
        return violations
    if _has_subquery_or_cte(stmt):
        return violations
    (_alias, table), = tables.items()
    if table not in schema:
        ghosts.add(table)
        return violations
    real_cols = schema[table]
    out_aliases = _explicit_aliases(stmt)

    for col in stmt.find_all(exp.Column):
        if col.table:
            continue  # 带限定 → test_raw_sql_column_contract 管
        name = (col.name or "").lower()
        if not name or name == "*":
            continue
        if name in _PSEUDO_COLS or name in out_aliases or name in brace_names:
            continue
        if name not in real_cols:
            violations.append((table, name))

    for ins in stmt.find_all(exp.Insert):
        schema_expr = ins.this
        if isinstance(schema_expr, exp.Schema):
            for ident in schema_expr.expressions:
                if isinstance(ident, exp.Identifier):
                    nm = ident.name.lower()
                    if (nm and nm not in real_cols and nm not in _PSEUDO_COLS
                            and nm not in brace_names):
                        violations.append((table, nm))
    return violations


def _scan_unqualified() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """全仓扫描，返回 (列违规 {key: files}, 幽灵表 {table: files})。路径用正斜杠。"""
    import sqlglot

    schema = _load_pg_schema_sync()
    assert len(schema) > 50, f"PG schema 表数异常少（{len(schema)}），疑连库失败"

    findings: dict[str, set[str]] = {}
    ghosts: dict[str, set[str]] = {}
    for fpath in _iter_python_files():
        try:
            source = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(fpath.relative_to(REPO_ROOT)).replace("\\", "/")
        for sql in _extract_sql_strings(source):
            try:
                trees = sqlglot.parse(sql, read="postgres")
            except Exception:
                continue
            bnames = _brace_names(sql)
            local_ghost: set[str] = set()
            for tree in trees:
                if tree is None:
                    continue
                for t, c in _check_stmt(tree, schema, bnames, local_ghost):
                    findings.setdefault(f"{t}.{c}", set()).add(rel)
            for g in local_ghost:
                ghosts.setdefault(g, set()).add(rel)
    return findings, ghosts


# ─── 断言 ────────────────────────────────────────────────────────────────────
#
# 🔴 共享一次扫描：`async_session` 的 engine 连接池绑定到首个事件循环，
# 每个测试各自 `asyncio.run()` 会创建并关闭新循环 ⇒ 第二个测试起连库报
# `Event loop is closed`、拿到空 schema ⇒ 基线假性腐烂。故全模块只扫一次。


@pytest.fixture(scope="module")
def scan_result():
    return _scan_unqualified()


def test_no_new_unqualified_column_violations(scan_result):
    """现算无限定列违规必须 ⊆ 基线 —— 新增一条即红（防新代码再引入查错列）。"""
    findings, _ = scan_result
    new_keys = set(findings) - set(_UNQUALIFIED_BASELINE)
    assert not new_keys, (
        "发现**新增**的裸 SQL 无限定列违规（不在基线内）：\n"
        + "\n".join(
            f"  🔴 {k}\n     引用于: {sorted(findings[k])}"
            for k in sorted(new_keys)
        )
        + "\n\n修复：改正列名 / 查正确的表；确为 f-string 变量/伪列误判则补排除规则。"
    )
    # 同键下新增引用文件也要红（防某文件新引入同一错列）
    for key, files in findings.items():
        if key in _UNQUALIFIED_BASELINE:
            extra = files - _UNQUALIFIED_BASELINE[key]
            assert not extra, (
                f"基线列 {key} 出现**新增引用文件**：{sorted(extra)}（修正或并入基线并说明）"
            )


def test_baseline_entries_still_exist_no_rot(scan_result):
    """基线每条仍必须真实出现 —— 修复后必须删除对应项（防基线腐烂成空转白名单）。"""
    findings, _ = scan_result
    stale_keys = set(_UNQUALIFIED_BASELINE) - set(findings)
    assert not stale_keys, (
        "以下基线项已不再出现（说明已修复）——请从 _UNQUALIFIED_BASELINE 删除它们：\n"
        + "\n".join(f"  ✅ {k}" for k in sorted(stale_keys))
    )
    # 每条基线声明的文件也必须仍真实引用（修了某文件就从该项的集合里删）
    for key, base_files in _UNQUALIFIED_BASELINE.items():
        cur = findings.get(key, set())
        gone = base_files - cur
        assert not gone, (
            f"基线列 {key} 不再被这些文件引用（已修复）：{sorted(gone)}——请从基线该项删除。"
        )


def test_no_new_ghost_tables(scan_result):
    """现算幽灵表（表 ∉ 真库）必须 ⊆ 基线，且基线每条仍出现。"""
    _, ghosts = scan_result
    new_ghosts = set(ghosts) - set(_GHOST_TABLE_BASELINE)
    assert not new_ghosts, (
        "发现**新增**幽灵表（真库无此表、单实体表作用域）：\n"
        + "\n".join(f"  🔴 {g} <- {sorted(ghosts[g])}" for g in sorted(new_ghosts))
    )
    stale = set(_GHOST_TABLE_BASELINE) - set(ghosts)
    assert not stale, (
        "以下幽灵表基线已不再出现，请删除：\n" + "\n".join(f"  ✅ {g}" for g in sorted(stale))
    )


# ─── 反向自检 ────────────────────────────────────────────────────────────────


def test_reverse_selfcheck_detector_catches_bad_column():
    """反向自检：注入一条查不存在列的单表 SQL，检测器必须命中（防检测空转）。"""
    import sqlglot

    schema = {"working_paper": {"id", "project_id", "status"}}
    sql = "SELECT id, nonexistent_col FROM working_paper WHERE project_id = :pid"
    trees = sqlglot.parse(sql, read="postgres")
    ghosts: set[str] = set()
    hits = []
    for tree in trees:
        hits.extend(_check_stmt(tree, schema, set(), ghosts))
    assert ("working_paper", "nonexistent_col") in hits
    # 真实列不得误报
    assert ("working_paper", "id") not in hits
    assert ("working_paper", "status") not in hits


def test_reverse_selfcheck_fstring_var_not_flagged():
    """反向自检：f-string 插值变量名不得被当列（否则 23→N 爆基线）。"""
    import sqlglot

    schema = {"trial_balance": {"project_id", "year", "standard_account_code"}}
    sql = "SELECT * FROM trial_balance WHERE standard_account_code IN ({placeholders})"
    bnames = _brace_names(sql)
    assert "placeholders" in bnames
    trees = sqlglot.parse(sql, read="postgres")
    hits = []
    for tree in trees:
        hits.extend(_check_stmt(tree, schema, bnames, set()))
    assert hits == [], f"f-string 变量被误报为列: {hits}"


def test_reverse_selfcheck_multi_table_scope_skipped():
    """反向自检：多实体表作用域（无限定列无法归属）必须跳过，保守零误报。"""
    import sqlglot

    schema = {"a": {"x"}, "b": {"y"}}
    sql = "SELECT z FROM a JOIN b ON a.x = b.y"
    trees = sqlglot.parse(sql, read="postgres")
    hits = []
    for tree in trees:
        hits.extend(_check_stmt(tree, schema, set(), set()))
    assert hits == [], "多表作用域不应产生无限定列违规（z 无法可靠归属）"


def test_reverse_selfcheck_system_schema_not_ghost():
    """反向自检：information_schema.columns 不得被当幽灵表 columns。"""
    import sqlglot

    schema = {"working_paper": {"id"}}
    sql = "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public'"
    trees = sqlglot.parse(sql, read="postgres")
    ghosts: set[str] = set()
    for tree in trees:
        _check_stmt(tree, schema, set(), ghosts)
    assert "columns" not in ghosts, "information_schema.columns 被误当成幽灵表 columns"
