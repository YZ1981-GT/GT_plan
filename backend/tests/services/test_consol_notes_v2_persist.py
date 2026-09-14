"""Task 4.2 / 4.3 — 合并附注 V2 落库 属性测试（disclosure-note-linkage-completion Req3/Req7）.

覆盖 `_persist_consol_sections_v2`（Task 4.1，裁决 C = 仅落 provenance）的四条正确性属性：

- **Property 7（V2 落库幂等）**：同 ``(project_id, year, note_section)`` 二次落库
  不新增行；``_manual_override=True`` 锁定章节不被覆盖（进 skipped）；软删行被复活
  复用（而非 fresh INSERT，后者会撞唯一键 500）。
- **Property 8（V2 fail-open）**：某章节落库抛异常时，其余章节仍落库，函数返回
  ``{upserted, skipped, errors}`` 且不 raise，``errors`` 记录失败章节。
- **Property 9（V2 开关关零改动）**：``CONSOL_NOTES_V2_ENABLED=False`` 时
  ``generate_full_consol_notes`` 不调用 ``_persist_consol_sections_v2``（不落库）。
- **Property 10（V2 落库激活穿透）**：落库后 ``note_consol_drilldown_service`` 对已
  落库章节返回 ``has_breakdown=true`` 且 ``by_company`` 非空。

采用 mock-AsyncSession（stateful fake，与既有 `test_consol_disclosure_v2` 同款风格），
避免真实 PG 的 FK create_all 阻塞（memory：service_identities blocker）。

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 7.3
"""

from __future__ import annotations

import asyncio
import string
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings as hyp_settings, strategies as st

from app.core.config import settings
from app.services.consol_disclosure_service import (
    _persist_consol_sections_v2,
    generate_full_consol_notes,
)
from app.services.note_consol_drilldown_service import get_note_consol_breakdown


# ---------------------------------------------------------------------------
# stateful fake AsyncSession（无真实 DB，规避 FK create_all 阻塞）
# ---------------------------------------------------------------------------


def _criteria_from_stmt(stmt):
    """从 select 语句 whereclause 提取 (note_section, wants_deleted)。

    ``_persist_consol_sections_v2`` 每章节先查 active（is_deleted=false）再查软删
    （is_deleted=true）。走表达式树而非编译 SQL，方言无关。
    """
    section = None
    wants_deleted = False
    where = getattr(stmt, "whereclause", None)
    clauses = getattr(where, "clauses", None) or ([where] if where is not None else [])
    for cl in clauses:
        left = getattr(cl, "left", None)
        right = getattr(cl, "right", None)
        key = getattr(left, "key", None) if left is not None else None
        if key == "note_section":
            section = getattr(right, "value", None)
        elif key == "is_deleted":
            # right 为 sa.false()/sa.true() 子句元素（类名 False_/True_）
            wants_deleted = "true" in type(right).__name__.lower()
    return section, wants_deleted


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeNote:
    """DisclosureNote ORM 行的属性替身（用于预置 active/软删章节）。"""

    def __init__(self, **kw):
        self.note_section = kw.get("note_section")
        self.is_deleted = kw.get("is_deleted", False)
        self.table_data = kw.get("table_data")
        self.source_project_id = kw.get("source_project_id")
        self.consolidation_breakdown = kw.get("consolidation_breakdown")
        self.last_sync_source = kw.get("last_sync_source")
        self.last_sync_at = kw.get("last_sync_at")
        self.updated_at = kw.get("updated_at")


class _FakeSession:
    """stateful fake AsyncSession：按 (note_section, is_deleted) 匹配查询。"""

    def __init__(self, existing=None, poison_section=None, commit_error=False):
        self.rows = list(existing or [])
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0
        self.poison_section = poison_section
        self.commit_error = commit_error

    async def execute(self, stmt):
        section, wants_deleted = _criteria_from_stmt(stmt)
        if self.poison_section is not None and section == self.poison_section:
            raise RuntimeError(f"boom on section {section}")
        for n in self.rows:
            if (
                getattr(n, "note_section", None) == section
                and bool(getattr(n, "is_deleted", False)) == wants_deleted
            ):
                return _FakeResult(n)
        return _FakeResult(None)

    def add(self, obj):
        # 模拟 INSERT：新行进 store，供同一 fake 后续查询命中（幂等验证）
        self.added.append(obj)
        self.rows.append(obj)

    async def commit(self):
        self.commit_count += 1
        if self.commit_error:
            raise RuntimeError("commit boom")

    async def rollback(self):
        self.rollback_count += 1


