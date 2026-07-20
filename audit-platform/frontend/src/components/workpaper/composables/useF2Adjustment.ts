/**
 * useF2Adjustment — F2-14 调整分录（10列）
 * Spec: .kiro/specs/f2-inventory-main/ Task 8.1
 * 比照 useD4Adjustment / useG3Adjustment（集中表推送）
 */
import { ref, computed, watch, onBeforeUnmount, getCurrentInstance, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from './useF2InvMaiFormulaEngine'
import type { ChecklistResponse } from './useF2FormData'
import { F2_INVENTORY_ACCOUNTS } from './f2AccountModel'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'

export { F2_INVENTORY_ACCOUNTS } from './f2AccountModel'

export interface F2AdjustmentRow {
  rowId: string
  seq: number
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  entryType: 'AJE' | 'RJE'
  indexRef: string
  remark: string
  noteItem: string
  /** 已推送到集中 adjustments 表的分组 ID */
  sourceGroupId?: string
}

const STORAGE_KEY = 'F2-14-rows'

function generateRowId(): string {
  return `f2a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyRow(seq: number): F2AdjustmentRow {
  return {
    rowId: generateRowId(),
    seq,
    summary: '',
    accountCode: '1401',
    accountName: '原材料',
    debitAmount: 0,
    creditAmount: 0,
    entryType: 'AJE',
    indexRef: '',
    remark: '',
    noteItem: '',
  }
}

function safeParseRows(jsonStr: string | null | undefined): F2AdjustmentRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyRow(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      summary: raw.summary || raw.description || '',
      accountCode: raw.accountCode || '1401',
      accountName: raw.accountName || '原材料',
      debitAmount: parseNum(raw.debitAmount),
      creditAmount: parseNum(raw.creditAmount),
      entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
      indexRef: raw.indexRef || '',
      remark: raw.remark || '',
      noteItem: raw.noteItem || '',
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }))
  } catch {
    return []
  }
}

export function useF2Adjustment(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  projectId?: Ref<string>
  auditYear?: Ref<number | undefined>
  /** 直接 HTTP 保存（可选）；缺省仍走 f2:save-items */
  saveItems?: (items: ChecklistResponse[]) => Promise<void>
}) {
  const { allResponses, isReadonly, projectId, auditYear, saveItems } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const pushing = ref(false)

  const storedData = ref<F2AdjustmentRow[]>([])

  function loadRows(): void {
    storedData.value = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [emptyRow(1)]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, () => {
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  const rows: ComputedRef<F2AdjustmentRow[]> = computed(() => storedData.value)

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() =>
    isDebitCreditBalanced(
      rows.value.map((r) => r.debitAmount),
      rows.value.map((r) => r.creditAmount),
    ),
  )

  function publishAdjustments(): void {
    for (const row of rows.value) {
      if (row.debitAmount === 0 && row.creditAmount === 0) continue
      try {
        eventBus.emit('adjustment:created', {
          wpCode: 'F2',
          entryType: row.entryType,
          amount: Math.max(row.debitAmount, row.creditAmount),
          accountCode: row.accountCode,
          accountName: row.accountName,
          description: row.summary,
        })
      } catch { /* silent */ }
    }
  }

  /**
   * 确认同步：EventBus → F2-1 + 平衡的未推送组分推集中 adjustments（对齐 G3 publishAdjustment）。
   * 工具栏「同步至审定表」应调用本方法；单元格编辑仍只走 persistRows→publishAdjustments（不打 API）。
   */
  async function confirmAndSync(): Promise<number> {
    publishAdjustments()
    return pushConfirmedToCentralModule({ quiet: true })
  }

  function persistRows(): void {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(storedData.value),
    })
    debounceSave()
    publishAdjustments()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; void flushSave() }, 2000)
  }

  async function flushSave(): Promise<void> {
    const item = allResponses.value.get(STORAGE_KEY)
    if (!item) return
    if (saveItems) {
      try {
        await saveItems([item])
      } catch { /* parent/HTTP 失败时仍尝试 window 兜底 */ }
    }
    window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  /**
   * 将平衡的 AJE/RJE 组推送到集中 adjustments 表（对齐 useG3Adjustment）。
   * 已带 sourceGroupId 的行跳过；不平衡组跳过。
   * @param opts.quiet 自动同步路径：缺项目/不平衡/无待推送时不弹 toast
   */
  async function pushConfirmedToCentralModule(opts?: { quiet?: boolean }): Promise<number> {
    const quiet = !!opts?.quiet
    if (readonly.value) return 0
    const pid = projectId?.value
    const year = Number(auditYear?.value)
    if (!pid || !Number.isFinite(year) || year < 1900) {
      if (!quiet) ElMessage.warning('缺少项目或审计年度，无法推送集中调整表')
      return 0
    }
    if (!isBalanced.value) {
      if (!quiet) ElMessage.warning('调整分录借贷不平衡，请先平衡后再推送')
      return 0
    }

    const pending = storedData.value.filter(
      (r) => !r.sourceGroupId && (r.debitAmount !== 0 || r.creditAmount !== 0),
    )
    if (!pending.length) {
      if (!quiet) ElMessage.info('没有待推送的调整分录')
      return 0
    }

    const groups = new Map<string, F2AdjustmentRow[]>()
    for (const row of pending) {
      const key = `${row.entryType}||${row.summary || row.rowId}`
      const arr = groups.get(key) ?? []
      arr.push(row)
      groups.set(key, arr)
    }

    pushing.value = true
    let pushed = 0
    try {
      for (const [, lines] of groups) {
        const debitSum = lines.reduce((s, r) => s + r.debitAmount, 0)
        const creditSum = lines.reduce((s, r) => s + r.creditAmount, 0)
        if (Math.abs(debitSum - creditSum) > 0.01) continue
        const adjustment_type = lines[0].entryType === 'RJE' ? 'rje' : 'aje'
        try {
          const res: any = await api.post(adjPaths.create(pid), {
            adjustment_type,
            year,
            company_code: 'default',
            description: `[F2] ${lines[0].summary || '存货调整'}`,
            line_items: lines.map((r) => ({
              standard_account_code: r.accountCode,
              account_name: r.accountName || undefined,
              debit_amount: r.debitAmount,
              credit_amount: r.creditAmount,
            })),
          }, { _silent: true } as any)
          const groupId = res?.entry_group_id ?? res?.data?.entry_group_id ?? res?.id
          if (groupId) {
            const id = String(groupId)
            storedData.value = storedData.value.map((r) =>
              lines.some((l) => l.rowId === r.rowId) ? { ...r, sourceGroupId: id } : r,
            )
            pushed++
          }
        } catch { /* 单组失败不阻断 */ }
      }
      if (pushed > 0) {
        // 只落库 + EventBus，勿再调 publishAdjustments（避免递归）
        allResponses.value.set(STORAGE_KEY, {
          item_id: STORAGE_KEY,
          conclusion: null,
          remark: JSON.stringify(storedData.value),
        })
        debounceSave()
        eventBus.emit('adjustment:updated')
        ElMessage.success(`已推送 ${pushed} 组调整至集中台账`)
      } else if (!quiet) {
        ElMessage.warning('未推送成功（请检查借贷是否成组平衡）')
      }
    } finally {
      pushing.value = false
    }
    return pushed
  }

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(emptyRow(storedData.value.length + 1))
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || storedData.value.length <= 1) return
    const idx = storedData.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    storedData.value.splice(idx, 1)
    storedData.value.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = storedData.value.find((r) => r.rowId === rowId)
    if (!row) return

    if (field === 'accountCode') {
      row.accountCode = String(value ?? '')
      const acc = F2_INVENTORY_ACCOUNTS.find((a) => a.code === row.accountCode)
      if (acc) row.accountName = acc.name
    } else if (field === 'accountName') {
      row.accountName = String(value ?? '')
      const acc = F2_INVENTORY_ACCOUNTS.find((a) => a.name === row.accountName)
      if (acc) row.accountCode = acc.code
    } else if (field === 'debitAmount' || field === 'creditAmount') {
      ;(row as any)[field] = parseNum(value)
    } else if (field === 'entryType') {
      row.entryType = value === 'RJE' ? 'RJE' : 'AJE'
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    persistRows()
  }

  if (getCurrentInstance()) {
    onBeforeUnmount(() => {
      if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; void flushSave() }
    })
  }

  return {
    rows,
    debitTotal,
    creditTotal,
    balanceDiff,
    isBalanced,
    accountOptions: F2_INVENTORY_ACCOUNTS,
    addRow,
    removeRow,
    updateCell,
    publishAdjustments,
    confirmAndSync,
    pushConfirmedToCentralModule,
    pushing,
    flushSave,
  }
}

export default useF2Adjustment
