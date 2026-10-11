# -*- coding: utf-8 -*-
"""新内容不得沿用「已被编辑器确认打开过」的代际 —— spec d2-online-edit-platform-closure · R13。

═══ 锁的是什么缺陷 ═══

2026-10-11 和平药房 D2：OO 保存 → 回表单 → 再点在线编辑。物化提交（HTML→OO，不随编辑
会话）沿用了当前代际（gen 3），同一用户的 lease 被复用，而它的 client-confirmation 钉在
上一会话的基线上 ⇒ ``confirm-descriptor`` 恒 422「同一编辑会话不得用不同基线二次确认」，
在线编辑从此打不开（直到 4 小时 lease 过期）。

更深一层的危害是 OnlyOffice 按 ``doc_key`` 缓存文档（``_next_generation_probe`` 里 G7/D4
分支早已写明的理由）：即便 confirm 放行，新内容沿用旧 ``doc_key`` 时编辑器拿到的是缓存的
旧文档，而 descriptor 记的基线是新内容 ⇒ 下一次保存会把 HTML 侧的改动当成「OO 改回去了」
静默覆盖。

═══ 判据 ═══

不随会话的提交（``plan.room_id is None``）遇到「候选代际的 room 已确认过」⇒ 换代；
随会话的提交（OO→HTML）照旧沿用会话所在代际；room 不存在 / 从未确认 ⇒ 沿用；终态 room 与
G7/D4 canary 的既有行为不变。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.workpaper_sync import content_mutation as CM

_WP = uuid.uuid4()
_D2 = "xlsx/gt-d2-accounts-receivable"
_D4 = "xlsx/gt-d4-operating-revenue"


class _Result:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _ScriptedReadOnlySession:
    """按 SELECT 的目标表回答 `_next_generation_probe` 的四条查询；收到写语句即判红。"""

    def __init__(self, *, pointer_generation: int | None, room: Any, max_rep: int, max_room: int) -> None:
        self.pointer_generation = pointer_generation
        self.room = room
        self.max_rep = max_rep
        self.max_room = max_room
        self.statements: list[str] = []

    async def execute(self, statement: Any, *_a: Any, **_k: Any) -> _Result:
        assert getattr(statement, "is_select", False), f"选代际只许读：{statement!r}"
        sql = str(statement).lower()
        self.statements.append(sql)
        if "working_paper_sync_entry_state" in sql:
            return _Result(self.pointer_generation)
        if "max(working_paper_content_representation.generation)" in sql:
            return _Result(self.max_rep)
        if "max(working_paper_oo_room.generation)" in sql:
            return _Result(self.max_room)
        if "from working_paper_oo_room" in sql:
            return _Result(self.room)
        raise AssertionError(f"未预期的查询：{sql}")


def _room(*, generation: int, state: str = "active", confirmed: bool) -> SimpleNamespace:
    return SimpleNamespace(
        generation=generation,
        state=state,
        refresh_required_at=None,
        refresh_reason=None,
        client_confirmed_base_version_id=uuid.uuid4() if confirmed else None,
    )


def _plan(*, entry_id: str = _D2, room_bound: bool) -> SimpleNamespace:
    return SimpleNamespace(
        wp_id=_WP, entry_id=entry_id, room_id=uuid.uuid4() if room_bound else None
    )


async def _probe(session: _ScriptedReadOnlySession, plan: SimpleNamespace) -> int:
    svc = CM.ContentMutationService(
        session=session,  # type: ignore[arg-type]
        repository=object(),  # type: ignore[arg-type]
        artifacts=object(),  # type: ignore[arg-type]
        resolution=object(),  # type: ignore[arg-type]
    )
    return await svc._next_generation_probe(plan)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_html_commit_rotates_away_from_a_generation_an_editor_has_opened() -> None:
    """R13 本体：和平药房 D2 的真栈形态（gen 3 room 已确认 + HTML→OO 物化提交）。"""
    session = _ScriptedReadOnlySession(
        pointer_generation=3, room=_room(generation=3, confirmed=True), max_rep=3, max_room=3
    )
    assert await _probe(session, _plan(room_bound=False)) == 4


@pytest.mark.asyncio
async def test_oo_commit_stays_in_the_session_generation() -> None:
    """OO→HTML 的结果就是会话里那份文档 ⇒ 必须留在会话所在代际（协同用户仍在同一间 room）。"""
    session = _ScriptedReadOnlySession(
        pointer_generation=3, room=_room(generation=3, confirmed=True), max_rep=3, max_room=3
    )
    assert await _probe(session, _plan(room_bound=True)) == 3


@pytest.mark.asyncio
async def test_unconfirmed_room_is_still_reused() -> None:
    """room 开了但从未有编辑器确认（OO 没缓存过这份文档）⇒ 沿用，不白烧代际。"""
    session = _ScriptedReadOnlySession(
        pointer_generation=2, room=_room(generation=2, state="opening", confirmed=False),
        max_rep=2, max_room=2,
    )
    assert await _probe(session, _plan(room_bound=False)) == 2


@pytest.mark.asyncio
async def test_generation_without_a_room_is_reused() -> None:
    """首版之后第一次物化：候选代际还没有 room ⇒ 沿用（与修复前同口径）。"""
    session = _ScriptedReadOnlySession(pointer_generation=1, room=None, max_rep=1, max_room=0)
    assert await _probe(session, _plan(room_bound=False)) == 1


@pytest.mark.parametrize("room_bound", [False, True])
@pytest.mark.asyncio
async def test_retired_room_still_rotates_for_both_origins(room_bound: bool) -> None:
    """既有行为（R5）不变：终态 room ⇒ 两种来源都换代。"""
    session = _ScriptedReadOnlySession(
        pointer_generation=3, room=_room(generation=3, state="superseded", confirmed=True),
        max_rep=3, max_room=3,
    )
    assert await _probe(session, _plan(room_bound=room_bound)) == 4


@pytest.mark.asyncio
async def test_canary_entries_keep_rotating_unconditionally() -> None:
    session = _ScriptedReadOnlySession(pointer_generation=5, room=None, max_rep=7, max_room=6)
    assert await _probe(session, _plan(entry_id=_D4, room_bound=True)) == 8
    assert all("entry_state" not in s for s in session.statements), "canary 分支不查 pointer"
