/**
 * useM4Adjudication — M4-1 审定表 composable
 *
 * Spec: .kiro/specs/m4-capital-reserve/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理双区块行：资本溢价(股本溢价) + 其他资本公积 + 合计
 * - 列结构：项目 | 期初 | 贷方发生(增加) | 借方发生(减少) | 期末 | 未审 | AJE | RJE | 审定
 * - 审定数公式：审定=未审+AJE+RJE（calcAuditedAmount）
 * - 权益类贷方期末：期末=期初+贷方-借方（calcEquityEndBalance）
 * - 小计：按区块(premium/other)分组 calcSubtotal
 * - 审定数变化→writebackTB(4002)+EventBus 'substantive:adjudicated'
 * - 与M4-2明细表交叉验证
 *
 * 科目：4002 资本公积（**贷方/权益类！期末=期初+贷方-借方**）
 * 资本溢价在贷方增加（出资超面值），借方减少（转增资本/弥补亏损）
 */
import { computed, watch, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from './useM4FormulaEngine'
import type { useM4FormData } from './useM4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表区块类型 */
export type M4AdjudicationBlock = 'premium' | 'other'

/** 审定表行数据（44×12结构，41公式） */
export interface M4AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 所属区块：premium=资本溢价/股本溢价, other=其他资本公积 */
  block: M4AdjudicationBlock
  /** 期初余额（B列，贷方余额） */
  beginning: number
  /** 贷方发生额-增加（C列：资本溢价增加/股份支付确认等） */
  creditAmount: number
  /** 借方发生额-减少（D列：转增资本/弥补亏损等） */
  debitAmount: number
  /** 期末余额（E列，公式=期初+贷方-借方，权益类！） */
  endBalance: number
  /** 未审数（F列） */
  unadjusted: number
  /** AJE（G列） */
  aje: number
  /** RJE（H列） */
  rje: number
  /** 审定数（I列，公式=未审+AJE+RJE） */
  audited: number
}

/** 合计行数据 */
export interface M4AdjudicationTotal {
  beginning: number
  creditAmount: number
  debitAmount: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

/** 审定表变动率 */
export interface M4PeriodChange {
  /** 本期变动金额（期末-期初） */
  changeAmount: number
  /** 变动率 */
  changeRate: number | null
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M4-1 审定表业务逻辑（权益类贷方+双区块+小计+TB回写）
 *
 * @param formData 由调用方传入的 useM4FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useM4Adjudication(
  formData: ReturnType<typeof useM4FormData>,
  rows: Ref<M4AdjudicationRow[]>,
) {
  const { writebackTB, saveBatch, debouncedSave } = formData

  // ─── 1. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M4AdjudicationRow[]> = computed(() => {
    return rows.value.map(row => {
      // 权益类贷方：期末=期初+贷方(增加)-借方(减少)
      const endBalance = calcEquityEndBalance(row.beginning, row.creditAmount, row.debitAmount)
      // 审定=未审+AJE+RJE
      const audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
      return { ...row, endBalance, audited }
    })
  })

  // ─── 2. 双区块小计 ────────────────────────────────────────────────────

  /** 资本溢价(股本溢价)区块小计 */
  const premiumSubtotal: ComputedRef<M4AdjudicationTotal> = computed(() => {
    return _calcBlockSubtotal('premium')
  })

  /** 其他资本公积区块小计 */
  const otherSubtotal: ComputedRef<M4AdjudicationTotal> = computed(() => {
    return _calcBlockSubtotal('other')
  })

