"""D1 应收票据明细表四表库取数 seed（D1-2 原值 / D1-4 坏账准备）.

spec: .kiro/specs/d1-four-table-extraction-formula-wiring/
      (Requirements 1.x / 2.x / Property 1, 2, 4, 5, 6, 7)

**背景（实证纠正「宁缺勿造」）**：已归档 spec `d-cycle-four-table-extraction-formulas`
对 D1 判定「TB 1121 只有科目总额、无原值/坏账×银行/商业维度」故不 seed D1-2/D1-4。
对实际入库数据的只读核查证明该前提不成立——客户科目表在**叶子层**已干净编码：

  * 原值：1121.01 应收票据_银行承兑汇票 / 1121.02 商业承兑汇票 / 1121.03 信用证
  * 坏账：1231.01 坏账准备_应收票据

且原值叶子 roll-forward 逐分精确（opening + debit − credit = closing，子科目 closing 之和
= 1121 closing）。故本模块经既有 `get_active_filter` + `TbBalance` 叶子范式（与 `prefill.py`
同一读取口径，**不新造第 3 套四表库读取**）诚实取数 seed，审计师可调整。

**四条铁律**：
  * 叶子只汇总（Property 1）：排除科目本身与中间级 rollup，防双算。
  * 手工优先（Property 2）：responses_snapshot 已有非空 remark 的锚点不覆盖。
  * fail-open（Property 4）：查询异常 / year 缺失 / 无叶子 → 跳过 seed，不阻断 render。
  * 灰度开关：调用方（render）在 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 分支内调用。

**seed 落点**：transient 写入 `responses_snapshot`（不落库，mirror `tier_a_seed` 范式），
前端 `useD1DetailCategory` / `useD1BadDebt` 既有 `loadFromResponses` 路径零改动即消费。

**符号约定**：原值（1121，debit 方向）在有符号/绝对值两种约定下均为正，直接取原值；
坏账准备（1231，credit 备抵）在两种约定下分别存 +/−，故一律 `abs()` 归一为计提口径正值
（审定表 净值 = 原值 − 坏账，坏账取正）。
"""
from __future__ import annotations

import json
import logging

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.d_cycle_extraction.anchor_registry import is_known_anchor
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)

# 金额判零阈值（对齐 prefill.py：< 0.005 视为零，跳过）
_ZERO_EPS = 0.005

_GROSS_PREFIX = "1121"       # 应收票据原值
_BAD_DEBT_PREFIX = "1231"    # 坏账准备
_BAD_DEBT_NAME_HINT = "应收票据"  # 1231 下须名称含此才归属 D1

# 前端持久化锚点（与 useD1DetailCategory / useD1BadDebt 一致）
CAT_ROWS_ANCHOR = "D1-cat-rows"
BD_INDIVIDUAL_ANCHOR = "D1-bd-individual-rows"
BD_PORTFOLIO_ANCHOR = "D1-bd-portfolio-rows"

_WP_CODE = "D1"


def _is_leaf(code: str, all_codes: list[str]) -> bool:
    """叶子判定：code 不是任何其它 code 的前缀（防中间级 rollup 与子科目双算）。"""
    if not code:
        return True
    return not any(c != code and c.startswith(code) for c in all_codes)


def _category_from_name(name: str) -> str:
    """把叶子科目名归一为披露/明细口径的种类名。

    「应收票据_信用证」→「信用证」；无下划线则原样返回。
    """
    n = (name or "").strip()
    if "_" in n:
        return n.split("_")[-1].strip() or n
    return n


