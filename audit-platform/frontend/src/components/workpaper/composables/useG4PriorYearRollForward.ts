import { ref, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { confirmDangerous } from '@/utils/confirm'
import type { ChecklistResponse } from './useF1FormData'
import {
  G4_ITEM_IDS,
  buildCanonicalPayload,
  parseCanonicalArray,
  parseCanonicalJson,
} from './g4StorageContract'

export interface G4RollForwardChange {
  itemId: string
  label: string
  changedRows: number
  skippedRows: number
  payload: ChecklistResponse
}

export interface G4RollForwardPlan {
  priorWpId: string
  priorWpCode: string
  force: boolean
  changes: G4RollForwardChange[]
}

interface Options {
  projectId: Ref<string>
  wpId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  /** 优先使用：一次 PUT 写入全部结转变更 */
  saveBatch?: (items: ChecklistResponse[]) => Promise<void>
  confirm?: typeof confirmDangerous
}

const OPENING_FIELDS = [
  ['openingCost', 'closingCost'],
  ['openingInterestAdj', 'closingInterestAdj'],
  ['openingAccruedInterest', 'closingAccruedInterest'],
  ['openingSubtotal', 'closingSubtotal'],
  ['openingImpairment', 'closingImpairment'],
  ['openingAmortizedCost', 'amortizedCost'],
  ['openingOneYearDeduct', 'oneYearSubtotal'],
  ['openingAdjustment', 'closingAdjustment'],
  ['openingAdjusted', 'closingAudited'],
] as const

const TERM_FIELDS = [
  'faceValueTotal',
  'initialDate',
  'maturityDate',
  'purchasePrice',
  'transactionCost',
  'couponRate',
  'effectiveRate',
] as const

function populated(value: unknown): boolean {
  if (value == null) return false
  if (typeof value === 'number') return value !== 0
  return String(value).trim() !== ''
}

function rowKey(row: any): string {
  const stable = String(row?.crossSheetInvestmentId || '').trim()
  if (stable) return `id:${stable}`
  return String(row?.investProject || row?.projectName || '').trim()
}

function normalizeResponses(raw: any): Map<string, ChecklistResponse> {
  const source = raw?.data ?? raw
  const list = Array.isArray(source)
    ? source
    : Array.isArray(source?.items)
      ? source.items
      : Array.isArray(source?.responses)
        ? source.responses
        : null
  const map = new Map<string, ChecklistResponse>()
  if (list) {
    for (const item of list) {
      if (item?.item_id) map.set(item.item_id, item)
    }
    return map
  }
  const objectSource = source?.checklist_responses ?? source
  if (objectSource && typeof objectSource === 'object') {
    for (const [itemId, value] of Object.entries(objectSource)) {
      if (value && typeof value === 'object') {
        map.set(itemId, { item_id: itemId, ...(value as object) } as ChecklistResponse)
      }
    }
  }
  return map
}

function buildDetailRows(prior: any[], current: any[], force: boolean) {
  const currentByKey = new Map(current.map((row) => [rowKey(row), row]))
  let changedRows = 0
  let skippedRows = 0
  const result = [...current]

  for (const priorRow of prior) {
    const key = rowKey(priorRow)
    if (!key) continue
    const existing = currentByKey.get(key)
    const target = existing ?? {
      id: `${priorRow.id || key}-rf`,
      seq: result.length + 1,
      investCategory: priorRow.investCategory ?? '',
      investProject: priorRow.investProject ?? key.replace(/^id:/, ''),
      faceValue: priorRow.faceValue ?? 0,
      couponRate: priorRow.couponRate ?? 0,
      effectiveRate: priorRow.effectiveRate ?? 0,
      maturityDate: priorRow.maturityDate ?? '',
      crossSheetInvestmentId: priorRow.crossSheetInvestmentId || priorRow.id || undefined,
    }
    const patch: Record<string, unknown> = {}
    for (const [opening, closing] of OPENING_FIELDS) {
      if (!force && populated(target[opening])) continue
      patch[opening] = priorRow[closing] ?? 0
    }
    if (Object.keys(patch).length === 0) {
      skippedRows++
      continue
    }
    const next = { ...target, ...patch }
    if (existing) result[result.indexOf(existing)] = next
    else result.push(next)
    currentByKey.set(key, next)
    changedRows++
  }
  return { rows: result, changedRows, skippedRows }
}

function buildImpairmentRows(prior: any[], current: any[], force: boolean) {
  const currentByKey = new Map(current.map((row) => [rowKey(row), row]))
  let changedRows = 0
  let skippedRows = 0
  const result = [...current]
  for (const priorRow of prior) {
    const key = rowKey(priorRow)
    if (!key) continue
    const priorImpairment = priorRow.adjImpairment
      ?? priorRow.impairmentProvision
      ?? priorRow.closingImpairment
      ?? 0
    const existing = currentByKey.get(key)
    if (existing && !force && populated(existing.priorImpairment)) {
      skippedRows++
      continue
    }
    const next = existing
      ? { ...existing, priorImpairment }
      : {
          id: `${priorRow.id || key}-rf`,
          seq: result.length + 1,
          investProject: priorRow.investProject ?? key.replace(/^id:/, ''),
          stageGroup: priorRow.stageGroup ?? 'Stage1',
          priorImpairment,
          crossSheetInvestmentId: priorRow.crossSheetInvestmentId || priorRow.id || undefined,
        }
    if (existing) result[result.indexOf(existing)] = next
    else result.push(next)
    currentByKey.set(key, next)
    changedRows++
  }
  return { rows: result, changedRows, skippedRows }
}

function buildInterestGroups(prior: any[], current: any[], force: boolean) {
  const currentByKey = new Map(current.map((group) => [rowKey(group), group]))
  let changedRows = 0
  let skippedRows = 0
  const result = [...current]
  for (const priorGroup of prior) {
    const key = rowKey(priorGroup)
    if (!key) continue
    const existing = currentByKey.get(key)
    const initial = { ...(existing?.initial ?? {}) }
    let changed = false
    for (const field of TERM_FIELDS) {
      if (!force && populated(initial[field])) continue
      initial[field] = priorGroup.initial?.[field] ?? (typeof initial[field] === 'string' ? '' : 0)
      changed = true
    }
    if (!changed) {
      skippedRows++
      continue
    }
    const next = existing
      ? { ...existing, initial }
      : {
          id: `${priorGroup.id || key}-rf`,
          projectName: priorGroup.projectName ?? key,
          initial: { ...initial, initialCarryingAmount: 0 },
          periods: [],
        }
    if (existing) result[result.indexOf(existing)] = next
    else result.push(next)
    currentByKey.set(key, next)
    changedRows++
  }
  return { rows: result, changedRows, skippedRows }
}

export function useG4PriorYearRollForward(options: Options) {
  const loading = ref(false)
  const applying = ref(false)
  const preview = ref<G4RollForwardPlan | null>(null)

  async function fetchPriorResponses(priorMeta: any): Promise<Map<string, ChecklistResponse>> {
    const embedded = normalizeResponses(priorMeta?.checklist_responses ?? priorMeta?.responses)
    if (embedded.size > 0) return embedded
    if (!priorMeta?.wp_id) return embedded
    const raw = await api.get(`/api/workpapers/${priorMeta.wp_id}/checklist-responses`)
    return normalizeResponses(raw)
  }

  async function loadPreview(force = false): Promise<G4RollForwardPlan> {
    loading.value = true
    try {
      const priorMeta = await api.get<any>(
        `/api/projects/${options.projectId.value}/workpapers/${options.wpId.value}/prior-year`,
      )
      if (!priorMeta?.wp_id) throw new Error('未找到可结转的上年底稿')
      const prior = await fetchPriorResponses(priorMeta)
      const current = options.allResponses.value
      const changes: G4RollForwardChange[] = []

      const detail = buildDetailRows(
        parseCanonicalArray(prior.get(G4_ITEM_IDS.G4_2_ROWS)),
        parseCanonicalArray(current.get(G4_ITEM_IDS.G4_2_ROWS)),
        force,
      )
      if (detail.changedRows) changes.push({
        itemId: G4_ITEM_IDS.G4_2_ROWS,
        label: 'G4-2 期末转期初',
        changedRows: detail.changedRows,
        skippedRows: detail.skippedRows,
        payload: buildCanonicalPayload(G4_ITEM_IDS.G4_2_ROWS, detail.rows),
      })

      const impairment = buildImpairmentRows(
        parseCanonicalArray(prior.get(G4_ITEM_IDS.G4_10_ROWS)),
        parseCanonicalArray(current.get(G4_ITEM_IDS.G4_10_ROWS)),
        force,
      )
      if (impairment.changedRows) changes.push({
        itemId: G4_ITEM_IDS.G4_10_ROWS,
        label: 'G4-10 上期减值',
        changedRows: impairment.changedRows,
        skippedRows: impairment.skippedRows,
        payload: buildCanonicalPayload(G4_ITEM_IDS.G4_10_ROWS, impairment.rows),
      })

      const interest = buildInterestGroups(
        parseCanonicalJson<any[]>(prior.get(G4_ITEM_IDS.G4_4_INTEREST)) ?? [],
        parseCanonicalJson<any[]>(current.get(G4_ITEM_IDS.G4_4_INTEREST)) ?? [],
        force,
      )
      if (interest.changedRows) changes.push({
        itemId: G4_ITEM_IDS.G4_4_INTEREST,
        label: 'G4-4 工具条款',
        changedRows: interest.changedRows,
        skippedRows: interest.skippedRows,
        payload: buildCanonicalPayload(G4_ITEM_IDS.G4_4_INTEREST, interest.rows),
      })

      preview.value = {
        priorWpId: priorMeta.wp_id,
        priorWpCode: priorMeta.wp_code || 'G4',
        force,
        changes,
      }
      return preview.value
    } finally {
      loading.value = false
    }
  }

  async function applyPreview(plan = preview.value): Promise<boolean> {
    if (!plan || plan.changes.length === 0) return false
    const total = plan.changes.reduce((sum, item) => sum + item.changedRows, 0)
    const detail = plan.changes
      .map((item) => `${item.label} ${item.changedRows} 行${item.skippedRows ? `（跳过 ${item.skippedRows} 行）` : ''}`)
      .join('；')
    await (options.confirm ?? confirmDangerous)({
      title: '确认上年结转',
      message: `结转预览：${detail}。合计 ${total} 行。${plan.force ? '本次将覆盖已填期初字段。' : '已填期初字段不会被覆盖。'}`,
      confirmText: '确认结转',
    })
    applying.value = true
    try {
      for (const change of plan.changes) {
        options.allResponses.value.set(change.itemId, change.payload)
      }
      const payloads = plan.changes.map((change) => change.payload)
      if (options.saveBatch) {
        await options.saveBatch(payloads)
      } else {
        for (const change of plan.changes) {
          await options.saveImmediate(change.itemId, change.payload)
        }
      }
      return true
    } finally {
      applying.value = false
    }
  }

  return { loading, applying, preview, loadPreview, applyPreview }
}

