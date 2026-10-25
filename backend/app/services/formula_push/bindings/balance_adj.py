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
from app.services.formula_push.js_compat import js_number_to_string
from app.services.formula_push.rules import PushRule, workpaper_addr_id
from app.services.formula_push.sources import FormulaSources, load_hall_adjustments, load_tb_audited


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


@dataclass
class BalanceAdjSources:
    """审定表族 binding 的取数结果（只有试算表审定口径）。"""

    formula: FormulaSources
    template_type: str | None = None
    warnings: list[str] = field(default_factory=list)


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
        self.wp_code = spec.wp_code
        self.account_prefixes = spec.account_codes
        self.derivations: frozenset[str] = frozenset({
            f"{spec.wp_code.lower()}_audited_total",
            f"{spec.wp_code.lower()}_note_main",
        })
        self.four_table_slots: frozenset[str] = frozenset()
        self.tb_columns: frozenset[str] = frozenset({"期末余额", "年初余额", "本期发生额"})
        self.paper_codes: tuple[str, ...] = (spec.wp_code,)
        self._spec = spec
        # 缓存 TB 数据供 note_rows 使用
        self._last_tb_data: Mapping[str, Mapping[str, Decimal]] | None = None

    async def load_sources(
        self, db: Any, project_id: UUID, year: int, wp_id: UUID | None,
    ) -> BalanceAdjSources:
        """取齐推送所需的全部源数据（试算表审定口径 + 大厅调整净额）。"""
        warnings: list[str] = []
        tb = await load_tb_audited(db, project_id, year, self.account_prefixes)
        if len(tb.company_codes) > 1:
            warnings.append(f"试算表含多个公司编码 {list(tb.company_codes)}，按全部合计")
        self._last_tb_data = tb.tb_data if tb.available else None
        # 加载大厅已批准调整净额（与 E1 同口径，ADR-PUSH-001）
        hall = await load_hall_adjustments(db, project_id, year, self.account_prefixes)
        template_type = await _load_template_type(db, project_id)
        return BalanceAdjSources(
            formula=FormulaSources(tb=tb, hall_adj=hall),
            template_type=template_type,
            warnings=warnings,
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
            return self._derivation_target(rule, entries)
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
        self, rule: PushRule, entries: Mapping[str, Any],
    ) -> tuple[list[WorkpaperTarget], list[TargetSkip]]:
        """derivation 分支：审定合计 derived 键。"""
        target = rule.target
        addr = workpaper_addr_id(self.wp_code, target.sheet_code, target.item_id)
        name = rule.source.name
        params = rule.source.params_map
        expected_name = f"{self.wp_code.lower()}_audited_total"
        if name != expected_name:
            raise ValueError(f"{rule.rule_id}: 审定表族不支持派生 {name!r}")
        kind = params.get("kind")
        value = self._compute_audited(kind, entries)
        return [WorkpaperTarget(
            rule_id=rule.rule_id, policy=rule.policy, addr_id=addr,
            item_id=target.item_id, formula_value=value,
            current_value=entries.get(target.item_id),
        )], []

    def _compute_audited(self, kind: str | None, entries: Mapping[str, Any]) -> float:
        """按 kind (receivable/net/asset/liability) 计算审定合计。"""
        spec = self._spec
        # 双区块模式（K6）
        if spec.sections:
            return self._compute_section_audited(kind, entries)
        # 动态行模式（K2/K7）
        if spec.dynamic_rows:
            return self._compute_dynamic_audited(kind, entries)
        # 固定行模式（K3/K4/K5）
        if spec.fixed_row_keys:
            return self._compute_fixed_audited(kind, entries)
        raise ValueError(f"{spec.wp_code}: 无法确定行模式（需声明 dynamic_rows / fixed_row_keys / sections）")

    def _compute_fixed_audited(
        self, kind: str | None, entries: Mapping[str, Any],
    ) -> float:
        """固定行审定合计：按 ``fixed_row_keys`` 遍历。

        键模式：
        - 无前缀：``{sheet_code}-{rowKey}-unadj``（K4/K5）
        - 有前缀：``{sheet_code}-{prefix}-{rowKey}-unadj``（K3 的 nature 组）
        """
        spec = self._spec
        prefix = spec.fixed_row_prefix
        total = 0.0
        for rk in spec.fixed_row_keys:
            if prefix:
                base = f"{spec.sheet_code}-{prefix}-{rk}"
            else:
                base = f"{spec.sheet_code}-{rk}"
            unadj = _num(entries, f"{base}-unadj")
            aje = _num(entries, f"{base}-aje")
            rje = _num(entries, f"{base}-rje")
            total += _round2(unadj + aje + rje)
        total = _round2(total)
        if kind == "receivable":
            return total
        if kind == "net":
            return total  # K3/K4/K5/K7 全部 has_provision=False
        raise ValueError(f"{spec.wp_code}: 审定合计 kind={kind!r} 不合法")

    def _compute_section_audited(
        self, kind: str | None, entries: Mapping[str, Any],
    ) -> float:
        """双区块审定合计（K6）：按 kind 选区块。"""
        spec = self._spec
        for section_key, row_keys in spec.sections:
            if kind == section_key:
                total = 0.0
                for rk in row_keys:
                    base = f"{spec.sheet_code}-{section_key}-{rk}"
                    unadj = _num(entries, f"{base}-unadj")
                    aje = _num(entries, f"{base}-aje")
                    rje = _num(entries, f"{base}-rje")
                    total += _round2(unadj + aje + rje)
                return _round2(total)
        raise ValueError(f"{spec.wp_code}: 审定合计 kind={kind!r} 无匹配区块")

    def _compute_dynamic_audited(
        self, kind: str | None, entries: Mapping[str, Any],
    ) -> float:
        """动态行审定合计：从 ``{sheet_code}-rows`` 读行清单，汇总。"""
        spec = self._spec
        rows_item_id = f"{spec.sheet_code}-rows"
        row_keys = _read_dynamic_row_keys(entries, rows_item_id)
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
        from app.services.formula_push.bindings.note_direct import _is_pl_code, _tb_value

        rows: list[dict] = []
        account_name = _load_account_name(spec.wp_code)
        for code in codes:
            is_pl = _is_pl_code(code)
            ending_col = "本期发生额" if is_pl else "期末余额"
            opening_col = "年初余额"
            ending, ending_resolved = _tb_value(tb_data, code, ending_col)
            opening, opening_resolved = _tb_value(tb_data, code, opening_col)
            label = account_name if len(codes) == 1 else f"{account_name}_{code}"
            rows.append({
                "key": f"{spec.wp_code}-note-{code}",
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
                "key": f"{spec.wp_code}-note-total",
                "label": account_name,
                "note_label": account_name,
                "is_total": True,
                "is_memo": False,
                "ending": total_ending,
                "opening": total_opening,
                "ending_resolved": True,
                "opening_resolved": True,
            })

        return rows

    def entry_warnings(self, entries: Mapping[str, Any]) -> list[str]:
        return []


