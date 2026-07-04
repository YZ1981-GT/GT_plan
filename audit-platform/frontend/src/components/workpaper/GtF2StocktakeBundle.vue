<template>
  <div class="f2-stocktake-bundle">
    <div v-if="isLoading" class="loading"><el-skeleton :rows="6" animated /></div>
    <template v-else>
      <div class="toolbar">
        <el-segmented v-model="dualMode.currentMode.value" :options="dualMode.modeOptions" size="small" @change="dualMode.onModeChange" />
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
        <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="projectId"
        :sheet-name="props.sheetName || activeTab"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <template v-else-if="singleSheetMode">
        <component
          :is="tabComponent(activeTab)"
          :wp-id="props.wpId"
          :project-id="projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />
      </template>

      <el-tabs v-else v-model="activeTab" class="stocktake-tabs">
        <el-tab-pane label="监盘程序表" name="program" lazy>
          <GtAProgramConsole
            v-if="activeTab === 'program'"
            :wp-id="props.wpId"
            sheet-name="F2-21A"
            :schema="{ columns: [], rows: [] }"
            :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
            :readonly="isReadonly"
          />
        </el-tab-pane>
        <el-tab-pane v-for="t in dataTabs" :key="t.id" :label="t.label" :name="t.id" lazy>
          <component
            :is="tabComponent(t.id)"
            v-if="activeTab === t.id"
            :wp-id="props.wpId"
            :project-id="projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </el-tab-pane>
      </el-tabs>

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="projectId" />
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
/**
 * GtF2StocktakeBundle — F2 存货监盘 HTML 入口 (F2-21A + F2-21~26)
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, toRef, defineAsyncComponent, type Component } from 'vue'
import { useRoute } from 'vue-router'
import { useF2StocktakeFormData, type ChecklistResponse } from './composables/useF2StocktakeFormData'
import { useF2StocktakeDualMode } from './composables/useF2StocktakeDualMode'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import { useF2ReviewDialogProvide } from './composables/useF2ReviewDialogProvide'
import F2TabStocktakeQuestionnaire from './f2/stocktake/F2TabStocktakeQuestionnaire.vue'
import F2TabStocktakePlan from './f2/stocktake/F2TabStocktakePlan.vue'
import F2TabStocktakeSummary from './f2/stocktake/F2TabStocktakeSummary.vue'
import F2TabStocktakeReconcile from './f2/stocktake/F2TabStocktakeReconcile.vue'
import F2TabStocktakeSampleResult from './f2/stocktake/F2TabStocktakeSampleResult.vue'
import F2TabStocktakeRollforward from './f2/stocktake/F2TabStocktakeRollforward.vue'
import GtAProgramConsole from './GtAProgramConsole.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const GtReviewDialog = defineAsyncComponent(() => import('@/components/collaboration/GtReviewDialog.vue'))

const props = defineProps<{
  wpId: string
  projectId?: string
  wpCode?: string
  sheetName?: string
  readonly?: boolean
}>()

const route = useRoute()
const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)
const projectId = computed(() => props.projectId || (route.params.projectId as string) || '')

const formData = useF2StocktakeFormData({
  wpId: toRef(props, 'wpId'),
  projectId,
})

const allResponses = computed(() => formData.allResponses.value)

const dualMode = useF2StocktakeDualMode({
  wpId: toRef(props, 'wpId'),
  reloadAll: () => formData.loadAll(),
})

const versionToolbar = useWorkpaperVersionToolbar({
  wpId: toRef(props, 'wpId'),
  projectId,
})
const { versionTrailRef } = versionToolbar

const wpIdRef = toRef(props, 'wpId')
const reviewDialog = useF2ReviewDialogProvide({ wpId: wpIdRef, projectId })

provide('reloadWorkpaperData', () => formData.loadAll())

const dataTabs = [
  { id: 'F2-21', label: '盘点问卷' },
  { id: 'F2-22', label: '监盘计划' },
  { id: 'F2-23', label: '监盘小结' },
  { id: 'F2-24', label: '账面核对' },
  { id: 'F2-25', label: '抽盘汇总' },
  { id: 'F2-26', label: '倒轧表' },
]

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  const m = name.match(/(F2-21A|F2-2[1-6])/)
  return m ? m[1] : 'F2-21A'
})

const singleSheetMode = computed(() => /^F2-2[1-6]$/.test(currentSheet.value))

const activeTab = ref(singleSheetMode.value ? currentSheet.value : 'program')

function tabComponent(id: string): Component {
  const map: Record<string, Component> = {
    'F2-21': F2TabStocktakeQuestionnaire,
    'F2-22': F2TabStocktakePlan,
    'F2-23': F2TabStocktakeSummary,
    'F2-24': F2TabStocktakeReconcile,
    'F2-25': F2TabStocktakeSampleResult,
    'F2-26': F2TabStocktakeRollforward,
  }
  return map[id] || F2TabStocktakeQuestionnaire
}

async function handleSave(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length) {
    await formData.saveItemsFromEvent(items)
    versionToolbar.scheduleAutoSnapshot()
  }
}

onMounted(() => {
  window.addEventListener('f2-stocktake:save-items', handleSave)
  void formData.loadAll().finally(() => { isLoading.value = false })
})

onBeforeUnmount(() => {
  window.removeEventListener('f2-stocktake:save-items', handleSave)
})
</script>

<style scoped>
.f2-stocktake-bundle { padding: 12px; height: 100%; display: flex; flex-direction: column; }
.loading { padding: 24px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.stocktake-tabs { flex: 1; }
.stocktake-tabs :deep(.el-tabs__content) { overflow: auto; }
</style>
