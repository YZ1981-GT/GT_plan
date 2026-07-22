/**

 * useG12Adjustment — G12-3 调整分录汇总（对齐 Excel 调整分录汇总 G12-3）

 */

import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'

import { ElMessage } from 'element-plus'

import { G12_ACCOUNT_CODE } from './g12Constants'

import {

  G12_ADJ_ACCOUNT_OPTIONS,

  G12_ADJ_CATEGORY_OPTIONS,

  categoryToEntryType,

  entryTypeToCategory,

  groupG12AdjustmentsByDesc,

  isG12AdjustmentBalanced,

  isG12RelatedAccount,

  summarizeG12Adjustment,

  type G12AdjCategory,

} from './g12AdjStorage'

import { useWorkpaperAuditYear } from './workpaperAuditYear'

import { parseNum } from './useG12FormulaEngine'

import type { ChecklistResponse } from './useF1FormData'

import { api } from '@/services/apiProxy'

import { adjustments as adjPaths } from '@/services/apiPaths/accounting'

import { eventBus } from '@/utils/eventBus'

import { g12AdjustmentNeedsSync } from './g12CoreWorkflowReadiness'



export interface G12AdjustmentRow {

  rowId: string

  seq: number

  adjustmentDesc: string

  category: G12AdjCategory

  fsItem: string

  accountCode: string

  accountName: string

  noteItem: string

  debitAmount: number

  creditAmount: number

  indexRef: string

  remark: string

  sourceGroupId?: string

}



const ITEM_ID = 'G12-aje-rows'

export const G12_AJE_ADJ_OVERLAY_ID = 'G12-aje-adj-overlay'



function genId() {

  return `g12a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`

}



function todayIso(): string {

  return new Date().toISOString().slice(0, 10)

}



export function createEmptyG12AdjustmentRow(): G12AdjustmentRow {

  return {

    rowId: genId(),

    seq: 0,

    adjustmentDesc: '',

    category: 'account',

    fsItem: '净敞口套期收益',

    accountCode: G12_ACCOUNT_CODE,

    accountName: '净敞口套期收益',

    noteItem: '净敞口套期收益',

    debitAmount: 0,

    creditAmount: 0,

    indexRef: '',

    remark: '',

  }

}



function isLegacyAdjRow(raw: Record<string, unknown>): boolean {

  return Boolean(raw.summary || raw.date || raw.preparedBy) && !raw.adjustmentDesc

}



function norm(raw: any, idx: number): G12AdjustmentRow {

  if (isLegacyAdjRow(raw)) {

    const entryType = raw.entryType === 'RJE' ? 'RJE' : 'AJE'

    const code = String(raw.accountCode || G12_ACCOUNT_CODE).trim() || G12_ACCOUNT_CODE

    const known = G12_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)

    return {

      rowId: raw.rowId || genId(),

      seq: raw.seq ?? idx + 1,

      adjustmentDesc: raw.summary || raw.description || '',

      category: entryTypeToCategory(entryType),

      fsItem: '净敞口套期收益',

      accountCode: code,

      accountName: (raw.accountName ?? known?.name ?? '').trim() || known?.name || '净敞口套期收益',

      noteItem: '净敞口套期收益',

      debitAmount: parseNum(raw.debitAmount),

      creditAmount: parseNum(raw.creditAmount),

      indexRef: raw.indexRef ?? '',

      remark: raw.remark ?? '',

      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,

    }

  }



  const code = String(raw.accountCode || G12_ACCOUNT_CODE).trim() || G12_ACCOUNT_CODE

  const known = G12_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)

  const category = (['account', 'report', 'other'].includes(raw.category)

    ? raw.category

    : entryTypeToCategory(raw.entryType)) as G12AdjCategory



  return {

    rowId: raw.rowId || genId(),

    seq: raw.seq ?? idx + 1,

    adjustmentDesc: raw.adjustmentDesc ?? raw.summary ?? '',

    category,

    fsItem: raw.fsItem ?? '净敞口套期收益',

    accountCode: code,

    accountName: (raw.accountName ?? known?.name ?? '').trim() || known?.name || '净敞口套期收益',

    noteItem: raw.noteItem ?? '净敞口套期收益',

    debitAmount: parseNum(raw.debitAmount),

    creditAmount: parseNum(raw.creditAmount),

    indexRef: raw.indexRef ?? '',

    remark: raw.remark ?? '',

    sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,

  }

}



function resequence(rows: G12AdjustmentRow[]): G12AdjustmentRow[] {

  return rows.map((r, i) => ({ ...r, seq: i + 1 }))

}



function entryTypeFromModule(t: string | undefined): 'AJE' | 'RJE' {

  const text = String(t || '').toLowerCase()

  if (text.includes('rje') || text.includes('报表') || text.includes('重分类')) return 'RJE'

  return 'AJE'

}



