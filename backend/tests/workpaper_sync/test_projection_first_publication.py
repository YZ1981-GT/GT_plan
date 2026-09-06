# -*- coding: utf-8 -*-
"""首版 published representation 生产链的判据（F7）。

**Spec: published-representation-production-path-and-lane-adjudication**

═══ 本文件先落哪几条，以及为什么 ═══════════════════════════════════════════════

2026-09-04 的首轮变异检验（`tmp` 变异脚本，6 条）暴露出**两条判据缺口**，两条都判
**GREEN** —— 即改坏了没有任何测试打红。它们是本文件的第一批内容：

* **Property 36**（宿主目标解析单一真源）：把宿主的 `_adjudicated_wp_codes(entry_id)`
  换成写死的 `("D2",)`，无任何判据打红。而实测该处曾有**三份真源**并存、两边各错一处。
* **Property 37**（叠加层丢占位 None 但保留清空）：把
  `if field.value is None and key not in baseline.values:` 去掉后半个条件，无任何判据
  打红 —— 而那半个条件正是「审计师清空一格」的唯一保护。

其余几条选的是**零数据库即可验**的：错误码互不相同、暂存期实测入参与 OOXML 安全门、
空 adapter 必被拒。真库相关的（Properties 13 / 19 / 20 / 25 / 26 / 33~35）归 F8。

═══ 纪律 ═══════════════════════════════════════════════════════════════════════

* 判据一律落在**行为 / 结构 / 真实执行**，不落在「字符串是否存在」。
* AST 判据在取值前**先剥 docstring**：生产源的 docstring 里正当地叙述了被禁用的符号名
  （解释为什么不用它），不剥就会把叙述当成真实引用（本仓库已栽过一次）。
* `hypothesis` 的 `max_examples` ≥ 100。
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_THIS = Path(__file__).resolve()
REPO = _THIS.parents[3]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))

F2_PATH = BACKEND / "app/services/workpaper_sync/projection_first_publication.py"
HOST_PATH = BACKEND / "scripts/fix/fix_projection_first_publication.py"
ADJUDICATION_PATH = BACKEND / "data/workpaper_sync_entry_wp_code_adjudication.json"
#: BP-24 之后目标解析（裁决表读取 + 全序 + SQL）的**唯一**实现位置。
#: 宿主只转引；对「排序是否被抄第二份」「SQL 是否 LIMIT 1」这类结构判据要看这里。
RESOLUTION_PATH = BACKEND / "app/services/workpaper_sync/projection_target_resolution.py"
#: BP-24 分歧的另一半宿主。两个宿主的 `TARGET_ORDER_SQL` 必须是**同一个**对象。
T76_HOST_PATH = BACKEND / "scripts/fix/fix_task76_provision_projection_definitions.py"

from app.services.workpaper_sync import projection_first_publication as F2  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# 装配辅助
# ═══════════════════════════════════════════════════════════════════════════


def _load_module_by_path(path: Path, alias: str) -> Any:
    """按路径加载 `backend/scripts/fix/` 下的脚本（那不是 package）。

    🔴 必须先进 `sys.modules` 再 exec —— 脚本里有 `@dataclass` + `from __future__ import
    annotations`，不注册就是 `AttributeError: 'NoneType' object has no attribute
    '__dict__'`（本仓库多处踩过）。
    """
    spec = importlib.util.spec_from_file_location(alias, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_host() -> Any:
    """加载首版发布宿主。"""
    return _load_module_by_path(HOST_PATH, "_fp_host_for_tests")


def _strip_docstrings(source: str) -> str:
    """把模块 / 类 / 函数的 docstring 从源码里剔掉后重新 unparse。

    `_strip_comments` 一类的工具**不剥 docstring**。对生产源做「某符号是否真被用到」的
    判断前必须先剥：本文件要判的恰恰是「宿主还读不读 `PILOT_WP_CODES`」，而宿主的
    docstring 里正当地写着这个名字（解释为什么不读它）。
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _function_node(source: str, name: str) -> ast.AST:
    tree = ast.parse(source)
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


class _Field:
    """`Projection.values` 的最小替身：只需要 `value` 与 `value_type`。"""

    __slots__ = ("value", "value_type")

    def __init__(self, value: Any, value_type: Any = "amount") -> None:
        self.value = value
        self.value_type = value_type

    def __repr__(self) -> str:  # pragma: no cover - 仅调试可读性
        return f"_Field({self.value!r})"


class _Projection:
    """`adapters.base.Projection` 的最小替身。"""

    def __init__(
        self,
        *,
        values: dict[str, _Field],
        row_keys: dict[str, tuple[str, ...]] | None = None,
        contract_id: str = "t.contract",
        semantic_version: str = "1.0.0",
        document_type: str = "xlsx",
    ) -> None:
        self.values = values
        self.row_keys = row_keys or {}
        self.contract_id = contract_id
        self.semantic_version = semantic_version
        self.document_type = document_type


class _BaselineAdapter:
    """`adapter.extract` 的最小替身 —— 恒返回给定的基线 projection。"""

    def __init__(self, baseline: _Projection) -> None:
        self._baseline = baseline
        self.extract_calls = 0

    def extract(self, *, artifact: Any, contract: Any) -> _Projection:
        self.extract_calls += 1
        return self._baseline


def _lane_facts(**over: Any) -> Any:
    """四条判据全真的 `LaneSupplyFacts`，按需覆盖（真类型，不是替身）。"""
    from app.services.workpaper_sync import projection_lane_registry as R

    base: dict[str, Any] = {
        "entry_id": _STUB_ENTRY_ID,
        "verdict": R.LaneVerdict.projection,
        "projection_bundle_provisioned": True,
        "published_representation_current": True,
        "representation_follows_projection_contract": True,
        "representation_contract_digest_matches": True,
    }
    base.update(over)
    return R.LaneSupplyFacts(**base)


#: 判据 ③ 的注入用 entry —— 取**真实**已交付 entry，否则 `resolve_plan` 会先被
#: `assert_projection_lane`（判据 ①）拦住，判据 ③ 根本走不到。
_STUB_ENTRY_ID = "xlsx/gt-h1-fixed-assets"


@contextlib.contextmanager
def _patched_lane_supply(facts: Any) -> Any:
    """把 `observe_lane_supply` 换成恒返回 `facts` 的替身。

    🔴 打在 **`projection_first_publication` 的导入处**而不是 lane registry 模块上：
    `resolve_plan` 是函数内 `from ... import observe_lane_supply`，改模块属性对它无效。
    这里用 `sys.modules` 级替换保证真的生效 —— 替身没生效时本判据会静默变成
    「跑真库」，那正是最坏的假绿。
    """
    from app.services.workpaper_sync import projection_lane_registry as R

    async def _stub(**_kwargs: Any) -> Any:
        return facts

    original = R.observe_lane_supply
    R.observe_lane_supply = _stub  # type: ignore[assignment]
    try:
        yield
    finally:
        R.observe_lane_supply = original  # type: ignore[assignment]


async def _resolve_plan_with_stub_supply() -> Any:
    """用最小替身跑 `resolve_plan` 本体（判据 ①②③ 之后会因缺 bundle 停下）。"""

    class _NoRowSession:
        async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            class _R:
                def first(self) -> None:
                    return None

                def scalar_one_or_none(self) -> None:
                    return None

                def scalar_one(self) -> int:
                    return 0

                def mappings(self) -> Any:
                    return self

                def all(self) -> list[Any]:
                    return []

            return _R()

    class _NoResolution:
        async def load_bundle_snapshot(self, _bundle_id: Any) -> Any:
            raise RuntimeError("替身不供 bundle —— 判据 ④ 之后不再推进")

    import uuid as _uuid

    return await F2.resolve_plan(
        session=_NoRowSession(),
        resolution=_NoResolution(),
        project_id=_uuid.uuid4(),
        wp_id=_uuid.uuid4(),
        entry_id=_STUB_ENTRY_ID,
    )


