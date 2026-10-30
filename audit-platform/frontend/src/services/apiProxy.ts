/**
 * API 代理层：统一解包、类型安全与受控 GET single-flight。
 *
 * `http.get` 返回 AxiosResponse；`api.get` 返回已解包业务数据。只有可证明语义
 * 等价的 GET 才共享在途 producer；每个调用者仍拿到自己的订阅 Promise，因此取消
 * 一个调用者不会取消其他调用者或底层请求。
 */
import http from '@/utils/http'
import {
  CanceledError,
  type AxiosRequestConfig,
} from 'axios'
import {
  onRequestIdentityEpochChange,
  requestIdentityEpoch,
} from '@/services/requestIdentityEpoch'

type ProxyGetConfig = AxiosRequestConfig & {
  _silent?: boolean
  _dedupe?: boolean
}

type Flight = {
  epoch: number
  producer: Promise<any>
}

type Canonical = null | boolean | number | string | Canonical[] | { [key: string]: Canonical }
const NOT_CANONICAL = Symbol('not-canonical')
const _inflightGet = new Map<string, Flight>()
const _SAFE_GET_CONFIG_KEYS = new Set(['params', 'responseType', '_silent', '_dedupe', 'signal'])
const _SAFE_RESPONSE_TYPES = new Set(['json', 'text', 'arraybuffer', 'blob', 'document'])

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== 'object') return false
  const proto = Object.getPrototypeOf(value)
  return proto === Object.prototype || proto === null
}

/** Canonicalize only plain query values. Unknown runtime types bypass sharing. */
function canonicalValue(value: unknown, active: Set<object> = new Set()): Canonical | typeof NOT_CANONICAL {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') return Number.isFinite(value) ? value : NOT_CANONICAL
  if (Array.isArray(value)) {
    if (active.has(value)) return NOT_CANONICAL
    active.add(value)
    try {
      const out: Canonical[] = []
      for (const item of value) {
        const next = canonicalValue(item, active)
        if (next === NOT_CANONICAL) return NOT_CANONICAL
        out.push(next)
      }
      return out
    } finally {
      active.delete(value)
    }
  }
  if (!isPlainRecord(value) || active.has(value)) return NOT_CANONICAL
  active.add(value)
  try {
    const out: Record<string, Canonical> = {}
    for (const key of Object.keys(value).sort()) {
      const next = canonicalValue(value[key], active)
      if (next === NOT_CANONICAL) return NOT_CANONICAL
      out[key] = next
    }
    return out
  } finally {
    active.delete(value)
  }
}

function canonicalParams(params: unknown): string | null {
  if (params == null) return '{}'
  const value = canonicalValue(params)
  return value === NOT_CANONICAL ? null : JSON.stringify(value)
}

function asAbortSignal(value: unknown): AbortSignal | undefined | null {
  if (value == null) return undefined
  if (typeof value !== 'object') return null
  const signal = value as AbortSignal
  return typeof signal.aborted === 'boolean'
    && typeof signal.addEventListener === 'function'
    && typeof signal.removeEventListener === 'function'
    ? signal
    : null
}

type SharePlan = {
  key: string
  epoch: number
  signal?: AbortSignal
  producerConfig: ProxyGetConfig
}

/**
 * Return a plan only when every meaningful config field is known and stable.
 * Caller `_dedupe:false` is an explicit independent-request boundary.
 */
function sharePlan(url: string, config?: ProxyGetConfig): SharePlan | null {
  const raw = config ?? {}
  if (!Object.keys(raw).every((key) => _SAFE_GET_CONFIG_KEYS.has(key))) return null
  if (raw._dedupe === false || (raw._dedupe !== undefined && raw._dedupe !== true)) return null
  if (raw._silent !== undefined && typeof raw._silent !== 'boolean') return null
  const responseType = raw.responseType ?? 'json'
  if (typeof responseType !== 'string' || !_SAFE_RESPONSE_TYPES.has(responseType)) return null
  const signal = asAbortSignal(raw.signal)
  if (signal === null) return null
  const params = canonicalParams(raw.params)
  if (params === null) return null
  const epoch = requestIdentityEpoch()
  const { signal: _callerSignal, ...transport } = raw
  return {
    key: JSON.stringify(['v1', epoch, url, responseType, Boolean(raw._silent), params]),
    epoch,
    signal,
    // A single producer must not enter utils/http's cancel-previous pending map.
    producerConfig: { ...transport, _dedupe: false },
  }
}

