"""``report_config`` 行名 ↔ ``account_chart`` 科目名 对账判据的**单一真源**.

spec: `report-config-account-code-integrity`（Task 1）。

背景：`report_config` 是平台「报表行 → 科目码」唯一真源，`resolve_report_line_account_codes`
与 `semantic_account_resolver`（层③）都读它。这张表此前**零一致性校验** ——
`row_name` 与 formula 引用科目的实际名从不比对，错码可静默存在数年
（2026-08-03 全表对账查出 13 行错码，此前两次修复只覆盖 5 行且其中一次前提错误）。

本模块只放**判据**，不做 IO；对账逻辑在
`backend/tests/four_table/test_report_config_account_integrity.py`。
迁移侧的校验也读本模块，避免两份判据打架。

判据三条边界（写在这里防下个会话放宽）：

1. **`row_name` 与科目名不同 ≠ 错码** —— 报表用语与会计科目用语本就不同
   （`未分配利润` 对应科目 `利润分配`）。`ROW_NAME_ACCOUNT_ALIASES` 是**穷举**的，
   不是模糊匹配；加一条必须有实证。
2. **码零命中 ≠ 错码** —— 要看该科目名在库里有没有别的归属：
   有 → 错码（`BS-084` 的 `4005`，库存股实为 `4201`）；
   没有 → 业务事实（`BS-004` 的 `1102`，衍生金融资产这批项目都没有）。
3. **按 source 分域判定** —— `client` 8 项目 / `standard` 10 项目，且 standard 侧
   并存两套编码体系 → 合并判定会把 `4101` 误判成「一码多名」。
"""
from __future__ import annotations

import re

# ─── 两套编码体系（守卫必须内建的事实） ──────────────────────────────────────

#: ``account_chart`` 的 ``source='standard'`` 并存两套完整编码体系，不是零散错码。
#:
#: | 体系                        | 权益 | 成本     | 损益 | 项目数 |
#: |----------------------------|------|---------|------|-------|
#: | 旧《企业会计制度》(2001)     | 3xxx | **4xxx** | 5xxx | 6     |
#: | CAS 2006                   | **4xxx** | 5xxx | 6xxx | 4     |
#:
#: 2026-08-03 实证的同码双名（同一 source 内），全部来自体系差异而**非错码**：
#: ``4001`` 实收资本/生产成本 · ``4101`` 盈余公积/制造费用 ·
#: ``4301`` 专项储备/研发支出 · ``4401`` 其他权益工具/工程施工。
#: → 名称比对必须「命中任一即通过」，且不得据此判「一码多名」为缺陷。
DUAL_SYSTEM_CODES: frozenset[str] = frozenset({"4001", "4101", "4301", "4401"})


# ─── 报表用语 ↔ 会计科目用语 的合法差异（穷举，非模糊匹配） ──────────────────

#: 每对 = (report_config.row_name 侧用语, account_chart.account_name 侧用语)。
#:
#: 🔴 只收「同一科目的两种叫法」，**不得用它掩盖真错码** ——
#: 守卫有一条断言：别名两侧归一后不得在同一 source 内指向**不同**科目码。
ROW_NAME_ACCOUNT_ALIASES: tuple[tuple[str, str], ...] = (
    # 利润分配是科目，未分配利润是其下的报表列示口径（BS-088 = TB('4104')）
    ("未分配利润", "利润分配"),
    # 报表用「款项」，科目用「账款」
    ("预收款项", "预收账款"),
    ("预付款项", "预付账款"),
    # 报表用「收益」，科目用「损益」
    ("公允价值变动收益", "公允价值变动损益"),
    ("资产处置收益", "资产处置损益"),
    # 同一科目在不同项目的两种写法（2026-08-03 实证：1901 在库里两名并存，
    # standard 侧 损溢5/损益3 项目、client 侧 损溢1/损益4 项目）
    ("待处理财产损溢", "待处理财产损益"),
)


# ─── 零命中码白名单（业务事实，不改） ────────────────────────────────────────

