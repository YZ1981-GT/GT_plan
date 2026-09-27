<template>
  <div class="h10-asset-disposal-income">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== '底稿目录'" class="h10-toolbar">
        <!--
          🔴 切换器改 `v-model` 且**不带 `:disabled`**：健康检查是 mount 期异步，
          disabled 在未就绪时会把「在线编辑」锁死、点击被彻底吞掉 —— D4 已实证的 bug ③。
          健康门禁移进 `useHSyncMode.switchMode`（await 兜底），切换器保持可点。
        -->
        <el-segmented v-model="currentMode" :options="modeOptions" size="small" />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-tag size="small" :type="hSync.syncStateTag.value.type">
          {{ hSync.syncStateTag.value.text }}
        </el-tag>
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-h10-asset-disposal-income" />
      </div>

      <!--
        受管 sheet（H10-3 调整分录汇总）的在线编辑 —— 统一双向宿主。
        🔴 `.oo-container` 必须有**确定高度**（D4 踩过 height:100% 被压成一条）。
      -->
      <div
        v-if="isHtmlSheet && currentSheet !== '底稿目录' && currentMode === 'onlyoffice' && isH10SyncManagedSheet"
        class="oo-container"
      >
        <WorkpaperSyncEditorHost
          ref="syncEditorHostRef"
          :descriptor="hSync.descriptor.value"
          :bridge="hSync.syncBridge"
        />
      </div>

      <!-- 非受管 sheet 的 OnlyOffice 模式（legacy 只读视图，无双向回写） -->
      <GtOnlyOfficeSheet
        v-else-if="isHtmlSheet && currentSheet !== '底稿目录' && currentMode === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
        @fallback="onOoLoadFailed"
      />

      <H10TabProcedure
        v-else-if="currentSheet === 'H10A'"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <template v-else-if="currentSheet === 'H10-1'">
        <!--
          🔴 `:all-responses` / `@refresh-complete` 原为 `allResponses` / `selfLoad()` ——
          这两个标识符在**本宿主里不存在**（H5/H7 等宿主有自己的 `allResponses` ref 与
          `selfLoad`，H10 走 `useH10FormData`）。把本宿主纳入 `tsconfig._h-cycle-sync.json`
          后 vue-tsc 两条 TS2339 当场暴露：面板拿到 `undefined`、`@refresh-complete` 一触发
          就是 ReferenceError。改为本宿主真实存在的 `formData.allResponses.value` /
          `reloadAll()`（与下方 `H10TabAdjudication` 的写法一致）。
        -->
        <HiFourTableSourcePanel
          v-if="props.htmlData?.hi_extraction_enabled"
          :wp-code="'H10'"
          :segments="getHiExtractionSegments('H10')"
          :all-responses="formData.allResponses.value"
          :is-readonly="isReadonly"
          @refresh-complete="reloadAll()"
        />
        <H10TabAdjudication
          :all-responses="formData.allResponses.value"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          :debounced-save="onDebouncedSave"
          @imported="reloadAll"
        />
      </template>

      <H10TabDetail
        v-else-if="currentSheet === 'H10-2'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <H10TabAdjustment
        v-else-if="currentSheet === 'H10-3'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
        @imported="reloadAll"
      />

      <H10TabCheck
        v-else-if="currentSheet === 'H10-4'"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :year="runtime?.year?.value"
        :debounced-save="onDebouncedSave"
      />

      <H10TabDisclosureBase
        v-else-if="currentSheet === '附注上市'"
        variant="listed"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <H10TabDisclosureBase
        v-else-if="currentSheet === '附注国企'"
        variant="soe"
        :all-responses="formData.allResponses.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
        :is-readonly="isReadonly"
        :debounced-save="onDebouncedSave"
      />

      <div v-else-if="currentSheet === '底稿目录'" class="h-cycle-tab-index-page">
        <H10TabDirectory
          :all-responses="formData.allResponses.value"
          :available-sheets="availableSheets"
        />
        <GCycleBIndexExtras
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName"
          :wp-code="props.wpCode"
          :html-data="props.htmlData"
          :available-sheets="availableSheets"
          :all-responses="formData.allResponses.value"
          :show-architecture="false"
        />
      </div>

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

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtH10AssetDisposalIncome — H10 资产处置损益主入口
 * 科目 6115 损益类；EventBus: disposal:completed(H6) / substantive:adjudicated(6115)
 */
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent, provide, inject} from 'vue'
import { useH10FormData } from './composables/useH10FormData'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { useHSyncMode } from './composables/useHSyncMode'

