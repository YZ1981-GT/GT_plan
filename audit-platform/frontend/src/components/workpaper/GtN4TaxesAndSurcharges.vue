<template>
  <div class="n4-taxes-and-surcharges">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="isHtmlSheet" class="n4-taxes-and-surcharges-toolbar">
        <GtWpAiReviewToolbar
          :wp-id="props.wpId"
          :project-id="props.projectId"
          wp-code-prefix="N4"
          :sheet-name="props.sheetName"
          label="税金及附加"
          @navigate-sheet="handleNavigate"
        />
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

      <!-- N4A 程序表 → 复用 a-program-console -->
      <GtCycleAProgramRouter
        v-else-if="currentSheet === 'N4A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :wp-code="'N4A'"
        :sheet-name="props.sheetName || ''"
      />

      <!-- O2A 原底稿 → skip，走 OnlyOffice fallback -->
      <GtOnlyOfficeSheet
        v-else-if="currentSheet === 'O2A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 底稿目录 -->
      <N4TabIndex
        v-else-if="currentSheet === 'N4' || currentSheet === '底稿目录'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N4-1 审定表（损益类，83公式，各税种分行，取发生额） -->
      <N4TabAdjudication
        v-else-if="currentSheet === 'N4-1'"
        :all-responses="allResponsesRef"
        :wp-id="wpIdRef"
        :project-id="projectIdRef"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N4-2 明细表（34×11，18公式，各税种发生额明细） -->
      <N4TabDetail
        v-else-if="currentSheet === 'N4-2'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N4-3 调整分录 -->
      <N4TabAdjustment
        v-else-if="currentSheet === 'N4-3'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- 附注（上市） -->
      <N4TabDisclosureListed
        v-else-if="currentSheet === '附注(上市)' || currentSheet === '附注（上市）'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- 附注（国企） -->
      <N4TabDisclosureSoe
        v-else-if="currentSheet === '附注(国企)' || currentSheet === '附注（国企）'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- 兜底：skip sheet / 未迁移 → OnlyOffice fallback -->
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
 * GtN4TaxesAndSurcharges.vue — N4 税金及附加底稿主入口
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/ Task 1.1
 * 科目: 6403税金及附加（损益类/借方）
 * 取数规则: 本期发生额（从tb_ledger），与H10/I6/N5同款
 * sheetName 分发到 N4 专属子组件（N4-1~N4-3），N4A走程序表，O2A走 OnlyOffice 兜底
 * 集成：useWorkpaperVersionToolbar(autoSnapshot on save) + provide('openReviewDialog')
 * EventBus：substantive:adjudicated(6403) / expense:taxes-surcharges-updated → A类利润表
 *
 * Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 1.8, 1.9, 1.11
 */
import { ref, computed, inject, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import GtWpAiReviewToolbar from './review/GtWpAiReviewToolbar.vue'

// ─── defineAsyncComponent lazy 加载子组件 ────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtCycleAProgramRouter = defineAsyncComponent(() => import('./GtCycleAProgramRouter.vue'))

// n4/core/
const N4TabIndex = defineAsyncComponent(() => import('./n4/core/N4TabIndex.vue'))
const N4TabAdjudication = defineAsyncComponent(() => import('./n4/core/N4TabAdjudication.vue'))
const N4TabDetail = defineAsyncComponent(() => import('./n4/core/N4TabDetail.vue'))
const N4TabAdjustment = defineAsyncComponent(() => import('./n4/core/N4TabAdjustment.vue'))
const N4TabDisclosureListed = defineAsyncComponent(() => import('./n4/core/N4TabDisclosureListed.vue'))
const N4TabDisclosureSoe = defineAsyncComponent(() => import('./n4/core/N4TabDisclosureSoe.vue'))

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
 * N4 子组件（N4TabIndex/N4TabAdjustment）emit 的是 'navigate-sheet'，其余可能 emit 'navigate'，两者都转发。
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
  // 匹配 N4A, O2A, N4-1~N4-3, N4, 底稿目录, 附注 等
  const m = name.match(/(N4A|O2A|N4-[1-3]|N4)/)
  if (m) return m[1]
  // 附注匹配
  if (name.includes('附注') && (name.includes('上市') || name.includes('国企'))) {
    return name.includes('上市') ? '附注(上市)' : '附注(国企)'
  }
  if (name.includes('底稿目录')) return '底稿目录'
  return name
})

