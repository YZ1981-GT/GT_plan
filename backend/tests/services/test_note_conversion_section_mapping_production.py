"""生产路径章节映射单测 —— 承接已删除的 ``convert_disclosure_notes_v2`` 全部断言.

spec: soe-listed-note-conversion-correctness / Task 10（Requirements 6.1, 6.3）

------------------------------------------------------------------------------
本文件为什么存在
------------------------------------------------------------------------------

Task 10 裁决为**删除** ``convert_disclosure_notes_v2`` / ``preview_conversion_v2``
（生产零调用方的孤儿），而 Requirement 6.3 明令「其 11 个测试的断言 SHALL 同步
迁移到生产路径的测试上，不得直接删测试」。本文件即那批断言的落点。

迁移映射的**机器可校验真源**在
``backend/tests/test_note_conversion_v2_removal.py`` 的 ``ASSERTION_MIGRATION``
常量（22 行 / 覆盖 21 个 v2 测试名，配 ``test_migration_table_covers_all_v2_tests``
与 ``test_target_test_exists`` 双向锁死）。**本 docstring 只作导读，不作判据** ——
下表若与该常量不符，以常量为准。

🔴 2026-08-07 实测修正：本表上一版引用的 10 个目标名是**重命名前**的旧名
（``test_manual_cells_counted`` / ``test_roundtrip_keeps_manual_values`` /
``test_same_type_returns_zeroed_result`` 等），磁盘上早已不存在 —— 而
``ASSERTION_MIGRATION`` 常量是按磁盘 AST 实测校对过的、指向真实用例。
docstring 表与代码脱节属「基线按预期而非实测写」的同族缺陷，已按磁盘重写。

迁移映射（源 → 本文件，逐条可追；共 21 个 v2 测试）：

======================================================  ==========================================
原测试（``test_note_conversion_v2.py`` / ``_pbt.py``）    本文件对应
======================================================  ==========================================
``test_preview_v2_returns_all_fields``                  ``test_preview_plan_exposes_all_buckets``
``test_preview_v2_same_type_noop``                      ``test_same_type_conversion_is_noop``
``test_preview_v2_invalid_target_raises``               ``test_invalid_target_type_raises``
``test_preview_v2_counts_manual_cells_correctly``       ``test_manual_cells_are_counted_and_preserved``
``test_convert_v2_common_sections_preserved``           ``test_common_section_data_preserved``
``test_convert_v2_soe_only_archived``                   ``test_source_only_sections_archived``
``test_convert_v2_listed_only_created``                 ``test_target_only_sections_created`` +
                                                        ``test_created_note_section_is_real_number_not_sid``
                                                        （一分为二，后者判据更强）
``test_convert_v2_format_diff_adapted``                 ``test_format_diff_counts_only_real_changes``
                                                        （**判据更强**：按 ``report.changed``
                                                        事实判据，空操作不得计数）
``test_convert_v2_updates_template_type``               ``test_execute_conversion_updates_template_type``
``test_convert_v2_same_type_noop``                      ``test_same_type_conversion_is_noop``
``test_convert_v2_invalid_target_raises``               ``test_invalid_target_type_raises``
``test_convert_v2_listed_to_soe_reverses``              ``test_reverse_direction_swaps_archive_and_create``
``test_convert_v2_no_notes_still_works``                ``test_no_notes_still_creates_target_only_sections``
``test_pbt_full_roundtrip_soe_listed_soe``              ``test_full_roundtrip_preserves_manual_cells``
``test_pbt_archived_sections_have_lineage``             ``test_archived_sections_have_lineage``
``test_pbt_manual_cells_preserved_after_roundtrip``     ``test_manual_cells_are_counted_and_preserved``
``test_pbt_locked_cells_preserved``                     ``test_locked_cells_preserved``（PBT 保留，
                                                        改为真调生产路径而非 ``deepcopy`` 自证）
``test_pbt_empty_table_safe``                           ``test_empty_and_none_table_data_are_safe``
``test_roundtrip_preserves_manual_value_simple``        ``test_manual_value_survives_simple_rewrite``
``test_roundtrip_empty_rows_safe``                      ``test_empty_and_none_table_data_are_safe``
``test_roundtrip_none_table_data_safe``                 ``test_none_table_data_is_safe``
======================================================  ==========================================

🔴 **三个原测试的断言在迁移时被诚实加强**（旧版锁定的是缺陷行为）：

1. ``test_convert_v2_common_sections_preserved`` 只断言 ``common_count == 2`` 且
   ``not n.is_deleted`` —— 而 v2 **从不改写 ``section_id``**（本 spec 立项要修的核心
   缺陷之一）。迁移版必须断言 ``section_id`` 与 ``note_section`` **真的变成目标侧取值**。
2. ``test_convert_v2_listed_only_created`` 只断言 ``created_count == 1`` 与
   ``db.add`` 被调 —— 而 v2 写 ``note_section=sid  # legacy compat``（章节号列写成
   slug，界面与 Word 导出都读它）。迁移版断言 ``note_section`` 是**目标模板的真实
   ``section_number``**。
3. ``test_convert_v2_format_diff_adapted`` 靠 ``patch(adapt_table_data, return_value=…)``
   造出「改了」的假象；v2 改造前是**无条件** ``+= 1``。迁移版按事实判据断言：
   ``field_mapping`` 为空 ⇒ 不计数；非空且真改结构 ⇒ 才计数。

------------------------------------------------------------------------------
为什么用内存替身 session 而不是真实库
------------------------------------------------------------------------------

Requirement 10.6 明令禁止为凑验收改动真实项目的 ``template_type``（会触发
``execute_full_chain(force=True)`` 全链重算）。真实库验收归 Task 19 且需用户显式
授权专用项目。本文件走内存替身，**判据数据全部来自真实 diff + 真实两份模板 JSON**
（不自造章节 sid / 章节号），故仍是对生产逻辑的有效验证。

🔴 替身的 ``_Savepoint.__aexit__`` **必须 ``return False``**（不吞异常）——
上一轮临时探针的替身写了 ``return True``，会让「失败章节进 failed」这条根本测不出来
（异常被 savepoint 吃掉，生产代码的 ``except`` 永远收不到）。
"""
from __future__ import annotations

