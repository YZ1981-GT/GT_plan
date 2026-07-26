<template>
  <div class="h2-construction-in-progress">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 双模式切换器（OO 模式也需可见，否则无法切回结构化） -->
      <div v-if="showModeSwitch" class="h2-header-toolbar">
        <el-segmented
          :model-value="currentMode"
          :options="modeOptions"
          size="small"
          @change="onModeChange"
        />
        <span v-if="healthTag" class="h2-oo-tag" :class="`h2-oo-tag--${healthTag.type}`">
          {{ healthTag.text }}
        </span>
      </div>

      <!-- OnlyOffice 模式 -->
      <GtOnlyOfficeSheet
        v-if="currentMode === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
        @fallback="onOoLoadFailed"
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
        <template v-else-if="currentSheet === 'H2A'">
          <el-alert
            v-if="c7State.completed && c7State.needsExtended"
            type="error"
            :closable="false"
            show-icon
            class="c7-prereq-alert"
            title="C7 控制测试结论为失效/存在无效控制点：请扩大实质性程序样本量，并在 H2A 程序表记录应对。"
            :description="c7AlertDesc"
          />
          <el-alert
            v-else-if="c7State.completed"
            type="success"
            :closable="false"
            show-icon
            class="c7-prereq-alert"
            :title="`C7 控制测试前置已完成（结论：${c7State.conclusion || '已记录'}）`"
          />
          <el-alert
            v-else
            type="warning"
            :closable="false"
            show-icon
            class="c7-prereq-alert"
            title="C7 在建工程循环控制测试尚未完成：完成 C7 后将自动回写本程序表前置状态。"
          />
          <CycleTabProcedure
            sheet-code="H2A"
            :html-data="props.htmlData"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H2-1 审定表（三角勾稽含转固扣减） -->
        <H2TabAdjudication
          v-else-if="currentSheet === 'H2-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :html-data="props.htmlData"
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
          :year="props.year"
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
          :year="props.year"
        />

        <!-- H2-6 审核记录（按工程核查 + 弹窗填报） -->
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
          :year="props.year"
        />

        <!-- H2-9 减少检查 -->
        <H2TabDecreaseCheck
          v-else-if="currentSheet === 'H2-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
        />

        <!-- H2-10/H2-11 利息资本化（互斥分支：随 sheet 锁定，切换即导航） -->
        <template v-else-if="currentSheet === 'H2-10' || currentSheet === 'H2-11'">
          <div class="interest-cap-branch-selector">
            <el-segmented
              :model-value="currentSheet === 'H2-11' ? 'withBorrow' : 'noBorrow'"
              :options="[
                { label: '无专门借款 (H2-10)', value: 'noBorrow' },
                { label: '有专门借款 (H2-11)', value: 'withBorrow' },
              ]"
              size="small"
              @change="onInterestCapBranchChange"
            />
            <span class="branch-hint">二者互斥，按是否存在专门借款择一编制</span>
          </div>
          <H2TabInterestCapNoBorrow
            v-if="currentSheet === 'H2-10'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          />
          <H2TabInterestCapWithBorrow
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          />
        </template>

        <!-- H2-12 监盘计划 -->
        <H2TabStocktakePlan
          v-else-if="currentSheet === 'H2-12'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H2-13 盘点检查表 -->
        <H2TabStocktakeCheck
          v-else-if="currentSheet === 'H2-13'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H2-14 监盘小结 -->
        <H2TabStocktakeSummary
          v-else-if="currentSheet === 'H2-14'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
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
          v-else-if="currentSheet === '附注上市' && disclosureStd.showListed.value"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />
        <el-empty
          v-else-if="currentSheet === '附注上市' && !disclosureStd.showListed.value"
          description="本项目适用准则不含上市公司附注版（applicable_standards）"
        />

        <!-- 附注披露（国企） -->
        <H2TabDisclosureSoe
          v-else-if="currentSheet === '附注国企' && disclosureStd.showSoe.value"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />
        <el-empty
          v-else-if="currentSheet === '附注国企' && !disclosureStd.showSoe.value"
          description="本项目适用准则不含国有企业附注版（applicable_standards）"
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

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
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
import { ref, computed, onMounted, provide, toRef, inject, defineAsyncComponent, watch } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import useH2DualMode from './composables/useH2DualMode'
import useH2ImportExport from './composables/useH2ImportExport'
import { useH2C7Prerequisite } from './composables/useH2C7Prerequisite'
import { useH2ApplicableStandards } from './composables/useH2ApplicableStandards'
import {
  H2_INTEREST_BRANCH_KEY,
  inactiveInterestCapResultKey,
  type InterestCapBranch,
} from './composables/h2InterestCapBranch'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
// 版本 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载

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

