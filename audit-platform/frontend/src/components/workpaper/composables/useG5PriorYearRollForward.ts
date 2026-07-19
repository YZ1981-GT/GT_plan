/**
 * useG5PriorYearRollForward — G5 上年结转
 * G5-2：上年 agingAudited → 本期 agingPrior
 * G5-3：上年期末审定 → 本期 openingUnadjusted
 */
import { ref, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { confirmDangerous } from '@/utils/confirm'
import type { ChecklistResponse } from './useF1FormData'
import {
  G5_ITEM_IDS,
  buildCanonicalPayload,
  parseCanonicalArray,
} from './g5StorageContract'
import { closingAuditedOfLeaf } from './g5SuiteStatus'

export interface G5RollForwardChange {
  itemId: string
  label: string
  changedRows: number
  skippedRows: number
  payload: ChecklistResponse
}

export interface G5RollForwardPlan {
  priorWpId: string
  priorWpCode: string
  force: boolean
  changes: G5RollForwardChange[]
}

interface Options {
  projectId: Ref<string>
  wpId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  saveBatch?: (items: ChecklistResponse[]) => Promise<void>
  confirm?: typeof confirmDangerous
}

function populated(value: unknown): boolean {
  if (value == null) return false
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).some((v) => populated(v))
  }
  return String(value).trim() !== ''
}

function balanceKey(row: any): string {
  const stable = String(row?.crossSheetReceivableId || '').trim()
  if (stable) return `id:${stable}`
  const debtor = String(row?.debtorName || '').trim()
  const contract = String(row?.contractNo || '').trim()
  if (debtor || contract) return `name:${debtor}|${contract}`
  return ''
}