/** H10 entry id（manifest 冻结值，与 `phase5_h10_asset_disposal_income.ENTRY_ID` 逐字一致）。 */
const H10_SYNC_ENTRY_ID = 'xlsx/gt-h10-asset-disposal-income'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import type { ChecklistResponse } from './composables/useF1FormData'
import HiFourTableSourcePanel from './shared/HiFourTableSourcePanel.vue'
import { getHiExtractionSegments } from './composables/hiExtractionSegments'
import { useHostApplicableStandards } from './composables/hostApplicableStandards'

const H10TabProcedure = defineAsyncComponent(() => import('./h10/core/H10TabProcedure.vue'))
const H10TabAdjudication = defineAsyncComponent(() => import('./h10/core/H10TabAdjudication.vue'))
const H10TabDetail = defineAsyncComponent(() => import('./h10/core/H10TabDetail.vue'))
const H10TabAdjustment = defineAsyncComponent(() => import('./h10/core/H10TabAdjustment.vue'))
const H10TabCheck = defineAsyncComponent(() => import('./h10/inspection/H10TabCheck.vue'))
const H10TabDisclosureBase = defineAsyncComponent(() => import('./h10/core/H10TabDisclosureBase.vue'))
const H10TabDirectory = defineAsyncComponent(() => import('./h10/core/H10TabDirectory.vue'))
const GCycleBIndexExtras = defineAsyncComponent(() => import('./shared/GCycleBIndexExtras.vue'))
const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{ (e: 'jump-to-section', sheetName: string): void }>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const formData = useH10FormData({ wpId: wpIdRef, projectId: projectIdRef })
const isReadonly = computed(() => !!props.readonly)
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)

// 适用准则：显式 prop > 本 sheet html_data > runtime context（scaffold 从 render-config
// 顶层注入）。收敛到共享 composable，兼容 v2 对象 / 逗号串 / JSON 串。
const applicableStandards = useHostApplicableStandards({
  explicit: () => props.applicableStandards,
  htmlData: () => props.htmlData,
})

const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('h10VersionTrailRef', versionTrailRef)
provide('h10OpenVersionHistory', openVersionHistory)

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/底稿目录/.test(name)) return '底稿目录'
  if (/附注披露/.test(name)) {
    return name.includes('国有') || name.includes('国企') ? '附注国企' : '附注上市'
  }
  const m = name.match(/(H10A|H10-\d+)/)
  return m ? m[1] : ''
})

const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['H10A', 'H10-1', 'H10-2', 'H10-3', 'H10-4', '底稿目录'].includes(s) || s.startsWith('附注')
})

