/**
 * useCurrentProjectId — 当前项目上下文的响应式单一来源
 *
 * D9（acnr-foundation-defect-closure，需求 11.1/11.4）：项目页内使用但组件本身无项目入参
 * 的 ACNR 消费者（选址器 / 导航 / 公式作用域等）用它拿当前 projectId，交给
 * `useAcnr(useCurrentProjectId())` 按项目订阅 SSE 失效并隔离解析缓存。
 *
 * 口径：路由参数 `projectId` 优先，其次项目 store；都没有返回空串（useAcnr 空值不建连接）。
 * 只能在组件 setup / 其它 composable 的 setup 作用域内调用（内部用 useRoute）。
 */
import { computed, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '@/stores/project'

export function useCurrentProjectId(): ComputedRef<string> {
  const route = useRoute()
  const projectStore = useProjectStore()
  return computed(
    () => (route.params.projectId as string) || projectStore.projectId || '',
  )
}
