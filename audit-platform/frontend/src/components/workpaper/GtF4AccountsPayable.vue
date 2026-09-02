<template>
  <div class="f4-accounts-payable">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="showHtmlToolbar" class="f4-accounts-payable-toolbar">
        <el-segmented
          :model-value="dualMode.currentMode.value"
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
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-f4-accounts-payable" />
      </div>

      <!-- 全局勾稽告警 -->
      <el-alert
        v-if="tbAmount > 0 && f4AuditedTotal > 0 && Math.abs(f4AuditedTotal - tbAmount) > 1"
        type="warning"
        :closable="false"
        style="margin-bottom: 8px"
      >
        <template #title>
          F4-1审定合计 {{ f4AuditedTotal.toLocaleString() }} 与试算平衡表(2202)
          {{ tbAmount.toLocaleString() }} 差异 {{ Math.round(f4AuditedTotal - tbAmount).toLocaleString() }}
        </template>
      </el-alert>

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
          :adjudication-prefill="props.htmlData?.adjudication_prefill"
          :tb-source-codes="props.htmlData?.project_context?.tb_source_codes"
        />

        <F4TabDetail
          v-else-if="currentSheet === 'F4-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :bs-date="bsDate"
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
          :bs-date="bsDate"
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
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import {
  useAgingConfig,
  PRESET_SEGMENTS,
  DEFAULT_SUBJECT_PRESETS,
  type AgingSegment,
} from '@/composables/useAgingConfig'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import CycleImportExportDropdown from './shared/CycleImportExportDropdown.vue'
import { isImportExportSheet, resolveImportExportSheet } from './shared/cycleImportExportRegistry'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
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
  const yr = formData.projectContext.value?.audit_year
  if (yr) return parseInt(String(yr), 10)
  return new Date().getFullYear() - 1
})
const bsDate = computed(
  () => (props.htmlData?.project_context?.bs_date
    ?? props.htmlData?.projectContext?.bs_date
    ?? formData.projectContext.value?.bs_date)
    || '',
)
// 🔴 render 输出 project_context（snake_case）；formData.projectContext 仅在 selfLoad
// 读到 htmlData.projectContext（camelCase）时才填 → 恒空。故优先读 htmlData.project_context，
// 否则 2202 TB 核对标量恒 0（审定表差异/全局告警失效）。
const tbAmount = computed(() => {
  const ctx = props.htmlData?.project_context
    ?? props.htmlData?.projectContext
    ?? formData.projectContext.value
  return Number(ctx?.tb_amount ?? ctx?.tb_amount_audited ?? 0) || 0
})

// 从 allResponses 解析 F4-1 审定合计（用于全局勾稽告警）
const f4AuditedTotal = computed(() => {
  try {
    const raw = allResponses.value.get('F4-1-adj-nature-rows')?.remark
    if (!raw) return 0
    const rows = JSON.parse(raw)
    if (!Array.isArray(rows)) return 0
    // 找到合计行或逐行累加期末审定数
    let total = 0
    for (const r of rows) {
      if (r.label === '合计') return parseFloat(r.closingAdjusted ?? r.closingUnadjusted ?? 0) || 0
      total += parseFloat(r.closingAdjusted ?? 0) || 0
    }
    return total
  } catch { return 0 }
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
provide('f4BsDate', bsDate)
provide('f4TbAmount', tbAmount)

// ─── 账龄段：一处装配并 provide，各 tab 经 inject 共享（避免每 tab 各自请求、首帧段数跳变） ──
const f4AgingConfig = useAgingConfig(computed(() => props.projectId), 'F4')
const f4AgingSegments = computed<AgingSegment[]>(() =>
  f4AgingConfig.segments.value.length
    ? f4AgingConfig.segments.value
    : (PRESET_SEGMENTS[DEFAULT_SUBJECT_PRESETS.F4 ?? 'THREE_YEAR'] as AgingSegment[]),
)
provide('f4AgingSegments', f4AgingSegments)
provide('f4AgingPreset', computed(() => f4AgingConfig.preset.value))

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

// ─── 复核圆点 ─────────────────────────────────────────────────────────────────
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

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
