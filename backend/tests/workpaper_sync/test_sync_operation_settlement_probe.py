"""结算后复核探针的**离线**守卫（R3.4 / Property 3 的探针侧）。

spec `frozen-contract-read-path-and-legacy-operation-settlement` 任务 9
Requirements: R3.4
Property: **Property 3**（「状态变了但内容没落地」不可能出现）

═══ 分工 ═══

| 判据 | 文件 |
| --- | --- |
| 探针是**只读**的（AST：无 insert/update/delete/commit） | 本文件 |
| 八条形态判据**真的会红**（逐条驱动否定侧） | 本文件 |
| 报告结构 / 可重跑 / 对拍口径 / CLI 契约 | 本文件 |
| 真库上「残缺形态确实被判红」+ 历史缺口棘轮 | `test_sync_operation_settlement_pg.py` |

🔴 **纪律（memory 铁律 ㉖）**：结构判据一律用 **AST**，不用文本 `in` 匹配 ——
本模块与探针模块的 docstring 里逐处解释「为什么不能裸 SQL 改 state」时逐字写着
`UPDATE` / `commit`，用子串判据会把自己判成违规。

🔴 **纪律（㉒）**：「扫描器命中」≠「有缺陷」。每条判据都同时给**正面判据**
（什么形态算干净）与**双向变异**（造一个违规样本必须红 + 现算的真实模块必须绿）。
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from scripts.check import check_sync_operation_settlement as CLI
from scripts.check import sync_settlement_facts as FACTS
from scripts.check import sync_settlement_review as RULES

BACKEND = Path(__file__).resolve().parents[2]
CLI_PY = BACKEND / "scripts" / "check" / "check_sync_operation_settlement.py"
FACTS_PY = BACKEND / "scripts" / "check" / "sync_settlement_facts.py"
RULES_PY = BACKEND / "scripts" / "check" / "sync_settlement_review.py"

_STAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════════════


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _call_names(tree: ast.AST) -> set[str]:
    """函数/方法调用的**点分全名**集合（见 `_dotted_calls`）。"""
    return set(_dotted_calls(tree))


def _dotted_calls(tree: ast.AST) -> list[str]:
    """所有调用的**点分全名**（`sys.path.insert` / `sa.text` / `x.commit`）。

    🔴 用全名而不是末段名：`sys.path.insert(...)` 的末段也是 `insert`，
    按末段判会把「往 sys.path 加仓库根」这条无害语句判成写库（假红）。
    """
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        parts: list[str] = []
        cur: ast.AST = node.func
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        if parts:
            out.append(".".join(reversed(parts)))
    return out


def _sql_statements(tree: ast.Module) -> list[tuple[str, str]]:
    """本模块里的**全部 SQL 文本**：`(来源, 文本)`。

    两条来源都要扫，少一条就有静默脱管口：

    * `sa.text("…")` 的**实参**字面量（内联 SQL）；
    * 模块级 `NAME = \"\"\"…\"\"\"` 常量（本仓的 SQL 都是这么写的 —— 只扫
      `sa.text(...)` 实参会对「把 SQL 放常量里、调用时传变量」的形态**恒绿**，
      实测：首版只找到 1 条 `SET TRANSACTION READ ONLY`，5 条 SELECT 一条都没扫到）。
    """
    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "text"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            out.append((f"sa.text@{node.lineno}", node.args[0].value))
    for node in tree.body:
        targets: list[ast.AST] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if value is None or not isinstance(value, ast.Constant):
            continue
        if not isinstance(value.value, str):
            continue
        for t in targets:
            if isinstance(t, ast.Name):
                out.append((t.id, value.value))
    return out


def _sql_head(text: str) -> str:
    """SQL 文本的首个**大写关键字**（跳过空白与注释行）。"""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        return stripped.split()[0].upper()
    return ""


def _chain(**overrides: Any) -> FACTS.VersionChain:
    """一条「已正确落地」的版本链基线；用例按需覆盖单个字段。"""
    base: dict[str, Any] = {
        "application_id": "app-1",
        "application_state": "applied",
        "definition_bundle_id": "bundle-1",
        "base_version_id": "cv-base",
        "base_representation_id": "rep-base",
        "current_revision": 11,
        "base_content_version_revision": 4,
        "result_representation_id": "rep-result",
        "result_revision": 5,
        "merged_projection_sha256": "a" * 64,
        "entry_state_present": True,
        "entry_current_representation_id": "rep-result",
        "entry_representation_generation": 1,
        "result_representation_generation": 1,
        "result_content_version_revision": 5,
        "room_id": "room-1",
    }
    base.update(overrides)
    return FACTS.VersionChain(**base)


def _rollup(**overrides: Any) -> FACTS.ConflictRollup:
    base: dict[str, Any] = {
        "total": 0,
        "resolved": 0,
        "abandoned": 0,
        "superseded": 0,
        "unsettled": 0,
        "triplet_complete": 0,
        "resolution_pair_complete": 0,
        "resolved_without_value": (),
    }
    base.update(overrides)
    return FACTS.ConflictRollup(**base)


def _event(seq: int, frm: str | None, to: str) -> FACTS.TimelineEvent:
    return FACTS.TimelineEvent(
        sequence_no=seq,
        from_state=frm,
        to_state=to,
        stage="s",
        actor_type="system",
        actor_id=None,
        error_code=None,
        occurred_at=f"2026-01-01T00:00:0{seq}+00:00",
    )


def _timeline(*pairs: tuple[str | None, str]) -> tuple[FACTS.TimelineEvent, ...]:
    return tuple(_event(i, frm, to) for i, (frm, to) in enumerate(pairs, 1))


def _report(**overrides: Any) -> FACTS.OperationReport:
    base: dict[str, Any] = {
        "operation_id": "op-1",
        "entry_id": "xlsx/gt-d4-operating-revenue",
        "wp_id": "wp-1",
        "project_id": "proj-1",
        "direction": "oo_to_html",
        "state": "applied",
        "is_terminal": True,
        "accepted_at": None,
        "finished_at": "2026-11-16T00:00:00+00:00",
        "error_code": None,
        "error_stage": None,
        "conflicts": _rollup(total=3, resolved=3, resolution_pair_complete=3),
        "version_chain": _chain(),
        "timeline": _timeline((None, "created"), ("created", "applied")),
        "verdicts": (),
    }
    base.update(overrides)
    return FACTS.OperationReport(**base)


class TestTheReportCarriesEveryVerdict:
    """报告层必须把八条判据都带出去，否则 CLI 输出看不出结论。

    （八条判据**各自**的否定侧在 `test_sync_operation_settlement_verdicts.py`；
    这里只守「报告把它们都带出去了」。）
    """

    def test_the_registry_lists_eight_unique_rules(self) -> None:
        assert len(RULES.ALL_VERDICTS) == 8
        assert len(set(RULES.ALL_VERDICTS)) == 8, "判据 id 有重复"

    def test_build_verdicts_emits_exactly_the_registry(self) -> None:
        """产出的 id 必须**逐值等于**登记表 —— 防「登记了却不执行」。"""
        produced = RULES.build_verdicts(
            state="applied",
            direction="oo_to_html",
            rollup=_rollup(),
            chain=_chain(),
            timeline=_timeline((None, "created"), ("created", "applied")),
        )
        assert tuple(v.rule_id for v in produced) == RULES.ALL_VERDICTS

    def test_the_report_dict_carries_all_verdicts(self) -> None:
        verdicts = RULES.build_verdicts(
            state="applied",
            direction="oo_to_html",
            rollup=_rollup(),
            chain=_chain(),
            timeline=_timeline((None, "created"), ("created", "applied")),
        )
        payload = _report(verdicts=verdicts).as_dict()
        assert [v["rule_id"] for v in payload["verdicts"]] == list(RULES.ALL_VERDICTS)
        assert payload["ok"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 一、探针必须是**只读**的（本任务最硬的一条）
# ═══════════════════════════════════════════════════════════════════════════

#: 会写库的调用名（**点分全名**，避免 `sys.path.insert` 之类假红）。
#: 判据 = 调用的末段名落在本集合里，且**不是** `sys.path.*` / `list.*` 这类容器操作。
_WRITE_CALL_TAILS: frozenset[str] = frozenset(
    {
        "insert",
        "update",
        "delete",
        "commit",
        "flush",
        "bulk_insert_mappings",
        "bulk_update_mappings",
        "execute_driver_sql",
        "add",
        "add_all",
        "exec_driver_sql",
    }
)

#: 末段命中但**不是**写库的白名单（容器 / 路径操作）。每项都要能自证。
_WRITE_CALL_EXEMPT: frozenset[str] = frozenset(
    {
        # 往 sys.path 加仓库根 —— 无害，且是本仓脚本的固定写法。
        "sys.path.insert",
        # `list.add` / `set.add` 不存在，但 `set.update` / `dict.update` / `list.extend`
        # 是纯内存容器操作；本模块用 `set.update` 吗？没有。为了不给出过宽豁免，
        # 这里**只**放 sys.path.insert。
    }
)

#: 会改库的 SQL 首词。
_WRITE_SQL_HEAD: frozenset[str] = frozenset(
    {"INSERT", "UPDATE", "DELETE", "TRUNCATE", "ALTER", "DROP", "CREATE", "MERGE", "COPY"}
)

_MODULES = [CLI_PY, FACTS_PY, RULES_PY]
_MODULE_IDS = ["cli", "facts", "rules"]


class TestTheProbeIsReadOnly:
    """R3.4 的「只读」不能靠自觉 —— 静态断言 + 运行时证据两条都要有。"""

    @pytest.mark.parametrize("path", _MODULES, ids=_MODULE_IDS)
    def test_no_write_call_anywhere(self, path: Path) -> None:
        """三个模块里**一个**写库调用都不许有（变异 m4 必须让本条红）。"""
        offenders = sorted(
            name
            for name in _call_names(_tree(path))
            if name not in _WRITE_CALL_EXEMPT and name.rsplit(".", 1)[-1] in _WRITE_CALL_TAILS
        )
        assert offenders == [], f"{path.name} 里出现写库调用：{offenders}"

    @pytest.mark.parametrize("path", _MODULES, ids=_MODULE_IDS)
    def test_every_sql_statement_is_a_select(self, path: Path) -> None:
        """所有 SQL 文本（内联 + 模块级常量）的首词必须是 `SELECT` 或会话控制语句。

        🔴 首版只扫 `sa.text(...)` 的**实参**，而本模块的 SQL 全写在模块级常量里
        ⇒ 只找到 1 条、5 条 SELECT 一条都没扫到（分母不足 ⇒ 判据形同虚设）。
        这条教训就是「扫描口径必复核覆盖面」的现场实例。
        """
        offenders = [
            (source, _sql_head(text))
            for source, text in _sql_statements(_tree(path))
            if _sql_head(text) in _WRITE_SQL_HEAD
        ]
        assert offenders == [], f"{path.name} 里有写 SQL：{offenders}"

    def test_the_probe_actually_has_sql_to_check(self) -> None:
        """分母非空 —— 否则上面两条判据对「一个 SQL 都没有的模块」恒绿。"""
        statements = _sql_statements(_tree(CLI_PY))
        selects = [s for s in statements if _sql_head(s[1]) == "SELECT"]
        assert len(selects) >= 5, (
            f"CLI 里只找到 {len(selects)} 条 SELECT（全部 {len(statements)} 条 SQL）—— "
            "分母不足，只读判据等于没跑"
        )

    def test_the_enforced_read_only_statement_exists(self) -> None:
        """PG 上必须真的把事务设成只读。"""
        heads = [_sql_head(text) for _, text in _sql_statements(_tree(CLI_PY))]
        texts = [text for _, text in _sql_statements(_tree(CLI_PY))]
        assert any("SET TRANSACTION READ ONLY" in t for t in texts), (
            "CLI 里没有 SET TRANSACTION READ ONLY —— 只读就只剩自觉"
        )
        assert "SET" in heads, "SET TRANSACTION READ ONLY 没被 SQL 扫描器识别"

    def test_the_read_only_flag_is_only_set_on_postgres(self) -> None:
        """方言检测：非 PG 不得声称「已只读」（否则报告在撒谎）。"""
        tree = _tree(CLI_PY)
        assert any(
            isinstance(n, ast.Constant) and n.value == "postgresql" for n in ast.walk(tree)
        ), "CLI 里没有 dialect == 'postgresql' 的分支 —— 方言检测缺失"
        assigns = [
            t.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            for t in node.targets
            if isinstance(t, ast.Name) and t.id == "read_only_enforced"
        ]
        assert len(assigns) == 2, (
            f"read_only_enforced 应恰有 2 处赋值（初值 False + PG 分支 True），实得 {len(assigns)}"
        )

    def test_rollback_is_in_a_finally_block(self) -> None:
        """只读事务必须无条件收尾 —— 异常路径也不能漏。"""
        tree = _tree(CLI_PY)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Try) and node.finalbody:
                for sub in node.finalbody:
                    for inner in ast.walk(sub):
                        if (
                            isinstance(inner, ast.Call)
                            and isinstance(inner.func, ast.Attribute)
                            and inner.func.attr == "rollback"
                        ):
                            found = True
        assert found, "rollback 不在 finally 块里 —— 异常路径会漏收尾"


# 八条形态判据（V1~V8）的逐条否定侧在 `test_sync_operation_settlement_verdicts.py`
# （拆文件的原因：合起来 982 行 > 800 行门限；判据本身没有减少）。


# ═══════════════════════════════════════════════════════════════════════════
# 三、冲突计数滚动（② 段的唯一口径）
# ═══════════════════════════════════════════════════════════════════════════


class TestSummarizeConflicts:
    def test_the_four_buckets_are_mutually_exclusive(self) -> None:
        rows = [
            {"id": "a", "resolved_at": "t", "resolved_by": "u", "resolved_value": {"v": 1}},
            {"id": "b", "abandoned_at": "t", "abandon_reason": "契约换代", "abandoned_by": "u"},
            {"id": "c", "superseded_at": "t"},
            {"id": "d"},
        ]
        rollup = FACTS.summarize_conflicts(rows)
        assert (rollup.total, rollup.resolved, rollup.abandoned, rollup.superseded) == (4, 1, 1, 1)
        assert rollup.unsettled == 1
        assert rollup.settled == 3
        assert rollup.is_fully_settled is False

    def test_an_unsettled_row_is_the_one_with_all_three_marks_empty(self) -> None:
        """「仍未处理」的**唯一**口径：三个标记列全空。只缺一个不算。"""
        rows = [
            {"id": "a", "superseded_at": "t"},
            {"id": "b"},
            {"id": "c", "abandoned_at": "t", "abandon_reason": "r", "abandoned_by": "u"},
        ]
        rollup = FACTS.summarize_conflicts(rows)
        assert rollup.unsettled == 1

    def test_a_blank_reason_does_not_count_as_complete(self) -> None:
        rows = [{"id": "x", "abandoned_at": "t", "abandon_reason": "   ", "abandoned_by": "u"}]
        rollup = FACTS.summarize_conflicts(rows)
        assert rollup.abandoned == 1
        assert rollup.triplet_complete == 0, "空白原因不得算三列齐备"

    def test_a_lone_reason_column_does_not_count_as_complete(self) -> None:
        """只写了 reason（没有 at/by）—— 残缺，不计入 complete。"""
        rollup = FACTS.summarize_conflicts([{"id": "x", "abandon_reason": "有原因"}])
        assert rollup.abandoned == 0
        assert rollup.triplet_complete == 0

    def test_resolved_without_value_is_named(self) -> None:
        rollup = FACTS.summarize_conflicts([{"id": "c-9", "resolved_at": "t", "resolved_by": "u"}])
        assert rollup.resolved_without_value == ("c-9",)

    def test_an_empty_settlement_is_green(self) -> None:
        rollup = FACTS.summarize_conflicts([])
        assert rollup.total == 0
        assert rollup.is_fully_settled is True


# ═══════════════════════════════════════════════════════════════════════════
# 四、报告结构 / 可重跑 / 对拍口径
# ═══════════════════════════════════════════════════════════════════════════


class TestTheDocumentIsReproducible:
    def test_the_content_digest_ignores_generated_at(self) -> None:
        """**可重跑**的可证伪形式：同一输入两次跑，digest 必须相同。"""
        a = CLI.build_document(
            [_report()], read_only_enforced=True, dialect="postgresql", generated_at=_STAMP
        )
        b = CLI.build_document(
            [_report()],
            read_only_enforced=True,
            dialect="postgresql",
            generated_at=datetime(2030, 6, 6, tzinfo=timezone.utc),
        )
        assert a["generated_at"] != b["generated_at"]
        assert a["content_digest"] == b["content_digest"]

    def test_a_changed_version_chain_changes_the_digest(self) -> None:
        """版本链参与 digest —— 漏读它会让两次报告「看起来一样」（假绿）。"""
        a = CLI.build_document(
            [_report(version_chain=_chain(result_representation_id="rep-A"))],
            read_only_enforced=True,
            dialect="postgresql",
            generated_at=_STAMP,
        )
        b = CLI.build_document(
            [_report(version_chain=_chain(result_representation_id="rep-B"))],
            read_only_enforced=True,
            dialect="postgresql",
            generated_at=_STAMP,
        )
        assert a["content_digest"] != b["content_digest"]

    def test_a_changed_conflict_rollup_changes_the_digest(self) -> None:
        a = CLI.build_document(
            [_report()], read_only_enforced=True, dialect="postgresql", generated_at=_STAMP
        )
        b = CLI.build_document(
            [_report(conflicts=_rollup(total=4, resolved=4, resolution_pair_complete=4))],
            read_only_enforced=True,
            dialect="postgresql",
            generated_at=_STAMP,
        )
        assert a["content_digest"] != b["content_digest"]

    def test_compare_ignores_only_generated_at(self) -> None:
        a = CLI.build_document(
            [_report()], read_only_enforced=True, dialect="postgresql", generated_at=_STAMP
        )
        b = CLI.build_document(
            [_report()],
            read_only_enforced=True,
            dialect="postgresql",
            generated_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        )
        assert CLI.compare_documents(a, b) == []

    def test_compare_catches_a_real_difference(self) -> None:
        a = CLI.build_document(
            [_report()], read_only_enforced=True, dialect="postgresql", generated_at=_STAMP
        )
        b = CLI.build_document(
            [_report(conflicts=_rollup(total=4, resolved=4))],
            read_only_enforced=True,
            dialect="postgresql",
            generated_at=_STAMP,
        )
        problems = CLI.compare_documents(a, b)
        assert problems, "真差异没被抓到 —— 对拍判据形同虚设"
        assert any("content_digest" in p for p in problems)

    def test_compare_catches_a_different_schema_first(self) -> None:
        problems = CLI.compare_documents(
            {"schema": "a", "operations": []}, {"schema": "b", "operations": []}
        )
        assert len(problems) == 1 and "schema" in problems[0]

    def test_nondeterministic_keys_is_only_the_timestamp(self) -> None:
        """被忽略的键只有生成时刻。加业务字段进这个集合 = 给对拍开后门。"""
        assert RULES.NONDETERMINISTIC_KEYS == ("generated_at",)


class TestTheDocumentCarriesTheFourSections:
    def test_every_operation_dict_has_the_four_sections(self) -> None:
        payload = _report().as_dict()
        for key in (
            "state",
            "is_terminal",
            "accepted_at",
            "finished_at",
            "error_code",
            "error_stage",
            "conflicts",
            "version_chain",
            "timeline",
        ):
            assert key in payload, f"报告缺 {key} 段"
        for key in (
            "total",
            "resolved",
            "abandoned",
            "superseded",
            "unsettled",
            "triplet_complete",
            "resolution_pair_complete",
            "settled",
            "is_fully_settled",
        ):
            assert key in payload["conflicts"], f"② 段缺 {key}"
        for key in (
            "application_id",
            "base_version_id",
            "base_representation_id",
            "base_content_version_revision",
            "result_representation_id",
            "result_representation_generation",
            "result_content_version_revision",
            "entry_state_present",
            "entry_current_representation_id",
            "room_id",
        ):
            assert key in payload["version_chain"], f"③ 段缺 {key}"

    def test_the_timeline_carries_the_audit_fields(self) -> None:
        event = _report().as_dict()["timeline"][0]
        for key in ("sequence_no", "from_state", "to_state", "stage", "actor_type", "occurred_at"):
            assert key in event, f"④ 段缺 {key}"

    def test_the_report_is_json_serialisable(self) -> None:
        doc = CLI.build_document([_report()], read_only_enforced=False, dialect="sqlite")
        assert json.loads(json.dumps(doc, ensure_ascii=False))["operation_count"] == 1

    def test_the_known_gap_registry_is_listed_in_the_document(self) -> None:
        doc = CLI.build_document([], read_only_enforced=True, dialect="postgresql")
        assert doc["known_gap_ids"] == sorted(RULES.KNOWN_LEGACY_GAPS)

    def test_a_failing_operation_makes_failure_count_positive(self) -> None:
        bad = _report(
            verdicts=RULES.build_verdicts(
                state="superseded",
                direction="oo_to_html",
                rollup=_rollup(total=3, abandoned=3, triplet_complete=1),
                chain=_chain(result_representation_id=None),
                timeline=_timeline((None, "created"), ("created", "superseded")),
            )
        )
        doc = CLI.build_document([bad], read_only_enforced=True, dialect="postgresql")
        assert doc["failure_count"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 五、CLI 形态
# ═══════════════════════════════════════════════════════════════════════════


class TestTheCliContract:
    def test_it_refuses_to_run_without_a_selector(self) -> None:
        with pytest.raises(SystemExit) as exc:
            CLI.main([])
        assert exc.value.code == 2, "缺 --operation / --all 必须是 2（argparse 约定）"

    def test_compare_on_a_missing_file_returns_environment_error(self, tmp_path: Path) -> None:
        """环境失败（2）必须与「发现不一致」（1）可区分。"""
        code = CLI.main(
            ["--compare", str(tmp_path / "nope.json"), str(tmp_path / "nope2.json")]
        )
        assert code == 2

    def test_compare_on_malformed_json_returns_environment_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert CLI.main(["--compare", str(bad), str(bad)]) == 2

    def test_compare_reports_difference_with_exit_one(self, tmp_path: Path) -> None:
        left = tmp_path / "l.json"
        right = tmp_path / "r.json"
        left.write_text(
            json.dumps(
                CLI.build_document(
                    [_report()],
                    read_only_enforced=True,
                    dialect="postgresql",
                    generated_at=_STAMP,
                )
            ),
            encoding="utf-8",
        )
        right.write_text(
            json.dumps(
                CLI.build_document(
                    [_report(state="conflict", is_terminal=False)],
                    read_only_enforced=True,
                    dialect="postgresql",
                    generated_at=_STAMP,
                )
            ),
            encoding="utf-8",
        )
        assert CLI.main(["--compare", str(left), str(right)]) == 1

    def test_the_reviewable_states_exclude_created(self) -> None:
        """`created` 还没结算，没有可复核的内容 —— 不许混进 --all 的分母。"""
        assert "created" not in CLI._REVIEWABLE_STATES
        assert "conflict" in CLI._REVIEWABLE_STATES
        assert "applied" in CLI._REVIEWABLE_STATES

    def test_the_reviewable_states_match_the_operation_enum(self) -> None:
        """登记的状态必须都是 `OperationState` 的成员（防写错字面量）。"""
        from app.services.workpaper_sync.models import OperationState

        unknown = set(CLI._REVIEWABLE_STATES) - {s.value for s in OperationState}
        assert unknown == set(), f"--all 的分母里有非枚举取值：{unknown}"

    def test_the_reviewable_states_cover_every_terminal_state(self) -> None:
        """所有 operation 终态都必须在分母里 —— 漏一个就有一类 operation 永不被复核。"""
        from app.services.workpaper_sync.models import TERMINAL_STATES

        terminals = {s.value for s in TERMINAL_STATES["operation"]}
        missing = terminals - set(CLI._REVIEWABLE_STATES)
        assert missing == set(), f"--all 漏了终态 {missing}"

    def test_the_probe_can_locate_the_repo_root(self) -> None:
        """脚本自己定位仓库根（不依赖 cwd）。"""
        assert CLI.BACKEND_ROOT == BACKEND
        assert (CLI.BACKEND_ROOT / "app" / "services" / "workpaper_sync").is_dir()


# ═══════════════════════════════════════════════════════════════════════════
# 六、文件行数门（新文件不得超 800，且不许加白名单）
# ═══════════════════════════════════════════════════════════════════════════


class TestTheNewFilesFitTheLineGate:
    @pytest.mark.parametrize(
        "path", [CLI_PY, FACTS_PY, RULES_PY, Path(__file__)], ids=["cli", "facts", "rules", "this"]
    )
    def test_under_eight_hundred_lines(self, path: Path) -> None:
        """口径与 `check_file_size.py` 一致：`len(text.splitlines())`。

        🔴 不许用 `len(text.split("\\n"))`（多算 1），也不许用 PowerShell 的
        `Measure-Object -Line`（跳过空行，会低估）。
        """
        count = len(path.read_text(encoding="utf-8").splitlines())
        assert count <= 800, f"{path.name} 有 {count} 行（阈值 800），须拆分而非加白名单"

    def test_none_of_them_is_in_the_size_whitelist(self) -> None:
        """新文件一律不得进白名单（memory 铁律：超 800 行须拆分）。"""
        whitelist = (BACKEND / "scripts" / "file_size_whitelist.txt").read_text(encoding="utf-8")
        for name in (
            "check_sync_operation_settlement.py",
            "sync_settlement_facts.py",
            "sync_settlement_review.py",
        ):
            assert name not in whitelist, f"{name} 被加进了行数白名单"
