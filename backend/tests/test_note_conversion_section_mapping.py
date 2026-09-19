"""章节映射守卫 — Property 5~10 / 16~19 / 24~26 / 35 / 36.

spec: soe-listed-note-conversion-correctness / Task 11
（Requirements 4.1, 4.2, 4.3, 6.4；连带 2.1~2.8）

------------------------------------------------------------------------------
本文件与 Task 10 两个文件的分工（不得互相重复断言）
------------------------------------------------------------------------------

============================================================  ==================================
文件                                                          定位
============================================================  ==================================
``tests/services/test_note_conversion_section_mapping_production.py``  Task 10：**承接已删除 v2 的
                                                              21 条断言**（逐例迁移，判据是
                                                              「单个章节被正确处理」）
``tests/test_note_conversion_v2_removal.py``                  Task 10：**删除收口**（v2 符号归零
                                                              + 迁移表双向锁死 + Property 24 判据
                                                              的**唯一实现**）
``tests/test_note_conversion_section_mapping.py``（本文件）    Task 11：**Property 级不变式守卫**
                                                              （判据是「一次运行结束后全体章节
                                                              满足的性质」+ 场景级反向自检）
============================================================  ==================================

故本文件刻意**不写**「某个章节的 section_id 变成了 X」这类单例断言（Task 10 已有），
改写成**全量扫描后的不变式**（例如「所有落在 pairs 里的章节，改写后 sid 一律属于目标
侧取值集合，且 note_section 一律等于目标模板的 section_number」）——单例断言挡不住
「只对第一个章节生效」的实现，不变式可以。

🔴 **Property 24 只引用不重造**。判据实现（``_service_methods`` /
``_method_names_under_scan`` / ``_non_test_call_sites``）在
``tests/test_note_conversion_v2_removal.py``，本文件 import 它。同一不变式两处实现
= 双真源（改一处另一处不红），平台已多次踩过。

🔴 **Property 25 不作为验收判据**。design.md 明写它是「接线分支」的判据，而 Task 10
裁决为**删除不接线** ⇒ 本文件只留说明性断言（v2 符号确实不在服务类上），不据它新建
任何 v2 相关实现。

🔴 **Property 26 只做轻断言**。迁移表的双向锁死（覆盖全部 21 个 v2 测试 / 无孤儿生产
测试 / 条目上限 / 理由质量闸）已在 v2_removal 文件里，本文件只断言「迁移表存在且已覆盖
被删测试」，不重复。

------------------------------------------------------------------------------
为什么用内存替身而不是真实库
------------------------------------------------------------------------------

Requirement 10.6 明令禁止为凑验收改动真实项目的 ``template_type``（会触发
``execute_full_chain(force=True)`` 全链重算）。真实库验收归 Task 19。本文件走内存
替身，但**全部判据数据取自真实 diff + 真实两份模板 JSON**（章节 sid / 章节号 / 标题
一律从 ``load_diff_data()`` 与 ``load_template_sections()`` 现取，不自造），故仍是对
生产逻辑的有效验证。替身本身复用 Task 10 已建的 ``FakeSession`` / ``make_note``
（同一替身两份实现即双真源）。

🔴 ``_Savepoint.__aexit__`` 必须 ``return False``（不吞异常）—— 否则
「失败章节进 failed 桶」这条根本测不出来。该纪律由 Task 10 的替身承载，本文件
``test_savepoint_replica_does_not_swallow`` 反向钉死它（替身被改坏时打红）。
"""
from __future__ import annotations

import copy
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest

from app.services.note_conversion_service import (
    MAP_NOTES_PENDING_KEYS,
    SKIP_REASON_SID_AMBIGUOUS,
    SKIP_REASON_SID_UNRESOLVED,
    SKIP_REASON_TARGET_SID_OCCUPIED,
    SKIP_REASON_UNKNOWN_SECTION,
    NoteConversionService,
    archive_reason,
    count_manual_cells,
)
from app.services.note_section_matcher import normalize_for_match
from app.services.note_template_diff import load_diff_data, load_template_sections

# --- 复用 Task 10 的内存替身（禁止在本文件再造一份）------------------------------
from tests.services.test_note_conversion_section_mapping_production import (  # noqa: E402
    PROJECT,
    YEAR,
    FakeSession,
    make_note,
)

# --- 复用 Task 10 的 Property 24 判据实现（同一不变式只许一处实现）--------------
from tests.test_note_conversion_v2_removal import (  # noqa: E402
    ASSERTION_MIGRATION,
    CONVERSION_SERVICE,
    REMOVED_SYMBOLS,
    _method_names_under_scan,
    _non_test_call_sites,
    _service_methods,
)


# ---------------------------------------------------------------------------
# 真实判据数据
# ---------------------------------------------------------------------------


def _sections_by_sid(side: str) -> dict[str, dict[str, Any]]:
    return {
        s["section_id"]: s
        for s in load_template_sections(side)
        if isinstance(s, dict) and s.get("section_id")
    }


