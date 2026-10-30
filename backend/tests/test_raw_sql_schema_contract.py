"""契约测试：裸 SQL 引用的表 ⊆ 真实可建表集合（ORM 模型 ∪ 迁移建表 ∪ 基础设施表）。

**为什么需要**：本仓库连续多轮 500 bug 的根因高度同源——`text("...FROM xxx...")`
裸 SQL 引用了「基于想象 / 已改名 / 从未迁移」的表（如 wp_account_mapping /
report_snapshots / group_note_templates / system_settings），这类 bug：
- schema_drift_detector 抓不到（它只比对 ORM ↔ DB，不扫裸 SQL 字符串）
- 单元测试多用 mock / SQLite 跑不到真实 schema
- 只在生产真实 PG 上对空数据项目命中端点才暴露（UndefinedTable 500）

本测试在 CI 阶段纯静态扫描裸 SQL 的 FROM/JOIN 表引用，与「权威可建表集合」比对，
一次性兜住整类「查不存在表」bug，无需 live DB。

**Validates**: GET 巡检复盘元反思「CI SQL 列引用 ⊆ 真实 schema 契约检查」
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_APP = REPO_ROOT / "backend" / "app"
MIGRATIONS_DIR = REPO_ROOT / "backend" / "migrations"

EXCLUDE_DIRS = {"__pycache__", ".hypothesis", "tests", "migrations"}

# FROM <table> / JOIN <table>（仅匹配普通标识符表名，跳过子查询 "(" 与带 schema 前缀）
_FROM_JOIN_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b",
    re.IGNORECASE,
)
# EXTRACT(field FROM col) / SUBSTRING(x FROM n) 等函数内的 FROM 不是表引用，先剔除
_EXTRACT_FROM_RE = re.compile(
    r"\b(?:EXTRACT|SUBSTRING|TRIM|OVERLAY|POSITION)\s*\([^)]*?\bFROM\b",
    re.IGNORECASE,
)
# SQL 保留字 / 非表名（FROM 后可能跟这些，需排除）
_SQL_NONTABLE = {
    "select", "lateral", "unnest", "generate_series", "jsonb_array_elements",
    "jsonb_array_elements_text", "json_array_elements", "values", "only",
}

# 基础设施 / 外部租户表（不来自 ORM 也不来自业务迁移，但合法存在）
_INFRA_TABLES = {
    "schema_version", "schema_migration_failures", "schema_drift_log",
    "pg_type", "pg_enum", "pg_class", "pg_attribute", "pg_namespace",
    "pg_stat_statements", "pg_indexes", "pg_tables", "information_schema",
    "columns", "tables", "ledger_datasets",  # ledger_datasets 由 dataset_models 定义，保险纳入
    # PG 系统目录/进度视图（gin_index_monitor 等查询用）
    "pg_index", "pg_stat_progress_create_index", "pg_stat_activity",
    "pg_locks", "pg_database", "pg_roles",
    # 真实存在于 PG 但 ORM 未映射的历史表（drift detector 标 db_extra，合法）
    "review_conversation_participants", "tb_aux_balance_summary",
    "review_conversation_exports", "wp_sheet_locks", "wp_migration_snapshots",
}

# 🔴 已知 phantom 表引用债务（裸 SQL 引用了真实 PG 不存在的表）。
# 这些是 GET 巡检契约测试（2026-06-01）发现的存量隐患——对应代码路径多被
# try/except 包裹或走冷门分支，未在常规巡检中命中 500，但本质是定时炸弹。
# 列入白名单使本测试先「守住增量」（防新增 phantom 引用），存量逐个核实后清零。
# 每条需后续确认：改正表名 / 补迁移建表 / 删死代码。
# TODO(schema-debt): 逐个消除，清零后删除本白名单。
_KNOWN_PHANTOM_DEBT = {
    "wp_template_registry",       # custom_query.py/wp_template_registry.py — 服务层 table_exists 懒判，未迁移（功能债务）
    # ai_generated_content / event_cascade_health：签发清单改用真表（ai_content / ai_content_governance /
    # stale_summary_aggregate）后已无引用，2026-10-17 移除（spec deliverable-writeback-and-online-edit-integrity）
}

# PG 函数式表源（FROM 后跟函数，非真实表）
_FUNCTION_SOURCES = {
    "to_regclass", "now", "current_setting", "set_config",
}


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(BACKEND_APP):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for n in names:
            if n.endswith(".py"):
                files.append(Path(root) / n)
    return files


def _extract_sql_strings(source: str) -> list[str]:
    """提取真正传给 text()/sa.text()/sql_text() 的 SQL 块。

    只认 text(...) 调用实参里的字符串字面量，避免把普通 prose f-string、
    注释、文档字符串误当 SQL 扫描（那是假阳性主因）。
    """
    blocks: list[str] = []
    # 匹配 text( / sa.text( / sql_text( / _text( 后紧跟的字符串字面量
    #
    # 🔴 `(?:[frbFRB]{1,2})?` 这个前缀组不能省：没有它，**f-string 写的 SQL 整段被跳过**。
    #    2026-09-06 实测代价 —— `formula_runtime/value_loader.py` 的
    #    `f"SELECT row_code, {col_name} FROM report_rows "` 引用了一张**从未建过**的表，
    #    而本测试长期全绿；该 reader 又被 `except Exception: pass` 完全静默吞掉，
    #    于是「公式引用 report 域 → 静默取空 → 照算出错值」在四层守卫下全部隐形。
    #    f-string 是拼动态列名/表名最常见的写法，恰恰是最该扫的那一类。
    #
    # 🔴 模块别名同样要认：`import sqlalchemy as _sa` / `as sa_mod` 后写 `_sa.text(` / `sa_mod.text(`，
    #    原正则只认字面的 `sa.text`，这类调用整段不扫（2026-10-30 现算：`_c24_import_export.py` 1 段；
    #    spec ai-content-pending-target-label 变异时发现）⇒ 「<标识符>[.<标识符>…].text(」都算。
    call_re = re.compile(
        r"""(?:^|[^\w.])(?:(?:[A-Za-z_]\w*\.)+text|sql_text|sa_text|_text|text)\s*\(\s*"""
        r"""(?:[frbFRB]{1,2})?"""
        r"""(?:"{3}(.*?)"{3}|'{3}(.*?)'{3}|"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""",
        re.DOTALL,
    )
    for m in call_re.finditer(source):
        s = m.group(1) or m.group(2) or m.group(3) or m.group(4) or ""
        if re.search(r"\b(FROM|JOIN)\b", s, re.IGNORECASE):
            blocks.append(s)
    return blocks


def _collect_referenced_tables() -> dict[str, set[str]]:
    """扫描全仓裸 SQL，返回 {表名: {引用它的文件相对路径}}。

    排除：CTE 名（WITH x AS）、SQL 关键字、函数式表源。
    """
    refs: dict[str, set[str]] = {}
    for fpath in _iter_python_files():
        try:
            source = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(fpath.relative_to(REPO_ROOT))
        for sql in _extract_sql_strings(source):
            for tbl in _table_refs_in_sql(sql):
                refs.setdefault(tbl, set()).add(rel)
    return refs


_CTE_RE = re.compile(
    r"\bWITH\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\b|,\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", re.IGNORECASE
)


def _table_refs_in_sql(sql: str) -> set[str]:
    """一段 SQL 里 FROM / JOIN 引用的表名（小写）。"""
    # 剔除 EXTRACT(field FROM col) 等函数内 FROM（非表引用）
    sql_clean = _EXTRACT_FROM_RE.sub("", sql)
    # 本 SQL 内定义的 CTE 名，FROM/JOIN 它们不算表引用
    ctes = {(g1 or g2).lower() for g1, g2 in _CTE_RE.findall(sql_clean) if (g1 or g2)}
    out: set[str] = set()
    for m in _FROM_JOIN_RE.finditer(sql_clean):
        tbl = m.group(1).lower()
        # 单字母/双字母 token 一律视为别名（FROM (...) l），非真实表
        if len(tbl) <= 2:
            continue
        if tbl in _SQL_NONTABLE or tbl in _FUNCTION_SOURCES or tbl in ctes:
            continue
        # 「FROM 名字(」是函数式表源（json_populate_recordset / jsonb_to_recordset …），不是表：
        # PG 里表的列别名必须先写表别名（FROM t AS x(a, b)），表名后不会直接跟括号。
        # 2026-10-19 起 note_project_realign_apply 的 json_populate_recordset 被当成幽灵表，本守卫一直红。
        if sql_clean[m.end():].lstrip().startswith("("):
            continue
        out.add(tbl)
    return out


def _collect_orm_tables() -> set[str]:
    """ORM Base.metadata 全表（先 import 全部 model 子模块保证完整）。"""
    import importlib
    import pkgutil
    import app.models as models_pkg
    for mod_info in pkgutil.walk_packages(models_pkg.__path__, prefix="app.models."):
        try:
            importlib.import_module(mod_info.name)
        except Exception:
            pass
    from app.models.base import Base
    return {t.lower() for t in Base.metadata.tables.keys()}


def _collect_migration_tables() -> set[str]:
    """扫描 migrations/V*.sql 的 CREATE TABLE [IF NOT EXISTS] <name>。"""
    tables: set[str] = set()
    if not MIGRATIONS_DIR.is_dir():
        return tables
    pat = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-zA-Z_][a-zA-Z0-9_]*)",
        re.IGNORECASE,
    )
    for f in MIGRATIONS_DIR.glob("V*.sql"):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in pat.finditer(content):
            tables.add(m.group(1).lower())
    return tables


