<template>
  <div class="m9-other-comprehensive-income">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- M9 底稿目录 -->
      <M9TabIndex
        v-if="currentSheet === 'index'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 M9A（复用 GtAProgramConsole） -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'procedure'"
        :wp-id="props.wpId"
        sheet-name="M9A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- M9-1 审定表（权益类贷方！期末=期初+贷方-借方，双大类：不可/可重分类） -->
      <M9TabAdjudication
        v-else-if="currentSheet === 'M9-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M9-2 明细表（OCI分项+税后净额，30列区段Tab） -->
      <M9TabDetail
        v-else-if="currentSheet === 'M9-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M9-3 调整分录汇总（借贷平衡） -->
      <M9TabAdjustment
        v-else-if="currentSheet === 'M9-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M9-4 OCI核对表（多来源核对：G8公允变动+J2重计量+外币折算，13公式） -->
      <M9TabOciReconcile
        v-else-if="currentSheet === 'M9-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注披露信息（上市公司） -->
      <M9TabDisclosureListed
        v-else-if="currentSheet === 'disclosure-listed'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注披露信息（国有企业，67×21，20公式） -->
      <M9TabDisclosureSoe
        v-else-if="currentSheet === 'disclosure-soe'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
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
 * GtM9OtherComprehensiveIncome.vue — M9 其他综合收益底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取编码（M9/M9A/M9-1~M9-4），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：4103 其他综合收益（**贷方/权益类！**）
 * 核心铁律：期末=期初+贷方-借方（OCI增加时贷方增加，减少/重分类进损益时借方减少）
 * 特殊功能：①权益类贷方公式 ②OCI双大类(不可/可重分类) ③OCI核对(接收G8/J2/外币折算) ④税后净额
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated(4103) / adjustment:created
 * - 跨底稿联动: TB回写(4103) + G8公允变动→OCI核对 + J2重计量→OCI核对
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, inject, onMounted, onBeforeUnmount, provide, toRef, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const M9TabIndex = defineAsyncComponent(() => import('./m9/core/M9TabIndex.vue'))
const M9TabAdjudication = defineAsyncComponent(() => import('./m9/core/M9TabAdjudication.vue'))
const M9TabDetail = defineAsyncComponent(() => import('./m9/core/M9TabDetail.vue'))
const M9TabAdjustment = defineAsyncComponent(() => import('./m9/core/M9TabAdjustment.vue'))
const M9TabDisclosureListed = defineAsyncComponent(() => import('./m9/core/M9TabDisclosureListed.vue'))
const M9TabDisclosureSoe = defineAsyncComponent(() => import('./m9/core/M9TabDisclosureSoe.vue'))

// Inspection
const M9TabOciReconcile = defineAsyncComponent(() => import('./m9/inspection/M9TabOciReconcile.vue'))

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
 * M9TabIndex 目录行点击→通知外层 GtWpRenderer 切换 sheetName。
 * 注意：GtWpRenderer 监听 @navigate-sheet，故此处必须 emit 'navigate-sheet'。
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
 * GtWpRenderer 传入完整 sheet_name（如"审定表M9-1"），
 * 正则提取编码来匹配子组件。
 *
 * 映射关系：
 *   底稿目录                                   → index             → M9TabIndex
 *   其他综合收益实质性程序表M9A                → procedure         → GtAProgramConsole (复用)
 *   审定表M9-1                                 → M9-1              → M9TabAdjudication（权益类贷方！双大类）
 *   明细表M9-2                                 → M9-2              → M9TabDetail（OCI分项+税后净额）
 *   调整分录汇总M9-3                           → M9-3              → M9TabAdjustment
 *   OCI核对表M9-4                              → M9-4              → M9TabOciReconcile（多来源核对）
 *   附注披露信息（上市公司）                   → disclosure-listed → M9TabDisclosureListed
 *   附注披露信息（国有企业）                   → disclosure-soe    → M9TabDisclosureSoe
 *   参考－会计规定 / 其他                       → OO fallback       → GtOnlyOfficeSheet
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // 提取 M9-N 编码（M9-1 ~ M9-4）
  const codeMatch = name.match(/M9-[1-4]/)
  if (codeMatch) return codeMatch[0]

  // 程序表 M9A
  if (name.match(/M9A/) || name.includes('实质性程序表')) return 'procedure'

  // 附注特殊匹配
  if (name.includes('上市公司')) return 'disclosure-listed'
  if (name.includes('国有企业')) return 'disclosure-soe'

  // 底稿目录（默认）
  if (name.includes('底稿目录') || name === 'M9' || name === '') return 'index'

  // 未匹配（会计规定辅助等）→ OO fallback
  return name
})

// ─── Runtime Boundary（GtWpRenderer 统一提供 版本/复核/AI/displayPrefs + 挂真实 Host） ───
// 复核对话与版本历史由 Runtime Boundary 统一 provide('openReviewDialog') + version 承载，
// 本主入口不再本地 new GtReviewDialog / useWorkpaperVersionToolbar（避免重复 provider/Host）。
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())

// 复核圆点（GtReviewTrigger/GtReviewDot 消费）
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

// ─── 监听 m9:save-items → 保存后自动快照（版本链能力来自 Runtime Boundary） ──

function handleM9SaveItems(_e: Event): void {
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
    console.warn('[GtM9OtherComprehensiveIncome] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  window.addEventListener('m9:save-items', handleM9SaveItems)
  selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('m9:save-items', handleM9SaveItems)
})
</script>

<style scoped>
.m9-other-comprehensive-income {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
