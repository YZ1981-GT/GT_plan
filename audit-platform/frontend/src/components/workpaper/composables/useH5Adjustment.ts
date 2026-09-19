/**
 * useH5Adjustment — H5-3 调整分录 composable
 *
 * 借贷平衡校验, EventBus publish
 * 10列调整分录管理
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 3.4-3.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'
import { calcSubtotal } from './useH5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjustmentEntry {
  rowId: string
  entryNo: string             // 分录编号
  type: 'AJE' | 'RJE'        // 调整类型
  accountCode: string         // 科目代码
  accountName: string         // 科目名称
  description: string         // 摘要
  debitAmount: number         // 借方金额
  creditAmount: number        // 贷方金额
  preparedBy: string          // 编制人
  remark: string              // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H5-3'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5Adjustment(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const { allResponses, onSave } = opts

  const entries = ref<AdjustmentEntry[]>([])
  const auditNote = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _load(): void {
    const item = allResponses.value.get(`${ITEM_PREFIX}-entries`)
    const raw = item?.remark
    if (!raw) { entries.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      entries.value = Array.isArray(parsed) ? parsed.map(_normalize) : []
    } catch { entries.value = [] }
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalize(raw: any): AdjustmentEntry {
    return {
      rowId: raw.rowId ?? `adj-${Math.random().toString(36).slice(2, 10)}`,
      entryNo: raw.entryNo ?? '',
      type: raw.type === 'RJE' ? 'RJE' : 'AJE',
      accountCode: raw.accountCode ?? '',
      accountName: raw.accountName ?? '',
      description: raw.description ?? '',
      debitAmount: Number(raw.debitAmount) || 0,
      creditAmount: Number(raw.creditAmount) || 0,
      preparedBy: raw.preparedBy ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const totalDebit = computed(() => calcSubtotal(entries.value.map((e) => e.debitAmount)))
  const totalCredit = computed(() => calcSubtotal(entries.value.map((e) => e.creditAmount)))
  const isBalanced = computed(() => Math.abs(totalDebit.value - totalCredit.value) < 0.01)
  const balanceDiff = computed(() => totalDebit.value - totalCredit.value)

  const ajeEntries = computed(() => entries.value.filter((e) => e.type === 'AJE'))
  const rjeEntries = computed(() => entries.value.filter((e) => e.type === 'RJE'))

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addEntry(type: 'AJE' | 'RJE' = 'AJE'): void {
    const entry: AdjustmentEntry = {
      rowId: `adj-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      entryNo: '', type,
      accountCode: '', accountName: '', description: '',
      debitAmount: 0, creditAmount: 0,
      preparedBy: '', remark: '',
    }
    entries.value.push(entry)
    _persist()
  }

  function removeEntry(rowId: string): void {
    const idx = entries.value.findIndex((e) => e.rowId === rowId)
    if (idx >= 0) { entries.value.splice(idx, 1); _persist() }
  }

  function updateEntry(rowId: string, field: keyof AdjustmentEntry, value: any): void {
    const entry = entries.value.find((e) => e.rowId === rowId)
    if (!entry) return
    ;(entry as any)[field] = value
    _persist()
  }

  /** 发布调整分录到A13错报汇总 */
  function publishAdjustment(): void {
    if (!isBalanced.value) return
    opts.onPublishEvent?.('adjustment:created', {
      wpCode: 'H5',
      entries: entries.value,
      totalDebit: totalDebit.value,
      totalCredit: totalCredit.value,
    })
  }

  function _persist(): void { onSave?.(`${ITEM_PREFIX}-entries`, entries.value) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX}-audit-note`, note) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    entries, auditNote,
    totalDebit, totalCredit, isBalanced, balanceDiff,
    ajeEntries, rjeEntries,
    addEntry, removeEntry, updateEntry, publishAdjustment, saveNote,
  }
}
