/**
 * D4 IPO 检查表（D4-25/26/27/28）列规格 + 公式真源 + 投影纯函数 —— 唯一结构真源。
 *
 * spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 2 · Task 4/6/9
 *
 * 🔴 唯一真源：四个 .vue 组件只读本模块，禁止各自定义列数组/公式字面量。
 * 🔴 label 序列逐列 == 后端 `_SHEET_HEADERS[sheet]`（导入导出锚点，三向守卫钉死，
 *    见 backend/tests/test_ipo_checklist_column_contract.py）。
 * 🔴 列 label 与源模板表头单元格逐列一致（含全角标点，归一化规则见守卫）。
 *    源模板真源 = backend/wp_templates/D/D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx。
 *
 * 数值来自 openpyxl 实测复算而非预期：D4-25=13 / D4-26=19(14主+5子) / D4-27=18 / D4-28=15(9主+5子+索引号)。
 */

export type ChecklistColumnType =
  | 'text'
  | 'number'
  | 'amount'
  | 'percent'
  | 'select'
  | 'checkbox'

export interface ChecklistColumnSpec {
  /** 稳定 key，禁用 label（会撞键）。投影/公式/覆盖全部按 key。 */
  key: string
  /** 中文 label，与源模板表头单元格逐字一致（归一化后 == 后端 _SHEET_HEADERS）。 */
  label: string
  /** 父组（两级表头），无父组为 null。 */
  group: string | null
  type: ChecklistColumnType
  /** type='select' 专用点选项。 */
  options?: readonly string[]
  width?: number
  /** 表内计算派生列（默认只读，禁手填；手填后锁定为手填值）。 */
  derived?: boolean
  /** 序号列（由 seq 派生，不参与投影）。 */
  seqColumn?: boolean
}

export interface ChecklistSheetSpec {
  sheetCode: 'D4-25' | 'D4-26' | 'D4-27' | 'D4-28'
  /** 源 xlsx tab 全名（OO sheet-name 用，必须逐字一致）。 */
  sheetName: string
  /** 表头行号（1-based）。单级 [n]，两级 [main, sub]。 */
  headerRows: number[]
  /** 数据区首行（1-based）。 */
  dataStartRow: number
  /** 结论/审计说明区锚点单元格（可选）。 */
  noteAnchor?: string
  /** 新增行必须先输入的命名字段 key（ElMessageBox.prompt）。 */
  nameColumnKey: string
  columns: readonly ChecklistColumnSpec[]
}

// ── D4-25 经销商检查（单级表头 row11，13 列）─────────────────────────────────
const D4_25_COLUMNS: readonly ChecklistColumnSpec[] = [
  { key: 'seq', label: '序号', group: null, type: 'number', width: 55, seqColumn: true },
  { key: 'customerName', label: '客户名称', group: null, type: 'text', width: 130 },
  { key: 'dealer', label: '经销商', group: null, type: 'text', width: 100 },
  { key: 'salesQty', label: '本期销售数量', group: null, type: 'number', width: 100 },
  { key: 'salesAmount', label: '本期销售金额', group: null, type: 'amount', width: 120 },
  { key: 'proportion', label: '占同类交易比例', group: null, type: 'percent', width: 110, derived: true },
  { key: 'arBalance', label: '期末应收账款余额', group: null, type: 'amount', width: 130 },
  { key: 'isRelated', label: '是否关联方', group: null, type: 'select', options: ['是', '否'], width: 90 },
  { key: 'entityType', label: '个人/企业', group: null, type: 'select', options: ['个人', '企业'], width: 90 },
  { key: 'expenseBearer', label: '销售费用承担方式', group: null, type: 'text', width: 120 },
  { key: 'subsidy', label: '补贴或返利', group: null, type: 'select', options: ['是', '否'], width: 100 },
  { key: 'terminalSalesAmount', label: '终端销售金额', group: null, type: 'amount', width: 120 },
  { key: 'remark', label: '备注', group: null, type: 'text', width: 120 },
]

