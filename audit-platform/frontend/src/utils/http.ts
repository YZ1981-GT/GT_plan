/**
 * HTTP 客户端 — 统一请求封装
 *
 * 功能：Bearer token 自动附加、401 自动刷新、ApiResponse 统一解包、
 *       分级错误处理、请求取消（AbortController）、请求去重、自动重试
 */
import axios, { type AxiosResponse, type InternalAxiosRequestConfig, type AxiosError } from 'axios'
import NProgress from 'nprogress'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

// ── NProgress 活跃请求计数器 ──────────────────────────────
let activeRequests = 0

// ── Trace ID 存储（R7-S2-11）──────────────────────────────
let _lastTraceId = ''
/** 获取最近一次请求的 trace id（X-Request-ID 响应头） */
export function getLastTraceId(): string { return _lastTraceId }

// ── R10 Spec C / Sprint 1.3：5xx 环形缓冲区监控 ─────────
// design D4：last100Requests 不暴露给业务代码，只通过 recent5xxRate / getRecentNetworkStats 访问
const _last100Requests: { status: number; ts: number }[] = []
const _MAX_BUFFER = 100
const _WINDOW_MS = 60_000
const _MIN_SAMPLES = 10

function _trackResponse(status: number) {
  _last100Requests.push({ status, ts: Date.now() })
  if (_last100Requests.length > _MAX_BUFFER) {
    _last100Requests.shift()
  }
}

/** 最近 1 分钟内 5xx 比率（< 10 次请求时返回 0） */
export function recent5xxRate(): number {
  const now = Date.now()
  const recent = _last100Requests.filter((r) => now - r.ts < _WINDOW_MS)
  if (recent.length < _MIN_SAMPLES) return 0
  const xx5 = recent.filter((r) => r.status >= 500 && r.status < 600).length
  return xx5 / recent.length
}

/** 网络状态详情（仅 DegradedBanner 内部使用，不暴露原始数组） */
export function getRecentNetworkStats(): {
  total: number
  xx5_count: number
  xx5_rate: number
  last_5xx_at: number | null
} {
  const now = Date.now()
  const recent = _last100Requests.filter((r) => now - r.ts < _WINDOW_MS)
  const xx5 = recent.filter((r) => r.status >= 500 && r.status < 600)
  return {
    total: recent.length,
    xx5_count: xx5.length,
    xx5_rate: recent.length >= _MIN_SAMPLES ? xx5.length / recent.length : 0,
    last_5xx_at: xx5.length > 0 ? xx5[xx5.length - 1].ts : null,
  }
}

/** 测试钩子：清空缓冲区 */
export function _resetNetworkStats() {
  _last100Requests.length = 0
}

const http = axios.create({
  baseURL: '/',
  timeout: 120000,
})

// ── 请求去重：相同 GET 请求在飞行中不重复发送 ──────────────
const pendingMap = new Map<string, AbortController>()
// POST/PUT/PATCH 防重复提交的自动清理定时器（防止超时/取消时 key 泄漏）
const pendingTimers = new Map<string, ReturnType<typeof setTimeout>>()

function getRequestKey(config: InternalAxiosRequestConfig): string {
  const base = `${config.method}:${config.url}:${JSON.stringify(config.params || '')}`
  // POST/PUT/PATCH 请求：对 body 做轻量 hash（取前100字符+总长度），避免大 body 时 JSON.stringify 性能差
  if (config.data && typeof config.data === 'object' && !(config.data instanceof FormData)) {
    try {
      const bodyStr = JSON.stringify(config.data)
      const bodyHash = `${bodyStr.slice(0, 100)}|len:${bodyStr.length}`
      return `${base}:${bodyHash}`
    } catch {
      return base
    }
  }
  return base
}

function addPending(config: InternalAxiosRequestConfig) {
  const key = getRequestKey(config)
  // 跳过 FormData 上传请求（文件上传不参与去重）
  if (config.data instanceof FormData) return
  const method = config.method?.toUpperCase()
  if (method === 'GET' && pendingMap.has(key)) {
    // GET 去重：取消前一个相同请求
    pendingMap.get(key)!.abort()
  } else if ((method === 'POST' || method === 'PUT' || method === 'PATCH') && pendingMap.has(key)) {
    // POST/PUT/PATCH 防重复提交：取消当前请求（保留先发的）
    const controller = new AbortController()
    controller.abort()
    config.signal = controller.signal
    return
  }
  const controller = new AbortController()
  config.signal = controller.signal
  pendingMap.set(key, controller)
  // POST/PUT/PATCH 设置 5 分钟自动清理，防止超时/取消时 key 泄漏导致后续请求永久被拒
  if (method === 'POST' || method === 'PUT' || method === 'PATCH') {
    const existingTimer = pendingTimers.get(key)
    if (existingTimer) clearTimeout(existingTimer)
    const cleanupTimer = setTimeout(() => {
      pendingMap.delete(key)
      pendingTimers.delete(key)
    }, 5 * 60 * 1000)
    pendingTimers.set(key, cleanupTimer)
  }
}

