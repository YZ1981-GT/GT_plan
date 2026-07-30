<template>
  <div class="i1-intangible-assets">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'I1'" class="i1-header-toolbar">
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
        <!-- 底稿目录 I1 -->
        <I1TabIndex
          v-if="currentSheet === 'I1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I1A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'I1A'"
          sheet-code="I1A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- I1-1 审定表 -->
        <HiFourTableSourcePanel
          v-if="props.htmlData?.hi_extraction_enabled"
          :wp-code="'I1'"
          :segments="getHiExtractionSegments('I1')"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @refresh-complete="selfLoad()"
        />
        <I1TabAdjudication
          v-else-if="currentSheet === 'I1-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :is-readonly="isReadonly"
          :cross-sheet-cost-audited="adjudicationFromDetail.costAudited"
          :cross-sheet-amort-audited="adjudicationFromDetail.amortAudited"
          :cross-sheet-impair-audited="adjudicationFromDetail.impairAudited"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I1-2 明细表 -->
        <I1TabDetail
          v-else-if="currentSheet === 'I1-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I1-3 调整分录 -->
        <I1TabAdjustment
          v-else-if="currentSheet === 'I1-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I1-4 摊销减值政策检查 -->
        <I1TabPolicyCheck
          v-else-if="currentSheet === 'I1-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I1-5 增加检查 -->
        <I1TabAdditionCheck
          v-else-if="currentSheet === 'I1-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :year="props.year"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I1-6 减少明细 -->
        <I1TabDisposalCheck
          v-else-if="currentSheet === 'I1-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :year="props.year"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I1-7 使用寿命检查 -->
        <I1TabUsefulLifeCheck
          v-else-if="currentSheet === 'I1-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I1-8 权属检查 -->
        <I1TabTitleCheck
          v-else-if="currentSheet === 'I1-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I1-9 摊销分配分析 -->
        <I1TabAmortizationAlloc
          v-else-if="currentSheet === 'I1-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :amortization-by-asset="amortizationForAlloc.byAsset"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I1-10 / I1-11 摊销测算 (2分支选择器) -->
        <template v-else-if="currentSheet === 'I1-10' || currentSheet === 'I1-11'">
          <div class="amort-branch-selector" style="margin-bottom:12px;padding:0 16px">
            <el-segmented
              v-model="amortizationBranch"
              :options="[
                { label: '不含减值（I1-10）', value: 'noImpair' },
                { label: '含减值（I1-11）', value: 'withImpair' },
              ]"
              size="small"
            />
          </div>
          <I1TabAmortizationNoImpair
            v-if="amortizationBranch === 'noImpair'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            @save="handleChildSave"
            @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          />
          <I1TabAmortizationWithImpair
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            @save="handleChildSave"
            @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          />
        </template>

        <!-- I1-12 减值准备测试 -->
        <I1TabImpairmentTest
          v-else-if="currentSheet === 'I1-12'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I1-13 可收回金额测试(DCF) -->
        <I1TabRecoverableTest
          v-else-if="currentSheet === 'I1-13'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市） -->
        <I1TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <I1TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
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
 * GtI1IntangibleAssets.vue — I1 无形资产底稿主入口
 *
 * sheetName prop v-if 分发到全部14个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * 摊销分支选择器: I1-10(不含减值) vs I1-11(含减值)
 *
 * Spec: .kiro/specs/i1-intangible-assets/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, watch, onMounted, provide, toRef, defineAsyncComponent, inject } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useI1DualMode } from './composables/useI1DualMode'
import { useI1CrossSheet } from './composables/useI1CrossSheet'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import HiFourTableSourcePanel from './shared/HiFourTableSourcePanel.vue'
import { getHiExtractionSegments } from './composables/hiExtractionSegments'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

// core
const I1TabIndex = defineAsyncComponent(() => import('./i1/core/I1TabIndex.vue'))
const I1TabAdjudication = defineAsyncComponent(() => import('./i1/core/I1TabAdjudication.vue'))
const I1TabDetail = defineAsyncComponent(() => import('./i1/core/I1TabDetail.vue'))
const I1TabAdjustment = defineAsyncComponent(() => import('./i1/core/I1TabAdjustment.vue'))
const I1TabDisclosureListed = defineAsyncComponent(() => import('./i1/core/I1TabDisclosureListed.vue'))
const I1TabDisclosureSoe = defineAsyncComponent(() => import('./i1/core/I1TabDisclosureSoe.vue'))

// inspection
const I1TabPolicyCheck = defineAsyncComponent(() => import('./i1/inspection/I1TabPolicyCheck.vue'))
const I1TabAdditionCheck = defineAsyncComponent(() => import('./i1/inspection/I1TabAdditionCheck.vue'))
const I1TabDisposalCheck = defineAsyncComponent(() => import('./i1/inspection/I1TabDisposalCheck.vue'))
const I1TabUsefulLifeCheck = defineAsyncComponent(() => import('./i1/inspection/I1TabUsefulLifeCheck.vue'))
const I1TabTitleCheck = defineAsyncComponent(() => import('./i1/inspection/I1TabTitleCheck.vue'))

// amortization
const I1TabAmortizationAlloc = defineAsyncComponent(() => import('./i1/amortization/I1TabAmortizationAlloc.vue'))
const I1TabAmortizationNoImpair = defineAsyncComponent(() => import('./i1/amortization/I1TabAmortizationNoImpair.vue'))
const I1TabAmortizationWithImpair = defineAsyncComponent(() => import('./i1/amortization/I1TabAmortizationWithImpair.vue'))

