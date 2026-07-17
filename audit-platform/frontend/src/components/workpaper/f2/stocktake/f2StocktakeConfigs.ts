/** F2-21~26 监盘 sheet 配置 — 文本模块优先，表格仅用于 F2-24/25/26 明细 */

export interface StocktakeSectionField {
  id: string
  label: string
  indent?: boolean
  isSection?: boolean
  /** 多行叙述（程序说明、差异分析等） */
  multiline?: boolean
  /** 日期选择器（存 YYYY-MM-DD） */
  date?: boolean
  /** 占满整行（问卷/结论类） */
  fullWidth?: boolean
  /** placeholder / 副提示 */
  hint?: string
  /** textarea 默认行数 */
  rows?: number
}

/** F2-22 卡片分区布局 */
export interface F2PlanLayoutGroup {
  id: string
  title: string
  subtitle?: string
  cols: 1 | 2 | 3
  fieldIds: string[]
}

export const F2_22_LAYOUT: F2PlanLayoutGroup[] = [
  { id: 'meta', title: '文首信息', subtitle: '被审计单位与报告日', cols: 3, fieldIds: ['entityName', 'auditYear', 'bsDate'] },
  { id: 'boundary', title: '一～四 · 目标与边界', subtitle: '目的 → 范围裁剪 → 地点 → 时间', cols: 2, fieldIds: ['purpose', 'scope', 'warehouses', 'countDate'] },
  { id: 'team', title: '五 · 参与人员及分工', subtitle: '人 ↔ 地点配对', cols: 2, fieldIds: ['auditors', 'clientStaff', 'assignment'] },
  { id: 'prep', title: '六 · 监盘前准备', subtitle: '程序准备 + 构成分析', cols: 2, fieldIds: ['prep', 'inventoryComposition'] },
  { id: 'method', title: '七～八 · 方式与要求', subtitle: '主盘/监盘/抽盘 · 覆盖率与取证', cols: 2, fieldIds: ['countMethod', 'requirements'] },
  { id: 'risk', title: '九 · 特别关注', cols: 3, fieldIds: ['remoteWarehouse', 'fraudRisk', 'expertNeeded'] },
  { id: 'sign', title: '落款', cols: 2, fieldIds: ['teamName', 'planDate'] },
]

/** F2-21 盘点计划问卷 — 底稿为 d-form-confirmation 长文本问卷，地点表并入叙述字段 */
export const F2_21_FIELDS: StocktakeSectionField[] = [
  { id: 'header-basic', label: '基本信息', isSection: true },
  { id: 'entity', label: '被审计单位', indent: true },
  { id: 'auditYear', label: '审计期间', indent: true },
  { id: 'header-schedule', label: '盘点时间与通知', isSection: true },
  { id: 'notifyClient', label: '是否已通知被审计单位盘点时间', indent: true },
  { id: 'countSchedule', label: '各监盘地点、存货类型、占比及盘点时间安排', indent: true, multiline: true, fullWidth: true },
  { id: 'header-scope', label: '盘点范围', isSection: true },
  { id: 'warehouses', label: '监盘仓库/地点清单', indent: true, multiline: true, fullWidth: true },
  { id: 'inventoryTypes', label: '存货类型覆盖（原材料/在产品/产成品等）', indent: true, multiline: true, fullWidth: true },
  { id: 'coveragePct', label: '监盘金额/数量占存货总额比例', indent: true },
  { id: 'header-method', label: '盘点方法与程序', isSection: true },
  { id: 'countMethod', label: '全面盘点/循环盘点/抽盘等安排', indent: true, multiline: true, fullWidth: true },
  { id: 'prepProcedure', label: '盘前准备（盘点表编号、截止控制）', indent: true, multiline: true, fullWidth: true },
  { id: 'header-team', label: '人员安排', isSection: true },
  { id: 'auditors', label: '项目组监盘人员', indent: true, multiline: true, fullWidth: true },
  { id: 'clientStaff', label: '被审计单位盘点负责人及陪同人员', indent: true, multiline: true, fullWidth: true },
  { id: 'header-risk', label: '风险与特殊考虑', isSection: true },
  { id: 'remoteWarehouse', label: '异地仓库/第三方代管存货', indent: true, multiline: true, fullWidth: true },
  { id: 'fraudRisk', label: '舞弊风险及是否不预先通知监盘', indent: true, multiline: true, fullWidth: true },
  { id: 'expertNeeded', label: '是否需要专家（贵金属/化学品等）', indent: true, multiline: true, fullWidth: true },
]

