import { ref, computed, type ComputedRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useRouter } from 'vue-router'
import { handleApiError } from '@/utils/errorHandler'
import { openWorkpaperCell } from '@/services/openWorkpaperCell'
import type { useCellSelection } from '@/composables/useCellSelection'
import { reportChecksToCsv } from '@/services/reportCheckPresentation'
import { useReportRequestFence } from './useReportRequestFence'

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface TraceLocation {
  label: string
  tab: string
  rowCode: string
}

export interface UseReportTraceOptions {
  projectId: ComputedRef<string>
  /** 审计年度；项目没填为 null（仅用于导出文件名） */
  year: ComputedRef<number | null>
  activeTab: Ref<string>
  activeTabLabel: ComputedRef<string>
  consistencyResult: Ref<any>
  fetchReport: () => Promise<void>
  rvCtx: ReturnType<typeof useCellSelection>
}

export interface UseReportTraceReturn {
  rvTraceDialogVisible: Ref<boolean>
  rvTraceLoading: Ref<boolean>
  rvTraceResult: Ref<{
    upstream: any[]
    downstream: any[]
    attachments: any[]
    objectId: string
    projectId: string
  } | null>
  onRvCtxCellTrace: () => Promise<void>
  onRvTraceLocate: (node: any) => Promise<void>

  showAuditDialog: Ref<boolean>
  auditTab: Ref<string>
  filteredAuditChecks: ComputedRef<any[]>
  onExportAuditExcel: () => void
  onAuditDrilldown: (check: any) => void

  showTraceSelectDialog: Ref<boolean>
  traceSelectOptions: Ref<TraceLocation[]>
  traceSelectCheck: Ref<any>
  isTracing: Ref<boolean>
  onTraceJump: (loc: TraceLocation) => void
  onTraceReturn: () => void

  parseTraceLocations: (check: any) => TraceLocation[]
}

// ─── Composable ─────────────────────────────────────────────────────────────

