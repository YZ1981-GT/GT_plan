"""归档清单与归档包（spec attachment-archive-and-a-class-evidence 需求 1，ADR-AE-01 / ADR-AE-02）。

回归背景：打包只把 ``storage/projects/{pid}`` 打 tar（真库多数底稿不在那里），附件 / 交付件 / 底稿数据都不进包，
打包失败返回 ``{"error"}`` 编排照样成功；章节只算哈希不进包。
"""
from __future__ import annotations

import hashlib
import json
import uuid
import zipfile
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.core.config import settings
from app.models.evidence_governance_models import AttachmentVersion
from app.models.phase13_models import WordExportTask
from app.services import archive_section_registry
from app.services.archive_inventory import MISSING, OK, SKIPPED, build_project_inventory, orphan_files
from app.services.archive_package_builder import ArchivePackageError, build_archive_package, package_path
from app.services.archive_section_registry import SectionDef
from app.services.wp_export.wp_file_resolver import BACKEND_ROOT
from tests.attachment_security_baseline._world import add_attachment, add_wp, sqlite_attachment_world

CHECKLIST = sa.Table(
    "checklist_responses", sa.MetaData(),
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("wp_id", sa.Uuid()), sa.Column("item_id", sa.String(100)), sa.Column("conclusion", sa.String(50)),
    sa.Column("remark", sa.Text), sa.Column("wp_ref", sa.String(100)),
)
TEMPLATE = BACKEND_ROOT / "wp_templates" / "A" / "A30 电子底稿归档检查表.xlsx"


@pytest_asyncio.fixture
async def world(monkeypatch, tmp_path):
    # 底稿文件路径边界（Property 42）只认 cwd / backend / 仓库根：让 tmp_path 成为 cwd，测试文件才不被判越界
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setattr(settings, "ATTACHMENT_LOCAL_STORAGE_ROOT", str(tmp_path / "attachments"))
    async with sqlite_attachment_world(monkeypatch) as w:
        def _create(sync_session):
            conn = sync_session.connection()
            WordExportTask.__table__.create(conn)
            CHECKLIST.create(conn)
        await w.db.run_sync(_create)
        yield w


def _sections(monkeypatch, *defs: SectionDef) -> None:
    monkeypatch.setattr(archive_section_registry, "list_all", lambda: list(defs))


async def _const(content):
    async def gen(project_id, db):
        return content
    return gen


def _file(tmp_path: Path, rel: str, data: bytes) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


async def _deliverable(world, *, status: str, file_path: str | None, doc_type: str = "audit_report"):
    who = await world.edit_member()
    return await world._add(WordExportTask(project_id=world.target.id, doc_type=doc_type, status=status,
                                           file_path=file_path, created_by=who.user.id))


async def _good_project(world, tmp_path):
    """一张有文件的底稿、一张未生成文件的底稿、一份现行附件（含旧版本）、一份已确认交付件。"""
    wp_file = _file(tmp_path, "wp/D2-1.xlsx", b"wp-bytes")
    wp = await add_wp(world, world.target, wp_code="D2-1")
    wp.file_path = str(wp_file)
    wp.parsed_data = {"conclusion": "可以确认"}
    blank = await add_wp(world, world.target, wp_code="A30")
    blank.file_path = ""
    await world.db.flush()
    await world.db.execute(CHECKLIST.insert().values(wp_id=blank.id, item_id="A30-A1-11", conclusion="是"))
    old = await add_attachment(world, world.target, file_name="回函.pdf",
                               file_path=str(_file(tmp_path, "att/v1.pdf", b"old")))
    new = await add_attachment(world, world.target, file_name="回函.pdf", previous_version_id=old.id,
                               file_path=str(_file(tmp_path, "att/v2.pdf", b"new-version")))
    report = await _deliverable(world, status="confirmed", file_path=str(_file(tmp_path, "dl/report.docx", b"docx")))
    await _deliverable(world, status="draft", file_path=str(_file(tmp_path, "dl/draft.docx", b"draft")))
    return wp, blank, old, new, report


async def test_workpaper_name_whitespace_trimmed(world, tmp_path):
    """模板名带前导空格（A16「 管理层声明书程序表」，走查下载的包里出现「A16  管理层…」双空格）⇒ 先去首尾空白。"""
    from app.models.workpaper_models import WpIndex

    wp = await add_wp(world, world.target, wp_code="A16")
    wp.file_path = str(_file(tmp_path, "wp/A16.xlsx", b"a16"))
    (await world.db.get(WpIndex, wp.wp_index_id)).wp_name = " 管理层声明书程序表 "
    await world.db.flush()
    entry = next(e for e in (await build_project_inventory(world.db, world.target.id)).entries
                 if e.category == "workpaper_file")
    assert (entry.label, entry.arcname) == ("A16 管理层声明书程序表", "10-底稿/A16 管理层声明书程序表.xlsx")


