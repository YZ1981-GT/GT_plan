/**
 * useM9Adjudication — M9-1 审定表 composable
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理双区块行：以后不能重分类进损益的OCI + 以后能重分类进损益的OCI
 * - 行结构:
 *   不可重分类：其他权益工具投资公允变动(G8)、设定受益计划重计量(J2)
 *   可重分类：其他债权投资公允变动、现金流量套期损益、外币财务报表折算差额
 * - 列结构：项目 | 期初 | 贷方发生(OCI增加) | 借方发生(减少/重分类) | 期末 | 未审 | AJE | RJE | 审定
 *           + 试算平衡表数 | 审定与试算差异 | 变动率
 * - 审定数公式：审定=未审+AJE+RJE（calcAuditedAmount）
 * - 权益类贷方期末：期末=期初+贷方-借方（calcEquityEndBalance）
 * - 双区块小计：按nonReclass/reclass分组 calcSubtotal
 * - 变动率: IF(AND(B=0,E=0),0, IF(B=0,1, E/B))
 * - 审定数变化→writebackTB(4103)+EventBus 'substantive:adjudicated'
 * - 与M9-2明细合计交叉验证
 * - subscribe EventBus 'disclosure:note-text-updated' 刷新
 *
 * 科目：4103 其他综合收益（**贷方/权益类！期末=期初+贷方-借方**）
 * OCI增加在贷方增加，OCI减少/重分类进损益在借方减少
 *
 * 47×12结构，41公式
 */
import { computed, watch, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from './useM9FormulaEngine'
import type { useM9FormData } from './useM9FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表区块类型：以后不能重分类进损益 / 以后能重分类进损益 */
export type M9AdjudicationBlock = 'nonReclass' | 'reclass'

/** 行分类（OCI来源） */
export type M9RowCategory =
  | 'equity-instrument-fair-value'   // 其他权益工具投资公允变动(G8)
  | 'defined-benefit-remeasure'      // 设定受益计划重计量(J2)
  | 'debt-instrument-fair-value'     // 其他债权投资公允变动
  | 'cashflow-hedge'                 // 现金流量套期损益
  | 'foreign-currency-translation'   // 外币财务报表折算差额
  | 'other'                          // 其他

/** 审定表行数据（47×12结构） */
export interface M9AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 所属区块：nonReclass=不可重分类, reclass=可重分类 */
  block: M9AdjudicationBlock
  /** 行分类（OCI来源） */
  category: M9RowCategory
  /** 期初余额（B列，贷方余额） */
  beginning: number
  /** 贷方发生额-OCI增加（C列：公允变动/重计量等） */
  creditAmount: number
  /** 借方发生额-OCI减少/重分类（D列：处置转出/重分类进损益） */
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
export interface M9AdjudicationTotal {
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
 * M9-1 审定表业务逻辑（权益类贷方+双区块+小计+TB回写）
 *
 * @param formData 由调用方传入的 useM9FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useM9Adjudication(
  formData: ReturnType<typeof useM9FormData>,
  rows: Ref<M9AdjudicationRow[]>,
) {
  const { writebackTB, saveBatch, debouncedSave } = formData

  // ─── 1. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M9AdjudicationRow[]> = computed(() => {
    return rows.value.map(row => {
      // 权益类贷方：期末=期初+贷方(OCI增加)-借方(OCI减少/重分类)
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

  /** 以后不能重分类进损益区块小计（G8公允变动+J2重计量） */
  const nonReclassSubtotal: ComputedRef<M9AdjudicationTotal> = computed(() => {
    return _calcBlockSubtotal('nonReclass')
  })

  /** 以后能重分类进损益区块小计（其他债权+套期+外币折算） */
  const reclassSubtotal: ComputedRef<M9AdjudicationTotal> = computed(() => {
    return _calcBlockSubtotal('reclass')
  })

  /** 合计行（全部行汇总） */
  const totalRow: ComputedRef<M9AdjudicationTotal> = computed(() => {
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

  function _calcBlockSubtotal(block: M9AdjudicationBlock): M9AdjudicationTotal {
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
  function addRow(itemName?: string, block?: M9AdjudicationBlock, category?: M9RowCategory): void {
    const key = `m9-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const resolvedBlock = block || 'nonReclass'
    const newRow: M9AdjudicationRow = {
      key,
      itemName: itemName || '',
      block: resolvedBlock,
      category: category || (resolvedBlock === 'nonReclass' ? 'equity-instrument-fair-value' : 'debt-instrument-fair-value'),
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
   * - 回写 trial_balance 科目 4103（贷方/权益类！）
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `M9-1-row-${n}-name`, data: { remark: row.itemName } },
        { itemId: `M9-1-row-${n}-block`, data: { remark: row.block } },
        { itemId: `M9-1-row-${n}-category`, data: { remark: row.category } },
        { itemId: `M9-1-row-${n}-audited`, data: { remark: String(row.audited) } },
        { itemId: `M9-1-row-${n}-endBalance`, data: { remark: String(row.endBalance) } },
      ]
    }).flat()

    // 区块小计（供 CrossSheet 勾稽）
    items.push(
      { itemId: 'M9-1-nonReclass-subtotal', data: { remark: String(nonReclassSubtotal.value.audited) } },
      { itemId: 'M9-1-reclass-subtotal', data: { remark: String(reclassSubtotal.value.audited) } },
      { itemId: 'M9-1-total-audited', data: { remark: String(totalRow.value.audited) } },
    )

    await saveBatch(items)

    // TB回写（科目4103其他综合收益，贷方/权益类！）
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

  // ─── 8. 与明细表M9-2交叉验证 ──────────────────────────────────────────

  /**
   * 与M9-2明细表合计交叉验证
   * @param detailNonReclassTotal 明细表不可重分类合计
   * @param detailReclassTotal 明细表可重分类合计
   */
  function crossValidateWithDetail(
    detailNonReclassTotal: number,
    detailReclassTotal: number,
  ): { nonReclassDiff: number; reclassDiff: number; isMatch: boolean } {
    const nonReclassDiff = nonReclassSubtotal.value.audited - detailNonReclassTotal
    const reclassDiff = reclassSubtotal.value.audited - detailReclassTotal
    const isMatch = Math.abs(nonReclassDiff) < 0.01 && Math.abs(reclassDiff) < 0.01
    return { nonReclassDiff, reclassDiff, isMatch }
  }

  // ─── 9. EventBus 订阅附注刷新 ────────────────────────────────────────────

  /** 订阅附注变化通知 */
  function subscribeDisclosure(callback: () => void): () => void {
    const handler = () => callback()
    eventBus.on('disclosure:note-text-updated' as any, handler)
    return () => eventBus.off('disclosure:note-text-updated' as any, handler)
  }

  /** 订阅 'substantive:adjudicated' 事件刷新（其他sheet调整后同步） */
  function subscribeAdjudicated(callback: () => void): () => void {
    const handler = (payload: any) => {
      // 仅对非本组件发出的事件响应
      if (payload?.wpCode !== 'M9' || payload?.accountCode !== '4103') {
        callback()
      }
    }
    eventBus.on('substantive:adjudicated' as any, handler)
    return () => eventBus.off('substantive:adjudicated' as any, handler)
  }

  // ─── 10. 内部保存触发 ─────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = rows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`M9-1-row-${n}-data`, {
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
    nonReclassSubtotal,
    reclassSubtotal,
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
    subscribeAdjudicated,
  }
}

export default useM9Adjudication