def _run(coro):
    """同步驱动协程（hypothesis 与 function-scoped async fixture 不兼容，走 asyncio.run）。"""
    return asyncio.run(coro)


_PID = uuid4()
_YEAR = 2025
_SECTION_ALPHABET = string.ascii_lowercase + string.digits + "_-"
_section_id = st.text(alphabet=_SECTION_ALPHABET, min_size=1, max_size=10).map(str.strip).filter(bool)


def _sections(ids):
    return [
        {"section_id": sid, "consolidation_breakdown": {"by_company": [{"code": sid, "amount": "1"}]}}
        for sid in ids
    ]


# ===========================================================================
# Property 7 — V2 落库幂等 / 不覆盖锁定 / 软删复活
# ===========================================================================


class TestProperty7Idempotent:
    """Property 7：同键二次落库不新增行；锁定章节不覆盖；软删行复活。

    **Validates: Requirements 3.4**
    """

    @given(ids=st.lists(_section_id, min_size=1, max_size=5, unique=True))
    @hyp_settings(max_examples=25)
    def test_p7_idempotent_no_duplicate_rows(self, ids):
        """连续两次落库同一批章节：首次全新建，二次全走更新，无重复行。"""
        sections = _sections(ids)
        db = _FakeSession()

        r1 = _run(_persist_consol_sections_v2(db, _PID, _YEAR, sections, "soe"))
        assert r1["upserted"] == len(ids)
        assert r1["errors"] == []
        assert len(db.added) == len(ids)  # 首次全部 INSERT

        r2 = _run(_persist_consol_sections_v2(db, _PID, _YEAR, sections, "soe"))
        assert r2["upserted"] == len(ids)
        assert r2["errors"] == []
        # 二次不新增行（全部命中 active 走更新分支）
        assert len(db.added) == len(ids)
        # 每个 section 在 store 中仅一条 active 行（无重复）
        for sid in ids:
            active = [n for n in db.rows if n.note_section == sid and not bool(getattr(n, "is_deleted", False))]
            assert len(active) == 1

    def test_p7_skip_manual_override_locked(self):
        """已锁定（_manual_override=True）章节进 skipped，provenance 不被覆盖。"""
        locked = _FakeNote(
            note_section="sec_locked",
            is_deleted=False,
            table_data={"_manual_override": True},
            source_project_id=None,
            consolidation_breakdown=None,
            last_sync_source=None,
        )
        db = _FakeSession(existing=[locked])
        r = _run(
            _persist_consol_sections_v2(
                db, _PID, _YEAR, _sections(["sec_locked"]), "soe"
            )
        )
        assert r["skipped"] == 1
        assert r["upserted"] == 0
        # provenance 三字段未被触碰
        assert locked.source_project_id is None
        assert locked.consolidation_breakdown is None
        assert locked.last_sync_source is None
        assert len(db.added) == 0

    def test_p7_sub_table_manual_override_locked(self):
        """子表 _manual_override 标记同样锁定（_detect_manual_override 双位判定）。"""
        locked = _FakeNote(
            note_section="sec_sub_locked",
            is_deleted=False,
            table_data={"sub_table_data": {"_manual_override": True}},
            last_sync_source=None,
        )
        db = _FakeSession(existing=[locked])
        r = _run(
            _persist_consol_sections_v2(
                db, _PID, _YEAR, _sections(["sec_sub_locked"]), "soe"
            )
        )
        assert r["skipped"] == 1 and r["upserted"] == 0
        assert locked.last_sync_source is None

    def test_p7_soft_deleted_revived_not_fresh_insert(self):
        """软删章节被复活复用（is_deleted→False + 更 provenance），不 fresh INSERT。"""
        deleted = _FakeNote(
            note_section="sec_del",
            is_deleted=True,
            table_data={"rows": [{"label": "x"}]},  # 非锁定
            source_project_id=None,
            consolidation_breakdown=None,
            last_sync_source=None,
        )
        db = _FakeSession(existing=[deleted])
        r = _run(
            _persist_consol_sections_v2(
                db, _PID, _YEAR, _sections(["sec_del"]), "soe"
            )
        )
        assert r["upserted"] == 1
        assert r["errors"] == []
        assert deleted.is_deleted is False  # 复活
        assert deleted.source_project_id == _PID
        assert deleted.consolidation_breakdown == {"by_company": [{"code": "sec_del", "amount": "1"}]}
        assert deleted.last_sync_source == "consolidation"
        # 关键：未 fresh INSERT（否则唯一键 (project,year,section) 撞键 500）
        assert len(db.added) == 0

    def test_p7_empty_section_id_skipped(self):
        """空 section_id 进 skipped，不新建、不报错。"""
        db = _FakeSession()
        r = _run(
            _persist_consol_sections_v2(
                db, _PID, _YEAR, [{"section_id": "  ", "consolidation_breakdown": {}}], "soe"
            )
        )
        assert r["skipped"] == 1 and r["upserted"] == 0 and r["errors"] == []
        assert len(db.added) == 0