/** F2-22 对齐 G2-6-2：认定→范围裁剪→人点匹配→构成分析→方法与覆盖率→取证 */
export const F2_22_FIELDS: StocktakeSectionField[] = [
  { id: 'header-meta', label: '文首信息', isSection: true },
  { id: 'entityName', label: '被审计单位' },
  { id: 'auditYear', label: '审计年度' },
  { id: 'bsDate', label: '资产负债表日', date: true, hint: '选择报告日' },
  { id: 'header-purpose', label: '一、监盘目的', isSection: true },
  { id: 'purpose', label: '监盘目的', hint: '存在 / 权属 / 账实相符 / 品质与跌价', multiline: true, fullWidth: true, rows: 3 },
  { id: 'header-scope', label: '二、监盘范围', isSection: true },
  { id: 'scope', label: '监盘范围', hint: '含不纳入本次监盘的裁剪说明', multiline: true, fullWidth: true, rows: 3 },
  { id: 'header-place', label: '三、监盘地点', isSection: true },
  { id: 'warehouses', label: '监盘地点', hint: '仓库 / 车间清单', multiline: true, fullWidth: true, rows: 2 },
  { id: 'header-time', label: '四、监盘时间', isSection: true },
  { id: 'countDate', label: '监盘时间', hint: '与客户协商的起止安排', multiline: true, fullWidth: true, rows: 2 },
  { id: 'header-team', label: '五、参与人员及分工', isSection: true },
  { id: 'auditors', label: '项目组监盘人员', multiline: true, rows: 2 },
  { id: 'clientStaff', label: '被审计单位配合人员', multiline: true, rows: 2 },
  { id: 'assignment', label: '分工安排', hint: '人 ↔ 地点配对', multiline: true, fullWidth: true, rows: 3 },
  { id: 'header-prep', label: '六、监盘前准备工作', isSection: true },
  { id: 'prep', label: '准备工作', hint: '索取盘点计划 / 人员就位 / 检查盘点准备', multiline: true, fullWidth: true, rows: 3 },
  { id: 'inventoryComposition', label: '存货构成分析', hint: '类别占比与存放分布，支撑重点监盘', multiline: true, fullWidth: true, rows: 4 },
  { id: 'header-method', label: '七、监盘方式', isSection: true },
  { id: 'countMethod', label: '监盘方式', hint: '客户主盘 + 事务所监盘/抽盘；视频监盘须专项说明', multiline: true, fullWidth: true, rows: 3 },
  { id: 'header-req', label: '八、监盘要求', isSection: true },
  { id: 'requirements', label: '监盘要求', hint: '纪律 / 品质 / 抽盘覆盖率 / 取证与报告', multiline: true, fullWidth: true, rows: 3 },
  { id: 'header-risk', label: '九、特别关注事项', isSection: true },
  { id: 'remoteWarehouse', label: '异地 / 代管', multiline: true, rows: 2 },
  { id: 'fraudRisk', label: '舞弊风险', multiline: true, rows: 2 },
  { id: 'expertNeeded', label: '专家需求', multiline: true, rows: 2 },
  { id: 'header-sign', label: '落款', isSection: true },
  { id: 'teamName', label: '项目组署名' },
  { id: 'planDate', label: '计划编制日期', date: true, hint: '选择编制日期' },
]

