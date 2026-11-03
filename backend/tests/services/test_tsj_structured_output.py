"""
TSJ 结构化输出服务单测

覆盖：
- Task 3.1: build_structured_prompt 构建
- Task 3.2: parse_findings_json 解析 + write_findings_to_ai_content 写入
- Task 3.3: process_review_response fallback 逻辑
"""

import json
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.tsj_structured_output_service import (
    STRUCTURED_OUTPUT_INSTRUCTION,
    TsjConfirmationLogWriteError,
    build_structured_prompt,
    parse_findings_json,
    process_review_response,
    write_findings_to_ai_content,
)


def _unit_db() -> MagicMock:
    """给纯业务单元测试的最小 AsyncSession 双身。

    ``AsyncSession.add`` / ``begin_nested`` 不是 coroutine。旧用 `AsyncMock()` 冒充
    整个 session，新增日志路径后会把 `db.add(...)`、`db.begin_nested()` 都变成未 await
    的 coroutine，测试虽绿却报 RuntimeWarning。真正的日志语义由下面的真实 SQLite
    类覆盖；这些旧测试只关心 AIContent 的组装和事务边界（不 commit、不 rollback），
    因此同步 add + 异步 flush / commit / rollback 的形状必须与真实 Session 对齐。
    """
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()

    @asynccontextmanager
    async def _nested_transaction():
        yield

    db.begin_nested = MagicMock(side_effect=_nested_transaction)
    return db


# --------------------------------------------------------------------------
# Task 3.1: build_structured_prompt
# --------------------------------------------------------------------------


class TestBuildStructuredPrompt:
    def test_appends_instruction(self):
        result = build_structured_prompt("检查存在性", "底稿内容ABC")
        assert "检查存在性" in result
        assert "底稿内容ABC" in result
        assert STRUCTURED_OUTPUT_INSTRUCTION in result

    def test_contains_json_format_requirement(self):
        result = build_structured_prompt("base", "content")
        assert '"findings"' in result
        assert "issue_type" in result
        assert "severity" in result


# --------------------------------------------------------------------------
# Task 3.2: parse_findings_json
# --------------------------------------------------------------------------