class _Fx:
    """从真实 diff + 真实模板派生本文件全部判据数据。

    刻意**不硬编码**任何 sid / 章节号 / 标题：模板一改，候选自动跟随；候选为空即
    断言失败（判据失效必须打红，不能静默空转）。
    """

    def __init__(self) -> None:
        self.diff = load_diff_data()
        svc = NoteConversionService(FakeSession([]))
        self.plan = svc._build_section_mapping_plan(self.diff, "soe", "listed")
        self.plan_rev = svc._build_section_mapping_plan(self.diff, "listed", "soe")
        self.soe = _sections_by_sid("soe")
        self.listed = _sections_by_sid("listed")
        self.backfill = svc._build_sid_backfill_index(list(self.soe.values()))

        # 归一化标题 -> 源侧 sid 数（回填歧义判据用）
        title_counts: dict[str, list[str]] = {}
        for sid, sec in self.soe.items():
            key = normalize_for_match(sec.get("section_title"))
            if key:
                title_counts.setdefault(key, []).append(sid)
        self._title_counts = title_counts

        unique_nt = {k for k, v in self.backfill["by_number_title"].items() if len(v) == 1}
        unique_t = {k for k, v in self.backfill["by_title"].items() if len(v) == 1}

        # 候选 pair：两侧都有章节号、两侧章节号不同、源侧 (number,title) 与 title 均唯一
        cands: list[dict[str, Any]] = []
        for src_sid, pair in self.plan["pairs"].items():
            ss = self.soe.get(src_sid)
            ls = self.listed.get(pair["target_sid"])
            if not ss or not ls:
                continue
            src_num = ss.get("section_number")
            tgt_num = ls.get("section_number")
            if not src_num or not tgt_num or src_num == tgt_num:
                continue
            title = normalize_for_match(ss.get("section_title"))
            num = normalize_for_match(src_num)
            if f"{num}\x00{title}" not in unique_nt or title not in unique_t:
                continue
            cands.append(
                {
                    "src_sid": src_sid,
                    "tgt_sid": pair["target_sid"],
                    "src_num": src_num,
                    "tgt_num": tgt_num,
                    "title": ss.get("section_title") or "",
                    "via": pair["via"],
                }
            )
        assert len(cands) >= 3, (
            "真实 diff/模板里找不到 3 对「两侧章节号不同且源侧回填键唯一」的共有章节 "
            "-- 本文件的全部映射判据失效，先查 note_soe_listed_diff.json 与两份模板"
        )

        # 别名桥接（Property 5 的 via='alias' 分支）—— 先取，好让它的章节号参与占位排除
        assert self.plan["bridged"], "真实 diff 里别名桥接为空 -- Property 5 的别名分支判据失效"
        bridged_ok = [
            b for b in self.plan["bridged"]
            if (self.soe.get(b["source_sid"]) or {}).get("section_number")
            and (self.listed.get(b["target_sid"]) or {}).get("section_number")
        ]
        assert bridged_ok, "别名桥接的两侧都缺 section_number -- Property 5 别名分支判据失效"
        self.bridged = bridged_ok[0]
        self.bridged_src_num = self.soe[self.bridged["source_sid"]]["section_number"]
        self.bridged_tgt_num = self.listed[self.bridged["target_sid"]]["section_number"]

        # 避免替身里自造的章节号互相占位（真实库靠
        # uq_disclosure_notes_project_year_section 保证唯一，替身不保证）：
        # 所选源章节号与目标章节号两两不得相交，且不得与别名桥接那对相交。
        picked: list[dict[str, Any]] = []
        used: set[str] = {self.bridged_src_num, self.bridged_tgt_num}
        for c in cands:
            if c["src_num"] in used or c["tgt_num"] in used:
                continue
            picked.append(c)
            used.update({c["src_num"], c["tgt_num"]})
            if len(picked) == 3:
                break
        assert len(picked) == 3, "候选 pair 的章节号互相占位，无法取到 3 对互不冲突的"
        self.c0, self.c1, self.c2 = picked

        # 源侧独有（Property 7 归档）—— 章节号同样不得与上面已用的相交
        src_only = sorted(
            sid for sid in self.plan["source_only"]
            if (self.soe.get(sid) or {}).get("section_number")
            and self.soe[sid]["section_number"] not in used
        )
        assert src_only, "真实 diff 里 source_only 无可用（带章节号且不占位）条目 -- Property 7 判据失效"
        self.archive_sid = src_only[0]
        self.archive_num = self.soe[self.archive_sid]["section_number"]
        used.add(self.archive_num)

        # 目标侧独有（Property 8 新建）
        tgt_only = sorted(
            sid for sid in self.plan["target_only"]
            if (self.listed.get(sid) or {}).get("section_number")
            and self.listed[sid]["section_number"] not in used
        )
        assert tgt_only, "真实 diff 里 target_only 无可用（带章节号且不占位）条目 -- Property 8 判据失效"
        self.create_sid = tgt_only[0]
        self.create_num = self.listed[self.create_sid]["section_number"]
        used.add(self.create_num)
        self.used_numbers = frozenset(used)

        # 回填歧义（Property 36 的 SID_AMBIGUOUS 分支）
        amb = sorted(k for k, v in self._title_counts.items() if len(v) > 1)
        assert amb, "源侧模板无同名章节 -- Property 36 的歧义分支判据失效"
        amb_key = amb[0]
        self.ambiguous_title = (
            self.soe[self._title_counts[amb_key][0]].get("section_title") or ""
        )

    # -- 派生工具 ----------------------------------------------------------

    def empty_diff(self, *, keep_source_only: bool = False) -> dict[str, Any]:
        """构造「零共有章节」的 diff（Property 16）。

        ``keep_source_only=True`` 时保留源独有清单，用于「零共有 + 有归档」场景 ——
        证明 ``mapped`` 只统计**改写**，不把归档/新建混进去。
        """
        d = copy.deepcopy(self.diff)
        d["common_sections"] = []
        d["format_diff_sections"] = []
        d["listed_only_sections"] = []
        if not keep_source_only:
            d["soe_only_sections"] = []
        return d


@pytest.fixture(scope="module")
def fx() -> _Fx:
    return _Fx()


# ---------------------------------------------------------------------------
# 运行器
# ---------------------------------------------------------------------------


class Scenario:
    """跑一次 ``_map_disclosure_notes``，把入参/替身/结果收在一处。"""

    def __init__(
        self,
        notes: list[Any],
        *,
        diff: dict[str, Any] | None = None,
        current_type: str = "soe",
        target_type: str = "listed",
    ) -> None:
        self.notes_in = list(notes)
        self.session = FakeSession(notes)
        self.svc = NoteConversionService(self.session)
        self.diff = diff
        self.current_type = current_type
        self.target_type = target_type
        self.result: dict[str, Any] = {}

    async def run(self, *, fail_note_ids: set[UUID] | None = None) -> dict[str, Any]:
        """执行映射。

        ``fail_note_ids`` 按 **note id 精确匹配**注入一次「写入异常」（Requirement 4.3）。

        🔴 为什么不用 ``FakeSession(flush_fail_on=...)``：那个替身的 ``flush`` 判据是
        「``self.notes`` 里存在被标记的 note」，与「当前正在处理谁」无关 ⇒ 处理**健康**
        章节时的 flush 也会抛，健康章节被连带打死，于是「其余仍处理」这半边永远测不出来
        （Task 10 的 ``test_single_failure_does_not_block_others`` 只能验「进 failed 桶」
        那半边，正是这个成因）。改为在 ``_record_lineage``（真实写入路径，位于逐章
        savepoint 之内）上按 note id 精确抛。
        """
        ids = fail_note_ids or set()
        original = NoteConversionService.__dict__["_record_lineage"].__func__

        def _lineage(note: Any, **kwargs: Any) -> bool:
            if getattr(note, "id", None) in ids:
                raise RuntimeError(f"injected lineage write failure for {note.id}")
            return original(note, **kwargs)

        ctxs: list[Any] = [
            patch.object(NoteConversionService, "_record_lineage", staticmethod(_lineage))
        ]
        if self.diff is not None:
            ctxs.append(
                patch(
                    "app.services.note_template_diff.load_diff_data",
                    return_value=self.diff,
                )
            )
        try:
            for ctx in ctxs:
                ctx.__enter__()
            self.result = await self.svc._map_disclosure_notes(
                PROJECT, YEAR, self.current_type, self.target_type
            )
        finally:
            for ctx in reversed(ctxs):
                ctx.__exit__(None, None, None)
        return self.result

    # -- 结果视图 ----------------------------------------------------------

    @property
    def live(self) -> list[Any]:
        return [n for n in self.session.notes if not n.is_deleted]

    @property
    def skipped_ids(self) -> set[str]:
        return {i["note_id"] for i in self.result.get("skipped", []) if i.get("note_id")}

    @property
    def failed_ids(self) -> set[str]:
        return {i["note_id"] for i in self.result.get("failed", []) if i.get("note_id")}

    def skip_reason_of(self, note: Any) -> str | None:
        for item in self.result.get("skipped", []):
            if item.get("note_id") == str(note.id):
                return item.get("reason")
        return None

    def legacy_count_star_mapped(self) -> int:
        """复现**改造前**的实现：``SELECT count(*)`` 当 ``mapped`` 上报。

        Property 16 的反向自检用：该值在「零共有章节」场景里必须 > 0，否则那个场景
        对「count(*) 冒充」不敏感（断言等于空转）。
        """
        return len([n for n in self.notes_in if not n.is_deleted])


# ---------------------------------------------------------------------------
# 通用不变式检查器
# ---------------------------------------------------------------------------


