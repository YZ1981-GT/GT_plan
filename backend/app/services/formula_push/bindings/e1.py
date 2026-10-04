"""E1 货币资金 binding：取数（DB）+ 规则目标展开 + 写入叠加层。

spec: chain-closure-phase2-formula-push-engine · design §四 · 任务 7 / 8

纯计算全部在 :mod:`e1_calc`（双侧夹具守卫）；本模块只做三件事：

1. :func:`load_e1_sources` —— 四表叶子 / 账户级 / 试算表审定口径 / 大厅已确认调整 / 附注模板类型。
   四表三处取数一律 ``strict=True``：失败上抛，**不**退化成空结果（写入方拿「失败的空」推送会把
   真实金额刷成 0）。
2. :meth:`E1Binding.workpaper_targets` —— 把一条规则展开成若干目标（地址 + 公式值 + 当前值）或跳过原因。
   派生规则读的是**叠加层**（本次运行已决定写入的值），所以同一次运行里「行 → 明细合计 → 审定合计 →
   语义槽 → 附注」逐级生效。
3. :meth:`E1Binding.apply` —— 把决定写入的目标落到叠加层（行字段改行 JSON，单值键改 remark）。
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.services.formula_engine import execute
from app.services.formula_push.bindings import e1_calc
from app.services.formula_push.js_compat import js_number, js_number_to_string
from app.services.formula_push.rules import PushRule, workpaper_addr_id
from app.services.formula_push.sources import FormulaSources, load_hall_adjustments, load_tb_audited

WP_CODE = "E1"
E1_ACCOUNT_CODES: tuple[str, ...] = ("1001", "1002", "1012")
NOTE_TEMPLATE_TYPES: tuple[str, ...] = ("listed", "soe")

#: 本 binding 实现的派生名（规则清单加载时据此校验）
DERIVATIONS: frozenset[str] = frozenset({
    "e1_cash_detail_total",
    "e1_bank_detail_total",
    "e1_adjudicated_total",
    "e1_main_row_slot",
    "e1_disclosure_main_rows",
})


@dataclass
class E1Sources:
    four_table_prefill: dict[str, list[dict]]
    account_prefill: dict[str, Any]
    formula: FormulaSources
    template_type: str | None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorkpaperTarget:
    """一个底稿目标。``row_id``/``field`` 为空 = 单值键（写 remark）。"""

    rule_id: str
    policy: str
    addr_id: str
    item_id: str
    formula_value: Any
    current_value: Any
    row_id: str | None = None
    field: str | None = None
    mirror_field: str | None = None


@dataclass(frozen=True)
class TargetSkip:
    rule_id: str
    addr_id: str | None
    reason: str


@dataclass
class _FourTableCtx:
    """four_table 取数函数只用这 4 个属性（ctx.db / project_id / wp_id / year）。"""

    db: Any
    project_id: UUID
    wp_id: UUID | None
    year: int


async def _load_template_type(db, project_id: UUID) -> str | None:
    """附注模块渲染用的同一权威（DisclosureEngine._get_active_template_type，ADR-PUSH-003）。"""
    from app.services.disclosure_engine import DisclosureEngine

    value = await DisclosureEngine(db)._get_active_template_type(project_id)
    return value if isinstance(value, str) and value else None


async def _load_entity_type(db, project_id: UUID) -> str | None:
    import sqlalchemy as sa

    from app.models.core import Project

    raw = (await db.execute(
        sa.select(Project.applicable_standard_v2).where(Project.id == project_id)
    )).scalar_one_or_none()
    return raw.get("entity_type") if isinstance(raw, dict) else None


async def load_e1_sources(db, project_id: UUID, year: int, wp_id: UUID | None) -> E1Sources:
    """取齐 E1 推送所需的全部源数据（失败即上抛）。"""
    from app.routers.wp_render_strategies._e1_monetary_fund import _build_four_table_extraction

    warnings: list[str] = []
    extraction = await _build_four_table_extraction(
        _FourTableCtx(db=db, project_id=project_id, wp_id=wp_id, year=year), year, strict=True,
    )
    prefill = extraction.get("four_table_prefill") or {}
    four_table = {k: list(prefill.get(k) or []) for k in ("cash", "bank", "other", "finance_co", "digital")}
    source_codes = extraction.get("tb_source_codes") or {}
    if source_codes.get("chart_available") is False:
        warnings.append("本项目科目表不可用，货币资金科目按标准科目编码兜底定位")

    tb = await load_tb_audited(db, project_id, year, E1_ACCOUNT_CODES)
    if len(tb.company_codes) > 1:
        warnings.append(f"试算表含多个公司编码 {list(tb.company_codes)}，试算平衡表数按全部合计")
    hall = await load_hall_adjustments(db, project_id, year, E1_ACCOUNT_CODES)

    template_type = await _load_template_type(db, project_id)
    entity_type = await _load_entity_type(db, project_id)
    if template_type in NOTE_TEMPLATE_TYPES and entity_type in NOTE_TEMPLATE_TYPES and entity_type != template_type:
        label = {"listed": "上市", "soe": "国企"}
        warnings.append(
            f"附注模板为{label[template_type]}版，适用准则为{label[entity_type]}口径；"
            "按附注模板推送（与附注模块显示一致）"
        )
    return E1Sources(
        four_table_prefill=four_table,
        account_prefill=extraction.get("account_prefill") or {},
        formula=FormulaSources(tb=tb, hall_adj=hall),
        template_type=template_type,
        warnings=warnings,
    )


def _number_or_blank(value: float | None) -> str:
    return "" if value is None else js_number_to_string(value)


def _is_stored_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _same_stored(a: Any, b: Any) -> bool:
    """两个存储值是否相同：都空相同、一空一非空不同；数值按 JS ``Number`` 精确比较；非数值全等。"""
    if _is_stored_blank(a) or _is_stored_blank(b):
        return _is_stored_blank(a) and _is_stored_blank(b)
    na, nb = js_number(a), js_number(b)
    if math.isnan(na) or math.isnan(nb):
        return a == b
    return na == nb


def _row_by_id(raw: Any, row_id: str) -> Mapping[str, Any]:
    """行 JSON 中首个 id 命中的行（与 apply_row_pushes / 前端 find 同口径）；无则空。"""
    rows = json.loads(raw) if isinstance(raw, str) and raw else (raw or [])
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, Mapping) and str(row.get("id") or "") == row_id:
            return row
    return {}


class E1Binding:
    wp_code = WP_CODE
    account_prefixes = E1_ACCOUNT_CODES
    derivations = DERIVATIONS

    load_sources = staticmethod(load_e1_sources)

    # ── 目标展开 ────────────────────────────────────────────────────────────

    def workpaper_targets(
        self, rule: PushRule, entries: Mapping[str, Any], sources: E1Sources
    ) -> tuple[list[WorkpaperTarget], list[TargetSkip]]:
        target = rule.target
        if target.domain != "workpaper":
            raise ValueError(f"{rule.rule_id} 不是底稿目标")
        kind = rule.source.kind
        if kind == "four_table_leaves":
            return self._row_targets(rule, entries, sources)
        addr = workpaper_addr_id(WP_CODE, target.sheet_code, target.item_id)
        if kind == "formula":
            reason = sources.formula.unavailable_reason(rule.source.context_map)
            if reason:
                return [], [TargetSkip(rule.rule_id, addr, reason)]
            result = execute(rule.source.expression, sources.formula.context_for(rule.source.context_map))
            if result.errors or result.blocked:
                return [], [TargetSkip(rule.rule_id, addr, "公式求值失败：" + "；".join(result.errors))]
            value: Any = float(result.value)
        else:
            value = self._derive(rule, entries, sources)
            if isinstance(value, e1_calc.Unavailable):
                return [], [TargetSkip(rule.rule_id, addr, value.reason)]
        return [WorkpaperTarget(
            rule_id=rule.rule_id, policy=rule.policy, addr_id=addr, item_id=target.item_id,
            formula_value=value, current_value=entries.get(target.item_id),
        )], []

    def _derive(self, rule: PushRule, entries: Mapping[str, Any], sources: E1Sources) -> Any:
        name, params = rule.source.name, rule.source.params_map
        period = params.get("period")
        if name == "e1_cash_detail_total":
            return e1_calc.cash_detail_total(entries, sources.four_table_prefill.get("cash") or [], period)
        if name == "e1_bank_detail_total":
            variant, _ = e1_calc.bank_variant(entries)
            return e1_calc.bank_detail_total(entries, variant, sources.four_table_prefill, params["group"], period)
        if name == "e1_adjudicated_total":
            return e1_calc.adjudicated_total(entries, params["account_code"], period)
        if name == "e1_main_row_slot":
            return e1_calc.main_row_slot(entries, params["slot"], period)
        raise ValueError(f"{rule.rule_id}: 派生 {name!r} 不产生底稿单值目标")

    def _row_targets(
        self, rule: PushRule, entries: Mapping[str, Any], sources: E1Sources
    ) -> tuple[list[WorkpaperTarget], list[TargetSkip]]:
        target = rule.target
        raw = entries.get(target.item_id)
        if target.item_id == e1_calc.CASH_ROWS_KEY:
            seeds = e1_calc.build_cash_seed_rows(sources.four_table_prefill.get("cash"))
            pushes, skips = e1_calc.plan_cash_row_pushes(raw, seeds)
        elif target.item_id == e1_calc.BANK_ROWS_KEY:
            seeds = e1_calc.bank_seed_rows(sources.four_table_prefill, sources.account_prefill)
            variant, _ = e1_calc.bank_variant(entries)
            pushes, skips = e1_calc.plan_bank_row_pushes(raw, seeds, variant)
        else:
            raise ValueError(f"{rule.rule_id}: 不认识的行集 {target.item_id}")
        allowed = set(target.fields)
        targets = [
            WorkpaperTarget(
                rule_id=rule.rule_id, policy=rule.policy,
                addr_id=workpaper_addr_id(WP_CODE, target.sheet_code, target.item_id,
                                          row_id=p.row_id, field_name=p.field),
                item_id=target.item_id, formula_value=p.value, current_value=p.current,
                row_id=p.row_id, field=p.field, mirror_field=p.mirror_field,
            )
            for p in pushes
            # 规则声明的是本位币三列；多币种原币权威行推的是对应原币列（同一语义字段）
            if p.field in allowed or (p.mirror_field in allowed)
        ]
        skip_list = [
            TargetSkip(rule.rule_id, workpaper_addr_id(WP_CODE, target.sheet_code, target.item_id, row_id=row_id), reason)
            for row_id, reason in skips
        ]
        return targets, skip_list

    # ── 写入叠加层 ──────────────────────────────────────────────────────────

    def apply(self, entries: dict[str, Any], target: WorkpaperTarget, value: Any) -> bool:
        """把 ``value`` 落到叠加层；返回存储值是否真的改变。

        「不变」= 空写（如 composable 占位行 0 → 四表 0）：引擎据此把判定的 write 如实记为 unchanged，
        且不为它落库 / 不计入「后台已更新」—— 只比条目文本会把 JSON 重新序列化误算成改动。
        """
        old = entries.get(target.item_id)
        if target.row_id is None:
            new = _number_or_blank(value)
            entries[target.item_id] = new
            return not _same_stored(old, new)
        new = e1_calc.apply_row_pushes(
            old,
            [e1_calc.RowPush(target.row_id, target.field, float(value), None, mirror_field=target.mirror_field)],
        )
        entries[target.item_id] = new
        before, after = _row_by_id(old, target.row_id), _row_by_id(new, target.row_id)
        fields = [target.field] + ([target.mirror_field] if target.mirror_field else [])
        return any(not _same_stored(before.get(f), after.get(f)) for f in fields)

    # ── 附注 ────────────────────────────────────────────────────────────────

    def note_rows(self, entries: Mapping[str, Any], template_type: str) -> list[dict[str, Any]]:
        return e1_calc.disclosure_main_rows(entries, template_type)

    # ── 运行告警（进运行记录，不静默）────────────────────────────────────────

    def entry_warnings(self, entries: Mapping[str, Any]) -> list[str]:
        warnings: list[str] = []
        _, defaulted = e1_calc.bank_variant(entries)
        if defaulted and entries.get(e1_calc.BANK_ROWS_KEY):
            warnings.append("银行存款明细未记录币种版本，按「人民币及外币」口径汇总（与底稿缺省一致）")
        return warnings
