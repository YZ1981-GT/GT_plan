"""J 类（职工薪酬）科目定位与分类 —— 单一真源。

**为什么需要本模块**

改造前 J1/J2 各自硬编码科目码，且 J2 写的是 ``2221`` = **应交税费**（长期应付职工薪酬实为
``2705``）。活体 8 个项目里 ``2221`` 有 18~72 行数据 → J2-1 审定表预填出的是**全部税种行**，
TB 核对数是应交税费余额；不是"恒空"，是**把税种当成长期应付职工薪酬显示**。同族缺陷：
K2（``1231`` 坏账准备 → ``1901`` 其他流动资产）、D6（``1402`` 在途物资 → ``1141`` 合同资产）。

**科目映射真源（`report_config` 实证）**

====  ==========  ==========  ==========================  ==========
循环  变体        报表行      公式                        科目
====  ==========  ==========  ==========================  ==========
J1    listed_*    ``BS-051``  ``TB('2211','期末余额')``   ``2211``
J1    soe_*       ``BS-069``  ``TB('2211','期末余额')``   ``2211``
J2    listed_*    ``BS-067``  **NULL**                    兜底 ``2705``
J2    soe_*       ``BS-093``  **NULL**                    兜底 ``2705``
====  ==========  ==========  ==========================  ==========

🔴 **两变体报表行编码不同**（平台其它循环多为同一 row_code 跨准则），故 spec 按变体挑，
不给共享件 :class:`ReportLineAccountSpec` 加只有 J 类需要的字段。

**客户子科目天然对应披露行**（同 F1 ``1123`` / G7 ``1511`` 范式，活体 ``account_chart`` 实证）

- ``2211.01 短期薪酬`` → 披露「（1）短期薪酬」；其下 ``.01 工资`` / ``.03 福利费`` /
  ``.04 社会保险``（``.04.01 医疗`` / ``.04.02 工伤`` / ``.04.03 生育``）/ ``.05 住房公积金`` /
  ``.06 工会经费`` / ``.07 职工教育经费`` / ``.02 短期带薪缺勤`` / ``.99 其他短期薪酬`` **逐行对应**
- ``2211.02 设定提存计划`` → 披露「（2）设定提存计划」；``.02.01 基本养老`` / ``.02.02 失业`` /
  ``.02.03 企业年金`` **逐行对应「其中：」四项**
- ``2705.01.02 当期服务成本`` … ``.06 重新计量`` → J2 披露「设定受益计划变动情况」变动行

**归类一律按科目名称、编码只作兜底** —— 平台已两次实证编码语义在项目间冲突
（存货 ``1405``/``1406``、税金 ``6403.02``），职工薪酬同理（``221101`` 平铺形态无二级段可判）。

spec: .kiro/specs/j-cycle-four-table-extraction-and-disclosure-alignment/
      Requirements 1.1, 1.4, 3.1, 3.2 / Property 1, 4
"""
from __future__ import annotations

from dataclasses import dataclass

from .report_line_accounts import ReportLineAccountSpec

# ─────────────────────────────────────────────────────────────────────────────
# 报表行定位（按变体）
# ─────────────────────────────────────────────────────────────────────────────

#: J1 应付职工薪酬 —— 原值兜底标准码。两变体公式相同，但 row_code 不同。
J1_GROSS_FALLBACK: tuple[str, ...] = ("2211",)

#: J2 长期应付职工薪酬 —— `report_config` 两变体公式均为 NULL，必须兜底。
J2_GROSS_FALLBACK: tuple[str, ...] = ("2705",)

