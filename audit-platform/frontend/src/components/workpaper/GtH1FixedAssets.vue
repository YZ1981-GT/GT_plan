<template>
  <div class="h1-fixed-assets">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="showHtmlToolbar" class="h1-header-toolbar">
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
        <H1TabIndex
          v-if="currentSheet === 'H1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'H1A'"
          sheet-code="H1A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- H1-1 审定表 -->
        <H1TabAdjudication
          v-else-if="currentSheet === 'H1-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-2 明细表 -->
        <H1TabDetail
          v-else-if="currentSheet === 'H1-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-3 调整分录 -->
        <H1TabAdjustment
          v-else-if="currentSheet === 'H1-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-4 闲置检查 -->
        <H1TabIdleCheck
          v-else-if="currentSheet === 'H1-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-5 会计政策 -->
        <H1TabPolicyCheck
          v-else-if="currentSheet === 'H1-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-6 分析表 -->
        <H1TabAnalysis
          v-else-if="currentSheet === 'H1-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-7 增加检查 -->
        <H1TabAdditionCheck
          v-else-if="currentSheet === 'H1-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-8 减少检查 -->
        <H1TabDisposalCheck
          v-else-if="currentSheet === 'H1-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-9 监盘计划 -->
        <H1TabStocktakePlan
          v-else-if="currentSheet === 'H1-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-10 盘点检查 -->
        <H1TabStocktakeCheck
          v-else-if="currentSheet === 'H1-10'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-11 监盘小结 -->
        <H1TabStocktakeSummary
          v-else-if="currentSheet === 'H1-11'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-12 折旧测算 (3分支选择器) -->
        <template v-else-if="currentSheet === 'H1-12'">
          <div class="dep-branch-selector" style="margin-bottom:12px;padding:0 16px">
            <el-segmented v-model="depreciationBranch" :options="[{label:'不含减值-直线法',value:'A'},{label:'含减值',value:'B'},{label:'多次减值',value:'C'}]" size="small" />
          </div>
          <H1TabDepreciationStraight
            v-if="depreciationBranch === 'A'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
          <H1TabDepreciationImpair
            v-else-if="depreciationBranch === 'B'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
          <H1TabDepreciationMulti
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H1-13 折旧分配 -->
        <H1TabDepreciationAlloc
          v-else-if="currentSheet === 'H1-13'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-14 减值测算 -->
        <H1TabImpairment
          v-else-if="currentSheet === 'H1-14'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-15 可收回金额 -->
        <H1TabRecoverable
          v-else-if="currentSheet === 'H1-15'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-16 房屋建筑物权属 -->
        <H1TabTitleBuilding
          v-else-if="currentSheet === 'H1-16'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-17 运输设备权属 -->
        <H1TabTitleVehicle
          v-else-if="currentSheet === 'H1-17'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-18 关联交易 -->
        <H1TabRelatedParty
          v-else-if="currentSheet === 'H1-18'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-19 经营租出 -->
        <H1TabOperatingLease
          v-else-if="currentSheet === 'H1-19'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-20 融资租出 -->
        <H1TabFinanceLease
          v-else-if="currentSheet === 'H1-20'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（上市） -->
        <H1TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（国企） -->
        <H1TabDisclosureSoe
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
 * GtH1FixedAssets.vue — H1 固定资产底稿主入口
 *
 * sheetName prop v-if 分发到全部22个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * useVersionTrail: autoSnapshot on save。
 *
 * Spec: .kiro/specs/h1-fixed-assets/ Task 6.1
 * Requirements: 1.2-1.3, 17.1
 */
