/**
 * useLoading — 全局加载状态管理 [R3.9]
 *
 * 提供 withLoading 包装函数，自动管理 loading ref 的 true/false 切换，
 * 消除手动 try/finally 模板代码。
 */
import { ref, type Ref } from 'vue'

/**
 * 将异步函数包装为自动管理 loading 状态的版本。
 *
 * @param loadingRef - 一个 Ref<boolean>，调用期间自动设为 true，结束后恢复 false
 * @param fn - 要包装的异步函数
 * @returns 与原函数签名相同的包装函数
 *
 * @example
 * ```ts
 * const loading = ref(false)
 * const fetchData = withLoading(loading, async () => {
 *   rows.value = await api.getList()
 * })
 * // 调用时 loading 自动切换
 * await fetchData()
 * ```
 */
export function withLoading<T extends (...args: any[]) => Promise<any>>(
  loadingRef: Ref<boolean>,
  fn: T,
): (...args: Parameters<T>) => Promise<Awaited<ReturnType<T>>> {
  return async (...args: Parameters<T>) => {
    loadingRef.value = true
    try {
      return await fn(...args)
    } finally {
      loadingRef.value = false
    }
  }
}

/**
 * 创建一对 loading ref + withLoading 绑定的便捷 composable。
 *
 * @example
 * ```ts
 * const { loading, wrap } = useLoading()
 * const fetchData = wrap(async () => { ... })
 * ```
 */
export function useLoading() {
  const loading = ref(false)

  function wrap<T extends (...args: any[]) => Promise<any>>(fn: T) {
    return withLoading(loading, fn)
  }

  return { loading, wrap }
}
