export const CONSOL_PUSH_EVENTS = {
  pushed: 'consol.pushed',
  stale: 'consol.push_stale',
  failed: 'consol.push_failed',
} as const

export const CONSOL_PUSH_RUN_STATUS = {
  running: 'running',
  succeeded: 'succeeded',
  partial: 'partial',
  failed: 'failed',
} as const

export interface ConsolPushEventPayload {
  project_id?: string
  year?: number
  run_id?: string
  status?: string
  trigger?: string
  trigger_label?: string
  pushed_projects?: string[]
  warnings?: string[]
  source_project_id?: string
}

export function isCurrentConsolPushEvent(
  payload: ConsolPushEventPayload | null | undefined,
  projectId: string,
  year: number,
): boolean {
  return !!payload && payload.project_id === projectId && Number(payload.year) === Number(year)
}

export function pushEventMessage(payload: ConsolPushEventPayload, fallback: string): string {
  return payload.warnings?.[0] || fallback
}

export function isFailedPushStatus(status: string | null | undefined): boolean {
  return status === CONSOL_PUSH_RUN_STATUS.failed
}

export function isPartialPushStatus(status: string | null | undefined): boolean {
  return status === CONSOL_PUSH_RUN_STATUS.partial
}
