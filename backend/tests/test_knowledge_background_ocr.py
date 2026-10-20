"""知识库扫描件后台 OCR（spec dsh-kb-ocr-local-first-routing Req 5，Task 7~9）。

SQLite 文件库（多会话：认领与围栏要两个连接各看各的）；OCR 识别函数注入替身，其余（认领 SQL、
状态机、围栏写回、上传管线、路由鉴权）全部真实执行。真实 PG 的 ``SKIP LOCKED`` 并发见
``test_knowledge_background_ocr_pg.py``。
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.core import User, UserRole  # noqa: E402
from app.models.knowledge_models import KnowledgeAccessLevel as L  # noqa: E402
from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder  # noqa: E402
from app.services import knowledge_ocr_service as S  # noqa: E402
from app.services.unified_ocr_service import OCRServiceUnavailableError  # noqa: E402
from app.workers import knowledge_ocr_worker as W  # noqa: E402

OWNER = uuid.UUID("00000000-0000-0000-0000-00000000e001")
OTHER = uuid.UUID("00000000-0000-0000-0000-00000000e002")
_TABLES = [User.__table__, KnowledgeFolder.__table__, KnowledgeDocument.__table__]


@pytest_asyncio.fixture
async def world(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'kb.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    folder_id = uuid.uuid4()
    async with factory() as s:
        s.add(KnowledgeFolder(id=folder_id, name="扫描件", access_level=L.public, created_by=OWNER))
        await s.commit()
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(b"%PDF-1.4 scanned")
    yield SimpleNamespace(engine=engine, factory=factory, folder_id=folder_id, scan=scan, tmp=tmp_path)
    await engine.dispose()


async def _add_doc(world, **fields) -> uuid.UUID:
    doc_id = uuid.uuid4()
    values = {"id": doc_id, "folder_id": world.folder_id, "name": "回函扫描.pdf", "file_type": "pdf",
              "storage_path": str(world.scan), "created_by": OWNER}
    values.update(fields)
    async with world.factory() as s:
        s.add(KnowledgeDocument(**values))
        await s.commit()
    return doc_id


async def _get(world, doc_id) -> KnowledgeDocument:
    async with world.factory() as s:
        return (await s.execute(sa.select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))).scalar_one()


async def _set(world, doc_id, **values) -> None:
    async with world.factory() as s:
        await s.execute(sa.update(KnowledgeDocument).where(KnowledgeDocument.id == doc_id).values(**values))
        await s.commit()


async def _claim(world):
    async with world.factory() as s:
        return await S.claim_next(s)


@pytest.fixture(autouse=True)
def _no_index_refresh(monkeypatch):
    refreshed: list = []

    async def _record(_factory, doc_id):
        refreshed.append(doc_id)

    monkeypatch.setattr(S, "_refresh_index", _record)
    return refreshed


def _recognizer(*outcomes):
    calls: list[str] = []
    queue = list(outcomes)

    async def _recognize(path: str) -> dict:
        calls.append(path)
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return {"text": item}

    _recognize.calls = calls  # type: ignore[attr-defined]
    return _recognize


# ---------------------------------------------------------------------------
# 可识别类型
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,file_type,expected", [
    ("回函.pdf", None, True), ("截图.PNG", None, True), ("扫描.jpeg", None, True),
    ("合同.docx", None, False), ("说明.txt", None, False), ("无扩展名", "pdf", True),
    ("x.pdf", "docx", False),  # file_type 优先
])
def test_ocr_eligibility(name, file_type, expected) -> None:
    assert S.is_ocr_eligible(name, file_type) is expected


# ---------------------------------------------------------------------------
# 认领 → 识别 → 写回
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_doc_is_claimed_recognized_and_text_written_back(world, _no_index_refresh) -> None:
    doc_id = await _add_doc(world, ocr_status="pending")
    claim = await _claim(world)
    assert claim is not None and claim.doc_id == doc_id and claim.attempt == 1
    leased = await _get(world, doc_id)
    assert leased.ocr_status == "running" and leased.ocr_attempts == 1
    assert leased.ocr_due_at is not None and leased.ocr_due_at.replace(tzinfo=None) > S._utcnow().replace(tzinfo=None)

    recognize = _recognizer("询证函回函\x00 金额 100,000.00 ")
    assert await S.process(claim, session_factory=world.factory, recognize=recognize) == "done"
    done = await _get(world, doc_id)
    assert done.ocr_status == "done" and done.ocr_error is None and done.ocr_due_at is None
    assert done.content_text == "询证函回函 金额 100,000.00"  # NUL 剔除、首尾空白去掉
    assert recognize.calls == [str(world.scan)]
    assert _no_index_refresh == [doc_id]
    assert await _claim(world) is None


@pytest.mark.asyncio
async def test_recognized_but_no_text_is_empty_not_failed(world, _no_index_refresh) -> None:
    doc_id = await _add_doc(world, ocr_status="pending")
    claim = await _claim(world)
    assert await S.process(claim, session_factory=world.factory, recognize=_recognizer("  ")) == "empty"
    doc = await _get(world, doc_id)
    assert doc.ocr_status == "empty" and doc.content_text is None and _no_index_refresh == []


@pytest.mark.asyncio
async def test_service_unavailable_backs_off_then_fails_after_max_attempts(world) -> None:
    doc_id = await _add_doc(world, ocr_status="pending")
    down = OCRServiceUnavailableError("服务器 OCR「paddleocrv6」：远程 OCR 服务不可达", kinds=("unavailable",))
    recognize = _recognizer(down, down, down)
    for attempt, delay in ((1, 60), (2, 300)):
        claim = await _claim(world)
        assert claim.attempt == attempt
        assert await S.process(claim, session_factory=world.factory, recognize=recognize) == "pending"
        doc = await _get(world, doc_id)
        assert doc.ocr_status == "pending" and "不可达" in doc.ocr_error
        wait = doc.ocr_due_at.replace(tzinfo=None) - S._utcnow().replace(tzinfo=None)
        assert timedelta(seconds=delay - 5) < wait <= timedelta(seconds=delay)
        assert await _claim(world) is None, "退避期内不得再认领"
        await _set(world, doc_id, ocr_due_at=S._utcnow() - timedelta(seconds=1))
    claim = await _claim(world)
    assert claim.attempt == 3
    assert await S.process(claim, session_factory=world.factory, recognize=recognize) == "failed"
    doc = await _get(world, doc_id)
    assert doc.ocr_status == "failed" and doc.ocr_error.startswith("多次识别失败") and doc.ocr_due_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("error,expected_reason", [
    (OCRServiceUnavailableError("远程 OCR 返回 HTTP 422（文件格式或尺寸不被接受）", kinds=("request",)), "拒绝了这份文件"),
    (FileNotFoundError("gone"), "文件不存在"),
])
async def test_file_problems_fail_without_retry(world, error, expected_reason) -> None:
    doc_id = await _add_doc(world, ocr_status="pending")
    claim = await _claim(world)
    assert await S.process(claim, session_factory=world.factory, recognize=_recognizer(error)) == "failed"
    doc = await _get(world, doc_id)
    assert doc.ocr_status == "failed" and expected_reason in doc.ocr_error and doc.ocr_attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kinds", [("unavailable", "request"), ()])
async def test_mixed_kinds_are_retried(world, kinds) -> None:
    """不全是文件本身的问题 ⇒ 退避重试：本机未安装（unavailable）+ 服务器拒收（request）；
    或者根本没有候选可试（未配置 OCR 模型，kinds 为空 —— 管理员配好后应能自动补识别）。"""
    doc_id = await _add_doc(world, ocr_status="pending")
    claim = await _claim(world)
    error = OCRServiceUnavailableError("x", kinds=kinds)
    assert await S.process(claim, session_factory=world.factory, recognize=_recognizer(error)) == "pending"
    assert (await _get(world, doc_id)).ocr_status == "pending"


@pytest.mark.asyncio
async def test_doc_without_storage_fails(world) -> None:
    doc_id = await _add_doc(world, ocr_status="pending", storage_path=None)
    claim = await _claim(world)
    assert await S.process(claim, session_factory=world.factory, recognize=_recognizer("x")) == "failed"
    assert "没有存储文件" in (await _get(world, doc_id)).ocr_error


@pytest.mark.asyncio
async def test_stale_lease_result_is_discarded(world) -> None:
    """租约过期被别的 worker 接手后，原 worker 迟到的结果不得覆盖（围栏 = ocr_attempts）。"""
    doc_id = await _add_doc(world, ocr_status="pending")
    first = await _claim(world)
    await _set(world, doc_id, ocr_due_at=S._utcnow() - timedelta(seconds=1))  # 模拟进程卡死、租约过期
    second = await _claim(world)
    assert second.attempt == 2
    assert await S.process(first, session_factory=world.factory, recognize=_recognizer("旧结果")) == "stale"
    assert (await _get(world, doc_id)).ocr_status == "running"
    assert await S.process(second, session_factory=world.factory, recognize=_recognizer("新结果")) == "done"
    assert (await _get(world, doc_id)).content_text == "新结果"


async def _rival_claims(world, doc_id) -> str:
    claim = await _claim(world)
    assert claim is not None and claim.doc_id == doc_id
    return "rival"


async def _original_worker_backs_off(world, doc_id) -> str:
    late = S.OcrClaim(doc_id, 1, str(world.scan), "回函扫描.pdf")
    due = S._utcnow() + timedelta(minutes=5)
    assert await S._finish(world.factory, late, "pending", error="服务暂不可用", due=due) == "pending"
    return "backoff"


@pytest.mark.asyncio
@pytest.mark.parametrize("start,interleave,expect_status,expect_attempts", [
    # 新文档：别的 worker 抢先认领（attempts 0→1）
    ({"ocr_status": "pending"}, _rival_claims, "running", 1),
    # 租约过期：别的 worker 抢先接手（status 前后都是 running，只有 attempts 能区分）
    ({"ocr_status": "running", "ocr_attempts": 1}, _rival_claims, "running", 2),
    # 租约过期：原 worker 迟到的结果把它退回 pending 并排了退避（attempts 不变，只有 status 能区分）
    ({"ocr_status": "running", "ocr_attempts": 1}, _original_worker_backs_off, "pending", 1),
])
async def test_claim_fence_rejects_row_changed_between_select_and_update(
    world, start, interleave, expect_status, expect_attempts,
) -> None:
    """SQLite 没有行锁（PG 的 SKIP LOCKED 见 _pg 用例）：读到候选行之后、写之前它被改了 ⇒ 条件更新 0 行，不得认领。"""
    if start["ocr_status"] == "running":
        start = {**start, "ocr_due_at": S._utcnow() - timedelta(seconds=1)}
    doc_id = await _add_doc(world, **start)
    happened: list[str] = []

    async with world.factory() as s:
        real_execute = s.execute

        async def _execute(stmt, *args, **kwargs):
            result = await real_execute(stmt, *args, **kwargs)
            if isinstance(stmt, sa.Select) and not happened:
                happened.append(await interleave(world, doc_id))
            return result

        s.execute = _execute  # type: ignore[method-assign]
        mine = await S.claim_next(s)

    assert happened, "插入点没有触发（认领语句形态变了，本用例失效）"
    assert mine is None, "条件更新没有挡住：候选行已被改动仍被认领"
    doc = await _get(world, doc_id)
    assert (doc.ocr_status, doc.ocr_attempts) == (expect_status, expect_attempts)


@pytest.mark.asyncio
async def test_expired_lease_with_attempts_exhausted_is_failed_not_reclaimed(world) -> None:
    doc_id = await _add_doc(
        world, ocr_status="running", ocr_attempts=S.MAX_ATTEMPTS,
        ocr_due_at=S._utcnow() - timedelta(minutes=1),
    )
    assert await _claim(world) is None
    doc = await _get(world, doc_id)
    assert doc.ocr_status == "failed" and "多次中断" in doc.ocr_error
    # 原 worker 其实没死、迟到交回结果：租约已作废（状态已是 failed），不得把它改回去
    late = S.OcrClaim(doc_id, S.MAX_ATTEMPTS, str(world.scan), "回函扫描.pdf")
    assert await S.process(late, session_factory=world.factory, recognize=_recognizer("迟到")) == "stale"
    doc = await _get(world, doc_id)
    assert doc.ocr_status == "failed" and doc.content_text is None


@pytest.mark.asyncio
async def test_live_lease_and_deleted_and_finished_docs_are_not_claimed(world) -> None:
    await _add_doc(world, ocr_status="running", ocr_attempts=1, ocr_due_at=S._utcnow() + timedelta(minutes=5))
    await _add_doc(world, ocr_status="pending", is_deleted=True)
    for status in ("done", "empty", "failed", None):
        await _add_doc(world, ocr_status=status)
    assert await _claim(world) is None


@pytest.mark.asyncio
async def test_drain_processes_queue_in_order(world) -> None:
    first = await _add_doc(world, ocr_status="pending", name="a.pdf")
    second = await _add_doc(world, ocr_status="pending", name="b.pdf")
    handled = await W.drain(session_factory=world.factory, recognize=_recognizer("甲", "乙"))
    assert handled == 2
    assert {(await _get(world, first)).ocr_status, (await _get(world, second)).ocr_status} == {"done"}


async def _until(predicate, *, seconds: float = 2.0) -> bool:
    import asyncio

    for _ in range(int(seconds / 0.01)):
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


@pytest.mark.asyncio
async def test_worker_switch_and_wake(monkeypatch) -> None:
    """开关关闭不启动；打开后首轮立即处理，上传后 wake() 不等 30 秒轮询就开下一轮；stop 后退出。"""
    import asyncio

    from app.core.config import settings

    beats: list[str] = []
    rounds: list[int] = []

    async def _beat(name):
        beats.append(name)

    async def _drain(**_kw):
        rounds.append(len(rounds))
        return 0

    monkeypatch.setattr(W, "write_heartbeat", _beat)
    monkeypatch.setattr(W, "drain", _drain)
    monkeypatch.setattr(W, "POLL_SECONDS", 30.0)
    monkeypatch.setattr(W, "_wake_event", None)

    stop = asyncio.Event()
    monkeypatch.setattr(settings, "KNOWLEDGE_OCR_WORKER_ENABLED", False)
    await asyncio.wait_for(W.run(stop), timeout=2)
    assert rounds == [] and beats == []

    monkeypatch.setattr(settings, "KNOWLEDGE_OCR_WORKER_ENABLED", True)
    task = asyncio.create_task(W.run(stop))
    try:
        assert await _until(lambda: len(rounds) == 1), "打开开关后没有立即处理首轮"
        await asyncio.sleep(0.05)
        assert len(rounds) == 1  # 没有新文档时等轮询，不空转
        W.wake()
        assert await _until(lambda: len(rounds) == 2), "wake() 没有让 worker 立即开下一轮"
        stop.set()
        await asyncio.wait_for(task, timeout=2)
    finally:
        task.cancel()
    assert beats == ["knowledge_ocr_worker"] * 2


# ---------------------------------------------------------------------------
# 重新识别
# ---------------------------------------------------------------------------


def _doc_like(**kw):
    base = {"name": "回函扫描.pdf", "file_type": "pdf", "ocr_status": "failed", "content_text": None,
            "ocr_attempts": 3, "ocr_error": "x", "ocr_due_at": None}
    base.update(kw)
    return SimpleNamespace(**base)


def test_request_retry_resets_failed_doc() -> None:
    doc = _doc_like()
    S.request_retry(doc)
    assert (doc.ocr_status, doc.ocr_attempts, doc.ocr_error, doc.ocr_due_at) == ("pending", 0, None, None)


@pytest.mark.parametrize("kw,reason", [
    ({"ocr_status": "running"}, "识别中"),
    ({"ocr_status": "pending"}, "识别中"),
    ({"content_text": "已有正文"}, "已有正文"),
    ({"name": "合同.docx", "file_type": "docx"}, "不支持"),
])
def test_request_retry_rejections(kw, reason) -> None:
    with pytest.raises(S.OcrRetryRejected, match=reason):
        S.request_retry(_doc_like(**kw))


# ---------------------------------------------------------------------------
# 上传管线：扫描件排队、回执、唤醒
# ---------------------------------------------------------------------------


class _Upload:
    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self._data = data

    async def read(self) -> bytes:
        return self._data


@pytest.mark.asyncio
async def test_upload_queues_scanned_files_and_wakes_worker(world, monkeypatch) -> None:
    from app.services import knowledge_upload_service as U
    from app.services.knowledge_folder_service import KnowledgeDocumentService

    monkeypatch.setattr(U, "_knowledge_storage_base", lambda _fid: world.tmp)
    woken: list[bool] = []
    monkeypatch.setattr(W, "wake", lambda: woken.append(True))

    async def _insert(db, svc: KnowledgeDocumentService, **fields):
        async with db.begin_nested():
            return await svc.create_document(**fields)

    async def _extract(_path, _content, name):
        return "有文字层的正文" if name == "文字版.pdf" else None

    files = [_Upload("回函扫描.pdf", b"%PDF scan"), _Upload("空白.docx", b"PK"), _Upload("文字版.pdf", b"%PDF text")]
    async with world.factory() as db:
        receipt = await U.store_uploaded_files(
            db, world.folder_id, files, SimpleNamespace(id=OWNER), None,
            insert_document=_insert, extract_text=_extract, trigger_index_update=AsyncMock(),
        )
    by_name = {f["name"]: f for f in receipt["files"]}
    assert by_name["回函扫描.pdf"]["ocr_queued"] is True and by_name["回函扫描.pdf"]["text_extracted"] is False
    assert by_name["空白.docx"]["ocr_queued"] is False   # 不可 OCR 的类型不排队
    assert by_name["文字版.pdf"]["ocr_queued"] is False  # 已有文字层
    assert woken == [True]
    statuses = {f["name"]: (await _get(world, uuid.UUID(f["id"]))).ocr_status for f in receipt["files"]}
    assert statuses == {"回函扫描.pdf": "pending", "空白.docx": None, "文字版.pdf": None}


@pytest.mark.asyncio
async def test_upload_without_scans_does_not_wake(world, monkeypatch) -> None:
    from app.services import knowledge_upload_service as U

    monkeypatch.setattr(U, "_knowledge_storage_base", lambda _fid: world.tmp)
    woken: list[bool] = []
    monkeypatch.setattr(W, "wake", lambda: woken.append(True))

    async def _insert(db, svc, **fields):
        async with db.begin_nested():
            return await svc.create_document(**fields)

    async with world.factory() as db:
        await U.store_uploaded_files(
            db, world.folder_id, [_Upload("说明.txt", "正文".encode())], SimpleNamespace(id=OWNER), None,
            insert_document=_insert, extract_text=AsyncMock(return_value=None), trigger_index_update=AsyncMock(),
        )
    assert woken == []


# ---------------------------------------------------------------------------
# 路由：列表带状态、重新识别端点
# ---------------------------------------------------------------------------


class _Actor:
    def __init__(self, uid, role):
        self.id, self.role = uid, role
        self.username = f"u-{uid.hex[-4:]}"
        self.email = f"{self.username}@example.com"
        self.is_active = True


@pytest_asyncio.fixture
async def api(world):
    from app.routers.knowledge_folders import router

    current = {"actor": _Actor(OWNER, UserRole.auditor)}
    app = FastAPI()
    app.include_router(router)

    async def _db():
        async with world.factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: current["actor"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(client=client, current=current)


@pytest.mark.asyncio
async def test_list_documents_reports_ocr_status(world, api) -> None:
    await _add_doc(world, ocr_status="failed", ocr_error="远程 OCR 认证失败，请检查 API Key")
    resp = await api.client.get(f"/api/knowledge-library/folders/{world.folder_id}/documents")
    assert resp.status_code == 200
    row = resp.json()[0]
    assert row["has_text"] is False and row["ocr_status"] == "failed"
    assert row["ocr_error"] == "远程 OCR 认证失败，请检查 API Key"


@pytest.mark.asyncio
async def test_retry_endpoint_requeues_and_wakes(world, api, monkeypatch) -> None:
    woken: list[bool] = []
    monkeypatch.setattr(W, "wake", lambda: woken.append(True))
    doc_id = await _add_doc(world, ocr_status="failed", ocr_attempts=3, ocr_error="多次识别失败")
    resp = await api.client.post(f"/api/knowledge-library/documents/{doc_id}/ocr-retry")
    assert resp.status_code == 200 and resp.json()["ocr_status"] == "pending"
    doc = await _get(world, doc_id)
    assert (doc.ocr_status, doc.ocr_attempts, doc.ocr_error) == ("pending", 0, None)
    assert woken == [True]

    again = await api.client.post(f"/api/knowledge-library/documents/{doc_id}/ocr-retry")
    assert again.status_code == 409 and "识别中" in again.json()["detail"]


@pytest.mark.asyncio
async def test_retry_endpoint_requires_manage_permission(world, api) -> None:
    doc_id = await _add_doc(world, ocr_status="failed")
    api.current["actor"] = _Actor(OTHER, UserRole.auditor)
    resp = await api.client.post(f"/api/knowledge-library/documents/{doc_id}/ocr-retry")
    assert resp.status_code == 403
    assert (await _get(world, doc_id)).ocr_status == "failed"
    missing = await api.client.post(f"/api/knowledge-library/documents/{uuid.uuid4()}/ocr-retry")
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# 统一 OCR 冷却口径（ADR-DKR-006）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,cools", [("request", False), ("timeout", False), ("unavailable", True), ("config", True)])
async def test_remote_ocr_failure_cools_only_when_candidate_unavailable(monkeypatch, kind, cools) -> None:
    from app.services import remote_ocr_runtime as remote
    from app.services.llm_route import is_cooling, reset_route_health
    from app.services.unified_ocr_service import UnifiedOCRService

    reset_route_health()
    config = SimpleNamespace(
        is_remote=True, deployment="server", identity="paddleocr|https://ai.example/ocr|paddleocrv6"
    )
    candidate = remote.OCRRouteCandidate("ocr", "server", "paddleocrv6", config=config)

    async def _route(capability, *, db=None):
        return [candidate]

    monkeypatch.setattr(remote, "resolve_ocr_route", _route)
    error = remote.RemoteOCRRuntimeError("ocr_x", f"失败（{kind}）", kind=kind)
    monkeypatch.setattr(remote, "recognize_remote_file", AsyncMock(side_effect=error))
    with pytest.raises(OCRServiceUnavailableError) as exc:
        await UnifiedOCRService().recognize("scan.pdf")
    assert exc.value.kinds == (kind,)
    assert is_cooling(candidate.identity) is cools
    reset_route_health()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,expected_kind", [
    (404, "config"),          # 端点 / API 路径配错：候选不可用，冷却
    (401, "config"),          # Key 错：同上
    (503, "unavailable"),
    (422, "request"),         # 这份文件格式 / 尺寸不被接受：不冷却、后台不重试
    (413, "request"),
    (400, "request"),
    (httpx.ConnectTimeout, "unavailable"),  # 连不上：服务挂了
    (httpx.ConnectError, "unavailable"),
    (httpx.ReadTimeout, "timeout"),         # 连上了但这份文件处理太久：不冷却
])
async def test_remote_ocr_failure_kind_by_cause(monkeypatch, outcome, expected_kind) -> None:
    from app.core.config import settings
    from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
    from app.services import remote_ocr_runtime as remote
    from app.services.ai_model_secret_service import encrypt_api_key
    from app.services.llm_endpoint_policy import SafeEndpoint

    monkeypatch.setattr(settings, "ENCRYPTION_KEY", "kb-ocr-kind-test-key")
    config = remote.resolve_ocr_config_from_model(AIModelConfig(
        id=uuid.uuid4(), model_name="paddleocrv6", model_type=AIModelType.ocr, provider=AIProvider.paddleocr,
        endpoint_url="https://ocr.example.com:10080", api_key_ciphertext=encrypt_api_key("placeholder-not-real"),
        ocr_capability="ocr", ocr_protocol="paddlex_json", api_path="/ocr", auth_scheme="bearer",
        request_timeout_seconds=60, is_active=True, is_deleted=False,
    ))

    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(outcome, int):
            return httpx.Response(outcome, json={"errorMsg": "x"})
        raise outcome("模拟", request=request)

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    async def _describe(_endpoint, _exc):
        return "模拟网络失败"

    monkeypatch.setattr(
        remote, "resolve_endpoint",
        AsyncMock(return_value=SafeEndpoint("https://ocr.example.com:10080", "ocr.example.com")),
    )
    monkeypatch.setattr(remote, "describe_network_failure", _describe)
    monkeypatch.setattr(remote.httpx, "AsyncClient", client_factory)
    with pytest.raises(remote.RemoteOCRRuntimeError) as exc:
        await remote.recognize_remote_bytes(config, b"%PDF scan", filename="scan.pdf")
    assert exc.value.kind == expected_kind
