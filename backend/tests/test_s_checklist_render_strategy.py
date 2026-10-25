from __future__ import annotations

import json
from types import SimpleNamespace

from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.routers.wp_render_strategies._s_checklist_sheets import (
    S_CHECKLIST_ITEM_IDS,
    render,
)


class _Result:
    def __init__(self, row: object | None) -> None:
        self._row = row

    def fetchone(self) -> object | None:
        return self._row


class _Savepoint:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def __aenter__(self) -> _Savepoint:
        self.events.append("savepoint_enter")
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        self.events.append("savepoint_rollback" if exc_type else "savepoint_release")
        return False


class _Session:
    def __init__(self, row: object | None = None, error: Exception | None = None) -> None:
        self.row = row
        self.error = error
        self.events: list[str] = []
        self.calls: list[tuple[object, dict[str, str]]] = []

    def begin_nested(self) -> _Savepoint:
        self.events.append("begin_nested")
        return _Savepoint(self.events)

    async def execute(self, statement, params: dict[str, str]) -> _Result:
        self.calls.append((statement, params))
        if self.error:
            raise self.error
        return _Result(self.row)


def _context(component_type: str, db: _Session, sheet_name: str = "目标 sheet"):
    return SimpleNamespace(
        component_type=component_type,
        wp_id="wp-1",
        classification=SimpleNamespace(sheet_name=sheet_name),
        db=db,
    )


def test_all_s_checklist_component_types_are_registered_to_the_dedicated_strategy() -> None:
    assert len(S_CHECKLIST_ITEM_IDS) == 12
    assert set(S_CHECKLIST_ITEM_IDS).issubset(RENDERER_DISPATCH)
    assert {RENDERER_DISPATCH[component_type] for component_type in S_CHECKLIST_ITEM_IDS} == {render}


async def test_each_registered_type_dispatches_and_merges_its_saved_payload() -> None:
    """每个可写类型都必须经真实 dispatch 入口读取并合并自己的 payload。"""
    for component_type, item_id in S_CHECKLIST_ITEM_IDS.items():
        if item_id is None:
            continue

        sheet_name = f"{component_type} 精确 sheet"
        db = _Session(
            row=SimpleNamespace(
                remark=json.dumps(
                    {
                        "payload_marker": f"loaded:{component_type}",
                        # Payload 不能覆盖 dispatch 当前身份。
                        "component_type": "spoofed",
                        "sheet_name": "spoofed",
                        "cells": {"A1": "must not escape"},
                    },
                    ensure_ascii=False,
                )
            )
        )

        # 通过生产注册集合调用，而不是直接调用 render 实现。
        result = await RENDERER_DISPATCH[component_type](_context(component_type, db, sheet_name))

        assert result["payload_marker"] == f"loaded:{component_type}"
        assert result["component_type"] == component_type
        assert result["sheet_name"] == sheet_name
        assert "cells" not in result
        assert db.calls[0][1] == {"wp_id": "wp-1", "item_id": item_id}
        assert db.events == ["begin_nested", "savepoint_enter", "savepoint_release"]


async def test_each_registered_type_no_row_returns_light_dedicated_payload() -> None:
    """无 checklist 行也必须返回专属轻量结果，不进入网格/OnlyOffice fallback。"""
    for component_type in S_CHECKLIST_ITEM_IDS:
        db = _Session()
        sheet_name = f"{component_type} 精确 sheet"
        result = await RENDERER_DISPATCH[component_type](_context(component_type, db, sheet_name))

        assert result == {
            "component_type": component_type,
            "sheet_name": sheet_name,
        }
        assert "cells" not in result
        assert result["component_type"] != "onlyoffice-sheet"
        if S_CHECKLIST_ITEM_IDS[component_type] is None:
            assert db.calls == []
            assert db.events == []
        else:
            assert db.events == ["begin_nested", "savepoint_enter", "savepoint_release"]


async def test_each_item_backed_dispatch_failure_rolls_back_savepoint() -> None:
    """每个需要查库的真实 dispatch 分支都必须隔离异常并保留诊断结果。"""
    for component_type, item_id in S_CHECKLIST_ITEM_IDS.items():
        if item_id is None:
            continue

        db = _Session(error=RuntimeError(f"db unavailable: {component_type}"))
        sheet_name = f"{component_type} 精确 sheet"
        result = await RENDERER_DISPATCH[component_type](_context(component_type, db, sheet_name))

        assert result == {
            "component_type": component_type,
            "sheet_name": sheet_name,
            "error": "checklist_responses_unavailable",
        }
        assert "cells" not in result
        assert db.calls[0][1] == {"wp_id": "wp-1", "item_id": item_id}
        assert db.events == ["begin_nested", "savepoint_enter", "savepoint_rollback"]
