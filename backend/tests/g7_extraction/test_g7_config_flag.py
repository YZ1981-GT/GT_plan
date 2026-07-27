"""Wave 0 / Task 1.1 — 灰度开关 G7_FOUR_TABLE_EXTRACTION_ENABLED 默认 False。

对齐 D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED 的命名与默认；关闭时取数路径
逐字节等价于当前行为（Property 5 的最外层锚点）。
"""

from __future__ import annotations

from app.core.config import settings


def test_g7_extraction_flag_default_false():
    """默认关闭：不写库、render 不注入 tb_leaf_categories。"""
    assert settings.G7_FOUR_TABLE_EXTRACTION_ENABLED is False


def test_g7_extraction_flag_is_bool():
    assert isinstance(settings.G7_FOUR_TABLE_EXTRACTION_ENABLED, bool)


def test_g7_flag_aligns_with_d_cycle_naming():
    """与既有灰度开关同名族存在（命名一致性）。"""
    assert hasattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED")
    assert hasattr(settings, "G7_FOUR_TABLE_EXTRACTION_ENABLED")
