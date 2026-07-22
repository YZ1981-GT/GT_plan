/**
 * useD3LongTerm — D3-5 账龄1年以上检查表核心逻辑 composable
 *
 * Spec: .kiro/specs/d3-prepaid-accounts/
 * Task: 11.1
 *
 * 职责：
 * - 定义 LongTermRow 类型（8列）
 * - rows reactive（从D3-lt-rows加载JSON）
 * - 从crossSheet.longTermRows导入功能
 * - subtotalRow computed（期末余额/结转金额SUM）
 * - addRow/removeRow/updateCell
 * - auditNote/conclusion 双向绑定
 *
 * Requirements: 9.1-9.8
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useD3FormulaEngine'
import type { ChecklistResponse } from './useD3FormData'
import type { LongTermImportRow } from './useD3CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface LongTermRow {
  rowId: string
  customerName: string       // 对方单位名称
  endBalance: number         // 期末余额
  aging: string              // 账龄
  businessDescription: string // 经济业务说明
  reason: string             // 未结转或未偿还的原因
  settlementAmount: number   // 至审计日结转或偿还金额
  disposalConclusion: string // 处理结论（应确认收入/应退回/应转营业外收入/正常挂账/待确定）
  plan: string               // 处理计划
  remark: string             // 备注
}

/**
 * 处理结论枚举（CAS14 视角，判断型字段点选）：
 * - 应确认收入：履约义务已完成，应转收入（关注收入截止 D4）
 * - 应退回：合同解除/多收，应退款（列示为其他应付款/其他流动负债）
 * - 应转营业外收入：确实无需支付/对方已注销/超时效，转营业外收入（关联 K12）
 * - 正常挂账：合理未结转（如长期合同尚在履约）
 * - 待确定：需进一步取证
 */
export const DISPOSAL_CONCLUSIONS = [
  '应确认收入',
  '应退回',
  '应转营业外收入',
  '正常挂账',
  '待确定',
] as const

export interface UseD3LongTermOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D3-lt-rows'
const ITEM_ID_NOTE = 'D3-lt-note'
const ITEM_ID_CONCLUSION = 'D3-lt-conclusion'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

function safeParseRows(jsonStr: string | null | undefined): LongTermRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function normalizeRow(raw: any): LongTermRow {
  return {
    rowId: raw.rowId || generateRowId(),
    customerName: raw.customerName || '',
    endBalance: parseNum(raw.endBalance),
    aging: raw.aging || '',
    businessDescription: raw.businessDescription || '',
    reason: raw.reason || '',
    settlementAmount: parseNum(raw.settlementAmount),
    disposalConclusion: raw.disposalConclusion || '',
    plan: raw.plan || '',
    remark: raw.remark || '',
  }
}

function createEmptyRow(): LongTermRow {
  return {
    rowId: generateRowId(),
    customerName: '',
    endBalance: 0,
    aging: '',
    businessDescription: '',
    reason: '',
    settlementAmount: 0,
    disposalConclusion: '',
    plan: '',
    remark: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD3LongTerm(options: UseD3LongTermOptions) {
  const { allResponses, debouncedSave, isReadonly } = options

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<LongTermRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => { rows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── subtotalRow computed ────────────────────────────────────────────

  const subtotalRow: ComputedRef<{ endBalance: number; settlementAmount: number }> = computed(() => {
    return {
      endBalance: calcSubtotal(rows.value.map(r => r.endBalance)),
      settlementAmount: calcSubtotal(rows.value.map(r => r.settlementAmount)),
    }
  })

  // ─── 处理结论汇总（供跨底稿联动提示：→D4收入 / →K12营业外收入） ──────────

  /** 按处理结论分组的笔数与金额合计 */
  const disposalSummary: ComputedRef<{
    shouldRecognizeRevenue: { count: number; amount: number }
    shouldTransferNonOperating: { count: number; amount: number }
    shouldRefund: { count: number; amount: number }
    pending: { count: number; amount: number }
  }> = computed(() => {
    const acc = {
      shouldRecognizeRevenue: { count: 0, amount: 0 },
      shouldTransferNonOperating: { count: 0, amount: 0 },
      shouldRefund: { count: 0, amount: 0 },
      pending: { count: 0, amount: 0 },
    }
    for (const r of rows.value) {
      const amt = parseNum(r.endBalance)
      switch (r.disposalConclusion) {
        case '应确认收入':
          acc.shouldRecognizeRevenue.count++; acc.shouldRecognizeRevenue.amount += amt; break
        case '应转营业外收入':
          acc.shouldTransferNonOperating.count++; acc.shouldTransferNonOperating.amount += amt; break
        case '应退回':
          acc.shouldRefund.count++; acc.shouldRefund.amount += amt; break
        case '待确定':
          acc.pending.count++; acc.pending.amount += amt; break
      }
    }
    return acc
  })

  // ─── Import from crossSheet ──────────────────────────────────────────

  function importFromCrossSheet(longTermRows: LongTermImportRow[]): void {
    if (isReadonly.value) return
    if (longTermRows.length === 0) return

    const imported: LongTermRow[] = longTermRows.map(r => ({
      rowId: generateRowId(),
      customerName: r.customerName,
      endBalance: r.endAudited,
      aging: r.agingDescription,
      businessDescription: '',
      reason: '',
      settlementAmount: 0,
      plan: '',
      remark: '',
    }))

    rows.value = [...rows.value, ...imported]
    persistRows()
  }

  // ─── addRow / removeRow / updateCell ─────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, createEmptyRow()]
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }
    if (field === 'endBalance' || field === 'settlementAmount') {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = value
    }

    const newRows = [...rows.value]
    newRows[idx] = row
    rows.value = newRows
    persistRows()
  }

  // ─── Audit Note / Conclusion ─────────────────────────────────────────

  const auditNote = ref('')
  const conclusion = ref('')

  watch(
    () => allResponses.value.get(ITEM_ID_NOTE)?.remark,
    (val) => { auditNote.value = val || '' },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_ID_CONCLUSION)?.remark,
    (val) => { conclusion.value = val || '' },
    { immediate: true },
  )

  watch(() => auditNote.value, (val) => { debouncedSave(ITEM_ID_NOTE, { remark: val }) })
  watch(() => conclusion.value, (val) => { debouncedSave(ITEM_ID_CONCLUSION, { remark: val }) })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    subtotalRow,
    disposalSummary,
    auditNote,
    conclusion,
    addRow,
    removeRow,
    updateCell,
    importFromCrossSheet,
  }
}

export default useD3LongTerm
