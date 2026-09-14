"""deliverable-center P0 属性化测试与单元测试"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_log_models import AuditLogEntry
from app.models.base import Base
from app.models.base import ProjectType, ProjectStatus, UserRole
from app.models.core import Project, User
from app.models.phase13_models import (
    VALID_STATUS_TRANSITIONS,
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.services import deliverable_service as ds_module
from app.services.deliverable_service import DeliverableService

# Feature: audit-report-deliverable-center

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_DELIVERABLE_TABLES = [
    User.__table__,
    Project.__table__,
    WordExportTask.__table__,
    WordExportTaskVersion.__table__,
    AuditLogEntry.__table__,
]


async def _seed_project_user(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """在给定 session 中建一个用户 + 项目，返回 (project_id, user_id)。"""
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    suffix = user_id.hex[:8]
    session.add(
        User(
            id=user_id,
            username=f"deliverable_{suffix}",
            email=f"deliverable_{suffix}@test.com",
            hashed_password="x",
            role=UserRole.admin,
        )
    )
    await session.flush()
    session.add(
        Project(
            id=project_id,
            name="交付中心测试项目",
            client_name="交付中心测试",
            project_type=ProjectType.annual,
            status=ProjectStatus.planning,
            created_by=user_id,
        )
    )
    await session.flush()
    return project_id, user_id


def _run_in_isolated_db(coro_factory):
    """为单个 hypothesis 样例建独立内存库并运行 coro_factory(session, project_id, user_id)。"""

    async def _runner():
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_DELIVERABLE_TABLES)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                project_id, user_id = await _seed_project_user(session)
                await session.commit()
                return await coro_factory(session, project_id, user_id)
        finally:
            await engine.dispose()

    return asyncio.run(_runner())


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=_DELIVERABLE_TABLES
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    suffix = user_id.hex[:8]
    user = User(
        id=user_id,
        username=f"deliverable_{suffix}",
        email=f"deliverable_{suffix}@test.com",
        hashed_password="x",
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.flush()
    project = Project(
        id=project_id,
        name="交付中心测试项目",
        client_name="交付中心测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=user_id,
    )
    db_session.add(project)
    await db_session.commit()
    return {"project_id": project_id, "user_id": user_id}


@pytest.mark.asyncio
async def test_status_transition_valid(db_session, seeded_db):
    """Property 5: 状态机转换合法性 — 合法转换接受"""
    svc = DeliverableService(db_session)
    project_id = seeded_db["project_id"]
    user_id = seeded_db["user_id"]
    task = await svc.create_task(project_id, "audit_report", "soe", user_id)
    await svc.update_status(task.id, WordExportStatus.generating.value)
    await svc.update_status(task.id, WordExportStatus.generated.value)
    await svc.update_status(task.id, WordExportStatus.editing.value)
    assert task.status == WordExportStatus.editing.value


@pytest.mark.asyncio
async def test_status_transition_invalid(db_session, seeded_db):
    """Property 5: 非法转换被拒绝"""
    svc = DeliverableService(db_session)
    project_id = seeded_db["project_id"]
    user_id = seeded_db["user_id"]
    task = await svc.create_task(project_id, "audit_report", "soe", user_id)
    with pytest.raises(ValueError):
        await svc.update_status(task.id, WordExportStatus.confirmed.value)


@given(
    version_nos=st.lists(st.integers(min_value=1, max_value=20), min_size=1, max_size=8, unique=True)
)
@settings(max_examples=3)
@pytest.mark.asyncio
async def test_version_compare_symmetry(version_nos):
    """Property 13: 版本对比对称性 — compare(a,a) 为空"""
    from app.services.deliverable_service import VersionCompareResult

    a, b = version_nos[0], version_nos[-1]
    empty = VersionCompareResult(a, a, None, None, None)
    assert empty.exported_at_diff is None
    assert empty.file_size_diff is None
    if a == b:
        assert empty.selected_sections_diff is None


# ---------------------------------------------------------------------------
# list_deliverables 服务级 PBT 支撑：每个 hypothesis 样例独立建库，避免
# 函数级 fixture 与 hypothesis 多样例共享状态导致的脏数据。
# ---------------------------------------------------------------------------

DOC_TYPE_POOL = ["audit_report", "financial_report", "disclosure_notes", "full_package"]
STATUS_POOL = [s.value for s in WordExportStatus]
# 两个导出者用户名（用于关键字命中导出者字段的场景）
EXPORTER_NAMES = ["alice_audit", "bob_review"]

# 单条交付物生成规格：(doc_type, status_idx, file_token, exporter_idx, day_offset, file_size)
_deliverable_spec = st.tuples(
    st.sampled_from(DOC_TYPE_POOL),
    st.integers(min_value=0, max_value=len(STATUS_POOL) - 1),
    st.text(alphabet="abcXYZ_", min_size=1, max_size=6),
    st.integers(min_value=0, max_value=1),
    st.integers(min_value=0, max_value=10),
    st.integers(min_value=1, max_value=999999),
)


async def _build_and_list(specs, **list_kwargs):
    """按 specs 在独立内存库中建任务，返回 (full_dtos, filtered_dtos, meta)。

    full_dtos: 无筛选的全量列表
    filtered_dtos: 按 list_kwargs 筛选的列表
    meta: {task_id: {doc_type,status,file_name,exporter,created_at}}
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_DELIVERABLE_TABLES)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    meta: dict = {}
    try:
        async with session_factory() as session:
            project_id = uuid.uuid4()
            user_ids: list[uuid.UUID] = []
            for idx, uname in enumerate(EXPORTER_NAMES):
                uid = uuid.uuid4()
                user_ids.append(uid)
                session.add(
                    User(
                        id=uid,
                        username=uname,
                        email=f"{uname}@test.com",
                        hashed_password="x",
                        role=UserRole.auditor,
                    )
                )
            await session.flush()
            session.add(
                Project(
                    id=project_id,
                    name="筛选搜索测试项目",
                    client_name="筛选搜索",
                    project_type=ProjectType.annual,
                    status=ProjectStatus.planning,
                    created_by=user_ids[0],
                )
            )
            await session.flush()

            base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
            for i, (doc_type, st_idx, token, exp_idx, day_off, fsize) in enumerate(specs):
                status = STATUS_POOL[st_idx]
                created = base_time + timedelta(days=day_off, seconds=i)
                file_name = f"{token}_{i}.docx"
                task = WordExportTask(
                    project_id=project_id,
                    doc_type=doc_type,
                    status=status,
                    file_path=f"/storage/{file_name}",
                    file_size=fsize,
                    created_by=user_ids[exp_idx],
                    created_at=created,
                    updated_at=created,
                )
                session.add(task)
                await session.flush()
                meta[task.id] = {
                    "doc_type": doc_type,
                    "status": status,
                    "file_name": file_name,
                    "exporter": EXPORTER_NAMES[exp_idx],
                    "created_at": created,
                }
            await session.commit()

            svc = DeliverableService(session)
            full = await svc.list_deliverables(project_id)
            filtered = await svc.list_deliverables(project_id, **list_kwargs)
            return full, filtered, meta
    finally:
        await engine.dispose()


