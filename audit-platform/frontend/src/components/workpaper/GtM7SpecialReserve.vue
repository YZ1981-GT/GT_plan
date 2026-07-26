<template>
  <div class="m7-special-reserve">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- M7 底稿目录（不参与双模式） -->
      <M7TabIndex
        v-if="currentSheet === 'index'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 M7A（复用 GtAProgramConsole，不参与双模式） -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'procedure'"
        :wp-id="props.wpId"
        sheet-name="M7A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- 其余 HTML sheet：结构化 / OnlyOffice 双模式切换（健康门控） -->
      <template v-else>
        <div class="mode-toggle-bar">
          <el-segmented
            :model-value="dualMode.mode.value"
            :options="modeToggleOptions"
            size="small"
            @change="dualMode.switchMode"
          />
        </div>

        <!-- 结构化视图（HTML sheet 分支） -->
        <template v-if="dualMode.mode.value === 'html'">
          <!-- M7-1 审定表（权益类贷方！期末=期初+贷方-借方） -->
          <M7TabAdjudication
            v-if="currentSheet === 'M7-1'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M7-2 明细表（计提+使用明细，27列区段Tab） -->
          <M7TabDetail
            v-else-if="currentSheet === 'M7-2'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M7-3 调整分录汇总（借贷平衡） -->
          <M7TabAdjustment
            v-else-if="currentSheet === 'M7-3'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M7-4 专项储备计提测试（安全生产费，按产量/收入） -->
          <M7TabAccrualTest
            v-else-if="currentSheet === 'M7-4'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M7-5 专项储备支出检查表 -->
          <M7TabExpenditureCheck
            v-else-if="currentSheet === 'M7-5'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- 附注披露信息（上市公司） -->
          <M7TabDisclosureListed
            v-else-if="currentSheet === 'disclosure-listed'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- 附注披露信息（国有企业） -->
          <M7TabDisclosureSoe
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

        <!-- OnlyOffice 在线编辑模式 -->
        <GtOnlyOfficeSheet
          v-else
          :wp-id="props.wpId"
          :sheet-name="dualMode.resolveOoSheetName()"
          style="height: 100%; min-height: 600px"
        />
      </template>
    </template>

  </div>
</template>

<script setup lang="ts">
/**
 * GtM7SpecialReserve.vue — M7 专项储备底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取编码（M7/M7A/M7-1~M7-5），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：4201 专项储备（**贷方/权益类！**）
 * 核心铁律：期末=期初+贷方-借方（计提时贷方增加，使用时借方减少）
 * 特殊功能：①权益类贷方公式 ②安全生产费计提测试（按产量/收入分档） ③支出检查（资本化转H1/费用化冲减）
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated(4201) / adjustment:created
 * - 跨底稿联动: TB回写(4201) + 资本化支出→H1固定资产
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, inject, onMounted, onBeforeUnmount, provide, toRef, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import { useM7EntryDualMode } from './composables/useM7EntryDualMode'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const M7TabIndex = defineAsyncComponent(() => import('./m7/core/M7TabIndex.vue'))
const M7TabAdjudication = defineAsyncComponent(() => import('./m7/core/M7TabAdjudication.vue'))
const M7TabDetail = defineAsyncComponent(() => import('./m7/core/M7TabDetail.vue'))
const M7TabAdjustment = defineAsyncComponent(() => import('./m7/core/M7TabAdjustment.vue'))
const M7TabDisclosureListed = defineAsyncComponent(() => import('./m7/core/M7TabDisclosureListed.vue'))
const M7TabDisclosureSoe = defineAsyncComponent(() => import('./m7/core/M7TabDisclosureSoe.vue'))

// Calc
const M7TabAccrualTest = defineAsyncComponent(() => import('./m7/calc/M7TabAccrualTest.vue'))

// Inspection
const M7TabExpenditureCheck = defineAsyncComponent(() => import('./m7/inspection/M7TabExpenditureCheck.vue'))

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
 * M7TabIndex 目录行点击→通知外层 GtWpRenderer 切换 sheetName。
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
 * GtWpRenderer 传入完整 sheet_name（如"审定表M7-1"），
 * 正则提取编码来匹配子组件。
 *
 * 映射关系：
 *   底稿目录                              → index             → M7TabIndex
 *   专项储备实质性程序表M7A               → procedure         → GtAProgramConsole (复用)
 *   审定表M7-1                            → M7-1              → M7TabAdjudication（权益类贷方！）
 *   明细表M7-2                            → M7-2              → M7TabDetail（计提+使用27列区段Tab）
 *   调整分录汇总M7-3                      → M7-3              → M7TabAdjustment
 *   专项储备计提测试表M7-4                → M7-4              → M7TabAccrualTest（安全生产费）
 *   专项储备支出检查表M7-5                → M7-5              → M7TabExpenditureCheck
 *   附注披露信息（上市公司）              → disclosure-listed → M7TabDisclosureListed
 *   附注披露信息（国有企业）              → disclosure-soe    → M7TabDisclosureSoe
 *   参考－会计规定                        → OO fallback       → GtOnlyOfficeSheet
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // 提取 M7-N 编码（M7-1 ~ M7-5）
  const codeMatch = name.match(/M7-[1-5]/)
  if (codeMatch) return codeMatch[0]

  // 程序表 M7A
  if (name.match(/M7A/) || name.includes('实质性程序表')) return 'procedure'

  // 附注特殊匹配
  if (name.includes('上市公司')) return 'disclosure-listed'
  if (name.includes('国有企业')) return 'disclosure-soe'

  // 底稿目录（默认）
  if (name.includes('底稿目录') || name === 'M7' || name === '') return 'index'

  // 未匹配（会计规定辅助等）→ OO fallback
  return name
})

// ─── 双模式（HTML ↔ OnlyOffice，健康门控"拉取成功才切"，对齐 M1/D4 范式） ───
// index/procedure 不参与双模式；其余 HTML sheet 上方显示 segmented 切换栏。
const dualMode = useM7EntryDualMode({
  wpId: toRef(props, 'wpId') as any,
  currentSheet,
  reloadAllResponses: async () => {
    // 各子组件在 mount 时自加载各自 formData；此处仅重跑 render-config 预热。
    await selfLoad()
  },
})

const modeToggleOptions = computed(() => [
  { label: '结构化', value: 'html' as const },
  {
    label: dualMode.ooAvailable.value ? 'OnlyOffice（拉取成功）' : 'OnlyOffice（不可用）',
    value: 'onlyoffice' as const,
    disabled: !dualMode.ooAvailable.value,
  },
])

// ─── Runtime Boundary（GtWpRenderer 统一提供 版本/复核/AI/displayPrefs + 挂真实 Host） ───
// 复核对话与版本历史由 Runtime Boundary 统一 provide('openReviewDialog') + version 承载，
// 本主入口不再本地 new GtReviewDialog / useWorkpaperVersionToolbar（避免重复 provider/Host）。
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())

// 复核圆点（GtReviewTrigger/GtReviewDot 消费）
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

// ─── 监听 m7:save-items → 保存后自动快照（版本链能力来自 Runtime Boundary） ──

function handleM7SaveItems(_e: Event): void {
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
    console.warn('[GtM7SpecialReserve] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  window.addEventListener('m7:save-items', handleM7SaveItems)
  selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('m7:save-items', handleM7SaveItems)
})
</script>

<style scoped>
.m7-special-reserve {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.mode-toggle-bar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
</style>
