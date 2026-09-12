<template>
  <div class="d2-accounts-receivable">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 双模式工具栏 -->
      <div v-if="showModeToolbar" class="d2-mode-toolbar">
        <el-segmented
          v-model="renderMode"
          :options="renderModeOptions"
          size="small"
        />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d2-accounts-receivable" />
        <!-- 运行时同步状态：区分「正在同步 / 不可用原因 / 上次结果」，不合并成一句「成功」 -->
        <el-tag v-if="syncBusy" type="warning" size="small">
          同步中…
        </el-tag>
        <el-tooltip
          v-else-if="syncUnavailableReason"
          :content="syncUnavailableReason"
          placement="bottom"
        >
          <el-tag type="danger" size="small">在线编辑不可用</el-tag>
        </el-tooltip>
        <el-tooltip
          v-else-if="syncFeedbackOk"
          :content="syncFeedbackOk"
          placement="bottom"
        >
          <el-tag type="success" size="small">已同步</el-tag>
        </el-tooltip>
        <el-tag v-if="saving" type="info" size="small">保存中…</el-tag>
      </div>

      <!-- 勾稽差异提示 -->
      <el-alert
        v-if="!crossSheet.reconciliationDiff.value.isBalanced"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
      >
        <template #title>
          D2-1审定表合计({{ fmtAmt(crossSheet.reconciliationDiff.value.adjTotal) }})
          与D2-2明细表合计({{ fmtAmt(crossSheet.reconciliationDiff.value.detailTotal) }})
          差异 {{ fmtAmt(crossSheet.reconciliationDiff.value.diff) }} 元，请核实
        </template>
      </el-alert>
      <el-alert
        v-if="crossSheet.detailVsTbDiff.value && !crossSheet.detailVsTbDiff.value.isBalanced"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
      >
        <template #title>
          D2-2明细表合计({{ fmtAmt(crossSheet.detailVsTbDiff.value.detailTotal) }})
          与TB科目1122审定额({{ fmtAmt(crossSheet.detailVsTbDiff.value.tbAmount) }})
          差异 {{ fmtAmt(crossSheet.detailVsTbDiff.value.diff) }} 元，请核实
        </template>
      </el-alert>
      <!-- ECL↔坏账准备期末勾稽（全局提示；ECL tab 内已单独展示，此处避免重复） -->
      <el-alert
        v-if="currentSheet !== 'D2-9' && currentSheet !== 'D2-10'
          && crossSheet.eclVsBadDebtDiff.value && !crossSheet.eclVsBadDebtDiff.value.isBalanced"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
      >
        <template #title>
          D2-10 ECL单项合计({{ fmtAmt(crossSheet.eclVsBadDebtDiff.value.eclTotal) }})
          与D2-3坏账准备期末({{ fmtAmt(crossSheet.eclVsBadDebtDiff.value.badDebtCurrent) }})
          差异 {{ fmtAmt(crossSheet.eclVsBadDebtDiff.value.diff) }} 元，请核实
        </template>
      </el-alert>

      <!-- OnlyOffice 在线编辑（统一路径：descriptor → WorkpaperSyncEditorHost） -->
      <!-- D2-2 canary：只在明细表走 USER_SYNC_PREFIX；其它 sheet 不挂 legacy GtOnlyOfficeSheet -->
      <WorkpaperSyncEditorHost
        v-if="renderMode === 'onlyoffice' && isD2DetailSheet"
        ref="syncEditorHostRef"
        :descriptor="syncOoDescriptor"
        :bridge="syncBridge"
      />

      <!-- HTML 结构化视图 -->
      <template v-else>
      <!-- D2 主入口 / 目录 -->
      <D2TabIndex
        v-if="currentSheet === 'D2' || currentSheet === '目录'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />

      <!-- 程序表 D2A -->
      <D2TabProcedure
        v-else-if="currentSheet === 'D2A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :html-data="props.htmlData"
        :is-readonly="isReadonly"
      />

      <!-- 核心组 -->
      <D2TabAdjudication
        v-else-if="currentSheet === 'D2-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :html-data="props.htmlData"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />
      <D2TabDetail
        v-else-if="currentSheet === 'D2-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
        :related-parties="relatedParties"
        :bs-date="bsDate"
      />
      <D2TabBadDebt
        v-else-if="currentSheet === 'D2-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />
      <D2TabAdjustment
        v-else-if="currentSheet === 'D2-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />

      <!-- 附注披露（上市公司） -->
      <D2TabDisclosure
        v-else-if="currentSheet === '附注上市'"
        variant="listed"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />

      <!-- 附注披露（国企） -->
      <D2TabDisclosure
        v-else-if="currentSheet === '附注国企'"
        variant="soe"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />

      <!-- 分析程序 -->
      <D2TabAnalysis
        v-else-if="currentSheet === 'D2-5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />

      <!-- 检查程序组 -->
      <D2TabRelatedParty
        v-else-if="currentSheet === 'D2-6'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />
      <D2TabVoucherCheck
        v-else-if="currentSheet === 'D2-7'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
        :bs-date="bsDate"
      />
      <D2TabPolicyCheck
        v-else-if="currentSheet === 'D2-8'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />
      <D2TabEcl
        v-else-if="currentSheet === 'D2-9'"
        ecl-focus="D2-9"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />
      <D2TabEcl
        v-else-if="currentSheet === 'D2-10'"
        ecl-focus="D2-10"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />
      <D2TabWriteoffCheck
        v-else-if="currentSheet === 'D2-11'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />
      <D2TabPledgeCheck
        v-else-if="currentSheet === 'D2-12'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />
      <D2TabBizModel
        v-else-if="currentSheet === 'D2-13'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />
      <D2TabCutoff
        v-else-if="currentSheet === '截止测试' || (props.sheetName && props.sheetName.includes('截止'))"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
        :bs-date="bsDate"
      />

      <!-- 未迁移 sheet → OnlyOffice 降级 -->
      <GtOnlyOfficeSheet
        v-else-if="useOnlyOfficeFallback"
        :key="props.sheetName"
        :wp-id="props.wpId"
        :sheet-name="props.sheetName || ''"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @fallback="onlyOfficeFallback = true"
      />

      <!-- 最终兜底：目录 -->
      <D2TabIndex
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />
      </template>
    </template>

    <GtWpReviewRail
      v-if="!isLoading && renderMode !== 'onlyoffice'"
      :section-id="d2ReviewSection.id"
      :section-label="d2ReviewSection.label"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * GtD2AccountsReceivable.vue — D2 应收账款底稿主入口
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, toRef, defineAsyncComponent, type Ref } from 'vue'
import { useAgingConfig } from '@/composables/useAgingConfig'
import { useD2FormData, type ChecklistResponse } from './composables/useD2FormData'
import { useD2CrossSheet } from './composables/useD2CrossSheet'
// 2026-09-10: DEC-10 解除后迁统一路径。`useD2SyncBridge` + `/d2-sync/*` 仍保留
// 至 ONLYOFFICE_VERIFIED（DEC-08），但本宿主不再调用它们。
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'
// Re-export getSheetNameFromD2Code which was also in the deleted module.
// The sheet name resolution function is kept inline since it's pure data.
const D2_SHEET_MAP: Record<string, string> = {
  D2: 'D2', 目录: 'D2', D2A: 'D2A',
  'D2-1': 'D2-1', 'D2-2': 'D2-2', 'D2-3': 'D2-3', 'D2-4': 'D2-4',
  'D2-5': 'D2-5', 'D2-6': 'D2-6', 'D2-7': 'D2-7', 'D2-8': 'D2-8',
  'D2-9': 'D2-9', 'D2-10': 'D2-10', 'D2-11': 'D2-11', 'D2-12': 'D2-12',
  'D2-13': 'D2-13',
  附注上市: '附注披露信息(上市公司)', 附注国企: '附注披露信息(国企)',
  截止测试: '截止测试',
}
function getSheetNameFromD2Code(code: string): string {
  if (D2_SHEET_MAP[code]) return D2_SHEET_MAP[code]
  if (code.includes('截止')) return code
  return code
}
type D2RenderMode = 'html' | 'onlyoffice'
const D2_SYNC_ENTRY_ID = 'xlsx/gt-d2-accounts-receivable'
/** 与后端 D2 managed sheet_key / materialize 取证脚本一致。 */
const D2_MANAGED_SHEET_KEY = 'd22-managed'
import { resolveCycleReviewSection } from './composables/cycleReviewSectionMap'
import GtWpReviewRail from './GtWpReviewRail.vue'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useD2ReviewThreads } from './composables/useD2ReviewThreads'
import { D2_SAVE_ITEMS_KEY, D2_WRITEBACK_KEY } from './composables/d2InjectionKeys'
import { normalizeD2SheetName } from './composables/d2Constants'
import D2TabIndex from './d2/D2TabIndex.vue'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'

