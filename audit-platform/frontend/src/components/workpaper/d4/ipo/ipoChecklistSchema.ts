/**
 * ipoChecklistSchema.ts — D4-25/26/27/28 IPO 检查表列规格单一真源
 *
 * 本文件是四张 IPO 检查表的唯一结构真源：
 * - 列规格（key/label/group/type/options/width/derived/seqColumn）
 * - 公式预设（IPO_FORMULA_PRESETS）
 * - 投影纯函数（rowsToSheet / sheetToRows）
 * - 派生集合（CHECKBOX_COLUMNS / DERIVED_COLUMNS）
 *
 * 🔴 四个 .vue 组件禁止定义公式常量，只引用本模块。
 * 🔴 key 用稳定标识（禁 label，会撞键）。
 * 🔴 label 与源模板表头单元格逐字一致（含全角标点与顿号）。
 * 🔴 与后端 _SHEET_HEADERS[sheet] 摊平后逐列一致。
 */

// ═══════════════════════════════════════════════════════════════════════
// 接口定义
// ═══════════════════════════════════════════════════════════════════════

export interface ChecklistColumnSpec {
  /** 稳定 key，禁 label（会撞键） */
  key: string
  /** 中文 label，与源模板表头单元格逐字一致 */
  label: string
  /** 父组（两级表头），无父组为 null */
  group: string | null
  /** 列类型 */
  type: 'text' | 'number' | 'amount' | 'percent' | 'select' | 'checkbox'
  /** type='select' 专用选项 */
  options?: readonly string[]
  /** 列宽（el-table-column width/min-width） */
  width?: number
  /** 表内计算派生列（禁手填） */
  derived?: boolean
  /** 序号列（由 seq 派生，不参与投影） */
  seqColumn?: boolean
}

export interface ChecklistSheetSpec {
  sheetCode: 'D4-25' | 'D4-26' | 'D4-27' | 'D4-28'
  /** 源 xlsx tab 全名（OO sheet-name 用，必须与源模板完全一致） */
  sheetName: string
  /** 表头行号 */
  headerRows: number[]
  /** 数据区首行 */
  dataStartRow: number
  /** 结论/审计说明区锚点单元格 */
  noteAnchor?: string
  /** 列规格 */
  columns: readonly ChecklistColumnSpec[]
}

// ═══════════════════════════════════════════════════════════════════════
// D4-25 经销商检查 — 13 列，单级表头，headerRows=[11]，dataStartRow=12
// ═══════════════════════════════════════════════════════════════════════

const D4_25_COLUMNS: readonly ChecklistColumnSpec[] = [
  { key: 'seq', label: '序号', group: null, type: 'number', width: 55, seqColumn: true },
  { key: 'customerName', label: '客户名称', group: null, type: 'text', width: 120 },
  { key: 'dealer', label: '经销商', group: null, type: 'text', width: 100 },
  { key: 'salesQty', label: '本期销售数量', group: null, type: 'number', width: 100 },
  { key: 'salesAmount', label: '本期销售金额', group: null, type: 'amount', width: 120 },
  { key: 'salesRatio', label: '占同类交易比例', group: null, type: 'percent', width: 100, derived: true },
  { key: 'arBalance', label: '期末应收账款余额', group: null, type: 'amount', width: 120 },
  { key: 'isRelated', label: '是否关联方', group: null, type: 'select', width: 85, options: ['是', '否'] },
  { key: 'entityType', label: '个人/企业', group: null, type: 'select', width: 85, options: ['个人', '企业'] },
  { key: 'expenseBearer', label: '销售费用承担方式', group: null, type: 'text', width: 110 },
  { key: 'subsidy', label: '补贴或返利', group: null, type: 'select', width: 85, options: ['是', '否'] },
  { key: 'terminalSalesAmount', label: '终端销售金额', group: null, type: 'amount', width: 120 },
  { key: 'remark', label: '备注', group: null, type: 'text', width: 100 },
] as const

// ═══════════════════════════════════════════════════════════════════════
// D4-26 境外销售收入检查 — 19 列（14 主列 + 5 二级列），两级表头
// headerRows=[11,12]，dataStartRow=13
// 父组「核查程序执行情况」跨 O~S 5 列
// ═══════════════════════════════════════════════════════════════════════