// ── D4-26 境外销售收入检查（两级表头 row11/12，14 主 + 5 子）──────────────────
const D4_26_PROGRAM_GROUP = '核查程序执行情况'
const D4_26_COLUMNS: readonly ChecklistColumnSpec[] = [
  { key: 'customerName', label: '客户名称', group: null, type: 'text', width: 130 },
  { key: 'country', label: '所在国家/地区', group: null, type: 'text', width: 110 },
  { key: 'productType', label: '产品种类', group: null, type: 'text', width: 100 },
  { key: 'businessMode', label: '业务模式', group: null, type: 'select', options: ['直销客户', '经销商'], width: 110 },
  { key: 'salesAmount', label: '本期销售金额', group: null, type: 'amount', width: 120 },
  { key: 'proportion', label: '占同类交易比例', group: null, type: 'percent', width: 110, derived: true },
  { key: 'tradeMode', label: '贸易模式', group: null, type: 'select', options: ['EXW', 'FOB', 'CIF'], width: 100 },
  { key: 'tradeTerms', label: '主要贸易条款', group: null, type: 'text', width: 130 },
  { key: 'settlementMode', label: '出口结算模式', group: null, type: 'select', options: ['汇款', '托收', '信用证', '银行保函'], width: 120 },
  { key: 'hasThirdPartyPayment', label: '是否存在第三方回款', group: null, type: 'select', options: ['是', '否'], width: 120 },
  { key: 'thirdPartyReason', label: '第三方回款原因', group: null, type: 'text', width: 130 },
  { key: 'confirmedSalesAmount', label: '核查程序确认的销售金额', group: null, type: 'amount', width: 150 },
  { key: 'difference', label: '差异', group: null, type: 'amount', width: 110, derived: true },
  { key: 'differenceReason', label: '差异原因分析', group: null, type: 'text', width: 130 },
  // 5 二级列（父组「核查程序执行情况」，源 xlsx O12:S12）
  { key: 'checkFieldVisit', label: '实地走访', group: D4_26_PROGRAM_GROUP, type: 'checkbox', width: 80 },
  { key: 'checkTransConfirm', label: '交易函证', group: D4_26_PROGRAM_GROUP, type: 'checkbox', width: 80 },
  { key: 'checkCustomsConfirm', label: '海关函证', group: D4_26_PROGRAM_GROUP, type: 'checkbox', width: 80 },
  { key: 'checkDeclaration', label: '核对报关单', group: D4_26_PROGRAM_GROUP, type: 'checkbox', width: 90 },
  { key: 'checkEportData', label: '电子口岸数据查询', group: D4_26_PROGRAM_GROUP, type: 'checkbox', width: 110 },
]

// ── D4-27 识别未披露的关联方（单级表头 row14，18 列，含 10 身份属性 checkbox）───
const D4_27_COLUMNS: readonly ChecklistColumnSpec[] = [
  { key: 'seq', label: '序号', group: null, type: 'number', width: 55, seqColumn: true },
  { key: 'name', label: '姓名', group: null, type: 'text', width: 110 },
  { key: 'isPersonalCustomer', label: '个人客户', group: null, type: 'checkbox', width: 80 },
  { key: 'isCustomerLegal', label: '客户法人', group: null, type: 'checkbox', width: 80 },
  { key: 'isContractSigner', label: '合同签订人', group: null, type: 'checkbox', width: 90 },
  { key: 'isExecRelative', label: '高管亲属', group: null, type: 'checkbox', width: 80 },
  { key: 'isFinanceDept', label: '财务部门', group: null, type: 'checkbox', width: 80 },
  { key: 'isMgmtDept', label: '管理部门', group: null, type: 'checkbox', width: 80 },
  { key: 'isTechDept', label: '技术部门', group: null, type: 'checkbox', width: 80 },
  { key: 'isProductionDept', label: '生产部门', group: null, type: 'checkbox', width: 80 },
  { key: 'isMarketingDept', label: '营销部门', group: null, type: 'checkbox', width: 80 },
  { key: 'isOther', label: '其他', group: null, type: 'checkbox', width: 70 },
  { key: 'total', label: '总计', group: null, type: 'number', width: 70, derived: true },
  { key: 'isDuplicateName', label: '重名(Y/N)', group: null, type: 'select', options: ['Y', 'N'], width: 90 },
  { key: 'shareholderExecRelative', label: '公司股东/高管/亲属/员工', group: null, type: 'text', width: 150 },
  { key: 'annualSales', label: '年度销售额', group: null, type: 'amount', width: 120 },
  { key: 'note', label: '说明', group: null, type: 'text', width: 150 },
  { key: 'indexNo', label: '索引号', group: null, type: 'text', width: 90 },
]

