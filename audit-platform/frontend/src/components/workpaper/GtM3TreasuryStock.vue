<template>
  <div class="m3-treasury-stock">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- M3 底稿目录（不参与双模式） -->
      <M3TabIndex
        v-if="currentSheet === 'index'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 M3A（复用 GtAProgramConsole，不参与双模式） -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'procedure'"
        :wp-id="props.wpId"
        sheet-name="M3A"
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
          <!-- M3-1 审定表（权益备抵类借方！期末=期初+借方-贷方） -->
          <M3TabAdjudication
            v-if="currentSheet === 'M3-1'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- 附注披露信息（上市公司） -->
          <M3TabDisclosureListed
            v-else-if="currentSheet === 'disclosure-listed'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M3-2 明细表（按回购批次列示，19列3区段Tab） -->
          <M3TabDetail
            v-else-if="currentSheet === 'M3-2'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M3-3 调整分录汇总（借贷平衡） -->
          <M3TabAdjustment
            v-else-if="currentSheet === 'M3-3'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M3-4 外币投资汇率测算表（外币回购折算） -->
          <M3TabFxInvest
            v-else-if="currentSheet === 'M3-4'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- M3-5 库存股检查表（回购/注销核对） -->
          <M3TabTreasuryCheck
            v-else-if="currentSheet === 'M3-5'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
            @navigate="handleNavigate"
          />
          <!-- OnlyOffice fallback: 未迁移 sheet / 会计规定辅助 -->
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
 * GtM3TreasuryStock.vue — M3 库存股底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取编码（M3/M3A/M3-1~M3-5），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：4002 库存股（**借方/权益备抵类！**）
 * 核心铁律：期末=期初+借方-贷方（回购在借方增加，注销/再售在贷方减少，与其他M权益类方向相反！）
 * 特殊功能：①权益备抵借方公式 ②回购/注销核对(M3-5) ③外币回购折算(M3-4) ④按回购批次列示(M3-2)
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated(4002) / adjustment:created
 * - 跨底稿联动: TB回写(4002) + 注销冲减→M2实收资本 + 注销冲减→M4资本公积
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, inject, onMounted, provide, toRef, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import { useM3EntryDualMode } from './composables/useM3EntryDualMode'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const M3TabIndex = defineAsyncComponent(() => import('./m3/core/M3TabIndex.vue'))
const M3TabAdjudication = defineAsyncComponent(() => import('./m3/core/M3TabAdjudication.vue'))
const M3TabDetail = defineAsyncComponent(() => import('./m3/core/M3TabDetail.vue'))
const M3TabAdjustment = defineAsyncComponent(() => import('./m3/core/M3TabAdjustment.vue'))
const M3TabDisclosureListed = defineAsyncComponent(() => import('./m3/core/M3TabDisclosureListed.vue'))

// Calc (外币投资汇率)
const M3TabFxInvest = defineAsyncComponent(() => import('./m3/calc/M3TabFxInvest.vue'))

// Inspection (检查表：回购/注销核对)
const M3TabTreasuryCheck = defineAsyncComponent(() => import('./m3/inspection/M3TabTreasuryCheck.vue'))

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
 * GtWpRenderer 传入完整 sheet_name（如"审定表M3-1"），
 * 正则提取编码来匹配子组件。
 *
 * 映射关系：
 *   底稿目录                         → index             → M3TabIndex
 *   库存股实质性程序表M3A            → procedure         → GtAProgramConsole (复用)
 *   审定表M3-1                       → M3-1              → M3TabAdjudication（权益备抵借方！）
 *   附注披露信息（上市公司）         → disclosure-listed → M3TabDisclosureListed
 *   明细表M3-2                       → M3-2              → M3TabDetail（按回购批次）
 *   调整分录汇总M3-3                 → M3-3              → M3TabAdjustment
 *   外币投资汇率测算表M3-4           → M3-4              → M3TabFxInvest（外币回购折算）
 *   库存股检查表M3-5                 → M3-5              → M3TabTreasuryCheck（回购/注销核对）
 *   参考－会计规定                   → OO fallback       → GtOnlyOfficeSheet (SKIP)
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // 提取 M3-N 编码（M3-1 ~ M3-5）
  const codeMatch = name.match(/M3-[1-5]/)
  if (codeMatch) return codeMatch[0]

  // 程序表 M3A
  if (name.match(/M3A/) || name.includes('实质性程序表')) return 'procedure'

  // 附注特殊匹配
  if (name.includes('上市公司')) return 'disclosure-listed'

  // 底稿目录（默认）
  if (name.includes('底稿目录') || name === 'M3' || name === '') return 'index'

  // 未匹配（会计规定辅助等）→ OO fallback
  return name
})

// ─── 双模式（HTML ↔ OnlyOffice，健康门控"拉取成功才切"，对齐 D4/M1 范式） ───
// index/procedure 不参与双模式；其余 HTML sheet 上方显示 segmented 切换栏。
const dualMode = useM3EntryDualMode({
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
    console.warn('[GtM3TreasuryStock] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.m3-treasury-stock {
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
