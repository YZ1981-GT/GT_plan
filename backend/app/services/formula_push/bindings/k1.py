"""K1（其他应收款）公式推送 binding。

K1-2 明细表保存的 JSON 可在同一张 K1 工作纸内聚合到 K1-1 组合行未审数，
再由现有 derived 规则计算审定合计 3 键。明细来源缺失或无法解析时跳过目标，
不把来源缺失误写成 0。

审定合计 3 键 = derived（推送引擎计算，前端不保存）。
K1-2 组合原值 / 坏账准备 = editable（明细汇总可跟随，用户手工值保留）。
账龄 / 性质分布仍由前端同步，不由本 binding 推送。

附注推送：``note_rows()`` 从 ``k1_calc`` 取审定净值（receivable − baddebt）推期末，
从试算表 ``年初余额`` 推期初；输出单行 label="其他应收款"。

spec: formula-push-all-subjects-rollout · design §八 · 需求 1.1~1.3
spec: formula-push-note-rollout-batch-c · Task 3
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
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
    "k1_detail_combo_unadj",
    "k1_detail_combo_baddebt",
    "k1_note_main",
})

#: K1-2 明细表 JSON 保存键（与前端 K1TabDetail.persistRows 同源）
K1_DETAIL_ROWS_ITEM = "K1-2-detail-rows"
#: 前端 K1-1 组合行的固定顺序：单项计提、账龄组合、客户类型组合、其他组合
K1_PORTFOLIO_ROW_KEYS = ("r0", "r1", "r2", "r3")

#: 附注推送行标签（与附注模板 note_template_*「其他应收款」主表行名一致）
_NOTE_LABEL = "其他应收款"


@dataclass(frozen=True)
class _K1DetailAggregation:
    """从 K1-2 明细 JSON 得到的可安全写入组合未审数。"""

    receivable: tuple[float, ...]
    baddebt: tuple[float, ...]
    valid_rows: int
    raw_rows: int
    warning: str | None = None


def _finite_number(value: Any) -> float | None:
    """与前端 Number(v) + Number.isFinite 同口径；非法字段不进入汇总。"""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _detail_rows(entries: Mapping[str, Any]) -> _K1DetailAggregation | None:
    """解析 K1-2 明细行；来源缺失/非法时返回 None，禁止把目标刷成零。"""
    raw = entries.get(K1_DETAIL_ROWS_ITEM)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, Mapping):
        raw = raw.get("remark") or raw.get("value")
    if not isinstance(raw, str):
        return _K1DetailAggregation((), (), 0, 0, "K1-2 明细数据不是 JSON 文本，组合未审数未推送")
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _K1DetailAggregation((), (), 0, 0, "K1-2 明细数据 JSON 无法解析，组合未审数未推送")
    if not isinstance(parsed, list):
        return _K1DetailAggregation((), (), 0, 0, "K1-2 明细数据不是数组，组合未审数未推送")

    receivable = [0.0] * len(K1_PORTFOLIO_ROW_KEYS)
    baddebt = [0.0] * len(K1_PORTFOLIO_ROW_KEYS)
    valid_rows = 0
    invalid_rows = 0
    for row in parsed:
        if not isinstance(row, Mapping):
            invalid_rows += 1
            continue
        end = _finite_number(row.get("endBalance"))
        provision = _finite_number(row.get("badDebtProvision"))
        stage = _finite_number(row.get("stage"))
        if end is None or provision is None or stage is None:
            invalid_rows += 1
            continue
        # 与前端 classifyK1Portfolio 一致：stage 3 = individual，其余 = aging。
        row_index = 0 if stage == 3 else 1
        receivable[row_index] += end
        baddebt[row_index] += provision
        valid_rows += 1

    warning = None
    if invalid_rows:
        warning = f"K1-2 明细有 {invalid_rows} 行字段非法，已跳过；有效行 {valid_rows}/{len(parsed)}"
    if not valid_rows:
        warning = warning or "K1-2 明细没有有效行，组合未审数未推送"
    return _K1DetailAggregation(
        tuple(_round2(v) for v in receivable),
        tuple(_round2(v) for v in baddebt),
        valid_rows,
        len(parsed),
        warning,
    )


def _round2(value: float) -> float:
    return round(value * 100) / 100



@dataclass
class K1Sources:
    formula: FormulaSources
    template_type: str | None = None
    warnings: list[str] = field(default_factory=list)


async def _load_template_type(db: Any, project_id: UUID) -> str | None:
    """附注模块渲染用的同一权威（与 TierA / E1 同源，ADR-PUSH-003）。"""
    from app.services.disclosure_engine import DisclosureEngine

    value = await DisclosureEngine(db)._get_active_template_type(project_id)
    return value if isinstance(value, str) and value else None


async def load_k1_sources(db, project_id: UUID, year: int, wp_id: UUID | None) -> K1Sources:
    """取齐 K1 推送所需的全部源数据。"""
    warnings: list[str] = []
    tb = await load_tb_audited(db, project_id, year, K1_ACCOUNT_CODES)
    if len(tb.company_codes) > 1:
        warnings.append(f"试算表含多个公司编码 {list(tb.company_codes)}，按全部合计")
    template_type = await _load_template_type(db, project_id)
    return K1Sources(formula=FormulaSources(tb=tb), template_type=template_type, warnings=warnings)


class K1Binding:
    wp_code = WP_CODE
    account_prefixes = K1_ACCOUNT_CODES
    derivations = DERIVATIONS
    four_table_slots = frozenset()
    tb_columns = frozenset({"期末余额", "年初余额", "本期发生额"})
    paper_codes = (WP_CODE,)

    def __init__(self) -> None:
        # 附注推送用：load_sources 时缓存 TB 数据，note_rows 读取
        self._last_tb_data: Mapping[str, Mapping[str, Decimal]] | None = None

    async def load_sources(self, db, project_id: UUID, year: int, wp_id: UUID | None) -> K1Sources:
        """取齐 K1 推送所需的全部源数据。"""
        sources = await load_k1_sources(db, project_id, year, wp_id)
        # 缓存 TB 数据供 note_rows 使用（engine 的 note_rows 签名不传 sources）
        tb = sources.formula.tb
        self._last_tb_data = tb.tb_data if tb is not None and tb.available else None
        return sources

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
        if name in {"k1_detail_combo_unadj", "k1_detail_combo_baddebt"}:
            aggregation = _detail_rows(entries)
            if aggregation is None or aggregation.valid_rows == 0:
                raise ValueError(
                    f"{rule.rule_id}: {aggregation.warning if aggregation else 'K1-2 明细来源缺失，组合未审数未推送'}"
                )
            kind = "receivable" if name == "k1_detail_combo_unadj" else "baddebt"
            row_key = params.get("row_key")
            if row_key not in K1_PORTFOLIO_ROW_KEYS:
                raise ValueError(f"{rule.rule_id}: K1 组合行 row_key={row_key!r} 不合法")
            index = K1_PORTFOLIO_ROW_KEYS.index(row_key)
            return getattr(aggregation, kind)[index]
        raise ValueError(f"{rule.rule_id}: K1 不支持派生 {name!r}")

    def _detail_target(
        self, rule: PushRule, entries: Mapping[str, Any],
    ) -> tuple[list[WorkpaperTarget], list[TargetSkip]]:
        aggregation = _detail_rows(entries)
        addr = workpaper_addr_id(WP_CODE, rule.target.sheet_code, rule.target.item_id)
        if aggregation is None:
            return [], [TargetSkip(rule.rule_id, addr, "K1-2 明细数据缺失，组合未审数保持原值")]
        if aggregation.valid_rows == 0:
            return [], [TargetSkip(rule.rule_id, addr, aggregation.warning or "K1-2 明细没有有效行，组合未审数保持原值")]
        if aggregation.warning:
            return [], [TargetSkip(rule.rule_id, addr, aggregation.warning + "；为避免部分汇总，本次组合未审数保持原值")]
        name = rule.source.name
        values = aggregation.receivable if name == "k1_detail_combo_unadj" else aggregation.baddebt
        row_key = rule.source.params_map.get("row_key")
        if row_key not in K1_PORTFOLIO_ROW_KEYS:
            raise ValueError(f"{rule.rule_id}: K1 组合行 row_key={row_key!r} 不合法")
        value = values[K1_PORTFOLIO_ROW_KEYS.index(row_key)]
        return [WorkpaperTarget(
            rule_id=rule.rule_id, policy=rule.policy, addr_id=addr, item_id=rule.target.item_id,
            formula_value=value, current_value=entries.get(rule.target.item_id),
        )], []

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
            if rule.source.name in {"k1_detail_combo_unadj", "k1_detail_combo_baddebt"}:
                return self._detail_target(rule, entries)
            value = self._derive(rule, entries)
        else:
            raise ValueError(f"{rule.rule_id}: K1 不支持 source.kind={kind}")
        addr = workpaper_addr_id(WP_CODE, target.sheet_code, target.item_id)
        return [WorkpaperTarget(
            rule_id=rule.rule_id, policy=rule.policy, addr_id=addr, item_id=target.item_id,
            formula_value=value, current_value=entries.get(target.item_id),
        )], []

    def apply(self, entries: dict[str, Any], target: WorkpaperTarget, value: Any) -> bool:
        old = entries.get(target.item_id)
        new = "" if value is None else js_number_to_string(float(value))
        entries[target.item_id] = new
        return old != new

    def note_rows(self, entries: Mapping[str, Any], template_type: str, rule: PushRule) -> list[dict]:
        """K1 附注主表推送：单行"其他应收款"。

        期末 = ``k1_calc.audited_net(entries)``（原值 − 坏账 = 审定净值，从条目计算）；
        期初 = TB ``年初余额`` 合计（codes 1221+1231，试算表口径的上期净值）。
        """
        # ending 从 entries 取审定净值
        ending = k1_calc.audited_net(entries)
        ending_resolved = True  # entries 始终可算（缺项 = 0）

        # opening 从 TB 年初余额取（load_sources 时已缓存）
        tb_data = self._last_tb_data
        if tb_data is not None:
            opening = sum(
                float(tb_data.get(code, {}).get("年初余额", Decimal("0")))
                for code in K1_ACCOUNT_CODES
            )
            opening_resolved = True
        else:
            opening = 0.0
            opening_resolved = False

        return [{
            "key": f"{WP_CODE}-note-main",
            "label": _NOTE_LABEL,
            "note_label": _NOTE_LABEL,
            "is_total": False,
            "is_memo": False,
            "ending": ending,
            "opening": opening,
            "ending_resolved": ending_resolved,
            "opening_resolved": opening_resolved,
        }]

    def entry_warnings(self, entries: Mapping[str, Any]) -> list[str]:
        aggregation = _detail_rows(entries)
        if aggregation is None or not aggregation.warning:
            return []
        return [aggregation.warning]
