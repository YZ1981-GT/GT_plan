/** ACNR 持久版本锁的 409 错误解析。 */
import type { AcnrResolveResult } from './useAcnr'

export const ACNR_REGISTRY_ERROR_CODES = {
  ACNR_REGISTRY_SNAPSHOT_MISSING: 'snapshot_missing',
  ACNR_REGISTRY_SNAPSHOT_INVALID: 'snapshot_invalid',
  ACNR_REGISTRY_LOCK_FAILED: 'lock_failed',
} as const

export type AcnrRegistryFailure = typeof ACNR_REGISTRY_ERROR_CODES[keyof typeof ACNR_REGISTRY_ERROR_CODES]

function responseData(error: unknown): Record<string, unknown> | null {
  const response = (error as { response?: { status?: number; data?: unknown } })?.response
  if (response?.status !== 409 || !response.data || typeof response.data !== 'object') return null
  return response.data as Record<string, unknown>
}

export function parseAcnrRegistryFailure(error: unknown): AcnrResolveResult | null {
  const data = responseData(error)
  if (!data) return null
  const detail = data.detail && typeof data.detail === 'object' ? data.detail as Record<string, unknown> : null
  const wireCode = String(data.error_code ?? detail?.error_code ?? '') as keyof typeof ACNR_REGISTRY_ERROR_CODES
  const code = ACNR_REGISTRY_ERROR_CODES[wireCode]
  if (!code) return null
  const message = data.message ?? detail?.message ?? (typeof data.detail === 'string' ? data.detail : '')
  return {
    found: false,
    error: code,
    reason: typeof message === 'string' && message ? message : '地址目录版本不可用，请联系管理员处理',
  }
}

export function isAcnrRegistryFailure(result: Pick<AcnrResolveResult, 'error'> | null | undefined): boolean {
  return result?.error === 'snapshot_missing' || result?.error === 'snapshot_invalid' || result?.error === 'lock_failed'
}
