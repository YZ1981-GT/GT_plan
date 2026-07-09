/**
 * useM6Adjustment — M6-3 调整分录汇总 composable
 *
 * Spec: .kiro/specs/m6-retained-earnings/
 * Task: 3.4
 * Requirements: 5.3
 *
 * 职责：
 * - AJE/RJE 调整分录行管理
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步M6-1审定表（M6-1订阅该事件刷新AJE/RJE列）
 *
 * 科目：4104 利润分配-未分配利润（**贷方/权益类！**）
 * 调增未分配利润→贷方增加（贷记4104），调减未分配利润→借方减少（借记4104）
 *
 * 未分配利润调整典型场景：
 * - 利润表科目调整影响净利润→间接影响未分配利润
 * - 直接调整期初未分配利润（前期差错追溯）：借:利润分配-未分配利润 贷:相关科目
 * - 补提盈余公积：借:利润分配-未分配利润 贷:盈余公积
 * - 冲回多计利润：借:利润分配-未分配利润 贷:以前年度损益调整
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useM6FormulaEngine'
import type { useM6FormData } from './useM6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type M6AdjustmentType = 'AJE' | 'RJE'

/** 调整分录类别 */
export type M6AdjustmentCategory = '报表调整' | '账项调整' | '重分类' | '前期差错' | '其他' | ''

/** 调整分录行 */
export interface M6AdjustmentEntry {
  /** 序号 */
  index: number
  /** 调整事项说明 */
  description: string
  /** 类别 */
  category: M6AdjustmentCategory
  /** 报表项目 */
  reportItem: string
  /** 科目名称 */
  accountName: string
  /** 附注项目 */
  noteItem: string
  /** AJE or RJE */
  type: M6AdjustmentType
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
export interface M6BalanceStatus {
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
 * M6-3 调整分录业务逻辑（借贷平衡校验+EventBus双向同步M6-1）
 *
 * @param formData 由调用方传入的 useM6FormData 实例
 */
export function useM6Adjustment(formData: ReturnType<typeof useM6FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<M6AdjustmentEntry[]>([])
  const activeType = ref<M6AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型的分录 */
  const filteredEntries: ComputedRef<M6AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<M6AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<M6AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<M6BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<M6BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<M6BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /**
   * AJE 对科目4104未分配利润的净影响
   * 未分配利润是贷方权益类：贷方增加=调增未分配利润，借方减少=调减未分配利润
   * 净影响 = 贷方 - 借方（正=净增，负=净减）
   */
  const ajeNet4104: ComputedRef<number> = computed(() => {
    const entries4104 = ajeEntries.value.filter(e =>
      e.accountName.includes('未分配利润') || e.accountName.includes('利润分配'),
    )
    const debit = calcSubtotal(entries4104.map(e => e.debitAmount))
    const credit = calcSubtotal(entries4104.map(e => e.creditAmount))
    return credit - debit // 权益类贷方：贷方净增=调增
  })

  /** RJE 对科目4104的净影响 */
  const rjeNet4104: ComputedRef<number> = computed(() => {
    const entries4104 = rjeEntries.value.filter(e =>
      e.accountName.includes('未分配利润') || e.accountName.includes('利润分配'),
    )
    const debit = calcSubtotal(entries4104.map(e => e.debitAmount))
    const credit = calcSubtotal(entries4104.map(e => e.creditAmount))
    return credit - debit // 权益类贷方：贷方净增=调增
  })

  function _calcBalance(items: M6AdjustmentEntry[]): M6BalanceStatus {
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
  function addEntry(type?: M6AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: M6AdjustmentEntry = {
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
    field: keyof M6AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: M6AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步M6-1 ─────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * - 借贷平衡校验通过才允许发布
   * - 通知 A13 审计调整汇总
   * - 双向同步 M6-1 审定表（M6-1 订阅该事件刷新 AJE/RJE 列）
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
        { itemId: `M6-3-entry-${n}-type`, data: { remark: entry.type } },
        { itemId: `M6-3-entry-${n}-desc`, data: { remark: entry.description || null } },
        { itemId: `M6-3-entry-${n}-category`, data: { remark: entry.category || null } },
        { itemId: `M6-3-entry-${n}-report`, data: { remark: entry.reportItem || null } },
        { itemId: `M6-3-entry-${n}-account`, data: { remark: entry.accountName || null } },
        { itemId: `M6-3-entry-${n}-note`, data: { remark: entry.noteItem || null } },
        { itemId: `M6-3-entry-${n}-debit`, data: { remark: entry.debitAmount ? String(entry.debitAmount) : null } },
        { itemId: `M6-3-entry-${n}-credit`, data: { remark: entry.creditAmount ? String(entry.creditAmount) : null } },
        { itemId: `M6-3-entry-${n}-ref`, data: { remark: entry.refIndex || null } },
        { itemId: `M6-3-entry-${n}-remark`, data: { remark: entry.remark || null } },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish（双向同步M6-1 + 通知A13）
    eventBus.emit('adjustment:created', {
      wpCode: 'M6',
      accountCode: '4104',
      ajeNet: ajeNet4104.value,
      rjeNet: rjeNet4104.value,
      timestamp: Date.now(),
    } as any)
  }

  // ─── 5. 加载已保存数据 ────────────────────────────────────────────────

  /** 从 allResponses 恢复调整分录数据 */
  function loadFromResponses(allResponses: Map<string, any>): void {
    const loaded: M6AdjustmentEntry[] = []
    let i = 1
    while (true) {
      const resp = allResponses.get(`M6-3-entry-${i}-data`)
      if (!resp?.remark) break
      try {
        const data = JSON.parse(resp.remark)
        loaded.push({
          index: i,
          description: data.description || '',
          category: data.category || '',
          reportItem: data.reportItem || '',
          accountName: data.accountName || '',
          noteItem: data.noteItem || '',
          type: data.type || 'AJE',
          debitAmount: data.debitAmount || 0,
          creditAmount: data.creditAmount || 0,
          refIndex: data.refIndex || '',
          remark: data.remark || '',
        })
      } catch { /* ignore parse error */ }
      i++
    }
    if (loaded.length > 0) {
      entries.value = loaded
    }
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    debouncedSave(`M6-3-entry-${n}-data`, {
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
    ajeNet4104,
    rjeNet4104,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,

    // 加载
    loadFromResponses,
  }
}

export default useM6Adjustment
