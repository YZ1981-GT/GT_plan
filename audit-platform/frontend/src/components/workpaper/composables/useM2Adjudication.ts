/**
 * useM2Adjudication — M2-1 审定表 composable
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理按出资人/股东分类的行（动态行，每行=一个出资人）+ 小计行
 * - 列结构（xlsx 49×12）：
 *   项目(A) | 期初(未审B/AJE_C/RJE_D/审定E) | 期末(未审F/AJE_G/RJE_H/审定I) | 变动额J | 变动率K | 备注L
 * - 审定数公式：审定=未审+AJE+RJE（calcAuditedAmount）
 * - 权益类期末校验：calcEquityEndBalance(期初+贷方-借方)
 * - 审定数变化→writebackTB(4001)+EventBus 'substantive:adjudicated'
 * - subscribe附注EventBus刷新
 *
 * 科目：4001 实收资本/股本（贷方/权益类！期末=期初+贷方-借方）
 * 增资在贷方增加，减资在借方减少
 */
import { computed, watch, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
  calcVarianceAmount,
  calcVarianceRate,
} from './useM2FormulaEngine'
import type { useM2FormData } from './useM2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行数据（按出资人/股东分类，对应xlsx M2-1 row7~rowN） */
export interface M2AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 出资人/股东名称（A列） */
  investorName: string
  /** 期初未审数（B列） */
  beginUnadjusted: number
  /** 期初AJE（C列） */
  beginAje: number
  /** 期初RJE（D列） */
  beginRje: number
  /** 期初审定数（E列，公式=B+C+D） */
  beginAudited: number
  /** 贷方发生额-增资（F列） */
  creditAmount: number
  /** 借方发生额-减资（G列） */
  debitAmount: number
  /** 期末未审数（H列） */
  endUnadjusted: number
  /** 期末AJE（I列） */
  endAje: number
  /** 期末RJE（J列） */
  endRje: number
  /** 期末审定数（K列，公式=H+I+J） */
  endAudited: number
  /** 变动额（L列，公式=K-E） */
  varianceAmount: number
  /** 变动率（M列） */
  varianceRate: number
}

