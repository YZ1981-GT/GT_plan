<template>
  <div class="m2-paid-in-capital">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- M2 底稿目录 -->
      <M2TabIndex
        v-if="currentSheet === 'index'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 M2A（复用 GtAProgramConsole） -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'procedure'"
        :wp-id="props.wpId"
        sheet-name="M2A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- M2-1 审定表（权益类贷方+按出资人分类+小计） -->
      <M2TabAdjudication
        v-else-if="currentSheet === 'M2-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注披露信息（上市公司） -->
      <M2TabDisclosureListed
        v-else-if="currentSheet === 'disclosure-listed'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注披露信息（国有企业） -->
      <M2TabDisclosureSoe
        v-else-if="currentSheet === 'disclosure-soe'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M2-2 明细表（上市/非上市双版本分支选择器） -->
      <M2TabDetail
        v-else-if="currentSheet === 'M2-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M2-3 调整分录汇总（借贷平衡） -->
      <M2TabAdjustment
        v-else-if="currentSheet === 'M2-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M2-4 外币投资汇率测算表（13公式） -->
      <M2TabFxInvest
        v-else-if="currentSheet === 'M2-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M2-5 实收资本（股本）检查表（含验资核对） -->
      <M2TabCapitalCheck
        v-else-if="currentSheet === 'M2-5'"
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
 * GtM2PaidInCapital.vue — M2 实收资本（股本）底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取编码（M2/M2A/M2-1~M2-5），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：4001 实收资本/股本（贷方/权益类！期末=期初+贷方-借方）
 * 增资在贷方增加，减资在借方减少。
 * 特殊功能：①权益类贷方公式 ②上市/非上市双版本明细(M2-2) ③验资核对(M2-5) ④外币投资折算(M2-4)
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated(4001) / adjustment:created
 * - 跨底稿联动: TB回写(4001) + M2-4折算差异→M4资本公积
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, inject, onMounted, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const M2TabIndex = defineAsyncComponent(() => import('./m2/core/M2TabIndex.vue'))
const M2TabAdjudication = defineAsyncComponent(() => import('./m2/core/M2TabAdjudication.vue'))
const M2TabDetail = defineAsyncComponent(() => import('./m2/core/M2TabDetail.vue'))
const M2TabAdjustment = defineAsyncComponent(() => import('./m2/core/M2TabAdjustment.vue'))
const M2TabDisclosureListed = defineAsyncComponent(() => import('./m2/core/M2TabDisclosureListed.vue'))
const M2TabDisclosureSoe = defineAsyncComponent(() => import('./m2/core/M2TabDisclosureSoe.vue'))

// Calc (外币投资汇率)
const M2TabFxInvest = defineAsyncComponent(() => import('./m2/calc/M2TabFxInvest.vue'))

// Inspection (检查表+验资核对)
const M2TabCapitalCheck = defineAsyncComponent(() => import('./m2/inspection/M2TabCapitalCheck.vue'))

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
 * 子组件目录行点击 / 返回目录 → 通知外层 GtWpRenderer 切换 sheetName。
 * GtWpRenderer 监听的是 `@navigate-sheet`(onChildNavigateSheet)，故此处必须
 * emit `navigate-sheet`（而非 `navigate`），否则二级导航静默失效。
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
 * GtWpRenderer 传入完整 sheet_name（如"审定表M2-1"），
 * 正则提取编码来匹配子组件。
 *
 * 映射关系：
 *   底稿目录                    → index    → M2TabIndex
 *   实收资本实质性程序表M2A     → procedure → GtAProgramConsole (复用)
 *   审定表M2-1                  → M2-1     → M2TabAdjudication
 *   附注披露信息（上市公司）    → disclosure-listed → M2TabDisclosureListed
 *   附注披露信息（国有企业）    → disclosure-soe    → M2TabDisclosureSoe
 *   明细表M2-2                  → M2-2     → M2TabDetail (双版本分支选择器)
 *   调整分录汇总M2-3            → M2-3     → M2TabAdjustment
 *   外币投资汇率测算表M2-4      → M2-4     → M2TabFxInvest
 *   检查表M2-5                  → M2-5     → M2TabCapitalCheck (含验资核对)
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // 提取 M2-N 编码（M2-1 ~ M2-5）
  const codeMatch = name.match(/M2-[1-5]/)
  if (codeMatch) return codeMatch[0]

  // 程序表 M2A
  if (name.match(/M2A/) || name.includes('实质性程序表')) return 'procedure'

  // 附注特殊匹配
  if (name.includes('上市公司')) return 'disclosure-listed'
  if (name.includes('国有企业')) return 'disclosure-soe'

  // 底稿目录（默认）
  if (name.includes('底稿目录') || name === 'M2' || name === '') return 'index'

  // 未匹配 → OO fallback
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
    console.warn('[GtM2PaidInCapital] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.m2-paid-in-capital {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