function removePending(config: InternalAxiosRequestConfig) {
  const key = getRequestKey(config)
  pendingMap.delete(key)
  // 清除对应的自动清理定时器
  const timer = pendingTimers.get(key)
  if (timer) {
    clearTimeout(timer)
    pendingTimers.delete(key)
  }
}

async function extractErrorDetail(responseData: unknown): Promise<string> {
  if (responseData instanceof Blob) {
    try {
      const text = await responseData.text()
      if (!text) return ''
      try {
        const parsed = JSON.parse(text)
        return parsed?.detail ?? parsed?.message ?? text
      } catch {
        return text
      }
    } catch {
      return ''
    }
  }

  if (responseData && typeof responseData === 'object') {
    const d = (responseData as any)?.detail ?? (responseData as any)?.message ?? ''
    if (typeof d === 'string') return d
    if (d && typeof d === 'object') return d.message || d.msg || JSON.stringify(d)
    return String(d || '')
  }

  return typeof responseData === 'string' ? responseData : ''
}

// ── 请求拦截器 ──────────────────────────────────────────
http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const authStore = useAuthStore()
  config.headers = config.headers ?? {}
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  addPending(config)
  // NProgress：首个请求启动进度条，后续请求递增
  activeRequests++
  if (activeRequests === 1) {
    NProgress.start()
  } else {
    NProgress.inc()
  }
  // 记录请求开始时间
  ;(config as any)._startTime = Date.now()
  return config
})

// ── 401 刷新队列 ────────────────────────────────────────
let isRefreshing = false
let refreshQueue: Array<{
  resolve: (token: string) => void
  reject: (error: unknown) => void
}> = []

