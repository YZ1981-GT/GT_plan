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
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
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

/** 跨底稿重复抽凭项（后端 `cross_workpaper_duplicates` 的一条，R8.1） */
export interface CrossWpDuplicate {
  voucherNo: string
  /** 抽过它的底稿编码（去重排序）；取不到 wp_code 时为空数组 */
  wpCodes: string[]
  /** 涉及的批次数 */
  batchCount: number
}

/**
 * 审计师对跨底稿重复项的处置（R8.5/8.7）：
 * - `keep_all` 保留全部（有意交叉复核）
 * - `removed` 剔除重复项（避免样本浪费与覆盖率虚高）
 * - `none` 本次未涉及重复 / 用户取消了抽样
 */
export type DuplicateDecision = 'keep_all' | 'removed' | 'none'

export interface VoucherSamplingOptions {
  projectId: Ref<string>
  year: Ref<number>
  workpaperId: Ref<string>
  accountCode: string
  /**
   * 宿主底稿编码（如 'D2'），仅用于推断错报推送 A13 时的 source_wp_code 溯源。
   * 缺省为空串 → 该字段留 null（不用科目码冒充底稿编码，否则错报汇总的来源列不可信）。
   */
  wpCode?: string
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
  /**
   * 抽样框数据集版本（R1）：本次抽样所依据的 active 序时账版本 id。
   * null = 未识别到已激活账套版本（如尚未导入账套）→ 该批次无法据 seed 复算，
   * UI 如实提示但不阻断抽样（"先建底稿后导账套"是合法工作流）。
   */
  const datasetId = ref<string | null>(null)
  /**
   * 跨底稿重复抽凭（R8）：本次样本中被**其它底稿**抽取登记过的凭证。
   *
   * 重复抽同一张凭证有时是有意的（不同循环从不同认定角度检查同一笔交易），有时是
   * 样本浪费（覆盖率虚高）→ 由审计师在弹窗里判断，不由配置项静默决定。
   */
  const crossWpDuplicates = ref<CrossWpDuplicate[]>([])
  /** 审计师对重复项的处置（随回填留痕落库，R8.7） */
  const duplicateDecision = ref<DuplicateDecision>('none')
  /**
   * 评价来源批次（R2.7）：抽样评价从既有批次回读时标注来源，供审计师区分
   * "这是上一批次的结论"与"这是刚算出来的结论"。执行新抽样后清空（R2.8）。
   */
  const loadedFromBatch = ref<{
    logId: string
    batchId: string | null
    evaluatedAt: string | null
  } | null>(null)
  /**
   * 结论人工确认标识（R18.7：确认前不定稿）。
   *
   * 原先是 `GtVoucherSamplingEngine.vue` 的组件级 ref，现收进 composable 作单一真源 ——
   * 回读既有批次评价时必须能还原该状态（R2.7），组件级 ref 随 destroy-on-close 消失。
   */
  const conclusionConfirmed = ref(false)
  /** 本批次推断错报已推送至 A13 的时间戳（R3.7 防重复计入错报汇总） */
  const a13PushedAt = ref<string | null>(null)
  /**
   * 抑制一次「结论变化 ⇒ 人工确认失效」：仅供回读既有评价时使用。
   * 回读会先写 samplingConclusion 再写 conclusionConfirmed，若不抑制，watch 会把
   * 刚还原的确认状态立刻打回 false（表现为"上次确认过的结论重开后又要再确认一遍"）。
   */
  let suppressConfirmInvalidateOnce = false

  // 任一次错报推断/结论重算（录入实际错报、重新推断、重抽、重新抽样清空）都会使
  // 上一次的人工确认失效，强制审计师对最新结论重新确认后方可定稿。
  watch(samplingConclusion, () => {
    if (suppressConfirmInvalidateOnce) {
      suppressConfirmInvalidateOnce = false
      return
    }
    conclusionConfirmed.value = false
  })

  /** 人工确认当前结论（R18.7 门禁的唯一放开入口） */
  function confirmConclusion(): void {
    conclusionConfirmed.value = true
  }

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
          // R5.5 排除范围：缺省 'workpaper' 与改造前行为逐字节等价
          exclude_scope: config.value.excludeScope ?? 'workpaper',
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