# ===========================================================================
# Property 8 — V2 fail-open
# ===========================================================================


class TestProperty8FailOpen:
    """Property 8：单章节落库异常时其余章节仍落库，函数不 raise。

    **Validates: Requirements 3.5**
    """

    def test_p8_middle_section_error_others_persist(self):
        """中间章节抛异常 → 首尾照常落库，errors 记录失败章节，不 raise。"""
        db = _FakeSession(poison_section="sec_bad")
        sections = _sections(["sec_1", "sec_bad", "sec_3"])
        r = _run(_persist_consol_sections_v2(db, _PID, _YEAR, sections, "soe"))

        assert r["upserted"] == 2  # sec_1 / sec_3 落库
        assert len(r["errors"]) == 1
        assert r["errors"][0]["section_id"] == "sec_bad"
        assert "error" in r["errors"][0]
        assert {n.note_section for n in db.added} == {"sec_1", "sec_3"}
        assert db.commit_count == 1  # 末尾仍提交一次

    @given(
        ids=st.lists(_section_id, min_size=2, max_size=6, unique=True),
        poison_idx=st.integers(min_value=0, max_value=5),
    )
    @hyp_settings(max_examples=20)
    def test_p8_arbitrary_poison_position(self, ids, poison_idx):
        """任意位置的毒章节：仅它进 errors，其余全落库，函数不抛。"""
        poison = ids[poison_idx % len(ids)]
        db = _FakeSession(poison_section=poison)
        r = _run(_persist_consol_sections_v2(db, _PID, _YEAR, _sections(ids), "soe"))

        assert len(r["errors"]) == 1
        assert r["errors"][0]["section_id"] == poison
        assert r["upserted"] == len(ids) - 1
        assert poison not in {n.note_section for n in db.added}
        assert len(db.added) == len(ids) - 1

    def test_p8_commit_failure_records_error_no_raise(self):
        """commit 异常被 fail-open 捕获（记 __commit__ error + rollback），不 raise。"""
        db = _FakeSession(commit_error=True)
        r = _run(_persist_consol_sections_v2(db, _PID, _YEAR, _sections(["sec_x"]), "soe"))
        assert any(e["section_id"] == "__commit__" for e in r["errors"])
        assert db.rollback_count == 1


# ===========================================================================
# Property 9 — V2 开关关零改动
# ===========================================================================


class TestProperty9SwitchOff:
    """Property 9：CONSOL_NOTES_V2_ENABLED=False 时不落库（不调 persist）。

    **Validates: Requirements 3.3, 6.1**
    """

    @pytest.mark.asyncio
    async def test_p9_switch_off_no_persist_called(self, monkeypatch):
        """开关关：generate_full_consol_notes 不调用 _persist_consol_sections_v2。"""
        monkeypatch.setattr(settings, "CONSOL_NOTES_V2_ENABLED", False, raising=False)
        db = AsyncMock()
        with patch(
            "app.services.consol_disclosure_service._fetch_subsidiary_list",
            return_value=[{"project_id": uuid4(), "company_code": "S1",
                           "company_name": "子A", "consol_level": 2}],
        ), patch(
            "app.services.consol_disclosure_service._load_section_mapping",
            return_value=[],
        ), patch(
            "app.services.consol_note_aggregation_service.get_lineage_chain",
            return_value=[_PID],
        ), patch(
            "app.services.consol_disclosure_service._persist_consol_sections_v2",
            new_callable=AsyncMock,
        ) as spy:
            await generate_full_consol_notes(db, _PID, _YEAR)

        spy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_p9_switch_on_persist_called_once(self, monkeypatch):
        """开关开：generate_full_consol_notes 调用一次 _persist_consol_sections_v2。"""
        monkeypatch.setattr(settings, "CONSOL_NOTES_V2_ENABLED", True, raising=False)
        db = AsyncMock()
        with patch(
            "app.services.consol_disclosure_service._fetch_subsidiary_list",
            return_value=[{"project_id": uuid4(), "company_code": "S1",
                           "company_name": "子A", "consol_level": 2}],
        ), patch(
            "app.services.consol_disclosure_service._load_section_mapping",
            return_value=[],
        ), patch(
            "app.services.consol_note_aggregation_service.get_lineage_chain",
            return_value=[_PID],
        ), patch(
            "app.services.consol_disclosure_service._persist_consol_sections_v2",
            new_callable=AsyncMock,
        ) as spy:
            await generate_full_consol_notes(db, _PID, _YEAR)

        spy.assert_awaited_once()


