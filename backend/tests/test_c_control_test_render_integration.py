"""C2~C15 控制测试弹窗增强 — 集成测试（render 策略 + guidance JSON 完整性）.

Spec: .kiro/specs/c-control-test-popup-enhance/  Task 13.2

覆盖：
  1. render-config 返回 guidance 字段正确性
     - 对有效循环，render() 返回的 html_data 含 guidance（wp_code==C{n}）
       与 guidance_cx2（wp_code==C{n}-2）
     - 无对应 JSON 的 wp_code 时 guidance / guidance_cx2 均为 None
     使用 mock RenderContext（db.execute 返回空结果集），复用仓库既有
     render-strategy 测试的 MagicMock(spec=RenderContext) + AsyncMock 模式。

  2. Property 2: Guidance section 完整渲染
     对任意已加载的 GuidanceData（C2..C15 / C2-2..C15-2），其 sections 数组的
     每一项都有非空 heading + 非空 content，且数量守恒（加载后 section 数 == 文件中
     section 数）。琥珀块前端以 v-for 逐 section 渲染 heading+content，因此后端 JSON
     的 section 完整性等价于渲染结构的 N 对 heading-content 完整性。
     使用 hypothesis，max_examples=5。
     **Validates: Requirements 2.1, 2.3, 4.4, 5.3, 7.1, 7.2**
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._c_control_test import GUIDANCE_DIR, render
from app.routers.wp_render_strategies._context import RenderContext

CYCLE_NUMBERS = list(range(2, 16))


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: 构造 mock RenderContext（db.execute 返回空结果集）
# ═══════════════════════════════════════════════════════════════════════════════


def _make_ctx(wp_code: str) -> RenderContext:
    """构造 mock RenderContext：两次 db.execute（checklist_responses / projects）均返回空。"""
    db = AsyncMock()

    cr_result = MagicMock()
    cr_result.fetchall.return_value = []  # checklist_responses 空

    proj_result = MagicMock()
    proj_result.fetchone.return_value = None  # projects 无行

    db.execute = AsyncMock(side_effect=[cr_result, proj_result])

    ctx = MagicMock(spec=RenderContext)
    ctx.wp_id = "wp-c-test-001"
    ctx.db = db
    ctx.wp_code = wp_code
    ctx.project_id = "proj-c-test-001"
    return ctx


# ═══════════════════════════════════════════════════════════════════════════════
# 1. render-config 返回 guidance 字段正确性
# ═══════════════════════════════════════════════════════════════════════════════


class TestRenderReturnsGuidance:
    """render() 的 html_data 正确包含 guidance / guidance_cx2 字段."""

    @pytest.mark.asyncio
    async def test_render_returns_guidance_for_valid_cycle_c5(self):
        """有效循环 C5：guidance.wp_code==C5，guidance_cx2.wp_code==C5-2."""
        ctx = _make_ctx("C5")
        result = await render(ctx)

        assert result is not None
        assert result["component_type"] == "c-control-test"
        assert result["wp_code"] == "C5"

        # L1 guidance
        assert result["guidance"] is not None, "C5.json 存在，guidance 不应为 None"
        assert result["guidance"]["wp_code"] == "C5"
        assert isinstance(result["guidance"]["sections"], list)
        assert len(result["guidance"]["sections"]) >= 1

        # Cx-2 guidance
        assert result["guidance_cx2"] is not None, "C5-2.json 存在，guidance_cx2 不应为 None"
        assert result["guidance_cx2"]["wp_code"] == "C5-2"
        assert isinstance(result["guidance_cx2"]["sections"], list)
        assert len(result["guidance_cx2"]["sections"]) >= 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("n", CYCLE_NUMBERS)
    async def test_render_guidance_wp_code_matches_cycle(self, n: int):
        """对 C2..C15 每个循环，guidance/guidance_cx2 的 wp_code 与循环号一致."""
        ctx = _make_ctx(f"C{n}")
        result = await render(ctx)

        assert result["guidance"] is not None, f"C{n}.json 应存在"
        assert result["guidance"]["wp_code"] == f"C{n}"
        assert result["guidance_cx2"] is not None, f"C{n}-2.json 应存在"
        assert result["guidance_cx2"]["wp_code"] == f"C{n}-2"

    @pytest.mark.asyncio
    async def test_render_guidance_null_when_no_json(self):
        """无对应 JSON 的 wp_code（如 C999）：guidance 与 guidance_cx2 均为 None，不抛异常."""
        ctx = _make_ctx("C999")
        result = await render(ctx)

        assert result is not None
        assert result["guidance"] is None
        assert result["guidance_cx2"] is None

    @pytest.mark.asyncio
    async def test_render_cx2_standalone_strips_suffix(self):
        """Cx-2 独立底稿 wp_code=C5-2：base 剥离后 guidance 仍加载 C5，guidance_cx2 加载 C5-2."""
        ctx = _make_ctx("C5-2")
        result = await render(ctx)

        # base_wp_code = C5 → guidance 命中 C5.json（而非不存在的 C5-2.json 当 L1）
        assert result["guidance"] is not None
        assert result["guidance"]["wp_code"] == "C5"
        assert result["guidance_cx2"] is not None
        assert result["guidance_cx2"]["wp_code"] == "C5-2"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Property 2: Guidance section 完整渲染
# ═══════════════════════════════════════════════════════════════════════════════


def _load_raw(wp_code: str) -> dict:
    """直接读取 guidance JSON 文件（用于数量守恒对照，绕过 _load_guidance 缓存/校验）."""
    return json.loads((GUIDANCE_DIR / f"{wp_code}.json").read_text(encoding="utf-8"))


class TestProperty2GuidanceSectionCompleteRender:
    """Feature: c-control-test-popup-enhance, Property 2: Guidance section 完整渲染.

    对任意 GuidanceData（N 个 section，N≥1），渲染结构恰好含 N 对 heading-content，
    且每对与源 section 的 heading/content 一致。后端等价校验：加载后 sections 数量守恒，
    每个 section 的 heading 与 content 均为非空字符串。

    **Validates: Requirements 2.1, 2.3, 4.4, 5.3, 7.1, 7.2**
    """

    @settings(max_examples=5)
    @given(n=st.integers(min_value=2, max_value=15))
    def test_l1_guidance_sections_complete(self, n: int):
        """C{n}.json：section 数量守恒 + 每个 section heading/content 非空."""
        ctx = _make_ctx(f"C{n}")
        result = asyncio.run(render(ctx))
        guidance = result["guidance"]
        assert guidance is not None

        raw = _load_raw(f"C{n}")
        # 数量守恒：加载后的 section 数 == 文件中的 section 数
        assert len(guidance["sections"]) == len(raw["sections"]) >= 1

        for i, sec in enumerate(guidance["sections"]):
            assert isinstance(sec.get("heading"), str) and sec["heading"].strip(), (
                f"C{n} section[{i}] heading 应为非空字符串"
            )
            assert isinstance(sec.get("content"), str) and sec["content"].strip(), (
                f"C{n} section[{i}] content 应为非空字符串"
            )
            # 与源文件逐项一致（heading/content 完整保留）
            assert sec["heading"] == raw["sections"][i]["heading"]
            assert sec["content"] == raw["sections"][i]["content"]

    @settings(max_examples=5)
    @given(n=st.integers(min_value=2, max_value=15))
    def test_cx2_guidance_sections_complete(self, n: int):
        """C{n}-2.json：section 数量守恒 + 每个 section heading/content 非空."""
        ctx = _make_ctx(f"C{n}")
        result = asyncio.run(render(ctx))
        guidance = result["guidance_cx2"]
        assert guidance is not None

        raw = _load_raw(f"C{n}-2")
        assert len(guidance["sections"]) == len(raw["sections"]) >= 1

        for i, sec in enumerate(guidance["sections"]):
            assert isinstance(sec.get("heading"), str) and sec["heading"].strip()
            assert isinstance(sec.get("content"), str) and sec["content"].strip()
            assert sec["heading"] == raw["sections"][i]["heading"]
            assert sec["content"] == raw["sections"][i]["content"]
