import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const http = axios.create({
  baseURL: '/',
  timeout: 30000,
})

// Request interceptor: attach Bearer token
http.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  return config
})

// Track refresh state to avoid concurrent refresh calls
let isRefreshing = false
let pendingRequests: Array<(token: string) => void> = []

// Response interceptor: handle 401 refresh + error messages
http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    const authStore = useAuthStore()

    // 401 → try refresh token
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (!authStore.refreshToken) {
        authStore.logout()
        window.location.href = '/login'
        return Promise.reject(error)
      }

      if (isRefreshing) {
        // Queue this request until refresh completes
        return new Promise((resolve) => {
          pendingRequests.push((token: string) => {
            originalRequest.headers.Authorization = `Bearer ${token}`
            resolve(http(originalRequest))
          })
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        await authStore.refreshAccessToken()
        const newToken = authStore.token!

        // Retry queued requests
        pendingRequests.forEach((cb) => cb(newToken))
        pendingRequests = []

        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return http(originalRequest)
      } catch {
        authStore.logout()
        window.location.href = '/login'
        return Promise.reject(error)
      } finally {
        isRefreshing = false
      }
    }

    // Extract error message
    const message =
      error.response?.data?.message ??
      error.response?.data?.detail ??
      error.message ??
      '请求失败'

    ElMessage.error(message)
    return Promise.reject(error)
  },
)

export default http
