/**
 * useStaleImpactConfirm — 修改前影响预览确认 composable
 *
 * wp-traceability-panel Task 6.1
 * 在修改调整分录/底稿前弹出"将影响 N 张底稿 / M 报表行 / K 附注"预览，
 * 用户确认后才执行修改。
 *
 * Requirements: 5.1, 5.3
 *
 * @example
 * const { confirmBeforeModify } = useStaleImpactConfirm(projectId, year)
 * // 修改前调用
 * const confirmed = await confirmBeforeModify('1001', 50000)
 * if (confirmed) { doModify() }
 */
import { ref, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { apiProxy } from '@/utils/apiProxy'

export interface ImpactSummary {
  workpaperCount: number
  reportRowCount: number
  noteCount: number
  details: {
    workpapers: Array<{ wp_code: string; wp_name: string }>
    reportRows: Array<{ report_type: string; row_code: string; row_name: string }>
    notes: Array<{ section: string; title: string }>
  }
}

export function useStaleImpactConfirm(projectId: Ref<string>, year: Ref<number>) {
  const loading = ref(false)

  /**
   * 获取影响预览摘要
   */
  async function fetchImpactSummary(accountCode: string, amount?: number): Promise<ImpactSummary | null> {
    try {
      loading.value = true
      const data = await apiProxy.get(
        `/api/projects/${projectId.value}/linkage/impact-preview`,
        {
          params: {
            account_code: accountCode,
            year: year.value,
            amount: amount ?? 0,
          },
        }
      ) as Record<string, unknown>

      const workpapers = (data.affected_workpapers as Array<{ wp_code: string; wp_name: string }>) || []
      const reportRows = (data.affected_report_rows as Array<{ report_type: string; row_code: string; row_name: string }>) || []
      // 附注影响从 affected_notes 或推算
      const notes = (data.affected_notes as Array<{ section: string; title: string }>) || []

      return {
        workpaperCount: workpapers.length,
        reportRowCount: reportRows.length,
        noteCount: notes.length,
        details: { workpapers, reportRows, notes },
      }
    } catch {
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 修改前确认：弹出影响预览，用户确认后返回 true
   */
  async function confirmBeforeModify(accountCode: string, amount?: number): Promise<boolean> {
    const summary = await fetchImpactSummary(accountCode, amount)

    // 无影响或查询失败时直接放行
    if (!summary || (summary.workpaperCount === 0 && summary.reportRowCount === 0 && summary.noteCount === 0)) {
      return true
    }

    const parts: string[] = []
    if (summary.workpaperCount > 0) parts.push(`${summary.workpaperCount} 张底稿`)
    if (summary.reportRowCount > 0) parts.push(`${summary.reportRowCount} 报表行`)
    if (summary.noteCount > 0) parts.push(`${summary.noteCount} 附注`)

    const message = `此操作将影响 ${parts.join(' / ')}，是否继续？`

    try {
      await ElMessageBox.confirm(message, '影响预览', {
        confirmButtonText: '确认修改',
        cancelButtonText: '取消',
        type: 'warning',
      })
      return true
    } catch {
      return false
    }
  }

  return {
    loading,
    fetchImpactSummary,
    confirmBeforeModify,
  }
}
