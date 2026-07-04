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
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, defineAsyncComponent } from 'vue'
import { useG1TraFinFormData } from './composables/useG1TraFinFormData'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import G1TabAdjudication from './g1-trading-financial-assets/core/G1TabAdjudication.vue'
import G1TabFairValueTest from './g1-trading-financial-assets/valuation/G1TabFairValueTest.vue'
import G1TabDetail from './g1-trading-financial-assets/core/G1TabDetail.vue'

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
const formData = useG1TraFinFormData({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const isReadonly = computed(() => !!props.readonly)

const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const { versionTrailRef } = versionToolbar

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/附注披露\s*\(\s*上市\s*\)/.test(name) || name.includes('附注披露(上市)')) return '附注上市'
  if (/附注披露\s*\(\s*国企\s*\)/.test(name) || name.includes('附注披露(国企)')) return '附注国企'
  const m = name.match(/(G1A|G1-\d+)/)
  return m ? m[1] : ''
})

const MIGRATED_SHEETS = new Set(['G1-1', 'G1-2', 'G1-6'])

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
