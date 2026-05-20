"""N-F8 IPO 专项触发器（占位实现）— 单元测试

测试范围:
- _IPO_CONFIG 注册表含 'N2' 入口（codes=[]）
- _ensure_ipo_loaded(prefix='N2') 不抛异常，返回 empty result
- D/F/H/J/K/L/M 既有 IPO 触发器回归

对应 spec: workpaper-n-tax-cycle N-F8 / Sprint 3 Task 3.3
"""
from __future__ import annotations

import sys
from uuid import uuid4

import pytest

sys.path.insert(0, "backend")


# ---- N2 _IPO_CONFIG 注册校验 ------------------------------------------------


def test_n2_ipo_config_registered():
    """_IPO_CONFIG 必须含 N2 入口"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert "N2" in _IPO_CONFIG
    assert _IPO_CONFIG["N2"]["audit_cycle"] == "N"
    assert "codes" in _IPO_CONFIG["N2"]
    assert _IPO_CONFIG["N2"]["codes"] == []


def test_n2_ipo_config_has_name_prefix():
    """N2 入口必须有 name_prefix 字段"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert "name_prefix" in _IPO_CONFIG["N2"]
    assert isinstance(_IPO_CONFIG["N2"]["name_prefix"], str)
    assert len(_IPO_CONFIG["N2"]["name_prefix"]) > 0


# ---- _ensure_ipo_loaded(prefix='N2') 行为测试 -------------------------------


@pytest.mark.asyncio
async def test_ensure_ipo_loaded_n2_empty_result():
    """N2 codes=[]，_ensure_ipo_loaded 返回 empty result（不抛异常）"""
    from app.services.wp_template_init_service import _ensure_ipo_loaded

    project_id = uuid4()
    result = await _ensure_ipo_loaded(
        db=None,
        project_id=project_id,
        year=2025,
        wp_code_prefix="N2",
    )

    assert isinstance(result, dict)
    assert result["prefix"] == "N2"
    assert result["added_codes"] == []
    assert result["skipped_existing"] == []
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_ensure_ipo_loaded_n2_lowercase_prefix():
    """大小写不敏感：'n2' 也能命中 N2 配置"""
    from app.services.wp_template_init_service import _ensure_ipo_loaded

    project_id = uuid4()
    result = await _ensure_ipo_loaded(
        db=None,
        project_id=project_id,
        year=2025,
        wp_code_prefix="n2",
    )

    assert isinstance(result, dict)
    assert result["prefix"].upper() == "N2"
    assert result["added_codes"] == []


# ---- D/F/H/J/K/L/M 既有 IPO 触发器回归 --------------------------------------


def test_d4_ipo_config_unchanged():
    """D spec 回归：_IPO_CONFIG['D4'] 不受 N2 添加影响"""
    from app.services.wp_template_init_service import D4_IPO_CODES, _IPO_CONFIG

    assert "D4" in _IPO_CONFIG
    assert _IPO_CONFIG["D4"]["audit_cycle"] == "D"
    assert _IPO_CONFIG["D4"]["codes"] is D4_IPO_CODES
    assert len(D4_IPO_CODES) == 12


def test_f2_ipo_config_unchanged():
    """F spec 回归：_IPO_CONFIG['F2'] 不受 N2 添加影响"""
    from app.services.wp_template_init_service import F2_IPO_CODES, _IPO_CONFIG

    assert "F2" in _IPO_CONFIG
    assert _IPO_CONFIG["F2"]["audit_cycle"] == "F"
    assert _IPO_CONFIG["F2"]["codes"] is F2_IPO_CODES
    assert len(F2_IPO_CODES) == 12


def test_h1_ipo_config_unchanged():
    """H spec 回归：_IPO_CONFIG['H1'] 不受 N2 添加影响"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert "H1" in _IPO_CONFIG
    assert _IPO_CONFIG["H1"]["audit_cycle"] == "H"
    assert _IPO_CONFIG["H1"]["codes"] == []


def test_j1_ipo_config_unchanged():
    """J spec 回归：_IPO_CONFIG['J1'] 不受 N2 添加影响"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert "J1" in _IPO_CONFIG
    assert _IPO_CONFIG["J1"]["audit_cycle"] == "J"
    assert _IPO_CONFIG["J1"]["codes"] == []


def test_k8_ipo_config_unchanged():
    """K spec 回归：_IPO_CONFIG['K8'] 不受 N2 添加影响"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert "K8" in _IPO_CONFIG
    assert _IPO_CONFIG["K8"]["audit_cycle"] == "K"
    assert _IPO_CONFIG["K8"]["codes"] == []


def test_l1_ipo_config_unchanged():
    """L spec 回归：_IPO_CONFIG['L1'] 不受 N2 添加影响"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert "L1" in _IPO_CONFIG
    assert _IPO_CONFIG["L1"]["audit_cycle"] == "L"
    assert _IPO_CONFIG["L1"]["codes"] == []


def test_m2_ipo_config_unchanged():
    """M spec 回归：_IPO_CONFIG['M2'] 不受 N2 添加影响"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert "M2" in _IPO_CONFIG
    assert _IPO_CONFIG["M2"]["audit_cycle"] == "M"
    assert _IPO_CONFIG["M2"]["codes"] == []


def test_ipo_config_total_prefixes():
    """_IPO_CONFIG 应含 D4 + F2 + H1 + J1 + K8 + L1 + M2 + N2 = 8 个 prefix"""
    from app.services.wp_template_init_service import _IPO_CONFIG

    assert len(_IPO_CONFIG) >= 8
    assert {"D4", "F2", "H1", "J1", "K8", "L1", "M2", "N2"}.issubset(
        set(_IPO_CONFIG.keys())
    )


# ---- 未注册 prefix 降级行为 --------------------------------------------------


@pytest.mark.asyncio
async def test_unregistered_prefix_returns_error():
    """未注册 prefix 返回 errors 非空"""
    from app.services.wp_template_init_service import _ensure_ipo_loaded

    project_id = uuid4()
    result = await _ensure_ipo_loaded(
        db=None,
        project_id=project_id,
        year=2025,
        wp_code_prefix="ZZ",
    )

    assert len(result["errors"]) > 0
    assert "unsupported" in result["errors"][0].get("error", "").lower() or \
           "ZZ" in str(result["errors"])
