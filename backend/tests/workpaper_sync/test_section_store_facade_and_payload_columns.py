# -*- coding: utf-8 -*-
"""多区 store 门面按 provider 绑定 + 载荷列按 provider 声明（spec oo-writeback-template-parity-closure R3 批 B3）。

原状（两处叠加，G1 / G3 / G4 / G5 / G6 两个方向都不通）：

1. G3 / G4 / G5 / G6 原样重导出 G9 的门面（``_provider()`` 写死 G9）⇒ 投影 / 合并用 G9 的 spec；G1 自己的门面按
   store item 取第一条 spec ⇒ 三区只通区①。
2. 回写镜像 / 出方向投影 / 采纳覆盖一律读写 ``remark``，而 G1-2 / G3-2 / G6-5 前端只写 ``conclusion``，
   G4-7 / G5-2 两列同写、读 conclusion 优先；G4 / G6 的单数 STORE_ITEM_ID 还照抄成 G4-2-rows / G6-2-rows。

钉住：门面绑定本 provider（且全仓不再有借别家门面的）、各区投影 / 合并 / 新增行归区、dict 外壳只换行数组、
载荷列口径（remark 口径 SQL 与原调用点逐字相同）、回写镜像与出方向读取按口径落列。
"""
from __future__ import annotations

import asyncio
import copy
import importlib
import json
from typing import Any

import pytest

from app.services.workpaper_sync import store_payload_columns as C
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs
from app.services.workpaper_sync.phase5_section_store_facade import SectionStoreFacade

_SYNC = "app.services.workpaper_sync."
BOUND = {
    "phase5_g1_trading_financial_assets": None,
    "phase5_g3_dividend_receivable": None,
    "phase5_g4_bond_investment": None,
    "phase5_g5_long_term_receivable": None,
    "phase5_g6_other_bond": "rows",
    "phase5_g9_other_noncurrent": None,
}


def _mod(name: str) -> Any:
    return importlib.import_module(_SYNC + name)


def _contract(mod: Any) -> Any:
    return parse_contract(mod.build_contract_payload(), adapter_id=mod.ADAPTER_ID)


def _row(spec: Any, rid: str, i: int) -> dict[str, Any]:
    row: dict[str, Any] = {spec.row_identity_key: rid}
    if spec.row_section_field:
        row[spec.row_section_field] = spec.row_section_value
    for _ck, _col, _mode, vtype, path, _label, _group in managed_field_specs(spec):
        if path == spec.row_section_field:  # 区字段不受管（见下方守卫），这里只防夹具自己盖掉区值
            continue
        val: Any = (i + 1) * 100 if vtype in {"amount", "integer"} else f"v{i}"
        cur = row
        parts = str(path).split("/")
        for seg in parts[:-1]:
            cur = cur.setdefault(seg, {})
        cur[parts[-1]] = val
    return row


def _editable_text_path(spec: Any) -> str:
    return next(
        r[4] for r in managed_field_specs(spec)
        if r[2] == "editable" and r[3] == "text" and "/" not in r[4] and r[4] != spec.row_section_field
    )


# ─── 门面绑定 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(BOUND))
def test_facade_bound_to_own_provider(name: str) -> None:
    mod = _mod(name)
    for fn_name in ("build_store_projection", "merge_projection_into_store_rows", "iter_store_rows"):
        fn = getattr(mod, fn_name)
        facade = getattr(fn, "__self__", None)
        assert isinstance(facade, SectionStoreFacade), (name, fn_name)
        assert facade.provider_module == name, (name, fn_name, facade.provider_module)
        assert facade.rows_key == BOUND[name]
    facade = mod.build_store_projection.__self__
    assert facade.specs_for() == tuple(mod.managed_row_table_specs())


