"""Task 68 后端全链 / bundle / candidate / recovery 与辐射面 **独立回归门**。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7 Task 68

═══ 本任务为什么必须是独立的 ═══

正文逐字：「不得由实现任务自证」。所以本门**不 import 任何实现任务的守卫**，也不把
「跑一遍实现任务自己写的测试然后报 passed」当判据。每条不变量都在这里**重新表达**一次：

* **schema 侧** —— 真连 PostgreSQL，读 `pg_get_constraintdef` / `pg_get_indexdef` /
  `pg_get_triggerdef` / `pg_get_functiondef` / `information_schema.columns`，逐列逐片段
  比对。判据是**定义内容**，不是「同名对象存在」。
* **行为侧** —— 在 **scratch schema**（`tmp_task68_reg_<hex>`）里真造行：合法形态必须被
  接受（对照组），非法形态必须被**它自己声明的那条约束**拒绝，且各臂的拒绝理由**互不
  命中**。跑完 `DROP SCHEMA CASCADE` 并给出前后逐表行数快照作复原实证。

🔴 **为什么行为侧不可省**：本报告实测生产 `public` schema 里 forcesave request /
application / operation / delivery / room / scope index / content version 等 **13 张表
全部 0 行**。0 行上「逐行成立」恒真（假绿第⑥源），schema 侧能证明「DDL 把住了」，但
证明不了「这条约束真的会在插入时报错」。两侧缺一即不算验过。

═══ 六个子条目的落点 ═══

| 子条目 | 报告字段 |
|---|---|
| 1 targeted tests | `suite_run` + `radiation_surface` |
| 2 真实 PG：request/application/operation/recovery/delivery/scope/version | `invariants[sub_bullet=2]` |
| 3 真实 PG：bundle/candidate/incoming/close-capture/leader | `invariants[sub_bullet=3]` |
| 4 用户端点 | `endpoint_checks` |
| 5 独立文件/契约套件验证完整链 | `chain_checks` |
| 6 辐射面反查 + 不冒充 OO probe | `radiation_surface` + `oo_scope_boundary` |

═══ 本门不做什么 ═══

* **不运行真实 OnlyOffice 场景**，不刷新 evidence，不宣称任何 scenario 通过 —— 那是
  Task 70。`oo_scope_boundary` 显式记录这条边界。
* **不改生产代码、不改迁移、不改 Tasks 61/66/67 的产物**。发现缺陷如实登记为
  `BP-68-n` 与 `preexisting_failures`，不顺手修（会让 Task 70 的 evidence stale）。
* 对生产 `public` schema **只 SELECT**；一切写入只发生在 scratch schema。

═══ 用法（仓库根；PATH 上的 `python` 指向坏掉的解释器）═══

    .\\.venv\\Scripts\\python.exe backend/scripts/check/check_task68_backend_chain_independent_regression.py --check
    .\\.venv\\Scripts\\python.exe backend/scripts/check/check_task68_backend_chain_independent_regression.py --write
    ... --write --run-suites          # 另跑辐射面全量 pytest（十余分钟）并写进报告

`--check` / `--write` 互斥且必选。`--check` 现算全部结论并与磁盘逐字节比对；
`suite_run` 块是**昂贵的真实 pytest 执行结果**，`--check` 从磁盘复用但会现算辐射面清单
并逐项核对（清单变了立刻红），因此改 scanner 无法蒙过去。
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Final, Mapping, Sequence

# ════════════════════════════════════════════════════════════════════════════
# §0 常量与路径
# ════════════════════════════════════════════════════════════════════════════

SCHEMA_VERSION: Final[str] = "task68-backend-chain-independent-regression:v1"
OWNER_TASK: Final[str] = "68"
TASK_NUMBER: Final[int] = 68
SPEC: Final[str] = "workpaper-html-onlyoffice-bidirectional-writeback-closure"

REPO: Final[Path] = Path(__file__).resolve().parents[3]
BACKEND: Final[Path] = REPO / "backend"
DATA: Final[Path] = BACKEND / "data"

OUTPUT_PATH: Final[Path] = DATA / "workpaper_sync_task68_backend_chain_regression.json"
TASK67_REPORT_PATH: Final[Path] = DATA / "workpaper_sync_task67_structural_pre_reconcile.json"
TASK66_PLAN_PATH: Final[Path] = DATA / "workpaper_sync_task66_legacy_deletion_plan.json"
PARADIGM_PATH: Final[Path] = DATA / "workpaper_sync_migration_paradigm.json"

SPEC_DIR: Final[Path] = REPO / ".kiro" / "specs" / SPEC
TASKS_MD: Final[Path] = SPEC_DIR / "tasks.md"
DESIGN_MD: Final[Path] = SPEC_DIR / "design.md"

ROUTER_PY: Final[Path] = BACKEND / "app" / "routers" / "wp_sync_router.py"
GUARD_PY: Final[Path] = BACKEND / "app" / "services" / "workpaper_sync" / "endpoint_guard.py"
RESOLUTION_PY: Final[Path] = (
    BACKEND / "app" / "services" / "workpaper_sync" / "conflict_resolution.py"
)
SYNC_SERVICES_DIR: Final[Path] = BACKEND / "app" / "services" / "workpaper_sync"

#: 生产库实际应用到 V152（V153 已占号未应用）。行为侧 scratch schema 必须与生产同 DDL，
#: 否则「行上验过」验的是另一套 schema。
SCRATCH_MIGRATIONS: Final[tuple[Path, ...]] = (
    BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql",
    BACKEND / "migrations" / "V152__workpaper_content_version_upload_wopi_source.sql",
)

_SCHEMA_PREFIX: Final[str] = "tmp_task68_reg_"

#: 🔴 全局 `BP-NN` 已被 Tasks 60/61/63/64 重复占用（同号不同义）；本任务用 task-scoped 前缀。
BP_ID_RE: Final[re.Pattern[str]] = re.compile(r"BP-68-\d+")

RESULT_PASSED: Final[str] = "passed"
RESULT_FAILED: Final[str] = "failed"
RESULT_UNVERIFIABLE: Final[str] = "unverifiable"

#: 正文「独立验证 Property …」逐条（48 条）。守卫与 design.md 双向锁死。
DECLARED_PROPERTIES: Final[tuple[int, ...]] = (
    4, 5, 6, 7, 9, 10, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31,
    32, 36, 37, 38, 39, 40, 41, 42, 43, 44, 50, 52, 53, 54, 59, 60, 61, 62, 63, 64, 65,
    67, 68, 69, 70, 71,
)

#: 正文六个子条目。每条都必须有独立判据与独立报告字段。
SUB_BULLETS: Final[Mapping[int, str]] = {
    1: "运行 migration/repository/artifact/retention/content+representation mutation/"
       "definition-bundle store/candidate finalize/room/close-intent/request/delivery/"
       "recovery/content-application/operation/scope-index/merge/coordinator/outbox/"
       "evidence/Excel/Word targeted tests",
    2: "真实 PostgreSQL 独立校验 forcesave 复合唯一键与 frozen fingerprint、application "
       "key/sequence/fence、operation primary+duplicate、N shell 收敛、recovery claim、"
       "delivery durable_at gate、scope index tombstone、content version opaque UUID",
    3: "真实 PostgreSQL 继续校验 bundle slot NOT NULL/CHECK/trigger、projection contract "
       "approved child、typed marker 非法空值、candidate 不可见、incoming state、"
       "quarantined、close-capture exactly-one、leader promotion、frozen bundle 不折叠",
    4: "对 pending/materialize/confirm/forcesave/close-intents/recovery list/claim/"
       "download-only/operations/conflicts/timeline/resolve/versions rollback 全用户端点"
       "独立验证显式 scope、opaque UUID、统一 404/403、授权顺序",
    5: "独立文件/契约套件验证完整 template → instrumentation → contract → bundle → "
       "representation、历史 frozen bundle、contract 字段、动态列/行、Word tag/Word-only、"
       "resolver 子码、custom approved bundle 与 candidate-only upgrader/finalize owner",
    6: "按引用关系反查辐射面，不跑无边界全量；从仓库根执行；不冒充真实 OO probe/evidence",
}

#: 报告里每条不变量必须带的字段（守卫逐格断言，防 additive 注入）。
REQUIRED_INVARIANT_FACETS: Final[tuple[str, ...]] = (
    "check_id",
    "statement",
    "sub_bullet",
    "measured_by",
    "owner_task",
    "properties",
    "requirements",
    "schema_side",
    "behaviour_side",
    "passed",
)

#: 行为侧的封闭结论词表。
BEHAVIOUR_STATES: Final[tuple[str, ...]] = (
    "verified_on_rows",       # 真造行验过，全部臂符合声明
    "arm_mismatch",           # 造行了但有臂不符声明 ⇒ 真缺陷
    "harness_error",          # 采集自身失败（禁 fail-open，必须红）
    "not_executed",           # 未执行（只允许显式 owner 转交时出现）
)

#: schema 侧的封闭结论词表。
SCHEMA_STATES: Final[tuple[str, ...]] = (
    "satisfied",
    "missing_fragments",
    "absent",
    "not_enforced_at_schema",  # 已现测确认 DDL 不禁止 ⇒ 靠服务层，必须点名 owner
    "db_unreadable",
)

_DB_UNREADABLE: Final[str] = (
    "PostgreSQL 不可读。Task 68 的 schema 侧判据全部落在真库的 UNIQUE/CHECK/trigger/"
    "function 定义上，行为侧还要在 scratch schema 里真造行；读不到时**不得**按"
    "「没有违反项所以通过」处理（AC 5.12 明令禁 fail-open）。报告会把受影响的检查标成 "
    "`db_unreadable` 并整体判 unverifiable。"
)


class Task68GateError(RuntimeError):
    """门自身的结构错误（禁 fail-open：让它抛，不要降级成「无数据」）。"""


# ════════════════════════════════════════════════════════════════════════════
# §1 基础工具
# ════════════════════════════════════════════════════════════════════════════


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def stable_json(value: Any, *, indent: int | None = None) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=indent)


def digest_of(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise Task68GateError(f"缺少输入文件: {rel(path)}")
    return json.loads(path.read_text(encoding="utf-8"))


def git_head() -> str:
    try:
        out = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - 记录后由守卫判断
        return f"unavailable:{type(exc).__name__}"
    return out.stdout.strip() or "unavailable"


def _ensure_backend_on_path() -> None:
    for extra in (BACKEND, BACKEND / "scripts" / "gen"):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    os.environ.setdefault("DB_DISABLE_SSL", "True")


def strip_py_comments(source: str) -> str:
    """去掉 `#` 注释与文档串，只留可执行文本。

    🔴 只用于**不含 SQL 三引号字面量**的文件。含 `sa.text(\"\"\"...\"\"\")` 的模块必须走
    AST（本 spec 的教训 14）。本门的所有 AST 判据都直接走 `ast`，此函数仅用于
    「路由模板字面量」这类纯文本扫描。
    """
    out: list[str] = []
    for line in source.splitlines():
        stripped = line.split("#", 1)[0] if "#" in line else line
        out.append(stripped)
    return "\n".join(out)


_AST_CACHE: dict[str, ast.Module] = {}


def module_ast(path: Path) -> ast.Module:
    """按路径缓存 AST（变异要跑几十轮，不缓存会从秒级拖到分钟级）。"""
    key = str(path)
    if key not in _AST_CACHE:
        _AST_CACHE[key] = ast.parse(path.read_text(encoding="utf-8"))
    return _AST_CACHE[key]


def dotted_name(node: ast.expr) -> str | None:
    """把 `a.b.c` / `a` 还原成点号串（AST 判据的基础，禁子串匹配）。"""
    parts: list[str] = []
    cur: ast.expr | None = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def function_def(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise Task68GateError(f"AST 里找不到函数 {name}")


# ════════════════════════════════════════════════════════════════════════════
# §2 schema 侧：真库 DDL 目录（独立表达，不复用 Task 67 的读法）
# ════════════════════════════════════════════════════════════════════════════

#: 🔴 与 Task 67 刻意用**不同的系统视图**：67 走 `pg_indexes` / `information_schema`
#: 的定义列；这里走 `pg_constraint` / `pg_index` / `pg_trigger` / `pg_proc` 的
#: `pg_get_*def()`，独立复核同一批约束。两侧同时错的概率远低于抄同一份读法。
_SQL_CONSTRAINTS: Final[str] = """
SELECT rel.relname AS table_name,
       con.conname  AS name,
       con.contype  AS contype,
       pg_get_constraintdef(con.oid) AS definition
  FROM pg_constraint con
  JOIN pg_class rel ON rel.oid = con.conrelid
  JOIN pg_namespace ns ON ns.oid = rel.relnamespace
 WHERE ns.nspname = 'public' AND rel.relname LIKE 'working_paper%'
"""

_SQL_INDEXES: Final[str] = """
SELECT rel.relname AS table_name,
       idx.relname AS name,
       pg_get_indexdef(idx.oid) AS definition
  FROM pg_index i
  JOIN pg_class idx ON idx.oid = i.indexrelid
  JOIN pg_class rel ON rel.oid = i.indrelid
  JOIN pg_namespace ns ON ns.oid = rel.relnamespace
 WHERE ns.nspname = 'public' AND rel.relname LIKE 'working_paper%'
"""

_SQL_TRIGGERS: Final[str] = """
SELECT rel.relname AS table_name,
       tg.tgname   AS name,
       pg_get_triggerdef(tg.oid) AS definition
  FROM pg_trigger tg
  JOIN pg_class rel ON rel.oid = tg.tgrelid
  JOIN pg_namespace ns ON ns.oid = rel.relnamespace
 WHERE ns.nspname = 'public' AND NOT tg.tgisinternal AND rel.relname LIKE 'working_paper%'
"""

_SQL_FUNCTIONS: Final[str] = """
SELECT p.proname AS name, pg_get_functiondef(p.oid) AS definition
  FROM pg_proc p
  JOIN pg_namespace ns ON ns.oid = p.pronamespace
 WHERE ns.nspname = 'public' AND p.proname LIKE 'wpsync%'
"""

_SQL_COLUMNS: Final[str] = """
SELECT table_name, column_name, is_nullable, data_type
  FROM information_schema.columns
 WHERE table_schema = 'public' AND table_name LIKE 'working_paper%'
