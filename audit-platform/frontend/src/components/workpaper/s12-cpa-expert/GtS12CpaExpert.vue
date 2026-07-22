<template>
  <div class="s12-cpa-expert">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- ─── 工具栏：双模式 + 版本历史 ─── -->
      <div v-if="isHtmlSheet" class="s12-toolbar">
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

      <!-- ═══ sheetName v-if 分发（NO internal el-tabs） ═══ -->

      <!-- S12 利用专家的工作程序表 -->
      <S12ProgramSheet
        v-else-if="currentSheet === 'program'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
      />

      <!-- S12-1 评价胜任能力、专业素质和客观性 -->
      <S12EvaluationSheet
        v-else-if="currentSheet === 'evaluation-competence'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        sheet-key="S12-1"
        title="评价胜任能力、专业素质和客观性"
      />

      <!-- S12-1-1 评价专家的客观性 -->
      <S12EvaluationSheet
        v-else-if="currentSheet === 'evaluation-objectivity'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        sheet-key="S12-1-1"
        title="评价专家的客观性"
      />

      <!-- S12-2 了解专家的专长领域 -->
      <S12EvaluationSheet
        v-else-if="currentSheet === 'understanding-expertise'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        sheet-key="S12-2"
        title="了解专家的专长领域"
      />

      <!-- S12-3 评价专家工作的恰当性 -->
      <S12EvaluationSheet
        v-else-if="currentSheet === 'evaluation-appropriateness'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        sheet-key="S12-3"
        title="评价专家工作的恰当性"
      />

      <!-- S12-3-1 注册会计师的专家的报告 -->
      <S12EvaluationSheet
        v-else-if="currentSheet === 'expert-report'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        sheet-key="S12-3-1"
        title="注册会计师的专家的报告"
      />

      <!-- S12-3-2/3-3/3-4 多分支子表（按 ExpertDomain 选择） -->
      <S12BranchSheet
        v-else-if="currentSheet === 'branch'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        :all-responses="allResponses"
        prefix="S12"
      />

      <!-- OnlyOffice fallback：未匹配的 sheet -->
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
      :related-data="{ wpCode: 'S12', projectId: props.projectId }"
    />

    <!-- 版本历史抽屉 -->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
  </div>
</template>

