"""confirmation-attachment-ocr-linkage — Task 1.1 characterization 安全网

零回归基线：锁定「回函证据链 + 状态撤回」改造 **之前** 的既有行为，供后续波次
（M1 撤回 / M2 附件链 / M3 OCR 比对 / M4 自动匹配）逐字节对照防回归。

本文件 **只断言现状**（不是断言理想行为），且不改任何 app/ 下业务代码。

锁定三类既有行为：
1. 前进单向状态机 ``confirmation_service._ALLOWED_TRANSITIONS`` 逐键精确内容，
   且 ``_STATUS_RANK`` 尚不存在（撤回能力 Task 2.1 才引入）。
2. ``transition_status`` 行为：非法转换抛中文 ValueError（现状文案）；合法转换成功。
3. ``AttachmentService.extract_confirmation_reply``：从 OCR 文本抽取
   reply_amount/reply_date/reply_entity/confidence，且返回值 **恒含**
   ``governed=False`` / ``requires_human_confirmation=True``（OCR 结果不自动落库标记）。

_Requirements: 9.1, 9.3, 9.4_
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

# ─── SQLite 兼容 shim（与既有 confirmation/attachment 测试同款）────────────────
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, User  # noqa: E402
from app.models.attachment_models import Attachment, AttachmentWorkingPaper  # noqa: E402
from app.models.workpaper_models import (  # noqa: E402
    WpIndex,
    WpStatus,
    WpSourceType,
    WpFileStatus,
    WorkingPaper,
)
from app.models.confirmation_models import Confirmation  # noqa: E402
from app.services import confirmation_service  # noqa: E402
from app.services.confirmation_service import (  # noqa: E402
    _ALLOWED_TRANSITIONS,
    create_confirmation,
    transition_status,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


# ════════════════════════════════════════════════════════════════════════════
# Part 1 — 前进单向状态机 + _STATUS_RANK 未定义（纯 import 断言，无 DB）
# ════════════════════════════════════════════════════════════════════════════


class TestAllowedTransitionsBaseline:
    """锁定 ``_ALLOWED_TRANSITIONS`` 前进单向表逐键内容不被后续改动破坏。"""

    def test_allowed_transitions_exact_dict(self):
        """整表逐键精确相等（现状：前进单向，终态空集）。"""
        assert _ALLOWED_TRANSITIONS == {
            "pending": {"sent"},
            "sent": {"returned"},
            "returned": {"matched", "discrepancy"},
            "matched": set(),
            "discrepancy": set(),
        }

    def test_allowed_transitions_per_key(self):
        """逐键断言（整表相等失败时定位到具体键）。"""
        assert _ALLOWED_TRANSITIONS["pending"] == {"sent"}
        assert _ALLOWED_TRANSITIONS["sent"] == {"returned"}
        assert _ALLOWED_TRANSITIONS["returned"] == {"matched", "discrepancy"}
        assert _ALLOWED_TRANSITIONS["matched"] == set()
        assert _ALLOWED_TRANSITIONS["discrepancy"] == set()

    def test_terminal_states_are_empty(self):
        """matched / discrepancy 为终态（现状无任何出边，尤其无反向撤回边）。"""
        assert _ALLOWED_TRANSITIONS["matched"] == set()
        assert _ALLOWED_TRANSITIONS["discrepancy"] == set()

    def test_forward_only_no_reverse_edges(self):
        """现状为纯前进图：任何目标状态都不指回其来源（无撤回边）。"""
        # 前进链的 rank，越大越靠后
        forward_order = ["pending", "sent", "returned", "matched", "discrepancy"]
        rank = {s: i for i, s in enumerate(forward_order)}
        # returned 的两个终态并列在其后
        rank["matched"] = 3
        rank["discrepancy"] = 3
        for src, targets in _ALLOWED_TRANSITIONS.items():
            for tgt in targets:
                assert rank[tgt] > rank[src], (
                    f"现状不应存在反向/同级边 {src}->{tgt}（撤回能力尚未引入）"
                )

    def test_status_rank_not_yet_defined(self):
        """撤回能力（Task 2.1）才引入 ``_STATUS_RANK``；当前基线尚不存在。"""
        assert not hasattr(confirmation_service, "_STATUS_RANK"), (
            "基线阶段 _STATUS_RANK 不应存在；若已存在说明撤回能力已引入，需更新 characterization 基线"
        )

    def test_reversal_targets_not_yet_defined(self):
        """同理，撤回目标表 ``_REVERSAL_TARGETS`` 亦尚未引入。"""
        assert not hasattr(confirmation_service, "_REVERSAL_TARGETS")

    def test_reverse_status_fn_not_yet_defined(self):
        """撤回服务函数 ``reverse_status`` 尚未引入（M1 才加）。"""
        assert not hasattr(confirmation_service, "reverse_status")


# ════════════════════════════════════════════════════════════════════════════
# Part 2 — transition_status 行为（非法抛中文 ValueError / 合法成功）
# ════════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def conf_session() -> AsyncSession:
    """仅创建 confirmations 表的内存会话（SQLite 默认不强制 FK，无需建关联表）。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.drop_all(sync_conn, tables=[Confirmation.__table__])
        )
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[Confirmation.__table__])
        )
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


