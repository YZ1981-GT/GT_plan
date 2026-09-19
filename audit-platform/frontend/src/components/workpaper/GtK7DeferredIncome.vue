<template>
  <div class="k7-deferred-income">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'K7'" class="k7-header-toolbar">
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
        <K7TabIndex
          v-if="currentSheet === 'K7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K7A 程序表 (复用 GtAProgramConsole selfLoad) -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'K7A'"
          sheet-code="K7A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- K7-1 审定表 -->
        <K7TabAdjudication
          v-else-if="currentSheet === 'K7-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :prefill="adjudicationPrefill"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          :tb-source-codes="tbSourceCodes"
        />

        <!-- K7-2 明细表 -->
        <K7TabDetail
          v-else-if="currentSheet === 'K7-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K7-3 调整分录 -->
        <K7TabAdjustment
          v-else-if="currentSheet === 'K7-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K7-4 分摊测算表 -->
        <K7TabAmortizationCalc
          v-else-if="currentSheet === 'K7-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K7-5 递延收益检查表（凭证级测试） -->
        <K7TabDeferredCheck
          v-else-if="currentSheet === 'K7-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市公司） -->
        <K7TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <K7TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 未匹配 → OnlyOffice fallback（包含会计提示辅助sheet） -->
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
 * GtK7DeferredIncome.vue — K7 递延收益底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K7-{sheet}-{field}"
 *
 * 科目：2401递延收益（贷方/负债类）
 * 核心：期末=期初+收到-分摊（负债类！方向与资产类相反）
 *       政府补助分摊测算引擎 + 分摊去向联动K10/K12
 *
 * Spec: .kiro/specs/k7-deferred-income/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, onMounted, onBeforeUnmount, inject, defineAsyncComponent, toRef, provide } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useChecklistPersistence } from '@/composables/workpaper/useChecklistPersistence'
import { collectChecklistResponses, toChecklistPatch } from '@/composables/workpaper/checklistPersistenceHelpers'
import {
  WorkpaperRuntimeContextKey,
  type WorkpaperRuntimeContext,
} from './composables/useWorkpaperScaffold'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core
const K7TabIndex = defineAsyncComponent(() => import('./k7/core/K7TabIndex.vue'))
const K7TabAdjudication = defineAsyncComponent(() => import('./k7/core/K7TabAdjudication.vue'))
const K7TabDetail = defineAsyncComponent(() => import('./k7/core/K7TabDetail.vue'))
const K7TabAdjustment = defineAsyncComponent(() => import('./k7/core/K7TabAdjustment.vue'))
const K7TabDisclosureListed = defineAsyncComponent(() => import('./k7/core/K7TabDisclosureListed.vue'))
const K7TabDisclosureSoe = defineAsyncComponent(() => import('./k7/core/K7TabDisclosureSoe.vue'))

// amortization
const K7TabAmortizationCalc = defineAsyncComponent(() => import('./k7/amortization/K7TabAmortizationCalc.vue'))

// inspection
const K7TabDeferredCheck = defineAsyncComponent(() => import('./k7/inspection/K7TabDeferredCheck.vue'))

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

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed<string | undefined>(() => props.projectId || undefined)
const persistence = useChecklistPersistence({ wpId: wpIdRef, projectId: projectIdRef })
const allResponses = persistence.responses
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const tbData = ref({
  unadjusted2401: 0,
  audited2401: 0,
})

/** K7-1 审定表明细子科目预填（来自后端 render adjudication_prefill） */
const adjudicationPrefill = computed(() =>
  Array.isArray(props.htmlData?.adjudication_prefill) ? props.htmlData.adjudication_prefill : []
)

/** 四表取数溯源（render 下发，供审定表 Tab 展示来源科目与报表行） */
const tbSourceCodes = computed(() => props.htmlData?.tb_source_codes ?? null)


// ─── 双模式 (OO 健康检查 + el-segmented) ────────────────────────────────────
const dualMode = (() => {
  const currentMode = ref<'html' | 'onlyoffice'>('html')
  const isOoAvailable = ref(false)
  const checking = ref(true)
  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  async function checkOoHealth(): Promise<void> {
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      isOoAvailable.value = !!(res?.data?.data?.healthy ?? res?.data?.healthy)
    } catch {
      isOoAvailable.value = false
    } finally {
      checking.value = false
    }
  }

  function onModeChange(val: string | number): void {
    currentMode.value = val as 'html' | 'onlyoffice'
  }

  // 启动时检查 OO 可用性
  checkOoHealth()

  return { currentMode, isOoAvailable, checking, modeOptions, onModeChange }
})()

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (K7/K7A/K7-1~K7-5/附注)
 * 支持格式：
 *  - "底稿目录" → K7
 *  - "实质性程序表K7A" → K7A
 *  - "审定表K7-1" → K7-1
 *  - "明细表K7-2" → K7-2
 *  - "调整分录汇总K7-3" → K7-3
 *  - "测算表K7-4" → K7-4
 *  - "递延收益检查表K7-5" → K7-5
 *  - "附注披露信息（上市公司）" → 附注上市
 *  - "附注披露信息（国有企业）" → 附注国企
 *  - "会计提示" → '' (走 OO fallback)
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K7'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 K7A
  if (/K7A/.test(name)) return 'K7A'
  // K7-N 编码（K7-1 到 K7-5）
  const m = name.match(/(K7-\d+)/)
  if (m) return m[1]
  // 底稿目录 K7（无后缀）
  if (/底稿目录/.test(name) || (/\bK7\b/.test(name) && !/K7-/.test(name) && !/K7A/.test(name))) return 'K7'
  return ''
})

// ─── 子组件 save 回调（统一 Persistence Adapter） ─────────────────────────────
async function handleChildSave(itemId: string, value: unknown): Promise<void> {
  if (!props.wpId) return
  try {
    await persistence.save(itemId, toChecklistPatch(value))
    runtime?.version.scheduleAutoSnapshot()
    emit('save')
  } catch (error) {
    ElMessage.error(persistence.stateOf(itemId).lastError || '保存失败，数据已保留在本地，请稍后重试')
    console.warn(`[GtK7DeferredIncome] save failed: ${itemId}`, error)
  }
}

// ─── TB自动取数（2401递延收益） ───────────────────────────────────────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '2401', year: props.year },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u2401 = 0, a2401 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('2401')) {
        u2401 += Number(item.unadjusted_amount ?? 0)
        a2401 += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value.unadjusted2401 = u2401
    tbData.value.audited2401 = a2401
  } catch {
    // TB取数失败静默处理
  }
}

// ─── selfLoad（统一 Persistence Adapter） ─────────────────────────────────────
async function selfLoad(): Promise<void> {
  try {
    const snapshot = props.htmlData
      ? collectChecklistResponses(
          props.htmlData.responses_snapshot,
          props.htmlData.allResponses,
          props.htmlData.checklist_responses,
        )
      : []
    if (snapshot.length > 0) persistence.hydrate(snapshot)
    else await persistence.load()
  } catch (err) {
    console.warn('[GtK7DeferredIncome] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// 复核圆点
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onBeforeUnmount(() => { void persistence.flush().catch(() => undefined) })

onMounted(() => {
  void selfLoad()
  void _loadTbData()
})
</script>

<style scoped>
.k7-deferred-income {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.k7-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
