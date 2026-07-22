/**
 * H1-13 对方底稿折旧数反向拉取
 *
 * 从 K8/K9/I6/F2/F5 的 checklist_responses 中按行名匹配「折旧费」等，
 * 供 H1-13 勾稽核对表回填「对方底稿数」并自动算差异。
 */
import { api } from '@/services/apiProxy'

export type CounterpartField =
  | 'productionCost'
  | 'manufacturing'
  | 'selling'
  | 'admin'
  | 'rd'

export interface CounterpartAmount {
  field: CounterpartField
  wpCode: string
  amount: number | null
  /** 命中行标签，便于审计说明 */
  matchedLabel: string
  sourceItemId: string
  status: 'ok' | 'wp_missing' | 'item_missing' | 'row_missing' | 'error'
  message: string
}

function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 兼容纯数组 / { rows: [...] } 矩阵 / 嵌套 JSON 字符串 */
function extractRows(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  let data: any = raw
  if (typeof raw === 'string' && raw.trim()) {
    try {
      data = JSON.parse(raw)
    } catch {
      return []
    }
  }
  if (Array.isArray(data)) return data
  if (data && typeof data === 'object') {
    if (Array.isArray(data.rows)) return data.rows
    if (Array.isArray(data.items)) return data.items
  }
  return []
}

async function resolveWpId(projectId: string, wpCode: string): Promise<string | null> {
  try {
    const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: wpCode },
      _silent: true,
    } as any)
    return (idRes as any)?.wp_id ?? (idRes as any)?.data?.wp_id ?? null
  } catch {
    return null
  }
}

async function loadResponses(wpId: string): Promise<Map<string, any>> {
  const map = new Map<string, any>()
  try {
    const res = await api.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    for (const item of list) {
      if (item?.item_id) map.set(item.item_id, item)
    }
  } catch { /* ignore */ }
  return map
}

function rowName(row: any): string {
  return String(
    row?.accountName
    ?? row?.category
    ?? row?.label
    ?? row?.name
    ?? row?.itemName
    ?? row?.costItem
    ?? '',
  ).trim()
}

function rowAmount(row: any): number {
  // 优先审定数，其次合计/未审
  const candidates = [
    row?.audited,
    row?.auditedAmount,
    row?.total,
    row?.unadjTotal,
    row?.amount,
    row?.actualAmt,
  ]
  for (const c of candidates) {
    if (c != null && c !== '' && Number.isFinite(Number(c))) return parseNum(c)
  }
  return 0
}

function nameMatches(name: string, keywords: string[]): boolean {
  if (!name) return false
  return keywords.some((k) => name.includes(k))
}

function findInRows(
  rows: any[],
  keywords: string[],
): { amount: number; label: string } | null {
  // 精确优先，再模糊
  for (const kw of keywords) {
    const exact = rows.find((r) => rowName(r) === kw)
    if (exact) return { amount: rowAmount(exact), label: rowName(exact) }
  }
  for (const r of rows) {
    const n = rowName(r)
    if (nameMatches(n, keywords)) return { amount: rowAmount(r), label: n }
  }
  // F2-43 matrix: key === 'depreciation'
  const byKey = rows.find((r) => r?.key === 'depreciation')
  if (byKey && keywords.some((k) => k.includes('折旧'))) {
    return { amount: rowAmount(byKey), label: rowName(byKey) || '折旧费' }
  }
  return null
}

interface PullSpec {
  field: CounterpartField
  wpCode: string
  itemIds: string[]
  keywords: string[]
}

const PULL_SPECS: PullSpec[] = [
  {
    field: 'selling',
    wpCode: 'K8',
    itemIds: ['K8-2-detail-rows'],
    keywords: ['折旧费', '固定资产折旧', '折旧'],
  },
  {
    field: 'admin',
    wpCode: 'K9',
    itemIds: ['K9-2-detail-rows'],
    keywords: ['折旧费', '固定资产折旧', '折旧'],
  },
  {
    field: 'rd',
    wpCode: 'I6',
    itemIds: ['I6-2-detail-rows'],
    keywords: ['折旧费', '固定资产折旧', '折旧'],
  },
  {
    field: 'manufacturing',
    wpCode: 'F2',
    itemIds: ['F2-43-rows'],
    keywords: ['折旧费', '固定资产折旧', '折旧'],
  },
  {
    field: 'productionCost',
    wpCode: 'F5',
    itemIds: ['F5-1-adj-main-rows', 'F5-1-adj-other-rows', 'F5-2-detail-rows'],
    keywords: ['生产成本折旧', '固定资产折旧', '折旧费', '折旧'],
  },
]

/**
 * 并行拉取各对方底稿折旧行金额。
 * 同一 wpCode 只请求一次 checklist-responses。
 */
export async function pullH1DepAllocCounterparts(
  projectId: string,
): Promise<Record<CounterpartField, CounterpartAmount>> {
  const wpCodes = [...new Set(PULL_SPECS.map((s) => s.wpCode))]
  const wpIdMap = new Map<string, string | null>()
  const respMap = new Map<string, Map<string, any>>()

  await Promise.all(
    wpCodes.map(async (code) => {
      const wpId = await resolveWpId(projectId, code)
      wpIdMap.set(code, wpId)
      if (wpId) respMap.set(code, await loadResponses(wpId))
    }),
  )

  const result = {} as Record<CounterpartField, CounterpartAmount>

  for (const spec of PULL_SPECS) {
    const wpId = wpIdMap.get(spec.wpCode)
    if (!wpId) {
      result[spec.field] = {
        field: spec.field,
        wpCode: spec.wpCode,
        amount: null,
        matchedLabel: '',
        sourceItemId: '',
        status: 'wp_missing',
        message: `未找到底稿 ${spec.wpCode}`,
      }
      continue
    }

    const responses = respMap.get(spec.wpCode) ?? new Map()
    let found: { amount: number; label: string; itemId: string } | null = null

    for (const itemId of spec.itemIds) {
      const item = responses.get(itemId)
      if (!item) continue
      const list = extractRows(item.remark ?? item.conclusion)
      const hit = findInRows(list, spec.keywords)
      if (hit) {
        found = { ...hit, itemId }
        break
      }
    }

    if (!found) {
      const anyItem = spec.itemIds.some((id) => responses.has(id))
      result[spec.field] = {
        field: spec.field,
        wpCode: spec.wpCode,
        amount: null,
        matchedLabel: '',
        sourceItemId: '',
        status: anyItem ? 'row_missing' : 'item_missing',
        message: anyItem
          ? `${spec.wpCode} 已加载但未找到折旧行`
          : `${spec.wpCode} 无明细数据`,
      }
      continue
    }

    result[spec.field] = {
      field: spec.field,
      wpCode: spec.wpCode,
      amount: found.amount,
      matchedLabel: found.label,
      sourceItemId: found.itemId,
      status: 'ok',
      message: `已取 ${spec.wpCode}/${found.label}`,
    }
  }

  return result
}

export default pullH1DepAllocCounterparts