class TestTransitionStatusBaseline:
    """锁定 ``transition_status``：合法转换成功、非法转换抛中文 ValueError。"""

    @pytest.mark.asyncio
    async def test_legal_transition_pending_to_sent_succeeds(self, conf_session):
        created = await create_confirmation(
            conf_session, FAKE_PROJECT_ID, {"confirm_type": "receivable", "counterparty": "甲公司"}
        )
        assert created["status"] == "pending"

        result = await transition_status(conf_session, uuid.UUID(created["id"]), "sent")
        assert result["status"] == "sent"

    @pytest.mark.asyncio
    async def test_full_forward_path_all_legal(self, conf_session):
        """整条前进链 pending→sent→returned→matched 全部合法成功。"""
        created = await create_confirmation(
            conf_session, FAKE_PROJECT_ID, {"confirm_type": "bank", "counterparty": "某银行"}
        )
        cid = uuid.UUID(created["id"])
        assert (await transition_status(conf_session, cid, "sent"))["status"] == "sent"
        assert (await transition_status(conf_session, cid, "returned"))["status"] == "returned"
        assert (await transition_status(conf_session, cid, "matched"))["status"] == "matched"

    @pytest.mark.asyncio
    async def test_returned_to_discrepancy_legal(self, conf_session):
        created = await create_confirmation(
            conf_session, FAKE_PROJECT_ID, {"confirm_type": "payable", "counterparty": "乙供应商"}
        )
        cid = uuid.UUID(created["id"])
        await transition_status(conf_session, cid, "sent")
        await transition_status(conf_session, cid, "returned")
        assert (await transition_status(conf_session, cid, "discrepancy"))["status"] == "discrepancy"

    @pytest.mark.asyncio
    async def test_illegal_skip_raises_chinese_valueerror(self, conf_session):
        """pending → returned 越级为非法，抛现状中文文案，且状态不变。"""
        created = await create_confirmation(
            conf_session, FAKE_PROJECT_ID, {"confirm_type": "receivable", "counterparty": "丙公司"}
        )
        cid = uuid.UUID(created["id"])

        with pytest.raises(ValueError) as exc:
            await transition_status(conf_session, cid, "returned")
        # 锁定现状文案（含中文状态名映射）
        assert str(exc.value) == "不能从『待发函』直接转为『已回函』"

        # 状态未被非法转换改动
        detail = await confirmation_service.get_confirmation(conf_session, cid)
        assert detail["status"] == "pending"

    @pytest.mark.asyncio
    async def test_illegal_reverse_from_terminal_raises(self, conf_session):
        """现状终态（matched）不可回退到 returned —— 非法，抛中文 ValueError。"""
        created = await create_confirmation(
            conf_session, FAKE_PROJECT_ID, {"confirm_type": "bank", "counterparty": "丁银行"}
        )
        cid = uuid.UUID(created["id"])
        await transition_status(conf_session, cid, "sent")
        await transition_status(conf_session, cid, "returned")
        await transition_status(conf_session, cid, "matched")

        with pytest.raises(ValueError) as exc:
            await transition_status(conf_session, cid, "returned")
        assert str(exc.value) == "不能从『相符』直接转为『已回函』"

        detail = await confirmation_service.get_confirmation(conf_session, cid)
        assert detail["status"] == "matched"

    @pytest.mark.asyncio
    async def test_transition_nonexistent_raises(self, conf_session):
        """不存在的函证 id → 现状中文 ValueError『函证记录不存在』。"""
        with pytest.raises(ValueError, match="函证记录不存在"):
            await transition_status(conf_session, uuid.uuid4(), "sent")


# ════════════════════════════════════════════════════════════════════════════
# Part 3 — extract_confirmation_reply 抽取 + 治理标记恒存在（不自动落库）
# ════════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def att_session() -> AsyncSession:
    """附件相关表的内存会话（镜像既有 test_metabase_attachments 的 db_session）。"""
    async with test_engine.begin() as conn:
        tables = [
            User.__table__,
            Project.__table__,
            WpIndex.__table__,
            WorkingPaper.__table__,
            Attachment.__table__,
            AttachmentWorkingPaper.__table__,
        ]
        await conn.run_sync(lambda sync_conn: Base.metadata.drop_all(sync_conn, tables=tables))
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_att_session(att_session: AsyncSession):
    """播种项目，供 create_attachment 使用（镜像既有 seeded_db）。"""
    project = Project(
        id=FAKE_PROJECT_ID,
        name="函证证据链基线",
        client_name="测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        created_by=FAKE_USER_ID,
    )
    att_session.add(project)
    await att_session.flush()
    return att_session


