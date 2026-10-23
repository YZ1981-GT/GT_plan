"""status 2 回 0 之后关闭 room 的判据与接线（spec writeback-followup-issue-closure R1.1~1.3 / D1）。

两层：

* ``close_room_if_docserver_saved`` 的判定（替身会话，不连库）：只有「已 durable 的 status 2」关闭；
  status 4、未 durable、找不到 delivery 都不动；关闭失败不抛（回调必须回 0）。
* 路由接线（AST）：关闭调用在 apply **之后**、且不被「有没有 application」门控 —— 归组成
  recovery case 的 status 2 同样作废了 key。真库的状态边与换代见
  ``test_room_close_after_docserver_saved_pg.py`` / ``test_task25_room_generation_reuse_pg.py``。
"""
from __future__ import annotations

import ast
import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.workpaper_sync import callback_room_close as CRC

_ROUTER = Path(__file__).resolve().parents[2] / "app" / "routers" / "wp_sync_router.py"


class _Result:
    def __init__(self, row: Any) -> None:
        self._row = row

    def one_or_none(self) -> Any:
        return self._row


class _Session:
    """只记录调用顺序的会话替身；``execute`` 回给定的 delivery 行。"""

    def __init__(self, row: Any) -> None:
        self.row = row
        self.calls: list[str] = []

    async def rollback(self) -> None:
        self.calls.append("rollback")

    async def commit(self) -> None:
        self.calls.append("commit")

    async def execute(self, stmt: Any) -> _Result:
        self.calls.append("execute")
        return _Result(self.row)


def _row(status: int, *, durable: bool) -> SimpleNamespace:
    return SimpleNamespace(
        callback_status=status,
        durable_at=datetime.now(timezone.utc) if durable else None,
    )


@pytest.fixture()
def closed(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    calls: list[uuid.UUID] = []

    async def _close(self: Any, *, room_id: uuid.UUID) -> None:
        calls.append(room_id)

    monkeypatch.setattr(CRC.RoomService, "close_after_docserver_saved", _close)
    return calls


def _run(session: _Session, *, delivery_id: uuid.UUID | None = None) -> tuple[bool, uuid.UUID]:
    room = uuid.uuid4()
    did = uuid.uuid4() if delivery_id is None else delivery_id
    return asyncio.run(CRC.close_room_if_docserver_saved(session, room_id=room, delivery_id=did)), room


def test_durable_status_2_closes_and_commits(closed: list[uuid.UUID]) -> None:
    session = _Session(_row(2, durable=True))
    went, room = _run(session)
    assert went is True
    assert closed == [room]
    assert session.calls == ["rollback", "execute", "commit"]


@pytest.mark.parametrize(
    "row",
    [
        pytest.param(_row(4, durable=False), id="status-4-no-changes"),
        # 现实中 status 4 不下载、不会 durable；这一条把「只认 status 2」与 durable 判据解耦钉住
        pytest.param(_row(4, durable=True), id="status-4-even-if-durable"),
        pytest.param(_row(6, durable=True), id="status-6-forcesave"),
        pytest.param(_row(2, durable=False), id="status-2-not-durable"),
        pytest.param(None, id="delivery-missing"),
    ],
)
def test_everything_else_leaves_the_room_alone(closed: list[uuid.UUID], row: Any) -> None:
    session = _Session(row)
    went, _ = _run(session)
    assert went is False
    assert closed == []
    assert "commit" not in session.calls


def test_no_delivery_id_touches_nothing(closed: list[uuid.UUID]) -> None:
    session = _Session(_row(2, durable=True))
    went = asyncio.run(
        CRC.close_room_if_docserver_saved(session, room_id=uuid.uuid4(), delivery_id=None)
    )
    assert went is False and closed == [] and session.calls == []


def test_close_failure_is_swallowed_and_rolled_back(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(self: Any, *, room_id: uuid.UUID) -> None:
        raise RuntimeError("lock timeout")

    monkeypatch.setattr(CRC.RoomService, "close_after_docserver_saved", _boom)
    session = _Session(_row(2, durable=True))
    went, _ = _run(session)
    assert went is False
    assert session.calls == ["rollback", "execute", "rollback"]


def test_final_save_status_is_2_only() -> None:
    """status 4 不关（文档服务器没有保存那个 key），契约 room_transition 的偏离写在 design。"""
    assert CRC.DOCSERVER_FINAL_SAVE_STATUS == 2


# ─────────────────────────────────────────────────────────────────────────
# 路由接线
# ─────────────────────────────────────────────────────────────────────────


def _handler() -> ast.AsyncFunctionDef:
    tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "post_room_onlyoffice_callback":
            return node
    raise AssertionError("找不到 post_room_onlyoffice_callback")


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        f = node.func
        return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
    return None


def test_router_closes_after_apply_and_for_unmatched_too() -> None:
    fn = _handler()
    top = list(fn.body)
    close_at = next(
        i for i, stmt in enumerate(top)
        if any(_call_name(n) == "close_room_if_docserver_saved" for n in ast.walk(stmt))
    )
    apply_at = next(
        i for i, stmt in enumerate(top)
        if any(_call_name(n) == "_apply_durable_incoming" for n in ast.walk(stmt))
    )
    assert apply_at < close_at, "关闭必须在 apply 之后：apply 结算的是这一代 room"
    # 关闭语句是函数体顶层语句，不在任何 if 里 ⇒ 未归组（recovery case）的 status 2 也会走到。
    assert isinstance(top[close_at], ast.Expr), ast.unparse(top[close_at])
    # 非零 ack（durable 前失败）在它之前就返回 ⇒ 被拒的 status 2 不关 room（R1.2）。
    early_error_return = next(
        i for i, stmt in enumerate(top)
        if isinstance(stmt, ast.If) and "response_error" in ast.unparse(stmt.test)
    )
    assert early_error_return < close_at
