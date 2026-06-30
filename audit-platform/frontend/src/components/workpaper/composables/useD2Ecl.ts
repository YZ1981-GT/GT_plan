/**
 * useD2Ecl — ECL合并D2-9 + D2-10核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 9.1
 *
 * 职责：
 * - D2-9 单项ECL：singleRows reactive + singleTotal computed
 * - D2-9 应计提自动计算（= 余额×损失率）+ 差异计算（= 实际-应计提）
 * - D2-9 从D2-3自动获取"期末坏账准备账面余额"
 * - D2-9 从D2-2筛选"单项计提"客户导入（importFromDetail）
 * - D2-10 单项折现区：discountRows + 概率加权计算
 * - D2-10 迁徙率矩阵：migrationMatrix + expectedLossRate连乘
 * - outputLossRates：输出各组合的预期损失率供D2-3引用
 *
 * Requirements: 9.1-9.7, 10.1-10.7
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calculateProvision,
  calculateDifference,
  calculateExpectedLossRate,
} from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

/** D2-9 单项ECL行 (8列) */
export interface EclSingleRow {
  rowId: string
  debtorName: string           // 债务人名称
  auditedBalance: number       // 审定余额
  expectedLossRate: number     // 预期信用损失率
  shouldProvision: number      // 应计提 = balance × rate
  actualBalance: number        // 实际账面余额（从D2-3取）
  difference: number           // 差异 = actual - should
  basis: string                // 计提依据
  indexRef: string             // 索引号
}

/** D2-10 迁徙率矩阵行 */
export interface MigrationRateRow {
  rowId: string
  agingBand: string            // 账龄段
  year1Rate: number            // 第1年迁徙率
  year2Rate: number            // 第2年迁徙率
  year3Rate: number            // 第3年迁徙率
  avgRate: number              // 平均迁徙率 = AVG(year1,year2,year3)
  expectedLossRate: number     // 预期信用损失率 = 连乘
}

/** D2-10 折现法ECL行 */
export interface EclDiscountRow {
  rowId: string
  debtorName: string           // 债务人名称
  balance: number              // 余额
  scenarios: EclScenario[]     // 概率加权场景
  expectedLossRate: number     // 预期损失率 = 1 - ΣPV/balance
  conclusion: string           // 结论
}

/** 折现法概率场景 */
export interface EclScenario {
  scenarioName: string         // 情景名称（乐观/基准/悲观）
  probability: number          // 概率权重
  presentValue: number         // 折现现值
  weighted: number             // 加权 = presentValue × probability
}

// ─── Constants ───────────────────────────────────────────────────────────────

const SINGLE_ROWS_KEY = 'D2-ecl-single-rows'
const DISCOUNT_ROWS_KEY = 'D2-ecl-discount-rows'
const MIGRATION_MATRIX_KEY = 'D2-ecl-migration-matrix'

