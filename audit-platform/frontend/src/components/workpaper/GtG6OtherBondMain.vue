<template>
  <div class="g6-other-bond-investment-main">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <div v-else-if="loadError" class="error-container">
      <el-card shadow="never">
        <el-result icon="error" title="数据加载失败" :sub-title="loadError">
          <template #extra>
            <el-button type="primary" @click="retrySelfLoad">重试</el-button>
          </template>
        </el-result>
      </el-card>
    </div>
    <template v-else>
      <div class="g6-other-bond-investment-main-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <!-- 双模式：HTML sheet 切到 OnlyOffice -->
      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- G6A 实质性程序表 -->
      <G6TabProcedure
        v-else-if="currentSheet === 'procedure'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G6-1 审定表 -->
      <G6TabAdjudication
        v-else-if="currentSheet === 'adjudication'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="formData.allResponses.value"
      />

      <!-- G6-2 明细表 -->
      <G6TabDetail
        v-else-if="currentSheet === 'detail'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="formData.allResponses.value"
        @imported="onSheetImported"
      />

      <!-- G6-3 坏账准备明细表 -->
      <G6TabBadDebtDetail
        v-else-if="currentSheet === 'badDebtDetail'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="formData.allResponses.value"
        @imported="onSheetImported"
      />

      <!-- G6-4 调整分录汇总 -->
      <G6TabAdjustment
        v-else-if="currentSheet === 'adjustment'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="formData.allResponses.value"
        @imported="onSheetImported"
      />

      <!-- 附注披露信息（上市公司） -->
      <G6TabDisclosureListed
        v-else-if="currentSheet === 'disclosureListed'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="formData.allResponses.value"
      />

      <!-- 附注披露信息（国企） -->
      <G6TabDisclosureSOE
        v-else-if="currentSheet === 'disclosureSOE'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="formData.allResponses.value"
      />

      <!-- 底稿目录 -->
      <template v-else-if="currentSheet === 'directory'">
        <div class="g6-index-toolbar">
          <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        </div>
        <G6TabDirectory
          :all-responses="formData.allResponses.value"
          :available-sheets="availableSheets"
        />
        <GCycleBIndexExtras
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName"
          :wp-code="'G6'"
          :html-data="directoryHtmlData"
          :available-sheets="availableSheets"
          :all-responses="formData.allResponses.value"
        />
      </template>

      <!-- 兜底：未迁移/未匹配 sheet → OnlyOffice fallback -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG6OtherBondMain.vue — G6 其他债权投资底稿(main组)主入口
 *
 * 对齐 G4/G5：formData + g6:save-items + 附注路由 + 双模式 reload
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { useG6MainDualMode } from './composables/useG6MainDualMode'
import { useG6MainFormData } from './composables/useG6MainFormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import type { ChecklistResponse } from './composables/useF1FormData'
import { matchG6SaveItemsEvent } from './composables/g6CrossHelpers'

// ─── defineAsyncComponent 懒加载所有子组件 ───────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G6TabProcedure = defineAsyncComponent(
  () => import('./g6-other-bond-investment-main/core/G6TabProcedure.vue'),
)
const G6TabAdjudication = defineAsyncComponent(
  () => import('./g6-other-bond-investment-main/core/G6TabAdjudication.vue'),
)
const G6TabDetail = defineAsyncComponent(
  () => import('./g6-other-bond-investment-main/core/G6TabDetail.vue'),
)
const G6TabBadDebtDetail = defineAsyncComponent(
  () => import('./g6-other-bond-investment-main/core/G6TabBadDebtDetail.vue'),
)
const G6TabAdjustment = defineAsyncComponent(
  () => import('./g6-other-bond-investment-main/core/G6TabAdjustment.vue'),
)
const G6TabDisclosureListed = defineAsyncComponent(
  () => import('./g6-other-bond-investment-main/core/G6TabDisclosureListed.vue'),
)
const G6TabDisclosureSOE = defineAsyncComponent(
  () => import('./g6-other-bond-investment-main/core/G6TabDisclosureSOE.vue'),
)
const G6TabDirectory = defineAsyncComponent(
  () => import('./g6-other-bond-investment-main/core/G6TabDirectory.vue'),
)
const GCycleBIndexExtras = defineAsyncComponent(() => import('./shared/GCycleBIndexExtras.vue'))

// ─── Props ──────────────────────────────────────────────────────────────────
const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

// ─── sheetName 正则 → 编码映射 ──────────────────────────────────────────────
const SHEET_CODE_MAP: Record<string, string> = {
  'G6A': 'procedure',
  'G6-1': 'adjudication',
  'G6-2': 'detail',
  'G6-3': 'badDebtDetail',
  'G6-4': 'adjustment',
  '附注披露信息（上市公司）': 'disclosureListed',
  '附注披露信息（国企）': 'disclosureSOE',
  '底稿目录': 'directory',
}

const isLoading = ref(true)
const loadError = ref<string | null>(null)
const selfLoadData = ref<Record<string, any> | null>(null)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const isReadonly = computed(() => !!props.readonly)

