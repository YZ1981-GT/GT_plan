/**
 * useD2CrossSheet — D2 应收账款跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('D2-*')?.remark 存 JSON 数组或数值，try/catch 解析。
 *
 * P1-6 优化：使用 focused key extractors 避免任意 item 变化触发全部 crossSheet 重算。
 * 每个 crossSheet computed 仅依赖其实际使用的 key 的 remark 值（通过中间 computed 隔离）。
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
import { PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD2CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  /**
   * 项目账龄配置段（3年段 / 5年段 / 自定义，来自 useAgingConfig）。
   * 不传则回退 5 年段预设（与 useAgingConfig 对 D2 的默认预设一致）。
   */
  agingSegments?: Ref<AgingSegment[]>
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

/**
 * 账龄段汇总：**键 = 项目账龄配置的段 key**（枚举账龄：3年段 / 5年段 / 自定义）。
 * 不再是固定 6 段结构体——项目切 3 年段时键为 within1/y1to2/y2to3/over3。
 */
export type D2AgingBands = Record<string, number>

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

/** 账龄期间 → D2-2 明细行的 nested 容器字段 / legacy 扁平字段前缀。 */
const AGING_PERIOD_FIELDS = {
  prior: { nested: 'agingPrior', flat: 'priorAging' },
  current: { nested: 'agingCurrent', flat: 'currentAging' },
  audited: { nested: 'agingAudited', flat: 'auditedAging' },
} as const

export type D2AgingPeriod = keyof typeof AGING_PERIOD_FIELDS

/**
 * 段 key → legacy 扁平字段后缀（迁移前 D2-detail-rows 的 `{prefix}{suffix}`）。
 * `over3`（3 年段的「3年以上」）在 legacy 里没有单一字段，须由 3-4/4-5/5年以上 三段相加，
 * 这正是此前「3 年段项目的 3 年以上金额恒 0」的根因。
 */
const LEGACY_AGING_SUFFIX: Record<string, string[]> = {
  within1: ['1Year'],
  within1Year: ['1Year'],
  y1to2: ['1to2'],
  y2to3: ['2to3'],
  y3to4: ['3to4'],
  y4to5: ['4to5'],
  over3: ['3to4', '4to5', 'Over5'],
  over5: ['Over5'],
}

/**
 * 取某行某期间某账龄段的金额：**nested keyed 优先**（aging-config 迁移后的存储形态），
 * 无 nested 时回退 legacy 扁平字段（迁移前数据），两者都没有则 0。纯函数，可独立测试。
 */
export function agingCellValue(
  row: Record<string, unknown>,
  period: D2AgingPeriod,
  segKey: string,
): number {
  const { nested, flat } = AGING_PERIOD_FIELDS[period]
  const container = row?.[nested]
  if (container && typeof container === 'object' && !Array.isArray(container)) {
    const v = (container as Record<string, unknown>)[segKey]
    if (v !== undefined && v !== null && v !== '') return parseNum(v)
  }
  const suffixes = LEGACY_AGING_SUFFIX[segKey]
  if (!suffixes) return 0
  return suffixes.reduce((s, sfx) => s + parseNum(row?.[`${flat}${sfx}`]), 0)
}

/**
 * 按项目账龄配置段汇总 D2-2 明细账龄（枚举账龄单一口径）。
 * 纯函数：段列表由调用方给定，键即段 key，不再硬编码 6 段。
 */
