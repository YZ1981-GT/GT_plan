/**
 * useL2Adjustment — L2-3 调整分录核心逻辑 composable
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 3.4
 * Requirements: 5.3
 *
 * 职责：
 * - 管理 AJE/RJE 调整分录条目
 * - 借贷平衡校验：总借方 = 总贷方
 * - EventBus publish 'adjustment:created' 通知 L2-1 审定表
 * - 与 L2-1 审定表双向同步
 * - 分录类型切换（AJE / RJE）
 *
 * 科目：2231 应付利息（贷方/负债类）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { calcSubtotal } from './useL2FormulaEngine'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useL2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录条目 */
export interface AdjustmentEntry {
  /** 分录唯一ID */
  entryId: string
  /** 分录类型 */
  entryType: 'AJE' | 'RJE'
  /** 序号 */
  seqNo: number
  /** 科目编码 */
  accountCode: string
  /** 科目名称 */
  accountName: string
  /** 借方金额 */
  debitAmount: number
  /** 贷方金额 */
  creditAmount: number
  /** 摘要/说明 */
  description: string
  /** 创建时间 */
  createdAt: string
}

/** 借贷平衡结果 */
export interface BalanceCheckResult {
  /** 总借方 */
  totalDebit: number
  /** 总贷方 */
  totalCredit: number
  /** 差额（借-贷） */
  diff: number
  /** 是否平衡 */
  isBalanced: boolean
}

export interface UseL2AdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveField: (itemId: string, value: { conclusion?: string; remark?: string }) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ENTRIES = 'L2-L2-3-entries'

