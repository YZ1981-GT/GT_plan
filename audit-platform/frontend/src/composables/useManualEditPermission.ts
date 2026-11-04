/**
 * 账号「允许修改」开关（spec citar-manual-edit-permission）。
 *
 * 管理员在「账号权限」页逐个账号开 / 关；关闭后不能人工修改自动生成的数据（税审底稿公式 / 取数格、报表金额、
 * 审核说明、余额表 / 序时账等），后端同样拒收（403）。本模块只决定界面给不给修改入口。
 *
 * - `canManualEdit`：当前账号是否允许；账号信息里没有该字段（旧会话）按允许，与后端默认一致。
 * - `refreshCurrentUser()`：重读 `/api/users/me`，开关变化后不必重新登录（CitarLayout 进入项目时调一次）。
 */
import { computed } from 'vue'
import http from '@/utils/http'
import { users as P_usr } from '@/services/apiPaths'
import { useAuthStore, type UserProfile } from '@/stores/auth'

export const MANUAL_EDIT_DENIED_TIP = '账号未开通「允许修改」，不能修改自动生成的数据（请联系管理员在「账号权限」开启）'

export function useManualEditPermission() {
  const authStore = useAuthStore()
  const canManualEdit = computed(() => authStore.user?.allow_manual_edit !== false)
  return { canManualEdit }
}

/** 重读当前账号信息；失败不打扰用户（沿用已缓存的账号信息）。 */
export async function refreshCurrentUser(): Promise<void> {
  const authStore = useAuthStore()
  if (!authStore.isAuthenticated) return
  try {
    const { data } = await http.get(P_usr.me, { _silent: true, _dedupe: false } as any)
    if (data && typeof data === 'object' && 'id' in data) {
      // /api/users/me 返回完整账号信息（含 permissions），整体替换
      authStore.user = data as UserProfile
      sessionStorage.setItem('user', JSON.stringify(authStore.user))
    }
  } catch {
    // 网络 / 鉴权问题由其他请求的拦截器处理
  }
}
