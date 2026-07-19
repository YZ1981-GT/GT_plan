<template>
  <div class="g2-interest-receivable">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="currentSheet !== '底稿目录'" class="g2-interest-receivable-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          v-model="renderMode"
          :options="renderModeOptions"
          size="small"
        />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-button size="small" type="primary" plain @click="openHandbook('preparation')">
          📖 编制手册
        </el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <!-- 双模式：HTML sheet 切到 OnlyOffice（目录页不走 OO） -->
      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && currentSheet !== '底稿目录' && renderMode === 'onlyoffice'"
        :key="ooSheetName"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="ooSheetName"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
        @fallback="onOoFallback"
      />

      <!-- G2A 程序表（对齐 D4A） -->
      <CycleTabProcedure
        v-else-if="currentSheet === 'G2A'"
        sheet-code="G2A"
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
            class="g2a-handbook-tip"
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

      <!-- G2-1 审定表 -->
      <G2TabAdjudication
        v-else-if="currentSheet === 'G2-1'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- G2-2 明细表 -->
      <G2TabDetail
        v-else-if="currentSheet === 'G2-2'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- G2-3 坏账准备明细 -->
      <G2TabBadDebtDetail
        v-else-if="currentSheet === 'G2-3'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- G2-4 调整分录汇总（对齐 D4-4 + 调整分录模块联动） -->
      <G2TabAdjustment
        v-else-if="currentSheet === 'G2-4'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :audit-year="auditYear"
        @imported="onSheetImported"
      />

      <!-- G2-5 利息测算表 -->
      <G2TabInterestCalc
        v-else-if="currentSheet === 'G2-5'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- G2-6 长期未收回检查 -->
      <G2TabOverdueCheck
        v-else-if="currentSheet === 'G2-6'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- G2-7 坏账准备测算（单项/账龄组合/其他组合） -->
      <G2TabECLCalc
        v-else-if="currentSheet === 'G2-7'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- G2-8 凭证检查表（借方/贷方区块） -->
      <G2TabVoucherCheck
        v-else-if="currentSheet === 'G2-8'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        @imported="onSheetImported"
      />

      <!-- 附注披露(上市) -->
      <G2TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
      />

      <!-- 附注披露(国企) -->
      <G2TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :applicable-standards="applicableStandards"
      />

      <!-- 底稿目录（对齐 G1：泳道卡片） -->
      <template v-else-if="currentSheet === '底稿目录'">
        <div class="g2-index-toolbar">
          <el-button size="small" type="primary" plain @click="openHandbook('preparation')">
            📖 编制手册
          </el-button>
          <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        </div>
        <GCycleBIndexExtras
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName"
          :wp-code="props.wpCode"
          :html-data="props.htmlData"
          :available-sheets="availableSheets"
        />
      </template>

      <!-- 兜底：未迁移 sheet → OnlyOffice -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
      <G2PreparationHandbookDialog
        v-model="handbookVisible"
        :initial-tab="handbookTab"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG2InterestReceivable.vue — G2 应收利息底稿主入口
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 1.1, 9.1~9.3
 * sheetName 分发到 G2 专属子组件（G2-1~G2-8 + 附注），G2A/未迁移走 OnlyOffice
 * 集成：useWorkpaperVersionToolbar(autoSnapshot) + provide('openReviewDialog')
 * EventBus：监听 g2:save-items 持久化 + substantive:adjudicated(1132)
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { useG2IntRecFormData } from './composables/useG2IntRecFormData'
import { useG2DualMode, type G2RenderMode } from './composables/useG2DualMode'
import { extractG2SheetCode, buildG2FallbackSheets } from './composables/g2SheetLabels'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useWorkpaperEntryInjections } from './composables/useWorkpaperEntryInjections'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import type { ChecklistResponse } from './composables/useF1FormData'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GCycleBIndexExtras = defineAsyncComponent(() => import('./shared/GCycleBIndexExtras.vue'))
const G2TabAdjudication = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabAdjudication.vue'))
const G2TabDetail = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabDetail.vue'))
const G2TabBadDebtDetail = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabBadDebtDetail.vue'))
const G2TabAdjustment = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabAdjustment.vue'))
const G2TabInterestCalc = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabInterestCalc.vue'))
const G2TabOverdueCheck = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabOverdueCheck.vue'))
const G2TabECLCalc = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabECLCalc.vue'))
const G2TabVoucherCheck = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabVoucherCheck.vue'))
const G2TabDisclosureListed = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabDisclosureListed.vue'))
const G2TabDisclosureSOE = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabDisclosureSOE.vue'))
const G2PreparationHandbookDialog = defineAsyncComponent(
  () => import('./g2-interest-receivable/G2PreparationHandbookDialog.vue'),
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

const emit = defineEmits<{
  (e: 'jump-to-section', sheetName: string): void
}>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const formData = useG2IntRecFormData({ wpId: wpIdRef, projectId: projectIdRef })
const allResponsesRef = computed(() => formData.allResponses.value)
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
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

provide('g2VersionTrailRef', versionTrailRef)
provide('g2OpenVersionHistory', openVersionHistory)

/** 与 G1 对齐：sheetName → 内部分发编码（含底稿目录 / 附注） */
const currentSheet = computed(() => extractG2SheetCode(props.sheetName || props.wpCode || ''))

const MIGRATED_SHEETS = new Set([
  'G2A', 'G2-1', 'G2-2', 'G2-3', 'G2-4', 'G2-5', 'G2-6', 'G2-7', 'G2-8',
  '附注上市', '附注国企', '底稿目录',
])
const isHtmlSheet = computed(() => MIGRATED_SHEETS.has(currentSheet.value))

const availableSheets = computed(() => {
  const fromHtml = props.htmlData?.sheets ?? props.htmlData?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  // 对齐 G1：优先用自加载 render-config 的 sheetCache（真实 sheet 名）
  const cached = Object.keys(formData.sheetCache.value)
  if (cached.length) return cached.map(sheet_name => ({ sheet_name }))
  // 对齐 D4：仍无数据时用静态映射兜底，保证目录与 OO 解析有可用 sheet 名
  return buildG2FallbackSheets()
})

const dualMode = useG2DualMode({
  wpId: wpIdRef,
  currentSheet,
  availableSheets,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

const ooSheetName = computed(
  () => dualMode.resolveOoSheetName() || props.sheetName || '应收利息实质性程序表G2A',
)

const renderMode = computed({
  get: () => dualMode.currentMode.value,
  set: (v: G2RenderMode) => {
    void dualMode.switchMode(v)
  },
})

const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  {
    label: '在线编辑',
    value: 'onlyoffice' as const,
    disabled: !dualMode.isOoAvailable.value,
  },
])

function onOoFallback(): void {
  dualMode.onOoFallback()
}

useWorkpaperEntryInjections({
  onJumpToSection: (sheetLabel) => emit('jump-to-section', sheetLabel),
  reloadFn: () => formData.loadAll(),
  wpId: wpIdRef,
})

/** 审计年度：供 G2-4 从调整分录模块取数 */
const auditYear = computed(() =>
  props.htmlData?.project_context?.audit_year
  ?? props.htmlData?.projectContext?.audit_year
  ?? props.htmlData?.audit_year
  ?? null,
)

function onSheetImported(): void {
  void formData.loadAll()
}

const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

// 复核对话 openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide，子组件 inject 命中祖先
provide('reloadWorkpaperData', () => formData.loadAll())

// ─── 监听 g2:save-items → 保存 + autoSnapshot ───────────────────────────────
async function handleG2SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    for (const it of items) {
      if (it?.item_id) await formData.saveImmediate(it.item_id, it)
    }
    scheduleAutoSnapshot()
  }
}

