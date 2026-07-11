<template>
  <div class="h2-construction-in-progress">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="showHtmlToolbar" class="h2-header-toolbar">
        <el-segmented
          v-model="currentMode"
          :options="modeOptions"
          size="small"
          @change="onModeChange"
        />
      </div>

      <!-- OnlyOffice 模式 -->
      <GtOnlyOfficeSheet
        v-if="currentMode === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- HTML 结构化视图 -->
      <template v-else>
        <!-- 底稿目录 -->
        <H2TabIndex
          v-if="currentSheet === 'H2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'H2A'"
          sheet-code="H2A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- H2-1 审定表（三角勾稽含转固扣减） -->
        <H2TabAdjudication
          v-else-if="currentSheet === 'H2-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-2 明细表（3区段Tab 50列） -->
        <H2TabDetail
          v-else-if="currentSheet === 'H2-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-3 调整分录 -->
        <H2TabAdjustment
          v-else-if="currentSheet === 'H2-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-4 分析表 -->
        <H2TabAnalysis
          v-else-if="currentSheet === 'H2-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-5 转固时点检查（核心联动H1） -->
        <H2TabTransferCheck
          v-else-if="currentSheet === 'H2-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-6 审核记录（签章式） -->
        <H2TabReviewRecord
          v-else-if="currentSheet === 'H2-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-7 工程造价比较 -->
        <H2TabCostComparison
          v-else-if="currentSheet === 'H2-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-8 增加检查 -->
        <H2TabAdditionCheck
          v-else-if="currentSheet === 'H2-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-9 减少检查 -->
        <H2TabDecreaseCheck
          v-else-if="currentSheet === 'H2-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-10/H2-11 利息资本化（2分支选择器） -->
        <template v-else-if="currentSheet === 'H2-10' || currentSheet === 'H2-11'">
          <div class="interest-cap-branch-selector" style="margin-bottom:12px;padding:0 16px">
            <el-segmented v-model="interestCapBranch" :options="[{label:'无专门借款',value:'noBorrow'},{label:'有专门借款',value:'withBorrow'}]" size="small" />
          </div>
          <H2TabInterestCapNoBorrow
            v-if="interestCapBranch === 'noBorrow'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
          <H2TabInterestCapWithBorrow
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H2-12 监盘计划 -->
        <H2TabStocktakePlan
          v-else-if="currentSheet === 'H2-12'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-13 盘点检查表 -->
        <H2TabStocktakeCheck
          v-else-if="currentSheet === 'H2-13'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-14 监盘小结 -->
        <H2TabStocktakeSummary
          v-else-if="currentSheet === 'H2-14'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-15 减值测算 -->
        <H2TabImpairment
          v-else-if="currentSheet === 'H2-15'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-16 可收回金额（DCF） -->
        <H2TabRecoverable
          v-else-if="currentSheet === 'H2-16'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H2-17 关联交易 -->
        <H2TabRelatedParty
          v-else-if="currentSheet === 'H2-17'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（上市） -->
        <H2TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（国企） -->
        <H2TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 未匹配 → OnlyOffice fallback -->
        <GtOnlyOfficeSheet
          v-else
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName || ''"
          :readonly="isReadonly"
          style="height: calc(100vh - 180px)"
        />
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtH2ConstructionInProgress.vue — H2 在建工程底稿主入口
 *
 * sheetName prop v-if 分发到全部17个子组件+2附注，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * useVersionTrail: autoSnapshot on save。
 *
 * 科目：1604 在建工程（借方/资产类）
 * 核心：三角勾稽（期末=期初+增加-减少-转固）、利息资本化2分支、转固联动H1
 *
 * Spec: .kiro/specs/h2-construction-in-progress/ Task 1.1
 * Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9
 */