/** 提取当前sheetName对应的组件标识 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''
  if (SHEET_CODE_MAP[name]) return SHEET_CODE_MAP[name]
  if (/G6-note-listed|附注披露.*上市|附注.*上市/.test(name)) return 'disclosureListed'
  if (/G6-note-soe|附注披露.*国企|附注.*国企/.test(name)) return 'disclosureSOE'
  if (/G6-directory|底稿目录/.test(name)) return 'directory'
  if (/附注/.test(name)) return name.includes('国企') ? 'disclosureSOE' : 'disclosureListed'
  const codeMatch = name.match(/(G6A|G6-[1-4])/i)
  if (codeMatch) {
    const code = codeMatch[1].toUpperCase().replace(/^G6A$/i, 'G6A')
    return SHEET_CODE_MAP[code] || ''
  }
  return ''
})

/** 已迁移为HTML专属组件的sheet列表（支持双模式切换） */
const HTML_SHEETS = new Set([
  'procedure',
  'adjudication',
  'detail',
  'badDebtDetail',
  'adjustment',
  'disclosureListed',
  'disclosureSOE',
  'directory',
])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))

/** 解析后的 htmlData（优先使用prop，fallback到selfLoad结果） */
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

// ─── useG6MainFormData ──────────────────────────────────────────────────────
const formData = useG6MainFormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
  onAfterSave: () => scheduleAutoSnapshot(),
})

// ─── 双模式切换 ─────────────────────────────────────────────────────────────
const dualMode = useG6MainDualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

const availableSheets = computed(() => {
  const hd = resolvedHtmlData.value
  const fromHtml = hd?.sheets ?? hd?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) {
    // 统一为下划线格式（buildCycleArchitectureHtmlData 期望 sheet_name/component_type）
    return fromHtml.map((s: any) => ({
      sheet_name: s.sheet_name || s.sheetName || s.name || '',
      component_type: s.component_type || s.componentType || 'audit-sheet',
    }))
  }
  // 对齐 G1：htmlData 无 sheets 时用自加载 render-config 的 sheetCache 兜底
  return Object.keys(formData.sheetCache.value).map(sheet_name => ({ sheet_name }))
})

/** 目录页传给 GCycleBIndexExtras 的 htmlData：去除 navigation_rows 强制从 availableSheets 重建 */
const directoryHtmlData = computed(() => {
  const hd = resolvedHtmlData.value || props.htmlData
  if (!hd) return undefined
  const { navigation_rows: _, ...rest } = hd as any
  return rest as Record<string, unknown>
})

provide('g6VersionTrailRef', versionTrailRef)
provide('g6OpenVersionHistory', openVersionHistory)
provide('reloadWorkpaperData', () => formData.loadAll())

/** 目录页跳转：G6TabDirectory inject('jumpToSection') → navigate-sheet → GtWpRenderer */
const emit = defineEmits<{ 'navigate-sheet': [sheetName: string] }>()
provide('jumpToSection', (sheetName: string) => emit('navigate-sheet', sheetName))

function onSheetImported(): void {
  void formData.loadAll()
}

async function handleG6SaveItems(e: Event): Promise<void> {
  const items = matchG6SaveItemsEvent(e, props.wpId)
  if (!items?.length) return
  await formData.saveItemsFromEvent(items as ChecklistResponse[])
  scheduleAutoSnapshot()
}

function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
  if (d?.accountCode === '1503') {
    void formData.saveImmediate('G6-1-adjudicated-amount', {
      item_id: 'G6-1-adjudicated-amount',
      conclusion: String(d.adjudicatedAmount),
      remark: null,
    })
  }
}

/** G6-3 → G6-1 减值准备单项/组合期末未审回写 */
function handleBadDebtWriteback(e: Event): void {
  const d = (e as CustomEvent<{
    individualClosing: number
    portfolioClosing: number
  }>).detail
  if (!d) return
  const map = formData.allResponses.value
  const prevRaw = map.get('G6-1-rows')?.conclusion || map.get('G6-1-rows')?.remark || '{}'
  let store: Record<string, any> = {}
  try {
    store = JSON.parse(String(prevRaw))
    if (!store || typeof store !== 'object' || Array.isArray(store)) store = {}
  } catch {
    store = {}
  }
  const note = '来自 G6-3 坏账准备明细回写'
  const patch = (key: string, amount: number) => {
    const prev = store[key] ?? {}
    const prevReason = String(prev.reasonAnalysis || '')
    store[key] = {
      ...prev,
      closingUnadjusted: amount,
      reasonAnalysis: prevReason.includes('G6-3')
        ? prevReason
        : [prevReason, note].filter(Boolean).join('；'),
    }
  }
  patch('impairment-individual', Number(d.individualClosing) || 0)
  patch('impairment-portfolio', Number(d.portfolioClosing) || 0)
  const json = JSON.stringify(store)
  void formData.saveImmediate('G6-1-rows', {
    item_id: 'G6-1-rows',
    conclusion: json,
    remark: json,
  })
}

// ─── selfLoad：始终 loadAll；htmlData 为空时再 hydrate selfLoadData ─────────
async function selfLoad(): Promise<void> {
  try {
    await formData.loadAll()
    if (props.htmlData != null) return
    const parsed = formData.parseContent()
    if (parsed && Object.keys(parsed).length > 0) {
      selfLoadData.value = parsed as Record<string, any>
    }
  } catch (err: any) {
    loadError.value = err?.message || '加载渲染配置失败'
  }
}

async function retrySelfLoad(): Promise<void> {
  loadError.value = null
  isLoading.value = true
  await selfLoad()
  isLoading.value = false
}

// ─── 生命周期 ───────────────────────────────────────────────────────────────
onMounted(async () => {
  window.addEventListener('g6:save-items', handleG6SaveItems)
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  window.addEventListener('g6:bad-debt-writeback', handleBadDebtWriteback)
  await selfLoad()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g6:save-items', handleG6SaveItems)
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
  window.removeEventListener('g6:bad-debt-writeback', handleBadDebtWriteback)
})
</script>

<style scoped>
.g6-other-bond-investment-main { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g6-other-bond-investment-main-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
.g6-index-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
</style>
