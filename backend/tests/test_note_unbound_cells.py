"""附注「没有绑定 ≠ 人工」（spec note-pull-followup-closure R5 / ADR-5）。

生成不再把没有 binding / binding 为 manual 且没有预填值的格标 manual（``_cell_meta.unbound``，生成用例见
``test_disclosure_note_formula_baseline`` / ``test_disclosure_engine_v2``）；这里钉住下游：重新生成合并与刷新不拿空值覆盖
这类格已写入的值，推送照常写入；存量修复工具只改回「manual、值为空、无预填、binding 没有自动来源」的格。
"""
from __future__ import annotations

import asyncio
import contextlib
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.report_models import ContentType, DisclosureNote
from app.services.disclosure_engine import DisclosureEngine, binding_cell_unbound
from app.services.formula_push.policy import decide_note
from app.services.note_cell_merge import merge_row_preserving_cell_modes

_FIX_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fix" / "fix_note_manual_placeholders.py"
_spec = importlib.util.spec_from_file_location("fix_note_manual_placeholders", _FIX_PATH)
FIX = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FIX)  # type: ignore[union-attr]

TB = {"source": "trial_balance", "field": "audited", "account_codes": ["1001"], "mode": "auto"}
TODO = {"source": "manual", "mode": "manual", "todo": "待审计师手工填或从底稿同步"}
BINDING = {"tables": [{
    "header_normalize": [{"semantic": "row_label"}, {"semantic": "closing_balance"}, {"semantic": "opening_balance"}],
    "rows": {
        "银行存款": {"binding": {"closing_balance": TB, "opening_balance": TODO}},
        "预填行": {"binding": {"closing_balance": {**TODO, "manual_value": 5.0}}},
    },
}]}


def test_binding_cell_unbound_truth_table():
    assert binding_cell_unbound(None) is True
    assert binding_cell_unbound({}) is True and binding_cell_unbound({"mode": "auto"}) is True, "没有取数来源"
    assert binding_cell_unbound(TODO) is True
    assert binding_cell_unbound({**TODO, "manual_value": ""}) is True
    assert binding_cell_unbound({**TODO, "manual_value": 0}) is False, "预填 0 也是预填值"
    assert binding_cell_unbound({**TODO, "manual_value": 5}) is False
    assert binding_cell_unbound({"source": "manual", "mode": "auto"}) is True, "来源 manual 没有预填 = 没有值可取"
    assert binding_cell_unbound({**TB, "mode": "manual"}) is True, "binding 声明 manual 且没有预填值"
    assert binding_cell_unbound(TB) is False
    assert binding_cell_unbound({"source": "trial_balance"}) is False, "mode 缺省按 auto"


# ── 重新生成合并 ─────────────────────────────────────────────────────────────


def test_merge_keeps_written_value_of_unbound_auto_cell():
    old = {"label": "银行存款", "values": [100.0, 7.0], "_cell_modes": {"0": "auto"}, "_cell_meta": {}}
    new = {"label": "银行存款", "values": [150.0, None], "_cell_modes": {"0": "auto"},
           "_cell_meta": {"0": {"semantic": "closing_balance", "binding_id": "b0"},
                          "1": {"semantic": "opening_balance", "binding_id": "b1", "unbound": True}}}
    merged = merge_row_preserving_cell_modes(old, new)
    assert merged["values"] == [150.0, 7.0], "有绑定的自动格取新值；没有绑定的格保留推送 / 公式写入的旧值"
    assert merged["_cell_meta"]["1"]["unbound"] is True and "unbound" not in merged["_cell_meta"]["0"]


def test_merge_takes_new_value_once_binding_exists_and_clears_flag():
    old = {"label": "银行存款", "values": [None, 7.0], "_cell_modes": {},
           "_cell_meta": {"1": {"manual_value": None, "semantic": "opening_balance", "binding_id": None, "unbound": True}}}
    new = {"label": "银行存款", "values": [None, 9.0], "_cell_modes": {"1": "auto"},
           "_cell_meta": {"1": {"semantic": "opening_balance", "binding_id": "b1"}}}
    merged = merge_row_preserving_cell_modes(old, new)
    assert merged["values"][1] == 9.0 and "unbound" not in merged["_cell_meta"]["1"]