const D2TabProcedure = defineAsyncComponent(() => import('./d2/D2TabProcedure.vue'))
const D2TabAdjudication = defineAsyncComponent(() => import('./d2/D2TabAdjudication.vue'))
const D2TabDetail = defineAsyncComponent(() => import('./d2/D2TabDetail.vue'))
const D2TabBadDebt = defineAsyncComponent(() => import('./d2/D2TabBadDebt.vue'))
const D2TabAdjustment = defineAsyncComponent(() => import('./d2/D2TabAdjustment.vue'))
const D2TabDisclosure = defineAsyncComponent(() => import('./d2/D2TabDisclosure.vue'))
const D2TabAnalysis = defineAsyncComponent(() => import('./d2/D2TabAnalysis.vue'))
const D2TabRelatedParty = defineAsyncComponent(() => import('./d2/D2TabRelatedParty.vue'))
const D2TabVoucherCheck = defineAsyncComponent(() => import('./d2/D2TabVoucherCheck.vue'))
const D2TabPolicyCheck = defineAsyncComponent(() => import('./d2/D2TabPolicyCheck.vue'))
const D2TabEcl = defineAsyncComponent(() => import('./d2/D2TabEcl.vue'))
const D2TabWriteoffCheck = defineAsyncComponent(() => import('./d2/D2TabWriteoffCheck.vue'))
const D2TabPledgeCheck = defineAsyncComponent(() => import('./d2/D2TabPledgeCheck.vue'))
const D2TabBizModel = defineAsyncComponent(() => import('./d2/D2TabBizModel.vue'))
const D2TabCutoff = defineAsyncComponent(() => import('./d2/D2TabCutoff.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
  (e: 'jump-to-section', sheetName: string): void
}>()

const isReadonly = computed(() => !!props.readonly)
const runtime = inject(WorkpaperRuntimeContextKey, null)

const formData = useD2FormData(toRef(props, 'wpId'), toRef(props, 'projectId'), toRef(props, 'htmlData'))
const allResponses = computed(() => formData.allResponses.value)
const saving = formData.saving

/**
 * 项目账龄配置（枚举账龄：3年段 / 5年段 / 自定义）——D2 全部账龄口径的单一真源。
 * 审定表/明细/分析/ECL/政策检查/披露表都消费这一份，禁止各 tab 自建段清单。
 */
const { segments: d2AgingSegments, preset: d2AgingPreset } = useAgingConfig(
  toRef(props, 'projectId') as Ref<string>,
  'D2',
)
const crossSheet = useD2CrossSheet({ allResponses, agingSegments: d2AgingSegments })

// D2 只消费 GtWpRenderer 已初始化的版本能力，不再创建第二个 toolbar/Host。
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

const bsDate = computed(() => {
  const ctx = props.htmlData?.project_context ?? props.htmlData?.projectContext
  if (ctx?.bs_date) return ctx.bs_date
  if (props.year) return `${props.year}-12-31`
  return ''
})

/** 金额格式化(千分位 + 2位小数) */
function fmtAmt(v: number): string {
  if (v == null || Number.isNaN(v)) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const relatedParties = computed<string[]>(() => {
  const raw = props.htmlData?.project_context?.related_parties
  return Array.isArray(raw) ? raw : []
})

const isLoading = ref(true)
const onlyOfficeFallback = ref(false)
const syncSwitching = ref(false)

/** 统一宿主实例 —— 切回结构化视图前用它 `forceSave()`（内部走 room forcesave）。 */
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)

const currentSheet = computed(() => normalizeD2SheetName(props.sheetName))
/** 统一路径 canary 仅覆盖 D2-2 明细表（manifest entry 的 managed sheet）。 */
const isD2DetailSheet = computed(() => currentSheet.value === 'D2-2')

const d2ReviewSection = computed(() => resolveCycleReviewSection('D2', currentSheet.value))

// ─── G4 host canary：useWorkpaperSyncBridge + store-projection flush ─────────
//
// 🔴 flushHtml 必须先 flushPendingSave，再 readStoreProjection：HTML debounce 未落库
// 时服务端投影仍是旧 store（与 2026-09-06 缺陷 A 同型）。
// 🔴 不得在前端重造 39 列→stable-key 映射（Requirement 6.1）；overlay 脚手架由服务端
// store-projection 叠加（DEC-10 解除后的 materialize-ready 语义）。
const syncEntryId = ref(D2_SYNC_ENTRY_ID)
const syncSheetKey = ref(D2_MANAGED_SHEET_KEY)
const syncBridge = useWorkpaperSyncBridge({
  entryId: syncEntryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: syncSheetKey,
  // 谓词 8：capability 从 source-backed manifest 现算，禁止宿主内联字面量
  capability: capabilityForEntry(D2_SYNC_ENTRY_ID),
  flushHtml: async () => {
    await formData.flushPendingSave()
    const snap = await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: D2_SYNC_ENTRY_ID,
    })
    return {
      expectedRevision: snap.expectedRevision,
      projection: snap.projection,
      sheetKey: D2_MANAGED_SHEET_KEY,
    }
  },
  reloadHtml: async (_minimumRevision: number) => {
    await formData.loadAll()
  },
})

