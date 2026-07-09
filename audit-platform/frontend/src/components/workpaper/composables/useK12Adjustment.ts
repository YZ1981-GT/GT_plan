/**
 * useK12Adjustment — K12-3 调整分录 composable
 *
 * Spec: .kiro/specs/k12-non-operating-income/
 * Task: 6.2
 * Requirements: 6.2
 *
 * 职责：
 * - AJE/RJE 行管理（新增/删除/更新）
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created' → A13 错报汇总表
 * - 双向同步 K12-1 审定表（K12-1 订阅该事件刷新 AJE/RJE 列）
 *
 * 科目：6301 营业外收入（贷方/损益类）
 * ⚠️ 贷方科目：贷方增加=调增营业外收入，借方减少=冲减营业外收入
 *
 * 事件流：
 *   K12-3 save → emit 'adjustment:created' {entryType, accountCode:'6301', amount, wpCode:'K12'}
 *   → A13 拾取 K12-3 调整
 *   → K12-1 recalc（subscribe 'adjustment:created'）→ writebackTB → substantive:adjudicated → disclosure
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useK12FormulaEngine'
import type { useK12FormData } from './useK12FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type K12AdjustmentType = 'AJE' | 'RJE'

/** 调整分录行 */
export interface K12AdjustmentEntry {
  /** 序号 */
  index: number
  /** AJE or RJE */
  type: K12AdjustmentType
  /** 摘要/调整事项说明 */
  description: string
  /** 科目编码 */
  accountCode: string
  /** 科目名称 */
  accountName: string
  /** 借方金额 */
  debitAmount: number
  /** 贷方金额 */
  creditAmount: number
  /** 索引号 */
  refIndex: string
  /** 备注 */
  remark: string
}

