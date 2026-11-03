/** S32～S35 页签负责人展示；姓名由索引接口统一解析，不改变委派。 */
import { ref } from 'vue'
import type { WpIndexItem } from '@/services/workpaperApi'

export function useBundleAssigneeLabels() {
  const names = ref<Record<string, string>>({})

  function setAssignees(items: WpIndexItem[]) {
    names.value = Object.fromEntries(
      items
        .filter(item => item.wp_id && item.assigned_to && item.assignee_name?.trim())
        .map(item => [item.wp_code, item.assignee_name!.trim()]),
    )
  }

  function tabLabel(label: string, wpCode?: string): string {
    const name = wpCode ? names.value[wpCode] : undefined
    return name ? `${label}（负责人：${name}）` : label
  }

  return { setAssignees, tabLabel }
}
