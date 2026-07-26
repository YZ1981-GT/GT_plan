<template>
  <div class="g4-bond-investment-ecl">
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
      <div class="g4-bond-investment-ecl-toolbar">
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

      <!-- G4-9 三阶段划分 -->
      <G4TabStageClassification
        v-else-if="currentSheet === 'stageClassification'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onSheetImported"
        @navigate-sheet="onNavigateSheet"
      />

      <!-- G4-10 减值准备测算表 -->
      <G4TabImpairmentCalc
        v-else-if="currentSheet === 'impairmentCalc'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onSheetImported"
      />

      <!-- G4-11 预期信用损失计量测试 -->
      <G4TabEclMeasurement
        v-else-if="currentSheet === 'eclMeasurement'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onSheetImported"
      />

      <!-- G4-12 减值准备转回核销检查 -->
      <G4TabReversalWriteOff
        v-else-if="currentSheet === 'reversalWriteOff'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onSheetImported"
      />

      <!-- G4-13 凭证检查表 -->
      <G4TabVoucherCheck
        v-else-if="currentSheet === 'voucherCheck'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onSheetImported"
      />

      <!-- 参考-中证协金融工具减值指引 -->
      <G4TabRefImpairmentGuidance
        v-else-if="currentSheet === 'refImpairmentGuidance'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="true"
      />

      <!-- 参考-根据剩余期限折算PD -->
      <G4TabRefPdConversion
        v-else-if="currentSheet === 'refPdConversion'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="true"
      />

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
 * GtG4BondInvestmentEcl.vue — G4 债权投资底稿(ECL组)主入口
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/ Task 4.1 + 4.2
 * sheetName正则提取编码(G4-9~G4-13, 参考-xxx) → v-if分发到7个子组件（defineAsyncComponent lazy）
 * 未匹配 → OnlyOffice fallback
 * 集成：useWorkpaperVersionToolbar(autoSnapshot) + provide('openReviewDialog') + 双模式切换
 * selfLoad：始终 formData.loadAll；htmlData为null时额外解析 sheetCache
 *
 * Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9, 9.1, 9.4, 11.7
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { useG4EclDualMode } from './composables/useG4EclDualMode'
import { useG4EclFormData } from './composables/useG4EclFormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import type { ChecklistResponse } from './composables/useF1FormData'
import type { AdjustmentEntry } from './composables/useG4MainAdjustment'
import { persistExceptionDraftsToMainWp } from './composables/g4ExceptionRouting'
import { ElMessage } from 'element-plus'

// ─── defineAsyncComponent 懒加载所有子组件 ───────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G4TabStageClassification = defineAsyncComponent(
  () => import('./g4-bond-investment-ecl/impairment/G4TabStageClassification.vue'),
)
const G4TabImpairmentCalc = defineAsyncComponent(
  () => import('./g4-bond-investment-ecl/impairment/G4TabImpairmentCalc.vue'),
)
const G4TabEclMeasurement = defineAsyncComponent(
  () => import('./g4-bond-investment-ecl/impairment/G4TabEclMeasurement.vue'),
)
const G4TabReversalWriteOff = defineAsyncComponent(
  () => import('./g4-bond-investment-ecl/impairment/G4TabReversalWriteOff.vue'),
)
const G4TabVoucherCheck = defineAsyncComponent(
  () => import('./g4-bond-investment-ecl/voucher/G4TabVoucherCheck.vue'),
)
const G4TabRefImpairmentGuidance = defineAsyncComponent(
  () => import('./g4-bond-investment-ecl/reference/G4TabRefImpairmentGuidance.vue'),
)
const G4TabRefPdConversion = defineAsyncComponent(
  () => import('./g4-bond-investment-ecl/reference/G4TabRefPdConversion.vue'),
)

// ─── Props ──────────────────────────────────────────────────────────────────
const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── sheetName 正则 → 编码映射 ──────────────────────────────────────────────
const SHEET_CODE_MAP: Record<string, string> = {
  'G4-9': 'stageClassification',
  'G4-10': 'impairmentCalc',
  'G4-11': 'eclMeasurement',
  'G4-12': 'reversalWriteOff',
  'G4-13': 'voucherCheck',
  '参考-中证协': 'refImpairmentGuidance',
  '参考-根据剩余期限折算PD': 'refPdConversion',
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

  // 优先匹配中文参考材料sheet
  if (name.includes('参考-根据剩余期限折算PD') || name.includes('参考-剩余期限折算PD')) {
    return 'refPdConversion'
  }
  if (name.includes('参考-中证协') || name.includes('参考-减值指引')) {
    return 'refImpairmentGuidance'
  }

  // 正则匹配：G4-9/G4-10/G4-11/G4-12/G4-13
  const codeMatch = name.match(/G4-(9|1[0-3])/)
  if (codeMatch) {
    const code = `G4-${codeMatch[1]}`
    return SHEET_CODE_MAP[code] || ''
  }

  return ''
})

/** 已迁移为HTML专属组件的sheet列表（支持双模式切换） */
const HTML_SHEETS = new Set([
  'stageClassification',
  'impairmentCalc',
  'eclMeasurement',
  'reversalWriteOff',
  'voucherCheck',
  'refImpairmentGuidance',
  'refPdConversion',
])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))

/** 解析后的 htmlData（优先使用prop，fallback到selfLoad结果） */
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

// ─── useG4EclFormData 用于selfLoad ─────────────────────────────────────────
const formData = useG4EclFormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
  onAfterSave: () => scheduleAutoSnapshot(),
})

// ─── 双模式切换 ─────────────────────────────────────────────────────────────
const dualMode = useG4EclDualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

provide('g4VersionTrailRef', versionTrailRef)
provide('g4OpenVersionHistory', openVersionHistory)
provide('reloadWorkpaperData', () => formData.loadAll())
provide('navigateG4Sheet', (code: string) => emit('navigate-sheet', code))

// 复核对话 openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide，子组件 inject 命中祖先

function onNavigateSheet(sheetName: string): void {
  emit('navigate-sheet', sheetName)
}

function onSheetImported(): void {
  void formData.loadAll()
}

async function handleG4SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    for (const it of items) {
      if (it?.item_id) await formData.saveImmediate(it.item_id, it)
    }
    scheduleAutoSnapshot()
  }
}

function handleExceptionDrafts(e: Event): void {
  const drafts = (e as CustomEvent<{ drafts: AdjustmentEntry[] }>).detail?.drafts
  if (!Array.isArray(drafts) || drafts.length === 0) return
  void persistExceptionDraftsToMainWp(drafts, {
    projectId: props.projectId,
  }).then((result) => {
    if (!result) ElMessage.error('未找到 G4 主底稿，异常草稿未写入 G4-3')
  }).catch(() => {
    ElMessage.error('写入 G4-3 异常草稿失败')
  })
}

// ─── selfLoad：始终 loadAll；htmlData 缺失时再填充 selfLoadData ─────────────
async function selfLoad(): Promise<void> {
  try {
    await formData.loadAll()
    if (props.htmlData != null) return
    // 从formData的sheetCache中获取当前sheet的数据
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
  window.addEventListener('g4:save-items', handleG4SaveItems)
  window.addEventListener('g4:exception-drafts', handleExceptionDrafts)
  await selfLoad()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g4:save-items', handleG4SaveItems)
  window.removeEventListener('g4:exception-drafts', handleExceptionDrafts)
})
</script>

<style scoped>
.g4-bond-investment-ecl { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g4-bond-investment-ecl-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