/** 避免 `:descriptor="syncBridge.descriptor.value"` 丢失对 ref 的追踪 */
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)

const syncBusy = computed(
  () =>
    syncSwitching.value
    || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
const syncUnavailableReason = computed(() => {
  if (!isD2DetailSheet.value) {
    return '统一路径 canary 仅开放 D2-2 明细表在线编辑'
  }
  const err = syncBridge.lastError.value
  return err ? `${err.errorCode}: ${err.message}` : ''
})
const syncFeedbackOk = computed(() => {
  const fb = syncBridge.feedback.value
  return fb.kind === 'success' ? fb.message : ''
})

const renderMode = computed({
  get: (): D2RenderMode => (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html'),
  set: (v: D2RenderMode) => {
    void switchRenderMode(v)
  },
})

const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  {
    label: '在线编辑',
    value: 'onlyoffice' as const,
    disabled: !isD2DetailSheet.value || isReadonly.value,
  },
])

async function switchRenderMode(target: D2RenderMode): Promise<void> {
  if (target === renderMode.value) return
  if (target === 'onlyoffice') {
    if (!isD2DetailSheet.value) return
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
      // 回写已完成但自动 reload 未跑完时，点结构化视图应主动 reload（§9.6）
      await syncBridge.reloadAfterApplied()
    } else if (syncBridge.canForcesave.value && syncEditorHostRef.value) {
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

const KNOWN_HTML_SHEETS = new Set([
  'D2', '目录', 'D2A',
  'D2-1', 'D2-2', 'D2-3', 'D2-4', 'D2-5', 'D2-6', 'D2-7', 'D2-8',
  'D2-9', 'D2-10', 'D2-11', 'D2-12', 'D2-13',
  '附注上市', '附注国企', '截止测试',
])

const showModeToolbar = computed(() =>
  currentSheet.value !== 'skip' && currentSheet.value !== 'D2' && currentSheet.value !== '目录' && KNOWN_HTML_SHEETS.has(currentSheet.value),
)

const useOnlyOfficeFallback = computed(() => {
  if (onlyOfficeFallback.value) return false
  return props.sheetName != null && !KNOWN_HTML_SHEETS.has(currentSheet.value)
})

const wpIdRef = toRef(props, 'wpId')

const { getThreadDot, getRowDot } = useD2ReviewThreads(wpIdRef)
provide('d2GetThreadDot', getThreadDot)
provide('d2GetRowDot', getRowDot)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

provide('d2CrossSheet', crossSheet)
provide('d2AgingSegments', d2AgingSegments)
provide('d2AgingPreset', d2AgingPreset)
provide('d2VersionTrailRef', runtime?.version.versionTrailRef)
provide('d2OpenVersionHistory', openVersionHistory)

// ─── P0-2: provide/inject 替代 window event ──────────────────────────────
// 子 tab 通过 inject(D2_SAVE_ITEMS_KEY) 保存数据，不再用全局 window.dispatchEvent。
// 优势：类型安全、组件隔离（同页面多 D2 实例不冲突）、无需生命周期管理。
async function d2SaveItems(items: ChecklistResponse[]): Promise<void> {
  if (!Array.isArray(items) || items.length === 0) return
  try {
    await formData.saveItemsFromEvent(items)
    scheduleAutoSnapshot()
    emit('save')
  } catch {
    // Adapter 已保留 dirty/error 状态并由 useD2FormData 给出可见错误；失败时不发保存事件/快照。
  }
}

function d2Writeback(accountCode: string, auditedAmount: number): void {
  if (accountCode != null && auditedAmount != null) {
    void formData.writebackTrialBalance(accountCode, auditedAmount)
  }
}

provide(D2_SAVE_ITEMS_KEY, d2SaveItems)
provide(D2_WRITEBACK_KEY, d2Writeback)

// 向后兼容：保留 window event 监听，过渡期内旧写法仍能工作
function handleD2SaveItems(e: Event): void {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    void d2SaveItems(items)
  }
}

function handleD2Writeback(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; auditedAmount: number }>).detail
  if (d?.accountCode != null && d.auditedAmount != null) {
    d2Writeback(d.accountCode, d.auditedAmount)
  }
}