async def test_inventory_verdicts(world, tmp_path):
    wp, blank, old, new, report = await _good_project(world, tmp_path)
    missing_wp = await add_wp(world, world.target, wp_code="E1-1")
    missing_wp.file_path = str(tmp_path / "gone.xlsx")
    tpl_wp = await add_wp(world, world.target, wp_code="A30-1")
    tpl_wp.file_path = str(TEMPLATE)
    await add_attachment(world, world.target, file_name="已删.pdf", is_deleted=True)
    lost = await add_attachment(world, world.target, file_name="丢失.pdf", file_path=str(tmp_path / "nope.pdf"))
    pl = await add_attachment(world, world.target, file_name="云端.pdf", file_path="paperless://documents/7",
                              storage_type="paperless")
    pending = await add_attachment(world, world.target, file_name="待检测.pdf", state="pending",
                                   file_path=str(_file(tmp_path, "att/p.pdf", b"p")))
    await _deliverable(world, status="signed", file_path=str(tmp_path / "no.docx"), doc_type="notes")
    await world.db.flush()
    assert TEMPLATE.is_file()

    inv = await build_project_inventory(world.db, world.target.id)
    by = {(e.category, e.label): e for e in inv.entries}
    assert by[("workpaper_file", "D2-1 D2-1 测试底稿")].status == OK
    assert by[("workpaper_file", "D2-1 D2-1 测试底稿")].arcname == "10-底稿/D2-1 D2-1 测试底稿.xlsx"
    assert by[("workpaper_file", "A30 A30 测试底稿")].status == SKIPPED
    assert by[("workpaper_file", "A30-1 A30-1 测试底稿")].status == SKIPPED  # 指向模板库 ≠ 底稿文件
    assert "模板库" in by[("workpaper_file", "A30-1 A30-1 测试底稿")].reason
    e1 = by[("workpaper_file", "E1-1 E1-1 测试底稿")]
    assert (e1.status, e1.reason) == (MISSING, "底稿文件不存在（路径已配置但磁盘上找不到）")
    atts = [e for e in inv.entries if e.category == "attachment"]
    assert {e.source_id for e in atts} == {str(new.id), str(lost.id), str(pl.id), str(pending.id)}  # 旧版本 / 已删除不收
    assert by[("attachment", "丢失.pdf")].status == MISSING
    assert by[("attachment", "云端.pdf")].reason == "附件存于 Paperless，但平台未配置 Paperless"
    assert by[("attachment", "待检测.pdf")].status == SKIPPED
    dls = [e for e in inv.entries if e.category == "deliverable"]
    assert {e.source_id for e in dls} >= {str(report.id)}
    assert [e.status for e in dls if e.label.startswith("notes")] == [MISSING]
    assert all(e.label != "audit_report（draft）" for e in dls)  # 草稿不收


async def test_package_success_manifest_matches_zip(world, tmp_path, monkeypatch):
    wp, blank, old, new, report = await _good_project(world, tmp_path)
    _sections(monkeypatch,
              SectionDef("00", "00-项目封面.pdf", await _const(b"%PDF-cover"), "项目封面"),
              SectionDef("99", "99-审计日志.jsonl", await _const(None), "审计日志导出"))
    job_id = uuid.uuid4()
    result = await build_archive_package(world.db, world.target.id, job_id)

    assert result.path == package_path(world.target.id, job_id) and result.path.is_file()
    assert not result.path.with_name(result.path.name + ".part").exists()
    assert result.sha256 == hashlib.sha256(result.path.read_bytes()).hexdigest()
    with zipfile.ZipFile(result.path) as zf:
        names = set(zf.namelist())
        manifest_bytes = zf.read("manifest.json")
        manifest = json.loads(manifest_bytes)
        assert result.manifest_hash == hashlib.sha256(manifest_bytes).hexdigest()
        assert names == {e["arcname"] for e in manifest["entries"]} | {"manifest.json"}
        for e in manifest["entries"]:
            data = zf.read(e["arcname"])
            assert (len(data), hashlib.sha256(data).hexdigest()) == (e["size"], e["sha256"]), e["arcname"]
        assert zf.read("10-底稿/D2-1 D2-1 测试底稿.xlsx") == b"wp-bytes"
        assert zf.read(f"40-附件/{str(new.id)[:8]}-回函.pdf") == b"new-version"  # 只收现行版本
        assert zf.read("00-项目封面.pdf") == b"%PDF-cover"
        assert zf.read(f"50-交付件/audit_report-{str(report.id)[:8]}.docx") == b"docx"
        snap = json.loads(zf.read("11-底稿数据/A30.json"))
        assert snap["checklist_responses"] == [{"item_id": "A30-A1-11", "conclusion": "是", "remark": None,
                                                "wp_ref": None}]
        assert json.loads(zf.read("11-底稿数据/D2-1.json"))["parsed_data"] == {"conclusion": "可以确认"}
    assert sorted(s["label"] for s in manifest["skipped"]) == ["A30 A30 测试底稿", "审计日志导出"]
    assert manifest["project_id"] == str(world.target.id) and manifest["job_id"] == str(job_id)
    assert result.counts == {"section": 1, "workpaper_file": 1, "attachment": 1, "deliverable": 1,
                             "workpaper_data": 2}


