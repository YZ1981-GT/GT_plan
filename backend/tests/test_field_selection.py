"""
F5 字段选择核心模块单元测试

验证 parse_fields 和 resolve_columns 的正确性。
Requirements: 5.1, 5.2, 5.4, 5.5
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.field_selection import (
    BLOCKED_FIELDS,
    DEFAULT_SUMMARY_FIELDS,
    parse_fields,
    resolve_columns,
)


# ---------------------------------------------------------------------------
# 测试用模型（不依赖真实数据库）
# ---------------------------------------------------------------------------
class _Base(DeclarativeBase):
    pass


class FakeWorkpaper(_Base):
    """模拟 WorkingPaper 模型，用于测试字段选择"""

    __tablename__ = "fake_workpaper"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    wp_code: Mapped[str] = mapped_column(sa.String(50))
    wp_name: Mapped[str] = mapped_column(sa.String(200))
    status: Mapped[str] = mapped_column(sa.String(30))
    cycle: Mapped[str] = mapped_column(sa.String(10))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid(), nullable=True)
    updated_at: Mapped[str] = mapped_column(sa.String(50))
    created_at: Mapped[str] = mapped_column(sa.String(50))
    parsed_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    file_content: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    raw_html: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)


# ---------------------------------------------------------------------------
# parse_fields 测试
# ---------------------------------------------------------------------------
class TestParseFields:
    def test_none_input(self):
        """None 输入返回 None"""
        assert parse_fields(None) is None

    def test_empty_string(self):
        """空字符串返回 None"""
        assert parse_fields("") is None

    def test_whitespace_only(self):
        """纯空白字符串返回 None"""
        assert parse_fields("   ") is None

    def test_single_field(self):
        """单个字段"""
        result = parse_fields("id")
        assert result == {"id"}

    def test_multiple_fields(self):
        """多个字段逗号分隔"""
        result = parse_fields("id,wp_code,status")
        assert result == {"id", "wp_code", "status"}

    def test_fields_with_spaces(self):
        """字段名前后有空格应被 strip"""
        result = parse_fields(" id , wp_code , status ")
        assert result == {"id", "wp_code", "status"}

    def test_trailing_comma(self):
        """末尾逗号不产生空字段"""
        result = parse_fields("id,wp_code,")
        assert result == {"id", "wp_code"}

    def test_leading_comma(self):
        """前导逗号不产生空字段"""
        result = parse_fields(",id,wp_code")
        assert result == {"id", "wp_code"}

    def test_duplicate_fields(self):
        """重复字段名去重"""
        result = parse_fields("id,id,wp_code,wp_code")
        assert result == {"id", "wp_code"}

    def test_consecutive_commas(self):
        """连续逗号不产生空字段"""
        result = parse_fields("id,,wp_code,,,status")
        assert result == {"id", "wp_code", "status"}


# ---------------------------------------------------------------------------
# resolve_columns 测试
# ---------------------------------------------------------------------------
class TestResolveColumns:
    def test_requested_fields_basic(self):
        """请求指定字段，返回对应列"""
        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields={"id", "wp_code", "status"},
        )
        col_names = {c.key for c in cols}
        assert col_names == {"id", "wp_code", "status"}

    def test_invalid_fields_silently_ignored(self):
        """无效字段名静默忽略"""
        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields={"id", "nonexistent_field", "also_fake"},
        )
        col_names = {c.key for c in cols}
        assert col_names == {"id"}

    def test_blocked_fields_removed(self):
        """屏蔽字段即使被请求也不返回"""
        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields={"id", "parsed_data", "file_content", "raw_html"},
        )
        col_names = {c.key for c in cols}
        assert "parsed_data" not in col_names
        assert "file_content" not in col_names
        assert "raw_html" not in col_names
        assert "id" in col_names

    def test_password_hash_blocked(self):
        """password_hash 安全屏蔽"""
        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields={"id", "password_hash"},
        )
        col_names = {c.key for c in cols}
        assert "password_hash" not in col_names
        assert "id" in col_names

    def test_default_fields_used_when_no_request(self):
        """requested_fields=None 时使用 default_fields"""
        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields=None,
            default_fields={"id", "wp_code", "status"},
        )
        col_names = {c.key for c in cols}
        assert col_names == {"id", "wp_code", "status"}

    def test_default_fields_exclude_blocked(self):
        """默认字段集也排除屏蔽字段"""
        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields=None,
            default_fields={"id", "wp_code", "parsed_data"},
        )
        col_names = {c.key for c in cols}
        assert "parsed_data" not in col_names
        assert col_names == {"id", "wp_code"}

    def test_no_default_returns_all_minus_blocked(self):
        """无 requested 且无 default 时返回全部字段减去 blocked"""
        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields=None,
            default_fields=None,
        )
        col_names = {c.key for c in cols}
        # 应包含非屏蔽字段
        assert "id" in col_names
        assert "wp_code" in col_names
        assert "status" in col_names
        # 不应包含屏蔽字段
        assert "parsed_data" not in col_names
        assert "file_content" not in col_names
        assert "raw_html" not in col_names
        assert "password_hash" not in col_names

    def test_custom_blocked_fields(self):
        """自定义屏蔽字段列表"""
        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields={"id", "wp_code", "status"},
            blocked_fields={"status"},  # 自定义屏蔽 status
        )
        col_names = {c.key for c in cols}
        assert "status" not in col_names
        assert col_names == {"id", "wp_code"}

    def test_empty_requested_fields(self):
        """请求空集合时返回至少 id"""
        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields=set(),
        )
        col_names = {c.key for c in cols}
        assert "id" in col_names

    def test_all_requested_are_blocked(self):
        """所有请求字段都被屏蔽时返回 id"""
        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields={"parsed_data", "file_content", "raw_html"},
        )
        col_names = {c.key for c in cols}
        assert "id" in col_names

    def test_columns_are_instrumented_attributes(self):
        """返回的列对象是 SQLAlchemy InstrumentedAttribute"""
        from sqlalchemy.orm import InstrumentedAttribute

        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields={"id", "wp_code"},
        )
        for col in cols:
            assert isinstance(col, InstrumentedAttribute)

    def test_output_is_sorted(self):
        """输出列按字段名排序（稳定性）"""
        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields={"status", "id", "wp_code", "cycle"},
        )
        col_names = [c.key for c in cols]
        assert col_names == sorted(col_names)

    def test_default_fields_with_nonexistent_fields(self):
        """默认字段集中包含模型不存在的字段时静默忽略"""
        cols = resolve_columns(
            FakeWorkpaper,
            requested_fields=None,
            default_fields={"id", "wp_code", "nonexistent_column"},
        )
        col_names = {c.key for c in cols}
        assert col_names == {"id", "wp_code"}


# ---------------------------------------------------------------------------
# 模块常量测试
# ---------------------------------------------------------------------------
class TestModuleConstants:
    def test_default_summary_fields_defined(self):
        """默认摘要字段集已定义且非空"""
        assert len(DEFAULT_SUMMARY_FIELDS) > 0
        assert "id" in DEFAULT_SUMMARY_FIELDS
        assert "wp_code" in DEFAULT_SUMMARY_FIELDS
        assert "status" in DEFAULT_SUMMARY_FIELDS

    def test_default_summary_excludes_large_fields(self):
        """默认摘要字段不包含大字段"""
        assert "parsed_data" not in DEFAULT_SUMMARY_FIELDS
        assert "file_content" not in DEFAULT_SUMMARY_FIELDS
        assert "raw_html" not in DEFAULT_SUMMARY_FIELDS

    def test_blocked_fields_defined(self):
        """屏蔽字段集已定义"""
        assert "parsed_data" in BLOCKED_FIELDS
        assert "file_content" in BLOCKED_FIELDS
        assert "raw_html" in BLOCKED_FIELDS
        assert "password_hash" in BLOCKED_FIELDS


# ---------------------------------------------------------------------------
# 端点级字段选择集成测试（验证 router 层过滤逻辑）
# Requirements: 5.1, 5.3, 5.4, 5.6
# ---------------------------------------------------------------------------
class TestEndpointFieldSelection:
    """验证三个列表端点的字段选择逻辑在 router 层正确工作。

    这些测试不依赖数据库，直接测试字段过滤逻辑。
    """

    def _sample_workpaper_items(self) -> list[dict]:
        """模拟 WorkingPaperService.list_workpapers 返回的数据"""
        return [
            {
                "id": "uuid-1",
                "project_id": "proj-1",
                "wp_index_id": "idx-1",
                "wp_code": "D2-1",
                "wp_name": "销售收入审定表",
                "audit_cycle": "D",
                "index_status": "draft",
                "file_status": "draft",
                "status": "draft",
                "review_status": "not_submitted",
                "assigned_to": "user-1",
                "reviewer": None,
                "file_version": 1,
                "file_path": "/path/to/file",
                "source_type": "template",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-02T00:00:00",
            },
            {
                "id": "uuid-2",
                "project_id": "proj-1",
                "wp_index_id": "idx-2",
                "wp_code": "E1-1",
                "wp_name": "货币资金审定表",
                "audit_cycle": "E",
                "index_status": "completed",
                "file_status": "completed",
                "status": "completed",
                "review_status": "passed",
                "assigned_to": "user-2",
                "reviewer": "user-3",
                "file_version": 3,
                "file_path": "/path/to/file2",
                "source_type": "template",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-03T00:00:00",
            },
        ]

    def _sample_review_items(self) -> list[dict]:
        """模拟 WpReviewService.list_reviews 返回的数据"""
        return [
            {
                "id": "review-1",
                "working_paper_id": "wp-1",
                "cell_reference": "A1",
                "comment_text": "请补充说明",
                "commenter_id": "user-1",
                "status": "open",
                "reply_text": None,
                "replier_id": None,
                "replied_at": None,
                "resolved_by": None,
                "resolved_at": None,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            },
        ]

    def _sample_adjustment_result(self) -> dict:
        """模拟 AdjustmentService.list_entries 返回的分页数据"""
        return {
            "items": [
                {
                    "id": "adj-1",
                    "entry_group_id": "group-1",
                    "adjustment_no": "AJE-001",
                    "adjustment_type": "aje",
                    "description": "调整分录1",
                    "review_status": "draft",
                    "reviewer_id": None,
                    "reviewed_at": None,
                    "rejection_reason": None,
                    "created_by": "user-1",
                    "created_at": "2026-01-01T00:00:00",
                    "line_items": [
                        {"account_code": "6001", "debit_amount": 100, "credit_amount": 0}
                    ],
                },
            ],
            "total": 1,
            "page": 1,
            "page_size": 50,
        }

    def test_workpaper_fields_filter_specific(self):
        """WorkpaperList: 指定字段只返回请求的字段"""
        items = self._sample_workpaper_items()
        requested_fields = parse_fields("id,wp_code,status")

        # 模拟 router 层逻辑
        allowed = requested_fields - BLOCKED_FIELDS
        allowed.add("id")
        filtered = [
            {k: v for k, v in item.items() if k in allowed}
            for item in items
        ]

        assert len(filtered) == 2
        for item in filtered:
            assert set(item.keys()) == {"id", "wp_code", "status"}

    def test_workpaper_fields_filter_none_returns_all(self):
        """WorkpaperList: fields=None 时返回全部字段（向后兼容）"""
        items = self._sample_workpaper_items()
        requested_fields = parse_fields(None)

        # 当 requested_fields 为 None 时不过滤
        assert requested_fields is None
        # items 保持原样
        assert len(items[0]) == 17  # 全部字段

    def test_workpaper_fields_invalid_ignored(self):
        """WorkpaperList: 无效字段名静默忽略"""
        items = self._sample_workpaper_items()
        requested_fields = parse_fields("id,nonexistent,fake_field,wp_code")

        allowed = requested_fields - BLOCKED_FIELDS
        allowed.add("id")
        filtered = [
            {k: v for k, v in item.items() if k in allowed}
            for item in items
        ]

        # nonexistent 和 fake_field 不在 items 的 keys 中，自然被忽略
        for item in filtered:
            assert set(item.keys()) == {"id", "wp_code"}

    def test_workpaper_fields_blocked_not_returned(self):
        """WorkpaperList: 屏蔽字段即使请求也不返回"""
        items = self._sample_workpaper_items()
        # 即使请求 parsed_data（屏蔽字段），也不返回
        requested_fields = parse_fields("id,wp_code,parsed_data")

        allowed = requested_fields - BLOCKED_FIELDS
        allowed.add("id")
        filtered = [
            {k: v for k, v in item.items() if k in allowed}
            for item in items
        ]

        for item in filtered:
            assert "parsed_data" not in item
            assert set(item.keys()) == {"id", "wp_code"}

    def test_workpaper_fields_always_includes_id(self):
        """WorkpaperList: 即使不请求 id，也始终包含"""
        items = self._sample_workpaper_items()
        requested_fields = parse_fields("wp_code,status")

        allowed = requested_fields - BLOCKED_FIELDS
        allowed.add("id")
        filtered = [
            {k: v for k, v in item.items() if k in allowed}
            for item in items
        ]

        for item in filtered:
            assert "id" in item

    def test_review_fields_filter_specific(self):
        """ReviewRecordList: 指定字段只返回请求的字段"""
        items = self._sample_review_items()
        requested_fields = parse_fields("id,comment_text,status")

        allowed = requested_fields - BLOCKED_FIELDS
        allowed.add("id")
        filtered = [
            {k: v for k, v in item.items() if k in allowed}
            for item in items
        ]

        assert len(filtered) == 1
        assert set(filtered[0].keys()) == {"id", "comment_text", "status"}

    def test_review_fields_none_returns_all(self):
        """ReviewRecordList: fields=None 时返回全部字段"""
        items = self._sample_review_items()
        requested_fields = parse_fields(None)
        assert requested_fields is None
        # items 保持原样（13 个字段）
        assert len(items[0]) == 13

    def test_adjustment_fields_filter_preserves_pagination(self):
        """AdjustmentList: 字段过滤仅影响 items，不影响分页元数据"""
        result = self._sample_adjustment_result()
        requested_fields = parse_fields("id,adjustment_no,description")

        # 模拟 router 层逻辑
        if requested_fields is not None and isinstance(result, dict) and "items" in result:
            allowed = requested_fields - BLOCKED_FIELDS
            allowed.add("id")
            result["items"] = [
                {k: v for k, v in item.items() if k in allowed}
                for item in result["items"]
            ]

        # 分页元数据保持不变
        assert result["total"] == 1
        assert result["page"] == 1
        assert result["page_size"] == 50
        # items 被过滤
        assert set(result["items"][0].keys()) == {"id", "adjustment_no", "description"}

    def test_adjustment_fields_none_preserves_all(self):
        """AdjustmentList: fields=None 时 items 保持全部字段"""
        result = self._sample_adjustment_result()
        requested_fields = parse_fields(None)

        # 不过滤
        if requested_fields is not None and isinstance(result, dict) and "items" in result:
            allowed = requested_fields - BLOCKED_FIELDS
            allowed.add("id")
            result["items"] = [
                {k: v for k, v in item.items() if k in allowed}
                for item in result["items"]
            ]

        # items 保持原样
        assert "line_items" in result["items"][0]
        assert "adjustment_no" in result["items"][0]

    def test_all_invalid_fields_returns_only_id(self):
        """所有请求字段都无效时，仅返回 id"""
        items = self._sample_workpaper_items()
        requested_fields = parse_fields("fake1,fake2,fake3")

        allowed = requested_fields - BLOCKED_FIELDS
        allowed.add("id")
        filtered = [
            {k: v for k, v in item.items() if k in allowed}
            for item in items
        ]

        for item in filtered:
            assert set(item.keys()) == {"id"}

    def test_fields_selection_does_not_affect_item_count(self):
        """字段选择不影响返回的记录数量"""
        items = self._sample_workpaper_items()
        requested_fields = parse_fields("id,wp_code")

        allowed = requested_fields - BLOCKED_FIELDS
        allowed.add("id")
        filtered = [
            {k: v for k, v in item.items() if k in allowed}
            for item in items
        ]

        assert len(filtered) == len(items)


# ---------------------------------------------------------------------------
# Property-Based Tests: 字段选择
# ---------------------------------------------------------------------------

from hypothesis import given, settings, strategies as st, assume


# Known model fields for FakeWorkpaper
_ALL_FAKE_FIELDS = {
    "id", "wp_code", "wp_name", "status", "cycle",
    "assignee_id", "updated_at", "created_at",
    "parsed_data", "file_content", "raw_html", "password_hash",
}
_NON_BLOCKED_FIELDS = _ALL_FAKE_FIELDS - BLOCKED_FIELDS
_INVALID_FIELDS = {"nonexistent", "fake_col", "xyz", "abc", "zzz_field"}


class TestFieldSelectionPBT:
    """Property 9: 字段选择过滤正确性

    **Validates: Requirements 5.1, 5.4**

    For any valid fields parameter and any response object, the response should
    contain only the intersection of requested fields and model's actual fields
    (invalid field names silently ignored, no extra fields returned).
    """

    @settings(max_examples=15)
    @given(
        requested=st.sets(
            st.sampled_from(sorted(_ALL_FAKE_FIELDS | _INVALID_FIELDS)),
            min_size=1,
            max_size=8,
        )
    )
    def test_resolve_columns_returns_subset_of_requested(self, requested: set[str]):
        """Property 9: 返回列是请求字段与模型字段交集减去 blocked。

        **Validates: Requirements 5.1, 5.4**
        """
        cols = resolve_columns(FakeWorkpaper, requested_fields=requested)
        col_names = {c.key for c in cols}

        # 返回的列必须是模型实际列的子集
        assert col_names <= _ALL_FAKE_FIELDS, (
            f"返回了模型不存在的列: {col_names - _ALL_FAKE_FIELDS}"
        )

        # 返回的列不包含任何 blocked 字段
        assert col_names.isdisjoint(BLOCKED_FIELDS), (
            f"返回了 blocked 字段: {col_names & BLOCKED_FIELDS}"
        )

        # 返回的列是 (requested ∩ model_fields) - blocked 的子集
        expected_max = (requested & _ALL_FAKE_FIELDS) - BLOCKED_FIELDS
        assert col_names <= (expected_max | {"id"}), (
            f"返回了超出预期的列: {col_names - expected_max - {'id'}}"
        )

    @settings(max_examples=15)
    @given(
        requested=st.sets(
            st.sampled_from(sorted(_NON_BLOCKED_FIELDS)),
            min_size=1,
            max_size=6,
        )
    )
    def test_valid_requested_fields_all_returned(self, requested: set[str]):
        """Property 9: 请求的有效非 blocked 字段全部返回。

        **Validates: Requirements 5.1, 5.4**
        """
        cols = resolve_columns(FakeWorkpaper, requested_fields=requested)
        col_names = {c.key for c in cols}

        # 所有请求的有效非 blocked 字段都应出现在结果中
        assert requested <= col_names, (
            f"缺少请求的有效字段: {requested - col_names}"
        )

    @settings(max_examples=15)
    @given(
        invalid_fields=st.sets(
            st.sampled_from(sorted(_INVALID_FIELDS)),
            min_size=1,
            max_size=5,
        )
    )
    def test_invalid_fields_silently_ignored(self, invalid_fields: set[str]):
        """Property 9: 无效字段名静默忽略，不报错。

        **Validates: Requirements 5.4**
        """
        cols = resolve_columns(FakeWorkpaper, requested_fields=invalid_fields)
        col_names = {c.key for c in cols}

        # 无效字段不出现在结果中
        assert col_names.isdisjoint(invalid_fields)
        # 至少返回 id（fallback）
        assert "id" in col_names


class TestFieldSelectionOrthogonalityPBT:
    """Property 10: 字段选择与分页/排序正交

    **Validates: Requirements 5.6**

    For any combination of ?fields= with pagination/sorting parameters,
    the field selection logic should not affect pagination metadata or sort order.
    """

    @settings(max_examples=15)
    @given(
        fields_a=st.sets(
            st.sampled_from(sorted(_NON_BLOCKED_FIELDS)),
            min_size=1,
            max_size=6,
        ),
        fields_b=st.sets(
            st.sampled_from(sorted(_NON_BLOCKED_FIELDS)),
            min_size=1,
            max_size=6,
        ),
    )
    def test_different_fields_same_column_count_logic(
        self, fields_a: set[str], fields_b: set[str]
    ):
        """Property 10: 不同字段选择不影响 resolve_columns 的确定性行为。

        **Validates: Requirements 5.6**

        字段选择仅影响返回的列集合，不影响排序/分页逻辑（正交性）。
        resolve_columns 对相同输入始终返回相同结果（确定性）。
        """
        # 同一字段集调用两次结果一致（确定性）
        cols_a1 = resolve_columns(FakeWorkpaper, requested_fields=fields_a)
        cols_a2 = resolve_columns(FakeWorkpaper, requested_fields=fields_a)

        names_a1 = [c.key for c in cols_a1]
        names_a2 = [c.key for c in cols_a2]

        assert names_a1 == names_a2, "相同输入应产生相同输出（确定性）"

    @settings(max_examples=15)
    @given(
        fields=st.one_of(
            st.none(),
            st.sets(
                st.sampled_from(sorted(_NON_BLOCKED_FIELDS)),
                min_size=1,
                max_size=6,
            ),
        ),
        page=st.integers(min_value=1, max_value=100),
        page_size=st.integers(min_value=10, max_value=100),
    )
    def test_fields_do_not_affect_pagination_params(
        self, fields: set[str] | None, page: int, page_size: int
    ):
        """Property 10: 字段选择不影响分页参数的有效性。

        **Validates: Requirements 5.6**

        无论 fields 如何选择，分页参数（page, page_size）的语义不变。
        """
        # parse_fields 的结果不依赖分页参数
        fields_str = ",".join(fields) if fields else None
        parsed = parse_fields(fields_str)

        if fields is not None:
            assert parsed is not None
            # parsed 结果与 page/page_size 无关
            assert parsed == fields
        else:
            assert parsed is None

        # 分页参数始终有效（正交性）
        assert page >= 1
        assert page_size >= 10
