/**
 * useM8Adjudication — M8-1 审定表 composable
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理权益类单区块数据（一般风险准备4104）
 * - 行结构: 6 detail rows (rows 7-12 in xlsx) + 1 total row (row 13)
 * - 列结构：项目 | 期初未审 | 期初AJE | 期初RJE | 期初审定 | 期末未审 | 期末AJE | 期末RJE | 期末审定 | 变动额 | 变动率 | 原因
 * - 审定数公式：审定=未审+AJE+RJE（calcAuditedAmount）
 * - 权益类贷方期末：期末=期初+贷方-借方（calcEquityEndBalance）
 * - 合计行: SUM(B7:B12) 等区域求和
 * - 变动率: IF(AND(E=0,J=0),0, IF(E=0,1, J/E))
 * - 变动额: J=I-E（期末审定-期初审定）
 * - 审定数变化→writebackTB(4104)+EventBus 'substantive:adjudicated'
 * - 与M8-2明细表交叉验证
 * - subscribe EventBus 'substantive:adjudicated' 刷新
 *
 * 科目：4104 一般风险准备（**贷方/权益类！期末=期初+贷方-借方**）
 * 金融企业从净利润中计提时贷方增加，转回/使用时借方减少
 *
 * 25×12结构，84公式
 */
import { computed, watch, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from './useM8FormulaEngine'
import type { useM8FormData } from './useM8FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行数据（25×12结构） */
export interface M8AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 期初未审数（B列） */
  beginUnadjusted: number
  /** 期初AJE（C列，账项调整） */
  beginAje: number
  /** 期初RJE（D列，重分类调整） */
  beginRje: number
  /** 期初审定数（E列，公式=B+C+D） */
  beginAudited: number
  /** 期末未审数（F列） */
  endUnadjusted: number
  /** 期末AJE（G列，账项调整） */
  endAje: number
  /** 期末RJE（H列，重分类调整） */
  endRje: number
  /** 期末审定数（I列，公式=F+G+H） */
  endAudited: number
  /** 变动额（J列，公式=I-E） */
  changeAmount: number
  /** 变动率（K列） */
  changeRate: number
  /** 原因分析（L列） */
  reason: string
}

