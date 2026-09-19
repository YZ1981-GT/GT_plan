/**
 * useG10VoucherCheck — G10-7 凭证检查（贷方侧，6项核对 + 双表口径）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { parseNum, isDebitCreditBalanced, calcSubtotal } from './useG10FormulaEngine'
import {
  G10A_VOUCHER_MARK_KEY,
  G10A_VOUCHER_PROGRAM_NOS,
  buildG10VoucherProcedureSummary,
  markG10AProcedureSteps,
} from './g10FvCrossHelpers'
import {
  buildG10VoucherPushItems,
  isG10QuantitativeVoucherAbnormal,
  pushG10VoucherAbnormalToAdjustment,
} from './g10VoucherCross'
import {
  G10_VOUCHER_CHECK_DEFS,
  G10_VOUCHER_PERIOD_OPTIONS,
  calcG10SampleAbsAmount,
  calcG10SuggestedSampleSize,
  defaultG10SamplingParams,
  formatG10SamplingMethodLabel,
  g10VoucherInspectionRatio,
  parseG10SamplingParams,
  type G10SamplingParams,
  type G10ScopeSamplingParams,
  type G10VoucherCheckKey,
  type G10VoucherPeriodScope,
} from './g10VoucherConstants'
import { G10_ACCOUNT_CODE, G10_ACCOUNT_NAME } from './g10Constants'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export type G10VoucherTab = 'basic' | 'check' | 'conclusion'

export interface G10VoucherCheckRow {
  id: string
  seq: number
  periodScope: G10VoucherPeriodScope
  voucherDate: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  debitAmount: number
  creditAmount: number
  attachment: string | null
  supportingDocDesc: string
  check1OriginalComplete: boolean
  check2Authorization: boolean
  check3Accounting: boolean
  check4InitialCost: boolean
  check5Interest: boolean
  check6FairValueCorrect: boolean
  indexNo: string
  isAbnormal: boolean
  abnormalDesc: string
  riskLevel: 'high' | 'medium' | 'low' | ''
  remark: string
  source: string
}

const ITEM_ID_ROWS = 'G10-voucher-rows'
const ITEM_ID_CONCLUSION = 'G10-voucher-conclusion'
export const ITEM_ID_G10_VC_PARAMS = 'G10-vc-params'
const ROWS_VERSION = 2

function generateId(): string {
  return `g10v-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function recalcG10VoucherAbnormal(row: G10VoucherCheckRow): G10VoucherCheckRow {
  const checks = G10_VOUCHER_CHECK_DEFS.map((d) => row[d.key as G10VoucherCheckKey])
  const isAbnormal = checks.some((c) => c === false)
  return { ...row, isAbnormal }
}

function toBoolCheck(v: unknown): boolean {
  if (typeof v === 'boolean') return v
  const s = String(v ?? '').trim()
  return s === '✓' || s === '是' || s === 'true' || s === '1'
}

export function enrichG10VoucherRow(raw: Partial<G10VoucherCheckRow> & { id?: string }, seq: number): G10VoucherCheckRow {
  const base: G10VoucherCheckRow = {
    id: raw.id ?? generateId(),
    seq,
    periodScope: (raw.periodScope as G10VoucherPeriodScope) ?? 'current',
    voucherDate: raw.voucherDate ?? '',
    voucherNo: raw.voucherNo ?? '',
    businessContent: raw.businessContent ?? raw.summary ?? '',
    counterAccount: raw.counterAccount ?? '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount ?? raw.amount),
    attachment: raw.attachment ?? null,
    supportingDocDesc: raw.supportingDocDesc ?? '',
    check1OriginalComplete: raw.check1OriginalComplete === undefined ? true : toBoolCheck(raw.check1OriginalComplete),
    check2Authorization: raw.check2Authorization === undefined ? true : toBoolCheck(raw.check2Authorization),
    check3Accounting: raw.check3Accounting === undefined ? true : toBoolCheck(raw.check3Accounting),
    check4InitialCost: raw.check4InitialCost === undefined ? true : toBoolCheck(raw.check4InitialCost),
    check5Interest: raw.check5Interest === undefined ? true : toBoolCheck(raw.check5Interest),
    check6FairValueCorrect: raw.check6FairValueCorrect === undefined
      ? toBoolCheck((raw as any).check4FairValueCorrect ?? true)
      : toBoolCheck(raw.check6FairValueCorrect),
    indexNo: raw.indexNo ?? raw.indexRef ?? '',
    isAbnormal: false,
    abnormalDesc: raw.abnormalDesc ?? '',
    riskLevel: (raw.riskLevel as G10VoucherCheckRow['riskLevel']) ?? '',
    remark: raw.remark ?? '',
    source: raw.source ?? '',
  }
  if (raw.isAbnormal === true || raw.isAbnormal === '是' || raw.isAbnormal === '✓') {
    base.isAbnormal = true
  }
  return recalcG10VoucherAbnormal(base)
}

export function computeG10VoucherAnomalyRate(rows: G10VoucherCheckRow[]): number {
  if (!rows.length) return 0
  return (rows.filter((r) => r.isAbnormal).length / rows.length) * 100
}

function scopeLabel(scope: G10VoucherPeriodScope): string {
  return G10_VOUCHER_PERIOD_OPTIONS.find((o) => o.value === scope)?.label ?? scope
}

function appendScopeMemoSection(
  lines: string[],
  scope: G10VoucherPeriodScope,
  params: G10ScopeSamplingParams,
  scopeRows: G10VoucherCheckRow[],
): void {
  const sampleAbs = calcG10SampleAbsAmount(scopeRows)
  const ratio = g10VoucherInspectionRatio(sampleAbs, params.populationAmount)
  const suggested = calcG10SuggestedSampleSize(params)
  const abn = scopeRows.filter((r) => r.isAbnormal)

  lines.push(`### ${scopeLabel(scope)}`)
  lines.push(`- 测试总体：${params.testPopulation || '—'}`)
  lines.push(`- 特定样本：${params.specificSamples || '—'}`)
  lines.push(`- 抽样总体：${params.samplingPopulation || '—'}`)
  lines.push(`- 抽样方法：${formatG10SamplingMethodLabel(params.samplingMethod)}`)
  lines.push(`- 目标样本量：${params.targetSampleSize || '—'} 笔`)
  lines.push(`- 当前样本量：${scopeRows.length} 笔`)
  lines.push(`- 公式建议样本量：${suggested ?? '—'}`)
  lines.push(`- 总体金额：${params.populationAmount ? params.populationAmount.toLocaleString('zh-CN') : '—'}`)
  lines.push(`- 已查样本金额：${sampleAbs.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
  lines.push(`- 检查比例：${ratio == null ? '—' : `${(ratio * 100).toFixed(1)}%`}`)
  lines.push(`- 异常：${abn.length} 笔（异常率 ${computeG10VoucherAnomalyRate(scopeRows).toFixed(1)}%）`)
  if (params.samplingProcess?.trim()) {
    lines.push(`- 抽样过程：${params.samplingProcess.trim()}`)
  }
  lines.push('')
}

/** G10-7 抽样备忘（Markdown，对标 G9-6） */
export function buildG10VoucherSamplingMemo(input: {
  params: G10SamplingParams
  rows: G10VoucherCheckRow[]
  conclusion: string
  accountCode?: string
}): string {
  const { params, rows, conclusion, accountCode = G10_ACCOUNT_CODE } = input
  const currentRows = rows.filter((r) => r.periodScope === 'current')
  const subsequentRows = rows.filter((r) => r.periodScope === 'subsequent')
  const abn = rows.filter((r) => r.isAbnormal)
  const lines: string[] = []

  lines.push('# G10-7 凭证检查抽样备忘')
  lines.push('')
  lines.push(`生成时间：${new Date().toISOString()}`)
  lines.push(`科目：${accountCode} ${G10_ACCOUNT_NAME}`)
  lines.push('')
  lines.push('## 一、抽样参数（分表）')
  lines.push('')
  appendScopeMemoSection(lines, 'current', params.current, currentRows)
  appendScopeMemoSection(lines, 'subsequent', params.subsequent, subsequentRows)

  lines.push('## 二、核对结果汇总')
  lines.push(`- 全表样本行数：${rows.length}（本期 ${currentRows.length} · 期后 ${subsequentRows.length}）`)
  lines.push(`- 异常合计：${abn.length}（异常率 ${computeG10VoucherAnomalyRate(rows).toFixed(1)}%）`)
  if (abn.length) {
    lines.push('')
    lines.push('### 异常明细')
    for (const r of abn.slice(0, 50)) {
      lines.push(
        `- [${scopeLabel(r.periodScope)}] ${r.voucherNo || r.id}｜${r.businessContent || '—'}｜${r.abnormalDesc || '（无说明）'}`,
      )
    }
  }
  lines.push('')
  lines.push('## 三、检查结论')
  lines.push(conclusion?.trim() || '—')
  lines.push('')
  lines.push('## 四、编制说明')
  lines.push('- 六项核对：①齐全②授权③账务④成本⑤利息⑥公允；任一项「否」→ 异常。')
  lines.push('- 本期发生额与期后处置/新增分表编制；检查比例 = 已查金额 ÷ 总体金额。')
  lines.push('- 样本借贷不必平衡（抽样明细常为单边发生额）。')
  lines.push('- 检查比例低于 30% 时应扩大样本或在审计说明中解释。')
  lines.push('')
  return lines.join('\n')
}

