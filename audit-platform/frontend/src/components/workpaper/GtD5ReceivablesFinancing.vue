<template>
  <div class="d5-receivables-financing">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- 程序表 D5A -->
      <D5TabProcedure
        v-if="currentSheet === 'D5A' || currentSheet === 'D5'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
      />
      <!-- 审定表 D5-1 -->
      <D5TabAdjudication
        v-else-if="currentSheet === 'D5-1'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
      />
      <!-- 明细表 D5-2 -->
      <D5TabDetail
        v-else-if="currentSheet === 'D5-2'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
      />
      <!-- 调整分录 D5-3 -->
      <D5TabAdjustment
        v-else-if="currentSheet === 'D5-3'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
      />
      <!-- 公允价值测算 D5-4 -->
      <D5TabFairValue
        v-else-if="currentSheet === 'D5-4'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
        :period-end="periodEnd"
        :default-discount-rate="defaultDiscountRate"
      />
      <!-- 附注披露（上市） -->
      <D5TabDisclosure
        v-else-if="currentSheet === '附注上市' || currentSheet === '附注（上市）' || currentSheet === '附注披露'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
      />
      <!-- 附注披露（国企） -->
      <D5TabDisclosure
        v-else-if="currentSheet === '附注国企' || currentSheet === '附注（国企）'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
      />
      <!-- Fallback: 默认显示审定表 -->
      <D5TabAdjudication
        v-else
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtD5ReceivablesFinancing.vue — D5 应收款项融资底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，按 v-if 分发到对应子组件。
 * 不再使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目：1124 应收款项融资（借方/资产类/FVOCI）
 * selfLoad: htmlData 为 null 时自行调 render-config
 */
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import { useD5FormData } from './composables/useD5FormData'
import { useD5CrossSheet } from './composables/useD5CrossSheet'
import { parseNum } from './composables/useD5FormulaEngine'

// ─── Lazy Sub-Components ─────────────────────────────────────────────────────

const D5TabProcedure = defineAsyncComponent(() => import('./d5/D5TabProcedure.vue'))
const D5TabAdjudication = defineAsyncComponent(() => import('./d5/D5TabAdjudication.vue'))
const D5TabDetail = defineAsyncComponent(() => import('./d5/D5TabDetail.vue'))
const D5TabAdjustment = defineAsyncComponent(() => import('./d5/D5TabAdjustment.vue'))
const D5TabFairValue = defineAsyncComponent(() => import('./d5/D5TabFairValue.vue'))
const D5TabDisclosure = defineAsyncComponent(() => import('./d5/D5TabDisclosure.vue'))

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

defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── State ───────────────────────────────────────────────────────────────────

const isReadonly = computed(() => !!props.readonly)
const wpId = computed(() => props.wpId)
const projectId = computed(() => props.projectId)

/** 当前激活的 sheet（由外层 GtWpRenderer 通过 sheetName prop 控制）。
 * GtWpRenderer 传入完整 sheet_name（如"应收款项融资审定表D5-1"），
 * 需提取编码部分来匹配子组件。 */
const currentSheet = computed(() => {
  const name = props.sheetName || 'D5-1'
  // 提取末尾 D5 编码（D5/D5A/D5-1~D5-4）
  const match = name.match(/D5(?:-\d+)?[A-Z]?$|D5$/)
  if (match) return match[0]
  // 附注特殊匹配
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企')) return '附注国企'
  return name
})

// ─── Composables ─────────────────────────────────────────────────────────────

const {
  allResponses,
  isLoading,
  loadAll,
  saveImmediate,
  debouncedSave,
} = useD5FormData({ wpId, projectId })

const crossSheet = useD5CrossSheet({ allResponses })

// ─── Derived: periodEnd / defaultDiscountRate ────────────────────────────────

const periodEnd = computed(() => {
  const fromHtml = props.htmlData?.project_context?.period_end
  if (fromHtml) return fromHtml
  return props.year ? `${props.year}-12-31` : '2025-12-31'
})

const defaultDiscountRate = computed(() => {
  const resp = allResponses.value.get('D5-4-default-rate')
  return parseNum(resp?.remark)
})

// ─── Provide openReviewDialog ────────────────────────────────────────────────

function openReviewDialog(sectionId: string): void {
  console.log('[D5] openReviewDialog:', sectionId)
}

provide('openReviewDialog', openReviewDialog)

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
})
</script>

<style scoped>
.d5-receivables-financing {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
