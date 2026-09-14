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
// 说明：readonly 支持 Ref 或 ComputedRef（组件侧多以 computed 传入）
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { determineCutoffStatus, computeDateRange, type CutoffDirection, type CutoffStatus } from './cutoffJudgment'
import { inWindow as canonicalInWindow, judgeCrossPeriod as canonicalJudge } from './cutoffCanonical'

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
  /** 只读态：为真时禁用一键取数与回写（R25.6） */
  readonly?: Ref<boolean> | ComputedRef<boolean>
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

// ─── 截止窗口纯函数（供一键取数与 PBT 复用；design C.2 / Property 11·12）────
//
// spec: voucher-check-sampling-integration, Task 10 基座（Task 3 先行落地以供属性测试）
// 纯函数、无 Vue 依赖，泛型保持调用方凭证结构不变。

/**
 * 基准日 ±N 天窗口过滤（纯函数）。
 *
 * 仅保留记账日期 d 满足 `cutoffDate − daysBefore ≤ d ≤ cutoffDate + daysAfter` 的凭证；
 * 窗口外或日期非法者一律排除。
 *
 * Requirements: 25.1, 25.3（design C.2 / Property 11）
 */
export function filterByCutoffWindow<T extends { voucherDate: string }>(
  vouchers: T[],
  cutoffDate: string,
  daysBefore: number,
  daysAfter: number,
): T[] {
  // 薄封装：委托 cutoffCanonical.inWindow（单一真源）。行为等价（P10 已锁定）。
  const list = Array.isArray(vouchers) ? vouchers : []
  return list.filter((v) => canonicalInWindow(v?.voucherDate, cutoffDate, daysBefore, daysAfter))
}

/**
 * 跨期判定（纯函数）。
 *
 * 当记账日期(voucherDate)与业务发生日期(businessDate)分居基准日两侧时为 true，
 * 同侧为 false；判定仅依赖各日期相对基准日的位置（> 基准日为"期后"，≤ 基准日为"期内/当日"）。
 * 单日期降级：缺业务发生日期时，退化为"记账日期落在基准日之后即需人工判断的跨期疑点"，
 * 位置判定语义不变。
 *
 * Requirements: 25.5（design C.2 / Property 12）
 */
