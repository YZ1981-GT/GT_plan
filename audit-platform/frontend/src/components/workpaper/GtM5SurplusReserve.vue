<template>
  <div class="m5-surplus-reserve">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- M5 底稿目录 -->
      <M5TabIndex
        v-if="currentSheet === 'index'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 M5A（复用 GtAProgramConsole） -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'procedure'"
        :wp-id="props.wpId"
        sheet-name="M5A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- M5-1 审定表（权益类贷方！期末=期初+贷方-借方） -->
      <M5TabAdjudication
        v-else-if="currentSheet === 'M5-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M5-2 明细表（法定+任意盈余公积） -->
      <M5TabDetail
        v-else-if="currentSheet === 'M5-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M5-3 调整分录汇总（借贷平衡） -->
      <M5TabAdjustment
        v-else-if="currentSheet === 'M5-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M5-4 盈余公积计提检查（法定10%+50%上限） -->
      <M5TabAccrualTest
        v-else-if="currentSheet === 'M5-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M5-5 盈余公积检查表 -->
      <M5TabReserveCheck
        v-else-if="currentSheet === 'M5-5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注披露信息（上市公司） -->
      <M5TabDisclosureListed
        v-else-if="currentSheet === 'disclosure-listed'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注披露信息（国有企业） -->
      <M5TabDisclosureSoe
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

    <!-- 复核对话组件 -->
    <GtReviewDialog
      v-if="reviewDialogVisible"
      :wp-id="props.wpId"
      :section-id="reviewDialogSectionId"
      :section-label="reviewDialogSectionLabel"
      :current-user="currentUser"
      :related-data="{ wpCode: 'M5', projectId: props.projectId }"
    />

    <!-- 版本历史抽屉 -->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
  </div>
</template>

<script setup lang="ts">
/**
 * GtM5SurplusReserve.vue — M5 盈余公积底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取编码（M5/M5A/M5-1~M5-5），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：4101 盈余公积（**贷方/权益类！**）
 * 核心铁律：期末=期初+贷方-借方（计提时贷方增加，转增资本/弥补亏损时借方减少）
 * 特殊功能：①权益类贷方公式 ②法定盈余公积10%计提测试 ③接收M6未分配利润(计提基数) ④50%上限判断
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated(4101) / adjustment:created
 * - 跨底稿联动: TB回写(4101) + M6净利润→计提基数 + M5计提盈余公积→M6可供分配利润
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const M5TabIndex = defineAsyncComponent(() => import('./m5/core/M5TabIndex.vue'))
const M5TabAdjudication = defineAsyncComponent(() => import('./m5/core/M5TabAdjudication.vue'))
const M5TabDetail = defineAsyncComponent(() => import('./m5/core/M5TabDetail.vue'))
const M5TabAdjustment = defineAsyncComponent(() => import('./m5/core/M5TabAdjustment.vue'))
const M5TabDisclosureListed = defineAsyncComponent(() => import('./m5/core/M5TabDisclosureListed.vue'))
const M5TabDisclosureSoe = defineAsyncComponent(() => import('./m5/core/M5TabDisclosureSoe.vue'))

// Calc
const M5TabAccrualTest = defineAsyncComponent(() => import('./m5/calc/M5TabAccrualTest.vue'))

// Inspection
const M5TabReserveCheck = defineAsyncComponent(() => import('./m5/inspection/M5TabReserveCheck.vue'))

// Shared
const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtReviewDialog = defineAsyncComponent(() => import('@/components/collaboration/GtReviewDialog.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

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

// ─── Auth (for review dialog) ────────────────────────────────────────────────

const authStore = useAuthStore()
const currentUser = computed(() => ({
  id: authStore.userId || '',
  name: authStore.user?.full_name || authStore.username || '',
  role: (authStore.user?.role || '审计助理') as any,
}))

// ─── sheetName → 子组件分发 ──────────────────────────────────────────────────

/**
 * 当前激活的 sheet（由外层 GtWpRenderer 通过 sheetName prop 控制）。
 * GtWpRenderer 传入完整 sheet_name（如"审定表M5-1"），
 * 正则提取编码来匹配子组件。
 *
 * 映射关系：
 *   底稿目录                         → index             → M5TabIndex
 *   盈余公积实质性程序表M5A          → procedure         → GtAProgramConsole (复用)
 *   审定表M5-1                       → M5-1              → M5TabAdjudication（权益类贷方！）
 *   明细表M5-2                       → M5-2              → M5TabDetail（法定+任意盈余公积）
 *   调整分录汇总M5-3                 → M5-3              → M5TabAdjustment
 *   盈余公积计提检查表M5-4           → M5-4              → M5TabAccrualTest（法定10%+50%上限）
 *   盈余公积检查表M5-5               → M5-5              → M5TabReserveCheck
 *   附注披露信息（上市公司）         → disclosure-listed → M5TabDisclosureListed
 *   附注披露信息（国有企业）         → disclosure-soe    → M5TabDisclosureSoe
 *   参考－会计规定                   → OO fallback       → GtOnlyOfficeSheet
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // 提取 M5-N 编码（M5-1 ~ M5-5）
  const codeMatch = name.match(/M5-[1-5]/)
  if (codeMatch) return codeMatch[0]

  // 程序表 M5A
  if (name.match(/M5A/) || name.includes('实质性程序表')) return 'procedure'

  // 附注特殊匹配
  if (name.includes('上市公司')) return 'disclosure-listed'
  if (name.includes('国有企业')) return 'disclosure-soe'

  // 底稿目录（默认）
  if (name.includes('底稿目录') || name === 'M5' || name === '') return 'index'

  // 未匹配（会计规定辅助等）→ OO fallback
  return name
})

// ─── Provide openReviewDialog ────────────────────────────────────────────────

/** 复核对话状态 */
const reviewDialogVisible = ref(false)
const reviewDialogSectionId = ref('')
const reviewDialogSectionLabel = ref('')

/**
 * 子组件 inject 后在 section 标题栏右侧放复核按钮。
 * 点击调用 openReviewDialog(sectionId, sectionLabel?) 打开复核对话面板。
 */
function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  reviewDialogSectionId.value = sectionId
  reviewDialogSectionLabel.value = sectionLabel || sectionId
  reviewDialogVisible.value = true
}

provide('openReviewDialog', openReviewDialog)

// ─── 版本追踪 useWorkpaperVersionToolbar (autoSnapshot on save) ──────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar

provide('versionTrail', versionToolbar)
provide('openVersionHistory', () => versionToolbar.openVersionHistory())

// ─── 监听 m5:save-items → 保存后自动快照 ────────────────────────────────────

function handleM5SaveItems(_e: Event): void {
  versionToolbar.scheduleAutoSnapshot()
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
    console.warn('[GtM5SurplusReserve] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  window.addEventListener('m5:save-items', handleM5SaveItems)
  selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('m5:save-items', handleM5SaveItems)
})
</script>

<style scoped>
.m5-surplus-reserve {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
