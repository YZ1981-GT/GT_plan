"""F2 存货审定表 Tier A 取数公式预设 + 读时收敛.

spec: f2-four-table-extraction-refresh

- `load_f2_presets()`：读 `f2_extraction_presets.json`（mtime 缓存），
  返回 F2 Tier A 默认公式绑定列表；文件缺失/解析失败 → `[]`。
- `resolve_effective(db, wp_id, project_id)`：**读时收敛** =
  预设 ∪ 用户 `wp_formula`。每锚点唯一，优先级 **禁用 > 用户 custom > 预设**；
  预设未落库不丢失（同锚点无用户覆盖时仍出现，source=preset）。
  每个绑定的 anchor 经 `f2_extraction.anchor_registry.is_known_anchor` 校验，
  未知锚点丢弃 + 告警。
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpFormula
from app.services.f2_extraction.anchor_registry import is_known_anchor

logger = logging.getLogger(__name__)

# __file__ = backend/app/services/f2_extraction/presets.py
# parents[3] = backend
_PRESETS_PATH: Path = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "f2_extraction"
    / "f2_extraction_presets.json"
)

_DISABLED_CATEGORY = "__disabled__"

# source 枚举
SOURCE_PRESET = "preset"
SOURCE_CUSTOM = "custom"
SOURCE_DISABLED = "disabled"


# ─── Tier A 语义标注 ───────────────────────────────────────────────────────────


def f2_tier_a_semantic(expression: str | None) -> str:
    """返回 F2 Tier A 取数语义标注.

    F2 的 TB() 取数走 **tb_balance**（未审原始余额），与 D 循环 Tier A 走
    trial_balance（审定核对标量）**口径不同**。返回固定文案 + 列名补充。
    """
    if not expression:
        return ""
    return "四表库未审取数（tb_balance，≠ 通用 TB() 的 trial_balance 审定核对）"


# ─── mtime 缓存 ────────────────────────────────────────────────────────────────

_lock = threading.Lock()
_cached_mtime: float | None = None
_cache: list[dict] = []


def _normalize_entry(entry: Any) -> dict | None:
    """把 JSON 预设条目规范化为 Binding dict."""
    if not isinstance(entry, dict):
        return None
    anchor = str(entry.get("anchor") or "").strip()
    expression = str(entry.get("expression") or "").strip()
    if not anchor or not expression:
        return None
    return {
        "anchor": anchor,
        "expression": expression,
        "formula_type": str(entry.get("formula_type") or "auto_calc").strip(),
        "description": str(entry.get("description") or "").strip(),
        "sheet_name": str(entry.get("sheet_name") or "").strip(),
        "source": SOURCE_PRESET,
    }


def _load_from_disk() -> list[dict]:
    """按 mtime 缓存加载 F2 预设条目列表."""
    global _cached_mtime, _cache
    with _lock:
        try:
            mtime = _PRESETS_PATH.stat().st_mtime
        except OSError:
            _cached_mtime = None
            _cache = []
            return _cache

        if _cached_mtime == mtime:
            return _cache

        try:
            raw = json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("f2_extraction_presets 解析失败: %s", exc)
            _cached_mtime = mtime
            _cache = []
            return _cache

        entries: list[dict] = []
        if isinstance(raw, dict):
            f2_list = raw.get("F2")
            if isinstance(f2_list, list):
                for entry in f2_list:
                    norm = _normalize_entry(entry)
                    if norm is not None:
                        entries.append(norm)

        _cached_mtime = mtime
        _cache = entries
        return _cache


# ─── 公开 API ──────────────────────────────────────────────────────────────────


def load_f2_presets() -> list[dict]:
    """返回 F2 Tier A 预设公式绑定列表.

    文件缺失/解析失败/无条目 → `[]`。
    """
    presets = _load_from_disk()
    return [dict(b) for b in presets]


def _is_disabled(formula: WpFormula) -> bool:
    """判定用户 wp_formula 是否为「禁用」标记."""
    category = (formula.category or "").strip()
    expression = (formula.expression or "").strip()
    return category == _DISABLED_CATEGORY or not expression


def _formula_to_binding(formula: WpFormula) -> dict:
    """把用户 WpFormula 转 Binding dict（custom 或 disabled）."""
    disabled = _is_disabled(formula)
    return {
        "anchor": (formula.target_cell or "").strip(),
        "expression": (formula.expression or "").strip(),
        "formula_type": (formula.formula_type or "auto_calc").strip(),
        "description": (formula.description or "").strip(),
        "sheet_name": (formula.sheet_name or "").strip(),
        "source": SOURCE_DISABLED if disabled else SOURCE_CUSTOM,
    }


async def resolve_effective(
    db: AsyncSession,
    wp_id: UUID | str,
    project_id: UUID | str,
) -> list[dict]:
    """读时收敛：预设 ∪ 用户 wp_formula，每锚点唯一（禁用 > custom > 预设）.

    - 预设 anchor 经 `is_known_anchor` 校验，未知丢弃 + warning
    - 用户 wp_formula 按 `WpFormula.wp_id == wp_id` 查询
    - 禁用标记：category == '__disabled__' 或 expression 空

    Returns:
        list[dict]（Binding: {anchor, expression, formula_type, description,
        source, sheet_name}）
    """
    # 1. 预设（校验锚点）
    effective: dict[str, dict] = {}
    for b in load_f2_presets():
        anchor = b["anchor"]
        if not is_known_anchor(anchor):
            logger.warning(
                "F2 预设锚点未知，丢弃: anchor=%s", anchor
            )
            continue
        effective[anchor] = b

    # 2. 用户 wp_formula 覆盖
    try:
        result = await db.execute(
            sa.select(WpFormula).where(WpFormula.wp_id == _as_uuid(wp_id))
        )
        user_formulas = list(result.scalars().all())
    except Exception as e:  # noqa: BLE001
        logger.warning("F2 resolve_effective 读取用户 wp_formula 失败: %s", e)
        user_formulas = []

    for formula in user_formulas:
        anchor = (formula.target_cell or "").strip()
        if not anchor:
            continue
        if not is_known_anchor(anchor):
            logger.warning(
                "F2 用户公式锚点未知，丢弃: anchor=%s", anchor
            )
            continue
        # 用户绑定覆盖同锚点预设（禁用 > custom > 预设）
        effective[anchor] = _formula_to_binding(formula)

    return sorted(
        effective.values(),
        key=lambda b: (b.get("sheet_name", ""), b.get("anchor", "")),
    )


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))