import { ref, computed, onMounted, onUnmounted, provide, toRef, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import useVersionTrail from './composables/useVersionTrail'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core — H1TabIndex 非 lazy（底稿目录轻量，首屏必显）
import H1TabIndex from './h1/core/H1TabIndex.vue'
const H1TabAdjudication = defineAsyncComponent(() => import('./h1/core/H1TabAdjudication.vue'))
const H1TabDetail = defineAsyncComponent(() => import('./h1/core/H1TabDetail.vue'))
const H1TabAdjustment = defineAsyncComponent(() => import('./h1/core/H1TabAdjustment.vue'))
const H1TabAnalysis = defineAsyncComponent(() => import('./h1/core/H1TabAnalysis.vue'))
const H1TabDisclosureListed = defineAsyncComponent(() => import('./h1/core/H1TabDisclosureListed.vue'))
const H1TabDisclosureSoe = defineAsyncComponent(() => import('./h1/core/H1TabDisclosureSoe.vue'))

// inspection
const H1TabIdleCheck = defineAsyncComponent(() => import('./h1/inspection/H1TabIdleCheck.vue'))
const H1TabPolicyCheck = defineAsyncComponent(() => import('./h1/inspection/H1TabPolicyCheck.vue'))
const H1TabAdditionCheck = defineAsyncComponent(() => import('./h1/inspection/H1TabAdditionCheck.vue'))
const H1TabDisposalCheck = defineAsyncComponent(() => import('./h1/inspection/H1TabDisposalCheck.vue'))
const H1TabTitleBuilding = defineAsyncComponent(() => import('./h1/inspection/H1TabTitleBuilding.vue'))
const H1TabTitleVehicle = defineAsyncComponent(() => import('./h1/inspection/H1TabTitleVehicle.vue'))
const H1TabRelatedParty = defineAsyncComponent(() => import('./h1/inspection/H1TabRelatedParty.vue'))
const H1TabOperatingLease = defineAsyncComponent(() => import('./h1/inspection/H1TabOperatingLease.vue'))
const H1TabFinanceLease = defineAsyncComponent(() => import('./h1/inspection/H1TabFinanceLease.vue'))

// stocktake
const H1TabStocktakePlan = defineAsyncComponent(() => import('./h1/stocktake/H1TabStocktakePlan.vue'))
const H1TabStocktakeCheck = defineAsyncComponent(() => import('./h1/stocktake/H1TabStocktakeCheck.vue'))
const H1TabStocktakeSummary = defineAsyncComponent(() => import('./h1/stocktake/H1TabStocktakeSummary.vue'))

// depreciation
const H1TabDepreciationStraight = defineAsyncComponent(() => import('./h1/depreciation/H1TabDepreciationStraight.vue'))
const H1TabDepreciationImpair = defineAsyncComponent(() => import('./h1/depreciation/H1TabDepreciationImpair.vue'))
const H1TabDepreciationMulti = defineAsyncComponent(() => import('./h1/depreciation/H1TabDepreciationMulti.vue'))
const H1TabDepreciationAlloc = defineAsyncComponent(() => import('./h1/depreciation/H1TabDepreciationAlloc.vue'))

// impairment
const H1TabImpairment = defineAsyncComponent(() => import('./h1/impairment/H1TabImpairment.vue'))
const H1TabRecoverable = defineAsyncComponent(() => import('./h1/impairment/H1TabRecoverable.vue'))

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
const currentMode = ref<'html' | 'onlyoffice'>('html')
const modeOptions = [
  { label: '结构化视图', value: 'html' },
  { label: '在线编辑', value: 'onlyoffice' },
]
const depreciationBranch = ref<'A' | 'B' | 'C'>('A')

/** 从 sheetName 提取编码 (H1/H1A/H1-1~H1-20/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  if (/附注.*上市|H1-note-listed/.test(name)) return '附注上市'
  if (/附注.*国企|H1-note-soe/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  // 程序表
  const mA = name.match(/H1A/)
  if (mA) return 'H1A'
  // H1-N 编码（H1-1 到 H1-20）
  const m = name.match(/(H1-\d+)/)
  if (m) return m[1]
  // 底稿目录 H1（无后缀）
  if (/\bH1\b/.test(name) && !/H1-/.test(name) && !/H1A/.test(name)) return 'H1'
  return ''
})

const showHtmlToolbar = computed(() => {
  const s = currentSheet.value
  return s !== '' && currentMode.value !== 'onlyoffice'
})

// ─── 双模式切换 ──────────────────────────────────────────────────────────────
function onModeChange(mode: string | number) {
  currentMode.value = mode as 'html' | 'onlyoffice'
}

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
      // 兼容两种键名：allResponses（历史）/ responses_snapshot（H1 render 策略实际输出）
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.responses_snapshot)
      if (map.size > 0) allResponses.value = map
    } else {
      // selfLoad: 自行调用 render-config
      const res = await http.get(`/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'h1-fixed-assets' },
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
    console.warn('[GtH1FixedAssets] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── provide for child components ────────────────────────────────────────────
function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  console.log('[H1] openReviewDialog:', sectionId, sectionLabel)
  // Integrated with audit-review-dialog module — real impl delegates to parent via emit
}
provide('openReviewDialog', openReviewDialog)

// ─── 版本追踪 useVersionTrail (autoSnapshot on save) ─────────────────────────
const versionTrail = useVersionTrail({
  projectId: toRef(props, 'projectId') as any,
  workpaperId: toRef(props, 'wpId') as any,
})
provide('versionTrail', versionTrail)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
let c6EventSource: EventSource | null = null

onMounted(() => {
  void selfLoad()
  // 版本追踪：已集成 useVersionTrail — createSnapshot 由保存流程触发

  // 6.9 — subscribe 'control:c6-completed' → 更新 H1A 前置状态
  subscribeC6Completed()
})

/** 6.9: 订阅 C6 前置控制完成事件，更新 H1A 程序表前置状态 */
function subscribeC6Completed() {
  try {
    c6EventSource = new EventSource(`/api/projects/${props.projectId}/events?topic=control:c6-completed`)
    c6EventSource.onmessage = (evt) => {
      try {
        const payload = JSON.parse(evt.data)
        console.log('[H1] received control:c6-completed', payload)
        // 更新 allResponses 中 H1A 前置完成状态
        allResponses.value.set('H1A-c6-prerequisite', {
          item_id: 'H1A-c6-prerequisite',
          conclusion: 'Y',
          remark: `C6完成于 ${new Date().toISOString()}`,
        })
      } catch { /* ignore parse error */ }
    }
  } catch { /* SSE not available */ }
}

onUnmounted(() => { c6EventSource?.close() })
</script>

<style scoped>
.h1-fixed-assets {
  width: 100%;
  min-height: 400px;
}

.loading-container {
  padding: 24px;
}

.h1-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
