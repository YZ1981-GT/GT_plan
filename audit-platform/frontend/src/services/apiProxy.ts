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

/**
 * 在途表键 = `{l|s}{d|n}|url`：l/s = 是否静默，d/n = 是否参与 utils/http 的 GET 去重（`_dedupe:false` 为 n）。
 * 只有 config 为空、或只带 `_silent` / `_dedupe` 标志时共享（带 params / headers / validateStatus 等不共享，行为不变）。
 *
 * spec procedure-chain-hardening-and-java-contracts R16：附加标志原先一律绕开共享 ⇒ 编辑器打开时 GtWpRenderer 与壳的侧栏
 * 同时取 render-config 各发一条。现在静默调用方可以加入同 URL 的任何在途请求（失败时那条请求自己按原样提示，
 * 静默方照常自行处理，不会多出提示）；非静默调用方只加入同类非静默请求 —— 加入静默请求会丢掉它该有的错误提示。
 */
const _inflightGet = new Map<string, Promise<any>>()
const _SHARE_FLAGS = new Set(['_silent', '_dedupe'])

function _shareKind(config?: AxiosRequestConfig): string | null {
  if (!config) return 'ld'
  if (!Object.keys(config).every((k) => _SHARE_FLAGS.has(k))) return null
  const c = config as { _silent?: boolean; _dedupe?: boolean }
  return `${c._silent ? 's' : 'l'}${c._dedupe === false ? 'n' : 'd'}`
}

async function get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const kind = _shareKind(config)
  if (kind) {
    const joinable = kind[0] === 's' ? ['ld', 'ln', 'sd', 'sn'] : [kind]
    for (const k of joinable) {
      const pending = _inflightGet.get(`${k}|${url}`)
      if (pending) return pending as Promise<T>
    }
  }
  const p = http.get(url, config).then(({ data }) => data as T)
  if (kind) {
    const key = `${kind}|${url}`
    _inflightGet.set(key, p)
    // 成功失败都移除；then(clear, clear) 而非 finally，派生 Promise 不会成为未处理拒绝
    const clear = () => { if (_inflightGet.get(key) === p) _inflightGet.delete(key) }
    p.then(clear, clear)
  }
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
