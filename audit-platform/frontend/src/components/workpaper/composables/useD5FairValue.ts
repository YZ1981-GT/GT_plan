/**
 * useD5FairValue — D5-4 公允价值测算表核心逻辑 composable
 *
 * Spec: .kiro/specs/d5-receivables-financing/
 * Task: 8.1
 *
 * 职责：
 * - 定义 FairValueRow 类型（13列 A~M）
 * - rows reactive（从D5-4-rows加载JSON数组）
 * - 行内公式自动计算（G=F-E天数差, I=D×H×G÷360, J=D-I, K=J）
 * - totalRow computed（票面合计/贴现利息合计/公允价值合计）
 * - ociDiffMessage computed（D5-4 FV合计 vs D5-2期末合计差异提示文案）
 * - addRow/removeRow/updateCell
 * - setDefaultRate（全表统一默认利率，用户可逐行覆盖）
 * - measurementDate默认填充period_end
 * - fvHierarchy下拉（第二层次/第三层次）+ tooltip判定规则
 * - auditNotes 双向绑定（explanation/conclusion）
 *
 * Requirements: 6.1-6.10
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  parseNum,
  calcRemainingDays,
  calcDiscountInterest,
  calcFairValue,
  calcSubtotal,
} from './useD5FormulaEngine'
import type { ChecklistResponse } from './useD5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface FairValueRow {
  rowId: string
  category: string            // A: 类别（应收票据/应收账款）
  itemName: string            // B: 明细项目
  billNo: string              // C: 票据号
  faceValue: number           // D: 票面金额
  measurementDate: string     // E: 计量日（默认period_end）
  maturityDate: string        // F: 到期日
  remainingDays: number       // G: =F-E（自动）
  discountRate: number        // H: 市场贴现利率
  discountInterest: number    // I: =D×H×G÷360（自动）
  discountAmount: number      // J: =D-I（自动，即贴现金额）
  fairValue: number           // K: =J（自动，期末公允价值）
  fvHierarchy: string         // L: 公允价值层次（第二层次/第三层次）
  remark: string              // M: 备注
}

export type SaveFn = (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
export type DebouncedSaveFn = (itemId: string, data: Partial<ChecklistResponse>) => void

export interface UseD5FairValueOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  debouncedSave: DebouncedSaveFn
  isReadonly: Ref<boolean>
  periodEnd: Ref<string>       // 资产负债表日
  defaultDiscountRate: Ref<number>  // 全表默认利率
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D5-4-rows'
const ITEM_ID_DEFAULT_RATE = 'D5-4-default-rate'
const ITEM_ID_NOTE_EXPLANATION = 'D5-4-note-explanation'
const ITEM_ID_NOTE_CONCLUSION = 'D5-4-note-conclusion'

/** 公允价值层次下拉选项 */
export const FV_HIERARCHY_OPTIONS = ['第二层次', '第三层次'] as const

/** 公允价值层次判定规则 tooltip */
export const FV_HIERARCHY_TOOLTIP = '可观察输入值(如银行公布贴现利率)→第二层次；不可观察输入值→第三层次'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

/** 安全解析 JSON 数组 */
function safeParseRows(jsonStr: string | null | undefined): FairValueRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

/** 规范化行数据，确保所有字段存在且类型正确 */
function normalizeRow(raw: any): FairValueRow {
  return {
    rowId: raw.rowId || generateRowId(),
    category: raw.category || '',
    itemName: raw.itemName || '',
    billNo: raw.billNo || '',
    faceValue: parseNum(raw.faceValue),
    measurementDate: raw.measurementDate || '',
    maturityDate: raw.maturityDate || '',
    remainingDays: parseNum(raw.remainingDays),
    discountRate: parseNum(raw.discountRate),
    discountInterest: parseNum(raw.discountInterest),
    discountAmount: parseNum(raw.discountAmount),
    fairValue: parseNum(raw.fairValue),
    fvHierarchy: raw.fvHierarchy || '',
    remark: raw.remark || '',
  }
}

