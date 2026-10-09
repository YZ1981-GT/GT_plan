<template>
  <div class="k3-other-payables">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'K3'" class="k3-header-toolbar">
        <el-segmented
          v-if="dualMode.isOoAvailable.value"
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-k3-other-payables" />
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
        <!-- 全局跨sheet勾稽告警 -->
        <div v-if="globalAlerts.length > 0" class="k3-global-alerts">
          <el-alert
            v-for="(a, i) in globalAlerts"
            :key="i"
            :type="a.type"
            :closable="false"
            show-icon
            :title="a.text"
          />
        </div>

        <!-- 底稿目录 -->
        <K3TabIndex
          v-if="currentSheet === 'K3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K3A 程序表 (selfLoad) -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'K3A'"
          sheet-code="K3A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- K3-1 审定表 -->
        <K3TabAdjudication
          v-else-if="currentSheet === 'K3-1'"
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

        <!-- K3-2 明细表 -->
        <K3TabDetail
          v-else-if="currentSheet === 'K3-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K3-3 调整分录 -->
        <K3TabAdjustment
          v-else-if="currentSheet === 'K3-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K3-4 大额其他应付款分析 -->
        <K3TabLargeAmount
          v-else-if="currentSheet === 'K3-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K3-5 长期挂账检查 -->
        <K3TabLongOutstanding
          v-else-if="currentSheet === 'K3-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K3-6 关联方及交易检查 -->
        <K3TabRelatedParty
          v-else-if="currentSheet === 'K3-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K3-7 其他应付款检查（含反向截止） -->
        <K3TabPayableCheck
          v-else-if="currentSheet === 'K3-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市公司） -->
        <K3TabDisclosureListed
          :applicable-standards="applicableStandards"
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <K3TabDisclosureSoe
          :applicable-standards="applicableStandards"
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
 * GtK3OtherPayables.vue — K3 其他应付款底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K3-{sheet}-{field}"
 *
 * 科目：2241其他应付款（贷方/负债类）
 * 核心：期末=期初+贷方-借方（负债类！方向与资产类相反）
 *       完整性认定为主 + 反向截止测试
 *
 * Spec: .kiro/specs/k3-other-payables/ Task 1.1
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
import { useK3CrossSheet } from './composables/useK3CrossSheet'
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
import { fetchOnlyOfficeHealthy } from './sync/onlyOfficeHealth'
import {
  migrateWorkpaperSyncMode,
  workpaperSyncModeKey,
  type WorkpaperSyncStoredMode,
} from './sync/workpaperSyncModeStorage'
import { useHostApplicableStandards } from './composables/hostApplicableStandards'
// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core
const K3TabIndex = defineAsyncComponent(() => import('./k3/core/K3TabIndex.vue'))
const K3TabAdjudication = defineAsyncComponent(() => import('./k3/core/K3TabAdjudication.vue'))
const K3TabDetail = defineAsyncComponent(() => import('./k3/core/K3TabDetail.vue'))
const K3TabAdjustment = defineAsyncComponent(() => import('./k3/core/K3TabAdjustment.vue'))
const K3TabDisclosureListed = defineAsyncComponent(() => import('./k3/core/K3TabDisclosureListed.vue'))
const K3TabDisclosureSoe = defineAsyncComponent(() => import('./k3/core/K3TabDisclosureSoe.vue'))

// inspection
const K3TabLargeAmount = defineAsyncComponent(() => import('./k3/inspection/K3TabLargeAmount.vue'))
const K3TabLongOutstanding = defineAsyncComponent(() => import('./k3/inspection/K3TabLongOutstanding.vue'))
const K3TabRelatedParty = defineAsyncComponent(() => import('./k3/inspection/K3TabRelatedParty.vue'))
const K3TabPayableCheck = defineAsyncComponent(() => import('./k3/inspection/K3TabPayableCheck.vue'))

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
const applicableStandards = useHostApplicableStandards({ htmlData: () => props.htmlData })
const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed<string | undefined>(() => props.projectId || undefined)
const persistence = useChecklistPersistence({ wpId: wpIdRef, projectId: projectIdRef })
const allResponses = persistence.responses
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const tbData = ref({
  unadjusted2241: 0,
  audited2241: 0,
})

/** K3-1 审定表明细子科目预填（来自后端 render adjudication_prefill） */
const adjudicationPrefill = computed(() =>
  Array.isArray(props.htmlData?.adjudication_prefill) ? props.htmlData.adjudication_prefill : []
)

/** 四表取数溯源（render 下发，供审定表 Tab 展示来源科目与报表行） */
const tbSourceCodes = computed(() => props.htmlData?.tb_source_codes ?? null)


// ─── 跨sheet勾稽引擎（全局告警banner消费） ────────────────────────────────────
const { adjudicationVsDetail, longOutstandingVsDetail, largeAmountVsDetail } = useK3CrossSheet(allResponses)

/** 全局勾稽告警（在非当前编辑源sheet显示，避免与sheet内告警重复） */
const globalAlerts = computed(() => {
  const alerts: Array<{ type: 'warning' | 'info'; text: string }> = []
  const sheet = currentSheet.value
  // ① K3-1审定 vs K3-2明细（在K3-1/K3-2页内已有各自告警，此处排除避免重复）
  if (sheet !== 'K3-1' && sheet !== 'K3-2') {
    const av = adjudicationVsDetail.value
    if (!av.isMatch && (Math.abs(av.diff) > 0.01)) {
      alerts.push({ type: 'warning', text: `K3-1审定合计与K3-2明细合计差异 ${fmtCny(av.diff)}，请核对` })
    }
  }
  // ② 3年以上长期挂账（在K3-5页内已有告警，此处排除）
  if (sheet !== 'K3-5' && longOutstandingVsDetail.value.count > 0) {
    alerts.push({ type: 'info', text: `K3-2明细中3年以上长期挂账 ${longOutstandingVsDetail.value.count} 笔，合计 ${fmtCny(longOutstandingVsDetail.value.total)}，请确认K3-5已覆盖评估` })
  }
  // ③ 大额款项（在K3-4页内已有阈值提示，此处排除）
  if (sheet !== 'K3-4' && largeAmountVsDetail.value.count > 0) {
    alerts.push({ type: 'info', text: `K3-2明细中大额款项 ${largeAmountVsDetail.value.count} 笔，合计 ${fmtCny(largeAmountVsDetail.value.total)}，请确认K3-4已覆盖分析` })
  }
  return alerts
})

