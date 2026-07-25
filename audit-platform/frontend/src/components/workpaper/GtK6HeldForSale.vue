<template>
  <div class="k6-held-for-sale">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet" class="k6-header-toolbar">
        <el-segmented
          v-if="dualMode.isOoAvailable.value"
          v-model="dualMode.currentMode.value"
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
        <K6TabIndex
          v-if="currentSheet === 'K6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K6A 程序表 (selfLoad) -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'K6A'"
          sheet-code="K6A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- K6-1 审定表（资产+负债双区块） -->
        <K6TabAdjudication
          v-else-if="currentSheet === 'K6-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K6-2 明细表 -->
        <K6TabDetail
          v-else-if="currentSheet === 'K6-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K6-3 调整分录 -->
        <K6TabAdjustment
          v-else-if="currentSheet === 'K6-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K6-4 初始确认检查表（CAS42五条件） -->
        <K6TabInitialRecognition
          v-else-if="currentSheet === 'K6-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K6-5 减值测试（孰低法） -->
        <K6TabImpairmentTest
          v-else-if="currentSheet === 'K6-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K6-6 处置组减值 -->
        <K6TabGroupImpairment
          v-else-if="currentSheet === 'K6-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K6-7 不再满足持有待售检查 -->
        <K6TabNoLongerCheck
          v-else-if="currentSheet === 'K6-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市公司） -->
        <K6TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <K6TabDisclosureSoe
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
 * GtK6HeldForSale.vue — K6 持有待售资产和负债底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K6-{sheet}-{field}"
 *
 * 科目：持有待售资产（借方/资产类）+ 持有待售负债（贷方/负债类）
 * 核心：CAS42五条件分类 + 减值孰低法 + 处置组减值分摊
 *       资产类期末=期初+增加-减少-减值
 *       负债类期末=期初+增加-减少
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
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
const K6TabIndex = defineAsyncComponent(() => import('./k6/core/K6TabIndex.vue'))
const K6TabAdjudication = defineAsyncComponent(() => import('./k6/core/K6TabAdjudication.vue'))
const K6TabDetail = defineAsyncComponent(() => import('./k6/core/K6TabDetail.vue'))
const K6TabAdjustment = defineAsyncComponent(() => import('./k6/core/K6TabAdjustment.vue'))
const K6TabDisclosureListed = defineAsyncComponent(() => import('./k6/core/K6TabDisclosureListed.vue'))
const K6TabDisclosureSoe = defineAsyncComponent(() => import('./k6/core/K6TabDisclosureSoe.vue'))

// impairment
const K6TabInitialRecognition = defineAsyncComponent(() => import('./k6/impairment/K6TabInitialRecognition.vue'))
const K6TabImpairmentTest = defineAsyncComponent(() => import('./k6/impairment/K6TabImpairmentTest.vue'))
const K6TabGroupImpairment = defineAsyncComponent(() => import('./k6/impairment/K6TabGroupImpairment.vue'))
const K6TabNoLongerCheck = defineAsyncComponent(() => import('./k6/impairment/K6TabNoLongerCheck.vue'))

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
  unadjustedAsset: 0,
  auditedAsset: 0,
  unadjustedLiability: 0,
  auditedLiability: 0,
})

// ─── 双模式 (OO 健康检查 + el-segmented + localStorage 持久化) ────────────────
const DUAL_MODE_STORAGE_PREFIX = 'k6-dual-mode:'

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
 * 从 sheetName 提取编码 (K6/K6A/K6-1~K6-7/附注)
 * 支持格式：
 *  - "底稿目录" → K6
 *  - "实质性程序表 K6A" → K6A
 *  - "审定表 K6-1" → K6-1
 *  - "明细表 K6-2" → K6-2
 *  - "调整分录汇总 K6-3" → K6-3
 *  - "初始确认检查表 K6-4" → K6-4
 *  - "减值测试 K6-5" → K6-5
 *  - "处置组减值 K6-6" → K6-6
 *  - "不再满足检查 K6-7" → K6-7
 *  - "附注披露信息（上市公司）" → 附注上市
 *  - "附注披露信息（国企）" → 附注国企
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K6'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 K6A
  if (/K6A/.test(name)) return 'K6A'
  // K6-N 编码（K6-1 到 K6-7）
  const m = name.match(/(K6-\d+)/)
  if (m) return m[1]
  // 底稿目录 K6（无后缀）
  if (/底稿目录/.test(name) || (/\bK6\b/.test(name) && !/K6-/.test(name) && !/K6A/.test(name))) return 'K6'
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
    console.warn(`[GtK6HeldForSale] save failed: ${itemId}`, error)
  }
}

