/**
 * GET 共享在途内核（spec platform-performance-residual-findings-closure R11）：utils/http 与 apiProxy 共用。
 *
 * 同一 GET（地址、规范化参数、返回类型、静默标记、登录身份代际相同，且配置只含白名单项）在飞时，后发者订阅先发者的
 * 那一次请求。原 utils/http 的去重是「后发者取消先发者」：同页两个组件取同一地址时，先发的一方静默失败（工时页「预算
 * 对比」恒空、编辑器误报「底稿文件尚未生成」、索引芯片显示「底稿不存在」……各处只能自建在途表绕开）。
 *
 * - 每个调用方一个订阅：自己的 signal 只取消自己；登录身份代际切换时所有订阅以取消结束；底层请求不带任何调用方 signal。
 * - 结果互不串改：第一个拿到结果的调用方拿原值，其余在结算时（任何调用方代码运行之前）拿拷贝。
 * - 新鲜度屏障：在途记录带创建时的屏障号；写请求开始 / 结束、收到项目事件推送时推进屏障，此前的在途记录不再给新请求
 *   共用（新请求另发），旧记录照常把结果交给已有订阅者 —— 「保存后重取」不会拿到保存前的数据。
 * - 成功、失败都移出在途表：不缓存结果。
 */
import { CanceledError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'
import { onRequestIdentityEpochChange, requestIdentityEpoch } from '@/services/requestIdentityEpoch'
import { clonePlain } from '@/utils/cloneable'

export type SharedGetConfig = AxiosRequestConfig & { _silent?: boolean; _dedupe?: boolean }

export interface Flight<T> {
  epoch: number
  barrier: number
  producer: Promise<T>
  /** 已交付的订阅数：第一个拿原值，其余拿拷贝 */
  delivered: number
}

export interface SharePlan {
  key: string
  epoch: number
  signal?: AbortSignal
  /** 交给生产者的配置：去掉调用方 signal（生产者不随任何一个调用方取消） */
  transport: SharedGetConfig
}

type Canonical = null | boolean | number | string | Canonical[] | { [key: string]: Canonical }
const NOT_CANONICAL = Symbol('not-canonical')
const SAFE_CONFIG_KEYS = new Set(['params', 'responseType', '_silent', '_dedupe', 'signal'])
const SAFE_RESPONSE_TYPES = new Set(['json', 'text', 'arraybuffer', 'blob', 'document'])

let shareBarrier = 0

/** 推进新鲜度屏障：此前在飞的 GET 不再给之后的请求共用（写请求开始 / 结束、项目事件推送时调用）。 */
export function advanceGetShareBarrier(): void {
  shareBarrier += 1
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== 'object') return false
  const proto = Object.getPrototypeOf(value)
  return proto === Object.prototype || proto === null
}

/** 只规范化纯查询值；Date、URLSearchParams、函数、带环结构等不猜等价性（返回 NOT_CANONICAL ⇒ 独立发送）。 */
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

/** 合法 AbortSignal → signal；没传 → undefined；传了别的东西 → null（不共享） */
export function asAbortSignal(value: unknown): AbortSignal | undefined | null {
  if (value == null) return undefined
  if (typeof value !== 'object') return null
  const signal = value as AbortSignal
  return typeof signal.aborted === 'boolean'
    && typeof signal.addEventListener === 'function'
    && typeof signal.removeEventListener === 'function'
    ? signal
    : null
}

/**
 * 能证明语义等价才给计划：配置只含白名单项、`_dedupe` 不为 false、参数可规范化、返回类型已知。
 * 拿不到计划的请求独立发送（调用方 `_dedupe:false` 是显式的独立请求边界）。
 */
export function planSharedGet(url: string, config?: SharedGetConfig): SharePlan | null {
  const raw = (config ?? {}) as Record<string, unknown>
  if (!Object.keys(raw).every((key) => SAFE_CONFIG_KEYS.has(key))) return null
  if (raw._dedupe === false || (raw._dedupe !== undefined && raw._dedupe !== true)) return null
  if (raw._silent !== undefined && typeof raw._silent !== 'boolean') return null
  const responseType = raw.responseType ?? 'json'
  if (typeof responseType !== 'string' || !SAFE_RESPONSE_TYPES.has(responseType)) return null
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
    transport: transport as SharedGetConfig,
  }
}

