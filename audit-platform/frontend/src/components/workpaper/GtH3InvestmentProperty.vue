<template>
  <div class="h3-investment-property">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 顶部工具栏（双模式切换+计量模式切换）— 目录页隐藏 -->
      <div v-if="currentSheet !== 'H3'" class="h3-header-toolbar">
        <el-segmented
          :model-value="currentMode"
          :options="modeOptions"
          size="small"
          :disabled="!isOoAvailable && currentMode === 'html'"
          @change="onModeChange"
        />
        <!-- 计量模式切换 -->
        <el-segmented
          v-if="currentMode === 'html'"
          v-model="measurementModel"
          :options="measurementOptions"
          size="small"
          style="margin-left: 16px"
          @change="(val: string | number) => switchModel(val as 'cost' | 'fair_value')"
        />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-h3-investment-property" />
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
        <H3TabIndex
          v-if="currentSheet === 'H3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
          :is-readonly="isReadonly"
        />

        <!-- H3A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'H3A'"
          sheet-code="H3A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- H3-1 审定表（双计量模式）
             🔴 必须传 `:html-data` —— 两个审定表要读 `tb_source_codes` 渲染四表取数
             溯源面板（漏传 = 面板静默不渲染，四层验证全查不出）。 -->
        <template v-else-if="currentSheet === 'H3-1'">
          <H3TabAdjudicationCost
            v-if="measurementModel === 'cost'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :html-data="props.htmlData"
            :is-readonly="isReadonly"
          />
          <H3TabAdjudicationFair
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :html-data="props.htmlData"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H3-2 明细表（双计量模式） -->
        <template v-else-if="currentSheet === 'H3-2'">
          <H3TabDetailCost
            v-if="measurementModel === 'cost'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
          <H3TabDetailFair
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H3-3 调整分录 -->
        <H3TabAdjustment
          v-else-if="currentSheet === 'H3-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H3-4 会计政策检查表 -->
        <H3TabPolicyCheck
          v-else-if="currentSheet === 'H3-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
          :is-readonly="isReadonly"
        />

        <!-- H3-5 增减检查表（双计量模式，统一组件） -->
        <H3TabAdditionCheck
          v-else-if="currentSheet === 'H3-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
          :is-readonly="isReadonly"
          :year="props.year"
          :html-data="props.htmlData"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H3-6 互转审核表 -->
        <H3TabTransferReview
          v-else-if="currentSheet === 'H3-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
          :is-readonly="isReadonly"
        />

        <!-- H3-7 折旧测算表（仅成本模式，含分支选择器） -->
        <template v-else-if="currentSheet === 'H3-7'">
          <div v-if="measurementModel === 'fair_value'" class="h3-mode-hint">
            <el-alert type="info" :closable="false" show-icon>
              公允价值模式下不计提折旧，此表仅适用于成本模式。
            </el-alert>
          </div>
          <template v-else>
            <div class="dep-branch-selector" style="margin-bottom:12px;padding:0 16px">
              <el-segmented
                v-model="depreciationBranch"
                :options="[{label:'不含减值',value:'noImpair'},{label:'含减值',value:'withImpair'}]"
                size="small"
              />
            </div>
            <H3TabDepreciationNoImpair
              v-if="depreciationBranch === 'noImpair'"
              :wp-id="props.wpId"
              :project-id="props.projectId"
              :all-responses="allResponses"
              :is-readonly="isReadonly"
              :audit-year="props.year"
            />
            <H3TabDepreciationWithImpair
              v-else
              :wp-id="props.wpId"
              :project-id="props.projectId"
              :all-responses="allResponses"
              :is-readonly="isReadonly"
              :audit-year="props.year"
            />
          </template>
        </template>

        <!-- H3-8 公允价值复核表 -->
        <H3TabFairValueReview
          v-else-if="currentSheet === 'H3-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
          :is-readonly="isReadonly"
        />

        <!-- H3-9 盘点检查表 -->
        <H3TabStocktakeCheck
          v-else-if="currentSheet === 'H3-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H3-10 减值测算表（仅成本模式） -->
        <template v-else-if="currentSheet === 'H3-10'">
          <div v-if="measurementModel === 'fair_value'" class="h3-mode-hint">
            <el-alert type="info" :closable="false" show-icon>
              公允价值模式下不计提减值，此表仅适用于成本模式。
            </el-alert>
          </div>
          <H3TabImpairment
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H3-11 可收回金额测试表（仅成本模式） -->
        <template v-else-if="currentSheet === 'H3-11'">
          <div v-if="measurementModel === 'fair_value'" class="h3-mode-hint">
            <el-alert type="info" :closable="false" show-icon>
              公允价值模式下不适用可收回金额测试，此表仅适用于成本模式。
            </el-alert>
          </div>
          <H3TabRecoverable
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          />
        </template>

        <!-- H3-12 产权核对表 -->
        <H3TabTitleCheck
          v-else-if="currentSheet === 'H3-12'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
          :html-data="effectiveHtmlData"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H3-13 关联交易检查表 -->
        <H3TabRelatedParty
          v-else-if="currentSheet === 'H3-13'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H3-14 租金收入测算表 -->
        <H3TabRentalIncome
          v-else-if="currentSheet === 'H3-14'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
          :html-data="props.htmlData"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（上市） -->
        <H3TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（国企） -->
        <H3TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
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

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtH3InvestmentProperty.vue — H3 投资性房地产底稿主入口
 *
 * sheetName prop v-if 分发到全部20个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * measurementModel: 双计量模式(成本/公允价值)控制 H3-1/H3-2/H3-5/H3-7 的双版本显隐。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * useVersionTrail: autoSnapshot on save。
 * useH3DualMode: HTML↔OnlyOffice切换+OO健康检查。
 * useH3FormData: allResponses + save + TB取数。
 * useH3MeasurementModel: 计量模式持久化。
 *
 * Spec: .kiro/specs/h3-investment-property/ Task 6.1
 * Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9, 1.11, 16.1-16.2, 16.8, 16.10
 */
