# -*- coding: utf-8 -*-
"""lane 裁决登记表的判据（F6）。

**Spec: published-representation-production-path-and-lane-adjudication**

═══ 本文件的落点 ═══════════════════════════════════════════════════════════════

Task 10.1 的九条变异里有四条打在本模块上（1 / 2 / 3 / 7），而它们的 `want` 测试此前
**不存在** —— 没有靶子的变异只会判 WRONG-TEST，不能证明任何事。本文件先把靶子立起来：

| 变异 | 形态 | 本文件的对手判据 |
|---|---|---|
1 | `adjudicate_lane` 的 L1 分支移到 L2 之后 | `TestLaneOrderIsLoadBearing` |
2 | `supply_satisfied` 改成只读判据 A | `TestSupplyRequiresAllFourCriteria` |
3 | `observe_lane_supply` 的 `raise` 改成 `return False` | `TestObservationFailureIsNotDegraded` |
7 | 新写一处 `entry_id.startswith("opaque-")` 判定 | `TestNoSecondLaneDecisionSite` |

═══ Property 编号 ═══════════════════════════════════════════════════════════════

🔴 **编号一律以 `design.md` 的 `### Property N` 为真源。** 首版本文件自造了一套 1~8
的编号，与 design.md 语义**错位**（本文件的「Property 1」实为 design 的 Property 2），
于是 tasks.md 要求的「标签回指 design.md」失效 —— 读者按标签去查会查到另一条判据。
2026-09-05 已按 design.md 重编号，覆盖如下：

| design Property | 本文件的落点 | 任务 |
|---|---|---|
1 | `TestVerdictDomainIsClosedAndDeterministic` | 1.2 |
2 | `TestOpaqueVerdictSurvivesEveryLaterCriterion` | 1.2 |
3 | `TestUndecidedNamesTheFirstFailedCriterion` | 1.2 |
4 | `TestOpaqueLaneCoverageIsLocked` | 1.4 |
5 | `TestNoSecondLaneDecisionSite` | 1.4 |
6 | `TestSupplyRequiresAllFourCriteria` | 2.2 |
7 | `TestProvisionedBundleDoesNotImplySupply` | 2.2 |
8 | `TestCriterionAAndCReadDifferentSources` | 2.2 |
9 | `TestObservationFailureIsNotDegraded` | 2.3 |
17 | `TestLaneOrderIsNotCommutable` | 1.4 |

═══ 纪律 ═══════════════════════════════════════════════════════════════════════

* 判据落在**行为 / 结构 / 真实执行**，不落在「字符串是否存在」。
* 空集上恒真的判据必须自带非空分母断言。
* `hypothesis` 的 `max_examples` ≥ 100。
* 本文件**零数据库**：`observe_lane_supply` 的取数用替身 session，真库侧归 F8。
"""

from __future__ import annotations

import ast
import asyncio
import itertools
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync import projection_lane_registry as R

_MODULE_PATH = Path(R.__file__)


def _load_manifest_once() -> tuple[Any, Any]:
    """整份 manifest 只读一次 —— 确定性判据要拿**同一个**对象喂两次。"""
    from app.services.workpaper_sync.adapters.registry import manifest_entries_by_id
    from app.services.workpaper_sync.entry_profile import load_entry_manifest

    manifest = load_entry_manifest()
    return manifest, manifest_entries_by_id(manifest)


_MANIFEST_SNAPSHOT, _MANIFEST_BY_ID = _load_manifest_once()


# ═══════════════════════════════════════════════════════════════════════════
# 装配辅助
# ═══════════════════════════════════════════════════════════════════════════


def _facts(**over: Any) -> R.LaneSupplyFacts:
    """四条判据全真的 `LaneSupplyFacts`，按需覆盖。"""
    base: dict[str, Any] = {
        "entry_id": "xlsx/gt-h1-fixed-assets",
        "verdict": R.LaneVerdict.projection,
        "projection_bundle_provisioned": True,
        "published_representation_current": True,
        "representation_follows_projection_contract": True,
        "representation_contract_digest_matches": True,
    }
    base.update(over)
    return R.LaneSupplyFacts(**base)


def _real_opaque_entry_id(*, wp_code: str | None = None) -> str:
    """真源构造的 opaque entry_id —— 不手写前缀（手写就成了第二真源）。

    `opaque_entry_id` 的签名是 keyword-only `(*, wp_code, wp_id)`：`wp_code` 给
    `custom_cells` lane（`opaque-{wp_code}`），`wp_id` 给 `offline_upload` /
    `wopi_put_file`（`opaque-{wp_id}`）。两种口径的分叉登记在
    `opaque_entry_gate.ENTRY_ID_NAMESPACE_SPLIT_NOTE` 里。
    """
    import uuid

    from app.services.workpaper_sync.writer_migration import opaque_entry_id

    return opaque_entry_id(wp_code=wp_code, wp_id=uuid.uuid4())


def _delivered_entry_ids() -> tuple[str, ...]:
    from app.services.workpaper_sync.adapters.registry import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )

    return tuple(str(row["entry_id"]) for row in DELIVERED_PER_ENTRY_CONTRACTS)


#: 反向自检的种植目录 —— 必须在 `assert_no_second_lane_decision_site` 的**真实**扫描根
#: 内（`backend/app/**` 与 `backend/scripts/**`）。选 `scripts/diagnose/`：那里本就放
#: 一次性诊断脚本，且 `_wip_*` 前缀已被 `.gitignore` 收，万一 finally 没跑到也不会入库。
_PLANT_DIR = Path(R.__file__).resolve().parents[3] / "scripts" / "diagnose"


def _plant_violation(filename: str, body: str) -> Path:
    """往扫描根里种一个探针文件，返回其路径（调用方负责 `unlink`）。

    🔴 文件名一律 `_wip_` 前缀：`.gitignore` 已收该前缀，异常退出时不会污染 git 状态。
    """
    assert filename.startswith("_wip_"), "探针文件名必须 `_wip_` 前缀（.gitignore 已收）"
    assert _PLANT_DIR.is_dir(), f"扫描根不存在: {_PLANT_DIR}"
    path = _PLANT_DIR / filename
    path.write_text("# -*- coding: utf-8 -*-\n" + body, encoding="utf-8")
    return path


def _synthetic_lane(lane_id: str, source: Any, *, template: Any = None) -> Any:
    """按真实 `OpaqueLane` 的形状造一条替身 lane（`dataclasses.replace`）。

    用 `replace` 而不是手写全部字段：那边加字段时本辅助自动跟上，不会因为漏一个
    必填字段而让扰动构造失败（那会让扰动测试因错误的理由通过或失败）。
    """
    import dataclasses

    from app.services.workpaper_sync.opaque_entry_gate import OPAQUE_AUTHORITY_LANES

    base = template if template is not None else OPAQUE_AUTHORITY_LANES[0]
    return dataclasses.replace(base, lane_id=lane_id, entry_id_source=source)


def _function_source(name: str) -> str:
    """按 AST 行号截取函数体（不用花括号/字符窗口 —— 返回注解里的括号会骗到别处）。"""
    source = _MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    lines = source.splitlines()[node.lineno - 1 : node.end_lineno]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Property 2：opaque 命名空间的 entry_id 恒判 opaque 且不受后续判据影响
# ═══════════════════════════════════════════════════════════════════════════


