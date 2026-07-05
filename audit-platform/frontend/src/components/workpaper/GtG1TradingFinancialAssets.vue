<template>
  <div class="g1-trading-financial-assets">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div class="g1-toolbar">
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
      </div>

      <GtOnlyOfficeSheet
        v-if="currentSheet === 'G1A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <G1TabAdjudication
        v-else-if="currentSheet === 'G1-1'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabFairValueTest
        v-else-if="currentSheet === 'G1-6'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabDetail
        v-else-if="currentSheet === 'G1-2'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabAdjustment
        v-else-if="currentSheet === 'G1-3'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabLevel3Reconciliation
        v-else-if="currentSheet === 'G1-7'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabBusinessModel
        v-else-if="currentSheet === 'G1-8'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabClassification
        v-else-if="currentSheet === 'G1-9'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabContractCashflow
        v-else-if="currentSheet === 'G1-10'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabInventory
        v-else-if="currentSheet === 'G1-4'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabIncomeCalc
        v-else-if="currentSheet === 'G1-5'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabSecuritiesCount
        v-else-if="currentSheet === 'G1-11'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabCountReconciliation
        v-else-if="currentSheet === 'G1-12'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G1TabVoucherCheck
        v-else-if="currentSheet === 'G1-13'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
      />

      <G1TabDerivativeCheck
        v-else-if="currentSheet === 'G1-14'"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <GtGridSheet
        v-else-if="useGridFallback"
        :html-data="props.htmlData || formData.getSheet(props.sheetName || currentSheet)"
        :readonly="isReadonly"
      />

      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <GtWpVersionTrail
        ref="versionTrailRef"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
      />

      <!-- 复核对话（供子组件 inject('openReviewDialog') 触发）-->
      <GtReviewDialog
        v-if="reviewDialog.isOpen.value && reviewDialog.activationParams.value"
        :key="reviewDialog.activationParams.value.sectionId"
        v-bind="reviewDialog.activationParams.value"
        @closed="reviewDialog.closeReviewDialog"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, defineAsyncComponent } from 'vue'
import { useG1TraFinFormData } from './composables/useG1TraFinFormData'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import { useG1ReviewDialogProvide } from './composables/useG1ReviewDialogProvide'
import G1TabAdjudication from './g1-trading-financial-assets/core/G1TabAdjudication.vue'
import G1TabFairValueTest from './g1-trading-financial-assets/valuation/G1TabFairValueTest.vue'
import G1TabDetail from './g1-trading-financial-assets/core/G1TabDetail.vue'

const G1TabAdjustment = defineAsyncComponent(() => import('./g1-trading-financial-assets/core/G1TabAdjustment.vue'))
const G1TabDisclosureListed = defineAsyncComponent(() => import('./g1-trading-financial-assets/core/G1TabDisclosureListed.vue'))
const G1TabDisclosureSOE = defineAsyncComponent(() => import('./g1-trading-financial-assets/core/G1TabDisclosureSOE.vue'))
const G1TabLevel3Reconciliation = defineAsyncComponent(() => import('./g1-trading-financial-assets/valuation/G1TabLevel3Reconciliation.vue'))
const G1TabBusinessModel = defineAsyncComponent(() => import('./g1-trading-financial-assets/classification/G1TabBusinessModel.vue'))
const G1TabClassification = defineAsyncComponent(() => import('./g1-trading-financial-assets/classification/G1TabClassification.vue'))
const G1TabContractCashflow = defineAsyncComponent(() => import('./g1-trading-financial-assets/classification/G1TabContractCashflow.vue'))
const G1TabInventory = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabInventory.vue'))
const G1TabIncomeCalc = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabIncomeCalc.vue'))
const G1TabSecuritiesCount = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabSecuritiesCount.vue'))
const G1TabCountReconciliation = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabCountReconciliation.vue'))
const G1TabVoucherCheck = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabVoucherCheck.vue'))
const G1TabDerivativeCheck = defineAsyncComponent(() => import('./g1-trading-financial-assets/inspection/G1TabDerivativeCheck.vue'))

const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const GtReviewDialog = defineAsyncComponent(() => import('@/components/collaboration/GtReviewDialog.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const isReadonly = computed(() => !!props.readonly)

const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const { versionTrailRef } = versionToolbar

// autoSnapshot on save：子组件 debouncedSave → 持久化后触发版本快照（debounce）
const formData = useG1TraFinFormData({
  wpId: wpIdRef,
  projectId: computed(() => props.projectId),
  onAfterSave: () => versionToolbar.scheduleAutoSnapshot(),
})

// ─── 复核对话 provide（供子组件 section 标题栏复核按钮 inject('openReviewDialog')）───
const reviewDialog = useG1ReviewDialogProvide({ wpId: wpIdRef, projectId: computed(() => props.projectId) })

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/附注披露\s*\(\s*上市\s*\)/.test(name) || name.includes('附注披露(上市)')) return '附注上市'
  if (/附注披露\s*\(\s*国企\s*\)/.test(name) || name.includes('附注披露(国企)')) return '附注国企'
  const m = name.match(/(G1A|G1-\d+)/)
  return m ? m[1] : ''
})

const MIGRATED_SHEETS = new Set([
  'G1-1', 'G1-2', 'G1-3', 'G1-4', 'G1-5', 'G1-6', 'G1-7',
  'G1-8', 'G1-9', 'G1-10', 'G1-11', 'G1-12', 'G1-13', 'G1-14',
])

const useGridFallback = computed(() => {
  const code = currentSheet.value
  return !!code && code !== 'G1A' && !MIGRATED_SHEETS.has(code) && !code.startsWith('附注')
})

async function selfLoad() {
  await formData.loadAll()
  isLoading.value = false
}

onMounted(() => { void selfLoad() })
</script>

<style scoped>
.g1-trading-financial-assets { padding: 12px; }
.loading-container { padding: 24px; }
.g1-toolbar { margin-bottom: 8px; }
</style>
