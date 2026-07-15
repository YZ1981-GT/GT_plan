import { computed, onMounted, ref } from 'vue'
import http from '@/utils/http'

export interface DisclosureCapabilities {
  advanced_query: boolean
  disclosure_writeback: boolean
  historical_upload: boolean
  historical_upload_reason: string
}

const DEFAULT_REASON = '历史 Word/PDF 解析尚未实现'
const SAFE_DEFAULTS: DisclosureCapabilities = {
  advanced_query: false,
  disclosure_writeback: false,
  historical_upload: false,
  historical_upload_reason: DEFAULT_REASON,
}

export interface UseDisclosureCapabilitiesOptions {
  autoLoad?: boolean
}

export function useDisclosureCapabilities(options: UseDisclosureCapabilitiesOptions = {}) {
  const capabilities = ref<DisclosureCapabilities>({ ...SAFE_DEFAULTS })
  const loading = ref(false)
  const error = ref<string | null>(null)

  const historicalUploadDisabled = computed(() => !capabilities.value.historical_upload)
  const historicalUploadReason = computed(() =>
    capabilities.value.historical_upload
      ? ''
      : capabilities.value.historical_upload_reason || DEFAULT_REASON,
  )

  async function loadCapabilities(): Promise<DisclosureCapabilities> {
    loading.value = true
    error.value = null
    try {
      const response = await http.get('/api/disclosure-notes/capabilities', { _silent: true })
      const payload = response?.data?.data ?? response?.data ?? {}
      capabilities.value = {
        advanced_query: payload.advanced_query === true,
        disclosure_writeback: payload.disclosure_writeback === true,
        historical_upload: payload.historical_upload === true,
        historical_upload_reason: /[\u4e00-\u9fff]/.test(payload.historical_upload_reason ?? '')
          ? payload.historical_upload_reason
          : DEFAULT_REASON,
      }
    } catch {
      error.value = '无法确认历史上传能力，已安全禁用'
      capabilities.value = { ...SAFE_DEFAULTS, historical_upload_reason: error.value }
    } finally {
      loading.value = false
    }
    return capabilities.value
  }

  if (options.autoLoad !== false) onMounted(() => { void loadCapabilities() })

  return {
    capabilities,
    loading,
    error,
    historicalUploadDisabled,
    historicalUploadReason,
    loadCapabilities,
  }
}
