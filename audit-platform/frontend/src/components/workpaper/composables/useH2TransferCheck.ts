/**
 * useH2TransferCheck — H2-5 转固时点检查 composable
 *
 * TransferRow 15列 + CAS4五条件自动判定
 * 转固合计 + 与H2-1交叉验证 + H1联动EventBus
 * 延迟天数计算 + 异常高亮规则
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.7
 * Requirements: 6.1-6.10
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcTransferCondition, calcOverdueDays, calcSubtotal } from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H2TransferRow {
  rowId: string
  /** 工程名称 */
  name: string
  /** 转固日期 */
  transferDate: string
  /** 转固金额 */
  transferAmount: number
  /** 条件1: 实体建造完成 */
  condition1: boolean
  /** 条件2: 达到设计要求 */
  condition2: boolean
  /** 条件3: 试运转合格 */
  condition3: boolean
  /** 条件4: 竣工决算已办or可确定 */
  condition4: boolean
  /** 条件5: 已投入使用or可使用 */
  condition5: boolean
  /** 五条件全满足 (公式列) */
  allConditionsMet: boolean
  /** 是否及时转固 */
  timelyTransfer: boolean | null
  /** 延迟天数 (公式列) */
  delayDays: number
  /** 对应H1资产 */
  h1Asset: string
  /** H1入账金额 */
  h1Amount: number
  /** 差异 (公式列: 转固金额 - H1入账金额) */
  difference: number
  /** 备注 */
  remark: string
  /** 五条件满足日期（用于计算延迟天数） */
  conditionsMetDate: string
}

