"""归档完整性检查新增 5 类（spec attachment-archive-and-a-class-evidence 需求 5）。

回归背景：完整性检查只看底稿状态，不看证据缺口、未回函、识别未确认、文件缺失、孤儿文件 ⇒ 检查通过的项目
打包时照样缺件（改造前打包又不报缺件，归档包静默残缺）。
"""
from __future__ import annotations

from pathlib import Path

import pytest_asyncio

from app.core.config import settings
from app.models.attachment_models import AttachmentWorkingPaper
from app.models.phase13_models import WordExportTask
from app.services import archive_completeness_evidence as ace
from app.services import confirmation_evidence_status
from app.services.attachment_ocr_text import text_sha256
from tests.attachment_security_baseline._world import add_attachment, add_wp, sqlite_attachment_world


@pytest_asyncio.fixture
async def world(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "ATTACHMENT_LOCAL_STORAGE_ROOT", str(tmp_path / "attachments"))
    async with sqlite_attachment_world(monkeypatch) as w:
        await w.db.run_sync(lambda s: WordExportTask.__table__.create(s.connection()))
        yield w


def _rows(items):
    return [(i.wp_code, i.wp_name, i.status) for i in items]


async def test_missing_files_lists_unreadable_items(world, tmp_path):
    wp = await add_wp(world, world.target, wp_code="E1-1")
    wp.file_path = str(tmp_path / "gone.xlsx")
    await add_attachment(world, world.target, file_name="丢失.pdf", file_path=str(tmp_path / "nope.pdf"))
    await world.db.flush()
    assert _rows(await ace.check_missing_files(world.db, world.target.id)) == [
        ("E1-1", "E1-1 E1-1 测试底稿", "底稿文件不存在（路径已配置但磁盘上找不到）"),
        ("附件", "丢失.pdf", "附件文件不存在"),
    ]


async def test_missing_files_query_failure_blocks(world, monkeypatch):
    import app.services.archive_inventory as inv

    async def boom(db, project_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(inv, "build_project_inventory", boom)
    items = await ace.check_missing_files(world.db, world.target.id)
    assert len(items) == 1 and items[0].status.startswith("清单检查失败")


async def test_evidence_gaps_and_unreplied_dedup(world, monkeypatch):
    f3 = await add_wp(world, world.target, wp_code="F3-5")
    await add_wp(world, world.target, wp_code="B1-1")  # 无声明：不出现
    signed_ok = await add_wp(world, world.target, wp_code="A16")
    att = await add_attachment(world, world.target, attachment_type="signed")
    await world._add(AttachmentWorkingPaper(attachment_id=att.id, wp_id=signed_ok.id, association_type="evidence"))
    d0 = await add_wp(world, world.target, wp_code="D0")
    d01 = await add_wp(world, world.target, wp_code="D0-1")  # 同一工作簿：拆分相同，只报一次
    for wp in (d0, d01):
        reply = await add_attachment(world, world.target, attachment_type="confirmation")
        await world._add(AttachmentWorkingPaper(attachment_id=reply.id, wp_id=wp.id, association_type="confirmation"))

    async def breakdown(db, project_id, wp_code):
        items = [{"confirmation_id": f"c{i}", "counterparty": f"客户{i}"} for i in range(4)]
        return {"total": 6, "replied": 2, "alternative": 0, "missing": 4, "missing_items": items}

    monkeypatch.setattr(confirmation_evidence_status, "confirmation_breakdown", breakdown)
    gaps, unreplied = await ace.check_evidence(world.db, world.target.id)
    assert _rows(gaps) == [("F3-5", "F3-5 测试底稿", "缺票据影像")]
    assert _rows(unreplied) == [("D0", "D0 测试底稿", "4 笔未回函且无替代程序：客户0、客户1、客户2等")]
    assert f3.id is not None


async def test_unconfirmed_ocr(world):
    wp = await add_wp(world, world.target, wp_code="D2-1")
    pending = await add_attachment(world, world.target, file_name="未确认.pdf", ocr_text="识别文字", ocr_status="completed")
    await world._add(AttachmentWorkingPaper(attachment_id=pending.id, wp_id=wp.id, association_type="evidence"))
    await add_attachment(world, world.target, file_name="已确认.pdf", ocr_text="已核对",
                         ocr_status="completed", ocr_confirmed_sha256=text_sha256("已核对"))
    await add_attachment(world, world.target, file_name="改过.pdf", ocr_text="新文字",
                         ocr_status="completed", ocr_confirmed_sha256=text_sha256("旧文字"))
    await add_attachment(world, world.target, file_name="无文字.pdf", ocr_text="  ")
    # 同一秒建的行按 created_at 排不出先后（SQLite 秒级），按内容比
    assert sorted(_rows(await ace.check_unconfirmed_ocr(world.db, world.target.id))) == sorted([
        ("D2-1", "未确认.pdf", "识别结果未人工确认"),
        ("未关联底稿", "改过.pdf", "识别结果未人工确认"),  # 确认后文本被改 ⇒ 确认失效
    ])


async def test_orphan_files_category(world):
    root = Path(settings.ATTACHMENT_LOCAL_STORAGE_ROOT) / str(world.target.id) / "evidence"
    root.mkdir(parents=True)
    (root / "a.pdf").write_bytes(b"1")
    (root / "b.pdf").write_bytes(b"2")
    await add_attachment(world, world.target, file_path=str(root / "a.pdf"))
    assert _rows(await ace.check_orphan_files(world.db, world.target.id)) == [
        ("附件目录", "evidence/b.pdf", "未被任何附件记录引用"),
    ]


async def test_report_blocks_only_on_missing_files_among_new(world, tmp_path, monkeypatch):
    from app.services import archive_completeness_service as acs

    async def empty(db, project_id):
        return []

    for name in ("_check_missing", "_check_unsigned", "_check_unresolved_reviews", "_check_stale",
                 "_check_sampling_records"):
        monkeypatch.setattr(acs, name, empty)
    f3 = await add_wp(world, world.target, wp_code="F3-5")  # 证据缺口：提示，不阻断
    f3.file_path = ""  # 未生成文件 ≠ 缺件
    await world.db.flush()
    report = await acs.get_archive_completeness_report(world.db, world.target.id)
    cats = {c.category: c for c in report.categories}
    assert cats["evidence_gaps"].count == 1 and not cats["evidence_gaps"].is_blocking
    assert report.can_proceed is True
    gone = await add_wp(world, world.target, wp_code="E1-1")
    gone.file_path = str(tmp_path / "gone.xlsx")
    await world.db.flush()
    report = await acs.get_archive_completeness_report(world.db, world.target.id)
    cats = {c.category: c for c in report.categories}
    assert cats["missing_files"].count == 1 and cats["missing_files"].is_blocking
    assert report.can_proceed is False
