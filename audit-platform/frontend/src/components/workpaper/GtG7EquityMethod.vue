<template>
  <div class="g7-long-term-equity-method">
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
      <!-- 工具栏：双模式切换 + 版本历史 -->
      <div class="g7-equity-method-toolbar">
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

      <!-- 本册无「底稿目录」sheet，用导航条提供目录/进度/手册入口 -->
      <G7SheetNavBar
        v-if="isHtmlSheet && dualMode.currentMode.value !== 'onlyoffice'"
        :sheets="navSheets"
        :current-code="sheetCode"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        title="G7 权益法组 · 底稿导航"
        workflow-hint="建议顺序：G7-4 基本信息 → G7-5 财务信息 → G7-6 会计政策差异 → G7-13 投资成本测试 → G7-14 权益法测算（可推 G7-3 建议分录）→ G7-15 内部交易抵销 → G7-16 未确认损失 → G7-17 减值测试（同步 G7-14 / 供 K11 减值来源）。"
        @navigate="(s: string) => emit('navigate-sheet', s)"
      />

      <!-- 双模式：HTML sheet 切到 OnlyOffice -->
      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- sheetName v-if 分发：匹配到编码的子组件 -->
      <component
        v-else-if="activeComponent"
        :is="activeComponent"
        :html-data="resolvedHtmlData"
        :sheet-name="props.sheetName || ''"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :readonly="isReadonly"
      />

      <!-- OnlyOffice fallback：未匹配到编码 -->
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
 * GtG7EquityMethod — G7 长期股权投资(权益法组) 主入口
 *
 * componentType: g7-long-term-equity-method
 * Spec: .kiro/specs/g7-long-term-equity-method/
 * Task: 1.1 (注册四件套) + 3.1 (主入口完整实现)
 *
 * 架构：
 * - 接收 sheetName prop，正则提取编码(G7-4/G7-5/G7-6/G7-13~G7-17)
 * - v-if 分发到 defineAsyncComponent 懒加载的8个子组件
 * - 未匹配编码 → OnlyOffice fallback
 * - htmlData为null时selfLoad逻辑(useG7EquityMethodFormData)
 * - 双模式切换(useG7EquityMethodDualMode): HTML ↔ OnlyOffice el-segmented
 * - 版本链集成：useWorkpaperVersionToolbar + autoSnapshot
 * - 复核集成：provide('openReviewDialog', openReviewDialog)
 *
 * Requirements: 1.1, 1.2, 1.4, 7.2
 */
import { ref, computed, onMounted, inject, defineAsyncComponent, type Component } from 'vue'
import G7SheetNavBar from './g7-shared/G7SheetNavBar.vue'
import { useG7EquityMethodDualMode } from './composables/useG7EquityMethodDualMode'
import { useG7EquityMethodFormData } from './composables/useG7EquityMethodFormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'

// ─── Lazy sub-components (defineAsyncComponent) ────────────────────────────
const G7TabBasicInfo = defineAsyncComponent(() => import('./g7-long-term-equity-method/info/G7TabBasicInfo.vue'))
const G7TabFinancialInfo = defineAsyncComponent(() => import('./g7-long-term-equity-method/info/G7TabFinancialInfo.vue'))
const G7TabAccountingPolicy = defineAsyncComponent(() => import('./g7-long-term-equity-method/info/G7TabAccountingPolicy.vue'))
const G7TabInvestmentCostTest = defineAsyncComponent(() => import('./g7-long-term-equity-method/calculation/G7TabInvestmentCostTest.vue'))
const G7TabEquityMethodCalc = defineAsyncComponent(() => import('./g7-long-term-equity-method/calculation/G7TabEquityMethodCalc.vue'))
const G7TabInternalTransaction = defineAsyncComponent(() => import('./g7-long-term-equity-method/calculation/G7TabInternalTransaction.vue'))
const G7TabUnrecognizedLoss = defineAsyncComponent(() => import('./g7-long-term-equity-method/impairment/G7TabUnrecognizedLoss.vue'))
const G7TabImpairmentTest = defineAsyncComponent(() => import('./g7-long-term-equity-method/impairment/G7TabImpairmentTest.vue'))

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// ─── Sheet code → component mapping ───────────────────────────────────────
const SHEET_COMPONENT_MAP: Record<string, Component> = {
  'G7-4': G7TabBasicInfo,
  'G7-5': G7TabFinancialInfo,
  'G7-6': G7TabAccountingPolicy,
  'G7-13': G7TabInvestmentCostTest,
  'G7-14': G7TabEquityMethodCalc,
  'G7-15': G7TabInternalTransaction,
  'G7-16': G7TabUnrecognizedLoss,
  'G7-17': G7TabImpairmentTest,
}