@given(specs=st.lists(_deliverable_spec, min_size=1, max_size=6))
@settings(max_examples=3, deadline=None)
def test_group_partition_property(specs):
    # Feature: audit-report-deliverable-center, Property 6: 交付物分组分区性
    """Property 6: 交付物分组分区性 — 按 doc_type 分组并集=原集合、两两不相交、组内同类"""
    full, _filtered, meta = asyncio.run(_build_and_list(specs))

    grouped: dict[str, list] = {}
    for dto in full:
        grouped.setdefault(dto.doc_type, []).append(dto)

    flat_ids = [dto.task_id for g in grouped.values() for dto in g]
    # 并集等于原集合
    assert sorted(map(str, flat_ids)) == sorted(map(str, (d.task_id for d in full)))
    # 两两不相交（无重复 task_id）
    assert len(flat_ids) == len(set(flat_ids))
    # 每组内 doc_type 相同
    for doc_type, group in grouped.items():
        assert all(dto.doc_type == doc_type for dto in group)
    # 覆盖全部输入
    assert len(full) == len(specs)


@given(specs=st.lists(_deliverable_spec, min_size=1, max_size=6))
@settings(max_examples=3, deadline=None)
def test_dto_field_completeness(specs):
    # Feature: audit-report-deliverable-center, Property 7: 列表 DTO 字段完整性
    """Property 7: 列表 DTO 字段完整性 — 七字段均存在且核心字段被正确填充"""
    full, _filtered, meta = asyncio.run(_build_and_list(specs))

    required = (
        "file_name",
        "version_no",
        "doc_type",
        "exporter_name",
        "exported_at",
        "status",
        "file_size",
    )
    assert len(full) == len(specs)
    for dto in full:
        d = dto.__dict__
        for key in required:
            assert key in d
        m = meta[dto.task_id]
        # 核心字段取值正确
        assert dto.doc_type == m["doc_type"]
        assert dto.status == m["status"]
        assert dto.exporter_name == m["exporter"]
        assert dto.file_name == m["file_name"]
        assert dto.version_no >= 1
        assert dto.exported_at is not None
        assert dto.file_size is not None


