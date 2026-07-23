<template>
  <div class="k12-non-operating-income">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet" class="k12-header-toolbar">
        <!-- 一律绑定 :model-value（非 v-model）：切 OO 前必须 config 拉取成功，switchMode 内才置 currentMode -->
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
          v-else-if="dualMode.currentMode.value === 'onlyoffice' && dualMode.ooConfig.value"
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
        <K12TabIndex
          v-if="currentSheet === 'K12'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K12-1 审定表（损益类！取发生额） -->
        <K12TabAdjudication
          v-else-if="currentSheet === 'K12-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K12-2 明细表（26列3区段，27行） -->
        <K12TabDetail
          v-else-if="currentSheet === 'K12-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K12-3 调整分录 -->
        <K12TabAdjustment
          v-else-if="currentSheet === 'K12-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K12-4 营业外收入检查表 -->
        <K12TabNonOperatingCheck
          v-else-if="currentSheet === 'K12-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :year="props.year"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（上市） -->
        <K12TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <K12TabDisclosureSoe
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
 * GtK12NonOperatingIncome.vue — K12 营业外收入底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K12-{sheet}-{field}"
 *
 * 损益类科目（6301营业外收入）— 取发生额非余额！贷方科目，贷方=收入增加。
 *
 * Spec: .kiro/specs/k12-non-operating-income/ Task 1.1
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
import { useK12DualMode } from './composables/useK12DualMode'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core
const K12TabIndex = defineAsyncComponent(() => import('./k12/core/K12TabIndex.vue'))
const K12TabAdjudication = defineAsyncComponent(() => import('./k12/core/K12TabAdjudication.vue'))
const K12TabDetail = defineAsyncComponent(() => import('./k12/core/K12TabDetail.vue'))
const K12TabAdjustment = defineAsyncComponent(() => import('./k12/core/K12TabAdjustment.vue'))
const K12TabNonOperatingCheck = defineAsyncComponent(() => import('./k12/core/K12TabNonOperatingCheck.vue'))
const K12TabDisclosureListed = defineAsyncComponent(() => import('./k12/core/K12TabDisclosureListed.vue'))
const K12TabDisclosureSoe = defineAsyncComponent(() => import('./k12/core/K12TabDisclosureSoe.vue'))

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
  /** 6301 未审发生额 */
  unadjusted6301: 0,
  /** 6301 审定发生额 */
  audited6301: 0,
})

// ─── 双模式 (OO 健康检查 + el-segmented) ─────────────────────────────────────
const dualMode = useK12DualMode({
  wpId: computed(() => props.wpId) as any,
  projectId: computed(() => props.projectId || '') as any,
  sheetName: computed(() => props.sheetName || '') as any,
  reloadAll: async () => { await selfLoad() },
})

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (K12/K12A/K12-1~K12-4/附注)
 * 损益类底稿 — 审定取发生额非余额
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K12'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // K12A 程序表（走 a-program-console，不在此分发）
  if (/K12A/.test(name)) return ''
  // K12-N 编码（K12-1 到 K12-4）
  const m = name.match(/(K12-\d+)/)
  if (m) return m[1]
  // 底稿目录 K12（无后缀）
  if (/底稿目录/.test(name) || (/\bK12\b/.test(name) && !/K12-/.test(name) && !/K12A/.test(name))) return 'K12'
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
    console.warn(`[GtK12NonOperatingIncome] save failed: ${itemId}`, error)
  }
}

// ─── TB自动取数（6301营业外收入 — 损益类取发生额！贷方=收入增加） ──────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '6301', year: props.year },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u6301 = 0, a6301 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('6301')) {
        u6301 += Number(item.unadjusted_amount ?? 0)
        a6301 += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value = { unadjusted6301: u6301, audited6301: a6301 }
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
    console.warn('[GtK12NonOperatingIncome] selfLoad failed:', err)
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
.k12-non-operating-income {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.k12-header-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