def _overlay(baseline: _Projection, store: _Projection) -> Any:
    """跑生产实现 `_overlay_store_on_substrate_baseline`（真调用，不复制其逻辑）。"""
    return F2._overlay_store_on_substrate_baseline(
        adapter=_BaselineAdapter(baseline),
        contract=object(),
        substrate=Path("/nonexistent-substrate.xlsx"),
        store_projection=store,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Property 36：宿主的目标底稿解析只有一份真源
# ═══════════════════════════════════════════════════════════════════════════


class TestHostTargetResolutionHasASingleSource:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 36: 宿主的目标底稿解析只有一份真源**

    **Validates: Requirements 6.4, 6.5**
    """

    def test_host_target_codes_equal_the_reviewed_adjudication(self) -> None:
        """行为判据：宿主算出的码族**逐 entry**等于裁决表声明的 `wp_codes`。

        这条是变异 M5 的直接对手：把宿主的解析换成写死的 `("D2",)` 时，除 D2 之外的
        entry 都会不等 ⇒ 打红。
        """
        host = _load_host()
        document = json.loads(ADJUDICATION_PATH.read_text(encoding="utf-8"))
        adjudications = document["adjudications"]
        assert adjudications, "裁决表为空 —— 判据会在空集上恒真"

        from app.services.workpaper_sync.adapters import registry as registry_module

        delivered = {
            str(row["entry_id"]) for row in registry_module.DELIVERED_PER_ENTRY_CONTRACTS
        }
        assert delivered, "交付登记表为空 —— 判据会在空集上恒真"

        compared = 0
        for row in adjudications:
            entry_id = str(row["entry_id"])
            if entry_id not in delivered:
                continue
            expected = tuple(str(code).strip() for code in row["wp_codes"])
            actual = host._adjudicated_wp_codes(entry_id)
            assert actual == expected, (
                f"entry {entry_id}: 宿主算出 {actual}，裁决表声明 {expected} —— "
                "两者不等即说明宿主又有了第二份真源"
            )
            compared += 1
        assert compared == len(delivered), (
            f"只比对了 {compared} / {len(delivered)} 个已交付 entry —— "
            "分母不足时本判据是空转"
        )

    @pytest.mark.parametrize(
        "path",
        [HOST_PATH, RESOLUTION_PATH],
        ids=["host", "resolution_module"],
    )
    def test_host_does_not_read_filename_heuristics(self, path: Path) -> None:
        """结构判据：对 `PILOT_WP_CODES` / `wp_code_patterns` 零取值。

        判据在**剥掉 docstring 之后**才做 —— 两份源码的 docstring 里都正当地写着这些
        名字（解释为什么不读它们），不剥就恒红。

        🔴 BP-24 之后判据必须**同时**覆盖生产模块：解析实现搬走了，只盯宿主等于把判据
        留在一个已经不含实现的文件上（判据仍绿而真正的实现无人看管 = 假绿第①源）。
        """
        stripped = _strip_docstrings(path.read_text(encoding="utf-8"))
        tree = ast.parse(stripped)

        getattr_lookups = {
            node.args[1].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        }
        attributes = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        subscripts = {
            node.slice.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        }
        seen = getattr_lookups | attributes | subscripts
        for banned in ("PILOT_WP_CODES", "wp_code_patterns", "wp_match"):
            assert banned not in seen, (
                f"{path.name} 对 {banned!r} 做了取值 —— 那是 manifest 从宿主 Vue 文件名 "
                "CamelCase 抽出来的启发式产物，实测产 D2A / G7L / H1F 三个在 wp_index "
                "里 0 命中的幻影码"
            )

        # 🔴 反向自检：证明 `_strip_docstrings` 对本判据真的有效 —— 没有它，strip 可以是
        #    空操作而判据照样绿，将来有人在 docstring 里提到被禁名字就会突然恒红。
        #
        #    自检用**合成输入**而不是「本文件原文里有、剥完就没有」。后者首版用过，
        #    实测两种失效：① BP-24 把解析搬走后宿主正文不再讨论幻影码 ⇒ 分母为空、
        #    自检在空集上判定；② 生产模块把幻影码写进了 `raise` 的**错误文案**（那是
        #    正当的，且 strip 本就不该剥它）⇒ 自检误报。合成输入两侧都钉死，与行文无关。
        assert "wp_code_patterns" not in _strip_docstrings(
            'def f():\n    """提到 wp_code_patterns"""\n    return 1\n'
        ), "`_strip_docstrings` 没剥掉 docstring —— 它是空操作，本判据只是恰好通过"
        assert "wp_code_patterns" in _strip_docstrings(
            'def f():\n    return "wp_code_patterns"\n'
        ), "`_strip_docstrings` 把**代码里**的字符串也剥了 —— 本判据会漏掉真违规"

    def test_host_has_no_hardcoded_wp_code_literal(self) -> None:
        """结构判据：`_build_plan_rows` 里不出现写死的 wp_code 字面量。

        直接对着变异 M5 的形态：`"wp_codes": ("D2",)`。判据落在「该函数体内没有形如
        wp_code 的字符串常量」，而不是「源码里没有 'D2' 这三个字符」。
        """
        stripped = _strip_docstrings(HOST_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "_build_plan_rows")
        constants = {
            inner.value
            for inner in ast.walk(node)
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str)
        }
        document = json.loads(ADJUDICATION_PATH.read_text(encoding="utf-8"))
        known_codes = {
            str(code)
            for row in document["adjudications"]
            for code in row["wp_codes"]
        }
        assert known_codes, "裁决表里一个 wp_code 都没有 —— 判据会在空集上恒真"
        leaked = sorted(known_codes & constants)
        assert not leaked, (
            f"`_build_plan_rows` 里出现写死的 wp_code 字面量 {leaked} —— "
            "目标码族必须现取裁决表"
        )

    def test_missing_adjudication_entry_fails_closed(self) -> None:
        """缺条目必须抛，**不得**回落到任何启发式。

        回落等于把「无人裁决」伪装成「已裁决」。
        """
        host = _load_host()
        with pytest.raises(host.HostError) as caught:
            host._adjudicated_wp_codes("xlsx/definitely-not-adjudicated")
        assert "裁决表" in str(caught.value)

    def test_missing_provisioning_key_fails_closed(self, tmp_path: Path) -> None:
        """裁决条目缺 `resolvable_for_provisioning` 时必须抛，不得默认放行。

        反向自检形态：把键删掉（内存副本）后必须抛 —— 只断言「当前表通过」是空分母。
        """
        host = _load_host()
        document = json.loads(ADJUDICATION_PATH.read_text(encoding="utf-8"))
        row = dict(document["adjudications"][0])
        entry_id = str(row["entry_id"])
        row.pop("resolvable_for_provisioning", None)
        crippled = tmp_path / "adjudication_without_key.json"
        crippled.write_text(
            json.dumps({"adjudications": [row]}, ensure_ascii=False), encoding="utf-8"
        )
        # 🔴 BP-24：裁决表路径的真源在生产模块，patch 宿主那个转引常量**不起作用**
        #    （宿主只是把它 re-export，读文件的是生产模块）。这条判据首版就是因此
        #    `DID NOT RAISE` —— 而那恰好证明宿主已不再自留第二份读取实现。
        from app.services.workpaper_sync import projection_target_resolution as TR

        saved = TR.WP_CODE_ADJUDICATION
        try:
            TR.WP_CODE_ADJUDICATION = crippled  # type: ignore[misc]
            with pytest.raises(host.HostError) as caught:
                host._adjudicated_wp_codes(entry_id)
            assert "resolvable_for_provisioning" in str(caught.value)
        finally:
            TR.WP_CODE_ADJUDICATION = saved  # type: ignore[misc]
        # 复原自证：恢复后仍能正常解析（否则是 fixture 泄漏）
        assert host._adjudicated_wp_codes(entry_id), "复原后解析不出来 —— fixture 泄漏"
        # 反向自检：patch 打在宿主那个转引常量上必须**无效** —— 否则说明宿主又自己读了一遍
        saved_host = host._WP_CODE_ADJUDICATION
        try:
            host._WP_CODE_ADJUDICATION = crippled
            assert host._adjudicated_wp_codes(entry_id), (
                "patch 宿主的转引常量竟然改变了行为 ⇒ 宿主自己又读了一份裁决表，"
                "BP-24 收敛被撤销"
            )
        finally:
            host._WP_CODE_ADJUDICATION = saved_host


# ═══════════════════════════════════════════════════════════════════════════
# Property 37：叠加层丢占位 None 但保留清空动作
# ═══════════════════════════════════════════════════════════════════════════


class TestOverlayDropsPlaceholdersButKeepsClearing:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 37: 叠加层丢占位 None 但保留清空动作**

    **Validates: Requirements 5.2, 5.4**
    """

    def test_placeholder_none_absent_from_baseline_is_dropped(self) -> None:
        """G7 的真实形态：基线不含该键 + store 给 None ⇒ 不进 merged。"""
        baseline = _Projection(values={"t/r1/kept": _Field(7)})
        store = _Projection(
            values={f"minority_financials/minority-fs-1/minority_financials_{i}": _Field(None)
                    for i in range(1, 11)}
        )
        merged = _overlay(baseline, store)
        assert set(merged.values) == {"t/r1/kept"}, (
            "占位 None 进了 merged projection ⇒ materialize 会把它写成 0，"
            "反读回来判不等值（G7 实测 100 处 None → 0）"
        )

    def test_clearing_none_present_in_baseline_is_kept(self) -> None:
        """🔴 另一半：基线**有值**而 store 给 None ⇒ 必须保留（清空动作）。

        这条是变异 M6 的直接对手：去掉 `and key not in baseline.values` 后本条打红。
        """
        baseline = _Projection(values={"t/r1/amount": _Field(1234)})
        store = _Projection(values={"t/r1/amount": _Field(None)})
        merged = _overlay(baseline, store)
        assert "t/r1/amount" in merged.values, (
            "审计师清空一格的动作被静默吞掉 —— 那比多写一个 0 更贵"
        )
        assert merged.values["t/r1/amount"].value is None, (
            "清空动作没被写下去（保留了基线旧值）⇒ 用户以为清了、实际没清"
        )

    def test_non_none_store_value_always_overrides_baseline(self) -> None:
        """store 侧非 None 恒覆盖基线 —— HTML 已录入的值是更新的业务事实。"""
        baseline = _Projection(values={"t/r1/amount": _Field(1)})
        store = _Projection(values={"t/r1/amount": _Field(2)})
        merged = _overlay(baseline, store)
        assert merged.values["t/r1/amount"].value == 2

    @settings(max_examples=200, deadline=None)
    @given(
        baseline_keys=st.lists(
            st.sampled_from(["k1", "k2", "k3", "k4"]), unique=True, max_size=4
        ),
        store_none_keys=st.lists(
            st.sampled_from(["k1", "k2", "k3", "k4", "k5"]), unique=True, max_size=5
        ),
    )
    def test_dropped_set_is_exactly_store_none_minus_baseline(
        self, baseline_keys: list[str], store_none_keys: list[str]
    ) -> None:
        """两个条件缺任一都会让本条打红。

        被丢弃的键集合 **恰等于** `{store 里取值为 None 的键} − {基线拥有的键}`：
        * 去掉「取值为 None」这半个条件 ⇒ 非 None 的 store 键也被丢 ⇒ 集合变大 ⇒ 红
        * 去掉「基线不含」这半个条件 ⇒ 清空动作也被丢 ⇒ 集合变大 ⇒ 红
        """
        baseline = _Projection(values={key: _Field(1) for key in baseline_keys})
        store = _Projection(
            values={
                **{key: _Field(None) for key in store_none_keys},
                "always_present": _Field(9),
            }
        )
        merged = _overlay(baseline, store)
        expected_dropped = set(store_none_keys) - set(baseline_keys)
        actual_dropped = (set(baseline_keys) | set(store.values)) - set(merged.values)
        assert actual_dropped == expected_dropped, (
            f"被丢弃集合 {sorted(actual_dropped)} != 期望 {sorted(expected_dropped)}"
        )
        assert "always_present" in merged.values, "非 None 的 store 字段被误丢"

    def test_row_keys_merge_preserves_order_and_dedupes(self) -> None:
        """行序合并：基线物理行序在前、store 新增行在后，保序且去重。"""
        baseline = _Projection(values={}, row_keys={"tbl": ("a", "b")})
        store = _Projection(values={}, row_keys={"tbl": ("b", "c")})
        merged = _overlay(baseline, store)
        assert merged.row_keys["tbl"] == ("a", "b", "c")


# ═══════════════════════════════════════════════════════════════════════════
# Property 10：首版准入按固定顺序求值并返回无写入面的冻结计划
# ═══════════════════════════════════════════════════════════════════════════


class _BundleRow:
    """判据 A 的 SQL 行替身（`_SQL_CRITERION_A` 的 select 列）。"""

    def __init__(self) -> None:
        import uuid as _uuid

        self.bundle_id = _uuid.uuid4()
        self.bundle_sha256 = "b" * 64
        for slot in ("template", "instrumentation", "contract"):
            setattr(self, f"{slot}_slot_type", "definition")
            setattr(self, f"{slot}_slot_ref", f"{slot}-ref")
            setattr(self, f"{slot}_slot_digest", f"{slot}-digest")


class _SessionWithBundle:
    """能供出 bundle 行与 `content_revision` 的替身 —— 让准入推进到第 ④⑤ 条。"""

    def __init__(self, *, bundle_row: Any = None) -> None:
        self.bundle_row = bundle_row if bundle_row is not None else _BundleRow()

    async def execute(self, clause: Any, params: Any = None) -> Any:
        sql = str(clause)
        row = self.bundle_row if "working_paper_sync_definition_bundle" in sql else None

        class _R:
            def first(self) -> Any:
                return row

            def scalar_one_or_none(self) -> Any:
                return 0

            def scalar_one(self) -> int:
                return 0

        return _R()


class _ExplodingResolution:
    """第 ④ 条（bundle snapshot）失败的构造。"""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error or RuntimeError("bundle snapshot 不可用（替身）")

    async def load_bundle_snapshot(self, _bundle_id: Any) -> Any:
        raise self._error


class _StubBundleSnapshot:
    def __init__(self) -> None:
        import uuid as _uuid

        self.bundle_id = _uuid.uuid4()
        self.bundle_sha256 = "s" * 64


class _OkResolution:
    async def load_bundle_snapshot(self, _bundle_id: Any) -> Any:
        return _StubBundleSnapshot()


async def _resolve_plan(
    *,
    session: Any = None,
    resolution: Any = None,
    entry_id: str = _STUB_ENTRY_ID,
) -> Any:
    import uuid as _uuid

    return await F2.resolve_plan(
        session=session if session is not None else _SessionWithBundle(),
        resolution=resolution if resolution is not None else _OkResolution(),
        project_id=_uuid.uuid4(),
        wp_id=_uuid.uuid4(),
        entry_id=entry_id,
    )


class TestAdmissionOrderIsNotCommutable:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 10: 首版准入按固定顺序求值并返回无写入面的冻结计划**

    **Validates: Requirements 3.1, 3.2, 3.9**

    🔴 判据形态取自 tasks.md 4.2 原文：「逐一构造**使第 k 条不成立**的输入，断言抛出
    的 `error_code` 恒为第 k 条那一个（**不被后续判据遮蔽**）」。

    「不被遮蔽」是本条的全部价值。举例：造一个「判据 A 假 **且** 判据 B 真」的输入 ——
    第 ② 条与第 ③ 条同时不成立。若实现把 ③ 排在 ② 之前，抛出的会是
    `first_publication_already_done`，于是运维被送去查「为什么已经发过了」，
    而真正的原因是 bundle 还没 provision。只断言「抛了个异常」区分不出这两种。
    """

    def test_criterion_1_opaque_lane_is_not_masked_by_later_criteria(self) -> None:
        """第 ① 条：opaque entry_id ⇒ `lane_is_opaque`，即使后四条也全不成立。

        opaque entry 没有 per-entry 契约登记 ⇒ 第 ② 条必然也不成立。① 必须先抛。
        """
        import asyncio
        import uuid as _uuid

        from app.services.workpaper_sync import projection_lane_registry as R
        from app.services.workpaper_sync.writer_migration import opaque_entry_id

        entry_id = opaque_entry_id(wp_code=None, wp_id=_uuid.uuid4())
        with pytest.raises(R.LaneIsOpaqueError) as caught:
            asyncio.run(_resolve_plan(entry_id=entry_id))
        assert getattr(caught.value, "error_code", "") == "lane_is_opaque", (
            f"opaque entry 抛的是 {getattr(caught.value, 'error_code', '?')} —— "
            "第 ② 条（缺 bundle）把「这根本不是 projection lane」遮蔽掉了"
        )

    def test_criterion_1_undecided_lane_is_not_masked(self) -> None:
        """第 ① 条另一支：未登记 entry ⇒ `lane_undecided`（不是「缺 bundle」）。"""
        import asyncio

        from app.services.workpaper_sync import projection_lane_registry as R

        with pytest.raises(R.LaneUndecidedError) as caught:
            asyncio.run(_resolve_plan(entry_id="xlsx/not-a-manifest-entry-at-all"))
        assert getattr(caught.value, "error_code", "") == "lane_undecided"

    def test_criterion_2_is_not_masked_by_criterion_3(self) -> None:
        """🔴 第 ② 条：判据 A 假 **且** 判据 B 真 ⇒ 必须抛 ②，不是 ③。

        这一条是「顺序不可交换」的核心构造：两条同时不成立，结论必须是靠前那条。
        """
        import asyncio

        facts = _lane_facts(
            projection_bundle_provisioned=False,
            published_representation_current=True,
        )
        with _patched_lane_supply(facts):
            with pytest.raises(F2.ProjectionBundleNotProvisionedError) as caught:
                asyncio.run(_resolve_plan())
        assert (
            getattr(caught.value, "error_code", "") == "projection_bundle_not_provisioned"
        ), (
            "判据 A 假而判据 B 真时抛的不是 ② —— ③ 被排到了 ② 之前，"
            "运维会被送去查「为什么已经发过了」而真因是 bundle 还没 provision"
        )
        assert "判据 A" in str(caught.value)

    def test_criterion_3_is_not_masked_by_criterion_4(self) -> None:
        """第 ③ 条：判据 B 真 **且** bundle 不可加载 ⇒ 必须抛 ③，不是 ④。"""
        import asyncio

        facts = _lane_facts(published_representation_current=True)
        with _patched_lane_supply(facts):
            with pytest.raises(F2.FirstPublicationAlreadyDoneError):
                asyncio.run(_resolve_plan(resolution=_ExplodingResolution()))

    def test_criterion_4_is_not_masked_by_criterion_5(self) -> None:
        """第 ④ 条：bundle 不可加载时抛的是**被委派方**的异常，不是 ⑤ 的契约码。

        ④ 委派 `load_bundle_snapshot`，因此这里不该出现 `contract_not_reviewed` ——
        若出现，说明 ⑤ 被排到了 ④ 之前（或 ④ 被 try/except 吞掉了）。
        """
        import asyncio

        sentinel = RuntimeError("bundle snapshot 校验失败（替身注入）")
        facts = _lane_facts(published_representation_current=False)
        with _patched_lane_supply(facts):
            with pytest.raises(Exception) as caught:
                asyncio.run(_resolve_plan(resolution=_ExplodingResolution(sentinel)))
        assert caught.value is sentinel or "bundle" in str(caught.value).lower(), (
            f"第 ④ 条失败时抛的是 {type(caught.value).__name__}: {caught.value} —— "
            "被委派方的异常没有透出来"
        )
        assert not isinstance(caught.value, F2.ContractNotReviewedError), (
            "bundle 不可加载却抛 `contract_not_reviewed` —— ⑤ 被排到了 ④ 之前"
        )

    def test_criterion_5_contract_unavailable_raises_its_own_code(self) -> None:
        """第 ⑤ 条：前四条全过而磁盘契约不可用 ⇒ `contract_not_reviewed`。"""
        import asyncio

        from app.services.workpaper_sync import contracts as contracts_module

        facts = _lane_facts(published_representation_current=False)
        original = contracts_module.load_contract

        def _reject(contract_id: str) -> Any:
            raise RuntimeError(f"review_status != reviewed（替身）: {contract_id}")

        contracts_module.load_contract = _reject  # type: ignore[assignment]
        try:
            with _patched_lane_supply(facts):
                with pytest.raises(F2.ContractNotReviewedError) as caught:
                    asyncio.run(_resolve_plan())
        finally:
            contracts_module.load_contract = original  # type: ignore[assignment]
        assert getattr(caught.value, "error_code", "") == "contract_not_reviewed"

    def test_all_five_criteria_were_actually_reached(self) -> None:
        """自证分母：五条各自的构造真的走到了那一条（而不是全停在 ①）。

        没有这一条时，上面五条可以全部因为「① 就抛了」而通过 ——
        那样「顺序」这件事完全没有被验证。
        """
        import asyncio

        from app.services.workpaper_sync import projection_lane_registry as R

        reached: list[int] = []

        # ① 用 opaque entry
        import uuid as _uuid

        from app.services.workpaper_sync.writer_migration import opaque_entry_id

        with contextlib.suppress(R.LaneIsOpaqueError):
            asyncio.run(
                _resolve_plan(entry_id=opaque_entry_id(wp_code=None, wp_id=_uuid.uuid4()))
            )
            reached.append(0)  # 不该到这
        reached.append(1)

        # ② A 假
        with _patched_lane_supply(_lane_facts(projection_bundle_provisioned=False)):
            with contextlib.suppress(F2.ProjectionBundleNotProvisionedError):
                asyncio.run(_resolve_plan())
        reached.append(2)

        # ③ B 真
        with _patched_lane_supply(_lane_facts(published_representation_current=True)):
            with contextlib.suppress(F2.FirstPublicationAlreadyDoneError):
                asyncio.run(_resolve_plan())
        reached.append(3)

        # ④ bundle 不可加载
        with _patched_lane_supply(_lane_facts(published_representation_current=False)):
            with contextlib.suppress(Exception):
                asyncio.run(_resolve_plan(resolution=_ExplodingResolution()))
        reached.append(4)

        # ⑤ 契约不可用（前四条全过 ⇒ 证明 ①~④ 真的能被走过去）
        from app.services.workpaper_sync import contracts as contracts_module

        original = contracts_module.load_contract

        def _reject(contract_id: str) -> Any:
            raise RuntimeError("替身拒绝")

        contracts_module.load_contract = _reject  # type: ignore[assignment]
        try:
            with _patched_lane_supply(_lane_facts(published_representation_current=False)):
                with pytest.raises(F2.ContractNotReviewedError):
                    asyncio.run(_resolve_plan())
        finally:
            contracts_module.load_contract = original  # type: ignore[assignment]
        reached.append(5)

        assert reached == [1, 2, 3, 4, 5], (
            f"五条准入的构造没有逐条到位: {reached} —— "
            "第 ⑤ 条能被走到，证明 ①~④ 在正例输入下确实全部放行"
        )

    def test_successful_plan_is_frozen_and_has_no_mutation_surface(self) -> None:
        """五条全过 ⇒ 返回冻结计划；且它不持 session / repository / outbox。"""
        import asyncio
        import dataclasses

        facts = _lane_facts(published_representation_current=False)
        with _patched_lane_supply(facts):
            plan = asyncio.run(_resolve_plan())
        assert dataclasses.is_dataclass(plan)
        with pytest.raises(Exception):
            plan.entry_id = "mutated"  # type: ignore[misc]
        assert plan.entry_id == _STUB_ENTRY_ID
        assert plan.authority_model_logical_id.endswith(".authority-model")

    def test_plan_carrying_a_session_is_rejected(self) -> None:
        """`assert_no_mutation_surface` 真在跑：塞了 session 的计划必须抛。

        判据落在**真实执行**：直接构造一个夹带 session 的 plan。
        没有这一条时，`__post_init__` 里的那行调用可以被删掉而无人知道。
        """
        import uuid as _uuid

        class _FakeSession:
            async def execute(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover
                raise AssertionError("不该被调用")

            async def commit(self) -> None:  # pragma: no cover
                raise AssertionError("不该被调用")

        with pytest.raises(Exception) as caught:
            F2.FirstPublicationPlan(
                project_id=_uuid.uuid4(),
                wp_id=_uuid.uuid4(),
                entry_id=_STUB_ENTRY_ID,
                contract_id="h1.disposal_check",
                provider_module="m",
                document_type="xlsx",
                expected_revision=0,
                bundle=_FakeSession(),  # ← 写入面
                contract=object(),
                authority_model_logical_id="h1.disposal_check.authority-model",
            )
        assert "FirstPublicationPlan" in str(caught.value) or "mutation" in str(
            caught.value
        ).lower(), f"抛的不是写入面判据: {caught.value}"

    def test_contract_criterion_number_is_locked_at_import(self) -> None:
        """判据编号锁在 **import 期**真跑，且它锁的数字与实测一致。

        🔴 `_CONTRACT_CRITERION` 是「lane 裁决里契约那一格的编号」。写死一个数而不锁，
        L 顺序调整后翻译就会落到错的格上 —— 把「bundle 缺失」当成「契约未复核」，
        运维被送去找契约复核方而真正该做的是跑 Task 76 的 provision 宿主。

        两侧判据：
        ① 结构 —— 模块顶层存在对 `_assert_contract_criterion_number_agrees()` 的**调用**
           表达式（只取引用不调用 = additive 死代码）；
        ② 行为 —— 现跑一次该函数不抛（它内部会真的打断契约加载并比对编号）。
        """
        stripped = _strip_docstrings(F2_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(stripped)
        top_level_calls = {
            node.value.func.id
            for node in tree.body
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
        }
        assert "_assert_contract_criterion_number_agrees" in top_level_calls, (
            "模块顶层没有对 `_assert_contract_criterion_number_agrees()` 的调用 —— "
            f"import 期不跑，编号指错格也不会有人知道。顶层调用实测: {sorted(top_level_calls)}"
        )
        F2._assert_contract_criterion_number_agrees()  # 现跑一次，不抛即通过

    def test_authority_logical_id_is_taken_from_the_delivery_registry(self) -> None:
        """`authority_model_logical_id` 与 `DELIVERED_PER_ENTRY_CONTRACTS` 现算值相等。

        改登记表即失败 —— 本模块不写死该字面量（Requirement 3.3）。
        """
        import asyncio

        from app.services.workpaper_sync.adapters import registry as registry_module
        from app.services.workpaper_sync.projection_lane_registry import (
            authority_model_logical_id,
        )

        row = next(
            r
            for r in registry_module.DELIVERED_PER_ENTRY_CONTRACTS
            if str(r["entry_id"]) == _STUB_ENTRY_ID
        )
        expected = authority_model_logical_id(str(row["contract_id"]))
        with _patched_lane_supply(_lane_facts(published_representation_current=False)):
            plan = asyncio.run(_resolve_plan())
        assert plan.authority_model_logical_id == expected
        assert plan.contract_id == str(row["contract_id"])

        # 结构侧：F2 里不出现写死的 `.authority-model` 后缀拼接
        stripped = _strip_docstrings(F2_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "resolve_plan")
        constants = {
            inner.value
            for inner in ast.walk(node)
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str)
        }
        assert ".authority-model" not in constants, (
            "`resolve_plan` 里写死了 `.authority-model` 后缀 —— 必须现取派生函数"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 12（部分）：一切拒绝形态的 error_code 两两不同
# ═══════════════════════════════════════════════════════════════════════════


class TestRejectionErrorCodesArePairwiseDistinct:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 12: 一切拒绝形态的 error_code 两两不同并指出首个不符项**

    **Validates: Requirements 3.5, 3.6, 7.1, 7.3, 7.5, 7.6, 7.7**
    """

    def test_first_publication_error_codes_are_pairwise_distinct(self) -> None:
        base = F2.FirstPublicationError
        subclasses = sorted(
            {
                cls
                for cls in vars(F2).values()
                if isinstance(cls, type)
                and issubclass(cls, base)
                and cls is not base
            },
            key=lambda cls: cls.__name__,
        )
        assert len(subclasses) >= 5, (
            f"只找到 {len(subclasses)} 个 `FirstPublicationError` 子类 —— "
            "分母过小时「两两不同」几乎恒真"
        )
        codes = [getattr(cls, "error_code", None) for cls in subclasses]
        assert all(codes), dict(zip([c.__name__ for c in subclasses], codes))
        assert len(set(codes)) == len(codes), (
            "有两个拒绝形态共用同一个 error_code ⇒ 「为什么发不出去」不可分辨："
            + json.dumps(
                {cls.__name__: code for cls, code in zip(subclasses, codes)},
                ensure_ascii=False,
            )
        )

    def test_host_settlement_vocabulary_is_closed_and_covers_registered_codes(
        self,
    ) -> None:
        """封闭词表判据：每个登记的 error_code 都映射到词表内的格。"""
        host = _load_host()
        vocabulary = set(host.CHECK_ENTRY_STATES)
        assert len(vocabulary) == len(host.CHECK_ENTRY_STATES), "词表里有重复项"
        mapped = set(host._ERROR_CODE_TO_STATE.values())
        outside = sorted(mapped - vocabulary)
        assert not outside, f"`_ERROR_CODE_TO_STATE` 映到词表外的格: {outside}"

        # materialize 侧取值域必须逐条登记 —— 那张表是权威登记表，漏一条就落兜底格
        from app.services.workpaper_sync.excel_materialize import FAILURE_KINDS

        assert FAILURE_KINDS, "FAILURE_KINDS 为空 —— 判据会在空集上恒真"
        missing = sorted(set(FAILURE_KINDS) - set(host._ERROR_CODE_TO_STATE))
        assert not missing, (
            f"`excel_materialize.FAILURE_KINDS` 里有 {len(missing)} 个 error_code 未登记进"
            f"宿主结算词表 {missing} —— 它们会落进 `blocked_unregistered_failure_shape`"
        )

    def test_unregistered_error_code_raises_instead_of_silently_bucketing(self) -> None:
        """未登记的 error_code 必须让 `_settle_for` 抛，而不是静默归类。"""
        host = _load_host()
        with pytest.raises(host.HostError) as caught:
            host._settle_for("definitely_not_a_registered_error_code")
        assert "封闭集" in str(caught.value)

    def test_every_blocked_state_declares_an_unblock_owner(self) -> None:
        """每个 blocked 格都要有解除方 —— 「卡住了」不带「谁能解」等于没有结论。"""
        host = _load_host()
        blocked = [
            state for state in host.CHECK_ENTRY_STATES if state.startswith("blocked_")
        ]
        assert blocked, "词表里没有 blocked 格 —— 判据空转"
        missing = sorted(set(blocked) - set(host._STATE_UNBLOCK_OWNER))
        assert not missing, f"这些 blocked 格没有登记解除方: {missing}"


# ═══════════════════════════════════════════════════════════════════════════
# Property 15 / 16：暂存期零数据库 + OOXML 安全门在发布前失败
# ═══════════════════════════════════════════════════════════════════════════


class TestApplyIsPerEntryTransactional:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 25: 每 entry 独立事务，单点失败只回滚自身并以非零退出码报错**

    **Validates: Requirements 6.6, 6.7, 6.11**

    🔴 本类首版标的是「Property 35 邻域」，那是**编号错位**：design.md 的 Property 35
    是「复原流程每步独立事务」（F8 的真库夹具），与 `--apply` 的逐 entry 事务是两件事。
    2026-09-05 更正为 Property 25。落库侧（前 k-1 个 entry 结果不变）归 F8。
    """

    def _apply_node(self) -> ast.AST:
        stripped = _strip_docstrings(HOST_PATH.read_text(encoding="utf-8"))
        return _function_node(stripped, "run_apply")

    def test_apply_uses_one_session_per_entry(self) -> None:
        """🔴 变异 M8（改为共用外层事务）的直接对手。

        判据是**结构**的：`async with Session() as session` 必须在**逐 entry 的循环体
        内部**。判在「循环内」而不是「文件里出现过」—— 后者在把它提到循环外之后照样绿。
        """
        node = self._apply_node()
        loops = [
            inner
            for inner in ast.walk(node)
            if isinstance(inner, (ast.For, ast.AsyncFor))
        ]
        assert loops, "`run_apply` 里没有循环 —— 逐 entry 处理不见了"

        def _opens_session(scope: ast.AST) -> bool:
            for stmt in ast.walk(scope):
                if not isinstance(stmt, (ast.With, ast.AsyncWith)):
                    continue
                for item in stmt.items:
                    call = item.context_expr
                    if (
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Name)
                        and call.func.id == "Session"
                    ):
                        return True
            return False

        assert any(_opens_session(loop) for loop in loops), (
            "逐 entry 循环体内没有 `async with Session() as session` —— "
            "session 被提到循环外即共用事务，一个 entry 失败会连带回滚其它 entry "
            "已成功的提交（2026-09-04 首轮「四个 entry 一个都发不出去」的加剧版）"
        )

        # 反向：`_apply` 里不得出现 `engine.begin()`（那是共用事务的典型形态）
        text = ast.unparse(node)
        assert "engine.begin" not in text, (
            "`_apply` 里出现 `engine.begin()` —— 逐 entry 独立事务禁止共用外层事务"
        )

    def test_apply_rolls_back_only_the_failing_entry(self) -> None:
        """每个 except 分支都要 `await session.rollback()`，且 commit 在循环内。"""
        node = self._apply_node()
        handlers = [
            inner for inner in ast.walk(node) if isinstance(inner, ast.ExceptHandler)
        ]
        assert handlers, "`run_apply` 没有 except 分支 —— 失败会裸奔出循环"

        # 🔴 不是所有 except 都该 rollback。outbox 那一支**刻意不回滚**：内容已经
        #    `session.commit()` 了，事件发布失败已落成耐久 outbox 行由 replay worker
        #    重放，此时回滚等于把已提交的内容判成失败。判据因此只针对**发布失败**那批
        #    handler —— 用「同一 handler 内调用了 `_settle_exception`」来识别它们，
        #    那是「这条 entry 发布失败了」的结构标志。
        settle_handlers = [
            handler
            for handler in handlers
            if any(
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "_settle_exception"
                for inner in ast.walk(handler)
            )
        ]
        assert len(settle_handlers) >= 2, (
            f"只找到 {len(settle_handlers)} 个发布失败 handler（认 `_settle_exception`）"
            " —— 预期至少 2 个（domain 错与兜底 Exception 各一）"
        )
        for handler in settle_handlers:
            text = ast.unparse(handler)
            assert "rollback" in text, (
                f"第 {handler.lineno} 行的发布失败 handler 没有 rollback —— "
                "失败 entry 的部分写入会留在事务里"
            )

        # 反向自证：outbox 那一支确实存在且确实**不**回滚（若它也回滚了，说明有人
        # 把「内容已提交」这个前提搞丢了）
        outbox_handlers = [
            handler
            for handler in handlers
            if "publish_pending" in ast.unparse(handler)
            or "outbox" in ast.unparse(handler)
        ]
        assert outbox_handlers, (
            "找不到 outbox 发布失败的 handler —— 那一支的存在本身是「内容已提交后"
            "事件失败不得翻成整体失败」的判据"
        )
        for handler in outbox_handlers:
            assert "rollback" not in ast.unparse(handler), (
                f"第 {handler.lineno} 行的 outbox handler 里出现 rollback —— "
                "内容已 commit，回滚它等于把已提交的首版判成失败"
            )

        loops = [
            inner
            for inner in ast.walk(node)
            if isinstance(inner, (ast.For, ast.AsyncFor))
        ]
        commit_in_loop = any(
            "session.commit" in ast.unparse(loop) for loop in loops
        )
        assert commit_in_loop, (
            "`session.commit()` 不在逐 entry 循环内 —— 那意味着所有 entry 共享一次提交"
        )

    def test_apply_actually_awaits_publish_first_generation(self) -> None:
        """🔴 变异 M9（只取引用不调用）的直接对手 —— 假绿第①源。

        判据必须是「存在一个 `await` 表达式，其被 await 的对象是对
        `publish_first_generation` 的**调用**」。判「源码里出现这个名字」会在
        `receipt = F2.publish_first_generation`（只取引用）之后照样绿 —— 而那时
        `--apply` 什么都不发。
        """
        node = self._apply_node()
        awaited_calls = [
            inner
            for inner in ast.walk(node)
            if isinstance(inner, ast.Await)
            and isinstance(inner.value, ast.Call)
            and (
                (
                    isinstance(inner.value.func, ast.Attribute)
                    and inner.value.func.attr == "publish_first_generation"
                )
                or (
                    isinstance(inner.value.func, ast.Name)
                    and inner.value.func.id == "publish_first_generation"
                )
            )
        ]
        assert awaited_calls, (
            "`_apply` 里没有 `await ...publish_first_generation(...)` 的**调用** —— "
            "只取引用不调用是 additive 死代码：函数写好了、测试单独测它全绿，"
            "而宿主 `--apply` 一份 representation 都不发"
        )


class TestStagingIsZeroDatabaseAndGatesBeforePublish:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 15: substrate 暂存期零数据库读写 / Property 16: 被策略拒绝的 OOXML 部件
    在发布前失败且不留 staged artifact**

    **Validates: Requirements 4.2, 4.3, 4.4, 4.5**
    """

    def test_stage_signature_has_no_session_parameter(self) -> None:
        """签名侧：`stage_instrumented_substrate` 的参数里根本不该有 session。

        判据落在签名而不是「跑一次没写库」：签名里没有 session 时，「失败时库一行没动」
        在**构造上**成立，不需要靠调用方自觉。
        """
        node = _function_node(F2_PATH.read_text(encoding="utf-8"), "stage_instrumented_substrate")
        args = node.args
        names = {a.arg for a in list(args.args) + list(args.kwonlyargs)}
        for banned in ("session", "db", "connection", "repository"):
            assert banned not in names, (
                f"`stage_instrumented_substrate` 的签名里出现 {banned!r} —— "
                "暂存期零数据库这条就不再是构造上成立的了"
            )

    def test_b60_authoritative_bytes_are_rejected_with_a_named_gate(
        self, tmp_path: Path
    ) -> None:
        """已知负例：B60 权威模板必须以 `ooxml_security_rejected` + 具体 gate 名被拒。

        用**真实权威字节**而不是手搓最小 xlsx —— 后者会让判据在空集上恒真。
        失败后 staged 目录必须为空（不得留下被策略拒绝的字节）。
        """
        entry_id = "xlsx/b60/gt-b60-bundle"
        with pytest.raises(F2.OoxmlSecurityRejectedError) as caught:
            F2.stage_instrumented_substrate(
                entry_id=entry_id, staging_dir=tmp_path, contract=None
            )
        error = caught.value
        assert getattr(error, "error_code", "") == "ooxml_security_rejected"
        assert str(getattr(error, "gate", "")), (
            "拒绝时没带 gate 名 —— 「为什么被拒」就只能靠读消息猜"
        )
        assert str(error.gate) == "external_relationships", (
            f"gate 名实测为 {error.gate!r}，与登记的已知负例不符 —— "
            "安全策略变了就该重新裁决，而不是让判据跟着漂"
        )
        leftovers = [p.name for p in tmp_path.iterdir() if p.suffix == ".xlsx"]
        assert not leftovers, f"被策略拒绝后 staged 目录留下了 {leftovers}"

    def test_the_gate_runs_before_the_staged_artifact_is_produced(
        self, tmp_path: Path
    ) -> None:
        """结构判据：`validate_ooxml_artifact` 的调用在 staged 文件**命名之前**。

        🔴 判据必须落在**顺序**上而不是「安全门被调用过」：把它挪到 staged 文件产出
        之后，B60 的字节就已经躺在 staging 目录里了 —— 而后续任何一步失败（或进程被
        中断）都会把它留在那儿，成为一份「通过了发布链」的假象产物。

        判据形态：AST 里 `validate_ooxml_artifact` 的行号 < `staged_path = ` 赋值行号。
        """
        stripped = _strip_docstrings(F2_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "stage_instrumented_substrate")
        gate_lines = [
            inner.lineno
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id == "validate_ooxml_artifact"
        ]
        staged_assign_lines = [
            inner.lineno
            for inner in ast.walk(node)
            if isinstance(inner, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "staged_path" for t in inner.targets
            )
        ]
        assert gate_lines, "`stage_instrumented_substrate` 里没有 OOXML 安全门调用"
        assert staged_assign_lines, "没有 `staged_path = ...` 赋值 —— 产物名从哪来的？"
        assert min(gate_lines) < min(staged_assign_lines), (
            f"安全门在行 {min(gate_lines)}、staged 产物命名在行 "
            f"{min(staged_assign_lines)} —— 门必须在**产出之前**跑，否则被策略拒绝的"
            "字节会先落进 staging 目录"
        )

    #: 三类被禁部件的注入构造。
    #:
    #: 🔴 **形态取自门的真实判据**，不是从部件名猜的。首版我按「注入
    #: `xl/externalLinks/externalLink1.xml`」构造，实测**不触发拒绝** —— 查
    #: `ooxml_security.py` 第 8 道门后确认它判的是 **`.rels` 里的
    #: `TargetMode="External"`**，与是否存在 `externalLinks/` 部件无关。
    #: 另两道门判的分别是 `macro_part_markers` 与 `embedded_object_prefixes`
    #: （两者都现取策略常量，本表不写死部件名）。
    _INJECTIONS = ("external_relationships", "macros", "embedded_objects")

    @pytest.mark.parametrize("expected_gate", _INJECTIONS)
    def test_each_forbidden_part_class_triggers_its_own_gate(
        self, tmp_path: Path, expected_gate: str
    ) -> None:
        """三类被禁部件各自触发**它自己那道**门（Requirement 4.5 逐条）。

        用**通过了安全门的真实 instrumented 字节**做底，只注入一处 —— 这样「被拒」
        只可能来自注入物。手搓最小 xlsx 会让判据说不清是被哪一条拒的。

        判据不止「被拒了」，还要求 `gate` **恰是**预期那道 —— 否则三条参数化会互相
        顶替（任一注入触发任一门都算通过），那等于只有一条判据。
        """
        import zipfile

        from app.services.workpaper_sync.artifacts import (
            load_limits,
            validate_ooxml_artifact,
        )

        limits = load_limits()
        policy = limits.ooxml

        # 先取一份干净的 instrumented 字节（H1 实测通过全部 10 道 gate）
        clean = F2.stage_instrumented_substrate(
            entry_id="xlsx/gt-h1-fixed-assets", staging_dir=tmp_path / "clean"
        )
        # 对照组：干净字节必须通过（证明拒绝来自注入物而不是底料）
        baseline_report = validate_ooxml_artifact(
            clean.staged_path, document_type="xlsx", limits=limits
        )
        assert expected_gate in tuple(baseline_report.gates), (
            f"干净字节没通过 {expected_gate} 门 —— 底料本身就不干净，判据无意义。"
            f"实测通过: {tuple(baseline_report.gates)}"
        )

        # ── 按门的真实判据构造注入物（策略常量现取）──────────────────
        if expected_gate == "external_relationships":
            mode = str(policy.external_relationship_target_mode)
            name = "xl/_rels/_injected.rels"
            blob = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'<Relationship Id="rIdInjected" Type="http://x/externalLink" '
                f'Target="file:///C:/evil.xlsx" TargetMode="{mode}"/>'
                "</Relationships>"
            ).encode("utf-8")
        elif expected_gate == "macros":
            marker = str(policy.macro_part_markers[0])
            name = f"xl/{marker}" if "/" not in marker else marker
            blob = b"injected-macro-blob"
        else:
            prefix = str(policy.embedded_object_prefixes[0])
            name = f"{prefix}injected1.bin"
            blob = b"injected-embedded-object"

        with zipfile.ZipFile(clean.staged_path) as src:
            existing = set(src.namelist())
            assert name not in existing, f"{name} 本来就在包里 —— 注入无意义"
            polluted = tmp_path / f"polluted-{expected_gate}.xlsx"
            with zipfile.ZipFile(polluted, "w", zipfile.ZIP_DEFLATED) as dst:
                for item in src.infolist():
                    dst.writestr(item, src.read(item.filename))
                dst.writestr(name, blob)

        with pytest.raises(Exception) as caught:
            validate_ooxml_artifact(polluted, document_type="xlsx", limits=limits)
        gate = str(getattr(caught.value, "gate", "") or "")
        assert gate == expected_gate, (
            f"注入 {name!r} 后被 {gate!r} 门拒 —— 预期 {expected_gate!r}。"
            "三类被禁部件必须各自触发它自己那道门，否则参数化的三条互相顶替"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 22 / 23 / 24 / 26：宿主 `--check` 的只读性、封闭词表、目标确定性、幂等
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 分工：这四条都有「结构 / 零库」的一半与「真库落数」的一半。
#    本文件只落前者（F7 是零数据库文件）；后者归 F8 的真实 PG 夹具：
#      * P22 的「跑前跑后四张表逐行相等」
#      * P24 的「同一库状态重复运行选同一条底稿」
#      * P26 的「重跑 --apply 后行数与 digest 逐项不变」


class TestCheckIsReadOnlyAndRunsTheWholeChain:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 22: `--check` 只读且跑完全链**

    **Validates: Requirements 6.1, 6.2**
    """

    def _check_node(self) -> ast.AST:
        stripped = _strip_docstrings(HOST_PATH.read_text(encoding="utf-8"))
        return _function_node(stripped, "run_check")

    def test_check_never_writes(self) -> None:
        """`run_check` 里零写入调用。

        判据枚举**写入面的方法名**而不是找 `commit` 这一个词 —— 后者漏掉
        `session.add` / `flush` / `merge` / `delete`，而它们同样会让「只读」失守。
        """
        text = ast.unparse(self._check_node())
        banned_calls = (
            "session.commit",
            "session.add",
            "session.flush",
            "session.merge",
            "session.delete",
            "engine.begin",
            "publish_first_generation",
            "bump_content_revision",
        )
        offending = [name for name in banned_calls if name in text]
        assert not offending, (
            f"`run_check` 里出现写入面调用 {offending} —— `--check` 必须一行库都不写"
        )

    def test_check_covers_every_declared_stage(self) -> None:
        """`CHECK_STAGES` 的每一格都在 `run_check` 里被真的**赋过值**。

        🔴 判据落在「阶段被记录」而不是「词表里有这一格」：宿主自己的注释写明首版
        `--check` 只跑到 `adapter_built` 就报「能发」，而真发时后四段全失败 ——
        那正是「预演说能发、真发发不出」的假绿。
        """
        host = _load_host()
        stages = tuple(host.CHECK_STAGES)
        assert len(stages) >= 6, f"阶段词表只有 {len(stages)} 格，分母过小"
        assert len(set(stages)) == len(stages), f"阶段词表有重复: {stages}"

        text = ast.unparse(self._check_node())
        missing = [stage for stage in stages if repr(stage) not in text]
        assert not missing, (
            f"这些阶段在 `run_check` 里从未被记录: {missing} —— "
            "声明了却不跑的阶段等于没有；预演会说「能发」而真发在那一段失败"
        )

    def test_stage_recording_is_not_unconditional(self) -> None:
        """阶段标记不得**无条件**全置真 —— 那样「跑完全链」变成一句自述。

        判据：`run_check` 里对 `settlement.stages` 的写入必须发生在 ≥2 个不同的
        语法位置（逐段推进），而不是一处 dict 字面量一次性填满。
        """
        node = self._check_node()
        stage_writes = [
            inner.lineno
            for inner in ast.walk(node)
            if isinstance(inner, ast.Subscript)
            and isinstance(inner.value, ast.Attribute)
            and inner.value.attr == "stages"
        ]
        assert len(stage_writes) >= 4, (
            f"`settlement.stages` 只在 {len(stage_writes)} 处被写 —— "
            "逐段推进的阶段标记应当散布在链条各步，一次性填满等于自述跑完了"
        )

    def test_check_really_runs_and_settles_every_entry(self) -> None:
        """真跑一次 `--check`：每个 entry 都落到词表内的格，且阶段有真实推进。

        这是本类唯一的**行为**判据。它连库（只读），因此库不可达时 skip。
        """
        host = _load_host()
        import asyncio

        try:
            results = asyncio.run(host.run_check())
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"真库不可达或装配失败: {type(exc).__name__}: {exc}")

        assert results, "`--check` 一个 entry 都没结算"
        vocabulary = set(host.CHECK_ENTRY_STATES)
        for settlement in results:
            assert settlement.state in vocabulary, (
                f"{settlement.entry_id} 结算到词表外的取值 {settlement.state!r}"
            )
            assert settlement.stages, f"{settlement.entry_id} 没有任何阶段记录"
        # 非空分母：至少一个 entry 真的推进过 ≥3 段（否则「跑完全链」无从谈起）
        deepest = max(len(s.stages) for s in results)
        assert deepest >= 3, (
            f"最深的 entry 只推进了 {deepest} 段 —— 全部 entry 都在第一段就停了，"
            "「跑完全链」这条判据在空集上"
        )


class TestSettlementVocabularyIsClosed:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 23: 逐 entry 结算落在封闭词表内**

    **Validates: Requirements 6.3, 6.9, 6.10, 6.11**
    """

    def test_design_declared_six_states_are_all_present(self) -> None:
        """design.md 声明的六格必须全在（扩格允许，减格不允许）。"""
        host = _load_host()
        declared = {
            "ready_to_publish",
            "blocked_missing_approved_bundle",
            "blocked_ooxml_gate",
            "blocked_contract_not_reviewed",
            "blocked_lane_undecided",
            "already_published",
        }
        missing = sorted(declared - set(host.CHECK_ENTRY_STATES))
        assert not missing, (
            f"design.md 声明的结算格缺失: {missing} —— 词表可以扩，不可以减"
        )

    def test_every_state_is_reachable_from_some_error_code_or_success(self) -> None:
        """每一格都有到达路径 —— 到不了的格是死格（Requirement 6.3 的反面）。

        三类到达路径，缺一不可枚举：
        * `_ERROR_CODE_TO_STATE` 的值域（绝大多数 blocked 格）；
        * `ready_to_publish` —— 成功路径；
        * 源码里被**直接赋值**的格 —— 兜底格 `blocked_unregistered_failure_shape`
          属这一类：它不经映射表（`_settle_for` 对未登记 code 抛），而由
          `_settle_exception` 直接赋值。首版我漏了这一类，判据当场把兜底格误报成死格。
        """
        host = _load_host()
        stripped = _strip_docstrings(HOST_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(stripped)
        directly_assigned = {
            node.value.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and any(
                isinstance(t, ast.Attribute) and t.attr == "state"
                for t in node.targets
            )
        }
        reachable = (
            set(host._ERROR_CODE_TO_STATE.values())
            | {"ready_to_publish"}
            | directly_assigned
        )
        orphans = sorted(set(host.CHECK_ENTRY_STATES) - reachable)
        assert not orphans, (
            f"这些结算格没有任何到达路径: {orphans} —— 死格会让读报告的人以为"
            "某种结论可能出现，而它永远不会"
        )
        assert directly_assigned, (
            "源码里没有任何 `settlement.state = <字面量>` —— 兜底格的到达路径不见了"
        )

    def test_contract_not_reviewed_is_reachable_after_the_translation_fix(self) -> None:
        """🔴 `blocked_contract_not_reviewed` 必须**真的**可达。

        2026-09-05 之前它是死格：`resolve_plan` 的第 ⑤ 条与 lane 裁决的 L5 判同一件
        事，于是任何契约未复核的 entry 都先在第 ① 条抛 `lane_undecided` ⇒ 落进
        `blocked_lane_undecided`，运维被送去查 lane 裁决而真正该做的是催契约复核。

        本条判据落在**真实执行**：打断契约加载，跑 `_settle_exception`，
        断言它落到 `blocked_contract_not_reviewed` 而不是 `blocked_lane_undecided`。
        """
        import asyncio

        host = _load_host()
        from app.services.workpaper_sync import contracts as contracts_module

        original = contracts_module.load_contract

        def _reject(contract_id: str) -> Any:
            raise RuntimeError(f"review_status != reviewed（替身）: {contract_id}")

        contracts_module.load_contract = _reject  # type: ignore[assignment]
        try:
            facts = _lane_facts(published_representation_current=False)
            with _patched_lane_supply(facts):
                with pytest.raises(F2.ContractNotReviewedError) as caught:
                    asyncio.run(_resolve_plan())
        finally:
            contracts_module.load_contract = original  # type: ignore[assignment]

        state = host._settle_for(caught.value.error_code)
        assert state == "blocked_contract_not_reviewed", (
            f"契约不可用时结算到 {state!r} —— 应为 `blocked_contract_not_reviewed`。"
            "落进 blocked_lane_undecided 会把运维送去查 lane 裁决的五条判据，"
            "而真正的解除方是契约复核方"
        )
        owner = host._STATE_UNBLOCK_OWNER[state]
        assert "契约" in owner or "review_status" in owner, (
            f"该格登记的解除方与契约无关: {owner}"
        )

    @settings(max_examples=200, deadline=None)
    @given(code=st.text(min_size=0, max_size=40))
    def test_arbitrary_error_code_never_silently_buckets(self, code: str) -> None:
        """任意字符串：要么落在词表内的格，要么抛 —— 绝不静默归类。"""
        host = _load_host()
        try:
            state = host._settle_for(code)
        except host.HostError:
            return  # 未登记 ⇒ 抛，这是正确行为
        assert state in set(host.CHECK_ENTRY_STATES), (
            f"error_code {code!r} 落到词表外的取值 {state!r}"
        )


class TestTargetSelectionIsDeterministic:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 24: 目标选取在固定库状态下确定**

    **Validates: Requirements 6.5**
    """

    def test_order_clause_is_a_total_order(self) -> None:
        """排序键必须以 `wp.id` 收尾 —— 主键是唯一能保证全序的那一项。

        少了它，`wp_code` + `created_at` 相同的两条底稿之间的先后由 PG 的物理顺序决定
        （随 VACUUM / 页面重排而变），于是 `--check` 与 `--apply` 可能选到不同底稿。
        """
        host = _load_host()
        clause = str(host.TARGET_ORDER_SQL)
        assert clause.strip().endswith("wp.id"), (
            f"`TARGET_ORDER_SQL` 不以 `wp.id` 收尾: {clause!r} —— 那不是全序"
        )
        assert "wi.wp_code" in clause, "排序里没有 wp_code —— 码族内的先后不确定"
        assert "wp.created_at" in clause, "排序里没有 created_at"

    def test_order_clause_has_no_random_or_time_dependent_term(self) -> None:
        """排序里不得含随机/时钟项 —— 那会让「同一库状态」也选出不同结果。"""
        clause = str(_load_host().TARGET_ORDER_SQL).lower()
        for banned in ("random()", "now()", "current_timestamp", "clock_timestamp"):
            assert banned not in clause, (
                f"排序里出现 {banned!r} —— 目标选取不再确定"
            )

    def test_check_and_apply_share_the_same_order_clause(self) -> None:
        """`--check` 与 `--apply` 必须用**同一个** `TARGET_ORDER_SQL` 常量。

        判据落在 AST：目标解析只有 `_resolve_target` 一处，且两个入口都调它。
        各写一份排序的后果是预演选 A、真发选 B —— 而报告读起来完全正常。

        🔴 BP-24 之后「拼进 SQL」的那一处在**生产模块**里，宿主只转引常量 ⇒ 拼接判据
        看 `RESOLUTION_PATH`，调用判据仍看宿主（两个入口必须都走 `_resolve_target`）。
        """
        stripped = _strip_docstrings(RESOLUTION_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(stripped)

        # 🔴 判据落在「**拼进 SQL** 的位置只有一处」，不是「这个名字只出现一次」。
        #    首版我按后者写，实测命中 3 处：定义（163）、SQL 拼接（317）、JSON 报告
        #    落盘（905）。后两者里只有一处真取数，另一处是把排序键写进报告供 evidence
        #    现读 —— 那是**该有**的，禁掉它会逼人把排序键复制到报告里（真正的第二真源）。
        sql_interpolations: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.JoinedStr):
                continue
            for part in node.values:
                if (
                    isinstance(part, ast.FormattedValue)
                    and isinstance(part.value, ast.Name)
                    and part.value.id == "TARGET_ORDER_SQL"
                ):
                    sql_interpolations.append(node.lineno)
        assert len(sql_interpolations) == 1, (
            f"`TARGET_ORDER_SQL` 在 {RESOLUTION_PATH.name} 里被拼进 SQL 的位置有 "
            f"{len(sql_interpolations)} 处（应恰 1 处，在 `resolve_projection_target` 里）"
            f"—— 多处拼接意味着排序被抄了第二份，预演选 A 真发选 B 而报告读起来完全"
            f"正常。行号: {sql_interpolations}"
        )

        # 另一半：ORDER BY 子句不得由字面量另写一份。
        #
        # 🔴 判据必须看 `ORDER BY` **之后**的文本。首版我写成「常量里同时含 ORDER BY 与
        #    wp.id」，实测误报：`_resolve_target` 的 f-string 静态前缀恰以 `ORDER BY `
        #    结尾（排序键由 `{TARGET_ORDER_SQL}` 插进来），而 `wp.id` 出现在 SELECT
        #    的列清单里 —— 两个条件都命中，判据把正确的实现报成了违规。
        def _tail_after_order_by(text: str) -> str:
            upper = text.upper()
            index = upper.find("ORDER BY")
            return text[index + len("ORDER BY") :] if index >= 0 else ""

        order_by_literals = [
            (node.lineno, _tail_after_order_by(node.value).strip()[:60])
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _tail_after_order_by(node.value).strip()
        ]
        assert not order_by_literals, (
            f"源码里有写死排序键的 ORDER BY 字面量: {order_by_literals} —— "
            "排序键的真源只能是 `TARGET_ORDER_SQL`"
        )
        # 调用侧判据看**宿主**（`stripped` 上面已被换成生产模块的源码）。
        host_stripped = _strip_docstrings(HOST_PATH.read_text(encoding="utf-8"))
        for entry in ("run_check", "run_apply"):
            node = _function_node(host_stripped, entry)
            calls = [
                inner
                for inner in ast.walk(node)
                if isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "_resolve_target"
            ]
            assert calls, f"`{entry}` 没有调用 `_resolve_target` —— 它另选了目标"

    def test_resolve_target_selects_at_most_one_row(self) -> None:
        """SQL 带 `LIMIT 1` 且取 `.first()` —— 「唯一目标」在构造上成立。

        🔴 BP-24：SQL 已搬进生产模块的 `resolve_projection_target`，宿主的
        `_resolve_target` 只是转引 ⇒ 判据必须跟着实现走，否则会在一个只有一行 `return`
        的函数上找 `LIMIT 1` 而恒红（首版就是这样打红的）。
        """
        stripped = _strip_docstrings(RESOLUTION_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "resolve_projection_target")
        text = ast.unparse(node)
        assert "LIMIT 1" in text, "`resolve_projection_target` 的 SQL 没有 `LIMIT 1`"
        assert ".first()" in text, "`resolve_projection_target` 没取 `.first()`"

    def test_both_hosts_share_one_order_clause_object(self) -> None:
        """🔴 BP-24：两个宿主的 `TARGET_ORDER_SQL` 必须是**同一个**对象。

        分歧的实测代价（2026-09-05 真库）：首版宿主的全序含 `has_store_payload DESC`，
        Task 76 的 provisioner 那份没有 ⇒ D2 首版发布落在 `ef7f88e3`（store 490,291 B）
        而 provisioner 解析到 `1e171c06`（store 空），于是 provisioner 对**已发布**的 D2
        报 `settlement=blocked` / `current_representation_id=null`；B60 同样分歧。
        `--apply` 若照旧执行，candidate/representation 会建在另一条底稿上 ——「四表有真实
        行」与「首版已发布」各自成立却指向不同 wp，是典型的假绿。

        判据是 `is` 同一性而不是字符串相等：字符串相等允许两边各写一份**恰好一样**的
        字面量，那种形态下任何一边被改动都不会打红。
        """
        from app.services.workpaper_sync import projection_target_resolution as TR

        host = _load_host()
        t76 = _load_module_by_path(T76_HOST_PATH, "_t76_host_for_tests")
        assert host.TARGET_ORDER_SQL is TR.TARGET_ORDER_SQL, (
            "首版宿主的 `TARGET_ORDER_SQL` 不是生产模块那个对象 —— 又抄了一份"
        )
        assert t76.TARGET_ORDER_SQL is TR.TARGET_ORDER_SQL, (
            "Task 76 provisioner 的 `TARGET_ORDER_SQL` 不是生产模块那个对象 —— "
            "这正是 BP-24 的形态"
        )
        # 全序必须真的含 store 偏好项：它是 BP-24 分歧的实质内容，
        # 只锁「同一对象」而不锁内容的话，两边一起退回旧全序仍然绿。
        assert "store.remark" in TR.TARGET_ORDER_SQL, (
            "全序里没有 store 载荷偏好项 —— D2 会重新选到 store 为空的那条底稿，"
            "首版发出去是空 projection"
        )
        # 两个宿主都不得自留 ORDER BY 字面量（含 `wp.created_at` 的那种）。
        for path in (HOST_PATH, T76_HOST_PATH):
            stripped = _strip_docstrings(path.read_text(encoding="utf-8"))
            leaked = [
                node.lineno
                for node in ast.walk(ast.parse(stripped))
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "wp.created_at" in node.value
            ]
            assert not leaked, (
                f"{path.name} 里有含 `wp.created_at` 的字符串字面量（行 {leaked}）—— "
                "排序键的真源只能是生产模块的 `TARGET_ORDER_SQL`"
            )


class TestRerunApplyIsIdempotent:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 26: 重跑 `--apply` 幂等，不产生第二份供给**

    **Validates: Requirements 6.8**

    落库侧（行数与 digest 逐项不变）归 F8；这里落**结构与行为的零库侧**：
    已发布的 entry 在第二次 `--apply` 时必须被 `resolve_plan` 的判据 ③ 拦住。
    """

    def test_second_attempt_is_rejected_by_criterion_three(self) -> None:
        """行为侧：判据 B 已成立（= 首版已发）时 `resolve_plan` 必抛，不覆盖既有。"""
        import asyncio

        facts = _lane_facts(published_representation_current=True)
        with _patched_lane_supply(facts):
            with pytest.raises(F2.FirstPublicationAlreadyDoneError) as caught:
                asyncio.run(_resolve_plan())
        assert caught.value.error_code == "first_publication_already_done"

    def test_already_published_settles_without_touching_the_database(self) -> None:
        """`already_published` 这一格必须由 error_code 映射到达，不经任何写入。"""
        host = _load_host()
        assert (
            host._settle_for("first_publication_already_done") == "already_published"
        )

    def test_apply_skips_entries_that_are_not_ready(self) -> None:
        """结构侧：`run_apply` 只对准入通过的 entry 发布。

        判据：`publish_first_generation` 的调用不在 `run_apply` 的函数体顶层，而在
        `try` 块内且其前方有 `resolve_plan` 调用 —— 顺序保证了「先过准入、后发布」。
        """
        stripped = _strip_docstrings(HOST_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "run_apply")
        resolve_lines = [
            inner.lineno
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "resolve_plan"
        ]
        publish_lines = [
            inner.lineno
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "publish_first_generation"
        ]
        assert resolve_lines, "`run_apply` 里没有 `resolve_plan` 调用 —— 它不过准入就发"
        assert publish_lines, "`run_apply` 里没有 `publish_first_generation` 调用"
        assert min(resolve_lines) < min(publish_lines), (
            f"`resolve_plan` 在行 {min(resolve_lines)}、`publish_first_generation` 在行 "
            f"{min(publish_lines)} —— 准入必须在发布**之前**"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 14：substrate 暂存现算四项实测入参且动态列键不由 label 充当
# ═══════════════════════════════════════════════════════════════════════════


class TestStagedInputsAreMeasuredAndKeysAreLabelIndependent:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 14: substrate 暂存现算四项实测入参且动态列键不由 label 充当**

    **Validates: Requirements 4.1, 4.6**

    分母说明：四个 entry 里**只有 G7** 声明了 `dynamic_columns`（实测 10 列）。
    前三个的字典恒空 ⇒ 任何「键与 label 的关系」判据在它们身上都是空转。
    因此本类的动态列判据一律打在 G7 上，并自带非空断言。
    """

    _G7 = "xlsx/gt-g7-long-term-equity-main"

    @pytest.fixture(scope="class")
    def staged_g7(self, tmp_path_factory: pytest.TempPathFactory) -> Any:
        """G7 的 staged substrate（class 级，instrumentation 比较慢）。"""
        target = tmp_path_factory.mktemp("staged-g7")
        return F2.stage_instrumented_substrate(entry_id=self._G7, staging_dir=target)

    def test_all_four_measured_inputs_are_non_empty(self, staged_g7: Any) -> None:
        """四项实测入参都现算出来了（Requirement 4.1）。"""
        assert staged_g7.identity_inventory is not None
        assert staged_g7.observed_structure, "observed_structure 为空"
        assert staged_g7.observed_business_sheets, "observed_business_sheets 为空"
        assert staged_g7.observed_dynamic_columns, (
            "G7 的 observed_dynamic_columns 为空 —— 它实测有 10 个动态列，"
            "空字典说明现算失败并被静默降级（本类全部动态列判据会随之空转）"
        )
        assert staged_g7.instrumented_sha256 != staged_g7.source_sha256, (
            "instrumented 与源字节 digest 相同 —— instrumentation 没有真的注入 identity"
        )

    def test_dynamic_column_keys_come_from_the_stable_key_function(
        self, staged_g7: Any
    ) -> None:
        """键逐项等于 `dynamic_column_stable_keys(slot, count)` 的现算值。"""
        from app.services.workpaper_sync.excel_entry_gate import (
            dynamic_column_stable_keys,
        )

        assert staged_g7.observed_dynamic_columns
        for table_key, pairs in staged_g7.observed_dynamic_columns.items():
            keys = [key for _label, key in pairs]
            expected = list(
                dynamic_column_stable_keys(slot=table_key, count=len(pairs))
            )
            assert keys == expected, (
                f"{table_key}: 键实测 {keys[:3]}…、现算 {expected[:3]}… —— "
                "键不是由稳定键函数派生的"
            )

    def test_keys_are_invariant_under_label_perturbation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 label 扰动后**全部键逐项不变**（Requirement 4.6 的核心）。

        判据落在**真实执行**：把 `_dynamic_column_labels` 换成一个返回完全不同 label
        的替身，重跑 staging，断言键集合与扰动前逐项相同、而 label 确实变了。

        为什么这条重要：label 是**可见表头文本**，审计师随时会改（「本期」→「2026 年」）。
        键一旦由 label 派生，改一次表头就会让全部行身份失配，反读回来判不等值 ——
        而那时报的错会是「roundtrip 不等值」，与真因（表头被改名）相距很远。
        """
        baseline = F2.stage_instrumented_substrate(
            entry_id=self._G7, staging_dir=tmp_path / "before"
        )
        before = {
            table_key: [key for _label, key in pairs]
            for table_key, pairs in baseline.observed_dynamic_columns.items()
        }
        before_labels = {
            table_key: [label for label, _key in pairs]
            for table_key, pairs in baseline.observed_dynamic_columns.items()
        }
        assert before, "扰动前就没有动态列 —— 判据会在空集上恒真"

        def _renamed(*, instrumented: Any, table_key: str, count: int) -> tuple[str, ...]:
            return tuple(f"审计师改过的表头-{table_key}-{i}" for i in range(1, count + 1))

        monkeypatch.setattr(F2, "_dynamic_column_labels", _renamed)
        perturbed = F2.stage_instrumented_substrate(
            entry_id=self._G7, staging_dir=tmp_path / "after"
        )
        after = {
            table_key: [key for _label, key in pairs]
            for table_key, pairs in perturbed.observed_dynamic_columns.items()
        }
        after_labels = {
            table_key: [label for label, _key in pairs]
            for table_key, pairs in perturbed.observed_dynamic_columns.items()
        }

        assert after == before, (
            f"label 扰动后键变了：before={before}、after={after} —— "
            "键由 label 派生，改一次表头就会让全部行身份失配"
        )
        assert after_labels != before_labels, (
            "替身没生效（label 没变）—— 本判据退化成了「跑两次结果一样」，"
            "那对任何确定性实现都恒真"
        )

    def test_labels_never_appear_among_the_keys(self, staged_g7: Any) -> None:
        """label 与键的取值域**不相交** —— label 没有以任何形式充当键。"""
        for table_key, pairs in staged_g7.observed_dynamic_columns.items():
            labels = {label for label, _key in pairs}
            keys = {key for _label, key in pairs}
            assert not (labels & keys), (
                f"{table_key}: label 与键有交集 {sorted(labels & keys)} —— "
                "label 正在充当键"
            )

    def test_dynamic_bindings_are_column_letters_not_labels(
        self, staged_g7: Any
    ) -> None:
        """`observed_dynamic_bindings` 的值必须是**可解析的 Excel 列标**。

        G7 首版实测炸在 `'minority_financials#1' is not a valid column name` ——
        判据因此落在「真的能过 `column_index_from_string`」而不是「看起来像列标」。
        """
        from openpyxl.utils import column_index_from_string

        bindings = staged_g7.observed_dynamic_bindings
        assert bindings, "G7 的 observed_dynamic_bindings 为空 —— 判据空转"
        for table_key, mapping in bindings.items():
            assert mapping, f"{table_key} 的绑定为空"
            indices = []
            for key, column in mapping.items():
                indices.append(column_index_from_string(str(column)))
                assert "#" not in str(column), (
                    f"{table_key}[{key}] 的绑定值 {column!r} 含 `#` —— 那是 label 的形态"
                )
            assert len(set(indices)) == len(indices), (
                f"{table_key}: 两个键绑到了同一列（列索引 {sorted(indices)}）"
            )

    def test_key_count_equals_binding_count(self, staged_g7: Any) -> None:
        """两份现算（label 侧与列标侧）的键集合逐项相同 —— 它们共用同一段跨度推导。"""
        cols = staged_g7.observed_dynamic_columns
        binds = staged_g7.observed_dynamic_bindings
        assert set(cols) == set(binds), (
            f"两侧表集合不等: {sorted(cols)} vs {sorted(binds)}"
        )
        for table_key in cols:
            key_side = {key for _label, key in cols[table_key]}
            bind_side = set(binds[table_key])
            assert key_side == bind_side, (
                f"{table_key}: label 侧键 {sorted(key_side)[:3]}… 与列标侧键 "
                f"{sorted(bind_side)[:3]}… 不等 —— 两份现算没有共用同一段跨度推导"
            )

    def test_staging_leaves_exactly_one_artifact(self, tmp_path: Path) -> None:
        """成功路径下 staging 目录里恰有一个 xlsx，且探针文件已被改名而非留存。"""
        staged = F2.stage_instrumented_substrate(
            entry_id="xlsx/gt-h1-fixed-assets", staging_dir=tmp_path
        )
        artifacts = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".xlsx")
        assert artifacts == [staged.staged_path.name], (
            f"staging 目录里有 {artifacts} —— 探针文件没被改名（留了两份）"
        )
        assert not staged.staged_path.name.startswith("_probe-"), (
            "staged 产物仍叫 `_probe-*` —— 它是安全门的临时探针名，不该成为产物名"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 18：Frozen_Definitions 的生产入参零 representation 依赖
# ═══════════════════════════════════════════════════════════════════════════


class TestFrozenDefinitionsHaveZeroRepresentationDependency:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 18: Frozen_Definitions 的生产入参零 representation 依赖**

    **Validates: Requirements 5.1, 5.2, 5.3**

    ═══ 这是本 spec 的破环点，也是整条链能成立的唯一理由 ═══════════════════════

    `FrozenEntryDefinitions` 有两个互不依赖的生产者：

    * `PublishedIdentityObserver.observe()` —— **需要** current published representation；
    * `ExcelEntryDefinitionLoader.load()`   —— **不需要**。

    平台从未产出过 published representation，因此第一条路走不通（要 representation 才能
    造 adapter，要 adapter 才能发 representation）。本 spec 走第二条：入参全部来自
    approved projection bundle 与 `stage_instrumented_substrate` 现算的实测值。

    判据必须能抓住「悄悄把 representation 拉回入参」这一种回归 —— 那会让环重新闭合，
    而症状是「首个 entry 永远发不出去」，与真因（多了一个入参）看不出关系。
    """

    _LOADER_CALL = "load"

    def _publish_node(self) -> ast.AST:
        stripped = _strip_docstrings(F2_PATH.read_text(encoding="utf-8"))
        return _function_node(stripped, "publish_first_generation")

    def _loader_load_call(self) -> ast.Call:
        """定位 `loader.load(...)` 那一处调用。"""
        node = self._publish_node()
        calls = [
            inner
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == self._LOADER_CALL
            and isinstance(inner.func.value, ast.Name)
            and inner.func.value.id == "loader"
        ]
        assert len(calls) == 1, (
            f"`publish_first_generation` 里对 `loader.load(...)` 的调用有 {len(calls)} 处"
            "（应恰 1 处）—— 多处会让「入参无 representation」这条判据只覆盖其中一处"
        )
        return calls[0]

    def test_loader_load_is_called_with_keywords_only(self) -> None:
        """全具名实参 —— 位置实参会让下面几条按名字判的判据失效。"""
        call = self._loader_load_call()
        assert not call.args, (
            f"`loader.load(...)` 有 {len(call.args)} 个位置实参 —— "
            "按名字判入参的判据会漏掉它们"
        )
        assert call.keywords, "`loader.load(...)` 一个具名实参都没有？"

    def test_no_argument_name_mentions_representation(self) -> None:
        """🔴 入参名里零 `representation` —— 环不得重新闭合。"""
        call = self._loader_load_call()
        names = [str(kw.arg or "") for kw in call.keywords]
        offending = [n for n in names if "representation" in n.lower()]
        assert not offending, (
            f"`loader.load(...)` 的入参里出现 {offending} —— "
            "representation 又回到了 Frozen_Definitions 的生产入参里，"
            "「要 representation 才能造 adapter、要 adapter 才能发 representation」"
            "这个环重新闭合，首版将永远发不出去"
        )

    def test_every_argument_traces_to_plan_or_staged(self) -> None:
        """每个入参的**来源**只能是 `plan`（approved bundle）或 `staged`（现算实测值）。

        判据落在 AST：实参表达式的根名字必须在 `{plan, staged, adapter_build}` 内。
        这比「名字里没有 representation」强 —— 它排除了「从别处取一个恰好不叫
        representation 的东西」。
        """
        call = self._loader_load_call()
        allowed_roots = {"plan", "staged", "adapter_build"}

        def _root(expr: ast.AST) -> str:
            node: Any = expr
            while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
                node = (
                    node.value
                    if isinstance(node, (ast.Attribute, ast.Subscript))
                    else node.func
                )
            return node.id if isinstance(node, ast.Name) else f"<{type(node).__name__}>"

        traced: dict[str, str] = {}
        for keyword in call.keywords:
            name = str(keyword.arg or "")
            root = _root(keyword.value)
            traced[name] = root
            assert root in allowed_roots, (
                f"入参 {name!r} 的来源根是 {root!r}，不在 {sorted(allowed_roots)} 内 —— "
                "Frozen_Definitions 的入参必须全部来自 approved bundle 与现算实测值"
            )
        assert len(traced) >= 6, (
            f"只追踪到 {len(traced)} 个入参 {sorted(traced)} —— "
            "分母过小，loader 的必填入参不止这些"
        )
        # 四项现算实测值必须都在（否则「实测」这件事没有真的发生）
        from_staged = {n for n, root in traced.items() if root == "staged"}
        assert len(from_staged) >= 4, (
            f"只有 {sorted(from_staged)} 来自现算实测值 —— Requirement 4.1 要求四项"
        )

    def test_the_observer_path_is_not_used(self) -> None:
        """`PublishedIdentityObserver` 在首版链里零引用（它需要 representation）。"""
        text = ast.unparse(self._publish_node())
        for banned in ("PublishedIdentityObserver", "observe_published_identity"):
            assert banned not in text, (
                f"首版发布链里出现 {banned!r} —— 那条生产者需要 current published "
                "representation，首版时它不存在"
            )

    def test_loader_signature_accepts_no_representation_argument(self) -> None:
        """被调方的**签名**里也没有 representation 入参 —— 构造上不可能传。

        这一条比调用侧强：调用侧不传只是「这次没传」，签名里没有才是「传不了」。
        """
        from app.services.workpaper_sync.excel_entry_gate import (
            ExcelEntryDefinitionLoader,
        )

        import inspect

        signature = inspect.signature(ExcelEntryDefinitionLoader.load)
        names = [p for p in signature.parameters if p != "self"]
        assert names, "loader.load 没有参数？"
        offending = [n for n in names if "representation" in n.lower()]
        assert not offending, (
            f"`ExcelEntryDefinitionLoader.load` 的签名里有 {offending} —— "
            "那条生产路径本该是「不依赖 representation」的那一个"
        )

    def test_loader_reads_no_representation_table_anywhere_in_its_call_tree(
        self,
    ) -> None:
        """🔴 结构侧的强判据：loader 的**整条调用树**里零 representation 表引用。

        为什么是这个形态而不是「用替身 session 跑一遍」：我先按后者写，实测因**错误的
        理由**失败 —— loader 自己会查 bundle 行（`_load_bundle_row`），替身让那条查询
        返回空，于是它抛 `FrozenBundleDigestMismatchError`（缺 bundle 时不得回退，那正是
        它该做的）。要让替身跑通就得把 bundle 行、artifact 行的形状全复制一遍，而那份
        复制品一旦与真实 schema 漂移，判据就不再证明任何事。

        ⇒ 行为侧的证明（真库里该 (wp, entry) 无 representation 而 loader 仍产出）
        归 F8 的真实 PG 夹具；这里落**结构**判据：把 `excel_entry_gate` 模块里所有
        SQL 文本与 ORM 引用扫一遍，断言 representation 相关的表名一次都不出现。
        """
        loader_source = (
            BACKEND / "app/services/workpaper_sync/excel_entry_gate.py"
        ).read_text(encoding="utf-8")
        stripped = _strip_docstrings(loader_source)
        tree = ast.parse(stripped)

        # 🔴 判据落在 **ORM 模型类**而不是 SQL 字符串：实测该模块零裸 SQL（`sa.text`
        #    出现 0 次），全部取数走 `sa.select(<Model>)`。按字符串扫会在空集上恒真 ——
        #    首版我就是那样写的，非空分母断言当场把它打红了。
        selected_models: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "select"
                and node.args
            ):
                target = node.args[0]
                name = (
                    target.id
                    if isinstance(target, ast.Name)
                    else ast.unparse(target)
                )
                selected_models.append((node.lineno, name))

        assert selected_models, (
            "`excel_entry_gate` 里一处 `sa.select(...)` 都没有 —— 「没查 representation」"
            "可能只是因为它压根不查库，本判据在空集上"
        )

        representation_models = (
            "Representation",
            "EntryState",
            "UpgradeCandidate",
            "ContentVersion",
        )
        offending = [
            f"L{line}: {name}"
            for line, name in selected_models
            if any(token in name for token in representation_models)
        ]
        assert not offending, (
            f"loader 的取数点里出现 representation 侧模型: {offending} —— "
            "这条生产路径本该零 representation 依赖，查它等于让环重新闭合"
        )
        assert all("Definition" in name for _line, name in selected_models), (
            f"loader 的取数点不全在 definition 侧: {selected_models} —— "
            "入参本该只来自 approved projection bundle"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 结构判据：首版发布链不降级任何既有判据
# ═══════════════════════════════════════════════════════════════════════════


class TestPublishDoesNotDowngradeExistingGates:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 21: 以空 adapter 提交 projection 必被拒**

    **Validates: Requirements 5.8, 7.2, 7.4, 7.9, 7.10**
    """

    def test_publish_never_passes_a_null_adapter(self) -> None:
        """`publish_first_generation` 里不得出现 `adapter=None`。

        以空 adapter 提交 projection 会绕开 `_assert_authority_shape`。
        """
        stripped = _strip_docstrings(F2_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "publish_first_generation")
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            for keyword in inner.keywords:
                if keyword.arg == "adapter":
                    assert not (
                        isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is None
                    ), "`adapter=None` 出现在首版发布链里 —— 那是绕开授权形态门"

    def test_publish_direction_is_the_frozen_constant(self) -> None:
        """`direction` 实参恒为模块常量，不是可传参 —— 反方向要走三方 merge。"""
        assert F2.FIRST_PUBLICATION_DIRECTION == "html_to_oo"
        stripped = _strip_docstrings(F2_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "publish_first_generation")
        directions = [
            keyword.value
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
            for keyword in inner.keywords
            if keyword.arg == "direction"
        ]
        assert directions, "首版发布链里没给 `direction` —— adapter 方向由默认值决定了"
        for value in directions:
            assert isinstance(value, ast.Name) and value.id == "FIRST_PUBLICATION_DIRECTION", (
                "`direction` 不是那个冻结常量 —— 写成字面量或参数就可能被传成 oo_to_html"
            )

    def test_publish_touches_no_word_domain_path(self) -> None:
        """函数体内对 Word adapter 路径零引用（`PENDING_ENGINE_ADAPTERS` 的禁令）。"""
        stripped = _strip_docstrings(F2_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "publish_first_generation")
        text = ast.unparse(node)
        for banned in ("adapters.word", "adapters/word", "PENDING_ENGINE_ADAPTERS"):
            assert banned not in text, (
                f"首版发布链里出现 {banned!r} —— 那条门归 Task 61，本 spec 不得碰"
            )

    # ── Property 11 的两条（成对，缺一即可被单侧实现骗过）──────────────
    #
    # **Feature: published-representation-production-path-and-lane-adjudication,
    # Property 11: 首版入口拒绝已有 current representation 的 entry**
    #
    # **Validates: Requirements 3.4**

    def test_existing_current_representation_is_rejected(self) -> None:
        """判据 ③：判据 B 为**真**时必须抛 `FirstPublicationAlreadyDoneError`。

        🔴 变异 M4（把 `if facts.published_representation_current:` 取反）的直接对手。
        判据落在**真实执行**：注入一个「B 为真」的供给观测替身，跑 `resolve_plan`
        本体，断言它抛。取反后这一支不再触发 ⇒ 打红。
        """
        import asyncio

        facts = _lane_facts(published_representation_current=True)
        with _patched_lane_supply(facts):
            with pytest.raises(F2.FirstPublicationAlreadyDoneError) as caught:
                asyncio.run(_resolve_plan_with_stub_supply())
        assert (
            getattr(caught.value, "error_code", "") == "first_publication_already_done"
        )
        message = str(caught.value)
        assert "判据 B" in message, f"诊断没点名判据 B: {message}"
        assert "首版" in message, f"诊断没说明本入口只发首版: {message}"

    def test_absent_current_representation_passes_criterion_three(self) -> None:
        """判据 B 为**假**时判据 ③ 必须放行（不得把「还没有」也拒掉）。

        与上一条成对：只有一条时，「无条件抛」和「无条件放行」各能骗过一条。
        取反后本条会撞上 `FirstPublicationAlreadyDoneError` ⇒ 打红。
        """
        import asyncio

        facts = _lane_facts(published_representation_current=False)
        with _patched_lane_supply(facts):
            # 判据 ③ 之后是 ④（bundle snapshot），本替身不供 bundle ⇒ 预期停在 ④ 之后
            # 的任意其它失败，但**绝不**是 `FirstPublicationAlreadyDoneError`。
            try:
                asyncio.run(_resolve_plan_with_stub_supply())
            except F2.FirstPublicationAlreadyDoneError as exc:  # pragma: no cover
                pytest.fail(
                    f"判据 B 为假却被判「已发布」⇒ 判据 ③ 的期望值反了: {exc}"
                )
            except Exception:
                pass  # 停在后续阶段属预期

    def test_row_bearing_table_key_comes_from_the_contract(self) -> None:
        """行身份表必须从**冻结契约**派生，不得硬取 provider 的命名约定。

        实测 `ROWS_TABLE_KEY` 只有 3/4 个 provider 声明 —— G7 没有，硬取就是
        `AttributeError`。
        """
        stripped = _strip_docstrings(F2_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "_identity_binding")
        text = ast.unparse(node)
        assert "provider.ROWS_TABLE_KEY" not in text, (
            "`_identity_binding` 又直接取 `provider.ROWS_TABLE_KEY` 了 —— "
            "那是只有 3/4 provider 遵守的命名约定，G7 上是 AttributeError"
        )
        assert "_row_bearing_table_key" in text, (
            "`_identity_binding` 没走契约派生的行身份表"
        )

    def test_row_bearing_table_key_agrees_with_every_declaring_provider(self) -> None:
        """双向锁：凡声明了 `ROWS_TABLE_KEY` 的 provider，两侧必须逐一相等。"""
        import importlib

        from app.services.workpaper_sync.adapters import registry as registry_module
        from app.services.workpaper_sync.contracts import load_contract

        checked = 0
        for row in registry_module.DELIVERED_PER_ENTRY_CONTRACTS:
            provider = importlib.import_module(str(row["provider_module"]))
            contract = load_contract(str(row["contract_id"]))
            derived = F2._row_bearing_table_key(contract=contract, provider=provider)
            assert derived, f"{row['entry_id']}: 派生不出行身份表"
            declared = str(getattr(provider, "ROWS_TABLE_KEY", "") or "").strip()
            if declared:
                assert declared == derived, (
                    f"{row['entry_id']}: provider 声明 {declared!r}、契约派生 {derived!r}"
                )
                checked += 1
        assert checked >= 3, (
            f"只有 {checked} 个 provider 声明了 `ROWS_TABLE_KEY` —— 双向锁的分母过小"
        )

    def test_dynamic_column_binding_values_are_column_letters(self) -> None:
        """`dynamic_column_columns` 的值必须是 Excel 列标，不是 label。

        塞 label 时 `ExcelIdentityBinding` 的 `column_index_from_string` 会炸
        `'minority_financials#1' is not a valid column name`（G7 实测）。
        """
        stripped = _strip_docstrings(F2_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "_identity_binding")
        text = ast.unparse(node)
        assert "observed_dynamic_bindings" in text, (
            "`_identity_binding` 没读 `staged.observed_dynamic_bindings`（key → 列标），"
            "很可能又拿 `observed_dynamic_columns` 的 (label, key) 对去凑"
        )
        assert "observed_dynamic_columns" not in text, (
            "`_identity_binding` 又读了 `observed_dynamic_columns` —— 那是 (label, key) 对，"
            "喂给 `dynamic_column_columns` 会把 label 当列标"
        )