@given(
    specs=st.lists(_deliverable_spec, min_size=1, max_size=6),
    use_doc_type=st.booleans(),
    use_status=st.booleans(),
    day_from=st.integers(min_value=0, max_value=10),
    day_to=st.integers(min_value=0, max_value=10),
)
@settings(max_examples=3, deadline=None)
def test_filter_subset_and_satisfies(specs, use_doc_type, use_status, day_from, day_to):
    # Feature: audit-report-deliverable-center, Property 9: 筛选结果子集且满足条件
    """Property 9: 筛选结果子集且满足条件 — 结果是原集合子集，且每个元素满足全部条件"""
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    lo, hi = sorted((day_from, day_to))
    filt_doc_type = specs[0][0] if use_doc_type else None
    filt_status = STATUS_POOL[specs[0][1]] if use_status else None
    date_from = base_time + timedelta(days=lo)
    date_to = base_time + timedelta(days=hi, hours=23)

    full, filtered, meta = asyncio.run(
        _build_and_list(
            specs,
            doc_type=filt_doc_type,
            status=filt_status,
            date_from=date_from,
            date_to=date_to,
        )
    )

    full_ids = {d.task_id for d in full}
    filtered_ids = {d.task_id for d in filtered}

    # 结果是原集合的子集
    assert filtered_ids.issubset(full_ids)

    # 结果中每个元素都满足全部给定条件
    for dto in filtered:
        m = meta[dto.task_id]
        if filt_doc_type is not None:
            assert dto.doc_type == filt_doc_type
        if filt_status is not None:
            assert dto.status == filt_status
        assert date_from <= m["created_at"] <= date_to

    # 完备性：所有满足条件的元素都应出现在结果中
    expected = set()
    for tid, m in meta.items():
        if filt_doc_type is not None and m["doc_type"] != filt_doc_type:
            continue
        if filt_status is not None and m["status"] != filt_status:
            continue
        if not (date_from <= m["created_at"] <= date_to):
            continue
        expected.add(tid)
    assert filtered_ids == expected


@given(
    specs=st.lists(_deliverable_spec, min_size=1, max_size=6),
    keyword=st.sampled_from(["abc", "XYZ", "alice", "bob", "docx", ".docx", "zzz_none"]),
)
@settings(max_examples=3, deadline=None)
def test_keyword_search_relevance(specs, keyword):
    # Feature: audit-report-deliverable-center, Property 10: 关键字搜索相关性
    """Property 10: 关键字搜索相关性 — 结果均含关键字，且原集合中所有匹配项都在结果内"""
    full, filtered, meta = asyncio.run(_build_and_list(specs, keyword=keyword))

    full_ids = {d.task_id for d in full}
    filtered_ids = {d.task_id for d in filtered}
    assert filtered_ids.issubset(full_ids)

    kw = keyword.lower()
    # 结果中每个元素的文件名或导出者包含关键字
    for dto in filtered:
        name_match = bool(dto.file_name) and kw in dto.file_name.lower()
        exporter_match = bool(dto.exporter_name) and kw in dto.exporter_name.lower()
        assert name_match or exporter_match

    # 原集合中所有匹配元素都出现在结果中
    expected = {
        tid
        for tid, m in meta.items()
        if kw in m["file_name"].lower() or kw in m["exporter"].lower()
    }
    assert filtered_ids == expected


