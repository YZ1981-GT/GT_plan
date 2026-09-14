/**
 * useM10Adjudication — M10-1 审定表 composable
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理三组行：永续债/优先股/其他权益工具 × N行 + 各组小计 + 合计行
 * - 列结构：项目 | 期初 | 贷方发生(发行) | 借方发生(赎回/转换) | 期末 | 未审 | AJE | RJE | 审定
 *           + 试算平衡表数 | 差异 | 变动率
 * - 审定数公式：审定=未审+AJE+RJE（calcAuditedAmount）
 * - 权益类贷方期末：期末=期初+贷方-借方（calcEquityEndBalance）
 * - 小计：按组(perpetualBond/preferredStock/other)分组 calcSubtotal
 * - 审定数变化→writebackTB(4003)+EventBus 'substantive:adjudicated'
 * - 与M10-2明细表交叉验证
 *
 * 科目：4003 其他权益工具（**贷方/权益类！期末=期初+贷方-借方**）
 * 永续债/优先股发行在贷方增加，赎回/转换在借方减少
 *
 * 38×14结构，29公式
 */
import { computed, watch, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from './useM10FormulaEngine'
import type { useM10FormData } from './useM10FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表工具分组：永续债/优先股/其他权益工具 */
export type M10InstrumentGroup = 'perpetualBond' | 'preferredStock' | 'other'

/** 审定表行数据（38×14结构） */
export interface M10AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 所属分组 */
  group: M10InstrumentGroup
  /** 期初余额（B列，贷方余额） */
  beginning: number
  /** 贷方发生额-发行增加（C列：永续债/优先股发行） */
  creditAmount: number
  /** 借方发生额-赎回/转换减少（D列） */
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
  changeRate: number | null
}

