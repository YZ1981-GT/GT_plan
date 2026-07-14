<template>
  <div class="f4-accounts-payable">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div class="f4-accounts-payable-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
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
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <CycleTabProcedure
        v-else-if="currentSheet === 'F4A'"
        sheet-code="F4A"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
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

      <!-- 版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtF4AccountsPayable.vue — F4 应付账款底稿主入口
 *
 * Spec: .kiro/specs/f4-accounts-payable/ Task 1.1, 9.1
 * 集成：useWorkpaperVersionToolbar(autoSnapshot on save) + provide('openReviewDialog')
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { useF4AccPayFormData } from './composables/useF4AccPayFormData'
import { useF4DualMode } from './composables/useF4DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import CycleTabAdjudication from './shared/CycleTabAdjudication.vue'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import CycleImportExportDropdown from './shared/CycleImportExportDropdown.vue'
import { getAdjudicationConfig } from './shared/cycleAdjudicationConfigs'
import { isImportExportSheet, resolveImportExportSheet } from './shared/cycleImportExportRegistry'
import type { ChecklistResponse } from './composables/useF1FormData'

const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

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
const formData = useF4AccPayFormData({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const isReadonly = computed(() => !!props.readonly)
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供 ───
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

const adjudicationConfig = computed(() => getAdjudicationConfig(currentSheet.value))

const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return s === 'F4A' || !!adjudicationConfig.value || s.startsWith('附注')
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
const useGridFallback = computed(() => {
  const code = currentSheet.value
  return !!code && code !== 'F4A' && !adjudicationConfig.value && !code.startsWith('附注')
})

async function onImported() {
  await formData.loadAll()
}

// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide（真实复核对话）
provide('reloadWorkpaperData', () => formData.loadAll())

// ─── 监听 f4:save-items → 保存 + autoSnapshot ───────────────────────────────
async function handleF4SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    await formData.saveImmediate(items[0].item_id, items[0])
    versionToolbar.scheduleAutoSnapshot()
  }
}

function handleF4Writeback(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; auditedAmount: number }>).detail
  if (d?.accountCode != null && d.auditedAmount != null) {
    // writeback is handled by individual composables via api
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