import { ref, computed, onMounted, onUnmounted, provide, toRef, inject, defineAsyncComponent, watch } from 'vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useH3DualMode } from './composables/useH3DualMode'
import { useH3FormData } from './composables/useH3FormData'
import { useH3MeasurementModel } from './composables/useH3MeasurementModel'
import { createH3RowNavigation, H3RowNavigationKey } from './composables/useH3RowNavigation'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
// 版本 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载

// core — H3TabIndex 非 lazy（底稿目录轻量，首屏必显）— 骨架阶段先 lazy
const H3TabIndex = defineAsyncComponent(() => import('./h3/core/H3TabIndex.vue'))
const H3TabAdjudicationCost = defineAsyncComponent(() => import('./h3/core/H3TabAdjudicationCost.vue'))
const H3TabAdjudicationFair = defineAsyncComponent(() => import('./h3/core/H3TabAdjudicationFair.vue'))
const H3TabDetailCost = defineAsyncComponent(() => import('./h3/core/H3TabDetailCost.vue'))
const H3TabDetailFair = defineAsyncComponent(() => import('./h3/core/H3TabDetailFair.vue'))
const H3TabAdjustment = defineAsyncComponent(() => import('./h3/core/H3TabAdjustment.vue'))
const H3TabDisclosureListed = defineAsyncComponent(() => import('./h3/core/H3TabDisclosureListed.vue'))
const H3TabDisclosureSoe = defineAsyncComponent(() => import('./h3/core/H3TabDisclosureSoe.vue'))

// inspection
const H3TabPolicyCheck = defineAsyncComponent(() => import('./h3/inspection/H3TabPolicyCheck.vue'))
const H3TabAdditionCheck = defineAsyncComponent(() => import('./h3/inspection/H3TabAdditionCheck.vue'))
const H3TabTransferReview = defineAsyncComponent(() => import('./h3/inspection/H3TabTransferReview.vue'))
const H3TabStocktakeCheck = defineAsyncComponent(() => import('./h3/inspection/H3TabStocktakeCheck.vue'))
const H3TabTitleCheck = defineAsyncComponent(() => import('./h3/inspection/H3TabTitleCheck.vue'))
const H3TabRelatedParty = defineAsyncComponent(() => import('./h3/inspection/H3TabRelatedParty.vue'))

// depreciation
const H3TabDepreciationNoImpair = defineAsyncComponent(() => import('./h3/depreciation/H3TabDepreciationNoImpair.vue'))
const H3TabDepreciationWithImpair = defineAsyncComponent(() => import('./h3/depreciation/H3TabDepreciationWithImpair.vue'))

// impairment
const H3TabImpairment = defineAsyncComponent(() => import('./h3/impairment/H3TabImpairment.vue'))
const H3TabRecoverable = defineAsyncComponent(() => import('./h3/impairment/H3TabRecoverable.vue'))

// fairvalue
const H3TabFairValueReview = defineAsyncComponent(() => import('./h3/fairvalue/H3TabFairValueReview.vue'))

// rental
const H3TabRentalIncome = defineAsyncComponent(() => import('./h3/rental/H3TabRentalIncome.vue'))

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
/** selfLoad 时缓存 project_context（htmlData 未透传时供子表使用） */
const selfLoadedProjectContext = ref<Record<string, unknown> | null>(null)

const effectiveHtmlData = computed(() => {
  if (props.htmlData) return props.htmlData
  if (selfLoadedProjectContext.value) {
    return { project_context: selfLoadedProjectContext.value }
  }
  return undefined
})

/** 折旧分支选择器（仅成本模式 H3-7） */
const depreciationBranch = ref<'noImpair' | 'withImpair'>('noImpair')

// ─── useH3DualMode — HTML↔OO 切换 ──────────────────────────────────────────
const {
  currentMode,
  isOoAvailable,
  modeOptions,
  onModeChange,
} = useH3DualMode({
  wpId: toRef(props, 'wpId') as any,
  sheetName: toRef(props, 'sheetName') as any,
  autoSave: async () => {
    // flush all pending debounced saves before switching mode
    await formData.saveBatch([])
  },
  reloadAll: async () => { await selfLoad() },
})

