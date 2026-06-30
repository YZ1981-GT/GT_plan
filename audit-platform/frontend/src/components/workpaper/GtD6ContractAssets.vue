<template>
  <div class="d6-contract-assets">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- 程序表 D6A -->
      <D6TabProcedure
        v-if="currentSheet === 'D6A' || currentSheet === 'D6'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
      />
      <!-- 审定表 D6-1 -->
      <D6TabAdjudication
        v-else-if="currentSheet === 'D6-1'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
      />
      <!-- 明细表 D6-2 -->
      <D6TabDetail
        v-else-if="currentSheet === 'D6-2'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
      />
      <!-- 减值准备明细 D6-3 -->
      <D6TabImpairmentDetail
        v-else-if="currentSheet === 'D6-3'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
      />
      <!-- 调整分录 D6-4 -->
      <D6TabAdjustment
        v-else-if="currentSheet === 'D6-4'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
      />
      <!-- 关联方检查 D6-5 -->
      <D6TabRelatedParty
        v-else-if="currentSheet === 'D6-5'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
      />
      <!-- 检查表 D6-6 -->
      <D6TabInspection
        v-else-if="currentSheet === 'D6-6'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
      />
      <!-- 减值政策 D6-7 -->
      <D6TabPolicyCheck
        v-else-if="currentSheet === 'D6-7'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
      />
      <!-- 减值测算 D6-8 -->
      <D6TabEclCalculation
        v-else-if="currentSheet === 'D6-8'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
        :cross-sheet="crossSheet"
      />
      <!-- 转回核销 D6-9 -->
      <D6TabWriteoffCheck
        v-else-if="currentSheet === 'D6-9'"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        :save-immediate="saveImmediate"
        :debounced-save="debouncedSave"
      />
      <!-- 附注披露（上市） -->
      <D6TabDisclosure
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
      <D6TabDisclosure
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
      <D6TabAdjudication
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
 * GtD6ContractAssets.vue — D6 合同资产底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，按 v-if 分发到对应子组件。
 * 不使用内部 el-tabs（GtWpRenderer 已提供 sheet 目录 tabs）。
 *
 * 科目：1402 合同资产（借方/资产类）
 * 核心公式：期末=期初+借方-贷方；净值=原值-坏账准备；应计提=余额×损失率
 * selfLoad: htmlData 为 null 时自行调 render-config
 */
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'

// ─── Lazy Sub-Components ─────────────────────────────────────────────────────

const D6TabProcedure = defineAsyncComponent(() => import('./d6/D6TabProcedure.vue'))
const D6TabAdjudication = defineAsyncComponent(() => import('./d6/D6TabAdjudication.vue'))
const D6TabDetail = defineAsyncComponent(() => import('./d6/D6TabDetail.vue'))
const D6TabImpairmentDetail = defineAsyncComponent(() => import('./d6/D6TabImpairmentDetail.vue'))
const D6TabAdjustment = defineAsyncComponent(() => import('./d6/D6TabAdjustment.vue'))
const D6TabRelatedParty = defineAsyncComponent(() => import('./d6/D6TabRelatedParty.vue'))
const D6TabInspection = defineAsyncComponent(() => import('./d6/D6TabInspection.vue'))
const D6TabPolicyCheck = defineAsyncComponent(() => import('./d6/D6TabPolicyCheck.vue'))
const D6TabEclCalculation = defineAsyncComponent(() => import('./d6/D6TabEclCalculation.vue'))
const D6TabWriteoffCheck = defineAsyncComponent(() => import('./d6/D6TabWriteoffCheck.vue'))
const D6TabDisclosure = defineAsyncComponent(() => import('./d6/D6TabDisclosure.vue'))

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
 * GtWpRenderer 传入完整 sheet_name（如"合同资产审定表D6-1"），
 * 需提取编码部分来匹配子组件。 */
const currentSheet = computed(() => {
  const name = props.sheetName || 'D6-1'
  // 提取末尾 D6 编码（D6/D6A/D6-1~D6-9）
  const match = name.match(/D6(?:A|-\d+)?$/)
  if (match) return match[0]
  // 附注特殊匹配
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企')) return '附注国企'
  return name
})

// ─── Cross-Sheet placeholder（后续 task 4 实现完整 useD6CrossSheet） ─────────

const crossSheet = computed(() => ({
  originalValueAggregation: computed(() => ({})),
  impairmentAggregation: computed(() => ({})),
  blockTotals: computed(() => ({
    block1: { subtotal: 0, deduction: 0, total: 0 },
    block2: { subtotal: 0, deduction: 0, total: 0 },
    block3: { subtotal: 0, deduction: 0, total: 0 },
  })),
  netValueRows: computed(() => []),
  eclReferenceValues: computed(() => ({ single: 0, groups: {}, total: 0 })),
  adjustmentTotals: computed(() => ({ ajeTotal: 0, rjeTotal: 0 })),
  netValueValidation: computed(() => ({ isValid: true, diff: 0 })),
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
        params: { force_component_type: 'd6-contract-assets' },
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
    console.error('[D6] loadAll failed:', err)
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
    console.error('[D6] saveImmediate failed:', itemId, err)
  }
}

/** debounced 保存（2s 延迟） */
let _saveTimers: Map<string, ReturnType<typeof setTimeout>> = new Map()
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
  console.log('[D6] openReviewDialog:', sectionId)
}

provide('openReviewDialog', openReviewDialog)

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
})
</script>

<style scoped>
.d6-contract-assets {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
