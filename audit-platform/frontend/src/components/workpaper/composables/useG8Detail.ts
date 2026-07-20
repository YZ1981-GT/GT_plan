/**
 * useG8Detail — G8-2 明细表（24列+OCI期初 → 2区段 Tab）
 *
 * 编制逻辑：按被投资单位滚动列示成本/公允/OCI，支撑 G8-1 审定；
 * 并向 G8-4（公允测试）、G8-5（指定适当性）、G8-6（凭证）提供名单与账面锚点。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { G8_FV_LEVEL_OPTIONS, G8_VALUATION_METHOD_OPTIONS } from './g8Constants'
import {
  parseNum,
  calcAdjustedAmount,
  calcEndingBalance,
  calcFairValueAmount,
  calcOciCumulativeEnding,
  calcSubtotal,
} from './useG8FormulaEngine'
import {
  fetchG8AuxInvesteeSeeds,
  matchG8InvesteeKey,
  pushG8DetailTotalsToAdjudication,
  type G8AuxInvesteeSeed,
} from './g8CrossHelpers'
import type { ChecklistResponse } from './useF1FormData'

export interface G8DetailRow {
  rowId: string
  seq: number
  investeeName: string
  /** 投资比例（小数，如 0.15 = 15%） */
  investmentRatio: number
  openingBalance: number
  openingAdjustment: number
  openingAdjusted: number
  increaseAmount: number
  decreaseAmount: number
  fvChangeAmount: number
  closingBalance: number
  closingAdjustment: number
  closingAdjusted: number
  designationReason: string
  /** 期初 OCI 累计（滚动起点） */
  ociOpeningCumulative: number
  ociCumulativeChange: number
  ociCurrentChange: number
  ociToRetainedEarnings: number
  transferReason: string
  confirmationStatus: string
  fairValueLevel: string
  valuationMethod: string
  shareCount: number
  pricePerShare: number
  fairValueTotal: number
  remark: string
}

/** 行级完整性/勾稽提示 */
export interface G8DetailRowIssue {
  rowId: string
  investeeName: string
  field: string
  message: string
  variance?: number
}

export const G8_CONFIRMATION_STATUS_OPTIONS = [
  '已发函已回函',
  '已发函未回函',
  '未发函',
  '不适用',
] as const

const ITEM_ID_ROWS = 'G8-detail-rows'
const DIFF_TOLERANCE = 0.01