def collect_binding_prefixes(node: Any) -> set[str]:
    """收集 ``table_data`` 内全部 ``binding_id`` 的章节号前缀（首个 ``.`` 之前）。

    ``binding_id`` 形态是「章节号.行标签.列键」（实测 1030 个未软删章节中 446 条带
    binding）。binding 分布在多个层级（``rows`` / ``_tables[].rows`` /
    ``sub_table_data``），故递归收集而不是只扫固定路径。
    """
    out: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "binding_id" and isinstance(value, str) and "." in value:
                out.add(value.split(".", 1)[0])
            else:
                out |= collect_binding_prefixes(value)
    elif isinstance(node, list):
        for item in node:
            out |= collect_binding_prefixes(item)
    return out


def assert_no_orphaned_binding(note: Any, old_number: str) -> None:
    """Property 35 的不变式：不得留下「前缀指向旧章节号而 lineage 无记录」的绑定。

    两种合法终态：前缀已同步改写 / 前缀仍是旧章节号但
    ``template_lineage.legacy_note_sections`` 记了它（供解析回退）。
    """
    prefixes = collect_binding_prefixes(note.table_data)
    lineage = note.template_lineage if isinstance(note.template_lineage, dict) else {}
    legacy = set(lineage.get("legacy_note_sections") or [])
    if old_number in prefixes and old_number not in legacy:
        raise AssertionError(
            f"note {note.id} 的 binding_id 仍以旧章节号 {old_number!r} 为前缀，"
            f"而 template_lineage.legacy_note_sections={sorted(legacy)} 未记录它 "
            "-- binding 已失联（Requirement 2.7 / Property 35）"
        )


# ===========================================================================
# 判据自检 —— 扫描面/替身纪律非空，否则下面全部断言是空转
# ===========================================================================


class TestGuardSanity:
    """判据本身有效性自检（缺了这层，判据失效会表现为「全绿」）。"""

    def test_diff_and_templates_are_non_empty(self, fx: _Fx) -> None:
        assert fx.diff.get("is_mock") is False, "落盘 diff 仍是 mock -- 判据数据不可信"
        for bucket in (
            "common_sections",
            "soe_only_sections",
            "listed_only_sections",
            "format_diff_sections",
        ):
            assert fx.diff.get(bucket), f"diff 的 {bucket} 为空 -- 判据失效"
        assert len(fx.soe) > 100 and len(fx.listed) > 100, "模板章节数异常偏少 -- 判据失效"
        assert fx.plan["pairs"], "映射计划的 pairs 为空 -- Property 5/6/16 判据失效"
        assert fx.plan["source_only"], "source_only 为空 -- Property 7 判据失效"
        assert fx.plan["target_only"], "target_only 为空 -- Property 8 判据失效"

    @pytest.mark.asyncio
    async def test_savepoint_replica_does_not_swallow_exceptions(self) -> None:
        """反向钉死 Task 10 替身的纪律：``__aexit__`` 不得吞异常。

        替身若 ``return True``，「失败章节进 failed 桶」（Property 18）会静默变绿 ——
        异常被 savepoint 吃掉，生产代码的 ``except`` 永远收不到。
        """
        sess = FakeSession([])
        with pytest.raises(RuntimeError):
            async with sess.begin_nested():
                raise RuntimeError("must propagate")

    def test_binding_prefix_collector_finds_nested_bindings(self) -> None:
        """收集器自检：三处容器（``rows`` / ``_tables[].rows`` / ``sub_table_data``）都要覆盖。"""
        td = {
            "rows": [{"binding_id": "甲、1.行A.closing"}],
            "_tables": [{"rows": [{"binding_id": "乙、2.行B.opening"}]}],
            "sub_table_data": {"t": [{"binding_id": "丙、3.行C.v"}]},
        }
        assert collect_binding_prefixes(td) == {"甲、1", "乙、2", "丙、3"}


# ===========================================================================
# Property 5 / 6 —— 共有章节改写的**全量不变式**
# ===========================================================================


def _pair_note(fx: _Fx, c: dict[str, Any], **kw: Any) -> Any:
    """按候选 pair 造一条共有章节记录（sid/章节号/标题全取真实模板值）。

    ``section_title`` 允许调用方覆盖（用于在断言消息里区分同源多条记录）。
    """
    kw.setdefault("section_title", c["title"])
    return make_note(section_id=c["src_sid"], note_section=c["src_num"], **kw)


class TestProperty5And6_RewriteInvariant:
    """Property 5：共有章节 ``section_id`` 被真正改写、``note_section`` 同步改写。
    Property 6：源侧 sid 进 ``template_lineage.legacy_section_ids``。

    与 Task 10 的分工：那边断言「某一个章节被改成了 X」；本类断言**一次运行后全体
    章节满足的不变式** —— 单例断言挡不住「只对第一个章节生效」的实现。
    """

    @pytest.mark.asyncio
    async def test_every_mapped_section_lands_on_target_side(self, fx: _Fx) -> None:
        notes = [
            _pair_note(fx, fx.c0),
            _pair_note(fx, fx.c1),
            _pair_note(fx, fx.c2),
            # via='alias' 分支：措辞差异章节靠穷举配对桥接，不得走「归档 + 新建空章」
            make_note(
                section_id=fx.bridged["source_sid"],
                note_section=fx.bridged_src_num,
                section_title=fx.bridged["source_title"],
            ),
        ]
        # (note, 源 sid, 期望目标 sid, 期望目标章节号) —— 与 notes 一一对应
        expected = [
            (notes[0], fx.c0["src_sid"], fx.c0["tgt_sid"], fx.c0["tgt_num"]),
            (notes[1], fx.c1["src_sid"], fx.c1["tgt_sid"], fx.c1["tgt_num"]),
            (notes[2], fx.c2["src_sid"], fx.c2["tgt_sid"], fx.c2["tgt_num"]),
            (
                notes[3],
                fx.bridged["source_sid"],
                fx.bridged["target_sid"],
                fx.bridged_tgt_num,
            ),
        ]
        sc = Scenario(notes)
        res = await sc.run()

        assert res["mapped"] == len(notes), (
            f"mapped={res['mapped']} 与投入的共有章节数 {len(notes)} 不符；"
            f"skipped={res.get('skipped_reasons')} failed={res['failed']}"
        )
        # 不变式 1：每个投入的章节都落到**它自己**的目标侧取值（不是「某个」目标值）
        for note, src_sid, tgt_sid, tgt_num in expected:
            assert note.section_id == tgt_sid, (
                f"章节 {src_sid} 的 section_id 未改写为目标侧 {tgt_sid}（实为 {note.section_id}）"
            )
            assert note.note_section == tgt_num, (
                f"章节 {src_sid} 的 note_section 未同步改写为 {tgt_num}"
                f"（实为 {note.note_section}）-- 列名是 note_section 不是 section_number"
            )
            assert not note.is_deleted, "共有章节不得被软删"

        # 不变式 2：全体未软删章节的 sid 里，不得再出现任何源侧取值
        live_sids = {n.section_id for n in sc.live if n.section_id}
        leftovers = live_sids & {src for _, src, _, _ in expected}
        assert not leftovers, f"改写后仍残留源侧 sid: {sorted(leftovers)}"

    @pytest.mark.asyncio
    async def test_legacy_section_ids_recorded_for_every_mapped(self, fx: _Fx) -> None:
        notes = [_pair_note(fx, fx.c0), _pair_note(fx, fx.c1)]
        sc = Scenario(notes)
        await sc.run()

        for note, c in zip(notes, (fx.c0, fx.c1)):
            lineage = note.template_lineage or {}
            assert c["src_sid"] in (lineage.get("legacy_section_ids") or []), (
                f"源侧 sid {c['src_sid']} 未进 template_lineage.legacy_section_ids"
                "（disclosure_notes 无 legacy_aliases 列，本 spec 无迁移故落 JSONB）"
            )
            assert lineage.get("conversions"), "转换方向未留痕（template_lineage.conversions）"

    @pytest.mark.asyncio
    async def test_alias_bridge_does_not_archive_and_recreate(self, fx: _Fx) -> None:
        """别名桥接的章节必须走「改写」而不是「归档 + 新建空章」（否则丢已录数据）。"""
        note = make_note(
            section_id=fx.bridged["source_sid"],
            note_section=fx.bridged_src_num,
            section_title=fx.bridged["source_title"],
            table_data={"rows": [{"label": "行A", "values": ["1"]}]},
        )
        sc = Scenario([note])
        res = await sc.run()

        assert res["mapped"] >= 1 and not note.is_deleted, (
            "别名桥接章节被归档了 -- 措辞差异章节会因此丢数据"
            f"（skipped={res.get('skipped_reasons')}）"
        )
        assert note.table_data == {"rows": [{"label": "行A", "values": ["1"]}]}, "已录数据被改动"
        assert (note.template_lineage or {}).get("alias_source_title"), "别名桥接未留源侧标题"


