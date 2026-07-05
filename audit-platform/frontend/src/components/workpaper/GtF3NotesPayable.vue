<template>

  <div class="f3-notes-payable">

    <div v-if="isLoading" class="loading-container">

      <el-skeleton :rows="8" animated />

    </div>



    <template v-else>

      <div v-if="showHtmlToolbar" class="f3-header-toolbar">

        <el-segmented

          v-model="dualMode.currentMode.value"

          :options="dualMode.modeOptions"

          size="small"

          @change="dualMode.onModeChange"

        />

        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>

        <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>

      </div>



      <!-- OnlyOffice 模式 -->

      <GtOnlyOfficeSheet

        v-if="dualMode.currentMode.value === 'onlyoffice'"

        :wp-id="props.wpId"

        :project-id="props.projectId"

        :sheet-name="props.sheetName || ''"

        :readonly="isReadonly"

        style="height: calc(100vh - 180px)"

      />



      <!-- HTML 结构化视图 -->

      <template v-else>

        <!-- F3A 程序表（对齐 D4A） -->
        <CycleTabProcedure
          v-if="currentSheet === 'F3A'"
          sheet-code="F3A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />



        <!-- F3-1 审定表 -->

        <F3TabAdjudication

          v-else-if="currentSheet === 'F3-1'"

          :wp-id="props.wpId"

          :project-id="props.projectId"

          :all-responses="allResponses"

          :is-readonly="isReadonly"

          :cross-sheet="crossSheet"

        />



        <!-- F3-2 明细 -->

        <F3TabDetail

          v-else-if="currentSheet === 'F3-2'"

          :wp-id="props.wpId"

          :project-id="props.projectId"

          :all-responses="allResponses"

          :is-readonly="isReadonly"

        />



        <!-- F3-3 调整分录 -->

        <F3TabAdjustment

          v-else-if="currentSheet === 'F3-3'"

          :wp-id="props.wpId"

          :project-id="props.projectId"

          :all-responses="allResponses"

          :is-readonly="isReadonly"

        />



        <!-- F3-4 利息测算 -->

        <F3TabInterestCalc

          v-else-if="currentSheet === 'F3-4'"

          :wp-id="props.wpId"

          :project-id="props.projectId"

          :all-responses="allResponses"

          :is-readonly="isReadonly"

        />



        <!-- F3-5 逾期检查 -->

        <F3TabOverdueCheck

          v-else-if="currentSheet === 'F3-5'"

          :wp-id="props.wpId"

          :project-id="props.projectId"

          :all-responses="allResponses"

          :is-readonly="isReadonly"

        />



        <!-- F3-6 关联方 -->

        <F3TabRelatedParty

          v-else-if="currentSheet === 'F3-6'"

          :wp-id="props.wpId"

          :project-id="props.projectId"

          :all-responses="allResponses"

          :is-readonly="isReadonly"

        />



        <!-- F3-7 检查表 -->

        <F3TabVoucherCheck

          v-else-if="currentSheet === 'F3-7'"

          :wp-id="props.wpId"

          :project-id="props.projectId"

          :all-responses="allResponses"

          :is-readonly="isReadonly"

          :year="auditYear"

        />



        <!-- 附注披露（上市） -->

        <F3TabDisclosureListed

          v-else-if="currentSheet === '附注上市'"

          :wp-id="props.wpId"

          :project-id="props.projectId"

          :all-responses="allResponses"

          :is-readonly="isReadonly"

          :applicable-standards="applicableStandards"

        />



        <!-- 附注披露（国企） -->

        <F3TabDisclosureSOE

          v-else-if="currentSheet === '附注国企'"

          :wp-id="props.wpId"

          :project-id="props.projectId"

          :all-responses="allResponses"

          :is-readonly="isReadonly"

          :applicable-standards="applicableStandards"

        />



        <!-- 未匹配 → OnlyOffice fallback -->

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

    </template>

  </div>

</template>



<script setup lang="ts">

/**

 * GtF3NotesPayable.vue — F3 应付票据底稿主入口

 *

 * 比照 GtD4OperatingRevenue：外层 GtWpRenderer 通过 sheetName 分发，无内层 el-tabs。

 * Spec: .kiro/specs/f3-notes-payable/ Task 1.1, 9.1

 */

import { ref, computed, onMounted, onBeforeUnmount, provide, toRef, defineAsyncComponent } from 'vue'

import { useF3FormData, type ChecklistResponse } from './composables/useF3FormData'

import { useF3CrossSheet } from './composables/useF3CrossSheet'

import { useF3DualMode } from './composables/useF3DualMode'

import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'



const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))



const F3TabAdjudication = defineAsyncComponent(() => import('./f3-notes-payable/F3TabAdjudication.vue'))

