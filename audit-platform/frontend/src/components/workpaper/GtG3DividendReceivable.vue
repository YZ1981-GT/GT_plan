<template>
  <div class="g3-dividend-receivable">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div class="g3-dividend-receivable-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-button size="small" type="primary" plain @click="openHandbook('preparation')">
          📖 编制手册
        </el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice' && dualMode.isOoAvailable.value"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
        @fallback="dualMode.onOoFallback"
      />

      <CycleTabProcedure
        v-else-if="currentSheet === 'G3A'"
        sheet-code="G3A"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      >
        <template #toolbar>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="g3a-handbook-tip"
            title="本表为程序控制台：勾选拟执行程序并填索引。不熟悉编制逻辑？请打开手册。"
          />
          <el-button type="primary" size="small" @click="openHandbook('preparation')">
            📖 编制手册
          </el-button>
          <el-button size="small" @click="openHandbook('usage')">
            使用手册
          </el-button>
        </template>
      </CycleTabProcedure>

      <G3TabAdjudication
        v-else-if="currentSheet === 'G3-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :audit-year="auditYear"
        @imported="onSheetImported"
      />

      <G3TabDetail
        v-else-if="currentSheet === 'G3-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        @imported="onSheetImported"
      />

      <G3TabAdjustment
        v-else-if="currentSheet === 'G3-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :audit-year="auditYear"
        @imported="onSheetImported"
      />

      <G3TabCalcCheck
        v-else-if="currentSheet === 'G3-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :audit-year="auditYear"
        :cutoff-date="cutoffDate"
        @imported="onSheetImported"
      />

      <G3TabOverdueCheck
        v-else-if="currentSheet === 'G3-5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        @imported="onSheetImported"
      />

      <G3TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :applicable-standards="applicableStandards"
      />

      <G3TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :all-responses="formData.allResponses.value"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :applicable-standards="applicableStandards"
      />

      <!-- 底稿目录：对齐 G1 目录页，显示泳道卡片 -->
      <template v-else-if="currentSheet === '底稿目录'">
        <GCycleBIndexExtras
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName"
          :wp-code="props.wpCode"
          :html-data="directoryHtmlData"
          :available-sheets="availableSheets"
          :all-responses="formData.allResponses.value"
        />
      </template>

      <!-- 完整Excel：OO不可用时的友好提示 -->
      <div v-else-if="currentSheet === '完整Excel'" class="g3-excel-fallback">
        <el-empty description="完整Excel视图需要OnlyOffice服务可用">
          <template #image><span style="font-size:48px">📄</span></template>
          <el-button type="primary" size="small" @click="openHandbook('preparation')">查看编制手册</el-button>
        </el-empty>
      </div>

      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <G3PreparationHandbookDialog
        v-model="handbookVisible"
        :initial-tab="handbookTab"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG3DividendReceivable.vue — G3 应收股利底稿主入口
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Task 1.1, 9.1~9.3
 * sheetName 分发到 G3 专属子组件（G3A + G3-1~G3-5 + 附注），未迁移走 OnlyOffice
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { useG3FormData } from './composables/useG3FormData'
import { useG3DualMode } from './composables/useG3DualMode'
import { buildDirectoryHtmlData } from './composables/gCycleIndexRouting'
import { eventBus } from '@/utils/eventBus'
import { G3SaveItemsKey, G3WritebackTbKey, G3DetailRevisionKey } from './composables/g3InternalKeys'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import type { ChecklistResponse } from './composables/useF1FormData'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G3TabAdjudication = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabAdjudication.vue'))
const G3TabDetail = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabDetail.vue'))
const G3TabCalcCheck = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabCalcCheck.vue'))
const G3TabAdjustment = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabAdjustment.vue'))
const G3TabOverdueCheck = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabOverdueCheck.vue'))
const G3TabDisclosureListed = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabDisclosureListed.vue'))
const G3TabDisclosureSOE = defineAsyncComponent(() => import('./g3-dividend-receivable/G3TabDisclosureSOE.vue'))
const GCycleBIndexExtras = defineAsyncComponent(
  () => import('./shared/GCycleBIndexExtras.vue'),
)
const G3PreparationHandbookDialog = defineAsyncComponent(
  () => import('./g3-dividend-receivable/G3PreparationHandbookDialog.vue'),
)

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
  /** 项目适用准则（上市/国企等），用于附注章节映射 */
  applicableStandards?: string[]
}>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const formData = useG3FormData({ wpId: wpIdRef, projectId: projectIdRef })
const isReadonly = computed(() => !!props.readonly)
const applicableStandards = computed<string[]>(() => {
  const fromProp = props.applicableStandards
  if (Array.isArray(fromProp) && fromProp.length) return fromProp.map(String).filter(Boolean)
  const raw =
    props.htmlData?.project_context?.applicable_standards
    ?? props.htmlData?.projectContext?.applicable_standards
    ?? props.htmlData?.applicable_standards
    ?? props.htmlData?.applicableStandards
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
const runtime = inject(WorkpaperRuntimeContextKey, null)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
// 再提供一层：保证 G3 子树能拿到 Runtime Boundary 的复核入口（缺省 null，Tab 侧 v-if）
provide('openReviewDialog', openReviewDialog)

const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

const availableSheets = computed(() => {
  const fromHtml = props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  // 对齐 G1：htmlData 无 sheets 时用自加载 render-config 的 sheetCache 兜底，
  // 保证底稿目录架构树非空
  return Object.keys(formData.sheetCache.value).map(sheet_name => ({ sheet_name }))
})

/** 目录页传给 GCycleBIndexExtras 的 htmlData：从 sheetCache 补全 cycle_workpapers（本循环底稿目录 grid） */
const directoryHtmlData = computed(() =>
  buildDirectoryHtmlData(props.htmlData, formData.sheetCache.value),
)

/** 与 G2 对齐：兼容 note-listed / 附注披露信息（上市公司）等模板名 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/底稿目录/.test(name)) return '底稿目录'
  if (/完整Excel|完整\s*Excel/i.test(name)) return '完整Excel'
  if (/G3-note-listed|附注披露.*上市|附注.*上市/.test(name)) return '附注上市'
  if (/G3-note-soe|附注披露.*国企|附注.*国企/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(G3A|G3-\d+)/)
  return m ? m[1] : ''
})

const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return s === 'G3A' || /^G3-[1-5]$/.test(s) || s.startsWith('附注') || s === '底稿目录' || s === '完整Excel'
})

const dualMode = useG3DualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

function onSheetImported(): void {
  void formData.loadAll()
}

/** 审计年度：供 G3-1 取试算 / G3-3 从调整分录模块取数；优先 htmlData，回退 Runtime */
const auditYear = computed(() =>
  props.htmlData?.project_context?.audit_year
  ?? props.htmlData?.projectContext?.audit_year
  ?? props.htmlData?.audit_year
  ?? runtime?.year?.value
  ?? null,
)

/** 资产负债表日：优先项目上下文 period_end，否则审计年度末 */
const cutoffDate = computed(() => {
  const fromCtx =
    props.htmlData?.project_context?.period_end
    ?? props.htmlData?.project_context?.audit_period_end
    ?? props.htmlData?.projectContext?.period_end
    ?? props.htmlData?.projectContext?.audit_period_end
  if (fromCtx) return String(fromCtx).slice(0, 10)
  const y = auditYear.value
  if (y != null && y !== '') {
    const n = Number(y)
    if (Number.isFinite(n) && n >= 1900) return `${Math.trunc(n)}-12-31`
  }
  return ''
})

provide('reloadWorkpaperData', () => formData.loadAll())
provide(G3DetailRevisionKey, formData.detailRevision)

provide(G3SaveItemsKey, async (items: ChecklistResponse[]) => {
  if (!Array.isArray(items) || !items.length) return
  for (const it of items) {
    if (it?.item_id) await formData.saveImmediate(it.item_id, it)
  }
  scheduleAutoSnapshot()
})

provide(G3WritebackTbKey, async (auditedAmount: number) => {
  if (typeof auditedAmount !== 'number' || !Number.isFinite(auditedAmount)) return
  await formData.writebackTrialBalance(auditedAmount)
})

/** 经 eventBus 订阅（crossWpEventBridge 已桥接 window ↔ mitt） */
function handleAdjudicated(d: {
  accountCode: string
  auditedAmount?: number
  adjudicatedAmount?: number
}): void {
  if (d?.accountCode !== '1131') return
  const amt = d.auditedAmount ?? (d as { adjudicatedAmount?: number }).adjudicatedAmount
  if (amt == null || !Number.isFinite(Number(amt))) return
  void formData.saveImmediate('G3-1-adjudicated-amount', {
    item_id: 'G3-1-adjudicated-amount',
    conclusion: String(amt),
    remark: null,
  })
}

onMounted(async () => {
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  formData.flushPending()
})
</script>

<style scoped>
.g3-dividend-receivable { padding: 12px; }
.loading-container { padding: 24px; }
.g3-dividend-receivable-toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.g3a-handbook-tip { flex: 1; min-width: 220px; margin-right: 4px; }

.g3-index-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }

.g3-excel-fallback { padding: 48px 24px; text-align: center; }
</style>