/**
 * 对单行重新计算公式链：
 * G = calcRemainingDays(E, F) — 到期日减去计量日
 * I = calcDiscountInterest(D, H, G) — 票面×利率×天数÷360
 * J = calcFairValue(D, I) — 票面 - 贴现利息
 * K = J（期末公允价值 = 贴现金额）
 */
export function recalcFairValueRow(row: FairValueRow): FairValueRow {
  const G = calcRemainingDays(row.measurementDate, row.maturityDate)
  const I = calcDiscountInterest(row.faceValue, row.discountRate, G)
  const J = calcFairValue(row.faceValue, I)
  const K = J

  return {
    ...row,
    remainingDays: G,
    discountInterest: I,
    discountAmount: J,
    fairValue: K,
  }
}

/** 创建空行（数值为 0，计量日默认填 periodEnd） */
export function createEmptyFairValueRow(periodEnd: string, defaultRate: number): FairValueRow {
  return {
    rowId: generateRowId(),
    category: '',
    itemName: '',
    billNo: '',
    faceValue: 0,
    measurementDate: periodEnd,
    maturityDate: '',
    remainingDays: 0,
    discountRate: defaultRate,
    discountInterest: 0,
    discountAmount: 0,
    fairValue: 0,
    fvHierarchy: '',
    remark: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD5FairValue(options: UseD5FairValueOptions) {
  const {
    allResponses,
    wpId: _wpId,
    projectId: _projectId,
    saveImmediate,
    debouncedSave,
    isReadonly,
    periodEnd,
    defaultDiscountRate,
  } = options
  void _wpId // reserved for future use
  void _projectId // reserved for future use

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<FairValueRow[]>([])

  // Load rows from allResponses
  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => {
      const parsed = safeParseRows(jsonStr)
      // Recalculate formula chain for each row
      rows.value = parsed.map(recalcFairValueRow)
    },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── totalRow computed ───────────────────────────────────────────────

  /**
   * 合计行：票面合计 / 贴现利息合计 / 公允价值合计
   */
  const totalRow: ComputedRef<{ faceValue: number; discountInterest: number; fairValue: number }> = computed(() => {
    return {
      faceValue: calcSubtotal(rows.value.map(r => r.faceValue)),
      discountInterest: calcSubtotal(rows.value.map(r => r.discountInterest)),
      fairValue: calcSubtotal(rows.value.map(r => r.fairValue)),
    }
  })

  // ─── ociDiffMessage computed ─────────────────────────────────────────

  /**
   * D5-4 公允价值合计 vs D5-2 期末审定合计差异提示文案
   *
   * 从 allResponses 中获取 D5-2 行数据，计算期末审定合计，
   * 与 D5-4 公允价值合计对比，有差异时生成提示文案。
   */
  const ociDiffMessage: ComputedRef<string | null> = computed(() => {
    // 计算 D5-2 期末审定合计
    const d52Resp = allResponses.value.get('D5-2-rows')
    let d52EndAuditedTotal = 0
    if (d52Resp?.remark) {
      try {
        const d52Rows = JSON.parse(d52Resp.remark)
        if (Array.isArray(d52Rows)) {
          for (const row of d52Rows) {
            d52EndAuditedTotal += parseNum(row.endAudited)
          }
        }
      } catch {
        // JSON 解析失败，忽略
      }
    }

    // D5-4 公允价值合计
    const fvTotal = totalRow.value.fairValue

    // 如果两者都为 0，无意义（可能还没数据）
    if (d52EndAuditedTotal === 0 && fvTotal === 0) return null

    // 计算差额
    const diff = d52EndAuditedTotal - fvTotal

    // 浮点精度：差异绝对值 < 0.01 视为无差异
    if (Math.abs(diff) < 0.01) return null

    // 生成差异提示文案
    const sign = diff > 0 ? '+' : ''
    return `D5-4公允价值合计≠D5-2期末审定合计，差额=OCI公允价值变动：${sign}${diff.toFixed(2)}元`
  })

  // ─── addRow ──────────────────────────────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    const newRow = createEmptyFairValueRow(periodEnd.value, defaultDiscountRate.value)
    rows.value = [...rows.value, newRow]
    persistRows()
  }

  // ─── removeRow ───────────────────────────────────────────────────────

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  // ─── updateCell ──────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return

    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }

    // Numeric fields (input → recalc)
    const numericFields = ['faceValue', 'discountRate']

    // String/date fields
    const stringFields = ['category', 'itemName', 'billNo', 'measurementDate', 'maturityDate', 'fvHierarchy', 'remark']

    if (numericFields.includes(field)) {
      ;(row as any)[field] = parseNum(value)
    } else if (stringFields.includes(field)) {
      ;(row as any)[field] = value ?? ''
    }

    // Recalculate formula chain
    const recalculated = recalcFairValueRow(row)

    // Update rows array
    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows

    persistRows()
  }

  // ─── setDefaultRate（全表统一默认利率）─────────────────────────────────

  /**
   * 设置全表统一默认利率。
   * 已有行中如果当前利率为0或等于旧默认值，则更新为新默认值。
   * 用户逐行覆盖过的利率（≠旧默认值且≠0）不受影响。
   */
  function setDefaultRate(rate: number): void {
    if (isReadonly.value) return

    const oldDefault = defaultDiscountRate.value

    // 更新存储中的默认利率
    saveImmediate(ITEM_ID_DEFAULT_RATE, { remark: String(rate) })

    // 更新已有行中利率为0或旧默认值的行
    let changed = false
    const newRows = rows.value.map(row => {
      if (row.discountRate === 0 || row.discountRate === oldDefault) {
        changed = true
        return recalcFairValueRow({ ...row, discountRate: rate })
      }
      return row
    })

    if (changed) {
      rows.value = newRows
      persistRows()
    }
  }

  // ─── auditNotes 双向绑定 ─────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string }>({
    explanation: '',
    conclusion: '',
  })

  // 从 allResponses 加载审计说明/结论
  watch(
    () => [
      allResponses.value.get(ITEM_ID_NOTE_EXPLANATION)?.remark,
      allResponses.value.get(ITEM_ID_NOTE_CONCLUSION)?.remark,
    ],
    ([explanation, conclusion]) => {
      auditNotes.value = {
        explanation: explanation || '',
        conclusion: conclusion || '',
      }
    },
    { immediate: true },
  )

  // Watch auditNotes changes for persistence
  watch(
    () => auditNotes.value.explanation,
    (val) => {
      debouncedSave(ITEM_ID_NOTE_EXPLANATION, { remark: val })
    },
  )

  watch(
    () => auditNotes.value.conclusion,
    (val) => {
      debouncedSave(ITEM_ID_NOTE_CONCLUSION, { remark: val })
    },
  )

  // ─── rateReasonabilityWarnings（贴现利率合理性预警）──────────────────

  /** 贴现利率合理性预警：差异超过200bp(2%)的行标记warning */
  const rateReasonabilityWarnings: ComputedRef<Array<{ rowId: string; itemName: string; rate: number; deviation: number }>> = computed(() => {
    const warnings: Array<{ rowId: string; itemName: string; rate: number; deviation: number }> = []
    if (rows.value.length === 0) return warnings

    // 计算当前所有行的加权平均利率作为基准
    let totalFace = 0
    let weightedRate = 0
    for (const row of rows.value) {
      if (row.faceValue > 0 && row.discountRate > 0) {
        totalFace += row.faceValue
        weightedRate += row.faceValue * row.discountRate
      }
    }
    const avgRate = totalFace > 0 ? weightedRate / totalFace : 0
    if (avgRate === 0) return warnings

    // 差异超过200bp(0.02即2个百分点)
    const threshold = 0.02
    for (const row of rows.value) {
      if (row.discountRate > 0) {
        const deviation = Math.abs(row.discountRate - avgRate)
        if (deviation > threshold) {
          warnings.push({
            rowId: row.rowId,
            itemName: row.itemName || row.billNo || '未命名',
            rate: row.discountRate,
            deviation,
          })
        }
      }
    }
    return warnings
  })

  // ─── maturityWarnings（到期日预警）────────────────────────────────────

  /** 到期日预警统计：已逾期(remainingDays≤0)和即将到期(1-30天) */
  const maturityWarnings: ComputedRef<{
    overdue: Array<{ rowId: string; itemName: string; days: number; faceValue: number }>
    nearMaturity: Array<{ rowId: string; itemName: string; days: number; faceValue: number }>
    overdueTotal: number
    nearMaturityTotal: number
  }> = computed(() => {
    const overdue: Array<{ rowId: string; itemName: string; days: number; faceValue: number }> = []
    const nearMaturity: Array<{ rowId: string; itemName: string; days: number; faceValue: number }> = []

    for (const row of rows.value) {
      if (!row.maturityDate) continue
      const days = row.remainingDays
      const info = { rowId: row.rowId, itemName: row.itemName || row.billNo || '未命名', days, faceValue: row.faceValue }

      if (days <= 0 && row.maturityDate) {
        overdue.push(info)
      } else if (days > 0 && days <= 30) {
        nearMaturity.push(info)
      }
    }

    return {
      overdue,
      nearMaturity,
      overdueTotal: calcSubtotal(overdue.map(r => r.faceValue)),
      nearMaturityTotal: calcSubtotal(nearMaturity.map(r => r.faceValue)),
    }
  })

  // ─── importFromDetail（从D5-2带入候选行）──────────────────────────────

  /**
   * 从D5-2明细表带入类别=应收票据的行作为公允价值测算候选
   * 去重: billNo 或 itemName 已存在则跳过
   */
  function importFromDetail(): void {
    if (isReadonly.value) return

    const d52Resp = allResponses.value.get('D5-2-rows')
    if (!d52Resp?.remark) {
      ElMessage.info('D5-2明细表暂无数据')
      return
    }

    let d52Rows: any[] = []
    try {
      d52Rows = JSON.parse(d52Resp.remark)
      if (!Array.isArray(d52Rows)) d52Rows = []
    } catch {
      ElMessage.error('D5-2数据解析失败')
      return
    }

    // 筛选应收票据类
    const candidates = d52Rows.filter((r: any) => r.category === '应收票据' && parseNum(r.endAudited) > 0)
    if (candidates.length === 0) {
      ElMessage.info('D5-2中无应收票据类明细（或期末审定为0）')
      return
    }

    // 去重(已存在的itemName不重复添加)
    const existingNames = new Set(rows.value.map(r => r.itemName).filter(Boolean))
    const newCandidates = candidates.filter((c: any) => !existingNames.has(c.itemName || ''))

    if (newCandidates.length === 0) {
      ElMessage.info('D5-2所有应收票据已在公允价值测算表中')
      return
    }

    const imported = newCandidates.map((c: any) => {
      const row = createEmptyFairValueRow(periodEnd.value, defaultDiscountRate.value)
      row.category = '应收票据'
      row.itemName = c.itemName || ''
      row.faceValue = parseNum(c.endAudited) // 票面金额=期末审定数
      return recalcFairValueRow(row)
    })

    rows.value = [...rows.value, ...imported]
    persistRows()
    ElMessage.success(`从D5-2带入${imported.length}笔应收票据候选`)
  }

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    totalRow,
    ociDiffMessage,
    addRow,
    removeRow,
    updateCell,
    setDefaultRate,
    auditNotes,
    rateReasonabilityWarnings,
    maturityWarnings,
    importFromDetail,
  }
}

export default useD5FairValue
