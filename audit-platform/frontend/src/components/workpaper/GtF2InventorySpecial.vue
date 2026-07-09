<template>
  <div class="f2-inventory-special">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="showHtmlToolbar" class="f2-spe-toolbar">
        <el-segmented
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
        <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
        <el-tag v-if="isIpoSheet && !formData.isIpoProject.value" size="small" type="info">IPO专项（当前项目不可见）</el-tag>
      </div>

      <el-alert
        v-if="externalAdjudicated.dataUpdatedVisible.value"
        title="关联审定数据已更新（科目 1405）"
        type="info"
        show-icon
        :closable="false"
        class="data-updated-bar"
      />

      <GtOnlyOfficeSheet
        v-if="dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <template v-else-if="showIpoBlocked">
        <el-empty description="此底稿仅适用于 IPO/上市/新三板/重组项目" />
      </template>

      <template v-else>
        <F2TabContractProcedure
          v-if="currentSheet === 'F2-55A'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <F2TabIpoProcedure
          v-else-if="currentSheet === 'F2-61A'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <F2TabContractCostDetail
          v-else-if="currentSheet === 'F2-55'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabContractCostCheck
          v-else-if="currentSheet === 'F2-56'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :audit-year="auditYear"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabImpairment
          v-else-if="currentSheet === 'F2-57'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabLossContract
          v-else-if="currentSheet === 'F2-58'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabPurchasePrice
          v-else-if="currentSheet === 'F2-61'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabUnitPrice
          v-else-if="currentSheet === 'F2-62'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabCapacityEnergy
          v-else-if="currentSheet === 'F2-63'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabUnitConsumption
          v-else-if="currentSheet === 'F2-64'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabRelatedPartyInquiry
          v-else-if="currentSheet === 'F2-65'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabRelatedPartyMarket
          v-else-if="currentSheet === 'F2-66'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabUndisclosedParty
          v-else-if="currentSheet === 'F2-67'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabSupplierStructure
          v-else-if="currentSheet === 'F2-68'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabSupplierChecklist
          v-else-if="currentSheet === 'F2-69'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabInterviewSummary
          v-else-if="currentSheet === 'F2-71'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabSupplierInfoCheck
          v-else-if="currentSheet === 'F2-70'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F2TabInterviewDetail
          v-else-if="currentSheet === 'F2-72'"
          :wp-id="props.wpId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <GtGridSheet
          v-else-if="useGridFallback"
          :html-data="props.htmlData || formData.getSheet(currentSheet)"
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
      </template>

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />

      <GtWpReviewDialogHost />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, provide, toRef, defineAsyncComponent } from 'vue'
import { useF2SpecialFormData, type ChecklistResponse } from './composables/useF2SpecialFormData'
import { useF2SpecialDualMode } from './composables/useF2SpecialDualMode'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import { useF2ReviewDialogProvide } from './composables/useF2ReviewDialogProvide'
import { useF2SpeExternalAdjudicated } from './composables/useF2SpeExternalAdjudicated'

