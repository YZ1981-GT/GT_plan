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
        <el-button
          v-if="canStartAiReview && props.sheetName"
          size="small"
          type="success"
          plain
          @click="onCurrentSheetAiReview"
        >
          本页AI复核
        </el-button>
        <el-button
          v-if="canStartAiReview"
          size="small"
          type="primary"
          plain
          @click="reviewDialogVisible = true"
        >
          批量AI复核
        </el-button>
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

      <!-- OnlyOffice 在线编辑 -->
      <GtOnlyOfficeSheet
        v-if="renderMode === 'onlyoffice'"
        :key="ooSheetName"
        :wp-id="props.wpId"
        :sheet-name="ooSheetName"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @fallback="onOoFallback"
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

      <!-- 附注披露 -->
      <D2TabDisclosure
        v-else-if="currentSheet === '附注上市' || currentSheet === '附注国企'"
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

    <!-- AI 批量复核面板 -->
    <el-dialog v-model="reviewDialogVisible" title="D2 应收账款 AI 批量复核" width="900px" :destroy-on-close="false">
      <ReviewPanel
        ref="reviewPanelRef"
        :project-id="props.projectId"
        wp-code-prefix="D2"
        :year="props.year || new Date().getFullYear()"
        @navigate-sheet="onReviewNavigateSheet"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * GtD2AccountsReceivable.vue — D2 应收账款底稿主入口
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, toRef, defineAsyncComponent, nextTick } from 'vue'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import { useD2FormData, type ChecklistResponse } from './composables/useD2FormData'
import { useD2CrossSheet } from './composables/useD2CrossSheet'
import { useD2EntryDualMode, type D2RenderMode } from './composables/useD2EntryDualMode'
import { resolveCycleReviewSection } from './composables/cycleReviewSectionMap'
import GtWpReviewRail from './GtWpReviewRail.vue'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useD2ReviewThreads } from './composables/useD2ReviewThreads'
import { D2_SAVE_ITEMS_KEY, D2_WRITEBACK_KEY } from './composables/d2InjectionKeys'
import D2TabIndex from './d2/D2TabIndex.vue'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'

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
const ReviewPanel = defineAsyncComponent(() => import('./review/ReviewPanel.vue'))

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

const { currentRole } = usePermissionMatrix()
const reviewDialogVisible = ref(false)
const reviewPanelRef = ref<{ reviewCurrentSheet: (wpId: string, sheetName: string) => Promise<unknown> } | null>(null)
const canStartAiReview = computed(() => {
  const allowedRoles = ['manager', 'partner', 'qc', 'admin']
  return allowedRoles.includes(currentRole.value)
})

const formData = useD2FormData(toRef(props, 'wpId'), toRef(props, 'projectId'))
const allResponses = computed(() => formData.allResponses.value)
const saving = formData.saving

const crossSheet = useD2CrossSheet({ allResponses })

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

const currentSheet = computed(() => {
  const name = props.sheetName || 'D2'
  const codeMatch = name.match(/D2(?:-\d+)?[A-Z]?$|D2A$/)
  if (codeMatch) return codeMatch[0]
  if (name.includes('目录')) return '目录'
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企')) return '附注国企'
  if (name.includes('截止')) return '截止测试'
  if (name === 'D2' || name.startsWith('D2 ')) return 'D2'
  return name
})

const d2ReviewSection = computed(() => resolveCycleReviewSection('D2', currentSheet.value))

const dualMode = useD2EntryDualMode({
  wpId: toRef(props, 'wpId'),
  currentSheet,
  reloadAllResponses: () => formData.loadAll(),
})

const ooSheetName = computed(() =>
  dualMode.resolveOoSheetName() || props.sheetName || 'D2-1',
)

const renderMode = computed({
  get: () => dualMode.mode.value,
  set: (v: D2RenderMode) => { void dualMode.switchMode(v) },
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

async function onCurrentSheetAiReview(): Promise<void> {
  if (!props.sheetName) return
  reviewDialogVisible.value = true
  await nextTick()
  await reviewPanelRef.value?.reviewCurrentSheet(props.wpId, props.sheetName)
}

function onReviewNavigateSheet(sheetName: string): void {
  reviewDialogVisible.value = false
  emit('jump-to-section', sheetName)
}

const KNOWN_HTML_SHEETS = new Set([
  'D2', '目录', 'D2A',
  'D2-1', 'D2-2', 'D2-3', 'D2-4', 'D2-5', 'D2-6', 'D2-7', 'D2-8',
  'D2-9', 'D2-10', 'D2-11', 'D2-12', 'D2-13',
  '附注上市', '附注国企', '截止测试',
])

const showModeToolbar = computed(() =>
  currentSheet.value !== 'skip' && KNOWN_HTML_SHEETS.has(currentSheet.value),
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