# ===========================================================================
# Property 7 —— 源独有章节归档留痕
# ===========================================================================


class TestProperty7_ArchiveTrace:
    @pytest.mark.asyncio
    async def test_source_only_archived_with_sid_and_reason(self, fx: _Fx) -> None:
        note = make_note(
            section_id=fx.archive_sid,
            note_section=fx.archive_num,
            section_title=(fx.soe[fx.archive_sid].get("section_title") or ""),
        )
        sc = Scenario([note])
        res = await sc.run()

        assert res["archived"] >= 1, f"源独有章节未归档（skipped={res.get('skipped_reasons')}）"
        assert note.is_deleted is True, (
            "归档必须靠 is_deleted -- status 枚举实测只有 draft/confirmed，没有 archived"
        )
        entries = (note.template_lineage or {}).get("archived_sections") or []
        hit = [e for e in entries if e.get("section_id") == fx.archive_sid]
        assert hit, f"archived_sections 未记录 {fx.archive_sid}：{entries}"
        assert hit[0].get("reason") == archive_reason("soe", "listed"), (
            f"归档 reason 不符：{hit[0].get('reason')}"
        )
        assert hit[0].get("archived_at"), "archived_sections 缺 archived_at"

    @pytest.mark.asyncio
    async def test_archive_is_idempotent_on_rerun(self, fx: _Fx) -> None:
        """重复归档不得把「归档一次」记成多次（去重按 (section_id, reason)）。"""
        note = make_note(section_id=fx.archive_sid, note_section=fx.archive_num)
        await Scenario([note]).run()
        first = copy.deepcopy((note.template_lineage or {}).get("archived_sections") or [])
        note.is_deleted = False  # 复现「再跑一次」
        await Scenario([note]).run()
        second = (note.template_lineage or {}).get("archived_sections") or []
        assert len(second) == len(first) == 1, (
            f"重复归档产生了 {len(second)} 条 archived_sections（应恒为 1）"
        )


# ===========================================================================
# Property 8 —— 目标独有章节被创建为空章节
# ===========================================================================


class TestProperty8_CreateTargetOnly:
    @pytest.mark.asyncio
    async def test_created_notes_are_empty_drafts_with_real_chapter_number(
        self, fx: _Fx
    ) -> None:
        sc = Scenario([])
        res = await sc.run()

        assert res["created"] > 0, f"目标独有章节一个都没建（skipped={res.get('skipped_reasons')}）"
        created = [n for n in sc.session.added]
        assert created, "db.add 未被调用"

        # 不变式：每个新建章节都是 is_empty=true / status='draft'，
        # 且 note_section 是**目标模板的真实 section_number**（不得写成 sid）
        for note in created:
            assert note.is_empty is True, f"新建章节 {note.section_id} 的 is_empty 不为 True"
            assert note.status == "draft", f"新建章节 {note.section_id} 的 status 不为 draft"
            assert note.section_id in fx.plan["target_only"], (
                f"新建了不属于 target_only 的章节 {note.section_id}"
            )
            expect_num = fx.listed[note.section_id].get("section_number")
            assert note.note_section == expect_num, (
                f"新建章节 {note.section_id} 的 note_section={note.note_section!r}，"
                f"应为目标模板的 section_number {expect_num!r}"
                "（写成 sid 会让界面与 Word 导出显示一串 slug）"
            )
            assert note.note_section != note.section_id, "note_section 被写成了 sid"
            assert (note.template_lineage or {}).get("created_by_conversion") == "soe_to_listed"

    @pytest.mark.asyncio
    async def test_create_is_idempotent_when_sid_already_present(self, fx: _Fx) -> None:
        """已存在该 sid 的未删除记录时不重复建（幂等重跑）。"""
        existing = make_note(section_id=fx.create_sid, note_section=fx.create_num)
        sc = Scenario([existing])
        res = await sc.run()
        assert fx.create_sid not in {n.section_id for n in sc.session.added}, (
            f"已存在 {fx.create_sid} 却仍新建了一遍 -- 会产生重复行"
        )
        reasons = {i["reason"] for i in res["skipped"] if i.get("section_id") == fx.create_sid}
        assert reasons, f"未新建却没登记原因（skipped 里查不到 {fx.create_sid}）"


# ===========================================================================
# Property 9 —— 人工编辑保留（值不变，不只是计数）
# ===========================================================================


class TestProperty9_ManualEditsPreserved:
    @pytest.mark.asyncio
    async def test_manual_cell_values_unchanged_through_rewrite(self, fx: _Fx) -> None:
        table_data = {
            "rows": [
                {
                    "label": "手工行",
                    "values": ["123.45", "678.90"],
                    "_cell_modes": {"0": "manual", "1": "auto"},
                    "binding_id": f"{fx.c0['src_num']}.手工行.closing_balance",
                },
                {
                    "label": "自动行",
                    "values": ["1"],
                    "_cell_modes": {"0": "auto"},
                },
            ],
            "sub_table_data": {
                "明细": [{"label": "子行", "values": ["9"], "_cell_modes": {"0": "manual"}}]
            },
        }
        before_manual = count_manual_cells(table_data)
        assert before_manual == 2, f"判据自检失败：构造的 manual 单元格应为 2，实为 {before_manual}"
        note = _pair_note(fx, fx.c0, table_data=copy.deepcopy(table_data))

        sc = Scenario([note])
        res = await sc.run()

        assert res["mapped"] == 1, f"章节未被改写（skipped={res.get('skipped_reasons')}）"
        assert res["user_edits_dropped"] == 0, (
            f"改写弄丢了 {res['user_edits_dropped']} 个 manual 单元格 -- 违反平台红线"
        )
        assert res["user_edits_preserved"] == before_manual, (
            f"user_edits_preserved={res['user_edits_preserved']}，应为 {before_manual}"
        )
        # 值不变（不只是计数不变）
        assert note.table_data["rows"][0]["values"] == ["123.45", "678.90"]
        assert note.table_data["rows"][0]["_cell_modes"] == {"0": "manual", "1": "auto"}
        assert note.table_data["sub_table_data"]["明细"][0]["values"] == ["9"]

    @pytest.mark.asyncio
    async def test_none_and_empty_table_data_are_safe(self, fx: _Fx) -> None:
        n1 = _pair_note(fx, fx.c0, table_data=None)
        n2 = _pair_note(fx, fx.c1, table_data={})
        sc = Scenario([n1, n2])
        res = await sc.run()
        assert res["mapped"] == 2, f"空/None table_data 导致映射失败：{res['failed']}"
        assert res["user_edits_preserved"] == 0
        assert res["user_edits_dropped"] == 0


