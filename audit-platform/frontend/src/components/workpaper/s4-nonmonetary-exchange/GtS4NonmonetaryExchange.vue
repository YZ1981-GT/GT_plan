<template>
  <div class="s4-nonmonetary-exchange">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- ─── 工具栏：双模式 + 版本历史 ─── -->
      <div v-if="isHtmlSheet" class="s4-toolbar">
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

      <!-- 审计程序 S4 -->
      <S4ProgramSheet
        v-else-if="currentSheet === 'program'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 审定表 S4-1 -->
      <S4AdjudicationSheet
        v-else-if="currentSheet === 'adjudication'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @save="handleAdjudicationSave"
      />

      <!-- 商业实质的判断 S4-2 -->
      <S4CommercialSubstanceSheet
        v-else-if="currentSheet === 'substance'"
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
      :related-data="{ wpCode: 'S4', projectId: props.projectId }"
    />

    <!-- 版本历史抽屉 -->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
  </div>
</template>

<script setup lang="ts">
/**
 * GtS4NonmonetaryExchange.vue — S4 非货币性资产交换底稿主入口
 *
 * 由外层 GtWpRenderer 的 componentType 's4-nonmonetary-exchange' 路由到此组件。
 * 组件接收 sheetName prop，v-if 分发到 3 个内部子组件（无内部 el-tabs）。
 *
 * sheetName 映射关系（Phase0 dispatch_table）：
 *   非货币性资产交换审计程序S4  → program       → S4ProgramSheet
 *   审定表S4-1                  → adjudication  → S4AdjudicationSheet
 *   商业实质的判断S4-2          → substance     → S4CommercialSubstanceSheet
 *
 * 核心特性：
 * - NO internal el-tabs — 仅 sheetName v-if 分发
 * - selfLoad: htmlData 为 null 时自行调 render-config 加载数据
 * - useS4FormulaEngine 集成（审定表损益计算 + 商业实质 IF 判断）
 * - 非经常性损益标注 — 附注披露中标注交换损益为非经常性损益
 * - EventBus — 发布 disclosure:note-text-updated
 * - 13px 表格字体 + 公式列虚线下划线 + tooltip
 * - GtIndexChip 跨底稿引用
 * - 审计说明/结论 el-card + AI 按钮
 * - 编制提示 details 折叠
 * - readonly 禁止编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.1
 * Requirements: 1.5, 2.1, 2.5
 */
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'

// ─── Lazy-loaded child components ────────────────────────────────────────────

const S4ProgramSheet = defineAsyncComponent(() => import('./S4ProgramSheet.vue'))
const S4AdjudicationSheet = defineAsyncComponent(() => import('./S4AdjudicationSheet.vue'))
const S4CommercialSubstanceSheet = defineAsyncComponent(() => import('./S4CommercialSubstanceSheet.vue'))

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
 * GtWpRenderer 传入完整 sheetName（如"审定表S4-1"），正则匹配后路由。
 *
 * 映射表（Phase0 dispatch_table）：
 *   非货币性资产交换审计程序S4  → program
 *   审定表S4-1                  → adjudication
 *   商业实质的判断S4-2          → substance
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // GT_Custom → skip
  if (name === 'GT_Custom') return 'skip'

  // 商业实质判断 S4-2
  if (name.includes('商业实质') || name.match(/S4-2/)) return 'substance'

  // 审定表 S4-1
  if (name.includes('审定表') || name.match(/S4-1/)) return 'adjudication'

  // 审计程序 S4
  if (name.includes('审计程序') || name.includes('程序S4') || name.includes('非货币性资产交换审计程序')) return 'program'

  // 空 sheetName → 默认显示审计程序
  if (name === '' || name === 'S4') return 'program'

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

/** 三个 sheet 都为 HTML sheet */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['program', 'adjudication', 'substance'].includes(s)
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
    console.warn('[GtS4NonmonetaryExchange] selfLoad failed:', err)
  }

  isLoading.value = false
}

provide('reloadWorkpaperData', selfLoad)

// ─── EventBus + 披露联动（非经常性损益标注 Req 2.5） ─────────────────────────

import { useSEstimateDisclosureEventBus } from '../composables/useSEstimateDisclosureEventBus'

const {
  disclosureText,
  aiLoading,
  saveAndPublish,
  publishDisclosureNoteUpdated,
  onDisclosureTextChange,
  generateDisclosureWithAi,
} = useSEstimateDisclosureEventBus({
  wpCode: 'S4',
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onRefresh: () => selfLoad(),
  isReadonly,
})

// provide 给子组件用（审定表保存 + 披露区联动）
provide('sEstimateDisclosure', {
  disclosureText,
  aiLoading,
  saveAndPublish,
  publishDisclosureNoteUpdated,
  onDisclosureTextChange,
  generateDisclosureWithAi,
})

// ─── 审定表保存回调 ──────────────────────────────────────────────────────────

function handleAdjudicationSave() {
  saveAndPublish({ wpCode: 'S4' })
  parentEmit('save')
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.s4-nonmonetary-exchange {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.s4-toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
