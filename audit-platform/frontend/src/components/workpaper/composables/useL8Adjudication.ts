/**
 * useL8Adjudication — L8-1 审定表 composable（损益类！取发生额）
 *
 * Spec: .kiro/specs/l8-financial-expenses/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理10个费用项目行 + 合计行
 * - 列结构：项目 | 本期发生额(未审/AJE/RJE/审定) | 上期发生额 | 变动额 | 变动率
 * - 审定数公式：审定=未审+AJE+RJE
 * - 合计公式：=B7-B8-B9+B10-B11+B12+B13-B14-B15+B16
 *   （利息费用总额-利息资本化-利息收入+未确认融资费用-未实现融资收益+承兑贴息+汇兑损失-汇兑收益-汇兑资本化+手续费及其他）
 * - 审定数变化→writebackTB(6603发生额口径)+发布'substantive:adjudicated'
 * - 与L8-2明细表合计交叉验证
 *
 * 科目：6603 财务费用（**借方/损益类！**取发生额）
 */
import { computed, watch, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
  validateAdjudicationVsDetail,
  isChangeRateExceeding,
} from './useL8FormulaEngine'
import type { useL8FormData } from './useL8FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行数据（对应xlsx L8-1 row7~row16，10个费用明细项目） */
export interface L8AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 合计公式符号：+1或-1，控制该行在合计中的加减 */
  sign: 1 | -1
  /** 本期未审数（发生额） */
  currentUnadjusted: number
  /** 本期AJE */
  currentAje: number
  /** 本期RJE */
  currentRje: number
  /** 本期审定数（公式=未审+AJE+RJE） */
  currentAudited: number
  /** 上期发生额 */
  priorOccurrence: number
  /** 变动额（公式=本期审定-上期发生额） */
  changeAmount: number
  /** 变动率（公式=变动额/上期×100） */
  changeRate: number | 'N/A'
}

/** 合计行数据 */
export interface L8AdjudicationTotal {
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number
  priorOccurrence: number
  changeAmount: number
  changeRate: number | 'N/A'
}

// ─── Constants ───────────────────────────────────────────────────────────────

/**
 * L8-1 审定表10个费用项目行 + 合计公式符号
 *
 * 合计 = B7 - B8 - B9 + B10 - B11 + B12 + B13 - B14 - B15 + B16
 * 即：利息费用总额 - 利息资本化 - 利息收入 + 未确认融资费用
 *     - 未实现融资收益 + 承兑汇票贴息 + 汇兑损失 - 汇兑收益
 *     - 汇兑损益资本化 + 手续费及其他
 */
export const L8_ADJUDICATION_ITEMS: Array<{ key: string; itemName: string; sign: 1 | -1 }> = [
  { key: 'interestExpTotal', itemName: '利息费用总额', sign: 1 },
  { key: 'interestCapitalized', itemName: '减：利息资本化', sign: -1 },
  { key: 'interestIncome', itemName: '减：利息收入', sign: -1 },
  { key: 'unrecognizedFinCost', itemName: '未确认融资费用', sign: 1 },
  { key: 'unrealizedFinIncome', itemName: '减：未实现融资收益', sign: -1 },
  { key: 'bankAcceptDiscount', itemName: '承兑汇票贴息', sign: 1 },
  { key: 'fxLoss', itemName: '汇兑损失', sign: 1 },
  { key: 'fxGain', itemName: '减：汇兑收益', sign: -1 },
  { key: 'fxCapitalized', itemName: '减：汇兑损益资本化', sign: -1 },
  { key: 'feeAndOther', itemName: '手续费及其他', sign: 1 },
]