def test_no_provider_borrows_another_entrys_facade() -> None:
    """全仓 phase5 provider 的门面函数若是 SectionStoreFacade 的绑定方法，必须绑本模块（不许再借别家）。"""
    import pkgutil

    import app.services.workpaper_sync as pkg

    checked = 0
    for info in pkgutil.iter_modules(pkg.__path__):
        if not info.name.startswith("phase5_"):
            continue
        mod = _mod(info.name)
        for fn_name in ("build_store_projection", "merge_projection_into_store_rows", "iter_store_rows"):
            facade = getattr(getattr(mod, fn_name, None), "__self__", None)
            if isinstance(facade, SectionStoreFacade) and info.name != "phase5_g9_store_facade":
                checked += 1
                assert facade.provider_module == info.name, (info.name, fn_name, facade.provider_module)
    assert checked >= 15  # 5 家 × 3 个门面（G9 主模块经伴生模块重导出，也绑 G9 自己）


def test_no_spec_manages_its_own_section_field() -> None:
    """区归属字段不得是受管列：受管就会被 OO 侧那一格的值盖掉，行落到各区之外（G1 A 列原绑 acctClass）。"""
    import pkgutil

    import app.services.workpaper_sync as pkg

    sectioned = 0
    offenders: list[tuple[str, str]] = []
    for info in pkgutil.iter_modules(pkg.__path__):
        if not info.name.startswith("phase5_"):
            continue
        fn = getattr(_mod(info.name), "managed_row_table_specs", None)
        if not callable(fn):
            continue
        for spec in fn():
            if not spec.row_section_field:
                continue
            sectioned += 1
            if any(r[4] == spec.row_section_field for r in managed_field_specs(spec)):
                offenders.append((info.name, spec.table_key))
    assert offenders == []
    assert sectioned >= 10  # G1 三区 / G3 两区 / G5 / G9 三区 / L5 两区 / D6 两区（经各自主模块与伴生模块重复计入）


def test_g1_column_a_is_investment_category_not_section() -> None:
    mod = _mod("phase5_g1_trading_financial_assets")
    for spec in mod.managed_row_table_specs():
        first = managed_field_specs(spec)[0]
        assert (first[1], first[4]) == ("A", "investType"), first
    # OO 侧在区② 新增一行、A 列填类别文字：行仍归区②，类别落 investType
    spec = mod.managed_row_table_specs()[1]
    row = _row(spec, "r-new", 3)
    row["investType"] = "债务工具投资"
    proj = mod.build_store_projection(json.dumps([row], ensure_ascii=False), contract=_contract(mod))
    merged, *_ = mod.merge_projection_into_store_rows(projection=proj, base_rows=[])
    (got,) = merged
    assert got["acctClass"] == "classified_fvpl" and got["investType"] == "债务工具投资"


