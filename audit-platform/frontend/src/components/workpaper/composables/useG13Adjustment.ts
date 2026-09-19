/**
 * useG13Adjustment — G13-3 调整分录汇总
 *
 * 编制逻辑（对齐 Excel「公允价值变动收益调整分录汇总表 G13-3」）：
 * 1. 列：调整事项说明 / 类别(账项调整·报表调整·其他) / 报表项目 / 科目 / 附注项目 / 借贷 / 索引 / 备注
 * 2. 「账项调整」影响审定数；「报表调整」仅影响列报，不回写 G13-2
 * 3. 仅汇总 6101 贷−借净额，按「所属科目」分项写入 G13-2 明细表
 * 4. 兼容旧字段 entryType/summary/accountCode/preparedBy（导入与历史数据）
 * 5. 与中央调整分录模块双向同步；可推送 A13 错报汇总
 */
import { ref, computed, watch, onBeforeUnmount, getCurrentInstance, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from './useG13FormulaEngine'
import { mapCutoffToG13Adjustment, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import type { ChecklistResponse } from './useF1FormData'
import { G13_ACCOUNT_CODE, G13_BELONG_ACCOUNT_LABELS, G13_BELONG_ACCOUNTS } from './g13Constants'
import {
  G13_ADJ_ACCOUNT_OPTIONS,
  G13_AJE_ADJ_OVERLAY_ID,
  G13_CATEGORY_OPTIONS,
  aggregateG13AdjustmentByAdjRow,
  aggregateG13AdjustmentByBelong,
  calcG13AdjustmentNet,
  categoryFromLegacy,
  categoryFromModule,
  inferG13BelongAccount,
  isG13AccountCode,
  isG13RelatedAccount,
  summarizeG13Adjustment,
  type G13AdjustmentWritebackMap,
} from './g13AdjStorage'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'
import { useWorkpaperAuditYear } from './workpaperAuditYear'

export interface G13AdjustmentRow {
  rowId: string
  /** 调整事项说明（Excel A 列） */
  description: string
  /** 类别：账项调整 / 报表调整 / 其他 */
  category: string
  reportItem: string
  accountName: string
  accountCode: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** 回写目标：G1/G8/G9/G10/H3/other → G13-2 所属科目 */
  belongAccount: string
  /** 兼容旧存档 / 截止回填 */
  entryType: 'AJE' | 'RJE'
  date: string
  preparedBy: string
  /** 中央调整分录模块 entry_group_id（有值表示来自模块或已推送） */
  sourceGroupId?: string
  /** @deprecated 旧摘要字段，读档时并入 description */
  summary?: string
}

const ITEM_ID_ROWS = 'G13-aje-rows'
const BALANCE_TOLERANCE = 0.01
const G13_WP_CODE = 'G13'

export { G13_CATEGORY_OPTIONS, G13_ADJ_ACCOUNT_OPTIONS, G13_AJE_ADJ_OVERLAY_ID }

export const G13_BELONG_WRITEBACK_OPTIONS = [
  ...G13_BELONG_ACCOUNTS.map((code) => ({
    value: code,
    label: G13_BELONG_ACCOUNT_LABELS[code] ?? code,
  })),
  { value: 'other', label: '其他' },
]

function generateRowId(): string {
  return `g13a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export function createEmptyG13AdjustmentRow(): G13AdjustmentRow {
  return {
    rowId: generateRowId(),
    description: '',
    category: '账项调整',
    reportItem: '公允价值变动收益',
    accountName: '公允价值变动收益',
    accountCode: G13_ACCOUNT_CODE,
    noteItem: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: 'G13-3',
    remark: '',
    belongAccount: 'other',
    entryType: 'AJE',
    date: todayIso(),
    preparedBy: '',
  }
}

function normalizeRow(raw: any): G13AdjustmentRow {
  const category = categoryFromLegacy(raw)
  const entryType: 'AJE' | 'RJE' = category === '报表调整' ? 'RJE' : 'AJE'
  const code = String(raw.accountCode ?? G13_ACCOUNT_CODE).trim() || G13_ACCOUNT_CODE
  const known = G13_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)
  const description = String(raw.description || raw.summary || '').trim()
  const belongAccount = inferG13BelongAccount({
    belongAccount: raw.belongAccount,
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
    reportItem: raw.reportItem || (isG13AccountCode(code) ? '公允价值变动收益' : '相关科目'),
    accountName: (raw.accountName ?? known?.name ?? '').trim() || known?.name || '公允价值变动收益',
    accountCode: code,
    noteItem: raw.noteItem || '',
    debitAmount: parseNum(raw.debitAmount ?? raw.debit),
    creditAmount: parseNum(raw.creditAmount ?? raw.credit),
    indexRef: raw.indexRef || raw.index || 'G13-3',
    remark: raw.remark || '',
    belongAccount,
    entryType,
    date: raw.date || '',
    preparedBy: raw.preparedBy || '',
    sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
  }
}

function parseRows(json: string | null | undefined): G13AdjustmentRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

export interface UseG13AdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
  auditYear?: Ref<number | string | null | undefined> | ComputedRef<number | string | null | undefined>
  /** 按所属科目分项回写 G13-2 调整数 */
  applyAdjustmentToDetail?: (byBelong: G13AdjustmentWritebackMap) => void
}

export function useG13Adjustment(options: UseG13AdjustmentOptions) {
  const rows = ref<G13AdjustmentRow[]>([])
  const syncing = ref(false)
  const lastSyncMsg = ref('')
  const auditYearRef = useWorkpaperAuditYear(options.auditYear)

  watch(
    () => options.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )

  function persist(): void {
    options.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() =>
    isDebitCreditBalanced(
      rows.value.map((r) => r.debitAmount),
      rows.value.map((r) => r.creditAmount),
    ) || Math.abs(balanceDiff.value) < BALANCE_TOLERANCE,
  )
  const adjustmentNet = computed(() => calcG13AdjustmentNet(rows.value))
  const writebackPreview = computed(() => aggregateG13AdjustmentByBelong(rows.value))
  const summary = computed(() => summarizeG13Adjustment(rows.value))

  function addRow(): void {
    if (options.isReadonly.value) return
    rows.value = [...rows.value, createEmptyG13AdjustmentRow()]
    persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateRow(rowId: string, patch: Partial<G13AdjustmentRow>): void {
    if (options.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r, ...patch }
      if (patch.category != null) {
        next.entryType = patch.category === '报表调整' ? 'RJE' : 'AJE'
      }
      if (patch.accountCode != null) {
        const known = G13_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === patch.accountCode)
        if (known && (patch.accountName == null || patch.accountName === r.accountName)) {
          next.accountName = known.name
        }
      }
      if (patch.belongAccount != null) {
        next.belongAccount = patch.belongAccount
      } else if (
        patch.description != null
        || patch.noteItem != null
        || patch.remark != null
      ) {
        // 仅在仍为「其他」时按摘要自动推断，避免覆盖人工选择
        if (!next.belongAccount || next.belongAccount === 'other') {
          next.belongAccount = inferG13BelongAccount({ ...next, belongAccount: '' })
        }
      }
      return next
    })
    persist()
  }

  function updateCell(rowId: string, field: keyof G13AdjustmentRow, value: unknown): void {
    if (field === 'debitAmount' || field === 'creditAmount') {
      updateRow(rowId, { [field]: parseNum(value) } as Partial<G13AdjustmentRow>)
      return
    }
    if (field === 'entryType') {
      const et = value === 'RJE' ? 'RJE' : 'AJE'
      updateRow(rowId, {
        entryType: et,
        category: et === 'RJE' ? '报表调整' : '账项调整',
      })
      return
    }
    updateRow(rowId, { [field]: value } as Partial<G13AdjustmentRow>)
  }

  /** 将 6101 账项净额按审定表 rowKey 写入 overlay，供 G13-1 直接取数 */
  function syncToAdjudicationOverlay(): G13AdjustmentWritebackMap {
    const byAdj = aggregateG13AdjustmentByAdjRow(rows.value)
    options.debouncedSave(G13_AJE_ADJ_OVERLAY_ID, { remark: JSON.stringify(byAdj) })
    window.dispatchEvent(new CustomEvent('g13:aje-overlay-updated', {
      detail: { overlay: byAdj, netAdjustment: calcG13AdjustmentNet(rows.value) },
    }))
    return byAdj
  }

  function syncToDetail(): void {
    const byBelong = aggregateG13AdjustmentByBelong(rows.value)
    const byAdj = syncToAdjudicationOverlay()
    options.applyAdjustmentToDetail?.(byBelong)
    window.dispatchEvent(new CustomEvent('g13:adjustment-synced', {
      detail: { byBelong, byAdj, netAdjustment: calcG13AdjustmentNet(rows.value) },
    }))
  }

  function applyCutoffResults(samples: ExtractedVoucher[], fillMode: FillMode): void {
    if (options.isReadonly.value || !samples.length) return
    const mapped = samples.map(mapCutoffToG13Adjustment)
    rows.value = mergeByFillMode(
      rows.value,
      mapped,
      fillMode,
      (r) => `${r.date}|${r.description}|${r.debitAmount}|${r.creditAmount}`,
    )
    persist()
  }

  function tableRowClassName({ row }: { row: G13AdjustmentRow }): string {
    if (row.category === '报表调整' || row.entryType === 'RJE') return 'rje-row'
    if (isG13AccountCode(row.accountCode)) return 'g13-acct-row'
    return ''
  }

  async function pushToCentralModule(): Promise<number> {
    const projectId = options.projectId?.value
    if (!projectId || options.isReadonly.value || !isBalanced.value) return 0
    const year = Number(auditYearRef.value)
    if (!Number.isFinite(year) || year < 1900) return 0

    const pending = rows.value.filter(
      (r) => !r.sourceGroupId && (Math.abs(r.debitAmount) > 0.005 || Math.abs(r.creditAmount) > 0.005),
    )
    if (!pending.length) return 0

    const groups = new Map<string, G13AdjustmentRow[]>()
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
          description: `[G13] ${lines[0].description || '公允价值变动收益调整'}`,
          line_items: lines.map((r) => ({
            standard_account_code: r.accountCode || G13_ACCOUNT_CODE,
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
      options.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
      eventBus.emit('adjustment:updated')
    }
    return pushed
  }

  function publishAdjustment(): void {
    if (!isBalanced.value) return
    syncToDetail()
    for (const row of rows.value) {
      if (row.debitAmount === 0 && row.creditAmount === 0) continue
      try {
        eventBus.emit('adjustment:created', {
          wpCode: G13_WP_CODE,
          entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
          amount: Math.max(row.debitAmount, row.creditAmount),
          accountCode: row.accountCode || G13_ACCOUNT_CODE,
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

  async function syncFromAdjustmentModule(): Promise<number> {
    const projectId = options.projectId?.value
    if (!projectId || options.isReadonly.value) return 0
    syncing.value = true
    lastSyncMsg.value = ''
    try {
      const year = Number(auditYearRef.value) || new Date().getFullYear()
      const res: any = await api.get(adjPaths.list(projectId), {
        params: { year, page: 1, page_size: 200 },
        _silent: true,
      } as any)
      const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []
      if (!Array.isArray(items)) {
        lastSyncMsg.value = '未获取到调整分录'
        return 0
      }

      const imported: G13AdjustmentRow[] = []
      for (const entry of items) {
        const lines = entry.line_items || entry.lines || []
        if (!lines.some((li: any) => isG13RelatedAccount(li.standard_account_code || li.account_code))) {
          continue
        }
        const groupId = String(entry.entry_group_id || entry.id || '')
        // 仅当分录组含 6101 时拉入（避免把纯资产端调整整组灌入）
        const has6101 = lines.some((li: any) =>
          isG13AccountCode(String(li.standard_account_code || li.account_code || '')),
        )
        if (!has6101) continue

        for (const li of lines) {
          const accountCode = String(li.standard_account_code || li.account_code || '')
          if (!isG13RelatedAccount(accountCode)) continue
          imported.push(normalizeRow({
            description: entry.description || entry.adjustment_no || '调整分录模块同步',
            category: categoryFromModule(entry.adjustment_type || entry.type),
            reportItem: isG13AccountCode(accountCode) ? '公允价值变动收益' : '相关科目',
            accountName: li.account_name || accountCode,
            accountCode,
            debitAmount: li.debit_amount,
            creditAmount: li.credit_amount,
            indexRef: entry.adjustment_no || 'G13-3',
            remark: '来自调整分录模块',
            sourceGroupId: groupId,
          }))
        }
      }

      if (!imported.length) {
        lastSyncMsg.value = '调整分录模块中无含 6101 的相关分录'
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

  function pushToA13(rowIds?: string[]): void {
    const selected = rowIds?.length
      ? rows.value.filter((r) => rowIds.includes(r.rowId))
      : rows.value.filter((r) => r.category !== '报表调整' && (r.debitAmount || r.creditAmount))
    if (!selected.length) return
    try {
      eventBus.emit('a13:push-misstatement', {
        items: selected.map((row) => ({
          wpCode: G13_WP_CODE,
          entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
          description: row.description,
          reportItem: row.reportItem,
          accountName: row.accountName,
          debitAmount: row.debitAmount,
          creditAmount: row.creditAmount,
          indexRef: row.indexRef,
        })),
        wpCode: G13_WP_CODE,
        timestamp: Date.now(),
      })
      lastSyncMsg.value = `已推送 ${selected.length} 行至 A13`
    } catch { /* silent */ }
  }

  function onModuleUpdated(): void {
    if (options.projectId?.value && !options.isReadonly.value) {
      void syncFromAdjustmentModule()
    }
  }

  eventBus.on('adjustment:updated', onModuleUpdated)
  eventBus.on('adjustment:saved', onModuleUpdated)

  if (getCurrentInstance()) {
    onBeforeUnmount(() => {
      eventBus.off('adjustment:updated', onModuleUpdated)
      eventBus.off('adjustment:saved', onModuleUpdated)
    })
  }

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
    categoryOptions: G13_CATEGORY_OPTIONS,
    accountOptions: G13_ADJ_ACCOUNT_OPTIONS,
    belongOptions: G13_BELONG_WRITEBACK_OPTIONS,
    addRow,
    removeRow,
    updateCell,
    updateRow,
    syncToDetail,
    syncToAdjudicationOverlay,
    publishAdjustment,
    syncFromAdjustmentModule,
    pushToCentralModule,
    pushToA13,
    applyCutoffResults,
    tableRowClassName,
    persist,
    ITEM_ID_ROWS,
  }
}