import copy
from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from app.services.note_conversion_service import (
    MAP_NOTES_PENDING_KEYS,
    NoteConversionService,
    count_manual_cells,
)
from app.services.note_template_diff import load_diff_data, load_template_sections


PROJECT = UUID("00000000-0000-0000-0000-0000000000aa")
YEAR = 2025


# ---------------------------------------------------------------------------
# 内存替身 session —— 只实现 _map_disclosure_notes 用到的 4 个能力
# ---------------------------------------------------------------------------


class _Scalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _Scalars:
        return _Scalars(self._rows)

    def all(self) -> list[Any]:
        return list(self._rows)


class _Row:
    def __init__(self, id: UUID, note_section: str | None) -> None:
        self.id = id
        self.note_section = note_section


class _Savepoint:
    """savepoint 语义：进入时快照全部 note 的可变字段，异常时还原。

    🔴 ``__aexit__`` 返回 ``False`` —— **不得吞异常**。生产代码靠自己的
    ``except Exception`` 把失败章节记进 ``failed`` 桶并继续处理其余章节
    （Requirement 4.3）；替身若 ``return True`` 会把异常吃掉，该行为永远测不出来。
    """

    def __init__(self, session: "FakeSession") -> None:
        self.session = session
        self.snapshot: dict[UUID, tuple] = {}
        self.added: list[Any] = []

    async def __aenter__(self) -> "_Savepoint":
        self.snapshot = {
            n.id: (
                n.section_id,
                n.note_section,
                n.is_deleted,
                deepcopy(n.table_data),
                deepcopy(n.template_lineage),
            )
            for n in self.session.notes
        }
        self.added = list(self.session.added)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            for n in self.session.notes:
                snap = self.snapshot.get(n.id)
                if snap:
                    (
                        n.section_id,
                        n.note_section,
                        n.is_deleted,
                        n.table_data,
                        n.template_lineage,
                    ) = snap
            keep = set(self.snapshot)
            self.session.notes = [
                n for n in self.session.notes if n.id in keep or n in self.added
            ]
            self.session.added = list(self.added)
        return False


class FakeSession:
    """替身 session。

    ``flush_fail_on`` 按 **note id** 精确匹配注入失败（Requirement 4.3 的失败隔离
    判据）——按「第 N 次 flush」注入会让失败落在不确定的章节上，测不出隔离语义。
    """

    def __init__(
        self,
        notes: list[Any],
        flush_fail_on: set[UUID] | None = None,
    ) -> None:
        self.notes = list(notes)
        self.added: list[Any] = []
        self.flush_fail_on = flush_fail_on or set()
        self.flush_calls = 0
        self.committed = False

    async def execute(self, stmt: Any) -> _Result:
        text = str(stmt)
        head = text.split("FROM")[0]
        live = [n for n in self.notes if not n.is_deleted]
        # 两条查询都含 disclosure_notes.id / note_section（全列 ORM select 也列它们）
        # ⇒ 判据取「SELECT 头部是否含 table_data 列」：number_owner 查询只取两列。
        if "disclosure_notes.table_data" not in head:
            return _Result([_Row(n.id, n.note_section) for n in self.notes])
        return _Result(live)

    async def flush(self) -> None:
        self.flush_calls += 1
        for n in self.notes:
            if n.id in self.flush_fail_on:
                raise RuntimeError(f"injected flush failure for {n.id}")

    async def commit(self) -> None:
        self.committed = True

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        self.notes.append(obj)

    def begin_nested(self) -> _Savepoint:
        return _Savepoint(self)


