"""公式推送独占键后端查询（与生成器 gen_formula_push_owned_keys.py 同源同口径）。

按规则清单现算 policy ∈ {system, derived} 的底稿目标 item_id，排除行集目标。
进程内按规则文件 mtime 缓存。

spec: formula-push-all-subjects-rollout · design §五 · 需求 4.3
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from app.services.formula_push.rules import RULES_PATH

_OWNED_POLICIES = frozenset({"system", "derived"})
_EXCLUDED_KINDS = frozenset({"four_table_leaves"})
_PRIMARY_RE = re.compile(r"^([A-Z]\d+)")


@lru_cache(maxsize=4)
def _compute(path: str, mtime_ns: int) -> dict[str, frozenset[str]]:
    """按规则文件和修改时间缓存的独占键集合。"""
    import json

    document = json.loads(Path(path).read_text("utf-8"))
    result: dict[str, set[str]] = {}
    for rule in document.get("rules") or []:
        target = rule.get("target") or {}
        if target.get("domain") != "workpaper":
            continue
        if rule.get("policy") not in _OWNED_POLICIES:
            continue
        source = rule.get("source") or {}
        if source.get("kind") in _EXCLUDED_KINDS:
            continue
        item_id = target.get("item_id")
        if not item_id:
            continue
        wp_code = (rule.get("page_key") or "").split(":", 1)[-1]
        result.setdefault(wp_code, set()).add(item_id)
    return {code: frozenset(items) for code, items in result.items()}


def owned_item_ids(wp_code: str, *, rules_path: Path = RULES_PATH) -> frozenset[str]:
    """返回指定主编码的独占键集合（缓存按文件 mtime）。"""
    p = Path(rules_path)
    try:
        all_owned = _compute(str(p.resolve()), p.stat().st_mtime_ns)
    except FileNotFoundError:
        return frozenset()
    return all_owned.get(wp_code, frozenset())


def is_owned(wp_code: str, item_id: str, *, rules_path: Path = RULES_PATH) -> bool:
    """判断 item_id 是否是指定主编码的独占键。"""
    return item_id in owned_item_ids(wp_code, rules_path=rules_path)


# ── 宽限期：未推送过的项目允许前端双写独占键 ─────────────────────────────────
# spec: formula-push-all-subjects-rollout · design §5.3 风险缓解
# 若该项目从未成功运行过公式推送，独占键剔除不生效（前端双写仍可落库）。
# 一旦推送引擎跑过至少一次（succeeded/partial），剔除立即生效。


async def has_any_push_run(db: "AsyncSession", project_id: "UUID") -> bool:  # noqa: F821
    """检查该项目是否已有过至少一次成功/部分成功的推送运行记录。

    用于宽限期判定：未推送过的项目允许前端双写独占键，
    避免 E1 派生值在首次推送前丢失。

    失败时默认返回 True（即默认执行剔除），防止宽限期因异常被无限延长。
    """
    import sqlalchemy as sa

    try:
        result = await db.execute(
            sa.text(
                "SELECT 1 FROM formula_push_run"
                " WHERE project_id = :pid"
                "   AND status IN ('succeeded', 'partial')"
                " LIMIT 1"
            ),
            {"pid": str(project_id)},
        )
        return result.scalar_one_or_none() is not None
    except Exception:
        # 查询失败（表不存在 / 连接异常等）→ 默认执行剔除（安全侧）
        return True