// ── D4-28 客户信息核查清单（两级表头 row12/13，9 主 + 5 子 + 索引号）────────────
const D4_28_METHOD_GROUP = '核查方式（√）'
const D4_28_COLUMNS: readonly ChecklistColumnSpec[] = [
  { key: 'seq', label: '序号', group: null, type: 'number', width: 55, seqColumn: true },
  { key: 'customerName', label: '客户名称', group: null, type: 'text', width: 130 },
  { key: 'selectionReason', label: '选取原因', group: null, type: 'text', width: 130 },
  { key: 'salesAmount', label: '销售金额', group: null, type: 'amount', width: 120 },
  { key: 'salesProportion', label: '占总交易比重', group: null, type: 'percent', width: 100, derived: true },
  { key: 'arBalance', label: '应收账款期末余额', group: null, type: 'amount', width: 130 },
  { key: 'arProportion', label: '占期末余额比重', group: null, type: 'percent', width: 110, derived: true },
  { key: 'contractLiabBalance', label: '合同负债期末余额', group: null, type: 'amount', width: 130 },
  { key: 'contractLiabProportion', label: '占期末余额比重', group: null, type: 'percent', width: 110, derived: true },
  // 5 二级列（父组「核查方式（√）」，源 xlsx J13:N13）
  { key: 'methodBusinessInfo', label: '工商资料查询', group: D4_28_METHOD_GROUP, type: 'checkbox', width: 100 },
  { key: 'methodInternet', label: '互联网信息查询', group: D4_28_METHOD_GROUP, type: 'checkbox', width: 110 },
  { key: 'methodConfirmation', label: '函证', group: D4_28_METHOD_GROUP, type: 'checkbox', width: 70 },
  { key: 'methodInterview', label: '视频、电话访谈', group: D4_28_METHOD_GROUP, type: 'checkbox', width: 100 },
  { key: 'methodFieldVisit', label: '实地走访', group: D4_28_METHOD_GROUP, type: 'checkbox', width: 80 },
  { key: 'indexNo', label: '索引号', group: null, type: 'text', width: 90 },
]

export const SHEET_SPECS: Record<string, ChecklistSheetSpec> = {
  'D4-25': {
    sheetCode: 'D4-25',
    sheetName: '经销商检查D4-25',
    headerRows: [11],
    dataStartRow: 12,
    noteAnchor: 'A23',
    nameColumnKey: 'customerName',
    columns: D4_25_COLUMNS,
  },
  'D4-26': {
    sheetCode: 'D4-26',
    sheetName: '境外销售收入检查D4-26',
    headerRows: [11, 12],
    dataStartRow: 13,
    nameColumnKey: 'customerName',
    columns: D4_26_COLUMNS,
  },
  'D4-27': {
    sheetCode: 'D4-27',
    sheetName: '识别未披露的关联方D4-27',
    headerRows: [14],
    dataStartRow: 15,
    nameColumnKey: 'name',
    columns: D4_27_COLUMNS,
  },
  'D4-28': {
    sheetCode: 'D4-28',
    sheetName: '客户信息核查清单D4-28',
    headerRows: [12, 13],
    dataStartRow: 14,
    noteAnchor: 'A25',
    nameColumnKey: 'customerName',
    columns: D4_28_COLUMNS,
  },
}

