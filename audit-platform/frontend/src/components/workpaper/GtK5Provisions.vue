<template>
  <div class="k5-provisions">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'K5'" class="k5-header-toolbar">
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
        <K5TabIndex
          v-if="currentSheet === 'K5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K5A 程序表 (selfLoad) -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'K5A'"
          sheet-code="K5A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- K5-1 审定表 -->
        <K5TabAdjudication
          v-else-if="currentSheet === 'K5-1'"
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

        <!-- K5-2 明细表 -->
        <K5TabDetail
          v-else-if="currentSheet === 'K5-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          @imported="selfLoad()"
        />

        <!-- K5-3 调整分录 -->
        <K5TabAdjustment
          v-else-if="currentSheet === 'K5-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          @imported="selfLoad()"
        />

        <!-- K5-4 产品质量保修检查 -->
        <K5TabWarrantyCheck
          v-else-if="currentSheet === 'K5-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K5-5 弃置费用检查 -->
        <K5TabDecommissionCheck
          v-else-if="currentSheet === 'K5-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K5-6 未决诉讼检查 -->
        <K5TabLitigationCheck
          v-else-if="currentSheet === 'K5-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K5-7 预计负债检查表（凭证级测试，K1-12 范式） -->
        <K5TabProvisionCheck
          v-else-if="currentSheet === 'K5-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市公司） -->
        <K5TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <K5TabDisclosureSoe
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
 * GtK5Provisions.vue — K5 预计负债底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K5-{sheet}-{field}"
 *
 * 科目：2701预计负债（贷方/负债类）
 * 核心：期末=期初+计提-转销（负债类！方向与资产类相反）
 *       或有事项三级可能性判断（CAS13）
 *       最佳估计数引擎（单值/区间中值/期望值加权）
 *
 * Spec: .kiro/specs/k5-provisions/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, inject, onMounted, defineAsyncComponent, toRef, provide } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { k5QueryCodes } from './composables/k5AccountScope'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useChecklistPersistence } from '@/composables/workpaper/useChecklistPersistence'
import {
  WorkpaperRuntimeContextKey,
  type WorkpaperRuntimeContext,
} from './composables/useWorkpaperScaffold'
import { collectK5Responses, toK5PersistencePatch } from './k5/k5Persistence'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core
const K5TabIndex = defineAsyncComponent(() => import('./k5/core/K5TabIndex.vue'))
const K5TabAdjudication = defineAsyncComponent(() => import('./k5/core/K5TabAdjudication.vue'))
const K5TabDetail = defineAsyncComponent(() => import('./k5/core/K5TabDetail.vue'))
const K5TabAdjustment = defineAsyncComponent(() => import('./k5/core/K5TabAdjustment.vue'))
const K5TabDisclosureListed = defineAsyncComponent(() => import('./k5/core/K5TabDisclosureListed.vue'))
const K5TabDisclosureSoe = defineAsyncComponent(() => import('./k5/core/K5TabDisclosureSoe.vue'))

// contingency
const K5TabWarrantyCheck = defineAsyncComponent(() => import('./k5/contingency/K5TabWarrantyCheck.vue'))
const K5TabDecommissionCheck = defineAsyncComponent(() => import('./k5/contingency/K5TabDecommissionCheck.vue'))
const K5TabLitigationCheck = defineAsyncComponent(() => import('./k5/contingency/K5TabLitigationCheck.vue'))
const K5TabProvisionCheck = defineAsyncComponent(() => import('./k5/contingency/K5TabProvisionCheck.vue'))

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
const persistence = useChecklistPersistence({
  wpId: wpIdRef,
  projectId: projectIdRef,
})
const allResponses = persistence.responses
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const tbData = ref({
  unadjusted: 0,
  audited: 0,
})

/** K5-1 审定表明细子科目预填（来自后端 render adjudication_prefill） */
const adjudicationPrefill = computed(() =>
  Array.isArray(props.htmlData?.adjudication_prefill) ? props.htmlData.adjudication_prefill : []
)

// ─── 双模式 (OO 健康检查 + el-segmented + localStorage 持久化) ────────────────
const DUAL_MODE_STORAGE_PREFIX = 'k5-dual-mode:'

