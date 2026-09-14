<script setup lang="ts">
/**
 * GtVoucherSamplingEngine — 通用抽凭引擎主组件
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 6.1
 *
 * 通用组件：通过 props 配置适配 D2-7/D4-14/D4-15/E2-7 等所有抽凭底稿
 * Requirements: 5.4, 8.3, 9.1, 9.3, 10.1, 10.3, 10.4, 10.5, 12.3
 */
import { defineAsyncComponent, toRef, computed, inject, ref, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useVoucherSampling } from '../composables/useVoucherSampling'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'
import { useSamplingPhase, type ViewMode } from '../composables/useSamplingPhase'
import { reconcilePopulation, buildSamplingMemo } from '../composables/useSamplingAlgorithms'
import {
  UNCHECKED_DISPOSITION_HINTS,
  UNCHECKED_DISPOSITION_LABELS,
  UNCHECKED_DISPOSITION_MODES,
  isUnchecked,
  type UncheckedDispositionMode,
} from '../composables/samplingUncheckedDisposition'
import {
  DEVIATION_NATURES,
  NO_SIMPLE_PROJECTION_HINT,
  deviationNatureLabels,
  isDeviation,
  type DeviationNature,
} from '../composables/samplingDeviationNature'
import { saveBlobAsFile } from '@/utils/http'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import GtReviewTrigger from '@/components/workpaper/GtReviewTrigger.vue'
import type {
  Phase,
  SamplingMethod,
  FillMode,
  SampledVoucher,
  CheckResult,
  SamplingConfig,
} from '../composables/useSamplingAlgorithms'

// ─── 异步加载子组件（后续任务实现） ──────────────────────────────────────────

const SamplingConfigDialog = defineAsyncComponent(() =>
  import('./SamplingConfigDialog.vue'),
)
const SamplingPreviewDialog = defineAsyncComponent(() =>
  import('./SamplingPreviewDialog.vue'),
)
const SamplingHistoryDrawer = defineAsyncComponent(() =>
  import('./SamplingHistoryDrawer.vue'),
)
const SamplingComparePanel = defineAsyncComponent(() =>
  import('./SamplingComparePanel.vue'),
)

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  accountCode: string
  phase: Phase
  defaultMethod?: SamplingMethod
  workpaperId: string
  projectId: string
  year: number
  /** 初始期间月份（1-12），用于期后抽凭默认 Q1 等 */
  initialPeriodRange?: number[]
  /** 合并进默认抽样配置（如底稿按测试原因预填关键词/方向/方法） */
  initialConfigPatch?: Partial<SamplingConfig>
  /** 顶部提示（如「已按测试原因预填：大额」） */
  configHint?: string
  /**
   * 父底稿当前已有的全量样本（含所有 phase）。用于生成 before_data 快照与
   * append/replace/merge 的真实前态；不传则视为空前态（向后兼容）。
   */
  existingSamples?: SampledVoucher[]
  /**
   * 宿主底稿编码（如 'D2' / 'K8'），用于推断错报推送 A13 时的 source_wp_code 溯源。
   *
   * 不传时**回落到 `WorkpaperRuntimeContext.wpCode`**（scaffold 在底稿页统一 provide）——
   * 实测 78 个宿主一个都没传该 prop，若只靠 prop 则 `source_wp_code` 恒为 null，
   * A13 错报汇总里看不出这笔推断错报出自哪张底稿。两处都取不到时才留空
   * （不用科目码或占位文本冒充底稿编码）。
   */
  wpCode?: string
  /**
   * 只读态（底稿已归档/锁定/复核通过，R10.3）。
   *
   * `true` 时禁用抽样配置、执行抽样、回填与全部行内录入 —— 已归档底稿的抽样结果
   * 不应被改动。默认 `false` 与改造前逐位一致（零回归）。
   *
   * **当前 78 个抽凭宿主均未传该 prop**（实测零字面量传参），故运行态恒为可编辑。
   * 接口先就位，宿主批量接线归 `voucher-check-shared-layer`。
   *
   * 注：`wpCode` 同样零宿主传参，但它已改为回落 `WorkpaperRuntimeContext.wpCode`
   * （见上），故不再是死 prop；`readonly` 无同款运行时来源，仍需宿主显式传。
   */
  readonly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  defaultMethod: 'random',
  initialPeriodRange: undefined,
  initialConfigPatch: undefined,
  configHint: '',
  existingSamples: undefined,
  wpCode: '',
})

// ─── Emits ────────────────────────────────────────────────────────────────────

/** 回填时附带的方法学快照（供底稿「抽样过程」自动回填） */
export interface SamplingFilledMethodology {
  samplingMethod: SamplingMethod
  samplingInterval: string | null
  sampleSize: number
  suggestedSampleSize: number | null
  tolerableMisstatement: number | null
  expectedMisstatement: number | null
  confidenceLevel: number | null
  accountCodes: string[]
  randomSeed: string | null
  /**
   * 抽凭批次号（R6.2）：由 `cutoff-fill` 响应回报，使归档件上的样本可追溯到唯一批次。
   * 无批次时为 null（如日志接口未回报），bar 侧如实不渲染该列。
   */
  batchId: string | null
  /**
   * 抽样框数据集版本（R6.2）：本次抽样所依据的 active 序时账版本 id。
   * null = 未识别到已激活账套版本 → bar 显示「未绑定账套版本」（不可据 seed 复算）。
   */
  datasetId: string | null
}

const emit = defineEmits<{
  (e: 'filled', payload: {
    samples: SampledVoucher[]
    phase: Phase
    fillMode: FillMode
    method?: SamplingMethod
    methodology?: SamplingFilledMethodology
  }): void
  (e: 'phase-changed', payload: { phase: Phase }): void
}>()

// ─── 宿主底稿编码：prop 优先，回落 WorkpaperRuntimeContext ────────────────────
// 🔴 `inject` 必须在 setup 顶层（写进函数体会静默拿不到，平台已记该踩坑）。
// 实测 78 个抽凭宿主一个都没传 `wp-code` prop → 只靠 prop 会让 A13 里
// `source_wp_code` 恒为 null（看不出推断错报出自哪张底稿）。scaffold 在底稿页
// 统一 provide 了 `wpCode`，故这里回落到它，无需改 78 个宿主。
const workpaperRuntime = inject(WorkpaperRuntimeContextKey, null)
const effectiveWpCode = computed(
  () => props.wpCode || workpaperRuntime?.wpCode?.value || '',
)

// ─── Composable: useVoucherSampling ───────────────────────────────────────────

