/**
 * useM7Adjudication — M7-1 审定表 composable
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理权益类单区块数据（专项储备4201）
 * - 行结构: 按类别分类(安全生产费/其他专项储备)+小计+合计行
 * - 列结构：项目 | 期初 | 贷方发生(计提) | 借方发生(使用) | 期末 | 未审 | AJE | RJE | 审定
 *           + 试算平衡表数 | 审定与试算差异 | 变动率
 * - 审定数公式：审定=未审+AJE+RJE（calcAuditedAmount）
 * - 权益类贷方期末：期末=期初+贷方-借方（calcEquityEndBalance）
 * - 小计：按类别分组 calcSubtotal
 * - 变动率: IF(AND(B=0,E=0),0, IF(B=0,1, E/B))
 * - 审定数变化→writebackTB(4201)+EventBus 'substantive:adjudicated'
 * - 与M7-2明细表交叉验证
 * - subscribe EventBus 'substantive:adjudicated' 刷新
 *
 * 科目：4201 专项储备（**贷方/权益类！期末=期初+贷方-借方**）
 * 安全生产费计提在贷方增加，费用化/资本化使用在借方减少
 *
 * 32×12结构，66公式
 */
import { computed, watch, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from './useM7FormulaEngine'
import type { useM7FormData } from './useM7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 行分类：安全生产费 / 维简费 / 其他专项储备 */
export type M7RowCategory = 'safety-production' | 'maintenance' | 'other'

/** 审定表行数据（32×12结构） */
export interface M7AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 行分类 */
  category: M7RowCategory
  /** 期初余额（B列，贷方余额） */
  beginning: number
  /** 贷方发生额-计提增加（C列：安全生产费等计提） */
  creditAmount: number
  /** 借方发生额-使用减少（D列：费用化+资本化支出） */
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
  /** 试算平衡表数（J列，来自TB取数） */
  tbBalance: number
  /** 审定与试算差异（K列=审定-试算） */
  tbDiff: number
  /** 变动率（L列） */
  changeRate: number
}

/** 合计行数据 */
export interface M7AdjudicationTotal {
  beginning: number
  creditAmount: number
  debitAmount: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  tbBalance: number
  tbDiff: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 变动率公式（源xlsx逻辑）:
 * IF(AND(B=0, E=0), 0, IF(B=0, 1, E/B))
 * 其中 B=期初, E=期末
 */
function calcChangeRate(beginning: number, endBalance: number): number {
  if (beginning === 0 && endBalance === 0) return 0
  if (beginning === 0 && endBalance > 0) return 1
  if (beginning === 0) return -1 // endBalance < 0
  return endBalance / beginning
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M7-1 审定表业务逻辑（权益类贷方+单区块+小计+TB回写）
 *
 * @param formData 由调用方传入的 useM7FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useM7Adjudication(
  formData: ReturnType<typeof useM7FormData>,
  rows: Ref<M7AdjudicationRow[]>,
) {
  const { writebackTB, saveBatch, debouncedSave } = formData

  // ─── 1. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M7AdjudicationRow[]> = computed(() => {
    return rows.value.map(row => {
      // 权益类贷方：期末=期初+贷方(计提)-借方(使用)
      const endBalance = calcEquityEndBalance(row.beginning, row.creditAmount, row.debitAmount)
      // 审定=未审+AJE+RJE
      const audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
      // 审定与试算差异
      const tbDiff = audited - row.tbBalance
      // 变动率
      const changeRate = calcChangeRate(row.beginning, endBalance)
      return { ...row, endBalance, audited, tbDiff, changeRate }
    })
  })

  // ─── 2. 分类小计 ──────────────────────────────────────────────────────

  /** 安全生产费小计 */
  const safetyProductionSubtotal: ComputedRef<M7AdjudicationTotal> = computed(() => {
    return _calcCategorySubtotal('safety-production')
  })

  /** 维简费小计 */
  const maintenanceSubtotal: ComputedRef<M7AdjudicationTotal> = computed(() => {
    return _calcCategorySubtotal('maintenance')
  })

  /** 其他专项储备小计 */
  const otherSubtotal: ComputedRef<M7AdjudicationTotal> = computed(() => {
    return _calcCategorySubtotal('other')
  })

