"""底稿证据类型声明（Req4）— 配置加载 + 前缀匹配 + satisfied 判定。

spec: attachment-workpaper-linkage-convergence Task 5.1
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "workpaper_evidence_requirements.json"
)


@lru_cache(maxsize=1)
def load_evidence_requirements_config() -> dict[str, list[dict[str, str]]]:
    """读取 JSON；失败返回空 dict（fail-open）。忽略 ``_`` 开头注释键。"""
    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[dict[str, str]]] = {}
        for key, val in raw.items():
            if not isinstance(key, str) or key.startswith("_"):
                continue
            if not isinstance(val, list):
                continue
            cleaned: list[dict[str, str]] = []
            for item in val:
                if not isinstance(item, dict):
                    continue
                t = item.get("type")
                label = item.get("label")
                if isinstance(t, str) and t and isinstance(label, str) and label:
                    cleaned.append({"type": t, "label": label})
            if cleaned:
                out[key] = cleaned
        return out
    except Exception:
        logger.warning("event=awp_evidence_config_fail_open", exc_info=True)
        return {}


def clear_evidence_requirements_cache() -> None:
    load_evidence_requirements_config.cache_clear()


def matches_wp_code_prefix(wp_code: str, prefix: str) -> bool:
    """前缀匹配：exact / ``prefix-`` / ``prefix``+字母后缀（E1A）；不匹配 E1→E10。"""
    if not wp_code or not prefix:
        return False
    if wp_code == prefix:
        return True
    if wp_code.startswith(prefix + "-"):
        return True
    if len(wp_code) > len(prefix) and wp_code.startswith(prefix):
        return wp_code[len(prefix)].isalpha()
    return False


def resolve_requirements_for_wp_code(wp_code: str | None) -> list[dict[str, str]]:
    """返回该 wp_code 的声明清单；无匹配返回 []。多前缀命中时取最长前缀。"""
    if not wp_code:
        return []
    cfg = load_evidence_requirements_config()
    hits = [p for p in cfg if matches_wp_code_prefix(wp_code, p)]
    if not hits:
        return []
    best = max(hits, key=len)
    return list(cfg[best])


def item_satisfies_type(item: dict[str, Any], req_type: str) -> bool:
    """附件行是否满足某证据类型（attachment_type / association_type / confirmation 来源）。"""
    if not req_type:
        return False
    if item.get("attachment_type") == req_type:
        return True
    if item.get("association_type") == req_type:
        return True
    sources = item.get("sources") or []
    if req_type == "confirmation" and "confirmation" in sources:
        return True
    if item.get("source") == req_type:
        return True
    return False


def build_evidence_requirements(
    wp_code: str | None,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """构造 additive ``evidence_requirements``；无声明返回 None（不附加键）。"""
    try:
        reqs = resolve_requirements_for_wp_code(wp_code)
        if not reqs:
            return None
        out: list[dict[str, Any]] = []
        for r in reqs:
            t = r["type"]
            satisfied = any(item_satisfies_type(it, t) for it in items)
            out.append({"type": t, "label": r["label"], "satisfied": satisfied})
        return out
    except Exception:
        logger.warning("event=awp_evidence_build_fail_open", exc_info=True)
        return None
