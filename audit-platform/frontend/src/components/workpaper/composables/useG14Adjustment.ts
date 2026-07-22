/**
 * useG14Adjustment — G14-3 调整分录汇总
 *
 * 编制逻辑（对齐 Excel「信用减值损失调整分录汇总表 G14-3」）：
 * 1. 列：调整事项说明 / 类别(账项调整·报表调整·其他) / 报表项目 / 科目 / 附注项目 / 借贷 / 索引 / 备注
 * 2. 「账项调整」影响审定数；「报表调整」仅影响列报，不回写 G14-2
 * 3. 仅汇总 6702 借−贷净额，按「回写行」分项写入 G14-2 明细表
 * 4. 兼容旧字段 entryType/summary/重分类调整（导入与历史数据）
 * 5. 与中央调整分录模块双向同步；可推送 A13 错报汇总
 */
import { ref, computed, watch, onBeforeUnmount, getCurrentInstance, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from './useG14FormulaEngine'
import { mapCutoffToG14Adjustment, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import type { ChecklistResponse } from './useF1FormData'
import { G14_ACCOUNT_CODE } from './g14Constants'
import {
  G14_ADJ_ACCOUNT_OPTIONS,
  G14_CATEGORY_OPTIONS,
  G14_WRITEBACK_OPTIONS,
  aggregateG14AdjustmentByRow,
  calcG14AdjustmentNet,
  categoryFromLegacy,
  categoryFromModule,
  inferG14AdjudicationRowKey,
  isG14AccountCode,
  isG14RelatedAccount,
  summarizeG14Adjustment,
  type G14AdjustmentWritebackMap,
} from './g14AdjStorage'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'
import { useWorkpaperAuditYear } from './workpaperAuditYear'

export interface G14AdjustmentRow {
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
  /** 回写目标：G14-2 明细 rowKey */
  adjudicationRowKey: string
  /** 兼容旧存档 / 截止回填 */
  entryType: 'AJE' | 'RJE'
  date: string
  preparedBy: string
  /** 中央调整分录模块 entry_group_id（有值表示来自模块或已推送） */
  sourceGroupId?: string
  /** @deprecated 旧摘要字段，读档时并入 description */
  summary?: string
}

const ITEM_ID_ROWS = 'G14-aje-rows'
const BALANCE_TOLERANCE = 0.01
const G14_WP_CODE = 'G14'

export { G14_CATEGORY_OPTIONS, G14_ADJ_ACCOUNT_OPTIONS, G14_WRITEBACK_OPTIONS }

function generateRowId(): string {
  return `g14a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export function createEmptyG14AdjustmentRow(): G14AdjustmentRow {
  return {
    rowId: generateRowId(),
    description: '',
    category: '账项调整',
    reportItem: '信用减值损失',
    accountName: '信用减值损失',
    accountCode: G14_ACCOUNT_CODE,
    noteItem: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: 'G14-3',
    remark: '',
    adjudicationRowKey: 'other',
    entryType: 'AJE',
    date: todayIso(),
    preparedBy: '',
  }
}

function normalizeRow(raw: any): G14AdjustmentRow {
  const category = categoryFromLegacy(raw)
  const entryType: 'AJE' | 'RJE' = category === '报表调整' ? 'RJE' : 'AJE'
  const code = String(raw.accountCode ?? G14_ACCOUNT_CODE).trim() || G14_ACCOUNT_CODE
  const known = G14_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)
  const description = String(raw.description || raw.summary || '').trim()
  const adjudicationRowKey = inferG14AdjudicationRowKey({
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
    reportItem: raw.reportItem || (isG14AccountCode(code) ? '信用减值损失' : '相关科目'),
    accountName: (raw.accountName ?? known?.name ?? '').trim() || known?.name || '信用减值损失',
    accountCode: code,
    noteItem: raw.noteItem || '',
    debitAmount: parseNum(raw.debitAmount ?? raw.debit),
    creditAmount: parseNum(raw.creditAmount ?? raw.credit),
    indexRef: raw.indexRef || raw.index || 'G14-3',
    remark: raw.remark || '',
    adjudicationRowKey,
    entryType,
    date: raw.date || '',
    preparedBy: raw.preparedBy || '',
    sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
  }
}

function parseRows(json: string | null | undefined): G14AdjustmentRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

export interface UseG14AdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
  auditYear?: Ref<number | string | null | undefined> | ComputedRef<number | string | null | undefined>
  /** 按明细行分项回写 G14-2 调整数 */
  applyAdjustmentToDetail?: (byRow: G14AdjustmentWritebackMap) => void
}

export function useG14Adjustment(options: UseG14AdjustmentOptions) {
  const rows = ref<G14AdjustmentRow[]>([])
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
  const adjustmentNet = computed(() => calcG14AdjustmentNet(rows.value))
  const writebackPreview = computed(() => aggregateG14AdjustmentByRow(rows.value))
  const summary = computed(() => summarizeG14Adjustment(rows.value))

  function addRow(): void {
    if (options.isReadonly.value) return
    rows.value = [...rows.value, createEmptyG14AdjustmentRow()]
    persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateRow(rowId: string, patch: Partial<G14AdjustmentRow>): void {
    if (options.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r, ...patch }
      if (patch.category != null) {
        next.entryType = patch.category === '报表调整' ? 'RJE' : 'AJE'
      }
      if (patch.accountCode != null) {
        const known = G14_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === patch.accountCode)
        if (known && (patch.accountName == null || patch.accountName === r.accountName)) {
          next.accountName = known.name
        }
      }
      if (patch.adjudicationRowKey != null) {
        next.adjudicationRowKey = patch.adjudicationRowKey
      } else if (
        patch.description != null
        || patch.noteItem != null
        || patch.remark != null
      ) {
        if (!next.adjudicationRowKey || next.adjudicationRowKey === 'other') {
          next.adjudicationRowKey = inferG14AdjudicationRowKey({ ...next, adjudicationRowKey: '' })
        }
      }
      return next
    })
    persist()
  }

  function updateCell(rowId: string, field: keyof G14AdjustmentRow, value: unknown): void {
    if (field === 'debitAmount' || field === 'creditAmount') {
      updateRow(rowId, { [field]: parseNum(value) } as Partial<G14AdjustmentRow>)
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
    updateRow(rowId, { [field]: value } as Partial<G14AdjustmentRow>)
  }

  /** 将 6702 账项净额按明细行写入 G14-2 */
  function syncToDetail(): G14AdjustmentWritebackMap {
    const byRow = aggregateG14AdjustmentByRow(rows.value)
    options.applyAdjustmentToDetail?.(byRow)
    window.dispatchEvent(new CustomEvent('g14:adjustment-synced', {
      detail: { byRow, netAdjustment: calcG14AdjustmentNet(rows.value) },
    }))
    return byRow
  }

  function applyCutoffResults(samples: ExtractedVoucher[], fillMode: FillMode): void {
    if (options.isReadonly.value || !samples.length) return
    const mapped = samples.map(mapCutoffToG14Adjustment)
    rows.value = mergeByFillMode(
      rows.value,
      mapped,
      fillMode,
      (r) => `${r.date}|${r.description}|${r.debitAmount}|${r.creditAmount}`,
    )
    persist()
  }

  function tableRowClassName({ row }: { row: G14AdjustmentRow }): string {
    if (row.category === '报表调整' || row.entryType === 'RJE') return 'rje-row'
    if (isG14AccountCode(row.accountCode)) return 'g14-acct-row'
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

    const groups = new Map<string, G14AdjustmentRow[]>()
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
          description: `[G14] ${lines[0].description || '信用减值损失调整'}`,
          line_items: lines.map((r) => ({
            standard_account_code: r.accountCode || G14_ACCOUNT_CODE,
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
          wpCode: G14_WP_CODE,
          entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
          amount: Math.max(row.debitAmount, row.creditAmount),
          accountCode: row.accountCode || G14_ACCOUNT_CODE,
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

      const imported: G14AdjustmentRow[] = []
      for (const entry of items) {
        const lines = entry.line_items || entry.lines || []
        if (!lines.some((li: any) => isG14RelatedAccount(li.standard_account_code || li.account_code))) {
          continue
        }
        const groupId = String(entry.entry_group_id || entry.id || '')
        // 仅当分录组含 6702 时拉入（避免把纯资产端减值准备调整整组灌入）
        const has6702 = lines.some((li: any) =>
          isG14AccountCode(String(li.standard_account_code || li.account_code || '')),
        )
        if (!has6702) continue

        for (const li of lines) {
          const accountCode = String(li.standard_account_code || li.account_code || '')
          if (!isG14RelatedAccount(accountCode)) continue
          imported.push(normalizeRow({
            description: entry.description || entry.adjustment_no || '调整分录模块同步',
            category: categoryFromModule(entry.adjustment_type || entry.type),
            reportItem: isG14AccountCode(accountCode) ? '信用减值损失' : '相关科目',
            accountName: li.account_name || accountCode,
            accountCode,
            debitAmount: li.debit_amount,
            creditAmount: li.credit_amount,
            indexRef: entry.adjustment_no || 'G14-3',
            remark: '来自调整分录模块',
            sourceGroupId: groupId,
          }))
        }
      }

      if (!imported.length) {
        lastSyncMsg.value = '调整分录模块中无含 6702 的相关分录'
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
          wpCode: G14_WP_CODE,
          entryType: row.category === '报表调整' ? 'RJE' : 'AJE',
          description: row.description,
          reportItem: row.reportItem,
          accountName: row.accountName,
          debitAmount: row.debitAmount,
          creditAmount: row.creditAmount,
          indexRef: row.indexRef,
        })),
        wpCode: G14_WP_CODE,
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
    categoryOptions: G14_CATEGORY_OPTIONS,
    accountOptions: G14_ADJ_ACCOUNT_OPTIONS,
    writebackOptions: G14_WRITEBACK_OPTIONS,
    addRow,
    removeRow,
    updateCell,
    updateRow,
    syncToDetail,
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
