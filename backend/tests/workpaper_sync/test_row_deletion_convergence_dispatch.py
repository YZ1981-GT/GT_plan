"""6.8b 分流：clear / delete / 共存降级（Property 4 + Property 19）。

spec: workpaper-sync-row-deletion-multi-region-propagation
Tasks: 17.1 · 17.2 · 17.3
Requirements: 1.11 · 8.4 · 9.1 ~ 9.6

═══ 判定树（design § 删与插共存 4.2）═══

    stale_rows 非空？
    ├─ 否 → 两个分支都空
    └─ 是 → 删后受管区剩余有身份数据行 <= 0 ？
            ├─ 是 → stale_cleared（容量归零）
            └─ 否 → 契约 row_convergence == delete ？
                    ├─ 否 → stale_cleared（默认，逐字节零回归）
                    └─ 是 → orphan 非空（删与插共存）？
                            ├─ 是 → stale_cleared ＋ 可观测降级原因
                            └─ 否 → stale_deleted（真正走删行）

🔴 本文件的重点是**全组合覆盖**（Requirement 9.5）：apply 期那条
`[convergence_delete_with_insert_unsupported]` 必须**不可达**。判据不是「断言那个 raise
不存在」（那等于把纵深防御删掉），而是断言计划期分流覆盖了
「stale 有无 × orphan 有无 × 容量是否归零 × 契约是否开启」的全部组合。
"""

from __future__ import annotations

import ast
import inspect
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# 1. 分流判定树的结构锁（AST，不依赖能否造出四类输入）
# ═══════════════════════════════════════════════════════════════════════════


def _dispatch_source() -> str:
    """`plan_managed_writes` 里 6.8b 分流那一段源码。"""
    return textwrap.dedent(inspect.getsource(M.plan_managed_writes))