/** 默认迁徙率矩阵账龄段 */
const DEFAULT_AGING_BANDS = [
  '1年以内',
  '1-2年',
  '2-3年',
  '3-4年',
  '4-5年',
  '5年以上',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `ecl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createEmptySingleRow(): EclSingleRow {
  return {
    rowId: generateRowId(),
    debtorName: '',
    auditedBalance: 0,
    expectedLossRate: 0,
    shouldProvision: 0,
    actualBalance: 0,
    difference: 0,
    basis: '',
    indexRef: '',
  }
}

function createEmptyDiscountRow(): EclDiscountRow {
  return {
    rowId: generateRowId(),
    debtorName: '',
    balance: 0,
    scenarios: [
      { scenarioName: '乐观', probability: 0.25, presentValue: 0, weighted: 0 },
      { scenarioName: '基准', probability: 0.50, presentValue: 0, weighted: 0 },
      { scenarioName: '悲观', probability: 0.25, presentValue: 0, weighted: 0 },
    ],
    expectedLossRate: 0,
    conclusion: '',
  }
}

function createDefaultMigrationMatrix(): MigrationRateRow[] {
  return DEFAULT_AGING_BANDS.map(band => ({
    rowId: generateRowId(),
    agingBand: band,
    year1Rate: 0,
    year2Rate: 0,
    year3Rate: 0,
    avgRate: 0,
    expectedLossRate: 0,
  }))
}

/** 重算单行ECL公式 */
function recalcSingleRow(row: EclSingleRow): EclSingleRow {
  row.shouldProvision = calculateProvision(row.auditedBalance, row.expectedLossRate)
  row.difference = calculateDifference(row.actualBalance, row.shouldProvision)
  return row
}

/** 重算折现行ECL公式 */
function recalcDiscountRow(row: EclDiscountRow): EclDiscountRow {
  // 加权现值
  for (const s of row.scenarios) {
    s.weighted = s.presentValue * s.probability
  }
  const totalPV = row.scenarios.reduce((sum, s) => sum + s.weighted, 0)
  // expectedLossRate = 1 - ΣPV / balance
  row.expectedLossRate = row.balance === 0 ? 0 : 1 - totalPV / row.balance
  return row
}

/** 重算迁徙率矩阵行 */
function recalcMigrationRow(row: MigrationRateRow, subsequentRates: number[]): MigrationRateRow {
  // avgRate = 三年平均
  const rates = [row.year1Rate, row.year2Rate, row.year3Rate].filter(r => r > 0)
  row.avgRate = rates.length > 0 ? rates.reduce((a, b) => a + b, 0) / rates.length : 0
  // expectedLossRate = 本行avgRate × 后续各行avgRate连乘
  const allRates = [row.avgRate, ...subsequentRates]
  row.expectedLossRate = calculateExpectedLossRate(allRates)
  return row
}

function parseSingleRows(jsonStr: string | null | undefined): EclSingleRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => recalcSingleRow({
      rowId: raw.rowId || generateRowId(),
      debtorName: raw.debtorName || '',
      auditedBalance: parseNum(raw.auditedBalance),
      expectedLossRate: parseNum(raw.expectedLossRate),
      shouldProvision: parseNum(raw.shouldProvision),
      actualBalance: parseNum(raw.actualBalance),
      difference: parseNum(raw.difference),
      basis: raw.basis || '',
      indexRef: raw.indexRef || '',
    }))
  } catch {
    return []
  }
}

function parseDiscountRows(jsonStr: string | null | undefined): EclDiscountRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => {
      const scenarios: EclScenario[] = Array.isArray(raw.scenarios)
        ? raw.scenarios.map((s: any) => ({
            scenarioName: s.scenarioName || '',
            probability: parseNum(s.probability),
            presentValue: parseNum(s.presentValue),
            weighted: parseNum(s.weighted),
          }))
        : []
      return recalcDiscountRow({
        rowId: raw.rowId || generateRowId(),
        debtorName: raw.debtorName || '',
        balance: parseNum(raw.balance),
        scenarios,
        expectedLossRate: parseNum(raw.expectedLossRate),
        conclusion: raw.conclusion || '',
      })
    })
  } catch {
    return []
  }
}

function parseMigrationMatrix(jsonStr: string | null | undefined): MigrationRateRow[] {
  if (!jsonStr) return createDefaultMigrationMatrix()
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed) || parsed.length === 0) return createDefaultMigrationMatrix()
    return parsed.map((raw: any) => ({
      rowId: raw.rowId || generateRowId(),
      agingBand: raw.agingBand || '',
      year1Rate: parseNum(raw.year1Rate),
      year2Rate: parseNum(raw.year2Rate),
      year3Rate: parseNum(raw.year3Rate),
      avgRate: parseNum(raw.avgRate),
      expectedLossRate: parseNum(raw.expectedLossRate),
    }))
  } catch {
    return createDefaultMigrationMatrix()
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2Ecl(options: UseD2BaseOptions) {
  const { allResponses, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const singleRows = ref<EclSingleRow[]>([])
  const discountRows = ref<EclDiscountRow[]>([])
  const migrationMatrix = ref<MigrationRateRow[]>(createDefaultMigrationMatrix())
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadData(): void {
    const singleResp = allResponses.value.get(SINGLE_ROWS_KEY)
    singleRows.value = parseSingleRows(singleResp?.remark)

    const discountResp = allResponses.value.get(DISCOUNT_ROWS_KEY)
    discountRows.value = parseDiscountRows(discountResp?.remark)

    const migrationResp = allResponses.value.get(MIGRATION_MATRIX_KEY)
    migrationMatrix.value = parseMigrationMatrix(migrationResp?.remark)
    recalcAllMigration()
  }

  watch(
    () => [
      allResponses.value.get(SINGLE_ROWS_KEY)?.remark,
      allResponses.value.get(DISCOUNT_ROWS_KEY)?.remark,
      allResponses.value.get(MIGRATION_MATRIX_KEY)?.remark,
    ],
    () => {
      if (singleRows.value.length === 0 && discountRows.value.length === 0) {
        loadData()
      }
    },
    { immediate: true }
  )

  // ─── D2-9 Single ECL Total ─────────────────────────────────────────────

  const singleTotal: ComputedRef<{
    auditedBalance: number
    shouldProvision: number
    actualBalance: number
    difference: number
  }> = computed(() => {
    const rows = singleRows.value
    return {
      auditedBalance: rows.reduce((s, r) => s + r.auditedBalance, 0),
      shouldProvision: rows.reduce((s, r) => s + r.shouldProvision, 0),
      actualBalance: rows.reduce((s, r) => s + r.actualBalance, 0),
      difference: rows.reduce((s, r) => s + r.difference, 0),
    }
  })

  // ─── D2-10 Migration Matrix: output loss rates ─────────────────────────

  /**
   * 输出各账龄段的预期损失率（供D2-3坏账准备表引用）
   */
  const outputLossRates: ComputedRef<Map<string, number>> = computed(() => {
    const map = new Map<string, number>()
    for (const row of migrationMatrix.value) {
      map.set(row.agingBand, row.expectedLossRate)
    }
    return map
  })

  /**
   * 迁徙率变动警告：本年 vs 上年迁徙率差异超过阈值
   */
  const migrationChangeWarning: ComputedRef<string | null> = computed(() => {
    const warnings: string[] = []
    for (const row of migrationMatrix.value) {
      if (row.year1Rate > 0 && row.year2Rate > 0) {
        const change = Math.abs(row.year1Rate - row.year2Rate) / row.year2Rate
        if (change > 0.5) {
          warnings.push(`${row.agingBand}段迁徙率变动${(change * 100).toFixed(0)}%`)
        }
      }
    }
    return warnings.length > 0 ? warnings.join('；') : null
  })

  // ─── Recalc Migration Chain ────────────────────────────────────────────

  /**
   * 重算迁徙率矩阵全部行的 expectedLossRate（连乘逻辑）
   * 每行的 expectedLossRate = 本行avgRate × 下一行avgRate × ... × 最后行avgRate
   */
  function recalcAllMigration(): void {
    const rows = migrationMatrix.value
    for (let i = 0; i < rows.length; i++) {
      const rates = [rows[i].year1Rate, rows[i].year2Rate, rows[i].year3Rate].filter(r => r > 0)
      rows[i].avgRate = rates.length > 0 ? rates.reduce((a, b) => a + b, 0) / rates.length : 0
    }
    // 连乘：从最后一行开始，每行的expectedLossRate = 本行avg × 后续所有行avg
    for (let i = 0; i < rows.length; i++) {
      const subsequentAvgs = rows.slice(i + 1).map(r => r.avgRate).filter(r => r > 0)
      const allRates = rows[i].avgRate > 0 ? [rows[i].avgRate, ...subsequentAvgs] : []
      rows[i].expectedLossRate = calculateExpectedLossRate(allRates)
    }
  }

  // ─── Import from D2-2 Detail ───────────────────────────────────────────

  /**
   * 从D2-2明细表筛选"单项计提"客户导入到 D2-9
   */
  function importFromDetail(): void {
    if (isReadonly.value) return

    const detailJson = allResponses.value.get('D2-detail-rows')?.remark
    if (!detailJson) return

    try {
      const detailRows = JSON.parse(detailJson)
      if (!Array.isArray(detailRows)) return

      const filtered = detailRows.filter(
        (row: any) => (row.creditRiskClassification || row.AI || '') === '单项计提'
      )

      const imported: EclSingleRow[] = filtered.map((row: any) => {
        const newRow = createEmptySingleRow()
        newRow.debtorName = row.debtorName || row.clientName || ''
        newRow.auditedBalance = parseNum(row.currentAudited ?? row.auditedBalance)
        return recalcSingleRow(newRow)
      })

      if (imported.length > 0) {
        singleRows.value = [...singleRows.value, ...imported]
        debounceSave()
      }
    } catch {
      // silent
    }
  }

  // ─── Row Management: Single ────────────────────────────────────────────

  function addSingleRow(): void {
    if (isReadonly.value) return
    singleRows.value.push(createEmptySingleRow())
    debounceSave()
  }

  function removeSingleRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = singleRows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    singleRows.value.splice(idx, 1)
    debounceSave()
  }

  // ─── Row Management: Discount ──────────────────────────────────────────

  function addDiscountRow(): void {
    if (isReadonly.value) return
    discountRows.value.push(createEmptyDiscountRow())
    debounceSave()
  }

  function removeDiscountRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = discountRows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    discountRows.value.splice(idx, 1)
    debounceSave()
  }

  // ─── Update Cell ───────────────────────────────────────────────────────

  /**
   * 编辑单元格 → 公式重算 → debounce保存
   */
  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return

    // Try single rows
    const singleRow = singleRows.value.find(r => r.rowId === rowId)
    if (singleRow) {
      const key = field as keyof EclSingleRow
      if (key === 'debtorName' || key === 'basis' || key === 'indexRef') {
        ;(singleRow as any)[key] = String(value)
      } else if (key !== 'rowId' && key !== 'shouldProvision' && key !== 'difference') {
        ;(singleRow as any)[key] = parseNum(value)
      }
      recalcSingleRow(singleRow)
      debounceSave()
      return
    }

    // Try discount rows
    const discountRow = discountRows.value.find(r => r.rowId === rowId)
    if (discountRow) {
      const key = field as keyof EclDiscountRow
      if (key === 'debtorName' || key === 'conclusion') {
        ;(discountRow as any)[key] = String(value)
      } else if (key === 'balance') {
        discountRow.balance = parseNum(value)
      }
      recalcDiscountRow(discountRow)
      debounceSave()
      return
    }

    // Try migration matrix
    const migrationRow = migrationMatrix.value.find(r => r.rowId === rowId)
    if (migrationRow) {
      const key = field as keyof MigrationRateRow
      if (key === 'agingBand') {
        migrationRow.agingBand = String(value)
      } else if (key === 'year1Rate' || key === 'year2Rate' || key === 'year3Rate') {
        ;(migrationRow as any)[key] = parseNum(value)
      }
      recalcAllMigration()
      debounceSave()
      return
    }
  }

  /**
   * 更新折现场景
   */
  function updateScenario(rowId: string, scenarioIndex: number, field: keyof EclScenario, value: any): void {
    if (isReadonly.value) return
    const row = discountRows.value.find(r => r.rowId === rowId)
    if (!row || !row.scenarios[scenarioIndex]) return

    const scenario = row.scenarios[scenarioIndex]
    if (field === 'scenarioName') {
      scenario.scenarioName = String(value)
    } else if (field === 'probability' || field === 'presentValue') {
      ;(scenario as any)[field] = parseNum(value)
    }
    recalcDiscountRow(row)
    debounceSave()
  }

  // ─── Serialization & Save ──────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    const items = [
      { item_id: SINGLE_ROWS_KEY, conclusion: null, remark: JSON.stringify(singleRows.value) },
      { item_id: DISCOUNT_ROWS_KEY, conclusion: null, remark: JSON.stringify(discountRows.value) },
      { item_id: MIGRATION_MATRIX_KEY, conclusion: null, remark: JSON.stringify(migrationMatrix.value) },
    ]
    // Update allResponses
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    dispatchSaveEvent(items)
  }

  function dispatchSaveEvent(items: any[]): void {
    try {
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // D2-9 单项ECL
    singleRows,
    singleTotal,

    // D2-10 折现法
    discountRows,

    // D2-10 迁徙率矩阵
    migrationMatrix,
    outputLossRates,
    migrationChangeWarning,

    // 从D2-2导入
    importFromDetail,

    // 行操作
    addSingleRow,
    removeSingleRow,
    addDiscountRow,
    removeDiscountRow,
    updateCell,
    updateScenario,
  }
}

export default useD2Ecl
