<template>
  <div class="k9-admin-expenses">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'K9'" class="k9-header-toolbar">
        <el-segmented
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="dualMode.onModeChange"
        />
        <!-- OnlyOffice 状态：必须「拉取成功」才进入在线编辑（对齐 D4 范式） -->
        <el-tag v-if="dualMode.currentMode.value === 'onlyoffice'" size="small" type="success">OnlyOffice 拉取成功</el-tag>
        <el-tag v-else-if="dualMode.fetchingConfig.value" size="small" type="warning">OnlyOffice 拉取中…</el-tag>
        <el-tag v-else-if="dualMode.checking.value" size="small" type="info">OnlyOffice 检测中…</el-tag>
        <el-tag v-else-if="!dualMode.isOoAvailable.value" size="small" type="info">OnlyOffice 不可用（仅结构化视图）</el-tag>
        <el-tag v-else size="small" type="success">OnlyOffice 就绪</el-tag>
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
        <!-- 跨表勾稽提示（仅失衡时显示；K9-1 自带详细勾稽故排除） -->
        <el-alert
          v-if="crossSheetAlerts.length > 0 && currentSheet !== 'K9-1'"
          type="warning"
          :closable="false"
          show-icon
          style="margin: 8px 12px"
        >
          <template #title>跨表勾稽提示</template>
          <ul style="margin: 4px 0 0; padding-left: 18px; line-height: 1.6">
            <li v-for="(m, i) in crossSheetAlerts" :key="i">{{ m }}</li>
          </ul>
        </el-alert>

        <!-- 底稿目录 -->
        <K9TabIndex
          v-if="currentSheet === 'K9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K9A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'K9A'"
          sheet-code="K9A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- K9-1 审定表（损益类！取发生额） -->
        <K9TabAdjudication
          v-else-if="currentSheet === 'K9-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :prefill="adjudicationPrefill"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) =          :tb-source-codes="tbSourceCodes"
        > emit('navigate-sheet', s)"
        />

        <!-- K9-2 明细表（25列3区段，55行） -->
        <K9TabDetail
          v-else-if="currentSheet === 'K9-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K9-3 调整分录 -->
        <K9TabAdjustment
          v-else-if="currentSheet === 'K9-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K9-4 实质性分析（16公式，48行） -->
        <K9TabSubstantiveAnalysis
          v-else-if="currentSheet === 'K9-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K9-5 合同检查 -->
        <K9TabContractCheck
          v-else-if="currentSheet === 'K9-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K9-6 截止测试（记账凭证→原始凭证） -->
        <K9TabCutoffV2S
          v-else-if="currentSheet === 'K9-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :period-end="periodEnd"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K9-7 截止测试（原始凭证→记账凭证） -->
        <K9TabCutoffS2V
          v-else-if="currentSheet === 'K9-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :period-end="periodEnd"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K9-8 管理费用检查表（凭证级测试） -->
        <K9TabAdminCheck
          v-else-if="currentSheet === 'K9-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市） -->
        <K9TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <K9TabDisclosureSoe
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
    </template>

  </div>
</template>