// impairment
const I1TabImpairmentTest = defineAsyncComponent(() => import('./i1/impairment/I1TabImpairmentTest.vue'))
const I1TabRecoverableTest = defineAsyncComponent(() => import('./i1/impairment/I1TabRecoverableTest.vue'))

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
  unadjusted1701: 0,
  audited1701: 0,
  unadjusted1702: 0,
  audited1702: 0,
  unadjusted1703: 0,
  audited1703: 0,
})
const amortizationBranch = ref<'noImpair' | 'withImpair'>('noImpair')

// ─── 跨Sheet：I1-10/11 → I1-9 摊销分配 ─────────────────────────────────────
const { amortizationForAlloc, adjudicationFromDetail } = useI1CrossSheet(allResponses)

// ─── 双模式 useI1DualMode (OO 健康检查 + el-segmented) ──────────────────────
const wpIdRef = computed(() => props.wpId)
const dualMode = useI1DualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: async () => { void selfLoad() },
})

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/** 从 sheetName 提取编码 (I1/I1A/I1-1~I1-13/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  // 源模板国企 sheet 名是「附注披露信息（国有企业）」——「国有企业」而非「国企」，
  // 只认「国企」会落到末尾 fallback 被误判成上市（H1 实测踩中过）
  if (/附注.*上市|I1-note-listed/.test(name)) return '附注上市'
  if (/附注.*国企|附注.*国有|I1-note-soe/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') || name.includes('国有') ? '附注国企' : '附注上市'
  // 程序表 I1A
  if (/I1A/.test(name)) return 'I1A'
  // 审定表（xlsx「审定表I1」/ Adjudication_I1）→ I1-1，勿误判为目录
  if (/审定表|Adjudication_I1/.test(name)) return 'I1-1'
  // I1-N 编码（I1-1 到 I1-13）
  const m = name.match(/(I1-\d+)/)
  if (m) return m[1]
  // 底稿目录
  if (/底稿目录|Tab_Index/.test(name)) return 'I1'
  // 裸 I1（无后缀）→ 目录
  if (/\bI1\b/.test(name) && !/I1-/.test(name) && !/I1A/.test(name)) return 'I1'
  return ''
})

// ─── 双模式切换（已由 useI1DualMode composable 处理）────────────────────────

// ─── 子组件 save 回调（持久化 checklist_responses） ────────────────────────────
async function handleChildSave(itemId: string, value: any): Promise<void> {
  if (!props.wpId || !itemId) return
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  // 乐观更新本地 Map
  allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: strVal })
  try {
    await http.put(`/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: null, remark: strVal }],
    })
  } catch {
    // 静默失败，数据保留在本地
  }
}

// ─── TB自动取数（1701+1702+1703） ───────────────────────────────────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '1701,1702,1703' },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u1701 = 0, a1701 = 0, u1702 = 0, a1702 = 0, u1703 = 0, a1703 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('1701')) { u1701 += Number(item.unadjusted_amount ?? 0); a1701 += Number(item.audited_amount ?? 0) }
      else if (code.startsWith('1702')) { u1702 += Number(item.unadjusted_amount ?? 0); a1702 += Number(item.audited_amount ?? 0) }
      else if (code.startsWith('1703')) { u1703 += Number(item.unadjusted_amount ?? 0); a1703 += Number(item.audited_amount ?? 0) }
    }
    tbData.value = { unadjusted1701: u1701, audited1701: a1701, unadjusted1702: u1702, audited1702: a1702, unadjusted1703: u1703, audited1703: a1703 }
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
        params: { force_component_type: 'i1-intangible-assets' },
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
    console.warn('[GtI1IntangibleAssets] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── 摊销分支联动：根据 sheetName / 已存偏好设置分支 ────────────────────────
function syncAmortizationBranch() {
  const sheet = currentSheet.value
  if (sheet === 'I1-10') {
    amortizationBranch.value = 'noImpair'
    return
  }
  if (sheet === 'I1-11') {
    amortizationBranch.value = 'withImpair'
    return
  }
  const br = allResponses.value.get('I1-amort-branch')?.remark
  if (br === 'noImpair' || br === 'withImpair') amortizationBranch.value = br
}

// 用户在 I1-10/11 页切换分段时显式持久化（子 tab mount 不再副作用写分支）
watch(amortizationBranch, (b) => {
  if (currentSheet.value !== 'I1-10' && currentSheet.value !== 'I1-11') return
  const cur = allResponses.value.get('I1-amort-branch')?.remark
  if (cur !== b) void handleChildSave('I1-amort-branch', b)
})

watch(currentSheet, () => syncAmortizationBranch())

// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide（真实复核对话）

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('i1VersionTrailRef', versionTrailRef)
provide('i1OpenVersionHistory', openVersionHistory)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  syncAmortizationBranch()
  void selfLoad()
  void _loadTbData()
})
</script>

<style scoped>
.i1-intangible-assets {
  width: 100%;
  min-height: 400px;
}

.loading-container {
  padding: 24px;
}

.i1-header-toolbar {
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  display: flex;
  align-items: center;
  gap: 12px;
}

.amort-branch-selector {
  padding: 0 16px;
  margin-bottom: 12px;
}
</style>
