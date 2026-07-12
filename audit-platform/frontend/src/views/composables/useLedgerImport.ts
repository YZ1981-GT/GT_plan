/**
 * useLedgerImport - 账套智能导入域逻辑
 *
 * 从 LedgerPenetration.vue 拆分而来，包含：
 * - 文件上传与预览
 * - 列映射手动调整
 * - 后台导入轮询
 * - 导入耗时预估
 * - 数据校验与去重
 *
 * @domain ledger-import
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { api } from '@/services/apiProxy'
import { ledger as P_ledger } from '@/services/apiPaths'
import { useImportValidation } from '@/utils/useImportValidation'
import { handleApiError } from '@/utils/errorHandler'

// ─── 类型定义 ───
interface ImportValidationItem {
  file?: string | null
  sheet?: string | null
  rule_code: string
  severity: 'fatal' | 'error' | 'warning' | 'info' | string
  message: string
  blocking?: boolean
}

interface ImportValidationSummary {
  total: number
  blocking_count: number
  has_blocking?: boolean
  by_severity: Record<string, number>
}

interface LedgerImportResultPayload {
  imported?: Record<string, number>
  year?: number | null
  diagnostics?: Array<Record<string, unknown>>
  validation?: ImportValidationItem[]
  validation_summary?: ImportValidationSummary
  errors?: string[]
  batch_id?: string | null
}

interface SheetMappingInfo {
  sheet: string
  data_type: string
  mapped: number
  total: number
  rate: number
  unmapped: string[]
}

const DATA_TYPE_LABELS: Record<string, string> = {
  tb_balance: '余额表',
  tb_ledger: '序时账',
  tb_aux_balance: '辅助余额',
  tb_aux_ledger: '辅助明细',
}

export const STANDARD_FIELDS = [
  { value: '', label: '（不映射）' },
  { value: 'account_code', label: '科目编码' },
  { value: 'account_name', label: '科目名称' },
  { value: 'voucher_date', label: '凭证日期' },
  { value: 'voucher_no', label: '凭证号' },
  { value: 'debit_amount', label: '借方金额' },
  { value: 'credit_amount', label: '贷方金额' },
  { value: 'opening_balance', label: '期初余额' },
  { value: 'closing_balance', label: '期末余额' },
  { value: 'aux_dimensions', label: '核算维度（混合）' },
  { value: 'aux_type', label: '辅助类型' },
  { value: 'aux_code', label: '辅助编码' },
  { value: 'aux_name', label: '辅助名称' },
  { value: 'summary', label: '摘要' },
  { value: 'direction', label: '借贷方向' },
  { value: 'preparer', label: '制单人' },
  { value: 'accounting_period', label: '会计期间' },
]

export function useLedgerImport(projectId: Ref<string> | ComputedRef<string>, year: Ref<number> | ComputedRef<number>) {
  // ─── 导入弹窗与状态 ───
  const importDialogVisible = ref(false)
  const importStep = ref<'upload' | 'preview' | 'importing' | 'done'>('upload')
  const importFiles = ref<File[]>([])
  const importYear = ref<number | undefined>(undefined)
  const previewResult = ref<any>(null)
  const importedResult = ref<LedgerImportResultPayload | null>(null)
  const uploadToken = ref('')
  const previewing = ref(false)
  const importing = ref(false)
  const importProgressPct = ref(0)
  const uploadRef = ref()

  // ─── 数据管理 ───
  const dataManagerVisible = ref(false)
  const importHistoryVisible = ref(false)
  const importHistoryLoading = ref(false)
  const importHistoryJobs = ref<any[]>([])
  const importHistoryDatasets = ref<any[]>([])

  // ─── 后台轮询 ───
  const bgImportPolling = ref(false)
  const bgImportMessage = ref('')
  const isImportActive = ref(false)

  // ─── 校验与去重 ───
  const validateDialogVisible = ref(false)
  const validating = ref(false)
  const validateResult = ref<any>(null)
  const deduping = ref(false)

  // ─── 列映射 ───
  const userColumnMapping = ref<Record<string, Record<string, string>>>({})

  // ─── 耗时预估 ───
  const importTotalBytes = computed(() =>
    importFiles.value.reduce((sum, f) => sum + (f.size || 0), 0),
  )
  const importTotalMB = computed(() => importTotalBytes.value / (1024 * 1024))
  const importIsLargeFile = computed(() => importTotalMB.value > 50)
  const importEstimateSeconds = computed(() => {
    const mb = importTotalMB.value
    const uploadSec = Math.round(mb / 2.5)
    let processSec: number
    if (mb < 1) processSec = 10
    else if (mb < 5) processSec = Math.round(mb * 11)
    else if (mb < 20) processSec = Math.round(mb * 12)
    else if (mb < 100) processSec = Math.round(mb * 14)
    else processSec = Math.round(mb * 16)
    return uploadSec + processSec
  })
  const importEstimateText = computed(() => {
    const s = importEstimateSeconds.value
    if (s < 60) return `约 ${s} 秒`
    if (s < 600) return `约 ${Math.round(s / 60)} 分钟`
    return `约 ${Math.round(s / 60)} 分钟（强烈建议后台继续）`
  })

  // ─── 映射完成率 ───
  const mappingCoverage = computed(() => {
    const sheets: SheetMappingInfo[] = []
    let totalMapped = 0
    let totalHeaders = 0
    for (const d of (previewResult.value?.diagnostics || [])) {
      const headers: string[] = d.headers || d.raw_headers || []
      const mapping = d.column_mapping || {}
      const mapped = Object.keys(mapping).length
      const total = headers.length
      const unmapped = headers.filter((h: string) => !mapping[h])
      sheets.push({
        sheet: `${d.file || ''} / ${d.sheet || ''}`,
        data_type: d.data_type || '未知',
        mapped,
        total,
        rate: total > 0 ? Math.round(mapped * 100 / total) : 0,
        unmapped,
      })
      totalMapped += mapped
      totalHeaders += total
    }
    const rate = totalHeaders > 0 ? Math.round(totalMapped * 100 / totalHeaders) : 0
    const hasLow = sheets.some((s) => s.rate < 70) || rate < 70
    return { sheets, mapped: totalMapped, total: totalHeaders, rate, hasLow, isWarning: hasLow }
  })

  // ─── 导入结果摘要 ───
  const importedResultSummaryEntries = computed(() => {
    const imported = importedResult.value?.imported || {}
    return Object.entries(imported).map(([key, value]) => ({
      key,
      label: DATA_TYPE_LABELS[key] || key,
      value: `${typeof value === 'number' ? value.toLocaleString() : value} 条`,
    }))
  })

  const {
    validationSummary: importValidationSummary,
    groupedValidationItems: groupedImportValidationItems,
    validationSummaryAlertType: importValidationSummaryAlertType,
    validationSummaryTitle: importValidationSummaryTitle,
  } = useImportValidation<ImportValidationItem, ImportValidationSummary>(
    () => importedResult.value?.validation,
    () => importedResult.value?.validation_summary,
  )

  // ─── 方法 ───
  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  function initColumnMapping() {
    userColumnMapping.value = {}
    if (!previewResult.value?.diagnostics) return
    for (const d of previewResult.value.diagnostics) {
      const key = `${d.file}/${d.sheet}`
      const mapping: Record<string, string> = {}
      if (d.column_mapping) {
        for (const [col, field] of Object.entries(d.column_mapping)) {
          if (field) mapping[col] = field as string
        }
      }
      userColumnMapping.value[key] = mapping
    }
  }

  async function runValidation() {
    validating.value = true
    validateDialogVisible.value = true
    validateResult.value = null
    try {
      const data = await api.get(
        `${P_ledger.validate(projectId.value)}?year=${year.value}`,
      )
      validateResult.value = data
    } catch (e: any) {
      handleApiError(e, '校验')
    } finally {
      validating.value = false
    }
  }

  async function runDedup(onRefresh?: () => void) {
    if (!projectId.value) return
    deduping.value = true
    try {
      const preview: any = await api.post(P_ledger.data.dedup(projectId.value), {
        year: year.value,
        dry_run: true,
      })
      const total = preview?.total_deleted ?? 0
      if (total === 0) {
        ElMessage.success('未检测到重复数据，无需去重')
        return
      }
      const detail = ['tb_balance', 'tb_ledger', 'tb_aux_balance', 'tb_aux_ledger']
        .map((t) => {
          const label = { tb_balance: '余额表', tb_ledger: '序时账', tb_aux_balance: '辅助余额', tb_aux_ledger: '辅助明细' }[t]
          return preview[t] ? `${label}: ${preview[t].toLocaleString()} 行` : null
        })
        .filter(Boolean)
        .join('，')
      await ElMessageBox.confirm(
        `检测到 ${total.toLocaleString()} 行整行完全相同的重复数据（${detail}）。\n` +
          `去重将保留每组首条、删除其余完全相同的行（任一字段有差异的行不会被删，删除的数据进回收站可恢复）。是否继续？`,
        '数据去重确认',
        { type: 'warning', confirmButtonText: '确认去重', cancelButtonText: '取消' },
      )
      const result: any = await api.post(P_ledger.data.dedup(projectId.value), {
        year: year.value,
        dry_run: false,
      })
      const deleted = result?.total_deleted ?? 0
      ElMessage.success(
        `去重完成，共清理 ${deleted.toLocaleString()} 行重复数据（已进回收站，可在"数据管理"中恢复）`,
      )
      onRefresh?.()
    } catch (e: any) {
      if (e === 'cancel' || e === 'close') return
      handleApiError(e, '去重')
    } finally {
      deduping.value = false
    }
  }

  async function loadImportHistory() {
    importHistoryLoading.value = true
    try {
      const [jobsData, datasetsData] = await Promise.allSettled([
        api.get(P_ledger.import.jobs(projectId.value), { params: { year: year.value } }),
        api.get(P_ledger.import.datasets(projectId.value), { params: { year: year.value } }),
      ])
      importHistoryJobs.value = jobsData.status === 'fulfilled' ? (jobsData.value ?? []) : []
      importHistoryDatasets.value = datasetsData.status === 'fulfilled' ? (datasetsData.value ?? []) : []
    } finally {
      importHistoryLoading.value = false
    }
  }

  function formatRecordSummary(summary: Record<string, unknown> | null | undefined) {
    if (!summary) return '—'
    const parts: string[] = []
    if (summary.tb_balance) parts.push(`余额 ${summary.tb_balance}`)
    if (summary.tb_aux_balance) parts.push(`辅助余额 ${summary.tb_aux_balance}`)
    if (summary.tb_ledger) parts.push(`序时账 ${summary.tb_ledger}`)
    if (summary.tb_aux_ledger) parts.push(`辅助明细 ${summary.tb_aux_ledger}`)
    return parts.length > 0 ? parts.join(' / ') : '—'
  }

  function openImportDialog() {
    importDialogVisible.value = true
    importStep.value = 'upload'
    importFiles.value = []
    previewResult.value = null
    importedResult.value = null
  }

  function onIncrementalUpload(yr: number) {
    dataManagerVisible.value = false
    importDialogVisible.value = true
    importStep.value = 'upload'
    importFiles.value = []
    importYear.value = yr
    ElNotification({
      title: '增量追加模式',
      message: `请上传 ${yr} 年的序时账文件，系统将自动检测并只追加新月份`,
      type: 'info',
      duration: 5000,
    })
  }

  return {
    // 弹窗状态
    importDialogVisible,
    importStep,
    importFiles,
    importYear,
    previewResult,
    importedResult,
    uploadToken,
    previewing,
    importing,
    importProgressPct,
    uploadRef,
    // 数据管理
    dataManagerVisible,
    importHistoryVisible,
    importHistoryLoading,
    importHistoryJobs,
    importHistoryDatasets,
    // 后台轮询
    bgImportPolling,
    bgImportMessage,
    isImportActive,
    // 校验去重
    validateDialogVisible,
    validating,
    validateResult,
    deduping,
    // 列映射
    userColumnMapping,
    // computed
    importTotalBytes,
    importTotalMB,
    importIsLargeFile,
    importEstimateSeconds,
    importEstimateText,
    mappingCoverage,
    importedResultSummaryEntries,
    importValidationSummary,
    groupedImportValidationItems,
    importValidationSummaryAlertType,
    importValidationSummaryTitle,
    // 方法
    formatFileSize,
    initColumnMapping,
    runValidation,
    runDedup,
    loadImportHistory,
    formatRecordSummary,
    openImportDialog,
    onIncrementalUpload,
    STANDARD_FIELDS,
    DATA_TYPE_LABELS,
  }
}