/** 订阅被取消 / 身份已切换时给调用方的错误（`isRequestCancelled` 认它） */
export function canceledError(config?: AxiosRequestConfig): CanceledError<unknown> {
  const error = new CanceledError<unknown>('请求已取消或登录身份已切换')
  if (config) error.config = config as InternalAxiosRequestConfig
  return error
}

/** 后加入者拿到的数据拷贝：普通对象 / 数组深拷贝，ArrayBuffer 复制，Blob / 字符串等不可变值原样共用。 */
export function copySharedData<T>(value: T): T {
  if (value instanceof ArrayBuffer) return value.slice(0) as unknown as T
  if (Array.isArray(value) || isPlainRecord(value)) return clonePlain(value)
  return value
}

/** 给每个调用方一个独立的取消边界；生产者照常跑完，剩下的订阅者照常拿结果。 */
function subscribe<T>(
  flight: Flight<T>,
  signal: AbortSignal | undefined,
  expectedEpoch: number,
  config: AxiosRequestConfig | undefined,
  copyForFollower: (value: T) => T,
): Promise<T> {
  if (signal?.aborted || requestIdentityEpoch() !== expectedEpoch) {
    return Promise.reject(canceledError(config))
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
    const onAbort = () => finish(reject, canceledError(config))
    signal?.addEventListener('abort', onAbort, { once: true })
    unsubscribe = onRequestIdentityEpochChange((next) => {
      if (next !== expectedEpoch) finish(reject, canceledError(config))
    })
    if (signal?.aborted || requestIdentityEpoch() !== expectedEpoch) {
      finish(reject, canceledError(config))
      return
    }
    flight.producer.then(
      (value) => {
        if (settled) return
        if (requestIdentityEpoch() !== expectedEpoch || flight.epoch !== expectedEpoch) {
          finish(reject, canceledError(config))
          return
        }
        // 结算回调按订阅顺序同步执行、早于任何调用方的后续代码 ⇒ 拷贝取自未被改动的原值
        const own = flight.delivered === 0 ? value : copyForFollower(value)
        flight.delivered += 1
        finish(resolve, own)
      },
      (error) => {
        if (requestIdentityEpoch() !== expectedEpoch || flight.epoch !== expectedEpoch) {
          finish(reject, canceledError(config))
        } else {
          finish(reject, error)
        }
      },
    )
  })
}

/** 共享在途：键相同、身份代际与新鲜度屏障都没变的在途记录就订阅它，否则用 `start()` 另起一个。 */
export function sharedGet<T>(
  flights: Map<string, Flight<T>>,
  plan: SharePlan,
  start: () => Promise<T>,
  copyForFollower: (value: T) => T,
  config?: AxiosRequestConfig,
): Promise<T> {
  if (plan.signal?.aborted) return Promise.reject(canceledError(config))
  let flight = flights.get(plan.key)
  if (!flight || flight.barrier !== shareBarrier || flight.epoch !== plan.epoch) {
    const created: Flight<T> = { epoch: plan.epoch, barrier: shareBarrier, producer: start(), delivered: 0 }
    flights.set(plan.key, created)
    // 成功、失败都清（then(clear, clear) 而不是 finally：清理本身不能变成未处理的拒绝）；只清自己那条
    const clear = () => {
      if (flights.get(plan.key) === created) flights.delete(plan.key)
    }
    created.producer.then(clear, clear)
    flight = created
  }
  return subscribe(flight, plan.signal, plan.epoch, config, copyForFollower)
}

/** 拿不到计划的独立请求：同样有调用方取消边界与身份代际边界（不拷贝：只有一个订阅者）。 */
export function standaloneGet<T>(producer: Promise<T>, signal: AbortSignal | undefined, config?: AxiosRequestConfig): Promise<T> {
  const epoch = requestIdentityEpoch()
  return subscribe({ epoch, barrier: shareBarrier, producer, delivered: 0 }, signal, epoch, config, (v) => v)
}