# ===========================================================================
# Property 10 —— 无重复行
# ===========================================================================


class TestProperty10_NoDuplicateRows:
    @pytest.mark.asyncio
    async def test_no_duplicate_section_id_among_live_notes(self, fx: _Fx) -> None:
        """含**对抗构造**：两条同源 sid 的记录 + 一条已占目标 sid 的记录。"""
        dup_a = _pair_note(fx, fx.c0, section_title="重复A")
        dup_b = _pair_note(fx, fx.c0, section_title="重复B")
        dup_b.note_section = f"{fx.c0['src_num']}#B"  # 替身无唯一索引，避开章节号占位
        occupier = make_note(
            section_id=fx.c1["tgt_sid"],
            note_section=fx.c1["tgt_num"],
            section_title="已占目标 sid",
        )
        mover = _pair_note(fx, fx.c1, section_title="想搬到已被占的 sid")
        sc = Scenario([dup_a, dup_b, occupier, mover])
        res = await sc.run()

        live_sids = [n.section_id for n in sc.live if n.section_id]
        dupes = {s for s in live_sids if live_sids.count(s) > 1}
        assert not dupes, (
            f"转换后出现重复的 (project, year, section_id): {sorted(dupes)}"
            "（Requirement 2.6 / Property 10）"
        )
        # 对抗构造确实触发了占用检查（否则本测试是空转）
        assert SKIP_REASON_TARGET_SID_OCCUPIED in (res.get("skipped_reasons") or {}), (
            f"目标 sid 占用检查未触发，本测试对重复行不敏感：{res.get('skipped_reasons')}"
        )

    @pytest.mark.asyncio
    async def test_two_null_sid_rows_backfilling_to_same_sid_do_not_duplicate(
        self, fx: _Fx
    ) -> None:
        """两条 ``section_id IS NULL`` 的存量行回填到同一个 sid 时不得产生重复行。"""
        a = make_note(section_id=None, note_section=fx.c0["src_num"], section_title=fx.c0["title"])
        b = make_note(
            section_id=None,
            note_section=f"{fx.c0['src_num']}#B",
            section_title=fx.c0["title"],
        )
        sc = Scenario([a, b])
        res = await sc.run()

        assert res["sid_backfilled"] == 2, f"两条 NULL sid 未都被回填：{res['sid_backfilled']}"
        live_sids = [n.section_id for n in sc.live if n.section_id]
        dupes = {s for s in live_sids if live_sids.count(s) > 1}
        assert not dupes, f"回填制造了重复 sid: {sorted(dupes)}"


# ===========================================================================
# Property 16 —— mapped 反映真实映射数（零共有章节场景）
# ===========================================================================


class TestProperty16_MappedReflectsRealCount:
    """改造前的实现只 ``SELECT count(*)`` 返回**存量**章节数，一行不改，而该计数被当
    ``mapped_notes`` 上报给审计师（界面显示「已映射 N 个章节」而实际零映射）。

    「零共有章节」场景是唯一能把两者区分开的构造：存量行数 > 0 而真实映射数 == 0。
    """

    @pytest.mark.asyncio
    async def test_zero_common_sections_returns_mapped_zero(self, fx: _Fx) -> None:
        notes = [_pair_note(fx, fx.c0), _pair_note(fx, fx.c1), _pair_note(fx, fx.c2)]
        sc = Scenario(notes, diff=fx.empty_diff())
        res = await sc.run()

        assert res["mapped"] == 0, (
            f"零共有章节场景仍上报 mapped={res['mapped']} -- 这正是 count(*) 冒充的形态"
        )
        assert res["archived"] == 0 and res["created"] == 0
        # 三条记录都必须有明确处置（不得静默消失）
        assert len(res["skipped"]) == len(notes), (
            f"{len(notes)} 条记录只登记了 {len(res['skipped'])} 条处置"
        )
        assert set((res.get("skipped_reasons") or {})) == {SKIP_REASON_UNKNOWN_SECTION}, (
            f"跳过原因分布异常：{res.get('skipped_reasons')}"
        )

    @pytest.mark.asyncio
    async def test_count_star_impersonation_would_fail_this_scenario(self, fx: _Fx) -> None:
        """反向自检：该场景对「count(*) 冒充」必须敏感，否则上面那条断言是空转。"""
        notes = [_pair_note(fx, fx.c0), _pair_note(fx, fx.c1), _pair_note(fx, fx.c2)]
        sc = Scenario(notes, diff=fx.empty_diff())
        res = await sc.run()

        legacy = sc.legacy_count_star_mapped()
        assert legacy == len(notes) > 0, (
            "复现的旧实现（count(*)）在本场景返回 0，场景对该缺陷不敏感 -- 判据失效"
        )
        assert res["mapped"] != legacy, (
            f"真实映射数 {res['mapped']} 与 count(*) 值 {legacy} 相等，本场景无法区分二者"
        )

    @pytest.mark.asyncio
    async def test_archive_and_create_are_not_counted_as_mapped(self, fx: _Fx) -> None:
        """零共有 + 有归档：``mapped`` 只统计**改写**，归档/新建各归各的桶。"""
        note = make_note(section_id=fx.archive_sid, note_section=fx.archive_num)
        sc = Scenario([note], diff=fx.empty_diff(keep_source_only=True))
        res = await sc.run()

        assert res["mapped"] == 0, f"归档被算进了 mapped：{res['mapped']}"
        assert res["archived"] == 1, f"归档未计数：{res['archived']}"


# ===========================================================================
# Property 17 —— 返回结构分类齐备（类型与条目形状）
# ===========================================================================


class TestProperty17_ReturnShape:
    """Task 10 已断言五个键**存在**；本类补断言它们的**类型与条目形状**
    （键在而类型错，调用方一样拿不到可用信息）。"""

    @pytest.mark.asyncio
    async def test_five_categories_have_expected_types(self, fx: _Fx) -> None:
        notes = [
            _pair_note(fx, fx.c0),
            make_note(section_id=fx.archive_sid, note_section=fx.archive_num),
            make_note(section_id=None, note_section="零、无此章节号", section_title="无法回填XYZ"),
        ]
        sc = Scenario(notes)
        res = await sc.run()

        for key in ("mapped", "archived", "created"):
            assert isinstance(res[key], int), f"{key} 应为 int，实为 {type(res[key]).__name__}"
        for key in ("skipped", "failed"):
            assert isinstance(res[key], list), f"{key} 应为 list，实为 {type(res[key]).__name__}"
        assert res["skipped"], "本场景应产生至少一条 skipped（回填不出的 NULL sid 行）"
        for item in res["skipped"]:
            assert isinstance(item, dict) and item.get("reason"), f"skipped 条目缺 reason: {item}"
            assert {"note_id", "section_id", "note_section", "section_title"} <= set(item)
        # 未测量项纪律：Task 9 收口后不得再有 None = 未测量的键
        assert list(res["pending_keys"]) == list(MAP_NOTES_PENDING_KEYS) == []
        for key in ("archived", "created", "user_edits_preserved"):
            assert res[key] is not None, f"{key} 仍是 None（未测量）-- Task 9 应已填充"

    @pytest.mark.asyncio
    async def test_skipped_reasons_histogram_matches_skipped_list(self, fx: _Fx) -> None:
        notes = [_pair_note(fx, fx.c0), _pair_note(fx, fx.c1)]
        sc = Scenario(notes, diff=fx.empty_diff())
        res = await sc.run()
        hist = res.get("skipped_reasons") or {}
        assert sum(hist.values()) == len(res["skipped"]), (
            f"skipped_reasons 合计 {sum(hist.values())} 与 skipped 条数 {len(res['skipped'])} 不符"
        )