/** 分组小计/合计行数据 */
export interface M10AdjudicationTotal {
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

/** 分组标签 */
export const M10_INSTRUMENT_GROUPS = [
  { key: 'perpetualBond' as const, label: '永续债' },
  { key: 'preferredStock' as const, label: '优先股' },
  { key: 'other' as const, label: '其他权益工具' },
] as const

/**
 * 变动率公式（源xlsx逻辑）:
 * IF(AND(B=0, E=0), null, IF(B=0, 1, (E-B)/B))
 */
function calcChangeRate(beginning: number, endBalance: number): number | null {
  if (beginning === 0 && endBalance === 0) return null
  if (beginning === 0) return 1
  return (endBalance - beginning) / beginning
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M10-1 审定表业务逻辑（权益类贷方+三组+小计+TB回写）
 *
 * @param formData 由调用方传入的 useM10FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useM10Adjudication(
  formData: ReturnType<typeof useM10FormData>,
  rows: Ref<M10AdjudicationRow[]>,
) {
  const { writebackTB, saveBatch, debouncedSave } = formData

  // ─── 1. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M10AdjudicationRow[]> = computed(() => {
    return rows.value.map(row => {
      // 权益类贷方：期末=期初+贷方(发行)-借方(赎回/转换)
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

  // ─── 2. 三组小计 ──────────────────────────────────────────────────────

  /** 永续债组小计 */
  const perpetualBondSubtotal: ComputedRef<M10AdjudicationTotal> = computed(() => {
    return _calcGroupSubtotal('perpetualBond')
  })

  /** 优先股组小计 */
  const preferredStockSubtotal: ComputedRef<M10AdjudicationTotal> = computed(() => {
    return _calcGroupSubtotal('preferredStock')
  })

  /** 其他权益工具组小计 */
  const otherSubtotal: ComputedRef<M10AdjudicationTotal> = computed(() => {
    return _calcGroupSubtotal('other')
  })

  /** 合计行（全部行汇总） */
  const totalRow: ComputedRef<M10AdjudicationTotal> = computed(() => {
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

  function _calcGroupSubtotal(group: M10InstrumentGroup): M10AdjudicationTotal {
    const r = computedRows.value.filter(x => x.group === group)
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

  // ─── 3. 审定合计 ──────────────────────────────────────────────────────

  /** 审定合计金额（公开给 CrossSheet） */
  const adjudicatedTotal: ComputedRef<number> = computed(() => {
    return totalRow.value.audited
  })

  /** 总变动率 */
  const totalChangeRate: ComputedRef<number | null> = computed(() => {
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
  function addRow(itemName?: string, group?: M10InstrumentGroup): void {
    const key = `m10-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const newRow: M10AdjudicationRow = {
      key,
      itemName: itemName || '',
      group: group || 'perpetualBond',
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
      changeRate: null,
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
    field: 'itemName' | 'group' | 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje' | 'tbBalance',
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
   * - 回写 trial_balance 科目 4003（贷方/权益类！）
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `M10-1-row-${n}-name`, data: { remark: row.itemName } },
        { itemId: `M10-1-row-${n}-group`, data: { remark: row.group } },
        { itemId: `M10-1-row-${n}-audited`, data: { remark: String(row.audited) } },
        { itemId: `M10-1-row-${n}-endBalance`, data: { remark: String(row.endBalance) } },
      ]
    }).flat()

    // 分组小计（供 CrossSheet 勾稽）
    items.push(
      { itemId: 'M10-1-perpetualBond-subtotal', data: { remark: String(perpetualBondSubtotal.value.audited) } },
      { itemId: 'M10-1-preferredStock-subtotal', data: { remark: String(preferredStockSubtotal.value.audited) } },
      { itemId: 'M10-1-other-subtotal', data: { remark: String(otherSubtotal.value.audited) } },
      { itemId: 'M10-1-total-audited', data: { remark: String(totalRow.value.audited) } },
    )

    await saveBatch(items)

    // TB回写（科目4003其他权益工具，贷方/权益类！）
    await writebackTB(totalRow.value.audited)

    // EventBus publish 'substantive:adjudicated'（通知附注组件刷新）
    eventBus.emit('substantive:adjudicated', {
      wpCode: 'M10',
      accountCode: '4003',
      audited: totalRow.value.audited,
      perpetualBondAudited: perpetualBondSubtotal.value.audited,
      preferredStockAudited: preferredStockSubtotal.value.audited,
      otherAudited: otherSubtotal.value.audited,
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

  // ─── 8. 与明细表交叉验证 ──────────────────────────────────────────────

  /**
   * 与M10-2明细表合计交叉验证
   * @param detailTotal 明细表合计金额
   */
  function crossValidateWithDetail(
    detailTotal: number,
  ): { diff: number; isMatch: boolean } {
    const diff = totalRow.value.audited - detailTotal
    const isMatch = Math.abs(diff) < 0.01
    return { diff, isMatch }
  }

  /**
   * 按分组交叉验证（明细表分组合计 vs 审定表分组小计）
   */
  function crossValidateByGroup(
    detailPerpetualBond: number,
    detailPreferredStock: number,
    detailOther: number,
  ): { perpetualBondDiff: number; preferredStockDiff: number; otherDiff: number; isMatch: boolean } {
    const perpetualBondDiff = perpetualBondSubtotal.value.audited - detailPerpetualBond
    const preferredStockDiff = preferredStockSubtotal.value.audited - detailPreferredStock
    const otherDiff = otherSubtotal.value.audited - detailOther
    const isMatch = Math.abs(perpetualBondDiff) < 0.01 && Math.abs(preferredStockDiff) < 0.01 && Math.abs(otherDiff) < 0.01
    return { perpetualBondDiff, preferredStockDiff, otherDiff, isMatch }
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
    debouncedSave(`M10-1-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        group: row.group,
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
    // 分组小计
    perpetualBondSubtotal,
    preferredStockSubtotal,
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
    crossValidateByGroup,
    // EventBus
    subscribeDisclosure,
  }
}

export default useM10Adjudication