function badDebtKey(row: any): string {
  const stable = String(row?.crossSheetReceivableId || '').trim()
  if (stable) return `id:${stable}`
  const category = String(row?.category || row?.provisionMethod || '').trim()
  const item = String(row?.item || row?.debtorOrGroup || '').trim()
  if (category || item) return `name:${category}|${item}`
  return ''
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

export function buildG52RollForward(prior: any[], current: any[], force: boolean) {
  const currentByKey = new Map(current.map((row) => [balanceKey(row), row]))
  let changedRows = 0
  let skippedRows = 0
  const result = [...current]

  for (const priorRow of prior) {
    const key = balanceKey(priorRow)
    if (!key) continue
    const existing = currentByKey.get(key)
    if (existing && !force && populated(existing.agingPrior)) {
      skippedRows++
      continue
    }
    const agingPrior = priorRow.agingAudited && typeof priorRow.agingAudited === 'object'
      ? { ...priorRow.agingAudited }
      : {}
    if (!populated(agingPrior) && existing) {
      skippedRows++
      continue
    }
    const next = existing
      ? {
          ...existing,
          agingPrior,
          crossSheetReceivableId:
            existing.crossSheetReceivableId
            || priorRow.crossSheetReceivableId
            || priorRow.id,
        }
      : {
          id: `${priorRow.id || key}-rf`,
          seq: result.length + 1,
          debtorName: priorRow.debtorName ?? '',
          businessType: priorRow.businessType ?? 'other',
          contractNo: priorRow.contractNo ?? '',
          startDate: priorRow.startDate ?? '',
          maturityDate: priorRow.maturityDate ?? '',
          isWithinOneYear: !!priorRow.isWithinOneYear,
          contractAmount: priorRow.contractAmount ?? 0,
          recoveredAmount: 0,
          closingBalance: 0,
          debitOccurrence: 0,
          creditOccurrence: 0,
          isRelatedParty: !!priorRow.isRelatedParty,
          unrealizedIncome: 0,
          netAmount: 0,
          agingPrior,
          agingCurrent: {},
          agingAudited: {},
          agingTotal: 0,
          remark: '',
          crossSheetReceivableId: priorRow.crossSheetReceivableId || priorRow.id,
        }
    if (existing) result[result.indexOf(existing)] = next
    else result.push(next)
    currentByKey.set(key, next)
    changedRows++
  }
  return { rows: result, changedRows, skippedRows }
}

export function buildG53RollForward(prior: any[], current: any[], force: boolean) {
  const currentByKey = new Map(current.map((row) => [badDebtKey(row), row]))
  let changedRows = 0
  let skippedRows = 0
  const result = [...current]

  for (const priorRow of prior) {
    const key = badDebtKey(priorRow)
    if (!key) continue
    const opening = closingAuditedOfLeaf(priorRow)
    const existing = currentByKey.get(key)
    if (existing && !force && populated(existing.openingUnadjusted)) {
      skippedRows++
      continue
    }
    const next = existing
      ? {
          ...existing,
          openingUnadjusted: opening,
          crossSheetReceivableId:
            existing.crossSheetReceivableId
            || priorRow.crossSheetReceivableId
            || priorRow.id,
        }
      : {
          id: `${priorRow.id || key}-rf`,
          seq: result.length + 1,
          category: priorRow.category === 'individual' || priorRow.provisionMethod === 'individual'
            ? 'individual'
            : 'portfolio',
          item: priorRow.item || priorRow.debtorOrGroup || '',
          portfolioType: priorRow.portfolioType || (priorRow.category === 'portfolio' ? 'business' : ''),
          openingUnadjusted: opening,
          openingAdjustment: 0,
          provisionIncrease: 0,
          otherIncrease: 0,
          reversal: 0,
          writeOff: 0,
          otherDecrease: 0,
          closingAdjustment: 0,
          reason: '',
          crossSheetReceivableId: priorRow.crossSheetReceivableId || priorRow.id,
        }
    if (existing) result[result.indexOf(existing)] = next
    else result.push(next)
    currentByKey.set(key, next)
    changedRows++
  }
  return { rows: result, changedRows, skippedRows }
}

export function useG5PriorYearRollForward(options: Options) {
  const loading = ref(false)
  const applying = ref(false)
  const preview = ref<G5RollForwardPlan | null>(null)

  async function fetchPriorResponses(priorMeta: any): Promise<Map<string, ChecklistResponse>> {
    const embedded = normalizeResponses(priorMeta?.checklist_responses ?? priorMeta?.responses)
    if (embedded.size > 0) return embedded
    if (!priorMeta?.wp_id) return embedded
    const raw = await api.get(`/api/workpapers/${priorMeta.wp_id}/checklist-responses`)
    return normalizeResponses(raw)
  }

  async function loadPreview(force = false): Promise<G5RollForwardPlan> {
    loading.value = true
    try {
      const priorMeta = await api.get<any>(
        `/api/projects/${options.projectId.value}/workpapers/${options.wpId.value}/prior-year`,
      )
      if (!priorMeta?.wp_id) throw new Error('未找到可结转的上年底稿')
      const prior = await fetchPriorResponses(priorMeta)
      const current = options.allResponses.value
      const changes: G5RollForwardChange[] = []

      const detail = buildG52RollForward(
        parseCanonicalArray(prior.get(G5_ITEM_IDS.G5_2_ROWS)),
        parseCanonicalArray(current.get(G5_ITEM_IDS.G5_2_ROWS)),
        force,
      )
      if (detail.changedRows) {
        changes.push({
          itemId: G5_ITEM_IDS.G5_2_ROWS,
          label: 'G5-2 账龄期初',
          changedRows: detail.changedRows,
          skippedRows: detail.skippedRows,
          payload: buildCanonicalPayload(G5_ITEM_IDS.G5_2_ROWS, detail.rows),
        })
      }

      const badDebt = buildG53RollForward(
        parseCanonicalArray(prior.get(G5_ITEM_IDS.G5_3_ROWS)),
        parseCanonicalArray(current.get(G5_ITEM_IDS.G5_3_ROWS)),
        force,
      )
      if (badDebt.changedRows) {
        changes.push({
          itemId: G5_ITEM_IDS.G5_3_ROWS,
          label: 'G5-3 坏账期初',
          changedRows: badDebt.changedRows,
          skippedRows: badDebt.skippedRows,
          payload: buildCanonicalPayload(G5_ITEM_IDS.G5_3_ROWS, badDebt.rows),
        })
      }

      preview.value = {
        priorWpId: priorMeta.wp_id,
        priorWpCode: priorMeta.wp_code || 'G5',
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
