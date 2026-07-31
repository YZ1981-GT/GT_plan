<template>
  <div class="k1-other-receivables">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 目录页(currentSheet==='K1')不显示 AI复核/双模式工具栏（无复核对象+不需双模式） -->
      <div v-if="isHtmlSheet && currentSheet !== 'K1'" class="k1-header-toolbar">
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
        <K1TabIndex
          v-if="currentSheet === 'K1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K1A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'K1A'"
          sheet-code="K1A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- K1-1 审定表 -->
        <K1TabAdjudication
          v-else-if="currentSheet === 'K1-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :adjudication-prefill="adjudicationPrefill"
          :tb-source-codes="tbSourceCodes"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K1-2 明细表 -->
        <K1TabDetail
          v-else-if="currentSheet === 'K1-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :related-parties="k1RelatedParties"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K1-3 坏账准备明细 -->
        <K1TabBadDebtDetail
          v-else-if="currentSheet === 'K1-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K1-4 调整分录 -->
        <K1TabAdjustment
          v-else-if="currentSheet === 'K1-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :year="props.year"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K1-5 大额分析 -->
        <K1TabLargeAmount
          v-else-if="currentSheet === 'K1-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :related-parties="k1RelatedParties"
          :bs-date="k1BsDate"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K1-6 会计政策检查 -->
        <K1TabPolicyCheck
          v-else-if="currentSheet === 'K1-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K1-7 三阶段划分 -->
        <K1TabStageCheck
          v-else-if="currentSheet === 'K1-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K1-8 坏账准备测算 -->
        <K1TabBadDebtCalc
          v-else-if="currentSheet === 'K1-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K1-9 核销检查 -->
        <K1TabWriteoffCheck
          v-else-if="currentSheet === 'K1-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K1-10 长期未收回检查 -->
        <K1TabOverdueCheck
          v-else-if="currentSheet === 'K1-10'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :bs-date="k1BsDate"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K1-11 关联方检查 -->
        <K1TabRelatedParty
          v-else-if="currentSheet === 'K1-11'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :related-parties="k1RelatedParties"
          :bs-date="k1BsDate"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K1-12 其他应收款检查 -->
        <K1TabReceivableCheck
          v-else-if="currentSheet === 'K1-12'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市） -->
        <K1TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（国企） -->
        <K1TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
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
 * GtK1OtherReceivables.vue — K1 其他应收款底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K1-{sheet}-{field}"
 *
 * 科目：1221其他应收款（借方/资产类）+ 坏账准备（贷方/资产备抵类）
 * 核心：ECL三阶段引擎 + 坏账准备测算 + 资产类三角勾稽
 *
 * Spec: .kiro/specs/k1-other-receivables/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, onMounted, onBeforeUnmount, inject, defineAsyncComponent, provide, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useChecklistPersistence } from '@/composables/workpaper/useChecklistPersistence'
import { collectChecklistResponses, toChecklistPatch } from '@/composables/workpaper/checklistPersistenceHelpers'
import {
  WorkpaperRuntimeContextKey,
  type WorkpaperRuntimeContext,
} from './composables/useWorkpaperScaffold'
import { createK1RowNavigation, K1RowNavigationKey } from './composables/useK1RowNavigation'
import { resolveK1BsDate } from './composables/k1PostPaymentFromLedger'
import type { K1AdjudicationPrefill } from './composables/useK1Adjudication'
import {
  k1GrossQueryCodes,
  k1ProvisionQueryCodes,
  sumLongestPrefixOnly,
  type K1TbSourceCodes,
} from './composables/k1TbSourceCodes'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core
const K1TabIndex = defineAsyncComponent(() => import('./k1/core/K1TabIndex.vue'))
const K1TabAdjudication = defineAsyncComponent(() => import('./k1/core/K1TabAdjudication.vue'))
const K1TabDetail = defineAsyncComponent(() => import('./k1/core/K1TabDetail.vue'))
const K1TabAdjustment = defineAsyncComponent(() => import('./k1/core/K1TabAdjustment.vue'))
const K1TabDisclosureListed = defineAsyncComponent(() => import('./k1/core/K1TabDisclosureListed.vue'))
const K1TabDisclosureSoe = defineAsyncComponent(() => import('./k1/core/K1TabDisclosureSoe.vue'))

