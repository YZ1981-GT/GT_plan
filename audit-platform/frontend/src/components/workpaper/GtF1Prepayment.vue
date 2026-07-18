<template>
  <div class="f1-prepayment">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="showHtmlToolbar" class="f1-header-toolbar">
        <el-segmented
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
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
          v-if="currentSheet === 'F1A'"
          sheet-code="F1A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <F1TabAdjudication
          v-else-if="currentSheet === 'F1-1'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <F1TabDetail
          v-else-if="currentSheet === 'F1-2'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <F1TabAdjustment
          v-else-if="currentSheet === 'F1-3'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <F1TabAnalysis
          v-else-if="currentSheet === 'F1-4'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <F1TabLongTerm
          v-else-if="currentSheet === 'F1-5'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <F1TabRelatedParty
          v-else-if="currentSheet === 'F1-6'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
        />

        <F1TabComprehensiveCheck
          v-else-if="currentSheet === 'F1-7'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
        />

        <F1TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
          :applicable-standards="applicableStandards"
        />

        <F1TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :all-responses="allResponses"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
          :save-immediate="saveImmediate"
          :debounced-save="debouncedSave"
          :cross-sheet="crossSheet"
          :applicable-standards="applicableStandards"
        />

        <F1TabConfirmationProcedure
          v-else-if="currentSheet === 'F1-CONF'"
          :wp-id="wpIdRef"
          :project-id="projectIdRef"
          :is-readonly="isReadonly"
        />

        <!-- 兜底：未识别 sheet → OnlyOffice -->
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
 * GtF1Prepayment.vue — F1 预付账款底稿主入口
 *
 * 比照 GtF3NotesPayable / GtF4AccountsPayable：
 * 外层 GtWpRenderer 通过 sheetName 分发，无内层 el-tabs（避免双层嵌套）。
 *
 * 科目覆盖：1123 预付账款（借方科目/资产类）
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { useF1FormData } from './composables/useF1FormData'
import { useF1CrossSheet } from './composables/useF1CrossSheet'
import { useF1DualMode } from './composables/useF1DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'

const F1TabAdjudication = defineAsyncComponent(() => import('./f1/F1TabAdjudication.vue'))
const F1TabDetail = defineAsyncComponent(() => import('./f1/F1TabDetail.vue'))
const F1TabAdjustment = defineAsyncComponent(() => import('./f1/F1TabAdjustment.vue'))
const F1TabAnalysis = defineAsyncComponent(() => import('./f1/F1TabAnalysis.vue'))
const F1TabLongTerm = defineAsyncComponent(() => import('./f1/F1TabLongTerm.vue'))
const F1TabRelatedParty = defineAsyncComponent(() => import('./f1/F1TabRelatedParty.vue'))
const F1TabConfirmationProcedure = defineAsyncComponent(() => import('./f1/F1TabConfirmationProcedure.vue'))
const F1TabComprehensiveCheck = defineAsyncComponent(() => import('./f1/F1TabComprehensiveCheck.vue'))
const F1TabDisclosureListed = defineAsyncComponent(() => import('./f1/F1TabDisclosureListed.vue'))
const F1TabDisclosureSoe = defineAsyncComponent(() => import('./f1/F1TabDisclosureSoe.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const sheetNameRef = computed(() => props.sheetName || '')

/** 从 sheetName 提取 F1A / F1-1~F1-7 / 附注 / 函证编码 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/F1-note-listed|附注披露.*上市|附注.*上市/.test(name)) return '附注上市'
  if (/F1-note-soe|附注披露.*国企|附注.*国企/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  if (/函证|F1-CONF|F1CONF/i.test(name)) return 'F1-CONF'
  const m = name.match(/(F1A|F1-\d+)/i)
  return m ? m[1].toUpperCase().replace(/^F1A$/i, 'F1A') : ''
})

const showHtmlToolbar = computed(() => {
  const s = currentSheet.value
  return s.startsWith('F1-') || s === 'F1A' || s.startsWith('附注') || s === 'F1-CONF'
})

/** 适用准则：htmlData / project_context 可能是数组或逗号分隔字符串 */
const applicableStandards = computed<string[]>(() => {
  const raw =
    props.htmlData?.project_context?.applicable_standards
    ?? props.htmlData?.projectContext?.applicable_standards
    ?? props.htmlData?.applicable_standards
    ?? []
  if (Array.isArray(raw)) return raw.map(String).filter(Boolean)
  if (typeof raw === 'string' && raw.trim()) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) return parsed.map(String).filter(Boolean)
    } catch { /* ignore */ }
    return raw.split(/[,;|]+/).map((s: string) => s.trim()).filter(Boolean)
  }
  return []
})

const {
  allResponses,
  loadAll,
  saveImmediate: rawSaveImmediate,
  debouncedSave,
  writebackTrialBalance,
} = useF1FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionToolbar = runtime?.version ?? {
  versionTrailRef: ref<{ openDrawer: () => void } | null>(null),
  openVersionHistory: () => undefined,
  scheduleAutoSnapshot: () => undefined,
  wrapSaveImmediate: (<T,>(fn: T): T => fn),
}
const { versionTrailRef, openVersionHistory } = versionToolbar
const saveImmediate = versionToolbar.wrapSaveImmediate(rawSaveImmediate)

provide('f1VersionTrailRef', versionTrailRef)
provide('f1OpenVersionHistory', openVersionHistory)

const crossSheet = useF1CrossSheet({ allResponses })

const dualMode = useF1DualMode({
  wpId: wpIdRef,
  sheetName: sheetNameRef,
  reloadAll: () => loadAll(),
})

provide('reloadWorkpaperData', loadAll)

function handleF1Writeback(e: Event): void {
  const d = (e as CustomEvent<{ accountCode?: string; auditedAmount?: number }>).detail
  if (d?.auditedAmount == null) return
  void writebackTrialBalance(d.auditedAmount)
}

async function selfLoad() {
  if (props.htmlData) {
    // htmlData 已由 render-config 注入，仍拉 checklist 全量
  }
  try {
    await loadAll()
  } catch (err) {
    console.warn('[GtF1Prepayment] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  window.addEventListener('f1:writeback-trial-balance', handleF1Writeback)
  void selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('f1:writeback-trial-balance', handleF1Writeback)
})
</script>

<style scoped>
.f1-prepayment {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.f1-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}
</style>
