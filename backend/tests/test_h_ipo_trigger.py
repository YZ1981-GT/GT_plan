"""H-F14 IPO 评估增值核查占位实现 — 单元测试

测试范围:
- _IPO_CONFIG 注册表含 'H1' 入口（codes=[]）
- _ensure_ipo_loaded(prefix='H1') 不抛异常，返回 empty result
- event_handler 暂不订阅 H1 相关事件（占位状态）
- D/F spec 已注册的 IPO trigger 不受影响（回归保留）
"""
from __future__ import annotations

import pytest


# ---- H1 _IPO_CONFIG 注册校验 ------------------------------------------------


def test_h1_ipo_config_registered():
    """_IPO_CONFIG 必须含 H1 入口"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert "H1" in _IPO_CONFIG
    assert _IPO_CONFIG["H1"]["audit_cycle"] == "H"
    assert "codes" in _IPO_CONFIG["H1"]
    assert _IPO_CONFIG["H1"]["codes"] == []


def test_h1_ipo_config_has_name_prefix():
    """H1 入口必须有 name_prefix 字段"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert "name_prefix" in _IPO_CONFIG["H1"]
    assert isinstance(_IPO_CONFIG["H1"]["name_prefix"], str)
    assert len(_IPO_CONFIG["H1"]["name_prefix"]) > 0


# ---- _ensure_ipo_loaded(prefix='H1') 空 codes 安全 ---------------------------


@pytest.mark.asyncio
async def test_ensure_ipo_loaded_h1_no_exception():
    """_ensure_ipo_loaded(prefix='H1') 不抛异常，返回 empty result"""
    from uuid import uuid4

    from app.services.wp_template_init_service import _ensure_ipo_loaded

    result = await _ensure_ipo_loaded(
        None, uuid4(), 2024, wp_code_prefix="H1"
    )
    assert result["prefix"] == "H1"
    assert result["added_codes"] == []
    assert result["skipped_existing"] == []
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_ensure_ipo_loaded_h1_case_insensitive():
    """prefix 大小写不敏感（内部 .upper()）"""
    from uuid import uuid4

    from app.services.wp_template_init_service import _ensure_ipo_loaded

    result = await _ensure_ipo_loaded(
        None, uuid4(), 2024, wp_code_prefix="h1"
    )
    assert result["prefix"] == "h1"
    assert result["added_codes"] == []
    assert result["errors"] == []


# ---- event_handler 不订阅 H1 事件（占位状态）---------------------------------


def test_event_handler_no_h1_subscription():
    """event_handlers 中不应有 H1 相关的事件订阅（占位状态）"""
    import inspect

    from app.services import event_handlers

    src = inspect.getsource(event_handlers)
    # 不应有 H1 专属 handler
    assert "_on_h1_" not in src.lower() or "h1" not in src.lower().split("_on_")[1:]


# ---- D/F spec 回归保留 -------------------------------------------------------


def test_d4_ipo_config_unchanged():
    """D spec 回归：_IPO_CONFIG['D4'] 不受 H1 添加影响"""
    from app.services.wp_template_init_service import D4_IPO_CODES, _IPO_CONFIG

    assert "D4" in _IPO_CONFIG
    assert _IPO_CONFIG["D4"]["audit_cycle"] == "D"
    assert _IPO_CONFIG["D4"]["codes"] is D4_IPO_CODES
    assert len(D4_IPO_CODES) == 12


def test_f2_ipo_config_unchanged():
    """F spec 回归：_IPO_CONFIG['F2'] 不受 H1 添加影响"""
    from app.services.wp_template_init_service import F2_IPO_CODES, _IPO_CONFIG

    assert "F2" in _IPO_CONFIG
    assert _IPO_CONFIG["F2"]["audit_cycle"] == "F"
    assert _IPO_CONFIG["F2"]["codes"] is F2_IPO_CODES
    assert len(F2_IPO_CODES) == 12


def test_ipo_config_total_prefixes():
    """_IPO_CONFIG 应含 D4 + F2 + H1 + J1 = 4 个 prefix"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert len(_IPO_CONFIG) >= 4
    assert {"D4", "F2", "H1", "J1"}.issubset(set(_IPO_CONFIG.keys()))
