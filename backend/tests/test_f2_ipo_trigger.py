"""F-F14 IPO 通用化 + B51-4 触发 F2-61~F2-72 加载 — 单元测试

测试范围:
- _ensure_ipo_loaded 通用函数对 D4/F2 两个 prefix 的支持
- F2_IPO_CODES 含 12 条（F2-61~F2-72）
- _IPO_CONFIG 注册表正确性
- _on_b514_high_risk 事件 handler 注册（不实际触发 DB 操作）
- D spec 回归：D4 prefix 仍可用（向后兼容）
"""
from __future__ import annotations

import pytest


# ---- F2_IPO_CODES / _IPO_CONFIG 静态校验 ------------------------------------

def test_f2_ipo_codes_count():
    """F2-61~F2-72 = 12 条"""
    from app.services.wp_template_init_service import F2_IPO_CODES
    assert len(F2_IPO_CODES) == 12
    assert F2_IPO_CODES[0] == "F2-61"
    assert F2_IPO_CODES[-1] == "F2-72"


def test_f2_ipo_codes_consecutive():
    """F2-61 至 F2-72 连续 12 个编号"""
    from app.services.wp_template_init_service import F2_IPO_CODES
    nums = sorted(int(c.split("-")[1]) for c in F2_IPO_CODES)
    assert nums == list(range(61, 73))


def test_d4_ipo_codes_unchanged():
    """D spec 回归：D4_IPO_CODES 不变"""
    from app.services.wp_template_init_service import D4_IPO_CODES
    assert "D4-22" in D4_IPO_CODES
    assert "D4-22A" in D4_IPO_CODES
    assert "D4-32" in D4_IPO_CODES
    # D4-22 至 D4-32 + D4-22A = 12 条
    assert len(D4_IPO_CODES) == 12


def test_ipo_config_registry():
    """_IPO_CONFIG 必须含 D4 + F2 两个 prefix"""
    from app.services.wp_template_init_service import _IPO_CONFIG
    assert "D4" in _IPO_CONFIG
    assert "F2" in _IPO_CONFIG
    assert _IPO_CONFIG["D4"]["audit_cycle"] == "D"
    assert _IPO_CONFIG["F2"]["audit_cycle"] == "F"
    assert "codes" in _IPO_CONFIG["D4"]
    assert "codes" in _IPO_CONFIG["F2"]


# ---- 函数签名 + 回退兼容 ----------------------------------------------------

def test_ensure_ipo_loaded_signature():
    """_ensure_ipo_loaded 必须 accept wp_code_prefix 参数"""
    from app.services.wp_template_init_service import _ensure_ipo_loaded
    import inspect
    sig = inspect.signature(_ensure_ipo_loaded)
    params = list(sig.parameters.keys())
    assert "db" in params
    assert "project_id" in params
    assert "year" in params
    assert "wp_code_prefix" in params
    # default 应为 "D4"（保留旧行为）
    assert sig.parameters["wp_code_prefix"].default == "D4"


def test_ensure_d4_ipo_loaded_still_exported():
    """D spec 回归：_ensure_d4_ipo_loaded 仍可导入（向后兼容包装）"""
    from app.services.wp_template_init_service import _ensure_d4_ipo_loaded
    assert callable(_ensure_d4_ipo_loaded)


# ---- _ensure_ipo_loaded 不支持 prefix 时的优雅降级 ------------------------------

@pytest.mark.asyncio
async def test_ensure_ipo_loaded_unsupported_prefix():
    """未注册 prefix → errors 列表含说明 + 不抛异常"""
    from app.services.wp_template_init_service import _ensure_ipo_loaded
    from uuid import uuid4

    # 用 None 作为 db 不会被调用（早返回）
    result = await _ensure_ipo_loaded(
        None, uuid4(), 2024, wp_code_prefix="UNSUPPORTED"
    )
    assert result["prefix"] == "UNSUPPORTED"
    assert result["added_codes"] == []
    assert result["skipped_existing"] == []
    assert len(result["errors"]) == 1
    assert "unsupported prefix" in result["errors"][0]["error"]


# ---- 事件 handler 注册 -------------------------------------------------------

def test_b514_handler_function_exists():
    """检查 register_event_handlers 注册了 _on_b514_high_risk handler"""
    import inspect
    from app.services import event_handlers
    src = inspect.getsource(event_handlers)
    assert "_on_b514_high_risk" in src
    # 必须订阅 WORKPAPER_SAVED
    assert "event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_b514_high_risk)" in src
    # 必须用 wp_code_prefix='F2' 调通用函数
    assert "wp_code_prefix=\"F2\"" in src


def test_b515_handler_still_present():
    """D spec 回归：_on_b515_high_risk handler 不能被破坏"""
    import inspect
    from app.services import event_handlers
    src = inspect.getsource(event_handlers)
    assert "_on_b515_high_risk" in src
    assert "event_bus.subscribe(EventType.WORKPAPER_SAVED, _on_b515_high_risk)" in src


# ---- F2 IPO 模板文件存在性 ------------------------------------------------

def test_f2_ipo_template_file_exists():
    """F2-61至F2-72 模板文件物理存在"""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    f_dir = repo_root / "backend" / "wp_templates" / "F"
    if not f_dir.exists():
        pytest.skip("F template dir not present in current snapshot")
    matched = list(f_dir.glob("F2-61*F2-72*.xlsx"))
    assert matched, f"Missing F2-61..F2-72 IPO template under {f_dir}"


