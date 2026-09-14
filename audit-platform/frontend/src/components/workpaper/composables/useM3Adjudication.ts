/**
 * useM3Adjudication — M3-1 审定表 composable
 *
 * Spec: .kiro/specs/m3-treasury-stock/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理按回购批次分类的行（33×12结构）+ 小计行
 * - 列结构：项目 | 期初 | 借方发生(回购) | 贷方发生(注销/再售) | 期末 | 未审 | AJE | RJE | 审定
 * - 审定数公式：审定=未审+AJE+RJE（calcAuditedAmount）
 * - 权益备抵类期末：期末=期初+借方-贷方（calcContraEquityEndBalance）
 * - 小计：按回购批次分组 calcSubtotal
 * - 审定数变化→writebackTB(4002)+EventBus 'substantive:adjudicated'
 *
 * 科目：4002 库存股（**借方/权益备抵类！期末=期初+借方-贷方**）
 * 回购股份在借方增加库存股，注销/再售在贷方减少库存股（与其他M权益类方向相反！）
 */
import { computed, watch, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcContraEquityEndBalance,
  calcSubtotal,
} from './useM3FormulaEngine'
import type { useM3FormData } from './useM3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行数据（按回购批次分类，33行×12列） */
export interface M3AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 项目/回购批次名（A列） */
  batchName: string
  /** 期初余额（B列，借方余额） */
  beginning: number
  /** 借方发生额-回购增加（C列） */
  debitAmount: number
  /** 贷方发生额-注销/再售减少（D列） */
  creditAmount: number
  /** 期末余额（E列，公式=期初+借方-贷方，借方余额） */
  endBalance: number
  /** 未审数（F列） */
  unadjusted: number
  /** AJE（G列） */
  aje: number
  /** RJE（H列） */
  rje: number
  /** 审定数（I列，公式=未审+AJE+RJE） */
  audited: number
  /** 所属分类（回购批次分组键） */
  category: string
}