#: 🔴 `is_liability=True` 必填 —— J 类原值科目本身是**贷方**。不置该标志时
#: `split_gross_provision` 会按 `account_chart.direction == 'credit'` 把 `2211` / `2705`
#: 整体误判成备抵：实测 4 个项目 `gross` 变空、`resolved_from` 谎报 `fallback`、
#: 溯源面板把「应付职工薪酬」显示成备抵科目（第 5 个项目 `account_chart` 无该科目行
#: 才侥幸走对 = 缺陷被数据掩盖）。J 类无备抵科目，故也不设 `provision_row_code`。
J1_SPEC_BY_ENTITY: dict[str, ReportLineAccountSpec] = {
    "listed": ReportLineAccountSpec(
        row_code="BS-051", fallback_gross=J1_GROSS_FALLBACK, is_liability=True
    ),
    "soe": ReportLineAccountSpec(
        row_code="BS-069", fallback_gross=J1_GROSS_FALLBACK, is_liability=True
    ),
}

J2_SPEC_BY_ENTITY: dict[str, ReportLineAccountSpec] = {
    "listed": ReportLineAccountSpec(
        row_code="BS-067", fallback_gross=J2_GROSS_FALLBACK, is_liability=True
    ),
    "soe": ReportLineAccountSpec(
        row_code="BS-093", fallback_gross=J2_GROSS_FALLBACK, is_liability=True
    ),
}

#: 主体类型未知时的默认变体（活体 8 个在册项目 `entity_type` 全为 soe）
DEFAULT_ENTITY = "soe"


def entity_of(applicable_standards) -> str:
    """从适用准则列表判定主体类型（``'listed'`` / ``'soe'``）。纯函数。

    `derive_applicable_standards` 输出形如 ``["soe_standalone", "soe", "standalone"]``；
    只看 entity 维度（附注模板只有 listed/soe 两份，章节号差异也只由它决定）。
    """
    for std in applicable_standards or []:
        s = str(std or "").strip().lower()
        if s.startswith("listed"):
            return "listed"
        if s.startswith("soe"):
            return "soe"
    return DEFAULT_ENTITY


def pick_spec(
    specs: dict[str, ReportLineAccountSpec], applicable_standards
) -> ReportLineAccountSpec:
    """按适用准则挑对应变体的报表行 spec。纯函数，恒返回非 None。"""
    return specs[entity_of(applicable_standards)]


# ─────────────────────────────────────────────────────────────────────────────
# J1 分类规则（声明式单一真源）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AccountRule:
    """一条「科目名 → 目标行」的归类规则。

    Attributes:
        key: 目标行的稳定键（前端行 key / 审定表 category）。
        label: 中文标签，**逐字取自源 xlsx**。
        keywords: 科目名匹配词。规则表顺序即优先级，首个命中即返回。
        exclude_keywords: 否决词 —— 命中任一则本规则不适用。
            🔴 必要性：``其他权益变动_不属于其他综合收益`` 类命名会让宽关键字误命中
            （G7 已实证），职工薪酬侧同理：「设定提存」与「设定受益」互为干扰。
        code_segments: 编码兜底 —— ``2211`` 的二级段（``'01'`` / ``'02'``）。
            仅当名称完全不命中时使用；平铺形态（``221101``）无二级段，只能靠名称。
        source_ref: 源 xlsx 单元格坐标，供 openpyxl 守卫反查。
    """

    key: str
    label: str
    keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    code_segments: tuple[str, ...] = ()
    source_ref: str = ""


# ── J1 审定表三分类（沿用前端 useJ1Adjudication 的 category 枚举，零回归） ──

CAT_SHORT_TERM = "short_term"
CAT_POST_EMPLOYMENT = "post_employment"
CAT_SEVERANCE = "severance"

