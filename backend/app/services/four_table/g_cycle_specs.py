"""G 循环（投资与金融工具）语义科目定位规格 —— **跨 G1~G14 单一真源**。

一处声明、各 render 策略引用，杜绝「main 与 ecl / sppi / service 子策略科目码分叉」
（实证分叉：G4 main 用 ``1504`` 而 ecl/sppi 写 ``1501``；G6 main 用 ``1505``
而 service 写 ``1503``）。

**为什么按科目名而不按标准码声明**

`report_config`（原本被当成映射真源）在 G 循环有 **4 处错码**，`account_chart` +
`trial_balance.account_name` 双向实证::

    BS-022 其他债权投资      = TB('1505')   ← 1505 实为「债权投资减值准备」，应为 1506
    BS-025 其他权益工具投资  = TB('1506')   ← 1506 实为「其他债权投资」，  应为 1507
    BS-026 其他非流动金融资产 = TB('1507')  ← 1507 实为「其他权益工具投资」，应为 1519
    IS-016 信用减值损失      = TB('6701')   ← 6701 实为「资产减值损失」，  应为 6702
    IS-017 资产减值损失      = TB('6702')   ← 与 IS-016 **整整互换**

铁证：同库 ``CFSS-003 加：资产减值损失 = TB('6701')`` 与
``CFSS-004 信用减值损失 = TB('6702')`` **是对的** → 现金流量表补充资料与利润表自相矛盾。
活体差额：6701 合计 3,876,759.84 / 6702 合计 126,151,230.15（G14 与 K11 的钱互换 1.22 亿）。

且**标准码本身在项目间并不一致**（详见 `semantic_account_resolver` 模块 docstring）：
`1504~1507` 只在 6 个项目的标准科目表里、`1519` 只在 4 个、4 个项目完全没有这一族；
客户科目表里**压根没有** `1504~1507`/`1519`，唯一有投资类科目的项目用的是旧准则
`1501 持有至到期投资` / `1503 可供出售金融资产`。

→ 故科目一律**按名称**在该项目自己的科目表里定位，`report_config` 降级为提示 + 冲突检测。

**实证不存在的科目（返空是正确行为，不是缺陷）**

- ``1102 衍生金融资产``：`report_config` 的 ``BS-004`` 引用它，但**任何项目的科目表里都没有**
  （`2102` 是「短期应付债券」，不是衍生金融负债）→ G1/G10 的衍生品槽解析为空。
  写死 `1102` 只会静默产出 0，掩盖「本项目无衍生金融工具」这一事实。
- ``6103 净敞口套期收益``：仅 4 个项目的**标准**科目表有，无客户科目 → G12 走标准表定位。

**旧准则拆分不可自动化**

客户仍在用 ``1503 可供出售金融资产`` 时，新准则下按业务模式与合同现金流量特征（SPPI）
拆到「交易性金融资产 / 其他债权投资 / 其他权益工具投资」三处 —— 这是**会计判断**
（正是 G4-5/G4-6、G6-7/G6-8 底稿在做的事）。故把它们放进各相关循环的
``legacy_standard_names``：命中时只进 ``unmapped_candidates`` 提示人工映射，**绝不自动归槽**。

spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
      Requirements 1, 2 / Property 4, 5
"""
from __future__ import annotations

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

# ─────────────────────────── 通用否决词 ───────────────────────────

#: 一切「原值」槽的通用否决词 —— 备抵 / 累计类科目名普遍**包含**原值科目名
#: （`债权投资减值准备` 含 `债权投资`、`长期股权投资减值准备` 含 `长期股权投资`）。
_PROVISION_WORDS = (
    "减值准备",
    "坏账准备",
    "跌价准备",
    "累计折旧",
    "累计摊销",
    "减值损失",
)

#: 损益类槽的否决词 —— 防把资产侧同名科目吸进损益槽
_ASSET_WORDS = ("准备", "累计")

#: 旧准则金融资产科目（新准则下需按 SPPI 人工拆分，不自动归槽）
_LEGACY_FINANCIAL = ("持有至到期投资", "可供出售金融资产")


def _gross(
    key: str,
    names: tuple[str, ...],
    fallback: tuple[str, ...],
    label: str,
    extra_excludes: tuple[str, ...] = (),
) -> SemanticAccountSlot:
    """原值槽的构造助手（自动带上通用备抵否决词）。"""
    return SemanticAccountSlot(
        key=key,
        names=names,
        exclude_names=_PROVISION_WORDS + extra_excludes,
        fallback_standard_codes=fallback,
        label=label,
    )


def _provision(
    key: str,
    names: tuple[str, ...],
    fallback: tuple[str, ...],
    label: str,
    extra_excludes: tuple[str, ...] = (),
) -> SemanticAccountSlot:
    """备抵槽的构造助手。

    🔴 `is_provision` **显式声明**，不由 `direction` 推断 —— 实证 `account_chart`
    里备抵科目的 `direction` 也可能是 ``debit``（H3 的 1525/1526/1527 全是 debit）。
    """
    return SemanticAccountSlot(
        key=key,
        names=names,
        exclude_names=("减值损失", "信用减值损失", "资产减值损失") + extra_excludes,
        fallback_standard_codes=fallback,
        label=label,
        is_provision=True,
    )


