# Feature: dsh-agent-panel-integration — Task 23 地址 mention 授权、脱敏与跳转
"""地址坐标 mention 的四边契约守卫。

Requirements: 6.1, 6.6, 6.7
Properties:
  - **Property 15（地址索引真源与失效联动）**：AddressCoordinateIndexSource 的输出文本
    只由源 AddressEntry/ACNR 字段生成；源变更触发后索引更新或标 stale。
    **Validates: Requirements 6.2, 6.3, 6.6**
  - **Property 17（地址权限与脱敏一致）**：未授权用户不能通过 address 搜索或直接 ID
    获得 label/current value；授权结果中的当前值经过与 native chat 相同的角色脱敏。
    **Validates: Requirements 6.1, 6.7**

四边契约：
  源坐标 → IndexSource → runtime search → mention → context
  每一边的行为必须满足不变量；不只检查索引表"存在"。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.address_mention import (
    AddressMentionDetail,
    build_address_manifest_entry,
    check_address_stale,
    mask_address_value,
    resolve_address_mention,
)
from app.services.ai_chat.contracts import (
    AccessDecision,
    AiChatAction,
    AiChatDenialCode,
    HostRef,
    HostType,
    ResourceType,
)
from app.services.ai_chat.context_budget import ContextManifestEntry
from app.services.ai_chat.mention_service import (
    MentionCandidate,
    MentionSearchService,
)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@dataclass
class MockAddressEntry:
    """模拟 AddressEntry 用于测试。"""
    uri: str = "report://BS/BS-002#期末"
    domain: str = "report"
    source: str = "BS"
    path: str = "BS-002"
    cell: str = "期末"
    label: str = "资产负债表 > 货币资金 > 期末"
    value: float | None = 12345678.90
    row_code: str = "BS-002"
    account_code: str = "1001"
    note_section: str = ""
    wp_code: str = "A1"
    jump_route: str = "/reports/balance_sheet"
    formula_ref: str = "TB('1001','审定数')"
    tags: list = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = ["资产", "货币资金"]


def _make_host_decision(
    project_id: UUID | None = None,
    principal_id: UUID | None = None,
) -> AccessDecision:
    """创建已授权的宿主决策。"""
    return AccessDecision(
        allowed=True,
        principal_id=principal_id or uuid4(),
        project_id=project_id or uuid4(),
        cycle_scope=frozenset(["D", "E", "F"]),
        allowed_actions=frozenset({"read", "search"}),
        scope_unbounded=False,
    )


def _make_user(role: str = "auditor", user_id: UUID | None = None):
    """创建测试用户。"""
    u = MagicMock()
    u.id = user_id or uuid4()
    u.role = role
    return u


# ---------------------------------------------------------------------------
# Edge 1: 源坐标 → IndexSource 文本生成
# ---------------------------------------------------------------------------


class TestEdge1SourceToIndexSource:
    """源坐标 → IndexSource：文本只由 AddressEntry/ACNR 字段生成（Property 15）。"""

    def test_index_text_only_from_address_fields(self):
        """Property 15: 索引文本只来自已知 AddressEntry 字段。

        **Validates: Requirements 6.2, 6.3**
        """
        from app.services.ai_chat.address_index_source import _build_index_text

        entry = MockAddressEntry()
        text = _build_index_text(entry)

        # 文本必须非空
        assert text, "索引文本不能为空"
        # 文本中的内容必须源自 entry 的字段
        assert entry.label in text
        assert entry.domain in text or f"[{entry.domain}]" in text
        assert entry.wp_code in text or f"底稿:{entry.wp_code}" in text

    def test_index_text_empty_entry_returns_empty(self):
        """无字段的空条目应生成空文本（不生成"垃圾文本"）。"""
        from app.services.ai_chat.address_index_source import _build_index_text

        empty = MagicMock()
        empty.label = ""
        empty.display_name = ""
        empty.domain = ""
        empty.wp_code = ""
        empty.sheet_code = ""
        empty.sheet_name = ""
        empty.formula_ref = ""
        empty.expression = ""
        empty.description = ""
        empty.note = ""

        text = _build_index_text(empty)
        assert text == ""

    def test_legacy_index_text_only_from_known_fields(self):
        """Legacy 索引文本同样只来自 AddressEntry 字段。"""
        from app.services.ai_chat.address_index_source import _build_legacy_index_text

        entry = MockAddressEntry()
        text = _build_legacy_index_text(entry)

        assert text, "Legacy 索引文本不能为空"
        assert entry.label in text


# ---------------------------------------------------------------------------
# Edge 2: IndexSource → runtime search（embedding/stale）
# ---------------------------------------------------------------------------


class TestEdge2IndexSourceToSearch:
    """IndexSource → runtime search：search strict source_type + stale 检测。"""

    def test_address_coordinate_source_type_constant(self):
        """源类型常量与迁移 enum 值一致（Property 15）。

        **Validates: Requirements 6.2**
        """
        from app.services.ai_chat.address_index_source import (
            ADDRESS_COORDINATE_SOURCE_TYPE,
        )

        assert ADDRESS_COORDINATE_SOURCE_TYPE == "address_coordinate"

    @pytest.mark.asyncio
    async def test_search_address_returns_proper_fields(self):
        """Mention 搜索返回稳定 addr_id、label、jump_route（Req 6.1）。

        🔴 候选粒度已从**单元格级**改为**表级**：一条候选 = 一张数据表，
        引用后 AI 拿整表自行分析。因此 ``id`` 是表级 URI（``tb://1001``，无
        ``#cell``），``label`` 不含列名。粒度本身的守卫见
        ``test_mention_address_table_level.py``。

        **Validates: Requirements 6.1**
        """
        project_id = uuid4()
        tb_entry = MockAddressEntry(
            uri="tb://1001#审定数",
            domain="tb",
            source="1001",
            path="",
            cell="审定数",
            label="试算表 > 1001 库存现金 > 审定数",
            jump_route="/projects/x/trial-balance?year=2025&highlight=1001",
        )

        mock_db = AsyncMock()
        with patch("app.services.address_registry.address_registry") as mock_registry:
            # 表级聚合走 get_domain（按域整体取，再把 cell 维度聚合掉）
            async def _get_domain(db, pid, year, template_type, domain):
                return [tb_entry] if domain == "tb" else []

            mock_registry.get_domain = AsyncMock(side_effect=_get_domain)

            svc = MentionSearchService(mock_db)
            results = await svc._search_address("%库存现金%", project_id, 10, 2025)

        assert len(results) >= 1
        candidate = results[0]
        assert candidate.type == "address"
        assert candidate.id  # 稳定 addr_id 不为空
        assert candidate.label  # label 不为空
        assert candidate.jump_route  # jump_route 不为空
        # 表级契约：id 无单元格片段、label 不以列名结尾
        assert "#" not in candidate.id
        assert candidate.id == "tb://1001"
        assert candidate.label == "试算表 > 1001 库存现金"

    @pytest.mark.asyncio
    async def test_search_address_empty_project_returns_empty(self):
        """无项目时地址搜索返回空（不暴露任何数据）。"""
        mock_db = AsyncMock()
        svc = MentionSearchService(mock_db)
        results = await svc._search_address("%test%", None, 10, 2025)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_address_error_returns_empty_not_raises(self):
        """域构建异常返回空列表（semantic_unavailable 语义），不抛异常（Req 6.6）。

        **Validates: Requirements 6.6**
        """
        mock_db = AsyncMock()
        with patch("app.services.address_registry.address_registry") as mock_registry:
            mock_registry.get_domain = AsyncMock(
                side_effect=RuntimeError("registry down")
            )

            svc = MentionSearchService(mock_db)
            results = await svc._search_address("%test%", uuid4(), 10, 2025)

        assert results == []


# ---------------------------------------------------------------------------
# Edge 3: runtime search → mention（授权过滤）
# ---------------------------------------------------------------------------


class TestEdge3SearchToMention:
    """runtime search → mention：未授权用户不能搜索到 label 或当前值（Property 17）。"""

    @pytest.mark.asyncio
    async def test_unauthorized_user_gets_no_address_detail(self):
        """Property 17: 未授权用户通过 resolve_address_mention 返回 None。

        **Validates: Requirements 6.7**
        """
        mock_db = AsyncMock()
        user = _make_user("assistant")
        host_decision = _make_host_decision()

        # Mock authorize_resource 返回拒绝
        with patch.object(
            ResourceAccessResolver,
            "authorize_resource",
            new_callable=AsyncMock,
            return_value=AccessDecision(
                allowed=False,
                principal_id=user.id,
                project_id=host_decision.project_id,
                denial_code=AiChatDenialCode.access_denied.value,
            ),
        ):
            result = await resolve_address_mention(
                mock_db,
                user=user,
                host_decision=host_decision,
                addr_id="TB('1001','审定数')",
                project_id=host_decision.project_id,
            )

        # 未授权 → None（不泄露 label/value）
        assert result is None

    @pytest.mark.asyncio
    async def test_authorized_user_gets_address_detail(self):
        """授权用户通过 resolve_address_mention 获得完整详情。

        **Validates: Requirements 6.1**
        """
        mock_db = AsyncMock()
        user = _make_user("partner")
        project_id = uuid4()
        host_decision = _make_host_decision(project_id=project_id, principal_id=user.id)
        entry = MockAddressEntry()

        with patch.object(
            ResourceAccessResolver,
            "authorize_resource",
            new_callable=AsyncMock,
            return_value=AccessDecision(
                allowed=True,
                principal_id=user.id,
                project_id=project_id,
                cycle_scope=frozenset(["D"]),
                allowed_actions=frozenset({"read", "search"}),
            ),
        ), patch(
            "app.services.ai_chat.address_mention._load_address_entry",
            new_callable=AsyncMock,
            return_value={
                "label": entry.label,
                "domain": entry.domain,
                "uri": entry.uri,
                "formula_ref": entry.formula_ref,
                "jump_route": entry.jump_route,
                "value": entry.value,
                "wp_code": entry.wp_code,
                "account_code": entry.account_code,
                "note_section": entry.note_section,
            },
        ), patch(
            "app.services.ai_chat.address_mention._get_address_version",
            new_callable=AsyncMock,
            return_value="v1.0",
        ), patch(
            "app.services.ai_chat.address_mention.check_address_stale",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await resolve_address_mention(
                mock_db,
                user=user,
                host_decision=host_decision,
                addr_id=entry.formula_ref,
                project_id=project_id,
            )

        assert result is not None
        assert result.addr_id == entry.formula_ref
        assert result.label == entry.label
        assert result.domain == entry.domain
        assert result.uri == entry.uri
        assert result.jump_route == entry.jump_route
        assert result.version == "v1.0"
        assert result.stale is False
        # partner 不脱敏
        assert result.current_value == str(entry.value)

    @pytest.mark.asyncio
    async def test_resolve_with_no_project_returns_none(self):
        """无项目绑定时 resolve 返回 None。"""
        mock_db = AsyncMock()
        user = _make_user()
        host_decision = _make_host_decision()

        result = await resolve_address_mention(
            mock_db,
            user=user,
            host_decision=host_decision,
            addr_id="TB('1001','审定数')",
            project_id=None,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Edge 4: mention → context（脱敏 + manifest stale/version/unavailable）
# ---------------------------------------------------------------------------


class TestEdge4MentionToContext:
    """mention → context：manifest 展示 version/stale/unavailable（Req 6.6）。"""

    def test_masking_partner_no_mask(self):
        """Property 17: partner 角色不脱敏当前值。

        **Validates: Requirements 6.7**
        """
        value = 50_000_000.0
        result = mask_address_value(value, "partner")
        assert result == str(value)

    def test_masking_admin_no_mask(self):
        """admin 角色不脱敏当前值。"""
        value = 99_999_999.0
        result = mask_address_value(value, "admin")
        assert result == str(value)

    def test_masking_manager_above_threshold(self):
        """Property 17: manager 超阈值脱敏为区间描述。

        **Validates: Requirements 6.7**
        """
        from app.services.export_mask_service import AMOUNT_THRESHOLD

        value = AMOUNT_THRESHOLD + 1
        result = mask_address_value(value, "manager")
        assert "万" in result  # 区间描述包含"万"
        assert str(value) not in result  # 不含原始值

    def test_masking_manager_below_threshold(self):
        """manager 未超阈值不脱敏。"""
        value = 100.0
        result = mask_address_value(value, "manager")
        assert result == str(value)

    def test_masking_assistant_above_threshold(self):
        """Property 17: assistant 超阈值完全脱敏为 ***。

        **Validates: Requirements 6.7**
        """
        from app.services.export_mask_service import AMOUNT_THRESHOLD

        value = AMOUNT_THRESHOLD + 1
        result = mask_address_value(value, "assistant")
        assert result == "***"

    def test_masking_unknown_role_fail_closed(self):
        """Property 17: 未知角色 fail-closed → 完全脱敏。

        **Validates: Requirements 6.7**
        """
        result = mask_address_value(50_000_000.0, "unknown_role")
        assert result == "***"

    def test_masking_none_value_returns_none(self):
        """None 值直接返回 None。"""
        result = mask_address_value(None, "assistant")
        assert result is None

    def test_masking_non_numeric_value(self):
        """非数值字符串不脱敏（非敏感数据）。"""
        result = mask_address_value("文本内容", "assistant")
        assert result == "文本内容"

    def test_manifest_entry_included_with_version(self):
        """已授权+非 stale → included + version 展示。

        **Validates: Requirements 6.6**
        """
        detail = AddressMentionDetail(
            addr_id="TB('1001','审定数')",
            label="试算表 > 库存现金 > 审定数",
            domain="tb",
            uri="tb://1001#审定数",
            formula_ref="TB('1001','审定数')",
            jump_route="/trial-balance",
            current_value="12345.00",
            version="v2.1",
            stale=False,
        )

        entry = build_address_manifest_entry(detail, detail.addr_id, used_tokens=50)

        assert entry.status == "included"
        assert entry.version == "v2.1"
        assert entry.stale is False
        assert entry.source_type == "address"
        assert entry.source_id == detail.addr_id

    def test_manifest_entry_stale_shows_reason(self):
        """stale 条目 manifest 有过期提示（Req 6.6）。

        **Validates: Requirements 6.6**
        """
        detail = AddressMentionDetail(
            addr_id="TB('1001','审定数')",
            label="试算表 > 库存现金 > 审定数",
            domain="tb",
            uri="tb://1001#审定数",
            formula_ref="TB('1001','审定数')",
            jump_route="",
            current_value="12345.00",
            version="v1.0",
            stale=True,
        )

        entry = build_address_manifest_entry(detail, detail.addr_id)

        assert entry.status == "included"
        assert entry.stale is True
        assert entry.version == "v1.0"
        assert "过期" in entry.reason

    def test_manifest_entry_unavailable_when_none(self):
        """未授权/不存在 → unavailable（不泄露 label）。

        **Validates: Requirements 6.7**
        """
        entry = build_address_manifest_entry(None, "TB('9999','审定数')")

        assert entry.status == "unavailable"
        assert entry.label == ""  # 不泄露 label
        assert "不可用" in entry.reason or "未授权" in entry.reason


# ---------------------------------------------------------------------------
# ResourceAccessResolver 地址授权判定
# ---------------------------------------------------------------------------


class TestAddressAuthorization:
    """ResourceAccessResolver 对 address 类型的授权判定。"""

    @pytest.mark.asyncio
    async def test_address_invalid_id_rejected(self):
        """空/空白 address ID 返回 invalid_resource_id。"""
        mock_db = AsyncMock()
        resolver = ResourceAccessResolver(mock_db)
        user = _make_user("auditor")
        host_decision = _make_host_decision(principal_id=user.id)

        # 需要 mock role_allows_action 因为 "auditor" 需要走 CAPABILITY_MATRIX
        with patch(
            "app.services.ai_chat.access.role_allows_action",
            return_value=True,
        ):
            decision = await resolver.authorize_resource(
                user, host_decision, ResourceType.address, "", AiChatAction.search
            )
        assert not decision.allowed
        assert decision.denial_code == AiChatDenialCode.invalid_resource_id.value

    @pytest.mark.asyncio
    async def test_address_no_project_rejected(self):
        """无项目绑定时地址授权拒绝。"""
        mock_db = AsyncMock()
        resolver = ResourceAccessResolver(mock_db)
        user = _make_user("auditor")
        # host_decision 无项目
        host_decision = AccessDecision(
            allowed=True,
            principal_id=user.id,
            project_id=None,
            cycle_scope=frozenset(),
            allowed_actions=frozenset({"read", "search"}),
        )

        with patch(
            "app.services.ai_chat.access.role_allows_action",
            return_value=True,
        ):
            decision = await resolver.authorize_resource(
                user, host_decision, ResourceType.address,
                "TB('1001','审定数')", AiChatAction.search
            )
        assert not decision.allowed

    @pytest.mark.asyncio
    async def test_address_valid_id_accepted_structure(self):
        """合法字符串 ID 不被 coerce_uuid 拒绝（地址 ID 非 UUID）。"""
        mock_db = AsyncMock()
        resolver = ResourceAccessResolver(mock_db)
        user = _make_user("auditor")
        project_id = uuid4()
        host_decision = _make_host_decision(
            project_id=project_id, principal_id=user.id
        )

        # mock role_allows_action, _resolve_scope 和 _is_project_member
        with patch(
            "app.services.ai_chat.access.role_allows_action",
            return_value=True,
        ), patch.object(
            resolver, "_resolve_scope",
            new_callable=AsyncMock,
            return_value=(frozenset(["D"]), False),
        ), patch.object(
            resolver, "_is_project_member",
            new_callable=AsyncMock,
            return_value=True,
        ):
            decision = await resolver.authorize_resource(
                user, host_decision, ResourceType.address,
                "TB('1001','审定数')", AiChatAction.read
            )

        assert decision.allowed
        assert decision.project_id == project_id


# ---------------------------------------------------------------------------
# 完整四边契约总结
# ---------------------------------------------------------------------------


class TestFourEdgeContractSummary:
    """四边契约完整性：源坐标 → IndexSource → search → mention → context。

    断言每一边的关键不变量 —— 不只检查索引表"存在"。
    """

    def test_edge1_source_generates_text_from_fields_only(self):
        """Edge 1: 索引文本严格只来自 AddressEntry 字段。"""
        from app.services.ai_chat.address_index_source import _build_index_text

        entry = MockAddressEntry()
        text = _build_index_text(entry)

        # 不包含任何非 entry 字段的数据
        # 索引文本应该是 entry 字段的子集组合
        allowed_parts = {
            entry.label, entry.domain, entry.wp_code,
            getattr(entry, "sheet_code", ""),
            getattr(entry, "sheet_name", ""),
            entry.formula_ref,
            getattr(entry, "description", ""),
        }
        # 验证文本中的每个非分隔符部分都源自 entry 字段
        segments = [s.strip() for s in text.split("|")]
        for seg in segments:
            seg_clean = seg.strip()
            if not seg_clean:
                continue
            # 去除前缀标记（如"底稿:", "[", "]", "Sheet:", "公式:"）
            content = (
                seg_clean
                .replace("底稿:", "")
                .replace("Sheet:", "")
                .replace("公式:", "")
                .replace("[", "").replace("]", "")
                .strip()
            )
            assert any(
                content in str(v) or str(v) in content
                for v in allowed_parts if v
            ), f"索引文本包含非 entry 字段的数据: '{seg_clean}'"

    def test_edge2_source_type_strict(self):
        """Edge 2: 搜索使用严格 source_type=address_coordinate 过滤。"""
        from app.services.ai_chat.address_index_source import (
            ADDRESS_COORDINATE_SOURCE_TYPE,
            AddressCoordinateIndexSource,
        )

        source = AddressCoordinateIndexSource(AsyncMock())
        assert source.source_type == ADDRESS_COORDINATE_SOURCE_TYPE
        assert source.source_type == "address_coordinate"

    @pytest.mark.asyncio
    async def test_edge3_search_respects_authorization(self):
        """Edge 3: 搜索结果经 filter_visible_resources 过滤。"""
        mock_db = AsyncMock()
        svc = MentionSearchService(mock_db)

        # 验证 _search_address 被调用时 project_id 是必要条件
        # （传真实 year，确保空结果是缺 project_id 导致，而非缺 year 短路）
        result = await svc._search_address("%test%", None, 10, 2025)
        assert result == [], "无项目时搜索必须返回空"

    def test_edge4_manifest_carries_version_and_stale(self):
        """Edge 4: manifest 条目承载 version 和 stale 状态。"""
        detail = AddressMentionDetail(
            addr_id="TB('1001','审定数')",
            label="label",
            domain="tb",
            uri="uri",
            formula_ref="TB('1001','审定数')",
            jump_route="/tb",
            current_value="100",
            version="v3.0",
            stale=True,
        )
        entry = build_address_manifest_entry(detail, detail.addr_id)
        serialized = entry.as_dict()

        assert "version" in serialized
        assert serialized["version"] == "v3.0"
        assert "stale" in serialized
        assert serialized["stale"] is True

    def test_edge4_unavailable_leaks_nothing(self):
        """Edge 4: unavailable 条目不泄露 label/值。"""
        entry = build_address_manifest_entry(None, "secret_addr")
        serialized = entry.as_dict()

        assert serialized["status"] == "unavailable"
        # label 键不出现或为空
        assert serialized.get("label", "") == ""