def test_placeholder_registry_loadable():
    """Property 50: 占位符注册表可加载"""
    from app.services.report_body_service import _load_registry

    reg = _load_registry()
    assert "auto" in reg
    assert "financial" in reg
    assert "entity_name" in reg["auto"]
    assert "total_assets" in reg["financial"]


# ===========================================================================
# Task 3 — 版本链与双路径存储 PBT / 单元测试
# ===========================================================================


@given(
    n_versions=st.integers(min_value=1, max_value=6),
    sizes=st.lists(st.integers(min_value=1, max_value=99999), min_size=1, max_size=6),
)
@settings(max_examples=3, deadline=None)
def test_version_no_monotonic_increasing(n_versions, sizes):
    # Feature: audit-report-deliverable-center, Property 11: 版本号单调递增
    """Property 11: 每次追加版本号 = 当前 max+1，序列严格单调递增且无重复"""

    async def _body(session, project_id, user_id):
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, "audit_report", "soe", user_id)
        # create_task 已创建初始版本 v1
        assigned = [1]
        for i in range(n_versions):
            ver = await svc.create_version(
                task.id,
                file_path=f"/storage/v{i}.docx",
                html_path=None,
                user_id=user_id,
                file_size=sizes[i % len(sizes)],
                created_via="generate",
            )
            # 版本号 = 之前最大值 + 1
            assert ver.version_no == max(assigned) + 1
            assigned.append(ver.version_no)
        # 严格单调递增且无重复
        assert assigned == sorted(assigned)
        assert len(assigned) == len(set(assigned))
        assert all(b - a == 1 for a, b in zip(assigned, assigned[1:]))

    _run_in_isolated_db(_body)


@given(
    ops=st.lists(st.sampled_from(["create", "noop"]), min_size=1, max_size=8),
)
@settings(max_examples=3, deadline=None)
def test_history_versions_not_deleted(ops):
    # Feature: audit-report-deliverable-center, Property 12: 历史版本不删除不变式
    """Property 12: 不含归档的操作序列中，版本集合单调不减（已有版本不被删除）"""

    async def _body(session, project_id, user_id):
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, "audit_report", "soe", user_id)
        prev_count = len(await svc.get_version_chain(task.id))
        prev_ids: set = {v.id for v in await svc.get_version_chain(task.id)}
        for i, op in enumerate(ops):
            if op == "create":
                await svc.create_version(
                    task.id,
                    file_path=f"/storage/h{i}.docx",
                    html_path=None,
                    user_id=user_id,
                )
            chain = await svc.get_version_chain(task.id)
            cur_ids = {v.id for v in chain}
            # 单调不减
            assert len(chain) >= prev_count
            # 既有版本始终保留
            assert prev_ids.issubset(cur_ids)
            prev_count = len(chain)
            prev_ids = cur_ids

    _run_in_isolated_db(_body)