const dualMode = (() => {
  const currentMode = ref<'html' | 'onlyoffice'>('html')
  const isOoAvailable = ref(false)
  const checking = ref(true)
  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  function loadPersistedMode(): void {
    try {
      const saved = localStorage.getItem(DUAL_MODE_STORAGE_PREFIX + props.wpId)
      if (saved === 'html' || saved === 'onlyoffice') currentMode.value = saved
    } catch { /* ignore */ }
  }

  function persistMode(mode: 'html' | 'onlyoffice'): void {
    try {
      localStorage.setItem(DUAL_MODE_STORAGE_PREFIX + props.wpId, mode)
    } catch { /* ignore */ }
  }

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
    persistMode(currentMode.value)
  }

  loadPersistedMode()
  checkOoHealth()

  return { currentMode, isOoAvailable, checking, modeOptions, onModeChange }
})()

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (K5/K5A/K5-1~K5-7/附注)
 * 支持格式：
 *  - "底稿目录" → K5
 *  - "实质性程序表 K5A" → K5A
 *  - "审定表 K5-1" → K5-1
 *  - "明细表 K5-2" → K5-2
 *  - "调整分录汇总 K5-3" → K5-3
 *  - "产品质量保修检查表 K5-4" → K5-4
 *  - "弃置费用检查表 K5-5" → K5-5
 *  - "未决诉讼检查表 K5-6" → K5-6
 *  - "预计负债检查表 K5-7" → K5-7
 *  - "附注披露信息（上市公司）" → 附注上市
 *  - "附注披露信息（国企）" → 附注国企
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K5'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 K5A
  if (/K5A/.test(name)) return 'K5A'
  // K5-N 编码（K5-1 到 K5-7）
  const m = name.match(/(K5-\d+)/)
  if (m) return m[1]
  // 底稿目录 K5（无后缀）
  if (/底稿目录/.test(name) || (/\bK5\b/.test(name) && !/K5-/.test(name) && !/K5A/.test(name))) return 'K5'
  return ''
})

// ─── 子组件 save 回调（统一 Persistence Adapter） ─────────────────────────────
async function handleChildSave(itemId: string, value: unknown): Promise<void> {
  if (!props.wpId) return
  try {
    await persistence.save(itemId, toK5PersistencePatch(value))
    runtime?.version.scheduleAutoSnapshot()
    emit('save')
  } catch (error) {
    ElMessage.error(persistence.stateOf(itemId).lastError || '保存失败，数据已保留在本地，请稍后重试')
    console.warn(`[GtK5Provisions] save failed: ${itemId}`, error)
  }
}

// ─── TB自动取数（预计负债） ────────────────────────────────────────────────────
/**
 * 🔴 科目码取自 `k5AccountScope`（报表行 **BS-065**，两准则同号，兜底 2801）。
 *    旧注释写 BS-068/BS-094 已于 2026-08-09 按 report_config 连库对账改正：
 *    BS-068 实为**其他非流动负债**（L7 的行，`TB('2911')` 且 2911 全库零命中）、
 *    BS-094 名对但 formula 为 NULL（后果 TRACE_ONLY：退兜底 2801，金额对、溯源失真）。
 * 历史实现写死 `2701` = 长期应付款（L5 科目）→ 取到别的循环的余额当预计负债显示。
 *
 * render 已下发 `tb_values.provisions_*`，本函数只在 seed 缺失时兜底请求。
 */
/** 四表取数溯源 */
const tbSourceCodes = computed(() => (props.htmlData as any)?.tb_source_codes ?? null)

async function _loadTbData(): Promise<void> {
  if (!props.projectId) return

  const seededUnadj = (props.htmlData as any)?.tb_values?.provisions_unadjusted
  if (seededUnadj != null) {
    tbData.value.unadjusted = Number(seededUnadj) || 0
    tbData.value.audited = Number((props.htmlData as any)?.tb_values?.provisions_audited ?? 0) || 0
    return
  }

  const codes = k5QueryCodes((props.htmlData as any)?.tb_source_codes)
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: codes[0], year: props.year },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let uProvision = 0, aProvision = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (!codes.some((c) => code === c || code.startsWith(c))) continue
      uProvision += Number(item.unadjusted_amount ?? 0)
      aProvision += Number(item.audited_amount ?? 0)
    }
    tbData.value.unadjusted = uProvision
    tbData.value.audited = aProvision
  } catch {
    // TB取数失败静默处理
  }
}

// ─── selfLoad ────────────────────────────────────────────────────────────────
async function selfLoad(): Promise<void> {
  try {
    const snapshot = props.htmlData
      ? collectK5Responses(
          props.htmlData.responses_snapshot,
          props.htmlData.allResponses,
          props.htmlData.checklist_responses,
        )
      : []

    if (snapshot.length > 0) {
      persistence.hydrate(snapshot)
    } else {
      await persistence.load()
    }
  } catch (error) {
    console.warn('[GtK5Provisions] selfLoad failed:', error)
  } finally {
    isLoading.value = false
  }
}

// 复核圆点
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  void selfLoad()
  void _loadTbData()
})
</script>

<style scoped>
.k5-provisions {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.k5-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