#: 🔴 顺序即优先级。`辞退` 必须先于 `短期`：``2211.01.99.05 应付职工薪酬_短期薪酬_
#: 其他短期薪酬_辞退经济补偿`` 的科目名同时含「短期薪酬」与「辞退」，按披露口径
#: （源模板主表有独立「辞退福利」行）应归 severance。守卫 Property 4 用它反向自检。
J1_CATEGORY_RULES: tuple[AccountRule, ...] = (
    AccountRule(
        key=CAT_SEVERANCE,
        label="辞退福利",
        keywords=("辞退", "解除劳动关系", "内退"),
        source_ref="J1!附注披露信息（上市公司）!A9",
    ),
    AccountRule(
        key=CAT_POST_EMPLOYMENT,
        label="离职后福利-设定提存计划",
        keywords=(
            "设定提存",
            "基本养老",
            "养老保险",
            "失业保险",
            "年金",
            "离职后福利",
            "离退休",
        ),
        # 设定受益计划属 J2（2705），即便客户挂在 2211 下也不并入设定提存行
        exclude_keywords=("设定受益",),
        code_segments=("02", "07"),
        source_ref="J1!附注披露信息（上市公司）!A8",
    ),
    AccountRule(
        key=CAT_SHORT_TERM,
        label="短期薪酬",
        keywords=("短期薪酬", "工资", "福利费", "社会保险", "公积金", "工会", "教育经费"),
        code_segments=("01",),
        source_ref="J1!附注披露信息（上市公司）!A7",
    ),
)

#: 名称与编码都不命中时的兜底分类。源模板主表有「一年内到期的其他福利」与国企「其他」行，
#: 但把未识别科目塞进它们属臆造 → 统一落 short_term（源模板「其他短期薪酬」是正当收纳行）。
J1_CATEGORY_FALLBACK = CAT_SHORT_TERM


# ── J1 披露「（1）短期薪酬」明细行（源 R18~R33 逐字） ──

J1_SHORT_TERM_ROW_RULES: tuple[AccountRule, ...] = (
    AccountRule(
        key="salary",
        label="工资、奖金、津贴和补贴",
        keywords=("工资", "奖金", "津贴", "补贴"),
        exclude_keywords=("劳务派遣", "离退休"),
        source_ref="J1!附注披露信息（上市公司）!A18",
    ),
    AccountRule(
        key="welfare",
        label="职工福利费",
        keywords=("福利费",),
        exclude_keywords=("劳务派遣", "非货币"),
        source_ref="J1!附注披露信息（上市公司）!A19",
    ),
    AccountRule(
        key="social_medical",
        label="其中：1．医疗保险费",
        keywords=("医疗保险",),
        source_ref="J1!附注披露信息（上市公司）!A21",
    ),
    AccountRule(
        key="social_injury",
        label="2．工伤保险费",
        keywords=("工伤",),
        source_ref="J1!附注披露信息（上市公司）!A22",
    ),
    AccountRule(
        key="social_maternity",
        label="3．生育保险费",
        keywords=("生育",),
        source_ref="J1!附注披露信息（上市公司）!A23",
    ),
    # 🔴 必须排在三个具体险种**之后**：`'社会保险' in '..._社会保险_医疗保险'` 为真，
    # 放前面会把三个险种全吞掉。本条收纳「只到社会保险费这一层」的叶子
    # （活体平铺形态 `221103 社会保险费`）与未识别险种（`..._社会保险_其他`）。
    # 落父行会破坏「社会保险费 = Σ其中：各险种」勾稽（源 R20 是 SUM 公式），
    # 故落源模板 R24 的 `……` 可扩位，seed 时 label 取实际叶子科目名。
    AccountRule(
        key="social_other",
        label="……",
        keywords=("社会保险", "社保"),
        source_ref="J1!附注披露信息（上市公司）!A24",
    ),
    AccountRule(
        key="housing",
        label="住房公积金",
        keywords=("公积金",),
        source_ref="J1!附注披露信息（上市公司）!A28",
    ),
    AccountRule(
        key="union_edu",
        label="工会经费和职工教育经费",
        keywords=("工会", "教育经费"),
        source_ref="J1!附注披露信息（上市公司）!A29",
    ),
    AccountRule(
        key="paid_absence",
        label="短期带薪缺勤",
        keywords=("带薪缺勤",),
        source_ref="J1!附注披露信息（上市公司）!A30",
    ),
    AccountRule(
        key="profit_sharing",
        label="短期利润分享计划",
        keywords=("利润分享",),
        source_ref="J1!附注披露信息（上市公司）!A31",
    ),
    AccountRule(
        key="non_monetary",
        label="非货币性福利",
        keywords=("非货币",),
        source_ref="J1!附注披露信息（上市公司）!A32",
    ),
)

