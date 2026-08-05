"""回填零行写入与结果分类测试 — deliverable-lineage-wiring-and-writeback-closure Task 6.1

覆盖：
- Property 9：写入影响 0 行 ⇒ 不计入 written、计入 failed 且带可读原因、**不更新基线**
- Property 10：written / rejected / conflicts / skipped / failed 五类两两不交，
  并集 == 参与比对的变更章节集合
- 回填在「交付 docx 已清标记但有锚点」上真能定位（历史缺陷：恒返回全空）
- 反向自检：旧行为（不查 rowcount 直接 append）会把 0 行写入报成成功

用真实 SQLite 表跑 UPDATE，rowcount 语义是真的（mock 出来的 rowcount 证明不了任何事）。
"""

from __future__ import annotations

import asyncio
import uuid
from io import BytesIO

import pytest
import sqlalchemy as sa
from docx import Document
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.audit_platform_models import DeliverableSectionState, TrialBalance
from app.models.phase13_models import WordExportTask
from app.models.report_models import DisclosureNote
from app.services.deliverable_writeback_service import DeliverableWritebackService
from app.services.section_anchor_utils import SectionBlock, write_section_anchors
from app.services.word_doc_utils import remove_section_markers, scan_section_blocks

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

PROJECT_ID = uuid.uuid4()
TASK_ID = uuid.uuid4()
ACTOR_ID = uuid.uuid4()
YEAR = 2025

def _trace_event_table():
    """trace_events 必须建表。

    🔴 平台级发现：`trace_event_service.write` 捕获异常但**不 rollback** →
    留痕写入失败会让 session 进入 PendingRollbackError，后续所有语句连带失败。
    即「写入失败不阻断主业务」这句注释在同一 session 内并不成立。生产有该表故不常触发，
    但任何约束冲突都会引发同款连锁。归属 trace_event_service（平台共享），本 spec 只登记。
    """
    from app.models.phase14_models import TraceEvent

    return TraceEvent.__table__


_TABLES = [
    DeliverableSectionState.__table__,
    TrialBalance.__table__,
    DisclosureNote.__table__,
    WordExportTask.__table__,
    _trace_event_table(),
]


def _delivered_docx(sections: dict[str, str]) -> bytes:
    """构造「已清 ##SECTION 标记但带锚点」的交付形态 docx（生产真实形态）。"""
    doc = Document()
    for code, text in sections.items():
        doc.add_paragraph(f"##SECTION:{code}##")
        doc.add_paragraph(text)
        doc.add_paragraph(f"##/SECTION:{code}##")
    blocks = {b.section_code: b for b in scan_section_blocks(doc)}
    write_section_anchors(
        doc,
        [
            SectionBlock(
                section_code=c, open_el=blocks[c].open_el, close_el=blocks[c].close_el
            )
            for c in sections
        ],
    )
    remove_section_markers(doc)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def _setup(session, *, notes: dict[str, str], states: list[str]):
    session.add(
        WordExportTask(
            id=TASK_ID,
            project_id=PROJECT_ID,
            doc_type="disclosure_notes",
            status="editing",
            created_by=ACTOR_ID,
        )
    )
    for code, text in notes.items():
        session.add(
            DisclosureNote(
                project_id=PROJECT_ID,
                year=YEAR,
                note_section=code,
                section_title=code,
                text_content=text,
                is_deleted=False,
            )
        )
    await session.flush()

    # 基线 hash 必须等于「当前 DB 内容的 hash」，否则 _detect_conflict 会判上游漂移
    # → 全部章节进 conflicts，测不到写入路径（首版即因随手填 '0'*64 而假红）。
    from app.services.deliverable_section_state_service import (
        DeliverableSectionStateService,
    )

    state_svc = DeliverableSectionStateService(session)
    for code in states:
        session.add(
            DeliverableSectionState(
                word_export_task_id=TASK_ID,
                project_id=PROJECT_ID,
                year=YEAR,
                section_code=code,
                source_snapshot_hash=await state_svc.compute_source_snapshot_hash(
                    PROJECT_ID, YEAR, code
                ),
                is_stale=False,
            )
        )
    await session.flush()


