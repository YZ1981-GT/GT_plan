/**
 * 生成审定报表（审定报表页与报表分析页共用）。
 * POST /api/reports/generate；前置条件不满足时后端回 400 + {message, prerequisite_action}，
 * 转成提示条并给出「去xx」按钮（菜单段见 PREREQUISITE_SEGMENTS）。
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { reports as P_rpt } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

/** 生成报表前置条件 → 本版式里去完成它的菜单 */
export const PREREQUISITE_SEGMENTS: Record<string, { segment: string; label: string }> = {
  import_ledger: { segment: 'ledger-import', label: '数据导入' },
  auto_match: { segment: 'mapping', label: '底稿映射' },
  recalc: { segment: 'trial-balance', label: '试算平衡表' },
}

export interface Prerequisite { message: string; segment?: string; label?: string }

export function useCitarReportGenerate(projectId: Ref<string>, year: Ref<number | null>) {
  const generating = ref(false)
  const prerequisite = ref<Prerequisite | null>(null)

  /** 成功返回 true（调用方据此重读数据） */
  async function generate(): Promise<boolean> {
    if (!year.value) return false
    generating.value = true
    prerequisite.value = null
    try {
      // _silent：错误由本页处理（前置条件转成提示条），不再叠一层全局弹窗
      const res: any = await api.post(
        P_rpt.generate,
        { project_id: projectId.value, year: year.value },
        { _silent: true, timeout: 300000 } as any,
      )
      ElMessage.success(`报表已生成：${res?.summary?.non_zero_rows ?? 0} 行有数`)
      return true
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (e?.response?.status === 400 && detail?.message) {
        const target = PREREQUISITE_SEGMENTS[detail.prerequisite_action || '']
        prerequisite.value = { message: detail.message, ...target }
      } else {
        handleApiError(e, '生成报表')
      }
      return false
    } finally {
      generating.value = false
    }
  }

  return { generating, prerequisite, generate }
}
