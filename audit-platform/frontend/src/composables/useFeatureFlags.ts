// Feature: zero-downtime-deployment, Component 8
/**
 * Feature flag 消费 composable。
 * 读取 flag 状态控制功能可见性；admin 界面调 PUT 设置开关。
 * 使用 DB-backed /api/feature-flags-v2 端点（区别于旧内存开关 /api/feature-flags）。
 */
import { ref } from 'vue'
import { api } from '@/services/apiProxy'

export interface FeatureFlag {
  flag_key: string
  description: string | null
  enabled: boolean
  rollout_percentage: number
  whitelist_user_ids: string[] | null
}

export function useFeatureFlags() {
  const flags = ref<FeatureFlag[]>([])
  const loading = ref(false)

  async function fetchFlags() {
    loading.value = true
    try {
      const data = await api.get('/api/feature-flags-v2')
      flags.value = data as FeatureFlag[]
    } catch {
      // Silent failure — admin panel graceful degradation
    } finally {
      loading.value = false
    }
  }

  async function updateFlag(key: string, update: Partial<FeatureFlag>) {
    await api.put(`/api/feature-flags-v2/${key}`, update)
    await fetchFlags()
  }

  async function isEnabled(key: string): Promise<boolean> {
    try {
      const data = await api.get(`/api/feature-flags-v2/${key}`) as FeatureFlag
      return data.enabled
    } catch {
      return false // conservative: disabled if error
    }
  }

  return { flags, loading, fetchFlags, updateFlag, isEnabled }
}
