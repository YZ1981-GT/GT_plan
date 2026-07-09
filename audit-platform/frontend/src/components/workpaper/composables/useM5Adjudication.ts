/**
 * useM5Adjudication — M5-1 审定表 composable
 *
 * Spec: .kiro/specs/m5-surplus-reserve/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理双区块行：法定盈余公积 + 任意盈余公积 + 合计
 * - 行结构: 法定/任意/利润归还投资/其他 + 合计行(SUM) + 试算平衡表数行 + 差异行
 * - 列结构：项目 | 期初 | 贷方发生(计提) | 借方发生(转增/弥补) | 期末 | 未审 | AJE | RJE | 审定
 *           + 试算平衡表数 | 审定与试算差异 | 变动率
 * - 审定数公式：审定=未审+AJE+RJE（calcAuditedAmount）
 * - 权益类贷方期末：期末=期初+贷方-借方（calcEquityEndBalance）
 * - 小计：按区块(statutory/discretionary)分组 calcSubtotal
 * - 变动率: IF(AND(B=0,J=0),0, IF(AND(B=0,J>0),1, J/B))
 * - 审定数变化→writebackTB(4101)+EventBus 'substantive:adjudicated'
 * - 与M5-2明细表交叉验证
 *
 * 科目：4101 盈余公积（**贷方/权益类！期末=期初+贷方-借方**）
 * 法定盈余公积计提在贷方增加，转增资本/弥补亏损在借方减少
 *
 * 48×12结构，59公式
 */
import { computed, watch, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from './useM5FormulaEngine'
import type { useM5FormData } from './useM5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表区块类型：法定盈余公积 / 任意盈余公积 */
export type M5AdjudicationBlock = 'statutory' | 'discretionary'

/** 行分类：法定/任意/利润归还投资/其他 */
export type M5RowCategory = 'statutory' | 'discretionary' | 'profit-return' | 'other'

/** 审定表行数据（48×12结构） */
export interface M5AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 所属区块：statutory=法定盈余公积, discretionary=任意盈余公积 */
  block: M5AdjudicationBlock
  /** 行分类 */
  category: M5RowCategory
  /** 期初余额（B列，贷方余额） */
  beginning: number
  /** 贷方发生额-计提增加（C列：法定10%计提/任意计提） */
  creditAmount: number
  /** 借方发生额-减少（D列：转增资本/弥补亏损/利润归还投资） */
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
export interface M5AdjudicationTotal {
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
 * IF(AND(B=0, J=0), 0, IF(AND(B=0, J>0), 1, J/B))
 * 其中 B=期初, J=期末
 */
function calcChangeRate(beginning: number, endBalance: number): number {
  if (beginning === 0 && endBalance === 0) return 0
  if (beginning === 0 && endBalance > 0) return 1
  if (beginning === 0) return -1 // endBalance < 0
  return endBalance / beginning
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M5-1 审定表业务逻辑（权益类贷方+双区块+小计+TB回写）
 *
 * @param formData 由调用方传入的 useM5FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useM5Adjudication(
  formData: ReturnType<typeof useM5FormData>,
  rows: Ref<M5AdjudicationRow[]>,
) {
  const { writebackTB, saveBatch, debouncedSave } = formData

  // ─── 1. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M5AdjudicationRow[]> = computed(() => {
    return rows.value.map(row => {
      // 权益类贷方：期末=期初+贷方(计提)-借方(转增/弥补)
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

  // ─── 2. 双区块小计 ────────────────────────────────────────────────────

  /** 法定盈余公积区块小计 */
  const statutorySubtotal: ComputedRef<M5AdjudicationTotal> = computed(() => {
    return _calcBlockSubtotal('statutory')
  })

  /** 任意盈余公积区块小计 */
  const discretionarySubtotal: ComputedRef<M5AdjudicationTotal> = computed(() => {
    return _calcBlockSubtotal('discretionary')
  })

  /** 合计行（全部行汇总） */
  const totalRow: ComputedRef<M5AdjudicationTotal> = computed(() => {
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

  function _calcBlockSubtotal(block: M5AdjudicationBlock): M5AdjudicationTotal {
    const r = computedRows.value.filter(x => x.block === block)
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
  function addRow(itemName?: string, block?: M5AdjudicationBlock): void {
    const key = `m5-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const newRow: M5AdjudicationRow = {
      key,
      itemName: itemName || '',
      block: block || 'statutory',
      category: block === 'discretionary' ? 'discretionary' : 'statutory',
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
    field: 'itemName' | 'block' | 'category' | 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje' | 'tbBalance',
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
   * - 回写 trial_balance 科目 4101（贷方/权益类！）
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `M5-1-row-${n}-name`, data: { remark: row.itemName } },
        { itemId: `M5-1-row-${n}-block`, data: { remark: row.block } },
        { itemId: `M5-1-row-${n}-category`, data: { remark: row.category } },
        { itemId: `M5-1-row-${n}-audited`, data: { remark: String(row.audited) } },
        { itemId: `M5-1-row-${n}-endBalance`, data: { remark: String(row.endBalance) } },
      ]
    }).flat()

    // 区块小计（供 CrossSheet 勾稽）
    items.push(
      { itemId: 'M5-1-statutory-subtotal', data: { remark: String(statutorySubtotal.value.audited) } },
      { itemId: 'M5-1-discretionary-subtotal', data: { remark: String(discretionarySubtotal.value.audited) } },
      { itemId: 'M5-1-total-audited', data: { remark: String(totalRow.value.audited) } },
    )

    await saveBatch(items)

    // TB回写（科目4101盈余公积，贷方/权益类！）
    await writebackTB(totalRow.value.audited)

    // EventBus publish 'substantive:adjudicated'（通知附注组件刷新）
    eventBus.emit('substantive:adjudicated', {
      wpCode: 'M5',
      accountCode: '4101',
      audited: totalRow.value.audited,
      statutoryAudited: statutorySubtotal.value.audited,
      discretionaryAudited: discretionarySubtotal.value.audited,
      timestamp: Date.now(),
    } as any)

    // EventBus publish 'm5:surplus-accrual'（M5→M6: 盈余公积审定额→M6可供分配利润）
    eventBus.emit('m5:surplus-accrual' as any, {
      wpCode: 'M5',
      statutoryAccrual: statutorySubtotal.value.audited,
      discretionaryAccrual: discretionarySubtotal.value.audited,
      totalAccrual: totalRow.value.audited,
      timestamp: Date.now(),
    })
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
   * 与M5-2明细表合计交叉验证
   * @param detailStatutoryTotal 明细表法定盈余公积合计
   * @param detailDiscretionaryTotal 明细表任意盈余公积合计
   */
  function crossValidateWithDetail(
    detailStatutoryTotal: number,
    detailDiscretionaryTotal: number,
  ): { statutoryDiff: number; discretionaryDiff: number; isMatch: boolean } {
    const statutoryDiff = statutorySubtotal.value.audited - detailStatutoryTotal
    const discretionaryDiff = discretionarySubtotal.value.audited - detailDiscretionaryTotal
    const isMatch = Math.abs(statutoryDiff) < 0.01 && Math.abs(discretionaryDiff) < 0.01
    return { statutoryDiff, discretionaryDiff, isMatch }
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
    debouncedSave(`M5-1-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        block: row.block,
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
    // 区块小计
    statutorySubtotal,
    discretionarySubtotal,
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
    subscribeDisclosure,
  }
}

export default useM5Adjudication