/** checkbox 列 key 集合（投影 1↔true 转换用）。 */
export const CHECKBOX_COLUMNS: Record<string, readonly string[]> = Object.fromEntries(
  Object.entries(SHEET_SPECS).map(([code, spec]) => [
    code,
    spec.columns.filter((c) => c.type === 'checkbox').map((c) => c.key),
  ]),
)

/** 派生列 key 集合（表内计算，默认只读）。 */
export const DERIVED_COLUMNS: Record<string, readonly string[]> = Object.fromEntries(
  Object.entries(SHEET_SPECS).map(([code, spec]) => [
    code,
    spec.columns.filter((c) => c.derived).map((c) => c.key),
  ]),
)

// ═══════════════════════════════════════════════════════════════════════════
// 行记录类型：{ rowId, seq, ...columns.map(key) }
// ═══════════════════════════════════════════════════════════════════════════
export type ChecklistRow = Record<string, unknown> & { rowId: string; seq: number }

// ── 投影值转换 ───────────────────────────────────────────────────────────────
function truthyCheckbox(v: unknown): boolean {
  if (v === true) return true
  if (typeof v === 'number') return v === 1
  const s = String(v ?? '').trim()
  return s === '1' || s === 'true' || s === 'Y' || s === 'y' || s === '是' || s === '√'
}

/**
 * 解析数值单元格：非数字（含 `12.3%`）→ 按数值解析，失败 → null（禁写 NaN）。
 * 百分比文本 `12.3%` → 0.123。
 */
function parseNumeric(v: unknown): number | null {
  if (v == null || v === '') return null
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  let s = String(v).trim().replace(/,/g, '')
  if (s === '') return null
  let pct = false
  if (s.endsWith('%')) {
    pct = true
    s = s.slice(0, -1)
  }
  const n = Number(s)
  if (!Number.isFinite(n)) return null
  return pct ? n / 100 : n
}

/**
 * rows → OO sheet 数据区二维数组（按列规格顺序，逐行）。
 * - 行按 seq 升序
 * - checkbox → 1（与源模板口径一致）；false/空 → null（空单元格，不写占位文本）
 * - amount/number/percent 写数值不写格式化串
 * - seqColumn 写序号（1-based 由 seq 派生）
 */
export function rowsToSheet(rows: ChecklistRow[], spec: ChecklistSheetSpec): unknown[][] {
  const sorted = [...rows].sort((a, b) => (Number(a.seq) || 0) - (Number(b.seq) || 0))
  return sorted.map((row, idx) =>
    spec.columns.map((col) => {
      if (col.seqColumn) return idx + 1
      const v = row[col.key]
      if (col.type === 'checkbox') return truthyCheckbox(v) ? 1 : null
      if (col.type === 'amount' || col.type === 'number' || col.type === 'percent') {
        const n = parseNumeric(v)
        return n
      }
      return v == null || v === '' ? null : v
    }),
  )
}

/**
 * OO sheet 数据区二维数组 → rows。
 * - 全空行跳过（不产生幽灵空行）
 * - seqColumn 不参与投影（由行序派生 seq）
 * - checkbox：1/true/Y/是 → true，其余 → false
 * - number/amount/percent：解析失败 → null（禁写 NaN）
 */
