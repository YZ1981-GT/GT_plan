/**
 * useAuditContext — 审计上下文 composable（横切组件 1）
 *
 * 统一收敛 projectId / year / applicableStandard / isArchived / canEdit 的响应式读取，
 * 对外暴露 reactive view + onContextChange 回调注册 + 事件 emit。
 *
 * 数据源：projectStore 是单一真源，本 composable 只是 reactive view + watcher。
 * URL 同步：projectStore.changeYear(y) 时同步 route.query.year + emit year:changed（既有逻辑）。
 * 自动 watch：route.params.projectId / route.query.year 变化时触发 audit-context:changed 事件。
 * debounce：50ms 防抖避免路由跳转抖动。
 *
 * @see design.md 横切组件 1
 */
import { computed, watch, onScopeDispose, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { useRoleContextStore } from '@/stores/roleContext'
import { eventBus } from '@/utils/eventBus'

export interface AuditContextState {
  /** 当前项目 ID（响应式） */
  projectId: ComputedRef<string>
  /** 当前审计年度（响应式） */
  year: ComputedRef<number>
  /** 适用准则 'soe' | 'listed'（响应式） */
  applicableStandard: ComputedRef<'soe' | 'listed'>
  /** 项目是否已归档（响应式） */
  isArchived: ComputedRef<boolean>
  /** 当前用户在该项目下是否可编辑（响应式） */
  canEdit: ComputedRef<boolean>
  /** 注册 refetch 回调，年度/项目变化时自动触发；返回取消注册函数 */
  onContextChange: (cb: (ctx: { projectId: string; year: number }) => void) => () => void
}

/** debounce 延迟（ms），避免路由跳转期间多次触发 */
export const DEBOUNCE_MS = 50

export function useAuditContext(options?: {
  /** 标记本视图与 audit context 无关（如帮助页），跳过事件监听 */
  irrelevant?: boolean
}): AuditContextState {
  const route = useRoute()
  const projectStore = useProjectStore()
  const roleContextStore = useRoleContextStore()

  // ─── 响应式 computed（三级 fallback 铁律） ───
  const projectId = computed(() => projectStore.projectId || (route.params.projectId as string) || '')

  const year = computed(() =>
    projectStore.year || Number(route.query.year) || new Date().getFullYear() - 1
  )

  const applicableStandard = computed<'soe' | 'listed'>(() => projectStore.standard)

  const isArchived = computed(() => projectStore.projectStatus === 'archived')

  const canEdit = computed(() => !isArchived.value && roleContextStore.canEditInProject)

  // ─── onContextChange 回调注册 ───
  const callbacks = new Set<(ctx: { projectId: string; year: number }) => void>()

  function onContextChange(cb: (ctx: { projectId: string; year: number }) => void): () => void {
    callbacks.add(cb)
    return () => { callbacks.delete(cb) }
  }

  // ─── 自动 watch + debounce + 事件 emit ───
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  if (!options?.irrelevant) {
    watch(
      [() => route.params.projectId, () => route.query.year, () => projectStore.standard],
      ([newPid, newYear, newStandard], [oldPid, oldYear, oldStandard]) => {
        if (debounceTimer) clearTimeout(debounceTimer)

        debounceTimer = setTimeout(() => {
          const currentProjectId = projectId.value
          const currentYear = year.value
          const currentStandard = applicableStandard.value

          // emit audit-context:changed 事件
          eventBus.emit('audit-context:changed', {
            projectId: currentProjectId,
            year: currentYear,
            applicableStandard: currentStandard,
            before: {
              projectId: (oldPid as string) || '',
              year: Number(oldYear) || new Date().getFullYear() - 1,
              applicableStandard: (oldStandard as 'soe' | 'listed') || 'soe',
            },
          })

          // 调用所有注册的回调
          callbacks.forEach((cb) => {
            try {
              cb({ projectId: currentProjectId, year: currentYear })
            } catch { /* 回调异常不影响其他回调 */ }
          })
        }, DEBOUNCE_MS)
      },
      { flush: 'post' }
    )
  }

  // 组件销毁时清理 timer + 回调
  onScopeDispose(() => {
    if (debounceTimer) clearTimeout(debounceTimer)
    callbacks.clear()
  })

  return {
    projectId,
    year,
    applicableStandard,
    isArchived,
    canEdit,
    onContextChange,
  }
}
