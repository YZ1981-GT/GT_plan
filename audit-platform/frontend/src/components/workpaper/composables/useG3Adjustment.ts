/**
 * useG3Adjustment — G3-3 调整分录汇总
 * 对齐 D4-4 / Excel「应收股利调整分录汇总表」列结构 + 调整分录模块联动（科目 1131）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useG3DivRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'
import {
  applyG3AdjustmentWriteback,
  computeG3NetAdjustments,
  parseG3AdjStore,
} from './g3AdjudicationItems'
import {
  G3_ACCOUNT_CODE,
  G3_ADJ_STORAGE_KEY,
  G3_ADJUSTMENT_ROWS_KEY,
  G3_WP_CODE,
} from './g3Constants'

export { G3_ACCOUNT_CODE }

/** 与 Excel G3-3 / D4-4 对齐的列 */
export interface G3AdjustmentRow {
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

const STORAGE_KEY = G3_ADJUSTMENT_ROWS_KEY
const LEGACY_STORAGE_KEY = 'G3-3-adjustment-rows'
const ADJ_STORAGE_KEY = G3_ADJ_STORAGE_KEY
const BALANCE_TOLERANCE = 0.005

/** 应收股利及相关投资收益科目前缀 */
const G3_RELATED_PREFIXES = ['1131', '6111']

function generateRowId(): string {
  return `g3a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

export function createEmptyG3AdjustmentRow(): G3AdjustmentRow {
  return {
    rowId: generateRowId(),
    description: '',
    category: '账项调整',
    reportItem: '应收股利',
    accountName: '应收股利',
    accountCode: G3_ACCOUNT_CODE,
    noteItem: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: 'G3-3',
    remark: '',
  }
}

function normalizeRow(raw: any): G3AdjustmentRow {
  return {
    rowId: raw.rowId || raw.id || generateRowId(),
    description: raw.description || raw.summary || '',
    category: raw.category
      || (raw.entryType === 'RJE' ? '报表调整' : raw.entryType === 'AJE' ? '账项调整' : '账项调整'),
    reportItem: raw.reportItem || '应收股利',
    accountName: raw.accountName || '',
    accountCode: raw.accountCode || G3_ACCOUNT_CODE,
    noteItem: raw.noteItem || '',
    debitAmount: parseNum(raw.debitAmount ?? raw.debit),
    creditAmount: parseNum(raw.creditAmount ?? raw.credit),
    indexRef: raw.indexRef || 'G3-3',
    remark: raw.remark || '',
    sourceGroupId: raw.sourceGroupId,
  }
}

function safeParseRows(jsonStr: string | null | undefined): G3AdjustmentRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function isG3RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return G3_RELATED_PREFIXES.some((p) => c === p || c.startsWith(p))
}

function categoryFromType(t: string | undefined): string {
  const x = String(t || '').toLowerCase()
  if (x.includes('rje') || x.includes('报表') || x.includes('重分类')) return '报表调整'
  if (x.includes('其他')) return '其他'
  return '账项调整'
}

export function useG3Adjustment(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
  wpId: Ref<string>
  projectId: Ref<string>
  auditYear?: Ref<number | string | null | undefined>
}) {
  const rows = ref<G3AdjustmentRow[]>([])
  const syncing = ref(false)
  const lastSyncMsg = ref('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  function readStoredJson(): string | null | undefined {
    const primary = opts.allResponses.value.get(STORAGE_KEY)
    const legacy = opts.allResponses.value.get(LEGACY_STORAGE_KEY)
    return primary?.remark || primary?.conclusion || legacy?.remark || legacy?.conclusion || null
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

  /** 影响 1131 的净账项/报表调整（借−贷；资产增加为正） */
  const netAdjustments = computed(() => computeG3NetAdjustments(rows.value))

  function persistRows(): void {
    if (opts.isReadonly.value) return
    const json = JSON.stringify(rows.value)
    opts.debouncedSave(STORAGE_KEY, { remark: json, conclusion: json })
  }

  function addRow(): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, createEmptyG3AdjustmentRow()]
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persistRows()
  }

  function updateCell(rowId: string, field: keyof G3AdjustmentRow, value: unknown): void {
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
        eventBus.emit('adjustment:created', {
          wpCode: G3_WP_CODE,
          entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
          amount: Math.max(row.debitAmount, row.creditAmount),
          accountCode: row.accountCode || G3_ACCOUNT_CODE,
          accountName: row.accountName,
          description: row.description,
          debitAmount: row.debitAmount,
          creditAmount: row.creditAmount,
          timestamp: Date.now(),
        })
      } catch {
        /* silent */
      }
    }

    const { netAJE, netRJE } = netAdjustments.value
    try {
      const raw = opts.allResponses.value.get(ADJ_STORAGE_KEY)?.remark
      const store = applyG3AdjustmentWriteback(parseG3AdjStore(raw), netAJE, netRJE)
      opts.debouncedSave(ADJ_STORAGE_KEY, { conclusion: null, remark: JSON.stringify(store) })
    } catch {
      /* silent */
    }

    try {
      eventBus.emit('g3:adjustment-confirmed', {
        accountCode: G3_ACCOUNT_CODE,
        netAJE,
        netRJE,
        rowCount: rows.value.length,
      })
    } catch {
      /* silent */
    }

    // 底稿 → 集中调整表：未同步过的分录组 POST（按描述聚合借贷）
    void pushConfirmedToCentralModule()
  }

  /** 将确认分录写入集中 adjustments 表（单向；已带 sourceGroupId 的跳过） */
  async function pushConfirmedToCentralModule(): Promise<void> {
    if (!opts.projectId.value || opts.isReadonly.value) return
    const yearRaw = opts.auditYear?.value
    const year = Number(yearRaw)
    if (!Number.isFinite(year) || year < 1900) return

    const pending = rows.value.filter(
      (r) => !r.sourceGroupId && (r.debitAmount !== 0 || r.creditAmount !== 0),
    )
    if (!pending.length) return

    // 按描述+类别分组，凑齐借贷对后写入
    const groups = new Map<string, G3AdjustmentRow[]>()
    for (const row of pending) {
      const key = `${row.category}||${row.description || row.rowId}`
      const arr = groups.get(key) ?? []
      arr.push(row)
      groups.set(key, arr)
    }

    let pushed = 0
    for (const [, lines] of groups) {
      const debitSum = lines.reduce((s, r) => s + r.debitAmount, 0)
      const creditSum = lines.reduce((s, r) => s + r.creditAmount, 0)
      if (Math.abs(debitSum - creditSum) > 0.01) continue // 不平衡组跳过，勿污染集中台账
      const adjustment_type = lines[0].category === '报表调整' ? 'rje' : 'aje'
      try {
        const res: any = await api.post(adjPaths.create(opts.projectId.value), {
          adjustment_type,
          year,
          company_code: 'default',
          description: `[G3] ${lines[0].description || '应收股利调整'}`,
          line_items: lines.map((r) => ({
            standard_account_code: r.accountCode || G3_ACCOUNT_CODE,
            account_name: r.accountName || undefined,
            debit_amount: r.debitAmount,
            credit_amount: r.creditAmount,
          })),
        }, { _silent: true } as any)
        const groupId = res?.entry_group_id ?? res?.data?.entry_group_id ?? res?.id
        if (groupId) {
          const id = String(groupId)
          rows.value = rows.value.map((r) =>
            lines.some((l) => l.rowId === r.rowId) ? { ...r, sourceGroupId: id } : r,
          )
          pushed++
        }
      } catch {
        /* 集中表写入失败不阻断底稿确认 */
      }
    }
    if (pushed > 0) {
      persistRows()
      eventBus.emit('adjustment:updated')
    }
  }

  function pushToA13(rowIds: string[]): void {
    const selected = rows.value.filter((r) => rowIds.includes(r.rowId))
    if (!selected.length) return
    try {
      eventBus.emit('a13:push-misstatement', {
        items: selected.map((row) => ({
          wpCode: G3_WP_CODE,
          entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
          description: row.description,
          reportItem: row.reportItem,
          accountName: row.accountName,
          debitAmount: row.debitAmount,
          creditAmount: row.creditAmount,
          indexRef: row.indexRef,
        })),
        wpCode: G3_WP_CODE,
        timestamp: Date.now(),
      })
    } catch {
      /* silent */
    }
  }

  /** 从调整分录模块拉取涉及 1131 等相关科目的分录行 */
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

      const imported: G3AdjustmentRow[] = []
      for (const entry of items) {
        const lines = entry.line_items || entry.lines || []
        const related = lines.filter((li: any) =>
          isG3RelatedAccount(li.standard_account_code || li.account_code || ''),
        )
        if (!related.length) continue
        for (const li of related) {
          const code = String(li.standard_account_code || li.account_code || '')
          imported.push({
            rowId: generateRowId(),
            description: entry.description || entry.adjustment_no || '调整分录模块同步',
            category: categoryFromType(entry.adjustment_type || entry.type),
            reportItem: code.startsWith('1131') ? '应收股利' : '投资收益',
            accountName: li.account_name || code,
            accountCode: code,
            noteItem: '',
            debitAmount: parseNum(li.debit_amount),
            creditAmount: parseNum(li.credit_amount),
            indexRef: entry.adjustment_no || 'G3-3',
            remark: '来自调整分录模块',
            sourceGroupId: entry.entry_group_id || entry.id,
          })
        }
      }

      if (!imported.length) {
        lastSyncMsg.value = '调整分录模块中无与 1131 等相关的分录'
        return 0
      }

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

  eventBus.on('adjustment:updated', onModuleUpdated)
  eventBus.on('adjustment:saved', onModuleUpdated)

  onBeforeUnmount(() => {
    eventBus.off('adjustment:updated', onModuleUpdated)
    eventBus.off('adjustment:saved', onModuleUpdated)
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
  })

  return {
    rows: rows as Ref<G3AdjustmentRow[]>,
    debitTotal: debitTotal as ComputedRef<number>,
    creditTotal: creditTotal as ComputedRef<number>,
    balanceDiff: balanceDiff as ComputedRef<number>,
    isBalanced: isBalanced as ComputedRef<boolean>,
    netAdjustments,
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

export default useG3Adjustment
