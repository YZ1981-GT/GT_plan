<template>
  <div class="g4-bond-investment-main">
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
      <div class="g4-bond-investment-main-toolbar">
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

      <!-- G4A 程序表 -->
      <G4TabProcedure
        v-else-if="currentSheet === 'procedure'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G4-1 审定表 -->
      <G4TabAdjudication
        v-else-if="currentSheet === 'adjudication'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G4-2 明细表 -->
      <G4TabDetail
        v-else-if="currentSheet === 'detail'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G4-3 调整分录 -->
      <G4TabAdjustment
        v-else-if="currentSheet === 'adjustment'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G4-4 利息测算表 -->
      <G4TabInterestCalc
        v-else-if="currentSheet === 'interestCalc'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 附注披露(上市) -->
      <G4TabDisclosureListed
        v-else-if="currentSheet === 'disclosureListed'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 附注披露(国企) -->
      <G4TabDisclosureSOE
        v-else-if="currentSheet === 'disclosureSOE'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 底稿目录 -->
      <G4TabDirectory
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

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG4BondInvestmentMain.vue — G4 债权投资底稿(main组)主入口
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Task 3.1~3.6
 * sheetName正则提取编码 → v-if分发到8个子组件（defineAsyncComponent lazy）
 * 未匹配 → OnlyOffice fallback
 * 集成：useWorkpaperVersionToolbar(autoSnapshot) + provide('openReviewDialog') + 双模式切换
 * selfLoad：htmlData为null时自动调用 render-config 获取数据
 */
import { ref, computed, onMounted, provide, inject, defineAsyncComponent } from 'vue'
import { useG4MainDualMode } from './composables/useG4MainDualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import http from '@/utils/http'

// ─── defineAsyncComponent 懒加载所有子组件 ───────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G4TabProcedure = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabProcedure.vue'))
const G4TabAdjudication = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabAdjudication.vue'))
const G4TabDetail = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabDetail.vue'))
const G4TabAdjustment = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabAdjustment.vue'))
const G4TabDisclosureListed = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabDisclosureListed.vue'))
const G4TabDisclosureSOE = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabDisclosureSOE.vue'))
const G4TabDirectory = defineAsyncComponent(() => import('./g4-bond-investment-main/core/G4TabDirectory.vue'))
const G4TabInterestCalc = defineAsyncComponent(() => import('./g4-bond-investment-main/measurement/G4TabInterestCalc.vue'))

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
  'G4A': 'procedure',
  'G4-1': 'adjudication',
  'G4-2': 'detail',
  'G4-3': 'adjustment',
  'G4-4': 'interestCalc',
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
  // 精确匹配中文全称
  if (SHEET_CODE_MAP[name]) return SHEET_CODE_MAP[name]
  // 正则匹配：G4A、G4-1~G4-4
  const codeMatch = name.match(/(G4A|G4-[1-4])/)
  if (codeMatch) return SHEET_CODE_MAP[codeMatch[1]] || ''
  // 中文关键词匹配
  if (/附注披露/.test(name)) {
    return name.includes('国企') ? 'disclosureSOE' : 'disclosureListed'
  }
  if (/底稿目录/.test(name)) return 'directory'
  return ''
})

/** 已迁移为HTML专属组件的sheet列表（支持双模式切换） */
const HTML_SHEETS = new Set([
  'procedure', 'adjudication', 'detail', 'adjustment',
  'interestCalc', 'disclosureListed', 'disclosureSOE', 'directory',
])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))

/** 解析后的 htmlData（优先使用prop，fallback到selfLoad结果） */
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

// ─── 双模式切换 ─────────────────────────────────────────────────────────────
const dualMode = useG4MainDualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
})

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)

provide('g4VersionTrailRef', versionTrailRef)
provide('g4OpenVersionHistory', openVersionHistory)

// 复核对话 openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide，子组件 inject 命中祖先

// ─── selfLoad 模式：htmlData 为 null 时自动获取数据 ─────────────────────────
async function selfLoad(): Promise<void> {
  if (props.htmlData != null) return
  try {
    const { data } = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { force_component_type: 'g4-bond-investment-main' },
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
.g4-bond-investment-main { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g4-bond-investment-main-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
