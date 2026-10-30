"""attach 接线完整性：多受管表 entry 必须补兄弟 binding；attach 必须经本模块 digest 比对取观测结果。

spec: writeback-followup-issue-closure · R12（B 组）

背景（真库实测 2026-10-24，`ExcelSyncAdapter._all_bindings()` 是 materialize / extract 唯一遍历面）：
F3 / F4 / F5 / F2 盘点 / K1 已注册但只挂主 binding ⇒ 两个方向静默退化成单表。F3 在当前已发布
artifact 上只挂主 binding 反读 0 个受管字段，补上兄弟 binding 后 59 个；生产提交的三道门两种情况
**都是绿的**（门只管「没管的地方没被动」，不管「该管的有没有管到」）。F2 盘点 / 计价 / 专项的 attach
直调观测器，本模块那份 contract digest 比对从未被生产调用。

判据：
1. 台账 xlsx entry 的契约有 ≥2 张行身份表 ⇒ attach 必须补兄弟 binding（def 形态：`build_excel_adapter`
   带非空 `sibling_bindings`；骨架委托：传 `provider_name=__name__`；工厂：`cfg.instrumentation_specs_fn`）。
   已知缺口逐条登记**可伪证**的原因（反向断言「原因仍成立」，修好即红、逼着删条目）。
2. 接上了的：离线跑生产同一对齐内核，主 binding + 兄弟 binding 恰好覆盖契约全部行身份表。
3. def 形态 attach（含骨架一跳）构造 adapter 时必须 await 本模块 `resolve_published_frozen_definitions`，
   不得直调观测器。
"""
from __future__ import annotations

import ast
import importlib
import inspect
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.workpaper_sync import projection_first_publication as PFP
from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
    DELIVERED_PER_ENTRY_CONTRACTS,
)
from app.services.workpaper_sync.contracts import load_contract
from tests.workpaper_sync.provider_attach_identity import (
    closure_cell,
    import_aliases,
    is_factory_closure,
)

SVC = Path(__file__).resolve().parents[2] / "app" / "services" / "workpaper_sync"
#: 白名单骨架 → 它的 attach 函数名（委托目标按委托方文件的 import 现解析，不按别名字面）。
_SKELETON_ATTACH: dict[str, str] = {
    "phase5_h_cycle_common": "attach_h_entry_adapter",
    "phase5_l_cycle_common": "attach_l_entry_adapter",
}
_ADAPTER_BUILDERS = frozenset({"build_excel_adapter", "ExcelSyncAdapter"})
_OBSERVER = "observe_published_frozen_definitions"
_RESOLVE = "resolve_published_frozen_definitions"


# ════════════════════════════════════════════════════════════════════════════
# AST 判据（纯函数，下方有可伪证性自检）
# ════════════════════════════════════════════════════════════════════════════


def _call_name(call: ast.Call) -> str:
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def builder_calls(node: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Call) and _call_name(n) in _ADAPTER_BUILDERS]


def supplies_siblings(call: ast.Call) -> bool:
    """`sibling_bindings=` 存在且不是空元组 / None 字面量。"""
    kw = next((k for k in call.keywords if k.arg == "sibling_bindings"), None)
    if kw is None:
        return False
    value = kw.value
    if isinstance(value, ast.Tuple) and not value.elts:
        return False
    return not (isinstance(value, ast.Constant) and value.value is None)


def awaited_names(node: ast.AST) -> set[str]:
    return {
        _call_name(n.value)
        for n in ast.walk(node)
        if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
    }


def passes_own_name(call: ast.Call, keyword: str) -> bool:
    """委托调用把 `keyword=__name__` 原样传下去（传别的模块名 = 用别人的 specs）。"""
    return any(
        k.arg == keyword and isinstance(k.value, ast.Name) and k.value.id == "__name__"
        for k in call.keywords
    )


def top_function(path: Path, name: str) -> ast.AST | None:
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def skeleton_hop(node: ast.AST, provider_path: Path) -> tuple[Path, ast.AST, ast.Call] | None:
    """attach 体内 `await <骨架别名>.<骨架 attach>(…)` ⇒ (骨架文件, 骨架函数节点, 委托调用)。"""
    aliases = import_aliases(provider_path)
    for n in ast.walk(node):
        if not (isinstance(n, ast.Await) and isinstance(n.value, ast.Call)):
            continue
        func = n.value.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module = aliases.get(func.value.id)
            if module in _SKELETON_ATTACH and func.attr == _SKELETON_ATTACH[module]:
                path = SVC / f"{module}.py"
                inner = top_function(path, func.attr)
                assert inner is not None, f"{path.name} 里找不到 {func.attr}"
                return path, inner, n.value
    return None


