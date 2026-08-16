"""备抵科目反解结果的名称过滤 —— 拦 ``account_mapping`` 的错映射。

问题背景（2026-08-05 真实库实证）
--------------------------------
四表取数的备抵侧链路是：

    报表行公式 / 槽兜底码（**标准码**，横杠体系 ``1231-02``）
        → ``account_mapping`` 反解 → 客户**原始码**（点号体系 ``1231.02``）
        → 前缀匹配 ``tb_balance``

而 ``account_mapping`` 里存在一条 ``auto_fuzzy`` 错映射::

    original_account_code  original_account_name      standard_account_code  type
    1231.05                坏账准备_长期应收款          1231-02               auto_fuzzy   (2 个项目)

⇒ 任何按 ``1231-02``（坏账准备-应收账款）反解的路径，都会把**长期应收款**的
坏账准备一并纳入 D2 的备抵，让应收账款净额偏小。

错在**映射数据**、不在定位逻辑，故正解是在反解之后叠一道
「原始科目名须含本槽主体关键词」的过滤（同 F1 的
``use_provision_name_filter`` 范式），并把被剔除的行**如实记录**下来
供溯源面板展示 —— 而不是静默丢弃。

同族陷阱（为什么关键词不能宽）
------------------------------
D2 的主体关键词只能是「应收账款」，**不能**写成「应收」：错映射进来的那条
名叫「坏账准备_长期应收款」，它含「应收」但不含「应收账款」，正是靠这个
差别拦住的。关键词写宽一格，这道过滤就完全空转。

设计约束
--------
- 纯函数，无 DB / 无 ORM，便于单测与反向自检
- ``subject_keywords`` 为空 ⇒ **空操作**（原样返回，``dropped`` 为空）。
  这保证既有循环（G/H/E1/M8）接入本模块时行为逐字不变
- 判据用「原始科目名」而非码 —— 码本身看不出归属（``1231.05`` 在 client 表
  是长期应收款、在 standard 表 ``1231-05`` 却是合同资产，见 memory
  「点号码与横杠码是两套体系且语义可能完全不同」）
- 名称缺失（``None`` / 空串）时**保留**该码并标注 ``name_missing``：
  宁可多算也不静默丢一个真实备抵；由溯源面板提示人工确认

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "DroppedCode",
    "FilterResult",
    "normalize_account_name",
    "filter_provision_codes",
]

#: 名称缺失时的标注（保留该码，不剔除）
REASON_NAME_MISSING = "name_missing"


def normalize_account_name(name: str | None) -> str:
    """科目名归一 —— 只去空白与常见分隔符，**不做**更激进的归一化。

    分隔符归一的理由：同一科目在 client 表写 ``坏账准备_应收账款``、
    在 standard 表写 ``坏账准备-应收账款``，主体关键词匹配不应被分隔符影响。

    🔴 刻意**不**做的事：不去「其他」「合计」等词、不做同义词映射、不转拼音。
    再激进的归一化会放过真错位（同 memory「行名比对的归一化只许去空白 +
    去行业适用性标记」的教训）。
    """
    if not name:
        return ""
    s = str(name)
    for ch in (" ", "\u3000", "\t", "\r", "\n", "_", "-", "－", "—", "·"):
        s = s.replace(ch, "")
    return s


@dataclass(frozen=True)
class DroppedCode:
    """被名称过滤剔除的一条原始码（供溯源面板展示）。"""

    code: str
    name: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "name": self.name, "reason": self.reason}


@dataclass(frozen=True)
class FilterResult:
    """过滤结果。

    Attributes:
        kept: 保留的原始码（保持入参顺序，去重）
        dropped: **真被剔除**的码及理由 —— 与 ``kept`` 无交集
        warnings: 保留但需人工确认的码（当前只有「名称缺失」一种）——
            这些码**在** ``kept`` 里。刻意与 ``dropped`` 分开，否则
            溯源面板显示「已剔除 N 条」会把实际保留的行算进去。
        applied: 是否真的执行了过滤（``subject_keywords`` 为空时为 False）
    """

    kept: tuple[str, ...]
    dropped: tuple[DroppedCode, ...]
    warnings: tuple[DroppedCode, ...] = ()
    applied: bool = True

    @property
    def dropped_dicts(self) -> list[dict[str, str]]:
        return [d.as_dict() for d in self.dropped]

    @property
    def warning_dicts(self) -> list[dict[str, str]]:
        return [d.as_dict() for d in self.warnings]


def filter_provision_codes(
    codes: tuple[str, ...] | list[str],
    name_by_code: dict[str, str | None],
    subject_keywords: tuple[str, ...] | list[str],
) -> FilterResult:
    """按主体关键词过滤备抵科目的反解结果。

    Args:
        codes: 反解出的客户原始码（点号体系），顺序即优先级
        name_by_code: 原始码 → 原始科目名（来自 ``account_mapping`` 或
            ``tb_balance``；缺失的键按「名称缺失」处理 = 保留）
        subject_keywords: 本槽业务主体关键词（来自
            :attr:`SemanticAccountSlot.subject_keywords`）。空 ⇒ 空操作

    Returns:
        :class:`FilterResult`

    Examples:
        拦住错映射进来的长期应收款坏账::

            >>> r = filter_provision_codes(
            ...     ["1231.02", "1231.05"],
            ...     {"1231.02": "坏账准备_应收账款", "1231.05": "坏账准备_长期应收款"},
            ...     ("应收账款",),
            ... )
            >>> r.kept
            ('1231.02',)
            >>> r.dropped[0].code, r.dropped[0].reason
            ('1231.05', '名称不含本循环主体关键词（应收账款）')

        关键词为空 ⇒ 空操作（既有循环零回归）::

            >>> filter_provision_codes(["1231.02", "1231.05"], {}, ()).kept
            ('1231.02', '1231.05')
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for c in codes or ():
        key = str(c or "").strip()
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)

    kws = tuple(str(k).strip() for k in (subject_keywords or ()) if str(k).strip())
    if not kws:
        # 空操作 —— 既有 28 个消费方接入时行为逐字不变
        return FilterResult(kept=tuple(ordered), dropped=(), warnings=(), applied=False)

    norm_kws = tuple(normalize_account_name(k) for k in kws)
    kept: list[str] = []
    dropped: list[DroppedCode] = []
    warnings: list[DroppedCode] = []

    for code in ordered:
        raw_name = name_by_code.get(code)
        if raw_name is None or not str(raw_name).strip():
            # 名称缺失 ⇒ 保留 + 标注，交人工确认（宁可多算也不静默丢真实备抵）
            kept.append(code)
            warnings.append(DroppedCode(code=code, name="", reason=REASON_NAME_MISSING))
            continue
        norm_name = normalize_account_name(raw_name)
        if any(kw and kw in norm_name for kw in norm_kws):
            kept.append(code)
        else:
            dropped.append(
                DroppedCode(
                    code=code,
                    name=str(raw_name),
                    reason="名称不含本循环主体关键词（%s）" % "/".join(kws),
                )
            )

    return FilterResult(
        kept=tuple(kept), dropped=tuple(dropped), warnings=tuple(warnings), applied=True
    )