// impairment
const K1TabBadDebtDetail = defineAsyncComponent(() => import('./k1/impairment/K1TabBadDebtDetail.vue'))
const K1TabStageCheck = defineAsyncComponent(() => import('./k1/impairment/K1TabStageCheck.vue'))
const K1TabBadDebtCalc = defineAsyncComponent(() => import('./k1/impairment/K1TabBadDebtCalc.vue'))

// inspection
const K1TabLargeAmount = defineAsyncComponent(() => import('./k1/inspection/K1TabLargeAmount.vue'))
const K1TabPolicyCheck = defineAsyncComponent(() => import('./k1/inspection/K1TabPolicyCheck.vue'))
const K1TabWriteoffCheck = defineAsyncComponent(() => import('./k1/inspection/K1TabWriteoffCheck.vue'))
const K1TabOverdueCheck = defineAsyncComponent(() => import('./k1/inspection/K1TabOverdueCheck.vue'))
const K1TabRelatedParty = defineAsyncComponent(() => import('./k1/inspection/K1TabRelatedParty.vue'))
const K1TabReceivableCheck = defineAsyncComponent(() => import('./k1/inspection/K1TabReceivableCheck.vue'))

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

const k1RowNav = createK1RowNavigation((sheetName) => emit('navigate-sheet', sheetName))
provide(K1RowNavigationKey, k1RowNav)

// 复核圆点
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)

/** B19 关联方清单：后端 render 注入，供 K1-2/K1-11 完整性校验 */
const k1RelatedParties = computed<string[]>(() => {
  const ctx = props.htmlData?.project_context ?? props.htmlData?.projectContext ?? {}
  const raw = ctx.related_parties
  if (!Array.isArray(raw)) return []
  return raw
    .map((p: unknown) => {
      if (typeof p === 'string') return p
      if (p && typeof p === 'object') {
        const o = p as Record<string, unknown>
        return String(o.name ?? o.party_name ?? o.partyName ?? '')
      }
      return ''
    })
    .filter(Boolean)
})

/** 资产负债表日：供期后回款窗口 */
const k1BsDate = computed(() => {
  const ctx = props.htmlData?.project_context ?? props.htmlData?.projectContext ?? {}
  return resolveK1BsDate(ctx.bs_date ?? ctx.bsDate, props.year ?? ctx.audit_year)
})

/** 审定表 tb_balance 预填（仅无持久化未审数时由后端返回） */
const adjudicationPrefill = computed<K1AdjudicationPrefill | null>(() => {
  const raw = props.htmlData?.adjudication_prefill ?? props.htmlData?.adjudicationPrefill
  if (!raw || typeof raw !== 'object') return null
  return raw as K1AdjudicationPrefill
})

/**
 * 四表库取数溯源（报表行 BS-009 → 标准码 → 客户原始码）。
 * 既供 K1-1 溯源面板展示，也是坏账兜底请求的口径来源（禁止再写死 `1231`）。
 */
const tbSourceCodes = computed<K1TbSourceCodes | null>(() => {
  const raw = props.htmlData?.tb_source_codes ?? props.htmlData?.tbSourceCodes
  if (!raw || typeof raw !== 'object') return null
  return raw as K1TbSourceCodes
})

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed<string | undefined>(() => props.projectId || undefined)
const persistence = useChecklistPersistence({ wpId: wpIdRef, projectId: projectIdRef })
const allResponses = persistence.responses
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const tbData = ref({
  unadjusted1221: 0,
  audited1221: 0,
  unadjustedBadDebt: 0,
  auditedBadDebt: 0,
})

