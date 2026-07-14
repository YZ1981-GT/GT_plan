<template>
  <div class="l6-special-payables">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- L6 主sheet 底稿目录 -->
      <L6TabIndex
        v-if="currentSheet === 'L6'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 L6A -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'L6A'"
        :wp-id="props.wpId"
        sheet-name="L6A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- L6-1 审定表（负债类贷方+按专项项目分类+小计） -->
      <L6TabAdjudication
        v-else-if="currentSheet === 'L6-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L6-2 明细表（33列区段Tab，按专项项目列示） -->
      <L6TabDetail
        v-else-if="currentSheet === 'L6-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L6-3 调整分录（借贷平衡） -->
      <L6TabAdjustment
        v-else-if="currentSheet === 'L6-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L6-4 专项应付款检查表（专款专用核查） -->
      <L6TabSpecialCheck
        v-else-if="currentSheet === 'L6-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注（上市/国企） -->
      <L6TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <L6TabDisclosureSoe
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
 * GtL6SpecialPayables.vue — L6 专项应付款底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取末尾编码（L6/L6A/L6-1~L6-4），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：2601 专项应付款（贷方/负债类！期末=期初+贷方-借方）
 * L筹资循环标准负债底稿，专款专用核查为核心程序。
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated / adjustment:created
 * - 跨底稿联动: TB回写(2601)
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, inject, onMounted, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const L6TabIndex = defineAsyncComponent(() => import('./l6/core/L6TabIndex.vue'))
const L6TabAdjudication = defineAsyncComponent(() => import('./l6/core/L6TabAdjudication.vue'))
const L6TabDetail = defineAsyncComponent(() => import('./l6/core/L6TabDetail.vue'))
const L6TabAdjustment = defineAsyncComponent(() => import('./l6/core/L6TabAdjustment.vue'))
const L6TabDisclosureListed = defineAsyncComponent(() => import('./l6/core/L6TabDisclosureListed.vue'))
const L6TabDisclosureSoe = defineAsyncComponent(() => import('./l6/core/L6TabDisclosureSoe.vue'))

// Inspection
const L6TabSpecialCheck = defineAsyncComponent(() => import('./l6/inspection/L6TabSpecialCheck.vue'))

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
 * GtWpRenderer 传入完整 sheet_name（如"审定表L6-1"），
 * 正则提取末尾编码（L6/L6A/L6-1~L6-4）来匹配子组件。
 */
const currentSheet = computed(() => {
  const name = props.sheetName || 'L6'
  // 提取末尾的L6编码（L6/L6A/L6-1~L6-4）
  const match = name.match(/L6(?:-\d+)?[A-Z]?$|L6$/)
  if (match) return match[0]
  // 附注特殊匹配
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企') || name.includes('国有')) return '附注国企'
  return name
})

// ─── Runtime Boundary（GtWpRenderer 统一提供 版本/复核/AI/displayPrefs + 挂真实 Host） ───
// 复核对话与版本历史由 Runtime Boundary 统一 provide('openReviewDialog') + version 承载，
// 本主入口不再本地 new GtReviewDialog / useWorkpaperVersionToolbar（避免重复 provider/Host）。
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())

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
    console.warn('[GtL6SpecialPayables] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.l6-special-payables {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
