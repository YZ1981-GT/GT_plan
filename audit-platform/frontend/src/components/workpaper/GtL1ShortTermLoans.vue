<template>
  <div class="l1-short-term-loans">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <div v-if="isProcedureSheet" class="l1-procedure-toolbar">
        <el-segmented
          v-model="procedureDualMode.currentMode.value"
          :options="procedureDualMode.modeOptions.value"
          size="small"
          @change="procedureDualMode.onModeChange"
        />
        <el-tag v-if="!procedureDualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="isProcedureSheet && procedureDualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || 'L1A'"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- L1 主sheet 底稿目录 -->
      <L1TabIndex
        v-else-if="currentSheet === 'L1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 L1A -->
      <CycleTabProcedure
        v-else-if="currentSheet === 'L1A'"
        sheet-code="L1A"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L1-1 审定表 -->
      <L1TabAdjudication
        v-else-if="currentSheet === 'L1-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L1-2 明细表 -->
      <L1TabDetail
        v-else-if="currentSheet === 'L1-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L1-3 调整分录 -->
      <L1TabAdjustment
        v-else-if="currentSheet === 'L1-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L1-4 征信报告核对 -->
      <L1TabCreditCheck
        v-else-if="currentSheet === 'L1-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L1-5 利息测算表（核心！联动L2/L8） -->
      <L1TabInterestCalc
        v-else-if="currentSheet === 'L1-5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L1-6 贷款合同检查 -->
      <L1TabContractCheck
        v-else-if="currentSheet === 'L1-6'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L1-7 逾期贷款检查 -->
      <L1TabOverdueCheck
        v-else-if="currentSheet === 'L1-7'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L1-8 抵质押资产检查 -->
      <L1TabPledgeCheck
        v-else-if="currentSheet === 'L1-8'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- L1-9 短期借款检查表 -->
      <L1TabStLoanCheck
        v-else-if="currentSheet === 'L1-9'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注（上市/国企） -->
      <L1TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <L1TabDisclosureSoe
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

    <GtWpReviewDialogHost />

    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
  </div>
</template>

<script setup lang="ts">
/**
 * GtL1ShortTermLoans.vue — L1 短期借款底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取末尾编码（L1/L1-1~L1-9/L1A），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：2001 短期借款（贷方/负债类！期末=期初+贷方-借方）
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated / l1:interest-calculated / adjustment:created
 * - 跨底稿联动: publishInterestCalculated provide → L1-5 inject
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, onMounted, provide, defineAsyncComponent, toRef } from 'vue'
import http from '@/utils/http'
import { useL1FormData } from '@/composables/useL1FormData'
import { useL1Adjudication } from '@/composables/useL1Adjudication'
import { useL1CrossSheet } from '@/composables/useL1CrossSheet'
import { useCycleHtmlOoDualMode } from './composables/useCycleHtmlOoDualMode'
import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const L1TabIndex = defineAsyncComponent(() => import('./l1/core/L1TabIndex.vue'))
const L1TabAdjudication = defineAsyncComponent(() => import('./l1/core/L1TabAdjudication.vue'))
const L1TabDetail = defineAsyncComponent(() => import('./l1/core/L1TabDetail.vue'))
const L1TabAdjustment = defineAsyncComponent(() => import('./l1/core/L1TabAdjustment.vue'))
const L1TabDisclosureListed = defineAsyncComponent(() => import('./l1/core/L1TabDisclosureListed.vue'))
const L1TabDisclosureSoe = defineAsyncComponent(() => import('./l1/core/L1TabDisclosureSoe.vue'))

// Interest
const L1TabInterestCalc = defineAsyncComponent(() => import('./l1/interest/L1TabInterestCalc.vue'))

// Inspection
const L1TabCreditCheck = defineAsyncComponent(() => import('./l1/inspection/L1TabCreditCheck.vue'))
const L1TabContractCheck = defineAsyncComponent(() => import('./l1/inspection/L1TabContractCheck.vue'))
const L1TabOverdueCheck = defineAsyncComponent(() => import('./l1/inspection/L1TabOverdueCheck.vue'))
const L1TabPledgeCheck = defineAsyncComponent(() => import('./l1/inspection/L1TabPledgeCheck.vue'))
const L1TabStLoanCheck = defineAsyncComponent(() => import('./l1/inspection/L1TabStLoanCheck.vue'))

// Shared
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const GtWpReviewDialogHost = defineAsyncComponent(() => import('./GtWpReviewDialogHost.vue'))

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
 * L1TabIndex 目录行点击/子组件"返回目录"→通知外层 GtWpRenderer 切换 sheetName。
 * 外层 GtWpRenderer 监听 @navigate-sheet（对齐 K1 范式），此处 emit 向上传递请求。
 */