// ─── 监听 substantive:adjudicated(1132) → 附注刷新 ──────────────────────────
function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
  if (d?.accountCode === '1132') {
    void formData.saveImmediate('G2-1-adjudicated-amount', {
      item_id: 'G2-1-adjudicated-amount',
      conclusion: String(d.adjudicatedAmount),
      remark: null,
    })
  }
}

/** 审定净值回写试算 1132（对齐 G11） */
function handleG2Writeback(e: Event): void {
  const d = (e as CustomEvent<{ accountCode?: string; auditedAmount?: number }>).detail
  if (!d || d.accountCode !== '1132') return
  if (typeof d.auditedAmount !== 'number' || !Number.isFinite(d.auditedAmount)) return
  void formData.writebackTrialBalance(d.auditedAmount)
}

onMounted(async () => {
  window.addEventListener('g2:save-items', handleG2SaveItems)
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  window.addEventListener('g2:writeback-trial-balance', handleG2Writeback)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g2:save-items', handleG2SaveItems)
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
  window.removeEventListener('g2:writeback-trial-balance', handleG2Writeback)
  formData.flushPending()
})
</script>

<style scoped>
.g2-interest-receivable { padding: 12px; }
.loading-container { padding: 24px; }
.g2-interest-receivable-toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.g2a-handbook-tip { flex: 1; min-width: 220px; margin-right: 4px; }
.g2-index-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
</style>