class TestDispatchTreeStructure:
    """**Validates: Requirements 8.4, 9.1, 9.3, 9.5**

    🔴 这一节用 AST 而不是文本 `in`（工作区铁律 ㉖）：判定树的四个条件里
    `row_convergence` / `orphan` / `remaining` 这些名字在同一个函数的注释与 docstring 里
    都出现过好几次，文本匹配必然假绿。
    """

    def test_four_conditions_are_all_present_in_order(self) -> None:
        """四个判定条件都在，且**顺序**是「容量 → 契约 → 共存」。

        顺序是正确性的一部分：容量归零必须在契约门控**之前**判，否则一张已开启的表在
        「store 把整表清空」时会真把受管区删空 ⇒ 下一次 extract 抛
        `IdentityCarrierMissingError`。
        """
        tree = ast.parse(_dispatch_source())
        # 找到 `if stale_rows:` 那个节点
        target: ast.If | None = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Name)
                and node.test.id == "stale_rows"
            ):
                target = node
                break
        assert target is not None, "找不到 `if stale_rows:` 分流入口"

        # 逐级收集 if/elif 链上每一层的条件源码
        conditions: list[str] = []
        chain: list[ast.stmt] = list(target.body)
        cursor: Any = None
        for stmt in chain:
            if isinstance(stmt, ast.If):
                cursor = stmt
                break
        assert cursor is not None, "`if stale_rows:` 里没有第二层判定 ⇒ 分流树没建起来"
        while isinstance(cursor, ast.If):
            conditions.append(ast.unparse(cursor.test))
            nxt = cursor.orelse[0] if len(cursor.orelse) == 1 else None
            cursor = nxt if isinstance(nxt, ast.If) else None

        assert len(conditions) == 3, (
            f"判定链应有 3 层（容量 / 契约 / 共存），实得 {len(conditions)}：{conditions}"
        )
        assert "remaining_after_delete" in conditions[0], conditions
        assert "deletes_physical_rows" in conditions[1], conditions
        assert conditions[2] == "orphan", conditions

    def test_insert_at_is_not_recomputed_for_coexistence(self) -> None:
        """🔴 Requirement 9.3：共存时**不**在删行前口径重算插入点。

        重算那条路要求「删后重算 insert_at」，是独立能力；在这里凑会得到一个没有判据
        覆盖的行号。判据：分流段里没有对 `insert_at` 的**赋值**。
        """
        tree = ast.parse(_dispatch_source())
        assigned: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Attribute) and tgt.attr == "insert_at":
                        assigned.append(ast.unparse(node))
                    if isinstance(tgt, ast.Name) and tgt.id == "insert_at":
                        assigned.append(ast.unparse(node))
        assert not assigned, f"分流里重算了插入点：{assigned}"

    def test_apply_side_depth_defence_is_retained(self) -> None:
        """🔴 apply 期的共存拦截**必须保留**（Requirement 9.4）。

        判据是「它还在」而不是「它不可达」—— 纵深防御的价值恰恰在于计划期漂移时它会叫。
        """
        src = textwrap.dedent(inspect.getsource(M.apply_plan_zip_with_report))
        tree = ast.parse(src)
        raises = [
            ast.unparse(node)
            for node in ast.walk(tree)
            if isinstance(node, ast.Raise)
            and "convergence_delete_with_insert_unsupported" in ast.unparse(node)
        ]
        assert len(raises) == 1, (
            f"apply 期的共存拦截不见了或重复了（实得 {len(raises)} 处）—— "
            "它是纵深防御，计划期分流漂移时靠它兜住"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Property 19：共存降级为清空且原因可读
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty19CoexistenceDegradesToClear:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 19: 共存降级为清空且原因可读**

    **Validates: Requirements 9.1, 9.2, 9.5, 9.6**
    """

    def test_reason_is_exposed_in_the_readable_summary(self) -> None:
        """🔴 降级原因必须进 `MaterializePlan.as_dict()`（Requirement 9.2 / 9.6）。

        不可观测的降级 = 「删行功能上线了但在双向变更的 entry 上从来没跑过」这种
        看不见的空转 —— 那正是平台反复踩的「能力已建 ≠ 接线完整」的另一面。
        """
        plan = M.MaterializePlan(
            sheet_part="xl/worksheets/sheet1.xml",
            sheet_name="s",
            writes=(),
            preserved_formulas={},
            dynamic_column_columns={},
            stale_cleared=(7,),
            stale_clear_reason="delete_with_insert_coexist: 测试文案",
        )
        payload = plan.as_dict()
        assert payload["stale_clear_reason"] == "delete_with_insert_coexist: 测试文案"
        assert payload["stale_cleared"] == [7]
        assert payload["stale_deleted"] == []

    def test_default_path_writes_no_reason(self) -> None:
        """🔴 契约未开启是**常态不是降级** ⇒ 不写 reason。

        全都写的话真正的降级会在日志里淹没，而 Requirement 9.2 要的正是降级可观测。
        """
        src = _dispatch_source()
        tree = ast.parse(src)
        target = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "stale_rows"
        )
        cursor: Any = next(s for s in target.body if isinstance(s, ast.If))
        # 第二层（契约未开启）的 body 里不得有对 stale_clear_reason 的赋值
        second = cursor.orelse[0]
        assert isinstance(second, ast.If)
        assigns = [
            ast.unparse(n)
            for n in ast.walk(ast.Module(body=list(second.body), type_ignores=[]))
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "stale_clear_reason"
                for t in n.targets
            )
        ]
        assert not assigns, f"契约未开启这一支写了降级原因：{assigns}"

    @pytest.mark.parametrize(
        "reason_token",
        ["capacity_would_reach_zero", "delete_with_insert_coexist"],
    )
    def test_each_degrade_reason_is_a_stable_machine_readable_token(
        self, reason_token: str
    ) -> None:
        """🔴 降级原因带**机器可读前缀**：判据与运维都按 token 匹配，不按中文散文。

        中文文案会被改写（本仓库的错误文案经常润色），token 是稳定契约。
        """
        src = _dispatch_source()
        assert f'"{reason_token}:' in src or f"'{reason_token}:" in src, (
            f"分流里找不到降级 token {reason_token!r} —— 判据与运维无法按稳定串匹配"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Property 4：删行计划必带两份声明
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty4DeletePlanCarriesBothDeclarations:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 4: 删行计划必带两份声明**

    **Validates: Requirement 1.11**
    """

    def test_planner_sets_both_carrier_and_change_set(self) -> None:
        """AST：走删行那一支时 `row_deletion` 与 `deletion_change` **同时**被赋值。

        只有前者 ⇒ definedName 与跨 sheet 公式仍指旧行号；只有后者 ⇒ 物理行没删。
        """
        src = _dispatch_source()
        tree = ast.parse(src)
        # 找 `_plan_row_deletion(...)` 的那条赋值
        call_assigns = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", "") == "_plan_row_deletion"
        ]
        assert len(call_assigns) == 1, (
            f"`_plan_row_deletion` 的调用点应恰好 1 处，实得 {len(call_assigns)}"
        )
        targets = ast.unparse(call_assigns[0].targets[0])
        for name in ("row_deletion", "deletion_change", "stale_deleted"):
            assert name in targets, f"删行支没赋值 {name}：{targets}"

    def test_helper_returns_both_declarations(self) -> None:
        """`_plan_row_deletion` 自己产出两份声明（正源在它里面，不在调用点拼）。"""
        src = textwrap.dedent(inspect.getsource(M._plan_row_deletion))
        tree = ast.parse(src)
        called = {
            getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
        }
        assert "RowDeletionShift" in called, sorted(c for c in called if c)
        assert "plan_workbook_row_change_for_delete" in called, sorted(
            c for c in called if c
        )

    def test_trace_key_is_the_row_identity_not_the_row_number(self) -> None:
        """🔴 留痕键取**行身份**而不是行号（Requirement 1.9）。

        行号删完就变了，拿它留痕等于留了一个第二天就对不上的东西。
        """
        src = textwrap.dedent(inspect.getsource(M._plan_row_deletion))
        tree = ast.parse(src)
        kwargs = {
            kw.arg: ast.unparse(kw.value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "plan_workbook_row_change_for_delete"
            for kw in n.keywords
        }
        assert "row_uuids" in kwargs, sorted(kwargs)
        assert "stale_rows" in kwargs["row_uuids"], (
            f"留痕键不是从 stale_rows（行号→行身份）来的：{kwargs['row_uuids']}"
        )

    def test_total_rows_and_table_part_are_wired_for_deletion_too(self) -> None:
        """🔴 删行支必须**也**设 `total_formula_rows` 与 `table_part`。

        不设的后果是两条 fail-closed：合计区间不收缩（A7 上界判据拦）与本表 Table ref
        不收缩（`[convergence_table_ref_not_shrunk]`）。两者都不产坏字节，
        但症状离真因很远。
        """
        src = _dispatch_source()
        tree = ast.parse(src)
        resolves = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", "")
            == "_resolve_total_rows_and_table_part"
        ]
        assert len(resolves) == 1, (
            f"分流段里 `_resolve_total_rows_and_table_part` 调用应恰好 1 处，"
            f"实得 {len(resolves)}"
        )
        targets = ast.unparse(resolves[0].targets[0])
        assert "total_formula_rows" in targets and "table_part" in targets, targets

    def test_the_derivation_has_a_single_source(self) -> None:
        """🔴 插行与删行共用同一个推导函数（禁第二份）。

        两处各写一份的症状是「删行侧合计不收缩 / Table ref 不收缩」，
        而那两条各自的 fail-closed 会在很远的地方报出来。
        """
        shift_src = textwrap.dedent(inspect.getsource(M._plan_row_shift))
        shift_calls = {
            getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            for n in ast.walk(ast.parse(shift_src))
            if isinstance(n, ast.Call)
        }
        assert "_resolve_total_rows_and_table_part" in shift_calls, (
            f"插行侧没走共用推导 ⇒ 已经有两份了：{sorted(c for c in shift_calls if c)}"
        )
        # 且推导函数自己只被这两处调用
        module_src = Path(M.__file__).read_bytes().decode("utf-8")
        module_tree = ast.parse(module_src)
        callers = [
            node
            for node in ast.walk(module_tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", "") == "_resolve_total_rows_and_table_part"
        ]
        assert len(callers) == 2, (
            f"共用推导的调用点应恰好 2 处（插行 / 删行），实得 {len(callers)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 全组合覆盖：使 apply 期共存拦截不可达
# ═══════════════════════════════════════════════════════════════════════════


class TestDispatchCoversAllCombinations:
    """**Validates: Requirement 9.5**

    「stale 有无 × orphan 有无 × 容量归零 × 契约开启」= 16 种组合。
    🔴 这里用**判定树求值**而不是端到端造 16 份 substrate：造 16 份真实工作簿需要
    16 套契约与模板，而判定树本身是纯逻辑 —— 把它复刻一遍（**复刻而非 import 私有逻辑**，
    与上游同款纪律）并断言复刻结果与生产 AST 的条件顺序一致，比造不出来的端到端更可靠。
    """

    @staticmethod
    def _expected(
        *, stale: bool, orphan: bool, capacity_zero: bool, contract_delete: bool
    ) -> str:
        """判定树的**复刻**（与生产逻辑同构，顺序照 design 4.2）。"""
        if not stale:
            return "neither"
        if capacity_zero:
            return "cleared:capacity_would_reach_zero"
        if not contract_delete:
            return "cleared:default"
        if orphan:
            return "cleared:delete_with_insert_coexist"
        return "deleted"

    def test_all_sixteen_combinations_are_decided(self) -> None:
        """全 16 组合都有确定归属，且**没有任何一组**落到「删与插共存下走删行」。

        后半句正是「apply 期拦截不可达」的形式化：只要存在一组 stale∧orphan 归到
        `deleted`，那条 raise 就可达。
        """
        outcomes: dict[tuple[bool, bool, bool, bool], str] = {}
        for stale in (False, True):
            for orphan in (False, True):
                for capacity_zero in (False, True):
                    for contract_delete in (False, True):
                        outcomes[(stale, orphan, capacity_zero, contract_delete)] = (
                            self._expected(
                                stale=stale,
                                orphan=orphan,
                                capacity_zero=capacity_zero,
                                contract_delete=contract_delete,
                            )
                        )
        assert len(outcomes) == 16
        coexist_deleted = [
            key for key, val in outcomes.items() if key[0] and key[1] and val == "deleted"
        ]
        assert not coexist_deleted, (
            f"存在「stale ∧ orphan ⇒ 走删行」的组合 {coexist_deleted} ⇒ "
            "apply 期的共存拦截可达，Requirement 9.5 不成立"
        )
        # 唯一走删行的组合：stale ∧ 无 orphan ∧ 容量未归零 ∧ 契约开启
        deleted = [key for key, val in outcomes.items() if val == "deleted"]
        assert deleted == [(True, False, False, True)], deleted

    def test_default_contract_never_deletes(self) -> None:
        """🔴 契约未开启（= 全部既有契约）下，**任何**组合都不走删行。

        这是「逐字节零回归」在分流层面的表述。
        """
        for stale in (False, True):
            for orphan in (False, True):
                for capacity_zero in (False, True):
                    got = self._expected(
                        stale=stale,
                        orphan=orphan,
                        capacity_zero=capacity_zero,
                        contract_delete=False,
                    )
                    assert got != "deleted", (stale, orphan, capacity_zero, got)

    def test_replica_matches_production_condition_order(self) -> None:
        """🔴 复刻与生产**同构**的证明：条件顺序逐项对齐。

        没有这条，上面两条测的就只是我自己写的那个函数。
        """
        tree = ast.parse(_dispatch_source())
        target = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "stale_rows"
        )
        cursor: Any = next(s for s in target.body if isinstance(s, ast.If))
        order: list[str] = []
        while isinstance(cursor, ast.If):
            order.append(ast.unparse(cursor.test))
            nxt = cursor.orelse[0] if len(cursor.orelse) == 1 else None
            cursor = nxt if isinstance(nxt, ast.If) else None
        # 复刻里的顺序：capacity → contract → orphan
        replica_order = ["capacity_zero", "contract_delete", "orphan"]
        production_tokens = ["remaining_after_delete", "deletes_physical_rows", "orphan"]
        assert len(order) == len(replica_order) == len(production_tokens)
        for idx, (token, cond) in enumerate(zip(production_tokens, order)):
            assert token in cond, f"第 {idx + 1} 层条件不是 {token}：{cond}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. 契约门控与分流的接线
# ═══════════════════════════════════════════════════════════════════════════


def test_dispatch_reads_the_contract_through_the_single_property() -> None:
    """🔴 分流判「是否开启」只走 `TableSpec.deletes_physical_rows`。

    各处自己写 `spec.row_convergence is RowConvergenceMode.delete` 就会漂
    （漏一处 = 一处静默按 clear 走或反之）。
    """
    src = _dispatch_source()
    assert "deletes_physical_rows" in src
    tree = ast.parse(src)
    direct = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare) and "RowConvergenceMode" in ast.unparse(node)
    ]
    assert not direct, f"分流里直接比对枚举了（应走属性）：{direct}"
    assert isinstance(C.TableSpec.deletes_physical_rows, property)