# 治理标记的两个恒定字段（锁定「OCR 结果不自动落库、须人工确认」的现状契约）
_GOVERNANCE_MARKER_KEYS = ("governed", "requires_human_confirmation")


def _assert_governance_marker(result: dict) -> None:
    """断言返回值恒含 governed=False / requires_human_confirmation=True。"""
    assert result["governed"] is False, "OCR 抽取结果不应标记为已治理（governed=False）"
    assert result["requires_human_confirmation"] is True, (
        "OCR 抽取结果须标记为需人工确认（requires_human_confirmation=True）"
    )


class TestExtractConfirmationReplyBaseline:
    """锁定 ``extract_confirmation_reply`` 抽取输出 + 治理标记恒存在。"""

    @pytest.mark.asyncio
    async def test_extract_full_fields(self, seeded_att_session):
        from app.services.attachment_service import AttachmentService

        svc = AttachmentService(seeded_att_session)
        att = await svc.create_attachment(
            FAKE_PROJECT_ID,
            {"file_name": "回函.pdf", "file_path": "/reply.pdf", "file_type": "pdf", "file_size": 100},
        )
        await seeded_att_session.flush()
        await svc.update_ocr_status(
            uuid.UUID(att["id"]),
            "completed",
            "致：致同会计师事务所\n"
            "经核对，截至2025年12月31日，贵公司在我行的存款余额为：¥1,234,567.89元。\n"
            "单位：中国工商银行北京分行\n"
            "日期：2026年1月15日",
        )
        await seeded_att_session.flush()

        result = await svc.extract_confirmation_reply(uuid.UUID(att["id"]))
        assert result["reply_amount"] == 1234567.89
        assert result["reply_date"] is not None
        assert result["reply_entity"] is not None
        assert result["confidence"] in ("high", "medium")
        _assert_governance_marker(result)

    @pytest.mark.asyncio
    async def test_extract_amount_only(self, seeded_att_session):
        from app.services.attachment_service import AttachmentService

        svc = AttachmentService(seeded_att_session)
        att = await svc.create_attachment(
            FAKE_PROJECT_ID,
            {"file_name": "回函2.pdf", "file_path": "/reply2.pdf", "file_type": "pdf", "file_size": 100},
        )
        await seeded_att_session.flush()
        await svc.update_ocr_status(uuid.UUID(att["id"]), "completed", "余额：500,000.00元")
        await seeded_att_session.flush()

        result = await svc.extract_confirmation_reply(uuid.UUID(att["id"]))
        assert result["reply_amount"] == 500000.00
        assert result["confidence"] == "medium"
        _assert_governance_marker(result)

    @pytest.mark.asyncio
    async def test_extract_empty_ocr(self, seeded_att_session):
        from app.services.attachment_service import AttachmentService

        svc = AttachmentService(seeded_att_session)
        att = await svc.create_attachment(
            FAKE_PROJECT_ID,
            {"file_name": "空回函.pdf", "file_path": "/empty.pdf", "file_type": "pdf", "file_size": 100},
        )
        await seeded_att_session.flush()

        result = await svc.extract_confirmation_reply(uuid.UUID(att["id"]))
        assert result["reply_amount"] is None
        assert result["confidence"] == "low"
        assert "OCR 文本为空" in result["message"]
        _assert_governance_marker(result)

    @pytest.mark.asyncio
    async def test_governance_marker_present_in_all_paths(self, seeded_att_session):
        """治理标记（不自动落库）在 空OCR / 部分命中 / 全命中 三条返回路径均恒存在。"""
        from app.services.attachment_service import AttachmentService

        svc = AttachmentService(seeded_att_session)

        ocr_texts = {
            "empty": "",
            "partial": "余额：88,888.88元",
            "full": "单位：某某公司\n余额：¥100,000.00元\n日期：2025年12月31日",
        }
        for label, text in ocr_texts.items():
            att = await svc.create_attachment(
                FAKE_PROJECT_ID,
                {
                    "file_name": f"{label}.pdf",
                    "file_path": f"/{label}.pdf",
                    "file_type": "pdf",
                    "file_size": 100,
                },
            )
            await seeded_att_session.flush()
            if text:
                await svc.update_ocr_status(uuid.UUID(att["id"]), "completed", text)
                await seeded_att_session.flush()

            result = await svc.extract_confirmation_reply(uuid.UUID(att["id"]))
            # 两个治理键恒存在且值恒定
            for key in _GOVERNANCE_MARKER_KEYS:
                assert key in result, f"[{label}] 返回值缺治理标记键 {key}"
            _assert_governance_marker(result)

    @pytest.mark.asyncio
    async def test_extract_nonexistent_raises(self, seeded_att_session):
        from app.services.attachment_service import AttachmentService

        svc = AttachmentService(seeded_att_session)
        with pytest.raises(ValueError, match="附件不存在"):
            await svc.extract_confirmation_reply(uuid.uuid4())