function parseRows(json: string | null | undefined): G10VoucherCheckRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    if (Array.isArray(parsed)) return parsed.map((r, i) => enrichG10VoucherRow(r, i + 1))
    const rows = Array.isArray(parsed?.rows) ? parsed.rows : []
    return rows.map((r, i) => enrichG10VoucherRow(r, i + 1))
  } catch {
    return []
  }
}

export function useG10VoucherCheck(opts: {
  wpId?: Ref<string>
  projectId?: Ref<string> | ComputedRef<string>
  year?: Ref<number | null> | ComputedRef<number | null>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G10VoucherCheckRow[]>([])
  const samplingParams = ref<G10SamplingParams>(defaultG10SamplingParams())
  const activeScope = ref<G10VoucherPeriodScope>('current')
  const activeTab = ref<G10VoucherTab>('basic')
  const activeRowIndex = ref(0)
  const conclusion = ref('')
  const aiLoading = ref(false)
  const procedureMarking = ref(false)

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )
  watch(
    () => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion,
    (v) => { conclusion.value = v ?? '' },
    { immediate: true },
  )
  watch(
    () => opts.allResponses.value.get(ITEM_ID_G10_VC_PARAMS)?.remark,
    (json) => { samplingParams.value = parseG10SamplingParams(json) },
    { immediate: true },
  )

  function persistSamplingParams(): void {
    opts.debouncedSave(ITEM_ID_G10_VC_PARAMS, {
      remark: JSON.stringify(samplingParams.value),
    })
  }

  function updateScopeSampling<K extends keyof G10ScopeSamplingParams>(
    scope: G10VoucherPeriodScope,
    field: K,
    value: G10ScopeSamplingParams[K],
  ): void {
    if (opts.isReadonly.value) return
    samplingParams.value = {
      ...samplingParams.value,
      [scope]: { ...samplingParams.value[scope], [field]: value },
    }
    persistSamplingParams()
  }

  function applySuggestedSampleSize(scope: G10VoucherPeriodScope): number | null {
    const suggested = calcG10SuggestedSampleSize(samplingParams.value[scope])
    if (!suggested) return null
    updateScopeSampling(scope, 'targetSampleSize', suggested)
    return suggested
  }

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, {
      remark: JSON.stringify({ version: ROWS_VERSION, rows: rows.value }),
    })
  }

  const scopedRows = computed(() =>
    rows.value
      .filter((r) => r.periodScope === activeScope.value)
      .map((r, i) => ({ ...r, seq: i + 1 })),
  )

  const activeScopeParams = computed(() => samplingParams.value[activeScope.value])

  const suggestedSampleSize = computed(() => calcG10SuggestedSampleSize(activeScopeParams.value))

  const sampleAbsAmount = computed(() => calcG10SampleAbsAmount(scopedRows.value))

  const inspectionRatio = computed(() =>
    g10VoucherInspectionRatio(sampleAbsAmount.value, activeScopeParams.value.populationAmount),
  )

  const inspectionRatioPct = computed(() =>
    inspectionRatio.value == null ? null : inspectionRatio.value * 100,
  )

  const lowInspectionRatio = computed(() =>
    inspectionRatio.value != null && inspectionRatio.value < 0.3,
  )

  const progressPct = computed(() => {
    const target = activeScopeParams.value.targetSampleSize
    const current = scopedRows.value.length
    if (target <= 0) return current > 0 ? 100 : 0
    return Math.min(100, Math.round((current / target) * 100))
  })

  const currentSampleSize = computed(() => scopedRows.value.length)
  const debitTotal = computed(() => calcSubtotal(scopedRows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(scopedRows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => isDebitCreditBalanced(
    scopedRows.value.map((r) => r.debitAmount),
    scopedRows.value.map((r) => r.creditAmount),
  ))
  const abnormalCount = computed(() => scopedRows.value.filter((r) => r.isAbnormal).length)
  const allAbnormalCount = computed(() => rows.value.filter((r) => r.isAbnormal).length)
  const quantitativeAbnormalCount = computed(() =>
    rows.value.filter(isG10QuantitativeVoucherAbnormal).length,
  )

  function isG10VoucherRowTested(row: G10VoucherCheckRow): boolean {
    return row.check1OriginalComplete
      && row.check2Authorization
      && row.check3Accounting
      && row.check4InitialCost
      && row.check5Interest
      && row.check6FairValueCorrect
  }

  const untestedCount = computed(() => rows.value.filter((r) => !isG10VoucherRowTested(r)).length)
  const completionPct = computed(() => {
    if (!rows.value.length) return 0
    return Math.round(((rows.value.length - untestedCount.value) / rows.value.length) * 100)
  })
  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G10A_VOUCHER_MARK_KEY)?.remark
    || opts.allResponses.value.get(G10A_VOUCHER_MARK_KEY)?.conclusion === 'completed',
  )
  const useVirtualScroll = computed(() => scopedRows.value.length > 50)

  function updateRow(id: string, patch: Partial<G10VoucherCheckRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? recalcG10VoucherAbnormal(enrichG10VoucherRow({ ...r, ...patch }, r.seq)) : r))
    persist()
  }

  function addRow(): void {
    if (opts.isReadonly.value) return
    rows.value = [...rows.value, enrichG10VoucherRow({ periodScope: activeScope.value }, rows.value.length + 1)]
    persist()
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  function mergeSample(sample: Partial<G10VoucherCheckRow>): void {
    if (opts.isReadonly.value) return
    rows.value = [
      ...rows.value,
      enrichG10VoucherRow(
        { ...sample, source: sample.source ?? '抽凭', periodScope: sample.periodScope ?? activeScope.value },
        rows.value.length + 1,
      ),
    ]
    persist()
  }

  function loadRows(data: G10VoucherCheckRow[]): void {
    rows.value = data.map((r, i) => enrichG10VoucherRow(r, i + 1))
    persist()
  }

  function reloadFromStore(): void {
    rows.value = parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark)
  }

  function setActiveRowIndex(index: number): void {
    activeRowIndex.value = index
  }

  function setPeriodScope(scope: G10VoucherPeriodScope): void {
    activeScope.value = scope
    activeRowIndex.value = 0
  }

  function updateConclusion(value: string): void {
    if (opts.isReadonly.value) return
    conclusion.value = value
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: value })
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g10/ai/voucher-conclusion`, {
        rows: rows.value.filter((r) => r.isAbnormal),
        existingContent: conclusion.value,
      }, { _silent: true } as any)
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateConclusion(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  function buildMemo(): string {
    return buildG10VoucherSamplingMemo({
      params: samplingParams.value,
      rows: rows.value,
      conclusion: conclusion.value,
    })
  }

  async function pushAbnormalToAdjustment(): Promise<number> {
    if (opts.isReadonly.value) return 0
    const targets = buildG10VoucherPushItems(rows.value)
    if (!targets.length) {
      ElMessage.info('无金额类异常凭证可推送（须异常且存在借贷金额，且成本/利息/公允核对未通过）')
      return 0
    }
    const { pushed, skipped } = pushG10VoucherAbnormalToAdjustment(
      opts.allResponses.value,
      opts.debouncedSave,
      rows.value,
    )
    if (!pushed) {
      ElMessage.info(skipped ? 'G10-3 已存在相同摘要的凭证异常草稿，未重复追加' : '无可推送项')
      return 0
    }
    const skipHint = skipped ? `（跳过 ${skipped} 笔重复）` : ''
    ElMessage.success(`已向 G10-3 推送 ${pushed} 笔凭证异常调整草稿${skipHint}，并回写 G10-1`)
    return pushed
  }

  async function markProcedureComplete(): Promise<{ ok: boolean; message: string }> {
    const projectId = opts.projectId?.value
    if (!projectId || opts.isReadonly.value) {
      return { ok: false, message: '缺少项目或只读，无法回填 G10A' }
    }
    if (!rows.value.length) {
      return { ok: false, message: '请先编制 G10-7 后再回填程序表' }
    }
    procedureMarking.value = true
    try {
      const summary = buildG10VoucherProcedureSummary({
        rowCount: rows.value.length,
        abnormal: allAbnormalCount.value,
        untested: untestedCount.value,
        completionPct: completionPct.value,
        quantitative: quantitativeAbnormalCount.value,
      })
      const n = await markG10AProcedureSteps({
        projectId,
        year: opts.year?.value ?? undefined,
        programNos: [...G10A_VOUCHER_PROGRAM_NOS],
        linkedWorkpapers: 'G10-7',
        executionSummary: summary,
      })
      opts.debouncedSave(G10A_VOUCHER_MARK_KEY, {
        item_id: G10A_VOUCHER_MARK_KEY,
        conclusion: 'completed',
        remark: summary,
      })
      return {
        ok: n > 0,
        message: n > 0
          ? `已回填 G10A 程序步骤 ${[...G10A_VOUCHER_PROGRAM_NOS].join('/')}（凭证检查）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G10A 查看）',
      }
    } catch {
      return { ok: false, message: '回填 G10A 失败' }
    } finally {
      procedureMarking.value = false
    }
  }

  return {
    rows,
    scopedRows,
    samplingParams,
    activeScopeParams,
    suggestedSampleSize,
    sampleAbsAmount,
    inspectionRatio,
    inspectionRatioPct,
    lowInspectionRatio,
    progressPct,
    currentSampleSize,
    activeScope,
    activeTab,
    activeRowIndex,
    conclusion,
    aiLoading,
    debitTotal,
    creditTotal,
    balanceDiff,
    isBalanced,
    abnormalCount,
    allAbnormalCount,
    quantitativeAbnormalCount,
    untestedCount,
    completionPct,
    procedureMarking,
    procedureMarked,
    useVirtualScroll,
    updateRow,
    addRow,
    removeRow,
    mergeSample,
    loadRows,
    reloadFromStore,
    setActiveRowIndex,
    setPeriodScope,
    updateScopeSampling,
    applySuggestedSampleSize,
    updateConclusion,
    generateAiConclusion,
    buildMemo,
    pushAbnormalToAdjustment,
    markProcedureComplete,
    formatG10SamplingMethodLabel,
  }
}
