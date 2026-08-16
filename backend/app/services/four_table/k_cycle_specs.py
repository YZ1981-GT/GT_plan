"""K 循环（K1~K13）科目定位声明 —— **单一真源**。

各 render 只从本模块取声明，不再各写一份科目码字面量。守卫测试与 render 共读本模块，
故「声明与实现漂移」在结构上不可能发生。

科目映射真源 = ``report_config``（**DB，不是本文件里的任何表格**）::

    tb_balance.account_code  →  account_mapping  →  trial_balance.standard_account_code
                                                          │ report_config.formula
                                                          ▼  （按 applicable_standard）
                                                       报表行

🔴🔴🔴 **判据在 DB，不在本文件。禁止再往本文件写「实证表」。**

本文件此前带过一张自称「DB 只读实证」的表格，它把 listed / soe 两侧报表行号**整体
记错一档**，导致 9 处 row_code 错位（其中 K6/K9 是活的取数错误），且因为它看起来像
实证、后续会话反复采信，错误潜伏了很久。2026-08-09 连库逐条反查后该表已删除。

判据固化在 :mod:`backend.tests.four_table.test_k_cycle_row_code_evidence` —— 它
**连库**按 ``row_name`` 反查 ``report_config`` 四变体并与本文件声明精确比对。要核对
某个 row_code 请跑那个守卫，不要在这里加表格。

**本轮改正的关键事实**（判据仍在 DB，此处只记结论与后果分级）：

- 正确落点**全部是「两准则同号」** —— K 循环没有一个科目在 listed / soe 下用不同
  row_code。此前「两侧必须不同」的假设本身就是错的（还被写成了守卫断言）。
- 后果分三级：``ACTIVE_WRONG``（公式非 NULL + 科目在客户表存在 ⇒ 解析成功 ⇒ 取到
  **别的科目的钱**）> ``SILENT_EMPTY``（科目存在但方向被判成备抵 ⇒ gross 空 ⇒ 显示 0）
  > ``TRACE_ONLY``（公式 NULL 或 ``ROW()`` 派生 ⇒ 退兜底 ⇒ 金额对、``resolved_from``
  谎报）。逐条留痕见各 spec 的 ``row_code_evidence``。

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 1.1~1.12 / 2.1~2.5 / 3.1~3.3 / Property 1~9, 53
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .pl_occurrence import AccountNature
from .report_line_accounts import ReportLineAccountSpec

# ─────────────────────────────────────────────────────────────────────────────
# 无实体科目的循环（宁缺勿造）
# ─────────────────────────────────────────────────────────────────────────────

#: 三表零命中说明文案（render 输出 `tb_source_codes.empty_reason`，前端溯源面板展示）
EMPTY_REASON_NO_ACCOUNT = (
    "三表零命中：account_chart / tb_balance / trial_balance 均无该科目 —— "
    "本科目在实务中是报表行、由多个明细科目按性质归集，四表侧无法自动取数，"
    "请在审定表手工录入（平台铁律：宁缺勿造，不臆造数据）"
)

#: 运行时降级文案：标准科目表里**有**该科目，但**本项目**科目表没用它。
#:
#: 🔴 与 :data:`EMPTY_REASON_NO_ACCOUNT` 是**两层不同的事** ——
#: 前者是「标准科目表里就没这个科目」（``has_account=False``，设计期结论）；
#: 本条是「科目存在但这个项目没用」（运行期结论）。K6 实测只有 1 个 client 项目
#: 有 ``1481``/``2245`` ⇒ 多数项目走本条降级，是高频可见路径。
EMPTY_REASON_NOT_IN_PROJECT = (
    "本项目无此科目：标准科目表有该科目，但本项目的科目表未使用它 —— "
    "四表侧无数据可取，请确认业务上是否确实不存在该项目（区别于「余额为 0」）"
)

#: K4 历史硬编码过、但**在标准科目表中不存在**的码。守卫据此断言源码不得再出现。
#:
#: 🔴 2026-08-09 收缩：``1481``/``2245`` 已从本表移出 —— 实测它们在 ``account_chart``
#: client 侧**确实存在**（各 1 个项目），且 ``report_config`` 的 ``BS-012``/``BS-051``
#: 公式都在。把它们当「不存在的码」是旧记载的错误。
NONEXISTENT_ACCOUNT_CODES: tuple[str, ...] = ("2301", "2605", "2331", "2911")

#: 🔴 语义桥接（`to_semantic_spec` / `semantic_spec_of`）**已撤回**的理由（Property 16）。
#:
#: 撤回依据（2026-08-09 连库实证）：
#: ① 两个函数在 `backend/app/**` 生产代码里**零消费方**（只有测试引用）= 死代码；
#: ② K 循环科目码在项目间**基本一致** —— `account_chart` 实测 `2241`(standard 10 /
#:    client 8)、`2801`(8/5)、`2401`(9/6)、`6601`(10/8)、`6602`(10/8) 等主科目
#:    在所有项目同码同名，语义解析（按科目名在本项目科目表定位）买不到东西；
#: ③ 旧桥接**硬编码 `row_code_soe`** ⇒ 换过去对上市项目即 regression；
#: ④ 旧桥接是**单槽**规格，而语义解析器的「报表公式兜底层」只对单槽成立 —— 一旦将来
#:    加备抵槽（K1 的 `1231-03` / K6 的 `1482`）会把整条报表行金额塞进子项槽。
#:
#: 需要重新发起迁移前，必须先推翻 ② 的对账结果（拿新的 `account_chart` 实证）。
SEMANTIC_BRIDGE_WITHDRAWAL_REASON = (
    "K 循环科目码在项目间基本一致（account_chart 实测主科目全项目同码同名），"
    "语义解析买不到东西；且旧桥接硬编码 row_code_soe + 单槽规格，"
    "接过去对上市项目即 regression。生产零消费方 ⇒ 撤回而非接线。"
)

#: K5 历史误用的码 → 它真正的科目名（守卫的反向自检用）
MISUSED_ACCOUNT_CODES: dict[str, str] = {"2701": "长期应付款"}

#: 后果分级取值（Requirement 1.12 / Property 53 要求每条改正留痕时标注）
SEVERITY_ACTIVE_WRONG = "ACTIVE_WRONG"
SEVERITY_SILENT_EMPTY = "SILENT_EMPTY"
SEVERITY_TRACE_ONLY = "TRACE_ONLY"
SEVERITY_VALUES: tuple[str, ...] = (
    SEVERITY_ACTIVE_WRONG,
    SEVERITY_SILENT_EMPTY,
    SEVERITY_TRACE_ONLY,
)


@dataclass(frozen=True)
class KCycleSpec:
    """单个 K 循环的科目定位声明。

    Attributes:
        wp_code: 循环编码（``K1`` ~ ``K13``）。
        account_name: 科目中文名（展示与守卫按名反查 `report_config` 用）。
        row_code_listed: 上市准则下的报表行编码。
        row_code_soe: 国企准则下的报表行编码。

            🔴 K 循环实测**两侧全部同号** —— 保留两个字段是为了兼容
            :meth:`spec_for` 的既有签名与其它循环的形态，不是因为它们该不同。
        fallback_standard: 兜底**标准码**（报表映射解析失败时用）；无实体科目时为空。
        fallback_provision: 备抵侧兜底**标准码**。

            🔴 与 :attr:`provision_row_code` 是**两条互补路径**，不可互相替代：
            前者用于「备抵码写在原值行公式里」（K1 的 `BS-009` soe_standalone
            含 `− TB('1231-03')`），listed 侧公式不含它 ⇒ 解析不出备抵 ⇒
            **必须**靠本字段兜住，否则上市项目坏账准备取不到数；
            后者用于「备抵自成一行」（K6 的 `IMP-007`）。
        nature: 损益类科目的增加方向；资产负债类为 ``None``（走余额口径）。
        has_account: ``False`` 表示**标准科目表里就没这个科目**，走宁缺勿造分支。
            与「本项目没用这个科目」是两层（后者是运行期降级，见
            :data:`EMPTY_REASON_NOT_IN_PROJECT`）。
        is_liability: 负债 / 权益类置 ``True``（备抵拆分整体跳过）。
        gross_direction: 主体科目方向（``'credit'`` = 负债类的弱形式）。
        extra_standard_codes: 报表公式引用但需单列的附加科目标准码。
        provision_row_code: 备抵科目的**独立报表行**编码。
        provision_name_filter: 备抵侧名称过滤词（反解退化为宽前缀时叠加）。
        trust_report_config: ``False`` = 不让报表公式参与定位（派生行 / 已知错码）。
        row_code_evidence: 改正留痕 —— 原值 / 该原值实际指向的科目 / 后果分级。
        note: 该循环的实证结论（写进 `tb_source_codes` 供溯源，也是守卫判据来源）。
    """

    wp_code: str
    account_name: str
    row_code_listed: str
    row_code_soe: str
    fallback_standard: str = ""
    fallback_provision: tuple[str, ...] = ()
    nature: AccountNature | None = None
    has_account: bool = True
    is_liability: bool = False
    gross_direction: str | None = None
    extra_standard_codes: tuple[str, ...] = ()
    provision_row_code: str | None = None
    provision_name_filter: str | None = None
    trust_report_config: bool = True
    row_code_evidence: str = ""
    note: str = ""

    @property
    def is_pl(self) -> bool:
        """是否损益类（取发生额而非余额）。"""
        return self.nature is not None

    def spec_for(self, applicable_standards) -> ReportLineAccountSpec:
        """按适用准则选报表行，产出共享件所需的 :class:`ReportLineAccountSpec`。

        🔴 本方法只挑**一个**行号（与 L 侧 `pick_row_codes` 返回「尝试顺序」不同）——
        故行号一旦写错，就**没有第二次机会**回落到正确报表行，只能退到
        ``fallback_standard``。这正是 K 循环 9 处错位能长期潜伏的机制：
        「错 row_code + 该码公式为 NULL」会被兜底码兜成「看起来正确」。

        K 循环实测两侧同号，故本方法当前对两个分支返回相同 row_code —— 保留分支是
        为了「将来某科目真的分变体」时不必改调用方。

        无法判定准则时用国企行号（在册项目绝大多数是 soe）。
        """
        stds = [str(s or "") for s in (applicable_standards or [])]
        is_listed = any("listed" in s for s in stds)
        row_code = self.row_code_listed if is_listed else self.row_code_soe
        return ReportLineAccountSpec(
            row_code=row_code,
            fallback_gross=(self.fallback_standard,) if self.fallback_standard else (),
            fallback_provision=self.fallback_provision,
            provision_row_code=self.provision_row_code,
            provision_name_filter=self.provision_name_filter,
            extra_standard_codes=self.extra_standard_codes,
            is_liability=self.is_liability,
            gross_direction=self.gross_direction,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 声明表（唯一真源）
# ─────────────────────────────────────────────────────────────────────────────

K_CYCLE_SPECS: dict[str, KCycleSpec] = {
    # ── K1 其他应收款（本轮由私有 spec 收进真源，Requirement 3.1~3.2）──────────
    "K1": KCycleSpec(
        wp_code="K1",
        account_name="其他应收款",
        row_code_listed="BS-009",
        row_code_soe="BS-009",
        fallback_standard="1221",
        # 🔴 备抵兜底不可省：`BS-009` 只有 soe_standalone 的公式含 `− TB('1231-03')`，
        #    另三个变体（listed 两侧 + soe_consolidated）公式里**没有备抵码** ⇒
        #    那三种项目全靠这个兜底才拿得到坏账准备。改造前私有 spec 就带着它，
        #    收进真源时若丢掉，上市项目的 K1 备抵会静默变空（Task 6 characterization 抓出）。
        fallback_provision=("1231-03",),
        extra_standard_codes=("1131", "1132"),
        # 🔴 逐字保持「其他应收款」（不是「其他应收」）—— 该词用于反解退化为宽前缀
        #    `1231` 时过滤 `account_name`，写窄成「其他应收」会把
        #    `1231.02 坏账准备_应收账款`… 之外的同前缀名一并放进来。
        #    改造前私有 spec 的值即「其他应收款」，characterization 钉死。
        provision_name_filter="其他应收款",
        row_code_evidence="【新纳入·非改正】此前 render 各写私有 spec、不在声明表内，"
        "无原值可留痕（故不含「原值 / 实际指向 / 后果分级」三段）；"
        "BS-009 四变体一致指「其他应收款」，soe_standalone 公式含 "
        "− TB('1231-03') + TB('1131')",
        note="备抵 1231-03 坏账准备-其他应收款；反解退化为宽前缀 1231 时须叠名称过滤"
        "（防把应收账款坏账 1231-02 算进来）；1131 应收股利 / 1132 应收利息 单列不并入 gross",
    ),
    # ── K2 其他流动资产 ──────────────────────────────────────────────────────
    "K2": KCycleSpec(
        wp_code="K2",
        account_name="其他流动资产",
        row_code_listed="BS-014",
        row_code_soe="BS-014",
        fallback_standard="1901",
        # 🔴 改造前私有 spec 带 `extra_standard_codes=(K2_DIVIDEND_STANDARD,)` = `('1131',)`。
        #    K2 的「与经审计的财务报表核对」区要单列应收股利，收进真源时不可丢
        #    （Task 6 characterization 抓出）。1131 同时被 K1 单列 —— 两个循环都只是
        #    「核对区展示」不并入各自 gross，不构成双算。
        extra_standard_codes=("1131",),
        row_code_evidence="【新纳入·非改正】BS-014 四变体公式全 NULL ⇒ 恒退兜底 1901，"
        "resolved_from 恒 fallback（属正常兜底、非缺陷，故本条不标后果分级）",
        note="🔴 历史硬编码 1231（坏账准备）是错误科目族；1901 待处理财产损溢是兜底口径，"
        "与前端 k2AccountScope.ts 交叉锁死",
    ),
    # ── K3 其他应付款 ────────────────────────────────────────────────────────
    "K3": KCycleSpec(
        wp_code="K3",
        account_name="其他应付款",
        # 原值 BS-053 / BS-075：BS-053 实为**其他流动负债**（K4 的行，与 K4 跨循环撞码）；
        # BS-075 在 soe 侧名对但 formula NULL、在 listed 侧是**股本**。
        row_code_listed="BS-050",
        row_code_soe="BS-050",
        fallback_standard="2241",
        extra_standard_codes=("2231",),
        is_liability=True,
        gross_direction="credit",
        row_code_evidence="原值 listed=BS-053（实为其他流动负债 / K4 的行，跨循环撞码）"
        "+ soe=BS-075（soe 侧名对但 formula NULL；listed 侧是股本）；"
        f"后果 {SEVERITY_TRACE_ONLY}（两个原值公式均 NULL ⇒ 退兜底 2241，"
        "金额对但漏 2231 应付利息、溯源失真）",
        note="BS-050 在 standalone 变体下是 TB('2241')+TB('2231')（财会[2018]15 号："
        "应付利息并入其他应付款列报）⇒ 2231 走 extra_standard_codes 单列，不并入 gross；"
        "2241/2231 在 account_chart 均为 credit ⇒ 必须声明负债方向",
    ),
    # ── K4 其他流动负债（唯一成立的宁缺勿造）────────────────────────────────
    "K4": KCycleSpec(
        wp_code="K4",
        account_name="其他流动负债",
        row_code_listed="BS-053",
        row_code_soe="BS-053",
        fallback_standard="",
        has_account=False,
        is_liability=True,
        gross_direction="credit",
        row_code_evidence="原值 listed=BS-058 / soe=BS-081；BS-081 实为**实收资本（或股本）**"
        f"`TB('4001','期末余额')` ⇒ 后果 {SEVERITY_SILENT_EMPTY} —— 4001 在 client 侧"
        "8 项目为 credit，而 K4 原未声明方向 ⇒ 原值被 split_gross_provision 判成备抵、"
        "gross 变空 ⇒ 表现为「恒空」而非错数，掩盖了错位本身",
        note="✅ 宁缺勿造成立（唯一一个）：BS-053 四变体公式全 NULL，"
        "且 account_chart 按名（其他流动负债）按码（2301）**两侧都零命中** ⇒ "
        "本科目在实务中是报表行、由多个明细按性质归集，四表侧无法自动取数",
    ),
    # ── K5 预计负债 ──────────────────────────────────────────────────────────
    "K5": KCycleSpec(
        wp_code="K5",
        account_name="预计负债",
        row_code_listed="BS-065",
        row_code_soe="BS-065",
        fallback_standard="2801",
        is_liability=True,
        gross_direction="credit",
        row_code_evidence="soe 原值 BS-094（row_name 实为「预计负债」名对，但 formula NULL）⇒ "
        f"后果 {SEVERITY_TRACE_ONLY}（退兜底 2801，金额对、溯源失真）；"
        "listed 侧曾误写 BS-068（其他非流动负债 / L7 的行，TB('2911') 且 2911 全库零命中）"
        "已于 2026-08-05 改正为 BS-065",
        note="🔴 历史硬编码 2701 = 长期应付款（L5 科目）；真值 2801 预计负债"
        "（account_chart standard 8 / client 5 项目，均为 credit）",
    ),
    # ── K6 持有待售资产和负债（宁缺勿造**不成立**，本轮改 has_account=True）──
    "K6": KCycleSpec(
        wp_code="K6",
        account_name="持有待售资产",
        row_code_listed="BS-012",
        row_code_soe="BS-012",
        fallback_standard="1481",
        provision_row_code="IMP-007",
        has_account=True,
        row_code_evidence="原值 listed=BS-015（**流动资产合计**，ROW() 派生行）"
        f"⇒ {SEVERITY_TRACE_ONLY}；soe=BS-024（**长期股权投资** TB('1511')）"
        f"⇒ 🔴 {SEVERITY_ACTIVE_WRONG} —— 1511 在 8 个 client 项目存在且 direction=debit"
        "（不被备抵拆分挡住）⇒ 持有待售资产审定表取到长期股权投资余额",
        note="🔴 宁缺勿造**不成立**（推翻旧记载）：1481 持有待售资产 / 1482 持有待售资产"
        "减值准备 / 2245 持有待售负债 在 account_chart **client 侧确实存在**（各 1 个项目），"
        "且 report_config 的 BS-012 / BS-051 / IMP-007 公式都在。"
        "多数项目仍会走 EMPTY_REASON_NOT_IN_PROJECT 运行期降级（≠ 余额为 0）",
    ),
    # ── K7 递延收益 ──────────────────────────────────────────────────────────
    "K7": KCycleSpec(
        wp_code="K7",
        account_name="递延收益",
        row_code_listed="BS-066",
        row_code_soe="BS-066",
        fallback_standard="2401",
        is_liability=True,
        gross_direction="credit",
        row_code_evidence="原值 listed=BS-069（**非流动负债合计**，ROW() 派生行）"
        f"⇒ {SEVERITY_TRACE_ONLY}；soe=BS-095（名对但 formula NULL）⇒ 同级",
        note="BS-066 四变体一致 TB('2401','期末余额')；2401 在 account_chart 为 credit",
    ),
    # ── K8~K13 损益类 ────────────────────────────────────────────────────────
    "K8": KCycleSpec(
        wp_code="K8",
        account_name="销售费用",
        row_code_listed="IS-004",
        row_code_soe="IS-004",
        fallback_standard="6601",
        nature=AccountNature.EXPENSE,
        row_code_evidence="soe 原值 IS-022（**三、利润总额**，ROW('IS-019')+ROW('IS-020')"
        f"−ROW('IS-021') 派生行）⇒ {SEVERITY_TRACE_ONLY} —— extract_signed_codes 抽不出 "
        "TB() ⇒ codes 空 ⇒ 退兜底 6601，金额对但 resolved_from 谎报 report_config",
        note="损益类借方；原实现 debit - credit 恒 0（活体 6601 逐行 debit==credit），"
        "改 trial_balance 权威（实证 505,080,400.27）",
    ),
    "K9": KCycleSpec(
        wp_code="K9",
        account_name="管理费用",
        row_code_listed="IS-005",
        row_code_soe="IS-005",
        fallback_standard="6602",
        nature=AccountNature.EXPENSE,
        row_code_evidence="soe 原值 IS-023 = **减：所得税费用** TB('6801','本期发生额')"
        f"⇒ 🔴 {SEVERITY_ACTIVE_WRONG} —— 6801 在 standard 9 / client 7 项目存在且"
        " direction=debit（不被备抵拆分挡住）⇒ 管理费用审定表取到所得税费用金额",
        note="损益类借方；同 K8（实证 trial_balance 6602 = 72,957,201.11）",
    ),
    "K10": KCycleSpec(
        wp_code="K10",
        account_name="其他收益",
        row_code_listed="IS-010",
        row_code_soe="IS-010",
        fallback_standard="6117",
        nature=AccountNature.INCOME,
        row_code_evidence="soe 原值 IS-030 = **五、其他综合收益的税后净额**（formula NULL）"
        f"⇒ {SEVERITY_TRACE_ONLY}（退兜底 6117，金额对、溯源失真）",
        note="损益类贷方；IS-010 行名是「加：其他收益」（按名反查须容忍「加：」前缀）；"
        "trial_balance 符号在项目间不统一（-146,477.91 与 +15,712.56 并存）"
        "→ 按报表口径取绝对值并留 raw_sign",
    ),
    "K11": KCycleSpec(
        wp_code="K11",
        account_name="资产减值损失",
        row_code_listed="IS-017",
        row_code_soe="IS-017",
        fallback_standard="6701",
        nature=AccountNature.EXPENSE,
        row_code_evidence="soe 原值 IS-038 是**一码两义**（listed 侧「5. 其他」/ soe 侧"
        "「资产减值损失（损失以“－”号填列）」，两侧 formula 均 NULL）"
        f"⇒ {SEVERITY_TRACE_ONLY}",
        note="IS-017 四变体一致 TB('6701','本期发生额')（**推翻旧记载的「formula 为 None」**）；"
        "account_chart 实证 6701=资产减值损失、6702=信用减值损失（后者属 G14，不是 K11）",
    ),
    "K12": KCycleSpec(
        wp_code="K12",
        account_name="营业外收入",
        row_code_listed="IS-020",
        row_code_soe="IS-020",
        fallback_standard="6301",
        nature=AccountNature.INCOME,
        row_code_evidence="soe 原值 IS-041（listed 侧「（一）基本每股收益（元/股）」/ "
        f"soe 侧「加： 营业外收入」，两侧 formula 均 NULL）⇒ {SEVERITY_TRACE_ONLY}",
        note="损益类贷方；IS-020 行名是「加：营业外收入」；同 K10 的符号处理",
    ),
    "K13": KCycleSpec(
        wp_code="K13",
        account_name="营业外支出",
        row_code_listed="IS-021",
        row_code_soe="IS-021",
        fallback_standard="6711",
        nature=AccountNature.EXPENSE,
        row_code_evidence="soe 原值 IS-043（listed 侧「4. 其他债权投资信用减值准备」/ "
        f"soe 侧「减： 营业外支出」，两侧 formula 均 NULL）⇒ {SEVERITY_TRACE_ONLY}",
        note="损益类借方；IS-021 行名是「减：营业外支出」；同 K8",
    ),
}

#: K6 负债侧报表行（K6 一个循环管资产与负债两侧，资产侧行号在 `K_CYCLE_SPECS`）
#:
#: 🔴 两准则同号（实测 BS-051 四变体一致 `TB('2245','期末余额')`）。
#: 原值 BS-056（listed 侧名对但 formula NULL / soe 侧是**△向中央银行借款**）
#: 与 BS-079（listed 侧是**资本公积**）均为错位。
K6_LIABILITY_ROW_CODE = "BS-051"
K6_LIABILITY_ROW_CODE_LISTED = K6_LIABILITY_ROW_CODE
K6_LIABILITY_ROW_CODE_SOE = K6_LIABILITY_ROW_CODE

#: K6 备抵侧报表行（持有待售资产减值准备，仅 soe_standalone 有公式 `TB('1482')`）
K6_PROVISION_ROW_CODE = "IMP-007"

#: K6 资产侧 / 负债侧 / 备抵侧标准码（方向不同，故分列）
K6_ASSET_STANDARD_CODE = "1481"
K6_PROVISION_STANDARD_CODE = "1482"
K6_LIABILITY_STANDARD_CODE = "2245"

#: K0 豁免理由（守卫要求豁免必须带理由，防豁免退化成盲区）
#:
#: 🔴 必须定义在 :data:`CYCLES_EXEMPT_FROM_ACCOUNT_SPEC` **之前** —— 模块级字典的值
#: 在 import 期就求值，顺序反了会以 ``NameError`` 让整个模块无法 import，且该错误会
#: 以「collection error」形态打红全部消费方测试（本轮踩过一次）。
EXEMPT_REASON_K0 = (
    "K0 是管理循环函证底稿（11 个 sheet 全为函证程序 / 结果汇总 / 差异调节 / "
    "替代程序 / 舞弊风险评价），不承载科目余额取数，且源模板无披露 sheet ⇒ "
    "不适用报表行定位；其函证对象科目由 K1（其他应收款）与 K3（其他应付款）声明"
)

#: K0 是函证循环（无科目余额口径）—— 显式豁免于科目定位声明（Requirement 3.1）
CYCLES_EXEMPT_FROM_ACCOUNT_SPEC: dict[str, str] = {
    "K0": EXEMPT_REASON_K0,
}


def liability_spec_for(applicable_standards) -> ReportLineAccountSpec:
    """K6 **负债侧**（持有待售负债）的科目定位规格。

    K6 一个循环管资产与负债两侧、方向相反 —— 资产侧 `1481`/`1482` 是 ``debit``、
    负债侧 `2245` 是 ``credit`` ⇒ 必须分两个规格，负债侧声明负债方向，否则
    :func:`split_gross_provision` 会把 `2245` 判成备抵、``gross`` 变空。

    实证（`report_config` 四变体一致）::

        BS-051 持有待售负债 = TB('2245','期末余额')

    ⚠️ 旧实现用 ``BS-056``（listed 侧确为「持有待售负债」但 **formula 为 NULL**，
    soe 侧则是「△向中央银行借款」）与 ``BS-079``（listed 侧是**资本公积**），
    两者都不该作为取数行。

    Args:
        applicable_standards: 适用准则列表（当前两侧同号，保留形参供将来分变体）。
    """
    _ = applicable_standards  # 两准则同号；保留形参以免将来分变体时改调用方
    return ReportLineAccountSpec(
        row_code=K6_LIABILITY_ROW_CODE,
        fallback_gross=(K6_LIABILITY_STANDARD_CODE,),
        fallback_provision=(),
        is_liability=True,
        gross_direction="credit",
    )


def get_k_cycle_spec(wp_code: str) -> KCycleSpec | None:
    """按 wp_code 取声明（大小写不敏感）。未登记返 ``None``。"""
    return K_CYCLE_SPECS.get(str(wp_code or "").strip().upper())


def pl_cycle_codes() -> list[str]:
    """损益类循环的 wp_code 列表（K8~K13）。"""
    return [c for c, s in K_CYCLE_SPECS.items() if s.is_pl]


def balance_cycle_codes() -> list[str]:
    """资产负债类循环的 wp_code 列表（K1~K7）。"""
    return [c for c, s in K_CYCLE_SPECS.items() if not s.is_pl]


def no_account_cycle_codes() -> list[str]:
    """标准科目表零命中、走宁缺勿造的循环（实测只有 K4）。"""
    return [c for c, s in K_CYCLE_SPECS.items() if not s.has_account]


def credit_side_cycle_codes() -> list[str]:
    """已声明负债 / 权益方向的循环（K3/K4/K5/K7）。"""
    return [
        c
        for c, s in K_CYCLE_SPECS.items()
        if s.is_liability or s.gross_direction == "credit"
    ]


def severity_of(wp_code: str) -> str | None:
    """从 ``row_code_evidence`` 里抽出后果分级取值（守卫与验收脚本共用）。

    留痕文本里必须恰好出现一个分级取值；抽不出返 ``None``（守卫会打红）。
    """
    spec = get_k_cycle_spec(wp_code)
    if spec is None:
        return None
    hits = [v for v in SEVERITY_VALUES if v in spec.row_code_evidence]
    if not hits:
        return None
    # 🔴 一条留痕可含多个分级（K6：listed 侧 TRACE_ONLY + soe 侧 ACTIVE_WRONG）——
    #    分级语义是「该循环最坏会怎样」，故取**最严**的一档而非首个命中。
    #    SEVERITY_VALUES 已按严重度降序声明，用它的下标做排序键。
    return min(hits, key=SEVERITY_VALUES.index)


__all__ = [
    "liability_spec_for",
    "SEMANTIC_BRIDGE_WITHDRAWAL_REASON",
    "CYCLES_EXEMPT_FROM_ACCOUNT_SPEC",
    "EMPTY_REASON_NOT_IN_PROJECT",
    "EMPTY_REASON_NO_ACCOUNT",
    "EXEMPT_REASON_K0",
    "K6_ASSET_STANDARD_CODE",
    "K6_LIABILITY_ROW_CODE",
    "K6_LIABILITY_ROW_CODE_LISTED",
    "K6_LIABILITY_ROW_CODE_SOE",
    "K6_LIABILITY_STANDARD_CODE",
    "K6_PROVISION_ROW_CODE",
    "K6_PROVISION_STANDARD_CODE",
    "K_CYCLE_SPECS",
    "MISUSED_ACCOUNT_CODES",
    "NONEXISTENT_ACCOUNT_CODES",
    "SEVERITY_ACTIVE_WRONG",
    "SEVERITY_SILENT_EMPTY",
    "SEVERITY_TRACE_ONLY",
    "SEVERITY_VALUES",
    "KCycleSpec",
    "balance_cycle_codes",
    "credit_side_cycle_codes",
    "get_k_cycle_spec",
    "no_account_cycle_codes",
    "pl_cycle_codes",
    "severity_of",
]