// ─── Props ─────────────────────────────────────────────────────────────────
const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName?: string
  wpId: string
  projectId: string
  wpCode?: string
  readonly?: boolean
}>()

/** 导航条点击 → 转发给 GtWpRenderer 切换 tab */
const emit = defineEmits<{ 'navigate-sheet': [sheetName: string] }>()

// ─── Reactive refs for composables ─────────────────────────────────────────
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const loadError = ref<string | null>(null)
const selfLoadData = ref<Record<string, any> | null>(null)

// ─── Sheet code extraction (regex) ─────────────────────────────────────────
const sheetCode = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 匹配 G7-4, G7-5, G7-6, G7-13, G7-14, G7-15, G7-16, G7-17
  const m = name.match(/G7-(\d+)/)
  if (m) {
    return `G7-${m[1]}`
  }
  return ''
})

// ─── Active component (v-if dispatch) ──────────────────────────────────────
const activeComponent = computed(() => {
  return SHEET_COMPONENT_MAP[sheetCode.value] || null
})

// ─── 导航条数据（优先用 render 返回的真实 sheetName，缺失时回退本地常量） ──────
const FALLBACK_NAV_SHEETS: Array<{ code: string; sheetName: string; shortLabel: string }> = [
  { code: 'G7-4', sheetName: '被投资单位基本信息G7-4', shortLabel: '基本信息' },
  { code: 'G7-5', sheetName: '被投资单位财务信息G7-5', shortLabel: '财务信息' },
  { code: 'G7-6', sheetName: '被投资公司会计政策G7-6', shortLabel: '会计政策' },
  { code: 'G7-13', sheetName: '投资成本测试表G7-13', shortLabel: '投资成本测试' },
  { code: 'G7-14', sheetName: '权益法测算表G7-14', shortLabel: '权益法测算' },
  { code: 'G7-15', sheetName: '内部交易抵销测算表G7-15', shortLabel: '内部交易抵销' },
  { code: 'G7-16', sheetName: '未确认投资损失测试表G7-16', shortLabel: '未确认损失' },
  { code: 'G7-17', sheetName: '减值测试表G7-17', shortLabel: '减值测试' },
]

const navSheets = computed(() => {
  const fromRender = ((props.htmlData ?? selfLoadData.value) as any)?.sheets
  if (!Array.isArray(fromRender) || fromRender.length === 0) return FALLBACK_NAV_SHEETS
  const byCode = new Map(FALLBACK_NAV_SHEETS.map((s) => [s.code, s]))
  const mapped = fromRender
    .filter((s: any) => SHEET_COMPONENT_MAP[String(s?.code || '')])
    .map((s: any) => ({
      code: String(s.code),
      sheetName: String(s.sheetName || s.code),
      shortLabel: byCode.get(String(s.code))?.shortLabel || String(s.code),
    }))
  return mapped.length ? mapped : FALLBACK_NAV_SHEETS
})

/** 已匹配到HTML子组件的sheet（支持双模式切换） */
const isHtmlSheet = computed(() => !!activeComponent.value)

/** 解析后的 htmlData（优先使用prop，fallback到selfLoad结果） */
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

// ─── useG7EquityMethodFormData 用于selfLoad ─────────────────────────────────
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

const formData = useG7EquityMethodFormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
  onAfterSave: () => scheduleAutoSnapshot(),
})
// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一提供，子组件 inject 命中祖先

// ─── 双模式切换 (HTML ↔ OnlyOffice) ─────────────────────────────────────────
const dualMode = useG7EquityMethodDualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: async () => {
    await formData.load()
    const parsed = formData.parseContent()
    if (parsed && Object.keys(parsed).length > 0) {
      selfLoadData.value = parsed
    }
  },
})

// ─── selfLoad 模式：htmlData 为 null 时自动获取数据 ─────────────────────────
async function selfLoadInit(): Promise<void> {
  if (props.htmlData != null) return
  try {
    await formData.load()
    const parsed = formData.parseContent()
    if (parsed && Object.keys(parsed).length > 0) {
      selfLoadData.value = parsed
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

// ─── Lifecycle ─────────────────────────────────────────────────────────────
onMounted(async () => {
  await selfLoadInit()
  isLoading.value = false
})
</script>

<style scoped>
.g7-long-term-equity-method {
  padding: 12px;
}
.loading-container {
  padding: 24px;
}
.error-container {
  padding: 24px;
}
.g7-equity-method-toolbar {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
