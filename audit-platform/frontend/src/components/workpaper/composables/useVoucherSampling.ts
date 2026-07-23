/**
 * useVoucherSampling — 通用抽凭引擎核心 composable
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 5.1
 *
 * 职责：
 * - 定义接口：VoucherSamplingOptions、ExtractionLogEntry、CompareResult
 * - config 响应式初始化（从 props 解析默认 accountCodes、method）
 * - validateConfig() — 委托 validateSamplingConfig
 * - triggerSampling() — POST /voucher-extract → 填充 sampledVouchers → 打开预览
 * - 选中统计 computed：selectedVouchers、selectedCount、selectedDebitTotal、selectedCreditTotal
 * - confirmFill(mode) — 按 phase 约束 mode → 生成 before_data 快照 → 按 mode 合并 → POST /cutoff-fill 记录日志
 * - fill mode 逻辑：append/replace/merge（replace 时仅清当前 phase 行）
 * - loadHistory() — GET /voucher-history
 * - undoLastExtraction(logId) — POST /voucher-undo
 * - compareVersions(logIdA, logIdB) — POST /voucher-compare
 * - updateField(index, field, value) — 更新字段 + 追加 edit_trail entry
 * - batchMarkChecked(indices) — 批量设 checkResult='Y' + 追加 trail
 * - checkCompliance() — 委托 checkCAS1314Compliance
 *
 * Requirements: 1.7, 1.8, 2.2, 3.9, 4.2, 4.5, 7.1, 7.2, 7.3, 7.4, 8.3, 9.1, 9.2, 9.3, 10.3, 10.4
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import {
  validateSamplingConfig,
  checkCAS1314Compliance,
  computeCoverage,
  computeMusInterval,
  computeSampleSize,
  markHighValueItems,
  projectMisstatement,
  deriveSamplingConclusion,
  type SamplingMethod,
  type Phase,
  type FillMode,
  type SamplingConfig,
  type SampledVoucher,
  type EditTrailEntry,
  type CoverageStats,
  type ComplianceWarning,
  type MisstatementResult,
  type SamplingConclusion,
} from './useSamplingAlgorithms'
import { useVersionTrail } from './useVersionTrail'

// ─── Interfaces ──────────────────────────────────────────────────────────────

export interface VoucherSamplingOptions {
  projectId: Ref<string>
  year: Ref<number>
  workpaperId: Ref<string>
  accountCode: string
  phase: Ref<Phase>
  defaultMethod?: SamplingMethod
  /** 初始期间月份 1-12（如期后默认 [1,2,3]） */
  initialPeriodRange?: number[]
  /** 打开引擎时合并进默认配置（如 I4-5 按测试原因预填关键词/方向） */
  initialConfigPatch?: Partial<SamplingConfig>
}

export interface ExtractionLogEntry {
  id: string
  createdAt: string
  userId: string
  samplingMethod: SamplingMethod
  sampleCount: number
  coverageStats: CoverageStats
  phase: Phase
  fillMode: FillMode
  isUndone: boolean
  extractionCriteria: Record<string, unknown>
  // ─── 方法学增强回显（R22 重抽治理/可复现；后端未就绪时兜底为 null）─────────
  /** 本次抽样使用的随机种子（R22.2 可复现，在历史与版本链展示） */
  randomSeed?: number | null
  /** MUS 抽样间隔（Decimal 字符串，R17） */
  samplingInterval?: string | null
  /** 重抽原因（R22.1） */
  resampleReason?: string | null
  /** 抽样结论文案（R18.5/18.6） */
  conclusion?: string | null
}

export interface CompareResult {
  added: SampledVoucher[]
  removed: SampledVoucher[]
  retained: SampledVoucher[]
}

// ─── Pure Function: applyFillMode（独立导出供 PBT 测试） ─────────────────────

/**
 * 填充策略纯函数
 *
 * - append: 将 selected 追加到 existing（当前 phase 行）末尾
 * - replace: 仅清空当前 phase 行，替换为 selected（保留其他 phase 行不动）
 * - merge: 按 voucher_no 去重，已存在于同 phase 的不重复添加
 *
 * @param existing 全量已有 samples（含所有 phase）
 * @param selected 本次要填充的凭证（已含正确 phase）
 * @param mode 填充策略
 * @param currentPhase 当前操作阶段
 */
