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
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
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
      <G7TabDirectory
        v-else-if="currentSheet === 'directory'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
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

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
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
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import { useG7DualMode } from './composables/useG7DualMode'
import { useG7FormData } from './composables/useG7FormData'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'

// ─── defineAsyncComponent 懒加载所有子组件 ───────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
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
const G7TabDirectory = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/core/G7TabDirectory.vue'),
)
const G7TabDisclosureListed = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/disclosure/G7TabDisclosureListed.vue'),
)
const G7TabDisclosureSOE = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/disclosure/G7TabDisclosureSOE.vue'),
)

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

// ─── 双模式切换 (HTML ↔ OnlyOffice) ─────────────────────────────────────────
const dualMode = useG7DualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
})

// ─── useG7FormData 用于selfLoad ─────────────────────────────────────────────
const formData = useG7FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
  onAfterSave: () => versionToolbar.scheduleAutoSnapshot(),
})

// ─── 版本历史集成 (autoSnapshot on save) ────────────────────────────────────
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar

// ─── provide openReviewDialog 供子组件 inject ────────────────────────────────
function openReviewDialog(sectionId: string): void {
  console.log('[G7-main] openReviewDialog:', sectionId)
  // TODO: 接入 audit-review-dialog 模块（useReviewDialog）
}
provide('openReviewDialog', openReviewDialog)

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
  await selfLoadInit()
  isLoading.value = false
})
</script>

<style scoped>
.g7-long-term-equity-main { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g7-long-term-equity-main-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
