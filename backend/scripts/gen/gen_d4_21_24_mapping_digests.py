# -*- coding: utf-8 -*-
"""为 D4-21/22/23/24 sibling sheet 计算冻结 mapping_digest（Wave 2）。

digest_payload 形态沿用 phase5_d4_revenue_detail.mapping_digest_payload：
contract_fields[{col,column_key,header,json_path,mode}] + 几何 + footer + 模板路径。
本脚本只算 digest 并打印，供 sibling 模块把结果写死为 EXPECTED_* 哨兵。
"""
from __future__ import annotations

import hashlib
import json

TEMPLATE_RELATIVE_PATH = "D/D4 收入底稿.xlsx"


def digest(payload: dict) -> str:
    canon = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def payload(managed_sheet, header_row, first_data, last_data, footer_row,
            footer_marker, fields, *, header_rows=None):
    p = {
        "contract_fields": [
            {"col": c, "column_key": k, "header": h, "json_path": jp, "mode": m}
            for (k, c, m, _vt, jp, h) in fields
        ],
        "first_data_row": first_data,
        "footer_marker_exact": footer_marker,
        "footer_row": footer_row,
        "header_row": header_row,
        "last_data_row": last_data,
        "managed_sheet": managed_sheet,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
    }
    if header_rows is not None:
        p["header_rows"] = list(header_rows)
    return p


# D4-21：11 受管列，header 15，data 16-30，boundary 31（三、审计说明，非合计）
D4_21_FIELDS = (
    ("party_name", "A", "editable", "text", "partyName", "关联方客户名称"),
    ("relationship", "B", "editable", "text", "relationship", "关联关系"),
    ("product", "C", "editable", "text", "product", "产品名称"),
    ("qty", "D", "editable", "amount", "qty", "销售数量"),
    ("sales_amount", "E", "editable", "amount", "salesAmount", "销售额"),
    ("sales_ratio", "F", "editable", "amount", "salesRatio", "销售额占同类产品销售额比例"),
    ("avg_price", "G", "editable", "amount", "avgPrice", "平均单价"),
    ("nonrelated_avg_price", "H", "editable", "amount", "nonrelatedAvgPrice", "非关联方销售平均单价"),
    ("fair_price", "J", "editable", "amount", "fairPrice", "可比公允价格"),
    ("prior_sales_ratio", "L", "editable", "amount", "priorSalesRatio", "上年度销售额占同类产品销售额比例"),
    ("prior_avg_price", "M", "editable", "amount", "priorAvgPrice", "上年度销售平均单价"),
    ("remark", "N", "editable", "text", "remark", "备注"),
)

# D4-23：8 受管列，两级表头 10+11，data 12-23，footer 24 合计
D4_23_FIELDS = (
    ("month", "A", "editable", "text", "month", "月份"),
    ("main_revenue", "B", "editable", "amount", "mainRevenue", "主营业务收入"),
    ("other_revenue", "C", "editable", "amount", "otherRevenue", "其他业务收入"),
    ("vat_invoice_amount", "E", "editable", "amount", "vatInvoiceAmount", "增值税发票金额"),
    ("vat_invoice_count", "F", "editable", "amount", "vatInvoiceCount", "防伪税控开具的增值税发票份数"),
    ("plain_invoice_amount", "G", "editable", "amount", "plainInvoiceAmount", "普通发票金额"),
    ("plain_invoice_count", "H", "editable", "amount", "plainInvoiceCount", "开具的普通发票份数"),
    ("index_no", "K", "editable", "text", "indexNo", "索引号"),
)

# D4-24：12 受管列，header 14，data 15-22，boundary 23（三、审计说明）
D4_24_FIELDS = (
    ("seq", "A", "editable", "text", "seq", "序号"),
    ("customer_name", "B", "editable", "text", "customerName", "客户名称"),
    ("annual_sales", "C", "editable", "amount", "annualSales", "本年度销售金额"),
    ("ending_ar", "D", "editable", "amount", "endingAr", "期末应收账款余额"),
    ("third_party_amount", "E", "editable", "amount", "thirdPartyAmount", "本年度第三方回款金额"),
    ("payer_name", "F", "editable", "text", "payerName", "第三方回款方名称"),
    ("reason", "G", "editable", "text", "reason", "第三方回款原因"),
    ("payer_customer_relation", "H", "editable", "text", "payerCustomerRelation", "第三方回款方与客户关系"),
    ("payer_entity_relation", "I", "editable", "text", "payerEntityRelation", "第三方回款方与被审计单位关系"),
    ("has_payment_agreement", "J", "editable", "text", "hasPaymentAgreement", "是否有代付协议"),
    ("is_confirmed", "K", "editable", "text", "isConfirmed", "是否函证"),
    ("rationality", "L", "editable", "text", "rationality", "合理性分析"),
    ("index_no", "M", "editable", "text", "indexNo", "索引"),
)

# D4-22：静态块 + 动态列。固定指标行作行身份，B/C 本期上期 + 同业动态列 + H 合理性。
# 数字化 digest 只锁固定列（A 指标名 + B 本期 + C 上期 + H 合理性）；同业列走 dynamic。
D4_22_METRICS = [
    "年度预算", "主营业务收入", "销售人员数量", "销售人员人均创收",
    "销售区域分布是否变化（占比和区域数量等）", "销售人员业绩指标", "销售人员薪酬",
    "期末在手订单", "息税前利润（利润总额＋财务费用）",
    "薪酬总额（支付给职工以及为职工支付的现金+期末应付职工薪酬-期初应付职工薪酬）",
    "人力投入回报率(ROP)", "运输费用/营业收入",
]
D4_22_FIXED_FIELDS = (
    ("metric_name", "A", "editable", "text", "metricName", "指标名称"),
    ("current_period", "B", "editable", "amount", "currentPeriod", "本期"),
    ("prior_period", "C", "editable", "amount", "priorPeriod", "上期"),
    ("rationality", "H", "editable", "text", "rationality", "合理性分析"),
)


def main():
    print("D4-21:", digest(payload(
        "关联方销售情况及价格分析D4-21", 15, 16, 30, 31, "三、审计说明：", D4_21_FIELDS)))
    print("D4-23:", digest(payload(
        "收入与开具发票金额比较分析D4-23", 11, 12, 23, 24, "合计", D4_23_FIELDS,
        header_rows=(10, 11))))
    print("D4-24:", digest(payload(
        "第三方回款检查D4-24", 14, 15, 22, 23, "三、审计说明：", D4_24_FIELDS)))
    # D4-22 digest 额外锁 metric 行集与 dynamic 声明
    p22 = payload("重要指标分析表D4-22", 11, 12, 23, 24, "三、审计说明", D4_22_FIXED_FIELDS)
    p22["fixed_metric_rows"] = D4_22_METRICS
    p22["dynamic_columns"] = {
        "slot": "peer", "anchor_first_col": "D", "label_row": 11,
        "note": "同业公司列，{slot}_{seq} 稳定键，禁写死列数",
    }
    print("D4-22:", digest(p22))


if __name__ == "__main__":
    main()
