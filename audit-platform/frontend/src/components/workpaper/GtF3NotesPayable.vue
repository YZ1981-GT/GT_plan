<template>

  <div class="f3-notes-payable">

    <div v-if="isLoading" class="loading-container">

      <el-skeleton :rows="8" animated />

    </div>



    <template v-else>

      <div v-if="showHtmlToolbar" class="f3-header-toolbar">

        <el-segmented

          v-model="renderMode"

          :options="dualMode.modeOptions"

          size="small"

          :disabled="isF3SyncManagedSheet && syncBusy"

        />

        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>

        <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>

        <el-tag v-if="isF3SyncManagedSheet && syncBusy" size="small" type="info">同步中…</el-tag>
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-f3-notes-payable" />
      </div>



      <!-- 在线编辑模式：受管 sheet 走 WorkpaperSyncEditorHost（真双向），非受管走 legacy GtOnlyOfficeSheet -->
      <!-- F3-5 canary 真双向路径（spec: f3-sync-coverage-and-first-canary） -->
      <div
        v-if="renderMode === 'onlyoffice' && isF3SyncManagedSheet"
        class="oo-container"
      >
        <WorkpaperSyncEditorHost
          ref="syncEditorHostRef"
          :descriptor="syncOoDescriptor"
          :bridge="syncBridge"
        />
      </div>

      <!-- 非受管 sheet 保留 legacy GtOnlyOfficeSheet（假双向，如实登记） -->
      <GtOnlyOfficeSheet

        v-else-if="renderMode === 'onlyoffice'"

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

          :tb-amount="tbAmount2201"

          :adjudication-prefill="props.htmlData?.adjudication_prefill"

          :tb-source-codes="props.htmlData?.project_context?.tb_source_codes"

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



      <!-- 版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->

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

import { ref, computed, onMounted, onBeforeUnmount, provide, toRef, inject, defineAsyncComponent } from 'vue'

import { useF3FormData, type ChecklistResponse } from './composables/useF3FormData'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'

import { useF3CrossSheet } from './composables/useF3CrossSheet'

import { useF3DualMode } from './composables/useF3DualMode'

import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useHostApplicableStandards } from './composables/hostApplicableStandards'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'



const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
// F3-5 canary 真双向（spec: f3-sync-coverage-and-first-canary）
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'



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



// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供 ───

const runtime = inject(WorkpaperRuntimeContextKey, null)

const versionToolbar = runtime?.version ?? {
  versionTrailRef: ref<{ openDrawer: () => void } | null>(null),
  openVersionHistory: () => undefined,
  scheduleAutoSnapshot: () => undefined,
  wrapSaveImmediate: (<T,>(fn: T): T => fn),
}

const { versionTrailRef, openVersionHistory } = versionToolbar

provide('f3VersionTrailRef', versionTrailRef)
provide('f3OpenVersionHistory', openVersionHistory)



const dualMode = useF3DualMode({

  wpId: toRef(props, 'wpId'),

  projectId: toRef(props, 'projectId'),

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



// ─── F3-5 canary：useWorkpaperSyncBridge 真双向 ───────────────────────────────
//
// 🔴 只覆盖 F3-5「逾期应付票据检查表」（manifest entry 的受管 sheet = f35-managed）。
// 其余 sheet 仍走 legacy GtOnlyOfficeSheet（假双向），如实登记不假装已接。
// F3 是单册、一 entry ⇒ 所有受管 sheet 共用同一 entry_id（不随 sheet 变），
// 具体是哪张 sheet 由 flushHtml 回传的 sheetKey 告知后端。
const F3_SYNC_ENTRY_ID = 'xlsx/gt-f3-notes-payable'
/** 受管 sheet 清单：wp sheet code → 契约 sheet_key（与 provider 受管清单一致）。 */
const F3_SHEET_KEY_BY_CODE: Record<string, string> = {
  'F3-5': 'f35-managed',
}
/** 当前 sheet 是否走 syncBridge 真双向路径。 */
const isF3SyncManagedSheet = computed(() => currentSheet.value in F3_SHEET_KEY_BY_CODE)
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const syncEntryId = ref(F3_SYNC_ENTRY_ID)
const syncSheetKey = computed(() => F3_SHEET_KEY_BY_CODE[currentSheet.value] || 'f35-managed')
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  capability: capabilityForEntry(F3_SYNC_ENTRY_ID),
  flushHtml: async () => {
    // 🔴 顺序不可换：先 flush 掉 2s debounce 未落库的行，再读 store projection。
    // 否则读到的是旧快照，切到 OO 侧后会用旧值覆盖 HTML 侧刚写的编辑。
    formData.flushPendingSave()
    const snap = await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: F3_SYNC_ENTRY_ID,
    })
    return {
      expectedRevision: snap.expectedRevision,
      projection: snap.projection,
      sheetKey: syncSheetKey.value,
    }
  },
  reloadHtml: async (_minimumRevision: number) => {
    await formData.loadAll()
  },
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncSwitching = ref(false)
const syncBusy = computed(() =>
  syncSwitching.value
  || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)

// ─── 🔴 受管 sheet 的模式切换协议（照 D3 switchRenderMode 4 分支）───────────
//
// dualMode.onModeChange 只翻 currentMode ref，**不走 syncBridge 的保存流程**。
// 用户编辑后未保存直接切模式 ⇒ OO 侧编辑数据丢失（forceSave 没发、room 没关）。
//
// 正确做法：受管 sheet 的模式切换由 `renderMode` computed setter 拦截，走 syncBridge
// 的 4 条精细分支（已保存 / 未改动 / 有改动可保存 / 兜底）。非受管仍走 dualMode 原路径。
type F3RenderMode = 'html' | 'onlyoffice'