# ═══════════════════════════════════════════════════════════════════════════
# 6. 真实链路：契约开关一翻，`plan_managed_writes` 真的产出删行计划
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 上面全是 AST / 纯逻辑判据。**它们全绿也可能整条分流从未被执行过** —— 这正是上游
#    M28 变异（摘掉调用点仍 GREEN）的教训。本节走 K11 真实 substrate：
#    同一份 substrate + 同一份 projection，只翻契约里的 `row_convergence`，
#    断言两侧分别落到 `stale_cleared` 与 `stale_deleted`。


# ── 靶子选择：为什么是 D1-8 而不是 K11 ──────────────────────────────────────
#
# 🔴 K11（Task 18.1 字节基线那套）**不能**当删行靶子，两条都实测过：
#   ① `'审定表K11-1'` 的受管行被 sheet4/sheet5 各 3 处**跨 sheet 单格引用**指着
#      （`A19`/`G19`/`D19` × 2 张表 = 6 处）⇒ 门面按 Requirement 1.8 抛
#      `DanglingReferenceError`，受管区 7..25 每一行都被锁死；
#   ② K11 契约有静态格 `B27` 落在插入点之下 ⇒ 连 orphan 那一支都走不通
#      （`[contract_static_row_below_insertion]`）。
# 换 D1-8：现算受管区 14..21 **每一行都可删**（各 7 条传播声明）。
#
# 🔴 D1-8 的 8 个行身份**全是模板骨架**（`GTROW-D18DISCOUNT-00NN`），而 6.8b 的 stale
#    判据明确排除骨架行 ⇒ 直接从 projection 摘一行**产生不了 stale**。照 K11 基线同款办法
#    把其中一行的 UUID 格换成运行期 mint 前缀，它才算「用户真的删了这一行」。
STALE_ROW = 19
STALE_IDENTITY = "GTROW-MINTED-DISPATCH0001"


