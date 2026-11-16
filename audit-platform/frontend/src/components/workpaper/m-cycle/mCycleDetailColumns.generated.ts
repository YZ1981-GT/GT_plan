/**
 * M 循环明细表列元数据 —— **自动生成，勿手改**。
 *
 * 生成器：`backend/scripts/gen/generate_m_cycle_detail_columns.py`
 * 真源：provider 的 `DETAIL_FIELDS` / `DETAIL_SHEET`（模板的单一权威声明）。
 *
 * 🔴 为什么要生成：M3/M5/M7 原先的前端行模型与模板是**两张不同的表**
 * （列集合交集 ≤1），手抄列名必然再次漂移。这里把列清单、两级表头、
 * editable/formula、值类型一次性从 provider 导出，前端只消费不重述。
 */
export interface MCycleDetailField {
  /** 契约列键（stable_field_key 的末段，与模板列语义一致） */
  columnKey: string
  /** 前端 store 键（契约 json_pointer 末段，逐行 JSON 用它） */
  jsonKey: string
  /** 模板列字母 */
  column: string
  /** 叶子表头 */
  header: string
  /** 组表头（空串 = 无上级组） */
  group: string
  /** editable = 可录入；formula = 由 OO 重算，前端只显示 */
  mode: 'editable' | 'formula'
  /** amount / text / rate */
  valueType: string
}

export interface MCycleDetailSheet {
  sheetKey: string
  tableKey: string
  /** 合计行行标签（模板原文） */
  footerMarker: string
  /** 固定数据行的行标签（模板 A 列，空串 = 模板上留白的可填行） */
  rowLabels: string[]
  fields: MCycleDetailField[]
}