class TestLaneOrderIsLoadBearing:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 2: opaque 命名空间的 entry_id 恒判 opaque 且不受后续判据影响**

    **Validates: Requirements 1.3, 1.4, 1.7**
    """

    def test_opaque_entry_id_is_adjudicated_opaque(self) -> None:
        """opaque entry_id ⇒ `opaque`。

        🔴 这条是变异 1（L1 后移）的直接对手：opaque entry_id **永不在 manifest 里**，
        L1 一旦排到 L2 之后，它会先撞 L2 的 `undecided` ⇒ 本条打红。
        """
        entry_id = _real_opaque_entry_id()
        assert R.adjudicate_lane(entry_id) is R.LaneVerdict.opaque

    def test_opaque_verdict_holds_even_with_an_empty_manifest(self) -> None:
        """喂空 manifest 仍判 `opaque` —— 证明 L1 真的在 L2 **之前**。

        这一条比上一条更强：`manifest={}` 时 L2 必然不成立，因此若结论仍是 `opaque`，
        那只可能是 L1 在 L2 之前就返回了。把 L1 后移则本条必得 `undecided`。
        """
        entry_id = _real_opaque_entry_id()
        assert R.adjudicate_lane(entry_id, manifest={}) is R.LaneVerdict.opaque

    def test_real_opaque_representation_entry_is_opaque(self) -> None:
        """已在真库落成的那个 opaque entry_id 形态同样判 `opaque`（回归锚）。"""
        # 形态取自 writer_migration 的构造函数，值用固定 uuid 以免依赖库
        import uuid

        from app.services.workpaper_sync.writer_migration import opaque_entry_id

        wp_id = uuid.UUID("017624e2-cd7e-4641-bd99-db7c1f1f5f7e")
        entry_id = opaque_entry_id(wp_code=None, wp_id=wp_id)
        assert entry_id == f"opaque-{wp_id}", (
            f"真库那条 representation 的 entry_id 形态变了: {entry_id}"
        )
        assert R.adjudicate_lane(entry_id) is R.LaneVerdict.opaque

        # 另一种口径（custom_cells 的 `opaque-{wp_code}`）同样判 opaque
        by_code = opaque_entry_id(wp_code="ZZ99", wp_id=wp_id)
        assert R.adjudicate_lane(by_code) is R.LaneVerdict.opaque

    @settings(max_examples=200, deadline=None)
    @given(
        suffix=st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
            min_size=0,
            max_size=24,
        )
    )
    def test_any_entry_id_under_the_opaque_prefix_is_opaque(self, suffix: str) -> None:
        """前缀之下的**任何** entry_id 都判 `opaque`，与后缀无关。"""
        entry_id = R._opaque_entry_prefix() + suffix
        assert R.adjudicate_lane(entry_id) is R.LaneVerdict.opaque

    def test_unknown_entry_is_undecided_not_projection(self) -> None:
        """不在 manifest 的非 opaque entry ⇒ `undecided`（fail closed，不默认 projection）。"""
        assert (
            R.adjudicate_lane("xlsx/definitely-not-a-manifest-entry")
            is R.LaneVerdict.undecided
        )

    def test_delivered_pilot_entries_are_projection(self) -> None:
        """四个已交付 pilot entry 全判 `projection` —— 非空分母，防「全 undecided 也绿」。"""
        delivered = _delivered_entry_ids()
        assert len(delivered) >= 4, f"已交付 entry 只有 {len(delivered)} 个，分母过小"
        for entry_id in delivered:
            assert R.adjudicate_lane(entry_id) is R.LaneVerdict.projection, entry_id

    def test_verdict_domain_is_closed_at_three(self) -> None:
        """三值域封闭 —— 加第四个值必须改判据，不能悄悄多一格。"""
        assert {v.value for v in R.LaneVerdict} == {
            "projection",
            "opaque",
            "undecided",
        }

    def test_l1_branch_precedes_the_manifest_lookup_in_source_order(self) -> None:
        """结构判据：源码里 L1 的 `return opaque` 行号 **小于** L2 的 manifest 取数行号。

        行为判据（上面那条空 manifest）已经能抓住变异 1，本条是它的结构冗余：
        两条一起红时定位更快。判据用 AST 行号，不用字符串出现顺序。
        """
        source = _MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "adjudicate_lane"
        )
        opaque_returns = [
            inner.lineno
            for inner in ast.walk(node)
            if isinstance(inner, ast.Return)
            and isinstance(inner.value, ast.Attribute)
            and inner.value.attr == "opaque"
        ]
        manifest_calls = [
            inner.lineno
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id == "manifest_entries_by_id"
        ]
        assert opaque_returns, "`adjudicate_lane` 里没有 `return LaneVerdict.opaque`"
        assert manifest_calls, "`adjudicate_lane` 里没有 manifest 取数 —— L2 不见了"
        assert min(opaque_returns) < min(manifest_calls), (
            f"L1 的 opaque 分支在行 {min(opaque_returns)}，L2 的 manifest 取数在行 "
            f"{min(manifest_calls)} —— L1 必须在前，否则 opaque entry 先撞 L2 的 "
            "undecided，L1 成为不可达分支"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 3：判据不足恒判 undecided 并点名首个不足判据与其真源
# ═══════════════════════════════════════════════════════════════════════════


class TestAssertProjectionLaneDistinguishesRejections:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 3: 判据不足恒判 undecided 并点名首个不足判据与其真源**

    **Validates: Requirements 1.5, 1.7**
    """

    def test_opaque_raises_lane_is_opaque_with_lane_id(self) -> None:
        entry_id = _real_opaque_entry_id()
        with pytest.raises(R.LaneIsOpaqueError) as caught:
            R.assert_projection_lane(entry_id)
        assert caught.value.entry_id == entry_id
        assert caught.value.lane_id, "没带 lane_id ⇒ 「命中哪条 opaque lane」查不到"

    def test_undecided_raises_lane_undecided_naming_the_first_failed_criterion(
        self,
    ) -> None:
        """`undecided` 必须点名**首个**不成立判据与其真源文件。"""
        with pytest.raises(R.LaneUndecidedError) as caught:
            R.assert_projection_lane("xlsx/definitely-not-a-manifest-entry")
        message = str(caught.value)
        assert "manifest" in message.lower() or "L2" in message, message
        assert ".json" in message or "/" in message, (
            f"诊断没给真源文件路径: {message}"
        )

    def test_the_two_rejections_are_not_the_same_class(self) -> None:
        """两类拒绝不得同类 —— 同类就无法在调用方分开处置。"""
        assert not issubclass(R.LaneIsOpaqueError, R.LaneUndecidedError)
        assert not issubclass(R.LaneUndecidedError, R.LaneIsOpaqueError)
        assert issubclass(R.LaneIsOpaqueError, R.LaneRegistryError)
        assert issubclass(R.LaneUndecidedError, R.LaneRegistryError)

    def test_error_codes_are_distinct(self) -> None:
        codes = {
            cls.__name__: getattr(cls, "error_code", None)
            for cls in (
                R.LaneIsOpaqueError,
                R.LaneUndecidedError,
                R.LaneSupplyObservationError,
                R.OpaqueLaneCoverageDriftError,
            )
        }
        present = [c for c in codes.values() if c]
        assert len(set(present)) == len(present), codes

    def test_projection_lane_entries_pass_without_raising(self) -> None:
        """非空分母：四个 pilot entry 必须全部通过（否则本类判据全在空集上）。"""
        delivered = _delivered_entry_ids()
        assert len(delivered) >= 4
        for entry_id in delivered:
            R.assert_projection_lane(entry_id)  # 不抛即通过


# ═══════════════════════════════════════════════════════════════════════════
# Property 6：供给成立当且仅当四条判据全为真
# ═══════════════════════════════════════════════════════════════════════════