export function useReportTrace(options: UseReportTraceOptions): UseReportTraceReturn {
  const {
    projectId, year, activeTab, activeTabLabel,
    consistencyResult, fetchReport, rvCtx,
  } = options

  // ─── Cell Trace (Lineage) ─────────────────────────────────────────────────
  const rvTraceDialogVisible = ref(false)
  const rvTraceLoading = ref(false)
  const rvTraceResult = ref<{
    upstream: any[]
    downstream: any[]
    attachments: any[]
    objectId: string
    projectId: string
  } | null>(null)

  const lineageFence = useReportRequestFence(
    () => [projectId.value, year.value, activeTab.value],
    () => { rvTraceDialogVisible.value = false; rvTraceResult.value = null; rvTraceLoading.value = false },
  )

  async function onRvCtxCellTrace() {
    rvCtx.closeContextMenu()
    const row = rvCtx.contextMenu.rowData
    if (!row?.row_code) {
      ElMessage.info('请在数据行上右键')
      return
    }
    const request = lineageFence.begin('lineage')
    const pid = projectId.value
    const rowCode = row.row_code
    rvTraceDialogVisible.value = true
    rvTraceLoading.value = true
    rvTraceResult.value = null
    try {
      const data: any = await api.get(
        `/api/projects/${pid}/lineage`,
        { params: { object_type: 'report_row', object_id: rowCode, direction: 'both' } },
      )
      if (!request.isCurrent()) return
      const upstream = data?.upstream || []
      const downstream = data?.downstream || []
      const attachments = data?.attachments || []
      rvTraceResult.value = {
        upstream, downstream, attachments,
        objectId: rowCode,
        projectId: pid,
      }
      if (!upstream.length && !downstream.length && !attachments.length) {
        rvTraceDialogVisible.value = false
        ElMessage.info('该数字暂无溯源信息')
      }
    } catch (e: any) {
      if (!request.isCurrent()) return
      rvTraceDialogVisible.value = false
      handleApiError(e, '数字溯源')
    } finally {
      if (request.isCurrent()) rvTraceLoading.value = false
    }
  }

  const router = useRouter()
  async function onRvTraceLocate(node: any) {
    rvTraceDialogVisible.value = false
    const reason = await openWorkpaperCell(router, { projectId: projectId.value, wpId: node?.wp_id, wpCode: node?.wp_code, sheet: node?.sheet_name, cell: node?.cell_ref })
    if (reason) ElMessage.warning(reason)
  }

  // ─── Audit Dialog ─────────────────────────────────────────────────────────
  const showAuditDialog = ref(false)
  const auditTab = ref('all')

  const filteredAuditChecks = computed(() => {
    const checks = consistencyResult.value?.checks || []
    if (auditTab.value === 'all') return checks
    return checks.filter((c: any) => c.category === auditTab.value)
  })

  function onExportAuditExcel() {
    const checks = filteredAuditChecks.value
    if (!checks.length) {
      ElMessage.warning('无审核数据可导出')
      return
    }
    const BOM = '\uFEFF'
    const blob = new Blob([BOM + reportChecksToCsv(checks)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `审核报告_${activeTabLabel.value}${year.value != null ? `_${year.value}` : ''}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('审核报告已导出')
  }

  function onAuditDrilldown(check: any) {
    const locs = parseTraceLocations(check)
    if (locs.length === 1) {
      onTraceJump(locs[0])
    } else if (locs.length > 1) {
      showTraceSelectDialog.value = true
      traceSelectOptions.value = locs
      traceSelectCheck.value = check
    } else {
      ElMessage.info('该审核项无可溯源的定位信息')
    }
  }

  // ─── Trace Select ─────────────────────────────────────────────────────────
  const showTraceSelectDialog = ref(false)
  const traceSelectOptions = ref<TraceLocation[]>([])
  const traceSelectCheck = ref<any>(null)
  const isTracing = ref(false)
  const traceFromTab = ref('')
  const auditFence = useReportRequestFence(() => [projectId.value, year.value, consistencyResult.value], () => {
    showAuditDialog.value = false
    showTraceSelectDialog.value = false
    traceSelectOptions.value = []
    traceSelectCheck.value = null
    isTracing.value = false
    traceFromTab.value = ''
  })
  let traceSession: ReturnType<typeof auditFence.begin> | null = null

  function onTraceJump(loc: TraceLocation) {
    if (!consistencyResult.value) return
    if (!isTracing.value) {
      traceFromTab.value = activeTab.value
      traceSession = auditFence.begin('trace')
    }
    activeTab.value = loc.tab
    showTraceSelectDialog.value = false
    showAuditDialog.value = false
    isTracing.value = true
    fetchReport()
  }

  function onTraceReturn() {
    if (!isTracing.value || !traceSession?.isCurrent() || !consistencyResult.value) return
    isTracing.value = false
    showAuditDialog.value = true
    if (traceFromTab.value) {
      activeTab.value = traceFromTab.value
      fetchReport()
    }
  }

  // ─── Helpers ──────────────────────────────────────────────────────────────

  function parseTraceLocations(check: any): TraceLocation[] {
    const locs: TraceLocation[] = []
    const formula = check.formula || ''
    const source = check.source || ''
    const name = check.name || ''

    const codeMatch = source.match(/^([A-Z]+-\d+)/)
    if (codeMatch) {
      const code = codeMatch[1]
      const tab = codeToTab(code)
      locs.push({ label: `${code} (${tabLabel(tab)})`, tab, rowCode: code })
    }

    const refs = formula.matchAll(/([A-Z]+-\d+)/g)
    for (const m of refs) {
      const code = m[1]
      if (!locs.find(l => l.rowCode === code)) {
        const tab = codeToTab(code)
        locs.push({ label: `${code} (${tabLabel(tab)})`, tab, rowCode: code })
      }
    }

    if (!locs.length) {
      if (name.includes('资产负债表')) locs.push({ label: '资产负债表', tab: 'balance_sheet', rowCode: '' })
      else if (name.includes('利润')) locs.push({ label: '利润表', tab: 'income_statement', rowCode: '' })
      else if (name.includes('现金')) locs.push({ label: '现金流量表', tab: 'cash_flow_statement', rowCode: '' })
    }

    return locs
  }

  function codeToTab(code: string): string {
    if (code.startsWith('BS-')) return 'balance_sheet'
    if (code.startsWith('IS-')) return 'income_statement'
    if (code.startsWith('CFS-')) return 'cash_flow_statement'
    if (code.startsWith('EQ-')) return 'equity_statement'
    if (code.startsWith('CFSS-')) return 'cash_flow_supplement'
    if (code.startsWith('IMP-')) return 'impairment_provision'
    return 'balance_sheet'
  }

  function tabLabel(tab: string): string {
    const m: Record<string, string> = {
      balance_sheet: '资产负债表', income_statement: '利润表',
      cash_flow_statement: '现金流量表', equity_statement: '权益变动表',
      cash_flow_supplement: '现金流附表', impairment_provision: '资产减值准备表',
    }
    return m[tab] || tab
  }

  return {
    rvTraceDialogVisible,
    rvTraceLoading,
    rvTraceResult,
    onRvCtxCellTrace,
    onRvTraceLocate,

    showAuditDialog,
    auditTab,
    filteredAuditChecks,
    onExportAuditExcel,
    onAuditDrilldown,

    showTraceSelectDialog,
    traceSelectOptions,
    traceSelectCheck,
    isTracing,
    onTraceJump,
    onTraceReturn,

    parseTraceLocations,
  }
}
