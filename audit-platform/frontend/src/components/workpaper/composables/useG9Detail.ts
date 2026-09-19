/**
 * useG9Detail — G9-2 明细表（28列 → 3区段 Tab）
 *
 * 编制逻辑：
 * 1. 期初审定 = 期初 + 期初调整；期末余额 = 期初审定+增−减+FV+利息−减值+OCI；审定 = 期末+调整
 * 2. 可按分类小计，回写 G9-1 各组首行未审数
 * 3. 可从 1504 辅助核算取数；Level3 须填估值方法
 * 4. FVOCI 可将本期 FV 变动填入 OCI 变动
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  G9_CLASSIFICATION_OPTIONS,
  G9_INSTRUMENT_TYPE_OPTIONS,
  G9_FV_LEVEL_OPTIONS,
  G9_VALUATION_METHOD_OPTIONS,
} from './g9Constants'
import { parseNum, calcAdjustedAmount, calcEndingBalance, calcSubtotal } from './useG9FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import {
  fetchG9AuxAssetSeeds,
  pushG9DetailGroupTotalsToAdjudication,
  type G9AuxAssetSeed,
} from './g9CrossHelpers'
import { matchG9AssetKey } from './g9VoucherCross'

export interface G9DetailRow {
  rowId: string
  seq: number
  assetName: string
  classification: string
  /** 附注工具种类：债务/权益/衍生/其他 */
  instrumentType: string
  /** 是否指定为 FVTPL（仅分类为 FVTPL 时有意义） */
  isDesignated: boolean
  initialInvestDate: string
  maturityDate: string
  holdingQuantity: number
  faceValueOrCost: number
  measurementAttribute: string
  isRelatedParty: boolean
  openingBalance: number
  openingAdjustment: number
  openingAdjusted: number
  increaseAmount: number
  decreaseAmount: number
  fvChangeAmount: number
  interestIncome: number
  impairmentLoss: number
  ociChange: number
  closingBalance: number
  closingAdjustment: number
  closingAdjusted: number
  fairValueLevel: string
  valuationMethod: string
  confirmationStatus: string
  ociCumulative: number
  impairmentProvision: number
  remark: string
}

export interface G9DetailRowIssue {
  rowId: string
  assetName: string
  field: string
  message: string
  variance?: number
}

export const G9_CONFIRMATION_OPTIONS = [
  '未发函',
  '已发函',
  '已回函相符',
  '已回函不符',
  '不适用',
] as const

const ITEM_ID_ROWS = 'G9-detail-rows'
const ITEM_ID_ADJ_ROWS = 'G9-adj-rows'
const DIFF_TOLERANCE = 0.01