# ===========================================================================
# Property 18 —— 单章节失败不阻断（关键是「其余仍处理」这半边）
# ===========================================================================


class TestProperty18_FailureIsolation:
    @pytest.mark.asyncio
    async def test_single_section_failure_does_not_block_the_rest(self, fx: _Fx) -> None:
        good_a = _pair_note(fx, fx.c0, section_title="健康A")
        bad = _pair_note(fx, fx.c1, section_title="注入失败")
        good_b = _pair_note(fx, fx.c2, section_title="健康B")
        sc = Scenario([good_a, bad, good_b])
        res = await sc.run(fail_note_ids={bad.id})

        # 半边一：失败章节进 failed 桶，带可定位信息
        assert len(res["failed"]) == 1, f"failed 桶条数异常：{res['failed']}"
        item = res["failed"][0]
        assert item["note_id"] == str(bad.id)
        assert item["phase"] == "map_section"
        assert item["error"], "failed 条目缺 error 描述"

        # 半边二（Task 10 覆盖不到的那半边）：其余章节仍被处理
        assert res["mapped"] == 2, (
            f"其余章节未被处理（mapped={res['mapped']}）-- 一章失败让整次转换白做"
        )
        assert good_a.section_id == fx.c0["tgt_sid"], "失败章节之**前**的章节未改写"
        assert good_b.section_id == fx.c2["tgt_sid"], "失败章节之**后**的章节未改写"

        # 半边三：失败章节被 savepoint 回滚到改写前（不留半成品）
        assert bad.section_id == fx.c1["src_sid"], (
            f"失败章节未回滚，section_id 停在 {bad.section_id} -- savepoint 隔离失效"
        )
        assert bad.note_section == fx.c1["src_num"], "失败章节的 note_section 未回滚"

    @pytest.mark.asyncio
    async def test_failure_injection_is_precise_by_note_id(self, fx: _Fx) -> None:
        """反向自检：不注入时全绿，注入才红 -- 证明失败来自注入而非环境。"""
        notes = [_pair_note(fx, fx.c0), _pair_note(fx, fx.c1)]
        res = await Scenario(notes).run()
        assert not res["failed"], f"未注入却有失败：{res['failed']}"
        assert res["mapped"] == 2


# ===========================================================================
# Property 19 —— 零值带原因码且两者可区分
# ===========================================================================


class TestProperty19_ZeroValueReasonCodes:
    def test_reason_codes_are_distinguishable(self) -> None:
        from app.services.note_conversion_row_codes import FORMULA_REWRITE_REASON

        assert FORMULA_REWRITE_REASON == "no_mapping_needed", (
            f"原因码取值变了：{FORMULA_REWRITE_REASON}"
        )
        assert FORMULA_REWRITE_REASON != "not_implemented", (
            "「已扫描确无对象」与「未实现」必须可区分（Requirement 4.4）"
        )
        assert NoteConversionService.report_row_mapping_reason() == FORMULA_REWRITE_REASON
        assert NoteConversionService.formula_rewrite_reason() == FORMULA_REWRITE_REASON

    @pytest.mark.asyncio
    async def test_zero_returns_carry_reason(self) -> None:
        svc = NoteConversionService(FakeSession([]))
        rows = await svc._map_report_rows(PROJECT, YEAR, "soe", "listed")
        formulas, reason = await svc._update_formula_references(PROJECT, YEAR, "soe", "listed")
        assert rows == 0 and formulas == 0
        assert reason == "no_mapping_needed", f"零值未附可区分的原因码：{reason}"

    def test_zero_return_docstrings_carry_evidence_not_temporary_wording(self) -> None:
        """Property 15 的邻接判据（本文件顺带钉死）：docstring 不得留「For now」。"""
        src = CONVERSION_SERVICE.read_text(encoding="utf-8")
        assert "For now" not in src, (
            "服务源码里仍有「For now」这类临时措辞 -- 免做结论必须写实证依据"
        )
        for doc in (
            NoteConversionService._map_report_rows.__doc__ or "",
            NoteConversionService._update_formula_references.__doc__ or "",
        ):
            assert "report_config" in doc, "免做结论的 docstring 缺实证依据（report_config 对账）"


# ===========================================================================
# Property 24 —— 无孤儿转换函数（判据实现只在 v2_removal，本处只引用）
# ===========================================================================


class TestProperty24_NoOrphanConversionFunctions:
    """🔴 判据口径**同类内调用也算**（design.md Property 24 已钉死）。

    ``_map_*`` 是**私有子步骤**，被同类的公开入口 ``execute_conversion`` 调用即属
    「有消费方」；扫描面**含服务文件自身**。不得改成「必须有服务文件之外的调用方」——
    那会把正常的私有子步骤全部误判成孤儿，逼人把私有子步骤提成公开 API（制造第二个
    入口 = 双真源）。

    判据函数（``_method_names_under_scan`` / ``_non_test_call_sites``）的实现在
    ``tests/test_note_conversion_v2_removal.py``，本类只 import 它 —— 同一不变式两处
    实现即双真源。
    """

    def test_scan_surface_is_non_empty(self) -> None:
        names = _method_names_under_scan()
        assert names, "未扫到任何 convert_*/_map_* 方法 -- 判据失效"
        assert {"_map_disclosure_notes", "_map_report_rows"} <= set(names)

    def test_no_method_is_orphaned(self) -> None:
        orphans = {m: _non_test_call_sites(m) for m in _method_names_under_scan()}
        empty = sorted(m for m, callers in orphans.items() if not callers)
        assert not empty, (
            f"孤儿转换函数（无非测试调用方）：{empty} -- 要么接线到生产路径，"
            "要么删除（删前先迁移测试断言）"
        )

    def test_self_call_counts_as_consumer(self) -> None:
        """口径锁死：``_map_*`` 的调用点就在服务文件自身，这**是**合格状态。"""
        service_rel = "backend/app/services/note_conversion_service.py"
        for method in ("_map_disclosure_notes", "_map_report_rows"):
            callers = _non_test_call_sites(method)
            assert service_rel in callers, (
                f"{method} 的调用点不在服务文件自身（{callers}）-- "
                "扫描面被改成排除服务文件了？那会把私有子步骤误判成孤儿"
            )

    def test_public_entry_has_production_caller_outside_service(self) -> None:
        """整条链要有生产消费方：公开入口 ``execute_conversion`` 必须被服务文件**之外**调用。"""
        callers = _non_test_call_sites("execute_conversion")
        outside = [c for c in callers if not c.endswith("note_conversion_service.py")]
        assert outside, (
            f"execute_conversion 无服务文件之外的生产调用方（callers={callers}）-- "
            "整条章节映射链没有生产消费方"
        )


# ===========================================================================
# Property 25 —— 接线分支未选，本 Property 不作验收判据（只留说明性断言）
# ===========================================================================


