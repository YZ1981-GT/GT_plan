/**
 * 请求监控与性能追踪
 *
 * 功能：请求日志、慢请求告警、Web Vitals 采集
 */

// ── 请求性能日志 ────────────────────────────────────────
interface RequestLog {
  url: string
  method: string
  status: number
  duration: number
  timestamp: number
}

const requestLogs: RequestLog[] = []
const MAX_LOGS = 200
const SLOW_THRESHOLD = 3000 // 3秒视为慢请求

/** 记录请求日志（由 http.ts 拦截器调用） */
export function logRequest(log: RequestLog) {
  requestLogs.push(log)
  if (requestLogs.length > MAX_LOGS) requestLogs.shift()

  if (log.duration > SLOW_THRESHOLD) {
    console.warn(`[慢请求] ${log.method} ${log.url} ${log.duration}ms`)
  }
}

/** 获取最近的请求日志 */
export function getRequestLogs(): RequestLog[] {
  return [...requestLogs]
}

/** 获取请求统计 */
export function getRequestStats() {
  if (requestLogs.length === 0) return null
  const durations = requestLogs.map((l) => l.duration)
  const errors = requestLogs.filter((l) => l.status >= 400)
  return {
    total: requestLogs.length,
    avgDuration: Math.round(durations.reduce((a, b) => a + b, 0) / durations.length),
    maxDuration: Math.max(...durations),
    errorCount: errors.length,
    errorRate: (errors.length / requestLogs.length * 100).toFixed(1) + '%',
    slowCount: requestLogs.filter((l) => l.duration > SLOW_THRESHOLD).length,
  }
}

// ── Web Vitals 采集 ─────────────────────────────────────
interface VitalMetric {
  name: string
  value: number
  rating: 'good' | 'needs-improvement' | 'poor'
}

const vitals: VitalMetric[] = []

/** 采集 Web Vitals（需要浏览器支持 PerformanceObserver） */
export function initWebVitals() {
  if (typeof window === 'undefined' || !('PerformanceObserver' in window)) return

  // LCP (Largest Contentful Paint)
  try {
    const lcpObserver = new PerformanceObserver((list) => {
      const entries = list.getEntries()
      const last = entries[entries.length - 1] as any
      if (last) {
        const value = last.startTime
        vitals.push({
          name: 'LCP',
          value: Math.round(value),
          rating: value < 2500 ? 'good' : value < 4000 ? 'needs-improvement' : 'poor',
        })
      }
    })
    lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true })
  } catch { /* not supported */ }

  // FID (First Input Delay)
  try {
    const fidObserver = new PerformanceObserver((list) => {
      const entry = list.getEntries()[0] as any
      if (entry) {
        const value = entry.processingStart - entry.startTime
        vitals.push({
          name: 'FID',
          value: Math.round(value),
          rating: value < 100 ? 'good' : value < 300 ? 'needs-improvement' : 'poor',
        })
      }
    })
    fidObserver.observe({ type: 'first-input', buffered: true })
  } catch { /* not supported */ }

  // CLS (Cumulative Layout Shift)
  try {
    let clsValue = 0
    const clsObserver = new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as any[]) {
        if (!entry.hadRecentInput) clsValue += entry.value
      }
      vitals.push({
        name: 'CLS',
        value: Math.round(clsValue * 1000) / 1000,
        rating: clsValue < 0.1 ? 'good' : clsValue < 0.25 ? 'needs-improvement' : 'poor',
      })
    })
    clsObserver.observe({ type: 'layout-shift', buffered: true })
  } catch { /* not supported */ }
}

/** 获取 Web Vitals 数据 */
export function getWebVitals(): VitalMetric[] {
  return [...vitals]
}
