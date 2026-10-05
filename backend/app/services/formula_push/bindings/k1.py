"""K1（其他应收款）公式推送 binding。

审定合计 3 键 = derived（推送引擎计算，前端不保存）。
性质行 / 账龄组合 r1 / FS 三项 = editable（用户可改，推送跟随或保留）。
组合 r0/r2/r3 不推（审计判断）。

spec: formula-push-all-subjects-rollout · design §八 · 需求 1.1~1.3
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.services.formula_push.bindings import TargetSkip, WorkpaperTarget, k1_calc
from app.services.formula_push.js_compat import js_number_to_string
from app.services.formula_push.rules import PushRule, workpaper_addr_id
from app.services.formula_push.sources import FormulaSources, load_tb_audited

WP_CODE = "K1"
K1_ACCOUNT_CODES: tuple[str, ...] = ("1221", "1231")

DERIVATIONS: frozenset[str] = frozenset({
    "k1_audited_total",
})


@dataclass
class K1Sources:
    formula: FormulaSources
    warnings: list[str] = field(default_factory=list)


async def load_k1_sources(db, project_id: UUID, year: int, wp_id: UUID | None) -> K1Sources:
    """取齐 K1 推送所需的全部源数据。"""
    warnings: list[str] = []
    tb = await load_tb_audited(db, project_id, year, K1_ACCOUNT_CODES)
    if len(tb.company_codes) > 1:
        warnings.append(f"试算表含多个公司编码 {list(tb.company_codes)}，按全部合计")
    return K1Sources(formula=FormulaSources(tb=tb), warnings=warnings)


class K1Binding:
    wp_code = WP_CODE
    account_prefixes = K1_ACCOUNT_CODES
    derivations = DERIVATIONS
    four_table_slots = frozenset()
    tb_columns = frozenset({"期末余额", "年初余额", "本期发生额"})
    paper_codes = (WP_CODE,)

    load_sources = staticmethod(load_k1_sources)

    def workpaper_targets(
        self, rule: PushRule, entries: Mapping[str, Any], sources: K1Sources,
        *, paper_code: str | None = None,
    ) -> tuple[list[WorkpaperTarget], list[TargetSkip]]:
        target = rule.target
        if target.domain != "workpaper":
            raise ValueError(f"{rule.rule_id} 不是底稿目标")
        kind = rule.source.kind
        if kind == "formula":
            from app.services.formula_engine import execute

            reason = sources.formula.unavailable_reason(rule.source.context_map)
            if reason:
                return [], [TargetSkip(rule.rule_id, workpaper_addr_id(WP_CODE, target.sheet_code, target.item_id), reason)]
            result = execute(rule.source.expression, sources.formula.context_for(rule.source.context_map))
            if result.errors or result.blocked:
                return [], [TargetSkip(rule.rule_id, workpaper_addr_id(WP_CODE, target.sheet_code, target.item_id),
                                       "公式求值失败：" + "；".join(result.errors))]
            value: Any = float(result.value)
        elif kind == "derivation":
            value = self._derive(rule, entries)
        else:
            raise ValueError(f"{rule.rule_id}: K1 不支持 source.kind={kind}")
        addr = workpaper_addr_id(WP_CODE, target.sheet_code, target.item_id)
        return [WorkpaperTarget(
            rule_id=rule.rule_id, policy=rule.policy, addr_id=addr, item_id=target.item_id,
            formula_value=value, current_value=entries.get(target.item_id),
        )], []

    def _derive(self, rule: PushRule, entries: Mapping[str, Any]) -> Any:
        name = rule.source.name
        params = rule.source.params_map
        if name == "k1_audited_total":
            kind = params.get("kind")
            if kind == "receivable":
                return k1_calc.audited_receivable(entries)
            if kind == "baddebt":
                return k1_calc.audited_baddebt(entries)
            if kind == "net":
                return k1_calc.audited_net(entries)
            raise ValueError(f"{rule.rule_id}: k1_audited_total 的 kind={kind!r} 不合法")
        raise ValueError(f"{rule.rule_id}: K1 不支持派生 {name!r}")

    def apply(self, entries: dict[str, Any], target: WorkpaperTarget, value: Any) -> bool:
        old = entries.get(target.item_id)
        new = "" if value is None else js_number_to_string(float(value))
        entries[target.item_id] = new
        return old != new

    def note_rows(self, entries: Mapping[str, Any], template_type: str, rule: PushRule) -> list[dict]:
        return []

    def entry_warnings(self, entries: Mapping[str, Any]) -> list[str]:
        return []
