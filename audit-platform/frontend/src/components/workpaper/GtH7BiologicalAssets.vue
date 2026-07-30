<template>
  <div class="h7-biological-assets">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 行业适用性守卫：非农林牧渔行业 -->
    <el-empty
      v-else-if="!isApplicable"
      description="本底稿仅适用于农林牧渔行业项目"
      :image-size="120"
    />

    <template v-else>
      <div v-if="currentSheet !== 'H7'" class="h7-header-toolbar">
        <el-segmented
          :model-value="currentMode"
          :options="modeOptions"
          size="small"
          @change="onModeChange"
        />
        <!-- 计量模式切换 -->
        <el-segmented
          v-if="currentMode === 'html'"
          v-model="measurementModel"
          :options="measurementOptions"
          size="small"
          style="margin-left: 16px"
          @change="onMeasurementModelChange"
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
        <!-- 底稿目录 H7 -->
        <H7TabIndex
          v-if="currentSheet === 'H7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
          :is-readonly="isReadonly"
        />

        <!-- H7A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'H7A'"
          sheet-code="H7A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- H7-1 审定表（双版本：成本/公允） -->
        <template v-else-if="currentSheet === 'H7-1'">
          <HiFourTableSourcePanel
            v-if="props.htmlData?.hi_extraction_enabled"
            :wp-code="'H7'"
            :segments="getHiExtractionSegments('H7')"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            @refresh-complete="selfLoad()"
          />
          <H7TabAdjudicationCost
            v-if="measurementModel === 'cost'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
          <H7TabAdjudicationFair
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H7-2 明细表（双版本：成本/公允） -->
        <template v-else-if="currentSheet === 'H7-2'">
          <H7TabDetailCost
            v-if="measurementModel === 'cost'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
          <H7TabDetailFair
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H7-3 调整分录 -->
        <H7TabAdjustment
          v-else-if="currentSheet === 'H7-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H7-4 会计政策检查（CAS5） -->
        <H7TabPolicyCheck
          v-else-if="currentSheet === 'H7-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :measurement-model="measurementModel"
          :is-readonly="isReadonly"
        />

        <!-- H7-5 分析表 -->
        <H7TabAnalysis
          v-else-if="currentSheet === 'H7-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H7-6 增加检查（双版本：成本/公允） -->
        <template v-else-if="currentSheet === 'H7-6'">
          <H7TabAdditionCost
            v-if="measurementModel === 'cost'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
          <H7TabAdditionFair
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H7-7 减少检查（双版本：成本/公允） -->
        <template v-else-if="currentSheet === 'H7-7'">
          <H7TabDisposalCost
            v-if="measurementModel === 'cost'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
          <H7TabDisposalFair
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H7-8 监盘计划 -->
        <H7TabStocktakePlan
          v-else-if="currentSheet === 'H7-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H7-9 盘点检查 -->
        <H7TabStocktakeCheck
          v-else-if="currentSheet === 'H7-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H7-10 监盘小结 -->
        <H7TabStocktakeSummary
          v-else-if="currentSheet === 'H7-10'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H7-11 折旧测算表（仅成本模式，含分支选择器） -->
        <template v-else-if="currentSheet === 'H7-11'">
          <div v-if="measurementModel === 'fair_value'" class="h7-mode-hint">
            <el-alert type="info" :closable="false" show-icon>
              公允价值模式下不计提折旧，此表仅适用于成本模式。
            </el-alert>
          </div>
          <template v-else>
            <div class="depreciation-branch-selector" style="margin-bottom:12px;padding:0 16px">
              <el-segmented
                v-model="depBranch"
                :options="[{label:'不含减值-直线法',value:'noImpair'},{label:'含减值',value:'withImpair'}]"
                size="small"
              />
            </div>
            <H7TabDepreciationNoImpair
              v-if="depBranch === 'noImpair'"
              :wp-id="props.wpId"
              :project-id="props.projectId"
              :all-responses="allResponses"
              :is-readonly="isReadonly"
            />
            <H7TabDepreciationWithImpair
              v-else
              :wp-id="props.wpId"
              :project-id="props.projectId"
              :all-responses="allResponses"
              :is-readonly="isReadonly"
            />
          </template>
        </template>

        <!-- H7-12 折旧分配（仅成本模式） -->
        <template v-else-if="currentSheet === 'H7-12'">
          <div v-if="measurementModel === 'fair_value'" class="h7-mode-hint">
            <el-alert type="info" :closable="false" show-icon>
              公允价值模式下不计提折旧，此表仅适用于成本模式。
            </el-alert>
          </div>
          <H7TabDepreciationAlloc
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H7-13 公允价值复核（仅公允模式核心） -->
        <template v-else-if="currentSheet === 'H7-13'">
          <div v-if="measurementModel === 'cost'" class="h7-mode-hint">
            <el-alert type="info" :closable="false" show-icon>
              成本模式下不适用公允价值复核，此表仅适用于公允价值模式。
            </el-alert>
          </div>
          <H7TabFairValueReview
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H7-14 互转审核 + 产量记录 -->
        <H7TabTransferReview
          v-else-if="currentSheet === 'H7-14'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H7-15 减值测算（仅成本模式） -->
        <template v-else-if="currentSheet === 'H7-15'">
          <div v-if="measurementModel === 'fair_value'" class="h7-mode-hint">
            <el-alert type="info" :closable="false" show-icon>
              公允价值模式下不计提减值，此表仅适用于成本模式。
            </el-alert>
          </div>
          <H7TabImpairment
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H7-16 可收回金额（仅成本模式） -->
        <template v-else-if="currentSheet === 'H7-16'">
          <div v-if="measurementModel === 'fair_value'" class="h7-mode-hint">
            <el-alert type="info" :closable="false" show-icon>
              公允价值模式下不适用可收回金额测试，此表仅适用于成本模式。
            </el-alert>
          </div>
          <H7TabRecoverable
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H7-17 关联交易 -->
        <H7TabRelatedParty
          v-else-if="currentSheet === 'H7-17'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（上市） -->
        <H7TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（国企） -->
        <H7TabDisclosureSoe
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

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtH7BiologicalAssets.vue — H7 生产性生物资产底稿主入口
 *
 * sheetName prop v-if 分发到全部23个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * measurementModel: 双计量模式(成本/公允价值)控制 H7-1/H7-2/H7-6/H7-7 的双版本显隐。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * 行业守卫: applicable_when industry IN ['agriculture','forestry','livestock','fishery']。
 * useVersionTrail: autoSnapshot on save。
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 1.1
 * Requirements: 1.1-1.9, 1.11, 1.13
 */
