"""单元测试：TemplateService 可见性 + 执行 + 失效引用降级（advanced-query-module Task 14.2）。

覆盖：
  - 可见性纯函数 ``_is_template_visible``（所有者恒可见 / global|public 全员 /
    team 交集 / private 非所有者拒绝 / admin(None) 语义）。
  - ``is_visible`` / ``assert_executable``（无权 → TemplateForbiddenError 403）。
  - ``execute_template``：
      * 无访问权 → TemplateForbiddenError（不触达执行）。
      * 失效引用降级（R13.7）：跳过失效引用、保留 addr_id、返回其余有效结果，非整体失败。
      * 全部目标有效 → 无 stale_refs。
      * 跨项目聚合行套 Ownership_Check（filter_accessible_rows）仅返回有权行（R13.5）。
      * 单项目结果（行不含 project_id）不被误删。

_Requirements: 13.4, 13.5, 13.6, 13.7_
"""

from __future__ import annotations

import uuid

import pytest

from app.services.custom_query.addressing_service import ResolvedTarget
from app.services.custom_query.template_service import (
    StaleRef,
    TemplateExecutionResult,
    TemplateForbiddenError,
    TemplateService,
    _is_template_visible,
)


# ─── 测试替身 ────────────────────────────────────────────────────────────────


class _FakeUser:
    def __init__(self, uid: uuid.UUID) -> None:
        self.id = uid


class _FakeTemplate:
    """最小 CustomQueryTemplate 替身。"""

    def __init__(
        self,
        *,
        scope: str,
        owner_id: uuid.UUID | None = None,
        shared_project_ids: list | None = None,
        config: dict | None = None,
        tid: uuid.UUID | None = None,
    ) -> None:
        self.id = tid or uuid.uuid4()
        self.scope = scope
        self._owner_id = owner_id
        self.shared_project_ids = shared_project_ids or []
        self.config = config or {}

    @property
    def owner_id(self):
        return self._owner_id


class _FakeGuard:
    """可注入的 OwnershipGuard 替身。

    accessible=None → admin/partner 全访问；否则集合。filter_accessible_rows
    仅保留 project_id ∈ accessible 的行（None → 全保留）。
    """

    def __init__(self, accessible: set[uuid.UUID] | None) -> None:
        self._accessible = accessible

    async def get_accessible_project_ids(self, user, db):
        return self._accessible

    async def filter_accessible_rows(self, rows, *, user, db):
        if self._accessible is None:
            return list(rows)
        kept = []
        for r in rows:
            pid = r.get("project_id") if isinstance(r, dict) else None
            try:
                pid_u = uuid.UUID(str(pid)) if pid is not None else None
            except (ValueError, TypeError):
                pid_u = None
            if pid_u is not None and pid_u in self._accessible:
                kept.append(r)
        return kept


class _FakeAddressing:
    """按预设 raw→found 映射解析目标。"""

    def __init__(self, resolve_map: dict[str, bool]) -> None:
        self._map = resolve_map

    async def resolve_many(self, raws, *, project_id=None, db=None, timeout_s=5.0):
        out = []
        for raw in raws:
            found = self._map.get(raw, False)
            if found:
                out.append(
                    ResolvedTarget(
                        raw=raw, found=True, addr_id=raw, entry_type="cell"
                    )
                )
            else:
                out.append(
                    ResolvedTarget(raw=raw, found=False, error="unresolvable")
                )
        return out


class _FakeResult:
    def __init__(self, rows, columns=None, warnings=None, cache_hit=False) -> None:
        self.rows = rows
        self.columns = columns or []
        self.warnings = warnings or []
        self.cache_hit = cache_hit


def _make_executor(result, capture: dict):
    async def _run(req, *, user, db):
        capture["req"] = req
        return result

    return _run


# ─── 可见性纯函数 ────────────────────────────────────────────────────────────


def test_owner_always_visible():
    owner = uuid.uuid4()
    for scope in ("private", "team", "public", "global"):
        assert _is_template_visible(
            scope=scope,
            owner_id=owner,
            shared_project_ids=[],
            user_id=owner,
            accessible_project_ids=set(),
        )


def test_global_and_public_visible_to_all():
    for scope in ("global", "public"):
        assert _is_template_visible(
            scope=scope,
            owner_id=uuid.uuid4(),
            shared_project_ids=[],
            user_id=uuid.uuid4(),
            accessible_project_ids=set(),
        )


def test_private_non_owner_not_visible():
    assert not _is_template_visible(
        scope="private",
        owner_id=uuid.uuid4(),
        shared_project_ids=[],
        user_id=uuid.uuid4(),
        accessible_project_ids={uuid.uuid4()},
    )


def test_private_non_owner_not_visible_even_for_admin():
    # accessible=None (admin/partner) 不改变他人私有模板隐私
    assert not _is_template_visible(
        scope="private",
        owner_id=uuid.uuid4(),
        shared_project_ids=[],
        user_id=uuid.uuid4(),
        accessible_project_ids=None,
    )


def test_team_visible_when_shared_intersects_accessible():
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    assert _is_template_visible(
        scope="team",
        owner_id=uuid.uuid4(),
        shared_project_ids=[p1],
        user_id=uuid.uuid4(),
        accessible_project_ids={p1, p2},
    )


def test_team_not_visible_without_intersection():
    assert not _is_template_visible(
        scope="team",
        owner_id=uuid.uuid4(),
        shared_project_ids=[uuid.uuid4()],
        user_id=uuid.uuid4(),
        accessible_project_ids={uuid.uuid4()},
    )


