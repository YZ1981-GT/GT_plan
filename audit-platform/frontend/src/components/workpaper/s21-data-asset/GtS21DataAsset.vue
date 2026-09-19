<template>
  <div class="s21-data-asset">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- ─── 工具栏：双模式 + 版本历史 ─── -->
      <div v-if="isHtmlSheet" class="s21-toolbar">
        <el-segmented
          v-model="dualMode"
          :options="modeOptions"
          size="small"
          @change="handleModeChange"
        />
        <el-button size="small" @click="openVersionHistory">版本历史</el-button>
      </div>

      <!-- 双模式：切换到 OnlyOffice -->
      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode === 'OnlyOffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 审计程序 S21 -->
      <GtS21Program
        v-else-if="currentSheet === 'program'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
      />
      <!-- 基本情况 S21-1 -->
      <GtS21BasicInfo
        v-else-if="currentSheet === 'S21-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
      />
      <!-- 开发支出资本化分析表 S21-2（核心计算表） -->
      <GtS21Capitalization
        v-else-if="currentSheet === 'S21-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
      />
      <!-- 成本归集与分摊检查表 S21-3 -->
      <GtS21CostAllocation
        v-else-if="currentSheet === 'S21-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
      />
      <!-- 摊销政策检查表 S21-4 -->
      <GtS21Amortization
        v-else-if="currentSheet === 'S21-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
      />
      <!-- OnlyOffice fallback: 未匹配的 sheet -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: 100%; min-height: 600px"
      />
    </template>

    <!-- 复核对话组件 -->
    <GtReviewDialog
      v-if="reviewDialogVisible"
      :wp-id="props.wpId"
      :section-id="reviewDialogSectionId"
      :section-label="reviewDialogSectionLabel"
      :current-user="currentUser"
      :related-data="{ wpCode: 'S21', projectId: props.projectId }"
    />

    <!-- 版本历史抽屉 -->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
  </div>
</template>

<script setup lang="ts">
/**
 * GtS21DataAsset.vue — S21 数据资产底稿主入口
 *
 * 由外层 GtWpRenderer 的 componentType 's21-data-asset' 路由到此组件。
 * 组件接收 sheetName prop，v-if 分发到 5 个内部子组件（无内部 el-tabs）。
 *
 * sheetName 映射关系：
 *   数据资产S21                    → program       → GtS21Program (审计程序)
 *   数据资产的基本情况S21-1        → S21-1        → GtS21BasicInfo (基本情况)
 *   开发支出资本化分析表S21-2      → S21-2        → GtS21Capitalization (核心计算表)
 *   成本归集与分摊检查表S21-3      → S21-3        → GtS21CostAllocation (检查表)
 *   摊销政策检查表S21-4            → S21-4        → GtS21Amortization (检查表)
 *
 * 核心特性：
 * - NO internal el-tabs — 仅 sheetName v-if 分发
 * - selfLoad: htmlData 为 null 时自行调 render-config 加载数据
 * - S21-2 核心：使用 useS21FormulaEngine 实时计算按月归集、类目合计、占比
 * - 资本化 5 项条件判断（技术可行性/使用出售意图/市场需求/技术财力/单独核算可靠计量）
 * - S21-3 成本归集与分摊检查（分摊方法+适当性评价）
 * - 公式单元格只读不可手工覆盖（Req 5.6）
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 4.2
 * Requirements: 1.5, 5.4, 5.5, 5.6
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'

// ─── Lazy-loaded child components ────────────────────────────────────────────

const GtS21Program = defineAsyncComponent(() => import('./GtS21Program.vue'))
const GtS21BasicInfo = defineAsyncComponent(() => import('./GtS21BasicInfo.vue'))
const GtS21Capitalization = defineAsyncComponent(() => import('./GtS21Capitalization.vue'))
const GtS21CostAllocation = defineAsyncComponent(() => import('./GtS21CostAllocation.vue'))
const GtS21Amortization = defineAsyncComponent(() => import('./GtS21Amortization.vue'))

// Shared
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../GtOnlyOfficeSheet.vue'))
const GtReviewDialog = defineAsyncComponent(() => import('@/components/collaboration/GtReviewDialog.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('../version-trail/GtWpVersionTrail.vue'))

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

const parentEmit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
  (e: 'navigate', sheetName: string): void
}>()

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

/** 子表持久化数据快照（item_id → {conclusion, remark}）；由 selfLoad 合并 responses_snapshot 填充 */
const allResponses = ref<Map<string, any>>(new Map())

// ─── Auth ────────────────────────────────────────────────────────────────────

const authStore = useAuthStore()
const currentUser = computed(() => ({
  id: authStore.userId || '',
  name: authStore.user?.full_name || authStore.username || '',
  role: (authStore.user?.role || '审计助理') as any,
}))

// ─── sheetName → 子组件分发 ──────────────────────────────────────────────────

