"""Task 6.1 / 6.2 判据（主体）—— 唯一计划路径 + 计划输入三态 + 旧的第二口径已删。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 1.2 / 1.4 / 3.1 / 4.1 / 4.2 · ADR-AOS-003（dry_run 与真实执行共用同一计划纯函数）

═══ 为什么是新建文件而不是追加 ═══

`adopt_substrate_response.py` 在本轮之前**没有任何专属测试文件**（现搜实证：
`backend/tests/**/*.py` 里 `adopt_substrate_response` / `_dry_run_summary` /
`compute_adopt_substrate` 三个符号命中 **0**；对 `adopt-substrate` 这个端点字面量的命中是
4 处 / 3 文件，经判注释后**可执行代码仅 1 处** —— `test_task28_sync_router.py` 的路由清单
字面量 `("POST", "/adopt-substrate")`）。⇒ 本文件是该模块的第一份行为判据。

═══ 为什么切成两份 ═══

交付时本文件 **1055** 行（`count_lines` 口径 = `splitlines()`）> `.py` 门禁 **800** ⇒ 按域内
先例（`test_aos_property_out_of_scope_rows.py` / `…_out_of_scope_mutants.py`）抽伴生件
**`test_aos_adopt_plan_gates_and_wire_form.py`**。切在 **§4 / §5 之间** —— 不是按行数对半砍，
两侧各是一个完整关注点：

- 本文件 = 「**计划是怎么来的**」：唯一计划路径（§1）+ 计划输入三件（§2 接线 / §3 scope 只取
  声明 / §4 三态）+ 旧的第二口径已删（§10）。🔴 §10 留在主体是因为它与 §1 是**同一关注点的
  正反两面** —— §1 证明新路径唯一，§10 证明旧的两处口径（`_dry_run_summary` /
  `_baseline_row_counts`）已删；两条分家就没人看得出「唯一口径」是怎么成立的。
- 伴生件 = 「**计划算出来之后**」：digest 校验门（§5）+ 载荷不可解析门（§6）+ 错误码契约（§7）
  + 对外 wire form（§8）+ 事务纪律与 6.3 / 6.4 棘轮（§9）。

🔴 **本文件同时是两份的共用工具箱**（源码级变异 `_source_mutant` / AST 取件 / 桩 reader /
桩 projection / 固定计划 `_fixed_plan` / `_ROUTER_PY`）：伴生件**只 import 不另造第二份** ——
判据工具一漂，两边就在测不同的东西。每组「判据函数 + 它的变异反证」都在同一文件内：
§1 的 `judge_shared_plan` 与 M1~M4 都在这里，§8 的 `judge_wire_form` 与它的两组变异都在那边。
拆分是**纯文件搬家**：一条断言没删没弱化，例数拆分前后逐字相等（证据见 tasks.md 6.2）。

═══ 判据面（逐节，每节都配变异反证）═══

| 节 | 判据 | Requirement | 落点 |
| --- | --- | --- | --- |
| §1 | dry_run 与真实执行**共用**唯一计划函数（AST：调用点 + 语句次序） | 3.1 | 本文件 |
| §2 | 3 条空 `declared_scopes` item 的接线（本任务的硬前提） | 3.1 / 3.2 | 本文件 |
| §3 | scope 覆盖只取**声明**，取不到就不猜 | 1.2 / 1.4 | 本文件 |
| §4 | `build_plan_inputs` 三态（reader / 跳过 / 未裁决） | 4.1 / 4.2 | 本文件 |
| §10 | 被取代的两个私有函数已删 + 指针注释 | —— | 本文件 |
| §5 | `plan_digest` 不符即拒（含 router 409 映射） | 3.4 | 伴生件 |
| §6 | 载荷不可解析 ⇒ 422 且**带 item_id** | 4.4 | 伴生件 |
| §7 | 三个新 `error_code` 与**既有三个**同风格 | 3.4 / 4.4 | 伴生件 |
| §8 | wire form 含 Requirement 3.2 要的全部字段 | 3.2 | 伴生件 |
| §9 | service 不 commit；6.3 / 6.4 未被提前实现（三条 xfail 棘轮） | —— | 伴生件 |

🔴 **变异一律进程内源码级**（`inspect.getsource` → 替换唯一锚点 → 在生产模块 `globals` 的
**副本**里 `exec`），生产文件一字不改。不用 `monkeypatch.setattr` —— 本域有并发会话，
即便自动还原，窗口期内也改了共用模块的行为（域内 4.4 / 4.6 / 4.7 同一处置）。

🔴 **三条 `xfail(strict=True)` 棘轮在伴生件 §9**，钉住的是 Task 6.3 / 6.4 的诉求
（删除侧应用 / `AdoptPlanVerificationError` → 500 / `changed_item_count` 取自 plan）。
它们现在必然失败 ⇒ xfail；那两个任务落地当天会 XPASS 而 strict 使其**打红**，逼迫把 xfail
摘掉并写真断言 —— 而不是让「本该如此」的诉求静默沉底。同时它们也是「本轮**没有**提前实现
6.3 / 6.4」的可执行证明：一旦偷跑，这三条会当场 XPASS-red。**跑主体时不要漏掉伴生件**，
否则那三条棘轮根本不参与判定。
"""