function canceled(config?: AxiosRequestConfig): CanceledError {
  return new CanceledError('请求已取消或登录身份已切换', config)
}


/**
 * Give each caller a separate cancellation boundary around a shared producer.
 * The producer deliberately continues when a subscriber aborts: the remaining
 * subscriber(s) still receive the response and the in-flight entry self-cleans.
 */
function subscribe<T>(flight: Flight, signal: AbortSignal | undefined, expectedEpoch: number, config?: AxiosRequestConfig): Promise<T> {
  if (signal?.aborted || requestIdentityEpoch() !== expectedEpoch) {
    return Promise.reject(canceled(config))
  }
  return new Promise<T>((resolve, reject) => {
    let settled = false
    let unsubscribe = () => {}
    const finish = (callback: (value: any) => void, value: any) => {
      if (settled) return
      settled = true
      signal?.removeEventListener('abort', onAbort)
      unsubscribe()
      callback(value)
    }
    const onAbort = () => finish(reject, canceled(config))
    signal?.addEventListener('abort', onAbort, { once: true })
    unsubscribe = onRequestIdentityEpochChange((next) => {
      if (next !== expectedEpoch) finish(reject, canceled(config))
    })
    // An identity switch cannot normally interleave with this synchronous setup,
    // but checking again makes the boundary explicit for future integrations.
    if (signal?.aborted || requestIdentityEpoch() !== expectedEpoch) {
      finish(reject, canceled(config))
      return
    }
    flight.producer.then(
      (value) => {
        if (requestIdentityEpoch() !== expectedEpoch || flight.epoch !== expectedEpoch) {
          finish(reject, canceled(config))
        } else {
          finish(resolve, value)
        }
      },
      (error) => {
        if (requestIdentityEpoch() !== expectedEpoch || flight.epoch !== expectedEpoch) {
          finish(reject, canceled(config))
        } else {
          finish(reject, error)
        }
      },
    )
  })
}

function createProducer<T>(url: string, config?: ProxyGetConfig): Promise<T> {
  return http.get(url, config).then(({ data }) => data as T)
}

/**
 * GET single-flight with a conservative allowlist. Unsafe configs remain
 * independent and are explicitly passed to http with `_dedupe:false`, so they
 * do not fall back to the legacy cancel-previous map.
 */
function get<T = any>(url: string, config?: ProxyGetConfig): Promise<T> {
  const plan = sharePlan(url, config)
  const signal = asAbortSignal(config?.signal)
  if (signal?.aborted) return Promise.reject(canceled(config))

  if (!plan) {
    const epoch = requestIdentityEpoch()
    const standalone: ProxyGetConfig = { ...(config ?? {}), _dedupe: false }
    return subscribe<T>({ epoch, producer: createProducer<T>(url, standalone) }, signal ?? undefined, epoch, config)
  }

  let flight = _inflightGet.get(plan.key)
  if (!flight) {
    const producer = createProducer<T>(url, plan.producerConfig)
    flight = { epoch: plan.epoch, producer }
    _inflightGet.set(plan.key, flight)
    // Success and failure both clear. Use `then(clear, clear)`, not `finally`,
    // so cleanup itself cannot become an unhandled rejected promise.
    const clear = () => {
      if (_inflightGet.get(plan.key) === flight) _inflightGet.delete(plan.key)
    }
    producer.then(clear, clear)
  }
  return subscribe<T>(flight, plan.signal, plan.epoch, config)
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

/** 下载永远独立发送：Blob 预览/下载不得被默认 GET 去重互相取消。 */
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
