/**
 * useG2Adjustment — G2-4 调整分录汇总
 * 对齐 D4-4 / Excel「应收利息调整分录汇总表」列结构 + 调整分录模块联动（科目 1132）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useG2IntRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import {
  G2_ACCOUNT_CODE,
  applyG2AdjustmentWriteback,
  G2_ADJ_WRITEBACK_ROW_KEY,
  parseG2AdjStore,
} from './g2AdjudicationItems'

export { G2_ACCOUNT_CODE }

/** 与 Excel G2-4 / D4-4 对齐的列 */
export interface G2AdjustmentRow {
  rowId: string
  description: string
  category: string
  reportItem: string
  accountName: string
  accountCode: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** 来自调整分录模块时带 entry_group_id */
  sourceGroupId?: string
}

const STORAGE_KEY = 'G2-4-rows'
const BALANCE_TOLERANCE = 0.005

/** 应收利息及相关损益/减值科目前缀 */
const G2_RELATED_PREFIXES = ['1132', '1231', '6101', '6111']

function generateRowId(): string {
  return `g2a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

export function createEmptyG2AdjustmentRow(): G2AdjustmentRow {
  return {
    rowId: generateRowId(),
    description: '',
    category: '账项调整',
    reportItem: '应收利息',
    accountName: '应收利息',
    accountCode: G2_ACCOUNT_CODE,
    noteItem: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: 'G2-4',
    remark: '',
  }
}

function normalizeRow(raw: any): G2AdjustmentRow {
  return {
    rowId: raw.rowId || raw.id || generateRowId(),
    description: raw.description || raw.summary || '',
    category: raw.category
      || (raw.entryType === 'RJE' ? '报表调整' : raw.entryType === 'AJE' ? '账项调整' : '账项调整'),
    reportItem: raw.reportItem || '应收利息',
    accountName: raw.accountName || '',
    accountCode: raw.accountCode || G2_ACCOUNT_CODE,
    noteItem: raw.noteItem || '',
    debitAmount: parseNum(raw.debitAmount ?? raw.debit),
    creditAmount: parseNum(raw.creditAmount ?? raw.credit),
    indexRef: raw.indexRef || 'G2-4',
    remark: raw.remark || '',
    sourceGroupId: raw.sourceGroupId,
  }
}

function safeParseRows(jsonStr: string | null | undefined): G2AdjustmentRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function isG2RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return G2_RELATED_PREFIXES.some((p) => c === p || c.startsWith(p))
}

function categoryFromType(t: string | undefined): string {
  const x = String(t || '').toLowerCase()
  if (x.includes('rje') || x.includes('报表') || x.includes('重分类')) return '报表调整'
  if (x.includes('其他')) return '其他'
  return '账项调整'
}

export function useG2Adjustment(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
  wpId: Ref<string>
  projectId: Ref<string>
  auditYear?: Ref<number | string | null | undefined>
}) {
  const rows = ref<G2AdjustmentRow[]>([])
  const syncing = ref(false)
  const lastSyncMsg = ref('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  function readStoredJson(): string | null | undefined {
    const item = opts.allResponses.value.get(STORAGE_KEY)
    return item?.remark || item?.conclusion || null
  }

  function loadRows(): void {
    rows.value = safeParseRows(readStoredJson())
  }

  watch(
    () => readStoredJson(),
    () => loadRows(),
    { immediate: true },
  )

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  /** 影响 1132 的净调整（借−贷，资产增加为正）；报表调整不计入 */
  const netAjeToG2 = computed(() => {
    let net = 0
    for (const r of rows.value) {
      const related =
        isG2RelatedAccount(r.accountCode)
        || String(r.accountName).includes('应收利息')
      if (!related) continue
      if (r.category === '报表调整') continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  function persistRows(): void {
    if (opts.isReadonly.value) return
    const json = JSON.stringify(rows.value)
    opts.debouncedSave(STORAGE_KEY, { remark: json, conclusion: json })
  }

  function addRow(): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, createEmptyG2AdjustmentRow()]
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persistRows()
  }

  function updateCell(rowId: string, field: keyof G2AdjustmentRow, value: unknown): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      if (field === 'debitAmount' || field === 'creditAmount') {
        return { ...r, [field]: parseNum(value) }
      }
      return { ...r, [field]: String(value ?? '') }
    })
    persistRows()
  }

  function publishAdjustment(): void {
    for (const row of rows.value) {
      if (row.debitAmount === 0 && row.creditAmount === 0) continue
      try {
        window.dispatchEvent(
          new CustomEvent('adjustment:created', {
            detail: {
              wpCode: 'G2',
              entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
              amount: Math.max(row.debitAmount, row.creditAmount),
              accountCode: row.accountCode || G2_ACCOUNT_CODE,
              accountName: row.accountName,
              description: row.description,
              debitAmount: row.debitAmount,
              creditAmount: row.creditAmount,
              timestamp: Date.now(),
            },
          }),
        )
      } catch {
        /* silent */
      }
    }

    // 直接回写 G2-1 审定表（即使审定表未挂载也能落库）
    const net = netAjeToG2.value
    try {
      const raw = opts.allResponses.value.get('G2-1-rows')?.remark
      const store = applyG2AdjustmentWriteback(parseG2AdjStore(raw), net, G2_ADJ_WRITEBACK_ROW_KEY)
      opts.debouncedSave('G2-1-rows', { remark: JSON.stringify(store) })
    } catch {
      /* silent */
    }

    try {
      window.dispatchEvent(
        new CustomEvent('g2:adjustment-confirmed', {
          detail: {
            accountCode: G2_ACCOUNT_CODE,
            netAdjustment: net,
            rowKey: G2_ADJ_WRITEBACK_ROW_KEY,
            rowCount: rows.value.length,
          },
        }),
      )
    } catch {
      /* silent */
    }
  }

  function pushToA13(rowIds: string[]): void {
    const selected = rows.value.filter((r) => rowIds.includes(r.rowId))
    if (!selected.length) return
    try {
      window.dispatchEvent(
        new CustomEvent('a13:push-misstatement', {
          detail: {
            items: selected.map((row) => ({
              wpCode: 'G2',
              entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
              description: row.description,
              reportItem: row.reportItem,
              accountName: row.accountName,
              debitAmount: row.debitAmount,
              creditAmount: row.creditAmount,
              indexRef: row.indexRef,
            })),
          },
        }),
      )
    } catch {
      /* silent */
    }
  }

  /** 从调整分录模块拉取涉及 1132 等相关科目的分录行 */
  async function syncFromAdjustmentModule(): Promise<number> {
    if (opts.isReadonly.value || !opts.projectId.value) return 0
    syncing.value = true
    lastSyncMsg.value = ''
    try {
      const yearRaw = opts.auditYear?.value
      const year = Number(yearRaw) || new Date().getFullYear()
      const res: any = await api.get(adjPaths.list(opts.projectId.value), {
        params: { year, page: 1, page_size: 200 },
        _silent: true,
      } as any)
      const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []
      if (!Array.isArray(items)) {
        lastSyncMsg.value = '未获取到调整分录'
        return 0
      }

      const imported: G2AdjustmentRow[] = []
      for (const entry of items) {
        const lines = entry.line_items || entry.lines || []
        const related = lines.filter((li: any) =>
          isG2RelatedAccount(li.standard_account_code || li.account_code || ''),
        )
        if (!related.length) continue
        for (const li of related) {
          const code = String(li.standard_account_code || li.account_code || '')
          imported.push({
            rowId: generateRowId(),
            description: entry.description || entry.adjustment_no || '调整分录模块同步',
            category: categoryFromType(entry.adjustment_type || entry.type),
            reportItem: '应收利息',
            accountName: li.account_name || code,
            accountCode: code,
            noteItem: '',
            debitAmount: parseNum(li.debit_amount),
            creditAmount: parseNum(li.credit_amount),
            indexRef: entry.adjustment_no || 'G2-4',
            remark: '来自调整分录模块',
            sourceGroupId: entry.entry_group_id || entry.id,
          })
        }
      }

      if (!imported.length) {
        lastSyncMsg.value = '调整分录模块中无与 1132 等相关的分录'
        return 0
      }

      // 合并：保留手工行（无 sourceGroupId），替换已同步行
      const manual = rows.value.filter((r) => !r.sourceGroupId)
      rows.value = [...manual, ...imported]
      persistRows()
      lastSyncMsg.value = `已同步 ${imported.length} 行`
      return imported.length
    } catch {
      lastSyncMsg.value = '同步失败，请稍后重试'
      return 0
    } finally {
      syncing.value = false
    }
  }

  function onModuleUpdated() {
    if (opts.projectId.value && !opts.isReadonly.value) {
      void syncFromAdjustmentModule()
    }
  }

  window.addEventListener('adjustment:updated', onModuleUpdated)
  window.addEventListener('adjustment:saved', onModuleUpdated)

  onBeforeUnmount(() => {
    window.removeEventListener('adjustment:updated', onModuleUpdated)
    window.removeEventListener('adjustment:saved', onModuleUpdated)
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
  })

  return {
    rows: rows as Ref<G2AdjustmentRow[]>,
    debitTotal: debitTotal as ComputedRef<number>,
    creditTotal: creditTotal as ComputedRef<number>,
    balanceDiff: balanceDiff as ComputedRef<number>,
    isBalanced: isBalanced as ComputedRef<boolean>,
    netAjeToG2,
    syncing,
    lastSyncMsg,
    addRow,
    removeRow,
    updateCell,
    publishAdjustment,
    pushToA13,
    syncFromAdjustmentModule,
    loadRows,
  }
}

export default useG2Adjustment
