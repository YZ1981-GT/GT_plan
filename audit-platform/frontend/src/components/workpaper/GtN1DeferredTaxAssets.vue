<template>
  <div class="n1-deferred-tax-assets">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- ─── 工具栏：双模式（六大集成标准，版本历史由 Runtime Boundary 统一 GtWpToolbar 提供） ─── -->
      <div v-if="isSwitchableSheet" class="n1-toolbar">
        <!-- 🔴 铁律：:model-value + @change，禁用 v-model（v-model 会先改值使 switchMode 守卫短路） -->
        <el-segmented
          :model-value="dualMode.mode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="(val: any) => dualMode.switchMode(val, props.sheetName || '')"
        />
        <el-tag v-if="dualMode.fetchingConfig.value" size="small" type="info">正在拉取 OnlyOffice 文档…</el-tag>
        <el-tag v-else-if="!dualMode.isOOHealthy.value" size="small" type="warning">OO不可用（仅结构化视图）</el-tag>
        <el-tag v-else-if="dualMode.ooConfigReady.value" size="small" type="success">OnlyOffice 拉取成功</el-tag>
        <el-tag v-else size="small" type="success" effect="plain">OnlyOffice 就绪</el-tag>
      </div>

      <!-- 双模式：HTML sheet 切到 OnlyOffice（目录页不参与，否则切过 OO 后目录被顶掉且无处切回） -->
      <GtOnlyOfficeSheet
        v-if="isSwitchableSheet && dualMode.isOnlyOffice.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
        @fallback="dualMode.onOoLoadFailed"
      />

      <!-- N1 底稿目录 -->
      <N1TabIndex
        v-else-if="currentSheet === 'index'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :year="effectiveYear"
        @navigate="handleNavigate"
      />
      <!-- 程序表 N1A（复用 GtAProgramConsole） -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'procedure'"
        :wp-id="props.wpId"
        sheet-name="N1A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- N1-1 审定表（资产类借方！期末=期初+借-贷） -->
      <N1TabAdjudication
        v-else-if="currentSheet === 'N1-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :year="effectiveYear"
        @navigate="handleNavigate"
      />
      <!-- 附注披露信息（上市公司） -->
      <N1TabDisclosureListed
        v-else-if="currentSheet === 'disclosure-listed'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :year="effectiveYear"
        @navigate="handleNavigate"
      />
      <!-- 附注披露信息（国企） -->
      <N1TabDisclosureSoe
        v-else-if="currentSheet === 'disclosure-soe'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :year="effectiveYear"
        @navigate="handleNavigate"
      />
      <!-- N1-2 明细表（14列14公式，按暂时性差异项目明细） -->
      <N1TabDetail
        v-else-if="currentSheet === 'N1-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :year="effectiveYear"
        @navigate="handleNavigate"
      />
      <!-- N1-3 调整分录汇总 -->
      <N1TabAdjustment
        v-else-if="currentSheet === 'N1-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :year="effectiveYear"
        @navigate="handleNavigate"
      />
      <!-- N1-4 递延所得税资产（负债）测算表（63×15，21公式，核心引擎） -->
      <N1TabCalcTable
        v-else-if="currentSheet === 'N1-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :year="effectiveYear"
        @navigate="handleNavigate"
      />
      <!-- N1-5 可用以后年度税前利润弥补的亏损检查表 -->
      <N1TabLossCheck
        v-else-if="currentSheet === 'N1-5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :year="effectiveYear"
        :view-mode="dualMode.isMatrix.value ? 'matrix' : 'structured'"
        @navigate="handleNavigate"
        @exit-matrix="dualMode.switchMode('structured')"
      />
      <!-- OnlyOffice fallback: 未迁移 sheet / 参考辅助 -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :sheet-name="props.sheetName"
        style="height: 100%; min-height: 600px"
      />
    </template>

  </div>
</template>

