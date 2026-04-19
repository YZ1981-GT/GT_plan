/**
 * Web Vitals 性能指标收集 + 前端性能告警
 *
 * Phase 8 Task 8.1 & 8.2:
 * - 收集 FCP, LCP, TTI 使用 Performance API
 * - 超阈值时通过 ElNotification 告警
 * - 上报到后端 POST /api/admin/performance-metrics（降级 console.log）
 */

import { ElNotification } from 'element-plus'

export interface WebVitalMetric {
  name: string
  value: number
  unit: string
  timestamp: number
}

// 告警阈值
const THRESHOLDS = {
  LCP: 4000,  // ms — Largest Contentful Paint
  FCP: 3000,  // ms — First Contentful Paint
  TTI: 5000,  // ms — Time to Interactive (approx)
}

const collectedMetrics: WebVitalMetric[] = []

function checkThreshold(metric: WebVitalMetric) {
  const threshold = (THRESHOLDS as Record<string, number>)[metric.name]
  if (threshold && metric.value > threshold) {
    ElNotification({
      title: '性能告警',
      message: `${metric.name} = ${metric.value.toFixed(0)}ms 超过阈值 ${threshold}ms，页面加载较慢`,
      type: 'warning',
      duration: 6000,
    })
  }
}

function reportMetric(metric: WebVitalMetric) {
  collectedMetrics.push(metric)
  checkThreshold(metric)

  // 尝试上报后端，失败降级 console.log
  try {
    const token = localStorage.getItem('token')
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    fetch('/api/admin/performance-metrics', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        metric_name: metric.name,
        metric_value: metric.value,
        unit: metric.unit,
        source: 'frontend',
        timestamp: metric.timestamp,
        url: window.location.pathname,
      }),
    }).catch(() => {
      // 静默降级
    })
  } catch {
    // 静默降级
  }
}

/**
 * 收集 FCP（First Contentful Paint）
 */
function collectFCP() {
  try {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.name === 'first-contentful-paint') {
          reportMetric({
            name: 'FCP',
            value: entry.startTime,
            unit: 'ms',
            timestamp: Date.now(),
          })
          observer.disconnect()
        }
      }
    })
    observer.observe({ type: 'paint', buffered: true })
  } catch {
    // PerformanceObserver not supported
  }
}

/**
 * 收集 LCP（Largest Contentful Paint）
 */
function collectLCP() {
  try {
    const observer = new PerformanceObserver((list) => {
      const entries = list.getEntries()
      // LCP 取最后一个（最终值）
      const last = entries[entries.length - 1]
      if (last) {
        reportMetric({
          name: 'LCP',
          value: last.startTime,
          unit: 'ms',
          timestamp: Date.now(),
        })
      }
    })
    observer.observe({ type: 'largest-contentful-paint', buffered: true })

    // LCP 在用户交互后不再更新，延迟断开
    setTimeout(() => observer.disconnect(), 15000)
  } catch {
    // PerformanceObserver not supported
  }
}

/**
 * 收集 TTI（Time to Interactive）近似值
 * 使用 domInteractive 作为近似
 */
function collectTTI() {
  try {
    const check = () => {
      const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
      if (nav && nav.domInteractive > 0) {
        reportMetric({
          name: 'TTI',
          value: nav.domInteractive,
          unit: 'ms',
          timestamp: Date.now(),
        })
      } else {
        // 页面还没加载完，延迟重试
        setTimeout(check, 1000)
      }
    }
    // 等 DOM 加载完再采集
    if (document.readyState === 'complete') {
      check()
    } else {
      window.addEventListener('load', () => setTimeout(check, 100))
    }
  } catch {
    // fallback
  }
}

/**
 * 初始化 Web Vitals 收集
 * 在 main.ts 中调用一次即可
 */
export function initWebVitals() {
  collectFCP()
  collectLCP()
  collectTTI()
}

/**
 * 获取已收集的指标（供调试/展示用）
 */
export function getCollectedMetrics(): WebVitalMetric[] {
  return [...collectedMetrics]
}

export default { initWebVitals, getCollectedMetrics }
