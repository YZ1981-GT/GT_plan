/**
 * H8-9 对方底稿折旧数反向拉取
 *
 * 优先匹配「使用权资产折旧 / 租赁折旧」，避免误取固定资产折旧行。
 * 营业成本→D5；制造费用→F2；销售→K8；管理→K9；研发→I6。
 */
import { api } from '@/services/apiProxy'

export type H8CounterpartField =
  | 'operatingCost'
  | 'manufacturing'
  | 'selling'
  | 'admin'
  | 'rd'

export interface H8CounterpartAmount {
  field: H8CounterpartField
  wpCode: string
  amount: number | null
  matchedLabel: string
  sourceItemId: string
  status: 'ok' | 'wp_missing' | 'item_missing' | 'row_missing' | 'error'
  message: string
}

function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

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

function findInRows(
  rows: any[],
  keywords: string[],
): { amount: number; label: string } | null {
  for (const kw of keywords) {
    const exact = rows.find((r) => rowName(r) === kw)
    if (exact) return { amount: rowAmount(exact), label: rowName(exact) }
  }
  for (const r of rows) {
    const n = rowName(r)
    if (keywords.some((k) => n.includes(k))) return { amount: rowAmount(r), label: n }
  }
  return null
}

interface PullSpec {
  field: H8CounterpartField
  wpCode: string
  itemIds: string[]
  keywords: string[]
}

/** 关键词优先使用权资产/租赁，再回退通用「折旧」 */
const PULL_SPECS: PullSpec[] = [
  {
    field: 'operatingCost',
    wpCode: 'D5',
    itemIds: ['D5-2-detail-rows', 'D5-1-adj-main-rows', 'D5-2-rows'],
    keywords: ['使用权资产折旧', '租赁折旧', '折旧费', '折旧'],
  },
  {
    field: 'manufacturing',
    wpCode: 'F2',
    itemIds: ['F2-43-rows'],
    keywords: ['使用权资产折旧', '租赁折旧', '折旧费', '折旧'],
  },
  {
    field: 'selling',
    wpCode: 'K8',
    itemIds: ['K8-2-detail-rows'],
    keywords: ['使用权资产折旧', '租赁折旧', '折旧费', '折旧'],
  },
  {
    field: 'admin',
    wpCode: 'K9',
    itemIds: ['K9-2-detail-rows'],
    keywords: ['使用权资产折旧', '租赁折旧', '折旧费', '折旧'],
  },
  {
    field: 'rd',
    wpCode: 'I6',
    itemIds: ['I6-2-detail-rows'],
    keywords: ['使用权资产折旧', '租赁折旧', '折旧费', '折旧'],
  },
]

export async function pullH8DepAllocCounterparts(
  projectId: string,
): Promise<Record<H8CounterpartField, H8CounterpartAmount>> {
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

  const result = {} as Record<H8CounterpartField, H8CounterpartAmount>

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
          ? `${spec.wpCode} 已加载但未找到使用权资产折旧行`
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

export default pullH8DepAllocCounterparts
