<template>
  <div class="k4-other-current-liabilities">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'K4'" class="k4-header-toolbar">
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
        <!-- 全局告警区（非目录/程序表页显示） -->
        <div v-if="currentSheet !== 'K4' && currentSheet !== 'K4A' && globalAlerts.length > 0" class="k4-global-alerts">
          <el-alert
            v-for="(alert, aIdx) in globalAlerts"
            :key="aIdx"
            :type="alert.type"
            :closable="false"
            show-icon
            style="margin-bottom:6px"
          >
            <template #title>{{ alert.message }}</template>
          </el-alert>
        </div>

        <!-- 底稿目录 -->
        <K4TabIndex
          v-if="currentSheet === 'K4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K4A 程序表 (selfLoad) -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'K4A'"
          sheet-code="K4A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- K4-1 审定表 -->
        <K4TabAdjudication
          v-else-if="currentSheet === 'K4-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K4-2 明细表 -->
        <K4TabDetail
          v-else-if="currentSheet === 'K4-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K4-3 调整分录 -->
        <K4TabAdjustment
          v-else-if="currentSheet === 'K4-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K4-4 检查表（凭证级测试，K1-12 范式） -->
        <K4TabCheck
          v-else-if="currentSheet === 'K4-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市公司） -->
        <K4TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <K4TabDisclosureSoe
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
 * GtK4OtherCurrentLiabilities.vue — K4 其他流动负债底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K4-{sheet}-{field}"
 *
 * 科目：2245其他流动负债（贷方/负债类）
 * 核心：期末=期初+贷方-借方（负债类！方向与资产类相反）
 *       完整性认定为主
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, onMounted, onBeforeUnmount, inject, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
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
const K4TabIndex = defineAsyncComponent(() => import('./k4/core/K4TabIndex.vue'))
const K4TabAdjudication = defineAsyncComponent(() => import('./k4/core/K4TabAdjudication.vue'))
const K4TabDetail = defineAsyncComponent(() => import('./k4/core/K4TabDetail.vue'))
const K4TabAdjustment = defineAsyncComponent(() => import('./k4/core/K4TabAdjustment.vue'))
const K4TabCheck = defineAsyncComponent(() => import('./k4/core/K4TabCheck.vue'))
const K4TabDisclosureListed = defineAsyncComponent(() => import('./k4/core/K4TabDisclosureListed.vue'))
const K4TabDisclosureSoe = defineAsyncComponent(() => import('./k4/core/K4TabDisclosureSoe.vue'))

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
  unadjusted2245: 0,
  audited2245: 0,
})

// ─── 全局告警区（跨sheet汇总） ──────────────────────────────────────────────
const globalAlerts = computed(() => {
  const alerts: Array<{ type: 'warning' | 'error' | 'info' | 'success'; message: string }> = []

  // K4-1 审定合计 vs TB(2245)
  const k41Audited = getResponseNum('K4-1-audited-total')
  if (k41Audited > 0 && tbData.value.audited2245 > 0) {
    const diff = Math.abs(k41Audited - tbData.value.audited2245)
    if (diff > 1) {
      alerts.push({ type: 'warning', message: `K4-1 审定合计（${fmtAmtGlobal(k41Audited)}）与 TB 2245 审定数（${fmtAmtGlobal(tbData.value.audited2245)}）差异 ${fmtAmtGlobal(diff)} 元` })
    }
  }

  // K4-2 明细合计 vs K4-1 审定合计
  const k42Total = getResponseNum('K4-2-detail-total')
  if (k42Total > 0 && k41Audited > 0) {
    const diff2 = Math.abs(k41Audited - k42Total)
    if (diff2 > 1) {
      alerts.push({ type: 'warning', message: `K4-2 明细审定合计（${fmtAmtGlobal(k42Total)}）与 K4-1 审定合计（${fmtAmtGlobal(k41Audited)}）差异 ${fmtAmtGlobal(diff2)} 元` })
    }
  }

  return alerts
})

function getResponseNum(key: string): number {
  const item = allResponses.value.get(key)
  const v = item?.remark ?? item?.value ?? item
  return Number(v) || 0
}

function fmtAmtGlobal(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 双模式 (OO 健康检查 + el-segmented + localStorage 持久化) ────────────────
const DUAL_MODE_STORAGE_PREFIX = 'k4-dual-mode:'

const dualMode = (() => {
  const currentMode = ref<'html' | 'onlyoffice'>('html')
  const isOoAvailable = ref(false)
  const checking = ref(true)
  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  // localStorage 持久化 (per wpId)
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

  // 启动时恢复持久化模式 + 检查 OO 可用性
  loadPersistedMode()
  checkOoHealth()

  return { currentMode, isOoAvailable, checking, modeOptions, onModeChange }
})()

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (K4/K4A/K4-1~K4-4/附注)
 * 支持格式：
 *  - "底稿目录" → K4
 *  - "实质性程序表 K4A" → K4A
 *  - "审定表 K4-1" → K4-1
 *  - "明细表 K4-2" → K4-2
 *  - "调整分录汇总 K4-3" → K4-3
 *  - "其他流动负债检查表 K4-4" → K4-4
 *  - "附注披露信息（上市公司）" → 附注上市
 *  - "附注披露信息（国企）" → 附注国企
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K4'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 K4A
  if (/K4A/.test(name)) return 'K4A'
  // K4-N 编码（K4-1 到 K4-4）
  const m = name.match(/(K4-\d+)/)
  if (m) return m[1]
  // 底稿目录 K4（无后缀）
  if (/底稿目录/.test(name) || (/\bK4\b/.test(name) && !/K4-/.test(name) && !/K4A/.test(name))) return 'K4'
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
    console.warn(`[GtK4OtherCurrentLiabilities] save failed: ${itemId}`, error)
  }
}

// ─── TB自动取数（2245其他流动负债） ─────────────────────────────────────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '2245', year: props.year },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u2245 = 0, a2245 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('2245')) {
        u2245 += Number(item.unadjusted_amount ?? 0)
        a2245 += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value.unadjusted2245 = u2245
    tbData.value.audited2245 = a2245
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
    console.warn('[GtK4OtherCurrentLiabilities] selfLoad failed:', err)
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
.k4-other-current-liabilities {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.k4-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.k4-global-alerts {
  padding: 8px 16px 0;
}
</style>
