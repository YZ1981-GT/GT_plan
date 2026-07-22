<template>
  <div class="k11-asset-impairment-loss">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet" class="k11-header-toolbar">
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
        <K11TabIndex
          v-if="currentSheet === 'K11'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K11-1 审定表（损益类！取发生额） -->
        <K11TabAdjudication
          v-else-if="currentSheet === 'K11-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K11-2 明细表（18列2区段，50行） -->
        <K11TabDetail
          v-else-if="currentSheet === 'K11-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K11-3 调整分录 -->
        <K11TabAdjustment
          v-else-if="currentSheet === 'K11-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市） -->
        <K11TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <K11TabDisclosureSoe
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
 * GtK11AssetImpairmentLoss.vue — K11 资产减值损失底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K11-{sheet}-{field}"
 *
 * 损益类科目（6701资产减值损失）— 取发生额非余额！与K8/K9/I6/H10同款处理。
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, onMounted, onUnmounted, onBeforeUnmount, inject, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useChecklistPersistence } from '@/composables/workpaper/useChecklistPersistence'
import { collectChecklistResponses, toChecklistPatch } from '@/composables/workpaper/checklistPersistenceHelpers'
import {
  WorkpaperRuntimeContextKey,
  type WorkpaperRuntimeContext,
} from './composables/useWorkpaperScaffold'
import { useK11DualMode } from './composables/useK11DualMode'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core
const K11TabIndex = defineAsyncComponent(() => import('./k11/core/K11TabIndex.vue'))
const K11TabAdjudication = defineAsyncComponent(() => import('./k11/core/K11TabAdjudication.vue'))
const K11TabDetail = defineAsyncComponent(() => import('./k11/core/K11TabDetail.vue'))
const K11TabAdjustment = defineAsyncComponent(() => import('./k11/core/K11TabAdjustment.vue'))
const K11TabDisclosureListed = defineAsyncComponent(() => import('./k11/core/K11TabDisclosureListed.vue'))
const K11TabDisclosureSoe = defineAsyncComponent(() => import('./k11/core/K11TabDisclosureSoe.vue'))

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
  /** 6701 未审发生额 */
  unadjusted6701: 0,
  /** 6701 审定发生额 */
  audited6701: 0,
})

// ─── 双模式 (OO 健康检查 + el-segmented) ─────────────────────────────────────
const dualMode = useK11DualMode({
  wpId: computed(() => props.wpId) as any,
  sheetName: computed(() => props.sheetName || '') as any,
  reloadAll: async () => { await selfLoad() },
})

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (K11/K11A/K11-1~K11-3/附注)
 * 损益类底稿 — 审定取发生额非余额
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K11'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // K11A 程序表（走 a-program-console，不在此分发）
  if (/K11A/.test(name)) return ''
  // K11-N 编码（K11-1 到 K11-3）
  const m = name.match(/(K11-\d+)/)
  if (m) return m[1]
  // 底稿目录 K11（无后缀）
  if (/底稿目录/.test(name) || (/\bK11\b/.test(name) && !/K11-/.test(name) && !/K11A/.test(name))) return 'K11'
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
    console.warn(`[GtK11AssetImpairmentLoss] save failed: ${itemId}`, error)
  }
}

// ─── TB自动取数（6701资产减值损失 — 损益类取发生额！） ─────────────────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '6701', year: props.year },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u6701 = 0, a6701 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('6701')) {
        u6701 += Number(item.unadjusted_amount ?? 0)
        a6701 += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value = { unadjusted6701: u6701, audited6701: a6701 }
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
    console.warn('[GtK11AssetImpairmentLoss] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// 卸载前 flush 待保存变更（事件监听清理在下方 onUnmounted）。
onBeforeUnmount(() => { void persistence.flush().catch(() => undefined) })

// ─── Lifecycle ───────────────────────────────────────────────────────────────

/**
 * 源底稿减值计提事件处理器（F2/H1/H3/I1/I2/I3/H2/G7）
 * 源底稿通过 window.dispatchEvent(CustomEvent) 发布 'substantive:adjudicated'
 * K11 subscribe 这些事件以更新 K11-2 明细表的 sourceAmount
 *
 * Task 6.2: subscribe各减值源底稿(F2/H1/I1/I2/I3)减值计提
 * Requirements: 6.2, 4.2
 */
const SOURCE_WP_CODES = ['F2', 'H1', 'H3', 'I1', 'I2', 'I3', 'H2', 'G7'] as const

function handleSourceAdjudicated(e: Event): void {
  const detail = (e as CustomEvent).detail
  if (!detail) return
  const wpCode = detail.wpCode ?? detail.wp_code ?? ''
  if (!SOURCE_WP_CODES.includes(wpCode as any)) return

  // 更新 allResponses 中对应来源底稿的金额（供 K11-2 CrossSheet 核对）
  const amount = Number(detail.auditedAmount ?? detail.amount ?? 0)
  if (amount !== 0) {
    allResponses.value.set(`K11-source-${wpCode}-amount`, {
      item_id: `K11-source-${wpCode}-amount`,
      conclusion: null,
      remark: String(amount),
    })
    allResponses.value.set(`K11-source-${wpCode}-status`, {
      item_id: `K11-source-${wpCode}-status`,
      conclusion: null,
      remark: 'done',
    })
  }
}

/** 处理 'impairment:calculated' 事件（F2 存货跌价 / H1 固定资产减值等） */
function handleImpairmentCalculated(e: Event): void {
  const detail = (e as CustomEvent).detail
  if (!detail) return
  const wpCode = detail.wpCode ?? detail.wp_code ?? ''
  if (!SOURCE_WP_CODES.includes(wpCode as any)) return

  const amount = Number(detail.totalRequiredProvision ?? detail.amount ?? 0)
  // 允许 0（本期无补提也要刷新源金额，避免沿用旧数）
  if (!Number.isFinite(amount)) return

  allResponses.value.set(`K11-source-${wpCode}-amount`, {
    item_id: `K11-source-${wpCode}-amount`,
    conclusion: null,
    remark: String(amount),
  })
  allResponses.value.set(`K11-source-${wpCode}-status`, {
    item_id: `K11-source-${wpCode}-status`,
    conclusion: null,
    remark: 'done',
  })

  // 对齐 useK11CrossSheet 键名
  const catKey = WP_TO_CATEGORY_KEY[wpCode]
  if (catKey) {
    allResponses.value.set(`K11-2-${catKey}-source-amount`, {
      item_id: `K11-2-${catKey}-source-amount`,
      conclusion: null,
      remark: String(amount),
    })
  }
}

/** 源底稿编码 → K11-2 CrossSheet category key */
const WP_TO_CATEGORY_KEY: Record<string, string> = {
  F2: 'inventory',
  H1: 'fixed-asset',
  I1: 'intangible',
  I2: 'development',
  I3: 'goodwill',
  H2: 'construction',
  G7: 'equity',
  H3: 'investment-property',
}

onMounted(() => {
  void selfLoad()
  void _loadTbData()

  // Subscribe 源底稿减值计提事件（window CustomEvent 模式）
  window.addEventListener('substantive:adjudicated', handleSourceAdjudicated)
  window.addEventListener('impairment:calculated', handleImpairmentCalculated)
})

onUnmounted(() => {
  // Cleanup source workpaper subscriptions
  window.removeEventListener('substantive:adjudicated', handleSourceAdjudicated)
  window.removeEventListener('impairment:calculated', handleImpairmentCalculated)
})
</script>

<style scoped>
.k11-asset-impairment-loss {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.k11-header-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