const D4_26_COLUMNS: readonly ChecklistColumnSpec[] = [
  { key: 'customerName', label: '客户名称', group: null, type: 'text', width: 110 },
  { key: 'country', label: '所在国家/地区', group: null, type: 'text', width: 100 },
  { key: 'productType', label: '产品种类', group: null, type: 'text', width: 100 },
  { key: 'bizModel', label: '业务模式', group: null, type: 'select', width: 90, options: ['直销客户', '经销商'] },
  { key: 'salesAmount', label: '本期销售金额', group: null, type: 'amount', width: 120 },
  { key: 'salesRatio', label: '占同类交易比例', group: null, type: 'percent', width: 100, derived: true },
  { key: 'tradeMode', label: '贸易模式', group: null, type: 'select', width: 80, options: ['EXW', 'FOB', 'CIF'] },
  { key: 'tradeTerms', label: '主要贸易条款', group: null, type: 'text', width: 110 },
  { key: 'settlementMode', label: '出口结算模式', group: null, type: 'select', width: 100, options: ['汇款', '托收', '信用证', '银行保函'] },
  { key: 'hasThirdParty', label: '是否存在第三方回款', group: null, type: 'select', width: 100, options: ['是', '否'] },
  { key: 'thirdPartyReason', label: '第三方回款原因', group: null, type: 'text', width: 110 },
  { key: 'verifiedAmount', label: '核查程序确认的销售金额', group: null, type: 'amount', width: 130 },
  { key: 'diff', label: '差异', group: null, type: 'amount', width: 100, derived: true },
  { key: 'diffReason', label: '差异原因分析', group: null, type: 'text', width: 110 },
  // 二级列：父组「核查程序执行情况」
  { key: 'fieldVisit', label: '实地走访', group: '核查程序执行情况', type: 'checkbox', width: 60 },
  { key: 'tradeConfirm', label: '交易函证', group: '核查程序执行情况', type: 'checkbox', width: 60 },
  { key: 'customsConfirm', label: '海关函证', group: '核查程序执行情况', type: 'checkbox', width: 60 },
  { key: 'checkDeclaration', label: '核对报关单', group: '核查程序执行情况', type: 'checkbox', width: 70 },
  { key: 'eportQuery', label: '电子口岸数据查询', group: '核查程序执行情况', type: 'checkbox', width: 80 },
] as const

// ═══════════════════════════════════════════════════════════════════════
// D4-27 识别未披露的关联方 — 18 列，单级表头，headerRows=[14]，dataStartRow=15
// ═══════════════════════════════════════════════════════════════════════

const D4_27_COLUMNS: readonly ChecklistColumnSpec[] = [
  { key: 'seq', label: '序号', group: null, type: 'number', width: 50, seqColumn: true },
  { key: 'personName', label: '姓名', group: null, type: 'text', width: 90 },
  { key: 'personalCustomer', label: '个人客户', group: null, type: 'checkbox', width: 55 },
  { key: 'customerLegalPerson', label: '客户法人', group: null, type: 'checkbox', width: 55 },
  { key: 'contractSignee', label: '合同签订人', group: null, type: 'checkbox', width: 60 },
  { key: 'executiveRelative', label: '高管亲属', group: null, type: 'checkbox', width: 55 },
  { key: 'financeDept', label: '财务部门', group: null, type: 'checkbox', width: 55 },
  { key: 'managementDept', label: '管理部门', group: null, type: 'checkbox', width: 55 },
  { key: 'techDept', label: '技术部门', group: null, type: 'checkbox', width: 55 },
  { key: 'productionDept', label: '生产部门', group: null, type: 'checkbox', width: 55 },
  { key: 'salesDept', label: '营销部门', group: null, type: 'checkbox', width: 55 },
  { key: 'otherDept', label: '其他', group: null, type: 'checkbox', width: 45 },
  { key: 'total', label: '总计', group: null, type: 'number', width: 50, derived: true },
  { key: 'isMatch', label: '重名(Y/N)', group: null, type: 'select', width: 65, options: ['Y', 'N'] },
  { key: 'identity', label: '公司股东/高管/亲属/员工', group: null, type: 'text', width: 110 },
  { key: 'annualSales', label: '年度销售额', group: null, type: 'amount', width: 100 },
  { key: 'note', label: '说明', group: null, type: 'text', width: 100 },
  { key: 'indexRef', label: '索引号', group: null, type: 'text', width: 70 },
] as const

// ═══════════════════════════════════════════════════════════════════════
// D4-28 客户信息核查清单 — 15 列（10 主列 + 5 二级列），两级表头
// headerRows=[12,13]，dataStartRow=14
// 父组「核查方式（√）」跨 J~N 5 列
// ═══════════════════════════════════════════════════════════════════════

