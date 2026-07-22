<template>
  <div class="h5-oil-gas-assets">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 行业适用性守卫：非 oil_gas/mining 行业 -->
    <el-empty
      v-else-if="!isApplicable"
      description="本底稿仅适用于石油天然气/采矿行业项目"
      :image-size="120"
    />

    <template v-else>
      <div v-if="showHtmlToolbar" class="h5-header-toolbar">
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
        <!-- 底稿目录 H5 -->
        <H5TabIndex
          v-if="currentSheet === 'H5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'H5A'"
          sheet-code="H5A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- H5-1 审定表 -->
        <H5TabAdjudication
          v-else-if="currentSheet === 'H5-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-2 明细表 -->
        <H5TabDetail
          v-else-if="currentSheet === 'H5-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-3 调整分录 -->
        <H5TabAdjustment
          v-else-if="currentSheet === 'H5-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-4 闲置检查 -->
        <H5TabIdleCheck
          v-else-if="currentSheet === 'H5-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-5 会计政策（CAS27） -->
        <H5TabPolicyCheck
          v-else-if="currentSheet === 'H5-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-6 分析表 -->
        <H5TabAnalysis
          v-else-if="currentSheet === 'H5-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-7 增加检查 -->
        <H5TabAdditionCheck
          v-else-if="currentSheet === 'H5-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-8 减少检查 -->
        <H5TabDisposalCheck
          v-else-if="currentSheet === 'H5-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-9 监盘计划 -->
        <H5TabStocktakePlan
          v-else-if="currentSheet === 'H5-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-10 盘点检查 -->
        <H5TabStocktakeCheck
          v-else-if="currentSheet === 'H5-10'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H5-11 监盘小结 -->
        <H5TabStocktakeSummary
          v-else-if="currentSheet === 'H5-11'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-12 折耗测算（双分支：不含减值/含减值） -->
        <template v-else-if="currentSheet === 'H5-12'">
          <div class="depletion-branch-selector" style="margin-bottom:12px;padding:0 16px">
            <el-segmented
              v-model="depletionBranch"
              :options="[{label:'不含减值',value:'noImpair'},{label:'含减值',value:'withImpair'}]"
              size="small"
            />
          </div>
          <H5TabDepletionNoImpair
            v-if="depletionBranch === 'noImpair'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
          <H5TabDepletionWithImpair
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H5-13 折耗分配 -->
        <H5TabDepletionAlloc
          v-else-if="currentSheet === 'H5-13'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-14 减值测算 -->
        <H5TabImpairment
          v-else-if="currentSheet === 'H5-14'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-15 可收回金额 -->
        <H5TabRecoverable
          v-else-if="currentSheet === 'H5-15'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-16 权属检查（采矿权） -->
        <H5TabTitleCheck
          v-else-if="currentSheet === 'H5-16'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-17 关联交易 -->
        <H5TabRelatedParty
          v-else-if="currentSheet === 'H5-17'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-18 经营租出 -->
        <H5TabOperatingLease
          v-else-if="currentSheet === 'H5-18'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-19 融资租出 -->
        <H5TabFinanceLease
          v-else-if="currentSheet === 'H5-19'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（上市） -->
        <H5TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（国企） -->
        <H5TabDisclosureSoe
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

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtH5OilGasAssets.vue — H5 油气资产底稿主入口
 *
 * sheetName prop v-if 分发到全部21个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * 行业守卫: applicable_when industry IN ['oil_gas','mining']。
 * useVersionTrail: autoSnapshot on save。
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/ Task 1.1
 * Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9, 1.11
 */
