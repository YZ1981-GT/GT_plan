"""Task 67 structural pre-reconcile 报告的守卫。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 67
点名 Property：**1 / 2 / 3 / 28 / 51 / 67 / 69 / 70 / 71**；点名 AC：1.1 · 1.2 · 1.3 ·
1.4 · 1.5 · 1.6 · 1.7 · 1.8 · 2.1 · 6.10 · 6.18 · 9.8 · 9.9 · 9.10 · 12.10 · 12.11 ·
12.12 · 12.13 · 14.16。

═══ 被守的产物 ═══

* `backend/scripts/gen/generate_task67_structural_pre_reconcile.py`（生成器；本文件
  **import 它并现读它的判据函数**，不抄第二份规则）
* `backend/data/workpaper_sync_task67_structural_pre_reconcile.json`（结构报告）

═══ 本轮判据与前几轮守卫的关键差异（照抄会假绿的点）═══

1. **本任务只报告，不修复**。「没改生产代码 / 没写库」不能靠人说 —— 本文件用 **AST**
   断言生成器的每一条 SQL 字面量都以 `SELECT`/`WITH` 开头、不出现
   `session.add`/`commit`/`flush`/`begin`、`write_text` 只对 `OUTPUT_PATH`、
   `unlink`/`rmtree`/`os.remove` 一个都不出现，并且**不**调用 manifest 生成器的
   `--apply` 侧写盘函数。
2. **空集不得恒真**（假绿第⑥源）。正文点名的一长串链路校验里，10 张表实测 0 行。本文件
   逐条断言：`passed` 只由 schema 侧结构判据决定，`row_denominator=0` 必须带
   `denominator_empty=true` + 非空 `denominator_empty_note` + `owner_task`，并且
   `SchemaRequirement` 集合非空（`ChainCheck.evaluate` 自己也 fail closed）。
3. **判据不能是重言式**（教训 13）。本文件对链路检查做**反事实多臂实验**：逐臂在内存里
   把某条 UNIQUE 索引 / CHECK / trigger 的定义抹掉或改坏，对应检查必须翻红。
4. **反事实抓不到「恒真」**（教训 15）。因此再加**正向重算**：把记录里的 db 快照原样喂回
   `evaluate_chain_checks()` / `build_counters()` / `classify_entry()`，逐格比对。
5. **名单类判据必须断言包含真实目标**（教训 16）。入向义务扫描、只读 SQL 清单、
   `REQUIRED_INBOUND_TARGETS` 三处都断言具体真实路径在里面，而不只是「非空」。

用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）::

    .\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_task67_structural_pre_reconcile.py -q
"""

from __future__ import annotations

import ast
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

# ════════════════════════════════════════════════════════════════════════════
# 路径与自举
# ════════════════════════════════════════════════════════════════════════════
_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"
GEN_DIR = BACKEND / "scripts" / "gen"

for _p in (BACKEND, GEN_DIR):
    if str(_p) not in sys.path:  # pragma: no cover - import 自举
        sys.path.insert(0, str(_p))

import generate_task67_structural_pre_reconcile as GEN  # noqa: E402

REPORT_PATH = DATA / "workpaper_sync_task67_structural_pre_reconcile.json"
GENERATOR_PATH = GEN_DIR / "generate_task67_structural_pre_reconcile.py"
TASK66_PLAN_PATH = DATA / "workpaper_sync_task66_legacy_deletion_plan.json"


# ════════════════════════════════════════════════════════════════════════════
# fixtures（昂贵对象一律进程内缓存 —— 变异检验要跑几十轮）
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    assert REPORT_PATH.is_file(), (
        f"{REPORT_PATH.name} 不存在 —— 先跑生成器 `--write`；缺文件时本套件必须打红而不是 skip"
    )
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert payload.get("schema_version") == GEN.SCHEMA_VERSION
    assert payload.get("task") == GEN.OWNER_TASK
    return payload


@pytest.fixture(scope="module")
def entries(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = report["entries"]
    assert rows, "报告 `entries` 为空 —— 空清单会让本套件几乎全部恒真（假绿第⑥源）"
    return rows


@pytest.fixture(scope="module")
def live_regeneration() -> GEN.SourceRegeneration:
    """现跑一次源码重生成（node 发现器 + 内存 build_manifest）。

    module 级缓存是必须的：node 发现器一次十几秒，而变异检验要跑几十轮。
    这条 fixture 的存在理由是**判据必须落在现算上**——只读磁盘上那份记录时，
    生成器侧的变异只能被逐字节锁抓到，而「重生成是否真的成功」这条结论就没有
    自己的判据（实测 M01 首轮只命中逐字节锁）。
    """
    return GEN.regenerate_from_source()


@pytest.fixture(scope="module")
def live_report() -> dict[str, Any]:
    """现跑一次完整报告。module 级缓存，逐字节锁与 digest 判据共用同一次构造。"""
    return GEN.build_report()


@pytest.fixture(scope="module")
def snapshot(report: dict[str, Any]) -> GEN.DbSnapshot:
    """把记录里的 db 快照**还原成生产 dataclass**，供正向重算与反事实多臂使用。

    刻意用记录里的值而不是重新连库：正向重算要证明的是「记录里的结论能从记录里的输入
    重算出来」；重新连库会让「记录被手改」这类缺陷从判据里溜掉。
    """
    return _snapshot_from_record(report)


def _snapshot_from_record(report: dict[str, Any]) -> GEN.DbSnapshot:
    raw = report["database_snapshot"]
    snap = GEN.DbSnapshot(readable=bool(raw["readable"]), error=raw["error"])
    snap.row_counts = dict(raw["row_counts"])
    for attr in (
        "definition_artifacts",
        "definition_bundles",
        "null_markers",
        "entry_states",
        "representations",
        "candidates",
        "content_versions",
        "scope_index",
        "test_runs",
        "evidence_scenarios",
    ):
        setattr(snap, attr, copy.deepcopy(raw[attr]))
    # UNIQUE/CHECK/trigger 的实际定义在报告里逐条挂在 chain_checks 的
    # `schema_requirements` 上（含 definition 原文），从那里反建索引。
    for check in report["chain_checks"].values():
        for requirement in check.get("schema_requirements") or []:
            if requirement["definition"] is None:
                continue
            sink = {
                "unique_index": snap.unique_indexes,
                "check": snap.check_constraints,
                "trigger": snap.triggers,
            }[requirement["kind"]]
            sink.setdefault(requirement["table"], {})[requirement["name"]] = requirement[
                "definition"
            ]
    return snap


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else None
    return None


_AST_CACHE: dict[str, Any] = {}


def _generator_ast() -> ast.Module:
    if "tree" not in _AST_CACHE:
        _AST_CACHE["tree"] = ast.parse(GENERATOR_PATH.read_text(encoding="utf-8"))
    return _AST_CACHE["tree"]


def _generator_calls() -> tuple[set[str], set[str], set[str]]:
    """AST 抽 `(裸调用名, 点分调用路径, write_* 的接收者名)`。

    走 AST 而不是子串：文档字符串里写着 `--apply` / `commit` 是**说明文字**，不是调用点
    （教训 12；Task 62 的 BP 文案就把首版子串判据打成过假红）。
    """
    if "calls" in _AST_CACHE:
        return _AST_CACHE["calls"]
    bare: set[str] = set()
    dotted: set[str] = set()
    writes: set[str] = set()
    for node in ast.walk(_generator_ast()):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            bare.add(func.id)
        elif isinstance(func, ast.Attribute):
            bare.add(func.attr)
            full = _dotted(func)
            if full:
                dotted.add(full)
            if func.attr in {"write_text", "write_bytes"}:
                recv = func.value
                if isinstance(recv, ast.Name):
                    writes.add(recv.id)
                elif isinstance(recv, ast.Attribute):
                    writes.add(recv.attr)
                else:
                    writes.add(ast.dump(recv)[:40])
    _AST_CACHE["calls"] = (bare, dotted, writes)
    return _AST_CACHE["calls"]


def _sql_literals() -> list[str]:
    """AST 现读生成器里每一处 `sa.text(...)` 与 `_SQL_*` 常量的字符串字面量。

    🔴 不用 `strip_comments`：教训 14 记着它会把 `sa.text(\"\"\"...SQL...\"\"\")` 一起剥掉。
    """
    out: list[str] = []
    tree = _generator_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                name = _dotted(target)
                if name and name.startswith("_SQL_") and isinstance(node.value, ast.Constant):
                    out.append(str(node.value.value))
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.JoinedStr, ast.BinOp)):
            continue
        if isinstance(node, ast.Call):
            full = _dotted(node.func)
            if full in {"sa.text", "text"}:
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        out.append(arg.value)
    # `_SQL_*` 里有用括号隐式拼接的多段字符串常量（AST 里是单个 Constant，已覆盖），
    # 也有 f-string（`SELECT count(*) FROM {table}`），后者单独取。
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            rendered = "".join(
                part.value if isinstance(part, ast.Constant) else "{}"
                for part in node.values
            )
            if re.search(r"\b(select|insert|update|delete|from)\b", rendered, re.I):
                out.append(rendered)
    return out


# ════════════════════════════════════════════════════════════════════════════
# §1 守卫自检（词表封闭、分母非空、比较器真的敏感）
# ════════════════════════════════════════════════════════════════════════════