/** 借贷平衡状态 */
export interface K12BalanceStatus {
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
/** 科目编码 */
const ACCOUNT_CODE = '6301'
/** 底稿编码 */
const WP_CODE = 'K12'
/** item_id 前缀 */
const ITEM_PREFIX = 'K12-3'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * K12-3 调整分录业务逻辑
 *
 * @param formData 由调用方传入的 useK12FormData 实例
 */
export function useK12Adjustment(formData: ReturnType<typeof useK12FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<K12AdjustmentEntry[]>([])
  const activeType = ref<K12AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型（AJE/RJE）的分录 */
  const filteredEntries: ComputedRef<K12AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<K12AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<K12AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<K12BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<K12BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<K12BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /**
   * AJE 对科目6301的净影响
   * ⚠️ 6301是贷方科目：贷方增加=调增营业外收入，借方减少=冲减
   * 净影响 = 贷方 - 借方（正数=调增收入）
   */
  const ajeNet6301: ComputedRef<number> = computed(() => {
    const aje6301 = ajeEntries.value.filter(e => e.accountCode === ACCOUNT_CODE)
    const credit = calcSubtotal(aje6301.map(e => e.creditAmount))
    const debit = calcSubtotal(aje6301.map(e => e.debitAmount))
    return credit - debit // 贷方科目：贷-借
  })

  /**
   * RJE 对科目6301的净影响
   * 净影响 = 贷方 - 借方（正数=调增收入）
   */
  const rjeNet6301: ComputedRef<number> = computed(() => {
    const rje6301 = rjeEntries.value.filter(e => e.accountCode === ACCOUNT_CODE)
    const credit = calcSubtotal(rje6301.map(e => e.creditAmount))
    const debit = calcSubtotal(rje6301.map(e => e.debitAmount))
    return credit - debit // 贷方科目：贷-借
  })

  function _calcBalance(items: K12AdjustmentEntry[]): K12BalanceStatus {
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
  function addEntry(type?: K12AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: K12AdjustmentEntry = {
      index: entries.value.length + 1,
      type: t,
      description: '',
      accountCode: '',
      accountName: '',
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
    field: keyof K12AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: K12AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步K12-1 ────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   *
   * 校验：借贷平衡（Σ借方===Σ贷方）通过后才允许保存+发布。
   *
   * 事件效果：
   * - 通知 A13 审计调整汇总拾取 K12-3 的 AJE/RJE
   * - 双向同步 K12-1 审定表（K12-1 订阅该事件刷新 AJE/RJE 列）
   *
   * EventPayload 契约：
   *   {
   *     entryType: 'AJE' | 'RJE',
   *     accountCode: '6301',
   *     amount: number (AJE/RJE净影响金额),
   *     wpCode: 'K12',
   *     ajeNet: number,
   *     rjeNet: number,
   *     timestamp: number
   *   }
   */
  async function saveAndPublish(): Promise<void> {
    // 校验借贷平衡
    const balance = currentBalance.value
    if (!balance.isBalanced) {
      return // 不平衡时不允许发布
    }

    // 批量保存到 checklist_responses
    const items = entries.value.map((entry, i) => {
      const n = i + 1
      return [
        { itemId: `${ITEM_PREFIX}-entry-${n}-type`, value: entry.type },
        { itemId: `${ITEM_PREFIX}-entry-${n}-desc`, value: entry.description || null },
        { itemId: `${ITEM_PREFIX}-entry-${n}-code`, value: entry.accountCode || null },
        { itemId: `${ITEM_PREFIX}-entry-${n}-name`, value: entry.accountName || null },
        { itemId: `${ITEM_PREFIX}-entry-${n}-debit`, value: entry.debitAmount ? String(entry.debitAmount) : null },
        { itemId: `${ITEM_PREFIX}-entry-${n}-credit`, value: entry.creditAmount ? String(entry.creditAmount) : null },
        { itemId: `${ITEM_PREFIX}-entry-${n}-ref`, value: entry.refIndex || null },
        { itemId: `${ITEM_PREFIX}-entry-${n}-remark`, value: entry.remark || null },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish 'adjustment:created'
    // ⚠️ 此事件触发两个下游：
    //   1. A13 错报汇总表拾取 K12-3 调整（通过 accountCode + wpCode 匹配）
    //   2. K12-1 订阅后刷新 AJE/RJE 列 → recalc → writebackTB → substantive:adjudicated → disclosure
    eventBus.emit('adjustment:created', {
      entryType: activeType.value,
      accountCode: ACCOUNT_CODE,
      amount: activeType.value === 'AJE' ? ajeNet6301.value : rjeNet6301.value,
      wpCode: WP_CODE,
      ajeNet: ajeNet6301.value,
      rjeNet: rjeNet6301.value,
      timestamp: Date.now(),
    })
  }

  // ─── 5. 恢复已保存分录 ────────────────────────────────────────────────

  /**
   * 从 checklist_responses 恢复已保存的分录行
   * item_id 格式: K12-3-entry-{n}-{field}
   */
  function restoreEntries(): void {
    const prefix = `${ITEM_PREFIX}-entry-`
    let maxIdx = 0

    for (const [key] of formData.allResponses.value.entries()) {
      if (key.startsWith(prefix) && key.endsWith('-type')) {
        const match = key.match(/K12-3-entry-(\d+)-type/)
        if (match) {
          const n = parseInt(match[1])
          if (n > maxIdx) maxIdx = n
        }
      }
    }

    if (maxIdx === 0) return

    const getVal = (itemId: string): string => {
      const item = formData.allResponses.value.get(itemId)
      return item?.remark ?? ''
    }

    for (let i = 1; i <= maxIdx; i++) {
      const typeVal = getVal(`${prefix}${i}-type`)
      if (!typeVal) continue // 跳过无效条目

      entries.value.push({
        index: i,
        type: (typeVal === 'RJE' ? 'RJE' : 'AJE') as K12AdjustmentType,
        description: getVal(`${prefix}${i}-desc`),
        accountCode: getVal(`${prefix}${i}-code`),
        accountName: getVal(`${prefix}${i}-name`),
        debitAmount: Number(getVal(`${prefix}${i}-debit`)) || 0,
        creditAmount: Number(getVal(`${prefix}${i}-credit`)) || 0,
        refIndex: getVal(`${prefix}${i}-ref`),
        remark: getVal(`${prefix}${i}-remark`),
      })
    }
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    const pairs: [string, string | null][] = [
      [`${ITEM_PREFIX}-entry-${n}-type`, entry.type],
      [`${ITEM_PREFIX}-entry-${n}-desc`, entry.description || null],
      [`${ITEM_PREFIX}-entry-${n}-code`, entry.accountCode || null],
      [`${ITEM_PREFIX}-entry-${n}-name`, entry.accountName || null],
      [`${ITEM_PREFIX}-entry-${n}-debit`, entry.debitAmount ? String(entry.debitAmount) : null],
      [`${ITEM_PREFIX}-entry-${n}-credit`, entry.creditAmount ? String(entry.creditAmount) : null],
      [`${ITEM_PREFIX}-entry-${n}-ref`, entry.refIndex || null],
      [`${ITEM_PREFIX}-entry-${n}-remark`, entry.remark || null],
    ]
    for (const [itemId, remark] of pairs) {
      debouncedSave(itemId, { item_id: itemId, conclusion: null, remark })
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
    ajeNet6301,
    rjeNet6301,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,

    // 恢复
    restoreEntries,
  }
}

export default useK12Adjustment
