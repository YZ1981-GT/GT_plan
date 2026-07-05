<template>
  <div class="g3-dividend-receivable">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div class="g3-dividend-receivable-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <!-- 双模式：HTML sheet 切到 OnlyOffice -->
      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- G3A 程序表（对齐 D4A） -->
      <CycleTabProcedure
        v-else-if="currentSheet === 'G3A'"
        sheet-code="G3A"
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

      <G3TabDetail
        v-else-if="currentSheet === 'G3-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G3TabAdjustment
        v-else-if="currentSheet === 'G3-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G3TabCalcCheck
        v-else-if="currentSheet === 'G3-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G3TabOverdueCheck
        v-else-if="currentSheet === 'G3-5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G3TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <G3TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <!-- 兜底：未迁移 sheet → OnlyOffice -->
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
/**
 * GtG3DividendReceivable.vue — G3 应收股利底稿主入口
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Task 1.1, 9.1~9.3
 * sheetName 分发到 G3 专属子组件（G3A + G3-1~G3-5 + 附注），未迁移走 OnlyOffice
 * 集成：useWorkpaperVersionToolbar(autoSnapshot) + provide('openReviewDialog') + 双模式
 * EventBus：监听 g3:save-items 持久化 + substantive:adjudicated(1131)
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import { useG3DivRecFormData } from './composables/useG3DivRecFormData'
import { useG3DualMode } from './composables/useG3DualMode'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import CycleTabAdjudication from './shared/CycleTabAdjudication.vue'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import { getAdjudicationConfig } from './shared/cycleAdjudicationConfigs'
import type { ChecklistResponse } from './composables/useF1FormData'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const G3TabDetail = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabDetail.vue'))
const G3TabCalcCheck = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabCalcCheck.vue'))
const G3TabAdjustment = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabAdjustment.vue'))
const G3TabOverdueCheck = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabOverdueCheck.vue'))
const G3TabDisclosureListed = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabDisclosureListed.vue'))
const G3TabDisclosureSOE = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabDisclosureSOE.vue'))

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
const projectIdRef = computed(() => props.projectId)
const formData = useG3DivRecFormData({ wpId: wpIdRef, projectId: projectIdRef })
const isReadonly = computed(() => !!props.readonly)
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/附注披露/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(G3A|G3-\d+)/)
  return m ? m[1] : ''
})

const adjudicationConfig = computed(() => getAdjudicationConfig(currentSheet.value))

/** G3A + G3-1~G3-5 + 附注 为 HTML 专属组件（支持双模式） */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return s === 'G3A' || /^G3-[1-5]$/.test(s) || s.startsWith('附注') || !!adjudicationConfig.value
})

const dualMode = useG3DualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

// ─── provide openReviewDialog 供子组件 inject ────────────────────────────────
function openReviewDialog(sectionId: string): void {
  console.log('[G3] openReviewDialog:', sectionId)
}
provide('openReviewDialog', openReviewDialog)
provide('reloadWorkpaperData', () => formData.loadAll())

// ─── 监听 g3:save-items → 保存 + autoSnapshot ───────────────────────────────
async function handleG3SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    for (const it of items) {
      if (it?.item_id) await formData.saveImmediate(it.item_id, it)
    }
    versionToolbar.scheduleAutoSnapshot()
  }
}

// ─── 监听 substantive:adjudicated(1131) → 附注刷新 ──────────────────────────
function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
  if (d?.accountCode === '1131') {
    void formData.saveImmediate('G3-1-adjudicated-amount', {
      item_id: 'G3-1-adjudicated-amount',
      conclusion: String(d.adjudicatedAmount),
      remark: null,
    })
  }
}

onMounted(async () => {
  window.addEventListener('g3:save-items', handleG3SaveItems)
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g3:save-items', handleG3SaveItems)
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
})
</script>

<style scoped>
.g3-dividend-receivable { padding: 12px; }
.loading-container { padding: 24px; }
.g3-dividend-receivable-toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }
</style>