class TestGuardSelfChecks:
    def test_vocabularies_are_closed_non_empty_and_distinct(self) -> None:
        for name, vocab in (
            ("REPORTED_COUNTER_KINDS", GEN.REPORTED_COUNTER_KINDS),
            ("REQUIRED_ENTRY_FACETS", GEN.REQUIRED_ENTRY_FACETS),
            ("STRUCTURAL_ERROR_KINDS", GEN.STRUCTURAL_ERROR_KINDS),
            ("SNAPSHOT_TABLES", GEN.SNAPSHOT_TABLES),
            ("READONLY_SQL_STATEMENTS", GEN.READONLY_SQL_STATEMENTS),
            ("REQUIRED_INBOUND_TARGETS", GEN.REQUIRED_INBOUND_TARGETS),
        ):
            assert vocab, f"{name} 为空 —— 封闭词表退化成任意字符串"
            assert len(set(vocab)) == len(vocab), f"{name} 有重复取值"

    def test_the_six_reported_counters_are_exactly_the_task_text_ones(self) -> None:
        """正文逐字点名六类计数。少一类就是漏报，多一类就是自造口径。"""
        assert set(GEN.REPORTED_COUNTER_KINDS) == {
            "unadjudicated",
            "fake_bidirectional",
            "unaccepted",
            "unreachable",
            "evidence_stale",
            "planned_delete",
        }

    def test_bp_id_regex_is_task_scoped_and_rejects_the_global_form(self) -> None:
        """🔴 全局 `BP-NN` 已被 Tasks 60/61/63/64 重复占用（同号不同义）。"""
        assert GEN.BP_ID_RE.fullmatch("BP-67-1")
        assert GEN.BP_ID_RE.fullmatch("BP-67-12")
        for bad in ("BP-1", "BP-17", "BP-66-1", "BP-670-1", "bp-67-1", "BP-67-"):
            assert not GEN.BP_ID_RE.fullmatch(bad), f"{bad!r} 不该被 BP-67 正则接受"

    def test_chain_check_evaluate_fails_closed_without_schema_requirements(self) -> None:
        """没有 schema 要求的检查必须**抛错**，否则 `passed` 恒真（假绿第⑥源）。"""
        naked = GEN.ChainCheck(
            check_id="naked",
            statement="x",
            measured_by="y",
            owner_task="67",
            row_tables=("working_paper_oo_room",),
            schema_requirements=(),
        )
        db = GEN.DbSnapshot(readable=True, error=None)
        with pytest.raises(GEN.Task67GenerationError, match="没有任何 schema 要求"):
            naked.evaluate(db)

    def test_schema_requirement_detects_a_missing_fragment_not_just_presence(self) -> None:
        """反向自检：索引**存在**但少一列时必须判不满足，否则五元组判据形同虚设。"""
        db = GEN.DbSnapshot(readable=True, error=None)
        db.unique_indexes["working_paper_forcesave_request"] = {
            "uq_wpfr_idempotency": (
                "CREATE UNIQUE INDEX uq_wpfr_idempotency ON x USING btree "
                "(room_id, generation, kind, idempotency_key)"
            )
        }
        requirement = GEN.SchemaRequirement(
            "unique_index",
            "working_paper_forcesave_request",
            "uq_wpfr_idempotency",
            ("room_id", "generation", "initiated_by_participant_id", "kind", "idempotency_key"),
        )
        result = requirement.evaluate(db)
        assert result["present"] is True
        assert result["satisfied"] is False
        assert result["missing_fragments"] == ["initiated_by_participant_id"]

    def test_db_unreadable_never_reads_as_passed(self) -> None:
        """🔴 fail-open 是本 spec 记录的最贵一类缺陷。库读不到时必须判 False。"""
        db = GEN.DbSnapshot(readable=False, error="boom")
        for check in GEN.CHAIN_CHECKS:
            result = check.evaluate(db)
            assert result["passed"] is False, f"{check.check_id}: 库不可读却判通过"
            assert result["state"] == "db_unreadable"

    #: source digest 必须覆盖的四个**源码侧**事实。逐个独立断言（教训 3）：合成一条
    #: 「随便改点什么 digest 就变」的判据时，去掉其中任意一格照样绿。
    SOURCE_FACETS: tuple[tuple[str, Any], ...] = (
        ("mounts", [{"mountId": "m2"}]),
        ("profile_source", {"a": 2}),
        ("host_path", "other.vue"),
        ("document_type", "docx"),
    )
    #: reviewed 业务字段：改它们**不得**让 digest 变。
    REVIEWED_FACETS: tuple[tuple[str, Any], ...] = (
        ("capability", "bidirectional"),
        ("migration_state", "adapter_candidate"),
        ("evidence", {"review_status": "x"}),
        ("adapter_id", "excel@1"),
    )

    @staticmethod
    def _digest_base() -> dict[str, Any]:
        return {
            "entry_id": "xlsx/x",
            "mounts": [{"mountId": "m1"}],
            "profile_source": {"a": 1},
            "host_path": "h.vue",
            "document_type": "xlsx",
            "capability": "single_onlyoffice",
            "migration_state": "legacy_fake_bidirectional",
            "evidence": {"review_status": "source_inventory_reviewed"},
            "adapter_id": None,
        }

    def test_source_digest_tracks_every_source_side_facet(self) -> None:
        """🔴 逐格：任一源码侧事实变了，source digest 必须跟着变。

        少一格的后果是具体的：`profile_source` 掉出去之后，宿主换文件、readonly 绑定
        改法、inbound 引用数变化都不会触发 evidence 重跑（AC 14.16 的失效轴少一条）。

        故意不用 `parametrize`：已知坑 BP-29 —— `_mutation_kit/cli.py::_locate_want` 对
        parametrize nodeid 恒误报，而本方法是多条变异的 `want` 目标。
        """
        base = self._digest_base()
        for field, new_value in self.SOURCE_FACETS:
            changed = {**base, field: new_value}
            assert GEN.entry_source_digest(base) != GEN.entry_source_digest(changed), (
                f"改了源码侧事实 {field!r} 但 source digest 没变 ⇒ 该格不在 digest 里"
            )

    def test_entry_source_digest_ignores_reviewed_business_fields(self) -> None:
        """source digest 只随源码变。改 capability/裁决不得让 evidence 全部变 stale。"""
        base = self._digest_base()
        for field, new_value in self.REVIEWED_FACETS:
            changed = {**base, field: new_value}
            assert GEN.entry_source_digest(base) == GEN.entry_source_digest(changed), (
                f"改了 reviewed 业务字段 {field!r} 就让 source digest 变了 ⇒ "
                "任何一次裁决调整都会把已验收的 evidence 全部打成过期"
            )


# ════════════════════════════════════════════════════════════════════════════
# §2 只报告不修复：AST 断言生成器只读
# ════════════════════════════════════════════════════════════════════════════


class TestGeneratorOnlyReports:
    #: 危险的裸调用（不与常见 str/list 方法同名）。
    #: 🔴 `add` **刻意不在**这张表里：`set.add` 与 `session.add` 同名不同义，把它当裸名
    #: 禁令会把 `seen.add(marker_id)` 判成写库（首版实测踩到）。ORM 写入一律靠下面的
    #: 点分路径判据把守，并由 `test_dotted_judgement_still_catches_session_add` 反向证明
    #: 那条判据没有因此失守。同理 `commit` 不进裸名表（`git commit` 的字符串、
    #: `plan_commit` 字段名都不是调用）。
    FORBIDDEN_BARE_CALLS = frozenset(
        {
            "unlink",
            "rmtree",
            "rmdir",
            "flush",
            "provision",
            "commit_bytes",
            "finalize_candidate",
            "attach_candidate_definitions",
            "append_candidate_event",
        }
    )
    #: 危险的点分调用。
    FORBIDDEN_DOTTED_CALLS = frozenset(
        {
            "os.remove",
            "os.unlink",
            "shutil.rmtree",
            "session.add",
            "session.commit",
            "conn.commit",
            "engine.begin",
            "gen.main",
            "gen._atomic_write",
        }
    )

    def test_no_destructive_or_write_calls(self) -> None:
        bare, dotted, _ = _generator_calls()
        hit_bare = sorted(self.FORBIDDEN_BARE_CALLS & bare)
        hit_dotted = sorted(self.FORBIDDEN_DOTTED_CALLS & dotted)
        assert not hit_bare, f"生成器出现破坏性/写入裸调用: {hit_bare}"
        assert not hit_dotted, f"生成器出现破坏性/写入点分调用: {hit_dotted}"

    def test_dotted_judgement_still_catches_session_add(self) -> None:
        """反向自检：把 `add` 从裸名禁令里去掉后，点分判据必须仍然抓得住 ORM 写入。

        造两段合成源码各喂一次：`seen.add(x)`（合法，集合操作）与 `session.add(row)`
        （非法，ORM 写入）。只断言「当前生成器干净」对这条判据是否存在毫无信息量 ——
        把 `FORBIDDEN_DOTTED_CALLS` 整个删空，那种断言照样绿（本 spec 记录的假绿第②源）。
        """
        legal = ast.parse("seen = set()\nseen.add('x')\n")
        illegal = ast.parse("session.add(row)\nsession.commit()\n")

        def dotted_of(tree: ast.Module) -> set[str]:
            out: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    full = _dotted(node.func)
                    if full:
                        out.add(full)
            return out

        assert not (self.FORBIDDEN_DOTTED_CALLS & dotted_of(legal)), (
            "`seen.add()` 被判成写库 ⇒ 判据把集合操作与 ORM 写入混为一谈"
        )
        caught = self.FORBIDDEN_DOTTED_CALLS & dotted_of(illegal)
        assert {"session.add", "session.commit"} <= caught, (
            f"`session.add` / `session.commit` 没被点分判据抓住，实得 {sorted(caught)} ⇒ "
            "去掉裸名 `add` 之后写库禁令失守了"
        )

    def test_write_text_only_targets_the_report(self) -> None:
        _, _, writes = _generator_calls()
        assert writes == {"tmp"}, (
            f"`write_text` 的接收者应恰为报告的临时文件变量 `tmp`，实得 {sorted(writes)}"
        )
        source = GENERATOR_PATH.read_text(encoding="utf-8")
        assert "os.replace(tmp, OUTPUT_PATH)" in source, (
            "原子写入必须落到 OUTPUT_PATH —— 换成别的目标就等于本任务在改别人的文件"
        )

    def test_every_sql_literal_is_read_only(self) -> None:
        """🔴 本任务要查一长串表，因此**必须**逐条证明只读，而不是「我没写 INSERT」。"""
        literals = _sql_literals()
        assert len(literals) >= len(GEN.READONLY_SQL_STATEMENTS), (
            f"AST 只抽到 {len(literals)} 条 SQL 字面量，少于声明的 "
            f"{len(GEN.READONLY_SQL_STATEMENTS)} 条 —— 抽取器退化了"
        )
        forbidden = re.compile(
            r"\b(insert|update|delete|truncate|drop|alter|create|grant|copy)\b", re.I
        )
        for sql in literals:
            head = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
            assert head in {"SELECT", "WITH"}, f"SQL 不以 SELECT/WITH 开头: {sql[:80]!r}"
            assert not forbidden.search(sql), f"SQL 含写操作关键字: {sql[:80]!r}"

    def test_the_declared_readonly_sql_list_contains_the_real_targets(self) -> None:
        """教训 16：名单类判据必须断言「包含那个真实目标」，不只是非空。"""
        joined = "\n".join(GEN.READONLY_SQL_STATEMENTS)
        for needle in (
            "pg_get_indexdef",
            "pg_get_constraintdef",
            "pg_get_triggerdef",
            "working_paper_sync_definition_bundle",
            "working_paper_representation_upgrade_candidate",
            "working_paper_sync_scope_index",
        ):
            assert needle in joined, f"只读 SQL 清单里没有真实目标 {needle!r}"

    def test_the_disk_manifest_is_not_rewritten(self, report: dict[str, Any]) -> None:
        """正文只授权报告。磁盘 manifest 的 sha256 必须与报告记录的一致。"""
        import hashlib

        actual = hashlib.sha256(GEN.MANIFEST_PATH.read_bytes()).hexdigest()
        assert report["inputs"]["entry_manifest"]["sha256"] == actual, (
            "磁盘 manifest 与报告记录的 sha256 不符 —— 有人（可能是本任务）改过它"
        )
        assert report["source_regeneration"]["disk_manifest_is_readonly_input"] is True

    def test_task66_plan_is_an_untouched_input(self, report: dict[str, Any]) -> None:
        import hashlib

        actual = hashlib.sha256(TASK66_PLAN_PATH.read_bytes()).hexdigest()
        assert report["inputs"]["task66_deletion_plan"]["sha256"] == actual
        plan = json.loads(TASK66_PLAN_PATH.read_text(encoding="utf-8"))
        assert report["inputs"]["task66_deletion_plan"]["plan_commit"] == plan["plan_commit"]


