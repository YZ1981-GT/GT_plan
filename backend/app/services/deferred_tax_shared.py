"""四表库取数共享件 —— 科目层级判定 / 语义槽分类 / 槽聚合。

spec: `.kiro/specs/n345-four-table-extraction-alignment/`

**为什么抽这里**
----------------
N1（递延所得税资产 1811 + 负债 2901）已把「叶子聚合 + 语义槽分类 + 全零槽跳过」做完并
活体实测通过；N3（递延所得税负债 2901）需要同样能力，N4/N5 需要其中的科目谓词与叶子判定。
平台已有「不新造第 3 套四表库读取」的收敛铁律 → 抽共享模块，各策略引用，
而不是在 N3 里复制一份。

**本模块只做纯计算 + SQLAlchemy 谓词构造**，不发起查询、不 import 具体 ORM 模型
（列对象由调用方传入），因此可被任意四表（`tb_balance` / `tb_ledger` / `trial_balance`）复用。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import sqlalchemy as sa

__all__ = [
    "LIABILITY_SLOTS",
    "LIABILITY_SLOT_OTHER",
    "aggregate_by_slot",
    "classify_liability_subaccount",
    "code_predicate",
    "leaf_rows",
    "parse_num",
]


# ─── 数值解析 ─────────────────────────────────────────────────────────────────


def parse_num(v: Any) -> float:
    """安全解析数值：None / 空串 / 非数 / NaN → 0.0。"""
    if v is None or v == "":
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f != f else f  # NaN → 0.0


# ─── 科目谓词 ─────────────────────────────────────────────────────────────────


def code_predicate(col: Any, code: str):
    """单个科目码 → 过滤谓词（单码走前缀、``start~end`` 走区间）。

    与 `report_account_mapping.build_trial_balance_code_filter` 同语义，但那个函数把列名
    写死为 `standard_account_code`（`trial_balance` 的列）；本函数由调用方传列对象，
    故 `tb_balance.account_code` / `tb_ledger.account_code` 都能用。
    """
    text = str(code).strip()
    if "~" in text:
        lo, hi = (p.strip() for p in text.split("~", 1))
        return sa.and_(col >= lo, col <= hi + "\uffff")  # 覆盖区间上界下所有子科目
    return col.like(f"{text}%")


def leaf_rows(rows: Sequence[Any]) -> list[Any]:
    """只保留叶子行（无更深层级），防与中间级 rollup 双算。

    🔴 有意使用**不带点**的 `startswith`：科目表既有点分层级（`2901.01`）也有平铺层级
    （`290101`），不带点两者都能正确判定；带点会把平铺层级的父级也当成叶子
    → 与其子科目同时计入而双算。
    """
    codes = [str(getattr(r, "account_code", "") or "").strip() for r in rows]
    out: list[Any] = []
    for r in rows:
        code = str(getattr(r, "account_code", "") or "").strip()
        if not code:
            continue
        if any(c != code and c.startswith(code) for c in codes):
            continue
        out.append(r)
    return out


# ─── 递延所得税负债语义槽（源模板 N1 披露表负债段 R23:R27）────────────────────

# 🔴 用**英文语义槽**而非中文显示名作键：源模板负债段第 4 项两版用语不同
# （上市「使用权资产」/ 国企「租赁形成」）→ 中文名作键必然让一版对不上。
# 显示名映射的单一真源在前端（`N1_LIABILITY_SLOT_LABEL` / `n3LiabilitySlotLabel`）。
LIABILITY_SLOT_OTHER = "other"
LIABILITY_SLOTS: list[str] = [
    "depreciation",            # 购入摊销年限大于税法规定的资产
    "afs_fv",                  # 可供出售金融资产公允价值变动
    "investment_property_fv",  # 投资性房地产公允价值变动
    "lease",                   # 使用权资产(上市) / 租赁形成(国企)
    LIABILITY_SLOT_OTHER,      # 其他
]


def classify_liability_subaccount(name: str | None) -> str:
    """递延所得税负债子科目名 → 语义槽（无法识别 → ``other``）。

    映射依据 = N1 源模板 `附注披露信息（上市公司）` / `（国企）` 的 R23:R27 行语义
    + 活体实测子科目名（`2901.01 公允价值变动` / `2901.02 固定资产加速折旧` /
    `2901.03 经营租赁相关`）。

    🔴 判定顺序有意如此：`投资性房地产` 必须先于泛化的 `公允价值`，否则
    「投资性房地产公允价值变动」会被 `afs_fv` 抢走。同理 `加速折旧`
    （税法折旧快于账面 ⇒ 账面摊销年限大于税法规定）归 `depreciation`。
    """
    n = (name or "").strip()
    if "投资性房地产" in n:
        return "investment_property_fv"
    if any(k in n for k in ("加速折旧", "摊销年限", "折旧年限", "加速摊销")):
        return "depreciation"
    if any(k in n for k in ("租赁", "使用权")):
        return "lease"
    if "公允价值" in n:
        return "afs_fv"
    return LIABILITY_SLOT_OTHER


# ─── 槽聚合 ───────────────────────────────────────────────────────────────────


def aggregate_by_slot(
    rows: Sequence[Any],
    classify: Callable[[str | None], str],
    *,
    absolute: bool = False,
) -> dict[str, dict[str, float]]:
    """叶子行 → ``{槽: {opening, closing}}``；全零槽跳过。

    Args:
        classify: 子科目名 → 槽键。
        absolute: 负债类开启 —— 活体实测 `2901` 期末同时存在 `-233512.19`（负数约定）
            与 `200530.32`（绝对值约定）两种符号口径，统一归一为披露口径正数。
    """
    norm: Callable[[float], float] = abs if absolute else (lambda v: v)
    agg: dict[str, dict[str, float]] = {}
    for r in rows:
        slot = classify(getattr(r, "account_name", None))
        cell = agg.setdefault(slot, {"opening": 0.0, "closing": 0.0})
        cell["opening"] += norm(parse_num(getattr(r, "opening_balance", None)))
        cell["closing"] += norm(parse_num(getattr(r, "closing_balance", None)))
    return {
        slot: {"opening": round(v["opening"], 2), "closing": round(v["closing"], 2)}
        for slot, v in agg.items()
        if abs(v["opening"]) >= 0.005 or abs(v["closing"]) >= 0.005
    }
