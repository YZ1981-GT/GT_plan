"""单元测试：TemplateService 模板保存与分享（advanced-query-module Task 14.1）。

覆盖：
  - 名称校验（1–200 字符；空 / 空白 / 超 200 → TEMPLATE_INVALID，不建部分记录）
  - scope 校验与 personal → private 别名归一
  - 非法 scope → TEMPLATE_INVALID
  - shared_project_ids 校验（私有/团队写入；global/public 置空；非法 UUID 拒绝）
  - service 只 flush 不 commit（调用方 commit）

_Requirements: 13.1, 13.2, 13.3_
"""

from __future__ import annotations

import uuid

import pytest

from app.services.custom_query.template_service import (
    TemplateInvalidError,
    TemplateService,
    _normalize_scope,
    _normalize_shared_project_ids,
    _validate_name,
)


class _FakeSession:
    """最小 AsyncSession 替身：记录 add / flush / commit 调用。"""

    def __init__(self) -> None:
        self.added: list = []
        self.flush_calls = 0
        self.commit_calls = 0

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flush_calls += 1

    async def commit(self) -> None:  # 不应被 service 调用
        self.commit_calls += 1


# ─── 纯函数校验 ──────────────────────────────────────────────────────────────


def test_validate_name_accepts_valid():
    assert _validate_name("我的查询") == "我的查询"
    assert _validate_name("x") == "x"
    assert _validate_name("a" * 200) == "a" * 200
    # 首尾空白被裁剪
    assert _validate_name("  trimmed  ") == "trimmed"


@pytest.mark.parametrize("bad", ["", "   ", "a" * 201, None, 123])
def test_validate_name_rejects_invalid(bad):
    with pytest.raises(TemplateInvalidError) as exc:
        _validate_name(bad)
    assert exc.value.error_code == "TEMPLATE_INVALID"


def test_normalize_scope_alias_personal_to_private():
    assert _normalize_scope("personal") == "private"
    assert _normalize_scope("PERSONAL") == "private"
    assert _normalize_scope("global") == "global"
    assert _normalize_scope("team") == "team"
    assert _normalize_scope("public") == "public"


@pytest.mark.parametrize("bad", ["private", "unknown", "", None, 42])
def test_normalize_scope_rejects_invalid(bad):
    # 注意：'private' 不是合法输入（合法输入用别名 'personal'）
    with pytest.raises(TemplateInvalidError):
        _normalize_scope(bad)


def test_shared_ids_empty_for_all_visible_scopes():
    pid = str(uuid.uuid4())
    assert _normalize_shared_project_ids("global", [pid]) == []
    assert _normalize_shared_project_ids("public", [pid]) == []


def test_shared_ids_written_for_private_and_team():
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    out = _normalize_shared_project_ids("private", [str(p1), str(p2)])
    assert out == [p1, p2]
    out_team = _normalize_shared_project_ids("team", [p1])
    assert out_team == [p1]


def test_shared_ids_dedup_preserves_order():
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    out = _normalize_shared_project_ids("private", [p1, p2, p1])
    assert out == [p1, p2]


def test_shared_ids_rejects_invalid_uuid():
    with pytest.raises(TemplateInvalidError):
        _normalize_shared_project_ids("private", ["not-a-uuid"])


# ─── save_template 集成（Fake session）───────────────────────────────────────


@pytest.mark.asyncio
async def test_save_template_persists_and_only_flushes():
    db = _FakeSession()
    svc = TemplateService()
    creator = uuid.uuid4()

    tpl = await svc.save_template(
        db=db,
        creator_id=creator,
        name="测试模板",
        scope="personal",
        config={"targets": ["A1/S1/c1"]},
    )

    assert tpl.name == "测试模板"
    assert tpl.scope == "private"  # personal → private 归一
    assert tpl.created_by == creator
    assert tpl.creator_id == creator
    assert tpl.config == {"targets": ["A1/S1/c1"]}
    # 只 flush 不 commit（平台铁律）
    assert db.flush_calls == 1
    assert db.commit_calls == 0
    assert db.added == [tpl]


@pytest.mark.asyncio
async def test_save_template_writes_shared_project_ids():
    db = _FakeSession()
    svc = TemplateService()
    p1 = uuid.uuid4()

    tpl = await svc.save_template(
        db=db,
        creator_id=uuid.uuid4(),
        name="分享模板",
        scope="team",
        shared_project_ids=[str(p1)],
    )
    assert tpl.shared_project_ids == [p1]


@pytest.mark.asyncio
async def test_save_template_global_ignores_shared_ids():
    db = _FakeSession()
    svc = TemplateService()

    tpl = await svc.save_template(
        db=db,
        creator_id=uuid.uuid4(),
        name="全局模板",
        scope="global",
        shared_project_ids=[str(uuid.uuid4())],
    )
    assert tpl.scope == "global"
    assert tpl.shared_project_ids == []


@pytest.mark.asyncio
async def test_save_template_invalid_name_no_partial_record():
    db = _FakeSession()
    svc = TemplateService()

    with pytest.raises(TemplateInvalidError):
        await svc.save_template(
            db=db,
            creator_id=uuid.uuid4(),
            name="   ",
            scope="personal",
        )
    # 不建部分记录：无 add / 无 flush
    assert db.added == []
    assert db.flush_calls == 0


@pytest.mark.asyncio
async def test_save_template_invalid_scope_no_partial_record():
    db = _FakeSession()
    svc = TemplateService()

    with pytest.raises(TemplateInvalidError):
        await svc.save_template(
            db=db,
            creator_id=uuid.uuid4(),
            name="有效名称",
            scope="不存在的scope",
        )
    assert db.added == []
    assert db.flush_calls == 0
