/**
 * useG11Adjustment — G11-3 调整分录汇总
 *
 * 编制逻辑（对齐 Excel「投资收益调整分录汇总表 G11-3」）：
 * 1. 列：调整事项说明 / 类别(账项调整·报表调整·其他) / 报表项目 / 科目 / 附注项目 / 借贷 / 索引 / 备注
 * 2. 「账项调整」影响审定数；「报表调整」仅影响列报，不回写 G11-1/G11-2
 * 3. 仅汇总 6111 贷−借净额，按「回写行」分项写入 G11-1 / G11-2
 * 4. 兼容旧字段 entryType/summary（导入与历史数据）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'
import {
  parseNum,
  calcSubtotal,
  isDebitCreditBalanced,
} from './useG11FormulaEngine'
import {
  aggregateG11AdjustmentByRow,
  applyG11AdjustmentWriteback,
  calcG11AdjustmentNet,
  parseG11AdjStore,
  summarizeG11Adjustment,
  type G11AdjustmentWritebackMap,
} from './g11AdjStorage'
import {
  G11_ADJ_ACCOUNT_OPTIONS,
  G11_ADJUDICATION_WRITEBACK_OPTIONS,
  inferG11AdjudicationRowKey,
  isG11AccountCode,
} from './g11AccountMatch'
import { G11_ACCOUNT_CODE } from './g11Constants'
import type { ChecklistResponse } from './useF1FormData'

export const G11_CATEGORY_OPTIONS = ['账项调整', '报表调整', '其他'] as const

export interface G11AdjustmentRow {
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
  /** 回写目标：G11-1/G11-2 分项 rowKey */
  adjudicationRowKey: string
  /** 兼容旧存档 / 模块同步 */
  entryType: 'AJE' | 'RJE'
  date: string
  preparedBy: string
  sourceGroupId?: string
}

const ITEM_ID_ROWS = 'G11-aje-rows'
const ITEM_ID_ADJ_ROWS = 'G11-adj-rows'
const BALANCE_TOLERANCE = 0.01
const G11_WP_CODE = 'G11'

/** 投资收益调整常见相关科目 */
const G11_RELATED_PREFIXES = ['6111', '1511', '1501', '1503', '1504', '6101', '1131', '1002', '4104']

function isG11RelatedAccount(code: string): boolean {
  const c = String(code || '').trim()
  return G11_RELATED_PREFIXES.some((p) => c === p || c.startsWith(p))
}

function categoryFromModule(t: string | undefined): string {
  const x = String(t || '').toLowerCase()
  if (x.includes('rje') || x.includes('报表') || x.includes('重分类')) return '报表调整'
  if (x.includes('其他')) return '其他'
  return '账项调整'
}

