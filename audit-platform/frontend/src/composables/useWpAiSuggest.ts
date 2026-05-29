/**
 * useWpAiSuggest — AI 辅助填写 composable
 *
 * 提供 AI 建议请求 + 采纳/修改/忽略交互逻辑 + ai_assisted 标记
 *
 * workpaper-editor-slimdown Task 7.1 / 7.3 / 7.4
 * Validates: Requirements US-5
 */

import { ref, computed } from 'vue'
import { apiProxy } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'

export interface AiSuggestion {
  text: string
  confidence: number
  fieldName: string
}

export type AiSuggestionAction = 'adopt' | 'modify' | 'ignore'

export interface UseWpAiSuggestOptions {
  wpId: string
  sheetName: string
}

/**
 * Feature flag: 是否启用 AI 建议功能
 * 通过 settings API 或环境变量控制
 */
const _aiEnabledCache = ref<boolean | null>(null)

async function checkAiEnabled(): Promise<boolean> {
  if (_aiEnabledCache.value !== null) return _aiEnabledCache.value
  try {
    const resp = await apiProxy.get('/api/feature-flags')
    const flags = resp?.flags || resp || {}
    _aiEnabledCache.value = !!flags.WP_AI_SERVICE_ENABLED
  } catch {
    // 如果无法获取 feature flags，默认禁用
    _aiEnabledCache.value = false
  }
  return _aiEnabledCache.value
}

export function useWpAiSuggest(options: UseWpAiSuggestOptions) {
  const { wpId, sheetName } = options

  const aiEnabled = ref(false)
  const aiLoading = ref(false)
  const currentSuggestion = ref<AiSuggestion | null>(null)
  const showSuggestionPanel = ref(false)
  const aiAssistedFields = ref<Set<string>>(new Set())

  // 初始化：检查 feature flag
  checkAiEnabled().then(enabled => {
    aiEnabled.value = enabled
  })

  /**
   * 请求 AI 建议
   */
  async function requestSuggestion(fieldName: string, existingContent: string = '') {
    if (!aiEnabled.value) return
    aiLoading.value = true
    currentSuggestion.value = null

    try {
      const resp = await apiProxy.post(`/api/workpapers/${wpId}/ai/suggest`, {
        sheet_name: sheetName,
        field_name: fieldName,
        existing_content: existingContent,
      })
      currentSuggestion.value = {
        text: resp.suggestion || '',
        confidence: resp.confidence || 0,
        fieldName,
      }
      showSuggestionPanel.value = true
    } catch (err: any) {
      if (err?.response?.status === 403) {
        ElMessage.warning('AI 服务未启用')
        aiEnabled.value = false
      } else {
        ElMessage.error('AI 建议请求失败')
      }
    } finally {
      aiLoading.value = false
    }
  }

  /**
   * 采纳建议 → 标记 ai_assisted
   */
  function adoptSuggestion(): string {
    if (!currentSuggestion.value) return ''
    const text = currentSuggestion.value.text
    aiAssistedFields.value.add(currentSuggestion.value.fieldName)
    showSuggestionPanel.value = false
    ElMessage.success('已采纳 AI 建议')
    return text
  }

  /**
   * 修改后采纳 → 标记 ai_assisted
   */
  function modifySuggestion(modifiedText: string): string {
    if (!currentSuggestion.value) return modifiedText
    aiAssistedFields.value.add(currentSuggestion.value.fieldName)
    showSuggestionPanel.value = false
    ElMessage.success('已采纳修改后的 AI 建议')
    return modifiedText
  }

  /**
   * 忽略建议
   */
  function ignoreSuggestion() {
    showSuggestionPanel.value = false
    currentSuggestion.value = null
    ElMessage.info('已忽略 AI 建议')
  }

  /**
   * 获取 ai_assisted_fields 列表（用于保存 payload）
   */
  const assistedFieldsList = computed(() => Array.from(aiAssistedFields.value))

  return {
    aiEnabled,
    aiLoading,
    currentSuggestion,
    showSuggestionPanel,
    aiAssistedFields,
    assistedFieldsList,
    requestSuggestion,
    adoptSuggestion,
    modifySuggestion,
    ignoreSuggestion,
  }
}