const renderMode = computed({
  get: (): F3RenderMode =>
    isF3SyncManagedSheet.value
      ? (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html')
      : dualMode.currentMode.value,
  set: (v: F3RenderMode) => {
    if (isF3SyncManagedSheet.value) void switchRenderMode(v)
    else void dualMode.switchMode(v)
  },
})

/**
 * 受管 sheet 的 4 分支保存协议（照 D3 switchRenderMode）。
 *
 *   html→oo：syncBridge.switchToOnlyOffice()（内部 flush + pending + materialize）
 *   oo→html（已 applied）：syncBridge.reloadAfterApplied()
 *   oo→html（未改动 dirty=false）：syncBridge.leaveWithoutSaving()（clean close，不发 forceSave）
 *   oo→html（有改动 canForcesave）：syncEditorHostRef.forceSave()
 *   兜底：syncBridge.persistMode('html')
 *
 * 🔴 铁律：用户已保存（点过保存按钮） ⇒ 切换丝滑（applied 分支无网络调用）；
 *   用户未保存（dirty=true）⇒ 切换时自动 forceSave（等待 OO 确认，略慢是正常的）；
 *   用户未编辑（dirty=false）⇒ clean close（零网络调用）。
 */
async function switchRenderMode(target: F3RenderMode): Promise<void> {
  if (target === renderMode.value) return
  if (target === 'onlyoffice') {
    if (!isF3SyncManagedSheet.value) return
    syncSwitching.value = true
    try {
      await syncBridge.switchToOnlyOffice()
    } catch {
      // lastError / feedback 已由桥写入；保持 html
    } finally {
      syncSwitching.value = false
    }
    return
  }
  // → html
  if (syncBridge.mode.value !== 'oo') {
    syncBridge.persistMode('html')
    return
  }
  syncSwitching.value = true
  try {
    if (String(syncBridge.state.value) === 'applied') {
      await syncBridge.reloadAfterApplied()
    } else if (syncBridge.mode.value === 'oo' && !syncBridge.dirty.value) {
      // 一个字都没改就切回结构化视图 ⇒ clean close，不发 forceSave。
      await syncBridge.leaveWithoutSaving()
    } else if (syncBridge.canForcesave.value && syncEditorHostRef.value) {
      // 🔴 有改动且 forceSave 可用 ⇒ 先保存再切（用户体验：切换略慢但不丢数据）。
      await syncEditorHostRef.value.forceSave()
    } else {
      syncBridge.persistMode('html')
    }
  } catch {
    // 保持 OO；错误在桥上
  } finally {
    syncSwitching.value = false
  }
}

const showHtmlToolbar = computed(() => {

  const s = currentSheet.value

  return s.startsWith('F3-') || s === 'F3A' || s.startsWith('附注')

})



// 适用准则：显式 prop > 本 sheet html_data > runtime context（scaffold 从 render-config
// 顶层注入）。收敛到共享 composable，兼容 v2 对象 / 逗号串 / JSON 串。
const applicableStandards = useHostApplicableStandards({
  explicit: () => formData.projectContext.value?.applicable_standards,
  htmlData: () => props.htmlData,
})

// 2201 应付票据 TB 核对标量（render tb_values['2201']，trial_balance/tb_balance）：
// 供 F3-1 审定表「试算平衡表数」只读回退 seed（四表入库刷新即有核对基准）。
const tbAmount2201 = computed<number | null>(() => {
  const tv = props.htmlData?.tb_values ?? (formData.projectContext.value as any)?.tb_values
  const v = tv?.['2201']
  return v != null ? (Number(v) || 0) : null
})



const auditYear = computed(() => {

  if (props.year) return props.year

  const bs = formData.projectContext.value?.bs_date

  if (bs && String(bs).length >= 4) return parseInt(String(bs).slice(0, 4), 10)

  return new Date().getFullYear() - 1

})



// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide（真实复核对话）

provide('reloadWorkpaperData', () => formData.loadAll())

// ─── 复核圆点 ─────────────────────────────────────────────────────────────────
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

async function handleF3SaveItems(e: Event): Promise<void> {

  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items

  if (Array.isArray(items) && items.length > 0) {

    await formData.saveItemsFromEvent(items)

    versionToolbar.scheduleAutoSnapshot()

  }

}



// ─── TB 回写：已移除 f3:writeback-trial-balance 监听器（spec tb-writeback-explicit-publish-gate Task 3） ──
// 原 handleF3Writeback 监听 window 'f3:writeback-trial-balance' → useF3FormData.writebackTrialBalance
// 落库 trial_balance，绕过显式确认门。改造后 TB 回写由 F3TabAdjudication.publishToTb
// （显式二次确认 → publish-to-tb 端点）承载；publishAdjudicated 只 emit substantive:adjudicated。

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

  void selfLoad()

})



onBeforeUnmount(() => {

  window.removeEventListener('f3:save-items', handleF3SaveItems)

})

</script>



<style scoped>

.f3-notes-payable {

  padding: 12px;

}

/* F3-5 canary：WorkpaperSyncEditorHost 自身不带高度，容器须给足否则编辑器塌成 0 高 */
.oo-container {
  min-height: 600px;
  height: calc(100vh - 200px);
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

