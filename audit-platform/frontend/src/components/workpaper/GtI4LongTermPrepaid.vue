<template>
  <div class="i4-long-term-prepaid">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'I4'" class="i4-header-toolbar">
        <el-segmented
          v-if="dualMode.isOoAvailable.value"
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value && !dualMode.checking.value" size="small" type="info">仅结构化视图</el-tag>
      </div>

      <!-- OnlyOffice 模式 -->
      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- HTML 结构化视图 -->
      <template v-else-if="dualMode.currentMode.value === 'html'">
        <!-- 底稿目录 -->
        <I4TabIndex
          v-if="currentSheet === 'I4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I4A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'I4A'"
          sheet-code="I4A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- I4-1 审定表 -->
        <template v-else-if="currentSheet === 'I4-1'">
          <HiFourTableSourcePanel
            v-if="props.htmlData?.hi_extraction_enabled"
            :wp-code="'I4'"
            :segments="getHiExtractionSegments('I4')"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            @refresh-complete="selfLoad()"
          />
          <I4TabAdjudication
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :tb-data="tbData"
            :is-readonly="isReadonly"
            :html-data="props.htmlData"
            @save="handleChildSave"
            @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          />
        </template>

        <!-- 附注披露（上市） -->
        <I4TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（国企） -->
        <I4TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />
        <!-- I4-2 明细表 -->
        <I4TabDetail
          v-else-if="currentSheet === 'I4-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- I4-3 调整分录 -->
        <I4TabAdjustment
          v-else-if="currentSheet === 'I4-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I4-4 摊销政策检查 -->
        <I4TabPolicyCheck
          v-else-if="currentSheet === 'I4-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :project-context="projectContext"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I4-5 针对性检查 -->
        <I4TabTargetedCheck
          v-else-if="currentSheet === 'I4-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I4-6 / I4-7 摊销测算 (2分支选择器: 直线法/工作量法) -->
        <template v-else-if="currentSheet === 'I4-6' || currentSheet === 'I4-7'">
          <div class="amort-branch-selector" style="margin-bottom:12px;padding:0 16px">
            <el-segmented
              v-model="amortizationMethod"
              :options="[
                { label: '直线法（I4-6）', value: 'straight' },
                { label: '工作量法（I4-7）', value: 'units' },
              ]"
              size="small"
            />
          </div>
          <I4TabAmortizationStraight
            v-if="amortizationMethod === 'straight'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
          <I4TabAmortizationUnits
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

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
 * GtI4LongTermPrepaid.vue — I4 长期待摊费用底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * 摊销分支选择器: 直线法(I4-6) vs 工作量法(I4-7)
 * checklist_responses 前缀: "I4-{sheet}-{field}"
 *
 * Spec（归档）: .kiro/specs/_archive/05-business-features/i4-long-term-prepaid/ Task 1.1
 * Requirements: 1.1-1.10
 *
 * 数据加载/保存：本壳层自管 selfLoad + handleChildSave（勿再用孤儿 useI4FormData）。
 */
import { ref, computed, onMounted, watch, provide, toRef, defineAsyncComponent, inject } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useI4DualMode } from './composables/useI4DualMode'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import HiFourTableSourcePanel from './shared/HiFourTableSourcePanel.vue'
import { getHiExtractionSegments } from './composables/hiExtractionSegments'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

// core
const I4TabIndex = defineAsyncComponent(() => import('./i4/core/I4TabIndex.vue'))
const I4TabAdjudication = defineAsyncComponent(() => import('./i4/core/I4TabAdjudication.vue'))
const I4TabDetail = defineAsyncComponent(() => import('./i4/core/I4TabDetail.vue'))
const I4TabAdjustment = defineAsyncComponent(() => import('./i4/core/I4TabAdjustment.vue'))
const I4TabPolicyCheck = defineAsyncComponent(() => import('./i4/core/I4TabPolicyCheck.vue'))
const I4TabTargetedCheck = defineAsyncComponent(() => import('./i4/core/I4TabTargetedCheck.vue'))
const I4TabDisclosureListed = defineAsyncComponent(() => import('./i4/core/I4TabDisclosureListed.vue'))
const I4TabDisclosureSoe = defineAsyncComponent(() => import('./i4/core/I4TabDisclosureSoe.vue'))