  /** 合计行（全部行汇总） */
  const totalRow: ComputedRef<M7AdjudicationTotal> = computed(() => {
    const r = computedRows.value
    const beginning = calcSubtotal(r.map(x => x.beginning))
    const creditAmount = calcSubtotal(r.map(x => x.creditAmount))
    const debitAmount = calcSubtotal(r.map(x => x.debitAmount))
    const endBalance = calcEquityEndBalance(beginning, creditAmount, debitAmount)
    const unadjusted = calcSubtotal(r.map(x => x.unadjusted))
    const aje = calcSubtotal(r.map(x => x.aje))
    const rje = calcSubtotal(r.map(x => x.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const tbBalance = calcSubtotal(r.map(x => x.tbBalance))
    const tbDiff = audited - tbBalance
    return { beginning, creditAmount, debitAmount, endBalance, unadjusted, aje, rje, audited, tbBalance, tbDiff }
  })

  function _calcCategorySubtotal(category: M7RowCategory): M7AdjudicationTotal {
    const r = computedRows.value.filter(x => x.category === category)
    const beginning = calcSubtotal(r.map(x => x.beginning))
    const creditAmount = calcSubtotal(r.map(x => x.creditAmount))
    const debitAmount = calcSubtotal(r.map(x => x.debitAmount))
    const endBalance = calcEquityEndBalance(beginning, creditAmount, debitAmount)
    const unadjusted = calcSubtotal(r.map(x => x.unadjusted))
    const aje = calcSubtotal(r.map(x => x.aje))
    const rje = calcSubtotal(r.map(x => x.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const tbBalance = calcSubtotal(r.map(x => x.tbBalance))
    const tbDiff = audited - tbBalance
    return { beginning, creditAmount, debitAmount, endBalance, unadjusted, aje, rje, audited, tbBalance, tbDiff }
  }

  // ─── 3. 审定合计 + 变动率 ─────────────────────────────────────────────

  /** 审定合计金额（公开给 CrossSheet） */
  const adjudicatedTotal: ComputedRef<number> = computed(() => {
    return totalRow.value.audited
  })

  /** 总变动率 */
  const totalChangeRate: ComputedRef<number> = computed(() => {
    return calcChangeRate(totalRow.value.beginning, totalRow.value.endBalance)
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
  function addRow(itemName?: string, category?: M7RowCategory): void {
    const key = `m7-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const newRow: M7AdjudicationRow = {
      key,
      itemName: itemName || '',
      category: category || 'safety-production',
      beginning: 0,
      creditAmount: 0,
      debitAmount: 0,
      endBalance: 0,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      tbBalance: 0,
      tbDiff: 0,
      changeRate: 0,
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
    field: 'itemName' | 'category' | 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje' | 'tbBalance',
    value: string | number,
  ): void {
    if (index < 0 || index >= rows.value.length) return
    const row = rows.value[index] as any
    row[field] = value

    // 重算公式列
    row.endBalance = calcEquityEndBalance(row.beginning, row.creditAmount, row.debitAmount)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    row.tbDiff = row.audited - row.tbBalance
    row.changeRate = calcChangeRate(row.beginning, row.endBalance)

    _triggerSave(index)
  }

  // ─── 6. 保存 + TB回写 ─────────────────────────────────────────────────

  /**
   * 保存审定表并触发TB回写 + EventBus
   * - 回写 trial_balance 科目 4201（贷方/权益类！）
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `M7-1-row-${n}-name`, data: { remark: row.itemName } },
        { itemId: `M7-1-row-${n}-category`, data: { remark: row.category } },
        { itemId: `M7-1-row-${n}-audited`, data: { remark: String(row.audited) } },
        { itemId: `M7-1-row-${n}-endBalance`, data: { remark: String(row.endBalance) } },
      ]
    }).flat()

    // 分类小计（供 CrossSheet 勾稽）
    items.push(
      { itemId: 'M7-1-safety-subtotal', data: { remark: String(safetyProductionSubtotal.value.audited) } },
      { itemId: 'M7-1-maintenance-subtotal', data: { remark: String(maintenanceSubtotal.value.audited) } },
      { itemId: 'M7-1-other-subtotal', data: { remark: String(otherSubtotal.value.audited) } },
      { itemId: 'M7-1-total-audited', data: { remark: String(totalRow.value.audited) } },
    )

    await saveBatch(items)

    // TB回写（科目4201专项储备，贷方/权益类！）
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
   * 与M7-2明细表合计交叉验证
   * @param detailTotal 明细表合计（计提合计/使用合计/期末合计）
   */
  function crossValidateWithDetail(
    detailTotal: { creditTotal: number; debitTotal: number; endBalanceTotal: number },
  ): { creditDiff: number; debitDiff: number; endDiff: number; isMatch: boolean } {
    const creditDiff = totalRow.value.creditAmount - detailTotal.creditTotal
    const debitDiff = totalRow.value.debitAmount - detailTotal.debitTotal
    const endDiff = totalRow.value.endBalance - detailTotal.endBalanceTotal
    const isMatch = Math.abs(creditDiff) < 0.01 && Math.abs(debitDiff) < 0.01 && Math.abs(endDiff) < 0.01
    return { creditDiff, debitDiff, endDiff, isMatch }
  }

  // ─── 9. EventBus 订阅附注/adjudicated 刷新 ─────────────────────────────

  /** 订阅 'substantive:adjudicated' 事件刷新（其他sheet调整后同步） */
  function subscribeAdjudicated(callback: () => void): () => void {
    const handler = (payload: any) => {
      // 仅对非本组件发出的事件响应
      if (payload?.wpCode !== 'M7' || payload?.accountCode !== '4201') {
        callback()
      }
    }
    eventBus.on('substantive:adjudicated' as any, handler)
    return () => eventBus.off('substantive:adjudicated' as any, handler)
  }

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
    debouncedSave(`M7-1-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        category: row.category,
        beginning: row.beginning,
        creditAmount: row.creditAmount,
        debitAmount: row.debitAmount,
        unadjusted: row.unadjusted,
        aje: row.aje,
        rje: row.rje,
        tbBalance: row.tbBalance,
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
    // 分类小计
    safetyProductionSubtotal,
    maintenanceSubtotal,
    otherSubtotal,
    // 合计行
    totalRow,
    // 审定合计
    adjudicatedTotal,
    // 变动率
    totalChangeRate,
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
    subscribeAdjudicated,
    subscribeDisclosure,
  }
}

export default useM7Adjudication
