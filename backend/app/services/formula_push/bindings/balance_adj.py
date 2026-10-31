"""资产负债类审定表族 binding（批 C）。

一个类 ``BalanceAdjudicationBinding`` 服务全部资产负债类审定表科目，
通过 ``AdjudicationSpec`` 实例化差异。

覆盖范围：K2~K7 / G1~G10 / H1~H10 / I1~I5 / J1~J2（约 35 个主编码）。

设计依据：formula-push-all-subjects-rollout · design §十三
spec: formula-push-balance-adj-batch-c · design §一 · 需求 C1~C14

注册表写法::

    "K2": "app.services.formula_push.bindings.balance_adj:binding_for('K2')"
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.services.formula_push.bindings import TargetSkip, WorkpaperTarget
from app.services.formula_push.bindings.balance_adj_calc import (
    _num,
    _round2,
    audited_net,
    audited_total,
)
from app.services.formula_push.bindings.balance_adj_extract import (
    AUDITED_SOURCES,
    conclusion_keys,
    evaluate,
)
from app.services.formula_push.policy import is_blank
from app.services.formula_push.js_compat import js_number_to_string
from app.services.formula_push.rules import PushRule, workpaper_addr_id
from app.services.formula_push.sources import (
    FormulaSources, PriorPlSnapshot, load_hall_adjustments, load_prior_pl, load_tb_audited,
)
from app.services.four_table.dual_family_codes import codes_for_cycle_slot
from app.services.four_table.g_cycle_specs import G_CYCLE_SPECS
from app.services.four_table.h6_account_scope import H6_ACCOUNT_SPEC
from app.services.four_table.i_cycle_accounts import I_CYCLE_SEGMENTS


# ── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AdjudicationSpec:
    """审定表族 binding 规格——一个实例描述一个科目的审定表推送结构。

    每个字段都须经现读确认（方法论 ②⑭），禁按命名习惯推。
    """

    wp_code: str
    #: TB 取数的科目码前缀（从 ``k_cycle_specs.fallback_standard`` 等现读取得）
    account_codes: tuple[str, ...]
    #: 审定表 sheet 编码（如 ``"K2-1"``）
    sheet_code: str
    #: 有坏账准备 / 减值维度
    has_provision: bool = True
    #: 负债侧（K3/K4/K5/K7），金额需取绝对值
    is_liability: bool = False
    #: 该科目在标准科目表里不存在（如 K4），推送只落 derived 合计
    has_account: bool = True
    #: 动态行模式：从 ``{sheet_code}-rows`` 读行清单，组合行不推
    dynamic_rows: bool = False
    #: 固定行模式的行键列表（如 ``("r0", "r1", "r2", "r3")``）
    fixed_row_keys: tuple[str, ...] = ()
    #: 固定行模式的行键前缀（如 ``""`` 表示 ``K5-1-r0-unadj``，``"nature"`` 表示 ``K3-1-nature-r0-unadj``）
    fixed_row_prefix: str = ""
    #: 双区块模式的区块定义列表（K6 资产+负债两侧）
    sections: tuple[tuple[str, tuple[str, ...]], ...] = ()
    #: 动态行的金额字段后缀列表（用于审定合计计算）
    value_suffixes: tuple[str, ...] = ("unadj", "aje", "rje")
    #: 多个科目是同一报表项目的互斥写法（双族：使用权资产 1641 / 1651、租赁负债 2601 / 2651，逐项目只用一族），
    #: 附注主表只出一行（各码合计）。不并行时每码一行会全部对上附注同一行 ⇒ 撞行、一格都不写。
    merge_note_codes: bool = False
    #: 没有标准科目时的原因（``account_codes`` 为空时必填）：不取试算表、不推附注主表，相关格子交给用户填写
    no_account_reason: str = ""
    #: 附注主表按行声明（加项科目 − 减项科目）。为空 = 每个科目一行（各码合计另出合计行）。
    #: H1 / I1 的科目里有累计折旧 / 摊销、减值准备（备抵），逐码出行再相加会把备抵当正数并进合计
    #: （spec formula-fetch-followup-defect-closure R6.3）⇒ 必须按账面价值声明。
    note_lines: tuple[NoteLine, ...] = ()


@dataclass(frozen=True)
class NoteLine:
    """附注主表的一行：``label`` = Σ加项科目 − Σ减项科目（期末取审定数、期初取年初余额）。"""

    label: str
    plus: tuple[str, ...]
    minus: tuple[str, ...] = ()
    #: 附注里该行本身是分段合计行（如「一、原价合计」）：按行名精确对上合计行，写入后不再按「合计 = 上方各行」重算
    match_total: bool = False


@dataclass
class BalanceAdjSources:
    """审定表族 binding 的取数结果（试算表审定口径 + 审定合计要从结论列读的前端合计）。"""

    formula: FormulaSources
    template_type: str | None = None
    warnings: list[str] = field(default_factory=list)
    #: ``AUDITED_SOURCES`` 里声明从结论列读的合计键 → 结论列值（引擎快照只带 remark 列）
    conclusions: dict[str, Any] = field(default_factory=dict)


# ── 工具函数 ────────────────────────────────────────────────────────────────


def _read_dynamic_row_keys(entries: Mapping[str, Any], rows_item_id: str) -> tuple[str, ...]:
    """从 entries 读取动态行清单的 rowId 列表。

    存储格式：``K2-1-rows`` 的值是 JSON 数组，每个元素有 ``rowId`` 字段。
    """
    raw = entries.get(rows_item_id)
    if raw is None or raw == "":
        return ()
    text = raw
    # entries 可能包含 {remark, updated_at} 或纯字符串
    if isinstance(raw, dict):
        text = raw.get("remark") or raw.get("value") or ""
    if not isinstance(text, str) or not text.strip():
        return ()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(
        item["rowId"]
        for item in parsed
        if isinstance(item, dict) and isinstance(item.get("rowId"), str)
    )


def _flat_rows_total(entries: Mapping[str, Any], bases: list[str]) -> float | None:
    """扁平行键审定合计 = Σ(``{base}-unadj`` + ``-aje`` + ``-rje``)；一个键都没存过 ⇒ ``None``（不是 0）。"""
    keys = [f"{base}-{suffix}" for base in bases for suffix in ("unadj", "aje", "rje")]
    if all(is_blank(entries.get(k)) for k in keys):
        return None
    return _round2(sum(
        _round2(_num(entries, f"{b}-unadj") + _num(entries, f"{b}-aje") + _num(entries, f"{b}-rje"))
        for b in bases
    ))


async def _load_conclusions(db: Any, wp_id: UUID, keys: tuple[str, ...]) -> dict[str, Any]:
    """读结论列里的前端合计（与引擎 ``_read_entries`` 同表同键，只换列）。"""
    import sqlalchemy as sa

    stmt = sa.text(
        "SELECT item_id, conclusion FROM checklist_responses WHERE wp_id = :wp_id AND item_id IN :keys"
    ).bindparams(sa.bindparam("keys", expanding=True))
    rows = (await db.execute(stmt, {"wp_id": str(wp_id), "keys": list(keys)})).all()
    return {r[0]: r[1] for r in rows}


def _dynamic_audited_total(
    entries: Mapping[str, Any],
    sheet_code: str,
    row_keys: tuple[str, ...],
) -> float:
    """动态行审定合计 = Σ(unadj + aje + rje) for all rows。"""
    total = 0.0
    for rk in row_keys:
        base = f"{sheet_code}-{rk}"
        unadj = _num(entries, f"{base}-unadj")
        aje = _num(entries, f"{base}-aje")
        rje = _num(entries, f"{base}-rje")
        total += _round2(unadj + aje + rje)
    return _round2(total)


# ── BalanceAdjudicationBinding ──────────────────────────────────────────────


class BalanceAdjudicationBinding:
    """资产负债类审定表族 binding。

    通过 ``AdjudicationSpec`` 实例化，一个类服务全部批 C 科目。
    须兼容执行 Tier A 锚点规则（``source.kind=formula``），详见 design §三。
    """

    def __init__(self, spec: AdjudicationSpec) -> None:
        if not spec.account_codes and not spec.no_account_reason:
            raise ValueError(f"{spec.wp_code}: 没有科目时必须写明 no_account_reason")
        modes = [
            name for name, on in (
                ("AUDITED_SOURCES", spec.wp_code in AUDITED_SOURCES), ("dynamic_rows", spec.dynamic_rows),
                ("fixed_row_keys", bool(spec.fixed_row_keys)), ("sections", bool(spec.sections)),
            ) if on
        ]
        if len(modes) != 1:
            raise ValueError(f"{spec.wp_code}: 审定合计须且只须声明一种来源，现为 {modes or '无'}")
        self._audited_sources = AUDITED_SOURCES.get(spec.wp_code)
        self.wp_code = spec.wp_code
        self.account_prefixes = spec.account_codes
        #: 非空 = 本科目没有标准科目（bindings 校验据此放行空 account_prefixes）
        self.no_account_reason = spec.no_account_reason if not spec.account_codes else ""
        derivations = {f"{spec.wp_code.lower()}_audited_total"}
        if spec.account_codes:  # 附注主表取自试算表；没有科目就没有附注主表推送
            derivations.add(f"{spec.wp_code.lower()}_note_main")
        self.derivations: frozenset[str] = frozenset(derivations)
        self.four_table_slots: frozenset[str] = frozenset()
        self.tb_columns: frozenset[str] = frozenset({"期末余额", "年初余额", "本期发生额"})
        self.paper_codes: tuple[str, ...] = (spec.wp_code,)
        self._spec = spec
        # 缓存 TB 数据供 note_rows 使用
        self._last_tb_data: Mapping[str, Mapping[str, Decimal]] | None = None
        #: 损益类科目的上年发生额（附注上期列）；没有损益类科目为 None
        self._last_prior_pl: PriorPlSnapshot | None = None

    async def load_sources(
        self, db: Any, project_id: UUID, year: int, wp_id: UUID | None,
    ) -> BalanceAdjSources:
        """取齐推送所需的全部源数据（试算表审定口径 + 大厅调整净额；损益类另取上年试算表作上期）。"""
        warnings: list[str] = []
        tb = await load_tb_audited(db, project_id, year, self.account_prefixes)
        if len(tb.company_codes) > 1:
            warnings.append(f"试算表含多个公司编码 {list(tb.company_codes)}，按全部合计")
        self._last_tb_data = tb.tb_data if tb.available else None
        self._last_prior_pl = await load_prior_pl(db, project_id, year, self.account_prefixes) if tb.available else None
        # 加载大厅已批准调整净额（与 E1 同口径，ADR-PUSH-001）
        hall = await load_hall_adjustments(db, project_id, year, self.account_prefixes)
        template_type = await _load_template_type(db, project_id)
        conclusions: dict[str, Any] = {}
        keys = conclusion_keys(self._audited_sources) if self._audited_sources is not None else ()
        if keys and wp_id is not None:
            conclusions = await _load_conclusions(db, wp_id, keys)
        return BalanceAdjSources(
            formula=FormulaSources(tb=tb, hall_adj=hall),
            template_type=template_type,
            warnings=warnings,
            conclusions=conclusions,
        )

    def workpaper_targets(
        self,
        rule: PushRule,
        entries: Mapping[str, Any],
        sources: BalanceAdjSources,
        *,
        paper_code: str | None = None,
    ) -> tuple[list[WorkpaperTarget], list[TargetSkip]]:
        target = rule.target
        if target.domain != "workpaper":
            raise ValueError(f"{rule.rule_id} 不是底稿目标")
        kind = rule.source.kind
        if kind == "formula":
            return self._formula_target(rule, entries, sources)
        if kind == "derivation":
            return self._derivation_target(rule, entries, sources)
        raise ValueError(f"{rule.rule_id}: 审定表族不支持 source.kind={kind!r}")

    def _formula_target(
        self, rule: PushRule, entries: Mapping[str, Any], sources: BalanceAdjSources,
    ) -> tuple[list[WorkpaperTarget], list[TargetSkip]]:
        """formula 分支：与 Tier A 锚点逻辑等价（兼容执行）。"""
        target = rule.target
        addr = workpaper_addr_id(self.wp_code, target.sheet_code, target.item_id)
        reason = sources.formula.unavailable_reason(rule.source.context_map)
        if reason:
            return [], [TargetSkip(rule.rule_id, addr, reason)]

        from app.services.formula_engine import execute

        result = execute(rule.source.expression, sources.formula.context_for(rule.source.context_map))
        if result.errors or result.blocked:
            return [], [TargetSkip(
                rule.rule_id, addr, "公式求值失败：" + "；".join(result.errors),
            )]
        value: Any = float(result.value)
        return [WorkpaperTarget(
            rule_id=rule.rule_id, policy=rule.policy, addr_id=addr,
            item_id=target.item_id, formula_value=value,
            current_value=entries.get(target.item_id),
        )], []

    def _derivation_target(
        self, rule: PushRule, entries: Mapping[str, Any], sources: BalanceAdjSources,
    ) -> tuple[list[WorkpaperTarget], list[TargetSkip]]:
        """derivation 分支：审定合计 derived 键。读不到 ⇒ 公式值为空（derived 空值 = 目标写空）。"""
        target = rule.target
        addr = workpaper_addr_id(self.wp_code, target.sheet_code, target.item_id)
        name = rule.source.name
        params = rule.source.params_map
        expected_name = f"{self.wp_code.lower()}_audited_total"
        if name != expected_name:
            raise ValueError(f"{rule.rule_id}: 审定表族不支持派生 {name!r}")
        kind = params.get("kind")
        value = self._compute_audited(kind, entries, sources.conclusions)
        return [WorkpaperTarget(
            rule_id=rule.rule_id, policy=rule.policy, addr_id=addr,
            item_id=target.item_id, formula_value=value,
            current_value=entries.get(target.item_id),
        )], []

    def _compute_audited(
        self, kind: str | None, entries: Mapping[str, Any], conclusions: Mapping[str, Any] | None = None,
    ) -> float | None:
        """按 kind (receivable/net/asset/liab) 计算审定合计；前端没有存任何来源 ⇒ ``None``（不写假的 0）。"""
        spec = self._spec
        if self._audited_sources is not None:
            return evaluate(self._audited_sources, kind, entries, conclusions or {})
        # 双区块模式（K6）
        if spec.sections:
            return self._compute_section_audited(kind, entries)
        # 动态行模式（K2）
        if spec.dynamic_rows:
            return self._compute_dynamic_audited(kind, entries)
        # 固定行模式（K3/K4/K5）
        if spec.fixed_row_keys:
            return self._compute_fixed_audited(kind, entries)
        raise ValueError(f"{spec.wp_code}: 无法确定行模式（需声明 dynamic_rows / fixed_row_keys / sections）")

    def _compute_fixed_audited(
        self, kind: str | None, entries: Mapping[str, Any],
    ) -> float | None:
        """固定行审定合计：按 ``fixed_row_keys`` 遍历；一个行键都没存过 ⇒ ``None``。

        键模式：
        - 无前缀：``{sheet_code}-{rowKey}-unadj``（K4/K5）
        - 有前缀：``{sheet_code}-{prefix}-{rowKey}-unadj``（K3 的 nature 组）
        """
        spec = self._spec
        prefix = spec.fixed_row_prefix
        if kind not in ("receivable", "net"):
            raise ValueError(f"{spec.wp_code}: 审定合计 kind={kind!r} 不合法")
        bases = [f"{spec.sheet_code}-{prefix}-{rk}" if prefix else f"{spec.sheet_code}-{rk}"
                 for rk in spec.fixed_row_keys]
        # K3/K4/K5 全部 has_provision=False ⇒ net = receivable
        return _flat_rows_total(entries, bases)

    def _compute_section_audited(
        self, kind: str | None, entries: Mapping[str, Any],
    ) -> float | None:
        """双区块审定合计（K6）：按 kind 选区块；该区块一个行键都没存过 ⇒ ``None``。"""
        spec = self._spec
        for section_key, row_keys in spec.sections:
            if kind == section_key:
                return _flat_rows_total(entries, [f"{spec.sheet_code}-{section_key}-{rk}" for rk in row_keys])
        raise ValueError(f"{spec.wp_code}: 审定合计 kind={kind!r} 无匹配区块")

    def _compute_dynamic_audited(
        self, kind: str | None, entries: Mapping[str, Any],
    ) -> float | None:
        """动态行审定合计：从 ``{sheet_code}-rows`` 读行清单，汇总；没有行清单 ⇒ ``None``。"""
        spec = self._spec
        rows_item_id = f"{spec.sheet_code}-rows"
        row_keys = _read_dynamic_row_keys(entries, rows_item_id)
        if not row_keys:
            if kind not in ("receivable", "net"):
                raise ValueError(f"{spec.wp_code}: 审定合计 kind={kind!r} 不合法")
            return None
        total = _dynamic_audited_total(entries, spec.sheet_code, row_keys)
        if kind == "receivable":
            return total
        if kind == "net":
            # has_provision=False → net = receivable
            if not spec.has_provision:
                return total
            # has_provision=True 时需要 baddebt 侧（暂不实现）
            raise ValueError(f"{spec.wp_code}: 动态行备抵侧尚未实现")
        raise ValueError(f"{spec.wp_code}: 审定合计 kind={kind!r} 不合法")

    def apply(self, entries: dict[str, Any], target: WorkpaperTarget, value: Any) -> bool:
        """单值键写入；返回存储值是否改变。"""
        old = entries.get(target.item_id)
        new = "" if value is None else js_number_to_string(float(value))
        entries[target.item_id] = new
        return old != new

    def note_rows(
        self, entries: Mapping[str, Any], template_type: str, rule: PushRule,
    ) -> list[dict]:
        """从试算表取审定数构建附注行。

        复用 NoteDirectBinding / Tier A 的同口径逻辑。
        """
        tb_data = self._last_tb_data
        if tb_data is None:
            return []

        spec = self._spec
        codes = spec.account_codes
        from app.services.formula_push.bindings.note_direct import code_note_rows

        account_name = _load_account_name(spec.wp_code)
        if spec.note_lines:
            return _line_note_rows(spec.wp_code, spec.note_lines, tb_data)
        if spec.merge_note_codes and len(codes) > 1:
            return _merged_note_rows(spec.wp_code, account_name, codes, tb_data)
        return code_note_rows(spec.wp_code, account_name, codes, tb_data, self._last_prior_pl)

    def entry_warnings(self, entries: Mapping[str, Any]) -> list[str]:
        return []


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _merged_note_rows(
    wp_code: str, account_name: str, codes: tuple[str, ...],
    tb_data: Mapping[str, Mapping[str, Decimal]],
) -> list[dict]:
    """互斥双族科目并成一行（各码合计），另附同值合计行供附注找不到同名行时兜底写合计。"""
    from app.services.formula_push.bindings.note_direct import _tb_value

    ending = opening = 0.0
    ending_resolved = opening_resolved = False
    for code in codes:
        e, e_ok = _tb_value(tb_data, code, "期末余额")
        o, o_ok = _tb_value(tb_data, code, "年初余额")
        ending, opening = ending + e, opening + o
        ending_resolved, opening_resolved = ending_resolved or e_ok, opening_resolved or o_ok
    row = {
        "key": f"{wp_code}-note-{'+'.join(codes)}",
        "label": account_name,
        "note_label": account_name,
        "is_total": False,
        "is_memo": False,
        "ending": _round2(ending),
        "opening": _round2(opening),
        "ending_resolved": ending_resolved,
        "opening_resolved": opening_resolved,
    }
    return [row, {**row, "key": f"{wp_code}-note-total", "is_total": True}]


def _line_note_rows(
    wp_code: str, lines: tuple[NoteLine, ...], tb_data: Mapping[str, Mapping[str, Decimal]],
) -> list[dict]:
    """按 ``note_lines`` 出附注行：Σ加项 − Σ减项。加项科目全都不存在 ⇒ 未取到（附注保持原值）；减项缺失按 0。

    只有一行且不是分段合计行时另附同值合计行，供附注找不到同名行时兜底写合计（与 ``_merged_note_rows`` 同）。
    """
    from app.services.formula_push.bindings.note_direct import _tb_value

    def signed(line: NoteLine, column: str) -> tuple[float, bool]:
        plus = [_tb_value(tb_data, code, column) for code in line.plus]
        minus = [_tb_value(tb_data, code, column) for code in line.minus]
        value = sum(v for v, _ in plus) - sum(v for v, _ in minus)
        return _round2(value), any(ok for _, ok in plus)

    rows: list[dict] = []
    for line in lines:
        ending, ending_resolved = signed(line, "期末余额")
        opening, opening_resolved = signed(line, "年初余额")
        rows.append({
            "key": f"{wp_code}-note-{line.label}",
            "label": line.label,
            "note_label": line.label,
            "is_total": False,
            "is_memo": False,
            "match_total": line.match_total,
            "ending": ending,
            "opening": opening,
            "ending_resolved": ending_resolved,
            "opening_resolved": opening_resolved,
        })
    if len(lines) == 1 and not lines[0].match_total:
        rows.append({**rows[0], "key": f"{wp_code}-note-total", "is_total": True})
    return rows


def _h6_codes() -> tuple[str, ...]:
    """H6 固定资产清理：语义科目规格的兜底标准码（``h6_account_scope``，1606）。"""
    return tuple(c for slot in H6_ACCOUNT_SPEC.slots for c in slot.fallback_standard_codes)


def _g_codes(wp_code: str) -> tuple[str, ...]:
    """G 循环：语义科目规格里原值侧（非备抵）槽的兜底标准码（``g_cycle_specs.G_CYCLE_SPECS``）。"""
    return tuple(dict.fromkeys(
        c for slot in G_CYCLE_SPECS[wp_code].slots if not slot.is_provision for c in slot.fallback_standard_codes
    ))


def _i_codes(wp_code: str) -> tuple[str, ...]:
    """I 循环：段声明的兜底标准码（``i_cycle_accounts.I_CYCLE_SEGMENTS``，按声明顺序）；空 = 无标准科目。"""
    return tuple(dict.fromkeys(c for seg in I_CYCLE_SEGMENTS[wp_code] for c in seg.fallback))


def _i1_note_lines() -> tuple[NoteLine, ...]:
    """I1 附注「无形资产情况」表（国企模板）的四段合计行；科目按 I1 三段的单一来源顺序（原价 / 累计摊销 / 减值准备）。

    上市模板该表是「列 = 无形资产类别、行 = 期初 / 增减 / 期末」的矩阵，没有期末 / 期初列 ⇒ 对不上，不写。
    """
    cost, amort, impair = (tuple(seg.fallback) for seg in I_CYCLE_SEGMENTS["I1"])
    return (
        NoteLine("一、原价合计", cost, match_total=True),
        NoteLine("二、累计摊销合计", amort, match_total=True),
        NoteLine("三、无形资产减值准备合计", impair, match_total=True),
        NoteLine("四、账面价值合计", cost, amort + impair, match_total=True),
    )


def _load_account_name(wp_code: str) -> str:
    """从 ``wp_account_mapping.json`` 读科目名。"""
    from app.services.formula_push.bindings.note_direct import _load_wp_mapping

    mapping = _load_wp_mapping()
    item = mapping.get(wp_code)
    return item.get("account_name", wp_code) if item else wp_code


async def _load_template_type(db: Any, project_id: UUID) -> str | None:
    """附注模块渲染用的同一权威（与 E1 / Tier A / NoteDirectBinding 同源）。"""
    from app.services.disclosure_engine import DisclosureEngine

    value = await DisclosureEngine(db)._get_active_template_type(project_id)
    return value if isinstance(value, str) and value else None


# ── 规格声明（逐科目现读确认后添加） ────────────────────────────────────────


_SPECS: dict[str, AdjudicationSpec] = {
    # ── K2 其他流动资产（canary）──────────────────────────────────────────────
    # account_codes: k_cycle_specs.K2.fallback_standard = "1901"
    # 🔴 wp_account_mapping.json 写 "1701" 是旧值，以 k_cycle_specs 为准
    # sheet_code: "K2-1"（审定表K2-1）
    # has_provision: False（无坏账准备 / 减值维度）
    # dynamic_rows: True（动态行，行清单存在 K2-1-rows）
    "K2": AdjudicationSpec(
        wp_code="K2",
        account_codes=("1901",),
        sheet_code="K2-1",
        has_provision=False,
        is_liability=False,
        has_account=True,
        dynamic_rows=True,
    ),
    # ── K3 其他应付款（负债类）───────────────────────────────────────────────
    # account_codes: k_cycle_specs.K3.fallback_standard = "2241"
    # sheet_code: "K3-1"
    # 固定行 nature r0~r3（保证金及押金 / 往来款 / 代收代付 / 其他）
    # 键模式: K3-1-nature-r{i}-unadj
    # is_liability: True（贷方负债类）
    "K3": AdjudicationSpec(
        wp_code="K3",
        account_codes=("2241",),
        sheet_code="K3-1",
        has_provision=False,
        is_liability=True,
        has_account=True,
        fixed_row_keys=("r0", "r1", "r2", "r3"),
        fixed_row_prefix="nature",
    ),
    # ── K4 其他流动负债（负债类，无实体科目）──────────────────────────────────
    # 🔴 k_cycle_specs.K4.fallback_standard = ""：其他流动负债是报表项目，由多个明细归集，没有标准科目。
    #    原先规则取 TB('2261')（NoteDirectBinding 时代遗留），2261 在各项目科目表与试算表里都不存在 ⇒
    #    试算平衡表数恒推 0、附注主表恒推 0（spec formula-fetch-followup-defect-closure R6.2）。改为无科目声明，
    #    只推审定表固定行的审定合计；试算平衡表数与附注主表交给用户填写。
    # sheet_code: "K4-1"
    # 固定行 r0~r4（短期应付债券 / 政府补助 / 待转销项税额 / 应付退货款 / 其他）
    # 键模式: K4-1-r{i}-unadj
    "K4": AdjudicationSpec(
        wp_code="K4",
        account_codes=(),
        sheet_code="K4-1",
        has_provision=False,
        is_liability=True,
        has_account=False,
        fixed_row_keys=("r0", "r1", "r2", "r3", "r4"),
        no_account_reason="其他流动负债没有标准科目（k_cycle_specs 不给兜底码；原规则取的 2261 在各项目科目表与试算表里都不存在），"
                          "试算平衡表数与附注主表交给用户填写",
    ),
    # ── K5 预计负债（负债类）─────────────────────────────────────────────────
    # account_codes: k_cycle_specs.K5.fallback_standard = "2801"
    # sheet_code: "K5-1"
    # 固定行 r0~r5（产品质量保证 / 未决诉讼 / 亏损合同 / 重组义务 / 弃置义务 / 其他）
    # 键模式: K5-1-r{i}-unadj
    "K5": AdjudicationSpec(
        wp_code="K5",
        account_codes=("2801",),
        sheet_code="K5-1",
        has_provision=False,
        is_liability=True,
        has_account=True,
        fixed_row_keys=("r0", "r1", "r2", "r3", "r4", "r5"),
    ),
    # ── K6 持有待售资产和负债（双区块：资产侧+负债侧）─────────────────────────
    # account_codes: 1481（资产侧）+ 2245（负债侧）
    # sheet_code: "K6-1"
    # 双区块：asset r0~r6 / liab r0~r4
    # 键模式: K6-1-asset-r{i}-unadj / K6-1-liab-r{i}-unadj
    "K6": AdjudicationSpec(
        wp_code="K6",
        account_codes=("1481", "2245"),
        sheet_code="K6-1",
        has_provision=False,
        is_liability=False,
        has_account=True,
        sections=(
            ("asset", ("r0", "r1", "r2", "r3", "r4", "r5", "r6")),
            ("liab", ("r0", "r1", "r2", "r3", "r4")),
        ),
    ),
    # ── K7 递延收益（负债类，动态行）────────────────────────────────────────
    # account_codes: k_cycle_specs.K7.fallback_standard = "2401"
    # sheet_code: "K7-1"
    # 动态行（K7-1-rows 存 JSON）
    # 键模式: K7-1-{rowId}-unadj
    "K7": AdjudicationSpec(
        wp_code="K7",
        account_codes=("2401",),
        sheet_code="K7-1",
        has_provision=False,
        is_liability=True,
        has_account=True,
    ),
    # ── G 循环（投资，G1~G10 不含 G7） ──────────────────────────────────────
    "G1": AdjudicationSpec(wp_code="G1", account_codes=('1101',), sheet_code="G1-1", has_provision=False),  # 交易性金融资产
    "G2": AdjudicationSpec(wp_code="G2", account_codes=('1132',), sheet_code="G2-1", has_provision=False),  # 应收利息
    "G3": AdjudicationSpec(wp_code="G3", account_codes=('1131',), sheet_code="G3-1", has_provision=False),  # 应收股利
    "G4": AdjudicationSpec(wp_code="G4", account_codes=('1504',), sheet_code="G4-1", has_provision=False),  # 债权投资
    "G5": AdjudicationSpec(wp_code="G5", account_codes=('1531',), sheet_code="G5-1", has_provision=False),  # 长期应收款
    # 🔴 G6 / G8 原先都手写 `1503`（旧准则「可供出售金融资产」）：新准则下要按业务模式与合同现金流量特征人工拆分，
    #    不能自动归到任一科目（g_cycle_specs「旧准则拆分不可自动化」），两张底稿还会同推一个数。改取口径单一来源
    #    （spec formula-fetch-and-wp-generation-defect-closure R1.4）。
    "G6": AdjudicationSpec(wp_code="G6", account_codes=_g_codes("G6"), sheet_code="G6-1", has_provision=False),  # 其他债权投资（1506）
    "G8": AdjudicationSpec(wp_code="G8", account_codes=_g_codes("G8"), sheet_code="G8-1", has_provision=False),  # 其他权益工具投资（1507）
    "G9": AdjudicationSpec(wp_code="G9", account_codes=('1519',), sheet_code="G9-1", has_provision=False),  # 其他非流动金融资产
    "G10": AdjudicationSpec(wp_code="G10", account_codes=('2101',), sheet_code="G10-1", has_provision=False, is_liability=True),  # 交易性金融负债
    # ── H 循环（固定资产，H1~H10） ──────────────────────────────────────────
    # 🔴 H1 / I1 的科目含累计折旧 / 摊销、减值准备（备抵）：附注主表按账面价值出行（两种准则模板的行名现读确认：
    #    固定资产表「固定资产」行；国企无形资产情况表四段合计行），原先逐码出行、合计行把备抵当正数相加
    #    （和平 2025 固定资产合计被推成 1601 + 1602，spec formula-fetch-followup-defect-closure R6.3）。
    "H1": AdjudicationSpec(
        wp_code="H1", account_codes=('1601', '1602', '1603'), sheet_code="H1-1", has_provision=False,
        note_lines=(NoteLine("固定资产", ("1601",), ("1602", "1603")),),
    ),  # 固定资产
    "H2": AdjudicationSpec(wp_code="H2", account_codes=('1604',), sheet_code="H2-1", has_provision=False),  # 在建工程
    "H3": AdjudicationSpec(wp_code="H3", account_codes=('1521',), sheet_code="H3-1", has_provision=False),  # 投资性房地产
    "H4": AdjudicationSpec(wp_code="H4", account_codes=('1605',), sheet_code="H4-1", has_provision=False),  # 工程物资
    "H5": AdjudicationSpec(wp_code="H5", account_codes=('1631',), sheet_code="H5-1", has_provision=False),  # 油气资产
    # 🔴 H6 / H8 / H9 / I1~I5 的科目取自口径单一来源（不在这里再写一份字面量）。原先手写的是映射码 / 错码：
    #    H6 `1606B`、I1 `1703B`（试算表标准码里没有字母后缀）、H8 `1901`（待处理财产损溢）、H9 `2802`（不存在）、
    #    I5 `1901` ⇒ 推送恒为 0 或推别的科目（spec formula-fetch-and-wp-generation-defect-closure R1）。
    "H6": AdjudicationSpec(wp_code="H6", account_codes=_h6_codes(), sheet_code="H6-1", has_provision=False),  # 固定资产清理
    "H7": AdjudicationSpec(wp_code="H7", account_codes=('1621',), sheet_code="H7-1", has_provision=False),  # 生产性生物资产
    "H8": AdjudicationSpec(wp_code="H8", account_codes=codes_for_cycle_slot("H8", "gross"), sheet_code="H8-1", has_provision=False, merge_note_codes=True),  # 使用权资产（原值，双族）
    "H9": AdjudicationSpec(wp_code="H9", account_codes=codes_for_cycle_slot("H9", "gross"), sheet_code="H9-1", has_provision=False, is_liability=True, merge_note_codes=True),  # 租赁负债（双族；未确认融资费用另列，不并取）
    "H10": AdjudicationSpec(wp_code="H10", account_codes=('6115',), sheet_code="H10-1", has_provision=False),  # 资产处置损益
    # ── I 循环（无形资产，I1~I5） ────────────────────────────────────────────
    "I1": AdjudicationSpec(
        wp_code="I1", account_codes=_i_codes("I1"), sheet_code="I1-1", has_provision=False,
        note_lines=_i1_note_lines(),
    ),  # 无形资产（原价 / 累计摊销 / 减值准备）
    "I2": AdjudicationSpec(wp_code="I2", account_codes=_i_codes("I2"), sheet_code="I2-1", has_provision=False),  # 开发支出
    "I3": AdjudicationSpec(wp_code="I3", account_codes=_i_codes("I3"), sheet_code="I3-1", has_provision=False),  # 商誉
    "I4": AdjudicationSpec(wp_code="I4", account_codes=_i_codes("I4"), sheet_code="I4-1", has_provision=False),  # 长期待摊费用
    "I5": AdjudicationSpec(
        wp_code="I5", account_codes=_i_codes("I5"), sheet_code="I5-1", has_provision=False, has_account=False,
        no_account_reason="其他非流动资产没有标准科目（报表行 BS-037 引用的 1911 在标准科目表与各项目试算表里都不存在），"
                          "试算平衡表数与附注主表交给用户填写",
    ),  # 其他非流动资产
}


def binding_for(wp_code: str) -> BalanceAdjudicationBinding:
    """族 binding 工厂：按规格声明为指定底稿编码创建 ``BalanceAdjudicationBinding`` 实例。"""
    if wp_code not in _SPECS:
        raise KeyError(f"底稿 {wp_code} 不在审定表族规格中")
    return BalanceAdjudicationBinding(_SPECS[wp_code])