<script setup lang="ts">
/**
 * GtS12CpaExpert.vue — S12 利用专家（注册会计师的专家）的工作 主入口
 *
 * 由外层 GtWpRenderer 的 componentType 's12-cpa-expert' 路由到此组件。
 * 组件接收 sheetName prop，v-if 分发到 9 个内部子组件（无内部 el-tabs）。
 *
 * sheetName 映射关系（Phase0 dispatch_table）：
 *   S12 利用专家的工作程序表                       → program
 *   S12-1 评价胜任能力、专业素质和客观性           → evaluation-competence
 *   S12-1-1 评价专家的客观性                       → evaluation-objectivity
 *   S12-2 了解专家的专长领域                       → understanding-expertise
 *   S12-3 评价专家工作的恰当性                     → evaluation-appropriateness
 *   S12-3-1 注册会计师的专家的报告                 → expert-report
 *   S12-3-2 利用专家评价管理层的工作的适当性       → branch (general)
 *   S12-3-3 利用专家评价管理层的工作(股份支付)     → branch (share-based-payment)
 *   S12-3-4 利用专家评价管理层的工作(金融工具公允价值） → branch (financial-instrument-fair-value)
 *
 * 核心特性：
 * - NO internal el-tabs — 仅 sheetName v-if 分发
 * - selfLoad: htmlData 为 null 时自行调 render-config 加载数据
 * - resolveExpertSubSheet 多分支域选择（通用/股份支付/金融工具公允价值）
 * - EventBus — 发布 WORKPAPER_SAVED
 * - 13px 表格字体 + GtIndexChip 跨底稿引用
 * - 审计说明/结论 el-card + AI 按钮
 * - 编制提示 details 折叠
 * - readonly 禁止编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.3
 * Requirements: 1.5, 4.1, 4.2, 4.5
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'

// ─── Lazy-loaded child components ────────────────────────────────────────────

const S12ProgramSheet = defineAsyncComponent(() => import('./S12ProgramSheet.vue'))
const S12EvaluationSheet = defineAsyncComponent(() => import('./S12EvaluationSheet.vue'))
const S12BranchSheet = defineAsyncComponent(() => import('./S12BranchSheet.vue'))

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
 * GtWpRenderer 传入完整 sheetName，正则匹配后路由。
 *
 * 映射表（Phase0 dispatch_table）：
 *   S12 利用专家的工作程序表           → program
 *   S12-1 评价胜任能力、专业素质和客观性 → evaluation-competence
 *   S12-1-1 评价专家的客观性           → evaluation-objectivity
 *   S12-2 了解专家的专长领域           → understanding-expertise
 *   S12-3 评价专家工作的恰当性         → evaluation-appropriateness
 *   S12-3-1 注册会计师的专家的报告     → expert-report
 *   S12-3-2/3-3/3-4 多分支子表         → branch
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // GT_Custom → skip
  if (name === 'GT_Custom') return 'skip'

  // S12-3-2/3-3/3-4 多分支子表（优先匹配）
  if (name.match(/S12-3-[234]/) || name.includes('利用专家评价管理层的工作')) return 'branch'

  // S12-3-1 专家报告
  if (name.match(/S12-3-1/) || name.includes('注册会计师的专家的报告')) return 'expert-report'

  // S12-3 评价恰当性
  if (name.match(/S12-3\b/) || name.includes('评价专家工作的恰当性')) return 'evaluation-appropriateness'

  // S12-2 了解专长领域
  if (name.match(/S12-2/) || name.includes('了解专家的专长领域')) return 'understanding-expertise'

  // S12-1-1 客观性评价（优先于 S12-1）
  if (name.match(/S12-1-1/) || name.includes('评价专家的客观性')) return 'evaluation-objectivity'

  // S12-1 胜任能力评价
  if (name.match(/S12-1\b/) || name.includes('评价胜任能力')) return 'evaluation-competence'

  // S12 程序表
  if (name.includes('程序表') || name.includes('利用专家的工作程序') || name === 'S12') return 'program'

  // 空 sheetName → 默认显示程序表
  if (name === '') return 'program'

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

/** 所有 sheet 均为 HTML sheet */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return [
    'program', 'evaluation-competence', 'evaluation-objectivity',
    'understanding-expertise', 'evaluation-appropriateness',
    'expert-report', 'branch',
  ].includes(s)
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
 * 合并 render 策略输出的 responses_snapshot（S12 render 实际输出键）到 allResponses，
 * 供子表 seed 恢复（此前丢弃 → 刷新丢失，本次修复）。
 */
async function selfLoad() {
  try {
    if (props.htmlData) {
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.responses_snapshot)
      if (map.size > 0) allResponses.value = map
    } else {
      const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
      const data = res.data?.data || res.data
      if (data?.sheets && Array.isArray(data.sheets)) {
        const map = new Map<string, any>()
        for (const sheet of data.sheets) {
          _mergeResponses(map, sheet.html_data?.allResponses)
          _mergeResponses(map, sheet.html_data?.responses_snapshot)
        }
        if (map.size > 0) allResponses.value = map
      }
    }
  } catch (err) {
    console.warn('[GtS12CpaExpert] selfLoad failed:', err)
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
    }).catch((err: unknown) => console.warn('[GtS12] persistResponse failed:', itemId, err))
  }, 800))
}

provide('saveResponse', persistResponse)
provide('allResponses', allResponses)

onBeforeUnmount(() => {
  for (const t of _saveTimers.values()) clearTimeout(t)
  _saveTimers.clear()
})

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.s12-cpa-expert {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.s12-toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
