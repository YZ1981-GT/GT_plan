"""批 8 回归：合并版本向量在请求路径与 runner 路径必须同源（含 report_scope/period_end）。

缺陷（task 8.2 阻断，已确定性复现）：
  - 请求路径 ``consol_operation_service._snapshot`` 调用
    ``build_version_vector(db, context=resolved_context, tree=tree)``，其中 resolved_context
    由 ``build_consol_context`` 产出，``report_scope='consolidated'`` / ``period_end`` 均已填。
  - runner 路径 ``consol_operation_runner._load_runtime`` / ``_post_vector`` 曾改为传位置
    ``project_id/year`` + ``tree_fingerprint/template_type``（不传 context），于是 ``build_version_vector``
    内部用 bare ``ConsolContext`` 兜底，``report_scope=None`` / ``period_end=None`` ⇒
    ``template_digest`` 与请求路径不同 ⇒ ``vectors_equal`` 恒 False ⇒ 每次 refresh_all/push
    都被判成 stale（INPUT_VERSION_CHANGED），卡死「succeeded → published run → artifact → sign-off」成功尾链。

修复：runner 两处改回传已解析的 ``context=context``。本测试用同一 SQLite 库证明：
  1. 请求路径向量 == runner 路径向量（同 digest、同 template_digest、``vectors_equal`` 为 True）；
  2. 变异对照：若仍走旧的 bare-context 调用，``template_digest`` 不同、``vectors_equal`` 为 False
     —— 复现缺陷，确保本回归能在回退修复后变红。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401 - 注册全模型与 SQLite 方言补丁
from app.models.base import Base, ProjectStatus
from app.models.core import Project
from app.schemas.consol_operation import ConsolVersionVector
from app.services import consol_operation_runner as runner
from app.services import consol_operation_service as service
from app.services.consol_context_service import build_consol_context
from app.services.consol_tree_service import TreeNode
from app.services.consol_version_vector import build_version_vector, vectors_equal

YEAR = 2025
PERIOD_END = date(YEAR, 12, 31)


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


def _project(pid: uuid.UUID) -> Project:
    return Project(
        id=pid,
        name="【测试】版本向量同源_2025",
        client_name="【测试】版本向量同源",
        company_code="VV",
        audit_year=YEAR,
        audit_period_end=PERIOD_END,
        report_scope="consolidated",
        template_type="soe",
        status=ProjectStatus.execution,
        consol_lock=False,
    )


def _tree(pid: uuid.UUID) -> TreeNode:
    """合并根（aggregate）下挂一个单体数据叶子，叶子才带 project_id 以便 data_leaves 命中。"""
    leaf = TreeNode(
        project_id=uuid.uuid4(),
        company_code="VV-SUB",
        company_name="【测试】子公司",
        parent_company_code="VV",
        ultimate_company_code="VV",
        consol_level=2,
        children=[],
        report_scope="standalone",
        node_key="VV-SUB:subsidiary",
        role="subsidiary",
        kind="data",
        display_name="【测试】子公司",
        mode="subsidiary",
    )
    return TreeNode(
        project_id=pid,
        company_code="VV",
        company_name="【测试】版本向量同源",
        parent_company_code=None,
        ultimate_company_code="VV",
        consol_level=1,
        children=[leaf],
        report_scope="consolidated",
        node_key="VV:consol",
        role="consol",
        kind="aggregate",
        display_name="【测试】版本向量同源（合并）",
        mode="subsidiary",
    )


@pytest.mark.asyncio
async def test_request_and_runner_vectors_are_equal_with_resolved_context(factory):
    """请求路径与 runner 路径对同一未变输入必须算出相等向量（template_digest 含 report_scope/period_end）。"""
    pid = uuid.uuid4()
    tree = _tree(pid)
    async with factory() as db:
        db.add(_project(pid))
        await db.commit()

        # 请求路径：build_consol_context 产出已解析 context（report_scope/period_end 已填）。
        resolved_context = await build_consol_context(db, pid, YEAR, tree=tree)
        assert resolved_context.report_scope == "consolidated"
        assert resolved_context.period_end == PERIOD_END

        vector_request = await build_version_vector(db, context=resolved_context, tree=tree)

        # runner 路径（修复后）：同样传 context=context。
        vector_runner_fixed = await build_version_vector(db, context=resolved_context, tree=tree)

        assert vector_runner_fixed.template_digest == vector_request.template_digest
        assert vector_runner_fixed.digest == vector_request.digest
        assert vectors_equal(vector_request, vector_runner_fixed)

        # ── 变异对照：旧 runner 的 bare-context 调用（不传 context）。 ──
        # report_scope=None / period_end=None ⇒ template_digest 不同 ⇒ vectors_equal 恒 False。
        vector_bare = await build_version_vector(
            db,
            pid,
            YEAR,
            tree=tree,
            tree_fingerprint=resolved_context.tree_fingerprint,
            template_type=resolved_context.template_type,
        )
        assert vector_bare.template_digest != vector_request.template_digest, (
            "缺陷复现失败：bare-context 的 template_digest 竟与请求路径相同，"
            "说明 report_scope/period_end 未进入 template_digest，回归失去意义"
        )
        assert not vectors_equal(vector_request, vector_bare)


@pytest.mark.asyncio
async def test_load_runtime_vector_matches_stored_request_vector_so_run_is_not_stale(factory):
    """驱动真实请求路径存一个 running operation，再跑 _load_runtime，其 current_vector 必须等于
    已存向量 ⇒ execute_claim 不会短路成 stale，succeeded 成功尾链在服务层可达。"""
    pid = uuid.uuid4()
    tree = _tree(pid)
    op_id = uuid.uuid4()
    async with factory() as db:
        db.add(_project(pid))
        await db.commit()

        # 请求路径：构造 context + 版本向量，并写入 running operation（模拟 request_operation 的落库）。
        import app.services.consol_tree_service as tree_mod

        orig_build_tree = tree_mod.build_tree

        async def fake_build_tree(_db, _pid):
            return tree

        tree_mod.build_tree = fake_build_tree
        try:
            context, stored_vector = await service._snapshot(db, pid, YEAR, op_id)
        finally:
            tree_mod.build_tree = orig_build_tree

        assert context.report_scope == "consolidated"
        assert context.period_end == PERIOD_END

        from app.models.consol_operation_models import ConsolOperation

        now = datetime.now(timezone.utc)
        owner = uuid.uuid4()
        operation = ConsolOperation(
            id=op_id,
            project_id=pid,
            year=YEAR,
            operation_type="refresh_all",
            idempotency_key=str(uuid.uuid4()),
            idempotency_keys={},
            request_hash="9" * 64,
            request_payload={},
            context_json=context.to_dict(),
            version_vector=stored_vector.model_dump(mode="json"),
            status="running",
            revision=1,
            attempt=1,
            lease_owner=owner,
            lease_expires_at=now + timedelta(minutes=5),
            trigger_source="manual",
            steps=[],
            errors=[],
            result_refs={},
            metrics={},
        )
        db.add(operation)
        await db.commit()

        claim = service.OperationClaim(
            operation_id=op_id,
            project_id=pid,
            year=YEAR,
            operation_type="refresh_all",
            lease_owner=owner,
            revision=1,
        )

        # runner 路径：_load_runtime 内部 build_consol_context 用的是真实 build_tree，
        # 这里 patch 成同一棵合成树，使指纹与请求路径一致。
        import app.services.consol_tree_service as tree_mod2

        tree_mod2.build_tree = fake_build_tree
        try:
            (
                _operation,
                runtime_context,
                _runtime_tree,
                current_vector,
            ) = await runner._load_runtime(db, claim)
        finally:
            tree_mod2.build_tree = orig_build_tree

        assert runtime_context.report_scope == "consolidated"
        assert runtime_context.period_end == PERIOD_END

        # 核心断言：runner 算出的向量与请求路径存库向量相等 ⇒ 不进 stale 分支。
        stored = ConsolVersionVector.model_validate(operation.version_vector)
        assert current_vector.template_digest == stored.template_digest
        assert vectors_equal(stored, current_vector), (
            "runner 路径向量与请求路径存库向量不等 ⇒ execute_claim 会把未变输入误判为 stale"
        )