class TestProperty25_WiringBranchNotSelected:
    """design.md Property 25 是「**接线** v2 后该验什么」的判据，而 Task 10 裁决为
    **删除不接线** ⇒ 本 Property 不生效。

    其语义已被生产路径承接并由别处钉死：``format_adapted`` 的空操作守卫在
    ``test_note_template_diff_integrity.py::TestConsumerCountsOnlyRealAdaptations``；
    共有章节 ``section_id`` 改写在本文件 Property 5。此处只留一条说明性断言，防止
    下个会话据 Property 25 重新造一份 v2 实现。
    """

    def test_v2_symbols_are_not_methods_of_the_service(self) -> None:
        methods = set(_service_methods())
        present = sorted(set(REMOVED_SYMBOLS) & methods)
        assert not present, (
            f"服务类上又出现了已删除的 v2 方法：{present} -- Task 10 裁决为删除不接线，"
            "重新造 v2 会形成第二份章节转换真源"
        )

    @pytest.mark.asyncio
    async def test_format_adapted_is_zero_while_field_mapping_all_null(self, fx: _Fx) -> None:
        """实证锚点：真实 diff 的 39 条 ``format_diff`` 的 ``field_mapping`` 全为 null
        ⇒ 适配是合法空操作，``format_adapted`` 必须为 0（不得无条件 ``+= 1``）。"""
        non_null = [e for e in (fx.diff.get("format_diff_sections") or []) if e.get("field_mapping")]
        if non_null:
            pytest.skip(
                f"field_mapping 已不再全为 null（{len(non_null)} 条非空）-- "
                "该实证锚点已过期，改由 test_note_template_diff_integrity 的守卫承担"
            )
        note = _pair_note(fx, fx.c0, table_data={"rows": [{"label": "行", "values": ["1"]}]})
        res = await Scenario([note]).run()
        assert res["format_adapted"] == 0, (
            f"field_mapping 全为 null 却上报 format_adapted={res['format_adapted']} -- 空操作被计为已适配"
        )


# ===========================================================================
# Property 26 —— 测试不丢失（轻断言；双向锁死在 v2_removal）
# ===========================================================================


class TestProperty26_MigrationTableCoversDeletedTests:
    """迁移表的**双向锁死**（覆盖全部 21 个 v2 测试 / 无孤儿生产测试 / 条目上限 /
    理由质量闸）在 ``tests/test_note_conversion_v2_removal.py``。本类只做轻断言：
    表存在、非空、覆盖被删测试数量下限 —— 不重复那边的判据。
    """

    def test_migration_table_exists_and_is_non_empty(self) -> None:
        assert ASSERTION_MIGRATION, "ASSERTION_MIGRATION 迁移表为空 -- Requirement 6.3 无留痕"
        assert len(ASSERTION_MIGRATION) >= 21, (
            f"迁移表只有 {len(ASSERTION_MIGRATION)} 条，被删的 v2 测试实测 21 个 -- 有遗漏"
        )

    def test_every_entry_names_a_source_and_a_target(self) -> None:
        for entry in ASSERTION_MIGRATION:
            src, tgt = entry[0], entry[1]
            assert src.startswith("test_"), f"迁移表源测试名异常：{src}"
            assert tgt.startswith("test_"), f"迁移表目标测试名异常：{tgt}（源 {src}）"


# ===========================================================================
# Property 35 —— binding_id 不因章节号改写而失联
# ===========================================================================


class TestProperty35_BindingIdNotOrphaned:
    """``binding_id`` 形态是「**章节号**.行标签.列键」（实测 1030 个未软删章节中 446 条
    带 binding）。改 ``note_section`` 而不改前缀会让这批绑定**静默失联** —— 公式取数
    变成空值而不是报错，属最难发现的一类缺陷。

    合法终态两种：前缀已同步改写 / 前缀仍是旧章节号但
    ``template_lineage.legacy_note_sections`` 记了它（供解析回退）。
    """

    @staticmethod
    def _binding_table_data(old_number: str, foreign_prefix: str) -> dict[str, Any]:
        """三处容器各放一条本章节 binding + 一条**外章节** binding（不得被误改）。"""
        return {
            "rows": [{"label": "行A", "binding_id": f"{old_number}.行A.closing_balance"}],
            "_tables": [
                {
                    "name": "表1",
                    "rows": [
                        {"label": "行B", "binding_id": f"{old_number}.行B.opening_balance"},
                        # 跨章节引用：前缀不是本章节号，改写必须放过它
                        {"label": "行C", "binding_id": f"{foreign_prefix}.行C.closing_balance"},
                    ],
                }
            ],
            "sub_table_data": {
                "明细": [{"label": "子行", "binding_id": f"{old_number}.子行.prior_year_value"}]
            },
        }

    @pytest.mark.asyncio
    async def test_prefix_rewritten_and_old_number_recorded(self, fx: _Fx) -> None:
        old_num, new_num = fx.c0["src_num"], fx.c0["tgt_num"]
        foreign = fx.c2["src_num"]
        note = _pair_note(
            fx, fx.c0, table_data=self._binding_table_data(old_num, foreign)
        )
        res = await Scenario([note]).run()

        assert res["mapped"] == 1, f"章节未被改写（skipped={res.get('skipped_reasons')}）"
        assert res["binding_ids_rewritten"] == 3, (
            f"binding 改写条数 {res['binding_ids_rewritten']} != 3 -- "
            "递归覆盖面缩了（rows / _tables[].rows / sub_table_data 三处都要改）"
        )
        prefixes = collect_binding_prefixes(note.table_data)
        assert new_num in prefixes, f"binding 前缀未改到新章节号 {new_num}：{sorted(prefixes)}"
        assert old_num not in prefixes, (
            f"仍有 binding 停在旧章节号 {old_num}：{sorted(prefixes)}"
        )
        assert foreign in prefixes, (
            f"跨章节 binding 的前缀 {foreign} 被误改了：{sorted(prefixes)} -- "
            "改写必须只作用于本章节号"
        )
        legacy = (note.template_lineage or {}).get("legacy_note_sections") or []
        assert old_num in legacy, (
            f"旧章节号 {old_num} 未记入 template_lineage.legacy_note_sections（{legacy}）"
        )
        # 不变式检查器
        assert_no_orphaned_binding(note, old_num)

    @pytest.mark.asyncio
    async def test_invariant_holds_for_every_mapped_note(self, fx: _Fx) -> None:
        """全量不变式：批量改写后逐个章节都不得留下失联绑定。"""
        cases = [
            (fx.c0, self._binding_table_data(fx.c0["src_num"], "外、9")),
            (fx.c1, self._binding_table_data(fx.c1["src_num"], "外、9")),
            (fx.c2, {"rows": [{"label": "无绑定行", "values": ["1"]}]}),
        ]
        notes = [_pair_note(fx, c, table_data=td) for c, td in cases]
        res = await Scenario(notes).run()
        assert res["mapped"] == 3, f"批量改写未全部生效：{res.get('skipped_reasons')}"
        for note, (c, _) in zip(notes, cases):
            assert_no_orphaned_binding(note, c["src_num"])

    def test_naive_rewrite_without_lineage_is_flagged(self, fx: _Fx) -> None:
        """反向自检：复现「只改 note_section、不改 binding 前缀、不记 lineage」必须打红。

        这正是 design.md 变异检验清单里的那一条。若检查器对它无反应，上面两条断言
        就是空转。
        """
        old_num, new_num = fx.c0["src_num"], fx.c0["tgt_num"]
        note = _pair_note(
            fx, fx.c0, table_data=self._binding_table_data(old_num, "外、9")
        )
        # 朴素实现：只改章节号
        note.note_section = new_num
        note.section_id = fx.c0["tgt_sid"]
        with pytest.raises(AssertionError, match="binding_id 仍以旧章节号"):
            assert_no_orphaned_binding(note, old_num)

    def test_lineage_only_fallback_is_accepted(self, fx: _Fx) -> None:
        """另一种合法终态：前缀没改但 lineage 记了旧章节号（供解析回退）。"""
        old_num = fx.c0["src_num"]
        note = _pair_note(
            fx, fx.c0, table_data=self._binding_table_data(old_num, "外、9")
        )
        note.note_section = fx.c0["tgt_num"]
        note.template_lineage = {"legacy_note_sections": [old_num]}
        assert_no_orphaned_binding(note, old_num)  # 不得打红


