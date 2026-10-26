"""建底稿统一回执与单码建底稿（spec procedure-chain-hardening-and-java-contracts R11）。

- ``GenerationReceipt``：七类分流、失败不计入新建、请求内未填表头的份数只算工作簿、各入口同一措辞；
- ``create_template_workpaper``（链路编排 / IPO / B60 共用）：单码保存点，建行或落文件失败只回滚该码、
  删掉已落文件、进回执 failures；同一会话里此前未提交的写入不受影响（原先单码失败整会话 rollback）。
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex  # noqa: E402
from app.services import wp_generate_file, wp_template_init_service  # noqa: E402
from app.services.wp_generate_file import GeneratedWorkpaperFile, create_template_workpaper  # noqa: E402
from app.services.wp_generation_receipt import GenerationReceipt, failure_text  # noqa: E402

_TABLES = [User.__table__, Project.__table__, WpIndex.__table__, WorkingPaper.__table__]


def _file(name: str, from_template: bool = True) -> GeneratedWorkpaperFile:
    return GeneratedWorkpaperFile(path=Path(name), from_template=from_template)


# ── GenerationReceipt ────────────────────────────────────────────────────


def test_receipt_classifies_created_blank_and_header_states():
    r = GenerationReceipt()
    r.add_created("E1", _file("a.xlsx"), header_filled=False)
    r.add_created("ZZ9", _file("b.xlsx", from_template=False), header_filled=False)
    r.add_created("B60", _file("c.xlsm"), header_filled=False)
    r.add_created("A10", _file("d.docx"), header_filled=False)  # Word 没有表头格，不算「表头未填」
    r.add_created("J2A", _file("e.xlsx"), header_issue="打开底稿文件失败")
    r.add_failure("H1", RuntimeError("模板复制失败"))
    assert r.created_codes == ["E1", "ZZ9", "B60", "A10", "J2A"]
    assert r.blank_codes == ["ZZ9"]
    assert r.header_unfilled == 3
    assert r.header_failures == [{"wp_code": "J2A", "reason": "打开底稿文件失败"}]
    assert r.failures == [{"wp_code": "H1", "error": "模板复制失败"}]
    payload = r.to_payload()
    assert payload["created"] == 5, "失败不计入新建"
    assert set(payload) == {
        "created", "created_codes", "existing_codes", "skipped_trimmed_codes", "in_recycle_codes", "blank_codes",
        "failures", "header_failures", "header_unfilled", "ignored_codes", "message",
    }


def test_failure_text_uses_class_name_when_message_empty_and_truncates():
    assert failure_text(OSError()) == "OSError"
    assert failure_text(ValueError("  ")) == "ValueError"
    assert len(failure_text(RuntimeError("x" * 1000))) == 300
    assert failure_text("已有原因") == "已有原因"


def test_receipt_describe_lists_every_category_in_one_wording():
    r = GenerationReceipt(existing_codes=["E1"], skipped_trimmed_codes=["H3", "H3-1"], in_recycle_codes=["E2"],
                          ignored_codes=["ZZ1"])
    r.add_created("ZZ9", _file("b.xlsx", from_template=False), header_filled=False)
    r.add_created("J2A", _file("e.xlsx"), header_issue="打开底稿文件失败")
    r.add_failure("H1", RuntimeError("模板复制失败"))
    text = r.describe()
    assert text.startswith("已生成 2 个底稿")
    for part in ("1 个编码已有底稿，未重复生成：E1", "1 个选中的编码不在所选模板集里，未生成：ZZ1",
                 "2 个编码已在程序裁剪中标为不执行，未生成：H3、H3-1", "1 个编码的底稿在回收站中，请从回收站恢复：E2",
                 "1 个编码没有找到底稿模板，已建空白底稿：ZZ9", "1 个编码生成失败：H1（模板复制失败）",
                 "1 个底稿表头未填上：J2A（打开底稿文件失败）", "1 份底稿生成时未写入表头"):
        assert part in text, part
    assert GenerationReceipt().describe() == "已生成 0 个底稿"


# ── create_template_workpaper ────────────────────────────────────────────


@pytest.fixture
async def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(wp_template_init_service, "STORAGE_DIR", tmp_path / "wp_storage")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        pid = uuid.uuid4()
        db.add(Project(id=pid, name="【测试】生成回执", client_name="【测试】生成回执", status=ProjectStatus.execution,
                       template_type="soe", report_scope="standalone", audit_year=2025))
        await db.commit()
        yield {"db": db, "pid": pid, "tmp": tmp_path}
    await engine.dispose()


def _template_writer(tmp_path: Path, broken: set[str] = frozenset()):
    """替身 init：给编码写一份「模板」文件；``broken`` 里的编码抛错。"""

    def _init(*, project_id, wp_id, wp_code, scenario="normal", has_foreign_currency=False, **_kw):
        if wp_code in broken:
            raise OSError("模板文件被占用")
        target = wp_template_init_service.get_workpaper_storage_path(project_id, wp_id)
        target.write_bytes(b"PK-template")
        return target

    return _init


async def _codes(db, pid) -> list[str]:
    return sorted((await db.execute(sa.select(WpIndex.wp_code).where(WpIndex.project_id == pid))).scalars())


async def test_create_template_workpaper_success_binds_own_file(world, monkeypatch):
    monkeypatch.setattr(wp_template_init_service, "init_workpaper_from_template", _template_writer(world["tmp"]))
    receipt = GenerationReceipt()
    wp = await create_template_workpaper(world["db"], receipt, project_id=world["pid"], wp_code="E1",
                                         wp_name="货币资金", audit_cycle="E")
    assert wp is not None and Path(wp.file_path).is_file()
    assert Path(wp.file_path).parent == world["tmp"] / "wp_storage" / str(world["pid"])
    assert receipt.created_codes == ["E1"] and receipt.blank_codes == [] and receipt.header_unfilled == 1


async def test_template_copy_failure_is_a_failure_not_a_creation(world, monkeypatch):
    monkeypatch.setattr(wp_template_init_service, "init_workpaper_from_template",
                        _template_writer(world["tmp"], broken={"H1"}))
    db = world["db"]
    receipt = GenerationReceipt()
    for code in ("H1", "E1"):
        await create_template_workpaper(db, receipt, project_id=world["pid"], wp_code=code, wp_name=code,
                                        audit_cycle=code[0])
    assert receipt.created_codes == ["E1"]
    assert receipt.failures == [{"wp_code": "H1", "error": "模板文件被占用"}]
    assert await _codes(db, world["pid"]) == ["E1"], "复制失败的编码不留没有文件的底稿行"


async def test_failure_after_file_written_discards_file_and_keeps_earlier_session_work(world, monkeypatch):
    monkeypatch.setattr(wp_template_init_service, "init_workpaper_from_template", _template_writer(world["tmp"]))
    db = world["db"]
    # 同一会话里先前未提交的写入（链路编排里是试算表重算等）：单码失败不得把它一起回滚
    db.add(WpIndex(project_id=world["pid"], wp_code="PRE", wp_name="先前写入", audit_cycle="A"))
    await db.flush()
    calls = {"n": 0}
    real_flush = db.flush

    async def _flaky_flush(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:  # 第三次 flush = 落文件后回写 file_path
            raise RuntimeError("落库失败")
        return await real_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", _flaky_flush)
    receipt = GenerationReceipt()
    assert await create_template_workpaper(db, receipt, project_id=world["pid"], wp_code="E1", wp_name="货币资金",
                                           audit_cycle="E") is None
    monkeypatch.setattr(db, "flush", real_flush)
    assert receipt.failures == [{"wp_code": "E1", "error": "落库失败"}] and receipt.created_codes == []
    storage = world["tmp"] / "wp_storage" / str(world["pid"])
    assert not any(storage.glob("*")), "已落的文件随该码一起删掉（不留孤儿文件）"
    assert await _codes(db, world["pid"]) == ["PRE"], "只回滚失败的这一码"


async def test_missing_template_builds_blank_book_reported_as_blank(world, monkeypatch):
    monkeypatch.setattr(wp_template_init_service, "init_workpaper_from_template", lambda **kw: None)
    receipt = GenerationReceipt()
    wp = await create_template_workpaper(world["db"], receipt, project_id=world["pid"], wp_code="ZZ9",
                                         wp_name="未知", audit_cycle="Z")
    assert wp is not None and Path(wp.file_path).suffix == ".xlsx" and Path(wp.file_path).is_file()
    assert receipt.blank_codes == ["ZZ9"] and receipt.created_codes == ["ZZ9"]
    assert wp_generate_file.BLANK_NOTICE  # 空白册说明文字仍由 materialize_workpaper_file 写入
