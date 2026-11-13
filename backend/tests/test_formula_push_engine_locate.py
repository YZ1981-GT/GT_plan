"""公式推送运行计划一次查询定位全部底稿编码（消 N+1；从 ``test_formula_push_engine.py`` 挪出，该文件超行数门）。

spec: note-disclosure-pull-regression-and-headless-backend 批 1（随 ``85caab386`` 覆盖丢失的批量定位一起恢复）
"""
from __future__ import annotations

import uuid

import pytest

from app.services.formula_push import engine as push


@pytest.mark.asyncio
async def test_workpaper_plan_locates_all_codes_in_one_query():
    project_id = uuid.uuid4()
    ids = {"E1": uuid.uuid4(), "K1": uuid.uuid4()}

    class Result:
        def all(self):
            return [
                (ids["E1"], "draft", "E1"),
                (ids["K1"], "review_passed", "K1"),
            ]

    class Db:
        def __init__(self):
            self.calls = []

        async def execute(self, statement, params):
            self.calls.append((statement, params))
            return Result()

    db = Db()
    found = await push._find_workpapers_for_codes(
        db,
        project_id,
        ["E1", "K1", "E1"],
    )

    assert len(db.calls) == 1
    assert db.calls[0][1]["codes"] == ["E1", "K1"]
    assert found["E1"][0].id == ids["E1"]
    assert found["K1"][0].status == "review_passed"