export function markCutoffCrossPeriod(
  v: { voucherDate: string; businessDate?: string | null },
  cutoffDate: string,
): boolean {
  // 薄封装：委托 cutoffCanonical.judgeCrossPeriod（cutoff-boundary 模式）。
  // 双侧齐全→XOR；仅单侧(或另一侧非法)→单日期降级(晚于截止日为疑点)；均缺→false。
  // 行为等价 legacy（P8/P9 已锁定，含非法 businessDate 降级）。
  const verdict = canonicalJudge(
    { bookDate: v?.voucherDate ?? '', documentDate: v?.businessDate ?? '' },
    cutoffDate,
    'cutoff-boundary',
  )
  return verdict === 'crossing' || verdict === 'suspect'
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
    readonly,
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

  // ─── triggerCutoffFetch（一键取数：四表库凭证库联动，Req 25）───────────────
  //
  // 与 triggerExtraction（走 /cutoff-extract）不同，本函数复用抽凭引擎的
  // /sampling/voucher-extract 端点，以基准日 ±N 天窗口（filters.date_from/date_to）
  // 从四表库凭证库（tb_ledger）按科目/方向/金额检索，映射为 ExtractedVoucher，
  // 经纯函数 filterByCutoffWindow 兜底裁剪窗口、markCutoffCrossPeriod 标注跨期疑点，
  // 再打开预览由既有 confirmFill 回写。只读禁用（R25.6）。
  //
  // Requirements: 25.1, 25.2, 25.3, 25.4, 25.5, 25.6

  async function triggerCutoffFetch(): Promise<void> {
    // 只读禁用一键取数（R25.6）
    if (readonly?.value) {
      ElMessage.warning('只读状态下禁用一键取数')
      return
    }
    // 校验：基准日 + 科目范围（R25.1/R25.2）
    if (!validateConfig()) return

    loading.value = true
    try {
      // 基准日 ±N 天窗口（R25.1/R25.3）
      const { start, end } = computeDateRange(
        config.value.cutoffDate,
        config.value.daysBefore,
        config.value.daysAfter,
      )

      // 检索条件：科目范围 + 借贷方向 + 金额（R25.2），日期窗口经 filters.date_from/date_to
      const filters: Record<string, any> = {
        account_codes: config.value.accountCodes,
        direction_filter: config.value.directionFilter,
        voucher_type_filter: config.value.voucherTypeFilter,
        summary_keyword: config.value.summaryKeyword,
        // 一键取数为"检索总体"，不排除已提取（保证窗口内凭证完整可见）
        exclude_extracted: false,
        date_from: start,
        date_to: end,
      }
      if (config.value.amountThreshold && config.value.amountThreshold > 0) {
        // 金额条件：GREATEST(借,贷) ≥ 阈值（元），下沉到序时账查询
        filters.amount_min = config.value.amountThreshold
      }

      // 复用抽凭端点，specific_item + 阈值0 = 返回窗口内全部符合条件凭证（检索模式，R25.3）
      const res = await http.post(
        `/api/projects/${projectId.value}/sampling/voucher-extract`,
        {
          sampling_method: 'specific_item',
          sampling_params: { materiality_threshold: 0 },
          filters,
          workpaper_id: workpaperId.value,
          year: year.value,
        },
      )

      const data = res.data as any
      const items: any[] = data?.items ?? []
      const statsData = data?.stats ?? {}

      if (items.length === 0) {
        ElMessage.info('未找到符合条件的凭证')
        return
      }

      // 映射为 ExtractedVoucher，并用 markCutoffCrossPeriod 标注跨期疑点（R25.5）
      const mapped: ExtractedVoucher[] = items.map((item: any) => {
        const debitAmt = item.debit_amount ?? item.debitAmount ?? null
        const creditAmt = item.credit_amount ?? item.creditAmount ?? null
        const voucherDate = item.voucher_date ?? item.voucherDate ?? ''
        // 业务发生日期（单据日期）用于跨期判定；缺省时 markCutoffCrossPeriod 走单日期降级
        const businessDate =
          item.business_date ?? item.businessDate ?? item.bill_date ?? null

        const crossPeriod = markCutoffCrossPeriod(
          { voucherDate, businessDate },
          config.value.cutoffDate,
        )

        return {
          voucherNo: item.voucher_no ?? item.voucherNo ?? '',
          voucherDate,
          summary: item.summary ?? null,
          debitAmount: debitAmt != null ? String(debitAmt) : null,
          creditAmount: creditAmt != null ? String(creditAmt) : null,
          accountCode: item.account_code ?? item.accountCode ?? '',
          accountName: item.account_name ?? item.accountName ?? null,
          counterpartAccount:
            item.counterpart_account ?? item.counterpartAccount ?? null,
          voucherType: item.voucher_type ?? item.voucherType ?? null,
          cutoffStatus: crossPeriod ? ('可能跨期' as CutoffStatus) : ('正常' as CutoffStatus),
          remark: crossPeriod ? '跨期疑点' : '',
          selected: true, // 默认全部勾选
        } as ExtractedVoucher
      })

      // 纯函数兜底裁剪窗口（后端已按 date_from/date_to 过滤，此处保证客户端窗口不变量，R25.3）
      extractedVouchers.value = filterByCutoffWindow(
        mapped,
        config.value.cutoffDate,
        config.value.daysBefore,
        config.value.daysAfter,
      )

      if (extractedVouchers.value.length === 0) {
        ElMessage.info('未找到符合条件的凭证')
        return
      }

      // 填充统计（复用抽凭端点的总体统计口径）
      stats.value = {
        totalCount:
          statsData.population_count ?? statsData.totalCount ?? extractedVouchers.value.length,
        debitTotal: String(
          statsData.population_debit_total ?? statsData.debit_total ?? '0',
        ),
        creditTotal: String(
          statsData.population_credit_total ?? statsData.credit_total ?? '0',
        ),
        byVoucherType: {},
        truncated: data?.truncated ?? statsData.truncated ?? false,
      }

      // 打开预览弹窗，由既有 confirmFill 回写截止底稿（R25.4）
      previewVisible.value = true
    } catch (err: any) {
      ElMessage.error(err?.message || '一键取数失败，请稍后重试')
    } finally {
      loading.value = false
    }
  }

  // ─── confirmFill ────────────────────────────────────────────────────────

  async function confirmFill(): Promise<ExtractedVoucher[]> {
    // 只读禁用回写（R25.6）
    if (readonly?.value) {
      ElMessage.warning('只读状态下禁用回写')
      return []
    }
    const selected = selectedVouchers.value
    if (selected.length === 0) {
      ElMessage.warning('请至少勾选一条凭证')
      return []
    }

    const existing = existingSamples?.value ?? []
    const mode = fillMode.value

    // 应用填充策略
    const result = applyFillMode(existing, selected, mode)

    // 版本链快照由后端 cutoff-fill 统一创建（VersionTrailService），
    // 前端不再重复创建，避免一次填充产生两份快照。

    // 记录填充日志（含 before_data 快照 + filled_voucher_nos 供排除已提取）
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
          // 已填充凭证号 → 后端存入 extraction_criteria.filled_voucher_nos，
          // 供下次 exclude_extracted 排除，避免重复抽取
          filled_voucher_nos: selected.map(v => v.voucherNo).filter(Boolean),
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
        // 后端 cutoff-undo 强制要求 log_id + wp_id 两个 Query 参数，
        // 漏传 wp_id 会 422；wp_id 亦作归属安全校验。
        { params: { log_id: logId, wp_id: workpaperId.value } },
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
    triggerCutoffFetch,
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
