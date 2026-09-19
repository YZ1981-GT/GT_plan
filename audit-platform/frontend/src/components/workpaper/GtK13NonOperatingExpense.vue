<template>
  <div class="k13-non-operating-expense">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'K13'" class="k13-header-toolbar">
        <!-- 一律绑定 :model-value（非 v-model）：切 OO 前必须 config 拉取成功，switchMode 内才置 currentMode -->
        <el-segmented
          v-if="dualMode.isOoAvailable.value"
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <!-- OnlyOffice 状态：检测中 / 拉取成功（就绪）/ 仅结构化（对齐 D4「拉取成功才可以」） -->
        <el-tag v-if="dualMode.checking.value" size="small" type="warning">OnlyOffice 检测中…</el-tag>
        <el-tag
          v-else-if="dualMode.isOoAvailable.value && dualMode.currentMode.value === 'onlyoffice' && dualMode.ooConfig.value"
          size="small"
          type="success"
        >OnlyOffice 拉取成功 ✓</el-tag>
        <el-tag v-else-if="dualMode.isOoAvailable.value" size="small" type="success" effect="plain">OnlyOffice 就绪</el-tag>
        <el-tag v-else size="small" type="info">仅结构化视图</el-tag>
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
        <K13TabIndex
          v-if="currentSheet === 'K13'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K13-1 审定表（损益类！取发生额） -->
        <K13TabAdjudication
          v-else-if="currentSheet === 'K13-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :is-readonly="isReadonly"
          :prefill="adjudicationPrefill"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          :tb-source-codes="tbSourceCodes"
        />

        <!-- K13-2 明细表（26列3区段，27行） -->
        <K13TabDetail
          v-else-if="currentSheet === 'K13-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :year="props.year"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K13-3 调整分录 -->
        <K13TabAdjustment
          v-else-if="currentSheet === 'K13-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K13-4 营业外支出检查表 -->
        <K13TabNonOperatingCheck
          v-else-if="currentSheet === 'K13-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :year="props.year"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（上市） -->
        <K13TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <K13TabDisclosureSoe
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
 * GtK13NonOperatingExpense.vue — K13 营业外支出底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K13-{sheet}-{field}"
 *
 * 损益类科目（6711营业外支出）— 取发生额非余额！借方科目，借方=支出增加。
 *
 * Spec: .kiro/specs/k13-non-operating-expense/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, onMounted, onBeforeUnmount, inject, provide, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useChecklistPersistence } from '@/composables/workpaper/useChecklistPersistence'
import { collectChecklistResponses, toChecklistPatch } from '@/composables/workpaper/checklistPersistenceHelpers'
import {
  WorkpaperRuntimeContextKey,
  type WorkpaperRuntimeContext,
} from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useK13DualMode } from './composables/useK13DualMode'
// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core
const K13TabIndex = defineAsyncComponent(() => import('./k13/core/K13TabIndex.vue'))
const K13TabAdjudication = defineAsyncComponent(() => import('./k13/core/K13TabAdjudication.vue'))
const K13TabDetail = defineAsyncComponent(() => import('./k13/core/K13TabDetail.vue'))
const K13TabAdjustment = defineAsyncComponent(() => import('./k13/core/K13TabAdjustment.vue'))
const K13TabNonOperatingCheck = defineAsyncComponent(() => import('./k13/core/K13TabNonOperatingCheck.vue'))
const K13TabDisclosureListed = defineAsyncComponent(() => import('./k13/core/K13TabDisclosureListed.vue'))
const K13TabDisclosureSoe = defineAsyncComponent(() => import('./k13/core/K13TabDisclosureSoe.vue'))

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

// ─── 复核圆点（openReviewDialog 由 GtWpRenderer 运行时边界提供；此处仅补 dots） ──
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

const tbData = ref({
  /** 6711 未审发生额 */
  unadjusted6711: 0,
  /** 6711 审定发生额 */
  audited6711: 0,
})

/** tb_balance 6711 明细子科目预填（后端 render 输出 adjudication_prefill） */
const adjudicationPrefill = computed<Array<{ name: string; unadjustedDebit: number; unadjustedCredit: number }>>(() =>
  Array.isArray(props.htmlData?.adjudication_prefill) ? props.htmlData.adjudication_prefill : []
)

// ─── 双模式 (OO 健康检查 + el-segmented) ─────────────────────────────────────
const dualMode = useK13DualMode({
  wpId: computed(() => props.wpId) as any,
  projectId: computed(() => props.projectId || '') as any,
  sheetName: computed(() => props.sheetName || '') as any,
  reloadAll: async () => { await selfLoad() },
})

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (K13/K13A/K13-1~K13-4/附注)
 * 损益类底稿 — 审定取发生额非余额
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K13'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // K13A 程序表（走 a-program-console，不在此分发）
  if (/K13A/.test(name)) return ''
  // K13-N 编码（K13-1 到 K13-4）
  const m = name.match(/(K13-\d+)/)
  if (m) return m[1]
  // 底稿目录 K13（无后缀）
  if (/底稿目录/.test(name) || (/\bK13\b/.test(name) && !/K13-/.test(name) && !/K13A/.test(name))) return 'K13'
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
    console.warn(`[GtK13NonOperatingExpense] save failed: ${itemId}`, error)
  }
}

// ─── TB自动取数（6711营业外支出 — 损益类取发生额！借方=支出增加） ──────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '6711', year: props.year },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u6711 = 0, a6711 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('6711')) {
        u6711 += Number(item.unadjusted_amount ?? 0)
        a6711 += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value = { unadjusted6711: u6711, audited6711: a6711 }
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
    console.warn('[GtK13NonOperatingExpense] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onBeforeUnmount(() => { void persistence.flush().catch(() => undefined) })

onMounted(() => {
  void selfLoad()
  void _loadTbData()
})
</script>

<style scoped>
.k13-non-operating-expense {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.k13-header-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