function handleNavigate(sheetName: string) {
  parentEmit('navigate-sheet', sheetName)
}

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

// ─── FormData (provide/inject pattern for child components) ──────────────────

const formData = useL1FormData(
  toRef(props, 'wpId') as any,
  toRef(props, 'projectId') as any,
  isReadonly,
)

provide('l1FormData', formData)

// ─── CrossSheet Engine (for 勾稽校验 inject) ─────────────────────────────────

const crossSheet = useL1CrossSheet(
  formData.adjudicationData,
  formData.detailRows,
  formData.interestCalcRows,
  formData.creditCheckRows,
  'L1',
)

provide('adjudicationVsDetail', crossSheet.adjudicationVsDetail)

// ─── Provide publishInterestCalculated → L1-5 inject ─────────────────────────

provide('publishInterestCalculated', crossSheet.publishInterestCalculated)

/**
 * 当前激活的 sheet（由外层 GtWpRenderer 通过 sheetName prop 控制）。
 * GtWpRenderer 传入完整 sheet_name（如"审定表L1-1"），
 * 正则提取末尾编码（L1/L1-1~L1-9/L1A）来匹配子组件。
 */
const currentSheet = computed(() => {
  const name = props.sheetName || 'L1'
  // 底稿目录 sheet → 显示 L1 底稿目录（对齐 K1）
  if (name.includes('底稿目录')) return 'L1'
  // 提取末尾的L1编码（L1/L1A/L1-1~L1-9）
  const match = name.match(/L1(?:-\d+)?[A-Z]?$|L1$/)
  if (match) return match[0]
  // 附注特殊匹配
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企')) return '附注国企'
  return name
})

const isProcedureSheet = computed(() => currentSheet.value === 'L1A')
const procedureDualMode = useCycleHtmlOoDualMode({
  wpId: toRef(props, 'wpId') as any,
  storagePrefix: 'l1-proc:',
})

// ─── Provide openReviewDialog ────────────────────────────────────────────────
useWorkpaperReviewProvide({
  wpId: toRef(props, 'wpId') as any,
  projectId: toRef(props, 'projectId') as any,
})

// ─── 版本追踪 useWorkpaperVersionToolbar (autoSnapshot on save) ──────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef, openVersionHistory, scheduleAutoSnapshot } = versionToolbar

provide('versionTrail', versionToolbar)
provide('l1VersionTrailRef', versionTrailRef)
provide('l1OpenVersionHistory', openVersionHistory)

// ─── selfLoad ────────────────────────────────────────────────────────────────

async function selfLoad() {
  if (props.htmlData) {
    // 从 props 提供的数据初始化
    isLoading.value = false
    // 仍需从 checklist_responses 加载结构化数据
    await formData.selfLoad()
    return
  }

  // 当 htmlData 为空时（bundle 内嵌场景），自行加载 render-config
  try {
    await http.get(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
  } catch (err) {
    console.warn('[GtL1ShortTermLoans] selfLoad failed:', err)
  }

  // 加载 checklist_responses 到结构化 state
  await formData.selfLoad()
  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.l1-short-term-loans {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.l1-procedure-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
</style>
