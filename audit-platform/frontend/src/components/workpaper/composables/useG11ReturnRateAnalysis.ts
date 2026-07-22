/**
 * useG11ReturnRateAnalysis — G11-4 收益率分析
 * 逻辑：收益率 = 发生额 / 平均投资；本期 vs 上期变动 |Δ|>5pp 标异常；可从 G11-1 带入审定数。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  G11_RETURN_RATE_ITEMS,
  G11_RETURN_RATE_CHANGE_THRESHOLD,
  G11_RETURN_RATE_CONCLUSION_TEMPLATES,
} from './g11Constants'
import {
  parseNum,
  calcAverageBalance,
  calcReturnRate,
  calcReturnRateChange,
  isReturnRateChangeExceeding,
  calcAdjustedAmount,
  calcSubtotal,
} from './useG11FormulaEngine'
import { parseG11AdjStore } from './g11AdjStorage'
import {
  buildBalancePatchFromTb,
  type G11TbRowLike,
} from './g11ReturnRateBalanceMap'
import { useWorkpaperAuditYear, fetchTrialBalanceByPrefix } from './workpaperAuditYear'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G11ReturnRateRow {
  id: string
  rowKey: string
  itemName: string
  /** 本期发生额①（通常取自 G11-1 本期审定） */
  currentIncome: number
  currentOpening: number
  currentClosing: number
  /** 平均投资② = (期初+期末)/2 */
  currentAvgBalance: number
  /** 比率③ = ①/② */
  currentReturnRate: number | null
  /** 上期审定数④ */
  priorAudited: number
  priorOpening: number
  priorClosing: number
  /** 平均投资⑤ */
  priorAvgBalance: number
  /** 比率⑥ = ④/⑤ */
  priorReturnRate: number | null
  /** 变动⑦ = ③−⑥ */
  returnRateChange: number | null
  /** 可选：市场平均收益率（小数），用于重大投资外部对标 */
  marketYield: number | null
  /** 本期收益率 − 市场收益率（百分点，小数形式） */
  vsMarketDiff: number | null
  abnormalNote: string
  abnormalHighlight: boolean
  /** 异常且未填说明 */
  noteRequired: boolean
}

export const ITEM_ID_RETURN_RATE_ROWS = 'G11-return-rate-rows'
export const ITEM_ID_RETURN_RATE_CONCLUSION = 'G11-return-rate-conclusion'
export const ITEM_ID_RETURN_RATE_NOTE = 'G11-return-rate-audit-note'
const ITEM_ID_ADJ_ROWS = 'G11-adj-rows'

