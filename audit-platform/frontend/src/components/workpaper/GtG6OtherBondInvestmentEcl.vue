<template>
  <div class="g6-other-bond-investment-ecl">
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
      <div class="g6-other-bond-investment-ecl-toolbar">
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

      <!-- G6-11 三阶段划分 -->
      <G6TabStageClassification
        v-else-if="currentSheet === 'stageClassification'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G6-12 减值准备测算表 -->
      <G6TabImpairmentCalc
        v-else-if="currentSheet === 'impairmentCalc'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G6-13 预期信用损失计量测试 -->
      <G6TabEclMeasurement
        v-else-if="currentSheet === 'eclMeasurement'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G6-14 减值准备转回核销检查 -->
      <G6TabReversalWriteOff
        v-else-if="currentSheet === 'reversalWriteOff'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G6-15 凭证检查表 -->
      <G6TabVoucherCheck
        v-else-if="currentSheet === 'voucherCheck'"
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
 * ⚠️ 死代码标注（fghi-sheet-content-completion Task 13.2，2026-07-13）：
 *   htmlRendererRegistry.ts 将 componentType `g6-other-bond-investment-ecl`
 *   映射到 `GtG6OtherBondEcl.vue`（根目录同名简版：仅 GtGridSheet + OO 兜底），
 *   而非本文件。本文件（真正 v-if 分发 5 个子组件 StageClassification/
 *   ImpairmentCalc/EclMeasurement/ReversalWriteOff/VoucherCheck 的调度器）
 *   未在任何 registry / wp_code_overrides 中被引用 → 当前为孤立/死代码。
 *   与 main/sppi 组（短名 GtG6OtherBondMain/GtG6OtherBondSppi 即调度器且已注册）
 *   命名约定相反：ECL 的短名文件是简版桩、长名文件是调度器。
 *   注意：本 spec 打磨的 5 个 ECL 子组件仅经本（未注册）调度器可达。
 *   按任务要求仅标注不删除、不改注册表（重接属独立决策，需人工确认）。
 *
 * GtG6OtherBondInvestmentEcl.vue — G6 其他债权投资底稿(ECL组)主入口
 *
 * Spec: .kiro/specs/g6-other-bond-investment-ecl/ Task 3.1
 * sheetName正则提取编码(G6-11~G6-15) → v-if分发到5个defineAsyncComponent子组件
 * 未匹配 → OnlyOffice fallback
 * 集成：useWorkpaperVersionToolbar(autoSnapshot) + provide('openReviewDialog') + 双模式切换
 * selfLoad：htmlData为null时通过useG6EclFormData调用render-config获取数据
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 6.2
 */
import { ref, computed, onMounted, inject, defineAsyncComponent } from 'vue'
import { useG6EclDualMode } from './composables/useG6EclDualMode'
import { useG6EclFormData } from './composables/useG6EclFormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'

// ─── defineAsyncComponent 懒加载所有子组件 ───────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G6TabStageClassification = defineAsyncComponent(
  () => import('./g6-other-bond-investment-ecl/impairment/G6TabStageClassification.vue'),
)
const G6TabImpairmentCalc = defineAsyncComponent(
  () => import('./g6-other-bond-investment-ecl/impairment/G6TabImpairmentCalc.vue'),
)
const G6TabEclMeasurement = defineAsyncComponent(
  () => import('./g6-other-bond-investment-ecl/impairment/G6TabEclMeasurement.vue'),
)
const G6TabReversalWriteOff = defineAsyncComponent(
  () => import('./g6-other-bond-investment-ecl/impairment/G6TabReversalWriteOff.vue'),
)
const G6TabVoucherCheck = defineAsyncComponent(
  () => import('./g6-other-bond-investment-ecl/voucher/G6TabVoucherCheck.vue'),
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
  'G6-11': 'stageClassification',
  'G6-12': 'impairmentCalc',
  'G6-13': 'eclMeasurement',
  'G6-14': 'reversalWriteOff',
  'G6-15': 'voucherCheck',
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

  // 正则匹配：G6-11/G6-12/G6-13/G6-14/G6-15
  const codeMatch = name.match(/G6-1([1-5])/)
  if (codeMatch) {
    const code = `G6-1${codeMatch[1]}`
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
])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))

/** 解析后的 htmlData（优先使用prop，fallback到selfLoad结果） */
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

// ─── 双模式切换 ─────────────────────────────────────────────────────────────
const dualMode = useG6EclDualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
})

// ─── useG6EclFormData 用于selfLoad ──────────────────────────────────────────
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

const formData = useG6EclFormData({
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
.g6-other-bond-investment-ecl { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g6-other-bond-investment-ecl-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
