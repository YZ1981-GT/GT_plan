<template>
  <div class="g7-long-term-equity-subsidiary">
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
      <div class="g7-subsidiary-toolbar">
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
        title="G7 子公司组 · 底稿导航"
        workflow-hint="建议顺序：G7-7 控制判断 → G7-8 同控初始计量 / G7-9 非同控初始计量 → G7-10 后续计量检查 → G7-11 处置（非一揽子）/ G7-12 处置（一揽子）→ G7-18 凭证检查（抽凭 1511）。初始计量与处置结果经合并联动进入合并工作底稿。"
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
 * GtG7EquitySubsidiary — G7 长期股权投资(子公司组) 主入口
 *
 * componentType: g7-long-term-equity-subsidiary
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/
 * Task: 3.1 (主入口 sheetName v-if dispatch)
 *
 * 架构：
 * - 接收 sheetName prop，正则提取编码(G7-7/G7-8/G7-9/G7-10/G7-11/G7-12/G7-18)
 * - v-if 分发到 defineAsyncComponent 懒加载的7个子组件
 * - 未匹配编码 → OnlyOffice fallback
 * - htmlData为null时selfLoad逻辑(useG7SubFormData)
 * - 双模式切换(useG7SubDualMode): HTML ↔ OnlyOffice el-segmented
 * - 版本链集成：useWorkpaperVersionToolbar + autoSnapshot
 * - 复核集成：provide('openReviewDialog', openReviewDialog)
 *
 * 子目录分组:
 *   initial/   → G7-7(控制判断) + G7-8(同控) + G7-9(非同控)
 *   subsequent/ → G7-10(后续计量)
 *   disposal/  → G7-11(非一揽子) + G7-12(一揽子)
 *   voucher/   → G7-18(凭证检查)
 *
 * Requirements: 1.1, 1.2, 1.4, 7.2
 */
import { ref, computed, onMounted, inject, defineAsyncComponent, type Component } from 'vue'
import G7SheetNavBar from './g7-shared/G7SheetNavBar.vue'
import { useG7SubDualMode } from './composables/useG7SubDualMode'
import { useG7SubFormData } from './composables/useG7SubFormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'

// ─── Lazy sub-components (defineAsyncComponent × 7) ────────────────────────
const G7TabControlJudgment = defineAsyncComponent(() => import('./g7-long-term-equity-subsidiary/initial/G7TabControlJudgment.vue'))
const G7TabSameControlMeasurement = defineAsyncComponent(() => import('./g7-long-term-equity-subsidiary/initial/G7TabSameControlMeasurement.vue'))
const G7TabNotSameControlMeasurement = defineAsyncComponent(() => import('./g7-long-term-equity-subsidiary/initial/G7TabNotSameControlMeasurement.vue'))
const G7TabSubsequentMeasurement = defineAsyncComponent(() => import('./g7-long-term-equity-subsidiary/subsequent/G7TabSubsequentMeasurement.vue'))
const G7TabDisposalSingle = defineAsyncComponent(() => import('./g7-long-term-equity-subsidiary/disposal/G7TabDisposalSingle.vue'))
const G7TabDisposalPackage = defineAsyncComponent(() => import('./g7-long-term-equity-subsidiary/disposal/G7TabDisposalPackage.vue'))
const G7TabVoucherCheck = defineAsyncComponent(() => import('./g7-long-term-equity-subsidiary/voucher/G7TabVoucherCheck.vue'))

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// ─── Sheet code → component mapping ───────────────────────────────────────
const SHEET_COMPONENT_MAP: Record<string, Component> = {
  'G7-7': G7TabControlJudgment,
  'G7-8': G7TabSameControlMeasurement,
  'G7-9': G7TabNotSameControlMeasurement,
  'G7-10': G7TabSubsequentMeasurement,
  'G7-11': G7TabDisposalSingle,
  'G7-12': G7TabDisposalPackage,
  'G7-18': G7TabVoucherCheck,
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
  // 匹配 G7-7, G7-8, G7-9, G7-10, G7-11, G7-12, G7-18
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

/** 已匹配到HTML子组件的sheet（支持双模式切换） */
const isHtmlSheet = computed(() => !!activeComponent.value)

/** 解析后的 htmlData（优先使用prop，fallback到selfLoad结果） */
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

// ─── 导航条数据（优先用 render 返回的真实 sheetName，缺失时回退本地常量） ──────
const FALLBACK_NAV_SHEETS: Array<{ code: string; sheetName: string; shortLabel: string }> = [
  { code: 'G7-7', sheetName: '投资初始确认判断G7-7', shortLabel: '控制判断' },
  { code: 'G7-8', sheetName: '子公司初始计量测试（同控）G7-8', shortLabel: '同控初始计量' },
  { code: 'G7-9', sheetName: '非同一控制下企业合并G7-9', shortLabel: '非同控初始计量' },
  { code: 'G7-10', sheetName: '后续计量检查G7-10', shortLabel: '后续计量' },
  { code: 'G7-11', sheetName: '处置检查（非一揽子交易）G7-11', shortLabel: '处置(非一揽子)' },
  { code: 'G7-12', sheetName: '处置检查（一揽子交易）G7-12', shortLabel: '处置(一揽子)' },
  { code: 'G7-18', sheetName: '凭证检查表G7-18', shortLabel: '凭证检查' },
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

// ─── useG7SubFormData 用于selfLoad ──────────────────────────────────────────
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

const formData = useG7SubFormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
  onAfterSave: () => scheduleAutoSnapshot(),
})
// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一提供，子组件 inject 命中祖先

// ─── 双模式切换 (HTML ↔ OnlyOffice) ─────────────────────────────────────────
const dualMode = useG7SubDualMode({
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
.g7-long-term-equity-subsidiary {
  padding: 12px;
}
.loading-container {
  padding: 24px;
}
.error-container {
  padding: 24px;
}
.g7-subsidiary-toolbar {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