      // R1：记录抽样框数据集版本；未识别时如实提示（不阻断）
      const rawDatasetId = statsData.dataset_id ?? statsData.datasetId ?? null
      datasetId.value = rawDatasetId != null ? String(rawDatasetId) : null
      if (datasetId.value === null) {
        ElMessage.info(
          '未识别到已激活账套版本，本次抽样无法绑定抽样框版本（后续无法据随机种子复算）',
        )
      }

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
        // 往来单位（后端按 tb_aux_ledger 精确匹配补全）。三态语义见
        // SampledVoucher.partyName 的注释：null 不区分「无此维度／未匹配／歧义」，
        // 歧义单独由 partyAmbiguous 表达 —— 不能用「有没有名字」反推。
        partyName: item.party_name ?? item.partyName ?? null,
        partyAuxType: item.party_aux_type ?? item.partyAuxType ?? null,
        partyAmbiguous: Boolean(item.party_ambiguous ?? item.partyAmbiguous ?? false),
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
      // R2.8：同时清空"评价来自哪个批次"的标注 —— 否则界面会把上一批次的结论
      // 挂到全新样本上（结论与样本不匹配，是比无结论更坏的状态）
      loadedFromBatch.value = null

      // 截断提示
      if (truncated) {
        ElMessage.warning('抽样结果超过500条，已截断显示')
      }

      // R8：跨底稿重复抽凭 → 弹窗要求审计师显式判断（在打开预览**之前**）
      crossWpDuplicates.value = (data?.cross_workpaper_duplicates ?? []).map(
        (d: any) => ({
          voucherNo: String(d.voucher_no ?? d.voucherNo ?? ''),
          wpCodes: Array.isArray(d.wp_codes ?? d.wpCodes)
            ? (d.wp_codes ?? d.wpCodes).map((c: any) => String(c))
            : [],
          batchCount: Number(d.batch_count ?? d.batchCount ?? 0) || 0,
        }),
      )
      duplicateDecision.value = 'none'
      if (crossWpDuplicates.value.length > 0) {
        const proceed = await confirmCrossWpDuplicates()
        if (!proceed) {
          // 用户取消：放弃本次抽样结果（不打开预览，不留半套样本）
          sampledVouchers.value = []
          coverageStats.value = null
          return
        }
      }