// ─── TB回写（实际调 trial_balance writeback + EventBus）─────────────────────
/** 科目 1481 持有待售资产(借方) / 2605 持有待售负债(贷方) */
const ACCOUNT_CODE_ASSET = '1481'
const ACCOUNT_CODE_LIABILITY = '2605'

/**
 * writebackTB: 审定数回写 trial_balance 双科目 + 发布 substantive:adjudicated。
 * Requirement 2.6: WHEN 审定数变化时 SHALL 回写+发布。
 */
async function writebackTB(assetAudited: number, liabilityAudited: number): Promise<void> {
  if (!props.projectId) return
  try {
    await Promise.all([
      http.put(`/api/projects/${props.projectId}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_ASSET,
        audited_amount: assetAudited,
      }),
      http.put(`/api/projects/${props.projectId}/trial-balance/writeback`, {
        account_code: ACCOUNT_CODE_LIABILITY,
        audited_amount: liabilityAudited,
      }),
    ])

    // EventBus: substantive:adjudicated (资产)
    eventBus.emit('substantive:adjudicated', {
      accountCode: ACCOUNT_CODE_ASSET,
      auditedAmount: assetAudited,
      wpCode: 'K6',
      timestamp: Date.now(),
    })
    // EventBus: substantive:adjudicated (负债)
    eventBus.emit('substantive:adjudicated', {
      accountCode: ACCOUNT_CODE_LIABILITY,
      auditedAmount: liabilityAudited,
      wpCode: 'K6',
      timestamp: Date.now(),
    })

    // 同步本地 tbData
    tbData.value.auditedAsset = assetAudited
    tbData.value.auditedLiability = liabilityAudited
  } catch {
    // 失败静默（子组件处理提示）
  }
}

// ─── TB自动取数（持有待售资产+负债） ────────────────────────────────────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId || !props.year) return
  try {
    // 持有待售资产科目 1481
    const resAsset = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '1481', year: props.year },
      _silent: true,
    } as any)
    const listAsset: any[] = Array.isArray(resAsset?.data?.data ?? resAsset?.data) ? (resAsset?.data?.data ?? resAsset?.data) : []
    let uAsset = 0, aAsset = 0
    for (const item of listAsset) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('1481')) {
        uAsset += Number(item.unadjusted_amount ?? 0)
        aAsset += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value.unadjustedAsset = uAsset
    tbData.value.auditedAsset = aAsset

    // 持有待售负债科目 2605
    const resLiab = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '2605', year: props.year },
      _silent: true,
    } as any)
    const listLiab: any[] = Array.isArray(resLiab?.data?.data ?? resLiab?.data) ? (resLiab?.data?.data ?? resLiab?.data) : []
    let uLiab = 0, aLiab = 0
    for (const item of listLiab) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('2605')) {
        uLiab += Math.abs(Number(item.unadjusted_amount ?? 0))
        aLiab += Math.abs(Number(item.audited_amount ?? 0))
      }
    }
    tbData.value.unadjustedLiability = uLiab
    tbData.value.auditedLiability = aLiab
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
    console.warn('[GtK6HeldForSale] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── provide for child components ────────────────────────────────────────────
// 复核对话由 Runtime Boundary（GtWpRenderer + GtWorkpaperRuntimeHosts）统一 provide/挂载；
// 此处仅保留 K6 业务专属的审定回写 provide。
provide('k6WritebackTB', writebackTB)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onBeforeUnmount(() => { void persistence.flush().catch(() => undefined) })

onMounted(() => {
  void selfLoad()
  void _loadTbData()
})
</script>

<style scoped>
.k6-held-for-sale {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.k6-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