/** F2-23 卡片分区 — 对齐 G2-6-1 / 源模板「存货监盘小结」 */
export const F2_23_LAYOUT: F2PlanLayoutGroup[] = [
  { id: 'meta', title: '文首信息', subtitle: '被审计单位与报告日', cols: 3, fieldIds: ['entityName', 'auditYear', 'bsDate'] },
  { id: 'boundary', title: '一～四 · 目的与边界', subtitle: '目的 → 范围裁剪 → 地点 → 时间', cols: 2, fieldIds: ['purpose', 'scope', 'warehouses', 'countDate'] },
  { id: 'team', title: '五 · 参与人员及分工', subtitle: '客户盘点人 + 项目组分地点安排', cols: 2, fieldIds: ['clientStaff', 'auditors', 'assignment'] },
  { id: 'method', title: '六 · 公司存货盘点方法', subtitle: '永续盘存 / 实地盘存等', cols: 1, fieldIds: ['countMethod'] },
  { id: 'summary', title: '七 · 监盘情况汇总', subtitle: '过程概述与抽盘覆盖；未结账时可暂空金额', cols: 2, fieldIds: ['processOverview', 'inventoryTotal', 'sampleAmount', 'samplePct', 'coverageNote'] },
  { id: 'detail', title: '八 · 具体监盘情况', subtitle: '分地点结果；可引用各分厂抽盘表', cols: 1, fieldIds: ['resultByLocation'] },
  { id: 'conclusion', title: '九 · 监盘结论', cols: 1, fieldIds: ['overallConclusion', 'followUp'] },
  { id: 'sign', title: '落款', cols: 2, fieldIds: ['teamName', 'summaryDate'] },
]

/** F2-23 对齐 G2-6-1：目的→范围→地点→时间→分工→盘点方法→汇总→分地点→结论 */
export const F2_23_FIELDS: StocktakeSectionField[] = [
  { id: 'header-meta', label: '文首信息', isSection: true },
  { id: 'entityName', label: '被审计单位' },
  { id: 'auditYear', label: '审计年度' },
  { id: 'bsDate', label: '资产负债表日', date: true, hint: '选择报告日' },
  { id: 'header-purpose', label: '一、监盘目的', isSection: true },
  { id: 'purpose', label: '监盘目的', hint: '存在 / 权属 / 账实相符 / 品质与跌价', multiline: true, fullWidth: true, rows: 4 },
  { id: 'header-scope', label: '二、监盘范围', isSection: true },
  { id: 'scope', label: '监盘范围', hint: '含不纳入本次监盘的分/子公司说明', multiline: true, fullWidth: true, rows: 3 },
  { id: 'header-place', label: '三、监盘地点', isSection: true },
  { id: 'warehouses', label: '监盘地点', hint: '各分厂仓库 / 车间 / 子公司', multiline: true, fullWidth: true, rows: 2 },
  { id: 'header-time', label: '四、监盘时间', isSection: true },
  { id: 'countDate', label: '监盘时间', hint: '与客户协商的起止安排', multiline: true, fullWidth: true, rows: 2 },
  { id: 'header-team', label: '五、参与人员及分工', isSection: true },
  { id: 'clientStaff', label: '被审计单位盘点人员', hint: '仓管 / 物资管理 / 财务监督等', multiline: true, rows: 2 },
  { id: 'auditors', label: '项目组监盘人员', multiline: true, rows: 2 },
  { id: 'assignment', label: '分工安排', hint: '人 ↔ 地点配对（如：张三→工业园）', multiline: true, fullWidth: true, rows: 4 },
  { id: 'header-method', label: '六、公司存货盘点方法', isSection: true },
  { id: 'countMethod', label: '盘点方法', hint: '永续盘存制 / 实地盘存；类别差异说明', multiline: true, fullWidth: true, rows: 4 },
  { id: 'header-summary', label: '七、监盘情况汇总', isSection: true },
  { id: 'processOverview', label: '监盘过程概述', hint: '观察盘点、抽盘范围、重点仓库', multiline: true, fullWidth: true, rows: 5 },
  { id: 'inventoryTotal', label: '存货总额（万元）', hint: '未结账可暂空' },
  { id: 'sampleAmount', label: '抽盘金额（万元）', hint: '未结账可暂空' },
  { id: 'samplePct', label: '抽盘占比（%）' },
  { id: 'coverageNote', label: '覆盖率说明', hint: '如：因期末未结账金额暂不确定', multiline: true, fullWidth: true, rows: 2 },
  { id: 'header-detail', label: '八、具体监盘情况', isSection: true },
  { id: 'resultByLocation', label: '分地点监盘结果', hint: '按分厂逐条：主要存货、差异、抽盘表索引', multiline: true, fullWidth: true, rows: 12 },
  { id: 'header-conclusion', label: '九、监盘结论', isSection: true },
  { id: 'overallConclusion', label: '监盘总体结论', hint: '管理规范性、重大差异、账实相符评价', multiline: true, fullWidth: true, rows: 4 },
  { id: 'followUp', label: '需进一步跟进事项', multiline: true, fullWidth: true, rows: 2 },
  { id: 'header-sign', label: '落款', isSection: true },
  { id: 'teamName', label: '项目组署名' },
  { id: 'summaryDate', label: '小结编制日期', date: true, hint: '选择编制日期' },
]