const emit = defineEmits<{ (e: 'save'): void; (e: 'completed'): void; (e: 'navigate-sheet', sheetName: string): void }>()

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const allResponses = ref<Map<string, any>>(new Map())

function onInterestCapBranchChange(val: string | number | boolean) {
  const b: InterestCapBranch = val === 'withBorrow' ? 'withBorrow' : 'noBorrow'
  persistResponse(H2_INTEREST_BRANCH_KEY, b)
  persistResponse(inactiveInterestCapResultKey(b), null)
  if (b === 'withBorrow') {
    emit('navigate-sheet', 'H2-11 利息资本化有专门借款')
  } else {
    emit('navigate-sheet', 'H2-10 利息资本化无专门借款')
  }
}

// ─── 双模式 useH2DualMode (Task 6.2) ────────────────────────────────────────
const {
  currentMode,
  modeOptions,
  isOoAvailable,
  onModeChange: _rawH2ModeChange,
  healthTag,
  onOoLoadFailed,
} = useH2DualMode({
  wpId: toRef(props, 'wpId') as any,
  projectId: toRef(props, 'projectId') as any,
  sheetName: computed(() => props.sheetName || '') as any,
  autoSave: async () => { /* trigger version snapshot */ },
  reloadAll: async () => { await selfLoad() },
})

/** C1: 目录/程序表不支持在线编辑(仅阻止切 OO 方向) */
function onModeChange(val: string | number | boolean): void {
  if (val === 'onlyoffice') {
    const s = currentSheet.value
    if (s === 'H2' || s.endsWith('A')) {
      return
    }
  }
  _rawH2ModeChange(val)
}

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
  if (/底稿目录/.test(name) || (/\bH2\b/.test(name) && !/H2-/.test(name) && !/H2A/.test(name))) return 'H2'
  return ''
})

const showHtmlToolbar = computed(() => {
  const s = currentSheet.value
  return s !== '' && currentMode.value !== 'onlyoffice'
})

/** 双模式切换器是否可见（OO 模式也需要，否则无法切回结构化） */
const showModeSwitch = computed(() => {
  const s = currentSheet.value
  return s !== '' && s !== 'H2'
})

// ─── selfLoad ────────────────────────────────────────────────────────────────
/** 合并一个 responses 对象（{item_id: {...}}）到目标 Map */
function _mergeResponses(map: Map<string, any>, src: any): void {
  if (!src || typeof src !== 'object') return
  // 注入权威 item_id：dict 值缺 item_id 时以键补齐（否则保存 items 缺 item_id 触发 422）；v 自带 item_id 则以其为准
  for (const [k, v] of Object.entries(src)) map.set(k, (v && typeof v === 'object' && !Array.isArray(v)) ? { item_id: k, ...v } : { item_id: k, remark: v })
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
      const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
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

// ─── 子组件 save 持久化（Bug C 修复：子 tab 此前 composable 未接 onSave → 从不落库） ──
// 子组件契约：inject('saveResponse')(itemId, value)。value 为字符串或对象（对象序列化进 remark）。
// 防抖 800ms 批量 PUT /checklist-responses，并乐观更新本地 Map 供 selfLoad/跨表读取。
const _saveTimers = new Map<string, ReturnType<typeof setTimeout>>()
function persistResponse(
  itemId: string,
  value: any,
  opts?: { conclusion?: string | null },
): void {
  if (!itemId || !props.wpId) return
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  const updated = {
    ...existing,
    item_id: itemId,
    remark: strVal,
    conclusion: opts && 'conclusion' in opts ? (opts.conclusion ?? null) : existing.conclusion,
  }
  // 替换 Map 引用以触发依赖 allResponses 的 computed（目录完成度/C7 等）
  const next = new Map(allResponses.value)
  next.set(itemId, updated)
  allResponses.value = next
  if (isReadonly.value) return
  const prev = _saveTimers.get(itemId)
  if (prev) clearTimeout(prev)
  _saveTimers.set(itemId, setTimeout(() => {
    _saveTimers.delete(itemId)
    http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: updated.conclusion ?? null, remark: updated.remark ?? null }],
    }).then(() => { scheduleAutoSnapshot() })
      .catch((err: unknown) => console.warn('[GtH2] persistResponse failed:', itemId, err))
  }, 800))
}

// ─── provide for child components ────────────────────────────────────────────
// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide，子组件 inject 命中祖先
provide('allResponses', allResponses)
provide('saveResponse', persistResponse)

