# Feature: procedure-delegation-notification — Task 16 性能与索引计划验证
"""程序行任务性能压测 + covering/claim 索引计划 + 结构化 metrics/trace_id + 日志隐私。

Task 16 / 需求 14.4-14.5 / Design "Testing Strategy · 性能"：

- **5000 行 delegation preview ≤ 3s**（不含异步 materialize 等待，需求 14.4）：
  用 row selector 展开 5000 个已物化任务，度量 resolve + classify + 一次性 preview 创建。
- **常规任务分页查询 p95 ≤ 2s**（需求 14.4）：ProcedureTaskQueryService.list_tasks
  按 active staff 的 assignee covering index 过滤，重复采样取 p95。
- **单任务转换 p95 ≤ 1s**（需求 14.4）：ProcedureTaskTransitionService.acknowledge
  逐任务（assigned→acknowledged，wp_id=NULL 时投影 no-op）度量 + commit。
- **covering / claim 索引计划**（需求 14.4 / 12.3-12.4）：EXPLAIN 断言
  ``ix_procedure_row_tasks_assignee_cover`` 与 ``ix_task_events_claim_order`` 可命中
  （SET LOCAL enable_seqscan=off 使"Index Scan not Seq Scan"成为确定性信号）。
- **结构化 metrics / trace_id**（需求 14.5）：dispatcher.metrics 返回结构化指标；
  转换写入的 outbox 携带 trace_id（= request_id）。
- **日志隐私**（需求 14.5）：静态扫描 procedure 服务模块的 logging 语句，
  断言不记录附件正文或敏感凭证明细。

说明（诚实基准，禁止假绿）：
- 索引命中是 **确定性硬断言**（与硬件无关）。
- 延迟阈值按需求 14.4 断言并同时 **打印真实测量值**；本机（localhost PG16）实测远低于阈值。
  若目标硬件无法达到精确 p95，应如实报告实测值，绝不降断言或跳过。
- 全部为一次性 seed→度量→清理；不污染 dev 库（PERF 前缀 + 事务外显式 DELETE 清理）。

Validates: Requirements 14.4, 14.5, 12.3, 12.4
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.services.procedure_delegation_service import ProcedureDelegationService
from app.services.procedure_delivery_dispatcher import ProcedureDeliveryDispatcher
from app.services.procedure_task_query_service import (
    ProcedureTaskQueryService,
    TaskQueryFilters,
)
from app.services.procedure_task_transition_service import (
    AGGREGATE_PROCEDURE_ROW_TASK,
    ProcedureTaskTransitionService,
)

import app.models.procedure_models  # noqa: F401
import app.models.staff_models  # noqa: F401
import app.models.workpaper_models  # noqa: F401
import app.models.core  # noqa: F401

pytestmark = [pytest.mark.pg_only, pytest.mark.perf, pytest.mark.slow]

_IS_PG = settings.DATABASE_URL.startswith("postgresql")

# 压测规模（需求 14.4 = 5000 行）；CI 可用 env 降规模，本机默认 5000 真实度量。
TASK_COUNT = int(os.environ.get("PROCEDURE_PERF_TASK_COUNT", "5000"))
QUERY_SAMPLES = int(os.environ.get("PROCEDURE_PERF_QUERY_SAMPLES", "30"))
TRANSITION_SAMPLES = int(os.environ.get("PROCEDURE_PERF_TRANSITION_SAMPLES", "40"))

# 需求 14.4 阈值
PREVIEW_BUDGET_S = 3.0
QUERY_P95_BUDGET_S = 2.0
TRANSITION_P95_BUDGET_S = 1.0


def _percentile(samples: list[float], pct: float) -> float:
    """线性插值分位数（pct ∈ [0,100]）。"""
    if not samples:
        return 0.0
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


@pytest_asyncio.fixture
async def pg_perf_env():
    """连接 dev PG，复用真实 project/wp_index/user，seed 5000 已物化任务，收尾清理。"""
    if not _IS_PG:
        pytest.skip("need PostgreSQL (performance benchmark)")
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    run_id = uuid.uuid4().hex[:12]
    def_pat = f"PERFDEL::{run_id}::%"
    staff_id = uuid.uuid4()

    # 复用真实 project + wp_index + user（满足 FK 与授权归一化）
    async with factory() as s:
        picked = (
            await s.execute(
                sa.text(
                    "SELECT wi.project_id, wi.id, COALESCE(wi.audit_cycle,'D'), "
                    "COALESCE(wi.wp_code,'PERFWP') "
                    "FROM wp_index wi WHERE wi.is_deleted=false LIMIT 1"
                )
            )
        ).first()
        user_id = (await s.execute(sa.text("SELECT id FROM users LIMIT 1"))).scalar()
    if picked is None or user_id is None:
        await engine.dispose()
        pytest.skip("dev 库无 wp_index/users 可复用于性能压测")
    project_id, wp_index_id, cycle, wp_code = picked
    sheet_key = "PERFWP"

    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO staff_members (id, user_id, name, source, is_deleted) "
                "VALUES (:id,:uid,'性能压测执行人','custom',false)"
            ),
            {"id": staff_id, "uid": user_id},
        )
        # 5000 definitions（各 definition_key 全局唯一，满足 active partial unique 4 元组）
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_definitions "
                "(definition_key, template_code, template_revision_hash, sheet_key, "
                " program_no, procedure_text, source_locator, ref_snapshot, "
                " legacy_aliases, normalized_content) "
                "SELECT :prefix || g, 'PERFWP', repeat('a',64), :sk, g::text, "
                "       'perf 程序：核对明细账与总账', '{}'::jsonb, '[]'::jsonb, "
                "       '[]'::jsonb, '{}'::jsonb "
                "FROM generate_series(1, :n) g"
            ),
            {"prefix": f"PERFDEL::{run_id}::", "sk": sheet_key, "n": TASK_COUNT},
        )
        # 5000 tasks（wp_id=NULL 先委派后生成；1/3 逾期）；(project,wp_index,sheet_key,def_key) 唯一
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_tasks "
                "(id, project_id, wp_index_id, wp_id, definition_key, sheet_key, wp_code, "
                " sheet_name, program_no, procedure_text, ref_snapshot, "
                " definition_revision_hash, audit_cycle_snapshot, applicability_status, "
                " workflow_status, assignee_staff_id, assignment_version, lock_version, "
                " due_at, is_deleted, evidence_snapshot, migration_detail) "
                "SELECT gen_random_uuid(), :pid, :wi, NULL, :prefix || g, :sk, :wc, "
                "       :sk, g::text, 'perf 程序：核对明细账与总账', '[]'::jsonb, "
                "       repeat('a',64), :cy, 'execute', 'assigned', :asg, 1, 0, "
                "       CASE WHEN g % 3 = 0 THEN now() - interval '1 day' ELSE NULL END, "
                "       false, '[]'::jsonb, '{}'::jsonb "
                "FROM generate_series(1, :n) g"
            ),
            {
                "pid": project_id, "wi": wp_index_id, "prefix": f"PERFDEL::{run_id}::",
                "sk": sheet_key, "wc": wp_code, "cy": cycle, "asg": staff_id, "n": TASK_COUNT,
            },
        )
        await s.commit()
        # 让规划器可用新数据（covering index 命中确定性）
        await s.execute(sa.text("ANALYZE procedure_row_tasks"))
        await s.execute(sa.text("ANALYZE task_events"))
        await s.commit()

    env = {
        "engine": engine,
        "factory": factory,
        "project_id": project_id,
        "wp_index_id": wp_index_id,
        "user_id": user_id,
        "staff_id": staff_id,
        "cycle": cycle,
        "sheet_key": sheet_key,
        "def_pat": def_pat,
        "run_id": run_id,
    }
    try:
        yield env
    finally:
        # 清理：history / outbox / preview / tasks / definitions / staff（顺序满足 FK）
        async with factory() as s:
            await s.execute(
                sa.text(
                    "DELETE FROM procedure_row_task_history WHERE task_id IN "
                    "(SELECT id FROM procedure_row_tasks WHERE definition_key LIKE :pat)"
                ),
                {"pat": def_pat},
            )
            await s.execute(
                sa.text(
                    "DELETE FROM task_events WHERE aggregate_type=:agg AND aggregate_id IN "
                    "(SELECT id FROM procedure_row_tasks WHERE definition_key LIKE :pat)"
                ),
                {"agg": AGGREGATE_PROCEDURE_ROW_TASK, "pat": def_pat},
            )
            await s.execute(
                sa.text(
                    "DELETE FROM procedure_operation_previews "
                    "WHERE actor_user_id=:uid AND project_id=:pid AND operation='delegate'"
                ),
                {"uid": user_id, "pid": project_id},
            )
            await s.execute(
                sa.text("DELETE FROM procedure_row_tasks WHERE definition_key LIKE :pat"),
                {"pat": def_pat},
            )
            await s.execute(
                sa.text("DELETE FROM procedure_row_definitions WHERE definition_key LIKE :pat"),
                {"pat": def_pat},
            )
            await s.execute(
                sa.text("DELETE FROM staff_members WHERE id=:id"), {"id": staff_id}
            )
            await s.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_delegation_preview_5000_rows_within_budget(pg_perf_env):
    """5000 行 row-selector delegation preview ≤ 3s（不含异步 materialize，需求 14.4）。"""
    factory = pg_perf_env["factory"]
    project_id = pg_perf_env["project_id"]
    user_id = pg_perf_env["user_id"]
    staff_id = pg_perf_env["staff_id"]
    def_pat = pg_perf_env["def_pat"]

    async with factory() as s:
        task_ids = (
            await s.execute(
                sa.text(
                    "SELECT id FROM procedure_row_tasks WHERE definition_key LIKE :pat"
                ),
                {"pat": def_pat},
            )
        ).scalars().all()
    assert len(task_ids) == TASK_COUNT, f"seed 数不符: {len(task_ids)}"

    selector = {"kind": "row", "task_ids": [str(t) for t in task_ids]}
    async with factory() as s:
        svc = ProcedureDelegationService(s)
        t0 = time.perf_counter()
        preview = await svc.preview(
            project_id,
            actor_user_id=user_id,
            selector=selector,
            assignee_staff_id=staff_id,  # 同执行人 → 全 unchanged，但仍展开+分类+建 preview
        )
        elapsed = time.perf_counter() - t0
        await s.commit()

    print(
        f"\n[PERF] delegation preview rows={TASK_COUNT} status={preview['status']} "
        f"targets={preview['summary']['targets']} elapsed={elapsed:.3f}s "
        f"(budget {PREVIEW_BUDGET_S}s)"
    )
    assert preview["status"] == "ready"
    assert preview["summary"]["targets"] == TASK_COUNT
    assert elapsed <= PREVIEW_BUDGET_S, (
        f"5000 行 preview {elapsed:.3f}s 超过 {PREVIEW_BUDGET_S}s 预算"
    )


@pytest.mark.asyncio
async def test_task_query_p95_within_budget(pg_perf_env):
    """常规任务分页查询 p95 ≤ 2s（assignee covering index，需求 14.4）。"""
    factory = pg_perf_env["factory"]
    project_id = pg_perf_env["project_id"]
    user_id = pg_perf_env["user_id"]

    latencies: list[float] = []
    for _ in range(QUERY_SAMPLES):
        async with factory() as s:
            svc = ProcedureTaskQueryService(s)
            t0 = time.perf_counter()
            res = await svc.list_tasks(
                user_id,
                TaskQueryFilters(project_id=project_id, role="assignee", page=1, page_size=20),
            )
            latencies.append(time.perf_counter() - t0)
        assert res["pagination"]["total"] >= TASK_COUNT
        assert len(res["items"]) == 20

    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    print(
        f"\n[PERF] task query samples={QUERY_SAMPLES} p50={p50*1000:.1f}ms "
        f"p95={p95*1000:.1f}ms max={max(latencies)*1000:.1f}ms (budget {QUERY_P95_BUDGET_S}s)"
    )
    assert p95 <= QUERY_P95_BUDGET_S, f"任务查询 p95 {p95:.3f}s 超过 {QUERY_P95_BUDGET_S}s 预算"


@pytest.mark.asyncio
async def test_single_transition_p95_within_budget(pg_perf_env):
    """单任务转换 p95 ≤ 1s（acknowledge，含 commit，需求 14.4）。"""
    factory = pg_perf_env["factory"]
    def_pat = pg_perf_env["def_pat"]

    async with factory() as s:
        target_ids = (
            await s.execute(
                sa.text(
                    "SELECT id FROM procedure_row_tasks WHERE definition_key LIKE :pat "
                    "AND workflow_status='assigned' LIMIT :lim"
                ),
                {"pat": def_pat, "lim": TRANSITION_SAMPLES},
            )
        ).scalars().all()
    assert len(target_ids) == TRANSITION_SAMPLES

    from app.models.procedure_models import ProcedureRowTask

    latencies: list[float] = []
    for tid in target_ids:
        async with factory() as s:
            task = (
                await s.execute(sa.select(ProcedureRowTask).where(ProcedureRowTask.id == tid))
            ).scalar_one()
            svc = ProcedureTaskTransitionService(s)
            t0 = time.perf_counter()
            await svc.acknowledge(
                task,
                actor_user_id=pg_perf_env["user_id"],
                request_id=f"perf-ack-{pg_perf_env['run_id']}-{tid}",
                expected_assignment_version=1,
            )
            await s.commit()
            latencies.append(time.perf_counter() - t0)

    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    print(
        f"\n[PERF] single transition (acknowledge) samples={TRANSITION_SAMPLES} "
        f"p50={p50*1000:.1f}ms p95={p95*1000:.1f}ms max={max(latencies)*1000:.1f}ms "
        f"(budget {TRANSITION_P95_BUDGET_S}s)"
    )
    assert p95 <= TRANSITION_P95_BUDGET_S, (
        f"单任务转换 p95 {p95:.3f}s 超过 {TRANSITION_P95_BUDGET_S}s 预算"
    )


@pytest.mark.asyncio
async def test_covering_index_used_in_query_plan(pg_perf_env):
    """assignee covering index 命中查询计划（Index Scan not Seq Scan，需求 12.3）。"""
    factory = pg_perf_env["factory"]
    staff_id = pg_perf_env["staff_id"]
    async with factory() as s:
        # SET LOCAL enable_seqscan=off 使"索引可命中"成为确定性信号；覆盖列与 covering index 一致
        await s.execute(sa.text("SET LOCAL enable_seqscan = off"))
        plan_rows = (
            await s.execute(
                sa.text(
                    "EXPLAIN SELECT id, wp_index_id, wp_id, sheet_key, definition_key, "
                    "lock_version, assignment_version FROM procedure_row_tasks "
                    "WHERE is_deleted=false AND assignee_staff_id=:sid "
                    "AND workflow_status='assigned' ORDER BY due_at, project_id"
                ),
                {"sid": staff_id},
            )
        ).scalars().all()
    plan = "\n".join(plan_rows)
    print(f"\n[PERF] assignee covering-index plan:\n{plan}")
    assert "Seq Scan" not in plan, f"assignee 查询回退顺序扫描:\n{plan}"
    assert "ix_procedure_row_tasks_assignee_cover" in plan, (
        f"未命中 assignee covering index:\n{plan}"
    )


@pytest.mark.asyncio
async def test_claim_index_used_in_dispatcher_plan(pg_perf_env):
    """outbox claim index 命中 dispatcher 领取计划（Index Scan not Seq Scan，需求 12.4）。"""
    factory = pg_perf_env["factory"]
    async with factory() as s:
        await s.execute(sa.text("SET LOCAL enable_seqscan = off"))
        plan_rows = (
            await s.execute(
                sa.text(
                    "EXPLAIN SELECT id, aggregate_id, aggregate_version FROM task_events "
                    "WHERE aggregate_type=:agg AND processed_at IS NULL "
                    "AND dead_letter_at IS NULL "
                    "AND (available_at IS NULL OR available_at <= now()) "
                    "ORDER BY available_at NULLS FIRST, aggregate_id, aggregate_version"
                ),
                {"agg": AGGREGATE_PROCEDURE_ROW_TASK},
            )
        ).scalars().all()
    plan = "\n".join(plan_rows)
    print(f"\n[PERF] outbox claim-index plan:\n{plan}")
    assert "ix_task_events_claim_order" in plan, f"未命中 outbox claim index:\n{plan}"


@pytest.mark.asyncio
async def test_structured_metrics_and_trace_id(pg_perf_env):
    """结构化 dispatcher metrics + outbox trace_id（需求 14.5）。"""
    factory = pg_perf_env["factory"]
    def_pat = pg_perf_env["def_pat"]
    run_id = pg_perf_env["run_id"]
    user_id = pg_perf_env["user_id"]

    # 先产生一条真实 outbox（acknowledge），断言其 trace_id = request_id
    from app.models.procedure_models import ProcedureRowTask

    async with factory() as s:
        tid = (
            await s.execute(
                sa.text(
                    "SELECT id FROM procedure_row_tasks WHERE definition_key LIKE :pat "
                    "AND workflow_status='assigned' LIMIT 1"
                ),
                {"pat": def_pat},
            )
        ).scalar()
        task = (
            await s.execute(sa.select(ProcedureRowTask).where(ProcedureRowTask.id == tid))
        ).scalar_one()
        svc = ProcedureTaskTransitionService(s)
        req_id = f"perf-trace-{run_id}"
        await svc.acknowledge(
            task, actor_user_id=user_id, request_id=req_id, expected_assignment_version=1
        )
        await s.commit()

    async with factory() as s:
        trace_id = (
            await s.execute(
                sa.text(
                    "SELECT trace_id FROM task_events "
                    "WHERE aggregate_type=:agg AND aggregate_id=:tid "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"agg": AGGREGATE_PROCEDURE_ROW_TASK, "tid": tid},
            )
        ).scalar()
        assert trace_id == req_id, f"outbox trace_id 未记录 request_id: {trace_id!r}"

        dispatcher = ProcedureDeliveryDispatcher()
        metrics = await dispatcher.metrics(s)

    print(f"\n[PERF] dispatcher structured metrics: {metrics}")
    for key in ("backlog", "leased", "failing", "dead_letter", "processed", "oldest_age_seconds"):
        assert key in metrics, f"metrics 缺结构化字段 {key}"
    assert isinstance(metrics["backlog"], int)
    assert isinstance(metrics["oldest_age_seconds"], float)
    assert metrics["backlog"] >= 1  # 至少本测试刚写入的 outbox


def test_log_privacy_no_sensitive_body_logging():
    """静态扫描 procedure 服务日志语句：不记录附件正文或敏感凭证明细（需求 14.5）。

    不依赖 DB。扫描 backend/app/services/procedure_*.py 中 ``logger.<level>(...)`` 语句，
    断言其参数不引用附件正文 / 密码 / token / 密钥 / 证据正文等敏感字段。
    """
    import ast
    from pathlib import Path

    services_dir = Path(__file__).resolve().parent.parent.parent / "app" / "services"
    proc_files = sorted(services_dir.glob("procedure_*.py"))
    assert proc_files, "未找到 procedure_*.py 服务模块"

    # 敏感 token（日志参数中出现即视为潜在泄露）
    forbidden = (
        "password", "secret", "token", "credential", "private_key",
        "attachment_body", "file_content", "raw_body", "附件正文", "凭证明细",
    )
    _LOG_LEVELS = {"debug", "info", "warning", "warn", "error", "critical", "exception"}
    violations: list[str] = []

    for pf in proc_files:
        src = pf.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(pf))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # 匹配 logger.<level>(...) / log.<level>(...)
            if not (isinstance(func, ast.Attribute) and func.attr in _LOG_LEVELS):
                continue
            # 收集本调用的字面量文本片段
            snippet = ast.get_source_segment(src, node) or ""
            low = snippet.lower()
            for bad in forbidden:
                if bad in low:
                    violations.append(f"{pf.name}:{node.lineno} → 含敏感字段 '{bad}': {snippet[:120]}")

    assert not violations, "procedure 服务日志疑似记录敏感信息:\n" + "\n".join(violations)
