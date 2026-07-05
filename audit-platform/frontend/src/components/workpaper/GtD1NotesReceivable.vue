<template>

  <div class="d1-notes-receivable" :class="{ 'is-readonly': review.isReadonly.value }">

    <div v-if="isLoading" class="loading-container">

      <el-skeleton :rows="8" animated />

    </div>



    <template v-else>

      <!-- 双模式工具栏（结构化 HTML ↔ OnlyOffice） -->

      <div v-if="showModeToolbar" class="d1-mode-toolbar">

        <el-segmented v-model="renderMode" :options="renderModeOptions" size="small" />

        <el-tag v-if="formSaving" type="info" size="small">保存中…</el-tag>

      </div>



      <GtOnlyOfficeSheet

        v-if="renderMode === 'onlyoffice'"

        :key="ooSheetName"

        :wp-id="props.wpId"

        :sheet-name="ooSheetName"

        :project-id="props.projectId"

        :readonly="props.readonly ?? false"

        @fallback="onOoFallback"

      />



      <template v-else>

      <!-- 底稿目录 / D1 主入口 -->

      <D1TabIndex

        v-if="currentSheet === 'directory' || currentSheet === 'D1' || currentSheet === 'skip'"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :all-responses="allResponses"

        :is-readonly="props.readonly ?? false"

        :available-sheets="availableSheets"

      />



      <!-- 程序表 D1A -->

      <D1TabProcedure

        v-else-if="currentSheet === 'D1A'"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :html-data="props.htmlData"

        :is-readonly="props.readonly ?? false"

      />



      <D1TabAdjudication

        v-else-if="currentSheet === 'D1-1'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabDetailCategory

        v-else-if="currentSheet === 'D1-2'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabDetailCustomer

        v-else-if="currentSheet === 'D1-3'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabBadDebt

        v-else-if="currentSheet === 'D1-4'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabDisclosure

        v-else-if="currentSheet === '附注上市'"

        variant="listed"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

      />

      <D1TabDisclosure

        v-else-if="currentSheet === '附注国企'"

        variant="soe"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

      />

      <D1TabPolicyCheck

        v-else-if="currentSheet === 'D1-14'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

      />

      <D1TabEclCalc

        v-else-if="currentSheet === 'D1-15'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

      />

      <D1TabBusinessMode

        v-else-if="currentSheet === 'D1-6'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabMemoReconciliation

        v-else-if="currentSheet === 'D1-7'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabEndorsementDetail

        v-else-if="currentSheet === 'D1-8'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabInterestCheck

        v-else-if="currentSheet === 'D1-9'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabInventoryCount

        v-else-if="currentSheet === 'D1-10'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabRelatedPartyCheck

        v-else-if="currentSheet === 'D1-11'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabPledgeCheck

        v-else-if="currentSheet === 'D1-12'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabSamplingVouching

        v-else-if="currentSheet === 'D1-13'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabWriteoffCheck

        v-else-if="currentSheet === 'D1-16'"

        :all-responses="allResponses"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />

      <D1TabAdjustment

        v-else-if="currentSheet === 'D1-5'"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :all-responses="allResponses"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

      />



      <!-- 分析提示等 → OnlyOffice -->

      <div v-else-if="useOnlyOfficeFallback" class="d1-fallback-sheet">

        <GtOnlyOfficeSheet

          :wp-id="props.wpId"

          :sheet-name="props.sheetName || ''"

          :project-id="props.projectId"

        />

      </div>



      <!-- 未识别 sheet → 目录兜底 -->

      <D1TabIndex

        v-else

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :all-responses="allResponses"

        :is-readonly="props.readonly ?? false"

        :available-sheets="availableSheets"

      />

      </template>

    </template>

  </div>

</template>



<script setup lang="ts">

/**

 * GtD1NotesReceivable.vue — D1 应收票据底稿主入口（比照 D2/D4 架构）

 */

import { ref, computed, defineAsyncComponent, toRef, onMounted, onBeforeUnmount, provide } from 'vue'

