/**
 * useCutoffAutoSampling — 截止测试自动提取核心 composable
 *
 * Spec: .kiro/specs/cutoff-test-auto-sampling/
 * Task: 6.1
 *
 * 职责：
 * - 定义所有 TypeScript 接口：CutoffConfig、ExtractedVoucher、ExtractStats、FillMode、ExtractionLogEntry
 * - config 响应式初始化（从 props.accountCode 解析默认科目、从 props.year 计算默认截止日 12月31日）
 * - validateConfig() — 校验 cutoffDate 非空 + accountCodes 非空
 * - dateRangeText computed — 显示 "2025-12-26 至 2026-01-10" 格式
 * - triggerExtraction() — 调用 POST /cutoff-extract → 填充 extractedVouchers → 打开预览
 * - 选中统计 computed：selectedVouchers、selectedCount、cutoffErrorCount、selectedDebitTotal、selectedCreditTotal
 * - confirmFill(mode) — 按 fill mode 生成新 samples → emit 'filled' → 调用 POST /cutoff-fill 记录日志
 * - 三种 fill mode 逻辑：append（拼接）、replace（替换）、merge（按 voucher_no 去重）
 * - loadHistory() — 调用 GET /cutoff-history
 * - undoLastExtraction(logId) — 调用 POST /cutoff-undo → emit 'filled' with before_data
 *
 * Requirements: 1.2, 1.3, 1.5, 3.3, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.3, 5.6, 5.8, 7.5, 8.4, 9.1, 9.5
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { determineCutoffStatus, computeDateRange, type CutoffDirection, type CutoffStatus } from './cutoffJudgment'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CutoffConfig {
  cutoffDate: string          // YYYY-MM-DD
  daysBefore: number          // 默认5
  daysAfter: number           // 默认10
  amountThreshold: number     // 默认0(不限)
  accountCodes: string[]      // 科目列表(前缀匹配)
  directionFilter: 'debit' | 'credit' | 'all'
  voucherTypeFilter: string[] // 记/收/付/转
  summaryKeyword: string
  excludeExtracted: boolean   // 默认true
}

export interface ExtractedVoucher {
  voucherNo: string
  voucherDate: string
  summary: string | null
  debitAmount: string | null    // Decimal字符串
  creditAmount: string | null
  accountCode: string
  accountName: string | null
  counterpartAccount: string | null
  voucherType: string | null
  cutoffStatus: CutoffStatus
  remark: string
  selected: boolean
}

export interface ExtractStats {
  totalCount: number
  debitTotal: string
  creditTotal: string
  byVoucherType: Record<string, number>
  truncated: boolean
}

export type FillMode = 'append' | 'replace' | 'merge'

export interface ExtractionLogEntry {
  id: string
  createdAt: string
  userId: string
  fillMode: FillMode
  filledCount: number
  totalMatched: number
  extractionCriteria: CutoffConfig
  isUndone: boolean
}

export interface CutoffAutoSamplingOptions {
  projectId: Ref<string>
  year: Ref<number>
  workpaperId: Ref<string>
  accountCode: string                       // 关联科目编码
  cutoffDirection: CutoffDirection           // 截止判定方向
  defaultConditions?: Partial<CutoffConfig>  // 默认条件覆盖
  /** 当前已有 samples（用于 merge/before_data 快照） */
  existingSamples?: Ref<ExtractedVoucher[]>
  /** 填充回调（父组件决定如何集成到自身数据结构） */
  onFilled?: (payload: { samples: ExtractedVoucher[]; fillMode: FillMode }) => void
}

// ─── Pure Function: applyFillMode（独立导出供 PBT 测试） ─────────────────────

/**
 * 填充策略纯函数
 *
 * - append: [...existing, ...selected]
 * - replace: [...selected]
 * - merge: existing + selected 中 voucher_no 不在 existing 中的条目
 */
