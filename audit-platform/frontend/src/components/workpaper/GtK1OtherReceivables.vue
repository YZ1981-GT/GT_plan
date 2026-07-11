<template>
  <div class="k1-other-receivables">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet" class="k1-header-toolbar">
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
        />

        <!-- K1-10 长期未收回检查 -->
        <K1TabOverdueCheck
          v-else-if="currentSheet === 'K1-10'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K1-11 关联方检查 -->
        <K1TabRelatedParty
          v-else-if="currentSheet === 'K1-11'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- K1-12 其他应收款检查 -->
        <K1TabReceivableCheck
          v-else-if="currentSheet === 'K1-12'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（上市） -->
        <K1TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <K1TabDisclosureSoe
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
import { ref, computed, onMounted, provide, toRef, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import useVersionTrail from './composables/useVersionTrail'
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

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const allResponses = ref<Map<string, any>>(new Map())
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
      const res = await http.get('/workpapers/onlyoffice/health', { _silent: true } as any)
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
  if (/\bK1\b/.test(name) && !/K1-/.test(name) && !/K1A/.test(name)) return 'K1'
  return ''
})

// ─── 子组件 save 回调（持久化 checklist_responses） ────────────────────────────
async function handleChildSave(itemId: string, value: any): Promise<void> {
  if (!props.wpId) return
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  // 乐观更新本地 Map
  allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: strVal })
  try {
    await http.put(`/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: null, remark: strVal }],
    })
  } catch {
    // 静默失败，数据保留在本地
  }
}

// ─── TB自动取数（1221其他应收款 + 坏账准备） ──────────────────────────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '1221' },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u1221 = 0, a1221 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('1221')) {
        u1221 += Number(item.unadjusted_amount ?? 0)
        a1221 += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value.unadjusted1221 = u1221
    tbData.value.audited1221 = a1221
  } catch {
    // TB取数失败静默处理
  }

  // 坏账准备（科目号取决于企业会计制度，通常为1231或下挂1221坏账）
  try {
    const res = await http.get(`/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '1231' },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let uBd = 0, aBd = 0
    for (const item of list) {
      uBd += Number(item.unadjusted_amount ?? 0)
      aBd += Number(item.audited_amount ?? 0)
    }
    tbData.value.unadjustedBadDebt = uBd
    tbData.value.auditedBadDebt = aBd
  } catch {
    // 静默处理
  }
}

// ─── selfLoad ────────────────────────────────────────────────────────────────
/** 合并一个 responses 对象（{item_id: {...}}）到目标 Map */
function _mergeResponses(map: Map<string, any>, src: any): void {
  if (!src || typeof src !== 'object') return
  for (const [k, v] of Object.entries(src)) map.set(k, v)
}

async function selfLoad(): Promise<void> {
  try {
    if (props.htmlData) {
      // 从父级透传的 htmlData 中提取 responses
      // 兼容两种键名：allResponses（历史）/ responses_snapshot（K1 render 策略实际输出）
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.responses_snapshot)
      if (map.size > 0) allResponses.value = map
    } else {
      // selfLoad: 自行调用 render-config
      const res = await http.get(`/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'k1-other-receivables' },
        _silent: true,
      } as any)
      const data = res.data?.data || res.data
      if (data?.sheets && Array.isArray(data.sheets)) {
        const map = new Map<string, any>()
        for (const sheet of data.sheets) {
          _mergeResponses(map, sheet.html_data?.allResponses)
          _mergeResponses(map, sheet.html_data?.responses_snapshot)
        }
        allResponses.value = map
      }
    }
  } catch (err) {
    console.warn('[GtK1OtherReceivables] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── provide for child components ────────────────────────────────────────────
function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  console.log('[K1] openReviewDialog:', sectionId, sectionLabel)
}
provide('openReviewDialog', openReviewDialog)

// ─── 版本追踪 useVersionTrail (autoSnapshot on save) ─────────────────────────
const versionTrail = useVersionTrail({
  projectId: toRef(props, 'projectId') as any,
  workpaperId: toRef(props, 'wpId') as any,
})
provide('versionTrail', versionTrail)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
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
