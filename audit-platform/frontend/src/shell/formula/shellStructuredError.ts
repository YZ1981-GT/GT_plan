/**
 * Structured shell errors + safe telemetry (formula-toolbar Task 12).
 *
 * Failures keep user work; UI gets Chinese structured reason.
 * Logs never include tokens, full formulas, or attachment bodies.
 */

export type ShellErrorDomain =
  | 'provider'
  | 'save'
  | 'review'
  | 'adapter'
  | 'location'
  | 'capability'
  | 'rail'

export interface ShellStructuredError {
  domain: ShellErrorDomain
  reasonCode: string
  zhMessage: string
  correlationId: string
  subjectKey: string | null
  operation: string | null
  provider: string | null
  ownerEpoch: number | null
  contextRevision: number | null
  capabilityEpoch: number | null
  /** Keep draft / in-progress work — never clear on error. */
  preserveWork: true
}

export interface ShellSafeLogRecord {
  correlationId: string
  subjectKey: string | null
  operation: string | null
  provider: string | null
  ownerEpoch: number | null
  capabilityEpoch: number | null
  verdict: 'error' | 'blocked' | 'partial'
  reasonCode: string
  /** Intentionally excludes expression / token / attachment body. */
}

const SENSITIVE_PATTERNS = [
  /Bearer\s+[A-Za-z0-9._\-]+/i,
  /token[=:]\s*\S+/i,
  /formula\s*=\s*.+/i,
  /表达式\s*[:=]\s*.+/i,
  /attachment[_-]?body/i,
  /-----BEGIN [A-Z ]+-----/,
]

export function containsSensitiveShellPayload(text: string | null | undefined): boolean {
  if (!text) return false
  return SENSITIVE_PATTERNS.some((re) => re.test(text))
}

export function createShellStructuredError(input: {
  domain: ShellErrorDomain
  reasonCode: string
  zhMessage: string
  correlationId?: string
  subjectKey?: string | null
  operation?: string | null
  provider?: string | null
  ownerEpoch?: number | null
  contextRevision?: number | null
  capabilityEpoch?: number | null
}): ShellStructuredError {
  if (containsSensitiveShellPayload(input.zhMessage)) {
    throw new Error('shell_error_zh_must_not_leak_sensitive_payload')
  }
  return {
    domain: input.domain,
    reasonCode: input.reasonCode,
    zhMessage: input.zhMessage,
    correlationId: input.correlationId ?? `shell-err-${Date.now().toString(36)}`,
    subjectKey: input.subjectKey ?? null,
    operation: input.operation ?? null,
    provider: input.provider ?? null,
    ownerEpoch: input.ownerEpoch ?? null,
    contextRevision: input.contextRevision ?? null,
    capabilityEpoch: input.capabilityEpoch ?? null,
    preserveWork: true,
  }
}

export function toShellSafeLog(error: ShellStructuredError): ShellSafeLogRecord {
  return {
    correlationId: error.correlationId,
    subjectKey: error.subjectKey,
    operation: error.operation,
    provider: error.provider,
    ownerEpoch: error.ownerEpoch,
    capabilityEpoch: error.capabilityEpoch,
    verdict: 'error',
    reasonCode: error.reasonCode,
  }
}

/**
 * Broad catch → success is forbidden. Callers must map failures to structured errors.
 */
export function assertNotBroadCatchSuccess(input: {
  caught: boolean
  reportedSuccess: boolean
}): { ok: boolean; reasonCode: string | null } {
  if (input.caught && input.reportedSuccess) {
    return { ok: false, reasonCode: 'broad_catch_success_forbidden' }
  }
  return { ok: true, reasonCode: null }
}