#: 引用码在全库 ``account_chart`` 任何 source 任何项目都不存在，
#: **且该科目名在库中亦零命中** → 判为业务事实（这批项目确实没有该科目）。
#:
#: 🔴 value 必须写明实证查询与日期；空白 value 视为未登记 → 守卫打红。
#: 🔴 一旦该科目名在库中出现，守卫必须打红（迫使复核该行是否其实是错码）。
ZERO_HIT_WHITELIST: dict[str, str] = {
    "BS-004": (
        "1102 衍生金融资产：码与名在全库 account_chart 均零命中"
        "（2026-08-03 实证 SELECT ... WHERE account_code='1102' OR account_name LIKE '%衍生金融资产%'）"
    ),
    "BS-007": (
        "1124 应收款项融资：码与名在全库 account_chart 均零命中"
        "（2026-08-03 实证；memory 亦已记该码不存在）"
    ),
    "BS-037": (
        "1911 其他非流动资产：码与名在全库 account_chart 均零命中（2026-08-03 实证）"
    ),
    # 🔴 BS-066 已于 2026-08-04 从白名单**移出** —— spec 立项时的白名单依据错了：
    #    `2811` 确实零命中，但「递延收益」在库中**有归属**（`2401`，standard 9 / client 6 项目）
    #    → 按判据边界 2「码零命中 + 名有归属 = 错码」，它是第 14 个错码而非业务事实。
    #    见 SUSPECTED_NEW_ISSUES。
    "BS-068": (
        "2911 其他非流动负债：码与名在全库 account_chart 均零命中（2026-08-03 实证）"
    ),
}


# ─── 派生行：语义上不对应任何单一会计科目 ────────────────────────────────────

#: 这些行是**重分类 / 合并抵销 / 变动额**派生项，挂单一科目码只会让审定表
#: 显示一个来源错误的数 → formula 必须为 NULL，调用方按既有
#: ``return codes or fallback`` 走自己的兜底或显示「本项目无此科目」。
#:
#: value = 判定依据（守卫要求非空）。
DERIVED_ROWS_WITHOUT_ACCOUNT: dict[str, str] = {
    "BS-090": (
        "少数股东权益：合并抵销派生项，CAS 2006 无对应单一会计科目；"
        "原写 4201 实为库存股，既取错又与修正后的 BS-084 双算"
    ),
    "BS-013": (
        "一年内到期的非流动资产：各非流动资产一年内到期部分的重分类合计；"
        "原写 1503 实为可供出售金融资产（旧准则科目）"
    ),
    "BS-053": (
        "其他流动负债：原写 2901 实为递延所得税负债，且已由 BS-067 认领 → 跨行双算；"
        "CAS 下该行是「其他」性质汇总，无单一科目"
    ),
    "BS-043": (
        "衍生金融负债：原写 2102 实为短期应付债券；CAS 2006 的衍生工具在 3201，"
        "但该码在 standard 侧是「利润分配」(6 项目) → 一码两义不可用，故置 NULL"
    ),
    "CFSS-016": (
        "存货的减少：是**变动额**（期初−期末）不是余额，且存货是区间 1401~1499；"
        "原写单一 1401 实为材料采购"
    ),
    "IMP-017": (
        "十六、商誉减值准备：原写 1711 是商誉**原值**（把原值当备抵）；"
        "1712 商誉减值准备在全库零命中 → 宁缺勿造置 NULL"
    ),
}


# ─── 修正清单（V138 的机器可读镜像，供守卫交叉锁死） ─────────────────────────

