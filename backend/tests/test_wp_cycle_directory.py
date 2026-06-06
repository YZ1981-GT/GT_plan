"""wp_cycle_directory — 循环底稿目录服务测试

覆盖：
- _natural_key 自然排序（D2-1 < D2-10 < D3，D1 < D1A）
- build_cycle_workpapers：audit_cycle 为空 → []（不查库）
- build_cycle_workpapers：DB 异常 → [] 降级（不抛）
- build_cycle_workpapers：正常组装 + is_current 标注 + wp_id None 透传 + 排序
"""

from __future__ import annotations

import uuid

import pytest

from app.services.wp_cycle_directory import _natural_key, build_cycle_workpapers


# ─────────────────────── 自然排序 ───────────────────────

def test_natural_key_numeric_ordering():
    codes = ["D2-10", "D2-1", "D2-2", "D3", "D10", "D1"]
    ordered = sorted(codes, key=_natural_key)
    assert ordered == ["D1", "D2-1", "D2-2", "D2-10", "D3", "D10"]


def test_natural_key_letter_suffix():
    # D1 < D1A（数字段相同，字母后缀比较）
    assert _natural_key("D1") < _natural_key("D1A")


# ─────────────────────── build_cycle_workpapers 降级 ───────────────────────

@pytest.mark.asyncio
async def test_empty_cycle_returns_empty():
    # audit_cycle 为空 → 直接返回 []，不触碰 db（传 None 也不报错）
    out = await build_cycle_workpapers(
        db=None, project_id=uuid.uuid4(), audit_cycle=None, current_wp_id=uuid.uuid4(),
    )
    assert out == []


class _FailingDB:
    async def execute(self, *_a, **_k):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_db_error_degrades_to_empty():
    out = await build_cycle_workpapers(
        db=_FailingDB(), project_id=uuid.uuid4(), audit_cycle="D",
        current_wp_id=uuid.uuid4(),
    )
    assert out == []


# ─────────────────────── build_cycle_workpapers 正常组装 ───────────────────────

class _Row:
    def __init__(self, wp_code, wp_name, status, wp_id):
        self.wp_code = wp_code
        self.wp_name = wp_name
        self.status = status
        self.wp_id = wp_id


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_a, **_k):
        return _Result(self._rows)


@pytest.mark.asyncio
async def test_assemble_sorts_and_marks_current():
    cur = uuid.uuid4()
    other = uuid.uuid4()
    rows = [
        _Row("D2-10", "应收账款审定表10", "not_started", other),
        _Row("D1", "应收票据审定表", "not_started", cur),
        _Row("D2-1", "应收账款审定表1", "in_progress", other),
        _Row("D0", "收入循环函证", "not_started", None),  # 未生成文件
    ]
    out = await build_cycle_workpapers(
        db=_FakeDB(rows), project_id=uuid.uuid4(), audit_cycle="D",
        current_wp_id=cur,
    )

    # 自然排序：D0 < D1 < D2-1 < D2-10
    assert [x["wp_code"] for x in out] == ["D0", "D1", "D2-1", "D2-10"]

    # is_current 仅当前底稿
    by_code = {x["wp_code"]: x for x in out}
    assert by_code["D1"]["is_current"] is True
    assert by_code["D2-1"]["is_current"] is False

    # 未生成文件 → wp_id None（前端置灰）
    assert by_code["D0"]["wp_id"] is None
    assert by_code["D1"]["wp_id"] == str(cur)