export const M_CYCLE_DETAIL_COLUMNS: Record<string, MCycleDetailSheet> = {
  M3: {
    sheetKey: "m301-managed",
    tableKey: "m" + "3_detail_rows",
    footerMarker: "\u5408\u8ba1",
    rowLabels: ["减资回购股份", "奖励员工回购股份", "对合并、分立决议有异议回购股份", "母子公司交叉持股", "", "", "", "", "", ""],
    fields: [
    {"columnKey": "category", "jsonKey": "category", "column": "A", "header": "库存股类别", "group": "", "mode": "editable", "valueType": "text"},
    {"columnKey": "prior_opening", "jsonKey": "priorOpening", "column": "B", "header": "期初数", "group": "未审数", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_increase", "jsonKey": "currentIncrease", "column": "C", "header": "本期增加", "group": "", "mode": "editable", "valueType": "amount"},
    {"columnKey": "decrease_transfer", "jsonKey": "decreaseTransfer", "column": "D", "header": "转让", "group": "本期减少", "mode": "editable", "valueType": "amount"},
    {"columnKey": "decrease_cancel", "jsonKey": "decreaseCancel", "column": "E", "header": "注销", "group": "本期减少", "mode": "editable", "valueType": "amount"},
    {"columnKey": "closing_balance", "jsonKey": "closingBalance", "column": "F", "header": "期末数", "group": "未审数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "prior_adj_aje", "jsonKey": "priorAdjAje", "column": "G", "header": "账项调整", "group": "期初调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "prior_adj_rje", "jsonKey": "priorAdjRje", "column": "H", "header": "重分类调整", "group": "期初调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_aje_increase", "jsonKey": "currentAjeIncrease", "column": "I", "header": "本期增加", "group": "账项调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_aje_decrease", "jsonKey": "currentAjeDecrease", "column": "J", "header": "本期减少", "group": "账项调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_rje_increase", "jsonKey": "currentRjeIncrease", "column": "K", "header": "本期增加", "group": "重分类调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_rje_decrease", "jsonKey": "currentRjeDecrease", "column": "L", "header": "本期减少", "group": "重分类调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "audited_opening", "jsonKey": "auditedOpening", "column": "M", "header": "期初数", "group": "审定数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "audited_increase", "jsonKey": "auditedIncrease", "column": "N", "header": "本期增加", "group": "审定数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "audited_decrease", "jsonKey": "auditedDecrease", "column": "O", "header": "本期减少", "group": "审定数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "audited_closing", "jsonKey": "auditedClosing", "column": "P", "header": "期末数", "group": "审定数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "resolution_ref", "jsonKey": "resolutionRef", "column": "Q", "header": "相关决议索引号", "group": "", "mode": "editable", "valueType": "text"},
    {"columnKey": "accounting_correct", "jsonKey": "accountingCorrect", "column": "R", "header": "相关会计处理是否正确", "group": "", "mode": "editable", "valueType": "text"},
    {"columnKey": "remark", "jsonKey": "remark", "column": "S", "header": "备注", "group": "", "mode": "editable", "valueType": "text"},
    ],
  },
  M5: {
    sheetKey: "m501-managed",
    tableKey: "m" + "5_detail_rows",
    footerMarker: "\u5408\u8ba1",
    rowLabels: ["法定盈余公积", "任意盈余公积", "利润归还投资", "其他"],
    fields: [
    {"columnKey": "item_name", "jsonKey": "itemName", "column": "A", "header": "明细项目", "group": "", "mode": "editable", "valueType": "text"},
    {"columnKey": "prior_opening", "jsonKey": "priorOpening", "column": "B", "header": "期初数", "group": "未审数", "mode": "editable", "valueType": "amount"},
    {"columnKey": "increase_amount", "jsonKey": "increaseAmount", "column": "C", "header": "金额", "group": "本期增加", "mode": "editable", "valueType": "amount"},
    {"columnKey": "increase_method", "jsonKey": "increaseMethod", "column": "D", "header": "增加方式", "group": "本期增加", "mode": "editable", "valueType": "text"},
    {"columnKey": "decrease_amount", "jsonKey": "decreaseAmount", "column": "E", "header": "金额", "group": "本期减少", "mode": "editable", "valueType": "amount"},
    {"columnKey": "decrease_method", "jsonKey": "decreaseMethod", "column": "F", "header": "减少方式", "group": "本期减少", "mode": "editable", "valueType": "text"},
    {"columnKey": "closing_balance", "jsonKey": "closingBalance", "column": "G", "header": "期末数", "group": "未审数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "prior_adj_aje", "jsonKey": "priorAdjAje", "column": "H", "header": "账项调整", "group": "期初调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "prior_adj_rje", "jsonKey": "priorAdjRje", "column": "I", "header": "重分类调整", "group": "期初调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_aje_increase", "jsonKey": "currentAjeIncrease", "column": "J", "header": "本期增加", "group": "账项调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_aje_decrease", "jsonKey": "currentAjeDecrease", "column": "K", "header": "本期减少", "group": "账项调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_rje_increase", "jsonKey": "currentRjeIncrease", "column": "L", "header": "本期增加", "group": "重分类调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_rje_decrease", "jsonKey": "currentRjeDecrease", "column": "M", "header": "本期减少", "group": "重分类调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "audited_opening", "jsonKey": "auditedOpening", "column": "N", "header": "期初数", "group": "审定数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "audited_increase", "jsonKey": "auditedIncrease", "column": "O", "header": "本期增加", "group": "审定数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "audited_decrease", "jsonKey": "auditedDecrease", "column": "P", "header": "本期减少", "group": "审定数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "audited_closing", "jsonKey": "auditedClosing", "column": "Q", "header": "期末数", "group": "审定数", "mode": "formula", "valueType": "amount"},
    ],
  },
  M7: {
    sheetKey: "m701-managed",
    tableKey: "m" + "7_detail_rows",
    footerMarker: "\u5408\u8ba1",
    rowLabels: ["安全生产费", "维简费", "其他（请注明）", "", "", "", ""],
    fields: [
    {"columnKey": "project_name", "jsonKey": "projectName", "column": "A", "header": "项目", "group": "", "mode": "editable", "valueType": "text"},
    {"columnKey": "prior_opening", "jsonKey": "priorOpening", "column": "B", "header": "期初数", "group": "未审数", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_increase", "jsonKey": "currentIncrease", "column": "C", "header": "本期增加", "group": "", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_decrease", "jsonKey": "currentDecrease", "column": "D", "header": "本期减少", "group": "", "mode": "editable", "valueType": "amount"},
    {"columnKey": "closing_balance", "jsonKey": "closingBalance", "column": "E", "header": "期末数", "group": "未审数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "prior_adj_aje", "jsonKey": "priorAdjAje", "column": "F", "header": "账项调整", "group": "期初调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "prior_adj_rje", "jsonKey": "priorAdjRje", "column": "G", "header": "重分类调整", "group": "期初调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_aje_increase", "jsonKey": "currentAjeIncrease", "column": "H", "header": "本期增加", "group": "账项调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_aje_decrease", "jsonKey": "currentAjeDecrease", "column": "I", "header": "本期减少", "group": "账项调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_rje_increase", "jsonKey": "currentRjeIncrease", "column": "J", "header": "本期增加", "group": "重分类调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "current_rje_decrease", "jsonKey": "currentRjeDecrease", "column": "K", "header": "本期减少", "group": "重分类调整", "mode": "editable", "valueType": "amount"},
    {"columnKey": "audited_opening", "jsonKey": "auditedOpening", "column": "L", "header": "期初数", "group": "审定数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "audited_increase", "jsonKey": "auditedIncrease", "column": "M", "header": "本期增加", "group": "审定数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "audited_decrease", "jsonKey": "auditedDecrease", "column": "N", "header": "本期减少", "group": "审定数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "audited_closing", "jsonKey": "auditedClosing", "column": "O", "header": "期末数", "group": "审定数", "mode": "formula", "valueType": "amount"},
    {"columnKey": "doc_ref", "jsonKey": "docRef", "column": "P", "header": "文件依据", "group": "", "mode": "editable", "valueType": "text"},
    {"columnKey": "index_ref", "jsonKey": "indexRef", "column": "Q", "header": "索引号", "group": "", "mode": "editable", "valueType": "text"},
    {"columnKey": "remark", "jsonKey": "remark", "column": "R", "header": "备注", "group": "", "mode": "editable", "valueType": "text"},
    ],
  },
}
