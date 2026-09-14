#!/usr/bin/env python
"""G7 数据列 key 改动量化闸（**只读**，spec Task 8；Task 9/10/11 硬前置）。

## 为什么需要它

C 类（数据列 key 21 处）与 E 类（列数 5 处）是本 spec **唯一有数据风险**的两类 ——
`disclosure_notes.table_data.sub_table_data` 的行对象**按列 key 索引数据**
（`_cell_meta` / `_cell_modes` 亦按数据列 key 键），改 seed 侧 key 会让既有录入值失联。

标签列（B 类）不在本闸范围：投影器 `note_sub_table_projector._project_row` 有
**双向兜底**（任意标签 key ↔ 规范 `label` 互相回填）且标签列不承载数据 ⇒ 零数据风险。

## 判据

对每张待改表，统计「**已有行对象用 seed 侧 key 落过非空值**」的记录数：

- 受影响记录数 **0** → 可改 seed（`SAFE_TO_RENAME_SEED`）
- 受影响记录数 **非 0** → 改运行时并保留 seed key（`MUST_KEEP_SEED_KEY`）
- 查询失败 / 表不可判 → **fail-closed**（`FAIL_CLOSED`，拒绝改 seed）

🔴 **fail-closed 是本闸的核心** —— 宁可不改也不冒数据失联风险。

## 连库铁律（memory 已记，逐条落地）

1. **一次性专用 engine**（`create_async_engine` + `poolclass=NullPool`）并在**同一 loop 内**
   `dispose()`；禁借 `app.core.database.async_session` 共享池（借了会让同批连库测试报
   `Event loop is closed`）。
2. **只读** —— 全程无 INSERT/UPDATE/DELETE。
3. **写 SQL 前先查真实列名** —— 本脚本只用 ORM 与 `information_schema` 校验过的列。
4. 输出**自己写盘 UTF-8**（PowerShell `>` 重定向会把中文腌成乱码）。
5. 控制台输出禁 emoji（GBK 控制台 `print('✅')` 抛 `UnicodeEncodeError`）。

用法：
  python backend/scripts/diagnose/diagnose_g7_seed_key_impact.py
  python backend/scripts/diagnose/diagnose_g7_seed_key_impact.py --out <path>

spec: .kiro/specs/g7-column-alignment-and-extraction-closure/ Task 8
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import settings  # noqa: E402

OUT_DEFAULT = Path(__file__).resolve().parent / "_diagnose_g7_seed_key_impact.txt"


class Verdict(str, Enum):
    """裁决三态（态名从枚举派生，禁在统计表里另写一份字面量）。"""

    SAFE_TO_RENAME_SEED = "SAFE_TO_RENAME_SEED"
    MUST_KEEP_SEED_KEY = "MUST_KEEP_SEED_KEY"
    FAIL_CLOSED = "FAIL_CLOSED"


VERDICT_NAMES: tuple[str, ...] = tuple(v.value for v in Verdict)


# ═══════════════════════════════════════════════════════════════════════════
# 待判定清单 —— C 类 21 处 + E 类 5 处
#
# 🔴 索引键是 **(variant, note_section, table_name) 三元组**：实测模板侧 listed 63 个
# 表名跨章节重复、soe 40 个（`长期股权投资` 出现 3 次），按表名全局索引会匹配到
# 会计政策章的空壳版（建档核实轮已复现一次假结论）。
#
# `seed_keys` = 改动前 seed 侧数据列 key（本闸要查的就是它们有没有落过值）
# `runtime_keys` = 运行时数据列 key（拟定的目标形态）
# `cls` = 'C'（数据列 key 不一致）/ 'E'（列数不等，差异列恒为 `name`）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TableTarget:
    variant: str
    section: str
    table: str
    cls: str
    seed_keys: tuple[str, ...]
    runtime_keys: tuple[str, ...]
    note: str = ""

    @property
    def vanishing_keys(self) -> frozenset[str]:
        """本次改动中**真会消失**的 seed key = `seed - runtime`。

        🔴 风险模型的核心（初版闸曾用 `seed_keys` 全集，导致 3 张表假 fail-closed）：
        把 seed 侧列集从 `seed_keys` 改成 `runtime_keys` 后，某个已落值的 key `K`
        失联的**充要条件**是 `K ∈ seed_keys 且 K ∉ runtime_keys` —— 即该列名从列集里
        消失。两侧同名的 key（如 `bookNetAssets` / `level` / `reason`）改动前后都在，
        数据原地不动，**零风险**，不该计入命中。

        实测：3 张 soe 表的 `_sub_table_columns` 命中 8/6/2 处，但命中的**全是**两侧
        同名的 key，与要改名的 key 交集为空 ⇒ 按全集判会误锁死这 3 张表。
        """
        return frozenset(self.seed_keys) - frozenset(self.runtime_keys)


TARGETS: tuple[TableTarget, ...] = (
    # ── C 类：静态数据列（16 处）────────────────────────────────────────────
    TableTarget(
        "listed", "七、1", "企业集团的构成", "C",
        ("region", "registered", "nature", "direct", "indirect", "method"),
        ("principalPlace", "registeredPlace", "businessNature",
         "directHolding", "indirectHolding", "acquisitionMethod"),
    ),
    TableTarget(
        "listed", "七、1", "重要的非全资子公司", "C",
        ("minorityRatio", "minorityProfit", "minorityDividend", "minorityEquity"),
        ("holdingRatio", "currentProfit", "dividend", "closingEquity"),
    ),
    TableTarget(
        "listed", "七、1", "重要的合营企业或联营企业", "C",
        ("region", "registered", "nature", "direct", "indirect", "method"),
        ("principalPlace", "registeredPlace", "businessNature",
         "directHolding", "indirectHolding", "accountingMethod"),
    ),
    TableTarget(
        "listed", "七、1", "重要的共同经营", "C",
        ("region", "registered", "nature", "direct", "indirect"),
        ("principalPlace", "registeredPlace", "businessNature",
         "directShare", "indirectShare"),
    ),
    TableTarget(
        "soe", "七、本期发生的同一控", "本期发生的同一控制下企业合并情况", "C",
        ("consolidationDate", "bookNetAssets", "consideration", "controller",
         "revenue", "netProfit", "cashIncrease", "operatingCashFlow"),
        ("consolidationDate", "bookNetAssets", "consideration", "ultimateController",
         "revenue", "netProfit", "cashIncrease", "operatingCashFlow"),
        note="仅 controller -> ultimateController 一列不同",
    ),
    TableTarget(
        "soe", "七、本期发生的非同一", "本期发生的非同一控制下企业合并情况", "C",
        ("purchaseDate", "purchaseDateBasis", "preHoldingRatio",
         "atCombinationHoldingRatio", "bookNetAssets", "fvIdentifiableAmount",
         "fvIdentifiableMethod", "consideration", "goodwill",
         "postRevenue", "postProfit", "postCashFlow"),
        ("purchaseDate", "purchaseDateBasis", "preHolding",
         "atCombinationHolding", "bookNetAssets", "fvIdentifiable",
         "fvMethod", "consideration", "goodwill",
         "postRevenue", "postProfit", "postCashFlow"),
    ),
    TableTarget(
        "soe", "八、18", "②对合营企业或联营企业发生超额亏损的分担额", "C",
        ("priorUnrecognised", "currentUnrecognised", "closingUnrecognised"),
        ("priorCumulative", "currentUnrecognized", "closingCumulative"),
    ),
    TableTarget(
        "soe", "八、18", "结构化主体权益的账面价值和最大损失敞口", "C",
        ("sponsorScale", "endBookValue", "endMaxLoss",
         "beginBookValue", "beginMaxLoss", "presentationItem"),
        ("sponsorScale", "closingCarrying", "closingMaxLoss",
         "openingCarrying", "openingMaxLoss", "presentationItem"),
    ),
    TableTarget(
        "soe", "八、18", "结构化主体获得收益及转移资产情况", "C",
        ("serviceFee", "assetSaleGain", "incomeTotal", "transferredAssets"),
        ("serviceFee", "assetSaleGain", "total", "transferredAssets"),
        note="仅 incomeTotal -> total 一列不同",
    ),
    # ── C 类：动态列（5 处，seed 侧是写死序号）─────────────────────────────
    TableTarget(
        "listed", "七、1", "未丧失控制权的所有者权益份额变动影响", "C",
        ("company1", "company2", "company3", "company4", "company5", "company6"),
        ("ownership-change-company_1", "ownership-change-company_2",
         "ownership-change-company_3", "ownership-change-company_4",
         "ownership-change-company_5", "ownership-change-company_6"),
        note="动态列：seed 写死序号与动态列不兼容（审计师增删改名后 seed key 无法跟随）",
    ),
    TableTarget(
        "listed", "七、1", "重要联营企业主要财务信息", "C",
        ("c1Current", "c1Prior", "c2Current", "c2Prior", "c3Current", "c3Prior"),
        ("important-associate_1_current", "important-associate_1_prior",
         "important-associate_2_current", "important-associate_2_prior",
         "important-associate_3_current", "important-associate_3_prior"),
        note="动态列",
    ),
    TableTarget(
        "listed", "七、1", "续：重要联营企业本期及上期经营成果", "C",
        ("c1Current", "c1Prior", "c2Current", "c2Prior", "c3Current", "c3Prior"),
        ("important-associate_1_current", "important-associate_1_prior",
         "important-associate_2_current", "important-associate_2_prior",
         "important-associate_3_current", "important-associate_3_prior"),
        note="动态列",
    ),
    TableTarget(
        "soe", "七、重要非全资子公司", "主要财务信息", "C",
        ("c1Current", "c1Prior", "c2Current", "c2Prior", "c3Current", "c3Prior",
         "c4Current", "c4Prior", "c5Current", "c5Prior"),
        ("minority-fs-company_1_current", "minority-fs-company_1_prior",
         "minority-fs-company_2_current", "minority-fs-company_2_prior",
         "minority-fs-company_3_current", "minority-fs-company_3_prior",
         "minority-fs-company_4_current", "minority-fs-company_4_prior",
         "minority-fs-company_5_current", "minority-fs-company_5_prior"),
        note="动态列",
    ),
    TableTarget(
        "soe", "七、本期不再纳入合并", "本期出售的子公司出售日的财务状况", "C",
        ("c1SaleDate", "c1Opening", "c2SaleDate", "c2Opening"),
        ("sold-fs-position-company_1_saleDate", "sold-fs-position-company_1_opening",
         "sold-fs-position-company_2_saleDate", "sold-fs-position-company_2_opening"),
        note="动态列",
    ),
    TableTarget(
        "soe", "七、本期不再纳入合并", "本期出售的子公司出售日的经营成果", "C",
        ("aCurrent", "aPrior", "bCurrent", "bPrior", "cCurrent", "cPrior",
         "dCurrent", "dPrior", "eCurrent", "ePrior"),
        ("sold-fs-result-company_1_current", "sold-fs-result-company_1_prior",
         "sold-fs-result-company_2_current", "sold-fs-result-company_2_prior",
         "sold-fs-result-company_3_current", "sold-fs-result-company_3_prior",
         "sold-fs-result-company_4_current", "sold-fs-result-company_4_prior",
         "sold-fs-result-company_5_current", "sold-fs-result-company_5_prior"),
        note="动态列",
    ),
    TableTarget(
        "soe", "七、母公司在子公司的",
        "母公司在子公司的所有者权益份额发生变化的情况", "C",
        ("company1", "company2", "company3"),
        ("ownership-change-company_1", "ownership-change-company_2",
         "ownership-change-company_3"),
        note="动态列",
    ),
    # ── E 类：列数差 1（差异列恒为 `name`）─────────────────────────────────
    TableTarget(
        "soe", "七、本期纳入合并报表", "本期纳入合并报表范围的子公司基本情况", "E",
        ("name", "level", "enterpriseType", "registered", "region", "nature",
         "paidInCapital", "subscribedRatio", "paidRatio", "votingRights",
         "investmentAmount", "method"),
        ("level", "enterpriseType", "registeredPlace", "principalPlace",
         "businessNature", "paidInCapital", "subscribedRatio", "paidInRatio",
         "votingRights", "investmentAmount", "acquisitionMethod"),
        note="E+C 叠加：既差 name 一列，其余列 key 亦不同",
    ),
    TableTarget(
        "soe", "七、母公司拥有被投资",
        "母公司拥有被投资单位表决权不足半数但能对被投资单位形成控制的原因", "E",
        ("name", "subscribedRatio", "votingRights", "registeredCapital",
         "investmentAmount", "level", "reason"),
        ("subscribedRatio", "votingRights", "registeredCapital",
         "investmentAmount", "level", "reason"),
        note="仅差 name 一列，其余 key 逐位相同",
    ),
    TableTarget(
        "soe", "七、母公司直接或通过",
        "母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权但未能对其形成控制的原因",
        "E",
        ("name", "subscribedRatio", "votingRights", "registeredCapital",
         "investmentAmount", "level", "reason"),
        ("subscribedRatio", "votingRights", "registeredCapital",
         "investmentAmount", "level", "reason"),
        note="仅差 name 一列，其余 key 逐位相同",
    ),
    TableTarget(
        "soe", "七、重要非全资子公司", "少数股东", "E",
        ("name", "minorityRatio", "minorityProfit", "minorityDividend",
         "minorityEquity"),
        ("holdingRatio", "currentProfit", "dividend", "closingEquity"),
        note="E+C 叠加",
    ),
    TableTarget(
        "soe", "七、本期不再纳入合并", "原子公司的基本情况", "E",
        ("name", "registered", "nature", "holdingRatio", "votingRatio", "reason"),
        ("registeredPlace", "businessNature", "holdingRatio", "votingRights",
         "reason"),
        note="E+C 叠加",
    ),
)


def _self_check_targets() -> list[str]:
    """启动自检：清单本身的结构性约束（防清单腐化后判据静默空转）。"""
    errs: list[str] = []
    if not TARGETS:
        errs.append("TARGETS 为空 —— 判据会空转")
    keys = [(t.variant, t.section, t.table) for t in TARGETS]
    dup = {k for k in keys if keys.count(k) > 1}
    if dup:
        errs.append(f"三元组重复：{sorted(dup)}")
    # 🔴 计数建模（初版写错过，勿再「修回去」）：前端守卫报的 `C 数据列 key = 21` 是
    # **有 key 分叉的表数**，它 = 16 张纯 C 表 ∪ 5 张 E 表 —— 那 5 张 E 表除了差一个
    # `name` 列，其余列 key 也不同，故同时被 C 判据命中。清单里 `cls` 是**主成因**
    # 单选标签（E 表标 'E'），所以 `cls == 'C'` 的条目数应为 **16** 而非 21。
    # 已实证：guard_C == {纯C} ∪ {E}（差集两侧皆空），见 Task 8 实录。
    c_cnt = sum(1 for t in TARGETS if t.cls == "C")
    e_cnt = sum(1 for t in TARGETS if t.cls == "E")
    if c_cnt != 16:
        errs.append(f"纯 C 类（主成因=数据列 key）条目数 {c_cnt} != 16")
    if e_cnt != 5:
        errs.append(f"E 类条目数 {e_cnt} != 5（守卫实测值）")
    if len(TARGETS) != 21:
        errs.append(f"清单总表数 {len(TARGETS)} != 21")
    # 与守卫 `C=21` 对齐：清单里**每一张**表都必须有数据列 key 分叉
    #（含 5 张 E 表）—— 否则说明清单混进了无需过闸的表
    no_key_drift = [
        f"{t.variant}/{t.section}/{t.table}"
        for t in TARGETS
        if tuple(t.seed_keys) == tuple(t.runtime_keys)
    ]
    if no_key_drift:
        errs.append(f"清单内无 key 分叉的表（不该过本闸）：{no_key_drift}")
    for t in TARGETS:
        if t.variant not in ("listed", "soe"):
            errs.append(f"variant 非法：{t.variant}")
        if not t.seed_keys:
            errs.append(f"{t.table}: seed_keys 为空")
        if set(t.seed_keys) == set(t.runtime_keys):
            errs.append(f"{t.table}: seed 与运行时 key 集合相同，不该在本清单里")
        # 🔴 风险模型自检：`vanishing_keys` 非空是「本表确实有列会消失」的前提。
        #    若为空说明两侧只是**顺序**不同（那属 C 类逐位比对，不是失联风险），
        #    此时本闸对该表的裁决无意义，应从清单移出而非静默给 SAFE。
        if not t.vanishing_keys:
            errs.append(
                f"{t.table}: vanishing_keys 为空（两侧 key 集合相同、仅顺序不同）"
                f" —— 无失联风险，不该在本闸清单里"
            )
    return errs


# ═══════════════════════════════════════════════════════════════════════════
# 结果模型
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class TableImpact:
    target: TableTarget
    verdict: Verdict
    note_rows: int = 0            # 该表在库里出现的行对象总数
    populated_rows: int = 0       # 用 seed key 落过**非空**值的行数
    populated_keys: dict[str, int] = field(default_factory=dict)
    meta_hits: int = 0            # `_cell_meta` / `_cell_modes` 里出现**会消失的** key 的次数
    meta_hit_keys: set[str] = field(default_factory=set)
    projects: set[str] = field(default_factory=set)
    reason: str = ""


def _is_populated(v: object) -> bool:
    """「落过值」判据：非 None、非空串、非纯空白。0 与 False 算落过值。"""
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    return True


def _scan_rows(
    target: TableTarget,
    rows: list,
    impact: TableImpact,
) -> None:
    # 🔴 只看**会消失**的 key（见 `TableTarget.vanishing_keys`），不看 seed 全集
    vanishing = target.vanishing_keys
    for row in rows:
        if not isinstance(row, dict):
            continue
        impact.note_rows += 1
        hit = False
        for k in vanishing:
            if k in row and _is_populated(row.get(k)):
                impact.populated_keys[k] = impact.populated_keys.get(k, 0) + 1
                hit = True
        if hit:
            impact.populated_rows += 1


def _scan_meta(target: TableTarget, table_obj: dict, impact: TableImpact) -> None:
    """`_cell_meta` / `_cell_modes` 按**数据列 key** 索引 ⇒ 同样会因改 key 失联。

    同 `_scan_rows`：判据取 `vanishing_keys`（`seed - runtime`），不取 seed 全集。
    """
    vanishing = target.vanishing_keys
    for bucket_name in ("_cell_meta", "_cell_modes", "_cell_provenance"):
        bucket = table_obj.get(bucket_name)
        if isinstance(bucket, dict):
            for k in bucket:
                if k in vanishing:
                    impact.meta_hits += 1
                    impact.meta_hit_keys.add(k)
        elif isinstance(bucket, list):
            for item in bucket:
                if isinstance(item, dict):
                    for k in item:
                        if k in vanishing:
                            impact.meta_hits += 1
                            impact.meta_hit_keys.add(k)


async def _load(url: str) -> tuple[list[dict], list[str]]:
    """一次性拉取全部 G7 相关附注记录（专用引擎 + NullPool，同 loop dispose）。"""
    warnings: list[str] = []
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        echo=False,
        connect_args={"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {},
    )
    out: list[dict] = []
    try:
        async with engine.connect() as conn:
            # 铁律 3：先查真实列名（平台已因 wp_id vs workpaper_id 踩过 P0）
            cols = (
                await conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'disclosure_notes'"
                    )
                )
            ).scalars().all()
            colset = set(cols)
            for need in ("project_id", "note_section", "table_data"):
                if need not in colset:
                    warnings.append(f"disclosure_notes 缺列 {need}（实际列：{sorted(colset)}）")
            if warnings:
                return [], warnings

            sections = sorted({t.section for t in TARGETS})
            # `source_template` 有已知错配（memory 已记：项目 2aa00f57 的 `五、1` 记成 soe）
            # ⇒ **不按它过滤 variant**，改为按「章节号 + 表名」二元组匹配后再核 variant。
            has_current_std = "current_standard" in colset
            sel = [
                "project_id",
                "note_section",
                "table_data",
            ]
            if has_current_std:
                sel.append("current_standard")
            else:
                warnings.append("disclosure_notes 无 current_standard 列 ⇒ variant 只能按章节号推断")
            if "source_template" in colset:
                sel.append("source_template")
            stmt = sa.text(
                f"SELECT {', '.join(sel)} FROM disclosure_notes "
                "WHERE note_section = ANY(:secs)"
            ).bindparams(sa.bindparam("secs", value=sections, type_=sa.ARRAY(sa.Text)))
            res = await conn.execute(stmt)
            for row in res.mappings():
                out.append(dict(row))
    finally:
        # 铁律 1：同一 loop 内 dispose
        await engine.dispose()
    return out, warnings


def _variant_of(rec: dict) -> str | None:
    """由 `current_standard` 前缀定 variant（`source_template` 有已知错配不可信）。"""
    cs = rec.get("current_standard")
    if isinstance(cs, str) and cs:
        if cs.startswith("listed"):
            return "listed"
        if cs.startswith("soe"):
            return "soe"
    return None


def _analyze(records: list[dict]) -> tuple[list[TableImpact], list[str]]:
    notes: list[str] = []
    impacts: list[TableImpact] = []
    # 章节号 → 该章节下的记录
    by_section: dict[str, list[dict]] = {}
    for rec in records:
        by_section.setdefault(str(rec.get("note_section") or ""), []).append(rec)

    for t in TARGETS:
        imp = TableImpact(target=t, verdict=Verdict.FAIL_CLOSED)
        recs = by_section.get(t.section, [])
        if not recs:
            # 该章节全库无记录 ⇒ 无数据可失联 ⇒ 可改
            imp.verdict = Verdict.SAFE_TO_RENAME_SEED
            imp.reason = "该章节全库无 disclosure_notes 记录"
            impacts.append(imp)
            continue

        matched_any = False
        for rec in recs:
            v = _variant_of(rec)
            if v is not None and v != t.variant:
                continue  # 明确属另一变体
            td = rec.get("table_data")
            if isinstance(td, str):
                try:
                    td = json.loads(td)
                except Exception as exc:  # noqa: BLE001
                    imp.verdict = Verdict.FAIL_CLOSED
                    imp.reason = f"table_data 解析失败：{exc}"
                    matched_any = True
                    break
            if not isinstance(td, dict):
                continue
            sub = td.get("sub_table_data")
            if not isinstance(sub, dict):
                continue
            matched_any = True
            imp.projects.add(str(rec.get("project_id")))
            payload = sub.get(t.table)
            if isinstance(payload, list):
                _scan_rows(t, payload, imp)
            elif isinstance(payload, dict):
                # 投影结果形态 `{rows, _column_groups}`（平台已记的第二形态）
                rws = payload.get("rows")
                if isinstance(rws, list):
                    _scan_rows(t, rws, imp)
                _scan_meta(t, payload, imp)
            # 表级元数据桶
            cols_meta = td.get("_sub_table_columns")
            if isinstance(cols_meta, dict):
                cm = cols_meta.get(t.table)
                if isinstance(cm, list):
                    for c in cm:
                        # 同 `_scan_meta`：只看会消失的 key
                        if isinstance(c, dict) and c.get("key") in t.vanishing_keys:
                            imp.meta_hits += 1
                            imp.meta_hit_keys.add(str(c.get("key")))

        if not matched_any:
            imp.verdict = Verdict.SAFE_TO_RENAME_SEED
            imp.reason = "该章节记录存在但均无 sub_table_data（未推送过）"
        elif imp.verdict is Verdict.FAIL_CLOSED and imp.reason:
            pass  # 解析失败，保持 fail-closed
        elif imp.populated_rows > 0:
            imp.verdict = Verdict.MUST_KEEP_SEED_KEY
            imp.reason = (
                f"{imp.populated_rows} 个行对象已用 seed key 落过非空值"
                f"（涉及 {len(imp.projects)} 个项目）"
            )
        else:
            imp.verdict = Verdict.SAFE_TO_RENAME_SEED
            imp.reason = (
                f"扫过 {imp.note_rows} 个行对象，无一用 seed key 落过非空值"
                + (f"；但 _cell_meta 等元数据桶有 {imp.meta_hits} 处命中" if imp.meta_hits else "")
            )
            if imp.meta_hits > 0:
                # 元数据命中同样会失联 ⇒ 收紧为 fail-closed
                imp.verdict = Verdict.FAIL_CLOSED
                imp.reason = (
                    f"行对象无值，但 _cell_meta/_cell_modes/_sub_table_columns 有 "
                    f"{imp.meta_hits} 处 seed key 命中 ⇒ fail-closed"
                )
        impacts.append(imp)

    return impacts, notes


def _render(impacts: list[TableImpact], warnings: list[str], self_errs: list[str]) -> str:
    lines: list[str] = []
    lines.append("G7 数据列 key 改动量化闸（只读，spec Task 8）")
    lines.append("=" * 90)
    if self_errs:
        lines.append("[FATAL] 清单自检失败：")
        lines.extend(f"  - {e}" for e in self_errs)
        return "\n".join(lines)
    if warnings:
        lines.append("[WARN] 环境/schema 告警：")
        lines.extend(f"  - {w}" for w in warnings)
        lines.append("")

    counts = {v: 0 for v in VERDICT_NAMES}
    for imp in impacts:
        counts[imp.verdict.value] += 1

    lines.append("裁决分布：")
    for name in VERDICT_NAMES:
        lines.append(f"  {name}: {counts[name]}")
    lines.append("")

    for cls in ("C", "E"):
        lines.append("=" * 90)
        lines.append(f"{cls} 类")
        lines.append("=" * 90)
        for imp in impacts:
            if imp.target.cls != cls:
                continue
            t = imp.target
            lines.append(f"[{imp.verdict.value}] {t.variant}/{t.section}/{t.table}")
            lines.append(f"    理由 = {imp.reason}")
            lines.append(f"    行对象 {imp.note_rows} 个 / 落值行 {imp.populated_rows} 个"
                         f" / 元数据命中 {imp.meta_hits}")
            if imp.populated_keys:
                top = sorted(imp.populated_keys.items(), key=lambda kv: -kv[1])
                lines.append(f"    落值 key = {top}")
            if t.note:
                lines.append(f"    备注 = {t.note}")
        lines.append("")

    lines.append("=" * 90)
    lines.append("落地建议（Task 9/10/11 按此执行）")
    lines.append("=" * 90)
    safe = [i for i in impacts if i.verdict is Verdict.SAFE_TO_RENAME_SEED]
    keep = [i for i in impacts if i.verdict is Verdict.MUST_KEEP_SEED_KEY]
    closed = [i for i in impacts if i.verdict is Verdict.FAIL_CLOSED]
    lines.append(f"可改 seed（受影响记录 0）：{len(safe)} 张")
    lines.append(f"必须保留 seed key、改运行时：{len(keep)} 张")
    for i in keep:
        lines.append(f"    - {i.target.variant}/{i.target.section}/{i.target.table}")
    lines.append(f"fail-closed（拒绝改 seed）：{len(closed)} 张")
    for i in closed:
        lines.append(f"    - {i.target.variant}/{i.target.section}/{i.target.table}"
                     f"  <- {i.reason}")
    lines.append("")
    lines.append("🔴 禁把两侧都改成第三套 key（会同时丢两侧数据）——")
    lines.append("   落地后 key 集合必须与改动前**某一侧**相等。")
    return "\n".join(lines)


async def _amain(out: Path) -> int:
    self_errs = _self_check_targets()
    if self_errs:
        text = _render([], [], self_errs)
        out.write_text(text, encoding="utf-8")
        print(text[:2000])
        return 2

    try:
        records, warnings = await _load(settings.DATABASE_URL)
    except Exception as exc:  # noqa: BLE001
        # 铁律：查询失败一律 fail-closed
        impacts = [
            TableImpact(target=t, verdict=Verdict.FAIL_CLOSED,
                        reason=f"连库失败：{type(exc).__name__}: {exc}")
            for t in TARGETS
        ]
        text = _render(impacts, [f"连库失败：{exc}"], [])
        out.write_text(text, encoding="utf-8")
        print("[FAIL-CLOSED] connect failed; see", out)
        return 2

    impacts, notes = _analyze(records)
    text = _render(impacts, warnings + notes, [])
    out.write_text(text, encoding="utf-8")
    print(f"[OK] records={len(records)} targets={len(TARGETS)} -> {out.name}")
    for name in VERDICT_NAMES:
        n = sum(1 for i in impacts if i.verdict.value == name)
        print(f"  {name}: {n}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="G7 数据列 key 改动量化闸（只读）")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()
    return asyncio.run(_amain(Path(args.out)))


if __name__ == "__main__":
    raise SystemExit(main())
