<template>

  <div class="d1-notes-receivable" :class="{ 'is-readonly': review.isReadonly.value }">

    <div v-if="isLoading" class="loading-container">

      <el-skeleton :rows="8" animated />

    </div>



    <template v-else>

      <!-- 双模式工具栏（结构化 HTML ↔ OnlyOffice） -->

      <div v-if="showModeToolbar" class="d1-mode-toolbar">

        <el-segmented v-model="renderMode" :options="renderModeOptions" size="small" />

        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d1-notes-receivable" />

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

      <!-- 全局勾稽告警（跨 sheet 聚合，ECL/坏账/贴现披露口径）-->

      <div v-if="globalAlerts.length" class="d1-global-alerts">

        <el-alert

          v-for="(a, i) in globalAlerts"

          :key="`d1-galert-${i}`"

          :type="a.type"

          :closable="false"

          show-icon

          :title="a.text"

        />

      </div>

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
        :html-data="props.htmlData"

        :is-readonly="props.readonly ?? false"

        :sheet-name="props.sheetName"

        :tb-seed-amount="tbNotesReceivableAmount"

        :tb-seed-provenance="tbNotesReceivableProvenance"

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

        :related-parties="relatedParties"

        :bs-date="bsDate"

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

        :year="props.year"

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

    <GtWpReviewRail
      v-if="!isLoading && renderMode !== 'onlyoffice'"
      :section-id="d1ReviewSection.id"
      :section-label="d1ReviewSection.label"
    />
    <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->

  </div>

</template>



<script setup lang="ts">

/**

 * GtD1NotesReceivable.vue — D1 应收票据底稿主入口（比照 D2/D4 架构）

 */

import { ref, computed, defineAsyncComponent, toRef, inject, onMounted, onBeforeUnmount, provide } from 'vue'

import { useD1FormData } from './composables/useD1FormData'

import { useD1Procedure } from './composables/useD1Procedure'

import { useD1Review } from './composables/useD1Review'

import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

import { useD1ReviewThreads } from './composables/useD1ReviewThreads'

import { useD1CrossSheet } from './composables/useD1CrossSheet'

import { useD1EntryDualMode, type D1RenderMode } from './composables/useD1EntryDualMode'

import { useD1EventBus } from './composables/useD1EventBus'

import { resolveD1SheetCode } from './composables/useD1SheetRouting'

import { resolveD1SheetLabel } from './composables/d1SheetLabels'
import { resolveD1ReviewSection } from './composables/d1ReviewSectionMap'
import GtWpReviewRail from './GtWpReviewRail.vue'

import D1TabIndex from './d1/D1TabIndex.vue'

import D1TabDisclosure from './d1/D1TabDisclosure.vue'

import D1TabAdjudication from './d1/D1TabAdjudication.vue'

import D1TabDetailCategory from './d1/D1TabDetailCategory.vue'

import D1TabDetailCustomer from './d1/D1TabDetailCustomer.vue'

import D1TabBadDebt from './d1/D1TabBadDebt.vue'

import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'

import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'



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

const relatedParties = computed<string[]>(() => {
  const raw = props.htmlData?.project_context?.related_parties
    ?? props.htmlData?.projectContext?.related_parties
  if (!Array.isArray(raw)) return []
  return raw
    .map((p: unknown) => {
      if (typeof p === 'string') return p
      if (p && typeof p === 'object') {
        const o = p as Record<string, unknown>
        return String(o.name ?? o.party_name ?? o.partyName ?? '')
      }
      return ''
    })
    .filter(Boolean)
})

const d1ReviewSection = computed(() => resolveD1ReviewSection(currentSheet.value))

/**
 * 试算平衡表应收票据**净额**（原值 1121 − 坏账准备 1231-01）：由 render 提供，
 * 供 D1-1 审定表 TB↔审定净值核对行做 seed 回退。
 *
 * 🔴 净额口径（不是原值）：源模板 `审定表D1-1` 的差异数 `E20=E18-E19`，E18 是
 * 「三、应收票据净值」小计 → 被比较的「试算平衡表数」必然是净额；`report_config`
 * 的 BS-005 在 soe_standalone 下公式亦为 `TB('1121')-TB('1231-01')`。取原值会让核对行
 * 显示一个恰好等于坏账准备的**假差异**（实测项目 0ec33ac9：1,162,288.03）。
 *
 * 主路径是 Tier A 公式 `D1-adj-tb-amount` 求值后 transient seed 到锚点；本值仅在
 * 该公式缺失/被停用时兜底，两者同口径。
 */
const tbNotesReceivableAmount = computed<number>(() => {
  const ctx = props.htmlData?.project_context ?? props.htmlData?.projectContext
  const v = Number(ctx?.tb_amount)
  return Number.isFinite(v) ? v : 0
})

