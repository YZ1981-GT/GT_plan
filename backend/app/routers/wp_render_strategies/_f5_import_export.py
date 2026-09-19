"""F5 营业成本 — 导入导出（列结构对齐 requirements）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

_ADJ_HEADERS = ["序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方金额", "贷方金额", "编制人", "备注"]
_ADJ_KEYS = ["seq", "entryType", "date", "summary", "accountCode", "accountName", "debitAmount", "creditAmount", "preparer", "remark"]

_F5_2_HEADERS = [
    "品种", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月",
    "本期账项调整", "本期重分类调整", "上期未审数", "上期账项调整", "上期重分类调整", "备注",
]
_F5_2_KEYS = [
    "product", "m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10", "m11", "m12",
    "currentAje", "currentRje", "priorUnaudited", "priorAje", "priorRje", "remark",
]

_F5_SPECS: dict[str, dict[str, Any]] = {
    "F5-2": {
        "item_id": "F5-2-monthly-rows",
        "title": "F5-2 主营业务成本月度明细表",
        "headers": _F5_2_HEADERS,
        "field_keys": _F5_2_KEYS,
        "guidance": [
            "F5-2 主营业务成本月度明细表 编制说明",
            "",
            "1. 按品种动态登记1~12月成本；本期未审数=各月合计，本期审定=未审+账项调整+重分类（公式列，导入后重算）。",
            "2. 上期审定=上期未审+账项调整+重分类；未审/审定变动比例由系统计算。",
            "3. 合计行纵向汇总；比例行=各月合计/本期未审合计。",
            "4. 品种可同步至F5-1审定表主营业务成本区。",
        ],
        # 导入宽表 m1..m12 需映射为 months 数组——由前端迁移兼容；此处按扁平字段导出，
        # 导入后前端 migrate 会把 m1..m12 还原为 months。
    },
    "F5-3": {
        "item_id": "F5-3-other-cost-rows",
        "title": "F5-3 其他业务成本明细表",
        "headers": [
            "项目", "本期未审数", "本期账项调整", "本期重分类调整",
            "上期未审数", "上期账项调整", "上期重分类调整", "备注",
        ],
        "field_keys": [
            "item", "currentUnaudited", "currentAje", "currentRje",
            "priorUnaudited", "priorAje", "priorRje", "remark",
        ],
        "guidance": [
            "F5-3 其他业务成本明细表 编制说明",
            "",
            "1. 按项目登记本期/上期未审及账项、重分类调整；审定=未审+账项+重分类（公式列，导入后重算）。",
            "2. 结构比=该行审定/合计审定；变动额=本期审定−上期审定；变动率按上期审定计算。",
            "3. 预置出租固定资产等常见项目，可追加扩展行。合计应与F5-1其他业务成本核对。",
            "4. 兼容旧字段 costItem/currentAmount/priorAmount，导入后映射为 item/未审数。",
        ],
    },
    "F5-4": {
        "item_id": "F5-4-rows",
        "title": "F5-4 调整分录汇总表",
        "headers": _ADJ_HEADERS,
        "field_keys": _ADJ_KEYS,
        "guidance": ["F5-4 调整分录 编制说明", "", "分录类型填 AJE 或 RJE。"],
    },
    "F5-5": {
        "item_id": "F5-5-comparison-rows",
        "title": "F5-5 主营业务成本与上年度比较分析表",
        "headers": [
            "产品", "本期数量", "本期平均单位成本", "上期数量", "上期平均单位成本",
            "变动原因", "索引号",
        ],
        "field_keys": [
            "product", "currentQty", "currentUnitCost", "priorQty", "priorUnitCost",
            "changeReason", "indexRef",
        ],
        "guidance": [
            "F5-5 主营业务成本与上年度比较分析表 编制说明",
            "",
            "1. 按产品登记本期/上期数量与平均单位成本；总成本=数量×单价（公式列，导入后重算）。",
            "2. 变动额=本期−上期；变动率=变动额/上期（上期为0则N/A）。合计行仅汇总总成本。",
            "3. 变动原因与索引号用于交叉索引 F5-2 / F5-6 等底稿。",
            "4. 兼容旧毛利模型字段 currentCost/priorCost（导入后映射为数量=1、单价=成本）。",
        ],
    },
    "F5-6": {
        "item_id": "F5-6-quantity-recon-plants",
        "title": "F5-6 销售数量与结转成本数量核对明细表",
        "headers": [
            "分厂", "产品",
            "销售1月", "销售2月", "销售3月", "销售4月", "销售5月", "销售6月",
            "销售7月", "销售8月", "销售9月", "销售10月", "销售11月", "销售12月",
            "结转1月", "结转2月", "结转3月", "结转4月", "结转5月", "结转6月",
            "结转7月", "结转8月", "结转9月", "结转10月", "结转11月", "结转12月",
        ],
        "field_keys": [
            "plant", "product",
            "sm1", "sm2", "sm3", "sm4", "sm5", "sm6", "sm7", "sm8", "sm9", "sm10", "sm11", "sm12",
            "cm1", "cm2", "cm3", "cm4", "cm5", "cm6", "cm7", "cm8", "cm9", "cm10", "cm11", "cm12",
        ],
        "guidance": [
            "F5-6 销售数量与结转成本数量核对明细表 编制说明",
            "",
            "1. 按分厂、产品登记销售数量与结转成本数量的1~12月；总计=各月合计（公式列，导入后重算）。",
            "2. 差异=销售−结转（各月及总计只读）。分厂行=产品合计；总计行=分厂合计。",
            "3. 导入为扁平宽表；前端迁移为 { plants:[{ name, products:[{ salesMonths, costMonths }] }] }。",
            "4. 兼容旧年累计字段 salesQty/costQty（映射至12月）。",
        ],
    },
    "F5-8": {
        "item_id": "F5-8-rows",
        "title": "F5-8 主营业务成本账户中重大调整事项核查表",
        "headers": [
            "日期", "凭证号", "重大调整事项内容", "借方", "贷方", "调整理由", "理由是否充分",
        ],
        "field_keys": [
            "date", "voucherNo", "itemContent", "debitAmount", "creditAmount",
            "adjustmentReason", "reasonAdequate",
        ],
        "guidance": [
            "F5-8 主营业务成本账户中重大调整事项核查表 编制说明",
            "",
            "1. 本表是销售成本审定表（F5-1）的附表，用于审查重大调整事项的理由是否充分。",
            "2. 按日期、凭证号登记事项内容及借贷方金额，填写调整理由并评价「理由是否充分」。",
            "3. 检查现金返利、实物返利是否冲减或调整存货，或冲减购货当期主营业务成本。",
            "4. 与 F5-4 调整分录、F5-7 成本倒轧相互印证。兼容旧字段 adjustmentDate/adjustmentAmount 等。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="f5-import-export",
    api_prefix="f5",
    specs=_F5_SPECS,
    storage_field="remark",
)