const {
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
  selectedVouchers,
  selectedCount,
  selectedDebitTotal,
  selectedCreditTotal,
  triggerSampling,
  confirmFill,
  loadHistory,
  undoLastExtraction,
  compareVersions,
  toggleSelectAll,
  updateField,
  batchMarkChecked,
  validateConfig,
  configErrors,
  checkCompliance,
  // ─── 方法学增强状态 ───
  suggestedSampleSize,
  samplingInterval,
  misstatementResult,
  samplingConclusion,
  tolerableFromMateriality,
  uncheckedSampleCount,
  reconcileInfo,
  methodologySnapshot,
  // ─── 方法学增强操作（R15/R16/R18/R22）───
  loadTolerableMisstatement,
  computeSuggestedSampleSize,
  applySuggestedSampleSize,
  inferMisstatement,
  recordActualMisstatement,
  resample,
  // ─── 抽样框版本 + 评价留痕（R1/R2/R3）───
  datasetId,
  filledBatchId,
  loadedFromBatch,
  conclusionConfirmed,
  a13PushedAt,
  persistEvaluation,
  loadLatestEvaluation,
  confirmConclusion,
  pushProjectedToA13,
  // ─── Wave 2：未检查处置 / 偏差性质 / 完整性放行 / 分层评价 ───
  // （sampling-evaluation-and-governance-closure R3~R6）
  coverageThreshold,
  uncheckedDisposition,
  uncheckedResolution,
  setUncheckedDisposition,
  deviationAnnotations,
  deviationResolution,
  setDeviationAnnotation,
  reconcileOverrideReason,
  setReconcileBlockedReason,
  conclusionBlockedReason,
  stratifiedDetail,
  stratifiedFallback,
} = useVoucherSampling({
  projectId: toRef(props, 'projectId'),
  year: toRef(props, 'year'),
  workpaperId: toRef(props, 'workpaperId'),
  accountCode: props.accountCode,
  phase: toRef(props, 'phase'),
  defaultMethod: props.defaultMethod,
  initialPeriodRange: props.initialPeriodRange,
  initialConfigPatch: props.initialConfigPatch,
  // getter 而非静态字符串：runtime.wpCode 在本组件 setup 时未必已就位
  wpCode: () => effectiveWpCode.value,
})

// ─── Composable: useSamplingPhase ─────────────────────────────────────────────

const {
  viewMode,
  visibleSamples,
  isRowEditable,
  isFillModeRestricted,
} = useSamplingPhase({
  phase: toRef(props, 'phase'),
  samples: sampledVouchers,
})

// ─── 已填充 samples（由父组件外部管理，本组件内展示 sampledVouchers） ──────────

/** 核查结果选项 */
const checkResultOptions: { label: string; value: CheckResult }[] = [
  { label: '—', value: '' },
  { label: 'Y', value: 'Y' },
  { label: 'N', value: 'N' },
  { label: '异常', value: '异常' },
]

// ─── 行样式：预审行在年审阶段 disabled ───────────────────────────────────────

function getRowClassName({ row }: { row: SampledVoucher }): string {
  if (!canEditRow(row)) {
    return 'row-disabled'
  }
  return ''
}

// ─── 操作 ─────────────────────────────────────────────────────────────────────

/** 打开配置弹窗 */
function handleOpenConfig() {
  configDialogVisible.value = true
}

/** 打开历史侧栏 */
function handleShowHistory() {
  loadHistory()
}

/**
 * 重新打开抽样结果预览（不重抽、不换种子）。
 *
 * 用于两种情形：审计师手动关掉了预览；或被结论确认门禁挡回主体确认结论后要回来填充。
 */
function handleReopenPreview() {
  if (sampledVouchers.value.length === 0) {
    ElMessage.info('本会话尚无抽样结果，请先执行「自动抽凭」')
    return
  }
  previewVisible.value = true
}

/** 批量标记已核查：标记当前可见行 */
function handleBatchMarkChecked() {
  const indices: number[] = []
  visibleSamples.value.forEach((row) => {
    if (canEditRow(row)) {
      const idx = sampledVouchers.value.indexOf(row)
      if (idx >= 0) indices.push(idx)
    }
  })
  if (indices.length > 0) {
    batchMarkChecked(indices)
  }
}

/**
 * R18.7 结论确认门禁的**原因文案**（null = 未阻断）。
 *
 * 传给预览弹窗让「确认填充」按钮**前置 disabled + tooltip**：审计师在勾选样本时
 * 就知道还差一步，而不是勾完点下去才被一条看不见的 warning 拦住。
 * 未做错报推断（无可容忍错报 → `samplingConclusion` 为 null）的简单抽凭不受约束。
 */
const confirmBlockedReason = computed<string | null>(() => {
  // Wave 2（sampling-evaluation R3.4/R4.3/R5.1~5.3）：三处准则门控收敛在 composable 的
  // `conclusionBlockedReason` 里，此处只做合并与文案补全，不另开判定分支。
  const criteriaBlocked = conclusionBlockedReason.value
  if (criteriaBlocked) {
    return `${criteriaBlocked}（请先关闭本预览，在下方对应区域补齐后再点操作栏的「继续填充」）`
  }
  if (samplingConclusion.value && !conclusionConfirmed.value) {
    return '已生成抽样结论建议：请先关闭本预览，在「错报推断与总体结论」区点「确认采用此结论」，再点操作栏的「继续填充」回到本页填入底稿'
  }
  return null
})

/** 确认填充后 emit */
async function handleConfirmFill() {
  // 双保险：预览弹窗已按 confirmBlockedReason 前置 disabled，这里兜住其它调用路径。
  // 🔴 命中门控必须**先关闭预览弹窗** —— 它带遮罩，不关则提示指向的
  // 「错报推断与总体结论」区既看不到也点不到，那条提示就是死信。
  if (confirmBlockedReason.value) {
    previewVisible.value = false
    ElMessage.warning({
      message: confirmBlockedReason.value,
      duration: 6000,
      showClose: true,
    })
    return
  }
  // 传入父底稿真实前态，供 before_data 快照与 append/replace/merge 基于真实底稿状态
  const result = await confirmFill(props.existingSamples)
  if (result.length > 0) {
    const methodology: SamplingFilledMethodology = {
      samplingMethod: config.value.samplingMethod,
      samplingInterval: samplingInterval.value ?? null,
      sampleSize: result.length,
      suggestedSampleSize: suggestedSampleSize.value ?? config.value.suggestedSampleSize ?? null,
      tolerableMisstatement: config.value.tolerableMisstatement ?? null,
      expectedMisstatement: config.value.expectedMisstatement ?? null,
      confidenceLevel: config.value.confidenceLevel ?? null,
      accountCodes: [...(config.value.accountCodes ?? [])],
      randomSeed: seedUsed.value != null ? String(seedUsed.value) : (config.value.randomSeed != null ? String(config.value.randomSeed) : null),
      // R6.2：批次号与抽样框版本 —— 归档件上最要紧的两个可追溯字段。
      // `confirmFill` 已在其内部消费 `cutoff-fill` 响应写入 filledBatchId，
      // 故此处（confirmFill 之后）取值已就绪。
      batchId: filledBatchId.value,
      datasetId: datasetId.value,
    }
    emit('filled', {
      samples: result,
      phase: props.phase,
      fillMode: isFillModeRestricted.value ? 'append' : fillMode.value,
      method: config.value.samplingMethod,
      methodology,
    })
    // 检查合规性
    checkCompliance()
  }
}

/** 视图模式切换 */
function handleViewModeChange(val: ViewMode) {
  viewMode.value = val
}

// ─── 版本对比 ─────────────────────────────────────────────────────────────────