def make_note(
    *,
    section_id: str | None = None,
    note_section: str = "",
    section_title: str = "",
    table_data: dict[str, Any] | None = None,
    lineage: dict[str, Any] | None = None,
) -> Any:
    from app.models.report_models import DisclosureNote

    n = DisclosureNote()
    n.id = uuid4()
    n.project_id = PROJECT
    n.year = YEAR
    n.section_id = section_id
    n.note_section = note_section
    n.section_title = section_title
    n.table_data = table_data
    n.template_lineage = lineage
    n.is_deleted = False
    n.is_empty = False
    n.status = "draft"
    return n


# ---------------------------------------------------------------------------
# 真实判据数据（不自造 sid / 章节号）
# ---------------------------------------------------------------------------


class _Fixture:
    """从真实 diff + 真实模板取一对可用的 (源 sid, 目标 sid, 两侧章节号)。"""

    def __init__(self) -> None:
        self.diff = load_diff_data()
        svc = NoteConversionService(FakeSession([]))
        self.plan_fwd = svc._build_section_mapping_plan(self.diff, "soe", "listed")
        self.plan_rev = svc._build_section_mapping_plan(self.diff, "listed", "soe")
        self.soe_sections = {
            s["section_id"]: s
            for s in load_template_sections("soe")
            if isinstance(s, dict) and s.get("section_id")
        }
        self.listed_sections = {
            s["section_id"]: s
            for s in load_template_sections("listed")
            if isinstance(s, dict) and s.get("section_id")
        }
        pairs = [
            (src, p)
            for src, p in self.plan_fwd["pairs"].items()
            if (self.soe_sections.get(src) or {}).get("section_number")
            and (self.listed_sections.get(p["target_sid"]) or {}).get("section_number")
        ]
        assert pairs, "真实 diff 里找不到两侧都带 section_number 的 pair —— 判据失效"
        self.src_sid, pair = pairs[0]
        self.tgt_sid = pair["target_sid"]
        self.src_num = self.soe_sections[self.src_sid]["section_number"]
        self.tgt_num = self.listed_sections[self.tgt_sid]["section_number"]
        self.src_title = self.soe_sections[self.src_sid].get("section_title") or ""
        # 第二对（失败隔离用）
        self.src_sid2, pair2 = pairs[1]
        self.tgt_sid2 = pair2["target_sid"]
        self.src_num2 = self.soe_sections[self.src_sid2]["section_number"]
        # 源侧独有（归档用）
        src_only = sorted(self.plan_fwd["source_only"])
        assert src_only, "真实 diff 里 source_only 为空 —— 归档判据失效"
        self.archive_sid = src_only[0]
        self.archive_num = (self.soe_sections.get(self.archive_sid) or {}).get(
            "section_number"
        ) or "零、未知"
        # 目标侧独有（新建用）：取一个带 section_number 的
        tgt_only = [
            (sid, e)
            for sid, e in self.plan_fwd["target_only"].items()
            if (self.listed_sections.get(sid) or {}).get("section_number")
        ]
        assert tgt_only, "真实 diff 里 target_only 无带章节号条目 —— 新建判据失效"
        self.create_sid, self.create_entry = tgt_only[0]
        self.create_num = self.listed_sections[self.create_sid]["section_number"]


@pytest.fixture(scope="module")
def fx() -> _Fixture:
    return _Fixture()


# ---------------------------------------------------------------------------
# 迁移：preview_conversion_v2 的字段/计数断言 → 生产返回结构
# ---------------------------------------------------------------------------


class TestPreviewFields:
    """承接 ``test_preview_v2_returns_all_fields``。

    v2 的 preview 返回 ``common_sections`` / ``to_archive_sections`` /
    ``to_create_sections`` 三个**清单**；生产路径把同一信息表达为
    ``_build_section_mapping_plan`` 的 ``pairs`` / ``source_only`` / ``target_only``，
    并由 ``_map_disclosure_notes`` 返回**实际发生数**（Requirement 4.1/4.2）。
    """

    def test_preview_plan_exposes_all_buckets(self, fx: _Fixture) -> None:
        for key in ("pairs", "source_only", "target_only", "format_diff", "bridged"):
            assert key in fx.plan_fwd, f"映射计划缺 {key}"
        assert fx.plan_fwd["pairs"], "pairs 为空"
        assert fx.plan_fwd["source_only"], "source_only 为空"
        assert fx.plan_fwd["target_only"], "target_only 为空"

    def test_plan_is_symmetric(self, fx: _Fixture) -> None:
        """两个方向的 pair 数相等（同一批共有章节 + 同一批别名桥接）。"""
        assert len(fx.plan_fwd["pairs"]) == len(fx.plan_rev["pairs"])

    @pytest.mark.asyncio
    async def test_result_has_five_categories(self, fx: _Fixture) -> None:
        """Requirement 4.2：mapped / archived / created / skipped / failed 齐备。"""
        note = make_note(
            section_id=fx.src_sid, note_section=fx.src_num, section_title=fx.src_title
        )
        svc = NoteConversionService(FakeSession([note]))
        res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")
        for key in ("mapped", "archived", "created", "skipped", "failed"):
            assert key in res, f"返回结构缺分类 {key}"
        assert isinstance(res["skipped"], list)
        assert isinstance(res["failed"], list)

    @pytest.mark.asyncio
    async def test_no_pending_keys_remain(self, fx: _Fixture) -> None:
        """Task 9 收口后三个键是真实计数，不再有「未测量」项。"""
        assert MAP_NOTES_PENDING_KEYS == ()
        note = make_note(
            section_id=fx.src_sid, note_section=fx.src_num, section_title=fx.src_title
        )
        svc = NoteConversionService(FakeSession([note]))
        res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")
        for key in ("archived", "created", "user_edits_preserved"):
            assert res[key] is not None, f"{key} 仍是 None（未测量）"
            assert isinstance(res[key], int)
        assert res["pending_keys"] == []


