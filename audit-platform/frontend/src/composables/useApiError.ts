/**
 * 统一 API 错误处理 — R1 Bug Fix 8
 *
 * 提供 parseApiError / showApiError 两个工具函数，
 * 统一处理后端返回的各种错误格式。
 */
import { ElMessage } from 'element-plus'

export interface ParsedApiError {
  code: string
  message: string
  detail?: any
}

/**
 * 解析 API 错误为统一结构。
 *
 * 支持格式：
 * 1. err.response.data.detail 为对象 { error_code, message }
 * 2. err.response.data.detail 为字符串
 * 3. err.message（网络错误等）
 * 4. 兜底 "未知错误"
 */
export function parseApiError(err: any): ParsedApiError {
  // FastAPI 标准错误格式：{ detail: { error_code, message } }
  const detail = err?.response?.data?.detail

  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    return {
      code: detail.error_code || detail.code || 'UNKNOWN',
      message: detail.message || detail.msg || '操作失败',
      detail,
    }
  }

  // detail 为字符串
  if (detail && typeof detail === 'string') {
    return {
      code: 'API_ERROR',
      message: detail,
    }
  }

  // FastAPI validation error: detail 为数组
  if (detail && Array.isArray(detail) && detail.length > 0) {
    const first = detail[0]
    const msg = first?.msg || '请求参数错误'
    return {
      code: 'VALIDATION_ERROR',
      message: msg,
      detail,
    }
  }

  // 网络错误 / axios 错误
  if (err?.message && typeof err.message === 'string') {
    // 常见网络错误中文化
    if (err.message.includes('Network Error')) {
      return { code: 'NETWORK_ERROR', message: '网络连接失败，请检查网络' }
    }
    if (err.message.includes('timeout')) {
      return { code: 'TIMEOUT', message: '请求超时，请稍后重试' }
    }
    return { code: 'REQUEST_ERROR', message: err.message }
  }

  return { code: 'UNKNOWN', message: '未知错误' }
}

/**
 * 解析并弹出 ElMessage.error 提示。
 */
export function showApiError(err: any): ParsedApiError {
  const parsed = parseApiError(err)
  ElMessage.error(parsed.message)
  return parsed
}
