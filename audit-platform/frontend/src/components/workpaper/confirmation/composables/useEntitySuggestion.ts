/**
 * useEntitySuggestion — 被询证单位名称建议 composable
 *
 * 从 D0-2 底稿数据中提取已核实的单位名称，
 * 供 D0-1 的 entity_name 字段 autocomplete 使用。
 *
 * 当前为桩实现：D0-2 未实施时 graceful degrade 为空列表。
 */
import { ref, type Ref } from 'vue'

export function useEntitySuggestion(projectId: Ref<string>, wpId: Ref<string>) {
  const suggestions = ref<string[]>([])
  const loading = ref(false)

  async function fetchEntities() {
    // Try to fetch D0-2 sheet data from same workpaper
    // Gracefully degrade to empty if not available
    try {
      loading.value = true
      // API call to get sibling sheets' parsed_data
      // For now, return empty - will be connected when D0-2 is implemented
      // Future: GET /workpapers/{wpId}/siblings?sheet_type=D0-2&field=entity_name
      suggestions.value = []
    } catch {
      suggestions.value = []
    } finally {
      loading.value = false
    }
  }

  return { suggestions, loading, fetchEntities }
}
