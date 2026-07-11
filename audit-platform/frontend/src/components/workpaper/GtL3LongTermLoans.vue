<template>
  <div class="l3-long-term-loans">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- L3 主sheet 底稿目录 -->
      <L3TabIndex
        v-if="currentSheet === 'L3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 L3A -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'L3A'"
        :wp-id="props.wpId"
        sheet-name="L3A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- L3-1 审定表（负债类贷方+一年内到期列） -->
      <L3TabAdjudication
        v-else-if="currentSheet === 'L3-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L3-2 明细表（32列区段Tab+到期分类） -->
      <L3TabDetail
        v-else-if="currentSheet === 'L3-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @open-review="(s: string) => openReviewDialog(s)"
      />
      <!-- L3-3 调整分录（含重分类RJE） -->
      <L3TabAdjustment
        v-else-if="currentSheet === 'L3-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L3-4 征信报告核对 -->
      <L3TabCreditCheck
        v-else-if="currentSheet === 'L3-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L3-5 利息测算表（核心！联动L2/L8） -->
      <L3TabInterestCalc
        v-else-if="currentSheet === 'L3-5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L3-6 贷款合同检查（区段Tab+OCR） -->
      <L3TabContractCheck
        v-else-if="currentSheet === 'L3-6'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @open-review="(s: string) => openReviewDialog(s)"
      />
      <!-- L3-7 逾期贷款检查 -->
      <L3TabOverdueCheck
        v-else-if="currentSheet === 'L3-7'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L3-8 抵质押资产检查 -->
      <L3TabPledgeCheck
        v-else-if="currentSheet === 'L3-8'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L3-9 长期借款检查表 -->
      <L3TabLtLoanCheck
        v-else-if="currentSheet === 'L3-9'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @open-review="(s: string) => openReviewDialog(s)"
      />
      <!-- 附注（上市/国企） -->
      <L3TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <L3TabDisclosureSoe
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

    <!-- 复核对话组件（Phase 6.3） -->
    <GtReviewDialog
      v-if="reviewDialogVisible"
      :wp-id="props.wpId"
      :section-id="reviewDialogSectionId"
      :section-label="reviewDialogSectionLabel"
      :current-user="currentUser"
      :related-data="{ wpCode: 'L3', projectId: props.projectId }"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * GtL3LongTermLoans.vue — L3 长期借款底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取末尾编码（L3/L3-1~L3-9/L3A），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：2501 长期借款（贷方/负债类！期末=期初+贷方-借方）
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated / l3:interest-calculated / adjustment:created
 * - 跨底稿联动: publishInterestCalculated provide → L3-5 inject
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, onMounted, provide, defineAsyncComponent, toRef } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import useVersionTrail from './composables/useVersionTrail'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const L3TabIndex = defineAsyncComponent(() => import('./l3/core/L3TabIndex.vue'))
const L3TabAdjudication = defineAsyncComponent(() => import('./l3/core/L3TabAdjudication.vue'))
const L3TabDetail = defineAsyncComponent(() => import('./l3/core/L3TabDetail.vue'))
const L3TabAdjustment = defineAsyncComponent(() => import('./l3/core/L3TabAdjustment.vue'))
const L3TabDisclosureListed = defineAsyncComponent(() => import('./l3/core/L3TabDisclosureListed.vue'))
const L3TabDisclosureSoe = defineAsyncComponent(() => import('./l3/core/L3TabDisclosureSoe.vue'))

// Interest
const L3TabInterestCalc = defineAsyncComponent(() => import('./l3/interest/L3TabInterestCalc.vue'))

// Inspection
const L3TabCreditCheck = defineAsyncComponent(() => import('./l3/inspection/L3TabCreditCheck.vue'))
const L3TabContractCheck = defineAsyncComponent(() => import('./l3/inspection/L3TabContractCheck.vue'))
const L3TabOverdueCheck = defineAsyncComponent(() => import('./l3/inspection/L3TabOverdueCheck.vue'))
const L3TabPledgeCheck = defineAsyncComponent(() => import('./l3/inspection/L3TabPledgeCheck.vue'))
const L3TabLtLoanCheck = defineAsyncComponent(() => import('./l3/inspection/L3TabLtLoanCheck.vue'))

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
  (e: 'navigate-sheet', sheetName: string): void
}>()

/**
 * L3TabIndex 目录行点击/子组件"返回目录"→通知外层 GtWpRenderer 切换 sheetName。
 * 外层 GtWpRenderer 监听 @navigate-sheet（对齐 K1 范式），此处 emit 向上传递请求。
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
 * GtWpRenderer 传入完整 sheet_name（如"审定表L3-1"），
 * 正则提取末尾编码（L3/L3-1~L3-9/L3A）来匹配子组件。
 */
const currentSheet = computed(() => {
  const name = props.sheetName || 'L3'
  // 底稿目录 sheet → 显示 L3 底稿目录（对齐 K1）
  if (name.includes('底稿目录')) return 'L3'
  // 提取末尾的L3编码（L3/L3A/L3-1~L3-9）
  const match = name.match(/L3(?:-\d+)?[A-Z]?$|L3$/)
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
    console.warn('[GtL3LongTermLoans] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.l3-long-term-loans {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
