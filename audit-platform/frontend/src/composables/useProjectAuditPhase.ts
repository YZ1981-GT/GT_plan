/**
 * 项目当前审计阶段与预审截止日（spec voucher-identity-writeback-and-audit-phase 任务 8，需求 6.1 / 6.2）
 *
 * 阶段是项目的事实（后端 projects.current_audit_phase，V212，缺省年审）：抽凭、挂凭、挂凭回拉
 * 生成的行都按它标阶段，宿主不再各传一个字面量。
 *
 * - 读：GET /api/projects/{id}/audit-phase（项目成员）；`canEdit` 由后端判（经理、合伙人含签字合伙人、admin）。
 * - 改：PUT 同一路径；只收 preliminary / final，预审截止日须在审计期间内且早于期末。
 * - 按项目缓存一份状态：同一页面的引擎、宿主、设置页共用；保存后就地更新，所有消费方同时看到新阶段。
 */
import { computed, reactive, ref, toValue, type MaybeRefOrGetter } from 'vue'
import http from '@/utils/http'
import { projects as P_projects } from '@/services/apiPaths'

export type AuditPhase = 'preliminary' | 'final'

export const AUDIT_PHASE_LABEL: Record<AuditPhase, string> = { preliminary: '预审', final: '年审' }

export interface ProjectAuditPhaseState {
  phase: AuditPhase
  interimCutoffDate: string | null
  auditPeriodStart: string | null
  auditPeriodEnd: string | null
  canEdit: boolean
}

const cache = reactive(new Map<string, ProjectAuditPhaseState>())
const inflight = new Map<string, Promise<ProjectAuditPhaseState>>()

function unwrap(res: any): any {
  return res?.data?.data ?? res?.data ?? res
}

function fromWire(d: any): ProjectAuditPhaseState {
  return {
    phase: d?.current_audit_phase === 'preliminary' ? 'preliminary' : 'final',
    interimCutoffDate: d?.interim_cutoff_date ?? null,
    auditPeriodStart: d?.audit_period_start ?? null,
    auditPeriodEnd: d?.audit_period_end ?? null,
    canEdit: Boolean(d?.can_edit),
  }
}

/** 「年审（预审截止 2025-09-30）」/「预审」：引擎与宿主顶部显示用 */
export function auditPhaseText(state: Pick<ProjectAuditPhaseState, 'phase' | 'interimCutoffDate'> | null): string {
  if (!state) return AUDIT_PHASE_LABEL.final
  const cutoff = state.interimCutoffDate ? `（预审截止 ${state.interimCutoffDate}）` : ''
  return `${AUDIT_PHASE_LABEL[state.phase]}${cutoff}`
}

/** 保存失败的原因（给用户看的中文） */
export function auditPhaseSaveFailureReason(err: unknown): string {
  const res = (err as { response?: { status?: number; data?: any } } | null)?.response
  const detail = res?.data?.detail
  if (res?.status === 403) return '只有项目经理、合伙人（含签字合伙人）可以修改审计阶段'
  if (res?.status === 423) return '项目已归档，审计阶段只读'
  if (res?.status === 422 && detail && typeof detail === 'object' && !Array.isArray(detail) && detail.message) {
    return String(detail.message)
  }
  if (res?.status === 422) return '审计阶段只能是预审或年审'
  return '保存失败，请稍后重试'
}

export async function fetchProjectAuditPhase(projectId: string, force = false): Promise<ProjectAuditPhaseState> {
  const cached = cache.get(projectId)
  if (cached && !force) return cached
  const pending = inflight.get(projectId)
  if (pending) return pending
  const p = (async () => {
    try {
      const res = await http.get(P_projects.auditPhase(projectId), { _silent: true } as any)
      const state = fromWire(unwrap(res))
      cache.set(projectId, state)
      return state
    } finally {
      inflight.delete(projectId)
    }
  })()
  inflight.set(projectId, p)
  return p
}

export function useProjectAuditPhase(projectId: MaybeRefOrGetter<string | null | undefined>) {
  const pid = computed(() => toValue(projectId) || '')
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  const state = computed<ProjectAuditPhaseState | null>(() => (pid.value ? cache.get(pid.value) ?? null : null))
  const phase = computed<AuditPhase>(() => state.value?.phase ?? 'final')
  const interimCutoffDate = computed(() => state.value?.interimCutoffDate ?? null)
  const canEdit = computed(() => Boolean(state.value?.canEdit))
  const text = computed(() => auditPhaseText(state.value))

  async function load(force = false): Promise<ProjectAuditPhaseState | null> {
    if (!pid.value) return null
    loading.value = true
    error.value = null
    try {
      return await fetchProjectAuditPhase(pid.value, force)
    } catch {
      error.value = '审计阶段读取失败'
      return null
    } finally {
      loading.value = false
    }
  }

  /** 保存；失败抛出原错误（原因用 auditPhaseSaveFailureReason 取），成功返回是否有改动 */
  async function save(next: { phase: AuditPhase; interimCutoffDate: string | null }): Promise<boolean> {
    if (!pid.value) return false
    saving.value = true
    try {
      const res = await http.put(
        P_projects.auditPhase(pid.value),
        { current_audit_phase: next.phase, interim_cutoff_date: next.interimCutoffDate || null },
        { _silent: true } as any,
      )
      const body = unwrap(res)
      cache.set(pid.value, fromWire(body))
      return Boolean(body?.changed)
    } finally {
      saving.value = false
    }
  }

  return { state, phase, interimCutoffDate, canEdit, text, loading, saving, error, load, save }
}

/** 测试用：清空缓存 */
export function __resetProjectAuditPhaseCache(): void {
  cache.clear()
  inflight.clear()
}
