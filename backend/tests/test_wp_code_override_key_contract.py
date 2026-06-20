"""Override KEY 真实性契约测试（P2）

补充 `test_wp_code_override_contract.py`（仅校验 value 合法），本测试校验
`_WP_CODE_OVERRIDE` 的 **key（wp_code）真实存在**，防止拼错或循环改版废弃后
override 静默失效（孤儿 override）。

校验逻辑：override key 须满足以下之一：
  1. 直接命中"已知 wp_code 全集"（聚合 backend/data + backend/app/data 全部
     含 wp_code/code 的 JSON 数据源）
  2. 去合法后缀后命中全集：
     - 程序表底稿后缀 `A`（如 K1A→K1、L7A→L7）
     - 多 sheet 子表后缀 `-N`（如 A11-2→A11、A13-5→A13）

新增 override 若 key 既不在全集、去后缀也匹配不到，即判定为孤儿，测试失败。
"""
from __future__ import annotations

import glob
import json
import os
import re

_BASE = os.path.join(os.path.dirname(__file__), "..")
_DATA_DIRS = [
    os.path.join(_BASE, "data"),
    os.path.join(_BASE, "app", "data"),
]

# 去后缀规则：程序表 A 后缀、子表 -N 后缀
_SUFFIX_PATTERNS = [
    re.compile(r"A$"),       # K1A -> K1
    re.compile(r"-\d+$"),    # A11-2 -> A11
]


def _collect_known_wp_codes() -> set[str]:
    """聚合所有数据源 JSON 中的 wp_code / code 字段。"""
    known: set[str] = set()
    for d in _DATA_DIRS:
        for fp in glob.glob(os.path.join(d, "*.json")):
            try:
                with open(fp, encoding="utf-8-sig") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            items = (
                data
                if isinstance(data, list)
                else (
                    data.get("mappings")
                    or data.get("templates")
                    or data.get("rules")
                    or []
                )
            )
            if not isinstance(items, list):
                continue
            for x in items:
                if isinstance(x, dict):
                    code = x.get("wp_code") or x.get("code")
                    if code:
                        known.add(code)
    return known


def _matches_known(code: str, known: set[str]) -> bool:
    if code in known:
        return True
    for pat in _SUFFIX_PATTERNS:
        base = pat.sub("", code)
        if base != code and base in known:
            return True
    return False


def test_all_override_keys_are_real_wp_codes():
    """所有 override key 须命中已知 wp_code 全集（或去合法后缀后命中）。

    失败即说明存在孤儿 override（拼错/循环改版废弃），override 会静默失效。
    """
    from app.services.wp_classification_service import _WP_CODE_OVERRIDE

    known = _collect_known_wp_codes()
    assert known, "未能从数据源聚合到任何 wp_code，校验前置条件失败"

    orphans = sorted(k for k in _WP_CODE_OVERRIDE if not _matches_known(k, known))
    assert not orphans, (
        f"发现 {len(orphans)} 个孤儿 override（key 不在任何数据源、去后缀也匹配不到）:\n"
        + "\n".join(f"  {k!r} -> {_WP_CODE_OVERRIDE[k]!r}" for k in orphans)
        + "\n请确认 wp_code 拼写正确，或该底稿是否已废弃。"
    )
