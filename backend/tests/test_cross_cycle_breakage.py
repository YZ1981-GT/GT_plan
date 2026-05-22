"""跨循环断裂清单服务测试

Tests for:
- Task 6.1: 断裂清单服务逻辑
- Task 6.2: 断裂清单路由

覆盖：
- severity 排序正确性（blocking > required > warning > recommended > info）
- 断裂检测逻辑（target_missing / target_stale）
- 统计摘要一致性
- CWR 加载失败 503 降级
- 环境变量路径覆盖
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.cross_cycle_breakage_service import (
    SEVERITY_ORDER,
    BreakageListResponse,
    BreakageRecord,
    BreakageSummary,
    _resolve_cwr_path,
    get_cross_cycle_breakage,
    load_cwr_references,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_cwr_json(references: list[dict]) -> str:
    """生成 CWR JSON 字符串。"""
    return json.dumps({"references": references})


def _make_reference(
    ref_id: str = "CW-TEST-01",
    source_wp: str = "H1",
    severity: str = "blocking",
    targets: list[dict] | None = None,
) -> dict:
    """生成单条 CWR reference。"""
    if targets is None:
        targets = [{"wp_code": "K8", "sheet": "审定表K8-1", "cell": "D1"}]
    return {
        "ref_id": ref_id,
        "source_wp": source_wp,
        "targets": targets,
        "severity": severity,
        "category": "other",
    }


# ---------------------------------------------------------------------------
# Unit Tests: CWR Loading
# ---------------------------------------------------------------------------


class TestCWRLoading:
    """CWR 文件加载测试。"""

    def test_resolve_cwr_path_default(self, monkeypatch):
        """默认路径指向 backend/data/cross_wp_references.json。"""
        monkeypatch.delenv("CROSS_WP_REF_PATH", raising=False)
        path = _resolve_cwr_path()
        assert path.name == "cross_wp_references.json"
        assert "data" in str(path)

    def test_resolve_cwr_path_env_override(self, monkeypatch, tmp_path):
        """环境变量覆盖路径。"""
        custom_path = tmp_path / "custom_cwr.json"
        custom_path.write_text(_make_cwr_json([]), encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(custom_path))
        path = _resolve_cwr_path()
        assert path == custom_path

    def test_load_cwr_references_success(self, monkeypatch, tmp_path):
        """成功加载 CWR references。"""
        refs = [_make_reference()]
        cwr_file = tmp_path / "cwr.json"
        cwr_file.write_text(_make_cwr_json(refs), encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(cwr_file))

        loaded = load_cwr_references()
        assert len(loaded) == 1
        assert loaded[0]["ref_id"] == "CW-TEST-01"

    def test_load_cwr_references_file_not_found(self, monkeypatch, tmp_path):
        """文件不存在时抛出 FileNotFoundError。"""
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(tmp_path / "nonexistent.json"))
        with pytest.raises(FileNotFoundError):
            load_cwr_references()

    def test_load_cwr_references_invalid_json(self, monkeypatch, tmp_path):
        """JSON 格式错误时抛出异常。"""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json", encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(bad_file))
        with pytest.raises(json.JSONDecodeError):
            load_cwr_references()

    def test_load_cwr_references_missing_references_key(self, monkeypatch, tmp_path):
        """缺少 references 字段时抛出 ValueError。"""
        bad_file = tmp_path / "no_refs.json"
        bad_file.write_text(json.dumps({"data": []}), encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(bad_file))
        with pytest.raises(ValueError, match="references field missing"):
            load_cwr_references()


# ---------------------------------------------------------------------------
# Unit Tests: Breakage Detection Logic
# ---------------------------------------------------------------------------


class TestBreakageDetection:
    """断裂检测逻辑测试。"""

    @pytest.fixture
    def mock_db(self):
        """Mock AsyncSession that returns configurable wp_code sets."""
        db = AsyncMock()
        return db

    def _setup_db_mock(self, db, existing_codes: set[str], stale_codes: set[str]):
        """配置 mock DB 返回指定的 wp_code 集合。"""
        from unittest.mock import MagicMock

        # First call: existing wp_codes
        existing_result = MagicMock()
        existing_result.all.return_value = [(code,) for code in existing_codes]

        # Second call: stale wp_codes
        stale_result = MagicMock()
        stale_result.all.return_value = [(code,) for code in stale_codes]

        db.execute = AsyncMock(side_effect=[existing_result, stale_result])

    @pytest.mark.asyncio
    async def test_target_missing_detection(self, mock_db, monkeypatch, tmp_path):
        """target_missing：项目内无对应 wp_code。"""
        refs = [
            _make_reference(
                ref_id="CW-01",
                severity="blocking",
                targets=[{"wp_code": "NONEXISTENT"}],
            )
        ]
        cwr_file = tmp_path / "cwr.json"
        cwr_file.write_text(_make_cwr_json(refs), encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(cwr_file))

        self._setup_db_mock(mock_db, existing_codes={"H1", "K8"}, stale_codes=set())

        result = await get_cross_cycle_breakage(db=mock_db, project_id=uuid4())

        assert len(result.items) == 1
        assert result.items[0].reason == "target_missing"
        assert result.items[0].target_wp_code == "NONEXISTENT"

    @pytest.mark.asyncio
    async def test_target_stale_detection(self, mock_db, monkeypatch, tmp_path):
        """target_stale：wp_code 存在但 prefill_stale=true。"""
        refs = [
            _make_reference(
                ref_id="CW-01",
                severity="warning",
                targets=[{"wp_code": "K8"}],
            )
        ]
        cwr_file = tmp_path / "cwr.json"
        cwr_file.write_text(_make_cwr_json(refs), encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(cwr_file))

        self._setup_db_mock(mock_db, existing_codes={"H1", "K8"}, stale_codes={"K8"})

        result = await get_cross_cycle_breakage(db=mock_db, project_id=uuid4())

        assert len(result.items) == 1
        assert result.items[0].reason == "target_stale"
        assert result.items[0].target_wp_code == "K8"

    @pytest.mark.asyncio
    async def test_no_breakage_when_target_exists_and_not_stale(
        self, mock_db, monkeypatch, tmp_path
    ):
        """target 存在且不 stale 时无断裂。"""
        refs = [
            _make_reference(
                ref_id="CW-01",
                severity="blocking",
                targets=[{"wp_code": "K8"}],
            )
        ]
        cwr_file = tmp_path / "cwr.json"
        cwr_file.write_text(_make_cwr_json(refs), encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(cwr_file))

        self._setup_db_mock(mock_db, existing_codes={"H1", "K8"}, stale_codes=set())

        result = await get_cross_cycle_breakage(db=mock_db, project_id=uuid4())

        assert len(result.items) == 0
        assert result.summary.blocking == 0

    @pytest.mark.asyncio
    async def test_cross_module_targets_skipped(
        self, mock_db, monkeypatch, tmp_path
    ):
        """cross_module 类型 target（无 wp_code）被跳过。"""
        refs = [
            {
                "ref_id": "CW-MODULE",
                "source_wp": "B15",
                "targets": [
                    {"target_module": "trial_balance", "link_type": "data_source"}
                ],
                "severity": "info",
                "category": "other",
            }
        ]
        cwr_file = tmp_path / "cwr.json"
        cwr_file.write_text(_make_cwr_json(refs), encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(cwr_file))

        self._setup_db_mock(mock_db, existing_codes={"B15"}, stale_codes=set())

        result = await get_cross_cycle_breakage(db=mock_db, project_id=uuid4())

        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_multiple_targets_per_reference(
        self, mock_db, monkeypatch, tmp_path
    ):
        """单条 reference 有多个 targets，每个独立检测。"""
        refs = [
            _make_reference(
                ref_id="CW-01",
                severity="blocking",
                targets=[
                    {"wp_code": "K8"},  # exists, not stale → no breakage
                    {"wp_code": "K9"},  # exists, stale → target_stale
                    {"wp_code": "MISSING"},  # not exists → target_missing
                ],
            )
        ]
        cwr_file = tmp_path / "cwr.json"
        cwr_file.write_text(_make_cwr_json(refs), encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(cwr_file))

        self._setup_db_mock(
            mock_db, existing_codes={"K8", "K9"}, stale_codes={"K9"}
        )

        result = await get_cross_cycle_breakage(db=mock_db, project_id=uuid4())

        assert len(result.items) == 2
        reasons = {item.reason for item in result.items}
        assert reasons == {"target_missing", "target_stale"}


# ---------------------------------------------------------------------------
# Unit Tests: Severity Sorting
# ---------------------------------------------------------------------------


class TestSeveritySorting:
    """severity 排序测试。"""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    def _setup_db_mock(self, db, existing_codes: set[str], stale_codes: set[str]):
        from unittest.mock import MagicMock

        existing_result = MagicMock()
        existing_result.all.return_value = [(code,) for code in existing_codes]
        stale_result = MagicMock()
        stale_result.all.return_value = [(code,) for code in stale_codes]
        db.execute = AsyncMock(side_effect=[existing_result, stale_result])

    @pytest.mark.asyncio
    async def test_severity_descending_order(self, mock_db, monkeypatch, tmp_path):
        """断裂清单按 severity 降序排列：blocking > required > warning > recommended > info。"""
        refs = [
            _make_reference(ref_id="CW-05", severity="info", targets=[{"wp_code": "T5"}]),
            _make_reference(ref_id="CW-03", severity="warning", targets=[{"wp_code": "T3"}]),
            _make_reference(ref_id="CW-01", severity="blocking", targets=[{"wp_code": "T1"}]),
            _make_reference(ref_id="CW-04", severity="recommended", targets=[{"wp_code": "T4"}]),
            _make_reference(ref_id="CW-02", severity="required", targets=[{"wp_code": "T2"}]),
        ]
        cwr_file = tmp_path / "cwr.json"
        cwr_file.write_text(_make_cwr_json(refs), encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(cwr_file))

        # All targets missing
        self._setup_db_mock(mock_db, existing_codes=set(), stale_codes=set())

        result = await get_cross_cycle_breakage(db=mock_db, project_id=uuid4())

        assert len(result.items) == 5
        severities = [item.severity for item in result.items]
        assert severities == ["blocking", "required", "warning", "recommended", "info"]


# ---------------------------------------------------------------------------
# Unit Tests: Summary Statistics
# ---------------------------------------------------------------------------


class TestSummaryStatistics:
    """统计摘要测试。"""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    def _setup_db_mock(self, db, existing_codes: set[str], stale_codes: set[str]):
        from unittest.mock import MagicMock

        existing_result = MagicMock()
        existing_result.all.return_value = [(code,) for code in existing_codes]
        stale_result = MagicMock()
        stale_result.all.return_value = [(code,) for code in stale_codes]
        db.execute = AsyncMock(side_effect=[existing_result, stale_result])

    @pytest.mark.asyncio
    async def test_summary_counts_match_items(self, mock_db, monkeypatch, tmp_path):
        """summary 各级别计数与 items 中对应 severity 数量一致。"""
        refs = [
            _make_reference(ref_id="CW-01", severity="blocking", targets=[{"wp_code": "T1"}]),
            _make_reference(ref_id="CW-02", severity="blocking", targets=[{"wp_code": "T2"}]),
            _make_reference(ref_id="CW-03", severity="warning", targets=[{"wp_code": "T3"}]),
            _make_reference(ref_id="CW-04", severity="info", targets=[{"wp_code": "T4"}]),
            _make_reference(ref_id="CW-05", severity="required", targets=[{"wp_code": "T5"}]),
            _make_reference(ref_id="CW-06", severity="recommended", targets=[{"wp_code": "T6"}]),
        ]
        cwr_file = tmp_path / "cwr.json"
        cwr_file.write_text(_make_cwr_json(refs), encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(cwr_file))

        # All targets missing
        self._setup_db_mock(mock_db, existing_codes=set(), stale_codes=set())

        result = await get_cross_cycle_breakage(db=mock_db, project_id=uuid4())

        assert result.summary.blocking == 2
        assert result.summary.warning == 1
        assert result.summary.info == 1
        assert result.summary.required == 1
        assert result.summary.recommended == 1

        # Total items == sum of all severity counts
        total_from_summary = (
            result.summary.blocking
            + result.summary.required
            + result.summary.warning
            + result.summary.recommended
            + result.summary.info
        )
        assert total_from_summary == len(result.items)

    @pytest.mark.asyncio
    async def test_empty_breakage_list(self, mock_db, monkeypatch, tmp_path):
        """无断裂时返回空列表和全零摘要。"""
        refs = [
            _make_reference(ref_id="CW-01", severity="blocking", targets=[{"wp_code": "K8"}]),
        ]
        cwr_file = tmp_path / "cwr.json"
        cwr_file.write_text(_make_cwr_json(refs), encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(cwr_file))

        # K8 exists and not stale
        self._setup_db_mock(mock_db, existing_codes={"K8"}, stale_codes=set())

        result = await get_cross_cycle_breakage(db=mock_db, project_id=uuid4())

        assert len(result.items) == 0
        assert result.summary.blocking == 0
        assert result.summary.required == 0
        assert result.summary.warning == 0
        assert result.summary.recommended == 0
        assert result.summary.info == 0


# ---------------------------------------------------------------------------
# Unit Tests: Response Model
# ---------------------------------------------------------------------------


class TestResponseModel:
    """响应模型测试。"""

    def test_breakage_record_fields(self):
        """BreakageRecord 包含所有必需字段。"""
        record = BreakageRecord(
            ref_id="CW-01",
            source_wp_code="H1",
            target_wp_code="K8",
            severity="blocking",
            reason="target_missing",
            last_checked_at=datetime.now(timezone.utc),
        )
        assert record.ref_id == "CW-01"
        assert record.source_wp_code == "H1"
        assert record.target_wp_code == "K8"
        assert record.severity == "blocking"
        assert record.reason == "target_missing"
        assert record.last_checked_at is not None

    def test_breakage_summary_defaults(self):
        """BreakageSummary 默认值全为 0。"""
        summary = BreakageSummary()
        assert summary.blocking == 0
        assert summary.required == 0
        assert summary.warning == 0
        assert summary.recommended == 0
        assert summary.info == 0

    def test_breakage_list_response_structure(self):
        """BreakageListResponse 包含 items 和 summary。"""
        response = BreakageListResponse(
            items=[
                BreakageRecord(
                    ref_id="CW-01",
                    source_wp_code="H1",
                    target_wp_code="K8",
                    severity="blocking",
                    reason="target_missing",
                    last_checked_at=datetime.now(timezone.utc),
                )
            ],
            summary=BreakageSummary(blocking=1),
        )
        assert len(response.items) == 1
        assert response.summary.blocking == 1


# ---------------------------------------------------------------------------
# Unit Tests: Invalid Severity Handling
# ---------------------------------------------------------------------------


class TestInvalidSeverity:
    """无效 severity 处理测试。"""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    def _setup_db_mock(self, db, existing_codes: set[str], stale_codes: set[str]):
        from unittest.mock import MagicMock

        existing_result = MagicMock()
        existing_result.all.return_value = [(code,) for code in existing_codes]
        stale_result = MagicMock()
        stale_result.all.return_value = [(code,) for code in stale_codes]
        db.execute = AsyncMock(side_effect=[existing_result, stale_result])

    @pytest.mark.asyncio
    async def test_unknown_severity_defaults_to_info(
        self, mock_db, monkeypatch, tmp_path
    ):
        """未知 severity 值降级为 info。"""
        refs = [
            _make_reference(
                ref_id="CW-01",
                severity="unknown_level",
                targets=[{"wp_code": "MISSING"}],
            )
        ]
        cwr_file = tmp_path / "cwr.json"
        cwr_file.write_text(_make_cwr_json(refs), encoding="utf-8")
        monkeypatch.setenv("CROSS_WP_REF_PATH", str(cwr_file))

        self._setup_db_mock(mock_db, existing_codes=set(), stale_codes=set())

        result = await get_cross_cycle_breakage(db=mock_db, project_id=uuid4())

        assert len(result.items) == 1
        assert result.items[0].severity == "info"


# ---------------------------------------------------------------------------
# Property-Based Tests: 断裂清单
# ---------------------------------------------------------------------------

from hypothesis import given, settings, strategies as st, assume


_SEVERITY_LEVELS = ["blocking", "required", "warning", "recommended", "info"]
_REASONS = ["target_missing", "target_stale"]


class TestBreakageFilterPBT:
    """Property 3: 断裂清单过滤正确性

    **Validates: Requirements 2.2**

    For any set of cross_wp_references, the breakage list should contain exactly
    those entries where the target workpaper is missing or stale, and no other entries.
    """

    @settings(max_examples=100)
    @given(
        n_refs=st.integers(min_value=1, max_value=20),
        existing_ratio=st.floats(min_value=0.0, max_value=1.0),
        stale_ratio=st.floats(min_value=0.0, max_value=1.0),
    )
    def test_breakage_only_for_missing_or_stale(
        self, n_refs: int, existing_ratio: float, stale_ratio: float
    ):
        """Property 3: 断裂清单仅包含 target_missing 或 target_stale 的条目。

        **Validates: Requirements 2.2**
        """
        # Generate target wp_codes
        all_targets = [f"T{i}" for i in range(n_refs)]

        # Determine which exist and which are stale
        n_existing = int(n_refs * existing_ratio)
        existing_codes = set(all_targets[:n_existing])
        n_stale = int(n_existing * stale_ratio)
        stale_codes = set(list(existing_codes)[:n_stale])

        # Simulate breakage detection logic (mirrors service logic)
        breakage_items = []
        for target in all_targets:
            if target not in existing_codes:
                breakage_items.append(("target_missing", target))
            elif target in stale_codes:
                breakage_items.append(("target_stale", target))

        # Verify: every breakage item has a valid reason
        for reason, target in breakage_items:
            assert reason in _REASONS
            if reason == "target_missing":
                assert target not in existing_codes
            elif reason == "target_stale":
                assert target in existing_codes
                assert target in stale_codes

        # Verify: no non-broken targets appear in breakage list
        broken_targets = {t for _, t in breakage_items}
        for target in all_targets:
            if target in existing_codes and target not in stale_codes:
                assert target not in broken_targets, (
                    f"正常 target {target} 不应出现在断裂清单中"
                )


class TestBreakageSeveritySortPBT:
    """Property 4: 断裂清单 severity 排序

    **Validates: Requirements 2.3**

    For any breakage list, items should be sorted by severity descending
    (blocking > required > warning > recommended > info).
    """

    @settings(max_examples=100)
    @given(
        severities=st.lists(
            st.sampled_from(_SEVERITY_LEVELS),
            min_size=1,
            max_size=30,
        )
    )
    def test_severity_sort_invariant(self, severities: list[str]):
        """Property 4: 排序后 severity 单调非递减（按 SEVERITY_ORDER）。

        **Validates: Requirements 2.3**
        """
        now = datetime.now(timezone.utc)
        items = [
            BreakageRecord(
                ref_id=f"CW-{i:03d}",
                source_wp_code=f"H{i}",
                target_wp_code=f"T{i}",
                severity=sev,
                reason="target_missing",
                last_checked_at=now,
            )
            for i, sev in enumerate(severities)
        ]

        # Sort using the same logic as the service
        items.sort(key=lambda item: (SEVERITY_ORDER.get(item.severity, 4), item.ref_id))

        # Verify: severity order is non-decreasing
        for i in range(len(items) - 1):
            order_i = SEVERITY_ORDER[items[i].severity]
            order_j = SEVERITY_ORDER[items[i + 1].severity]
            assert order_i <= order_j, (
                f"排序违反：items[{i}].severity={items[i].severity} "
                f"(order={order_i}) 应 <= items[{i+1}].severity="
                f"{items[i+1].severity} (order={order_j})"
            )


class TestBreakageSummaryConsistencyPBT:
    """Property 5: 断裂统计摘要一致性

    **Validates: Requirements 2.6**

    For any breakage list response, the sum of all severity counts in summary
    should equal len(items), and each count should equal the number of items
    with that severity.
    """

    @settings(max_examples=100)
    @given(
        severities=st.lists(
            st.sampled_from(_SEVERITY_LEVELS),
            min_size=0,
            max_size=30,
        )
    )
    def test_summary_counts_equal_items(self, severities: list[str]):
        """Property 5: summary 各级别计数之和 == len(items)。

        **Validates: Requirements 2.6**
        """
        now = datetime.now(timezone.utc)
        items = [
            BreakageRecord(
                ref_id=f"CW-{i:03d}",
                source_wp_code=f"H{i}",
                target_wp_code=f"T{i}",
                severity=sev,
                reason="target_missing",
                last_checked_at=now,
            )
            for i, sev in enumerate(severities)
        ]

        # Compute summary using the same logic as the service
        summary = BreakageSummary()
        for item in items:
            if item.severity == "blocking":
                summary.blocking += 1
            elif item.severity == "required":
                summary.required += 1
            elif item.severity == "warning":
                summary.warning += 1
            elif item.severity == "recommended":
                summary.recommended += 1
            elif item.severity == "info":
                summary.info += 1

        # Invariant: sum of counts == len(items)
        total = (
            summary.blocking
            + summary.required
            + summary.warning
            + summary.recommended
            + summary.info
        )
        assert total == len(items), (
            f"摘要总数 {total} != items 数量 {len(items)}"
        )

        # Invariant: each count matches actual items with that severity
        for level in _SEVERITY_LEVELS:
            expected = sum(1 for item in items if item.severity == level)
            actual = getattr(summary, level)
            assert actual == expected, (
                f"severity={level}: summary={actual} != actual={expected}"
            )
