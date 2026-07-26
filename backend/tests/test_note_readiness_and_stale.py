"""附注模块联动复盘 P0-1 / P0-3 / P1-1 单测（纯逻辑，无 DB）。

覆盖：
- ``note_readiness_service`` 的章节↔底稿映射（真源 = 生成的 registry JSON）
- ``latest_findings_by_section`` 按 severity 聚合 + fail-open
- ``build_readiness`` 的 summary 口径（needs_sync / empty / stale）
- ``mark_notes_stale_for_report_change`` 粒度化（有 linkage 只标关联章节 / 无 linkage 回退全量）
- ``report_note_references`` 第 3 级勾稽回退（预设库）
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import note_readiness_service as nrs


# ---------------------------------------------------------------------------
# 章节 ↔ 底稿映射（registry 真源）
# ---------------------------------------------------------------------------


def test_section_workpaper_map_uses_authoritative_sections():
    """registry 真源必须给出权威章节号（D1=五、4 / D2=五、5），

    而非陈旧的 DEFAULT_WP_MAPPING（D1→五、2 / D2→五、3）。
    """
    m = nrs.section_workpaper_map()
    assert m.get("五、4") == ["D1"], m.get("五、4")
    assert m.get("五、5") == ["D2"]
    assert m.get("八、4") == ["D1"]
    assert m.get("五、1") == ["E1"]
    # 老编号不应出现在 D1/D2 映射上
    assert "D1" not in m.get("五、2", [])
    assert "D2" not in m.get("五、3", [])


def test_section_workpaper_map_supports_multiple_workpapers():
    """一个章节可由多张底稿维护（K1 其他应收款 五、8 亦被 G2 推送）。"""
    m = nrs.section_workpaper_map()
    codes = m.get("五、8", [])
    assert "K1" in codes and "G2" in codes, codes


def test_section_sheet_map_only_registers_real_sheet_names():
    """sheet 名缺失时不臆造（值必须非空字符串）。"""
    s = nrs.section_sheet_map()
    assert all(isinstance(v, str) and v for v in s.values())
    assert "五、4" in s  # D1 有真实 tab 名


# ---------------------------------------------------------------------------
# findings 聚合
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDb:
    def __init__(self, row=None, raises=False):
        self._row = row
        self._raises = raises

    async def execute(self, *_a, **_kw):
        if self._raises:
            raise RuntimeError("db down")
        return _FakeResult(self._row)


def test_latest_findings_groups_by_section_and_severity():
    findings = [
        {"note_section": "五、1", "severity": "error"},
        {"note_section": "五、1", "severity": "warning"},
        {"note_section": "五、4", "severity": "warning"},
        {"note_section": "", "severity": "error"},          # 无章节 → 忽略
        "bad-entry",                                          # 非 dict → 忽略
    ]
    ts = SimpleNamespace(isoformat=lambda: "2026-07-26T00:00:00+00:00")
    db = _FakeDb(row=(findings, ts))
    out, at = asyncio.run(nrs.latest_findings_by_section(db, uuid4(), 2025))
    assert out["五、1"] == {"error": 1, "warning": 1}
    assert out["五、4"] == {"error": 0, "warning": 1}
    assert "" not in out
    assert at == "2026-07-26T00:00:00+00:00"


def test_latest_findings_fail_open_on_db_error():
    out, at = asyncio.run(nrs.latest_findings_by_section(_FakeDb(raises=True), uuid4(), 2025))
    assert out == {} and at is None


def test_latest_findings_no_run_returns_empty():
    out, at = asyncio.run(nrs.latest_findings_by_section(_FakeDb(row=None), uuid4(), 2025))
    assert out == {} and at is None


# ---------------------------------------------------------------------------
# build_readiness summary 口径
# ---------------------------------------------------------------------------


def _note(section, *, has_rows=True, stale=False, stale_source=None, last_sync_at=None):
    table = {"rows": [{"label": "x", "values": [1]}]} if has_rows else {"rows": []}
    return SimpleNamespace(
        id=uuid4(),
        note_section=section,
        section_title=f"{section} 标题",
        account_name="",
        table_data=table,
        text_content=None,
        is_empty=False,
        is_stale=stale,
        stale_source=stale_source,
        last_sync_at=last_sync_at,
        last_sync_source=None,
        last_sync_wp_id=None,
    )


class _ReadinessDb:
    """只为 build_readiness 提供最小 execute 行为（notes / findings / wp_ids）。"""

    def __init__(self, notes):
        self._notes = notes
        self._calls = 0

    async def execute(self, *_a, **_kw):
        self._calls += 1
        if self._calls == 1:  # notes 查询
            notes = self._notes

            class _R:
                def scalars(self):
                    return SimpleNamespace(all=lambda: notes)

            return _R()
        # findings / wp_ids 查询：返回空
        class _R2:
            def fetchone(self):
                return None

            def fetchall(self):
                return []

        return _R2()


def test_build_readiness_summary_counts():
    notes = [
        _note("五、4"),                                   # 有底稿映射 + 未同步
        _note("五、1", last_sync_at=SimpleNamespace(isoformat=lambda: "T")),  # 已同步
        _note("五、999", has_rows=False, stale=True, stale_source="report"),  # 无映射/空/stale
    ]
    data = asyncio.run(nrs.build_readiness(_ReadinessDb(notes), uuid4(), 2025))
    s = data["summary"]
    assert s["total"] == 3
    assert s["empty"] == 1 and s["with_data"] == 2
    assert s["syncable"] == 2            # 五、4 + 五、1 有底稿映射
    assert s["never_synced"] == 1        # 仅 五、4
    assert s["stale"] == 1 and s["stale_report"] == 1
    assert s["validation_ran"] is False
    by_sec = {x["note_section"]: x for x in data["sections"]}
    assert by_sec["五、4"]["needs_sync"] is True
    assert by_sec["五、1"]["needs_sync"] is False
    assert by_sec["五、999"]["wp_codes"] == []


# ---------------------------------------------------------------------------
# P0-3 stale 粒度化
# ---------------------------------------------------------------------------


class _StaleDb:
    def __init__(self, notes):
        self._notes = notes
        self.flushed = 0

    async def execute(self, *_a, **_kw):
        notes = self._notes

        class _R:
            def scalars(self):
                return SimpleNamespace(all=lambda: notes)

        return _R()

    async def flush(self):
        self.flushed += 1


def _linkage_note(section, *, binding_row_code=None):
    row = {"label": "x", "values": [0]}
    if binding_row_code:
        row["_cell_meta"] = {"1": {"binding": {"source": "report", "row_code": binding_row_code}}}
    return SimpleNamespace(
        id=uuid4(),
        note_section=section,
        table_data={"rows": [row]},
        is_stale=False,
        stale_source=None,
    )


def test_mark_stale_only_targets_linked_sections():
    from app.services.report_note_sync_service import ReportNoteSyncService

    linked = _linkage_note("五、1", binding_row_code="BS-002")
    plain = _linkage_note("五、9")
    db = _StaleDb([linked, plain])
    n = asyncio.run(ReportNoteSyncService(db).mark_notes_stale_for_report_change(uuid4(), 2025))
    assert n == 1
    assert linked.is_stale is True and linked.stale_source == "report"
    assert plain.is_stale is False and plain.stale_source is None


def test_mark_stale_respects_changed_row_codes():
    from app.services.report_note_sync_service import ReportNoteSyncService

    a = _linkage_note("五、1", binding_row_code="BS-002")
    b = _linkage_note("五、4", binding_row_code="BS-008")
    db = _StaleDb([a, b])
    n = asyncio.run(
        ReportNoteSyncService(db).mark_notes_stale_for_report_change(
            uuid4(), 2025, changed_row_codes={"BS-008"},
        )
    )
    assert n == 1
    assert b.is_stale is True and a.is_stale is False


def test_mark_stale_falls_back_to_all_when_no_linkage():
    """全项目无任何 linkage 目标 → 保守全量标记，但来源标注为 fallback（可弱化呈现）。"""
    from app.services.report_note_sync_service import ReportNoteSyncService

    notes = [_linkage_note("五、1"), _linkage_note("五、4")]
    db = _StaleDb(notes)
    n = asyncio.run(ReportNoteSyncService(db).mark_notes_stale_for_report_change(uuid4(), 2025))
    assert n == 2
    assert all(x.is_stale and x.stale_source == "report_fallback" for x in notes)


# ---------------------------------------------------------------------------
# P1-1 报表行 → 附注引用：第 3 级勾稽回退
# ---------------------------------------------------------------------------


def test_cross_check_fallback_finds_sections_from_presets():
    from app.routers.report_note_references import find_cross_check_sections_for_row

    # 预设库含形如 ABS(ROW('BS-002')-NOTE('五、1','合计'))<=1 的 logic_check
    hits = find_cross_check_sections_for_row("BS-002")
    assert isinstance(hits, set)
    assert "五、1" in hits, hits


def test_cross_check_fallback_empty_for_unknown_row():
    from app.routers.report_note_references import find_cross_check_sections_for_row

    assert find_cross_check_sections_for_row("ZZ-999") == set()
    assert find_cross_check_sections_for_row("") == set()


@pytest.mark.parametrize("bad", [None, 123, []])
def test_cross_check_fallback_type_safe(bad):
    from app.routers.report_note_references import find_cross_check_sections_for_row

    assert find_cross_check_sections_for_row(bad) == set()  # type: ignore[arg-type]
