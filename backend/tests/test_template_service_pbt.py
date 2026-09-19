"""属性测试（Hypothesis）：TemplateService 模板保存/可见性/失效引用降级。

advanced-query-module Tasks 14.3 / 14.4 / 14.5 — 逐条映射设计属性 P25 / P26 / P27。

- **Property 25: 模板保存校验**（Validates: Requirements 13.2）
    非法名称（空 / 超 200）或非法 scope → 描述性错误 `TEMPLATE_INVALID`，
    且不创建部分模板记录（无 db.add / 无 flush）。
- **Property 26: 模板可见性规则**（Validates: Requirements 13.3, 13.4）
    随机 scope + 分享集合 + 可访问集合，断言可见可执行当且仅当规则成立，
    否则 `assert_executable` 抛 `TEMPLATE_FORBIDDEN`(403)。
- **Property 27: 模板失效引用部分降级**（Validates: Requirements 13.7）
    含 k 个失效 addr_id，断言跳过失效引用、标注并保留 addr_id、返回其余有效结果
    （非整体失败）。

铁律：每条属性一个测试，`@settings(max_examples=5)`（fast profile 收敛 example 数），
用 fakes/stubs（session / guard / addressing / executor）不触真实 DB。
"""

from __future__ import annotations

import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.custom_query.addressing_service import ResolvedTarget
from app.services.custom_query.template_service import (
    StaleRef,
    TemplateExecutionResult,
    TemplateForbiddenError,
    TemplateInvalidError,
    TemplateService,
    _is_template_visible,
)

# 固定项目 id 池 —— 让分享集合 / 可访问集合可控地相交（避免随机 UUID 永不相交）。
_PROJECT_POOL: list[uuid.UUID] = [uuid.uuid4() for _ in range(5)]
_CANONICAL_SCOPES = ("private", "team", "public", "global")


# ─── 测试替身（镜像 test_advanced_query_template_*.py 风格）──────────────────


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

    async def commit(self) -> None:
        self.commit_calls += 1


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
    ) -> None:
        self.id = uuid.uuid4()
        self.scope = scope
        self._owner_id = owner_id
        self.shared_project_ids = shared_project_ids or []
        self.config = config or {}

    @property
    def owner_id(self):
        return self._owner_id


class _FakeGuard:
    """OwnershipGuard 替身：accessible=None → admin/partner 全访问。"""

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
    """按预设 raw→found 映射解析目标（非 all-or-nothing 出口）。"""

    def __init__(self, resolve_map: dict[str, bool]) -> None:
        self._map = resolve_map

    async def resolve_many(self, raws, *, project_id=None, db=None, timeout_s=5.0):
        out = []
        for raw in raws:
            if self._map.get(raw, False):
                out.append(
                    ResolvedTarget(raw=raw, found=True, addr_id=raw, entry_type="cell")
                )
            else:
                out.append(ResolvedTarget(raw=raw, found=False, error="unresolvable"))
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


def _expected_visible(
    *, scope, owner_id, shared, user_id, accessible: set | None
) -> bool:
    """P26 参考实现（oracle）：模板可见性规则的独立朴素判定。"""
    if owner_id is not None and user_id is not None and owner_id == user_id:
        return True
    if scope in ("global", "public"):
        return True
    if scope == "team":
        if accessible is None:  # admin / partner
            return True
        return bool(set(shared) & accessible)
    # private（非所有者）或未知 scope
    return False


# ─── Property 25: 模板保存校验 ───────────────────────────────────────────────
# Feature: advanced-query-module, Property 25: 模板保存校验
# Validates: Requirements 13.2


# 非法名称：空串 / 纯空白 / 超 200 字符。
_illegal_names = st.one_of(
    st.just(""),
    st.text(alphabet=" \t\n", min_size=1, max_size=8),
    st.text(min_size=201, max_size=260),
)
# 非法 scope：不属于 {global, personal, team, public}（含 canonical 'private' 别名之外的值）。
_illegal_scopes = st.one_of(
    st.just("private"),  # 'private' 非合法输入（合法输入用别名 'personal'）
    st.text(min_size=1, max_size=12).filter(
        lambda s: s.strip().lower() not in {"global", "personal", "team", "public"}
    ),
    st.just(""),
)


@settings(max_examples=5)
@given(
    illegal_name=_illegal_names,
    valid_scope=st.sampled_from(["global", "personal", "team", "public"]),
)
@pytest.mark.asyncio
async def test_p25_illegal_name_rejected_no_partial_record(illegal_name, valid_scope):
    """非法名称 → TEMPLATE_INVALID，且不建部分记录。"""
    db = _FakeSession()
    svc = TemplateService()
    with pytest.raises(TemplateInvalidError) as exc:
        await svc.save_template(
            db=db,
            creator_id=uuid.uuid4(),
            name=illegal_name,
            scope=valid_scope,
        )
    assert exc.value.error_code == "TEMPLATE_INVALID"
    assert str(exc.value)  # 描述性错误非空
    # 不建部分记录
    assert db.added == []
    assert db.flush_calls == 0
    assert db.commit_calls == 0


