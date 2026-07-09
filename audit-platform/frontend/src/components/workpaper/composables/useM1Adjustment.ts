/**
 * useM1Adjustment — M1-3 调整分录汇总 composable
 *
 * Spec: .kiro/specs/m1-dividends-payable/
 * Task: 3.4
 * Requirements: 6.3
 *
 * 职责：
 * - AJE/RJE 调整分录行管理
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步M1-1审定表（通过EventBus通知）
 *
 * xlsx 结构（调整分录汇总M1-3）：
 *   A(调整事项说明) | B(类别：报表调整/账项调整/其他) | C(报表项目)
 *   D(科目名称) | E(附注项目) | F(借方调整金额) | G(贷方调整金额)
 *   H(索引) | I(备注)
 *
 * 科目：2232 应付股利（贷方/负债类）
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useM1FormulaEngine'
import type { useM1FormData } from './useM1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type M1AdjustmentType = 'AJE' | 'RJE'

/** 调整分录类别 */
export type M1AdjustmentCategory = '报表调整' | '账项调整' | '其他' | ''

/** 调整分录行 */
export interface M1AdjustmentEntry {
  /** 序号 */
  index: number
  /** 调整事项说明（A列） */
  description: string
  /** 类别（B列） */
  category: M1AdjustmentCategory
  /** 报表项目（C列） */
  reportItem: string
  /** 科目名称（D列） */
  accountName: string
  /** 附注项目（E列） */
  noteItem: string
  /** AJE or RJE */
  type: M1AdjustmentType
  /** 借方调整金额（F列） */
  debitAmount: number
  /** 贷方调整金额（G列） */
  creditAmount: number
  /** 索引（H列） */
  refIndex: string
  /** 备注（I列） */
  remark: string
}

/** 借贷平衡状态 */
export interface M1BalanceStatus {
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
 * M1-3 调整分录业务逻辑
 *
 * @param formData 由调用方传入的 useM1FormData 实例
 */
export function useM1Adjustment(formData: ReturnType<typeof useM1FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<M1AdjustmentEntry[]>([])
  const activeType = ref<M1AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型（AJE/RJE）的分录 */
  const filteredEntries: ComputedRef<M1AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<M1AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<M1AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<M1BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<M1BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<M1BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /** AJE 对科目2232应付股利的净影响（贷方增加-借方减少，负债类贷方） */
  const ajeNet2232: ComputedRef<number> = computed(() => {
    const entries2232 = ajeEntries.value.filter(e => e.accountName.includes('应付股利'))
    const credit = calcSubtotal(entries2232.map(e => e.creditAmount))
    const debit = calcSubtotal(entries2232.map(e => e.debitAmount))
    return credit - debit // 负债类：贷方净增
  })

  /** RJE 对科目2232的净影响 */
  const rjeNet2232: ComputedRef<number> = computed(() => {
    const entries2232 = rjeEntries.value.filter(e => e.accountName.includes('应付股利'))
    const credit = calcSubtotal(entries2232.map(e => e.creditAmount))
    const debit = calcSubtotal(entries2232.map(e => e.debitAmount))
    return credit - debit
  })

  function _calcBalance(items: M1AdjustmentEntry[]): M1BalanceStatus {
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
  function addEntry(type?: M1AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: M1AdjustmentEntry = {
      index: entries.value.length + 1,
      description: '',
      category: '',
      reportItem: '',
      accountName: '',
      noteItem: '',
      type: t,
      debitAmount: 0,
      creditAmount: 0,
      refIndex: '',
      remark: '',
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
    field: keyof M1AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: M1AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步M1-1 ─────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * - 借贷平衡校验通过才允许发布
   * - 通知 A13 审计调整汇总
   * - 双向同步 M1-1 审定表（M1-1 订阅该事件刷新 AJE/RJE 列）
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
        { itemId: `M1-M1-3-entry-${n}-type`, data: { remark: entry.type } },
        { itemId: `M1-M1-3-entry-${n}-desc`, data: { remark: entry.description || null } },
        { itemId: `M1-M1-3-entry-${n}-category`, data: { remark: entry.category || null } },
        { itemId: `M1-M1-3-entry-${n}-report`, data: { remark: entry.reportItem || null } },
        { itemId: `M1-M1-3-entry-${n}-account`, data: { remark: entry.accountName || null } },
        { itemId: `M1-M1-3-entry-${n}-note`, data: { remark: entry.noteItem || null } },
        { itemId: `M1-M1-3-entry-${n}-debit`, data: { remark: entry.debitAmount ? String(entry.debitAmount) : null } },
        { itemId: `M1-M1-3-entry-${n}-credit`, data: { remark: entry.creditAmount ? String(entry.creditAmount) : null } },
        { itemId: `M1-M1-3-entry-${n}-ref`, data: { remark: entry.refIndex || null } },
        { itemId: `M1-M1-3-entry-${n}-remark`, data: { remark: entry.remark || null } },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish（双向同步M1-1 + 通知A13）
    eventBus.emit('adjustment:created', {
      wpCode: 'M1',
      accountCode: '2232',
      ajeNet: ajeNet2232.value,
      rjeNet: rjeNet2232.value,
      timestamp: Date.now(),
    } as any)
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    const pairs: [string, string | null][] = [
      [`M1-M1-3-entry-${n}-type`, entry.type],
      [`M1-M1-3-entry-${n}-desc`, entry.description || null],
      [`M1-M1-3-entry-${n}-category`, entry.category || null],
      [`M1-M1-3-entry-${n}-report`, entry.reportItem || null],
      [`M1-M1-3-entry-${n}-account`, entry.accountName || null],
      [`M1-M1-3-entry-${n}-note`, entry.noteItem || null],
      [`M1-M1-3-entry-${n}-debit`, entry.debitAmount ? String(entry.debitAmount) : null],
      [`M1-M1-3-entry-${n}-credit`, entry.creditAmount ? String(entry.creditAmount) : null],
      [`M1-M1-3-entry-${n}-ref`, entry.refIndex || null],
      [`M1-M1-3-entry-${n}-remark`, entry.remark || null],
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
    ajeNet2232,
    rjeNet2232,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,
  }
}

export default useM1Adjustment