const D4_28_COLUMNS: readonly ChecklistColumnSpec[] = [
  { key: 'seq', label: '序号', group: null, type: 'number', width: 50, seqColumn: true },
  { key: 'customerName', label: '客户名称', group: null, type: 'text', width: 110 },
  { key: 'reason', label: '选取原因', group: null, type: 'text', width: 100 },
  { key: 'salesAmount', label: '销售金额', group: null, type: 'amount', width: 100 },
  { key: 'salesRatio', label: '占总交易比重', group: null, type: 'percent', width: 80, derived: true },
  { key: 'arBalance', label: '应收账款期末余额', group: null, type: 'amount', width: 110 },
  { key: 'arRatio', label: '占期末余额比重', group: null, type: 'percent', width: 80, derived: true },
  { key: 'contractLiability', label: '合同负债期末余额', group: null, type: 'amount', width: 110 },
  { key: 'clRatio', label: '占期末余额比重', group: null, type: 'percent', width: 80, derived: true },
  // 二级列：父组「核查方式（√）」
  { key: 'checkBiz', label: '工商资料查询', group: '核查方式（√）', type: 'checkbox', width: 55 },
  { key: 'checkInternet', label: '互联网信息查询', group: '核查方式（√）', type: 'checkbox', width: 60 },
  { key: 'checkConfirm', label: '函证', group: '核查方式（√）', type: 'checkbox', width: 45 },
  { key: 'checkCall', label: '视频电话访谈', group: '核查方式（√）', type: 'checkbox', width: 60 },
  { key: 'checkVisit', label: '实地走访', group: '核查方式（√）', type: 'checkbox', width: 55 },
  { key: 'indexRef', label: '索引号', group: null, type: 'text', width: 70 },
] as const

// ═══════════════════════════════════════════════════════════════════════
// SHEET_SPECS — 四张表规格汇总
// ═══════════════════════════════════════════════════════════════════════

export const SHEET_SPECS: Record<string, ChecklistSheetSpec> = {
  'D4-25': {
    sheetCode: 'D4-25',
    sheetName: '经销商检查D4-25',
    headerRows: [11],
    dataStartRow: 12,
    noteAnchor: 'A23',
    columns: D4_25_COLUMNS,
  },
  'D4-26': {
    sheetCode: 'D4-26',
    sheetName: '境外销售收入检查D4-26',
    headerRows: [11, 12],
    dataStartRow: 13,
    columns: D4_26_COLUMNS,
  },
  'D4-27': {
    sheetCode: 'D4-27',
    sheetName: '识别未披露的关联方D4-27',
    headerRows: [14],
    dataStartRow: 15,
    columns: D4_27_COLUMNS,
  },
  'D4-28': {
    sheetCode: 'D4-28',
    sheetName: '客户信息核查清单D4-28',
    headerRows: [12, 13],
    dataStartRow: 14,
    noteAnchor: 'A25',
    columns: D4_28_COLUMNS,
  },
}

// ═══════════════════════════════════════════════════════════════════════
// 公式真源 — IPO_FORMULA_PRESETS（14 条）
// 🔴 四个 .vue 组件内零公式字面量，只引用本处。
// 🔴 禁止自造披露内容：预设公式只覆盖源模板已有列与审计常识口径。
// ═══════════════════════════════════════════════════════════════════════

export interface IpoFormulaPreset {
  sheetCode: 'D4-25' | 'D4-26' | 'D4-27' | 'D4-28'
  /** 行定位：'*' = 全部行 */
  rowKey: '*' | string
  /** 目标列 key（必须在该 sheet 列规格内） */
  columnKey: string
  category: 'inter_sheet' | 'intra_sheet'
  /** category=inter_sheet 时必填，后端 resolver 名 */
  resolver?: string
  /** category=intra_sheet 时必填，引用 $col 表示本表列 */
  expression?: string
  /** 依赖列 key */
  dependsOn: readonly string[]
  precision: number
  /** 源 xlsx 单元格或审计依据，禁止留空 */
  sourceRef: string
  /** 一句中文说明 */
  reason: string
}