@settings(max_examples=5)
@given(illegal_scope=_illegal_scopes)
@pytest.mark.asyncio
async def test_p25_illegal_scope_rejected_no_partial_record(illegal_scope):
    """非法 scope → TEMPLATE_INVALID，且不建部分记录。"""
    db = _FakeSession()
    svc = TemplateService()
    with pytest.raises(TemplateInvalidError) as exc:
        await svc.save_template(
            db=db,
            creator_id=uuid.uuid4(),
            name="合法名称",
            scope=illegal_scope,
        )
    assert exc.value.error_code == "TEMPLATE_INVALID"
    assert str(exc.value)
    assert db.added == []
    assert db.flush_calls == 0
    assert db.commit_calls == 0


# ─── Property 26: 模板可见性规则 ─────────────────────────────────────────────
# Feature: advanced-query-module, Property 26: 模板可见性规则
# Validates: Requirements 13.3, 13.4


_pool_indices = st.lists(
    st.integers(min_value=0, max_value=len(_PROJECT_POOL) - 1),
    min_size=0,
    max_size=len(_PROJECT_POOL),
    unique=True,
)


@settings(max_examples=5)
@given(
    scope=st.sampled_from(_CANONICAL_SCOPES),
    shared_idx=_pool_indices,
    accessible_idx=st.one_of(st.none(), _pool_indices),
    owner_is_user=st.booleans(),
)
@pytest.mark.asyncio
async def test_p26_visibility_matches_rule(
    scope, shared_idx, accessible_idx, owner_is_user
):
    """随机 scope + 分享 + 可访问集合：可见 ⇔ 规则成立，否则 403。"""
    owner_id = uuid.uuid4()
    user_id = owner_id if owner_is_user else uuid.uuid4()
    shared = [_PROJECT_POOL[i] for i in shared_idx]
    accessible = (
        None if accessible_idx is None else {_PROJECT_POOL[i] for i in accessible_idx}
    )

    expected = _expected_visible(
        scope=scope,
        owner_id=owner_id,
        shared=shared,
        user_id=user_id,
        accessible=accessible,
    )

    # 纯函数判定与 oracle 一致
    actual = _is_template_visible(
        scope=scope,
        owner_id=owner_id,
        shared_project_ids=shared,
        user_id=user_id,
        accessible_project_ids=accessible,
    )
    assert actual == expected

    # 端到端：is_visible / assert_executable 与规则一致
    svc = TemplateService()
    tpl = _FakeTemplate(scope=scope, owner_id=owner_id, shared_project_ids=shared)
    guard = _FakeGuard(accessible=accessible)
    user = _FakeUser(user_id)

    assert await svc.is_visible(tpl, user=user, db=None, guard=guard) == expected

    if expected:
        # 可见 → 不抛异常
        await svc.assert_executable(tpl, user=user, db=None, guard=guard)
    else:
        # 不可见 → TEMPLATE_FORBIDDEN 403
        with pytest.raises(TemplateForbiddenError) as exc:
            await svc.assert_executable(tpl, user=user, db=None, guard=guard)
        assert exc.value.error_code == "TEMPLATE_FORBIDDEN"


# ─── Property 27: 模板失效引用部分降级 ──────────────────────────────────────
# Feature: advanced-query-module, Property 27: 模板失效引用部分降级
# Validates: Requirements 13.7


@settings(max_examples=5)
@given(
    n_valid=st.integers(min_value=0, max_value=6),
    n_stale=st.integers(min_value=1, max_value=6),
)
@pytest.mark.asyncio
async def test_p27_stale_refs_degrade_partially(n_valid, n_stale):
    """含 k 个失效 addr_id：跳过失效、保留 addr_id、返回其余有效结果（非整体失败）。"""
    valid_targets = [f"WP{i}/S1/c{i}" for i in range(n_valid)]
    stale_targets = [f"GONE{j}/S9/c{j}" for j in range(n_stale)]
    all_targets = valid_targets + stale_targets

    resolve_map = {t: True for t in valid_targets}
    resolve_map.update({t: False for t in stale_targets})

    # 所有者本人执行 → 可见（隔离可见性，聚焦降级行为）；guard 全访问。
    owner = uuid.uuid4()
    tpl = _FakeTemplate(
        scope="private",
        owner_id=owner,
        config={"targets": all_targets, "entry": "business"},
    )
    svc = TemplateService()
    capture: dict = {}
    exec_rows = [{"x": 1}, {"x": 2}]
    executor = _make_executor(_FakeResult(rows=exec_rows, columns=[{"key": "x"}]), capture)

    res = await svc.execute_template(
        tpl,
        user=_FakeUser(owner),
        project_id=uuid.uuid4(),
        db=None,
        executor=executor,
        guard=_FakeGuard(accessible=None),
        addressing=_FakeAddressing(resolve_map),
    )

    assert isinstance(res, TemplateExecutionResult)

    # 非整体失败：仍返回有效结果集
    assert res.rows == exec_rows
    assert res.total == len(exec_rows)

    # 失效引用被完整标注并保留 addr_id
    assert len(res.stale_refs) == n_stale
    for sref in res.stale_refs:
        assert isinstance(sref, StaleRef)
        assert sref.error == "unresolvable"
    assert {s.addr_id for s in res.stale_refs} == set(stale_targets)

    # 仅有效目标进入执行；失效目标被剔除
    assert capture["req"].targets == valid_targets