export function useG12Adjustment(opts: {

  allResponses: Ref<Map<string, ChecklistResponse>>

  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void

  isReadonly: Ref<boolean> | ComputedRef<boolean>

  projectId?: Ref<string> | ComputedRef<string>

  applyAdjustmentOverlay?: (overlay: Record<string, number>) => void

}) {

  const rows = ref<G12AdjustmentRow[]>([])

  const syncing = ref(false)

  const lastSyncMsg = ref('')

  const auditYearRef = useWorkpaperAuditYear()



  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => {

    try {

      rows.value = j ? JSON.parse(j).map(norm) : []

    } catch {

      rows.value = []

    }

  }, { immediate: true })



  function persist(list = rows.value) {

    opts.debouncedSave(ITEM_ID, { remark: JSON.stringify(list) })

    rows.value = list

  }



  const summary = computed(() => summarizeG12Adjustment(rows.value))

  const groups = computed(() => groupG12AdjustmentsByDesc(rows.value))

  const debitTotal = computed(() => summary.value.totalDebits)

  const creditTotal = computed(() => summary.value.totalCredits)

  const balanceDiff = computed(() => summary.value.balanceDiff)

  const isBalanced = computed(() => isG12AdjustmentBalanced(rows.value))

  const writebackPreview = computed(() => ({

    net6103: summary.value.net6103,

    aje: summary.value.ajeNet6103,

    rje: summary.value.rjeNet6103,

  }))

  const needsSyncToAdjudication = computed(() =>
    g12AdjustmentNeedsSync(opts.allResponses.value),
  )

  const isSyncedToAdjudication = computed(() =>
    !needsSyncToAdjudication.value && (rows.value.length === 0 || isBalanced.value),
  )



  function addRow(desc = '') {

    if (opts.isReadonly.value) return

    persist(resequence([

      ...rows.value,

      { ...createEmptyG12AdjustmentRow(), adjustmentDesc: desc, seq: rows.value.length + 1 },

    ]))

  }



  function addRowToGroup(adjustmentDesc: string) {

    if (opts.isReadonly.value) return

    persist(resequence([

      ...rows.value,

      {

        ...createEmptyG12AdjustmentRow(),

        adjustmentDesc: adjustmentDesc.trim() || '（未命名调整事项）',

        seq: rows.value.length + 1,

      },

    ]))

  }



  function addBalancedPair(net6103Delta: number, desc: string, indexRef = 'G12-2') {

    if (opts.isReadonly.value || Math.abs(net6103Delta) < 0.01) return

    const abs = Math.abs(net6103Delta)

    const isDebit6103 = net6103Delta > 0

    persist(resequence([

      ...rows.value,

      {

        ...createEmptyG12AdjustmentRow(),

        adjustmentDesc: desc,

        category: 'account',

        debitAmount: isDebit6103 ? abs : 0,

        creditAmount: isDebit6103 ? 0 : abs,

        indexRef,

        remark: '自 G12-2 明细差异推送',

      },

      {

        ...createEmptyG12AdjustmentRow(),

        adjustmentDesc: desc,

        category: 'account',

        accountCode: '4104',

        accountName: '利润分配—未分配利润',

        fsItem: '未分配利润',

        noteItem: '',

        debitAmount: isDebit6103 ? 0 : abs,

        creditAmount: isDebit6103 ? abs : 0,

        indexRef,

        remark: '自 G12-2 明细差异推送（对方科目）',

      },

    ]))

    ElMessage.success('已生成成对调整分录，请核对对方科目')

  }



  function removeRow(id: string) {

    if (opts.isReadonly.value) return

    persist(resequence(rows.value.filter((r) => r.rowId !== id)))

  }



  function updateCell(id: string, field: keyof G12AdjustmentRow, value: unknown) {

    if (opts.isReadonly.value) return

    const idx = rows.value.findIndex((r) => r.rowId === id)

    if (idx === -1) return

    const row = { ...rows.value[idx] }

    if (field === 'debitAmount' || field === 'creditAmount') row[field] = parseNum(value)

    else if (field === 'category') row.category = (value as G12AdjCategory) || 'account'

    else if (field === 'accountCode') {

      row.accountCode = String(value ?? G12_ACCOUNT_CODE)

      const known = G12_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === row.accountCode)

      if (known) row.accountName = known.name

    } else (row as any)[field] = value

    persist(resequence([...rows.value.slice(0, idx), row, ...rows.value.slice(idx + 1)]))

  }



  function syncToAdjudication(): void {

    if (opts.isReadonly.value || !isBalanced.value) return

    const overlay: Record<string, number> = { net_hedge: summary.value.net6103 }

    opts.debouncedSave(G12_AJE_ADJ_OVERLAY_ID, { remark: JSON.stringify(overlay) })

    opts.applyAdjustmentOverlay?.(overlay)

    window.dispatchEvent(new CustomEvent('g12:adjustment-synced', {

      detail: { netAdjustment: summary.value.net6103, overlay },

    }))

    ElMessage.success(`已同步至 G12-1（6103 净额 ${summary.value.net6103.toFixed(2)}）`)

  }



  async function pushToAdjustmentModule(): Promise<number> {

    const projectId = opts.projectId?.value

    if (!projectId || opts.isReadonly.value || !isBalanced.value) return 0

    const year = auditYearRef.value

    if (year == null) return 0



    const pending = rows.value.filter(

      (r) => !r.sourceGroupId && (Math.abs(r.debitAmount) > 0.005 || Math.abs(r.creditAmount) > 0.005),

    )

    if (!pending.length) return 0



    const groupMap = new Map<string, G12AdjustmentRow[]>()

    for (const row of pending) {

      const key = `${categoryToEntryType(row.category)}||${row.adjustmentDesc || row.rowId}`

      groupMap.set(key, [...(groupMap.get(key) || []), row])

    }



    let pushed = 0

    let list = [...rows.value]

    for (const lines of groupMap.values()) {

      const debit = lines.reduce((s, r) => s + r.debitAmount, 0)

      const credit = lines.reduce((s, r) => s + r.creditAmount, 0)

      if (Math.abs(debit - credit) >= 0.01) continue

      try {

        const res: any = await api.post(adjPaths.create(projectId), {

          adjustment_type: categoryToEntryType(lines[0].category) === 'RJE' ? 'rje' : 'aje',

          year,

          company_code: 'default',

          description: `[G12] ${lines[0].adjustmentDesc || '净敞口套期收益调整'}`,

          line_items: lines.map((r) => ({

            standard_account_code: r.accountCode || G12_ACCOUNT_CODE,

            account_name: r.accountName || undefined,

            debit_amount: r.debitAmount,

            credit_amount: r.creditAmount,

          })),

        }, { _silent: true } as any)

        const groupId = res?.entry_group_id ?? res?.data?.entry_group_id ?? res?.id

        if (!groupId) continue

        const id = String(groupId)

        list = list.map((r) => (lines.some((l) => l.rowId === r.rowId) ? { ...r, sourceGroupId: id } : r))

        pushed += 1

      } catch {

        lastSyncMsg.value = '底稿已保存，但部分分录未能同步至集中模块'

      }

    }

    if (pushed > 0) {

      persist(list)

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

      const year = auditYearRef.value ?? new Date().getFullYear()

      const res: any = await api.get(adjPaths.list(projectId), {

        params: { year, page: 1, page_size: 200 },

        _silent: true,

      } as any)

      const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []

      if (!Array.isArray(items)) {

        lastSyncMsg.value = '未获取到调整分录'

        return 0

      }



      const imported: G12AdjustmentRow[] = []

      for (const item of items) {

        const lines = item.line_items || item.lines || []

        if (!lines.some((li: any) => isG12RelatedAccount(li.standard_account_code || li.account_code))) continue

        const groupId = String(item.entry_group_id || item.id || '')

        const desc = String(item.description || item.adjustment_no || '调整分录模块同步').replace(/^\[G12\]\s*/, '')

        for (const li of lines) {

          const accountCode = String(li.standard_account_code || li.account_code || '')

          imported.push(norm({

            rowId: `${groupId}-${imported.length}`,

            adjustmentDesc: desc,

            category: entryTypeToCategory(entryTypeFromModule(item.adjustment_type || item.type)),

            fsItem: '净敞口套期收益',

            accountCode,

            accountName: li.account_name || accountCode,

            noteItem: '净敞口套期收益',

            debitAmount: li.debit_amount,

            creditAmount: li.credit_amount,

            indexRef: '调整模块',

            remark: '来自调整分录模块',

            sourceGroupId: groupId,

          }, imported.length))

        }

      }

      const manual = rows.value.filter((r) => !r.sourceGroupId)

      persist([...manual, ...imported].map((r, i) => ({ ...r, seq: i + 1 })))

      lastSyncMsg.value = imported.length

        ? `已同步 ${imported.length} 行`

        : '集中模块中无 6103/6101/4002 等相关分录'

      return imported.length

    } catch {

      lastSyncMsg.value = '同步失败，请稍后重试'

      return 0

    } finally {

      syncing.value = false

    }

  }



  async function confirmAndPush(): Promise<{ ok: boolean; pushed: number }> {

    if (!isBalanced.value) return { ok: false, pushed: 0 }

    persist(rows.value)

    const pushed = await pushToAdjustmentModule()

    return { ok: true, pushed }

  }



  function onModuleUpdated() {

    if (!opts.isReadonly.value && opts.projectId?.value) void syncFromAdjustmentModule()

  }



  onMounted(() => {

    eventBus.on('adjustment:updated', onModuleUpdated)

  })

  onBeforeUnmount(() => {

    eventBus.off('adjustment:updated', onModuleUpdated)

  })



  return {

    rows,

    groups,

    summary,

    debitTotal,

    creditTotal,

    balanceDiff,

    isBalanced,

    writebackPreview,

    needsSyncToAdjudication,

    isSyncedToAdjudication,

    syncing,

    lastSyncMsg,

    addRow,

    addRowToGroup,

    addBalancedPair,

    removeRow,

    updateCell,

    syncToAdjudication,

    pushToAdjustmentModule,

    syncFromAdjustmentModule,

    confirmAndPush,

    persist,

    ITEM_ID,

    G12_ADJ_CATEGORY_OPTIONS,

    G12_ADJ_ACCOUNT_OPTIONS,

    categoryToEntryType,

  }

}


