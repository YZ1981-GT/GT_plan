import { defineStore } from 'pinia'
import axios from 'axios'
import http from '@/utils/http'
import { API } from '@/services/apiPaths'

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
}

export interface AuthState {
  token: string | null
  refreshToken: string | null
  user: UserProfile | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    // 安全改进：改用 sessionStorage（关闭标签页自动清除，防止 XSS 窃取 token）
    // localStorage 在 XSS 攻击下可被任意 JS 读取，审计平台数据敏感，需更高安全级别
    token: sessionStorage.getItem('token'),
    refreshToken: sessionStorage.getItem('refreshToken'),
    user: null,
  }),

  getters: {
    isAuthenticated: (state) => !!state.token,
    username: (state) => state.user?.username ?? '',
    userId: (state) => state.user?.id ?? '',
  },

  actions: {
    async login(username: string, password: string) {
      const { data } = await authHttp.post('/api/auth/login', { username, password })
      const payload = data
      this.token = payload.access_token
      this.refreshToken = payload.refresh_token
      this.user = payload.user ?? null
      sessionStorage.setItem('token', this.token!)
      sessionStorage.setItem('refreshToken', this.refreshToken!)
    },

    async logout() {
      try {
        await authHttp.post('/api/auth/logout', {
          refresh_token: this.refreshToken,
        }, {
          headers: { Authorization: `Bearer ${this.token}` },
        })
      } catch {
        // ignore logout errors
      }
      this.token = null
      this.refreshToken = null
      this.user = null
      sessionStorage.removeItem('token')
      sessionStorage.removeItem('refreshToken')
    },

    async refreshAccessToken() {
      const { data } = await authHttp.post('/api/auth/refresh', {
        refresh_token: this.refreshToken,
      })
      const payload = data
      // Token Rotation: 后端每次刷新都签发新的 refresh_token
      this.token = payload.access_token
      this.refreshToken = payload.refresh_token ?? this.refreshToken
      sessionStorage.setItem('token', this.token!)
      sessionStorage.setItem('refreshToken', this.refreshToken!)
    },

    async fetchUserProfile() {
      // 使用带拦截器的 http 实例，自动附加 token + 401 刷新
      const { data } = await http.get(API.users.me)
      this.user = data
    },
  },
})