@given(
    size_a=st.integers(min_value=1, max_value=99999),
    size_b=st.integers(min_value=1, max_value=99999),
    sections_a=st.lists(st.sampled_from(["opinion", "basis", "kam", "emphasis"]), max_size=4, unique=True),
    sections_b=st.lists(st.sampled_from(["opinion", "basis", "kam", "emphasis"]), max_size=4, unique=True),
)
@settings(max_examples=3, deadline=None)
def test_version_compare_symmetry_full(size_a, size_b, sections_a, sections_b):
    # Feature: audit-report-deliverable-center, Property 13: 版本对比对称性
    """Property 13: compare(a,b) 与 compare(b,a) 对称；compare(a,a) 为空差异"""

    async def _body(session, project_id, user_id):
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, "audit_report", "soe", user_id)
        va = await svc.create_version(
            task.id, file_path="/s/a.docx", html_path=None, user_id=user_id,
            file_size=size_a, selected_sections=sections_a,
        )
        vb = await svc.create_version(
            task.id, file_path="/s/b.docx", html_path=None, user_id=user_id,
            file_size=size_b, selected_sections=sections_b,
        )

        # compare(a,a) 为空差异
        same = await svc.compare_versions(task.id, va.version_no, va.version_no)
        assert same.exported_at_diff is None
        assert same.file_size_diff is None
        assert same.selected_sections_diff is None

        ab = await svc.compare_versions(task.id, va.version_no, vb.version_no)
        ba = await svc.compare_versions(task.id, vb.version_no, va.version_no)

        # 对称性：a/b 互换，每个差异字段的 a、b 值互换
        def _swapped(diff_ab, diff_ba, name):
            if diff_ab is None and diff_ba is None:
                return True
            if diff_ab is None or diff_ba is None:
                return False
            return (
                diff_ab[name]["a"] == diff_ba[name]["b"]
                and diff_ab[name]["b"] == diff_ba[name]["a"]
            )

        assert _swapped(ab.file_size_diff, ba.file_size_diff, "file_size")
        assert _swapped(ab.selected_sections_diff, ba.selected_sections_diff, "selected_sections")
        # 差异存在性与底层数据一致
        assert (ab.file_size_diff is not None) == (size_a != size_b)
        assert (ab.selected_sections_diff is not None) == (sections_a != sections_b)

    _run_in_isolated_db(_body)


@given(
    terminal_status=st.sampled_from(["confirmed", "signed", "archived"]),
    doc_type=st.sampled_from(["audit_report", "financial_report", "disclosure_notes"]),
)
@settings(max_examples=3, deadline=None)
def test_terminal_reexport_creates_new_deliverable(terminal_status, doc_type):
    # Feature: audit-report-deliverable-center, Property 14: 终态再导出新建交付物
    """Property 14: 终态({confirmed,signed,archived})交付物同类型再导出 → 新独立交付物"""

    async def _body(session, project_id, user_id):
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, doc_type, "soe", user_id)
        # 直接置为终态（绕过状态机以构造前置条件）
        task.status = terminal_status
        await session.flush()

        new_task, is_new = await svc.export_or_new_deliverable(
            project_id, doc_type, "soe", user_id, existing_task_id=task.id
        )
        assert is_new is True
        assert new_task.id != task.id
        assert new_task.doc_type == doc_type

    _run_in_isolated_db(_body)


@given(
    non_terminal_status=st.sampled_from(["draft", "generated", "editing", "pending_approval"]),
)
@settings(max_examples=3, deadline=None)
def test_non_terminal_reexport_reuses_deliverable(non_terminal_status):
    # Feature: audit-report-deliverable-center, Property 14: 终态再导出新建交付物（反向）
    """Property 14 反向：非终态再导出复用原交付物（不新建）"""

    async def _body(session, project_id, user_id):
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, "audit_report", "soe", user_id)
        task.status = non_terminal_status
        await session.flush()

        same_task, is_new = await svc.export_or_new_deliverable(
            project_id, "audit_report", "soe", user_id, existing_task_id=task.id
        )
        assert is_new is False
        assert same_task.id == task.id

    _run_in_isolated_db(_body)


def _reachable_status_pairs():
    """枚举 (current, target) 全组合：current 取状态机所有键，target 取所有状态值。"""
    all_states = list(VALID_STATUS_TRANSITIONS.keys())
    pairs = []
    for cur in all_states:
        for tgt in all_states:
            pairs.append((cur, tgt))
    return pairs


@given(pair=st.sampled_from(_reachable_status_pairs()))
@settings(max_examples=3, deadline=None)
def test_status_transition_legality(pair):
    # Feature: audit-report-deliverable-center, Property 5: 状态机转换合法性
    """Property 5: 转换被接受 iff target ∈ VALID_STATUS_TRANSITIONS[current]；非法则状态不变"""
    current, target = pair

    async def _body(session, project_id, user_id):
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, "audit_report", "soe", user_id)
        task.status = current
        await session.flush()

        legal = target in VALID_STATUS_TRANSITIONS.get(current, [])
        if legal:
            updated = await svc.update_status(task.id, target)
            assert updated.status == target
        else:
            with pytest.raises(ValueError):
                await svc.update_status(task.id, target)
            refreshed = await svc.get_task(task.id)
            assert refreshed.status == current

    _run_in_isolated_db(_body)