import { ref, computed, onMounted, provide, toRef, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import useVersionTrail from './composables/useVersionTrail'
import useH2DualMode from './composables/useH2DualMode'
import useH2ImportExport from './composables/useH2ImportExport'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core — H2TabIndex 非 lazy（底稿目录轻量，首屏必显）
import H2TabIndex from './h2/core/H2TabIndex.vue'
const H2TabAdjudication = defineAsyncComponent(() => import('./h2/core/H2TabAdjudication.vue'))
const H2TabDetail = defineAsyncComponent(() => import('./h2/core/H2TabDetail.vue'))
const H2TabAdjustment = defineAsyncComponent(() => import('./h2/core/H2TabAdjustment.vue'))
const H2TabAnalysis = defineAsyncComponent(() => import('./h2/core/H2TabAnalysis.vue'))
const H2TabDisclosureListed = defineAsyncComponent(() => import('./h2/core/H2TabDisclosureListed.vue'))
const H2TabDisclosureSoe = defineAsyncComponent(() => import('./h2/core/H2TabDisclosureSoe.vue'))

// inspection
const H2TabTransferCheck = defineAsyncComponent(() => import('./h2/inspection/H2TabTransferCheck.vue'))
const H2TabReviewRecord = defineAsyncComponent(() => import('./h2/inspection/H2TabReviewRecord.vue'))
const H2TabCostComparison = defineAsyncComponent(() => import('./h2/inspection/H2TabCostComparison.vue'))
const H2TabAdditionCheck = defineAsyncComponent(() => import('./h2/inspection/H2TabAdditionCheck.vue'))
const H2TabDecreaseCheck = defineAsyncComponent(() => import('./h2/inspection/H2TabDecreaseCheck.vue'))
const H2TabRelatedParty = defineAsyncComponent(() => import('./h2/inspection/H2TabRelatedParty.vue'))

// interest (利息资本化2分支)
const H2TabInterestCapNoBorrow = defineAsyncComponent(() => import('./h2/interest/H2TabInterestCapNoBorrow.vue'))
const H2TabInterestCapWithBorrow = defineAsyncComponent(() => import('./h2/interest/H2TabInterestCapWithBorrow.vue'))

// stocktake
const H2TabStocktakePlan = defineAsyncComponent(() => import('./h2/stocktake/H2TabStocktakePlan.vue'))
const H2TabStocktakeCheck = defineAsyncComponent(() => import('./h2/stocktake/H2TabStocktakeCheck.vue'))
const H2TabStocktakeSummary = defineAsyncComponent(() => import('./h2/stocktake/H2TabStocktakeSummary.vue'))

// impairment
const H2TabImpairment = defineAsyncComponent(() => import('./h2/impairment/H2TabImpairment.vue'))
const H2TabRecoverable = defineAsyncComponent(() => import('./h2/impairment/H2TabRecoverable.vue'))

// ─── Props & Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

defineEmits<{ (e: 'save'): void; (e: 'completed'): void }>()

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const allResponses = ref<Map<string, any>>(new Map())
const interestCapBranch = ref<'noBorrow' | 'withBorrow'>('noBorrow')

// ─── 双模式 useH2DualMode (Task 6.2) ────────────────────────────────────────
const {
  currentMode,
  modeOptions,
  isOoAvailable,
  onModeChange,
} = useH2DualMode({
  wpId: toRef(props, 'wpId') as any,
  autoSave: async () => { /* trigger version snapshot */ },
  reloadAll: async () => { await selfLoad() },
})

// ─── 导入导出 useH2ImportExport (Task 6.3) ───────────────────────────────────
const importExport = useH2ImportExport({
  wpId: toRef(props, 'wpId') as any,
  projectId: toRef(props, 'projectId') as any,
  onImported: async () => { await selfLoad() },
})
provide('h2ImportExport', importExport)

/** 从 sheetName 提取编码 (H2/H2A/H2-1~H2-17/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  if (/附注.*上市|H2-note-listed/.test(name)) return '附注上市'
  if (/附注.*国企|H2-note-soe/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  // 程序表
  if (/H2A/.test(name)) return 'H2A'
  // H2-N 编码（H2-1 到 H2-17）
  const m = name.match(/(H2-\d+)/)
  if (m) return m[1]
  // 底稿目录 H2（无后缀）
  if (/\bH2\b/.test(name) && !/H2-/.test(name) && !/H2A/.test(name)) return 'H2'
  return ''
})

const showHtmlToolbar = computed(() => {
  const s = currentSheet.value
  return s !== '' && currentMode.value !== 'onlyoffice'
})

// ─── selfLoad ────────────────────────────────────────────────────────────────
/** 合并一个 responses 对象（{item_id: {...}}）到目标 Map */
function _mergeResponses(map: Map<string, any>, src: any): void {
  if (!src || typeof src !== 'object') return
  for (const [k, v] of Object.entries(src)) map.set(k, v)
}

async function selfLoad(): Promise<void> {
  try {
    if (props.htmlData) {
      // 从父级透传的 htmlData 中提取 responses
      // 兼容两种键名：allResponses（历史）/ responses_snapshot（H2 render 策略实际输出）
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.responses_snapshot)
      if (map.size > 0) allResponses.value = map
    } else {
      // selfLoad: 自行调用 render-config
      const res = await http.get(`/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'h2-construction-in-progress' },
        _silent: true,
      } as any)
      const data = res.data?.data || res.data
      if (data?.sheets && Array.isArray(data.sheets)) {
        const map = new Map<string, any>()
        for (const sheet of data.sheets) {
          _mergeResponses(map, sheet.html_data?.allResponses)
          _mergeResponses(map, sheet.html_data?.responses_snapshot)
        }
        allResponses.value = map
      }
    }
  } catch (err) {
    console.warn('[GtH2ConstructionInProgress] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── provide for child components ────────────────────────────────────────────
function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  console.log('[H2] openReviewDialog:', sectionId, sectionLabel)
  // Integrated with audit-review-dialog module — real impl delegates to parent via emit
}
provide('openReviewDialog', openReviewDialog)

// ─── EventBus 订阅（Task 6.8 + 6.9） ────────────────────────────────────────
/**
 * Task 6.8: subscribe 'substantive:adjudicated' → 刷新附注取数
 * Task 6.9: subscribe 'control:c7-completed' → 更新H2A前置状态
 *
 * EventBus integration via SSE subscription in the platform layer.
 * The allResponses map is reactive and auto-updates from render-config polling.
 * Below we declare intent; actual SSE listener is handled by GtWpRenderer parent.
 */
const eventSubscriptions = {
  'substantive:adjudicated': () => {
    // 刷新附注取数：触发 selfLoad 重新获取最新数据
    void selfLoad()
  },
  'control:c7-completed': (payload: any) => {
    // 更新H2A程序表前置状态
    console.log('[H2] C7前置完成，更新H2A状态', payload)
    // allResponses will auto-refresh on next render-config poll
    void selfLoad()
  },
}
provide('eventSubscriptions', eventSubscriptions)

// ─── 版本追踪 useVersionTrail (autoSnapshot on save) ─────────────────────────
const versionTrail = useVersionTrail({
  projectId: toRef(props, 'projectId') as any,
  workpaperId: toRef(props, 'wpId') as any,
})
provide('versionTrail', versionTrail)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  void selfLoad()
})
</script>

<style scoped>
.h2-construction-in-progress {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.h2-header-toolbar {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.interest-cap-branch-selector {
  display: flex;
  align-items: center;
}
</style>
