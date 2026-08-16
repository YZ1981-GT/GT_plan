<template>
  <div class="l7-other-noncurrent-liabilities">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- L7 主sheet 底稿目录 -->
      <L7TabIndex
        v-if="currentSheet === 'L7'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 L7A -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'L7A'"
        :wp-id="props.wpId"
        sheet-name="L7A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- L7-1 审定表（负债类贷方+按项目分类+小计） -->
      <L7TabAdjudication
        v-else-if="currentSheet === 'L7-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :html-data="props.htmlData"
        @navigate="handleNavigate"
      />
      <!-- L7-2 明细表（27列区段Tab，按项目列示） -->
      <L7TabDetail
        v-else-if="currentSheet === 'L7-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L7-3 调整分录（借贷平衡） -->
      <L7TabAdjustment
        v-else-if="currentSheet === 'L7-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L7-4 其他非流动负债检查表 -->
      <L7TabOtherCheck
        v-else-if="currentSheet === 'L7-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注（上市/国企） -->
      <L7TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <L7TabDisclosureSoe
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

  </div>
</template>

<script setup lang="ts">
/**
 * GtL7OtherNoncurrentLiabilities.vue — L7 其他非流动负债底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取末尾编码（L7/L7A/L7-1~L7-4），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：2801 其他非流动负债（贷方/负债类！期末=期初+贷方-借方）
 * L筹资循环最简标准负债底稿，无复杂计算引擎。
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated / adjustment:created
 * - 跨底稿联动: TB回写(2801)
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, inject, onMounted, provide, defineAsyncComponent, toRef } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const L7TabIndex = defineAsyncComponent(() => import('./l7/core/L7TabIndex.vue'))
const L7TabAdjudication = defineAsyncComponent(() => import('./l7/core/L7TabAdjudication.vue'))
const L7TabDetail = defineAsyncComponent(() => import('./l7/core/L7TabDetail.vue'))
const L7TabAdjustment = defineAsyncComponent(() => import('./l7/core/L7TabAdjustment.vue'))
const L7TabDisclosureListed = defineAsyncComponent(() => import('./l7/core/L7TabDisclosureListed.vue'))
const L7TabDisclosureSoe = defineAsyncComponent(() => import('./l7/core/L7TabDisclosureSoe.vue'))

// Inspection
const L7TabOtherCheck = defineAsyncComponent(() => import('./l7/inspection/L7TabOtherCheck.vue'))

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
 * 子组件目录行点击 / "← 返回目录" 按钮 emit 'navigate' → 转发为 'navigate-sheet'，
 * 由外层 GtWpRenderer 的 @navigate-sheet(onChildNavigateSheet) 按 sheet_name 子串匹配切换 sheet。
 * 注意：GtWpRenderer 监听的是 'navigate-sheet' 而非 'navigate'，此处必须转发正确的事件名。
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
 * GtWpRenderer 传入完整 sheet_name（如"审定表L7-1"），
 * 正则提取末尾编码（L7/L7A/L7-1~L7-4）来匹配子组件。
 */
const currentSheet = computed(() => {
  const name = props.sheetName || 'L7'
  // 提取末尾的L7编码（L7/L7A/L7-1~L7-4）
  const match = name.match(/L7(?:-\d+)?[A-Z]?$|L7$/)
  if (match) return match[0]
  // 附注特殊匹配
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企')) return '附注国企'
  return name
})

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
    console.warn('[GtL7OtherNoncurrentLiabilities] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.l7-other-noncurrent-liabilities {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
