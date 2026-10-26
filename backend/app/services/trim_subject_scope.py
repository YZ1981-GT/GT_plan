# -*- coding: utf-8 -*-
"""程序裁剪「科目有无数据」判定 —— 以本项目科目映射之后的标准科目为准。

spec: .kiro/specs/procedure-trim-generation-delegation-chain/ 需求 1

## 为什么重写

旧判定（``procedure_trim_scope``）用两份静态表把底稿编码写死到科目码
（``account_package_registry.json`` + ``procedure_trim_account_map.json``），再与试算表
期末非零的码比对。实测三类错：

1. **码表写错**：H3 投资性房地产写成 1503/1504（可供出售金融资产 / 债权投资），
   重药安徽 1521 审定 7,689,744.44 被判「无数据」自动裁掉；同类还有 H8 / I2 / I6 / M3 /
   M7 / M9 / M10 / G4 / G6 / G8 等 16 处。
2. **码在不同项目含义不同**：项目标准科目表有两种写法 —— 一类沿用客户 2006 版码
   （实收资本 4001、使用权资产 1651、其他综合收益 4003），一类映射进平台标准表
   （3001、1641、3102）。只写一套码，另一类项目就失效。
3. **只看期末**：当年还清的借款（期初 7700 万、期末 0）被判无数据。

## 现在怎么判

- **科目口径**：底稿主码的科目名称与兜底码取四表单一来源（``four_table`` 各循环语义
  规格，经 :mod:`app.services.four_table.declared_codes` 的入口取），没有规格的底稿取
  ``wp_account_mapping.json`` 的主条目（``is_primary``）。
- **逐项目定位**：与四表取数同一顺序 —— 客户科目表按名称 → 平台标准科目表按名称 →
  兜底码（须在本项目科目表里确实存在）；科目表整体不可用时才用裸兜底码。不走报表
  公式层（多槽规格下会把整行科目塞给某个子项）。名称匹配取**全部候选名的并集**
  （见 :func:`match_slot_all_names`），不是四表定位的「第一个命中的名字」。
- **有数据**：标准层任一命中码（前缀）期末审定（无则未审）/ 期初非零，或按映射归集
  的本期借贷发生非零；客户层任一命中客户码（点号边界）期初 / 期末 / 借 / 贷非零
  （覆盖映射缺口，证据里注明 ``client_unmapped``）。阈值 0.005 元。
- **无法判定**（无规格无登记、名称与码都定位不到且科目表不可用）返回 ``unknown``，
  调用方不得当作无数据。

全程只读；任一可选查询失败只降级不中断（各自 SAVEPOINT，避免 PG 事务 aborted 连带）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.four_table.leaf_aggregation import (
    LeafRow,
    filter_by_prefixes,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.semantic_account_resolver import (
    SOURCE_CLIENT,
    SOURCE_STANDARD,
    ChartRow,
    SemanticAccountSlot,
    is_top_level_code,
    normalize_account_name,
    to_chart_rows,
)

logger = logging.getLogger(__name__)

#: 按科目余额驱动裁剪的循环（A/B/C/S 不按单科目余额裁剪）
DATA_DRIVEN_CYCLES = frozenset("DEFGHIJKLMN")
#: 金额阈值（元）：绝对值小于它视为 0
AMOUNT_EPSILON = 0.005

STATE_WITH_DATA = "with_data"
STATE_NO_DATA = "no_data"
STATE_UNKNOWN = "unknown"

SCOPE_SOURCE_FOUR_TABLE = "four_table"
SCOPE_SOURCE_WP_MAPPING = "wp_account_mapping"

LOCATED_CLIENT_CHART = "client_chart"
LOCATED_STANDARD_CHART = "standard_chart"
LOCATED_FALLBACK = "fallback"
LOCATED_FALLBACK_NO_CHART = "fallback_no_chart"

_WP_MAPPING_PATH = Path(__file__).resolve().parents[2] / "data" / "wp_account_mapping.json"

#: 候选底稿编号：各循环字母 × 序号（覆盖四表规格的全部键，不另写一份规格表）
_CANDIDATE_NUMBERS = range(0, 21)


@dataclass(frozen=True)
class SubjectScope:
    """一个底稿主码的科目口径（语义槽集合）。"""

    wp_code: str
    slots: tuple[SemanticAccountSlot, ...]
    source: str
    label: str = ""


def _k_scope(wp_code: str) -> SubjectScope | None:
    """K 循环规格 → 语义槽（主体按名称 + 兜底码；备抵 / 附加只按兜底码）。"""
    from app.services.four_table.declared_codes import _k_spec  # 单一来源入口

    k = _k_spec(wp_code)
    if k is None or not getattr(k, "has_account", True):
        return None
    slots: list[SemanticAccountSlot] = [
        SemanticAccountSlot(
            key="gross",
            names=(k.account_name,) if k.account_name else (),
            fallback_standard_codes=(k.fallback_standard,) if k.fallback_standard else (),
        )
    ]
    if k.fallback_provision:
        slots.append(
            SemanticAccountSlot(
                key="provision",
                names=(),
                fallback_standard_codes=tuple(k.fallback_provision),
                is_provision=True,
            )
        )
    if k.extra_standard_codes:
        slots.append(
            SemanticAccountSlot(
                key="extra", names=(), fallback_standard_codes=tuple(k.extra_standard_codes)
            )
        )
    return SubjectScope(wp_code, tuple(slots), SCOPE_SOURCE_FOUR_TABLE, k.account_name or "")


def _semantic_scope(wp_code: str) -> SubjectScope | None:
    from app.services.four_table.declared_codes import _semantic_spec  # 单一来源入口

    try:
        spec = _semantic_spec(wp_code)
    except Exception as e:  # noqa: BLE001 — 个别规格不可用不影响其余底稿
        logger.warning("裁剪科目口径：%s 的四表规格读取失败: %s", wp_code, e)
        return None
    if spec is None or not getattr(spec, "slots", None):
        return None
    label = spec.slots[0].display_label if spec.slots else ""
    return SubjectScope(wp_code, tuple(spec.slots), SCOPE_SOURCE_FOUR_TABLE, label)


def _wp_mapping_primary_entries() -> dict[str, dict]:
    """``wp_account_mapping.json`` 中 D~N 循环的主条目（``is_primary``）。"""
    try:
        raw = json.loads(_WP_MAPPING_PATH.read_text(encoding="utf-8-sig"))
    except Exception as e:  # noqa: BLE001
        logger.warning("裁剪科目口径：wp_account_mapping.json 读取失败: %s", e)
        return {}
    entries = raw.get("mappings", []) if isinstance(raw, dict) else raw
    out: dict[str, dict] = {}
    for item in entries or []:
        if not isinstance(item, dict) or not item.get("is_primary"):
            continue
        code = str(item.get("wp_code") or "").strip().upper()
        if not code or code[:1] not in DATA_DRIVEN_CYCLES:
            continue
        out.setdefault(code, item)
    return out


@lru_cache(maxsize=1)
def subject_scopes() -> dict[str, SubjectScope]:
    """全部可判定底稿主码的科目口径。四表规格优先，映射表主条目只补规格缺失的底稿。"""
    out: dict[str, SubjectScope] = {}
    for letter in sorted(DATA_DRIVEN_CYCLES):
        for n in _CANDIDATE_NUMBERS:
            code = f"{letter}{n}"
            scope = _k_scope(code) if letter == "K" else None
            if scope is None:
                scope = _semantic_scope(code)
            if scope is not None:
                out[code] = scope
    for code, item in _wp_mapping_primary_entries().items():
        if code in out:
            continue
        name = str(item.get("account_name") or "").strip()
        codes = tuple(
            str(c).strip() for c in (item.get("account_codes") or []) if str(c or "").strip()
        )
        if not name and not codes:
            continue
        out[code] = SubjectScope(
            code,
            (SemanticAccountSlot(key="gross", names=(name,) if name else (), fallback_standard_codes=codes),),
            SCOPE_SOURCE_WP_MAPPING,
            name,
        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 定位与取数（纯函数）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class LocatedSlot:
    key: str
    located_by: str
    matched: list[tuple[str, str]]
    standard_codes: list[str]
    client_codes: list[str]

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "located_by": self.located_by,
            "matched": [list(m) for m in self.matched],
            "standard_codes": list(self.standard_codes),
            "client_codes": list(self.client_codes),
        }


def _minimal_prefixes(codes) -> list[str]:
    uniq = sorted({(c or "").strip() for c in codes} - {""})
    return [c for c in uniq if not any(c != o and c.startswith(o + ".") for o in uniq)]


def client_to_standard(client_codes: list[str], mapping: dict[str, str]) -> list[str]:
    """客户码前缀 → 本项目映射到的标准码（含点号子级的映射行）。"""
    out = {
        std
        for orig, std in mapping.items()
        if any(orig == c or orig.startswith(c + ".") for c in client_codes)
    }
    return sorted(out - {""})


def standard_to_client(standard_codes: list[str], mapping: dict[str, str]) -> list[str]:
    """标准码 → 本项目映射到它（或其子级）的客户码。"""
    out = {
        orig
        for orig, std in mapping.items()
        if any(std == s or std.startswith(s) for s in standard_codes)
    }
    return _minimal_prefixes(out)


def match_slot_all_names(slot: SemanticAccountSlot, rows: list[ChartRow]) -> list[ChartRow]:
    """按槽的**全部**候选名逐个匹配并取并集（一级科目；否决词先过滤；每个名字精确优先、无精确再包含）。

    🔴 与 ``semantic_account_resolver.match_slot_in_chart`` 的差别是刻意的：后者为「定位这个槽
    对应的那一个科目」只取**第一个**有命中的名字。判「有无数据」要看全部候选科目 —— 存货槽
    候选名是「存货 / 材料采购 / 原材料 / 库存商品」，重药安徽「材料采购」为 0 而「库存商品」
    1.59 亿，只取第一个命中的名字会把存货判成无数据。
    """
    cands = [r for r in rows or [] if is_top_level_code(r.account_code) and r.account_name]
    excludes = [normalize_account_name(x) for x in (slot.exclude_names or ()) if x]
    if excludes:
        cands = [
            r for r in cands
            if not any(ex and ex in normalize_account_name(r.account_name) for ex in excludes)
        ]
    hits: dict[str, ChartRow] = {}
    for name in slot.names or ():
        wanted = normalize_account_name(name)
        if not wanted:
            continue
        exact = [r for r in cands if normalize_account_name(r.account_name) == wanted]
        for r in exact or [r for r in cands if wanted in normalize_account_name(r.account_name)]:
            hits.setdefault(r.account_code, r)
    return [hits[c] for c in sorted(hits)]


def locate_slot(
    slot: SemanticAccountSlot,
    *,
    client_rows: list[ChartRow],
    standard_rows: list[ChartRow],
    mapping: dict[str, str],
) -> LocatedSlot | None:
    """定位一个槽（客户科目表按名 → 平台标准科目表按名 → 兜底码）；定位不到返回 ``None``。纯函数。"""
    rows = match_slot_all_names(slot, client_rows)
    if rows:
        client = _minimal_prefixes(r.account_code for r in rows)
        return LocatedSlot(
            slot.key, LOCATED_CLIENT_CHART,
            [(r.account_code, r.account_name) for r in rows],
            client_to_standard(client, mapping), client,
        )
    rows = match_slot_all_names(slot, standard_rows)
    if rows:
        std = _minimal_prefixes(r.account_code for r in rows)
        return LocatedSlot(
            slot.key, LOCATED_STANDARD_CHART,
            [(r.account_code, r.account_name) for r in rows],
            std, standard_to_client(std, mapping),
        )
    fallback = [c for c in (slot.fallback_standard_codes or ()) if c]
    if not fallback:
        return None
    chart_codes = {r.account_code for r in (*client_rows, *standard_rows)}
    if chart_codes:
        hit = [c for c in fallback if c in chart_codes]
        if not hit:
            return None
        return LocatedSlot(slot.key, LOCATED_FALLBACK, [], hit, standard_to_client(hit, mapping))
    return LocatedSlot(
        slot.key, LOCATED_FALLBACK_NO_CHART, [], fallback, standard_to_client(fallback, mapping)
    )


def _abs(v: Any) -> float:
    try:
        return abs(float(v or 0))
    except (TypeError, ValueError):
        return 0.0


def _starts_with_any(code: str, prefixes: list[str]) -> bool:
    return any(code == p or code.startswith(p) for p in prefixes)


@dataclass
class TbRow:
    code: str
    name: str
    closing: float
    opening: float


@dataclass
class SubjectEvidence:
    wp_code: str
    state: str
    reason: str
    scope_source: str
    label: str = ""
    slots: list[LocatedSlot] = field(default_factory=list)
    closing: float = 0.0
    opening: float = 0.0
    debit: float = 0.0
    credit: float = 0.0
    client_unmapped: bool = False

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "reason": self.reason,
            "scope_source": self.scope_source,
            "label": self.label,
            "slots": [s.as_dict() for s in self.slots],
            "closing": round(self.closing, 2),
            "opening": round(self.opening, 2),
            "debit": round(self.debit, 2),
            "credit": round(self.credit, 2),
            "client_unmapped": self.client_unmapped,
        }


def evaluate_scope(
    scope: SubjectScope,
    *,
    client_rows: list[ChartRow],
    standard_rows: list[ChartRow],
    mapping: dict[str, str],
    tb_rows: list[TbRow],
    occurrence: dict[str, tuple[float, float]],
    leaves: list[LeafRow],
) -> SubjectEvidence:
    """判定一个底稿主码有无数据。纯函数（全部输入由调用方一次取齐）。"""
    located = [
        loc
        for slot in scope.slots
        if (loc := locate_slot(
            slot, client_rows=client_rows, standard_rows=standard_rows, mapping=mapping
        )) is not None
    ]
    ev = SubjectEvidence(
        wp_code=scope.wp_code, state=STATE_UNKNOWN, reason="", scope_source=scope.source,
        label=scope.label, slots=located,
    )
    if not located:
        if client_rows or standard_rows:
            ev.state = STATE_NO_DATA
            ev.reason = f"本项目科目表中没有{scope.label or '该科目'}"
        else:
            ev.reason = "本项目没有可用的科目表，且该底稿没有兜底科目码，无法判定"
        return ev

    std_codes = sorted({c for loc in located for c in loc.standard_codes})
    client_codes = _minimal_prefixes(c for loc in located for c in loc.client_codes)
    for r in tb_rows:
        if std_codes and _starts_with_any(r.code, std_codes):
            ev.closing += _abs(r.closing)
            ev.opening += _abs(r.opening)
    for code, (dr, cr) in occurrence.items():
        if std_codes and _starts_with_any(code, std_codes):
            ev.debit += _abs(dr)
            ev.credit += _abs(cr)
    standard_has = any(
        v >= AMOUNT_EPSILON for v in (ev.closing, ev.opening, ev.debit, ev.credit)
    )
    client_has = False
    if client_codes:
        for leaf in filter_by_prefixes(leaves, client_codes):
            if any(_abs(v) >= AMOUNT_EPSILON for v in (leaf.closing, leaf.opening, leaf.debit, leaf.credit)):
                client_has = True
                if not standard_has:
                    ev.closing += _abs(leaf.closing)
                    ev.opening += _abs(leaf.opening)
                    ev.debit += _abs(leaf.debit)
                    ev.credit += _abs(leaf.credit)
    if standard_has:
        ev.state = STATE_WITH_DATA
        ev.reason = "映射后的标准科目有余额或本期发生额"
    elif client_has:
        ev.state = STATE_WITH_DATA
        ev.client_unmapped = True
        ev.reason = "客户科目有余额或发生额，但未进入试算表（科目映射可能缺失）"
    else:
        ev.state = STATE_NO_DATA
        ev.reason = "相关科目期初、期末余额与本期发生额均为 0"
    return ev


# ─────────────────────────────────────────────────────────────────────────────
# 取数（只读；可选数据源失败只降级）
# ─────────────────────────────────────────────────────────────────────────────


class TrialBalanceUnavailable(RuntimeError):
    """试算表查询失败：调用方应按「无法裁剪」处理（不得当作试算表为空以外的结论）。"""


async def _optional_fetch(db: AsyncSession, label: str, sql: str, params: dict) -> list:
    try:
        async with db.begin_nested():
            return list((await db.execute(sa.text(sql), params)).fetchall())
    except Exception as e:  # noqa: BLE001
        logger.warning("裁剪科目判定：%s 读取失败，降级处理: %s", label, e)
        return []


async def fetch_tb_rows(db: AsyncSession, project_id: UUID, year: int) -> list[TbRow]:
    from app.models.audit_platform_models import TrialBalance
    from app.services.dataset_query import get_active_filter

    tb = TrialBalance.__table__
    try:
        async with db.begin_nested():
            active = await get_active_filter(db, tb, project_id, year)
            rows = (
                await db.execute(
                    sa.select(
                        tb.c.standard_account_code,
                        tb.c.account_name,
                        tb.c.unadjusted_amount,
                        tb.c.audited_amount,
                        tb.c.opening_balance,
                    ).where(active)
                )
            ).fetchall()
    except Exception as e:  # noqa: BLE001
        raise TrialBalanceUnavailable(str(e)) from e
    out: list[TbRow] = []
    for r in rows:
        code = (r.standard_account_code or "").strip()
        if not code:
            continue
        closing = r.audited_amount if r.audited_amount is not None else r.unadjusted_amount
        out.append(TbRow(code, (r.account_name or "").strip(), float(closing or 0), float(r.opening_balance or 0)))
    return out


async def fetch_leaves(db: AsyncSession, project_id: UUID, year: int) -> list[LeafRow]:
    from app.models.audit_platform_models import TbBalance
    from app.services.dataset_query import get_active_filter

    try:
        async with db.begin_nested():
            active = await get_active_filter(db, TbBalance.__table__, project_id, year)
            rows = (
                await db.execute(
                    sa.select(
                        TbBalance.account_code,
                        TbBalance.account_name,
                        TbBalance.opening_balance,
                        TbBalance.closing_balance,
                        TbBalance.debit_amount,
                        TbBalance.credit_amount,
                        TbBalance.closing_direction,
                        TbBalance.opening_direction,
                        TbBalance.dataset_id,
                    ).where(active)
                )
            ).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning("裁剪科目判定：余额表读取失败，跳过发生额与客户科目判定: %s", e)
        return []
    return select_leaves(to_leaf_rows(rows))


def occurrence_by_standard(leaves: list[LeafRow], mapping: dict[str, str]) -> dict[str, tuple[float, float]]:
    """叶子发生额按映射归集到标准码（与公式引擎同口径：最长前缀继承祖先映射）。"""
    from app.services.four_table.occurrence_by_standard_code import (
        CREDIT_KEY,
        DEBIT_KEY,
        aggregate_occurrence,
    )

    agg = aggregate_occurrence(leaves, mapping)
    return {std: (float(v[DEBIT_KEY]), float(v[CREDIT_KEY])) for std, v in agg.items()}


@dataclass
class SubjectAvailability:
    tb_empty: bool
    cycles_with_data: list[str]
    evidence: dict[str, SubjectEvidence]

    def codes_in(self, state: str) -> list[str]:
        return sorted(c for c, ev in self.evidence.items() if ev.state == state)


async def evaluate_subjects(db: AsyncSession, project_id: UUID, year: int) -> SubjectAvailability:
    """对全部可判定底稿主码给出有无数据结论。试算表读取失败抛 :class:`TrialBalanceUnavailable`。"""
    from app.services.b50_risk_reader import cycle_for_account

    tb_rows = await fetch_tb_rows(db, project_id, year)
    chart = to_chart_rows(
        await _optional_fetch(
            db, "科目表",
            "SELECT account_code, account_name, direction, source FROM account_chart "
            "WHERE project_id = :pid AND is_deleted = false",
            {"pid": str(project_id)},
        )
    )
    mapping: dict[str, str] = {}
    for r in await _optional_fetch(
        db, "科目映射",
        "SELECT original_account_code, standard_account_code FROM account_mapping "
        "WHERE project_id = :pid AND is_deleted = false",
        {"pid": str(project_id)},
    ):
        orig = (r.original_account_code or "").strip()
        std = (r.standard_account_code or "").strip()
        if orig and std:
            mapping[orig] = std
    leaves = await fetch_leaves(db, project_id, year)
    occurrence = occurrence_by_standard(leaves, mapping) if leaves else {}

    client_rows = [r for r in chart if r.source == SOURCE_CLIENT]
    standard_rows = [r for r in chart if r.source == SOURCE_STANDARD]

    cycles: set[str] = set()
    any_nonzero = False
    for r in tb_rows:
        if _abs(r.closing) >= AMOUNT_EPSILON or _abs(r.opening) >= AMOUNT_EPSILON:
            any_nonzero = True
            cyc = cycle_for_account(r.name, r.code)
            if cyc in DATA_DRIVEN_CYCLES:
                cycles.add(cyc)

    evidence = {
        code: evaluate_scope(
            scope,
            client_rows=client_rows,
            standard_rows=standard_rows,
            mapping=mapping,
            tb_rows=tb_rows,
            occurrence=occurrence,
            leaves=leaves,
        )
        for code, scope in subject_scopes().items()
    }
    return SubjectAvailability(
        tb_empty=not any_nonzero and not cycles,
        cycles_with_data=sorted(cycles),
        evidence=evidence,
    )


__all__ = [
    "AMOUNT_EPSILON",
    "STATE_NO_DATA",
    "STATE_UNKNOWN",
    "STATE_WITH_DATA",
    "SubjectAvailability",
    "SubjectEvidence",
    "SubjectScope",
    "TbRow",
    "TrialBalanceUnavailable",
    "client_to_standard",
    "evaluate_scope",
    "evaluate_subjects",
    "locate_slot",
    "standard_to_client",
    "subject_scopes",
]