/** skip sheet 列表（O2A原底稿标记skip走OO兜底） */
const SKIP_SHEETS = ['O2A']

/** HTML 专属组件渲染的 sheet（支持双模式切换）；N4A走程序表，O2A走OO */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  if (SKIP_SHEETS.some(sk => (props.sheetName || '').includes(sk))) return false
  if (s === 'N4A' || s === 'O2A') return false
  return /^N4-[1-3]$/.test(s) || s === 'N4' || s === '底稿目录'
    || s.includes('附注')
})

// ─── selfLoad（bundle内嵌场景 htmlData 为 null 时自加载） ─────────────────────
/**
 * 合并一个 responses 来源到目标 Map。
 * 后端 N4 render 策略实际输出键为 `checklist_responses`（dict {item_id: {...}}）；
 * 历史/其他策略可能用 `responses_snapshot` 或 `allResponses`，三键都合并，兼容 dict 与 array 两种形态。
 */
function _mergeResponses(map: Map<string, any>, src: any): void {
  if (!src || typeof src !== 'object') return
  if (Array.isArray(src)) {
    for (const r of src) {
      if (r?.item_id) map.set(r.item_id, r)
    }
    return
  }
  // 注入权威 item_id：dict 值缺 item_id 时以键补齐（否则保存 items 缺 item_id 触发 422）；v 自带 item_id 则以其为准
  for (const [k, v] of Object.entries(src)) map.set(k, (v && typeof v === 'object' && !Array.isArray(v)) ? { item_id: k, ...v } : { item_id: k, remark: v })
}

async function selfLoad(): Promise<void> {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { project_id: props.projectId },
    })
    const sheets = res.data?.data?.sheets || res.data?.sheets || []
    const map = new Map<string, any>()
    for (const sheet of sheets) {
      _mergeResponses(map, sheet?.html_data?.checklist_responses)
      _mergeResponses(map, sheet?.html_data?.responses_snapshot)
      _mergeResponses(map, sheet?.html_data?.allResponses)
    }
    if (map.size > 0) allResponses.value = map
  } catch (e) {
    console.error('[N4] selfLoad failed:', e)
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
    // 从 htmlData 解析 responses（兼容 checklist_responses / responses_snapshot / allResponses）
    const map = new Map<string, any>()
    _mergeResponses(map, props.htmlData?.checklist_responses)
    _mergeResponses(map, props.htmlData?.responses_snapshot)
    _mergeResponses(map, props.htmlData?.allResponses)
    allResponses.value = map
  }
  isLoading.value = false

  // ─── EventBus 订阅 ─────────────────────────────────────────────────
  eventBus.on('disclosure:refresh' as any, onDisclosureRefresh)
  eventBus.on('tax-accrual:updated', onTaxAccrualUpdated)
})

onBeforeUnmount(() => {
  eventBus.off('disclosure:refresh' as any, onDisclosureRefresh)
  eventBus.off('tax-accrual:updated', onTaxAccrualUpdated)
})

// ─── EventBus handlers ──────────────────────────────────────────────────────
function onDisclosureRefresh(): void {
  selfLoad()
}

function onTaxAccrualUpdated(): void {
  // N2各税种计提额变动 → 刷新N4数据（费用确认=计提额交叉验证）
  selfLoad()
}

// ─── 版本快照：子组件保存后触发自动快照（版本链能力来自 Runtime Boundary） ────
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())
</script>

<style scoped>
.n4-taxes-and-surcharges {
  width: 100%;
  min-height: 400px;
}
.n4-taxes-and-surcharges-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.loading-container {
  padding: 24px;
}
</style>