@dataclass(frozen=True)
class Wiring:
    form: str  # factory / def / skeleton / no_adapter
    supplies_siblings: bool
    awaited: frozenset[str]  # def / skeleton 形态：attach 链上被 await 的调用名
    where: str


def attach_wiring(module: Any) -> Wiring:
    attach = getattr(module, "attach_pilot_adapters", None)
    assert callable(attach), f"{module.__name__} 没有 attach_pilot_adapters"
    if is_factory_closure(attach, "attach_adapters"):
        cfg = closure_cell(attach, "cfg")
        return Wiring("factory", cfg.instrumentation_specs_fn is not None, frozenset(), "build_orchestration")
    assert attach.__module__ == module.__name__, (
        f"{module.__name__}: attach 来自 {attach.__module__} ⇒ 认不出的形态，判据不放行"
    )
    path = Path(inspect.getsourcefile(module) or "")
    node = top_function(path, attach.__name__)
    assert node is not None, f"{path.name}: 找不到 attach 的 def {attach.__name__}"
    where = f"{path.name}::{attach.__name__}"
    calls = builder_calls(node)
    if calls:
        return Wiring("def", all(supplies_siblings(c) for c in calls), frozenset(awaited_names(node)), where)
    hop = skeleton_hop(node, path)
    if hop is None:
        return Wiring("no_adapter", False, frozenset(awaited_names(node)), where)
    skel_path, inner, call = hop
    inner_calls = builder_calls(inner)
    assert inner_calls, f"{skel_path.name}::{_call_name(call)} 不构造 adapter ⇒ 认不出的形态"
    wired = all(supplies_siblings(c) for c in inner_calls) and passes_own_name(call, "provider_name")
    awaited = frozenset(awaited_names(node) | awaited_names(inner))
    return Wiring("skeleton", wired, awaited, f"{where} → {skel_path.name}::{_call_name(call)}")


# ════════════════════════════════════════════════════════════════════════════
# 分母：台账 xlsx 行（逐行现算，不写死数）
# ════════════════════════════════════════════════════════════════════════════

_XLSX_ROWS: tuple[Any, ...] = tuple(
    r for r in DELIVERED_PER_ENTRY_CONTRACTS if str(r.get("document_type")) == "xlsx"
)


def _row_tables(contract: Any) -> set[str]:
    """要靠 binding 覆盖的行身份表。转置 sheet（D4-29 / D4-12 …）由 adapter 按契约 sheet_key
    走 `resolve_transposed_specs` 分派，不经 binding ⇒ 不计入（与 `adapters/excel.py` 同一个真源）。"""
    from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs

    transposed = {spec.sheet_key for spec in resolve_transposed_specs(contract)}
    return {
        str(t.table_key)
        for s in contract.sheets
        if s.sheet_key not in transposed
        for t in s.tables
        if t.row_identity is not None
    }


@dataclass(frozen=True)
class _Case:
    module: Any
    contract: Any
    row_tables: frozenset[str]
    wiring: Wiring


def _load_case(row: Any) -> _Case:
    module = importlib.import_module(str(row["provider_module"]))
    contract = load_contract(str(row["contract_id"]))
    return _Case(module, contract, frozenset(_row_tables(contract)), attach_wiring(module))


_CASES: dict[str, _Case] = {str(r["contract_id"]): _load_case(r) for r in _XLSX_ROWS}
_MULTI: tuple[str, ...] = tuple(cid for cid, c in _CASES.items() if len(c.row_tables) >= 2)


# ════════════════════════════════════════════════════════════════════════════
# 已知缺口：每条带「原因仍成立」的可伪证判据（修好即红 ⇒ 逼着接线并删条目）
# ════════════════════════════════════════════════════════════════════════════


def _factory_instrumentation_still_singular(case: _Case) -> str | None:
    """D3/D5/D6/D7：模块级 instrumentation 仍是工厂单数那份、模块没有复数 specs。"""
    attach = case.module.attach_pilot_adapters
    cfg = closure_cell(attach, "cfg")
    if cfg.instrumentation_definition_payload_fn is not None or cfg.instrumentation_specs_fn is not None:
        return "cfg 已注入复数 instrumentation / specs"
    published = getattr(case.module, "instrumentation_definition_payload", None)
    if not is_factory_closure(published, "instrumentation_definition_payload"):
        return "模块级 instrumentation_definition_payload 已不是工厂单数那份"
    if callable(getattr(case.module, "instrumentation_specs", None)):
        return "模块已导出复数 instrumentation_specs（扩展 specs 不含基表的问题可能已解）"
    return None


#: attach 根本不构造 adapter 的 entry（与行表数无关，单列）→ 原因。
_NO_ADAPTER: dict[str, str] = {
    "e1.monetary_fund_detail": "attach 尚未实现 adapter 构造（capability 放行即显式抛，BP-61-1）",
}

