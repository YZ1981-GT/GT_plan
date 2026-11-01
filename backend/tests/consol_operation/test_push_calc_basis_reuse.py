"""批 3：CalcBasis 单次复用 + push_targets 递归 CTE 的调用次数 / SQL 斜率守卫。

- push 每个 target 只 load_calc_basis 一次，并把同一份 basis 贯穿 worksheet/trial/report/notes 四步；
- push_targets 不论父链深度多少都只发一条 SQL，并正确处理环、软删父、非合并中间父与自下而上顺序。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401 - 注册全模型与 SQLite 方言补丁
from app.models.base import Base, ProjectStatus
from app.models.consol_operation_models import ConsolOperation
from app.models.consol_push_models import ConsolPushRun
from app.models.core import Project, User
from app.services import consol_push_service as push_service

YEAR = 2025

# 只建本测试涉及的表：全表 create_all 会连带并发会话引入的 PG-only 默认值表
# （user_display_preferences 的 '{}'::jsonb），在 SQLite 上无法建表。
_TABLES = [
    User.__table__,
    Project.__table__,
    ConsolOperation.__table__,
    ConsolPushRun.__table__,
]


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _project(
    *, name: str, code: str, scope: str = "consolidated",
    parent: uuid.UUID | None = None, deleted: bool = False,
) -> Project:
    return Project(
        id=uuid.uuid4(), name=f"【测试】{name}_2025", client_name=f"【测试】{name}",
        company_code=code, audit_year=YEAR, report_scope=scope,
        status=ProjectStatus.execution, parent_project_id=parent, is_deleted=deleted,
    )


# ─────────────────────────────── push_targets 深度 SQL 恒定 ───────────────────────────────


class _SqlCounter:
    """统计一次 async 事务里真正下发到数据库的语句条数。"""

    def __init__(self, engine):
        self.sync_engine = engine.sync_engine
        self.count = 0

    def _on_exec(self, *_args, **_kwargs):
        self.count += 1

    def __enter__(self):
        event.listen(self.sync_engine, "before_cursor_execute", self._on_exec)
        return self

    def __exit__(self, *_exc):
        event.remove(self.sync_engine, "before_cursor_execute", self._on_exec)


async def _chain(db: AsyncSession, depth: int) -> Project:
    """造一条 depth 层父链：根是数据项目，其余是合并项目；返回最底层项目。"""
    root = _project(name=f"顶层{depth}", code=f"T{depth}", scope="consolidated")
    db.add(root)
    parent = root
    for level in range(depth):
        node = _project(
            name=f"层{depth}_{level}", code=f"L{depth}_{level}",
            scope="consolidated", parent=parent.id,
        )
        db.add(node)
        parent = node
    await db.commit()
    return parent


@pytest.mark.asyncio
async def test_push_targets_single_query_regardless_of_depth(db: AsyncSession, engine):
    """深度 1 与深度 10 的 push_targets 发出的 SQL 条数相同（递归 CTE，不随深度线性增长）。"""
    shallow = await _chain(db, 1)
    with _SqlCounter(engine) as counter:
        targets_shallow = await push_service.push_targets(db, shallow.id)
    sql_shallow = counter.count

    deep = await _chain(db, 10)
    with _SqlCounter(engine) as counter:
        targets_deep = await push_service.push_targets(db, deep.id)
    sql_deep = counter.count

    assert sql_shallow == sql_deep == 1
    # self + 全部合并父（深度 N 的链：self 加 N 个合并父）
    assert len(targets_shallow) == 2
    assert len(targets_deep) == 11
    assert targets_deep[0] == deep.id  # self 永远在首位


@pytest.mark.asyncio
async def test_push_targets_stops_at_cycle_and_deleted_and_keeps_non_consol_parent(db: AsyncSession):
    """环、软删父终止上溯；非合并中间父不进 targets 但不截断更上层合并父。"""
    # 非合并中间父：leaf(合并) → mid(单体) → top(合并)
    top = _project(name="环顶", code="CY_T", scope="consolidated")
    db.add(top)
    await db.flush()
    mid = _project(name="环中", code="CY_M", scope="standalone", parent=top.id)
    db.add(mid)
    await db.flush()
    leaf = _project(name="环底", code="CY_L", scope="consolidated", parent=mid.id)
    db.add(leaf)
    await db.commit()

    targets = await push_service.push_targets(db, leaf.id)
    assert targets[0] == leaf.id
    # mid 是单体中间父：不进 targets，但 top（更上层合并父）仍纳入
    assert mid.id not in targets
    assert top.id in targets
    assert set(targets) == {leaf.id, top.id}

    # 软删父：上溯到软删项目即停
    gone = _project(name="已删父", code="DEL_P", scope="consolidated", deleted=True)
    db.add(gone)
    await db.flush()
    child = _project(name="孤儿", code="ORPH", scope="consolidated", parent=gone.id)
    db.add(child)
    await db.commit()
    child_targets = await push_service.push_targets(db, child.id)
    assert child_targets == [child.id]

    # 自引用环：parent 指向自己，只返回自己且不死循环
    loop = _project(name="自环", code="SELF")
    db.add(loop)
    await db.flush()
    loop.parent_project_id = loop.id
    await db.commit()
    loop_targets = await push_service.push_targets(db, loop.id)
    assert loop_targets == [loop.id]


# ─────────────────────────────── 每 target 只装载一次 CalcBasis ───────────────────────────────


@pytest.mark.asyncio
async def test_push_loads_calc_basis_once_per_target(db: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    """push 对每个 target 恰调用一次 load_calc_basis，并把同一份 basis 对象透传给 _push_one 四步。

    四步本身被替换为只记录收到的 basis 身份，避免跑真实重算；本测试只验证 basis 复用边界。
    """
    import app.services.consol_calc_basis as calc_mod
    import app.services.consol_context_service as ctx_mod
    import app.services.consol_tree_service as tree_mod
    import app.services.consol_version_vector as vector_mod

    # 两层合并链：leaf → top
    top = _project(name="口径顶", code="CB_T", scope="consolidated")
    db.add(top)
    await db.flush()
    leaf = _project(name="口径底", code="CB_L", scope="consolidated", parent=top.id)
    db.add(leaf)
    await db.commit()

    class _FakeTree:
        def __init__(self, pid: uuid.UUID):
            self.project_id = pid
            self.node_key = f"{pid}:consol"

    class _FakeContext:
        def __init__(self, pid: uuid.UUID):
            self.project_id = pid
            self.year = YEAR

    class _FakeBasis:
        def __init__(self, pid: uuid.UUID, tree):
            self.project_id = pid
            self.tree = tree
            self.year = YEAR

    load_calls: list[uuid.UUID] = []
    basis_by_project: dict[uuid.UUID, _FakeBasis] = {}

    async def fake_build_tree(_db, pid, *a, **k):
        return _FakeTree(pid)

    async def fake_build_context(_db, pid, _year, *a, **k):
        return _FakeContext(pid)

    async def fake_build_target_context(_db, _src, pid, _year, *a, **k):
        return _FakeContext(pid)

    def fake_validate_context(*_a, **_k):
        return None

    def fake_validate_basis(*_a, **_k):
        return None

    async def fake_load_calc_basis(_db, pid, _year, *, tree=None, **k):
        load_calls.append(pid)
        basis = _FakeBasis(pid, tree or _FakeTree(pid))
        basis_by_project[pid] = basis
        return basis

    class _FakeVector:
        def model_dump(self, **_kwargs):
            return {"tree_fingerprint": "a" * 64, "tb_digest": "b" * 64}

    async def fake_build_version_vector(*_args, **_kwargs):
        return _FakeVector()

    monkeypatch.setattr(tree_mod, "build_tree", fake_build_tree)
    monkeypatch.setattr(ctx_mod, "build_consol_context", fake_build_context)
    monkeypatch.setattr(ctx_mod, "build_target_consol_context", fake_build_target_context)
    monkeypatch.setattr(ctx_mod, "validate_context", fake_validate_context)
    monkeypatch.setattr(calc_mod, "load_calc_basis", fake_load_calc_basis)
    monkeypatch.setattr(calc_mod, "validate_calc_basis", fake_validate_basis)
    monkeypatch.setattr(vector_mod, "build_version_vector", fake_build_version_vector)

    seen_basis: list[tuple[uuid.UUID, int]] = []

    async def fake_push_one(
        _db, project_id, _year, steps, _warnings, *,
        context=None, tree=None, basis=None, user_id=None, **_run_kwargs,
    ):
        # 记录每个 target 的四步各拿到的 basis 对象 id（证明四步共用同一份）
        seen_basis.append((project_id, id(basis)))
        steps.append({
            "project_id": str(project_id), "project_name": "x", "step": push_service.STEP_REPORT,
            "step_label": "报表", "status": "succeeded", "detail": "",
        })
        # basis 必须是本 target 的那一份
        assert basis is basis_by_project[project_id]
        return True

    monkeypatch.setattr(push_service, "_push_one", fake_push_one)

    result = await push_service.push(db, leaf.id, YEAR, trigger=push_service.TRIGGER_MANUAL)

    assert result.status == "succeeded"
    # 两个 target（leaf、top）各装载一次，合计两次——不随四步放大
    assert load_calls == [leaf.id, top.id]
    # 每个 target 只把一份 basis 传进 _push_one（四步复用已由 _push_one 内部保证）
    assert len(seen_basis) == 2
    assert {pid for pid, _ in seen_basis} == {leaf.id, top.id}