/** F2-24 核对说明（表前叙述，底稿 static_text 5~7 行） */
export const F2_24_NARRATIVE_FIELDS: StocktakeSectionField[] = [
  { id: 'header', label: '核对说明', isSection: true },
  { id: 'purpose', label: '核对目的', indent: true, multiline: true, fullWidth: true },
  { id: 'bookSource', label: '账面余额数据来源', indent: true, multiline: true, fullWidth: true },
  { id: 'erpSource', label: '仓储台账/ERP 数据来源', indent: true, multiline: true, fullWidth: true },
  { id: 'method', label: '核对方法与差异处理', indent: true, multiline: true, fullWidth: true },
]

/** F2-24 对齐源模板：文首 + 双向核对说明 + 双时点 */
export const F2_24_FIELDS: StocktakeSectionField[] = [
  { id: 'header-meta', label: '文首信息', isSection: true },
  { id: 'entityName', label: '被审计单位' },
  { id: 'cutoffDate', label: '截止日（资产负债表日）', date: true, hint: '选择报告日' },
  { id: 'countDate', label: '监盘/盘点日', date: true, hint: '与截止日不同时需填第二节' },
  { id: 'header-method', label: '核对方法', isSection: true },
  { id: 'purpose', label: '核对目的', hint: '账面 ↔ 仓储台账双向核对，支撑存在性/完整性', multiline: true, fullWidth: true, rows: 2 },
  { id: 'bookSource', label: '账面余额数据来源', hint: '总账/明细账/结账报表', multiline: true, rows: 2 },
  { id: 'erpSource', label: '仓储台账/ERP 来源', hint: 'ERP 库存、卡片、收发存', multiline: true, rows: 2 },
  { id: 'method', label: '核对方法与差异处理', hint: '双向核对；大数据量可借助 IT 审计', multiline: true, fullWidth: true, rows: 3 },
  { id: 'header-bs', label: '一、资产负债表日核对', isSection: true },
  { id: 'bsNote', label: '资产负债表日核对说明', hint: '范围、抽样、重大差异概述', multiline: true, fullWidth: true, rows: 2 },
  { id: 'header-count', label: '二、盘点日核对（条件）', isSection: true },
  { id: 'countDiffers', label: '盘点日是否异于截止日', hint: '填「是」或「否」' },
  { id: 'countNote', label: '盘点日核对说明', hint: '仅盘点日≠截止日时填写', multiline: true, fullWidth: true, rows: 2 },
]

export const F2_24_LAYOUT: F2PlanLayoutGroup[] = [
  { id: 'meta', title: '文首信息', subtitle: '被审计单位与时点', cols: 3, fieldIds: ['entityName', 'cutoffDate', 'countDate'] },
  { id: 'method', title: '核对方法', subtitle: '收发存明细账 ↔ 仓储台账（ERP）↔ 卡片 · 双向核对', cols: 2, fieldIds: ['purpose', 'bookSource', 'erpSource', 'method'] },
]

/** F2-25 抽盘概况（表前叙述，底稿 static_text 5~13 行） */
export const F2_25_NARRATIVE_FIELDS: StocktakeSectionField[] = [
  { id: 'header', label: '抽盘概况', isSection: true },
  { id: 'sampleBasis', label: '样本选取依据（重要性/风险/类别）', indent: true, multiline: true, fullWidth: true },
  { id: 'locations', label: '抽盘仓库/车间', indent: true, multiline: true, fullWidth: true },
  { id: 'countSheetRange', label: '盘点表编号范围', indent: true, multiline: true, fullWidth: true },
]