# ---------------------------------------------------------------------------
# 迁移：共有章节 —— 断言加强为「真的改写了 sid 与章节号」
# ---------------------------------------------------------------------------


class TestCommonSectionRewrite:
    @pytest.mark.asyncio
    async def test_common_section_data_preserved(self, fx: _Fixture) -> None:
        """承接 ``test_convert_v2_common_sections_preserved``（断言已加强）。

        v2 只断 ``common_count`` 且不改 ``section_id``；本例断言 sid 与章节号
        **真的变成目标侧取值**，且 manual 单元格计数不减。
        """
        td = {
            "rows": [
                {
                    "label": "A",
                    "values": [100],
                    "_cell_modes": {"0": "manual"},
                },
                {"label": "B", "values": [200], "_cell_modes": {}},
            ]
        }
        note = make_note(
            section_id=fx.src_sid,
            note_section=fx.src_num,
            section_title=fx.src_title,
            table_data=deepcopy(td),
        )
        manual_before = count_manual_cells(note.table_data)
        assert manual_before == 1, "fixture 未产生 manual 单元格 —— 断言会空转"

        svc = NoteConversionService(FakeSession([note]))
        res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")

        assert res["mapped"] == 1
        assert note.section_id == fx.tgt_sid, "section_id 未改写（v2 的核心缺陷）"
        assert note.note_section == fx.tgt_num, "note_section 未改写"
        assert note.is_deleted is False
        assert count_manual_cells(note.table_data) == manual_before
        assert res["user_edits_dropped"] == 0
        assert res["user_edits_preserved"] == manual_before

    @pytest.mark.asyncio
    async def test_legacy_ids_recorded(self, fx: _Fixture) -> None:
        """源侧 sid / 旧章节号进 ``template_lineage``（Requirements 2.2, 2.7）。"""
        note = make_note(
            section_id=fx.src_sid,
            note_section=fx.src_num,
            section_title=fx.src_title,
            table_data={"rows": [{"binding_id": f"{fx.src_num}.行A.col1"}]},
        )
        svc = NoteConversionService(FakeSession([note]))
        await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")

        lineage = note.template_lineage or {}
        assert fx.src_sid in (lineage.get("legacy_section_ids") or [])
        assert fx.src_num in (lineage.get("legacy_note_sections") or [])

    @pytest.mark.asyncio
    async def test_binding_id_prefix_rewritten(self, fx: _Fixture) -> None:
        """Requirement 2.7 / Property 35：binding_id 不因章节号改写而失联。"""
        note = make_note(
            section_id=fx.src_sid,
            note_section=fx.src_num,
            section_title=fx.src_title,
            table_data={
                "rows": [
                    {"binding_id": f"{fx.src_num}.行A.col1"},
                    {"binding_id": "九、99.别的章.colX"},
                ],
                "_tables": [{"rows": [{"binding_id": f"{fx.src_num}.行B.col2"}]}],
                "sub_table_data": {"t1": [{"binding_id": f"{fx.src_num}.行C.col3"}]},
            },
        )
        svc = NoteConversionService(FakeSession([note]))
        res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")

        assert res["binding_ids_rewritten"] == 3
        assert note.table_data["rows"][0]["binding_id"].startswith(f"{fx.tgt_num}.")
        assert note.table_data["_tables"][0]["rows"][0]["binding_id"].startswith(
            f"{fx.tgt_num}."
        )
        assert note.table_data["sub_table_data"]["t1"][0]["binding_id"].startswith(
            f"{fx.tgt_num}."
        )
        # 别的章节号不得被误改
        assert note.table_data["rows"][1]["binding_id"] == "九、99.别的章.colX"

    @pytest.mark.asyncio
    async def test_idempotent_rerun(self, fx: _Fixture) -> None:
        """幂等重跑：第二次 mapped=0（已是目标侧取值）。"""
        note = make_note(
            section_id=fx.src_sid, note_section=fx.src_num, section_title=fx.src_title
        )
        svc = NoteConversionService(FakeSession([note]))
        first = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")
        second = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")
        assert first["mapped"] == 1
        assert second["mapped"] == 0