const F3TabDetail = defineAsyncComponent(() => import('./f3-notes-payable/F3TabDetail.vue'))

const F3TabAdjustment = defineAsyncComponent(() => import('./f3-notes-payable/F3TabAdjustment.vue'))

const F3TabInterestCalc = defineAsyncComponent(() => import('./f3-notes-payable/F3TabInterestCalc.vue'))

const F3TabOverdueCheck = defineAsyncComponent(() => import('./f3-notes-payable/F3TabOverdueCheck.vue'))

const F3TabRelatedParty = defineAsyncComponent(() => import('./f3-notes-payable/F3TabRelatedParty.vue'))

const F3TabVoucherCheck = defineAsyncComponent(() => import('./f3-notes-payable/F3TabVoucherCheck.vue'))

const F3TabDisclosureListed = defineAsyncComponent(() => import('./f3-notes-payable/F3TabDisclosureListed.vue'))

const F3TabDisclosureSOE = defineAsyncComponent(() => import('./f3-notes-payable/F3TabDisclosureSOE.vue'))



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



const isReadonly = computed(() => !!props.readonly)

const isLoading = ref(true)

const sheetNameRef = computed(() => props.sheetName || '')



const formData = useF3FormData({

  wpId: toRef(props, 'wpId'),

  projectId: toRef(props, 'projectId'),

})



const allResponses = computed(() => formData.allResponses.value)



const crossSheet = useF3CrossSheet({

  allResponses: formData.allResponses,

  projectContext: formData.projectContext,

})



const versionToolbar = useWorkpaperVersionToolbar({

  wpId: toRef(props, 'wpId'),

  projectId: toRef(props, 'projectId'),

})

const { versionTrailRef } = versionToolbar



const dualMode = useF3DualMode({

  wpId: toRef(props, 'wpId'),

  sheetName: sheetNameRef,

  reloadAll: () => formData.loadAll(),

})



/** 从 sheetName 提取 F3A / F3-1~F3-7 / 附注编码 */

const currentSheet = computed(() => {

  const name = props.sheetName || props.wpCode || ''

  if (/F3-note-listed|附注披露.*上市|附注.*上市/.test(name)) return '附注上市'

  if (/F3-note-soe|附注披露.*国企|附注.*国企/.test(name)) return '附注国企'

  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'

  const m = name.match(/(F3A|F3-\d+)/)

  return m ? m[1] : ''

})



const showHtmlToolbar = computed(() => {

  const s = currentSheet.value

  return s.startsWith('F3-') || s === 'F3A' || s.startsWith('附注')

})



const applicableStandards = computed(() =>

  formData.projectContext.value?.applicable_standards ?? [],

)



const auditYear = computed(() => {

  if (props.year) return props.year

  const bs = formData.projectContext.value?.bs_date

  if (bs && String(bs).length >= 4) return parseInt(String(bs).slice(0, 4), 10)

  return new Date().getFullYear() - 1

})



function openReviewDialog(sectionId: string): void {

  console.log('[F3] openReviewDialog:', sectionId)

}

provide('openReviewDialog', openReviewDialog)

provide('reloadWorkpaperData', () => formData.loadAll())



async function handleF3SaveItems(e: Event): Promise<void> {

  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items

  if (Array.isArray(items) && items.length > 0) {

    await formData.saveItemsFromEvent(items)

    versionToolbar.scheduleAutoSnapshot()

  }

}



function handleF3Writeback(e: Event): void {

  const d = (e as CustomEvent<{ accountCode: string; auditedAmount: number }>).detail

  if (d?.accountCode != null && d.auditedAmount != null) {

    void formData.writebackTrialBalance(d.accountCode, d.auditedAmount)

  }

}



async function selfLoad(): Promise<void> {

  if (props.htmlData?.projectContext) {

    formData.projectContext.value = props.htmlData.projectContext

  }

  try {

    await formData.loadAll()

  } catch (err) {

    console.warn('[GtF3NotesPayable] selfLoad failed:', err)

  } finally {

    isLoading.value = false

  }

}



onMounted(() => {

  window.addEventListener('f3:save-items', handleF3SaveItems)

  window.addEventListener('f3:writeback-trial-balance', handleF3Writeback)

  void selfLoad()

})



onBeforeUnmount(() => {

  window.removeEventListener('f3:save-items', handleF3SaveItems)

  window.removeEventListener('f3:writeback-trial-balance', handleF3Writeback)

})

</script>



<style scoped>

.f3-notes-payable {

  padding: 12px;

}

.loading-container {

  padding: 24px;

}

.f3-header-toolbar {

  margin-bottom: 8px;

  display: flex;

  gap: 8px;

  align-items: center;

}

</style>

