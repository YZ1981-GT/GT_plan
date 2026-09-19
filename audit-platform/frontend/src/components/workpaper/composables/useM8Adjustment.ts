/**
 * useM8Adjustment — M8-3 调整分录汇总 composable
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 3.4
 * Requirements: 4.1
 *
 * 职责：
 * - AJE/RJE 调整分录动态行管理
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步M8-1审定表（M8-1订阅该事件刷新AJE/RJE列）
 * - 列结构（24×10，xlsx调整分录汇总M8-3）：
 *   A:调整事项说明 | B:类别 | C:报表项目 | D:科目名称 | E:附注项目
 *   F:…… | G:借方调整金额 | H:贷方调整金额 | I:索引 | J:备注
 *
 * 科目：4104 一般风险准备（**贷方/权益类！**）
 * 调增一般风险准备→贷方增加（贷记4104），调减→借方减少（借记4104）
 *
 * 一般风险准备调整典型场景：
 * - 补提一般风险准备：借:利润分配-提取一般风险准备 贷:一般风险准备
 * - 冲回多计提：借:一般风险准备 贷:利润分配-提取一般风险准备
 * - 监管要求补提：借:利润分配 贷:一般风险准备
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useM8FormulaEngine'
import type { useM8FormData } from './useM8FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type M8AdjustmentType = 'AJE' | 'RJE'

/** 调整分录类别 */
export type M8AdjustmentCategory = '报表调整' | '账项调整' | '重分类' | '其他' | ''

/** 调整分录行 */
export interface M8AdjustmentEntry {
  /** 序号 */
  index: number
  /** 调整事项说明（A列） */
  description: string
  /** 类别（B列） */
  category: M8AdjustmentCategory
  /** 报表项目（C列） */
  reportItem: string
  /** 科目名称（D列） */
  accountName: string
  /** 附注项目（E列） */
  noteItem: string
  /** AJE or RJE */
  type: M8AdjustmentType
  /** 借方调整金额（G列） */
  debitAmount: number
  /** 贷方调整金额（H列） */
  creditAmount: number
  /** 索引号（I列） */
  refIndex: string
  /** 备注（J列） */
  remark: string
}

/** 借贷平衡状态 */
export interface M8BalanceStatus {
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
 * M8-3 调整分录业务逻辑（借贷平衡+EventBus+双向同步M8-1）
 *
 * @param formData 由调用方传入的 useM8FormData 实例
 */
export function useM8Adjustment(formData: ReturnType<typeof useM8FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<M8AdjustmentEntry[]>([])
  const activeType = ref<M8AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型的分录 */
  const filteredEntries: ComputedRef<M8AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<M8AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<M8AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<M8BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<M8BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<M8BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /**
   * AJE 对科目4104一般风险准备的净影响
   * 一般风险准备是贷方权益类：贷方增加=调增，借方减少=调减
   * 净影响 = 贷方 - 借方（正=净增，负=净减）
   */
  const ajeNet4104: ComputedRef<number> = computed(() => {
    const entries4104 = ajeEntries.value.filter(e =>
      e.accountName.includes('一般风险准备') || e.accountName.includes('4104'),
    )
    const debit = calcSubtotal(entries4104.map(e => e.debitAmount))
    const credit = calcSubtotal(entries4104.map(e => e.creditAmount))
    return credit - debit // 权益类贷方：贷方净增=调增
  })

  /** RJE 对科目4104的净影响 */
  const rjeNet4104: ComputedRef<number> = computed(() => {
    const entries4104 = rjeEntries.value.filter(e =>
      e.accountName.includes('一般风险准备') || e.accountName.includes('4104'),
    )
    const debit = calcSubtotal(entries4104.map(e => e.debitAmount))
    const credit = calcSubtotal(entries4104.map(e => e.creditAmount))
    return credit - debit // 权益类贷方：贷方净增=调增
  })

  function _calcBalance(items: M8AdjustmentEntry[]): M8BalanceStatus {
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
  function addEntry(type?: M8AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: M8AdjustmentEntry = {
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
    field: keyof M8AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: M8AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步M8-1 ─────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * - 借贷平衡校验通过才允许发布
   * - 通知 A13 审计调整汇总
   * - 双向同步 M8-1 审定表（M8-1 订阅该事件刷新 AJE/RJE 列）
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
        { itemId: `M8-3-entry-${n}-type`, data: { remark: entry.type } },
        { itemId: `M8-3-entry-${n}-desc`, data: { remark: entry.description || null } },
        { itemId: `M8-3-entry-${n}-category`, data: { remark: entry.category || null } },
        { itemId: `M8-3-entry-${n}-report`, data: { remark: entry.reportItem || null } },
        { itemId: `M8-3-entry-${n}-account`, data: { remark: entry.accountName || null } },
        { itemId: `M8-3-entry-${n}-note`, data: { remark: entry.noteItem || null } },
        { itemId: `M8-3-entry-${n}-debit`, data: { remark: entry.debitAmount ? String(entry.debitAmount) : null } },
        { itemId: `M8-3-entry-${n}-credit`, data: { remark: entry.creditAmount ? String(entry.creditAmount) : null } },
        { itemId: `M8-3-entry-${n}-ref`, data: { remark: entry.refIndex || null } },
        { itemId: `M8-3-entry-${n}-remark`, data: { remark: entry.remark || null } },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish（双向同步M8-1 + 通知A13）
    eventBus.emit('adjustment:created', {
      wpCode: 'M8',
      accountCode: '4104',
      ajeNet: ajeNet4104.value,
      rjeNet: rjeNet4104.value,
      timestamp: Date.now(),
    })
  }

  // ─── 5. EventBus 订阅（从M8-1接收审定数变化） ─────────────────────────

  /**
   * 订阅 M8-1 审定事件（双向同步：当M8-1审定数变化时同步刷新M8-3状态）
   */
  function subscribeAdjudicated(callback: (payload: any) => void): () => void {
    const handler = (payload: any) => {
      if (payload?.wpCode === 'M8' && payload?.accountCode === '4104') {
        callback(payload)
      }
    }
    eventBus.on('substantive:adjudicated', handler)
    return () => eventBus.off('substantive:adjudicated', handler)
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    debouncedSave(`M8-3-entry-${n}-data`, {
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

export default useM8Adjustment
