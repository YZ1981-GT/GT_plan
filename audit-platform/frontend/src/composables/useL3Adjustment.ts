/**
 * useL3Adjustment — L3-3 调整分录 composable
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 3.4
 * Requirements: 9.1
 *
 * 职责：
 * - AJE/RJE 行管理（含重分类RJE: 借长期借款/贷一年内到期非流动负债）
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步 L3-1 审定表
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from '@/composables/useL3FormulaEngine'
import { buildReclassEntry } from '@/composables/useL3ReclassEngine'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type L3AdjustmentType = 'AJE' | 'RJE'

/** 调整分录行 */
export interface L3AdjustmentEntry {
  /** 序号 */
  index: number
  /** AJE or RJE */
  type: L3AdjustmentType
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
export interface L3BalanceStatus {
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
 * L3-3 调整分录业务逻辑
 *
 * @param formData 由调用方传入的 useL3FormData 实例
 */
export function useL3Adjustment(formData: ReturnType<typeof useL3FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<L3AdjustmentEntry[]>([])
  const activeType = ref<L3AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型（AJE/RJE）的分录 */
  const filteredEntries: ComputedRef<L3AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<L3AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<L3AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<L3BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<L3BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<L3BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /** AJE 净影响（科目2501长期借款：贷方增加 - 借方减少） */
  const ajeNetAmount: ComputedRef<number> = computed(() => {
    const aje2501 = ajeEntries.value.filter(e => e.accountCode === '2501')
    const credit = calcSubtotal(aje2501.map(e => e.creditAmount))
    const debit = calcSubtotal(aje2501.map(e => e.debitAmount))
    return credit - debit
  })

  /** RJE 净影响（科目2501长期借款） */
  const rjeNetAmount: ComputedRef<number> = computed(() => {
    const rje2501 = rjeEntries.value.filter(e => e.accountCode === '2501')
    const credit = calcSubtotal(rje2501.map(e => e.creditAmount))
    const debit = calcSubtotal(rje2501.map(e => e.debitAmount))
    return credit - debit
  })

  function _calcBalance(items: L3AdjustmentEntry[]): L3BalanceStatus {
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

  /** 新增调整分录行 */
  function addEntry(type?: L3AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: L3AdjustmentEntry = {
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

  /** 删除分录行 */
  function removeEntry(index: number): void {
    if (index < 0 || index >= entries.value.length) return
    entries.value.splice(index, 1)
    // 重新编号
    entries.value.forEach((e, i) => { e.index = i + 1 })
    _triggerSaveAll()
  }

  /** 更新分录行字段 */
  function updateEntry(
    index: number,
    field: keyof L3AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: L3AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. 重分类RJE生成 ─────────────────────────────────────────────────

  /**
   * 生成一年内到期重分类RJE分录
   * 借：长期借款（2501）
   * 贷：一年内到期的非流动负债（2801）
   *
   * @param currentPortion 一年内到期金额
   */
  function generateReclassRJE(currentPortion: number): void {
    if (currentPortion <= 0) return

    const reclass = buildReclassEntry(currentPortion)

    // 生成借方行
    const debitEntry: L3AdjustmentEntry = {
      index: entries.value.length + 1,
      type: 'RJE',
      description: reclass.description,
      accountCode: reclass.debit.accountCode,
      accountName: reclass.debit.account,
      debitAmount: reclass.debit.amount,
      creditAmount: 0,
    }
    entries.value.push(debitEntry)

    // 生成贷方行
    const creditEntry: L3AdjustmentEntry = {
      index: entries.value.length + 1,
      type: 'RJE',
      description: reclass.description,
      accountCode: reclass.credit.accountCode,
      accountName: reclass.credit.account,
      debitAmount: 0,
      creditAmount: reclass.credit.amount,
    }
    entries.value.push(creditEntry)

    _triggerSaveAll()
  }

  // ─── 5. EventBus 发布 ─────────────────────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * 用于通知 A13 审计调整汇总 + L3-1 审定表双向同步
   */
  async function saveAndPublish(): Promise<void> {
    // 校验借贷平衡
    const balance = currentBalance.value
    if (!balance.isBalanced) {
      return // 不平衡时不允许发布
    }

    // 批量保存
    const items = entries.value.map((entry, i) => {
      const n = i + 1
      return [
        { itemId: `L3-adj-entry-${n}-type`, data: { remark: entry.type } },
        { itemId: `L3-adj-entry-${n}-desc`, data: { remark: entry.description || null } },
        { itemId: `L3-adj-entry-${n}-code`, data: { remark: entry.accountCode || null } },
        { itemId: `L3-adj-entry-${n}-name`, data: { remark: entry.accountName || null } },
        { itemId: `L3-adj-entry-${n}-debit`, data: { remark: entry.debitAmount ? String(entry.debitAmount) : null } },
        { itemId: `L3-adj-entry-${n}-credit`, data: { remark: entry.creditAmount ? String(entry.creditAmount) : null } },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish
    eventBus.emit('adjustment:created', {
      wpCode: 'L3',
      type: activeType.value,
      entries: filteredEntries.value,
      balance: balance,
      timestamp: Date.now(),
    })
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    const pairs: [string, string | null][] = [
      [`L3-adj-entry-${n}-type`, entry.type],
      [`L3-adj-entry-${n}-desc`, entry.description || null],
      [`L3-adj-entry-${n}-code`, entry.accountCode || null],
      [`L3-adj-entry-${n}-name`, entry.accountName || null],
      [`L3-adj-entry-${n}-debit`, entry.debitAmount ? String(entry.debitAmount) : null],
      [`L3-adj-entry-${n}-credit`, entry.creditAmount ? String(entry.creditAmount) : null],
    ]
    for (const [itemId, remark] of pairs) {
      debouncedSave(itemId, { remark })
    }
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

    // 重分类
    generateReclassRJE,

    // 保存
    saveAndPublish,
  }
}

export default useL3Adjustment