// ── 响应拦截器 ──────────────────────────────────────────
http.interceptors.response.use(
  (response: AxiosResponse) => {
    removePending(response.config as InternalAxiosRequestConfig)
    // R7-S2-11: 存储 trace id
    _lastTraceId = response.headers?.['x-request-id'] || ''
    // R10 Spec C: 5xx 环形缓冲区记录响应
    _trackResponse(response.status)
    // NProgress：所有请求完成后结束进度条
    activeRequests = Math.max(0, activeRequests - 1)
    if (activeRequests === 0) NProgress.done()
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
    // R7-S2-11: 存储 trace id（错误响应）
    _lastTraceId = (error.response?.headers as any)?.['x-request-id'] || ''
    // R10 Spec C: 5xx 环形缓冲区记录错误响应
    _trackResponse(error.response?.status ?? 0)
    // NProgress：错误时也递减计数
    activeRequests = Math.max(0, activeRequests - 1)
    if (activeRequests === 0) NProgress.done()

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

    // R8-S1-05：超时专门处理
    if (error.code === 'ECONNABORTED') {
      const { feedback } = await import('./feedback')
      feedback.notify({
        type: 'warning',
        title: '请求超时',
        message: '网络连接缓慢，已停止等待。建议检查网络或稍后重试。',
        duration: 6000,
      })
      return Promise.reject(error)
    }

    // R8-S1-05：断网专门处理
    if (!error.response && !navigator.onLine) {
      const { feedback } = await import('./feedback')
      feedback.notify({
        type: 'warning',
        title: '网络已断开',
        message: '当前离线，部分操作可能无法完成。恢复网络后请重试。',
        duration: 8000,
      })
      return Promise.reject(error)
    }

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
        return new Promise((resolve, reject) => {
          refreshQueue.push({
            resolve: (token: string) => {
              originalRequest.headers = originalRequest.headers ?? {}
              originalRequest.headers.Authorization = `Bearer ${token}`
              resolve(http(originalRequest))
            },
            reject,
          })
        })
      }
      originalRequest._retry = true
      isRefreshing = true
      try {
        await authStore.refreshAccessToken()
        const newToken = authStore.token!
        refreshQueue.forEach(({ resolve }) => resolve(newToken))
        refreshQueue = []
        originalRequest.headers = originalRequest.headers ?? {}
        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return http(originalRequest)
      } catch (refreshError) {
        refreshQueue.forEach(({ reject }) => reject(refreshError))
        refreshQueue = []
        authStore.logout()
        window.location.href = '/login'
        return Promise.reject(error)
      } finally {
        isRefreshing = false
      }
    }

    // 500/502/503 自动重试（最多 2 次）+ loading 提示
    if (status && status >= 500 && (originalRequest._retryCount ?? 0) < 2) {
      originalRequest._retryCount = (originalRequest._retryCount ?? 0) + 1
      const retryMsg = ElMessage.info({
        message: `服务器暂时异常，正在第 ${originalRequest._retryCount} 次重试...`,
        duration: 0,
        showClose: true,
      })
      await new Promise((r) => setTimeout(r, 1000 * originalRequest._retryCount!))
      retryMsg.close()
      return http(originalRequest)
    }

    // 分级错误提示
    const detail = await extractErrorDetail(error.response?.data)
    const fallback = error.message ?? '请求失败'
    const requestId = error.response?.headers?.['x-request-id'] || ''
    const msgMap: Record<number, string> = {
      400: detail || '请求参数错误',
      403: '权限不足，无法执行此操作',
      404: detail || '请求的资源不存在',
      409: detail || '数据冲突，请刷新后重试',
      413: detail || '文件过大，超出限制',
      422: detail || '数据校验失败',
      423: '',  // 423 锁定详情由下方专门处理
      500: '服务器内部错误，请稍后重试',
      502: '网关错误，请稍后重试',
      503: '服务暂时不可用',
    }
    const msg = (status && msgMap[status]) || detail || fallback

    // 423 锁定详情：显示锁定人/时间/解锁方式
    if (status === 423) {
      let lockInfo = detail || '资源已锁定'
      try {
        const lockData = error.response?.data as any
        const payload = lockData?.data ?? lockData
        if (payload && typeof payload === 'object') {
          const lockedBy = payload.locked_by || payload.lockedBy || ''
          const lockedAt = payload.locked_at || payload.lockedAt || ''
          const unlockHint = payload.unlock_hint || payload.unlockHint || '请联系锁定人或等待自动释放'
          if (lockedBy) {
            lockInfo = `资源已被 ${lockedBy} 锁定`
            if (lockedAt) lockInfo += `（${lockedAt}）`
            lockInfo += `\n解锁方式：${unlockHint}`
          }
        }
      } catch { /* ignore parse errors */ }
      ElMessage.warning({ message: lockInfo, duration: 5000, showClose: true })
      return Promise.reject(error)
    }

    const displayMsg = requestId ? `${msg}（ID: ${requestId}）` : msg
    if (status && status >= 500) {
      // R8-S1-05：5xx 最终失败用持续性通知卡片（重试已耗尽）
      const { feedback } = await import('./feedback')
      feedback.notify({
        type: 'error',
        title: '服务器错误',
        message: displayMsg,
        duration: 8000,
      })
    } else if (status === 403) {
      ElMessage.error(displayMsg)
    } else {
      ElMessage.warning(displayMsg)
    }
    return Promise.reject(error)
  },
)

// ── 导出辅助函数 ────────────────────────────────────────

function extractFileNameFromDisposition(contentDisposition?: string, fallback: string = 'download') {
  if (!contentDisposition) return fallback

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      return utf8Match[1]
    }
  }

  const fileNameMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  if (fileNameMatch?.[1]) {
    return fileNameMatch[1]
  }

  return fallback
}

export function saveBlobAsFile(blob: Blob, fileName: string) {
  const objectUrl = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = fileName
  a.click()
  window.URL.revokeObjectURL(objectUrl)
}

export async function downloadFile(
  url: string,
  options?: {
    method?: 'get' | 'post'
    data?: any
    params?: Record<string, any>
    fileName?: string
  },
) {
  const method = options?.method ?? 'get'
  const response = method === 'post'
    ? await http.post(url, options?.data ?? null, { params: options?.params, responseType: 'blob' })
    : await http.get(url, { params: options?.params, responseType: 'blob' })

  const contentDisposition = response.headers?.['content-disposition'] as string | undefined
  const resolvedFileName = extractFileNameFromDisposition(contentDisposition, options?.fileName || 'download')
  saveBlobAsFile(response.data as Blob, resolvedFileName)
  return response
}

/** 创建可取消的请求（用于组件卸载时取消） */
export function createCancelToken() {
  const controller = new AbortController()
  return {
    signal: controller.signal,
    cancel: () => controller.abort(),
  }
}

export default http