def build_d1_category_rows_from_tb(leaves: list[dict]) -> list[dict]:
    """把 1121 叶子子科目映射为 D1-2 原值明细行（D1-cat-rows JSON）.

    Args:
        leaves: `[{"code","name","opening","debit","credit","closing"}, ...]`（叶子级）。

    Returns:
        D1-cat-rows 行 dict 列表。roll-forward 映射：
          priorUnadjusted=opening / currentIncrease=debit / currentDecrease=credit
          （→ 前端 currentUnadjusted computed = opening + debit − credit = closing）。
        名称含「银行承兑」→ `fixed-bank`；含「商业承兑」→ `fixed-commercial`；
        其余叶子作动态行 `dynamic-tb-{n}`（种类名取叶子名去前缀）。
        全零叶子（无期初、无发生）跳过。前端 loadFromResponses 会补齐缺失的固定行。
    """
    rows: list[dict] = []
    dyn_idx = 0
    for lf in leaves:
        opening = float(lf.get("opening") or 0)
        debit = float(lf.get("debit") or 0)
        credit = float(lf.get("credit") or 0)
        if (
            abs(opening) < _ZERO_EPS
            and abs(debit) < _ZERO_EPS
            and abs(credit) < _ZERO_EPS
        ):
            continue
        name = (lf.get("name") or "").strip()
        if "银行承兑" in name:
            row_id, category, is_fixed = "fixed-bank", "银行承兑汇票", True
        elif "商业承兑" in name:
            row_id, category, is_fixed = "fixed-commercial", "商业承兑汇票", True
        else:
            dyn_idx += 1
            row_id, category, is_fixed = (
                f"dynamic-tb-{dyn_idx}",
                _category_from_name(name),
                False,
            )
        rows.append(
            {
                "rowId": row_id,
                "category": category,
                "isFixed": is_fixed,
                "priorUnadjusted": opening,
                "priorAje": 0,
                "priorRje": 0,
                "currentIncrease": debit,
                "currentDecrease": credit,
                "currentAje": 0,
                "currentRje": 0,
            }
        )
    return rows


def build_d1_bad_debt_rows_from_tb(leaves: list[dict]) -> tuple[list[dict], list[dict]]:
    """把 1231「应收票据」叶子映射为 D1-4 坏账准备行 → (individual_rows, portfolio_rows).

    宁缺勿造（R2.3）：TB 不提供单项/组合拆分，故只 seed `按组合计提` 固定行、individual
    留空（前端补默认空行）。坏账为备抵科目，`abs()` 归一为计提口径正值。

    本期净变动 = |期末| − |期初|：≥0 记入 `currentProvision`（本期计提），
    <0 记入 `currentReversal`（本期转回，坏账减少最常见原因）——使前端
    currentUnadjusted computed = 期初 + 计提 − 转回 = 期末，roll-forward 守恒；
    审计师据 D1-15 ECL 测算细分五列（手工优先保留其编辑）。

    Args:
        leaves: 1231 名称含「应收票据」的叶子 `[{"opening","closing", ...}, ...]`。

    Returns:
        `(individual_rows, portfolio_rows)`。无可映射叶子（全零）→ `([], [])`。
    """
    opening = sum(abs(float(lf.get("opening") or 0)) for lf in leaves)
    closing = sum(abs(float(lf.get("closing") or 0)) for lf in leaves)
    if opening < _ZERO_EPS and closing < _ZERO_EPS:
        return [], []
    net = closing - opening
    portfolio_row = {
        "rowId": "fixed-portfolio",
        "category": "portfolio",
        "label": "按组合计提",
        "isSubRow": False,
        "priorUnadjusted": opening,
        "priorAje": 0,
        "priorRje": 0,
        "currentProvision": net if net >= 0 else 0,
        "currentRecovery": 0,
        "currentReversal": (-net) if net < 0 else 0,
        "currentWriteOff": 0,
        "currentOther": 0,
        "currentAje": 0,
        "currentRje": 0,
    }
    return [], [portfolio_row]