# ── 辅助 ────────────────────────────────────────────────────────────────────


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
    # account_codes: K4 formula 规则用 TB('2261')，虽然 has_account=False
    # 🔴 k_cycle_specs.K4.fallback_standard = ""（标准科目表无此科目），但 formula
    # 规则从 NoteDirectBinding 时代引用 2261，取数需要此码
    # sheet_code: "K4-1"
    # 固定行 r0~r4（短期应付债券 / 政府补助 / 待转销项税额 / 应付退货款 / 其他）
    # 键模式: K4-1-r{i}-unadj
    "K4": AdjudicationSpec(
        wp_code="K4",
        account_codes=("2261",),
        sheet_code="K4-1",
        has_provision=False,
        is_liability=True,
        has_account=False,
        fixed_row_keys=("r0", "r1", "r2", "r3", "r4"),
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
        dynamic_rows=True,
    ),
    # ── G 循环（投资，G1~G10 不含 G7） ──────────────────────────────────────
    "G1": AdjudicationSpec(wp_code="G1", account_codes=('1101',), sheet_code="G1-1", has_provision=False, dynamic_rows=True),  # 交易性金融资产
    "G2": AdjudicationSpec(wp_code="G2", account_codes=('1132',), sheet_code="G2-1", has_provision=False, dynamic_rows=True),  # 应收利息
    "G3": AdjudicationSpec(wp_code="G3", account_codes=('1131',), sheet_code="G3-1", has_provision=False, dynamic_rows=True),  # 应收股利
    "G4": AdjudicationSpec(wp_code="G4", account_codes=('1504',), sheet_code="G4-1", has_provision=False, dynamic_rows=True),  # 债权投资
    "G5": AdjudicationSpec(wp_code="G5", account_codes=('1531',), sheet_code="G5-1", has_provision=False, dynamic_rows=True),  # 长期应收款
    "G6": AdjudicationSpec(wp_code="G6", account_codes=('1503',), sheet_code="G6-1", has_provision=False, dynamic_rows=True),  # 其他债权投资
    "G8": AdjudicationSpec(wp_code="G8", account_codes=('1503',), sheet_code="G8-1", has_provision=False, dynamic_rows=True),  # 其他权益工具投资
    "G9": AdjudicationSpec(wp_code="G9", account_codes=('1519',), sheet_code="G9-1", has_provision=False, dynamic_rows=True),  # 其他非流动金融资产
    "G10": AdjudicationSpec(wp_code="G10", account_codes=('2101',), sheet_code="G10-1", has_provision=False, is_liability=True, dynamic_rows=True),  # 交易性金融负债
    # ── H 循环（固定资产，H1~H10） ──────────────────────────────────────────
    "H1": AdjudicationSpec(wp_code="H1", account_codes=('1601', '1602', '1603'), sheet_code="H1-1", has_provision=False, dynamic_rows=True),  # 固定资产
    "H2": AdjudicationSpec(wp_code="H2", account_codes=('1604',), sheet_code="H2-1", has_provision=False, dynamic_rows=True),  # 在建工程
    "H3": AdjudicationSpec(wp_code="H3", account_codes=('1521',), sheet_code="H3-1", has_provision=False, dynamic_rows=True),  # 投资性房地产
    "H4": AdjudicationSpec(wp_code="H4", account_codes=('1605',), sheet_code="H4-1", has_provision=False, dynamic_rows=True),  # 工程物资
    "H5": AdjudicationSpec(wp_code="H5", account_codes=('1631',), sheet_code="H5-1", has_provision=False, dynamic_rows=True),  # 油气资产
    "H6": AdjudicationSpec(wp_code="H6", account_codes=('1606B',), sheet_code="H6-1", has_provision=False, dynamic_rows=True),  # 固定资产清理
    "H7": AdjudicationSpec(wp_code="H7", account_codes=('1621',), sheet_code="H7-1", has_provision=False, dynamic_rows=True),  # 生产性生物资产
    "H8": AdjudicationSpec(wp_code="H8", account_codes=('1901',), sheet_code="H8-1", has_provision=False, dynamic_rows=True),  # 使用权资产
    "H9": AdjudicationSpec(wp_code="H9", account_codes=('2802',), sheet_code="H9-1", has_provision=False, is_liability=True, dynamic_rows=True),  # 租赁负债
    "H10": AdjudicationSpec(wp_code="H10", account_codes=('6115',), sheet_code="H10-1", has_provision=False, dynamic_rows=True),  # 资产处置损益
    # ── I 循环（无形资产，I1~I5） ────────────────────────────────────────────
    "I1": AdjudicationSpec(wp_code="I1", account_codes=('1701', '1702', '1703B'), sheet_code="I1-1", has_provision=False, dynamic_rows=True),  # 无形资产
    "I2": AdjudicationSpec(wp_code="I2", account_codes=('1704',), sheet_code="I2-1", has_provision=False, dynamic_rows=True),  # 开发支出
    "I3": AdjudicationSpec(wp_code="I3", account_codes=('1711',), sheet_code="I3-1", has_provision=False, dynamic_rows=True),  # 商誉
    "I4": AdjudicationSpec(wp_code="I4", account_codes=('1801',), sheet_code="I4-1", has_provision=False, dynamic_rows=True),  # 长期待摊费用
    "I5": AdjudicationSpec(wp_code="I5", account_codes=('1901',), sheet_code="I5-1", has_provision=False, dynamic_rows=True),  # 其他非流动资产
}


def binding_for(wp_code: str) -> BalanceAdjudicationBinding:
    """族 binding 工厂：按规格声明为指定底稿编码创建 ``BalanceAdjudicationBinding`` 实例。"""
    if wp_code not in _SPECS:
        raise KeyError(f"底稿 {wp_code} 不在审定表族规格中")
    return BalanceAdjudicationBinding(_SPECS[wp_code])
