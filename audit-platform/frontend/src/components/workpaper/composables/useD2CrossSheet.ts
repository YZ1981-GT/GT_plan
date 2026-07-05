/**
 * useD2CrossSheet — D2 应收账款跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('D2-*')?.remark 存 JSON 数组或数值，try/catch 解析。
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import {
  parseNum,
  sumif,
  getAuditedAmount,
} from './useD2FormulaEngine'
import type { ChecklistResponse } from './useD2FormData'
import type { DetailRow } from './useD2Detail'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD2CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
}

/** D2-3 坏账准备行原始 JSON 结构 */
interface BadDebtRowRaw {
  rowId?: string
  isFixed?: boolean
  priorAudited?: number
  currentAudited?: number
}

/** D2-9 单项 ECL 行原始 JSON 结构 */
interface Ecl9RowRaw {
  auditedBalance?: number
  shouldProvision?: number
  actualBalance?: number
  difference?: number
}

export interface D2AgingBands {
  within1Year: number
  y1to2: number
  y2to3: number
  y3to4: number
  y4to5: number
  over5: number
}

export interface D2DisclosureSourceData {
  individual: { prior: number; current: number }
  aging: { prior: number; current: number }
  customerType: { prior: number; current: number }
  total: { prior: number; current: number }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function sumAgingBands(
  rows: DetailRow[],
  prefix: 'priorAging' | 'currentAging' | 'auditedAging',
): D2AgingBands {
  const fields = [
    `${prefix}1Year`,
    `${prefix}1to2`,
    `${prefix}2to3`,
    `${prefix}3to4`,
    `${prefix}4to5`,
    `${prefix}Over5`,
  ] as const

  const result: D2AgingBands = {
    within1Year: 0,
    y1to2: 0,
    y2to3: 0,
    y3to4: 0,
    y4to5: 0,
    over5: 0,
  }

  const keys: (keyof D2AgingBands)[] = [
    'within1Year', 'y1to2', 'y2to3', 'y3to4', 'y4to5', 'over5',
  ]

  for (const row of rows) {
    fields.forEach((field, i) => {
      result[keys[i]] += parseNum((row as Record<string, unknown>)[field])
    })
  }

  return result
}

function mapDetailRow(raw: Record<string, unknown>): DetailRow {
  return {
    rowId: String(raw.rowId ?? ''),
    seq: parseNum(raw.seq),
    customerName: String(raw.customerName ?? ''),
    companyCode: String(raw.companyCode ?? ''),
    relationType: String(raw.relationType ?? '非关联方'),
    priorUnadjusted: parseNum(raw.priorUnadjusted),
    priorAje: parseNum(raw.priorAje),
    priorRje: parseNum(raw.priorRje),
    priorAudited: parseNum(raw.priorAudited),
    priorAging1Year: parseNum(raw.priorAging1Year),
    priorAging1to2: parseNum(raw.priorAging1to2),
    priorAging2to3: parseNum(raw.priorAging2to3),
    priorAging3to4: parseNum(raw.priorAging3to4),
    priorAging4to5: parseNum(raw.priorAging4to5),
    priorAgingOver5: parseNum(raw.priorAgingOver5),
    debitOccurrence: parseNum(raw.debitOccurrence),
    creditOccurrence: parseNum(raw.creditOccurrence),
    endBalance: parseNum(raw.endBalance),
    reclassification: parseNum(raw.reclassification),
    currentUnadjusted: parseNum(raw.currentUnadjusted ?? raw.S),
    currentAging1Year: parseNum(raw.currentAging1Year),
    currentAging1to2: parseNum(raw.currentAging1to2),
    currentAging2to3: parseNum(raw.currentAging2to3),
    currentAging3to4: parseNum(raw.currentAging3to4),
    currentAging4to5: parseNum(raw.currentAging4to5),
    currentAgingOver5: parseNum(raw.currentAgingOver5),
    currentAje: parseNum(raw.currentAje ?? raw.Z),
    currentRje: parseNum(raw.currentRje ?? raw.AA),
    currentAudited: parseNum(raw.currentAudited),
    auditedAging1Year: parseNum(raw.auditedAging1Year),
    auditedAging1to2: parseNum(raw.auditedAging1to2),
    auditedAging2to3: parseNum(raw.auditedAging2to3),
    auditedAging3to4: parseNum(raw.auditedAging3to4),
    auditedAging4to5: parseNum(raw.auditedAging4to5),
    auditedAgingOver5: parseNum(raw.auditedAgingOver5),
    creditRiskClassification: String(raw.creditRiskClassification ?? raw.AI ?? ''),
    groupName: String(raw.groupName ?? ''),
    isConfirmation: Boolean(raw.isConfirmation),
    postPayment: parseNum(raw.postPayment),
    remark: String(raw.remark ?? ''),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2CrossSheet(options: UseD2CrossSheetOptions) {
  const { allResponses } = options

  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loaded')

  function getVal(itemId: string): ChecklistResponse {
    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  }

  // ─── D2-2 明细行 ───────────────────────────────────────────────────────

  const detailRows = computed<DetailRow[]>(() => {
    const jsonData = getVal('D2-detail-rows').remark
    if (jsonData) {
      try {
        const parsed = JSON.parse(jsonData)
        if (Array.isArray(parsed)) {
          return parsed.map((row: Record<string, unknown>) => mapDetailRow(row))
        }
      } catch { /* fall through */ }
    }

    const count = parseNum(getVal('D2-detail-count').remark)
    if (count <= 0) return []

    const rows: DetailRow[] = []
    for (let i = 1; i <= count; i++) {
      rows.push(mapDetailRow({
        rowId: `detail-${i}`,
        creditRiskClassification:
          getVal(`D2-detail-${i}-creditRiskClassification`).remark
          || getVal(`D2-detail-${i}-AI`).remark
          || '',
        currentUnadjusted: getVal(`D2-detail-${i}-currentUnadjusted`).remark,
        currentAje: getVal(`D2-detail-${i}-currentAje`).remark,
        currentRje: getVal(`D2-detail-${i}-currentRje`).remark,
        priorAudited: getVal(`D2-detail-${i}-priorAudited`).remark,
      }))
    }
    return rows
  })

  // ─── D2-2 → D2-1 SUMIF 聚合 ────────────────────────────────────────────

  const sumifAggregation = computed(() => {
    const rows = detailRows.value
    if (rows.length === 0) return null

    crossSheetStatus.value = 'loading'
    try {
      const result = {
        individual: {
          currentUnadjusted: sumif(rows, 'creditRiskClassification', '单项计提', 'currentUnadjusted'),
          currentAje: sumif(rows, 'creditRiskClassification', '单项计提', 'currentAje'),
          currentRje: sumif(rows, 'creditRiskClassification', '单项计提', 'currentRje'),
          priorAudited: sumif(rows, 'creditRiskClassification', '单项计提', 'priorAudited'),
        },
        aging: {
          currentUnadjusted: sumif(rows, 'creditRiskClassification', '账龄组合', 'currentUnadjusted'),
          currentAje: sumif(rows, 'creditRiskClassification', '账龄组合', 'currentAje'),
          currentRje: sumif(rows, 'creditRiskClassification', '账龄组合', 'currentRje'),
          priorAudited: sumif(rows, 'creditRiskClassification', '账龄组合', 'priorAudited'),
        },
        customerType: {
          currentUnadjusted: sumif(rows, 'creditRiskClassification', '客户类型组合', 'currentUnadjusted'),
          currentAje: sumif(rows, 'creditRiskClassification', '客户类型组合', 'currentAje'),
          currentRje: sumif(rows, 'creditRiskClassification', '客户类型组合', 'currentRje'),
          priorAudited: sumif(rows, 'creditRiskClassification', '客户类型组合', 'priorAudited'),
        },
      }
      crossSheetStatus.value = 'loaded'
      return result
    } catch {
      crossSheetStatus.value = 'error'
      return null
    }
  })

  // ─── D2-3 坏账准备合计 ─────────────────────────────────────────────────

  const badDebtByCategory: ComputedRef<{
    individual: { prior: number; current: number }
    aging: { prior: number; current: number }
    customerType: { prior: number; current: number }
  }> = computed(() => {
    const result = {
      individual: { prior: 0, current: 0 },
      aging: { prior: 0, current: 0 },
      customerType: { prior: 0, current: 0 },
    }

    for (const [cat, key] of [
      ['individual', 'D2-bd-individual-rows'],
      ['aging', 'D2-bd-aging-rows'],
      ['customerType', 'D2-bd-customer-rows'],
    ] as const) {
      const rows = safeParseRows<BadDebtRowRaw>(getVal(key).remark)
      const fixedRow = rows.find(r => r.isFixed)
      if (fixedRow) {
        result[cat].prior = parseNum(fixedRow.priorAudited)
        result[cat].current = parseNum(fixedRow.currentAudited)
      }
    }
    return result
  })

  const badDebtTotal: ComputedRef<{ prior: number; current: number }> = computed(() => {
    const by = badDebtByCategory.value
    return {
      prior: by.individual.prior + by.aging.prior + by.customerType.prior,
      current: by.individual.current + by.aging.current + by.customerType.current,
    }
  })

  // ─── D2-9 单项 ECL 合计 ────────────────────────────────────────────────

  const eclSingleTotal: ComputedRef<number> = computed(() => {
    const rows = safeParseRows<Ecl9RowRaw>(getVal('D2-ecl9-rows').remark)
    return rows.reduce((sum, row) => sum + parseNum(row.shouldProvision), 0)
  })

  // ─── D2-1 → 附注审定数据 ───────────────────────────────────────────────

  const adjudicationForDisclosure: ComputedRef<D2DisclosureSourceData> = computed(() => {
    const agg = sumifAggregation.value

    function readAudited(
      rowKey: string,
      aggKey: 'individual' | 'aging' | 'customerType',
    ): { prior: number; current: number } {
      const priorUnadjusted = parseNum(getVal(`D2-adj-${rowKey}-prior-unadjusted`).remark)
        || (agg ? agg[aggKey].priorAudited : 0)
      const priorAje = parseNum(getVal(`D2-adj-${rowKey}-prior-aje`).remark)
      const priorRje = parseNum(getVal(`D2-adj-${rowKey}-prior-rje`).remark)
      const prior = getAuditedAmount(priorUnadjusted, priorAje, priorRje)

      const currentUnadjusted = parseNum(getVal(`D2-adj-${rowKey}-current-unadjusted`).remark)
        || (agg ? agg[aggKey].currentUnadjusted : 0)
      const currentAje = parseNum(getVal(`D2-adj-${rowKey}-current-aje`).remark)
        || (agg ? agg[aggKey].currentAje : 0)
      const currentRje = parseNum(getVal(`D2-adj-${rowKey}-current-rje`).remark)
        || (agg ? agg[aggKey].currentRje : 0)
      const current = getAuditedAmount(currentUnadjusted, currentAje, currentRje)

      return { prior, current }
    }

    const individual = readAudited('individual', 'individual')
    const aging = readAudited('aging', 'aging')
    const customerType = readAudited('customer-type', 'customerType')

    return {
      individual,
      aging,
      customerType,
      total: {
        prior: individual.prior + aging.prior + customerType.prior,
        current: individual.current + aging.current + customerType.current,
      },
    }
  })

  // ─── D2-2 账龄段汇总 ───────────────────────────────────────────────────

  const agingFromDetail: ComputedRef<{
    prior: D2AgingBands
    current: D2AgingBands
    audited: D2AgingBands
  }> = computed(() => {
    const rows = detailRows.value
    return {
      prior: sumAgingBands(rows, 'priorAging'),
      current: sumAgingBands(rows, 'currentAging'),
      audited: sumAgingBands(rows, 'auditedAging'),
    }
  })

  return {
    detailRows,
    sumifAggregation,
    badDebtByCategory,
    badDebtTotal,
    eclSingleTotal,
    adjudicationForDisclosure,
    agingFromDetail,
    crossSheetStatus,
  }
}

export default useD2CrossSheet
