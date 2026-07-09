/**
 * useM7Adjustment — M7-3 调整分录汇总 composable
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Task: 3.4
 * Requirements: 6.1
 *
 * 职责：
 * - AJE/RJE 调整分录行管理
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步M7-1审定表（M7-1订阅该事件刷新AJE/RJE列）
 * - 动态行管理
 *
 * 科目：4201 专项储备（**贷方/权益类！**）
 * 调增专项储备→贷方增加（贷记4201），调减专项储备→借方减少（借记4201）
 *
 * 专项储备调整典型场景：
 * - 补提安全生产费：借:生产成本/管理费用 贷:专项储备
 * - 冲回多计提：借:专项储备 贷:生产成本/管理费用
 * - 资本化支出调整：借:专项储备 贷:累计折旧-专项储备折旧
 * - 计提基础调整（产量/收入重述）
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useM7FormulaEngine'
import type { useM7FormData } from './useM7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type M7AdjustmentType = 'AJE' | 'RJE'

/** 调整分录类别 */
export type M7AdjustmentCategory = '报表调整' | '账项调整' | '重分类' | '其他' | ''

/** 调整分录行 */
export interface M7AdjustmentEntry {
  /** 序号 */
  index: number
  /** 调整事项说明 */
  description: string
  /** 类别 */
  category: M7AdjustmentCategory
  /** 报表项目 */
  reportItem: string
  /** 科目名称 */
  accountName: string
  /** 附注项目 */
  noteItem: string
  /** AJE or RJE */
  type: M7AdjustmentType
  /** 借方调整金额 */
  debitAmount: number
  /** 贷方调整金额 */
  creditAmount: number
  /** 索引号 */
  refIndex: string
  /** 备注 */
  remark: string
}

/** 借贷平衡状态 */
export interface M7BalanceStatus {
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

const BALANCE_THRESHOLD = 0.01

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M7-3 调整分录业务逻辑（借贷平衡+EventBus+双向同步M7-1）
 *
 * @param formData 由调用方传入的 useM7FormData 实例
 */
export function useM7Adjustment(formData: ReturnType<typeof useM7FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<M7AdjustmentEntry[]>([])
  const activeType = ref<M7AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型的分录 */
  const filteredEntries: ComputedRef<M7AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<M7AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<M7AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<M7BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<M7BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<M7BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /**
   * AJE 对科目4201专项储备的净影响
   * 专项储备是贷方权益类：贷方增加=调增专项储备，借方减少=调减专项储备
   * 净影响 = 贷方 - 借方（正=净增，负=净减）
   */
  const ajeNet4201: ComputedRef<number> = computed(() => {
    const entries4201 = ajeEntries.value.filter(e => e.accountName.includes('专项储备'))
    const debit = calcSubtotal(entries4201.map(e => e.debitAmount))
    const credit = calcSubtotal(entries4201.map(e => e.creditAmount))
    return credit - debit // 权益类贷方：贷方净增=调增
  })

  /** RJE 对科目4201的净影响 */
  const rjeNet4201: ComputedRef<number> = computed(() => {
    const entries4201 = rjeEntries.value.filter(e => e.accountName.includes('专项储备'))
    const debit = calcSubtotal(entries4201.map(e => e.debitAmount))
    const credit = calcSubtotal(entries4201.map(e => e.creditAmount))
    return credit - debit // 权益类贷方：贷方净增=调增
  })

  function _calcBalance(items: M7AdjustmentEntry[]): M7BalanceStatus {
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

  // ─── 3. 行操作（动态行管理） ──────────────────────────────────────────

  /** 新增调整分录行 */
  function addEntry(type?: M7AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: M7AdjustmentEntry = {
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
    field: keyof M7AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: M7AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步M7-1 ─────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * - 借贷平衡校验通过才允许发布
   * - 通知 A13 审计调整汇总
   * - 双向同步 M7-1 审定表（M7-1 订阅该事件刷新 AJE/RJE 列）
   */
  async function saveAndPublish(): Promise<void> {
    const balance = currentBalance.value
    if (!balance.isBalanced) {
      return // 不平衡时不允许发布
    }

    // 批量保存
    const items = entries.value.map((entry, i) => {
      const n = i + 1
      return [
        { itemId: `M7-3-entry-${n}-type`, data: { remark: entry.type } },
        { itemId: `M7-3-entry-${n}-desc`, data: { remark: entry.description || null } },
        { itemId: `M7-3-entry-${n}-category`, data: { remark: entry.category || null } },
        { itemId: `M7-3-entry-${n}-report`, data: { remark: entry.reportItem || null } },
        { itemId: `M7-3-entry-${n}-account`, data: { remark: entry.accountName || null } },
        { itemId: `M7-3-entry-${n}-note`, data: { remark: entry.noteItem || null } },
        { itemId: `M7-3-entry-${n}-debit`, data: { remark: entry.debitAmount ? String(entry.debitAmount) : null } },
        { itemId: `M7-3-entry-${n}-credit`, data: { remark: entry.creditAmount ? String(entry.creditAmount) : null } },
        { itemId: `M7-3-entry-${n}-ref`, data: { remark: entry.refIndex || null } },
        { itemId: `M7-3-entry-${n}-remark`, data: { remark: entry.remark || null } },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish（双向同步M7-1 + 通知A13）
    eventBus.emit('adjustment:created', {
      wpCode: 'M7',
      accountCode: '4201',
      ajeNet: ajeNet4201.value,
      rjeNet: rjeNet4201.value,
      timestamp: Date.now(),
    } as any)
  }

  // ─── 5. EventBus 订阅（从M7-1接收审定数变化） ─────────────────────────

  /**
   * 订阅 M7-1 审定事件（双向同步：当M7-1审定数变化时同步刷新M7-3状态）
   */
  function subscribeAdjudicated(callback: (payload: any) => void): () => void {
    const handler = (payload: any) => {
      if (payload?.wpCode === 'M7' && payload?.accountCode === '4201') {
        callback(payload)
      }
    }
    eventBus.on('substantive:adjudicated' as any, handler)
    return () => eventBus.off('substantive:adjudicated' as any, handler)
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    debouncedSave(`M7-3-entry-${n}-data`, {
      remark: JSON.stringify({
        index: entry.index,
        type: entry.type,
        description: entry.description,
        category: entry.category,
        reportItem: entry.reportItem,
        accountName: entry.accountName,
        noteItem: entry.noteItem,
        debitAmount: entry.debitAmount,
        creditAmount: entry.creditAmount,
        refIndex: entry.refIndex,
        remark: entry.remark,
      }),
    })
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
    ajeNet4201,
    rjeNet4201,

    // 行操作（动态行管理）
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,

    // EventBus订阅
    subscribeAdjudicated,
  }
}

export default useM7Adjustment
