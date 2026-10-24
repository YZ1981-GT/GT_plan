"""附注直推族 binding（简单型科目：底稿审定表锚点 + 附注主表推送）。

57 个未注册主编码通过 ``note_direct_for(code)`` 工厂按科目实例化，注册表写法形如::

    "G1": "app.services.formula_push.bindings.note_direct:note_direct_for('G1')"

与 Tier A 的区别：
- Tier A 从预设库（``d_cycle_extraction_presets.json``）取科目码；
  NoteDirectBinding 从 ``wp_account_mapping.json`` 取 —— J / L / M 循环例外，改取四表口径单一来源
  （见 :func:`_single_source_codes`）。
- Tier A 只有底稿锚点（``stage=source``）；
  NoteDirectBinding 同时有底稿锚点 + 附注推送（``stage=note``）。
- 两者不合并——Tier A 已在生产运行且有 250+ 测试守护，改动风险高于新建。

附注推送通过 ``note_rows()`` 从试算表取审定数构建附注行。
损益类科目（标准码 6 开头）自动用 ``本期发生额`` 取数。

spec: formula-push-note-rollout-batch-d · design §1~§3
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from app.services.formula_push.bindings import TargetSkip, WorkpaperTarget
from app.services.formula_push.js_compat import js_number_to_string
from app.services.formula_push.rules import PushRule, workpaper_addr_id
from app.services.formula_push.sources import FormulaSources, load_tb_audited

_DATA_DIR = Path(__file__).resolve().parents[4] / "data"
_WP_MAPPING_PATH = _DATA_DIR / "wp_account_mapping.json"

#: 损益类科目前缀（6 开头）
_PL_PREFIX = "6"

#: 附注主表按「账面余额 / 跌价准备 / 账面价值」写合计行的底稿 → 试算表科目区间（spec formula-fetch-followup-defect-closure R6.1）。
#:
#: 🔴 F2 存货原先逐码出行（映射表的 1401 / 1402 / 1403 / 1405 / 1408 / 1461），合计行把 1461 存货跌价准备当正数加进存货；
#:    且映射表码不全 —— 同一个码在两套标准科目表变体里是不同科目（``f2_extraction.category_rules`` 实证：1406 一半项目是
#:    库存商品、一半是发出商品；存货跌价准备落在 1416 / 1461 / 1471），和平 2025 的 1406 库存商品 1.2 亿、1416 跌价准备
#:    都不在那 6 个码里。改为：取报表 BS-010 同一区间（``f_cycle_specs``：``SUM_TB('1401~1499')``）的全部试算表行，
#:    按科目名归类（同一单一来源 ``classify_f2_category``，F2 审定表也用它）：跌价准备 / 减值准备计入跌价准备列，
#:    商品进销差价从账面余额中减去，其余计入账面余额；账面价值 = 账面余额 − 跌价准备。只写合计行，明细行由底稿同步。
_BOOK_VALUE_RANGES: dict[str, tuple[str, str]] = {"F2": ("1401", "1499")}
#: 合计行六个字段：与底稿同步写入的「存货分类」列键一致（真库 ``_sub_table_columns['存货分类']``）
BOOK_VALUE_FIELDS: tuple[str, ...] = (
    "end_gross", "end_impairment", "end_net", "prior_gross", "prior_impairment", "prior_net",
)

#: 口径单一来源没有标准科目的底稿：不取试算表、不推附注主表，相关格子交给用户填写（规则清单里也不得有它们的取数规则）。
_NO_ACCOUNT_REASONS: dict[str, str] = {
    "L7": "其他非流动负债是报表行、由多个明细科目归集，没有标准科目（l_cycle_specs 不给兜底码）；"
          "原映射表写的 2801 是 K5 预计负债",
    "M8": "一般风险准备没有标准科目（各项目科目表都没有该科目，m_cycle_specs 不给兜底码）；原映射表写的 4301 是专项储备",
    "D5": "应收款项融资没有可取数的科目（各项目科目表与试算表都没有 1124，d_cycle_specs 不给兜底码）；"
          "原映射表与推送规则取的 1124 推出来恒为 0",
}


@dataclass
class NoteDirectSources:
    """NoteDirectBinding 的取数结果（只有试算表审定口径）。"""
    formula: FormulaSources
    template_type: str | None = None
    warnings: list[str] = field(default_factory=list)


# ── 数据加载 ────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _load_wp_mapping() -> dict[str, dict]:
    """按 wp_code 加载完整映射条目（仅主编码），进程内缓存。"""
    raw = json.loads(_WP_MAPPING_PATH.read_text(encoding="utf-8"))
    import re
    primary_re = re.compile(r"^[A-Z]\d+$")
    result: dict[str, dict] = {}
    for item in raw.get("mappings", []):
        code = item.get("wp_code", "")
        if primary_re.fullmatch(code) and code not in result:
            result[code] = item
    return result


def _is_pl_code(code: str) -> bool:
    """损益类科目：标准码以 6 开头。"""
    return code.startswith(_PL_PREFIX)


def _tb_value(
    tb_data: Mapping[str, Mapping[str, Decimal]], code: str, column: str,
) -> tuple[float, bool]:
    """从 TB 快照取值；返回 ``(value, resolved)``。``resolved=False`` = 科目不存在。"""
    bucket = tb_data.get(code)
    if bucket is None:
        return 0.0, False
    raw = bucket.get(column, Decimal("0"))
    return float(raw), True


# ── NoteDirectBinding ───────────────────────────────────────────────────────


class NoteDirectBinding:
    """简单型附注直推族 binding：底稿审定表锚点 + 附注主表推送。

    通过 :func:`note_direct_for` 工厂按科目码实例化。
    """

    def __init__(
        self,
        wp_code: str,
        account_codes: tuple[str, ...],
        account_name: str,
        *,
        is_income: bool = False,
        no_account_reason: str = "",
        book_value_range: tuple[str, str] | None = None,
    ) -> None:
        if not account_codes and not no_account_reason:
            raise ValueError(f"{wp_code}: 没有科目时必须写明 no_account_reason")
        #: 非空 = 附注主表按账面余额 / 跌价准备 / 账面价值写合计行（见 ``_BOOK_VALUE_RANGES``）
        self._book_value_range = book_value_range
        self._last_book_values: dict[str, Any] | None = None
        self.wp_code = wp_code
        self.account_prefixes = account_codes
        #: 非空 = 本科目没有标准科目（bindings 校验据此放行空 account_prefixes）
        self.no_account_reason = no_account_reason if not account_codes else ""
        self.tb_columns: frozenset[str] = frozenset({"期末余额", "年初余额", "本期发生额"})
        # 附注主表取自试算表；没有科目就没有附注主表推送
        self.derivations: frozenset[str] = (
            frozenset({f"{wp_code.lower()}_note_main"}) if account_codes else frozenset()
        )
        self.four_table_slots: frozenset[str] = frozenset()
        self.paper_codes: tuple[str, ...] = (wp_code,)
        self._is_income = is_income
        self._account_name = account_name
        # load_sources 缓存 TB 数据供 note_rows 使用（engine 的 note_rows 签名不传 sources）
        self._last_tb_data: Mapping[str, Mapping[str, Decimal]] | None = None

    async def load_sources(
        self, db: Any, project_id: UUID, year: int, wp_id: UUID | None,
    ) -> NoteDirectSources:
        """取齐推送所需的全部源数据（只有试算表审定口径）。"""
        warnings: list[str] = []
        tb = await load_tb_audited(db, project_id, year, self.account_prefixes)
        if len(tb.company_codes) > 1:
            warnings.append(f"试算表含多个公司编码 {list(tb.company_codes)}，按全部合计")
        self._last_tb_data = tb.tb_data if tb.available else None
        self._last_book_values = None
        if self._book_value_range is not None and tb.available:
            self._last_book_values = await _load_book_values(db, project_id, year, *self._book_value_range)
        template_type = await _load_template_type(db, project_id)
        return NoteDirectSources(formula=FormulaSources(tb=tb), template_type=template_type, warnings=warnings)

    def workpaper_targets(
        self, rule: PushRule, entries: Mapping[str, Any], sources: NoteDirectSources,
        *, paper_code: str | None = None,
    ) -> tuple[list[WorkpaperTarget], list[TargetSkip]]:
        """底稿锚点目标（单值公式）。"""
        target = rule.target
        if target.domain != "workpaper":
            raise ValueError(f"{rule.rule_id} 不是底稿目标")
        kind = rule.source.kind
        if kind != "formula":
            raise ValueError(f"{rule.rule_id}: NoteDirectBinding 只支持 formula 来源，收到 {kind!r}")

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
        """从试算表取审定数构建附注行。

        单科目：一行数据（label=科目名, ending=TB审定数, opening=TB年初数）。
        多科目：每个科目一行 + 合计行。
        损益类（科目码 6 开头）：ending 取「本期发生额」，opening 取「年初余额」。

        返回格式与 E1 / Tier A 的 ``note_rows`` 一致：
        ``[{key, label, note_label, is_total, is_memo, ending, opening, ending_resolved, opening_resolved}]``
        """
        tb_data = self._last_tb_data
        if tb_data is None:
            return []
        if self._book_value_range is not None:
            return self._book_value_rows(rule)

        codes = self.account_prefixes
        rows: list[dict] = []
        for code in codes:
            is_pl = _is_pl_code(code)
            ending_col = "本期发生额" if is_pl else "期末余额"
            opening_col = "年初余额"
            ending, ending_resolved = _tb_value(tb_data, code, ending_col)
            opening, opening_resolved = _tb_value(tb_data, code, opening_col)
            label = self._account_name if len(codes) == 1 else f"{self._account_name}_{code}"
            rows.append({
                "key": f"{self.wp_code}-note-{code}",
                "label": label,
                "note_label": label,
                "is_total": False,
                "is_memo": False,
                "ending": ending,
                "opening": opening,
                "ending_resolved": ending_resolved,
                "opening_resolved": opening_resolved,
            })

        if len(codes) > 1:
            total_ending = sum(r["ending"] for r in rows)
            total_opening = sum(r["opening"] for r in rows)
            rows.append({
                "key": f"{self.wp_code}-note-total",
                "label": self._account_name,
                "note_label": self._account_name,
                "is_total": True,
                "is_memo": False,
                "ending": total_ending,
                "opening": total_opening,
                "ending_resolved": True,
                "opening_resolved": True,
            })

        return rows

    def _book_value_rows(self, rule: PushRule) -> list[dict]:
        """账面价值口径：只给主表规则出一行，按行名「合计」对上附注合计行写六个字段（写后不再按上方各行重算）。

        子表规则（同一 binding 的 ``subtable_*``）不取试算表 ⇒ 不出行（原先逐码行的合计会被兜底写进子表合计行）。
        区间内一行科目都没有 ⇒ 六个字段都标未取到（附注保持原值，不写 0）。
        """
        values = self._last_book_values
        if values is None or getattr(rule, "rule_id", None) != f"{self.wp_code}.note.main":
            return []
        row: dict[str, Any] = {
            "key": f"{self.wp_code}-note-total",
            "label": "合计",
            "note_label": "合计",
            "is_total": False,
            "is_memo": False,
            "match_total": True,
        }
        for name in BOOK_VALUE_FIELDS:
            row[name] = values[name]
            row[f"{name}_resolved"] = values["found"]
        return [row]

    def entry_warnings(self, entries: Mapping[str, Any]) -> list[str]:
        return []


async def _load_book_values(db: Any, project_id: UUID, year: int, lo: str, hi: str) -> dict[str, Any]:
    """试算表 ``lo ≤ 标准码 ≤ hi``（与报表 ``SUM_TB`` 同口径的字符串区间）逐行按科目名归类后合计。

    期末取审定数、期初取年初余额；跌价准备 / 进销差价取绝对值（与 F2 审定表 ``_f2_inventory_main`` 同口径：
    备抵按名称识别，方向口径不一致的历史数据也不会把减项变成加项）。
    """
    import sqlalchemy as sa

    from app.models.audit_platform_models import TrialBalance
    from app.services.f2_extraction.category_rules import classify_f2_category, is_f2_impairment_category

    rows = (await db.execute(
        sa.select(TrialBalance.account_name, TrialBalance.audited_amount, TrialBalance.opening_balance).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
            TrialBalance.standard_account_code >= lo,
            TrialBalance.standard_account_code <= hi,
        )
    )).all()
    gross = {"end": Decimal("0"), "prior": Decimal("0")}
    impairment = {"end": Decimal("0"), "prior": Decimal("0")}
    for name, audited, opening in rows:
        category = classify_f2_category(name)
        for period, amount in (("end", audited), ("prior", opening)):
            value = Decimal(str(amount or 0))
            if is_f2_impairment_category(category):
                impairment[period] += abs(value)
            elif category == "price-difference":
                gross[period] -= abs(value)
            else:
                gross[period] += value
    out: dict[str, Any] = {"found": bool(rows)}
    for period in ("end", "prior"):
        out[f"{period}_gross"] = float(gross[period])
        out[f"{period}_impairment"] = float(impairment[period])
        out[f"{period}_net"] = float(gross[period] - impairment[period])
    return out


# ── 模板类型加载（复用 Tier A 同源） ───────────────────────────────────────


async def _load_template_type(db: Any, project_id: UUID) -> str | None:
    """附注模块渲染用的同一权威（与 E1 / Tier A 同源，ADR-PUSH-003）。"""
    from app.services.disclosure_engine import DisclosureEngine

    value = await DisclosureEngine(db)._get_active_template_type(project_id)
    return value if isinstance(value, str) and value else None


# ── 工厂函数 ────────────────────────────────────────────────────────────────


def _single_source_codes(code: str) -> tuple[str, ...] | None:
    """J / L / M 循环的科目取四表口径单一来源（单槽声明、已逐项真库对账）；None = 该循环未声明，沿用映射表。

    🔴 映射表 ``wp_account_mapping.json`` 在这三个循环有 9 个底稿的科目码是错的（2026-10-23 对照模板册名与真库试算表）：
    M3~M10 整体错位一格（M3 库存股写 4002 资本公积、M4 资本公积写 4101 盈余公积、M5 盈余公积写 4103 本年利润、
    M7 专项储备写 4201 库存股、M8 一般风险准备写 4301、M9 其他综合收益写 4401、M10 其他权益工具写不存在的 4501），
    J2 长期应付职工薪酬写不存在的 2611（实为 2705）、L7 其他非流动负债写 K5 的 2801 预计负债。推送因此把别的科目的数
    写进附注（真库和平药房_2025：盈余公积附注期末 = 本年利润 53,384,067.82）或恒为 0（J2 / M9 有数却推 0）。
    映射表另有十几个模块在读，本 spec 只改推送取数，映射表本身见 spec formula-fetch-and-wp-generation-defect-closure
    design §9（R1.4）。只取原值侧（非备抵）槽，与审定表族 binding 同口径。
    """
    from app.services.four_table.j_cycle_account_scope import j_semantic_spec_of
    from app.services.four_table.l_cycle_specs import L_CYCLE_SPECS
    from app.services.four_table.m_cycle_specs import M_CYCLE_SPECS

    spec = {"J": j_semantic_spec_of(code), "L": L_CYCLE_SPECS.get(code), "M": M_CYCLE_SPECS.get(code)}.get(code[:1])
    if spec is None:
        return None
    return tuple(dict.fromkeys(
        c for slot in spec.slots if not slot.is_provision for c in slot.fallback_standard_codes
    ))


def note_direct_for(code: str) -> NoteDirectBinding:
    """族 binding 工厂：按 ``wp_account_mapping.json`` 为指定底稿编码创建实例（J / L / M 循环科目取口径单一来源）。

    注册表写法：``"G1": "app.services.formula_push.bindings.note_direct:note_direct_for('G1')"``
    """
    mapping = _load_wp_mapping()
    if code not in mapping:
        raise KeyError(f"底稿 {code} 在 wp_account_mapping.json 中不存在")
    item = mapping[code]
    single = _single_source_codes(code)
    account_codes = single if single is not None else tuple(item.get("account_codes", []))
    reason = _NO_ACCOUNT_REASONS.get(code, "")
    if not account_codes and not reason:
        raise ValueError(f"底稿 {code} 没有科目码（口径单一来源 / wp_account_mapping.json），也没登记无科目原因")
    if account_codes and reason:
        raise ValueError(f"底稿 {code} 登记了无科目原因却取到科目 {account_codes}（_NO_ACCOUNT_REASONS 过时）")
    account_name = item.get("account_name", code)
    is_income = any(_is_pl_code(c) for c in account_codes)
    return NoteDirectBinding(
        wp_code=code,
        account_codes=account_codes,
        account_name=account_name,
        is_income=is_income,
        no_account_reason=reason,
        book_value_range=_BOOK_VALUE_RANGES.get(code),
    )