# ---------------------------------------------------------------------------
# 迁移：归档
# ---------------------------------------------------------------------------


class TestArchive:
    @pytest.mark.asyncio
    async def test_source_only_sections_archived(self, fx: _Fixture) -> None:
        """承接 ``test_convert_v2_soe_only_archived``。"""
        note = make_note(
            section_id=fx.archive_sid,
            note_section=fx.archive_num,
            section_title="源独有",
            table_data={"rows": []},
        )
        svc = NoteConversionService(FakeSession([note]))
        res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")

        assert res["archived"] == 1
        assert note.is_deleted is True

    @pytest.mark.asyncio
    async def test_archived_sections_have_lineage(self, fx: _Fixture) -> None:
        """承接 ``test_pbt_archived_sections_have_lineage``（Requirement 2.3）。"""
        note = make_note(
            section_id=fx.archive_sid,
            note_section=fx.archive_num,
            section_title="源独有",
            table_data={"rows": [{"label": "X", "values": [1]}]},
        )
        svc = NoteConversionService(FakeSession([note]))
        await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")

        lineage = note.template_lineage or {}
        archived = lineage.get("archived_sections") or []
        assert archived, "archived_sections 未写入"
        assert archived[0]["section_id"] == fx.archive_sid
        assert "archived_at" in archived[0]
        assert "reason" in archived[0]


# ---------------------------------------------------------------------------
# 迁移：新建目标侧独有章节 —— 断言加强为「章节号是真实 section_number 不是 sid」
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_target_only_sections_created(self, fx: _Fixture) -> None:
        """承接 ``test_convert_v2_listed_only_created`` + ``test_convert_v2_no_notes_still_works``。"""
        sess = FakeSession([])
        svc = NoteConversionService(sess)
        res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")

        assert res["created"] > 0, "目标侧独有章节未被新建"
        assert sess.added, "db.add 未被调用"

    @pytest.mark.asyncio
    async def test_created_note_section_is_real_number_not_sid(
        self, fx: _Fixture
    ) -> None:
        """🔴 断言加强：v2 写 ``note_section=sid  # legacy compat`` 是缺陷形态。

        该列是**展示用章节号**（界面与 Word 导出都读它），写成 slug 会显示一串拼音。
        """
        sess = FakeSession([])
        svc = NoteConversionService(sess)
        await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")

        assert sess.added, "无新建章节 —— 断言会空转"
        for new_note in sess.added:
            assert new_note.section_id, "新建章节缺 section_id"
            assert new_note.note_section, "新建章节缺 note_section"
            assert new_note.note_section != new_note.section_id, (
                f"note_section 被写成 sid（{new_note.note_section}）—— "
                "那是 convert_disclosure_notes_v2 的缺陷形态"
            )
            # Requirement 2.4
            assert new_note.is_empty is True
            assert new_note.status == "draft"


# ---------------------------------------------------------------------------
# 迁移：格式适配 —— 断言从「patch 造假」改为事实判据
# ---------------------------------------------------------------------------


class TestFormatAdapt:
    """承接 ``test_convert_v2_format_diff_adapted``（判据已加强）。

    v2 版靠 ``patch(adapt_table_data, return_value=已改的字典)`` 制造「适配成功」，
    掩盖了改造前**无条件** ``format_adapted_count += 1`` 这一假成功反馈。本组按
    ``AdaptReport.changed``（输出 != 输入）这一事实判据断言两个方向。
    """

    @pytest.mark.asyncio
    async def test_empty_field_mapping_does_not_count(self, fx: _Fixture) -> None:
        """真实数据 39/39 条 ``field_mapping`` 全 null ⇒ 不得计为已适配。"""
        note = make_note(
            section_id=fx.src_sid,
            note_section=fx.src_num,
            section_title=fx.src_title,
            table_data={"rows": [{"label": "X", "values": [1]}]},
        )
        svc = NoteConversionService(FakeSession([note]))
        res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")
        assert res["format_adapted"] == 0, (
            "field_mapping 全 null 却计入 format_adapted —— 假成功反馈重现"
        )

    @pytest.mark.asyncio
    async def test_format_diff_counts_only_real_changes(self, fx: _Fixture) -> None:
        """非空 ``field_mapping`` 且真改结构 ⇒ 才计数。"""
        diff = deepcopy(load_diff_data())
        diff["format_diff_sections"] = [
            {
                "section_title": fx.src_title,
                "soe_section_id": fx.src_sid,
                "listed_section_id": fx.tgt_sid,
                "soe_format": {},
                "listed_format": {"layout": "category_sum"},
                "field_mapping": {"column_remap": {"col_old": "col_new"}},
            }
        ]
        note = make_note(
            section_id=fx.src_sid,
            note_section=fx.src_num,
            section_title=fx.src_title,
            table_data={
                "_columns_meta": [{"id": "col_old", "name": "旧列"}],
                "rows": [
                    {
                        "row_type": "data",
                        "values": {"col_old": "100"},
                        "_cell_modes": {"col_old": "manual"},
                    }
                ],
            },
        )
        svc = NoteConversionService(FakeSession([note]))
        with patch(
            "app.services.note_template_diff.load_diff_data", return_value=diff
        ):
            res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")

        assert res["format_adapted"] == 1, "真实结构改动未被计数"
        assert note.table_data["_columns_meta"][0]["id"] == "col_new"
        # manual 标记必须跟着列改名走（平台红线）
        assert note.table_data["rows"][0]["_cell_modes"].get("col_new") == "manual"
        assert res["user_edits_dropped"] == 0


