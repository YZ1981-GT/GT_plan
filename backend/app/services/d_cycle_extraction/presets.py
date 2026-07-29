"""D-cycle Tier A 提取公式预设库 + 读时收敛（预设 ∪ 用户 wp_formula）.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/
      (Requirements 3.3, 5.4, 5.5 / Property 5, 8)

- `load_presets(wp_code)`：读 `d_cycle_extraction_presets.json`（mtime 缓存），
  返回该 wp_code 的 Tier A 默认公式绑定列表；文件缺失/解析失败 → `[]`。
- `resolve_effective(db, wp_id, wp_code, project_id)`：**读时收敛** =
  预设 ∪ 用户 `wp_formula`。每锚点唯一，优先级 **禁用 > 用户 custom > 预设**
  （Property 5 / R5.4 R5.5）；预设未落库不丢失（同锚点无用户覆盖时仍出现，source=preset）。
  每个绑定的 anchor 经 `anchor_registry.is_known_anchor(wp_code, anchor)` 校验，
  未知锚点丢弃 + 告警（Property 8 复用 / R6.2 —— 防提取种子写到不存在字段）。

**禁用标记**（R5.5）：用户 `wp_formula` 满足以下任一即视为「禁用」（该锚点不再自动填充，
区别于「恢复默认」的删除）：
  * `category == '__disabled__'`，或
  * `expression` 为空/纯空白。

Binding（内存 dict，不新建表）：
  { wp_code, sheet_name, anchor, expression, formula_type, description, source, tier }
  source ∈ {preset, custom, disabled}；tier == "A"。
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpFormula
from app.services.d_cycle_extraction.anchor_registry import is_known_anchor

logger = logging.getLogger(__name__)

# __file__ = backend/app/services/d_cycle_extraction/presets.py
# parents[3] = backend
_PRESETS_PATH: Path = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "d_cycle_extraction"
    / "d_cycle_extraction_presets.json"
)

_DISABLED_CATEGORY = "__disabled__"

# source 枚举
SOURCE_PRESET = "preset"
SOURCE_CUSTOM = "custom"
SOURCE_DISABLED = "disabled"

# ─── Tier A 取数语义标注（P1-4：审定/未审口径消歧）────────────────────────────
#
# 🔴 关键口径澄清：Tier A 可编辑公式 `TB('code','列')` 经 `wp_formula_eval_service`
# 读 **trial_balance**（审定汇总，`_COLUMN_MAP`：期末余额/审定数→audited_amount），
# 是「TB↔审定核对标量」；而 Tier B（D6）seed 读 **tb_balance**（原始余额，
# opening/closing = 未审）。二者虽同经 get_active_filter，但**不同物理表、不同列、
# 不同语义（审定 vs 未审）**。面板须标注，避免审计师把核对标量当未审 seed。
_TB_COLUMN_RE = re.compile(r"""["']([^"']+)["']\s*\)""")

# 列名 → 语义（对齐 wp_formula_eval_service._COLUMN_MAP）
_COLUMN_SEMANTIC = {
    "期末余额": "审定数",
    "审定数": "审定数",
    "年初余额": "期初余额",
    "期初余额": "期初余额",
    "未审数": "未审数",
    "RJE调整": "重分类调整",
    "AJE调整": "账项调整",
}


def tier_a_semantic(expression: str | None) -> str:
    """从 Tier A 公式表达式派生取数语义标注（P1-4）.

    Tier A 走 `trial_balance`（审定/核对口径），与 Tier B `tb_balance`（未审 seed）
    口径不同。返回带数据源标注的短语义标签，供公式管理面板展示消歧。
    表达式为空/无法解析列名 → 返回通用标注（仍标 trial_balance 审定口径）。
    """
    if not expression:
        return ""
    m = _TB_COLUMN_RE.search(expression)
    col = (m.group(1).strip() if m else "")
    sem = _COLUMN_SEMANTIC.get(col, "")
    if sem:
        return f"试算表{sem}（trial_balance 核对标量，≠ tb_balance 未审 seed）"
    return "试算表取数（trial_balance 核对标量，≠ tb_balance 未审 seed）"

# ─── mtime 缓存 ────────────────────────────────────────────────────────────────

_lock = threading.Lock()
_cached_mtime: float | None = None
# wp_code -> list[preset binding dict]
_cache: dict[str, list[dict]] = {}


def _normalize_preset_entry(wp_code: str, entry: Any) -> dict | None:
    """把 JSON 预设条目规范化为 Binding dict（缺 anchor/expression 视为无效跳过）。"""
    if not isinstance(entry, dict):
        return None
    anchor = str(entry.get("anchor") or "").strip()
    expression = str(entry.get("expression") or "").strip()
    if not anchor or not expression:
        return None
    return {
        "wp_code": wp_code,
        "sheet_name": str(entry.get("sheet_name") or "").strip(),
        "anchor": anchor,
        "expression": expression,
        "formula_type": str(entry.get("formula_type") or "auto_calc").strip(),
        "description": str(entry.get("description") or "").strip(),
        "source": SOURCE_PRESET,
        "tier": "A",
    }


def _load_all() -> dict[str, list[dict]]:
    """按 mtime 缓存加载预设库。缺失/解析失败 → 空 dict（该 wp 无 Tier A）。"""
    global _cached_mtime, _cache
    with _lock:
        try:
            mtime = _PRESETS_PATH.stat().st_mtime
        except OSError:
            _cached_mtime = None
            _cache = {}
            return _cache

        if _cached_mtime == mtime:
            # 命中缓存（注意：空 dict 也是有效缓存，靠 mtime 相等判定）
            return _cache

        try:
            raw = json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("d_cycle_extraction_presets 解析失败: %s", exc)
            _cached_mtime = mtime
            _cache = {}
            return _cache

        parsed: dict[str, list[dict]] = {}
        if isinstance(raw, dict):
            for wp_code, entries in raw.items():
                if wp_code.startswith("_"):  # 跳过 _meta 等元数据键
                    continue
                if not isinstance(entries, list):
                    continue
                bindings: list[dict] = []
                for entry in entries:
                    norm = _normalize_preset_entry(wp_code, entry)
                    if norm is not None:
                        bindings.append(norm)
                parsed[wp_code] = bindings

        _cached_mtime = mtime
        _cache = parsed
        return _cache


# ─── 公开 API ──────────────────────────────────────────────────────────────────


def load_presets(wp_code: str) -> list[dict]:
    """返回某 wp_code 的 Tier A 预设公式绑定列表（预设不落库）.

    文件缺失/解析失败/该 wp_code 无预设 → `[]`。
    """
    if not wp_code:
        return []
    presets = _load_all().get(wp_code, [])
    # 返回副本，防调用方污染缓存
    return [dict(b) for b in presets]


def _is_disabled(formula: WpFormula) -> bool:
    """判定用户 wp_formula 是否为「禁用」标记（R5.5）。"""
    category = (formula.category or "").strip()
    expression = (formula.expression or "").strip()
    return category == _DISABLED_CATEGORY or not expression


def _formula_to_binding(wp_code: str, formula: WpFormula) -> dict:
    """把用户 WpFormula 转 Binding dict（custom 或 disabled）。"""
    disabled = _is_disabled(formula)
    return {
        "wp_code": wp_code,
        "sheet_name": (formula.sheet_name or "").strip(),
        "anchor": (formula.target_cell or "").strip(),
        "expression": (formula.expression or "").strip(),
        "formula_type": (formula.formula_type or "auto_calc").strip(),
        "description": (formula.description or "").strip(),
        "source": SOURCE_DISABLED if disabled else SOURCE_CUSTOM,
        "tier": "A",
    }


async def resolve_effective(
    db: AsyncSession,
    wp_id: UUID | str,
    wp_code: str,
    project_id: UUID | str,
) -> list[dict]:
    """读时收敛：预设 ∪ 用户 wp_formula，每锚点唯一（禁用 > 用户 custom > 预设）.

    Property 5：预设未落库不丢失（同锚点无用户覆盖时仍以 source=preset 出现）；
                用户覆盖同锚点时以 custom/disabled 取代预设。
    Property 8：每个绑定 anchor 必 ∈ `is_known_anchor(wp_code, anchor)`，
                未知锚点丢弃 + 告警（不静默写空）。

    Returns:
        `list[Binding dict]`，按 (sheet_name, anchor) 排序。
    """
    # 1. 预设（校验锚点合法性）
    effective: dict[str, dict] = {}
    for b in load_presets(wp_code):
        anchor = b["anchor"]
        if not is_known_anchor(wp_code, anchor):
            logger.warning(
                "d_cycle 预设锚点未知，丢弃: wp_code=%s anchor=%s", wp_code, anchor
            )
            continue
        effective[anchor] = b

    # 2. 用户 wp_formula 覆盖（同锚点用户 custom/disabled 取代预设）
    try:
        result = await db.execute(
            sa.select(WpFormula).where(WpFormula.wp_id == _as_uuid(wp_id))
        )
        user_formulas = list(result.scalars().all())
    except Exception as e:  # noqa: BLE001
        logger.warning("resolve_effective 读取用户 wp_formula 失败: %s", e)
        user_formulas = []

    for formula in user_formulas:
        anchor = (formula.target_cell or "").strip()
        if not anchor:
            continue
        if not is_known_anchor(wp_code, anchor):
            logger.warning(
                "d_cycle 用户公式锚点未知，丢弃: wp_code=%s anchor=%s", wp_code, anchor
            )
            continue
        # 用户绑定覆盖同锚点预设（禁用 > custom > 预设）
        effective[anchor] = _formula_to_binding(wp_code, formula)

    return sorted(
        effective.values(),
        key=lambda b: (b.get("sheet_name", ""), b.get("anchor", "")),
    )


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


# ─── Tier B 只读溯源描述（描述四表库 prefill 填什么，非可编辑公式）──────────────
#
# 只登记**确实由 Tier B 四表库预填/归集**填充的锚点（对齐各 render 策略实际接入 +
# `README.md` 差异矩阵），未接入 Tier B 的循环留空（诚实，不臆造 / R7.4）。
# 当前 D6 接入 render `adjudication_prefill`（`_d6_contract_assets.py`）；D2 因 D2-1 审定表
# 按信用风险组合分类、TB 1122 无该维度而**不做审定表 seed**（宁缺勿造 R3.4），仅登记其
# D2-2 明细四表库归集来源作只读溯源。D1/D3/D4/D5/D7 待各自 Wave 接入后再补条目。
#
# 每条描述性、不可编辑（editable=False，source="prefill"，tier="B"）：审计师在
# 公式管理面板据此知道「这块数从四表库哪来」，但不能把复杂归集当单条公式编辑
# （分类/账龄/客户/叶子按名归集无法压成单条 TB/SUM_TB 公式）。

_TIER_B_PROVENANCE: dict[str, list[dict]] = {
    "D6": [
        {
            "sheet_name": "D6-1",
            "anchor": "D6-1-adj-block1-*-priorUnadjusted / currentUnadjusted",
            "description": (
                "审定表 一、原值(block1) 期初/期末未审 ← tb_balance 1402 叶子子科目"
                "（期初/期末余额，get_active_filter 数据集版本，只取叶子防双算，手工优先）"
            ),
        },
        {
            "sheet_name": "D6-2",
            "anchor": "D6-2-rows",
            "description": (
                "明细表 期初未审/借贷方发生额/期后结算 ← tb_aux_balance 1402 按客户/合同"
                "维度归集 + 次年序时账 1402 贷方（一键取数，Tier B 复杂归集，非单条公式）"
            ),
        },
    ],
    # D2：诚实登记——只描述**确实由四表库归集**填充的锚点（D2-2 明细），且明确
    # 声明 D2-1 分类行**不做四表库 seed**（宁缺勿造 R3.4）。审定表分类未审是 SUMIF
    # 派生自 D2-2，不是四表库直接填。
    "D2": [
        {
            "sheet_name": "D2-2",
            "anchor": "D2-detail-rows",
            "description": (
                "明细表 期初未审/借贷方发生额/期后回款 ← tb_aux_balance 1122 按**客户维度**"
                "归集（importFromAuxBalance）+ 序时账期后回款（importPostPaymentFromLedger）"
                "（一键取数，Tier B 复杂归集，非单条公式）"
            ),
        },
        {
            "sheet_name": "D2-1",
            "anchor": "D2-adj-(individual|aging|customer-type)-*",
            "description": (
                "审定表分类行（单项计提/账龄组合/客户类型组合）未审数**不从四表库填**："
                "TB 1122 只有科目总额、无信用风险组合维度（宁缺勿造 R3.4）→ 分类未审由"
                "D2-2 明细按信用风险组合方式 SUMIF 聚合派生。可从四表库干净取的仅"
                "D2-adj-tb-amount（1122 总额），已作 Tier A 可编辑公式 TB('1122','期末余额')。"
            ),
        },
    ],
    # D1：诚实登记——只描述**确实由四表库归集**填充的锚点（D1-3 客户明细期后兑付 ←
    # 序时账 1121 贷方），且明确声明 D1-1 审定表分类行（银行承兑/商业承兑 × 原值/坏账/净值）
    # **不做四表库 seed**（宁缺勿造 R3.4）。审定表原值未审由 D1-2 按类别明细 cross-sheet 派生。
    "D1": [
        {
            "sheet_name": "D1-3",
            "anchor": "D1-cust-rows",
            "description": (
                "客户明细表 期后兑付/回款 ← **序时账 1121 贷方**（资产负债表日后科目 1121 "
                "贷方发生额 = 票据承兑收款，importPostSettlementFromLedger 按客户名归集）"
                "（一键取数，Tier B 复杂归集，非单条公式）"
            ),
        },
        {
            "sheet_name": "D1-1",
            "anchor": "D1-adj-(gross|bd)-(bank|commercial)-*",
            "description": (
                "审定表分类行（银行承兑汇票/商业承兑汇票 × 原值/坏账准备/净值三区块）未审数"
                "**不从四表库填**：TB 1121 只有科目总额、无「原值/坏账/净值 × 银行/商业」组合"
                "维度（宁缺勿造 R3.4）→ 原值未审由 D1-2 按类别明细（D1-cat-rows）cross-sheet "
                "派生、坏账来自减值模型、净值 = 原值−坏账 computed。可从四表库干净取的仅"
                "D1-adj-tb-amount（1121 总额），已作 Tier A 可编辑公式 TB('1121','期末余额')。"
            ),
        },
    ],
    # D3：诚实登记——只描述**确实由四表库归集**填充的锚点（D3-2 明细 ← tb_aux_balance 2203
    # 客户维度归集），且明确声明 D3-1 审定表双区块分类行（按性质/按账龄）**不做四表库 seed**
    # （宁缺勿造 R3.4）。审定表未审由 D3-2 明细 SUMIF 聚合派生。
    "D3": [
        {
            "sheet_name": "D3-2",
            "anchor": "D3-det-rows",
            "description": (
                "明细表 期初/期末未审等 ← tb_aux_balance 2203 按**客户维度**归集"
                "（importFromAuxBalance → /d3/import-aux-balance）"
                "（一键取数，Tier B 复杂归集，非单条公式）"
            ),
        },
        {
            "sheet_name": "D3-1",
            "anchor": "D3-adj-(nature|aging)-*",
            "description": (
                "审定表双区块分类行（一、按性质：固定资产/土地使用权/合同不成立对价/其他；"
                "二、按账龄段）未审数**不从四表库填**：TB 2203 只有科目总额、无「性质/账龄」"
                "组合维度（宁缺勿造 R3.4）→ 分类未审由 D3-2 明细（D3-det-rows）SUMIF 聚合派生。"
                "可从四表库干净取的仅 D3-adj-trial-balance-amount（2203 总额，TB↔账龄合计核对"
                "标量），已作 Tier A 可编辑公式 TB('2203','期末余额')。"
            ),
        },
    ],
    # D4：营业收入（收入类 occurrence）。诚实登记 D4-2 主营明细/D4-3 其他明细 ←
    # 序时账 6001/6051 归集（Tier B），并声明 D4-1 审定表明细行（按产品/项目）**不做
    # 四表库 seed**（宁缺勿造 R3.4）。审定表由 D4-2/D4-3 SUMIF 派生。
    "D4": [
        {
            "sheet_name": "D4-2",
            "anchor": "D4-2-rows",
            "description": (
                "主营业务收入明细表 各产品各月收入 ← **序时账 6001 贷方按产品×月归集**"
                "（d4_ledger_monthly_by_product resolver，「从序时账取数」）"
                "（一键取数，Tier B 复杂归集，非单条公式）"
            ),
        },
        {
            "sheet_name": "D4-1",
            "anchor": "D4-1-adj-rows",
            "description": (
                "审定表主营/其他收入明细行（按产品/项目）未审数**不从四表库填**：TB 6001/6051"
                "只有科目总额、无产品/项目维度（宁缺勿造 R3.4）→ 明细行由 D4-2/D4-3 明细"
                "SUMIF 聚合派生。可从四表库干净取的仅 D4-1-adj-tb-6001/D4-1-adj-tb-6051"
                "（6001 主营/6051 其他审定发生额，TB↔审定小计核对标量），已作 Tier A 可编辑"
                "公式 TB('6001','审定数')/TB('6051','审定数')。"
            ),
        },
    ],
    # D5：应收款项融资（余额类）。诚实登记 D5-2 明细 ← tb_aux_balance 1124 归集 + 序时账
    # 期后兑现，并声明 D5-1 审定表两分类行（应收票据/应收账款）**不做四表库 seed**
    # （宁缺勿造 R3.4）。审定表由 D5-2 按类别 SUMIF 派生。
    "D5": [
        {
            "sheet_name": "D5-2",
            "anchor": "D5-2-rows",
            "description": (
                "明细表 期初/期末未审/期后兑现 ← tb_aux_balance 1124 按**类别维度**归集"
                "（应收票据/应收账款）+ 序时账期后兑现"
                "（一键取数，Tier B 复杂归集，非单条公式）"
            ),
        },
        {
            "sheet_name": "D5-1",
            "anchor": "D5-1-adj-(notes-receivable|accounts-receivable)-*",
            "description": (
                "审定表两分类行（应收票据/应收账款）未审数**不从四表库填**：TB 1124 只有科目"
                "总额、无「应收票据/应收账款」类别拆分（宁缺勿造 R3.4）→ 分类未审由 D5-2 明细"
                "（D5-2-rows）按类别 SUMIF 聚合派生（useD5Adjudication categoryAggregation）。"
                "OCI 公允价值变动减项来自 D5-4 公允价值测算，非四表库。可从四表库干净取的仅"
                "D5-1-tb-amount（1124 总额，试算平衡表数核对标量），已作 Tier A 可编辑公式"
                " TB('1124','期末余额')。"
            ),
        },
    ],
    # D7：合同负债（余额类，双区块同 D3）。诚实登记 D7-2 明细 ← tb_aux_balance 2205 归集，
    # 并声明 D7-1 审定表双区块分类行（性质/账龄）**不做四表库 seed**（宁缺勿造 R3.4）。
    "D7": [
        {
            "sheet_name": "D7-2",
            "anchor": "D7-2-rows",
            "description": (
                "明细表 期初/期末未审等 ← tb_aux_balance 2205 按**客户/合同维度**归集"
                "（一键取数，Tier B 复杂归集，非单条公式）"
            ),
        },
        {
            "sheet_name": "D7-1",
            "anchor": "D7-1-adj-(nature|aging)-*",
            "description": (
                "审定表双区块分类行（一、按性质：预收货款/开发项目预收款/预收工程款/其他；"
                "二、按账龄段）未审数**不从四表库填**：TB 2205 只有科目总额、无「性质/账龄」"
                "组合维度（宁缺勿造 R3.4）→ 分类未审由 D7-2 明细（D7-2-rows）SUMIF 聚合派生"
                "（useD7Adjudication natAgg/agingByKey）。可从四表库干净取的仅"
                " D7-1-adj-aging-trial-balance-currentAudited（2205 总额，试算平衡表数核对标量），"
                "已作 Tier A 可编辑公式 TB('2205','期末余额')。"
            ),
        },
    ],
    "H5": [{"sheet_name": "H5-1", "anchor": "H5-1-cost-rows/depletion-rows", "description": "审定表原值/折耗 ← tb_balance 1631/1632 子科目余额（_fetch_tb_data 黑盒取数）"}],
    "H6": [{"sheet_name": "H6-1", "anchor": "H6-1-rows", "description": "审定表期初/期末 ← tb_balance 1606 子科目余额（过渡科目期末应为0）"}],
    "H7": [{"sheet_name": "H7-1", "anchor": "H7-1-cost-rows", "description": "审定表原值/折旧 ← trial_balance 1621（_fetch_tb_data，行业守卫agriculture/forestry/livestock/fishery）"}],
    "H8": [{"sheet_name": "H8-2", "anchor": "H8-2-rows", "description": "明细表合同级原值 ← tb_balance 1901 叶子子科目（_build_h8_detail_prefill）"}],
    "H9": [{"sheet_name": "H9-1", "anchor": "H9-1-rows", "description": "审定表租赁负债/未确认融资费用 ← tb_balance 2205+子科目（负债贷方/备抵借方）"}],
    "H10": [{"sheet_name": "H10-1", "anchor": "H10-1-adjudicated-amount", "description": "审定表资产处置损益 ← tb_balance 6115 借贷发生额（损益类）"}],
    "I1": [{"sheet_name": "I1-1", "anchor": "I1-adj-cost/amort/impair-rows", "description": "审定表原值/累计摊销/减值三区块 ← tb_balance 1701/1702/1703 子科目余额"}],
    "I2": [{"sheet_name": "I2-1", "anchor": "I2-1-rows", "description": "审定表开发支出 ← tb_balance 1717 子科目余额（资产类）"}],
    "I3": [{"sheet_name": "I3-1", "anchor": "I3-adj-rows", "description": "审定表商誉 ← tb_balance 1711（不摊销仅减值）"}],
    "I4": [{"sheet_name": "I4-1", "anchor": "I4-adj-rows", "description": "审定表长期待摊费用 ← tb_balance 1801 子科目余额"}],
    "I5": [{"sheet_name": "I5-1", "anchor": "I5-adj-rows", "description": "审定表其他非流动资产 ← tb_balance 1911 子科目余额"}],
    "I6": [{"sheet_name": "I6-1", "anchor": "I6-1-rows", "description": "审定表研发费用 ← tb_balance 6602 发生额（损益类借方）"}],
}


def tier_b_provenance(wp_code: str) -> list[dict]:
    """返回某 wp_code 的 Tier B 只读溯源描述条目（描述四表库 prefill 填什么）.

    只登记确实由 Tier B 四表库预填/归集填充的锚点；未接入的循环返回 `[]`（诚实，
    不臆造 / R7.4）。每条 `editable=False`、`source="prefill"`、`tier="B"`，`value=None`
    （面板不在此重算，seed 值由 render-config 的 `adjudication_prefill` 提供 / R5.6）。
    """
    if not wp_code:
        return []
    entries = _TIER_B_PROVENANCE.get(wp_code, [])
    return [
        {
            "wp_code": wp_code,
            "sheet_name": e.get("sheet_name", ""),
            "anchor": e.get("anchor", ""),
            "description": e.get("description", ""),
            "source": "prefill",
            "editable": False,
            "tier": "B",
            # P1-4：Tier B 是四表库**未审/明细维度**预填来源（tb_balance 期初/期末余额
            # 或 tb_aux_balance/序时账归集），与 Tier A 的 trial_balance 审定核对标量口径不同。
            "semantic": "四表库未审/明细来源（tb_balance/tb_aux_balance/序时账，非审定数）",
            "value": None,
        }
        for e in entries
    ]