export const IPO_FORMULA_PRESETS: readonly IpoFormulaPreset[] = [
  // ─── D4-25 经销商检查 ───────────────────────────────────────
  {
    sheetCode: 'D4-25', rowKey: '*', columnKey: 'salesAmount',
    category: 'inter_sheet', resolver: 'd4_25_dealer_sales',
    dependsOn: ['customerName'], precision: 2,
    sourceRef: '经销商检查D4-25!E11 + D4-2 收入明细',
    reason: '本期销售金额从 D4-2 收入明细按客户名称匹配提取',
  },
  {
    sheetCode: 'D4-25', rowKey: '*', columnKey: 'arBalance',
    category: 'inter_sheet', resolver: 'd4_25_dealer_sales',
    dependsOn: ['customerName'], precision: 2,
    sourceRef: '经销商检查D4-25!G11 + D2-2 客户账龄',
    reason: '期末应收账款余额从 D2-2 客户账龄按客户名称匹配提取',
  },
  {
    sheetCode: 'D4-25', rowKey: '*', columnKey: 'salesRatio',
    category: 'intra_sheet',
    expression: "'$salesAmount' / SUM($salesAmount)",
    dependsOn: ['salesAmount'], precision: 4,
    sourceRef: '经销商检查D4-25!F11',
    reason: '占同类交易比例 = 该行本期销售金额 / 全部行本期销售金额合计',
  },
  // ─── D4-26 境外销售收入检查 ────────────────────────────────────
  {
    sheetCode: 'D4-26', rowKey: '*', columnKey: 'salesAmount',
    category: 'inter_sheet', resolver: 'd4_26_overseas_sales',
    dependsOn: ['customerName'], precision: 2,
    sourceRef: '境外销售收入检查D4-26!E11',
    reason: '本期销售金额从境外销售明细按客户名称匹配提取',
  },
  {
    sheetCode: 'D4-26', rowKey: '*', columnKey: 'diff',
    category: 'intra_sheet',
    expression: "'$verifiedAmount' - '$salesAmount'",
    dependsOn: ['verifiedAmount', 'salesAmount'], precision: 2,
    sourceRef: '境外销售收入检查D4-26!M11',
    reason: '差异 = 核查程序确认的销售金额 − 本期销售金额',
  },
  {
    sheetCode: 'D4-26', rowKey: '*', columnKey: 'salesRatio',
    category: 'intra_sheet',
    expression: "'$salesAmount' / SUM($salesAmount)",
    dependsOn: ['salesAmount'], precision: 4,
    sourceRef: '境外销售收入检查D4-26!F11',
    reason: '占同类交易比例 = 该行本期销售金额 / 全部行本期销售金额合计',
  },
  // ─── D4-27 识别未披露的关联方 ──────────────────────────────────
  {
    sheetCode: 'D4-27', rowKey: '*', columnKey: 'annualSales',
    category: 'inter_sheet', resolver: 'd4_27_related_party_sales',
    dependsOn: ['personName'], precision: 2,
    sourceRef: '识别未披露的关联方D4-27!P14',
    reason: '年度销售额从客户维度销售明细按姓名/客户法人匹配提取',
  },
  {
    sheetCode: 'D4-27', rowKey: '*', columnKey: 'total',
    category: 'intra_sheet',
    expression: 'SUM($personalCustomer,$customerLegalPerson,$contractSignee,$executiveRelative,$financeDept,$managementDept,$techDept,$productionDept,$salesDept,$otherDept)',
    dependsOn: [
      'personalCustomer', 'customerLegalPerson', 'contractSignee', 'executiveRelative',
      'financeDept', 'managementDept', 'techDept', 'productionDept', 'salesDept', 'otherDept',
    ],
    precision: 0,
    sourceRef: '识别未披露的关联方D4-27!M15=SUM(C15:L15)',
    reason: '总计 = 10 个身份属性列勾选数之和（与源模板公式口径一致）',
  },
  // ─── D4-28 客户信息核查清单 ────────────────────────────────────
  {
    sheetCode: 'D4-28', rowKey: '*', columnKey: 'salesAmount',
    category: 'inter_sheet', resolver: 'd4_28_customer_balances',
    dependsOn: ['customerName'], precision: 2,
    sourceRef: '客户信息核查清单D4-28!D12',
    reason: '销售金额从 D4-2 收入明细按客户名称匹配提取',
  },
  {
    sheetCode: 'D4-28', rowKey: '*', columnKey: 'arBalance',
    category: 'inter_sheet', resolver: 'd4_28_customer_balances',
    dependsOn: ['customerName'], precision: 2,
    sourceRef: '客户信息核查清单D4-28!F12',
    reason: '应收账款期末余额从 D2-2 客户账龄按客户名称匹配提取',
  },
  {
    sheetCode: 'D4-28', rowKey: '*', columnKey: 'contractLiability',
    category: 'inter_sheet', resolver: 'd4_28_customer_balances',
    dependsOn: ['customerName'], precision: 2,
    sourceRef: '客户信息核查清单D4-28!H12',
    reason: '合同负债期末余额从合同负债明细按客户名称匹配提取',
  },
  {
    sheetCode: 'D4-28', rowKey: '*', columnKey: 'salesRatio',
    category: 'intra_sheet',
    expression: "'$salesAmount' / SUM($salesAmount)",
    dependsOn: ['salesAmount'], precision: 4,
    sourceRef: '客户信息核查清单D4-28!E12',
    reason: '占总交易比重 = 销售金额 / 销售金额合计',
  },
  {
    sheetCode: 'D4-28', rowKey: '*', columnKey: 'arRatio',
    category: 'intra_sheet',
    expression: "'$arBalance' / SUM($arBalance)",
    dependsOn: ['arBalance'], precision: 4,
    sourceRef: '客户信息核查清单D4-28!G12',
    reason: '占期末余额比重 = 应收账款期末余额 / 应收账款期末余额合计',
  },
  {
    sheetCode: 'D4-28', rowKey: '*', columnKey: 'clRatio',
    category: 'intra_sheet',
    expression: "'$contractLiability' / SUM($contractLiability)",
    dependsOn: ['contractLiability'], precision: 4,
    sourceRef: '客户信息核查清单D4-28!I12',
    reason: '合同负债占比 = 合同负债期末余额 / 合同负债期末余额合计',
  },
] as const

