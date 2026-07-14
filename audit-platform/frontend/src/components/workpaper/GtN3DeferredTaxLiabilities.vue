<template>
  <div class="n3-deferred-tax-liabilities">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="isHtmlSheet" class="n3-deferred-tax-liabilities-toolbar">
        <el-segmented
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
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

      <!-- N3A 程序表 → OnlyOffice fallback（Phase 6 前暂不做HTML组件化） -->
      <GtOnlyOfficeSheet
        v-else-if="currentSheet === 'N3A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 底稿目录 -->
      <N3TabIndex
        v-else-if="currentSheet === 'N3' || currentSheet === '底稿目录'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N3-1 审定表（负债类，78公式，期末余额） -->
      <N3TabAdjudication
        v-else-if="currentSheet === 'N3-1'"
        :all-responses="allResponsesRef"
        :wp-id="wpIdRef"
        :project-id="projectIdRef"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N3-2 明细表（14列14公式，应纳税暂时性差异×税率） -->
      <N3TabDetail
        v-else-if="currentSheet === 'N3-2'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N3-3 调整分录 -->
      <N3TabAdjustment
        v-else-if="currentSheet === 'N3-3'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- 附注披露 -->
      <N3TabDisclosure
        v-else-if="currentSheet === '附注' || currentSheet === 'disclosure'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- 兜底：未迁移 sheet → OnlyOffice fallback -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtN3DeferredTaxLiabilities.vue — N3 递延所得税负债底稿主入口
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/ Task 1.1
 * 科目: 2901递延所得税负债（负债类/贷方）
 * sheetName 分发到 N3 专属子组件（N3-1~N3-3），N3A 走 OnlyOffice 兜底
 * 集成：useWorkpaperVersionToolbar(autoSnapshot on save) + provide('openReviewDialog')
 * EventBus：substantive:adjudicated(2901) / deferred-tax:liability-updated → N5
 */
import { ref, computed, inject, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'

// ─── defineAsyncComponent lazy 加载子组件 ────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const N3TabIndex = defineAsyncComponent(() => import('./n3/core/N3TabIndex.vue'))
const N3TabAdjudication = defineAsyncComponent(() => import('./n3/core/N3TabAdjudication.vue'))
const N3TabDetail = defineAsyncComponent(() => import('./n3/core/N3TabDetail.vue'))
const N3TabAdjustment = defineAsyncComponent(() => import('./n3/core/N3TabAdjustment.vue'))
const N3TabDisclosure = defineAsyncComponent(() => import('./n3/core/N3TabDisclosure.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

/**
 * 子组件目录行/返回按钮 emit navigate/navigate-sheet → 转发为 navigate-sheet 给外层 GtWpRenderer。
 * 铁律：GtWpRenderer 监听 @navigate-sheet，主入口必须 emit 'navigate-sheet'。
 */
function handleNavigate(sheetName: string): void {
  emit('navigate-sheet', sheetName)
}

// ─── 状态 ────────────────────────────────────────────────────────────────────
const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const allResponses = ref<Map<string, any>>(new Map())
const allResponsesRef = computed(() => allResponses.value)
const isReadonly = computed(() => !!props.readonly)
// ─── Runtime Boundary（GtWpRenderer 统一提供 版本/复核/AI + 挂真实 Host） ───
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)

// ─── 双模式 ──────────────────────────────────────────────────────────────────
const dualMode = {
  currentMode: ref<'html' | 'onlyoffice'>('html'),
  modeOptions: [
    { label: 'HTML', value: 'html' },
    { label: 'OnlyOffice', value: 'onlyoffice' },
  ],
  isOoAvailable: ref(true),
  onModeChange: () => {},
}

// ─── sheetName 正则提取编码 ──────────────────────────────────────────────────
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 匹配 N3A, N3-1~N3-3, N3
  const m = name.match(/(N3A|N3-\d+|N3)/)
  if (m) return m[1]
  if (name.includes('底稿目录')) return '底稿目录'
  if (name.includes('附注') || name.includes('披露')) return '附注'
  return name
})

/** N3-1~N3-3 + 附注 为 HTML 专属组件渲染的 sheet（支持双模式切换）；N3A 走 OnlyOffice */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return /^N3-\d+$/.test(s) || s === 'N3' || s === '底稿目录' || s === '附注'
})

// ─── selfLoad（bundle内嵌场景 htmlData 为 null 时自加载） ─────────────────────
/**
 * 合并一个 responses 来源到目标 Map。
 * 后端 N3 render 策略实际输出键为 `responses_snapshot`（dict {item_id: {...}}）；
 * 历史/其他策略可能用 `checklist_responses` 或 `allResponses`，三键都合并，兼容 dict 与 array 两种形态。
 */
function _mergeResponses(map: Map<string, any>, src: any): void {
  if (!src || typeof src !== 'object') return
  if (Array.isArray(src)) {
    for (const r of src) {
      if (r?.item_id) map.set(r.item_id, r)
    }
    return
  }
  for (const [k, v] of Object.entries(src)) map.set(k, v)
}

async function selfLoad(): Promise<void> {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { project_id: props.projectId },
    })
    const sheets = res.data?.data?.sheets || res.data?.sheets || []
    const map = new Map<string, any>()
    for (const sheet of sheets) {
      _mergeResponses(map, sheet?.html_data?.responses_snapshot)
      _mergeResponses(map, sheet?.html_data?.checklist_responses)
      _mergeResponses(map, sheet?.html_data?.allResponses)
    }
    if (map.size > 0) allResponses.value = map
  } catch (e) {
    console.error('[N3] selfLoad failed:', e)
  }
}

// 复核对话由 Runtime Boundary 统一 provide('openReviewDialog') + 挂真实 Host（删除 console 桩）。
provide('reloadWorkpaperData', selfLoad)

// ─── 生命周期 ────────────────────────────────────────────────────────────────
onMounted(async () => {
  // 如果 htmlData 为 null（selfLoad 场景），自行加载
  if (!props.htmlData) {
    await selfLoad()
  } else {
    // 从 htmlData 解析 responses（兼容 responses_snapshot / checklist_responses / allResponses）
    const map = new Map<string, any>()
    _mergeResponses(map, props.htmlData?.responses_snapshot)
    _mergeResponses(map, props.htmlData?.checklist_responses)
    _mergeResponses(map, props.htmlData?.allResponses)
    allResponses.value = map
  }
  isLoading.value = false

  // ─── EventBus 订阅 'disclosure:refresh' → 刷新数据 ────────────────────
  eventBus.on('disclosure:refresh' as any, onDisclosureRefresh)
})

onBeforeUnmount(() => {
  eventBus.off('disclosure:refresh' as any, onDisclosureRefresh)
})

// ─── EventBus handler: disclosure:refresh → 重新加载数据 ─────────────────────
function onDisclosureRefresh(): void {
  selfLoad()
}

// ─── 版本快照：子组件保存后触发自动快照（版本链能力来自 Runtime Boundary） ────
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())
</script>

<style scoped>
.n3-deferred-tax-liabilities { padding: 12px; }
.loading-container { padding: 24px; }
.n3-deferred-tax-liabilities-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