import { ref, computed, onMounted, provide, toRef, inject, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
// 版本 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载

// core — H5TabIndex 非 lazy（底稿目录轻量，首屏必显）
import H5TabIndex from './h5/core/H5TabIndex.vue'
const H5TabAdjudication = defineAsyncComponent(() => import('./h5/core/H5TabAdjudication.vue'))
const H5TabDetail = defineAsyncComponent(() => import('./h5/core/H5TabDetail.vue'))
const H5TabAdjustment = defineAsyncComponent(() => import('./h5/core/H5TabAdjustment.vue'))
const H5TabAnalysis = defineAsyncComponent(() => import('./h5/core/H5TabAnalysis.vue'))
const H5TabDisclosureListed = defineAsyncComponent(() => import('./h5/core/H5TabDisclosureListed.vue'))
const H5TabDisclosureSoe = defineAsyncComponent(() => import('./h5/core/H5TabDisclosureSoe.vue'))

// inspection
const H5TabIdleCheck = defineAsyncComponent(() => import('./h5/inspection/H5TabIdleCheck.vue'))
const H5TabPolicyCheck = defineAsyncComponent(() => import('./h5/inspection/H5TabPolicyCheck.vue'))
const H5TabAdditionCheck = defineAsyncComponent(() => import('./h5/inspection/H5TabAdditionCheck.vue'))
const H5TabDisposalCheck = defineAsyncComponent(() => import('./h5/inspection/H5TabDisposalCheck.vue'))
const H5TabTitleCheck = defineAsyncComponent(() => import('./h5/inspection/H5TabTitleCheck.vue'))
const H5TabRelatedParty = defineAsyncComponent(() => import('./h5/inspection/H5TabRelatedParty.vue'))

// stocktake
const H5TabStocktakePlan = defineAsyncComponent(() => import('./h5/stocktake/H5TabStocktakePlan.vue'))
const H5TabStocktakeCheck = defineAsyncComponent(() => import('./h5/stocktake/H5TabStocktakeCheck.vue'))
const H5TabStocktakeSummary = defineAsyncComponent(() => import('./h5/stocktake/H5TabStocktakeSummary.vue'))

// depletion
const H5TabDepletionNoImpair = defineAsyncComponent(() => import('./h5/depletion/H5TabDepletionNoImpair.vue'))
const H5TabDepletionWithImpair = defineAsyncComponent(() => import('./h5/depletion/H5TabDepletionWithImpair.vue'))
const H5TabDepletionAlloc = defineAsyncComponent(() => import('./h5/depletion/H5TabDepletionAlloc.vue'))

// impairment
const H5TabImpairment = defineAsyncComponent(() => import('./h5/impairment/H5TabImpairment.vue'))
const H5TabRecoverable = defineAsyncComponent(() => import('./h5/impairment/H5TabRecoverable.vue'))

// lease
const H5TabOperatingLease = defineAsyncComponent(() => import('./h5/lease/H5TabOperatingLease.vue'))
const H5TabFinanceLease = defineAsyncComponent(() => import('./h5/lease/H5TabFinanceLease.vue'))

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

// ─── 行业适用性守卫 ──────────────────────────────────────────────────────────
const projectContext = inject<any>('projectContext', null)
const isApplicable = ref(true)

function checkIndustryApplicability() {
  if (!projectContext?.value && !projectContext) return // 无context默认放行
  const ctx = projectContext?.value || projectContext
  const industry = ctx?.industry || ctx?.project?.industry || ''
  if (industry && !['oil_gas', 'mining'].includes(industry)) {
    isApplicable.value = false
  }
}

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const allResponses = ref<Map<string, any>>(new Map())
const currentMode = ref<'html' | 'onlyoffice'>('html')
const modeOptions = [
  { label: '结构化视图', value: 'html' },
  { label: '在线编辑', value: 'onlyoffice' },
]
const depletionBranch = ref<'noImpair' | 'withImpair'>('noImpair')

/** 从 sheetName 提取编码 (H5/H5A/H5-1~H5-19/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  if (/附注.*上市|H5-note-listed/.test(name)) return '附注上市'
  if (/附注.*国企|H5-note-soe/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  // 程序表
  if (/H5A/.test(name)) return 'H5A'
  // H5-N 编码（H5-1 到 H5-19）
  const m = name.match(/(H5-\d+)/)
  if (m) return m[1]
  // 底稿目录 H5（无后缀）
  if (/底稿目录/.test(name) || (/\bH5\b/.test(name) && !/H5-/.test(name) && !/H5A/.test(name))) return 'H5'
  return ''
})

const showHtmlToolbar = computed(() => {
  return currentSheet.value !== '' && currentMode.value !== 'onlyoffice'
})

// ─── 双模式切换 ──────────────────────────────────────────────────────────────
function onModeChange(mode: string | number) {
  currentMode.value = mode as 'html' | 'onlyoffice'
}

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
      // 兼容两种键名：allResponses（历史）/ responses_snapshot（H5 render 策略实际输出）
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.responses_snapshot)
      if (map.size > 0) allResponses.value = map
    } else {
      // selfLoad: 自行调用 render-config
      const res = await http.get(`/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'h5-oil-gas-assets' },
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
    console.warn('[GtH5OilGasAssets] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── provide for child components ────────────────────────────────────────────
// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide，子组件 inject 命中祖先

// ─── 版本追踪 useWorkpaperVersionToolbar (autoSnapshot on save) ──────────────
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('h5VersionTrailRef', versionTrailRef)
provide('h5OpenVersionHistory', openVersionHistory)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  checkIndustryApplicability()
  void selfLoad()
})
</script>

<style scoped>
.h5-oil-gas-assets {
  width: 100%;
  min-height: 400px;
}

.loading-container {
  padding: 24px;
}

.h5-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.depletion-branch-selector {
  padding: 8px 16px;
}
</style>
