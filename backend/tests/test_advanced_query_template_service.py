"""单元测试：TemplateService 模板保存与分享（advanced-query-module Task 14.1）。

覆盖：
  - 名称校验（1–200 字符；空 / 空白 / 超 200 → TEMPLATE_INVALID，不建部分记录）
  - scope 归一只走 ``TemplateScopeAdapter``：private / team / project / public 入库原值，历史 global → public、
    personal → private
  - 非法 scope → TEMPLATE_INVALID（中文原因）
  - shared_project_ids 只有 project 档写入（去重、按 UUID 文本排序），其余档置空；非法 UUID / project 档为空 → 拒绝
  - service 只 flush 不 commit（调用方 commit）

advanced-query-linkage-closure 任务 24 改写的断言（design §10.1，逐条理由）：
  - 原「``'private'`` 不是合法输入、``'global'`` 原样入库」：这正是 AQ-16 的根因——路由先经 adapter 把 scope 归一成
    ``private``，本服务再按自己那份 ``VALID_INPUT_SCOPES`` 判非法 ⇒ 保存恒 500；``project`` 同样被判非法。改为 adapter
    口径：private / project 合法，历史 global 入库为 public（ADR-AQL-11：入库规范值 private / project / public）。
  - 原「private / team 也写入分享项目」：adapter 合同里只有 project 档有分享项目（team 的锚点在 ``config.project_id``），
    私有模板带分享项目自相矛盾 ⇒ 改为置空。
  - 原「分享项目去重保序」：adapter 去重后按 UUID 文本排序（等价集合不因提交顺序漂移）⇒ 改断言排序后的结果。
  - 原直接调用的 ``_normalize_scope`` / ``_normalize_shared_project_ids`` 已删除（scope 归一只有 adapter 一处），改经
    ``save_template`` 断言入库值。

_Requirements: 13.1, 13.2, 13.3_
"""

from __future__ import annotations

import uuid

import pytest

from app.services.custom_query.template_service import (
    TemplateInvalidError,
    TemplateService,
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


async def _save(scope, shared=None, *, config=None):
    db = _FakeSession()
    tpl = await TemplateService().save_template(
        db=db, creator_id=uuid.uuid4(), name="测试模板", scope=scope, shared_project_ids=shared, config=config,
    )
    return tpl, db


# ─── 名称校验 ────────────────────────────────────────────────────────────────


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


# ─── scope 归一（adapter 口径）────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("given", "stored"),
    [("personal", "private"), ("PERSONAL", "private"), ("private", "private"), ("global", "public"),
     ("public", "public"), ("team", "team")],
)
async def test_scope_is_normalized_by_the_adapter(given, stored):
    tpl, _db = await _save(given)
    assert tpl.scope == stored


@pytest.mark.asyncio
async def test_project_scope_is_accepted_with_shared_projects():
    p1 = uuid.uuid4()
    tpl, _db = await _save(" Project ", [str(p1)])
    assert (tpl.scope, tpl.shared_project_ids) == ("project", [p1])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bad", "reason"),
    [("unknown", "不支持的模板范围：unknown"), ("", "不支持的模板范围："), (None, "scope 必须是字符串"),
     (42, "scope 必须是字符串")],
)
async def test_invalid_scope_is_rejected_with_a_chinese_reason(bad, reason):
    with pytest.raises(TemplateInvalidError) as exc:
        await _save(bad)
    assert exc.value.error_code == "TEMPLATE_INVALID"
    assert exc.value.message == reason


# ─── 分享项目 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["private", "personal", "team", "public", "global"])
async def test_only_project_scope_keeps_shared_project_ids(scope):
    tpl, _db = await _save(scope, [str(uuid.uuid4())])
    assert tpl.shared_project_ids == []


@pytest.mark.asyncio
async def test_project_shared_ids_are_deduplicated_and_sorted():
    p1, p2 = sorted((uuid.uuid4(), uuid.uuid4()), key=str)
    tpl, _db = await _save("project", [str(p2), p1, str(p2)])
    assert tpl.shared_project_ids == [p1, p2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("shared", "reason"),
    [(["not-a-uuid"], "共享项目标识非法：not-a-uuid"), (None, "指定项目共享至少需要一个项目"),
     ([], "指定项目共享至少需要一个项目")],
)
async def test_project_scope_rejects_bad_or_missing_projects(shared, reason):
    with pytest.raises(TemplateInvalidError) as exc:
        await _save("project", shared)
    assert exc.value.message == reason


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
