/**
 * useImpactPreview — 影响预判 composable [enterprise-linkage 3.7]
 *
 * 输入防抖 300ms 后调用 /impact-preview，
 * 返回受影响的 TB 行/报表行/底稿列表。
 *
 * @example
 * ```ts
 * const { preview, loading, fetchPreview } = useImpactPreview(projectId, year)
 * fetchPreview('1001', 50000)
 * ```
 */
import { ref, onUnmounted, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { linkage as P } from '@/services/apiPaths'

export interface ImpactTbRow {
  row_code: string
  row_name: string
  current_audited?: number
  delta_amount?: number
}

export interface ImpactReportRow {
  report_type: string
  row_code: string
  row_name: string
}

export interface ImpactWorkpaper {
  wp_id: string
  wp_code: string
  wp_name: string
}

export interface ImpactPreviewResult {
  affected_tb_rows: ImpactTbRow[]
  affected_report_rows: ImpactReportRow[]
  affected_workpapers: ImpactWorkpaper[]
  has_final_report_warning: boolean
  unmapped_account: boolean
}

const DEBOUNCE_MS = 300

export function useImpactPreview(projectId: Ref<string>, year: Ref<number>) {
  const preview = ref<ImpactPreviewResult | null>(null)
  const loading = ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  function fetchPreview(accountCode: string, amount?: number) {
    // Clear previous timer
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }

    if (!accountCode) {
      preview.value = null
      return
    }

    loading.value = true

    debounceTimer = setTimeout(async () => {
      const pid = projectId.value
      if (!pid) {
        loading.value = false
        return
      }

      try {
        const params: Record<string, any> = {
          account_code: accountCode,
          year: year.value,
        }
        if (amount != null) params.amount = amount

        const data = await api.get(P.impactPreview(pid), { params })
        preview.value = data ?? null
      } catch {
        preview.value = null
      } finally {
        loading.value = false
      }
    }, DEBOUNCE_MS)
  }

  onUnmounted(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
  })

  return {
    preview,
    loading,
    fetchPreview,
  }
}