from __future__ import annotations

import ast
import copy
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, Mapping

import pytest

from app.services.workpaper_sync import adopt_substrate_response as ASR
from app.services.workpaper_sync.adopt_overwrite_compute import compute_overwrite_plan
from app.services.workpaper_sync.adopt_overwrite_plan import (
    ItemOverwriteDelta,
    OverwritePlan,
    OverwritePlanShapeError,
    SkipReason,
)
from app.services.workpaper_sync.adopt_row_reader import RowReaderResolution

_REPO = Path(__file__).resolve().parents[3]
_ROUTER_PY = _REPO / "backend" / "app" / "routers" / "wp_sync_router.py"

#: 本轮接线的三条 item（Task 4.2 `_scopes_of` docstring 交给 6.1 的清单）。
#: 🔴 `table_key` / 身份键**不写字面量**：测试期从门面定义模块的声明常量现读
#: （`ROWS_TABLE_KEY` / `ROW_IDENTITY_STORE_KEY`），与生产同源。
EMPTY_SCOPE_CASES: tuple[tuple[str, str, str], ...] = (
    ("d4.revenue_detail", "D4-2-rows", "app.services.workpaper_sync.phase5_d4_revenue_detail"),
    ("d2.receivable_detail", "D2-detail-rows", "app.services.workpaper_sync.pilot_d2_large_json"),
    ("h1.disposal_check", "H1-8-rows", "app.services.workpaper_sync.pilot_h1_grouped_dynamic"),
)


# ═══════════════════════════════════════════════════════════════════════════════
# 工具：源码级变异（进程内，生产文件一字不改）
# ═══════════════════════════════════════════════════════════════════════════════


def _source_mutant(func: Any, *, old: str, new: str, module: Any) -> Any:
    """按**唯一**锚点做源码级变异，返回独立函数对象（不回写 module）。"""
    src = inspect.getsource(func)
    hits = src.count(old)
    assert hits == 1, (
        f"锚点 {old!r} 在 {func.__name__} 源码里命中 {hits} 次（须恰 1）—— "
        "命中 0 次时 `str.replace` 静默变成空操作，变异体等于生产实现，红一次都打不出还全绿"
    )
    namespace = dict(vars(module))
    exec(compile(src.replace(old, new), f"<mutant:{func.__name__}>", "exec"), namespace)
    mutant = namespace[func.__name__]
    assert mutant is not func, "变异体与生产函数是同一个对象"
    assert mutant.__globals__ is not vars(module), "变异体的 globals 就是生产模块的 globals"
    return mutant


def _module_ast() -> ast.Module:
    return ast.parse(inspect.getsource(ASR))


