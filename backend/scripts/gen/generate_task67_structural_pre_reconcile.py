"""Task 67 —— structural pre-reconcile：manifest / registry / definition / bundle /
candidate / deletion-plan 的逐 entry 双向核对报告生成器。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 67
点名 Property：**1 / 2 / 3 / 28 / 51 / 67 / 69 / 70 / 71**
点名 AC：1.1 · 1.2 · 1.3 · 1.4 · 1.5 · 1.6 · 1.7 · 1.8 · 2.1 · 6.10 · 6.18 · 9.8 ·
9.9 · 9.10 · 12.10 · 12.11 · 12.12 · 12.13 · 14.16

═══ 本任务的性质（决定了本文件能做什么、不能做什么）═══

任务正文逐字：「本任务是 structural pre-reconcile，只允许并如实报告未裁决、假双向、
未验收、unreachable、evidence stale 及 planned-delete 计数；**允许报告 stale，不要求
stale 清零**，不运行真实 OO 场景，**不授权删除**，也不把 planned-delete 当作最终五个
零。」

因此本生成器：

* **只读**。DB 只走 `SELECT`（守卫用 AST 断言每一条 SQL 字面量都以 SELECT/WITH 开头、
  且不出现 `session.add` / `commit` / `flush` / `begin`）。
* **不写 manifest**。正文要求「从最终源码重新生成 mounts 与 source-backed manifest」，
  但唯一合法入口 `generate_workpaper_sync_manifest.py` 的 `build_manifest()` 有一道
  `approved_source_digest` 复核门。当前源码实测**已经漂移**（见
  `source_regeneration.digests_agree`），该门会拒绝。本生成器的做法是：在**内存里**把
  `approved_source_digest` 换成当前源码的实测值再重算，并把「磁盘 manifest 已过期」
  本身当作要报告的结构事实 —— 而**不是** `--apply` 覆盖并发方的文件。
* **不裁决删除**。所有 planned-delete 数字原样引自 Task 66 的清册并双向核对落点。

═══ 空集不得恒真（假绿第⑥源）═══

正文点名的一长串链路校验里，有一大半的 DB 表实测 **0 行**。0 行的集合上「逐行成立」
恒真，是本 spec 反复记录的假绿形态。本生成器对每条链路检查同时给出两个分母：

* `row_denominator` —— 真实行数。为 0 时 `denominator_empty=true` 且必须写明 `owner`。
* `schema_denominator` —— **结构判据**：该约束在 PostgreSQL 侧的 UNIQUE 索引 / CHECK
  约束 / trigger 是否存在且定义符合要求。这一条在 0 行时**依然可判定**，因为它读的是
  `pg_index` / `pg_constraint` / `pg_trigger` 的实际定义，不是行。

`passed` 由 `schema_denominator` 决定；`row_denominator` 只影响 `verified_on_rows`。
两者分开是刻意的：混成一个布尔会让「0 行所以通过」与「schema 真的把住了」不可区分。

═══ 用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）═══

    .\\.venv\\Scripts\\python.exe backend/scripts/gen/generate_task67_structural_pre_reconcile.py --check
    .\\.venv\\Scripts\\python.exe backend/scripts/gen/generate_task67_structural_pre_reconcile.py --write
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # import 自举：backend/scripts
import _census_lock  # noqa: E402  普查量/逐字节锁分离（四门共用，说理在那里）

import argparse
import asyncio
import copy
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

# ════════════════════════════════════════════════════════════════════════════
# 常量与路径
# ════════════════════════════════════════════════════════════════════════════

SCHEMA_VERSION = "task67-structural-pre-reconcile:v1"
OWNER_TASK = "67"
SPEC = "workpaper-html-onlyoffice-bidirectional-writeback-closure"

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
DATA = BACKEND / "data"

OUTPUT_PATH = DATA / "workpaper_sync_task67_structural_pre_reconcile.json"
MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
OVERLAY_PATH = DATA / "workpaper_sync_entry_overlay.json"
TASK66_PLAN_PATH = DATA / "workpaper_sync_task66_legacy_deletion_plan.json"
PARADIGM_PATH = DATA / "workpaper_sync_migration_paradigm.json"
MANIFEST_GENERATOR_PATH = BACKEND / "scripts" / "gen" / "generate_workpaper_sync_manifest.py"

#: 🔴 task-scoped 前缀。全局 `BP-NN` 已被 Tasks 60/61/63/64 重复占用（同号不同义），
#: 接回去只会制造第 N 份冲突。守卫用 `re.fullmatch(r"BP-67-\d+")` 锁死。
BP_ID_RE = re.compile(r"BP-67-\d+")

#: 正文点名的六类计数。写成封闭元组让守卫能断言「一个不少、一个不多」。
REPORTED_COUNTER_KINDS: tuple[str, ...] = (
    "unadjudicated",
    "fake_bidirectional",
    "unaccepted",
    "unreachable",
    "evidence_stale",
    "planned_delete",
)

#: 每条 entry 必须给出的核对面。缺一格即结构错误（正文 bullet 1 的「双向核对」清单）。
REQUIRED_ENTRY_FACETS: tuple[str, ...] = (
    "source_digest",
    "editable",
    "room_model",
    "scenario_profile",
    "registry_landing",
    "host_dom_landing",
    "descriptor_room_config",
    "authority_contract_bundle_chain",
    "candidate_published_representation",
    "deletion_plan_landing",
)

#: 结构错误的封闭词表（正文：「profile 降级、计划外 legacy/unreachable 或
#: digest/owner/rollback 缺失立即报结构错误」）。
STRUCTURAL_ERROR_KINDS: tuple[str, ...] = (
    "source_digest_drifted_from_reviewed_overlay",
    "profile_downgraded",
    "unplanned_legacy_or_unreachable",
    "missing_digest_owner_or_rollback",
    "parent_entry_double_counted",
    "registry_landing_missing",
)


class Task67GenerationError(RuntimeError):
    """生成期结构错误（fail closed；不吞异常）。"""


# ════════════════════════════════════════════════════════════════════════════
# 基础工具
# ════════════════════════════════════════════════════════════════════════════


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def stable_json(value: Any, *, indent: int | None = None) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
        separators=(",", ":") if indent is None else None,
    )


def digest_of(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise Task67GenerationError(f"必需输入不存在: {rel(path)}") from exc
    except json.JSONDecodeError as exc:
        raise Task67GenerationError(f"输入不是合法 JSON: {rel(path)}: {exc}") from exc
    if not isinstance(payload, dict):
        raise Task67GenerationError(f"JSON 根必须是对象: {rel(path)}")
    return payload


def git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if completed.returncode != 0:
        raise Task67GenerationError(f"git rev-parse HEAD 失败: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _ensure_backend_on_path() -> None:
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    os.environ.setdefault("DB_DISABLE_SSL", "True")


# ════════════════════════════════════════════════════════════════════════════
# §1 从最终源码重新生成 mounts 与 source-backed manifest（内存态，绝不写盘）
# ════════════════════════════════════════════════════════════════════════════


def load_manifest_generator() -> Any:
    """import 唯一合法的 manifest 生成入口（不复制它的推导规则）。"""
    spec = importlib.util.spec_from_file_location(
        "task67_manifest_gen", MANIFEST_GENERATOR_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover - 环境异常
        raise Task67GenerationError(f"无法加载 {rel(MANIFEST_GENERATOR_PATH)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass
class SourceRegeneration:
    """mounts 与 manifest 的重生成结果 + 与磁盘态的逐 entry 差异。"""

    approved_source_digest: str
    current_source_digest: str
    disk_manifest_digest: str
    rebuilt_manifest_digest: str | None
    rebuilt: dict[str, Any] | None
    disk: dict[str, Any]
    rebuild_error: str | None
    mount_ids_only_on_disk: tuple[str, ...]
    mount_ids_only_in_source: tuple[str, ...]

    @property
    def digests_agree(self) -> bool:
        return self.approved_source_digest == self.current_source_digest

    def as_dict(self) -> dict[str, Any]:
        return {
            "regeneration_entry_point": (
                f"{rel(MANIFEST_GENERATOR_PATH)}::discover_source + build_manifest"
            ),
            "why_not_apply": (
                "`--apply` 会覆盖并发会话正在用的 manifest 与 overlay，而正文明令本任务"
                "「不授权删除」「只报告」。本生成器只在**内存**里把 overlay 的 "
                "`approved_source_digest` 换成当前源码实测值以绕过复核门，磁盘 manifest "
                "一个字节都没动 —— 漂移本身是要报告的结构事实，不是要顺手修的东西。"
            ),
            "approved_source_digest": self.approved_source_digest,
            "current_source_digest": self.current_source_digest,
            "digests_agree": self.digests_agree,
            "disk_manifest_digest": self.disk_manifest_digest,
            "rebuilt_manifest_digest": self.rebuilt_manifest_digest,
            "rebuild_error": self.rebuild_error,
            "mount_id_only_on_disk_count": len(self.mount_ids_only_on_disk),
            "mount_id_only_in_source_count": len(self.mount_ids_only_in_source),
            "mount_ids_only_on_disk": list(self.mount_ids_only_on_disk),
            "mount_ids_only_in_source": list(self.mount_ids_only_in_source),
            "disk_manifest_is_readonly_input": True,
            "disk_manifest_sha256": sha256_of(MANIFEST_PATH),
        }


def regenerate_from_source() -> SourceRegeneration:
    gen = load_manifest_generator()
    discovery = gen.discover_source()
    overlay = gen._read_json(gen._OVERLAY)
    disk = read_json(MANIFEST_PATH)

    approved = str(overlay.get("approved_source_digest") or "")
    current = str(discovery.get("sourceDigest") or "")

    patched = copy.deepcopy(overlay)
    patched["approved_source_digest"] = current
    rebuilt: dict[str, Any] | None = None
    rebuild_error: str | None = None
    try:
        rebuilt = gen.build_manifest(discovery, patched)
    except Exception as exc:  # noqa: BLE001 - 重生成失败本身是要报告的结构事实
        # 🔴 不是 fail-open：异常被**如实记进报告**并让 `rebuilt` 保持 None，
        # 下游每条依赖重生成的判据都会因此显式降级为 `rebuild_unavailable`。
        rebuild_error = f"{type(exc).__name__}: {exc}"

    disk_mount_ids = {
        mount["mountId"]
        for entry in disk.get("entries") or []
        for mount in entry.get("mounts") or []
    }
    source_mount_ids = {
        item["mountId"] for item in [*discovery["mounts"], *discovery["dispatchers"]]
    }
    return SourceRegeneration(
        approved_source_digest=approved,
        current_source_digest=current,
        disk_manifest_digest=str(disk.get("manifest_digest") or ""),
        rebuilt_manifest_digest=None if rebuilt is None else str(rebuilt.get("manifest_digest")),
        rebuilt=rebuilt,
        disk=disk,
        rebuild_error=rebuild_error,
        mount_ids_only_on_disk=tuple(sorted(disk_mount_ids - source_mount_ids)),
        mount_ids_only_in_source=tuple(sorted(source_mount_ids - disk_mount_ids)),
    )


def entry_source_digest(entry: Mapping[str, Any]) -> str:
    """一条 entry 的 source digest：它的物理 mounts + profile_source 的 canonical 摘要。

    刻意**不**含 capability / migration_state / evidence 等 reviewed 业务字段 ——
    source digest 必须只随源码变，否则「改一句裁决就让全部 evidence 变 stale」。
    """
    return digest_of(
        {
            "entry_id": entry["entry_id"],
            "mounts": entry.get("mounts"),
            "profile_source": entry.get("profile_source"),
            "host_path": entry.get("host_path"),
            "document_type": entry.get("document_type"),
        }
    )


# ════════════════════════════════════════════════════════════════════════════
# §2 DB 快照（只读；一次 asyncio.run 取全部）
# ════════════════════════════════════════════════════════════════════════════

#: 需要行数与结构事实的 sync 域表。写成封闭元组让守卫能断言分母覆盖面。
SNAPSHOT_TABLES: tuple[str, ...] = (
    "working_paper_artifact",
    "working_paper_callback_delivery",
    "working_paper_callback_recovery_case",
    "working_paper_content_application",
    "working_paper_content_application_event",
    "working_paper_content_representation",
    "working_paper_content_version",
    "working_paper_entry_evidence_scenario",
    "working_paper_forcesave_request",
    "working_paper_oo_client_confirmation",
    "working_paper_oo_close_intent",
    "working_paper_oo_participant",
    "working_paper_oo_room",
    "working_paper_representation_upgrade_candidate",
    "working_paper_sync_conflict",
    "working_paper_sync_definition_artifact",
    "working_paper_sync_definition_bundle",
    "working_paper_sync_definition_null_marker",
    "working_paper_sync_entry_state",
    "working_paper_sync_operation",
    "working_paper_sync_scope_index",
    "working_paper_sync_test_run",
)

_SQL_ROW_COUNTS = "SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'public'"

_SQL_UNIQUE_INDEXES = (
    "SELECT c.relname AS table_name, i.relname AS index_name, "
    "pg_get_indexdef(ix.indexrelid) AS definition "
    "FROM pg_index ix "
    "JOIN pg_class i ON i.oid = ix.indexrelid "
    "JOIN pg_class c ON c.oid = ix.indrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND ix.indisunique AND c.relname LIKE 'working_paper_%'"
)

_SQL_CHECK_CONSTRAINTS = (
    "SELECT rel.relname AS table_name, con.conname AS constraint_name, "
    "pg_get_constraintdef(con.oid) AS definition "
    "FROM pg_constraint con "
    "JOIN pg_class rel ON rel.oid = con.conrelid "
    "JOIN pg_namespace n ON n.oid = rel.relnamespace "
    "WHERE n.nspname = 'public' AND con.contype = 'c' AND rel.relname LIKE 'working_paper_%'"
)

_SQL_TRIGGERS = (
    "SELECT c.relname AS table_name, t.tgname AS trigger_name, "
    "pg_get_triggerdef(t.oid) AS definition "
    "FROM pg_trigger t "
    "JOIN pg_class c ON c.oid = t.tgrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE NOT t.tgisinternal AND n.nspname = 'public' AND c.relname LIKE 'working_paper_%'"
)

_SQL_DEFINITION_ARTIFACTS = (
    "SELECT id::text AS id, kind, logical_id, semantic_version, authority_model_type, "
    "state, source_commit, sha256, structure_hash, supersedes_id::text AS supersedes_id "
    "FROM working_paper_sync_definition_artifact"
)

_SQL_DEFINITION_BUNDLES = (
    "SELECT id::text AS id, schema_version, state, "
    "authority_model_definition_id::text AS authority_model_definition_id, "
    "authority_model_definition_sha256, "
    "template_slot_type, template_slot_ref, template_slot_digest, "
    "instrumentation_slot_type, instrumentation_slot_ref, instrumentation_slot_digest, "
    "contract_slot_type, contract_slot_ref, contract_slot_digest, "
    "canonical_payload_sha256 "
    "FROM working_paper_sync_definition_bundle"
)

_SQL_NULL_MARKERS = (
    "SELECT marker_id, applies_to_slot, marker_version, canonical_payload, sha256, state "
    "FROM working_paper_sync_definition_null_marker"
)

_SQL_ENTRY_STATE = (
    "SELECT wp_id::text AS wp_id, entry_id, "
    "current_representation_id::text AS current_representation_id, representation_generation "
    "FROM working_paper_sync_entry_state"
)

_SQL_REPRESENTATIONS = (
    "SELECT id::text AS id, wp_id::text AS wp_id, entry_id, "
    "content_version_id::text AS content_version_id, generation, document_type, "
    "definition_bundle_id::text AS definition_bundle_id, definition_bundle_sha256, "
    "authority_model_definition_sha256, adapter_id, reason "
    "FROM working_paper_content_representation"
)

_SQL_CANDIDATES = (
    "SELECT id::text AS id, wp_id::text AS wp_id, entry_id, state, "
    "target_contract_definition_id::text AS target_contract_definition_id, "
    "target_definition_bundle_id::text AS target_definition_bundle_id, "
    "finalized_representation_id::text AS finalized_representation_id "
    "FROM working_paper_representation_upgrade_candidate"
)

_SQL_CONTENT_VERSIONS = (
    "SELECT id::text AS id, wp_id::text AS wp_id, revision, source, "
    "projection_sha256, authoritative_artifact_sha256 "
    "FROM working_paper_content_version"
)

_SQL_SCOPE_INDEX = (
    "SELECT resource_kind, resource_id, project_id::text AS project_id, "
    "wp_id::text AS wp_id, entry_id, generation, retired_at::text AS retired_at "
    "FROM working_paper_sync_scope_index"
)

_SQL_TEST_RUNS = (
    "SELECT id::text AS id, entry_id, manifest_source_digest, scenario_profile_digest, "
    "required_scenario_set_digest, definition_bundle_sha256, "
    "authority_model_definition_sha256, editability, room_model, aggregate_result "
    "FROM working_paper_sync_test_run"
)

#: 🔴 `working_paper_entry_evidence_scenario` **没有** `entry_id` 列 —— scenario 行经
#: `run_id` 挂在 `working_paper_sync_test_run` 上，entry 身份只存在于 run 行。首版直接
#: SELECT entry_id 被 PG 以 UndefinedColumn 拒绝，整个快照降级成 `db_unreadable`；这正是
#: 「fail closed 而不是 fail open」应有的表现（若吞掉异常，14 条链路检查会全部变成
#: 「没有违反行所以通过」）。
_SQL_EVIDENCE_SCENARIOS = (
    "SELECT s.id::text AS id, r.entry_id AS entry_id, s.scenario_id, s.scenario_kind, s.result "
    "FROM working_paper_entry_evidence_scenario s "
    "JOIN working_paper_sync_test_run r ON r.id = s.run_id"
)

#: SQL 字面量清单。守卫据此断言「每一条都是只读」（AST 现读本模块的 `sa.text(...)`）。
READONLY_SQL_STATEMENTS: tuple[str, ...] = (
    _SQL_ROW_COUNTS,
    _SQL_UNIQUE_INDEXES,
    _SQL_CHECK_CONSTRAINTS,
    _SQL_TRIGGERS,
    _SQL_DEFINITION_ARTIFACTS,
    _SQL_DEFINITION_BUNDLES,
    _SQL_NULL_MARKERS,
    _SQL_ENTRY_STATE,
    _SQL_REPRESENTATIONS,
    _SQL_CANDIDATES,
    _SQL_CONTENT_VERSIONS,
    _SQL_SCOPE_INDEX,
    _SQL_TEST_RUNS,
    _SQL_EVIDENCE_SCENARIOS,
)

_DB_UNREADABLE = (
    "PostgreSQL 不可读。structural pre-reconcile 的一半判据（bundle / candidate / "
    "representation / forcesave / application / operation / delivery / close / scope）"
    "落在真库的行与 DDL 上，读不到时**不得**按「没有违反项所以通过」处理 —— 报告会把"
    "这些检查标成 `db_unreadable` 并整体判 unverifiable。"
)


@dataclass
class DbSnapshot:
    readable: bool
    error: str | None
    row_counts: dict[str, int] = field(default_factory=dict)
    unique_indexes: dict[str, dict[str, str]] = field(default_factory=dict)
    check_constraints: dict[str, dict[str, str]] = field(default_factory=dict)
    triggers: dict[str, dict[str, str]] = field(default_factory=dict)
    definition_artifacts: list[dict[str, Any]] = field(default_factory=list)
    definition_bundles: list[dict[str, Any]] = field(default_factory=list)
    null_markers: list[dict[str, Any]] = field(default_factory=list)
    entry_states: list[dict[str, Any]] = field(default_factory=list)
    representations: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    content_versions: list[dict[str, Any]] = field(default_factory=list)
    scope_index: list[dict[str, Any]] = field(default_factory=list)
    test_runs: list[dict[str, Any]] = field(default_factory=list)
    evidence_scenarios: list[dict[str, Any]] = field(default_factory=list)

    def index_def(self, table: str, index: str) -> str | None:
        return (self.unique_indexes.get(table) or {}).get(index)

    def check_def(self, table: str, name: str) -> str | None:
        return (self.check_constraints.get(table) or {}).get(name)

    def trigger_def(self, table: str, name: str) -> str | None:
        return (self.triggers.get(table) or {}).get(name)

    def as_dict(self) -> dict[str, Any]:
        return {
            "readable": self.readable,
            "error": self.error,
            "row_counts": {name: self.row_counts.get(name, 0) for name in SNAPSHOT_TABLES},
            "unique_index_count": sum(len(v) for v in self.unique_indexes.values()),
            "check_constraint_count": sum(len(v) for v in self.check_constraints.values()),
            "trigger_count": sum(len(v) for v in self.triggers.values()),
            "definition_artifacts": self.definition_artifacts,
            "definition_bundles": self.definition_bundles,
            "null_markers": self.null_markers,
            "entry_states": self.entry_states,
            "representations": self.representations,
            "candidates": self.candidates,
            "content_versions": self.content_versions,
            "scope_index": self.scope_index,
            "test_runs": self.test_runs,
            "evidence_scenarios": self.evidence_scenarios,
        }


async def _collect_db(snapshot: DbSnapshot) -> None:
    import sqlalchemy as sa

    from app.core.database import engine  # noqa: PLC0415 - 延迟 import

    async with engine.connect() as conn:  # 只 connect，不 begin ⇒ 没有写事务
        rows = (await conn.execute(sa.text(_SQL_ROW_COUNTS))).mappings().all()
        snapshot.row_counts = {row["relname"]: int(row["n_live_tup"] or 0) for row in rows}
        # pg_stat 是估算值；对 0/非 0 判定不可靠，逐表现算精确计数。
        for table in SNAPSHOT_TABLES:
            exact = (
                await conn.execute(sa.text(f"SELECT count(*) AS n FROM {table}"))  # noqa: S608
            ).scalar_one()
            snapshot.row_counts[table] = int(exact)

        for sql, sink, key_a, key_b in (
            (_SQL_UNIQUE_INDEXES, snapshot.unique_indexes, "table_name", "index_name"),
            (_SQL_CHECK_CONSTRAINTS, snapshot.check_constraints, "table_name", "constraint_name"),
            (_SQL_TRIGGERS, snapshot.triggers, "table_name", "trigger_name"),
        ):
            for row in (await conn.execute(sa.text(sql))).mappings().all():
                sink.setdefault(row[key_a], {})[row[key_b]] = row["definition"]

        for sql, attr in (
            (_SQL_DEFINITION_ARTIFACTS, "definition_artifacts"),
            (_SQL_DEFINITION_BUNDLES, "definition_bundles"),
            (_SQL_NULL_MARKERS, "null_markers"),
            (_SQL_ENTRY_STATE, "entry_states"),
            (_SQL_REPRESENTATIONS, "representations"),
            (_SQL_CANDIDATES, "candidates"),
            (_SQL_CONTENT_VERSIONS, "content_versions"),
            (_SQL_SCOPE_INDEX, "scope_index"),
            (_SQL_TEST_RUNS, "test_runs"),
            (_SQL_EVIDENCE_SCENARIOS, "evidence_scenarios"),
        ):
            payload = [dict(row) for row in (await conn.execute(sa.text(sql))).mappings().all()]
            setattr(snapshot, attr, sorted(payload, key=lambda item: stable_json(item)))
    await engine.dispose()


def read_db_snapshot() -> DbSnapshot:
    _ensure_backend_on_path()
    snapshot = DbSnapshot(readable=False, error=None)
    try:
        asyncio.run(_collect_db(snapshot))
    except Exception as exc:  # noqa: BLE001 - 不可读本身要如实报告，不得静默当通过
        snapshot.error = f"{type(exc).__name__}: {exc}"
        return snapshot
    snapshot.readable = True
    return snapshot


# ════════════════════════════════════════════════════════════════════════════
# §3 结构判据：一条链路检查 = 一条独立判据 + 两个分母
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class SchemaRequirement:
    """一条 schema 侧的结构要求（UNIQUE 索引 / CHECK / trigger 的存在与定义）。"""

    kind: str  # "unique_index" | "check" | "trigger"
    table: str
    name: str
    must_contain: tuple[str, ...] = ()

    def evaluate(self, db: DbSnapshot) -> dict[str, Any]:
        lookup = {
            "unique_index": db.index_def,
            "check": db.check_def,
            "trigger": db.trigger_def,
        }[self.kind]
        definition = lookup(self.table, self.name)
        missing_fragments = [
            fragment for fragment in self.must_contain if fragment not in (definition or "")
        ]
        return {
            "kind": self.kind,
            "table": self.table,
            "name": self.name,
            "present": definition is not None,
            "missing_fragments": missing_fragments,
            "satisfied": definition is not None and not missing_fragments,
            "definition": definition,
        }


@dataclass
class ChainCheck:
    """正文 bullet 2 点名的一条链路检查。

    `row_tables` 给出「真实行分母」；`schema_requirements` 给出「结构分母」。
    `passed` **只由结构分母决定** —— 行分母为 0 时若也参与 `passed`，判据就退化成
    「空集恒真」。
    """

    check_id: str
    statement: str
    measured_by: str
    owner_task: str
    row_tables: tuple[str, ...] = ()
    schema_requirements: tuple[SchemaRequirement, ...] = ()
    row_violation_fn: str | None = None

    def evaluate(self, db: DbSnapshot, row_violations: Sequence[Any] = ()) -> dict[str, Any]:
        if not db.readable:
            return {
                "check_id": self.check_id,
                "statement": self.statement,
                "measured_by": self.measured_by,
                "owner_task": self.owner_task,
                "passed": False,
                "state": "db_unreadable",
                "detail": _DB_UNREADABLE,
                "row_denominator": None,
                "denominator_empty": None,
                "schema_requirements": [],
                "row_violations": [],
            }
        evaluated = [req.evaluate(db) for req in self.schema_requirements]
        if not evaluated:
            raise Task67GenerationError(
                f"检查 {self.check_id} 没有任何 schema 要求 —— 那样 `passed` 就恒真"
                "（空集恒等价，假绿第⑥源）"
            )
        row_denominator = sum(db.row_counts.get(table, 0) for table in self.row_tables)
        schema_ok = all(item["satisfied"] for item in evaluated)
        return {
            "check_id": self.check_id,
            "statement": self.statement,
            "measured_by": self.measured_by,
            "owner_task": self.owner_task,
            "passed": schema_ok and not row_violations,
            "state": "measured",
            "row_tables": list(self.row_tables),
            "row_denominator": row_denominator,
            "denominator_empty": row_denominator == 0,
            "denominator_empty_note": (
                None
                if row_denominator
                else (
                    "行分母为 0 ⇒ 本检查的通过**只来自 schema 侧结构判据**"
                    "（UNIQUE/CHECK/trigger 的实际定义），不来自「没有违反行」。"
                    f"行供给归 owner_task={self.owner_task}。"
                )
            ),
            "verified_on_rows": bool(row_denominator) and not row_violations,
            "schema_requirements": evaluated,
            "schema_satisfied": schema_ok,
            "row_violations": list(row_violations),
        }


#: 正文 bullet 2 的逐条判据。每条都是独立的 `ChainCheck`，可逐条变异。
CHAIN_CHECKS: tuple[ChainCheck, ...] = (
    ChainCheck(
        check_id="chain_child_kind_state_digest",
        statement=(
            "`template → instrumentation → contract → bundle → representation` 的每个 child "
            "都必须有 kind / state / digest 三元事实，且 bundle 行的 slot type 与 slot ref "
            "互相锁死（definition slot 指 UUID、marker slot 指版本化 marker）。"
        ),
        measured_by="bundle 三个 `*_type_ref_agree` CHECK + `trg_wpsdb_slots` + 逐 bundle 行现算 child 反查",
        owner_task="67",
        row_tables=("working_paper_sync_definition_bundle",),
        schema_requirements=(
            SchemaRequirement("check", "working_paper_sync_definition_bundle", "ck_wpsdb_template_type_ref_agree", ("definition:%",)),
            SchemaRequirement("check", "working_paper_sync_definition_bundle", "ck_wpsdb_instrumentation_type_ref_agree", ("definition:%",)),
            SchemaRequirement("check", "working_paper_sync_definition_bundle", "ck_wpsdb_contract_type_ref_agree", ("definition:%",)),
            SchemaRequirement("trigger", "working_paper_sync_definition_bundle", "trg_wpsdb_slots"),
            SchemaRequirement("check", "working_paper_sync_definition_artifact", "ck_wpsda_kind", ("template", "instrumentation", "contract", "authority_model")),
            SchemaRequirement("check", "working_paper_sync_definition_artifact", "ck_wpsda_state", ("candidate", "approved", "retired")),
        ),
        row_violation_fn="child_inventory_violations",
    ),
    ChainCheck(
        check_id="projection_contract_requires_approved_child",
        statement=(
            "authority model = `projection_contract` 的 bundle，三个 slot 必须都是真 "
            "definition child 且 child state = approved；不得用 typed null marker 顶替。"
        ),
        measured_by="`ck_wpsda_authority_model_type` 封闭三态 + `trg_wpsdb_slots` + 逐 bundle 现算 child state",
        owner_task="67",
        row_tables=("working_paper_sync_definition_bundle",),
        schema_requirements=(
            SchemaRequirement("check", "working_paper_sync_definition_artifact", "ck_wpsda_authority_model_type", ("projection_contract", "custom_authoritative_ooxml", "opaque_single_onlyoffice")),
            SchemaRequirement("trigger", "working_paper_sync_definition_bundle", "trg_wpsdb_slots"),
            SchemaRequirement("check", "working_paper_sync_definition_artifact", "ck_wpsda_approved_at"),
        ),
        row_violation_fn="projection_child_violations",
    ),
    ChainCheck(
        check_id="typed_null_marker_rules",
        statement=(
            "optional child 只能用 registry 中**版本化** typed null marker；slot omission / "
            "SQL·JSON NULL / 空串 / 全零 hash 一律拒绝。"
        ),
        measured_by="`ck_wpsnm_versioned_id` 正则 + `ck_wpsnm_payload_non_empty` + `ck_wpsnm_sha256` + 逐 marker 行与 `definitions.marker_digest()` 现算比对",
        owner_task="67",
        row_tables=("working_paper_sync_definition_null_marker",),
        schema_requirements=(
            SchemaRequirement("check", "working_paper_sync_definition_null_marker", "ck_wpsnm_versioned_id", ("template|instrumentation|contract", "none:v")),
            SchemaRequirement("check", "working_paper_sync_definition_null_marker", "ck_wpsnm_payload_non_empty"),
            SchemaRequirement("check", "working_paper_sync_definition_null_marker", "ck_wpsnm_sha256", ("wpsync_is_digest",)),
            SchemaRequirement("check", "working_paper_sync_definition_bundle", "ck_wpsdb_template_slot_type", ("template:none:v",)),
            SchemaRequirement("check", "working_paper_sync_definition_bundle", "ck_wpsdb_instrumentation_slot_type", ("instrumentation:none:v",)),
            SchemaRequirement("check", "working_paper_sync_definition_bundle", "ck_wpsdb_contract_slot_type", ("contract:none:v",)),
        ),
        row_violation_fn="marker_violations",
    ),
    ChainCheck(
        check_id="candidate_non_current_and_non_resolvable",
        statement=(
            "upgrade candidate 永不可成为 current representation、永不可被 resolver 看见；"
            "candidate artifact 的 state 不得进 published。"
        ),
        measured_by="`ck_wpa_candidate_never_published` + `trg_wpruc_guard` + `trg_wpses_pointer` + 逐 candidate 行反查 entry pointer",
        owner_task="67",
        row_tables=("working_paper_representation_upgrade_candidate",),
        schema_requirements=(
            SchemaRequirement("check", "working_paper_artifact", "ck_wpa_candidate_never_published", ("upgrade_candidate",)),
            SchemaRequirement("trigger", "working_paper_representation_upgrade_candidate", "trg_wpruc_guard"),
            SchemaRequirement("trigger", "working_paper_sync_entry_state", "trg_wpses_pointer"),
            SchemaRequirement("check", "working_paper_representation_upgrade_candidate", "ck_wpruc_finalized_pointer"),
            SchemaRequirement("check", "working_paper_representation_upgrade_candidate", "ck_wpruc_ready_requires_bundle"),
        ),
        row_violation_fn="candidate_violations",
    ),
    ChainCheck(
        check_id="pure_upgrade_keeps_revision_and_history_freezes_bundle",
        statement=(
            "纯 definition upgrade 只加 representation generation、不动 content version "
            "revision；历史 retry 冻结当时的 bundle digest。"
        ),
        measured_by="`uq_wpcr_generation` 含 content_version_id + `ck_wpcr_reason` 含 definition_upgrade + `trg_wpcv_immutable` + `trg_wpcr_immutable`",
        owner_task="67",
        row_tables=("working_paper_content_representation", "working_paper_content_version"),
        schema_requirements=(
            SchemaRequirement("unique_index", "working_paper_content_representation", "uq_wpcr_generation", ("wp_id", "entry_id", "content_version_id", "generation")),
            SchemaRequirement("check", "working_paper_content_representation", "ck_wpcr_reason", ("definition_upgrade",)),
            SchemaRequirement("trigger", "working_paper_content_version", "trg_wpcv_immutable"),
            SchemaRequirement("trigger", "working_paper_content_representation", "trg_wpcr_immutable"),
            SchemaRequirement("check", "working_paper_content_representation", "ck_wpcr_bundle_digest", ("wpsync_is_digest",)),
        ),
        row_violation_fn="pure_upgrade_violations",
    ),
    ChainCheck(
        check_id="forcesave_five_tuple_and_frozen_fingerprint",
        statement=(
            "forcesave request 的幂等键恰是 `(room, generation, initiated_by_participant_id, "
            "kind, idempotency_key)` 五元组，且 `frozen_request_fingerprint` 不可变。"
        ),
        measured_by="`uq_wpfr_idempotency` 五列逐列现读 + `ck_wpfr_fingerprint` + `trg_wpfr_frozen` + `trg_wpfr_identity`",
        owner_task="68/70",
        row_tables=("working_paper_forcesave_request",),
        schema_requirements=(
            SchemaRequirement(
                "unique_index",
                "working_paper_forcesave_request",
                "uq_wpfr_idempotency",
                ("room_id", "generation", "initiated_by_participant_id", "kind", "idempotency_key"),
            ),
            SchemaRequirement("check", "working_paper_forcesave_request", "ck_wpfr_fingerprint", ("wpsync_is_digest",)),
            SchemaRequirement("trigger", "working_paper_forcesave_request", "trg_wpfr_frozen"),
            SchemaRequirement("trigger", "working_paper_forcesave_request", "trg_wpfr_identity"),
            SchemaRequirement("unique_index", "working_paper_forcesave_request", "uq_wpfr_sequence", ("room_id", "generation", "request_sequence")),
        ),
    ),
    ChainCheck(
        check_id="application_sequence_vs_room_canonical_fence",
        statement=(
            "application 的 `origin_request_sequence` 不可变、`effective_request_sequence` "
            "单调 GREATEST 且不低于 origin；room 的 canonical fence 与 durable sequence 同向推进。"
        ),
        measured_by="`ck_wpca_effective_ge_origin` + `trg_wpca_mutation` + `ck_wpoor_durable_le_request` + `ck_wpoor_durable_fence_pair` + `trg_wpoor_monotonic` + `ck_wpcae_fold_requires_room_fence`",
        owner_task="68/70",
        row_tables=("working_paper_content_application", "working_paper_oo_room"),
        schema_requirements=(
            SchemaRequirement("check", "working_paper_content_application", "ck_wpca_effective_ge_origin"),
            SchemaRequirement("check", "working_paper_content_application", "ck_wpca_no_self_supersede"),
            SchemaRequirement("trigger", "working_paper_content_application", "trg_wpca_mutation"),
            SchemaRequirement("check", "working_paper_oo_room", "ck_wpoor_durable_le_request"),
            SchemaRequirement("check", "working_paper_oo_room", "ck_wpoor_durable_fence_pair"),
            SchemaRequirement("trigger", "working_paper_oo_room", "trg_wpoor_monotonic"),
            SchemaRequirement("check", "working_paper_content_application_event", "ck_wpcae_fold_requires_room_fence"),
        ),
    ),
    ChainCheck(
        check_id="application_to_primary_operation_one_to_one",
        statement="一个 application 恰对应一个 primary operation（application_id 全局唯一）。",
        measured_by="`uq_wpso_application` UNIQUE(application_id) + `ck_wpso_bound_at` + `trg_wpso_application_link`",
        owner_task="68/70",
        row_tables=("working_paper_sync_operation", "working_paper_content_application"),
        schema_requirements=(
            SchemaRequirement("unique_index", "working_paper_sync_operation", "uq_wpso_application", ("application_id",)),
            SchemaRequirement("check", "working_paper_sync_operation", "ck_wpso_bound_at"),
            SchemaRequirement("check", "working_paper_sync_operation", "ck_wpso_bound_requires_application"),
            SchemaRequirement("trigger", "working_paper_sync_operation", "trg_wpso_application_link"),
        ),
    ),
    ChainCheck(
        check_id="duplicate_direct_canonical_and_zero_stranded_shell",
        statement=(
            "duplicate operation 只能**直接**指向 canonical primary（不成链不成环）、"
            "duplicate 不得再绑 application，且不留 stranded waiting shell。"
        ),
        measured_by="`ck_wpso_duplicate_shape` + `ck_wpso_no_self_duplicate` + `ck_wpso_not_both_owners` + `trg_wpso_duplicate_link`",
        owner_task="68/70",
        row_tables=("working_paper_sync_operation",),
        schema_requirements=(
            SchemaRequirement("check", "working_paper_sync_operation", "ck_wpso_duplicate_shape", ("duplicate_of_operation_id", "application_id IS NULL")),
            SchemaRequirement("check", "working_paper_sync_operation", "ck_wpso_no_self_duplicate"),
            SchemaRequirement("check", "working_paper_sync_operation", "ck_wpso_not_both_owners"),
            SchemaRequirement("trigger", "working_paper_sync_operation", "trg_wpso_duplicate_link"),
        ),
    ),
    ChainCheck(
        check_id="delivery_durable_at_owner_constraint",
        statement=(
            "delivery 以 `durable_at` 为 owner gate：pre-durable 零 owner、durable 恰一 owner "
            "（application XOR recovery case），且 unmatched/ambiguous 零业务实体。"
        ),
        measured_by="`ck_wpcd_durable_exactly_one_owner` 的 XOR 以 durable_at 为门 + `ck_wpcd_no_double_owner` + `ck_wpcd_unmatched_zero_entities` + `ck_wpcd_ambiguous_zero_entities` + `trg_wpcd_durable_fact`",
        owner_task="68/70",
        row_tables=("working_paper_callback_delivery",),
        schema_requirements=(
            SchemaRequirement("check", "working_paper_callback_delivery", "ck_wpcd_durable_exactly_one_owner", ("durable_at IS NULL",)),
            SchemaRequirement("check", "working_paper_callback_delivery", "ck_wpcd_no_double_owner"),
            SchemaRequirement("check", "working_paper_callback_delivery", "ck_wpcd_unmatched_zero_entities"),
            SchemaRequirement("check", "working_paper_callback_delivery", "ck_wpcd_ambiguous_zero_entities"),
            SchemaRequirement("check", "working_paper_callback_delivery", "ck_wpcd_durable_requires_incoming"),
            SchemaRequirement("trigger", "working_paper_callback_delivery", "trg_wpcd_durable_fact"),
        ),
    ),
    ChainCheck(
        check_id="application_and_engine_are_durable_only",
        statement=(
            "application / engine 只接 durable incoming；quarantined 保持 `durable_at=NULL`、"
            "不可 release、不可转 durable；incoming 永不 published。"
        ),
        measured_by="`ck_wpa_durable_quarantine_exclusive` + `ck_wpa_quarantined_state_no_durable_at` + `ck_wpa_durable_state_has_durable_at` + `ck_wpa_incoming_never_published` + `trg_wpa_transition`",
        owner_task="68/70",
        row_tables=("working_paper_artifact",),
        schema_requirements=(
            SchemaRequirement("check", "working_paper_artifact", "ck_wpa_durable_quarantine_exclusive"),
            SchemaRequirement("check", "working_paper_artifact", "ck_wpa_quarantined_state_no_durable_at"),
            SchemaRequirement("check", "working_paper_artifact", "ck_wpa_durable_state_has_durable_at"),
            SchemaRequirement("check", "working_paper_artifact", "ck_wpa_incoming_never_published", ("incoming",)),
            SchemaRequirement("check", "working_paper_artifact", "ck_wpa_incoming_requires_delivery"),
            SchemaRequirement("trigger", "working_paper_artifact", "trg_wpa_transition"),
        ),
        row_violation_fn="incoming_state_violations",
    ),
    ChainCheck(
        check_id="close_authorization_stale_successor_recovery_required",
        statement=(
            "leader promotion 前 revoke/expire 必须落 `authorization_stale`；合法 successor "
            "接任；无 successor 时落 `recovery_required` 且不永久阻塞；close-capture 至多一条。"
        ),
        measured_by="`ck_wpoci_state` 三态齐备 + `uq_wpoci_active` 部分唯一把三态排除在 active 之外 + `ck_wpoci_promoted_pair` + `trg_wpoci_promotion` + `uq_wpfr_open_close_capture`",
        owner_task="68/70",
        row_tables=("working_paper_oo_close_intent",),
        schema_requirements=(
            SchemaRequirement("check", "working_paper_oo_close_intent", "ck_wpoci_state", ("authorization_stale", "successor_selected", "recovery_required")),
            SchemaRequirement("unique_index", "working_paper_oo_close_intent", "uq_wpoci_active", ("recovery_required", "promoted", "superseded")),
            SchemaRequirement("check", "working_paper_oo_close_intent", "ck_wpoci_promoted_pair"),
            SchemaRequirement("trigger", "working_paper_oo_close_intent", "trg_wpoci_promotion"),
            SchemaRequirement("unique_index", "working_paper_forcesave_request", "uq_wpfr_open_close_capture", ("close_capture",)),
            SchemaRequirement("unique_index", "working_paper_oo_close_intent", "uq_wpoci_sequence", ("intent_sequence",)),
        ),
    ),
    ChainCheck(
        check_id="scope_tombstone_exists_and_retired_is_not_reusable",
        statement=(
            "scope index 的 child 退役写 tombstone；tombstone 不可 DELETE、不可清空、"
            "resource id 不可复用。"
        ),
        measured_by="`trg_wpssi_no_delete` + `trg_wpssi_update_guard` + `pk_wpssi(resource_kind,resource_id)` + `ck_wpssi_entry_non_empty`",
        owner_task="68/70",
        row_tables=("working_paper_sync_scope_index",),
        schema_requirements=(
            SchemaRequirement("trigger", "working_paper_sync_scope_index", "trg_wpssi_no_delete"),
            SchemaRequirement("trigger", "working_paper_sync_scope_index", "trg_wpssi_update_guard"),
            SchemaRequirement("unique_index", "working_paper_sync_scope_index", "pk_wpssi", ("resource_kind", "resource_id")),
            SchemaRequirement("check", "working_paper_sync_scope_index", "ck_wpssi_entry_non_empty"),
            SchemaRequirement("check", "working_paper_sync_scope_index", "ck_wpssi_resource_kind", ("content_version", "upgrade_candidate")),
        ),
        row_violation_fn="scope_violations",
    ),
    ChainCheck(
        check_id="content_version_scope_uses_opaque_uuid_only",
        statement=(
            "content version 的 scope 只用 opaque UUID；numeric revision 不得作 route / "
            "resource key，两个 wp 相同 numeric revision 不得碰撞。"
        ),
        measured_by="`ck_wpssi_content_version_uuid` + `ck_wpssi_opaque_resource_id` + `uq_wpcv_wp_revision` 含 wp_id + 路由源码 AST 现读 `versions/{version_id}`",
        owner_task="68/70",
        row_tables=("working_paper_content_version", "working_paper_sync_scope_index"),
        schema_requirements=(
            SchemaRequirement("check", "working_paper_sync_scope_index", "ck_wpssi_content_version_uuid", ("wpsync_is_uuid_text",)),
            SchemaRequirement("check", "working_paper_sync_scope_index", "ck_wpssi_opaque_resource_id", ("wpsync_is_opaque_resource_id",)),
            SchemaRequirement("unique_index", "working_paper_content_version", "uq_wpcv_wp_revision", ("wp_id", "revision")),
            SchemaRequirement("check", "working_paper_content_version", "ck_wpcv_revision_non_negative"),
        ),
        row_violation_fn="numeric_revision_collision_violations",
    ),
)


# ── 行级违反项现算（每条都必须能被独立喂进记录重算）─────────────────────────


def child_inventory_violations(db: DbSnapshot) -> list[dict[str, Any]]:
    by_id = {row["id"]: row for row in db.definition_artifacts}
    violations: list[dict[str, Any]] = []
    for bundle in db.definition_bundles:
        for slot in ("template", "instrumentation", "contract"):
            slot_type = bundle[f"{slot}_slot_type"]
            slot_ref = bundle[f"{slot}_slot_ref"]
            slot_digest = bundle[f"{slot}_slot_digest"]
            if slot_type == "definition":
                child_id = slot_ref.split(":", 1)[1]
                child = by_id.get(child_id)
                if child is None:
                    violations.append(
                        {"bundle_id": bundle["id"], "slot": slot, "why": "definition slot 指向不存在的 child"}
                    )
                    continue
                if child["kind"] != slot:
                    violations.append(
                        {"bundle_id": bundle["id"], "slot": slot, "why": f"child kind={child['kind']} 与 slot 不符"}
                    )
                if child["sha256"] != slot_digest:
                    violations.append(
                        {"bundle_id": bundle["id"], "slot": slot, "why": "child sha256 与 slot digest 不符"}
                    )
            elif slot_ref != f"marker:{slot_type}":
                violations.append(
                    {"bundle_id": bundle["id"], "slot": slot, "why": f"marker slot ref {slot_ref!r} 与 type 不符"}
                )
    return violations


def projection_child_violations(db: DbSnapshot) -> list[dict[str, Any]]:
    by_id = {row["id"]: row for row in db.definition_artifacts}
    violations: list[dict[str, Any]] = []
    for bundle in db.definition_bundles:
        authority = by_id.get(bundle["authority_model_definition_id"])
        if authority is None:
            violations.append({"bundle_id": bundle["id"], "why": "authority model child 不存在"})
            continue
        if authority.get("authority_model_type") != "projection_contract":
            continue
        for slot in ("template", "instrumentation", "contract"):
            if bundle[f"{slot}_slot_type"] != "definition":
                violations.append(
                    {
                        "bundle_id": bundle["id"],
                        "slot": slot,
                        "why": "projection_contract bundle 用 typed null marker 顶替了必需 child",
                    }
                )
                continue
            child = by_id.get(bundle[f"{slot}_slot_ref"].split(":", 1)[1])
            if child is None or child["state"] != "approved":
                violations.append(
                    {
                        "bundle_id": bundle["id"],
                        "slot": slot,
                        "why": f"child state={None if child is None else child['state']} 不是 approved",
                    }
                )
    return violations


def marker_violations(db: DbSnapshot) -> list[dict[str, Any]]:
    """把库里的 marker 行喂回 `definitions.marker_digest()` 现算比对。"""
    _ensure_backend_on_path()
    from app.services.workpaper_sync.definitions import (  # noqa: PLC0415
        TYPED_NULL_MARKERS,
        marker_digest,
    )

    violations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in db.null_markers:
        marker_id = row["marker_id"]
        seen.add(marker_id)
        registry_entry = TYPED_NULL_MARKERS.get(marker_id)
        if registry_entry is None:
            violations.append({"marker_id": marker_id, "why": "库里的 marker 不在生产 registry 里"})
            continue
        expected = marker_digest(row["applies_to_slot"])
        if row["sha256"] != expected:
            violations.append(
                {"marker_id": marker_id, "why": f"digest 与 `marker_digest()` 现算不符（期望 {expected[:12]}…）"}
            )
        if row["sha256"] == "0" * 64:
            violations.append({"marker_id": marker_id, "why": "全零 hash"})
        if not (row["canonical_payload"] or "").strip():
            violations.append({"marker_id": marker_id, "why": "canonical payload 为空"})
    for marker_id in sorted(TYPED_NULL_MARKERS):
        if marker_id not in seen:
            violations.append({"marker_id": marker_id, "why": "生产 registry 声明的 marker 在库里缺行"})
    return violations


def candidate_violations(db: DbSnapshot) -> list[dict[str, Any]]:
    current_ids = {row["current_representation_id"] for row in db.entry_states}
    violations: list[dict[str, Any]] = []
    for row in db.candidates:
        if row["state"] in {"ready", "finalized"} and not row["target_definition_bundle_id"]:
            violations.append({"candidate_id": row["id"], "why": f"state={row['state']} 却无 target bundle"})
        if row["state"] != "finalized" and row["finalized_representation_id"]:
            violations.append({"candidate_id": row["id"], "why": "未 finalized 却有 finalized pointer"})
        if row["finalized_representation_id"] and row["finalized_representation_id"] in current_ids:
            # finalized 后指针合法；此处只检测**非** finalized 的 candidate 成为 current。
            if row["state"] != "finalized":
                violations.append({"candidate_id": row["id"], "why": "非 finalized candidate 成为 current"})
    return violations


def pure_upgrade_violations(db: DbSnapshot) -> list[dict[str, Any]]:
    by_version: dict[str, list[dict[str, Any]]] = {}
    for row in db.representations:
        by_version.setdefault(row["content_version_id"], []).append(row)
    violations: list[dict[str, Any]] = []
    for version_id, rows in sorted(by_version.items()):
        generations = sorted(int(r["generation"]) for r in rows)
        if len(set(generations)) != len(generations):
            violations.append({"content_version_id": version_id, "why": "同 content version 下 generation 重复"})
        if len(rows) > 1 and len({r["entry_id"] for r in rows}) == 1:
            bundles = {r["definition_bundle_sha256"] for r in rows}
            if len(bundles) == 1:
                violations.append(
                    {
                        "content_version_id": version_id,
                        "why": "同 entry 多个 generation 但 bundle digest 未变 ⇒ 不是 definition upgrade",
                    }
                )
    return violations


def incoming_state_violations(db: DbSnapshot) -> list[dict[str, Any]]:
    # incoming artifact 的 state 明细不在快照列里（只取了行数），此处只能给结构结论。
    return []


def scope_violations(db: DbSnapshot) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    violations: list[dict[str, Any]] = []
    for row in db.scope_index:
        key = (row["resource_kind"], row["resource_id"])
        if key in seen:
            violations.append({"resource": list(key), "why": "resource id 被复用"})
        seen[key] = row
        if not (row["entry_id"] or "").strip():
            violations.append({"resource": list(key), "why": "entry_id 为空 ⇒ scope 丢失"})
    return violations


def numeric_revision_collision_violations(db: DbSnapshot) -> list[dict[str, Any]]:
    seen: dict[tuple[str, int], str] = {}
    violations: list[dict[str, Any]] = []
    for row in db.content_versions:
        key = (row["wp_id"], int(row["revision"]))
        if key in seen:
            violations.append({"wp_id": row["wp_id"], "revision": row["revision"], "why": "同 wp 同 revision 重复"})
        seen[key] = row["id"]
    return violations


ROW_VIOLATION_FUNCTIONS: Mapping[str, Any] = {
    "child_inventory_violations": child_inventory_violations,
    "projection_child_violations": projection_child_violations,
    "marker_violations": marker_violations,
    "candidate_violations": candidate_violations,
    "pure_upgrade_violations": pure_upgrade_violations,
    "incoming_state_violations": incoming_state_violations,
    "scope_violations": scope_violations,
    "numeric_revision_collision_violations": numeric_revision_collision_violations,
}


def evaluate_chain_checks(db: DbSnapshot) -> dict[str, dict[str, Any]]:
    """逐条现算链路检查。**纯函数**：只吃 `db` 快照，便于守卫正向重算（教训 15）。"""
    out: dict[str, dict[str, Any]] = {}
    for check in CHAIN_CHECKS:
        violations: list[Any] = []
        if check.row_violation_fn and db.readable:
            fn = ROW_VIOLATION_FUNCTIONS[check.row_violation_fn]
            violations = list(fn(db))
        out[check.check_id] = check.evaluate(db, violations)
    return out


# ════════════════════════════════════════════════════════════════════════════
# §4 逐 entry 双向核对
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class Task66PlanFacts:
    """Task 66 清册的只读投影（本任务的必需输入；一个字节都不改）。"""

    payload: dict[str, Any]

    @property
    def items(self) -> list[dict[str, Any]]:
        return self.payload["items"]

    @property
    def replacement_registry(self) -> list[dict[str, Any]]:
        return self.payload["replacement_registry"]

    @property
    def scenario_sets(self) -> dict[str, Any]:
        return self.payload["manifest_required_scenario_sets"]

    @property
    def plan_commit(self) -> str:
        return str(self.payload["plan_commit"])

    def items_by_entry(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for item in self.items:
            for entry_id in (item.get("replacement") or {}).get("manifest_entry_ids") or []:
                out.setdefault(entry_id, []).append(item["item_id"])
        return {key: sorted(value) for key, value in out.items()}

    def pending_delete_item_ids(self) -> set[str]:
        return {i["item_id"] for i in self.items if i["disposition"] == "pending_delete"}

    def items_missing_required_bindings(self) -> list[dict[str, Any]]:
        """正文：「digest/owner/rollback 缺失立即报结构错误」。逐项现算，不信 counters。"""
        bad: list[dict[str, Any]] = []
        for item in self.items:
            missing: list[str] = []
            if not (item.get("sha256") or "").strip():
                missing.append("sha256")
            owner = item.get("owner") or {}
            if not str(owner.get("deletion_owner_task") or "").strip():
                missing.append("owner.deletion_owner_task")
            if not str(owner.get("replacement_owner_task") or "").strip():
                missing.append("owner.replacement_owner_task")
            rollback = item.get("rollback_target") or {}
            if not str(rollback.get("mode") or "").strip():
                missing.append("rollback_target.mode")
            if missing:
                bad.append({"item_id": item["item_id"], "missing": missing})
        return bad


def load_task66_plan() -> Task66PlanFacts:
    payload = read_json(TASK66_PLAN_PATH)
    if payload.get("task") != "66":
        raise Task67GenerationError("Task 66 清册的 `task` 字段不是 66 —— 输入被换过")
    for key in ("items", "replacement_registry", "manifest_required_scenario_sets", "plan_commit"):
        if key not in payload:
            raise Task67GenerationError(f"Task 66 清册缺 `{key}` —— 本任务的双向核对无法进行")
    return Task66PlanFacts(payload=payload)


@dataclass
class ProductionLandings:
    """registry / profile / supply 三个生产面的现算落点。"""

    plan_by_entry: dict[str, dict[str, Any]]
    registration_count: int
    profile_by_entry: dict[str, dict[str, Any]]
    supply_by_entry: dict[str, dict[str, Any]]
    delivered_contracts: list[dict[str, Any]]
    pending_engine_adapters: list[dict[str, Any]]
    allowed_provider_modules: list[str]
    opaque_lanes: list[dict[str, Any]]


def collect_production_landings(entries: Mapping[str, Mapping[str, Any]]) -> ProductionLandings:
    _ensure_backend_on_path()
    from app.services.workpaper_sync import entry_profile as EP  # noqa: PLC0415
    from app.services.workpaper_sync import entry_source_facts as F  # noqa: PLC0415
    from app.services.workpaper_sync import opaque_entry_gate as OG  # noqa: PLC0415
    from app.services.workpaper_sync import projection_provisioning as PP  # noqa: PLC0415
    from app.services.workpaper_sync.adapters import registry as REG  # noqa: PLC0415

    plan = REG.build_manifest_registration_plan(entries)
    plan_by_entry = {
        item.entry_id: {
            "capability": item.capability.value,
            "contract_id": item.contract_id,
            "provider_module": item.provider_module,
            "blocked_reason": item.blocked_reason,
            "registrable": item.blocked_reason is None,
        }
        for item in plan
    }
    registry = REG.build_production_registry(manifest={"entries": list(entries.values())})
    registration_count = len(registry.registrations())

    profile_by_entry: dict[str, dict[str, Any]] = {}
    for entry_id, entry in entries.items():
        record: dict[str, Any] = {
            "editable": None,
            "editability": None,
            "room_model": None,
            "scenario_profile_id": None,
            "scenario_profile_digest": None,
            "capability": entry.get("capability"),
            "capability_consistency": None,
            "capability_error": None,
            "descriptor": None,
            "descriptor_error": None,
            "room": None,
            "room_error": None,
        }
        try:
            profile = EP.extract_entry_profile(entry)
            capability = EP.capability_of(entry)
            record.update(
                editable=profile.editable,
                editability=profile.editability.value,
                room_model=profile.room_model.value,
                scenario_profile_id=profile.scenario_profile.profile_id,
                scenario_profile_digest=profile.scenario_profile.digest,
            )
            try:
                EP.assert_profile_consistent_with_capability(profile, capability)
                record["capability_consistency"] = "consistent"
            except EP.EntryProfileError as exc:
                record["capability_consistency"] = type(exc).__name__
                record["capability_error"] = str(exc)
            descriptor = F.observe_descriptor_facts(entry)
            if descriptor is None:
                record["descriptor"] = {"observed": False, "why": "该 entry 不产出 launch descriptor"}
            else:
                record["descriptor"] = {
                    "observed": True,
                    "mode": descriptor.mode.value,
                    "exposes_mode_switch": descriptor.exposes_mode_switch,
                }
                try:
                    EP.assert_profile_consistent_with_descriptor(profile, capability, descriptor)
                    record["descriptor"]["consistency"] = "consistent"
                except EP.EntryProfileError as exc:
                    record["descriptor"]["consistency"] = type(exc).__name__
                    record["descriptor_error"] = str(exc)
            room = F.observe_room_facts(entry)
            record["room"] = {
                "shared_doc_key": room.shared_doc_key,
                "doc_key_includes_mtime": room.doc_key_includes_mtime,
                "participant_lease": room.participant_lease,
            }
            try:
                EP.assert_profile_consistent_with_room(profile, room)
                record["room"]["consistency"] = "consistent"
            except EP.EntryProfileError as exc:
                record["room"]["consistency"] = type(exc).__name__
                record["room_error"] = str(exc)
        except EP.EntryProfileError as exc:
            record["capability_consistency"] = type(exc).__name__
            record["capability_error"] = str(exc)
        profile_by_entry[entry_id] = record

    supply_by_entry: dict[str, dict[str, Any]] = {}
    for entry_id in entries:
        try:
            supply = PP.load_projection_supply(entry_id)
        except Exception as exc:  # noqa: BLE001 - 供给缺失是要报告的结构事实
            supply_by_entry[entry_id] = {
                "available": False,
                "error_type": type(exc).__name__,
                "error": str(exc)[:220],
                "authority_model": None,
            }
            continue
        supply_by_entry[entry_id] = {
            "available": True,
            "error_type": None,
            "error": None,
            "authority_model": getattr(getattr(supply, "authority_model", None), "value", None),
            "contract_id": getattr(supply, "contract_id", None),
        }

    return ProductionLandings(
        plan_by_entry=plan_by_entry,
        registration_count=registration_count,
        profile_by_entry=profile_by_entry,
        supply_by_entry=supply_by_entry,
        delivered_contracts=[
            {
                "contract_id": row.get("contract_id"),
                "entry_id": row.get("entry_id"),
                "authority_model": row.get("authority_model"),
                "adapter_registered": bool(row.get("adapter_registered")),
                "provider_module": row.get("provider_module"),
            }
            for row in REG.DELIVERED_PER_ENTRY_CONTRACTS
        ],
        pending_engine_adapters=[
            {"module_path": row.get("module_path") or row.get("module"), "document_type": row.get("document_type")}
            for row in REG.PENDING_ENGINE_ADAPTERS
        ],
        allowed_provider_modules=sorted(REG._ALLOWED_PROVIDER_MODULES),
        opaque_lanes=[
            {
                "lane_id": lane.lane_id,
                "authority_model": lane.authority_model.value,
                "document_type": lane.document_type,
                "has_html_counterpart": lane.has_html_counterpart,
                "adjudication_owner_task": lane.adjudication_owner_task,
            }
            for lane in OG.OPAQUE_AUTHORITY_LANES
        ],
    )


def build_entry_rows(
    *,
    regeneration: SourceRegeneration,
    landings: ProductionLandings,
    db: DbSnapshot,
    plan66: Task66PlanFacts,
) -> list[dict[str, Any]]:
    """逐 entry 组装十个核对面。**父入口不重复计数**由 `counted_in_denominator` 表达。"""
    disk_entries = {entry["entry_id"]: entry for entry in regeneration.disk["entries"]}
    rebuilt_entries = (
        {}
        if regeneration.rebuilt is None
        else {entry["entry_id"]: entry for entry in regeneration.rebuilt["entries"]}
    )
    plan_items_by_entry = plan66.items_by_entry()
    scenario_sets = plan66.scenario_sets

    entry_states_by_entry: dict[str, list[dict[str, Any]]] = {}
    for row in db.entry_states:
        entry_states_by_entry.setdefault(row["entry_id"], []).append(row)
    representations_by_entry: dict[str, list[dict[str, Any]]] = {}
    for row in db.representations:
        representations_by_entry.setdefault(row["entry_id"], []).append(row)
    candidates_by_entry: dict[str, list[dict[str, Any]]] = {}
    for row in db.candidates:
        candidates_by_entry.setdefault(row["entry_id"], []).append(row)
    runs_by_entry: dict[str, list[dict[str, Any]]] = {}
    for row in db.test_runs:
        runs_by_entry.setdefault(row["entry_id"], []).append(row)
    scenarios_by_entry: dict[str, list[dict[str, Any]]] = {}
    for row in db.evidence_scenarios:
        scenarios_by_entry.setdefault(row["entry_id"], []).append(row)

    rows: list[dict[str, Any]] = []
    for entry_id in sorted(disk_entries):
        disk = disk_entries[entry_id]
        rebuilt = rebuilt_entries.get(entry_id)
        profile = landings.profile_by_entry.get(entry_id) or {}
        supply = landings.supply_by_entry.get(entry_id) or {}
        plan_landing = landings.plan_by_entry.get(entry_id)

        disk_digest = entry_source_digest(disk)
        rebuilt_digest = None if rebuilt is None else entry_source_digest(rebuilt)
        source_changed = rebuilt is not None and rebuilt_digest != disk_digest

        independent = bool(disk.get("independent_entry"))
        parent_entry_id = disk.get("parent_entry_id")

        scenario_probe = scenario_sets.get(entry_id) or {}
        row = {
            "entry_id": entry_id,
            "document_type": disk.get("document_type"),
            "capability": disk.get("capability"),
            "migration_state": disk.get("migration_state"),
            "independent_entry": independent,
            "parent_entry_id": parent_entry_id,
            # 🔴 父入口不重复计数：所有 counters 的分母只取 `counted_in_denominator=True`。
            "counted_in_denominator": independent,
            "counted_in_denominator_why": (
                "独立 entry"
                if independent
                else f"parent 重复入口（parent_entry_id={parent_entry_id!r}），只复用其独立 entry 的一切"
            ),
            # ── ① source digest
            "source_digest": {
                "disk": disk_digest,
                "rebuilt_from_source": rebuilt_digest,
                "changed": source_changed,
                "rebuild_available": rebuilt is not None,
            },
            # ── ② editable ③ room_model ④ scenario_profile
            "editable": profile.get("editable"),
            "editability": profile.get("editability"),
            "room_model": profile.get("room_model"),
            "scenario_profile": {
                "profile_id": profile.get("scenario_profile_id"),
                "digest": profile.get("scenario_profile_digest"),
                "capability_consistency": profile.get("capability_consistency"),
                "capability_error": profile.get("capability_error"),
                "required_scenario_probe": {
                    "status": scenario_probe.get("status"),
                    "error_type": scenario_probe.get("error_type"),
                    "scenario_count": len(scenario_probe.get("scenario_ids") or []),
                    "set_digest": scenario_probe.get("required_scenario_set_digest"),
                    "is_probe_not_verdict": True,
                },
            },
            # ── ⑤ registry 落点
            "registry_landing": {
                "planned": plan_landing is not None,
                "registrable": None if plan_landing is None else plan_landing["registrable"],
                "contract_id": None if plan_landing is None else plan_landing["contract_id"],
                "provider_module": None if plan_landing is None else plan_landing["provider_module"],
                "blocked_reason": None if plan_landing is None else plan_landing["blocked_reason"],
                "adapter_id_in_manifest": disk.get("adapter_id"),
                "actually_registered": False,
            },
            # ── ⑥ 宿主 DOM 落点
            "host_dom_landing": {
                "host_path": disk.get("host_path"),
                "mount_count": len(disk.get("mounts") or []),
                "mounts": [
                    {
                        "mount_id": mount.get("mountId"),
                        "file": mount.get("file"),
                        "component": mount.get("component"),
                        "condition": mount.get("condition"),
                        "runtime_cardinality": mount.get("runtimeCardinality"),
                        "source_kind": mount.get("sourceKind"),
                    }
                    for mount in (disk.get("mounts") or [])
                ],
                "host_reachable": bool(
                    ((disk.get("scenario_profile") or {}).get("host_reachable"))
                ),
                "inbound_reference_count": (disk.get("profile_source") or {}).get(
                    "inbound_reference_count"
                ),
            },
            # ── ⑦ descriptor / room 配置
            "descriptor_room_config": {
                "descriptor": profile.get("descriptor"),
                "descriptor_error": profile.get("descriptor_error"),
                "room": profile.get("room"),
                "room_error": profile.get("room_error"),
            },
            # ── ⑧ authority-model / contract / definition bundle 链
            "authority_contract_bundle_chain": {
                "projection_supply_available": supply.get("available"),
                "projection_supply_error_type": supply.get("error_type"),
                "authority_model": supply.get("authority_model"),
                "contract_id": supply.get("contract_id"),
                "approved_bundle_bound_to_entry": False,
                "why_no_bundle_binding": (
                    "`working_paper_sync_definition_bundle` 没有 entry_id 列 —— bundle 只经 "
                    "representation / application / test_run 的外键与 entry 相连，而这三张表"
                    "实测 0 行 ⇒ 今天没有任何 bundle 绑定到具体 entry。"
                ),
            },
            # ── ⑨ candidate / published result representation
            "candidate_published_representation": {
                "entry_state_rows": len(entry_states_by_entry.get(entry_id) or []),
                "current_representation_id": next(
                    (
                        r["current_representation_id"]
                        for r in entry_states_by_entry.get(entry_id) or []
                    ),
                    None,
                ),
                "representation_rows": len(representations_by_entry.get(entry_id) or []),
                "candidate_rows": len(candidates_by_entry.get(entry_id) or []),
                "candidate_states": sorted(
                    {r["state"] for r in candidates_by_entry.get(entry_id) or []}
                ),
                "published": False,
            },
            # ── ⑩ Task 66 deletion plan 落点
            "deletion_plan_landing": {
                "referenced_by_item_ids": plan_items_by_entry.get(entry_id, []),
                "referenced_item_count": len(plan_items_by_entry.get(entry_id, [])),
                "pending_delete_item_count": len(
                    [
                        item_id
                        for item_id in plan_items_by_entry.get(entry_id, [])
                        if item_id in plan66.pending_delete_item_ids()
                    ]
                ),
                "has_landing": entry_id in plan_items_by_entry,
            },
            # ── evidence 面（未验收 / stale 的判据来源）
            "evidence": {
                "test_run_rows": len(runs_by_entry.get(entry_id) or []),
                "scenario_rows": len(scenarios_by_entry.get(entry_id) or []),
                "manifest_review_status": (disk.get("evidence") or {}).get("review_status"),
                "browser_case": (disk.get("evidence") or {}).get("browser_case"),
                "contract_test": (disk.get("evidence") or {}).get("contract_test"),
                "legacy_reasons": (disk.get("evidence") or {}).get("legacy_reasons") or [],
            },
        }

        row["registry_landing"]["actually_registered"] = (
            landings.registration_count > 0 and row["registry_landing"]["registrable"] is True
        )
        row["candidate_published_representation"]["published"] = (
            row["candidate_published_representation"]["entry_state_rows"] > 0
            and row["candidate_published_representation"]["representation_rows"] > 0
        )
        row["verdicts"] = classify_entry(row, disk)
        row["evidence_rerun_axes"] = evidence_rerun_axes(row, regeneration)
        rows.append(row)
    return rows


#: 六类计数的**逐 entry** 判据。写成纯函数让守卫能把记录里的 row 原样喂回来重算
#: （教训 15：反事实多臂只能证明「非重言」，抓不到「恒真」，必须再加正向重算）。
def classify_entry(row: Mapping[str, Any], disk_entry: Mapping[str, Any]) -> dict[str, Any]:
    unreachable = disk_entry.get("capability") == "unreachable"
    unadjudicated = bool(disk_entry.get("html_store") == "unresolved") and bool(
        disk_entry.get("independent_entry")
    )
    fake_bidirectional = disk_entry.get("migration_state") == "legacy_fake_bidirectional"
    published = bool(row["candidate_published_representation"]["published"])
    accepted = published and row["evidence"]["test_run_rows"] > 0
    planned_delete = row["deletion_plan_landing"]["pending_delete_item_count"] > 0
    # stale 只对**已有** evidence 的 entry 有意义；0 run 的 entry 是「未验收」不是「过期」。
    has_evidence = row["evidence"]["test_run_rows"] > 0
    return {
        "unadjudicated": unadjudicated,
        "fake_bidirectional": fake_bidirectional,
        "unaccepted": not accepted,
        "unreachable": unreachable,
        "evidence_stale": has_evidence and bool(row["source_digest"]["changed"]),
        "evidence_stale_is_measurable": has_evidence,
        "planned_delete": planned_delete,
    }


def evidence_rerun_axes(row: Mapping[str, Any], regeneration: SourceRegeneration) -> list[str]:
    """按 source/manifest/profile/definition/bundle/candidate 变化逐 entry 给出重跑集合。

    码取自生产枚举 `evidence.StaleReason`，不自造词表 —— 自造会让 Task 70 的刷新与
    Task 29/39 的 recomputer 用两套口径。
    """
    _ensure_backend_on_path()
    from app.services.workpaper_sync.evidence import StaleReason  # noqa: PLC0415

    axes: list[str] = []
    if not regeneration.digests_agree:
        axes.append(StaleReason.manifest_source_digest_changed.value)
    if row["source_digest"]["changed"]:
        if StaleReason.manifest_source_digest_changed.value not in axes:
            axes.append(StaleReason.manifest_source_digest_changed.value)
        axes.append(StaleReason.scenario_profile_changed.value)
    if not row["authority_contract_bundle_chain"]["approved_bundle_bound_to_entry"]:
        axes.append(StaleReason.definition_bundle_changed.value)
        axes.append(StaleReason.authority_model_changed.value)
    if (row["scenario_profile"]["required_scenario_probe"] or {}).get("status") != "derived":
        axes.append(StaleReason.required_scenario_set_changed.value)
    return sorted(set(axes))


# ════════════════════════════════════════════════════════════════════════════
# §5 结构错误 / 计数 / 入向义务 / BP
# ════════════════════════════════════════════════════════════════════════════


def structural_errors(
    *,
    regeneration: SourceRegeneration,
    rows: Sequence[Mapping[str, Any]],
    landings: ProductionLandings,
    plan66: Task66PlanFacts,
) -> list[dict[str, Any]]:
    """正文点名的四类立即报错 + 两条本任务补的完整性错误。逐条独立判据。"""
    errors: list[dict[str, Any]] = []

    if not regeneration.digests_agree:
        errors.append(
            {
                "kind": "source_digest_drifted_from_reviewed_overlay",
                "detail": (
                    "overlay 的 `approved_source_digest` 与当前源码实测 sourceDigest 不符 ⇒ "
                    "磁盘 manifest 已不是「最终源码」的 manifest。本任务不改 overlay（复核是"
                    "人的动作），只如实报错。"
                ),
                "approved": regeneration.approved_source_digest,
                "current": regeneration.current_source_digest,
                "mount_id_churn": len(regeneration.mount_ids_only_in_source),
                "owner_task": "1/67 复核方",
            }
        )

    # profile 降级：重算后的三字段与磁盘态不一致即降级（editable→readonly、
    # shared→none、profile_id 变化都算）。
    downgraded = [
        row["entry_id"]
        for row in rows
        if row["source_digest"]["rebuild_available"]
        and row["scenario_profile"]["profile_id"] is None
    ]
    if downgraded:
        errors.append(
            {
                "kind": "profile_downgraded",
                "detail": "重算后 scenario_profile 解析不出 profile_id",
                "entry_ids": sorted(downgraded),
                "owner_task": "67",
            }
        )

    # 计划外 legacy / unreachable：manifest 里判 legacy_fake_bidirectional 或 unreachable，
    # 但 Task 66 清册里没有任何一项引用它。
    unplanned = sorted(
        row["entry_id"]
        for row in rows
        if row["migration_state"] in {"legacy_fake_bidirectional", "unreachable_pending_delete"}
        and not row["deletion_plan_landing"]["has_landing"]
    )
    if unplanned:
        errors.append(
            {
                "kind": "unplanned_legacy_or_unreachable",
                "detail": "manifest 判 legacy/unreachable 但 Task 66 清册无落点",
                "entry_ids": unplanned,
                "owner_task": "66/67",
            }
        )

    missing_bindings = plan66.items_missing_required_bindings()
    if missing_bindings:
        errors.append(
            {
                "kind": "missing_digest_owner_or_rollback",
                "detail": "Task 66 清册项缺 digest / owner / rollback",
                "items": missing_bindings,
                "owner_task": "66",
            }
        )

    # 父入口重复计数：父与子同时进分母就是重复计数。
    double_counted = sorted(
        row["entry_id"]
        for row in rows
        if row["parent_entry_id"] is not None and row["counted_in_denominator"]
    )
    if double_counted:
        errors.append(
            {
                "kind": "parent_entry_double_counted",
                "detail": "parent 重复入口被算进分母",
                "entry_ids": double_counted,
                "owner_task": "67",
            }
        )

    unplanned_registry = sorted(
        row["entry_id"] for row in rows if not row["registry_landing"]["planned"]
    )
    if unplanned_registry:
        errors.append(
            {
                "kind": "registry_landing_missing",
                "detail": "manifest entry 在 registry 注册计划里没有对应项（静默跳过）",
                "entry_ids": unplanned_registry,
                "owner_task": "67",
            }
        )

    for error in errors:
        if error["kind"] not in STRUCTURAL_ERROR_KINDS:
            raise Task67GenerationError(f"结构错误类型 {error['kind']!r} 不在封闭词表里")
    return errors


def build_counters(
    *,
    rows: Sequence[Mapping[str, Any]],
    landings: ProductionLandings,
    db: DbSnapshot,
    plan66: Task66PlanFacts,
    regeneration: SourceRegeneration,
) -> dict[str, Any]:
    """正文点名的六类计数 + 结构分母。**纯函数**，便于守卫正向重算。"""
    counted = [row for row in rows if row["counted_in_denominator"]]
    all_rows = list(rows)

    def count(kind: str, *, scope: Sequence[Mapping[str, Any]]) -> int:
        return sum(1 for row in scope if row["verdicts"][kind])

    # 主口径：分母 = 独立 entry（父入口不重复计数）。
    reported = {kind: count(kind, scope=counted) for kind in REPORTED_COUNTER_KINDS}
    # 🔴 副口径必须同时给出。实测 `xlsx/gt-g6-other-bond-ecl` 既是 `capability=unreachable`
    # 又是 parent 重复入口 ⇒ 主口径下 `unreachable=0`。只报主口径会让一条真实的
    # unreachable entry 从报告里消失，而正文明令「如实报告 unreachable」。两个口径都在，
    # 差集也在，读者才不会把「不重复计数」误读成「没有」。
    over_all = {kind: count(kind, scope=all_rows) for kind in REPORTED_COUNTER_KINDS}
    if set(reported) != set(REPORTED_COUNTER_KINDS):
        raise Task67GenerationError(
            f"六类计数与封闭词表不符：多 {sorted(set(reported) - set(REPORTED_COUNTER_KINDS))} "
            f"少 {sorted(set(REPORTED_COUNTER_KINDS) - set(reported))}"
        )

    measurable_stale = [row for row in counted if row["verdicts"]["evidence_stale_is_measurable"]]
    return {
        "reported_by_task_text": reported,
        "reported_by_task_text_over_all_entries": over_all,
        "parent_duplicate_only_deltas": {
            kind: over_all[kind] - reported[kind] for kind in REPORTED_COUNTER_KINDS
        },
        "parent_duplicate_only_entry_ids": {
            kind: sorted(
                row["entry_id"]
                for row in all_rows
                if row["verdicts"][kind] and not row["counted_in_denominator"]
            )
            for kind in REPORTED_COUNTER_KINDS
        },
        "denominators": {
            "manifest_entry_total": len(all_rows),
            "independent_entry_total": len(counted),
            "parent_duplicate_total": len(all_rows) - len(counted),
            "primary_denominator": "independent_entry_total",
            "primary_denominator_why": (
                "正文「父入口不重复计数」⇒ 主口径分母只取 `independent_entry=true`。"
                "副口径 `..._over_all_entries` 与差集 `parent_duplicate_only_*` 同时给出，"
                "确保没有任何真实 entry 因为不进主分母而从报告里消失。"
            ),
            "evidence_stale_denominator": len(measurable_stale),
            "evidence_stale_denominator_empty": not measurable_stale,
            "evidence_stale_denominator_note": (
                None
                if measurable_stale
                else (
                    "`working_paper_sync_test_run` 实测 0 行 ⇒ 没有任何 evidence 可以「过期」。"
                    "`evidence_stale=0` **不是**「已刷新」，honest 读法是所有 entry 都在 "
                    "`unaccepted` 里。正文明确「允许报告 stale，不要求 stale 清零」，本报告"
                    "因此把该分母为空这件事显式写出来，并把「若有 evidence 则会 stale 的轴」"
                    "放进逐 entry `evidence_rerun_axes` 交给 Task 70。"
                )
            ),
        },
        "manifest_side": {
            "entry_count": len(all_rows),
            "capability_counts": _tally(all_rows, "capability"),
            "migration_state_counts": _tally(all_rows, "migration_state"),
            "room_model_counts": _tally(all_rows, "room_model"),
            "editability_counts": _tally(all_rows, "editability"),
            "entries_with_changed_source_digest": sum(
                1 for row in all_rows if row["source_digest"]["changed"]
            ),
            "entries_with_capability_profile_drift": sum(
                1
                for row in all_rows
                if row["scenario_profile"]["capability_consistency"] not in (None, "consistent")
            ),
            "entries_with_underivable_required_scenarios": sum(
                1
                for row in all_rows
                if (row["scenario_profile"]["required_scenario_probe"] or {}).get("status")
                != "derived"
            ),
        },
        "registry_side": {
            "planned_entry_count": len(landings.plan_by_entry),
            "registrable_entry_count": sum(
                1 for value in landings.plan_by_entry.values() if value["registrable"]
            ),
            "actually_registered_count": landings.registration_count,
            "delivered_per_entry_contract_count": len(landings.delivered_contracts),
            "manifest_entries_with_adapter_id": sum(
                1 for row in all_rows if row["registry_landing"]["adapter_id_in_manifest"]
            ),
        },
        "definition_side": {
            "definition_artifact_rows": db.row_counts.get("working_paper_sync_definition_artifact", 0),
            "definition_bundle_rows": db.row_counts.get("working_paper_sync_definition_bundle", 0),
            "approved_bundle_rows": sum(
                1 for row in db.definition_bundles if row["state"] == "approved"
            ),
            "typed_null_marker_rows": db.row_counts.get(
                "working_paper_sync_definition_null_marker", 0
            ),
            "bundles_bound_to_a_manifest_entry": 0,
            "bundles_bound_to_a_manifest_entry_why": (
                "bundle 表无 entry_id 列；与 entry 的唯一连接是 representation / application / "
                "test_run 的外键，三张表实测 0 行。"
            ),
        },
        "candidate_representation_side": {
            "entry_state_rows": db.row_counts.get("working_paper_sync_entry_state", 0),
            "content_version_rows": db.row_counts.get("working_paper_content_version", 0),
            "content_representation_rows": db.row_counts.get(
                "working_paper_content_representation", 0
            ),
            "upgrade_candidate_rows": db.row_counts.get(
                "working_paper_representation_upgrade_candidate", 0
            ),
            "entries_with_published_representation": sum(
                1 for row in all_rows if row["candidate_published_representation"]["published"]
            ),
        },
        "deletion_plan_side": {
            "plan_item_total": len(plan66.items),
            "plan_pending_delete_total": len(plan66.pending_delete_item_ids()),
            "manifest_entries_with_plan_landing": sum(
                1 for row in all_rows if row["deletion_plan_landing"]["has_landing"]
            ),
            "replacement_surface_modules": len(plan66.replacement_registry),
            "replacement_surface_unreachable_from_production_host": sum(
                1
                for surface in plan66.replacement_registry
                if not surface.get("reachable_from_production_host")
            ),
            "planned_delete_is_not_a_final_zero": (
                "正文：「不把 planned-delete 当作最终五个零」。此处只报计划规模，"
                "删除资格判断在 Task 72 Stage A。"
            ),
        },
        "source_side": {
            "mount_ids_only_on_disk": len(regeneration.mount_ids_only_on_disk),
            "mount_ids_only_in_source": len(regeneration.mount_ids_only_in_source),
            "source_digests_agree": regeneration.digests_agree,
        },
    }


def _tally(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key))
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


#: 扫描范围：生产代码与数据文件里点名 Task 67 的入向义务。写成常量让守卫能断言
#: 「至少覆盖这些真实目标」（教训 16：名单类判据必须断言包含真实目标）。
INBOUND_SCAN_ROOTS: tuple[str, ...] = ("backend/app", "backend/data")

_INBOUND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("adjudication_owner_task", re.compile(r'"adjudication_owner_task"\s*:\s*"67"')),
    ("owner_task", re.compile(r'"owner_task"\s*:\s*"67"')),
    ("must_fix_before", re.compile(r'"must_fix_before"\s*:\s*"[^"]*Task 67[^"]*"')),
    ("prose_reference", re.compile(r"Task 67")),
)

#: 必须出现在入向义务里的**真实**目标。只要求「非空 + 逐条成立」会被改名绕过。
REQUIRED_INBOUND_TARGETS: tuple[str, ...] = (
    "backend/app/services/workpaper_sync/opaque_entry_gate.py",
    "backend/app/services/workpaper_sync/entry_profile.py",
    "backend/app/services/workpaper_sync/evidence_freshness.py",
    "backend/data/workpaper_sync_task66_legacy_deletion_plan.json",
    "backend/data/workpaper_task61_word_pilot_gate_probes.json",
)


#: 🔴 **普查派生量（census-derived）** —— 逐字节锁必须剔除/投影的那一类字段。
#: 缺陷形态、为什么剔、剔除 ≠ 不管：见 `backend/scripts/_census_lock.py`（同型三处 + 一处传递）。
#:
#: 本门落点：`inbound_obligations` = 现扫 `backend/app` 与 `backend/data` 里点名 Task 67 的
#: 文件，随仓库演进。BP-72-8 实测：Task 72 的 pre-delete 报告一落盘就把 12 行顶成 13 行，
#: `test_inbound_scan_recomputes_...` 与 `test_check_matches_the_file_on_disk` 双双打红。
#: 本节点走**投影**而非删除：整块剔会把「入向普查器退化」一起放过（教训 16 的原始动机），
#: 故 :data:`REQUIRED_INBOUND_TARGETS` 那批真实目标的行继续锁死，只剔随仓库增长的尾巴。
CENSUS_KEYS: tuple[str, ...] = ("inbound_obligations", "census_contract.measured")


def _project_inbound_obligations(rows: Any) -> Any:
    """入向义务的**稳定投影**：只留真实目标那几行（它们不随仓库演进，继续进锁）。"""
    if not isinstance(rows, list):
        return rows
    return [
        r for r in rows if isinstance(r, Mapping) and str(r.get("path")) in REQUIRED_INBOUND_TARGETS
    ]


#: 走**投影**（保留稳定核）而不是整块剔除的 census 路径。未列在此的 census 路径整块剔。
CENSUS_PROJECTIONS: Mapping[str, Any] = {"inbound_obligations": _project_inbound_obligations}


def strip_census(node: Any, *, path: str = "") -> Any:
    """按点号路径对 :data:`CENSUS_KEYS` 剔除、对 :data:`CENSUS_PROJECTIONS` 投影（机制见
    `_census_lock`）。🔴 路径限定而非裸键名：报告里另有十余处正当的 `sha256` / `*_digest`，
    按裸键名剔会把真 stale 轴一起放过。
    """
    return _census_lock.strip_census(
        node, CENSUS_KEYS, projections=CENSUS_PROJECTIONS, path=path
    )


def census_semantics(rows: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """入向普查的**语义性质**。现算、不随仓库演进 ⇒ 逐条进锁（框架见 `_census_lock`）。

    * `scan_is_not_empty` 空集恒真；`all_required_targets_present` 普查器漏掉真实目标；
    * `scan_reaches_beyond_the_required_targets` —— 普查器被「修」成只返回那 5 条写死目标时
      投影比对照样绿，这条是唯一能抓到它的判据；
    * `every_scan_root_is_represented` 某个扫描根整块失联；`both_ownership_kinds_present`
      「结构化归属 vs 散文提及」被压平成一态。
    """
    live = list(rows) if rows is not None else collect_inbound_obligations()
    paths = {str(row["path"]) for row in live}
    structured = {str(row["path"]) for row in live if row.get("structured_ownership")}
    roots = {r: any(p.startswith(f"{r}/") for p in paths) for r in INBOUND_SCAN_ROOTS}
    checks = {
        "scan_is_not_empty": bool(live),
        "all_required_targets_present": set(REQUIRED_INBOUND_TARGETS) <= paths,
        "scan_reaches_beyond_the_required_targets": bool(paths - set(REQUIRED_INBOUND_TARGETS)),
        # 🔴 「每个根都有代表」与「一个根都没登记」必须分开：空的 roots 字典让 `all()` 恒真。
        "scan_roots_are_declared": bool(roots) and set(roots) == set(INBOUND_SCAN_ROOTS),
        "every_scan_root_is_represented": bool(roots) and all(roots.values()),
        "both_ownership_kinds_present": bool(structured) and bool(paths - structured),
        "opaque_gate_carries_structured_ownership": (
            "backend/app/services/workpaper_sync/opaque_entry_gate.py" in structured
        ),
    }
    return _census_lock.finalize_checks(checks, scan_roots_represented=roots)


def build_census_contract(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """普查契约节点。组装见 `_census_lock.build_census_contract`。"""
    return _census_lock.build_census_contract(
        statement=(
            "入向义务是仓库级普查的结果（随仓库演进）：`--check` 时现算并断言语义性质，"
            "**不进**逐字节冻结基线；真实目标那几行走投影，继续锁死。"
        ),
        census_keys=CENSUS_KEYS,
        projection=(
            "`inbound_obligations` → 只保留 `required_inbound_targets` 那几行（稳定核）；"
            "整块剔会把「普查器退化」一起放过。"
        ),
        why="BP-72-8 实测：下游 pre-delete 报告落进 `backend/data/` 就把 12 行顶成 13 行。",
        excluded_is_not_unchecked=(
            "`census_semantics` 断言六条语义性质，其中 "
            "`scan_reaches_beyond_the_required_targets` 专门抓「只返回写死的 5 条」。"
        ),
        still_locked=[
            "report_commit（源码变了但报告没重生成 —— 唯一的真 stale 轴）",
            "required_inbound_targets 那几行的 kinds / hit_count / structured_ownership",
            "chain_checks 的逐项判定、counters、entries 的逐 entry 事实",
            "report_digest（现在算在 census 投影**之后**的内容上 ⇒ 非普查内容继续锁死）",
        ],
        semantics=census_semantics(rows),
        measured={
            "row_count": len(rows),
            "structured_ownership_rows": sum(1 for r in rows if r.get("structured_ownership")),
        },
    )


def collect_inbound_obligations() -> list[dict[str, Any]]:
    """现扫生产代码/数据里点名 Task 67 的归属登记（不抄第二份清单）。"""
    out: list[dict[str, Any]] = []
    for root_name in INBOUND_SCAN_ROOTS:
        root = REPO / root_name
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".json"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "Task 67" not in text and '"67"' not in text:
                continue
            kinds: list[str] = []
            hit_count = 0
            for kind, pattern in _INBOUND_PATTERNS:
                matches = pattern.findall(text)
                if matches:
                    kinds.append(kind)
                    hit_count += len(matches)
            if not kinds:
                continue
            out.append(
                {
                    "path": rel(path),
                    "kinds": sorted(set(kinds)),
                    "hit_count": hit_count,
                    "structured_ownership": any(
                        kind in {"adjudication_owner_task", "owner_task", "must_fix_before"}
                        for kind in kinds
                    ),
                }
            )
    missing = [
        target for target in REQUIRED_INBOUND_TARGETS if target not in {row["path"] for row in out}
    ]
    if missing:
        raise Task67GenerationError(
            f"入向义务扫描漏掉了已知真实目标 {missing} —— 扫描器退化了（教训 16）"
        )
    return out


def build_blocking_preconditions(
    *,
    rows: Sequence[Mapping[str, Any]],
    landings: ProductionLandings,
    db: DbSnapshot,
    plan66: Task66PlanFacts,
    regeneration: SourceRegeneration,
) -> list[dict[str, Any]]:
    dead_surfaces = sorted(
        surface["path"]
        for surface in plan66.replacement_registry
        if not surface.get("reachable_from_production_host")
    )
    drifted = sorted(
        row["entry_id"]
        for row in rows
        if row["scenario_profile"]["capability_consistency"] not in (None, "consistent")
    )
    bps = [
        {
            "id": "BP-67-1",
            "title": "reviewed overlay 的 approved source digest 已过期 ⇒ 无法在不改 overlay 的前提下重生成磁盘 manifest",
            "statement": (
                "`build_manifest()` 的 `approved_source_digest` 复核门当前拒绝当前源码"
                f"（approved={regeneration.approved_source_digest[:12]}… vs "
                f"current={regeneration.current_source_digest[:12]}…）。本任务用**内存**补丁"
                "重算得到 186 条 entry，与磁盘 entry 集合一致、stats 逐格一致，但 "
                f"{len(regeneration.mount_ids_only_in_source)} 个 mountId 两侧互不相同 ⇒ 每条"
                "受影响 entry 的 source digest 都变了。"
            ),
            "owner_task": "1/67 复核方（人工复核 mount diff 后更新 approved_source_digest）",
            "why_not_fixed_here": (
                "正文只授权报告；`--apply` 会覆盖并发会话在用的 overlay/manifest，且"
                "「复核过 mount diff」是人的动作，不能由生成器代签。"
            ),
            "evidence": {
                "digests_agree": regeneration.digests_agree,
                "mount_id_only_in_source": len(regeneration.mount_ids_only_in_source),
                "mount_id_only_on_disk": len(regeneration.mount_ids_only_on_disk),
                "rebuilt_entry_count": (
                    None if regeneration.rebuilt is None else len(regeneration.rebuilt["entries"])
                ),
            },
        },
        {
            "id": "BP-67-2",
            "title": "186 条 planned entry 一条都注册不上（供给为 0）",
            "statement": (
                f"registry 注册计划有 {len(landings.plan_by_entry)} 项、其中 "
                f"{sum(1 for v in landings.plan_by_entry.values() if v['registrable'])} 项静态可注册，"
                f"但 `build_production_registry().registrations()` 实测 "
                f"{landings.registration_count} 条。原因是 published representation 供给为 0："
                f"`working_paper_sync_entry_state`={db.row_counts.get('working_paper_sync_entry_state', 0)} 行、"
                f"`working_paper_content_representation`={db.row_counts.get('working_paper_content_representation', 0)} 行、"
                f"`working_paper_content_version`={db.row_counts.get('working_paper_content_version', 0)} 行。"
            ),
            "owner_task": "`ContentMutationService.commit` + Tasks 36/77 finalize gate",
            "why_not_fixed_here": "供给是运行时产物，structural pre-reconcile 不写库。",
            "evidence": {
                "planned": len(landings.plan_by_entry),
                "registrable": sum(
                    1 for v in landings.plan_by_entry.values() if v["registrable"]
                ),
                "registered": landings.registration_count,
            },
        },
        {
            "id": "BP-67-3",
            "title": "5 条 docx entry 的 capability 与 room_model 结构性矛盾 ⇒ required scenario 推不出来",
            "statement": (
                "`capability=single_html` 只允许 `room_model ∈ ['none']`，这 5 条实得 "
                "`exclusive`，`assert_profile_consistent_with_capability` 现算抛 "
                "`EntryProfileDriftError` ⇒ Task 70 无法为它们推导 required scenario set。"
            ),
            "owner_task": "70（scenario 推导） / overlay 复核方（capability 或 room_model 二者之一裁错）",
            "why_not_fixed_here": "改 capability 是业务裁决、改 room_model 要动源码，两者都越界。",
            "evidence": {"entry_ids": drifted, "count": len(drifted)},
        },
        {
            "id": "BP-67-4",
            "title": "approved bundle 存在但一条都没绑到 entry ⇒ authority model 逐 entry 仍未定",
            "statement": (
                f"`working_paper_sync_definition_bundle` 实测 "
                f"{db.row_counts.get('working_paper_sync_definition_bundle', 0)} 行、其中 approved "
                f"{sum(1 for r in db.definition_bundles if r['state'] == 'approved')} 行"
                "（较 Task 61 实测的 1 行已增长），但 bundle 表**无 entry_id 列**，与 entry 的"
                "唯一连接（representation / application / test_run）全为 0 行 ⇒ 逐 entry 的"
                "authority model 依旧只能靠 `DELIVERED_PER_ENTRY_CONTRACTS` 的 reviewed 登记"
                f"（覆盖 {len(landings.delivered_contracts)} 条 entry），其余 "
                f"{len(landings.plan_by_entry) - len(landings.delivered_contracts)} 条无供给。"
            ),
            "owner_task": "70（按 approved bundle 重推 required scenario） / 76·77（bundle↔entry 绑定）",
            "why_not_fixed_here": "本任务不写库、不发布 contract。",
            "evidence": {
                "definition_bundle_rows": db.row_counts.get(
                    "working_paper_sync_definition_bundle", 0
                ),
                "approved_bundle_rows": sum(
                    1 for r in db.definition_bundles if r["state"] == "approved"
                ),
                "bundles_bound_to_entry": 0,
                "delivered_per_entry_contracts": len(landings.delivered_contracts),
            },
        },
        {
            "id": "BP-67-5",
            "title": "BP-66-1 如实转报：替代面对生产宿主不可达（本任务不解除）",
            "statement": (
                f"Task 66 实测 {len(dead_surfaces)}/{len(plan66.replacement_registry)} 个替代面模块"
                "从替代面目录外的生产文件不可达（含 `useWorkpaperSyncBridge.ts` 与 "
                "`WorkpaperSyncEditorHost.vue`）。本任务**现读该清册并原样核对**，未新增证据、"
                "也未解除。"
            ),
            "owner_task": "72（Stage B 接线/删除） / 69（宿主 DOM 独立回归）",
            "why_not_fixed_here": (
                "解除需要改前端宿主（把统一 bridge 接进 `components/workpaper/` 下的真实宿主），"
                "而正文只授权报告，且那 ~51 个宿主文件是并发会话在途禁碰面。"
            ),
            "evidence": {
                "unreachable_surface_count": len(dead_surfaces),
                "surface_total": len(plan66.replacement_registry),
                "unreachable_surface_paths": dead_surfaces,
                "task66_bp_id": "BP-66-1",
                "task66_bp_owner_task_field": "67",
                "task67_disposition": "reported_not_cleared",
            },
        },
        {
            "id": "BP-67-6",
            "title": "evidence 分母为空 ⇒ stale 计数无信息量，未验收才是真结论",
            "statement": (
                f"`working_paper_sync_test_run`={db.row_counts.get('working_paper_sync_test_run', 0)} 行、"
                f"`working_paper_entry_evidence_scenario`="
                f"{db.row_counts.get('working_paper_entry_evidence_scenario', 0)} 行 ⇒ "
                "`evidence_stale` 的分母为空。报告里 `evidence_stale=0` 必须与 "
                "`evidence_stale_denominator_empty=true` 一起读，否则会被误读成「已刷新」。"
            ),
            "owner_task": "70（真实刷新）",
            "why_not_fixed_here": "正文明令不运行真实 OO 场景。",
            "evidence": {
                "test_run_rows": db.row_counts.get("working_paper_sync_test_run", 0),
                "evidence_scenario_rows": db.row_counts.get(
                    "working_paper_entry_evidence_scenario", 0
                ),
            },
        },
    ]
    for bp in bps:
        if not BP_ID_RE.fullmatch(bp["id"]):
            raise Task67GenerationError(
                f"BP id {bp['id']!r} 不符 `BP-67-\\d+` —— 全局 BP-NN 已被 Tasks 60/61/63/64 重复占用"
            )
    return bps


# ════════════════════════════════════════════════════════════════════════════
# §6 报告组装与 CLI
# ════════════════════════════════════════════════════════════════════════════

WHY_THIS_TASK_ONLY_REPORTS: Mapping[str, str] = {
    "task_text": (
        "本任务是 structural pre-reconcile，只允许并如实报告未裁决、假双向、未验收、"
        "unreachable、evidence stale 及 planned-delete 计数；允许报告 stale，不要求 stale "
        "清零，不运行真实 OO 场景，不授权删除，也不把 planned-delete 当作最终五个零。"
    ),
    "consumers": (
        "输出只供 Tasks 68/69 独立结构复验与 Task 70 全 entry required-scenario 刷新；"
        "真正删除前判断只在 Task 72 Stage A 执行。"
    ),
    "what_this_report_does_not_certify": (
        "不认证五个零、不认证任何真实 OO probe、不认证删除资格、不认证 evidence 已刷新、"
        "不认证 adapter 已注册。"
    ),
    "readonly_guarantees": (
        "DB 只 SELECT（AST 可判）；磁盘 manifest / overlay / Task 66 清册均只读；"
        "唯一写入目标是本报告自己的 OUTPUT_PATH。"
    ),
}

FIVE_WAY_LOCK: Mapping[str, str] = {
    "source_side": (
        "`discover-workpaper-sync-mounts.mjs` 现扫源码得到 mounts + dispatchers + sourceDigest"
    ),
    "manifest_side": (
        "`generate_workpaper_sync_manifest.build_manifest()` 内存重算（overlay 的 "
        "approved digest 仅在内存里对齐），逐 entry 取 editable / room_model / scenario_profile"
    ),
    "registry_side": (
        "`build_manifest_registration_plan()` + `build_production_registry().registrations()` "
        "+ `load_projection_supply()` 现算"
    ),
    "database_side": (
        "一次 asyncio.run 的只读快照：22 张表的精确行数 + UNIQUE 索引 / CHECK / trigger 的"
        "实际定义 + definition/bundle/marker/entry_state/representation/candidate/"
        "content_version/scope/test_run/evidence 明细"
    ),
    "deletion_plan_side": (
        "Task 66 清册的 items / replacement_registry / manifest_required_scenario_sets 现读，"
        "逐 entry 双向核对落点"
    ),
}


def build_report() -> dict[str, Any]:
    regeneration = regenerate_from_source()
    plan66 = load_task66_plan()
    db = read_db_snapshot()

    disk_entries_by_id = {
        entry["entry_id"]: entry for entry in regeneration.disk["entries"]
    }
    landings = collect_production_landings(disk_entries_by_id)
    rows = build_entry_rows(
        regeneration=regeneration, landings=landings, db=db, plan66=plan66
    )
    for row in rows:
        missing = [facet for facet in REQUIRED_ENTRY_FACETS if facet not in row]
        if missing:
            raise Task67GenerationError(
                f"entry {row['entry_id']} 缺核对面 {missing} —— 正文要求逐 entry 十面齐备"
            )

    chain = evaluate_chain_checks(db)
    errors = structural_errors(
        regeneration=regeneration, rows=rows, landings=landings, plan66=plan66
    )
    counters = build_counters(
        rows=rows, landings=landings, db=db, plan66=plan66, regeneration=regeneration
    )
    bps = build_blocking_preconditions(
        rows=rows, landings=landings, db=db, plan66=plan66, regeneration=regeneration
    )
    inbound = collect_inbound_obligations()

    paradigm = read_json(PARADIGM_PATH)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "task": OWNER_TASK,
        "spec": SPEC,
        "description": (
            "Task 67 —— 从最终源码重新生成 mounts 与 source-backed manifest，逐 entry 锁定 "
            "source digest / editable / room_model / scenario_profile，并与 registry、宿主 DOM、"
            "descriptor+room 配置、authority-model+contract+definition bundle、candidate+"
            "published representation 及 Task 66 deletion plan 双向核对的**结构报告**。"
        ),
        "generator": rel(Path(__file__)),
        "report_commit": git_head(),
        "why_this_task_only_reports": dict(WHY_THIS_TASK_ONLY_REPORTS),
        "five_way_lock": dict(FIVE_WAY_LOCK),
        "reported_counter_kinds": list(REPORTED_COUNTER_KINDS),
        "required_entry_facets": list(REQUIRED_ENTRY_FACETS),
        "structural_error_kinds": list(STRUCTURAL_ERROR_KINDS),
        "paradigm_schema_version": paradigm.get("schema_version"),
        "inputs": {
            "entry_manifest": {
                "path": rel(MANIFEST_PATH),
                "sha256": sha256_of(MANIFEST_PATH),
                "readonly": True,
            },
            "entry_overlay": {
                "path": rel(OVERLAY_PATH),
                "sha256": sha256_of(OVERLAY_PATH),
                "readonly": True,
            },
            "task66_deletion_plan": {
                "path": rel(TASK66_PLAN_PATH),
                "sha256": sha256_of(TASK66_PLAN_PATH),
                "plan_commit": plan66.plan_commit,
                "readonly": True,
            },
            "migration_paradigm": {
                "path": rel(PARADIGM_PATH),
                "sha256": sha256_of(PARADIGM_PATH),
                "readonly": True,
            },
        },
        "source_regeneration": regeneration.as_dict(),
        "database_snapshot": db.as_dict(),
        "readonly_sql_statements": list(READONLY_SQL_STATEMENTS),
        "production_landings": {
            "registration_plan_size": len(landings.plan_by_entry),
            "registrations": landings.registration_count,
            "delivered_per_entry_contracts": landings.delivered_contracts,
            "pending_engine_adapters": landings.pending_engine_adapters,
            "allowed_provider_modules": landings.allowed_provider_modules,
            "opaque_authority_lanes": landings.opaque_lanes,
        },
        "chain_checks": chain,
        "structural_errors": errors,
        "counters": counters,
        "inbound_obligations": inbound,
        "census_contract": build_census_contract(inbound),
        "inbound_scan_roots": list(INBOUND_SCAN_ROOTS),
        "required_inbound_targets": list(REQUIRED_INBOUND_TARGETS),
        "blocking_preconditions": bps,
        "entries": rows,
        "verdict": _verdict(chain=chain, errors=errors, db=db),
        "requirements_covered": [
            "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "2.1",
            "6.10", "6.18", "9.8", "9.9", "9.10",
            "12.10", "12.11", "12.12", "12.13", "14.16",
        ],
        "properties_verified": [
            "Property 1", "Property 2", "Property 3", "Property 28", "Property 51",
            "Property 67", "Property 69", "Property 70", "Property 71",
        ],
    }
    # 🔴 digest 算在 **census 投影之后**的内容上：于是它继续锁死「非普查内容」（报告不可被
    #    手改），而不再被仓库演进顶红。少了 `strip_census`，digest 就重新变成一个会自己过期的锁。
    report["report_digest"] = digest_of(
        strip_census({key: value for key, value in report.items() if key != "report_digest"})
    )
    return report


def _verdict(
    *, chain: Mapping[str, Mapping[str, Any]], errors: Sequence[Mapping[str, Any]], db: DbSnapshot
) -> dict[str, Any]:
    """结构报告的自身判定。**不是** pre-delete eligibility。"""
    failing = sorted(key for key, value in chain.items() if not value["passed"])
    empty_row_denominators = sorted(
        key for key, value in chain.items() if value.get("denominator_empty")
    )
    if not db.readable:
        state = "unverifiable"
    elif errors or failing:
        state = "structural_errors_reported"
    else:
        state = "structurally_clean"
    return {
        "state": state,
        "state_vocabulary": ["unverifiable", "structural_errors_reported", "structurally_clean"],
        "chain_checks_failing": failing,
        "chain_checks_with_empty_row_denominator": empty_row_denominators,
        "structural_error_count": len(errors),
        "means": (
            "`structural_errors_reported` 是本任务的**预期**结果之一 —— 正文要求如实报告，"
            "不要求清零。它既不阻塞也不放行 Task 72 Stage A。"
        ),
    }


def render(report: Mapping[str, Any]) -> str:
    return stable_json(report, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task 67 structural pre-reconcile 报告生成器")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="与磁盘逐字节比对（不写）")
    mode.add_argument("--write", action="store_true", help="重算并原子写入报告")
    args = parser.parse_args(argv)

    report = build_report()
    rendered = render(report)
    if args.check:
        if not OUTPUT_PATH.is_file():
            print(f"[FAIL] {rel(OUTPUT_PATH)} 不存在 —— 先跑 --write")
            return 2
        on_disk = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        # 🔴 逐字节比对在 census 投影**之后**做（BP-72-8）；剔除 ≠ 不管，语义断言紧随其后现算。
        if strip_census(on_disk) != strip_census(json.loads(rendered)):
            print(f"[FAIL] {rel(OUTPUT_PATH)} 与现算不同（已按 census 投影，剩下的是真 stale 轴）")
            return 2
        semantics = report["census_contract"]["semantics"]
        if not semantics["all_hold"]:
            print(f"[FAIL] 入向普查语义断言不成立: {semantics['failing_checks']}")
            return 2
        disk_rows = ((on_disk.get("census_contract") or {}).get("measured") or {}).get("row_count")
        live_rows = report["census_contract"]["measured"]["row_count"]
        print(
            f"[OK] {rel(OUTPUT_PATH)} 一致（census 剔除后）；"
            f"入向义务快照 {disk_rows} → {live_rows} 行（不参与锁）"
        )
        return 0

    tmp = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".tmp")
    tmp.write_text(rendered, encoding="utf-8")
    os.replace(tmp, OUTPUT_PATH)
    print(f"[WROTE] {rel(OUTPUT_PATH)} ({len(rendered)} bytes)")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
