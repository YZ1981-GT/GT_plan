"""`tb_balance` 叶子科目聚合（跨循环共享，纯函数）。

**为什么必须是「叶子」而不是「最深层级」**

客户科目表是**参差的多级树**：同一父科目下，有的子科目还有孙科目，有的没有。实证项目
`0ec33ac9`/2025 的 `1221 其他应收款`::

    1221                      父（= 269,885,933.03）
    ├─ 1221.11 个人往来        叶子（3,597,359.45）        ← 无子科目
    ├─ 1221.12 保证金及押金    叶子（55,035,942.52）       ← 无子科目
    ├─ 1221.13 代收代付款项    非叶子
    │   ├─ 1221.13.01 …       叶子
    │   └─ …
    ├─ 1221.15 资金往来        非叶子 → 1221.15.01/.02/.04/.06/.08 叶子
    └─ 1221.98 其他            非叶子 → 1221.98.01…99 叶子

「只取最深层级（depth == max_depth）」会**整段丢掉** `1221.11` 与 `1221.12`
（合计 58,633,301.97 = 21.7%），而这两支恰好是 K1「款项性质分布」最核心的
个人往来 / 保证金押金桶 → 性质预填恒 0。正确口径 = 叶子（无子科目的最明细行），
其金额之和等于父科目行金额（Property 1，实测逐分相等）。

叶子判定与 `trial_balance_service.recalc_unadjusted` 同语义（同数据集 + 存在
`code + '.'` 前缀的兄弟行即非叶子）。

**不做方向翻转**：`trial_balance_service` 会按 `closing_direction` 把余额归一为
「借正贷负」（`debit → +ABS()`）。K1 侧**不采用** —— 实测存在 `direction='debit'`
且余额合法为负的叶子（项目 `2aa00f57` 的 `1221.98.07 = -227,132.40`），`+ABS()` 会
把它翻正，破坏「叶子和 == 父科目额」勾稽。备抵科目改在**聚合结果**上取绝对值即可
（`tb_balance` 存在「无符号 + 方向列」与「已带符号」两种约定并存，两者 `abs()` 同解）。

spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/
      Requirements 2.1~2.4 / Property 1
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LeafRow:
    """`tb_balance` 单行的取数视图（只保留聚合需要的列）。"""

    account_code: str
    account_name: str = ""
    opening: float = 0.0
    closing: float = 0.0
    debit: float = 0.0
    credit: float = 0.0
    #: `tb_balance.closing_direction`
    direction: str = ""
    #: `tb_balance.opening_direction` —— 🔴 **可能与期末方向不同**，实证项目
    #: `52c04ed1` 的 `2202.04 预提供应商返利` 期初 debit / 期末 credit，
    #: `2202.98 商务系统` 期初 credit / 期末 debit。用期末方向算期初会不平。
    opening_direction: str = ""
    dataset_id: str | None = None


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def to_leaf_rows(rows) -> list[LeafRow]:
    """把 SQLAlchemy Row / dict 序列归一为 :class:`LeafRow`（缺列按 0 / 空串）。

    🔴 **对已是 `LeafRow` 的元素幂等**（2026-08-05 实测踩坑后加）：本函数按 **DB 列名**
    取值（``closing_balance`` / ``debit_amount`` / ``closing_direction``），而 `LeafRow`
    的字段名是 ``closing`` / ``debit`` / ``direction`` —— 两套名字不同。若把已归一的
    `LeafRow` 列表再喂进来，``account_code`` 能取到但**全部金额会静默变 0**。

    这个坑很容易踩：:func:`tb_query.fetch_tb_subtree` 返回的就是 `LeafRow`，而
    :func:`parent_check.build_parent_check` 内部会对入参再调本函数一次
    （H 循环各自用裸 SQL 拿原始行故未暴露）。症状是 ``leaf_sum`` 恒 0 而
    ``trial_balance`` 有值，看起来像「叶子聚合坏了」。
    """
    out: list[LeafRow] = []
    for r in rows or []:
        if isinstance(r, LeafRow):
            out.append(r)
            continue
        get = r.get if isinstance(r, dict) else (lambda k, _r=r: getattr(_r, k, None))
        code = str(get("account_code") or "").strip()
        if not code:
            continue
        ds = get("dataset_id")
        out.append(
            LeafRow(
                account_code=code,
                account_name=str(get("account_name") or "").strip(),
                opening=_f(get("opening_balance")),
                closing=_f(get("closing_balance")),
                debit=_f(get("debit_amount")),
                credit=_f(get("credit_amount")),
                direction=str(get("closing_direction") or "").strip(),
                opening_direction=str(get("opening_direction") or "").strip(),
                dataset_id=None if ds is None else str(ds),
            )
        )
    return out


def select_leaves(rows: list[LeafRow]) -> list[LeafRow]:
    """筛出叶子行：不存在以 ``本码 + '.'`` 开头的**同数据集**兄弟行。纯函数。

    同一 ``account_code`` 可能在多个 ``dataset_id`` 下各有一行（staged / active /
    superseded）；子科目须与父级同数据集才算其子科目，故按 ``dataset_id`` 分桶判定。
    调用方应先用 ``get_active_filter`` 锁定 active 数据集，此处的分桶只是兜底。
    """
    by_dataset: dict[str | None, list[LeafRow]] = {}
    for r in rows or []:
        by_dataset.setdefault(r.dataset_id, []).append(r)

    out: list[LeafRow] = []
    for _ds, group in by_dataset.items():
        codes = {r.account_code for r in group}
        for r in group:
            prefix = r.account_code + "."
            if any(c != r.account_code and c.startswith(prefix) for c in codes):
                continue
            out.append(r)
    return out


def filter_by_prefixes(rows: list[LeafRow], prefixes) -> list[LeafRow]:
    """按科目码前缀集过滤（``code == p`` 或 ``code.startswith(p + '.')``）。

    严格要求点号边界 —— 否则前缀 ``1221`` 会误命中 ``12210``（不同科目）。
    """
    ps = [str(p or "").strip() for p in (prefixes or []) if str(p or "").strip()]
    if not ps:
        return []
    out: list[LeafRow] = []
    for r in rows or []:
        code = r.account_code
        if any(code == p or code.startswith(p + ".") for p in ps):
            out.append(r)
    return out


def sql_prefixes_for_specs(specs) -> list[str]:
    """把报表公式的科目编号规格转成**宽口径 SQL 前缀**（供 ``LIKE '{p}%'`` 下推）。

    - 单码 ``2202`` → ``2202``
    - 区间 ``1401~1499`` → 取两端公共前导串 ``14``（宽取，再由
      :func:`filter_by_code_specs` 做精确收敛）

    区间两端无公共前导（如 ``1401~2202``）时返回两端各自的一级码，仍属宽取。

    🔴 由 F1 提升为共享件（F5 的 ``IS-002`` 是 ``SUM_TB('6401~6499')`` 区间口径，
    G 循环的 ``TB_SUM('1401~1499')`` 同形），禁止各循环再抄一份。
    """
    out: list[str] = []
    for raw in specs or []:
        spec = str(raw or "").strip()
        if not spec:
            continue
        if "~" not in spec:
            out.append(spec)
            continue
        lo, _, hi = (p.strip() for p in spec.partition("~"))
        common = ""
        for a, b in zip(lo, hi):
            if a != b:
                break
            common += a
        if common:
            out.append(common)
        else:
            out.extend([lo, hi])
    return [p for p in dict.fromkeys(out) if p]


def filter_by_code_specs(leaves: list[LeafRow], specs) -> list[LeafRow]:
    """按报表公式的科目编号规格精确过滤叶子（支持单码前缀与 ``lo~hi`` 区间）。纯函数。

    单码走 :func:`filter_by_prefixes` 的严格点号边界；区间按**一级科目段**
    （首个 ``.`` 之前）字符串比较落在 ``[lo, hi]`` 内 —— 与
    ``build_trial_balance_code_filter`` 的区间语义一致（``hi`` 含其全部子科目）。
    """
    singles = [s for s in (str(x or "").strip() for x in specs or []) if s and "~" not in s]
    ranges = [
        tuple(p.strip() for p in str(x).partition("~")[::2])
        for x in specs or []
        if "~" in str(x or "")
    ]
    picked: dict[str, LeafRow] = {}
    for row in filter_by_prefixes(leaves, singles):
        picked[f"{row.dataset_id}|{row.account_code}"] = row
    for row in leaves or []:
        head = row.account_code.split(".", 1)[0]
        for lo, hi in ranges:
            if lo <= head <= hi:
                picked[f"{row.dataset_id}|{row.account_code}"] = row
                break
    return list(picked.values())


def aggregate_leaves(
    leaves: list[LeafRow],
    prefixes,
    *,
    absolute: bool = False,
) -> dict[str, float]:
    """按前缀集过滤叶子后求和 opening / closing / debit / credit。

    Args:
        leaves: 已经 :func:`select_leaves` 过的叶子行。
        prefixes: 原始码前缀集。
        absolute: 备抵科目置 ``True`` —— 对**聚合结果**取绝对值
            （不在行级翻转，见模块 docstring）。

    Returns:
        ``{"opening","closing","debit","credit"}``；无命中行时全 0。
    """
    picked = filter_by_prefixes(leaves, prefixes)
    agg = {
        "opening": sum(r.opening for r in picked),
        "closing": sum(r.closing for r in picked),
        "debit": sum(r.debit for r in picked),
        "credit": sum(r.credit for r in picked),
    }
    if absolute:
        agg = {k: abs(v) for k, v in agg.items()}
    return agg


def parent_totals(rows: list[LeafRow], prefix: str) -> dict[str, float]:
    """取父科目行本身的金额（供「叶子和 == 父额」勾稽自检）。无该行返全 0。"""
    p = (prefix or "").strip()
    picked = [r for r in rows or [] if r.account_code == p]
    return {
        "opening": sum(r.opening for r in picked),
        "closing": sum(r.closing for r in picked),
        "debit": sum(r.debit for r in picked),
        "credit": sum(r.credit for r in picked),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 符号约定自校验聚合（`tb_balance` 两种存储约定并存，无法用单一口径覆盖）
# ─────────────────────────────────────────────────────────────────────────────

#: 「原样求和」—— 余额已带符号，`closing_direction` 只作描述
CONVENTION_AS_STORED = "as_stored"
#: 「方向定符号」—— 余额存无符号绝对值，与父科目方向不同的叶子取负
CONVENTION_DIRECTIONAL = "directional"

_RECON_TOLERANCE = 0.005


@dataclass(frozen=True)
class LeafTotals:
    """叶子聚合结果 + 符号约定判定 + 父额勾稽证据。

    Attributes:
        opening / closing / debit / credit: 聚合金额（``absolute=True`` 时已取绝对值）。
        convention: 每个字段实际采用的约定
            （``{"opening": "directional", "closing": "as_stored", ...}``）。
        parent: 父科目行金额（绝对值口径）。
        diff: 聚合额与父额的差（绝对值口径）；全部落在容差内时 :attr:`matched` 为真。
        leaf_codes: 参与聚合的叶子科目码（升序）。
    """

    opening: float = 0.0
    closing: float = 0.0
    debit: float = 0.0
    credit: float = 0.0
    convention: dict[str, str] = field(default_factory=dict)
    parent: dict[str, float] = field(default_factory=dict)
    diff: dict[str, float] = field(default_factory=dict)
    leaf_codes: tuple[str, ...] = ()

    @property
    def matched(self) -> bool:
        return all(abs(v) <= _RECON_TOLERANCE for v in (self.diff or {}).values())

    def as_dict(self) -> dict:
        return {
            "opening": round(self.opening, 2),
            "closing": round(self.closing, 2),
            "debit": round(self.debit, 2),
            "credit": round(self.credit, 2),
            "convention": dict(self.convention),
            "parent": {k: round(v, 2) for k, v in (self.parent or {}).items()},
            "diff": {k: round(v, 2) for k, v in (self.diff or {}).items()},
            "leaf_codes": list(self.leaf_codes),
            "matched": self.matched,
        }


def resolve_leaf_totals(
    rows: list[LeafRow],
    prefix: str,
    *,
    absolute: bool = True,
    tolerance: float = _RECON_TOLERANCE,
) -> LeafTotals:
    """按**父科目额自校验**聚合某科目族的叶子，自动识别符号约定。纯函数。

    **为什么需要两种约定并存的处理**

    DB 只读实证（13 个「项目 × 科目族」组合，见 spec 的 Notes）表明 `tb_balance` 里
    同一份业务数据存在两种存储约定，且**没有一种口径对所有项目都对**::

        项目 0ec33ac9 / 2202  叶子全为正数 + closing_direction 定性质
            原样求和 261,347,490.52   ≠ 父额 254,189,472.38  ✗ 差 7,158,018.14
            方向定符号 254,189,472.38 == 父额                ✓

        项目 12c15a96 / 2202  叶子已带符号（负债存负数，借方性质子科目存正数）
            原样求和 −254,189,472.38  == 父额（绝对值）       ✓
            方向定符号 −261,347,490.52 ≠ 父额                ✗ 差 7,158,018.14

    故本函数**不猜约定**，而是两种都算，取与父科目额勾稽成立的那一种；两者都不成立时
    取更接近的一种并在 :attr:`LeafTotals.diff` 暴露差额（由调用方渲染 danger 提示）。
    父科目行缺失或为 0 时退化为原样求和（无参照物可校验）。

    这样做的额外收益：``diff`` 天然就是 Property 1「叶子和 == 父科目额」的证据，
    不需要调用方再算一遍。

    Args:
        rows: 该科目族的**全部**行（含父科目行本身）—— 父行是判定依据，不可预先剔除。
        prefix: 父科目原始码（如 ``2202``）。
        absolute: ``True``（默认）时对聚合结果取绝对值，用于负债 / 备抵等正数展示口径。
        tolerance: 勾稽容差（元）。

    Returns:
        :class:`LeafTotals`。无任何行时全 0 且 ``leaf_codes`` 为空。
    """
    p = (prefix or "").strip()
    scoped = [r for r in rows or [] if r.account_code == p or r.account_code.startswith(p + ".")]
    if not scoped:
        return LeafTotals()

    parent_row = next((r for r in scoped if r.account_code == p), None)
    parent_dir = (parent_row.direction if parent_row is not None else "").strip().lower()
    parent_abs = {
        "opening": abs(parent_row.opening) if parent_row is not None else 0.0,
        "closing": abs(parent_row.closing) if parent_row is not None else 0.0,
        "debit": abs(parent_row.debit) if parent_row is not None else 0.0,
        "credit": abs(parent_row.credit) if parent_row is not None else 0.0,
    }

    leaves = [r for r in select_leaves(scoped) if r.account_code != p]
    if not leaves:
        # 父科目本身就是叶子（无子科目）→ 直接用父额，勾稽恒成立
        vals = {k: (abs(v) if absolute else v) for k, v in parent_abs.items()}
        return LeafTotals(
            **vals,
            convention=dict.fromkeys(vals, CONVENTION_AS_STORED),
            parent=parent_abs,
            diff=dict.fromkeys(vals, 0.0),
            leaf_codes=(p,) if parent_row is not None else (),
        )

    # 🔴 期初必须用 `opening_direction`、期末用 `closing_direction` —— 两者可能不同
    #    （实证 52c04ed1 的 2202.04 期初 debit / 期末 credit）。用期末方向算期初，
    #    该项目的期初叶子和会比父额多 2,116,034.22（= 2 × 847,931.51 + 2 × 210,085.60）。
    #    发生额（debit / credit）无方向概念，恒按原样求和。
    parent_open_dir = (
        parent_row.opening_direction if parent_row is not None else ""
    ).strip().lower() or parent_dir

    def _sign(row: LeafRow, field_dir: str, ref_dir: str) -> int:
        d = (field_dir or "").strip().lower()
        if not ref_dir or not d:
            return 1
        return 1 if d == ref_dir else -1

    fields = ("opening", "closing", "debit", "credit")
    out: dict[str, float] = {}
    convention: dict[str, str] = {}
    diff: dict[str, float] = {}
    for fld in fields:
        as_stored = sum(getattr(r, fld) for r in leaves)
        if fld == "opening":
            directional = sum(
                r.opening * _sign(r, r.opening_direction, parent_open_dir) for r in leaves
            )
        elif fld == "closing":
            directional = sum(
                r.closing * _sign(r, r.direction, parent_dir) for r in leaves
            )
        else:
            # 发生额无方向语义 → 只有原样求和一种口径
            directional = as_stored
        ref = parent_abs[fld]
        d_stored = abs(abs(as_stored) - ref)
        d_dir = abs(abs(directional) - ref)
        if parent_row is None or ref <= tolerance:
            # 无参照物（父行缺失或父额为 0）→ 原样求和，不做无依据的翻转
            chosen, chosen_diff, name = as_stored, d_stored, CONVENTION_AS_STORED
        elif d_dir + tolerance < d_stored:
            chosen, chosen_diff, name = directional, d_dir, CONVENTION_DIRECTIONAL
        else:
            chosen, chosen_diff, name = as_stored, d_stored, CONVENTION_AS_STORED
        out[fld] = abs(chosen) if absolute else chosen
        convention[fld] = name
        diff[fld] = chosen_diff

    return LeafTotals(
        **out,
        convention=convention,
        parent=parent_abs,
        diff=diff,
        leaf_codes=tuple(sorted(r.account_code for r in leaves)),
    )


def leaf_signs(
    rows: list[LeafRow], prefix: str, field: str = "closing"
) -> dict[str, int]:
    """返回各叶子在 :func:`resolve_leaf_totals` 选定约定下的符号（``+1`` / ``-1``）。

    供分类桶聚合复用同一约定 —— 否则「按桶求和」与「按科目族求和」会用不同符号，
    导致「各桶之和 ≠ 叶子合计」（Property 2 失败）。

    Args:
        field: ``'opening'`` 或 ``'closing'``（两期方向列不同，须分别取）。
    """
    totals = resolve_leaf_totals(rows, prefix)
    leafset = set(totals.leaf_codes)
    if totals.convention.get(field) != CONVENTION_DIRECTIONAL:
        return {code: 1 for code in totals.leaf_codes}
    p = (prefix or "").strip()
    scoped = [r for r in rows or [] if r.account_code == p or r.account_code.startswith(p + ".")]
    parent_row = next((r for r in scoped if r.account_code == p), None)
    if field == "opening":
        ref_dir = (
            parent_row.opening_direction if parent_row is not None else ""
        ).strip().lower() or (parent_row.direction if parent_row is not None else "").strip().lower()
    else:
        ref_dir = (parent_row.direction if parent_row is not None else "").strip().lower()
    out: dict[str, int] = {}
    for r in scoped:
        if r.account_code not in leafset:
            continue
        d = (r.opening_direction if field == "opening" else r.direction).strip().lower()
        out[r.account_code] = 1 if (not ref_dir or not d or d == ref_dir) else -1
    return out


def aggregate_by_specs(
    leaves: list[LeafRow],
    specs,
    *,
    absolute: bool = False,
) -> dict[str, float]:
    """同 :func:`aggregate_leaves`，但入参是**科目编号规格**（支持 ``lo~hi`` 区间）。

    供 F2/F5 这类报表行公式本身就是区间口径（``SUM_TB('1401~1499')`` /
    ``SUM_TB('6401~6499')``）的循环使用。
    """
    picked = filter_by_code_specs(leaves, specs)
    agg = {
        "opening": sum(r.opening for r in picked),
        "closing": sum(r.closing for r in picked),
        "debit": sum(r.debit for r in picked),
        "credit": sum(r.credit for r in picked),
    }
    if absolute:
        agg = {k: abs(v) for k, v in agg.items()}
    return agg


def leaf_sign_map(rows: list[LeafRow], prefix: str) -> dict[str, dict[str, int]]:
    """一次给出期初 / 期末两期的叶子符号表（分类桶聚合的标准入参）。

    Returns:
        ``{"opening": {code: ±1}, "closing": {code: ±1}}``
    """
    return {
        "opening": leaf_signs(rows, prefix, "opening"),
        "closing": leaf_signs(rows, prefix, "closing"),
    }


__all__ = [
    "CONVENTION_AS_STORED",
    "CONVENTION_DIRECTIONAL",
    "LeafRow",
    "LeafTotals",
    "aggregate_by_specs",
    "aggregate_leaves",
    "filter_by_code_specs",
    "filter_by_prefixes",
    "leaf_sign_map",
    "leaf_signs",
    "parent_totals",
    "resolve_leaf_totals",
    "select_leaves",
    "sql_prefixes_for_specs",
    "to_leaf_rows",
]
