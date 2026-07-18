<template>
  <div class="f4-accounts-payable">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="showHtmlToolbar" class="f4-accounts-payable-toolbar">
        <el-segmented
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <CycleImportExportDropdown
          v-if="importExportCtx"
          :wp-id="props.wpId"
          :api-prefix="importExportCtx.apiPrefix"
          :sheet="importExportCtx.sheet"
          :variants="importExportCtx.variants"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
        <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <template v-else>
        <CycleTabProcedure
          v-if="currentSheet === 'F4A'"
          sheet-code="F4A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <F4TabAdjudication
          v-else-if="currentSheet === 'F4-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F4TabDetail
          v-else-if="currentSheet === 'F4-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F4TabAdjustment
          v-else-if="currentSheet === 'F4-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F4TabSubstantiveAnalysis
          v-else-if="currentSheet === 'F4-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F4TabLongOutstanding
          v-else-if="currentSheet === 'F4-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F4TabRelatedParty
          v-else-if="currentSheet === 'F4-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F4TabUnrecordedCheck
          v-else-if="currentSheet === 'F4-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F4TabVoucherCheck
          v-else-if="currentSheet === 'F4-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="auditYear"
        />

        <F4TabSupplierFinancing
          v-else-if="currentSheet === 'F4-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F4TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <F4TabDisclosureSOE
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
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
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtF4AccountsPayable.vue — F4 应付账款底稿主入口
 *
 * 比照 GtF3NotesPayable：外层 GtWpRenderer 通过 sheetName 分发，无内层 el-tabs。
 * Spec: .kiro/specs/f4-accounts-payable/ Task 1.1, 9.1
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { useF4FormData, type ChecklistResponse } from './composables/useF4FormData'
import { useF4DualMode } from './composables/useF4DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import CycleImportExportDropdown from './shared/CycleImportExportDropdown.vue'
import { isImportExportSheet, resolveImportExportSheet } from './shared/cycleImportExportRegistry'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const F4TabAdjudication = defineAsyncComponent(() => import('./f4-accounts-payable/F4TabAdjudication.vue'))
const F4TabDetail = defineAsyncComponent(() => import('./f4-accounts-payable/F4TabDetail.vue'))
const F4TabAdjustment = defineAsyncComponent(() => import('./f4-accounts-payable/F4TabAdjustment.vue'))
const F4TabSubstantiveAnalysis = defineAsyncComponent(() => import('./f4-accounts-payable/F4TabSubstantiveAnalysis.vue'))
const F4TabLongOutstanding = defineAsyncComponent(() => import('./f4-accounts-payable/F4TabLongOutstanding.vue'))
const F4TabRelatedParty = defineAsyncComponent(() => import('./f4-accounts-payable/F4TabRelatedParty.vue'))
const F4TabUnrecordedCheck = defineAsyncComponent(() => import('./f4-accounts-payable/F4TabUnrecordedCheck.vue'))
const F4TabVoucherCheck = defineAsyncComponent(() => import('./f4-accounts-payable/F4TabVoucherCheck.vue'))
const F4TabSupplierFinancing = defineAsyncComponent(() => import('./f4-accounts-payable/F4TabSupplierFinancing.vue'))
const F4TabDisclosureListed = defineAsyncComponent(() => import('./f4-accounts-payable/F4TabDisclosureListed.vue'))
const F4TabDisclosureSOE = defineAsyncComponent(() => import('./f4-accounts-payable/F4TabDisclosureSOE.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

defineEmits<{ (e: 'save'): void; (e: 'completed'): void }>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const formData = useF4FormData({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const isReadonly = computed(() => !!props.readonly)
const allResponses = computed(() => formData.allResponses.value)
const auditYear = computed(() => {
  if (props.year) return props.year
  const bs = formData.projectContext.value?.bs_date
  if (bs && String(bs).length >= 4) return parseInt(String(bs).slice(0, 4), 10)
  return new Date().getFullYear() - 1
})

const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionToolbar = runtime?.version ?? {
  versionTrailRef: ref<{ openDrawer: () => void } | null>(null),
  openVersionHistory: () => undefined,
  scheduleAutoSnapshot: () => undefined,
  wrapSaveImmediate: (<T,>(fn: T): T => fn),
}
const { versionTrailRef, openVersionHistory } = versionToolbar

provide('f4VersionTrailRef', versionTrailRef)
provide('f4OpenVersionHistory', openVersionHistory)

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/附注披露/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(F4A|F4-\d+)/)
  return m ? m[1] : ''
})

const showHtmlToolbar = computed(() => {
  const s = currentSheet.value
  return !!s && (s === 'F4A' || /^F4-\d+$/.test(s) || s.startsWith('附注'))
})

const dualMode = useF4DualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

const importExportCtx = computed(() =>
  isImportExportSheet('f4', currentSheet.value)
    ? resolveImportExportSheet('f4', currentSheet.value)
    : null,
)

async function onImported() {
  await formData.loadAll()
}

provide('reloadWorkpaperData', () => formData.loadAll())

async function handleF4SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    await formData.saveItemsFromEvent(items)
    versionToolbar.scheduleAutoSnapshot()
  }
}

function handleF4Writeback(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; auditedAmount: number }>).detail
  if (d?.accountCode != null && d.auditedAmount != null) {
    void formData.writebackTrialBalance(d.accountCode, d.auditedAmount)
  }
}

onMounted(async () => {
  window.addEventListener('f4:save-items', handleF4SaveItems)
  window.addEventListener('f4:writeback-trial-balance', handleF4Writeback)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('f4:save-items', handleF4SaveItems)
  window.removeEventListener('f4:writeback-trial-balance', handleF4Writeback)
})
</script>

<style scoped>
.f4-accounts-payable { padding: 12px; }
.loading-container { padding: 24px; }
.f4-accounts-payable-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