function generateId(): string {
  return `g11rr-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function resolveRowKey(raw: Partial<G11ReturnRateRow> & { itemName?: string }): string {
  if (raw.rowKey?.trim()) return raw.rowKey.trim()
  const byLabel = G11_RETURN_RATE_ITEMS.find((d) => d.label === (raw.itemName ?? ''))
  return byLabel?.rowKey ?? `custom-${generateId()}`
}

function enrichRow(raw: Partial<G11ReturnRateRow> & { itemName: string }): G11ReturnRateRow {
  const currentIncome = parseNum(raw.currentIncome)
  const currentOpening = parseNum(raw.currentOpening)
  const currentClosing = parseNum(raw.currentClosing)
  const currentAvgBalance = calcAverageBalance(currentOpening, currentClosing)
  const priorAudited = parseNum(raw.priorAudited)
  const priorOpening = parseNum(raw.priorOpening)
  const priorClosing = parseNum(raw.priorClosing)
  const priorAvgBalance = calcAverageBalance(priorOpening, priorClosing)
  const currentReturnRate = calcReturnRate(currentIncome, currentAvgBalance)
  const priorReturnRate = calcReturnRate(priorAudited, priorAvgBalance)
  const returnRateChange = calcReturnRateChange(currentReturnRate, priorReturnRate)
  const marketYield =
    raw.marketYield === null || raw.marketYield === undefined
      ? null
      : parseNum(raw.marketYield)
  const vsMarketDiff =
    currentReturnRate !== null && marketYield !== null ? currentReturnRate - marketYield : null
  const abnormalHighlight = isReturnRateChangeExceeding(
    returnRateChange,
    G11_RETURN_RATE_CHANGE_THRESHOLD,
  )
  const abnormalNote = raw.abnormalNote ?? ''
  return {
    id: raw.id ?? generateId(),
    rowKey: resolveRowKey(raw),
    itemName: raw.itemName,
    currentIncome,
    currentOpening,
    currentClosing,
    currentAvgBalance,
    currentReturnRate,
    priorAudited,
    priorOpening,
    priorClosing,
    priorAvgBalance,
    priorReturnRate,
    returnRateChange,
    marketYield,
    vsMarketDiff,
    abnormalNote,
    abnormalHighlight,
    noteRequired: abnormalHighlight && !abnormalNote.trim(),
  }
}

function defaultRows(): G11ReturnRateRow[] {
  return G11_RETURN_RATE_ITEMS.map((def) =>
    enrichRow({
      id: generateId(),
      rowKey: def.rowKey,
      itemName: def.label,
      currentIncome: 0,
      currentOpening: 0,
      currentClosing: 0,
      priorAudited: 0,
      priorOpening: 0,
      priorClosing: 0,
      marketYield: null,
      abnormalNote: '',
    }),
  )
}

function parseRows(json: string | null | undefined): G11ReturnRateRow[] {
  if (!json) return defaultRows()
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed) || parsed.length === 0) return defaultRows()
    return parsed.map((r) => enrichRow(r))
  } catch {
    return defaultRows()
  }
}

function buildLocalConclusion(rows: G11ReturnRateRow[]): string {
  const abnormal = rows.filter((r) => r.abnormalHighlight)
  if (abnormal.length === 0) {
    return G11_RETURN_RATE_CONCLUSION_TEMPLATES[0].text
  }
  const names = abnormal.map((r) => r.itemName).slice(0, 5).join('、')
  const more = abnormal.length > 5 ? `等 ${abnormal.length} 项` : ''
  const missing = abnormal.filter((r) => !r.abnormalNote.trim()).length
  const noteHint =
    missing > 0
      ? `其中 ${missing} 项尚未填写异常说明，待补充后定稿。`
      : '异常原因已于行内说明栏记录。'
  return `经对投资收益收益率进行分析，以下项目收益率变动超过 ${G11_RETURN_RATE_CHANGE_THRESHOLD * 100} 个百分点：${names}${more}。${noteHint}建议结合 G11-5 凭证检查及投资合同进一步核实。`
}

export function useG11ReturnRateAnalysis(opts: {
  wpId: Ref<string>
  projectId?: Ref<string> | ComputedRef<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const _auditYearRef = useWorkpaperAuditYear()
  const rows = ref<G11ReturnRateRow[]>(defaultRows())
  const conclusion = ref('')
  const auditNote = ref('')
  const aiLoading = ref(false)
  const tbLoading = ref(false)
  const lastPullSummary = ref('')
  const lastTbPullSummary = ref('')

  watch(
    () => opts.allResponses.value.get(ITEM_ID_RETURN_RATE_ROWS)?.remark,
    (json) => {
      rows.value = parseRows(json)
    },
    { immediate: true },
  )
  watch(
    () => opts.allResponses.value.get(ITEM_ID_RETURN_RATE_CONCLUSION)?.conclusion,
    (v) => {
      conclusion.value = v ?? ''
    },
    { immediate: true },
  )
  watch(
    () => opts.allResponses.value.get(ITEM_ID_RETURN_RATE_NOTE)?.remark,
    (v) => {
      auditNote.value = v ?? ''
    },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_RETURN_RATE_ROWS, { remark: JSON.stringify(rows.value) })
  }

  function updateRow(id: string, patch: Partial<G11ReturnRateRow> & Record<string, unknown>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrichRow({ ...r, ...patch }) : r))
    persist()
  }

  function updateBalance(
    id: string,
    field: 'currentOpening' | 'currentClosing' | 'priorOpening' | 'priorClosing',
    value: number,
  ): void {
    if (opts.isReadonly.value) return
    updateRow(id, { [field]: value } as Partial<G11ReturnRateRow>)
  }

  function reloadFromStore(): void {
    const json = opts.allResponses.value.get(ITEM_ID_RETURN_RATE_ROWS)?.remark
    rows.value = parseRows(json)
    auditNote.value = opts.allResponses.value.get(ITEM_ID_RETURN_RATE_NOTE)?.remark ?? ''
    conclusion.value = opts.allResponses.value.get(ITEM_ID_RETURN_RATE_CONCLUSION)?.conclusion ?? ''
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增收益率分析行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      if (!value?.trim()) return
      rows.value = [
        ...rows.value,
        enrichRow({ itemName: value.trim(), rowKey: `custom-${generateId()}` }),
      ]
      persist()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  function updateConclusion(value: string): void {
    if (opts.isReadonly.value) return
    conclusion.value = value
    opts.debouncedSave(ITEM_ID_RETURN_RATE_CONCLUSION, { conclusion: value })
  }

  function updateAuditNote(value: string): void {
    if (opts.isReadonly.value) return
    auditNote.value = value
    opts.debouncedSave(ITEM_ID_RETURN_RATE_NOTE, { remark: value, conclusion: null })
  }

  function applyConclusionTemplate(key: string): void {
    if (opts.isReadonly.value) return
    const tpl = G11_RETURN_RATE_CONCLUSION_TEMPLATES.find((t) => t.key === key)
    if (tpl) updateConclusion(tpl.text)
  }

  /** 从 G11-1 审定表带入本期/上期审定数 → 发生额① / 审定数④ */
  function pullFromAdjudication(): number {
    if (opts.isReadonly.value) return 0
    const store = parseG11AdjStore(opts.allResponses.value.get(ITEM_ID_ADJ_ROWS)?.remark)
    let filled = 0
    rows.value = rows.value.map((r) => {
      if (!r.rowKey || r.rowKey.startsWith('custom-')) return r
      const adj = store[r.rowKey]
      if (!adj) return r
      const currentIncome = calcAdjustedAmount(
        parseNum(adj.currentUnadjusted),
        parseNum(adj.currentAdjustment),
      )
      const priorAudited = calcAdjustedAmount(
        parseNum(adj.priorUnadjusted),
        parseNum(adj.priorAdjustment),
      )
      if (currentIncome === 0 && priorAudited === 0 && r.currentIncome === 0 && r.priorAudited === 0) {
        return r
      }
      filled += 1
      return enrichRow({ ...r, currentIncome, priorAudited })
    })
    persist()
    lastPullSummary.value =
      filled > 0
        ? `已从 G11-1 带入 ${filled} 行本期/上期审定数（发生额①、审定数④）`
        : 'G11-1 暂无可带入分项金额，请先在审定表填写未审/调整数'
    if (filled > 0) ElMessage.success(lastPullSummary.value)
    else ElMessage.info(lastPullSummary.value)
    return filled
  }

  /** 从试算表带入持有期间项目的期初/期末余额（平均投资基数） */
  async function pullBalancesFromTb(): Promise<number> {
    if (opts.isReadonly.value) return 0
    const projectId = opts.projectId?.value
    const year = _auditYearRef.value
    if (!projectId || year == null) {
      ElMessage.warning('缺少项目或审计年度，无法从试算表取数')
      return 0
    }
    tbLoading.value = true
    try {
      const [curList, priorList] = await Promise.all([
        fetchTrialBalanceByPrefix(projectId, year, '15'),
        fetchTrialBalanceByPrefix(projectId, year - 1, '15').catch(() => [] as G11TbRowLike[]),
      ])
      const currentYearRows = curList as G11TbRowLike[]
      const priorYearRows = (priorList?.length ? priorList : null) as G11TbRowLike[] | null

      let filled = 0
      let continuityCount = 0
      const hitLabels: string[] = []
      rows.value = rows.value.map((r) => {
        const patch = buildBalancePatchFromTb(r.rowKey, currentYearRows, priorYearRows)
        if (!patch) return r
        filled += 1
        if (patch.usedPriorContinuity) continuityCount += 1
        if (!hitLabels.includes(patch.sourceLabel)) hitLabels.push(patch.sourceLabel)
        return enrichRow({
          ...r,
          currentOpening: patch.currentOpening,
          currentClosing: patch.currentClosing,
          priorOpening: patch.priorOpening,
          priorClosing: patch.priorClosing,
        })
      })
      persist()

      if (filled > 0) {
        lastTbPullSummary.value =
          `已从 TB 带入 ${filled} 行余额（${hitLabels.join('、')}）` +
          (continuityCount > 0 ? `；其中 ${continuityCount} 行上期无 TB，按本期期初作上期期末` : '')
        ElMessage.success(lastTbPullSummary.value)
      } else {
        lastTbPullSummary.value = '试算表未匹配到投资类科目余额；处置/一次性利得行不自动带入'
        ElMessage.info(lastTbPullSummary.value)
      }
      return filled
    } catch {
      ElMessage.warning('试算表取数失败，请检查网络或手工填写期初/期末')
      return 0
    } finally {
      tbLoading.value = false
    }
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value) return
    aiLoading.value = true
    try {
      const abnormal = rows.value.filter((r) => r.abnormalHighlight)
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g11/ai/return-rate-conclusion`,
        {
          existingContent: conclusion.value,
          rows: abnormal,
          relatedContext: {
            abnormalCount: abnormal.length,
            missingNotes: abnormal.filter((r) => !r.abnormalNote.trim()).length,
            thresholdPp: G11_RETURN_RATE_CHANGE_THRESHOLD * 100,
            totalCurrentIncome: totals.value.currentIncome,
            totalPriorAudited: totals.value.priorAudited,
            adjCrossDiff: adjCrossCheck.value.diff,
            adjMismatched: adjCrossCheck.value.mismatched,
          },
        },
        { _silent: true } as any,
      )
      const text = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (text) updateConclusion(text)
      else updateConclusion(buildLocalConclusion(rows.value))
    } catch {
      updateConclusion(buildLocalConclusion(rows.value))
    } finally {
      aiLoading.value = false
    }
  }

  const abnormalCount = computed(() => rows.value.filter((r) => r.abnormalHighlight).length)
  const missingNoteCount = computed(() => rows.value.filter((r) => r.noteRequired).length)

  /** G11-4 本期发生额合计 vs G11-1 审定合计勾稽 */
  const adjCrossCheck = computed(() => {
    const store = parseG11AdjStore(opts.allResponses.value.get(ITEM_ID_ADJ_ROWS)?.remark)
    let adjTotal = 0
    for (const def of G11_RETURN_RATE_ITEMS) {
      const adj = store[def.rowKey]
      if (!adj) continue
      adjTotal += calcAdjustedAmount(
        parseNum(adj.currentUnadjusted),
        parseNum(adj.currentAdjustment),
      )
    }
    const rrTotal = calcSubtotal(rows.value.map((r) => r.currentIncome))
    const diff = Math.round((rrTotal - adjTotal) * 100) / 100
    return { adjTotal, rrTotal, diff, mismatched: Math.abs(diff) > 0.01 && adjTotal !== 0 }
  })

  const totals = computed(() => {
    const currentIncome = calcSubtotal(rows.value.map((r) => r.currentIncome))
    const priorAudited = calcSubtotal(rows.value.map((r) => r.priorAudited))
    const currentOpening = calcSubtotal(rows.value.map((r) => r.currentOpening))
    const currentClosing = calcSubtotal(rows.value.map((r) => r.currentClosing))
    const priorOpening = calcSubtotal(rows.value.map((r) => r.priorOpening))
    const priorClosing = calcSubtotal(rows.value.map((r) => r.priorClosing))
    const currentAvgBalance = calcAverageBalance(currentOpening, currentClosing)
    const priorAvgBalance = calcAverageBalance(priorOpening, priorClosing)
    const currentReturnRate = calcReturnRate(currentIncome, currentAvgBalance)
    const priorReturnRate = calcReturnRate(priorAudited, priorAvgBalance)
    const returnRateChange = calcReturnRateChange(currentReturnRate, priorReturnRate)
    return {
      currentIncome,
      priorAudited,
      currentOpening,
      currentClosing,
      priorOpening,
      priorClosing,
      currentAvgBalance,
      priorAvgBalance,
      currentReturnRate,
      priorReturnRate,
      returnRateChange,
      abnormalHighlight: isReturnRateChangeExceeding(
        returnRateChange,
        G11_RETURN_RATE_CHANGE_THRESHOLD,
      ),
    }
  })

  return {
    rows,
    conclusion,
    auditNote,
    aiLoading,
    tbLoading,
    abnormalCount,
    missingNoteCount,
    totals,
    adjCrossCheck,
    lastPullSummary,
    lastTbPullSummary,
    conclusionTemplates: G11_RETURN_RATE_CONCLUSION_TEMPLATES,
    updateRow,
    updateBalance,
    addRow,
    removeRow,
    updateConclusion,
    updateAuditNote,
    applyConclusionTemplate,
    pullFromAdjudication,
    pullBalancesFromTb,
    generateAiConclusion,
    reloadFromStore,
  }
}

/** 纯函数：供单测验证从审定 store 映射到收益率行 */
export function mapAdjStoreToReturnRatePatch(
  rowKey: string,
  store: ReturnType<typeof parseG11AdjStore>,
): { currentIncome: number; priorAudited: number } | null {
  const adj = store[rowKey]
  if (!adj) return null
  return {
    currentIncome: calcAdjustedAmount(
      parseNum(adj.currentUnadjusted),
      parseNum(adj.currentAdjustment),
    ),
    priorAudited: calcAdjustedAmount(
      parseNum(adj.priorUnadjusted),
      parseNum(adj.priorAdjustment),
    ),
  }
}
