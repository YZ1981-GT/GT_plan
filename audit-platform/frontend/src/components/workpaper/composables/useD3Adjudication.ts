/**
 * useD3Adjudication — D3-1 审定表核心逻辑 composable
 *
 * Spec: .kiro/specs/d3-prepaid-accounts/
 * Task: 6.1
 *
 * 职责：
 * - 双区块固定行（按性质分类 NATURE_ROWS + 按账龄分类 AGING_ROWS）
 * - sections computed（从allResponses加载 + crossSheet聚合填入）
 * - trialBalanceAmount（从TB auto_data取数）+ trialBalanceDiff computed
 * - crossValidationDiff + crossValidationWarning computed
 * - auditNotes 双向绑定（agingReason/changeAnalysis/conclusion）
 * - updateCell（编辑 → 公式重算 → debouncedSave）
 * - publishAdjudicated（EventBus发布，payload含2203/auditedAmount）
 * - onAdjustmentCreated监听（AJE/RJE累加）
 *
 * Requirements: 1.1-1.8, 2.1-2.8, 3.1-3.7, 18.1
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
} from './useD3FormulaEngine'
import { resolveTbAmountWithSeed } from './dCycleTbSeed'
import { D3_NATURE_CATEGORIES, D3_NATURE_LABEL_TO_KEY } from './d3NatureCategories'
import type { ChecklistResponse } from './useD3FormData'
import type { useD3CrossSheet } from './useD3CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjudicationRow {
  rowKey: string
  label: string
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number      // = 未审 + AJE + RJE
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number    // = 未审 + AJE + RJE
  changeAmount: number      // = 期末审定 - 期初审定
  changeRate: number | '' | 'N/A'
  reasonAnalysis: string
  isFromCrossSheet: boolean
  isEditable: boolean
}

export interface AdjudicationSection {
  sectionKey: 'by-nature' | 'by-aging'
  sectionLabel: string
  rows: AdjudicationRow[]
  subtotalRow: AdjudicationRow
}

export interface AdjustmentPayload {
  wpCode: string
  entryType: 'AJE' | 'RJE'
  amount: number
  accountCode?: string
}

export interface UseD3AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD3CrossSheet>
  isReadonly: Ref<boolean>
  /**
   * 试算平衡表预收款项（2203）数 —— render `project_context.tb_amount`
   * （`seed_tb_amount_scalars` 按 BS-046 报表行解析后的叶子口径）。
   *
   * 只在审计师未手工录入时回退使用（手工优先）。改造前该字段零消费方 =
   * dead output ⇒ TB 核对行恒 0、差异显示为整额假差异。
   *
   * spec: d-cycle-four-table-extraction-and-disclosure-completion Task 16
   */
  tbSeedAmount?: Ref<number>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/**
 * 区块一：按性质分类固定行。
 *
 * 🔴 派生自 `d3NatureCategories.D3_NATURE_CATEGORIES`（枚举单一真源，同时驱动 D3-2 C 列下拉）。
 * 禁在此处重写字面量 —— 标签必须与 D3-2 C 列取值逐字相同，否则源模板
 * `B8=SUMIF(D3-2!$C$12:$C$22, A8, ...)` 对应的聚合恒为 0。
 * spec: d-cycle-four-table-extraction-and-disclosure-completion Task 26
 */
export const NATURE_ROWS: readonly { readonly rowKey: string; readonly label: string }[] =
  D3_NATURE_CATEGORIES.map(({ rowKey, label }) => Object.freeze({ rowKey, label }))

/** 区块二：按账龄分类固定行 */
export const AGING_ROWS = [
  { rowKey: 'within-1-year', label: '1年以内' },
  { rowKey: '1-to-2-years', label: '1至2年' },
  { rowKey: '2-to-3-years', label: '2至3年' },
  { rowKey: 'over-3-years', label: '3年以上' },
] as const

/** 性质标签→rowKey映射（派生自单一真源，禁写第二份字面量） */
const NATURE_LABEL_TO_KEY: Readonly<Record<string, string>> = D3_NATURE_LABEL_TO_KEY

