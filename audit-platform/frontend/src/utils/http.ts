/**
 * HTTP 客户端 — 统一请求封装
 *
 * 功能：Bearer token 自动附加、401 自动刷新、ApiResponse 统一解包、
 *       分级错误处理、请求取消（AbortController）、请求去重、自动重试
 */
import axios, { type AxiosResponse, type InternalAxiosRequestConfig, type AxiosError } from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const http = axios.create({
  baseURL: '/',
  timeout: 30000,
})

// ── 请求去重：相同 GET 请求在飞行中不重复发送 ──────────────
const pendingMap = new Map<string, AbortController>()

function getRequestKey(config: InternalAxiosRequestConfig): string {
  return `${config.method}:${config.url}:${JSON.stringify(config.params || '')}`
}

function addPending(config: InternalAxiosRequestConfig) {
  const key = getRequestKey(config)
  if (config.method?.toUpperCase() === 'GET' && pendingMap.has(key)) {
    // 取消前一个相同请求
    pendingMap.get(key)!.abort()
  }
  const controller = new AbortController()
  config.signal = controller.signal
  pendingMap.set(key, controller)
}

function removePending(config: InternalAxiosRequestConfig) {
  const key = getRequestKey(config)
  pendingMap.delete(key)
}

// ── 请求拦截器 ──────────────────────────────────────────
http.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  addPending(config)
  // 记录请求开始时间
  ;(config as any)._startTime = Date.now()
  return config
})

// ── 401 刷新队列 ────────────────────────────────────────
let isRefreshing = false
let refreshQueue: Array<(token: string) => void> = []

// ── 响应拦截器 ──────────────────────────────────────────
http.interceptors.response.use(
  (response: AxiosResponse) => {
    removePending(response.config as InternalAxiosRequestConfig)
    // 记录请求日志
    const startTime = (response.config as any)._startTime
    if (startTime) {
      import('./monitor').then(({ logRequest }) => {
        logRequest({
          url: response.config.url || '',
          method: (response.config.method || 'get').toUpperCase(),
          status: response.status,
          duration: Date.now() - startTime,
          timestamp: Date.now(),
        })
      }).catch(() => {})
    }
    // blob/arraybuffer 不解包
    if (response.config.responseType === 'blob' || response.config.responseType === 'arraybuffer') {
      return response
    }
    // 统一解包 ApiResponse
    const d = response.data
    if (d && typeof d === 'object' && 'code' in d && 'data' in d) {
      response.data = d.data
    }
    return response
  },
  async (error: AxiosError) => {
    if (error.config) removePending(error.config as InternalAxiosRequestConfig)

    // 记录错误请求日志
    if (error.config) {
      const startTime = (error.config as any)._startTime
      if (startTime) {
        import('./monitor').then(({ logRequest }) => {
          logRequest({
            url: error.config?.url || '',
            method: (error.config?.method || 'get').toUpperCase(),
            status: error.response?.status || 0,
            duration: Date.now() - startTime,
            timestamp: Date.now(),
          })
        }).catch(() => {})
      }
    }

    // 请求被取消（去重导致）不弹错误
    if (axios.isCancel(error)) return Promise.reject(error)

    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean; _retryCount?: number }
    const authStore = useAuthStore()
    const status = error.response?.status

    // 401 → 刷新令牌
    if (status === 401 && !originalRequest._retry) {
      if (!authStore.refreshToken) {
        authStore.logout()
        window.location.href = '/login'
        return Promise.reject(error)
      }
      if (isRefreshing) {
        return new Promise((resolve) => {
          refreshQueue.push((token: string) => {
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
        refreshQueue.forEach((cb) => cb(newToken))
        refreshQueue = []
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

    // 500/502/503 自动重试（最多 2 次）
    if (status && status >= 500 && (originalRequest._retryCount ?? 0) < 2) {
      originalRequest._retryCount = (originalRequest._retryCount ?? 0) + 1
      await new Promise((r) => setTimeout(r, 1000 * originalRequest._retryCount!))
      return http(originalRequest)
    }

    // 分级错误提示
    const detail = (error.response?.data as any)?.detail ?? (error.response?.data as any)?.message ?? ''
    const fallback = error.message ?? '请求失败'
    const msgMap: Record<number, string> = {
      400: detail || '请求参数错误',
      403: '权限不足，无法执行此操作',
      404: detail || '请求的资源不存在',
      409: detail || '数据冲突，请刷新后重试',
      413: detail || '文件过大，超出限制',
      422: detail || '数据校验失败',
      423: detail || '资源已锁定（合并锁定中）',
      500: '服务器内部错误，请稍后重试',
      502: '网关错误，请稍后重试',
      503: '服务暂时不可用',
    }
    const msg = (status && msgMap[status]) || detail || fallback
    if (status && status >= 500) {
      ElMessage.error(msg)
    } else if (status === 403) {
      ElMessage.error(msg)
    } else {
      ElMessage.warning(msg)
    }
    return Promise.reject(error)
  },
)

// ── 导出辅助函数 ────────────────────────────────────────

/** 创建可取消的请求（用于组件卸载时取消） */
export function createCancelToken() {
  const controller = new AbortController()
  return {
    signal: controller.signal,
    cancel: () => controller.abort(),
  }
}

export default http
