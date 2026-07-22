/**
 * G12-5 支持性证据结构化：类型推断、展示文案、索引候选
 */
import {
  G12_NET_EXPOSURE_EVIDENCE_TYPES,
  type G12NetExposureEvidenceType,
} from './g12Constants'
import type { ChecklistResponse } from './useF1FormData'

const TYPE_LABEL: Record<string, string> = Object.fromEntries(
  G12_NET_EXPOSURE_EVIDENCE_TYPES.map((t) => [t.value, t.label]),
)

const INFER_RULES: Array<{ type: G12NetExposureEvidenceType; re: RegExp }> = [
  { type: 'sales_budget', re: /预算|预测|forecast|budget/i },
  { type: 'order_contract', re: /订单|合同|订单合同|purchase.?order|contract/i },
  { type: 'hedge_designation', re: /指定|hedge.?designation|套期文档|书面文件/i },
  { type: 'board_approval', re: /董事会|决议|批准|approval|会议纪要/i },
  { type: 'valuation_doc', re: /估值|公允|valuation|定价/i },
  { type: 'bank_confirm', re: /银行|对账|confirm|询证/i },
]

export function evidenceTypeLabel(type: string): string {
  return TYPE_LABEL[type] || type || ''
}

/** 从自由文本推断证据类型（兼容历史仅填 supportingEvidence） */
export function inferEvidenceType(text: string): G12NetExposureEvidenceType | '' {
  const t = text.trim()
  if (!t) return ''
  for (const rule of INFER_RULES) {
    if (rule.re.test(t)) return rule.type
  }
  return 'other'
}

export function formatEvidenceDisplay(type: string, detail: string): string {
  const label = evidenceTypeLabel(type)
  const d = detail.trim()
  if (label && d) return `${label}：${d}`
  return label || d
}

export interface G12IndexSuggestion {
  value: string
  label: string
  source: 'G12-2' | 'G12-4' | 'G12-6' | 'self'
}

function pushUnique(
  map: Map<string, G12IndexSuggestion>,
  value: string,
  source: G12IndexSuggestion['source'],
  extra = '',
) {
  const v = value.trim()
  if (!v) return
  if (map.has(v)) return
  const label = extra ? `${v}（${source} · ${extra}）` : `${v}（${source}）`
  map.set(v, { value: v, label, source })
}

function parseJsonArray(raw: string | null | undefined): Record<string, unknown>[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

/** 从 G12-2/4/6 及本表已有索引收集可选索引号 */
export function collectG12NetExposureIndexSuggestions(
  allResponses: Map<string, ChecklistResponse>,
  selfIndexRefs: string[] = [],
): G12IndexSuggestion[] {
  const map = new Map<string, G12IndexSuggestion>()

  for (const r of parseJsonArray(allResponses.get('G12-hedge-detail-rows')?.remark)) {
    const idx = String(r.indexRef ?? '').trim()
    const item = String(r.item ?? '').trim()
    if (idx) {
      pushUnique(map, idx, 'G12-2', item)
      pushUnique(map, `G12-2/${idx}`, 'G12-2', item)
    }
    const rel = String(r.hedgeRelationId ?? '').trim()
    if (rel) pushUnique(map, rel, 'G12-2', item)
  }

  for (const r of parseJsonArray(allResponses.get('G12-fv-test-rows')?.remark)) {
    const rel = String(r.hedgeRelationId ?? '').trim()
    const name = String(r.instrumentName ?? r.itemName ?? '').trim()
    if (rel) {
      pushUnique(map, rel, 'G12-4', name)
      pushUnique(map, `G12-4/${rel}`, 'G12-4', name)
    }
  }

  for (const r of parseJsonArray(allResponses.get('G12-voucher-rows')?.remark)) {
    const idx = String(r.indexNo ?? r.indexRef ?? '').trim()
    const vno = String(r.voucherNo ?? '').trim()
    if (idx) pushUnique(map, idx, 'G12-6', vno)
    const rel = String(r.hedgeRelationId ?? '').trim()
    if (rel) pushUnique(map, rel, 'G12-6', vno)
  }

  for (const s of selfIndexRefs) {
    pushUnique(map, s, 'self')
  }

  // 常用底稿入口
  for (const base of ['G12-2', 'G12-4', 'G12-5', 'G12-6']) {
    pushUnique(map, base, 'self')
  }

  return [...map.values()]
}

export function buildG12NetExposureAiContext(opts: {
  rows: Array<{
    seq: number
    item: string
    currency: string
    netPosition: string
    evidenceType?: string
    supportingEvidence: string
    hedgingInstrument: string
    indexRef: string
    hedgeRelationId?: string
  }>
  incompleteCount: number
  crossIssues: Array<{ seq: number; kind: string; detail: string; item?: string }>
  crossSummary: string | null
  auditNote: string
  testObjective: string
}) {
  return {
    测试目标: opts.testObjective,
    行数: opts.rows.length,
    待完善行数: opts.incompleteCount,
    交叉差异数: opts.crossIssues.length,
    交叉验证摘要: opts.crossSummary || '无交叉差异',
    交叉问题: opts.crossIssues.slice(0, 12).map((i) => ({
      seq: i.seq,
      kind: i.kind,
      item: i.item,
      detail: i.detail,
    })),
    测试行摘要: opts.rows.slice(0, 20).map((r) => ({
      seq: r.seq,
      item: r.item,
      currency: r.currency,
      netPosition: r.netPosition,
      evidenceType: r.evidenceType || '',
      evidence: formatEvidenceDisplay(r.evidenceType || '', r.supportingEvidence),
      hedgingInstrument: r.hedgingInstrument,
      indexRef: r.indexRef,
      hedgeRelationId: r.hedgeRelationId || '',
    })),
    审计说明摘要: opts.auditNote.slice(0, 400),
  }
}