_D567_REASON = (
    "扩展只做了一半：契约含扩展 sheet，但工厂 cfg 没注入复数 instrumentation（发布的仍是基表单数那份）"
    "也没注入复数 specs（扩展模块的 specs 不含基表 ⇒ 对齐内核计数不等）；另受裁决 sheet 不可观测缺陷阻断"
    "（design D15 / R12 A 组）。只接 attach 的兄弟 binding 无法实测，待 d567 lane 一并补"
)
#: contract_id → (原因, 「原因仍成立」判据)
_KNOWN_GAPS: dict[str, tuple[str, Any]] = {
    "d3.prepaid_receipts_detail": (_D567_REASON, _factory_instrumentation_still_singular),
    "d5.receivables_financing_detail": (_D567_REASON, _factory_instrumentation_still_singular),
    "d6.contract_assets_detail": (_D567_REASON, _factory_instrumentation_still_singular),
    "d7.contract_liabilities_detail": (_D567_REASON, _factory_instrumentation_still_singular),
}
_WIRED_MULTI: tuple[str, ...] = tuple(
    cid for cid in _MULTI if cid not in _KNOWN_GAPS and cid not in _NO_ADAPTER
)


# ════════════════════════════════════════════════════════════════════════════
# 判据
# ════════════════════════════════════════════════════════════════════════════


class TestSiblingBindingsSupplied:
    def test_denominator_is_not_empty(self) -> None:
        assert len(_XLSX_ROWS) == len(_CASES) > 0
        # 分母过小 ⇒ 判据空转（现算 ≥2 张行表的 entry 远不止这几条）
        assert len(_WIRED_MULTI) >= 10, _WIRED_MULTI

    @pytest.mark.parametrize("contract_id", _MULTI)
    def test_multi_table_attach_supplies_siblings(self, contract_id: str) -> None:
        case = _CASES[contract_id]
        if contract_id in _NO_ADAPTER:
            assert case.wiring.form == "no_adapter", f"{contract_id} 已构造 adapter —— 从 _NO_ADAPTER 删掉再核兄弟 binding"
            return
        gap = _KNOWN_GAPS.get(contract_id)
        if gap is not None:
            reason, still_true = gap
            problem = still_true(case)
            assert problem is None, f"{contract_id} 登记的缺口原因已不成立（{problem}）—— 接上兄弟 binding 并删条目"
            assert not case.wiring.supplies_siblings, f"{contract_id} 已接上兄弟 binding —— 从 _KNOWN_GAPS 删掉"
            return
        assert case.wiring.supplies_siblings, (
            f"{contract_id}（{case.wiring.where}，{case.wiring.form} 形态）契约有 "
            f"{len(case.row_tables)} 张行身份表，attach 只挂主 binding ⇒ materialize / extract "
            "静默退化成单表（R12）"
        )

    def test_gap_registry_has_no_stale_entries(self) -> None:
        stale = sorted(set(_KNOWN_GAPS) - set(_MULTI))
        assert not stale, f"缺口清单里有不再是多行表 entry 的条目：{stale}"

    @pytest.mark.parametrize("contract_id", _WIRED_MULTI)
    def test_alignment_covers_every_row_table(self, contract_id: str) -> None:
        """与生产同一对齐内核：主 binding + 兄弟 binding 恰好覆盖契约全部行身份表（不漏、不重）。"""
        case = _CASES[contract_id]
        provider: Any = case.module
        if case.wiring.form == "factory":
            cfg = closure_cell(case.module.attach_pilot_adapters, "cfg")
            provider = SimpleNamespace(__name__=cfg.adapter_id, instrumentation_specs=cfg.instrumentation_specs_fn)
        primary = PFP._row_bearing_table_key(contract=case.contract, provider=case.module)
        pairs = PFP._align_specs_to_sibling_tables(
            provider=provider, contract=case.contract, primary=SimpleNamespace(table_key=primary)
        )
        covered = [primary, *(str(table.table_key) for _, table in pairs)]
        assert len(covered) == len(set(covered)), f"{contract_id}: 同一张表被覆盖两次 {covered}"
        assert set(covered) == case.row_tables, (
            f"{contract_id}: 漏 {sorted(case.row_tables - set(covered))} / 多 {sorted(set(covered) - case.row_tables)}"
        )

    def test_observed_sibling_bindings_takes_the_named_provider(self) -> None:
        """一行入口按模块名取 provider：F3 得 8 条兄弟；换成单表 provider 的名字 ⇒ 0 条。"""
        from app.services.excel_structure_fingerprint import GT_SYNC_SHEET_NAME
        from app.services.workpaper_sync.excel_extract import ExcelIdentityBinding
        from app.services.workpaper_sync.phase5_row_table_sheet import observed_sibling_bindings

        case = _CASES["f3.notes_payable_detail"]
        primary_key = PFP._row_bearing_table_key(contract=case.contract, provider=case.module)
        observation = SimpleNamespace(identity_binding=ExcelIdentityBinding(
            table_name="GT_PRIMARY", uuid_column="A", table_key=primary_key, metadata_sheet=GT_SYNC_SHEET_NAME,
        ))
        siblings = observed_sibling_bindings(
            provider_name=case.module.__name__, observation=observation, contract=case.contract
        )
        assert {primary_key, *(b.table_key for b in siblings)} == case.row_tables
        assert len(siblings) == len(case.row_tables) - 1
        single = _CASES["f1.prepayment_detail"].module.__name__
        assert observed_sibling_bindings(provider_name=single, observation=observation, contract=case.contract) == ()