/** 变动率异常阈值（20%） */
const CHANGE_RATE_THRESHOLD = 20

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L8-1 审定表业务逻辑（损益类/发生额 + 10项目行 + 签名合计）
 *
 * @param formData 由调用方传入的 useL8FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useL8Adjudication(
  formData: ReturnType<typeof useL8FormData>,
  rows: { value: L8AdjudicationRow[] },
) {
  const { writebackTB, saveBatch, debouncedSave } = formData

  // ─── 1. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<L8AdjudicationRow[]> = computed(() => {
    return rows.value.map(row => {
      const currentAudited = calcAuditedAmount(row.currentUnadjusted, row.currentAje, row.currentRje)
      const changeAmount = calcChangeAmount(currentAudited, row.priorOccurrence)
      const changeRate = calcChangeRate(currentAudited, row.priorOccurrence)
      return {
        ...row,
        currentAudited,
        changeAmount,
        changeRate,
      }
    })
  })

  // ─── 2. 合计行（签名求和：+B7-B8-B9+B10-B11+B12+B13-B14-B15+B16） ────

  /** 合计行（对应xlsx合计行，按项目sign加减） */
  const totalRow: ComputedRef<L8AdjudicationTotal> = computed(() => {
    const r = computedRows.value
    let currentUnadjusted = 0
    let currentAje = 0
    let currentRje = 0
    let currentAudited = 0
    let priorOccurrence = 0

    for (const row of r) {
      currentUnadjusted += row.sign * row.currentUnadjusted
      currentAje += row.sign * row.currentAje
      currentRje += row.sign * row.currentRje
      currentAudited += row.sign * row.currentAudited
      priorOccurrence += row.sign * row.priorOccurrence
    }

    const changeAmount = calcChangeAmount(currentAudited, priorOccurrence)
    const changeRate = calcChangeRate(currentAudited, priorOccurrence)

    return {
      currentUnadjusted,
      currentAje,
      currentRje,
      currentAudited,
      priorOccurrence,
      changeAmount,
      changeRate,
    }
  })

  // ─── 3. 异常变动率行（高亮标记） ─────────────────────────────────────

  /** 变动率超阈值的行索引（供UI高亮） */
  const abnormalChangeRows: ComputedRef<number[]> = computed(() => {
    const indices: number[] = []
    computedRows.value.forEach((row, idx) => {
      if (isChangeRateExceeding(row.changeRate, CHANGE_RATE_THRESHOLD)) {
        indices.push(idx)
      }
    })
    return indices
  })

  // ─── 4. 交叉验证（审定表合计 vs 明细表合计） ──────────────────────────

  /**
   * 与L8-2明细表合计交叉验证
   * 需要外部传入 detailTotal（从 useL8CrossSheet.adjudicationVsDetail 获取）
   */
  function crossValidateWithDetail(detailTotal: number): { diff: number; isMatch: boolean } {
    return validateAdjudicationVsDetail(totalRow.value.currentAudited, detailTotal)
  }

  // ─── 5. 行操作 ────────────────────────────────────────────────────────

  /** 更新行某字段 */
  function updateRow(
    index: number,
    field: 'currentUnadjusted' | 'currentAje' | 'currentRje' | 'priorOccurrence',
    value: number,
  ): void {
    if (index < 0 || index >= rows.value.length) return
    const row = rows.value[index] as any
    row[field] = value

    // 重算公式列
    row.currentAudited = calcAuditedAmount(row.currentUnadjusted, row.currentAje, row.currentRje)
    row.changeAmount = calcChangeAmount(row.currentAudited, row.priorOccurrence)
    row.changeRate = calcChangeRate(row.currentAudited, row.priorOccurrence)

    _triggerSave(index)
  }

  // ─── 6. 保存 + TB回写 ─────────────────────────────────────────────────

  /**
   * 保存审定表并触发TB回写 + EventBus
   * - 回写 trial_balance 科目 6603（发生额口径！）
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      return [
        { itemId: `L8-1-row-${row.key}-unadj`, data: { remark: String(row.currentUnadjusted) } },
        { itemId: `L8-1-row-${row.key}-aje`, data: { remark: String(row.currentAje) } },
        { itemId: `L8-1-row-${row.key}-rje`, data: { remark: String(row.currentRje) } },
        { itemId: `L8-1-row-${row.key}-audited`, data: { remark: String(row.currentAudited) } },
        { itemId: `L8-1-row-${row.key}-prior`, data: { remark: String(row.priorOccurrence) } },
      ]
    }).flat()

    // 合计值（供 CrossSheet 勾稽读取）
    items.push({
      itemId: 'L8-1-total-audited',
      data: { remark: String(totalRow.value.currentAudited) },
    })

    await saveBatch(items)

    // TB回写（科目6603，发生额口径！）
    await writebackTB(totalRow.value.currentAudited)
  }

  // ─── 7. 审定数变化监听 → 自动回写 ────────────────────────────────────────

  watch(
    () => totalRow.value.currentAudited,
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
    debouncedSave(`L8-1-row-${row.key}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        sign: row.sign,
        currentUnadjusted: row.currentUnadjusted,
        currentAje: row.currentAje,
        currentRje: row.currentRje,
        priorOccurrence: row.priorOccurrence,
      }),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算行
    computedRows,
    // 合计行
    totalRow,
    // 异常行
    abnormalChangeRows,
    // 交叉验证
    crossValidateWithDetail,
    // 行操作
    updateRow,
    // 保存+回写
    saveAndWriteback,
    subscribeDisclosure,
  }
}

export default useL8Adjudication
