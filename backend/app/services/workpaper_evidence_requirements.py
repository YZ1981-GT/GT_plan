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


def _parse_evidence_requirements(raw: Any) -> dict[str, list[dict[str, str]]]:
    if not isinstance(raw, dict):
        raise ValueError("证据声明配置顶层必须是对象")
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
            evidence_type = item.get("type")
            label = item.get("label")
            if isinstance(evidence_type, str) and evidence_type and isinstance(label, str) and label:
                cleaned.append({"type": evidence_type, "label": label})
        if cleaned:
            out[key] = cleaned
    return out


def load_evidence_requirements_config_strict() -> dict[str, list[dict[str, str]]]:
    """加载并校验证据声明；正式就绪门使用，错误必须上抛为 ``unknown``。"""
    return _parse_evidence_requirements(json.loads(_CONFIG_PATH.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def load_evidence_requirements_config() -> dict[str, list[dict[str, str]]]:
    """兼容展示路径：配置失败返回空；正式门禁必须调用 strict 版本。"""
    try:
        return load_evidence_requirements_config_strict()
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


#: 精确匹配键前缀：``"=A16"`` 只匹配 A16 本身，不被 A16-1 / A16A 继承（spec attachment-archive-and-a-class-evidence ADR-AE-10）。
EXACT_KEY_PREFIX = "="


def _resolve_requirements(
    wp_code: str | None, cfg: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    if not wp_code:
        return []
    exact = cfg.get(EXACT_KEY_PREFIX + wp_code)
    if exact:
        return list(exact)
    hits = [p for p in cfg if not p.startswith(EXACT_KEY_PREFIX) and matches_wp_code_prefix(wp_code, p)]
    if not hits:
        return []
    return list(cfg[max(hits, key=len)])


def resolve_requirements_for_wp_code_strict(wp_code: str | None) -> list[dict[str, str]]:
    """正式门禁用解析：配置不可读或不合法时上抛，不伪装为无声明。"""
    return _resolve_requirements(wp_code, load_evidence_requirements_config_strict())


def resolve_requirements_for_wp_code(wp_code: str | None) -> list[dict[str, str]]:
    """兼容展示路径；无匹配或配置读取失败返回 []。"""
    return _resolve_requirements(wp_code, load_evidence_requirements_config())


def item_satisfies_type(item: dict[str, Any], req_type: str) -> bool:
    """附件行是否满足某证据类型（attachment_type / association_type / 本底稿行级链接的证据类型 / confirmation 来源）。

    行级链接的类型也算（spec attachment-voucher-evidence-binding 需求 5.1）：从别的底稿引用来的附件，附件本身的
    类型是源底稿上传时选的，在本底稿按链接上的类型（如「凭证 / 原始单据」）作证据。
    """
    if not req_type:
        return False
    if item.get("attachment_type") == req_type:
        return True
    if item.get("association_type") == req_type:
        return True
    if any(isinstance(p, dict) and p.get("evidence_type") == req_type for p in item.get("evidence_positions") or []):
        return True
    sources = item.get("sources") or []
    if req_type == "confirmation" and "confirmation" in sources:
        return True
    if item.get("source") == req_type:
        return True
    return False


def _build_from_declarations(
    declarations: list[dict[str, str]], items: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    if not declarations:
        return None
    return [
        {
            "type": row["type"],
            "label": row["label"],
            "satisfied": any(item_satisfies_type(item, row["type"]) for item in items),
        }
        for row in declarations
    ]


def build_evidence_requirements_strict(
    wp_code: str | None, items: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """正式门禁用构造；配置错误上抛。"""
    return _build_from_declarations(resolve_requirements_for_wp_code_strict(wp_code), items)


def build_evidence_requirements(
    wp_code: str | None,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """兼容展示路径；配置错误保持旧行为并返回 None。"""
    try:
        return _build_from_declarations(resolve_requirements_for_wp_code(wp_code), items)
    except Exception:
        logger.warning("event=awp_evidence_build_fail_open", exc_info=True)
        return None
