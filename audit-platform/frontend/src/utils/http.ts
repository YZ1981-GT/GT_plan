import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
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

// Response interceptor: unwrap ApiResponse + handle errors
http.interceptors.response.use(
  (response: AxiosResponse) => {
    // 二进制响应（blob/arraybuffer）不解包
    if (response.config.responseType === 'blob' || response.config.responseType === 'arraybuffer') {
      return response
    }
    // 统一解包 ApiResponse: { code, message, data } → 提取 data
    const d = response.data
    if (d && typeof d === 'object' && 'code' in d && 'data' in d) {
      response.data = d.data
    }
    return response
  },
  async (error) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
    const authStore = useAuthStore()
    const status = error.response?.status

    // 401 → try refresh token
    if (status === 401 && !originalRequest._retry) {
      if (!authStore.refreshToken) {
        authStore.logout()
        window.location.href = '/login'
        return Promise.reject(error)
      }
      if (isRefreshing) {
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

    // 分级错误处理
    const detail = error.response?.data?.detail ?? error.response?.data?.message ?? ''
    const fallback = error.message ?? '请求失败'

    switch (status) {
      case 400:
        ElMessage.warning(detail || '请求参数错误')
        break
      case 403:
        ElMessage.error('权限不足，无法执行此操作')
        break
      case 404:
        ElMessage.warning(detail || '请求的资源不存在')
        break
      case 409:
        ElMessage.warning(detail || '数据冲突，请刷新后重试')
        break
      case 413:
        ElMessage.error(detail || '文件过大，超出限制')
        break
      case 422:
        ElMessage.warning(detail || '数据校验失败')
        break
      case 423:
        ElMessage.warning(detail || '资源已锁定（合并锁定中）')
        break
      case 500:
        ElMessage.error('服务器内部错误，请稍后重试')
        break
      default:
        ElMessage.error(detail || fallback)
    }
    return Promise.reject(error)
  },
)

export default http