// 复核圆点：GtReviewTrigger 依赖 getThreadDot/getRowDot 才渲染蓝/红点
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
const { getThreadDot: h2GetThreadDot, getRowDot: h2GetRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', h2GetThreadDot)
provide('getRowDot', h2GetRowDot)

const disclosureStd = useH2ApplicableStandards({
  projectId: toRef(props, 'projectId'),
  allResponses,
  htmlData: toRef(props, 'htmlData'),
  onPersist: persistResponse,
})

watch(
  () => currentSheet.value,
  (sheet) => {
    if (!sheet) return
    const redirect = disclosureStd.redirectSheetName(sheet)
    if (redirect) emit('navigate-sheet', redirect)
  },
  { immediate: true },
)

// ─── C7 前置（真实落库，非 console.log） ────────────────────────────────────
const { state: c7State } = useH2C7Prerequisite({
  allResponses,
  onPersist: persistResponse,
  isReadonly,
})
const c7AlertDesc = computed(() => {
  const s = c7State.value
  const parts: string[] = []
  if (s.conclusion) parts.push(`循环结论：${s.conclusion}`)
  if (s.ineffectiveCount > 0) parts.push(`无效控制点 ${s.ineffectiveCount} 个`)
  if (s.maxDeviationRate > 0) parts.push(`最高偏差率 ${(s.maxDeviationRate * 100).toFixed(1)}%`)
  if (s.timestamp) parts.push(`记录于 ${s.timestamp}`)
  return parts.join('；') || undefined
})

// ─── EventBus 订阅（Task 6.8 + 6.9） ────────────────────────────────────────
/**
 * Task 6.8: subscribe 'substantive:adjudicated' → 刷新附注取数
 * Task 6.9: C7 由 useH2C7Prerequisite 直接监听 window 事件并落库 H2A-c7-prerequisite
 */
const eventSubscriptions = {
  'substantive:adjudicated': () => {
    void selfLoad()
  },
  'control:test-concluded': () => {
    // C7 状态由 useH2C7Prerequisite 写入；此处刷新附属数据
    void selfLoad()
  },
  'control:c7-completed': () => {
    void selfLoad()
  },
}
provide('eventSubscriptions', eventSubscriptions)
provide('h2C7Prerequisite', c7State)

// ─── 版本追踪 useWorkpaperVersionToolbar (autoSnapshot on save) ──────────────
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('h2VersionTrailRef', versionTrailRef)
provide('h2OpenVersionHistory', openVersionHistory)

// ─── Task 4.2: Persist_First 种子（从后端 detail_prefill 种子 H2-2 明细行） ─────
function _seedDetailFromPrefill(): void {
  const detailKey = 'H2-2-rows'
  const existing = allResponses.value.get(detailKey)
  const hasExisting = existing && (
    (typeof existing.remark === 'string' && existing.remark.trim() && existing.remark !== '[]')
    || (typeof existing.conclusion === 'string' && existing.conclusion.trim() && existing.conclusion !== '[]')
  )
  if (hasExisting) return // Persist_First: 已有手工数据不覆盖

  const prefill = props.htmlData?.detail_prefill
  if (!Array.isArray(prefill) || prefill.length === 0) return

  const seedRows = prefill.map((p: any, i: number) => ({
    rowId: `seed-${i}`,
    name: String(p.name || ''),
    cipBegin: Number(p.cipBegin) || 0,
    cipEnd: Number(p.cipEnd) || 0,
    category: String(p.category || '自动种子'),
  }))
  // 内存态写入 allResponses（不落库），composable 的 watch 会自动消费
  const next = new Map(allResponses.value)
  next.set(detailKey, { item_id: detailKey, remark: JSON.stringify(seedRows), conclusion: null })
  allResponses.value = next
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  void selfLoad().then(() => {
    disclosureStd.loadFromProject()
    // Task 4.2: Persist_First 种子 — 从后端 detail_prefill 种子 H2-2 明细行（仅空时）
    _seedDetailFromPrefill()
  })
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
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.h2-oo-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}
.h2-oo-tag--success { color: #67c23a; background: #f0f9eb; }
.h2-oo-tag--info { color: #909399; background: #f4f4f5; }
.h2-oo-tag--warning { color: #e6a23c; background: #fdf6ec; }
.interest-cap-branch-selector {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 0 16px;
  flex-wrap: wrap;
}
.interest-cap-branch-selector .branch-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.c7-prereq-alert {
  margin: 8px 12px 12px;
}
</style>
