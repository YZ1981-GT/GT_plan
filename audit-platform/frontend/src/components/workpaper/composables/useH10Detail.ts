/**
 * useH10Detail — H10-2 明细表（3 区段 Tab + 动态行）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { SOURCE_WP_OPTIONS, type H10SourceWp } from './h10Constants'
import { parseNum } from './useH10FormulaEngine'
import { calcDisposalGainLoss, calcNetBookValue } from './useH10DisposalCalcEngine'
import {
  scanH10ExcludedClassRows,
  summarizeH10ExcludedHits,
} from './h10ExcludedClassGuard'
import type { ChecklistResponse } from './useF1FormData'

export type H10DetailTab = 'basic' | 'disposal' | 'evidence'

export interface H10DetailRow {
  id: string
  seq: number
  assetName: string
  assetType: string
  sourceWp: H10SourceWp | string
  sourceIndex: string
  sourceRowRef: string
  originalCost: number
  accumulatedDepreciation: number
  impairmentProvision: number
  netBookValue: number
  disposalReason: string
  disposalMethod: string
  disposalIncome: number
  disposalExpenses: number
  disposalTax: number
  disposalGainLoss: number
  approvalDoc: string
  appraisalReport: string
  contractRef: string
  invoiceRef: string
  auditConclusion: string
  linkageId: string
  remark: string
  isLoss: boolean
}

const ITEM_ID_ROWS = 'H10-detail-rows'

function generateId(): string {
  return `h10d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function resolveSourceIndex(sourceWp: string): string {
  const hit = SOURCE_WP_OPTIONS.find((o) => o.value === sourceWp)
  return hit?.indexHint ?? ''
}

function enrichRow(raw: Partial<H10DetailRow> & { id?: string }, seq: number): H10DetailRow {
  const originalCost = parseNum(raw.originalCost)
  const accumulatedDepreciation = parseNum(raw.accumulatedDepreciation)
  const impairmentProvision = parseNum(raw.impairmentProvision ?? (raw as any).impairment)
  const netBookValue = calcNetBookValue(originalCost, accumulatedDepreciation, impairmentProvision)
  const disposalIncome = parseNum(raw.disposalIncome)
  const disposalExpenses = parseNum(raw.disposalExpenses)
  const disposalTax = parseNum(raw.disposalTax)
  const formulaGain = calcDisposalGainLoss(disposalIncome, netBookValue, disposalExpenses, disposalTax)
  // 跨底稿事件可能只给损益净额：无收入/原值时沿用传入值
  const hasCalcInputs = Math.abs(disposalIncome) > 0.005 || Math.abs(originalCost) > 0.005
  const disposalGainLoss = hasCalcInputs || raw.disposalGainLoss == null
    ? formulaGain
    : parseNum(raw.disposalGainLoss)
  const sourceWp = raw.sourceWp ?? 'OTHER'
  return {
    id: raw.id ?? generateId(),
    seq,
    assetName: raw.assetName ?? '',
    assetType: raw.assetType ?? '',
    sourceWp,
    sourceIndex: raw.sourceIndex ?? resolveSourceIndex(String(sourceWp)),
    sourceRowRef: raw.sourceRowRef ?? '',
    originalCost,
    accumulatedDepreciation,
    impairmentProvision,
    netBookValue,
    disposalReason: raw.disposalReason ?? '',
    disposalMethod: raw.disposalMethod ?? '',
    disposalIncome,
    disposalExpenses,
    disposalTax,
    disposalGainLoss,
    approvalDoc: raw.approvalDoc ?? '',
    appraisalReport: raw.appraisalReport ?? '',
    contractRef: raw.contractRef ?? '',
    invoiceRef: raw.invoiceRef ?? '',
    auditConclusion: raw.auditConclusion ?? '',
    linkageId: raw.linkageId ?? '',
    remark: raw.remark ?? '',
    isLoss: disposalGainLoss < 0,
  }
}

function parseRows(json: string | null | undefined): H10DetailRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r, i) => enrichRow(r, i + 1))
  } catch {
    return []
  }
}

export function useH10Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<H10DetailRow[]>([])
  const activeTab = ref<H10DetailTab>('basic')

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  function reseq(): void {
    rows.value = rows.value.map((r, i) => enrichRow(r, i + 1))
  }

  const statsSummary = computed(() => {
    const list = rows.value
    const totalIncome = list.reduce((s, r) => s + r.disposalIncome, 0)
    const totalGainLoss = list.reduce((s, r) => s + r.disposalGainLoss, 0)
    const profitCount = list.filter((r) => r.disposalGainLoss > 0).length
    const lossCount = list.filter((r) => r.disposalGainLoss < 0).length
    return {
      count: list.length,
      totalIncome,
      totalGainLoss,
      profitCount,
      lossCount,
    }
  })

  const sourceWpOptions = SOURCE_WP_OPTIONS

  const excludedClassHits = computed(() => scanH10ExcludedClassRows(rows.value))
  const excludedClassWarning = computed(() => summarizeH10ExcludedHits(excludedClassHits.value))

  function updateRow(id: string, patch: Partial<H10DetailRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrichRow({ ...r, ...patch }, r.seq) : r))
    persist()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入资产名称', '新增处置明细', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      if (!value?.trim()) return
      rows.value = [...rows.value, enrichRow({ assetName: value.trim() }, rows.value.length + 1)]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.id !== id)
    reseq()
    persist()
  }

  function loadRows(data: Partial<H10DetailRow>[]): void {
    rows.value = data.map((r, i) => enrichRow(r as H10DetailRow, i + 1))
    persist()
  }

  function createFromH6Event(payload: {
    assetName?: string
    assetType?: string
    disposalIncome?: number
    netBookValue?: number
    linkageId?: string
  }): void {
    if (opts.isReadonly.value) return
    const linkageId = payload.linkageId ?? `h6-${Date.now()}`
    if (linkageId && rows.value.some((r) => r.linkageId === linkageId)) return
    rows.value = [
      ...rows.value,
      enrichRow({
        assetName: payload.assetName ?? 'H6清理结转',
        assetType: payload.assetType ?? '固定资产',
        sourceWp: 'H6',
        disposalIncome: payload.disposalIncome,
        originalCost: payload.netBookValue,
        linkageId,
      }, rows.value.length + 1),
    ]
    persist()
  }

  /** 由主入口 EventBus 调用（H1~H8 disposal:source-updated） */
  function upsertFromSourceEvent(payload: {
    sourceWp?: string
    assetName?: string
    disposalGainLoss?: number
    sourceIndex?: string
    linkageId?: string
  }): void {
    if (opts.isReadonly.value) return
    const linkageId = payload.linkageId ?? `${payload.sourceWp}-${Date.now()}`
    const existingIdx = rows.value.findIndex((r) => r.linkageId === linkageId)
    const patch = enrichRow({
      ...(existingIdx >= 0 ? rows.value[existingIdx] : {}),
      assetName: payload.assetName ?? '',
      sourceWp: payload.sourceWp ?? 'OTHER',
      sourceIndex: payload.sourceIndex,
      disposalGainLoss: payload.disposalGainLoss,
      linkageId,
    }, existingIdx >= 0 ? rows.value[existingIdx].seq : rows.value.length + 1)
    if (existingIdx >= 0) {
      rows.value = rows.value.map((r, i) => (i === existingIdx ? patch : r))
    } else {
      rows.value = [...rows.value, patch]
    }
    persist()
  }

  const tabOptions = [
    { label: '基础信息', value: 'basic' },
    { label: '处置计算', value: 'disposal' },
    { label: '审计证据', value: 'evidence' },
  ] as const

  function reloadFromStore(): void {
    rows.value = parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark)
  }

  return {
    rows,
    activeTab,
    tabOptions,
    statsSummary,
    sourceWpOptions,
    excludedClassHits,
    excludedClassWarning,
    updateRow,
    addRow,
    removeRow,
    loadRows,
    reloadFromStore,
    createFromH6Event,
    upsertFromSourceEvent,
    ITEM_ID_ROWS,
  }
}
