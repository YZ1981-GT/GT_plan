<template>
  <div class="l5-long-term-payables">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- L5 主sheet 底稿目录 -->
      <L5TabIndex
        v-if="currentSheet === 'L5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 L5A -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'L5A'"
        :wp-id="props.wpId"
        sheet-name="L5A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- L5-1 审定表（负债类贷方+未确认融资费用备抵+净额） -->
      <L5TabAdjudication
        v-else-if="currentSheet === 'L5-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L5-2 明细表（按款项列示，30列区段Tab） -->
      <L5TabDetail
        v-else-if="currentSheet === 'L5-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L5-3 未确认融资费用明细表 -->
      <L5TabUnrecognizedDetail
        v-else-if="currentSheet === 'L5-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L5-4 调整分录 -->
      <L5TabAdjustment
        v-else-if="currentSheet === 'L5-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L5-5 未确认融资费用测算表（核心！实际利率法摊销） -->
      <L5TabAmortization
        v-else-if="currentSheet === 'L5-5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L5-6 关联方及交易检查表 -->
      <L5TabRelatedParty
        v-else-if="currentSheet === 'L5-6'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L5-7 长期应付款检查表 -->
      <L5TabLtPayableCheck
        v-else-if="currentSheet === 'L5-7'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- 附注（上市/国企） -->
      <L5TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <L5TabDisclosureSoe
        v-else-if="currentSheet === '附注国企'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- OnlyOffice fallback: 未迁移 sheet -->
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
      :related-data="{ wpCode: 'L5', projectId: props.projectId }"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * GtL5LongTermPayables.vue — L5 长期应付款底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取末尾编码（L5/L5A/L5-1~L5-7），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：2701 长期应付款（贷方/负债类！期末=期初+贷方-借方）
 *           + 未确认融资费用（借方/负债备抵类！期末=期初+借方-贷方）
 * 核心特殊：
 *   - 负债类贷方科目：期末=期初+贷方-借方
 *   - 未确认融资费用摊销：实际利率法（每期摊销=期初摊余成本×实际利率）
 *   - 净额=长期应付款-未确认融资费用
 *   - L5-5本期摊销→L8财务费用联动
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated / l5:amortization-calculated / adjustment:created
 * - 跨底稿联动: L5本期摊销→L8财务费用
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, onMounted, provide, defineAsyncComponent, toRef } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import useVersionTrail from './composables/useVersionTrail'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const L5TabIndex = defineAsyncComponent(() => import('./l5/core/L5TabIndex.vue'))
const L5TabAdjudication = defineAsyncComponent(() => import('./l5/core/L5TabAdjudication.vue'))
const L5TabDetail = defineAsyncComponent(() => import('./l5/core/L5TabDetail.vue'))
const L5TabUnrecognizedDetail = defineAsyncComponent(() => import('./l5/core/L5TabUnrecognizedDetail.vue'))
const L5TabAdjustment = defineAsyncComponent(() => import('./l5/core/L5TabAdjustment.vue'))
const L5TabDisclosureListed = defineAsyncComponent(() => import('./l5/core/L5TabDisclosureListed.vue'))
const L5TabDisclosureSoe = defineAsyncComponent(() => import('./l5/core/L5TabDisclosureSoe.vue'))

// Amortization
const L5TabAmortization = defineAsyncComponent(() => import('./l5/amortization/L5TabAmortization.vue'))

// Inspection
const L5TabRelatedParty = defineAsyncComponent(() => import('./l5/inspection/L5TabRelatedParty.vue'))
const L5TabLtPayableCheck = defineAsyncComponent(() => import('./l5/inspection/L5TabLtPayableCheck.vue'))

// Shared
const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtReviewDialog = defineAsyncComponent(() => import('@/components/collaboration/GtReviewDialog.vue'))

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
  (e: 'navigate', sheetName: string): void
}>()

/**
 * L5TabIndex 目录行点击→通知外层 GtWpRenderer 切换 sheetName。
 */
function handleNavigate(sheetName: string) {
  parentEmit('navigate', sheetName)
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
 * GtWpRenderer 传入完整 sheet_name（如"审定表L5-1"），
 * 正则提取末尾编码（L5/L5A/L5-1~L5-7）来匹配子组件。
 */
const currentSheet = computed(() => {
  const name = props.sheetName || 'L5'
  // 提取末尾的L5编码（L5/L5A/L5-1~L5-7）
  const match = name.match(/L5(?:-\d+)?[A-Z]?$|L5$/)
  if (match) return match[0]
  // 附注特殊匹配
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企')) return '附注国企'
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

// ─── 版本追踪 useVersionTrail (autoSnapshot) ────────────────────────────────

const versionTrail = useVersionTrail({
  projectId: toRef(props, 'projectId') as any,
  workpaperId: toRef(props, 'wpId') as any,
})

provide('versionTrail', versionTrail)

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
    console.warn('[GtL5LongTermPayables] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.l5-long-term-payables {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