def _d1_payload_builder() -> Any:
    from app.services.workpaper_sync import phase5_d1_notes_receivable as D1

    return D1.build_contract_payload


def _d1_adapter_id() -> str:
    from app.services.workpaper_sync import phase5_d1_notes_receivable as D1

    return str(D1.ADAPTER_ID)


@pytest.fixture(scope="module")
def d18_world(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return _build_d18_world(tmp_path_factory.mktemp("dispatch-d18"))


def _build_d18_world(workdir: Path | None = None) -> dict[str, Any]:
    """D1-8 真实世界：真模板 → instrumentation → 一行换成非骨架身份 → extract。

    🔴 做成**普通函数**（fixture 只是它的薄壳）：Task 18.3 的字节级变异反证在另一个
    测试模块里要用同一个世界，而 module 级 fixture 跨文件拿不到 —— 那一课在本 spec 里
    已经踩过一次（`test_clear_path_byte_zero_regression.world`）。
    """
    import tempfile
    import zipfile

    from app.services.excel_structure_fingerprint import identity_inventory
    from app.services.workpaper_sync import excel_extract as X
    from app.services.workpaper_sync.adapters.base import SubstrateRole
    from app.services.workpaper_sync.models import ArtifactKind, ArtifactState

    import test_row_deletion_apply_propagation as AP
    import test_sibling_table_ref_row_shift as SIB
    from test_task37_excel_extract import make_definitions, patch_cells

    binding = AP.build_binding()
    base_bytes = SIB._instrumented_bytes_for_provider(AP.PROVIDER)
    with zipfile.ZipFile(__import__("io").BytesIO(base_bytes)) as zf:
        sheet_part = X._sheet_parts(zf).get(AP.SHEET)
    assert sheet_part, AP.SHEET
    substrate_bytes = patch_cells(
        base_bytes, sheet_part, {f"{binding.uuid_column}{STALE_ROW}": STALE_IDENTITY}
    )

    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="dispatch-d18-"))
    base = workdir / "base.xlsx"
    base.write_bytes(substrate_bytes)
    contract = AP.build_contract()
    inventory = identity_inventory(
        substrate_bytes,
        expected_table=binding.table_name,
        uuid_column_letter=binding.uuid_column,
    )
    outcome = X.extract_projection(
        artifact=base,
        definitions=make_definitions(contract, inventory),
        binding=binding,
        substrate_role=SubstrateRole.published_representation,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.published,
    )
    with zipfile.ZipFile(base) as zf:
        runtime_binding = X.read_runtime_binding_pairs(zf)
        entries = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    return {
        "base": base,
        "binding": binding,
        # 🔴 取 provider 的 payload 构造器而不是已解析的 contract：本节要**改一个键再重新
        #    解析**，改已解析的 frozen dataclass 拿不到 CS-21 的校验。
        "contract_payload_of": _d1_payload_builder(),
        "outcome": outcome,
        "runtime_binding": runtime_binding,
        "entries": entries,
    }


