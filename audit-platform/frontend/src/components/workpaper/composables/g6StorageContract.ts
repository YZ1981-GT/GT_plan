/**
 * g6StorageContract — G6 套件规范存储契约
 *
 * 规范：结构化 JSON 以 conclusion 为准写入，并双写 remark 兼容；
 * 读取 conclusion 优先，fallback remark。
 */
import type { ChecklistResponse } from './useF1FormData'

export const G6_STORAGE_SCHEMA_VERSION = 1

/** 主要行表 / 结构化 payload 的 item_id */
export const G6_ITEM_IDS = {
  G6_1_ROWS: 'G6-1-rows',
  G6_1_CLASSIFICATION_SUMMARY: 'G6-1-classification-summary',
  G6_2_ROWS: 'G6-2-rows',
  G6_2_BALANCE_SHEET_DATE: 'G6-2-balance-sheet-date',
  G6_3_ROWS: 'G6-3-rows',
  G6_4_ROWS: 'G6-4-rows',
  G6_SPPI_CLASSIFICATION_SUMMARY: 'G6-sppi-classification-summary',
  G6_11_ROWS: 'G6-11-rows',
  G6_12_DATA: 'G6-12-impairment-calc-data',
  G6_12_ROWS: 'G6-12-rows',
  G6_13_MEASUREMENT: 'G6-13-ecl-measurement',
  G6_14_DATA: 'G6-14-reversal-writeoff-data',
  G6_14_ROWS: 'G6-14-rows',
  G6_15_ROWS: 'G6-15-rows',
  G6_15_CRITERIA: 'G6-15-criteria',
  G6_15_NOTE: 'G6-15-audit-note',
  G6_15_CONCLUSION: 'G6-15-audit-conclusion',
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

/** 结构化 payload 双写（conclusion + remark 同文） */
export function buildCanonicalPayload(value: unknown): Pick<ChecklistResponse, 'conclusion' | 'remark'> {
  const json = typeof value === 'string' ? value : JSON.stringify(value)
  return { conclusion: json, remark: json }
}

export function parseCanonicalJson<T = any>(
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
