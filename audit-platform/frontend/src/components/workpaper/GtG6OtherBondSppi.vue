<template>
  <div class="g6-other-bond-investment-sppi">
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
      <div class="g6-other-bond-investment-sppi-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          v-model="dualMode.currentMode.value"
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

      <!-- G6-5 公允价值测试表 -->
      <G6TabFairValueTest
        v-else-if="currentSheet === 'fairValueTest'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G6-6 利息测算表 -->
      <G6TabInterestCalculation
        v-else-if="currentSheet === 'interestCalculation'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G6-7 业务模式分析 -->
      <G6TabBusinessModel
        v-else-if="currentSheet === 'businessModel'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G6-8 SPPI测试 -->
      <G6TabSppiTest
        v-else-if="currentSheet === 'sppiTest'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G6-9 有价证券盘点表 -->
      <G6TabSecuritiesInventory
        v-else-if="currentSheet === 'securitiesInventory'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G6-10 盘点倒轧表 -->
      <G6TabInventoryRollForward
        v-else-if="currentSheet === 'inventoryRollForward'"
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

      <!-- 版本链/复核 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG6OtherBondSppi.vue — G6 其他债权投资(SPPI组)主入口
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 3.1
 * sheetName正则提取编码(G6-5~G6-10) → v-if分发到6个defineAsyncComponent子组件
 * 未匹配 → OnlyOffice fallback
 * 集成：useWorkpaperVersionToolbar(autoSnapshot) + provide('openReviewDialog') + 双模式切换
 * selfLoad：htmlData为null时通过useG6SppiFormData调用render-config获取数据
 *
 * Requirements: 1.1, 1.2, 1.4, 7.2
 */
import { ref, computed, onMounted, inject, defineAsyncComponent } from 'vue'
import { useG6SppiDualMode } from './composables/useG6SppiDualMode'
import { useG6SppiFormData } from './composables/useG6SppiFormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'

// ─── defineAsyncComponent 懒加载所有子组件 ───────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G6TabFairValueTest = defineAsyncComponent(
  () => import('./g6-other-bond-investment-sppi/fair-value/G6TabFairValueTest.vue'),
)
const G6TabInterestCalculation = defineAsyncComponent(
  () => import('./g6-other-bond-investment-sppi/interest/G6TabInterestCalculation.vue'),
)
const G6TabBusinessModel = defineAsyncComponent(
  () => import('./g6-other-bond-investment-sppi/classification/G6TabBusinessModel.vue'),
)
const G6TabSppiTest = defineAsyncComponent(
  () => import('./g6-other-bond-investment-sppi/classification/G6TabSppiTest.vue'),
)
const G6TabSecuritiesInventory = defineAsyncComponent(
  () => import('./g6-other-bond-investment-sppi/inspection/G6TabSecuritiesInventory.vue'),
)
const G6TabInventoryRollForward = defineAsyncComponent(
  () => import('./g6-other-bond-investment-sppi/inspection/G6TabInventoryRollForward.vue'),
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
  'G6-5': 'fairValueTest',
  'G6-6': 'interestCalculation',
  'G6-7': 'businessModel',
  'G6-8': 'sppiTest',
  'G6-9': 'securitiesInventory',
  'G6-10': 'inventoryRollForward',
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

  // 正则匹配：G6-5/G6-6/G6-7/G6-8/G6-9/G6-10
  const codeMatch = name.match(/G6-(5|6|7|8|9|10)/)
  if (codeMatch) {
    const code = `G6-${codeMatch[1]}`
    return SHEET_CODE_MAP[code] || ''
  }

  return ''
})

/** 已迁移为HTML专属组件的sheet列表（支持双模式切换） */
const HTML_SHEETS = new Set([
  'fairValueTest',
  'interestCalculation',
  'businessModel',
  'sppiTest',
  'securitiesInventory',
  'inventoryRollForward',
])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))

/** 解析后的 htmlData（优先使用prop，fallback到selfLoad结果） */
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

// ─── 双模式切换 ─────────────────────────────────────────────────────────────
const dualMode = useG6SppiDualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
})

// ─── useG6SppiFormData 用于selfLoad ─────────────────────────────────────────
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

const formData = useG6SppiFormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
  onAfterSave: () => scheduleAutoSnapshot(),
})
// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一提供，子组件 inject 命中祖先

// ─── selfLoad 模式：htmlData 为 null 时自动获取数据 ─────────────────────────
async function selfLoad(): Promise<void> {
  if (props.htmlData != null) return
  try {
    await formData.loadAll()
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
  await selfLoad()
  isLoading.value = false
})
</script>

<style scoped>
.g6-other-bond-investment-sppi { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g6-other-bond-investment-sppi-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
