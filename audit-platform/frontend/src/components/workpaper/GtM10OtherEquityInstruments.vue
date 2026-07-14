<template>
  <div class="m10-other-equity-instruments">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- M10 底稿目录 -->
      <M10TabIndex
        v-if="currentSheet === 'index'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 M10A（复用 GtAProgramConsole） -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'procedure'"
        :wp-id="props.wpId"
        sheet-name="M10A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- M10-1 审定表（权益类贷方！期末=期初+贷方-借方，按工具类型分类） -->
      <M10TabAdjudication
        v-else-if="currentSheet === 'M10-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M10-2 明细表（永续债/优先股明细，30列区段Tab） -->
      <M10TabDetail
        v-else-if="currentSheet === 'M10-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M10-3 调整分录汇总（借贷平衡） -->
      <M10TabAdjustment
        v-else-if="currentSheet === 'M10-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M10-4 负债与权益区分检查表（CAS37核心！64×8逐条判定） -->
      <M10TabClassificationCheck
        v-else-if="currentSheet === 'M10-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M10-5 其他权益工具检查表 -->
      <M10TabInstrumentCheck
        v-else-if="currentSheet === 'M10-5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注披露信息（上市公司） -->
      <M10TabDisclosureListed
        v-else-if="currentSheet === 'disclosure-listed'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注披露信息（国有企业） -->
      <M10TabDisclosureSoe
        v-else-if="currentSheet === 'disclosure-soe'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- OnlyOffice fallback: 未迁移 sheet / Q10A修订前 / 参考辅助 -->
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
 * GtM10OtherEquityInstruments.vue — M10 其他权益工具底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取编码（M10/M10A/M10-1~M10-5），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：4003 其他权益工具（**贷方/权益类！**）
 * 核心铁律：期末=期初+贷方-借方（发行时贷方增加，赎回/转换时借方减少）
 * 特殊功能：①权益类贷方公式 ②CAS37负债与权益区分（永续债/优先股判定） ③权益+负债金额守恒
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated(4003) / adjustment:created
 * - 跨底稿联动: TB回写(4003) + 负债部分→负债科目 + 附注subscribe
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, inject, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const M10TabIndex = defineAsyncComponent(() => import('./m10/core/M10TabIndex.vue'))
const M10TabAdjudication = defineAsyncComponent(() => import('./m10/core/M10TabAdjudication.vue'))
const M10TabDetail = defineAsyncComponent(() => import('./m10/core/M10TabDetail.vue'))
const M10TabAdjustment = defineAsyncComponent(() => import('./m10/core/M10TabAdjustment.vue'))
const M10TabDisclosureListed = defineAsyncComponent(() => import('./m10/core/M10TabDisclosureListed.vue'))
const M10TabDisclosureSoe = defineAsyncComponent(() => import('./m10/core/M10TabDisclosureSoe.vue'))

// Inspection
const M10TabClassificationCheck = defineAsyncComponent(() => import('./m10/inspection/M10TabClassificationCheck.vue'))
const M10TabInstrumentCheck = defineAsyncComponent(() => import('./m10/inspection/M10TabInstrumentCheck.vue'))

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
 * M10TabIndex 目录行点击→通知外层 GtWpRenderer 切换 sheetName。
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
 * GtWpRenderer 传入完整 sheet_name（如"审定表M10-1"），
 * 正则提取编码来匹配子组件。
 *
 * 映射关系：
 *   底稿目录                               → index             → M10TabIndex
 *   其他权益工具实质性程序表M10A           → procedure         → GtAProgramConsole (复用)
 *   审定表M10-1                            → M10-1             → M10TabAdjudication（权益类贷方！）
 *   明细表M10-2                            → M10-2             → M10TabDetail（永续债/优先股明细）
 *   调整分录汇总M10-3                      → M10-3             → M10TabAdjustment
 *   负债与权益区分检查表M10-4              → M10-4             → M10TabClassificationCheck（CAS37核心）
 *   其他权益工具检查表M10-5                → M10-5             → M10TabInstrumentCheck
 *   附注披露信息（上市公司）               → disclosure-listed → M10TabDisclosureListed
 *   附注披露信息（国有企业）               → disclosure-soe    → M10TabDisclosureSoe
 *   Q10A修订前 / 参考                      → OO fallback       → GtOnlyOfficeSheet
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // 提取 M10-N 编码（M10-1 ~ M10-5）
  const codeMatch = name.match(/M10-[1-5]/)
  if (codeMatch) return codeMatch[0]

  // 程序表 M10A
  if (name.match(/M10A/) || name.includes('实质性程序表')) return 'procedure'

  // 附注特殊匹配
  if (name.includes('上市公司')) return 'disclosure-listed'
  if (name.includes('国有企业')) return 'disclosure-soe'

  // Q10A修订前 → OO fallback（skip）
  if (name.includes('修订前') || name.includes('Q10A')) return name

  // 底稿目录（默认）
  if (name.includes('底稿目录') || name === 'M10' || name === '') return 'index'

  // 未匹配（参考/辅助等）→ OO fallback
  return name
})

// ─── Runtime Boundary（GtWpRenderer 统一提供 版本/复核/AI/displayPrefs + 挂真实 Host） ───
// 复核对话与版本历史由 Runtime Boundary 统一 provide('openReviewDialog') + version 承载，
// 本主入口不再本地 new GtReviewDialog / useWorkpaperVersionToolbar（避免重复 provider/Host）。
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())

// ─── 监听 m10:save-items → 保存后自动快照（版本链能力来自 Runtime Boundary） ──

function handleM10SaveItems(_e: Event): void {
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
    console.warn('[GtM10OtherEquityInstruments] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  window.addEventListener('m10:save-items', handleM10SaveItems)
  selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('m10:save-items', handleM10SaveItems)
})
</script>

<style scoped>
.m10-other-equity-instruments {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
