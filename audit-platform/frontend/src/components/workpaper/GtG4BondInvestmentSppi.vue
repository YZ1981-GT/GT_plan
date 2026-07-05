<template>
  <div class="g4-bond-investment-sppi">
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
      <div class="g4-bond-investment-sppi-toolbar">
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

      <!-- G4-5 业务模式分析 -->
      <G4TabBusinessModel
        v-else-if="currentSheet === 'businessModel'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G4-6 SPPI合同现金流量特征分析 -->
      <G4TabSppiTest
        v-else-if="currentSheet === 'sppiTest'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G4-7 有价证券盘点表 -->
      <G4TabSecuritiesInventory
        v-else-if="currentSheet === 'securitiesInventory'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G4-8 盘点倒轧结存表 -->
      <G4TabInventoryReconciliation
        v-else-if="currentSheet === 'inventoryReconciliation'"
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
 * GtG4BondInvestmentSppi.vue — G4 债权投资底稿(SPPI组)主入口
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 3.1
 * sheetName正则提取编码(G4-5~G4-8) → v-if分发到4个子组件（defineAsyncComponent lazy）
 * 未匹配 → OnlyOffice fallback
 * 集成：useWorkpaperVersionToolbar(autoSnapshot) + provide('openReviewDialog') + 双模式切换
 * selfLoad：htmlData为null时自动调用 render-config 获取数据
 */
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import { useG4SppiDualMode } from '@/composables/useG4SppiDualMode'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import http from '@/utils/http'

// ─── defineAsyncComponent 懒加载所有子组件 ───────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const G4TabBusinessModel = defineAsyncComponent(
  () => import('./g4-bond-investment-sppi/classification/G4TabBusinessModel.vue'),
)
const G4TabSppiTest = defineAsyncComponent(
  () => import('./g4-bond-investment-sppi/classification/G4TabSppiTest.vue'),
)
const G4TabSecuritiesInventory = defineAsyncComponent(
  () => import('./g4-bond-investment-sppi/inspection/G4TabSecuritiesInventory.vue'),
)
const G4TabInventoryReconciliation = defineAsyncComponent(
  () => import('./g4-bond-investment-sppi/inspection/G4TabInventoryReconciliation.vue'),
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
  'G4-5': 'businessModel',
  'G4-6': 'sppiTest',
  'G4-7': 'securitiesInventory',
  'G4-8': 'inventoryReconciliation',
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
  // 正则匹配：G4-5/G4-6/G4-7/G4-8
  const codeMatch = name.match(/G4-([5-8])/)
  if (codeMatch) {
    const code = `G4-${codeMatch[1]}`
    return SHEET_CODE_MAP[code] || ''
  }
  return ''
})

/** 已迁移为HTML专属组件的sheet列表（支持双模式切换） */
const HTML_SHEETS = new Set([
  'businessModel', 'sppiTest', 'securitiesInventory', 'inventoryReconciliation',
])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))

/** 解析后的 htmlData（优先使用prop，fallback到selfLoad结果） */
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

// ─── 双模式切换 ─────────────────────────────────────────────────────────────
const dualMode = useG4SppiDualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
})

// ─── 版本历史集成 ───────────────────────────────────────────────────────────
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar

// ─── provide openReviewDialog 供子组件 inject ────────────────────────────────
function openReviewDialog(sectionId: string): void {
  console.log('[G4-sppi] openReviewDialog:', sectionId)
}
provide('openReviewDialog', openReviewDialog)

// ─── selfLoad 模式：htmlData 为 null 时自动获取数据 ─────────────────────────
async function selfLoad(): Promise<void> {
  if (props.htmlData != null) return
  try {
    const { data } = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { force_component_type: 'g4-bond-investment-sppi' },
    })
    // render-config 返回 {sheets:[{html_data:{...}}]}
    const sheets = data?.sheets ?? data?.data?.sheets
    if (sheets && sheets.length > 0) {
      selfLoadData.value = sheets[0].html_data ?? sheets[0]
    } else {
      selfLoadData.value = data
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
.g4-bond-investment-sppi { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g4-bond-investment-sppi-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