def _collect_lazy_create_tables() -> set[str]:
    """扫描 app 内 CREATE TABLE IF NOT EXISTS（运行时懒建，合法存在）。"""
    tables: set[str] = set()
    pat = re.compile(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(?:public\.)?([a-zA-Z_][a-zA-Z0-9_]*)",
        re.IGNORECASE,
    )
    for fpath in _iter_python_files():
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in pat.finditer(content):
            tables.add(m.group(1).lower())
    return tables


def test_raw_sql_tables_are_known():
    """裸 SQL FROM/JOIN 引用的每张表都必须可建（ORM ∪ 迁移 ∪ 懒建 ∪ 基础设施）。

    失败即意味着某处裸 SQL 引用了不存在的表 —— 运行时必 UndefinedTable 500。
    修复方式：补迁移建表 / 改正表名 / （若是 CTE 别名误判）加入白名单。
    """
    known = (
        _collect_orm_tables()
        | _collect_migration_tables()
        | _collect_lazy_create_tables()
        | {t.lower() for t in _INFRA_TABLES}
    )
    refs = _collect_referenced_tables()

    unknown = {
        tbl: sorted(files)
        for tbl, files in refs.items()
        if tbl not in known and tbl not in _KNOWN_PHANTOM_DEBT
    }

    assert not unknown, (
        "发现【新增】裸 SQL 引用了「ORM/迁移/懒建」均无的表（运行时会 UndefinedTable 500）：\n"
        + "\n".join(
            f"  🔴 {tbl}\n     引用于: {files}"
            for tbl, files in sorted(unknown.items())
        )
        + "\n\n修复：补迁移建表 / 改正表名；若确为存量债务，登记进 _KNOWN_PHANTOM_DEBT。"
    )


