import { defineStore } from 'pinia'
import axios from 'axios'
import http from '@/utils/http'
import { API } from '@/services/apiPaths'
import { clearOnLogout } from '@/utils/aiChatCacheCleanup'
import { advanceRequestIdentityEpoch } from '@/services/requestIdentityEpoch'
import {
  broadcastTokenUpdate,
  broadcastLogout,
  listenAuthEvents,
  singleFlightRefresh,
} from '@/utils/crossWindowAuth'

/**
 * 认证专用 axios 实例（不带 auth 拦截器，避免循环依赖）。
 * 仅用于 login / refresh / logout 这三个不需要 token 自动附加的请求。
 */
const authHttp = axios.create({ baseURL: '/', timeout: 30000 })

export interface UserProfile {
  id: string
  username: string
  email: string
  role: string
  office_code: string | null
  is_active: boolean
  created_at: string
  /** 后端下发的权限列表（从 /api/users/me 获取），供 usePermission 使用 */
  permissions?: string[]
  /** 用户全名（中文姓名），eqcr/签字/审批等界面优先显示 */
  full_name?: string | null
}

export interface AuthState {
  token: string | null
  refreshToken: string | null
  user: UserProfile | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => {
    // 安全改进：改用 sessionStorage（关闭标签页自动清除，防止 XSS 窃取 token）
    // 一次性迁移：将旧 localStorage token 迁移到 sessionStorage，避免已登录用户被强制登出
    const oldToken = localStorage.getItem('token')
    const oldRefresh = localStorage.getItem('refreshToken')
    if (oldToken) {
      sessionStorage.setItem('token', oldToken)
      if (oldRefresh) sessionStorage.setItem('refreshToken', oldRefresh)
      localStorage.removeItem('token')
      localStorage.removeItem('refreshToken')
    }
    return {
      token: sessionStorage.getItem('token'),
      refreshToken: sessionStorage.getItem('refreshToken'),
      user: (() => {
        try {
          const s = sessionStorage.getItem('user')
          return s ? JSON.parse(s) : null
        } catch {
          return null
        }
      })(),
    }
  },

  getters: {
    isAuthenticated: (state) => !!state.token,
    username: (state) => state.user?.username ?? '',
    userId: (state) => state.user?.id ?? '',
  },

  actions: {
    async login(username: string, password: string) {
      const { data } = await authHttp.post('/api/auth/login', { username, password })
      const payload = data.data ?? data
      // 登录成功才切换逻辑身份；正常 refresh 不走这里。
      advanceRequestIdentityEpoch()
      this.token = payload.access_token
      this.refreshToken = payload.refresh_token
      this.user = payload.user ?? null
      sessionStorage.setItem('token', this.token!)
      sessionStorage.setItem('refreshToken', this.refreshToken!)
      if (this.user) sessionStorage.setItem('user', JSON.stringify(this.user))
    },

    async logout() {
      // 🔴 先同步清空本地会话，再通知后端。http.ts 在「刷新失败 / 刷新后仍 401」时调用本方法**不 await**、
      //    随即 `window.location.href = '/login'`：旧实现把清理放在 await 登出请求之后，页面卸载时请求被中断、
      //    清理永不执行 ⇒ 新页面仍读到旧 token（isAuthenticated 为真）⇒ 路由守卫把 /login 重定向回首页 ⇒
      //    401 ⇒ 再登出再跳转……无限整页重载（2026-09-30 实测 137 轮，每轮 12 个 401）。
      const refreshToken = this.refreshToken
      const accessToken = this.token
      // 必须在 token/user 对外可见地清空前推进：旧身份的 api.get 订阅者立即作废。
      advanceRequestIdentityEpoch()
      this.token = null
      this.refreshToken = null
      this.user = null
      sessionStorage.removeItem('token')
      sessionStorage.removeItem('refreshToken')
      sessionStorage.removeItem('user')
      // Task 10: 清理 AI 聊天敏感缓存
      clearOnLogout()
      // 多窗口：广播登出事件给其他窗口（multi-window-ledger-workbench Task 10）
      broadcastLogout()
      try {
        await authHttp.post('/api/auth/logout', {
          refresh_token: refreshToken,
        }, {
          headers: { Authorization: `Bearer ${accessToken}` },
        })
      } catch {
        // 服务端登出失败不影响本地已登出（refresh_token 到期自然失效）
      }
    },

    async refreshAccessToken() {
      // 多窗口安全：Web Locks 保证同一时刻只有一个标签页执行刷新
      // 其他标签页排队等待，避免 refresh token rotation 冲突
      // spec: multi-window-ledger-workbench Phase 2 Task 9
      await singleFlightRefresh(async () => {
        // 刷新前先检查 token 是否已被其他窗口更新（锁等待期间可能已收到广播）
        const freshToken = sessionStorage.getItem('token')
        if (freshToken && freshToken !== this.token) {
          this.token = freshToken
          this.refreshToken = sessionStorage.getItem('refreshToken') || this.refreshToken
          return
        }

        const { data } = await authHttp.post('/api/auth/refresh', {
          refresh_token: this.refreshToken,
        })
        const payload = data?.data ?? data
        const accessToken = payload?.access_token
        if (typeof accessToken !== 'string' || !accessToken) {
          throw new Error('刷新令牌响应缺少 access_token')
        }
        this.token = accessToken
        this.refreshToken = payload.refresh_token ?? this.refreshToken
        sessionStorage.setItem('token', accessToken)
        sessionStorage.setItem('refreshToken', this.refreshToken!)

        // 广播新 token 给其他窗口
        broadcastTokenUpdate(accessToken, this.refreshToken!)
      })
    },

    async fetchUserProfile() {
      // 使用带拦截器的 http 实例，自动附加 token + 401 刷新
      const { data } = await http.get(API.users.me)
      this.user = data
      if (this.user) sessionStorage.setItem('user', JSON.stringify(this.user))
    },
  },
})

// ── 多窗口认证事件监听（multi-window-ledger-workbench Phase 2 Task 10） ──
// 在模块加载时立即注册，确保所有窗口都能收到认证广播。
// 🔴 必须在 store 定义之后调用，因为 handlers 需要访问 store 实例。
if (typeof window !== 'undefined') {
  // 延迟到 Pinia 初始化后执行
  setTimeout(() => {
    try {
      const authStore = useAuthStore()
      listenAuthEvents({
        onTokenUpdate: (token, refreshToken) => {
          authStore.token = token
          authStore.refreshToken = refreshToken
          sessionStorage.setItem('token', token)
          sessionStorage.setItem('refreshToken', refreshToken)
        },
        onLogout: () => {
          // Broadcast logout 是明确会话边界；token-updated 则是同一会话轮换，不能推进。
          advanceRequestIdentityEpoch()
          authStore.token = null
          authStore.refreshToken = null
          authStore.user = null
          sessionStorage.removeItem('token')
          sessionStorage.removeItem('refreshToken')
          sessionStorage.removeItem('user')
          clearOnLogout()
          window.location.href = '/login'
        },
        onSessionRequest: () => {
          if (authStore.token && authStore.refreshToken) {
            return {
              token: authStore.token,
              refreshToken: authStore.refreshToken,
              user: authStore.user,
            }
          }
          return null
        },
      })
    } catch {
      // Pinia 未初始化时静默（SSR 或测试环境）
    }
  }, 0)
}