class TestAttachResolvesThroughDigestCheck:
    _ROWS = tuple(cid for cid, c in _CASES.items() if c.wiring.form in {"def", "skeleton"})

    @pytest.mark.parametrize("contract_id", _ROWS)
    def test_attach_awaits_own_resolution_not_the_observer(self, contract_id: str) -> None:
        wiring = _CASES[contract_id].wiring
        assert _OBSERVER not in wiring.awaited, (
            f"{contract_id}（{wiring.where}）attach 直调观测器 ⇒ 本模块 {_RESOLVE} 的 contract digest "
            "比对从未被生产调用（摆设），漂移的契约会被照常注册（R12）"
        )
        assert _RESOLVE in wiring.awaited, f"{contract_id}（{wiring.where}）attach 没 await {_RESOLVE}"

    def test_only_registered_entries_build_no_adapter(self) -> None:
        no_adapter = sorted(cid for cid, c in _CASES.items() if c.wiring.form == "no_adapter")
        assert no_adapter == sorted(_NO_ADAPTER), "不构造 adapter 的 attach 必须逐条登记原因（反之登记了的必须仍不构造）"


class TestPredicatesAreFalsifiable:
    """判据本身的反向自检：每个 AST 谓词在「缺陷形态」上必须给出相反结论。"""

    @staticmethod
    def _call(src: str) -> ast.Call:
        node = ast.parse(src).body[0].value  # type: ignore[attr-defined]
        assert isinstance(node, ast.Call)
        return node

    @pytest.mark.parametrize(
        ("src", "expected"),
        [
            ("build_excel_adapter(definitions=d, binding=b)", False),
            ("build_excel_adapter(definitions=d, binding=b, sibling_bindings=())", False),
            ("build_excel_adapter(definitions=d, binding=b, sibling_bindings=None)", False),
            ("build_excel_adapter(definitions=d, binding=b, sibling_bindings=siblings)", True),
            ("build_excel_adapter(sibling_bindings=observed_sibling_bindings(provider_name=__name__))", True),
        ],
    )
    def test_supplies_siblings(self, src: str, expected: bool) -> None:
        assert supplies_siblings(self._call(src)) is expected

    @pytest.mark.parametrize(
        ("src", "expected"),
        [
            ("f(registry, I, session=s)", False),
            ("f(registry, I, session=s, provider_name='app.services.workpaper_sync.other')", False),
            ("f(registry, I, session=s, provider_name=other.__name__)", False),
            ("f(registry, I, session=s, provider_name=__name__)", True),
        ],
    )
    def test_passes_own_name(self, src: str, expected: bool) -> None:
        assert passes_own_name(self._call(src), "provider_name") is expected

    def test_awaited_names_ignores_unawaited_calls(self) -> None:
        node = ast.parse("async def f():\n    observe_published_frozen_definitions()\n    await g()\n").body[0]
        assert awaited_names(node) == {"g"}

    def test_skeleton_hop_is_resolved_through_imports_not_alias_text(self, tmp_path: Path) -> None:
        body = "async def attach_pilot_adapters(registry, *, session):\n    return await HC.attach_h_entry_adapter(registry, I, session=session)\n"
        good = tmp_path / "good.py"
        good.write_text("from app.services.workpaper_sync import phase5_h_cycle_common as HC\n" + body, encoding="utf-8")
        node = top_function(good, "attach_pilot_adapters")
        hop = skeleton_hop(node, good)  # type: ignore[arg-type]
        assert hop is not None and hop[0].name == "phase5_h_cycle_common.py"
        assert not passes_own_name(hop[2], "provider_name"), "没传 provider_name 也算接上 ⇒ 判据放水"
        # 同一个别名指向白名单以外的模块 ⇒ 不是骨架委托（名字本身说明不了任何事）
        bad = tmp_path / "bad.py"
        bad.write_text("from app.services.workpaper_sync import phase5_f3_notes_payable as HC\n" + body, encoding="utf-8")
        assert skeleton_hop(top_function(bad, "attach_pilot_adapters"), bad) is None  # type: ignore[arg-type]
