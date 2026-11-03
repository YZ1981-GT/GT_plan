/**
 * 结构化克隆前去掉 Vue 响应式代理（spec attachment-confirmation-evidence-loop 浏览器走查发现）
 *
 * Vue `reactive` / Pinia state 是 Proxy：`structuredClone`、`BroadcastChannel.postMessage` 遇到它抛
 * `DataCloneError: #<Object> could not be cloned`。走查实测：新开标签页向已登录标签页要会话时，回执里带了
 * `authStore.user`（响应式）⇒ 回执发不出去，新标签页 2 秒后跳登录页；G7 权益法「新增商誉 / 公允价值明细」
 * 克隆的载荷里有响应式行（`groups.flatMap(g => g.rows)`）同样抛错。
 *
 * 只展开普通对象与数组；Date / Map / Set / ArrayBuffer 等原样交给 structuredClone。带环的结构按同一引用还原。
 */
import { toRaw } from 'vue'

function plainTree(value: unknown, seen: WeakMap<object, unknown>): unknown {
  const raw = toRaw(value as object) as unknown
  if (raw === null || typeof raw !== 'object') return raw
  if (seen.has(raw)) return seen.get(raw)
  if (Array.isArray(raw)) {
    const out: unknown[] = []
    seen.set(raw, out)
    for (const item of raw) out.push(plainTree(item, seen))
    return out
  }
  if (Object.getPrototypeOf(raw) === Object.prototype || Object.getPrototypeOf(raw) === null) {
    const out: Record<string, unknown> = {}
    seen.set(raw, out)
    for (const [key, item] of Object.entries(raw)) out[key] = plainTree(item, seen)
    return out
  }
  return raw
}

/** 递归去掉响应式代理，得到可结构化克隆的值（不复制 Date 等内置对象，交给调用方的克隆）。 */
export function toCloneable<T>(value: T): T {
  return plainTree(value, new WeakMap()) as T
}

/** `structuredClone` 的安全版：入参可以是响应式数据。全仓克隆一律走这里（守卫：utils/__tests__/cloneable.spec.ts）。 */
export function clonePlain<T>(value: T): T {
  return structuredClone(toCloneable(value))
}
