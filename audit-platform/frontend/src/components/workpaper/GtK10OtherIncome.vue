<template>
  <div class="k10-other-income">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'K10'" class="k10-header-toolbar">
        <!-- 一向绑定 :model-value（非 v-model）：切 OO 前必须 config 拉取成功，switchMode 内才置 currentMode -->
        <el-segmented
          v-if="dualMode.isOoAvailable.value"
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <!-- OnlyOffice 状态：检测中 / 拉取成功（就绪）/ 仅结构化 -->
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
        <K10TabIndex
          v-if="currentSheet === 'K10'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K10-1 审定表（损益类！取发生额） -->
        <K10TabAdjudication
          v-else-if="currentSheet === 'K10-1'"
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

        <!-- K10-2 明细表（12列，43行） -->
        <K10TabDetail
          v-else-if="currentSheet === 'K10-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K10-3 调整分录 -->
        <K10TabAdjustment
          v-else-if="currentSheet === 'K10-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K10-4 政府补助核对表 -->
        <K10TabGrantReconcile
          v-else-if="currentSheet === 'K10-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K10-5 应收政府补助检查表 -->
        <K10TabReceivableGrant
          v-else-if="currentSheet === 'K10-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K10-6 其他收益检查表 -->
        <K10TabOtherIncomeCheck
          v-else-if="currentSheet === 'K10-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :year="k10Year"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（上市） -->
        <K10TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <K10TabDisclosureSoe
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
 * GtK10OtherIncome.vue — K10 其他收益底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K10-{sheet}-{field}"
 *
 * 损益类科目（6117其他收益）— 取发生额非余额！贷方科目，贷方=收益增加。
 *
 * Spec: .kiro/specs/k10-other-income/ Task 1.1
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
import { useK10DualMode } from './composables/useK10DualMode'
// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core
const K10TabIndex = defineAsyncComponent(() => import('./k10/core/K10TabIndex.vue'))
const K10TabAdjudication = defineAsyncComponent(() => import('./k10/core/K10TabAdjudication.vue'))
const K10TabDetail = defineAsyncComponent(() => import('./k10/core/K10TabDetail.vue'))
const K10TabAdjustment = defineAsyncComponent(() => import('./k10/core/K10TabAdjustment.vue'))
const K10TabDisclosureListed = defineAsyncComponent(() => import('./k10/core/K10TabDisclosureListed.vue'))
const K10TabDisclosureSoe = defineAsyncComponent(() => import('./k10/core/K10TabDisclosureSoe.vue'))

// inspection
const K10TabGrantReconcile = defineAsyncComponent(() => import('./k10/inspection/K10TabGrantReconcile.vue'))
const K10TabReceivableGrant = defineAsyncComponent(() => import('./k10/inspection/K10TabReceivableGrant.vue'))
const K10TabOtherIncomeCheck = defineAsyncComponent(() => import('./k10/inspection/K10TabOtherIncomeCheck.vue'))

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

// 导入后子表可调此刷新 allResponses（重新拉取 checklist_responses）
provide('k10ReloadResponses', async () => { await persistence.load() })
const tbData = ref({
  /** 6117 未审发生额 */
  unadjusted6117: 0,
  /** 6117 审定发生额 */
  audited6117: 0,
})

/** tb_balance 6117 明细子科目预填（后端 render 输出 adjudication_prefill） */
const adjudicationPrefill = computed<Array<{ name: string; unadjustedDebit: number; unadjustedCredit: number }>>(() =>
  Array.isArray(props.htmlData?.adjudication_prefill) ? props.htmlData.adjudication_prefill : []
)

// ─── 年度（供 K10-6 抽凭引擎等使用；props.year → sheet/项目回退当前年） ──────
const k10Year = computed<number>(() => {
  if (props.year) return props.year
  const y = Number(String(props.sheetName || '').match(/20\d{2}/)?.[0])
  return Number.isFinite(y) && y > 0 ? y : new Date().getFullYear()
})

// ─── 双模式 (OO 健康检查 + config 拉取成功才切；D4 范式) ───────────────────────
const dualMode = useK10DualMode({
  wpId: computed(() => props.wpId) as any,
  projectId: computed(() => props.projectId || '') as any,
  sheetName: computed(() => props.sheetName || '') as any,
  reloadAll: async () => { await selfLoad() },
})

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (K10/K10A/K10-1~K10-6/附注)
 * 损益类底稿 — 审定取发生额非余额
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K10'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // K10A 程序表（走 a-program-console，不在此分发）
  if (/K10A/.test(name)) return ''
  // K10-N 编码（K10-1 到 K10-6）
  const m = name.match(/(K10-\d+)/)
  if (m) return m[1]
  // 底稿目录 K10（无后缀）
  if (/底稿目录/.test(name) || (/\bK10\b/.test(name) && !/K10-/.test(name) && !/K10A/.test(name))) return 'K10'
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
    console.warn(`[GtK10OtherIncome] save failed: ${itemId}`, error)
  }
}

// ─── TB自动取数（6117其他收益 — 损益类取发生额！贷方=收益增加） ──────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '6117', year: props.year },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u6117 = 0, a6117 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('6117')) {
        u6117 += Number(item.unadjusted_amount ?? 0)
        a6117 += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value = { unadjusted6117: u6117, audited6117: a6117 }
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
    console.warn('[GtK10OtherIncome] selfLoad failed:', err)
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
.k10-other-income {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.k10-header-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
