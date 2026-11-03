/**
 * useCurrentProjectId — 当前项目上下文的响应式单一来源
 *
 * D9（acnr-foundation-defect-closure，需求 11.1/11.4）：项目页内使用但组件本身无项目入参
 * 的 ACNR 消费者（选址器 / 导航 / 公式作用域等）用它拿当前 projectId，交给
 * `useAcnr(useCurrentProjectId())` 按项目订阅 SSE 失效并隔离解析缓存。
 *
 * 口径：路由参数 `projectId` 优先，其次项目 store；都没有返回空串（useAcnr 空值不建连接）。
 *
 * 取值上下文（段四审计 F4-03 / F4-16）：
 * - 路由只在有注入上下文时读取（`hasInjectionContext()`：组件 setup、`app.runWithContext`）；
 * - 项目 store 只在已有活动 Pinia 时读取（`getActivePinia()`）。
 * 两者都没有（在普通函数或纯函数单测里直接调用）时返回空串，不订阅、不影响 resolve。
 * 这是显式的条件分支，不吞异常：上下文存在时 useRoute / useProjectStore 抛出的错误照常抛出。
 */
import { computed, hasInjectionContext, type ComputedRef } from 'vue'
import { getActivePinia } from 'pinia'
import { useRoute, type RouteLocationNormalizedLoaded } from 'vue-router'
import { useProjectStore } from '@/stores/project'

export function useCurrentProjectId(): ComputedRef<string> {
  const route: RouteLocationNormalizedLoaded | undefined = hasInjectionContext()
    ? useRoute()
    : undefined
  const projectStore = getActivePinia() ? useProjectStore() : undefined
  return computed(
    () => (route?.params?.projectId as string) || projectStore?.projectId || '',
  )
}