  /** 合计行（全部行汇总） */
  const totalRow: ComputedRef<M4AdjudicationTotal> = computed(() => {
    const r = computedRows.value
    const beginning = calcSubtotal(r.map(x => x.beginning))
    const creditAmount = calcSubtotal(r.map(x => x.creditAmount))
    const debitAmount = calcSubtotal(r.map(x => x.debitAmount))
    const endBalance = calcEquityEndBalance(beginning, creditAmount, debitAmount)
    const unadjusted = calcSubtotal(r.map(x => x.unadjusted))
    const aje = calcSubtotal(r.map(x => x.aje))
    const rje = calcSubtotal(r.map(x => x.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    return { beginning, creditAmount, debitAmount, endBalance, unadjusted, aje, rje, audited }
  })

  function _calcBlockSubtotal(block: M4AdjudicationBlock): M4AdjudicationTotal {
    const r = computedRows.value.filter(x => x.block === block)
    const beginning = calcSubtotal(r.map(x => x.beginning))
    const creditAmount = calcSubtotal(r.map(x => x.creditAmount))
    const debitAmount = calcSubtotal(r.map(x => x.debitAmount))
    const endBalance = calcEquityEndBalance(beginning, creditAmount, debitAmount)
    const unadjusted = calcSubtotal(r.map(x => x.unadjusted))
    const aje = calcSubtotal(r.map(x => x.aje))
    const rje = calcSubtotal(r.map(x => x.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    return { beginning, creditAmount, debitAmount, endBalance, unadjusted, aje, rje, audited }
  }

  // ─── 3. 审定合计 + 本期变动 + 变动率 ──────────────────────────────────

  /** 审定合计金额（公开给 CrossSheet） */
  const adjudicatedTotal: ComputedRef<number> = computed(() => {
    return totalRow.value.audited
  })

  /** 本期变动 + 变动率 */
  const periodChange: ComputedRef<M4PeriodChange> = computed(() => {
    const total = totalRow.value
    const changeAmount = total.endBalance - total.beginning
    const changeRate = total.beginning !== 0
      ? changeAmount / total.beginning
      : null
    return { changeAmount, changeRate }
  })

  // ─── 4. 权益类期末校验 ────────────────────────────────────────────────

  /**
   * 权益类贷方期末校验：审定期末 === 期初+贷方-借方
   */
  const equityEndCheck: ComputedRef<{ expected: number; actual: number; diff: number; isMatch: boolean }> = computed(() => {
    const total = totalRow.value
    const expected = calcEquityEndBalance(total.beginning, total.creditAmount, total.debitAmount)
    const actual = total.endBalance
    const diff = actual - expected
    return { expected, actual, diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── 5. 行操作 ────────────────────────────────────────────────────────

  /** 新增行 */
  function addRow(itemName?: string, block?: M4AdjudicationBlock): void {
    const key = `m4-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const newRow: M4AdjudicationRow = {
      key,
      itemName: itemName || '',
      block: block || 'premium',
      beginning: 0,
      creditAmount: 0,
      debitAmount: 0,
      endBalance: 0,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
    }
    rows.value.push(newRow)
  }

  /** 删除行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
    _triggerSaveAll()
  }

  /** 更新行某字段 */
  function updateRow(
    index: number,
    field: 'itemName' | 'block' | 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje',
    value: string | number,
  ): void {
    if (index < 0 || index >= rows.value.length) return
    const row = rows.value[index] as any
    row[field] = value

    // 重算公式列
    row.endBalance = calcEquityEndBalance(row.beginning, row.creditAmount, row.debitAmount)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)

    _triggerSave(index)
  }

  // ─── 6. 保存 + TB回写 ─────────────────────────────────────────────────

  /**
   * 保存审定表并触发TB回写 + EventBus
   * - 回写 trial_balance 科目 4002（贷方/权益类！）
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `M4-1-row-${n}-name`, data: { remark: row.itemName } },
        { itemId: `M4-1-row-${n}-block`, data: { remark: row.block } },
        { itemId: `M4-1-row-${n}-audited`, data: { remark: String(row.audited) } },
        { itemId: `M4-1-row-${n}-endBalance`, data: { remark: String(row.endBalance) } },
      ]
    }).flat()

    // 区块小计（供 CrossSheet 勾稽）
    items.push(
      { itemId: 'M4-1-premium-subtotal', data: { remark: String(premiumSubtotal.value.audited) } },
      { itemId: 'M4-1-other-subtotal', data: { remark: String(otherSubtotal.value.audited) } },
      { itemId: 'M4-1-total-audited', data: { remark: String(totalRow.value.audited) } },
    )

    await saveBatch(items)

    // TB回写（科目4002资本公积，贷方/权益类！）
    await writebackTB(totalRow.value.audited)
  }

  // ─── 7. 审定数变化监听 → 自动回写 ────────────────────────────────────────

  watch(
    () => totalRow.value.audited,
    async (newVal, oldVal) => {
      if (oldVal !== undefined && newVal !== oldVal) {
        await saveAndWriteback()
      }
    },
  )

  // ─── 8. 与明细表交叉验证 ──────────────────────────────────────────────

  /**
   * 与M4-2明细表合计交叉验证
   * @param detailPremiumTotal 明细表资本溢价合计
   * @param detailOtherTotal 明细表其他资本公积合计
   */
  function crossValidateWithDetail(
    detailPremiumTotal: number,
    detailOtherTotal: number,
  ): { premiumDiff: number; otherDiff: number; isMatch: boolean } {
    const premiumDiff = premiumSubtotal.value.audited - detailPremiumTotal
    const otherDiff = otherSubtotal.value.audited - detailOtherTotal
    const isMatch = Math.abs(premiumDiff) < 0.01 && Math.abs(otherDiff) < 0.01
    return { premiumDiff, otherDiff, isMatch }
  }

  // ─── 9. EventBus 订阅附注刷新 ────────────────────────────────────────────

  /** 订阅附注变化通知 */
  function subscribeDisclosure(callback: () => void): () => void {
    const handler = () => callback()
    eventBus.on('disclosure:note-text-updated' as any, handler)
    return () => eventBus.off('disclosure:note-text-updated' as any, handler)
  }

  // ─── 10. 内部保存触发 ─────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = rows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`M4-1-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        block: row.block,
        beginning: row.beginning,
        creditAmount: row.creditAmount,
        debitAmount: row.debitAmount,
        unadjusted: row.unadjusted,
        aje: row.aje,
        rje: row.rje,
      }),
    })
  }

  function _triggerSaveAll(): void {
    rows.value.forEach((_, i) => _triggerSave(i))
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算行
    computedRows,
    // 区块小计
    premiumSubtotal,
    otherSubtotal,
    // 合计行
    totalRow,
    // 审定合计
    adjudicatedTotal,
    // 本期变动
    periodChange,
    // 权益类期末校验
    equityEndCheck,
    // 行操作
    addRow,
    removeRow,
    updateRow,
    // 保存+回写
    saveAndWriteback,
    // 交叉验证
    crossValidateWithDetail,
    // EventBus
    subscribeDisclosure,
  }
}

export default useM4Adjudication