def test_merge_still_keeps_manual_cells():
    old = {"label": "x", "values": [3.0], "_cell_modes": {"0": "manual"}, "_cell_meta": {}}
    new = {"label": "x", "values": [None], "_cell_modes": {}, "_cell_meta": {"0": {"unbound": True}}}
    assert merge_row_preserving_cell_modes(old, new)["values"] == [3.0]


def test_merge_unbound_flag_only_guards_blank_overwrite():
    """unbound 只挡「拿空值覆盖」：生成给了值就用新值，标记随之去掉。"""
    old = {"label": "x", "values": [7.0], "_cell_modes": {}, "_cell_meta": {}}
    new = {"label": "x", "values": [9.0], "_cell_modes": {}, "_cell_meta": {"0": {"unbound": True}}}
    merged = merge_row_preserving_cell_modes(old, new)
    assert merged["values"] == [9.0] and "unbound" not in merged["_cell_meta"]["0"]


def test_push_writes_into_unbound_cell_but_keeps_manual():
    assert decide_note(formula_value=5, current_value=None, cell_mode=None).action == "write"
    assert decide_note(formula_value=5, current_value=None, cell_mode="manual").action == "keep_manual"


# ── 刷新 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("skip_manual", [True, False])
async def test_refill_does_not_blank_unbound_cells(skip_manual):
    db = MagicMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    eng = DisclosureEngine(db)
    td = {"headers": ["项目", "期末余额", "期初余额"], "rows": [{
        "label": "银行存款", "values": [100.0, 7.0], "_cell_modes": {"0": "auto"},
        "_cell_meta": {"0": {"semantic": "closing_balance"}, "1": {"semantic": "opening_balance", "unbound": True}}}]}
    note = MagicMock(spec=DisclosureNote)
    note.note_section, note.content_type, note.table_data = "五、1", ContentType.table, td
    result = MagicMock()
    result.scalars.return_value.all.return_value = [note]
    db.execute = AsyncMock(return_value=result)

    async def dispatch(cell, ctx):
        return 999.0 if cell is TB else cell.get("manual_value")

    with (patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock),
          patch("app.services.note_template_bindings_loader.get_binding_for_section", return_value=BINDING),
          patch("app.services.note_source_resolvers.dispatch_resolver", side_effect=dispatch),
          patch("sqlalchemy.orm.attributes.flag_modified")):
        report = await eng.refill_sections(uuid4(), 2025, ["五、1"], skip_manual=skip_manual)
    assert td["rows"][0]["values"] == [999.0, 7.0], "期初是 manual 无预填的 binding：不拿空值覆盖推送写入的 7"
    assert report.cells_updated == 1


# ── 存量修复工具 ─────────────────────────────────────────────────────────────


def _note() -> dict:
    def row(label, values, modes, meta=None, **kw):
        return {"label": label, "values": values, "_cell_modes": modes, "_cell_meta": meta or {}, **kw}

    rows = [
        row("银行存款", [None, None], {"0": "manual", "1": "manual"}),       # 0 列 binding 自动来源（用户改的）/ 1 列占位
        row("其他", [None, None], {"0": "manual", "1": "manual"}),          # 没有 binding 行
        row("填过", [3.0, None], {"0": "manual"}),                          # 有值
        row("备份", [None, None], {"0": "manual"}, {"0": {"manual_value": 4.0}}),  # 有备份值
        row("预填行", [None, None], {"0": "manual"}),                        # binding 有预填值
        row("合计", [None, None], {"0": "manual"}, is_total=True),
    ]
    return {"_tables": [{"name": "t", "rows": rows}], "rows": copy.deepcopy(rows)}