const comparePanelVisible = ref(false)
const compareResult = ref<{ added: string[]; removed: string[]; retained: string[] }>({
  added: [],
  removed: [],
  retained: [],
})

/** 处理历史侧栏的对比请求 */
async function handleCompare(logIdA: string, logIdB: string) {
  const result = await compareVersions(logIdA, logIdB)
  compareResult.value = {
    added: result.added.map(v => v.voucherNo),
    removed: result.removed.map(v => v.voucherNo),
    retained: result.retained.map(v => v.voucherNo),
  }
  comparePanelVisible.value = true
}

/** 行内编辑：核查结果 */
function handleCheckResultChange(row: SampledVoucher, val: CheckResult) {
  const idx = sampledVouchers.value.indexOf(row)
  if (idx >= 0) updateField(idx, 'checkResult', val)
}

/** 行内编辑：异常标记 */
function handleAbnormalChange(row: SampledVoucher, val: boolean) {
  const idx = sampledVouchers.value.indexOf(row)
  if (idx >= 0) updateField(idx, 'abnormal', val)
}

/** 行内编辑：备注 */
function handleRemarkChange(row: SampledVoucher, val: string) {
  const idx = sampledVouchers.value.indexOf(row)
  if (idx >= 0) updateField(idx, 'remark', val)
}

// ─── 覆盖率 computed ──────────────────────────────────────────────────────────

const countCoverageDisplay = computed(() => {
  if (!coverageStats.value) return '—'
  return `${coverageStats.value.countCoverageRate}%`
})

const amountCoverageDisplay = computed(() => {
  if (!coverageStats.value) return '—'
  return `${coverageStats.value.amountCoverageRate}%`
})

// ─── 方法学增强：配置弹窗回调（R15/R16）──────────────────────────────────────

/** 依据置信度/可容忍/预期错报推导建议样本量（R15） */
function handleComputeSuggested() {
  const suggested = computeSuggestedSampleSize()
  if (suggested <= 0) {
    ElMessage.warning('请先填写置信度与可容忍错报（预期错报须小于可容忍错报）')
  }
}

/** 采用系统建议样本量（R15.3） */
function handleApplySuggested() {
  applySuggestedSampleSize()
}

/** 从重要性/B15 底稿带入可容忍错报（R16） */
async function handleLoadTolerable() {
  const value = await loadTolerableMisstatement()
  if (value == null) {
    ElMessage.info('未取得重要性数据，请手工录入可容忍错报')
  } else {
    ElMessage.success('已带入实际执行重要性作为可容忍错报')
  }
}

// ─── 方法学增强：MUS 抽样间隔展示 ─────────────────────────────────────────────

const isMusMethod = computed(() => config.value.samplingMethod === 'mus')
const samplingIntervalDisplay = computed(() => samplingInterval.value ?? null)

// ─── 方法学增强：总体完整性校验区（R19）─────────────────────────────────────

/** 账面金额（序时账/明细/审定），默认取抽样总体金额，允许审计师手工录入核对 */
const bookAmountInput = ref<string>('')
/** 总体完整性可容忍差异比例（默认 5%） */
const reconcileThresholdPct = ref<number>(0.05)

const samplingPopulationAmount = computed(
  () => coverageStats.value?.populationAmount ?? '0',
)
const samplingPopulationCount = computed(
  () => coverageStats.value?.populationCount ?? 0,
)

/**
 * 有效账面金额：手工录入优先（Req2.4）；否则用后端独立账面（trial_balance 审定）；
 * 二者皆无 → null（不以序时账总体自身比对，避免自身比对假绿，Req2.2）。
 */
const effectiveBookAmount = computed<string | null>(() => {
  if (bookAmountInput.value && bookAmountInput.value !== '') {
    return bookAmountInput.value
  }
  if (reconcileInfo.value?.available && reconcileInfo.value.bookAmount != null) {
    return reconcileInfo.value.bookAmount
  }
  return null
})

/** 是否可执行总体完整性核对（有独立账面或手工录入） */
const reconcileAvailable = computed(
  () => coverageStats.value != null && effectiveBookAmount.value != null,
)

/** 总体完整性校验结果（纯函数 reconcilePopulation）；无独立账面时返回 null → UI 显示"未执行核对" */
const populationReconcile = computed(() => {
  if (!coverageStats.value || effectiveBookAmount.value == null) return null
  return reconcilePopulation(
    samplingPopulationAmount.value,
    effectiveBookAmount.value,
    reconcileThresholdPct.value,
  )
})

/**
 * R5.1/5.2：总体完整性核对未通过 → 阻断结论确认。
 *
 * 「从不完整的总体中抽样」会让整个抽样结论失效，比「结论未人工确认」更该阻断。
 * 改造前这里只显示一条 alert，`confirmBlockedReason` 完全不看它。
 *
 * 尚未执行抽样（`coverageStats` 为空）时不判定 —— 那不是"核对失败"而是"还没开始"。
 */
const reconcileIssue = computed<string | null>(() => {
  if (!coverageStats.value) return null
  if (!reconcileAvailable.value) {
    return '未执行总体完整性核对：无独立账面来源且未手工录入账面金额，无法确认样本取自完整总体'
  }
  const r = populationReconcile.value
  if (r && !r.withinThreshold) {
    return (
      `总体完整性核对不符：抽样总体 ${samplingPopulationAmount.value} 元与账面 ` +
      `${effectiveBookAmount.value} 元差异 ${r.diff} 元，超出可容忍差异 ` +
      `${(reconcileThresholdPct.value * 100).toFixed(0)}%`
    )
  }
  return null
})

// 把判定结果注入 composable 的统一门控链（composable 不去猜组件里的手工录入状态）
watch(reconcileIssue, val => setReconcileBlockedReason(val), { immediate: true })

// ─── 方法学增强：错报推断区（R18）────────────────────────────────────────────

/** 行内录入实际错报金额 → 即时重算推断 + 落库（R2.9） */
function handleActualMisstatementChange(row: SampledVoucher, val: string) {
  const idx = sampledVouchers.value.indexOf(row)
  if (idx >= 0) {
    recordActualMisstatement(idx, val)
    void persistEvaluation()
  }
}

// ─── R10：复核 section_id ─────────────────────────────────────────────────────
//
// 形如 `D2-sampling-config` / `D2-sampling-conclusion`。带底稿编码前缀是为了让复核记录
// 能定位到具体循环（平台 section_id 命名惯例），后端按同名 key 登记专属 prompt。
//
// 编码取 `effectiveWpCode`（prop 优先 → 回落 `WorkpaperRuntimeContext.wpCode`），与
// pushProjectedToA13 的 source_wp_code 同一真源。两处都取不到才退化为 `sampling-*`
// （不用科目码冒充底稿编码 —— 那会让复核记录的来源列不可信）。
//
// 改前缀不丢数据：实测全库 4 张含 `section_id` 的表里，`sampling-*` 记录数为 0
// （78 个宿主都没传 prop ⇒ 该前缀从未真正产生过带编码的 key）。

