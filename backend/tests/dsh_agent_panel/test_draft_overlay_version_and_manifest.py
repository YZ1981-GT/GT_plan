"""Chat 未保存草稿的**版本核对**与 **manifest 条目**（chat-host-draft-overlay Task 2）。

Requirements:
  - 2.4：服务端必须重新核对宿主当前业务版本；已变化则降级为只读提示，**不得静默使用**。
  - 6.2：开启后 manifest 出现未保存草稿条目，且带 ``baseline_version`` 与 ``content_hash``。
  - 6.3：草稿基于旧版本时纳入被拒绝并给出中文原因，不得静默使用旧草稿。
  - 6.1：缺省（不提交 overlay）时行为与现状一致。

Design: §3 服务端校验顺序（fail-closed）步骤 6~7 / §4 manifest 契约。

## 「宿主当前业务版本」是哪一列

``working_paper.updated_at``（真源常量
``app.services.ai_chat.draft_overlay.WORKPAPER_BUSINESS_VERSION_SOURCE``）。
理由与已知边界见该常量 docstring：``content_revision`` 在多条保存路径上不推进
（univer-save 传 None、checklist PUT 走裸 SQL），拿它判版本会 fail-open。

## 判据取向

* 「**模型没看到旧草稿**」用 ``plan.system_message`` 里搜索草稿哨兵串来证明，
  而不是"函数没抛异常"；同一个哨兵在 ``included`` 用例里必须**出现**
  （阳性对照，否则断言恒真）。
* 「**Run 仍成功**」用「``build_context_plan`` 正常返回 + 拿得到完整 manifest」证明，
  不是只看 status 字段。
* 「**token 计入预算**」用「同请求带 / 不带 overlay 的 ``total_used`` 差值恰好等于
  overlay 的 ``used_tokens``」证明，而不是只看字段存在。
* 「缺省不改变行为」用 **manifest 键集相等 + 无 overlay 条目** 证明。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.models.ai_models import ChatEngineName
from app.services.ai_chat.context_budget import ContextBudgetPolicy
from app.services.ai_chat.context_plan import (
    DRAFT_OVERLAY_SOURCE_PREFIX,
    _read_workpaper_business_version,
    build_context_plan,
)
from app.services.ai_chat.contracts import HostType
from app.services.ai_chat.draft_overlay import (
    WORKPAPER_BUSINESS_VERSION_SOURCE,
    DraftOverlayRef,
    decide_draft_overlay,
    normalize_business_version,
    versions_match,
)
from app.services.ai_chat.engine import AuthorizedChatRunRequest
from app.services.ai_chat.run_contract import CAPABILITIES_BY_ENGINE
from app.services.doc_ai_context_builder import ChatContext, SearchHit

#: 草稿哨兵串：出现在 system message 里就证明"模型看到了这份草稿"。
DRAFT_SENTINEL = "草稿哨兵-减值测试结论待补-应收款账龄需重算"
DRAFT_TEXT = f"B1-1 审定表底稿：{DRAFT_SENTINEL}；抽样 12 笔、差异 2 笔。"

#: 宿主打开编辑器时的业务版本（= 库里那一列的值）。
OPENED_VERSION = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)

#: 夹具用的宿主 ID。
HOST_ID = str(uuid4())

#: 是否需要真 PG（与 ``_fixtures.IS_PG`` 同口径，不 import 夹具以免无谓建库）。
IS_PG = app_settings.DATABASE_URL.startswith("postgresql")


# ---------------------------------------------------------------------------
# 夹具：一个只回答"当前业务版本"的 db 替身 + 既有装配依赖的桩
# ---------------------------------------------------------------------------


class _VersionDb:
    """只响应 ``SELECT working_paper.updated_at`` 的 db 替身。

    版本核对是**单列读**（design §3 步骤 6），因此这里精确到"被问到的语句"：
    ``execute()`` 记录 SQL，返回配置值。装配链上其余取数一律由 patch 桩掉
    （与 ``test_context_plan_wiring.py`` 相同的做法）。

    ``raises`` 用来模拟"读不出当前版本"（库异常）—— 那是 design §3
    "任何一步失败都不阻断整轮对话"要覆盖的分支。
    """

    def __init__(
        self, version: object = OPENED_VERSION, *, raises: Exception | None = None
    ) -> None:
        self._version = version
        self._raises = raises
        self.statements: list[str] = []

    async def execute(self, statement):  # noqa: ANN001, ANN201 — 结构替身
        self.statements.append(str(statement))
        if self._raises is not None:
            raise self._raises
        version = self._version

        class _Result:
            def scalar_one_or_none(_self) -> object:  # noqa: N805
                return version

        return _Result()


class _Builder:
    """最小的 ContextBuilder 替身：只提供装配需要的正文与预算。"""

    token_budget = 8000

    async def build(self, *, host, query, user, enforce_budget=True):  # noqa: ANN001, ANN201
        assert enforce_budget is False
        return ChatContext(
            doc_excerpt="【已保存正文】B1-1 审定表（库里的值）",
            project_summary="项目摘要",
            knowledge_hits=[
                SearchHit("knowledge_doc", str(uuid4()), "知识片段", 0.9, 0, "准则文档")
            ],
            citations=[],
            token_estimate=1,
        )

    def build_citations(self, hits):  # noqa: ANN001, ANN201
        return []


def _overlay(**overrides: object) -> DraftOverlayRef:
    payload: dict[str, object] = {
        "host_type": HostType.workpaper.value,
        "host_id": HOST_ID,
        "baseline_version": OPENED_VERSION.isoformat(),
        "content": DRAFT_TEXT,
    }
    payload.update(overrides)
    return DraftOverlayRef.model_validate(payload)


def _request(
    *,
    overlay: DraftOverlayRef | None = None,
    host_id: str = HOST_ID,
) -> AuthorizedChatRunRequest:
    host = SimpleNamespace(
        principal_id=uuid4(),
        project_id=uuid4(),
        year=2025,
        resource_type=HostType.workpaper,
        resource_id=host_id,
        display_label="B1-1 货币资金",
        project_tools_enabled=True,
    )
    return AuthorizedChatRunRequest(
        run_id=uuid4(),
        session_id=uuid4(),
        request_id=uuid4(),
        host=host,
        query="这份底稿的减值测试是否充分？",
        engine=ChatEngineName.native,
        capabilities=CAPABILITIES_BY_ENGINE[ChatEngineName.native],
        assistant_message_id=uuid4(),
        principal=SimpleNamespace(id=host.principal_id),
        draft_overlay=overlay,
    )


async def _plan(request, db):  # noqa: ANN001, ANN201
    """跑一遍真实 ``build_context_plan``，只桩掉与本判据无关的下游取数。"""
    with patch(
        "app.services.ai_chat.context_plan.resolve_review_mode",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.ai_chat.context_plan.load_mention_context",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.ai_chat.context_plan.AttachmentService.validate_for_run",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.ai_chat.context_plan.AiRunResourceService"
        ".load_project_attachment_context",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.ai_chat.context_plan.build_audit_relation_context",
        new=AsyncMock(return_value=[]),
    ):
        return await build_context_plan(db, request=request, context_builder=_Builder())


def _overlay_entries(manifest: dict) -> list[dict]:
    """manifest 里所有 ``draft_overlay:*`` 条目（含 denied/unavailable 分组）。"""
    out: list[dict] = []
    for key in ("included", "trimmed", "denied", "unavailable"):
        for row in manifest.get(key, []):
            if str(row.get("source_type", "")).startswith(DRAFT_OVERLAY_SOURCE_PREFIX):
                out.append(row)
    return out


# ===========================================================================
# 版本比较本身（纯函数）—— 假冲突与 fail-closed
# ===========================================================================


class TestVersionComparison:
    """**Validates: Requirements 2.4, 6.3**"""

    def test_same_instant_in_different_spellings_is_equal(self) -> None:
        """同一时刻的不同写法不得被判成过期（否则每次提问都"假冲突"）。

        PG ``timestamptz`` 取回是 ``+00:00``，前端 JSON 回来常是 ``Z`` 或带毫秒 ——
        纯字符串比会把它们判成两个版本，从而把**新鲜草稿**误拒绝。
        """
        assert versions_match("2026-11-15T10:00:00+00:00", "2026-11-15T10:00:00Z")
        assert versions_match("2026-11-15T18:00:00+08:00", "2026-11-15T10:00:00Z")
        assert versions_match(OPENED_VERSION.isoformat(), OPENED_VERSION)

    def test_different_instant_is_rejected(self) -> None:
        assert not versions_match(
            OPENED_VERSION.isoformat(), OPENED_VERSION + timedelta(seconds=1)
        )

    @pytest.mark.parametrize("current", [None, "", "   "])
    def test_unknown_current_version_is_fail_closed(self, current: object) -> None:
        """读不出当前版本时**不得**判为一致 —— 那是无法证明新鲜却放行的 fail-open。"""
        assert not versions_match(OPENED_VERSION.isoformat(), current)

    def test_empty_baseline_is_fail_closed(self) -> None:
        assert not versions_match("", OPENED_VERSION)

    def test_normalize_is_idempotent(self) -> None:
        once = normalize_business_version(OPENED_VERSION)
        assert normalize_business_version(once) == once

    def test_unparsable_text_is_kept_verbatim(self) -> None:
        """认不出的字符串原样保留 ⇒ 与任何真实时间都不等（宁可拒绝，不猜）。"""
        assert normalize_business_version("not-a-timestamp") == "not-a-timestamp"
        assert not versions_match("not-a-timestamp", OPENED_VERSION)


# ===========================================================================
# 版本一致 → included，且 token 计入预算
# ===========================================================================


class TestMatchingVersionIsIncluded:
    """**Validates: Requirements 6.2**"""

    async def test_matching_version_yields_included_entry_with_hash_and_baseline(
        self,
    ) -> None:
        plan = await _plan(_request(overlay=_overlay()), _VersionDb(OPENED_VERSION))

        entries = _overlay_entries(plan.manifest)
        assert len(entries) == 1, plan.manifest
        entry = entries[0]
        assert entry["status"] == "included"
        assert entry["source_type"] == "draft_overlay:workpaper"
        assert entry["source_id"] == HOST_ID
        # 需求 6.2：两个键都必须带。
        assert entry["content_hash"].startswith("sha256:")
        assert entry["baseline_version"] == OPENED_VERSION.isoformat()
        assert entry["used_tokens"] > 0
        assert plan.manifest["draft_overlay_included"] is True

    async def test_draft_reaches_system_message_when_included(self) -> None:
        """阳性对照：``included`` 时哨兵**必须**出现在 system message 里。

        没有这一条，"``denied`` 时哨兵不在"的断言可能是恒真的（装配从来没接上草稿）。
        """
        plan = await _plan(_request(overlay=_overlay()), _VersionDb(OPENED_VERSION))
        assert DRAFT_SENTINEL in plan.system_message
        assert "【当前未保存草稿】" in plan.system_message
        # 已保存正文仍在：草稿是补充，不替代宿主正文。
        assert "【已保存正文】" in plan.system_message
        # 定界块仍恰好一个（草稿没有额外开一段未定界内容）。
        assert plan.system_message.count("<<<平台上下文数据 开始>>>") == 1

    async def test_used_tokens_are_counted_into_the_shared_budget(self) -> None:
        """overlay 的 token **真的**计入了同一个预算（差值与条目 used_tokens 相等）。"""
        baseline_plan = await _plan(_request(), _VersionDb(OPENED_VERSION))
        overlay_plan = await _plan(_request(overlay=_overlay()), _VersionDb(OPENED_VERSION))

        overlay_entry = _overlay_entries(overlay_plan.manifest)[0]
        delta = overlay_plan.manifest["total_used"] - baseline_plan.manifest["total_used"]
        assert delta == overlay_entry["used_tokens"], (
            f"total_used 差值 {delta} ≠ overlay 条目 used_tokens "
            f"{overlay_entry['used_tokens']}：token 没有计入同一次预算"
        )

    async def test_oversized_draft_is_trimmed_not_silently_dropped(self) -> None:
        """超预算的草稿标 ``trimmed``（仍纳入一部分），不静默整份丢掉。"""
        huge = DRAFT_TEXT + "补" * 20000
        plan = await _plan(_request(overlay=_overlay(content=huge)), _VersionDb(OPENED_VERSION))

        entries = _overlay_entries(plan.manifest)
        assert len(entries) == 1
        assert entries[0]["status"] == "trimmed"
        assert entries[0]["reason"] == "budget_exceeded"
        assert entries[0]["used_tokens"] > 0

    async def test_draft_does_not_crowd_out_the_saved_host_content(self) -> None:
        """草稿最多占宿主正文槽位的一半 —— 已保存正文必须仍有预算。"""
        huge = DRAFT_TEXT + "补" * 40000
        plan = await _plan(_request(overlay=_overlay(content=huge)), _VersionDb(OPENED_VERSION))
        assert "【已保存正文】" in plan.system_message, (
            "草稿把宿主正文挤没了：草稿是补充而非替代"
        )


# ===========================================================================
# 版本过期 → denied（中文原因），Run 仍成功，模型看不到旧草稿
# ===========================================================================


class TestStaleVersionIsDenied:
    """**Validates: Requirements 2.4, 6.3**"""

    async def test_stale_draft_is_denied_and_never_reaches_the_model(self) -> None:
        """核心判据：过期 → ``denied`` + 中文原因 + **正文不进 system message**。"""
        newer = OPENED_VERSION + timedelta(hours=1)
        plan = await _plan(_request(overlay=_overlay()), _VersionDb(newer))

        entries = _overlay_entries(plan.manifest)
        assert len(entries) == 1, plan.manifest
        entry = entries[0]
        assert entry["status"] == "denied"
        assert entry["reason"], "denied 必须带中文原因（需求 6.3）"
        assert "旧版本" in entry["reason"] and "请先保存或刷新" in entry["reason"]

        # 模型侧：旧草稿一个字都不能进去。
        assert DRAFT_SENTINEL not in plan.system_message
        assert "【当前未保存草稿】" not in plan.system_message
        # 顶栏标记如实为 False。
        assert plan.manifest["draft_overlay_included"] is False

    async def test_run_still_succeeds_when_overlay_is_denied(self) -> None:
        """拒绝**不阻断**整轮 Run：装配照常返回，宿主正文与知识仍在。"""
        newer = OPENED_VERSION + timedelta(days=1)
        plan = await _plan(_request(overlay=_overlay()), _VersionDb(newer))

        assert "【已保存正文】" in plan.system_message
        assert "知识片段" in plan.system_message
        assert plan.manifest["manifest_version"] == "context-plan-v1"
        # denied 条目不计入预算（没有把正文算成"用过"）。
        assert "used_tokens" not in _overlay_entries(plan.manifest)[0]

    async def test_denied_entry_still_carries_hash_and_baseline_for_audit(self) -> None:
        """拒绝时也要能看出"拒绝的是哪一份草稿、基于哪一版"（只存派生量，不含正文）。"""
        newer = OPENED_VERSION + timedelta(minutes=5)
        plan = await _plan(_request(overlay=_overlay()), _VersionDb(newer))

        entry = _overlay_entries(plan.manifest)[0]
        assert entry["content_hash"].startswith("sha256:")
        assert entry["baseline_version"] == OPENED_VERSION.isoformat()
        # 需求 4.3：manifest 只存 hash/长度，不含正文。
        assert DRAFT_SENTINEL not in str(plan.manifest)

    async def test_version_read_failure_degrades_to_denied_not_an_exception(self) -> None:
        """读版本失败（库异常）→ ``denied``，**不是**整轮 Run 失败。

        design §3：「任何一步失败都不阻断整轮对话」。若这里把异常抛出去，engine 的
        ``except Exception`` 会把它变成 ``context_build_failed`` ——
        用户为多问一句草稿反而彻底问不了话。
        """
        plan = await _plan(_request(overlay=_overlay()), _VersionDb(raises=RuntimeError("db down")))

        entries = _overlay_entries(plan.manifest)
        assert len(entries) == 1
        assert entries[0]["status"] == "denied"
        assert "读不到" in entries[0]["reason"]
        assert DRAFT_SENTINEL not in plan.system_message
        assert "【已保存正文】" in plan.system_message

    async def test_missing_workpaper_row_is_denied(self) -> None:
        """行不存在（版本读到 None）→ ``denied``，同样不抛。"""
        plan = await _plan(_request(overlay=_overlay()), _VersionDb(None))
        assert _overlay_entries(plan.manifest)[0]["status"] == "denied"
        assert DRAFT_SENTINEL not in plan.system_message

    async def test_illegal_host_id_is_denied_without_touching_the_database(self) -> None:
        """非法宿主 ID 直接降级，不发 SQL（避免把脏字符串拼进查询）。"""
        db = _VersionDb(OPENED_VERSION)
        overlay = _overlay(host_id="not-a-uuid")
        plan = await _plan(_request(overlay=overlay, host_id="not-a-uuid"), db)

        assert _overlay_entries(plan.manifest)[0]["status"] == "denied"
        assert db.statements == [], f"非法 ID 不该发 SQL：{db.statements}"


# ===========================================================================
# 缺省（不提交 overlay）→ manifest 与既有行为一致
# ===========================================================================


class TestAbsentOverlayLeavesManifestUnchanged:
    """**Validates: Requirements 6.1**"""

    async def test_no_overlay_entry_and_no_top_level_flag(self) -> None:
        """不提交 overlay 时：manifest 里既没有条目，也**没有**那个顶层键。

        🔴 刻意断言"键不存在"而不是"键为 False"：回归一个恒 False 的新键同样是对外
        契约变更，前端无法据此区分"后端不认 overlay"与"后端认但没纳入"。
        """
        plan = await _plan(_request(), _VersionDb(OPENED_VERSION))
        assert _overlay_entries(plan.manifest) == []
        assert "draft_overlay_included" not in plan.manifest
        assert DRAFT_SENTINEL not in plan.system_message
        assert "【当前未保存草稿】" not in plan.system_message

    async def test_no_version_query_is_issued_without_overlay(self) -> None:
        """不提交 overlay 时**零**额外查询（不得为判定而预读版本）。"""
        db = _VersionDb(OPENED_VERSION)
        await _plan(_request(), db)
        assert db.statements == [], f"缺省路径不该查工作版本：{db.statements}"

    async def test_manifest_key_set_equals_pre_overlay_contract(self) -> None:
        """顶层键集与加 overlay 前**逐键相同**（无新增键）。"""
        plan = await _plan(_request(), _VersionDb(OPENED_VERSION))
        allowed = {
            "manifest_version",
            "total_budget",
            "total_used",
            "citation_count",
            "project_tools_enabled",
            "review_mode",
            # 既有分组键（与加 overlay 前一致，按有无条目出现）
            "included",
            "trimmed",
            "denied",
            "unavailable",
        }
        assert set(plan.manifest) <= allowed, (
            f"缺省路径的 manifest 多出了键：{sorted(set(plan.manifest) - allowed)}"
        )

    async def test_non_overlay_entry_serialization_has_no_overlay_keys(self) -> None:
        """非 overlay 条目序列化后**不带** ``content_hash`` / ``baseline_version``。

        两个新字段必须只在有值时出现，否则既有 manifest 每条都多两键 ——
        既有消费者（前端 inspector）与快照守卫都会看到无关 diff。
        """
        plan = await _plan(_request(), _VersionDb(OPENED_VERSION))
        rows = [
            row
            for key in ("included", "trimmed", "denied", "unavailable")
            for row in plan.manifest.get(key, [])
        ]
        assert rows, "缺省路径应至少有宿主正文条目"
        for row in rows:
            assert "content_hash" not in row, row
            assert "baseline_version" not in row, row


# ===========================================================================
# 判定函数本身（不经装配）—— 拒绝理由的中文措辞
# ===========================================================================


class TestDecisionReasonIsChineseAndActionable:
    """**Validates: Requirements 6.3**"""

    def test_reason_names_both_versions(self) -> None:
        newer = OPENED_VERSION + timedelta(hours=2)
        decision = decide_draft_overlay(_overlay(), current_version=newer)
        assert decision.status == "denied"
        assert OPENED_VERSION.isoformat() in decision.reason
        assert newer.isoformat() in decision.reason

    def test_included_decision_has_no_reason(self) -> None:
        decision = decide_draft_overlay(_overlay(), current_version=OPENED_VERSION)
        assert decision.status == "included"
        assert decision.reason == ""
        assert decision.included is True

    def test_label_uses_display_name_when_available(self) -> None:
        """manifest 展示名取已授权的 display_label（design §4 的「底稿 B1-1」形态）。"""
        decision = decide_draft_overlay(
            _overlay(), current_version=OPENED_VERSION, host_label="B1-1 货币资金"
        )
        assert decision.label == "当前未保存草稿（B1-1 货币资金）"

    def test_label_falls_back_to_host_id(self) -> None:
        decision = decide_draft_overlay(_overlay(), current_version=OPENED_VERSION)
        assert HOST_ID in decision.label


# ===========================================================================
# 版本来源常量（前端 openedBaselineVersion 必须镜像同一列）
# ===========================================================================


class TestBusinessVersionSourceIsDeclared:
    """**Validates: Requirements 2.4**（版本来源单一真源，Task 4 据此镜像）"""

    def test_source_names_the_workpaper_updated_at_column(self) -> None:
        assert WORKPAPER_BUSINESS_VERSION_SOURCE == "working_paper.updated_at"

    async def test_assembly_reads_exactly_that_column(self) -> None:
        """装配期那条 SELECT **只**读 ``working_paper.updated_at``。

        判据落在 SQL 文本上而不是"函数被调用过"：若有人把版本来源改成
        ``content_revision``（多路径不推进，会 fail-open），本条会红。
        """
        db = _VersionDb(OPENED_VERSION)
        await _plan(_request(overlay=_overlay()), db)

        assert len(db.statements) == 1, db.statements
        sql = db.statements[0]
        assert "working_paper.updated_at" in sql, sql
        assert "content_revision" not in sql, f"版本来源漂移：{sql}"
        assert "is_deleted" in sql, "软删底稿不得作为版本来源"


# ===========================================================================
# 真实 PG：版本核对读的是库里那一列的真值
# ===========================================================================


@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL（未保存草稿版本核对）")
class TestVersionReadAgainstRealDatabase:
    """**Validates: Requirements 2.4**（真库：读到的是宿主真实业务版本）

    SQL 文本对账能防"改了列"，但防不住"读到了别的行 / 漏了软删过滤"；下面两个用例用
    真实 ``working_paper`` 行把这两件事一起钉住。全程在一个回滚事务里，不污染共享库。
    """

    async def _with_fixture(self, scenario):  # noqa: ANN001, ANN202
        from tests.dsh_agent_panel._fixtures import build_access_fixture

        engine = create_async_engine(app_settings.DATABASE_URL)
        conn = await engine.connect()
        trans = await conn.begin()
        session = AsyncSession(bind=conn)
        try:
            fixture = await build_access_fixture(session)
            return await scenario(session, fixture)
        finally:
            await session.close()
            await trans.rollback()
            await conn.close()
            await engine.dispose()

    async def test_reads_the_fixture_workpaper_updated_at(self) -> None:
        async def _scenario(session, fixture):  # noqa: ANN001, ANN202
            wp = fixture.wp_d_file
            expected = wp.updated_at
            assert expected is not None, "夹具底稿应带 updated_at"

            actual = await _read_workpaper_business_version(session, str(wp.id))
            assert normalize_business_version(actual) == normalize_business_version(
                expected
            ), f"读到的版本 {actual!r} ≠ 库里的 {expected!r}"

            # 软删的底稿不得作为版本来源（否则删掉后仍能"核对通过"）。
            other = fixture.wp_e_file
            await session.execute(
                sa.text("UPDATE working_paper SET is_deleted = true WHERE id = :wp"),
                {"wp": str(other.id)},
            )
            assert (
                await _read_workpaper_business_version(session, str(other.id)) is None
            ), "软删底稿仍然读出了业务版本"

        await self._with_fixture(_scenario)

    async def test_matching_baseline_from_real_row_yields_included(self) -> None:
        async def _scenario(session, fixture):  # noqa: ANN001, ANN202
            wp = fixture.wp_d_file
            baseline = normalize_business_version(
                await _read_workpaper_business_version(session, str(wp.id))
            )
            assert baseline, "真库应读出非空业务版本"

            decision = decide_draft_overlay(
                _overlay(baseline_version=baseline), current_version=baseline
            )
            assert decision.status == "included"

            # 同一份草稿，基线早 1 秒 → 必须拒绝（真库值参与的负向对照）。
            stale = decide_draft_overlay(
                _overlay(
                    baseline_version=(OPENED_VERSION - timedelta(seconds=1)).isoformat()
                ),
                current_version=baseline,
            )
            assert stale.status == "denied"

        await self._with_fixture(_scenario)


# ===========================================================================
# 预算策略自检：overlay 槽位不得让既有分配超出总预算
# ===========================================================================


class TestBudgetPolicyStillBalanced:
    """**Validates: Requirements 6.2**（token 计入同一预算，且不超总额）"""

    @pytest.mark.parametrize("review_mode", [True, False])
    def test_overlay_cap_plus_other_slots_stays_within_total(
        self, review_mode: bool
    ) -> None:
        """overlay 的上限取自 ``doc_excerpt`` 槽位，不得让总量越过总预算。"""
        policy = ContextBudgetPolicy(total_budget=8000, review_mode=review_mode)
        alloc = policy.allocate()
        summary = min(int(policy.total_budget * 0.10), alloc.doc_excerpt)
        overlay_cap = max(0, alloc.doc_excerpt - summary) // 2
        slots = (
            summary
            + overlay_cap
            + alloc.review_prompt
            + alloc.mentions
            + alloc.attachments
            + alloc.knowledge
        )
        assert slots <= alloc.total, f"槽位总和 {slots} 超过总预算 {alloc.total}"
