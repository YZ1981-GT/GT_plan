<template>
  <div class="n5-income-tax-expense">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'N5' && currentSheet !== '底稿目录'" class="n5-income-tax-expense-toolbar">
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

      <!-- N5A 程序表 → OnlyOffice fallback -->
      <GtOnlyOfficeSheet
        v-else-if="currentSheet === 'N5A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- N3A 原底稿 → skip，走 OnlyOffice fallback -->
      <GtOnlyOfficeSheet
        v-else-if="currentSheet === 'N3A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 底稿目录 -->
      <N5TabIndex
        v-else-if="currentSheet === 'N5' || currentSheet === '底稿目录'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N5-1 审定表（损益类，36公式，当期+递延） -->
      <N5TabAdjudication
        v-else-if="currentSheet === 'N5-1'"
        :all-responses="allResponsesRef"
        :wp-id="wpIdRef"
        :project-id="projectIdRef"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N5-2 明细表（38×10，8公式） -->
      <N5TabDetail
        v-else-if="currentSheet === 'N5-2'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N5-3 调整分录 -->
      <N5TabAdjustment
        v-else-if="currentSheet === 'N5-3'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N5-4 当期所得税费用计算表（82×7，核心） -->
      <N5TabCurrentTaxCalc
        v-else-if="currentSheet === 'N5-4'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N5-5 纳税调整明细表（107×8，虚拟滚动） -->
      <N5TabTaxAdjustment
        v-else-if="currentSheet === 'N5-5'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N5-6 税收优惠明细表（54×6，10公式） -->
      <N5TabTaxBenefit
        v-else-if="currentSheet === 'N5-6'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N5-6-1 加计扣除研发费用情况明细表（43×7，17公式） -->
      <N5TabRdSuperDeduction
        v-else-if="currentSheet === 'N5-6-1'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N5-6-2 高新技术企业认定条件检查表（18×13） -->
      <N5TabHighTechCheck
        v-else-if="currentSheet === 'N5-6-2'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N5-7 财产损失明细表（15×7，12公式） -->
      <N5TabPropertyLoss
        v-else-if="currentSheet === 'N5-7'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- N5-8 递延所得税费用核对表（44×10，12公式） -->
      <N5TabDeferredReconcile
        v-else-if="currentSheet === 'N5-8'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- 附注（上市） -->
      <N5TabDisclosureListed
        v-else-if="currentSheet === '附注(上市)' || currentSheet === '附注（上市）'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
        @navigate-sheet="handleNavigate"
      />

      <!-- 附注（国企） -->
      <N5TabDisclosureSoe
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
 * GtN5IncomeTaxExpense.vue — N5 所得税费用底稿主入口
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 1.1
 * 科目: 6801所得税费用（损益类/借方）
 * 取数规则: 本期发生额（从tb_ledger），与N4/H10/I6/L8同款
 * sheetName 分发到 N5 专属子组件（N5-1~N5-8/N5-6-1/N5-6-2），N5A/N3A走 OnlyOffice 兜底
 * 集成：useWorkpaperVersionToolbar(autoSnapshot on save) + provide('openReviewDialog')
 * EventBus：substantive:adjudicated(6801) / income-tax:updated → A类利润表
 *
 * Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 1.8, 1.9, 1.11
 */
