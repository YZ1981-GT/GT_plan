"""附注刷新从底稿取数（spec note-pull-header-formula-closure R2 / 任务 3~4）。

纯函数 + 打桩编排（不连库）；真库路径见 ``test_note_workpaper_pull_service_pg.py``。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from app.services import note_workpaper_pull_service as svc
from app.services.formula_push.results import PushItem, RunResult

PID = uuid.uuid4()


def test_shared_section_maps_to_every_workpaper():
    """共用章节：国企 八、42 其他应付款由 K3 / L2 / M1 三张底稿推。"""
    assert sorted(svc.codes_by_section("soe", ["八、42"])["八、42"]) == ["K3", "L2", "M1"]


def test_variant_picks_its_own_sections():
    soe, listed = svc.codes_by_section("soe", None), svc.codes_by_section("listed", None)
    assert soe["八、5"] == ["D2"] and listed["五、5"] == ["D2"]
    assert not any(s.startswith("五、") for s in soe) and not any(s.startswith("八、") for s in listed)


def test_unknown_section_is_reported_with_no_workpaper():
    assert svc.codes_by_section("soe", ["八、999"]) == {"八、999": []}


def test_summarize_push_counts_per_note_section():
    items = [
        PushItem("D2.note.main", "note", "note", "note://八、5/（1）按账龄披露应收账款/合 计.end", "write"),
        PushItem("D2.note.main", "note", "note", "note://八、5/（1）按账龄披露应收账款/合 计.prior", "unchanged"),
        PushItem("D2.note.main", "note", "note", "note://八、5/x/y.end", "keep_manual"),
        PushItem("D2.note.sub", "note", "note", "note://八、5/x/z.end", "skipped", reason="附注表缺少「期末」列"),
        PushItem("D2.note.sub", "note", "note", "note://八、5/x/w.end", "skipped", reason="附注表缺少「期末」列"),
        PushItem("E1.note.main", "note", "note", "note://八、1/货币资金/库存现金.end", "write"),
        PushItem("D2.tb", "source", "workpaper", "wp://D2/D2-1/D2-adj-tb-amount", "write"),
    ]
    result = RunResult(project_id=PID, year=2025, trigger="manual", items=items)
    per = svc.summarize_push(result, ["八、5"])
    assert per == {"八、5": {"written": 1, "unchanged": 1, "kept": 1, "skipped": 2,
                            "reasons": ["附注表缺少「期末」列"]}}


def test_manual_value_count_only_counts_filled_manual_cells():
    """旧生成器标了一片空 manual 格（重药安徽 八、5）不算人工填写；有值的 manual / locked 才算。"""
    td = {"_tables": [
        {"rows": [{"values": [None, None], "_cell_modes": {"0": "manual", "1": "manual"}}]},
        {"rows": [
            {"values": [100.0, "说明", 0], "_cell_modes": {"0": "manual", "1": "locked", "2": "manual"}},
            {"values": [5.0], "_cell_modes": {"0": "auto"}},
        ]},
    ]}
    assert svc.manual_value_count(td) == 2
    assert svc.manual_value_count({"rows": [{"values": [1], "_cell_modes": {"0": "manual"}}]}) == 1
    assert svc.manual_value_count(None) == 0


@dataclass
class _Db:
    project: object | None
    got: list = field(default_factory=list)

    async def get(self, model, key):
        self.got.append(key)
        return self.project


@pytest.fixture
def stubs(monkeypatch):
    calls = {}

    async def fake_push(db, project_id, year, codes, user_id):
        calls["push"] = (project_id, year, list(codes), user_id)
        return RunResult(project_id=project_id, year=year, trigger="manual", items=[
            PushItem("K3.note.main", "note", "note", "note://八、42/其他应付款/其他应付款.end", "write"),
        ]), None

    async def fake_marks(db, project_id, year, sections):
        calls["marks"] = list(sections)
        return {"synced": 0, "skipped": 0, "skipped_never_synced": len(sections)}

    async def fake_ids(db, project_id, codes):
        return {c: f"wp-{c}" for c in codes}

    async def fake_standards(db, project_id):
        return ["soe_standalone"]

    async def fake_formulas(db, project_id, year, sections):
        calls["formulas"] = list(sections)
        return {s: {"updated": 2, "skipped": 0, "error": None} for s in sections[:1]}

    async def fake_other(db, project_id, year, exclude):
        calls["other"] = sorted(exclude)
        return {"九、9": {"exists": True, "synced_before": False, "manual_values": 3}}

    monkeypatch.setattr(svc, "_push", fake_push)
    monkeypatch.setattr(svc, "_mark_synced_sections", fake_marks)
    monkeypatch.setattr(svc, "_other_section_states", fake_other)
    monkeypatch.setattr(svc, "_workpaper_ids", fake_ids)
    monkeypatch.setattr(svc, "_applicable_standards", fake_standards)
    monkeypatch.setattr(svc, "_apply_note_formulas", fake_formulas)
    return calls


@pytest.mark.asyncio
async def test_pull_pushes_exactly_the_section_workpapers(stubs):
    user = uuid.uuid4()
    out = await svc.pull_sections(_Db(SimpleNamespace(template_type="soe")), PID, 2025,
                                  sections=["八、42"], user_id=user)
    assert stubs["push"] == (PID, 2025, ["K3", "L2", "M1"], user)
    assert stubs["marks"] == ["八、42"]
    assert stubs["formulas"] == ["八、42"], "推送后对刷新的章节执行附注公式"
    assert out["formulas"] == {"updated": 2, "sections": ["八、42"], "errors": [], "differs": 0}
    row = out["sections"][0]
    assert row["section"] == "八、42" and row["written"] == 1 and row["formula_updated"] == 2
    assert row["wp_ids"] == {"K3": "wp-K3", "L2": "wp-L2", "M1": "wp-M1"}
    assert out["push"]["ran"] is True and out["push"]["written"] == 1
    assert out["applicable_standards"] == ["soe_standalone"] and out["variant"] == "soe"
    assert "other" not in stubs and out["section_states"] == {}, "单章节刷新：注册表外的章节不在本次范围"


@pytest.mark.asyncio
async def test_listed_project_uses_listed_sections(stubs):
    out = await svc.pull_sections(_Db(SimpleNamespace(template_type="listed")), PID, 2025,
                                  sections=None, user_id=None)
    assert all(r["section"].startswith("五、") for r in out["sections"])
    assert "D2" in stubs["push"][2]
    # 全部刷新：其余章节的状态也回给前端（离屏同步写注册表外的章节时判「已有人工填写不覆盖」，R1.1）
    assert stubs["other"] == sorted(r["section"] for r in out["sections"])
    assert out["section_states"]["九、9"] == {"exists": True, "synced_before": False, "manual_values": 3}


@pytest.mark.asyncio
async def test_missing_project_is_lookup_error(stubs):
    with pytest.raises(LookupError):
        await svc.pull_sections(_Db(None), PID, 2025, sections=None, user_id=None)


@pytest.mark.asyncio
async def test_push_refusal_is_reported_not_raised(monkeypatch):
    """推送引擎拒绝（审计年度不符）→ 回原因，章节标记照常做（真实 ``_push``，只打桩引擎）。"""
    from app.services.formula_push import engine

    async def marks(db, project_id, year, sections):
        return {"synced": 0, "skipped": 0, "skipped_never_synced": len(sections)}

    async def nothing(*_a, **_k):
        return {}

    async def refuse(*a, **k):
        raise engine.PushActionError("公式推送只作用于项目审计年度（2026），本次为 2025 年度，未推送")

    monkeypatch.setattr(svc, "_mark_synced_sections", marks)
    monkeypatch.setattr(svc, "_workpaper_ids", nothing)
    monkeypatch.setattr(svc, "_applicable_standards", nothing)
    monkeypatch.setattr(svc, "_apply_note_formulas", nothing)
    monkeypatch.setattr(engine, "run_and_commit", refuse)
    out = await svc.pull_sections(_Db(SimpleNamespace(template_type="soe")), PID, 2025,
                                  sections=["八、5"], user_id=None)
    assert out["push"]["ran"] is False
    assert "审计年度" in out["push"]["error"] and out["push"]["warnings"] == [out["push"]["error"]]
    assert out["skipped_never_synced"] == 1


class _NestedDb:
    """只给保存点的桩：记录进 / 出与是否带异常退出（异常退出 = 回滚这一节）。"""

    def __init__(self):
        self.rolled_back = 0

    def begin_nested(self):
        db = self

        class _Sp:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                if exc_type is not None:
                    db.rolled_back += 1
                return False

        return _Sp()


@pytest.mark.asyncio
async def test_note_formulas_run_per_section_and_one_failure_does_not_stop_others(monkeypatch):
    from app.services import note_formula_generator
    from app.services.formula_settings import note_settings

    seen, shared_ids = [], set()

    async def fake_execute(db, project_id, year, section, *, cross_data=None, **_kw):
        seen.append(section)
        shared_ids.add(id(cross_data))
        if section == "八、2":
            raise RuntimeError("公式表达式坏了")
        return {"executed": 2, "updated": 1 if section == "八、1" else 0, "results": [
            {"status": "ok"}, {"status": "skipped", "reason": "引用的单元格都没有数"}]}

    async def no_materialize(*_a, **_k):
        return None

    monkeypatch.setattr(note_formula_generator, "execute_note_formulas", fake_execute)
    monkeypatch.setattr(note_settings, "materialize_quietly", no_materialize)
    db = _NestedDb()
    out = await svc._apply_note_formulas(db, PID, 2025, ["八、1", "八、2", "八、3"])
    assert seen == ["八、1", "八、2", "八、3"], "一节失败不影响其余章节"
    assert db.rolled_back == 1, "失败的那一节在自己的保存点里回滚"
    assert len(shared_ids) == 1, "跨表取数多章节共用一次预载"
    assert out["八、1"] == {"updated": 1, "skipped": 1, "differs": 0, "error": None}
    assert out["八、2"]["error"].startswith("RuntimeError") and out["八、3"]["updated"] == 0


@pytest.mark.asyncio
async def test_push_crash_is_reported_not_raised(monkeypatch):
    from app.services.formula_push import engine

    async def boom(*a, **k):
        raise RuntimeError("连接中断")

    monkeypatch.setattr(engine, "run_and_commit", boom)
    result, error = await svc._push(object(), PID, 2025, ["D2"], None)
    assert result is None and "连接中断" in error