/**
 * R10.3 行可编辑判定 = phase 约束 **且** 非只读态。
 *
 * `isRowEditable`（来自 useSamplingPhase）只判「年审阶段不可改预审行」，
 * 不含底稿归档/锁定态。此处合并，模板一律走 `canEditRow` 而不再直接用 `isRowEditable`。
 */
function canEditRow(row: SampledVoucher): boolean {
  return !props.readonly && isRowEditable(row)
}

const samplingSectionPrefix = computed(() =>
  effectiveWpCode.value ? `${effectiveWpCode.value}-` : '',
)
const samplingConfigSectionId = computed(() => `${samplingSectionPrefix.value}sampling-config`)
const samplingConclusionSectionId = computed(
  () => `${samplingSectionPrefix.value}sampling-conclusion`,
)

// ─── Wave 2：未检查样本处置 / 偏差性质（R3 / R4）──────────────────────────────

/** 偏差性质中文标签（运行时取自 C 类控制测试口径，非硬编码副本） */
const natureLabels = deviationNatureLabels()

/** 处置下拉：写入并即时重算推断（视同偏差会按 100% 污染率进推断） */
function handleUncheckedModeChange(row: SampledVoucher, mode: UncheckedDispositionMode | null) {
  setUncheckedDisposition(row.voucherNo, mode)
  void persistEvaluation()
}

/** 替代程序说明 */
function handleUncheckedNoteChange(row: SampledVoucher, note: string) {
  const mode = uncheckedDisposition.value[row.voucherNo]?.mode
  if (!mode) return
  setUncheckedDisposition(row.voucherNo, mode, note)
  void persistEvaluation()
}

/** 偏差性质 */
function handleDeviationNatureChange(row: SampledVoucher, nature: DeviationNature | null) {
  setDeviationAnnotation(row.voucherNo, { nature })
  void persistEvaluation()
}

/** 偏差原因 / 影响评估 */
function handleDeviationTextChange(
  row: SampledVoucher,
  field: 'cause' | 'impact',
  value: string,
) {
  setDeviationAnnotation(row.voucherNo, { [field]: value })
  void persistEvaluation()
}

/** 手动触发错报推断（若尚未自动计算） */
function handleInferMisstatement() {
  const { conclusion } = inferMisstatement()
  // R3：未检查样本不再只是"提示未纳入推断"，而是要求逐笔选择准则处置
  const pending = uncheckedResolution.value.pending.length
  if (pending > 0) {
    ElMessage.warning(
      `有 ${pending} 笔未检查样本尚未选择处置方式：按 CAS 1314 须逐笔选择「视同偏差」或「已实施替代程序」`,
    )
  }
  if (!conclusion) {
    ElMessage.warning('请先在抽样参数中填写可容忍错报')
  }
  // R2.9：推断结果必须落库，否则关弹窗即丢（destroy-on-close）
  void persistEvaluation()
}

// R2.7：打开引擎时若本会话尚未抽样，回读最近一条未撤销批次的评价并还原推断区。
// 失败静默降级（回读是增强，不阻塞打开）；有当前批次样本时不覆盖。
onMounted(() => {
  void loadLatestEvaluation()
})

// ─── 推断错报记入 A13（R3）──────────────────────────────────────────────────

/**
 * 本会话是否执行过抽样（R2.7 回读态的判据）。
 *
 * 回读既有批次评价时 `misstatementResult` 有值而 `sampledVouchers` 为空 ——
 * 此时「重新推断」会拿 0 笔样本重算把回读结果抹掉，「记入 A13」的描述里
 * `样本量:0 随机种子:-`（`buildProjectedMisstatementDescription` 取的是会话内
 * 样本数与本次 seed）＝ 写错留痕。故这两个动作要求会话内确有样本。
 */
const hasSessionSamples = computed(() => sampledVouchers.value.length > 0)

/** 可否推送：会话内有样本 且 结论已确认 且 推断错报 > 0（R3.5） */
const canPushProjected = computed(() => {
  if (!misstatementResult.value) return false
  if (!hasSessionSamples.value) return false
  if (!conclusionConfirmed.value) return false
  return Number(misstatementResult.value.projected) > 0
})

/** 不可推送时的原因（tooltip 明示，避免"按钮灰着不知为何"） */
const pushProjectedDisabledReason = computed(() => {
  if (!misstatementResult.value) return '尚未推断错报：请先录入样本实际错报并执行推断'
  if (!hasSessionSamples.value) {
    return '当前数字读自上一批次评价，本会话未执行抽样：如需记入错报汇总请先「自动抽凭」取回样本（否则留痕里的样本量与随机种子会与实际批次不符）'
  }
  if (!conclusionConfirmed.value) return '请先确认抽样结论（未确认的结论不得进入错报汇总）'
  if (!(Number(misstatementResult.value.projected) > 0)) return '推断错报为 0，无需记入'
  return ''
})

/** 「重新推断」不可用原因（同上：0 笔样本重算会抹掉回读结果） */
const reInferDisabledReason = computed(() =>
  hasSessionSamples.value
    ? ''
    : '当前数字读自上一批次评价，本会话未执行抽样：重新推断会按 0 笔样本重算并覆盖该结果，请先「自动抽凭」',
)

async function handlePushProjected() {
  await pushProjectedToA13()
}

/** 评价来源批次标注（R2.7）：区分"上一批次的结论"与"刚算出来的结论" */
const evaluationSourceHint = computed(() => {
  const b = loadedFromBatch.value
  if (!b || !b.evaluatedAt) return ''
  const batch = b.batchId ? b.batchId.slice(0, 8) : '—'
  return `读自批次 ${batch}（${b.evaluatedAt.slice(0, 19).replace('T', ' ')} 评价）`
})

// 结论人工确认标识（R18.7：确认前不定稿）已收进 useVoucherSampling 作单一真源 ——
// 回读既有批次评价时须还原该状态，组件级 ref 随 destroy-on-close 消失。
// 「结论变化 ⇒ 确认失效」的 watch 也随之移入 composable（带一次性抑制，供回读使用）。
function handleConfirmConclusion() {
  confirmConclusion()
  // 确认动作本身即是审计判断，须落库（否则重开弹窗又要再确认一遍）
  void persistEvaluation()
  ElMessage.success('已确认抽样结论')
}

// ─── 抽样计划与结论备忘导出（R21）────────────────────────────────────────────

/** 导出 Sampling_Memo：以当前抽样批次实际数据生成备忘并下载（R21.1/21.2） */
function handleExportMemo() {
  if (!coverageStats.value && sampledVouchers.value.length === 0) {
    ElMessage.warning('尚无抽样批次，请先执行抽凭后再导出备忘')
    return
  }
  const memo = buildSamplingMemo({
    config: config.value,
    coverageStats: coverageStats.value,
    samplingInterval: samplingInterval.value,
    suggestedSampleSize: suggestedSampleSize.value,
    misstatementResult: misstatementResult.value,
    samplingConclusion: samplingConclusion.value,
    seedUsed: seedUsed.value,
    sampleCount: sampledVouchers.value.length,
    // R14.2 归档留痕：方法学算法版本（后端权威快照）+ 批次号。
    // 🔴 batchId 不能读 `methodologySnapshot.batch_id` —— 后端
    // `build_methodology_snapshot` 是纯方法学函数（抽样时批次还不存在），其快照里
    // 压根没有该键 → 恒 null。真源是 `cutoff-fill` 回报的 `filledBatchId`；
    // 重开底稿后（未重新回填）回落到评价回读拿到的 `loadedFromBatch.batchId`。
    algoVersion: methodologySnapshot.value?.algo_version ?? null,
    batchId: filledBatchId.value ?? loadedFromBatch.value?.batchId ?? null,
  })
  const stamp = new Date().toISOString().slice(0, 10)
  const account = config.value.accountCodes[0] ?? '抽样'
  const blob = new Blob([memo], { type: 'text/markdown;charset=utf-8' })
  saveBlobAsFile(blob, `抽样备忘_${account}_${stamp}.md`)
  ElMessage.success('已导出抽样计划与结论备忘')
}