# ===========================================================================
# Property 36 —— section_id 为 NULL 的存量行有明确处置
# ===========================================================================


def _dispositions(sc: Scenario, note: Any) -> set[str]:
    """一条 note 的处置集合（用于「不得静默跳过」的完备性判据）。"""
    out: set[str] = set()
    if str(note.id) in sc.skipped_ids:
        out.add("skipped")
    if str(note.id) in sc.failed_ids:
        out.add("failed")
    if note.is_deleted:
        out.add("archived")
    return out


class TestProperty36_NullSidExplicitDisposition:
    """``section_id`` 大面积为 NULL（实测 1030 条里 817 条）。这批行要么被回填 sid 后
    参与映射，要么计入 ``skipped`` 并附原因码 —— **静默跳过必红**（那会让这批行在转换后
    仍停留在源变体的章节号上，而调用方以为一切正常）。
    """

    def _notes(self, fx: _Fx) -> dict[str, Any]:
        return {
            # (a) (note_section, section_title) 唯一命中 -> 回填 -> 参与映射
            "by_number_title": make_note(
                section_id=None,
                note_section=fx.c0["src_num"],
                section_title=fx.c0["title"],
            ),
            # (b) 章节号对不上、仅 section_title 唯一命中 -> 回填 -> 参与映射
            "by_title": make_note(
                section_id=None,
                note_section="零、章节号已漂移",
                section_title=fx.c1["title"],
            ),
            # (c) 两级都对不上 -> 回填不出（注意它的 note_section 仍是**源变体**章节号，
            #     正是「静默跳过就看不出来」的形态）
            "unresolved": make_note(
                section_id=None,
                note_section=fx.c2["src_num"],
                section_title="绝无此章节标题ZZZ",
            ),
            # (d) 标题在源模板里撞名 -> 宁缺勿造
            "ambiguous": make_note(
                section_id=None,
                note_section="零、歧义",
                section_title=fx.ambiguous_title,
            ),
        }

    @pytest.mark.asyncio
    async def test_backfillable_rows_participate_in_mapping(self, fx: _Fx) -> None:
        cases = self._notes(fx)
        sc = Scenario(list(cases.values()))
        res = await sc.run()

        assert res["sid_backfilled"] == 2, (
            f"应有 2 条 NULL sid 被回填，实为 {res['sid_backfilled']}"
            f"（skipped={res.get('skipped_reasons')}）"
        )
        a, b = cases["by_number_title"], cases["by_title"]
        assert a.section_id == fx.c0["tgt_sid"] and a.note_section == fx.c0["tgt_num"], (
            f"(number,title) 回填的行未参与映射：sid={a.section_id} num={a.note_section}"
        )
        assert b.section_id == fx.c1["tgt_sid"] and b.note_section == fx.c1["tgt_num"], (
            f"title 回填的行未参与映射：sid={b.section_id} num={b.note_section}"
        )
        assert (a.template_lineage or {}).get("section_id_backfilled_from") == "number_title"
        assert (b.template_lineage or {}).get("section_id_backfilled_from") == "title"

    @pytest.mark.asyncio
    async def test_unresolvable_rows_are_skipped_with_reason_not_silently(
        self, fx: _Fx
    ) -> None:
        cases = self._notes(fx)
        sc = Scenario(list(cases.values()))
        await sc.run()

        c, d = cases["unresolved"], cases["ambiguous"]
        assert sc.skip_reason_of(c) == SKIP_REASON_SID_UNRESOLVED, (
            f"回填不出的行未登记 {SKIP_REASON_SID_UNRESOLVED}"
            f"（实为 {sc.skip_reason_of(c)}）-- 静默跳过"
        )
        assert sc.skip_reason_of(d) == SKIP_REASON_SID_AMBIGUOUS, (
            f"回填歧义的行未登记 {SKIP_REASON_SID_AMBIGUOUS}（实为 {sc.skip_reason_of(d)}）"
        )
        # 这条行仍停在**源变体**章节号上 —— 允许，但必须已登记处置（否则调用方看不见）
        assert c.note_section == fx.c2["src_num"] and c.section_id is None
        assert "skipped" in _dispositions(sc, c), (
            "回填不出的行既没被改写也没进 skipped -- 正是 Property 36 要禁的静默跳过"
        )

    @pytest.mark.asyncio
    async def test_every_null_sid_row_is_accounted_for(self, fx: _Fx) -> None:
        """完备性不变式：每条 NULL sid 行都必须有可见处置。"""
        cases = self._notes(fx)
        notes = list(cases.values())
        sc = Scenario(notes)
        await sc.run()

        unaccounted: list[str] = []
        for note in notes:
            mapped_ok = note.section_id is not None and note.note_section not in (
                fx.c0["src_num"],
                fx.c2["src_num"],
                "零、章节号已漂移",
                "零、歧义",
            )
            if not mapped_ok and not _dispositions(sc, note):
                unaccounted.append(f"{note.note_section!r}/{note.section_title!r}")
        assert not unaccounted, (
            f"以下 NULL sid 行既未被改写也未登记处置（静默跳过）：{unaccounted}"
        )

    @pytest.mark.asyncio
    async def test_backfilled_sid_is_persisted_when_row_is_skipped(self, fx: _Fx) -> None:
        """回填成功但本轮不改写时，回填结果要落库（下次转换可直接参与映射）。

        构造：一条 NULL sid 行回填出的 sid 属于**源独有**清单 -> 归档路径，
        归档时应把回填出的 sid 一并落库，使 ``archived_sections[].section_id`` 与该行
        实际取值一致。
        """
        sec = fx.soe[fx.archive_sid]
        note = make_note(
            section_id=None,
            note_section=sec.get("section_number"),
            section_title=sec.get("section_title") or "",
        )
        sc = Scenario([note])
        res = await sc.run()

        if res["sid_backfilled"] == 0:
            pytest.skip(
                f"源独有章节 {fx.archive_sid} 的 (number,title) 在源模板里不唯一，"
                "本场景取不到可回填样本"
            )
        assert note.section_id == fx.archive_sid, (
            f"归档时未把回填出的 sid 落库（实为 {note.section_id}）"
        )
        entries = (note.template_lineage or {}).get("archived_sections") or []
        assert any(e.get("section_id") == fx.archive_sid for e in entries), (
            f"archived_sections 与该行实际 sid 不一致：{entries}"
        )
        assert (note.template_lineage or {}).get("section_id_backfilled_from"), (
            "回填来源未留痕（section_id_backfilled_from）"
        )