/** 平衡校验阈值（0.01元内视为平衡） */
const BALANCE_THRESHOLD = 0.01

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateEntryId(): string {
  return `entry-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function safeParseEntries(jsonStr: string | null | undefined): AdjustmentEntry[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeEntry) : []
  } catch {
    return []
  }
}

function normalizeEntry(raw: any): AdjustmentEntry {
  return {
    entryId: raw.entryId || generateEntryId(),
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    seqNo: parseNum(raw.seqNo),
    accountCode: raw.accountCode || '',
    accountName: raw.accountName || '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    description: raw.description || '',
    createdAt: raw.createdAt || new Date().toISOString(),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL2Adjustment(options: UseL2AdjustmentOptions) {
  const { allResponses, wpId, projectId, saveField, debouncedSave } = options

  // ─── Reactive entries ──────────────────────────────────────────────────

  const entries = ref<AdjustmentEntry[]>([])
  const activeEntryType = ref<'AJE' | 'RJE'>('AJE')

  // Load from allResponses
  watch(
    () => allResponses.value.get(ITEM_ID_ENTRIES)?.remark,
    (jsonStr) => {
      entries.value = safeParseEntries(jsonStr)
    },
    { immediate: true },
  )

  // ─── Persist ───────────────────────────────────────────────────────────

  function persistEntries(): void {
    debouncedSave(ITEM_ID_ENTRIES, { remark: JSON.stringify(entries.value) })
  }

  // ─── Filtered by type ──────────────────────────────────────────────────

  /** AJE分录列表 */
  const ajeEntries: ComputedRef<AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.entryType === 'AJE')
  })

  /** RJE分录列表 */
  const rjeEntries: ComputedRef<AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.entryType === 'RJE')
  })

  /** 当前类型的分录列表 */
  const currentEntries: ComputedRef<AdjustmentEntry[]> = computed(() => {
    return activeEntryType.value === 'AJE' ? ajeEntries.value : rjeEntries.value
  })

  // ─── Balance check ─────────────────────────────────────────────────────

  /** AJE 借贷平衡检查 */
  const ajeBalanceCheck: ComputedRef<BalanceCheckResult> = computed(() => {
    const totalDebit = calcSubtotal(ajeEntries.value.map(e => e.debitAmount))
    const totalCredit = calcSubtotal(ajeEntries.value.map(e => e.creditAmount))
    const diff = parseFloat((totalDebit - totalCredit).toFixed(2))
    return {
      totalDebit,
      totalCredit,
      diff,
      isBalanced: Math.abs(diff) <= BALANCE_THRESHOLD,
    }
  })

  /** RJE 借贷平衡检查 */
  const rjeBalanceCheck: ComputedRef<BalanceCheckResult> = computed(() => {
    const totalDebit = calcSubtotal(rjeEntries.value.map(e => e.debitAmount))
    const totalCredit = calcSubtotal(rjeEntries.value.map(e => e.creditAmount))
    const diff = parseFloat((totalDebit - totalCredit).toFixed(2))
    return {
      totalDebit,
      totalCredit,
      diff,
      isBalanced: Math.abs(diff) <= BALANCE_THRESHOLD,
    }
  })

  /** 当前类型的借贷平衡 */
  const currentBalanceCheck: ComputedRef<BalanceCheckResult> = computed(() => {
    return activeEntryType.value === 'AJE' ? ajeBalanceCheck.value : rjeBalanceCheck.value
  })

  // ─── L2-1 应付利息调整合计（供审定表消费） ─────────────────────────────

  /** AJE净调整额（贷方-借方，正=调增应付利息，负=调减） */
  const ajeNetAmount: ComputedRef<number> = computed(() => {
    const totalCredit = calcSubtotal(
      ajeEntries.value
        .filter(e => e.accountCode === '2231')
        .map(e => e.creditAmount),
    )
    const totalDebit = calcSubtotal(
      ajeEntries.value
        .filter(e => e.accountCode === '2231')
        .map(e => e.debitAmount),
    )
    return totalCredit - totalDebit
  })

  /** RJE净调整额 */
  const rjeNetAmount: ComputedRef<number> = computed(() => {
    const totalCredit = calcSubtotal(
      rjeEntries.value
        .filter(e => e.accountCode === '2231')
        .map(e => e.creditAmount),
    )
    const totalDebit = calcSubtotal(
      rjeEntries.value
        .filter(e => e.accountCode === '2231')
        .map(e => e.debitAmount),
    )
    return totalCredit - totalDebit
  })

  // ─── addEntry ──────────────────────────────────────────────────────────

  /**
   * 新增调整分录
   */
  function addEntry(entryType?: 'AJE' | 'RJE'): void {
    const type = entryType || activeEntryType.value
    const sameTypeEntries = entries.value.filter(e => e.entryType === type)
    const newEntry: AdjustmentEntry = {
      entryId: generateEntryId(),
      entryType: type,
      seqNo: sameTypeEntries.length + 1,
      accountCode: '',
      accountName: '',
      debitAmount: 0,
      creditAmount: 0,
      description: '',
      createdAt: new Date().toISOString(),
    }

    entries.value = [...entries.value, newEntry]
    persistEntries()

    // Publish EventBus event for L2-1 to pick up
    publishAdjustmentCreated(newEntry)
  }

  // ─── removeEntry ───────────────────────────────────────────────────────

  function removeEntry(entryId: string): void {
    entries.value = entries.value.filter(e => e.entryId !== entryId)
    // Resequence
    let ajeSeq = 1
    let rjeSeq = 1
    entries.value = entries.value.map(e => {
      if (e.entryType === 'AJE') {
        return { ...e, seqNo: ajeSeq++ }
      }
      return { ...e, seqNo: rjeSeq++ }
    })
    persistEntries()
  }

  // ─── updateEntry ───────────────────────────────────────────────────────

  function updateEntry(entryId: string, field: string, value: any): void {
    const idx = entries.value.findIndex(e => e.entryId === entryId)
    if (idx === -1) return

    const entry = { ...entries.value[idx] }

    if (field === 'debitAmount' || field === 'creditAmount') {
      ;(entry as any)[field] = parseNum(value)
    } else {
      ;(entry as any)[field] = value
    }

    const newEntries = [...entries.value]
    newEntries[idx] = entry
    entries.value = newEntries
    persistEntries()
  }

  // ─── publishAdjustmentCreated ──────────────────────────────────────────

  /**
   * 发布 adjustment:created EventBus 事件
   * L2-1 审定表监听此事件以累加 AJE/RJE
   */
  function publishAdjustmentCreated(_entry: AdjustmentEntry): void {
    // 使用 mitt eventBus 发布（payload 为 void 类型，符合 Events 定义）
    eventBus.emit('adjustment:created')
  }

  // ─── submitAdjustment（提交/同步） ─────────────────────────────────────

  /**
   * 提交调整分录（校验平衡性后保存并通知审定表）
   */
  async function submitAdjustment(): Promise<boolean> {
    const check = currentBalanceCheck.value
    if (!check.isBalanced) {
      ElMessage.warning(`借贷不平衡，差额${check.diff}元，请调整后再提交`)
      return false
    }

    // 持久化
    await saveField(ITEM_ID_ENTRIES, { remark: JSON.stringify(entries.value) })

    ElMessage.success('调整分录已保存')
    return true
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 数据
    entries,
    ajeEntries,
    rjeEntries,
    currentEntries,
    activeEntryType,
    // 平衡检查
    ajeBalanceCheck,
    rjeBalanceCheck,
    currentBalanceCheck,
    // 审定表联动
    ajeNetAmount,
    rjeNetAmount,
    // 操作
    addEntry,
    removeEntry,
    updateEntry,
    submitAdjustment,
    publishAdjustmentCreated,
  }
}

export default useL2Adjustment