// ─── 方法学增强：重抽治理（R22）──────────────────────────────────────────────

/** 重抽：必须录入原因（R22.1）→ 保留历史批次（R22.3）→ 新种子（R22.2） */
async function handleResample() {
  try {
    const { value } = await ElMessageBox.prompt(
      '重抽将保留此前的历史批次并生成新的随机种子。请填写重抽原因：',
      '重抽凭证',
      {
        confirmButtonText: '确认重抽',
        cancelButtonText: '取消',
        inputPlaceholder: '如：样本代表性不足 / 补充特定项目',
        inputValidator: (v: string) => (v && v.trim() ? true : '重抽原因不能为空'),
      },
    )
    conclusionConfirmed.value = false
    await resample(value)
  } catch {
    // 用户取消，无操作
  }
}
</script>

<template>
  <div class="gt-voucher-sampling-engine">
    <el-alert
      v-if="props.configHint"
      type="info"
      :closable="false"
      show-icon
      :title="props.configHint"
      style="margin-bottom: 12px"
    />
    <!-- ═══ 覆盖率统计卡片 ═══ -->
    <div class="coverage-stats-bar">
      <div class="stat-card">
        <span class="stat-label">笔数覆盖率</span>
        <span class="stat-value">{{ countCoverageDisplay }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">金额覆盖率</span>
        <span class="stat-value">{{ amountCoverageDisplay }}</span>
      </div>
      <div class="stat-card" v-if="coverageStats">
        <span class="stat-label">样本/总体</span>
        <span class="stat-value">{{ coverageStats.sampleCount }} / {{ coverageStats.populationCount }}</span>
      </div>
      <!-- MUS 抽样间隔展示（R17.1） -->
      <div class="stat-card" v-if="isMusMethod && samplingIntervalDisplay">
        <span class="stat-label">抽样间隔（MUS）</span>
        <span class="stat-value stat-value--interval">{{ samplingIntervalDisplay }} 元</span>
      </div>
    </div>

    <!-- ═══ 总体完整性校验区（R19）═══ -->
    <el-card
      v-if="coverageStats"
      shadow="never"
      class="reconcile-card"
    >
      <template #header>
        <div class="reconcile-header">
          <span class="reconcile-title">总体完整性校验</span>
          <span class="reconcile-sub">将抽样总体与账面（序时账/明细表/审定数）核对，确认从完整总体中抽样</span>
          <!-- R10：抽样配置与总体界定的复核入口（总体是否完整、抽样框版本是否适用） -->
          <GtReviewTrigger :section-id="samplingConfigSectionId" label="💬 复核" />
        </div>
      </template>
      <div class="reconcile-body">
        <div class="reconcile-item">
          <span class="reconcile-label">抽样总体金额</span>
          <span class="reconcile-value">{{ samplingPopulationAmount }} 元</span>
        </div>
        <div class="reconcile-item">
          <span class="reconcile-label">抽样总体笔数</span>
          <span class="reconcile-value">{{ samplingPopulationCount }} 笔</span>
        </div>
        <div class="reconcile-item">
          <span class="reconcile-label">账面金额（独立来源）</span>
          <el-input
            v-model="bookAmountInput"
            :disabled="props.readonly"
            size="small"
            :placeholder="reconcileInfo?.available ? '已取独立账面，可手工覆盖' : '无独立账面，请手工录入核对'"
            style="width: 200px"
          >
            <template #suffix>元</template>
          </el-input>
          <el-tag v-if="reconcileInfo?.available" size="small" type="success" effect="plain">
            {{ reconcileInfo?.basis && reconcileInfo.basis.startsWith('trial_balance_audited') ? '试算表审定发生额' : '独立来源' }}
          </el-tag>
        </div>
        <div class="reconcile-item">
          <span class="reconcile-label">可容忍差异</span>
          <el-select
            v-model="reconcileThresholdPct"
            :disabled="props.readonly"
            size="small"
            style="width: 100px"
          >
            <el-option :value="0.01" label="1%" />
            <el-option :value="0.03" label="3%" />
            <el-option :value="0.05" label="5%" />
            <el-option :value="0.10" label="10%" />
          </el-select>
        </div>
        <div class="reconcile-item" v-if="populationReconcile">
          <span class="reconcile-label">差异</span>
          <span class="reconcile-value">{{ populationReconcile.diff }} 元</span>
        </div>
      </div>
      <el-alert
        v-if="!reconcileAvailable"
        type="info"
        :closable="false"
        show-icon
        title="未执行总体完整性核对：无独立账面数据源，请手工录入账面金额（不以序时账总体自身比对）"
        style="margin-top: 8px"
      />
      <el-alert
        v-else-if="populationReconcile && !populationReconcile.withinThreshold"
        type="warning"
        :closable="false"
        show-icon
        title="总体可能不完整，抽样结论受限：抽样总体与独立账面差异超过可容忍阈值，请核实总体来源"
        style="margin-top: 8px"
      />

      <!-- R5.3：核对未通过时的理由放行入口。
           硬阻断会让合法例外（确无独立明细表可核对）无法推进；填写不少于 10 字的说明后
           可继续确认结论，理由与操作人、时间随评价留痕并进入归档件。 -->
      <div v-if="reconcileIssue" class="reconcile-override">
        <div class="reconcile-override-head">
          <el-tag type="danger" size="small" effect="dark">结论确认已阻断</el-tag>
          <span class="reconcile-override-text">{{ reconcileIssue }}</span>
        </div>
        <el-input
          v-model="reconcileOverrideReason"
          :disabled="props.readonly"
          type="textarea"
          :autosize="{ minRows: 2 }"
          maxlength="500"
          show-word-limit
          placeholder="如确有正当理由（例如该科目无独立明细表、已与总账另行核对一致），请说明不少于 10 字后继续；该说明将随抽样评价留痕"
        />
        <div class="reconcile-override-foot">
          <el-tag
            :type="reconcileOverrideReason.trim().length >= 10 ? 'success' : 'info'"
            size="small"
            effect="plain"
          >
            {{
              reconcileOverrideReason.trim().length >= 10
                ? '已填写放行理由，可继续确认结论'
                : `还需 ${10 - reconcileOverrideReason.trim().length} 字`
            }}
          </el-tag>
        </div>
      </div>
    </el-card>

    <!-- ═══ 视图模式切换 ═══ -->
    <div class="view-mode-bar">
      <el-radio-group
        :model-value="viewMode"
        size="small"
        @change="handleViewModeChange"
      >
        <el-radio-button value="all">全量</el-radio-button>
        <el-radio-button value="preliminary">仅预审</el-radio-button>
        <el-radio-button value="final">仅年审</el-radio-button>
      </el-radio-group>
    </div>

    <!-- ═══ CAS 1314 合规警告区 ═══ -->
    <div v-if="complianceWarnings.length > 0" class="compliance-warnings">
      <el-alert
        v-for="(warn, idx) in complianceWarnings"
        :key="idx"
        :title="warn.message"
        :type="warn.level === 'warning' ? 'warning' : 'info'"
        :closable="false"
        show-icon
        class="compliance-alert"
      />
    </div>

    <!-- ═══ 操作栏 ═══ -->
    <div class="action-bar">
      <el-button type="primary" size="small" :loading="loading" @click="handleOpenConfig">
        自动抽凭
      </el-button>
      <el-button size="small" @click="handleShowHistory">
        抽凭历史
      </el-button>
      <el-button size="small" @click="handleBatchMarkChecked">
        批量标记已核查
      </el-button>
      <!--
        重开预览：本会话已抽出样本但预览被关闭时提供回填通路。
        🔴 没有这个入口，用户一旦关掉预览（或被结论确认门禁挡回来）就只能「重抽」，
        而重抽会换随机种子与样本集合、打断本批次留痕（2026-08-04 实测）。
      -->
      <el-button
        v-if="sampledVouchers.length > 0 && !previewVisible"
        size="small"
        type="success"
        plain
        data-testid="reopen-sampling-preview"
        @click="handleReopenPreview"
      >
        继续填充（{{ sampledVouchers.length }} 笔待回填）
      </el-button>
      <el-button
        size="small"
        type="warning"
        plain
        :disabled="sampledVouchers.length === 0"
        @click="handleResample"
      >
        重抽
      </el-button>
      <el-button
        size="small"
        plain
        :disabled="!coverageStats && sampledVouchers.length === 0"
        @click="handleExportMemo"
      >
        导出抽样备忘
      </el-button>
    </div>

    <!-- ═══ 主体表格 ═══ -->
    <el-table
      :data="visibleSamples"
      :row-class-name="getRowClassName"
      border
      stripe
      size="small"
      class="sampling-table"
      empty-text='暂无抽凭数据，请点击「自动抽凭」开始'
    >
      <el-table-column prop="voucherNo" label="凭证号" min-width="100" show-overflow-tooltip />
      <el-table-column prop="voucherDate" label="日期" min-width="100" show-overflow-tooltip />
      <el-table-column prop="summary" label="摘要" min-width="160" show-overflow-tooltip />
      <el-table-column label="借方" min-width="110" align="right">
        <template #default="{ row }">
          <GtAmountCell :value="row.debitAmount" />
        </template>
      </el-table-column>
      <el-table-column label="贷方" min-width="110" align="right">
        <template #default="{ row }">
          <GtAmountCell :value="row.creditAmount" />
        </template>
      </el-table-column>
      <el-table-column prop="accountCode" label="科目" min-width="90" show-overflow-tooltip />
      <el-table-column prop="voucherType" label="凭证类型" min-width="80" align="center" />
      <!-- 高值必选标识（MUS，R17.4） -->
      <el-table-column label="高值" min-width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isHighValue" size="small" type="danger" effect="plain">
            高值必选
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <!-- 核查结果（inline select） -->
      <el-table-column label="核查结果" min-width="100" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="row.checkResult"
            size="small"
            :disabled="!canEditRow(row)"
            placeholder="—"
            @change="(val: CheckResult) => handleCheckResultChange(row, val)"
          >
            <el-option
              v-for="opt in checkResultOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </template>
      </el-table-column>
      <!-- 异常（inline switch） -->
      <el-table-column label="异常" min-width="70" align="center">
        <template #default="{ row }">
          <el-switch
            :model-value="row.abnormal"
            size="small"
            :disabled="!canEditRow(row)"
            @change="(val: boolean) => handleAbnormalChange(row, val)"
          />
        </template>
      </el-table-column>
      <!-- 实际错报（inline input，R18.1） -->
      <el-table-column label="实际错报(元)" min-width="120" align="right">
        <template #default="{ row }">
          <el-input
            :model-value="row.actualMisstatement"
            size="small"
            :disabled="!canEditRow(row)"
            placeholder="0"
            @change="(val: string) => handleActualMisstatementChange(row, val)"
          />
        </template>
      </el-table-column>
      <!-- R3：未检查样本处置（CAS 1314 二选一）。只对 checkResult 为空的行显示 —— 
           已检查样本没有"无法实施程序"这回事。 -->
      <el-table-column label="未检查处置" min-width="220">
        <template #default="{ row }">
          <div v-if="isUnchecked(row)" class="disposition-cell">
            <el-select
              :model-value="uncheckedDisposition[row.voucherNo]?.mode ?? null"
              size="small"
              clearable
              placeholder="须选择处置方式"
              :disabled="!canEditRow(row)"
              style="width: 100%"
              @change="(val: UncheckedDispositionMode | null) => handleUncheckedModeChange(row, val)"
            >
              <el-option
                v-for="mode in UNCHECKED_DISPOSITION_MODES"
                :key="mode"
                :value="mode"
                :label="UNCHECKED_DISPOSITION_LABELS[mode]"
              >
                <el-tooltip :content="UNCHECKED_DISPOSITION_HINTS[mode]" placement="right">
                  <span>{{ UNCHECKED_DISPOSITION_LABELS[mode] }}</span>
                </el-tooltip>
              </el-option>
            </el-select>
            <el-input
              v-if="uncheckedDisposition[row.voucherNo]?.mode === 'alternative_performed'"
              :model-value="uncheckedDisposition[row.voucherNo]?.note ?? ''"
              size="small"
              :disabled="!canEditRow(row)"
              placeholder="替代程序说明（必填）"
              @change="(val: string) => handleUncheckedNoteChange(row, val)"
            />
          </div>
          <span v-else class="strata-muted">—</span>
        </template>
      </el-table-column>

      <!-- R4：偏差性质与原因。只对偏差行（N / 异常）显示。 -->
      <el-table-column label="偏差性质与原因" min-width="260">
        <template #default="{ row }">
          <div v-if="isDeviation(row)" class="disposition-cell">
            <el-select
              :model-value="deviationAnnotations[row.voucherNo]?.nature ?? null"
              size="small"
              clearable
              placeholder="须标注偏差性质"
              :disabled="!canEditRow(row)"
              style="width: 100%"
              @change="(val: DeviationNature | null) => handleDeviationNatureChange(row, val)"
            >
              <el-option
                v-for="nature in DEVIATION_NATURES"
                :key="nature"
                :value="nature"
                :label="natureLabels[nature]"
              />
            </el-select>
            <template
              v-if="
                deviationAnnotations[row.voucherNo]?.nature === 'systematic' ||
                deviationAnnotations[row.voucherNo]?.nature === 'human'
              "
            >
              <el-input
                :model-value="deviationAnnotations[row.voucherNo]?.cause ?? ''"
                size="small"
                :disabled="!canEditRow(row)"
                placeholder="偏差原因（必填）"
                @change="(val: string) => handleDeviationTextChange(row, 'cause', val)"
              />
              <el-input
                :model-value="deviationAnnotations[row.voucherNo]?.impact ?? ''"
                size="small"
                :disabled="!canEditRow(row)"
                placeholder="对审计程序目的的影响评估（必填）"
                @change="(val: string) => handleDeviationTextChange(row, 'impact', val)"
              />
            </template>
          </div>
          <span v-else class="strata-muted">—</span>
        </template>
      </el-table-column>

      <!-- 备注（inline input） -->
      <el-table-column label="备注" min-width="140">
        <template #default="{ row }">
          <el-input
            :model-value="row.remark"
            size="small"
            :disabled="!canEditRow(row)"
            placeholder="备注"
            @change="(val: string) => handleRemarkChange(row, val)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 错报推断与总体结论区（R18）═══
         🔴 渲染门控必须含 `misstatementResult`：R2.7 回读既有批次评价时会话内没有
         样本，只按 `sampledVouchers.length > 0` 会把回读结果整块藏起来 ——
         「打开底稿就能看到上一批次的推断错报与结论」这条用户故事因此不成立
         （状态还原了但用户看不见 = dead output）。 -->
    <el-card
      v-if="sampledVouchers.length > 0 || misstatementResult"
      shadow="never"
      class="misstatement-card"
    >
      <template #header>
        <div class="misstatement-header">
          <span class="misstatement-title">错报推断与总体结论</span>
          <el-tag v-if="evaluationSourceHint" size="small" type="info">
            {{ evaluationSourceHint }}
          </el-tag>
          <el-tooltip
            :disabled="!reInferDisabledReason"
            :content="reInferDisabledReason"
            placement="top"
          >
            <span>
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="props.readonly || !hasSessionSamples"
                @click="handleInferMisstatement"
              >
                重新推断
              </el-button>
            </span>
          </el-tooltip>
          <!-- R10：结论区复核入口。抽样是审计判断最集中的环节（总体界定、样本量、
               种子、未检查样本处置、结论采纳），改造前引擎零 GtReviewTrigger。 -->
          <GtReviewTrigger :section-id="samplingConclusionSectionId" label="💬 复核" />
        </div>
      </template>

      <div v-if="misstatementResult" class="misstatement-body">
        <div class="misstatement-grid">
          <div class="ms-item">
            <span class="ms-label">推断错报</span>
            <span class="ms-value">{{ misstatementResult.projected }} 元</span>
          </div>
          <div class="ms-item">
            <span class="ms-label">高值层已知错报</span>
            <span class="ms-value">{{ misstatementResult.knownHighValue }} 元</span>
          </div>
          <div class="ms-item">
            <span class="ms-label">基本准备</span>
            <span class="ms-value">{{ misstatementResult.basicPrecision }} 元</span>
          </div>
          <div class="ms-item">
            <span class="ms-label">增量准备</span>
            <span class="ms-value">{{ misstatementResult.incrementalAllowance }} 元</span>
          </div>
          <div class="ms-item ms-item--emphasis">
            <span class="ms-label">错报上限 (UML)</span>
            <span class="ms-value ms-value--uml">{{ misstatementResult.upperLimit }} 元</span>
          </div>
        </div>

        <!-- ═══ 分层层内评价明细（R6.4/6.7）═══
             各层抽样比例不同，合并做比率估计会把抽得密的层的错报率摊到整个总体。
             新旧口径并列展示，差异非零时提示复核。 -->
        <div v-if="stratifiedDetail" class="strata-panel">
          <div class="strata-head">
            <span class="strata-title">分层层内评价</span>
            <el-tag size="small" type="warning" effect="plain">
              层内外推 {{ stratifiedDetail.projected }} 元
            </el-tag>
            <el-tag size="small" type="info" effect="plain">
              合并口径 {{ stratifiedDetail.legacy.projected }} 元
            </el-tag>
            <el-tag
              v-if="stratifiedDetail.projected !== stratifiedDetail.legacy.projected"
              size="small"
              type="danger"
              effect="plain"
            >
              两口径存在差异，请复核推断过程
            </el-tag>
          </div>
          <el-alert
            v-if="stratifiedDetail.unclassifiedCount > 0"
            type="warning"
            :closable="false"
            show-icon
            :title="`有 ${stratifiedDetail.unclassifiedCount} 笔样本金额不落入任何声明的层区间，已单独归入「未归层」并单独外推，请核实分层配置是否覆盖全部总体`"
            style="margin-bottom: 8px"
          />
          <el-alert
            v-if="stratifiedDetail.unsampledStrataCount > 0"
            type="warning"
            :closable="false"
            show-icon
            :title="`有 ${stratifiedDetail.unsampledStrataCount} 个层有总体金额但未抽到样本，该层不参与外推（属覆盖缺口，请考虑补充抽样）`"
            style="margin-bottom: 8px"
          />
          <el-alert
            v-if="stratifiedFallback"
            type="error"
            :closable="false"
            show-icon
            title="层内评价计算异常，已回退合并口径（数字按合并比率估计，请报告技术支持）"
            style="margin-bottom: 8px"
          />
          <el-table :data="stratifiedDetail.strataDetail" size="small" border>
            <el-table-column prop="label" label="层次" width="90" />
            <el-table-column label="金额区间" min-width="150">
              <template #default="{ row }">
                <span v-if="row.index === -1" class="strata-muted">未落入声明区间</span>
                <span v-else>{{ row.lowerBound }} ~ {{ row.upperBound }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="populationAmount" label="层总体金额" align="right" min-width="130" />
            <el-table-column prop="sampleCount" label="样本笔数" align="right" width="90" />
            <el-table-column prop="sampleAmount" label="样本金额" align="right" min-width="120" />
            <el-table-column prop="sampleError" label="样本错报" align="right" min-width="110" />
            <el-table-column prop="projected" label="该层外推额" align="right" min-width="120" />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag v-if="row.unsampled" size="small" type="danger" effect="plain">
                  未抽样
                </el-tag>
                <el-tag v-else-if="row.index === -1" size="small" type="warning" effect="plain">
                  未归层
                </el-tag>
                <span v-else class="strata-muted">—</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 结论确认门控提示（R3.4/R4.3/R5.1~5.3 统一出口） -->
        <el-alert
          v-if="conclusionBlockedReason"
          type="error"
          :closable="false"
          show-icon
          :title="conclusionBlockedReason"
          class="conclusion-alert"
        />

        <!-- 存在系统性或人为偏差时的准则提示（R4.2） -->
        <el-alert
          v-if="deviationResolution.hasNonProjectable"
          type="warning"
          :closable="false"
          show-icon
          :title="NO_SIMPLE_PROJECTION_HINT"
          class="conclusion-alert"
        />

        <!-- 结论建议（人工确认前不定稿，R18.7） -->
        <el-alert
          v-if="samplingConclusion"
          :type="samplingConclusion.accepted ? 'success' : 'error'"
          :closable="false"
          show-icon
          :title="samplingConclusion.message"
          class="conclusion-alert"
        />
        <div v-if="samplingConclusion" class="conclusion-confirm-bar">
          <el-tag v-if="conclusionConfirmed" type="success" effect="dark">已人工确认</el-tag>
          <!-- 门控一律「前置 disabled + tooltip」：命中时按钮不可点且鼠标悬停即知原因，
               而不是点下去才弹一条可能被遮挡的提示（平台已登记的死信铁律）。 -->
          <el-tooltip
            v-else
            :disabled="!conclusionBlockedReason"
            :content="conclusionBlockedReason ?? ''"
            placement="top"
          >
            <span>
              <el-button
                size="small"
                type="primary"
                :disabled="props.readonly || !!conclusionBlockedReason"
                @click="handleConfirmConclusion"
              >
                确认采用此结论
              </el-button>
            </span>
          </el-tooltip>
          <span class="conclusion-hint">结论建议由系统计算，需经审计师确认后方可作为最终结论</span>
        </div>

        <!-- 推断错报记入未更正错报汇总（R3.5~3.8）：CAS 1251 要求推断错报与
             事实错报一并汇总后与重要性比较，这是形成审计意见的必要步骤 -->
        <div class="a13-push-bar">
          <el-tooltip
            :disabled="canPushProjected"
            :content="pushProjectedDisabledReason"
            placement="top"
          >
            <span>
              <el-button
                size="small"
                type="danger"
                plain
                :disabled="!canPushProjected"
                @click="handlePushProjected"
              >
                记入未更正错报汇总（推断错报）
              </el-button>
            </span>
          </el-tooltip>
          <el-tag v-if="a13PushedAt" size="small" type="info">
            已于 {{ a13PushedAt.slice(0, 19).replace('T', ' ') }} 记入
          </el-tag>
          <span class="conclusion-hint">
            仅推送推断错报（{{ misstatementResult.projected }} 元）；高值层已知错报按事实错报单独记入
          </span>
        </div>
        <el-alert
          v-if="!samplingConclusion"
          type="info"
          :closable="false"
          show-icon
          title="请在抽样参数中填写可容忍错报，以便得出总体结论建议"
          class="conclusion-alert"
        />
      </div>
      <el-empty v-else description="录入样本实际错报后自动推断总体错报与结论" :image-size="60" />
    </el-card>

    <!-- ═══ 嵌入子组件（异步加载） ═══ -->
    <SamplingConfigDialog
      v-if="configDialogVisible"
      v-model:visible="configDialogVisible"
      :config="config"
      :config-errors="configErrors"
      :loading="loading"
      :suggested-sample-size="suggestedSampleSize"
      :tolerable-from-materiality="tolerableFromMateriality"
      @execute="triggerSampling"
      @compute-suggested="handleComputeSuggested"
      @apply-suggested="handleApplySuggested"
      @load-tolerable="handleLoadTolerable"
    />

    <SamplingPreviewDialog
      v-if="previewVisible"
      v-model:visible="previewVisible"
      :vouchers="sampledVouchers"
      :coverage-stats="coverageStats"
      :fill-mode="fillMode"
      :is-fill-mode-restricted="isFillModeRestricted"
      :selected-count="selectedCount"
      :selected-debit-total="selectedDebitTotal"
      :selected-credit-total="selectedCreditTotal"
      :phase="props.phase"
      :confirm-blocked-reason="confirmBlockedReason"
      @update:fill-mode="(v: FillMode) => fillMode = v"
      @confirm="handleConfirmFill"
      @toggle-select-all="toggleSelectAll"
    />

    <SamplingHistoryDrawer
      v-if="historyVisible"
      v-model:visible="historyVisible"
      :history-list="historyList"
      @undo="undoLastExtraction"
      @compare="handleCompare"
    />

    <SamplingComparePanel
      v-if="comparePanelVisible"
      v-model:visible="comparePanelVisible"
      :compare-result="compareResult"
    />
  </div>
</template>

<style scoped>
.gt-voucher-sampling-engine {
  padding: 12px 0;
}

/* ── 覆盖率统计卡片 ── */
.coverage-stats-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 6px;
  padding: 10px 20px;
  min-width: 120px;
}

.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
  margin-bottom: 4px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-color-primary, #409eff);
}