import { useD1FormData } from './composables/useD1FormData'

import { useD1Procedure } from './composables/useD1Procedure'

import { useD1Review } from './composables/useD1Review'

import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'

import { useD1ReviewThreads } from './composables/useD1ReviewThreads'

import { useD1CrossSheet } from './composables/useD1CrossSheet'

import { useD1EntryDualMode, type D1RenderMode } from './composables/useD1EntryDualMode'

import { useD1EventBus } from './composables/useD1EventBus'

import { resolveD1SheetCode } from './composables/useD1SheetRouting'

import { resolveD1SheetLabel } from './composables/d1SheetLabels'

import D1TabIndex from './d1/D1TabIndex.vue'

import D1TabDisclosure from './d1/D1TabDisclosure.vue'

import D1TabAdjudication from './d1/D1TabAdjudication.vue'

import D1TabDetailCategory from './d1/D1TabDetailCategory.vue'

import D1TabDetailCustomer from './d1/D1TabDetailCustomer.vue'

import D1TabBadDebt from './d1/D1TabBadDebt.vue'

import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'



const D1TabProcedure = defineAsyncComponent(() => import('./d1/D1TabProcedure.vue'))

const D1TabPolicyCheck = defineAsyncComponent(() => import('./d1/D1TabPolicyCheck.vue'))

const D1TabEclCalc = defineAsyncComponent(() => import('./d1/D1TabEclCalc.vue'))

const D1TabBusinessMode = defineAsyncComponent(() => import('./d1/D1TabBusinessMode.vue'))

const D1TabMemoReconciliation = defineAsyncComponent(() => import('./d1/D1TabMemoReconciliation.vue'))

const D1TabEndorsementDetail = defineAsyncComponent(() => import('./d1/D1TabEndorsementDetail.vue'))

const D1TabInterestCheck = defineAsyncComponent(() => import('./d1/D1TabInterestCheck.vue'))

const D1TabInventoryCount = defineAsyncComponent(() => import('./d1/D1TabInventoryCount.vue'))

const D1TabRelatedPartyCheck = defineAsyncComponent(() => import('./d1/D1TabRelatedPartyCheck.vue'))

const D1TabPledgeCheck = defineAsyncComponent(() => import('./d1/D1TabPledgeCheck.vue'))

const D1TabSamplingVouching = defineAsyncComponent(() => import('./d1/D1TabSamplingVouching.vue'))

const D1TabWriteoffCheck = defineAsyncComponent(() => import('./d1/D1TabWriteoffCheck.vue'))

const D1TabAdjustment = defineAsyncComponent(() => import('./d1/D1TabAdjustment.vue'))



const props = defineProps<{

  wpId: string

  projectId: string

  wpCode: string

  year: number

  readonly?: boolean

  sheetName?: string

  htmlData?: any

}>()



const emit = defineEmits<{

  (e: 'save'): void

  (e: 'completed'): void

  (e: 'jump-to-section', sheetName: string): void

}>()



const isLoading = ref(true)



const {

  allResponses,

  loadAll,

  saveImmediate,

  saveDebouncedText,

  flushPendingSave,

  saving: formSaving,

} = useD1FormData(toRef(props, 'wpId'), toRef(props, 'projectId'))



const procedure = useD1Procedure(allResponses, saveImmediate)



const review = useD1Review(

  allResponses,

  procedure.procedureProgress,

  procedure.canInputOverallConclusion,

  saveImmediate,

  computed(() => props.readonly ?? false),

)



const currentSheet = computed<string>(() => resolveD1SheetCode(props.sheetName || ''))



const availableSheets = computed(() =>

  props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets ?? [],

)



const KNOWN_HTML_SHEETS = new Set([

  'directory', 'D1', 'D1A',

  'D1-1', 'D1-2', 'D1-3', 'D1-4', 'D1-5', 'D1-6', 'D1-7', 'D1-8', 'D1-9',

  'D1-10', 'D1-11', 'D1-12', 'D1-13', 'D1-14', 'D1-15', 'D1-16',

  '附注上市', '附注国企',

])



