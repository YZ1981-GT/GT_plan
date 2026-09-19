<template>
  <div class="s6-fund-occupation">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- ─── 工具栏：双模式 + 版本历史 ─── -->
      <div v-if="isHtmlSheet" class="s6-toolbar">
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

      <!-- 审定表S6-1 -->
      <S6AdjudicationSheet
        v-else-if="currentSheet === 'adjudication'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @save="handleAdjudicationSave"
      />

      <!-- 对大股东及关联方资金占用和违规担保情况审核程序S6 -->
      <S6ProgramSheet
        v-else-if="currentSheet === 'program'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 会计监管风险提示第9号——上市公司控股股东资金占用及其审计 -->
      <S6RegulatoryReferenceSheet
        v-else-if="currentSheet === 'regulatory'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
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
      :related-data="{ wpCode: 'S6', projectId: props.projectId }"
    />

    <!-- 版本历史抽屉 -->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
  </div>
</template>

<script setup lang="ts">
/**
 * GtS6FundOccupation.vue — S6 对大股东及关联方资金占用和违规担保情况审核程序 主入口
 *
 * 由外层 GtWpRenderer 的 componentType 's6-fund-occupation' 路由到此组件。
 * 组件接收 sheetName prop，v-if 分发到 3 个功能性子组件（无内部 el-tabs）。
 * 排除 Phase0 中的空白 Sheet2。
 *
 * sheetName 映射关系（Phase0 dispatch_table）：
 *   审定表S6-1                                                   → adjudication
 *   对大股东及关联方资金占用和违规担保情况审核程序S6              → program
 *   会计监管风险提示第9号——上市公司控股股东资金占用及其审计       → regulatory
 *
 * 核心特性：
 * - NO internal el-tabs — 仅 sheetName v-if 分发
 * - selfLoad: htmlData 为 null 时自行调 render-config 加载数据
 * - S6-1 审定表支持 TB 回写（Req 6.3）
 * - S6 大程序表：143 rows 审核程序清单
 * - 会计监管风险提示第9号：方法论上下文样式（琥珀色左边线 + 浅黄背景，可折叠/滚动）
 * - EventBus — 发布 WORKPAPER_SAVED
 * - 13px 表格字体 + GtIndexChip + AI 按钮 + 编制提示 details
 * - readonly 禁止编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.4
 * Requirements: 1.5, 6.1, 6.2, 6.3
 */
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'

// ─── Lazy-loaded child components ────────────────────────────────────────────

const S6AdjudicationSheet = defineAsyncComponent(() => import('./S6AdjudicationSheet.vue'))
const S6ProgramSheet = defineAsyncComponent(() => import('./S6ProgramSheet.vue'))
const S6RegulatoryReferenceSheet = defineAsyncComponent(() => import('./S6RegulatoryReferenceSheet.vue'))

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
 *   审定表S6-1                                             → adjudication
 *   对大股东及关联方资金占用和违规担保情况审核程序S6       → program
 *   会计监管风险提示第9号——上市公司控股股东资金占用及其审计 → regulatory
 *   Sheet2 (empty)                                         → skip / OO fallback
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // GT_Custom → skip
  if (name === 'GT_Custom') return 'skip'

  // 会计监管风险提示第9号
  if (name.includes('会计监管风险提示') || name.includes('第9号') || name.includes('控股股东资金占用及其审计')) return 'regulatory'

  // 审定表 S6-1
  if (name.includes('审定表') || name.match(/S6-1/)) return 'adjudication'

  // 大型审核程序 S6
  if (name.includes('审核程序') || name.includes('资金占用和违规担保') || name.includes('程序S6') || name.match(/程序S6\s*/)) return 'program'

  // 空 sheetName → 默认显示审定表
  if (name === '' || name === 'S6') return 'adjudication'

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

/** 3 个功能 sheet 均为 HTML sheet */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['adjudication', 'program', 'regulatory'].includes(s)
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

/**
 * 当 htmlData 为 null（bundle 内嵌场景），自行调 render-config 加载数据。
 */
async function selfLoad() {
  if (props.htmlData) {
    isLoading.value = false
    return
  }

  try {
    await http.get(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
  } catch (err) {
    console.warn('[GtS6FundOccupation] selfLoad failed:', err)
  }

  isLoading.value = false
}

provide('reloadWorkpaperData', selfLoad)

// ─── EventBus + 审定表保存回调（Req 6.3 TB 回写） ───────────────────────────

import { useSEstimateDisclosureEventBus } from '../composables/useSEstimateDisclosureEventBus'

const {
  saveAndPublish,
} = useSEstimateDisclosureEventBus({
  wpCode: 'S6',
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onRefresh: () => selfLoad(),
  isReadonly,
})

function handleAdjudicationSave() {
  saveAndPublish({ wpCode: 'S6' })
  parentEmit('save')
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.s6-fund-occupation {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.s6-toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