def _projection_missing_the_minted_row(outcome: Any) -> Any:
    """把 projection 里那个**非骨架**身份摘掉 ⇒ 它成为 stale。"""
    import dataclasses

    projection = outcome.projection
    row_keys = dict(projection.row_keys)
    table_key = next((k for k, rows in row_keys.items() if STALE_IDENTITY in rows), None)
    assert table_key is not None, (
        f"projection 里找不到非骨架身份 {STALE_IDENTITY}，实测 "
        f"{ {k: list(v)[:3] for k, v in row_keys.items()} }"
    )
    row_keys[table_key] = tuple(r for r in row_keys[table_key] if r != STALE_IDENTITY)
    values = {
        key: value
        for key, value in dict(getattr(projection, "values", {}) or {}).items()
        if f"/{STALE_IDENTITY}/" not in str(key)
    }
    replaced = dataclasses.replace(projection, row_keys=row_keys)
    if hasattr(replaced, "values"):
        replaced = dataclasses.replace(replaced, values=values)
    return replaced


def _plan_with_convergence(
    world: dict[str, Any], mode: str | None, *, projection: Any = None
) -> Any:
    """把 D1-8 契约的**本区**表改成指定 `row_convergence` 后重新解析并算计划。"""
    binding = world["binding"]
    payload = world["contract_payload_of"]()
    touched = 0
    for sheet in payload.get("sheets") or []:
        for table in sheet.get("tables") or []:
            if table.get("table_key") == binding.table_key:
                if mode is None:
                    table.pop("row_convergence", None)
                else:
                    table["row_convergence"] = mode
                touched += 1
    assert touched == 1, f"按 table_key={binding.table_key!r} 命中 {touched} 张表（应为 1）"

    contract = C.parse_contract(payload, adapter_id=_d1_adapter_id())
    if projection is None:
        projection = _projection_missing_the_minted_row(world["outcome"])
    return M.plan_managed_writes(
        projection=projection,
        contract=contract,
        binding=binding,
        region=world["outcome"].region,
        scan=world["outcome"].scan,
        substrate_entries=world["entries"],
        substrate_formulas=world["outcome"].formula_inventory,
        runtime_binding=world["runtime_binding"],
    )


