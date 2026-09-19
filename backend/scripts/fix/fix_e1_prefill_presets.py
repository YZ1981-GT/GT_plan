#!/usr/bin/env python
"""纠正并补齐 E1 货币资金的公式管理预设（幂等）。

**改造前的 5 处缺陷（全部 DB / openpyxl 实证）**

1. 🔴 **取错整个科目族**：`数字货币明细表E1-4` 块 ``account_codes=['1502']`` +
   ``TB('1502',…)``，而 `account_chart` 实证 **`1502` = 持有至到期投资减值准备**。
   数字货币按《企业会计准则解释第 15 号》（财会〔2021〕35 号）是在「货币资金」项下
   **增设二级科目**核算，**没有独立的一级标准科目** —— 写死任何码都是错的
   （活体 `1502` 全库仅 1 行 / 1 个项目，即该项目的持有至到期投资减值准备）。
   → 改 `PLACEHOLDER`，由 render 的语义槽 `digital`（按科目名 `数字货币`/`数字人民币`
   在本项目科目表里定位）动态取数。

2. 🔴 **`applies_when` 是死字段**：该块写 ``applies_when="tb_account_exists:1502"``，
   `notes` 声称「chain_orchestrator 加载 sheet 前检查 tb_balance…无则隐藏整 sheet」。
   全仓 grep 实证：``tb_account_exists`` **只出现在本 JSON 与归档 spec 文档里，无任何
   Python 消费方**；`chain_orchestrator` 的同名字段读的是 ``project_flags`` 里的
   **flag 名**（B60 平台字段机制），与本文件不是一回事。→ 该功能从未实现，字段删除
   并把 `notes` 改成实情（避免下一个人再被误导）。

3. **`sheet` 名与源 xlsx 不一致**（→ prefill 定位不到该 sheet，预设静默失效）：

   ==================  ==========================  ==============================
   块                  改造前 `sheet`              源 xlsx 真实 tab 名
   ==================  ==========================  ==============================
   货币资金审定表      ``审定表E1-1``              ``货币资金审定表E1-1``
   货币资金分析程序    ``分析程序E1-3``            ``货币资金分析表E1-14``
   ==================  ==========================  ==============================

   ``分析程序E1-3`` 是**双重错误**：源 xlsx 里 ``E1-3`` 是「银行存款及其他货币资金
   明细表」，分析表实为 ``货币资金分析表E1-14`` / ``利息收入月度分析E1-15``。
   `PREV('E1','分析程序E1-3','审定数')` 同址改正。

4. **`TB_SUM('1001~1012',…)` 是脆弱写法**：`account_chart` 实证 ``^10(0|1)[0-9]$``
   范围内只有 `1001`/`1002`/`1012`，故当前**等价**于 `BS-002`（不虚增）；但客户若有
   `1003 存放中央银行款项` / `1011 存出保证金`（金融企业科目）就会虚增。
   → 改显式三项相加，与 ``report_config`` 的 ``BS-002`` 公式逐字同构。

5. **两张披露 sheet 零公式预设**（公式管理页对披露表完全空白）→ 新增两块，
   公式依据源 xlsx 逐格可查（上市 ``B8=='货币资金审定表E1-1'!G7`` 等）。

**另补** E1-1 审定表的底稿间 `WP()` 联动（← E1-2 / E1-3 / E1-4）。

**两条硬约束**

- `preset_library.convert_prefill_presets()` 的 ``page_key = f"workpaper:{wp_code}"``
  **忽略 sheet** → 同一 wp_code 内 ``cell_ref`` 必须**全局唯一**，同名互相遮蔽。
  改造前 `审定表E1-1` 与 `分析程序E1-3` 都有 ``上年审定数`` = 已在撞键 → 本脚本给
  分析表块的条目加前缀区分。
- **明细表块禁引 `WP()`** —— E1 取数级联是 E1-2/E1-3/E1-4 → E1-1，明细反引审定表即成环。

**范围外（本脚本不动，见 spec Notes）**

`E0 银行询证函` 块的 ``sheet="审定表E0-1"`` 同样不存在（源 xlsx 真实 tab 是
``函证结果汇总表E0-1``）。E0 函证模块跨 9 个循环共享，改名会让一个长期失效的 prefill
**突然开始写入**共享 sheet，需独立验证 → 留作后续，并由守卫显式锁定现值防静默漂移。

Usage::

    python backend/scripts/fix/fix_e1_prefill_presets.py --dry-run
    python backend/scripts/fix/fix_e1_prefill_presets.py
    python backend/scripts/fix/fix_e1_prefill_presets.py --check

spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/ R3 (Task 5)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
MAPPING_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"

# ── 源 xlsx 真实 tab 名（openpyxl 实证）────────────────────────────────────
SHEET_ADJ = "货币资金审定表E1-1"
SHEET_CASH_DETAIL = "现金明细表E1-2"
SHEET_BANK_DETAIL = "银行存款及其他货币资金明细表(人民币及外币)E1-3"
SHEET_DIGITAL = "数字货币明细表E1-4"
SHEET_ANALYSIS = "货币资金分析表E1-14"
SHEET_DISC_LISTED = "附注披露信息(上市公司)"
SHEET_DISC_SOE = "附注披露信息(国企)"

# ── Task 10 新增（E-cycle spec R3.1/3.2/3.6/3.7）────────────────────────────
#: E1-3 的**另一个 variant**（同 wp_code 两张 sheet，都是真实数据录入表）
SHEET_BANK_DETAIL_RMB = "银行存款及其他货币资金明细表(仅人民币)E1-3"
SHEET_RECONCILE = "银行存款余额调节表E1-6"
SHEET_ACCOUNT_LIST = "已开立银行账户清单核对表E1-10"
SHEET_CUTOFF_BANK = "银行存款截止测试表E1-21"
SHEET_CUTOFF_OTHER = "其他货币资金截止测试表E1-22"
SHEET_CASHFLOW_CHECK = "货币资金收支检查情况表E1-23"

#: E0 块的 sheet / wp_name 纠正（源 xlsx 无 `审定表E0-1`；真实 tab 见 openpyxl 实证）
SHEET_E0_WRONG = "审定表E0-1"
SHEET_E0_RIGHT = "函证结果汇总表E0-1"
WP_NAME_E0_WRONG = "银行询证函"
WP_NAME_E0_RIGHT = "函证结果汇总表"

#: 旧值 → 新值（sheet 名纠正）
SHEET_RENAMES: dict[str, str] = {
    "审定表E1-1": SHEET_ADJ,
    "分析程序E1-3": SHEET_ANALYSIS,
}

#: `BS-002` 货币资金三项显式相加（替代脆弱区间 `TB_SUM('1001~1012',…)`）
def _bs002(period: str) -> str:
    return (
        f"=TB('1001','{period}') + TB('1002','{period}') + TB('1012','{period}')"
    )


def _cell(ref: str, formula: str | None, ftype: str, desc: str) -> dict[str, Any]:
    """构造一个预设 cell。``formula=None`` ⇒ PLACEHOLDER（值另有真源，写不成公式）。"""
    return {
        "cell_ref": ref,
        "formula": formula if formula is not None else f"=PLACEHOLDER('{ref}')",
        "formula_type": ftype,
        "description": desc,
    }


#: 货币资金三科目的发生额之和（E1-23 收支检查的总体基数）
def _mf_occurrence(side: str) -> str:
    return (
        f"=TB('1001','{side}') + TB('1002','{side}') + TB('1012','{side}')"
    )


# ── Task 10：6 个新增预设块 ─────────────────────────────────────────────────
#
# 🔴 `cell_ref` 在 `workpaper:E1` 内必须**全局唯一** —— `convert_prefill_presets()` 的
# `page_key = f"workpaper:{wp_code}"` **忽略 sheet**，同名 cell_ref 互相遮蔽。故每块的
# cell_ref 都带 sheet 语义前缀（`_total_target_rmb_*` / `调节表_*` / `账户清单_*` /
# `截止测试_*` / `收支检查_*`），不与既有块重名。

#: ① `(仅人民币)E1-3` —— 与 `(人民币及外币)` 是同 wp_code 的两个 variant，
#: 两版都是真实数据录入表且共用持久化键；缺它时用户选「仅人民币」版公式管理页全空。
BANK_DETAIL_RMB_BLOCK: dict[str, Any] = {
    "wp_code": "E1",
    "wp_name": "银行存款及其他货币资金明细表(仅人民币)",
    "sheet": SHEET_BANK_DETAIL_RMB,
    "account_codes": ["1002", "1012"],
    "cells": [
        _cell(
            "_total_target_rmb_银行存款",
            "=TB('1002','期末余额')",
            "TB",
            "汇总驱动: 银行存款期末余额合计（仅人民币版）—— 供前端横幅展示"
            "「目标 vs 实际填列差异」与 ConsistencyGate 校验，不写入 Univer。"
            "cell_ref 带 `_rmb` 区分：page_key 忽略 sheet，与(人民币及外币)版同名会互相遮蔽。",
        ),
        _cell(
            "_total_target_rmb_银行存款_期初",
            "=TB('1002','期初余额')",
            "TB",
            "汇总驱动: 银行存款期初余额合计（仅人民币版，对应源 xlsx E 列「期初余额」）",
        ),
        _cell(
            "_total_target_rmb_其他货币资金",
            "=TB('1012','期末余额')",
            "TB",
            "汇总驱动: 其他货币资金期末余额合计（仅人民币版，对应源 xlsx A26「其他货币资金：」段）",
        ),
        _cell(
            "_total_target_rmb_其他货币资金_期初",
            "=TB('1012','期初余额')",
            "TB",
            "汇总驱动: 其他货币资金期初余额合计（仅人民币版）",
        ),
    ],
    "notes": (
        "源 xlsx 有两张尾码同为 E1-3 的 sheet（(仅人民币) / (人民币及外币)），宿主按 "
        "sheetName 含「仅人民币」→ rmb、含「人民币及外币」→ multi 分流，两版**共用同一"
        "持久化键 `E1-bank-detail-rows`**（行模型带 variant 字段区分）。本块是 rmb 版的"
        "汇总驱动；明细行按户列示，逐户数据由 render 的 `account_prefill`（`tb_aux_balance` "
        "的「银行账户」维度）下发 —— 客户的 1002 在 tb_balance 里不分户（叶子恒 1 行），"
        "故账户明细写不成 TB() 公式。段小计 E12/E22/E26 等是 SUM 公式，由 _is_formula_cell 跳过。"
    ),
}

#: ② E1-6 银行存款余额调节表
RECONCILE_BLOCK: dict[str, Any] = {
    "wp_code": "E1",
    "wp_name": "银行存款余额调节表",
    "sheet": SHEET_RECONCILE,
    "account_codes": ["1002"],
    "cells": [
        _cell(
            "调节表_企业银行存款日记账余额",
            "=TB('1002','期末余额')",
            "TB",
            "源 xlsx A16「企业银行存款日记账余额」—— 调节表的起点账面余额，"
            "取银行存款期末余额（审计过程第 1 步要求「将账面余额与总账核对」）。"
            "逐户调节时应改用账户级余额（见本块 notes）。",
        ),
        _cell(
            "调节表_企业银行存款日记账余额_期初",
            "=TB('1002','期初余额')",
            "TB",
            "银行存款期初余额（供上期调节项目结转对比；源模板只列期末调节，此项为参照）",
        ),
        _cell(
            "调节表_账户级余额明细",
            None,
            "PLACEHOLDER",
            "逐个银行账户的账面余额 —— 真源是 `tb_aux_balance` 的「银行账户」辅助维度，"
            "写不成 TB() 公式（客户的 1002 在 tb_balance 里不分户，叶子恒 1 行）。"
            "由 render 的 `account_prefill` 下发；余额调节表按户编制时逐户取该值。",
        ),
    ],
    "notes": (
        "源 xlsx A13「开户银行：」+ E13「银行账号：」= 一张表对应一个账户 ⇒ 多账户需多份。"
        "A17「加：银行已收企业未收款项」与 A25「减：银行已付、企业未付款项」的明细行"
        "（R20-R24 / R28-R32）是审计师逐笔录入的未达账项，无取数来源。"
        "C17/C25 是 SUM 公式，由 _is_formula_cell 守护跳过。"
    ),
}

#: ③ E1-10 已开立银行账户清单核对表
ACCOUNT_LIST_BLOCK: dict[str, Any] = {
    "wp_code": "E1",
    "wp_name": "已开立银行账户清单核对表",
    "sheet": SHEET_ACCOUNT_LIST,
    "account_codes": ["1002", "1012"],
    "cells": [
        _cell(
            "账户清单_账户明细",
            None,
            "PLACEHOLDER",
            "已开立银行结算账户清单的逐户明细（开户银行名称/账号/账户性质/账户状态/"
            "开户日期/销户日期）—— 真源是 `tb_aux_balance` 的「银行账户」辅助维度，"
            "由 render 的 `account_prefill` 下发。**零余额账户必须保留** —— 本表是账户"
            "完整性核对表，「本年新开立但期末为 0」的账户恰是体外账户排查对象。",
        ),
        _cell(
            "账户清单_账面合计",
            "=TB('1002','期末余额') + TB('1012','期末余额')",
            "TB",
            "账面银行存款 + 其他货币资金期末合计 —— 与《已开立银行结算账户清单》"
            "逐户加总核对（源 xlsx J11「与企业信息核对一致」列的判断依据）。",
        ),
    ],
    "notes": (
        "源 xlsx 审计过程：「在企业人员陪同下到人民银行或基本存款账户开户行查询并打印"
        "《已开立银行结算账户清单》」⇒ 清单本身是**外部证据**，平台侧只能提供账面账户"
        "清单供比对，不能代替查询。三方比对（四表账户 ∪ 央行清单 ∪ E0-3 回函）属"
        "范围外（需 OCR 数据源，见 spec Notes）。"
    ),
}

#: ④ E1-21 银行存款截止测试表
CUTOFF_BANK_BLOCK: dict[str, Any] = {
    "wp_code": "E1",
    "wp_name": "银行存款截止测试表",
    "sheet": SHEET_CUTOFF_BANK,
    "account_codes": ["1002"],
    "cells": [
        _cell(
            "截止测试_银行存款期末余额",
            "=TB('1002','期末余额')",
            "TB",
            "源 xlsx A9「金额大于____元的记账凭证」的阈值参照基数 —— "
            "银行存款期末余额（阈值通常按重要性水平或余额比例确定，由审计师填写）。",
        ),
        _cell(
            "截止测试_银行存款本期借方",
            "=TB('1002','本期借方')",
            "TB",
            "银行存款本期借方发生额（收款方向）—— 截止测试抽样总体规模参照。"
            "列名 `本期借方` 已在 formula_engine.COLUMN_ALIASES 注册（14 键）。",
        ),
        _cell(
            "截止测试_银行存款本期贷方",
            "=TB('1002','本期贷方')",
            "TB",
            "银行存款本期贷方发生额（付款方向）—— 截止测试抽样总体规模参照",
        ),
    ],
    "notes": (
        "源 xlsx A9：「从银行日记账中抽取资产负债表日前（  ）天、后（  ）天，且金额大于"
        "     元的记账凭证」⇒ 天数与阈值由审计师按风险确定，本块只提供余额与发生额"
        "两个参照基数。测试明细行（日期/凭证编号/业务内容/借贷金额）由抽凭引擎回填，"
        "A30「——截止日期：202X年12月31日——」是分隔行。"
    ),
}

#: ⑤ E1-22 其他货币资金截止测试表（与 E1-21 同构，科目换 1012）
CUTOFF_OTHER_BLOCK: dict[str, Any] = {
    "wp_code": "E1",
    "wp_name": "其他货币资金截止测试表",
    "sheet": SHEET_CUTOFF_OTHER,
    "account_codes": ["1012"],
    "cells": [
        _cell(
            "截止测试_其他货币资金期末余额",
            "=TB('1012','期末余额')",
            "TB",
            "源 xlsx A9「金额大于____元的记账凭证」的阈值参照基数 —— 其他货币资金期末余额",
        ),
        _cell(
            "截止测试_其他货币资金本期借方",
            "=TB('1012','本期借方')",
            "TB",
            "其他货币资金本期借方发生额 —— 截止测试抽样总体规模参照",
        ),
        _cell(
            "截止测试_其他货币资金本期贷方",
            "=TB('1012','本期贷方')",
            "TB",
            "其他货币资金本期贷方发生额 —— 截止测试抽样总体规模参照",
        ),
    ],
    "notes": (
        "源 xlsx A9：「从其他货币资金明细账中抽取资产负债表日前（  ）天、后（  ）天…」"
        "与 E1-21 同构，仅科目由 1002 换 1012。"
    ),
}

#: ⑥ E1-23 货币资金收支检查情况表
CASHFLOW_CHECK_BLOCK: dict[str, Any] = {
    "wp_code": "E1",
    "wp_name": "货币资金收支检查情况表",
    "sheet": SHEET_CASHFLOW_CHECK,
    "account_codes": ["1001", "1002", "1012"],
    "cells": [
        _cell(
            "收支检查_借方发生额合计",
            _mf_occurrence("本期借方"),
            "TB",
            "源 xlsx A9「测试总体：如货币资金借方发生额所有凭证共XX笔金额XX」的金额 —— "
            "货币资金三科目（1001/1002/1012）本期借方发生额之和，与 report_config 的 "
            "BS-002 口径同构（显式三项相加，不用脆弱区间）。",
        ),
        _cell(
            "收支检查_贷方发生额合计",
            _mf_occurrence("本期贷方"),
            "TB",
            "源 xlsx A9「贷方发生额所有凭证共XX笔金额XX」的金额 —— 货币资金三科目"
            "本期贷方发生额之和",
        ),
        _cell(
            "收支检查_借方凭证笔数",
            None,
            "PLACEHOLDER",
            "借方发生额的凭证笔数 —— 需按凭证号去重统计序时账，而 `LEDGER()` 的科目匹配是"
            "**精确等于**且 `tb_ledger.account_code` 是客户原始码（客户记 `1002.001` 时"
            "按 `1002` 查恒 0），写死任何码都不可靠 ⇒ 由抽凭引擎的总体统计提供。",
        ),
        _cell(
            "收支检查_贷方凭证笔数",
            None,
            "PLACEHOLDER",
            "贷方发生额的凭证笔数（同上，由抽凭引擎总体统计提供）",
        ),
    ],
    "notes": (
        "源 xlsx A9/A10/A11 是抽样参数区（测试总体 / 抽样总体 / 抽样方法 / 样本量 / "
        "抽样过程），A15「1.本期借方金额检查」起是逐笔测试明细（所属科目/日期/凭证编号/"
        "业务内容/对方科目/借贷金额/银行回单/其他支持性文件/索引号），由抽凭引擎回填。"
        "本块只提供两个总体金额基数 + 两个笔数占位。"
    ),
}

#: Task 10 新增块的统一清单（顺序即写入顺序）
NEW_BLOCKS: tuple[dict[str, Any], ...] = (
    BANK_DETAIL_RMB_BLOCK,
    RECONCILE_BLOCK,
    ACCOUNT_LIST_BLOCK,
    CUTOFF_BANK_BLOCK,
    CUTOFF_OTHER_BLOCK,
    CASHFLOW_CHECK_BLOCK,
)

# ── Task 10：非数据表白名单 + 无预设登记表（R3.8）────────────────────────────
#
# 🔴 两者语义不同，不可混为一谈：
# - **白名单** = 结构上不是数据表（底稿目录 / 程序表），本就不该有取数预设；
# - **登记表** = 是数据表但**有意**不给预设（无取数来源 / 外部证据 / 逐笔录入），
#   每条必须写明理由，防「缺预设」与「不需要预设」不可区分。

#: 非数据表（源 xlsx 5 个 workbook 各 1 张底稿目录 + 3 张实质性程序表）
NON_DATA_SHEETS: frozenset[str] = frozenset({
    "底稿目录",
    "货币资金实质性程序表E1A",
    "货币资金实质性程序表E26A",
    "函证程序表E0A",
})

#: 期望的非数据表命中数（底稿目录 ×5 + E1A + E26A + E0A = 8）——
#: 存在性自检：白名单在 45 张 visible sheet 上必须恰好命中 8 次，
#: 少了说明 sheet 名漂移（白名单失效 ⇒ 登记表被塞噪声），多了说明误伤数据表。
NON_DATA_SHEET_HITS = 8

#: 有意不给预设的数据表（E1 7 张 + E0 7 张 = 14 条）。每条理由 ≥15 字。
E1_SHEETS_WITHOUT_PRESET: dict[str, str] = {
    "调整分录汇总E1-5": (
        "调整分录由 A13 错报汇总与审定表 AJE 联动生成，本表是汇总展示，"
        "无独立取数来源（写预设会与调整分录模块双真源）"
    ),
    "库存现金（人民币）盘点表E1-7": (
        "现金盘点是现场程序，金额来自实地清点（票面面额 × 张数），"
        "账面余额已在 E1-2 现金明细表，本表不重复取数"
    ),
    "库存现金（外币）盘点表E1-8": (
        "外币现金盘点同 E1-7，且原币金额与汇率四表无来源"
        "（tb_aux_balance 无 closing_fc、无汇率列）"
    ),
    "银行存单盘点表E1-9": (
        "存单是外部实物凭证，编号/面额/到期日/利率由现场清点录入，四表无对应维度"
    ),
    "银行账户情况承诺E1-11": (
        "管理层书面承诺函，全文由被审计单位出具后录入，无任何取数格"
    ),
    "企业信用报告信息查询记录E1-18": (
        "征信报告是外部证据（人民银行查询打印），查询时间/操作人/报告编号"
        "为过程记录，四表无来源"
    ),
    "企业信用报告信息与账面核对记录E1-19": (
        "征信报告与账面的核对结论逐项由审计师判断（注册资本/信贷/担保/关联关系），"
        "账面侧数据已在 E1-1 与 L 循环底稿"
    ),
    "核实被函证单位信息E0-2": (
        "被函证单位的地址/联系人/联系方式核实是外部信息核对，来源是工商公示与"
        "客户提供资料，四表无该维度"
    ),
    "货币资金发函记录表E0-3": (
        "发函清单的开户银行与账号来自 E1-3 明细表（源模板跨表引用），"
        "函证属性由审计师逐户确定，不从四表直接取数"
    ),
    "借款发函记录表E0-4": (
        "借款函证清单的借款账号与余额来自 L 循环借款底稿，"
        "本表是发函过程记录（E 循环侧不重复取数）"
    ),
    "应付银行承兑汇票发函记录表E0-5": (
        "应付票据函证清单来自 F3 应付票据明细表，本表是发函过程记录"
    ),
    "理财产品发函记录表E0-6": (
        "理财产品清单来自 G 循环金融资产底稿，产品净值非货币资金科目余额"
    ),
    "跟函函证过程控制E0-7": (
        "跟函过程控制是审计过程记录（陪同人/工号/公示核对/致电确认），"
        "全部为过程性文字，无金额取数"
    ),
    "函证程序舞弊风险评价表E0-8": (
        "舞弊迹象 19 条为审计判断三态（是/否/不适用），预置条目来自源模板红字，"
        "结论推 B50 风险评估，无金额取数"
    ),
}

#: 审定表块内被替换的公式（cell_ref → 新公式）
ADJ_FORMULA_FIXES: dict[str, dict[str, str]] = {
    "期初余额": {
        "formula": _bs002("期初余额"),
        "formula_type": "TB",
        "description": (
            "货币资金期初余额合计 = 库存现金 + 银行存款 + 其他货币资金"
            "（与 report_config 的 BS-002 公式逐字同构；原 TB_SUM('1001~1012') "
            "在客户存在 1003/1011 时会虚增）"
        ),
    },
    "未审数": {
        "formula": _bs002("期末余额"),
        "formula_type": "TB",
        "description": (
            "货币资金期末余额合计（未审）= 库存现金 + 银行存款 + 其他货币资金"
            "（对齐 report_config BS-002）"
        ),
    },
}

#: E1-1 审定表新增的底稿间联动（cell_ref 在 workpaper:E1 内全局唯一）
ADJ_NEW_CELLS: list[dict[str, Any]] = [
    {
        "cell_ref": "现金明细表期末合计",
        "formula": f"=WP('E1','{SHEET_CASH_DETAIL}','期末余额合计')",
        "formula_type": "WP",
        "description": "库存现金审定未审数来源 = E1-2 现金明细表期末余额合计",
    },
    {
        "cell_ref": "银行及其他货币资金明细表期末合计",
        "formula": f"=WP('E1','{SHEET_BANK_DETAIL}','期末余额合计')",
        "formula_type": "WP",
        "description": (
            "银行存款 + 其他货币资金审定未审数来源 = E1-3 明细表期末余额合计"
            "（E1-3 按银行账户逐户列示，合计应与 TB(1002)+TB(1012) 勾稽）"
        ),
    },
    {
        "cell_ref": "数字货币明细表期末合计",
        "formula": f"=WP('E1','{SHEET_DIGITAL}','期末余额合计')",
        "formula_type": "WP",
        "description": (
            "数字货币审定未审数来源 = E1-4 数字货币明细表期末余额合计"
            "（数字货币无一级标准科目，按科目名在本项目科目表定位，见 e_cycle_specs）"
        ),
    },
    {
        "cell_ref": "本期借方发生额",
        "formula": _bs002("本期借方"),
        "formula_type": "TB",
        "description": "货币资金本期借方发生额合计（收款；供 E1-14 分析与 E1-23 收支检查）",
    },
    {
        "cell_ref": "本期贷方发生额",
        "formula": _bs002("本期贷方"),
        "formula_type": "TB",
        "description": "货币资金本期贷方发生额合计（付款；供 E1-14 分析与 E1-23 收支检查）",
    },
]

#: 数字货币块的整块替换（`1502` 是持有至到期投资减值准备 → 不得引用）
DIGITAL_BLOCK: dict[str, Any] = {
    "wp_code": "E1",
    "wp_name": "数字货币明细表",
    "sheet": SHEET_DIGITAL,
    # 🔴 故意留空：数字货币按准则解释 15 号是货币资金项下**增设二级科目**，
    # 无独立一级标准科目。科目由 render 的语义槽 `digital` 按科目名逐项目定位。
    "account_codes": [],
    "cells": [
        {
            "cell_ref": "数字货币期末合计",
            "formula": "=PLACEHOLDER('数字货币期末余额合计')",
            "formula_type": "PLACEHOLDER",
            "description": (
                "数字货币期末余额合计 —— 无独立一级标准科目（准则解释15号：在「货币资金」"
                "项下增设二级科目核算），故不写死科目码；由 render 语义槽 `digital` "
                "按科目名（数字货币/数字人民币）在**本项目**科目表里定位后下发。"
                "本项目无该科目时前端显示「本项目无此科目」而非 0。"
            ),
        },
        {
            "cell_ref": "数字货币期初合计",
            "formula": "=PLACEHOLDER('数字货币期初余额合计')",
            "formula_type": "PLACEHOLDER",
            "description": "数字货币期初余额合计（同上，语义槽动态定位）",
        },
    ],
    "notes": (
        "改造前本块引用 TB('1502')，而 1502 实为「持有至到期投资减值准备」= 取错整个"
        "科目族（活体全库仅 1 行 / 1 项目）。原 applies_when='tb_account_exists:1502' "
        "已删除 —— 全仓 grep 实证该形态无任何 Python 消费方（chain_orchestrator 的同名"
        "字段读的是 project_flags 里的 flag 名，属 B60 平台字段机制），所谓「无 1502 则"
        "隐藏整 sheet」从未实现。明细行 R10-R16 由用户逐项录入；R17 合计行是 SUM 公式，"
        "由 _is_formula_cell 守护跳过。"
    ),
}

#: 上市披露表块 —— 公式依据源 xlsx「附注披露信息(上市公司)」逐格
DISC_LISTED_BLOCK: dict[str, Any] = {
    "wp_code": "E1",
    "wp_name": "附注披露信息(上市公司)",
    "sheet": SHEET_DISC_LISTED,
    "account_codes": ["1001", "1002", "1012"],
    "cells": [
        {
            "cell_ref": "披露上市_库存现金_期末",
            "formula": f"=WP('E1','{SHEET_ADJ}','库存现金_审定数')",
            "formula_type": "WP",
            "description": "源 xlsx B8 = '货币资金审定表E1-1'!G7（库存现金审定数）",
        },
        {
            "cell_ref": "披露上市_库存现金_期初",
            "formula": f"=WP('E1','{SHEET_ADJ}','库存现金_期初审定数')",
            "formula_type": "WP",
            "description": "源 xlsx C8 = '货币资金审定表E1-1'!D7",
        },
        {
            "cell_ref": "披露上市_银行存款_期末",
            "formula": f"=WP('E1','{SHEET_ADJ}','银行存款_审定数')",
            "formula_type": "WP",
            "description": "源 xlsx B9 = '货币资金审定表E1-1'!G10",
        },
        {
            "cell_ref": "披露上市_银行存款_期初",
            "formula": f"=WP('E1','{SHEET_ADJ}','银行存款_期初审定数')",
            "formula_type": "WP",
            "description": "源 xlsx C9 = '货币资金审定表E1-1'!D10",
        },
        {
            "cell_ref": "披露上市_存放财务公司款项_期末",
            "formula": f"=WP('E1','{SHEET_ADJ}','存放财务公司款项_审定数')",
            "formula_type": "WP",
            "description": (
                "源 xlsx B10 = '货币资金审定表E1-1'!G9。按准则解释15号「可在货币资金"
                "项目之下增设『其中：存放财务公司款项』单独列示」→ 无独立一级标准科目，"
                "由 render 语义槽 `finance_co` 按科目名定位"
            ),
        },
        {
            "cell_ref": "披露上市_其他货币资金_期末",
            "formula": f"=WP('E1','{SHEET_ADJ}','其他货币资金_审定数')",
            "formula_type": "WP",
            "description": "源 xlsx B11 = '货币资金审定表E1-1'!G11",
        },
        {
            "cell_ref": "披露上市_其他货币资金_期初",
            "formula": f"=WP('E1','{SHEET_ADJ}','其他货币资金_期初审定数')",
            "formula_type": "WP",
            "description": "源 xlsx C11 = '货币资金审定表E1-1'!D11",
        },
        {
            "cell_ref": "披露上市_存款应计利息_期末",
            "formula": f"=WP('E1','{SHEET_ADJ}','存款应计利息_审定数')",
            "formula_type": "WP",
            "description": (
                "取审定表 E1-1 的「应计利息」行（R13 = SUM(G14:G17)，即"
                "财务公司存款 / 银行机构存款 / 其他货币资金 / 数字货币 四个子项之和）。"
                "🔴 源模板缺陷（openpyxl 实证，按意图实现不照抄）：披露 sheet 的 B12 写的是"
                "`G14+G15+G16` 只取前三项、**漏掉 G17 数字货币应计利息**，"
                "而同一 workbook 的审定表 R13 是 SUM(G14:G17) 四项 —— 两处自相矛盾。"
                "平台按审定表口径取四项（前端 useE1Adjudication.accruedTotalValues 亦是四子项），"
                "否则客户持有数字人民币时披露少计其应计利息。"
                "按源模板提示：应计利息指按实际利率法计提、尚未到付息期的部分，"
                "不含逾期未收利息（列示于「应收利息」），且不属现金及现金等价物"
            ),
        },
        {
            "cell_ref": "披露上市_合计_期末",
            "formula": "=PLACEHOLDER('货币资金披露合计（表内 SUM，勿覆盖）')",
            "formula_type": "PLACEHOLDER",
            "description": "源 xlsx B14 = SUM(B8:B13) —— 表内合计公式，不由 prefill 写入",
        },
        {
            "cell_ref": "披露上市_原币表勾稽差异",
            "formula": "=PLACEHOLDER('主表合计 − 原币表人民币合计（应为 0）')",
            "formula_type": "PLACEHOLDER",
            "description": (
                "源 xlsx B16 = B14 − D62 —— 这是**勾稽校验行**不是披露行，"
                "由披露表勾稽面板计算，不推送到附注"
            ),
        },
    ],
    "notes": (
        "改造前两张披露 sheet 零预设（公式管理页空白）。主表各行取自 E1-1 审定数，"
        "与源 xlsx 的跨 sheet 引用逐格对应。外币两表（R25 外币性货币项目 / R35 原币表）"
        "取自 E1-2 / E1-3 的币种维度，其 SUMIF 形态无法用 prefill 词汇表达 → 由前端"
        "披露表按币种枚举聚合，不在此处预设。"
    ),
}

#: 国企披露表块 —— 公式依据源 xlsx「附注披露信息(国企)」逐格
DISC_SOE_BLOCK: dict[str, Any] = {
    "wp_code": "E1",
    "wp_name": "附注披露信息(国企)",
    "sheet": SHEET_DISC_SOE,
    "account_codes": ["1001", "1002", "1012"],
    "cells": [
        {
            "cell_ref": "披露国企_现金_期末",
            "formula": f"=WP('E1','{SHEET_CASH_DETAIL}','期末余额合计')",
            "formula_type": "WP",
            "description": "源 xlsx B8 = '现金明细表E1-2'!G22（国企版首行字面是「现金」）",
        },
        {
            "cell_ref": "披露国企_现金_期初",
            "formula": f"=WP('E1','{SHEET_CASH_DETAIL}','期初余额合计')",
            "formula_type": "WP",
            "description": "源 xlsx C8 = '现金明细表E1-2'!B22",
        },
        {
            "cell_ref": "披露国企_银行存款_期末",
            "formula": f"=WP('E1','{SHEET_BANK_DETAIL}','银行存款期末合计')",
            "formula_type": "WP",
            "description": "源 xlsx B9 = E1-3!AB42 + AB43",
        },
        {
            "cell_ref": "披露国企_银行存款_期初",
            "formula": f"=WP('E1','{SHEET_BANK_DETAIL}','银行存款期初合计')",
            "formula_type": "WP",
            "description": "源 xlsx C9 = E1-3!G43 + G42",
        },
        {
            "cell_ref": "披露国企_其他货币资金_期末",
            "formula": f"=WP('E1','{SHEET_BANK_DETAIL}','其他货币资金期末合计')",
            "formula_type": "WP",
            "description": "源 xlsx B10 = E1-3!AB44",
        },
        {
            "cell_ref": "披露国企_其他货币资金_期初",
            "formula": f"=WP('E1','{SHEET_BANK_DETAIL}','其他货币资金期初合计')",
            "formula_type": "WP",
            "description": "源 xlsx C10 = E1-3!G44",
        },
        {
            "cell_ref": "披露国企_受限资金_期末合计",
            "formula": "=PLACEHOLDER('受限制货币资金期末合计（按受限类别动态归集）')",
            "formula_type": "PLACEHOLDER",
            "description": (
                "源 xlsx「受限制的货币资金明细」B23 合计。各类别行由 render 的 "
                "restricted_prefill 按**叶子科目名**动态分类归集（客户命名千差万别，"
                "无法写死科目码）；未命中的叶子进「待归类」面板交审计师点选。"
                "校验预设 F1-5：②表合计.期末 = 报表货币资金期末 − 补充资料③表"
                "「期末现金及现金等价物余额」"
            ),
        },
    ],
    "notes": (
        "国企版主表首行字面是「现金」（非「库存现金」），列头是「期末余额 / 年初余额」"
        "（非「期末数 / 期初数」）—— 与上市版不同，见源 xlsx R7/R8。"
        "受限制货币资金明细表的类别行走动态分类，见 four_table/e1_restricted_buckets.py。"
    ),
}

#: 分析表块的 cell_ref 前缀纠正（原 `上年审定数` 与审定表块撞 page_key）
ANALYSIS_CELL_RENAMES: dict[str, str] = {
    "上年审定数": "分析表上年审定数",
    "本年未审数": "分析表本年未审数",
}


# ─────────────────────────── 计划构建 ───────────────────────────


def _blocks(data: dict) -> list[dict]:
    return data["mappings"]


def _find(blocks: list[dict], wp_code: str, sheet: str) -> dict | None:
    for b in blocks:
        if b.get("wp_code") == wp_code and b.get("sheet") == sheet:
            return b
    return None


def build_plan(data: dict) -> list[str]:
    """就地修改 ``data``，返回变更描述列表（空 = 已对齐）。"""
    changes: list[str] = []
    blocks = _blocks(data)

    # ① sheet 名纠正（block.sheet 与公式内的 sheet 实参**都要改**）
    for old, new in SHEET_RENAMES.items():
        blk = _find(blocks, "E1", old)
        if blk is not None:
            blk["sheet"] = new
            changes.append(f"sheet 纠正: {old!r} → {new!r}")
    # 公式实参里的旧 sheet 名（`PREV('E1','审定表E1-1',…)` / `WP('E1','分析程序E1-3',…)`）
    for b in blocks:
        if b.get("wp_code") != "E1":
            continue
        for c in b.get("cells", []):
            f = c.get("formula") or ""
            for old, new in SHEET_RENAMES.items():
                if f"'{old}'" in f:
                    c["formula"] = f.replace(f"'{old}'", f"'{new}'")
                    f = c["formula"]
                    changes.append(
                        f"{b.get('sheet')}: {c.get('cell_ref')!r} 公式内 sheet 实参 "
                        f"{old!r} → {new!r}（源 xlsx 无该 tab，原公式定位落空）"
                    )

    # ② 审定表块：公式替换 + 新增联动
    adj = _find(blocks, "E1", SHEET_ADJ)
    if adj is not None:
        cells = adj.setdefault("cells", [])
        by_ref = {c.get("cell_ref"): c for c in cells}
        for ref, patch in ADJ_FORMULA_FIXES.items():
            cur = by_ref.get(ref)
            if cur is not None and cur.get("formula") != patch["formula"]:
                cur.update(patch)
                changes.append(f"{SHEET_ADJ}: {ref} 公式改为显式 BS-002 三项相加")
        for cell in ADJ_NEW_CELLS:
            if cell["cell_ref"] not in by_ref:
                cells.append(json.loads(json.dumps(cell, ensure_ascii=False)))
                changes.append(f"{SHEET_ADJ}: 新增 {cell['cell_ref']}")

    # ③ 分析表块：cell_ref 去撞键 + 公式口径
    ana = _find(blocks, "E1", SHEET_ANALYSIS)
    if ana is not None:
        for cell in ana.get("cells", []):
            ref = cell.get("cell_ref")
            if ref in ANALYSIS_CELL_RENAMES:
                cell["cell_ref"] = ANALYSIS_CELL_RENAMES[ref]
                changes.append(
                    f"{SHEET_ANALYSIS}: cell_ref {ref!r} → "
                    f"{ANALYSIS_CELL_RENAMES[ref]!r}（page_key 忽略 sheet，需全局唯一）"
                )
            f = cell.get("formula") or ""
            if "TB_SUM('1001~1012'" in f:
                period = "期末余额" if "期末余额" in f else "期初余额"
                cell["formula"] = _bs002(period)
                cell["formula_type"] = "TB"
                changes.append(f"{SHEET_ANALYSIS}: TB_SUM 区间改显式 BS-002 三项相加")

    # ④ 数字货币块整块替换（1502 → PLACEHOLDER + 删死字段）
    dig = _find(blocks, "E1", SHEET_DIGITAL)
    if dig is not None:
        target = json.loads(json.dumps(DIGITAL_BLOCK, ensure_ascii=False))
        if dig != target:
            idx = blocks.index(dig)
            blocks[idx] = target
            changes.append(
                f"{SHEET_DIGITAL}: 整块替换 —— 1502（持有至到期投资减值准备）→ "
                "PLACEHOLDER + 删除死字段 applies_when"
            )

    # ⑤ 两张披露 sheet 新增块
    for blk in (DISC_LISTED_BLOCK, DISC_SOE_BLOCK):
        existing = _find(blocks, "E1", blk["sheet"])
        target = json.loads(json.dumps(blk, ensure_ascii=False))
        if existing is None:
            blocks.append(target)
            changes.append(f"新增披露块: {blk['sheet']}")
        elif existing != target:
            blocks[blocks.index(existing)] = target
            changes.append(f"更新披露块: {blk['sheet']}")

    # ⑥ Task 10：E0 块 sheet / wp_name 纠正
    #
    # 🔴 源 xlsx 无 `审定表E0-1`（openpyxl 实证真实 tab = `函证结果汇总表E0-1`），
    # 且 `wp_name='银行询证函'` 也与该 sheet 无关（函证结果汇总表不是询证函本身）
    # = 双重贴错标签。改名会让一个长期失效的 prefill 开始生效，故公式口径不动
    # （仍是 TB('1002',…)，与函证汇总表的账面金额列同口径）。
    e0_wrong = _find(blocks, "E0", SHEET_E0_WRONG)
    if e0_wrong is not None:
        e0_wrong["sheet"] = SHEET_E0_RIGHT
        changes.append(
            f"E0: sheet 纠正 {SHEET_E0_WRONG!r} → {SHEET_E0_RIGHT!r}"
            "（源 xlsx 无前者，prefill 长期定位落空）"
        )
    e0 = _find(blocks, "E0", SHEET_E0_RIGHT)
    if e0 is not None and e0.get("wp_name") == WP_NAME_E0_WRONG:
        e0["wp_name"] = WP_NAME_E0_RIGHT
        changes.append(
            f"E0: wp_name 纠正 {WP_NAME_E0_WRONG!r} → {WP_NAME_E0_RIGHT!r}"
            "（该 sheet 是函证结果汇总表，不是询证函本身）"
        )

    # ⑦ Task 10：6 个新增预设块（(仅人民币)E1-3 / E1-6 / E1-10 / E1-21 / E1-22 / E1-23）
    for blk in NEW_BLOCKS:
        existing = _find(blocks, "E1", blk["sheet"])
        target = json.loads(json.dumps(blk, ensure_ascii=False))
        if existing is None:
            blocks.append(target)
            changes.append(f"新增预设块: {blk['sheet']}")
        elif existing != target:
            blocks[blocks.index(existing)] = target
            changes.append(f"更新预设块: {blk['sheet']}")

    return changes


def _semantic_blob(block: dict) -> str:
    """只取**语义字段**（公式 + 科目码 + 结构字段）拼串供断言。

    🔴 不能对整块 ``json.dumps`` 做「不得出现 xxx」类断言 —— ``description`` / ``notes``
    里会**如实写出被纠正的反例**（如「原 TB_SUM('1001~1012') 在…会虚增」、
    「改造前本块引用 TB('1502')」），整块扫描会把说明文字数成真实引用而误报。
    同 `stripComments()` 一类的坑，平台已多次踩中。
    """
    parts: list[str] = [json.dumps(block.get("account_codes") or [], ensure_ascii=False)]
    for k in ("applies_when",):
        if k in block:
            parts.append(f"{k}={block[k]!r}")
    for c in block.get("cells", []):
        parts.append(str(c.get("formula") or ""))
        parts.append(str(c.get("formula_type") or ""))
    return "\n".join(parts)


def _validate_constants() -> list[str]:
    """本脚本**自身常量**的自检（与数据文件无关）。

    🔴 为什么必须单独有这一层：`validate(data)` 校验的是**数据文件**，若脚本里的
    `NEW_BLOCKS` 常量退化（某块 cells 被清空 / cell_ref 撞键），`--check` 仍会
    读到数据文件里的旧好值而返回 0 欠账 —— 直到有人跑 `--apply` 才把数据写坏。
    变异检验实测过这条（把 `RECONCILE_BLOCK['cells']` 清空后 `--check` 仍 0）。
    """
    problems: list[str] = []

    if len(NEW_BLOCKS) != 6:
        problems.append(f"NEW_BLOCKS 应有 6 块（Task 10 R3.2/3.6/3.7），实为 {len(NEW_BLOCKS)}")

    seen_ref: dict[str, str] = {}
    seen_sheet: set[str] = set()
    for blk in NEW_BLOCKS:
        sheet = str(blk.get("sheet") or "")
        if not sheet:
            problems.append("NEW_BLOCKS 有块缺 sheet 名")
            continue
        if sheet in seen_sheet:
            problems.append(f"NEW_BLOCKS 里 sheet {sheet!r} 重复声明")
        seen_sheet.add(sheet)
        if not blk.get("wp_name"):
            problems.append(f"块 {sheet!r} 缺 wp_name")
        cells = blk.get("cells") or []
        if not cells:
            problems.append(
                f"常量 NEW_BLOCKS 的块 {sheet!r} cells 为空 —— `--apply` 会把它写成"
                "空预设块（等于没预设），而数据文件里的旧值会让 --check 看不出来"
            )
        for c in cells:
            ref = str(c.get("cell_ref") or "")
            if not ref:
                problems.append(f"块 {sheet!r} 有 cell 缺 cell_ref")
                continue
            # page_key = f"workpaper:{wp_code}" 忽略 sheet ⇒ cell_ref 须全局唯一
            if ref in seen_ref:
                problems.append(
                    f"NEW_BLOCKS 内 cell_ref 撞键 {ref!r}（{seen_ref[ref]!r} 与 {sheet!r}）"
                    " —— page_key 忽略 sheet，同名会互相遮蔽"
                )
            else:
                seen_ref[ref] = sheet
            if not str(c.get("formula") or "").strip():
                problems.append(f"块 {sheet!r} 的 {ref!r} 公式为空")
            if not str(c.get("formula_type") or "").strip():
                problems.append(f"块 {sheet!r} 的 {ref!r} 缺 formula_type")
            if len(str(c.get("description") or "").strip()) < 10:
                problems.append(
                    f"块 {sheet!r} 的 {ref!r} description 过短（<10 字）"
                    " —— 预设描述是审计师理解取数口径的唯一线索"
                )

    # 白名单命中数（在 45 张 visible sheet 上）—— 存在性自检，防 sheet 名漂移
    if len(NON_DATA_SHEETS) != 4:
        problems.append(
            f"NON_DATA_SHEETS 应有 4 个名字（底稿目录 + 3 张程序表），"
            f"实为 {len(NON_DATA_SHEETS)}；命中数期望 {NON_DATA_SHEET_HITS}"
            "（底稿目录 ×5 + 程序表 ×3）"
        )

    # 登记表与白名单互斥
    both = sorted(set(E1_SHEETS_WITHOUT_PRESET) & NON_DATA_SHEETS)
    if both:
        problems.append(
            f"以下 sheet 同时在无预设登记表与非数据表白名单里: {both} —— "
            "两者语义不同（白名单=结构上不是数据表；登记表=是数据表但有意不给预设）"
        )

    # 新增块的 sheet 不得同时在登记表/白名单里
    for blk in NEW_BLOCKS:
        sheet = str(blk.get("sheet") or "")
        if sheet in E1_SHEETS_WITHOUT_PRESET:
            problems.append(f"{sheet!r} 既在 NEW_BLOCKS 又在无预设登记表里（互斥）")
        if sheet in NON_DATA_SHEETS:
            problems.append(f"{sheet!r} 既在 NEW_BLOCKS 又在非数据表白名单里（互斥）")

    return problems


def validate(data: dict) -> list[str]:
    """返回欠账列表（空 = 已对齐）。"""
    problems: list[str] = _validate_constants()
    blocks = _blocks(data)
    e1 = [b for b in blocks if b.get("wp_code") == "E1"]

    # 反向自检：确实取到了 E1 块，且语义串非空（否则下面全是空转）
    if not e1:
        problems.append("未找到任何 wp_code=E1 的块（定位失效，断言会空转）")
    elif not any(_semantic_blob(b).strip() for b in e1):
        problems.append("E1 块的语义字段全空（_semantic_blob 抽取失效）")

    # 不得残留错误 sheet 名 —— block.sheet 与**公式实参**两处都查
    for bad in SHEET_RENAMES:
        if any(b.get("sheet") == bad for b in e1):
            problems.append(f"残留错误 sheet 名 {bad!r}（block.sheet）")
        for b in e1:
            for c in b.get("cells", []):
                if f"'{bad}'" in (c.get("formula") or ""):
                    problems.append(
                        f"块 {b.get('sheet')!r} 的 {c.get('cell_ref')!r} 公式仍引用"
                        f"不存在的 sheet {bad!r}"
                    )

    for b in e1:
        blob = _semantic_blob(b)
        if "1502" in blob:
            problems.append(f"块 {b.get('sheet')!r} 仍引用 1502（持有至到期投资减值准备）")
        if "tb_account_exists" in blob:
            problems.append(f"块 {b.get('sheet')!r} 仍带死字段 applies_when/tb_account_exists")
        if "TB_SUM('1001~1012'" in blob:
            problems.append(f"块 {b.get('sheet')!r} 仍用脆弱区间 TB_SUM('1001~1012')")

    # cell_ref 在 workpaper:E1 内全局唯一（page_key 忽略 sheet）
    seen: dict[str, str] = {}
    for b in e1:
        for c in b.get("cells", []):
            ref = c.get("cell_ref")
            if ref in seen:
                problems.append(
                    f"cell_ref 撞键 {ref!r}（{seen[ref]!r} 与 {b.get('sheet')!r}）"
                    " —— page_key 忽略 sheet，同名会互相遮蔽"
                )
            else:
                seen[ref] = b.get("sheet") or ""

    # 披露块存在
    for sheet in (SHEET_DISC_LISTED, SHEET_DISC_SOE):
        if not any(b.get("sheet") == sheet for b in e1):
            problems.append(f"缺披露块 {sheet!r}")

    # 明细块禁 WP()（防成环）
    detail_sheets = {
        SHEET_CASH_DETAIL,
        SHEET_BANK_DETAIL,
        SHEET_BANK_DETAIL_RMB,
        SHEET_DIGITAL,
    }
    for b in e1:
        if b.get("sheet") in detail_sheets:
            for c in b.get("cells", []):
                if "WP(" in (c.get("formula") or ""):
                    problems.append(
                        f"明细块 {b.get('sheet')!r} 的 {c.get('cell_ref')!r} 引用了 WP() "
                        "—— 会与 E1-1 审定表成环"
                    )

    # ── Task 10 判据 ────────────────────────────────────────────────────────

    # E0 块：不得残留错名 sheet / wp_name
    for b in blocks:
        if b.get("wp_code") != "E0":
            continue
        if b.get("sheet") == SHEET_E0_WRONG:
            problems.append(
                f"E0 块残留错名 sheet {SHEET_E0_WRONG!r}（源 xlsx 真实 tab 是 "
                f"{SHEET_E0_RIGHT!r}，prefill 定位落空）"
            )
        if b.get("wp_name") == WP_NAME_E0_WRONG:
            problems.append(
                f"E0 块残留错名 wp_name {WP_NAME_E0_WRONG!r}（应为 {WP_NAME_E0_RIGHT!r}）"
            )

    # 6 个新增块必须存在，且 cells 非空
    for blk in NEW_BLOCKS:
        got = _find(blocks, "E1", blk["sheet"])
        if got is None:
            problems.append(f"缺新增预设块 {blk['sheet']!r}")
        elif not got.get("cells"):
            problems.append(f"新增预设块 {blk['sheet']!r} 的 cells 为空（等于没预设）")

    # 登记表：条目数与理由长度（防「往登记表塞一条」变成逃逸阀）
    if len(E1_SHEETS_WITHOUT_PRESET) != 14:
        problems.append(
            f"E1_SHEETS_WITHOUT_PRESET 条目数 {len(E1_SHEETS_WITHOUT_PRESET)} != 14"
            "（E1 7 张 + E0 7 张；变更须同步 spec R3.8 并写明依据）"
        )
    for sheet, reason in E1_SHEETS_WITHOUT_PRESET.items():
        if len(reason.strip()) < 15:
            problems.append(f"登记表 {sheet!r} 的理由不足 15 字：{reason!r}")

    # 登记表与实际预设互斥：登记为「无预设」的 sheet 不得同时有预设块
    for sheet in E1_SHEETS_WITHOUT_PRESET:
        if any(b.get("sheet") == sheet for b in blocks):
            problems.append(
                f"{sheet!r} 既在无预设登记表里、又有预设块 —— 两者互斥，"
                "有预设就该从登记表移出"
            )

    # 白名单：非数据表不得有预设块
    for b in blocks:
        if b.get("wp_code") in ("E0", "E1") and b.get("sheet") in NON_DATA_SHEETS:
            problems.append(
                f"非数据表 {b.get('sheet')!r} 有预设块 —— 底稿目录/程序表无取数格"
            )

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="只打印变更，不写盘")
    ap.add_argument("--check", action="store_true", help="只校验，返回欠账数")
    args = ap.parse_args()

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)

    # 🔴 round-trip 自检：本脚本用 `json.dumps(indent=2)` 整文件重写，若当前文件的
    # 序列化形态与之不同（缩进/键序/尾换行被别的工具改过），写盘会产生**全文件重排**
    # 的巨大 diff 并与并发会话冲突 ⇒ 直接 exit 2，不写盘。
    if json.dumps(data, ensure_ascii=False, indent=2) + "\n" != raw:
        print(
            "[ERR] round-trip 自检失败：当前 JSON 的序列化形态与本脚本不一致"
            "（indent=2 / ensure_ascii=False / 尾换行）。"
            "写盘会造成全文件重排，已中止。请先确认是否有别的工具改过该文件的格式。"
        )
        return 2

    if args.check:
        problems = validate(data)
        for p in problems:
            print(f"  [欠账] {p}")
        print(f"--check: {len(problems)} 项欠账")
        return 1 if problems else 0

    changes = build_plan(data)
    if not changes:
        print("已对齐，无需变更（0 项）")
        return 0
    for c in changes:
        print(f"  [变更] {c}")
    print(f"共 {len(changes)} 项变更")

    if args.dry_run:
        print("--dry-run：未写盘")
        return 0

    problems = validate(data)
    if problems:
        for p in problems:
            print(f"  [校验失败] {p}")
        print("校验未通过，拒绝写盘")
        return 1

    MAPPING_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已写入 {MAPPING_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
