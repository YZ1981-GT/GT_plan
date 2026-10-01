<template>
  <div class="n4-taxes-and-surcharges">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'N4' && currentSheet !== '底稿目录'" class="n4-taxes-and-surcharges-toolbar">
        <el-segmented
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
        <!--
          AC 1.4 的「可操作原因」—— 未注册 adapter 却给出可点的模式切换时必须常显。
          spec: n-cycle-sync-foundation-and-first-canary Task 19（BP-7）
          🔴 只放 el-tooltip 不算接线：EP 的 tooltip 内容 hover 后才进 DOM。
        -->
        <GtEntrySyncCapabilityNotice :entry-id="N4_ENTRY_ID" />
      </div>

      <!-- 双模式：HTML sheet 切到 OnlyOffice -->
      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
        @fallback="dualMode.onOoLoadFailed"
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

      <!-- 附注（上市）—— 🔴 必须传 projectId，否则同步按钮永久锁死 -->
      <N4TabDisclosureListed
        v-else-if="currentSheet === N4_SHEET_DISCLOSURE_LISTED"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- 附注（国企）—— 源模板此节为「无」→ 本版不适用说明页 -->
      <N4TabDisclosureSoe
        v-else-if="currentSheet === N4_SHEET_DISCLOSURE_SOE"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
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
import { ElMessage } from 'element-plus'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { fetchOnlyOfficeHealthy } from './sync/onlyOfficeHealth'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
// ─── defineAsyncComponent lazy 加载子组件 ────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtCycleAProgramRouter = defineAsyncComponent(() => import('./GtCycleAProgramRouter.vue'))
const GtEntrySyncCapabilityNotice = defineAsyncComponent(
  () => import('./sync/GtEntrySyncCapabilityNotice.vue'),
)

// n4/core/
const N4TabIndex = defineAsyncComponent(() => import('./n4/core/N4TabIndex.vue'))
const N4TabAdjudication = defineAsyncComponent(() => import('./n4/core/N4TabAdjudication.vue'))
const N4TabDetail = defineAsyncComponent(() => import('./n4/core/N4TabDetail.vue'))
const N4TabAdjustment = defineAsyncComponent(() => import('./n4/core/N4TabAdjustment.vue'))
const N4TabDisclosureListed = defineAsyncComponent(() => import('./n4/core/N4TabDisclosureListed.vue'))
const N4TabDisclosureSoe = defineAsyncComponent(() => import('./n4/core/N4TabDisclosureSoe.vue'))

import {
  N4_SHEET_DISCLOSURE_LISTED,
  N4_SHEET_DISCLOSURE_SOE,
  isN4HtmlSheet,
  normalizeN4SheetName,
} from './composables/n4SheetRouting'

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

/** manifest 的稳定 entry_id —— AC 1.4 通知与 sync 判据的唯一锚点 */
const N4_ENTRY_ID = 'xlsx/gt-n4-taxes-and-surcharges'

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
/**
 * 🔴 这里原先是 `onModeChange: () => {}` 的**空实现**（BP-5 / NC-13）：
 * `<el-segmented>` 显示两个可点选项，但 `currentMode` 永远是 `'html'`，
 * 下面那个 `v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"`
 * 的 OO 挂载点**结构性不可达** —— 正是 AC 1.4 禁止的「以双模式成功态呈现假双向」。
 *
 * spec: n-cycle-sync-foundation-and-first-canary Task 13（canary 短板①）
 *
 * 三条设计约束：
 * 1. **保留宿主内联形态**（决策 3：不做载体归一化重构），只把开关变成可兑现的。
 * 2. 健康探针走平台**统一能力层** `sync/onlyOfficeHealth.ts`（带 TTL 缓存 + 并发去重），
 *    SHALL NOT 在这里再抄一份 `http.get('/api/workpapers/onlyoffice/health')` ——
 *    「各自再抄一遍」正是该模块被提到 `sync/` 层要解决的问题（BP-4 同源）。
 * 3. `modeOptions` **不带 `disabled`**：D4 已实证，未就绪时置灰会把入口彻底锁死、
 *    点击被吞掉。门禁放在 `onModeChange` 里 `await` 兜底 + 失败显式回落并提示。
 */
const currentMode = ref<'html' | 'onlyoffice'>('html')
const isOoAvailable = ref(true)
const modeOptions = [
  { label: 'HTML', value: 'html' },
  { label: 'OnlyOffice', value: 'onlyoffice' },
]

async function onModeChange(val: string | number | boolean): Promise<void> {
  const next = String(val) === 'onlyoffice' ? 'onlyoffice' : 'html'
  if (next === currentMode.value) return
  if (next === 'onlyoffice') {
    // forceRefresh：用户**已经点了**，不能被一个卡在过期边界的旧值挡住这次真实点击
    const healthy = await fetchOnlyOfficeHealthy(true)
    isOoAvailable.value = healthy
    if (!healthy) {
      currentMode.value = 'html'
      ElMessage.warning('OnlyOffice 服务当前不可用，已保持 HTML 模式')
      return
    }
  }
  currentMode.value = next
}

/** GtOnlyOfficeSheet @fallback：文档渲染/超时失败 → 回落 HTML 并标记不可用 */
function onOoLoadFailed(): void {
  isOoAvailable.value = false
  currentMode.value = 'html'
  ElMessage.warning('OnlyOffice 文档加载失败，已回落 HTML 模式')
}

const dualMode = { currentMode, modeOptions, isOoAvailable, onModeChange, onOoLoadFailed }

// ─── sheetName 归一（纯函数，见 composables/n4SheetRouting.ts）────────────────
// 🔴 披露判定前置于 wp_code 正则 + 国企多写法全认，防披露组件静默挂不上
const currentSheet = computed(() => normalizeN4SheetName(props.sheetName, props.wpCode))

/** skip sheet 列表（O2A原底稿标记skip走OO兜底） */
const SKIP_SHEETS = ['O2A']

/** HTML 专属组件渲染的 sheet（支持双模式切换）；N4A走程序表，O2A走OO */
const isHtmlSheet = computed(() => {
  if (SKIP_SHEETS.some(sk => (props.sheetName || '').includes(sk))) return false
  return isN4HtmlSheet(currentSheet.value)
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

// ─── 复核圆点（GtReviewDot 依赖 getThreadDot/getRowDot；Runtime Boundary 只 provide openReviewDialog） ───
const reviewThreads = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', reviewThreads.getThreadDot)
provide('getRowDot', reviewThreads.getRowDot)

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

  // OO 可用性预检（统一能力层带 TTL 缓存 + 并发去重，切底稿不会逐张重打）
  isOoAvailable.value = await fetchOnlyOfficeHealthy()

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
