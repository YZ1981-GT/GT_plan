/**
 * useL8Adjustment — L8-3 调整分录 composable
 *
 * Spec: .kiro/specs/l8-financial-expenses/
 * Task: 3.4
 * Requirements: 7.3
 *
 * 职责：
 * - AJE/RJE 调整分录行管理
 * - 列结构：调整事项说明 | 类别(报表调整/账项调整/其他)
 *   | 报表项目 | 科目名称 | 附注项目 | ... | 借方金额 | 贷方金额 | 索引 | 备注
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步L8-1审定表（通过EventBus通知，L8-1订阅刷新AJE/RJE列）
 *
 * 科目：6603 财务费用（借方/损益类！取发生额）
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useL8FormulaEngine'
import type { useL8FormData } from './useL8FormData'
import { L8_GROSS_FALLBACK_STANDARD } from './l8AccountScope'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type L8AdjustmentType = 'AJE' | 'RJE'

/** 调整分录类别 */
export type L8AdjustmentCategory = '报表调整' | '账项调整' | '其他' | ''

/** 调整分录行 */
export interface L8AdjustmentEntry {
  /** 序号 */
  index: number
  /** 调整事项说明 */
  description: string
  /** 类别（报表调整/账项调整/其他） */
  category: L8AdjustmentCategory
  /** 报表项目 */
  reportItem: string
  /** 科目名称 */
  accountName: string
  /** 附注项目 */
  noteItem: string
  /** AJE or RJE */
  type: L8AdjustmentType
  /** 借方调整金额 */
  debitAmount: number
  /** 贷方调整金额 */
  creditAmount: number
  /** 索引（交叉引用） */
  refIndex: string
  /** 备注 */
  remark: string
}

/** 借贷平衡状态 */
export interface L8BalanceStatus {
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
 * L8-3 调整分录业务逻辑
 *
 * @param formData 由调用方传入的 useL8FormData 实例
 */
export function useL8Adjustment(formData: ReturnType<typeof useL8FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<L8AdjustmentEntry[]>([])
  const activeType = ref<L8AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型（AJE/RJE）的分录 */
  const filteredEntries: ComputedRef<L8AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<L8AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<L8AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<L8BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<L8BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<L8BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /** AJE 对科目6603财务费用的净影响（借方增加-贷方减少，费用为借方科目） */
  const ajeNet6603: ComputedRef<number> = computed(() => {
    const entries6603 = ajeEntries.value.filter(e => e.accountName.includes('财务费用'))
    const debit = calcSubtotal(entries6603.map(e => e.debitAmount))
    const credit = calcSubtotal(entries6603.map(e => e.creditAmount))
    // 费用为借方科目：借方增加，贷方减少
    return debit - credit
  })

  /** RJE 对科目6603的净影响 */
  const rjeNet6603: ComputedRef<number> = computed(() => {
    const entries6603 = rjeEntries.value.filter(e => e.accountName.includes('财务费用'))
    const debit = calcSubtotal(entries6603.map(e => e.debitAmount))
    const credit = calcSubtotal(entries6603.map(e => e.creditAmount))
    return debit - credit
  })

  function _calcBalance(items: L8AdjustmentEntry[]): L8BalanceStatus {
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
  function addEntry(type?: L8AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: L8AdjustmentEntry = {
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
    field: keyof L8AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: L8AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步L8-1 ─────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * - 借贷平衡校验通过才允许发布
   * - 通知 A13 审计调整汇总
   * - 双向同步 L8-1 审定表（L8-1 订阅该事件刷新 AJE/RJE 列）
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
        { itemId: `L8-3-entry-${n}-type`, data: { remark: entry.type } },
        { itemId: `L8-3-entry-${n}-desc`, data: { remark: entry.description || null } },
        { itemId: `L8-3-entry-${n}-category`, data: { remark: entry.category || null } },
        { itemId: `L8-3-entry-${n}-report`, data: { remark: entry.reportItem || null } },
        { itemId: `L8-3-entry-${n}-account`, data: { remark: entry.accountName || null } },
        { itemId: `L8-3-entry-${n}-note`, data: { remark: entry.noteItem || null } },
        { itemId: `L8-3-entry-${n}-debit`, data: { remark: entry.debitAmount ? String(entry.debitAmount) : null } },
        { itemId: `L8-3-entry-${n}-credit`, data: { remark: entry.creditAmount ? String(entry.creditAmount) : null } },
        { itemId: `L8-3-entry-${n}-ref`, data: { remark: entry.refIndex || null } },
        { itemId: `L8-3-entry-${n}-remark`, data: { remark: entry.remark || null } },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish（双向同步L8-1 + 通知A13）
    eventBus.emit('adjustment:created', {
      wpCode: 'L8',
      accountCode: L8_GROSS_FALLBACK_STANDARD,
      ajeNet: ajeNet6603.value,
      rjeNet: rjeNet6603.value,
      timestamp: Date.now(),
    } as any)
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    const pairs: [string, string | null][] = [
      [`L8-3-entry-${n}-type`, entry.type],
      [`L8-3-entry-${n}-desc`, entry.description || null],
      [`L8-3-entry-${n}-category`, entry.category || null],
      [`L8-3-entry-${n}-report`, entry.reportItem || null],
      [`L8-3-entry-${n}-account`, entry.accountName || null],
      [`L8-3-entry-${n}-note`, entry.noteItem || null],
      [`L8-3-entry-${n}-debit`, entry.debitAmount ? String(entry.debitAmount) : null],
      [`L8-3-entry-${n}-credit`, entry.creditAmount ? String(entry.creditAmount) : null],
      [`L8-3-entry-${n}-ref`, entry.refIndex || null],
      [`L8-3-entry-${n}-remark`, entry.remark || null],
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
    ajeNet6603,
    rjeNet6603,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,
  }
}

export default useL8Adjustment