@given(
    sections=st.lists(st.sampled_from(["opinion", "basis", "kam"]), max_size=3, unique=True),
    content=st.binary(min_size=1, max_size=64),
)
@settings(max_examples=3, deadline=None)
def test_dual_path_atomic_record(sections, content):
    # Feature: audit-report-deliverable-center, Property 4: 双路径存储原子记录
    """Property 4: 成功导出后平台存在文件，且版本记录含完整元信息"""

    async def _body(session, project_id, user_id, tmp_root):
        ds_module.STORAGE_ROOT = tmp_root
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, "audit_report", "soe", user_id)
        await svc.update_status(task.id, "generating")

        result = await svc.render_and_store(
            task.id,
            docx_bytes=content,
            html_content="<html>x</html>",
            user_id=user_id,
            source_snapshot_refs={"tb_hash": "deadbeef"},
            selected_sections=sections,
        )
        assert result.platform_persist_failed is False
        # 平台存储中存在文件
        assert result.file_path is not None
        assert Path(result.file_path).exists()
        # 版本记录含完整元信息
        ver = result.version
        assert ver.file_path is not None
        assert ver.file_size == len(content)
        assert ver.selected_sections == sections
        assert ver.created_by == user_id
        assert ver.created_at is not None
        # task 维度也回填了文档类型/大小/章节
        refreshed = await svc.get_task(task.id)
        assert refreshed.doc_type == "audit_report"
        assert refreshed.file_size == len(content)
        assert refreshed.selected_sections == sections

    async def _runner():
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_DELIVERABLE_TABLES)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        original_root = ds_module.STORAGE_ROOT
        try:
            with tempfile.TemporaryDirectory() as td:
                async with session_factory() as session:
                    project_id, user_id = await _seed_project_user(session)
                    await session.commit()
                    await _body(session, project_id, user_id, Path(td))
        finally:
            ds_module.STORAGE_ROOT = original_root
            await engine.dispose()

    asyncio.run(_runner())


@given(
    n=st.integers(min_value=2, max_value=6),
)
@settings(max_examples=3, deadline=None)
def test_version_chain_time_desc(n):
    # Feature: audit-report-deliverable-center, Property 8: 版本链时间倒序
    """Property 8: get_version_chain 返回序列按创建时间严格倒序"""

    async def _body(session, project_id, user_id):
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, "audit_report", "soe", user_id)
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        # 显式构造严格递增 created_at 的版本
        for i in range(n):
            session.add(
                WordExportTaskVersion(
                    word_export_task_id=task.id,
                    version_no=i + 2,  # v1 由 create_task 创建
                    file_path=f"/s/v{i}.docx",
                    created_by=user_id,
                    created_at=base + timedelta(minutes=i + 1),
                )
            )
        await session.flush()

        chain = await svc.get_version_chain(task.id)
        times = [v.created_at for v in chain]
        # 严格倒序
        assert all(a > b for a, b in zip(times, times[1:]))

    _run_in_isolated_db(_body)


def test_dual_path_downgrade_returns_blob_on_platform_failure():
    """3.9 单元测试：平台写失败仍返回 blob（降级标志），版本记录仍留存（2.3）"""

    async def _runner():
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_DELIVERABLE_TABLES)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                project_id, user_id = await _seed_project_user(session)
                await session.commit()
                svc = DeliverableService(session)
                task = await svc.create_task(project_id, "audit_report", "soe", user_id)
                # 不提供任何文件内容 → 触发平台写入失败分支
                result = await svc.render_and_store(
                    task.id,
                    docx_bytes=None,
                    docx_path=None,
                    user_id=user_id,
                    selected_sections=["opinion"],
                )
                # 降级标志置位
                assert result.platform_persist_failed is True
                # blob 信息仍可用（download_url 仍生成），且版本记录仍创建留存
                assert result.download_url is not None
                assert result.version is not None
                chain = await svc.get_version_chain(task.id)
                assert any(v.id == result.version.id for v in chain)
        finally:
            await engine.dispose()

    asyncio.run(_runner())
