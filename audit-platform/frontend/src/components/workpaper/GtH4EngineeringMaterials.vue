<template>
  <div class="h4-engineering-materials">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 顶部工具栏（双模式切换）— 目录页隐藏 -->
      <div v-if="currentSheet !== 'H4'" class="h4-header-toolbar">
        <el-segmented
          :model-value="currentMode"
          :options="modeOptions"
          size="small"
          :disabled="!isOoAvailable && currentMode === 'html'"
          @change="onModeChange"
        />
      </div>

      <!-- OnlyOffice 模式 -->
      <GtOnlyOfficeSheet
        v-if="currentMode === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- HTML 结构化视图 -->
      <template v-else>
        <!-- 底稿目录 -->
        <H4TabIndex
          v-if="currentSheet === 'H4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H4A 程序表（selfLoad） -->
        <GtAProgramConsole
          v-else-if="currentSheet === 'H4A'"
          sheet-code="H4A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- H4-1 审定表 -->
        <H4TabAdjudication
          v-else-if="currentSheet === 'H4-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露信息（上市公司） -->
        <H4TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露信息（国有企业） -->
        <H4TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H4-2 明细表 -->
        <H4TabDetail
          v-else-if="currentSheet === 'H4-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H4-3 调整分录汇总 -->
        <H4TabAdjustment
          v-else-if="currentSheet === 'H4-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H4-4 增加检查表 -->
        <H4TabAdditionCheck
          v-else-if="currentSheet === 'H4-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :year="props.year"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H4-5 减少检查表 -->
        <H4TabDisposalCheck
          v-else-if="currentSheet === 'H4-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :year="props.year"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H4-6A 监盘计划 -->
        <H4TabStocktakePlan
          v-else-if="currentSheet === 'H4-6A'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H4-6 盘点检查表 -->
        <H4TabStocktakeCheck
          v-else-if="currentSheet === 'H4-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H4-6B 监盘小结 -->
        <H4TabStocktakeSummary
          v-else-if="currentSheet === 'H4-6B'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H4-7 减值测算表 -->
        <H4TabImpairment
          v-else-if="currentSheet === 'H4-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :sheet-name="props.sheetName || ''"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H4-8 可收回金额测试表（HTML测算为主，OO对照） -->
        <H4TabRecoverable
          v-else-if="currentSheet === 'H4-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :sheet-name="props.sheetName || ''"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H4-9 关联交易检查表 -->
        <H4TabRelatedParty
          v-else-if="currentSheet === 'H4-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
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

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtH4EngineeringMaterials.vue — H4 工程物资底稿主入口
 *
 * sheetName prop v-if 分发到全部12个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * useVersionTrail: autoSnapshot on save。
 * 双模式: HTML↔OnlyOffice切换+OO健康检查。
 *
 * Spec: .kiro/specs/h4-engineering-materials/ Task 1.1
 * Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, toRef, inject, defineAsyncComponent, nextTick } from 'vue'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useH4FormData } from './composables/useH4FormData'
import { useH4DualMode } from './composables/useH4DualMode'
import { useH4CrossSheet } from './composables/useH4CrossSheet'
import { buildH4DetailSeedRows } from './composables/h4DetailPrefill'
import { eventBus } from '@/utils/eventBus'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
// 版本 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载
const GtAProgramConsole = defineAsyncComponent(() => import('./GtCycleAProgramRouter.vue'))

// core
const H4TabIndex = defineAsyncComponent(() => import('./h4/core/H4TabIndex.vue'))
const H4TabAdjudication = defineAsyncComponent(() => import('./h4/core/H4TabAdjudication.vue'))
const H4TabDetail = defineAsyncComponent(() => import('./h4/core/H4TabDetail.vue'))
const H4TabAdjustment = defineAsyncComponent(() => import('./h4/core/H4TabAdjustment.vue'))
const H4TabDisclosureListed = defineAsyncComponent(() => import('./h4/core/H4TabDisclosureListed.vue'))
const H4TabDisclosureSoe = defineAsyncComponent(() => import('./h4/core/H4TabDisclosureSoe.vue'))

// inspection
const H4TabAdditionCheck = defineAsyncComponent(() => import('./h4/inspection/H4TabAdditionCheck.vue'))
const H4TabDisposalCheck = defineAsyncComponent(() => import('./h4/inspection/H4TabDisposalCheck.vue'))
const H4TabStocktakeCheck = defineAsyncComponent(() => import('./h4/inspection/H4TabStocktakeCheck.vue'))
const H4TabStocktakePlan = defineAsyncComponent(() => import('./h4/inspection/H4TabStocktakePlan.vue'))
const H4TabStocktakeSummary = defineAsyncComponent(() => import('./h4/inspection/H4TabStocktakeSummary.vue'))
const H4TabRelatedParty = defineAsyncComponent(() => import('./h4/inspection/H4TabRelatedParty.vue'))

// impairment
const H4TabImpairment = defineAsyncComponent(() => import('./h4/impairment/H4TabImpairment.vue'))
const H4TabRecoverable = defineAsyncComponent(() => import('./h4/impairment/H4TabRecoverable.vue'))

// ─── Props & Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{ (e: 'save'): void; (e: 'completed'): void; (e: 'navigate-sheet', sheetName: string): void }>()