export function sheetToRows(grid: unknown[][], spec: ChecklistSheetSpec): ChecklistRow[] {
  const out: ChecklistRow[] = []
  let seq = 0
  for (const gridRow of grid) {
    // 判空：所有非序号列都为空
    const nonSeqCols = spec.columns.filter((c) => !c.seqColumn)
    const allEmpty = nonSeqCols.every((col) => {
      const raw = gridRow[spec.columns.indexOf(col)]
      return raw == null || String(raw).trim() === ''
    })
    if (allEmpty) continue
    seq += 1
    const row: ChecklistRow = { rowId: `d4-${Date.now().toString(36)}-${seq}`, seq }
    for (let i = 0; i < spec.columns.length; i++) {
      const col = spec.columns[i]
      if (col.seqColumn) continue
      const raw = gridRow[i]
      if (col.type === 'checkbox') {
        row[col.key] = truthyCheckbox(raw)
      } else if (col.type === 'amount' || col.type === 'number' || col.type === 'percent') {
        row[col.key] = parseNumeric(raw)
      } else {
        row[col.key] = raw == null ? '' : String(raw)
      }
    }
    out.push(row)
  }
  return out
}

// ═══════════════════════════════════════════════════════════════════════════
// 公式真源（IPO_FORMULA_PRESETS）—— 唯一公式字面量来源，组件只引用不定义。
//   category='inter_sheet'  → 后端 resolver（Task 7 落地）
//   category='intra_sheet'  → 前端公式引擎（Task 8），expression 引用 $col（列 key）
// source_ref 全部指向源模板实测单元格。
// ═══════════════════════════════════════════════════════════════════════════
export interface IpoFormulaPreset {
  sheetCode: 'D4-25' | 'D4-26' | 'D4-27' | 'D4-28'
  rowKey: '*' | string
  columnKey: string
  category: 'inter_sheet' | 'intra_sheet'
  resolver?: string
  expression?: string
  dependsOn: readonly string[]
  precision: number
  sourceRef: string
  reason: string
}

