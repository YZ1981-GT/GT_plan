import { defineStore } from 'pinia'
import axios from 'axios'

export interface UserProfile {
  id: string
  username: string
  email: string
  role: string
  office_code: string | null
  is_active: boolean
  created_at: string
}

export interface AuthState {
  token: string | null
  refreshToken: string | null
  user: UserProfile | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    token: localStorage.getItem('token'),
    refreshToken: localStorage.getItem('refreshToken'),
    user: null,
  }),

  getters: {
    isAuthenticated: (state) => !!state.token,
    username: (state) => state.user?.username ?? '',
  },

  actions: {
    async login(username: string, password: string) {
      const { data } = await axios.post('/api/auth/login', { username, password })
      const payload = data.data ?? data
      this.token = payload.access_token
      this.refreshToken = payload.refresh_token
      this.user = payload.user ?? null
      localStorage.setItem('token', this.token!)
      localStorage.setItem('refreshToken', this.refreshToken!)
    },

    async logout() {
      try {
        await axios.post('/api/auth/logout', null, {
          headers: { Authorization: `Bearer ${this.token}` },
        })
      } catch {
        // ignore logout errors
      }
      this.token = null
      this.refreshToken = null
      this.user = null
      localStorage.removeItem('token')
      localStorage.removeItem('refreshToken')
    },

    async refreshAccessToken() {
      const { data } = await axios.post('/api/auth/refresh', {
        refresh_token: this.refreshToken,
      })
      const payload = data.data ?? data
      this.token = payload.access_token
      localStorage.setItem('token', this.token!)
    },

    async fetchUserProfile() {
      const { data } = await axios.get('/api/users/me', {
        headers: { Authorization: `Bearer ${this.token}` },
      })
      this.user = data.data ?? data
    },
  },
})