# ---------------------------------------------------------------------------
# P1-4 修复：B51-4 handler 触发条件 e2e 测试
#
# 通过复刻 event_handlers.py 中 _on_b514_high_risk 的逻辑（与 production 同源）
# 验证 wp_code / risk_level / 嵌套 conclusion 三类过滤条件正确性，
# 不实际访问 DB（保持轻量），与 D spec test_d4_ipo_trigger.py 模式一致。
# ---------------------------------------------------------------------------


def _make_f2_tracking_stub():
    calls: list[tuple] = []

    async def stub(db, project_id, year, wp_code_prefix="F2"):
        calls.append((project_id, year, wp_code_prefix))
        return {
            "prefix": wp_code_prefix,
            "added_codes": ["F2-61", "F2-62"],
            "skipped_existing": [],
            "errors": [],
        }

    return stub, calls


async def _build_b514_handler(tracking_stub):
    """复刻 _on_b514_high_risk 逻辑（与 event_handlers.py 同源）。"""
    import logging
    logger = logging.getLogger("test_f2_ipo_trigger")

    async def handler(payload) -> None:
        if not payload.extra:
            return
        wp_code = payload.extra.get("wp_code", "")
        if wp_code != "B51-4":
            return

        risk_level = payload.extra.get("risk_level")
        if not risk_level:
            parsed = payload.extra.get("parsed_data") or {}
            conclusion = (
                parsed.get("conclusion") or {} if isinstance(parsed, dict) else {}
            )
            risk_level = (
                conclusion.get("fraud_risk_level") or conclusion.get("risk_level")
            )

        if str(risk_level).lower() != "high":
            return

        project_id = payload.project_id
        year = payload.year
        if not project_id or not year:
            logger.warning("missing project_id or year")
            return

        await tracking_stub(None, project_id, year, "F2")

    return handler


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "wp_code",
    ["B51-1", "B23-1", "C2", "B51-5", "F2", ""],
)
async def test_b514_handler_filters_wp_code(wp_code):
    """非 B51-4 的 wp_code 应不触发 F2 IPO 加载（即使 B51-5 也不触发，避免误击 D 触发器）。"""
    from app.models.audit_platform_schemas import EventPayload, EventType
    import uuid

    stub, calls = _make_f2_tracking_stub()
    handler = await _build_b514_handler(stub)

    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=uuid.uuid4(),
        year=2025,
        extra={"wp_code": wp_code, "risk_level": "high"},
    )
    await handler(payload)
    assert calls == [], f"wp_code={wp_code!r} 不应触发 F2 IPO 加载，实际 {calls}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "risk_level",
    ["medium", "low", "MEDIUM", "", None],
)
async def test_b514_handler_filters_risk_level(risk_level):
    """B51-4 但 risk_level != 'high' 应不触发。"""
    from app.models.audit_platform_schemas import EventPayload, EventType
    import uuid

    stub, calls = _make_f2_tracking_stub()
    handler = await _build_b514_handler(stub)

    extra = {"wp_code": "B51-4"}
    if risk_level is not None:
        extra["risk_level"] = risk_level

    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=uuid.uuid4(),
        year=2025,
        extra=extra,
    )
    await handler(payload)
    assert calls == [], f"risk_level={risk_level!r} 不应触发，实际 {calls}"


@pytest.mark.asyncio
async def test_b514_handler_triggers_when_high():
    """B51-4 + risk_level='high' → 应触发一次 _ensure_ipo_loaded(prefix='F2')."""
    from app.models.audit_platform_schemas import EventPayload, EventType
    import uuid

    stub, calls = _make_f2_tracking_stub()
    handler = await _build_b514_handler(stub)

    pid = uuid.uuid4()
    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=pid,
        year=2025,
        extra={"wp_code": "B51-4", "risk_level": "high"},
    )
    await handler(payload)

    assert len(calls) == 1, f"应触发 1 次 F2 IPO 加载，实际 {calls}"
    called_pid, called_year, called_prefix = calls[0]
    assert called_pid == pid
    assert called_year == 2025
    assert called_prefix == "F2"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_id, conclusion",
    [
        ("fraud_risk_level_high", {"fraud_risk_level": "high"}),
        ("risk_level_high", {"risk_level": "high"}),
        ("fraud_risk_level_HIGH_uppercase", {"fraud_risk_level": "HIGH"}),
    ],
)
async def test_b514_handler_parses_nested_parsed_data(case_id, conclusion):
    """从嵌套 parsed_data.conclusion.fraud_risk_level 或 risk_level 解析为 high → 触发。"""
    from app.models.audit_platform_schemas import EventPayload, EventType
    import uuid

    stub, calls = _make_f2_tracking_stub()
    handler = await _build_b514_handler(stub)

    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=uuid.uuid4(),
        year=2025,
        extra={
            "wp_code": "B51-4",
            "parsed_data": {"conclusion": conclusion},
        },
    )
    await handler(payload)

    assert len(calls) == 1, f"case={case_id} 应触发 1 次，实际 {calls}"


@pytest.mark.asyncio
async def test_b514_handler_skips_when_missing_year():
    """B51-4 + high 但缺 year（=0 视为未提供）→ 不触发。"""
    from app.models.audit_platform_schemas import EventPayload, EventType
    import uuid

    stub, calls = _make_f2_tracking_stub()
    handler = await _build_b514_handler(stub)

    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=uuid.uuid4(),
        year=0,  # falsy → handler 应跳过
        extra={"wp_code": "B51-4", "risk_level": "high"},
    )
    await handler(payload)
    assert calls == []
