"""D-cycle 锚点登记表加载 + 合法性校验（Wave 0 / Task 1.2）.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/  (Requirements 6.1, 6.2, 6.3)

D-cycle 底稿真实 `checklist_responses` item_id 锚点集，从前端专属组件 composable 反查
（`d_cycle_anchor_registry.json`，非臆造）。Tier B 预填 seed 目标 / Tier A 公式 `target_cell`
必须 ∈ 对应 wp_code 的锚点集，否则拒绝（Property 8 —— 防止提取种子静默写到不存在字段而丢失）。

登记表条目两类：
  * **精确锚点**（普通字符串）：精确相等匹配。
  * **模式锚点**（`re:` 前缀）：已锚定正则，用于动态 rowKey 的 per-field 键
    （rowKey 可为运行时生成 id 或 `deduction`，含连字符，故不能用简单前缀）。

按 mtime 缓存解析后的登记表；文件缺失/解析失败 → 空集合（fail-open，不阻断 render）。
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Pattern

logger = logging.getLogger(__name__)

# __file__ = backend/app/services/d_cycle_extraction/anchor_registry.py
# parents[3] = backend
_REGISTRY_PATH: Path = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "d_cycle_extraction"
    / "d_cycle_anchor_registry.json"
)

_PATTERN_PREFIX = "re:"

# ─── mtime 缓存 ────────────────────────────────────────────────────────────────

_lock = threading.Lock()
_cached_mtime: float | None = None
# wp_code -> (exact_anchors:set[str], compiled_patterns:list[Pattern[str]])
_cache: dict[str, tuple[set[str], list[Pattern[str]]]] = {}

# `_seed_fields.map` 缓存（wp_code -> {anchor: field}），独立 mtime 缓存
_seed_cached_mtime: float | None = None
_seed_cache: dict[str, dict[str, str]] = {}


def _parse_entries(entries: list) -> tuple[set[str], list[Pattern[str]]]:
    """把登记表某 wp_code 的条目列表拆成 (精确集合, 编译后的正则列表)。"""
    exact: set[str] = set()
    patterns: list[Pattern[str]] = []
    for entry in entries:
        if not isinstance(entry, str):
            continue
        if entry.startswith(_PATTERN_PREFIX):
            expr = entry[len(_PATTERN_PREFIX):]
            try:
                patterns.append(re.compile(expr))
            except re.error:
                logger.warning("d_cycle_anchor_registry: 非法正则锚点被跳过: %r", entry)
        else:
            exact.add(entry)
    return exact, patterns


def _load() -> dict[str, tuple[set[str], list[Pattern[str]]]]:
    """按 mtime 缓存加载登记表。缺失/解析失败 → 空 dict（fail-open）。"""
    global _cached_mtime, _cache
    with _lock:
        try:
            mtime = _REGISTRY_PATH.stat().st_mtime
        except OSError:
            # 文件不存在
            _cached_mtime = None
            _cache = {}
            return _cache

        if _cached_mtime == mtime and _cache:
            return _cache

        try:
            raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("d_cycle_anchor_registry 解析失败: %s", exc)
            _cached_mtime = mtime
            _cache = {}
            return _cache

        parsed: dict[str, tuple[set[str], list[Pattern[str]]]] = {}
        for wp_code, entries in raw.items():
            if wp_code.startswith("_"):  # 跳过 _meta 等元数据键
                continue
            if isinstance(entries, list):
                parsed[wp_code] = _parse_entries(entries)

        _cached_mtime = mtime
        _cache = parsed
        return _cache


# ─── 公开 API ──────────────────────────────────────────────────────────────────


def known_anchors(wp_code: str) -> set[str]:
    """返回某 wp_code 的**精确**已知锚点集合（不含模式锚点）.

    模式锚点（动态 rowKey per-field）不是有限集合，无法枚举；
    需判定某具体 item_id 是否已知锚点时用 `is_known_anchor`（同时匹配精确 + 模式）。
    """
    registry = _load()
    entry = registry.get(wp_code)
    if entry is None:
        return set()
    exact, _patterns = entry
    return set(exact)


def is_known_anchor(wp_code: str, anchor: str) -> bool:
    """判定 `anchor` 是否属于 `wp_code` 的已知锚点集（精确 或 模式匹配）.

    未知锚点返回 False → 调用方应拒绝/告警，不静默写空（Property 8 / Req 6.2）。
    """
    if not wp_code or not anchor:
        return False
    registry = _load()
    entry = registry.get(wp_code)
    if entry is None:
        return False
    exact, patterns = entry
    if anchor in exact:
        return True
    return any(p.match(anchor) for p in patterns)


def registered_wp_codes() -> set[str]:
    """当前登记表已覆盖的 wp_code 集合（供诊断/测试）。"""
    return set(_load().keys())


def _load_seed_fields() -> dict[str, dict[str, str]]:
    """按 mtime 缓存加载 `_seed_fields.map`（wp_code -> {anchor: 字段名}）.

    spec: d-cycle-tier-a-writeback-detail-seed 决策2 / R3.7 —— render transient seed
    须写入前端 composable 实际读取的 responses_snapshot 字段（remark vs conclusion），
    逐锚点从 composable 反查后登记于 registry 的 `_seed_fields.map`。文件缺失/解析失败
    / 无该键 → 空 dict（fail-open，调用方按无登记处理即不 seed 该锚点）。
    """
    global _seed_cached_mtime, _seed_cache
    with _lock:
        try:
            mtime = _REGISTRY_PATH.stat().st_mtime
        except OSError:
            _seed_cached_mtime = None
            _seed_cache = {}
            return _seed_cache

        if _seed_cached_mtime == mtime and _seed_cache:
            return _seed_cache

        try:
            raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("d_cycle_anchor_registry `_seed_fields` 解析失败: %s", exc)
            _seed_cached_mtime = mtime
            _seed_cache = {}
            return _seed_cache

        parsed: dict[str, dict[str, str]] = {}
        seed_block = raw.get("_seed_fields") if isinstance(raw, dict) else None
        seed_map = seed_block.get("map") if isinstance(seed_block, dict) else None
        if isinstance(seed_map, dict):
            for wp_code, anchors in seed_map.items():
                if isinstance(anchors, dict):
                    parsed[wp_code] = {
                        str(a): str(f) for a, f in anchors.items() if f
                    }

        _seed_cached_mtime = mtime
        _seed_cache = parsed
        return _seed_cache


def seed_field(wp_code: str, anchor: str) -> str | None:
    """返回某 wp_code + anchor 的 render transient seed 目标字段（remark / conclusion）.

    仅对 `_seed_fields.map` 登记的 TB 核对行锚点返回字段名；未登记（非 TB 核对行 seed
    目标，如 note/明细行）→ None（调用方据此跳过 seed，只 seed 已核实读取字段的锚点，
    防 L1 式错列 round-trip 断裂 / 决策2 / R3.7）。
    """
    if not wp_code or not anchor:
        return None
    return _load_seed_fields().get(wp_code, {}).get(anchor)