export function sumAgingBySegments(
  rows: readonly Record<string, unknown>[],
  period: D2AgingPeriod,
  segments: readonly AgingSegment[],
): D2AgingBands {
  const result: D2AgingBands = {}
  for (const seg of segments) result[seg.key] = 0
  for (const row of rows) {
    for (const seg of segments) {
      result[seg.key] += agingCellValue(row, period, seg.key)
    }
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

  // ─── P1-6: Focused key extractors ─────────────────────────────────────
  // 每个 computed 仅依赖自己需要的特定 key 的 remark 值。
  // 当其他 key 变化时（如 D2-adj-* 更新），明细/坏账/ECL 的 computed 不重算。
  const detailRowsJson = computed(() => getVal('D2-detail-rows').remark)
  const detailCount = computed(() => getVal('D2-detail-count').remark)
  const bdIndividualJson = computed(() => getVal('D2-bd-individual-rows').remark)
  const bdAgingJson = computed(() => getVal('D2-bd-aging-rows').remark)
  const bdCustomerJson = computed(() => getVal('D2-bd-customer-rows').remark)
  const ecl9RowsJson = computed(() => getVal('D2-ecl9-rows').remark)
  const tbAmountRemark = computed(() => getVal('D2-adj-tb-amount').remark)

  // ─── D2-2 明细行 ───────────────────────────────────────────────────────

  const detailRows = computed<DetailRow[]>(() => {
    const jsonData = detailRowsJson.value
    if (jsonData) {
      try {
        const parsed = JSON.parse(jsonData)
        if (Array.isArray(parsed)) {
          return parsed.map((row: Record<string, unknown>) => mapDetailRow(row))
        }
      } catch { /* fall through */ }
    }

    const count = parseNum(detailCount.value)
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

    for (const [cat, jsonRef] of [
      ['individual', bdIndividualJson],
      ['aging', bdAgingJson],
      ['customerType', bdCustomerJson],
    ] as const) {
      const rows = safeParseRows<BadDebtRowRaw>(jsonRef.value)
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
    const rows = safeParseRows<Ecl9RowRaw>(ecl9RowsJson.value)
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

  /** 生效账龄段：项目账龄配置优先（3年段/5年段/自定义），未注入时回退 5 年段预设。 */
  const effectiveAgingSegments: ComputedRef<AgingSegment[]> = computed(() => {
    const list = options.agingSegments?.value
    if (Array.isArray(list) && list.length > 0) return list
    return PRESET_SEGMENTS.FIVE_YEAR
  })

  const agingFromDetail: ComputedRef<{
    prior: D2AgingBands
    current: D2AgingBands
    audited: D2AgingBands
    segments: AgingSegment[]
  }> = computed(() => {
    const rows = detailRows.value as unknown as Record<string, unknown>[]
    const segments = effectiveAgingSegments.value
    return {
      prior: sumAgingBySegments(rows, 'prior', segments),
      current: sumAgingBySegments(rows, 'current', segments),
      audited: sumAgingBySegments(rows, 'audited', segments),
      segments,
    }
  })

  // ─── D2-1↔D2-2 勾稽校验 ───────────────────────────────────────────────
  // 明细表(D2-2)合计 vs 审定表(D2-1)审定额 差异提示

  const detailTotalAudited = computed(() => {
    return detailRows.value.reduce(
      (sum, row) => sum + parseNum(row.currentAudited),
      0,
    )
  })

  const adjudicationTotalAudited = computed(() => {
    const adj = adjudicationForDisclosure.value
    return adj.total.current
  })

  /** 明细表合计 vs 审定表合计差异（绝对值 > 0.01 视为不平） */
  const reconciliationDiff = computed(() => {
    const diff = detailTotalAudited.value - adjudicationTotalAudited.value
    return {
      diff,
      isBalanced: Math.abs(diff) <= 0.01,
      detailTotal: detailTotalAudited.value,
      adjTotal: adjudicationTotalAudited.value,
    }
  })

  // ─── D2-10 ECL↔D2-3 坏账准备期末勾稽 ──────────────────────────────────

  const eclVsBadDebtDiff = computed(() => {
    const eclTotal = eclSingleTotal.value
    const bdCurrent = badDebtTotal.value.current
    const diff = eclTotal - bdCurrent
    return {
      diff,
      isBalanced: Math.abs(diff) <= 0.01,
      eclTotal,
      badDebtCurrent: bdCurrent,
    }
  })

  // ─── D2-2 明细表↔TB 余额核对 ──────────────────────────────────────────

  const detailVsTbDiff = computed(() => {
    const tbAmount = parseNum(tbAmountRemark.value)
    const detailTotal = detailTotalAudited.value
    if (tbAmount === 0 && detailTotal === 0) {
      return { diff: 0, isBalanced: true, detailTotal: 0, tbAmount: 0 }
    }
    const diff = detailTotal - tbAmount
    return {
      diff,
      isBalanced: Math.abs(diff) <= 0.01,
      detailTotal,
      tbAmount,
    }
  })

  return {
    detailRows,
    sumifAggregation,
    badDebtByCategory,
    badDebtTotal,
    eclSingleTotal,
    adjudicationForDisclosure,
    agingSegments: effectiveAgingSegments,
    agingFromDetail,
    reconciliationDiff,
    eclVsBadDebtDiff,
    detailVsTbDiff,
    crossSheetStatus,
  }
}

export default useD2CrossSheet