import { ref, computed, inject, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import { WorkpaperRuntimeContextKey, type WorkpaperRuntimeContext } from './composables/useWorkpaperScaffold'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
// ─── defineAsyncComponent lazy 加载子组件 ────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core/
const N5TabIndex = defineAsyncComponent(() => import('./n5/core/N5TabIndex.vue'))
const N5TabAdjudication = defineAsyncComponent(() => import('./n5/core/N5TabAdjudication.vue'))
const N5TabDetail = defineAsyncComponent(() => import('./n5/core/N5TabDetail.vue'))
const N5TabAdjustment = defineAsyncComponent(() => import('./n5/core/N5TabAdjustment.vue'))
const N5TabDisclosureListed = defineAsyncComponent(() => import('./n5/core/N5TabDisclosureListed.vue'))
const N5TabDisclosureSoe = defineAsyncComponent(() => import('./n5/core/N5TabDisclosureSoe.vue'))

// calc/
const N5TabCurrentTaxCalc = defineAsyncComponent(() => import('./n5/calc/N5TabCurrentTaxCalc.vue'))
const N5TabTaxAdjustment = defineAsyncComponent(() => import('./n5/calc/N5TabTaxAdjustment.vue'))
const N5TabDeferredReconcile = defineAsyncComponent(() => import('./n5/calc/N5TabDeferredReconcile.vue'))

// benefit/
const N5TabTaxBenefit = defineAsyncComponent(() => import('./n5/benefit/N5TabTaxBenefit.vue'))
const N5TabRdSuperDeduction = defineAsyncComponent(() => import('./n5/benefit/N5TabRdSuperDeduction.vue'))
const N5TabHighTechCheck = defineAsyncComponent(() => import('./n5/benefit/N5TabHighTechCheck.vue'))
const N5TabPropertyLoss = defineAsyncComponent(() => import('./n5/benefit/N5TabPropertyLoss.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
  year?: number
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

/**
 * 子组件目录行/返回按钮 emit navigate/navigate-sheet → 转发为 navigate-sheet 给外层 GtWpRenderer。
 * 铁律：GtWpRenderer 监听 @navigate-sheet，主入口必须 emit 'navigate-sheet'。
 * 已知遗留修复：N5TabIndex emit('navigate') 但父组件此前未绑 @navigate → 点击目录无法切 sheet。
 */
function handleNavigate(sheetName: string): void {
  emit('navigate-sheet', sheetName)
}

// ─── 状态 ────────────────────────────────────────────────────────────────────
const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const yearRef = computed(() => props.year || new Date().getFullYear())
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
  // 匹配 N5A, N3A, N5-6-1, N5-6-2, N5-1~N5-8, N5, 底稿目录, 附注 等
  const m = name.match(/(N5A|N3A|N5-6-[12]|N5-[1-8]|N5)/)
  if (m) return m[1]
  // 附注匹配
  if (name.includes('附注') && (name.includes('上市') || name.includes('国企'))) {
    return name.includes('上市') ? '附注(上市)' : '附注(国企)'
  }
  if (name.includes('底稿目录')) return '底稿目录'
  return name
})

/** skip sheet 列表（N3A原底稿标记skip走OO兜底） */
const SKIP_SHEETS = ['N3A']

/** HTML 专属组件渲染的 sheet（支持双模式切换）；N5A/N3A走 OnlyOffice */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  if (SKIP_SHEETS.some(sk => (props.sheetName || '').includes(sk))) return false
  if (s === 'N5A' || s === 'N3A') return false
  return /^N5-\d+(-\d+)?$/.test(s) || s === 'N5' || s === '底稿目录'
    || s.includes('附注')
})

// ─── selfLoad（bundle内嵌场景 htmlData 为 null 时自加载） ─────────────────────
/**
 * 合并一个 responses 来源到目标 Map。
 * 后端 N5 render 策略实际输出键为 `responses_snapshot`（dict {item_id: {...}}）；
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
    // 提取审定表预填
    for (const sheet of sheets) {
      if (sheet?.html_data?.adjudication_prefill && !adjudicationPrefill.value) {
        adjudicationPrefill.value = sheet.html_data.adjudication_prefill
      }
    }
  } catch (e) {
    console.error('[N5] selfLoad failed:', e)
  }
}

provide('reloadWorkpaperData', selfLoad)
provide('n5Year', yearRef)

// ─── 审定表预填 + 版本快照 ──────────────────────────────────────────────────
const adjudicationPrefill = ref<any>(null)
provide('n5AdjudicationPrefill', adjudicationPrefill)
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())
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

  // ─── EventBus 订阅 ─────────────────────────────────────────────────
  eventBus.on('disclosure:refresh' as any, onDisclosureRefresh)
  eventBus.on('deferred-tax:asset-updated', onDeferredTaxUpdate)
  eventBus.on('deferred-tax:liability-updated', onDeferredTaxUpdate)
})

onBeforeUnmount(() => {
  eventBus.off('disclosure:refresh' as any, onDisclosureRefresh)
  eventBus.off('deferred-tax:asset-updated', onDeferredTaxUpdate)
  eventBus.off('deferred-tax:liability-updated', onDeferredTaxUpdate)
})

// ─── EventBus handlers ──────────────────────────────────────────────────────
function onDisclosureRefresh(): void {
  selfLoad()
}

function onDeferredTaxUpdate(): void {
  // N1/N3递延税变动 → 刷新N5-8递延核对数据
  selfLoad()
}

// ─── 版本快照：子组件保存后触发自动快照（版本链能力来自 Runtime Boundary） ────
provide('scheduleAutoSnapshot', () => runtime?.version.scheduleAutoSnapshot())
</script>

<style scoped>
.n5-income-tax-expense { padding: 12px; }
.loading-container { padding: 24px; }
.n5-income-tax-expense-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