# ---------------------------------------------------------------------------
# 迁移：同类型空操作 / 非法目标 / 反向切换 / 全链入口
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_type_conversion_is_noop(fx: _Fixture) -> None:
    """承接 ``test_convert_v2_same_type_noop`` + ``test_preview_v2_same_type_noop``。"""
    note = make_note(
        section_id=fx.src_sid, note_section=fx.src_num, section_title=fx.src_title
    )
    svc = NoteConversionService(FakeSession([note]))
    res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "soe")
    assert res["mapped"] == 0
    assert res["archived"] == 0
    assert res["created"] == 0
    assert res["skipped"] == []
    assert res["failed"] == []
    assert note.section_id == fx.src_sid, "同类型切换不得改写"


@pytest.mark.asyncio
async def test_invalid_target_type_raises() -> None:
    """承接 ``test_convert_v2_invalid_target_raises`` / ``test_preview_v2_invalid_target_raises``。

    生产入口 ``execute_conversion`` 承载该校验（v2 也校验，但它已无调用方）。
    """
    svc = NoteConversionService(MagicMock())
    with pytest.raises(ValueError, match="target_type"):
        await svc.execute_conversion(uuid4(), YEAR, "invalid")
    with pytest.raises(ValueError, match="target_type"):
        await svc.preview_conversion(uuid4(), YEAR, "bad")


@pytest.mark.asyncio
async def test_reverse_direction_swaps_archive_and_create(fx: _Fixture) -> None:
    """承接 ``test_convert_v2_listed_to_soe_reverses``：反向切换归档/新建互换。"""
    rev_src_only = sorted(fx.plan_rev["source_only"])
    assert rev_src_only, "反向 source_only 为空"
    sid = rev_src_only[0]
    num = (fx.listed_sections.get(sid) or {}).get("section_number") or "零、未知"
    note = make_note(section_id=sid, note_section=num, section_title="listed 独有")
    sess = FakeSession([note])
    svc = NoteConversionService(sess)
    res = await svc._map_disclosure_notes(PROJECT, YEAR, "listed", "soe")

    assert res["archived"] == 1, "反向切换未归档 listed 独有章节"
    assert note.is_deleted is True
    assert res["created"] > 0, "反向切换未新建 soe 独有章节"


@pytest.mark.asyncio
async def test_execute_conversion_updates_template_type(fx: _Fixture) -> None:
    """承接 ``test_convert_v2_updates_template_type``：改 ``template_type`` 归生产入口。

    ``execute_conversion`` 用 ``sa.update(Project)`` 走 SQL（不是改 ORM 属性），
    故这里断言**该 UPDATE 语句真的被执行过**且带目标取值。
    """
    project = SimpleNamespace(
        id=PROJECT, template_type="soe", is_deleted=False, audit_year=YEAR
    )
    note = make_note(
        section_id=fx.src_sid, note_section=fx.src_num, section_title=fx.src_title
    )
    sess = FakeSession([note])
    statements: list[str] = []
    orig_execute = sess.execute

    async def _spy(stmt: Any) -> Any:
        statements.append(str(stmt))
        return await orig_execute(stmt)

    sess.execute = _spy  # type: ignore[method-assign]
    svc = NoteConversionService(sess)

    with patch.object(svc, "_get_project", AsyncMock(return_value=project)), patch.object(
        svc, "_create_snapshot", AsyncMock(return_value={"snapshot_id": "snap-1"})
    ), patch.object(
        svc, "_trigger_chain_refresh", AsyncMock(return_value={"triggered": False})
    ):
        result = await svc.execute_conversion(PROJECT, YEAR, "listed")

    assert result["status"] == "completed"
    assert result["to_type"] == "listed"
    updates = [s for s in statements if s.strip().upper().startswith("UPDATE PROJECTS")]
    assert updates, f"未见 UPDATE projects 语句: {statements}"
    assert "template_type" in updates[0]
    # Requirement 4.1：mapped_notes 是实际改写数，不是存量 count(*)
    assert result["mapped_notes"] == 1
    assert note.section_id == fx.tgt_sid


