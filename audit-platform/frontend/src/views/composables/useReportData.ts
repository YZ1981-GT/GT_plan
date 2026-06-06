import { ref, computed, type ComputedRef, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { projects as P_proj, reportConfig as P_rc } from '@/services/apiPaths'
import {
  generateReports, getReport, getReportConsistencyCheck,
  type ReportRow, type ReportConsistencyCheck,
} from '@/services/auditPlatformApi'
import { withLoading } from '@/composables/useLoading'
import { handleApiError } from '@/utils/errorHandler'

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface UseReportDataOptions {
  projectId: ComputedRef<string>
  year: ComputedRef<number>
  activeTab: Ref<string>
  reportMode: Ref<'audited' | 'unadjusted' | 'compare'>
  currentApplicableStandard: ComputedRef<string>
}

export interface UseReportDataReturn {
  // State
  rows: Ref<ReportRow[]>
  compareRows: Ref<any[]>
  loading: Ref<boolean>
  genLoading: Ref<boolean>
  checkLoading: Ref<boolean>
  syncLoading: Ref<boolean>
  balanceCheckResult: Ref<{ status: string; message: string } | null>
  consistencyResult: Ref<ReportConsistencyCheck | null>
  tableMaxHeight: Ref<number>

  // Actions
  fetchReport: () => Promise<void>
  onGenerate: () => Promise<void>
  onConsistencyCheck: () => Promise<void>
  runBalanceCheck: () => Promise<void>
  loadTemplateRows: () => Promise<void>
  ensureProjectYear: () => Promise<void>
  reloadReportContext: () => Promise<void>

  // Derived
  activeTabLabel: ComputedRef<string>
  coverageSummary: ComputedRef<{ total: number; withData: number; text: string } | null>

  // Project metadata (populated by ensureProjectYear)
  projectName: Ref<string>
  reportScope: Ref<string>
  templateType: Ref<string>
  isConsolidated: ComputedRef<boolean>

  // Internal (for main file sync of projectYear)
  _fetchedAuditYear: Ref<number | null>
}

// ─── Implementation ─────────────────────────────────────────────────────────

/**
 * Inline row type detection for coverageSummary computation.
 * Mirrors the logic in useReportColumns.getRowType but avoids circular dependency.
 */
function _getRowType(row: ReportRow): string {
  if (row.row_name && (row.row_name.includes('：') || row.row_name.includes(':'))) return 'header'
  if (row.is_total_row) return 'total'
  if (row.row_name && (row.row_name.startsWith('△') || row.row_name.startsWith('▲'))) return 'special'
  if (!row.formula_used && row.current_period_amount === '0') return 'manual'
  if (parseFloat(row.current_period_amount || '0') === 0 && !row.current_period_amount?.includes('.')) return 'zero'
  return 'data'
}

export function useReportData(options: UseReportDataOptions): UseReportDataReturn {
  const { projectId, year, activeTab, reportMode, currentApplicableStandard } = options
  const router = useRouter()

  // ─── State ──────────────────────────────────────────────────────────────────
  const rows = ref<ReportRow[]>([])
  const compareRows = ref<any[]>([])
  const loading = ref(false)
  const genLoading = ref(false)
  const checkLoading = ref(false)
  const syncLoading = ref(false)
  const balanceCheckResult = ref<{ status: string; message: string } | null>(null)
  const consistencyResult = ref<ReportConsistencyCheck | null>(null)
  const tableMaxHeight = ref(500)

  // Project metadata
  const projectName = ref<string>('')
  const reportScope = ref<string>('standalone')
  const templateType = ref<string>('soe')
  const isConsolidated = computed(() => reportScope.value === 'consolidated')
  /** Internal: fetched audit_year from project API (for main file to sync projectYear) */
  const _fetchedAuditYear = ref<number | null>(null)

  // ─── Derived ────────────────────────────────────────────────────────────────
  const activeTabLabel = computed(() => {
    const m: Record<string, string> = {
      balance_sheet: '资产负债表',
      income_statement: '利润表',
      cash_flow_statement: '现金流量表',
      equity_statement: '所有者权益变动表',
      cash_flow_supplement: '现金流附表',
      impairment_provision: '资产减值准备表',
    }
    return m[activeTab.value] || ''
  })

  /**
   * F28: 计算报表数据覆盖率摘要
   */
  const coverageSummary = computed(() => {
    if (!rows.value || rows.value.length === 0) return null
    const total = rows.value.length
    let withData = 0
    let headerRows = 0
    let manualRows = 0

    for (const row of rows.value) {
      const type = _getRowType(row)
      if (type === 'header') {
        headerRows++
      } else if (type === 'manual') {
        manualRows++
      } else {
        const amt = parseFloat(row.current_period_amount || '0')
        if (amt !== 0) withData++
      }
    }

    return {
      total,
      withData,
      headerRows,
      manualRows,
      text: `${total} 行，${withData} 行有数据，${headerRows} 行标题行，${manualRows} 行待填列`,
    }
  })

  // ─── Actions ────────────────────────────────────────────────────────────────

  async function runBalanceCheck() {
    try {
      const res = await api.get(`/api/projects/${projectId.value}/data-quality/check?checks=report_balance&year=${year.value}`)
      const rb = res?.results?.report_balance
      if (rb) {
        balanceCheckResult.value = { status: rb.status, message: rb.message || '' }
      }
    } catch {
      // 静默失败，不阻断
    }
  }

  async function ensureProjectYear() {
    try {
      // 直接调用项目详情 + wizard 获取完整信息
      const projRaw = await api.get(P_proj.detail(projectId.value), {
        validateStatus: (s: number) => s < 600,
      })
      const proj = projRaw?.data ?? projRaw ?? projRaw
      projectName.value = proj?.client_name || proj?.name || ''
      reportScope.value = proj?.report_scope || 'standalone'
      templateType.value = proj?.template_type || ''
      _fetchedAuditYear.value = Number(proj?.audit_year) || null

      // 从 wizard_state 补充 template_type
      const wizRaw = await api.get(P_proj.wizard(projectId.value), {
        validateStatus: (s: number) => s < 600,
      })
      const ws = wizRaw?.data ?? wizRaw
      const bi = ws?.steps?.basic_info?.data
      if (bi?.template_type) templateType.value = bi.template_type
      if (bi?.report_scope) reportScope.value = bi.report_scope
      if (bi?.client_name && !projectName.value) projectName.value = bi.client_name

      if (!templateType.value) templateType.value = 'soe'
    } catch {
      _fetchedAuditYear.value = null
    }
  }

  async function loadTemplateRows() {
    // 从报表配置加载预设行次（显示空值的模板框架）
    try {
      const data = await api.get(P_rc.list, {
        params: { report_type: activeTab.value, project_id: projectId.value, applicable_standard: currentApplicableStandard.value },
      })
      const configs = data
      if (Array.isArray(configs) && configs.length > 0) {
        rows.value = configs.map((r: any) => ({
          row_code: r.row_code || '',
          row_name: r.row_name || '',
          current_period_amount: null as string | null,
          prior_period_amount: null as string | null,
          indent_level: r.indent_level || 0,
          is_total_row: r.is_total || false,
          formula_used: r.formula || null,
          source_accounts: null as string[] | null,
        }))
      } else {
        rows.value = []
      }
    } catch {
      // 配置也没有，显示空
      rows.value = []
    }
  }

  const fetchReport = withLoading(loading, async () => {
    const std = currentApplicableStandard.value
    try {
      if (reportMode.value === 'compare') {
        const [audited, unadjusted] = await Promise.all([
          getReport(projectId.value, year.value, activeTab.value, false, std),
          getReport(projectId.value, year.value, activeTab.value, true, std),
        ])
        // 合并为对比行
        const uMap = new Map(unadjusted.map((r: any) => [r.row_code, r]))
        compareRows.value = audited.map((r: any) => {
          const u = uMap.get(r.row_code)
          const uAmt = parseFloat(u?.current_period_amount || '0')
          const aAmt = parseFloat(r.current_period_amount || '0')
          return {
            ...r,
            unadjusted_amount: uAmt,
            audited_amount: aAmt,
            adjustment: Math.round((aAmt - uAmt) * 100) / 100,
          }
        })
        rows.value = audited
      } else {
        rows.value = await getReport(projectId.value, year.value, activeTab.value, reportMode.value === 'unadjusted', std)
        compareRows.value = []
      }
    } catch (err: any) {
      // 404 = 报表未生成，加载预设模板结构显示空表格框架
      if (err?.response?.status === 404) {
        await loadTemplateRows()
      } else {
        rows.value = []
      }
      compareRows.value = []
    }

    // ② 自动运行跨表校对（静默，不弹窗，只在有异常时显示 balanceCheckResult 横幅）
    if (rows.value.length > 0) {
      try {
        const result = await getReportConsistencyCheck(projectId.value, year.value)
        if (result && !result.consistent) {
          const total = result.total || result.checks?.length || 0
          const passed = (result.logic_check_passed || 0) + (result.reasonability_passed || 0)
          const failCount = total - passed
          balanceCheckResult.value = {
            status: failCount > 0 ? 'warning' : 'passed',
            message: `自动校对：${total} 项审核，${failCount} 项未通过`,
          }
        } else {
          balanceCheckResult.value = null
        }
      } catch { /* 静默失败 */ }
    }
  })


  // F26: 前置条件错误处理——显示错误信息 + "去完成"跳转按钮
  const PREREQUISITE_ROUTE_MAP: Record<string, string> = {
    recalc: 'trial-balance',
    auto_match: 'mapping',
    generate_reports: 'reports',
    select_template: 'settings',
  }

  async function handlePrerequisiteError(message: string, action: string | null) {
    const routeKey = action ? PREREQUISITE_ROUTE_MAP[action] : null
    if (routeKey) {
      try {
        await ElMessageBox.confirm(
          message,
          '前置条件未满足',
          {
            confirmButtonText: '去完成',
            cancelButtonText: '取消',
            type: 'warning',
          },
        )
        // Navigate to the prerequisite page
        const targetPath = `/projects/${projectId.value}/${routeKey}`
        router.push(targetPath)
      } catch {
        // User cancelled
      }
    } else {
      ElMessage.warning(message || '前置条件未满足')
    }
  }

  async function onGenerate() {
    const { showGuide } = await import('@/composables/useWorkflowGuide')
    const ok = await showGuide(
      'report_generate',
      '📊 刷新报表数据',
      `<div style="line-height:1.8;font-size: var(--gt-font-size-sm)">
        <p>将根据试算表审定数重新计算生成六张财务报表。</p>
        <p style="color: var(--gt-color-info);font-size: var(--gt-font-size-xs);margin-top:6px">请确认以下准备工作已完成：</p>
        <ul style="padding-left:18px;margin:4px 0">
          <li><span style="color: var(--gt-color-wheat)">⚠</span> 已完成账套数据导入（科目余额表、序时账）</li>
          <li><span style="color: var(--gt-color-wheat)">⚠</span> 已完成科目映射（客户科目 → 标准科目）</li>
          <li><span style="color: var(--gt-color-wheat)">⚠</span> 调整分录已录入并审批（如有）</li>
        </ul>
        <p style="color: var(--gt-color-info);font-size: var(--gt-font-size-xs);margin-top:6px">💡 如果试算表数据为空，报表金额将全部为零</p>
      </div>`,
      '开始生成',
    )
    if (!ok) return
    await withLoading(genLoading, async () => {
      try {
        const result = await generateReports(projectId.value, year.value)
        const summary = result?.summary
        if (summary && summary.total_rows > 0) {
          ElMessage.success(`报表生成完成：${summary.total_rows} 行，${summary.non_zero_rows} 行有数据`)
        } else {
          ElMessage.success('报表生成完成')
        }
        await fetchReport()
        // F29/D10: 报表生成后自动执行报表平衡检查
        await runBalanceCheck()
      } catch (err: any) {
        const detail = err?.response?.data?.detail || err?.response?.data?.message
        if (err?.response?.status === 400 && detail) {
          const msg = typeof detail === 'object' ? detail.message : detail
          const action = typeof detail === 'object' ? detail.prerequisite_action : null
          await handlePrerequisiteError(msg, action)
        } else {
          handleApiError(err, '报表生成')
        }
      }
    })()
  }

  async function onConsistencyCheck() {
    const { showGuide } = await import('@/composables/useWorkflowGuide')
    const ok = await showGuide(
      'report_audit',
      '✅ 报表审核校验',
      `<div style="line-height:1.8;font-size: var(--gt-font-size-sm)">
        <p>将对报表执行逻辑审核和合理性检查。</p>
        <ul style="padding-left:18px;margin:4px 0">
          <li><span style="color: var(--gt-color-wheat)">⚠</span> 请先确认报表数据已生成（点击"刷新数据"）</li>
        </ul>
        <p style="color: var(--gt-color-success);font-size: var(--gt-font-size-xs);margin-top:6px">✓ 校验结果将按公式分类展示，可点击溯源跳转到具体位置</p>
      </div>`,
      '开始审核',
    )
    if (!ok) return
    await withLoading(checkLoading, async () => {
      consistencyResult.value = await getReportConsistencyCheck(projectId.value, year.value)
    })()
  }

  async function reloadReportContext() {
    await ensureProjectYear()
    await fetchReport()
  }

  // ─── Return ─────────────────────────────────────────────────────────────────
  return {
    // State
    rows,
    compareRows,
    loading,
    genLoading,
    checkLoading,
    syncLoading,
    balanceCheckResult,
    consistencyResult,
    tableMaxHeight,

    // Actions
    fetchReport,
    onGenerate,
    onConsistencyCheck,
    runBalanceCheck,
    loadTemplateRows,
    ensureProjectYear,
    reloadReportContext,

    // Derived
    activeTabLabel,
    coverageSummary,

    // Project metadata
    projectName,
    reportScope,
    templateType,
    isConsolidated,

    // Internal (for main file sync)
    _fetchedAuditYear,
  }
}