<script setup lang="ts">
/**
 * GtN1DeferredTaxAssets.vue — N1 递延所得税资产底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取编码（N1/N1A/N1-1~N1-5），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：1811 递延所得税资产（**借方/资产类！**）
 * 核心铁律：期末=期初+借方-贷方（资产类借方科目）
 * 特殊功能：①资产类取数（期末余额！非发生额） ②递延所得税=可抵扣暂时性差异×税率
 *           ③可弥补亏损确认（谨慎性：min(未弥补, 预计未来应纳税所得额)×税率）
 *           ④与N3递延所得税负债对应（同源暂时性差异分列） ⑤递延税费用变动→N5核对
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated(1811) / 'deferred-tax:asset-updated'
 * - 订阅: 'disclosure:refresh' / 'adjustment:created'
 * - 跨底稿联动: TB回写(1811期末余额) + N3对应 + N5递延税费用核对
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, inject, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import { useN1DualMode } from './composables/useN1DualMode'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const N1TabIndex = defineAsyncComponent(() => import('./n1/core/N1TabIndex.vue'))
const N1TabAdjudication = defineAsyncComponent(() => import('./n1/core/N1TabAdjudication.vue'))
const N1TabDetail = defineAsyncComponent(() => import('./n1/core/N1TabDetail.vue'))
const N1TabAdjustment = defineAsyncComponent(() => import('./n1/core/N1TabAdjustment.vue'))
const N1TabDisclosureListed = defineAsyncComponent(() => import('./n1/core/N1TabDisclosureListed.vue'))
const N1TabDisclosureSoe = defineAsyncComponent(() => import('./n1/core/N1TabDisclosureSoe.vue'))

// Calc
const N1TabCalcTable = defineAsyncComponent(() => import('./n1/calc/N1TabCalcTable.vue'))
const N1TabLossCheck = defineAsyncComponent(() => import('./n1/calc/N1TabLossCheck.vue'))

// Shared
const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

const parentEmit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

/**
 * N1TabIndex 目录行点击→通知外层 GtWpRenderer 切换 sheetName。
 * 铁律：GtWpRenderer 监听 @navigate-sheet，主入口必须 emit 'navigate-sheet'（非 'navigate'）。
 */
function handleNavigate(sheetName: string) {
  parentEmit('navigate-sheet', sheetName)
}

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

/**
 * 审计年度：props.year 优先，回退 htmlData.project_context.audit_year。
 * 铁律：亏损弥补期限届满/剩余年限判断依赖审计年度，不能用 new Date() 当前年
 * （2026 年做 2025 年报会整体偏一年）。
 */
const effectiveYear = computed<number | undefined>(() => {
  if (props.year) return props.year
  const raw = (props.htmlData as any)?.project_context?.audit_year
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
})

// ─── sheetName → 子组件分发 ──────────────────────────────────────────────────

