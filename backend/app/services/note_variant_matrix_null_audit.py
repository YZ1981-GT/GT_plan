"""`variant_matrix` null 条目的三态裁决真源（Requirement 7.1~7.4）。

spec: soe-listed-note-conversion-correctness / Task 12·13

本模块**只登记裁决结论**，不改数据、不含 IO。补记动作本身要等
spec ``parent-company-note-chapter-and-sourcing``（下称 A）的 Task 10 收口
—— A 也要改 ``note_template_variant_matrix.json``（增母公司维度），且其
Requirement 10.4 明确「其余 100 个非母公司科目取值不变」，与本 spec 要改的
35 条 null 正面撞车。两侧同时改同一 JSON 必互相回退。

------------------------------------------------------------------------------
三态定义
------------------------------------------------------------------------------

``FALSE_NULL``
    目标模板**确有**同语义章节，只是章节归属与源侧不同（多在「三、重要会计政策」
    「十四、日后事项」「十七、补充资料」章）⇒ 记 null 是错的，须补记落点。

``CROSS_GRAIN``
    目标模板有落点但**粒度不同**（源侧一科目 ↔ 目标侧合并成一章，或反之）
    ⇒ 不能简单补一个章节号，需要人工确认对应关系后再补。

``TRUE_NULL``
    目标模板确实无该科目披露落点（两版不对称是源模板事实）⇒ null 正确，
    但须附理由（Requirement 7.4）。

------------------------------------------------------------------------------
🔴 首轮「精确匹配」判定有 8 条误判（2026-08-06 关键词复核推翻）
------------------------------------------------------------------------------

按 ``section_title`` 精确匹配会把「同语义但换了叫法」判成 TRUE_NULL。实测
listed 侧 6 条 + soe 侧 2 条被误判：

- ``实收资本``（soe 用语）在 listed 模板叫 ``股本``（`五、53`）；反向
  ``股本``（listed 用语）在 soe 模板叫 ``实收资本``（`八、58`）—— 同一科目
  两版**用语互换**，精确匹配双向都落空。
- ``外币折算`` → listed ``五、73 外币货币性项目``
- ``分部信息`` → listed ``十四、分部报告``
- ``合并现金流量表相关事项`` → listed ``五、71 现金流量表补充资料``
- ``其他综合收益``（soe）→ ``八、79 归属于母公司所有者的其他综合收益``
- 三个「一年内到期的 X」→ listed 合并为 ``五、43 一年内到期的非流动负债``

⇒ **判 null 真假必须做关键词复核，不能只做 section_title 精确匹配**。这与
需求 5 的「章节匹配禁用相似度」不冲突：那条约束的是**转换时的自动配对**
（会误配「合并 ↔ 母公司」章），这里是**人工复核的辅助手段**，结论逐条冻结。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

__all__ = [
    "NullVerdict",
    "NullAuditEntry",
    "LISTED_NULL_AUDIT",
    "SOE_NULL_AUDIT",
    "SPEC_NAMED_FALSE_NULLS",
    "BLOCKED_BY_SPEC",
    "verdict_of",
]

NullVerdict = Literal["FALSE_NULL", "CROSS_GRAIN", "TRUE_NULL"]

#: 补记动作的阻塞方 —— 见模块 docstring。
BLOCKED_BY_SPEC: Final = "parent-company-note-chapter-and-sourcing"


@dataclass(frozen=True)
class NullAuditEntry:
    """一条 null 的裁决结论。

    Attributes:
        account_key: ``variant_matrix.accounts[].account_key``
        section_title: 该科目在**源侧**模板的章节标题
        verdict: 三态裁决
        target_section: FALSE_NULL 时的补记落点（``section_number``）；其余为 ``None``
        reason: 判定理由（TRUE_NULL 必填，Requirement 7.4）
    """

    account_key: str
    section_title: str
    verdict: NullVerdict
    target_section: str | None
    reason: str


def _e(
    key: str, title: str, verdict: NullVerdict, target: str | None, reason: str
) -> NullAuditEntry:
    return NullAuditEntry(key, title, verdict, target, reason)


# ---------------------------------------------------------------------------
# listed_standalone 为 null 的 25 条
# ---------------------------------------------------------------------------

LISTED_NULL_AUDIT: Final[tuple[NullAuditEntry, ...]] = (
    # ── FALSE_NULL：listed 模板确有落点，只是归在别的章 ──────────────────
    _e(
        "zi_chan_jian_zhi_sun_shi",
        "资产减值损失",
        "FALSE_NULL",
        "三、资产减值损失（损",
        "listed 模板有该章（1 表），章节号是 md 重建的 10 字截断值",
    ),
    _e(
        "zi_chan_chu_zhi_shou_yi",
        "资产处置收益",
        "FALSE_NULL",
        "三、资产处置收益（损",
        "listed 模板有该章（2 表），章节号是 md 重建的 10 字截断值",
    ),
    _e(
        "ying_ye_wai_shou_ru",
        "营业外收入",
        "FALSE_NULL",
        "三、营业外收入（注：",
        "listed 模板有该章（1 表），章节号是 md 重建的 10 字截断值",
    ),
    _e(
        "ying_ye_wai_zhi_chu",
        "营业外支出",
        "FALSE_NULL",
        "三、营业外支出（注：",
        "listed 模板有该章（1 表），章节号是 md 重建的 10 字截断值",
    ),
    _e(
        "xian_jin_liu_liang_biao_xiang_mu_zhu_shi",
        "现金流量表项目注释",
        "FALSE_NULL",
        "三、现金流量表项目注",
        "listed 模板有该章且含 9 张表，是本批受益面最大的一条",
    ),
    _e(
        "jie_kuan_fei_yong",
        "借款费用",
        "FALSE_NULL",
        "三、借款费用",
        "listed 模板有该章（会计政策章下，0 表 = 纯文字披露）",
    ),
    _e(
        "zhai_wu_chong_zu",
        "债务重组",
        "FALSE_NULL",
        "三、债务重组【不适用",
        "listed 模板有该章（0 表 = 纯文字披露），章节号含源模板的「不适用的删除」提示",
    ),
    _e(
        "zhong_zhi_jing_ying",
        "终止经营",
        "FALSE_NULL",
        "十四、终止经营",
        "listed 模板在「其他重要事项」章下有该节（1 表）",
    ),
    _e(
        "gu_fen_zhi_fu",
        "股份支付",
        "CROSS_GRAIN",
        None,
        "🔴 2026-08-07 由 FALSE_NULL 改判（原落点 `十二` 是**章标题行**不是披露节）。"
        "listed 第十二章「股份支付」实测 level=1 / tables=0 / 6 个子节"
        "（股份支付总体情况 2 表 / 以权益结算 1 表 / 以现金结算 1 表 / 本期股份支付费用 1 表 / "
        "股份支付的修改、终止情况 1 表 / `十二、1` 0 表）；而 soe 侧取值 `八、83` 是 "
        "level=2 且自带 3 表的**叶子节**（股份支付总体情况 / 以权益结算 / 以现金结算）⇒ "
        "soe 1 节 3 表 ↔ listed 1 章 6 子节，粒度不对称。补 `十二` 会让 variant_matrix 指向"
        "章标题行（该行 0 表），底稿同步取不到任何披露表；补某一个子节又会漏掉其余 5 个。"
        "⇒ 需业务确认「soe 八、83 的 3 张表分别对应 listed 哪几个子节」后再补。",
    ),
    _e(
        "tou_zi_shou_yi_xia_biao_zhong_bu_shi_yong_d",
        "投资收益【下表中不适用的项目，删除】",
        "CROSS_GRAIN",
        None,
        "🔴 2026-08-07 由 FALSE_NULL 改判（补记会造成撞码）。listed 合并章确有"
        "「五、69 投资收益」(2 表)，落点本身没问题；**但矩阵把同一科目拆成了两条** —— "
        "本条（soe 八、70 / listed null）与 `tou_zi_shou_yi`（listed 五、69 / soe null）"
        "指的是同一个「投资收益」。成因是 `build_variant_matrix.normalize_title` 只剥"
        "【】符号不剥括注文本，「投资收益【下表中不适用的项目，删除】」与「投资收益」"
        "归一后不相等 ⇒ 两者未配对（A spec 的 T10_PARENT_SIDE_WITHOUT_MERGED 已登记"
        "同一事实）。若两条各自补齐另一侧，两者的 variants 会**逐字相同** ⇒ 同一变体下"
        "两个 account_key 共用一个 section_code（实测由 0 组重复变 4 组），"
        "下游按 code 反查 account 出现二义性 —— 比留 null 更坏。"
        "⇒ 正确修法是先合并这两条 account（属 variant_matrix 生成器缺陷，"
        "不在本 spec 范围），合并后再补记。",
    ),
    # ── CROSS_GRAIN：有落点但粒度不同，需人工确认对应关系 ────────────────
    _e(
        "chi_you_dai_shou_zi_chan",
        "持有待售资产",
        "CROSS_GRAIN",
        None,
        "soe 拆两章（八、12 资产 / 八、43 负债），listed 合并为「五、11 持有待售资产和"
        "持有待售负债」(5 表) ⇒ 一对多，补记须同时决定资产/负债两侧如何落",
    ),
    _e(
        "chi_you_dai_shou_fu_zhai",
        "持有待售负债",
        "CROSS_GRAIN",
        None,
        "同上，listed 侧与「持有待售资产」共用「五、11」一章",
    ),
    _e(
        "you_xian_gu_yong_xu_zhai_deng_jin_rong_gong",
        "优先股、永续债等金融工具",
        "CROSS_GRAIN",
        None,
        "listed 侧只在会计政策章「三、金融工具」下有文字（0 表），无独立披露表；"
        "另有「三、优先股、永续债等」政策节 ⇒ 落哪个需业务确认",
    ),
    _e(
        "gui_shu_yu_mu_gong_si_suo_you_zhe_de_qi_ta",
        "归属于母公司所有者的其他综合收益",
        "CROSS_GRAIN",
        None,
        "listed 侧对应「五、57 其他综合收益」(2 表)，但标题少「归属于母公司所有者的」"
        "限定 ⇒ 口径是否等同需业务确认",
    ),
    _e(
        "mei_gu_shou_yi",
        "每股收益",
        "CROSS_GRAIN",
        None,
        "listed 侧在「十七、净资产收益率和每股收益」(2 表)，与净资产收益率合并一节",
    ),
    _e(
        "yi_nian_nei_dao_qi_de_chang_qi_jie_kuan",
        "（1）一年内到期的长期借款",
        "CROSS_GRAIN",
        None,
        "soe 把「一年内到期的」按借款/债券/应付款拆三节，listed 合并为"
        "「五、43 一年内到期的非流动负债」(5 表) ⇒ 三对一",
    ),
    _e(
        "yi_nian_nei_dao_qi_de_ying_fu_zhai_quan",
        "（2）一年内到期的应付债券",
        "CROSS_GRAIN",
        None,
        "同上，listed 侧合并进「五、43」",
    ),
    _e(
        "yi_nian_nei_dao_qi_de_chang_qi_ying_fu_kuan",
        "（3）一年内到期的长期应付款",
        "CROSS_GRAIN",
        None,
        "同上，listed 侧合并进「五、43」",
    ),
    _e(
        "shi_shou_zi_ben",
        "实收资本",
        "CROSS_GRAIN",
        None,
        "🔴 首轮误判为 TRUE_NULL。listed 模板叫「股本」(五、53)，与 soe 的「实收资本」"
        "是同一科目**两版用语互换** ⇒ 精确匹配双向都落空；补记须与 soe 侧的"
        "「股本」条目一并处置，避免两条互指",
    ),
    _e(
        "wai_bi_zhe_suan",
        "外币折算",
        "CROSS_GRAIN",
        None,
        "🔴 首轮误判为 TRUE_NULL。listed 有「五、73 外币货币性项目」(1 表，跨循环"
        "共享章) 与政策章「三、外币业务和外币报表折算」⇒ 落哪个需业务确认",
    ),
    _e(
        "fen_bu_xin_xi",
        "分部信息",
        "CROSS_GRAIN",
        None,
        "🔴 首轮误判为 TRUE_NULL。listed 叫「十四、分部报告」(5 表)，用语不同",
    ),
    _e(
        "he_bing_xian_jin_liu_liang_biao_xiang_guan",
        "合并现金流量表相关事项",
        "CROSS_GRAIN",
        None,
        "🔴 首轮误判为 TRUE_NULL。listed 对应「五、71 现金流量表补充资料」(7 表)；"
        "soe 侧该节是容器（含补充资料/取得子公司现金净额/现金等价物构成/供应商融资"
        "安排四块）⇒ 一对多",
    ),
    # ── TRUE_NULL：listed 模板确无落点 ──────────────────────────────────
    _e(
        "ying_shou_zi_jin_ji_zhong_guan_li_kuan",
        "应收资金集中管理款",
        "TRUE_NULL",
        None,
        "国资监管专属科目。listed 模板按「资金集中/资金归集」关键词全文零命中"
        "（listed 侧只在其他应收款下有「资金集中管理」子表，非独立科目）",
    ),
    _e(
        "you_qi_zi_chan",
        "油气资产",
        "TRUE_NULL",
        None,
        "listed 模板按「油气」关键词零命中 —— 上市附注模板未列该科目，"
        "两版不对称是源模板事实",
    ),
    _e(
        "fei_huo_bi_xing_zi_chan_jiao_huan",
        "非货币性资产交换",
        "TRUE_NULL",
        None,
        "listed 模板按「非货币」关键词零命中",
    ),
)


# ---------------------------------------------------------------------------
# soe_standalone 为 null 的 10 条
# ---------------------------------------------------------------------------

SOE_NULL_AUDIT: Final[tuple[NullAuditEntry, ...]] = (
    # ── FALSE_NULL ────────────────────────────────────────────────────────
    _e(
        "yi_ban_feng_xian_zhun_bei",
        "一般风险准备",
        "FALSE_NULL",
        "八、94",
        "soe 模板有该章（1 表）—— 该章由 spec m-cycle 的 fix 脚本新建（sort_index 插位）",
    ),
    _e(
        "tou_zi_shou_yi",
        "投资收益",
        "CROSS_GRAIN",
        None,
        "🔴 2026-08-07 由 FALSE_NULL 改判（Task 12 落盘前的撞码实证）。"
        "soe 合并章确有「投资收益【下表中不适用的项目，删除】」(八、70, 1 表)，"
        "但那一节**已被 `tou_zi_shou_yi_xia_biao_zhong_bu_shi_yong_d` 认领**"
        "（其 `variants.soe_*` 就是 `八、70`）⇒ 补 `八、70` 会让两个 account_key "
        "在 soe 两变体上撞码（实测补记前重复码 0 组、补记后 4 组）。"
        "根因是矩阵把同一科目拆成两条：`build_variant_matrix.normalize_title` "
        "只剥【】符号不剥括注文本，「投资收益【下表中不适用的项目，删除】」与"
        "「投资收益」归一后不相等故未配对（A spec 的 "
        "`T10_PARENT_SIDE_WITHOUT_MERGED` 已登记同一事实）。"
        "⇒ 正确处置是先合并这两条 account（属矩阵生成器的活，不在本 spec 范围），"
        "而非往其中一条补对方已占用的章节号。",
    ),
    _e(
        "xian_jin_liu_liang_biao_bu_chong_zi_liao",
        "现金流量表补充资料",
        "TRUE_NULL",
        None,
        "🔴 2026-08-07 由 FALSE_NULL 改判（A spec 已收口，复核结论反转）。"
        "soe 侧含「现金流量表补充资」的章节**全库只有 1 个**，即 "
        "`十二、现金流量表补充资`，实测 `scope='consolidated_only'` 且 "
        "`parent_section_id='chapter-12-mu-gong-si-...'` = **母公司章的子节**，"
        "已由 A spec 的 `parent_company_sections.soe` 承载。"
        "把它补进 `variants.soe_standalone/soe_consolidated`（= 合并/单体口径）"
        "会让合并口径取数指向母公司章 —— 正是本 spec 需求 2 要消除的错位形态，"
        "比留 null 更坏。soe 合并口径侧确实无独立的现金流量表补充资料披露章"
        "（该内容在 soe 模板并入「八、」各现金流量相关节），故 null 正确。"
        "关键词复核：`现金流量表补充资` 在 soe 侧命中 1 个且为母公司章子节。",
    ),
    # ── CROSS_GRAIN ───────────────────────────────────────────────────────
    _e(
        "chi_you_dai_shou_zi_chan_he_chi_you_dai_sho",
        "持有待售资产和持有待售负债",
        "CROSS_GRAIN",
        None,
        "listed 合并为一章，soe 拆两章（八、12 资产 4 表 / 八、43 负债 1 表）⇒ 一对多",
    ),
    _e(
        "qi_ta_zong_he_shou_yi",
        "其他综合收益",
        "CROSS_GRAIN",
        None,
        "🔴 首轮误判为 TRUE_NULL。soe 侧叫「八、79 归属于母公司所有者的其他综合收益」"
        "(1 表)，比 listed 标题多限定语 ⇒ 与 listed 侧同名条目互为镜像，须一并处置",
    ),
    _e(
        "gu_ben",
        "股本",
        "CROSS_GRAIN",
        None,
        "🔴 首轮误判为 TRUE_NULL。soe 模板叫「八、58 实收资本」(1 表)，"
        "与 listed 的「股本」是同一科目两版用语互换 ⇒ 须与 listed 侧「实收资本」一并处置",
    ),
    # ── TRUE_NULL ─────────────────────────────────────────────────────────
    _e(
        "she_ding_shou_yi_ji_hua_jing_zi_chan",
        "设定受益计划净资产",
        "TRUE_NULL",
        None,
        "soe 模板按「设定受益」关键词只命中长期应付职工薪酬下的「设定受益计划变动情况」"
        "子表，无独立的资产侧科目章 —— 该科目是上市专属（listed 五、17）",
    ),
    _e(
        "ku_cun_gu",
        "库存股",
        "TRUE_NULL",
        None,
        "soe 模板按「库存股/回购」关键词零命中 —— 国企附注模板未列该科目",
    ),
    _e(
        "shui_jin_ji_fu_jia",
        "税金及附加",
        "TRUE_NULL",
        None,
        "soe 模板按「税金及附加」关键词零命中（soe 侧该科目并入「八、41 应交税费」"
        "与损益类各费用节，无独立披露章）",
    ),
    _e(
        "gu_dong_quan_yi_bian_dong_biao_xiang_mu_zhu",
        "股东权益变动表项目注释",
        "TRUE_NULL",
        None,
        "soe 模板按「股东权益变动/所有者权益变动」关键词零命中 —— 该节是上市专属"
        "（listed 五、72）",
    ),
)


#: spec Requirement 7.2 点名要求补记的 8 个，全部已在 listed 侧实证为 FALSE_NULL。
#: 守卫按此断言「点名的都被裁决为 FALSE_NULL 且有落点」。
SPEC_NAMED_FALSE_NULLS: Final[frozenset[str]] = frozenset(
    {
        "zi_chan_jian_zhi_sun_shi",
        "ying_ye_wai_shou_ru",
        "ying_ye_wai_zhi_chu",
        "xian_jin_liu_liang_biao_xiang_mu_zhu_shi",
        "you_xian_gu_yong_xu_zhai_deng_jin_rong_gong",
        "jie_kuan_fei_yong",
        "zhong_zhi_jing_ying",
        "mei_gu_shou_yi",
    }
)


def verdict_of(account_key: str, side: str) -> NullAuditEntry | None:
    """按 ``account_key`` + 侧别取裁决条目；未登记返回 ``None``（绝不猜）。

    Args:
        account_key: ``variant_matrix`` 的科目键
        side: ``"listed"`` 或 ``"soe"``
    """
    table = LISTED_NULL_AUDIT if side == "listed" else SOE_NULL_AUDIT if side == "soe" else ()
    for entry in table:
        if entry.account_key == account_key:
            return entry
    return None
