/**
 * useD1EclCalc — D1-15 应收票据坏账准备测算表
 *
 * 纯函数与类型定义 + composable 主体。
 *
 * Spec: .kiro/specs/d1-ecl-provision/
 * Task: 1.1, 4.1
 *
 * Requirements: 6.1-9.5, 10.1-10.5, 12.2-12.6, 14.6, 15.1-15.7, 16.1-16.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface EclRow {
  id: string                  // 行唯一标识
  debtor: string              // A: 债务人名称
  balance: number             // B: 审定应收票据账面余额
  lossRate: number            // C: 预期信用损失率 [0,1]（内部小数存储）
  shouldProvision: number     // D: 期末应计提 = B×C（computed只读）
  actualProvision: number     // E: 期末坏账准备账面余额
  difference: number          // F: 差异 = E-D（computed只读）
  basis: string               // G: 计提依据及文件
  indexRef: string            // H: 索引号
  autoPulled?: boolean        // 是否由D1-4自动取数填充（用于浅蓝背景显示）
}

export interface SumRow {
  balance: number             // SUM(B)
  shouldProvision: number     // SUM(D)
  actualProvision: number     // SUM(E)
  difference: number          // SUM(F)
}

// ─── ID 生成 ──────────────────────────────────────────────────────────────────

/** 生成行唯一 ID（nanoid 风格轻量实现） */
export function generateEclRowId(): string {
  return `ecl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

// ─── 纯函数：公式引擎 ────────────────────────────────────────────────────────

/**
 * 应计提 = 余额 × 损失率 (D=B×C)
 *
 * 对所有行统一适用（组合section和单项section），结果可为负（当balance为负时）。
 */
export function calculateShouldProvision(balance: number, lossRate: number): number {
  return balance * lossRate
}

/**
 * 差异 = 实际计提 - 应计提 (F=E-D)
 *
 * 正值表示多提，负值表示少提。
 */
export function calculateDifference(actualProvision: number, shouldProvision: number): number {
  return actualProvision - shouldProvision
}

/**
 * SUM合计行：对rows数组的数值字段求和
 *
 * 各字段独立 reduce 求和，空数组返回全零 SumRow。
 */
export function calculateSumRow(rows: EclRow[]): SumRow {
  return {
    balance: rows.reduce((s, r) => s + r.balance, 0),
    shouldProvision: rows.reduce((s, r) => s + r.shouldProvision, 0),
    actualProvision: rows.reduce((s, r) => s + r.actualProvision, 0),
    difference: rows.reduce((s, r) => s + r.difference, 0),
  }
}

/**
 * 总合计 = 组合合计 + 单项合计（逐字段相加）
 */
export function calculateGrandTotal(portfolioSum: SumRow, individualSum: SumRow): SumRow {
  return {
    balance: portfolioSum.balance + individualSum.balance,
    shouldProvision: portfolioSum.shouldProvision + individualSum.shouldProvision,
    actualProvision: portfolioSum.actualProvision + individualSum.actualProvision,
    difference: portfolioSum.difference + individualSum.difference,
  }
}

/**
 * 重要性判断: |totalDifference| > materiality AND materiality > 0
 *
 * 当 materiality ≤ 0 时（未设置/无效），结果始终为 false。
 */
export function checkExceedsMateriality(totalDifference: number, materiality: number): boolean {
  return materiality > 0 && Math.abs(totalDifference) > materiality
}

/**
 * 损失率截断到[0,1]区间
 *
 * 用户输入百分比（0-100%），内部存储为小数（0-1）。
 * 对任意输入值强制约束在合法区间内。
 */
export function clampLossRate(value: number): number {
  return Math.max(0, Math.min(1, value))
}

// ─── 纯函数：格式化 ──────────────────────────────────────────────────────────

/**
 * 负数金额格式化：负数→括号格式 / 零→"-" / 正数→fmtAmount
 *
 * @param amount - 金额数值
 * @param fmtAmount - 千分位格式化函数（由 displayPrefs 提供）
 */
export function formatAmountDisplay(amount: number, fmtAmount: (n: number) => string): string {
  if (amount === 0) return '-'
  if (amount < 0) {
    const formatted = fmtAmount(Math.abs(amount))
    return `(${formatted})`
  }
  return fmtAmount(amount)
}

// ─── 纯函数：JSON 持久化 ──────────────────────────────────────────────────────

/** 需要序列化的用户输入字段（shouldProvision/difference 为计算字段，不存储） */
interface SerializedEclRow {
  id: string
  debtor: string
  balance: number
  lossRate: number
  actualProvision: number
  basis: string
  indexRef: string
  autoPulled?: boolean
}

/**
 * 行JSON序列化（持久化用）
 *
 * 仅存储用户输入字段，shouldProvision 和 difference 为计算字段不存储，
 * 反序列化时重新计算以确保一致性。
 */
export function serializeRows(rows: EclRow[]): string {
  const data: SerializedEclRow[] = rows.map(r => ({
    id: r.id,
    debtor: r.debtor,
    balance: r.balance,
    lossRate: r.lossRate,
    actualProvision: r.actualProvision,
    basis: r.basis,
    indexRef: r.indexRef,
    ...(r.autoPulled ? { autoPulled: true } : {}),
  }))
  return JSON.stringify(data)
}

/**
 * 行JSON反序列化（hydrate用）
 *
 * 解析 JSON 并重新计算 shouldProvision 和 difference，
 * 对 lossRate 应用 clamp 确保合法区间。
 * 解析失败时返回空数组（降级容错）。
 */
export function deserializeRows(json: string): EclRow[] {
  try {
    const parsed = JSON.parse(json) as Array<Record<string, unknown>>
    if (!Array.isArray(parsed)) return []
    return parsed.map(r => {
      const id = (r.id as string) || generateEclRowId()
      const debtor = (r.debtor as string) || ''
      const balance = Number(r.balance) || 0
      const lossRate = clampLossRate(Number(r.lossRate) || 0)
      const actualProvision = Number(r.actualProvision) || 0
      const shouldProvision = calculateShouldProvision(balance, lossRate)
      const difference = calculateDifference(actualProvision, shouldProvision)
      const basis = (r.basis as string) || ''
      const indexRef = (r.indexRef as string) || ''
      const autoPulled = r.autoPulled === true ? true : undefined

      return { id, debtor, balance, lossRate, shouldProvision, actualProvision, difference, basis, indexRef, ...(autoPulled ? { autoPulled } : {}) }
    })
  } catch {
    return []
  }
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────

// ─── Composable Types ────────────────────────────────────────────────────────

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface UseD1EclCalcOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  debouncedSave: SaveFn
  isReadonly: Ref<boolean>
}

// ─── Item ID Constants ───────────────────────────────────────────────────────

const ECL_ITEM_IDS = {
  portfolioRows: 'D1-ecl-portfolio-rows',
  individualRows: 'D1-ecl-individual-rows',
  auditNote: 'D1-ecl-audit-note',
  auditConclusion: 'D1-ecl-audit-conclusion',
  totalShouldProvision: 'D1-ecl-total-should-provision',
  totalActualProvision: 'D1-ecl-total-actual-provision',
  totalDifference: 'D1-ecl-total-difference',
} as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createEmptyRow(): EclRow {
  return {
    id: generateEclRowId(),
    debtor: '',
    balance: 0,
    lossRate: 0,
    shouldProvision: 0,
    actualProvision: 0,
    difference: 0,
    basis: '',
    indexRef: '',
  }
}

function createEmptyRows(count: number): EclRow[] {
  return Array.from({ length: count }, () => createEmptyRow())
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1EclCalc(options: UseD1EclCalcOptions) {
  const { allResponses, wpId, saveImmediate, debouncedSave, isReadonly } = options

  const isLoading = ref(false)

  // ─── 行数据 ───────────────────────────────────────────────────────────────

  const portfolioRows = ref<EclRow[]>(createEmptyRows(5))
  const individualRows = ref<EclRow[]>(createEmptyRows(3))

  // ─── lossRate 超范围警告 ──────────────────────────────────────────────────

  const lossRateWarningRow = ref<string | null>(null)
  let warningTimer: ReturnType<typeof setTimeout> | null = null

  function triggerLossRateWarning(rowId: string): void {
    lossRateWarningRow.value = rowId
    if (warningTimer) clearTimeout(warningTimer)
    warningTimer = setTimeout(() => {
      lossRateWarningRow.value = null
    }, 1500)
  }

  // ─── 行编辑：updateRow ────────────────────────────────────────────────────

  function updateRow(
    section: 'portfolio' | 'individual',
    index: number,
    field: keyof EclRow,
    value: string | number
  ): void {
    if (isReadonly.value) return
    const rows = section === 'portfolio' ? portfolioRows.value : individualRows.value
    if (index < 0 || index >= rows.length) return

    const row = { ...rows[index] }

    // Apply field value
    if (field === 'lossRate') {
      const numVal = Number(value) || 0
      // Trigger warning if out of range before clamping
      if (numVal < 0 || numVal > 1) {
        triggerLossRateWarning(row.id)
      }
      row.lossRate = clampLossRate(numVal)
    } else if (field === 'balance' || field === 'actualProvision') {
      ;(row as any)[field] = Number(value) || 0
      // Clear autoPulled flag when user manually edits E column
      if (field === 'actualProvision') {
        row.autoPulled = false
      }
    } else {
      ;(row as any)[field] = value
    }

    // Recalculate computed fields when relevant inputs change
    if (field === 'balance' || field === 'lossRate' || field === 'actualProvision') {
      row.shouldProvision = calculateShouldProvision(row.balance, row.lossRate)
      row.difference = calculateDifference(row.actualProvision, row.shouldProvision)
    }

    rows[index] = row
    scheduleSaveRows(section)
  }

  // ─── 动态行增删 ───────────────────────────────────────────────────────────

  function addPortfolioRow(): void {
    if (isReadonly.value) return
    portfolioRows.value = [...portfolioRows.value, createEmptyRow()]
    scheduleSaveRows('portfolio')
  }

  function removePortfolioRow(index: number): void {
    if (isReadonly.value) return
    if (index < 0 || index >= portfolioRows.value.length) return
    portfolioRows.value = portfolioRows.value.filter((_, i) => i !== index)
    scheduleSaveRows('portfolio')
  }

  function addIndividualRow(): void {
    if (isReadonly.value) return
    individualRows.value = [...individualRows.value, createEmptyRow()]
    scheduleSaveRows('individual')
  }

  function removeIndividualRow(index: number): void {
    if (isReadonly.value) return
    if (index < 0 || index >= individualRows.value.length) return
    individualRows.value = individualRows.value.filter((_, i) => i !== index)
    scheduleSaveRows('individual')
  }

  // ─── 合计行 Computed ──────────────────────────────────────────────────────

  const portfolioSumRow: ComputedRef<SumRow> = computed(() =>
    calculateSumRow(portfolioRows.value)
  )

  const individualSumRow: ComputedRef<SumRow> = computed(() =>
    calculateSumRow(individualRows.value)
  )

  const grandTotalRow: ComputedRef<SumRow> = computed(() =>
    calculateGrandTotal(portfolioSumRow.value, individualSumRow.value)
  )

  // ─── 重要性水平 Computed ──────────────────────────────────────────────────

  const materialityThreshold: ComputedRef<number> = computed(() => {
    // Scan allResponses for an item containing 'materiality' in key
    for (const [key, resp] of allResponses.value.entries()) {
      if (key.toLowerCase().includes('materiality')) {
        const val = Number(resp.remark)
        if (!isNaN(val) && val > 0) return val
      }
    }
    return 0
  })

  const exceedsMateriality: ComputedRef<boolean> = computed(() =>
    checkExceedsMateriality(grandTotalRow.value.difference, materialityThreshold.value)
  )

  // ─── 审计说明 / 审计结论 ──────────────────────────────────────────────────

  const auditNote = ref('')
  const auditConclusion = ref('')

  function saveAuditNote(): void {
    if (isReadonly.value) return
    debouncedSave([
      { item_id: ECL_ITEM_IDS.auditNote, remark: auditNote.value, conclusion: null },
    ])
  }

  function saveAuditConclusion(): void {
    if (isReadonly.value) return
    debouncedSave([
      { item_id: ECL_ITEM_IDS.auditConclusion, remark: auditConclusion.value, conclusion: null },
    ])
  }

  // ─── 行数据持久化（debounce保存） ────────────────────────────────────────

  let saveRowsTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSaveRows(section: 'portfolio' | 'individual' | 'both'): void {
    if (isReadonly.value) return
    if (saveRowsTimer) clearTimeout(saveRowsTimer)
    saveRowsTimer = setTimeout(() => {
      const items: ChecklistItem[] = []
      if (section === 'portfolio' || section === 'both') {
        items.push({
          item_id: ECL_ITEM_IDS.portfolioRows,
          remark: serializeRows(portfolioRows.value),
          conclusion: null,
        })
      }
      if (section === 'individual' || section === 'both') {
        items.push({
          item_id: ECL_ITEM_IDS.individualRows,
          remark: serializeRows(individualRows.value),
          conclusion: null,
        })
      }
      if (items.length > 0) {
        saveImmediate(items)
      }
    }, 2000)
  }

  // ─── 跨Spec写出：grandTotalRow变更时debounce写出 ─────────────────────────

  let crossSpecTimer: ReturnType<typeof setTimeout> | null = null

  watch(grandTotalRow, (newTotal) => {
    if (isReadonly.value) return
    if (crossSpecTimer) clearTimeout(crossSpecTimer)
    crossSpecTimer = setTimeout(() => {
      saveImmediate([
        { item_id: ECL_ITEM_IDS.totalShouldProvision, remark: String(newTotal.shouldProvision), conclusion: null },
        { item_id: ECL_ITEM_IDS.totalActualProvision, remark: String(newTotal.actualProvision), conclusion: null },
        { item_id: ECL_ITEM_IDS.totalDifference, remark: String(newTotal.difference), conclusion: null },
      ])
    }, 2000)
  }, { deep: true })

  // ─── Hydrate ──────────────────────────────────────────────────────────────

  function hydrate(): void {
    isLoading.value = true
    try {
      const get = (id: string) => allResponses.value.get(id)

      // Portfolio rows
      const portfolioJson = get(ECL_ITEM_IDS.portfolioRows)?.remark
      if (portfolioJson) {
        const parsed = deserializeRows(portfolioJson)
        portfolioRows.value = parsed.length > 0 ? parsed : createEmptyRows(5)
      } else {
        portfolioRows.value = createEmptyRows(5)
      }

      // Individual rows
      const individualJson = get(ECL_ITEM_IDS.individualRows)?.remark
      if (individualJson) {
        const parsed = deserializeRows(individualJson)
        individualRows.value = parsed.length > 0 ? parsed : createEmptyRows(3)
      } else {
        individualRows.value = createEmptyRows(3)
      }

      // Audit note & conclusion
      auditNote.value = get(ECL_ITEM_IDS.auditNote)?.remark ?? ''
      auditConclusion.value = get(ECL_ITEM_IDS.auditConclusion)?.remark ?? ''
    } finally {
      isLoading.value = false
    }
  }

  // ─── 从D1-4取数逻辑 ─────────────────────────────────────────────────────

  /** D1-4坏账准备数据是否可用 */
  const d1_4DataAvailable = computed<boolean>(() => {
    for (const key of allResponses.value.keys()) {
      if (key === 'D1-bd-individual-rows' || key === 'D1-bd-portfolio-rows') {
        const remark = allResponses.value.get(key)?.remark
        if (remark) return true
      }
    }
    return false
  })

  /**
   * 从D1-4坏账准备明细表取数填入E列（期末坏账准备账面余额）
   *
   * 匹配逻辑：
   * - 组合section：按D1-4 portfolio行的label字段 与 D1-15 row的debtor字段 做trimmed忽略大小写匹配
   * - 单项section：按D1-4 individual行的label字段 与 D1-15 row的debtor字段 做trimmed忽略大小写匹配
   * - 匹配成功时填入D1-4行的currentAudited作为E列值
   * - 填入后标记autoPulled=true
   * - 无匹配则不修改该行
   */
  function pullFromD1_4(): void {
    if (isReadonly.value) return

    // Parse D1-4 portfolio rows
    const portfolioD4Rows = parseD1_4Rows('D1-bd-portfolio-rows')
    // Parse D1-4 individual rows
    const individualD4Rows = parseD1_4Rows('D1-bd-individual-rows')

    let changed = false

    // Match portfolio section: D1-4 portfolio rows → D1-15 portfolioRows by label↔debtor
    if (portfolioD4Rows.length > 0) {
      const updatedPortfolio = portfolioRows.value.map(row => {
        if (!row.debtor.trim()) return row
        const match = findD1_4Match(portfolioD4Rows, row.debtor)
        if (match !== null) {
          const newRow = { ...row, actualProvision: match, autoPulled: true }
          newRow.shouldProvision = calculateShouldProvision(newRow.balance, newRow.lossRate)
          newRow.difference = calculateDifference(newRow.actualProvision, newRow.shouldProvision)
          changed = true
          return newRow
        }
        return row
      })
      portfolioRows.value = updatedPortfolio
    }

    // Match individual section: D1-4 individual rows → D1-15 individualRows by label↔debtor
    if (individualD4Rows.length > 0) {
      const updatedIndividual = individualRows.value.map(row => {
        if (!row.debtor.trim()) return row
        const match = findD1_4Match(individualD4Rows, row.debtor)
        if (match !== null) {
          const newRow = { ...row, actualProvision: match, autoPulled: true }
          newRow.shouldProvision = calculateShouldProvision(newRow.balance, newRow.lossRate)
          newRow.difference = calculateDifference(newRow.actualProvision, newRow.shouldProvision)
          changed = true
          return newRow
        }
        return row
      })
      individualRows.value = updatedIndividual
    }

    // Save after pull
    if (changed) {
      scheduleSaveRows('both')
    }
  }

  /** Parse D1-4 rows from allResponses by key */
  function parseD1_4Rows(key: string): Array<{ label: string; currentAudited: number }> {
    const response = allResponses.value.get(key)
    const raw = response?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw) as Array<Record<string, unknown>>
      if (!Array.isArray(parsed)) return []
      return parsed.map(r => ({
        label: String(r.label || '').trim(),
        currentAudited: Number(r.currentAudited) || 0,
      })).filter(r => r.label.length > 0)
    } catch {
      return []
    }
  }

  /** Find D1-4 row matching D1-15 debtor name (trimmed, case-insensitive) */
  function findD1_4Match(d4Rows: Array<{ label: string; currentAudited: number }>, debtor: string): number | null {
    const normalized = debtor.trim().toLowerCase()
    const match = d4Rows.find(r => r.label.toLowerCase() === normalized)
    return match ? match.currentAudited : null
  }

  // ─── 导入导出存根 ────────────────────────────────────────────────────────

  async function exportTemplate(): Promise<void> {
    const response = await http.post(
      `/api/workpapers/${wpId.value}/d1-ecl/export-template`,
      null,
      { responseType: 'blob' }
    )
    const blob = new Blob([response.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'D1-15_ECL测算模板.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function exportData(): Promise<void> {
    const response = await http.post(
      `/api/workpapers/${wpId.value}/d1-ecl/export-data`,
      null,
      { responseType: 'blob' }
    )
    const blob = new Blob([response.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'D1-15_ECL测算数据.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function importData(file: File): Promise<void> {
    const formData = new FormData()
    formData.append('file', file)
    await http.post(
      `/api/workpapers/${wpId.value}/d1-ecl/import-data`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
  }

  // ─── Return ───────────────────────────────────────────────────────────────

  return {
    // 行数据
    portfolioRows,
    individualRows,

    // 行操作
    addPortfolioRow,
    removePortfolioRow,
    addIndividualRow,
    removeIndividualRow,
    updateRow,

    // lossRate警告
    lossRateWarningRow,

    // 合计行
    portfolioSumRow,
    individualSumRow,
    grandTotalRow,

    // 重要性判断
    materialityThreshold,
    exceedsMateriality,

    // 审计说明/结论
    auditNote,
    auditConclusion,
    saveAuditNote,
    saveAuditConclusion,

    // 加载状态
    isLoading,
    hydrate,

    // 导入导出
    exportTemplate,
    exportData,
    importData,

    // D1-4取数
    d1_4DataAvailable,
    pullFromD1_4,
  }
}