/**
 * 当前激活的 sheet（由外层 GtWpRenderer 通过 sheetName prop 控制）。
 * GtWpRenderer 传入完整 sheet_name（如"递延所得税资产审定表N1-1"），
 * 正则提取编码来匹配子组件。
 *
 * 映射关系：
 *   底稿目录                                           → index              → N1TabIndex
 *   递延所得税资产审计程序表的N1A                     → procedure          → GtAProgramConsole (复用)
 *   递延所得税资产审定表N1-1                          → N1-1               → N1TabAdjudication（资产类借方！）
 *   附注披露信息（上市公司）                          → disclosure-listed  → N1TabDisclosureListed
 *   附注披露信息（国企）                              → disclosure-soe     → N1TabDisclosureSoe
 *   递延所得税资产明细表N1-2                          → N1-2               → N1TabDetail
 *   调整分录汇总N1-3                                  → N1-3               → N1TabAdjustment
 *   递延所得税资产（负债）测算表N1-4                  → N1-4               → N1TabCalcTable（核心引擎！）
 *   可用以后年度税前利润弥补的亏损检查表的N1-5       → N1-5               → N1TabLossCheck
 *   GT_Custom                                          → skip (hidden)
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // GT_Custom → skip (hidden config sheet)
  if (name === 'GT_Custom') return 'skip'

  // 提取 N1-N 编码（N1-1 ~ N1-5）
  const codeMatch = name.match(/N1-[1-5]/)
  if (codeMatch) return codeMatch[0]

  // 程序表 N1A
  if (name.match(/N1A/) || name.includes('程序表')) return 'procedure'

  // 附注特殊匹配
  if (name.includes('上市公司')) return 'disclosure-listed'
  if (name.includes('国企') || name.includes('国有企业')) return 'disclosure-soe'

  // 底稿目录（默认）
  if (name.includes('底稿目录') || name === 'N1' || name === '') return 'index'

  // 未匹配 → OO fallback
  return name
})

// ─── Runtime Boundary（GtWpRenderer 统一提供 版本/复核/AI/displayPrefs + 挂真实 Host） ───
// 复核对话与版本历史由 Runtime Boundary 统一 provide('openReviewDialog') + version 承载，
// 本主入口不再本地 new GtReviewDialog / useWorkpaperVersionToolbar（避免重复 provider/Host）。
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const wpIdRef = computed(() => props.wpId)

// ─── provide scheduleAutoSnapshot → 子组件保存后触发自动快照（版本链来自 Runtime Boundary） ─────
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())

// ─── 复核圆点（GtReviewDot 依赖 getThreadDot/getRowDot；Runtime Boundary 只 provide openReviewDialog） ───
const reviewThreads = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', reviewThreads.getThreadDot)
provide('getRowDot', reviewThreads.getRowDot)

// ─── 双模式 useN1DualMode（结构化/矩阵/OnlyOffice）─────────────────────────

/**
 * 矩阵视图（行 × 判断项核对矩阵，平台 J1-8/D2-7 语义）在 N1 中只有 N1-5 亏损检查表符合：
 * 弥补期限届满 / 预计应纳税所得额是否充足 / 确认依据是否已填。其余 sheet 是纯数值表不提供该选项。
 */
const supportsMatrix = computed(() => currentSheet.value === 'N1-5')

const dualMode = useN1DualMode({ wpId: wpIdRef, supportsMatrix })

/** N1-1~N1-5 + 附注 为 HTML 专属组件渲染的 sheet；N1A/GT_Custom 走 OO */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return /^N1-\d+$/.test(s) || s === 'index' || s === 'disclosure-listed' || s === 'disclosure-soe'
})

/**
 * 支持双模式切换的 sheet = HTML sheet 且非底稿目录。
 * 🔴 目录页必须排除：mode 是入口级共享状态，若目录也走 OO 分支，
 * 从 N1-1 切到在线编辑后点「底稿目录」会渲染 OnlyOffice（且该页无工具栏可切回）。
 */
const isSwitchableSheet = computed(() => isHtmlSheet.value && currentSheet.value !== 'index')

// ─── 监听 n1:save-items → 保存后自动快照 ────────────────────────────────────

function handleN1SaveItems(_e: Event): void {
  runtime?.version.scheduleAutoSnapshot()
}

// ─── selfLoad ────────────────────────────────────────────────────────────────

async function selfLoad() {
  if (props.htmlData) {
    // 从 props 提供的数据初始化
    isLoading.value = false
    return
  }

  // 当 htmlData 为空时（bundle 内嵌场景），自行加载 render-config
  try {
    await http.get(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
  } catch (err) {
    console.warn('[GtN1DeferredTaxAssets] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── provide reloadWorkpaperData → 子组件可主动刷新数据 ─────────────────────

provide('reloadWorkpaperData', selfLoad)

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  window.addEventListener('n1:save-items', handleN1SaveItems)
  selfLoad()

  // ─── EventBus 订阅 'disclosure:refresh' → 刷新数据（Task 6.1） ─────────
  eventBus.on('disclosure:refresh', onDisclosureRefresh)
})

onBeforeUnmount(() => {
  window.removeEventListener('n1:save-items', handleN1SaveItems)
  eventBus.off('disclosure:refresh', onDisclosureRefresh)
})

// ─── EventBus handler: disclosure:refresh → 重新加载数据 ─────────────────────

function onDisclosureRefresh(): void {
  selfLoad()
}
</script>

<style scoped>
.n1-deferred-tax-assets {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.n1-toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
