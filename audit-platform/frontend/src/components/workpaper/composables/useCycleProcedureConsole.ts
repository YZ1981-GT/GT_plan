/**
 * D/F/G 等循环程序表 selfLoad — 拉取 a-program-console render-config
 */
import { ref, onMounted, toValue, type MaybeRefOrGetter } from 'vue'
import { api } from '@/services/apiProxy'

export function useCycleProcedureConsole(options: {
  wpId: MaybeRefOrGetter<string>
  htmlData?: MaybeRefOrGetter<any>
  sheetLabel: string
  sheetCode: string
}) {
  const isLoading = ref(true)
  const programData = ref<any>(null)

  async function selfLoad(): Promise<void> {
    const htmlData = toValue(options.htmlData)
    // 空 programs 不能短路：否则 F2-21A 等灵魂表会卡在「暂无内容」
    if (htmlData?.programs?.length || (htmlData?.schema && htmlData.programs === undefined)) {
      programData.value = htmlData
      isLoading.value = false
      return
    }

    const wpId = toValue(options.wpId)
    if (!wpId) {
      isLoading.value = false
      return
    }

    try {
      const res = await api.get(`/api/workpapers/${wpId}/render-config`, {
        params: {
          force_component_type: 'a-program-console',
          sheet_name: options.sheetLabel,
        },
        _silent: true,
      } as any)
      const renderData = res?.data ?? res
      const sheets = renderData?.sheets ?? renderData?.data?.sheets ?? []
      const codeRe = new RegExp(
        options.sheetCode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
        'i',
      )
      const hit = sheets.find((s: any) => codeRe.test(s.sheet_name || s.name || ''))
      programData.value = hit?.html_data ?? sheets[0]?.html_data ?? renderData
    } catch (err) {
      console.warn(`[${options.sheetCode} procedure] selfLoad failed:`, err)
    } finally {
      isLoading.value = false
    }
  }

  onMounted(() => { void selfLoad() })

  return { isLoading, programData, reload: selfLoad }
}

export default useCycleProcedureConsole
