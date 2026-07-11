"""validate_refs_via_acnr 共享校验 helper 的示例式单元测试（acnr-consumer-wiring Task 9.4）。

覆盖 Task 9.4 要求：
- WP 域引用 ``full_resolve found=false`` → 产出 not_found issue；``found=true`` → 无 issue。
- 非 WP 域引用（TB/REPORT/NOTE 等）→ 路由到 legacy ``validate_formula_refs``。
- 混合表达式：WP 域走 full_resolve、非 WP 域走 legacy，issues 合并且不重复 WP issue。
- 三个调用点（WpFormulaService.save / routers.report_config / routers.wp_user_formulas）
  均委托同一 helper ``validate_refs_via_acnr``。

Monkeypatch 策略（与 9.3 一致）：
- patch resolver 模块的 ``full_resolve``（helper 内部延迟导入
  ``from app.services.acnr.resolver import full_resolve``，故 patch 目标为
  ``app.services.acnr.resolver.full_resolve``）。
- spy legacy ``address_registry.validate_formula_refs``（helper 通过导入的
  singleton ``address_registry`` 调用，故 patch.object 该实例方法）。

Requirements: 9.1, 9.2, 9.4
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr import formula_validation
from app.services.acnr.formula_validation import validate_refs_via_acnr
from app.services.acnr.resolver import ResolveResult
from app.services.address_registry import address_registry

# ─── 常量：受控表达式 ─────────────────────────────────────────────────────────
_WP_REF = "WP('D2','明细表D2-2','E100')"
_TB_REF = "TB('1001','审定数')"
_MIXED_EXPR = f"{_WP_REF} + {_TB_REF}"

_PROJECT_ID = "11111111-1111-1111-1111-111111111111"
_YEAR = 2025
_TEMPLATE = "soe"


def _patch_full_resolve(result_or_exc):
    """构造 patch 上下文：full_resolve 返回给定 ResolveResult 或抛异常。"""
    if isinstance(result_or_exc, Exception):
        mock = AsyncMock(side_effect=result_or_exc)
    else:
        mock = AsyncMock(return_value=result_or_exc)
    return patch("app.services.acnr.resolver.full_resolve", mock), mock


def _spy_legacy(return_value):
    """spy legacy validate_formula_refs（AsyncMock，返回受控 issues）。"""
    return patch.object(
        address_registry,
        "validate_formula_refs",
        new=AsyncMock(return_value=return_value),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. WP 域 found=false → not_found issue
# ═══════════════════════════════════════════════════════════════════════════════
def test_wp_ref_not_found_produces_issue():
    """WP 域引用 full_resolve found=false → 单条 not_found issue（Req 9.4）。"""
    fr_ctx, fr_mock = _patch_full_resolve(ResolveResult(found=False))
    db = MagicMock()

    with fr_ctx, _spy_legacy([]) as legacy_mock:
        issues = asyncio.run(
            validate_refs_via_acnr(db, _PROJECT_ID, _YEAR, _WP_REF, _TEMPLATE)
        )

    assert len(issues) == 1
    issue = issues[0]
    assert issue["ref"] == _WP_REF
    assert issue["status"] == "not_found"
    assert issue["reason"] == "not_found"
    assert "不存在" in issue["message"]
    # 纯 WP 表达式不含非 WP token → legacy 不应被调用
    legacy_mock.assert_not_awaited()
    fr_mock.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. WP 域 found=true → 无 issue
# ═══════════════════════════════════════════════════════════════════════════════
def test_wp_ref_found_yields_no_issue():
    """WP 域引用 full_resolve found=true → 无 issue（Req 9.1）。"""
    fr_ctx, fr_mock = _patch_full_resolve(
        ResolveResult(found=True, addr_id="D2/D2-2/E100")
    )
    db = MagicMock()

    with fr_ctx, _spy_legacy([]):
        issues = asyncio.run(
            validate_refs_via_acnr(db, _PROJECT_ID, _YEAR, _WP_REF, _TEMPLATE)
        )

    assert issues == []
    fr_mock.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 非 WP 域 → 路由到 legacy validate_formula_refs
# ═══════════════════════════════════════════════════════════════════════════════
def test_non_wp_ref_routes_to_legacy():
    """非 WP 域引用（TB）→ 委托 legacy validate_formula_refs（Req 9.4）。"""
    fr_ctx, fr_mock = _patch_full_resolve(ResolveResult(found=True))
    db = MagicMock()
    legacy_issue = {
        "ref": _TB_REF,
        "uri": "tb://1001#审定数",
        "status": "not_found",
        "message": "科目 1001 不存在",
    }

    with fr_ctx, _spy_legacy([legacy_issue]) as legacy_mock:
        issues = asyncio.run(
            validate_refs_via_acnr(db, _PROJECT_ID, _YEAR, _TB_REF, _TEMPLATE)
        )

    # legacy 结果原样返回（无 WP 域引用被过滤）
    assert issues == [legacy_issue]
    legacy_mock.assert_awaited_once_with(
        db, _PROJECT_ID, _YEAR, _TB_REF, _TEMPLATE
    )
    # 无 WP 引用 → full_resolve 不应被调用
    fr_mock.assert_not_awaited()


def test_non_wp_ref_passes_when_legacy_clean():
    """非 WP 域引用 legacy 通过（无 issue）→ 返回空列表。"""
    fr_ctx, _ = _patch_full_resolve(ResolveResult(found=True))
    db = MagicMock()

    with fr_ctx, _spy_legacy([]):
        issues = asyncio.run(
            validate_refs_via_acnr(db, _PROJECT_ID, _YEAR, _TB_REF, _TEMPLATE)
        )

    assert issues == []


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 混合表达式：WP→full_resolve，非 WP→legacy，合并且不重复 WP issue
# ═══════════════════════════════════════════════════════════════════════════════
def test_mixed_expression_splits_and_merges_without_duplicate_wp_issue():
    """混合表达式：WP 域走 full_resolve、非 WP 域走 legacy；

    legacy 若也返回 WP 域 issue 应被过滤，避免重复（Req 9.4）。
    """
    fr_ctx, fr_mock = _patch_full_resolve(ResolveResult(found=False))
    db = MagicMock()
    # legacy 返回 1 条 WP 域 issue（应被过滤）+ 1 条 TB 域 issue（应保留）
    legacy_issues = [
        {"ref": _WP_REF, "status": "not_found", "message": "legacy WP dup"},
        {"ref": _TB_REF, "status": "not_found", "message": "TB miss"},
    ]

    with fr_ctx, _spy_legacy(legacy_issues) as legacy_mock:
        issues = asyncio.run(
            validate_refs_via_acnr(db, _PROJECT_ID, _YEAR, _MIXED_EXPR, _TEMPLATE)
        )

    # WP issue 只来自 full_resolve（1 条），TB issue 来自 legacy（1 条）
    wp_issues = [i for i in issues if i["ref"] == _WP_REF]
    tb_issues = [i for i in issues if i["ref"] == _TB_REF]
    assert len(wp_issues) == 1, "WP 域 issue 不应重复"
    assert wp_issues[0]["message"] != "legacy WP dup", "WP issue 应来自 helper 而非 legacy"
    assert wp_issues[0]["reason"] == "not_found"
    assert len(tb_issues) == 1
    assert tb_issues[0]["message"] == "TB miss"
    assert len(issues) == 2

    fr_mock.assert_awaited_once()  # 仅 1 个 WP 引用
    legacy_mock.assert_awaited_once()  # 含非 WP token → legacy 被调用


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 三个调用点均委托 validate_refs_via_acnr
# ═══════════════════════════════════════════════════════════════════════════════
def test_wp_formula_service_delegates_to_helper():
    """WpFormulaService.save 经模块级导入委托同一 helper 对象（Req 9.1）。"""
    from app.services import wp_formula_service

    # 模块级 `from ... import validate_refs_via_acnr` → 同一函数对象
    assert (
        wp_formula_service.validate_refs_via_acnr
        is formula_validation.validate_refs_via_acnr
    )
    save_src = inspect.getsource(wp_formula_service.WpFormulaService.save)
    assert "validate_refs_via_acnr(" in save_src
    assert "address_registry.validate_formula_refs(" not in save_src


def test_report_config_router_delegates_to_helper():
    """report_config PUT 校验委托 validate_refs_via_acnr（Req 9.2）。"""
    from app.routers import report_config

    src = inspect.getsource(report_config)
    assert (
        "from app.services.acnr.formula_validation import" in src
        and "validate_refs_via_acnr" in src
    )
    assert "await validate_refs_via_acnr(" in src


def test_wp_user_formulas_router_delegates_to_helper():
    """wp_user_formulas PUT 校验委托 validate_refs_via_acnr（Req 9.2）。"""
    from app.routers import wp_user_formulas

    src = inspect.getsource(wp_user_formulas)
    assert (
        "from app.services.acnr.formula_validation import" in src
        and "validate_refs_via_acnr" in src
    )
    assert "await validate_refs_via_acnr(" in src