#: 「其他短期薪酬」是源模板的正当收纳行（R33）。未匹配的短期类叶子落此
#: （实证会落这里的：``2211.03 劳务派遣费`` / ``.05 劳动保护费`` / ``.06 商业保险``
#: —— 客户把这些挂在 2211 下核算，判「是不是外来科目」需客户科目表实证，不按行名推断）。
J1_SHORT_TERM_FALLBACK_ROW = AccountRule(
    key="other_short_term",
    label="其他短期薪酬",
    source_ref="J1!附注披露信息（上市公司）!A33",
)

#: 「社会保险费」父行 = 其下「其中：」各险种之和（源 R20 为 SUM 公式，不可手工录入）
J1_SOCIAL_PARENT_ROW = AccountRule(
    key="social",
    label="社会保险费",
    source_ref="J1!附注披露信息（上市公司）!A20",
)
J1_SOCIAL_CHILD_KEYS: tuple[str, ...] = (
    "social_medical",
    "social_injury",
    "social_maternity",
    "social_other",
)


# ── J1 披露「（2）设定提存计划」明细行（源 R41~R48 逐字，含序号） ──

J1_DC_ROW_RULES: tuple[AccountRule, ...] = (
    AccountRule(
        key="dc_pension",
        label="其中：1．基本养老保险费",
        keywords=("基本养老", "养老保险"),
        source_ref="J1!附注披露信息（上市公司）!A42",
    ),
    AccountRule(
        key="dc_unemployment",
        label="2．失业保险费",
        keywords=("失业",),
        source_ref="J1!附注披露信息（上市公司）!A43",
    ),
    AccountRule(
        key="dc_annuity",
        label="3．企业年金缴费",
        keywords=("年金",),
        source_ref="J1!附注披露信息（上市公司）!A44",
    ),
)

J1_DC_FALLBACK_ROW = AccountRule(
    key="dc_other",
    label="4．其他",
    source_ref="J1!附注披露信息（上市公司）!A45",
)

J1_DC_PARENT_ROW = AccountRule(
    key="dc_parent",
    label="离职后福利",
    source_ref="J1!附注披露信息（上市公司）!A41",
)


# ─────────────────────────────────────────────────────────────────────────────
# J2 变动行规则（2705 子科目 → 设定受益计划变动情况）
# ─────────────────────────────────────────────────────────────────────────────

#: 🔴 顺序即优先级。`重新计量` 必须先于 `设定受益`（``2705.01.06 …_重新计量设定收益负债``
#: 同时含两者）；`过去服务成本` 必须先于 `当期服务成本`（都含「服务成本」）。
J2_MOVEMENT_RULES: tuple[AccountRule, ...] = (
    AccountRule(
        key="oci_remeasure",
        label="设定受益计划净负债（净资产）的重新计量",
        keywords=("重新计量",),
        source_ref="J2!附注披露信息（国有企业）!A23",
    ),
    AccountRule(
        key="pl_past",
        label="2．过去服务成本",
        keywords=("过去服务成本",),
        source_ref="J2!附注披露信息（上市公司）!A22",
    ),
    AccountRule(
        key="pl_service",
        label="1．当期服务成本",
        keywords=("当期服务成本", "服务成本"),
        exclude_keywords=("过去",),
        source_ref="J2!附注披露信息（上市公司）!A21",
    ),
    AccountRule(
        key="pl_settle",
        label="3．结算利得（损失以“-”表示）",
        keywords=("结算利得",),
        source_ref="J2!附注披露信息（上市公司）!A23",
    ),
    AccountRule(
        key="pl_interest",
        label="4．利息净额",
        keywords=("利息净额",),
        source_ref="J2!附注披露信息（上市公司）!A24",
    ),
    AccountRule(
        key="begin",
        label="一、期初余额",
        keywords=("初始入账",),
        source_ref="J2!附注披露信息（上市公司）!A19",
    ),
)