def _golden_module() -> Any:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts/check/check_sync_provider_golden_digest.py"
    spec = importlib.util.spec_from_file_location("_golden_digest_b3", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_golden_digest_rejects_empty_synthetic_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    """零回归门：合成 payload 投影为空必须打红（原基线里 g1 / g3 / g4 / g5 / g6 都是空投影的 digest）。"""
    gd = _golden_module()
    entry = next(e for e in gd.PROVIDERS if e[0] == "g4")
    assert gd._digests_for(*entry)["store_projection_sha256"]  # 对照：真门面投影非空、算得出 digest
    real = gd._import_provider(entry[1])

    class _EmptyProjectionProvider:
        """其余属性原样转发真 provider，只把投影换成「空载荷的投影」（门禁的 `_import_provider` 会 reload 模块，
        直接改模块属性会被 reload 冲掉 ⇒ 换掉取 provider 这一步）。"""

        __name__ = real.__name__

        def __getattr__(self, name: str) -> Any:
            return getattr(real, name)

        @staticmethod
        def build_store_projection(payload: Any, *, contract: Any, **_kw: Any) -> Any:
            return real.build_store_projection([], contract=contract)

    monkeypatch.setattr(gd, "_import_provider", lambda _name: _EmptyProjectionProvider())
    with pytest.raises(RuntimeError, match="投影为空"):
        gd._digests_for(*entry)


def test_g4_g6_single_store_item_is_the_managed_one() -> None:
    for name, item in (("phase5_g4_bond_investment", "G4-7-items"), ("phase5_g6_other_bond", "G6-5-fair-value-data")):
        mod = _mod(name)
        assert mod.STORE_ITEM_ID == item
        assert tuple(mod.all_store_item_ids()) == (item,)


# ─── 投影 / 合并 ────────────────────────────────────────────────────────────


def test_g1_projects_and_merges_all_three_zones() -> None:
    mod = _mod("phase5_g1_trading_financial_assets")
    specs = mod.managed_row_table_specs()
    assert [s.row_section_value for s in specs] == ["trading", "classified_fvpl", "designated_fvpl"]
    base = [_row(s, f"r{i}", i) for i, s in enumerate(specs)]
    contract = _contract(mod)
    proj = mod.build_store_projection(json.dumps(base), contract=contract)
    for i, s in enumerate(specs):
        assert any(k.startswith(f"{s.table_key}/r{i}/") for k in proj.values), s.table_key
    # OO 侧改区② 一格、在区③ 新增一行
    edited = copy.deepcopy(base)
    path = _editable_text_path(specs[1])
    edited[1][path] = "OO 改的"
    new_row = _row(specs[2], "r-new", 7)
    edited.append(new_row)
    merged, applied, _visited, touched = mod.merge_projection_into_store_rows(
        projection=mod.build_store_projection(json.dumps(edited), contract=contract), base_rows=base,
    )
    by_id = {r["id"]: r for r in merged}
    assert by_id["r1"][path] == "OO 改的" and "r1" in touched and applied > 0
    assert by_id["r-new"]["acctClass"] == "designated_fvpl"  # 新增行按区补归属
    assert by_id["r0"] == base[0]


def test_g3_projects_its_own_two_zones() -> None:
    mod = _mod("phase5_g3_dividend_receivable")
    specs = mod.managed_row_table_specs()
    base = [_row(s, f"r{i}", i) for i, s in enumerate(specs)]
    proj = mod.build_store_projection(json.dumps(base), contract=_contract(mod))
    assert {k.split("/")[0] for k in proj.values} == {s.table_key for s in specs} == {"g3_2_rows_r1", "g3_2_rows_r2"}


def test_g4_projects_inventory_rows() -> None:
    mod = _mod("phase5_g4_bond_investment")
    (spec,) = mod.managed_row_table_specs()
    proj = mod.build_store_projection(json.dumps([_row(spec, "a", 0)]), contract=_contract(mod))
    assert proj.values and all(k.startswith("g4_7_items/a/") for k in proj.values)


def test_g6_dict_shell_projection_and_state_merge_keep_other_keys() -> None:
    mod = _mod("phase5_g6_other_bond")
    (spec,) = mod.managed_row_table_specs()
    contract = _contract(mod)
    state = {"rows": [_row(spec, "a", 0)], "conclusion": "公允价值测试结论", "version": 2}
    proj = mod.build_store_projection(json.dumps(state, ensure_ascii=False), contract=contract)
    assert proj.values and all(k.startswith("g6_5_fair_value/a/") for k in proj.values)
    # 无外壳的行数组也认（合成 payload / 旧数据）
    assert mod.build_store_projection(json.dumps(state["rows"]), contract=contract).values == proj.values
    edited = copy.deepcopy(state)
    path = _editable_text_path(spec)
    edited["rows"][0][path] = "OO 改的"
    merged, applied, _visited = mod.merge_projection_into_store_state(
        projection=mod.build_store_projection(json.dumps(edited), contract=contract), base_state=state,
    )
    assert applied > 0 and merged["rows"][0][path] == "OO 改的"
    assert merged["conclusion"] == "公允价值测试结论" and merged["version"] == 2
    # 采纳覆盖按行数组枚举：对象载荷照旧 fail visible（不会把外壳写丢）
    with pytest.raises(Exception, match="行对象数组"):
        list(mod.iter_store_rows(json.dumps(state)))


# ─── 载荷列口径 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("phase5_n1_deferred_tax_assets", C.CONCLUSION_ONLY),
        ("phase5_n2_taxes_payable", C.CONCLUSION_ONLY),
        ("phase5_n3_deferred_tax_liabilities", C.CONCLUSION_ONLY),
        ("phase5_g1_trading_financial_assets", C.CONCLUSION_ONLY),
        ("phase5_g3_dividend_receivable", C.CONCLUSION_ONLY),
        ("phase5_g6_other_bond", C.CONCLUSION_ONLY),
        ("phase5_g4_bond_investment", C.DUAL_WRITE),
        ("phase5_g5_long_term_receivable", C.DUAL_WRITE),
        ("phase5_g9_other_noncurrent", C.REMARK_ONLY),
        ("phase5_g2_interest_receivable", C.REMARK_ONLY),
        ("phase5_h6_asset_disposal_clearing", C.REMARK_ONLY),  # dual_write_remark_and_conclusion ≠ 两列同写
    ],
)
def test_payload_columns_follow_provider_declaration(name: str, expected: C.PayloadColumns) -> None:
    assert C.payload_columns_of(_mod(name)) is expected