#: row_code → (错码, 正确码, 实证)。仅含「改码」的行；「置 NULL」的行见
#: ``DERIVED_ROWS_WITHOUT_ACCOUNT``。
#:
#: 守卫用它断言「修正后不得再出现错码」+「新码在库中确实叫这个名」。
CODE_CORRECTIONS: dict[str, tuple[str, str, str]] = {
    "BS-082": ("4003", "4401", "其他权益工具：client 5 项目 = 4401；4003 实为其他综合收益"),
    "BS-084": ("4005", "4201", "库存股：client 5 / standard 3 项目 = 4201；4005 全库零命中"),
    "BS-085": ("4102", "4003", "其他综合收益：client 8 项目 = 4003；4102 全库零命中"),
    "BS-086": ("4103", "4301", "专项储备：client 4 项目 = 4301；4103 实为本年利润"),
    "EQ-015": ("4201", "4301", "（五）专项储备：同 BS-086；4201 实为库存股"),
    "BS-033": ("1703", "1704", "开发支出：client 4 / standard 3 项目 = 1704；1703 实为无形资产减值准备"),
    "IMP-008": ("1502", "1505", "债权投资减值准备：standard 6 项目 = 1505；1502 实为持有至到期投资减值准备（旧准则）"),
}

#: 已实证**正确**、不得被批量替换波及的权益段行（Property 2 的对照组）。
KNOWN_CORRECT_EQUITY_ROWS: dict[str, str] = {
    "BS-081": "4001",  # 实收资本（或股本）—— client 8 项目 = 实收资本
    "BS-083": "4002",  # 资本公积 —— client 7 项目
    "BS-087": "4101",  # 盈余公积 —— client 8 项目（standard 侧另有制造费用，属体系差异）
    "BS-088": "4104",  # 未分配利润 —— 科目名「利润分配」，走别名表
}

#: 🔴 待用户裁决，**不在 V138 范围内**（见 requirements R5）。
#: `1901` 名实不符（待处理财产损溢/损益）且 `tb_balance` 该科目全库余额恒 0；
#: `listed_standalone` 额外加的 `TB('1131')` 应收股利已由 `BS-009` 认领 = 潜在双算。
PENDING_ADJUDICATION: dict[str, str] = {
    "BS-014": (
        "其他流动资产 = TB('1901')：1901 实为待处理财产损溢/损益且余额恒 0；"
        "listed_standalone 另加 TB('1131') 应收股利与 BS-009 双算。"
        "三选项见 spec R5，倾向置 NULL 让 K2 走 k2_account_scope 兜底。"
        "波及 22 个文件引用 → 须用户拍板后另立 V139。"
    ),
}


# ─── 名称归一 ────────────────────────────────────────────────────────────────

#: 行名前缀噪声：`△`（保险专用行标记）/ `加：` / `减：` / `其中：`
_PREFIX_NOISE = ("△", "加：", "减：", "其中：", "加:", "减:", "其中:")

#: 中文序号前缀，两种形态：`一、`~`二十、` 与 `（一）`~`（二十）`
_SECTION_PREFIX_RE = re.compile(
    r"^(?:[（(][一二三四五六七八九十]+[）)]|[一二三四五六七八九十]+[、．.])\s*"
)

#: 尾部括注（`（或股本）` / `（增加以"－"号填列）` / `（不适用删除）`）
_TRAILING_PAREN_RE = re.compile(r"[（(][^（()）]*[）)]\s*$")

#: 全角/半角空白
_SPACE_RE = re.compile(r"[\s\u3000]+")


def normalize_name(s: str | None) -> str:
    """归一报表行名 / 科目名，供名称比对。

    去除：中文序号前缀（`一、` `（五）`）、`△` `加：` `减：` `其中：`、
    尾部括注、全部空白。

    🔴 只做**确定性**的噪声剥离，不做同义词映射（那是 ``ROW_NAME_ACCOUNT_ALIASES``
    的职责，且必须逐条有实证）。
    """
    if not s:
        return ""
    out = str(s).strip()
    # 序号前缀可能与 △/加： 叠加，循环剥到不变
    for _ in range(4):
        before = out
        out = _SECTION_PREFIX_RE.sub("", out)
        for noise in _PREFIX_NOISE:
            if out.startswith(noise):
                out = out[len(noise):]
        out = out.strip()
        if out == before:
            break
    # 尾部括注（可能有多层）
    for _ in range(3):
        stripped = _TRAILING_PAREN_RE.sub("", out).strip()
        if stripped == out or not stripped:
            break
        out = stripped
    return _SPACE_RE.sub("", out)