"""

#: 只读 SQL 清单。守卫据此断言「每一条都是 SELECT」，并断言清单里真的含这五条目标。
READONLY_SQL_STATEMENTS: Final[tuple[str, ...]] = (
    _SQL_CONSTRAINTS,
    _SQL_INDEXES,
    _SQL_TRIGGERS,
    _SQL_FUNCTIONS,
    _SQL_COLUMNS,
)

#: 行为侧要证明「0 行不是我们没验，而是供给还没到」，这些表的精确行数进报告。
PRODUCTION_ROW_TABLES: Final[tuple[str, ...]] = (
    "working_paper_forcesave_request",
    "working_paper_content_application",
    "working_paper_content_application_event",
    "working_paper_sync_operation",
    "working_paper_sync_operation_event",
    "working_paper_callback_delivery",
    "working_paper_callback_recovery_case",
    "working_paper_sync_scope_index",
    "working_paper_oo_room",
    "working_paper_oo_close_intent",
    "working_paper_content_version",
    "working_paper_content_representation",
    "working_paper_sync_entry_state",
    "working_paper_representation_upgrade_candidate",
    "working_paper_sync_definition_artifact",
    "working_paper_sync_definition_bundle",
    "working_paper_sync_definition_null_marker",
    "working_paper_artifact",
    "working_paper_sync_test_run",
    "working_paper_entry_evidence_scenario",
)


@dataclass
class SchemaCatalog:
    """生产 `public` schema 的 DDL 目录（只读）。"""

    readable: bool
    error: str | None = None
    constraints: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    indexes: dict[tuple[str, str], str] = field(default_factory=dict)
    triggers: dict[tuple[str, str], str] = field(default_factory=dict)
    functions: dict[str, str] = field(default_factory=dict)
    columns: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    row_counts: dict[str, int] = field(default_factory=dict)

    def constraint_def(self, table: str, name: str) -> str | None:
        row = self.constraints.get((table, name))
        return None if row is None else row["definition"]

    def index_def(self, table: str, name: str) -> str | None:
        return self.indexes.get((table, name))

    def trigger_def(self, table: str, name: str) -> str | None:
        return self.triggers.get((table, name))

    def function_def(self, name: str) -> str | None:
        return self.functions.get(name)

    def column_is_nullable(self, table: str, column: str) -> str | None:
        row = self.columns.get((table, column))
        return None if row is None else row["is_nullable"]

    def as_record(self) -> dict[str, Any]:
        return {
            "readable": self.readable,
            "error": self.error,
            "constraint_count": len(self.constraints),
            "index_count": len(self.indexes),
            "trigger_count": len(self.triggers),
            "function_count": len(self.functions),
            "column_count": len(self.columns),
            "row_counts": {t: self.row_counts.get(t, 0) for t in PRODUCTION_ROW_TABLES},
            "constraints": {
                f"{t}.{n}": v["definition"] for (t, n), v in sorted(self.constraints.items())
            },
            "indexes": {f"{t}.{n}": v for (t, n), v in sorted(self.indexes.items())},
            "triggers": {f"{t}.{n}": v for (t, n), v in sorted(self.triggers.items())},
            "functions": dict(sorted(self.functions.items())),
            "nullability": {
                f"{t}.{c}": v["is_nullable"] for (t, c), v in sorted(self.columns.items())
            },
        }


def catalog_from_record(record: Mapping[str, Any]) -> SchemaCatalog:
    """从报告记录还原目录 —— 守卫据此**正向重算**每条 schema 结论。

    🔴 反事实多臂只能证明「非重言」，抓不到「恒真」（教训 15）。所以必须能把记录里的
    输入原样喂回实现再比对一次。
    """
    catalog = SchemaCatalog(readable=bool(record.get("readable")), error=record.get("error"))
    for key, definition in (record.get("constraints") or {}).items():
        table, name = key.split(".", 1)
        catalog.constraints[(table, name)] = {"definition": definition, "contype": "?"}
    for key, definition in (record.get("indexes") or {}).items():
        table, name = key.split(".", 1)
        catalog.indexes[(table, name)] = definition
    for key, definition in (record.get("triggers") or {}).items():
        table, name = key.split(".", 1)
        catalog.triggers[(table, name)] = definition
    catalog.functions = dict(record.get("functions") or {})
    for key, nullable in (record.get("nullability") or {}).items():
        table, column = key.split(".", 1)
        catalog.columns[(table, column)] = {"is_nullable": nullable, "data_type": "?"}
    catalog.row_counts = dict(record.get("row_counts") or {})
    return catalog


async def _collect_catalog(catalog: SchemaCatalog) -> None:
    import sqlalchemy as sa

    from app.core.database import engine  # noqa: PLC0415 - 延迟 import

    # 🔴 `connect()` 而不是 `begin()`：对生产库的唯一承诺是只读，不开写事务。
    async with engine.connect() as conn:
        for row in (await conn.execute(sa.text(_SQL_CONSTRAINTS))).mappings().all():
            catalog.constraints[(row["table_name"], row["name"])] = {
                "definition": row["definition"],
                "contype": row["contype"],
            }
        for row in (await conn.execute(sa.text(_SQL_INDEXES))).mappings().all():
            catalog.indexes[(row["table_name"], row["name"])] = row["definition"]
        for row in (await conn.execute(sa.text(_SQL_TRIGGERS))).mappings().all():
            catalog.triggers[(row["table_name"], row["name"])] = row["definition"]
        for row in (await conn.execute(sa.text(_SQL_FUNCTIONS))).mappings().all():
            catalog.functions[row["name"]] = row["definition"]
        for row in (await conn.execute(sa.text(_SQL_COLUMNS))).mappings().all():
            catalog.columns[(row["table_name"], row["column_name"])] = {
                "is_nullable": row["is_nullable"],
                "data_type": row["data_type"],
            }
        for table in PRODUCTION_ROW_TABLES:
            catalog.row_counts[table] = int(
                (await conn.execute(sa.text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608
            )
    await engine.dispose()


def read_schema_catalog() -> SchemaCatalog:
    _ensure_backend_on_path()
    catalog = SchemaCatalog(readable=False)
    try:
        asyncio.run(_collect_catalog(catalog))
    except Exception as exc:  # noqa: BLE001 - 不可读本身要如实报告，不得静默当通过
        catalog.error = f"{type(exc).__name__}: {exc}"
        return catalog
    catalog.readable = True
    return catalog


@dataclass(frozen=True)
class DdlRequirement:
    """一条 schema 侧结构要求。

    `must_contain` 是**定义里必须逐片段出现**的文本 —— 只查「同名对象存在」会被
    「索引改名不变但少一列」绕过（教训 16 / 本 spec 反复踩的坑）。
    """

    kind: str  # constraint | index | trigger | function | not_null | absent_column
    table: str
    name: str
    must_contain: tuple[str, ...] = ()

    def evaluate(self, catalog: SchemaCatalog) -> dict[str, Any]:
        if self.kind == "not_null":
            actual = catalog.column_is_nullable(self.table, self.name)
            return {
                "kind": self.kind,
                "target": f"{self.table}.{self.name}",
                "present": actual is not None,
                "actual": actual,
                "missing_fragments": [] if actual == "NO" else ["is_nullable=NO"],
                "satisfied": actual == "NO",
                "definition": actual,
            }
        if self.kind == "absent_column":
            actual = catalog.column_is_nullable(self.table, self.name)
            return {
                "kind": self.kind,
                "target": f"{self.table}.{self.name}",
                "present": actual is None,
                "actual": actual,
                "missing_fragments": [] if actual is None else ["column_exists"],
                "satisfied": actual is None,
                "definition": None,
            }
        lookup: Callable[..., str | None] = {
            "constraint": catalog.constraint_def,
            "index": catalog.index_def,
            "trigger": catalog.trigger_def,
        }.get(self.kind, lambda *_: None)
        definition = (
            catalog.function_def(self.name)
            if self.kind == "function"
            else lookup(self.table, self.name)
        )
        missing = [frag for frag in self.must_contain if frag not in (definition or "")]
        return {
            "kind": self.kind,
            "target": f"{self.table}.{self.name}" if self.table else self.name,
            "present": definition is not None,
            "missing_fragments": missing,
            "satisfied": definition is not None and not missing,
            "definition": definition,
        }


# ════════════════════════════════════════════════════════════════════════════
# §3 行为侧：一条不变量 = 一组「臂」，每臂声明期望并现测
# ════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class BehaviourArm:
    """一条行为臂。

    * `accepted` —— **对照组**。合法形态必须真的插进去；对照组不过说明整条判据度量的
      根本不是那条约束（教训 5）。
    * `rejected` —— 非法形态必须被**它自己声明的那条约束**拒绝。`reject_signature`
      必填：只比「抛了异常」会把 NOT NULL、FK、别的 CHECK 全算成通过（教训 1）。
    * `measure` —— 收敛/计数类结论。`expect_measure` 逐键比对，禁止只断言「非空」。
    """

    arm_id: str
    intent: str
    expectation: str
    reject_signature: tuple[str, ...] = ()
    expect_measure: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.expectation not in ("accepted", "rejected", "measure"):
            raise Task68GateError(f"臂 {self.arm_id} 的 expectation 非法: {self.expectation}")
        if self.expectation == "rejected" and not self.reject_signature:
            raise Task68GateError(
                f"臂 {self.arm_id} 声明 rejected 却没有 reject_signature —— "
                "只比「抛了异常」会把 NOT NULL/FK/别的 CHECK 都算成通过（教训 1）"
            )
        if self.expectation == "measure" and not self.expect_measure:
            raise Task68GateError(
                f"臂 {self.arm_id} 声明 measure 却没有 expect_measure —— "
                "空期望恒真（假绿第⑥源）"
            )


def evaluate_arm(arm: BehaviourArm, observation: Mapping[str, Any] | None) -> dict[str, Any]:
    """逐臂比对。观测缺失 **不是** 通过。"""
    if observation is None:
        return {
            "arm_id": arm.arm_id,
            "intent": arm.intent,
            "expectation": arm.expectation,
            "state": "missing_observation",
            "agrees": False,
            "detail": "行为侧没有这条臂的观测 —— 声明与探针脱钩（additive 注入即死代码）",
        }
    if arm.expectation == "accepted":
        agrees = bool(observation.get("accepted"))
        return {
            "arm_id": arm.arm_id,
            "intent": arm.intent,
            "expectation": arm.expectation,
            "state": "agrees" if agrees else "disagrees",
            "agrees": agrees,
            "observed": {
                "accepted": bool(observation.get("accepted")),
                "rejection": observation.get("rejection"),
            },
        }
    if arm.expectation == "rejected":
        rejection = str(observation.get("rejection") or "")
        accepted = bool(observation.get("accepted"))
        hit = [frag for frag in arm.reject_signature if frag in rejection]
        agrees = (not accepted) and len(hit) == len(arm.reject_signature)
        return {
            "arm_id": arm.arm_id,
            "intent": arm.intent,
            "expectation": arm.expectation,
            "state": "agrees" if agrees else "disagrees",
            "agrees": agrees,
            "signature": list(arm.reject_signature),
            "signature_hits": hit,
            "observed": {"accepted": accepted, "rejection": rejection},
        }
    measured = dict(observation.get("measured") or {})
    expected = dict(arm.expect_measure or {})
    mismatched = {k: (v, measured.get(k)) for k, v in expected.items() if measured.get(k) != v}
    return {
        "arm_id": arm.arm_id,
        "intent": arm.intent,
        "expectation": arm.expectation,
        "state": "agrees" if not mismatched else "disagrees",
        "agrees": not mismatched,
        "expected": expected,
        "measured": measured,
        "mismatched": {k: {"expected": a, "measured": b} for k, (a, b) in mismatched.items()},
    }


@dataclass(frozen=True)
class Invariant:
    """正文 bullet 2/3 点名的一条不变量。schema 侧与行为侧**都必须给结论**。"""

    check_id: str
    sub_bullet: int
    statement: str
    measured_by: str
    properties: tuple[int, ...]
    requirements: tuple[str, ...]
    schema_requirements: tuple[DdlRequirement, ...] = ()
    arms: tuple[BehaviourArm, ...] = ()
    #: 已现测确认 DDL 不禁止某个 facet 时填这里 —— 必须点名 owner 与「哪里真的验了它」。
    schema_gap: Mapping[str, Any] | None = None
    owner_task: str = OWNER_TASK

    def __post_init__(self) -> None:
        if not self.schema_requirements and not self.schema_gap:
            raise Task68GateError(
                f"不变量 {self.check_id} 既无 schema 要求也无已登记的 schema gap —— "
                "那样 schema 侧结论恒真（空集恒等价）"
            )
        if not self.arms:
            raise Task68GateError(
                f"不变量 {self.check_id} 没有任何行为臂 —— 生产 public schema 这些表实测 0 行，"
                "没有行为臂就等于「0 行上逐行成立」，假绿第⑥源"
            )
        if not any(a.expectation == "accepted" for a in self.arms):
            raise Task68GateError(
                f"不变量 {self.check_id} 缺对照组（accepted 臂）—— 对照组不过时"
                "「非法被拒」可能只是因为世界搭错了（教训 5）"
            )
        if not any(a.expectation in ("rejected", "measure") for a in self.arms):
            raise Task68GateError(f"不变量 {self.check_id} 只有对照组，没有任何否定/计数臂")
        if not self.properties:
            raise Task68GateError(f"不变量 {self.check_id} 未声明 Property 落点")
        if not self.requirements:
            raise Task68GateError(f"不变量 {self.check_id} 未声明 Requirement 落点")

    def evaluate(
        self, catalog: SchemaCatalog, observations: Mapping[str, Mapping[str, Any]]
    ) -> dict[str, Any]:
        if not catalog.readable:
            return {
                "check_id": self.check_id,
                "statement": self.statement,
                "sub_bullet": self.sub_bullet,
                "measured_by": self.measured_by,
                "owner_task": self.owner_task,
                "properties": [f"Property {p}" for p in self.properties],
                "requirements": list(self.requirements),
                "schema_side": {"state": "db_unreadable", "detail": _DB_UNREADABLE,
                                "requirements": [], "satisfied": False},
                "behaviour_side": {"state": "harness_error", "detail": _DB_UNREADABLE,
                                   "arms": [], "agrees": False},
                "passed": False,
            }
        evaluated = [req.evaluate(catalog) for req in self.schema_requirements]
        absent = [item for item in evaluated if not item["present"]]
        gaps = [item for item in evaluated if item["present"] and item["missing_fragments"]]
        schema_ok = all(item["satisfied"] for item in evaluated)
        schema_state = (
            "satisfied"
            if schema_ok
            else ("absent" if absent else "missing_fragments")
        )
        schema_side: dict[str, Any] = {
            "state": schema_state,
            "satisfied": schema_ok,
            "requirement_count": len(evaluated),
            "requirements": evaluated,
            "absent": [item["target"] for item in absent],
            "missing_fragments": {item["target"]: item["missing_fragments"] for item in gaps},
        }
        if self.schema_gap:
            schema_side["declared_gap"] = dict(self.schema_gap)
            if not schema_side["requirements"]:
                schema_side["state"] = "not_enforced_at_schema"

        harness = observations.get("__harness__") or {}
        arm_rows = [evaluate_arm(arm, observations.get(arm.arm_id)) for arm in self.arms]
        arms_agree = all(row["agrees"] for row in arm_rows)
        if harness.get("error"):
            behaviour_state = "harness_error"
        elif not arm_rows:
            behaviour_state = "not_executed"
        else:
            behaviour_state = "verified_on_rows" if arms_agree else "arm_mismatch"
        # 各臂拒绝理由必须互不命中：否则「它自己声明的那条约束」这句话没有约束力。
        cross_hits = _cross_signature_hits(self.arms, observations)
        behaviour_side = {
            "state": behaviour_state,
            "agrees": arms_agree and not cross_hits and not harness.get("error"),
            "arm_count": len(arm_rows),
            "arms": arm_rows,
            "cross_signature_hits": cross_hits,
            "harness_error": harness.get("error"),
            # 🔴 只记前缀，不记那串随机 hex：报告要能被 `--check` 逐字节复核，任何每轮都变的值
            #    （schema 名、耗时）都会让逐字节锁**永远**对不上，锁就等于不存在。
            "scratch_schema_prefix": _SCHEMA_PREFIX,
        }
        return {
            "check_id": self.check_id,
            "statement": self.statement,
            "sub_bullet": self.sub_bullet,
            "measured_by": self.measured_by,
            "owner_task": self.owner_task,
            "properties": [f"Property {p}" for p in self.properties],
            "requirements": list(self.requirements),
            "schema_side": schema_side,
            "behaviour_side": behaviour_side,
            "passed": bool(schema_ok and behaviour_side["agrees"]),
        }


def _cross_signature_hits(
    arms: Sequence[BehaviourArm], observations: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """一条臂的 signature 命中了**另一条**臂的拒绝理由 ⇒ 两臂在度量同一件事。

    教训 1 的直接落法：判「拒绝」不能只比异常类型，必须比原因文案且**互不命中**。
    """
    rejects = [a for a in arms if a.expectation == "rejected"]
    hits: list[dict[str, Any]] = []
    for arm in rejects:
        for other in rejects:
            if other.arm_id == arm.arm_id:
                continue
            # 两臂**故意**声明同一条 signature（同一约束的不同触发形态，例如同五元组重放 vs
            # 同五元组换 payload）是合法的；要抓的是「声明了**不同**理由却互相命中」——
            # 那说明其中一条度量的不是它自称的那条约束。
            if set(arm.reject_signature) == set(other.reject_signature):
                continue
            rejection = str((observations.get(other.arm_id) or {}).get("rejection") or "")
            if not rejection:
                continue
            if all(frag in rejection for frag in arm.reject_signature):
                hits.append(
                    {
                        "signature_of": arm.arm_id,
                        "also_matches_rejection_of": other.arm_id,
                        "signature": list(arm.reject_signature),
                        "other_signature": list(other.reject_signature),
                    }
                )
    return hits


# ════════════════════════════════════════════════════════════════════════════
# §4 正文 bullet 2/3 的逐条不变量声明
# ════════════════════════════════════════════════════════════════════════════

_FR: Final[str] = "working_paper_forcesave_request"
_CA: Final[str] = "working_paper_content_application"
_CAE: Final[str] = "working_paper_content_application_event"
_OP: Final[str] = "working_paper_sync_operation"
_CD: Final[str] = "working_paper_callback_delivery"
_CRC: Final[str] = "working_paper_callback_recovery_case"
_SI: Final[str] = "working_paper_sync_scope_index"
_CV: Final[str] = "working_paper_content_version"
_CR: Final[str] = "working_paper_content_representation"
_ES: Final[str] = "working_paper_sync_entry_state"
_DB: Final[str] = "working_paper_sync_definition_bundle"
_DA: Final[str] = "working_paper_sync_definition_artifact"
_NM: Final[str] = "working_paper_sync_definition_null_marker"
_AR: Final[str] = "working_paper_artifact"
_UC: Final[str] = "working_paper_representation_upgrade_candidate"
_CI: Final[str] = "working_paper_oo_close_intent"


def _c(table: str, name: str, *frags: str) -> DdlRequirement:
    return DdlRequirement("constraint", table, name, frags)


def _i(table: str, name: str, *frags: str) -> DdlRequirement:
    return DdlRequirement("index", table, name, frags)


def _t(table: str, name: str, *frags: str) -> DdlRequirement:
    return DdlRequirement("trigger", table, name, frags)


def _f(name: str, *frags: str) -> DdlRequirement:
    return DdlRequirement("function", "", name, frags)


def _nn(table: str, column: str) -> DdlRequirement:
    return DdlRequirement("not_null", table, column)


INVARIANTS: Final[tuple[Invariant, ...]] = (
    # ═══ 子条目 2 ═════════════════════════════════════════════════════════
    Invariant(
        check_id="forcesave_five_tuple_idempotency",
        sub_bullet=2,
        statement=(
            "forcesave request 的幂等唯一范围必须是 "
            "`(room_id, generation, initiated_by_participant_id, kind, idempotency_key)` "
            "五元组；跨 participant / 跨 kind 复用同一 Idempotency-Key 不得命中旧 request，"
            "同五元组重放必须被拒（服务层据此 409 且不返回旧 ID）。"
        ),
        measured_by="`uq_wpfr_idempotency` 的 `pg_get_constraintdef` 逐列比对 + scratch schema 四臂真插",
        properties=(10, 18, 64),
        requirements=("3.6", "5.5"),
        schema_requirements=(
            _c(_FR, "uq_wpfr_idempotency", "UNIQUE", "room_id", "generation",
               "initiated_by_participant_id", "kind", "idempotency_key"),
            _c(_FR, "ck_wpfr_kind", "forcesave", "close_capture", "recovery_claim"),
        ),
        arms=(
            BehaviourArm("fr5_baseline", "第一条 request 必须真的插进去（对照组）", "accepted"),
            BehaviourArm(
                "fr5_same_tuple_again",
                "同五元组重放必须被 uq_wpfr_idempotency 拒绝",
                "rejected",
                ("uq_wpfr_idempotency",),
            ),
            BehaviourArm(
                "fr5_same_tuple_other_payload",
                "同五元组但 payload（client base / fingerprint）不同，仍必须被同一唯一键拒绝 —— "
                "服务层的 409 语义依赖这条，否则会返回旧 ID",
                "rejected",
                ("uq_wpfr_idempotency",),
            ),
            BehaviourArm("fr5_cross_participant", "换 participant 复用同 key 必须成功", "accepted"),
            BehaviourArm("fr5_cross_kind", "换 kind 复用同 key 必须成功", "accepted"),
            BehaviourArm(
                "fr5_distinct_ids",
                "三条成功的 request 的 id 互不相同 ⇒ 跨 participant/kind 复用 key 没有返回旧 ID",
                "measure",
                expect_measure={"accepted_rows": 3, "distinct_ids": 3, "reused_old_id": False},
            ),
        ),
    ),
    Invariant(
        check_id="forcesave_frozen_fingerprint_immutable",
        sub_bullet=2,
        statement=(
            "`frozen_request_fingerprint` 与全部冻结身份列 immutable，只允许 "
            "state/accepted_at/finished_at 推进；历史 retry 必须原样使用同一 frozen 值。"
        ),
        measured_by="`trg_wpfr_frozen` + `wpsync_check_request_frozen` 定义逐列比对 + 真 UPDATE 两臂",
        properties=(28, 38),
        requirements=("6.10", "8.9"),
        schema_requirements=(
            _t(_FR, "trg_wpfr_frozen", "wpsync_check_request_frozen", "BEFORE UPDATE"),
            _f("wpsync_check_request_frozen", "frozen_request_fingerprint", "idempotency_key",
               "initiated_by_participant_id", "definition_bundle_sha256"),
        ),
        arms=(
            BehaviourArm("frz_state_advance", "推进 state/accepted_at 必须允许（对照组）", "accepted"),
            BehaviourArm(
                "frz_fingerprint_update",
                "改写 frozen_request_fingerprint 必须被 wpsync_check_request_frozen 拒绝",
                "rejected",
                ("forcesave request 的冻结字段不可变",),
            ),
            BehaviourArm(
                "frz_bundle_update",
                "改写冻结 bundle digest 必须被同一 trigger 拒绝（bundle 是 frozen identity 的一部分）",
                "rejected",
                ("forcesave request 的冻结字段不可变",),
            ),
        ),
    ),
    Invariant(
        check_id="application_key_is_sole_owner_and_unique",
        sub_bullet=2,
        statement=(
            "`application_key` UNIQUE 且**只**存在于 `working_paper_content_application`；"
            "operation 表出现同名列即失败。"
        ),
        measured_by="inline UNIQUE 的 constraintdef + operation 表列缺席现测 + 同 key 二次插入",
        properties=(18, 64),
        requirements=("5.5",),
        schema_requirements=(
            _c(_CA, f"{_CA}_application_key_key", "UNIQUE", "application_key"),
            _c(_CA, "ck_wpca_application_key", "wpsync_is_digest"),
            DdlRequirement("absent_column", _OP, "application_key"),
        ),
        arms=(
            BehaviourArm("ak_baseline", "第一条 application 必须真的插进去（对照组）", "accepted"),
            BehaviourArm(
                "ak_same_key",
                "同 application_key 的第二条 application 必须被唯一键拒绝",
                "rejected",
                ("application_key",),
            ),
            BehaviourArm(
                "ak_operation_column_absent",
                "operation 表不得有 application_key 列（现测 information_schema）",
                "measure",
                expect_measure={"operation_has_application_key": False},
            ),
        ),
    ),
    Invariant(
        check_id="application_origin_immutable_effective_monotonic",
        sub_bullet=2,
        statement=(
            "`origin_request_sequence` 不可变；`effective_request_sequence` 只可 GREATEST "
            "单调提升且恒 >= origin；同一 application 的更高 sequence 只 fold，不 self-supersede。"
        ),
        measured_by="`ck_wpca_effective_ge_origin` + `trg_wpca_mutation` 定义比对 + 五臂真 UPDATE/INSERT",
        properties=(18, 36, 62),
        requirements=("4.11", "8.5", "5.5"),
        schema_requirements=(
            _c(_CA, "ck_wpca_effective_ge_origin", "effective_request_sequence",
               "origin_request_sequence"),
            _c(_CA, "ck_wpca_no_self_supersede", "superseded_by_application_id"),
            _t(_CA, "trg_wpca_mutation", "wpsync_check_application_mutation", "BEFORE UPDATE"),
            _f("wpsync_check_application_mutation", "origin_request_sequence",
               "effective_request_sequence 只可单调提升", "application_key"),
        ),
        arms=(
            BehaviourArm("eff_raise", "提升 effective sequence 必须允许（对照组）", "accepted"),
            BehaviourArm(
                "eff_lower",
                "下调 effective sequence 必须被 wpsync_check_application_mutation 拒绝",
                "rejected",
                ("effective_request_sequence 只可单调提升",),
            ),
            BehaviourArm(
                "eff_origin_update",
                "改写 origin_request_sequence 必须被拒 —— 实测由 "
                "`wpsync_check_application_identity` 的「必须等于 origin request 的 "
                "request_sequence」分支先命中（identity trigger 名字排在 mutation trigger 前）",
                "rejected",
                ("origin_request_sequence", "必须等于 origin request 的 request_sequence"),
            ),
            BehaviourArm(
                "eff_identity_column_update",
                "改写 identity 列（adapter_id）必须被 `wpsync_check_application_mutation` 的 "
                "identity 分支拒绝 —— 这条单独立臂，否则「identity 不可变」这条分支在本报告里"
                "从未被真正触发过（origin 那条被 identity trigger 抢先）",
                "rejected",
                ("content application 的 identity 列",),
            ),
            BehaviourArm(
                "eff_insert_below_origin",
                "插入 effective < origin 必须被 ck_wpca_effective_ge_origin 拒绝",
                "rejected",
                ("ck_wpca_effective_ge_origin",),
            ),
            BehaviourArm(
                "eff_self_supersede",
                "self-supersede 必须被 ck_wpca_no_self_supersede 拒绝",
                "rejected",
                ("ck_wpca_no_self_supersede",),
            ),
        ),
    ),
    Invariant(
        check_id="application_fold_writes_room_canonical_fence",
        sub_bullet=2,
        statement=(
            "`sequence_folded` event 必须同事务记录被折叠的 request 与 room canonical "
            "durable fence；同一 request 对同一 application 只能 fold 一次。"
        ),
        measured_by="`ck_wpcae_fold_requires_request` / `ck_wpcae_fold_requires_room_fence` / "
                    "`uq_wpcae_fold_once` 定义比对 + 四臂真插",
        properties=(18, 62, 68),
        requirements=("4.11", "13.5", "5.5"),
        schema_requirements=(
            _c(_CAE, "ck_wpcae_fold_requires_request", "sequence_folded", "folded_request_id"),
            _c(_CAE, "ck_wpcae_fold_requires_room_fence", "sequence_folded",
               "room_latest_durable_sequence"),
            _i(_CAE, "uq_wpcae_fold_once", "UNIQUE", "application_id", "folded_request_id",
               "sequence_folded"),
            _c(_CAE, "ck_wpcae_effective_ge_origin", "effective_request_sequence"),
        ),
        arms=(
            BehaviourArm("fold_full", "带 request + room fence 的 fold event 必须插入（对照组）",
                         "accepted"),
            BehaviourArm(
                "fold_no_request",
                "缺 folded_request_id 的 fold event 必须被 ck_wpcae_fold_requires_request 拒绝",
                "rejected",
                ("ck_wpcae_fold_requires_request",),
            ),
            BehaviourArm(
                "fold_no_room_fence",
                "缺 room_latest_durable_sequence 的 fold event 必须被 "
                "ck_wpcae_fold_requires_room_fence 拒绝（fence 必须同事务写）",
                "rejected",
                ("ck_wpcae_fold_requires_room_fence",),
            ),
            BehaviourArm(
                "fold_twice_same_request",
                "同 request 对同 application 第二次 fold 必须被 uq_wpcae_fold_once 拒绝",
                "rejected",
                ("uq_wpcae_fold_once",),
            ),
        ),
    ),
    Invariant(
        check_id="operation_nullable_primary_application_fk",
        sub_bullet=2,
        statement=(
            "operation 的 `application_id` 是 nullable UNIQUE primary FK：多个未归组 shell "
            "可以同时 NULL，但一个 application 最多绑定一个 primary operation；每个 request "
            "最多一个 shell。"
        ),
        measured_by="`uq_wpso_application` / `uq_wpso_request` 定义比对 + 三臂真插",
        properties=(18, 64, 68),
        requirements=("5.5", "13.5"),
        schema_requirements=(
            _c(_OP, "uq_wpso_application", "UNIQUE", "application_id"),
            _c(_OP, "uq_wpso_request", "UNIQUE", "forcesave_request_id"),
            _c(_OP, "ck_wpso_bound_requires_application", "application_bound"),
        ),
        arms=(
            BehaviourArm(
                "opfk_two_null_shells",
                "两个 application_id 均为 NULL 的 shell 必须都能插入（nullable UNIQUE 允许多 NULL）",
                "accepted",
            ),
            BehaviourArm(
                "opfk_same_application_twice",
                "两个 operation 绑定同一 application 必须被 uq_wpso_application 拒绝",
                "rejected",
                ("uq_wpso_application",),
            ),
            BehaviourArm(
                "opfk_same_request_twice",
                "同一 request 的第二个 shell 必须被 uq_wpso_request 拒绝",
                "rejected",
                ("uq_wpso_request",),
            ),
        ),
    ),
    Invariant(
        check_id="operation_duplicate_is_direct_only",
        sub_bullet=2,
        statement=(
            "`duplicate_of_operation_id` 只能直指已绑定 application 的 direct primary："
            "禁 self、禁链、禁环、禁 stranded duplicate、禁跨 scope，且 duplicate 自身 "
            "application_id 必为 NULL 且状态终态。"
        ),
        measured_by="`ck_wpso_no_self_duplicate` / `ck_wpso_duplicate_shape` / "
                    "`ck_wpso_not_both_owners` + `wpsync_check_operation_duplicate_link` + 六臂真插",
        properties=(18, 68),
        requirements=("5.5", "13.5"),
        schema_requirements=(
            _c(_OP, "ck_wpso_no_self_duplicate", "duplicate_of_operation_id"),
            _c(_OP, "ck_wpso_duplicate_shape", "duplicate", "application_id IS NULL"),
            _c(_OP, "ck_wpso_not_both_owners", "application_id IS NULL",
               "duplicate_of_operation_id IS NULL"),
            _f("wpsync_check_operation_duplicate_link", "direct primary",
               "禁止链/环与 stranded", "跨 scope"),
        ),
        arms=(
            BehaviourArm("dup_direct", "duplicate 直指 primary 必须允许（对照组）", "accepted"),
            BehaviourArm(
                "dup_self",
                "self duplicate 必须被 ck_wpso_no_self_duplicate 拒绝",
                "rejected",
                ("ck_wpso_no_self_duplicate",),
            ),
            # 🔴 实测：`ck_wpso_not_both_owners` 被 `ck_wpso_duplicate_shape` **结构性遮蔽** ——
            #    不存在只违反前者的输入（app 非空 + duplicate 非空时，state 无论是否 'duplicate'
            #    都同时违反 shape）。所以行为侧只能观测到 shape 那条；`not_both_owners` 仍在
            #    schema 侧逐片段核对（它是意图的显式记录，删掉它 schema 侧立刻红）。
            BehaviourArm(
                "dup_with_application",
                "duplicate 同时绑定 application 必须被拒 —— 实测由 `ck_wpso_duplicate_shape` 命中；"
                "`ck_wpso_not_both_owners` 是被它结构性遮蔽的同义约束（无输入能单独违反）",
                "rejected",
                ("ck_wpso_duplicate_shape",),
            ),
            BehaviourArm(
                "dup_chain",
                "duplicate 指向另一个 duplicate（链/环）必须被 duplicate_link trigger 拒绝",
                "rejected",
                ("不是 direct primary",),
            ),
            BehaviourArm(
                "dup_stranded_target",
                "duplicate 指向尚未绑定 application 的 shell（stranded）必须被同一 trigger 拒绝",
                "rejected",
                ("不是 direct primary",),
            ),
            BehaviourArm(
                "dup_rebind",
                "已绑定 application 的 operation 改绑/解绑必须被 binding_immutable trigger 拒绝",
                "rejected",
                ("禁止改绑/解绑",),
            ),
        ),
    ),
    Invariant(
        check_id="n_shells_converge_one_primary_rest_terminal",
        sub_bullet=2,
        statement=(
            "N 个 different-request 同 application key 的 shell，最终恰好 1 个 primary "
            "（application_id 非空、duplicate 指针空）+ N-1 个 terminal duplicate，"
            "且零 stranded、零链、零环。"
        ),
        measured_by="scratch schema 真造 4 request + 4 shell 后现算收敛形态",
        properties=(18, 68),
        requirements=("5.5", "13.5"),
        schema_requirements=(
            _c(_OP, "uq_wpso_application", "UNIQUE", "application_id"),
            _c(_OP, "ck_wpso_duplicate_shape", "duplicate"),
        ),
        arms=(
            BehaviourArm("nshell_build", "4 个 request + 4 个 shell 必须全部建成（对照组）",
                         "accepted"),
            BehaviourArm(
                "nshell_convergence",
                "收敛后：1 primary / 3 terminal duplicate / 0 stranded / 0 链 / 0 环 / 1 application",
                "measure",
                expect_measure={
                    "shells": 4,
                    "primary": 1,
                    "terminal_duplicates": 3,
                    "stranded": 0,
                    "chains": 0,
                    "cycles": 0,
                    "applications": 1,
                },
            ),
        ),
    ),
    Invariant(
        check_id="recovery_three_entities_zero_before_claim",
        sub_bullet=2,
        statement=(
            "recovery case 在 claim 成功前（含 download-only / quarantined / expired 终态）"
            "request / application / operation 三实体恒为空；`application_created` 必须一次性"
            "写入三实体 + claiming participant + prior confirmation + frozen bundle。"
        ),
        measured_by="`ck_wpcrc_pre_claim_zero_entities` / `ck_wpcrc_claimed_all_entities` + "
                    "`wpsync_check_recovery_incoming` + 五臂真插",
        properties=(18, 44),
        requirements=("5.5", "10.3"),
        schema_requirements=(
            _c(_CRC, "ck_wpcrc_pre_claim_zero_entities", "application_created",
               "recovery_request_id IS NULL", "application_id IS NULL", "operation_id IS NULL"),
            _c(_CRC, "ck_wpcrc_claimed_all_entities", "application_created",
               "claimed_by_participant_id", "prior_confirmation_id",
               "claimed_definition_bundle_id"),
            _f("wpsync_check_recovery_incoming", "state=durable", "quarantined 永不创建 application"),
        ),
        arms=(
            BehaviourArm("rec_unclaimed", "unclaimed 且三实体全空必须插入（对照组）", "accepted"),
            BehaviourArm(
                "rec_unclaimed_with_application",
                "unclaimed 却带 application 必须被 ck_wpcrc_pre_claim_zero_entities 拒绝",
                "rejected",
                ("ck_wpcrc_pre_claim_zero_entities",),
            ),
            BehaviourArm(
                "rec_download_only_with_operation",
                "download_only 终态带 operation 必须被同一 CHECK 拒绝",
                "rejected",
                ("ck_wpcrc_pre_claim_zero_entities",),
            ),
            BehaviourArm(
                "rec_claimed_partial",
                "application_created 缺 operation_id 必须被 ck_wpcrc_claimed_all_entities 拒绝",
                "rejected",
                ("ck_wpcrc_claimed_all_entities",),
            ),
            BehaviourArm(
                "rec_quarantined_incoming",
                "quarantined incoming 上 claim 必须被 wpsync_check_recovery_incoming 拒绝",
                "rejected",
                ("quarantined 永不创建 application",),
            ),
            BehaviourArm(
                "rec_claimed_full",
                "一次性写全三实体 + participant + prior confirmation + frozen bundle 必须成功",
                "accepted",
            ),
            BehaviourArm(
                "rec_canonical_convergence",
                "claim 后 primary/duplicate canonical 收敛：case 绑定的 operation 恰是该 "
                "application 的唯一 primary",
                "measure",
                expect_measure={"case_operation_is_primary": True, "primaries_for_app": 1},
            ),
        ),
    ),
    Invariant(
        check_id="delivery_durable_at_is_the_only_ownership_gate",
        sub_bullet=2,
        statement=(
            "delivery 归属只以 immutable `durable_at` 判定：durable 时恰有一个 owner"
            "（application XOR recovery），任何阶段禁双 owner，post-durable error 保留 owner，"
            "`request` 与 `application` 之间**不做** XOR（可同时非空）。"
        ),
        measured_by="`ck_wpcd_durable_exactly_one_owner` / `ck_wpcd_no_double_owner` / "
                    "`ck_wpcd_durable_state_requires_fact` / `ck_wpcd_unmatched_zero_entities` + "
                    "`wpsync_check_delivery_durable_fact` + 七臂真插/真改",
        properties=(18, 19),
        requirements=("5.5", "5.8"),
        schema_requirements=(
            _c(_CD, "ck_wpcd_durable_exactly_one_owner", "durable_at IS NULL",
               "application_id IS NOT NULL", "callback_recovery_case_id IS NOT NULL"),
            _c(_CD, "ck_wpcd_no_double_owner", "application_id IS NULL",
               "callback_recovery_case_id IS NULL"),
            _c(_CD, "ck_wpcd_durable_state_requires_fact", "durable_at IS NOT NULL"),
            _c(_CD, "ck_wpcd_unmatched_zero_entities", "unmatched",
               "callback_recovery_case_id IS NOT NULL"),
            _c(_CD, "ck_wpcd_durable_requires_incoming", "incoming_artifact_id IS NOT NULL"),
            _f("wpsync_check_delivery_durable_fact", "post-durable 不得丢弃 application owner",
               "immutable durable fact"),
        ),
        schema_gap={
            "facet": "pre_durable_rejected_or_error_zero_owner",
            "measured": "arm `dlv_pre_durable_owner` 现测：DDL **接受** "
                        "`state='rejected' AND durable_at IS NULL AND application_id IS NOT NULL`",
            "why_not_a_defect_of_this_task": "正文要求本任务如实报告，不授权改生产代码/迁移",
            "enforced_by": "服务层 `backend/app/services/workpaper_sync/callback_delivery.py`",
            "owner_task": "22",
            "independently_confirmed_by": [
                "backend/tests/workpaper_sync/test_task10_repository_pg.py::"
                "TestDeliveryOwnership::test_delivery_ownership_pre_and_post_durable",
                "backend/tests/workpaper_sync/test_task22_callback_claim_pg.py::"
                "TestOwnershipRows::test_forbidden_ownership_rows_are_rejected_by_their_declared_constraint",
            ],
            "blocking_point": "BP-68-1",
        },
        arms=(
            BehaviourArm("dlv_durable_one_owner", "durable + 恰一 application owner 必须插入（对照组）",
                         "accepted"),
            BehaviourArm(
                "dlv_durable_zero_owner",
                "durable 但零 owner 必须被 ck_wpcd_durable_exactly_one_owner 拒绝",
                "rejected",
                ("ck_wpcd_durable_exactly_one_owner",),
            ),
            BehaviourArm(
                "dlv_double_owner",
                "同时带 application 与 recovery owner 必须被 ck_wpcd_no_double_owner 拒绝",
                "rejected",
                ("ck_wpcd_no_double_owner",),
            ),
            BehaviourArm(
                "dlv_durable_state_no_fact",
                "state=durable 而 durable_at 为空必须被 ck_wpcd_durable_state_requires_fact 拒绝",
                "rejected",
                ("ck_wpcd_durable_state_requires_fact",),
            ),
            BehaviourArm(
                "dlv_unmatched_with_request",
                "unmatched 带 request 必须被 ck_wpcd_unmatched_zero_entities 拒绝",
                "rejected",
                ("ck_wpcd_unmatched_zero_entities",),
            ),
            BehaviourArm(
                "dlv_request_and_application",
                "durable correlated 同时带 request 与 application 必须允许 —— 两者**不做** XOR",
                "accepted",
            ),
            BehaviourArm(
                "dlv_post_durable_drop_owner",
                "post-durable 清空 application owner 必须被 wpsync_check_delivery_durable_fact 拒绝",
                "rejected",
                ("post-durable 不得丢弃 application owner",),
            ),
            BehaviourArm(
                "dlv_post_durable_error_keeps_owner",
                "post-durable 转 error 但保留 owner 必须允许（error 不清 owner）",
                "accepted",
            ),
            BehaviourArm(
                "dlv_pre_durable_owner",
                "🔴 gap 探针：pre-durable rejected 带 owner —— DDL 现测**接受**，"
                "说明这条只由服务层把住（见 schema_gap）",
                "measure",
                expect_measure={"ddl_accepts_pre_durable_owner": True},
            ),
        ),
    ),
    Invariant(
        check_id="scope_index_tombstone_and_opaque_resource_id",
        sub_bullet=2,
        statement=(
            "scope index 的 `(resource_kind, resource_id)` tombstone 永不物理删除 / 永不清空 / "
            "id 永不复用；scope 列不可变（禁跨 scope 重绑）；`resource_id` 必须 opaque —— "
            "纯数字 numeric revision 被 DB 拒绝，`content_version` kind 只接 UUID。"
        ),
        measured_by="`trg_wpssi_no_delete` / `trg_wpssi_update_guard` / "
                    "`ck_wpssi_opaque_resource_id` / `ck_wpssi_content_version_uuid` + "
                    "`wpsync_is_opaque_resource_id` + 七臂真插/真删/真改",
        properties=(37, 43),
        requirements=("8.7", "10.10", "14.13"),
        schema_requirements=(
            _t(_SI, "trg_wpssi_no_delete", "wpsync_forbid_scope_index_delete", "BEFORE DELETE"),
            _t(_SI, "trg_wpssi_update_guard", "wpsync_check_scope_index_update", "BEFORE UPDATE"),
            _c(_SI, "ck_wpssi_opaque_resource_id", "wpsync_is_opaque_resource_id"),
            _c(_SI, "ck_wpssi_content_version_uuid", "content_version", "wpsync_is_uuid_text"),
            _f("wpsync_is_opaque_resource_id", "[0-9]+"),
            _f("wpsync_forbid_scope_index_delete", "禁止物理删除"),
            _f("wpsync_check_scope_index_update", "tombstone 不可清空", "禁止跨 scope 重绑或 id 复用"),
        ),
        arms=(
            BehaviourArm("si_insert", "合法 opaque resource_id 必须插入（对照组）", "accepted"),
            BehaviourArm("si_retire", "设置 retired_at 退役必须允许（对照组）", "accepted"),
            BehaviourArm(
                "si_delete",
                "物理 DELETE 必须被 wpsync_forbid_scope_index_delete 拒绝",
                "rejected",
                ("禁止物理删除",),
            ),
            BehaviourArm(
                "si_clear_tombstone",
                "把 retired_at 清回 NULL 必须被 wpsync_check_scope_index_update 拒绝",
                "rejected",
                ("tombstone 不可清空",),
            ),
            BehaviourArm(
                "si_rebind_scope",
                "改 wp/entry（跨 scope 重绑）必须被同一 trigger 拒绝",
                "rejected",
                ("禁止跨 scope 重绑或 id 复用",),
            ),
            BehaviourArm(
                "si_numeric_resource_id",
                "纯数字 resource_id（numeric revision）必须被 ck_wpssi_opaque_resource_id 拒绝",
                "rejected",
                ("ck_wpssi_opaque_resource_id",),
            ),
            BehaviourArm(
                "si_content_version_not_uuid",
                "`content_version` kind 的非 UUID resource_id 必须被 "
                "ck_wpssi_content_version_uuid 拒绝",
                "rejected",
                ("ck_wpssi_content_version_uuid",),
            ),
        ),
    ),
    Invariant(
        check_id="content_version_opaque_uuid_no_cross_wp_collision",
        sub_bullet=2,
        statement=(
            "content version 只以 opaque `version_id` UUID 定位；numeric revision 仅 per-wp "
            "唯一 —— 两个 wp 可以各有 revision 1 且不碰撞，同 wp 重复 revision 被拒；"
            "numeric revision 作 route/resource key 在 scope index 层就失败。"
        ),
        measured_by="`uq_wpcv_wp_revision` + `wpsync_check_content_version_immutable` + 四臂真插",
        properties=(37, 7),
        requirements=("8.7", "2.10", "14.13"),
        schema_requirements=(
            _c(_CV, "uq_wpcv_wp_revision", "UNIQUE", "wp_id", "revision"),
            _c(_CV, "ck_wpcv_no_self_parent", "parent_version_id"),
            _t(_CV, "trg_wpcv_immutable", "wpsync_check_content_version_immutable"),
        ),
        arms=(
            BehaviourArm(
                "cv_two_wps_same_revision",
                "两个 wp 各有 revision=1 必须都插入（对照组：numeric revision 不是全局 key）",
                "accepted",
            ),
            BehaviourArm(
                "cv_same_wp_same_revision",
                "同 wp 重复 revision 必须被 uq_wpcv_wp_revision 拒绝",
                "rejected",
                ("uq_wpcv_wp_revision",),
            ),
            BehaviourArm(
                "cv_update_immutable",
                "UPDATE 历史 content version 必须被 immutable trigger 拒绝",
                "rejected",
                ("immutable 历史行，禁止 UPDATE",),
            ),
            BehaviourArm(
                "cv_numeric_as_resource_key",
                "把 numeric revision 当 content_version 的 resource key 写进 scope index 必须失败",
                "rejected",
                ("ck_wpssi",),
            ),
        ),
    ),
    # ═══ 子条目 3 ═════════════════════════════════════════════════════════
    Invariant(
        check_id="bundle_slots_not_null_check_and_trigger",
        sub_bullet=3,
        statement=(
            "definition bundle 的九个 slot 列全部 NOT NULL；digest 必须是真实非空非零 hex；"
            "slot type 只能是 `definition` 或版本化 typed null marker id；`trg_wpsdb_slots` "
            "逐 slot 现算 child。"
        ),
        measured_by="九列 `is_nullable` + 四个 digest CHECK + 三个 slot_type CHECK + "
                    "`trg_wpsdb_slots` / `wpsync_assert_bundle_slot` 定义 + 五臂真插",
        properties=(50, 67, 28),
        requirements=("12.6", "6.18", "6.10"),
        schema_requirements=(
            _nn(_DB, "template_slot_type"),
            _nn(_DB, "template_slot_ref"),
            _nn(_DB, "template_slot_digest"),
            _nn(_DB, "instrumentation_slot_type"),
            _nn(_DB, "instrumentation_slot_ref"),
            _nn(_DB, "instrumentation_slot_digest"),
            _nn(_DB, "contract_slot_type"),
            _nn(_DB, "contract_slot_ref"),
            _nn(_DB, "contract_slot_digest"),
            _c(_DB, "ck_wpsdb_template_digest", "wpsync_is_digest"),
            _c(_DB, "ck_wpsdb_contract_slot_type", "definition", "contract:none:v"),
            _t(_DB, "trg_wpsdb_slots", "wpsync_check_bundle_slots"),
            _f("wpsync_assert_bundle_slot", "slot 缺失", "digest 非法", "未登记的 typed null marker"),
        ),
        arms=(
            BehaviourArm("bs_legal", "三 slot 全 approved definition 的 bundle 必须插入（对照组）",
                         "accepted"),
            # 🔴 下面三条的实测拒绝方是 **BEFORE INSERT trigger**，不是同名 CHECK ——
            #    PostgreSQL 的 BEFORE 触发器先于 NOT NULL / CHECK 求值。CHECK 仍作为
            #    schema 侧要求逐片段核对（在 `schema_requirements` 里），但行为侧的
            #    signature 必须写触发器真实文案，否则这三条臂在度量别的东西。
            BehaviourArm(
                "bs_null_ref",
                "slot ref 为 SQL NULL 必须被拒（实测 `wpsync_assert_bundle_slot` 先命中，"
                "NOT NULL 在其后）",
                "rejected",
                ("slot 缺失（type/ref/digest 均不得为 NULL）",),
            ),
            BehaviourArm(
                "bs_zero_digest",
                "全零 digest 必须被拒（`wpsync_is_digest` 经 `wpsync_assert_bundle_slot` 判定）",
                "rejected",
                ("slot digest 非法（空串/全零/非 hex 均拒绝）",),
            ),
            BehaviourArm(
                "bs_bad_slot_type",
                "既非 `definition` 也非版本化 marker 的 slot type 必须被拒 —— 实测走 marker 分支"
                "查 registry 未命中（`ck_wpsdb_*_slot_type` 排在 trigger 之后，因此 CHECK 只作"
                "schema 侧兜底）",
                "rejected",
                ("引用未登记的 typed null marker",),
            ),
            BehaviourArm(
                "bs_digest_mismatch",
                "slot digest 与 child 实际 sha256 不一致必须被 wpsync_assert_bundle_slot 拒绝",
                "rejected",
                ("slot digest 与 child 实际 sha256 不一致",),
            ),
        ),
    ),
    Invariant(
        check_id="projection_contract_requires_approved_definition_children",
        sub_bullet=3,
        statement=(
            "authority model = `projection_contract` 的 bundle，template/instrumentation/"
            "contract 三 slot 必须全为 **approved definition** child；typed null marker 与 "
            "candidate 状态 child 一律拒绝。"
        ),
        measured_by="`wpsync_check_bundle_slots` 的 projection_contract 分支 + "
                    "`ck_wpsda_authority_model_type` + 四臂真插",
        properties=(50, 67, 28),
        requirements=("6.18", "12.6", "6.10"),
        schema_requirements=(
            _f("wpsync_check_bundle_slots", "projection_contract bundle",
               "三 slot 必须全为 approved definition"),
            _c(_DA, "ck_wpsda_authority_model_type", "projection_contract",
               "custom_authoritative_ooxml", "opaque_single_onlyoffice"),
            _c(_DA, "ck_wpsda_state", "candidate", "approved", "retired"),
        ),
        arms=(
            BehaviourArm("pc_three_definitions", "三 approved definition 的 projection bundle 必须插入",
                         "accepted"),
            BehaviourArm(
                "pc_marker_substitution",
                "projection_contract bundle 用 typed null marker 顶替 contract 必须被拒",
                "rejected",
                ("三 slot 必须全为 approved definition",),
            ),
            BehaviourArm(
                "pc_candidate_child",
                "child 处于 candidate 状态必须被 wpsync_assert_bundle_slot 拒绝",
                "rejected",
                ("slot child 必须 approved",),
            ),
            BehaviourArm(
                "pc_authority_model_type_null",
                "authority_model definition 缺 authority_model_type 必须被 "
                "ck_wpsda_authority_model_type 拒绝（三值逻辑陷阱）",
                "rejected",
                ("ck_wpsda_authority_model_type",),
            ),
        ),
    ),
    Invariant(
        check_id="typed_null_marker_registry_only",
        sub_bullet=3,
        statement=(
            "optional child 的 typed null marker 只能引用 registry 中**已登记且 active** 的"
            "版本化 marker，且 digest 必须与 registry 一致；未登记 id、错槽位、"
            "伪造 digest 一律拒绝。"
        ),
        measured_by="`ck_wpsnm_versioned_id` + `wpsync_assert_bundle_slot` 的 marker 分支 + 四臂真插",
        properties=(50, 67),
        requirements=("12.6", "6.18"),
        schema_requirements=(
            _c(_NM, "ck_wpsnm_versioned_id", "template|instrumentation|contract", "none:v"),
            _c(_NM, "ck_wpsnm_state", "active", "retired"),
            _f("wpsync_assert_bundle_slot", "未登记的 typed null marker",
               "marker digest 与 registry 不一致", "槽位的 marker"),
        ),
        arms=(
            BehaviourArm(
                "tm_registered_marker",
                "custom authority bundle 用已登记 marker + 真 digest 必须插入（对照组）",
                "accepted",
            ),
            BehaviourArm(
                "tm_unregistered_marker",
                "未登记 marker id 必须被 wpsync_assert_bundle_slot 拒绝",
                "rejected",
                ("未登记的 typed null marker",),
            ),
            BehaviourArm(
                "tm_wrong_slot_marker",
                "把 template 槽的 marker 用在 contract 槽必须被拒",
                "rejected",
                ("槽位的 marker",),
            ),
            BehaviourArm(
                "tm_forged_digest",
                "伪造 marker digest 必须被拒",
                "rejected",
                ("marker digest 与 registry 不一致",),
            ),
        ),
    ),
    Invariant(
        check_id="candidate_never_current_never_resolvable",
        sub_bullet=3,
        statement=(
            "upgrade candidate 永不 published/durable；entry current pointer 只接 published "
            "canonical/projection artifact；candidate finalize 出的 representation 必须绑定"
            "同一 content version（禁止推进 content revision）。"
        ),
        measured_by="`ck_wpa_candidate_never_published` + `trg_wpruc_guard` + "
                    "`trg_wpses_pointer` 定义 + 四臂真插",
        properties=(5, 67, 4),
        requirements=("2.4", "6.18", "2.1"),
        schema_requirements=(
            _c(_AR, "ck_wpa_candidate_never_published", "upgrade_candidate", "staged",
               "candidate", "orphan"),
            _t(_UC, "trg_wpruc_guard", "wpsync_check_upgrade_candidate"),
            _t(_ES, "trg_wpses_pointer", "wpsync_check_entry_state_pointer"),
            _f("wpsync_check_upgrade_candidate", "永不 published/durable",
               "禁止推进 content revision"),
            _f("wpsync_check_entry_state_pointer", "必须指向 published artifact"),
        ),
        arms=(
            BehaviourArm("cand_staged", "upgrade_candidate artifact 处于 staged 必须插入（对照组）",
                         "accepted"),
            BehaviourArm(
                "cand_published_artifact",
                "upgrade_candidate artifact 置 published 必须被 "
                "ck_wpa_candidate_never_published 拒绝",
                "rejected",
                ("ck_wpa_candidate_never_published",),
            ),
            BehaviourArm(
                "cand_durable_artifact",
                "upgrade_candidate artifact 置 durable 必须被同一 CHECK 拒绝",
                "rejected",
                ("ck_wpa_candidate_never_published",),
            ),
            BehaviourArm(
                "cand_pointer_to_staged",
                "entry current pointer 指向 staged artifact 的 representation 必须被 "
                "trg_wpses_pointer 拒绝",
                "rejected",
                ("必须指向 published artifact",),
            ),
            BehaviourArm(
                "cand_pointer_to_published",
                "entry current pointer 指向 published artifact 必须允许（对照组）",
                "accepted",
            ),
        ),
    ),
    Invariant(
        check_id="incoming_durable_or_quarantined_only",
        sub_bullet=3,
        statement=(
            "incoming artifact 永不 published/candidate；durable 与 quarantined 两支不可互转；"
            "quarantined 保持 `durable_at=NULL` 且只能 download-only/expire/retention。"
        ),
        measured_by="`ck_wpa_incoming_never_published` + `ck_wpa_durable_quarantine_exclusive` + "
                    "`wpsync_check_artifact_transition` + 五臂真插/真改",
        properties=(17, 19),
        requirements=("5.6", "5.8"),
        schema_requirements=(
            _c(_AR, "ck_wpa_incoming_never_published", "incoming", "staged", "durable",
               "quarantined"),
            _t(_AR, "trg_wpa_transition", "wpsync_check_artifact_transition"),
            _f("wpsync_check_artifact_transition", "quarantined 永不 release/转 durable",
               "durable 与 quarantined 两支不可互转"),
        ),
        arms=(
            BehaviourArm("inc_durable", "incoming durable 必须插入（对照组）", "accepted"),
            BehaviourArm("inc_quarantined", "incoming quarantined 且 durable_at 空必须插入（对照组）",
                         "accepted"),
            BehaviourArm(
                "inc_published",
                "incoming 置 published 必须被 ck_wpa_incoming_never_published 拒绝",
                "rejected",
                ("ck_wpa_incoming_never_published",),
            ),
            BehaviourArm(
                "inc_quarantined_to_durable",
                "quarantined→durable 必须被 wpsync_check_artifact_transition 拒绝",
                "rejected",
                ("quarantined 永不 release/转 durable",),
            ),
            BehaviourArm(
                "inc_durable_to_quarantined",
                "durable→quarantined 必须被同一 trigger 拒绝（两支不可互转）",
                "rejected",
                ("两支不可互转",),
            ),
        ),
    ),
    Invariant(
        check_id="application_incoming_fk_accepts_durable_only",
        sub_bullet=3,
        statement=(
            "application 的 `incoming_artifact_id` FK 只接 `kind=incoming, state=durable`；"
            "quarantined / staged 一律拒绝，`incoming_sha256` 必须等于 artifact 实际 digest。"
        ),
        measured_by="`wpsync_check_application_identity` 的 incoming 分支 + 四臂真插",
        properties=(17, 19, 65),
        requirements=("5.6", "5.8", "8.10"),
        schema_requirements=(
            _t(_CA, "trg_wpca_identity", "wpsync_check_application_identity"),
            _f("wpsync_check_application_identity", "必须 kind=incoming",
               "必须 state=durable", "quarantined 永不创建 application",
               "incoming_sha256 与 artifact 实际 digest 不一致"),
        ),
        arms=(
            BehaviourArm("aif_durable", "durable incoming 上建 application 必须成功（对照组）",
                         "accepted"),
            # 🔴 两臂共用一条 RAISE 文案（「必须 state=durable，实得 %（quarantined 永不创建
            #    application）」），只写「必须 state=durable」会让两臂互相命中 ⇒ 各自再钉住
            #    `实得 <state>` 那一段，才能证明拒绝的是**这一种**非法 state。
            BehaviourArm(
                "aif_quarantined",
                "quarantined incoming 上建 application 必须被拒，且拒绝理由点名 quarantined",
                "rejected",
                ("quarantined 永不创建 application", "实得 quarantined"),
            ),
            BehaviourArm(
                "aif_staged",
                "staged incoming 上建 application 必须被拒，且拒绝理由点名 staged",
                "rejected",
                ("必须 state=durable", "实得 staged"),
            ),
            BehaviourArm(
                "aif_sha_mismatch",
                "incoming_sha256 与 artifact 实际 digest 不一致必须被拒",
                "rejected",
                ("incoming_sha256 与 artifact 实际 digest 不一致",),
            ),
        ),
    ),
    Invariant(
        check_id="close_capture_partial_unique_is_at_most_one",
        sub_bullet=3,
        statement=(
            "`uq_wpfr_open_close_capture` 只证明 generation 内 **at-most-one** open "
            "close_capture；exactly-one 必须由行为测试给出：single / A-B / B-A / "
            "A terminal 前后 B close / reconciler 重入五种路径最终都恰好一条，0 或 >1 均失败。"
        ),
        measured_by="partial unique index 定义（含 4 个 open 状态与 kind 过滤）+ 五种顺序真跑",
        properties=(63, 68),
        requirements=("10.9", "13.5"),
        schema_requirements=(
            _i(_FR, "uq_wpfr_open_close_capture", "UNIQUE", "room_id", "generation",
               "close_capture", "frozen", "pending", "accepted", "correlated"),
            _c(_FR, "ck_wpfr_state", "authorization_stale", "terminal", "superseded"),
        ),
        arms=(
            BehaviourArm("cc_single", "单用户 close：恰一条 open close_capture（对照组）", "accepted"),
            BehaviourArm(
                "cc_second_open",
                "同 room/generation 第二条 open close_capture 必须被 partial unique 拒绝",
                "rejected",
                ("uq_wpfr_open_close_capture",),
            ),
            BehaviourArm(
                "cc_after_terminal",
                "前一条转 terminal 后，B 的 close_capture 必须允许（partial unique 只管 open）",
                "accepted",
            ),
            BehaviourArm(
                "cc_exactly_one_over_orders",
                "五种路径（single / A-B / B-A / A-terminal-then-B / reconciler 重入）"
                "各自最终 open close_capture 数恰为 1",
                "measure",
                expect_measure={
                    "single": 1,
                    "a_then_b": 1,
                    "b_then_a": 1,
                    "a_terminal_then_b": 1,
                    "reconciler_reentry": 1,
                    "orders_checked": 5,
                    "zero_or_more_than_one_seen": False,
                },
            ),
            BehaviourArm(
                "cc_leader_by_highest_intent_sequence",
                "打乱 created_at 与插入顺序后，leader 仍按最高 `(intent_sequence, id)` 选出",
                "measure",
                expect_measure={"leader_is_highest_intent_sequence": True, "shuffles": 3},
            ),
        ),
    ),
    Invariant(
        check_id="close_leader_promotion_and_authorization_stale",
        sub_bullet=3,
        statement=(
            "close intent 只能提升为同 room/generation 的 `close_capture` request；"
            "leader promotion 前撤权/过期必须写 `authorization_stale`（而不是静默成功），"
            "合法 successor 可接任同一 generation。"
        ),
        measured_by="`wpsync_check_close_intent_promotion` + `uq_wpoci_active` + "
                    "`ck_wpfr_state` 含 authorization_stale + 五臂真插",
        properties=(63, 43, 68),
        requirements=("10.9", "10.10", "13.5"),
        schema_requirements=(
            _t(_CI, "trg_wpoci_promotion", "wpsync_check_close_intent_promotion"),
            _f("wpsync_check_close_intent_promotion", "只能提升为 close_capture request",
               "promoted request 跨 room/generation"),
            _i(_CI, "uq_wpoci_active", "UNIQUE", "room_id", "generation", "participant_id"),
            _c(_FR, "ck_wpfr_state", "authorization_stale"),
        ),
        arms=(
            BehaviourArm("lead_promote", "提升为同 room/generation 的 close_capture 必须成功（对照组）",
                         "accepted"),
            BehaviourArm(
                "lead_promote_wrong_kind",
                "提升为 kind=forcesave 的 request 必须被 promotion trigger 拒绝",
                "rejected",
                ("只能提升为 close_capture request",),
            ),
            BehaviourArm(
                "lead_promote_cross_generation",
                "提升跨 room/generation 的 request 必须被同一 trigger 拒绝",
                "rejected",
                ("promoted request 跨 room/generation",),
            ),
            BehaviourArm(
                "lead_duplicate_active_intent",
                "同 room/generation/participant 的第二条 active intent 必须被 uq_wpoci_active 拒绝",
                "rejected",
                ("uq_wpoci_active",),
            ),
            BehaviourArm(
                "lead_authorization_stale",
                "撤权后把 request 置 `authorization_stale` 必须被接受（状态词表里有这一态）",
                "accepted",
            ),
            BehaviourArm(
                "lead_successor_same_generation",
                "合法 successor 接任后仍是同一 generation 的 open close_capture 恰一条",
                "measure",
                expect_measure={
                    "stale_request_state": "authorization_stale",
                    "successor_generation_equals_predecessor": True,
                    "open_close_captures_after_successor": 1,
                },
            ),
        ),
    ),
    Invariant(
        check_id="application_key_frozen_bundle_does_not_fold",
        sub_bullet=3,
        statement=(
            "application key 冻结 bundle：同一 incoming 在**不同** definition bundle 下必须产生"
            "两条互不折叠的 application；duplicate 折叠也要求同 bundle。"
        ),
        measured_by="`wpsync_check_application_identity` 的 bundle 锁 + "
                    "`wpsync_check_operation_duplicate_link` 的 bundle 分支 + 三臂真插",
        properties=(28, 64, 18),
        requirements=("6.10", "5.5"),
        schema_requirements=(
            _f("wpsync_check_application_identity",
               "bundle/authority identity 必须来自 origin request 的冻结值",
               "authority model 与 bundle child 未双向锁死"),
            _f("wpsync_check_operation_duplicate_link",
               "duplicate 目标 frozen bundle/authority 不同"),
        ),
        arms=(
            BehaviourArm(
                "fb_two_bundles_two_applications",
                "同 incoming + 两个不同 approved bundle ⇒ 两条 application 都必须插入（对照组）",
                "accepted",
            ),
            BehaviourArm(
                "fb_bundle_not_from_request",
                "application 的 bundle 不来自 origin request 的冻结值必须被拒",
                "rejected",
                ("bundle/authority identity 必须来自 origin request 的冻结值",),
            ),
            BehaviourArm(
                "fb_duplicate_across_bundles",
                "duplicate 指向 frozen bundle 不同的 primary 必须被拒（同 key 折叠要求同 bundle）",
                "rejected",
                ("frozen bundle/authority 不同",),
            ),
            BehaviourArm(
                "fb_no_folding",
                "两条 application 的 id 与 application_key 互不相同 ⇒ 没有跨 bundle 折叠",
                "measure",
                expect_measure={"applications": 2, "distinct_keys": 2, "folded": False},
            ),
        ),
    ),
)


# ════════════════════════════════════════════════════════════════════════════
# §5 行为侧探针：scratch schema 里真造行
# ════════════════════════════════════════════════════════════════════════════

#: 生产 `working_paper` / `projects` / `users` 的最小桩（本门只用 scope FK，不跑业务代码）。
_STUB_DDL: Final[str] = """
CREATE TABLE projects (id UUID PRIMARY KEY, name VARCHAR(200) NOT NULL DEFAULT 'stub');
CREATE TABLE users (id UUID PRIMARY KEY, username VARCHAR(100) NOT NULL DEFAULT 'stub');
CREATE TABLE working_paper (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    file_version INTEGER NOT NULL DEFAULT 1,
    parsed_data JSONB,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _d(label: str) -> str:
    """真实 sha256（`wpsync_is_digest` 拒绝空串/全零/非 hex/大写/短串）。"""
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


_UUID_RE: Final[re.Pattern[str]] = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_DIGEST_RE: Final[re.Pattern[str]] = re.compile(r"\b[0-9a-f]{64}\b")
_DETAIL_RE: Final[re.Pattern[str]] = re.compile(r"DETAIL:.*", re.S)


def normalize_rejection(text: str) -> str:
    """把拒绝理由规范化成**逐轮可复现**的形态。

    🔴 存在的理由（实测）：PostgreSQL 的拒绝文案里带每轮新生成的 UUID、digest 与
    `DETAIL: Failing row contains (...)` 整行值。原样记录会让 `--check` 的逐字节锁
    **永远**对不上 —— 锁于是等于不存在，报告可被任意手改。

    规范化只抹**标识值**，保留全部承载判据的部分：sqlstate、约束名、plpgsql 的中文文案
    （含 `实得 quarantined` 这类状态词）。
    """
    masked = _DETAIL_RE.sub("DETAIL:<row>", text)
    masked = _UUID_RE.sub("<uuid>", masked)
    return _DIGEST_RE.sub("<digest>", masked)


def _rejection_text(exc: BaseException) -> str:
    """把驱动异常压成可比片段串：`sqlstate|constraint|message`（已规范化）。

    🔴 只比异常类型不够（教训 1）：NOT NULL、FK、别的 CHECK 都是 IntegrityError。
    """
    orig = getattr(exc, "orig", None) or exc
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", "") or ""
    constraint = getattr(orig, "constraint_name", None) or ""
    message = str(getattr(orig, "message", None) or orig)
    return normalize_rejection(f"{sqlstate}|{constraint}|{message}")


class _Runner:
    """一条语句 = 一个独立事务。失败语句会 abort 事务，所以不能共用。"""

    def __init__(self, engine: Any, observations: dict[str, dict[str, Any]]) -> None:
        self.engine = engine
        self.obs = observations

    async def attempt(
        self, arm_id: str | None, sql: str, params: Mapping[str, Any] | None = None
    ) -> bool:
        """执行一条语句。`arm_id` 非空时把结果记进观测。返回是否成功。"""
        import sqlalchemy as sa

        try:
            async with self.engine.begin() as conn:
                await conn.execute(sa.text(sql), dict(params or {}))
        except Exception as exc:  # noqa: BLE001 - 拒绝本身就是观测
            if arm_id:
                self.obs[arm_id] = {"accepted": False, "rejection": _rejection_text(exc)}
            return False
        if arm_id:
            self.obs[arm_id] = {"accepted": True, "rejection": None}
        return True

    async def setup(self, sql: str, params: Mapping[str, Any] | None = None) -> None:
        """世界搭建语句：失败必须抛（世界搭错时后续「非法被拒」毫无信息量，教训 5）。"""
        import sqlalchemy as sa

        async with self.engine.begin() as conn:
            await conn.execute(sa.text(sql), dict(params or {}))

    async def scalar(self, sql: str, params: Mapping[str, Any] | None = None) -> Any:
        import sqlalchemy as sa

        async with self.engine.connect() as conn:
            return (await conn.execute(sa.text(sql), dict(params or {}))).scalar_one()

    async def rows(
        self, sql: str, params: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        import sqlalchemy as sa

        async with self.engine.connect() as conn:
            return [
                dict(r) for r in (await conn.execute(sa.text(sql), dict(params or {}))).mappings()
            ]

    def measure(self, arm_id: str, **measured: Any) -> None:
        self.obs[arm_id] = {"accepted": True, "rejection": None, "measured": measured}


_ART_COLS: Final[str] = (
    "id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, document_type, "
    "source_delivery_id, durable_at, quarantined_at, published_at"
)
_DEF_COLS: Final[str] = (
    "id, kind, logical_id, semantic_version, blob_artifact_id, sha256, structure_hash, "
    "authority_model_type, source_commit, state, approved_at"
)
_BUNDLE_COLS: Final[str] = (
    "id, authority_model_definition_id, authority_model_definition_sha256, "
    "template_slot_type, template_slot_ref, template_slot_digest, "
    "instrumentation_slot_type, instrumentation_slot_ref, instrumentation_slot_digest, "
    "contract_slot_type, contract_slot_ref, contract_slot_digest, "
    "canonical_payload_artifact_id, canonical_payload_sha256, state, approved_at"
)
_REQ_COLS: Final[str] = (
    "id, room_id, generation, request_sequence, kind, initiated_by_participant_id, "
    "initiator_permission_epoch, client_edit_epoch, write_fence_epoch, client_base_version_id, "
    "client_base_representation_id, client_base_projection_sha256, definition_bundle_id, "
    "definition_bundle_sha256, authority_model_definition_id, authority_model_definition_sha256, "
    "adapter_build_digest, contributor_snapshot_digest, idempotency_key, "
    "frozen_request_fingerprint, state"
)
_APP_COLS: Final[str] = (
    "id, project_id, wp_id, entry_id, room_id, generation, origin_request_id, application_key, "
    "client_edit_epoch, origin_request_sequence, effective_request_sequence, base_version_id, "
    "base_representation_id, current_revision, incoming_artifact_id, incoming_sha256, "
    "definition_bundle_id, definition_bundle_sha256, authority_model_definition_id, "
    "authority_model_definition_sha256, adapter_id, adapter_build_digest, "
    "contributor_snapshot_digest, state"
)
_OP_COLS: Final[str] = (
    "id, project_id, wp_id, entry_id, room_id, forcesave_request_id, application_id, "
    "duplicate_of_operation_id, initiated_by_participant_id, direction, state, "
    "definition_bundle_id, definition_bundle_sha256, authority_model_definition_id, "
    "authority_model_definition_sha256, application_bound_at"
)
_DLV_COLS: Final[str] = (
    "id, project_id, wp_id, entry_id, room_id, generation, operation_id, application_id, "
    "forcesave_request_id, callback_recovery_case_id, route_credential_id, callback_status, "
    "delivery_key, state, correlation_result, incoming_artifact_id, durable_at"
)


def _values(cols: str) -> str:
    return ", ".join(f":{c.strip()}" for c in cols.split(","))


def _ins(table: str, cols: str) -> str:
    return f"INSERT INTO {table} ({cols}) VALUES ({_values(cols)})"  # noqa: S608


def _u() -> str:
    return str(uuid.uuid4())


def _art(
    w: Mapping[str, Any],
    *,
    kind: str,
    state: str,
    label: str,
    delivery: str | None = None,
    wp: str | None = None,
    doc: str = "xlsx",
) -> dict[str, Any]:
    """构造一条合法 artifact 行参数（incoming 的路径必须带 delivery identity sealing）。"""
    wp_id = wp or w["wp_a"]
    art_id = _u()
    if kind == "incoming":
        if delivery is None:
            raise Task68GateError("incoming artifact 必须给 delivery id")
        path = f".incoming/{wp_id}/{delivery}/{label}.{doc}"
    else:
        path = f"{wp_id}/{kind}/{label}.{doc}"
    return {
        "id": art_id,
        "project_id": w["project"],
        "wp_id": wp_id,
        "kind": kind,
        "state": state,
        "relative_path": path,
        "sha256": _d(f"artifact::{label}"),
        "size_bytes": 1024,
        "document_type": doc,
        "source_delivery_id": delivery,
        "durable_at": "now()" if state == "durable" else None,
        "quarantined_at": None,
        "published_at": None,
    }


async def _insert_artifact(run: _Runner, row: dict[str, Any]) -> str:
    """artifact 的三个时间列有 CHECK 联动，用显式 SQL 而不是参数里塞 `now()`。"""
    durable = "now()" if row["state"] == "durable" else "NULL"
    quarantined = "now()" if row["state"] == "quarantined" else "NULL"
    published = "now()" if row["state"] == "published" else "NULL"
    sql = (
        "INSERT INTO working_paper_artifact "
        "(id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, "
        " document_type, source_delivery_id, durable_at, quarantined_at, published_at) "
        "VALUES (:id, :project_id, :wp_id, :kind, :state, :relative_path, :sha256, "
        f" :size_bytes, :document_type, :source_delivery_id, {durable}, {quarantined}, {published})"
    )
    payload = {k: v for k, v in row.items() if k not in ("durable_at", "quarantined_at", "published_at")}
    await run.setup(sql, payload)
    return str(row["id"])


async def _insert_definition(
    run: _Runner,
    *,
    blob: str,
    kind: str,
    label: str,
    state: str = "approved",
    authority_type: str | None = None,
) -> tuple[str, str]:
    def_id, sha = _u(), _d(f"definition::{kind}::{label}")
    approved = "now()" if state == "approved" else "NULL"
    await run.setup(
        "INSERT INTO working_paper_sync_definition_artifact "
        "(id, kind, logical_id, semantic_version, blob_artifact_id, sha256, structure_hash, "
        " authority_model_type, source_commit, state, approved_at) "
        f"VALUES (:id, :kind, :logical_id, 'v1', :blob, :sha, :structure, :atype, "
        f" 'task68-gate', :state, {approved})",
        {
            "id": def_id,
            "kind": kind,
            "logical_id": f"task68/{kind}/{label}",
            "blob": blob,
            "sha": sha,
            "structure": _d(f"structure::{label}"),
            "atype": authority_type,
            "state": state,
        },
    )
    return def_id, sha


async def _insert_bundle(
    run: _Runner,
    *,
    payload_artifact: str,
    authority: tuple[str, str],
    template: tuple[str, str, str],
    instrumentation: tuple[str, str, str],
    contract: tuple[str, str, str],
    label: str,
) -> tuple[str, str]:
    bundle_id, canonical = _u(), _d(f"bundle::{label}")
    # `ck_wpsdb_approved_at`：state=approved ⇒ approved_at 必须非空（用 SQL 侧 now()，
    # 不在参数里塞 timestamptz —— 驱动会按目标类型编码，Python 侧转换才可靠）。
    await run.setup(
        "INSERT INTO working_paper_sync_definition_bundle "
        "(id, authority_model_definition_id, authority_model_definition_sha256, "
        " template_slot_type, template_slot_ref, template_slot_digest, "
        " instrumentation_slot_type, instrumentation_slot_ref, instrumentation_slot_digest, "
        " contract_slot_type, contract_slot_ref, contract_slot_digest, "
        " canonical_payload_artifact_id, canonical_payload_sha256, state, approved_at) "
        "VALUES (:id, :authority_model_definition_id, :authority_model_definition_sha256, "
        " :template_slot_type, :template_slot_ref, :template_slot_digest, "
        " :instrumentation_slot_type, :instrumentation_slot_ref, :instrumentation_slot_digest, "
        " :contract_slot_type, :contract_slot_ref, :contract_slot_digest, "
        " :canonical_payload_artifact_id, :canonical_payload_sha256, 'approved', now())",
        {
            "id": bundle_id,
            "authority_model_definition_id": authority[0],
            "authority_model_definition_sha256": authority[1],
            "template_slot_type": template[0],
            "template_slot_ref": template[1],
            "template_slot_digest": template[2],
            "instrumentation_slot_type": instrumentation[0],
            "instrumentation_slot_ref": instrumentation[1],
            "instrumentation_slot_digest": instrumentation[2],
            "contract_slot_type": contract[0],
            "contract_slot_ref": contract[1],
            "contract_slot_digest": contract[2],
            "canonical_payload_artifact_id": payload_artifact,
            "canonical_payload_sha256": canonical,
        },
    )
    return bundle_id, canonical


async def _new_user(run: _Runner) -> str:
    """每个 participant 一个新 user（`uq_wpoop_active_lease` 按 (room, user) 唯一）。"""
    user_id = _u()
    await run.setup("INSERT INTO users (id) VALUES (:u)", {"u": user_id})
    return user_id


async def _build_world(run: _Runner) -> dict[str, Any]:  # noqa: PLR0915 - 一次搭全链
    """搭最小合法世界。任何一步失败即抛 —— 世界搭错时后续臂毫无信息量（教训 5）。"""
    w: dict[str, Any] = {
        "project": _u(),
        "wp_a": _u(),
        "wp_b": _u(),
        "user": _u(),
        "entry": "xlsx/gt-task68-regression",
        "entry2": "xlsx/gt-task68-regression-second",
    }
    await run.setup("INSERT INTO projects (id) VALUES (:p)", {"p": w["project"]})
    await run.setup("INSERT INTO users (id) VALUES (:u)", {"u": w["user"]})
    # 🔴 `uq_wpoop_active_lease` 是 (room_id, user_id) 的 partial unique ⇒ 同 room 内每个
    #    participant 必须是不同 user（首轮实测踩到：三个 participant 共用一个 user 直接撞键）。
    w["users"] = []
    for key in ("wp_a", "wp_b"):
        await run.setup(
            "INSERT INTO working_paper (id, project_id) VALUES (:w, :p)",
            {"w": w[key], "p": w["project"]},
        )

    # ── artifacts ───────────────────────────────────────────────────────────
    w["delivery_1"], w["delivery_2"] = _u(), _u()
    w["delivery_3"], w["delivery_4"] = _u(), _u()
    w["art_canon"] = await _insert_artifact(
        run, _art(w, kind="canonical", state="published", label="canon1")
    )
    w["art_canon2"] = await _insert_artifact(
        run, _art(w, kind="canonical", state="published", label="canon2")
    )
    w["art_staged"] = await _insert_artifact(
        run, _art(w, kind="canonical", state="staged", label="staged1")
    )
    w["art_canon_b"] = await _insert_artifact(
        run, _art(w, kind="canonical", state="published", label="canonb", wp=w["wp_b"])
    )
    w["art_blob"] = await _insert_artifact(
        run, _art(w, kind="definition", state="published", label="defblob", doc="json")
    )
    for idx in (1, 2, 3):
        w[f"art_payload_{idx}"] = await _insert_artifact(
            run, _art(w, kind="definition", state="published", label=f"payload{idx}", doc="json")
        )
    w["art_inc_durable"] = await _insert_artifact(
        run,
        _art(w, kind="incoming", state="durable", label="inc1", delivery=w["delivery_1"]),
    )
    w["art_inc_durable_sha"] = _d("artifact::inc1")
    w["art_inc_durable2"] = await _insert_artifact(
        run,
        _art(w, kind="incoming", state="durable", label="inc2", delivery=w["delivery_2"]),
    )
    w["art_inc_durable2_sha"] = _d("artifact::inc2")
    w["art_inc_quarantined"] = await _insert_artifact(
        run,
        _art(w, kind="incoming", state="quarantined", label="inc3", delivery=w["delivery_3"]),
    )
    w["art_inc_quarantined_sha"] = _d("artifact::inc3")
    w["art_inc_staged"] = await _insert_artifact(
        run,
        _art(w, kind="incoming", state="staged", label="inc4", delivery=w["delivery_4"]),
    )
    w["art_inc_staged_sha"] = _d("artifact::inc4")
    w["art_candidate"] = await _insert_artifact(
        run, _art(w, kind="upgrade_candidate", state="staged", label="cand1")
    )

    # ── definitions ─────────────────────────────────────────────────────────
    defs: dict[str, tuple[str, str]] = {}
    for suffix in ("1", "2"):
        for kind in ("template", "instrumentation", "contract"):
            defs[f"{kind}{suffix}"] = await _insert_definition(
                run, blob=w["art_blob"], kind=kind, label=f"{kind}{suffix}"
            )
    defs["contract_candidate"] = await _insert_definition(
        run, blob=w["art_blob"], kind="contract", label="contract-candidate", state="candidate"
    )
    for suffix in ("1", "2"):
        defs[f"authority_proj{suffix}"] = await _insert_definition(
            run,
            blob=w["art_blob"],
            kind="authority_model",
            label=f"projection{suffix}",
            authority_type="projection_contract",
        )
    defs["authority_custom"] = await _insert_definition(
        run,
        blob=w["art_blob"],
        kind="authority_model",
        label="custom",
        authority_type="custom_authoritative_ooxml",
    )
    w["defs"] = defs

    def _slot(key: str) -> tuple[str, str, str]:
        def_id, sha = defs[key]
        return ("definition", f"definition:{def_id}", sha)

    w["bundle_1"] = await _insert_bundle(
        run,
        payload_artifact=w["art_payload_1"],
        authority=defs["authority_proj1"],
        template=_slot("template1"),
        instrumentation=_slot("instrumentation1"),
        contract=_slot("contract1"),
        label="bundle1",
    )
    w["bundle_2"] = await _insert_bundle(
        run,
        payload_artifact=w["art_payload_2"],
        authority=defs["authority_proj2"],
        template=_slot("template2"),
        instrumentation=_slot("instrumentation2"),
        contract=_slot("contract2"),
        label="bundle2",
    )
    markers = {
        row["applies_to_slot"]: (row["marker_id"], row["sha256"])
        for row in await run.rows(
            "SELECT marker_id, applies_to_slot, sha256 FROM "
            "working_paper_sync_definition_null_marker WHERE state = 'active'"
        )
    }
    if set(markers) != {"template", "instrumentation", "contract"}:
        raise Task68GateError(f"typed null marker registry 形态异常: {sorted(markers)}")
    w["markers"] = markers
    # ref 必须是 `marker:<marker_id>`（trigger 用 `substring(from 8)` 剥前缀）。
    w["bundle_custom"] = await _insert_bundle(
        run,
        payload_artifact=w["art_payload_3"],
        authority=defs["authority_custom"],
        template=(markers["template"][0], f"marker:{markers['template'][0]}",
                  markers["template"][1]),
        instrumentation=(
            markers["instrumentation"][0],
            f"marker:{markers['instrumentation'][0]}",
            markers["instrumentation"][1],
        ),
        contract=(markers["contract"][0], f"marker:{markers['contract'][0]}",
                  markers["contract"][1]),
        label="bundle-custom",
    )

    # ── content version / representation / entry state ──────────────────────
    async def _version(wp: str, revision: int, artifact: str, label: str) -> str:
        version_id = _u()
        await run.setup(
            "INSERT INTO working_paper_content_version "
            "(id, wp_id, revision, source, projection_artifact_id, projection_sha256, actor_id) "
            "VALUES (:id, :wp, :rev, 'onlyoffice', :art, :sha, :actor)",
            {
                "id": version_id,
                "wp": wp,
                "rev": revision,
                "art": artifact,
                "sha": _d(f"projection::{label}"),
                "actor": w["user"],
            },
        )
        return version_id

    w["cv_a1"] = await _version(w["wp_a"], 1, w["art_canon"], "cva1")
    w["cv_a1_projection"] = _d("projection::cva1")
    w["cv_b1"] = await _version(w["wp_b"], 1, w["art_canon_b"], "cvb1")

    async def _representation(
        *, entry: str, version: str, generation: int, artifact: str, bundle_key: str, label: str
    ) -> str:
        bundle_id, bundle_sha = w[bundle_key]
        authority_key = "authority_proj1" if bundle_key == "bundle_1" else (
            "authority_proj2" if bundle_key == "bundle_2" else "authority_custom"
        )
        auth_id, auth_sha = defs[authority_key]
        rep_id = _u()
        artifact_sha = await run.scalar(
            "SELECT sha256 FROM working_paper_artifact WHERE id = :a", {"a": artifact}
        )
        await run.setup(
            "INSERT INTO working_paper_content_representation "
            "(id, wp_id, content_version_id, entry_id, generation, document_type, artifact_id, "
            " artifact_sha256, definition_bundle_id, definition_bundle_sha256, "
            " authority_model_definition_id, authority_model_definition_sha256, adapter_id, "
            " adapter_build_digest, structure_hash, identity_inventory_sha256, reason) "
            "VALUES (:id, :wp, :cv, :entry, :gen, 'xlsx', :art, :art_sha, :bundle, :bundle_sha, "
            " :auth, :auth_sha, 'task68-gate', :adapter, :structure, :inventory, 'content_commit')",
            {
                "id": rep_id,
                "wp": w["wp_a"],
                "cv": version,
                "entry": entry,
                "gen": generation,
                "art": artifact,
                "art_sha": artifact_sha,
                "bundle": bundle_id,
                "bundle_sha": bundle_sha,
                "auth": auth_id,
                "auth_sha": auth_sha,
                "adapter": _d("adapter::task68"),
                "structure": _d(f"structure::{label}"),
                "inventory": _d(f"inventory::{label}"),
            },
        )
        return rep_id

    w["rep_a1"] = await _representation(
        entry=w["entry"], version=w["cv_a1"], generation=1,
        artifact=w["art_canon"], bundle_key="bundle_1", label="repa1",
    )
    w["rep_a2"] = await _representation(
        entry=w["entry"], version=w["cv_a1"], generation=2,
        artifact=w["art_canon2"], bundle_key="bundle_2", label="repa2",
    )
    w["rep_staged"] = await _representation(
        entry=w["entry2"], version=w["cv_a1"], generation=1,
        artifact=w["art_staged"], bundle_key="bundle_1", label="repstaged",
    )

    # ── room / participants / confirmations ─────────────────────────────────
    w["room"] = _u()
    await run.setup(
        "INSERT INTO working_paper_oo_room "
        "(id, project_id, wp_id, entry_id, doc_key, generation, opened_base_version_id, "
        " latest_request_sequence, state, expires_at) "
        "VALUES (:id, :p, :wp, :entry, :doc, 1, :cv, 100, 'active', now() + interval '2 hours')",
        {
            "id": w["room"],
            "p": w["project"],
            "wp": w["wp_a"],
            "entry": w["entry"],
            "doc": f"task68-{w['room'][:12]}",
            "cv": w["cv_a1"],
        },
    )
    for key, state in (("p_a", "active"), ("p_b", "active"), ("p_revoked", "revoked")):
        w[key] = _u()
        revoked = "now()" if state == "revoked" else "NULL"
        user_id = await _new_user(run)
        w["users"].append(user_id)
        await run.setup(
            "INSERT INTO working_paper_oo_participant "
            "(id, room_id, user_id, mode, state, permission_epoch, joined_write_fence_epoch, "
            " lease_token_hash, expires_at, revoked_at) "
            f"VALUES (:id, :room, :user, 'edit', :state, 1, 1, :lease, "
            f" now() + interval '2 hours', {revoked})",
            {
                "id": w[key],
                "room": w["room"],
                "user": user_id,
                "state": state,
                "lease": _d(f"lease::{key}"),
            },
        )
    bundle_id, bundle_sha = w["bundle_1"]
    auth_id, auth_sha = defs["authority_proj1"]
    for key, participant in (("conf_a", "p_a"), ("conf_b", "p_b")):
        w[key] = _u()
        await run.setup(
            "INSERT INTO working_paper_oo_client_confirmation "
            "(id, room_id, participant_id, generation, doc_key, representation_id, "
            " artifact_sha256, content_version_id, projection_sha256, definition_bundle_id, "
            " definition_bundle_sha256, authority_model_definition_sha256, bundle_slots_digest, "
            " write_fence_epoch, idempotency_key) "
            "SELECT :id, :room, :participant, 1, r.doc_key, :rep, :art_sha, :cv, :proj, "
            " :bundle, :bundle_sha, :auth_sha, :slots, 1, :key "
            "  FROM working_paper_oo_room r WHERE r.id = :room",
            {
                "id": w[key],
                "room": w["room"],
                "participant": w[participant],
                "rep": w["rep_a1"],
                "art_sha": _d("artifact::canon1"),
                "cv": w["cv_a1"],
                "proj": w["cv_a1_projection"],
                "bundle": bundle_id,
                "bundle_sha": bundle_sha,
                "auth_sha": auth_sha,
                "slots": _d("slots::bundle1"),
                "key": f"conf-{key}",
            },
        )
    w["authority_1"] = (auth_id, auth_sha)
    return w


def _request_row(
    w: Mapping[str, Any],
    *,
    sequence: int,
    kind: str = "forcesave",
    participant_key: str = "p_a",
    key: str,
    bundle_key: str = "bundle_1",
    base_rep_key: str = "rep_a1",
    fingerprint_label: str | None = None,
    state: str = "frozen",
) -> dict[str, Any]:
    bundle_id, bundle_sha = w[bundle_key]
    authority_key = {
        "bundle_1": "authority_proj1",
        "bundle_2": "authority_proj2",
        "bundle_custom": "authority_custom",
    }[bundle_key]
    auth_id, auth_sha = w["defs"][authority_key]
    return {
        "id": _u(),
        "room_id": w["room"],
        "generation": 1,
        "request_sequence": sequence,
        "kind": kind,
        "initiated_by_participant_id": w[participant_key],
        "initiator_permission_epoch": 1,
        "client_edit_epoch": 1,
        "write_fence_epoch": 1,
        "client_base_version_id": w["cv_a1"],
        "client_base_representation_id": w[base_rep_key],
        "client_base_projection_sha256": w["cv_a1_projection"],
        "definition_bundle_id": bundle_id,
        "definition_bundle_sha256": bundle_sha,
        "authority_model_definition_id": auth_id,
        "authority_model_definition_sha256": auth_sha,
        "adapter_build_digest": _d("adapter::task68"),
        "contributor_snapshot_digest": _d("contributor::task68"),
        "idempotency_key": key,
        "frozen_request_fingerprint": _d(f"fingerprint::{fingerprint_label or key}::{sequence}"),
        "state": state,
    }


def _application_row(
    w: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    key_label: str,
    incoming_key: str = "art_inc_durable",
    origin_sequence: int | None = None,
    effective_sequence: int | None = None,
    bundle_key: str | None = None,
) -> dict[str, Any]:
    origin = origin_sequence if origin_sequence is not None else int(request["request_sequence"])
    effective = effective_sequence if effective_sequence is not None else origin
    if bundle_key is None:
        bundle_id = request["definition_bundle_id"]
        bundle_sha = request["definition_bundle_sha256"]
        auth_id = request["authority_model_definition_id"]
        auth_sha = request["authority_model_definition_sha256"]
    else:
        bundle_id, bundle_sha = w[bundle_key]
        authority_key = {
            "bundle_1": "authority_proj1",
            "bundle_2": "authority_proj2",
            "bundle_custom": "authority_custom",
        }[bundle_key]
        auth_id, auth_sha = w["defs"][authority_key]
    return {
        "id": _u(),
        "project_id": w["project"],
        "wp_id": w["wp_a"],
        "entry_id": w["entry"],
        "room_id": w["room"],
        "generation": 1,
        "origin_request_id": request["id"],
        "application_key": _d(f"application-key::{key_label}"),
        "client_edit_epoch": 1,
        "origin_request_sequence": origin,
        "effective_request_sequence": effective,
        "base_version_id": request["client_base_version_id"],
        "base_representation_id": request["client_base_representation_id"],
        "current_revision": 1,
        "incoming_artifact_id": w[incoming_key],
        "incoming_sha256": w[f"{incoming_key}_sha"],
        "definition_bundle_id": bundle_id,
        "definition_bundle_sha256": bundle_sha,
        "authority_model_definition_id": auth_id,
        "authority_model_definition_sha256": auth_sha,
        "adapter_id": "task68-gate",
        "adapter_build_digest": _d("adapter::task68"),
        "contributor_snapshot_digest": _d("contributor::task68"),
        "state": "queued",
    }


def _operation_row(
    w: Mapping[str, Any],
    *,
    request: Mapping[str, Any] | None,
    application: Mapping[str, Any] | None = None,
    duplicate_of: str | None = None,
    state: str = "created",
    bundle_key: str = "bundle_1",
) -> dict[str, Any]:
    if request is not None:
        bundle_id = request["definition_bundle_id"]
        bundle_sha = request["definition_bundle_sha256"]
        auth_id = request["authority_model_definition_id"]
        auth_sha = request["authority_model_definition_sha256"]
    else:
        bundle_id, bundle_sha = w[bundle_key]
        authority_key = {
            "bundle_1": "authority_proj1",
            "bundle_2": "authority_proj2",
            "bundle_custom": "authority_custom",
        }[bundle_key]
        auth_id, auth_sha = w["defs"][authority_key]
    return {
        "id": _u(),
        "project_id": w["project"],
        "wp_id": w["wp_a"],
        "entry_id": w["entry"],
        "room_id": w["room"],
        "forcesave_request_id": None if request is None else request["id"],
        "application_id": None if application is None else application["id"],
        "duplicate_of_operation_id": duplicate_of,
        "initiated_by_participant_id": w["p_a"],
        "direction": "oo_to_html",
        "state": state,
        "definition_bundle_id": bundle_id,
        "definition_bundle_sha256": bundle_sha,
        "authority_model_definition_id": auth_id,
        "authority_model_definition_sha256": auth_sha,
        "application_bound_at": None,
    }


async def _insert_ok(run: _Runner, table: str, cols: str, row: Mapping[str, Any]) -> None:
    await run.setup(_ins(table, cols), row)


# ── 子条目 2 的探针 ─────────────────────────────────────────────────────────


async def _probe_forcesave_five_tuple(run: _Runner, w: dict[str, Any]) -> None:
    shared = "task68-shared-idempotency-key"
    base = _request_row(w, sequence=201, key=shared)
    ok = await run.attempt("fr5_baseline", _ins(_FR, _REQ_COLS), base)
    if not ok:
        return
    # 🔴 换 request_sequence：否则拒绝可能来自 uq_wpfr_sequence 而非 uq_wpfr_idempotency，
    #    两条判据会互相遮蔽（cross_signature_hits 会抓到）。
    again = _request_row(w, sequence=202, key=shared)
    await run.attempt("fr5_same_tuple_again", _ins(_FR, _REQ_COLS), again)
    other_payload = _request_row(
        w, sequence=203, key=shared, base_rep_key="rep_a2", bundle_key="bundle_2",
        fingerprint_label="different-payload",
    )
    await run.attempt("fr5_same_tuple_other_payload", _ins(_FR, _REQ_COLS), other_payload)
    cross_participant = _request_row(w, sequence=204, key=shared, participant_key="p_b")
    await run.attempt("fr5_cross_participant", _ins(_FR, _REQ_COLS), cross_participant)
    cross_kind = _request_row(w, sequence=205, key=shared, kind="close_capture")
    await run.attempt("fr5_cross_kind", _ins(_FR, _REQ_COLS), cross_kind)
    ids = [
        r["id"]
        for r in await run.rows(
            f"SELECT id FROM {_FR} WHERE room_id = :room AND idempotency_key = :key",  # noqa: S608
            {"room": w["room"], "key": shared},
        )
    ]
    run.measure(
        "fr5_distinct_ids",
        accepted_rows=len(ids),
        distinct_ids=len({str(i) for i in ids}),
        reused_old_id=len(ids) != len({str(i) for i in ids}),
    )
    w["req_frozen"] = base


async def _probe_frozen_fingerprint(run: _Runner, w: dict[str, Any]) -> None:
    row = _request_row(w, sequence=211, key="task68-frozen-probe")
    await _insert_ok(run, _FR, _REQ_COLS, row)
    await run.attempt(
        "frz_state_advance",
        f"UPDATE {_FR} SET state = 'accepted', accepted_at = now() WHERE id = :id",  # noqa: S608
        {"id": row["id"]},
    )
    await run.attempt(
        "frz_fingerprint_update",
        f"UPDATE {_FR} SET frozen_request_fingerprint = :f WHERE id = :id",  # noqa: S608
        {"id": row["id"], "f": _d("tampered-fingerprint")},
    )
    await run.attempt(
        "frz_bundle_update",
        f"UPDATE {_FR} SET definition_bundle_sha256 = :s WHERE id = :id",  # noqa: S608
        {"id": row["id"], "s": _d("tampered-bundle")},
    )


async def _probe_application_key(run: _Runner, w: dict[str, Any]) -> None:
    req = _request_row(w, sequence=221, key="task68-appkey")
    await _insert_ok(run, _FR, _REQ_COLS, req)
    first = _application_row(w, request=req, key_label="appkey-shared")
    ok = await run.attempt("ak_baseline", _ins(_CA, _APP_COLS), first)
    if ok:
        w["app_primary"] = first
        w["req_primary"] = req
    req2 = _request_row(w, sequence=222, key="task68-appkey-2")
    await _insert_ok(run, _FR, _REQ_COLS, req2)
    clash = _application_row(w, request=req2, key_label="appkey-shared")
    await run.attempt("ak_same_key", _ins(_CA, _APP_COLS), clash)
    has_col = await run.scalar(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :t AND column_name = :c",
        {"t": _OP, "c": "application_key"},
    )
    run.measure("ak_operation_column_absent", operation_has_application_key=bool(int(has_col)))


async def _probe_application_sequences(run: _Runner, w: dict[str, Any]) -> None:
    req = _request_row(w, sequence=231, key="task68-seq")
    await _insert_ok(run, _FR, _REQ_COLS, req)
    app = _application_row(
        w, request=req, key_label="seq-probe", origin_sequence=231, effective_sequence=231
    )
    await _insert_ok(run, _CA, _APP_COLS, app)
    await run.attempt(
        "eff_raise",
        f"UPDATE {_CA} SET effective_request_sequence = 240 WHERE id = :id",  # noqa: S608
        {"id": app["id"]},
    )
    await run.attempt(
        "eff_lower",
        f"UPDATE {_CA} SET effective_request_sequence = 232 WHERE id = :id",  # noqa: S608
        {"id": app["id"]},
    )
    await run.attempt(
        "eff_origin_update",
        f"UPDATE {_CA} SET origin_request_sequence = 999 WHERE id = :id",  # noqa: S608
        {"id": app["id"]},
    )
    await run.attempt(
        "eff_identity_column_update",
        f"UPDATE {_CA} SET adapter_id = 'tampered-adapter' WHERE id = :id",  # noqa: S608
        {"id": app["id"]},
    )
    req2 = _request_row(w, sequence=232, key="task68-seq-2")
    await _insert_ok(run, _FR, _REQ_COLS, req2)
    below = _application_row(
        w, request=req2, key_label="seq-below", origin_sequence=232, effective_sequence=1
    )
    await run.attempt("eff_insert_below_origin", _ins(_CA, _APP_COLS), below)
    await run.attempt(
        "eff_self_supersede",
        f"UPDATE {_CA} SET superseded_by_application_id = id WHERE id = :id",  # noqa: S608
        {"id": app["id"]},
    )
    w["app_seq"] = app


async def _probe_application_fold(run: _Runner, w: dict[str, Any]) -> None:
    app = w["app_seq"]
    req = _request_row(w, sequence=241, key="task68-fold")
    await _insert_ok(run, _FR, _REQ_COLS, req)
    common = {
        "app": app["id"],
        "origin": app["origin_request_sequence"],
        "effective": 250,
        "req": req["id"],
    }
    await run.attempt(
        "fold_full",
        f"INSERT INTO {_CAE} (application_id, sequence_no, event_type, folded_request_id, "  # noqa: S608
        " origin_request_sequence, effective_request_sequence, room_latest_durable_sequence, "
        " actor_type) VALUES (:app, 1, 'sequence_folded', :req, :origin, :effective, 250, "
        " 'callback')",
        common,
    )
    await run.attempt(
        "fold_no_request",
        f"INSERT INTO {_CAE} (application_id, sequence_no, event_type, folded_request_id, "  # noqa: S608
        " origin_request_sequence, effective_request_sequence, room_latest_durable_sequence, "
        " actor_type) VALUES (:app, 2, 'sequence_folded', NULL, :origin, :effective, 250, "
        " 'callback')",
        common,
    )
    await run.attempt(
        "fold_no_room_fence",
        f"INSERT INTO {_CAE} (application_id, sequence_no, event_type, folded_request_id, "  # noqa: S608
        " origin_request_sequence, effective_request_sequence, room_latest_durable_sequence, "
        " actor_type) VALUES (:app, 3, 'sequence_folded', :req, :origin, :effective, NULL, "
        " 'callback')",
        common,
    )
    await run.attempt(
        "fold_twice_same_request",
        f"INSERT INTO {_CAE} (application_id, sequence_no, event_type, folded_request_id, "  # noqa: S608
        " origin_request_sequence, effective_request_sequence, room_latest_durable_sequence, "
        " actor_type) VALUES (:app, 4, 'sequence_folded', :req, :origin, :effective, 251, "
        " 'callback')",
        common,
    )


async def _probe_operation_links(run: _Runner, w: dict[str, Any]) -> None:
    app = w["app_primary"]
    req_primary = w["req_primary"]
    primary = _operation_row(
        w, request=req_primary, application=app, state="application_bound"
    )
    primary["application_bound_at"] = None
    # `ck_wpso_bound_at`：application_id 非空 ⇔ application_bound_at 非空。
    sql_primary = (
        f"INSERT INTO {_OP} ({_OP_COLS}) VALUES ("  # noqa: S608
        ":id, :project_id, :wp_id, :entry_id, :room_id, :forcesave_request_id, :application_id, "
        ":duplicate_of_operation_id, :initiated_by_participant_id, :direction, :state, "
        ":definition_bundle_id, :definition_bundle_sha256, :authority_model_definition_id, "
        ":authority_model_definition_sha256, now())"
    )
    payload = {k: v for k, v in primary.items() if k != "application_bound_at"}
    await run.setup(sql_primary, payload)
    w["op_primary"] = primary

    shell_a = _operation_row(w, request=None, state="created")
    shell_b = _operation_row(w, request=None, state="created")
    ok_a = await run.attempt(None, _ins(_OP, _OP_COLS), shell_a)
    ok_b = await run.attempt(None, _ins(_OP, _OP_COLS), shell_b)
    run.obs["opfk_two_null_shells"] = {
        "accepted": ok_a and ok_b,
        "rejection": None if (ok_a and ok_b) else "两个 NULL application shell 未能同时插入",
    }
    clash = _operation_row(w, request=None, application=app, state="application_bound")
    clash_payload = {k: v for k, v in clash.items() if k != "application_bound_at"}
    await run.attempt("opfk_same_application_twice", sql_primary, clash_payload)
    same_request = _operation_row(w, request=req_primary, state="created")
    await run.attempt("opfk_same_request_twice", _ins(_OP, _OP_COLS), same_request)

    dup = _operation_row(w, request=None, duplicate_of=primary["id"], state="duplicate")
    await run.attempt("dup_direct", _ins(_OP, _OP_COLS), dup)
    await run.attempt(
        "dup_self",
        f"UPDATE {_OP} SET duplicate_of_operation_id = id, state = 'duplicate' "  # noqa: S608
        "WHERE id = :id",
        {"id": shell_a["id"]},
    )
    both = _operation_row(
        w, request=None, application=app, duplicate_of=primary["id"], state="duplicate"
    )
    # 🔴 必须走带 `now()` 的 bound SQL：否则 `ck_wpso_bound_at`（application_id 非空 ⇔
    #    application_bound_at 非空）会先命中，这条臂就不再度量 `ck_wpso_not_both_owners`。
    await run.attempt(
        "dup_with_application",
        sql_primary,
        {k: v for k, v in both.items() if k != "application_bound_at"},
    )
    chain = _operation_row(w, request=None, duplicate_of=dup["id"], state="duplicate")
    await run.attempt("dup_chain", _ins(_OP, _OP_COLS), chain)
    stranded = _operation_row(w, request=None, duplicate_of=shell_b["id"], state="duplicate")
    await run.attempt("dup_stranded_target", _ins(_OP, _OP_COLS), stranded)
    await run.attempt(
        "dup_rebind",
        f"UPDATE {_OP} SET application_id = NULL, application_bound_at = NULL, "  # noqa: S608
        "state = 'created' WHERE id = :id",
        {"id": primary["id"]},
    )


async def _make_room(run: _Runner, w: Mapping[str, Any], *, entry: str, label: str) -> str:
    """建一个独立 room。

    🔴 `uq_wpoor_generation` 是 (wp_id, entry_id, generation) 唯一 ⇒ 每个探针必须有自己的
    entry，否则第二个探针整条挂掉（首轮实测：recovery / delivery 两个探针互撞）。
    """
    room_id = _u()
    entry = f"{entry}::{label}"
    await run.setup(
        "INSERT INTO working_paper_oo_room "
        "(id, project_id, wp_id, entry_id, doc_key, generation, opened_base_version_id, "
        " latest_request_sequence, state, expires_at) "
        "VALUES (:id, :p, :wp, :entry, :doc, 1, :cv, 500, 'active', now() + interval '2 hours')",
        {
            "id": room_id,
            "p": w["project"],
            "wp": w["wp_a"],
            "entry": entry,
            "doc": f"task68-{label}-{room_id[:8]}",
            "cv": w["cv_a1"],
        },
    )
    return room_id


async def _make_participant(run: _Runner, w: Mapping[str, Any], room: str, label: str) -> str:
    pid = _u()
    user_id = await _new_user(run)
    await run.setup(
        "INSERT INTO working_paper_oo_participant "
        "(id, room_id, user_id, mode, state, permission_epoch, joined_write_fence_epoch, "
        " lease_token_hash, expires_at) "
        "VALUES (:id, :room, :user, 'edit', 'active', 1, 1, :lease, now() + interval '2 hours')",
        {"id": pid, "room": room, "user": user_id, "lease": _d(f"lease::{label}")},
    )
    return pid


async def _probe_n_shell_convergence(run: _Runner, w: dict[str, Any]) -> None:
    """N 个 different-request 同 key ⇒ 1 primary + N-1 terminal duplicate，零 stranded/链/环。"""
    room = await _make_room(run, w, entry=w["entry2"], label="nshell")
    participant = await _make_participant(run, w, room, "nshell")
    requests: list[dict[str, Any]] = []
    built = True
    for idx in range(4):
        row = _request_row(w, sequence=300 + idx, key=f"task68-nshell-{idx}")
        row["room_id"] = room
        row["initiated_by_participant_id"] = participant
        row["client_base_representation_id"] = w["rep_staged"]
        built = await run.attempt(None, _ins(_FR, _REQ_COLS), row) and built
        requests.append(row)
    app = _application_row(w, request=requests[0], key_label="nshell-canonical")
    app["room_id"] = room
    app["entry_id"] = w["entry2"]
    app["base_representation_id"] = w["rep_staged"]
    built = await run.attempt(None, _ins(_CA, _APP_COLS), app) and built

    sql_bound = (
        f"INSERT INTO {_OP} ({_OP_COLS}) VALUES ("  # noqa: S608
        ":id, :project_id, :wp_id, :entry_id, :room_id, :forcesave_request_id, :application_id, "
        ":duplicate_of_operation_id, :initiated_by_participant_id, :direction, :state, "
        ":definition_bundle_id, :definition_bundle_sha256, :authority_model_definition_id, "
        ":authority_model_definition_sha256, now())"
    )
    primary = _operation_row(
        w, request=requests[0], application=app, state="application_bound"
    )
    primary["room_id"] = room
    primary["entry_id"] = w["entry2"]
    primary["initiated_by_participant_id"] = participant
    built = (
        await run.attempt(
            None, sql_bound, {k: v for k, v in primary.items() if k != "application_bound_at"}
        )
        and built
    )
    for req in requests[1:]:
        dup = _operation_row(
            w, request=req, duplicate_of=primary["id"], state="duplicate"
        )
        dup["room_id"] = room
        dup["entry_id"] = w["entry2"]
        dup["initiated_by_participant_id"] = participant
        built = await run.attempt(None, _ins(_OP, _OP_COLS), dup) and built
    run.obs["nshell_build"] = {
        "accepted": built,
        "rejection": None if built else "4 request + 4 shell 未能全部建成",
    }

    shells = await run.rows(
        f"SELECT id, application_id, duplicate_of_operation_id, state FROM {_OP} "  # noqa: S608
        "WHERE room_id = :room",
        {"room": room},
    )
    by_id = {str(r["id"]): r for r in shells}
    primaries = [r for r in shells if r["application_id"] is not None]
    duplicates = [r for r in shells if r["duplicate_of_operation_id"] is not None]
    stranded = [
        r
        for r in shells
        if r["application_id"] is None and r["duplicate_of_operation_id"] is None
    ]
    chains = [
        r
        for r in duplicates
        if (by_id.get(str(r["duplicate_of_operation_id"])) or {}).get(
            "duplicate_of_operation_id"
        )
        is not None
    ]
    cycles = 0
    for row in duplicates:
        seen: set[str] = set()
        cur: str | None = str(row["id"])
        while cur and cur not in seen:
            seen.add(cur)
            nxt = (by_id.get(cur) or {}).get("duplicate_of_operation_id")
            cur = None if nxt is None else str(nxt)
        if cur is not None:
            cycles += 1
    applications = int(
        await run.scalar(
            f"SELECT count(*) FROM {_CA} WHERE room_id = :room", {"room": room}  # noqa: S608
        )
    )
    run.measure(
        "nshell_convergence",
        shells=len(shells),
        primary=len(primaries),
        terminal_duplicates=len([r for r in duplicates if r["state"] == "duplicate"]),
        stranded=len(stranded),
        chains=len(chains),
        cycles=cycles,
        applications=applications,
    )


async def _probe_recovery(run: _Runner, w: dict[str, Any]) -> None:
    room = await _make_room(run, w, entry=w["entry2"], label="recovery")
    participant = await _make_participant(run, w, room, "recovery")
    bundle_id, bundle_sha = w["bundle_1"]

    def _case(
        *,
        state: str,
        incoming: str,
        request_id: str | None = None,
        application_id: str | None = None,
        operation_id: str | None = None,
        full_claim: bool = False,
        label: str,
    ) -> tuple[str, dict[str, Any]]:
        claimed = "now()" if full_claim else "NULL"
        sql = (
            "INSERT INTO working_paper_callback_recovery_case "
            "(id, project_id, wp_id, entry_id, room_id, generation, source_delivery_key, "
            " incoming_artifact_id, reason, state, claimed_by_participant_id, "
            " prior_confirmation_id, recovery_request_id, application_id, operation_id, "
            " claimed_definition_bundle_id, claimed_definition_bundle_sha256, idempotency_key, "
            f" expires_at, claimed_at) VALUES (:id, :p, :wp, :entry, :room, 1, :dkey, :inc, "
            f" 'crash_close', :state, :participant, :conf, :req, :app, :op, :bundle, :bsha, "
            f" :key, now() + interval '1 day', {claimed})"
        )
        return sql, {
            "id": _u(),
            "p": w["project"],
            "wp": w["wp_a"],
            "entry": w["entry2"],
            "room": room,
            "dkey": _d(f"delivery-key::{label}"),
            "inc": incoming,
            "state": state,
            "participant": participant if full_claim else None,
            "conf": w["conf_a"] if full_claim else None,
            "req": request_id,
            "app": application_id,
            "op": operation_id,
            "bundle": bundle_id if full_claim else None,
            "bsha": bundle_sha if full_claim else None,
            "key": f"claim-{label}",
        }

    sql, params = _case(state="unclaimed", incoming=w["art_inc_durable2"], label="unclaimed")
    await run.attempt("rec_unclaimed", sql, params)

    req = _request_row(w, sequence=401, key="task68-recovery-claim", kind="recovery_claim")
    req["room_id"] = room
    req["initiated_by_participant_id"] = participant
    req["client_base_representation_id"] = w["rep_staged"]
    await _insert_ok(run, _FR, _REQ_COLS, req)
    app = _application_row(
        w, request=req, key_label="recovery-claim", incoming_key="art_inc_durable2"
    )
    app["room_id"] = room
    app["entry_id"] = w["entry2"]
    app["base_representation_id"] = w["rep_staged"]
    await _insert_ok(run, _CA, _APP_COLS, app)
    op = _operation_row(w, request=req, application=app, state="application_bound")
    op["room_id"] = room
    op["entry_id"] = w["entry2"]
    op["initiated_by_participant_id"] = participant
    await run.setup(
        f"INSERT INTO {_OP} ({_OP_COLS}) VALUES ("  # noqa: S608
        ":id, :project_id, :wp_id, :entry_id, :room_id, :forcesave_request_id, :application_id, "
        ":duplicate_of_operation_id, :initiated_by_participant_id, :direction, :state, "
        ":definition_bundle_id, :definition_bundle_sha256, :authority_model_definition_id, "
        ":authority_model_definition_sha256, now())",
        {k: v for k, v in op.items() if k != "application_bound_at"},
    )

    sql, params = _case(
        state="unclaimed", incoming=w["art_inc_durable2"], application_id=app["id"],
        label="unclaimed-with-app",
    )
    await run.attempt("rec_unclaimed_with_application", sql, params)
    sql, params = _case(
        state="download_only", incoming=w["art_inc_durable2"], operation_id=op["id"],
        label="download-only-with-op",
    )
    await run.attempt("rec_download_only_with_operation", sql, params)
    sql, params = _case(
        state="application_created", incoming=w["art_inc_durable2"], request_id=req["id"],
        application_id=app["id"], operation_id=None, full_claim=True, label="partial-claim",
    )
    await run.attempt("rec_claimed_partial", sql, params)
    sql, params = _case(
        state="application_created", incoming=w["art_inc_quarantined"], request_id=req["id"],
        application_id=app["id"], operation_id=op["id"], full_claim=True, label="quarantined",
    )
    await run.attempt("rec_quarantined_incoming", sql, params)
    sql, params = _case(
        state="application_created", incoming=w["art_inc_durable2"], request_id=req["id"],
        application_id=app["id"], operation_id=op["id"], full_claim=True, label="full-claim",
    )
    await run.attempt("rec_claimed_full", sql, params)

    case_op = await run.rows(
        "SELECT operation_id, application_id FROM working_paper_callback_recovery_case "
        "WHERE state = 'application_created' AND room_id = :room",
        {"room": room},
    )
    primaries = int(
        await run.scalar(
            f"SELECT count(*) FROM {_OP} WHERE application_id = :app", {"app": app["id"]}  # noqa: S608
        )
    )
    run.measure(
        "rec_canonical_convergence",
        case_operation_is_primary=bool(
            case_op and str(case_op[0]["operation_id"]) == str(op["id"])
        ),
        primaries_for_app=primaries,
    )


async def _probe_delivery(run: _Runner, w: dict[str, Any]) -> None:
    room = await _make_room(run, w, entry=w["entry2"], label="delivery")
    participant = await _make_participant(run, w, room, "delivery")
    req = _request_row(w, sequence=501, key="task68-delivery")
    req["room_id"] = room
    req["initiated_by_participant_id"] = participant
    req["client_base_representation_id"] = w["rep_staged"]
    await _insert_ok(run, _FR, _REQ_COLS, req)
    app = _application_row(w, request=req, key_label="delivery-owner")
    app["room_id"] = room
    app["entry_id"] = w["entry2"]
    app["base_representation_id"] = w["rep_staged"]
    await _insert_ok(run, _CA, _APP_COLS, app)
    case_id = _u()
    await run.setup(
        "INSERT INTO working_paper_callback_recovery_case "
        "(id, project_id, wp_id, entry_id, room_id, generation, source_delivery_key, "
        " incoming_artifact_id, reason, state, expires_at) "
        "VALUES (:id, :p, :wp, :entry, :room, 1, :dkey, :inc, 'crash_close', 'unclaimed', "
        " now() + interval '1 day')",
        {
            "id": case_id,
            "p": w["project"],
            "wp": w["wp_a"],
            "entry": w["entry2"],
            "room": room,
            "dkey": _d("delivery-key::for-delivery-probe"),
            "inc": w["art_inc_durable2"],
        },
    )

    def _delivery(
        *,
        label: str,
        state: str,
        durable: bool,
        application: str | None = None,
        recovery: str | None = None,
        request: str | None = None,
        correlation: str | None = None,
        incoming: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        durable_expr = "now()" if durable else "NULL"
        sql = (
            "INSERT INTO working_paper_callback_delivery "
            "(id, project_id, wp_id, entry_id, room_id, generation, operation_id, "
            " application_id, forcesave_request_id, callback_recovery_case_id, "
            " route_credential_id, callback_status, delivery_key, state, correlation_result, "
            f" incoming_artifact_id, durable_at) VALUES (:id, :p, :wp, :entry, :room, 1, NULL, "
            f" :app, :req, :rec, :cred, 6, :dkey, :state, :corr, :inc, {durable_expr})"
        )
        return sql, {
            "id": _u(),
            "p": w["project"],
            "wp": w["wp_a"],
            "entry": w["entry2"],
            "room": room,
            "app": application,
            "req": request,
            "rec": recovery,
            "cred": _u(),
            "dkey": _d(f"delivery::{label}"),
            "state": state,
            "corr": correlation,
            "inc": incoming,
        }

    sql, params = _delivery(
        label="one-owner", state="durable", durable=True, application=app["id"],
        correlation="existing_application", incoming=w["art_inc_durable"],
    )
    ok = await run.attempt("dlv_durable_one_owner", sql, params)
    durable_id = params["id"] if ok else None

    sql, params = _delivery(
        label="zero-owner", state="durable", durable=True, incoming=w["art_inc_durable"],
    )
    await run.attempt("dlv_durable_zero_owner", sql, params)
    # 🔴 双 owner 臂必须 **pre-durable**：durable 时 `ck_wpcd_durable_exactly_one_owner`
    #    会先命中（两个 owner 都非空 ⇒ `<>` 为假），这条臂就不再度量 `ck_wpcd_no_double_owner`。
    sql, params = _delivery(
        label="double-owner", state="received", durable=False, application=app["id"],
        recovery=case_id, incoming=w["art_inc_durable"],
    )
    await run.attempt("dlv_double_owner", sql, params)
    sql, params = _delivery(
        label="state-no-fact", state="durable", durable=False, application=app["id"],
        incoming=w["art_inc_durable"],
    )
    await run.attempt("dlv_durable_state_no_fact", sql, params)
    sql, params = _delivery(
        label="unmatched-with-request", state="unmatched", durable=True, request=req["id"],
        recovery=case_id, incoming=w["art_inc_durable"],
    )
    await run.attempt("dlv_unmatched_with_request", sql, params)
    sql, params = _delivery(
        label="request-and-application", state="durable", durable=True, application=app["id"],
        request=req["id"], correlation="request", incoming=w["art_inc_durable"],
    )
    await run.attempt("dlv_request_and_application", sql, params)

    if durable_id:
        await run.attempt(
            "dlv_post_durable_drop_owner",
            "UPDATE working_paper_callback_delivery SET application_id = NULL WHERE id = :id",
            {"id": durable_id},
        )
        await run.attempt(
            "dlv_post_durable_error_keeps_owner",
            "UPDATE working_paper_callback_delivery SET state = 'error', response_error = 1 "
            "WHERE id = :id",
            {"id": durable_id},
        )
    sql, params = _delivery(
        label="pre-durable-owner", state="rejected", durable=False, application=app["id"],
    )
    accepted = await run.attempt(None, sql, params)
    run.measure("dlv_pre_durable_owner", ddl_accepts_pre_durable_owner=accepted)


async def _probe_scope_index(run: _Runner, w: dict[str, Any]) -> None:
    def _scope(kind: str, resource: str) -> tuple[str, dict[str, Any]]:
        return (
            "INSERT INTO working_paper_sync_scope_index "
            "(resource_kind, resource_id, project_id, wp_id, entry_id) "
            "VALUES (:kind, :rid, :p, :wp, :entry)",
            {
                "kind": kind,
                "rid": resource,
                "p": w["project"],
                "wp": w["wp_a"],
                "entry": w["entry"],
            },
        )

    live = _u()
    sql, params = _scope("content_version", live)
    await run.attempt("si_insert", sql, params)
    retiring = _u()
    # `ck_wpssi_resource_kind` 的封闭词表用 `sync_operation`（不是 `operation`）。
    sql, params = _scope("sync_operation", retiring)
    await run.setup(sql, params)
    await run.attempt(
        "si_retire",
        "UPDATE working_paper_sync_scope_index SET retired_at = now() "
        "WHERE resource_kind = 'sync_operation' AND resource_id = :rid",
        {"rid": retiring},
    )
    await run.attempt(
        "si_delete",
        "DELETE FROM working_paper_sync_scope_index WHERE resource_id = :rid",
        {"rid": retiring},
    )
    await run.attempt(
        "si_clear_tombstone",
        "UPDATE working_paper_sync_scope_index SET retired_at = NULL WHERE resource_id = :rid",
        {"rid": retiring},
    )
    await run.attempt(
        "si_rebind_scope",
        "UPDATE working_paper_sync_scope_index SET wp_id = :wp WHERE resource_id = :rid",
        {"rid": retiring, "wp": w["wp_b"]},
    )
    sql, params = _scope("sync_operation", "12345")
    await run.attempt("si_numeric_resource_id", sql, params)
    sql, params = _scope("content_version", "not-a-uuid-value")
    await run.attempt("si_content_version_not_uuid", sql, params)


async def _probe_content_version(run: _Runner, w: dict[str, Any]) -> None:
    # 世界里 wp_a / wp_b 各已有 revision=1 ⇒ 跨 wp 同 numeric revision 已经共存。
    both = int(
        await run.scalar(
            f"SELECT count(*) FROM {_CV} WHERE revision = 1 AND wp_id IN (:a, :b)",  # noqa: S608
            {"a": w["wp_a"], "b": w["wp_b"]},
        )
    )
    run.obs["cv_two_wps_same_revision"] = {
        "accepted": both == 2,
        "rejection": None if both == 2 else f"跨 wp 同 revision 只有 {both} 行",
    }
    await run.attempt(
        "cv_same_wp_same_revision",
        f"INSERT INTO {_CV} (id, wp_id, revision, source, projection_artifact_id, "  # noqa: S608
        " projection_sha256) VALUES (:id, :wp, 1, 'html', :art, :sha)",
        {"id": _u(), "wp": w["wp_a"], "art": w["art_canon2"], "sha": _d("projection::dupe")},
    )
    await run.attempt(
        "cv_update_immutable",
        f"UPDATE {_CV} SET source = 'rollback' WHERE id = :id",  # noqa: S608
        {"id": w["cv_a1"]},
    )
    await run.attempt(
        "cv_numeric_as_resource_key",
        "INSERT INTO working_paper_sync_scope_index "
        "(resource_kind, resource_id, project_id, wp_id, entry_id) "
        "VALUES ('content_version', '1', :p, :wp, :entry)",
        {"p": w["project"], "wp": w["wp_a"], "entry": w["entry"]},
    )


# ── 子条目 3 的探针 ─────────────────────────────────────────────────────────


def _bundle_sql() -> str:
    return _ins(_DB, _BUNDLE_COLS)


def _bundle_params(
    w: Mapping[str, Any],
    *,
    label: str,
    authority_key: str,
    template: tuple[str, str, str],
    instrumentation: tuple[str, str, str],
    contract: tuple[str, str, str],
    payload_artifact_key: str = "art_payload_1",
) -> dict[str, Any]:
    auth_id, auth_sha = w["defs"][authority_key]
    return {
        "id": _u(),
        "authority_model_definition_id": auth_id,
        "authority_model_definition_sha256": auth_sha,
        "template_slot_type": template[0],
        "template_slot_ref": template[1],
        "template_slot_digest": template[2],
        "instrumentation_slot_type": instrumentation[0],
        "instrumentation_slot_ref": instrumentation[1],
        "instrumentation_slot_digest": instrumentation[2],
        "contract_slot_type": contract[0],
        "contract_slot_ref": contract[1],
        "contract_slot_digest": contract[2],
        "canonical_payload_artifact_id": w[payload_artifact_key],
        "canonical_payload_sha256": _d(f"bundle::{label}"),
        "state": "candidate",
        "approved_at": None,
    }


def _def_slot(w: Mapping[str, Any], key: str) -> tuple[str, str, str]:
    def_id, sha = w["defs"][key]
    return ("definition", f"definition:{def_id}", sha)


def _marker_slot(w: Mapping[str, Any], slot: str) -> tuple[str, str, str]:
    """typed null marker slot 三元组。

    🔴 ref 的形态是 `marker:<marker_id>` —— `wpsync_assert_bundle_slot` 用
    `substring(p_slot_ref from 8)` 剥掉那 7 个字符的 `marker:` 前缀再查 registry。
    直接把 marker_id 当 ref 会被判「未登记」（首轮实测踩到）。
    """
    marker_id, sha = w["markers"][slot]
    return (marker_id, f"marker:{marker_id}", sha)


async def _probe_bundle_slots(run: _Runner, w: dict[str, Any]) -> None:
    legal = _bundle_params(
        w, label="bs-legal", authority_key="authority_proj1",
        template=_def_slot(w, "template1"),
        instrumentation=_def_slot(w, "instrumentation1"),
        contract=_def_slot(w, "contract1"),
    )
    await run.attempt("bs_legal", _bundle_sql(), legal)

    null_ref = _bundle_params(
        w, label="bs-null-ref", authority_key="authority_proj1",
        template=_def_slot(w, "template1"),
        instrumentation=_def_slot(w, "instrumentation1"),
        contract=_def_slot(w, "contract1"),
    )
    null_ref["contract_slot_ref"] = None
    await run.attempt("bs_null_ref", _bundle_sql(), null_ref)

    zero_digest = _bundle_params(
        w, label="bs-zero", authority_key="authority_proj1",
        template=_def_slot(w, "template1"),
        instrumentation=_def_slot(w, "instrumentation1"),
        contract=("definition", _def_slot(w, "contract1")[1], "0" * 64),
    )
    await run.attempt("bs_zero_digest", _bundle_sql(), zero_digest)

    bad_type = _bundle_params(
        w, label="bs-bad-type", authority_key="authority_proj1",
        template=_def_slot(w, "template1"),
        instrumentation=_def_slot(w, "instrumentation1"),
        contract=("whatever", _def_slot(w, "contract1")[1], _def_slot(w, "contract1")[2]),
    )
    await run.attempt("bs_bad_slot_type", _bundle_sql(), bad_type)

    mismatch = _bundle_params(
        w, label="bs-mismatch", authority_key="authority_proj1",
        template=_def_slot(w, "template1"),
        instrumentation=_def_slot(w, "instrumentation1"),
        contract=("definition", _def_slot(w, "contract1")[1], _d("wrong-child-digest")),
    )
    await run.attempt("bs_digest_mismatch", _bundle_sql(), mismatch)


async def _probe_projection_contract(run: _Runner, w: dict[str, Any]) -> None:
    ok = _bundle_params(
        w, label="pc-ok", authority_key="authority_proj1",
        template=_def_slot(w, "template1"),
        instrumentation=_def_slot(w, "instrumentation1"),
        contract=_def_slot(w, "contract1"),
    )
    await run.attempt("pc_three_definitions", _bundle_sql(), ok)

    substituted = _bundle_params(
        w, label="pc-marker", authority_key="authority_proj1",
        template=_def_slot(w, "template1"),
        instrumentation=_def_slot(w, "instrumentation1"),
        contract=_marker_slot(w, "contract"),
    )
    await run.attempt("pc_marker_substitution", _bundle_sql(), substituted)

    candidate_child = _bundle_params(
        w, label="pc-candidate", authority_key="authority_proj1",
        template=_def_slot(w, "template1"),
        instrumentation=_def_slot(w, "instrumentation1"),
        contract=_def_slot(w, "contract_candidate"),
    )
    await run.attempt("pc_candidate_child", _bundle_sql(), candidate_child)

    await run.attempt(
        "pc_authority_model_type_null",
        f"INSERT INTO {_DA} (id, kind, logical_id, semantic_version, blob_artifact_id, "  # noqa: S608
        " sha256, authority_model_type, source_commit, state, approved_at) "
        "VALUES (:id, 'authority_model', 'task68/authority/no-type', 'v1', :blob, :sha, "
        " NULL, 'task68-gate', 'approved', now())",
        {"id": _u(), "blob": w["art_blob"], "sha": _d("authority::no-type")},
    )


async def _probe_typed_markers(run: _Runner, w: dict[str, Any]) -> None:
    registered = _bundle_params(
        w, label="tm-ok", authority_key="authority_custom",
        template=_marker_slot(w, "template"),
        instrumentation=_marker_slot(w, "instrumentation"),
        contract=_marker_slot(w, "contract"),
        payload_artifact_key="art_payload_3",
    )
    await run.attempt("tm_registered_marker", _bundle_sql(), registered)

    unregistered = _bundle_params(
        w, label="tm-unregistered", authority_key="authority_custom",
        template=_marker_slot(w, "template"),
        instrumentation=_marker_slot(w, "instrumentation"),
        contract=("contract:none:v9", "contract:none:v9", _d("forged-marker-v9")),
        payload_artifact_key="art_payload_3",
    )
    await run.attempt("tm_unregistered_marker", _bundle_sql(), unregistered)

    # 🔴 slot_type 保持合法（否则拒绝会来自 `ck_wpsdb_contract_slot_type` 正则，
    #    而不是「使用了 template 槽位的 marker」—— 两条判据互相遮蔽）。
    contract_type = w["markers"]["contract"][0]
    template_id, template_sha = w["markers"]["template"]
    wrong_slot = _bundle_params(
        w, label="tm-wrong-slot", authority_key="authority_custom",
        template=_marker_slot(w, "template"),
        instrumentation=_marker_slot(w, "instrumentation"),
        contract=(contract_type, f"marker:{template_id}", template_sha),
        payload_artifact_key="art_payload_3",
    )
    await run.attempt("tm_wrong_slot_marker", _bundle_sql(), wrong_slot)

    contract_marker = _marker_slot(w, "contract")
    forged = _bundle_params(
        w, label="tm-forged", authority_key="authority_custom",
        template=_marker_slot(w, "template"),
        instrumentation=_marker_slot(w, "instrumentation"),
        contract=(contract_marker[0], contract_marker[1], _d("forged-digest")),
        payload_artifact_key="art_payload_3",
    )
    await run.attempt("tm_forged_digest", _bundle_sql(), forged)


async def _probe_candidate_invisibility(run: _Runner, w: dict[str, Any]) -> None:
    row = _art(w, kind="upgrade_candidate", state="staged", label="cand-probe")
    ok = await run.attempt(
        "cand_staged",
        "INSERT INTO working_paper_artifact "
        "(id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, document_type) "
        "VALUES (:id, :project_id, :wp_id, :kind, :state, :relative_path, :sha256, "
        " :size_bytes, :document_type)",
        {k: v for k, v in row.items()
         if k not in ("source_delivery_id", "durable_at", "quarantined_at", "published_at")},
    )
    if not ok:
        return
    await run.attempt(
        "cand_published_artifact",
        "UPDATE working_paper_artifact SET state = 'published', published_at = now() "
        "WHERE id = :id",
        {"id": row["id"]},
    )
    await run.attempt(
        "cand_durable_artifact",
        "UPDATE working_paper_artifact SET state = 'durable', durable_at = now() WHERE id = :id",
        {"id": row["id"]},
    )
    await run.attempt(
        "cand_pointer_to_staged",
        "INSERT INTO working_paper_sync_entry_state "
        "(wp_id, entry_id, current_representation_id, representation_generation) "
        "VALUES (:wp, :entry, :rep, 1)",
        {"wp": w["wp_a"], "entry": w["entry2"], "rep": w["rep_staged"]},
    )
    await run.attempt(
        "cand_pointer_to_published",
        "INSERT INTO working_paper_sync_entry_state "
        "(wp_id, entry_id, current_representation_id, representation_generation) "
        "VALUES (:wp, :entry, :rep, 1)",
        {"wp": w["wp_a"], "entry": w["entry"], "rep": w["rep_a1"]},
    )


async def _probe_incoming_states(run: _Runner, w: dict[str, Any]) -> None:
    run.obs["inc_durable"] = {"accepted": True, "rejection": None}
    run.obs["inc_quarantined"] = {"accepted": True, "rejection": None}
    # 上面两条对照组在世界搭建阶段已真插成功（art_inc_durable / art_inc_quarantined），
    # 世界搭建失败会直接抛 —— 所以这里记录的是**已经发生的**真实结果，不是断言。
    published = _art(
        w, kind="incoming", state="staged", label="inc-published", delivery=w["delivery_1"]
    )
    await run.attempt(
        "inc_published",
        "INSERT INTO working_paper_artifact "
        "(id, project_id, wp_id, kind, state, relative_path, sha256, size_bytes, "
        " document_type, source_delivery_id, published_at) "
        "VALUES (:id, :project_id, :wp_id, :kind, 'published', :relative_path, :sha256, "
        " :size_bytes, :document_type, :source_delivery_id, now())",
        {k: v for k, v in published.items()
         if k not in ("state", "durable_at", "quarantined_at", "published_at")},
    )
    await run.attempt(
        "inc_quarantined_to_durable",
        "UPDATE working_paper_artifact SET state = 'durable', durable_at = now(), "
        "quarantined_at = NULL WHERE id = :id",
        {"id": w["art_inc_quarantined"]},
    )
    await run.attempt(
        "inc_durable_to_quarantined",
        "UPDATE working_paper_artifact SET state = 'quarantined', quarantined_at = now(), "
        "durable_at = NULL WHERE id = :id",
        {"id": w["art_inc_durable"]},
    )


async def _probe_application_incoming_fk(run: _Runner, w: dict[str, Any]) -> None:
    req = _request_row(w, sequence=601, key="task68-incoming-fk")
    await _insert_ok(run, _FR, _REQ_COLS, req)
    ok_row = _application_row(w, request=req, key_label="incoming-durable")
    await run.attempt("aif_durable", _ins(_CA, _APP_COLS), ok_row)

    req2 = _request_row(w, sequence=602, key="task68-incoming-fk-2")
    await _insert_ok(run, _FR, _REQ_COLS, req2)
    quarantined = _application_row(
        w, request=req2, key_label="incoming-quarantined", incoming_key="art_inc_quarantined"
    )
    await run.attempt("aif_quarantined", _ins(_CA, _APP_COLS), quarantined)

    req3 = _request_row(w, sequence=603, key="task68-incoming-fk-3")
    await _insert_ok(run, _FR, _REQ_COLS, req3)
    staged = _application_row(
        w, request=req3, key_label="incoming-staged", incoming_key="art_inc_staged"
    )
    await run.attempt("aif_staged", _ins(_CA, _APP_COLS), staged)

    req4 = _request_row(w, sequence=604, key="task68-incoming-fk-4")
    await _insert_ok(run, _FR, _REQ_COLS, req4)
    mismatch = _application_row(w, request=req4, key_label="incoming-sha-mismatch")
    mismatch["incoming_sha256"] = _d("wrong-incoming-digest")
    await run.attempt("aif_sha_mismatch", _ins(_CA, _APP_COLS), mismatch)


async def _probe_close_capture(run: _Runner, w: dict[str, Any]) -> None:
    """exactly-one 必须由行为给出：partial unique 只证明 at-most-one。"""
    orders: dict[str, int] = {}

    async def _one_order(label: str, *, terminal_first: bool, reentry: bool = False) -> int:
        room = await _make_room(run, w, entry=f"{w['entry2']}::{label}", label=label)
        participants = [await _make_participant(run, w, room, f"{label}-{i}") for i in (0, 1)]
        first = _request_row(
            w, sequence=1, kind="close_capture", key=f"cc-{label}-a",
        )
        first["room_id"] = room
        first["initiated_by_participant_id"] = participants[0]
        first["client_base_representation_id"] = w["rep_staged"]
        await run.setup(_ins(_FR, _REQ_COLS), first)
        if terminal_first:
            await run.setup(
                f"UPDATE {_FR} SET state = 'terminal', finished_at = now() WHERE id = :id",  # noqa: S608
                {"id": first["id"]},
            )
        second = _request_row(
            w, sequence=2, kind="close_capture", key=f"cc-{label}-b",
        )
        second["room_id"] = room
        second["initiated_by_participant_id"] = participants[1]
        second["client_base_representation_id"] = w["rep_staged"]
        await run.attempt(None, _ins(_FR, _REQ_COLS), second)
        if reentry:
            # reconciler 重入：同一条 close_capture 再走一遍协调，不得产生第二条 open。
            await run.attempt(None, _ins(_FR, _REQ_COLS), dict(second, id=_u(), request_sequence=3))
        return int(
            await run.scalar(
                f"SELECT count(*) FROM {_FR} WHERE room_id = :room AND generation = 1 "  # noqa: S608
                "AND kind = 'close_capture' "
                "AND state IN ('frozen', 'pending', 'accepted', 'correlated')",
                {"room": room},
            )
        )

    # single：只有 A 发起
    room_single = await _make_room(run, w, entry=f"{w['entry2']}::single", label="cc-single")
    p_single = await _make_participant(run, w, room_single, "cc-single")
    single = _request_row(w, sequence=1, kind="close_capture", key="cc-single")
    single["room_id"] = room_single
    single["initiated_by_participant_id"] = p_single
    single["client_base_representation_id"] = w["rep_staged"]
    await run.attempt("cc_single", _ins(_FR, _REQ_COLS), single)
    orders["single"] = int(
        await run.scalar(
            f"SELECT count(*) FROM {_FR} WHERE room_id = :room AND kind = 'close_capture' "  # noqa: S608
            "AND state IN ('frozen', 'pending', 'accepted', 'correlated')",
            {"room": room_single},
        )
    )
    second_open = _request_row(w, sequence=2, kind="close_capture", key="cc-single-second")
    second_open["room_id"] = room_single
    second_open["initiated_by_participant_id"] = p_single
    second_open["client_base_representation_id"] = w["rep_staged"]
    await run.attempt("cc_second_open", _ins(_FR, _REQ_COLS), second_open)

    orders["a_then_b"] = await _one_order("cc-ab", terminal_first=False)
    orders["b_then_a"] = await _one_order("cc-ba", terminal_first=False)
    orders["a_terminal_then_b"] = await _one_order("cc-terminal", terminal_first=True)
    orders["reconciler_reentry"] = await _one_order("cc-reentry", terminal_first=False, reentry=True)
    run.obs["cc_after_terminal"] = {
        "accepted": orders["a_terminal_then_b"] == 1,
        "rejection": None
        if orders["a_terminal_then_b"] == 1
        else f"terminal 后 B 的 close_capture 未成为唯一 open（实得 {orders['a_terminal_then_b']}）",
    }
    run.measure(
        "cc_exactly_one_over_orders",
        orders_checked=len(orders),
        zero_or_more_than_one_seen=any(v != 1 for v in orders.values()),
        **orders,
    )

    # leader 选举：打乱 created_at 与插入顺序，leader 仍按最高 (intent_sequence, id)
    leader_ok = True
    for shuffle in range(3):
        room = await _make_room(
            run, w, entry=f"{w['entry2']}::leader{shuffle}", label=f"leader{shuffle}"
        )
        seqs = [3, 1, 2] if shuffle == 0 else ([2, 3, 1] if shuffle == 1 else [1, 2, 3])
        for idx, seq in enumerate(seqs):
            participant = await _make_participant(run, w, room, f"leader{shuffle}-{idx}")
            intent = _u()
            await run.setup(
                "INSERT INTO working_paper_oo_close_intent "
                "(id, room_id, generation, participant_id, client_confirmation_id, "
                " intent_sequence, barrier_epoch, created_at) "
                "VALUES (:id, :room, 1, :participant, :conf, :seq, 1, "
                f" now() - interval '{idx} minutes')",
                {
                    "id": intent,
                    "room": room,
                    "participant": participant,
                    "conf": w["conf_a"],
                    "seq": seq,
                },
            )
        picked = await run.rows(
            "SELECT intent_sequence FROM working_paper_oo_close_intent WHERE room_id = :room "
            "ORDER BY intent_sequence DESC, id DESC LIMIT 1",
            {"room": room},
        )
        leader_ok = leader_ok and bool(picked) and int(picked[0]["intent_sequence"]) == 3
    run.measure(
        "cc_leader_by_highest_intent_sequence",
        leader_is_highest_intent_sequence=leader_ok,
        shuffles=3,
    )


async def _probe_leader_promotion(run: _Runner, w: dict[str, Any]) -> None:
    room = await _make_room(run, w, entry=f"{w['entry2']}::promotion", label="promotion")
    p_first = await _make_participant(run, w, room, "promo-first")
    p_successor = await _make_participant(run, w, room, "promo-successor")

    async def _intent(participant: str, seq: int) -> str:
        intent = _u()
        await run.setup(
            "INSERT INTO working_paper_oo_close_intent "
            "(id, room_id, generation, participant_id, client_confirmation_id, intent_sequence, "
            " barrier_epoch) VALUES (:id, :room, 1, :participant, :conf, :seq, 1)",
            {
                "id": intent,
                "room": room,
                "participant": participant,
                "conf": w["conf_a"],
                "seq": seq,
            },
        )
        return intent

    intent_first = await _intent(p_first, 1)
    capture = _request_row(w, sequence=1, kind="close_capture", key="promo-capture")
    capture["room_id"] = room
    capture["initiated_by_participant_id"] = p_first
    capture["client_base_representation_id"] = w["rep_staged"]
    await run.setup(_ins(_FR, _REQ_COLS), capture)
    await run.attempt(
        "lead_promote",
        "UPDATE working_paper_oo_close_intent SET state = 'promoted', promoted_request_id = :req "
        "WHERE id = :id",
        {"id": intent_first, "req": capture["id"]},
    )
    forcesave = _request_row(w, sequence=2, kind="forcesave", key="promo-forcesave")
    forcesave["room_id"] = room
    forcesave["initiated_by_participant_id"] = p_first
    forcesave["client_base_representation_id"] = w["rep_staged"]
    await run.setup(_ins(_FR, _REQ_COLS), forcesave)
    intent_wrong = await _intent(p_successor, 2)
    await run.attempt(
        "lead_promote_wrong_kind",
        "UPDATE working_paper_oo_close_intent SET state = 'promoted', promoted_request_id = :req "
        "WHERE id = :id",
        {"id": intent_wrong, "req": forcesave["id"]},
    )
    # 🔴 跨 room 臂必须用**另一个 room 的 close_capture** request：拿 kind=forcesave 的
    #    request 会让「只能提升为 close_capture」先命中，这条臂就不再度量跨 room/generation。
    other_room = await _make_room(run, w, entry=w["entry2"], label="promotion-other")
    other_participant = await _make_participant(run, w, other_room, "promo-other")
    other_capture = _request_row(w, sequence=1, kind="close_capture", key="promo-other-capture")
    other_capture["room_id"] = other_room
    other_capture["initiated_by_participant_id"] = other_participant
    other_capture["client_base_representation_id"] = w["rep_staged"]
    await run.setup(_ins(_FR, _REQ_COLS), other_capture)
    await run.attempt(
        "lead_promote_cross_generation",
        "UPDATE working_paper_oo_close_intent SET state = 'promoted', promoted_request_id = :req "
        "WHERE id = :id",
        {"id": intent_wrong, "req": other_capture["id"]},
    )
    await run.attempt(
        "lead_duplicate_active_intent",
        "INSERT INTO working_paper_oo_close_intent "
        "(id, room_id, generation, participant_id, client_confirmation_id, intent_sequence, "
        " barrier_epoch) VALUES (:id, :room, 1, :participant, :conf, 9, 1)",
        {"id": _u(), "room": room, "participant": p_successor, "conf": w["conf_a"]},
    )
    await run.attempt(
        "lead_authorization_stale",
        f"UPDATE {_FR} SET state = 'authorization_stale', finished_at = now() WHERE id = :id",  # noqa: S608
        {"id": capture["id"]},
    )
    successor = _request_row(w, sequence=3, kind="close_capture", key="promo-successor")
    successor["room_id"] = room
    successor["initiated_by_participant_id"] = p_successor
    successor["client_base_representation_id"] = w["rep_staged"]
    await run.attempt(None, _ins(_FR, _REQ_COLS), successor)
    stale_state = await run.scalar(
        f"SELECT state FROM {_FR} WHERE id = :id", {"id": capture["id"]}  # noqa: S608
    )
    generations = await run.rows(
        f"SELECT DISTINCT generation FROM {_FR} WHERE room_id = :room "  # noqa: S608
        "AND kind = 'close_capture'",
        {"room": room},
    )
    open_count = int(
        await run.scalar(
            f"SELECT count(*) FROM {_FR} WHERE room_id = :room AND kind = 'close_capture' "  # noqa: S608
            "AND state IN ('frozen', 'pending', 'accepted', 'correlated')",
            {"room": room},
        )
    )
    run.measure(
        "lead_successor_same_generation",
        stale_request_state=str(stale_state),
        successor_generation_equals_predecessor=len(generations) == 1,
        open_close_captures_after_successor=open_count,
    )


async def _probe_frozen_bundle(run: _Runner, w: dict[str, Any]) -> None:
    room = await _make_room(run, w, entry=f"{w['entry2']}::frozen", label="frozen-bundle")
    participant = await _make_participant(run, w, room, "frozen-bundle")
    req_b1 = _request_row(w, sequence=1, key="frozen-b1", bundle_key="bundle_1")
    req_b1["room_id"] = room
    req_b1["initiated_by_participant_id"] = participant
    req_b1["client_base_representation_id"] = w["rep_a1"]
    await run.setup(_ins(_FR, _REQ_COLS), req_b1)
    req_b2 = _request_row(
        w, sequence=2, key="frozen-b2", bundle_key="bundle_2", base_rep_key="rep_a2"
    )
    req_b2["room_id"] = room
    req_b2["initiated_by_participant_id"] = participant
    await run.setup(_ins(_FR, _REQ_COLS), req_b2)

    app1 = _application_row(w, request=req_b1, key_label="frozen-b1")
    app1["room_id"] = room
    app2 = _application_row(w, request=req_b2, key_label="frozen-b2")
    app2["room_id"] = room
    ok1 = await run.attempt(None, _ins(_CA, _APP_COLS), app1)
    ok2 = await run.attempt(None, _ins(_CA, _APP_COLS), app2)
    run.obs["fb_two_bundles_two_applications"] = {
        "accepted": ok1 and ok2,
        "rejection": None if (ok1 and ok2) else "同 incoming 的两条不同 bundle application 未能共存",
    }

    req_b3 = _request_row(w, sequence=3, key="frozen-b3", bundle_key="bundle_1")
    req_b3["room_id"] = room
    req_b3["initiated_by_participant_id"] = participant
    req_b3["client_base_representation_id"] = w["rep_a1"]
    await run.setup(_ins(_FR, _REQ_COLS), req_b3)
    wrong_bundle = _application_row(
        w, request=req_b3, key_label="frozen-wrong-bundle", bundle_key="bundle_2"
    )
    wrong_bundle["room_id"] = room
    await run.attempt("fb_bundle_not_from_request", _ins(_CA, _APP_COLS), wrong_bundle)

    sql_bound = (
        f"INSERT INTO {_OP} ({_OP_COLS}) VALUES ("  # noqa: S608
        ":id, :project_id, :wp_id, :entry_id, :room_id, :forcesave_request_id, :application_id, "
        ":duplicate_of_operation_id, :initiated_by_participant_id, :direction, :state, "
        ":definition_bundle_id, :definition_bundle_sha256, :authority_model_definition_id, "
        ":authority_model_definition_sha256, now())"
    )
    primary = _operation_row(w, request=req_b1, application=app1, state="application_bound")
    primary["room_id"] = room
    primary["initiated_by_participant_id"] = participant
    await run.setup(sql_bound, {k: v for k, v in primary.items() if k != "application_bound_at"})
    dup_other_bundle = _operation_row(
        w, request=req_b2, duplicate_of=primary["id"], state="duplicate"
    )
    dup_other_bundle["room_id"] = room
    dup_other_bundle["initiated_by_participant_id"] = participant
    await run.attempt("fb_duplicate_across_bundles", _ins(_OP, _OP_COLS), dup_other_bundle)

    rows = await run.rows(
        f"SELECT id, application_key FROM {_CA} WHERE room_id = :room", {"room": room}  # noqa: S608
    )
    run.measure(
        "fb_no_folding",
        applications=len(rows),
        distinct_keys=len({str(r["application_key"]) for r in rows}),
        folded=len(rows) < 2,
    )


#: 探针注册表。守卫据此断言「每条声明的臂都有探针在写」（additive 注入即死代码）。
BEHAVIOUR_PROBES: Final[Mapping[str, Callable[[_Runner, dict[str, Any]], Any]]] = {
    "forcesave_five_tuple": _probe_forcesave_five_tuple,
    "frozen_fingerprint": _probe_frozen_fingerprint,
    "application_key": _probe_application_key,
    "application_sequences": _probe_application_sequences,
    "application_fold": _probe_application_fold,
    "operation_links": _probe_operation_links,
    "n_shell_convergence": _probe_n_shell_convergence,
    "recovery": _probe_recovery,
    "delivery": _probe_delivery,
    "scope_index": _probe_scope_index,
    "content_version": _probe_content_version,
    "bundle_slots": _probe_bundle_slots,
    "projection_contract": _probe_projection_contract,
    "typed_markers": _probe_typed_markers,
    "candidate_invisibility": _probe_candidate_invisibility,
    "incoming_states": _probe_incoming_states,
    "application_incoming_fk": _probe_application_incoming_fk,
    "close_capture": _probe_close_capture,
    "leader_promotion": _probe_leader_promotion,
    "frozen_bundle": _probe_frozen_bundle,
    "chain": lambda run, w: _probe_chain(run, w),
}


# ════════════════════════════════════════════════════════════════════════════
# §6 scratch schema 生命周期与复原实证
# ════════════════════════════════════════════════════════════════════════════


async def _run_behaviour(result: dict[str, Any]) -> None:  # noqa: PLR0915 - 一次跑全链
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise Task68GateError(
            "Task 68 的行为侧必须真实 PostgreSQL（正文逐字「真实PostgreSQL独立校验」）。"
            f"当前 DATABASE_URL 为 {str(settings.DATABASE_URL).split('://')[0]}。此处**不 skip**。"
        )
    for migration in SCRATCH_MIGRATIONS:
        if not migration.exists():
            raise Task68GateError(f"缺少迁移文件: {rel(migration)}")

    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(
        str(settings.DATABASE_URL), poolclass=NullPool, connect_args=dict(ssl_off)
    )
    result["schema"] = schema
    result["migrations"] = [m.name for m in SCRATCH_MIGRATIONS]
    result["apply_errors"] = []
    result["probe_errors"] = {}
    engine = None
    try:
        # 复原实证第一步：生产 public schema 的**前置**行数快照。
        async with admin.connect() as conn:
            result["public_before"] = {
                table: int(
                    (
                        await conn.execute(sa.text(f"SELECT count(*) FROM public.{table}"))  # noqa: S608
                    ).scalar_one()
                )
                for table in PRODUCTION_ROW_TABLES
            }
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(
            str(settings.DATABASE_URL),
            poolclass=NullPool,
            connect_args={**ssl_off, "server_settings": {"search_path": schema}},
        )
        async with engine.begin() as conn:
            for stmt in [s.strip() for s in _STUB_DDL.strip().split(";") if s.strip()]:
                await conn.exec_driver_sql(stmt)
        for migration in SCRATCH_MIGRATIONS:
            statements = MigrationRunner._split_sql_statements(
                migration.read_text(encoding="utf-8")
            )
            for idx, stmt in enumerate(statements, 1):
                try:
                    async with engine.begin() as conn:
                        await conn.exec_driver_sql(stmt)
                except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言为空
                    result["apply_errors"].append(
                        {"migration": migration.name, "index": idx, "error": f"{type(exc).__name__}: {exc}"}
                    )
        if result["apply_errors"]:
            raise Task68GateError(f"迁移应用失败: {result['apply_errors'][:3]}")

        observations: dict[str, dict[str, Any]] = {}
        run = _Runner(engine, observations)
        world = await _build_world(run)
        for name, probe in BEHAVIOUR_PROBES.items():
            try:
                await probe(run, world)
            except Exception as exc:  # noqa: BLE001 - 逐探针记录，禁 fail-open
                result["probe_errors"][name] = f"{type(exc).__name__}: {exc}"
        result["observations"] = observations
        result["scratch_row_counts"] = {}
        async with engine.connect() as conn:
            for table in PRODUCTION_ROW_TABLES:
                result["scratch_row_counts"][table] = int(
                    (await conn.execute(sa.text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608
                )
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            async with admin.connect() as conn:
                result["public_after"] = {
                    table: int(
                        (
                            await conn.execute(sa.text(f"SELECT count(*) FROM public.{table}"))  # noqa: S608
                        ).scalar_one()
                    )
                    for table in PRODUCTION_ROW_TABLES
                }
                leftovers = [
                    str(row[0])
                    for row in (
                        await conn.execute(
                            sa.text(
                                "SELECT schema_name FROM information_schema.schemata "
                                "WHERE schema_name LIKE :pat ORDER BY schema_name"
                            ),
                            {"pat": f"{_SCHEMA_PREFIX}%"},
                        )
                    ).all()
                ]
                result["scratch_schema_left"] = len(leftovers)
                # 🔴 「本次这一套是否清干净」与「库里还有没有别人/别轮次的残留」是两件事。
                #    只报总数时，M41（故意删掉 DROP）那类变异实验留下的残留会把本轮的复原
                #    结论打成假红；只报本轮的又会让残留被静默容忍。两个都报。
                result["own_schema_left"] = 1 if schema in leftovers else 0
                result["foreign_scratch_schemas"] = [s for s in leftovers if s != schema]
        finally:
            await admin.dispose()


def run_behaviour_harness() -> dict[str, Any]:
    """跑一次行为侧采集。禁 fail-open：采集失败必须留下 `error` 让判据变红。"""
    _ensure_backend_on_path()
    result: dict[str, Any] = {"error": None, "observations": {}}
    started = time.time()
    try:
        asyncio.run(_run_behaviour(result))
    except Exception as exc:  # noqa: BLE001 - 采集失败如实报告
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["elapsed_seconds"] = round(time.time() - started, 2)
    return result


def restoration_record(harness: Mapping[str, Any]) -> dict[str, Any]:
    """复原实证：生产 public 前后逐表行数必须相等，且无残留 scratch schema。"""
    before = dict(harness.get("public_before") or {})
    after = dict(harness.get("public_after") or {})
    drifted = {
        table: {"before": before.get(table), "after": after.get(table)}
        for table in sorted(set(before) | set(after))
        if before.get(table) != after.get(table)
    }
    left = harness.get("scratch_schema_left")
    own_left = harness.get("own_schema_left")
    foreign = list(harness.get("foreign_scratch_schemas") or [])
    measured = bool(before) and bool(after)
    return {
        "statement": "行为侧只在 scratch schema 写行；生产 `public` schema 前后逐表行数必须逐格相等，"
                     "且本轮创建的那套 `tmp_task68_reg_*` schema 必须被 DROP 干净。",
        "measured": measured,
        "table_count": len(before),
        "public_before": before,
        "public_after": after,
        "drifted_tables": drifted,
        "scratch_schemas_left": left,
        "own_schema_left": own_left,
        "foreign_scratch_schemas": foreign,
        "foreign_scratch_note": (
            "非本轮创建的 `tmp_task68_reg_*` 残留。来源通常是变异实验 M41（**故意**删掉 "
            "`DROP SCHEMA` 以证明清理逻辑有效）—— 如实列出并单独清理，不并进本轮复原结论。"
        ),
        "scratch_row_counts": dict(harness.get("scratch_row_counts") or {}),
        "restored": bool(measured and not drifted and own_left == 0),
        "why_this_is_the_proof": (
            "「跑完没报错」不是复原实证 —— 被 `^C` 中断的运行可能已提交部分变更，判成败一律"
            "**查数据**不看 exit code。前后逐表行数 + 残留 schema 计数是可复算的数据侧判据。"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# §7 子条目 5：完整链路的独立契约判据（真行 + 生产纯函数）
# ════════════════════════════════════════════════════════════════════════════

CHAIN_CHECKS: Final[tuple[Invariant, ...]] = (
    Invariant(
        check_id="chain_representation_binds_approved_bundle_and_children",
        sub_bullet=5,
        statement=(
            "`template → instrumentation → contract → bundle → representation` 的最后一跳："
            "representation 只能由 **approved** bundle finalize，且 bundle digest、authority "
            "model id/digest 与 bundle child 双向锁死。"
        ),
        measured_by="`wpsync_check_representation_identity` 定义 + scratch schema 四臂真插",
        properties=(28, 67, 65, 4),
        requirements=("6.10", "6.18", "8.10", "2.1"),
        schema_requirements=(
            _t(_CR, "trg_wpcr_identity", "wpsync_check_representation_identity"),
            _f("wpsync_check_representation_identity", "只能由 approved bundle finalize",
               "authority model 与 bundle child 未双向锁死",
               "definition_bundle_sha256 与 bundle canonical digest 不一致"),
        ),
        arms=(
            BehaviourArm("chain_rep_legal", "approved bundle + 双向锁死的 representation（对照组）",
                         "accepted"),
            BehaviourArm(
                "chain_rep_candidate_bundle",
                "candidate 状态 bundle 上 finalize representation 必须被拒",
                "rejected",
                ("只能由 approved bundle finalize",),
            ),
            BehaviourArm(
                "chain_rep_bundle_sha_mismatch",
                "representation 的 bundle digest 与 bundle canonical digest 不一致必须被拒",
                "rejected",
                ("与 bundle canonical digest 不一致",),
            ),
            BehaviourArm(
                "chain_rep_authority_mismatch",
                "representation 的 authority model 与 bundle child 不锁死必须被拒",
                "rejected",
                ("authority model 与 bundle child 未双向锁死",),
            ),
        ),
    ),
    Invariant(
        check_id="chain_representation_artifact_kind_and_state",
        sub_bullet=5,
        statement=(
            "representation 的 artifact 只能是 canonical/projection 且 staged/published —— "
            "incoming 与 upgrade_candidate 永不成为 representation 载体。"
        ),
        measured_by="`wpsync_check_representation_identity` 的 artifact 分支 + 三臂真插",
        properties=(17, 67, 5),
        requirements=("5.6", "6.18", "2.4"),
        schema_requirements=(
            _f("wpsync_check_representation_identity",
               "artifact kind 必须为 canonical/projection",
               "artifact state 必须为 staged/published",
               "artifact_sha256 与 artifact 实际 digest 不一致"),
        ),
        arms=(
            BehaviourArm("chain_art_canonical", "canonical published artifact 上建 representation",
                         "accepted"),
            BehaviourArm(
                "chain_art_incoming",
                "incoming artifact 上建 representation 必须被拒",
                "rejected",
                ("artifact kind 必须为 canonical/projection",),
            ),
            BehaviourArm(
                "chain_art_candidate",
                "upgrade_candidate artifact 上建 representation 必须被拒",
                "rejected",
                ("artifact kind 必须为 canonical/projection",),
            ),
            BehaviourArm(
                "chain_art_sha_mismatch",
                "representation 的 artifact_sha256 与 artifact 实际 digest 不一致必须被拒",
                "rejected",
                ("artifact_sha256 与 artifact 实际 digest 不一致",),
            ),
        ),
    ),
    Invariant(
        check_id="chain_historical_frozen_bundle_survives",
        sub_bullet=5,
        statement=(
            "历史 representation 的 frozen bundle 在新 bundle/新 generation 出现后**逐值不变**；"
            "representation 行本身 immutable（升级只能新增 generation）。"
        ),
        measured_by="`trg_wpcr_immutable` 定义 + 新增 generation 后对旧行逐列现算比对",
        properties=(28, 39, 67, 7),
        requirements=("6.10", "9.3", "6.18", "2.10"),
        schema_requirements=(
            _t(_CR, "trg_wpcr_immutable", "wpsync_check_representation_immutable"),
            _f("wpsync_check_representation_immutable", "immutable 行，禁止 UPDATE",
               "升级只能新增 generation"),
        ),
        arms=(
            BehaviourArm("chain_frozen_new_generation", "为同 content version 新增 generation（对照组）",
                         "accepted"),
            BehaviourArm(
                "chain_frozen_update_rejected",
                "UPDATE 历史 representation（任一列，此处用 `reason`）必须被 immutable trigger 拒绝",
                "rejected",
                ("immutable 行，禁止 UPDATE",),
            ),
            BehaviourArm(
                "chain_frozen_values_unchanged",
                "旧 generation 的 bundle id/digest/authority digest 在新 generation 出现后逐值不变",
                "measure",
                expect_measure={
                    "bundle_id_unchanged": True,
                    "bundle_sha_unchanged": True,
                    "authority_sha_unchanged": True,
                    "generations_now": 3,
                },
            ),
        ),
    ),
    Invariant(
        check_id="chain_custom_authority_bundle_typed_children",
        sub_bullet=5,
        statement=(
            "custom / opaque authority bundle 的 optional child 用版本化 typed null marker；"
            "slot omission（SQL NULL）仍然拒绝，representation 可绑定该 bundle。"
        ),
        measured_by="custom bundle 真插 + slot NULL 真拒 + representation 绑定真插",
        properties=(50, 67),
        requirements=("12.6", "6.18"),
        schema_requirements=(
            _nn(_DB, "contract_slot_ref"),
            _c(_DA, "ck_wpsda_authority_model_type", "custom_authoritative_ooxml",
               "opaque_single_onlyoffice"),
        ),
        arms=(
            BehaviourArm("chain_custom_bundle", "custom authority bundle + 三 marker（对照组）",
                         "accepted"),
            BehaviourArm(
                "chain_custom_slot_omitted",
                "custom bundle 省略 contract slot（SQL NULL）必须被拒（实测 BEFORE trigger 先于 "
                "NOT NULL 命中；NOT NULL 仍作 schema 侧要求逐列核对）",
                "rejected",
                ("slot 缺失（type/ref/digest 均不得为 NULL）",),
            ),
            BehaviourArm(
                "chain_custom_representation",
                "representation 绑定 custom authority bundle 必须允许",
                "accepted",
            ),
        ),
    ),
    Invariant(
        check_id="chain_candidate_only_upgrader_and_finalize_owner",
        sub_bullet=5,
        statement=(
            "升级前置阶段只产生 non-current candidate：`ready`/`finalized` 前必须先有 approved "
            "target bundle 与 approved contract；finalize 出的 representation 必须绑定同一 "
            "content version（禁止推进 content revision）。"
        ),
        measured_by="`ck_wpruc_ready_requires_bundle` / `ck_wpruc_finalized_pointer` + "
                    "`wpsync_check_upgrade_candidate` + 四臂真插",
        properties=(5, 67, 4),
        requirements=("2.4", "6.18", "2.1"),
        schema_requirements=(
            _c(_UC, "ck_wpruc_ready_requires_bundle", "ready", "finalized",
               "target_contract_definition_id", "target_definition_bundle_id"),
            _c(_UC, "ck_wpruc_finalized_pointer", "finalized", "finalized_representation_id"),
            _f("wpsync_check_upgrade_candidate", "target bundle 必须 approved",
               "必须为 approved contract definition", "禁止推进 content revision"),
        ),
        arms=(
            BehaviourArm("chain_cand_staged", "staged candidate 必须插入（对照组）", "accepted"),
            BehaviourArm(
                "chain_cand_ready_no_bundle",
                "ready 但缺 target bundle 必须被拒（实测 `wpsync_check_upgrade_candidate` 先命中，"
                "报「target bundle 必须 approved，实得 MISSING」；`ck_wpruc_ready_requires_bundle` "
                "作 schema 侧兜底）",
                "rejected",
                ("target bundle 必须 approved",),
            ),
            BehaviourArm(
                "chain_cand_candidate_contract",
                "target contract 处于 candidate 必须被 wpsync_check_upgrade_candidate 拒绝",
                "rejected",
                ("必须为 approved contract definition",),
            ),
            BehaviourArm(
                "chain_cand_wrong_artifact_kind",
                "candidate 的 staged artifact 必须 kind=upgrade_candidate（canonical 一律拒绝）—— "
                "「upgrade_candidate 永不 published/durable」那一面由 "
                "`candidate_never_current_never_resolvable` 的两条臂在 artifact 表上直接验",
                "rejected",
                ("artifact kind 必须为 upgrade_candidate",),
            ),
        ),
    ),
)

ALL_INVARIANTS: Final[tuple[Invariant, ...]] = INVARIANTS + CHAIN_CHECKS


async def _probe_chain(run: _Runner, w: dict[str, Any]) -> None:  # noqa: PLR0915
    """子条目 5 的真行探针。"""
    bundle1_id, bundle1_sha = w["bundle_1"]
    custom_id, custom_sha = w["bundle_custom"]
    auth1_id, auth1_sha = w["defs"]["authority_proj1"]
    auth_custom_id, auth_custom_sha = w["defs"]["authority_custom"]

    def _rep(
        *,
        entry: str,
        generation: int,
        artifact: str,
        artifact_sha: str,
        bundle: str,
        bundle_sha: str,
        auth: str,
        auth_sha_value: str,
        label: str,
    ) -> tuple[str, dict[str, Any]]:
        sql = (
            "INSERT INTO working_paper_content_representation "
            "(id, wp_id, content_version_id, entry_id, generation, document_type, artifact_id, "
            " artifact_sha256, definition_bundle_id, definition_bundle_sha256, "
            " authority_model_definition_id, authority_model_definition_sha256, adapter_id, "
            " adapter_build_digest, structure_hash, identity_inventory_sha256, reason) "
            "VALUES (:id, :wp, :cv, :entry, :gen, 'xlsx', :art, :art_sha, :bundle, :bundle_sha, "
            " :auth, :auth_sha, 'task68-gate', :adapter, :structure, :inventory, "
            " 'definition_upgrade')"
        )
        return sql, {
            "id": _u(),
            "wp": w["wp_a"],
            "cv": w["cv_a1"],
            "entry": entry,
            "gen": generation,
            "art": artifact,
            "art_sha": artifact_sha,
            "bundle": bundle,
            "bundle_sha": bundle_sha,
            "auth": auth,
            "auth_sha": auth_sha_value,
            "adapter": _d("adapter::task68"),
            "structure": _d(f"structure::{label}"),
            "inventory": _d(f"inventory::{label}"),
        }

    chain_entry = f"{w['entry']}::chain"
    sql, params = _rep(
        entry=chain_entry, generation=1, artifact=w["art_canon"],
        artifact_sha=_d("artifact::canon1"), bundle=bundle1_id, bundle_sha=bundle1_sha,
        auth=auth1_id, auth_sha_value=auth1_sha, label="chain-legal",
    )
    await run.attempt("chain_rep_legal", sql, params)
    run.obs["chain_art_canonical"] = dict(run.obs.get("chain_rep_legal") or {})

    # candidate 状态 bundle
    cand_bundle = _bundle_params(
        w, label="chain-candidate-bundle", authority_key="authority_proj1",
        template=_def_slot(w, "template1"),
        instrumentation=_def_slot(w, "instrumentation1"),
        contract=_def_slot(w, "contract1"),
        payload_artifact_key="art_payload_2",
    )
    if await run.attempt(None, _bundle_sql(), cand_bundle):
        sql, params = _rep(
            entry=chain_entry, generation=2, artifact=w["art_canon"],
            artifact_sha=_d("artifact::canon1"), bundle=cand_bundle["id"],
            bundle_sha=cand_bundle["canonical_payload_sha256"], auth=auth1_id,
            auth_sha_value=auth1_sha, label="chain-cand-bundle",
        )
        await run.attempt("chain_rep_candidate_bundle", sql, params)
    sql, params = _rep(
        entry=chain_entry, generation=3, artifact=w["art_canon"],
        artifact_sha=_d("artifact::canon1"), bundle=bundle1_id,
        bundle_sha=_d("forged-bundle-digest"), auth=auth1_id, auth_sha_value=auth1_sha,
        label="chain-bundle-mismatch",
    )
    await run.attempt("chain_rep_bundle_sha_mismatch", sql, params)
    sql, params = _rep(
        entry=chain_entry, generation=4, artifact=w["art_canon"],
        artifact_sha=_d("artifact::canon1"), bundle=bundle1_id, bundle_sha=bundle1_sha,
        auth=auth_custom_id, auth_sha_value=auth_custom_sha, label="chain-auth-mismatch",
    )
    await run.attempt("chain_rep_authority_mismatch", sql, params)
    sql, params = _rep(
        entry=chain_entry, generation=5, artifact=w["art_inc_durable"],
        artifact_sha=w["art_inc_durable_sha"], bundle=bundle1_id, bundle_sha=bundle1_sha,
        auth=auth1_id, auth_sha_value=auth1_sha, label="chain-incoming",
    )
    await run.attempt("chain_art_incoming", sql, params)
    sql, params = _rep(
        entry=chain_entry, generation=6, artifact=w["art_candidate"],
        artifact_sha=_d("artifact::cand1"), bundle=bundle1_id, bundle_sha=bundle1_sha,
        auth=auth1_id, auth_sha_value=auth1_sha, label="chain-candidate-artifact",
    )
    await run.attempt("chain_art_candidate", sql, params)
    sql, params = _rep(
        entry=chain_entry, generation=7, artifact=w["art_canon"],
        artifact_sha=_d("forged-artifact-digest"), bundle=bundle1_id, bundle_sha=bundle1_sha,
        auth=auth1_id, auth_sha_value=auth1_sha, label="chain-art-mismatch",
    )
    await run.attempt("chain_art_sha_mismatch", sql, params)

    # 历史 frozen bundle：先记下旧值，再新增 generation，再逐值比对
    before = await run.rows(
        "SELECT definition_bundle_id, definition_bundle_sha256, "
        "authority_model_definition_sha256 FROM working_paper_content_representation "
        "WHERE id = :id",
        {"id": w["rep_a1"]},
    )
    sql, params = _rep(
        entry=w["entry"], generation=3, artifact=w["art_canon2"],
        artifact_sha=_d("artifact::canon2"), bundle=custom_id, bundle_sha=custom_sha,
        auth=auth_custom_id, auth_sha_value=auth_custom_sha, label="chain-newgen",
    )
    await run.attempt("chain_frozen_new_generation", sql, params)
    run.obs["chain_custom_representation"] = dict(
        run.obs.get("chain_frozen_new_generation") or {}
    )
    # 🔴 改 bundle digest 会先撞 identity trigger（「与 bundle canonical digest 不一致」），
    #    那条臂就不再度量 immutability。改一个 identity trigger 不读的列（`reason`）才能
    #    真正触发 `wpsync_check_representation_immutable`。
    await run.attempt(
        "chain_frozen_update_rejected",
        "UPDATE working_paper_content_representation SET reason = 'rollback' WHERE id = :id",
        {"id": w["rep_a1"]},
    )
    after = await run.rows(
        "SELECT definition_bundle_id, definition_bundle_sha256, "
        "authority_model_definition_sha256 FROM working_paper_content_representation "
        "WHERE id = :id",
        {"id": w["rep_a1"]},
    )
    generations = int(
        await run.scalar(
            "SELECT count(*) FROM working_paper_content_representation "
            "WHERE wp_id = :wp AND entry_id = :entry",
            {"wp": w["wp_a"], "entry": w["entry"]},
        )
    )
    run.measure(
        "chain_frozen_values_unchanged",
        bundle_id_unchanged=bool(before and after)
        and str(before[0]["definition_bundle_id"]) == str(after[0]["definition_bundle_id"]),
        bundle_sha_unchanged=bool(before and after)
        and before[0]["definition_bundle_sha256"] == after[0]["definition_bundle_sha256"],
        authority_sha_unchanged=bool(before and after)
        and before[0]["authority_model_definition_sha256"]
        == after[0]["authority_model_definition_sha256"],
        generations_now=generations,
    )

    # custom bundle：对照组已在世界搭建阶段真插成功
    run.obs["chain_custom_bundle"] = {"accepted": True, "rejection": None}
    omitted = _bundle_params(
        w, label="chain-custom-omitted", authority_key="authority_custom",
        template=_marker_slot(w, "template"),
        instrumentation=_marker_slot(w, "instrumentation"),
        contract=_marker_slot(w, "contract"),
        payload_artifact_key="art_payload_3",
    )
    omitted["contract_slot_ref"] = None
    await run.attempt("chain_custom_slot_omitted", _bundle_sql(), omitted)

    # candidate-only upgrader / finalize owner
    def _candidate(
        *,
        state: str,
        artifact: str,
        artifact_sha: str,
        contract_key: str | None,
        bundle: str | None,
        label: str,
    ) -> tuple[str, dict[str, Any]]:
        contract_id = None if contract_key is None else w["defs"][contract_key][0]
        sql = (
            "INSERT INTO working_paper_representation_upgrade_candidate "
            "(id, wp_id, content_version_id, entry_id, source_representation_id, "
            " staged_artifact_id, staged_artifact_sha256, template_definition_id, "
            " instrumentation_definition_id, target_contract_definition_id, "
            " target_definition_bundle_id, state) "
            "VALUES (:id, :wp, :cv, :entry, :src, :art, :art_sha, :tpl, :ins, :contract, "
            " :bundle, :state)"
        )
        return sql, {
            "id": _u(),
            "wp": w["wp_a"],
            "cv": w["cv_a1"],
            "entry": f"{w['entry']}::cand::{label}",
            "src": w["rep_a1"],
            "art": artifact,
            "art_sha": artifact_sha,
            "tpl": w["defs"]["template1"][0],
            "ins": w["defs"]["instrumentation1"][0],
            "contract": contract_id,
            "bundle": bundle,
            "state": state,
        }

    sql, params = _candidate(
        state="staged", artifact=w["art_candidate"], artifact_sha=_d("artifact::cand1"),
        contract_key=None, bundle=None, label="staged",
    )
    await run.attempt("chain_cand_staged", sql, params)
    sql, params = _candidate(
        state="ready", artifact=w["art_candidate"], artifact_sha=_d("artifact::cand1"),
        contract_key=None, bundle=None, label="ready-no-bundle",
    )
    await run.attempt("chain_cand_ready_no_bundle", sql, params)
    sql, params = _candidate(
        state="ready", artifact=w["art_candidate"], artifact_sha=_d("artifact::cand1"),
        contract_key="contract_candidate", bundle=bundle1_id, label="candidate-contract",
    )
    await run.attempt("chain_cand_candidate_contract", sql, params)
    sql, params = _candidate(
        state="staged", artifact=w["art_canon"], artifact_sha=_d("artifact::canon1"),
        contract_key=None, bundle=None, label="wrong-artifact-kind",
    )
    await run.attempt("chain_cand_wrong_artifact_kind", sql, params)


# ════════════════════════════════════════════════════════════════════════════
# §8 子条目 4：用户端点的独立形态/顺序判据（AST，禁字符串存在）
# ════════════════════════════════════════════════════════════════════════════

#: 正文点名的全用户端点。**写死**在这里 —— 只迭代路由表的判据在路由被删空时照样绿（教训 16）。
REQUIRED_ENDPOINTS: Final[tuple[tuple[str, str, str], ...]] = (
    ("post", "/pending-mutations", "create_pending_mutation"),
    ("post", "/materialize", "materialize"),
    ("post", "/rooms/{room_id}/confirm-descriptor", "confirm_descriptor"),
    ("post", "/rooms/{room_id}/forcesave", "request_forcesave"),
    ("post", "/rooms/{room_id}/close-intents", "create_close_intent"),
    ("get", "/recovery-cases", "list_recovery_cases"),
    ("post", "/recovery-cases/{case_id}/claim", "claim_recovery_case"),
    ("post", "/recovery-cases/{case_id}/download-only", "terminate_recovery_download_only"),
    ("get", "/operations/{operation_id}", "get_operation"),
    ("get", "/operations/{operation_id}/conflicts", "get_operation_conflicts"),
    ("get", "/operations/{operation_id}/timeline", "get_operation_timeline"),
    ("post", "/operations/{operation_id}/resolve", "resolve_conflicts"),
    ("post", "/versions/{version_id}/rollback", "rollback_version"),
)

#: 统一拒绝面：scope 不可见族 → 404，授权族 → 403。守卫据此逐类断言。
_REFUSAL_EXPECTATION: Final[Mapping[str, int]] = {
    "SyncScopeInvisibleError": 404,
    "SyncActionForbiddenError": 403,
}


def _router_routes() -> list[dict[str, Any]]:
    """从 AST 读出每个 route 的 method / 路径后缀 / handler 名 / 是否挂在 USER_SYNC_PREFIX。"""
    tree = module_ast(ROUTER_PY)
    routes: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            target = dotted_name(deco.func)
            if target is None or not target.startswith(("router.", "public_router.")):
                continue
            method = target.split(".", 1)[1]
            arg = deco.args[0] if deco.args else None
            prefixed = (
                isinstance(arg, ast.BinOp)
                and isinstance(arg.op, ast.Add)
                and dotted_name(arg.left) == "USER_SYNC_PREFIX"
                and isinstance(arg.right, ast.Constant)
            )
            suffix = arg.right.value if prefixed else (
                arg.value if isinstance(arg, ast.Constant) else None
            )
            routes.append(
                {
                    "router": target.split(".", 1)[0],
                    "method": method,
                    "prefixed": prefixed,
                    "suffix": suffix,
                    "handler": node.name,
                }
            )
    return routes


def _awaited_call_order(handler: str) -> list[str]:
    """handler 体内 `await <call>` 的点号名序列（顺序判据的载体）。"""
    node = function_def(module_ast(ROUTER_PY), handler)
    order: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call):
            name = dotted_name(sub.value.func)
            if name:
                order.append(name)
    # ast.walk 不保证顺序 ⇒ 按源码位置排序。
    located = [
        (sub.lineno, sub.col_offset, dotted_name(sub.value.func))
        for sub in ast.walk(node)
        if isinstance(sub, ast.Await)
        and isinstance(sub.value, ast.Call)
        and dotted_name(sub.value.func)
    ]
    return [name for _, _, name in sorted(located)]


def _handler_param_annotations(handler: str) -> dict[str, str]:
    node = function_def(module_ast(ROUTER_PY), handler)
    out: dict[str, str] = {}
    for arg in list(node.args.args) + list(node.args.kwonlyargs):
        out[arg.arg] = "" if arg.annotation is None else (dotted_name(arg.annotation) or
                                                          ast.unparse(arg.annotation))
    return out


def _prefix_literal() -> str:
    tree = module_ast(ROUTER_PY)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(dotted_name(t) == "USER_SYNC_PREFIX" for t in node.targets)
            and isinstance(node.value, ast.Constant)
        ):
            return str(node.value.value)
    raise Task68GateError("router AST 里找不到 USER_SYNC_PREFIX 字面量")


def _guard_refusal_map() -> dict[str, int]:
    """从 `endpoint_guard._REFUSAL_STATUS` 的 AST 读出拒绝类 → HTTP 状态。"""
    tree = module_ast(GUARD_PY)
    out: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and dotted_name(node.target) == "_REFUSAL_STATUS":
            value = node.value
            if isinstance(value, ast.Call) and value.args:
                value = value.args[0]
            if isinstance(value, ast.Dict):
                for key, val in zip(value.keys, value.values, strict=False):
                    name = dotted_name(key) if key is not None else None
                    if name and isinstance(val, ast.Constant):
                        out[name] = int(val.value)
    return out


def guard_first_violations(orders: Mapping[str, Sequence[str]]) -> list[str]:
    """「`_guard` 必须是 handler 的第一个 await」的**纯函数**判据。

    🔴 抽成独立可测种子的理由：判据写在 AST 遍历里时，守卫只能重算 handler 的 await 序列
    自己判一遍 —— 那度量的是**路由代码**，不是**本门的检测器**。检测器被短路（`elif False`）
    时守卫照样绿（变异检验实测 GREEN）。抽出来后可以直接喂合成顺序检验它。
    """
    violations: list[str] = []
    for handler, order in orders.items():
        if "_guard" not in order:
            violations.append(f"{handler}: 体内没有 await _guard(...)")
        elif list(order).index("_guard") != 0:
            violations.append(f"{handler}: _guard 不是第一个 await（实得 {list(order)[:3]}）")
    return violations


def classify_refusal_site(
    status: int | None, *, after_guard: bool, error_code: str | None
) -> str:
    """把一个 `HTTPException(status_code=...)` 构造点分桶。

    同样抽成纯函数：分桶写在 AST 遍历里时，`if status == 404` 被短路后守卫无从察觉。
    """
    if status == 404:
        return "raw_404"
    if status == 403:
        if not after_guard or not error_code:
            return "bad_403"
        return "post_guard_403"
    return "other"


def build_endpoint_checks() -> list[dict[str, Any]]:  # noqa: PLR0915
    """子条目 4 的逐条判据。全部走 AST，禁「import 存在 / 字符串出现」。"""
    routes = _router_routes()
    prefix = _prefix_literal()
    by_key = {(r["method"], r["suffix"]): r for r in routes if r["router"] == "router"}
    checks: list[dict[str, Any]] = []

    def _add(
        check_id: str,
        statement: str,
        measured_by: str,
        properties: tuple[int, ...],
        requirements: tuple[str, ...],
        passed: bool,
        detail: Any,
    ) -> None:
        checks.append(
            {
                "check_id": check_id,
                "sub_bullet": 4,
                "statement": statement,
                "measured_by": measured_by,
                "owner_task": OWNER_TASK,
                "properties": [f"Property {p}" for p in properties],
                "requirements": list(requirements),
                "passed": bool(passed),
                "detail": detail,
            }
        )

    # E1：显式 project / wp / entry
    missing = [
        f"{m.upper()} {s}"
        for (m, s, _handler) in REQUIRED_ENDPOINTS
        if (m, s) not in by_key or not by_key[(m, s)]["prefixed"]
    ]
    scope_params = [p for p in ("{project_id}", "{wp_id}", "{entry_id:path}") if p not in prefix]
    _add(
        "endpoints_carry_explicit_project_wp_entry",
        "正文点名的 13 个用户端点全部挂在 `USER_SYNC_PREFIX` 上，而该前缀逐项含 "
        "`{project_id}` / `{wp_id}` / `{entry_id:path}` —— 任何端点不得靠隐式上下文推 scope。",
        "router AST：装饰器首参必须是 `USER_SYNC_PREFIX + \"...\"` 的 BinOp；前缀字面量逐段核对",
        (43, 69),
        ("10.10", "12.10", "14.13"),
        not missing and not scope_params,
        {
            "required": len(REQUIRED_ENDPOINTS),
            "not_prefixed_or_missing": missing,
            "prefix_literal": prefix,
            "scope_params_missing": scope_params,
        },
    )

    # E2：recovery list 另带 room / generation
    recovery_params = _handler_param_annotations("list_recovery_cases")
    _add(
        "recovery_list_requires_room_and_generation",
        "`GET /recovery-cases` 除 project/wp/entry 外必须显式带 room 与 generation。",
        "handler 形参 AST（`room_id` / `generation` 必须在签名里）",
        (69, 71),
        ("12.10", "14.16"),
        "room_id" in recovery_params and "generation" in recovery_params,
        {"params": sorted(recovery_params)},
    )

    # E3：rollback 的 route key 是 opaque content-version id，且 opaqueness 由 guard 判定
    #
    # 🔴 首轮判据写的是「`version_id` 形参必须标注 `uuid.UUID`」—— 实测是 `str`，而源码里
    #    写明了原因：声明成 UUID 时 `/versions/11/rollback` 会被 FastAPI 拦成 **422**，与统一
    #    404 oracle 不同桶（存在性泄露），且「numeric revision 不得作 route key」这条会由框架
    #    顺手实现、本模块无从证伪。所以正确的独立判据是「opaqueness 经 guard 的 scope ref 判定」，
    #    而不是形参注解。判据按事实改，不按预期改。
    rollback_params = _handler_param_annotations("rollback_version")
    rollback_src = ast.unparse(function_def(module_ast(ROUTER_PY), "rollback_version"))
    guard_error_classes = {
        node.name
        for node in ast.walk(module_ast(GUARD_PY))
        if isinstance(node, ast.ClassDef)
    }
    opaque_ref_built = (
        "ScopeResourceKind.content_version" in rollback_src
        and "resource_id=str(version_id)" in rollback_src
    )
    guard_enforces_opaque = {
        "OpaqueResourceIdRequiredError",
        "VersionIdNotUuidError",
    } <= guard_error_classes
    downstream_uuid = "uuid.UUID(str(version_id))" in rollback_src
    _add(
        "rollback_route_key_is_opaque_content_version_id",
        "`POST /versions/{version_id}/rollback` 的 route key 是 immutable opaque content-version "
        "id：handler 把它包成 `ScopeRef(content_version, str(version_id))` 交 guard 判定 —— "
        "numeric revision 由 guard 的 `OpaqueResourceIdRequiredError` / `VersionIdNotUuidError` "
        "统一走 404（不是 422），下游再转成 `uuid.UUID`。",
        "route 后缀字面量 + handler AST 里 ScopeRef 构造实参 + endpoint_guard 的拒绝类现算",
        (37, 7),
        ("8.7", "2.10", "14.13"),
        ("post", "/versions/{version_id}/rollback") in by_key
        and "version_id" in rollback_params
        and opaque_ref_built
        and guard_enforces_opaque
        and downstream_uuid,
        {
            "route_present": ("post", "/versions/{version_id}/rollback") in by_key,
            "version_id_annotation": rollback_params.get("version_id", ""),
            "annotation_note": "刻意是 `str`（源码有说明）：声明成 UUID 会让 numeric revision 被 "
                               "FastAPI 拦成 422，泄露存在性并绕开本模块的判据",
            "opaque_scope_ref_built": opaque_ref_built,
            "guard_has_opaque_refusals": sorted(
                {"OpaqueResourceIdRequiredError", "VersionIdNotUuidError"} & guard_error_classes
            ),
            "downstream_converts_to_uuid": downstream_uuid,
        },
    )

    # E4：没有任何 route 用 numeric revision 作 key
    revision_routes = [
        f"{r['method'].upper()} {r['suffix']}"
        for r in routes
        if isinstance(r["suffix"], str) and "revision" in r["suffix"]
    ]
    _add(
        "no_route_uses_numeric_revision_as_key",
        "整张路由表没有任何路径模板把 numeric revision 当 route/resource key。",
        "全部 route 后缀字面量现算（含 public_router）",
        (37,),
        ("8.7", "14.13"),
        not revision_routes,
        {"route_count": len(routes), "revision_routes": revision_routes},
    )

    # E5：授权先于业务读 —— guard 必须是 handler 的第一个 await
    order_rows: dict[str, Any] = {
        handler: _awaited_call_order(handler)
        for _method, _suffix, handler in REQUIRED_ENDPOINTS
    }
    violations = guard_first_violations(order_rows)
    _add(
        "guard_is_the_first_await_in_every_handler",
        "scope-index-before-resource：每个 handler 的**第一个** `await` 就是 `_guard(...)`，"
        "任何业务读写都在授权之后。",
        "handler 体内 `await <call>` 的按源码位置排序序列（AST，不是字符串出现）",
        (43, 16),
        ("10.10", "5.2", "14.13"),
        not violations,
        {"violations": violations, "awaited_order": order_rows},
    )

    # E6：统一 404/403 —— 拒绝面只有一处翻译
    # E6：统一 404/403
    #
    # 🔴 首轮判据写的是「handler 自己不得 raise `_not_found`」—— 实测 `list_recovery_cases` /
    #    `claim_recovery_case` 都会（资源不存在也要 404 且不得泄露）。那不是缺陷，判据本身错了。
    #    正确的独立判据是「**只有一处**构造 404/403 的 HTTPException」：所有 404 都经 `_not_found()`
    #    工厂、所有 403 都经 `_forbidden()`，router 里不得出现裸 `HTTPException(status_code=404/403)`。
    refusal = _guard_refusal_map()
    mismatch = {
        name: {"expected": status, "actual": refusal.get(name)}
        for name, status in _REFUSAL_EXPECTATION.items()
        if refusal.get(name) != status
    }
    factory_names = {"_not_found", "_forbidden"}
    router_tree = module_ast(ROUTER_PY)
    factory_bodies = {
        node.name: node
        for node in ast.walk(router_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in factory_names
    }
    raw_404_sites: list[str] = []
    raw_403_sites: list[dict[str, Any]] = []
    for node in ast.walk(router_tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in factory_names:
            continue
        guard_line = min(
            (
                sub.lineno
                for sub in ast.walk(node)
                if isinstance(sub, ast.Await)
                and isinstance(sub.value, ast.Call)
                and dotted_name(sub.value.func) == "_guard"
            ),
            default=None,
        )
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call) or dotted_name(sub.func) != "HTTPException":
                continue
            status = next(
                (
                    int(kw.value.value)
                    for kw in sub.keywords
                    if kw.arg == "status_code" and isinstance(kw.value, ast.Constant)
                ),
                None,
            )
            detail = next((kw.value for kw in sub.keywords if kw.arg == "detail"), None)
            error_code = None
            if isinstance(detail, ast.Dict):
                for key, val in zip(detail.keys, detail.values, strict=False):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "error_code"
                        and isinstance(val, ast.Constant)
                    ):
                        error_code = str(val.value)
            after_guard = guard_line is not None and sub.lineno > guard_line
            bucket = classify_refusal_site(
                status, after_guard=after_guard, error_code=error_code
            )
            if bucket == "raw_404":
                raw_404_sites.append(f"{node.name}:{sub.lineno}")
            elif bucket in ("post_guard_403", "bad_403"):
                raw_403_sites.append(
                    {
                        "site": f"{node.name}:{sub.lineno}",
                        "after_guard": after_guard,
                        "error_code": error_code,
                        "bucket": bucket,
                    }
                )
    bad_403 = [site for site in raw_403_sites if site["bucket"] == "bad_403"]
    _add(
        "unified_404_403_refusal_surface",
        "404 是存在性敏感码 ⇒ **只能**经 `_not_found()` 工厂构造（router 里零裸 404）。"
        "403 除 `_forbidden()` 外还允许 handler 在**授权之后**因 payload 级禁止动作拒绝"
        "（例如客户端直接发 `close_capture`），但每处必须 (a) 位于 `_guard` 之后、"
        "(b) 带 `error_code` —— 授权前的 403 会泄露存在性，无 error_code 的 403 客户端无法分桶。",
        "`endpoint_guard._REFUSAL_STATUS` 的 AST + router 全模块 HTTPException 构造点现算"
        "（含与 `_guard` 的行序比较与 detail.error_code 提取）",
        (43, 16),
        ("10.10", "5.2"),
        not mismatch and not raw_404_sites and not bad_403
        and factory_names <= set(factory_bodies),
        {
            "refusal_map": refusal,
            "mismatch": mismatch,
            "factories_present": sorted(factory_bodies),
            "raw_404_construction_sites": raw_404_sites,
            "post_guard_403_sites": raw_403_sites,
            "bad_403_sites": bad_403,
            "why_403_is_not_absolute": "首轮判据把 handler 调用 `_not_found()` 也算违规 —— 实测 "
                                      "`list_recovery_cases` / `claim_recovery_case` 都会（资源不存在"
                                      "也必须走同一个 404），那不是缺陷，是判据写错了。判据按事实改。",
        },
    )

    # E7：duplicate operation 按 requested id 授权
    resolve_src = ast.unparse(function_def(module_ast(ROUTER_PY), "resolve_conflicts"))
    retry_src = ast.unparse(function_def(module_ast(ROUTER_PY), "retry_operation"))
    resolve_guard_uses_requested = "_operation_ref(operation_id)" in resolve_src
    retry_guard_uses_requested = "_operation_ref(operation_id)" in retry_src
    _add(
        "duplicate_operation_authorization_keyed_on_requested_id",
        "`resolve` / `retry` 的授权 ref 用**请求里那个** operation id（而不是先跳到 canonical "
        "primary 再授权）—— 否则「先跳转后授权」会让无权用户借 duplicate 指针读到 primary。",
        "handler AST 源里 `_guard(..., refs=_operation_ref(operation_id))` 的实参现算",
        (43, 18),
        ("10.10", "5.5", "8.5"),
        resolve_guard_uses_requested and retry_guard_uses_requested,
        {
            "resolve_uses_requested_id": resolve_guard_uses_requested,
            "retry_uses_requested_id": retry_guard_uses_requested,
        },
    )
    return checks


# ════════════════════════════════════════════════════════════════════════════
# §9 子条目 1/6：辐射面按引用关系反查 + 真实 pytest 执行记录
# ════════════════════════════════════════════════════════════════════════════

#: 被验对象的**模块路径级**引用形态。刻意不用业务词（"delivery"/"outbox"/"migration"）——
#: 那样会把几十个无关模块的测试拉进来（首轮实测 207 个文件，一半是别的 spec 的）。
_SURFACE_PATTERNS: Final[tuple[tuple[str, str], ...]] = (
    ("sync_services_module", r"app\.services\.workpaper_sync"),
    ("sync_orm_module", r"app\.models\.workpaper_sync_models|workpaper_sync_models"),
    ("sync_router_module", r"app\.routers\.wp_sync_router|wp_sync_router"),
    ("scratch_migrations", r"V15[12]__"),
    ("sync_package_path", r"services[\"'/\\ ]+workpaper_sync|\"workpaper_sync\""),
)

TEST_ROOT: Final[Path] = BACKEND / "tests"


def radiation_surface() -> dict[str, Any]:
    """按引用关系现算辐射面。**不手抄清单** —— 手抄的清单在生产模块改名后静静过期。"""
    compiled = [(name, re.compile(pattern)) for name, pattern in _SURFACE_PATTERNS]
    files: dict[str, list[str]] = {}
    scanned = 0
    for path in sorted(TEST_ROOT.rglob("test_*.py")):
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        why = [name for name, pattern in compiled if pattern.search(text)]
        if why:
            files[path.relative_to(REPO).as_posix()] = why
    in_dir = sorted(p for p in files if "/tests/workpaper_sync/" in p)
    outside = sorted(p for p in files if "/tests/workpaper_sync/" not in p)
    dir_all = sorted(
        p.relative_to(REPO).as_posix()
        for p in (TEST_ROOT / "workpaper_sync").glob("test_*.py")
    )
    out_of_surface = [p for p in dir_all if p not in files]
    return {
        "statement": "辐射面 = `backend/tests/**/test_*.py` 中**按模块路径引用**到本次被验生产单元"
                     "（`app.services.workpaper_sync.*` / `workpaper_sync_models` / "
                     "`wp_sync_router` / V151・V152）的测试文件全集。不跑无边界全量。",
        "patterns": {name: pattern for name, pattern in _SURFACE_PATTERNS},
        "scanned_test_files": scanned,
        "surface_size": len(files),
        "inside_workpaper_sync_dir": len(in_dir),
        "outside_workpaper_sync_dir": len(outside),
        "outside_files": outside,
        "files": dict(sorted(files.items())),
        "in_dir_but_out_of_surface": out_of_surface,
        "in_dir_but_out_of_surface_note": (
            "这些文件在 `workpaper_sync/` 目录里但**不引用**任何被验生产单元（只读 data/JSON 与"
            "schema 契约），按引用关系判据它们不在辐射面。如实列出，不偷偷补进分母也不假装覆盖。"
        ),
        "digest": digest_of(sorted(files)),
    }


#: 基线里的既存红。**不修**（不属本任务；改 source commit 会让 Task 70 的 evidence stale）。
PREEXISTING_FAILURES: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "file": "backend/tests/workpaper_sync/test_task20_writer_gate.py",
        "failed": 1,
        "errors": 0,
        "nodeid_contains": "test_the_lane_is_part_of_the_freshness_contract",
        "attribution": "writer lane 的 freshness contract 判据在当前 source commit 下不满足",
        "owner_task": "20",
        "why_not_fixed_here": "Task 68 是独立回归，正文未授权改生产代码；修它会改 source commit "
                              "并让 Task 70 尚未刷新的 evidence 全部 stale",
    },
    {
        "file": "backend/tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py",
        "failed": 2,
        "errors": 0,
        "nodeid_contains": "_is_fresh",
        "attribution": "Excel pilot gate 的两条 freshness 判据依赖 Task 70 尚未刷新的 evidence",
        "owner_task": "70",
        "why_not_fixed_here": "本任务明令不冒充真实 OO probe/evidence 已通过；freshness 只能由 "
                              "Task 70 真跑 OO 场景后刷新",
    },
    {
        "file": "backend/tests/workpaper_sync/test_task73_entry_profile_manifest.py",
        "failed": 8,
        "errors": 0,
        "nodeid_contains": "",
        # 🔴 引用上游任务时**不写字面 `Task 67`**：上游 structural pre-reconcile 的入向扫描
        #    面覆盖 `backend/data/**` 并 grep 那个 bigram，本报告一落进 `backend/data/` 就会
        #    给它凭空多出一条入向义务，直接打红它的逐字节锁。已实测证明（把本报告移出
        #    `backend/data/` 后它的两条判据立刻转绿）。改写引用形式即可，无需改上游产物。
        "attribution": "磁盘 entry manifest 已落后于最终源码（上游 structural pre-reconcile"
                        "（任务 67）实测 overlay approved digest b0fd31f1… vs 源码现算 "
                        "5756356a…，48 条 entry 的 source digest 变了）",
        "owner_task": "73",
        "why_not_fixed_here": "manifest / overlay 是**只读**输入；重写它等于替复核方签「mount diff 已复核」",
    },
    {
        "file": "backend/tests/workpaper_sync/test_task30_closure_gate.py",
        "failed": 0,
        "errors": 6,
        "nodeid_contains": "",
        "attribution": "closure gate 的 fixture 在当前供给（published representation / test run 全 0 行）"
                       "下无法建立 ⇒ collection/setup 阶段 ERROR",
        "owner_task": "30",
        "why_not_fixed_here": "供给是 Task 70 的产出；本任务不造 evidence",
    },
    # ── 以下两条是**本次独立回归新发现**的既存红（不在交办基线的 11+6 里）───────────
    {
        "file": "backend/tests/test_workpaper_writer_inventory.py",
        "failed": 2,
        "errors": 0,
        "nodeid_contains": "",
        "attribution": "`backend/data/workpaper_writer_inventory.json` 与 "
                       "`workpaper_writer_domain_overlay.json` 在 git 里是 `??` 未跟踪且 "
                       "`source_digest` 已落后于生产 writer 的 AST（并发会话漂移）。与交办基线里 "
                       "`test_task44…::test_writer_inventory_is_still_fresh` 同一根因。",
        "owner_task": "20",
        "why_not_fixed_here": "本任务不改生产代码也不重生成他人的数据产物；重跑 inventory "
                              "生成器会覆盖并发会话在用的文件。**已排除本任务为成因**："
                              "本门新增的两个文件既不在 `backend/app`（inventory 的扫描面），"
                              "也不是 content writer。",
        "discovered_by_this_task": True,
    },
    {
        "file": "backend/tests/workpaper_sync/test_task67_structural_pre_reconcile.py",
        "failed": 0,
        "errors": 0,
        "nodeid_contains": "",
        "attribution": "首轮实测这里有 2 条红（`test_check_matches_the_file_on_disk` 与 "
                       "`test_inbound_scan_recomputes_and_contains_the_real_targets`），根因是"
                       "**本报告自己**：上游 structural pre-reconcile 的入向扫描面覆盖 "
                       "`backend/data/**` 并 grep 任务号 bigram，本报告一落地就给它多出一条入向"
                       "义务。已用「把本报告移出 `backend/data/` 后两条立刻转绿」证明因果，"
                       "并通过改写本报告里的引用形式消除碰撞（不改上游产物）。",
        "owner_task": "68",
        "why_not_fixed_here": "已在本任务内消除（改引用形式），故期望值为 0/0；"
                              "顺带暴露上游那条判据对「`backend/data/` 目录会增长」不鲁棒。",
        "discovered_by_this_task": True,
    },
)


def _parse_pytest_output(text: str) -> dict[str, Any]:
    """从 pytest 输出现算分类计数与失败 nodeid。"""
    failed = sorted({line.split(" ", 1)[1].split(" ")[0] for line in text.splitlines()
                     if line.startswith("FAILED ")})
    errors = sorted({line.split(" ", 1)[1].split(" ")[0] for line in text.splitlines()
                     if line.startswith("ERROR ")})
    tail = [line for line in text.splitlines() if re.search(r"\d+ (passed|failed|error)", line)]
    summary = tail[-1] if tail else ""
    counts = {
        key: int(match.group(1))
        for key in ("passed", "failed", "xfailed", "xpassed", "skipped", "error", "errors")
        if (match := re.search(rf"(\d+) {key}\b", summary))
    }
    return {
        "summary_line": summary.strip(),
        "counts": counts,
        "failed_nodeids": failed,
        "error_nodeids": errors,
    }


#: 本任务自己的守卫。它**不在**辐射面里（它验的是本门，不引用被验生产单元），但必须与
#: 辐射面在**同一次**执行里跑掉，否则「本门自己绿不绿」没有实证。
OWN_GUARD_PATH: Final[str] = "backend/tests/workpaper_sync/test_task68_backend_chain_regression.py"


def run_radiation_suites(surface: Mapping[str, Any]) -> dict[str, Any]:
    """真跑辐射面（十余分钟）。**从仓库根执行**（正文逐字）。"""
    files = sorted(surface["files"])
    if not files:
        raise Task68GateError("辐射面为空 —— 现算失败时不得当作「无需回归」")
    if not (REPO / OWN_GUARD_PATH).exists():
        raise Task68GateError(f"缺少本任务守卫 {OWN_GUARD_PATH}")
    to_run = files if OWN_GUARD_PATH in files else [*files, OWN_GUARD_PATH]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        sys.executable, "-m", "pytest", *to_run,
        # `-rfE`：`-rf` 只列 FAILED，ERROR 不进短摘要 ⇒ 6 个 collection/setup ERROR 会被
        # 漏成「无 nodeid」，既存红逐项核对就永远对不上（首轮实测踩到）。
        "-q", "--no-header", "--tb=no", "-rfE", "-p", "no:randomly",
    ]
    started = time.time()
    proc = subprocess.run(  # noqa: S603
        cmd,
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
        timeout=3600,
    )
    parsed = _parse_pytest_output(proc.stdout or "")
    return {
        "provenance": "recorded_from_real_execution",
        "executed_from": ".",
        "command": " ".join(["python", "-m", "pytest",
                             f"<{len(files)} 个辐射面文件 + 本任务守卫>",
                             "-q", "--no-header", "--tb=no", "-rfE", "-p", "no:randomly"]),
        "file_count": len(files),
        "executed_file_count": len(to_run),
        "own_guard_included": True,
        "own_guard_path": OWN_GUARD_PATH,
        "files_digest": surface["digest"],
        "returncode": proc.returncode,
        "elapsed_seconds": round(time.time() - started, 1),
        **parsed,
    }


def evaluate_suite_run(
    suite: Mapping[str, Any] | None, surface: Mapping[str, Any]
) -> dict[str, Any]:
    """核对 suite 记录：文件清单必须与现算辐射面一致，既存红必须逐项对上。"""
    if not suite:
        return {
            "state": "not_executed",
            "detail": "辐射面 pytest 未执行 —— 子条目 1 无结论。用 `--write --run-suites` 真跑一次。",
            "surface_digest_matches": None,
            "preexisting": [],
            "passed": False,
        }
    digest_matches = suite.get("files_digest") == surface["digest"]
    counts = dict(suite.get("counts") or {})
    failed_nodeids = list(suite.get("failed_nodeids") or [])
    error_nodeids = list(suite.get("error_nodeids") or [])
    observed_failed = counts.get("failed", 0)
    observed_errors = counts.get("error", counts.get("errors", 0))

    rows: list[dict[str, Any]] = []
    for entry in PREEXISTING_FAILURES:
        stem = Path(str(entry["file"])).name
        matched_failed = [n for n in failed_nodeids if stem in n]
        matched_errors = [n for n in error_nodeids if stem in n]
        rows.append(
            {
                **{k: v for k, v in entry.items()},
                "observed_failed": len(matched_failed),
                "observed_errors": len(matched_errors),
                "agrees": len(matched_failed) == int(entry["failed"])
                and len(matched_errors) == int(entry["errors"]),
                "nodeids": sorted(matched_failed + matched_errors),
            }
        )
    declared_failed = sum(int(e["failed"]) for e in PREEXISTING_FAILURES)
    declared_errors = sum(int(e["errors"]) for e in PREEXISTING_FAILURES)
    # 🔴 本任务守卫的失败**不是**「未登记的既存红」，而是本门自己的结论；必须单列。
    #    否则会自指：run N 的守卫读 run N-1 的报告，它的滞后失败进了 run N 的
    #    `unexpected_failed`，run N+1 的守卫又因此失败 —— 永不收敛。
    own_guard_stem = Path(OWN_GUARD_PATH).name
    own_guard_failed = sorted(n for n in failed_nodeids if own_guard_stem in n)
    own_guard_errors = sorted(n for n in error_nodeids if own_guard_stem in n)
    unexpected_failed = sorted(
        n
        for n in failed_nodeids
        if own_guard_stem not in n
        and not any(Path(str(e["file"])).name in n for e in PREEXISTING_FAILURES)
    )
    unexpected_errors = sorted(
        n
        for n in error_nodeids
        if own_guard_stem not in n
        and not any(Path(str(e["file"])).name in n for e in PREEXISTING_FAILURES)
    )
    return {
        "state": "executed",
        "provenance": suite.get("provenance"),
        "command": suite.get("command"),
        "executed_from": suite.get("executed_from"),
        "file_count": suite.get("file_count"),
        "executed_file_count": suite.get("executed_file_count"),
        "own_guard_included": suite.get("own_guard_included"),
        "own_guard_path": suite.get("own_guard_path"),
        "elapsed_seconds": suite.get("elapsed_seconds"),
        "surface_digest_matches": digest_matches,
        "counts": counts,
        "summary_line": suite.get("summary_line"),
        "declared_preexisting_failed": declared_failed,
        "declared_preexisting_errors": declared_errors,
        "observed_failed": observed_failed,
        "observed_errors": observed_errors,
        "preexisting": rows,
        "preexisting_all_agree": all(r["agrees"] for r in rows),
        "unexpected_failed_nodeids": unexpected_failed,
        "unexpected_error_nodeids": unexpected_errors,
        "own_guard_result": {
            "path": OWN_GUARD_PATH,
            "failed": own_guard_failed,
            "errors": own_guard_errors,
            "clean": not own_guard_failed and not own_guard_errors,
            "note": "本门守卫在那次执行里的结果。它读的是**上一份**报告（pytest 先跑、报告后写），"
                    "所以首轮改动后必然滞后一轮；连续两次 `--write --run-suites` 即收敛。",
        },
        "passed": bool(
            digest_matches
            and all(r["agrees"] for r in rows)
            and not unexpected_failed
            and not unexpected_errors
            and not own_guard_failed
            and not own_guard_errors
        ),
        "not_fixed_here": "17 条既存红（11 failed + 6 errors）如实登记，**一条都不修** —— "
                          "不属本任务，且会改 source commit 让 Task 70 的 evidence stale。",
    }


# ════════════════════════════════════════════════════════════════════════════
# §10 边界声明：本任务不冒充真实 OO probe / evidence
# ════════════════════════════════════════════════════════════════════════════

OO_SCOPE_BOUNDARY: Final[Mapping[str, Any]] = {
    "statement": "本门只做代码 / 数据库独立回归。**不**启动 OnlyOffice、**不**打开文档、"
                 "**不**运行任何 required scenario、**不**写 test run / evidence scenario 行、"
                 "**不**声称任何 scenario 通过。",
    "owner_of_real_oo_scenarios": "70",
    "forbidden_claims": [
        "scenario_passed",
        "evidence_refreshed",
        "oo_probe_executed",
        "required_scenarios_green",
    ],
    "evidence_tables_left_untouched": [
        "working_paper_sync_test_run",
        "working_paper_entry_evidence_scenario",
    ],
    "why": "正文逐字「本任务只做代码/数据库独立回归，不冒充真实 OO probe/evidence已通过」。"
           "scratch schema 里也不写这两张表 —— 写了就等于在报告里制造「有 evidence」的表象。",
}


# ════════════════════════════════════════════════════════════════════════════
# §11 48 条 Property 的落点（三档，档位由事实派生而非手填）
# ════════════════════════════════════════════════════════════════════════════

#: 第三档（既未被本门重新表达、也未在辐射面里被点名）的 property 必须在这里登记 owner，
#: 否则判结构错误。
#:
#: 🔴 实测**为空**：48 条里 24 条被本门重新表达、24 条在辐射面文件里被显式点名且由本门真跑。
#: 这里刻意不预填条目 —— 预填就是 additive 注入的死代码（本 spec 假绿第①源）。该分支的
#: 有效性由守卫喂合成输入证明（`property_landings` 是纯函数，可直接构造一条无落点的 property）。
DEFERRED_PROPERTIES: Final[Mapping[int, Mapping[str, str]]] = {}

_PROPERTY_ANNOTATION_CACHE: dict[str, dict[int, list[str]]] = {}


def property_annotations(surface: Mapping[str, Any]) -> dict[int, list[str]]:
    """在辐射面文件里现算「哪条 Property 被哪些文件显式点名」。

    判据是**显式标注**（`Property N` 带词边界 / `property_N_`），不是「随便提了个数字」。
    """
    key = str(surface["digest"])
    if key in _PROPERTY_ANNOTATION_CACHE:
        return _PROPERTY_ANNOTATION_CACHE[key]
    patterns = {
        number: re.compile(rf"(?:Property\s+{number}\b|property_{number}_|P{number}\b)")
        for number in DECLARED_PROPERTIES
    }
    found: dict[int, list[str]] = {number: [] for number in DECLARED_PROPERTIES}
    for path_str in surface["files"]:
        text = (REPO / path_str).read_text(encoding="utf-8", errors="replace")
        for number, pattern in patterns.items():
            if pattern.search(text):
                found[number].append(path_str)
    _PROPERTY_ANNOTATION_CACHE[key] = found
    return found


def build_property_landings(
    invariant_rows: Sequence[Mapping[str, Any]],
    endpoint_rows: Sequence[Mapping[str, Any]],
    surface: Mapping[str, Any],
    suite: Mapping[str, Any],
) -> dict[str, Any]:
    """逐条 Property 的落点。档位从事实派生：谁在哪一层被验，直接查得到。"""
    expressed: dict[int, list[str]] = {number: [] for number in DECLARED_PROPERTIES}
    for row in list(invariant_rows) + list(endpoint_rows):
        for label in row.get("properties") or ():
            number = int(str(label).split()[-1])
            if number in expressed:
                expressed[number].append(str(row["check_id"]))
    annotations = property_annotations(surface)
    suite_executed = suite.get("state") == "executed"

    rows: list[dict[str, Any]] = []
    tiers: dict[str, int] = {"independently_expressed": 0, "independently_executed": 0,
                             "deferred": 0}
    structural_errors: list[dict[str, Any]] = []
    for number in DECLARED_PROPERTIES:
        checks = sorted(set(expressed[number]))
        files = annotations[number]
        if checks:
            tier = "independently_expressed"
            owner = OWNER_TASK
            detail = {"checks": checks, "annotated_in_surface_files": len(files)}
        elif files and suite_executed:
            tier = "independently_executed"
            owner = OWNER_TASK
            detail = {
                "checks": [],
                "annotated_in_surface_files": len(files),
                "sample_files": files[:4],
                "caveat": "本门未在独立文件里重新表达这条 Property；独立性只来自「由本门从仓库根"
                          "真跑了这些文件」。比第一档弱，如实标出。",
            }
        else:
            tier = "deferred"
            declared = DEFERRED_PROPERTIES.get(number)
            owner = str((declared or {}).get("owner_task") or "")
            detail = {
                "checks": [],
                "annotated_in_surface_files": len(files),
                "declared_deferral": dict(declared) if declared else None,
            }
            if not declared:
                structural_errors.append(
                    {
                        "kind": "property_without_landing_or_declared_owner",
                        "property": f"Property {number}",
                        "detail": "既没在本门被重新表达，也没在辐射面文件里被点名，且未登记 owner ⇒ "
                                  "正文点名的 48 条里有一条无落点（结构错误，不得静默）",
                        "owner_task": OWNER_TASK,
                    }
                )
        tiers[tier] += 1
        rows.append(
            {
                "property": f"Property {number}",
                "tier": tier,
                "owner_task": owner,
                **detail,
            }
        )
    return {
        "declared_count": len(DECLARED_PROPERTIES),
        "tiers": tiers,
        "tier_semantics": {
            "independently_expressed": "本门在独立文件里重新表达了该不变量（schema 侧 DDL 判据 + "
                                       "行为侧真造行 / 端点 AST / 链路真行），不依赖实现任务的守卫。",
            "independently_executed": "本门未重新表达，但从仓库根真跑了辐射面里显式点名该 Property "
                                      "的测试文件。独立性弱于第一档 —— 如实标出，不冒充。",
            "deferred": "只能由真实 OO（Task 70）/ 真实宿主（Task 69）/ 容量验收（Task 71）给出，"
                        "必须点名 owner。",
        },
        "rows": rows,
        "structural_errors": structural_errors,
    }


# ════════════════════════════════════════════════════════════════════════════
# §12 BP（task-scoped 编号）与最终判定
# ════════════════════════════════════════════════════════════════════════════


def build_blocking_points(
    *,
    invariant_rows: Sequence[Mapping[str, Any]],
    catalog: Mapping[str, Any],
    suite: Mapping[str, Any],
    landings: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """BP 从**输入现算**（教训 11/15：写死的 BP 在事实变化后静静过期）。"""
    points: list[dict[str, Any]] = []

    gap_rows = [
        row
        for row in invariant_rows
        if (row.get("schema_side") or {}).get("declared_gap")
    ]
    for row in gap_rows:
        gap = dict(row["schema_side"]["declared_gap"])
        arm = next(
            (
                a
                for a in (row.get("behaviour_side") or {}).get("arms") or ()
                if a["arm_id"] == "dlv_pre_durable_owner"
            ),
            None,
        )
        accepted = bool(((arm or {}).get("measured") or {}).get("ddl_accepts_pre_durable_owner"))
        points.append(
            {
                "id": gap.get("blocking_point", "BP-68-1"),
                "subject": f"{row['check_id']} / {gap.get('facet')}",
                "statement": "DDL 现测**接受** pre-durable rejected/error 带 owner 的 delivery 行 ⇒ "
                             "这条不变量在 schema 层没有约束力，只由服务层把住。",
                "measured": accepted,
                "measured_how": gap.get("measured"),
                "enforced_by": gap.get("enforced_by"),
                "owner_task": gap.get("owner_task"),
                "independently_confirmed_by": list(gap.get("independently_confirmed_by") or ()),
                "task68_disposition": "reported_not_fixed",
                "why_not_fixed_here": gap.get("why_not_a_defect_of_this_task"),
            }
        )

    empty_tables = sorted(
        table for table, count in (catalog.get("row_counts") or {}).items() if not count
    )
    points.append(
        {
            "id": "BP-68-2",
            "subject": "production_public_schema_row_supply",
            "statement": f"生产 `public` schema 里 {len(empty_tables)} 张相关表实测 0 行 ⇒ 正文点名的"
                         "行为侧不变量在生产数据上**一条都验不了**；本门只能在 scratch schema 造行验。",
            "measured": len(empty_tables),
            "empty_tables": empty_tables,
            "owner_task": "70",
            "task68_disposition": "reported_not_fixed",
            "why_not_fixed_here": "行供给来自 Task 70 的真实场景执行；本门不造 evidence（见 "
                                  "`oo_scope_boundary`）。scratch schema 的结论对 DDL 成立，但"
                                  "**不能**替代生产数据上的验收。",
        }
    )

    preexisting = [r for r in (suite.get("preexisting") or ()) if not r.get("agrees")]
    points.append(
        {
            "id": "BP-68-3",
            "subject": "preexisting_reds_in_radiation_surface",
            "statement": "基线里的 11 failed + 6 errors 全部落在辐射面内，本门如实登记且**不修**。",
            "measured": {
                "declared_failed": suite.get("declared_preexisting_failed"),
                "declared_errors": suite.get("declared_preexisting_errors"),
                "observed_failed": suite.get("observed_failed"),
                "observed_errors": suite.get("observed_errors"),
                "rows_disagreeing": [r.get("file") for r in preexisting],
            },
            "owner_task": "20/30/44/70/73",
            "task68_disposition": "reported_not_fixed",
            "why_not_fixed_here": "修它们会改 source commit，让 Task 70 尚未刷新的 evidence 全部 stale。",
        }
    )

    weaker = [r for r in (landings.get("rows") or ()) if r["tier"] != "independently_expressed"]
    points.append(
        {
            "id": "BP-68-4",
            "subject": "properties_not_re_expressed_independently",
            "statement": f"48 条 Property 中 {len(weaker)} 条本门未在独立文件里重新表达 —— 它们的"
                         "独立性只来自「由本门从仓库根真跑了辐射面」，或已登记转交 owner。",
            "measured": {
                "independently_expressed": landings["tiers"]["independently_expressed"],
                "independently_executed": landings["tiers"]["independently_executed"],
                "deferred": landings["tiers"]["deferred"],
                "weaker_properties": [r["property"] for r in weaker],
            },
            "owner_task": "68/69/70/71",
            "task68_disposition": "reported_not_cleared",
            "why_not_fixed_here": "正文要求「不得由实现任务自证」；本门对能落到 DDL/行/AST 的不变量"
                                  "全部重新表达，对需要真实 OO / 真实宿主 / 压力面的部分如实标弱"
                                  "并点名 owner，而不是把「跑了他们的测试」说成「我独立验过」。",
        }
    )
    for point in points:
        if not BP_ID_RE.fullmatch(str(point["id"])):
            raise Task68GateError(
                f"BP 编号 {point['id']} 不是 task-scoped 形态 —— 全局 `BP-NN` 已被 Tasks "
                "60/61/63/64 重复占用（同号不同义），接回去只会制造第三份冲突"
            )
    return points


def build_verdict(report: Mapping[str, Any]) -> dict[str, Any]:
    """最终判定。`passed` / `failed` / `unverifiable` 三态，理由逐条可查。"""
    catalog = report["schema_catalog"]
    harness = report["behaviour_harness"]
    invariants = report["invariants"]
    endpoints = report["endpoint_checks"]
    suite = report["suite_verdict"]
    restoration = report["restoration"]
    landings = report["properties"]

    blockers: list[str] = []
    if not catalog.get("readable"):
        blockers.append(f"schema_catalog_unreadable: {catalog.get('error')}")
    if harness.get("error"):
        blockers.append(f"behaviour_harness_error: {harness.get('error')}")
    for name, error in (harness.get("probe_errors") or {}).items():
        blockers.append(f"probe_error[{name}]: {error}")

    failed_invariants = [row["check_id"] for row in invariants if not row["passed"]]
    failed_endpoints = [row["check_id"] for row in endpoints if not row["passed"]]
    property_errors = list(landings.get("structural_errors") or ())

    if blockers:
        result = RESULT_UNVERIFIABLE
    elif failed_invariants or failed_endpoints or property_errors or not restoration["restored"]:
        result = RESULT_FAILED
    elif suite.get("state") != "executed" or not suite.get("passed"):
        result = RESULT_FAILED
    else:
        result = RESULT_PASSED

    verified_on_rows = [
        row["check_id"]
        for row in invariants
        if (row.get("behaviour_side") or {}).get("state") == "verified_on_rows"
    ]
    schema_only = [
        row["check_id"]
        for row in invariants
        if (row.get("behaviour_side") or {}).get("state") != "verified_on_rows"
    ]
    return {
        "result": result,
        "blockers": blockers,
        "failed_invariants": failed_invariants,
        "failed_endpoint_checks": failed_endpoints,
        "property_structural_errors": property_errors,
        "restored": restoration["restored"],
        "suite_state": suite.get("state"),
        "suite_passed": suite.get("passed"),
        "invariant_count": len(invariants),
        "verified_on_rows": verified_on_rows,
        "schema_side_only": schema_only,
        "honest_scope": {
            "really_verified_on_rows": len(verified_on_rows),
            "schema_side_only": len(schema_only),
            "production_rows_available": sum(
                1 for count in (catalog.get("row_counts") or {}).values() if count
            ),
            "note": "所有行为侧结论都来自 **scratch schema** 的真行；生产 `public` schema 的相关表"
                    "实测 0 行（见 BP-68-2），因此「行上验过」= DDL 与约束在真库上确实会报错，"
                    "**不等于**生产数据已被验收。生产数据侧验收归 Task 70。",
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# §13 报告组装
# ════════════════════════════════════════════════════════════════════════════


def task_body(task_number: int = TASK_NUMBER) -> str:
    """现读 tasks.md 里本任务的正文（守卫据此双向锁死声明的 Property / Requirement）。"""
    text = TASKS_MD.read_text(encoding="utf-8")
    lines = text.split("\n")
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(rf"^\s*-\s\[[ x~\-]\]\s+{task_number}\.", line)
        ),
        None,
    )
    if start is None:
        raise Task68GateError(f"tasks.md 里找不到 Task {task_number}")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if re.match(r"^\s*-\s\[[ x~\-]\]\s+\d+\.", lines[index])
            or lines[index].startswith("### ")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def task_declarations() -> dict[str, Any]:
    body = task_body()
    properties = sorted({int(m) for m in re.findall(r"Property (\d+)", body)})
    req_line = next(
        (line for line in body.split("\n") if "_Requirements:" in line), ""
    )
    requirements = re.findall(r"\d+\.\d+", req_line)
    return {
        "properties_in_task_text": properties,
        "requirements_in_task_text": requirements,
        "declared_properties": list(DECLARED_PROPERTIES),
        "properties_match": properties == sorted(DECLARED_PROPERTIES),
        "requirement_count": len(requirements),
        "sub_bullet_count": len(SUB_BULLETS),
        "body_digest": sha256_text(body),
    }


def design_property_titles() -> dict[str, str]:
    """design.md 里每条 Property 的标题。

    🔴 正文可能紧跟在 `### Property N` 同一行（实测 Property 4 就是），只取「下一行」会
    拿到空串 —— 那样「标题非空」这条判据就变成了对 Markdown 排版的偶然依赖。
    """
    text = DESIGN_MD.read_text(encoding="utf-8")
    titles: dict[str, str] = {}
    for match in re.finditer(r"### Property (\d+)[ \t:.、]*([^\n]*)\n([^\n]*)", text):
        inline = match.group(2).strip()
        following = match.group(3).strip()
        titles[match.group(1)] = (inline or following)[:200]
    return titles


def upstream_inputs() -> dict[str, Any]:
    """Tasks 66/67 的产物是**只读输入**。逐字节记录，不重跑、不改。"""
    rows: dict[str, Any] = {}
    for label, path in (
        ("task67_structural_report", TASK67_REPORT_PATH),
        ("task66_deletion_plan", TASK66_PLAN_PATH),
        ("migration_paradigm", PARADIGM_PATH),
    ):
        if not path.exists():
            rows[label] = {"path": rel(path), "present": False}
            continue
        raw = path.read_bytes()
        rows[label] = {
            "path": rel(path),
            "present": True,
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "disposition": "read_only_input",
        }
    if rows.get("task67_structural_report", {}).get("present"):
        record = read_json(TASK67_REPORT_PATH)
        counters = record.get("counters") or {}
        rows["task67_structural_report"]["consumed"] = {
            "schema_version": record.get("schema_version"),
            "verdict": (record.get("verdict") or {}).get("result")
            if isinstance(record.get("verdict"), dict)
            else record.get("verdict"),
            "counter_keys": sorted(counters) if isinstance(counters, dict) else None,
        }
    return rows


def build_report(
    *,
    catalog: SchemaCatalog | None = None,
    harness: Mapping[str, Any] | None = None,
    suite: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """组装报告。三个昂贵输入可注入 —— 守卫据此**正向重算**（教训 15）。"""
    catalog = catalog if catalog is not None else read_schema_catalog()
    harness = harness if harness is not None else run_behaviour_harness()
    observations = dict(harness.get("observations") or {})
    observations["__harness__"] = {
        "error": harness.get("error"),
        "schema": harness.get("schema"),
    }

    invariant_rows = [inv.evaluate(catalog, observations) for inv in ALL_INVARIANTS]
    endpoint_rows = build_endpoint_checks()
    surface = radiation_surface()
    suite_row = evaluate_suite_run(suite, surface)
    landings = build_property_landings(invariant_rows, endpoint_rows, surface, suite_row)
    restoration = restoration_record(harness)

    report: dict[str, Any] = {
        "task": f"Task {TASK_NUMBER}",
        "spec": SPEC,
        "wave": 7,
        "schema_version": SCHEMA_VERSION,
        "owner_task": OWNER_TASK,
        "generated_by": rel(Path(__file__)),
        "source_commit": git_head(),
        "why_this_task_is_independent": {
            "task_text": "不得由实现任务自证",
            "how": [
                "schema 侧走 `pg_get_constraintdef` / `pg_get_indexdef` / `pg_get_triggerdef` / "
                "`pg_get_functiondef`（上游 structural pre-reconcile 走的是另一组系统视图）"
                "—— 独立复核同一批约束",
                "行为侧在 scratch schema 里用**裸 SQL** 造行，不经任何实现任务的服务代码；"
                "非法形态必须被它自己声明的那条约束拒绝，且各臂拒绝理由互不命中",
                "端点侧走 router / endpoint_guard 的 AST 顺序判据，不 import 实现任务的守卫",
                "辐射面按引用关系现算并由本门从仓库根真跑",
            ],
            "what_is_not_claimed": "对未能重新表达的 Property，报告标为第二/第三档并点名 owner，"
                                   "不把「跑了实现任务的测试」说成「我独立验过」",
        },
        "sub_bullets": {str(k): v for k, v in SUB_BULLETS.items()},
        "task_declarations": task_declarations(),
        "design_property_titles": design_property_titles(),
        "upstream_inputs": upstream_inputs(),
        "schema_catalog": catalog.as_record(),
        "behaviour_harness": {
            # 每轮都变的值（scratch schema 的随机 hex、墙钟耗时）**不入报告** ——
            # 否则 `--check` 的逐字节锁永远对不上，锁就等于不存在。
            "schema_prefix": _SCHEMA_PREFIX,
            "schema_is_ephemeral": True,
            "migrations": harness.get("migrations"),
            "error": harness.get("error"),
            "apply_errors": harness.get("apply_errors"),
            "probe_errors": harness.get("probe_errors"),
            "probe_count": len(BEHAVIOUR_PROBES),
            "observation_count": len(harness.get("observations") or {}),
            "observations": dict(sorted((harness.get("observations") or {}).items())),
        },
        "invariants": invariant_rows,
        "invariant_counts": {
            "total": len(invariant_rows),
            "by_sub_bullet": {
                str(bullet): sum(1 for row in invariant_rows if row["sub_bullet"] == bullet)
                for bullet in sorted({row["sub_bullet"] for row in invariant_rows})
            },
            "passed": sum(1 for row in invariant_rows if row["passed"]),
            "verified_on_rows": sum(
                1
                for row in invariant_rows
                if (row.get("behaviour_side") or {}).get("state") == "verified_on_rows"
            ),
            "arm_total": sum(
                len((row.get("behaviour_side") or {}).get("arms") or ()) for row in invariant_rows
            ),
        },
        "endpoint_checks": endpoint_rows,
        "radiation_surface": surface,
        "suite_run": dict(suite) if suite else None,
        "suite_verdict": suite_row,
        "oo_scope_boundary": dict(OO_SCOPE_BOUNDARY),
        "properties": landings,
        "restoration": restoration,
    }
    report["blocking_points"] = build_blocking_points(
        invariant_rows=invariant_rows,
        catalog=report["schema_catalog"],
        suite=suite_row,
        landings=landings,
    )
    report["verdict"] = build_verdict(report)
    report["report_digest"] = digest_of(
        {key: value for key, value in report.items() if key != "report_digest"}
    )
    return report


def render(report: Mapping[str, Any]) -> str:
    return stable_json(report, indent=2) + "\n"


# ════════════════════════════════════════════════════════════════════════════
# §14 CLI
# ════════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task 68 后端全链独立回归门")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="现算并与磁盘逐字节比对")
    mode.add_argument("--write", action="store_true", help="现算并写盘")
    parser.add_argument(
        "--run-suites",
        action="store_true",
        help="另跑辐射面全量 pytest（十余分钟）并把真实执行结果写进报告；只在 --write 下有效",
    )
    args = parser.parse_args(argv)

    suite: Mapping[str, Any] | None = None
    if args.run_suites:
        if not args.write:
            print("[Task68] --run-suites 只能与 --write 同用", file=sys.stderr)
            return 2
        suite = run_radiation_suites(radiation_surface())
    elif OUTPUT_PATH.exists():
        # `suite_run` 是**昂贵的真实执行记录**：复用磁盘上的那一份，但辐射面清单会现算并
        # 逐项核对（`surface_digest_matches`），改 scanner 蒙不过去。
        existing = read_json(OUTPUT_PATH)
        suite = existing.get("suite_run")

    report = build_report(suite=suite)
    rendered = render(report)
    verdict = report["verdict"]["result"]

    if args.write:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUTPUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(rendered, encoding="utf-8")
        os.replace(tmp, OUTPUT_PATH)
        print(f"[Task68] 已写入 {rel(OUTPUT_PATH)} · verdict={verdict}")
    else:
        if not OUTPUT_PATH.exists():
            print(f"[Task68] 缺少 {rel(OUTPUT_PATH)}，先跑 --write", file=sys.stderr)
            return 2
        on_disk = OUTPUT_PATH.read_text(encoding="utf-8")
        if on_disk != rendered:
            print(
                f"[Task68] 现算结果与 {rel(OUTPUT_PATH)} 不一致 —— 报告已过期或被手改",
                file=sys.stderr,
            )
            return 1
        print(f"[Task68] --check 通过 · verdict={verdict}")

    if verdict == RESULT_PASSED:
        return 0
    print(f"[Task68] verdict={verdict} · blockers={report['verdict']['blockers'][:3]}",
          file=sys.stderr)
    return 1 if verdict == RESULT_FAILED else 3


if __name__ == "__main__":
    raise SystemExit(main())