def test_remark_sql_is_byte_identical_to_the_original_call_sites() -> None:
    r = C.REMARK_ONLY
    assert r.select_sql() == "SELECT remark FROM checklist_responses WHERE wp_id = :wp AND item_id = :item"
    assert r.select_sql(limit=True) == (
        "SELECT remark FROM checklist_responses WHERE wp_id = :wp AND item_id = :item LIMIT 1"
    )
    assert r.update_sql == (
        "UPDATE checklist_responses SET remark = :val, updated_at = now() WHERE wp_id = :wp AND item_id = :item"
    )
    assert r.insert_sql == (
        "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, created_at, updated_at) "
        "VALUES (gen_random_uuid(), :pid, :wp, :item, :val, now(), now())"
    )
    assert C.DUAL_WRITE.update_sql.startswith("UPDATE checklist_responses SET conclusion = :val, remark = :val,")


def test_remark_hardwired_mirror_paths_only_serve_remark_providers() -> None:
    """多 item 镜像里 D4 的专用块 / dedicated dict store 的 SQL 仍写死 remark：走到它们的 provider 必须是 remark 口径。

    否则就是本批修掉的那类缺陷（前端只写 conclusion，回写却落 remark）换个路径再出现。
    """
    from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

    hit = 0
    for aid, plan in STORE_MERGE_REGISTRY.items():
        if not (plan.dual_store_fn or plan.dedicated_items):
            continue
        hit += 1
        assert C.payload_columns_of(_mod(plan.provider_module)) is C.REMARK_ONLY, aid
    assert hit >= 3  # d1 / d2 / d4


def test_unknown_payload_column_fails_visible() -> None:
    class _P:
        PAYLOAD_COLUMN = "remarks"

    with pytest.raises(ValueError, match="remark / conclusion"):
        C.payload_columns_of(_P())


class _Result:
    def __init__(self, row: dict[str, Any] | None, rowcount: int = 1) -> None:
        self._row = row
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> Any:
        return None if self._row is None else next(iter(self._row.values()))

    def mappings(self) -> "_Result":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._row


class _Session:
    """按 SELECT 的列返回同一行库存；记下全部写语句。"""

    def __init__(self, stored: dict[str, Any] | None) -> None:
        self.stored = stored
        self.writes: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _Result:
        sql = str(getattr(stmt, "text", stmt))
        if sql.startswith("SELECT"):
            if self.stored is None:
                return _Result(None)
            cols = [c.strip() for c in sql[len("SELECT "):sql.index(" FROM")].split(",")]
            return _Result({c: self.stored.get(c) for c in cols})
        self.writes.append((sql, dict(params or {})))
        return _Result(None, rowcount=1)

    async def commit(self) -> None:
        return None


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ({"remark": "R", "conclusion": "C"}, "C"),
        ({"remark": "R", "conclusion": "  "}, "R"),
        ({"remark": None, "conclusion": None}, None),
        (None, None),
    ],
)
def test_dual_read_prefers_conclusion_then_remark(stored: Any, expected: Any) -> None:
    got = asyncio.run(C.read_payload(_Session(stored), wp_id="w", item_id="i", columns=C.DUAL_WRITE))
    assert got == expected