def alias_group(name: str) -> frozenset[str]:
    """返回 ``name`` 所属的别名等价类（含自身，全部已归一）。

    别名表是无向的：查 `未分配利润` 与查 `利润分配` 得到同一个集合。
    """
    target = normalize_name(name)
    if not target:
        return frozenset()
    group = {target}
    # 别名关系可能链式（A↔B、B↔C），迭代到闭包
    for _ in range(len(ROW_NAME_ACCOUNT_ALIASES) + 1):
        grew = False
        for left, right in ROW_NAME_ACCOUNT_ALIASES:
            nl, nr = normalize_name(left), normalize_name(right)
            if nl in group and nr not in group:
                group.add(nr)
                grew = True
            elif nr in group and nl not in group:
                group.add(nl)
                grew = True
        if not grew:
            break
    return frozenset(group)


def names_match(row_name: str, account_name: str, *, detail_row: bool = False) -> bool:
    """行名与科目名是否视为一致（经归一 + 别名等价类）。

    ``detail_row=True`` 用于「其中：」明细行：此时行名 = 限定语 + 父科目名
    （``其中：应收账款坏账准备`` ← ``1231.02`` 的父科目名是 ``坏账准备``），
    比对放宽为「父科目名是行名的子串」。**只对明细行放宽**，普通行仍要求相等。
    """
    a = normalize_name(row_name)
    b = normalize_name(account_name)
    if not a or not b:
        return False
    if a == b:
        return True
    if b in alias_group(a):
        return True
    if detail_row and b in a:
        return True
    return False


def is_detail_row(row_name: str) -> bool:
    """是否「其中：」式明细展开行。"""
    return str(row_name or "").strip().startswith(DETAIL_ROW_PREFIXES)


# ─── TB 引用抽取 ─────────────────────────────────────────────────────────────

#: 匹配 ``TB('1123','期末余额')`` 与 ``SUM_TB('1401~1499','期末余额')``。
#:
#: 🔴 **函数名是 `SUM_TB` 不是 `TB_SUM`**（2026-08-04 实证：全表
#: ``regexp_matches(formula,'([A-Za-z_]\w*)\s*\(','g')`` 去重只有 ``TB`` / ``SUM_TB`` / ``ROW``）。
#: 写成 ``\bTB(?:_SUM)?`` 会漏掉 ``SUM_TB``（``_`` 是词字符，``\bTB`` 在 ``SUM_TB``
#: 中间不成立）→ 把 ``BS-010 存货 = SUM_TB('1401~1499') - TB('1416')`` 误抽成**单码行**，
#: 于是拿「存货」去比对备抵科目「存货跌价准备」而误报。
#:
#: 逗号前后允许空白（实证 BS-* 无空格、EQ/IMP/CFSS 有空格）。第 2 组 = 取数列（可缺省）。
TB_REF_RE = re.compile(r"\b(?:SUM_)?TB\s*\(\s*'([^']+)'\s*(?:,\s*'([^']*)')?")


def extract_tb_codes(formula: str | None) -> list[str]:
    """抽 formula 里全部 ``TB*('code')`` 的码（保序、保重复）。

    重复保留是有意的：``EQ-015`` 的 ``TB('4201','期末余额') - TB('4201','期初余额')``
    两处都要被修正，去重会让「两处都换了吗」这条断言失效。
    """
    if not formula:
        return []
    return [m[0] for m in TB_REF_RE.findall(formula)]


def extract_tb_refs(formula: str | None) -> list[tuple[str, str]]:
    """抽 ``(码, 取数列)`` 对；列缺省时返回空串。

    跨行双算判定必须带列 —— ``CFSS-026 现金的期末余额`` 与
    ``CFSS-027 减：现金的期初余额`` 引同一批码但列不同（期末 vs 期初），
    不带列会把它误判成双算。
    """
    if not formula:
        return []
    return [(m[0], m[1] or "") for m in TB_REF_RE.findall(formula)]