// ─── P0-3 + P1-4/5: selfLoad 严格类型 + merge 策略 ─────────────────────────
async function selfLoad(): Promise<void> {
  const snapshot = props.htmlData?.responses_snapshot
  // P1-4: 仅当 snapshot 非空对象时才使用（避免部分 htmlData 丢失完整数据）
  if (snapshot && typeof snapshot === 'object' && Object.keys(snapshot).length > 0) {
    const items = Object.entries(snapshot).map(([itemId, raw]) => {
      const entry = raw as Record<string, unknown>
      return {
        item_id: String(entry?.item_id ?? itemId),
        conclusion: (entry?.conclusion as string | null) ?? null,
        remark: (entry?.remark as string | null) ?? null,
        wp_ref: (entry?.wp_ref as string | null) ?? null,
        version: (entry?.version as string | undefined),
        updated_at: (entry?.updated_at as string | undefined),
      }
    })
    formData.hydrate(items)
    isLoading.value = false
    return
  }
  // P1-5: 否则从 API 加载完整数据
  try {
    await formData.loadAll()
  } catch (err) {
    console.warn('[GtD2AccountsReceivable] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  window.addEventListener('d2:save-items', handleD2SaveItems)
  window.addEventListener('d2:writeback-trial-balance', handleD2Writeback)
  void selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('d2:save-items', handleD2SaveItems)
  window.removeEventListener('d2:writeback-trial-balance', handleD2Writeback)
  void formData.flushPendingSave().catch(() => undefined)
})
</script>

<style scoped>
.d2-accounts-receivable {
  padding: 12px;
}

.d2-accounts-receivable :deep(.amount-negative) {
  color: #f56c6c;
}

.loading-container {
  padding: 24px;
}

.d2-mode-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
</style>
