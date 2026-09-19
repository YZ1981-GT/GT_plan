/**
 * useH10Adjustment — H10-3 调整分录（AJE/RJE 回写 H10-1）
 */
import { computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { H10_ACCOUNT_CODE } from './h10Constants'
import {
  aggregateH10AdjustmentAjeRje,
  aggregateH10AdjustmentByRow,
  applyH10AdjustmentWriteback,
  calcH10AdjustmentNet,
  parseH10AdjStore,
  patchH10AdjRow,
  type H10AdjRowStore,
} from './h10AdjStorage'
import { parseNum, isDebitCreditBalanced } from './useH10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface H10AdjustmentEntry {
  rowId: string
  seq: number
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparedBy: string
  remark: string
}

const ITEM_ID_ROWS = 'H10-adjustment-rows'
const ITEM_ID_ADJ_ROWS = 'H10-adj-rows'
export const H10_ADJ_OVERLAY_ID = 'H10-adj-overlay'

function genId(): string {
  return `h10a-${Date.now().toString(36)}`
}

function normalizeEntry(raw: any, idx: number): H10AdjustmentEntry {
  return {
    rowId: raw.rowId || raw.id || genId(),
    seq: raw.seq ?? idx + 1,
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    date: raw.date ?? '',
    summary: raw.summary ?? '',
    accountCode: raw.accountCode ?? H10_ACCOUNT_CODE,
    accountName: raw.accountName ?? '资产处置损益',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    preparedBy: raw.preparedBy ?? '',
    remark: raw.remark ?? '',
  }
}

function parseRows(json: string | null | undefined): H10AdjustmentEntry[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    return Array.isArray(arr) ? arr.map(normalizeEntry) : []
  } catch {
    return []
  }
}

export function useH10Adjustment(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  applyAdjustmentToAdjudication?: (aje: number, rje: number) => void
}) {
  const rows = computed(() => parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark))

  const balanceOk = computed(() =>
    isDebitCreditBalanced(rows.value.map((r) => r.debitAmount), rows.value.map((r) => r.creditAmount)),
  )

  const balanceDiff = computed(() => {
    const d = rows.value.reduce((s, r) => s + parseNum(r.debitAmount), 0)
    const c = rows.value.reduce((s, r) => s + parseNum(r.creditAmount), 0)
    return d - c
  })

  const adjustmentNet = computed(() => calcH10AdjustmentNet(rows.value))
  const writebackPreview = computed(() => aggregateH10AdjustmentAjeRje(rows.value))

  function persist(list: H10AdjustmentEntry[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
    syncWriteback(list)
  }

  function syncWriteback(list = rows.value): void {
    const wb = aggregateH10AdjustmentAjeRje(list)
    opts.debouncedSave(H10_ADJ_OVERLAY_ID, { remark: JSON.stringify(wb) })

    // 按目标行分组回写（P1 智能推断：对方科目/摘要→分类行，不再全写 fixed_asset_disposal）
    const grouped = aggregateH10AdjustmentByRow(list.map(r => ({
      ...r,
      summary: r.summary,
      counterAccountCode: '', // TODO: 分录目前无对方科目字段，靠摘要推断
    })))
    let store: H10AdjRowStore = parseH10AdjStore(opts.allResponses.value.get(ITEM_ID_ADJ_ROWS)?.remark)
    // 先清零所有行的 AJE/RJE（避免旧分配残留）
    for (const key of Object.keys(store)) {
      if (store[key]?.currentAje || store[key]?.currentRje) {
        store = patchH10AdjRow(store, key, { currentAje: 0, currentRje: 0 })
      }
    }
    // 按推断目标行分别写入
    for (const g of grouped) {
      store = patchH10AdjRow(store, g.rowKey, { currentAje: g.currentAje, currentRje: g.currentRje })
    }
    opts.debouncedSave(ITEM_ID_ADJ_ROWS, { remark: JSON.stringify(store) })

    const totalAje = grouped.reduce((s, g) => s + g.currentAje, 0)
    const totalRje = grouped.reduce((s, g) => s + g.currentRje, 0)
    opts.applyAdjustmentToAdjudication?.(totalAje, totalRje)
    publishAdjustmentEvents(list)
    try {
      window.dispatchEvent(new CustomEvent('h10:adjustment-writeback', { detail: wb }))
    } catch { /* silent */ }
  }

  function publishAdjustmentEvents(list: H10AdjustmentEntry[]): void {
    const wb = aggregateH10AdjustmentAjeRje(list)
    const emitOne = (entryType: 'AJE' | 'RJE', amount: number) => {
      if (Math.abs(amount) <= 0.001) return
      const payload = {
        wpCode: 'H10',
        entryType,
        amount,
        accountCode: H10_ACCOUNT_CODE,
        accountName: '资产处置损益',
        description: `H10-3 ${entryType} 净额 ${amount}`,
      }
      // 只走 eventBus，crossWpEventBridge 自动桥接 window（消除双投）
      try {
        eventBus.emit('adjustment:created', payload as any)
      } catch { /* silent */ }
    }
    emitOne('AJE', wb.currentAje)
    emitOne('RJE', wb.currentRje)
  }

  function updateRow(rowId: string, patch: Partial<H10AdjustmentEntry>): void {
    if (opts.isReadonly.value) return
    const list = rows.value.map((r) => (r.rowId === rowId ? normalizeEntry({ ...r, ...patch }, r.seq - 1) : r))
    persist(list)
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入摘要', '新增调整分录', { inputPlaceholder: '摘要' })
      const summary = (value ?? '').trim()
      if (!summary) return
      persist([
        ...rows.value,
        {
          rowId: genId(),
          seq: rows.value.length + 1,
          entryType: 'AJE',
          date: '',
          summary,
          accountCode: H10_ACCOUNT_CODE,
          accountName: '资产处置损益',
          debitAmount: 0,
          creditAmount: 0,
          preparedBy: '',
          remark: '',
        },
      ])
    } catch { /* cancelled */ }
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    persist(rows.value.filter((r) => r.rowId !== rowId).map((r, i) => ({ ...r, seq: i + 1 })))
  }

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    () => { /* rows computed */ },
    { immediate: true },
  )

  return {
    rows,
    balanceOk,
    isBalanced: balanceOk,
    balanceDiff,
    adjustmentNet,
    writebackPreview,
    updateRow,
    addRow,
    removeRow,
    syncWriteback,
    ITEM_ID_ROWS,
  }
}