/** 合计行数据 */
export interface M2AdjudicationTotal {
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginAudited: number
  creditAmount: number
  debitAmount: number
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number
  varianceAmount: number
  varianceRate: number
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M2-1 审定表业务逻辑（权益类贷方+按出资人分类+小计+TB回写）
 *
 * @param formData 由调用方传入的 useM2FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useM2Adjudication(
  formData: ReturnType<typeof useM2FormData>,
  rows: Ref<M2AdjudicationRow[]>,
) {
  const { writebackTB, saveBatch, debouncedSave } = formData

  // ─── 1. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M2AdjudicationRow[]> = computed(() => {
    return rows.value.map(row => {
      const beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAje, row.beginRje)
      const endAudited = calcAuditedAmount(row.endUnadjusted, row.endAje, row.endRje)
      const varianceAmount = calcVarianceAmount(endAudited, beginAudited)
      const varianceRate = calcVarianceRate(beginAudited, varianceAmount)
      return {
        ...row,
        beginAudited,
        endAudited,
        varianceAmount,
        varianceRate,
      }
    })
  })

  // ─── 2. 合计行 ────────────────────────────────────────────────────────

  /** 合计行（xlsx SUM公式行） */
  const totalRow: ComputedRef<M2AdjudicationTotal> = computed(() => {
    const r = computedRows.value
    const beginUnadjusted = calcSubtotal(r.map(x => x.beginUnadjusted))
    const beginAje = calcSubtotal(r.map(x => x.beginAje))
    const beginRje = calcSubtotal(r.map(x => x.beginRje))
    const beginAudited = calcSubtotal(r.map(x => x.beginAudited))
    const creditAmount = calcSubtotal(r.map(x => x.creditAmount))
    const debitAmount = calcSubtotal(r.map(x => x.debitAmount))
    const endUnadjusted = calcSubtotal(r.map(x => x.endUnadjusted))
    const endAje = calcSubtotal(r.map(x => x.endAje))
    const endRje = calcSubtotal(r.map(x => x.endRje))
    const endAudited = calcSubtotal(r.map(x => x.endAudited))
    const varianceAmount = calcVarianceAmount(endAudited, beginAudited)
    const varianceRate = calcVarianceRate(beginAudited, varianceAmount)
    return {
      beginUnadjusted,
      beginAje,
      beginRje,
      beginAudited,
      creditAmount,
      debitAmount,
      endUnadjusted,
      endAje,
      endRje,
      endAudited,
      varianceAmount,
      varianceRate,
    }
  })

  // ─── 3. 权益类期末校验 ────────────────────────────────────────────────

  /**
   * 权益类期末校验：期末审定 是否=期初审定+贷方(增资)-借方(减资)
   * 此为辅助校验值，供UI展示"校验通过/差异"
   */
  const equityEndBalanceCheck: ComputedRef<{ expected: number; actual: number; diff: number; isMatch: boolean }> = computed(() => {
    const total = totalRow.value
    // 权益类校验：期末=期初+贷方增资-借方减资
    const expected = calcEquityEndBalance(total.beginAudited, total.creditAmount, total.debitAmount)
    const actual = total.endAudited
    const diff = actual - expected
    return { expected, actual, diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── 4. 行操作 ────────────────────────────────────────────────────────

  /** 新增出资人行 */
  function addRow(investorName?: string): void {
    const key = `m2-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const newRow: M2AdjudicationRow = {
      key,
      investorName: investorName || '',
      beginUnadjusted: 0,
      beginAje: 0,
      beginRje: 0,
      beginAudited: 0,
      creditAmount: 0,
      debitAmount: 0,
      endUnadjusted: 0,
      endAje: 0,
      endRje: 0,
      endAudited: 0,
      varianceAmount: 0,
      varianceRate: 0,
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
    field: 'investorName' | 'beginUnadjusted' | 'beginAje' | 'beginRje' | 'creditAmount' | 'debitAmount' | 'endUnadjusted' | 'endAje' | 'endRje',
    value: string | number,
  ): void {
    if (index < 0 || index >= rows.value.length) return
    const row = rows.value[index] as any
    row[field] = value

    // 重算公式列
    row.beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAje, row.beginRje)
    row.endAudited = calcAuditedAmount(row.endUnadjusted, row.endAje, row.endRje)
    row.varianceAmount = calcVarianceAmount(row.endAudited, row.beginAudited)
    row.varianceRate = calcVarianceRate(row.beginAudited, row.varianceAmount)

    _triggerSave(index)
  }

  // ─── 5. 保存 + TB回写 ─────────────────────────────────────────────────

  /**
   * 保存审定表并触发TB回写 + EventBus
   * - 回写 trial_balance 科目 4001
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `M2-M2-1-row-${n}-name`, data: { remark: row.investorName } },
        { itemId: `M2-M2-1-row-${n}-beginAudited`, data: { remark: String(row.beginAudited) } },
        { itemId: `M2-M2-1-row-${n}-endAudited`, data: { remark: String(row.endAudited) } },
      ]
    }).flat()

    // 合计值（供 CrossSheet 勾稽）
    items.push({
      itemId: 'M2-M2-1-total-audited',
      data: { remark: String(totalRow.value.endAudited) },
    })

    await saveBatch(items)

    // TB回写（科目4001实收资本/股本）
    await writebackTB(totalRow.value.endAudited)
  }

  // ─── 6. 审定数变化监听 → 自动回写 ────────────────────────────────────────

  watch(
    () => totalRow.value.endAudited,
    async (newVal, oldVal) => {
      if (oldVal !== undefined && newVal !== oldVal) {
        await saveAndWriteback()
      }
    },
  )

  // ─── 7. EventBus 订阅附注刷新 ────────────────────────────────────────────

  /** 订阅附注变化通知 */
  function subscribeDisclosure(callback: () => void): () => void {
    const handler = () => callback()
    eventBus.on('disclosure:note-text-updated' as any, handler)
    return () => eventBus.off('disclosure:note-text-updated' as any, handler)
  }

  // ─── 8. 内部保存触发 ──────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = rows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`M2-M2-1-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        investorName: row.investorName,
        beginUnadjusted: row.beginUnadjusted,
        beginAje: row.beginAje,
        beginRje: row.beginRje,
        creditAmount: row.creditAmount,
        debitAmount: row.debitAmount,
        endUnadjusted: row.endUnadjusted,
        endAje: row.endAje,
        endRje: row.endRje,
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
    // 权益类校验
    equityEndBalanceCheck,
    // 行操作
    addRow,
    removeRow,
    updateRow,
    // 保存+回写
    saveAndWriteback,
    subscribeDisclosure,
  }
}

export default useM2Adjudication