// ─── 双模式切换（统一接桥，替代 useH10DualMode）───────────────────────────────
//
// 原实现是 `useH10DualMode`（112 行，宿主专属、把视图模式字符串存进浏览器本地偏好，
// 键前缀 `h10-dual-mode:`）。它**不建桥** ⇒ OO 侧编辑回不到 HTML。
//
// 🔴 本段刻意**不写出那个浏览器存储 API 的名字**：`test_h_foundation_hc_guards` 的 HC-10
//    判据按「文件文本里是否出现该 API 名」分类，宿主出现即被记成「第三处客户端存储」。
//    H10 的草稿存储在 `useH10FormData`（键按 itemId 分片），宿主自己一处都没有 ——
//    在注释里提一句就会把它误记进去。键前缀 `h10-dual-mode:` 已足够定位原实现。
//
// 🔴 受管 sheet 是 **H10-3 调整分录汇总**，不是模板里的 `明细表H10-2`：后者是 9 类固定行
//    × 12 月矩阵而本前端零月度建模（结构性不匹配，实测反驳了规划期 slice 的配对）。
//    改配后映射率 6/10 是全 H 最高档。依据见后端契约 `review.declared_coverage_gaps`
//    的 H10-GAP-1。
const hSync = useHSyncMode({
  entryId: H10_SYNC_ENTRY_ID,
  wpId: wpIdRef,
  projectId: projectIdRef,
  currentCode: computed(() => currentSheet.value),
  isReadonly,
  flushHtml: async () => {
    // 🔴 H10 是 `formdata_composable` 载体且实例就在宿主里 ⇒ 直接 flush，不需要
    //    `sync/hPendingWrites` 那层模块级注册表（那是 H5/H7 的 per_tab_* 载体才要的）。
    //    防抖窗口 **2000ms**（与 H3/H5 并列最长），漏 flush 会静默丢最多 2 秒的编辑。
    await formData.flushPendingSaves()
    const snap = await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: H10_SYNC_ENTRY_ID,
    })
    return {
      expectedRevision: snap.expectedRevision,
      projection: snap.projection,
      sheetKey: hSync.sheetKey.value,
    }
  },
  reloadHtml: async () => { await formData.loadAll() },
})

/** 模板 `ref="syncEditorHostRef"` 的落点 —— 直接复用桥里的 ref。 */
const syncEditorHostRef = hSync.syncHostRef
const isH10SyncManagedSheet = computed(() => hSync.isManagedSheet.value)
const modeOptions = hSync.modeOptions
const currentMode = hSync.renderMode

/** legacy OO 组件加载失败的兜底（只对**非受管** sheet 生效）。 */
function onOoLoadFailed(): void {
  void hSync.switchMode('html')
}

const useGridFallback = computed(() => !!currentSheet.value && !isHtmlSheet.value)

function onDebouncedSave(itemId: string, data: Partial<ChecklistResponse>) {
  formData.debouncedSave(itemId, data)
  scheduleAutoSnapshot()
}

async function reloadAll() {
  await formData.loadAll()
}

const availableSheets = computed(() =>
  props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets ?? [],
)

function handleDisposalCompleted(ev: Event) {
  const detail = (ev as CustomEvent).detail ?? {}
  formData.handleDisposalCompleted(detail)
}

function handleSourceDisposalUpdated(ev: Event) {
  const detail = (ev as CustomEvent).detail ?? {}
  formData.handleSourceDisposalUpdated(detail)
}

// spec: tb-writeback-explicit-publish-gate Task 10 / Req 1,2 —— 移除原「跨 wp 收到 6115 审定事件即
// 自动 formData.writebackTrialBalance 写 TB」的旁路（自动写、无确认，违反 Req 1/2）。H10 的 TB 回写
// 一律经 H10TabAdjudication 的显式发布门（adj.publishToTb 中文二次确认）。跨 wp 处置明细带入仍走
// disposal:completed（handleDisposalCompleted 只追加 H10-2 明细行，不写 TB）。

useWorkpaperReviewProvide({ wpId: wpIdRef, projectId: projectIdRef })
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

useWorkpaperEntryInjections({ onJumpToSection: sheetLabel => emit('jump-to-section', sheetLabel), reloadFn: reloadAll })

onMounted(async () => {
  window.addEventListener('disposal:completed', handleDisposalCompleted)
  window.addEventListener('disposal:source-updated', handleSourceDisposalUpdated)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('disposal:completed', handleDisposalCompleted)
  window.removeEventListener('disposal:source-updated', handleSourceDisposalUpdated)
})
</script>

<style scoped>
.h10-asset-disposal-income { padding: 12px; }
.loading-container { padding: 24px; }
.h10-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }

/*
 * 🔴 `height: 100%` 会被父级压成一条（D4 踩过）：OnlyOffice iframe 需要
 *    **确定**高度才撑得开，min-height 兜住父级无高度时的退化。
 */
.oo-container { width: 100%; min-height: 600px; height: calc(100vh - 200px); }
</style>