/**
 * 默认 THREE_YEAR 账龄段 key → 旧 rowKey 映射。
 *
 * 账龄区块改为按项目账龄配置段动态生成后，对默认 THREE_YEAR 段沿用旧 rowKey，
 * 以保留既有项目已保存的手工数据（reasonAnalysis / 手工 currentUnadjusted 等
 * item_id `D3-adj-aging-{rowKey}-{field}`）不被孤立；自定义段则直接用段 key。
 */
const LEGACY_AGING_ROWKEY: Record<string, string> = {
  within1: 'within-1-year',
  y1to2: '1-to-2-years',
  y2to3: '2-to-3-years',
  over3: 'over-3-years',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeItemId(section: string, rowKey: string, field: string): string {
  return `D3-adj-${section}-${rowKey}-${field}`
}

function getResponseNum(allResponses: Map<string, ChecklistResponse>, itemId: string): number {
  return parseNum(allResponses.get(itemId)?.remark)
}

function getResponseStr(allResponses: Map<string, ChecklistResponse>, itemId: string): string {
  return allResponses.get(itemId)?.remark || ''
}

function buildRow(
  section: string,
  rowKey: string,
  label: string,
  allResponses: Map<string, ChecklistResponse>,
  crossSheetCurrent: number,
  crossSheetPrior: number,
  eventAje: number,
  eventRje: number,
): AdjudicationRow {
  // Manual fields (editable)
  const priorUnadjusted = getResponseNum(allResponses, makeItemId(section, rowKey, 'priorUnadjusted'))
  const priorAje = getResponseNum(allResponses, makeItemId(section, rowKey, 'priorAje'))
  const priorRje = getResponseNum(allResponses, makeItemId(section, rowKey, 'priorRje'))

  // Current: crossSheet fills currentUnadjusted (from D3-2), or manual edit
  const manualCurrent = getResponseNum(allResponses, makeItemId(section, rowKey, 'currentUnadjusted'))
  const currentUnadjusted = crossSheetCurrent !== 0 ? crossSheetCurrent : manualCurrent
  const currentAje = getResponseNum(allResponses, makeItemId(section, rowKey, 'currentAje')) + eventAje
  const currentRje = getResponseNum(allResponses, makeItemId(section, rowKey, 'currentRje')) + eventRje

  const priorAudited = calcAuditedAmount(priorUnadjusted, priorAje, priorRje)
  const currentAudited = calcAuditedAmount(currentUnadjusted, currentAje, currentRje)
  const changeAmount = calcChangeAmount(currentAudited, priorAudited)
  const changeRate = calcChangeRate(priorAudited, currentAudited)
  const reasonAnalysis = getResponseStr(allResponses, makeItemId(section, rowKey, 'reasonAnalysis'))

  const isFromCrossSheet = crossSheetCurrent !== 0 || crossSheetPrior !== 0

  return {
    rowKey,
    label,
    priorUnadjusted,
    priorAje,
    priorRje,
    priorAudited,
    currentUnadjusted,
    currentAje,
    currentRje,
    currentAudited,
    changeAmount,
    changeRate,
    reasonAnalysis,
    isFromCrossSheet,
    isEditable: true,
  }
}

function buildSubtotalRow(rows: AdjudicationRow[], label: string): AdjudicationRow {
  const priorUnadjusted = calcSubtotal(rows.map(r => r.priorUnadjusted))
  const priorAje = calcSubtotal(rows.map(r => r.priorAje))
  const priorRje = calcSubtotal(rows.map(r => r.priorRje))
  const currentUnadjusted = calcSubtotal(rows.map(r => r.currentUnadjusted))
  const currentAje = calcSubtotal(rows.map(r => r.currentAje))
  const currentRje = calcSubtotal(rows.map(r => r.currentRje))
  const priorAudited = calcAuditedAmount(priorUnadjusted, priorAje, priorRje)
  const currentAudited = calcAuditedAmount(currentUnadjusted, currentAje, currentRje)
  const changeAmount = calcChangeAmount(currentAudited, priorAudited)
  const changeRate = calcChangeRate(priorAudited, currentAudited)

  return {
    rowKey: 'subtotal',
    label,
    priorUnadjusted,
    priorAje,
    priorRje,
    priorAudited,
    currentUnadjusted,
    currentAje,
    currentRje,
    currentAudited,
    changeAmount,
    changeRate,
    reasonAnalysis: '',
    isFromCrossSheet: false,
    isEditable: false,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD3Adjudication(options: UseD3AdjudicationOptions) {
  const { allResponses, wpId, projectId, saveImmediate, debouncedSave, crossSheet, isReadonly } = options

  let _debounceTimer: ReturnType<typeof setTimeout> | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // EventBus accumulated AJE/RJE (session-level, from adjustment:created events)
  const eventAjeAccum = ref(0)
  const eventRjeAccum = ref(0)

  // ─── Sections computed ───────────────────────────────────────────────

  const sections: ComputedRef<AdjudicationSection[]> = computed(() => {
    const responses = allResponses.value
    const natureAgg = crossSheet.natureAggregation.value
    // segment-driven 账龄聚合 + 有效账龄段（支持自定义账龄配置）
    const agingByKey = crossSheet.agingByKey.value
    const agingSegs = crossSheet.agingSegments.value

    // === 区块一：按性质分类 ===
    const natureRows: AdjudicationRow[] = NATURE_ROWS.map(({ rowKey, label }) => {
      const aggData = natureAgg[label] || { current: 0, prior: 0 }
      return buildRow('nature', rowKey, label, responses, aggData.current, aggData.prior, 0, 0)
    })

    const natureSubtotal = buildSubtotalRow(natureRows, '合计')

    // === 区块二：按账龄分类（按项目账龄配置段动态生成） ===
    const agingRows: AdjudicationRow[] = agingSegs.map((seg) => {
      const rowKey = LEGACY_AGING_ROWKEY[seg.key] ?? seg.key
      const crossCurrent = agingByKey.current[seg.key] ?? 0
      const crossPrior = agingByKey.prior[seg.key] ?? 0
      return buildRow('aging', rowKey, seg.label, responses, crossCurrent, crossPrior, eventAjeAccum.value, eventRjeAccum.value)
    })

    const agingSubtotal = buildSubtotalRow(agingRows, '合计')

    return [
      {
        sectionKey: 'by-nature' as const,
        sectionLabel: '一、按性质分类',
        rows: natureRows,
        subtotalRow: natureSubtotal,
      },
      {
        sectionKey: 'by-aging' as const,
        sectionLabel: '二、按账龄分类',
        rows: agingRows,
        subtotalRow: agingSubtotal,
      },
    ]
  })

  // ─── Trial Balance Amount ────────────────────────────────────────────

  /**
   * 试算平衡表数（手工优先，其次 render 下发的四表口径）。
   *
   * 🔴 改造前是 `ref` + watch 只读 checklist，render 的
   * `project_context.tb_amount` 零消费方 = dead output。
   * 现按平台既有范式（D1 / D7 的 `tbSeedAmount`）加只读回退。
   */
  const trialBalanceAmount: ComputedRef<number> = computed(() =>
    resolveTbAmountWithSeed(
      allResponses.value.get('D3-adj-trial-balance-amount')?.remark,
      options.tbSeedAmount?.value,
    ),
  )

  /** trialBalanceDiff = 账龄合计 currentAudited - trialBalanceAmount */
  const trialBalanceDiff: ComputedRef<number> = computed(() => {
    const agingSubtotal = sections.value[1]?.subtotalRow
    if (!agingSubtotal) return 0
    return agingSubtotal.currentAudited - trialBalanceAmount.value
  })

  // ─── Cross Validation ────────────────────────────────────────────────

  /** crossValidationDiff = 性质合计 currentAudited - 账龄合计 currentAudited */
  const crossValidationDiff: ComputedRef<number> = computed(() => {
    const natureSubtotal = sections.value[0]?.subtotalRow
    const agingSubtotal = sections.value[1]?.subtotalRow
    if (!natureSubtotal || !agingSubtotal) return 0
    return natureSubtotal.currentAudited - agingSubtotal.currentAudited
  })

  /** crossValidationWarning: non-null when diff !== 0 */
  const crossValidationWarning: ComputedRef<string | null> = computed(() => {
    const diff = crossValidationDiff.value
    if (diff === 0) return null
    const sign = diff > 0 ? '+' : ''
    return `性质分类合计≠账龄分类合计，差额：${sign}${diff}元`
  })

  // ─── 合同负债(2205)分类适当性勾稽（CAS14） ──────────────────────────────

  /**
   * contractLiabilityWarning: CAS14 下 2203 预收账款仅应保留非收入范围预收
   * （预收销售固定资产款/土地使用权款/合同不成立时已收取的对价）。
   * 「其他」类金额 > 0 时提示评估是否属于合同负债范围，应重分类至 2205。
   * 基于按性质分类聚合的「其他」类当期审定额判断，不臆造披露内容。
   */
  const contractLiabilityWarning: ComputedRef<string | null> = computed(() => {
    const other = crossSheet.natureAggregation.value['其他']
    const amt = other?.current ?? 0
    if (amt <= 0) return null
    const fmt = amt.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
    return `「其他」类预收账款期末审定 ${fmt} 元：CAS14 下 2203 仅应保留非收入范围预收（固定资产/土地使用权/合同不成立对价），请评估「其他」是否属于收入范围的合同负债，如是应重分类至「合同负债(2205)」并在附注区分列示。`
  })

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ agingReason: string; changeAnalysis: string; conclusion: string }>({
    agingReason: '',
    changeAnalysis: '',
    conclusion: '',
  })

  // Load from allResponses
  watch(
    () => [
      allResponses.value.get('D3-adj-note-aging-reason')?.remark,
      allResponses.value.get('D3-adj-note-change-analysis')?.remark,
      allResponses.value.get('D3-adj-note-conclusion')?.remark,
    ],
    ([aging, change, concl]) => {
      auditNotes.value = {
        agingReason: aging || '',
        changeAnalysis: change || '',
        conclusion: concl || '',
      }
    },
    { immediate: true },
  )

  // Watch for changes and debounce save
  watch(
    () => auditNotes.value.agingReason,
    (val) => {
      debouncedSave('D3-adj-note-aging-reason', { remark: val })
    },
  )

  watch(
    () => auditNotes.value.changeAnalysis,
    (val) => {
      debouncedSave('D3-adj-note-change-analysis', { remark: val })
    },
  )

  watch(
    () => auditNotes.value.conclusion,
    (val) => {
      debouncedSave('D3-adj-note-conclusion', { remark: val })
    },
  )

  // ─── updateCell ──────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: number | string): void {
    if (isReadonly.value) return

    // Determine section from rowKey
    const isNature = NATURE_ROWS.some(r => r.rowKey === rowKey)
    const section = isNature ? 'nature' : 'aging'
    const itemId = makeItemId(section, rowKey, field)

    // Update allResponses and trigger save
    const strValue = typeof value === 'number' ? String(value) : value
    debouncedSave(itemId, { remark: strValue })
  }

  // ─── publishAdjudicated ──────────────────────────────────────────────

  function publishAdjudicated(): void {
    const agingSubtotal = sections.value[1]?.subtotalRow
    const auditedAmount = agingSubtotal?.currentAudited ?? 0

    const payload = {
      wpCode: 'D3',
      accountCode: '2203',
      auditedAmount,
    }

    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
    } catch { /* silent */ }
  }

  // ─── onAdjustmentCreated ─────────────────────────────────────────────

  function onAdjustmentCreated(payload: AdjustmentPayload): void {
    if (payload.wpCode !== 'D3') return
    if (payload.entryType === 'AJE') {
      eventAjeAccum.value += payload.amount
    } else if (payload.entryType === 'RJE') {
      eventRjeAccum.value += payload.amount
    }
  }

  // ─── EventBus Registration ───────────────────────────────────────────

  const adjustmentHandler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail) onAdjustmentCreated(detail)
  }
  window.addEventListener('adjustment:created', adjustmentHandler)
  eventListeners.push({ event: 'adjustment:created', handler: adjustmentHandler })

  onBeforeUnmount(() => {
    if (_debounceTimer) {
      clearTimeout(_debounceTimer)
      _debounceTimer = null
    }
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    // 双区块
    sections,
    // 试算平衡表数 + 差异
    trialBalanceAmount,
    trialBalanceDiff,
    // 交叉验证
    crossValidationDiff,
    crossValidationWarning,
    // CAS14 合同负债分类适当性
    contractLiabilityWarning,
    // 审计说明
    auditNotes,
    // 操作
    updateCell,
    publishAdjudicated,
    // EventBus
    onAdjustmentCreated,
    // Internal (for testing)
    _eventAjeAccum: eventAjeAccum,
    _eventRjeAccum: eventRjeAccum,
  }
}

export default useD3Adjudication
