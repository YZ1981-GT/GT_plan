"""TSJ 确认日志保存点的真实 PostgreSQL 契约。

SQLite + Python RuntimeError 测不到 PostgreSQL 在 DML 约束违例后把事务标为
aborted 的语义。本文件在独立连接、外层整体回滚的真实 PG 夹具内测试：
1) 成功路径同时写 AIContent、pending ai_content_log、生命周期审计；
2) 在生产 `ai_content_log_service.create()` 的下一层注入真实 NOT NULL DML 违例，
   断言外层 TSJ 结果整体撤销、session 仍可查询，绝不留下 sign-off gate 看不到的 pending 内容。
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app.models.ai_models import AIContent
from app.models.v3_refinement_models import AiContentLog
from app.services.tsj_structured_output_service import (
    TsjConfirmationLogWriteError,
    write_findings_to_ai_content,
)
from tests.dsh_agent_panel._fixtures import IS_PG, run_with_fixture

pytestmark = [
    pytest.mark.pg_only,
    pytest.mark.skipif(not IS_PG, reason="need PostgreSQL for TSJ SAVEPOINT semantics"),
]

_FINDING = {
    "issue_type": "数据完整性",
    "severity": "high",
    "sheet": "应收账款明细",
    "cell_range": "C15:D20",
    "description": "账龄组合与余额不符",
    "evidence_ref": "D2-3!C15",
    "remediation": "重算账龄组合",
}


async def _count(session, model, project_id) -> int:
    return int(
        (await session.scalar(
            sa.select(sa.func.count()).select_from(model).where(model.project_id == project_id)
        )) or 0
    )


class TestTsjConfirmationLogPostgres:
    def test_success_persists_pending_log_and_returns_real_id(self):
        """真实 PG 成功路径：两张表与审计链一起存在，且 log id 回写 AIContent JSON。"""
        async def scenario(fx, _sql):
            actor_id = fx.actor("auditor").id
            project_id = fx.project_a.id
            wp_id = fx.wp_d_file.id
            wp_code = fx.wp_d.wp_code
            audit_cycle = fx.wp_d.audit_cycle
            rows = await write_findings_to_ai_content(
                db=fx.session,
                project_id=project_id,
                workpaper_id=wp_id,
                wp_code=wp_code,
                findings=[_FINDING],
                audit_cycle=audit_cycle,
                user_id=actor_id,
            )
            assert len(rows) == 1
            log_id = (rows[0].data_sources or {}).get("ai_content_log_id")
            assert log_id, "服务返回的 AIContent 必须带真实 ai_content_log id"
            assert await _count(fx.session, AIContent, project_id) == 1
            assert await _count(fx.session, AiContentLog, project_id) == 1
            log = await fx.session.get(AiContentLog, uuid.UUID(str(log_id)))
            assert log is not None and log.confirm_action == "pending"
            assert log.user_id == actor_id and log.wp_id == wp_id

        run_with_fixture(scenario)

    def test_real_pg_constraint_failure_rolls_back_all_pending_records_and_keeps_session_usable(self):
        """真实 NOT NULL 违例后，内外 SAVEPOINT 都回滚且外层 session 不 aborted。"""
        async def scenario(fx, _sql):
            actor_id = fx.actor("auditor").id
            project_id = fx.project_a.id
            wp_id = fx.wp_d_file.id
            wp_code = fx.wp_d.wp_code
            audit_cycle = fx.wp_d.audit_cycle
            called = []

            async def _real_constraint_failure(*, db, ai_log, user_id, action):
                # `ai_log` 已由 production create() add + flush；下一层的这条真实 PG
                # INSERT 故意少 project_id，触发 NOT NULL SQLSTATE，不替换被测函数本身。
                called.append(ai_log.id)
                await db.execute(
                    sa.text("INSERT INTO ai_content_log (id) VALUES (:id)"),
                    {"id": uuid.uuid4()},
                )

            with patch(
                "app.services.ai_content_log_service._write_lifecycle_audit",
                new=_real_constraint_failure,
            ):
                with pytest.raises(TsjConfirmationLogWriteError, match="确认流程"):
                    await write_findings_to_ai_content(
                        db=fx.session,
                        project_id=project_id,
                        workpaper_id=wp_id,
                        wp_code=wp_code,
                        findings=[_FINDING, dict(_FINDING, description="第二条")],
                        audit_cycle=audit_cycle,
                        user_id=actor_id,
                    )

            assert called, "故障必须发生在 create() 已 flush 后的生命周期审计下一层"
            assert await _count(fx.session, AIContent, project_id) == 0
            assert await _count(fx.session, AiContentLog, project_id) == 0
            # SQLSTATE 被保存点消化后同一 session 仍可继续读写，不能是 InFailedSQLTransaction。
            assert (await fx.session.scalar(sa.text("SELECT 42"))) == 42

        run_with_fixture(scenario)


    def test_flushed_results_can_be_rolled_back_by_route_response_validation(self):
        """服务返回后、路由 DTO 校验失败时，调用方 rollback 会撤销全部 pending 行。"""
        async def scenario(fx, _sql):
            actor_id = fx.actor("auditor").id
            project_id = fx.project_a.id
            wp_id = fx.wp_d_file.id
            wp_code = fx.wp_d.wp_code
            audit_cycle = fx.wp_d.audit_cycle

            # 模拟路由自己的请求事务：服务只 flush，不得 commit。
            boundary = await fx.session.begin_nested()
            try:
                rows = await write_findings_to_ai_content(
                    db=fx.session,
                    project_id=project_id,
                    workpaper_id=wp_id,
                    wp_code=wp_code,
                    findings=[_FINDING],
                    audit_cycle=audit_cycle,
                    user_id=actor_id,
                )
                assert len(rows) == 1
                assert await _count(fx.session, AIContent, project_id) == 1
                assert await _count(fx.session, AiContentLog, project_id) == 1
            finally:
                # 路由若在数量 / DTO ID 校验失败，会走这条 rollback，而非 service 已 commit。
                await boundary.rollback()

            assert await _count(fx.session, AIContent, project_id) == 0
            assert await _count(fx.session, AiContentLog, project_id) == 0
            assert (await fx.session.scalar(sa.text("SELECT 7"))) == 7

        run_with_fixture(scenario)
