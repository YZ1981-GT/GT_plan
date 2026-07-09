/**
 * useM9Adjustment — M9-3 调整分录汇总 composable
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 3.4
 * Requirements: 5.1
 *
 * 职责：
 * - AJE/RJE 调整分录行管理
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步M9-1审定表（M9-1订阅该事件刷新AJE/RJE列）
 *
 * 科目：4103 其他综合收益（**贷方/权益类！**）
 * 调增OCI→贷方增加（贷记4103），调减OCI→借方减少（借记4103）
 *
 * 其他综合收益调整典型场景：
 * - OCI公允价值调整：借:其他综合收益 贷:其他权益工具投资（减少OCI）
 * - OCI重分类进损益：借:其他综合收益 贷:投资收益（重分类转出）
 * - OCI税额调整：借:递延所得税负债 贷:其他综合收益（增加OCI）
 * - 权益法核算OCI份额：借:长期股权投资-其他综合收益 贷:其他综合收益
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useM9FormulaEngine'
import type { useM9FormData } from './useM9FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type M9AdjustmentType = 'AJE' | 'RJE'

/** 调整分录类别 */
export type M9AdjustmentCategory = '报表调整' | '账项调整' | '重分类' | '其他' | ''

/** OCI调整涉及分类 */
export type M9OciAdjustBlock = 'nonReclass' | 'reclass' | ''

/** 调整分录行 */
export interface M9AdjustmentEntry {
  /** 序号 */
  index: number
  /** 调整事项说明 */
  description: string
  /** 类别 */
  category: M9AdjustmentCategory
  /** 报表项目 */
  reportItem: string
  /** 科目名称 */
  accountName: string
  /** 附注项目 */
  noteItem: string
  /** AJE or RJE */
  type: M9AdjustmentType
  /** OCI涉及分类（不可重分类/可重分类） */
  ociBlock: M9OciAdjustBlock
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
export interface M9BalanceStatus {
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
 * M9-3 调整分录业务逻辑（借贷平衡+EventBus+双向同步M9-1）
 *
 * @param formData 由调用方传入的 useM9FormData 实例
 */
export function useM9Adjustment(formData: ReturnType<typeof useM9FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<M9AdjustmentEntry[]>([])
  const activeType = ref<M9AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型的分录 */
  const filteredEntries: ComputedRef<M9AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<M9AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<M9AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<M9BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<M9BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<M9BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /**
   * AJE 对科目4103其他综合收益的净影响
   * 其他综合收益是贷方权益类：贷方增加=OCI增加，借方减少=OCI减少/重分类
   * 净影响 = 贷方 - 借方（正=净增，负=净减）
   */
  const ajeNet4103: ComputedRef<number> = computed(() => {
    const entries4103 = ajeEntries.value.filter(e => e.accountName.includes('其他综合收益'))
    const debit = calcSubtotal(entries4103.map(e => e.debitAmount))
    const credit = calcSubtotal(entries4103.map(e => e.creditAmount))
    return credit - debit // 权益类贷方：贷方净增=OCI调增
  })

  /** RJE 对科目4103的净影响 */
  const rjeNet4103: ComputedRef<number> = computed(() => {
    const entries4103 = rjeEntries.value.filter(e => e.accountName.includes('其他综合收益'))
    const debit = calcSubtotal(entries4103.map(e => e.debitAmount))
    const credit = calcSubtotal(entries4103.map(e => e.creditAmount))
    return credit - debit // 权益类贷方：贷方净增=OCI调增
  })

  /** AJE 按OCI分类（不可重分类/可重分类）的净影响 */
  const ajeNetByBlock = computed(() => {
    const nonReclass = ajeEntries.value.filter(e => e.ociBlock === 'nonReclass' && e.accountName.includes('其他综合收益'))
    const reclass = ajeEntries.value.filter(e => e.ociBlock === 'reclass' && e.accountName.includes('其他综合收益'))
    return {
      nonReclass: calcSubtotal(nonReclass.map(e => e.creditAmount)) - calcSubtotal(nonReclass.map(e => e.debitAmount)),
      reclass: calcSubtotal(reclass.map(e => e.creditAmount)) - calcSubtotal(reclass.map(e => e.debitAmount)),
    }
  })

  /** RJE 按OCI分类的净影响 */
  const rjeNetByBlock = computed(() => {
    const nonReclass = rjeEntries.value.filter(e => e.ociBlock === 'nonReclass' && e.accountName.includes('其他综合收益'))
    const reclass = rjeEntries.value.filter(e => e.ociBlock === 'reclass' && e.accountName.includes('其他综合收益'))
    return {
      nonReclass: calcSubtotal(nonReclass.map(e => e.creditAmount)) - calcSubtotal(nonReclass.map(e => e.debitAmount)),
      reclass: calcSubtotal(reclass.map(e => e.creditAmount)) - calcSubtotal(reclass.map(e => e.debitAmount)),
    }
  })

  function _calcBalance(items: M9AdjustmentEntry[]): M9BalanceStatus {
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
  function addEntry(type?: M9AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: M9AdjustmentEntry = {
      index: entries.value.length + 1,
      description: '',
      category: '',
      reportItem: '',
      accountName: '',
      noteItem: '',
      type: t,
      ociBlock: '',
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
    field: keyof M9AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: M9AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步M9-1 ─────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * - 借贷平衡校验通过才允许发布
   * - 通知 A13 审计调整汇总
   * - 双向同步 M9-1 审定表（M9-1 订阅该事件刷新 AJE/RJE 列）
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
        { itemId: `M9-3-entry-${n}-type`, data: { remark: entry.type } },
        { itemId: `M9-3-entry-${n}-desc`, data: { remark: entry.description || null } },
        { itemId: `M9-3-entry-${n}-category`, data: { remark: entry.category || null } },
        { itemId: `M9-3-entry-${n}-report`, data: { remark: entry.reportItem || null } },
        { itemId: `M9-3-entry-${n}-account`, data: { remark: entry.accountName || null } },
        { itemId: `M9-3-entry-${n}-note`, data: { remark: entry.noteItem || null } },
        { itemId: `M9-3-entry-${n}-ociBlock`, data: { remark: entry.ociBlock || null } },
        { itemId: `M9-3-entry-${n}-debit`, data: { remark: entry.debitAmount ? String(entry.debitAmount) : null } },
        { itemId: `M9-3-entry-${n}-credit`, data: { remark: entry.creditAmount ? String(entry.creditAmount) : null } },
        { itemId: `M9-3-entry-${n}-ref`, data: { remark: entry.refIndex || null } },
        { itemId: `M9-3-entry-${n}-remark`, data: { remark: entry.remark || null } },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish（双向同步M9-1 + 通知A13）
    eventBus.emit('adjustment:created', {
      wpCode: 'M9',
      accountCode: '4103',
      ajeNet: ajeNet4103.value,
      rjeNet: rjeNet4103.value,
      ajeNetByBlock: ajeNetByBlock.value,
      rjeNetByBlock: rjeNetByBlock.value,
      timestamp: Date.now(),
    } as any)
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    debouncedSave(`M9-3-entry-${n}-data`, {
      remark: JSON.stringify({
        index: entry.index,
        type: entry.type,
        description: entry.description,
        category: entry.category,
        reportItem: entry.reportItem,
        accountName: entry.accountName,
        noteItem: entry.noteItem,
        ociBlock: entry.ociBlock,
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
    ajeNet4103,
    rjeNet4103,
    ajeNetByBlock,
    rjeNetByBlock,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,
  }
}

export default useM9Adjustment
