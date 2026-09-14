/**
 * useL1Adjustment — L1-3 调整分录 composable
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 3.4
 * Requirements: 8.1
 *
 * 职责：
 * - AJE/RJE 行管理
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步 L1-1 审定表
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from '@/composables/useL1FormulaEngine'
import type { useL1FormData } from '@/composables/useL1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type AdjustmentType = 'AJE' | 'RJE'

/** 调整分录行 */
export interface AdjustmentEntry {
  /** 序号 */
  index: number
  /** AJE or RJE */
  type: AdjustmentType
  /** 摘要 */
  description: string
  /** 科目编码 */
  accountCode: string
  /** 科目名称 */
  accountName: string
  /** 借方金额 */
  debitAmount: number
  /** 贷方金额 */
  creditAmount: number
}

/** 借贷平衡状态 */
export interface BalanceStatus {
  /** 借方合计 */
  totalDebit: number
  /** 贷方合计 */
  totalCredit: number
  /** 差额 */
  diff: number
  /** 是否平衡（差额绝对值≤0.01） */
  isBalanced: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 平衡阈值 */
const BALANCE_THRESHOLD = 0.01

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L1-3 调整分录业务逻辑
 *
 * @param formData 由调用方传入的 useL1FormData 实例
 */
export function useL1Adjustment(formData: ReturnType<typeof useL1FormData>) {
  const { debounceSave, saveImmediate } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<AdjustmentEntry[]>([])
  const activeType = ref<AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型（AJE/RJE）的分录 */
  const filteredEntries: ComputedRef<AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /** AJE 净影响（科目2001短期借款：贷方增加 - 借方减少） */
  const ajeNetAmount: ComputedRef<number> = computed(() => {
    const aje2001 = ajeEntries.value.filter(e => e.accountCode === '2001')
    const credit = calcSubtotal(aje2001.map(e => e.creditAmount))
    const debit = calcSubtotal(aje2001.map(e => e.debitAmount))
    return credit - debit
  })

  /** RJE 净影响（科目2001短期借款） */
  const rjeNetAmount: ComputedRef<number> = computed(() => {
    const rje2001 = rjeEntries.value.filter(e => e.accountCode === '2001')
    const credit = calcSubtotal(rje2001.map(e => e.creditAmount))
    const debit = calcSubtotal(rje2001.map(e => e.debitAmount))
    return credit - debit
  })

  function _calcBalance(items: AdjustmentEntry[]): BalanceStatus {
    const totalDebit = parseFloat(calcSubtotal(items.map(e => e.debitAmount)).toFixed(2))
    const totalCredit = parseFloat(calcSubtotal(items.map(e => e.creditAmount)).toFixed(2))
    const diff = parseFloat((totalDebit - totalCredit).toFixed(2))
    return {
      totalDebit,
      totalCredit,
      diff,
      isBalanced: Math.abs(diff) <= BALANCE_THRESHOLD,
    }
  }

  // ─── 3. 行操作 ────────────────────────────────────────────────────────

  /**
   * 新增调整分录行
   */
  function addEntry(type?: AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: AdjustmentEntry = {
      index: entries.value.length + 1,
      type: t,
      description: '',
      accountCode: '',
      accountName: '',
      debitAmount: 0,
      creditAmount: 0,
    }
    entries.value.push(newEntry)
    _triggerSave(entries.value.length - 1)
  }

  /**
   * 删除分录行
   */
  function removeEntry(index: number): void {
    const idx = entries.value.findIndex((_, i) => i === index)
    if (idx === -1) return
    entries.value.splice(idx, 1)
    // 重新编号
    entries.value.forEach((e, i) => { e.index = i + 1 })
    _triggerSaveAll()
  }

  /**
   * 更新分录行字段
   */
  function updateEntry(
    index: number,
    field: keyof AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /**
   * 切换 AJE/RJE Tab
   */
  function switchType(type: AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 ─────────────────────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * 用于通知 A13 审计调整汇总 + L1-1 审定表
   */
  async function saveAndPublish(): Promise<void> {
    // 校验借贷平衡
    const balance = currentBalance.value
    if (!balance.isBalanced) {
      return // 不平衡时不允许发布
    }

    // 序列化并保存
    const items = entries.value.map((entry, i) => {
      const n = i + 1
      return [
        { item_id: `L1-adj-entry-${n}-type`, conclusion: null, remark: entry.type },
        { item_id: `L1-adj-entry-${n}-desc`, conclusion: null, remark: entry.description || null },
        { item_id: `L1-adj-entry-${n}-code`, conclusion: null, remark: entry.accountCode || null },
        { item_id: `L1-adj-entry-${n}-name`, conclusion: null, remark: entry.accountName || null },
        { item_id: `L1-adj-entry-${n}-debit`, conclusion: null, remark: entry.debitAmount ? String(entry.debitAmount) : null },
        { item_id: `L1-adj-entry-${n}-credit`, conclusion: null, remark: entry.creditAmount ? String(entry.creditAmount) : null },
      ]
    }).flat()

    await saveImmediate(items)

    // EventBus publish
    eventBus.emit('adjustment:created', {
      wpCode: 'L1',
      type: activeType.value,
      entries: filteredEntries.value,
      balance: balance,
      timestamp: Date.now(),
    })
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    const items = [
      { item_id: `L1-adj-entry-${n}-type`, conclusion: null, remark: entry.type },
      { item_id: `L1-adj-entry-${n}-desc`, conclusion: null, remark: entry.description || null },
      { item_id: `L1-adj-entry-${n}-code`, conclusion: null, remark: entry.accountCode || null },
      { item_id: `L1-adj-entry-${n}-name`, conclusion: null, remark: entry.accountName || null },
      { item_id: `L1-adj-entry-${n}-debit`, conclusion: null, remark: entry.debitAmount ? String(entry.debitAmount) : null },
      { item_id: `L1-adj-entry-${n}-credit`, conclusion: null, remark: entry.creditAmount ? String(entry.creditAmount) : null },
    ]
    debounceSave(items)
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < entries.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // State
    entries,
    activeType,

    // 计算
    filteredEntries,
    ajeEntries,
    rjeEntries,
    ajeBalance,
    rjeBalance,
    currentBalance,
    ajeNetAmount,
    rjeNetAmount,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存
    saveAndPublish,
  }
}

export default useL1Adjustment
