import { ref, onScopeDispose, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
export function useG5LonTerFormData(opts: { wpId: Ref<string>; projectId: Ref<string> }) {
  const isLoading = ref(false)
  const sheetCache = ref<Record<string, any>>({})
  async function loadAll() {
    isLoading.value = true
    try {
      const res = await api.get(`/api/workpapers/${opts.wpId.value}/render-config`, {
        params: { force_component_type: 'g5-long-term-receivable' }, _silent: true,
      } as any)
      const data = res?.data ?? res
      const sheets = data?.sheets ?? data?.data?.sheets ?? []
      for (const s of sheets) sheetCache.value[s.sheet_name || s.name || 'default'] = s.html_data ?? s
    } finally { isLoading.value = false }
  }
  function getSheet(name: string) { return sheetCache.value[name] ?? { rows: [] } }
  onScopeDispose(() => {})
  return { isLoading, sheetCache, loadAll, getSheet }
}