async def _fetch_leaves(
    ctx, account_prefixes: str | list[str], *, name_contains: str | None = None
) -> list[dict]:
    """经 get_active_filter + TbBalance 取若干前缀下的叶子子科目余额/发生额（复用 prefill 口径）.

    Args:
        account_prefixes: 单个前缀或前缀集（`d1_account_resolver` 反解出的**原始码**）。
        name_contains: 可选名称过滤（仅 fallback 口径下用，见 D1AccountCodes.use_provision_name_filter）。

    返回 `[{"code","name","opening","closing","debit","credit"}, ...]`（仅叶子）。
    查询异常 → 抛给调用方（seed_d1_detail_rows 统一 fail-open）。
    """
    prefixes = (
        [account_prefixes] if isinstance(account_prefixes, str) else list(account_prefixes)
    )
    prefixes = [p.strip() for p in prefixes if (p or "").strip()]
    if not prefixes:
        return []
    # 🔴 不在 SQL 里排除前缀本身：`account_mapping` 反解可能给出**精确到子科目**的原始码
    # （标准码 `1231-01` → 原始码 `1231.01`），此时排除自身会让结果恒空。
    # 交给下面的 `_is_leaf` 判定：有子科目的父级自然被排除（防双算），无子科目的
    # 精确码本身就是叶子（客户科目表扁平时也能取到数）。
    active_filter = await get_active_filter(
        ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
    )
    result = await ctx.db.execute(
        sa.select(
            TbBalance.account_code.label("code"),
            TbBalance.account_name.label("name"),
            sa.func.sum(TbBalance.opening_balance).label("opening"),
            sa.func.sum(TbBalance.closing_balance).label("closing"),
            sa.func.sum(TbBalance.debit_amount).label("debit"),
            sa.func.sum(TbBalance.credit_amount).label("credit"),
        )
        .where(
            active_filter,
            sa.or_(*[TbBalance.account_code.startswith(p) for p in prefixes]),
        )
        .group_by(TbBalance.account_code, TbBalance.account_name)
    )
    raw = [
        {
            "code": (r.code or "").strip(),
            "name": (r.name or "").strip(),
            "opening": float(r.opening or 0),
            "closing": float(r.closing or 0),
            "debit": float(r.debit or 0),
            "credit": float(r.credit or 0),
        }
        for r in result.fetchall()
    ]
    all_codes = [x["code"] for x in raw if x["code"]]
    leaves = [x for x in raw if _is_leaf(x["code"], all_codes)]
    if name_contains:
        leaves = [x for x in leaves if name_contains in x["name"]]
    return leaves


def _is_blank_skeleton(raw: str) -> bool:
    """remark 是否为「默认全零骨架」（无任何用户录入的金额）。

    🔴 实测缺陷（2026-07-31 live）：前端 `useD1BadDebt` 在底稿首次打开时就会把
    `DEFAULT_INDIVIDUAL_ROW` / `DEFAULT_PORTFOLIO_ROW` 经防抖保存落库，remark 是一段
    **非空** JSON（全零骨架）。若「手工优先」只看 remark 非空，则**任何被打开过一次的
    底稿，坏账 seed 永久不再触发** —— 实证：真实项目 wp 68c7740e… 的
    `D1-bd-portfolio-rows` 自 2026-07-09 起即为全零骨架，seed 一直静默跳过。

    D6-2 的同类语义是「明细**完全空**时才 seed」，故此处对齐：所有行的数值字段全为 0
    → 判为无用户数据（骨架的 rowId/label 由前端按默认行重建，逐字相同，不存在可丢内容）。
    只要有任一非零金额（或解析失败 = 内容未知）就一律视为有手工数据，绝不覆盖。
    """
    try:
        parsed = json.loads(raw)
    except Exception:  # noqa: BLE001 — 内容未知 → 保守视为有手工数据
        return False
    if not isinstance(parsed, list):
        return False
    if not parsed:
        return True
    for row in parsed:
        if not isinstance(row, dict):
            return False  # 形态未知 → 保守
        for value in row.values():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)) and abs(float(value)) >= _ZERO_EPS:
                return False
            if isinstance(value, str):
                stripped = value.strip()
                # 纯数字字符串也算金额（历史数据可能存字符串）
                try:
                    if stripped and abs(float(stripped)) >= _ZERO_EPS:
                        return False
                except ValueError:
                    continue
    return True


