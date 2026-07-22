"""H1 固定资产 — 导入导出3端点（列结构对齐 requirements）.

POST /h1/export-template → 空白结构xlsx（H1-2按4区段分sheet）
POST /h1/export-data → 当前数据xlsx（含公式结果）
POST /h1/import-data → 解析xlsx→验证→写入checklist_responses
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── H1-2 明细表（基础区段） ─────────────────────────────────────────────────

_H1_2_BASE_HEADERS = [
    "资产分类", "资产名称", "资产编号", "入账日期", "使用年限(年)", "残值率(%)", "折旧方法",
    "存放地点", "使用部门", "是否提足折旧", "是否闲置", "是否有权属证明", "是否抵押受限",
]
_H1_2_BASE_KEYS = [
    "category", "name", "assetNo", "acquisitionDate", "usefulLife", "salvageRate", "depMethod",
    "location", "department", "isFullyDepreciated", "isIdle", "hasTitleDoc", "isMortgaged",
]

# ─── H1-2 明细表（原值变动区段） ─────────────────────────────────────────────

_H1_2_COST_HEADERS = [
    "资产分类", "资产名称",
    "未审期初", "未审本期增加", "增加方式", "未审本期减少", "减少方式", "未审期末",
    "期初调整", "账项调整增加", "账项调整减少",
    "审定期初", "审定本期增加", "审定本期减少", "审定期末",
]
_H1_2_COST_KEYS = [
    "category", "name",
    "costBeginUnadj", "costIncUnadj", "costIncMethod", "costDecUnadj", "costDecMethod", "costEndUnadj",
    "costOpenAdj", "costAjeInc", "costAjeDec",
    "costBeginAud", "costIncAud", "costDecAud", "costEndAud",
]

# ─── H1-2 明细表（折旧区段） ─────────────────────────────────────────────────

_H1_2_DEP_HEADERS = [
    "资产分类", "资产名称",
    "未审期初", "未审本期计提", "未审其他增加", "未审处置", "未审其他减少", "未审期末",
    "期初调整", "调整计提", "调整其他增加", "调整处置", "调整其他减少",
    "审定期初", "审定本期增加", "审定本期减少", "审定期末",
]
_H1_2_DEP_KEYS = [
    "category", "name",
    "depBeginUnadj", "depProvUnadj", "depOtherIncUnadj", "depDispUnadj", "depOtherDecUnadj", "depEndUnadj",
    "depOpenAdj", "depAjeProv", "depAjeOtherInc", "depAjeDisp", "depAjeOtherDec",
    "depBeginAud", "depIncAud", "depDecAud", "depEndAud",
]

# ─── H1-2 明细表（减值区段） ─────────────────────────────────────────────────

_H1_2_IMPAIR_HEADERS = [
    "资产分类", "资产名称",
    "未审期初", "未审本期计提", "未审其他增加", "未审处置", "未审其他减少", "未审期末",
    "期初调整", "调整计提", "调整其他增加", "调整处置", "调整其他减少",
    "审定期初", "审定本期增加", "审定本期减少", "审定期末",
    "期初未审净值", "期初审定净值", "期末未审净值", "期末审定净值",
]
_H1_2_IMPAIR_KEYS = [
    "category", "name",
    "impairBeginUnadj", "impairProvUnadj", "impairOtherIncUnadj", "impairDispUnadj", "impairOtherDecUnadj", "impairEndUnadj",
    "impairOpenAdj", "impairAjeProv", "impairAjeOtherInc", "impairAjeDisp", "impairAjeOtherDec",
    "impairBeginAud", "impairIncAud", "impairDecAud", "impairEndAud",
    "netBeginUnadj", "netBeginAud", "netEndUnadj", "netEndAud",
]

# ─── H1-3 调整分录 ──────────────────────────────────────────────────────────

# 对齐 Excel「固定资产调整分录汇总表」：类别=账项调整/报表调整/其他；科目代码为数字化增强列
_H1_3_HEADERS = [
    "序号", "调整事项说明", "类别", "报表项目", "科目代码", "科目名称",
    "附注项目", "借方调整金额", "贷方调整金额", "索引", "备注",
]
_H1_3_KEYS = [
    "seq", "description", "category", "reportItem", "accountCode", "accountName",
    "noteItem", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ─── H1-7 增加检查 ──────────────────────────────────────────────────────────

_H1_7_HEADERS = [
    "序号", "固定资产类别", "资产编号", "资产名称", "增加方式", "增加日期", "凭证号", "对方科目",
    "原值", "累计折旧", "减值准备", "净值",
    "验收单号", "验收日期", "合同编号", "合同对方", "合同金额",
    "发票号", "发票对方", "发票金额",
    "费用/资本化", "折旧起算日",
    "是否关联方", "关联方名称", "是否异常", "检查结果", "索引号", "备注",
]
_H1_7_KEYS = [
    "seq", "category", "assetNo", "name", "additionMethod", "acquisitionDate", "voucherNo", "counterpartAccount",
    "originalCost", "accDep", "impairment", "netValue",
    "acceptanceRef", "acceptanceDate", "contractRef", "contractParty", "contractAmount",
    "invoiceRef", "invoiceParty", "invoiceAmount",
    "expenseOrCapital", "depStartDate",
    "isRelatedParty", "relatedPartyName", "isAbnormal", "checkResult", "indexRef", "remark",
]

# ─── H1-8 减少检查 ──────────────────────────────────────────────────────────

_H1_8_HEADERS = [
    "序号", "固定资产类别", "资产编号", "资产名称", "减少方式", "减少日期", "凭证号", "对方科目",
    "原值", "累计折旧", "减值准备", "净值", "清理费用", "清理收入", "清理净损益",
    "申报单号", "是否恰当审批", "合同编号", "合同对方", "发票号", "评估报告",
    "是否关联方", "关联方名称", "是否异常", "检查结果", "索引号", "备注",
]
_H1_8_KEYS = [
    "seq", "category", "assetNo", "name", "disposalMethod", "disposalDate", "voucherNo", "counterpartAccount",
    "originalCost", "accDep", "impairment", "netValue", "disposalCost", "disposalIncome", "disposalGainLoss",
    "applicationRef", "isApproved", "contractRef", "contractParty", "invoiceRef", "evaluationReport",
    "isRelatedParty", "relatedPartyName", "isAbnormal", "checkResult", "indexRef", "remark",
]

# ─── H1-10 盘点检查（双向抽盘 · 账面/企业/抽盘三数量）─────────────────────────

_H1_10_HEADERS = [
    "序号", "抽盘方向", "资产名称", "资产编号", "存放地点", "规格", "单位", "单价",
    "账面数量", "账面金额", "企业盘点数量", "抽盘数量",
    "品质状况", "盘点结果", "差异原因", "差异金额", "处理建议", "盘点人", "备注",
]
_H1_10_KEYS = [
    "seq", "direction", "name", "assetNo", "location", "spec", "unit", "unitPrice",
    "bookQty", "bookAmount", "clientCountQty", "sampleQty",
    "qualityStatus", "result", "diffReason", "diffAmount", "suggestion", "checker", "remark",
]

# ─── H1-16 房屋权属 ─────────────────────────────────────────────────────────

_H1_16_HEADERS = [
    "序号", "资产编号", "资产名称", "原值", "累计折旧", "减值准备", "净值",
    "权证编号", "权利人", "是否被审计单位", "共有情况", "房屋坐落", "登记时间",
    "权利类型", "规划用途", "建筑面积", "使用期限", "他项权利", "权证索引",
    "是否抵押受限", "抵押面积", "抵押价值", "抵押性质", "抵押权人",
    "是否在建转固", "转固日期", "预计办证日", "办证进度",
    "核对结论", "备注",
]
_H1_16_KEYS = [
    "seq", "assetCode", "name", "bookValue", "accumDep", "impairment", "netValue",
    "titleCertNo", "owner", "isOwnerEntity", "coOwnership", "address", "issueDate",
    "propertyNature", "usage", "buildingArea", "usefulLife", "otherRights", "certCopyIndex",
    "isMortgaged", "mortgageArea", "mortgageAmount", "mortgageNature", "mortgagee",
    "fromCip", "completionDate", "expectedCertDate", "cipNote",
    "checkConclusion", "remark",
]

# ─── H1-19 经营租出 ─────────────────────────────────────────────────────────

_H1_19_HEADERS = [
    "序号", "承租方", "资产名称", "原值", "净值", "租赁起始日", "租赁终止日",
    "租赁期限(月)", "年租金", "月租金", "总租金收入", "折旧分摊", "维修费用",
    "租赁净收益", "收益率(%)", "市场租金参考", "差异", "合同编号", "是否关联", "结论", "备注",
]
_H1_19_KEYS = [
    "seq", "lessee", "assetName", "originalCost", "netValue", "leaseStart", "leaseEnd",
    "leaseTerm", "annualRent", "monthlyRent", "totalRentIncome", "depAlloc", "maintenanceCost",
    "netLeaseIncome", "returnRate", "marketRentRef", "rentDiff", "contractNo", "isRelated", "conclusion", "remark",
]

# ─── H1-18 关联交易 ─────────────────────────────────────────────────────────

_H1_18_HEADERS = [
    "序号", "交易方向", "关联单位名称", "关联方关系", "资产类别", "固定资产名称",
    "交易价格", "入账价值", "折旧年限", "出售时原值", "出售时累计折旧", "出售时减值准备",
    "出售时净值", "交易日期", "同类交易总额", "占同类比例%", "定价政策",
    "公允评估价值", "价格差异率%", "是否异常", "审批文件", "结论", "备注", "索引号",
]
_H1_18_KEYS = [
    "seq", "transType", "counterparty", "relationship", "assetCategory", "name",
    "transAmount", "bookValue", "depYears", "originalCost", "accumDep", "impairment",
    "netValue", "transDate", "categoryTotal", "similarRatio", "pricingPolicy",
    "appraisedValue", "priceDiffRate", "hasAnomaly", "approvalDoc", "conclusion", "remark", "indexRef",
]

# ─── H1-12 折旧测算（企业台账一键导入模板） ─────────────────────────────────

_H1_12_HEADERS = [
    "固定资产类别", "固定资产编号", "固定资产名称", "管理部门",
    "原值", "累计折旧期初", "累计折旧期末", "本期折旧", "账面月折旧额",
    "开始使用日期", "使用年限", "残值率", "折旧方法",
    "减值准备期初", "减值准备期末", "本期计提减值", "计提减值准备日期", "处置日期",
    "估计变更日", "变更前年限", "变更后年限", "变更前残值率", "变更后残值率",
]
_H1_12_KEYS = [
    "category", "assetNo", "assetName", "department",
    "originalCost", "accDepBegin", "bookAccDepEnd", "bookDepreciation", "bookMonthly",
    "startDate", "usefulLife", "salvageRate", "depMethod",
    "impairmentBegin", "impairmentEnd", "impairmentProvision", "impairmentDate", "disposalDate",
    "estimateChangeDate", "usefulLifeBefore", "usefulLifeAfter", "salvageRateBefore", "salvageRateAfter",
]

# ═══════════════════════════════════════════════════════════════════════════════

_H1_SPECS: dict[str, dict[str, Any]] = {
    "H1-2-base": {
        "item_id": "H1-2-rows",
        "title": "H1-2 明细表（基础信息）",
        "headers": _H1_2_BASE_HEADERS,
        "field_keys": _H1_2_BASE_KEYS,
        "guidance": [
            "H1-2 固定资产明细表 — 基础区段 编制说明",
            "",
            "折旧方法可选：直线法/双倍余额递减/年数总和法/工作量法。",
            "残值率通常为3%~5%。使用年限参考CAS4及税法规定。",
            "核对标志：是否提足折旧/闲置/权属证明/抵押受限（是填Y，否填N）。",
        ],
    },
    "H1-2-cost": {
        "item_id": "H1-2-rows",
        "title": "H1-2 明细表（原值变动）",
        "headers": _H1_2_COST_HEADERS,
        "field_keys": _H1_2_COST_KEYS,
        "guidance": [
            "H1-2 原值变动区段 编制说明（对齐源模板未审→调整→审定）",
            "",
            "未审期末=未审期初+未审增加-未审减少。",
            "审定期初=未审期初+期初调整；审定增加=未审增加+账项调整增加；审定减少同理。",
            "审定期末=审定期初+审定增加-审定减少。公式列导出时为结果值。",
        ],
    },
    "H1-2-dep": {
        "item_id": "H1-2-rows",
        "title": "H1-2 明细表（折旧）",
        "headers": _H1_2_DEP_HEADERS,
        "field_keys": _H1_2_DEP_KEYS,
        "guidance": [
            "H1-2 折旧区段 编制说明",
            "",
            "未审期末=期初+本期计提+其他增加-处置-其他减少（备抵类1602）。",
            "审定增减=未审对应项+账项调整对应项。",
        ],
    },
    "H1-2-impair": {
        "item_id": "H1-2-rows",
        "title": "H1-2 明细表（减值）",
        "headers": _H1_2_IMPAIR_HEADERS,
        "field_keys": _H1_2_IMPAIR_KEYS,
        "guidance": [
            "H1-2 减值区段 编制说明",
            "",
            "减值结构同累计折旧。净值=原值-累计折旧-减值准备（分别未审/审定）。",
            "固定资产减值损失一经确认不得转回（CAS8）；处置时冲销已提减值属转出而非转回。",
        ],
    },
    "H1-3": {
        "item_id": "H1-3-rows",
        "title": "H1-3 调整分录汇总表",
        "headers": _H1_3_HEADERS,
        "field_keys": _H1_3_KEYS,
        "allow_missing_headers": True,
        "header_aliases": {
            "类别": ["entryType", "调整类别", "AJE/RJE"],
            "借方调整金额": ["借方金额", "借方"],
            "贷方调整金额": ["贷方金额", "贷方"],
            "调整事项说明": ["摘要", "说明"],
            "科目代码": ["科目编码"],
            "索引": ["索引号", "交叉索引"],
        },
        "guidance": [
            "H1-3 固定资产调整分录汇总表 编制说明",
            "",
            "类别填：账项调整（影响审定数）/ 报表调整（重分类，仅列报）/ 其他。",
            "仅列示与固定资产相关的审计调整；借方合计应等于贷方合计。",
            "索引交叉引用 H1-7/H1-8/H1-12/H1-14 等来源底稿。",
        ],
    },
    "H1-7": {
        "item_id": "H1-7-rows",
        "title": "H1-7 固定资产增加检查表",
        "headers": _H1_7_HEADERS,
        "field_keys": _H1_7_KEYS,
        "allow_missing_headers": True,
        "header_aliases": {
            "资产名称": ["固定资产名称", "名称"],
            "资产编号": ["固定资产编号", "编号"],
            "增加日期": ["入账日期", "取得日期"],
            "增加方式": ["取得方式", "来源"],
            "验收单号": ["验收单", "验收凭证号"],
            "合同编号": ["合同", "合同/协议/订单"],
            "发票号": ["发票", "采购发票"],
            "费用/资本化": ["资本化判断", "资本化"],
            "检查结果": ["审计结论", "结果"],
        },
        "guidance": [
            "H1-7 增加检查 编制说明",
            "",
            "编制逻辑：审计目标 → 样本选取 → 测试过程（账面+关键证据）→ 检查比例 → 说明/结论。",
            "净值=原值-累计折旧-减值准备；检查比例=样本原值合计/本期增加固定资产合计。",
            "本期增加合计优先从 H1-2 原值本期增加带入，无则回退 H1-1 原值借方。",
            "检查比例偏低时扩大样本或在审计说明中解释；在建转入须关注验收与暂估折旧。",
            "增加方式：外购/在建工程转入/更新改造/盘盈/融资租赁/投资者投入/非货币交换/债务重组/企业合并/其他。",
            "本表含账→证抽查与证→账追查（H1-7-trace-rows）；完整性结合盘点综合判断。",
            "按增加方式填写专项勾选清单；暂估转固须填折旧起算日并联动 H1-12。",
            "关联方=是 的行可带入 H1-18；关注虚高计价输送利益等舞弊风险。",
        ],
    },
    "H1-8": {
        "item_id": "H1-8-rows",
        "title": "H1-8 固定资产减少检查表",
        "headers": _H1_8_HEADERS,
        "field_keys": _H1_8_KEYS,
        "guidance": [
            "H1-8 减少检查 编制说明",
            "",
            "编制逻辑：审计目标 → 测试原因 → 抽样 → 样本明细（转入清理勾稽+关键证据）→ 检查比例 → 说明/结论。",
            "净值=原值-累计折旧-减值准备；清理净损益=清理收入-净值-清理费用。",
            "检查比例=样本原值合计/本期减少固定资产合计；偏低时扩大样本或在审计说明中解释。",
            "减少方式：出售/报废/损毁/捐赠/盘亏/其他；关联方出售须关注评估定价。",
            "对方科目多为1606固定资产清理，处置结果联动H10资产处置损益。",
        ],
    },
    "H1-10": {
        "item_id": "H1-10-rows",
        "title": "H1-10 盘点检查表",
        "headers": _H1_10_HEADERS,
        "field_keys": _H1_10_KEYS,
        "allow_missing_headers": True,
        "header_aliases": {
            "账面金额": ["账面原值", "原值", "账面金额(原值)"],
            "资产名称": ["固定资产名称", "名称"],
            "资产编号": ["固定资产编号", "编号"],
            "企业盘点数量": ["企业盘点", "企业盘点记录数量"],
            "抽盘数量": ["审计抽盘", "实盘数量", "抽盘"],
            "品质状况": ["实际状态", "成色评估", "品质"],
            "盘点结果": ["结果", "抽盘结果"],
            "盘点人": ["监盘人", "检查人"],
            "抽盘方向": ["方向", "测试方向"],
            "差异原因": ["差异说明"],
        },
        "guidance": [
            "H1-10 固定资产盘点检查表 编制说明",
            "",
            "抽盘方向：bookToFloor（账面→实物，测存在）/ floorToBook（实物→账面，测完整）。",
            "亦可填中文：账面→实物 / 实物→账面。",
            "三数量：账面数量、企业盘点数量、审计抽盘数量；差异由系统自动计算。",
            "盘点结果：账实相符/盘盈/盘亏（可由抽盘−账面自动推导）。",
            "品质状况：正常/闲置/毁损/待报废；闲置毁损将推送 H1-4/H1-14 线索。",
            "样本与过程元数据（测试总体、原值合计等）在系统内「H1-10-meta」维护，不在本表。",
            "兼容旧模板：账面原值→账面金额、实际状态→品质状况等别名可导入。",
        ],
    },
    "H1-11": {
        "item_id": "H1-11-form",
        "title": "H1-11 监盘小结（归档扁平行）",
        "headers": ["分区", "字段", "值"],
        "field_keys": ["section", "field", "value"],
        "guidance": [
            "H1-11 固定资产监盘小结 编制/导出说明",
            "",
            "按「了解→盘前→现场→分类复盘→统计→结论」结构编制。",
            "仪表板与复盘统计联动 H1-10；计划样本量对照 H1-9。",
            "导出 JSON/本表扁平行便于归档签字；HTML 端支持附件 OCR 确认回写。",
            "权证 OCR 可同步预填 H1-16；闲置/报废可推送 H1-4 / H1-14。",
        ],
    },
    "H1-16": {
        "item_id": "H1-16-rows",
        "title": "H1-16 房屋建筑物权属检查表",
        "headers": _H1_16_HEADERS,
        "field_keys": _H1_16_KEYS,
        "guidance": [
            "H1-16 房屋建筑物权属检查表 编制说明",
            "",
            "三区结构：财务账面记录 → 权证记载 → 抵押情况。",
            "净值=原值-累计折旧-减值准备；与 H1-2 房屋建筑物明细勾稽。",
            "未办证在建转固单独列示（转固日/预计办证日/办证进度）。",
            "行级 📎 可上传权证扫描件 OCR 预填（仅填空）。",
            "权利人非被审计单位时标记权属异常；抵押房产须核对附注受限资产披露。",
            "每次审计须重新取得权证原件并与复印件核对。",
        ],
    },
    "H1-18": {
        "item_id": "H1-18-rows",
        "title": "H1-18 关联交易检查表",
        "headers": _H1_18_HEADERS,
        "field_keys": _H1_18_KEYS,
        "guidance": [
            "H1-18 关联交易检查表 编制说明",
            "",
            "仅登记合并范围外关联方固定资产购入/出售/无偿调拨。",
            "出售时净值=原值−累计折旧−减值准备；价格差异率=(交易价−公允价)/公允价×100%。",
            "交易方向取值：购入 / 出售 / 无偿调拨。",
        ],
    },
    "H1-19": {
        "item_id": "H1-19-rows",
        "title": "H1-19 经营租出固定资产检查表",
        "headers": _H1_19_HEADERS,
        "field_keys": _H1_19_KEYS,
        "guidance": [
            "H1-19 经营租出 编制说明",
            "",
            "月租金=年租金/12；租赁净收益=总租金-折旧-维修费。",
            "收益率=净收益/原值×100%。",
        ],
    },
    "H1-12": {
        "item_id": "H1-12-rows",
        # 导入同时写入 A 分支键；导出优先活动/分支键再回退共享键
        "mirror_item_ids": ["H1-12-A-rows"],
        "item_id_candidates": [
            "H1-12-A-rows",
            "H1-12-B-rows",
            "H1-12-C-rows",
            "H1-12-rows",
        ],
        "title": "H1-12 折旧测算（企业固定资产台账）",
        "headers": _H1_12_HEADERS,
        "field_keys": _H1_12_KEYS,
        "guidance": [
            "H1-12 折旧测算一键导入模板",
            "",
            "填写企业固定资产台账关键列后导入；系统按减值情况自动推荐：",
            "  A 不含减值直线法 / B 含减值 / C 多次减值。",
            "残值率可填 0.05 或 5（百分数）；开始使用日期格式 YYYY-MM-DD。",
            "CAS/税法：投入使用次月起提折旧。",
            "也可在前端直接用企业导出的原始表（表头别名自动映射）一键导入测算。",
            "导入将写入 H1-12-rows 与 H1-12-A-rows（分支隔离）。",
        ],
    },
}

router = create_cycle_import_export_router(tag="h1-import-export", api_prefix="h1", specs=_H1_SPECS)
