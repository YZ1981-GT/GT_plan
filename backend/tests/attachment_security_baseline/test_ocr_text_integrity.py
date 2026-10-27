"""附件识别文本完整性与确认留痕（spec attachment-security-baseline 需求 3.1–3.4、3.6，ADR-ASB-04）。

回归背景：列表 / 详情的 ``ocr_text`` 是 200 字预览，确认弹窗拿它当初值、确认时 ``PUT ocr-status`` 整体写回
⇒ 确认一次全文就被截成 200 字；确认状态没有落库；「重试识别」引用不存在的任务类型，什么都没调度。
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.attachment_models import Attachment
from app.routers import attachments as attachments_router_module
from app.services.attachment_ocr_text import OCR_PREVIEW_CHARS, text_sha256
from app.services.attachment_service import AttachmentService
from app.services.ocr_fields_service import OcrFieldsService
from tests.attachment_security_baseline._world import add_attachment, pg_attachment_world, sqlite_attachment_world

ROUTER = attachments_router_module.router
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
FULL = "银行询证函回函\n" + "".join(f"第{i:03d}行：账号 6222{i:04d} 余额 {i * 1000}.00 元；" for i in range(60))


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


async def _att(world, text: str | None = FULL, **values) -> Attachment:
    return await add_attachment(world, world.target, ocr_status="completed", ocr_text=text, **values)


async def _fresh(world, att: Attachment) -> Attachment:
    await world.db.refresh(att)  # 重新从库里读（不信会话里的对象）
    return att


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_fixture_text_is_longer_than_preview():
    assert len(FULL) > OCR_PREVIEW_CHARS * 5


# ── 全文与预览 ──


async def test_ocr_text_endpoint_returns_full_text_and_sha(world):
    att = await _att(world)
    user = (await world.member("readonly", "readonly")).user
    async with world.client(ROUTER, user=user) as client:
        full = await client.get(f"/api/attachments/{att.id}/ocr-text")
        detail = await client.get(f"/api/attachments/{att.id}")
    assert full.status_code == 200, full.text
    body = full.json()
    assert (body["ocr_text"], body["sha256"], body["length"]) == (FULL, _sha(FULL), len(FULL))
    assert body["ocr_confirmed"] is False
    preview = detail.json()
    assert preview["ocr_text"] == FULL[:OCR_PREVIEW_CHARS]
    assert (preview["ocr_text_length"], preview["ocr_text_truncated"], preview["ocr_confirmed"]) == (len(FULL), True, False)


# ── 确认 ──


async def test_confirm_with_preview_base_is_409_and_keeps_full_text(world):
    """弹窗若仍拿预览当基准（旧行为），确认必须被拒，库内全文不变。"""
    att = await _att(world)
    user = (await world.member("edit", "auditor")).user
    preview = FULL[:OCR_PREVIEW_CHARS]
    async with world.client(ROUTER, user=user) as client:
        resp = await client.post(f"/api/attachments/{att.id}/ocr-confirm",
                                 json={"base_sha256": _sha(preview), "ocr_text": preview})
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["error_code"] == "OCR_TEXT_CHANGED"
    row = await _fresh(world, att)
    assert (row.ocr_text, row.ocr_confirmed_sha256, row.ocr_confirmed_by) == (FULL, None, None)


async def test_confirm_unedited_records_who_and_when(world):
    att = await _att(world)
    user = (await world.member("edit", "auditor")).user
    async with world.client(ROUTER, user=user) as client:
        resp = await client.post(f"/api/attachments/{att.id}/ocr-confirm", json={"base_sha256": _sha(FULL).upper()})
        listed = await client.get(f"/api/attachments/{att.id}")
    assert resp.status_code == 200, resp.text
    assert (resp.json()["ocr_confirmed"], resp.json()["ocr_confirmed_edited"]) == (True, False)
    row = await _fresh(world, att)
    assert (row.ocr_text, row.ocr_confirmed_sha256, row.ocr_confirmed_by) == (FULL, _sha(FULL), user.id)
    assert row.ocr_confirmed_at is not None and row.ocr_status == "completed"
    assert listed.json()["ocr_confirmed"] is True
    assert listed.json()["ocr_confirmed_by"] == str(user.id)


async def test_confirm_with_revision_writes_full_revised_text(world):
    att = await _att(world)
    user = (await world.member("edit", "auditor")).user
    revised = FULL.replace("余额 0.00", "余额 0.01")
    async with world.client(ROUTER, user=user) as client:
        resp = await client.post(f"/api/attachments/{att.id}/ocr-confirm",
                                 json={"base_sha256": _sha(FULL), "ocr_text": revised})
    assert resp.status_code == 200, resp.text
    row = await _fresh(world, att)
    assert (row.ocr_text, row.ocr_confirmed_sha256, row.ocr_confirmed_edited) == (revised, _sha(revised), True)


async def test_confirmation_expires_when_any_writer_rewrites_text(world):
    att = await _att(world)
    user = (await world.member("edit", "auditor")).user
    async with world.client(ROUTER, user=user) as client:
        assert (await client.post(f"/api/attachments/{att.id}/ocr-confirm",
                                  json={"base_sha256": _sha(FULL)})).status_code == 200
        # 机器写入方（重新识别 / OCR 回写）改写文本，不清任何标记
        await AttachmentService(world.db).update_ocr_status(att.id, "completed", FULL + "补充页")
        await world.db.commit()
        after = await client.get(f"/api/attachments/{att.id}/ocr-text")
        stale = await client.post(f"/api/attachments/{att.id}/ocr-confirm", json={"base_sha256": _sha(FULL)})
    assert after.json()["ocr_confirmed"] is False
    assert stale.status_code == 409


async def test_confirm_empty_text(world):
    att = await _att(world, text=None)
    user = (await world.member("edit", "auditor")).user
    async with world.client(ROUTER, user=user) as client:
        resp = await client.post(f"/api/attachments/{att.id}/ocr-confirm", json={"base_sha256": text_sha256(None)})
    assert resp.status_code == 200 and resp.json()["ocr_confirmed"] is True


@pytest.mark.parametrize(("identity", "read", "confirm"), [
    ("anonymous", 401, 401), ("non_member", 403, 403), ("readonly", 200, 403), ("review", 200, 403),
    ("edit", 200, 200), ("admin", 200, 200), ("archived_edit", 200, 423),
])
async def test_permissions(world, identity, read, confirm):
    att = await _att(world)
    factories = {
        "anonymous": None,
        "non_member": world.non_member, "readonly": lambda: world.member("readonly", "readonly"),
        "review": lambda: world.member("review", "qc"), "edit": lambda: world.member("edit", "auditor"),
        "admin": world.admin_non_member, "archived_edit": world.archived_edit_member,
    }
    factory = factories[identity]
    user = (await factory()).user if factory else None
    async with world.client(ROUTER, user=user) as client:
        got = await client.get(f"/api/attachments/{att.id}/ocr-text")
        posted = await client.post(f"/api/attachments/{att.id}/ocr-confirm", json={"base_sha256": _sha(FULL)})
    assert (got.status_code, posted.status_code) == (read, confirm), (got.text, posted.text)
    row = await _fresh(world, att)
    assert (row.ocr_confirmed_sha256 is not None) == (confirm == 200)


# ── ocr-status 的 base 校验 ──


async def test_ocr_status_with_text_requires_matching_base(world):
    att = await _att(world)
    user = (await world.member("edit", "auditor")).user
    url = f"/api/attachments/{att.id}/ocr-status"
    preview = FULL[:OCR_PREVIEW_CHARS]
    async with world.client(ROUTER, user=user) as client:
        no_base = await client.put(url, json={"status": "completed", "ocr_text": preview})
        wrong = await client.put(url, json={"status": "completed", "ocr_text": preview, "base_sha256": _sha(preview)})
        assert (await _fresh(world, att)).ocr_text == FULL
        status_only = await client.put(url, json={"status": "failed"})
        ok = await client.put(url, json={"status": "completed", "ocr_text": FULL + "。", "base_sha256": _sha(FULL)})
    assert [r.status_code for r in (no_base, wrong, status_only, ok)] == [409, 409, 200, 200]
    row = await _fresh(world, att)
    assert (row.ocr_text, row.ocr_status) == (FULL + "。", "completed")


# ── 重试识别 ──


async def test_retry_ocr_schedules_recognition(world):
    att = await add_attachment(world, world.target, ocr_status="failed")
    user = (await world.member("edit", "auditor")).user
    seen: list[str] = []

    async def _trigger(self, attachment_id):
        row = (await self.db.execute(sa.select(Attachment).where(Attachment.id == attachment_id))).scalar_one()
        seen.append(row.ocr_status)  # 调度时状态已重置为待识别
        return {"status": "processing", "attachment_id": str(attachment_id), "job_id": "job-1"}, 202

    world.monkeypatch.setattr(OcrFieldsService, "get_or_trigger_ocr_fields", _trigger)
    async with world.client(ROUTER, user=user) as client:
        resp = await client.post(f"/api/attachments/{att.id}/retry-ocr")
    assert resp.status_code == 200, resp.text
    assert resp.json()["job_id"] == "job-1"
    assert seen == ["pending"]


def test_retry_ocr_no_longer_references_missing_task_type():
    """AST 判定（注释 / docstring 不算）：不再引用不存在的 ``TaskType.ocr_upload``，重试走识别调度。"""
    from app.services.task_center import TaskType

    assert not hasattr(TaskType, "ocr_upload")
    tree = ast.parse(Path(attachments_router_module.__file__).read_text(encoding="utf-8"))
    retry = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "retry_ocr")
    attrs = {n.attr for n in ast.walk(retry) if isinstance(n, ast.Attribute)}
    assert "ocr_upload" not in attrs and "get_or_trigger_ocr_fields" in attrs


# ── 迁移 ──


def test_v211_is_additive_and_replayable_by_construction():
    v = (MIGRATIONS / "V211__attachment_ocr_confirmation.sql").read_text(encoding="utf-8")
    r = (MIGRATIONS / "R211__attachment_ocr_confirmation.sql").read_text(encoding="utf-8")
    statements = [s.strip() for s in re.sub(r"--[^\n]*", "", v).split(";") if s.strip()]
    assert len(statements) == 4 and all("ADD COLUMN IF NOT EXISTS" in s for s in statements)
    dropped = re.findall(r"DROP COLUMN IF EXISTS (\w+)", r)
    added = re.findall(r"ADD COLUMN IF NOT EXISTS (\w+)", v)
    assert sorted(dropped) == sorted(added) == sorted(c for c in Attachment.__table__.columns.keys()
                                                       if c.startswith("ocr_confirmed"))


@pytest.mark.pg_only
async def test_v211_and_r211_replay_on_real_pg(monkeypatch):
    """真 PG 临时 schema 内：R211 → V211 → V211（重放无错）后四列齐全；再 R211 两次后四列消失。"""
    v = (MIGRATIONS / "V211__attachment_ocr_confirmation.sql").read_text(encoding="utf-8")
    r = (MIGRATIONS / "R211__attachment_ocr_confirmation.sql").read_text(encoding="utf-8")
    async with pg_attachment_world(monkeypatch) as w:
        conn = await w.db.connection()

        async def columns() -> set[str]:
            rows = await conn.exec_driver_sql(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
                "AND table_name = 'attachments' AND column_name LIKE 'ocr_confirmed%'")
            return {row[0] for row in rows}

        async def run(sql: str) -> None:  # asyncpg 预编译不收多语句：逐条执行
            for statement in (s.strip() for s in re.sub(r"--[^\n]*", "", sql).split(";")):
                if statement:
                    await conn.exec_driver_sql(statement)

        for sql in (r, v, v):
            await run(sql)
        assert await columns() == {"ocr_confirmed_sha256", "ocr_confirmed_by", "ocr_confirmed_at", "ocr_confirmed_edited"}
        for sql in (r, r):
            await run(sql)
        assert await columns() == set()
