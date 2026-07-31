<template>
  <div class="n2-taxes-payable">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'N2' && currentSheet !== '底稿目录'" class="n2-taxes-payable-toolbar">
        <el-segmented
          :model-value="dualMode.currentMode.value"
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

      <!-- N2A 程序表 → OnlyOffice fallback -->
      <GtOnlyOfficeSheet
        v-else-if="currentSheet === 'N2A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 底稿目录 -->
      <N2TabIndex
        v-else-if="currentSheet === 'N2' || currentSheet === '底稿目录'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N2-1 审定表（负债类，85公式，多税种分行） -->
      <N2TabAdjudication
        v-else-if="currentSheet === 'N2-1'"
        :all-responses="allResponsesRef"
        :wp-id="wpIdRef"
        :project-id="projectIdRef"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N2-2 明细表（23列区段Tab，22公式） -->
      <N2TabDetail
        v-else-if="currentSheet === 'N2-2'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N2-3 调整分录 -->
      <N2TabAdjustment
        v-else-if="currentSheet === 'N2-3'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N2-4 税收政策检查 -->
      <N2TabPolicyCheck
        v-else-if="currentSheet === 'N2-4'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N2-5 应交税金认定表（54×15） -->
      <N2TabRecognition
        v-else-if="currentSheet === 'N2-5'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N2-6 增值税测算表（48×8） -->
      <N2TabVatCalc
        v-else-if="currentSheet === 'N2-6'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N2-7 出口退税核对表 -->
      <N2TabExportRefund
        v-else-if="currentSheet === 'N2-7'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N2-8 应交其他税费测算表（26×9，11公式） -->
      <N2TabOtherTaxCalc
        v-else-if="currentSheet === 'N2-8'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N2-9 房产税测算表（30×7） -->
      <N2TabPropertyTax
        v-else-if="currentSheet === 'N2-9'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N2-10 土地增值税测算表（51×7） -->
      <N2TabLvt
        v-else-if="currentSheet === 'N2-10'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N2-11 应交税费检查表 -->
      <N2TabTaxCheck
        v-else-if="currentSheet === 'N2-11'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- 附注（上市）—— 🔴 必须传 projectId，否则同步（含自动同步）永久静默失败 -->
      <N2TabDisclosureListed
        v-else-if="currentSheet === N2_SHEET_DISCLOSURE_LISTED"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />

      <!-- 附注（国企） -->
      <N2TabDisclosureSoe
        v-else-if="currentSheet === N2_SHEET_DISCLOSURE_SOE"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
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
 * GtN2TaxesPayable.vue — N2 应交税费底稿主入口
 *
 * Spec: .kiro/specs/n2-taxes-payable/ Task 1.1
 * 科目: 2221应交税费（负债类/贷方）
 * sheetName 分发到 N2 专属子组件（N2-1~N2-11），N2A/O1A/出口退税额复核示例走 OnlyOffice 兜底
 * 集成：useWorkpaperVersionToolbar(autoSnapshot on save) + provide('openReviewDialog')
 * EventBus：substantive:adjudicated(2221) / tax-accrual:updated → N4
 */
import { ref, computed, inject, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import {
  N2_SHEET_DISCLOSURE_LISTED,
  N2_SHEET_DISCLOSURE_SOE,
  isN2HtmlSheet,
  normalizeN2SheetName,
} from './composables/n2SheetRouting'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
// ─── defineAsyncComponent lazy 加载子组件 ────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const N2TabIndex = defineAsyncComponent(() => import('./n2/core/N2TabIndex.vue'))
const N2TabAdjudication = defineAsyncComponent(() => import('./n2/core/N2TabAdjudication.vue'))
const N2TabDetail = defineAsyncComponent(() => import('./n2/core/N2TabDetail.vue'))
const N2TabAdjustment = defineAsyncComponent(() => import('./n2/core/N2TabAdjustment.vue'))
const N2TabDisclosureListed = defineAsyncComponent(() => import('./n2/core/N2TabDisclosureListed.vue'))
const N2TabDisclosureSoe = defineAsyncComponent(() => import('./n2/core/N2TabDisclosureSoe.vue'))
const N2TabPolicyCheck = defineAsyncComponent(() => import('./n2/inspection/N2TabPolicyCheck.vue'))
const N2TabRecognition = defineAsyncComponent(() => import('./n2/inspection/N2TabRecognition.vue'))
const N2TabTaxCheck = defineAsyncComponent(() => import('./n2/inspection/N2TabTaxCheck.vue'))
const N2TabVatCalc = defineAsyncComponent(() => import('./n2/calc/N2TabVatCalc.vue'))
const N2TabExportRefund = defineAsyncComponent(() => import('./n2/calc/N2TabExportRefund.vue'))
const N2TabOtherTaxCalc = defineAsyncComponent(() => import('./n2/calc/N2TabOtherTaxCalc.vue'))
const N2TabPropertyTax = defineAsyncComponent(() => import('./n2/calc/N2TabPropertyTax.vue'))
const N2TabLvt = defineAsyncComponent(() => import('./n2/calc/N2TabLvt.vue'))

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

// ─── sheetName 分发（纯函数，见 composables/n2SheetRouting.ts）───────────────
// 🔴 原实现有两处缺陷，已随 spec n-cycle-tax-disclosure-alignment 修掉：
//   ① wp_code 正则跑在披露判定**之前**（D2 实测过这类抢占会让披露组件永远挂不上）
//   ② 国企判定写的是**繁体「國企」**，而真实 sheet 名是简体「附注披露信息（国企）」
//      → 国企披露 Tab 从来没渲染过，落到 OnlyOffice 兜底
const currentSheet = computed(() => normalizeN2SheetName(props.sheetName, props.wpCode))

/** skip sheet 列表（O1A原底稿/出口退税额复核示例走OO兜底，不做HTML组件化） */
const SKIP_SHEETS = ['O1A', '出口退税额复核示例']

/** N2-1~N2-11 + 底稿目录 + 两张披露表为 HTML 专属组件渲染；N2A/skip 走 OnlyOffice */
const isHtmlSheet = computed(() => {
  if (SKIP_SHEETS.some(sk => (props.sheetName || '').includes(sk))) return false
  return isN2HtmlSheet(currentSheet.value)
})

// ─── selfLoad（bundle内嵌场景 htmlData 为 null 时自加载） ─────────────────────
/**
 * 合并一个 responses 来源到目标 Map。
 * 后端 N2 render 策略实际输出键为 `responses_snapshot`（dict {item_id: {...}}）；
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
      _mergeResponses(map, sheet?.html_data?.responses_snapshot)
      _mergeResponses(map, sheet?.html_data?.checklist_responses)
      _mergeResponses(map, sheet?.html_data?.allResponses)
    }
    if (map.size > 0) allResponses.value = map
  } catch (e) {
    console.error('[N2] selfLoad failed:', e)
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
    // 从 htmlData 解析 responses（兼容 responses_snapshot / checklist_responses / allResponses）
    const map = new Map<string, any>()
    _mergeResponses(map, props.htmlData?.responses_snapshot)
    _mergeResponses(map, props.htmlData?.checklist_responses)
    _mergeResponses(map, props.htmlData?.allResponses)
    allResponses.value = map
  }
  isLoading.value = false

  // ─── EventBus 订阅 'disclosure:refresh' → 刷新数据（Task 6.1） ─────────
  eventBus.on('disclosure:refresh' as any, onDisclosureRefresh)
})

onBeforeUnmount(() => {
  // 清理 EventBus 监听
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
.n2-taxes-payable { padding: 12px; }
.loading-container { padding: 24px; }
.n2-taxes-payable-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
