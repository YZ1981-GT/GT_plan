/**
 * useG5FormData — G5 长期应收款数据加载/保存/selfLoad
 *
 * Spec: .kiro/specs/g5-long-term-receivable/
 * Task: 3.2
 */
import { ref, onScopeDispose, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export interface UseG5FormDataOptions {
  wpId: ComputedRef<string> | Ref<string>
  projectId: ComputedRef<string> | Ref<string>
  htmlData?: ComputedRef<any> | Ref<any>
}

export function useG5FormData(opts: UseG5FormDataOptions) {
  const { wpId, projectId, htmlData } = opts

  const data = ref<any>(null)
  const isLoading = ref(false)

  async function load(): Promise<void> {
    // 如果 htmlData 已提供，直接使用
    if (htmlData?.value) {
      data.value = htmlData.value
      return
    }
    // selfLoad: bundle内嵌场景 htmlData 为 null
    if (!wpId.value) return
    isLoading.value = true
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/render-config`, {
        params: { force_component_type: 'g5-long-term-receivable' },
        _silent: true,
      } as any)
      const payload = res?.data ?? res
      data.value = payload
    } catch {
      // selfLoad 失败不阻塞
    } finally {
      isLoading.value = false
    }
  }

  return { data, isLoading, load }
}

export default useG5FormData