def test_fix_tool_plans_only_placeholder_cells():
    with patch("app.services.note_template_bindings_loader.get_binding_for_section", return_value=BINDING):
        changes, skipped = FIX.plan_note(_note(), "五、1")
    own = sorted((c["label"], c["col"], c["kind"]) for c in changes if c["table"] == 0)
    assert own == [("其他", 0, "无 binding"), ("其他", 1, "无 binding"), ("银行存款", 1, "manual 无预填")]
    assert sorted((c["label"], c["col"]) for c in changes if c["table"] == "rows") == [
        ("其他", 0), ("其他", 1), ("银行存款", 1)]
    assert all(c["mirror"] for c in changes if c["table"] == "rows"), "顶层 rows 是首表镜像：同样改、报告里单列"
    assert skipped == {"有值（人工填过）": 1, "有预填 / 备份值": 1, "binding 有取数来源 / 预填值（人工标的）": 2}


def test_fix_tool_apply_removes_manual_and_marks_unbound():
    td = _note()
    before = copy.deepcopy(td)
    with patch("app.services.note_template_bindings_loader.get_binding_for_section", return_value=BINDING):
        changes, _ = FIX.plan_note(td, "五、1")
    out = FIX.apply_plan(td, changes)
    assert td == before, "入参不动"
    for rows in (out["_tables"][0]["rows"], out["rows"]):
        assert rows[0]["_cell_modes"] == {"0": "manual"} and rows[0]["_cell_meta"]["1"]["unbound"] is True
        assert rows[1]["_cell_modes"] == {} and rows[1]["_cell_meta"]["0"]["unbound"] is True
        assert rows[2]["_cell_modes"] == {"0": "manual"} and rows[5]["_cell_modes"] == {"0": "manual"}
    with patch("app.services.note_template_bindings_loader.get_binding_for_section", return_value=BINDING):
        assert FIX.plan_note(out, "五、1")[0] == [], "幂等：改过一次后再跑没有可改的格"


def test_fix_tool_apply_requires_test_project(monkeypatch):
    run = AsyncMock(return_value=0)
    monkeypatch.setattr(FIX, "run", run)
    with pytest.raises(SystemExit):
        FIX.main(["--all", "--apply"])
    run.assert_not_called()


class _FakeDb:
    """``run()`` 的假会话：第 1 条查项目、第 2 条查附注，之后都是更新语句（记下来）。"""

    def __init__(self, projects, notes):
        self.projects, self.notes, self.updates, self.commits, self._n = projects, notes, [], 0, 0

    async def execute(self, stmt):
        self._n += 1
        if self._n == 1:
            return SimpleNamespace(all=lambda: self.projects)
        if self._n == 2:
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.notes))
        self.updates.append(stmt)
        return SimpleNamespace()

    async def commit(self):
        self.commits += 1

    def session(self):
        @contextlib.asynccontextmanager
        async def _cm():
            yield self
        return _cm()


@pytest.mark.parametrize("name, writes", [("某医药公司_2025", False), ("【测试】甲", True)])
def test_fix_tool_run_writes_only_test_projects_with_backup(tmp_path, monkeypatch, name, writes):
    note = SimpleNamespace(id=uuid4(), note_section="五、1", year=2025, table_data=_note())
    db = _FakeDb([(uuid4(), name)], [note])
    monkeypatch.setattr(FIX, "BACKUP_DIR", tmp_path)
    with (patch("app.core.database.async_session", db.session),
          patch("app.services.note_template_bindings_loader.get_binding_for_section", return_value=BINDING)):
        assert asyncio.run(FIX.run(None, None, True)) == 0
    backups = list(tmp_path.glob("note_manual_placeholders_*.json"))
    assert (len(db.updates), db.commits, len(backups)) == ((1, 1, 1) if writes else (0, 0, 0)), "真实项目只出报告"
    assert note.table_data == _note(), "内存里的原对象不动"
    if writes:
        saved = json.loads(backups[0].read_text(encoding="utf-8"))
        assert saved == [{"note_id": str(note.id), "note_section": "五、1", "year": 2025, "table_data": _note()}]
        written = db.updates[0].compile().params["table_data"]
        with patch("app.services.note_template_bindings_loader.get_binding_for_section", return_value=BINDING):
            assert written == FIX.apply_plan(_note(), FIX.plan_note(_note(), "五、1")[0])
