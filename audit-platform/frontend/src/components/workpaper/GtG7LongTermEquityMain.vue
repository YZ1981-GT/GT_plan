<template>
  <div class="g7-long-term-equity-main">
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
      <div class="g7-long-term-equity-main-toolbar">
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

      <!-- G7A 实质性程序表 -->
      <G7TabProcedure
        v-else-if="currentSheet === 'procedure'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G7-1 审定表 -->
      <G7TabAdjudication
        v-else-if="currentSheet === 'adjudication'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G7-2 明细表 -->
      <G7TabDetail
        v-else-if="currentSheet === 'detail'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G7-3 调整分录汇总 -->
      <G7TabAdjustment
        v-else-if="currentSheet === 'adjustment'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 附注披露信息（上市公司） -->
      <G7TabDisclosureListed
        v-else-if="currentSheet === 'disclosureListed'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 附注披露信息（国企） -->
      <G7TabDisclosureSOE
        v-else-if="currentSheet === 'disclosureSOE'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 底稿目录 -->
      <template v-else-if="currentSheet === 'directory'">
        <div class="g7-index-toolbar">
          <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        </div>
        <G7TabDirectory
          :all-responses="g7AllResponses"
          :available-sheets="availableSheets"
        />
        <GCycleBIndexExtras
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName"
          :wp-code="'G7'"
          :html-data="resolvedHtmlData ?? undefined"
          :available-sheets="availableSheets"
          :all-responses="g7AllResponses"
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

      <!-- 版本链/复核 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG7LongTermEquityMain.vue — G7 长期股权投资底稿(main组)主入口
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/ Task 2.1
 * sheetName正则提取编码(G7A/G7-1/G7-2/G7-3/附注披露(上市)/附注披露(国企)/底稿目录) → v-if分发到7个子组件（defineAsyncComponent lazy）
 * 未匹配 → OnlyOffice fallback
 * 集成：useWorkpaperVersionToolbar(autoSnapshot) + provide('openReviewDialog') + useG7DualMode双模式切换
 * selfLoad：htmlData为null时通过useG7FormData调用render-config获取数据
 *
 * Requirements: 1.1, 1.2, 1.4, 6.3, 6.7
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { useG7DualMode } from './composables/useG7DualMode'
import { useG7FormData } from './composables/useG7FormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'

const G7_ACCOUNT_CODE = '1511'
const G7_IMPAIRMENT_CODE = '1512'

// ─── defineAsyncComponent 懒加载所有子组件 ───────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G7TabProcedure = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/core/G7TabProcedure.vue'),
)
const G7TabAdjudication = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/core/G7TabAdjudication.vue'),
)
const G7TabDetail = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/core/G7TabDetail.vue'),
)
const G7TabAdjustment = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/core/G7TabAdjustment.vue'),
)
const G7TabDisclosureListed = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/disclosure/G7TabDisclosureListed.vue'),
)
const G7TabDisclosureSOE = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/disclosure/G7TabDisclosureSOE.vue'),
)
const G7TabDirectory = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/core/G7TabDirectory.vue'),
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
  'G7A': 'procedure',
  'G7-1': 'adjudication',
  'G7-2': 'detail',
  'G7-3': 'adjustment',
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

  // 优先匹配中文sheet名
  if (name.includes('附注披露信息（上市公司）') || name.includes('附注披露(上市)') || name.includes('附注-上市')) {
    return 'disclosureListed'
  }
  if (name.includes('附注披露信息（国企）') || name.includes('附注披露(国企)') || name.includes('附注-国企')) {
    return 'disclosureSOE'
  }
  if (name.includes('底稿目录')) {
    return 'directory'
  }

  // 正则匹配：G7A
  if (/G7A/i.test(name)) {
    return 'procedure'
  }

  // 正则匹配：G7-1/G7-2/G7-3
  const codeMatch = name.match(/G7-([1-3])/)
  if (codeMatch) {
    const code = `G7-${codeMatch[1]}`
    return SHEET_CODE_MAP[code] || ''
  }

  return ''
})

/** 已迁移为HTML专属组件的sheet列表（支持双模式切换） */
const HTML_SHEETS = new Set([
  'procedure',
  'adjudication',
  'detail',
  'adjustment',
  'disclosureListed',
  'disclosureSOE',
  'directory',
])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))

/** 解析后的 htmlData（优先使用prop，fallback到selfLoad结果） */
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

const availableSheets = computed(() => {
  const hd = resolvedHtmlData.value
  const fromHtml = hd?.sheets ?? hd?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  const metaSheets = formData.renderMeta.value?.sheets
  if (Array.isArray(metaSheets) && metaSheets.length) return metaSheets
  // 对齐 G1：htmlData 无 sheets 时用自加载 render-config 的 sheetCache 兜底，
  // 保证底稿目录架构树非空
  return Object.keys(formData.sheetCache.value).map(sheet_name => ({ sheet_name }))
})

// ─── useG7FormData 用于selfLoad ─────────────────────────────────────────────
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

provide('g7VersionTrailRef', versionTrailRef)
provide('g7OpenVersionHistory', openVersionHistory)

/** 目录页跳转：G7TabDirectory inject('jumpToSection') → emit('navigate-sheet') → GtWpRenderer */
const emit = defineEmits<{ 'navigate-sheet': [sheetName: string] }>()
provide('jumpToSection', (sheetName: string) => emit('navigate-sheet', sheetName))

const formData = useG7FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
  onAfterSave: () => scheduleAutoSnapshot(),
})
// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一提供，子组件 inject 命中祖先

/** G7 allResponses Map 供目录页进度/结论看板使用 */
const g7AllResponses = computed(() => formData.data.value)

// ─── 双模式切换 (HTML ↔ OnlyOffice) ─────────────────────────────────────────
const dualMode = useG7DualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: async () => {
    await formData.load()
    const parsed = formData.parseContent()
    if (parsed && Object.keys(parsed).length > 0) {
      selfLoadData.value = parsed as Record<string, any>
    }
  },
})

/** 审定发布：仅保存后 writebackTb=true 才回写 TB；打开/编辑中的广播不改试算表 */
function handleG7Adjudicated(e: Event): void {
  const detail = (e as CustomEvent<{
    accountCode?: string
    adjudicatedAmount?: number
    impairmentAccountCode?: string
    impairmentAmount?: number
    writebackTb?: boolean
  }>).detail
  if (detail?.accountCode !== G7_ACCOUNT_CODE) return
  if (detail.writebackTb !== true) return
  const amount = Number(detail.adjudicatedAmount)
  if (Number.isFinite(amount)) {
    void formData.writebackTB(amount, G7_ACCOUNT_CODE)
  }
  const impairAmt = Number(detail.impairmentAmount)
  if (Number.isFinite(impairAmt)) {
    void formData.writebackTB(impairAmt, detail.impairmentAccountCode || G7_IMPAIRMENT_CODE)
  }
}

// ─── selfLoad 模式：htmlData 为 null 时自动获取数据 ─────────────────────────
async function selfLoadInit(): Promise<void> {
  if (props.htmlData != null) return
  try {
    await formData.load()
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
  await selfLoadInit()
  isLoading.value = false
}

// ─── 生命周期 ───────────────────────────────────────────────────────────────
onMounted(async () => {
  window.addEventListener('substantive:adjudicated', handleG7Adjudicated)
  await selfLoadInit()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('substantive:adjudicated', handleG7Adjudicated)
})
</script>

<style scoped>
.g7-long-term-equity-main { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g7-long-term-equity-main-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
.g7-index-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
</style>