# ─── 名称比对的适用范围（判据收敛，防误杀） ──────────────────────────────────

#: **余额类报表** —— 行名通常就是科目名，可做严格名称对账。
BALANCE_SHEET_TABLES: frozenset[str] = frozenset({"BS", "IMP"})

#: **流量/变动类报表** —— 行名是「XX的增加/减少/折旧/摊销/损失」等**变动额**语义，
#: 与余额科目名天然不同（`CFSS-005 固定资产折旧` ← `1602 累计折旧`、
#: `CFSS-014 递延所得税资产减少` ← `1811 递延所得税资产`），
#: 且 `EQ-001 一、上期期末余额` 是多科目合计 → **名称对账不适用**。
#: 这类行只做「码在库中存在」检查（零命中仍按分档处置）。
FLOW_SHEET_TABLES: frozenset[str] = frozenset({"CFSS", "IS", "EQ"})

#: 行名前缀表示「上一行的明细展开」，其名 = 父科目名 + 限定语
#: （`IMP-002 其中：应收账款坏账准备` ← `1231.02` 的父科目名是「坏账准备」）
#: → 比对放宽为「父科目名是行名的子串」。
DETAIL_ROW_PREFIXES: tuple[str, ...] = ("其中：", "其中:")


def is_name_comparable(row_code: str, codes: list[str]) -> bool:
    """该行是否适用**严格**行名 ↔ 科目名对账。

    三个条件同时成立才做严格比对：

    1. 属余额类报表（`BS` / `IMP`）—— 流量表的行名是变动额语义
    2. **去重后只引用一个码** —— 多码行的行名是合成语义
       （`BS-002 货币资金` = 库存现金+银行存款+其他货币资金，无一叫「货币资金」；
       `BS-028 固定资产` = 原值−累计折旧−减值，减项当然不叫固定资产）
    3. 该码不是区间口径（`1401~1499`）

    🔴 这三条是**收敛判据不是放宽兜底**：不适用严格比对的行仍然要过
    「码必须在库中存在」与「派生行必须 NULL」两道检查，只是不做名称比对。
    """
    table = row_code.split("-", 1)[0]
    if table not in BALANCE_SHEET_TABLES:
        return False
    unique = {c for c in codes}
    if len(unique) != 1:
        return False
    return "~" not in next(iter(unique))


#: 🔴 本轮守卫**新查出**、spec 立项清单里没有的疑似问题 —— 不擅自进 V138，
#: 守卫跳过并在断言消息里提示，等用户裁决后另开任务。
SUSPECTED_NEW_ISSUES: dict[str, str] = {
    "BS-052": (
        "一年内到期的非流动负债 = TB('2501')：2501 实为长期借款，且已由 BS-061 长期借款认领 "
        "→ 与 BS-013/BS-053 同型（重分类派生行 + 跨行双算）。"
        "2026-08-04 守卫首次跑出，spec 立项清单未含，待裁决是否并入置 NULL 批次。"
    ),
    "BS-066": (
        "递延收益 = TB('2811')：2811 全库零命中，而「递延收益」实际挂在 2401"
        "（standard 9 / client 6 项目，CAS 2006 口径）→ 按判据边界 2 是**错码**，"
        "应 2811→2401。spec 立项时误将它列入零命中白名单（白名单依据只查了码没查名）。"
        "2026-08-04 守卫首次跑出，待裁决是否并入 V138 改码批次。"
    ),
}


def head_code(code: str) -> str:
    """取科目码主段，供查 ``account_chart``。

    ``1231-03`` → ``1231``（标准码用横杠分隔明细）；
    ``1231.03`` → ``1231``（客户原始码用点号）；
    ``1401~1499`` → ``1401``（区间口径取起点，仅用于存在性判断）。
    """
    for sep in ("~", "-", "."):
        if sep in code:
            code = code.split(sep, 1)[0]
    return code.strip()