#: J2 明细表 J2-2 的两个一级项（源 明细表J2-2 R13 / R16）
J2_TOP_ROW_RULES: tuple[AccountRule, ...] = (
    AccountRule(
        key="severance",
        label="辞退福利",
        keywords=("辞退",),
        code_segments=("02",),
        source_ref="J2!明细表J2-2!B16",
    ),
    AccountRule(
        key="post_employment",
        label="其中：1、离职后福利",
        keywords=("设定受益", "离退休", "离职后"),
        code_segments=("01",),
        source_ref="J2!明细表J2-2!B14",
    ),
)

J2_TOP_FALLBACK_ROW = AccountRule(
    key="other_long_term",
    label="     2、其他长期职工福利",
    source_ref="J2!明细表J2-2!B15",
)


# ─────────────────────────────────────────────────────────────────────────────
# 归类纯函数
# ─────────────────────────────────────────────────────────────────────────────


def _second_segment(code: str) -> str:
    """取 ``2211.01.04`` 的二级段 ``'01'``。平铺形态（``221101``）无点号 → 返空串。"""
    parts = (code or "").strip().split(".")
    return parts[1] if len(parts) >= 2 else ""


def match_rule(
    rules,
    account_name: str,
    account_code: str = "",
    *,
    fallback: AccountRule | None = None,
) -> AccountRule | None:
    """按规则表归类（名称优先 + 否决词 + 编码兜底）。纯函数。

    Args:
        rules: :class:`AccountRule` 序列，**顺序即优先级**。
        account_name: 科目名（``tb_balance.account_name``）。
        account_code: 科目码，供 ``code_segments`` 兜底。
        fallback: 全不命中时返回它（``None`` 则返回 ``None``）。

    Returns:
        命中的规则，或 ``fallback``。
    """
    name = (account_name or "").strip()
    seg = _second_segment(account_code)

    # 第一轮：名称匹配（含否决词）
    for rule in rules or ():
        if not rule.keywords:
            continue
        if rule.exclude_keywords and any(x in name for x in rule.exclude_keywords):
            continue
        if any(k in name for k in rule.keywords):
            return rule

    # 第二轮：编码二级段兜底（平铺形态取不到段，直接落 fallback）
    if seg:
        for rule in rules or ():
            if seg in (rule.code_segments or ()):
                return rule

    return fallback


def classify_j1_leaf(account_code: str, account_name: str) -> str:
    """``2211`` 叶子 → J1 审定表分类键（``short_term`` / ``post_employment`` / ``severance``）。"""
    rule = match_rule(J1_CATEGORY_RULES, account_name, account_code)
    return rule.key if rule else J1_CATEGORY_FALLBACK


def classify_j1_short_term_row(account_code: str, account_name: str) -> AccountRule:
    """``2211.01`` 叶子 → 披露「（1）短期薪酬」明细行。恒返回一条规则。"""
    return (
        match_rule(
            J1_SHORT_TERM_ROW_RULES,
            account_name,
            account_code,
            fallback=J1_SHORT_TERM_FALLBACK_ROW,
        )
        or J1_SHORT_TERM_FALLBACK_ROW
    )


def classify_j1_dc_row(account_code: str, account_name: str) -> AccountRule:
    """``2211.02`` 叶子 → 披露「（2）设定提存计划」明细行。恒返回一条规则。"""
    return (
        match_rule(
            J1_DC_ROW_RULES, account_name, account_code, fallback=J1_DC_FALLBACK_ROW
        )
        or J1_DC_FALLBACK_ROW
    )