def test_phantom_debt_not_growing_and_still_real():
    """守护已知 phantom 债务集合：①不被新条目掺入（增量靠主测试挡）
    ②已登记的债务表确实仍被引用（清零后应从 _KNOWN_PHANTOM_DEBT 删除，否则本测试提醒）。
    """
    refs = _collect_referenced_tables()
    referenced = set(refs.keys())
    stale = _KNOWN_PHANTOM_DEBT - referenced
    assert not stale, (
        f"以下表已不再被裸 SQL 引用（已修复？），请从 _KNOWN_PHANTOM_DEBT 移除：{sorted(stale)}"
    )


def test_extract_sql_strings_recognizes_call_forms():
    """抽取正则的自检：各种 text() 调用写法都要抽到，非调用的字符串与同名方法不算（防口径收窄后静默漏扫）。"""
    sql = "SELECT a FROM t"
    forms = [
        f'text("{sql}")',
        f'sa.text("{sql}")',
        f'_sa.text("{sql}")',
        f'sa_mod.text("{sql}")',
        f'sqlalchemy.sql.text("{sql}")',
        f'sql_text("{sql}")',
        f'sa_text("{sql}")',
        f'_text("{sql}")',
        f'text(f"{sql}")',
        f'x = sa.text(\n    "{sql}"\n)',
    ]
    for src in forms:
        assert _extract_sql_strings(src) == [sql], src
    for src in (f'"{sql}"', f'context("{sql}")', f'el.text_content("{sql}")', f'subtext("{sql}")'):
        assert _extract_sql_strings(src) == [], src


def test_table_refs_skip_function_sources_but_keep_tables():
    """表名抽取自检：函数式表源不算表，真实表（含紧跟换行 / 别名 / 子查询）照算。"""
    assert _table_refs_in_sql(
        "INSERT INTO t SELECT * FROM json_populate_recordset(NULL::t, CAST(:rows AS json))"
    ) == set()
    assert _table_refs_in_sql("SELECT * FROM jsonb_to_recordset (:j) AS x(a int)") == set()
    assert _table_refs_in_sql(
        "SELECT a.id FROM wp_index a JOIN working_paper\n  wp ON wp.wp_index_id = a.id WHERE x IN (SELECT 1)"
    ) == {"wp_index", "working_paper"}
    assert _table_refs_in_sql("WITH cte AS (SELECT 1) SELECT * FROM cte JOIN projects p ON true") == {"projects"}


def test_known_table_sets_nonempty():
    """防御：权威表集合非空（防 import 失败导致 known 为空使主测试假绿）。"""
    orm = _collect_orm_tables()
    mig = _collect_migration_tables()
    assert len(orm) > 50, f"ORM 表数异常少（{len(orm)}），疑 model import 失败"
    assert len(mig) > 20, f"迁移建表数异常少（{len(mig)}），疑迁移目录扫描失败"