/** 合计行数据 */
export interface M3AdjudicationTotal {
  beginning: number
  debitAmount: number
  creditAmount: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M3-1 审定表业务逻辑（权益备抵借方+按回购批次分类+小计+TB回写）
 *
 * @param formData 由调用方传入的 useM3FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useM3Adjudication(
  formData: ReturnType<typeof useM3FormData>,
  rows: Ref<M3AdjudicationRow[]>,
) {
  const { writebackTB, saveBatch, debouncedSave } = formData

  // ─── 1. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M3AdjudicationRow[]> = computed(() => {
    return rows.value.map(row => {
      // 权益备抵借方：期末=期初+借方(回购)-贷方(注销/再售)
      const endBalance = calcContraEquityEndBalance(row.beginning, row.debitAmount, row.creditAmount)
      // 审定=未审+AJE+RJE
      const audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
      return { ...row, endBalance, audited }
    })
  })

  // ─── 2. 合计行 ────────────────────────────────────────────────────────

  /** 合计行 */
  const totalRow: ComputedRef<M3AdjudicationTotal> = computed(() => {
    const r = computedRows.value
    const beginning = calcSubtotal(r.map(x => x.beginning))
    const debitAmount = calcSubtotal(r.map(x => x.debitAmount))
    const creditAmount = calcSubtotal(r.map(x => x.creditAmount))
    const endBalance = calcContraEquityEndBalance(beginning, debitAmount, creditAmount)
    const unadjusted = calcSubtotal(r.map(x => x.unadjusted))
    const aje = calcSubtotal(r.map(x => x.aje))
    const rje = calcSubtotal(r.map(x => x.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    return { beginning, debitAmount, creditAmount, endBalance, unadjusted, aje, rje, audited }
  })

  // ─── 3. 分类小计（按回购批次 category 分组） ──────────────────────────

  /** 分类小计 Map<category, subtotalRow> */
  const categorySubtotals: ComputedRef<Map<string, M3AdjudicationTotal>> = computed(() => {
    const map = new Map<string, M3AdjudicationTotal>()
    const groups = new Map<string, M3AdjudicationRow[]>()

    for (const row of computedRows.value) {
      const cat = row.category || '未分类'
      if (!groups.has(cat)) groups.set(cat, [])
      groups.get(cat)!.push(row)
    }

    for (const [cat, catRows] of groups.entries()) {
      const beginning = calcSubtotal(catRows.map(x => x.beginning))
      const debitAmount = calcSubtotal(catRows.map(x => x.debitAmount))
      const creditAmount = calcSubtotal(catRows.map(x => x.creditAmount))
      const endBalance = calcContraEquityEndBalance(beginning, debitAmount, creditAmount)
      const unadjusted = calcSubtotal(catRows.map(x => x.unadjusted))
      const aje = calcSubtotal(catRows.map(x => x.aje))
      const rje = calcSubtotal(catRows.map(x => x.rje))
      const audited = calcAuditedAmount(unadjusted, aje, rje)
      map.set(cat, { beginning, debitAmount, creditAmount, endBalance, unadjusted, aje, rje, audited })
    }

    return map
  })

  // ─── 4. 权益备抵期末校验 ──────────────────────────────────────────────

  /**
   * 权益备抵类期末校验：期末审定 是否= 期初+借方-贷方（方向正确性）
   */
  const contraEquityCheck: ComputedRef<{ expected: number; actual: number; diff: number; isMatch: boolean }> = computed(() => {
    const total = totalRow.value
    // 权益备抵借方校验：期末=期初+借方(回购)-贷方(注销/再售)
    const expected = calcContraEquityEndBalance(total.beginning, total.debitAmount, total.creditAmount)
    const actual = total.endBalance
    const diff = actual - expected
    return { expected, actual, diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── 5. 行操作 ────────────────────────────────────────────────────────

  /** 新增行 */
  function addRow(batchName?: string, category?: string): void {
    const key = `m3-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const newRow: M3AdjudicationRow = {
      key,
      batchName: batchName || '',
      beginning: 0,
      debitAmount: 0,
      creditAmount: 0,
      endBalance: 0,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      category: category || '',
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
    field: 'batchName' | 'beginning' | 'debitAmount' | 'creditAmount' | 'unadjusted' | 'aje' | 'rje' | 'category',
    value: string | number,
  ): void {
    if (index < 0 || index >= rows.value.length) return
    const row = rows.value[index] as any
    row[field] = value

    // 重算公式列
    row.endBalance = calcContraEquityEndBalance(row.beginning, row.debitAmount, row.creditAmount)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)

    _triggerSave(index)
  }

  // ─── 6. 保存 + TB回写 ─────────────────────────────────────────────────

  /**
   * 保存审定表并触发TB回写 + EventBus
   * - 回写 trial_balance 科目 4002（借方/权益备抵）
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `M3-M3-1-row-${n}-name`, data: { remark: row.batchName } },
        { itemId: `M3-M3-1-row-${n}-audited`, data: { remark: String(row.audited) } },
        { itemId: `M3-M3-1-row-${n}-endBalance`, data: { remark: String(row.endBalance) } },
      ]
    }).flat()

    // 合计值（供 CrossSheet 勾稽）
    items.push({
      itemId: 'M3-M3-1-total-audited',
      data: { remark: String(totalRow.value.audited) },
    })

    await saveBatch(items)

    // TB回写（科目4002库存股，借方/权益备抵类！）
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

  // ─── 8. EventBus 订阅附注刷新 ────────────────────────────────────────────

  /** 订阅附注变化通知 */
  function subscribeDisclosure(callback: () => void): () => void {
    const handler = () => callback()
    eventBus.on('disclosure:note-text-updated' as any, handler)
    return () => eventBus.off('disclosure:note-text-updated' as any, handler)
  }

  // ─── 9. 内部保存触发 ──────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = rows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`M3-M3-1-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        batchName: row.batchName,
        beginning: row.beginning,
        debitAmount: row.debitAmount,
        creditAmount: row.creditAmount,
        unadjusted: row.unadjusted,
        aje: row.aje,
        rje: row.rje,
        category: row.category,
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
    // 合计行
    totalRow,
    // 分类小计
    categorySubtotals,
    // 权益备抵校验
    contraEquityCheck,
    // 行操作
    addRow,
    removeRow,
    updateRow,
    // 保存+回写
    saveAndWriteback,
    subscribeDisclosure,
  }
}

export default useM3Adjudication