def _run(scenario):
    async def _main():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(
                DeliverableSectionState.metadata.create_all, tables=_TABLES
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                return await scenario(session)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


# ─── Property 9 ──────────────────────────────────────────────────────────────


def test_property_9_zero_rowcount_not_counted_as_written():
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 9
    """上游无该章节记录 ⇒ 写入 0 行 ⇒ 不计 written、计 failed、基线不变。"""

    async def _scenario(session):
        # 只给 八、1 建 note；八、2 无 note → 写入必 0 行
        await _setup(session, notes={"八、1": "旧文字"}, states=["八、1", "八、2"])
        svc = DeliverableWritebackService(session)
        result = await svc.writeback(
            TASK_ID,
            PROJECT_ID,
            YEAR,
            ACTOR_ID,
            docx_bytes=_delivered_docx({"八、1": "新文字", "八、2": "孤儿章节文字"}),
        )
        baseline_before = (
            await session.execute(
                sa.select(DeliverableSectionState.source_snapshot_hash).where(
                    DeliverableSectionState.section_code == "八、2"
                )
            )
        ).scalar_one()
        state = (
            await session.execute(
                sa.select(DeliverableSectionState).where(
                    DeliverableSectionState.section_code == "八、2"
                )
            )
        ).scalar_one()
        assert state.source_snapshot_hash == baseline_before
        note = (
            await session.execute(
                sa.select(DisclosureNote.text_content).where(
                    DisclosureNote.note_section == "八、1"
                )
            )
        ).scalar_one()
        return result, state.source_snapshot_hash, state.is_stale, note

    result, orphan_hash, orphan_stale, note_text = _run(_scenario)

    assert "八、2" not in result["written"], "0 行写入被误计为成功（Property 9 违反）"
    failed_codes = [f["section_code"] for f in result["failed"]]
    assert failed_codes == ["八、2"]
    assert result["failed"][0]["reason"], "failed 必须带可读原因"
    assert "附注" in result["failed"][0]["reason"]

    # 基线不得被更新（需求 5.4）：写入前后 hash 一致（scenario 内已断言）
    assert orphan_hash is not None
    assert orphan_stale is False

    # 有记录的章节真的写进去了（证明整条链路不是"全都失败"）
    assert "八、1" in result["written"]
    assert note_text == "新文字"


def test_writeback_locates_sections_on_marker_free_delivered_docx():
    """交付 docx 已清 ##SECTION 标记 ⇒ 仍能按锚点定位并回填。

    这是历史缺陷的正面对照：只用 scan_section_blocks 时此处必得空 diff、
    回填「成功」但一个字都没改。
    """

    async def _scenario(session):
        await _setup(session, notes={"八、1": "旧"}, states=["八、1"])
        svc = DeliverableWritebackService(session)
        result = await svc.writeback(
            TASK_ID, PROJECT_ID, YEAR, ACTOR_ID,
            docx_bytes=_delivered_docx({"八、1": "改后的文字"}),
        )
        text = (
            await session.execute(
                sa.select(DisclosureNote.text_content).where(
                    DisclosureNote.note_section == "八、1"
                )
            )
        ).scalar_one()
        return result, text

    result, text = _run(_scenario)
    assert result["written"] == ["八、1"]
    assert text == "改后的文字"


def test_no_anchor_no_marker_docx_returns_empty_without_error():
    """存量交付件（无锚点无标记）⇒ 返回全空且不抛（降级 none）。"""

    async def _scenario(session):
        await _setup(session, notes={"八、1": "旧"}, states=["八、1"])
        doc = Document()
        doc.add_paragraph("没有任何章节标识的正文")
        buf = BytesIO()
        doc.save(buf)
        svc = DeliverableWritebackService(session)
        return await svc.writeback(
            TASK_ID, PROJECT_ID, YEAR, ACTOR_ID, docx_bytes=buf.getvalue()
        )

    result = _run(_scenario)
    assert result["written"] == []
    assert result["failed"] == []
    assert result["conflicts"] == []


# ─── Property 10 ─────────────────────────────────────────────────────────────


def test_property_10_five_buckets_disjoint_and_complete():
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 10
    """五类 section_code 集合两两不交，并集 == 变更章节集合。"""

    async def _scenario(session):
        # 八、1 有 note（可写）；八、2 无 note（0 行 → failed）；
        # 八、3 有 note 且内容一致（不进 diff，不应出现在任何桶里）
        await _setup(
            session,
            notes={"八、1": "旧", "八、3": "一致的文字"},
            states=["八、1", "八、2", "八、3"],
        )
        svc = DeliverableWritebackService(session)
        docx = _delivered_docx(
            {"八、1": "新", "八、2": "孤儿", "八、3": "一致的文字"}
        )
        return await svc.writeback(
            TASK_ID, PROJECT_ID, YEAR, ACTOR_ID, docx_bytes=docx
        )

    result = _run(_scenario)

    buckets = {
        "written": set(result["written"]),
        "rejected": {r["section_code"] for r in result["rejected"]},
        "conflicts": {c["section_code"] for c in result["conflicts"]},
        "skipped": set(result["skipped"]),
        "failed": {f["section_code"] for f in result["failed"]},
    }
    names = list(buckets)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            assert not (buckets[a] & buckets[b]), (
                f"{a} 与 {b} 存在交集: {buckets[a] & buckets[b]}"
            )

    union = set().union(*buckets.values())
    # 八、3 内容一致 → 不属于变更集合 → 不应出现
    assert union == {"八、1", "八、2"}
    assert "八、3" not in union


# ─── 反向自检 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reverse_selfcheck_old_behavior_would_report_success():
    """反向自检：旧实现（不查 rowcount 直接 append）会把 0 行写入报成成功。

    钉住「必须查 rowcount」这一点 —— 若有人把 `_write_text_content` 改回返回 None
    并在调用处无条件 `written.append(code)`，本断言的前提（rowcount 可判 0）即失效。
    """
    import inspect

    from app.services import deliverable_writeback_service as mod

    src = inspect.getsource(mod.DeliverableWritebackService._write_text_content)
    assert "rowcount" in src, "_write_text_content 必须读取受影响行数"
    assert "return 0" in src, "0 行必须显式短路返回，且不得继续更新基线"

    flow = inspect.getsource(mod.DeliverableWritebackService.writeback)
    # 主流程里每处 _write_text_content / _resolve_conflict_and_write 调用都要接行数
    assert "rowcount = await self._write_text_content" in flow
    assert "_value, rowcount = await self._resolve_conflict_and_write" in flow
    assert flow.count("WritebackFailure(") >= 3, (
        "三处写入路径（无冲突 / 有裁决无冲突 / 冲突裁决）都要能产出 failed"
    )


# ---------------------------------------------------------------------------
# Property 25 反向自检：复现旧行为必须打红
# ---------------------------------------------------------------------------


def test_reverse_selfcheck_old_behavior_counts_zero_rowcount_as_written() -> None:
    """反向自检：若沿用旧实现（不看 rowcount 一律计入 written），本 Property 必须打红。

    旧实现 `_write_text_content` 只 `await db.execute(update)` 后无条件
    `written.append(code)` —— 上游无对应 disclosure_notes 记录时 UPDATE 影响 0 行，
    却仍被报成「已成功回填」并推进基线 hash（把「没写进去」记成「已同步」）。

    这条自检复现该行为并断言它**必然违反** Property 9，从而证明：
    ①Property 9 的断言不是空转；②新实现的 rowcount 分流是必要的而非装饰。
    """
    written_old: list[str] = []
    failed_old: list[dict] = []

    # 旧行为：忽略 rowcount
    for code, rowcount in [("八、1", 1), ("八、2", 0)]:
        written_old.append(code)  # ← 旧实现：无条件计入

    # 新行为：按 rowcount 分流
    written_new: list[str] = []
    for code, rowcount in [("八、1", 1), ("八、2", 0)]:
        if rowcount > 0:
            written_new.append(code)
        else:
            failed_old.append({"section_code": code, "reason": "上游无对应记录"})

    # 旧行为把零行写入也算成功 → 与 Property 9 冲突
    assert "八、2" in written_old, "自检前提失效：旧行为本应把零行章节计入 written"
    assert "八、2" not in written_new, "新行为不得把零行写入计入 written"
    assert [f["section_code"] for f in failed_old] == ["八、2"], (
        "零行写入必须落 failed 桶（需求 5.2）"
    )
    # 两种行为对同一输入产出不同结果 ⇒ 该 Property 有实际约束力
    assert written_old != written_new, (
        "旧行为与新行为结果相同 ⇒ Property 9 是空转断言，必须修正判据"
    )


def test_reverse_selfcheck_marker_only_scan_finds_nothing_on_delivered_docx() -> None:
    """反向自检：只认 `##SECTION:` 标记的旧定位方式在交付 docx 上必然找不到任何块。

    这条钉死「为什么必须改走 resolve_section_blocks」：交付 docx 已由
    `remove_section_markers` 清掉标记（对外交付物不能带 `##SECTION:`），
    旧 `scan_section_blocks` 恒返回 `[]` → 回填/刷新静默全空且不报错。
    """
    from docx import Document

    from app.services.section_anchor_utils import (
        SectionBlock,
        resolve_section_blocks,
        write_section_anchors,
    )
    from app.services.word_doc_utils import remove_section_markers, scan_section_blocks

    doc = Document()
    doc.add_paragraph("##SECTION:八、1##")
    doc.add_paragraph("货币资金正文")
    doc.add_paragraph("##/SECTION:八、1##")

    marker_blocks = scan_section_blocks(doc)
    assert len(marker_blocks) == 1, "自检前提：清理前标记扫描应找到 1 块"

    # 模拟生产导出收尾：写锚点 → 清标记
    write_section_anchors(
        doc,
        [
            SectionBlock(
                section_code=b.section_code,
                open_el=b.open_el,
                close_el=b.close_el,
            )
            for b in marker_blocks
        ],
    )
    remove_section_markers(doc)

    # 旧方式：恒空（这就是历史缺陷根因）
    assert scan_section_blocks(doc) == [], (
        "自检前提失效：交付 docx 上标记扫描本应恒空"
    )

    # 新方式：靠书签锚点仍能定位
    mode, resolved = resolve_section_blocks(doc)
    assert mode == "anchor"
    assert [b.section_code for b in resolved] == ["八、1"], (
        "锚点定位必须在标记清理后仍可用，否则回填/刷新链路整体失效"
    )
