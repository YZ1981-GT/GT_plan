<template>
  <div class="l4-bonds-payable">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- L4 主sheet 底稿目录 -->
      <L4TabIndex
        v-if="currentSheet === 'L4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 L4A -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'L4A'"
        :wp-id="props.wpId"
        sheet-name="L4A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- L4-1 审定表（负债类贷方+摊余成本） -->
      <L4TabAdjudication
        v-else-if="currentSheet === 'L4-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L4-2 明细表（89列极宽表区段Tab） -->
      <L4TabDetail
        v-else-if="currentSheet === 'L4-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @imported="selfLoad()"
      />
      <!-- L4-3 划分为金融负债的其他金融工具 -->
      <L4TabFinLiabOther
        v-else-if="currentSheet === 'L4-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L4-4 调整分录 -->
      <L4TabAdjustment
        v-else-if="currentSheet === 'L4-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L4-5 权益与负债划分检查 -->
      <L4TabEquityLiabCheck
        v-else-if="currentSheet === 'L4-5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L4-6 初始计量（发行价-交易费用+IRR） -->
      <L4TabInitialMeasure
        v-else-if="currentSheet === 'L4-6'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L4-7 后续计量（2分支选择器！核心） -->
      <L4TabSubsequentBullet
        v-else-if="currentSheet === 'L4-7' && bondBranch === '到期一次还本付息'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <L4TabSubsequentInstallment
        v-else-if="currentSheet === 'L4-7' && bondBranch === '分期付息到期一次还本'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L4-8 账面核对（2分支与L4-7联动） -->
      <L4TabBookReconBullet
        v-else-if="currentSheet === 'L4-8' && bondBranch === '到期一次还本付息'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <L4TabBookReconInstallment
        v-else-if="currentSheet === 'L4-8' && bondBranch === '分期付息到期一次还本'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L4-9 应付债券检查表 -->
      <L4TabBondCheck
        v-else-if="currentSheet === 'L4-9'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注（上市/国企） -->
      <L4TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <L4TabDisclosureSoe
        v-else-if="currentSheet === '附注国企'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- OnlyOffice fallback: 未迁移 sheet -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :sheet-name="props.sheetName"
        style="height: 100%; min-height: 600px"
      />
    </template>

    <!-- L4-7/L4-8 分支选择器（仅当前 sheet 为 L4-7/L4-8 时显示） -->
    <div
      v-if="showBranchSelector"
      class="branch-selector-container"
    >
      <el-segmented
        v-model="bondBranch"
        :options="branchOptions"
        size="default"
      />
    </div>

  </div>
</template>

