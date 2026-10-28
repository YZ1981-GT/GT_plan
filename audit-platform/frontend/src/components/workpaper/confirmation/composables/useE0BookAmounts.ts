/**
 * useE0BookAmounts.ts — E0 品种矩阵账面金额取数
 *
 * 经试算表唯一入口取各品种的期末审定数（科目及其明细之和、取绝对值），注入 buildE0SummaryMatrix。
 * 理财产品无固定科目 → 不预填（null）。年度缺省由后端按项目审计年度取。
 * 原先逐品种请求后端没有的 `/api/trial-balance/query` ⇒ 恒 404 被吞，账面金额恒空
 * （spec post-push-residual-defect-closure R1）。
 */
import { ref, onMounted } from 'vue'
import { fetchTrialBalanceRows, tbSumUnder } from '@/services/trialBalanceRows'
import { E0_BOOK_AMOUNT_SOURCES, type E0Category } from '../e0SummaryMatrix'

export function useE0BookAmounts(projectId: string | undefined) {
  const bookAmounts = ref<Partial<Record<E0Category, number>>>({})
  const loading = ref(false)

  async function fetch() {
    if (!projectId) return
    loading.value = true
    try {
      // 理财产品 = null，跳过；其余品种一次取齐
      const sources = (Object.entries(E0_BOOK_AMOUNT_SOURCES) as Array<[E0Category, { code: string } | null]>)
        .filter((e): e is [E0Category, { code: string }] => e[1] != null)
      const { rows } = await fetchTrialBalanceRows(projectId, { accountPrefix: sources.map(([, s]) => s.code) })
      for (const [category, source] of sources) {
        const amount = tbSumUnder(rows, source.code, 'audited_amount')
        if (amount != null) bookAmounts.value[category] = Math.abs(amount)
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
