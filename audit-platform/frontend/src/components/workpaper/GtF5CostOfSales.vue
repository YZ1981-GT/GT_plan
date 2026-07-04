<template>
  <div class="f5-cost-of-sales">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div class="f5-cost-of-sales-toolbar">
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
      </div>

      <GtOnlyOfficeSheet
        v-if="currentSheet === 'F5A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <CycleTabAdjudication
        v-else-if="adjudicationConfig"
        :config="adjudicationConfig"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
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

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import { useF5CosSalFormData } from './composables/useF5CosSalFormData'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import CycleTabAdjudication from './shared/CycleTabAdjudication.vue'
import CycleImportExportDropdown from './shared/CycleImportExportDropdown.vue'
import { getAdjudicationConfig } from './shared/cycleAdjudicationConfigs'
import { isImportExportSheet, resolveImportExportSheet } from './shared/cycleImportExportRegistry'

const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
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
const wpIdRef = computed(() => props.wpId)
const formData = useF5CosSalFormData({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const isReadonly = computed(() => !!props.readonly)
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const { versionTrailRef } = versionToolbar

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/附注披露/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(F5A|F5-\d+)/)
  return m ? m[1] : ''
})

const adjudicationConfig = computed(() => getAdjudicationConfig(currentSheet.value))
const importExportCtx = computed(() =>
  isImportExportSheet('f5', currentSheet.value)
    ? resolveImportExportSheet('f5', currentSheet.value)
    : null,
)
const useGridFallback = computed(() => {
  const code = currentSheet.value
  return !!code && code !== 'F5A' && !adjudicationConfig.value && !code.startsWith('附注')
})

async function onImported() {
  await formData.loadAll()
}

provide('reloadWorkpaperData', () => formData.loadAll())

onMounted(async () => { await formData.loadAll(); isLoading.value = false })
</script>

<style scoped>
.f5-cost-of-sales { padding: 12px; }
.loading-container { padding: 24px; }
.f5-cost-of-sales-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
