/**
 * useAProgramData — A 类程序表项目信息 + 适用性判定
 *
 * 从 GtAProgramConsole.vue 抽出（spec workpaper-frontend-large-component-split, Req 1）：
 * - 项目基本信息加载（含 business_category）：projectInfo state + loadProjectInfo
 * - B30 等仅限合并审计底稿的 applicable_when 标记 + isNotApplicable 覆盖判定
 *
 * 铁律：行为零变更、保响应式（ref/computed）；不在 composable 内 emit；依赖单向。
 *
 * @example
 * const data = useAProgramData(projectId)
 * // data.projectInfo / data.applicableWhen / data.isNotApplicable / data.loadProjectInfo()
 */
import { ref, computed, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { useProjectStore } from '@/stores/project'

export function useAProgramData(projectId: Ref<string>) {
  const projectStore = useProjectStore()
  const projectInfo = ref<Record<string, any>>({})
  // B30 等仅限合并审计的底稿：从 API 获取 applicable_when 标记
  const applicableWhen = ref<string | null>(null)

  /** 加载项目基本信息（含 business_category） */
  async function loadProjectInfo() {
    if (!projectId.value) return
    try {
      const res = await api.get(`/api/projects/${projectId.value}`)
      projectInfo.value = res?.data ?? res ?? {}
    } catch { /* ignore */ }
  }

  /** B30 等底稿 applicable_when="consolidated" 但项目为 standalone 时显示不适用覆盖 */
  const isNotApplicable = computed<boolean>(() => {
    if (!applicableWhen.value) return false
    if (applicableWhen.value === 'consolidated' && projectStore.auditScope !== 'consolidated') {
      return true
    }
    return false
  })

  return {
    projectInfo,
    applicableWhen,
    isNotApplicable,
    loadProjectInfo,
  }
}