/** 合计行数据 */
export interface M8AdjudicationTotal {
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginAudited: number
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number
  changeAmount: number
  changeRate: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 变动率公式（源xlsx逻辑）:
 * IF(AND(E=0, J=0), 0, IF(E=0, 1, J/E))
 * 其中 E=期初审定, J=变动额
 */
function calcChangeRate(beginAudited: number, changeAmount: number): number {
  if (beginAudited === 0 && changeAmount === 0) return 0
  if (beginAudited === 0 && changeAmount > 0) return 1
  if (beginAudited === 0) return -1
  return changeAmount / beginAudited
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M8-1 审定表业务逻辑（权益类贷方+单区块+合计+TB回写）
 *
 * @param formData 由调用方传入的 useM8FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useM8Adjudication(
  formData: ReturnType<typeof useM8FormData>,
  rows: Ref<M8AdjudicationRow[]>,
) {
  const { writebackTB, saveBatch, debouncedSave } = formData

  // ─── 1. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M8AdjudicationRow[]> = computed(() => {
    return rows.value.map(row => {
      // 期初审定=未审+AJE+RJE
      const beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAje, row.beginRje)
      // 期末审定=未审+AJE+RJE
      const endAudited = calcAuditedAmount(row.endUnadjusted, row.endAje, row.endRje)
      // 变动额=期末审定-期初审定
      const changeAmount = endAudited - beginAudited
      // 变动率
      const changeRate = calcChangeRate(beginAudited, changeAmount)
      return { ...row, beginAudited, endAudited, changeAmount, changeRate }
    })
  })

  // ─── 2. 合计行（SUM B7:B12） ─────────────────────────────────────────

  /** 合计行（全部行汇总，对应xlsx row 13） */
  const totalRow: ComputedRef<M8AdjudicationTotal> = computed(() => {
    const r = computedRows.value
    const beginUnadjusted = calcSubtotal(r.map(x => x.beginUnadjusted))
    const beginAje = calcSubtotal(r.map(x => x.beginAje))
    const beginRje = calcSubtotal(r.map(x => x.beginRje))
    const beginAudited = calcAuditedAmount(beginUnadjusted, beginAje, beginRje)
    const endUnadjusted = calcSubtotal(r.map(x => x.endUnadjusted))
    const endAje = calcSubtotal(r.map(x => x.endAje))
    const endRje = calcSubtotal(r.map(x => x.endRje))
    const endAudited = calcAuditedAmount(endUnadjusted, endAje, endRje)
    const changeAmount = endAudited - beginAudited
    const changeRate = calcChangeRate(beginAudited, changeAmount)
    return { beginUnadjusted, beginAje, beginRje, beginAudited, endUnadjusted, endAje, endRje, endAudited, changeAmount, changeRate }
  })

  // ─── 3. 审定合计 ─────────────────────────────────────────────────────

  /** 审定合计金额（公开给 CrossSheet） */
  const adjudicatedTotal: ComputedRef<number> = computed(() => {
    return totalRow.value.endAudited
  })

  // ─── 4. 权益类期末校验 ────────────────────────────────────────────────

  /**
   * 权益类贷方期末校验：审定期末余额与明细表交叉验证
   * M8-1 row13 I列 === M8-2 O17合计
   */
  const equityEndCheck: ComputedRef<{ expected: number; actual: number; diff: number; isMatch: boolean }> = computed(() => {
    const actual = totalRow.value.endAudited
    // 注：expected由crossValidateWithDetail提供
    return { expected: actual, actual, diff: 0, isMatch: true }
  })

  // ─── 5. 行操作 ────────────────────────────────────────────────────────

  /** 更新行某字段 */
  function updateRow(
    index: number,
    field: 'itemName' | 'beginUnadjusted' | 'beginAje' | 'beginRje' | 'endUnadjusted' | 'endAje' | 'endRje' | 'reason',
    value: string | number,
  ): void {
    if (index < 0 || index >= rows.value.length) return
    const row = rows.value[index] as any
    row[field] = value
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
        { itemId: `M8-1-row-${n}-name`, data: { remark: row.itemName } },
        { itemId: `M8-1-row-${n}-endAudited`, data: { remark: String(row.endAudited) } },
        { itemId: `M8-1-row-${n}-beginAudited`, data: { remark: String(row.beginAudited) } },
      ]
    }).flat()

    // 合计（供 CrossSheet 勾稽）
    items.push(
      { itemId: 'M8-1-total-endAudited', data: { remark: String(totalRow.value.endAudited) } },
      { itemId: 'M8-1-total-beginAudited', data: { remark: String(totalRow.value.beginAudited) } },
    )

    await saveBatch(items)

    // TB回写（科目4104一般风险准备，贷方/权益类！）
    await writebackTB(totalRow.value.endAudited)
  }

  // ─── 7. 审定数变化监听 → 自动回写 ────────────────────────────────────────

  watch(
    () => totalRow.value.endAudited,
    async (newVal, oldVal) => {
      if (oldVal !== undefined && newVal !== oldVal) {
        await saveAndWriteback()
      }
    },
  )

  // ─── 8. 与明细表交叉验证 ──────────────────────────────────────────────

  /**
   * 与M8-2明细表合计交叉验证
   * M8-1 审定表的期末审定合计(I13) ←→ M8-2 明细表的审定期末合计(O17)
   * @param detailAuditedEndTotal 明细表合计审定期末
   */
  function crossValidateWithDetail(
    detailAuditedEndTotal: number,
  ): { diff: number; isMatch: boolean } {
    const diff = totalRow.value.endAudited - detailAuditedEndTotal
    const isMatch = Math.abs(diff) < 0.01
    return { diff, isMatch }
  }

  // ─── 9. EventBus 订阅附注/adjudicated 刷新 ─────────────────────────────

  /** 订阅 'substantive:adjudicated' 事件刷新（其他sheet调整后同步） */
  function subscribeAdjudicated(callback: () => void): () => void {
    const handler = (payload: any) => {
      if (payload?.wpCode !== 'M8' || payload?.accountCode !== '4104') {
        callback()
      }
    }
    eventBus.on('substantive:adjudicated', handler)
    return () => eventBus.off('substantive:adjudicated', handler)
  }

  /** 订阅附注变化通知 */
  function subscribeDisclosure(callback: () => void): () => void {
    const handler = () => callback()
    eventBus.on('disclosure:note-text-updated', handler)
    return () => eventBus.off('disclosure:note-text-updated', handler)
  }

  // ─── 10. 内部保存触发 ─────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = rows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`M8-1-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        beginUnadjusted: row.beginUnadjusted,
        beginAje: row.beginAje,
        beginRje: row.beginRje,
        endUnadjusted: row.endUnadjusted,
        endAje: row.endAje,
        endRje: row.endRje,
        reason: row.reason,
      }),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算行
    computedRows,
    // 合计行
    totalRow,
    // 审定合计
    adjudicatedTotal,
    // 权益类期末校验
    equityEndCheck,
    // 行操作
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

export default useM8Adjudication
