<template>
  <div class="g5-long-term-receivable">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>
    <template v-else>
      <!-- 双模式切换 -->
      <div class="g5-long-term-receivable-toolbar">
        <el-segmented v-model="viewMode" :options="viewModeOptions" size="small" />
        <el-button size="small" @click="showVersionHistory">版本历史</el-button>
      </div>

      <!-- OnlyOffice 模式 -->
      <GtOnlyOfficeSheet
        v-if="viewMode === 'OO'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- HTML 模式：sheetName v-if dispatch -->
      <template v-else>
        <G5TabProcedure
          v-if="currentSheet === 'G5A'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabAdjudication
          v-else-if="currentSheet === 'G5-1'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabBalanceDetail
          v-else-if="currentSheet === 'G5-2'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabBadDebtDetail
          v-else-if="currentSheet === 'G5-3'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabAdjustment
          v-else-if="currentSheet === 'G5-4'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabLeaseAmortization
          v-else-if="currentSheet === 'G5-5'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabInstallmentSales
          v-else-if="currentSheet === 'G5-6'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabFactoringCheck
          v-else-if="currentSheet === 'G5-7'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabEclPolicy
          v-else-if="currentSheet === 'G5-8'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabStageClassification
          v-else-if="currentSheet === 'G5-9'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :is-readonly="isReadonly"
        />
        <G5TabImpairmentCalc
          v-else-if="currentSheet === 'G5-10'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :is-readonly="isReadonly"
        />
        <G5TabReversalWriteoff
          v-else-if="currentSheet === 'G5-11'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabVoucherCheck
          v-else-if="currentSheet === 'G5-12'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabDisclosureSOE
          v-else-if="currentSheet === '附注国企'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <G5TabDirectory
          v-else-if="currentSheet === '底稿目录'"
          :html-data="sheetData" :wp-id="props.wpId"
          :project-id="props.projectId" :readonly="isReadonly"
        />
        <!-- 未匹配 → OnlyOffice fallback -->
        <GtOnlyOfficeSheet
          v-else
          :wp-id="props.wpId" :project-id="props.projectId"
          :sheet-name="props.sheetName || ''" :readonly="isReadonly"
          style="height: calc(100vh - 180px)"
        />
      </template>

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, defineAsyncComponent, provide } from 'vue'
import { useG5FormData } from './composables/useG5FormData'
import { useG5DualMode } from './composables/useG5DualMode'
import { useVersionTrail } from '@/composables/useVersionTrail'

// ═══ defineAsyncComponent × 16 lazy load ═══
// core/
const G5TabProcedure = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabProcedure.vue'))
const G5TabAdjudication = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabAdjudication.vue'))
const G5TabBalanceDetail = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabBalanceDetail.vue'))
const G5TabBadDebtDetail = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabBadDebtDetail.vue'))
const G5TabAdjustment = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabAdjustment.vue'))
const G5TabDisclosureListed = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabDisclosureListed.vue'))
const G5TabDisclosureSOE = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabDisclosureSOE.vue'))
const G5TabDirectory = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabDirectory.vue'))
// measurement/
const G5TabLeaseAmortization = defineAsyncComponent(() => import('./g5-long-term-receivable/measurement/G5TabLeaseAmortization.vue'))
const G5TabInstallmentSales = defineAsyncComponent(() => import('./g5-long-term-receivable/measurement/G5TabInstallmentSales.vue'))
const G5TabFactoringCheck = defineAsyncComponent(() => import('./g5-long-term-receivable/measurement/G5TabFactoringCheck.vue'))
const G5TabEclPolicy = defineAsyncComponent(() => import('./g5-long-term-receivable/measurement/G5TabEclPolicy.vue'))
// impairment/
const G5TabStageClassification = defineAsyncComponent(() => import('./g5-long-term-receivable/impairment/G5TabStageClassification.vue'))
const G5TabImpairmentCalc = defineAsyncComponent(() => import('./g5-long-term-receivable/impairment/G5TabImpairmentCalc.vue'))
const G5TabReversalWriteoff = defineAsyncComponent(() => import('./g5-long-term-receivable/impairment/G5TabReversalWriteoff.vue'))
// voucher/
const G5TabVoucherCheck = defineAsyncComponent(() => import('./g5-long-term-receivable/voucher/G5TabVoucherCheck.vue'))
// shared
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}>()

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)
const versionTrailRef = ref()

// ═══ sheetName 正则提取编码 ═══
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/底稿目录/.test(name)) return '底稿目录'
  if (/附注披露/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(G5A|G5-1[0-2]|G5-[1-9])/)
  return m ? m[1] : ''
})

// ═══ 双模式 ═══
const { viewMode, viewModeOptions } = useG5DualMode()

// ═══ selfLoad: htmlData 为 null 时自行调用 render-config ═══
const formData = useG5FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  htmlData: computed(() => props.htmlData),
})
const sheetData = computed(() => props.htmlData || formData.data.value)

// ═══ 版本链集成 ═══
const { autoSnapshot } = useVersionTrail(computed(() => props.wpId))
function showVersionHistory() {
  versionTrailRef.value?.open?.()
}

// ═══ 复核对话 provide ═══
function openReviewDialog(sectionId: string): void {
  console.log('[G5] openReviewDialog:', sectionId)
}
provide('openReviewDialog', openReviewDialog)
provide('reloadWorkpaperData', () => formData.load())

onMounted(async () => {
  await formData.load()
  isLoading.value = false
})
</script>

<style scoped>
.g5-long-term-receivable { padding: 12px; }
.loading-container { padding: 24px; }
.g5-long-term-receivable-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
</style>