/**
 * 当前激活的 sheet 标识。
 * GtWpRenderer 传入完整 sheetName（如"数据资产S21"），正则匹配后路由。
 *
 * 映射表：
 *   数据资产S21                    → program
 *   数据资产的基本情况S21-1        → S21-1
 *   开发支出资本化分析表S21-2      → S21-2
 *   成本归集与分摊检查表S21-3      → S21-3
 *   摊销政策检查表S21-4            → S21-4
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // GT_Custom → skip
  if (name === 'GT_Custom') return 'skip'

  // S21-1 ~ S21-4 精确匹配编码
  const codeMatch = name.match(/S21-([1-4])/)
  if (codeMatch) return `S21-${codeMatch[1]}`

  // 审计程序 / 数据资产S21（不带后缀编号）
  if (name.includes('审计程序') || (name.includes('数据资产') && !name.includes('基本情况'))) return 'program'

  // 基本情况
  if (name.includes('基本情况')) return 'S21-1'

  // 资本化
  if (name.includes('资本化') || name.includes('开发支出')) return 'S21-2'

  // 成本归集
  if (name.includes('成本归集') || name.includes('分摊检查')) return 'S21-3'

  // 摊销政策
  if (name.includes('摊销')) return 'S21-4'

  // 表头 → skip
  if (name.includes('表头') || name.includes('请先填写')) return 'skip'

  // 空 sheetName → 默认显示审计程序
  if (name === '' || name === 'S21') return 'program'

  // 未匹配 → OO fallback
  return name
})

// ─── 双模式（HTML/OnlyOffice） ───────────────────────────────────────────────

const dualMode = ref<'HTML' | 'OnlyOffice'>('HTML')
const modeOptions = [
  { label: 'HTML', value: 'HTML' },
  { label: 'OnlyOffice', value: 'OnlyOffice' },
]

function handleModeChange(val: any) {
  dualMode.value = val
}

/** 所有内部 sheet 为 HTML sheet */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['program', 'S21-1', 'S21-2', 'S21-3', 'S21-4'].includes(s)
})

// ─── 复核对话 ────────────────────────────────────────────────────────────────

const reviewDialogVisible = ref(false)
const reviewDialogSectionId = ref('')
const reviewDialogSectionLabel = ref('')

function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  reviewDialogSectionId.value = sectionId
  reviewDialogSectionLabel.value = sectionLabel || sectionId
  reviewDialogVisible.value = true
}

provide('openReviewDialog', openReviewDialog)

// ─── 版本追踪 ────────────────────────────────────────────────────────────────

const versionTrailRef = ref<any>(null)

function openVersionHistory() {
  versionTrailRef.value?.open?.()
}

function scheduleAutoSnapshot() {
  // 自动快照逻辑（保存后触发）
}

provide('scheduleAutoSnapshot', scheduleAutoSnapshot)
provide('openVersionHistory', openVersionHistory)

// ─── selfLoad ────────────────────────────────────────────────────────────────

/** 合并一个 responses 对象（{item_id: {...}}）到目标 Map */
function _mergeResponses(map: Map<string, any>, src: any): void {
  if (!src || typeof src !== 'object') return
  // 注入权威 item_id：dict 值缺 item_id 时以键补齐（否则保存 items 缺 item_id 触发 422）；v 自带 item_id 则以其为准
  for (const [k, v] of Object.entries(src)) map.set(k, (v && typeof v === 'object' && !Array.isArray(v)) ? { item_id: k, ...v } : { item_id: k, remark: v })
}

/**
 * 当 htmlData 为 null（bundle 内嵌场景），自行调 render-config 加载数据。
 * 合并 render 策略输出的 responses_snapshot（S21 render 实际输出键）到 allResponses，
 * 供子表 seed 恢复（此前丢弃 → 刷新丢失，本次修复）。
 */
async function selfLoad() {
  try {
    if (props.htmlData) {
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.responses_snapshot)
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.checklist_responses)
      if (map.size > 0) allResponses.value = map
    } else {
      const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
      const data = res.data?.data || res.data
      if (data?.sheets && Array.isArray(data.sheets)) {
        const map = new Map<string, any>()
        for (const sheet of data.sheets) {
          _mergeResponses(map, sheet.html_data?.responses_snapshot)
          _mergeResponses(map, sheet.html_data?.allResponses)
          _mergeResponses(map, sheet.html_data?.checklist_responses)
        }
        if (map.size > 0) allResponses.value = map
      }
    }
  } catch (err) {
    console.warn('[GtS21DataAsset] selfLoad failed:', err)
  }

  isLoading.value = false
}

provide('reloadWorkpaperData', selfLoad)

// ─── 子表 save 持久化（子表 inject('saveResponse') 调用；防抖 800ms 批量 PUT） ──
// 乐观更新本地 Map 供 selfLoad/跨表读取；结构化 value 序列化进 remark；只读跳过。
const _saveTimers = new Map<string, ReturnType<typeof setTimeout>>()
function persistResponse(itemId: string, value: any): void {
  if (!itemId || !props.wpId) return
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  const updated = { ...existing, item_id: itemId, remark: strVal }
  allResponses.value.set(itemId, updated)
  if (isReadonly.value) return
  const prev = _saveTimers.get(itemId)
  if (prev) clearTimeout(prev)
  _saveTimers.set(itemId, setTimeout(() => {
    _saveTimers.delete(itemId)
    http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: updated.conclusion ?? null, remark: updated.remark ?? null }],
    }).catch((err: unknown) => console.warn('[GtS21DataAsset] persistResponse failed:', itemId, err))
  }, 800))
}

provide('saveResponse', persistResponse)
provide('allResponses', allResponses)

onBeforeUnmount(() => {
  for (const t of _saveTimers.values()) clearTimeout(t)
  _saveTimers.clear()
})

// ─── EventBus + 披露联动（Task 5.2: Req 7.3, 8.1, 8.2, 8.3） ───────────────

import { useSEstimateDisclosureEventBus } from '../composables/useSEstimateDisclosureEventBus'

const {
  disclosureText,
  aiLoading,
  saveAndPublish,
  publishDisclosureNoteUpdated,
  onDisclosureTextChange,
  generateDisclosureWithAi,
} = useSEstimateDisclosureEventBus({
  wpCode: 'S21',
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onRefresh: () => selfLoad(),
  isReadonly,
})

// provide 给子组件用
provide('sEstimateDisclosure', {
  disclosureText,
  aiLoading,
  saveAndPublish,
  publishDisclosureNoteUpdated,
  onDisclosureTextChange,
  generateDisclosureWithAi,
})

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.s21-data-asset {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.s21-toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
