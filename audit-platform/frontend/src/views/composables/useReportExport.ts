import { ref, type ComputedRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getReportExcelUrl, type ReportRow } from '@/services/auditPlatformApi'

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface UseReportExportOptions {
  projectId: ComputedRef<string>
  year: ComputedRef<number>
  activeTab: Ref<string>
  rows: Ref<ReportRow[]>
  activeTabLabel: ComputedRef<string>
  fetchReport: () => Promise<void>
}

export interface UseReportExportReturn {
  onExportExcel: () => void
  onExportAllExcel: () => void
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

  function onExportExcel() {
    import('@/services/commonApi').then(({ downloadFileAsBlob }) => {
      const url = getReportExcelUrl(projectId.value, year.value, activeTab.value)
      downloadFileAsBlob(url, `报表_${activeTab.value}_${year.value}.xlsx`)
    })
  }

  function onExportAllExcel() {
    import('@/services/commonApi').then(({ downloadFileAsBlob }) => {
      const url = `/api/reports/${projectId.value}/${year.value}/export`
      downloadFileAsBlob(url, `全部报表_${year.value}.xlsx`)
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
    copyReportTable,
    showReportImport,
    onReportImported,
  }
}
