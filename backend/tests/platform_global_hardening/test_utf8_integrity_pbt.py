"""Feature: platform-global-hardening, Property 4

Property 4: U+FFFD 完整性检查当且仅当含替换字符时失败
check_utf8_integrity 判定失败 SHALL 当且仅当 raw.count(b'\\xef\\xbf\\xbd') > 0；
对 .vue 文件命中时，其报告 SHALL 额外标注「疑似 shell 文本替换破坏」。

Validates: Requirements 3.1, 3.7
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# ─── 以文件路径加载被测守卫脚本（脚本位于 backend/scripts/check，非包）──────────
_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts" / "check" / "check_utf8_integrity.py"
)
_spec = importlib.util.spec_from_file_location("check_utf8_integrity", _SCRIPT)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

FFFD = b"\xef\xbf\xbd"


@settings(max_examples=100)
@given(
    # 任意基础字节内容 + 任意个数（含 0）U+FFFD 注入到随机位置
    base=st.binary(max_size=200),
    n_fffd=st.integers(min_value=0, max_value=10),
    ext=st.sampled_from([".vue", ".ts", ".py", ".md"]),
)
def test_violation_iff_contains_fffd(base: bytes, n_fffd: int, ext: str) -> None:
    """判定违规 iff 字节内容中 U+FFFD 数量 > 0；.vue 命中时报告含破坏标注。"""
    # 构造包含指定数量 U+FFFD 的字节内容（穿插入 base，保证 count 精确可控）
    raw = base + FFFD * n_fffd
    expected_count = raw.count(FFFD)

    # 核心 IFF：is_violation ⇔ count > 0
    assert guard.count_replacement_chars(raw) == expected_count
    assert guard.is_violation(raw) == (expected_count > 0)

    # 报告标注：仅当 .vue 且存在命中时包含「疑似 shell 文本替换破坏」marker
    if expected_count > 0:
        line = guard.format_violation(f"some/path{ext}", expected_count)
        if ext == ".vue":
            assert "疑似 shell 文本替换破坏" in line
        else:
            assert "疑似 shell 文本替换破坏" not in line


@settings(max_examples=100)
@given(base=st.binary(max_size=200))
def test_clean_bytes_never_violation(base: bytes) -> None:
    """不含 U+FFFD 字节序列的内容恒判定为非违规。"""
    # 剔除任何偶然出现的 U+FFFD 子串，保证 clean
    clean = base.replace(FFFD, b"")
    assert guard.count_replacement_chars(clean) == 0
    assert guard.is_violation(clean) is False