import { ref, computed, onMounted, provide, toRef, inject, watch, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import HiFourTableSourcePanel from './shared/HiFourTableSourcePanel.vue'
import { getHiExtractionSegments } from './composables/hiExtractionSegments'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

// core
import H7TabIndex from './h7/core/H7TabIndex.vue'
const H7TabAdjudicationCost = defineAsyncComponent(() => import('./h7/core/H7TabAdjudicationCost.vue'))
const H7TabAdjudicationFair = defineAsyncComponent(() => import('./h7/core/H7TabAdjudicationFair.vue'))
const H7TabDetailCost = defineAsyncComponent(() => import('./h7/core/H7TabDetailCost.vue'))
const H7TabDetailFair = defineAsyncComponent(() => import('./h7/core/H7TabDetailFair.vue'))
const H7TabAdjustment = defineAsyncComponent(() => import('./h7/core/H7TabAdjustment.vue'))
const H7TabAnalysis = defineAsyncComponent(() => import('./h7/core/H7TabAnalysis.vue'))
const H7TabDisclosureListed = defineAsyncComponent(() => import('./h7/core/H7TabDisclosureListed.vue'))
const H7TabDisclosureSoe = defineAsyncComponent(() => import('./h7/core/H7TabDisclosureSoe.vue'))

// inspection
const H7TabPolicyCheck = defineAsyncComponent(() => import('./h7/inspection/H7TabPolicyCheck.vue'))
const H7TabAdditionCost = defineAsyncComponent(() => import('./h7/inspection/H7TabAdditionCost.vue'))
const H7TabAdditionFair = defineAsyncComponent(() => import('./h7/inspection/H7TabAdditionFair.vue'))
const H7TabDisposalCost = defineAsyncComponent(() => import('./h7/inspection/H7TabDisposalCost.vue'))
const H7TabDisposalFair = defineAsyncComponent(() => import('./h7/inspection/H7TabDisposalFair.vue'))
const H7TabTransferReview = defineAsyncComponent(() => import('./h7/inspection/H7TabTransferReview.vue'))
const H7TabRelatedParty = defineAsyncComponent(() => import('./h7/inspection/H7TabRelatedParty.vue'))

// stocktake
const H7TabStocktakePlan = defineAsyncComponent(() => import('./h7/stocktake/H7TabStocktakePlan.vue'))
const H7TabStocktakeCheck = defineAsyncComponent(() => import('./h7/stocktake/H7TabStocktakeCheck.vue'))
const H7TabStocktakeSummary = defineAsyncComponent(() => import('./h7/stocktake/H7TabStocktakeSummary.vue'))

// depreciation
const H7TabDepreciationNoImpair = defineAsyncComponent(() => import('./h7/depreciation/H7TabDepreciationNoImpair.vue'))
const H7TabDepreciationWithImpair = defineAsyncComponent(() => import('./h7/depreciation/H7TabDepreciationWithImpair.vue'))
const H7TabDepreciationAlloc = defineAsyncComponent(() => import('./h7/depreciation/H7TabDepreciationAlloc.vue'))

// impairment
const H7TabImpairment = defineAsyncComponent(() => import('./h7/impairment/H7TabImpairment.vue'))
const H7TabRecoverable = defineAsyncComponent(() => import('./h7/impairment/H7TabRecoverable.vue'))

// fairvalue
const H7TabFairValueReview = defineAsyncComponent(() => import('./h7/fairvalue/H7TabFairValueReview.vue'))

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
const APPLICABLE_INDUSTRIES = ['agriculture', 'forestry', 'livestock', 'fishery']
const projectContext = inject<any>('projectContext', null)
const isApplicable = ref(true)

function checkIndustryApplicability() {
  if (!projectContext?.value && !projectContext) return // 无context默认放行
  const ctx = projectContext?.value || projectContext
  const industry = ctx?.industry || ctx?.project?.industry || ''
  if (industry && !APPLICABLE_INDUSTRIES.includes(industry)) {
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

// 计量模式
const measurementModel = ref<'cost' | 'fair_value'>('cost')
const measurementOptions = [
  { label: '成本模式', value: 'cost' },
  { label: '公允价值模式', value: 'fair_value' },
]

// H7-11 折旧分支选择器
const depBranch = ref<'noImpair' | 'withImpair'>('noImpair')

/** 从 sheetName 提取编码 (H7/H7A/H7-1~H7-17/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  // 源模板国企 sheet 名是「附注披露信息（国有企业）」——「国有企业」而非「国企」，
  // 只认「国企」会落到末尾 fallback 被误判成上市（H1 实测踩中过）
  if (/附注.*上市|H7-note-listed/.test(name)) return '附注上市'
  if (/附注.*国企|附注.*国有|H7-note-soe/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') || name.includes('国有') ? '附注国企' : '附注上市'
  // 程序表
  if (/H7A/.test(name)) return 'H7A'
  // H7-N 编码（H7-1 到 H7-17）
  const m = name.match(/(H7-\d+)/)
  if (m) return m[1]
  // 底稿目录 H7（无后缀）
  if (/底稿目录/.test(name) || (/\bH7\b/.test(name) && !/H7-/.test(name) && !/H7A/.test(name))) return 'H7'
  return ''
})

// ─── 双模式切换 ──────────────────────────────────────────────────────────────
function onModeChange(mode: string | number) {
  currentMode.value = mode as 'html' | 'onlyoffice'
}

function onMeasurementModelChange(val: string | number) {
  measurementModel.value = val as 'cost' | 'fair_value'
  // 持久化到 checklist_responses
  void saveMeasurementModel(val as string)
}

async function saveMeasurementModel(model: string) {
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: 'H7-measurement-model', conclusion: null, remark: model }],
    }, { _silent: true } as any)
  } catch (err) {
    console.warn('[GtH7BiologicalAssets] saveMeasurementModel failed:', err)
  }
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
      // 兼容两种键名：allResponses（历史）/ responses_snapshot（H7 render 策略实际输出）
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.responses_snapshot)
      if (map.size > 0) allResponses.value = map
      // 恢复 measurement_model 状态
      if (props.htmlData.measurement_model) {
        measurementModel.value = props.htmlData.measurement_model
      }
    } else {
      // selfLoad: 自行调用 render-config（/api 前缀，经 dev proxy 到后端）
      const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'h7-biological-assets' },
        _silent: true,
      } as any)
      const data = res.data?.data || res.data
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
    // 从 allResponses 恢复 measurement_model（存于 remark，兼容对象/原始值两种形态）
    const savedModelRaw = allResponses.value.get('H7-measurement-model')
    const savedModel = savedModelRaw && typeof savedModelRaw === 'object'
      ? (savedModelRaw.remark ?? savedModelRaw.conclusion)
      : savedModelRaw
    if (savedModel === 'cost' || savedModel === 'fair_value') {
      measurementModel.value = savedModel
    }
  } catch (err) {
    console.warn('[GtH7BiologicalAssets] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── 子组件 save 持久化（子 tab 通过 inject('saveResponse') 调用） ──────────────
// 子组件契约：saveResponse(itemId, value)。value 为字符串或对象（对象序列化进 remark）。
// 防抖 800ms 批量 PUT /checklist-responses，并乐观更新本地 Map 供 selfLoad/跨表读取。
const _saveTimers = new Map<string, ReturnType<typeof setTimeout>>()
function persistResponse(itemId: string, value: any): void {
  if (!itemId || !props.wpId) return
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  const updated = { ...existing, item_id: itemId, remark: strVal }
  allResponses.value.set(itemId, updated)
  if (isReadonly.value) return
  const prev = _saveTimers.get(itemId)
  if (prev) clearTimeout(prev)
  _saveTimers.set(itemId, setTimeout(() => {
    _saveTimers.delete(itemId)
    http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: updated.conclusion ?? null, remark: updated.remark ?? null }],
    }).catch((err: unknown) => console.warn('[GtH7] persistResponse failed:', itemId, err))
  }, 800))
}

// ─── provide for child components ────────────────────────────────────────────
function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  console.log('[H7] openReviewDialog:', sectionId, sectionLabel)
}
provide('openReviewDialog', openReviewDialog)
provide('measurementModel', measurementModel)
provide('allResponses', allResponses)
provide('saveResponse', persistResponse)

// H7 为 H 循环底稿，审计说明/结论采用纯 textarea，不接 AI（遵循 H6 先例 + fghi spec P7）。

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('h7VersionTrailRef', versionTrailRef)
provide('h7OpenVersionHistory', openVersionHistory)

// ─── Watch: measurementModel 切换时 autoSnapshot ──────────────────────────────
watch(measurementModel, () => {
  scheduleAutoSnapshot()
})

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  checkIndustryApplicability()
  void selfLoad()
})
</script>

<style scoped>
.h7-biological-assets {
  width: 100%;
  min-height: 400px;
}

.loading-container {
  padding: 24px;
}

.h7-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.h7-mode-hint {
  padding: 16px;
}

.depreciation-branch-selector {
  padding: 8px 16px;
}
</style>
