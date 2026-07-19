/**
 * g4StorageContract — G4 套件规范存储契约
 *
 * 规范：表格/结构化 JSON 以 `conclusion` 为准写入；
 * 兼容读取旧 `remark`（conclusion 优先）。
 * 文本类（审计说明/结论正文）仍可走 remark，但表格 payload 一律 conclusion。
 */
import type { ChecklistResponse } from './useF1FormData'

export const G4_STORAGE_SCHEMA_VERSION = 1

/** 主要行表 / 结构化 payload 的 item_id */
export const G4_ITEM_IDS = {
  G4_1_ROWS: 'G4-1-rows',
  G4_2_ROWS: 'G4-2-rows',
  G4_3_ROWS: 'G4-3-rows',
  G4_4_INTEREST: 'G4-4-interest-calc',
  G4_4_ROWS: 'G4-4-rows', // 导入导出兼容键
  G4_4_BENCHMARK: 'G4-4-interest-benchmark',
  G4_5_QUESTIONNAIRE: 'G4-5-questionnaire',
  G4_5_CONCLUSION: 'G4-5-audit-conclusion',
  G4_6_BOND: 'G4-6-bond-items',
  G4_6_OVERALL: 'G4-6-overall-conclusion',
  G4_7_HEADER: 'G4-7-header',
  G4_7_ITEMS: 'G4-7-items',
  G4_7_CONCLUSION: 'G4-7-audit-conclusion',
  G4_8_HEADER: 'G4-8-header',
  G4_8_ITEMS: 'G4-8-items',
  G4_8_CONCLUSION: 'G4-8-audit-conclusion',
  G4_9_ROWS: 'G4-9-rows',
  G4_10_ROWS: 'G4-10-rows',
  G4_11_MEASUREMENT: 'G4-11-ecl-measurement',
  G4_12_ROWS: 'G4-12-rows',
  G4_12_REVERSALS: 'G4-12-reversals',
  G4_12_WRITEOFFS: 'G4-12-writeoffs',
  G4_13_ROWS: 'G4-13-rows',
  G4_13_CRITERIA: 'G4-13-sample-criteria',
} as const

/** 信用减值损失科目：项目可配置，默认 6702 */
export const G4_CREDIT_LOSS_ACCOUNT_DEFAULT = {
  code: '6702',
  name: '信用减值损失',
} as const

export const G4_CREDIT_LOSS_CONFIG_KEY = 'G4-credit-loss-account'

export interface G4CreditLossAccountConfig {
  code: string
  name: string
}

export function resolveCreditLossAccount(
  allResponses?: Map<string, ChecklistResponse> | null,
): G4CreditLossAccountConfig {
  const raw = allResponses?.get(G4_CREDIT_LOSS_CONFIG_KEY)
  const src = raw?.conclusion || raw?.remark
  if (src) {
    try {
      const parsed = JSON.parse(src) as Partial<G4CreditLossAccountConfig>
      if (parsed?.code) {
        return {
          code: String(parsed.code),
          name: String(parsed.name || G4_CREDIT_LOSS_ACCOUNT_DEFAULT.name),
        }
      }
    } catch { /* ignore */ }
  }
  return { ...G4_CREDIT_LOSS_ACCOUNT_DEFAULT }
}

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

/**
 * 规范写入：主字段 conclusion；同步写 remark 做迁移期兼容（双写一代）。
 * 文本类单独用 buildTextPayload。
 */
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

/** 纯文本说明/结论：保留在 remark，conclusion 置空（避免与表格 JSON 混淆） */
export function buildTextPayload(itemId: string, text: string): ChecklistResponse {
  return {
    item_id: itemId,
    conclusion: null,
    remark: text ?? '',
  }
}

export function getResponse(
  map: Map<string, ChecklistResponse>,
  itemId: string,
): ChecklistResponse | undefined {
  return map.get(itemId)
}
