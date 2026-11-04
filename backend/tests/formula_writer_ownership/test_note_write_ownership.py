"""附注写入归属矩阵与判定（spec formula-writer-ownership-and-stale R1b / ADR-WOS-04，design §13）。

纯函数与登记表守卫：矩阵与登记表 / 推送规则双向一致、生成器幂等；判定顺序（locked → manual → 推送只写声明格 → 域外放行 →
容器 → 推送写定格 → 基础条目）；未知矩阵项 fail-closed；错误准则不得命中；模板绑定合并按 locked 语义保留推送写定格。
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import note_write_ownership as own
from app.services.note_formula_push_guard import OwnedPushCell
from app.services.note_write_ownership import (
    ANY_TABLE, CELL_PREFIX, FIELD_ROWS, FIELD_SUB_TABLE, IDENTITY, MatrixEntry, OwnershipMatrix, WriteGate,
    governed_chapters, load_matrix, merge_holding_pushed_cells, never_synced_manual_block, normalize_template_type,
)
from app.services.note_writers import NOTE_WRITERS, ROLES

ROOT = Path(__file__).resolve().parents[3]
GEN_PATH = ROOT / "backend" / "scripts" / "gen" / "gen_note_write_ownership_matrix.py"
AUTOMATIC = {"formula_push", "workpaper_sync", "workpaper_html_sync", "binding_refill", "update_note_values",
             "generate_notes", "report_sync", "formula_runtime_apply"}
GATE_MARKERS = {"WriteGate", "with_ownership", "merge_holding_pushed_cells"}

DOMAIN = frozenset({("soe", "八、1")})
CASH = "货币资金"


def _gen():
    spec = importlib.util.spec_from_file_location("gen_note_write_ownership_matrix", GEN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _matrix(push_fields: tuple[str, ...] = ("end_amount",), *, chapter=("soe", "八、1")) -> OwnershipMatrix:
    entries = {
        (ANY_TABLE, FIELD_SUB_TABLE): MatrixEntry("workpaper_sync"),
        (ANY_TABLE, FIELD_ROWS): MatrixEntry("binding_refill"),
        **{(CASH, CELL_PREFIX + f): MatrixEntry("formula_push", "pushed_cells", rules=("E1.note.main_rows",))
           for f in push_fields},
    }
    return OwnershipMatrix(chapters={chapter: entries}, identity=dict(IDENTITY))


def _gate(writer: str, table_data=None, *, template_type="soe", section="八、1", matrix=None, domain=DOMAIN):
    return WriteGate(writer, template_type, section, table_data if table_data is not None else {},
                     matrix=matrix if matrix is not None else _matrix(), domain=domain)


WORKPAPER_TD = {"_source": "workpaper", "sub_table_data": {CASH: [{"label": "库存现金", "end_amount": 1}]},
                "_sub_table_columns": {CASH: [{"key": "label", "is_label": True}, {"key": "end_amount"}]}}


# ─── 矩阵与登记表 ──────────────────────────────────────────────────────────────


def test_generated_matrix_is_current_and_render_is_idempotent():
    gen = _gen()
    text = own.MATRIX_PATH.read_text(encoding="utf-8")
    assert gen.render(gen.compute_matrix()) == text, "矩阵文件与登记表 / 推送规则现算不一致：重跑生成器"
    assert gen.main(["--check"]) == 0
    assert "generated_at" not in text, "输出不含时间戳（内容不变则字节不变）"


def test_matrix_domain_equals_registry_and_push_entries_equal_note_rules():
    from app.services.formula_push.engine import load_push_rules

    matrix = load_matrix()
    domain = governed_chapters()
    assert {tt for tt, _ in domain} == {"listed", "soe"}
    assert set(matrix.chapters) == set(domain), "矩阵章节 = 登记表按准则的章节（双向）"
    expected = {
        (tt, sec, rule.target.resolve_table(tt) or rule.target.table, CELL_PREFIX + field)
        for rule in load_push_rules() if rule.stage == "note"
        for tt, sec in rule.target.sections.items() for field in rule.target.fields
    }
    actual = {(tt, sec, table, field) for (tt, sec), entries in matrix.chapters.items()
              for (table, field), entry in entries.items() if entry.owner == "formula_push"}
    assert expected and actual == expected, "推送条目 = 附注推送规则目标（双向）"
    for key, entries in matrix.chapters.items():
        assert entries[(ANY_TABLE, FIELD_SUB_TABLE)].owner == "workpaper_sync", key
        assert entries[(ANY_TABLE, FIELD_ROWS)].owner == "binding_refill", key
        assert all(e.scope == "pushed_cells" for (t, f), e in entries.items() if e.owner == "formula_push"), key


def test_check_mode_fails_on_drift_and_on_missing_file(tmp_path, capsys):
    gen = _gen()
    text = own.MATRIX_PATH.read_text(encoding="utf-8")
    current = tmp_path / "current.json"
    current.write_text(text, encoding="utf-8")
    assert gen.main(["--check", "--output", str(current)]) == 0
    lines = text.splitlines(keepends=True)
    victim = next(i for i, line in enumerate(lines) if '"owner": "formula_push"' in line)
    drifted = tmp_path / "drifted.json"
    drifted.write_text("".join(lines[:victim] + lines[victim + 1:]), encoding="utf-8")
    assert gen.main(["--check", "--output", str(drifted)]) == 2
    assert "已漂移" in capsys.readouterr().err
    assert gen.main(["--check", "--output", str(tmp_path / "missing.json")]) == 2


def test_generator_refuses_push_targets_outside_the_registry(monkeypatch):
    """推送规则目标章节不在交接域 ⇒ 拒绝生成并点名规则（与 D1 矛盾，须先拍板），而不是静默漏掉这一章。"""
    from app.services.formula_push import engine as push_engine

    real = push_engine.load_push_rules()
    stray = SimpleNamespace(stage="note", rule_id="X9.note.stray", target=SimpleNamespace(
        sections={"soe": "八、999"}, table=CASH, fields=("end_amount",), resolve_table=lambda tt: None))
    monkeypatch.setattr(push_engine, "load_push_rules", lambda: (*real, stray))
    with pytest.raises(SystemExit, match=r"X9\.note\.stray（soe 八、999）"):
        _gen().compute_matrix()


def test_identity_and_roles_are_registered():
    matrix = load_matrix()
    assert dict(matrix.identity) == IDENTITY, "矩阵文件里的写方身份与判定模块一致"
    ids = {w.writer_id for w in NOTE_WRITERS}
    assert set(IDENTITY) | set(IDENTITY.values()) <= ids
    assert [w.writer_id for w in NOTE_WRITERS if w.role not in ROLES] == []
    assert {w.writer_id for w in NOTE_WRITERS if w.role == "automatic"} == AUTOMATIC
    owners = {e.owner for entries in matrix.chapters.values() for e in entries.values()}
    assert owners <= AUTOMATIC, "矩阵所有者只能是受约束的自动写方"


def _function(tree: ast.Module, qualname: str):
    parts = qualname.split(".")
    scope: list[ast.stmt] = tree.body
    node = None
    for part in parts:
        node = next((n for n in scope if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                     and n.name == part), None)
        assert node is not None, qualname
        scope = node.body
    return node, (next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == parts[0])
                  if len(parts) > 1 else None)


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def gate_reached(source: str, qualname: str) -> bool:
    """入口函数引用判定，或调用的同模块函数 / 同类方法引用判定（只看一层）。"""
    tree = ast.parse(source)
    fn, cls = _function(tree, qualname)
    names = _names(fn)
    if names & GATE_MARKERS:
        return True
    siblings = [n for n in (cls.body if cls is not None else []) + tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    called = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
              for n in ast.walk(fn) if isinstance(n, ast.Call)}
    return any(s.name in called and _names(s) & GATE_MARKERS for s in siblings)


def test_every_automatic_writer_goes_through_write_gate():
    missing = []
    for spec in (w for w in NOTE_WRITERS if w.role == "automatic"):
        module, qualname = spec.entrypoint.split(":", 1)
        path = ROOT / "backend" / Path(*module.split(".")).with_suffix(".py")
        if not gate_reached(path.read_text(encoding="utf-8"), qualname):
            missing.append(spec.entrypoint)
    assert missing == [], f"自动写方入口没有经写入归属判定：{missing}"


def test_gate_reach_checker_is_not_vacuous():
    assert not gate_reached("def f(td):\n    td['x'] = 1\n", "f")
    assert gate_reached("def f(td):\n    WriteGate('a', 'soe', 's', td)\n", "f")
    assert gate_reached("class A:\n    def g(self):\n        return WriteGate()\n    def f(self):\n        self.g()\n",
                        "A.f")


# ─── 判定顺序 ──────────────────────────────────────────────────────────────────


def test_cell_modes_come_first_and_legacy_placeholder_is_the_only_manual_exception():
    gate = _gate("binding_refill")
    assert gate.check(table=ANY_TABLE, field=FIELD_ROWS, cell_mode="locked").code == "locked"
    assert gate.check(table=ANY_TABLE, field=FIELD_ROWS, section_locked=True).code == "locked"
    assert gate.check(table=ANY_TABLE, field=FIELD_ROWS, cell_mode="manual").code == "manual"
    assert gate.check(table=ANY_TABLE, field=FIELD_ROWS, cell_mode="manual", legacy_manual=True).allowed
    assert gate.check(table=ANY_TABLE, field=FIELD_ROWS, cell_mode="locked", legacy_manual=True).code == "locked"
    assert not gate.check(table=CASH, field=FIELD_ROWS, column="end_amount", cell_mode="locked",
                          pushed=True).reportable, "锁定 / 人工的保留不进 blocked_writes"


def test_push_writes_only_declared_cells_even_outside_the_domain():
    push = _gate("formula_push")
    assert push.check(table=CASH, field=FIELD_ROWS, column="end_amount").allowed
    assert push.check(table=CASH, field=FIELD_SUB_TABLE, column="end_amount").allowed
    assert push.check(table=CASH, field=FIELD_ROWS, column="prior_amount").code == "unknown_entry"
    assert push.check(table="其他表", field=FIELD_ROWS, column="end_amount").code == "unknown_entry"
    outside = _gate("formula_push", section="八、99")
    assert not outside.governed and outside.check(table=CASH, field=FIELD_ROWS, column="end_amount").code == \
        "unknown_entry", "按标题改投到矩阵外的章节也拒"


def test_pushed_cell_belongs_to_push_and_unestablished_cell_falls_back_to_container_owner():
    refill = _gate("binding_refill")
    blocked = refill.check(table=CASH, field=FIELD_ROWS, column="end_amount", pushed=True)
    assert (blocked.allowed, blocked.code, blocked.owner_id) == (False, "pushed_cell", "formula_push")
    assert refill.check(table=CASH, field=FIELD_ROWS, column="end_amount").allowed, "推送没写定前按基础条目临时填"
    assert refill.check(table=CASH, field=FIELD_ROWS, column="prior_amount", pushed=True).allowed, \
        "矩阵没声明归推送的字段不按推送状态拦"
    sync = _gate("workpaper_sync", WORKPAPER_TD)
    assert sync.check(table=CASH, field=FIELD_SUB_TABLE, column="end_amount", pushed=True).code == "pushed_cell"
    assert sync.check(table=CASH, field=FIELD_SUB_TABLE, column="prior_amount").allowed


def test_base_owner_identity_and_owner_mismatch():
    assert _gate("binding_refill").check(table="x", field=FIELD_ROWS).allowed
    assert _gate("update_note_values").check(table="x", field=FIELD_ROWS).allowed, "报表更新 ≡ 模板绑定取数"
    assert _gate("generate_notes").check(table="x", field=FIELD_ROWS).allowed, "生成合并 ≡ 模板绑定取数"
    assert _gate("workpaper_html_sync", WORKPAPER_TD).check(table=CASH, field=FIELD_SUB_TABLE).allowed
    for writer in ("report_sync", "formula_runtime_apply", "workpaper_sync"):
        verdict = _gate(writer).check(table="x", field=FIELD_ROWS)
        assert (verdict.code, verdict.owner_id) == ("owner_mismatch", "binding_refill"), writer
    assert _gate("binding_refill").check(table=CASH, field=FIELD_SUB_TABLE).code == "owner_mismatch"


def test_template_container_is_shadowed_once_the_workpaper_container_is_active():
    refill = _gate("binding_refill", WORKPAPER_TD)
    assert refill.container == FIELD_SUB_TABLE
    verdict = refill.check(table=ANY_TABLE, field=FIELD_ROWS)
    assert (verdict.code, verdict.owner_id) == ("inactive_container", "workpaper_sync")
    empty_sub = {"_source": "workpaper", "sub_table_data": {}, "_tables": [{"rows": []}]}
    assert _gate("binding_refill", empty_sub).container == FIELD_ROWS, "投影为空 ⇒ 模板容器仍生效（与读时投影同判据）"
    assert _gate("binding_refill", {"sub_table_data": WORKPAPER_TD["sub_table_data"]}).container == FIELD_ROWS, \
        "没有底稿来源标记 ⇒ 不投影"


def test_unknown_matrix_rows_fail_closed_and_wrong_template_type_never_matches():
    blank = _gate("binding_refill", section="八、2", domain=DOMAIN | {("soe", "八、2")})
    assert blank.governed and blank.check(table="x", field=FIELD_ROWS).code == "unknown_entry", "域内缺行即拒"
    wrong = _gate("binding_refill", template_type="listed")
    assert not wrong.governed, "上市准则下的 八、1 不是交接章节"
    assert _gate("formula_push", template_type="listed").check(
        table=CASH, field=FIELD_ROWS, column="end_amount").code == "unknown_entry"
    assert normalize_template_type("soe_consolidated") == "soe" and normalize_template_type("listed") == "listed"
    assert normalize_template_type("custom") is None and normalize_template_type(None) is None


def test_unreadable_matrix_file_fails_closed(tmp_path):
    empty = load_matrix(tmp_path / "missing.json")
    assert empty.chapters == {}
    assert _gate("binding_refill", matrix=empty).check(table="x", field=FIELD_ROWS).code == "unknown_entry"
    assert _gate("formula_push", matrix=empty).check(
        table=CASH, field=FIELD_ROWS, column="end_amount").code == "unknown_entry"


def test_record_reports_ownership_blocks_with_structured_log(caplog):
    gate = _gate("report_sync")
    assert gate.record(gate.check(table="x", field=FIELD_ROWS, cell_mode="locked"), table="x", field=FIELD_ROWS) \
        is None and gate.blocked_writes == []
    with caplog.at_level(logging.INFO, logger=own.__name__):
        entry = gate.record(gate.check(table="x", field=FIELD_ROWS), table="x", field=FIELD_ROWS, row="库存现金",
                            incoming=5.0, kept=None)
    assert entry == gate.blocked_writes[0]
    assert {k: entry[k] for k in ("section", "table", "field", "row", "writer_id", "owner_id", "reason_code")} == {
        "section": "八、1", "table": "x", "field": FIELD_ROWS, "row": "库存现金", "writer_id": "report_sync",
        "owner_id": "binding_refill", "reason_code": "owner_mismatch"}
    assert "绑定取数刷新" in entry["reason"] and "报表同步附注" in entry["reason"], "原因写明所有者与被拒写方"
    assert "kept" not in entry and entry["incoming"] == 5.0, "值为 None 的附加键不进回报"
    record = next(r for r in caplog.records if getattr(r, "event", None) == "note_write_blocked")
    assert record.blocked_write == entry and "note_write_blocked" in record.getMessage()


# ─── manual 策略（底稿披露容器接管） ───────────────────────────────────────────


def test_manual_policy_predicate_and_takeover_scope():
    assert never_synced_manual_block(False, 1) and never_synced_manual_block(False, 3)
    assert not never_synced_manual_block(False, 0) and not never_synced_manual_block(True, 2)
    manual = {"_tables": [{"rows": [{"label": "库存现金", "values": [12.0, None], "_cell_modes": {"0": "manual"}}]}]}
    verdict = _gate("workpaper_sync", manual).check_takeover(manual)
    assert (verdict.allowed, verdict.code, verdict.owner_id) == (False, "manual_values_never_synced", "manual_editor")
    assert verdict.reportable
    assert _gate("workpaper_html_sync", manual).check_takeover(manual).code == "manual_values_never_synced"
    assert _gate("workpaper_sync", manual).check_takeover({**manual, "_last_sync_wp_id": "w"}).allowed, "同步过的不拦"
    assert _gate("workpaper_sync", manual, section="八、99").check_takeover(manual).allowed, "域外沿用前端同步现状"
    assert _gate("binding_refill", manual).check_takeover(manual).allowed, "只约束底稿披露同步"
    empty_manual = {"_tables": [{"rows": [{"values": [None], "_cell_modes": {"0": "manual"}}]}]}
    assert _gate("workpaper_sync", empty_manual).check_takeover(empty_manual).allowed, "空的人工格不算填写"


def test_matrix_manual_policy_cases_are_computed_by_the_backend_predicate():
    cases = json.loads(own.MATRIX_PATH.read_text(encoding="utf-8"))["manual_policy"]["cases"]
    assert {c["blocked"] for c in cases} == {True, False}
    assert all(c["blocked"] == never_synced_manual_block(c["synced_before"], c["manual_values"]) for c in cases)


# ─── 模板绑定合并：推送写定格按 locked 语义保留 ─────────────────────────────────


def _template_td(rows: list[tuple[str, list]]) -> dict:
    table = {"name": CASH, "headers": ["项目", "期末余额", "期初余额"],
             "rows": [{"label": label, "values": list(values)} for label, values in rows]}
    return {"_tables": [table], "headers": list(table["headers"]), "rows": copy.deepcopy(table["rows"]),
            "name": CASH}


def test_merge_holds_pushed_cell_and_merges_everything_else():
    old = _template_td([("库存现金", [100.0, 50.0]), ("银行存款", [1.0, 2.0])])
    old["_tables"][0]["rows"][0]["_cell_modes"] = {"1": "auto"}
    new = _template_td([("库存现金", [111.0, 55.0]), ("银行存款", [3.0, 4.0])])
    owned = {(0, 0, 0): OwnedPushCell(table=CASH, field="end_amount", label="库存现金", pushed=100.0)}
    gate = _gate("update_note_values", old, matrix=_matrix(("end_amount",)))
    merged = merge_holding_pushed_cells(old, new, owned, gate)

    rows = merged["_tables"][0]["rows"]
    assert [r["values"] for r in rows] == [[100.0, 55.0], [3.0, 4.0]], "推送写定格保留，其余格照三态合并取新值"
    assert rows[0]["_cell_modes"] == {"1": "auto"}, "临时 locked 还原为合并前的模式"
    assert merged["rows"] == rows, "多表顶层镜像与首表一致"
    assert "_gt_push_hold" not in json.dumps(merged, ensure_ascii=False)
    assert [(b["field"], b["writer_id"], b["owner_id"], b["reason_code"], b["incoming"], b["kept"])
            for b in gate.blocked_writes] == [
        ("table.cell:end_amount", "update_note_values", "formula_push", "pushed_cell", 111.0, 100.0)]


def test_merge_follows_the_matrix_and_single_table_layout():
    old = {"headers": ["项目", "期末余额"], "rows": [{"label": "库存现金", "values": [100.0]}]}
    new = {"headers": ["项目", "期末余额"], "rows": [{"label": "库存现金", "values": [111.0]}]}
    owned = {(0, 0, 0): OwnedPushCell(table=CASH, field="end_amount", label="库存现金", pushed=100.0)}
    held = merge_holding_pushed_cells(old, new, owned, _gate("generate_notes", old, matrix=_matrix()))
    assert held["rows"][0]["values"] == [100.0] and not held["rows"][0].get("_cell_modes")
    plain = merge_holding_pushed_cells(old, new, owned, _gate("generate_notes", old, matrix=_matrix(())))
    assert plain["rows"][0]["values"] == [111.0], "矩阵没声明该字段归推送 ⇒ 按模板绑定合并"
    gate = _gate("generate_notes", old, matrix=_matrix())
    same = merge_holding_pushed_cells(old, copy.deepcopy(old), owned, gate)
    assert same["rows"][0]["values"] == [100.0] and gate.blocked_writes == [], "值相同不回报"
