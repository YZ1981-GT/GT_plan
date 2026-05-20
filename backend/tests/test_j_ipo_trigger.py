"""J-F10 IPO 专项触发器（占位实现）— 单元测试

测试范围:
- _IPO_CONFIG 注册表含 'J1' 入口（codes=[]）
- _ensure_ipo_loaded(prefix='J1') 不抛异常，返回 empty result
- D/F/H/I/G 既有 IPO 触发器回归

对应 spec: workpaper-j-payroll-cycle J-F10
"""

import sys
sys.path.insert(0, "backend")

import asyncio
from uuid import uuid4

import pytest


# ---- J1 _IPO_CONFIG 注册校验 ------------------------------------------------


def test_j1_ipo_config_registered():
    """_IPO_CONFIG 必须含 J1 入口"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert "J1" in _IPO_CONFIG
    assert _IPO_CONFIG["J1"]["audit_cycle"] == "J"
    assert "codes" in _IPO_CONFIG["J1"]
    assert _IPO_CONFIG["J1"]["codes"] == []


def test_j1_ipo_config_has_name_prefix():
    """J1 入口必须有 name_prefix 字段"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert "name_prefix" in _IPO_CONFIG["J1"]
    assert isinstance(_IPO_CONFIG["J1"]["name_prefix"], str)
    assert len(_IPO_CONFIG["J1"]["name_prefix"]) > 0


# ---- _ensure_ipo_loaded(prefix='J1') 行为 -----------------------------------


def test_j1_ensure_ipo_loaded_returns_empty_result():
    """_ensure_ipo_loaded(prefix='J1') 不抛异常，返回 empty result"""
    from app.services.wp_template_init_service import _ensure_ipo_loaded

    async def _run():
        # 传入 None db 和假 project_id — codes=[] 时应直接返回 empty
        return await _ensure_ipo_loaded(
            db=None,
            project_id=uuid4(),
            year=2025,
            wp_code_prefix="J1",
        )

    result = asyncio.run(_run())
    assert result["prefix"] == "J1"
    assert result["added_codes"] == []
    assert result["skipped_existing"] == []
    assert result["errors"] == []


def test_j1_ensure_ipo_loaded_case_insensitive():
    """大小写不敏感：'j1' 也能匹配"""
    from app.services.wp_template_init_service import _ensure_ipo_loaded

    async def _run():
        return await _ensure_ipo_loaded(
            db=None,
            project_id=uuid4(),
            year=2025,
            wp_code_prefix="j1",
        )

    result = asyncio.run(_run())
    # 函数内部 .upper() 查找 config，返回的 prefix 可能保留原始输入
    assert result["prefix"].upper() == "J1"
    assert result["added_codes"] == []


# ---- D/F/H 既有 IPO 触发器回归 -----------------------------------------------


def test_d4_ipo_config_unchanged():
    """D spec 回归：_IPO_CONFIG['D4'] 不受 J1 添加影响"""
    from app.services.wp_template_init_service import D4_IPO_CODES, _IPO_CONFIG

    assert "D4" in _IPO_CONFIG
    assert _IPO_CONFIG["D4"]["audit_cycle"] == "D"
    assert _IPO_CONFIG["D4"]["codes"] is D4_IPO_CODES
    assert len(D4_IPO_CODES) == 12


def test_f2_ipo_config_unchanged():
    """F spec 回归：_IPO_CONFIG['F2'] 不受 J1 添加影响"""
    from app.services.wp_template_init_service import F2_IPO_CODES, _IPO_CONFIG

    assert "F2" in _IPO_CONFIG
    assert _IPO_CONFIG["F2"]["audit_cycle"] == "F"
    assert _IPO_CONFIG["F2"]["codes"] is F2_IPO_CODES
    assert len(F2_IPO_CODES) == 12


def test_h1_ipo_config_unchanged():
    """H spec 回归：_IPO_CONFIG['H1'] 不受 J1 添加影响"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert "H1" in _IPO_CONFIG
    assert _IPO_CONFIG["H1"]["audit_cycle"] == "H"
    assert _IPO_CONFIG["H1"]["codes"] == []


def test_ipo_config_total_prefixes():
    """_IPO_CONFIG 应含 D4 + F2 + H1 + J1 = 4 个 prefix"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert len(_IPO_CONFIG) >= 4
    assert {"D4", "F2", "H1", "J1"}.issubset(set(_IPO_CONFIG.keys()))


# ---- 未注册 prefix 降级行为 --------------------------------------------------


def test_unregistered_prefix_returns_error():
    """未注册 prefix 返回 errors 非空"""
    from app.services.wp_template_init_service import _ensure_ipo_loaded

    async def _run():
        return await _ensure_ipo_loaded(
            db=None,
            project_id=uuid4(),
            year=2025,
            wp_code_prefix="ZZ",
        )

    result = asyncio.run(_run())
    assert len(result["errors"]) > 0
    assert "unsupported" in result["errors"][0].get("error", "").lower() or \
           "ZZ" in str(result["errors"])
