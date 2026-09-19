/**
 * 高级查询构建器入口可用性 —— 单一判据。
 *
 * 与后端 `backend/app/routers/query_builder.py` 的 `_QUERY_BUILDER_ROLES`
 * 逐一对应。改造前 `CustomQueryTab.vue` 用的是
 * `canDo('edit', 'project_settings')` —— 那是**资源级**权限矩阵判据，与后端的
 * **角色白名单**判据是两套语义：矩阵一旦调整 project_settings 的编辑权，前端
 * 入口就会与后端 403 不一致（按钮可点但请求必失败，或按钮禁用而其实有权）。
 *
 * 前端仅作体验优化，安全边界始终在后端 `require_query_builder_access`。
 *
 * _Requirements: 11.1, 11.2_
 */
import { computed } from 'vue'

import { usePermissionMatrix } from '@/composables/usePermissionMatrix'

/** 可使用白名单构建器的角色（partner 为 manager 权限超集，平台既有约定纳入） */
export const QUERY_BUILDER_ROLES = ['admin', 'manager', 'partner'] as const

/** 角色不足时的中文原因提示（可见不可点场景展示） */
export const BUILDER_DISABLED_REASON = '高级构建器仅限管理员 / 经理 / 合伙人'

export function useQueryBuilderAccess() {
  const { currentRole } = usePermissionMatrix()

  const canUseBuilder = computed(() => {
    const role = String(currentRole.value ?? '')
    return (QUERY_BUILDER_ROLES as readonly string[]).includes(role)
  })

  return {
    currentRole,
    canUseBuilder,
    builderDisabledReason: BUILDER_DISABLED_REASON,
  }
}