// defineAsyncComponent lazy loading — 首屏仅加载当前 sheet 组件（对齐D4标准）
const F2TabContractProcedure = defineAsyncComponent(() => import('./f2-special/contract/F2TabContractProcedure.vue'))
const F2TabContractCostDetail = defineAsyncComponent(() => import('./f2-special/contract/F2TabContractCostDetail.vue'))
const F2TabContractCostCheck = defineAsyncComponent(() => import('./f2-special/contract/F2TabContractCostCheck.vue'))
const F2TabImpairment = defineAsyncComponent(() => import('./f2-special/contract/F2TabImpairment.vue'))
const F2TabLossContract = defineAsyncComponent(() => import('./f2-special/contract/F2TabLossContract.vue'))
const F2TabIpoProcedure = defineAsyncComponent(() => import('./f2-special/ipo/F2TabIpoProcedure.vue'))
const F2TabPurchasePrice = defineAsyncComponent(() => import('./f2-special/ipo/F2TabPurchasePrice.vue'))
const F2TabUnitPrice = defineAsyncComponent(() => import('./f2-special/ipo/F2TabUnitPrice.vue'))
const F2TabCapacityEnergy = defineAsyncComponent(() => import('./f2-special/ipo/F2TabCapacityEnergy.vue'))
const F2TabUnitConsumption = defineAsyncComponent(() => import('./f2-special/ipo/F2TabUnitConsumption.vue'))
const F2TabRelatedPartyInquiry = defineAsyncComponent(() => import('./f2-special/ipo/F2TabRelatedPartyInquiry.vue'))
const F2TabRelatedPartyMarket = defineAsyncComponent(() => import('./f2-special/ipo/F2TabRelatedPartyMarket.vue'))
const F2TabUndisclosedParty = defineAsyncComponent(() => import('./f2-special/ipo/F2TabUndisclosedParty.vue'))
const F2TabSupplierStructure = defineAsyncComponent(() => import('./f2-special/ipo/F2TabSupplierStructure.vue'))
const F2TabSupplierChecklist = defineAsyncComponent(() => import('./f2-special/ipo/F2TabSupplierChecklist.vue'))
const F2TabInterviewSummary = defineAsyncComponent(() => import('./f2-special/ipo/F2TabInterviewSummary.vue'))
const F2TabSupplierInfoCheck = defineAsyncComponent(() => import('./f2-special/ipo/F2TabSupplierInfoCheck.vue'))
const F2TabInterviewDetail = defineAsyncComponent(() => import('./f2-special/ipo/F2TabInterviewDetail.vue'))

const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const GtWpReviewDialogHost = defineAsyncComponent(() => import('./GtWpReviewDialogHost.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}>()

const CONTRACT_HTML = ['F2-55A', 'F2-55', 'F2-56', 'F2-57', 'F2-58']
const IPO_HTML = [
  'F2-61A',
  'F2-61', 'F2-62', 'F2-63', 'F2-64', 'F2-65', 'F2-66', 'F2-67', 'F2-68', 'F2-69', 'F2-71',
  'F2-70', 'F2-72',
]

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

const formData = useF2SpecialFormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const allResponses = computed(() => formData.allResponses.value)

const versionToolbar = useWorkpaperVersionToolbar({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})
const { versionTrailRef } = versionToolbar

const dualMode = useF2SpecialDualMode({
  wpId: toRef(props, 'wpId'),
  reloadAll: () => formData.loadAll(),
})

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  const m = name.match(/(F2A|F2-\d+[A-Z]?)/)
  return m ? m[1] : ''
})

const auditYear = computed(() => {
  const d = formData.projectContext.value?.audit_period_end
    || formData.projectContext.value?.bs_date || ''
  if (d.length >= 4) return parseInt(d.slice(0, 4), 10)
  return new Date().getFullYear() - 1
})

const isIpoSheet = computed(() => IPO_HTML.includes(currentSheet.value))

const showIpoBlocked = computed(() =>
  isIpoSheet.value && !formData.isIpoProject.value && dualMode.currentMode.value === 'html',
)

const isHtmlSheet = computed(() => {
  const c = currentSheet.value
  if (CONTRACT_HTML.includes(c)) return true
  if (IPO_HTML.includes(c) && formData.isIpoProject.value) return true
  return false
})

const showHtmlToolbar = computed(() => isHtmlSheet.value)

const useGridFallback = computed(() => {
  const code = currentSheet.value
  return code && !isHtmlSheet.value && !showIpoBlocked.value
})

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')
useF2ReviewDialogProvide({ wpId: wpIdRef, projectId: projectIdRef })

const externalAdjudicated = useF2SpeExternalAdjudicated({
  onRefresh: () => formData.loadAll(),
})

provide('reloadWorkpaperData', () => formData.loadAll())

async function handleF2SpeSaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    await formData.saveItemsFromEvent(items)
    versionToolbar.scheduleAutoSnapshot()
  }
}

async function selfLoad(): Promise<void> {
  try {
    await formData.loadAll()
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  window.addEventListener('f2-spe:save-items', handleF2SpeSaveItems)
  void selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('f2-spe:save-items', handleF2SpeSaveItems)
})
</script>

<style scoped>
.f2-inventory-special { padding: 12px; }
.loading-container { padding: 24px; }
.f2-spe-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.data-updated-bar { margin-bottom: 8px; }
</style>