      // 打开预览弹窗
      previewVisible.value = true
    } catch (err: any) {
      ElMessage.error(err?.message || '抽样执行失败，请稍后重试')
    } finally {
      loading.value = false
    }
  }

  // ─── 跨底稿重复抽凭确认（R8）────────────────────────────────────────────

  /** 重复项清单文案：>10 条截断显示并给出总数（R8.4） */
  function buildDuplicateSummary(dups: CrossWpDuplicate[], maxLines = 10): string {
    const shown = dups.slice(0, maxLines)
    const lines = shown.map((d) => {
      const where = d.wpCodes.length ? d.wpCodes.join('、') : '未知底稿'
      return `${d.voucherNo}（已被 ${where} 抽取）`
    })
    if (dups.length > shown.length) {
      lines.push(`……另有 ${dups.length - shown.length} 张，共 ${dups.length} 张`)
    }
    return lines.join('<br/>')
  }

  /**
   * 弹窗要求审计师对跨底稿重复项显式表态（R8.5）。
   *
   * 三出口：保留全部（有意交叉复核）／剔除重复项／取消本次抽样。
   * 返回 true = 继续打开预览；false = 放弃本次抽样结果。
   */
  async function confirmCrossWpDuplicates(): Promise<boolean> {
    const dups = crossWpDuplicates.value
    const dupSet = new Set(dups.map((d) => d.voucherNo))
    const body =
      `本次抽到的 <b>${dups.length}</b> 张凭证已被本项目其它底稿抽查过：<br/><br/>` +
      buildDuplicateSummary(dups) +
      '<br/><br/>重复抽查可能是有意的交叉复核，也可能造成样本浪费与覆盖率虚高，' +
      '请判断如何处置（本次选择将随抽凭留痕归档）。'

    try {
      const action = await ElMessageBox.confirm(body, '跨底稿重复抽凭确认', {
        dangerouslyUseHTMLString: true,
        distinguishCancelAndClose: true,
        confirmButtonText: '保留全部',
        cancelButtonText: '剔除重复项',
        type: 'warning',
      })
      void action
      duplicateDecision.value = 'keep_all'
      ElMessage.info(`已保留全部样本（含 ${dups.length} 张重复凭证）`)
      return true
    } catch (action) {
      if (action === 'cancel') {
        // 「剔除重复项」：移除重复凭证并按剩余样本重算覆盖率展示（R8.6）
        const before = sampledVouchers.value.length
        sampledVouchers.value = sampledVouchers.value.filter(
          (v) => !dupSet.has(v.voucherNo),
        )
        duplicateDecision.value = 'removed'
        recomputeCoverageAfterRemoval()
        const removed = before - sampledVouchers.value.length
        if (sampledVouchers.value.length === 0) {
          ElMessage.warning(
            `剔除 ${removed} 张重复凭证后已无剩余样本，请调整过滤条件或增大样本量后重抽`,
          )
          coverageStats.value = null
          return false
        }
        ElMessage.warning(
          `已剔除 ${removed} 张重复凭证，实际样本量降为 ${sampledVouchers.value.length} 笔`,
        )
        return true
      }
      // 关闭 / ESC → 取消本次抽样
      duplicateDecision.value = 'none'
      ElMessage.info('已取消本次抽样')
      return false
    }
  }

  /**
   * 剔除重复项后按剩余样本重算覆盖率展示（R8.6）。
   *
   * 分母（总体笔数/金额）**不变** —— 总体没变，变的只是样本；用变小的分母会让覆盖率
   * 虚高，正是本功能要避免的问题。
   */
  function recomputeCoverageAfterRemoval(): void {
    const stats = coverageStats.value
    if (!stats) return
    const sampleCount = sampledVouchers.value.length
    const sampleAmount = sampledVouchers.value.reduce((sum, v) => {
      const debit = v.debitAmount ? parseFloat(v.debitAmount) || 0 : 0
      const credit = v.creditAmount ? parseFloat(v.creditAmount) || 0 : 0
      return sum + Math.max(Math.abs(debit), Math.abs(credit))
    }, 0)
    const popCount = stats.populationCount || 0
    const popAmount = parseFloat(stats.populationAmount) || 0
    coverageStats.value = {
      ...stats,
      sampleCount,
      sampleAmount: sampleAmount.toFixed(2),
      countCoverageRate: popCount
        ? ((sampleCount / popCount) * 100).toFixed(2)
        : '0.00',
      amountCoverageRate: popAmount
        ? ((sampleAmount / popAmount) * 100).toFixed(2)
        : '0.00',
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
            // R1.3 抽样框版本留痕：序时账重导后据此判定该批次已不可复算。
            // 取本次 extract 返回值；未识别时为 null（不兜底）。
            dataset_id: datasetId.value,
            // R2.5：回填时若已完成推断，评价随留痕一并落库（省一次往返）
            evaluation: buildEvaluationPayload(),
            // R8.7：跨底稿重复抽凭的审计判断留痕（keep_all / removed / none）
            duplicate_decision: duplicateDecision.value,
            duplicate_voucher_nos: crossWpDuplicates.value.map((d) => d.voucherNo),
            // 🔴 必须含 population_amount / sample_amount：后端
            // `sampling_registry_service.build_record_fields` 从
            // `coverage_stats.population_amount` 投影 `sampling_records.
            // population_total_amount`（CAS 1314 的「总体金额」记录项）。
            // 只发两个 rate 会让该列恒为 NULL —— 映射声明了但取不到值。
            coverage_stats: coverageStats.value
              ? {
                  count_rate: coverageStats.value.countCoverageRate,
                  amount_rate: coverageStats.value.amountCoverageRate,
                  population_amount: coverageStats.value.populationAmount,
                  sample_amount: coverageStats.value.sampleAmount,
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
    // 金额两项读回写入侧的同名 key（写 `population_amount` 却读不回来，就成了
    // 平台已踩过的「写一个键读另一个键」）。改造前的既有记录无这两个 key → '0'。
    return {
      populationCount: item.total_matched ?? item.totalMatched ?? 0,
      populationAmount: String(cs.population_amount ?? cs.populationAmount ?? '0'),
      sampleCount: item.filled_count ?? item.filledCount ?? 0,
      sampleAmount: String(cs.sample_amount ?? cs.sampleAmount ?? '0'),
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

  // ─── 抽样评价持久化与回读（R2）──────────────────────────────────────────

  /** 偏差笔数：实际错报 > 0 的已检查样本数（CAS 1314 的"偏差/错报笔数"记录项） */
  function countDeviations(): number {
    return sampledVouchers.value.filter(
      (v) => v.checkResult !== '' && Number(v.actualMisstatement ?? 0) > 0,
    ).length
  }

  /**
   * 构造评价载荷（R2.3 形状）。尚无推断结果时返回 null —— 「没算」与「算出来是 0」
   * 是两件事，返回全 0 会让复核人误以为已评价且无错报。
   */
  function buildEvaluationPayload(): Record<string, unknown> | null {
    const r = misstatementResult.value
    if (!r) return null
    const conclusion = samplingConclusion.value
    return {
      projected: r.projected,
      known_high_value: r.knownHighValue,
      basic_precision: r.basicPrecision,
      incremental_allowance: r.incrementalAllowance,
      upper_limit: r.upperLimit,
      tolerable_misstatement: config.value.tolerableMisstatement ?? null,
      checked_sample_count: checkedSampleCount.value,
      unchecked_sample_count: uncheckedSampleCount.value,
      deviation_count: countDeviations(),
      conclusion_code: conclusion
        ? conclusion.accepted
          ? 'acceptable'
          : 'not_acceptable'
        : 'undetermined',
      conclusion_message: conclusion?.message ?? null,
      conclusion_confirmed: conclusionConfirmed.value,
      algo_version: methodologySnapshot.value?.algo_version ?? null,
    }
  }

  /**
   * 持久化当前评价到目标批次（R2.9）。
   *
   * 失败**不静默吞**：平台已有「catch {} 吞掉 422 让功能长期空转」的踩坑记录。
   */
  async function persistEvaluation(
    extra?: Record<string, unknown>,
  ): Promise<boolean> {
    const payload = buildEvaluationPayload()
    if (!payload) return false
    if (!projectId.value || !workpaperId.value) return false
    try {
      const res = await http.post(
        `/api/projects/${projectId.value}/sampling/voucher-evaluation`,
        {
          workpaper_id: workpaperId.value,
          log_id: loadedFromBatch.value?.logId ?? null,
          evaluation: { ...payload, ...(extra ?? {}) },
        },
      )
      const data = (res.data as any)?.data ?? res.data
      const evaluatedAt = data?.evaluation?.evaluated_at ?? null
      if (data?.log_id) {
        loadedFromBatch.value = {
          logId: String(data.log_id),
          batchId: data.batch_id != null ? String(data.batch_id) : null,
          evaluatedAt,
        }
      }
      return true
    } catch (err: any) {
      // 404 = 该底稿尚无抽凭批次（先抽样未回填时评价无处可落）→ 信息级提示
      const status = err?.response?.status
      if (status === 404) {
        ElMessage.info('尚未回填抽凭批次，抽样评价将在回填时一并保存')
      } else {
        ElMessage.error('抽样评价保存失败，请重试（本次推断结果尚未落库）')
      }
      return false
    }
  }

  /**
   * 从最近一条未撤销批次回读评价（R2.7）。
   *
   * 仅在本会话尚未执行新抽样时调用；失败静默降级为空评价（回读是增强，
   * 不得阻塞打开引擎），但**绝不把失败当"无评价"写回库**。
   */
  async function loadLatestEvaluation(): Promise<boolean> {
    if (!projectId.value || !workpaperId.value) return false
    if (sampledVouchers.value.length > 0) return false // 已有当前批次样本，不覆盖
    try {
      const res = await http.get(
        `/api/projects/${projectId.value}/sampling/voucher-history`,
        { params: { wp_id: workpaperId.value } },
      )
      const list: any[] = (res.data as any)?.data ?? res.data ?? []
      const latest = list.find((r) => !r?.is_undone && r?.evaluation)
      if (!latest) return false
      const ev = latest.evaluation
      misstatementResult.value = {
        projected: String(ev.projected ?? '0.00'),
        knownHighValue: String(ev.known_high_value ?? '0.00'),
        basicPrecision: String(ev.basic_precision ?? '0.00'),
        incrementalAllowance: String(ev.incremental_allowance ?? '0.00'),
        upperLimit: String(ev.upper_limit ?? '0.00'),
      }
      const code = String(ev.conclusion_code ?? 'undetermined')
      // 抑制一次 watch：先写结论会触发"确认失效"，把下一行刚还原的确认状态打回 false
      suppressConfirmInvalidateOnce = true
      samplingConclusion.value =
        code === 'undetermined'
          ? null
          : { accepted: code === 'acceptable', message: String(ev.conclusion_message ?? '') }
      conclusionConfirmed.value = Boolean(ev.conclusion_confirmed)
      a13PushedAt.value = ev.a13_pushed_at != null ? String(ev.a13_pushed_at) : null
      loadedFromBatch.value = {
        logId: String(latest.id),
        batchId: latest.batch_id != null ? String(latest.batch_id) : null,
        evaluatedAt: ev.evaluated_at != null ? String(ev.evaluated_at) : null,
      }
      return true
    } catch {
      return false
    }
  }

  // ─── 推断错报推送至 A13（R3）─────────────────────────────────────────────

  /**
   * 构造推断错报的描述（内嵌方法/样本量/种子/批次四项标识，供 A13 溯源）。
   *
   * 高值层已知错报**不并入金额**：它是逐笔查实的事实错报，应按 factual 单独记入
   * （多数情况下审计师已在底稿逐笔推过），并入 projected 会重复计入。此处仅在描述
   * 中提示，避免遗漏。
   */
  function buildProjectedMisstatementDescription(): string {
    const r = misstatementResult.value
    const parts = [
      `抽样推断错报（${config.value.samplingMethod}）`,
      `样本量:${sampledVouchers.value.length}`,
    ]
    if (samplingInterval.value) parts.push(`抽样间隔:${samplingInterval.value}`)
    parts.push(`随机种子:${seedUsed.value ?? '-'}`)
    parts.push(`批次:${loadedFromBatch.value?.batchId ?? '-'}`)
    if (r && Number(r.upperLimit) > 0) parts.push(`错报上限:${r.upperLimit}`)
    let desc = parts.join(' ')
    const known = Number(r?.knownHighValue ?? 0)
    if (known > 0) {
      desc += `；另有高值层已知错报 ${r?.knownHighValue} 元应按事实错报单独记入`
    }
    return desc
  }

  /**
   * 推送推断错报至 A13 未更正错报汇总（R3.5~3.8）。
   *
   * 门控：结论已人工确认 且 推断错报 > 0。二者缺一不推 ——
   * 未确认的结论进错报汇总等于把未定稿的判断写进交付物。
   */
  async function pushProjectedToA13(): Promise<boolean> {
    const r = misstatementResult.value
    if (!r) {
      ElMessage.warning('尚未推断错报，请先录入样本实际错报并执行推断')
      return false
    }
    if (!conclusionConfirmed.value) {
      ElMessage.warning('请先确认抽样结论后再推送推断错报')
      return false
    }
    const projected = Number(r.projected)
    if (!(projected > 0)) {
      ElMessage.info('推断错报为 0，无需记入未更正错报汇总')
      return false
    }
    if (a13PushedAt.value) {
      try {
        await ElMessageBox.confirm(
          `本批次已于 ${a13PushedAt.value} 推送过推断错报。重复推送会在错报汇总中重复计入，确认继续？`,
          '重复推送确认',
          { type: 'warning', confirmButtonText: '仍然推送', cancelButtonText: '取消' },
        )
      } catch {
        return false
      }
    }

    eventBus.emit('a13:push-misstatement' as any, {
      // 宿主未传 wpCode 时留空 → bridge 写 source_wp_code = null（如实留空）
      wpCode: (options.wpCode ?? '').slice(0, 20),
      accountCode: config.value.accountCodes[0] ?? null,
      amount: projected,
      description: buildProjectedMisstatementDescription(),
      misstatementType: 'projected',
      timestamp: Date.now(),
    })

    const pushedAt = new Date().toISOString()
    a13PushedAt.value = pushedAt
    // 写回已推送标记（防重复计入）；持久化失败时回滚内存标记以便重试
    const ok = await persistEvaluation({ a13_pushed_at: pushedAt })
    if (!ok) a13PushedAt.value = null
    ElMessage.success('已将推断错报记入未更正错报汇总')
    return true
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
    // 抽样框版本 + 评价留痕状态（R1/R2/R3）
    datasetId,
    loadedFromBatch,
    conclusionConfirmed,
    a13PushedAt,
    // 跨底稿重复抽凭（R8）
    crossWpDuplicates,
    duplicateDecision,

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

    // 抽样评价持久化与回读（R2）+ 结论确认（R18.7）
    buildEvaluationPayload,
    persistEvaluation,
    loadLatestEvaluation,
    confirmConclusion,
    countDeviations,

    // 推断错报推送 A13（R3）
    pushProjectedToA13,
    buildProjectedMisstatementDescription,

    // 跨底稿重复抽凭确认（R8）
    confirmCrossWpDuplicates,
    buildDuplicateSummary,
    recomputeCoverageAfterRemoval,

    // 校验
    validateConfig,
    configErrors,

    // CAS 1314 合规
    checkCompliance,
  }
}

export default useVoucherSampling
