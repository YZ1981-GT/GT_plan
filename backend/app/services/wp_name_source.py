"""底稿名称权威源（单一真源）。

根因：多条底稿生成路径（template_engine / wp_conversion._generate /
chain_orchestrator）各自维护 name fallback 链，部分路径**不查
wp_account_mapping.json**，导致 gt_template_library / chain mappings 中缺失的
编码（如 B22A / B23-* / B19-1 / B13-2）落到 "底稿{code}" 占位名。

本模块提供统一的 `resolve_wp_name(code, *candidates)`：
    候选名（模板名/库名，按序取第一个非空）→ wp_account_mapping.json → "底稿{code}"

所有生成路径的**最终兜底**都应经过它，保证名称一致且不再出现 "底稿{code}"。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_MAPPING_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "wp_account_mapping.json"


@lru_cache(maxsize=1)
def get_wp_name_map() -> dict[str, str]:
    """wp_code → wp_name（来自 wp_account_mapping.json，进程内缓存）。

    注：改动 wp_account_mapping.json 后需重启后端才生效（lru_cache）。
    """
    result: dict[str, str] = {}
    try:
        raw = json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
        entries = raw.get("mappings", raw) if isinstance(raw, dict) else raw
        for e in entries:
            if isinstance(e, dict):
                code = e.get("wp_code")
                name = e.get("wp_name")
                if code and name:
                    result.setdefault(code, name)
    except Exception:
        pass
    return result


def resolve_wp_name(wp_code: str, *candidates: str | None) -> str:
    """按序解析底稿名称。

    candidates 依次为各生成路径已有的候选名（模板名、库名等），取第一个非空；
    若均为空则查 wp_account_mapping.json；仍无则回退 "底稿{code}"。
    """
    for c in candidates:
        if c and str(c).strip():
            return str(c)
    mapped = get_wp_name_map().get(wp_code)
    if mapped:
        return mapped
    return f"底稿{wp_code}"
