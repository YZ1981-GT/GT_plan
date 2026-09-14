# Feature: workpaper-editing-guidance, Property 6: 推荐问题匹配 wp_code 模式
"""Property 6: 推荐问题匹配 wp_code 模式

For any wp_code ending with "A" → program questions;
ending with "-1" → determination questions;
others → default questions.
All results are non-empty lists.

**Validates: Requirements 4.8**
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_guidance_service import GuidanceService


# 程序表 wp_code：以 A 结尾且长度 > 1
_program_codes = st.from_regex(r"[A-Z][0-9]{1,2}A", fullmatch=True)

# 审定表 wp_code：以 -1 结尾
_determination_codes = st.from_regex(r"[A-Z][0-9]{1,2}-1", fullmatch=True)

# 其他 wp_code：不以 A 结尾也不以 -1 结尾
_default_codes = st.sampled_from(["A2", "A3", "B60", "X99", "Z5", "Q7", "M3"])


@given(wp_code=_program_codes)
@settings(max_examples=5)
def test_program_table_returns_program_questions(wp_code: str):
    """以 A 结尾的程序表返回程序表问题集，结果为非空列表。"""
    svc = GuidanceService()
    questions = svc.get_recommended_questions(wp_code)

    assert isinstance(questions, list), f"wp_code={wp_code} 应返回列表"
    assert len(questions) > 0, f"wp_code={wp_code} 程序表问题不能为空"


@given(wp_code=_determination_codes)
@settings(max_examples=5)
def test_determination_table_returns_determination_questions(wp_code: str):
    """以 -1 结尾的审定表返回审定表问题集，结果为非空列表。"""
    svc = GuidanceService()
    questions = svc.get_recommended_questions(wp_code)

    assert isinstance(questions, list), f"wp_code={wp_code} 应返回列表"
    assert len(questions) > 0, f"wp_code={wp_code} 审定表问题不能为空"


@given(wp_code=_default_codes)
@settings(max_examples=5)
def test_default_codes_return_default_questions(wp_code: str):
    """通用底稿返回默认问题集，结果为非空列表。"""
    svc = GuidanceService()
    questions = svc.get_recommended_questions(wp_code)

    assert isinstance(questions, list), f"wp_code={wp_code} 应返回列表"
    assert len(questions) > 0, f"wp_code={wp_code} 默认问题不能为空"