/** F2-25 对齐源模板：目标认定 + 过程元数据 + 双向抽盘 */
export const F2_25_FIELDS: StocktakeSectionField[] = [
  { id: 'header-meta', label: '文首信息', isSection: true },
  { id: 'entityName', label: '被审计单位' },
  { id: 'cutoffDate', label: '截止日', date: true, hint: '资产负债表日' },
  { id: 'header-process', label: '审计过程', isSection: true },
  { id: 'warehouseName', label: '仓库名称', hint: '本次抽盘仓库/车间' },
  { id: 'countTime', label: '盘点时间', hint: '现场盘点起止时间' },
  { id: 'auditors', label: '监盘人员', hint: '项目组签字人' },
  { id: 'clientStaff', label: '盘点人员', hint: '仓管/财务陪同' },
  { id: 'sampleBasis', label: '样本选取依据', hint: '重要性/风险/类别', multiline: true, fullWidth: true, rows: 2 },
]

export const F2_25_LAYOUT: F2PlanLayoutGroup[] = [
  { id: 'meta', title: '文首信息', cols: 2, fieldIds: ['entityName', 'cutoffDate'] },
  { id: 'process', title: '二、审计过程', subtitle: '仓库 · 时间 · 人员', cols: 2, fieldIds: ['warehouseName', 'countTime', 'auditors', 'clientStaff', 'sampleBasis'] },
]

/** F2-26 文首与调节说明 */
export const F2_26_FIELDS: StocktakeSectionField[] = [
  { id: 'header-meta', label: '文首信息', isSection: true },
  { id: 'entityName', label: '被审计单位' },
  { id: 'bsDate', label: '资产负债表日（截止日）', date: true, hint: '通常为报告期末' },
  { id: 'countDate', label: '监盘/盘点日', date: true, hint: '与截止日比较决定填哪一节' },
  { id: 'header-method', label: '调节说明', isSection: true },
  {
    id: 'method',
    label: '倒轧方法与收发核对说明',
    hint: '说明期间收发抽样、单据索引；盘点日≠截止日时必填对应节次',
    multiline: true,
    fullWidth: true,
    rows: 3,
  },
]

export const F2_26_LAYOUT: F2PlanLayoutGroup[] = [
  { id: 'meta', title: '文首信息', subtitle: '时点决定填「日后倒推」或「日前顺推」', cols: 3, fieldIds: ['entityName', 'bsDate', 'countDate'] },
  { id: 'method', title: '调节说明', cols: 1, fieldIds: ['method'] },
]

/** @deprecated 兼容旧叙述字段定义 */
export const F2_26_NARRATIVE_FIELDS = F2_26_FIELDS

export interface StocktakeReconcileRow {
  id: string
  itemName: string
  spec: string
  bookQty: number
  bookAmount: number
  erpQty: number
  erpAmount: number
  remark: string
}

/** F2-25 抽盘行：账面 / 企业盘点 / 审计抽盘 三数量 */
export interface StocktakeSampleRow {
  id: string
  itemCode: string
  itemName: string
  spec: string
  unit: string
  unitPrice: number
  bookQty: number
  bookAmount: number
  clientCountQty: number
  sampleQty: number
  /** 品质：正常 / 毁损 / 呆滞 / 过期 等 */
  qualityStatus: string
  varianceReason: string
  remark: string
}

/**
 * F2-26 倒轧行。
 * inboundQty / outboundQty 始终表示期间「入库 / 发出」实物量；
 * 日后表：D = A + 发出 − 入库；日前表：D = A + 入库 − 发出。
 */
export interface StocktakeRollforwardRow {
  id: string
  category: string
  itemCode: string
  itemName: string
  spec: string
  unit: string
  unitPrice: number
  warehouse: string
  /** A 盘点日实存数量 */
  countDayQty: number
  /** 期间入库数量 */
  inboundQty: number
  /** 期间发出数量 */
  outboundQty: number
  /** E 资产负债表日账面数量 */
  bookQty: number
  /** H 差异原因 */
  varianceReason: string
  /** I 是否调整：是 / 否 */
  needAdjust: string
  remark: string
}

/** 倒轧方向：after=截止日后盘点（倒推）；before=截止日前盘点（顺推） */
export type StocktakeRollMode = 'after' | 'before'