def _func_ast(name: str) -> Any:
    for node in ast.walk(_module_ast()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 在 {ASR.__name__} 里不存在")


def _callee_name(call: ast.Call) -> str:
    target = call.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def _stmt_index(body: list[Any], predicate: Any) -> int:
    for ordinal, stmt in enumerate(body):
        if predicate(stmt):
            return ordinal
    return -1


def _calls_named(node: ast.AST, name: str) -> list[ast.Call]:
    return [
        n for n in ast.walk(node) if isinstance(n, ast.Call) and _callee_name(n) == name
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# 工具：桩 reader / 桩 projection
# ═══════════════════════════════════════════════════════════════════════════════

_IDENTITY_KEY = "rowId"


class _StubReader:
    """最薄的 `RowReader` 实现 —— 只为 §3/§4/§6 造输入，不代表任何 provider。"""

    def __init__(
        self,
        *,
        item_id: str,
        section_field: str = "",
        declared_scopes: tuple[tuple[str, str | None], ...] = (),
        raises: BaseException | None = None,
    ) -> None:
        self.item_id = item_id
        self.section_field = section_field
        self.declared_scopes = declared_scopes
        self._raises = raises

    def iter_rows(self, payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
        if self._raises is not None:
            raise self._raises
        for row in json.loads(payload) if isinstance(payload, str) else payload:
            yield str(row[_IDENTITY_KEY]), row

    def section_of(self, row: Mapping[str, Any]) -> str | None:
        if not self.section_field:
            return None
        return str(row.get(self.section_field) or "") or None


def _projection(**row_keys: tuple[str, ...]) -> Any:
    return SimpleNamespace(row_keys=dict(row_keys))


def _fixed_plan() -> OverwritePlan:
    """一份固定计划（§5 / §8 用）。内容不重要，只要 digest 稳定、清单非空。"""
    return OverwritePlan(
        deltas=(
            ItemOverwriteDelta(
                item_id="AOS61-item",
                table_key="aos61_rows",
                rows_added=("aos61-a1",),
                rows_deleted=("aos61-d1", "aos61-d2"),
                rows_updated=("aos61-u1",),
            ),
            ItemOverwriteDelta(
                item_id="AOS61-blind", table_key=None, skipped_reason=SkipReason.item_blind
            ),
        ),
        store_rows_by_table={"aos61_rows": 3},
        substrate_rows_by_table={"aos61_rows": 2},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# §1 dry_run 与真实执行**共用**唯一计划函数（Requirement 3.1 / ADR-AOS-003）
# ═══════════════════════════════════════════════════════════════════════════════

#: 门面名（唯一允许算计划的入口）与被它转发的纯函数名。
_PLAN_FACADE = "compute_plan_for_adopt"
_PLAN_PURE = "compute_overwrite_plan"
_WIRE_FORM = "_plan_wire_form"


def judge_shared_plan(fn: Any) -> list[str]:
    """四条子判据，返回违规清单（空 = 合规）。**纯函数**，故 §1 的变异可直接喂 AST。

    🔴 子判据 3 用的是 `fn.body` 里的**下标**而不是 `lineno` —— 变异反证要靠交换两条语句
    来证明它有牙，而交换后 lineno 不变（lineno 绑在节点上），只有下标会动。
    """
    violations: list[str] = []
    facade_calls = _calls_named(fn, _PLAN_FACADE)
    if len(facade_calls) != 1:
        violations.append(f"{_PLAN_FACADE} 调用点 {len(facade_calls)} 处（须恰 1）")
    direct = _calls_named(fn, _PLAN_PURE)
    if direct:
        violations.append(
            f"{fn.name} 直接调了 {_PLAN_PURE} {len(direct)} 处 —— 必须经唯一门面"
        )
    plan_at = _stmt_index(fn.body, lambda s: bool(_calls_named(s, _PLAN_FACADE)))
    dry_at = _stmt_index(
        fn.body,
        lambda s: isinstance(s, ast.If)
        and isinstance(s.test, ast.Name)
        and s.test.id == "dry_run",
    )
    if plan_at < 0 or dry_at < 0:
        violations.append(f"定位失败：plan 语句下标 {plan_at} / dry_run 分支下标 {dry_at}")
    elif plan_at > dry_at:
        violations.append(
            f"plan 在 dry_run 分支**之后**才算（{plan_at} > {dry_at}）—— "
            "dry_run 就必然走了第二套算法"
        )
    if dry_at >= 0 and not _calls_named(fn.body[dry_at], _WIRE_FORM):
        violations.append(f"dry_run 分支的返回值里没有 {_WIRE_FORM} —— 它在自己拼摘要")
    return violations


class TestSharedPlanFunction:
    def test_production_satisfies_every_clause(self) -> None:
        """生产实现下四条子判据全部成立（对照组）。"""
        assert judge_shared_plan(_func_ast("compute_adopt_substrate")) == []

    def test_facade_forwards_the_one_pure_function(self) -> None:
        """门面自己**恰调一次**那个纯函数 —— 「只有一处算法」的落点。"""
        facade = _func_ast(_PLAN_FACADE)
        assert len(_calls_named(facade, _PLAN_PURE)) == 1, (
            f"{_PLAN_FACADE} 对 {_PLAN_PURE} 的调用点不是恰 1 处 —— "
            "门面存在的全部意义就是把「算计划」收敛成一处"
        )
        assert ASR.compute_overwrite_plan is compute_overwrite_plan, (
            "生产模块里的 compute_overwrite_plan 不是 adopt_overwrite_compute 那一个 —— "
            "同名不同源就是第二真源"
        )

    def test_mutant_dry_run_builds_its_own_summary_is_caught(self) -> None:
        """变异 M1：dry_run 分支不走 wire form ⇒ 子判据 4 打红（其余三条仍绿）。"""
        fn = copy.deepcopy(_func_ast("compute_adopt_substrate"))
        dry_at = _stmt_index(
            fn.body,
            lambda s: isinstance(s, ast.If)
            and isinstance(s.test, ast.Name)
            and s.test.id == "dry_run",
        )
        fn.body[dry_at] = ast.parse(
            "if dry_run:\n"
            "    return {'substrate_row_count': sum(\n"
            "        len(v or ()) for v in (getattr(baseline, 'row_keys', None) or {}).values()\n"
            "    )}\n"
        ).body[0]
        got = judge_shared_plan(fn)
        assert len(got) == 1 and _WIRE_FORM in got[0], (
            f"M1 期望只打红「dry_run 自己拼摘要」这一条，实得 {got}"
        )

    def test_mutant_second_call_site_is_caught(self) -> None:
        """变异 M2：多一个计划调用点 ⇒ 子判据 1 打红（两处算法的最常见形态）。"""
        fn = copy.deepcopy(_func_ast("compute_adopt_substrate"))
        plan_at = _stmt_index(fn.body, lambda s: bool(_calls_named(s, _PLAN_FACADE)))
        fn.body.insert(plan_at, copy.deepcopy(fn.body[plan_at]))
        got = judge_shared_plan(fn)
        assert len(got) == 1 and "调用点 2 处" in got[0], f"M2 实得 {got}"

    def test_mutant_direct_pure_call_is_caught(self) -> None:
        """变异 M3：绕过门面直接调纯函数 ⇒ 子判据 2 打红。"""
        fn = copy.deepcopy(_func_ast("compute_adopt_substrate"))
        plan_at = _stmt_index(fn.body, lambda s: bool(_calls_named(s, _PLAN_FACADE)))
        fn.body.insert(
            plan_at + 1, ast.parse(f"shadow = {_PLAN_PURE}(substrate_projection=baseline)").body[0]
        )
        got = judge_shared_plan(fn)
        assert len(got) == 1 and _PLAN_PURE in got[0], f"M3 实得 {got}"

    def test_mutant_plan_after_dry_run_branch_is_caught(self) -> None:
        """变异 M4：把 plan 语句挪到 dry_run 分支**之后** ⇒ 子判据 3 打红。

        🔴 这一组是「共用」这件事的**真正**要害：前三组变异都还留着一个 plan 调用点，
        只有本组模拟「dry_run 先返回、plan 只服务真实执行」—— 那正是改动前的形态。
        """
        fn = copy.deepcopy(_func_ast("compute_adopt_substrate"))
        plan_at = _stmt_index(fn.body, lambda s: bool(_calls_named(s, _PLAN_FACADE)))
        dry_at = _stmt_index(
            fn.body,
            lambda s: isinstance(s, ast.If)
            and isinstance(s.test, ast.Name)
            and s.test.id == "dry_run",
        )
        assert plan_at < dry_at, "前提：生产实现里 plan 在 dry_run 之前"
        fn.body[plan_at], fn.body[dry_at] = fn.body[dry_at], fn.body[plan_at]
        got = judge_shared_plan(fn)
        assert any("之后" in v for v in got), f"M4 实得 {got}"


# ═══════════════════════════════════════════════════════════════════════════════
# §2 三条空 `declared_scopes` item 的接线（Task 6.1 的硬前提）
#
# 🔴 Task 4.2 `_scopes_of` docstring 把这三条明写成「这条不做完，adopt 对 D4/D2/H1 会当场
#    fail visible」。本节先**现算复核**它们仍然为空，再实测接线后能真算出计划，最后用
#    「不接线」这一变体证明判据有牙。
# ═══════════════════════════════════════════════════════════════════════════════


def _declared_pair(module_path: str) -> tuple[str, str]:
    """门面定义模块的两个声明常量：行表 table_key 与行身份键。**现读，不写字面量。**"""
    owner = importlib.import_module(module_path)
    return str(owner.ROWS_TABLE_KEY), str(owner.ROW_IDENTITY_STORE_KEY)


def _payload_of(identity_key: str, *identities: str) -> str:
    return json.dumps([{identity_key: i} for i in identities], ensure_ascii=False)


class TestEmptyDeclaredScopesAreWired:
    @pytest.mark.parametrize(("adapter_id", "item_id", "module_path"), EMPTY_SCOPE_CASES)
    def test_scope_comes_from_the_declaration_constant(
        self, adapter_id: str, item_id: str, module_path: str
    ) -> None:
        """现算复核 + 接线：reader 的 `declared_scopes` 仍为空，而 `item_scopes` 由声明补上。"""
        table_key, _identity_key = _declared_pair(module_path)
        inputs = ASR.census_plan_inputs(SimpleNamespace(adapter_id=adapter_id))
        assert item_id in inputs.item_ids, f"{item_id} 不在本 adapter 的 item 分母里"
        reader = inputs.row_readers.get(item_id)
        assert reader is not None, f"{item_id} 现算已取不到 reader —— 前提变了，先查 Task 3.7"
        assert tuple(getattr(reader, "declared_scopes", ()) or ()) == (), (
            f"{item_id} 的 reader 现算已自带 declared_scopes —— 那本任务的接线就是多余的，"
            "应当改为不覆盖并在 tasks.md 更正现算结论"
        )
        assert inputs.item_scopes.get(item_id) == ((table_key, None),), (
            f"{item_id} 没有从门面定义模块的 ROWS_TABLE_KEY 拿到 scope 声明"
        )

    @pytest.mark.parametrize(("adapter_id", "item_id", "module_path"), EMPTY_SCOPE_CASES)
    def test_plan_is_computable_after_wiring(
        self, adapter_id: str, item_id: str, module_path: str
    ) -> None:
        """接线后三条 item **不再** fail visible，且三清单逐值正确。"""
        table_key, identity_key = _declared_pair(module_path)
        inputs = ASR.census_plan_inputs(SimpleNamespace(adapter_id=adapter_id))
        payload = _payload_of(identity_key, "aos61-keep", "aos61-gone")
        store_payloads = {i: (payload if i == item_id else None) for i in inputs.item_ids}
        baseline = _projection(**{table_key: ("aos61-keep", "aos61-new")})

        plan = ASR.compute_plan_for_adopt(
            baseline=baseline, store_payloads=store_payloads, plan_inputs=inputs
        )
        mine = [d for d in plan.deltas if d.item_id == item_id and d.table_key == table_key]
        assert len(mine) == 1, f"{item_id} 期望恰 1 条 delta，实得 {len(mine)}"
        delta = mine[0]
        assert delta.rows_added == ("aos61-new",)
        assert delta.rows_deleted == ("aos61-gone",)
        assert delta.rows_updated == ("aos61-keep",)
        assert delta.row_section is None
        assert plan.store_rows_by_table[table_key] == 2
        assert plan.substrate_rows_by_table[table_key] == 2

    @pytest.mark.parametrize(("adapter_id", "item_id", "module_path"), EMPTY_SCOPE_CASES)
    def test_without_the_wiring_it_fails_visible(
        self, adapter_id: str, item_id: str, module_path: str
    ) -> None:
        """变异反证：把 `item_scopes` 抽掉 ⇒ 当场抛（证明接线就是解掉 fail visible 的那一步）。"""
        table_key, identity_key = _declared_pair(module_path)
        inputs = ASR.census_plan_inputs(SimpleNamespace(adapter_id=adapter_id))
        payload = _payload_of(identity_key, "aos61-keep")
        store_payloads = {i: (payload if i == item_id else None) for i in inputs.item_ids}
        with pytest.raises(OverwritePlanShapeError, match="declared_scopes"):
            compute_overwrite_plan(
                substrate_projection=_projection(**{table_key: ("aos61-keep",)}),
                store_payloads=store_payloads,
                row_readers=inputs.row_readers,
                skip_reasons=inputs.skip_reasons,
                item_scopes={},
            )

    @pytest.mark.parametrize(("adapter_id", "item_id", "module_path"), EMPTY_SCOPE_CASES)
    def test_the_constant_is_the_one_the_projection_itself_uses(
        self, adapter_id: str, item_id: str, module_path: str
    ) -> None:
        """🔴 取的是**声明**不是键名兜底：provider 自己 `build_store_projection` 用的就是它。

        判据形态 = 源码里存在 `row_keys={ROWS_TABLE_KEY` 这一写法（常量名，不是它的值）。
        不这么核的话，「从模块上随便读了个叫 ROWS_TABLE_KEY 的常量」与「读到 projection 真用的
        那一个」在下游不可区分 —— 前者一旦与 projection 用的表名不同，作用域门会整表不命中
        而**静默零删除**。
        """
        src = inspect.getsource(importlib.import_module(module_path))
        assert "row_keys={ROWS_TABLE_KEY" in src, (
            f"{module_path} 的 build_store_projection 不再用 ROWS_TABLE_KEY 作 row_keys 的键 —— "
            "接线取的声明与 projection 用的表名已脱钩，必须重新裁定 scope 来源"
        )
        assert f'ROWS_TABLE_KEY: Final[str] = "{_declared_pair(module_path)[0]}"' in src, (
            f"{module_path} 的 ROWS_TABLE_KEY 不是模块级 Final 声明 —— 现读到的值可能来自别处"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# §3 scope 覆盖只取**声明**，取不到就不猜（Requirement 1.2 / 1.4）
# ═══════════════════════════════════════════════════════════════════════════════


#: 一个**确实**带 `ROWS_TABLE_KEY` 的真实模块（用于证明「返回空」不是因为读不到模块）。
_ROWS_KEY_STUB = EMPTY_SCOPE_CASES[2][2]


def _resolution(
    *, item_id: str = "AOS61-item", reader: Any = None, facade_module: str = "", **kw: Any
) -> RowReaderResolution:
    return RowReaderResolution(
        item_id=item_id, reader=reader, facade_module=facade_module, **kw
    )


class TestScopeOverrideOnlyFromDeclaration:
    def test_non_empty_declared_scopes_is_never_overridden(self) -> None:
        """reader 自带 scope ⇒ 不覆盖（它才是第一真源）。"""
        scopes = (("aos61_rows", None),)
        reader = _StubReader(item_id="AOS61-item", declared_scopes=scopes)
        got = ASR._scope_override_from_declaration(
            _resolution(reader=reader, declared_scopes=scopes, facade_module=__name__)
        )
        assert got == (), "reader 已有声明却仍被覆盖 —— 覆盖只该补空缺"

    def test_section_field_present_but_no_scope_refuses_to_guess(self) -> None:
        """🔴 有分区维度却拿不到 scope ⇒ 返回空（交给 compute 当场抛），**不猜 `None` 分区**。

        危害具体：硬塞 `(table_key, None)` 不会触发 `_in_scope_by_section` 的任何一条门
        （它只拦「无 section_field 却给了分区」这一向），于是真实分区的行永远匹配不上
        `None` 桶 ⇒ **静默少删**。本用例把那条静默失败钉死成 fail visible。
        """
        reader = _StubReader(item_id="AOS61-item", section_field="acctClass")
        assert (
            ASR._scope_override_from_declaration(
                _resolution(reader=reader, facade_module=_ROWS_KEY_STUB)
            )
            == ()
        )

    def test_missing_constant_yields_no_override(self) -> None:
        """门面定义模块上没有那个声明常量 ⇒ 不造 scope（同样交给 compute fail visible）。"""
        reader = _StubReader(item_id="AOS61-item")
        assert (
            ASR._scope_override_from_declaration(
                _resolution(reader=reader, facade_module="app.services.workpaper_sync.models")
            )
            == ()
        )
        # 变异对照：换成**有**该常量的模块 ⇒ 同一段代码必须命中（否则它什么都没在读）
        assert ASR._scope_override_from_declaration(
            _resolution(reader=reader, facade_module=EMPTY_SCOPE_CASES[0][2])
        ) == ((_declared_pair(EMPTY_SCOPE_CASES[0][2])[0], None),)

    def test_unknown_facade_module_yields_no_override(self) -> None:
        """`facade_module` 为空或不在 `sys.modules` ⇒ 不造 scope，且不抛。"""
        reader = _StubReader(item_id="AOS61-item")
        for module_name in ("", "app.services.workpaper_sync._aos61_absent_module"):
            assert (
                ASR._scope_override_from_declaration(
                    _resolution(reader=reader, facade_module=module_name)
                )
                == ()
            )


# ═══════════════════════════════════════════════════════════════════════════════
# §4 `build_plan_inputs` 三态（Requirement 4.1 / 4.2）
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildPlanInputsTriState:
    def test_enumerable_goes_to_readers(self) -> None:
        reader = _StubReader(item_id="A", declared_scopes=(("t", None),))
        got = ASR.build_plan_inputs(
            {"A": _resolution(item_id="A", reader=reader, declared_scopes=(("t", None),))},
            adapter_key="aos61.adapter",
        )
        assert got.row_readers == {"A": reader}
        assert got.skip_reasons == {}
        assert got.item_ids == ("A",)

    def test_skipped_goes_to_reasons(self) -> None:
        got = ASR.build_plan_inputs(
            {"B": _resolution(item_id="B", skip_reason=SkipReason.item_blind, detail="x")},
            adapter_key="aos61.adapter",
        )
        assert got.skip_reasons == {"B": SkipReason.item_blind}
        assert got.row_readers == {}

    def test_unruled_shape_is_registered_nowhere_and_fails_visible(self) -> None:
        """🔴 未裁决形态两边都不登记 ⇒ `compute_overwrite_plan` 当场抛。

        它**不是**「无行」（`RowReaderResolution.is_unruled_shape` docstring 逐字写明），
        硬塞任一 `SkipReason` 成员就是 Requirement 4.3 的「白名单失效条目」。
        """
        unruled = _resolution(item_id="C", detail="门面覆盖面不全（合成）")
        assert unruled.is_unruled_shape is True
        got = ASR.build_plan_inputs({"C": unruled}, adapter_key="aos61.adapter")
        assert "C" not in got.row_readers and "C" not in got.skip_reasons
        assert got.item_ids == ("C",), "未裁决形态仍须留在 item 分母里（否则它彻底消失）"
        with pytest.raises(OverwritePlanShapeError, match="既无 reader 也无跳过原因"):
            compute_overwrite_plan(
                substrate_projection=_projection(),
                store_payloads={"C": None},
                row_readers=got.row_readers,
                skip_reasons=got.skip_reasons,
                item_scopes=got.item_scopes,
            )

    @pytest.mark.parametrize("reason", [SkipReason.no_store_item, SkipReason.import_failed])
    def test_adapter_level_reason_is_keyed_by_adapter_id(self, reason: SkipReason) -> None:
        """adapter 级原因（没有 item_id 可填）第一位放 adapter_id。"""
        got = ASR.build_plan_inputs({}, adapter_key="aos61.adapter", adapter_reason=reason)
        assert got.skip_reasons == {"aos61.adapter": reason}
        assert got.item_ids == ()

    def test_census_reports_adapter_level_no_store_item(self) -> None:
        """现算实测：`a51.cashflow_audit` 是 `no_store_item` 的真实分母之一。"""
        got = ASR.census_plan_inputs(SimpleNamespace(adapter_id="a51.cashflow_audit"))
        assert got.item_ids == ()
        assert got.skip_reasons == {"a51.cashflow_audit": SkipReason.no_store_item}

    def test_census_reports_import_failed_for_unknown_adapter(self) -> None:
        """provider 解析失败 ⇒ `import_failed`（判定链 L1 只在本层可观测）。"""
        got = ASR.census_plan_inputs(SimpleNamespace(adapter_id="aos61/not-a-real-adapter"))
        assert got.skip_reasons == {
            "aos61/not-a-real-adapter": SkipReason.import_failed
        }


# ═══════════════════════════════════════════════════════════════════════════════
# §10 被取代的两个私有函数（Task 6.1 的字面要求）+ 指针注释
# ═══════════════════════════════════════════════════════════════════════════════


class TestReplacedHelpersAreGoneWithAPointer:
    @pytest.mark.parametrize("name", ["_dry_run_summary", "_baseline_row_counts"])
    def test_helper_is_removed(self, name: str) -> None:
        assert not hasattr(ASR, name), (
            f"{name} 还在 —— 它与计划侧是两处口径（原始 len vs 去重身份数），"
            "并存必有一天不等"
        )

    @pytest.mark.parametrize("name", ["_dry_run_summary", "_baseline_row_counts"])
    def test_module_docstring_points_at_the_replacement(self, name: str) -> None:
        """🔴 别的模块的 docstring 仍在引用这两个名字 ⇒ 本模块必须留可导航的落点。"""
        doc = ASR.__doc__ or ""
        assert name in doc, f"模块 docstring 里没有 {name} 的指针注释"

    def test_the_stale_references_elsewhere_are_registered(self) -> None:
        """现算实证那些历史引用**真的存在**（否则上一条的指针注释是在解释一个不存在的问题）。"""
        from app.services.workpaper_sync import adopt_overwrite_compute, adopt_overwrite_plan

        assert "_baseline_row_counts" in inspect.getsource(adopt_overwrite_compute)
        assert "_dry_run_summary" in inspect.getsource(adopt_overwrite_plan)


# ═══════════════════════════════════════════════════════════════════════════════
# 指针：另一半在哪
# ═══════════════════════════════════════════════════════════════════════════════
#
# §5~§9 在伴生件 **`test_aos_adopt_plan_gates_and_wire_form.py`**（切在 §4 / §5 之间，
# 理由见本文件模块 docstring「为什么切成两份」）。它承的判据：
#   §5 `plan_digest` 不符即拒（含 router 409 映射 + 校验点必在任何写之前）
#   §6 载荷不可解析 ⇒ 422 且带 item_id；`OverwritePlanShapeError` 原样穿透
#   §7 三个新 `error_code` 与既有三个同风格（`LEGACY_ERROR_CODES` / `NEW_ERROR_CODES`
#      两张基准表随 §7 一起搬过去了 —— 只有 §7 用它们）
#   §8 wire form 字段完备（`judge_wire_form` 与它的两组变异反证同在那边）
#   §9 service 不 commit + **三条 `xfail(strict=True)` 棘轮**（Task 6.3 / 6.4）
#
# 🔴 伴生件从本文件 import 工具与桩（`_source_mutant` / `_module_ast` / `_func_ast` /
#    `_callee_name` / `_stmt_index` / `_calls_named` / `_StubReader` / `_projection` /
#    `_fixed_plan` / `_IDENTITY_KEY` / `_ROUTER_PY`），本文件是它们的**唯一**来源
#    ⇒ 改这些工具的签名或行为前先看那边的调用点。
# 🔴 `_ROUTER_PY` / `_source_mutant` / `_fixed_plan` 拆分后只被伴生件用到 —— 留在本文件是
#    刻意的（工具箱单一来源），**不要因为「本文件没用到」就删**，删了那边当场 ImportError。
# 🔴 只跑本文件会漏掉 §9 那三条棘轮 ⇒ 定向回归清单必须两份都在。
