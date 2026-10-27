import { ref, type ComputedRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getReportExcelUrl, type ReportRow } from '@/services/auditPlatformApi'
import { reports as reportPaths } from '@/services/apiPaths/report'
import { downloadFile } from '@/utils/http'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface UseReportExportOptions {
  projectId: ComputedRef<string>
  /** 审计年度；项目没填为 null ⇒ 导出提示去填年度、不发请求 */
  year: ComputedRef<number | null>
  activeTab: Ref<string>
  rows: Ref<ReportRow[]>
  activeTabLabel: ComputedRef<string>
  fetchReport: () => Promise<void>
}

export interface UseReportExportReturn {
  onExportExcel: () => void
  onExportAllExcel: () => void
  onExportAllUnadjusted: () => void
  copyReportTable: () => void
  showReportImport: Ref<boolean>
  onReportImported: () => void
}

// ─── Composable ─────────────────────────────────────────────────────────────

export function useReportExport(options: UseReportExportOptions): UseReportExportReturn {
  const { projectId, year, activeTab, rows, fetchReport } = options

  const showReportImport = ref(false)

  function onReportImported() {
    showReportImport.value = false
    fetchReport()
  }

  /** 导出按年度出：项目没填审计年度时提示去填，返回 null */
  function exportYear(): number | null {
    const y = year.value
    if (y == null) ElMessage.warning(MISSING_AUDIT_YEAR_MESSAGE)
    return y
  }

  function onExportExcel() {
    const y = exportYear()
    if (y == null) return
    import('@/services/commonApi').then(({ downloadFileAsBlob }) => {
      const url = getReportExcelUrl(projectId.value, y, activeTab.value)
      downloadFileAsBlob(url, `报表_${activeTab.value}_${y}.xlsx`)
    })
  }

  function onExportAllExcel() {
    const y = exportYear()
    if (y == null) return
    void downloadFile(reportPaths.exportAllExcel(projectId.value), {
      method: 'post',
      data: {
        year: y,
        mode: 'audited',
      },
      fileName: `全部报表_已审_${y}.xlsx`,
    })
  }

  function onExportAllUnadjusted() {
    const y = exportYear()
    if (y == null) return
    void downloadFile(reportPaths.exportAllExcel(projectId.value), {
      method: 'post',
      data: {
        year: y,
        mode: 'unadjusted',
      },
      fileName: `全部报表_未审_${y}.xlsx`,
    })
  }

  function copyReportTable() {
    if (!rows.value.length) { ElMessage.warning('无数据可复制'); return }
    const headers = ['行次', '项目', '本期金额', '上期金额']
    const dataRows = rows.value.map((r: any) => [r.row_code || '', r.row_name || '', r.current_period_amount ?? '', r.prior_period_amount ?? ''])
    const text = [headers.join('\t'), ...dataRows.map(r => r.join('\t'))].join('\n')
    const html = `<table border="1"><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>${dataRows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`
    try {
      navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })])
      ElMessage.success(`已复制 ${dataRows.length} 行，可粘贴到 Word/Excel`)
    } catch {
      navigator.clipboard?.writeText(text)
      ElMessage.success('已复制为文本格式')
    }
  }

  return {
    onExportExcel,
    onExportAllExcel,
    onExportAllUnadjusted,
    copyReportTable,
    showReportImport,
    onReportImported,
  }
}
