"""Phase4 真实 PG readiness dry-run — 事务内执行后回滚，零痕迹

spec: chain-closure-phase4-deliverable-center-trio 任务 14
需求: 7.5

语义：
- 连接真实 PG（不可达时 skip，不以 SQLite 冒充）
- 选择 TB 行数最多的项目做 readiness 检查
- 整个过程在 BEGIN ... ROLLBACK 内，严禁 COMMIT
- 前后行数指纹比对，确认零增量
- formula_push_runs 表不存在时 readiness 诚实报 blocked，不 500
- 数据不可用时标 data-blocked，不假绿
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any
from uuid import UUID

import pytest

logger = logging.getLogger(__name__)

# ── PG 连接参数 ──────────────────────────────────────────────────────

# 从环境变量或硬编码取 PG 连接串（asyncpg 原生 DSN）
PG_DSN = os.getenv(
    "TEST_PG_DSN",
    "postgresql://postgres:postgres@localhost:5432/audit_platform",
)

# SQLAlchemy async URL（asyncpg 驱动）
SA_PG_URL = os.getenv(
    "TEST_SA_PG_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform",
)

# 需要做前后行数对比的关键表（只列真实存在的表，不存在的表 _count_rows 返回 None 自动跳过）
FINGERPRINT_TABLES = [
    "export_jobs_v2",
    "export_job_items_v2",
    "export_job_attempts",
    "deliverable_snapshots",
    "deliverable_versions",
    "trial_balance",
    "financial_reports",
    "disclosure_notes",
    "adjustments",
    "formula_push_run",
    "formula_push_state",
]


# ── 辅助函数 ─────────────────────────────────────────────────────────

async def _pg_reachable() -> bool:
    """尝试连接 PG，返回是否可达。"""
    try:
        import asyncpg
        conn = await asyncio.wait_for(
            asyncpg.connect(PG_DSN), timeout=5.0,
        )
        await conn.close()
        return True
    except Exception as exc:
        logger.info("PG 不可达: %s", exc)
        return False


async def _count_rows(conn, table: str) -> int | None:
    """安全计数某张表的行数，表不存在返回 None。"""
    try:
        row = await conn.fetchrow(f"SELECT count(*) AS cnt FROM {table}")  # noqa: S608
        return row["cnt"]
    except Exception:
        return None


async def _snapshot_row_counts(conn) -> dict[str, int | None]:
    """对所有指纹表做一次行数快照。"""
    return {t: await _count_rows(conn, t) for t in FINGERPRINT_TABLES}


async def _pick_best_project(conn) -> dict[str, Any] | None:
    """选择 TB 行数最多的非删除项目。返回 {id, name, year, tb_count}。"""
    row = await conn.fetchrow("""
        SELECT
            p.id,
            p.name,
            COALESCE(p.audit_year, EXTRACT(YEAR FROM p.audit_period_end)::int) AS year,
            COUNT(tb.id) AS tb_count
        FROM projects p
        LEFT JOIN trial_balance tb
            ON tb.project_id = p.id
            AND tb.is_deleted = false
        WHERE p.is_deleted = false
        GROUP BY p.id, p.name, p.audit_year, p.audit_period_end
        ORDER BY COUNT(tb.id) DESC
        LIMIT 1
    """)
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "year": row["year"],
        "tb_count": row["tb_count"],
    }


async def _table_exists(conn, table_name: str) -> bool:
    """检查 PG 表是否存在。"""
    row = await conn.fetchrow(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=$1) AS ex",
        table_name,
    )
    return row["ex"]


# ── 测试 ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_real_pg_readiness_dryrun():
    """真实 PG readiness dry-run — 事务内执行后回滚，零痕迹。

    流程：
    1. PG probe → 不可达则 skip
    2. 选择 TB 最多的项目
    3. asyncpg 独立连接记录 BEFORE 行数
    4. SQLAlchemy async session（带显式 BEGIN）执行 readiness
    5. 如果 readiness = ready → 尝试创建 snapshot + job（仍在事务内）
    6. ROLLBACK
    7. asyncpg 独立连接记录 AFTER 行数
    8. 断言 BEFORE == AFTER（零痕迹）
    9. 日志输出 readiness 结果
    """
    # ── 1. PG 可达性 ──
    if not await _pg_reachable():
        pytest.skip("PG 不可达，跳过真实 dry-run")

    import asyncpg

    # ── 2. 选项目 ──
    probe_conn = await asyncpg.connect(PG_DSN)
    try:
        project_info = await _pick_best_project(probe_conn)
        if project_info is None:
            pytest.skip("PG 中无可用项目，标 data-blocked")

        project_id: UUID = project_info["id"]
        year: int | None = project_info["year"]
        tb_count: int = project_info["tb_count"]

        logger.info(
            "选定项目: %s (id=%s, year=%s, tb=%d)",
            project_info["name"], project_id, year, tb_count,
        )

        if year is None:
            pytest.skip(
                f"项目 {project_info['name']} 审计年度为 NULL，标 data-blocked"
            )

        # ── 3. BEFORE 行数快照 ──
        before = await _snapshot_row_counts(probe_conn)
        logger.info("BEFORE 行数: %s", json.dumps(
            {k: v for k, v in before.items() if v is not None}, indent=2,
        ))
    finally:
        await probe_conn.close()

    # ── 4. SQLAlchemy 事务内 readiness ──
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    sa_engine = create_async_engine(SA_PG_URL, echo=False)
    async_session_factory = sessionmaker(
        sa_engine, class_=AsyncSession, expire_on_commit=False,
    )

    readiness_result = None
    readiness_dict = None
    snapshot_created = False
    job_created = False

    try:
        async with sa_engine.connect() as raw_conn:
            # 显式开始事务（禁止 autocommit）
            async with raw_conn.begin() as txn:
                session = AsyncSession(bind=raw_conn, expire_on_commit=False)
                try:
                    from app.services.deliverable_readiness_service import (
                        DeliverableReadinessService,
                    )

                    service = DeliverableReadinessService()
                    readiness_result = await service.check(
                        session, project_id, year,
                        include_file_checks=False,  # 文件物理校验在 dry-run 中跳过
                    )
                    readiness_dict = DeliverableReadinessService.result_to_dict(readiness_result)

                    logger.info(
                        "readiness status: %s, blockers: %d, warnings: %d",
                        readiness_result.status,
                        len(readiness_result.hard_blockers),
                        len(readiness_result.warnings),
                    )
                    for b in readiness_result.hard_blockers:
                        logger.info("  BLOCKER [%s]: %s", b.code, b.message)
                    for w in readiness_result.warnings:
                        logger.info("  WARNING [%s]: %s", w.code, w.message)

                    # ── 5. 如果 ready → 尝试创建 snapshot + job（事务内）──
                    if readiness_result.status in ("ready", "ready_with_warnings"):
                        import uuid as uuid_mod
                        from datetime import datetime, timezone

                        from app.models.phase13_models import (
                            DeliverableSnapshot,
                            ExportJob,
                        )

                        digest_val = readiness_result.snapshot.get("digest", "dry-run-test")

                        # 先查是否已有相同 digest 的 snapshot（Task 16 真实执行留下的）
                        from sqlalchemy import select
                        existing_snap = (await session.execute(
                            select(DeliverableSnapshot).where(
                                DeliverableSnapshot.digest == digest_val,
                            )
                        )).scalar_one_or_none()

                        if existing_snap is not None:
                            snap = existing_snap
                            snapshot_created = True
                            logger.info(
                                "snapshot 已存在（复用）: %s (digest=%s…)",
                                snap.id, digest_val[:16],
                            )
                        else:
                            snap = DeliverableSnapshot(
                                id=uuid_mod.uuid4(),
                                project_id=project_id,
                                year=year,
                                digest=digest_val,
                                payload=readiness_result.snapshot.get("payload"),
                                created_at=datetime.now(timezone.utc),
                            )
                            session.add(snap)
                            await session.flush()
                            snapshot_created = True
                            logger.info("snapshot 已创建（事务内）: %s", snap.id)

                        # 查询一个真实 user id 用作 initiated_by（FK 约束）
                        from app.models.core import User as UserModel
                        real_user = (await session.execute(
                            select(UserModel.id).limit(1)
                        )).scalar_one_or_none()
                        if real_user is None:
                            logger.info("无可用 user，跳过 job 创建")
                        else:
                            job = ExportJob(
                                id=uuid_mod.uuid4(),
                                project_id=project_id,
                                job_type="deliverable_trio",
                                status="queued",
                                kind="deliverable_trio",
                                year=year,
                                snapshot_id=snap.id,
                                trio_total=3,
                                trio_succeeded=0,
                                initiated_by=real_user,
                            )
                            session.add(job)
                            await session.flush()
                            job_created = True
                            logger.info("job 已创建（事务内）: %s", job.id)

                finally:
                    # ── 6. ROLLBACK — 核心：绝不 commit ──
                    await txn.rollback()
                    logger.info("事务已 ROLLBACK")
    finally:
        await sa_engine.dispose()

    # ── 7. AFTER 行数快照 ──
    after_conn = await asyncpg.connect(PG_DSN)
    try:
        after = await _snapshot_row_counts(after_conn)
        logger.info("AFTER 行数: %s", json.dumps(
            {k: v for k, v in after.items() if v is not None}, indent=2,
        ))
    finally:
        await after_conn.close()

    # ── 8. 零痕迹断言 ──
    for table in FINGERPRINT_TABLES:
        b = before.get(table)
        a = after.get(table)
        if b is not None and a is not None:
            assert b == a, (
                f"表 {table} 前后行数不一致: before={b}, after={a} — "
                "事务可能泄漏了 COMMIT"
            )

    # ── 9. 结果总结 ──
    assert readiness_result is not None, "readiness 检查未执行"
    assert readiness_dict is not None

    logger.info("=" * 60)
    logger.info("干跑结果总结")
    logger.info("=" * 60)
    logger.info("  项目: %s", project_info["name"])
    logger.info("  年度: %s", year)
    logger.info("  TB 行数: %d", tb_count)
    logger.info("  readiness: %s", readiness_result.status)
    logger.info("  硬闸门: %d 条", len(readiness_result.hard_blockers))
    logger.info("  软警告: %d 条", len(readiness_result.warnings))
    logger.info("  snapshot 创建: %s", snapshot_created)
    logger.info("  job 创建: %s", job_created)
    logger.info("  零痕迹校验: PASS")

    if readiness_result.status == "blocked":
        blocker_codes = [b.code for b in readiness_result.hard_blockers]
        logger.info(
            "  DATA-BLOCKED: readiness 报阻断 %s — "
            "这是预期结果（phase2 迁移未执行 / 数据不完整）",
            blocker_codes,
        )


@pytest.mark.asyncio
async def test_real_pg_readiness_blockers_honest():
    """真实 PG: readiness 诚实报 blockers，不 500，不假绿。

    验证：
    - 连接真 PG 执行 readiness，不抛未捕获异常
    - blockers 全部有中文 message
    - status 与 blockers 一致（有 blocker → blocked，无 → ready/ready_with_warnings）
    - 严格事务回滚
    """
    if not await _pg_reachable():
        pytest.skip("PG 不可达")

    import asyncpg

    probe_conn = await asyncpg.connect(PG_DSN)
    try:
        project_info = await _pick_best_project(probe_conn)
        if project_info is None:
            pytest.skip("PG 中无可用项目")

        fp_table_exists = await _table_exists(probe_conn, "formula_push_run")
        attempts_table_exists = await _table_exists(probe_conn, "export_job_attempts")
    finally:
        await probe_conn.close()

    project_id = project_info["id"]
    year = project_info["year"]
    if year is None:
        pytest.skip(f"项目 {project_info['name']} 年度为 NULL")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    sa_engine = create_async_engine(SA_PG_URL, echo=False)
    try:
        async with sa_engine.connect() as raw_conn:
            async with raw_conn.begin() as txn:
                session = AsyncSession(bind=raw_conn, expire_on_commit=False)
                try:
                    from app.services.deliverable_readiness_service import (
                        DeliverableReadinessService,
                    )

                    service = DeliverableReadinessService()

                    # 核心：不 500、不抛未捕获异常
                    readiness = await service.check(
                        session, project_id, year,
                        include_file_checks=False,
                    )

                    # ── 诚实性断言 ──

                    # 1. status 与 blockers 一致
                    if readiness.hard_blockers:
                        assert readiness.status == "blocked", (
                            f"有 {len(readiness.hard_blockers)} 个硬闸门但 "
                            f"status={readiness.status}，应为 blocked"
                        )
                    else:
                        assert readiness.status in ("ready", "ready_with_warnings"), (
                            f"无硬闸门但 status={readiness.status}"
                        )

                    # 2. 每条 blocker 有中文 message
                    for b in readiness.hard_blockers:
                        assert b.code, f"blocker 缺 code: {b}"
                        assert b.message, f"blocker 缺 message: {b}"
                        assert any(
                            "\u4e00" <= c <= "\u9fff" for c in b.message
                        ), f"blocker message 非中文: {b.message}"

                    # 3. 每条 warning 有中文 message
                    for w in readiness.warnings:
                        assert w.code, f"warning 缺 code: {w}"
                        assert w.message, f"warning 缺 message: {w}"

                    # 4. formula_push 诚实报告
                    if not fp_table_exists:
                        # 表不存在 → 必有 upstream_not_ready
                        blocker_codes = [b.code for b in readiness.hard_blockers]
                        assert "upstream_not_ready" in blocker_codes, (
                            f"formula_push_run 不存在但未报 upstream_not_ready。"
                            f"实际: {blocker_codes}"
                        )
                        logger.info(
                            "formula_push_run 不存在 → upstream_not_ready 验证通过"
                        )
                    else:
                        # 表存在 — 检查 formula_push 源状态诚实
                        fp_source = readiness.sources.get("formula_push", {})
                        logger.info(
                            "formula_push_run 表存在，源状态: available=%s, count=%s",
                            fp_source.get("available"),
                            fp_source.get("count"),
                        )

                    # 5. trio 结构完整
                    assert readiness.trio.get("total") == 3
                    steps = readiness.trio.get("steps", [])
                    assert len(steps) == 3
                    expected_keys = ["financial_report", "disclosure_notes", "audit_report"]
                    for i, step in enumerate(steps):
                        assert step["key"] == expected_keys[i], (
                            f"trio step {i} key={step['key']}，"
                            f"期望 {expected_keys[i]}"
                        )
                        assert step["sequence"] == i + 1

                    logger.info(
                        "诚实性验证通过: status=%s, blockers=%d, warnings=%d, "
                        "trio=%d steps",
                        readiness.status,
                        len(readiness.hard_blockers),
                        len(readiness.warnings),
                        len(steps),
                    )
                    for b in readiness.hard_blockers:
                        logger.info("  BLOCKER [%s]: %s", b.code, b.message)

                finally:
                    await txn.rollback()
    finally:
        await sa_engine.dispose()