// ═══════════════════════════════════════════════════════════════════════
// 派生集合
// ═══════════════════════════════════════════════════════════════════════

/** 按 sheetCode 获取 checkbox 列 key 集合 */
export function getCheckboxColumns(sheetCode: string): Set<string> {
  const spec = SHEET_SPECS[sheetCode]
  if (!spec) return new Set()
  return new Set(spec.columns.filter(c => c.type === 'checkbox').map(c => c.key))
}

/** 按 sheetCode 获取 derived 列 key 集合 */
export function getDerivedColumns(sheetCode: string): Set<string> {
  const spec = SHEET_SPECS[sheetCode]
  if (!spec) return new Set()
  return new Set(spec.columns.filter(c => c.derived).map(c => c.key))
}

/** 所有 checkbox 列（跨四表） */
export const CHECKBOX_COLUMNS: ReadonlySet<string> = new Set(
  Object.values(SHEET_SPECS).flatMap(s => s.columns.filter(c => c.type === 'checkbox').map(c => c.key))
)

/** 所有 derived 列（跨四表） */
export const DERIVED_COLUMNS: ReadonlySet<string> = new Set(
  Object.values(SHEET_SPECS).flatMap(s => s.columns.filter(c => c.derived).map(c => c.key))
)

// ═══════════════════════════════════════════════════════════════════════
// 投影纯函数
// ═══════════════════════════════════════════════════════════════════════

/** checkbox 值 → boolean */
export function parseCheckboxValue(val: unknown): boolean {
  if (val === true || val === 1 || val === '1' || val === 'Y' || val === '是' || val === 'true') return true
  return false
}

/** boolean → OO checkbox 值 */
export function toBoolCellValue(val: boolean): number | null {
  return val ? 1 : null
}

/** 安全解析数值，失败返回 null（禁写 NaN） */
export function parseNumericValue(val: unknown): number | null {
  if (val === null || val === undefined || val === '') return null
  if (typeof val === 'number') return Number.isFinite(val) ? val : null
  const s = String(val).replace(/,/g, '').replace(/%$/, '')
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}

export interface RowRecord {
  rowId: string
  [key: string]: unknown
}

/**
 * OO sheet 数据区 → rows 行记录数组
 *
 * - 只读 dataStartRow 之后；按列号取值
 * - 跳过 seqColumn
 * - 全空行跳过（不产生幽灵空行）
 * - checkbox: 1/true/Y/是 → true
 * - number/amount/percent: 非数字 → null（禁写 NaN）
 */
