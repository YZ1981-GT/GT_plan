/**
 * 高级查询构建器入口可用性 —— 单一判据（advanced-query-linkage-closure 任务 30，ADR-AQL-08；R3.6、R11.3）。
 *
 * 判据只在后端：`GET /api/query/access`（`services/custom_query/builder_access.resolve_builder_access`，与构建器各端点的
 * 门禁 `require_query_builder_access` 是同一实现）。前端不再持有角色清单——改造前这里按系统角色 {admin, manager, partner}
 * 判定：系统角色为 auditor 的现场项目经理（项目经理、edit 级）后端放行而前端挡住（AQ-21），原因文案也漏了「含项目经理」。
 *
 * - 首次使用时取一次 access 接口，结论按登录身份缓存在模块里（同一会话内各入口共用一次请求；换人登录或登出即失效，
 *   下次使用重取；没有登录时不发请求）；
 * - `canUseBuilder` = 准入通过且作用域非空（admin / partner 不限项目；其余身份可访问项目数 > 0）；
 * - `builderDisabledReason`：不可用时的中文原因，取接口的 `reason`（无权、没有可访问的项目、循环范围）；取不到接口结论时
 *   给「暂时无法确认…」并保持不可用——不回落到任何前端判据。
 *
 * 前端只作体验，安全边界在后端门禁。
 *
 * _Requirements: 11.1, 11.2（advanced-query-module）；R3.6、R11.3（advanced-query-linkage-closure）_
 */
import { computed, reactive, watch } from 'vue'

import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import { api } from '@/services/apiProxy'
import { queryBuilder as P_qb } from '@/services/apiPaths'
import { useAuthStore } from '@/stores/auth'

/** `GET /api/query/access` 的响应（后端 `builder_access.BuilderAccess.to_dict`） */
export interface QueryBuilderAccess {
  allowed: boolean
  basis: 'system_role' | 'project_manager' | null
  reason: string | null
  all_projects: boolean
  accessible_project_count: number | null
}

export const ACCESS_PENDING_REASON = '正在确认高级构建器权限…'
export const ACCESS_UNAVAILABLE_REASON = '暂时无法确认高级构建器权限，请稍后重试'
export const ACCESS_NOT_LOGGED_IN_REASON = '请先登录'
/** 接口判为不可用却没给原因时的兜底（与后端 builder_access 的两条原因同义） */
const FALLBACK_FORBIDDEN_REASON = '高级构建器仅限管理员、合伙人、经理（含任一项目的项目经理）使用'
const FALLBACK_NO_PROJECT_REASON = '您当前没有可访问的项目'

type Status = 'idle' | 'loading' | 'ready' | 'failed'

/** 模块级缓存：同一身份只取一次；`generation` 让过期请求的回包作废（换人登录 / 重置之后到达的不写入） */
const shared = reactive({
  identity: '' as string,
  access: null as QueryBuilderAccess | null,
  status: 'idle' as Status,
})
let generation = 0

function normalizeAccess(raw: unknown): QueryBuilderAccess | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  if (typeof r.allowed !== 'boolean') return null
  const count = r.accessible_project_count
  return {
    allowed: r.allowed,
    basis: r.basis === 'system_role' || r.basis === 'project_manager' ? r.basis : null,
    reason: typeof r.reason === 'string' && r.reason.trim() ? r.reason.trim() : null,
    all_projects: r.all_projects === true,
    accessible_project_count: typeof count === 'number' && Number.isFinite(count) ? count : null,
  }
}

async function load(identity: string): Promise<void> {
  if (!identity) {
    // 没有登录（或刚登出）：清空，不发请求
    generation += 1
    Object.assign(shared, { identity: '', access: null, status: 'idle' })
    return
  }
  // 同一身份已取到或正在取：共用；上次失败的，下一个使用方挂载时重取
  if (shared.identity === identity && (shared.status === 'loading' || shared.status === 'ready')) return
  const gen = ++generation
  Object.assign(shared, { identity, access: null, status: 'loading' })
  try {
    const raw = await api.get(P_qb.access, { _silent: true } as any)
    if (gen !== generation) return
    const access = normalizeAccess(raw)
    shared.access = access
    shared.status = access ? 'ready' : 'failed'
  } catch {
    if (gen === generation) shared.status = 'failed'
  }
}

/** 清空模块缓存（测试用；下次使用时重取） */
export function resetQueryBuilderAccessCache(): void {
  generation += 1
  Object.assign(shared, { identity: '', access: null, status: 'idle' })
}

export function useQueryBuilderAccess() {
  // currentRole 只供调用方显示，不参与构建器准入判定
  const { currentRole } = usePermissionMatrix()
  const authStore = useAuthStore()
  const identity = computed(() => String(authStore.user?.id || authStore.token || ''))
  watch(identity, (id) => { void load(id) }, { immediate: true })

  const access = computed<QueryBuilderAccess | null>(() =>
    shared.identity && shared.identity === identity.value ? shared.access : null,
  )
  const loading = computed(() => !!identity.value && (shared.identity !== identity.value || shared.status === 'loading'))
  const canUseBuilder = computed(() => {
    const a = access.value
    return !!a && a.allowed && (a.all_projects || (a.accessible_project_count ?? 0) > 0)
  })
  const allProjects = computed(() => !!access.value?.all_projects)
  const accessibleProjectCount = computed(() => access.value?.accessible_project_count ?? null)
  const builderDisabledReason = computed(() => {
    if (canUseBuilder.value) return ''
    const a = access.value
    if (a) return a.reason || (a.allowed ? FALLBACK_NO_PROJECT_REASON : FALLBACK_FORBIDDEN_REASON)
    if (!identity.value) return ACCESS_NOT_LOGGED_IN_REASON
    return shared.status === 'failed' && shared.identity === identity.value ? ACCESS_UNAVAILABLE_REASON : ACCESS_PENDING_REASON
  })

  return {
    currentRole,
    access,
    loading,
    canUseBuilder,
    allProjects,
    accessibleProjectCount,
    builderDisabledReason,
  }
}
