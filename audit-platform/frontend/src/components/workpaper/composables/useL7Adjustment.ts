/**
 * useL7Adjustment — L7-3 调整分录 composable
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/
 * Task: 3.4
 * Requirements: 4.3
 *
 * 职责：
 * - AJE/RJE 调整分录行管理
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步L7-1审定表（通过EventBus通知）
 *
 * xlsx 结构（调整分录汇总L7-3）：
 *   A(调整事项说明) | B(类别：报表调整/账项调整/其他) | C(报表项目)
 *   D(科目名称) | E(附注项目) | F(...) | G(借方调整金额) | H(贷方调整金额)
 *   I(索引) | J(备注)
 *
 * 科目：2801 其他非流动负债（贷方/负债类）
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useL7FormulaEngine'
import type { useL7FormData } from './useL7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type L7AdjustmentType = 'AJE' | 'RJE'

/** 调整分录类别（xlsx B列） */
export type L7AdjustmentCategory = '报表调整' | '账项调整' | '其他' | ''

/** 调整分录行（对应xlsx A-J列） */
export interface L7AdjustmentEntry {
  /** 序号 */
  index: number
  /** 调整事项说明（A列） */
  description: string
  /** 类别（B列：报表调整/账项调整/其他） */
  category: L7AdjustmentCategory
  /** 报表项目（C列） */
  reportItem: string
  /** 科目名称（D列） */
  accountName: string
  /** 附注项目（E列） */
  noteItem: string
  /** AJE or RJE */
  type: L7AdjustmentType
  /** 借方调整金额（G列） */
  debitAmount: number
  /** 贷方调整金额（H列） */
  creditAmount: number
  /** 索引（I列） */
  refIndex: string
}

/** 借贷平衡状态 */
export interface L7BalanceStatus {
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
 * L7-3 调整分录业务逻辑
 *
 * @param formData 由调用方传入的 useL7FormData 实例
 */
export function useL7Adjustment(formData: ReturnType<typeof useL7FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<L7AdjustmentEntry[]>([])
  const activeType = ref<L7AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型（AJE/RJE）的分录 */
  const filteredEntries: ComputedRef<L7AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<L7AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<L7AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<L7BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<L7BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<L7BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /** AJE 对科目2801其他非流动负债的净影响（贷方增加-借方减少，负债类贷方） */
  const ajeNet2801: ComputedRef<number> = computed(() => {
    const entries2801 = ajeEntries.value.filter(e => e.accountName.includes('其他非流动负债'))
    const credit = calcSubtotal(entries2801.map(e => e.creditAmount))
    const debit = calcSubtotal(entries2801.map(e => e.debitAmount))
    return credit - debit
  })

  /** RJE 对科目2801的净影响 */
  const rjeNet2801: ComputedRef<number> = computed(() => {
    const entries2801 = rjeEntries.value.filter(e => e.accountName.includes('其他非流动负债'))
    const credit = calcSubtotal(entries2801.map(e => e.creditAmount))
    const debit = calcSubtotal(entries2801.map(e => e.debitAmount))
    return credit - debit
  })

  function _calcBalance(items: L7AdjustmentEntry[]): L7BalanceStatus {
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
  function addEntry(type?: L7AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: L7AdjustmentEntry = {
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
    field: keyof L7AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: L7AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步L7-1 ─────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * - 借贷平衡校验通过才允许发布
   * - 通知 A13 审计调整汇总
   * - 双向同步 L7-1 审定表（L7-1 订阅该事件刷新 AJE/RJE 列）
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
        { itemId: `L7-L7-3-entry-${n}-type`, data: { remark: entry.type } },
        { itemId: `L7-L7-3-entry-${n}-desc`, data: { remark: entry.description || null } },
        { itemId: `L7-L7-3-entry-${n}-category`, data: { remark: entry.category || null } },
        { itemId: `L7-L7-3-entry-${n}-report`, data: { remark: entry.reportItem || null } },
        { itemId: `L7-L7-3-entry-${n}-account`, data: { remark: entry.accountName || null } },
        { itemId: `L7-L7-3-entry-${n}-note`, data: { remark: entry.noteItem || null } },
        { itemId: `L7-L7-3-entry-${n}-debit`, data: { remark: entry.debitAmount ? String(entry.debitAmount) : null } },
        { itemId: `L7-L7-3-entry-${n}-credit`, data: { remark: entry.creditAmount ? String(entry.creditAmount) : null } },
        { itemId: `L7-L7-3-entry-${n}-ref`, data: { remark: entry.refIndex || null } },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish（双向同步L7-1 + 通知A13）
    eventBus.emit('adjustment:created', {
      wpCode: 'L7',
      accountCode: 'BS-071', // L7 宁缺勿造，EventBus 用报表行标识（2801 是预计负债 K5）
      ajeNet: ajeNet2801.value,
      rjeNet: rjeNet2801.value,
      timestamp: Date.now(),
    } as any)
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    const pairs: [string, string | null][] = [
      [`L7-L7-3-entry-${n}-type`, entry.type],
      [`L7-L7-3-entry-${n}-desc`, entry.description || null],
      [`L7-L7-3-entry-${n}-category`, entry.category || null],
      [`L7-L7-3-entry-${n}-report`, entry.reportItem || null],
      [`L7-L7-3-entry-${n}-account`, entry.accountName || null],
      [`L7-L7-3-entry-${n}-note`, entry.noteItem || null],
      [`L7-L7-3-entry-${n}-debit`, entry.debitAmount ? String(entry.debitAmount) : null],
      [`L7-L7-3-entry-${n}-credit`, entry.creditAmount ? String(entry.creditAmount) : null],
      [`L7-L7-3-entry-${n}-ref`, entry.refIndex || null],
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
    ajeNet2801,
    rjeNet2801,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,
  }
}

export default useL7Adjustment