def classify_j2_movement(account_code: str, account_name: str) -> AccountRule | None:
    """``2705.01.xx`` 叶子 → 设定受益计划变动行。无对应变动性质时返 ``None``（宁缺勿造）。"""
    return match_rule(J2_MOVEMENT_RULES, account_name, account_code)


def classify_j2_top_row(account_code: str, account_name: str) -> AccountRule:
    """``2705`` 叶子 → J2-2 明细表一级项。恒返回一条规则。"""
    return (
        match_rule(
            J2_TOP_ROW_RULES, account_name, account_code, fallback=J2_TOP_FALLBACK_ROW
        )
        or J2_TOP_FALLBACK_ROW
    )


def flat_form_prefixes(prefixes) -> list[str]:
    """由点号前缀集派生**无点号平铺**形态的基码。

    🔴 :func:`leaf_aggregation.filter_by_prefixes` 严格要求点号边界（防 ``1221`` 误命中
    ``12210``），因此平铺形态 ``221101`` 不会被前缀 ``2211`` 命中。而 ``account_mapping``
    的反解结果又会被 :func:`minimal_prefix_set` 折叠成 ``['2211']``（子码全被父码前缀覆盖），
    单靠反解拿不回平铺子码 → 必须由基码 + 位数规则动态还原。
    """
    out: list[str] = []
    for p in prefixes or []:
        base = str(p or "").strip().replace(".", "")
        if base and base not in out:
            out.append(base)
    return out


def is_flat_child(code: str, base: str) -> bool:
    """``code`` 是否为 ``base`` 的**无点号平铺**子科目。纯函数。

    平铺形态每级 2 位数字（``2211`` → ``221101`` → ``22110101``），故判定为
    「去掉 base 前缀后，余下是长度为偶数的纯数字」。

    这条位数规则是必要的防误命中闸：``'12210'.startswith('1221')`` 为真，但 ``0``
    长度为奇数 → 判否（``12210`` 不是 ``1221`` 的子科目，是另一个科目码）。
    """
    c = (code or "").strip()
    b = (base or "").strip()
    if not c or not b or c == b or not c.startswith(b):
        return False
    rest = c[len(b) :]
    return rest.isdigit() and len(rest) % 2 == 0


def _has_child(code: str, all_codes: set[str], flat_bases: list[str]) -> bool:
    """``code`` 在给定码集中是否有子科目（点号形态或平铺形态）。"""
    dot_prefix = code + "."
    for other in all_codes:
        if other == code:
            continue
        if other.startswith(dot_prefix):
            return True
        # 平铺形态：仅当 code 本身落在本次科目范围内才按平铺规则判子级，
        # 否则 `2211` 会把无关的 `22119999` 认成子科目。
        if any(code == b or is_flat_child(code, b) for b in flat_bases) and is_flat_child(
            other, code
        ):
            return True
    return False