function fmtCny(v: number): string {
  return (v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 双模式 (OO 健康检查 + el-segmented) ────────────────────────────────────
/** K3 的 entry_id（统一模式键的第一段）。 */
const K3_ENTRY_ID = 'xlsx/gt-k3-other-payables'

/** 本宿主模式 ↔ 统一真源值域（`'html' | 'oo'`）的双向映射。 */
function toStoredMode(mode: 'html' | 'onlyoffice'): WorkpaperSyncStoredMode {
  return mode === 'onlyoffice' ? 'oo' : 'html'
}

function fromStoredMode(stored: string | null): 'html' | 'onlyoffice' | null {
  if (stored === 'oo') return 'onlyoffice'
  if (stored === 'html') return 'html'
  return null
}

const dualMode = (() => {
  const currentMode = ref<'html' | 'onlyoffice'>('html')
  const isOoAvailable = ref(false)
  const checking = ref(true)
  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  /** 统一模式键（三段全需；sheetKey 缺省 `default`）。 */
  function modeKey(): string {
    return workpaperSyncModeKey({
      entryId: K3_ENTRY_ID,
      wpId: props.wpId,
      sheetKey: currentSheet.value || undefined,
    })
  }

  /**
   * 迁移旧键 + 读回模式。
   *
   * 🔴 本宿主**原先没有持久化** —— 模式每次刷新都回落 'html'。本轮统一目标态为
   * 「都持久化」（与 K4/K5/K6 及 BP-6 组的 6 条一致）⇒ 这里是**新增**能力。
   * `migrateWorkpaperSyncMode` 对本 entry 无旧键可迁，调用是幂等空操作，
   * 留着是防御：用户浏览器里可能有更早版本遗留的键形态。
   */
  function loadPersistedMode(): void {
    try {
        // 🔴 capability 传 `'bidirectional'`：表达的是「本宿主的视图开关两侧都能开」
        //    （结构化视图 = 本地渲染 / OO = 在线编辑），与 entry 的写回 capability
        //    （`single_onlyoffice`）不是一回事。传后者会让 migrate 把存量 'html' 偏好
        //    回落成 'oo' 并落盘 ⇒ 老用户下次打开被强推进 OO。
        //    🔴 曾误传 `'dual'`（不在封闭域里）⇒ migrate 抛 mode_capability_unknown，
        //    被外层 catch 吞掉，连带下面读统一键那两行从未执行 ⇒ 偏好恢复整体失效。
      migrateWorkpaperSyncMode(
        { entryId: K3_ENTRY_ID, wpId: props.wpId, sheetKey: currentSheet.value || undefined },
        'bidirectional',
      )
      const stored = fromStoredMode(localStorage.getItem(modeKey()))
      if (stored) currentMode.value = stored
    } catch { /* ignore */ }
  }

  function persistMode(mode: 'html' | 'onlyoffice'): void {
    try {
      localStorage.setItem(modeKey(), toStoredMode(mode))
    } catch { /* ignore */ }
  }

  async function checkOoHealth(): Promise<void> {
    try {
      isOoAvailable.value = await fetchOnlyOfficeHealthy()
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

  // 启动时检查 OO 可用性
  loadPersistedMode()
  checkOoHealth()

  return { currentMode, isOoAvailable, checking, modeOptions, onModeChange }
})()

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (K3/K3A/K3-1~K3-7/附注)
 * 支持格式：
 *  - "底稿目录" → K3
 *  - "实质性程序表K3A" → K3A
 *  - "审定表K3-1" → K3-1
 *  - "明细表K3-2" → K3-2
 *  - "调整分录汇总K3-3" → K3-3
 *  - "大额其他应付款情况分析表K3-4" → K3-4
 *  - "长期挂账检查表K3-5" → K3-5
 *  - "关联方及交易检查表K3-6" → K3-6
 *  - "其他应付款检查表K3-7" → K3-7
 *  - "附注披露信息(上市公司)" → 附注上市
 *  - "附注披露信息(国企)" → 附注国企
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K3'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 K3A
  if (/K3A/.test(name)) return 'K3A'
  // K3-N 编码（K3-1 到 K3-7）
  const m = name.match(/(K3-\d+)/)
  if (m) return m[1]
  // 底稿目录 K3（无后缀）
  if (/底稿目录/.test(name) || (/\bK3\b/.test(name) && !/K3-/.test(name) && !/K3A/.test(name))) return 'K3'
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
    console.warn(`[GtK3OtherPayables] save failed: ${itemId}`, error)
  }
}

// ─── TB自动取数（2241其他应付款） ─────────────────────────────────────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '2241', year: props.year },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u2241 = 0, a2241 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('2241')) {
        u2241 += Number(item.unadjusted_amount ?? 0)
        a2241 += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value.unadjusted2241 = u2241
    tbData.value.audited2241 = a2241
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
    console.warn('[GtK3OtherPayables] selfLoad failed:', err)
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
.k3-other-payables {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.k3-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.k3-global-alerts {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 16px 0;
}
</style>