class TestSupplyRequiresAllFourCriteria:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 6: 供给成立当且仅当四条判据全为真**

    **Validates: Requirements 2.1, 2.3, 2.4**
    """

    def test_all_true_is_satisfied(self) -> None:
        assert _facts().supply_satisfied is True

    @pytest.mark.parametrize(
        "field",
        [
            "projection_bundle_provisioned",
            "published_representation_current",
            "representation_follows_projection_contract",
            "representation_contract_digest_matches",
        ],
    )
    def test_each_single_false_breaks_satisfaction(self, field: str) -> None:
        """🔴 变异 2（`supply_satisfied` 只读判据 A）的直接对手。

        逐条把**单个**判据置假：只读 A 的实现会在 B/C/D 任一为假时仍返回 True ⇒ 打红。
        """
        assert _facts(**{field: False}).supply_satisfied is False, (
            f"{field} 为假时供给仍判成立 —— 四条并非全部必需"
        )

    @settings(max_examples=200, deadline=None)
    @given(
        a=st.booleans(), b=st.booleans(), c=st.booleans(), d=st.booleans()
    )
    def test_satisfaction_equals_conjunction_over_all_16_states(
        self, a: bool, b: bool, c: bool, d: bool
    ) -> None:
        """穷举意义上的合取等价 —— 任何「少读一条」的实现都会在某个状态上不等。"""
        facts = _facts(
            projection_bundle_provisioned=a,
            published_representation_current=b,
            representation_follows_projection_contract=c,
            representation_contract_digest_matches=d,
        )
        assert facts.supply_satisfied is (a and b and c and d)

    def test_all_sixteen_states_are_actually_exercised(self) -> None:
        """自证分母：16 种组合逐一构造，且恰有 1 种为真。

        `hypothesis` 那条理论上可能抽不到全部 16 种；这条把分母钉死。
        """
        satisfied = 0
        for a, b, c, d in itertools.product((True, False), repeat=4):
            facts = _facts(
                projection_bundle_provisioned=a,
                published_representation_current=b,
                representation_follows_projection_contract=c,
                representation_contract_digest_matches=d,
            )
            if facts.supply_satisfied:
                satisfied += 1
        assert satisfied == 1, (
            f"16 种组合里有 {satisfied} 种判成立 —— 合取语义只允许恰 1 种"
        )

    def test_supply_satisfied_reads_all_four_fields_in_source(self) -> None:
        """结构冗余：`supply_satisfied` 的函数体里四个字段名都要出现。

        行为判据已能抓住变异 2；本条让「删掉三个字段」这种形态在结构层也立刻可见。
        """
        body = _function_source("supply_satisfied")
        for field in (
            "projection_bundle_provisioned",
            "published_representation_current",
            "representation_follows_projection_contract",
            "representation_contract_digest_matches",
        ):
            assert field in body, f"`supply_satisfied` 没读 {field}"

    def test_facts_are_frozen(self) -> None:
        """冻结数据类 —— 观测结果不得被下游改写。"""
        facts = _facts()
        with pytest.raises(Exception):
            facts.projection_bundle_provisioned = False  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# Property 6（诊断侧）：供给不足时诊断点名首个为假的判据
# ═══════════════════════════════════════════════════════════════════════════


class TestSupplyGapDiagnosticNamesCriteria:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 6: 供给成立当且仅当四条判据全为真（诊断侧：点名首个为假者）**

    **Validates: Requirements 2.4, 2.5**
    """

    def test_satisfied_supply_has_no_gap(self) -> None:
        assert R.describe_supply_gap(_facts()) is None

    def test_a_true_b_false_names_both(self) -> None:
        """A 真 B 假 ⇒ 同时点明「A 已满足」与「B 未满足」。"""
        text = R.describe_supply_gap(
            _facts(published_representation_current=False)
        )
        assert text is not None
        assert "判据 A" in text and "已满足" in text
        assert "判据 B" in text and "未满足" in text

    @pytest.mark.parametrize(
        ("field", "letter"),
        [
            ("projection_bundle_provisioned", "A"),
            ("published_representation_current", "B"),
            ("representation_follows_projection_contract", "C"),
            ("representation_contract_digest_matches", "D"),
        ],
    )
    def test_first_false_criterion_is_named(self, field: str, letter: str) -> None:
        """无论哪一条为假，诊断都点名它 —— 四条各有专属可分辨文案。"""
        text = R.describe_supply_gap(_facts(**{field: False}))
        assert text is not None
        assert f"判据 {letter}" in text, text
        assert field in text, f"诊断没给字段名 {field}: {text}"
        assert "未满足" in text

    def test_diagnostic_stops_at_the_first_false(self) -> None:
        """只展开**首个**为假者 —— fail-closed 的诊断只需第一因。"""
        text = R.describe_supply_gap(
            _facts(
                published_representation_current=False,
                representation_follows_projection_contract=False,
            )
        )
        assert text is not None
        assert "判据 B" in text
        assert "判据 C" not in text, f"越过首个为假者继续展开了: {text}"

    def test_diagnostic_is_generic_not_a_hardcoded_pair(self) -> None:
        """判据的通用性：A/B/C 真 D 假时也要逐条点明 A/B/C 已满足。

        写死「A 真 B 假」那一对的实现在此处只会给一句「D 未满足」⇒ 打红。
        """
        text = R.describe_supply_gap(
            _facts(representation_contract_digest_matches=False)
        )
        assert text is not None
        for letter in ("A", "B", "C"):
            assert f"判据 {letter}（" in text, f"缺 {letter} 的已满足陈述: {text}"
        assert "判据 D" in text and "未满足" in text

    def test_entry_id_is_in_the_diagnostic(self) -> None:
        text = R.describe_supply_gap(
            _facts(entry_id="xlsx/gt-d2-accounts-receivable", projection_bundle_provisioned=False)
        )
        assert text is not None and "xlsx/gt-d2-accounts-receivable" in text


# ═══════════════════════════════════════════════════════════════════════════
# Property 9：供给观测的异常不被降级为假值
# ═══════════════════════════════════════════════════════════════════════════


