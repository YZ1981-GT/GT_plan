/**
 * useM3Adjustment — M3-3 调整分录汇总 composable
 *
 * Spec: .kiro/specs/m3-treasury-stock/
 * Task: 3.4
 * Requirements: 6.1-6.3
 *
 * 职责：
 * - AJE/RJE 调整分录行管理
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步M3-1审定表（M3-1订阅该事件刷新AJE/RJE列）
 *
 * 科目：4002 库存股（**借方/权益备抵类！**）
 * 调增库存股→借方增加（借记4002），调减库存股→贷方减少（贷记4002）
 * 注意方向与M2（权益类贷方增加）相反！
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useM3FormulaEngine'
import type { useM3FormData } from './useM3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type M3AdjustmentType = 'AJE' | 'RJE'

/** 调整分录类别 */
export type M3AdjustmentCategory = '报表调整' | '账项调整' | '其他' | ''

/** 调整分录行 */
export interface M3AdjustmentEntry {
  /** 序号 */
  index: number
  /** 调整事项说明 */
  description: string
  /** 类别 */
  category: M3AdjustmentCategory
  /** 报表项目 */
  reportItem: string
  /** 科目名称 */
  accountName: string
  /** 附注项目 */
  noteItem: string
  /** AJE or RJE */
  type: M3AdjustmentType
  /** 借方调整金额 */
  debitAmount: number
  /** 贷方调整金额 */
  creditAmount: number
  /** 索引 */
  refIndex: string
  /** 备注 */
  remark: string
}

/** 借贷平衡状态 */
export interface M3BalanceStatus {
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
 * M3-3 调整分录业务逻辑（借贷平衡+EventBus+双向同步M3-1）
 *
 * @param formData 由调用方传入的 useM3FormData 实例
 */
export function useM3Adjustment(formData: ReturnType<typeof useM3FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<M3AdjustmentEntry[]>([])
  const activeType = ref<M3AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型的分录 */
  const filteredEntries: ComputedRef<M3AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<M3AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<M3AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<M3BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<M3BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<M3BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /**
   * AJE 对科目4002库存股的净影响
   * 库存股是借方备抵：借方增加=调增库存股，贷方减少=调减库存股
   * 净影响 = 借方 - 贷方（正=净增，负=净减）
   */
  const ajeNet4002: ComputedRef<number> = computed(() => {
    const entries4002 = ajeEntries.value.filter(e => e.accountName.includes('库存股'))
    const debit = calcSubtotal(entries4002.map(e => e.debitAmount))
    const credit = calcSubtotal(entries4002.map(e => e.creditAmount))
    return debit - credit // 备抵借方：借方净增=调增
  })

  /** RJE 对科目4002的净影响 */
  const rjeNet4002: ComputedRef<number> = computed(() => {
    const entries4002 = rjeEntries.value.filter(e => e.accountName.includes('库存股'))
    const debit = calcSubtotal(entries4002.map(e => e.debitAmount))
    const credit = calcSubtotal(entries4002.map(e => e.creditAmount))
    return debit - credit
  })

  function _calcBalance(items: M3AdjustmentEntry[]): M3BalanceStatus {
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
  function addEntry(type?: M3AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: M3AdjustmentEntry = {
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
    field: keyof M3AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: M3AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步M3-1 ─────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * - 借贷平衡校验通过才允许发布
   * - 通知 A13 审计调整汇总
   * - 双向同步 M3-1 审定表（M3-1 订阅该事件刷新 AJE/RJE 列）
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
        { itemId: `M3-M3-3-entry-${n}-type`, data: { remark: entry.type } },
        { itemId: `M3-M3-3-entry-${n}-desc`, data: { remark: entry.description || null } },
        { itemId: `M3-M3-3-entry-${n}-category`, data: { remark: entry.category || null } },
        { itemId: `M3-M3-3-entry-${n}-report`, data: { remark: entry.reportItem || null } },
        { itemId: `M3-M3-3-entry-${n}-account`, data: { remark: entry.accountName || null } },
        { itemId: `M3-M3-3-entry-${n}-note`, data: { remark: entry.noteItem || null } },
        { itemId: `M3-M3-3-entry-${n}-debit`, data: { remark: entry.debitAmount ? String(entry.debitAmount) : null } },
        { itemId: `M3-M3-3-entry-${n}-credit`, data: { remark: entry.creditAmount ? String(entry.creditAmount) : null } },
        { itemId: `M3-M3-3-entry-${n}-ref`, data: { remark: entry.refIndex || null } },
        { itemId: `M3-M3-3-entry-${n}-remark`, data: { remark: entry.remark || null } },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish（双向同步M3-1 + 通知A13）
    eventBus.emit('adjustment:created', {
      wpCode: 'M3',
      accountCode: '4002',
      ajeNet: ajeNet4002.value,
      rjeNet: rjeNet4002.value,
      timestamp: Date.now(),
    } as any)
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    debouncedSave(`M3-M3-3-entry-${n}-data`, {
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
    ajeNet4002,
    rjeNet4002,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,
  }
}

export default useM3Adjustment