// amortization
const I4TabAmortizationStraight = defineAsyncComponent(() => import('./i4/amortization/I4TabAmortizationStraight.vue'))
const I4TabAmortizationUnits = defineAsyncComponent(() => import('./i4/amortization/I4TabAmortizationUnits.vue'))

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
const tbData = ref({
  unadjusted1801: 0,
  audited1801: 0,
  priorAudited1801: 0,
})
const amortizationMethod = ref<'straight' | 'units'>('straight')

// ─── 双模式 useI4DualMode (OO 健康检查 + el-segmented) ──────────────────────
const dualMode = useI4DualMode({
  wpId: computed(() => props.wpId),
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: async () => { await selfLoad() },
})

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/** 从 sheetName 提取编码 (I4/I4A/I4-1~I4-7/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'I4'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 I4A
  if (/I4A/.test(name)) return 'I4A'
  // I4-N 编码（I4-1 到 I4-7）
  const m = name.match(/(I4-\d+)/)
  if (m) return m[1]
  // 底稿目录 I4（无后缀）
  if (/底稿目录/.test(name) || (/\bI4\b/.test(name) && !/I4-/.test(name) && !/I4A/.test(name))) return 'I4'
  return ''
})

/** 项目上下文（行业推荐等） */
const projectContext = computed(() =>
  props.htmlData?.project_context
  ?? props.htmlData?.projectContext
  ?? null,
)

// ─── 子组件 save 回调（持久化 checklist_responses） ────────────────────────────
async function handleChildSave(itemId: string, value: any): Promise<void> {
  if (!props.wpId) return
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  // 完成度标记：conclusion 需可被目录扫描（I4-4-completion / -ok）
  const isStatusMarker = /-(completion|completion-ok)$/.test(itemId)
  const payload = {
    item_id: itemId,
    conclusion: isStatusMarker ? strVal : null,
    remark: strVal,
  }
  allResponses.value.set(itemId, payload)
  try {
    await http.put(`/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [payload],
    })
  } catch {
    // 静默失败，数据保留在本地
  }
}

// ─── TB自动取数（1801长期待摊费用） ───────────────────────────────────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '1801' },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u1801 = 0, a1801 = 0, p1801 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('1801')) {
        u1801 += Number(item.unadjusted_amount ?? 0)
        a1801 += Number(item.audited_amount ?? 0)
        p1801 += Number(
          item.prior_amount
          ?? item.prior_audited_amount
          ?? item.prior_period_amount
          ?? item.last_year_amount
          ?? item.opening_audited_amount
          ?? 0,
        )
      }
    }
    tbData.value = { unadjusted1801: u1801, audited1801: a1801, priorAudited1801: p1801 }
  } catch {
    // TB取数失败静默处理
  }
}

// ─── selfLoad ────────────────────────────────────────────────────────────────
async function selfLoad(): Promise<void> {
  try {
    if (props.htmlData) {
      // 从父级透传的 htmlData 中提取 responses
      if (props.htmlData.allResponses) {
        const map = new Map<string, any>()
        for (const [k, v] of Object.entries(props.htmlData.allResponses)) {
          map.set(k, v)
        }
        allResponses.value = map
      }
    } else {
      // selfLoad: 自行调用 render-config
      const res = await http.get(`/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'i4-long-term-prepaid' },
        _silent: true,
      } as any)
      const data = res.data?.data || res.data
      if (data?.sheets && Array.isArray(data.sheets)) {
        const map = new Map<string, any>()
        for (const sheet of data.sheets) {
          if (sheet.html_data?.allResponses) {
            for (const [k, v] of Object.entries(sheet.html_data.allResponses)) {
              map.set(k, v)
            }
          }
        }
        allResponses.value = map
      }
    }
  } catch (err) {
    console.warn('[GtI4LongTermPrepaid] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── 摊销分支联动：根据 sheetName 自动设置分支 ──────────────────────────────
function syncAmortizationBranch() {
  const sheet = currentSheet.value
  if (sheet === 'I4-6') amortizationMethod.value = 'straight'
  else if (sheet === 'I4-7') amortizationMethod.value = 'units'
}

// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide（真实复核对话）

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('i4VersionTrailRef', versionTrailRef)
provide('i4OpenVersionHistory', openVersionHistory)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
watch(currentSheet, () => syncAmortizationBranch())
onMounted(() => {
  syncAmortizationBranch()
  void selfLoad()
  void _loadTbData()
})
</script>

<style scoped>
.i4-long-term-prepaid {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.i4-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.amort-branch-selector {
  padding: 0 16px;
  margin-bottom: 12px;
}
</style>
