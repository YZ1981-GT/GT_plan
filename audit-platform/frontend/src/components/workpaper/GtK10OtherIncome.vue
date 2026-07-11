<template>
  <div class="k10-other-income">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet" class="k10-header-toolbar">
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
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
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
import { ref, computed, onMounted, provide, toRef, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import useVersionTrail from './composables/useVersionTrail'
import { useK12DualMode } from './composables/useK12DualMode'

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
const allResponses = ref<Map<string, any>>(new Map())
const tbData = ref({
  /** 6117 未审发生额 */
  unadjusted6117: 0,
  /** 6117 审定发生额 */
  audited6117: 0,
})

// ─── 双模式 (OO 健康检查 + el-segmented) ─────────────────────────────────────
const dualMode = useK12DualMode({
  wpId: computed(() => props.wpId) as any,
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
  if (/\bK10\b/.test(name) && !/K10-/.test(name) && !/K10A/.test(name)) return 'K10'
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

// ─── TB自动取数（6117其他收益 — 损益类取发生额！贷方=收益增加） ──────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '6117' },
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
      // 兼容两种键名：allResponses（历史）/ responses_snapshot（render 策略实际输出）
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.responses_snapshot)
      if (map.size > 0) allResponses.value = map
    } else {
      // selfLoad: 自行调用 render-config
      const res = await http.get(`/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'k10-other-income' },
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
    console.warn('[GtK10OtherIncome] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── provide for child components ────────────────────────────────────────────
function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  console.log('[K10] openReviewDialog:', sectionId, sectionLabel)
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