def _has_persisted(responses_snapshot: dict, anchor: str) -> bool:
    """responses_snapshot 中该锚点是否已有**用户数据**（手工优先判定）。

    非空 remark 但内容是默认全零骨架时返回 False（见 `_is_blank_skeleton`）。
    """
    existing = responses_snapshot.get(anchor)
    if not isinstance(existing, dict):
        return False
    raw = (existing.get("remark") or "").strip()
    if not raw:
        return False
    return not _is_blank_skeleton(raw)


def _seed(responses_snapshot: dict, anchor: str, remark: str) -> None:
    """transient seed（不落库）：写入锚点 remark，保留既有 conclusion。"""
    existing = responses_snapshot.get(anchor)
    merged = dict(existing) if isinstance(existing, dict) else {}
    merged.setdefault("conclusion", "")
    merged["remark"] = remark
    responses_snapshot[anchor] = merged


async def seed_d1_detail_rows(ctx, responses_snapshot: dict, codes=None) -> None:
    """从四表库 seed D1-2 原值明细 / D1-4 坏账准备明细进 responses_snapshot（原地）.

    手工优先 + 锚点合法校验 + 全程 fail-open。调用方须在灰度开关分支内调用。

    Args:
        codes: `D1AccountCodes`（`d1_account_resolver.resolve_d1_account_codes` 的结果）。
            为 None 时自行解析；解析失败自动回退兜底前缀（等价改动前行为）。
    """
    try:
        if getattr(ctx, "year", None) is None:
            logger.debug("D1 detail seed: 缺 year，跳过（fail-open）")
            return

        # ─── 科目定位：报表规则映射（BS-005）→ 标准码 → account_mapping → 原始码 ────
        if codes is None:
            try:
                from app.services.d_cycle_extraction.d1_account_resolver import (
                    resolve_d1_account_codes,
                )

                codes = await resolve_d1_account_codes(ctx)
            except Exception as e:  # noqa: BLE001
                logger.debug("D1 detail seed: 科目解析失败（用兜底前缀）: %s", e)
                codes = None
        gross_prefixes = list(getattr(codes, "gross", None) or [_GROSS_PREFIX])
        provision_prefixes = list(getattr(codes, "provision", None) or [_BAD_DEBT_PREFIX])
        provision_name_filter = (
            _BAD_DEBT_NAME_HINT
            if (codes is None or getattr(codes, "use_provision_name_filter", True))
            else None
        )

        # ─── D1-2 原值明细（原值科目叶子）─────────────────────────────────
        if is_known_anchor(_WP_CODE, CAT_ROWS_ANCHOR) and not _has_persisted(
            responses_snapshot, CAT_ROWS_ANCHOR
        ):
            try:
                gross_leaves = await _fetch_leaves(ctx, gross_prefixes)
                cat_rows = build_d1_category_rows_from_tb(gross_leaves)
                if cat_rows:
                    _seed(
                        responses_snapshot,
                        CAT_ROWS_ANCHOR,
                        json.dumps(cat_rows, ensure_ascii=False),
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning("D1 detail seed: 原值(1121) 取数失败（fail-open）: %s", e)

        # ─── D1-4 坏账准备（坏账科目叶子；fallback 口径下叠名称过滤）──────────
        if is_known_anchor(_WP_CODE, BD_PORTFOLIO_ANCHOR) and not _has_persisted(
            responses_snapshot, BD_PORTFOLIO_ANCHOR
        ):
            try:
                bd_leaves = await _fetch_leaves(
                    ctx, provision_prefixes, name_contains=provision_name_filter
                )
                _individual, portfolio = build_d1_bad_debt_rows_from_tb(bd_leaves)
                if portfolio:
                    _seed(
                        responses_snapshot,
                        BD_PORTFOLIO_ANCHOR,
                        json.dumps(portfolio, ensure_ascii=False),
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning("D1 detail seed: 坏账(1231) 取数失败（fail-open）: %s", e)
    except Exception as e:  # noqa: BLE001 — 顶层兜底，绝不阻断 render
        logger.warning("D1 detail seed 顶层异常（fail-open）: %s", e)
