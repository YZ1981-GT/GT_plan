/**
 * useG5Adjudication — G5-1 审定表逻辑 (87行五层分组)
 *
 * 五层：一、原值 / 二、坏账准备 / 三、净值 / 四、一年内到期 / 五、报表列示数
 * 公式：借方余额/审定数/净值/报表数/变动率
 * EventBus: publish substantive:adjudicated(1531)
 */
import { ref, computed, watch } from 'vue'
import {
  parseNum, calcDebitBalance, calcAdjustedAmount,
  calcNetValue, calcReportAmount, calcChangeRate,
} from '@/composables/useG5FormulaEngine'

export type GroupType = 'gross' | 'provision' | 'net' | 'oneYear' | 'report'

export interface AdjudicationRow {
  id: string
  item: string
  category: string
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number
  closingUnadjusted: number
  closingAJE: number
  closingRJE: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
  reasonAnalysis: string
}

export interface AdjudicationGroup {
  groupName: string
  groupType: GroupType
  expanded: boolean
  rows: AdjudicationRow[]
}

export function useG5Adjudication(opts: {
  wpId: any
  projectId: any
  htmlData: any
  isReadonly: any
}) {
  const groups = ref<AdjudicationGroup[]>([
    { groupName: '一、长期应收款原值', groupType: 'gross', expanded: true, rows: [] },
    { groupName: '二、坏账准备', groupType: 'provision', expanded: true, rows: [] },
    { groupName: '三、长期应收款净值', groupType: 'net', expanded: true, rows: [] },
    { groupName: '四、减：一年内到期非流动资产', groupType: 'oneYear', expanded: true, rows: [] },
    { groupName: '五、长期应收款报表列示数', groupType: 'report', expanded: true, rows: [] },
  ])

  const tbValues = ref<{ opening: number; closing: number }>({ opening: 0, closing: 0 })
  const variance = computed(() => {
    const reportGroup = groups.value.find(g => g.groupType === 'report')
    if (!reportGroup || reportGroup.rows.length === 0) return 0
    const adjusted = reportGroup.rows[0]?.closingAdjusted ?? 0
    return adjusted - tbValues.value.closing
  })

  function recalcRow(row: AdjudicationRow) {
    row.openingAdjusted = calcAdjustedAmount(row.openingUnadjusted, row.openingAJE, row.openingRJE)
    row.closingAdjusted = calcAdjustedAmount(row.closingUnadjusted, row.closingAJE, row.closingRJE)
    row.changeAmount = row.closingAdjusted - row.openingAdjusted
    row.changeRate = calcChangeRate(row.openingAdjusted, row.closingAdjusted)
  }

  function recalcDerived() {
    const grossTotal = groups.value.find(g => g.groupType === 'gross')
      ?.rows.reduce((s, r) => s + r.closingAdjusted, 0) ?? 0
    const provTotal = groups.value.find(g => g.groupType === 'provision')
      ?.rows.reduce((s, r) => s + r.closingAdjusted, 0) ?? 0
    // 三、净值 = 原值 - 坏账
    const netGroup = groups.value.find(g => g.groupType === 'net')
    if (netGroup && netGroup.rows.length > 0) {
      netGroup.rows[0].closingAdjusted = calcNetValue(grossTotal, provTotal)
    }
    // 五、报表列示数 = 净值 - 一年内
    const oneYearTotal = groups.value.find(g => g.groupType === 'oneYear')
      ?.rows.reduce((s, r) => s + r.closingAdjusted, 0) ?? 0
    const reportGroup = groups.value.find(g => g.groupType === 'report')
    if (reportGroup && reportGroup.rows.length > 0) {
      reportGroup.rows[0].closingAdjusted = calcReportAmount(
        netGroup?.rows[0]?.closingAdjusted ?? 0, oneYearTotal
      )
    }
  }

  function toggleGroup(groupType: GroupType) {
    const g = groups.value.find(grp => grp.groupType === groupType)
    if (g) g.expanded = !g.expanded
  }

  const allRows = computed(() => groups.value.flatMap(g => g.rows))
  const needsReason = (row: AdjudicationRow) =>
    row.changeRate !== null && Math.abs(row.changeRate) > 0.2

  return {
    groups,
    tbValues,
    variance,
    allRows,
    recalcRow,
    recalcDerived,
    toggleGroup,
    needsReason,
  }
}