function genId(): string {
  return `g8d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

/** 持股数兼容导入别名 sharesHeld（导出模板历史字段） */
function resolveShareCount(raw: Partial<G8DetailRow> & Record<string, unknown>): number {
  return parseNum(raw.shareCount ?? raw.sharesHeld)
}

/**
 * 公允价值合计：优先用数量×单价；若手工填合计且与乘积差≤容差则保留手工值，
 * 否则在数量/单价均有值时以乘积覆盖（与 G8-4 口径一致）。
 */
export function resolveFairValueTotal(
  shareCount: number,
  pricePerShare: number,
  existingTotal?: number,
  opts?: { preferProduct?: boolean },
): number {
  const product = calcFairValueAmount(shareCount, pricePerShare)
  const existing = parseNum(existingTotal)
  if (shareCount && pricePerShare) {
    if (opts?.preferProduct) return product
    if (!existing) return product
    if (Math.abs(existing - product) <= DIFF_TOLERANCE) return product
    return existing
  }
  return existing
}

/** OCI 期末累计：滚动公式；preferRoll 或累计为空时用公式覆盖 */
export function resolveOciCumulative(
  opening: number,
  current: number,
  toRE: number,
  existing?: number,
  opts?: { preferRoll?: boolean },
): number {
  const computed = calcOciCumulativeEnding(opening, current, toRE)
  const existingN = parseNum(existing)
  if (opts?.preferRoll) return computed
  if (!existingN && (opening || current || toRE)) return computed
  if (Math.abs(existingN - computed) <= DIFF_TOLERANCE) return computed
  return existingN
}

export function enrichG8DetailRow(
  raw: Partial<G8DetailRow> & { rowId: string } & Record<string, unknown>,
  seq: number,
  opts?: { preferFvProduct?: boolean; preferOciRoll?: boolean },
): G8DetailRow {
  const openingAdjusted = calcAdjustedAmount(parseNum(raw.openingBalance), parseNum(raw.openingAdjustment))
  const closingBalance = calcEndingBalance(
    openingAdjusted,
    parseNum(raw.increaseAmount),
    parseNum(raw.decreaseAmount),
    parseNum(raw.fvChangeAmount),
  )
  const closingAdjusted = calcAdjustedAmount(closingBalance, parseNum(raw.closingAdjustment))
  const shareCount = resolveShareCount(raw)
  const pricePerShare = parseNum(raw.pricePerShare)
  const ociOpeningCumulative = parseNum(raw.ociOpeningCumulative)
  const ociCurrentChange = parseNum(raw.ociCurrentChange)
  const ociToRetainedEarnings = parseNum(raw.ociToRetainedEarnings)
  return {
    rowId: raw.rowId,
    seq,
    investeeName: String(raw.investeeName ?? ''),
    investmentRatio: parseNum(raw.investmentRatio),
    openingBalance: parseNum(raw.openingBalance),
    openingAdjustment: parseNum(raw.openingAdjustment),
    openingAdjusted,
    increaseAmount: parseNum(raw.increaseAmount),
    decreaseAmount: parseNum(raw.decreaseAmount),
    fvChangeAmount: parseNum(raw.fvChangeAmount),
    closingBalance,
    closingAdjustment: parseNum(raw.closingAdjustment),
    closingAdjusted,
    designationReason: String(raw.designationReason ?? ''),
    ociOpeningCumulative,
    ociCumulativeChange: resolveOciCumulative(
      ociOpeningCumulative,
      ociCurrentChange,
      ociToRetainedEarnings,
      parseNum(raw.ociCumulativeChange),
      { preferRoll: opts?.preferOciRoll },
    ),
    ociCurrentChange,
    ociToRetainedEarnings,
    transferReason: String(raw.transferReason ?? ''),
    confirmationStatus: String(raw.confirmationStatus ?? ''),
    fairValueLevel: String(raw.fairValueLevel ?? G8_FV_LEVEL_OPTIONS[1]),
    valuationMethod: String(raw.valuationMethod ?? ''),
    shareCount,
    pricePerShare,
    fairValueTotal: resolveFairValueTotal(
      shareCount,
      pricePerShare,
      parseNum(raw.fairValueTotal),
      { preferProduct: opts?.preferFvProduct },
    ),
    remark: String(raw.remark ?? ''),
  }
}

/** 将辅助核算种子转为明细行（期末−期初轧差暂入 FV 变动，便于勾稽期末） */
export function seedRowFromAux(seed: G8AuxInvesteeSeed, seq: number, existing?: G8DetailRow): G8DetailRow {
  const plug = Math.round((seed.closingBalance - seed.openingBalance) * 100) / 100
  return enrichG8DetailRow(
    {
      rowId: existing?.rowId ?? genId(),
      investeeName: seed.investeeName,
      openingBalance: seed.openingBalance,
      openingAdjustment: existing?.openingAdjustment ?? 0,
      increaseAmount: existing?.increaseAmount ?? 0,
      decreaseAmount: existing?.decreaseAmount ?? 0,
      fvChangeAmount: existing && (existing.increaseAmount || existing.decreaseAmount || existing.fvChangeAmount)
        ? existing.fvChangeAmount
        : plug,
      closingAdjustment: existing?.closingAdjustment ?? 0,
      designationReason: existing?.designationReason ?? '',
      ociOpeningCumulative: existing?.ociOpeningCumulative ?? 0,
      ociCurrentChange: existing?.ociCurrentChange ?? 0,
      ociToRetainedEarnings: existing?.ociToRetainedEarnings ?? 0,
      ociCumulativeChange: existing?.ociCumulativeChange ?? 0,
      fairValueLevel: existing?.fairValueLevel,
      valuationMethod: existing?.valuationMethod ?? '',
      shareCount: existing?.shareCount ?? 0,
      pricePerShare: existing?.pricePerShare ?? 0,
      fairValueTotal: existing?.fairValueTotal || seed.closingBalance,
      confirmationStatus: existing?.confirmationStatus ?? '',
      transferReason: existing?.transferReason ?? '',
      investmentRatio: existing?.investmentRatio ?? 0,
      remark: existing?.remark
        || `辅助核算(${seed.auxType})取数；增减轧差暂入FV变动，请按凭证拆分`,
    },
    seq,
  )
}

/** 扫描明细行完整性 */
export function scanG8DetailIntegrity(rows: G8DetailRow[]): G8DetailRowIssue[] {
  const issues: G8DetailRowIssue[] = []
  for (const r of rows) {
    const name = r.investeeName?.trim() || `第${r.seq}行`
    if (Math.abs(r.closingAdjusted) > DIFF_TOLERANCE && !r.designationReason?.trim()) {
      issues.push({
        rowId: r.rowId,
        investeeName: name,
        field: 'designationReason',
        message: '有期末审定余额但未填指定 OCI 原因',
      })
    }
    if (r.fairValueLevel === 'Level3' && !r.valuationMethod?.trim()) {
      issues.push({
        rowId: r.rowId,
        investeeName: name,
        field: 'valuationMethod',
        message: 'Level3 须填估值方法',
      })
    }
    if (r.shareCount && r.pricePerShare) {
      const product = calcFairValueAmount(r.shareCount, r.pricePerShare)
      if (Math.abs(product - r.fairValueTotal) > DIFF_TOLERANCE) {
        issues.push({
          rowId: r.rowId,
          investeeName: name,
          field: 'fairValueTotal',
          message: '公允价值合计 ≠ 持股数×每股公允价值',
          variance: r.fairValueTotal - product,
        })
      }
    }
    if (
      Math.abs(r.fvChangeAmount) > DIFF_TOLERANCE
      && Math.abs(r.ociCurrentChange) > DIFF_TOLERANCE
      && Math.abs(r.fvChangeAmount - r.ociCurrentChange) > DIFF_TOLERANCE
    ) {
      issues.push({
        rowId: r.rowId,
        investeeName: name,
        field: 'ociCurrentChange',
        message: '本期 OCI 变动与 FV 变动不一致（FVOCI 通常应对等）',
        variance: r.ociCurrentChange - r.fvChangeAmount,
      })
    }
    // OCI 滚动：期末累计 = 期初 + 本期 − 转入
    const ociExpected = calcOciCumulativeEnding(
      r.ociOpeningCumulative,
      r.ociCurrentChange,
      r.ociToRetainedEarnings,
    )
    const hasOciActivity = (
      Math.abs(r.ociOpeningCumulative) > DIFF_TOLERANCE
      || Math.abs(r.ociCurrentChange) > DIFF_TOLERANCE
      || Math.abs(r.ociToRetainedEarnings) > DIFF_TOLERANCE
      || Math.abs(r.ociCumulativeChange) > DIFF_TOLERANCE
    )
    if (hasOciActivity && Math.abs(r.ociCumulativeChange - ociExpected) > DIFF_TOLERANCE) {
      issues.push({
        rowId: r.rowId,
        investeeName: name,
        field: 'ociCumulativeChange',
        message: 'OCI期末累计 ≠ 期初累计+本期OCI−转入留存',
        variance: r.ociCumulativeChange - ociExpected,
      })
    }
    if (
      Math.abs(r.fairValueTotal) > DIFF_TOLERANCE
      && Math.abs(r.closingAdjusted) > DIFF_TOLERANCE
      && Math.abs(r.fairValueTotal - r.closingAdjusted) > DIFF_TOLERANCE
    ) {
      issues.push({
        rowId: r.rowId,
        investeeName: name,
        field: 'fairValueTotal',
        message: '公允价值合计与期末审定数不一致',
        variance: r.fairValueTotal - r.closingAdjusted,
      })
    }
    if (Math.abs(r.ociToRetainedEarnings) > DIFF_TOLERANCE && !r.transferReason?.trim()) {
      issues.push({
        rowId: r.rowId,
        investeeName: name,
        field: 'transferReason',
        message: 'OCI 转入留存收益已填金额但未说明转入原因',
      })
    }
  }
  return issues
}

function parseRows(json: string | null | undefined): G8DetailRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) =>
      enrichG8DetailRow({ ...r, rowId: r.rowId || r.id || genId() }, i + 1),
    )
  } catch {
    return []
  }
}

function parseAdjudicationClosingTotal(json: string | null | undefined): number | null {
  if (!json) return null
  try {
    const store = JSON.parse(json)
    if (!store || typeof store !== 'object' || Array.isArray(store)) return null
    let sum = 0
    let any = false
    for (const v of Object.values(store as Record<string, any>)) {
      if (!v || typeof v !== 'object') continue
      any = true
      const unadj = parseNum(v.closingUnadjusted)
      const adj = parseNum(v.closingAdjustment)
      sum += calcAdjustedAmount(unadj, adj)
    }
    return any ? sum : null
  } catch {
    return null
  }
}

export function useG8Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
}) {
  const activeTab = ref<'basic' | 'fv_oci'>('basic')
  const activeRowIndex = ref(0)
  const auxLoading = ref(false)

  const rows = computed(() => parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark))

  const totals = computed(() => ({
    openingAdjusted: calcSubtotal(rows.value.map((r) => r.openingAdjusted)),
    increaseAmount: calcSubtotal(rows.value.map((r) => r.increaseAmount)),
    decreaseAmount: calcSubtotal(rows.value.map((r) => r.decreaseAmount)),
    fvChangeAmount: calcSubtotal(rows.value.map((r) => r.fvChangeAmount)),
    closingBalance: calcSubtotal(rows.value.map((r) => r.closingBalance)),
    closingAdjusted: calcSubtotal(rows.value.map((r) => r.closingAdjusted)),
    ociOpeningCumulative: calcSubtotal(rows.value.map((r) => r.ociOpeningCumulative)),
    ociCurrentChange: calcSubtotal(rows.value.map((r) => r.ociCurrentChange)),
    ociCumulativeChange: calcSubtotal(rows.value.map((r) => r.ociCumulativeChange)),
    fairValueTotal: calcSubtotal(rows.value.map((r) => r.fairValueTotal)),
  }))

  const adjudicationClosingTotal = computed(() =>
    parseAdjudicationClosingTotal(opts.allResponses.value.get('G8-adj-rows')?.remark),
  )

  const adjCrossVariance = computed(() => {
    if (adjudicationClosingTotal.value == null || !rows.value.length) return null
    return totals.value.closingAdjusted - adjudicationClosingTotal.value
  })

  const hasAdjCrossMismatch = computed(() =>
    adjCrossVariance.value != null && Math.abs(adjCrossVariance.value) > DIFF_TOLERANCE,
  )

  const fvVsClosingVariance = computed(() =>
    totals.value.fairValueTotal - totals.value.closingAdjusted,
  )

  const hasFvVsClosingMismatch = computed(() =>
    rows.value.length > 0
    && Math.abs(totals.value.fairValueTotal) > DIFF_TOLERANCE
    && Math.abs(fvVsClosingVariance.value) > DIFF_TOLERANCE,
  )

  const integrityIssues = computed(() => scanG8DetailIntegrity(rows.value))

  const missingDesignationCount = computed(() =>
    integrityIssues.value.filter((i) => i.field === 'designationReason').length,
  )

  const ociRollIssueCount = computed(() =>
    integrityIssues.value.filter((i) => i.field === 'ociCumulativeChange').length,
  )

  function persist(list: G8DetailRow[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
  }

  function updateRow(rowId: string, patch: Partial<G8DetailRow>): void {
    if (opts.isReadonly.value) return
    const preferFvProduct = 'shareCount' in patch || 'pricePerShare' in patch
    const preferOciRoll = (
      'ociOpeningCumulative' in patch
      || 'ociCurrentChange' in patch
      || 'ociToRetainedEarnings' in patch
    )
    const list = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      return enrichG8DetailRow(
        { ...r, ...patch, rowId },
        r.seq,
        { preferFvProduct, preferOciRoll },
      )
    })
    persist(list)
  }

  function syncFairValueFromQtyPrice(rowId?: string): number {
    if (opts.isReadonly.value) return 0
    let n = 0
    const list = rows.value.map((r) => {
      if (rowId && r.rowId !== rowId) return r
      if (!r.shareCount || !r.pricePerShare) return r
      n += 1
      return enrichG8DetailRow({ ...r, rowId: r.rowId }, r.seq, { preferFvProduct: true })
    })
    if (n) persist(list)
    return n
  }

  /** 空白「本期OCI」按 FV 变动填入，并重算期末累计 */
  function fillOciFromFvChange(force = false): number {
    if (opts.isReadonly.value) return 0
    let n = 0
    const list = rows.value.map((r) => {
      if (!Math.abs(r.fvChangeAmount)) return r
      if (!force && Math.abs(r.ociCurrentChange) > DIFF_TOLERANCE) return r
      n += 1
      return enrichG8DetailRow(
        { ...r, ociCurrentChange: r.fvChangeAmount, rowId: r.rowId },
        r.seq,
        { preferOciRoll: true },
      )
    })
    if (n) persist(list)
    return n
  }

  /** 按 OCI 滚动公式重算全部期末累计 */
  function syncOciCumulativeRoll(): number {
    if (opts.isReadonly.value) return 0
    let n = 0
    const list = rows.value.map((r) => {
      n += 1
      return enrichG8DetailRow({ ...r, rowId: r.rowId }, r.seq, { preferOciRoll: true })
    })
    if (n) persist(list)
    return n
  }

  /** 从科目 1503 辅助核算生成/合并明细行 */
  async function seedFromAuxBalance(): Promise<{ added: number; updated: number; dimType: string; error?: string }> {
    if (opts.isReadonly.value) return { added: 0, updated: 0, dimType: '', error: '只读' }
    const projectId = opts.projectId?.value ?? ''
    if (!projectId) return { added: 0, updated: 0, dimType: '', error: '缺少项目 ID' }
    auxLoading.value = true
    try {
      const { seeds, dimType, error } = await fetchG8AuxInvesteeSeeds(projectId)
      if (error || !seeds.length) {
        return { added: 0, updated: 0, dimType, error: error || '无数据' }
      }
      const byName = new Map(
        rows.value.filter((r) => r.investeeName.trim()).map((r) => [matchG8InvesteeKey(r.investeeName), r]),
      )
      let added = 0
      let updated = 0
      const next: G8DetailRow[] = []
      let seq = 1
      for (const seed of seeds) {
        const prev = byName.get(matchG8InvesteeKey(seed.investeeName))
        if (prev) {
          updated += 1
          next.push(seedRowFromAux(seed, seq++, prev))
          byName.delete(matchG8InvesteeKey(seed.investeeName))
        } else {
          added += 1
          next.push(seedRowFromAux(seed, seq++))
        }
      }
      // 保留辅助核算未覆盖的已有行
      for (const r of rows.value) {
        if (!byName.has(matchG8InvesteeKey(r.investeeName))) continue
        next.push(enrichG8DetailRow(r, seq++))
      }
      persist(next)
      return { added, updated, dimType }
    } finally {
      auxLoading.value = false
    }
  }

  /** 明细合计回写 G8-1 首行未审数 */
  function pushTotalsToAdjudication(): boolean {
    if (opts.isReadonly.value || !rows.value.length) return false
    return pushG8DetailTotalsToAdjudication(
      opts.allResponses.value,
      opts.debouncedSave,
      {
        openingAdjusted: totals.value.openingAdjusted,
        closingBalance: totals.value.closingBalance,
        closingAdjusted: totals.value.closingAdjusted,
      },
    )
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增明细行', {
        inputPlaceholder: '被投资单位名称',
      })
      const name = (value ?? '').trim()
      if (!name) return
      const list = [
        ...rows.value,
        enrichG8DetailRow({ rowId: genId(), investeeName: name }, rows.value.length + 1),
      ]
      persist(list)
    } catch { /* cancelled */ }
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    const list = rows.value
      .filter((r) => r.rowId !== rowId)
      .map((r, i) => enrichG8DetailRow(r, i + 1))
    persist(list)
  }

  return {
    rows,
    activeTab,
    activeRowIndex,
    totals,
    adjudicationClosingTotal,
    adjCrossVariance,
    hasAdjCrossMismatch,
    fvVsClosingVariance,
    hasFvVsClosingMismatch,
    integrityIssues,
    missingDesignationCount,
    ociRollIssueCount,
    auxLoading,
    updateRow,
    addRow,
    removeRow,
    syncFairValueFromQtyPrice,
    fillOciFromFvChange,
    syncOciCumulativeRoll,
    seedFromAuxBalance,
    pushTotalsToAdjudication,
    fvLevelOptions: G8_FV_LEVEL_OPTIONS,
    valuationMethodOptions: G8_VALUATION_METHOD_OPTIONS,
    confirmationStatusOptions: G8_CONFIRMATION_STATUS_OPTIONS,
  }
}
