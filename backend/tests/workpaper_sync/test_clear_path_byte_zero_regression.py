# -*- coding: utf-8 -*-
"""`stale_cleared` 路径的逐字节零回归基线（Requirement 8.6 / 8.7 / 8.8）。

spec: workpaper-sync-row-deletion-multi-region-propagation
Tasks: 18.1（冻结）· 18.2（AST 门控）· 18.3（变异反证）

═══ 为什么基线要在改 6.8b **之前**取 ═══

改完就再也取不到「本 spec 之前」那一份字节了。本文件的冻结值取于：
* `excel_materialize.py` 的 6.8b 与 apply 阶段 0 **尚未改动**；
* `excel_workbook_row_change.py` 已加删行侧的新类与新门面，但那些是**纯增量**
  （插行门面签名逐字不变，`_scan_from_entries` 只是把原门面体内那四步抽成私有函数）。

═══ 🔴 冻结的不是 zip 容器的 sha256 ═══

`_write_entries` 用 `zipfile.writestr(name, payload)`，而那条路径会把**当前时间**写进
每个条目的 `date_time` ⇒ 同一份内容两次打包得到不同的容器字节。冻结容器 sha256 会做出
一个**永红**的门禁，而永红门禁比没有门禁更糟（红成常态 = 没人看）。

所以冻结的是**内容口径**：`{条目名: sha256(载荷)}` 的规范化摘要。它表达的正是
Requirement 8.6 想要的「产物内容一个字节都没变」，且可重现。
本文件另有一条判据**实证**容器 sha256 真的会随时间变（`test_container_sha_is_not_stable`），
免得后来人以为这里是偷懒。
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import sys
import textwrap
import zipfile
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync.adapters.base import SubstrateRole  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState  # noqa: E402

from test_task37_excel_extract import (  # noqa: E402
    BINDING,
    CONTRACT_ID,
    MANAGED_SHEET,
    SPEC,
    TEMPLATE,
    _read_entries,
    _sheet_part_of,
    business_cells,
    contract_payload,
    make_definitions,
    patch_cells,
)

BASELINE_PATH: Path = Path(__file__).with_name("data") / "clear_path_byte_baseline.json"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 固定 substrate + 固定 projection（去掉一个 row key 造 stale）
# ═══════════════════════════════════════════════════════════════════════════

#: 受管区内被改成**非骨架**身份的那一行（K11 受管区 7..25，取中间行避开区首/区末边界）。
#:
#: 🔴 为什么必须改身份而不是直接从 projection 里摘一行：
#:    K11 模板每个受管行的身份都是 `GTROW-K11-00NN`，属**模板预生成骨架**，而 6.8b 的
#:    stale 判据里明确把骨架行排除（`is_template_skeleton_identity`）—— 骨架行「不在
#:    store 的 row_keys 里」是常态，不代表用户删了行。首版基线因此得到
#:    `stale_cleared=[]`、`blank_write_count=0`，**基线挂在一条不含收敛的路径上**，
#:    18.3 的变异反证会假绿。
STALE_ROW = 19
#: 运行期 mint 前缀（与模板骨架**刻意不同域**，见 `excel_extract.MINTED_ROW_IDENTITY_PREFIX`）。
STALE_IDENTITY = "GTROW-MINTED-CLEARBASE1"
UUID_COLUMN = BINDING.uuid_column


def make_substrate_bytes() -> bytes:
    """固定 substrate：真模板 → instrumentation → 业务值 → 一行换成非骨架身份。

    守卫与冻结脚本**共用本函数**，两边不会变成两份口径。
    """
    gate = EI.ExcelIdentityCarrierGate.load()
    instrumented = EI.instrument_workbook_bytes(
        TEMPLATE.read_bytes(), SPEC, gate=gate
    ).instrumented_bytes
    part = _sheet_part_of(instrumented, MANAGED_SHEET)
    patched = patch_cells(instrumented, part, business_cells())
    return patch_cells(patched, part, {f"{UUID_COLUMN}{STALE_ROW}": STALE_IDENTITY})


@pytest.fixture(scope="module")
def substrate_bytes() -> bytes:
    return make_substrate_bytes()


@pytest.fixture(scope="module")
def world(substrate_bytes: bytes, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    workdir = tmp_path_factory.mktemp("clear-path-baseline")
    base = workdir / "base.xlsx"
    base.write_bytes(substrate_bytes)
    contract = parse_contract(contract_payload(), adapter_id=CONTRACT_ID)
    from app.services.excel_structure_fingerprint import identity_inventory

    inventory = identity_inventory(
        substrate_bytes,
        expected_table=BINDING.table_name,
        uuid_column_letter=BINDING.uuid_column,
    )
    definitions = make_definitions(contract, inventory)
    outcome = X.extract_projection(
        artifact=base,
        definitions=definitions,
        binding=BINDING,
        substrate_role=SubstrateRole.published_representation,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.published,
    )
    with zipfile.ZipFile(base) as zf:
        runtime_binding = X.read_runtime_binding_pairs(zf)
    return {
        "base": base,
        "contract": contract,
        "outcome": outcome,
        "runtime_binding": runtime_binding,
        "entries": _read_entries(substrate_bytes),
    }


def _projection_missing_one_row(outcome: Any) -> tuple[Any, str, str]:
    """把 projection 的某个 table 少声明**那一个非骨架身份** ⇒ 它成为 stale。

    🔴 **不是**「构造一个空 projection」：那会让容量分级判成「删后剩 0 行」而走另一条
    分支（上游更正 6），基线就不再观测本 spec 关心的那条路。
    🔴 也**不是**随便摘一行：摘骨架行不产生 stale（见 `STALE_ROW` 的注释）。
    """
    import dataclasses

    projection = outcome.projection
    row_keys = dict(projection.row_keys)
    table_key = next(
        (k for k, rows in row_keys.items() if STALE_IDENTITY in rows), None
    )
    assert table_key is not None, (
        f"projection 里找不到非骨架身份 {STALE_IDENTITY} ⇒ 造不出 stale。"
        f"实测 row_keys = { {k: list(v)[:3] for k, v in row_keys.items()} }"
    )
    row_keys[table_key] = tuple(r for r in row_keys[table_key] if r != STALE_IDENTITY)
    # 字段值也要一起摘掉，否则 merged projection 仍声明该行的字段 ⇒ 行集一致性判据先拦
    values = {
        key: value
        for key, value in dict(getattr(projection, "values", {}) or {}).items()
        if f"/{STALE_IDENTITY}/" not in str(key)
    }
    replaced = dataclasses.replace(projection, row_keys=row_keys)
    if hasattr(replaced, "values"):
        replaced = dataclasses.replace(replaced, values=values)
    return replaced, table_key, STALE_IDENTITY


def _plan_with_stale(world: dict[str, Any]) -> tuple[M.MaterializePlan, str, str]:
    projection, table_key, dropped = _projection_missing_one_row(world["outcome"])
    plan = M.plan_managed_writes(
        projection=projection,
        contract=world["contract"],
        binding=BINDING,
        region=world["outcome"].region,
        scan=world["outcome"].scan,
        substrate_entries=world["entries"],
        substrate_formulas=world["outcome"].formula_inventory,
        runtime_binding=world["runtime_binding"],
    )
    return plan, table_key, dropped


def _content_digest(data: bytes) -> dict[str, Any]:
    """`{条目名: sha256(载荷)}` 的规范化摘要 —— 内容口径，与打包时间无关。"""
    with zipfile.ZipFile(__import__("io").BytesIO(data)) as zf:
        per_entry = {
            name: hashlib.sha256(zf.read(name)).hexdigest()
            for name in sorted(zf.namelist())
        }
    payload = json.dumps(per_entry, sort_keys=True, separators=(",", ":"))
    return {
        "entry_count": len(per_entry),
        "per_entry": per_entry,
        "rolling": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. 冻结 / 比对
# ═══════════════════════════════════════════════════════════════════════════


def _freeze(world: dict[str, Any]) -> dict[str, Any]:
    plan, table_key, dropped = _plan_with_stale(world)
    product, report = M.apply_plan_zip_with_report(
        world["base"].read_bytes(), plan
    )
    return {
        "spec": "workpaper-sync-row-deletion-multi-region-propagation",
        "task": "18.1",
        "note": (
            "stale_cleared 路径的**内容口径**字节基线。容器 sha256 不可冻结"
            "（writestr 写当前时间），见模块 docstring。"
        ),
        "substrate_content": _content_digest(world["base"].read_bytes()),
        "stale_table_key": table_key,
        "stale_identity": dropped,
        "plan": {
            "stale_cleared": list(plan.stale_cleared),
            "stale_deleted": list(plan.stale_deleted),
            "row_shift": None if plan.row_shift is None else plan.row_shift.as_dict(),
            "write_count": len(plan.writes),
            "blank_write_count": sum(
                1 for w in plan.writes if w.kind is M.CellWriteKind.blank
            ),
        },
        "product_content": _content_digest(product),
        "shift_report": None if report is None else True,
    }


class TestClearPathByteBaseline:
    """**Validates: Requirements 8.6**"""

    def test_baseline_file_exists(self) -> None:
        assert BASELINE_PATH.is_file(), (
            f"字节基线缺失：{BASELINE_PATH.relative_to(_REPO)} —— 它必须入库，"
            "否则干净 checkout 下本守卫无从比对。重生成："
            "`python -m pytest <本文件> --freeze-clear-path-baseline`"
        )

    def test_scenario_is_the_clear_branch_not_the_delete_branch(
        self, world: dict[str, Any]
    ) -> None:
        """🔴 先证明这条基线**真的在观测清空分支**，否则它冻结的是别的东西。"""
        plan, _table, _dropped = _plan_with_stale(world)
        assert plan.stale_cleared, (
            "造不出 stale 行 ⇒ 基线挂在一条不含收敛的路径上，18.3 的变异反证会假绿"
        )
        assert plan.stale_deleted == (), (
            f"本 spec 落地前不该有删行计划，实得 {plan.stale_deleted}"
        )
        assert plan.row_shift is None, "本场景不该插行（插行会把基线带到另一条分支）"
        blanks = [w for w in plan.writes if w.kind is M.CellWriteKind.blank]
        assert blanks, "清空分支没产出 blank 写入 ⇒ 收敛实际没发生"

    def test_product_content_matches_frozen_baseline(
        self, world: dict[str, Any]
    ) -> None:
        """同一 substrate + 同一 projection ⇒ 产物内容摘要与冻结值逐值相等。"""
        stored = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        current = _freeze(world)
        assert current["substrate_content"]["rolling"] == stored["substrate_content"]["rolling"], (
            "substrate 本身变了 ⇒ 产物比对无意义。若模板/instrumentation 有意变更，"
            "须显式重生成基线并在提交说明里论证每一处 diff 的合法性"
        )
        assert current["plan"] == stored["plan"], (
            f"计划形态变了：现算 {current['plan']} / 冻结 {stored['plan']}"
        )
        got = current["product_content"]
        want = stored["product_content"]
        assert got["entry_count"] == want["entry_count"], (
            f"产物条目数 {got['entry_count']} ≠ 冻结 {want['entry_count']}"
        )
        differing = sorted(
            name
            for name in set(got["per_entry"]) | set(want["per_entry"])
            if got["per_entry"].get(name) != want["per_entry"].get(name)
        )
        assert not differing, (
            f"`stale_cleared` 路径的产物内容变了，差异条目 {differing}。\n"
            "🔴 若这是**有意**变更：改 `data/clear_path_byte_baseline.json` 的期望值，"
            "并在提交说明里逐处论证每一个条目 diff 的合法性。\n"
            "若不是有意的：本 spec 的删行改动漏进了清空分支 —— 那正是 Requirement 8.6 要拦的。"
        )
        assert got["rolling"] == want["rolling"]

    def test_container_sha_is_not_stable(self, world: dict[str, Any]) -> None:
        """🔴 实证「为什么不冻结容器 sha256」——`writestr` 把当前时间写进条目头。

        没有这条判据的话，后来人会以为「只比内容」是偷懒，进而把容器 sha 冻进去，
        做出一个永红的门禁。
        """
        import time

        source = world["base"].read_bytes()
        plan, _t, _d = _plan_with_stale(world)
        first, _ = M.apply_plan_zip_with_report(source, plan)
        time.sleep(2.1)  # zip 的 date_time 粒度是 2 秒
        second, _ = M.apply_plan_zip_with_report(source, plan)
        assert hashlib.sha256(first).hexdigest() != hashlib.sha256(second).hexdigest(), (
            "容器 sha256 两次相同 —— 若 `_write_entries` 已改成固定 date_time，"
            "那就可以直接冻结容器 sha，本文件的内容口径可以简化（请一并更新 docstring）"
        )
        # 而内容口径必须相同（否则本文件的整个前提不成立）
        assert _content_digest(first)["rolling"] == _content_digest(second)["rolling"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. Task 18.2：路径层 AST 断言 —— 删行计划的产出被 `row_convergence` 门控
# ═══════════════════════════════════════════════════════════════════════════


class TestDeletionIsGatedByTheContract:
    """**Validates: Requirement 8.7**

    🔴 判据取赋值语句的**祖先条件链**，不用字符串 grep：`row_convergence` /
    `deletes_physical_rows` 在 `plan_managed_writes` 的注释与 docstring 里出现过多次，
    文本匹配必然假绿（工作区铁律 ㉖）。
    """

    @staticmethod
    def _ancestor_conditions(func: Any, *, call_name: str) -> list[str]:
        """`call_name` 那次调用所在赋值语句的**全部祖先 `if` 条件**（自外向内）。"""
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
        # 先给每个节点挂上父指针（ast 不提供）
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node

        target: ast.AST | None = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == call_name
            ):
                target = node
                break
        assert target is not None, f"找不到 {call_name} 的调用"

        conditions: list[str] = []
        cursor: ast.AST | None = target
        child: ast.AST | None = None
        while cursor is not None:
            parent = parents.get(cursor)
            if isinstance(parent, ast.If):
                # 🔴 必须分清落在 `body` 还是 `orelse`：`elif` 链里目标在 orelse 上时，
                #    该层条件对它是**取反**成立的，直接收集会把语义写反。
                in_body = any(child is stmt or cursor is stmt for stmt in parent.body)
                conditions.append(
                    f"{'' if in_body else 'not '}{ast.unparse(parent.test)}"
                )
            child = cursor
            cursor = parent
        return list(reversed(conditions))

    def test_deletion_call_is_under_the_contract_gate(self) -> None:
        """🔴 `_plan_row_deletion` 的调用必须落在「契约已开启」这个条件之下。

        条件链现算应含三项（自外向内）：
        `stale_rows` → `not (remaining <= 0)` → `not (not deletes_physical_rows)`
        → `not orphan`。判据只钉死**契约那一项必须在链上且是肯定形态**，
        其余项由 `test_row_deletion_convergence_dispatch` 的顺序判据负责。
        """
        chain = self._ancestor_conditions(M.plan_managed_writes, call_name="_plan_row_deletion")
        assert chain, "`_plan_row_deletion` 不在任何条件之下 ⇒ 门控不存在"
        gate = [c for c in chain if "deletes_physical_rows" in c]
        assert len(gate) == 1, (
            f"契约门控在条件链上出现 {len(gate)} 次（应为 1）。链：{chain}"
        )
        # `elif not deletes_physical_rows:` 的 orelse 分支 ⇒ 收集出来是双重否定
        assert gate[0].startswith("not "), (
            f"契约门控在链上是**否定**形态 {gate[0]!r} ⇒ 语义反了：那会变成"
            "「契约没开启才删行」"
        )
        assert "not not " in gate[0] or "not (not " in gate[0], (
            f"门控形态不是预期的双重否定：{gate[0]!r} —— "
            "若分流结构改成正向 `if deletes_physical_rows:`，请同步更新本判据"
        )

    def test_stale_cleared_is_not_under_the_contract_gate(self) -> None:
        """🔴 反面：清空分支**不得**被契约门控 —— 它是默认行为，任何契约都要能走。

        没有这条，把整个 6.8b 包进 `if deletes_physical_rows:` 也是绿的，
        而那会让未开启删行的表连清空都不做（stale 行被静默留下 ⇒ 又一轮 extra）。
        """
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(M.plan_managed_writes)))
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        assigns = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "stale_cleared" for t in node.targets
            )
            and not isinstance(node.value, ast.Tuple)  # 排除初值 `= ()`
        ]
        assert len(assigns) == 1, f"`stale_cleared` 的实质赋值应恰 1 处，实得 {len(assigns)}"
        cursor: ast.AST | None = assigns[0]
        conds: list[str] = []
        while cursor is not None:
            parent = parents.get(cursor)
            if isinstance(parent, ast.If):
                conds.append(ast.unparse(parent.test))
            cursor = parent
        assert not any("deletes_physical_rows" in c for c in conds), (
            f"清空分支被契约门控了：{conds} —— 未开启删行的表会连清空都不做"
        )

    def test_the_scanner_would_catch_a_missing_gate(self) -> None:
        """🔴 变异反证（扫描器层）：同一个扫描器在**无门控**的函数上必须返回空链。

        没有这条，`_ancestor_conditions` 永远返回非空也会让上面那条绿。
        """

        def _ungated() -> Any:
            return _plan_row_deletion_stub()

        def _plan_row_deletion_stub() -> Any:  # pragma: no cover - 仅作扫描靶
            return None

        chain = self._ancestor_conditions(_ungated, call_name="_plan_row_deletion_stub")
        assert chain == [], f"无门控的函数也算出了条件链 {chain} ⇒ 扫描器失效"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Task 18.3：变异反证 —— 门控改恒真 ⇒ 18.1 的字节基线打红
# ═══════════════════════════════════════════════════════════════════════════


class TestForcingTheGateBreaksTheBaseline:
    """**Validates: Requirement 8.8**

    🔴 只有它打红才证明第 18.1 层**真的在观测字节**；不打红说明基线挂错了对象。

    变异手段：把 `TableSpec.deletes_physical_rows` 这个 property 换成恒 `True`
    （= 「全部契约都开启了删行」）。这是**最贴近真实误操作**的变异 ——
    改默认值、漏判门控、或把分流条件写反，三者的效果都等价于此。
    """

    @staticmethod
    def _force_gate(monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.workpaper_sync.contracts import TableSpec

        monkeypatch.setattr(
            TableSpec, "deletes_physical_rows", property(lambda self: True)
        )

    def test_gate_is_actually_flipped(
        self, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """前提：变异真的生效（K11 契约本来是 clear）。"""
        table = next(
            t
            for sheet in world["contract"].sheets
            for t in sheet.tables
            if t.table_key == BINDING.table_key
        )
        assert table.deletes_physical_rows is False, "K11 契约本来就开着删行 ⇒ 变异无意义"
        self._force_gate(monkeypatch)
        assert table.deletes_physical_rows is True, "monkeypatch 没生效"

    def test_forced_gate_no_longer_reproduces_the_frozen_bytes(
        self, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 门控恒真后，18.1 那条字节基线**必须**不再成立。

        K11 的受管行被 6 处跨 sheet 单格引用指着（`'审定表K11-1'!A19/G19/D19` × sheet4/5），
        所以走删行分支时计划期就会被 `DanglingReferenceError` 拦住 —— 那同样是「基线不再
        成立」，而且是比「字节不同」更早、更响的一种红。两种形态都接受，但必须**是其中之一**：
        既不抛也不变 = 门控形同虚设而基线察觉不到，那才是要拦的假绿。
        """
        from app.services.workpaper_sync import excel_workbook_row_change as N1

        stored = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        self._force_gate(monkeypatch)

        raised: Exception | None = None
        current: dict[str, Any] | None = None
        try:
            current = _freeze(world)
        except (N1.DanglingReferenceError, M.RowSetDivergenceError) as exc:
            raised = exc

        if raised is not None:
            assert "#REF!" in str(raised) or "convergence" in str(raised), str(raised)
            return
        assert current is not None
        assert (
            current["plan"] != stored["plan"]
            or current["product_content"]["rolling"] != stored["product_content"]["rolling"]
        ), (
            "门控恒真之后计划与产物**都**与冻结值相同 ⇒ 基线没在观测删行分支，"
            "18.1 是假绿（Requirement 8.8）"
        )

    def test_without_the_mutation_the_baseline_still_holds(
        self, world: dict[str, Any]
    ) -> None:
        """🔴 对照组：不做变异时基线**成立**。

        两条成对才说明上一条打红来自变异本身，而不是基线本来就已经坏了。
        """
        stored = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        current = _freeze(world)
        assert current["plan"] == stored["plan"]
        assert (
            current["product_content"]["rolling"] == stored["product_content"]["rolling"]
        )

    def test_k11_mutation_raises_before_reaching_the_byte_comparison(
        self, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 如实登记 K11 变异的**实际形态**：它抛，而不是产出不同字节。

        实测：门控恒真后 K11 在计划期就撞 `DanglingReferenceError`
        （受管行被 `'审定表K11-1'!A19/G19/D19` × sheet4/sheet5 共 6 处单格引用指着）。

        ⚠ 这条形态**单独不足以**满足 Requirement 8.8：它证明了「门控被改就会出事」，
        但**没走到字节比对**，所以证明不了「那条字节基线真的在观测字节」。
        字节级的证明在下一条（换 D1-8 靶子）。把这件事写成判据而不是注释，
        是因为「变异测试绿了」与「变异测试在测它声称要测的东西」是两回事。
        """
        from app.services.workpaper_sync import excel_workbook_row_change as N1

        self._force_gate(monkeypatch)
        with pytest.raises(N1.DanglingReferenceError) as err:
            _freeze(world)
        assert "#REF!" in str(err.value)

    def test_the_gate_really_controls_bytes_on_a_deletable_target(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 字节级变异反证（Requirement 8.8 的实质）：**同一份输入**，只翻门控
        ⇒ 产物字节必须不同。

        换 D1-8 做靶子，因为它受管区 14..21 **每一行都可删**（现算：各 7 条传播声明），
        于是删行分支能真的跑完并落出字节 —— K11 在计划期就被拦住，走不到这一步。

        这条与上一条合起来才构成完整证明：
        * 上一条 —— 门控被改，K11 这类不可删的表会 fail-closed（不会产坏字节）；
        * 本条   —— 门控被改，可删的表会产出**不同的字节** ⇒ 字节口径确实在观测门控。
        """
        import test_row_deletion_convergence_dispatch as DSP

        world = DSP._build_d18_world()
        projection = DSP._projection_missing_the_minted_row(world["outcome"])

        gated_plan = DSP._plan_with_convergence(world, None, projection=projection)
        assert gated_plan.stale_cleared and gated_plan.stale_deleted == (), (
            f"对照组没落在清空分支：{gated_plan.as_dict()}"
        )
        gated_product, _ = M.apply_plan_zip_with_report(
            world["base"].read_bytes(), gated_plan
        )

        self._force_gate(monkeypatch)
        forced_plan = DSP._plan_with_convergence(world, None, projection=projection)
        assert forced_plan.stale_deleted == gated_plan.stale_cleared, (
            "门控恒真后没改走删行 ⇒ 变异没生效，本条判据空转："
            f"{forced_plan.as_dict()}"
        )
        forced_product, _ = M.apply_plan_zip_with_report(
            world["base"].read_bytes(), forced_plan
        )

        before = _content_digest(gated_product)
        after = _content_digest(forced_product)
        assert before["rolling"] != after["rolling"], (
            "门控恒真后产物内容摘要**相同** ⇒ 字节口径察觉不到删行，"
            "18.1 那层基线是假绿（Requirement 8.8）"
        )
        differing = sorted(
            name
            for name in set(before["per_entry"]) | set(after["per_entry"])
            if before["per_entry"].get(name) != after["per_entry"].get(name)
        )
        # 受管 sheet 与本表 Table part 必在差异里（物理删行 + ref 收缩）
        assert any("worksheets/" in n for n in differing), differing
        assert any(n.startswith("xl/tables/") for n in differing), differing
