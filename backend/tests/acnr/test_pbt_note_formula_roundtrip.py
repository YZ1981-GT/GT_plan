# Feature: acnr-consumer-wiring, Property 20: Formula Dialog Edit Persistence Round-Trip
"""Property + unit tests for NoteFormulaService (P10 / Task 20.3).

**Property 20: Formula Dialog Edit Persistence Round-Trip**

*For any* sequence of formula edits saved via ``NoteFormulaService.save_many``,
reloading the same note section via ``list_by_section`` SHALL return exactly the
persisted set (no loss, no silent regeneration) — i.e. save→reload is an identity
on the (normalized) formula set. This is the service-level correctness backing the
``NoteFormulaDialog`` load/edit/persist fix.

**Validates: Requirements 15.1, 15.2, 15.4**

Testing framework: pytest + Hypothesis (max_examples>=100 for the round-trip property).

Test double strategy (no real DB — round-trip validated on the service contract):
- A real (unattached) ``DisclosureNote`` mapped instance holds ``table_data`` and is
  mutated in place by ``save_many`` (so ``flag_modified`` behaves as in production).
- ``_FakeDB.execute`` returns a result whose ``scalar_one_or_none`` yields that same
  note object on every call → the in-memory ``table_data`` persists across
  save→reload, exactly modelling the (project_id, year, note_section) row.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.models.report_models import DisclosureNote  # noqa: E402
from app.services.note_formula_service import (  # noqa: E402
    NoteFormulaService,
    _USER_FORMULAS_KEY,
    _VALID_CATEGORIES,
)


# ---------------------------------------------------------------------------
# Test doubles: in-memory DisclosureNote + fake async session
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeDB:
    """Minimal AsyncSession stand-in: execute → same note; flush → no-op.

    Returning the *same* note instance on every ``execute`` models the single
    (project_id, year, note_section) row and lets ``table_data`` mutations from
    ``save_many`` survive into the subsequent ``list_by_section`` reload.
    """

    def __init__(self, note: DisclosureNote | None):
        self._note = note
        self.flush_calls = 0

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._note)

    async def flush(self):
        self.flush_calls += 1


def _make_note(table_data: dict | None) -> DisclosureNote:
    """Build a real (unattached) mapped DisclosureNote so flag_modified works."""
    return DisclosureNote(
        project_id=uuid.uuid4(),
        year=2025,
        note_section="五、3",
        section_title="应收账款",
        table_data=table_data,
        is_deleted=False,
    )


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Hypothesis strategies — random formula records (target/formula/description/category)
# ---------------------------------------------------------------------------

# 无空白安全字符集（strip 后仍非空，保证 formula 生成即有效，不被当空行过滤）
_SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-'(),.:期末余额审定合计"

# category 混入合法值与非法值，验证归一化在 round-trip 上稳定（非法→auto_calc）
_CATEGORY_ST = st.one_of(
    st.sampled_from(_VALID_CATEGORIES),
    st.sampled_from(["", "bogus", "logic", None]),
)


@st.composite
def _formula_record(draw) -> dict:
    """生成一条带非空 formula 的公式记录（附随机 target/description/category/source）。"""
    return {
        "target": draw(st.text(alphabet=_SAFE, min_size=0, max_size=10)),
        # formula 非空（min_size>=1 且字符集无空白）→ 归一化后必留存
        "formula": draw(st.text(alphabet=_SAFE, min_size=1, max_size=24)),
        "description": draw(st.text(alphabet=_SAFE, min_size=0, max_size=20)),
        "category": draw(_CATEGORY_ST),
        "source": draw(st.text(alphabet=_SAFE, min_size=0, max_size=10)),
        # 混入前端本地态字段，验证被剔除
        "_editing": draw(st.booleans()),
    }


# ---------------------------------------------------------------------------
# Property 20 — save→reload identity
# ---------------------------------------------------------------------------


class TestProperty20RoundTrip:
    """Property 20: save_many(...) 后 list_by_section(...) 返回同一持久集。"""

    @given(records=st.lists(_formula_record(), min_size=1, max_size=12))
    @settings(max_examples=100)
    def test_save_reload_is_identity(self, records: list[dict]):
        """save→reload 恒等：list_by_section == save_many 返回的持久化集。

        起始 table_data 无 _user_formulas（模拟首次编辑），保存后重载必须
        返回逐字节相同的归一化集（无丢失、无静默重生成）。
        """
        svc = NoteFormulaService()
        # 起始态带 generator 预览遗留 _formulas，验证保存后 reload 不回退预览
        note = _make_note({"_formulas": {"0:1": {"expression": "SUM(x)"}}})
        db = _FakeDB(note)

        saved = _run(svc.save_many(db, note.project_id, 2025, "五、3", records))
        reloaded = _run(svc.list_by_section(db, note.project_id, 2025, "五、3"))

        # 核心恒等：重载结果与持久化结果完全一致
        assert reloaded == saved
        # 至少一条有效（generator 保证 formula 非空）→ 走已保存集而非预览
        assert len(reloaded) >= 1
        # 持久化落在 _user_formulas key（复用 table_data，无迁移）
        assert note.table_data[_USER_FORMULAS_KEY] == saved

    @given(records=st.lists(_formula_record(), min_size=1, max_size=8))
    @settings(max_examples=100)
    def test_reload_normalized_shape_stable(self, records: list[dict]):
        """重载集每条只含持久化字段，且 category 恒为合法值（归一化稳定）。"""
        svc = NoteFormulaService()
        note = _make_note({})
        db = _FakeDB(note)

        saved = _run(svc.save_many(db, note.project_id, 2025, "五、3", records))
        reloaded = _run(svc.list_by_section(db, note.project_id, 2025, "五、3"))

        assert reloaded == saved
        expected_keys = {"target", "formula", "description", "category", "source", "type"}
        for rec in reloaded:
            assert set(rec.keys()) == expected_keys
            assert "_editing" not in rec  # 前端本地态被剔除
            assert rec["category"] in _VALID_CATEGORIES
            assert rec["formula"].strip()  # 无空行

    @given(records=st.lists(_formula_record(), min_size=1, max_size=6))
    @settings(max_examples=100)
    def test_idempotent_double_save(self, records: list[dict]):
        """幂等：连续两次保存同一集，reload 结果不变（覆盖式写入语义）。"""
        svc = NoteFormulaService()
        note = _make_note({})
        db = _FakeDB(note)

        first = _run(svc.save_many(db, note.project_id, 2025, "五、3", records))
        # 用第一次归一化结果再次保存，应恒等
        second = _run(svc.save_many(db, note.project_id, 2025, "五、3", first))
        reloaded = _run(svc.list_by_section(db, note.project_id, 2025, "五、3"))

        assert first == second == reloaded


# ---------------------------------------------------------------------------
# Unit tests — specific behaviours behind the dialog fix
# ---------------------------------------------------------------------------


class TestListBySection:
    """list_by_section — onOpen 加载（Req 15.1）。"""

    def test_saved_user_formulas_take_priority(self):
        """已保存 _user_formulas 非空 → 直接返回（不回退 generator 预览）。"""
        svc = NoteFormulaService()
        note = _make_note(
            {
                "_user_formulas": [
                    {"target": "R1", "formula": "TB('1122','审定数')", "category": "auto_calc"}
                ],
                # 同时存在 generator 预览，必须被 _user_formulas 覆盖
                "_formulas": {"0:1": {"expression": "SUM(preview)"}},
            }
        )
        db = _FakeDB(note)
        out = _run(svc.list_by_section(db, note.project_id, 2025, "五、3"))

        assert len(out) == 1
        assert out[0]["formula"] == "TB('1122','审定数')"

    def test_falls_back_to_formulas_preview_when_no_user_set(self):
        """无 _user_formulas → 回退 generator 预览（_formulas dict 归一化）。"""
        svc = NoteFormulaService()
        note = _make_note(
            {"_formulas": {"2:3": {"expression": "SUM(A1:A2)", "description": "小计", "category": "auto_calc"}}}
        )
        db = _FakeDB(note)
        out = _run(svc.list_by_section(db, note.project_id, 2025, "五、3"))

        assert len(out) == 1
        assert out[0]["target"] == "2:3"
        assert out[0]["formula"] == "SUM(A1:A2)"

    def test_empty_when_note_missing(self):
        """note 不存在 → 空列表（弹窗不阻断）。"""
        svc = NoteFormulaService()
        db = _FakeDB(None)
        out = _run(svc.list_by_section(db, uuid.uuid4(), 2025, "五、3"))
        assert out == []

    def test_empty_when_no_table_data(self):
        svc = NoteFormulaService()
        note = _make_note(None)
        db = _FakeDB(note)
        out = _run(svc.list_by_section(db, note.project_id, 2025, "五、3"))
        assert out == []


class TestSaveMany:
    """save_many — 编辑持久化（Req 15.2）+ 跨重开存活。"""

    def test_edit_persists_across_reopen(self):
        """保存编辑集后，独立 reload（模拟弹窗重开）返回同一集。"""
        svc = NoteFormulaService()
        note = _make_note({})
        db = _FakeDB(note)

        records = [
            {"target": "R1", "formula": "TB('1122','审定数')", "description": "应收合计", "category": "auto_calc", "source": "TB"},
            {"target": "R2", "formula": "NOTE('五、3','合计','期末')", "description": "", "category": "logic_check", "source": ""},
        ]
        saved = _run(svc.save_many(db, note.project_id, 2025, "五、3", records))

        # 模拟"关闭再打开"：新建 service + 新 fake db 包同一 note（table_data 已被写入）
        svc2 = NoteFormulaService()
        db2 = _FakeDB(note)
        reopened = _run(svc2.list_by_section(db2, note.project_id, 2025, "五、3"))

        assert reopened == saved
        assert [r["formula"] for r in reopened] == [
            "TB('1122','审定数')",
            "NOTE('五、3','合计','期末')",
        ]

    def test_empty_rows_filtered(self):
        """空 formula 行（含纯空白）被过滤，不入库。"""
        svc = NoteFormulaService()
        note = _make_note({})
        db = _FakeDB(note)
        records = [
            {"target": "R1", "formula": "TB('1001','审定数')", "category": "auto_calc"},
            {"target": "", "formula": "", "category": "auto_calc"},  # 空行
            {"target": "R3", "formula": "   ", "category": "auto_calc"},  # 纯空白
        ]
        saved = _run(svc.save_many(db, note.project_id, 2025, "五、3", records))
        assert len(saved) == 1
        assert saved[0]["formula"] == "TB('1001','审定数')"

    def test_local_editing_field_stripped(self):
        """前端本地态 _editing 不进入持久化 shape。"""
        svc = NoteFormulaService()
        note = _make_note({})
        db = _FakeDB(note)
        saved = _run(
            svc.save_many(
                db, note.project_id, 2025, "五、3",
                [{"target": "R1", "formula": "SUM(x)", "category": "auto_calc", "_editing": True}],
            )
        )
        assert "_editing" not in saved[0]

    def test_invalid_category_normalized(self):
        """非法 category → 归一化为 auto_calc。"""
        svc = NoteFormulaService()
        note = _make_note({})
        db = _FakeDB(note)
        saved = _run(
            svc.save_many(
                db, note.project_id, 2025, "五、3",
                [{"target": "R1", "formula": "SUM(x)", "category": "not-a-category"}],
            )
        )
        assert saved[0]["category"] == "auto_calc"

    def test_flush_called_not_commit(self):
        """service 只 flush（router 统一 commit）。"""
        svc = NoteFormulaService()
        note = _make_note({})
        db = _FakeDB(note)
        _run(svc.save_many(db, note.project_id, 2025, "五、3", [{"formula": "SUM(x)"}]))
        assert db.flush_calls == 1

    def test_missing_note_raises_value_error(self):
        """附注章节不存在 → ValueError（router 转 404/400）。"""
        svc = NoteFormulaService()
        db = _FakeDB(None)
        raised = False
        try:
            _run(svc.save_many(db, uuid.uuid4(), 2025, "五、3", [{"formula": "SUM(x)"}]))
        except ValueError:
            raised = True
        assert raised