.stat-value--interval {
  color: var(--el-color-warning, #e6a23c);
  font-size: 15px;
}

/* ── Wave 2：完整性放行 / 分层明细 / 逐行处置 ── */
.reconcile-override {
  margin-top: 10px;
  padding: 10px 12px;
  border-left: 3px solid var(--el-color-danger);
  background: var(--el-color-danger-light-9);
  border-radius: 4px;
}

.reconcile-override-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.reconcile-override-text {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.reconcile-override-foot {
  margin-top: 6px;
}

.strata-panel {
  margin: 12px 0;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}

.strata-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.strata-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.strata-muted {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.disposition-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* ── 总体完整性校验区 ── */
.reconcile-card {
  margin-bottom: 12px;
}

.reconcile-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.reconcile-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.reconcile-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.reconcile-body {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px 24px;
}

.reconcile-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
}

.reconcile-label {
  color: var(--el-text-color-secondary);
}

.reconcile-value {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

/* ── 错报推断区 ── */
.misstatement-card {
  margin-top: 12px;
}

/* 推断错报记入 A13 操作条 */
.a13-push-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.misstatement-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.misstatement-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.misstatement-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  margin-bottom: 12px;
}

.ms-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 120px;
}

.ms-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.ms-value {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.ms-item--emphasis .ms-value--uml {
  color: var(--el-color-danger, #f56c6c);
  font-size: 17px;
}

.conclusion-alert {
  margin-top: 8px;
}

.conclusion-confirm-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}

.conclusion-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

/* ── 视图模式切换 ── */
.view-mode-bar {
  margin-bottom: 12px;
}

/* ── CAS 1314 合规警告 ── */
.compliance-warnings {
  margin-bottom: 12px;
}

.compliance-alert {
  margin-bottom: 6px;
}

.compliance-alert:last-child {
  margin-bottom: 0;
}

/* ── 操作栏 ── */
.action-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

/* ── 主体表格 ── */
.sampling-table {
  font-size: var(--wp-font-size, 13px);
}

.sampling-table :deep(.el-table__row) {
  font-size: var(--wp-font-size, 13px);
}

/* 预审行在年审阶段 disabled 样式 */
.sampling-table :deep(.row-disabled) {
  background-color: var(--el-fill-color-lighter, #fafafa) !important;
  opacity: 0.65;
  pointer-events: none;
}

.sampling-table :deep(.row-disabled) .el-input,
.sampling-table :deep(.row-disabled) .el-select,
.sampling-table :deep(.row-disabled) .el-switch {
  cursor: not-allowed;
}

/* inline 编辑控件紧凑 */
.sampling-table :deep(.el-select) {
  width: 80px;
}

.sampling-table :deep(.el-input) {
  width: 100%;
}
</style>
