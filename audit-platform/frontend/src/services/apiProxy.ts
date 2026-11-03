/**
 * API 代理层：统一解包、类型安全与受控 GET single-flight。
 *
 * `http.get` 返回 AxiosResponse；`api.get` 返回已解包业务数据。只有可证明语义等价的 GET 才共享在途 producer；
 * 每个调用者仍拿到自己的订阅 Promise，因此取消一个调用者不会取消其他调用者或底层请求。
 * 共享规则（白名单、取消边界、身份代际、新鲜度屏障、后加入者拷贝）在 `utils/getSingleFlight`，与 utils/http 同一份；
 * 本层有自己的在途表，生产者以 `_dedupe:false` 交给 http，不在 http 层再共享一次。
 */
import http from '@/utils/http'
import type { AxiosRequestConfig } from 'axios'
import {
  asAbortSignal,
  canceledError,
  copySharedData,
  planSharedGet,
  sharedGet,
  standaloneGet,
  type Flight,
  type SharedGetConfig,
} from '@/utils/getSingleFlight'

type ProxyGetConfig = SharedGetConfig

const _inflightGet = new Map<string, Flight<any>>()

function createProducer<T>(url: string, config?: ProxyGetConfig): Promise<T> {
  return http.get(url, config).then(({ data }) => data as T)
}

/**
 * GET single-flight with a conservative allowlist. Unsafe configs remain
 * independent and are explicitly passed to http with `_dedupe:false`.
 */
function get<T = any>(url: string, config?: ProxyGetConfig): Promise<T> {
  const signal = asAbortSignal(config?.signal)
  if (signal?.aborted) return Promise.reject(canceledError(config))
  const plan = planSharedGet(url, config)
  if (!plan) {
    const standalone: ProxyGetConfig = { ...(config ?? {}), _dedupe: false }
    return standaloneGet<T>(createProducer<T>(url, standalone), signal ?? undefined, config)
  }
  return sharedGet<T>(
    _inflightGet,
    plan,
    () => createProducer<T>(url, { ...plan.transport, _dedupe: false }),
    copySharedData,
    config,
  )
}

/** Vitest only: make flight lifetime explicit between examples. */
export function resetApiProxyInflightForTests(): void {
  _inflightGet.clear()
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

/** 下载永远独立发送：Blob 预览/下载不共享在途（每次点击都是一次真实下载）。 */
async function download(url: string, filename: string): Promise<void> {
  const response = await http.get(url, { responseType: 'blob', _dedupe: false } as ProxyGetConfig)
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
