/**
 * 委派被拒「被委派人看不到该循环」时，填写理由后带 `expand_scope` 重试一次。
 *
 * spec procedure-trim-generation-delegation-chain 需求 4.4 / ADR-8：底稿主编委派、程序委派、批量分配遇到被委派人的
 * 有效循环范围不含目标循环时返回 400，错误体
 * `{error: 'lead_delegation_rejected' | 'row_delegation_rejected', reason: 'out_of_scope', cycles, message}`；
 * 用户填写理由确认后，同一请求带 `expand_scope: true, scope_reason` 重试，后端同事务把缺少的循环加入其可见范围并记入
 * 委派历史。程序委派的预览凭证不会因 400 被消费，同一凭证可以重试。
 *
 * 调用方的请求须带 `_silent`（各 API 函数的 `silent` 选项），否则全局拦截器会先弹一次错误、再弹理由框；
 * 其他错误原样抛出，由调用方自己的 catch 提示。
 */
import { ElMessageBox } from 'element-plus'

export const DELEGATION_REJECTED_ERRORS: readonly string[] = ['lead_delegation_rejected', 'row_delegation_rejected']
export const OUT_OF_SCOPE = 'out_of_scope'

export interface DelegationRejection {
  error: string
  reason: string
  message: string
  cycles: string[]
}

/** 重试时附加的请求字段（首次为空对象） */
export interface ScopeExpansion {
  expand_scope?: boolean
  scope_reason?: string
}

export type ScopeRetryOutcome<T> =
  | { status: 'done'; result: T; expanded: boolean }
  | { status: 'cancelled' }

/** 从请求错误里取委派拒绝体；不是委派拒绝返回 null。 */
export function delegationRejection(e: any): DelegationRejection | null {
  const d = e?.response?.data?.detail ?? e?.response?.data?.data?.detail ?? e?.data?.detail
  if (!d || typeof d !== 'object' || !DELEGATION_REJECTED_ERRORS.includes(String(d.error))) return null
  return {
    error: String(d.error),
    reason: String(d.reason || ''),
    message: String(d.message || ''),
    cycles: Array.isArray(d.cycles) ? d.cycles.map((c: unknown) => String(c)) : [],
  }
}

export function isOutOfScopeRejection(e: any): boolean {
  return delegationRejection(e)?.reason === OUT_OF_SCOPE
}

/** 程序委派 preview 的 `scope_gaps` 一项：执行人 / 复核人有效循环范围缺少的循环 */
export interface ScopeGap {
  role: string
  name?: string
  cycles?: string[]
  is_member?: boolean
}

/** 预览里的可见范围缺口说明（没有缺口返回空串）。 */
export function describeScopeGaps(gaps: ScopeGap[] | null | undefined): string {
  const list = Array.isArray(gaps) ? gaps : []
  if (!list.length) return ''
  const parts = list.map((g) => {
    const who = `${g.role === 'reviewer' ? '复核人' : '执行人'}${g.name ? ` ${g.name}` : ''}`
    return g.is_member === false
      ? `${who}不是本项目成员，不能委派`
      : `${who}的可见范围不含 ${(g.cycles ?? []).join('、')} 循环`
  })
  const needReason = list.some((g) => g.is_member !== false)
  return parts.join('；') + (needReason ? '；应用时需填写理由扩大其可见范围' : '')
}

/** 理由框正文（纯函数，便于测试）。 */
export function scopeExpansionPromptText(r: DelegationRejection): string {
  const cycles = r.cycles.length ? `${r.cycles.join('、')} 循环` : '目标循环'
  const head = r.message || `被委派人的可见范围不含${cycles}`
  return `${head}\n确认后将把 ${cycles} 加入被委派人的可见范围，并记入委派历史。`
}

/** 弹框要理由；返回去掉首尾空白的理由，用户取消返回 null。 */
export async function promptScopeReason(r: DelegationRejection): Promise<string | null> {
  try {
    const res: any = await ElMessageBox.prompt(scopeExpansionPromptText(r), '扩大可见范围', {
      confirmButtonText: '扩大并委派',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputPlaceholder: '扩大可见范围的理由（必填）',
      inputValidator: (v: string) => (!!v && !!v.trim()) || '请填写扩大可见范围的理由',
    })
    const value = String(res?.value ?? '').trim()
    return value || null
  } catch {
    return null
  }
}

/**
 * 执行一次委派请求；被拒为 `out_of_scope` 时要理由后带扩权参数再执行一次。
 * `attempt(extra)`：首次 `extra = {}`，重试 `extra = {expand_scope: true, scope_reason}`，由调用方并进请求体。
 */
export async function withScopeExpansionRetry<T>(
  attempt: (extra: ScopeExpansion) => Promise<T>,
  opts: { prompt?: (r: DelegationRejection) => Promise<string | null> } = {},
): Promise<ScopeRetryOutcome<T>> {
  try {
    return { status: 'done', result: await attempt({}), expanded: false }
  } catch (e) {
    const r = delegationRejection(e)
    if (!r || r.reason !== OUT_OF_SCOPE) throw e
    const reason = await (opts.prompt ?? promptScopeReason)(r)
    if (!reason) return { status: 'cancelled' }
    return { status: 'done', result: await attempt({ expand_scope: true, scope_reason: reason }), expanded: true }
  }
}

export function useScopeExpansionRetry() {
  return { withScopeExpansionRetry, delegationRejection, isOutOfScopeRejection }
}