class TestRealChainDispatchFlipsWithTheContract:
    """**Validates: Requirements 1.11, 8.4, 9.5**（真实链路，非 AST）"""

    def test_default_contract_clears(self, d18_world: dict[str, Any]) -> None:
        """🔴 对照组：不声明该键 ⇒ 走清空，且**两份删行声明都为空**。"""
        plan = _plan_with_convergence(d18_world, None)
        assert plan.stale_cleared, "对照组没产出 stale ⇒ 靶子失效，本节全部空转"
        assert plan.stale_deleted == ()
        assert plan.row_deletion is None
        assert plan.deletion_change is None
        assert plan.stale_clear_reason == "", (
            f"默认路径写了降级原因：{plan.stale_clear_reason!r}"
        )

    def test_declaring_delete_produces_a_real_deletion_plan(
        self, d18_world: dict[str, Any]
    ) -> None:
        """🔴 主判据：契约声明 `delete` ⇒ 同一份输入改走删行，**两份声明同时出现**。"""
        baseline = _plan_with_convergence(d18_world, None)
        plan = _plan_with_convergence(d18_world, "delete")

        assert plan.stale_deleted == baseline.stale_cleared, (
            f"被删行集合 {plan.stale_deleted} 与对照组的清空集合 "
            f"{baseline.stale_cleared} 不一致 ⇒ 两条分支认定的 stale 行不是同一批"
        )
        assert plan.stale_cleared == (), "同时走了清空 ⇒ 两分支互斥被破坏"
        assert plan.row_deletion is not None, "缺位移载体（Requirement 1.11）"
        assert plan.deletion_change is not None, "缺工作簿级传播声明（Requirement 1.11）"
        assert plan.row_deletion.deleted_rows == plan.stale_deleted
        assert plan.row_deletion.count == len(plan.stale_deleted)
        assert plan.stale_clear_reason == "", "走删行却写了降级原因"

    def test_deletion_plan_also_carries_total_rows_and_table_part(
        self, d18_world: dict[str, Any]
    ) -> None:
        """🔴 删行计划必须**同时**带上 `total_formula_rows` 与 `table_part`。

        D1-8 的 footer（22 行）携带合计公式且契约 `carries_total_formula=True` ⇒ 两者都应非空。
        不带的后果是两条 fail-closed（合计不收缩 / 本表 ref 不收缩），症状离真因很远。
        """
        plan = _plan_with_convergence(d18_world, "delete")
        assert plan.table_part, "删行计划没带 table_part ⇒ 本表 Table ref 无从收缩"
        assert plan.table_part.startswith("xl/tables/"), plan.table_part
        assert plan.total_formula_rows, (
            "删行计划没带 total_formula_rows ⇒ 合计区间不会收缩，"
            "A7 的上界判据会在写盘前拦成 FooterFormulaRangeError"
        )

    def test_trace_keys_are_row_identities(self, d18_world: dict[str, Any]) -> None:
        """🔴 留痕键是**行身份**（Requirement 1.9）：删完行号就变了，行号留不住痕。"""
        plan = _plan_with_convergence(d18_world, "delete")
        # `deleted_row_keys` 是**键的元组**（与被删行一一对应、按行号升序），不是字典
        keys = plan.deletion_change.deleted_row_keys
        assert tuple(keys) == (STALE_IDENTITY,), (
            f"留痕键不是那个非骨架身份 {STALE_IDENTITY!r}：{keys}"
        )
        assert len(keys) == len(plan.stale_deleted), (
            f"留痕键 {len(keys)} 个 ≠ 被删行 {len(plan.stale_deleted)} 行 —— "
            "一一对应被破坏（Property 6）"
        )
        # 🔴 反面：留痕键**不是**行号。行号删完就变了，拿它留痕等于留了个明天就对不上的东西。
        assert not any(str(k).isdigit() for k in keys), keys

    def test_declaring_clear_explicitly_matches_the_default(
        self, d18_world: dict[str, Any]
    ) -> None:
        """显式写 `clear` 与不写**逐字段一致** —— 默认值没有隐藏的第二套语义。"""
        implicit = _plan_with_convergence(d18_world, None)
        explicit = _plan_with_convergence(d18_world, "clear")
        assert explicit.as_dict() == implicit.as_dict()

    def test_coexistence_degrades_on_the_real_chain(
        self, d18_world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 真实链路上的共存降级：契约已开启 + 有 orphan ⇒ 仍走清空并写下原因。

        orphan 用「projection 多声明一个不存在的身份」造出来 —— 那正是生产里
        「OO 侧新增了行」的形态。
        """
        import dataclasses

        projection = _projection_missing_the_minted_row(d18_world["outcome"])
        table_key = d18_world["binding"].table_key
        row_keys = dict(projection.row_keys)
        row_keys[table_key] = (*row_keys[table_key], "GTROW-MINTED-COEXIST0001")
        projection = dataclasses.replace(projection, row_keys=row_keys)

        plan = _plan_with_convergence(d18_world, "delete", projection=projection)
        assert plan.row_shift is not None, "没造出 orphan ⇒ 本条判据空转"
        assert plan.stale_deleted == (), "共存下仍走了删行 ⇒ 降级没生效"
        assert plan.stale_cleared, "共存下既没删也没清 ⇒ stale 行被静默丢弃"
        assert plan.row_deletion is None and plan.deletion_change is None
        assert "delete_with_insert_coexist" in plan.stale_clear_reason, (
            f"降级原因缺 token：{plan.stale_clear_reason!r}"
        )
        assert plan.as_dict()["stale_clear_reason"] == plan.stale_clear_reason


class TestDegradationReasonHasAnExternalConsumer:
    """降级原因必须**被外部读到**，不只是写进一个没人看的字段。

    🔴 复盘现算：`stale_clear_reason` 全仓 6 处引用**全在 `excel_materialize` 自己**
    （字段定义 / `as_dict` / 三处赋值 / 一处传参）⇒ 生产零外部消费方。而这个字段的
    存在理由恰恰是「降级必须可观测」—— 只写进 dataclass 与不写没有区别，用户看到的是
    「行删不掉但没人说为什么」。

    这两条判据把「有外部消费方」变成会打红的事实：摘掉 `logger.warning` 立刻红。
    """

    def test_degradation_emits_a_warning_log(
        self, d18_world: dict[str, Any], caplog: pytest.LogCaptureFixture
    ) -> None:
        """走降级分支时必须发一条 WARNING，且带得上原因 token。"""
        import dataclasses
        import logging as _logging

        projection = _projection_missing_the_minted_row(d18_world["outcome"])
        table_key = d18_world["binding"].table_key
        row_keys = dict(projection.row_keys)
        row_keys[table_key] = (*row_keys[table_key], "GTROW-MINTED-COEXIST0001")
        projection = dataclasses.replace(projection, row_keys=row_keys)

        with caplog.at_level(
            _logging.WARNING, logger="app.services.workpaper_sync.excel_materialize"
        ):
            plan = _plan_with_convergence(d18_world, "delete", projection=projection)

        assert plan.stale_clear_reason, "没造出降级 ⇒ 本条判据空转"
        hits = [
            r
            for r in caplog.records
            if r.levelno >= _logging.WARNING
            and "delete_with_insert_coexist" in r.getMessage()
        ]
        assert hits, (
            "降级发生却没有任何 WARNING 日志 —— `stale_clear_reason` 回到了"
            "「只写进字段、零外部消费方」的状态；实际 WARNING："
            f"{[r.getMessage()[:80] for r in caplog.records]}"
        )
        message = hits[0].getMessage()
        assert table_key in message, f"日志没带 table_key，排查时无从定位：{message!r}"

    def test_no_log_when_there_is_no_degradation(
        self, d18_world: dict[str, Any], caplog: pytest.LogCaptureFixture
    ) -> None:
        """反向：没降级就不许发这条 WARNING（否则日志变噪声、没人再看）。"""
        import logging as _logging

        projection = _projection_missing_the_minted_row(d18_world["outcome"])
        with caplog.at_level(
            _logging.WARNING, logger="app.services.workpaper_sync.excel_materialize"
        ):
            plan = _plan_with_convergence(d18_world, "delete", projection=projection)

        assert plan.stale_deleted, "没走成删行 ⇒ 本条反向判据空转"
        assert plan.stale_clear_reason == ""
        noisy = [
            r for r in caplog.records if "受管行收敛降级" in r.getMessage()
        ]
        assert not noisy, f"未降级却发了降级告警：{[r.getMessage()[:80] for r in noisy]}"