// ─── 双模式 (OO 健康检查 + el-segmented) ────────────────────────────────────
const dualMode = (() => {
  const currentMode = ref<'html' | 'onlyoffice'>('html')
  const isOoAvailable = ref(false)
  const checking = ref(true)
  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

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
  }

  // 启动时检查 OO 可用性
  checkOoHealth()

  return { currentMode, isOoAvailable, checking, modeOptions, onModeChange }
})()

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (K1/K1A/K1-1~K1-12/附注)
 * 支持格式：
 *  - "底稿目录" / "K1 其他应收款" → K1
 *  - "K1A xxx" → K1A
 *  - "K1-1 审定表" → K1-1
 *  - "K1-12 检查表" → K1-12
 *  - "附注...上市" / "附注...国" → 附注
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K1'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 K1A
  if (/K1A/.test(name)) return 'K1A'
  // K1-N 编码（K1-1 到 K1-12）
  const m = name.match(/(K1-\d+)/)
  if (m) return m[1]
  // 底稿目录 K1（无后缀）
  if (/底稿目录/.test(name) || (/\bK1\b/.test(name) && !/K1-/.test(name) && !/K1A/.test(name))) return 'K1'
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
    console.warn(`[GtK1OtherReceivables] save failed: ${itemId}`, error)
  }
}

// ─── TB自动取数（1221其他应收款 + 坏账准备） ──────────────────────────────────
async function _loadTbData(): Promise<void> {
  // 优先用 render 注入的 tb_values，避免重复请求
  const seeded = props.htmlData?.tb_values ?? props.htmlData?.tbValues
  if (seeded && typeof seeded === 'object') {
    const u1221 = Number(seeded.receivable_unadjusted ?? seeded.receivableUnadjusted ?? 0)
    const a1221 = Number(seeded.receivable_audited ?? seeded.receivableAudited ?? 0)
    const uBd = Number(seeded.bad_debt_unadjusted ?? seeded.badDebtUnadjusted ?? 0)
    const aBd = Number(seeded.bad_debt_audited ?? seeded.badDebtAudited ?? 0)
    // closing 兜底：无 trial_balance 未审时用 tb_balance 期末
    tbData.value = {
      unadjusted1221: u1221 || Number(seeded.receivable_unadjusted_closing ?? 0),
      audited1221: a1221 || Number(seeded.receivable_unadjusted_closing ?? 0),
      unadjustedBadDebt: Math.abs(uBd || Number(seeded.bad_debt_unadjusted_closing ?? 0)),
      auditedBadDebt: Math.abs(aBd || Number(seeded.bad_debt_unadjusted_closing ?? 0)),
    }
    if (tbData.value.unadjusted1221 || tbData.value.unadjustedBadDebt) return
  }

  if (!props.projectId) return

  /** 拉某科目前缀的试算平衡表行 → 归一为 `TbCodedAmountRow[]` */
  async function _fetchTbRows(prefix: string) {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: prefix, year: props.year },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data)
      ? (res?.data?.data ?? res?.data)
      : []
    return list.map((item) => ({
      code: String(item.standard_account_code ?? item.account_code ?? ''),
      unadjusted: Number(item.unadjusted_amount ?? 0),
      audited: Number(item.audited_amount ?? 0),
    }))
  }

  // 原值：口径取自 render 溯源（缺省 1221）；只累加叶子（最长前缀）防父子双计
  try {
    const codes = k1GrossQueryCodes(tbSourceCodes.value)
    const rows = await _fetchTbRows(codes[0].split('-')[0])
    const sum = sumLongestPrefixOnly(rows, codes)
    tbData.value.unadjusted1221 = sum.unadjusted
    tbData.value.audited1221 = sum.audited
  } catch {
    // TB取数失败静默处理
  }

  // 坏账准备：🔴 口径必须是「其他应收款」专属备抵子科目（实证 1231-03），
  // 而非宽口径 1231 —— 后者会把应收票据/应收账款的坏账一并算进 K1，
  // 且 trial_balance 里父码 1231 与子码 1231-0x 并存会双计。
  try {
    const codes = k1ProvisionQueryCodes(tbSourceCodes.value)
    const rows = await _fetchTbRows(codes[0].split('-')[0])
    const sum = sumLongestPrefixOnly(rows, codes)
    tbData.value.unadjustedBadDebt = Math.abs(sum.unadjusted)
    tbData.value.auditedBadDebt = Math.abs(sum.audited)
  } catch {
    // 静默处理
  }
}

// ─── selfLoad ────────────────────────────────────────────────────────────────
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
    console.warn('[GtK1OtherReceivables] selfLoad failed:', err)
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
.k1-other-receivables {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.k1-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
