/**
 * I1-9 对方底稿「无形资产摊销」反向拉取
 * 生产成本+制造费用→D5；销售→K8；管理→K9；研发→I6
 */
import { api } from '@/services/apiProxy'
import type { I1ExpenseField } from './useI1AmortizationAlloc'

export type I1CounterpartField = Extract<
  I1ExpenseField,
  'productionCost' | 'sellingExpense' | 'managementExpense' | 'rdExpense'
>

export interface I1CounterpartAmount {
  field: I1CounterpartField
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
    try { data = JSON.parse(raw) } catch { return [] }
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
    row?.accountName ?? row?.projectName ?? row?.category ?? row?.label ?? row?.name ?? row?.itemName ?? '',
  ).trim()
}

function rowAmount(row: any): number {
  const candidates = [
    row?.audited, row?.auditedAmount, row?.unadjTotal, row?.unadjusted,
    row?.total, row?.amount, row?.currentAmount,
  ]
  for (const c of candidates) {
    if (c != null && c !== '' && Number.isFinite(Number(c))) return parseNum(c)
  }
  return 0
}

function findInRows(rows: any[], keywords: string[]): { amount: number; label: string } | null {
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

const AMORT_KEYWORDS = ['无形资产摊销', '摊销费', '无形资产折旧及摊销']

const PULL_SPECS: Array<{
  field: I1CounterpartField
  wpCode: string
  itemIds: string[]
  keywords: string[]
}> = [
  {
    field: 'productionCost',
    wpCode: 'D5',
    itemIds: ['D5-2-detail-rows', 'D5-1-adj-main-rows', 'D5-2-rows'],
    keywords: [...AMORT_KEYWORDS, '摊销'],
  },
  {
    field: 'sellingExpense',
    wpCode: 'K8',
    itemIds: ['K8-2-detail-rows', 'K8-1-adj-rows'],
    keywords: [...AMORT_KEYWORDS, '折旧及摊销'],
  },
  {
    field: 'managementExpense',
    wpCode: 'K9',
    itemIds: ['K9-2-detail-rows', 'K9-1-adj-rows'],
    keywords: AMORT_KEYWORDS,
  },
  {
    field: 'rdExpense',
    wpCode: 'I6',
    itemIds: ['I6-2-detail-rows', 'I6-1-adj-rows'],
    keywords: AMORT_KEYWORDS,
  },
]

export async function pullI1AmortAllocCounterparts(
  projectId: string,
): Promise<Record<I1CounterpartField, I1CounterpartAmount>> {
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

  const result = {} as Record<I1CounterpartField, I1CounterpartAmount>

  for (const spec of PULL_SPECS) {
    const wpId = wpIdMap.get(spec.wpCode)
    if (!wpId) {
      result[spec.field] = {
        field: spec.field, wpCode: spec.wpCode, amount: null,
        matchedLabel: '', sourceItemId: '', status: 'wp_missing',
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
        field: spec.field, wpCode: spec.wpCode, amount: null,
        matchedLabel: '', sourceItemId: '',
        status: anyItem ? 'row_missing' : 'item_missing',
        message: anyItem
          ? `${spec.wpCode} 已加载但未找到无形资产摊销行`
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

/**
 * 将 I1-9 分配合计回写到对方底稿「无形资产摊销」行的未审数（并重算审定）。
 * 不覆盖 AJE/RJE；若找不到行则跳过。
 */
export async function pushI1AmortToExpenseWps(
  projectId: string,
  amounts: {
    productionManufacturing: number
    selling: number
    management: number
    rd: number
  },
): Promise<{ ok: number; skipped: number; messages: string[] }> {
  const targets: Array<{
    wpCode: string
    itemIds: string[]
    keywords: string[]
    amount: number
    label: string
  }> = [
    {
      wpCode: 'D5',
      itemIds: ['D5-2-detail-rows', 'D5-2-rows'],
      keywords: AMORT_KEYWORDS,
      amount: amounts.productionManufacturing,
      label: '生产成本+制造费用摊销',
    },
    {
      wpCode: 'K8',
      itemIds: ['K8-2-detail-rows'],
      keywords: [...AMORT_KEYWORDS, '折旧及摊销'],
      amount: amounts.selling,
      label: '销售费用摊销',
    },
    {
      wpCode: 'K9',
      itemIds: ['K9-2-detail-rows'],
      keywords: AMORT_KEYWORDS,
      amount: amounts.management,
      label: '管理费用摊销',
    },
    {
      wpCode: 'I6',
      itemIds: ['I6-2-detail-rows'],
      keywords: AMORT_KEYWORDS,
      amount: amounts.rd,
      label: '研发费用摊销',
    },
  ]

  let ok = 0
  let skipped = 0
  const messages: string[] = []

  for (const t of targets) {
    if (Math.abs(t.amount) < 0.005) {
      skipped++
      messages.push(`${t.wpCode} ${t.label}=0，跳过`)
      continue
    }
    const wpId = await resolveWpId(projectId, t.wpCode)
    if (!wpId) {
      skipped++
      messages.push(`未找到 ${t.wpCode}`)
      continue
    }
    const responses = await loadResponses(wpId)
    let written = false
    for (const itemId of t.itemIds) {
      const item = responses.get(itemId)
      if (!item) continue
      const list = extractRows(item.remark ?? item.conclusion)
      if (!list.length) continue

      let hitIdx = -1
      for (const kw of t.keywords) {
        hitIdx = list.findIndex((r) => rowName(r) === kw)
        if (hitIdx >= 0) break
      }
      if (hitIdx < 0) {
        hitIdx = list.findIndex((r) => t.keywords.some((k) => rowName(r).includes(k)))
      }
      if (hitIdx < 0) continue

      const row = { ...list[hitIdx] }
      // 写入未审发生额；保留 AJE/RJE。有月度列时写入 12 月以保证 SUM(months)=金额
      if (Array.isArray(row.months)) {
        const months = new Array(12).fill(0)
        months[11] = t.amount
        row.months = months
        row.unadjTotal = t.amount
        row.audited = t.amount + parseNum(row.aje) + parseNum(row.rje)
      } else if ('unadjTotal' in row || row.unadjTotal != null) {
        row.unadjTotal = t.amount
        row.audited = t.amount + parseNum(row.aje) + parseNum(row.rje)
      } else if ('unadjusted' in row || row.unadjusted != null) {
        row.unadjusted = t.amount
        row.audited = t.amount + parseNum(row.aje) + parseNum(row.rje)
      } else if ('unadjustedDebit' in row) {
        row.unadjustedDebit = t.amount
        row.unadjusted = t.amount
        row.audited = t.amount + parseNum(row.aje) + parseNum(row.rje)
      } else {
        row.amount = t.amount
        row.audited = t.amount
      }
      row._i1AmortPushedAt = new Date().toISOString()
      list[hitIdx] = row

      try {
        await api.put(`/api/workpapers/${wpId}/checklist-responses`, {
          items: [{ item_id: itemId, conclusion: null, remark: JSON.stringify(list) }],
        }, { _silent: true } as any)
        written = true
        ok++
        messages.push(`已回写 ${t.wpCode}/${rowName(row)} = ${t.amount.toFixed(2)}`)
        break
      } catch (e: any) {
        messages.push(`${t.wpCode} 回写失败: ${e?.message || e}`)
      }
    }
    if (!written) {
      skipped++
      messages.push(`${t.wpCode} 未找到可回写的摊销行`)
    }
  }

  return { ok, skipped, messages }
}

export default pullI1AmortAllocCounterparts