def test_team_visible_for_admin_all_access():
    assert _is_template_visible(
        scope="team",
        owner_id=uuid.uuid4(),
        shared_project_ids=[uuid.uuid4()],
        user_id=uuid.uuid4(),
        accessible_project_ids=None,
    )


# ─── is_visible / assert_executable ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_is_visible_uses_guard_accessible_ids():
    p1 = uuid.uuid4()
    tpl = _FakeTemplate(scope="team", owner_id=uuid.uuid4(), shared_project_ids=[p1])
    svc = TemplateService()
    guard = _FakeGuard(accessible={p1})
    assert await svc.is_visible(tpl, user=_FakeUser(uuid.uuid4()), db=None, guard=guard)


@pytest.mark.asyncio
async def test_assert_executable_raises_forbidden_when_not_visible():
    tpl = _FakeTemplate(scope="private", owner_id=uuid.uuid4())
    svc = TemplateService()
    guard = _FakeGuard(accessible=set())
    with pytest.raises(TemplateForbiddenError) as exc:
        await svc.assert_executable(tpl, user=_FakeUser(uuid.uuid4()), db=None, guard=guard)
    assert exc.value.error_code == "TEMPLATE_FORBIDDEN"


# ─── execute_template ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_forbidden_does_not_run_query():
    tpl = _FakeTemplate(scope="private", owner_id=uuid.uuid4(), config={"targets": ["A1/S1/c1"]})
    svc = TemplateService()
    guard = _FakeGuard(accessible=set())
    capture: dict = {}
    executor = _make_executor(_FakeResult(rows=[]), capture)

    with pytest.raises(TemplateForbiddenError):
        await svc.execute_template(
            tpl,
            user=_FakeUser(uuid.uuid4()),
            project_id=uuid.uuid4(),
            db=None,
            executor=executor,
            guard=guard,
            addressing=_FakeAddressing({}),
        )
    # 未执行查询
    assert "req" not in capture


@pytest.mark.asyncio
async def test_execute_stale_ref_degradation_returns_valid_results():
    owner = uuid.uuid4()
    valid = "A1/S1/c1"
    stale = "GONE/S9/c9"
    tpl = _FakeTemplate(
        scope="private",
        owner_id=owner,
        config={"targets": [valid, stale], "entry": "business"},
    )
    svc = TemplateService()
    guard = _FakeGuard(accessible=None)
    capture: dict = {}
    executor = _make_executor(
        _FakeResult(rows=[{"x": 1}], columns=[{"key": "x"}]), capture
    )

    res = await svc.execute_template(
        tpl,
        user=_FakeUser(owner),
        project_id=uuid.uuid4(),
        db=None,
        executor=executor,
        guard=guard,
        addressing=_FakeAddressing({valid: True, stale: False}),
    )

    assert isinstance(res, TemplateExecutionResult)
    # 非整体失败：仍返回有效结果
    assert res.rows == [{"x": 1}]
    # 失效引用被标注、保留 addr_id
    assert len(res.stale_refs) == 1
    assert isinstance(res.stale_refs[0], StaleRef)
    assert res.stale_refs[0].addr_id == stale
    assert res.stale_refs[0].error == "unresolvable"
    # 仅有效目标进入执行
    assert capture["req"].targets == [valid]


@pytest.mark.asyncio
async def test_execute_all_valid_no_stale_refs():
    owner = uuid.uuid4()
    t1, t2 = "A1/S1/c1", "A1/S1/c2"
    tpl = _FakeTemplate(scope="global", config={"targets": [t1, t2]})
    svc = TemplateService()
    capture: dict = {}
    executor = _make_executor(_FakeResult(rows=[{"a": 1}]), capture)

    res = await svc.execute_template(
        tpl,
        user=_FakeUser(uuid.uuid4()),
        project_id=uuid.uuid4(),
        db=None,
        executor=executor,
        guard=_FakeGuard(accessible=None),
        addressing=_FakeAddressing({t1: True, t2: True}),
    )
    assert res.stale_refs == []
    assert sorted(capture["req"].targets) == sorted([t1, t2])


@pytest.mark.asyncio
async def test_execute_cross_project_rows_filtered_by_ownership():
    owner = uuid.uuid4()
    accessible_pid = uuid.uuid4()
    other_pid = uuid.uuid4()
    tpl = _FakeTemplate(scope="global", config={"targets": []})
    svc = TemplateService()
    rows = [
        {"project_id": str(accessible_pid), "v": 1},
        {"project_id": str(other_pid), "v": 2},
    ]
    executor = _make_executor(_FakeResult(rows=rows), {})

    res = await svc.execute_template(
        tpl,
        user=_FakeUser(uuid.uuid4()),
        project_id=accessible_pid,
        db=None,
        executor=executor,
        guard=_FakeGuard(accessible={accessible_pid}),
        addressing=_FakeAddressing({}),
    )
    # 仅保留有权访问项目行（R13.5）
    assert res.rows == [{"project_id": str(accessible_pid), "v": 1}]
    assert res.total == 1


@pytest.mark.asyncio
async def test_execute_single_project_rows_not_dropped():
    # 行不含 project_id（单项目结果）→ 不施加跨项目过滤，不误删
    tpl = _FakeTemplate(scope="global", config={"targets": []})
    svc = TemplateService()
    rows = [{"v": 1}, {"v": 2}]
    executor = _make_executor(_FakeResult(rows=rows), {})

    res = await svc.execute_template(
        tpl,
        user=_FakeUser(uuid.uuid4()),
        project_id=uuid.uuid4(),
        db=None,
        executor=executor,
        guard=_FakeGuard(accessible={uuid.uuid4()}),
        addressing=_FakeAddressing({}),
    )
    assert res.rows == rows
    assert res.total == 2
