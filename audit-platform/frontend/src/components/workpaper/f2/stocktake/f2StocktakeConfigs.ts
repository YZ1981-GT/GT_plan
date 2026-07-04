/** F2-21~26 监盘 sheet 配置 — 文本模块优先，表格仅用于 F2-24/25/26 明细 */

export interface StocktakeSectionField {
  id: string
  label: string
  indent?: boolean
  isSection?: boolean
  /** 多行叙述（程序说明、差异分析等） */
  multiline?: boolean
  /** 占满整行（问卷/结论类） */
  fullWidth?: boolean
}

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

export const F2_22_FIELDS: StocktakeSectionField[] = [
  { id: 'header-info', label: '基本信息', isSection: true },
  { id: 'entity', label: '被审计单位', indent: true },
  { id: 'auditYear', label: '审计年度', indent: true },
  { id: 'countDate', label: '监盘日期', indent: true },
  { id: 'countLocation', label: '监盘地点', indent: true },
  { id: 'header-scope', label: '监盘范围', isSection: true },
  { id: 'warehouses', label: '监盘仓库/地点', indent: true, multiline: true, fullWidth: true },
  { id: 'inventoryTypes', label: '存货类型覆盖', indent: true, multiline: true, fullWidth: true },
  { id: 'coveragePct', label: '占存货总额比例', indent: true },
  { id: 'materiality', label: '选取重要性标准', indent: true },
  { id: 'header-team', label: '监盘团队分工', isSection: true },
  { id: 'partner', label: '项目负责人', indent: true },
  { id: 'observer', label: '盘点观察人员', indent: true },
  { id: 'sampler', label: '抽盘人员', indent: true },
  { id: 'cutoffStaff', label: '截止测试人员', indent: true },
  { id: 'header-procedure', label: '监盘程序要点', isSection: true },
  { id: 'prep', label: '盘前准备（核对盘点表/编号连续性）', indent: true, multiline: true, fullWidth: true },
  { id: 'execution', label: '盘中执行（观察/抽盘/截止）', indent: true, multiline: true, fullWidth: true },
  { id: 'followUp', label: '盘后跟进（倒轧/差异调查）', indent: true, multiline: true, fullWidth: true },
  { id: 'header-risk', label: '特别关注事项', isSection: true },
  { id: 'remoteWarehouse', label: '是否存在异地仓库/第三方代管', indent: true, multiline: true, fullWidth: true },
  { id: 'fraudRisk', label: '是否存在舞弊风险需不预先通知', indent: true, multiline: true, fullWidth: true },
  { id: 'expertNeeded', label: '是否需要专家参与（如贵金属/化学品）', indent: true, multiline: true, fullWidth: true },
]

export const F2_23_FIELDS: StocktakeSectionField[] = [
  { id: 'header-overview', label: '监盘概况', isSection: true },
  { id: 'countDate', label: '监盘日期', indent: true },
  { id: 'countLocation', label: '监盘地点', indent: true },
  { id: 'auditors', label: '监盘人员', indent: true, multiline: true, fullWidth: true },
  { id: 'clientStaff', label: '被审计单位陪同人员', indent: true, multiline: true, fullWidth: true },
  { id: 'header-scope', label: '监盘范围与覆盖率', isSection: true },
  { id: 'totalAmount', label: '盘点存货总金额', indent: true },
  { id: 'sampleCoverage', label: '抽盘金额/覆盖率', indent: true },
  { id: 'sheetRange', label: '盘点表编号范围', indent: true, multiline: true, fullWidth: true },
  { id: 'header-result', label: '监盘结果', isSection: true },
  { id: 'surplus', label: '盘盈数量/金额', indent: true },
  { id: 'shortage', label: '盘亏数量/金额', indent: true },
  { id: 'varianceRate', label: '差异率', indent: true },
  { id: 'varianceReason', label: '差异原因分析', indent: true, multiline: true, fullWidth: true },
  { id: 'header-observation', label: '监盘观察事项', isSection: true },
  { id: 'storageCondition', label: '存货存放状态（整洁/混乱/潮湿等）', indent: true, multiline: true, fullWidth: true },
  { id: 'obsoleteFound', label: '是否发现呆滞/毁损/过期存货', indent: true, multiline: true, fullWidth: true },
  { id: 'consignment', label: '是否存在代管/代销/质押存货', indent: true, multiline: true, fullWidth: true },
  { id: 'orgQuality', label: '盘点组织是否规范（人员/流程/记录）', indent: true, multiline: true, fullWidth: true },
  { id: 'header-cutoff', label: '截止测试', isSection: true },
  { id: 'lastInbound', label: '最后入库单号', indent: true },
  { id: 'lastOutbound', label: '最后出库单号', indent: true },
  { id: 'cutoffAnomaly', label: '截止时点有无异常出入库', indent: true, multiline: true, fullWidth: true },
  { id: 'header-conclusion', label: '总结与后续', isSection: true },
  { id: 'overallConclusion', label: '监盘总体结论', indent: true, multiline: true, fullWidth: true },
  { id: 'followUp', label: '需进一步跟进事项', indent: true, multiline: true, fullWidth: true },
  { id: 'opinionImpact', label: '是否影响审计意见', indent: true, multiline: true, fullWidth: true },
]

/** F2-24 核对说明（表前叙述，底稿 static_text 5~7 行） */
export const F2_24_NARRATIVE_FIELDS: StocktakeSectionField[] = [
  { id: 'header', label: '核对说明', isSection: true },
  { id: 'purpose', label: '核对目的', indent: true, multiline: true, fullWidth: true },
  { id: 'bookSource', label: '账面余额数据来源', indent: true, multiline: true, fullWidth: true },
  { id: 'erpSource', label: '仓储台账/ERP 数据来源', indent: true, multiline: true, fullWidth: true },
  { id: 'method', label: '核对方法与差异处理', indent: true, multiline: true, fullWidth: true },
]

/** F2-25 抽盘概况（表前叙述，底稿 static_text 5~13 行） */
export const F2_25_NARRATIVE_FIELDS: StocktakeSectionField[] = [
  { id: 'header', label: '抽盘概况', isSection: true },
  { id: 'sampleBasis', label: '样本选取依据（重要性/风险/类别）', indent: true, multiline: true, fullWidth: true },
  { id: 'locations', label: '抽盘仓库/车间', indent: true, multiline: true, fullWidth: true },
  { id: 'countSheetRange', label: '盘点表编号范围', indent: true, multiline: true, fullWidth: true },
]

/** F2-26 倒轧说明（表前叙述） */
export const F2_26_NARRATIVE_FIELDS: StocktakeSectionField[] = [
  { id: 'header', label: '倒轧说明', isSection: true },
  { id: 'countDate', label: '监盘日期', indent: true },
  { id: 'bsDate', label: '资产负债表日', indent: true },
  { id: 'method', label: '倒轧公式与调节说明', indent: true, multiline: true, fullWidth: true },
]

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

export interface StocktakeSampleRow {
  id: string
  itemName: string
  spec: string
  unit: string
  bookQty: number
  sampleQty: number
  varianceReason: string
  remark: string
}

export interface StocktakeRollforwardRow {
  id: string
  itemName: string
  countDayQty: number
  inboundQty: number
  outboundQty: number
  theoreticalQty: number
  bookQty: number
  remark: string
}