# ════════════════════════════════════════════════════════════════════════════
# §3 五边锁：source / manifest / registry / database / deletion-plan
# ════════════════════════════════════════════════════════════════════════════


class TestFiveWayLock:
    def test_all_five_sides_are_declared_and_non_empty(self, report: dict[str, Any]) -> None:
        lock = report["five_way_lock"]
        assert set(lock) == {
            "source_side",
            "manifest_side",
            "registry_side",
            "database_side",
            "deletion_plan_side",
        }
        for side, statement in lock.items():
            assert statement and len(statement) > 20, f"{side} 的说明是空话"

    def test_source_regeneration_reports_the_real_drift(
        self, report: dict[str, Any], live_regeneration: GEN.SourceRegeneration
    ) -> None:
        """本轮实测：overlay 的 approved digest 已过期 ⇒ 必须报出来，不得静默对齐。

        两侧都断言：记录侧（磁盘 JSON）+ **现算侧**（`regenerate_from_source()`）。
        只查记录时，把内存补丁去掉（重生成必然失败）这类改动只能被逐字节锁抓到，
        「重生成真的成功了」这条结论就没有自己的判据。
        """
        regen = report["source_regeneration"]
        assert regen["approved_source_digest"]
        assert regen["current_source_digest"]
        if regen["digests_agree"]:
            pytest.fail(
                "overlay 的 approved_source_digest 已与当前源码一致 —— 若复核方真的更新过它，"
                "请同步解除 BP-67-1 并更新本判据；本轮实测是不一致"
            )
        assert regen["mount_id_only_in_source_count"] > 0
        assert regen["mount_id_only_on_disk_count"] > 0
        assert regen["rebuild_error"] is None, (
            f"记录里的内存重算失败: {regen['rebuild_error']} —— 报告的 manifest 侧全部降级"
        )
        # ── 现算侧
        assert live_regeneration.rebuild_error is None, (
            f"现算重生成失败: {live_regeneration.rebuild_error} —— "
            "「从最终源码重新生成 mounts 与 source-backed manifest」这条正文要求没有兑现"
        )
        assert live_regeneration.rebuilt is not None
        assert live_regeneration.digests_agree is False
        assert live_regeneration.rebuilt_manifest_digest == regen["rebuilt_manifest_digest"]
        assert len(live_regeneration.rebuilt["entries"]) == len(report["entries"])

    def test_entry_set_survives_the_rebuild(self, report: dict[str, Any], entries: list[dict[str, Any]]) -> None:
        """重算后 entry 集合必须仍然逐条可比 —— 否则逐 entry 核对无从谈起。"""
        assert all(row["source_digest"]["rebuild_available"] for row in entries)
        changed = [row["entry_id"] for row in entries if row["source_digest"]["changed"]]
        assert changed, (
            "没有一条 entry 的 source digest 变化，却报告 sourceDigest 漂移 —— "
            "两个结论互相矛盾，说明 per-entry digest 没在度量源码"
        )
        assert len(changed) < len(entries), (
            "全部 entry 都变了 ⇒ per-entry digest 很可能掺进了全局量（如 manifest_digest）"
        )

    def test_registry_landing_covers_every_manifest_entry(
        self, report: dict[str, Any], entries: list[dict[str, Any]]
    ) -> None:
        """没有 entry 被静默跳过（registry 侧的 Property 3 分母完整性）。"""
        assert report["production_landings"]["registration_plan_size"] == len(entries)
        unplanned = [row["entry_id"] for row in entries if not row["registry_landing"]["planned"]]
        assert not unplanned, f"这些 entry 在注册计划里没有落点: {unplanned[:5]}"

    def test_deletion_plan_landing_is_two_way(
        self, report: dict[str, Any], entries: list[dict[str, Any]]
    ) -> None:
        """双向：清册引用的 entry_id 必须都在 manifest 里；manifest entry 的落点必须可查。"""
        plan = json.loads(TASK66_PLAN_PATH.read_text(encoding="utf-8"))
        manifest_ids = {row["entry_id"] for row in entries}
        referenced: set[str] = set()
        for item in plan["items"]:
            referenced.update((item.get("replacement") or {}).get("manifest_entry_ids") or [])
        assert referenced, "清册一个 manifest_entry_id 都没引用 —— 双向核对的一侧为空"
        dangling = sorted(referenced - manifest_ids)
        assert not dangling, f"清册引用了 manifest 里不存在的 entry: {dangling[:5]}"
        recorded = {
            row["entry_id"] for row in entries if row["deletion_plan_landing"]["has_landing"]
        }
        assert recorded == referenced, (
            f"报告记的落点与清册现算不符：多 {sorted(recorded - referenced)[:5]} "
            f"少 {sorted(referenced - recorded)[:5]}"
        )

    def test_scenario_probe_is_carried_over_verbatim_and_marked_as_a_probe(
        self, report: dict[str, Any], entries: list[dict[str, Any]]
    ) -> None:
        """Task 66 的 required scenario 集合是**探针**（BP-66-3）。不得当已验收用。"""
        plan = json.loads(TASK66_PLAN_PATH.read_text(encoding="utf-8"))
        sets = plan["manifest_required_scenario_sets"]
        assert sets, "清册的 required scenario 集合为空"
        for row in entries:
            probe = row["scenario_profile"]["required_scenario_probe"]
            assert probe["is_probe_not_verdict"] is True
            recorded = sets.get(row["entry_id"]) or {}
            assert probe["status"] == recorded.get("status"), row["entry_id"]
            assert probe["scenario_count"] == len(recorded.get("scenario_ids") or []), row["entry_id"]


# ════════════════════════════════════════════════════════════════════════════
# §4 逐 entry 十面齐备 + 父入口不重复计数
# ════════════════════════════════════════════════════════════════════════════


