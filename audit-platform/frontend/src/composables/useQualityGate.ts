/**
 * useQualityGate — quality_score 门禁 composable [wp-frontend-ux-polish Task 7]
 *
 * 功能：
 * - 7.1 提交复核时检查 quality_score 是否低于阈值，给出警告
 * - 7.2 PM 看板按 quality_score 排序（低分优先，找薄弱底稿）
 * - 7.3 统一 completion_rate 计算口径
 *
 * @example
 * const { checkBeforeReview, sortByQuality, qualityThreshold } = useQualityGate(projectId)
 */
import { ref, computed } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

export interface QualityScoreItem {
  wp_id: string
  wp_code: string
  wp_name?: string
  quality_score: number
  completion_rate: number
  consistency_status?: string
  review_status?: string
}

export interface QualityDashboard {
  total: number
  avg_score: number
  distribution: Record<string, number>
  by_status: Record<string, number>
}

/** 默认质量分阈值（低于此值提交复核时警告） */
const DEFAULT_QUALITY_THRESHOLD = 60

export function useQualityGate(projectId: string) {
  const qualityThreshold = ref(DEFAULT_QUALITY_THRESHOLD)
  const loading = ref(false)
  const dashboard = ref<QualityDashboard | null>(null)
  const workpapers = ref<QualityScoreItem[]>([])

  /**
   * 7.1 提交复核门禁：检查底稿 quality_score 是否低于阈值
   * @returns true = 通过门禁可继续提交；false = 用户取消
   */
  async function checkBeforeReview(wpId: string, wpCode: string): Promise<boolean> {
    try {
      const data: { quality_score: number; details?: Record<string, number> } = await api.get(
        `/api/projects/${projectId}/workpapers/${encodeURIComponent(wpId)}/quality-score`,
      )
      const score = data?.quality_score ?? 100

      if (score < qualityThreshold.value) {
        try {
          await ElMessageBox.confirm(
            `当前底稿 ${wpCode} 质量评分为 ${score} 分（阈值 ${qualityThreshold.value} 分），` +
            `建议先完善后再提交复核。\n\n确定继续提交吗？`,
            '质量评分偏低',
            {
              confirmButtonText: '仍然提交',
              cancelButtonText: '返回完善',
              type: 'warning',
            },
          )
          return true // 用户确认继续
        } catch {
          return false // 用户取消
        }
      }
      return true // 分数达标，直接通过
    } catch (e) {
      // 端点不可用时不阻塞提交
      handleApiError(e, '质量评分查询')
      return true
    }
  }

  /**
   * 7.2 PM 看板：按 quality_score 排序（低分优先）
   */
  const sortedByQuality = computed(() => {
    return [...workpapers.value].sort((a, b) => a.quality_score - b.quality_score)
  })

  /**
   * 加载项目底稿质量仪表盘数据
   */
  async function loadDashboard() {
    loading.value = true
    try {
      const data = await api.get(
        `/api/projects/${projectId}/workpapers/health-dashboard`,
      )
      dashboard.value = data?.quality || null
      workpapers.value = data?.workpapers || []
    } catch (e) {
      handleApiError(e, '加载质量看板')
    } finally {
      loading.value = false
    }
  }

  /**
   * 7.3 统一 completion_rate 计算：调用后端统一接口
   * 替代前端各处自行计算的分散逻辑
   */
  async function getUnifiedCompletionRate(wpId: string): Promise<number> {
    try {
      const data = await api.get(
        `/api/projects/${projectId}/workpapers/${encodeURIComponent(wpId)}/completion-rate`,
      )
      return data?.completion_rate ?? 0
    } catch {
      return 0
    }
  }

  /**
   * 批量获取项目所有底稿的 completion_rate（统一口径）
   */
  async function batchCompletionRates(): Promise<QualityScoreItem[]> {
    try {
      const data: QualityScoreItem[] = await api.get(
        `/api/projects/${projectId}/workpapers/quality-scores`,
      )
      workpapers.value = data || []
      return data || []
    } catch (e) {
      handleApiError(e, '批量质量评分')
      return []
    }
  }

  return {
    qualityThreshold,
    loading,
    dashboard,
    workpapers,
    sortedByQuality,
    checkBeforeReview,
    loadDashboard,
    getUnifiedCompletionRate,
    batchCompletionRates,
  }
}