<script setup lang="ts">
/**
 * GtK9AdminExpenses.vue — K9 管理费用底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K9-{sheet}-{field}"
 *
 * 损益类科目（6602管理费用）— 取发生额非余额！与K8/I6/H10同款处理。
 *
 * Spec: .kiro/specs/k9-admin-expenses/ Task 1.1
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
import { useK9DualMode } from './composables/useK9DualMode'
import { useK9CrossSheet } from './composables/useK9CrossSheet'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core
const K9TabIndex = defineAsyncComponent(() => import('./k9/core/K9TabIndex.vue'))
const K9TabAdjudication = defineAsyncComponent(() => import('./k9/core/K9TabAdjudication.vue'))
const K9TabDetail = defineAsyncComponent(() => import('./k9/core/K9TabDetail.vue'))
const K9TabAdjustment = defineAsyncComponent(() => import('./k9/core/K9TabAdjustment.vue'))
const K9TabDisclosureListed = defineAsyncComponent(() => import('./k9/core/K9TabDisclosureListed.vue'))
const K9TabDisclosureSoe = defineAsyncComponent(() => import('./k9/core/K9TabDisclosureSoe.vue'))

// analysis
const K9TabSubstantiveAnalysis = defineAsyncComponent(() => import('./k9/analysis/K9TabSubstantiveAnalysis.vue'))

// cutoff
const K9TabCutoffV2S = defineAsyncComponent(() => import('./k9/cutoff/K9TabCutoffV2S.vue'))
const K9TabCutoffS2V = defineAsyncComponent(() => import('./k9/cutoff/K9TabCutoffS2V.vue'))

// inspection
const K9TabContractCheck = defineAsyncComponent(() => import('./k9/inspection/K9TabContractCheck.vue'))
const K9TabAdminCheck = defineAsyncComponent(() => import('./k9/inspection/K9TabAdminCheck.vue'))

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
  /** 6602 未审发生额 */
  unadjusted6602: 0,
  /** 6602 审定发生额 */
  audited6602: 0,
})
/** 会计期间截止日（按审计年度），供 K9-6/K9-7 截止测试抽样使用 */
const periodEnd = computed(() => `${props.year ?? new Date().getFullYear()}-12-31`)
/** K9-1 审定表明细子科目预填（来自后端 render adjudication_prefill） */
const adjudicationPrefill = computed<Array<{ name: string; unadjustedDebit: number; unadjustedCredit: number }>>(
  () => (Array.isArray(props.htmlData?.adjudication_prefill) ? props.htmlData.adjudication_prefill : []),
)

// ─── 跨表勾稽（K9-1↔K9-2 / K9-4↔K9-2）：仅失衡时提示，K9-1 有自己的详细勾稽故排除 ───
const crossSheet = useK9CrossSheet(allResponses as any)
const crossSheetAlerts = computed<string[]>(() => {
  const out: string[] = []
  const adj = crossSheet.adjudicationVsDetail.value
  if (!adj.isMatch) out.push(`K9-1 审定合计 与 K9-2 明细合计差异 ${adj.diff.toFixed(2)}`)
  if (!crossSheet.analysisVsDetail.value.isMatch) out.push('K9-4 实质性分析合计 与 K9-2 明细合计不一致')
  return out
})

// ─── 双模式 (OO 健康检查 + el-segmented) ─────────────────────────────────────
const dualMode = useK9DualMode({
  wpId: computed(() => props.wpId) as any,
  sheetName: computed(() => props.sheetName || '') as any,
  reloadAll: async () => { await selfLoad() },
})

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (K9/K9A/K9-1~K9-8/附注)
 * 损益类底稿 — 审定取发生额非余额
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K9'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 K9A
  if (/K9A/.test(name)) return 'K9A'
  // K9-N 编码（K9-1 到 K9-8）
  const m = name.match(/(K9-\d+)/)
  if (m) return m[1]
  // 底稿目录 K9（无后缀）
  if (/底稿目录/.test(name) || (/\bK9\b/.test(name) && !/K9-/.test(name) && !/K9A/.test(name))) return 'K9'
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
    console.warn(`[GtK9AdminExpenses] save failed: ${itemId}`, error)
  }
}

// ─── TB自动取数（6602管理费用 — 损益类取发生额！） ─────────────────────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '6602', year: props.year },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u6602 = 0, a6602 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('6602')) {
        u6602 += Number(item.unadjusted_amount ?? 0)
        a6602 += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value = { unadjusted6602: u6602, audited6602: a6602 }
  } catch {
    // TB取数失败静默处理
  }
}

// ─── selfLoad（统一 Persistence Adapter） ─────────────────────────────────────
/** 四表取数溯源（render 下发，供审定表 Tab 展示来源科目与报表行） */
const tbSourceCodes = computed(() => props.htmlData?.tb_source_codes ?? null)

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
    console.warn('[GtK9AdminExpenses] selfLoad failed:', err)
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
.k9-admin-expenses {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.k9-header-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