export function sheetToRows(
  getCellValue: (row: number, col: number) => unknown,
  maxRow: number,
  spec: ChecklistSheetSpec
): RowRecord[] {
  const dataCols = spec.columns.filter(c => !c.seqColumn)
  const results: RowRecord[] = []

  for (let r = spec.dataStartRow; r <= maxRow && results.length < 500; r++) {
    const record: RowRecord = { rowId: `row-${r}` }
    let hasValue = false

    dataCols.forEach((col, colIdx) => {
      // 列号从 1 开始；如果有 seqColumn 它占第一列（A），数据列从 B 开始
      const seqCols = spec.columns.filter(c => c.seqColumn).length
      const excelCol = seqCols + colIdx + 1
      const raw = getCellValue(r, excelCol)

      if (col.type === 'checkbox') {
        const v = parseCheckboxValue(raw)
        record[col.key] = v
        if (v) hasValue = true
      } else if (col.type === 'number' || col.type === 'amount' || col.type === 'percent') {
        const v = parseNumericValue(raw)
        record[col.key] = v
        if (v !== null) hasValue = true
      } else {
        const v = raw != null && String(raw).trim() !== '' ? String(raw).trim() : null
        record[col.key] = v
        if (v !== null) hasValue = true
      }
    })

    // 全空行跳过
    if (hasValue) {
      results.push(record)
    }
  }

  return results
}

/**
 * rows 行记录数组 → OO sheet 数据区写入指令
 *
 * 返回 [row, col, value][] 用于批量写入 OO
 * - 行按 seq 升序写入 dataStartRow 起
 * - checkbox → 1；null → 空单元格
 * - amount 写数值不写格式化字符串
 * - 保留表头行不改
 */
export function rowsToSheet(
  rows: RowRecord[],
  spec: ChecklistSheetSpec
): Array<[number, number, unknown]> {
  const dataCols = spec.columns.filter(c => !c.seqColumn)
  const seqCols = spec.columns.filter(c => c.seqColumn).length
  const commands: Array<[number, number, unknown]> = []

  rows.forEach((row, rowIdx) => {
    const excelRow = spec.dataStartRow + rowIdx

    // 序号列
    if (seqCols > 0) {
      commands.push([excelRow, 1, rowIdx + 1])
    }

    dataCols.forEach((col, colIdx) => {
      const excelCol = seqCols + colIdx + 1
      const val = row[col.key]

      if (col.type === 'checkbox') {
        commands.push([excelRow, excelCol, toBoolCellValue(val === true)])
      } else if (val === null || val === undefined || val === '') {
        commands.push([excelRow, excelCol, null])
      } else {
        commands.push([excelRow, excelCol, val])
      }
    })
  })

  return commands
}

/**
 * 摊平列规格 label 序列（用于与后端 _SHEET_HEADERS 比对）
 * 两级表头的子列按位置展开（父组 label 不出现在摊平序列中）
 */
export function flattenLabels(spec: ChecklistSheetSpec): string[] {
  return spec.columns.map(c => c.label)
}

/**
 * 获取列的命名字段 key（新增行时用 ElMessageBox.prompt 输入的字段）
 */
export function getNameFieldKey(sheetCode: string): string {
  switch (sheetCode) {
    case 'D4-25': return 'customerName'
    case 'D4-26': return 'customerName'
    case 'D4-27': return 'personName'
    case 'D4-28': return 'customerName'
    default: return 'customerName'
  }
}

/**
 * 获取新增行时的 prompt 标题
 */
export function getAddRowPromptTitle(sheetCode: string): string {
  switch (sheetCode) {
    case 'D4-25': return '添加经销商记录'
    case 'D4-26': return '添加境外客户'
    case 'D4-27': return '添加人员'
    case 'D4-28': return '添加核查客户'
    default: return '添加记录'
  }
}

/**
 * 获取新增行时的 prompt 输入提示
 */
export function getAddRowInputLabel(sheetCode: string): string {
  switch (sheetCode) {
    case 'D4-25': return '请输入客户名称'
    case 'D4-26': return '请输入客户名称'
    case 'D4-27': return '请输入姓名'
    case 'D4-28': return '请输入客户名称'
    default: return '请输入名称'
  }
}

/**
 * 创建空行记录（只有 rowId 和 nameField 有值，其余按列类型初始化）
 */
export function createEmptyRow(sheetCode: string, nameValue: string): RowRecord {
  const spec = SHEET_SPECS[sheetCode]
  if (!spec) throw new Error(`Unknown sheetCode: ${sheetCode}`)
  const row: RowRecord = {
    rowId: `${sheetCode.toLowerCase()}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
  }
  const nameField = getNameFieldKey(sheetCode)
  for (const col of spec.columns) {
    if (col.seqColumn) continue
    if (col.key === nameField) {
      row[col.key] = nameValue
    } else if (col.type === 'checkbox') {
      row[col.key] = false
    } else if (col.type === 'number' || col.type === 'amount' || col.type === 'percent') {
      row[col.key] = null
    } else {
      row[col.key] = ''
    }
  }
  return row
}