# ===========================================================================
# Property 10 — V2 落库激活穿透
# ===========================================================================


class _DrilldownFakeResult:
    """模拟 db.execute 返回的 Result 对象，用于 drilldown service 的 _load_note。"""

    def __init__(self, note):
        self._note = note

    def scalar_one_or_none(self):
        return self._note


class _DrilldownFakeSession:
    """Drilldown 穿透查询的 fake session：按 section_id/note_section 匹配。"""

    def __init__(self, notes: list):
        self._notes = notes

    async def execute(self, stmt):
        """从 stmt 的 whereclause 提取 section_id/note_section 条件匹配。"""
        where = getattr(stmt, "whereclause", None)
        clauses = getattr(where, "clauses", None) or ([where] if where is not None else [])
        target_section = None
        for cl in clauses:
            left = getattr(cl, "left", None)
            right = getattr(cl, "right", None)
            key = getattr(left, "key", None) if left is not None else None
            if key in ("section_id", "note_section"):
                target_section = getattr(right, "value", None)
        if target_section is not None:
            for n in self._notes:
                sid = getattr(n, "section_id", None)
                ns = getattr(n, "note_section", None)
                if sid == target_section or ns == target_section:
                    if not getattr(n, "is_deleted", False):
                        return _DrilldownFakeResult(n)
        return _DrilldownFakeResult(None)


class _DrilldownFakeNote:
    """附注行替身：带 section_id/note_section/consolidation_breakdown/section_title。"""

    def __init__(self, **kw):
        self.section_id = kw.get("section_id")
        self.note_section = kw.get("note_section")
        self.consolidation_breakdown = kw.get("consolidation_breakdown")
        self.section_title = kw.get("section_title")
        self.is_deleted = kw.get("is_deleted", False)