class TestPerEntryFacets:
    def test_every_entry_carries_all_ten_facets(self, entries: list[dict[str, Any]]) -> None:
        for row in entries:
            missing = [facet for facet in GEN.REQUIRED_ENTRY_FACETS if facet not in row]
            assert not missing, f"{row['entry_id']} 缺核对面 {missing}"

    def test_parent_duplicates_are_never_in_the_primary_denominator(
        self, entries: list[dict[str, Any]]
    ) -> None:
        """🔴 父入口不重复计数 —— 独立判据（不与其他 facet 合成一条）。"""
        offenders = [
            row["entry_id"]
            for row in entries
            if row["parent_entry_id"] is not None and row["counted_in_denominator"]
        ]
        assert not offenders, f"parent 重复入口进了主分母: {offenders[:5]}"
        assert any(row["parent_entry_id"] is not None for row in entries), (
            "一条 parent 重复入口都没有 ⇒ 本判据分母为空、恒真"
        )
        for row in entries:
            assert row["counted_in_denominator"] == bool(row["independent_entry"])
            assert row["counted_in_denominator_why"]

    def test_the_dual_denominator_hides_nothing(self, report: dict[str, Any]) -> None:
        """🔴 主口径必须与副口径同时给出，差集逐 entry 列名。

        实测 `xlsx/gt-g6-other-bond-ecl` 既 `capability=unreachable` 又是 parent 重复入口
        ⇒ 主口径 `unreachable=0`。只报主口径会让这条真实 entry 从报告里消失。
        """
        counters = report["counters"]
        primary = counters["reported_by_task_text"]
        overall = counters["reported_by_task_text_over_all_entries"]
        deltas = counters["parent_duplicate_only_deltas"]
        ids = counters["parent_duplicate_only_entry_ids"]
        assert set(primary) == set(overall) == set(deltas) == set(ids) == set(
            GEN.REPORTED_COUNTER_KINDS
        )
        for kind in GEN.REPORTED_COUNTER_KINDS:
            assert overall[kind] - primary[kind] == deltas[kind], kind
            assert len(ids[kind]) == deltas[kind], kind
        assert deltas["unreachable"] == 1 and ids["unreachable"], (
            "那条既 unreachable 又是 parent 重复入口的 entry 不见了 —— "
            "若它真的被删了/改成独立了，请同步更新本判据"
        )

    def test_profile_drift_entries_are_named_not_swallowed(
        self, entries: list[dict[str, Any]]
    ) -> None:
        """5 条 `single_html` + `exclusive` 的矛盾必须逐条出现在报告里（BP-67-3）。"""
        drifted = [
            row["entry_id"]
            for row in entries
            if row["scenario_profile"]["capability_consistency"] not in (None, "consistent")
        ]
        assert drifted, (
            "一条 profile 漂移都没有 —— 若真的修好了，请同步解除 BP-67-3 并更新本判据"
        )
        for entry_id in drifted:
            row = next(r for r in entries if r["entry_id"] == entry_id)
            assert row["scenario_profile"]["capability_error"], f"{entry_id}: 判漂移却给不出原因"
            assert (
                row["scenario_profile"]["required_scenario_probe"]["status"] != "derived"
            ), f"{entry_id}: profile 矛盾却声称 required scenario 已推导"

    def test_descriptor_and_room_facets_come_from_production_observers(
        self, entries: list[dict[str, Any]]
    ) -> None:
        """descriptor/room 事实必须是**观测**到的，不是空对象占位。"""
        observed_room = [row for row in entries if row["descriptor_room_config"]["room"]]
        assert len(observed_room) == len(entries), "有 entry 的 room 事实是空的"
        keys = {"shared_doc_key", "doc_key_includes_mtime", "participant_lease"}
        for row in entries:
            assert keys <= set(row["descriptor_room_config"]["room"]), row["entry_id"]
        with_descriptor = [
            row for row in entries if (row["descriptor_room_config"]["descriptor"] or {}).get("observed")
        ]
        assert with_descriptor, (
            "没有任何 entry 观测到 launch descriptor ⇒ descriptor 面的判据分母为空"
        )

    def test_evidence_rerun_axes_use_the_production_stale_vocabulary(
        self, entries: list[dict[str, Any]]
    ) -> None:
        """重跑轴必须取自 `evidence.StaleReason`，不得自造词表（否则与 Task 29/39 两套口径）。"""
        from app.services.workpaper_sync.evidence import StaleReason

        allowed = {member.value for member in StaleReason}
        seen: set[str] = set()
        for row in entries:
            axes = row["evidence_rerun_axes"]
            assert axes, f"{row['entry_id']}: 重跑轴为空 —— 供给全缺时不可能一条都不用重跑"
            unknown = sorted(set(axes) - allowed)
            assert not unknown, f"{row['entry_id']}: 自造的 stale 码 {unknown}"
            seen.update(axes)
        assert len(seen) >= 3, f"全部 entry 合起来只用了 {sorted(seen)} —— 轴推导疑似退化"

    def test_evidence_rerun_axes_are_derived_live_not_just_recorded(self) -> None:
        """🔴 逻辑级：重跑轴必须由输入派生。

        只查记录时，把 `evidence_rerun_axes()` 改成返回 `[]` 只会被逐字节锁抓到
        （实测 M31 首轮如此）。这里造合成输入直接跑，并逐轴绑定到一个可单独改变的事实。
        """
        from app.services.workpaper_sync.evidence import StaleReason

        row, _ = _synthetic_row("xlsx/x", independent=True, source_changed=True)
        axes = GEN.evidence_rerun_axes(row, _synthetic_regeneration(agree=False))
        assert axes, "合成输入下重跑轴为空 ⇒ 该函数被短路，Task 70 会以为无需重跑"
        assert StaleReason.manifest_source_digest_changed.value in axes
        assert StaleReason.scenario_profile_changed.value in axes, (
            "该 entry 的 source digest 变了却没带 scenario profile 轴"
        )
        assert StaleReason.definition_bundle_changed.value in axes
        assert StaleReason.authority_model_changed.value in axes

        # 反向：source 未变 + digest 一致时，前两轴必须消失（剩下的仍由供给缺失驱动）。
        unchanged, _ = _synthetic_row("xlsx/y", independent=True, source_changed=False)
        quiet = GEN.evidence_rerun_axes(unchanged, _synthetic_regeneration(agree=True))
        assert StaleReason.manifest_source_digest_changed.value not in quiet, (
            "源码与 overlay 一致时仍报 manifest digest 轴 ⇒ 该轴与事实无关（重言式）"
        )
        assert StaleReason.scenario_profile_changed.value not in quiet


# ════════════════════════════════════════════════════════════════════════════
# §5 链路检查：空集不得恒真 + 反事实多臂 + 正向重算
# ════════════════════════════════════════════════════════════════════════════


class TestChainChecksAreMeasured:
    def test_declared_checks_and_reported_checks_are_the_same_set(
        self, report: dict[str, Any]
    ) -> None:
        declared = {check.check_id for check in GEN.CHAIN_CHECKS}
        reported = set(report["chain_checks"])
        assert declared == reported, (
            f"只声明未报告 {sorted(declared - reported)}；只报告未声明 {sorted(reported - declared)}"
        )
        assert len(declared) >= 14, f"链路检查只有 {len(declared)} 条 —— 正文点名的项没有逐条落地"

    def test_every_check_names_a_statement_a_measurement_and_an_owner(
        self, report: dict[str, Any]
    ) -> None:
        for check_id, value in report["chain_checks"].items():
            assert value["statement"] and len(value["statement"]) > 20, check_id
            assert value["measured_by"] and len(value["measured_by"]) > 10, check_id
            assert value["owner_task"], check_id

    def test_empty_row_denominators_are_declared_never_silently_passed(
        self, report: dict[str, Any], snapshot: GEN.DbSnapshot
    ) -> None:
        """🔴 假绿第⑥源的正面判据：0 行必须显式说明「通过只来自 schema 侧」。

        记录侧 + **现算侧**都断言：只查记录时，把说明字段改成恒 `None`、把
        `verified_on_rows` 改成恒真这类改动只会被逐字节锁抓到（实测 M08/M09 首轮如此），
        而「空分母被如实标注」这条结论就没有自己的判据。
        """
        for source, checks in (
            ("记录", report["chain_checks"]),
            ("现算", GEN.evaluate_chain_checks(snapshot)),
        ):
            empty = [
                (check_id, value)
                for check_id, value in checks.items()
                if value["denominator_empty"]
            ]
            assert empty, (
                f"{source}侧一条空分母都没有 —— 若供给真的补齐了，请同步更新本判据"
                "（本轮实测 10 条为空）"
            )
            for check_id, value in empty:
                assert value["row_denominator"] == 0, f"{source}/{check_id}"
                assert value["denominator_empty_note"], f"{source}/{check_id}: 空分母却不解释"
                assert "schema" in value["denominator_empty_note"], f"{source}/{check_id}"
                assert value["verified_on_rows"] is False, (
                    f"{source}/{check_id}: 0 行却声称在行上验过"
                )
                assert value["owner_task"], f"{source}/{check_id}: 空分母却没有 owner"

    def test_passed_is_decided_by_schema_not_by_the_empty_row_set(
        self, report: dict[str, Any]
    ) -> None:
        for check_id, value in report["chain_checks"].items():
            if value["state"] != "measured":
                continue
            expected = value["schema_satisfied"] and not value["row_violations"]
            assert value["passed"] == expected, check_id
            assert value["schema_requirements"], f"{check_id}: schema 要求为空"
            for requirement in value["schema_requirements"]:
                assert requirement["present"], (
                    f"{check_id}: {requirement['kind']} {requirement['table']}."
                    f"{requirement['name']} 在库里不存在 —— 判据落空"
                )

    def test_the_forcesave_five_tuple_is_checked_column_by_column(
        self, report: dict[str, Any]
    ) -> None:
        """教训 16 的复用：不能只要求索引存在，必须点名那五列。"""
        check = report["chain_checks"]["forcesave_five_tuple_and_frozen_fingerprint"]
        requirement = next(
            item
            for item in check["schema_requirements"]
            if item["name"] == "uq_wpfr_idempotency"
        )
        definition = requirement["definition"]
        for column in (
            "room_id",
            "generation",
            "initiated_by_participant_id",
            "kind",
            "idempotency_key",
        ):
            assert column in definition, f"五元键少了 {column}"
        assert requirement["satisfied"] and not requirement["missing_fragments"]

    def test_checks_recompute_from_the_recorded_snapshot(
        self, report: dict[str, Any], snapshot: GEN.DbSnapshot
    ) -> None:
        """🔴 教训 15：反事实多臂只能证明「非重言」，抓不到「恒真」。

        把记录里的 db 快照原样喂回 `evaluate_chain_checks()` 逐格比对 —— 这是「某条约束
        被悄悄改成 `passed=True`」的唯一捕手。
        """
        live = GEN.evaluate_chain_checks(snapshot)
        assert set(live) == set(report["chain_checks"])
        for check_id, value in live.items():
            recorded = report["chain_checks"][check_id]
            assert value["passed"] == recorded["passed"], (
                f"{check_id}: 现算 passed={value['passed']} 与记录 {recorded['passed']} 不符"
            )
            assert value["schema_satisfied"] == recorded["schema_satisfied"], check_id
            assert value["row_denominator"] == recorded["row_denominator"], check_id
            assert len(value["row_violations"]) == len(recorded["row_violations"]), check_id

    #: 反事实臂：`(check_id, kind, table, name)`。每条链路检查至少一臂。
    COUNTERFACTUAL_ARMS: tuple[tuple[str, str, str, str], ...] = (
        (
            "forcesave_five_tuple_and_frozen_fingerprint",
            "unique_index",
            "working_paper_forcesave_request",
            "uq_wpfr_idempotency",
        ),
        (
            "application_to_primary_operation_one_to_one",
            "unique_index",
            "working_paper_sync_operation",
            "uq_wpso_application",
        ),
        (
            "delivery_durable_at_owner_constraint",
            "check",
            "working_paper_callback_delivery",
            "ck_wpcd_durable_exactly_one_owner",
        ),
        (
            "scope_tombstone_exists_and_retired_is_not_reusable",
            "trigger",
            "working_paper_sync_scope_index",
            "trg_wpssi_no_delete",
        ),
        (
            "close_authorization_stale_successor_recovery_required",
            "check",
            "working_paper_oo_close_intent",
            "ck_wpoci_state",
        ),
        (
            "typed_null_marker_rules",
            "check",
            "working_paper_sync_definition_null_marker",
            "ck_wpsnm_versioned_id",
        ),
        (
            "candidate_non_current_and_non_resolvable",
            "check",
            "working_paper_artifact",
            "ck_wpa_candidate_never_published",
        ),
        (
            "content_version_scope_uses_opaque_uuid_only",
            "unique_index",
            "working_paper_content_version",
            "uq_wpcv_wp_revision",
        ),
        (
            "chain_child_kind_state_digest",
            "trigger",
            "working_paper_sync_definition_bundle",
            "trg_wpsdb_slots",
        ),
        (
            "projection_contract_requires_approved_child",
            "check",
            "working_paper_sync_definition_artifact",
            "ck_wpsda_authority_model_type",
        ),
        (
            "application_sequence_vs_room_canonical_fence",
            "check",
            "working_paper_content_application",
            "ck_wpca_effective_ge_origin",
        ),
        (
            "duplicate_direct_canonical_and_zero_stranded_shell",
            "check",
            "working_paper_sync_operation",
            "ck_wpso_duplicate_shape",
        ),
        (
            "application_and_engine_are_durable_only",
            "check",
            "working_paper_artifact",
            "ck_wpa_durable_quarantine_exclusive",
        ),
        (
            "pure_upgrade_keeps_revision_and_history_freezes_bundle",
            "trigger",
            "working_paper_content_version",
            "trg_wpcv_immutable",
        ),
    )

    def test_every_chain_check_has_at_least_one_counterfactual_arm(self) -> None:
        """分母完整性：一条检查没有反事实臂 = 它是否重言式无人验证。"""
        armed = {arm[0] for arm in self.COUNTERFACTUAL_ARMS}
        declared = {check.check_id for check in GEN.CHAIN_CHECKS}
        assert declared == armed, (
            f"缺反事实臂的检查 {sorted(declared - armed)}；臂指向不存在的检查 "
            f"{sorted(armed - declared)}"
        )

    def test_counterfactual_arms_flip_the_check(self, snapshot: GEN.DbSnapshot) -> None:
        """🔴 教训 13：判据不能是重言式。逐臂在**内存里**把该约束抹掉，检查必须翻红。

        这不是变异脚本的替代品 —— 它证明的是「每条链路检查都在度量某个可改变的
        结构事实」，而不是「某条恒真的事实被报告重复陈述了一遍」。

        故意不用 `parametrize`：已知坑 BP-29 —— `_mutation_kit/cli.py::_locate_want` 对
        parametrize nodeid 恒误报，而本方法是变异 M07 的 `want` 目标。
        """
        baseline = GEN.evaluate_chain_checks(snapshot)
        for check_id, kind, table, name in self.COUNTERFACTUAL_ARMS:
            assert baseline[check_id]["passed"] is True, (
                f"{check_id} 基线就没过 —— 对照组必须先过（教训 5）"
            )
            mutated_snapshot = copy.deepcopy(snapshot)
            sink = {
                "unique_index": mutated_snapshot.unique_indexes,
                "check": mutated_snapshot.check_constraints,
                "trigger": mutated_snapshot.triggers,
            }[kind]
            removed = (sink.get(table) or {}).pop(name, None)
            assert removed is not None, f"反事实臂的前提不存在: {kind} {table}.{name}"
            mutated = GEN.evaluate_chain_checks(mutated_snapshot)
            assert mutated[check_id]["passed"] is False, (
                f"抹掉 {kind} {table}.{name} 后 {check_id} 仍然通过 ⇒ 该判据度量的是别的东西"
            )

    def test_row_level_violation_functions_are_all_wired(self) -> None:
        """声明的 `row_violation_fn` 必须都能在函数表里查到（不能是死字符串）。"""
        declared = {
            check.row_violation_fn for check in GEN.CHAIN_CHECKS if check.row_violation_fn
        }
        assert declared, "没有一条检查做行级现算 ⇒ 全部只靠 schema，行侧完全没判据"
        assert declared <= set(GEN.ROW_VIOLATION_FUNCTIONS), sorted(
            declared - set(GEN.ROW_VIOLATION_FUNCTIONS)
        )
        for name in sorted(declared):
            assert callable(GEN.ROW_VIOLATION_FUNCTIONS[name])

    def test_marker_violations_really_detect_a_tampered_digest(
        self, snapshot: GEN.DbSnapshot
    ) -> None:
        """反向自检：typed null marker 的 digest 判据必须对篡改敏感。

        🔴 三条**分开**断言（教训 3）。首版只造了「全零 hash」一种篡改，于是
        `sha256 != marker_digest(slot)` 那条分支被短路时判据照样绿（实测 M10 判 GREEN）——
        因为全零同时命中另一条独立分支。现在「合法形态但取值错」单独占一臂。
        """
        assert snapshot.null_markers, "marker 行为空 ⇒ 本判据分母为空、恒真"
        assert GEN.marker_violations(snapshot) == []

        # ① 全零 hash（AC 6.19 明文禁止的形态之一）
        zeroed = copy.deepcopy(snapshot)
        zeroed.null_markers[0]["sha256"] = "0" * 64
        assert any("全零" in v["why"] for v in GEN.marker_violations(zeroed)), (
            "全零 hash 没被独立点名"
        )

        # ② 形态合法但取值与 `marker_digest()` 现算不符 —— 只有 digest 比对能抓到
        wrong = copy.deepcopy(snapshot)
        original = wrong.null_markers[0]["sha256"]
        wrong.null_markers[0]["sha256"] = ("a" if original[0] != "a" else "b") + original[1:]
        wrong_violations = GEN.marker_violations(wrong)
        assert any("digest" in v["why"] for v in wrong_violations), (
            f"改掉 marker digest 的一个字符后判据没点名 digest 不符，实得 {wrong_violations} ⇒ "
            "`marker_digest()` 现算比对被短路了"
        )

        # ③ 生产 registry 声明了而库里缺行
        missing = copy.deepcopy(snapshot)
        dropped = missing.null_markers.pop(0)
        assert any(
            v["marker_id"] == dropped["marker_id"] and "缺行" in v["why"]
            for v in GEN.marker_violations(missing)
        ), "registry 声明的 marker 在库里缺行时没被点名"

    def test_projection_child_violations_detect_a_marker_substitution(
        self, snapshot: GEN.DbSnapshot
    ) -> None:
        """projection_contract bundle 用 typed null marker 顶替必需 child 必须被抓到。"""
        assert snapshot.definition_bundles, "bundle 行为空 ⇒ 本判据分母为空、恒真"
        assert GEN.projection_child_violations(snapshot) == []
        tampered = copy.deepcopy(snapshot)
        by_id = {row["id"]: row for row in tampered.definition_artifacts}
        target = next(
            bundle
            for bundle in tampered.definition_bundles
            if (by_id.get(bundle["authority_model_definition_id"]) or {}).get(
                "authority_model_type"
            )
            == "projection_contract"
        )
        target["contract_slot_type"] = "contract:none:v1"
        target["contract_slot_ref"] = "marker:contract:none:v1"
        violations = GEN.projection_child_violations(tampered)
        assert violations, "projection bundle 的 contract child 被 marker 顶替却没红"
        assert any("typed null marker" in v["why"] for v in violations)