/** TB 核对行取数溯源：原值 / 坏账准备 / 净额，供审定表 tooltip 展示（可追溯口径）。 */
const tbNotesReceivableProvenance = computed<{
  gross: number; provision: number; net: number; hasProvision: boolean
}>(() => {
  const ctx = props.htmlData?.project_context ?? props.htmlData?.projectContext
  const num = (v: unknown): number => {
    const n = Number(v)
    return Number.isFinite(n) ? n : 0
  }
  const hasProvision = ctx?.tb_amount_gross !== undefined
  const gross = hasProvision ? num(ctx?.tb_amount_gross) : num(ctx?.tb_amount)
  return {
    gross,
    provision: num(ctx?.tb_provision_amount),
    net: num(ctx?.tb_amount),
    hasProvision,
  }
})

// 资产负债表日（render 提供）：供 D1-3 期后兑付取数窗口
const bsDate = computed<string>(() => {
  const ctx = props.htmlData?.project_context ?? props.htmlData?.projectContext
  return String(ctx?.bs_date ?? '')
})



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

  KNOWN_HTML_SHEETS.has(currentSheet.value) && !useOnlyOfficeFallback.value
  && currentSheet.value !== 'directory' && currentSheet.value !== 'D1' && currentSheet.value !== 'skip',

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

  { label: '结构化视图', value: 'html' as const },

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



// ─── 全局勾稽告警（跨 sheet 聚合）─────────────────────────────────────────
function fmtYuan(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
const globalAlerts = computed<Array<{ type: 'warning' | 'info' | 'success'; text: string }>>(() => {
  const alerts: Array<{ type: 'warning' | 'info' | 'success'; text: string }> = []
  const sheet = currentSheet.value
  // ① ECL 模型应计提 vs D1-4 坏账准备审定：差异>1 元提示（ECL/坏账 tab 内已自处理，排除避重复）
  if (sheet !== 'D1-15' && sheet !== 'D1-4') {
    const should = crossSheet.eclShouldProvision.value
    const diff = crossSheet.eclVsBadDebtDiff.value
    if (should > 0 && Math.abs(diff) > 1) {
      alerts.push({
        type: 'warning',
        text: `ECL 勾稽差异：D1-15 模型应计提减值 ${fmtYuan(should)} 元 与 D1-4 坏账准备审定合计 ${fmtYuan(crossSheet.badDebtTotalAudited.value)} 元 相差 ${fmtYuan(diff)} 元，请核对减值计提口径。`,
      })
    }
  }
  // ② D1-8 已贴现未终止确认票据：需表外披露 / 与 D5 应收款项融资勾稽（D1-8 tab 内已自处理，排除）
  if (sheet !== 'D1-8') {
    const disc = crossSheet.discountNotDerecognizedTotal.value
    if (disc > 0) {
      alerts.push({
        type: 'info',
        text: `D1-8 已贴现尚未终止确认票据 ${fmtYuan(disc)} 元：仍应列示应收票据并作表外披露，请与 D5 应收款项融资／附注质押担保勾稽。`,
      })
    }
  }
  return alerts
})

const wpIdRef = toRef(props, 'wpId')

const projectIdRef = toRef(props, 'projectId')



// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

// 保存成功后触发版本快照
const saveImmediateWithSnapshot = async (...args: Parameters<typeof saveImmediate>) => {
  await saveImmediate(...args)
  scheduleAutoSnapshot()
}

const { getThreadDot, getRowDot } = useD1ReviewThreads(wpIdRef)
provide('d1GetThreadDot', getThreadDot)
provide('d1GetRowDot', getRowDot)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: () => loadAll(),
})

provide('d1SaveImmediate', saveImmediateWithSnapshot)

provide('d1SaveDebouncedText', saveDebouncedText)

provide('d1SuppressLocalOo', true)

provide('d1CrossSheet', crossSheet)

provide('d1VersionTrailRef', versionTrailRef)

provide('d1OpenVersionHistory', openVersionHistory)

// 显示偏好收敛到单一真源（useDisplayPrefsStore），不再提供硬编码闭包。
// 过渡期同时保留字符串 key，值改为真 store，使未迁移 tab 立即获得正确单位/字号/负数行为。
// DisplayPrefs_Key 由 Runtime Boundary 统一 provide；保留字符串 key 供未迁移子 tab 使用。
const displayPrefs = useDisplayPrefsStore()
provide('displayPrefs', displayPrefs)



async function selfLoad(): Promise<void> {

  if (props.htmlData?.responses_snapshot) {

    const map = new Map<string, any>()

    for (const [k, v] of Object.entries(props.htmlData.responses_snapshot)) {

      // 以 Map 键为权威 item_id 注入（snapshot 值不含 item_id → 否则保存时 items 缺 item_id 触发 422）
      map.set(k, (v && typeof v === 'object') ? { item_id: k, ...v } : { item_id: k, remark: v })

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

.d1-global-alerts {

  display: flex;

  flex-direction: column;

  gap: 8px;

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