<script setup lang="ts">
/**
 * GtL4BondsPayable.vue — L4 应付债券底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取末尾编码（L4/L4-1~L4-9/L4A），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：2502 应付债券（贷方/负债类！期末=期初+贷方-借方）
 * 核心特殊：
 *   - 实际利率法EIR后续计量 2分支（到期一次还本付息 / 分期付息到期一次还本）
 *   - L4-7/L4-8 各2版本，用 el-segmented 分支选择器切换
 *   - 主入口 provide bondBranch，L4-7与L4-8 inject同步
 *   - 89列极宽表 L4-2 区段Tab拆分
 *   - 权益负债划分检查（复合金融工具分拆）
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated / l4:interest-calculated / adjustment:created
 * - 跨底稿联动: L4利息费用→L2/L8
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, inject, onMounted, provide, defineAsyncComponent, toRef } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const L4TabIndex = defineAsyncComponent(() => import('./l4/core/L4TabIndex.vue'))
const L4TabAdjudication = defineAsyncComponent(() => import('./l4/core/L4TabAdjudication.vue'))
const L4TabDetail = defineAsyncComponent(() => import('./l4/core/L4TabDetail.vue'))
const L4TabAdjustment = defineAsyncComponent(() => import('./l4/core/L4TabAdjustment.vue'))
const L4TabDisclosureListed = defineAsyncComponent(() => import('./l4/core/L4TabDisclosureListed.vue'))
const L4TabDisclosureSoe = defineAsyncComponent(() => import('./l4/core/L4TabDisclosureSoe.vue'))

// Measurement
const L4TabInitialMeasure = defineAsyncComponent(() => import('./l4/measurement/L4TabInitialMeasure.vue'))
const L4TabSubsequentBullet = defineAsyncComponent(() => import('./l4/measurement/L4TabSubsequentBullet.vue'))
const L4TabSubsequentInstallment = defineAsyncComponent(() => import('./l4/measurement/L4TabSubsequentInstallment.vue'))
const L4TabBookReconBullet = defineAsyncComponent(() => import('./l4/measurement/L4TabBookReconBullet.vue'))
const L4TabBookReconInstallment = defineAsyncComponent(() => import('./l4/measurement/L4TabBookReconInstallment.vue'))

// Classification
const L4TabEquityLiabCheck = defineAsyncComponent(() => import('./l4/classification/L4TabEquityLiabCheck.vue'))
const L4TabFinLiabOther = defineAsyncComponent(() => import('./l4/classification/L4TabFinLiabOther.vue'))

// Inspection
const L4TabBondCheck = defineAsyncComponent(() => import('./l4/inspection/L4TabBondCheck.vue'))

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
 * L4TabIndex 目录行点击/子组件"返回目录"→通知外层 GtWpRenderer 切换 sheetName。
 * 外层 GtWpRenderer 监听 @navigate-sheet（对齐 K1 范式），此处 emit 向上传递请求。
 */
function handleNavigate(sheetName: string) {
  parentEmit('navigate-sheet', sheetName)
}

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

// ─── sheetName → 子组件分发 ──────────────────────────────────────────────────

/**
 * 当前激活的 sheet（由外层 GtWpRenderer 通过 sheetName prop 控制）。
 * GtWpRenderer 传入完整 sheet_name（如"审定表L4-1"），
 * 正则提取末尾编码（L4/L4A/L4-1~L4-9）来匹配子组件。
 */
const currentSheet = computed(() => {
  const name = props.sheetName || 'L4'
  // 底稿目录 sheet → 显示 L4 底稿目录（对齐 K1）
  if (name.includes('底稿目录')) return 'L4'
  // 提取末尾的L4编码（L4/L4A/L4-1~L4-9）
  const match = name.match(/L4(?:-\d+)?[A-Z]?$|L4$/)
  if (match) return match[0]
  // 附注特殊匹配
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企')) return '附注国企'
  return name
})

// ─── bondBranch 分支选择器（L4-7/L4-8 共享） ─────────────────────────────────

/**
 * 应付债券后续计量2分支：
 * - 到期一次还本付息：利息资本化滚入摊余成本
 * - 分期付息到期一次还本：期间付票面利息
 * L4-7与L4-8通过 provide/inject 同步分支状态。
 */
const branchOptions = ['到期一次还本付息', '分期付息到期一次还本'] as const
const bondBranch = ref<typeof branchOptions[number]>('分期付息到期一次还本')

/** 仅当 L4-7/L4-8 时显示分支选择器 */
const showBranchSelector = computed(() => {
  return currentSheet.value === 'L4-7' || currentSheet.value === 'L4-8'
})

provide('bondBranch', bondBranch)

// ─── Runtime Boundary（GtWpRenderer 统一提供 版本/复核/AI/displayPrefs + 挂真实 Host） ───
// 复核对话与版本历史由 Runtime Boundary 统一 provide('openReviewDialog') + version 承载，
// 本主入口不再本地 new GtReviewDialog / useWorkpaperVersionToolbar（避免重复 provider/Host）。
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())

// ─── 复核圆点（子组件 GtReviewTrigger 依赖） ───
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

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
    console.warn('[GtL4BondsPayable] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.l4-bonds-payable {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.branch-selector-container {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  justify-content: center;
  padding: 12px 0;
  margin-bottom: 12px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