@pytest.mark.asyncio
async def test_no_notes_still_creates_target_only_sections(fx: _Fixture) -> None:
    """承接 ``test_convert_v2_no_notes_still_works``：无存量章节不崩且仍新建。"""
    sess = FakeSession([])
    svc = NoteConversionService(sess)
    res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")
    assert res["mapped"] == 0
    assert res["archived"] == 0
    assert res["created"] > 0
    assert res["failed"] == []


# ---------------------------------------------------------------------------
# 迁移：manual/locked 单元格保留（原 PBT 是 deepcopy 自证，现改为真调生产路径）
# ---------------------------------------------------------------------------


_finite = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
_cell_value = st.one_of(_finite, st.none())
_mode = st.sampled_from(["auto", "manual", "locked"])


# 🔴 策略规模直接决定单个 example 的成本 —— 每个 example 都真造一份 note 并真调
# 一次 ``_map_disclosure_notes``，成本大致正比于 行数×列数。
#
# 2026-08-08 行上界 8 → 4（列保持 1..4 不动）：本组要覆盖的「形态」是
# 单行/多行 × 单列/多列 × ``auto|manual|locked`` 三态混合，4 行 × 4 列 = 16 格
# 已能表达全部形态组合（含「同一行内三种 mode 并存」「整行 auto」「整列 locked」）；
# 第 5~8 行只是把同一形态再重复一遍，不产生新的反例空间。
# **收窄策略优先于降 max_examples** —— 省时的同时形态覆盖不降。
@st.composite
def table_data_strategy(draw):  # type: ignore[no-untyped-def]
    n_cols = draw(st.integers(min_value=1, max_value=4))
    n_rows = draw(st.integers(min_value=1, max_value=4))
    rows = []
    for i in range(n_rows):
        values = draw(st.lists(_cell_value, min_size=n_cols, max_size=n_cols))
        modes = {str(j): draw(_mode) for j in range(n_cols)}
        rows.append(
            {
                "label": f"row_{i}",
                "values": values,
                "_cell_modes": modes,
                "row_type": "data",
            }
        )
    return {"rows": rows}


