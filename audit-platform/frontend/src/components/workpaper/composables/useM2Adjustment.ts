/**
 * useM2Adjustment — M2-3 调整分录汇总 composable
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Task: 3.4
 * Requirements: 6.1-6.3
 *
 * 职责：
 * - AJE/RJE 调整分录行管理
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步M2-1审定表（通过EventBus通知，M2-1订阅刷新AJE/RJE列）
 *
 * xlsx 结构（调整分录汇总M2-3）：
 *   A(调整事项说明) | B(类别：报表调整/账项调整/其他) | C(报表项目)
 *   D(科目名称) | E(附注项目) | F(借方调整金额) | G(贷方调整金额)
 *   H(索引) | I(备注)
 *
 * 科目：4001 实收资本/股本（贷方/权益类！）
 * 调增实收资本→贷方增加（贷记4001），调减→借方减少（借记4001）
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useM2FormulaEngine'
import type { useM2FormData } from './useM2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type M2AdjustmentType = 'AJE' | 'RJE'

/** 调整分录类别 */
export type M2AdjustmentCategory = '报表调整' | '账项调整' | '其他' | ''

/** 调整分录行 */
export interface M2AdjustmentEntry {
  /** 序号 */
  index: number
  /** 调整事项说明（A列） */
  description: string
  /** 类别（B列） */
  category: M2AdjustmentCategory
  /** 报表项目（C列） */
  reportItem: string
  /** 科目名称（D列） */
  accountName: string
  /** 附注项目（E列） */
  noteItem: string
  /** AJE or RJE */
  type: M2AdjustmentType
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
export interface M2BalanceStatus {
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
 * M2-3 调整分录业务逻辑
 *
 * @param formData 由调用方传入的 useM2FormData 实例
 */
export function useM2Adjustment(formData: ReturnType<typeof useM2FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<M2AdjustmentEntry[]>([])
  const activeType = ref<M2AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型（AJE/RJE）的分录 */
  const filteredEntries: ComputedRef<M2AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<M2AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<M2AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<M2BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<M2BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<M2BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /** AJE 对科目4001实收资本的净影响（贷方增加-借方减少，权益类贷方） */
  const ajeNet4001: ComputedRef<number> = computed(() => {
    const entries4001 = ajeEntries.value.filter(e => e.accountName.includes('实收资本') || e.accountName.includes('股本'))
    const credit = calcSubtotal(entries4001.map(e => e.creditAmount))
    const debit = calcSubtotal(entries4001.map(e => e.debitAmount))
    return credit - debit // 权益类：贷方净增=调增
  })

  /** RJE 对科目4001的净影响 */
  const rjeNet4001: ComputedRef<number> = computed(() => {
    const entries4001 = rjeEntries.value.filter(e => e.accountName.includes('实收资本') || e.accountName.includes('股本'))
    const credit = calcSubtotal(entries4001.map(e => e.creditAmount))
    const debit = calcSubtotal(entries4001.map(e => e.debitAmount))
    return credit - debit
  })

  function _calcBalance(items: M2AdjustmentEntry[]): M2BalanceStatus {
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
  function addEntry(type?: M2AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: M2AdjustmentEntry = {
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
    field: keyof M2AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: M2AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步M2-1 ─────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * - 借贷平衡校验通过才允许发布
   * - 通知 A13 审计调整汇总
   * - 双向同步 M2-1 审定表（M2-1 订阅该事件刷新 AJE/RJE 列）
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
        { itemId: `M2-M2-3-entry-${n}-type`, data: { remark: entry.type } },
        { itemId: `M2-M2-3-entry-${n}-desc`, data: { remark: entry.description || null } },
        { itemId: `M2-M2-3-entry-${n}-category`, data: { remark: entry.category || null } },
        { itemId: `M2-M2-3-entry-${n}-report`, data: { remark: entry.reportItem || null } },
        { itemId: `M2-M2-3-entry-${n}-account`, data: { remark: entry.accountName || null } },
        { itemId: `M2-M2-3-entry-${n}-note`, data: { remark: entry.noteItem || null } },
        { itemId: `M2-M2-3-entry-${n}-debit`, data: { remark: entry.debitAmount ? String(entry.debitAmount) : null } },
        { itemId: `M2-M2-3-entry-${n}-credit`, data: { remark: entry.creditAmount ? String(entry.creditAmount) : null } },
        { itemId: `M2-M2-3-entry-${n}-ref`, data: { remark: entry.refIndex || null } },
        { itemId: `M2-M2-3-entry-${n}-remark`, data: { remark: entry.remark || null } },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish（双向同步M2-1 + 通知A13）
    eventBus.emit('adjustment:created', {
      wpCode: 'M2',
      accountCode: '4001',
      ajeNet: ajeNet4001.value,
      rjeNet: rjeNet4001.value,
      timestamp: Date.now(),
    } as any)
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    const pairs: [string, string | null][] = [
      [`M2-M2-3-entry-${n}-type`, entry.type],
      [`M2-M2-3-entry-${n}-desc`, entry.description || null],
      [`M2-M2-3-entry-${n}-category`, entry.category || null],
      [`M2-M2-3-entry-${n}-report`, entry.reportItem || null],
      [`M2-M2-3-entry-${n}-account`, entry.accountName || null],
      [`M2-M2-3-entry-${n}-note`, entry.noteItem || null],
      [`M2-M2-3-entry-${n}-debit`, entry.debitAmount ? String(entry.debitAmount) : null],
      [`M2-M2-3-entry-${n}-credit`, entry.creditAmount ? String(entry.creditAmount) : null],
      [`M2-M2-3-entry-${n}-ref`, entry.refIndex || null],
      [`M2-M2-3-entry-${n}-remark`, entry.remark || null],
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
    ajeNet4001,
    rjeNet4001,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,
  }
}

export default useM2Adjustment