async def test_package_missing_items_fail_without_leaving_file(world, tmp_path, monkeypatch):
    await _good_project(world, tmp_path)
    gone = await add_wp(world, world.target, wp_code="E1-1")
    gone.file_path = str(tmp_path / "gone.xlsx")
    await add_attachment(world, world.target, file_name="丢失.pdf", file_path=str(tmp_path / "nope.pdf"))
    await world.db.flush()
    _sections(monkeypatch)
    job_id = uuid.uuid4()
    with pytest.raises(ArchivePackageError) as exc:
        await build_archive_package(world.db, world.target.id, job_id)
    assert exc.value.problems == [
        "底稿文件｜E1-1 E1-1 测试底稿｜底稿文件不存在（路径已配置但磁盘上找不到）",
        "附件｜丢失.pdf｜附件文件不存在",
    ]
    assert str(exc.value).startswith("归档包有 2 项读不到，未生成归档包")
    target = package_path(world.target.id, job_id)
    assert not target.exists() and not target.with_name(target.name + ".part").exists()


async def test_section_generator_error_fails_package(world, tmp_path, monkeypatch):
    await _good_project(world, tmp_path)

    async def boom(project_id, db):
        raise RuntimeError("LibreOffice 不可用")

    _sections(monkeypatch, SectionDef("00", "00-项目封面.pdf", boom, "项目封面"))
    with pytest.raises(ArchivePackageError) as exc:
        await build_archive_package(world.db, world.target.id, uuid.uuid4())
    assert exc.value.problems == ["归档章节｜项目封面｜生成失败：LibreOffice 不可用"]


async def test_paperless_unreachable_fails_package(world, tmp_path, monkeypatch):
    from app.services.attachment_service import AttachmentService

    await add_attachment(world, world.target, file_name="云端.pdf", file_path="paperless://documents/7",
                         storage_type="paperless")
    monkeypatch.setattr(AttachmentService, "paperless_enabled", lambda self: True)
    monkeypatch.setattr(settings, "PAPERLESS_URL", "http://127.0.0.1:9", raising=False)
    orig_init = AttachmentService.__init__

    def init(self, *a, **kw):
        orig_init(self, *a, **kw)
        self.paperless_url, self.paperless_token = "http://127.0.0.1:9", "t"

    monkeypatch.setattr(AttachmentService, "__init__", init)
    _sections(monkeypatch)
    with pytest.raises(ArchivePackageError) as exc:
        await build_archive_package(world.db, world.target.id, uuid.uuid4())
    assert len(exc.value.problems) == 1 and exc.value.problems[0].startswith("附件｜云端.pdf｜Paperless 不可达")


async def test_orphan_files(world, tmp_path):
    root = Path(settings.ATTACHMENT_LOCAL_STORAGE_ROOT) / str(world.target.id)
    live = _file(root, "evidence/live.pdf", b"1")
    deleted = _file(root, "evidence/deleted.pdf", b"2")
    versioned = _file(root, "evidence/versioned.pdf", b"3")
    orphan = _file(root, "evidence/orphan.pdf", b"4")
    await add_attachment(world, world.target, file_path=str(live))
    gone = await add_attachment(world, world.target, file_path=str(deleted), is_deleted=True)
    await world._add(AttachmentVersion(attachment_id=gone.id, project_id=world.target.id, version_no=1,
                                       storage_type="local", storage_key=str(versioned), actor_type="user",
                                       actor_user_id=(await world.edit_member()).user.id))
    assert await orphan_files(world.db, world.target.id) == [orphan]