def _pl(
    key: str,
    names: tuple[str, ...],
    fallback: tuple[str, ...],
    label: str,
    extra_excludes: tuple[str, ...] = (),
) -> SemanticAccountSlot:
    """损益类槽的构造助手。"""
    return SemanticAccountSlot(
        key=key,
        names=names,
        exclude_names=_ASSET_WORDS + extra_excludes,
        fallback_standard_codes=fallback,
        label=label,
    )


# ─────────────────────────── G1~G14 规格 ───────────────────────────

#: G1 交易性金融资产（底稿同管交易性金融资产与衍生金融资产两个科目）
#: 🔴 `1102 衍生金融资产` 实证任何项目科目表都没有 → 该槽解析为空是正确行为。
G1_SPEC = SemanticAccountSpec(
    row_code="BS-003",
    slots=(
        _gross("gross", ("交易性金融资产",), ("1101",), "交易性金融资产"),
        # 🔴 **不给兜底码**：`1102` 实证任何项目科目表都没有，给了兜底只会在
        #    「科目表不可用」的降级路径里产出一个查不到任何数据的假前缀。
        #    项目真有该科目时，客户 / 标准科目表按名称即可命中（与 G10.derivative 一致）。
        _gross("derivative", ("衍生金融资产",), (), "衍生金融资产"),
    ),
    legacy_standard_names=_LEGACY_FINANCIAL,
)

#: G2 应收利息
#: 🔴 `report_config` **无独立报表行**：实证 `BS-015` 是「流动资产合计」（`ROW()` 派生行），
#:    `BS-009 其他应收款` 的公式含 `1131` 应收股利但**不含** `1132` 应收利息
#:    → `row_code=None`，不去报表配置里瞎认领一行（否则溯源面板会把「流动资产合计」
#:    的公式展示给审计师）。
G2_SPEC = SemanticAccountSpec(
    row_code=None,
    slots=(_gross("gross", ("应收利息",), ("1132",), "应收利息"),),
)

#: G3 应收股利（soe 侧 `BS-016 其中：应收股利` formula 为 None；listed 侧该行是
#: 「一年内到期的非流动资产」→ 同样不认领，按名称定位）
G3_SPEC = SemanticAccountSpec(
    row_code=None,
    slots=(_gross("gross", ("应收股利",), ("1131",), "应收股利"),),
)

#: G4 债权投资（原值 1504 + 备抵 1505）
G4_SPEC = SemanticAccountSpec(
    row_code="BS-021",
    slots=(
        _gross("gross", ("债权投资",), ("1504",), "债权投资", ("其他债权投资",)),
        _provision("provision", ("债权投资减值准备",), ("1505",), "债权投资减值准备",
                   ("其他债权投资",)),
    ),
    legacy_standard_names=_LEGACY_FINANCIAL,
)

#: G5 长期应收款（无备抵独立科目，坏账在 1231 族由 D/K 循环管）
G5_SPEC = SemanticAccountSpec(
    row_code="BS-023",
    slots=(_gross("gross", ("长期应收款",), ("1531",), "长期应收款"),),
)

#: G6 其他债权投资 —— **真值 1506**（`report_config` 的 `BS-022` 写 1505 = 债权投资减值准备）
#: CAS22 下 FVOCI-债务工具的减值在 OCI 确认、不冲减账面价值，故无备抵槽。
G6_SPEC = SemanticAccountSpec(
    row_code="BS-022",
    slots=(_gross("gross", ("其他债权投资",), ("1506",), "其他债权投资"),),
    legacy_standard_names=_LEGACY_FINANCIAL,
)

#: G7 长期股权投资（原值 1511 + 备抵 1512，备抵自成报表行 `IMP-009`）
G7_SPEC = SemanticAccountSpec(
    row_code="BS-024",
    slots=(
        _gross("gross", ("长期股权投资",), ("1511",), "长期股权投资"),
        _provision("provision", ("长期股权投资减值准备",), ("1512",), "长期股权投资减值准备"),
    ),
)

#: G8 其他权益工具投资 —— **真值 1507**（`BS-025` 写 1506 = 其他债权投资）
G8_SPEC = SemanticAccountSpec(
    row_code="BS-025",
    slots=(_gross("gross", ("其他权益工具投资",), ("1507",), "其他权益工具投资"),),
    legacy_standard_names=_LEGACY_FINANCIAL,
)

#: G9 其他非流动金融资产 —— **真值 1519**（`BS-026` 写 1507 = 其他权益工具投资）
#: 🔴 `1519` 只在 4 个项目的标准科目表里 → 另 6 个项目解析为空（正确行为）。
G9_SPEC = SemanticAccountSpec(
    row_code="BS-026",
    slots=(
        _gross("gross", ("其他非流动金融资产",), ("1519",), "其他非流动金融资产"),
    ),
    legacy_standard_names=_LEGACY_FINANCIAL,
)