const KNOWN_ONLYOFFICE_SHEETS = new Set(['analysis-hint'])



const useOnlyOfficeFallback = computed(() => {

  const sheet = currentSheet.value

  if (!sheet) return !!props.sheetName

  return KNOWN_ONLYOFFICE_SHEETS.has(sheet)

})



const showModeToolbar = computed(() =>

  KNOWN_HTML_SHEETS.has(currentSheet.value) && !useOnlyOfficeFallback.value,

)



const dualMode = useD1EntryDualMode({

  wpId: toRef(props, 'wpId'),

  currentSheet,

  availableSheets,

  reloadAllResponses: () => loadAll(),

})



const ooSheetName = computed(() =>

  resolveD1SheetLabel(currentSheet.value, availableSheets.value)

    || props.sheetName

    || 'D1-1',

)



const renderMode = computed({

  get: () => dualMode.mode.value,

  set: (v: D1RenderMode) => { void dualMode.switchMode(v) },

})



const renderModeOptions = computed(() => [

  { label: 'HTML精美化', value: 'html' as const },

  {

    label: '在线编辑',

    value: 'onlyoffice' as const,

    disabled: !dualMode.ooAvailable.value,

  },

])



function onOoFallback(): void {

  void dualMode.switchMode('html')

}



const crossSheet = useD1CrossSheet({ allResponses })

useD1EventBus(allResponses, saveDebouncedText)



const wpIdRef = toRef(props, 'wpId')

const projectIdRef = toRef(props, 'projectId')



useWorkpaperReviewProvide({ wpId: wpIdRef, projectId: projectIdRef })

const { getThreadDot, getRowDot } = useD1ReviewThreads(wpIdRef)
provide('d1GetThreadDot', getThreadDot)
provide('d1GetRowDot', getRowDot)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: () => loadAll(),
})

provide('d1SaveImmediate', saveImmediate)

provide('d1SaveDebouncedText', saveDebouncedText)

provide('d1SuppressLocalOo', true)

provide('d1CrossSheet', crossSheet)

provide('displayPrefs', {

  fmtAmount: (v: number) => {

    if (v === 0) return '-'

    const abs = Math.abs(v).toLocaleString('zh-CN', {

      minimumFractionDigits: 2,

      maximumFractionDigits: 2,

    })

    return v < 0 ? `(${abs})` : abs

  },

  fmtPercent: (v: number) => (v * 100).toFixed(2) + '%',

  amountClass: (v: number) => (v < 0 ? 'amount-negative' : ''),

})



async function selfLoad(): Promise<void> {

  if (props.htmlData?.responses_snapshot) {

    const map = new Map<string, any>()

    for (const [k, v] of Object.entries(props.htmlData.responses_snapshot)) {

      map.set(k, v)

    }

    allResponses.value = map as any

    isLoading.value = false

    return

  }

  try {

    await loadAll()

  } catch (err) {

    console.warn('[GtD1NotesReceivable] selfLoad failed:', err)

  } finally {

    isLoading.value = false

  }

}



onMounted(() => { void selfLoad() })



onBeforeUnmount(() => {

  flushPendingSave()

})

</script>



<style scoped>

.d1-notes-receivable {

  padding: 16px;

  max-width: 1400px;

  margin: 0 auto;

  min-height: 100%;

  display: flex;

  flex-direction: column;

}

.d1-notes-receivable.is-readonly {

  pointer-events: auto;

}

.d1-mode-toolbar {

  display: flex;

  align-items: center;

  gap: 12px;

  margin-bottom: 12px;

}

.loading-container {

  padding: 24px 0;

}

.d1-fallback-sheet {

  display: flex;

  flex-direction: column;

  min-height: calc(100vh - 280px);

}

.d1-fallback-sheet :deep(.gt-onlyoffice-sheet) {

  flex: 1;

  min-height: calc(100vh - 340px);

}

.amount-negative {

  color: #f56c6c;

}

</style>