def _mirror(adapter_id: str, session: _Session, projection: Any) -> None:
    from app.services.workpaper_sync.store_mirror import mirror_projection_into_store

    asyncio.run(mirror_projection_into_store(
        session, adapter_id=adapter_id, project_id="p", wp_id="w", merged_projection=projection, commit=False,
    ))


def test_mirror_writes_g1_conclusion_with_all_zones() -> None:
    mod = _mod("phase5_g1_trading_financial_assets")
    specs = mod.managed_row_table_specs()
    base = [_row(s, f"r{i}", i) for i, s in enumerate(specs)]
    edited = copy.deepcopy(base)
    path = _editable_text_path(specs[2])
    edited[2][path] = "区③ 改的"
    session = _Session({"conclusion": json.dumps(base, ensure_ascii=False), "remark": "[]"})
    _mirror(mod.ADAPTER_ID, session, mod.build_store_projection(json.dumps(edited), contract=_contract(mod)))
    ((sql, params),) = session.writes
    assert sql.startswith("UPDATE checklist_responses SET conclusion = :val,") and "remark" not in sql
    assert params["item"] == "G1-2-rows"
    assert {r["id"]: r for r in json.loads(params["val"])}["r2"][path] == "区③ 改的"


def test_mirror_g6_state_keeps_shell_in_conclusion() -> None:
    mod = _mod("phase5_g6_other_bond")
    (spec,) = mod.managed_row_table_specs()
    state = {"rows": [_row(spec, "a", 0)], "conclusion": "结论"}
    edited = copy.deepcopy(state)
    path = _editable_text_path(spec)
    edited["rows"][0][path] = "OO 改的"
    session = _Session({"conclusion": json.dumps(state, ensure_ascii=False)})
    _mirror(mod.ADAPTER_ID, session, mod.build_store_projection(json.dumps(edited), contract=_contract(mod)))
    ((sql, params),) = session.writes
    assert "SET conclusion = :val," in sql and params["item"] == "G6-5-fair-value-data"
    written = json.loads(params["val"])
    assert written["conclusion"] == "结论" and written["rows"][0][path] == "OO 改的"


def test_mirror_g4_dual_writes_both_columns_from_conclusion_base() -> None:
    mod = _mod("phase5_g4_bond_investment")
    (spec,) = mod.managed_row_table_specs()
    base = [_row(spec, "a", 0)]
    edited = copy.deepcopy(base)
    path = _editable_text_path(spec)
    edited[0][path] = "OO 改的"
    session = _Session({"conclusion": json.dumps(base, ensure_ascii=False), "remark": "[]"})
    _mirror(mod.ADAPTER_ID, session, mod.build_store_projection(json.dumps(edited), contract=_contract(mod)))
    ((sql, params),) = session.writes
    assert "SET conclusion = :val, remark = :val," in sql and params["item"] == "G4-7-items"
    assert json.loads(params["val"])[0][path] == "OO 改的"


def test_outbound_reads_the_declared_column() -> None:
    from app.services.workpaper_sync.store_projection_response import read_store_payload

    mod = _mod("phase5_g1_trading_financial_assets")
    read = asyncio.run(read_store_payload(session=_Session({"remark": "[]", "conclusion": "[{\"id\": \"x\"}]"}),
                                          wp_id="w", provider=mod))
    assert read.payload == "[{\"id\": \"x\"}]" and not read.empty


def _calls(fn: Any, name: str) -> list[Any]:
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == name
    ]