class TestProperty10DrilldownActivation:
    """Property 10：落库后 note_consol_drilldown_service 对已落库章节返回 has_breakdown=true 且 by_company 非空。

    **Validates: Requirements 3.1, 3.2**

    验证逻辑：
    1. 模拟 `_persist_consol_sections_v2` 已写入 `consolidation_breakdown` 到 disclosure_notes
    2. 调用 drilldown service 的 `get_note_consol_breakdown`
    3. 断言 `has_breakdown == True` 且 `by_company` 非空
    """

    def test_p10_persisted_note_has_breakdown_true(self):
        """落库后的章节（有 by_company 列表）→ drilldown 返回 has_breakdown=True。"""
        breakdown = {
            "by_company": [
                {"code": "S1", "company_name": "子公司A", "amount": "100"},
                {"code": "S2", "company_name": "子公司B", "amount": "200"},
            ],
            "computed_at": "2025-12-31T00:00:00",
        }
        note = _DrilldownFakeNote(
            section_id="五、1",
            note_section="五、1",
            consolidation_breakdown=breakdown,
            section_title="货币资金",
        )
        db = _DrilldownFakeSession(notes=[note])

        result = _run(get_note_consol_breakdown(db, _PID, _YEAR, "五、1"))

        assert result["has_breakdown"] is True
        assert len(result["by_company"]) == 2
        assert result["by_company"][0]["code"] == "S1"
        assert result["by_company"][1]["code"] == "S2"
        assert result["section_title"] == "货币资金"
        assert result["message"] is None
        assert result["computed_at"] == "2025-12-31T00:00:00"

    def test_p10_empty_breakdown_returns_false(self):
        """未落库/breakdown 为空 → has_breakdown=False + 友好提示。"""
        note = _DrilldownFakeNote(
            section_id="五、2",
            note_section="五、2",
            consolidation_breakdown=None,
            section_title="交易性金融资产",
        )
        db = _DrilldownFakeSession(notes=[note])

        result = _run(get_note_consol_breakdown(db, _PID, _YEAR, "五、2"))

        assert result["has_breakdown"] is False
        assert result["by_company"] == []
        assert result["message"] is not None

    def test_p10_note_not_found_returns_false(self):
        """章节不存在 → has_breakdown=False（EH1 友好空返回）。"""
        db = _DrilldownFakeSession(notes=[])

        result = _run(get_note_consol_breakdown(db, _PID, _YEAR, "五、99"))

        assert result["has_breakdown"] is False
        assert result["by_company"] == []
        assert result["message"] is not None

    @given(
        company_codes=st.lists(
            st.text(alphabet=string.ascii_uppercase + string.digits, min_size=1, max_size=5),
            min_size=1,
            max_size=10,
            unique=True,
        )
    )
    @hyp_settings(max_examples=5)
    def test_p10_arbitrary_by_company_activates_drilldown(self, company_codes):
        """任意非空 by_company 列表 → has_breakdown=True 且 by_company 数量一致。"""
        breakdown = {
            "by_company": [{"code": c, "amount": str(i * 100)} for i, c in enumerate(company_codes, 1)],
        }
        note = _DrilldownFakeNote(
            section_id="sec_test",
            note_section="sec_test",
            consolidation_breakdown=breakdown,
            section_title="测试章节",
        )
        db = _DrilldownFakeSession(notes=[note])

        result = _run(get_note_consol_breakdown(db, _PID, _YEAR, "sec_test"))

        assert result["has_breakdown"] is True
        assert len(result["by_company"]) == len(company_codes)
        assert result["message"] is None

    def test_p10_end_to_end_persist_then_drilldown(self):
        """端到端：_persist_consol_sections_v2 落库(update分支) → drilldown 读到 breakdown。

        模拟完整链路：预置一条 active note（使 persist 走 update 分支，规避
        新建分支对 SourceTemplate.consolidated 枚举的依赖），验证 persist 写入
        consolidation_breakdown 后 drilldown 返回 has_breakdown=True。
        """
        # 预置 active note（persist 命中后走 update 分支，不走 INSERT+SourceTemplate）
        existing_note = _FakeNote(
            note_section="五、10",
            is_deleted=False,
            table_data={"rows": []},  # 非锁定
            source_project_id=None,
            consolidation_breakdown=None,
            last_sync_source=None,
        )
        db_persist = _FakeSession(existing=[existing_note])
        sections = [
            {
                "section_id": "五、10",
                "consolidation_breakdown": {
                    "by_company": [
                        {"code": "SUB01", "company_name": "全资子公司", "amount": "5000"},
                    ],
                },
            }
        ]

        # Step 1: persist 写入（update 分支：仅更 provenance，不建新行）
        r = _run(_persist_consol_sections_v2(db_persist, _PID, _YEAR, sections, "listed"))
        assert r["upserted"] == 1
        assert r["errors"] == []

        # Step 2: 验证 persist 确实写入了 consolidation_breakdown
        assert existing_note.consolidation_breakdown is not None
        assert existing_note.consolidation_breakdown["by_company"][0]["code"] == "SUB01"
        assert existing_note.source_project_id == _PID
        assert existing_note.last_sync_source == "consolidation"

        # Step 3: drilldown 读取同一行（模拟 DB 读回已落库的 note）
        drilldown_note = _DrilldownFakeNote(
            section_id="五、10",
            note_section="五、10",
            consolidation_breakdown=existing_note.consolidation_breakdown,
            section_title=getattr(existing_note, "section_title", "已落库章节"),
        )
        db_drilldown = _DrilldownFakeSession(notes=[drilldown_note])

        result = _run(get_note_consol_breakdown(db_drilldown, _PID, _YEAR, "五、10"))

        assert result["has_breakdown"] is True
        assert len(result["by_company"]) == 1
        assert result["by_company"][0]["code"] == "SUB01"
        assert result["by_company"][0]["amount"] == "5000"
        assert result["message"] is None
