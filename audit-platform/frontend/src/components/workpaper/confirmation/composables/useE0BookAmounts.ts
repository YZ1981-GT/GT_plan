/**
 * useE0BookAmounts.ts — E0 品种矩阵账面金额取数
 *
 * 从 trial_balance API 获取各品种的期末余额，注入 buildE0SummaryMatrix。
 * 理财产品无固定科目 → 不预填（null）。
 */
import { ref, onMounted } from 'vue'
import http from '@/utils/http'
import { E0_BOOK_AMOUNT_SOURCES, type E0Category } from '../e0SummaryMatrix'

export function useE0BookAmounts(projectId: string | undefined) {
  const bookAmounts = ref<Partial<Record<E0Category, number>>>({})
  const loading = ref(false)

  async function fetch() {
    if (!projectId) return
    loading.value = true
    try {
      for (const [category, source] of Object.entries(E0_BOOK_AMOUNT_SOURCES)) {
        if (!source) continue // 理财产品 = null，跳过
        const res = await http.get('/api/trial-balance/query', {
          params: {
            project_id: projectId,
            standard_account_code: source.code,
            field: 'audited_amount',
          },
          _silent: true,
        } as any)
        const amount = (res as any)?.data?.amount ?? (res as any)?.amount
        if (typeof amount === 'number' && Number.isFinite(amount)) {
          bookAmounts.value[category as E0Category] = Math.abs(amount)
        }
      }
    } catch {
      // fail-open：取不到不影响其它功能
    } finally {
      loading.value = false
    }
  }

  onMounted(fetch)

  return { bookAmounts, loading, refresh: fetch }
}