export const IPO_FORMULA_PRESETS: readonly IpoFormulaPreset[] = [
  // D4-25 经销商检查
  {
    sheetCode: 'D4-25', rowKey: '*', columnKey: 'salesAmount', category: 'inter_sheet',
    resolver: 'd4_25_dealer_sales', dependsOn: ['customerName'], precision: 2,
    sourceRef: '经销商检查D4-25!E11', reason: '按客户名称从 D4-2 收入明细取本期销售金额',
  },
  {
    sheetCode: 'D4-25', rowKey: '*', columnKey: 'arBalance', category: 'inter_sheet',
    resolver: 'd4_25_dealer_sales', dependsOn: ['customerName'], precision: 2,
    sourceRef: '经销商检查D4-25!G11', reason: '按客户名称从 D2-2 客户账龄取期末应收账款余额',
  },
  {
    sheetCode: 'D4-25', rowKey: '*', columnKey: 'proportion', category: 'intra_sheet',
    expression: '$salesAmount / SUM($salesAmount)', dependsOn: ['salesAmount'], precision: 4,
    sourceRef: '经销商检查D4-25!F11', reason: '占同类交易比例 = 本行销售金额 / 全部行合计',
  },
  // D4-26 境外销售收入检查
  {
    sheetCode: 'D4-26', rowKey: '*', columnKey: 'salesAmount', category: 'inter_sheet',
    resolver: 'd4_26_overseas_sales', dependsOn: ['customerName'], precision: 2,
    sourceRef: '境外销售收入检查D4-26!E11', reason: '按客户名称从境外销售明细取本期销售金额',
  },
  {
    sheetCode: 'D4-26', rowKey: '*', columnKey: 'difference', category: 'intra_sheet',
    expression: '$confirmedSalesAmount - $salesAmount', dependsOn: ['confirmedSalesAmount', 'salesAmount'], precision: 2,
    sourceRef: '境外销售收入检查D4-26!M11', reason: '差异 = 核查程序确认的销售金额 − 本期销售金额',
  },
  {
    sheetCode: 'D4-26', rowKey: '*', columnKey: 'proportion', category: 'intra_sheet',
    expression: '$salesAmount / SUM($salesAmount)', dependsOn: ['salesAmount'], precision: 4,
    sourceRef: '境外销售收入检查D4-26!F11', reason: '占同类交易比例 = 本行销售金额 / 全部行合计',
  },
  // D4-27 识别未披露的关联方
  {
    sheetCode: 'D4-27', rowKey: '*', columnKey: 'annualSales', category: 'inter_sheet',
    resolver: 'd4_27_related_party_sales', dependsOn: ['name'], precision: 2,
    sourceRef: '识别未披露的关联方D4-27!P14', reason: '按姓名从客户维度销售明细取年度销售额',
  },
  {
    sheetCode: 'D4-27', rowKey: '*', columnKey: 'total', category: 'intra_sheet',
    expression:
      '$isPersonalCustomer + $isCustomerLegal + $isContractSigner + $isExecRelative + $isFinanceDept + $isMgmtDept + $isTechDept + $isProductionDept + $isMarketingDept + $isOther',
    dependsOn: [
      'isPersonalCustomer', 'isCustomerLegal', 'isContractSigner', 'isExecRelative', 'isFinanceDept',
      'isMgmtDept', 'isTechDept', 'isProductionDept', 'isMarketingDept', 'isOther',
    ],
    precision: 0,
    sourceRef: '识别未披露的关联方D4-27!M15=SUM(C15:L15)', reason: '总计 = 10 个身份属性列勾选数之和（源模板内嵌 =SUM(C15:L15)）',
  },
  // D4-28 客户信息核查清单
  {
    sheetCode: 'D4-28', rowKey: '*', columnKey: 'salesAmount', category: 'inter_sheet',
    resolver: 'd4_28_customer_balances', dependsOn: ['customerName'], precision: 2,
    sourceRef: '客户信息核查清单D4-28!D12', reason: '按客户名称从 D4-2 收入明细取销售金额',
  },
  {
    sheetCode: 'D4-28', rowKey: '*', columnKey: 'arBalance', category: 'inter_sheet',
    resolver: 'd4_28_customer_balances', dependsOn: ['customerName'], precision: 2,
    sourceRef: '客户信息核查清单D4-28!F12', reason: '按客户名称从 D2-2 客户账龄取应收账款期末余额',
  },
  {
    sheetCode: 'D4-28', rowKey: '*', columnKey: 'contractLiabBalance', category: 'inter_sheet',
    resolver: 'd4_28_customer_balances', dependsOn: ['customerName'], precision: 2,
    sourceRef: '客户信息核查清单D4-28!H12', reason: '按客户名称从合同负债明细取合同负债期末余额',
  },
  {
    sheetCode: 'D4-28', rowKey: '*', columnKey: 'salesProportion', category: 'intra_sheet',
    expression: '$salesAmount / SUM($salesAmount)', dependsOn: ['salesAmount'], precision: 4,
    sourceRef: '客户信息核查清单D4-28!E12', reason: '占总交易比重 = 本行销售金额 / 全部行合计',
  },
  {
    sheetCode: 'D4-28', rowKey: '*', columnKey: 'arProportion', category: 'intra_sheet',
    expression: '$arBalance / SUM($arBalance)', dependsOn: ['arBalance'], precision: 4,
    sourceRef: '客户信息核查清单D4-28!G12', reason: '占期末余额比重 = 本行应收账款期末余额 / 全部行合计',
  },
  {
    sheetCode: 'D4-28', rowKey: '*', columnKey: 'contractLiabProportion', category: 'intra_sheet',
    expression: '$contractLiabBalance / SUM($contractLiabBalance)', dependsOn: ['contractLiabBalance'], precision: 4,
    sourceRef: '客户信息核查清单D4-28!I12', reason: '合同负债占比 = 本行合同负债期末余额 / 全部行合计',
  },
]