# ════════════════════════════════════════════════════════════════════════════
# §6 计数与结构错误：正向重算 + 逐类独立
# ════════════════════════════════════════════════════════════════════════════


def _synthetic_row(
    entry_id: str,
    *,
    independent: bool,
    capability: str = "single_onlyoffice",
    migration_state: str = "adapter_candidate",
    html_store: str = "resolved",
    source_changed: bool = False,
    published: bool = False,
    test_runs: int = 0,
    pending_delete_items: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """造一条最小 entry row + 对应的 manifest entry，供逻辑级反向自检使用。

    这些合成输入是「六类计数 / 双分母」判据的**独立**信息源：只比对磁盘记录时，
    生成器里的派生分支被短路只会被逐字节锁抓到（实测 M13~M17 首轮如此），
    而「短路了什么」就没有任何判据说得出来。
    """
    row = {
        "entry_id": entry_id,
        "document_type": "xlsx",
        "capability": capability,
        "migration_state": migration_state,
        "independent_entry": independent,
        "parent_entry_id": None if independent else "xlsx/parent",
        "counted_in_denominator": independent,
        "counted_in_denominator_why": "synthetic",
        "source_digest": {
            "disk": "d",
            "rebuilt_from_source": "r" if source_changed else "d",
            "changed": source_changed,
            "rebuild_available": True,
        },
        "editable": True,
        "editability": "editable",
        "room_model": "shared",
        "scenario_profile": {
            "profile_id": "p",
            "digest": "x",
            "capability_consistency": "consistent",
            "capability_error": None,
            "required_scenario_probe": {
                "status": "derived",
                "error_type": None,
                "scenario_count": 1,
                "set_digest": "s",
                "is_probe_not_verdict": True,
            },
        },
        "registry_landing": {
            "planned": True,
            "registrable": False,
            "contract_id": None,
            "provider_module": None,
            "blocked_reason": "synthetic",
            "adapter_id_in_manifest": None,
            "actually_registered": False,
        },
        "host_dom_landing": {"host_path": "h.vue", "mount_count": 1, "mounts": []},
        "descriptor_room_config": {"descriptor": None, "room": None},
        "authority_contract_bundle_chain": {"approved_bundle_bound_to_entry": False},
        "candidate_published_representation": {
            "entry_state_rows": 1 if published else 0,
            "representation_rows": 1 if published else 0,
            "candidate_rows": 0,
            "candidate_states": [],
            "published": published,
        },
        "deletion_plan_landing": {
            "referenced_by_item_ids": [],
            "referenced_item_count": pending_delete_items,
            "pending_delete_item_count": pending_delete_items,
            "has_landing": pending_delete_items > 0,
        },
        "evidence": {
            "test_run_rows": test_runs,
            "scenario_rows": 0,
            "manifest_review_status": None,
            "browser_case": None,
            "contract_test": None,
            "legacy_reasons": [],
        },
    }
    manifest_entry = {
        "entry_id": entry_id,
        "capability": capability,
        "migration_state": migration_state,
        "html_store": html_store,
        "independent_entry": independent,
    }
    row["verdicts"] = GEN.classify_entry(row, manifest_entry)
    return row, manifest_entry


def _empty_landings() -> GEN.ProductionLandings:
    return GEN.ProductionLandings(
        plan_by_entry={},
        registration_count=0,
        profile_by_entry={},
        supply_by_entry={},
        delivered_contracts=[],
        pending_engine_adapters=[],
        allowed_provider_modules=[],
        opaque_lanes=[],
    )


def _empty_plan66() -> GEN.Task66PlanFacts:
    return GEN.Task66PlanFacts(
        payload={
            "task": "66",
            "plan_commit": "0" * 40,
            "items": [],
            "replacement_registry": [],
            "manifest_required_scenario_sets": {},
        }
    )


def _synthetic_regeneration(*, agree: bool) -> GEN.SourceRegeneration:
    return GEN.SourceRegeneration(
        approved_source_digest="a" * 64,
        current_source_digest=("a" if agree else "b") * 64,
        disk_manifest_digest="c" * 64,
        rebuilt_manifest_digest="c" * 64,
        rebuilt={"entries": []},
        disk={"entries": []},
        rebuild_error=None,
        mount_ids_only_on_disk=(),
        mount_ids_only_in_source=(),
    )


class TestCountersAndStructuralErrors:
    def test_classify_entry_pins_each_verdict_to_its_own_fact(self) -> None:
        """🔴 逻辑级反向自检：六类判定各自绑定到一个可单独改变的事实。

        只把记录喂回 `classify_entry()` 时，函数被短路后两侧都用同一个被短路的函数
        ⇒ 恒等（教训 15 的镜像）。合成输入是唯一能分辨「短路了哪一条」的信息源。
        """
        clean, _ = _synthetic_row("xlsx/clean", independent=True, published=True, test_runs=1)
        assert clean["verdicts"]["unadjudicated"] is False
        assert clean["verdicts"]["fake_bidirectional"] is False
        assert clean["verdicts"]["unaccepted"] is False
        assert clean["verdicts"]["unreachable"] is False
        assert clean["verdicts"]["planned_delete"] is False

        unadjudicated, _ = _synthetic_row(
            "xlsx/u", independent=True, html_store="unresolved", published=True, test_runs=1
        )
        assert unadjudicated["verdicts"]["unadjudicated"] is True

        fake, _ = _synthetic_row(
            "xlsx/f",
            independent=True,
            migration_state="legacy_fake_bidirectional",
            published=True,
            test_runs=1,
        )
        assert fake["verdicts"]["fake_bidirectional"] is True

        unaccepted, _ = _synthetic_row("xlsx/a", independent=True, published=False, test_runs=0)
        assert unaccepted["verdicts"]["unaccepted"] is True, (
            "没有 published representation / test run 的 entry 必须判未验收"
        )

        unreachable, _ = _synthetic_row(
            "xlsx/r", independent=True, capability="unreachable", published=True, test_runs=1
        )
        assert unreachable["verdicts"]["unreachable"] is True

        planned, _ = _synthetic_row(
            "xlsx/p", independent=True, published=True, test_runs=1, pending_delete_items=3
        )
        assert planned["verdicts"]["planned_delete"] is True, (
            "清册里有 pending_delete 项引用它，却没判 planned_delete"
        )

    def test_stale_requires_evidence_to_exist_first(self) -> None:
        """🔴 「过期」与「从未验收」是两件事，正文分开点名。

        源码变了但**没有任何 evidence** 的 entry 必须判 `unaccepted` 而**不是** stale；
        只有真有 run 行时源码变化才算 stale。
        """
        no_evidence, _ = _synthetic_row("xlsx/ns", independent=True, source_changed=True)
        assert no_evidence["verdicts"]["evidence_stale"] is False, (
            "没有任何 test run 却判 stale ⇒ 报告会声称「有 evidence 但过期了」，"
            "而真相是根本没有 evidence"
        )
        assert no_evidence["verdicts"]["evidence_stale_is_measurable"] is False
        assert no_evidence["verdicts"]["unaccepted"] is True

        with_evidence, _ = _synthetic_row(
            "xlsx/ws", independent=True, source_changed=True, published=True, test_runs=1
        )
        assert with_evidence["verdicts"]["evidence_stale"] is True
        assert with_evidence["verdicts"]["evidence_stale_is_measurable"] is True

        fresh, _ = _synthetic_row(
            "xlsx/fr", independent=True, source_changed=False, published=True, test_runs=1
        )
        assert fresh["verdicts"]["evidence_stale"] is False

    def test_build_entry_rows_derives_the_denominator_flag_from_independence(self) -> None:
        """🔴 逻辑级：`counted_in_denominator` 必须由 `independent_entry` 派生。

        记录侧判据（读磁盘 JSON）对这一格恒不敏感 —— 记录不会因为生成器被改而变。
        这里造两条最小 manifest entry 直接跑 `build_entry_rows()`。
        """
        def _disk_entry(entry_id: str, *, independent: bool) -> dict[str, Any]:
            return {
                "entry_id": entry_id,
                "document_type": "xlsx",
                "capability": "single_onlyoffice",
                "migration_state": "adapter_candidate",
                "independent_entry": independent,
                "parent_entry_id": None if independent else "xlsx/p",
                "html_store": "resolved",
                "adapter_id": None,
                "host_path": "h.vue",
                "mounts": [{"mountId": "m", "file": "h.vue", "component": "C"}],
                "profile_source": {"inbound_reference_count": 1},
                "scenario_profile": {"profile_id": "p", "host_reachable": True},
                "evidence": {"review_status": "x", "legacy_reasons": []},
            }

        regeneration = _synthetic_regeneration(agree=False)
        regeneration.disk = {
            "entries": [
                _disk_entry("xlsx/p", independent=True),
                _disk_entry("xlsx/c", independent=False),
            ]
        }
        regeneration.rebuilt = None
        rows = GEN.build_entry_rows(
            regeneration=regeneration,
            landings=_empty_landings(),
            db=GEN.DbSnapshot(readable=True, error=None),
            plan66=_empty_plan66(),
        )
        by_id = {row["entry_id"]: row for row in rows}
        assert by_id["xlsx/p"]["counted_in_denominator"] is True
        assert by_id["xlsx/c"]["counted_in_denominator"] is False, (
            "parent 重复入口被算进主分母 ⇒ 同一入口计两遍（正文：父入口不重复计数）"
        )
        for row in rows:
            assert row["counted_in_denominator_why"]
            missing = [facet for facet in GEN.REQUIRED_ENTRY_FACETS if facet not in row]
            assert not missing, f"{row['entry_id']} 缺核对面 {missing}"

        # 🔴 同一次构造顺带把 deletion plan 落点的**派生性**按住：清册只引用其中一条
        # entry 时，另一条必须判「无落点」。恒真的 `has_landing` 会让任何计划外的
        # legacy entry 都被当成已有落点（实测 M32 首轮判 GREEN 就是这条缺失）。
        partial_plan = GEN.Task66PlanFacts(
            payload={
                "task": "66",
                "plan_commit": "0" * 40,
                "items": [
                    {
                        "item_id": "synthetic:only-parent",
                        "disposition": "pending_delete",
                        "replacement": {"manifest_entry_ids": ["xlsx/p"]},
                    }
                ],
                "replacement_registry": [],
                "manifest_required_scenario_sets": {},
            }
        )
        landed = {
            row["entry_id"]: row["deletion_plan_landing"]
            for row in GEN.build_entry_rows(
                regeneration=regeneration,
                landings=_empty_landings(),
                db=GEN.DbSnapshot(readable=True, error=None),
                plan66=partial_plan,
            )
        }
        assert landed["xlsx/p"]["has_landing"] is True
        assert landed["xlsx/p"]["pending_delete_item_count"] == 1
        assert landed["xlsx/c"]["has_landing"] is False, (
            "清册没有引用这条 entry 却判它有落点 ⇒ 「计划外 legacy/unreachable」永远查不出来"
        )
        assert landed["xlsx/c"]["pending_delete_item_count"] == 0

    def test_build_counters_keeps_parent_duplicates_out_of_the_primary_denominator(
        self,
    ) -> None:
        """🔴 逻辑级：主口径排除 parent 重复入口，副口径必须仍然看得见它。"""
        independent, _ = _synthetic_row(
            "xlsx/ind", independent=True, capability="unreachable", pending_delete_items=1
        )
        duplicate, _ = _synthetic_row(
            "xlsx/dup", independent=False, capability="unreachable", pending_delete_items=1
        )
        counters = GEN.build_counters(
            rows=[independent, duplicate],
            landings=_empty_landings(),
            db=GEN.DbSnapshot(readable=True, error=None),
            plan66=_empty_plan66(),
            regeneration=_synthetic_regeneration(agree=False),
        )
        assert counters["denominators"]["manifest_entry_total"] == 2
        assert counters["denominators"]["independent_entry_total"] == 1
        assert counters["denominators"]["parent_duplicate_total"] == 1
        assert counters["reported_by_task_text"]["unreachable"] == 1, (
            "主口径把 parent 重复入口算进去了 ⇒ 同一入口被计两遍"
        )
        assert counters["reported_by_task_text_over_all_entries"]["unreachable"] == 2, (
            "副口径塌成主口径 ⇒ 那条 parent 重复入口从报告里消失"
        )
        assert counters["parent_duplicate_only_deltas"]["unreachable"] == 1
        assert counters["parent_duplicate_only_entry_ids"]["unreachable"] == ["xlsx/dup"]
        assert counters["reported_by_task_text"]["planned_delete"] == 1
        assert counters["reported_by_task_text_over_all_entries"]["planned_delete"] == 2

    def test_the_empty_stale_denominator_note_appears_only_when_it_is_empty(self) -> None:
        """🔴 逻辑级：空分母说明必须由「分母是否真的为空」驱动，不是常量文案。

        两臂：没有任何可度量 stale 的 entry ⇒ 必须有说明；有一条 entry 真的带 evidence
        ⇒ 说明必须消失。恒有/恒无都说明该字段与事实无关。
        """
        no_evidence, _ = _synthetic_row("xlsx/ns", independent=True, source_changed=True)
        empty = GEN.build_counters(
            rows=[no_evidence],
            landings=_empty_landings(),
            db=GEN.DbSnapshot(readable=True, error=None),
            plan66=_empty_plan66(),
            regeneration=_synthetic_regeneration(agree=False),
        )["denominators"]
        assert empty["evidence_stale_denominator"] == 0
        assert empty["evidence_stale_denominator_empty"] is True
        assert empty["evidence_stale_denominator_note"], "分母为空却不解释"
        assert "不要求 stale 清零" in empty["evidence_stale_denominator_note"]

        with_evidence, _ = _synthetic_row(
            "xlsx/ws", independent=True, source_changed=True, published=True, test_runs=1
        )
        filled = GEN.build_counters(
            rows=[with_evidence],
            landings=_empty_landings(),
            db=GEN.DbSnapshot(readable=True, error=None),
            plan66=_empty_plan66(),
            regeneration=_synthetic_regeneration(agree=False),
        )["denominators"]
        assert filled["evidence_stale_denominator"] == 1
        assert filled["evidence_stale_denominator_empty"] is False
        assert filled["evidence_stale_denominator_note"] is None, (
            "分母非空却仍挂着「分母为空」的说明 ⇒ 那句文案是常量，与事实无关"
        )

    def test_structural_errors_fire_on_a_synthetic_drift_and_stay_silent_without_one(
        self,
    ) -> None:
        """逻辑级：source digest 漂移分支必须由「是否漂移」这个事实驱动。"""
        row, _ = _synthetic_row("xlsx/x", independent=True, pending_delete_items=1)
        drifted = GEN.structural_errors(
            regeneration=_synthetic_regeneration(agree=False),
            rows=[row],
            landings=_empty_landings(),
            plan66=_empty_plan66(),
        )
        assert "source_digest_drifted_from_reviewed_overlay" in {
            error["kind"] for error in drifted
        }, "合成漂移没有触发结构错误 ⇒ 该分支被短路"
        aligned = GEN.structural_errors(
            regeneration=_synthetic_regeneration(agree=True),
            rows=[row],
            landings=_empty_landings(),
            plan66=_empty_plan66(),
        )
        assert "source_digest_drifted_from_reviewed_overlay" not in {
            error["kind"] for error in aligned
        }, "digest 一致时仍报漂移 ⇒ 该判据与事实无关（重言式）"

    def test_each_entry_verdict_recomputes_from_the_recorded_row(
        self, report: dict[str, Any], entries: list[dict[str, Any]]
    ) -> None:
        """正向重算：把记录里的 row + 磁盘 manifest entry 喂回 `classify_entry()`。"""
        disk = json.loads(GEN.MANIFEST_PATH.read_text(encoding="utf-8"))
        disk_by_id = {row["entry_id"]: row for row in disk["entries"]}
        for row in entries:
            live = GEN.classify_entry(row, disk_by_id[row["entry_id"]])
            assert live == row["verdicts"], f"{row['entry_id']}: verdict 现算与记录不符"

    def test_counters_recompute_from_the_recorded_entries(
        self, report: dict[str, Any], entries: list[dict[str, Any]]
    ) -> None:
        primary = report["counters"]["reported_by_task_text"]
        overall = report["counters"]["reported_by_task_text_over_all_entries"]
        for kind in GEN.REPORTED_COUNTER_KINDS:
            expected_primary = sum(
                1 for row in entries if row["verdicts"][kind] and row["counted_in_denominator"]
            )
            expected_overall = sum(1 for row in entries if row["verdicts"][kind])
            assert primary[kind] == expected_primary, kind
            assert overall[kind] == expected_overall, kind

    def test_each_of_the_six_counters_is_asserted_separately(
        self, report: dict[str, Any]
    ) -> None:
        """🔴 教训 3：集合成员判据要**分开**断言，不合成一条。"""
        counters = report["counters"]["reported_by_task_text"]
        denominators = report["counters"]["denominators"]
        total = denominators["independent_entry_total"]
        assert counters["unadjudicated"] > 0, "未裁决为 0 —— 与 manifest 的 unadjudicated 统计矛盾"
        assert counters["fake_bidirectional"] > 0, "假双向为 0 —— 与 manifest 统计矛盾"
        assert counters["unaccepted"] == total, (
            "未验收不等于全部独立 entry —— 若真有 entry 验收了，请同步更新本判据"
        )
        assert counters["unreachable"] >= 0
        assert counters["evidence_stale"] == 0 and denominators[
            "evidence_stale_denominator_empty"
        ] is True, "stale 计数与其分母必须一起读"
        assert counters["planned_delete"] > 0, "planned-delete 为 0 —— Task 66 清册没被消费"

    def test_stale_is_reported_and_never_required_to_be_zero(
        self, report: dict[str, Any]
    ) -> None:
        """正文逐字：「允许报告 stale，不要求 stale 清零」。"""
        note = report["counters"]["denominators"]["evidence_stale_denominator_note"]
        assert note and "不要求 stale 清零" in note
        assert "不是" in note, "0 必须被明确解释为「不是已刷新」"
        assert report["why_this_task_only_reports"]["what_this_report_does_not_certify"]
        certify = report["why_this_task_only_reports"]["what_this_report_does_not_certify"]
        for phrase in ("五个零", "真实 OO probe", "删除资格"):
            assert phrase in certify, f"免责声明里缺 {phrase!r}"

    def test_planned_delete_is_not_treated_as_a_final_zero(
        self, report: dict[str, Any]
    ) -> None:
        note = report["counters"]["deletion_plan_side"]["planned_delete_is_not_a_final_zero"]
        assert "Task 72 Stage A" in note

    def test_structural_error_kinds_are_closed_and_each_error_names_an_owner(
        self, report: dict[str, Any]
    ) -> None:
        for error in report["structural_errors"]:
            assert error["kind"] in GEN.STRUCTURAL_ERROR_KINDS, error["kind"]
            assert error["detail"] and error["owner_task"], error["kind"]

    def test_the_source_digest_drift_is_reported_as_a_structural_error(
        self, report: dict[str, Any]
    ) -> None:
        """正文：「digest 缺失立即报结构错误」。漂移同理必须落在 structural_errors 里。"""
        kinds = {error["kind"] for error in report["structural_errors"]}
        assert "source_digest_drifted_from_reviewed_overlay" in kinds, (
            "source digest 漂移没有进 structural_errors —— 若复核方更新过 overlay，"
            "请同步解除 BP-67-1 并更新本判据"
        )

    def test_no_unplanned_legacy_or_unreachable_slipped_through(
        self, entries: list[dict[str, Any]], report: dict[str, Any]
    ) -> None:
        """计划外 legacy/unreachable 必须么进 structural_errors、么根本不存在。"""
        unplanned = sorted(
            row["entry_id"]
            for row in entries
            if row["migration_state"] in {"legacy_fake_bidirectional", "unreachable_pending_delete"}
            and not row["deletion_plan_landing"]["has_landing"]
        )
        recorded = next(
            (
                error
                for error in report["structural_errors"]
                if error["kind"] == "unplanned_legacy_or_unreachable"
            ),
            None,
        )
        if unplanned:
            assert recorded is not None, f"计划外 legacy/unreachable {unplanned[:5]} 没有报错"
            assert sorted(recorded["entry_ids"]) == unplanned
        else:
            assert recorded is None
        # 分母非空：至少要有 legacy/unreachable entry 存在，否则本判据恒真。
        assert any(
            row["migration_state"] in {"legacy_fake_bidirectional", "unreachable_pending_delete"}
            for row in entries
        ), "一条 legacy/unreachable 都没有 ⇒ 本判据分母为空"

    def test_every_task66_item_still_has_digest_owner_and_rollback(self) -> None:
        """正文：「digest/owner/rollback 缺失立即报结构错误」。现算 Task 66 的全部清册项。"""
        plan = GEN.load_task66_plan()
        assert plan.items, "清册项为空 ⇒ 本判据分母为空"
        assert plan.items_missing_required_bindings() == [], (
            "Task 66 清册有项缺 digest/owner/rollback —— 应作为结构错误报出"
        )

    #: 四个必需绑定的「字段路径 → 期望被点名的 key」。
    MISSING_BINDING_CASES: tuple[tuple[tuple[str, ...], str], ...] = (
        (("sha256",), "sha256"),
        (("owner", "deletion_owner_task"), "owner.deletion_owner_task"),
        (("owner", "replacement_owner_task"), "owner.replacement_owner_task"),
        (("rollback_target", "mode"), "rollback_target.mode"),
    )

    def test_missing_binding_detector_catches_each_of_the_four(self) -> None:
        """🔴 「当前清册没有缺失」对「检测器是否还在工作」毫无信息量（假绿第②源）。

        逐条造一个**合成**缺失项喂回检测器：四个绑定各自必须被独立点名。四条分支共用
        一条集合判据时，删掉任意一条分支照样绿。

        故意不用 `parametrize`：已知坑 BP-29（`_locate_want` 对 parametrize nodeid 恒误报），
        而本方法是变异 M20 的 `want` 目标。
        """
        plan = GEN.load_task66_plan()
        for path, expected in self.MISSING_BINDING_CASES:
            victim = copy.deepcopy(plan.items[0])
            victim["item_id"] += f"@synthetic:{expected}"
            cursor: Any = victim
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = ""
            synthetic = GEN.Task66PlanFacts(
                payload={**plan.payload, "items": [*plan.items, victim]}
            )
            found = synthetic.items_missing_required_bindings()
            assert len(found) == 1, f"{expected}: 合成缺失项没被唯一命中，实得 {found}"
            assert found[0]["item_id"] == victim["item_id"]
            assert found[0]["missing"] == [expected], (
                f"检测器报的是 {found[0]['missing']}，期望恰好点名 {expected!r}"
            )


# ════════════════════════════════════════════════════════════════════════════
# §7 入向义务与 BP
# ════════════════════════════════════════════════════════════════════════════


class TestInboundObligationsAndBlockingPreconditions:
    def test_inbound_scan_recomputes_and_contains_the_real_targets(
        self, report: dict[str, Any]
    ) -> None:
        """教训 16：不只要求非空 + 逐条成立，还要断言真实目标在里面。"""
        live = GEN.collect_inbound_obligations()
        recorded = report["inbound_obligations"]
        assert {row["path"] for row in live} == {row["path"] for row in recorded}
        paths = {row["path"] for row in recorded}
        # 🔴 这五条路径**写死在判据里**，不迭代 `GEN.REQUIRED_INBOUND_TARGETS`：
        # 迭代那个常量时，把常量删空判据照样绿（教训 16 的 M13 形态）。
        for target in (
            "backend/app/services/workpaper_sync/opaque_entry_gate.py",
            "backend/app/services/workpaper_sync/entry_profile.py",
            "backend/app/services/workpaper_sync/evidence_freshness.py",
            "backend/data/workpaper_sync_task66_legacy_deletion_plan.json",
            "backend/data/workpaper_task61_word_pilot_gate_probes.json",
        ):
            assert target in paths, f"入向义务里没有真实目标 {target}"
            assert target in GEN.REQUIRED_INBOUND_TARGETS, (
                f"{target} 从 `REQUIRED_INBOUND_TARGETS` 里被移走了 —— 那道生成期反向门失守"
            )
        # 记录侧 + **现算侧**都要求存在机器可读的归属登记。只查记录时，把
        # `structured_ownership` 改成恒假只会被逐字节锁抓到（实测 M23 首轮如此），
        # 而「区分结构化归属与散文提及」这条能力就没有自己的判据。
        for source, rows in (("记录", recorded), ("现算", live)):
            structured = [row for row in rows if row["structured_ownership"]]
            assert structured, (
                f"{source}侧所有入向义务都只是散文提及 ⇒ 没有一条机器可读的归属登记"
            )
            owned = {row["path"] for row in structured}
            assert "backend/app/services/workpaper_sync/opaque_entry_gate.py" in owned, (
                f"{source}侧 `opaque_entry_gate.py` 不再算结构化归属 —— 它带的 "
                "`adjudication_owner_task=\"67\"` 是本任务唯一的生产侧机器可读归属"
            )

    def test_the_opaque_gate_entry_id_split_is_owned_by_this_task(
        self, report: dict[str, Any]
    ) -> None:
        """`opaque_entry_gate.ENTRY_ID_NAMESPACE_SPLIT_NOTE` 的 owner 就是 Task 67。"""
        from app.services.workpaper_sync.opaque_entry_gate import (
            ENTRY_ID_NAMESPACE_SPLIT_NOTE,
        )

        assert ENTRY_ID_NAMESPACE_SPLIT_NOTE["adjudication_owner_task"] == "67"
        paths = {row["path"] for row in report["inbound_obligations"]}
        assert "backend/app/services/workpaper_sync/opaque_entry_gate.py" in paths

    def test_every_bp_is_task_scoped_and_explains_why_it_is_not_fixed_here(
        self, report: dict[str, Any]
    ) -> None:
        bps = report["blocking_preconditions"]
        assert bps, "一条 BP 都没有 —— 本轮实测有 6 条，空清单是假绿"
        ids = [bp["id"] for bp in bps]
        assert len(set(ids)) == len(ids), f"BP id 重复: {ids}"
        for bp in bps:
            assert GEN.BP_ID_RE.fullmatch(bp["id"]), bp["id"]
            assert bp["title"] and bp["statement"], bp["id"]
            assert bp["owner_task"], bp["id"]
            assert bp["why_not_fixed_here"], f"{bp['id']}: 没写为什么不在本任务修"
            assert bp["evidence"], f"{bp['id']}: 没有实证"

    def test_bp_67_5_reports_bp_66_1_without_clearing_it(
        self, report: dict[str, Any]
    ) -> None:
        """🔴 BP-66-1 的 owner 字段写的就是 67。本任务的处置必须**明写**是转报不是解除。"""
        bp = next(item for item in report["blocking_preconditions"] if item["id"] == "BP-67-5")
        evidence = bp["evidence"]
        assert evidence["task66_bp_id"] == "BP-66-1"
        assert evidence["task66_bp_owner_task_field"] == "67"
        assert evidence["task67_disposition"] == "reported_not_cleared"
        assert evidence["unreachable_surface_count"] > 0, (
            "替代面已全部可达 ⇒ 请同步解除 BP-66-1/BP-67-5 并更新本判据"
        )
        plan = json.loads(TASK66_PLAN_PATH.read_text(encoding="utf-8"))
        live = sorted(
            surface["path"]
            for surface in plan["replacement_registry"]
            if not surface.get("reachable_from_production_host")
        )
        assert evidence["unreachable_surface_paths"] == live, (
            "转报的替代面清单与 Task 66 清册现算不符 —— 名单过期"
        )
        # 教训 16：断言那两个真实目标在名单里，改名不能绕过。
        joined = "\n".join(live)
        assert "useWorkpaperSyncBridge.ts" in joined
        assert "WorkpaperSyncEditorHost.vue" in joined

    def test_blocking_preconditions_are_built_from_their_inputs_not_from_constants(
        self,
    ) -> None:
        """🔴 逻辑级：BP 的处置与实证必须由输入派生。

        记录侧判据（读磁盘 JSON）对 BP 的构造过程恒不敏感 —— 把 `reported_not_cleared`
        改成 `cleared`、把 approved bundle 数写死成 Task 61 的旧值 1，记录都不会变
        （实测 M28/M29 首轮只命中逐字节锁）。这里用合成输入直接跑构造函数。
        """
        db = GEN.DbSnapshot(readable=True, error=None)
        db.row_counts = {
            "working_paper_sync_definition_bundle": 2,
            "working_paper_sync_entry_state": 0,
            "working_paper_content_representation": 0,
            "working_paper_content_version": 0,
            "working_paper_sync_test_run": 0,
            "working_paper_entry_evidence_scenario": 0,
        }
        db.definition_bundles = [
            {"id": "b1", "state": "approved"},
            {"id": "b2", "state": "approved"},
            {"id": "b3", "state": "candidate"},
        ]
        plan66 = GEN.Task66PlanFacts(
            payload={
                "task": "66",
                "plan_commit": "0" * 40,
                "items": [],
                "replacement_registry": [
                    {"path": "a/useWorkpaperSyncBridge.ts", "reachable_from_production_host": False},
                    {"path": "a/WorkpaperSyncEditorHost.vue", "reachable_from_production_host": False},
                    {"path": "a/reachable.ts", "reachable_from_production_host": True},
                ],
                "manifest_required_scenario_sets": {},
            }
        )
        row, _ = _synthetic_row("xlsx/x", independent=True)
        bps = GEN.build_blocking_preconditions(
            rows=[row],
            landings=_empty_landings(),
            db=db,
            plan66=plan66,
            regeneration=_synthetic_regeneration(agree=False),
        )
        by_id = {bp["id"]: bp for bp in bps}

        five = by_id["BP-67-5"]["evidence"]
        assert five["task67_disposition"] == "reported_not_cleared", (
            "BP-67-5 宣称已解除 —— 本任务没有改任何前端宿主，无权解除 BP-66-1"
        )
        assert five["unreachable_surface_count"] == 2, (
            f"不可达替代面计数不是从输入派生的，实得 {five['unreachable_surface_count']}"
        )
        assert five["unreachable_surface_paths"] == [
            "a/WorkpaperSyncEditorHost.vue",
            "a/useWorkpaperSyncBridge.ts",
        ]
        assert five["surface_total"] == 3

        four = by_id["BP-67-4"]["evidence"]
        assert four["approved_bundle_rows"] == 2, (
            f"approved bundle 数不是现算的（实得 {four['approved_bundle_rows']}）—— "
            "写死或引用上游旧数时，供给变化后结论会静静地过期"
        )
        assert four["definition_bundle_rows"] == 2
        assert four["bundles_bound_to_entry"] == 0

    def test_bp_67_2_is_backed_by_a_live_registry_recount(
        self, report: dict[str, Any]
    ) -> None:
        """「186 条 planned entry 一条都注册不上」必须现算，不许引用旧数。"""
        bp = next(item for item in report["blocking_preconditions"] if item["id"] == "BP-67-2")
        assert bp["evidence"]["registered"] == report["production_landings"]["registrations"]
        assert bp["evidence"]["planned"] == report["production_landings"]["registration_plan_size"]
        assert bp["evidence"]["registered"] == 0, (
            "registry 已经注册上了 ⇒ 请同步解除 BP-67-2 并更新本判据"
        )
        assert bp["evidence"]["registrable"] > 0, (
            "连静态可注册的 entry 都没有 ⇒ BP-67-2 的叙述（供给而非计划）不成立"
        )

    def test_bp_67_4_recomputes_the_bundle_supply_instead_of_citing_task61(
        self, report: dict[str, Any]
    ) -> None:
        """🔴 Task 61 实测 bundle=1；本轮实测已增长。BP 必须用**现算**值而不是旧数。"""
        bp = next(item for item in report["blocking_preconditions"] if item["id"] == "BP-67-4")
        db = report["database_snapshot"]
        assert bp["evidence"]["definition_bundle_rows"] == db["row_counts"][
            "working_paper_sync_definition_bundle"
        ]
        approved = sum(1 for row in db["definition_bundles"] if row["state"] == "approved")
        assert bp["evidence"]["approved_bundle_rows"] == approved
        assert approved > 0, (
            "approved bundle 为 0 ⇒ BP-67-4 的叙述（有 bundle 但没绑 entry）不成立，请改判据"
        )
        assert bp["evidence"]["bundles_bound_to_entry"] == 0


# ════════════════════════════════════════════════════════════════════════════
# §8 幂等与逐字节锁
# ════════════════════════════════════════════════════════════════════════════


class TestGeneratorIsIdempotentAndCheckIsStrict:
    def test_check_matches_the_file_on_disk(self, live_report: dict[str, Any]) -> None:
        """`--check` 与磁盘逐字节比对。变异检验的公共锚点（几乎每条变异都会带红它）。"""
        rendered = GEN.render(live_report)
        assert rendered == REPORT_PATH.read_text(encoding="utf-8"), (
            "现算报告与磁盘不同 —— 生成器或输入变了，请重跑 `--write`"
        )

    def test_cli_requires_exactly_one_mode(self) -> None:
        with pytest.raises(SystemExit) as both:
            GEN.main(["--check", "--write"])
        assert both.value.code == 2
        with pytest.raises(SystemExit) as neither:
            GEN.main([])
        assert neither.value.code == 2

    def test_report_digest_covers_everything_except_itself(
        self, live_report: dict[str, Any]
    ) -> None:
        """记录侧 + 现算侧：digest 必须覆盖除自己以外的**全部**字段。

        只查记录时，把生成期的 digest 输入缩成一个字段只会被逐字节锁抓到
        （实测 M30 首轮如此），而「报告不可被手改」这条保证就没有自己的判据。
        """
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        recorded = payload.pop("report_digest")
        assert GEN.digest_of(payload) == recorded, "report_digest 与磁盘内容不符"

        live = dict(live_report)
        live_digest = live.pop("report_digest")
        assert GEN.digest_of(live) == live_digest, (
            "现算报告的 report_digest 覆盖面小于全部字段 ⇒ 报告可被任意手改而 digest 不变"
        )
        # 反向：动一个与 digest 无关的深层字段，digest 必须变。
        tampered = copy.deepcopy(live)
        tampered["counters"]["reported_by_task_text"]["unaccepted"] = -1
        assert GEN.digest_of(tampered) != live_digest, (
            "改掉 counters 里的一个数字后 digest 没变 ⇒ digest 没覆盖 counters"
        )

    def test_the_report_declares_its_requirements_and_properties(self) -> None:
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        for ac in ("1.2", "1.6", "1.7", "6.18", "12.13", "14.16"):
            assert ac in payload["requirements_covered"], ac
        for prop in ("Property 3", "Property 51", "Property 67", "Property 71"):
            assert prop in payload["properties_verified"], prop
