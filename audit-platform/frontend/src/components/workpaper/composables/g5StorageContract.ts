/**
 * g5StorageContract — G5 长期应收款规范存储契约
 *
 * 表格/结构化 JSON：conclusion 为准，remark 双写兼容。
 * 审计说明/结论正文：走 remark，conclusion 置空。
 */
import type { ChecklistResponse } from './useF1FormData'

export const G5_STORAGE_SCHEMA_VERSION = 1

export const G5_ITEM_IDS = {
  G5_1_ROWS: 'G5-1-rows',
  G5_2_ROWS: 'G5-2-rows',
  G5_3_ROWS: 'G5-3-rows',
  G5_4_ROWS: 'G5-4-rows',
  G5_5_ROWS: 'G5-5-rows',
  G5_6_ROWS: 'G5-6-rows',
  G5_7_ROWS: 'G5-7-rows',
  G5_8_POLICY: 'G5-8-policy',
  G5_9_ROWS: 'G5-9-rows',
  G5_10_ROWS: 'G5-10-rows',
  G5_11_ROWS: 'G5-11-rows',
  G5_12_VOUCHER: 'G5-12-voucher-check',
  G5_12_ROWS: 'G5-12-rows',
} as const

/** conclusion 优先，兼容 remark */
export function readCanonicalRaw(
  resp: { conclusion?: string | null; remark?: string | null } | undefined | null,
): string | null {
  if (!resp) return null
  const c = resp.conclusion
  if (c != null && String(c).trim() !== '') return String(c)
  const r = resp.remark
  if (r != null && String(r).trim() !== '') return String(r)
  return null
}

export function parseCanonicalJson<T = unknown>(
  resp: { conclusion?: string | null; remark?: string | null } | undefined | null,
): T | null {
  const raw = readCanonicalRaw(resp)
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export function parseCanonicalArray(
  resp: { conclusion?: string | null; remark?: string | null } | undefined | null,
): any[] {
  const parsed = parseCanonicalJson(resp)
  if (Array.isArray(parsed)) return parsed
  if (parsed && typeof parsed === 'object' && Array.isArray((parsed as any).rows)) {
    return (parsed as any).rows
  }
  return []
}

export function buildCanonicalPayload(
  itemId: string,
  value: unknown,
): ChecklistResponse {
  const json = typeof value === 'string' ? value : JSON.stringify(value)
  return {
    item_id: itemId,
    conclusion: json,
    remark: json,
  }
}

export function buildTextPayload(itemId: string, text: string): ChecklistResponse {
  return {
    item_id: itemId,
    conclusion: null,
    remark: text ?? '',
  }
}