// ─── FormData（加载/保存/TB/回写） ────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const formData = useH4FormData({
  wpId: toRef(props, 'wpId') as any,
  projectId: toRef(props, 'projectId') as any,
})
const {
  isLoading,
  allResponses,
  tbValues,
  saveResponse,
  flushPending,
  writebackTrialBalance,
  mergeHtmlData,
  selfLoad: formSelfLoad,
  loadAllResponses,
} = formData

// ─── 双模式 HTML ↔ OnlyOffice ────────────────────────────────────────────────
const {
  currentMode,
  isOoAvailable,
  modeOptions,
  onModeChange,
} = useH4DualMode({
  wpId: toRef(props, 'wpId') as any,
  sheetName: toRef(props, 'sheetName') as any,
  autoSave: async () => { await flushPending() },
  reloadAll: async () => { await bootstrapLoad() },
})

/** 从 sheetName 提取编码 (H4/H4A/H4-1~H4-9/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国企|附注.*国有/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') || name.includes('国有') ? '附注国企' : '附注上市'
  if (/H4A/.test(name)) return 'H4A'
  const m = name.match(/(H4-\d+[A-Z]?)/)
  if (m) return m[1]
  if (/底稿目录/.test(name) || (/\bH4\b/.test(name) && !/H4-/.test(name) && !/H4A/.test(name))) return 'H4'
  return ''
})

/** 合并 htmlData 或走 FormData selfLoad */
async function bootstrapLoad(): Promise<void> {
  try {
    if (props.htmlData) {
      mergeHtmlData(props.htmlData)
      // sheets 数组中的 tb_values 一并合并
      if (Array.isArray(props.htmlData.sheets)) {
        for (const sheet of props.htmlData.sheets) {
          if (sheet.html_data?.tb_values) mergeHtmlData(sheet.html_data)
          if (sheet.html_data?.responses_snapshot) mergeHtmlData(sheet.html_data)
        }
      }
      // 补充 checklist 全量（覆盖 snapshot 可能不全）
      try { await loadAllResponses() } catch { /* ignore */ }
      formData.isLoading.value = false
    } else {
      await formSelfLoad()
    }
  } catch (err) {
    console.warn('[GtH4EngineeringMaterials] bootstrapLoad failed:', err)
    formData.isLoading.value = false
  }
}

// ─── provide for child components ────────────────────────────────────────────
provide('allResponses', allResponses)
provide('h4TbValues', tbValues)
provide('h4WritebackTB', writebackTrialBalance)

const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('h4VersionTrailRef', versionTrailRef)
provide('h4OpenVersionHistory', openVersionHistory)

/** 子组件 save：走 FormData，落库后触发版本快照 */
function persistResponse(itemId: string, value: any): void {
  if (!itemId) return
  if (isReadonly.value) {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    allResponses.value.set(itemId, { ...existing, item_id: itemId, remark: strVal })
    return
  }
  void saveResponse(itemId, value).then(() => { scheduleAutoSnapshot() })
}
provide('saveResponse', persistResponse)

// ─── CrossSheet 勾稽引擎（供全局告警 + 子组件消费） ────────────────────────────
const crossSheet = useH4CrossSheet(allResponses)
provide('h4CrossSheet', crossSheet)

// ─── 全局勾稽告警（主入口顶部展示，排除正在查看的对应 tab） ──────────────────
const globalAlerts = computed(() => {
  const alerts: Array<{ type: string; msg: string }> = []
  const sheet = currentSheet.value
  // 审定↔明细勾稽（H4-2 tab 内已显示，主入口排除）
  if (sheet !== 'H4-2') {
    const avd = crossSheet.adjudicationVsDetail.value
    if (!avd.isMatch && (crossSheet.adjudicationTotals.value.adjudicatedTotal !== 0 || crossSheet.detailTotal.value !== 0)) {
      alerts.push({ type: 'warning', msg: `H4-1 审定合计与 H4-2 明细合计差异 ${avd.diff.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` })
    }
  }
  return alerts
})

onMounted(() => {
  void bootstrapLoad().then(() => {
    // #2: 种子接线 — 灰度开启时从 detail_prefill 自动种子 H4-2 明细
    nextTick(() => {
      const prefill = props.htmlData?.detail_prefill
      const existingRemark = allResponses.value.get('H4-2-rows')?.remark
      const seedRows = buildH4DetailSeedRows(prefill, existingRemark)
      if (seedRows) {
        // 内存态写入（未编辑不落库，composable 的 watch 会消费）
        allResponses.value.set('H4-2-rows', {
          item_id: 'H4-2-rows',
          remark: JSON.stringify(seedRows),
          conclusion: null,
        })
      }
    })
  })
  window.addEventListener('tb:updated', _handleTbUpdated)
  window.addEventListener('substantive:adjudicated', _handleTbUpdated)
})

onBeforeUnmount(() => {
  window.removeEventListener('tb:updated', _handleTbUpdated)
  window.removeEventListener('substantive:adjudicated', _handleTbUpdated)
  void flushPending()
})

function _handleTbUpdated(e: Event) {
  const detail = (e as CustomEvent).detail
  if (
    !detail
    || !detail.accountCode
    || detail.accountCode === '1605'
    || detail.accountCode === '1604'
    || detail.wpCode === 'H4'
    || detail.wpCode === 'H2'
  ) {
    void bootstrapLoad()
  }
}
</script>

<style scoped>
.h4-engineering-materials {
  width: 100%;
  min-height: 400px;
}

.loading-container {
  padding: 24px;
}

.h4-header-toolbar {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
}
</style>
