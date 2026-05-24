/**
 * Batch Query Controller — Promise.allSettled + 最大并发 5 限流
 *
 * Req 1: 多底稿批量查询
 * - 按 wp_code 拆分为 N 次请求
 * - 最大并发 5（超过 5 个时排队等待）
 * - 任一子请求失败不阻塞其它
 * - 分组结果按 wp_code 聚合
 */

import { ref } from 'vue'
import axios from 'axios'
import { customQuery } from '@/services/apiPaths'

export interface BatchQueryParams {
  wpCodes: string[]
  projectId: string
  year?: number
  filters?: Record<string, any>
  cellRange?: string
  sheetName?: string
}

export interface BatchResultItem {
  rows?: Record<string, any>[]
  columns?: string[]
  total?: number
  source?: string
  error?: string
}

export interface BatchQueryResult {
  results: Record<string, BatchResultItem>
  totalSuccess: number
  totalFailed: number
}

const MAX_CONCURRENCY = 5

/**
 * 限流执行器：最多同时 maxConcurrency 个 Promise 在飞
 */
export async function executeWithConcurrencyLimit<T>(
  tasks: (() => Promise<T>)[],
  maxConcurrency: number = MAX_CONCURRENCY,
): Promise<PromiseSettledResult<T>[]> {
  const results: PromiseSettledResult<T>[] = new Array(tasks.length)
  let nextIndex = 0

  async function worker() {
    while (nextIndex < tasks.length) {
      const idx = nextIndex++
      try {
        const value = await tasks[idx]()
        results[idx] = { status: 'fulfilled', value }
      } catch (reason: any) {
        results[idx] = { status: 'rejected', reason }
      }
    }
  }

  // 启动 min(maxConcurrency, tasks.length) 个 worker
  const workerCount = Math.min(maxConcurrency, tasks.length)
  const workers: Promise<void>[] = []
  for (let i = 0; i < workerCount; i++) {
    workers.push(worker())
  }
  await Promise.all(workers)

  return results
}

export function useBatchQuery() {
  const loading = ref(false)
  const batchResult = ref<BatchQueryResult | null>(null)

  async function executeBatch(params: BatchQueryParams): Promise<BatchQueryResult> {
    loading.value = true
    batchResult.value = null

    try {
      const { wpCodes, projectId, year, filters = {}, cellRange, sheetName } = params

      // 构建每个 wp_code 的请求任务
      const tasks = wpCodes.map((wpCode) => {
        return async (): Promise<{ wpCode: string; data: BatchResultItem }> => {
          const source = sheetName
            ? `workpaper:${wpCode}|${sheetName}`
            : `workpaper:${wpCode}`

          const requestBody: Record<string, any> = {
            project_id: projectId,
            year: year ?? new Date().getFullYear(),
            source,
            filters: { ...filters, wp_code: wpCode },
          }

          if (cellRange) {
            requestBody.filters.cell_range = cellRange
          }
          if (sheetName) {
            requestBody.filters.sheet_name = sheetName
          }

          const resp = await axios.post(customQuery.execute, requestBody)
          return { wpCode, data: resp.data }
        }
      })

      // 限流执行
      const settled = await executeWithConcurrencyLimit(tasks, MAX_CONCURRENCY)

      // 聚合结果
      const results: Record<string, BatchResultItem> = {}
      let totalSuccess = 0
      let totalFailed = 0

      for (const item of settled) {
        if (item.status === 'fulfilled') {
          const { wpCode, data } = item.value
          if (data.error) {
            results[wpCode] = { error: data.error, rows: [], columns: [], total: 0 }
            totalFailed++
          } else {
            results[wpCode] = data
            totalSuccess++
          }
        } else {
          // rejected — 从 reason 中提取 wpCode（如果可能）
          const reason = item.reason
          const errMsg = reason?.response?.data?.detail || reason?.message || String(reason)
          // 尝试从 tasks 中找到对应的 wpCode
          const idx = settled.indexOf(item)
          const wpCode = wpCodes[idx] || `unknown_${idx}`
          results[wpCode] = { error: errMsg, rows: [], columns: [], total: 0 }
          totalFailed++
        }
      }

      const result: BatchQueryResult = { results, totalSuccess, totalFailed }
      batchResult.value = result
      return result
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    batchResult,
    executeBatch,
  }
}
