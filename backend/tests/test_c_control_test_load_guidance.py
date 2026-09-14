"""C2~C15 控制测试弹窗增强 — `_load_guidance` 单元测试 + 属性测试.

Spec: .kiro/specs/c-control-test-popup-enhance/ Task 3.3
被测函数: app.routers.wp_render_strategies._c_control_test._load_guidance

单元测试覆盖:
  1. 文件存在时正确解析返回（含 "sections" 字段）
  2. 文件不存在时返回 None
  3. JSON 格式错误时返回 None
  4. 缺少 "sections" 字段时返回 None

属性测试:
  - Property 1: Guidance 加载 — 有效循环编号 [2,15] 返回正确 guidance
  - Property 7: Guidance 缺失 — 不存在的 wp_code 安全降级返回 None（不抛异常）

**Validates: Requirements 7.1, 7.2, 7.3, 2.6, 3.4**
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies import _c_control_test
from app.routers.wp_render_strategies._c_control_test import _load_guidance

CYCLE_NUMBERS = list(range(2, 16))


# ═══════════════════════════════════════════════════════════════════════════════
# 单元测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestLoadGuidanceUnit:
    """`_load_guidance` 纯函数单元测试（文件存在/缺失/格式错误/缺字段）."""

    def test_existing_file_returns_parsed_dict_with_sections(self):
        """1. 文件存在时正确解析返回，含 sections 字段.

        使用真实存在的 C2.json（由 Task 1 创建）。
        """
        result = _load_guidance("C2")
        assert result is not None, "C2.json 存在，应返回非 None"
        assert isinstance(result, dict)
        assert result["wp_code"] == "C2"
        assert "sections" in result
        assert isinstance(result["sections"], list)
        assert len(result["sections"]) >= 1
        # 每个 section 含 heading/content
        for sec in result["sections"]:
            assert "heading" in sec
            assert "content" in sec

    def test_missing_file_returns_none(self):
        """2. 文件不存在时返回 None（不抛异常）."""
        assert _load_guidance("C999") is None
        assert _load_guidance("DOES_NOT_EXIST") is None

    def test_malformed_json_returns_none(self, tmp_path: Path, monkeypatch):
        """3. JSON 格式错误时返回 None.

        写入一个语法错误的 JSON 文件到临时目录，monkeypatch GUIDANCE_DIR。
        """
        malformed = tmp_path / "CBAD.json"
        malformed.write_text("{ this is not valid json ", encoding="utf-8")
        monkeypatch.setattr(_c_control_test, "GUIDANCE_DIR", tmp_path)

        assert _load_guidance("CBAD") is None

    def test_missing_sections_field_returns_none(self, tmp_path: Path, monkeypatch):
        """4. 缺少 sections 字段时返回 None."""
        no_sections = tmp_path / "CNOSEC.json"
        no_sections.write_text(
            json.dumps({"wp_code": "CNOSEC", "title": "no sections", "source": "static_json"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(_c_control_test, "GUIDANCE_DIR", tmp_path)

        assert _load_guidance("CNOSEC") is None

    def test_non_dict_json_returns_none(self, tmp_path: Path, monkeypatch):
        """JSON 顶层不是 dict（如数组）时返回 None."""
        arr = tmp_path / "CARR.json"
        arr.write_text(json.dumps([{"sections": []}]), encoding="utf-8")
        monkeypatch.setattr(_c_control_test, "GUIDANCE_DIR", tmp_path)

        assert _load_guidance("CARR") is None

    def test_valid_file_with_empty_sections_still_returns_dict(self, tmp_path: Path, monkeypatch):
        """含 sections key（即使为空数组）的 dict 应返回（校验仅检查 key 存在）."""
        empty_sec = tmp_path / "CEMPTY.json"
        empty_sec.write_text(
            json.dumps({"wp_code": "CEMPTY", "sections": [], "source": "static_json"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(_c_control_test, "GUIDANCE_DIR", tmp_path)

        result = _load_guidance("CEMPTY")
        assert result is not None
        assert result["sections"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# Property 1: Guidance 加载 — 有效循环编号返回正确 guidance
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty1GuidanceLoad:
    """Feature: c-control-test-popup-enhance, Property 1: Guidance 加载.

    对于 [2,15] 内任意循环编号 n：
    - _load_guidance("C{n}") 返回非空 dict，wp_code == "C{n}" 且 sections 非空
    - _load_guidance("C{n}-2") 返回 dict，wp_code == "C{n}-2"

    **Validates: Requirements 2.1, 3.1, 7.1, 7.2**
    """

    @settings(max_examples=5)
    @given(n=st.integers(min_value=2, max_value=15))
    def test_l1_guidance_loaded_for_valid_cycle(self, n: int):
        """C{n}.json 加载返回 wp_code == C{n} 且 sections 非空."""
        result = _load_guidance(f"C{n}")
        assert result is not None, f"C{n}.json 应存在并成功加载"
        assert result["wp_code"] == f"C{n}", f"wp_code 应为 C{n}，实际 {result.get('wp_code')}"
        assert isinstance(result["sections"], list)
        assert len(result["sections"]) >= 1, f"C{n} sections 不应为空"

    @settings(max_examples=5)
    @given(n=st.integers(min_value=2, max_value=15))
    def test_cx2_guidance_loaded_for_valid_cycle(self, n: int):
        """C{n}-2.json 加载返回 wp_code == C{n}-2."""
        result = _load_guidance(f"C{n}-2")
        assert result is not None, f"C{n}-2.json 应存在并成功加载"
        assert result["wp_code"] == f"C{n}-2", (
            f"wp_code 应为 C{n}-2，实际 {result.get('wp_code')}"
        )
        assert isinstance(result["sections"], list)
        assert len(result["sections"]) >= 1, f"C{n}-2 sections 不应为空"


# ═══════════════════════════════════════════════════════════════════════════════
# Property 7: Guidance 缺失 — 安全降级
# ═══════════════════════════════════════════════════════════════════════════════


class TestProperty7GuidanceMissingSafeDegrade:
    """Feature: c-control-test-popup-enhance, Property 7: Guidance 缺失 — 安全降级.

    对于任意不对应现有文件的 wp_code 字符串，_load_guidance 返回 None 且不抛异常。

    **Validates: Requirements 2.6, 3.4, 7.3**
    """

    # 生成不会命中现有 C2~C15 / C2-2~C15-2 文件的 wp_code
    _nonexistent_st = st.one_of(
        # 高循环编号（超出 [2,15]）
        st.integers(min_value=16, max_value=9999).map(lambda x: f"C{x}"),
        st.integers(min_value=16, max_value=9999).map(lambda x: f"C{x}-2"),
        # 随机字母数字串（几乎不可能撞上现有文件名）
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=3,
            max_size=20,
        ).filter(lambda s: s not in {f"C{n}" for n in CYCLE_NUMBERS}
                 and s not in {f"C{n}-2" for n in CYCLE_NUMBERS}),
        # 含路径分隔符 / 特殊字符的病态输入
        # NOTE: C1.json 实际存在（C1 向导），故不列入不存在样本
        st.sampled_from(["", "  ", "C", "C-", "../etc/passwd", "C0", "C16", "C100"]),
    )

    @settings(max_examples=5)
    @given(wp_code=_nonexistent_st)
    def test_nonexistent_wp_code_returns_none_without_raising(self, wp_code: str):
        """不存在的 wp_code 返回 None，不抛异常."""
        result = _load_guidance(wp_code)
        assert result is None, f"不存在的 wp_code={wp_code!r} 应返回 None，实际 {result!r}"
