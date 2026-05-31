/**
 * API 代理层 — 统一解包 + 类型安全
 * 
 * 用法：将页面中的 `import http from '@/utils/http'` 替换为 `import { api } from '@/services/apiProxy'`
 * 
 * 区别：
 * - http.get(url) 返回 AxiosResponse，需要 `const { data } = await http.get(url)`
 * - api.get(url) 直接返回业务数据，`const data = await api.get(url)`
 * 
 * 这样页面不再需要双层解包
 *
 * GET 请求 in-flight 共享：相同 URL 同时发起时返回同一个 Promise（避免 axios dedup 取消旧请求 + 重复网络）
 */
import http from '@/utils/http'
import type { AxiosRequestConfig } from 'axios'

const _inflightGet = new Map<string, Promise<any>>()

async function get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
  // 仅对无 config 的纯 GET 启用共享（带 params/headers 时 key 不稳定不缓存）
  const shouldShare = !config
  if (shouldShare && _inflightGet.has(url)) {
    return _inflightGet.get(url) as Promise<T>
  }
  const p = (async () => {
    try {
      const { data } = await http.get(url, config)
      return data as T
    } finally {
      if (shouldShare) _inflightGet.delete(url)
    }
  })()
  if (shouldShare) _inflightGet.set(url, p)
  return p
}

async function post<T = any>(url: string, body?: any, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await http.post(url, body, config)
  return data as T
}

async function put<T = any>(url: string, body?: any, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await http.put(url, body, config)
  return data as T
}

async function patch<T = any>(url: string, body?: any, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await http.patch(url, body, config)
  return data as T
}

async function del<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await http.delete(url, config)
  return data as T
}

/** 下载文件（blob） */
async function download(url: string, filename: string): Promise<void> {
  const response = await http.get(url, { responseType: 'blob' })
  const blob = new Blob([response.data])
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

export const api = { get, post, put, patch, delete: del, download }
/** 兼容别名：部分组件 import { apiProxy } from '@/services/apiProxy' */
export const apiProxy = api
export default api
