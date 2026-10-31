/**
 * 一致性检查项五态的统一读法与标签（需求 16.2 / 16.5，spec formula-hub-integrity-closure）。
 *
 * 后端 `GET /api/projects/{id}/workflow/consistency-check` 每项带 `status` 与 `reason`。
 * 「未执行（数据缺失）」「不适用」「检查异常」各有标签与原因，不显示「通过」。
 * 接口没给出（或给了认不出的）`status` 时按「检查异常」显示并写明原因，不按 `passed` 推断成「通过」——
 * 那正是面板原先自补「通过」的同一类做法。
 */
export type GateCheckStatus = 'passed' | 'failed' | 'not_executed' | 'not_applicable' | 'error'

export interface GateCheckLike {
  passed?: boolean
  status?: GateCheckStatus | string | null
  reason?: string | null
  details?: unknown
}

const KNOWN: readonly string[] = ['passed', 'failed', 'not_executed', 'not_applicable', 'error']

/** 接口没给出检查状态时显示的原因 */
export const MISSING_STATUS_REASON = '接口未返回检查状态'

function hasKnownStatus(check: GateCheckLike): boolean {
  return typeof check.status === 'string' && KNOWN.includes(check.status)
}

export function checkStatusOf(check: GateCheckLike): GateCheckStatus {
  return hasKnownStatus(check) ? (check.status as GateCheckStatus) : 'error'
}

const LABELS: Record<GateCheckStatus, string> = {
  passed: '通过',
  failed: '失败',
  not_executed: '未执行（数据缺失）',
  not_applicable: '不适用',
  error: '检查异常',
}

export function checkStatusLabel(check: GateCheckLike): string {
  return LABELS[checkStatusOf(check)]
}

/** 非通过项的原因：后端 `reason` 优先，没有再用字符串 `details`；状态缺失时说明接口没给状态。通过项返回空串。 */
export function checkReasonOf(check: GateCheckLike): string {
  if (!hasKnownStatus(check)) return MISSING_STATUS_REASON
  if (check.status === 'passed') return ''
  if (check.reason) return check.reason
  return typeof check.details === 'string' ? check.details : ''
}
