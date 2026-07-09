<template>
  <div class="l8-financial-expenses">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- L8 主sheet 底稿目录 -->
      <L8TabIndex
        v-if="currentSheet === 'L8'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 L8A -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'L8A'"
        :wp-id="props.wpId"
        sheet-name="L8A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- L8-1 审定表（损益类！取发生额） -->
      <L8TabAdjudication
        v-else-if="currentSheet === 'L8-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L8-2 明细表（费用项目分析+区段Tab） -->
      <L8TabDetail
        v-else-if="currentSheet === 'L8-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L8-3 调整分录（借贷平衡） -->
      <L8TabAdjustment
        v-else-if="currentSheet === 'L8-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L8-4 非金融机构利息支出测算 -->
      <L8TabNonFinInterest
        v-else-if="currentSheet === 'L8-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L8-5 截止性测试（序时账±天数） -->
      <L8TabCutoffTest
        v-else-if="currentSheet === 'L8-5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L8-6 财务费用检查表 -->
      <L8TabFinExpenseCheck
        v-else-if="currentSheet === 'L8-6'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- 附注（上市/国企） -->
      <L8TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <L8TabDisclosureSoe
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
      :related-data="{ wpCode: 'L8', projectId: props.projectId }"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * GtL8FinancialExpenses.vue — L8 财务费用底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取末尾编码（L8/L8A/L8-1~L8-6），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：6603 财务费用（**损益类！取发生额**，从 tb_ledger 取本期借贷发生额）
 * 与 L1~L7 负债类根本不同：取本期发生额（借方发生-贷方发生），不是期末余额。
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated / adjustment:created
 * - 跨底稿联动: 接收 L1/L3/L4 利息测算 + L5 摊销 → L8 利息支出测算
 * - TB回写: 6603（发生额口径）
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, onMounted, provide, defineAsyncComponent, toRef } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import useVersionTrail from './composables/useVersionTrail'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const L8TabIndex = defineAsyncComponent(() => import('./l8/core/L8TabIndex.vue'))
const L8TabAdjudication = defineAsyncComponent(() => import('./l8/core/L8TabAdjudication.vue'))
const L8TabDetail = defineAsyncComponent(() => import('./l8/core/L8TabDetail.vue'))
const L8TabAdjustment = defineAsyncComponent(() => import('./l8/core/L8TabAdjustment.vue'))
const L8TabDisclosureListed = defineAsyncComponent(() => import('./l8/core/L8TabDisclosureListed.vue'))
const L8TabDisclosureSoe = defineAsyncComponent(() => import('./l8/core/L8TabDisclosureSoe.vue'))

// Interest
const L8TabNonFinInterest = defineAsyncComponent(() => import('./l8/interest/L8TabNonFinInterest.vue'))

// Cutoff
const L8TabCutoffTest = defineAsyncComponent(() => import('./l8/cutoff/L8TabCutoffTest.vue'))

// Inspection
const L8TabFinExpenseCheck = defineAsyncComponent(() => import('./l8/inspection/L8TabFinExpenseCheck.vue'))

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
 * L8TabIndex 目录行点击→通知外层 GtWpRenderer 切换 sheetName。
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
 * GtWpRenderer 传入完整 sheet_name（如"审定表L8-1"），
 * 正则提取末尾编码（L8/L8A/L8-1~L8-6）来匹配子组件。
 */
const currentSheet = computed(() => {
  const name = props.sheetName || 'L8'
  // 提取末尾的L8编码（L8/L8A/L8-1~L8-6）
  const match = name.match(/L8(?:-\d+)?[A-Z]?$|L8$/)
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
    console.warn('[GtL8FinancialExpenses] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.l8-financial-expenses {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