/** 高亮类型 */
export type TransferHighlight = 'red-not-transferred' | 'yellow-delay' | 'red-amount-diff' | null

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H2-5-rows'
const NOTE_KEY = 'H2-5-audit-note'
const CONCLUSION_KEY = 'H2-5-audit-conclusion'
const DELAY_THRESHOLD_DAYS = 30

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2TransferCheck(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H2TransferRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _recalcRow(row: H2TransferRow): void {
    // CAS4五条件判定
    const conditions = [row.condition1, row.condition2, row.condition3, row.condition4, row.condition5]
    row.allConditionsMet = calcTransferCondition(conditions)

    // 延迟天数计算
    if (row.allConditionsMet && row.conditionsMetDate && row.transferDate) {
      row.delayDays = calcOverdueDays(row.transferDate, row.conditionsMetDate)
      row.timelyTransfer = row.delayDays <= DELAY_THRESHOLD_DAYS
    } else if (row.allConditionsMet && !row.transferDate) {
      // 五条件满足但未转固——视为未及时转固
      row.delayDays = row.conditionsMetDate
        ? calcOverdueDays(new Date().toISOString().slice(0, 10), row.conditionsMetDate)
        : 0
      row.timelyTransfer = false
    } else {
      row.delayDays = 0
      row.timelyTransfer = null
    }

    // 差异计算
    row.difference = row.transferAmount - row.h1Amount
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((r: any) => {
        const row: H2TransferRow = {
          rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
          name: r.name ?? '',
          transferDate: r.transferDate ?? '',
          transferAmount: Number(r.transferAmount) || 0,
          condition1: !!r.condition1,
          condition2: !!r.condition2,
          condition3: !!r.condition3,
          condition4: !!r.condition4,
          condition5: !!r.condition5,
          allConditionsMet: false,
          timelyTransfer: null,
          delayDays: 0,
          h1Asset: r.h1Asset ?? '',
          h1Amount: Number(r.h1Amount) || 0,
          difference: 0,
          remark: r.remark ?? '',
          conditionsMetDate: r.conditionsMetDate ?? '',
        }
        _recalcRow(row)
        return row
      })
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** 转固金额合计 */
  const transferTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.transferAmount)),
  )

  /** H1入账金额合计 */
  const h1Total: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.h1Amount)),
  )

  /** 总差异 */
  const totalDifference: ComputedRef<number> = computed(() =>
    transferTotal.value - h1Total.value,
  )

  /** 与H2-1交叉验证（从allResponses取H2-2的transfer合计） */
  const crossValidationH1: ComputedRef<{ diff: number; isMatch: boolean }> = computed(() => {
    const resp = options.allResponses.value.get('H2-2-rows')
    const raw = resp?.remark ?? resp?.conclusion
    let h2_2_transferTotal = 0
    if (raw) {
      try {
        const h2Rows = JSON.parse(raw)
        if (Array.isArray(h2Rows)) {
          for (const r of h2Rows) {
            h2_2_transferTotal += Number(r.transferAmount) || 0
          }
        }
      } catch { /* ignore */ }
    }
    const diff = transferTotal.value - h2_2_transferTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  /** 行高亮规则 */
  const rowHighlights: ComputedRef<Map<string, TransferHighlight>> = computed(() => {
    const map = new Map<string, TransferHighlight>()
    for (const row of rows.value) {
      if (row.allConditionsMet && !row.transferDate) {
        map.set(row.rowId, 'red-not-transferred')
      } else if (row.delayDays > DELAY_THRESHOLD_DAYS) {
        map.set(row.rowId, 'yellow-delay')
      } else if (Math.abs(row.difference) > 0.01) {
        map.set(row.rowId, 'red-amount-diff')
      } else {
        map.set(row.rowId, null)
      }
    }
    return map
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(name: string): void {
    if (options.isReadonly.value) return
    if (!name?.trim()) return
    const row: H2TransferRow = {
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name: name.trim(),
      transferDate: '',
      transferAmount: 0,
      condition1: false,
      condition2: false,
      condition3: false,
      condition4: false,
      condition5: false,
      allConditionsMet: false,
      timelyTransfer: null,
      delayDays: 0,
      h1Asset: '',
      h1Amount: 0,
      difference: 0,
      remark: '',
      conditionsMetDate: '',
    }
    rows.value.push(row)
    _persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      rows.value.splice(idx, 1)
      _persist()
    }
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const boolFields = ['condition1', 'condition2', 'condition3', 'condition4', 'condition5']
    const numFields = ['transferAmount', 'h1Amount']
    const formulaFields = ['allConditionsMet', 'timelyTransfer', 'delayDays', 'difference']

    if (formulaFields.includes(field)) return  // 公式列不可修改

    if (boolFields.includes(field)) {
      ;(row as any)[field] = !!value
    } else if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
    } else {
      ;(row as any)[field] = String(value ?? '')
    }

    _recalcRow(row)
    _persist()
  }

  /** 发布转固联动H1事件 */
  function publishTransferToH1(): void {
    if (!options.onPublishEvent) return
    options.onPublishEvent('h2:transfer-to-h1', {
      items: rows.value
        .filter(r => r.transferAmount > 0)
        .map(r => ({
          name: r.name,
          amount: r.transferAmount,
          date: r.transferDate,
          h1Asset: r.h1Asset,
        })),
      totalTransfer: transferTotal.value,
    })
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!options.onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      name: r.name,
      transferDate: r.transferDate,
      transferAmount: r.transferAmount,
      condition1: r.condition1,
      condition2: r.condition2,
      condition3: r.condition3,
      condition4: r.condition4,
      condition5: r.condition5,
      h1Asset: r.h1Asset,
      h1Amount: r.h1Amount,
      remark: r.remark,
      conditionsMetDate: r.conditionsMetDate,
    }))
    options.onSave(ROWS_KEY, toPersist)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    auditNote,
    auditConclusion,
    transferTotal,
    h1Total,
    totalDifference,
    crossValidationH1,
    rowHighlights,
    addRow,
    removeRow,
    updateCell,
    publishTransferToH1,
    saveNote,
    saveConclusion,
    initFromAllResponses,
  }
}

export default useH2TransferCheck
