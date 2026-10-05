"""Tier A 锚点族 binding（单公式审定表核对行）。

18 个底稿编码 / 21 条锚点，全部是 ``TB(...)`` 单值公式、``policy=system``、无派生、无附注。
通过 ``binding_for(code)`` 工厂按科目实例化，注册表写法形如::

    "D1": "app.services.formula_push.bindings.tier_a:binding_for('D1')"

spec: formula-push-all-subjects-rollout · design §九 · 需求 7.2, 7.3
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from app.services.formula_push.bindings import TargetSkip, WorkpaperTarget
from app.services.formula_push.js_compat import js_number_to_string
from app.services.formula_push.rules import PushRule, workpaper_addr_id
from app.services.formula_push.sources import FormulaSources, load_tb_audited

_PRESETS_PATH = Path(__file__).resolve().parents[4] / "data" / "d_cycle_extraction" / "d_cycle_extraction_presets.json"

#: TB() 第二参数（列名）提取正则
_TB_ARG_RE = re.compile(r"TB\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)")


@dataclass
class TierASources:
    """Tier A binding 的取数结果（只有试算表审定口径）。"""
    formula: FormulaSources
    warnings: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def _load_presets() -> dict[str, list[dict]]:
    """读取预设库（进程内缓存，按文件内容；不含以 ``_`` 开头的元数据键）。"""
    raw = json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if isinstance(v, list) and not k.startswith("_")}


def _extract_account_codes(expression: str) -> tuple[str, ...]:
    """从 ``TB('code','col')`` 表达式提取所有科目码（去重、排序）。"""
    codes = sorted({m.group(1) for m in _TB_ARG_RE.finditer(expression)})
    if not codes:
        raise ValueError(f"表达式 {expression!r} 中未找到 TB() 调用")
    return tuple(codes)


def _presets_for(wp_code: str) -> list[dict]:
    """取指定底稿编码的预设列表；不存在则抛 KeyError。"""
    presets = _load_presets()
    if wp_code not in presets:
        raise KeyError(f"底稿 {wp_code} 在 Tier A 预设库中不存在")
    return presets[wp_code]


def _all_account_codes(wp_code: str) -> tuple[str, ...]:
    """汇总该底稿全部锚点公式里引用的科目码（去重排序）。"""
    codes: set[str] = set()
    for preset in _presets_for(wp_code):
        for m in _TB_ARG_RE.finditer(preset["expression"]):
            codes.add(m.group(1))
    return tuple(sorted(codes))


class TierAAnchorBinding:
    """Tier A 单公式锚点族 binding：只有 ``source/formula`` 单值目标，无派生、无四表叶子、无附注。"""

    def __init__(self, wp_code: str, account_prefixes: tuple[str, ...]) -> None:
        self.wp_code = wp_code
        self.account_prefixes = account_prefixes
        self.derivations: frozenset[str] = frozenset()
        self.four_table_slots: frozenset[str] = frozenset()
        self.tb_columns: frozenset[str] = frozenset({"期末余额", "年初余额"})
        self.paper_codes: tuple[str, ...] = (wp_code,)

    async def load_sources(self, db: Any, project_id: UUID, year: int, wp_id: UUID | None) -> TierASources:
        """取齐推送所需的全部源数据（只有试算表审定口径）。"""
        warnings: list[str] = []
        tb = await load_tb_audited(db, project_id, year, self.account_prefixes)
        if len(tb.company_codes) > 1:
            warnings.append(f"试算表含多个公司编码 {list(tb.company_codes)}，按全部合计")
        return TierASources(formula=FormulaSources(tb=tb), warnings=warnings)

    def workpaper_targets(
        self, rule: PushRule, entries: Mapping[str, Any], sources: TierASources,
        *, paper_code: str | None = None,
    ) -> tuple[list[WorkpaperTarget], list[TargetSkip]]:
        target = rule.target
        if target.domain != "workpaper":
            raise ValueError(f"{rule.rule_id} 不是底稿目标")
        kind = rule.source.kind
        if kind != "formula":
            raise ValueError(f"{rule.rule_id}: Tier A 只支持 formula 来源，收到 {kind!r}")

        addr = workpaper_addr_id(self.wp_code, target.sheet_code, target.item_id)
        reason = sources.formula.unavailable_reason(rule.source.context_map)
        if reason:
            return [], [TargetSkip(rule.rule_id, addr, reason)]

        from app.services.formula_engine import execute
        result = execute(rule.source.expression, sources.formula.context_for(rule.source.context_map))
        if result.errors or result.blocked:
            return [], [TargetSkip(rule.rule_id, addr, "公式求值失败：" + "；".join(result.errors))]
        value: Any = float(result.value)
        return [WorkpaperTarget(
            rule_id=rule.rule_id, policy=rule.policy, addr_id=addr, item_id=target.item_id,
            formula_value=value, current_value=entries.get(target.item_id),
        )], []

    def apply(self, entries: dict[str, Any], target: WorkpaperTarget, value: Any) -> bool:
        """单值键写入；返回存储值是否改变。"""
        old = entries.get(target.item_id)
        new = "" if value is None else js_number_to_string(float(value))
        entries[target.item_id] = new
        return old != new

    def note_rows(self, entries: Mapping[str, Any], template_type: str, rule: PushRule) -> list[dict]:
        """Tier A 无附注规则。"""
        return []

    def entry_warnings(self, entries: Mapping[str, Any]) -> list[str]:
        return []


def binding_for(wp_code: str) -> TierAAnchorBinding:
    """族 binding 工厂：按预设库为指定底稿编码创建 TierAAnchorBinding 实例。"""
    codes = _all_account_codes(wp_code)
    return TierAAnchorBinding(wp_code=wp_code, account_prefixes=codes)