function genId(): string {
  return `g9d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function enrichG9DetailRow(raw: Partial<G9DetailRow> & { rowId: string }, seq: number): G9DetailRow {
  const openingAdjusted = calcAdjustedAmount(
    parseNum(raw.openingBalance),
    parseNum(raw.openingAdjustment),
    0,
  )
  const closingBalance = calcEndingBalance(
    openingAdjusted,
    parseNum(raw.increaseAmount),
    parseNum(raw.decreaseAmount),
    parseNum(raw.fvChangeAmount),
    parseNum(raw.interestIncome),
    parseNum(raw.impairmentLoss),
    parseNum(raw.ociChange),
  )
  const closingAdjusted = calcAdjustedAmount(closingBalance, parseNum(raw.closingAdjustment), 0)
  return {
    rowId: raw.rowId,
    seq,
    assetName: raw.assetName ?? '',
    classification: raw.classification ?? G9_CLASSIFICATION_OPTIONS[0],
    instrumentType: raw.instrumentType
      ?? (G9_INSTRUMENT_TYPE_OPTIONS.includes(raw.measurementAttribute as typeof G9_INSTRUMENT_TYPE_OPTIONS[number])
        ? String(raw.measurementAttribute)
        : ''),
    isDesignated: !!raw.isDesignated,
    initialInvestDate: raw.initialInvestDate ?? '',
    maturityDate: raw.maturityDate ?? '',
    holdingQuantity: parseNum(raw.holdingQuantity),
    faceValueOrCost: parseNum(raw.faceValueOrCost),
    measurementAttribute: raw.measurementAttribute ?? '',
    isRelatedParty: !!raw.isRelatedParty,
    openingBalance: parseNum(raw.openingBalance),
    openingAdjustment: parseNum(raw.openingAdjustment),
    openingAdjusted,
    increaseAmount: parseNum(raw.increaseAmount),
    decreaseAmount: parseNum(raw.decreaseAmount),
    fvChangeAmount: parseNum(raw.fvChangeAmount),
    interestIncome: parseNum(raw.interestIncome),
    impairmentLoss: parseNum(raw.impairmentLoss),
    ociChange: parseNum(raw.ociChange),
    closingBalance,
    closingAdjustment: parseNum(raw.closingAdjustment),
    closingAdjusted,
    fairValueLevel: raw.fairValueLevel ?? G9_FV_LEVEL_OPTIONS[1],
    valuationMethod: raw.valuationMethod ?? '',
    confirmationStatus: raw.confirmationStatus ?? '',
    ociCumulative: parseNum(raw.ociCumulative),
    impairmentProvision: parseNum(raw.impairmentProvision),
    remark: raw.remark ?? '',
  }
}

/** 辅助核算种子 → 明细行（期末−期初轧差暂入 FV 变动） */
export function seedRowFromAux(seed: G9AuxAssetSeed, seq: number, existing?: G9DetailRow): G9DetailRow {
  const plug = Math.round((seed.closingBalance - seed.openingBalance) * 100) / 100
  const hasMovement = existing && (
    existing.increaseAmount || existing.decreaseAmount || existing.fvChangeAmount
    || existing.interestIncome || existing.impairmentLoss || existing.ociChange
  )
  return enrichG9DetailRow(
    {
      rowId: existing?.rowId ?? genId(),
      assetName: seed.assetName,
      classification: existing?.classification ?? G9_CLASSIFICATION_OPTIONS[0],
      instrumentType: existing?.instrumentType ?? '',
      isDesignated: existing?.isDesignated ?? false,
      initialInvestDate: existing?.initialInvestDate ?? '',
      maturityDate: existing?.maturityDate ?? '',
      holdingQuantity: existing?.holdingQuantity ?? 0,
      faceValueOrCost: existing?.faceValueOrCost ?? 0,
      measurementAttribute: existing?.measurementAttribute ?? '',
      isRelatedParty: existing?.isRelatedParty ?? false,
      openingBalance: seed.openingBalance,
      openingAdjustment: existing?.openingAdjustment ?? 0,
      increaseAmount: existing?.increaseAmount ?? 0,
      decreaseAmount: existing?.decreaseAmount ?? 0,
      fvChangeAmount: hasMovement ? existing!.fvChangeAmount : plug,
      interestIncome: existing?.interestIncome ?? 0,
      impairmentLoss: existing?.impairmentLoss ?? 0,
      ociChange: existing?.ociChange ?? 0,
      closingAdjustment: existing?.closingAdjustment ?? 0,
      fairValueLevel: existing?.fairValueLevel,
      valuationMethod: existing?.valuationMethod ?? '',
      confirmationStatus: existing?.confirmationStatus ?? '',
      ociCumulative: existing?.ociCumulative ?? 0,
      impairmentProvision: existing?.impairmentProvision ?? 0,
      remark: existing?.remark
        || `辅助核算(${seed.auxType})取数；增减轧差暂入FV变动，请按凭证拆分`,
    },
    seq,
  )
}

export function scanG9DetailIntegrity(rows: G9DetailRow[]): G9DetailRowIssue[] {
  const issues: G9DetailRowIssue[] = []
  for (const r of rows) {
    const name = r.assetName?.trim() || `第${r.seq}行`
    if (!r.assetName?.trim() && Math.abs(r.closingAdjusted) > DIFF_TOLERANCE) {
      issues.push({ rowId: r.rowId, assetName: name, field: 'assetName', message: '有审定余额但资产名称为空' })
    }
    if (r.fairValueLevel === 'Level3' && !r.valuationMethod?.trim()) {
      issues.push({ rowId: r.rowId, assetName: name, field: 'valuationMethod', message: 'Level3 须填估值方法' })
    }
    if (
      r.classification === 'FVOCI'
      && Math.abs(r.fvChangeAmount) > DIFF_TOLERANCE
      && Math.abs(r.ociChange) > DIFF_TOLERANCE
      && Math.abs(r.fvChangeAmount - r.ociChange) > DIFF_TOLERANCE
    ) {
      issues.push({
        rowId: r.rowId,
        assetName: name,
        field: 'ociChange',
        message: 'FVOCI 本期 OCI 变动与 FV 变动不一致（通常应对等）',
        variance: r.ociChange - r.fvChangeAmount,
      })
    }
    if (
      r.classification === 'FVOCI'
      && Math.abs(r.fvChangeAmount) > DIFF_TOLERANCE
      && Math.abs(r.ociChange) <= DIFF_TOLERANCE
    ) {
      issues.push({
        rowId: r.rowId,
        assetName: name,
        field: 'ociChange',
        message: 'FVOCI 有 FV 变动但未填 OCI 变动（可用「FV→OCI」填入）',
      })
    }
    if (
      Math.abs(r.impairmentLoss) > DIFF_TOLERANCE
      && Math.abs(r.impairmentProvision) <= DIFF_TOLERANCE
      && r.classification === '摊余成本'
    ) {
      issues.push({
        rowId: r.rowId,
        assetName: name,
        field: 'impairmentProvision',
        message: '摊余成本有本期减值损失但减值准备期末为 0，请核对',
      })
    }
  }
  return issues
}

function parseRows(json: string | null | undefined): G9DetailRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichG9DetailRow({ ...r, rowId: r.rowId || r.id || genId() }, i + 1))
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
      sum += calcAdjustedAmount(
        parseNum(v.closingUnadjusted),
        parseNum(v.closingAJE),
        parseNum(v.closingRJE),
      )
    }
    return any ? sum : null
  } catch {
    return null
  }
}

export function useG9Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
}) {
  const activeTab = ref<'basic' | 'movement' | 'closing'>('basic')
  const activeRowIndex = ref(0)
  const auxLoading = ref(false)

  const rows = computed(() => parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark))

  const currentRowKey = computed(() => rows.value[activeRowIndex.value]?.rowId ?? '')

  const classificationSubtotals = computed(() => {
    const result: Record<string, number> = {}
    for (const cls of G9_CLASSIFICATION_OPTIONS) {
      const filtered = rows.value.filter((r) => r.classification === cls)
      result[cls] = calcSubtotal(filtered.map((r) => r.closingAdjusted))
    }
    result['总计'] = calcSubtotal(rows.value.map((r) => r.closingAdjusted))
    return result
  })

  const totals = computed(() => ({
    openingAdjusted: calcSubtotal(rows.value.map((r) => r.openingAdjusted)),
    increaseAmount: calcSubtotal(rows.value.map((r) => r.increaseAmount)),
    decreaseAmount: calcSubtotal(rows.value.map((r) => r.decreaseAmount)),
    fvChangeAmount: calcSubtotal(rows.value.map((r) => r.fvChangeAmount)),
    interestIncome: calcSubtotal(rows.value.map((r) => r.interestIncome)),
    impairmentLoss: calcSubtotal(rows.value.map((r) => r.impairmentLoss)),
    ociChange: calcSubtotal(rows.value.map((r) => r.ociChange)),
    closingBalance: calcSubtotal(rows.value.map((r) => r.closingBalance)),
    closingAdjusted: calcSubtotal(rows.value.map((r) => r.closingAdjusted)),
    ociCumulative: calcSubtotal(rows.value.map((r) => r.ociCumulative)),
  }))

  const adjudicationClosingTotal = computed(() =>
    parseAdjudicationClosingTotal(opts.allResponses.value.get(ITEM_ID_ADJ_ROWS)?.remark),
  )

  const adjCrossVariance = computed(() => {
    if (adjudicationClosingTotal.value == null || !rows.value.length) return null
    return totals.value.closingAdjusted - adjudicationClosingTotal.value
  })

  const hasAdjCrossMismatch = computed(() =>
    adjCrossVariance.value != null && Math.abs(adjCrossVariance.value) > DIFF_TOLERANCE,
  )

  const integrityIssues = computed(() => scanG9DetailIntegrity(rows.value))

  const level3MissingMethodCount = computed(() =>
    integrityIssues.value.filter((i) => i.field === 'valuationMethod').length,
  )

  function persist(list: G9DetailRow[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
  }

  function updateRow(rowId: string, patch: Partial<G9DetailRow>): void {
    if (opts.isReadonly.value) return
    const list = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r, ...patch, rowId }
      if (next.classification !== 'FVTPL') next.isDesignated = false
      return enrichG9DetailRow(next, r.seq)
    })
    persist(list)
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入资产名称', '新增明细行', { inputPlaceholder: '资产名称' })
      const name = (value ?? '').trim()
      if (!name) return
      persist([...rows.value, enrichG9DetailRow({ rowId: genId(), assetName: name }, rows.value.length + 1)])
    } catch { /* cancelled */ }
  }

  async function removeRow(rowId: string): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      await ElMessageBox.confirm('确认删除该明细行？', '删除确认', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      })
      const list = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrichG9DetailRow(r, i + 1))
      persist(list)
      if (activeRowIndex.value >= list.length) {
        activeRowIndex.value = Math.max(0, list.length - 1)
      }
    } catch { /* cancelled */ }
  }

  /** FVOCI：空白 OCI 变动按 FV 变动填入 */
  function fillOciFromFvChange(force = false): number {
    if (opts.isReadonly.value) return 0
    let n = 0
    const list = rows.value.map((r) => {
      if (r.classification !== 'FVOCI') return r
      if (!Math.abs(r.fvChangeAmount)) return r
      if (!force && Math.abs(r.ociChange) > DIFF_TOLERANCE) return r
      n += 1
      return enrichG9DetailRow({ ...r, ociChange: r.fvChangeAmount, rowId: r.rowId }, r.seq)
    })
    if (n) persist(list)
    return n
  }

  async function seedFromAuxBalance(): Promise<{ added: number; updated: number; dimType: string; error?: string }> {
    if (opts.isReadonly.value) return { added: 0, updated: 0, dimType: '', error: '只读' }
    const projectId = opts.projectId?.value ?? ''
    if (!projectId) return { added: 0, updated: 0, dimType: '', error: '缺少项目 ID' }
    auxLoading.value = true
    try {
      const { seeds, dimType, error } = await fetchG9AuxAssetSeeds(projectId)
      if (error || !seeds.length) {
        return { added: 0, updated: 0, dimType, error: error || '无数据' }
      }
      const byName = new Map(
        rows.value.filter((r) => r.assetName.trim()).map((r) => [matchG9AssetKey(r.assetName), r]),
      )
      let added = 0
      let updated = 0
      const next: G9DetailRow[] = []
      let seq = 1
      for (const seed of seeds) {
        const key = matchG9AssetKey(seed.assetName)
        const prev = byName.get(key)
        if (prev) {
          updated += 1
          next.push(seedRowFromAux(seed, seq++, prev))
          byName.delete(key)
        } else {
          added += 1
          next.push(seedRowFromAux(seed, seq++))
        }
      }
      for (const r of rows.value) {
        if (!byName.has(matchG9AssetKey(r.assetName))) continue
        next.push(enrichG9DetailRow(r, seq++))
      }
      persist(next)
      return { added, updated, dimType }
    } finally {
      auxLoading.value = false
    }
  }

  function pushTotalsToAdjudication(): number {
    if (opts.isReadonly.value || !rows.value.length) return 0
    const groups = G9_CLASSIFICATION_OPTIONS.map((classification) => {
      const filtered = rows.value.filter((r) => r.classification === classification)
      return {
        classification,
        openingAdjusted: calcSubtotal(filtered.map((r) => r.openingAdjusted)),
        closingBalance: calcSubtotal(filtered.map((r) => r.closingBalance)),
        closingAdjusted: calcSubtotal(filtered.map((r) => r.closingAdjusted)),
      }
    })
    const n = pushG9DetailGroupTotalsToAdjudication(
      opts.allResponses.value,
      opts.debouncedSave,
      groups,
    )
    if (n > 0) {
      ElMessage.success(`已按分类回写 G9-1 ${n} 组未审数`)
    } else {
      ElMessage.warning('无可回写的分类合计')
    }
    return n
  }

  return {
    rows,
    activeTab,
    activeRowIndex,
    currentRowKey,
    classificationSubtotals,
    totals,
    adjudicationClosingTotal,
    adjCrossVariance,
    hasAdjCrossMismatch,
    integrityIssues,
    level3MissingMethodCount,
    auxLoading,
    updateRow,
    addRow,
    removeRow,
    fillOciFromFvChange,
    seedFromAuxBalance,
    pushTotalsToAdjudication,
    classificationOptions: G9_CLASSIFICATION_OPTIONS,
    instrumentTypeOptions: G9_INSTRUMENT_TYPE_OPTIONS,
    fvLevelOptions: G9_FV_LEVEL_OPTIONS,
    valuationMethodOptions: G9_VALUATION_METHOD_OPTIONS,
    confirmationOptions: G9_CONFIRMATION_OPTIONS,
  }
}