class TestParseFindingsJson:
    def test_direct_json(self):
        """直接 JSON 文本解析"""
        text = json.dumps({
            "findings": [
                {
                    "issue_type": "数值错误",
                    "severity": "high",
                    "sheet": "应收账款明细",
                    "cell_range": "B5:D5",
                    "description": "金额不匹配",
                    "evidence_ref": "D2-3!B5",
                    "remediation": "核实原始凭证",
                }
            ]
        })
        result = parse_findings_json(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["issue_type"] == "数值错误"

    def test_code_block_json(self):
        """从 markdown 代码块提取"""
        text = "以下是复核结果：\n```json\n" + json.dumps({
            "findings": [{"issue_type": "逻辑错误", "severity": "medium",
                          "sheet": "S1", "cell_range": "A1",
                          "description": "desc", "evidence_ref": "",
                          "remediation": "fix"}]
        }) + "\n```\n其他文字"
        result = parse_findings_json(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["issue_type"] == "逻辑错误"

    def test_embedded_json_object(self):
        """从文本中提取 {...} 模式"""
        text = '复核完成，结果如下：{"findings": [{"issue_type": "披露缺失", "severity": "low", "sheet": "X", "cell_range": "C1", "description": "d", "evidence_ref": "", "remediation": "r"}]} 以上。'
        result = parse_findings_json(text)
        assert result is not None
        assert len(result) == 1

    def test_empty_findings(self):
        """空 findings 数组"""
        text = '{"findings": []}'
        result = parse_findings_json(text)
        assert result is not None
        assert len(result) == 0

    def test_invalid_json_returns_none(self):
        """无法解析时返回 None"""
        result = parse_findings_json("这是一段纯文本复核结果，没有JSON格式。")
        assert result is None

    def test_empty_string_returns_none(self):
        result = parse_findings_json("")
        assert result is None

    def test_none_like_returns_none(self):
        result = parse_findings_json("   ")
        assert result is None

    def test_top_level_array(self):
        """顶层直接是数组"""
        text = json.dumps([
            {"issue_type": "证据不足", "severity": "high",
             "sheet": "S", "cell_range": "A1:A2",
             "description": "d", "evidence_ref": "ref",
             "remediation": "r"}
        ])
        result = parse_findings_json(text)
        assert result is not None
        assert len(result) == 1


# --------------------------------------------------------------------------
# Task 3.2: write_findings_to_ai_content
# --------------------------------------------------------------------------


class TestWriteFindingsToAiContent:
    @pytest.fixture(autouse=True)
    def _stub_real_log_writer(self):
        """本类只测 AIContent 组装；日志真实落库由后面的 SQLite 类专测。"""
        with patch(
            "app.services.tsj_structured_output_service._log_ai_content",
            new_callable=AsyncMock,
            return_value="ai-log-id",
        ):
            yield

    @pytest.mark.asyncio
    async def test_writes_one_record_per_finding(self):
        """每条 finding 写入一条 AIContent"""
        db = _unit_db()

        findings = [
            {
                "issue_type": "数值错误",
                "severity": "high",
                "sheet": "应收账款明细",
                "cell_range": "B5:D5",
                "description": "金额不匹配",
                "evidence_ref": "D2-3!B5",
                "remediation": "核实原始凭证",
            },
            {
                "issue_type": "披露缺失",
                "severity": "low",
                "sheet": "附注",
                "cell_range": "A10",
                "description": "缺少披露",
                "evidence_ref": "",
                "remediation": "补充披露",
            },
        ]

        results = await write_findings_to_ai_content(
            db=db,
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="D2-3",
            findings=findings,
            audit_cycle="D",
        )

        assert len(results) == 2
        assert db.add.call_count == 2
        # 全部写入都在一个外层保存点里；事务归调用方：服务既不 commit 也不 rollback。
        db.begin_nested.assert_called_once()
        db.commit.assert_not_awaited()
        db.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_target_cell_format(self):
        """target_cell 格式为 {wp_code}:{sheet}:{cell_range}"""
        db = _unit_db()

        findings = [
            {
                "issue_type": "数值错误",
                "severity": "medium",
                "sheet": "应收账款明细",
                "cell_range": "B5:D5",
                "description": "desc",
                "evidence_ref": "",
                "remediation": "",
            }
        ]

        results = await write_findings_to_ai_content(
            db=db,
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="D2-3",
            findings=findings,
        )

        ai_content = results[0]
        assert ai_content.data_sources["target_cell"] == "D2-3:应收账款明细:B5:D5"

    @pytest.mark.asyncio
    async def test_confirmation_status_pending(self):
        """所有写入的记录 confirmation_status = pending"""
        db = _unit_db()

        findings = [
            {"issue_type": "逻辑错误", "severity": "high",
             "sheet": "S", "cell_range": "A1",
             "description": "d", "evidence_ref": "", "remediation": "r"}
        ]

        results = await write_findings_to_ai_content(
            db=db,
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="D2",
            findings=findings,
        )

        from app.models.ai_models import AIConfirmationStatus
        assert results[0].confirmation_status == AIConfirmationStatus.pending

    @pytest.mark.asyncio
    async def test_empty_findings_no_commit(self):
        """空 findings 不触发 commit"""
        db = _unit_db()

        results = await write_findings_to_ai_content(
            db=db,
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="D2",
            findings=[],
        )

        assert len(results) == 0
        db.commit.assert_not_awaited()


# --------------------------------------------------------------------------
# Task 3.3: process_review_response (fallback)
# --------------------------------------------------------------------------


class TestProcessReviewResponse:
    @pytest.fixture(autouse=True)
    def _stub_real_log_writer(self):
        """本类只测结构化 / fallback 分流；日志真实落库由后面的 SQLite 类专测。"""
        with patch(
            "app.services.tsj_structured_output_service._log_ai_content",
            new_callable=AsyncMock,
            return_value="ai-log-id",
        ):
            yield

    @pytest.mark.asyncio
    async def test_structured_parse_success(self):
        """结构化解析成功时逐条写入"""
        db = _unit_db()

        response = json.dumps({
            "findings": [
                {"issue_type": "数值错误", "severity": "high",
                 "sheet": "S1", "cell_range": "B1",
                 "description": "问题1", "evidence_ref": "ref1",
                 "remediation": "修复1"},
                {"issue_type": "披露缺失", "severity": "low",
                 "sheet": "S2", "cell_range": "C2",
                 "description": "问题2", "evidence_ref": "ref2",
                 "remediation": "修复2"},
            ]
        })

        results = await process_review_response(
            db=db,
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="D2-3",
            response_text=response,
            audit_cycle="D",
        )

        assert len(results) == 2
        assert results[0].data_sources["review_type"] == "structured"

    @pytest.mark.asyncio
    async def test_fallback_plain_text(self):
        """解析失败时 fallback 为纯文本单条存储"""
        db = _unit_db()

        plain_text = "这是一段无法解析为JSON的复核结果，包含多项发现但格式不规范。"

        results = await process_review_response(
            db=db,
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="D2-3",
            response_text=plain_text,
            audit_cycle="D",
        )

        assert len(results) == 1
        assert results[0].content_text == plain_text
        assert results[0].data_sources["review_type"] == "unstructured_fallback"
        assert results[0].data_sources["parse_failed"] is True

    @pytest.mark.asyncio
    async def test_fallback_preserves_full_response(self):
        """fallback 不丢数据：完整保留原始响应"""
        db = _unit_db()

        long_text = "复核发现：\n1. 应收账款余额异常\n2. 存货计价方法不一致\n" * 10

        results = await process_review_response(
            db=db,
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            workpaper_id=uuid.uuid4(),
            wp_code="F2",
            response_text=long_text,
        )

        assert results[0].content_text == long_text


# --------------------------------------------------------------------------
# ai_content_log 真实落库（spec stash-1021-lost-changes-recovery 范围外收口）
#
# 🔴 上面那些用例全部用 `AsyncMock()` 当 db —— 永远证明不了"写进去了"。
#    本模块原先漏传 `user_id`，`wrap_ai_output_with_log` 的五参门因此恒不满足、
#    整段跳过写表，而注释写着"写入 ai_content_log 以触发
#    AIContentMustBeConfirmedRule 门禁"。签字门禁只看 `ai_content_log`，
#    不看 `ai_content` 表 ⇒ 结构化复核的未确认发现实际拦不住签字。
#    所以这里必须用真实 SQLite 引擎 + 真实 `ai_content_log` 行来断言。
# --------------------------------------------------------------------------

import pytest_asyncio  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# SQLite 兼容 JSONB + ARRAY（先于模型导入；与 test_wrap_ai_output_with_log.py 同口径）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

from app.models.base import Base  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.audit_log_models  # noqa: E402, F401
import app.models.v3_refinement_models  # noqa: E402, F401

from app.models.ai_models import AIContent  # noqa: E402
from app.models.audit_log_models import AuditLogEntry  # noqa: E402
from app.models.v3_refinement_models import AiContentLog  # noqa: E402

_LOG_DB_URL = "sqlite+aiosqlite:///:memory:"
_log_engine = create_async_engine(_LOG_DB_URL, echo=False)


@pytest_asyncio.fixture
async def log_db() -> AsyncSession:
    """真实（内存）数据库会话，建本测试需要的 5 张表。"""
    async with _log_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                Base.metadata.tables["users"],
                Base.metadata.tables["projects"],
                Base.metadata.tables["ai_content"],
                Base.metadata.tables["ai_content_log"],
                Base.metadata.tables["audit_log_entries"],
            ],
        )
    factory = async_sessionmaker(_log_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def log_user_project(log_db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """预写 users / projects 各一条供 FK 引用。"""
    from app.models.base import ProjectStatus, UserRole
    from app.models.core import Project, User

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    log_db.add(
        User(
            id=user_id,
            username=f"tsj-{user_id.hex[:8]}",
            email=f"{user_id.hex[:8]}@test.local",
            hashed_password="hashed",
            role=UserRole.auditor,
            is_active=True,
        )
    )
    log_db.add(
        Project(
            id=project_id,
            name="TSJ 结构化复核测试项目",
            client_name="测试客户",
            status=ProjectStatus.execution,
        )
    )
    await log_db.commit()
    return user_id, project_id


_FINDING = {
    "issue_type": "数值错误",
    "severity": "high",
    "sheet": "应收账款明细",
    "cell_range": "B5:D5",
    "description": "金额不匹配",
    "evidence_ref": "D2-3!B5",
    "remediation": "核实原始凭证",
}


class TestAiContentLogActuallyWritten:
    @pytest.mark.asyncio
    async def test_findings_write_one_pending_log_row_each(
        self, log_db: AsyncSession, log_user_project
    ):
        """每条 finding 都落一行 pending 的 ai_content_log（不是只落 ai_content）。"""
        user_id, project_id = log_user_project
        wp_id = uuid.uuid4()

        second = dict(_FINDING, sheet="附注", cell_range="A10", description="缺少披露")
        results = await write_findings_to_ai_content(
            db=log_db,
            project_id=project_id,
            workpaper_id=wp_id,
            wp_code="D2-3",
            findings=[_FINDING, second],
            audit_cycle="D",
            user_id=user_id,
        )
        assert len(results) == 2
        returned_log_ids = {
            (row.data_sources or {}).get("ai_content_log_id") for row in results
        }
        assert None not in returned_log_ids and len(returned_log_ids) == 2

        logs = (
            (await log_db.execute(select(AiContentLog).where(AiContentLog.project_id == project_id)))
            .scalars()
            .all()
        )
        assert len(logs) == 2, "两条 finding 必须各写一行 ai_content_log"
        assert returned_log_ids == {str(log.id) for log in logs}
        assert {log.confirm_action for log in logs} == {"pending"}
        assert {log.user_id for log in logs} == {user_id}
        assert {log.wp_id for log in logs} == {wp_id}

    @pytest.mark.asyncio
    async def test_log_target_cell_carries_finding_position(
        self, log_db: AsyncSession, log_user_project
    ):
        """target_cell 把 finding 的位置带进日志（供待确认面板显示定位）。"""
        user_id, project_id = log_user_project
        wp_id = uuid.uuid4()

        await write_findings_to_ai_content(
            db=log_db,
            project_id=project_id,
            workpaper_id=wp_id,
            wp_code="D2-3",
            findings=[_FINDING],
            user_id=user_id,
        )
        log = (await log_db.execute(select(AiContentLog))).scalars().one()
        # ai_content_log_service.create 会前缀化成 {instance_type}:{instance_id}:{target_cell}
        assert log.target_cell == f"workpaper:{wp_id}:D2-3:应收账款明细:B5:D5"
        assert log.generated_content == "金额不匹配\n整改建议：核实原始凭证"

    @pytest.mark.asyncio
    async def test_log_row_blocks_sign_off_gate(
        self, log_db: AsyncSession, log_user_project
    ):
        """落库的 pending 行真的被签字门禁查到（这是写它的唯一目的）。"""
        from app.services import ai_content_log_service

        user_id, project_id = log_user_project
        await write_findings_to_ai_content(
            db=log_db,
            project_id=project_id,
            workpaper_id=uuid.uuid4(),
            wp_code="D2-3",
            findings=[_FINDING],
            user_id=user_id,
        )
        pending = await ai_content_log_service.list_pending_by_project(
            db=log_db, project_id=project_id, limit=5
        )
        assert len(pending) == 1
        count = await ai_content_log_service.count_pending_by_project(
            db=log_db, project_id=project_id
        )
        assert count == 1

    @pytest.mark.asyncio
    async def test_log_row_has_lifecycle_audit(
        self, log_db: AsyncSession, log_user_project
    ):
        """写日志同时留一条 ai_content_lifecycle 审计（哈希链起点）。"""
        user_id, project_id = log_user_project
        await write_findings_to_ai_content(
            db=log_db,
            project_id=project_id,
            workpaper_id=uuid.uuid4(),
            wp_code="D2-3",
            findings=[_FINDING],
            user_id=user_id,
        )
        entries = (await log_db.execute(select(AuditLogEntry))).scalars().all()
        assert len(entries) == 1
        assert entries[0].action_type == "ai_content_generate"
        assert entries[0].user_id == user_id

    @pytest.mark.asyncio
    async def test_fallback_path_also_writes_log(
        self, log_db: AsyncSession, log_user_project
    ):
        """解析失败的 fallback 路径同样落一行日志，定位退回 workpaper:{id}。"""
        user_id, project_id = log_user_project
        wp_id = uuid.uuid4()

        results = await process_review_response(
            db=log_db,
            project_id=project_id,
            workpaper_id=wp_id,
            wp_code="D2-3",
            response_text="这段文本不是 JSON，解析必然失败。",
            audit_cycle="D",
            user_id=user_id,
        )
        assert len(results) == 1
        log = (await log_db.execute(select(AiContentLog))).scalars().one()
        assert log.target_cell == f"workpaper:{wp_id}"
        assert log.confirm_action == "pending"

    @pytest.mark.asyncio
    async def test_log_write_failure_is_fail_closed_and_leaves_no_ai_content(
        self, log_db: AsyncSession, log_user_project, caplog
    ):
        """确认日志失败必须撤销 AIContent，不能留下 gate 读不到的 pending 行。"""
        import logging as _logging

        user_id, project_id = log_user_project

        with patch(
            "app.services.ai_content_log_service.create",
            new_callable=AsyncMock,
            side_effect=RuntimeError("注入：ai_content_log 写入失败"),
        ):
            with caplog.at_level(_logging.ERROR, logger="app.services.tsj_structured_output_service"):
                with pytest.raises(TsjConfirmationLogWriteError, match="确认流程"):
                    await write_findings_to_ai_content(
                        db=log_db,
                        project_id=project_id,
                        workpaper_id=uuid.uuid4(),
                        wp_code="D2-3",
                        findings=[_FINDING],
                        user_id=user_id,
                    )

        rows = (await log_db.execute(select(AIContent))).scalars().all()
        logs = (await log_db.execute(select(AiContentLog))).scalars().all()
        assert rows == [], "日志失败不得留下 AIContent pending（否则签字门禁看不见）"
        assert logs == [], "失败的日志必须随保存点回滚，不留半成品"
        # 保存点回滚后当前 session 仍能继续查询，而不是 PG aborted transaction。
        assert await log_db.scalar(select(AiContentLog.id).limit(1)) is None
        assert any(
            "本次复核将整体回滚" in r.getMessage() for r in caplog.records
        ), "必须按 ERROR 点名 fail-closed，否则运维侧看不见"

    @pytest.mark.asyncio
    async def test_user_id_is_required_keyword(self):
        """漏传 user_id 必须在调用绑定时就 TypeError 并点名 user_id，而不是静默跳过写日志。

        只写 ``pytest.raises(TypeError)`` 不够：参数一旦改成可选，函数体里别处偶发的
        TypeError（例如假 session 不支持 ``async with``）也会让断言通过 —— 2026-10-31
        「user_id 改可选」的变异正是这样存活的。所以同时钉签名和错误信息。
        """
        import inspect

        for fn in (write_findings_to_ai_content, process_review_response):
            param = inspect.signature(fn).parameters["user_id"]
            assert param.kind is inspect.Parameter.KEYWORD_ONLY, fn.__name__
            assert param.default is inspect.Parameter.empty, fn.__name__

        with pytest.raises(TypeError, match="user_id"):
            await write_findings_to_ai_content(
                db=AsyncMock(),
                project_id=uuid.uuid4(),
                workpaper_id=uuid.uuid4(),
                wp_code="D2-3",
                findings=[_FINDING],
            )
        with pytest.raises(TypeError, match="user_id"):
            await process_review_response(
                db=AsyncMock(),
                project_id=uuid.uuid4(),
                workpaper_id=uuid.uuid4(),
                wp_code="D2-3",
                response_text="x",
            )

    @pytest.mark.asyncio
    async def test_failure_after_flush_inside_savepoint_rolls_back_all_content(
        self, log_db: AsyncSession, log_user_project
    ):
        """日志已经 flush 后再失败，保存点必须撤销本次所有 AIContent 与日志。"""
        user_id, project_id = log_user_project

        with patch(
            "app.services.ai_content_log_service._write_lifecycle_audit",
            new_callable=AsyncMock,
            side_effect=RuntimeError("注入：审计写入失败（此时 log 行已 flush）"),
        ):
            with pytest.raises(TsjConfirmationLogWriteError, match="确认流程"):
                await write_findings_to_ai_content(
                    db=log_db,
                    project_id=project_id,
                    workpaper_id=uuid.uuid4(),
                    wp_code="D2-3",
                    findings=[_FINDING, dict(_FINDING, description="第二条")],
                    user_id=user_id,
                )

        rows = (await log_db.execute(select(AIContent))).scalars().all()
        logs = (await log_db.execute(select(AiContentLog))).scalars().all()
        assert rows == [], "保存点回滚必须带走本次所有 AIContent"
        assert logs == [], "已 flush 的日志也必须随保存点回滚"
        assert await log_db.scalar(select(AIContent.id).limit(1)) is None

    @pytest.mark.asyncio
    async def test_non_log_failure_mid_batch_rolls_back_earlier_findings(
        self, log_db: AsyncSession, log_user_project
    ):
        """日志之外的异常（第二条不是 dict）同样撤销前一条已写好的内容与日志，并原样冒泡。

        服务不改包、不 rollback 调用方事务：异常类型保持原样交给路由的通用分支
        （503 + rollback）；靠外层保存点保证本批次全有或全无。
        """
        from app.models.base import ProjectStatus
        from app.models.core import Project

        user_id, project_id = log_user_project
        # 调用方在同一事务里先写、尚未提交的数据：服务若越权 rollback 整个事务就会丢掉它。
        caller_marker = uuid.uuid4()
        log_db.add(
            Project(
                id=caller_marker,
                name="调用方未提交的数据",
                client_name="测试客户",
                status=ProjectStatus.execution,
            )
        )
        await log_db.flush()

        with pytest.raises(AttributeError):
            await write_findings_to_ai_content(
                db=log_db,
                project_id=project_id,
                workpaper_id=uuid.uuid4(),
                wp_code="D2-3",
                findings=[_FINDING, "不是 dict 的 finding"],  # type: ignore[list-item]
                user_id=user_id,
            )

        assert (await log_db.execute(select(AIContent))).scalars().all() == []
        assert (await log_db.execute(select(AiContentLog))).scalars().all() == []
        assert (
            await log_db.scalar(select(Project.id).where(Project.id == caller_marker))
        ) == caller_marker, "服务只能回滚自己的保存点，不得丢掉调用方未提交的写入"


    @pytest.mark.asyncio
    async def test_fabricated_log_id_without_row_is_fail_closed(
        self, log_db: AsyncSession, log_user_project
    ):
        """写入器返回 UUID 但数据库无对应行时，不能把它当作可确认内容。"""
        user_id, project_id = log_user_project
        fabricated = uuid.uuid4()
        with patch(
            "app.services.tsj_structured_output_service.wrap_ai_output_with_log",
            new_callable=AsyncMock,
            return_value={
                "ai_content_log_id": str(fabricated),
                "confirm_action": "pending",
            },
        ):
            with pytest.raises(TsjConfirmationLogWriteError, match="确认流程"):
                await write_findings_to_ai_content(
                    db=log_db,
                    project_id=project_id,
                    workpaper_id=uuid.uuid4(),
                    wp_code="D2-3",
                    findings=[_FINDING],
                    user_id=user_id,
                )

        assert (await log_db.execute(select(AIContent))).scalars().all() == []
        assert (await log_db.execute(select(AiContentLog))).scalars().all() == []