export function applyFillMode(
  existing: ExtractedVoucher[],
  selected: ExtractedVoucher[],
  mode: FillMode,
): ExtractedVoucher[] {
  switch (mode) {
    case 'append':
      return [...existing, ...selected]
    case 'replace':
      return [...selected]
    case 'merge': {
      const existingNos = new Set(existing.map(v => v.voucherNo))
      const newItems = selected.filter(v => !existingNos.has(v.voucherNo))
      return [...existing, ...newItems]
    }
    default:
      return [...existing, ...selected]
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useCutoffAutoSampling(options: CutoffAutoSamplingOptions) {
  const {
    projectId,
    year,
    workpaperId,
    accountCode,
    cutoffDirection,
    defaultConditions,
    existingSamples,
    onFilled,
  } = options

  // ─── Config 初始化 ──────────────────────────────────────────────────────

  function buildDefaultConfig(): CutoffConfig {
    // 从 accountCode 解析科目列表（支持逗号分隔如 "1405,1403"）
    const codes = accountCode
      ? accountCode.split(',').map(c => c.trim()).filter(Boolean)
      : []

    // 默认截止日 = 项目年度12月31日
    const defaultCutoffDate = `${year.value}-12-31`

    return {
      cutoffDate: defaultConditions?.cutoffDate ?? defaultCutoffDate,
      daysBefore: defaultConditions?.daysBefore ?? 5,
      daysAfter: defaultConditions?.daysAfter ?? 10,
      amountThreshold: defaultConditions?.amountThreshold ?? 0,
      accountCodes: defaultConditions?.accountCodes ?? codes,
      directionFilter: defaultConditions?.directionFilter ?? 'all',
      voucherTypeFilter: defaultConditions?.voucherTypeFilter ?? [],
      summaryKeyword: defaultConditions?.summaryKeyword ?? '',
      excludeExtracted: defaultConditions?.excludeExtracted ?? true,
    }
  }

  // ─── Reactive State ─────────────────────────────────────────────────────

  const config = ref<CutoffConfig>(buildDefaultConfig())
  const extractedVouchers = ref<ExtractedVoucher[]>([])
  const stats = ref<ExtractStats | null>(null)
  const loading = ref(false)
  const previewVisible = ref(false)
  const historyVisible = ref(false)
  const historyList = ref<ExtractionLogEntry[]>([])
  const fillMode = ref<FillMode>('append')
  const configErrors = ref<Record<string, string>>({})

  // ─── Validation ─────────────────────────────────────────────────────────

  function validateConfig(): boolean {
    const errors: Record<string, string> = {}

    if (!config.value.cutoffDate) {
      errors.cutoffDate = '截止基准日不能为空'
    }
    if (!config.value.accountCodes || config.value.accountCodes.length === 0) {
      errors.accountCodes = '科目范围不能为空'
    }

    configErrors.value = errors
    return Object.keys(errors).length === 0
  }

  // ─── Computed: dateRangeText ────────────────────────────────────────────

  const dateRangeText: ComputedRef<string> = computed(() => {
    if (!config.value.cutoffDate) return ''
    const { start, end } = computeDateRange(
      config.value.cutoffDate,
      config.value.daysBefore,
      config.value.daysAfter,
    )
    return `${start} 至 ${end}`
  })

  // ─── Computed: 选中统计 ─────────────────────────────────────────────────

  const selectedVouchers: ComputedRef<ExtractedVoucher[]> = computed(() => {
    return extractedVouchers.value.filter(v => v.selected)
  })

  const selectedCount: ComputedRef<number> = computed(() => {
    return selectedVouchers.value.length
  })

  const cutoffErrorCount: ComputedRef<number> = computed(() => {
    return selectedVouchers.value.filter(v => v.cutoffStatus === '可能跨期').length
  })

  const selectedDebitTotal: ComputedRef<number> = computed(() => {
    return selectedVouchers.value.reduce((sum, v) => {
      return sum + (v.debitAmount ? parseFloat(v.debitAmount) || 0 : 0)
    }, 0)
  })

  const selectedCreditTotal: ComputedRef<number> = computed(() => {
    return selectedVouchers.value.reduce((sum, v) => {
      return sum + (v.creditAmount ? parseFloat(v.creditAmount) || 0 : 0)
    }, 0)
  })

  // ─── triggerExtraction ──────────────────────────────────────────────────

  async function triggerExtraction(): Promise<void> {
    if (!validateConfig()) return

    loading.value = true
    try {
      const res = await http.post(
        `/api/projects/${projectId.value}/sampling/cutoff-extract`,
        {
          cutoff_date: config.value.cutoffDate,
          days_before: config.value.daysBefore,
          days_after: config.value.daysAfter,
          amount_threshold: config.value.amountThreshold,
          account_codes: config.value.accountCodes,
          direction_filter: config.value.directionFilter,
          voucher_type_filter: config.value.voucherTypeFilter,
          summary_keyword: config.value.summaryKeyword,
          exclude_extracted: config.value.excludeExtracted,
          workpaper_id: workpaperId.value,
        },
      )

      // res.data 已被 http 拦截器解包（ResponseWrapperMiddleware 信封已去除）
      const data = res.data as any

      const items: any[] = data?.items ?? []
      const statsData = data?.stats ?? {}

      if (items.length === 0) {
        ElMessage.info('未找到符合条件的凭证')
        return
      }

      // 映射并自动计算 cutoffStatus
      extractedVouchers.value = items.map((item: any) => {
        const debitAmt = item.debit_amount ?? item.debitAmount ?? null
        const creditAmt = item.credit_amount ?? item.creditAmount ?? null
        // 计算金额用于判定（借方为正，贷方为负）
        const amount = debitAmt ? parseFloat(debitAmt) : (creditAmt ? -parseFloat(creditAmt) : 0)

        const voucherDate = item.voucher_date ?? item.voucherDate ?? ''
        const status = determineCutoffStatus(
          voucherDate,
          config.value.cutoffDate,
          cutoffDirection,
          amount,
          config.value.daysBefore,
          config.value.daysAfter,
        )

        return {
          voucherNo: item.voucher_no ?? item.voucherNo ?? '',
          voucherDate,
          summary: item.summary ?? null,
          debitAmount: debitAmt != null ? String(debitAmt) : null,
          creditAmount: creditAmt != null ? String(creditAmt) : null,
          accountCode: item.account_code ?? item.accountCode ?? '',
          accountName: item.account_name ?? item.accountName ?? null,
          counterpartAccount: item.counterpart_account ?? item.counterpartAccount ?? null,
          voucherType: item.voucher_type ?? item.voucherType ?? null,
          cutoffStatus: status,
          remark: '',
          selected: true,  // 默认全部勾选
        } as ExtractedVoucher
      })

      // 填充统计
      stats.value = {
        totalCount: statsData.total_count ?? statsData.totalCount ?? items.length,
        debitTotal: String(statsData.debit_total ?? statsData.debitTotal ?? '0'),
        creditTotal: String(statsData.credit_total ?? statsData.creditTotal ?? '0'),
        byVoucherType: statsData.by_voucher_type ?? statsData.byVoucherType ?? {},
        truncated: statsData.truncated ?? false,
      }

      // 打开预览弹窗
      previewVisible.value = true
    } catch (err: any) {
      ElMessage.error(err?.message || '提取失败，请稍后重试')
    } finally {
      loading.value = false
    }
  }

  // ─── confirmFill ────────────────────────────────────────────────────────

  async function confirmFill(): Promise<ExtractedVoucher[]> {
    const selected = selectedVouchers.value
    if (selected.length === 0) {
      ElMessage.warning('请至少勾选一条凭证')
      return []
    }

    const existing = existingSamples?.value ?? []
    const mode = fillMode.value

    // 应用填充策略
    const result = applyFillMode(existing, selected, mode)

    // 创建版本链快照（fire-and-forget，失败不阻塞主流程）
    http.post(
      `/api/projects/${projectId.value}/workpapers/${workpaperId.value}/versions`,
      {
        snapshot_type: 'auto_sampling',
        description: `截止测试自动提取：${config.value.accountCodes.join(',')} ${config.value.cutoffDate}`,
      },
    ).catch(() => {
      // fire-and-forget: 版本链快照失败仅静默忽略
    })

    // 记录填充日志（含 before_data 快照 — 向后兼容）
    try {
      await http.post(
        `/api/projects/${projectId.value}/sampling/cutoff-fill`,
        {
          project_id: projectId.value,
          workpaper_id: workpaperId.value,
          extraction_type: 'cutoff',
          extraction_criteria: config.value,
          total_matched: stats.value?.totalCount ?? selected.length,
          filled_count: selected.length,
          fill_mode: mode,
          before_data: existing,
        },
      )
    } catch {
      ElMessage.error('记录填充日志失败')
      return []
    }

    // 通知父组件
    if (onFilled) {
      onFilled({ samples: result, fillMode: mode })
    }

    // 关闭预览
    previewVisible.value = false

    const cutoffCount = selected.filter(v => v.cutoffStatus === '可能跨期').length
    ElMessage.success(`成功填充${selected.length}笔凭证，其中跨期${cutoffCount}笔`)

    return result
  }

  // ─── toggleSelectAll ────────────────────────────────────────────────────

  function toggleSelectAll(selected: boolean): void {
    extractedVouchers.value.forEach(v => { v.selected = selected })
  }

  // ─── loadHistory ────────────────────────────────────────────────────────

  async function loadHistory(): Promise<void> {
    try {
      const res = await http.get(
        `/api/projects/${projectId.value}/sampling/cutoff-history`,
        { params: { wp_id: workpaperId.value } },
      )

      const data = res.data as any
      const list: any[] = Array.isArray(data) ? data : (data?.items ?? [])

      historyList.value = list.map((item: any) => ({
        id: item.id,
        createdAt: item.created_at ?? item.createdAt ?? '',
        userId: item.user_id ?? item.userId ?? '',
        fillMode: item.fill_mode ?? item.fillMode ?? 'append',
        filledCount: item.filled_count ?? item.filledCount ?? 0,
        totalMatched: item.total_matched ?? item.totalMatched ?? 0,
        extractionCriteria: item.extraction_criteria ?? item.extractionCriteria ?? {},
        isUndone: item.is_undone ?? item.isUndone ?? false,
      }))

      historyVisible.value = true
    } catch {
      ElMessage.error('加载提取历史失败')
    }
  }

  // ─── undoLastExtraction ─────────────────────────────────────────────────

  async function undoLastExtraction(logId: string): Promise<void> {
    try {
      const res = await http.post(
        `/api/projects/${projectId.value}/sampling/cutoff-undo`,
        null,
        { params: { log_id: logId } },
      )

      const data = res.data as any
      const beforeData: ExtractedVoucher[] = data?.before_data ?? data?.beforeData ?? []

      // 通知父组件恢复数据
      if (onFilled) {
        onFilled({ samples: beforeData, fillMode: 'replace' })
      }

      ElMessage.success('已撤销，底稿数据已恢复')

      // 刷新历史列表
      await loadHistory()
    } catch {
      ElMessage.error('撤销失败，请稍后重试')
    }
  }

  // ─── Return ─────────────────────────────────────────────────────────────

  return {
    // 状态
    config,
    extractedVouchers,
    stats,
    loading,
    previewVisible,
    historyVisible,
    historyList,
    fillMode,

    // 计算属性
    selectedVouchers,
    selectedCount,
    cutoffErrorCount,
    selectedDebitTotal,
    selectedCreditTotal,
    dateRangeText,

    // 操作
    triggerExtraction,
    confirmFill,
    loadHistory,
    undoLastExtraction,
    toggleSelectAll,

    // 校验
    validateConfig,
    configErrors,
  }
}

export default useCutoffAutoSampling