function generateRowId(): string {
  return `g11a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function categoryFromLegacy(raw: any): string {
  if (raw.category && G11_CATEGORY_OPTIONS.includes(raw.category)) return raw.category
  if (raw.entryType === 'RJE') return '报表调整'
  if (raw.entryType === 'AJE') return '账项调整'
  return '账项调整'
}

export function createEmptyG11AdjustmentRow(): G11AdjustmentRow {
  return {
    rowId: generateRowId(),
    description: '',
    category: '账项调整',
    reportItem: '投资收益',
    accountName: '投资收益',
    accountCode: G11_ACCOUNT_CODE,
    noteItem: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: 'G11-3',
    remark: '',
    adjudicationRowKey: 'other',
    entryType: 'AJE',
    date: todayIso(),
    preparedBy: '',
  }
}

function normalizeRow(raw: any): G11AdjustmentRow {
  const category = categoryFromLegacy(raw)
  const entryType: 'AJE' | 'RJE' = category === '报表调整' ? 'RJE' : 'AJE'
  const code = String(raw.accountCode ?? G11_ACCOUNT_CODE).trim() || G11_ACCOUNT_CODE
  const known = G11_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)
  const description = raw.description || raw.summary || ''
  const adjudicationRowKey = inferG11AdjudicationRowKey({
    adjudicationRowKey: raw.adjudicationRowKey,
    description,
    summary: raw.summary,
    noteItem: raw.noteItem,
    remark: raw.remark,
    accountName: raw.accountName,
  })
  return {
    rowId: raw.rowId || raw.id || generateRowId(),
    description,
    category,
    reportItem: raw.reportItem || '投资收益',
    accountName: (raw.accountName ?? known?.name ?? '').trim() || known?.name || '投资收益',
    accountCode: code,
    noteItem: raw.noteItem || '',
    debitAmount: parseNum(raw.debitAmount ?? raw.debit),
    creditAmount: parseNum(raw.creditAmount ?? raw.credit),
    indexRef: raw.indexRef || raw.index || 'G11-3',
    remark: raw.remark || '',
    adjudicationRowKey,
    entryType,
    date: raw.date || '',
    preparedBy: raw.preparedBy || '',
    sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
  }
}

function parseRows(json: string | null | undefined): G11AdjustmentRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

export interface UseG11AdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
  auditYear?: Ref<number | string | null | undefined> | ComputedRef<number | string | null | undefined>
  /** 分项回写至 G11-2（rowKey → 本期调整） */
  applyAdjustmentToDetail?: (byRow: G11AdjustmentWritebackMap) => void
}

export function useG11Adjustment(opts: UseG11AdjustmentOptions) {
  const rows = ref<G11AdjustmentRow[]>([])
  const syncing = ref(false)
  const lastSyncMsg = ref('')

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() =>
    isDebitCreditBalanced(
      rows.value.map((r) => r.debitAmount),
      rows.value.map((r) => r.creditAmount),
    ) || Math.abs(balanceDiff.value) < BALANCE_TOLERANCE,
  )
  const adjustmentNet = computed(() => calcG11AdjustmentNet(rows.value))
  const writebackPreview = computed(() => aggregateG11AdjustmentByRow(rows.value))
  const summary = computed(() => summarizeG11Adjustment(rows.value))

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
    syncWriteback()
  }

  function syncWriteback(): void {
    const byRow = aggregateG11AdjustmentByRow(rows.value)
    const store = parseG11AdjStore(opts.allResponses.value.get(ITEM_ID_ADJ_ROWS)?.remark)
    const patched = applyG11AdjustmentWriteback(store, byRow)
    opts.debouncedSave(ITEM_ID_ADJ_ROWS, { remark: JSON.stringify(patched) })
    opts.applyAdjustmentToDetail?.(byRow)
    try {
      window.dispatchEvent(new CustomEvent('g11:adjustment-synced', {
        detail: { byRow, netAdjustment: calcG11AdjustmentNet(rows.value) },
      }))
    } catch { /* silent */ }
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入调整事项说明', '新增调整分录', {
        inputPlaceholder: '如：补提权益法投资收益 / 跨期收益调整',
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      const desc = (value ?? '').trim()
      if (!desc) return
      const row = createEmptyG11AdjustmentRow()
      row.description = desc
      row.adjudicationRowKey = inferG11AdjudicationRowKey({ description: desc })
      rows.value = [...rows.value, row]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateRow(rowId: string, patch: Partial<G11AdjustmentRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r, ...patch }
      if (patch.category != null) {
        next.entryType = patch.category === '报表调整' ? 'RJE' : 'AJE'
      }
      if (patch.accountCode != null) {
        const known = G11_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === patch.accountCode)
        if (known && (patch.accountName == null || patch.accountName === r.accountName)) {
          next.accountName = known.name
        }
      }
      if (
        patch.description != null
        || patch.noteItem != null
        || patch.adjudicationRowKey != null
      ) {
        next.adjudicationRowKey = inferG11AdjudicationRowKey(next)
      }
      return normalizeRow(next)
    })
    persist()
  }

  function updateCell(rowId: string, field: keyof G11AdjustmentRow, value: unknown): void {
    if (field === 'debitAmount' || field === 'creditAmount') {
      updateRow(rowId, { [field]: parseNum(value) } as Partial<G11AdjustmentRow>)
    } else {
      updateRow(rowId, { [field]: String(value ?? '') } as Partial<G11AdjustmentRow>)
    }
  }

  function loadRows(data: G11AdjustmentRow[]): void {
    rows.value = data.map(normalizeRow)
    persist()
  }

  function tableRowClassName({ row }: { row: G11AdjustmentRow }): string {
    if (row.category === '报表调整' || row.entryType === 'RJE') return 'rje-row'
    if (isG11AccountCode(row.accountCode)) return 'g11-acct-row'
    return ''
  }

  function publishAdjustment(): void {
    if (!isBalanced.value) return
    syncWriteback()
    for (const row of rows.value) {
      if (row.debitAmount === 0 && row.creditAmount === 0) continue
      try {
        eventBus.emit('adjustment:created', {
          wpCode: G11_WP_CODE,
          entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
          amount: Math.max(row.debitAmount, row.creditAmount),
          accountCode: row.accountCode || G11_ACCOUNT_CODE,
          accountName: row.accountName,
          description: row.description,
          debitAmount: row.debitAmount,
          creditAmount: row.creditAmount,
          timestamp: Date.now(),
        })
      } catch { /* silent */ }
    }
    void pushToCentralModule()
  }

  async function pushToCentralModule(): Promise<number> {
    const projectId = opts.projectId?.value
    if (!projectId || opts.isReadonly.value || !isBalanced.value) return 0
    const year = Number(opts.auditYear?.value)
    if (!Number.isFinite(year) || year < 1900) return 0

    const pending = rows.value.filter(
      (r) => !r.sourceGroupId && (Math.abs(r.debitAmount) > 0.005 || Math.abs(r.creditAmount) > 0.005),
    )
    if (!pending.length) return 0

    const groups = new Map<string, G11AdjustmentRow[]>()
    for (const row of pending) {
      const key = `${row.category}||${row.description || row.rowId}`
      groups.set(key, [...(groups.get(key) || []), row])
    }

    let pushed = 0
    let list = [...rows.value]
    for (const lines of groups.values()) {
      const debit = lines.reduce((s, r) => s + r.debitAmount, 0)
      const credit = lines.reduce((s, r) => s + r.creditAmount, 0)
      if (Math.abs(debit - credit) >= 0.01) continue
      try {
        const res: any = await api.post(adjPaths.create(projectId), {
          adjustment_type: lines[0].category === '报表调整' ? 'rje' : 'aje',
          year,
          company_code: 'default',
          description: `[G11] ${lines[0].description || '投资收益调整'}`,
          line_items: lines.map((r) => ({
            standard_account_code: r.accountCode || G11_ACCOUNT_CODE,
            account_name: r.accountName || undefined,
            debit_amount: r.debitAmount,
            credit_amount: r.creditAmount,
          })),
        }, { _silent: true } as any)
        const groupId = res?.entry_group_id ?? res?.data?.entry_group_id ?? res?.id
        if (!groupId) continue
        const id = String(groupId)
        list = list.map((r) =>
          lines.some((l) => l.rowId === r.rowId) ? { ...r, sourceGroupId: id } : r,
        )
        pushed++
      } catch {
        lastSyncMsg.value = '底稿已保存，但部分分录未能同步至集中模块'
      }
    }
    if (pushed > 0) {
      rows.value = list
      opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
      eventBus.emit('adjustment:updated')
    }
    return pushed
  }

  async function syncFromAdjustmentModule(): Promise<number> {
    const projectId = opts.projectId?.value
    if (!projectId || opts.isReadonly.value) return 0
    syncing.value = true
    lastSyncMsg.value = ''
    try {
      const year = Number(opts.auditYear?.value) || new Date().getFullYear()
      const res: any = await api.get(adjPaths.list(projectId), {
        params: { year, page: 1, page_size: 200 },
        _silent: true,
      } as any)
      const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []
      if (!Array.isArray(items)) {
        lastSyncMsg.value = '未获取到调整分录'
        return 0
      }

      const imported: G11AdjustmentRow[] = []
      for (const entry of items) {
        const lines = entry.line_items || entry.lines || []
        if (!lines.some((li: any) => isG11RelatedAccount(li.standard_account_code || li.account_code))) {
          continue
        }
        const groupId = String(entry.entry_group_id || entry.id || '')
        for (const li of lines) {
          const accountCode = String(li.standard_account_code || li.account_code || '')
          if (!isG11RelatedAccount(accountCode)) continue
          imported.push(normalizeRow({
            description: entry.description || entry.adjustment_no || '调整分录模块同步',
            category: categoryFromModule(entry.adjustment_type || entry.type),
            reportItem: isG11AccountCode(accountCode) ? '投资收益' : '相关科目',
            accountName: li.account_name || accountCode,
            accountCode,
            debitAmount: li.debit_amount,
            creditAmount: li.credit_amount,
            indexRef: entry.adjustment_no || 'G11-3',
            remark: '来自调整分录模块',
            sourceGroupId: groupId,
          }))
        }
      }

      if (!imported.length) {
        lastSyncMsg.value = '调整分录模块中无与 6111 等相关的分录'
        return 0
      }

      const manual = rows.value.filter((r) => !r.sourceGroupId)
      rows.value = [...manual, ...imported]
      persist()
      lastSyncMsg.value = `已同步 ${imported.length} 行`
      return imported.length
    } catch {
      lastSyncMsg.value = '同步失败，请稍后重试'
      return 0
    } finally {
      syncing.value = false
    }
  }

  function pushToA13(rowIds: string[]): void {
    const selected = rows.value.filter((r) => rowIds.includes(r.rowId))
    if (!selected.length) return
    try {
      eventBus.emit('a13:push-misstatement', {
        items: selected.map((row) => ({
          wpCode: G11_WP_CODE,
          entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
          description: row.description,
          reportItem: row.reportItem,
          accountName: row.accountName,
          debitAmount: row.debitAmount,
          creditAmount: row.creditAmount,
          indexRef: row.indexRef,
        })),
        wpCode: G11_WP_CODE,
        timestamp: Date.now(),
      })
    } catch { /* silent */ }
  }

  function onModuleUpdated(): void {
    if (opts.projectId?.value && !opts.isReadonly.value) {
      void syncFromAdjustmentModule()
    }
  }

  eventBus.on('adjustment:updated', onModuleUpdated)
  eventBus.on('adjustment:saved', onModuleUpdated)

  onBeforeUnmount(() => {
    eventBus.off('adjustment:updated', onModuleUpdated)
    eventBus.off('adjustment:saved', onModuleUpdated)
  })

  return {
    rows,
    debitTotal,
    creditTotal,
    balanceDiff,
    isBalanced,
    adjustmentNet,
    writebackPreview,
    summary,
    syncing,
    lastSyncMsg,
    categoryOptions: G11_CATEGORY_OPTIONS,
    accountOptions: G11_ADJ_ACCOUNT_OPTIONS,
    writebackOptions: G11_ADJUDICATION_WRITEBACK_OPTIONS,
    addRow,
    removeRow,
    updateRow,
    updateCell,
    loadRows,
    syncWriteback,
    publishAdjustment,
    syncFromAdjustmentModule,
    pushToCentralModule,
    pushToA13,
    tableRowClassName,
    ITEM_ID_ROWS,
  }
}