def _kw_name(call: Any, key: str) -> str | None:
    value = next((k.value for k in call.keywords if k.arg == key), None)
    return getattr(value, "id", None)


def test_adopt_threads_one_payload_column_through_snapshots_deletions_and_audit() -> None:
    """采纳覆盖：两次快照、删除侧、回滚审计都按同一口径（`payload_columns_for_adapter`）—— AST 现读调用点。"""
    import ast
    import inspect
    import textwrap

    from app.services.workpaper_sync import adopt_overwrite_apply as AOA
    from app.services.workpaper_sync import adopt_substrate_response as ASR

    fn = ASR.compute_adopt_substrate
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    assigns = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "columns" for t in n.targets)
    ]
    assert len(assigns) == 1, "compute_adopt_substrate 应恰有一处 columns = …"
    value = assigns[0].value
    assert isinstance(value, ast.Call) and getattr(value.func, "id", None) == "payload_columns_for_adapter", (
        f"columns 不是按 adapter 取的载荷列口径：{ast.dump(value)[:120]}"
    )
    snaps = _calls(fn, "_snapshot_store")
    assert len(snaps) == 2 and all(_kw_name(c, "columns") == "columns" for c in snaps)
    for name in ("apply_overwrite_deletions", "_record_rollback_and_audit"):
        (call,) = _calls(fn, name)
        assert _kw_name(call, "columns") == "columns", name
    inner = _calls(AOA.apply_overwrite_deletions, "_snapshot_store")
    assert inner and all(_kw_name(c, "columns") == "cols" for c in inner)


def test_rollback_audit_records_snapshot_columns_only_when_not_remark(monkeypatch: pytest.MonkeyPatch) -> None:
    import uuid

    from app.services import audit_log_helper
    from app.services.workpaper_sync import adopt_substrate_response as ASR

    captured: list[dict[str, Any]] = []

    async def _fake_append(_session: Any, entry: dict[str, Any]) -> None:
        captured.append(dict(entry["details"]))

    monkeypatch.setattr(audit_log_helper, "append_audit_log", _fake_append)
    monkeypatch.setattr(ASR, "audit_details_for_applied", lambda _applied: {})
    common = dict(
        project_id=uuid.uuid4(), wp_id="w", entry_id="e", substrate_sha="s",
        before_snapshot={"G1-2-rows": "[]"}, changed_items=["G1-2-rows"], rollback_items=["G1-2-rows"],
        applied=None,
    )
    cases = ((C.CONCLUSION_ONLY, ["conclusion"]), (C.DUAL_WRITE, ["conclusion", "remark"]), (C.REMARK_ONLY, None))
    for columns, expected in cases:
        captured.clear()
        asyncio.run(ASR._record_rollback_and_audit(object(), columns=columns, **common))
        (details,) = captured
        assert details.get("rollback_snapshot_columns") == expected, columns
        assert ("rollback_snapshot_columns" in details) is (expected is not None)
    captured.clear()
    asyncio.run(ASR._record_rollback_and_audit(object(), **common))  # 旧调用（不传口径）⇒ details 不变
    assert "rollback_snapshot_columns" not in captured[0]


def test_adopt_snapshot_and_adapter_columns() -> None:
    from app.services.workpaper_sync.adopt_substrate_response import _snapshot_store

    assert C.payload_columns_for_adapter("g1.trading_financial_assets_detail") is C.CONCLUSION_ONLY
    assert C.payload_columns_for_adapter("g9.other_noncurrent_detail") is C.REMARK_ONLY
    snap = asyncio.run(_snapshot_store(_Session({"remark": "R", "conclusion": "C"}), wp_id="w",
                                       item_ids=("G1-2-rows",), columns=C.CONCLUSION_ONLY))
    assert snap == {"G1-2-rows": "C"}
    legacy = asyncio.run(_snapshot_store(_Session({"remark": "R", "conclusion": "C"}), wp_id="w", item_ids=("x",)))
    assert legacy == {"x": "R"}