class TestObservationFailureIsNotDegraded:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 9: 供给观测的异常不被降级为假值**

    **Validates: Requirements 2.6**
    """

    def test_broken_session_raises_instead_of_returning_false_facts(self) -> None:
        """🔴 变异 3（`raise` 改 `return False`）的直接对手。

        「四条皆假」与「查不出来」是两件事：前者是**已知**供给不足，后者是**未知**。
        把后者伪装成前者，会让接线错误、权限缺失、schema 漂移全部长得像「还没发首版」。
        """

        class _ExplodingSession:
            async def execute(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("模拟取数失败：连接被拒")

        with pytest.raises(R.LaneSupplyObservationError) as caught:
            asyncio.run(
                R.observe_lane_supply(
                    session=_ExplodingSession(),
                    project_id="00000000-0000-0000-0000-000000000000",
                    wp_id="00000000-0000-0000-0000-000000000001",
                    entry_id="xlsx/gt-h1-fixed-assets",
                )
            )
        message = str(caught.value)
        assert "xlsx/gt-h1-fixed-assets" in message, "诊断没带 entry_id"
        assert "RuntimeError" in message, (
            f"诊断没带原始异常类型 ⇒ 根因被吞: {message}"
        )

    def test_observation_error_is_not_a_lane_verdict(self) -> None:
        """观测失败是异常，不是第四个 verdict —— 三值域必须保持封闭。"""
        assert "observation" not in {v.value for v in R.LaneVerdict}
        assert issubclass(R.LaneSupplyObservationError, R.LaneRegistryError) or issubclass(
            R.LaneSupplyObservationError, R.SyncDomainError
        )

    def test_source_reraises_rather_than_returning_a_default(self) -> None:
        """结构判据：`observe_lane_supply` 的 `except` 分支里必须有 `raise`。

        判据落在「except 处理器内部存在 raise 语句」，而不是「源码里出现 raise 这个词」
        —— 后者在 `return LaneSupplyFacts(...False...)` 替换后照样绿。
        """
        source = _MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "observe_lane_supply"
        )
        handlers = [
            inner for inner in ast.walk(node) if isinstance(inner, ast.ExceptHandler)
        ]
        assert handlers, "`observe_lane_supply` 没有 except 分支 —— 取数失败会裸奔"
        for handler in handlers:
            raises = [
                stmt for stmt in ast.walk(handler) if isinstance(stmt, ast.Raise)
            ]
            assert raises, (
                f"第 {handler.lineno} 行的 except 分支里没有 raise —— "
                "取数失败被降级成了某个返回值"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Property 5 / 4：单一裁决点与 opaque lane 覆盖锁
# ═══════════════════════════════════════════════════════════════════════════


class TestNoSecondLaneDecisionSite:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 5: lane 判定没有第二真源**

    **Validates: Requirements 1.9**
    """

    def test_scanner_passes_on_the_current_tree(self) -> None:
        """🔴 变异 7（另写一处 `startswith("opaque-")`）的直接对手。

        契约：**违规时 `raise`**，返回值是**合规点与形状校验点的清册**（供 evidence
        现读）。所以判据是「不抛」+「清册非空」，不是「返回值为空」——
        我第一版把返回值当违规清单，那读错了契约。
        """
        findings = R.assert_no_second_lane_decision_site()
        assert isinstance(findings, dict)
        assert findings, (
            "清册为空 ⇒ 扫描器可能一个文件都没扫到，「无第二真源」成了恒真判据"
        )
        sites = sum(len(v) for v in findings.values())
        assert sites >= 2, (
            f"清册只有 {sites} 个位点 —— 分母过小，不足以证明扫描器真的在工作"
        )

    def test_shape_validation_sites_are_classified_as_shape(self) -> None:
        """清册里的形状校验点必须**真的**是形状校验，不是被文件名豁免掉的选路。

        实测清册里有两处：`representations.assert_bundle_snapshot_finalizable`
        （比 `bundle.authority_model.value`）与
        `generate_task67_structural_pre_reconcile.projection_child_violations`
        （比 `authority.get("authority_model_type")`）。两者比的都是 **bundle /
        definition artifact 自身**的取值，与「某个 entry 走哪条 lane」无关。
        """
        findings = R.assert_no_second_lane_decision_site()
        descriptions = [d for items in findings.values() for d in items]
        assert descriptions, "清册没有位点描述"
        for text in descriptions:
            assert "L" in text and ":" in text, f"位点描述缺行号: {text}"

    def test_classifier_calls_entry_derived_operands_lane(self) -> None:
        """分类器的反向自检：entry 派生的操作数必须判 `lane`。

        这条是「按操作数来源分类」这个设计的可执行判据。没有它时，分类器完全可以
        无条件返回 `"shape"` —— 全仓扫描照样绿（因为再没有位点被判违规）。
        """
        for expression in (
            'entry["authority_model"]',
            "manifest_row['authority_model_type']",
            "entry_bundle.authority_model",  # 两类提示词同时命中 ⇒ 从严判 lane
        ):
            operand = ast.parse(expression, mode="eval").body
            assert R._classify_authority_comparison(operand) == "lane", expression

    def test_classifier_calls_bundle_derived_operands_shape(self) -> None:
        """bundle / definition artifact 派生的操作数判 `shape`。"""
        for expression in (
            "bundle.authority_model.value",
            'authority.get("authority_model_type")',
        ):
            operand = ast.parse(expression, mode="eval").body
            assert R._classify_authority_comparison(operand) == "shape", expression

    def test_classifier_fails_closed_on_unknown_operands(self) -> None:
        """来源判不出来时 fail closed 判 `lane` —— 要求它显式走裁决。"""
        operand = ast.parse("some_totally_unknown_thing", mode="eval").body
        assert R._classify_authority_comparison(operand) == "lane"

    def test_opaque_prefix_comes_from_writer_migration(self) -> None:
        """前缀取自真源，本模块不写第二份字面量。"""
        from app.services.workpaper_sync.writer_migration import OPAQUE_ENTRY_PREFIX

        assert R._opaque_entry_prefix() == OPAQUE_ENTRY_PREFIX

        body = _function_source("_opaque_entry_prefix")
        assert "OPAQUE_ENTRY_PREFIX" in body
        assert '"opaque-"' not in body and "'opaque-'" not in body, (
            "`_opaque_entry_prefix` 里写死了前缀字面量 —— 那就是第二真源"
        )

    # ── 反向自检：故意写错必失败 ──────────────────────────────────────
    #
    # 🔴 tasks.md 对 Property 5 的要求原文：「**不得**只断言当前源码合规 —— 那是空
    #    分母」。上面几条全是「当前源码合规」+ 分类器单元判据，它们无法排除
    #    「扫描器一个文件都没真扫、或 pattern 从不命中」这种形态。
    #    下面两条真往扫描根里写一处违规，断言被报；删掉后恢复合规。

    def test_a_planted_opaque_prefix_decision_is_reported_as_a_violation(self) -> None:
        """往 `backend/scripts/**` 种一处 `startswith("opaque-")` ⇒ 必须被报违规。"""
        planted = _plant_violation(
            "_wip_lane_second_source_probe.py",
            "def _probe_lane(entry_id: str) -> bool:\n"
            '    return entry_id.startswith("opaque-")\n',
        )
        try:
            with pytest.raises(R.LaneRegistryError) as caught:
                R.assert_no_second_lane_decision_site()
            message = str(caught.value)
            assert planted.name in message, (
                f"违规被报了，但没点名种下的文件 {planted.name}: {message[:400]}"
            )
        finally:
            planted.unlink(missing_ok=True)

        # 删掉后必须恢复合规 —— 否则上一条的「打红」可能来自别的既存违规
        R.assert_no_second_lane_decision_site()

    def test_a_planted_authority_model_comparison_is_reported(self) -> None:
        """种一处 `entry["authority_model"] == "projection_contract"` ⇒ 必须被报。

        这一条覆盖的是**另一个 pattern**（比较 authority model 取值），
        且操作数来自 entry ⇒ 分类器应判 `lane` 而非 `shape`。
        """
        planted = _plant_violation(
            "_wip_lane_authority_compare_probe.py",
            "def _probe(entry: dict) -> bool:\n"
            '    return entry["authority_model"] == "projection_contract"\n',
        )
        try:
            with pytest.raises(R.LaneRegistryError) as caught:
                R.assert_no_second_lane_decision_site()
            assert planted.name in str(caught.value)
        finally:
            planted.unlink(missing_ok=True)
        R.assert_no_second_lane_decision_site()

    def test_a_planted_site_that_calls_the_registry_is_not_a_violation(self) -> None:
        """对照组：种下的位置若**调用了**本模块的裁决函数，则不算违规。

        没有这一条时，上两条可以由「任何含 `opaque-` 字面量的文件都报违规」满足 ——
        那样的扫描器会把 `writer_migration` 这类真源也误报，实际上不可用。
        """
        planted = _plant_violation(
            "_wip_lane_compliant_probe.py",
            "from app.services.workpaper_sync.projection_lane_registry import (\n"
            "    adjudicate_lane,\n"
            ")\n"
            "\n"
            "\n"
            "def _probe(entry_id: str) -> bool:\n"
            "    verdict = adjudicate_lane(entry_id)\n"
            '    return entry_id.startswith("opaque-") and verdict is not None\n',
        )
        try:
            R.assert_no_second_lane_decision_site()  # 不抛即通过
        finally:
            planted.unlink(missing_ok=True)