class TestManualCellPBT:
    """承接 ``test_pbt_manual_cells_preserved_after_roundtrip`` /
    ``test_pbt_locked_cells_preserved`` / ``test_pbt_empty_table_safe``。

    🔴 原 PBT 只对 ``copy.deepcopy(td)`` 自证「深拷贝不丢数据」，**根本没调生产
    代码**（注释里自承认「模拟 round-trip」）—— 那样即便生产路径把 manual 单元格
    全删了也测不出来。本组真调 ``_map_disclosure_notes``。

    ``max_examples`` = **8**（2026-08-08 由 20 下调，用户要求提速）。取 8 而不是
    更低的理由：本组的反例空间由「行数 × 列数 × 三态 mode 混合」张成，8 个 example
    足以在随机抽样下反复命中「同一行内 manual/locked/auto 并存」这一核心形态；
    再降到 5 以下会让「多行 × 多列 × 混合 mode」的联合形态出现概率明显下降。

    🔴 与平台既有约定的关系：平台约定值是 **20**（2026-08-04 由 100 下调）。本组
    显式低于该约定，因为**每个 example 都真调生产路径**（造 note + ``FakeSession``
    + ``asyncio.run(_map_disclosure_notes)``），单 example 成本远高于纯函数 PBT；
    纯函数型 PBT 仍按平台约定的 20 走，不要照本组改。

    🔴 本次下调是**纯提速**：下调前该 PBT 已是全绿（Task 9/10 实录：26 例全绿），
    不存在「降例数把反例掩盖掉」的情形。若将来它转红，反例必须按平台铁律固化成
    ``@example`` 而不是继续下调例数（降例数 ≠ 修缺陷）。
    """

    @given(td=table_data_strategy())
    @settings(
        max_examples=8,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_locked_cells_preserved(
        self, td: dict[str, Any]
    ) -> None:
        import asyncio

        fixture = _MODULE_FIXTURE
        expected: list[tuple[int, int, Any, str]] = []
        for ri, row in enumerate(td["rows"]):
            modes = row.get("_cell_modes", {})
            for ci in range(len(row["values"])):
                mode = modes.get(str(ci))
                if mode in ("manual", "locked"):
                    expected.append((ri, ci, row["values"][ci], mode))

        note = make_note(
            section_id=fixture.src_sid,
            note_section=fixture.src_num,
            section_title=fixture.src_title,
            table_data=deepcopy(td),
        )
        svc = NoteConversionService(FakeSession([note]))
        res = asyncio.run(svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed"))

        assert res["mapped"] == 1
        assert res["user_edits_dropped"] == 0
        for ri, ci, value, mode in expected:
            row = note.table_data["rows"][ri]
            assert row["values"][ci] == value, (
                f"{mode} cell [{ri}][{ci}] 丢失: 期望 {value}，实得 {row['values'][ci]}"
            )
            assert row["_cell_modes"][str(ci)] == mode


@pytest.mark.asyncio
async def test_manual_value_survives_simple_rewrite(fx: _Fixture) -> None:
    """承接 ``test_roundtrip_preserves_manual_value_simple``。"""
    note = make_note(
        section_id=fx.src_sid,
        note_section=fx.src_num,
        section_title=fx.src_title,
        table_data={"rows": [{"label": "A", "values": [42.0], "_cell_modes": {"0": "manual"}}]},
    )
    svc = NoteConversionService(FakeSession([note]))
    await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")
    assert note.table_data["rows"][0]["values"][0] == 42.0


@pytest.mark.asyncio
async def test_empty_and_none_table_data_are_safe(fx: _Fixture) -> None:
    """承接 ``test_roundtrip_empty_rows_safe``。"""
    note = make_note(
        section_id=fx.src_sid,
        note_section=fx.src_num,
        section_title=fx.src_title,
        table_data={"rows": []},
    )
    svc = NoteConversionService(FakeSession([note]))
    res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")
    assert res["mapped"] == 1
    assert res["failed"] == []
    assert note.table_data == {"rows": []}


@pytest.mark.asyncio
async def test_none_table_data_is_safe(fx: _Fixture) -> None:
    """承接 ``test_roundtrip_none_table_data_safe``：``table_data`` 为 None 不崩。"""
    note = make_note(
        section_id=fx.src_sid,
        note_section=fx.src_num,
        section_title=fx.src_title,
        table_data=None,
    )
    svc = NoteConversionService(FakeSession([note]))
    res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")
    assert res["mapped"] == 1
    assert res["failed"] == []
    assert note.table_data is None


@pytest.mark.asyncio
async def test_manual_cells_are_counted_and_preserved(fx: _Fixture) -> None:
    """承接 ``test_preview_v2_counts_manual_cells_correctly``（3 个 manual）。"""
    note = make_note(
        section_id=fx.src_sid,
        note_section=fx.src_num,
        section_title=fx.src_title,
        table_data={
            "rows": [
                {
                    "label": "A",
                    "values": [1, 2, 3],
                    "_cell_modes": {"0": "manual", "1": "manual", "2": "auto"},
                },
                {
                    "label": "B",
                    "values": [4, 5, 6],
                    "_cell_modes": {"0": "locked", "1": "manual"},
                },
            ]
        },
    )
    svc = NoteConversionService(FakeSession([note]))
    res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")
    assert res["user_edits_preserved"] == 3


@pytest.mark.asyncio
async def test_full_roundtrip_preserves_manual_cells(fx: _Fixture) -> None:
    """承接 ``test_pbt_full_roundtrip_soe_listed_soe``：soe→listed→soe 往返。"""
    td = {
        "rows": [
            {
                "label": "A",
                "values": [100.0, 200.0],
                "_cell_modes": {"0": "manual", "1": "auto"},
                "row_type": "data",
            },
            {
                "label": "B",
                "values": [300.0, 400.0],
                "_cell_modes": {"0": "auto", "1": "manual"},
                "row_type": "data",
            },
        ]
    }
    note = make_note(
        section_id=fx.src_sid,
        note_section=fx.src_num,
        section_title=fx.src_title,
        table_data=deepcopy(td),
    )
    sess = FakeSession([note])
    svc = NoteConversionService(sess)

    fwd = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")
    assert fwd["mapped"] == 1
    assert note.section_id == fx.tgt_sid

    back = await svc._map_disclosure_notes(PROJECT, YEAR, "listed", "soe")
    assert back["mapped"] == 1
    assert note.section_id == fx.src_sid, "往返后未回到源侧 sid"
    assert note.note_section == fx.src_num

    assert note.table_data["rows"][0]["values"][0] == 100.0
    assert note.table_data["rows"][1]["values"][1] == 400.0
    assert fwd["user_edits_dropped"] == 0
    assert back["user_edits_dropped"] == 0


# ---------------------------------------------------------------------------
# 失败隔离（Requirement 4.3）—— v2 没有这条能力，属生产路径新增
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_failure_does_not_block_others(fx: _Fixture) -> None:
    ok_note = make_note(
        section_id=fx.src_sid, note_section=fx.src_num, section_title="正常"
    )
    bad_note = make_note(
        section_id=fx.src_sid2, note_section=fx.src_num2, section_title="注入失败"
    )
    sess = FakeSession([ok_note, bad_note], flush_fail_on={bad_note.id})
    svc = NoteConversionService(sess)
    res = await svc._map_disclosure_notes(PROJECT, YEAR, "soe", "listed")

    assert res["failed"], "注入的失败章节未进 failed 桶"
    failed_ids = {f["note_id"] for f in res["failed"]}
    assert str(bad_note.id) in failed_ids
    for item in res["failed"]:
        assert {"note_id", "phase", "error"} <= set(item)


# ---------------------------------------------------------------------------
# module 级 fixture 给 PBT 用（hypothesis 与 function-scoped fixture 不兼容）
# ---------------------------------------------------------------------------

_MODULE_FIXTURE = _Fixture()
