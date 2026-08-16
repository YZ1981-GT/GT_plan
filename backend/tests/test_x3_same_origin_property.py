"""test_x3_same_origin_property.py — Property 9: 同源缺陷有消费方或有登记

spec: x3-adjustment-entry-import-export / 任务 13.2*
Validates: Requirements 8.1, 8.2, 8.3, 8.6, 8.7

Property 9 定义：
  对 catalog 中每条 `class_code = F-调整分录` 且 `import_export.enabled` 的条目，
  其 `item_id` 必须满足以下之一：
    (a) 在前端生产代码有消费方（四形态判据任一命中）
    (b) 在 Deviation Registry G1 的 entries 中有登记

即：不存在"catalog 记了、前端没消费、也没被登记为偏差"的孤立条目。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

sys.path.insert(0, "backend")

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FE_SRC = ROOT / "audit-platform" / "frontend" / "src"
WP_DIR = FE_SRC / "components" / "workpaper"
CATALOG_PATH = BACKEND / "data" / "acnr" / "global_catalog.json"
CONTRACT_PATH = BACKEND / "data" / "adjustment_ie_contract.json"
REGISTRY_PATH = ROOT / ".kiro" / "specs" / "x3-adjustment-entry-import-export" / "evidence" / "deviation_registry.json"

_ADJ_CLASS = "F-调整分录"


def _load_catalog_fadj_ie() -> list[dict]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return [
        s for s in catalog.get("sheets", [])
        if s.get("class_code") == _ADJ_CLASS
        and (s.get("import_export") or {}).get("enabled")
    ]


def _load_g1_registered_codes() -> set[str]:
    if not REGISTRY_PATH.exists():
        return set()
    reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    for g in reg.get("groups", []):
        if g.get("group") == "G1":
            return {e.get("key") or e.get("sheet_code", "") for e in g.get("entries", [])}
    return set()


def _has_consumer_literal(item_id: str) -> bool:
    """四形态简化：字面量搜索 + 通配前缀。"""
    if not item_id:
        return False
    search = item_id.replace("-*", "-") if "*" in item_id else item_id
    for p in sorted(FE_SRC.rglob("*")):
        if p.suffix not in (".ts", ".vue", ".js"):
            continue
        posix = p.as_posix()
        if "__tests__" in posix or posix.endswith(".spec.ts"):
            continue
        if search in p.read_text(encoding="utf-8", errors="replace"):
            return True
    return False


def _has_consumer_form4(code: str, item_id: str) -> bool:
    """形态④：ITEM_PREFIX 跨文件拼装。"""
    cycle = code.split("-")[0]
    import fnmatch
    patterns = [f"use{cycle}FormData.ts", f"{cycle}TabAdjust*.vue", f"use{cycle}Adjustment.ts"]
    for p in sorted(FE_SRC.rglob("*")):
        if p.suffix not in (".ts", ".vue"):
            continue
        if "__tests__" in p.as_posix():
            continue
        if not any(fnmatch.fnmatch(p.name, pat) for pat in patterns):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"ITEM_PREFIX\s*=\s*['\"]([^'\"]+)['\"]", src)
        if m:
            prefix_val = m.group(1)
            # 直接匹配：item_id 以 ITEM_PREFIX 开头
            if item_id.startswith(prefix_val):
                return True
            # 间接匹配：同 cycle 前缀 + **契约清单登记的任一后缀**在前端存在
            # 🔴 后缀表必须与 `check_x3_deviation_registry._contract_key_suffixes()`
            #    同源（都读 key_families），否则两处判据分叉：2026-08-16 首轮就因本处
            #    写死 `-entries` 而在 K8-3 上与 probe_g1 判定相反。
            if prefix_val.startswith(f"{cycle}-"):
                for suffix in _contract_suffixes():
                    if _has_consumer_literal(f"{prefix_val}-{suffix}"):
                        return True
    return False


def _contract_suffixes() -> tuple[str, ...]:
    """契约清单登记的全部后缀（单一真源 = `key_families`，禁硬编码）。"""
    global _SUFFIX_CACHE
    if _SUFFIX_CACHE is None:
        doc = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        out: set[str] = set()
        for entry in (doc.get("sheets") or {}).values():
            fams = entry.get("key_families") or {}
            for s in (fams.get("per_field") or {}).get("suffixes") or []:
                if isinstance(s, str) and s:
                    out.add(s.lstrip("-"))
            ds = (fams.get("data") or {}).get("suffix")
            if isinstance(ds, str) and ds:
                out.add(ds.lstrip("-"))
            sj_id = (fams.get("single_json") or {}).get("item_id")
            if isinstance(sj_id, str) and "-" in sj_id:
                out.add(sj_id.rsplit("-", 1)[-1])
        assert out, "契约清单未登记任何后缀 ⇒ 判据退化为恒假（禁空转）"
        _SUFFIX_CACHE = tuple(sorted(out))
    return _SUFFIX_CACHE


_SUFFIX_CACHE: tuple[str, ...] | None = None


# ─── 预加载数据（避免每次 hypothesis 迭代重复 IO）────────────────────────────────
_FADJ_IE = _load_catalog_fadj_ie()
_G1_REGISTERED = _load_g1_registered_codes()


class TestProperty9SameOriginConsumerOrRegistered:
    """Property 9：同源缺陷有消费方或有登记。"""

    @pytest.mark.parametrize(
        "entry",
        _FADJ_IE,
        ids=lambda e: e.get("sheet_code", "?"),
    )
    def test_each_entry_has_consumer_or_registration(self, entry: dict):
        """每条 F-调整分录 IE enabled 的 item_id 必须有消费方或被 G1 登记。"""
        code = entry.get("sheet_code", "?")
        item_id = (entry.get("import_export") or {}).get("item_id", "")

        # (a) 前端有消费方
        has_consumer = _has_consumer_literal(item_id) or _has_consumer_form4(code, item_id)

        # (b) 在 G1 登记
        is_registered = code in _G1_REGISTERED

        assert has_consumer or is_registered, (
            f"{code} 的 catalog item_id={item_id!r} 既无前端消费方又未在 G1 登记 —— "
            f"Property 9 违反（R8.7：不存在孤立条目）"
        )

    def test_denominator_sanity(self):
        """分母 ≥ 40（防空过）。"""
        assert len(_FADJ_IE) >= 40, f"F-调整分录 IE enabled 只有 {len(_FADJ_IE)} 条（< 40）"

    def test_g1_registration_non_empty(self):
        """G1 登记不为空（防空过使 (b) 恒假）。"""
        assert len(_G1_REGISTERED) > 0, "G1 entries 为空 —— deviation_registry.json 可能未生成"