#: G10 交易性金融负债（+ 衍生金融负债；后者实证无科目 → 返空）
G10_SPEC = SemanticAccountSpec(
    row_code="BS-042",
    slots=(
        _gross("gross", ("交易性金融负债",), ("2101",), "交易性金融负债"),
        _gross("derivative", ("衍生金融负债",), (), "衍生金融负债"),
    ),
)

#: G11 投资收益（损益类，口径 = 本期发生额）
G11_SPEC = SemanticAccountSpec(
    row_code="IS-011",
    slots=(_pl("gross", ("投资收益",), ("6111",), "投资收益"),),
)

#: G12 净敞口套期收益（`IS-014` 公式为 None → 走名称 / 兜底；仅 4 个项目标准表有该科目）
#: 🔴 公式预设曾错写 `6115`（= 资产处置损益，H10 的科目）。
G12_SPEC = SemanticAccountSpec(
    row_code="IS-014",
    slots=(_pl("gross", ("净敞口套期收益",), ("6103",), "净敞口套期收益"),),
)

#: G13 公允价值变动收益（科目名是「公允价值变动损益」，报表行名是「收益」→ 两个名都要认）
G13_SPEC = SemanticAccountSpec(
    row_code="IS-015",
    slots=(
        _pl(
            "gross",
            ("公允价值变动损益", "公允价值变动收益"),
            ("6101",),
            "公允价值变动损益",
        ),
    ),
)

#: G14 信用减值损失 —— **真值 6702**（`IS-016` 写 6701 = 资产减值损失，与 `IS-017` 互换）
#: 🔴 否决词必须含「资产减值损失」，否则包含匹配会命中 6701。
G14_SPEC = SemanticAccountSpec(
    row_code="IS-016",
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("信用减值损失",),
            exclude_names=("资产减值损失", "准备", "累计"),
            fallback_standard_codes=("6702",),
            label="信用减值损失",
        ),
    ),
)


#: wp_code → 语义规格（供 render 策略与守卫按循环取用）
G_CYCLE_SPECS: dict[str, SemanticAccountSpec] = {
    "G1": G1_SPEC,
    "G2": G2_SPEC,
    "G3": G3_SPEC,
    "G4": G4_SPEC,
    "G5": G5_SPEC,
    "G6": G6_SPEC,
    "G7": G7_SPEC,
    "G8": G8_SPEC,
    "G9": G9_SPEC,
    "G10": G10_SPEC,
    "G11": G11_SPEC,
    "G12": G12_SPEC,
    "G13": G13_SPEC,
    "G14": G14_SPEC,
}

#: 损益类 G 循环（取数口径必须是**本期发生额**，不是期初 / 期末余额）
#: 实证 `tb_balance.closing_balance` 在 6101/6111/6115/6701/6702 全项目全为 0
#: —— 含年末结转损益的全年账上，损益类余额结转后归零。
G_PL_CYCLES = frozenset({"G11", "G12", "G13", "G14"})

#: 损益类科目的**正方向**（本期发生额取哪一侧）。
#:
#: 🔴 **不能用 `debit - credit`**：含年末结转损益的全年账上必有「结转本年利润」分录，
#: 使同一科目的借贷两侧金额**恒相等** → 差额结构性为 0（N4/N5 实证 9 个项目全中，
#: 活体 `6801.01` dr == cr == 24,891,157.62）。故按声明的单侧取数。
#:
#: - ``credit``：收益 / 利得类（贷方登记收益）—— 投资收益、净敞口套期收益、
#:   公允价值变动收益。既有 `useG11Adjudication.loadTrialBalanceFromApi` 用
#:   `credit - debit` 亦印证贷方为正方向。
#: - ``debit``：损失类（借方登记损失）—— 信用减值损失。
G_PL_POSITIVE_SIDE: dict[str, str] = {
    "G11": "credit",
    "G12": "credit",
    "G13": "credit",
    "G14": "debit",
}


def spec_of(wp_code: str) -> SemanticAccountSpec | None:
    """按 wp_code 取语义规格（大小写不敏感；未登记返 ``None``）。"""
    return G_CYCLE_SPECS.get(str(wp_code or "").strip().upper())


__all__ = [
    "G1_SPEC",
    "G10_SPEC",
    "G11_SPEC",
    "G12_SPEC",
    "G13_SPEC",
    "G14_SPEC",
    "G2_SPEC",
    "G3_SPEC",
    "G4_SPEC",
    "G5_SPEC",
    "G6_SPEC",
    "G7_SPEC",
    "G8_SPEC",
    "G9_SPEC",
    "G_CYCLE_SPECS",
    "G_PL_CYCLES",
    "G_PL_POSITIVE_SIDE",
    "spec_of",
]
