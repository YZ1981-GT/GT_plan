"""K1-2 其他应收款明细表 ← `tb_aux_balance` 归集（纯函数，无 I/O）.

K1 的**级联根**是 K1-2 明细表：账龄 / 款项性质 / 前五名 / 三阶段划分 / 坏账测算 /
长期未收回 / 关联方检查 / 两个披露表 全部从它派生。四表入库后 K1-2 若为空，
整条链路都是空的（实证：全库 `K1-2-detail-rows` 0 条，而 `tb_aux_balance` 科目 1221
在项目 `2aa00f57` 有 2857 行客户维度数据）。

🔴 行字段名逐字对齐前端 `K1DetailRow`（`useK1Detail.ts`）——
**`beginBalance` / `endBalance`，不是 `openingBalance` / `closingBalance`**；
写错前端读不到（后端导入导出曾长期用后者，属静默失效）。

款项性质规则表 `K1_NATURE_RULES` 是**单一真源**：
- 本模块 `classify_k1_nature()` 返回中文性质名（写入 K1-2 行的 `nature` 字段，
  披露②「按款项性质披露」按该字符串分组）；
- `classify_k1_nature_key()` 返回 K1-1 性质分布 syncKey（`_k1_other_receivables`
  的预填按该键归桶）；
- 两者同表同序，与前端 `k1AdjudicationModel.classifyK1Nature` 逐条对应
  （保证金 → 押金 → 备用金 → 往来/代垫/关联 → 其他）。

spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Sequence
from uuid import uuid4

#: 归集行数上限（与 F1 同口径；超出截断并由端点提示按重要性补录）
K1_DETAIL_ROW_LIMIT = 500

#: 款项性质规则表：`(正则, K1-1 syncKey, K1-2 中文性质名)`。
#:
#: 🔴 顺序即优先级，且**必须与前端 `classifyK1Nature` 逐条一致**：
#: 「保证金」先于「押金」（源模板②行名是「保证金、押金」合并列示，但 K1-1 分开两行）。
K1_NATURE_RULES: tuple[tuple[str, str, str], ...] = (
    (r"保证金", "margin", "保证金"),
    (r"押金", "deposit", "押金"),
    (r"备用金", "petty", "备用金"),
    (r"往来|代垫|关联", "intercompany", "往来款"),
)

#: 兜底桶（syncKey, 中文名）
K1_NATURE_FALLBACK: tuple[str, str] = ("other-nature", "其他")


def classify_k1_nature_key(name: str) -> str:
    """名称 → K1-1 性质分布 syncKey（`margin`/`deposit`/`petty`/`intercompany`/`other-nature`）。"""
    text = (name or "").strip()
    for pattern, key, _label in K1_NATURE_RULES:
        if re.search(pattern, text):
            return key
    return K1_NATURE_FALLBACK[0]


def classify_k1_nature(name: str) -> str:
    """名称 → K1-2 行的中文性质名（`保证金`/`押金`/`备用金`/`往来款`/`其他`）。

    披露②「按款项性质披露」按该字符串分组（`aggregateNatureFromK1Detail`），
    故**不能返回英文键**，否则附注里会出现英文行名。
    """
    text = (name or "").strip()
    for pattern, _key, label in K1_NATURE_RULES:
        if re.search(pattern, text):
            return label
    return K1_NATURE_FALLBACK[1]


def _num(v: Any) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _segment_keys(segments: Sequence[Any]) -> list[str]:
    """从账龄段对象/字典/字符串里抽 key 序列（缺省回退 K1 默认首档 `within1`）。"""
    keys: list[str] = []
    for s in segments or []:
        if isinstance(s, str):
            key = s
        elif isinstance(s, dict):
            key = str(s.get("key") or "")
        else:
            key = str(getattr(s, "key", "") or "")
        key = key.strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def build_k1_detail_rows_from_aux(
    aux_entries: Iterable[Sequence],
    segments: Sequence[Any],
    related_party_names: Iterable[str] | None = None,
    *,
    row_limit: int = K1_DETAIL_ROW_LIMIT,
    row_id_factory: Callable[[], str] | None = None,
    source_hint: str = "",
) -> list[dict]:
    """纯函数：辅助余额归集结果 → K1-2 明细行。

    Args:
        aux_entries: 每项按位置解构为 ``(aux_name, opening, debit, credit, closing)``
            （`four_table.aux_aggregation.AuxEntry` 可直接喂）。
        segments: 当前有效账龄段（项目账龄配置），行内 aging 字段按其 key 建桶。
        related_party_names: 项目关联方名称集（`related_party_registry`）；
            名称命中 → `relatedParty='是'`。
        row_limit: 行数上限（超出截断，由调用方比对 `total_units` 判断是否截断）。
        row_id_factory: 行 id 工厂（默认 uuid4；单测注入确定性工厂）。
        source_hint: 写进 `remark` 的来源说明（如 ``1221·客户``）。

    账龄**不臆造**：辅助余额表无账龄维度 → 金额整笔落**首段**，端点在 message 里
    提示审计师按实际账龄调整（前端账龄区段可一键改档）。

    Returns:
        行 dict 列表；字段名逐字对齐前端 `K1DetailRow`。
    """
    make_row_id = row_id_factory or (lambda: f"K1-2-r-{uuid4().hex[:12]}")
    seg_keys = _segment_keys(segments) or ["within1"]
    first_key = seg_keys[0]
    rp = {str(n).strip() for n in (related_party_names or []) if str(n or "").strip()}
    remark = f"由辅助余额表({source_hint})导入" if source_hint else "由辅助余额表导入"

    def _aging(amount: float) -> dict[str, float]:
        bucket = {k: 0.0 for k in seg_keys}
        bucket[first_key] = amount
        return bucket

    rows: list[dict] = []
    seq = 0
    for entry in list(aux_entries)[:row_limit]:
        name = str(entry[0] or "").strip()
        if not name:
            continue
        opening = _num(entry[1])
        debit = _num(entry[2])
        credit = _num(entry[3])
        closing_raw = _num(entry[4])
        rolled = round(opening + debit - credit, 2)
        # 期末优先用账套 closing（含账套自身结转口径），缺失时用滚存值
        end_balance = closing_raw if abs(closing_raw) > 1e-9 else rolled
        seq += 1
        rows.append({
            "id": make_row_id(),
            "seq": seq,
            "counterparty": name,
            "nature": classify_k1_nature(name),
            "relatedParty": "是" if name in rp else "否",
            "beginBalance": round(opening, 2),
            "endBalance": round(end_balance, 2),
            "agingPrior": _aging(round(opening, 2)),
            "agingCurrent": _aging(round(end_balance, 2)),
            "agingAudited": _aging(round(end_balance, 2)),
            "stage": 1,
            "badDebtProvision": 0.0,
            "netValue": round(end_balance, 2),
            "voucherNo": "",
            "conclusion": "",
            "remark": remark,
        })
    return rows


def merge_k1_detail_rows(
    existing: Sequence[dict] | None,
    incoming: Sequence[dict],
) -> tuple[list[dict], list[dict]]:
    """按 `counterparty` 合并（**手工优先**：已存在的往来单位不重复导入、逐字不覆盖）。

    Returns:
        ``(merged, added)``；`added` 为本次真正新增的行（供端点回报 `imported_count`）。
    """
    old = [r for r in (existing or []) if isinstance(r, dict)]
    have = {str(r.get("counterparty", "")).strip() for r in old}
    added = [r for r in incoming if str(r.get("counterparty", "")).strip() not in have]
    # 续编 seq，避免与既有行撞号（前端只用于显示，不作键）
    base = 0
    for r in old:
        try:
            base = max(base, int(r.get("seq") or 0))
        except (TypeError, ValueError):
            continue
    for i, r in enumerate(added, start=1):
        r["seq"] = base + i
    return old + added, added