// ─── useH3FormData — 数据加载/保存 ────────────────────────────────────────────
const formData = useH3FormData({
  wpId: toRef(props, 'wpId') as any,
  projectId: toRef(props, 'projectId') as any,
  measurementModel: ref('cost') as any, // will be synced below
})

// ─── useH3MeasurementModel — 计量模式切换+持久化 ─────────────────────────────
const {
  measurementModel,
  switchModel,
  isSheetVisible,
} = useH3MeasurementModel({
  getValue: formData.getValue,
  saveImmediate: formData.saveImmediate,
})

const measurementOptions = [
  { label: '成本模式', value: 'cost' },
  { label: '公允价值模式', value: 'fair_value' },
]

/** 从 sheetName 提取编码 (H3/H3A/H3-1~H3-14/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国企|附注.*国有/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') || name.includes('国有') ? '附注国企' : '附注上市'
  // 程序表
  if (/H3A/.test(name)) return 'H3A'
  // H3-N 编码（H3-1 到 H3-14）— 先匹配两位数再匹配一位数
  const m = name.match(/(H3-\d+)/)
  if (m) return m[1]
  // 底稿目录 H3（无后缀）
  if (/底稿目录/.test(name) || (/\bH3\b/.test(name) && !/H3-/.test(name) && !/H3A/.test(name))) return 'H3'
  return ''
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
      // 兼容两种键名：allResponses（历史）/ responses_snapshot（H3 render 策略实际输出）
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.responses_snapshot)
      if (map.size > 0) allResponses.value = map
      // 恢复 measurement_model 状态
      if (props.htmlData.measurement_model) {
        measurementModel.value = props.htmlData.measurement_model
      }
      if (props.htmlData.project_context) {
        selfLoadedProjectContext.value = props.htmlData.project_context
      }
    } else {
      // selfLoad: 自行调用 render-config
      const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'h3-investment-property' },
        _silent: true,
      } as any)
      const data = res.data?.data || res.data
      if (data?.project_context) {
        selfLoadedProjectContext.value = data.project_context
      }
      if (data?.sheets && Array.isArray(data.sheets)) {
        const map = new Map<string, any>()
        for (const sheet of data.sheets) {
          _mergeResponses(map, sheet.html_data?.allResponses)
          _mergeResponses(map, sheet.html_data?.responses_snapshot)
          // 从 render-config 恢复 measurement_model
          if (sheet.html_data?.measurement_model) {
            measurementModel.value = sheet.html_data.measurement_model
          }
        }
        allResponses.value = map
      }
    }
  } catch (err) {
    console.warn('[GtH3InvestmentProperty] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── provide for child components ────────────────────────────────────────────
// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide，子组件 inject 命中祖先
provide('measurementModel', measurementModel)
provide('allResponses', allResponses)

// 复核圆点：GtReviewTrigger 依赖 getThreadDot/getRowDot 才渲染蓝/红点
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
const { getThreadDot: h3GetThreadDot, getRowDot: h3GetRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', h3GetThreadDot)
provide('getRowDot', h3GetRowDot)

const h3RowNav = createH3RowNavigation((sheetName) => emit('navigate-sheet', sheetName))
provide(H3RowNavigationKey, h3RowNav)

// ─── 版本追踪 useWorkpaperVersionToolbar (autoSnapshot on save) ──────────────
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('h3VersionTrailRef', versionTrailRef)
provide('h3OpenVersionHistory', openVersionHistory)

// ─── Watch: measurementModel 切换时 autoSnapshot ──────────────────────────────
watch(measurementModel, () => {
  scheduleAutoSnapshot()
})

// ─── Lifecycle ───────────────────────────────────────────────────────────────
// 审定数变更 / TB 更新 → 刷新 allResponses（各子 tab 含附注据此重算跨 sheet 取数）。
// 经 crossWpEventBridge 统一 window/eventBus 传输（P1 — 修 H3 附注刷新 double no-op）。
let _refreshTimer: ReturnType<typeof setTimeout> | null = null
function _handleAdjudicatedRefresh(): void {
  if (_refreshTimer) clearTimeout(_refreshTimer)
  _refreshTimer = setTimeout(() => { void selfLoad() }, 400)
}

onMounted(() => {
  void selfLoad()
  eventBus.on('substantive:adjudicated', _handleAdjudicatedRefresh)
  eventBus.on('trial-balance:updated', _handleAdjudicatedRefresh)
})

onUnmounted(() => {
  if (_refreshTimer) clearTimeout(_refreshTimer)
  eventBus.off('substantive:adjudicated', _handleAdjudicatedRefresh)
  eventBus.off('trial-balance:updated', _handleAdjudicatedRefresh)
})
</script>

<style scoped>
.h3-investment-property {
  width: 100%;
  min-height: 400px;
}

.loading-container {
  padding: 24px;
}

.h3-header-toolbar {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
}

.h3-mode-hint {
  padding: 24px 16px;
}

.dep-branch-selector {
  padding: 0 16px;
}
</style>
