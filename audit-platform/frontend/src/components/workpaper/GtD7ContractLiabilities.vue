<template>
  <div class="d7-contract-liabilities">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- 程序表 D7A -->
      <D7TabProcedure
        v-if="currentSheet === 'D7A' || currentSheet === 'D7'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
      />
      <!-- 审定表 D7-1 -->
      <D7TabAdjudication
        v-else-if="currentSheet === 'D7-1'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
      />
      <!-- 明细表 D7-2 -->
      <D7TabDetail
        v-else-if="currentSheet === 'D7-2'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
      />
      <!-- 调整分录 D7-3 -->
      <D7TabAdjustment
        v-else-if="currentSheet === 'D7-3'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
      />
      <!-- 分析表 D7-4 -->
      <D7TabAnalysis
        v-else-if="currentSheet === 'D7-4'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
      />
      <!-- 账龄1年以上检查 D7-5 -->
      <D7TabLongTerm
        v-else-if="currentSheet === 'D7-5'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
      />
      <!-- 关联方检查 D7-6 -->
      <D7TabRelatedParty
        v-else-if="currentSheet === 'D7-6'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
      />
      <!-- 凭证检查 D7-7 -->
      <D7TabVoucherCheck
        v-else-if="currentSheet === 'D7-7'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
      />
      <!-- 附注披露（上市） -->
      <D7TabDisclosure
        v-else-if="currentSheet === '附注上市'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
        variant="listed"
      />
      <!-- 附注披露（国企） -->
      <D7TabDisclosure
        v-else-if="currentSheet === '附注国企'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
        variant="soe"
      />
      <!-- Fallback: 默认显示审定表 -->
      <D7TabAdjudication
        v-else
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtD7ContractLiabilities.vue — D7 合同负债底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，按 v-if 分发到对应子组件。
 * 不使用内部 el-tabs（GtWpRenderer 已提供 sheet 目录 tabs）。
 *
 * 科目：2205 合同负债（贷方/负债类）
 * 核心公式：期末=期初+贷方-借方；审定数=未审+AJE+RJE
 * 双区块审定表：按性质分类+按账龄分类，含"减：计入其他非流动负债"扣减行
 * selfLoad: htmlData 为 null 时自行调 render-config
 */
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'

// ─── Lazy Sub-Components ─────────────────────────────────────────────────────

const D7TabProcedure = defineAsyncComponent(() => import('./d7/D7TabProcedure.vue'))
const D7TabAdjudication = defineAsyncComponent(() => import('./d7/D7TabAdjudication.vue'))
const D7TabDetail = defineAsyncComponent(() => import('./d7/D7TabDetail.vue'))
const D7TabAdjustment = defineAsyncComponent(() => import('./d7/D7TabAdjustment.vue'))
const D7TabAnalysis = defineAsyncComponent(() => import('./d7/D7TabAnalysis.vue'))
const D7TabLongTerm = defineAsyncComponent(() => import('./d7/D7TabLongTerm.vue'))
const D7TabRelatedParty = defineAsyncComponent(() => import('./d7/D7TabRelatedParty.vue'))
const D7TabVoucherCheck = defineAsyncComponent(() => import('./d7/D7TabVoucherCheck.vue'))
const D7TabDisclosure = defineAsyncComponent(() => import('./d7/D7TabDisclosure.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── State ───────────────────────────────────────────────────────────────────

const isReadonly = computed(() => !!props.readonly)
const wpId = computed(() => props.wpId)
const projectId = computed(() => props.projectId)
const isLoading = ref(false)
const allResponses = ref<Map<string, any>>(new Map())

/** 当前激活的 sheet（由外层 GtWpRenderer 通过 sheetName prop 控制）。
 * GtWpRenderer 传入完整 sheet_name（如"合同负债审定表D7-1"），
 * 需提取编码部分来匹配子组件。 */
const currentSheet = computed(() => {
  const name = props.sheetName || 'D7-1'
  // 提取末尾 D7 编码（D7/D7A/D7-1~D7-7）
  const match = name.match(/D7(?:A|-\d+)?$/)
  if (match) return match[0]
  // 附注特殊匹配
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企')) return '附注国企'
  if (name.includes('附注')) return '附注上市'
  return name
})

// ─── Cross-Sheet placeholder（后续 task 4 实现完整 useD7CrossSheet） ─────────

const crossSheet = computed(() => ({
  natureAggregation: computed(() => ({
    revenue: { prior: 0, current: 0 },
    development: { prior: 0, current: 0 },
    engineering: { prior: 0, current: 0 },
    other: { prior: 0, current: 0 },
  })),
  agingAggregation: computed(() => ({
    within1Year: { prior: 0, current: 0 },
    year1to2: { prior: 0, current: 0 },
    year2to3: { prior: 0, current: 0 },
    over3Years: { prior: 0, current: 0 },
  })),
  adjustmentTotals: computed(() => ({ ajeTotal: 0, rjeTotal: 0 })),
  adjudicationForDisclosure: computed(() => ({})),
  voucherPostTransferTotal: computed(() => 0),
  crossValidation: computed(() => ({ isConsistent: true, diff: 0 })),
  crossSheetStatus: ref('loaded' as const),
}))

// ─── Data Loading ────────────────────────────────────────────────────────────

/** selfLoad: 当 htmlData prop 为 null（bundle 内嵌场景），自行调 render-config 加载数据 */
async function loadAll() {
  isLoading.value = true
  try {
    // 尝试从 htmlData 获取已有 responses
    if (props.htmlData?.responses) {
      const map = new Map<string, any>()
      for (const r of props.htmlData.responses) {
        map.set(r.item_id, r)
      }
      allResponses.value = map
    } else {
      // selfLoad: 调 render-config 获取数据
      const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'd7-contract-liabilities' },
      })
      const data = res.data?.data || res.data
      if (data?.sheets?.[0]?.html_data?.responses) {
        const map = new Map<string, any>()
        for (const r of data.sheets[0].html_data.responses) {
          map.set(r.item_id, r)
        }
        allResponses.value = map
      }
    }
  } catch (err) {
    console.error('[D7] loadAll failed:', err)
  } finally {
    isLoading.value = false
  }
}

/** 保存单条 response（立即） */
async function saveImmediate(itemId: string, data: Partial<any>) {
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses/${itemId}`, data)
    // 更新本地 map
    const existing = allResponses.value.get(itemId) || { item_id: itemId }
    allResponses.value.set(itemId, { ...existing, ...data })
  } catch (err) {
    console.error('[D7] saveImmediate failed:', itemId, err)
  }
}

/** debounced 保存（2s 延迟） */
const _saveTimers: Map<string, ReturnType<typeof setTimeout>> = new Map()
function debouncedSave(itemId: string, data: Partial<any>) {
  const existing = _saveTimers.get(itemId)
  if (existing) clearTimeout(existing)
  _saveTimers.set(itemId, setTimeout(() => {
    saveImmediate(itemId, data)
    _saveTimers.delete(itemId)
  }, 2000))
}

// ─── Provide openReviewDialog ────────────────────────────────────────────────

function openReviewDialog(sectionId: string): void {
  console.log('[D7] openReviewDialog:', sectionId)
}

provide('openReviewDialog', openReviewDialog)

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
})
</script>

<style scoped>
.d7-contract-liabilities {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
