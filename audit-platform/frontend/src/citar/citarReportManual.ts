/**
 * 审定报表手工值（spec citar-table-manual-edit R6）：PUT /api/reports/{pid}/{year}/manual。
 * 改 / 恢复一批格后后端随即重新生成报表（合计按手工值重算）；报表未生成返回 409。
 */
import { api } from '@/services/apiProxy'
import { reports as P_rpt } from '@/services/apiPaths'

export interface ManualReportItem {
  report_type: string
  row_code: string
  column: 'current' | 'prior'
  /** null = 清空成空白 */
  value?: number | null
  /** 去掉手工值，恢复自动值 */
  restore?: boolean
}

export function saveReportManualValues(projectId: string, year: number, items: ManualReportItem[]): Promise<{ changed: number }> {
  return api.put(P_rpt.manual(projectId, year), { items }, { _silent: true, timeout: 300000 } as any) as Promise<{ changed: number }>
}
