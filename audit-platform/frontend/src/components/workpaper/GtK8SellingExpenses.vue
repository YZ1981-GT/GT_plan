<template>
  <div class="k8-selling-expenses">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'K8'" class="k8-header-toolbar">
        <el-segmented
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="dualMode.onModeChange"
        />
        <!-- OnlyOffice 拉取状态（对齐 D4「拉取成功才可以」）：就绪/检测中/不可用 -->
        <el-tag
          v-if="dualMode.healthStatus.value === 'ready'"
          size="small"
          type="success"
          effect="light"
        >
          OnlyOffice 就绪（拉取成功）
        </el-tag>
        <el-tag
          v-else-if="dualMode.healthStatus.value === 'fetching'"
          size="small"
          type="warning"
          effect="light"
        >
          正在拉取 OnlyOffice 文档…
        </el-tag>
        <el-tag
          v-else-if="dualMode.healthStatus.value === 'checking'"
          size="small"
          type="info"
          effect="light"
        >
          检测 OnlyOffice…
        </el-tag>
        <el-tag v-else size="small" type="info" effect="light">
          OnlyOffice 不可用 · 仅结构化视图
        </el-tag>
      </div>

      <!-- OnlyOffice 模式 -->
      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
        @fallback="dualMode.onOoLoadFailed"
      />

      <!-- HTML 结构化视图 -->
      <template v-else-if="dualMode.currentMode.value === 'html'">
        <!-- 底稿目录 -->
        <K8TabIndex
          v-if="currentSheet === 'K8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K8A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'K8A'"
          sheet-code="K8A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- K8-1 审定表（损益类！取发生额） -->
        <K8TabAdjudication
          v-else-if="currentSheet === 'K8-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :is-readonly="isReadonly"
          :prefill="adjudicationPrefill"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K8-2 明细表（27列3区段，48行） -->
        <K8TabDetail
          v-else-if="currentSheet === 'K8-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
        />

        <!-- K8-3 调整分录 -->
        <K8TabAdjustment
          v-else-if="currentSheet === 'K8-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K8-4 实质性分析（25公式，39行） -->
        <K8TabSubstantiveAnalysis
          v-else-if="currentSheet === 'K8-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K8-5 合同检查 -->
        <K8TabContractCheck
          v-else-if="currentSheet === 'K8-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K8-6 截止测试（记账凭证→原始凭证） -->
        <K8TabCutoffV2S
          v-else-if="currentSheet === 'K8-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
        />

        <!-- K8-7 截止测试（原始凭证→记账凭证） -->
        <K8TabCutoffS2V
          v-else-if="currentSheet === 'K8-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
        />

        <!-- K8-8 销售费用检查表（凭证级测试） -->
        <K8TabSellingCheck
          v-else-if="currentSheet === 'K8-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市） -->
        <K8TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（国企） -->
        <K8TabDisclosureSoe
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
 * GtK8SellingExpenses.vue — K8 销售费用底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K8-{sheet}-{field}"
 *
 * 损益类科目（6601销售费用）— 取发生额非余额！与I6/H10同款处理。
 *
 * Spec: .kiro/specs/k8-selling-expenses/ Task 1.1
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
const K8TabIndex = defineAsyncComponent(() => import('./k8/core/K8TabIndex.vue'))
const K8TabAdjudication = defineAsyncComponent(() => import('./k8/core/K8TabAdjudication.vue'))
const K8TabDetail = defineAsyncComponent(() => import('./k8/core/K8TabDetail.vue'))
const K8TabAdjustment = defineAsyncComponent(() => import('./k8/core/K8TabAdjustment.vue'))
const K8TabDisclosureListed = defineAsyncComponent(() => import('./k8/core/K8TabDisclosureListed.vue'))
const K8TabDisclosureSoe = defineAsyncComponent(() => import('./k8/core/K8TabDisclosureSoe.vue'))

// analysis
const K8TabSubstantiveAnalysis = defineAsyncComponent(() => import('./k8/analysis/K8TabSubstantiveAnalysis.vue'))

// cutoff
const K8TabCutoffV2S = defineAsyncComponent(() => import('./k8/cutoff/K8TabCutoffV2S.vue'))
const K8TabCutoffS2V = defineAsyncComponent(() => import('./k8/cutoff/K8TabCutoffS2V.vue'))

// inspection
const K8TabContractCheck = defineAsyncComponent(() => import('./k8/inspection/K8TabContractCheck.vue'))
const K8TabSellingCheck = defineAsyncComponent(() => import('./k8/inspection/K8TabSellingCheck.vue'))

// ─── 双模式 composable ──────────────────────────────────────────────────────
import { useK8DualMode } from './composables/useK8DualMode'
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
  /** 6601 未审发生额 */
  unadjusted6601: 0,
  /** 6601 审定发生额 */
  audited6601: 0,
})

/** tb_balance 6601 明细子科目预填（后端 render 输出 adjudication_prefill） */
const adjudicationPrefill = computed<Array<{ name: string; unadjustedDebit: number; unadjustedCredit: number }>>(() =>
  Array.isArray(props.htmlData?.adjudication_prefill) ? props.htmlData.adjudication_prefill : []
)

// ─── 双模式 (OO 健康检查 + el-segmented) ─────────────────────────────────────
const dualMode = useK8DualMode({
  wpId: computed(() => props.wpId),
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: async () => { await selfLoad() },
})

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (K8/K8A/K8-1~K8-8/附注)
 * 损益类底稿 — 审定取发生额非余额
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K8'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 K8A
  if (/K8A/.test(name)) return 'K8A'
  // K8-N 编码（K8-1 到 K8-8）
  const m = name.match(/(K8-\d+)/)
  if (m) return m[1]
  // 底稿目录 K8（无后缀）
  if (/底稿目录/.test(name) || (/\bK8\b/.test(name) && !/K8-/.test(name) && !/K8A/.test(name))) return 'K8'
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
    console.warn(`[GtK8SellingExpenses] save failed: ${itemId}`, error)
  }
}

// ─── TB自动取数（6601销售费用 — 损益类取发生额！） ─────────────────────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '6601', year: props.year },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u6601 = 0, a6601 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('6601')) {
        u6601 += Number(item.unadjusted_amount ?? 0)
        a6601 += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value = { unadjusted6601: u6601, audited6601: a6601 }
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
    console.warn('[GtK8SellingExpenses] selfLoad failed:', err)
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
.k8-selling-expenses {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.k8-header-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
