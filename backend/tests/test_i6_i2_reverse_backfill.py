"""
test_i6_i2_reverse_backfill.py — I-F8 I2↔I6 研发费用↔开发支出反向回填集成测试

验证:
1. CW-265 (I2→I6 资本化金额) 存在于 cross_wp_references.json 且结构正确
2. CW-266 (I6→I2 费用化金额) 存在于 cross_wp_references.json 且结构正确
3. event_handler 订阅 WORKPAPER_SAVED + wp_code='I2' 过滤
4. event_handler 订阅 WORKPAPER_SAVED + wp_code='I6' 过滤
5. I2 保存 → stale_engine 传播 + cross-ref:updated 事件发布 (target=I6)
6. I6 保存 → stale_engine 传播 + cross-ref:updated 事件发布 (target=I2)
7. 非 I2/I6 的 wp_code 不触发研发回填 handler
8. 缺少 project_id 或 year 时 handler 安全跳过

Spec: workpaper-i-intangible-assets-cycle / Sprint 2 / Task 2.21
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.models.audit_platform_schemas import EventPayload, EventType


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CROSS_WP_REF_PATH = DATA_DIR / "cross_wp_references.json"


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def references() -> list[dict]:
    assert CROSS_WP_REF_PATH.exists(), (
        f"cross_wp_references.json not found at {CROSS_WP_REF_PATH}"
    )
    data = json.loads(CROSS_WP_REF_PATH.read_text(encoding="utf-8"))
    return data["references"]


@pytest.fixture(scope="module")
def i2_to_i6_entries(references) -> list[dict]:
    """I2 → I6 且 category=data_flow_reverse 的条目"""
    return [
        r for r in references
        if r.get("source_wp") == "I2"
        and r.get("category") == "data_flow_reverse"
        and any(
            (t.get("wp_code") or "") == "I6"
            for t in r.get("targets", [])
        )
    ]


@pytest.fixture(scope="module")
def i6_to_i2_entries(references) -> list[dict]:
    """I6 → I2 且 category=data_flow_reverse 的条目"""
    return [
        r for r in references
        if r.get("source_wp") == "I6"
        and r.get("category") == "data_flow_reverse"
        and any(
            (t.get("wp_code") or "") == "I2"
            for t in r.get("targets", [])
        )
    ]


# ─── Test 1: CW-265 I2→I6 反向回填条目存在且结构正确 ────────────────────────


class TestI2ToI6ReverseRefEntry:
    """验证 CW-265 I2→I6 data_flow_reverse 条目存在于 cross_wp_references.json"""

    def test_at_least_one_reverse_entry(self, i2_to_i6_entries):
        """至少存在 1 条 I2→I6 反向回填条目"""
        assert len(i2_to_i6_entries) >= 1, (
            "I-F8 反向回填条目缺失: 需 ≥1 条 I2→I6 且 category=data_flow_reverse"
        )

    def test_ref_id_cw265(self, i2_to_i6_entries):
        """ref_id 应为 CW-265"""
        ref_ids = [r.get("ref_id") for r in i2_to_i6_entries]
        assert "CW-265" in ref_ids, (
            f"CW-265 not found in I2→I6 entries, got: {ref_ids}"
        )

    def test_source_sheet_i2_1(self, i2_to_i6_entries):
        """source_sheet 应引用 I2-1 审定表"""
        assert any(
            "I2-1" in (r.get("source_sheet") or "")
            for r in i2_to_i6_entries
        ), "至少需 1 条 source_sheet 含 'I2-1'"

    def test_source_cell_capitalization(self, i2_to_i6_entries):
        """source_cell 应含 '资本化'"""
        assert any(
            "资本化" in (r.get("source_cell") or "")
            for r in i2_to_i6_entries
        ), "source_cell 应含 '资本化'"

    def test_target_i6_capitalized_expenditure(self, i2_to_i6_entries):
        """target 应引用 I6 资本化支出"""
        for r in i2_to_i6_entries:
            for t in r["targets"]:
                if (t.get("wp_code") or "") == "I6":
                    assert "资本化" in (t.get("cell") or ""), (
                        f"{r['ref_id']} I6 target cell 不含 '资本化': {t.get('cell')}"
                    )

    def test_severity_warning(self, i2_to_i6_entries):
        """severity = warning"""
        for r in i2_to_i6_entries:
            assert r.get("severity") == "warning", (
                f"{r['ref_id']} severity 应为 warning, 实际为 {r.get('severity')}"
            )

    def test_trigger_workpaper_saved_i2(self, i2_to_i6_entries):
        """trigger 字段应配置 workpaper:saved:I2"""
        for r in i2_to_i6_entries:
            trig = (r.get("trigger") or "").lower()
            assert "i2" in trig, (
                f"{r['ref_id']} trigger 字段缺失或不含 'I2': {r.get('trigger')}"
            )

    def test_formula_uses_wp_syntax(self, i2_to_i6_entries):
        """target formula 使用 =WP('I2',...) 语法"""
        for r in i2_to_i6_entries:
            for t in r["targets"]:
                if (t.get("wp_code") or "") == "I6":
                    assert (t.get("formula") or "").startswith("=WP('I2'"), (
                        f"{r['ref_id']} formula 不是 =WP('I2',...): {t.get('formula')}"
                    )


# ─── Test 2: CW-266 I6→I2 反向回填条目存在且结构正确 ───────────────────────


class TestI6ToI2ReverseRefEntry:
    """验证 CW-266 I6→I2 data_flow_reverse 条目存在于 cross_wp_references.json"""

    def test_at_least_one_reverse_entry(self, i6_to_i2_entries):
        """至少存在 1 条 I6→I2 反向回填条目"""
        assert len(i6_to_i2_entries) >= 1, (
            "I-F8 反向回填条目缺失: 需 ≥1 条 I6→I2 且 category=data_flow_reverse"
        )

    def test_ref_id_cw266(self, i6_to_i2_entries):
        """ref_id 应为 CW-266"""
        ref_ids = [r.get("ref_id") for r in i6_to_i2_entries]
        assert "CW-266" in ref_ids, (
            f"CW-266 not found in I6→I2 entries, got: {ref_ids}"
        )

    def test_source_sheet_i6_1(self, i6_to_i2_entries):
        """source_sheet 应引用 I6-1 审定表"""
        assert any(
            "I6-1" in (r.get("source_sheet") or "")
            for r in i6_to_i2_entries
        ), "至少需 1 条 source_sheet 含 'I6-1'"

    def test_source_cell_expensed(self, i6_to_i2_entries):
        """source_cell 应含 '费用化'"""
        assert any(
            "费用化" in (r.get("source_cell") or "")
            for r in i6_to_i2_entries
        ), "source_cell 应含 '费用化'"

    def test_target_i2_expensed_portion(self, i6_to_i2_entries):
        """target 应引用 I2 对应费用化金额"""
        for r in i6_to_i2_entries:
            for t in r["targets"]:
                if (t.get("wp_code") or "") == "I2":
                    assert "费用化" in (t.get("cell") or ""), (
                        f"{r['ref_id']} I2 target cell 不含 '费用化': {t.get('cell')}"
                    )

    def test_trigger_workpaper_saved_i6(self, i6_to_i2_entries):
        """trigger 字段应配置 workpaper:saved:I6"""
        for r in i6_to_i2_entries:
            trig = (r.get("trigger") or "").lower()
            assert "i6" in trig, (
                f"{r['ref_id']} trigger 字段缺失或不含 'I6': {r.get('trigger')}"
            )

    def test_formula_uses_wp_syntax(self, i6_to_i2_entries):
        """target formula 使用 =WP('I6',...) 语法"""
        for r in i6_to_i2_entries:
            for t in r["targets"]:
                if (t.get("wp_code") or "") == "I2":
                    assert (t.get("formula") or "").startswith("=WP('I6'"), (
                        f"{r['ref_id']} formula 不是 =WP('I6',...): {t.get('formula')}"
                    )


# ─── Test 3: event_handler 注册验证 ──────────────────────────────────────────


class TestIRdEventHandlerRegistration:
    """验证 event_handlers.py 中 I2/I6 研发回填 handler 已注册"""

    def test_handler_function_exists(self):
        """_on_i_rd_reverse_backfill 函数存在"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert "_on_i_rd_reverse_backfill" in src

    def test_handler_subscribes_workpaper_saved(self):
        """handler 订阅 WORKPAPER_SAVED 事件"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert (
            "event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_i_rd_reverse_backfill)"
            in src
        )

    def test_handler_filters_i2(self):
        """handler 过滤 wp_code='I2'"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert '"I2"' in src or "'I2'" in src

    def test_handler_filters_i6(self):
        """handler 过滤 wp_code='I6'"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert '"I6"' in src or "'I6'" in src

    def test_wp_code_filter_set(self):
        """_I_RD_REVERSE_WP_CODES 集合包含 I2 和 I6"""
        from app.services import event_handlers
        src = inspect.getsource(event_handlers)
        assert "_I_RD_REVERSE_WP_CODES" in src


# ─── Test 4: I2 保存 → stale 传播 + cross-ref:updated 事件 ──────────────────


class TestI2SaveTriggersStaleAndCrossRef:
    """端到端: I2 保存 → stale_engine 传播 + CROSS_REF_UPDATED 事件发布"""

    @pytest.mark.asyncio
    async def test_i2_save_triggers_stale_propagation(self, monkeypatch):
        """I2 保存时 stale_engine.on_change 被调用"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        stale_calls: list[tuple] = []

        async def mock_on_change(uri, project_id, year):
            stale_calls.append((uri, str(project_id), year))
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        # 构造 I2 保存事件并直接 dispatch（绕过 debounce）
        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid4(),
            year=2025,
            extra={"wp_code": "I2", "sheet": "审定表I2-1", "wp_id": str(uuid4())},
        )

        await event_bus._dispatch(payload)

        # 验证 stale_engine.on_change 被调用（URI 含 I2 + 研发回填）
        i2_stale_calls = [c for c in stale_calls if "I2" in c[0] and "研发回填" in c[0]]
        assert len(i2_stale_calls) >= 1, (
            f"I2 保存未触发研发回填 stale_engine.on_change, all calls: {stale_calls}"
        )

    @pytest.mark.asyncio
    async def test_i2_save_emits_cross_ref_updated(self, monkeypatch):
        """I2 保存时发布 CROSS_REF_UPDATED 事件 (target=I6, ref_id=CW-265)"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        async def mock_on_change(uri, project_id, year):
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        pid = uuid4()
        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=pid,
            year=2025,
            extra={"wp_code": "I2", "sheet": "审定表I2-1", "wp_id": str(uuid4())},
        )

        await event_bus._dispatch(payload)

        # 过滤 I-F8 handler 发布的 CROSS_REF_UPDATED 事件（避免被其他订阅干扰）
        cross_ref_events = [
            p for p in published
            if hasattr(p, "event_type")
            and p.event_type == EventType.CROSS_REF_UPDATED
            and isinstance(p.extra, dict)
            and p.extra.get("source_wp_code") == "I2"
        ]
        assert len(cross_ref_events) >= 1, (
            "I2 保存未发布 CROSS_REF_UPDATED 事件, "
            f"published: {[(getattr(p, 'event_type', None), getattr(p, 'extra', None)) for p in published]}"
        )

        evt = cross_ref_events[0]
        assert evt.extra["target_wp_code"] == "I6"
        assert evt.extra["source_wp_code"] == "I2"
        assert evt.extra["ref_id"] == "CW-265"


# ─── Test 5: I6 保存 → stale 传播 + cross-ref:updated 事件 ──────────────────


class TestI6SaveTriggersStaleAndCrossRef:
    """端到端: I6 保存 → stale_engine 传播 + CROSS_REF_UPDATED 事件发布"""

    @pytest.mark.asyncio
    async def test_i6_save_triggers_stale_propagation(self, monkeypatch):
        """I6 保存时 stale_engine.on_change 被调用"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        stale_calls: list[tuple] = []

        async def mock_on_change(uri, project_id, year):
            stale_calls.append((uri, str(project_id), year))
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid4(),
            year=2025,
            extra={"wp_code": "I6", "sheet": "审定表I6-1", "wp_id": str(uuid4())},
        )

        await event_bus._dispatch(payload)

        # 验证 stale_engine.on_change 被调用（URI 含 I6 + 研发回填）
        i6_stale_calls = [c for c in stale_calls if "I6" in c[0] and "研发回填" in c[0]]
        assert len(i6_stale_calls) >= 1, (
            f"I6 保存未触发研发回填 stale_engine.on_change, all calls: {stale_calls}"
        )

    @pytest.mark.asyncio
    async def test_i6_save_emits_cross_ref_updated(self, monkeypatch):
        """I6 保存时发布 CROSS_REF_UPDATED 事件 (target=I2, ref_id=CW-266)"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        async def mock_on_change(uri, project_id, year):
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        pid = uuid4()
        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=pid,
            year=2025,
            extra={"wp_code": "I6", "sheet": "审定表I6-1", "wp_id": str(uuid4())},
        )

        await event_bus._dispatch(payload)

        cross_ref_events = [
            p for p in published
            if hasattr(p, "event_type")
            and p.event_type == EventType.CROSS_REF_UPDATED
            and isinstance(p.extra, dict)
            and p.extra.get("source_wp_code") == "I6"
        ]
        assert len(cross_ref_events) >= 1, (
            "I6 保存未发布 CROSS_REF_UPDATED 事件, "
            f"published: {[(getattr(p, 'event_type', None), getattr(p, 'extra', None)) for p in published]}"
        )

        evt = cross_ref_events[0]
        assert evt.extra["target_wp_code"] == "I2"
        assert evt.extra["source_wp_code"] == "I6"
        assert evt.extra["ref_id"] == "CW-266"


# ─── Test 6: 非 I2/I6 的 wp_code 不触发研发回填 ───────────────────────────


class TestNonRdWpCodeSkipped:
    """验证非 I2/I6 的 wp_code 不触发研发回填 handler"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("wp_code", ["I1", "I3", "I4", "I5", "H1", "D2", "F2"])
    async def test_non_rd_wp_code_no_cross_ref_event(self, monkeypatch, wp_code):
        """非 I2/I6 的 wp_code 不触发 I-F8 handler 的 CROSS_REF_UPDATED 事件"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        stale_calls: list[tuple] = []

        async def mock_on_change(uri, project_id, year):
            stale_calls.append((uri, str(project_id), year))
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid4(),
            year=2025,
            extra={"wp_code": wp_code, "sheet": f"审定表{wp_code}-1", "wp_id": str(uuid4())},
        )

        await event_bus._dispatch(payload)

        # 验证没有 I-F8 来源的 CROSS_REF_UPDATED 事件
        i_rd_events = [
            p for p in published
            if hasattr(p, "event_type")
            and p.event_type == EventType.CROSS_REF_UPDATED
            and isinstance(p.extra, dict)
            and p.extra.get("source_wp_code") in {"I2", "I6"}
        ]
        assert len(i_rd_events) == 0, (
            f"wp_code={wp_code} 不应触发 I-F8 CROSS_REF_UPDATED, got: {i_rd_events}"
        )

        # 同时验证没有"研发回填" stale URI
        i_rd_stale = [c for c in stale_calls if "研发回填" in c[0]]
        assert len(i_rd_stale) == 0, (
            f"wp_code={wp_code} 不应触发研发回填 stale, got: {i_rd_stale}"
        )


# ─── Test 7: 缺少 project_id 或 year 时 handler 跳过 ────────────────────────


class TestMissingFieldsSkipped:
    """验证缺少 project_id 或 year 时 handler 安全跳过"""

    @pytest.mark.asyncio
    async def test_missing_year_skips(self, monkeypatch):
        """year=None 时 handler 不触发 stale 传播"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        stale_calls: list[tuple] = []

        async def mock_on_change(uri, project_id, year):
            stale_calls.append((uri, str(project_id), year))
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid4(),
            year=None,
            extra={"wp_code": "I2", "sheet": "审定表I2-1", "wp_id": str(uuid4())},
        )

        await event_bus._dispatch(payload)

        # 研发回填 handler 应跳过（year=None）
        i_rd_stale = [c for c in stale_calls if "研发回填" in c[0]]
        assert len(i_rd_stale) == 0, (
            f"year=None 时不应触发研发回填 stale, got: {i_rd_stale}"
        )

    @pytest.mark.asyncio
    async def test_missing_extra_skips(self, monkeypatch):
        """extra={} (无 wp_code) 时 handler 不触发"""
        from app.services.stale_propagation_engine import stale_engine
        from app.services.event_bus import event_bus
        from app.services.event_handlers import register_event_handlers

        register_event_handlers()

        stale_calls: list[tuple] = []

        async def mock_on_change(uri, project_id, year):
            stale_calls.append((uri, str(project_id), year))
            return {"affected": [], "total": 0, "degraded": False}

        monkeypatch.setattr(stale_engine, "on_change", mock_on_change)

        published: list = []

        async def mock_publish_immediate(payload):
            published.append(payload)

        monkeypatch.setattr(event_bus, "publish_immediate", mock_publish_immediate)

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=uuid4(),
            year=2025,
            extra={},
        )

        await event_bus._dispatch(payload)

        # 研发回填 handler 应跳过（extra 无 wp_code）
        i_rd_stale = [c for c in stale_calls if "研发回填" in c[0]]
        assert len(i_rd_stale) == 0


# ─── Test 8: CROSS_REF_UPDATED 事件类型存在 ──────────────────────────────────


class TestCrossRefUpdatedEventType:
    """验证 EventType.CROSS_REF_UPDATED 枚举成员存在"""

    def test_enum_member_exists(self):
        assert hasattr(EventType, "CROSS_REF_UPDATED")

    def test_enum_value(self):
        assert EventType.CROSS_REF_UPDATED.value == "cross_ref.updated"
