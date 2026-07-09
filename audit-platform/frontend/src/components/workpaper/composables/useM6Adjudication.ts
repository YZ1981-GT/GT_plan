/**
 * useM6Adjudication — M6-1 审定表 composable
 *
 * Spec: .kiro/specs/m6-retained-earnings/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理M6-1审定表数据（47×12，33公式）
 * - 单区块：利润分配-未分配利润（贷方/权益类！）
 * - 行结构: 期初未分配利润 | 本年净利润转入(贷方) | 提取盈余公积(借方) | 分配股利(借方) | 前期差错 | 合计
 * - 列结构：项目 | 期初 | 贷方发生(净利润转入) | 借方发生(分配) | 期末 | 未审 | AJE | RJE | 审定
 *           + 试算平衡表数 | 审定与试算差异 | 变动率
 * - 审定数公式：审定=未审+AJE+RJE（calcAuditedAmount）
 * - 权益类贷方期末：期末=期初+贷方-借方（calcEquityEndBalance）
 * - 审定数变化→writebackTB(4104)+EventBus 'substantive:adjudicated'
 * - 与M6-2明细表交叉验证（adjudicationVsDetail）
 *
 * 科目：4104 利润分配-未分配利润（**贷方/权益类！期末=期初+贷方-借方**）
 * 本年净利润转入在贷方增加，分配（提取盈余公积、宣告股利）在借方减少
 *
 * 47×12结构，33公式
 */
import { computed, watch, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from './useM6FormulaEngine'
import type { useM6FormData } from './useM6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行分类 */
export type M6AdjRowCategory =
  | 'beginning'         // 期初未分配利润
  | 'net-profit'        // 本年净利润转入（贷方增加）
  | 'surplus-accrual'   // 提取盈余公积（借方减少）
  | 'dividend'          // 分配股利（借方减少）
  | 'prior-error'       // 前期差错更正
  | 'policy-change'     // 会计政策变更
  | 'other'             // 其他

/** 审定表行数据（47×12结构） */
export interface M6AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 行分类 */
  category: M6AdjRowCategory
  /** 期初余额（B列，贷方余额） */
  beginning: number
  /** 贷方发生额-净利润转入等增加（C列） */
  creditAmount: number
  /** 借方发生额-分配等减少（D列） */
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
export interface M6AdjudicationTotal {
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
 * IF(AND(B=0, E=0), 0, IF(AND(B=0, E>0), 1, (E-B)/B))
 * 其中 B=期初, E=期末
 */
function calcChangeRate(beginning: number, endBalance: number): number {
  if (beginning === 0 && endBalance === 0) return 0
  if (beginning === 0 && endBalance > 0) return 1
  if (beginning === 0) return -1 // endBalance < 0
  return (endBalance - beginning) / beginning
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M6-1 审定表业务逻辑（权益类贷方单区块审定+TB回写4104）
 *
 * @param formData 由调用方传入的 useM6FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useM6Adjudication(
  formData: ReturnType<typeof useM6FormData>,
  rows: Ref<M6AdjudicationRow[]>,
) {
  const { writebackTB, saveBatch, debouncedSave } = formData

  // ─── 1. 计算属性：公式列自动计算（33公式） ────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M6AdjudicationRow[]> = computed(() => {
    return rows.value.map(row => {
      // 权益类贷方：期末=期初+贷方(净利润转入)-借方(分配)
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

  // ─── 2. 合计行 ────────────────────────────────────────────────────────

  /** 合计行（全部行汇总） */
  const totalRow: ComputedRef<M6AdjudicationTotal> = computed(() => {
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
  function addRow(itemName?: string, category?: M6AdjRowCategory): void {
    const key = `m6-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const newRow: M6AdjudicationRow = {
      key,
      itemName: itemName || '',
      category: category || 'other',
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
   * - 回写 trial_balance 科目 4104（贷方/权益类！）
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `M6-1-row-${n}-name`, data: { remark: row.itemName } },
        { itemId: `M6-1-row-${n}-category`, data: { remark: row.category } },
        { itemId: `M6-1-row-${n}-audited`, data: { remark: String(row.audited) } },
        { itemId: `M6-1-row-${n}-endBalance`, data: { remark: String(row.endBalance) } },
      ]
    }).flat()

    // 合计行
    items.push(
      { itemId: 'M6-1-total-audited', data: { remark: String(totalRow.value.audited) } },
      { itemId: 'M6-1-total-endBalance', data: { remark: String(totalRow.value.endBalance) } },
    )

    await saveBatch(items)

    // TB回写（科目4104利润分配-未分配利润，贷方/权益类！）
    await writebackTB(totalRow.value.audited)

    // EventBus publish 'substantive:adjudicated'（通知附注/检查表组件刷新）
    eventBus.emit('substantive:adjudicated', {
      wpCode: 'M6',
      accountCode: '4104',
      audited: totalRow.value.audited,
      endBalance: totalRow.value.endBalance,
      timestamp: Date.now(),
    } as any)
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

  // ─── 8. 与M6-2明细表交叉验证 ─────────────────────────────────────────

  /**
   * 与M6-2明细表期末交叉验证（adjudicationVsDetail）
   * M6-1审定表的期末 === M6-2明细结转后的期末未分配利润
   * @param detailRetainedEnd M6-2明细结转后期末未分配利润
   */
  function crossValidateWithDetail(
    detailRetainedEnd: number,
  ): { diff: number; isMatch: boolean } {
    const diff = totalRow.value.endBalance - detailRetainedEnd
    const isMatch = Math.abs(diff) < 0.01
    return { diff, isMatch }
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
    debouncedSave(`M6-1-row-${n}-data`, {
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

export default useM6Adjudication