class TestOpaqueLaneCoverageIsLocked:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 4: L1 形态表与 opaque lane 登记双向锁**

    **Validates: Requirements 1.8**
    """

    def test_registry_covers_every_opaque_lane(self) -> None:
        R.assert_registry_covers_opaque_lanes()  # 不抛即通过

    def test_every_declared_lane_id_is_reachable_from_an_entry_id(self) -> None:
        """非空分母 + 覆盖：每条 opaque lane 都能被某个 entry_id 形态命中。"""
        from app.services.workpaper_sync.opaque_entry_gate import (
            OPAQUE_AUTHORITY_LANES,
        )

        assert len(OPAQUE_AUTHORITY_LANES) >= 3, (
            f"opaque lane 只有 {len(OPAQUE_AUTHORITY_LANES)} 条，分母过小"
        )
        lane_id = R._find_matching_opaque_lane(_real_opaque_entry_id())
        assert lane_id in {lane.lane_id for lane in OPAQUE_AUTHORITY_LANES}

    def test_non_opaque_entry_matches_no_lane(self) -> None:
        assert R._find_matching_opaque_lane("xlsx/gt-h1-fixed-assets") is None

    # ── 双向锁的三个方向，逐个单条扰动 ────────────────────────────────
    #
    # 🔴 首版这里只有「当前源码上不抛」一条，那在**单侧**上恒真：`assert_registry_
    #    covers_opaque_lanes` 当时只拿 OPAQUE_AUTHORITY_LANES 跟它自己比（lane_id 不
    #    重复、entry_id_source 是合法枚举成员），于是往那边**新增**一条 lane、或把某条
    #    的 entry_id_source **改掉**，判据都不打红。下面三条把那个缺口封上；生产侧因此
    #    补了 `_L1_OPAQUE_LANE_SHAPES` 作为锁的本侧。

    def test_adding_a_lane_on_the_source_side_breaks_the_lock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """方向 ①：那边新增一条 lane 而 L1 未认领 ⇒ 打红并点名该 `lane_id`。"""
        from app.services.workpaper_sync import opaque_entry_gate as OG

        extra = _synthetic_lane("zz_newly_added_writer", OG.EntryIdSource.wp_id)
        monkeypatch.setattr(
            OG, "OPAQUE_AUTHORITY_LANES", (*OG.OPAQUE_AUTHORITY_LANES, extra)
        )
        with pytest.raises(R.OpaqueLaneCoverageDriftError) as caught:
            R.assert_registry_covers_opaque_lanes()
        assert "zz_newly_added_writer" in str(caught.value), (
            f"诊断没点名新增的 lane_id: {caught.value}"
        )

    def test_removing_a_lane_on_the_source_side_breaks_the_lock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """方向 ②：那边删掉一条 lane 而 L1 仍登记着 ⇒ 打红并点名该 `lane_id`。"""
        from app.services.workpaper_sync import opaque_entry_gate as OG

        kept = tuple(OG.OPAQUE_AUTHORITY_LANES)[1:]
        dropped = tuple(OG.OPAQUE_AUTHORITY_LANES)[0].lane_id
        monkeypatch.setattr(OG, "OPAQUE_AUTHORITY_LANES", kept)
        with pytest.raises(R.OpaqueLaneCoverageDriftError) as caught:
            R.assert_registry_covers_opaque_lanes()
        assert dropped in str(caught.value), (
            f"诊断没点名被删的 lane_id {dropped}: {caught.value}"
        )

    def test_flipping_entry_id_source_breaks_the_lock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """方向 ③：把某条 lane 的 `entry_id_source` 换形态 ⇒ 打红并点名该 `lane_id`。

        这一条守的是 entry_id **命名空间**被悄悄换掉（`opaque-{wp_code}` ↔
        `opaque-{wp_id}`）—— 那会让同一个底稿在两种口径下产出两个不同的 entry_id。
        """
        from app.services.workpaper_sync import opaque_entry_gate as OG

        lanes = list(OG.OPAQUE_AUTHORITY_LANES)
        target = lanes[0]
        flipped = (
            OG.EntryIdSource.wp_id
            if target.entry_id_source is not OG.EntryIdSource.wp_id
            else OG.EntryIdSource.wp_code
        )
        lanes[0] = _synthetic_lane(target.lane_id, flipped, template=target)
        monkeypatch.setattr(OG, "OPAQUE_AUTHORITY_LANES", tuple(lanes))
        with pytest.raises(R.OpaqueLaneCoverageDriftError) as caught:
            R.assert_registry_covers_opaque_lanes()
        message = str(caught.value)
        assert target.lane_id in message, f"诊断没点名漂移的 lane_id: {message}"
        assert flipped.value in message and target.entry_id_source.value in message, (
            f"诊断没同时给出两侧形态: {message}"
        )

    def test_emptying_the_l1_side_breaks_the_lock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L1 侧被清空 ⇒ 打红。空表会让双向锁只剩一侧、退化成恒真。"""
        monkeypatch.setattr(R, "_L1_OPAQUE_LANE_SHAPES", {})
        with pytest.raises(R.OpaqueLaneCoverageDriftError) as caught:
            R.assert_registry_covers_opaque_lanes()
        assert "只剩一侧" in str(caught.value) or "为空" in str(caught.value)

    def test_all_three_directions_are_reported_together(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """三方向**一起**算完再报告 —— 不是算到第一个就抛。

        只报第一个时，守卫为了独立 falsify 第三条判据必须先把前两条构造成通过，
        而那需要改生产源码 ⇒ 第三条在测试里无法被独立打红。
        """
        from app.services.workpaper_sync import opaque_entry_gate as OG

        lanes = list(OG.OPAQUE_AUTHORITY_LANES)
        # ③ 形态漂移
        target = lanes[0]
        flipped = (
            OG.EntryIdSource.wp_id
            if target.entry_id_source is not OG.EntryIdSource.wp_id
            else OG.EntryIdSource.wp_code
        )
        lanes[0] = _synthetic_lane(target.lane_id, flipped, template=target)
        # ② L1 有而那边没有
        removed = lanes.pop().lane_id
        # ① 那边有而 L1 没有
        lanes.append(_synthetic_lane("zz_three_way", OG.EntryIdSource.wp_id))
        monkeypatch.setattr(OG, "OPAQUE_AUTHORITY_LANES", tuple(lanes))

        with pytest.raises(R.OpaqueLaneCoverageDriftError) as caught:
            R.assert_registry_covers_opaque_lanes()
        message = str(caught.value)
        for token in ("zz_three_way", removed, target.lane_id):
            assert token in message, f"三方向未一起报告，缺 {token}: {message}"

    def test_import_time_execution_is_a_module_level_expression(self) -> None:
        """`assert_registry_covers_opaque_lanes()` 在 **import 期**真跑。

        判据落在 AST：模块顶层存在一条对它的调用表达式。写在某个函数体里的调用
        不会在 import 期执行 ⇒ 坏表照样能被加载。
        """
        tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
        top_level_calls = [
            node.value.func.id
            for node in tree.body
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
        ]
        assert "assert_registry_covers_opaque_lanes" in top_level_calls, (
            "模块顶层没有对 `assert_registry_covers_opaque_lanes()` 的调用 —— "
            f"import 期不跑，坏表可被加载。顶层调用实测: {top_level_calls}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 供给观测的替身 session
# ═══════════════════════════════════════════════════════════════════════════
#
# `observe_lane_supply` 对三条 SQL 各发一次 `session.execute(...)`，判据 A / B / C+D
# 分别消费它们。替身按 SQL 文本里的**表名**分派，不按调用顺序 —— 按顺序分派会在实现
# 里调整取数次序时静默错位（那正是「判据 A 与 C 的取数语义互不重叠」要盯的事）。


class _Row:
    """按属性访问的行替身（`row.bundle_id` 等），与 SQLAlchemy Row 的用法一致。"""

    def __init__(self, **fields: Any) -> None:
        self.__dict__.update(fields)


class _Result:
    def __init__(self, row: Any) -> None:
        self._row = row

    def first(self) -> Any:
        return self._row

    def scalar_one(self) -> Any:  # pragma: no cover - 本文件不用
        return self._row


def _definition_slots(slot_type: str = "definition") -> dict[str, Any]:
    """三组 typed slot 列。`slot_type != "definition"` ⇒ 判据 A 为假。"""
    fields: dict[str, Any] = {}
    for slot in ("template", "instrumentation", "contract"):
        fields[f"{slot}_slot_type"] = slot_type
        fields[f"{slot}_slot_ref"] = f"{slot}-ref"
        fields[f"{slot}_slot_digest"] = f"{slot}-digest"
    return fields


class _SupplySession:
    """三条 SQL 各给一行（或 None）的替身 session。

    Args:
        bundle_row: 判据 A 的行；`None` ⇒ 无 approved projection bundle。
        entry_state_row: 判据 B 的行；`None` ⇒ 该 (wp, entry) 无 current representation。
        representation_row: 判据 C/D 的行；`None` ⇒ representation 悬挂（外键指向空）。
    """

    def __init__(
        self,
        *,
        bundle_row: Any = None,
        entry_state_row: Any = None,
        representation_row: Any = None,
    ) -> None:
        self.bundle_row = bundle_row
        self.entry_state_row = entry_state_row
        self.representation_row = representation_row
        self.executed: list[str] = []

    async def execute(self, clause: Any, params: Any = None) -> _Result:
        sql = str(clause)
        self.executed.append(sql)
        if "working_paper_sync_definition_bundle b" in sql and "JOIN" in sql:
            if "working_paper_content_representation" in sql:
                return _Result(self.representation_row)
            return _Result(self.bundle_row)
        if "working_paper_sync_entry_state" in sql:
            return _Result(self.entry_state_row)
        if "working_paper_content_representation" in sql:
            return _Result(self.representation_row)
        raise AssertionError(f"替身 session 收到未预期的 SQL:\n{sql}")


def _observe(session: Any, entry_id: str = "xlsx/gt-h1-fixed-assets") -> R.LaneSupplyFacts:
    import uuid

    return asyncio.run(
        R.observe_lane_supply(
            session=session,
            project_id=uuid.uuid4(),
            wp_id=uuid.uuid4(),
            entry_id=entry_id,
        )
    )


# ═══════════════════════════════════════════════════════════════════════════
# Property 7：「已 provision bundle」不蕴含「供给成立」
# ═══════════════════════════════════════════════════════════════════════════


class TestProvisionedBundleDoesNotImplySupply:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 7: 「已 provision bundle」不蕴含「供给成立」**

    **Validates: Requirements 2.5**

    这一条是本 spec 立项材料的硬要求：Task 76 把 bundle provision 出来之后，很容易
    把「bundle 在位」当成「首版已落成」。四个 pilot entry 里有三个正处于这个状态 ——
    判据 A 真、B/C/D 全假。
    """

    def test_criterion_a_true_and_b_false_is_not_satisfied(self) -> None:
        facts = _observe(
            _SupplySession(
                bundle_row=_Row(
                    bundle_id="b-1", bundle_sha256="deadbeef", **_definition_slots()
                ),
                entry_state_row=None,
            )
        )
        assert facts.projection_bundle_provisioned is True, (
            "替身给了 approved projection bundle 行，判据 A 却为假 —— "
            "要么 SQL 分派错位，要么 slot 判据没读 is_definition"
        )
        assert facts.published_representation_current is False
        assert facts.supply_satisfied is False, (
            "bundle 在位就被判「供给成立」—— 那正是本 spec 要拆开的两件事"
        )

    def test_gap_text_names_a_satisfied_and_b_unsatisfied_together(self) -> None:
        """诊断文本**同时**点明「A 已满足」与「B 未满足」（Requirement 2.5 原文）。"""
        facts = _observe(
            _SupplySession(
                bundle_row=_Row(
                    bundle_id="b-1", bundle_sha256="deadbeef", **_definition_slots()
                )
            )
        )
        text = R.describe_supply_gap(facts)
        assert text is not None
        assert "判据 A" in text and "已满足" in text, text
        assert "判据 B" in text and "未满足" in text, text

    def test_non_definition_slots_make_criterion_a_false(self) -> None:
        """slot 是 marker（非 definition）⇒ 判据 A 为假。

        这一条守的是「bundle 行存在」被当成「bundle 可用」：opaque bundle 的 contract
        slot 是版本化 typed null marker，行同样在，但它不是 definition。
        """
        facts = _observe(
            _SupplySession(
                bundle_row=_Row(
                    bundle_id="b-1",
                    bundle_sha256="deadbeef",
                    **_definition_slots("typed_null_marker/v1"),
                )
            )
        )
        assert facts.projection_bundle_provisioned is False, (
            "三个 slot 都是 typed null marker，判据 A 仍为真 —— is_definition 没被读"
        )

    def test_a_single_marker_slot_is_enough_to_fail_criterion_a(self) -> None:
        """**任一** slot 非 definition 即判据 A 为假（三 slot 全部必需）。"""
        for spoiled in ("template", "instrumentation", "contract"):
            fields = _definition_slots()
            fields[f"{spoiled}_slot_type"] = "marker"
            facts = _observe(
                _SupplySession(
                    bundle_row=_Row(bundle_id="b", bundle_sha256="d", **fields)
                )
            )
            assert facts.projection_bundle_provisioned is False, (
                f"{spoiled} slot 是 marker 时判据 A 仍为真 —— 三 slot 并非全部必需"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Property 8：判据 A 与判据 C 的取数语义互不重叠
# ═══════════════════════════════════════════════════════════════════════════


class TestCriterionAAndCReadDifferentSources:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 8: 判据 A 与判据 C 的取数语义互不重叠**

    **Validates: Requirements 2.2, 2.7, 2.8**
    """

    _OPAQUE_TYPE = "opaque_single_onlyoffice"

    def test_representation_bound_to_an_opaque_bundle_fails_criterion_c(self) -> None:
        """🔴 D2 那类情形的直接落点：有 current representation，但它绑的是 opaque bundle。

        判据 B 真（有 representation）、判据 C 假（它不是 projection_contract）。
        若 C 复用了 A 的取数（按 entry 正查 projection bundle），这里会错判为真。
        """
        facts = _observe(
            _SupplySession(
                bundle_row=_Row(
                    bundle_id="b-projection",
                    bundle_sha256="aaaa",
                    **_definition_slots(),
                ),
                entry_state_row=_Row(representation_id="r-1", generation=1),
                representation_row=_Row(
                    representation_id="r-1",
                    bundle_id="b-opaque",
                    authority_model_type=self._OPAQUE_TYPE,
                    contract_slot_digest="",
                    contract_slot_type="typed_null_marker/v1",
                ),
            )
        )
        assert facts.projection_bundle_provisioned is True, "判据 A 应真（bundle 在位）"
        assert facts.published_representation_current is True, "判据 B 应真"
        assert facts.representation_follows_projection_contract is False, (
            "current representation 绑的是 opaque bundle，判据 C 仍为真 —— "
            "C 复用了 A 的取数（按 entry 正查），而它应当从 representation **反查**"
        )
        assert facts.representation_contract_digest_matches is False, (
            "C 为假时 D 不应为真 —— opaque bundle 的 contract slot 是 typed null marker"
        )
        assert facts.supply_satisfied is False

    def test_criterion_c_reads_the_representation_not_the_entry(self) -> None:
        """结构判据：三条 SQL 真的都被发过，且 C/D 那条按 representation 主键取。"""
        session = _SupplySession(
            bundle_row=_Row(bundle_id="b", bundle_sha256="a", **_definition_slots()),
            entry_state_row=_Row(representation_id="r-9", generation=2),
            representation_row=_Row(
                representation_id="r-9",
                bundle_id="b2",
                authority_model_type=self._OPAQUE_TYPE,
                contract_slot_digest="x",
                contract_slot_type="definition",
            ),
        )
        _observe(session)
        assert len(session.executed) == 3, (
            f"只发了 {len(session.executed)} 条 SQL —— 四条判据不是各自独立取数"
        )
        joined = "\n".join(session.executed)
        assert "working_paper_sync_definition_bundle" in joined
        assert "working_paper_sync_entry_state" in joined
        assert "working_paper_content_representation" in joined
        cd_sql = next(
            s for s in session.executed if "working_paper_content_representation" in s
        )
        assert "r.id = :representation_id" in cd_sql, (
            "判据 C/D 的 SQL 不是按 representation 主键取 —— "
            f"它可能又按 entry 正查了一遍:\n{cd_sql}"
        )

    def test_projection_bundle_with_matching_digest_satisfies_c_and_d(self) -> None:
        """正例（非空分母）：representation 绑 projection bundle 且 digest 相符 ⇒ 四条全真。

        没有这一条时，上面几条「C 为假」可能只是因为 C 恒假。
        """
        from app.services.workpaper_sync.models import AuthorityModel

        entry_id = "xlsx/gt-h1-fixed-assets"
        contract_id = R._contract_id_for_entry(entry_id)
        disk_digest = R._disk_contract_canonical_digest(contract_id)
        facts = _observe(
            _SupplySession(
                bundle_row=_Row(
                    bundle_id="b", bundle_sha256="a", **_definition_slots()
                ),
                entry_state_row=_Row(representation_id="r-1", generation=1),
                representation_row=_Row(
                    representation_id="r-1",
                    bundle_id="b",
                    authority_model_type=AuthorityModel.projection_contract.value,
                    contract_slot_digest=disk_digest,
                    contract_slot_type="definition",
                ),
            ),
            entry_id,
        )
        assert facts.supply_satisfied is True, (
            "四条判据俱备的正例仍判供给不成立 —— "
            f"{R.describe_supply_gap(facts)}"
        )

    def test_digest_mismatch_fails_only_criterion_d(self) -> None:
        """digest 不符 ⇒ **只有** D 为假（A/B/C 仍真）—— 四条互不遮蔽。"""
        from app.services.workpaper_sync.models import AuthorityModel

        facts = _observe(
            _SupplySession(
                bundle_row=_Row(
                    bundle_id="b", bundle_sha256="a", **_definition_slots()
                ),
                entry_state_row=_Row(representation_id="r-1", generation=1),
                representation_row=_Row(
                    representation_id="r-1",
                    bundle_id="b",
                    authority_model_type=AuthorityModel.projection_contract.value,
                    contract_slot_digest="0" * 64,  # 与磁盘契约不符
                    contract_slot_type="definition",
                ),
            )
        )
        assert (
            facts.projection_bundle_provisioned,
            facts.published_representation_current,
            facts.representation_follows_projection_contract,
            facts.representation_contract_digest_matches,
        ) == (True, True, True, False)
        text = R.describe_supply_gap(facts)
        assert text is not None and "判据 D" in text


# ═══════════════════════════════════════════════════════════════════════════
# Property 9（补强）：三种致错情形各一例
# ═══════════════════════════════════════════════════════════════════════════


class TestObservationErrorsAreNeverDegraded:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 9: 供给观测的异常不被降级为假值**

    **Validates: Requirements 2.6**

    tasks.md 2.3 要求「表缺失 / 外键悬挂 / session 抛错」三种致错情形各一例。
    上面 `TestObservationFailureIsNotDegraded` 只覆盖了第三种。
    """

    def test_missing_table_raises(self) -> None:
        """表缺失（`UndefinedTable` 形态）⇒ 抛，不返回四条皆假。"""

        class _MissingTableSession:
            async def execute(self, *_a: Any, **_k: Any) -> Any:
                raise RuntimeError(
                    'relation "working_paper_sync_definition_bundle" does not exist'
                )

        with pytest.raises(R.LaneSupplyObservationError) as caught:
            _observe(_MissingTableSession())
        assert "does not exist" in str(caught.value)

    def test_dangling_foreign_key_is_not_silently_false(self) -> None:
        """外键悬挂：entry_state 指向的 representation 查不到。

        🔴 这一条的结论**不是**「抛异常」而是「四条不得全假、且 B 仍为真」——
        悬挂是**数据**事实（representation 被删而 pointer 未清），不是取数故障。
        判据要求它可与「本来就没发过首版」区分：后者 B 为假。
        """
        facts = _observe(
            _SupplySession(
                bundle_row=_Row(
                    bundle_id="b", bundle_sha256="a", **_definition_slots()
                ),
                entry_state_row=_Row(representation_id="r-gone", generation=1),
                representation_row=None,  # 反查不到 ⇒ 悬挂
            )
        )
        assert facts.published_representation_current is True, (
            "pointer 在但 representation 查不到时判据 B 被判假 —— "
            "「悬挂」与「从未发布」被混成同一格，前者需要人工清理而后者是正常起点"
        )
        assert facts.representation_follows_projection_contract is False
        assert facts.supply_satisfied is False
        text = R.describe_supply_gap(facts)
        assert text is not None and "判据 C" in text

    def test_session_raising_on_the_second_query_still_raises(self) -> None:
        """第一条 SQL 成功、第二条抛错 ⇒ 仍抛（不是只包了第一条）。"""

        class _LateFailureSession(_SupplySession):
            def __init__(self) -> None:
                super().__init__(
                    bundle_row=_Row(
                        bundle_id="b", bundle_sha256="a", **_definition_slots()
                    )
                )
                self.calls = 0

            async def execute(self, clause: Any, params: Any = None) -> _Result:
                self.calls += 1
                if self.calls >= 2:
                    raise RuntimeError("模拟第二条 SQL 失败：连接中断")
                return await super().execute(clause, params)

        session = _LateFailureSession()
        with pytest.raises(R.LaneSupplyObservationError) as caught:
            _observe(session)
        assert session.calls >= 2, "第二条 SQL 根本没被发出 —— 判据构造无效"
        assert "连接中断" in str(caught.value)

    def test_reverse_self_check_returning_false_would_be_caught(self) -> None:
        """反向自检：把实现改成 `return False` 形态后本类必须打红。

        判据落在**结构**上：`observe_lane_supply` 的每个 except 分支都必须以 `raise`
        结尾（而不是构造一个四条皆假的 `LaneSupplyFacts` 返回）。
        """
        source = _MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "observe_lane_supply"
        )
        handlers = [h for h in ast.walk(node) if isinstance(h, ast.ExceptHandler)]
        assert handlers, "没有 except 分支"
        for handler in handlers:
            terminal = handler.body[-1]
            assert isinstance(terminal, ast.Raise), (
                f"第 {handler.lineno} 行的 except 分支以 "
                f"{type(terminal).__name__} 收尾而不是 raise —— "
                "取数失败被降级成了某个返回值"
            )


class TestAuthorityLogicalSuffixMatchesProviders:
    """**Validates: Requirements 3.2, 6.9**"""

    def test_suffix_agrees_with_every_provider(self) -> None:
        checked = R.assert_authority_logical_suffix_matches_providers()
        assert len(checked) >= 4, (
            f"只核对了 {len(checked)} 个 provider 的 authority logical_id 后缀，分母过小"
        )

    def test_logical_id_is_derived_not_hardcoded(self) -> None:
        """`authority_model_logical_id` 由 contract_id 派生。"""
        assert (
            R.authority_model_logical_id("d2.receivable_detail")
            == "d2.receivable_detail.authority-model"
        )
        assert (
            R.authority_model_logical_id("g7.soe_subsidiary_disclosure")
            == "g7.soe_subsidiary_disclosure.authority-model"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 1：lane 裁决三值封闭且确定
# ═══════════════════════════════════════════════════════════════════════════


def _entry_id_strategy() -> st.SearchStrategy[str]:
    """三类 entry_id 混合生成器（tasks.md 1.2 的三类覆盖要求）。

    1. 由每条 opaque lane 的 `entry_id_source` 形态**现造**的（不手写前缀）；
    2. manifest 里真实存在的；
    3. 两者皆不在的任意字符串。
    """
    opaque = st.builds(
        _real_opaque_entry_id,
        wp_code=st.one_of(st.none(), st.sampled_from(["H1", "D2", "G7", "B60"])),
    )
    real = st.sampled_from(sorted(_manifest_entry_ids()) or ["xlsx/gt-h1-fixed-assets"])
    junk = st.text(min_size=0, max_size=40)
    return st.one_of(opaque, real, junk)


def _manifest_entry_ids() -> tuple[str, ...]:
    from app.services.workpaper_sync.adapters.registry import manifest_entries_by_id
    from app.services.workpaper_sync.entry_profile import load_entry_manifest

    return tuple(manifest_entries_by_id(load_entry_manifest()))


class TestVerdictDomainIsClosedAndDeterministic:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 1: lane 裁决三值封闭且确定**

    **Validates: Requirements 1.1, 1.2, 1.6**
    """

    @settings(max_examples=200, deadline=None)
    @given(entry_id=_entry_id_strategy())
    def test_verdict_is_always_inside_the_closed_domain(self, entry_id: str) -> None:
        """任意 entry_id 的裁决都落在三值枚举内 —— 没有第四种出口。"""
        verdict = R.adjudicate_lane(entry_id)
        assert isinstance(verdict, R.LaneVerdict)
        assert verdict in set(R.LaneVerdict)

    #: 确定性判据的重复次数。
    #:
    #: 🔴 **不是 2**。变异检验（把 `adjudicate_lane` 换成
    #: `random.choice(list(LaneVerdict))`）实测：只调两次时「恰好抽到同值」的概率是
    #: 1/3，本判据于是靠运气打红 —— 那不是判据，是抽奖。三值域下 12 次的漏检概率
    #: 是 3 × (1/3)**11 ≈ 1.7e-5，且每条 hypothesis 例都独立重跑一次。
    _DETERMINISM_REPEATS = 12

    @settings(max_examples=200, deadline=None)
    @given(entry_id=_entry_id_strategy())
    def test_repeated_adjudication_is_identical(self, entry_id: str) -> None:
        """同一 entry_id + 同一 manifest 快照重复裁决结果相同（Requirement 1.2）。

        判据用**同一份** manifest 对象反复喂：换对象比不出「裁决是否引入了随机性 /
        隐式全局状态」—— 那是本条要排除的形态。
        """
        snapshot = _MANIFEST_SNAPSHOT
        verdicts = {
            R.adjudicate_lane(entry_id, manifest=snapshot)
            for _ in range(self._DETERMINISM_REPEATS)
        }
        assert len(verdicts) == 1, (
            f"{entry_id!r}: {self._DETERMINISM_REPEATS} 次裁决得到 "
            f"{sorted(v.value for v in verdicts)} —— 裁决不确定"
        )

    def test_three_input_classes_are_all_exercised(self) -> None:
        """自证分母：三类 entry_id 各自真的产出了不同结论。

        没有这一条时，生成器完全可能只抽到 junk（全 undecided），
        「三值封闭」就在一个值上恒真。
        """
        opaque = R.adjudicate_lane(_real_opaque_entry_id())
        projection = R.adjudicate_lane(_delivered_entry_ids()[0])
        undecided = R.adjudicate_lane("xlsx/definitely-not-a-manifest-entry")
        assert {opaque, projection, undecided} == set(R.LaneVerdict), (
            f"三类输入只覆盖到 {sorted(v.value for v in {opaque, projection, undecided})}"
            " —— 三值域里有格子从未被走到，封闭性判据分母不足"
        )

    def test_determinism_survives_a_reordered_manifest(self) -> None:
        """把 manifest 的 entry 顺序打乱，结论不变 —— 裁决不依赖字典序。"""
        entries = dict(_MANIFEST_BY_ID)
        shuffled = {k: entries[k] for k in reversed(list(entries))}
        for entry_id in _delivered_entry_ids():
            assert R.adjudicate_lane(
                entry_id, manifest={"entries": list(entries.values())}
            ) is R.adjudicate_lane(
                entry_id, manifest={"entries": list(shuffled.values())}
            ), entry_id


# ═══════════════════════════════════════════════════════════════════════════
# Property 17：L1 的顺序门不可交换
# ═══════════════════════════════════════════════════════════════════════════


class TestLaneOrderIsNotCommutable:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 17: L1 的顺序门不可交换**

    **Validates: Requirements 1.3**

    🔴 tasks.md 对本条有一句特别要求：判据必须落在「**打红的恰是 Property 2 那条
    测试**」而非「有测试打红」。差别是实质的 —— 后者可以由任何一条无关判据满足，
    于是「L1 顺序被交换」这件事本身没有被任何东西盯住。

    落法：把 L1 的判据函数 `_is_opaque_entry_id` 短路成恒假（这**等价于**把 L1 排到
    L2 之后：opaque entry_id 永不在 manifest 里，于是它会先撞 L2 的 undecided），
    然后**在进程内直接调用** Property 2 的那几条测试方法，逐条断言它们抛
    `AssertionError`；同时断言另一条属性（Property 6）**仍通过**。
    """

    #: 交换 L1 顺序后必须打红的 Property 2 测试（行为侧，不含源码序那条 —— 短路判据
    #: 函数不改源码行号，那条本就不该因此变红）。
    _PROPERTY_2_BEHAVIOURAL_TESTS = (
        "test_opaque_entry_id_is_adjudicated_opaque",
        "test_opaque_verdict_holds_even_with_an_empty_manifest",
        "test_real_opaque_representation_entry_is_opaque",
    )

    def test_reordering_l1_reddens_exactly_the_property_2_tests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(R, "_is_opaque_entry_id", lambda entry_id: False)

        subject = TestLaneOrderIsLoadBearing()
        reddened: list[str] = []
        for name in self._PROPERTY_2_BEHAVIOURAL_TESTS:
            try:
                getattr(subject, name)()
            except AssertionError:
                reddened.append(name)
        assert reddened == list(self._PROPERTY_2_BEHAVIOURAL_TESTS), (
            "把 L1 判据短路成恒假后，Property 2 的行为判据没有全部打红："
            f"红 {reddened}、应红 {list(self._PROPERTY_2_BEHAVIOURAL_TESTS)} —— "
            "说明「opaque entry 恒判 opaque」并没有真的被这些判据盯住"
        )

    def test_reordering_l1_does_not_redden_an_unrelated_property(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """对照组：Property 6（供给合取）不受 L1 顺序影响，必须仍通过。

        这一条把上一条的「恰是」钉死：若交换 L1 会让**任何**判据都打红，
        那「打红的恰是 Property 2」就没有区分力。
        """
        monkeypatch.setattr(R, "_is_opaque_entry_id", lambda entry_id: False)
        supply = TestSupplyRequiresAllFourCriteria()
        supply.test_all_true_is_satisfied()
        supply.test_all_sixteen_states_are_actually_exercised()

    def test_opaque_entry_would_be_undecided_if_l1_came_second(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """交换后的实际结论是 `undecided`（不是别的什么）—— 顺序门的后果可指名。

        `undecided` ⇒ 首版入口的 `assert_projection_lane` 会抛 `lane_undecided`
        而不是 `lane_is_opaque`，于是「这是 opaque 底稿」这条事实在诊断里消失。
        """
        entry_id = _real_opaque_entry_id()
        assert R.adjudicate_lane(entry_id) is R.LaneVerdict.opaque
        monkeypatch.setattr(R, "_is_opaque_entry_id", lambda eid: False)
        assert R.adjudicate_lane(entry_id) is R.LaneVerdict.undecided
        with pytest.raises(R.LaneUndecidedError):
            R.assert_projection_lane(entry_id)