def select_scope_leaves(rows, prefixes) -> list:
    """在给定科目范围内筛出**叶子行**，同时兼容点号与平铺两种形态。纯函数。

    🔴 为什么不能直接用 :func:`leaf_aggregation.select_leaves` + ``filter_by_prefixes``：

    1. ``select_leaves`` 只按 ``code + '.'`` 判子级 → 客户若用平铺形态，``2211`` 会被
       当成叶子，而 ``221101`` 等真实叶子又被 ``filter_by_prefixes`` 漏掉
       → 结果只剩父额一行，明细全丢；两者若同时命中还会**父子双计**。
    2. 各项目科目表差异极大（实测 ``2211`` 原始码 27 / 33 / 51 个不等，
       ``2705`` 7~10 个不等）→ 不能假设层级深度，只能按「有没有子科目」动态判定。

    Args:
        rows: `tb_balance` 全量行（:class:`LeafRow` 或同结构对象，需有 ``account_code``
            与可选 ``dataset_id``）。
        prefixes: 科目范围前缀集（``ReportLineAccounts.gross``，原始码）。

    Returns:
        范围内的叶子行（保持入参顺序）。
    """
    flat_bases = flat_form_prefixes(prefixes)
    dot_prefixes = [str(p or "").strip() for p in (prefixes or []) if str(p or "").strip()]

    def _in_scope(code: str) -> bool:
        if any(code == p or code.startswith(p + ".") for p in dot_prefixes):
            return True
        return any(is_flat_child(code, b) for b in flat_bases)

    # 按 dataset 分桶（同 `select_leaves`：子科目须与父级同数据集才算其子级）
    by_dataset: dict[object, list] = {}
    for r in rows or []:
        code = getattr(r, "account_code", "") or ""
        if not code:
            continue
        by_dataset.setdefault(getattr(r, "dataset_id", None), []).append(r)

    out: list = []
    for group in by_dataset.values():
        codes = {getattr(r, "account_code", "") for r in group}
        for r in group:
            code = getattr(r, "account_code", "") or ""
            if not _in_scope(code):
                continue
            if _has_child(code, codes, flat_bases):
                continue
            out.append(r)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SemanticAccountSpec 声明（供 resolve_semantic_accounts 使用）
# ─────────────────────────────────────────────────────────────────────────────

from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

J1_SEMANTIC_SPEC = SemanticAccountSpec(
    row_code="BS-069",  # 国企行号（在册项目绝大多数是 soe）
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("应付职工薪酬", "短期应付职工薪酬"),
            exclude_names=(),
            fallback_standard_codes=("2211",),
            label="应付职工薪酬",
        ),
    ),
)

J2_SEMANTIC_SPEC = SemanticAccountSpec(
    row_code="BS-093",  # 国企行号
    slots=(
        SemanticAccountSlot(
            key="gross",
            names=("长期应付职工薪酬",),
            exclude_names=(),
            fallback_standard_codes=("2705",),
            label="长期应付职工薪酬",
        ),
    ),
)


def j_semantic_spec_of(wp_code: str) -> SemanticAccountSpec | None:
    """按 wp_code 取 J 循环的 SemanticAccountSpec。"""
    code = str(wp_code or "").strip().upper()
    if code == "J1":
        return J1_SEMANTIC_SPEC
    if code == "J2":
        return J2_SEMANTIC_SPEC
    return None


__all__ = [
    "CAT_POST_EMPLOYMENT",
    "CAT_SEVERANCE",
    "CAT_SHORT_TERM",
    "DEFAULT_ENTITY",
    "AccountRule",
    "J1_CATEGORY_FALLBACK",
    "J1_CATEGORY_RULES",
    "J1_DC_FALLBACK_ROW",
    "J1_DC_PARENT_ROW",
    "J1_DC_ROW_RULES",
    "J1_GROSS_FALLBACK",
    "J1_SHORT_TERM_FALLBACK_ROW",
    "J1_SHORT_TERM_ROW_RULES",
    "J1_SOCIAL_CHILD_KEYS",
    "J1_SOCIAL_PARENT_ROW",
    "J1_SPEC_BY_ENTITY",
    "J2_GROSS_FALLBACK",
    "J2_MOVEMENT_RULES",
    "J2_SPEC_BY_ENTITY",
    "J2_TOP_FALLBACK_ROW",
    "J2_TOP_ROW_RULES",
    "classify_j1_dc_row",
    "classify_j1_leaf",
    "classify_j1_short_term_row",
    "classify_j2_movement",
    "classify_j2_top_row",
    "entity_of",
    "flat_form_prefixes",
    "is_flat_child",
    "match_rule",
    "pick_spec",
    "select_scope_leaves",
]