export function applyFillMode(
  existing: SampledVoucher[],
  selected: SampledVoucher[],
  mode: FillMode,
  currentPhase: Phase,
): SampledVoucher[] {
  switch (mode) {
    case 'append':
      return [...existing, ...selected]

    case 'replace': {
      // 仅清除当前 phase 行，保留其他 phase 行
      const otherPhaseRows = existing.filter(v => v.phase !== currentPhase)
      return [...otherPhaseRows, ...selected]
    }

    case 'merge': {
      // 获取当前 phase 已有的 voucher_no 集合
      const existingPhaseNos = new Set(
        existing.filter(v => v.phase === currentPhase).map(v => v.voucherNo),
      )
      const newItems = selected.filter(v => !existingPhaseNos.has(v.voucherNo))
      return [...existing, ...newItems]
    }

    default:
      return [...existing, ...selected]
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useVoucherSampling(options: VoucherSamplingOptions) {
  const {
    projectId,
    year,
    workpaperId,
    accountCode,
    phase,
    defaultMethod,
    initialPeriodRange,
    initialConfigPatch,
  } = options

  // ─── Config 初始化 ──────────────────────────────────────────────────────

  function buildDefaultConfig(): SamplingConfig {
    // 从 accountCode 解析科目列表（支持逗号分隔如 "1122,1123"）
    const codes = accountCode
      ? accountCode.split(',').map(c => c.trim()).filter(Boolean)
      : []

    const months = (initialPeriodRange?.length
      ? initialPeriodRange.filter((m) => m >= 1 && m <= 12)
      : [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])

    const base: SamplingConfig = {
      samplingMethod: defaultMethod ?? 'random',
      sampleSize: 30,
      accountCodes: codes,
      periodRange: months.length ? months : [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
      directionFilter: 'all',
      voucherTypeFilter: [],
      summaryKeyword: '',
      excludeExtracted: true,
      samplingUnit: 'ledger_line',
      randomSeed: null,
      // ─── 方法学增强参数（可选，向后兼容）────────────────────────────
      confidenceLevel: undefined,
      tolerableMisstatement: undefined,
      expectedMisstatement: undefined,
      suggestedSampleSize: undefined,
      resampleReason: undefined,
    }
    if (!initialConfigPatch) return base
    return {
      ...base,
      ...initialConfigPatch,
      // 嵌套数组避免被 patch 意外覆盖为空
      accountCodes: initialConfigPatch.accountCodes?.length
        ? initialConfigPatch.accountCodes
        : base.accountCodes,
      periodRange: initialConfigPatch.periodRange?.length
        ? initialConfigPatch.periodRange
        : base.periodRange,
      voucherTypeFilter: initialConfigPatch.voucherTypeFilter
        ?? base.voucherTypeFilter,
    }
  }

  // ─── Reactive State ─────────────────────────────────────────────────────

  const config = ref<SamplingConfig>(buildDefaultConfig())
  const sampledVouchers = ref<SampledVoucher[]>([])
  const coverageStats = ref<CoverageStats | null>(null)
  const complianceWarnings = ref<ComplianceWarning[]>([])
  const loading = ref(false)
  const configDialogVisible = ref(false)
  const previewVisible = ref(false)
  const historyVisible = ref(false)
  const historyList = ref<ExtractionLogEntry[]>([])
  const fillMode = ref<FillMode>('append')
  const seedUsed = ref<number | null>(null)
  const configErrors = ref<Record<string, string>>({})

  // ─── 方法学增强状态（向后兼容，纯附加）───────────────────────────────────
  /** 系统建议样本量（R15.4 留痕；手工覆盖 config.sampleSize 后仍保留此建议值） */
  const suggestedSampleSize = ref<number | null>(null)
  /** 本次 MUS 抽样间隔（Decimal 字符串，R17.1 展示） */
  const samplingInterval = ref<string | null>(null)
  /** 错报推断结果（R18.2/18.4） */
  const misstatementResult = ref<MisstatementResult | null>(null)
  /** 抽样结论（R18.5/18.6；人工确认前不定稿） */
  const samplingConclusion = ref<SamplingConclusion | null>(null)
  /** 可容忍错报是否由重要性/B15 自动带入（R16；用于 UI 提示可覆盖） */
  const tolerableFromMateriality = ref(false)
  /**
   * 总体完整性核对信息（后端独立账面来源）：
   * - available=false → 无独立数据源，UI 显示"未执行核对"，不得以序时账总体自身比对。
   * - bookAmount → trial_balance 审定等独立账面；basis → 来源标识。
   */
  const reconcileInfo = ref<{
    available: boolean
    bookAmount: string | null
    basis: string | null
  } | null>(null)
  /** 后端方法学权威快照（含 algo_version）；抽样后由 triggerSampling 填充，回填时留痕 */
  const methodologySnapshot = ref<Record<string, any> | null>(null)

  // ─── 真实操作者解析（Req9）──────────────────────────────────────────────
  // edit_trail 本地 actor 用当前登录用户（乐观展示）；权威 actor 由后端持久化时以
  // current_user 记录。无 Pinia 的纯逻辑测试环境下 graceful 回退占位符。
  let _actorCache: string | null = null
  function resolveActor(): string {
    if (_actorCache) return _actorCache
    try {
      const store = useAuthStore()
      _actorCache = store.userId || store.username || 'current_user'
    } catch {
      _actorCache = 'current_user'
    }
    return _actorCache
  }

  // ─── Version Trail（延迟实例化）───────────────────────────────────────────
  // useVersionTrail 内部依赖 Pinia store（useAuthStore/useRoleContextStore），
  // 延迟到首次使用时实例化，避免无 Pinia 的纯逻辑测试环境实例化即报错。
  let _versionTrail: ReturnType<typeof useVersionTrail> | null = null
  function getVersionTrail(): ReturnType<typeof useVersionTrail> {
    if (!_versionTrail) {
      _versionTrail = useVersionTrail({ projectId, workpaperId })
    }
    return _versionTrail
  }

  // ─── Validation ─────────────────────────────────────────────────────────

  /**
   * 校验当前配置，委托 validateSamplingConfig
   * @returns true=校验通过
   */
  function validateConfig(): boolean {
    const errors = validateSamplingConfig(config.value)
    configErrors.value = errors
    return Object.keys(errors).length === 0
  }

  // ─── 方法学增强：重要性联动 / 样本量推导 / 错报推断 / 重抽治理 ───────────────

  /**
   * R16 从重要性/B15 底稿带入可容忍错报（实际执行重要性）作为初始值。
   *
   * - 成功：写入 config.tolerableMisstatement 并标记 tolerableFromMateriality=true，返回该值。
   * - 失败/未取到：不改动已有值，返回 null，允许审计师手工录入（R16.3）。
   *
   * @param pid 项目 ID，默认取当前 options.projectId
   * @returns 可容忍错报（Decimal 字符串）或 null
   */
  async function loadTolerableMisstatement(pid?: string): Promise<string | null> {
    const targetPid = pid ?? projectId.value
    if (!targetPid) return null
    try {
      const res = await http.get(`/api/projects/${targetPid}/materiality`, {
        params: { year: year.value },
        // 未编制重要性时后端可能 404，静默兜底允许手填
        _silent: true,
      } as any)
      const data = res.data as any
      const pm =
        data?.performance_materiality ??
        data?.performanceMateriality ??
        data?.overall_materiality ??
        data?.overallMateriality ??
        null
      if (pm == null || pm === '' || Number(pm) <= 0) return null
      const value = String(pm)
      config.value.tolerableMisstatement = value
      tolerableFromMateriality.value = true
      return value
    } catch {
      // 取数失败：允许手工录入（R16.3），不打断流程
      return null
    }
  }

  /**
   * R15 科学样本量推导（MUS）：依据置信度/可容忍错报/预期错报与总体金额推导建议样本量。
   *
   * 同步计算并留痕本次 MUS 抽样间隔（samplingInterval）。缺少置信度或可容忍错报时
   * 返回 0 并不改动配置（R15.5 由 validateConfig/UI 负责提示）。
   *
   * @param populationAmount 总体金额（Decimal 字符串），默认取当前覆盖率统计
   * @returns 建议样本量（非负整数，0 表示参数不足无法推导）
   */
  function computeSuggestedSampleSize(populationAmount?: string): number {
    const cfg = config.value
    const tol = cfg.tolerableMisstatement
    const cl = cfg.confidenceLevel
    if (!tol || tol === '' || cl == null || !(cl > 0 && cl < 1)) {
      return 0
    }
    const expected = cfg.expectedMisstatement && cfg.expectedMisstatement !== '' ? cfg.expectedMisstatement : '0'
    const popAmount = populationAmount ?? coverageStats.value?.populationAmount ?? '0'

    // 抽样间隔留痕
    samplingInterval.value = computeMusInterval(tol, cl, expected)

    const suggested = computeSampleSize(popAmount, tol, expected, cl)
    // R15.4 留痕：保留系统建议值（config.suggestedSampleSize 与 suggestedSampleSize ref）
    cfg.suggestedSampleSize = suggested
    suggestedSampleSize.value = suggested
    return suggested
  }

  /**
   * R15.3 采用系统建议样本量：将建议值写入当前方法的样本量参数（保留 suggestedSampleSize 留痕）。
   */
  function applySuggestedSampleSize(): void {
    const suggested = suggestedSampleSize.value
    if (suggested == null || suggested <= 0) return
    if (config.value.samplingMethod === 'mus') {
      config.value.musSampleSize = suggested
    } else {
      config.value.sampleSize = suggested
    }
  }

  /**
   * R18 错报推断与总体结论
   *
   * 基于样本已录入的实际错报（actualMisstatement）按当前抽样方法推断总体错报，
   * 计算错报上限（UML），并与可容忍错报比较得出结论建议。人工确认前不写入底稿（R18.7）。
   *
   * @returns { result, conclusion } 推断结果与结论（可容忍错报缺失时 conclusion 为 null）
   */
  function inferMisstatement(): {
    result: MisstatementResult
    conclusion: SamplingConclusion | null
  } {
    const cl = config.value.confidenceLevel ?? 0.95
    const interval = samplingInterval.value ?? '0'
    const popAmount = coverageStats.value?.populationAmount ?? '0'
    // R18：仅纳入已检查（checkResult 非空：Y/N/异常）的样本参与推断。
    // 未检查样本的 actualMisstatement 为空会被当作“零错报”，若计入将系统性低估
    // 推断错报与错报上限（UML），故此处显式排除，未检查数量由 uncheckedSampleCount 暴露给 UI 提示。
    const samples = sampledVouchers.value.filter(v => v.checkResult !== '')

    const result = projectMisstatement(
      samples,
      config.value.samplingMethod,
      interval,
      popAmount,
      cl,
    )
    misstatementResult.value = result

    const tol = config.value.tolerableMisstatement
    let conclusion: SamplingConclusion | null = null
    if (tol && tol !== '') {
      conclusion = deriveSamplingConclusion(result.upperLimit, tol)
    }
    samplingConclusion.value = conclusion
    return { result, conclusion }
  }

  /**
   * R18.1 录入某样本的实际错报金额（Decimal 字符串）+ edit_trail 留痕，并即时重算推断。
   *
   * @param index sampledVouchers 数组索引
   * @param value 实际错报金额
   */
  function recordActualMisstatement(index: number, value: string): void {
    const voucher = sampledVouchers.value[index]
    if (!voucher) return
    const oldValue = String(voucher.actualMisstatement ?? '')
    const newValue = String(value ?? '')
    voucher.actualMisstatement = newValue

    voucher.editTrail.push({
      userId: resolveActor(),
      timestamp: new Date().toISOString(),
      field: 'actualMisstatement',
      oldValue,
      newValue,
    })

    // 即时重算推断错报与结论
    inferMisstatement()
  }

  /**
   * R22 重抽治理：重抽必须录入原因（R22.1），不静默覆盖历史批次（R22.3，历史由后端逐条留存）。
   *
   * 重置随机种子以便本次重抽由后端生成新的可复现种子（R22.2）。
   *
   * @param reason 重抽原因（必填）
   * @returns 是否已发起重抽
   */
  async function resample(reason: string): Promise<boolean> {
    const trimmed = (reason ?? '').trim()
    if (!trimmed) {
      ElMessage.warning('重抽必须填写重抽原因')
      return false
    }
    config.value.resampleReason = trimmed
    // 重置种子 → 后端生成并回传新种子（seedUsed），保证可复现且不复用旧批次
    config.value.randomSeed = null
    await triggerSampling()
    return true
  }

  // ─── Computed: 选中统计 ─────────────────────────────────────────────────

  const selectedVouchers: ComputedRef<SampledVoucher[]> = computed(() => {
    return sampledVouchers.value.filter(v => v.selected)
  })

  const selectedCount: ComputedRef<number> = computed(() => {
    return selectedVouchers.value.length
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

  /** 已检查样本数（checkResult 非空），参与错报推断的样本集合大小 */
  const checkedSampleCount: ComputedRef<number> = computed(() => {
    return sampledVouchers.value.filter(v => v.checkResult !== '').length
  })

  /** 未检查样本数（checkResult 为空），不参与错报推断，UI 据此提示审计师补录核查结果 */
  const uncheckedSampleCount: ComputedRef<number> = computed(() => {
    return sampledVouchers.value.filter(v => v.checkResult === '').length
  })

  // ─── triggerSampling ────────────────────────────────────────────────────

  /**
   * 执行抽样：POST /voucher-extract → 填充 sampledVouchers → 打开预览
   */
  async function triggerSampling(): Promise<void> {
    if (!validateConfig()) return

    loading.value = true
    try {
      // 构建请求体
      const body: Record<string, unknown> = {
        sampling_method: config.value.samplingMethod,
        // 方法学参数随请求发送，供后端 CAS1314 权威口径计算间隔/样本量（单一真源）
        sampling_params: {
          ...buildSamplingParams(),
          confidence_level: config.value.confidenceLevel ?? null,
          tolerable_misstatement: config.value.tolerableMisstatement ?? null,
          expected_misstatement: config.value.expectedMisstatement ?? null,
        },
        random_seed: config.value.randomSeed ?? null,
        phase: phase.value,
        workpaper_id: workpaperId.value,
        year: year.value,
        filters: {
          account_codes: config.value.accountCodes,
          period_range: config.value.periodRange,
          amount_min: config.value.amountMin ?? null,
          amount_max: config.value.amountMax ?? null,
          direction_filter: config.value.directionFilter,
          voucher_type_filter: config.value.voucherTypeFilter,
          summary_keyword: config.value.summaryKeyword,
          exclude_extracted: config.value.excludeExtracted,
          sampling_unit: config.value.samplingUnit ?? 'ledger_line',
        },
      }

      const res = await http.post(
        `/api/projects/${projectId.value}/sampling/voucher-extract`,
        body,
      )

      const data = res.data as any
      const items: any[] = data?.items ?? []
      const statsData = data?.stats ?? {}
      const responseSeedUsed: number | null = data?.seed_used ?? null
      const truncated: boolean = data?.truncated ?? false

      if (items.length === 0) {
        ElMessage.info('未找到符合条件的凭证，请调整过滤条件')
        return
      }

      // 记录种子
      seedUsed.value = responseSeedUsed

      // 映射为 SampledVoucher（默认全选、phase取当前阶段）
      sampledVouchers.value = items.map((item: any) => ({
        id: item.id != null ? String(item.id) : undefined,  // 序时账行 id（P3 行级排除）
        voucherNo: item.voucher_no ?? item.voucherNo ?? '',
        voucherDate: item.voucher_date ?? item.voucherDate ?? '',
        summary: item.summary ?? null,
        debitAmount: item.debit_amount != null ? String(item.debit_amount) : (item.debitAmount != null ? String(item.debitAmount) : null),
        creditAmount: item.credit_amount != null ? String(item.credit_amount) : (item.creditAmount != null ? String(item.creditAmount) : null),
        accountCode: item.account_code ?? item.accountCode ?? '',
        accountName: item.account_name ?? item.accountName ?? null,
        counterpartAccount: item.counterpart_account ?? item.counterpartAccount ?? null,
        voucherType: item.voucher_type ?? item.voucherType ?? null,
        accountingPeriod: item.accounting_period ?? item.accountingPeriod ?? null,
        checkResult: '',
        abnormal: false,
        remark: '',
        selected: true,
        phase: phase.value,
        editTrail: [],
      } as SampledVoucher))

      // 填充覆盖率统计
      coverageStats.value = {
        populationCount: statsData.population_count ?? statsData.populationCount ?? 0,
        populationAmount: String(statsData.population_amount ?? statsData.populationAmount ?? '0'),
        sampleCount: statsData.sample_count ?? statsData.sampleCount ?? items.length,
        sampleAmount: String(statsData.sample_amount ?? statsData.sampleAmount ?? '0'),
        countCoverageRate: String(statsData.count_coverage_rate ?? statsData.countCoverageRate ?? '0.00'),
        amountCoverageRate: String(statsData.amount_coverage_rate ?? statsData.amountCoverageRate ?? '0.00'),
      }

      // 总体完整性核对信息（独立账面来源）
      reconcileInfo.value = {
        available: statsData.reconcile_available === true,
        bookAmount:
          statsData.book_amount != null ? String(statsData.book_amount) : null,
        basis: statsData.reconcile_basis ?? null,
      }

      // ─── 方法学单一真源：优先消费后端权威快照（interval/suggested/algo_version）───
      // 后端以 CAS1314 权威口径计算；前端 computeSuggestedSampleSize 仅作即时预览兜底。
      const methodologyData = data?.methodology ?? null
      methodologySnapshot.value = methodologyData
      samplingInterval.value = null
      const backendInterval = methodologyData?.sampling_interval
      if (backendInterval != null && backendInterval !== '' && backendInterval !== '0.00') {
        // 后端权威间隔
        samplingInterval.value = String(backendInterval)
        const backendSuggested = methodologyData?.suggested_sample_size
        if (backendSuggested != null) {
          suggestedSampleSize.value = Number(backendSuggested)
          config.value.suggestedSampleSize = Number(backendSuggested)
        }
        sampledVouchers.value = markHighValueItems(sampledVouchers.value, samplingInterval.value)
      } else if (
        config.value.samplingMethod === 'mus' &&
        config.value.tolerableMisstatement &&
        config.value.confidenceLevel != null
      ) {
        // 后端未返回间隔时，前端即时预览兜底（保持原行为）
        computeSuggestedSampleSize(coverageStats.value.populationAmount)
        if (samplingInterval.value) {
          sampledVouchers.value = markHighValueItems(sampledVouchers.value, samplingInterval.value)
        }
      }

      // 每次新抽样重置上一批次的错报推断状态（历史批次由后端留存，不受影响）
      misstatementResult.value = null
      samplingConclusion.value = null

      // 截断提示
      if (truncated) {
        ElMessage.warning('抽样结果超过500条，已截断显示')
      }

      // 打开预览弹窗
      previewVisible.value = true
    } catch (err: any) {
      ElMessage.error(err?.message || '抽样执行失败，请稍后重试')
    } finally {
      loading.value = false
    }
  }

  /**
   * 根据当前 config 构建各方法特有的 sampling_params
   */
  function buildSamplingParams(): Record<string, unknown> {
    const cfg = config.value
    switch (cfg.samplingMethod) {
      case 'random':
        return { sample_size: cfg.sampleSize }
      case 'stratified':
        return {
          strata: (cfg.strata ?? []).map(s => ({
            lower_bound: s.lowerBound,
            upper_bound: s.upperBound,
            sample_size: s.sampleSize,
          })),
        }
      case 'specific_item':
        return { materiality_threshold: cfg.materialityThreshold }
      case 'systematic':
        return { start_point: cfg.startPoint, interval: cfg.interval }
      case 'mus':
        return { sample_size: cfg.musSampleSize }
      default:
        return {}
    }
  }

  // ─── confirmFill ────────────────────────────────────────────────────────

  /**
   * 确认填充：按 phase 约束 mode → 生成 before_data 快照 → 按 mode 合并 → POST 记录日志
   *
   * 返回合并后的全量 samples，由父组件决定如何集成
   *
   * @param existingSamples 当前已有的全量 samples（由父组件传入）
   */
  async function confirmFill(existingSamples?: SampledVoucher[]): Promise<SampledVoucher[]> {
    const selected = selectedVouchers.value
    if (selected.length === 0) {
      ElMessage.warning('请至少勾选一条凭证')
      return []
    }

    const existing = existingSamples ?? []
    // 年审阶段强制 append
    const effectiveMode: FillMode = phase.value === 'final' ? 'append' : fillMode.value

    // 生成 before_data 快照（当前 phase 的行）
    const beforeData = existing.filter(v => v.phase === phase.value)

    // 应用填充策略
    const result = applyFillMode(existing, selected, effectiveMode, phase.value)

    // R9.1 创建版本链快照（经 useVersionTrail；含方法/间隔/样本量/seed，
    // 执行人与时间由后端补全）。fire-and-forget，失败不阻塞主流程。
    const snapshotDesc =
      `抽凭填充：方法=${config.value.samplingMethod}` +
      ` 科目=${config.value.accountCodes.join(',')}` +
      ` 间隔=${samplingInterval.value ?? '-'}` +
      ` 样本量=${selected.length}` +
      ` seed=${seedUsed.value ?? '-'}` +
      ` phase=${phase.value}` +
      (config.value.resampleReason ? ` 重抽原因=${config.value.resampleReason}` : '')
    try {
      void getVersionTrail()
        .createSnapshot(snapshotDesc, { snapshotType: 'auto_sampling', silent: true })
        .catch(() => {
          // fire-and-forget: 版本链快照失败仅静默忽略
        })
    } catch {
      // 版本链实例化失败（如无 Pinia 环境）不影响回填主流程
    }

    // 记录填充日志（含 before_data 快照 — 向后兼容）
    try {
      await http.post(
        `/api/projects/${projectId.value}/sampling/cutoff-fill`,
        {
          project_id: projectId.value,
          workpaper_id: workpaperId.value,
          extraction_type: 'voucher_sampling',
          extraction_criteria: {
            sampling_method: config.value.samplingMethod,
            sampling_params: buildSamplingParams(),
            random_seed: seedUsed.value,
            phase: phase.value,
            // 本次实际回填的凭证号清单：后端据此排除已抽凭证、预审转年审排重、
            // 版本比较（此前从不发送 → 排重/比较链路空转）。去空去重保持稳定。
            filled_voucher_nos: Array.from(
              new Set(selected.map(v => v.voucherNo).filter(Boolean)),
            ),
            // 本次回填的分录行 id 清单（P3 行级排除）：ledger_line 单位下后端据此按行排除，
            // 避免"同一凭证号跨不同科目"被整张误排。有 id 才发送（向后兼容旧样本无 id）。
            filled_unit_ids: Array.from(
              new Set(selected.map(v => v.id).filter((x): x is string => !!x)),
            ),
            // ─── 方法学增强字段（后端未就绪时作为冗余 JSON 留存，向后兼容）───
            confidence_level: config.value.confidenceLevel ?? null,
            tolerable_misstatement: config.value.tolerableMisstatement ?? null,
            expected_misstatement: config.value.expectedMisstatement ?? null,
            suggested_sample_size: config.value.suggestedSampleSize ?? null,
            sampling_interval: samplingInterval.value ?? null,
            resample_reason: config.value.resampleReason ?? null,
            conclusion: samplingConclusion.value?.message ?? null,
            // 方法学算法版本留痕（后端权威快照），支持未来漂移追溯（Req6.3）
            algo_version: methodologySnapshot.value?.algo_version ?? null,
            coverage_stats: coverageStats.value
              ? {
                  count_rate: coverageStats.value.countCoverageRate,
                  amount_rate: coverageStats.value.amountCoverageRate,
                }
              : null,
            filters: {
              account_codes: config.value.accountCodes,
              period_range: config.value.periodRange,
              amount_min: config.value.amountMin ?? null,
              amount_max: config.value.amountMax ?? null,
              direction_filter: config.value.directionFilter,
              voucher_type_filter: config.value.voucherTypeFilter,
              summary_keyword: config.value.summaryKeyword,
              exclude_extracted: config.value.excludeExtracted,
            },
          },
          total_matched: coverageStats.value?.populationCount ?? selected.length,
          filled_count: selected.length,
          fill_mode: effectiveMode,
          before_data: beforeData,
        },
      )
    } catch {
      ElMessage.error('记录填充日志失败')
      return []
    }

    // 关闭预览
    previewVisible.value = false
    ElMessage.success(`成功填充${selected.length}笔凭证`)

    return result
  }

  // ─── toggleSelectAll ────────────────────────────────────────────────────

  function toggleSelectAll(selected: boolean): void {
    sampledVouchers.value.forEach(v => { v.selected = selected })
  }

  // ─── loadHistory ────────────────────────────────────────────────────────

  /**
   * 加载抽凭历史 — GET /voucher-history
   */
  async function loadHistory(): Promise<void> {
    try {
      const res = await http.get(
        `/api/projects/${projectId.value}/sampling/voucher-history`,
        { params: { wp_id: workpaperId.value } },
      )

      const data = res.data as any
      const list: any[] = Array.isArray(data) ? data : (data?.items ?? [])

      historyList.value = list.map((item: any) => {
        const criteria = item.extraction_criteria ?? item.extractionCriteria ?? {}
        return {
          id: item.id ?? '',
          createdAt: item.created_at ?? item.createdAt ?? '',
          userId: item.user_id ?? item.userId ?? '',
          samplingMethod: item.sampling_method ?? item.samplingMethod ?? criteria.sampling_method ?? 'random',
          sampleCount: item.filled_count ?? item.filledCount ?? item.sampleCount ?? 0,
          coverageStats: parseCoverageStats(item),
          phase: criteria.phase ?? item.phase ?? 'preliminary',
          fillMode: item.fill_mode ?? item.fillMode ?? 'append',
          isUndone: item.is_undone ?? item.isUndone ?? false,
          extractionCriteria: criteria,
          // ─── 方法学增强回显（R22 seed/重抽原因；R17 间隔；R18 结论）兜底 null ──
          randomSeed: item.random_seed ?? item.randomSeed ?? criteria.random_seed ?? null,
          samplingInterval: item.sampling_interval ?? item.samplingInterval ?? criteria.sampling_interval ?? null,
          resampleReason: item.resample_reason ?? item.resampleReason ?? criteria.resample_reason ?? null,
          conclusion: item.conclusion ?? criteria.conclusion ?? null,
        }
      })

      historyVisible.value = true
    } catch {
      ElMessage.error('加载抽凭历史失败')
    }
  }

  /**
   * 从历史条目解析 CoverageStats
   */
  function parseCoverageStats(item: any): CoverageStats {
    const criteria = item.extraction_criteria ?? item.extractionCriteria ?? {}
    const cs = criteria.coverage_stats ?? criteria.coverageStats ?? {}
    return {
      populationCount: item.total_matched ?? item.totalMatched ?? 0,
      populationAmount: '0',
      sampleCount: item.filled_count ?? item.filledCount ?? 0,
      sampleAmount: '0',
      countCoverageRate: String(cs.count_rate ?? cs.countCoverageRate ?? '0.00'),
      amountCoverageRate: String(cs.amount_rate ?? cs.amountCoverageRate ?? '0.00'),
    }
  }

  // ─── undoLastExtraction ─────────────────────────────────────────────────

  /**
   * 撤销最近一次抽凭操作 — POST /voucher-undo
   *
   * @param logId 要撤销的日志记录 ID
   * @returns before_data（撤销前的快照数据）
   */
  async function undoLastExtraction(logId: string): Promise<SampledVoucher[]> {
    try {
      const res = await http.post(
        `/api/projects/${projectId.value}/sampling/voucher-undo`,
        null,
        { params: { log_id: logId } },
      )

      const data = res.data as any
      const beforeData: SampledVoucher[] = data?.before_data ?? data?.beforeData ?? []

      ElMessage.success('已撤销，底稿数据已恢复')

      // 刷新历史列表
      await loadHistory()

      return beforeData
    } catch {
      ElMessage.error('撤销失败，请稍后重试')
      return []
    }
  }

  // ─── compareVersions ────────────────────────────────────────────────────

  /**
   * 对比两次抽凭记录 — POST /voucher-compare
   *
   * @param logIdA 第一次抽凭日志ID
   * @param logIdB 第二次抽凭日志ID
   * @returns CompareResult（added/removed/retained）
   */
  async function compareVersions(logIdA: string, logIdB: string): Promise<CompareResult> {
    try {
      const res = await http.post(
        `/api/projects/${projectId.value}/sampling/voucher-compare`,
        { log_id_a: logIdA, log_id_b: logIdB },
      )

      const data = res.data as any
      return {
        added: data?.added ?? [],
        removed: data?.removed ?? [],
        retained: data?.retained ?? [],
      }
    } catch {
      ElMessage.error('版本对比失败')
      return { added: [], removed: [], retained: [] }
    }
  }

  // ─── updateField ────────────────────────────────────────────────────────

  /**
   * 更新凭证行的指定字段 + 追加 edit_trail 留痕
   *
   * @param index sampledVouchers 数组索引
   * @param field 字段名（如 'checkResult'、'remark'、'abnormal'）
   * @param value 新值
   */
  function updateField(index: number, field: string, value: unknown): void {
    const voucher = sampledVouchers.value[index]
    if (!voucher) return

    // 记录旧值
    const oldValue = String((voucher as any)[field] ?? '')
    const newValue = String(value ?? '')

    // 更新字段值
    ;(voucher as any)[field] = value

    // 追加 edit_trail entry
    const trailEntry: EditTrailEntry = {
      userId: resolveActor(),
      timestamp: new Date().toISOString(),
      field,
      oldValue,
      newValue,
    }
    voucher.editTrail.push(trailEntry)
  }

  // ─── batchMarkChecked ───────────────────────────────────────────────────

  /**
   * 批量标记已核查：设 checkResult='Y' + 追加 trail
   *
   * @param indices sampledVouchers 数组索引列表
   */
  function batchMarkChecked(indices: number[]): void {
    for (const idx of indices) {
      const voucher = sampledVouchers.value[idx]
      if (!voucher) continue

      const oldValue = String(voucher.checkResult ?? '')
      voucher.checkResult = 'Y'

      const trailEntry: EditTrailEntry = {
        userId: resolveActor(),
        timestamp: new Date().toISOString(),
        field: 'checkResult',
        oldValue,
        newValue: 'Y',
      }
      voucher.editTrail.push(trailEntry)
    }
  }

  // ─── checkCompliance ────────────────────────────────────────────────────

  /**
   * CAS 1314 合规性检查 — 委托 checkCAS1314Compliance
   *
   * @returns ComplianceWarning[] 合规警告列表
   */
  function checkCompliance(): ComplianceWarning[] {
    if (!coverageStats.value) return []

    const warnings = checkCAS1314Compliance(
      coverageStats.value,
      config.value.samplingMethod,
      selectedCount.value,
      sampledVouchers.value.length,
    )
    complianceWarnings.value = warnings
    return warnings
  }

  // ─── Return ─────────────────────────────────────────────────────────────

  return {
    // 状态
    config,
    sampledVouchers,
    coverageStats,
    complianceWarnings,
    loading,
    configDialogVisible,
    previewVisible,
    historyVisible,
    historyList,
    fillMode,
    seedUsed,

    // 方法学增强状态
    suggestedSampleSize,
    samplingInterval,
    misstatementResult,
    samplingConclusion,
    tolerableFromMateriality,
    reconcileInfo,
    methodologySnapshot,

    // 计算属性
    selectedVouchers,
    selectedCount,
    selectedDebitTotal,
    selectedCreditTotal,
    checkedSampleCount,
    uncheckedSampleCount,

    // 操作
    triggerSampling,
    confirmFill,
    loadHistory,
    undoLastExtraction,
    compareVersions,
    toggleSelectAll,
    updateField,
    batchMarkChecked,

    // 方法学增强操作（R15/R16/R18/R22）
    loadTolerableMisstatement,
    computeSuggestedSampleSize,
    applySuggestedSampleSize,
    inferMisstatement,
    recordActualMisstatement,
    resample,

    // 校验
    validateConfig,
    configErrors,

    // CAS 1314 合规
    checkCompliance,
  }
}

export default useVoucherSampling
