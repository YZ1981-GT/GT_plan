<template>
  <div class="s3-policy-change">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- ─── 工具栏：双模式 + 版本历史 ─── -->
      <div v-if="isHtmlSheet" class="s3-toolbar">
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

      <!-- 审定表 -->
      <GtS3Adjudication
        v-else-if="currentSheet === 'adjudication'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- S3-1 会计政策变更和前期差错更正 -->
      <GtS3PolicyError
        v-else-if="currentSheet === 'S3-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- S3-2 会计估计变更审计程序 -->
      <GtS3EstimateChange
        v-else-if="currentSheet === 'S3-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- S3-4 首次执行新金融工具准则的调整 -->
      <GtS3Ifrs9Adjust
        v-else-if="currentSheet === 'S3-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- S3-6 首次执行新收入准则的调整 -->
      <GtS3Ifrs15Adjust
        v-else-if="currentSheet === 'S3-6'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- S3-8 首次执行新租赁准则的调整 -->
      <GtS3Ifrs16Adjust
        v-else-if="currentSheet === 'S3-8'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- S3-9 简化的追溯调整法（1） -->
      <GtS3SimplifiedRetro1
        v-else-if="currentSheet === 'S3-9'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- S3-10 简化的追溯调整法（2） -->
      <GtS3SimplifiedRetro2
        v-else-if="currentSheet === 'S3-10'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- OnlyOffice fallback: 未匹配的 sheet（含参考sheet 1979公式） -->
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
      :related-data="{ wpCode: 'S3', projectId: props.projectId }"
    />

    <!-- 版本历史抽屉 -->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
  </div>
</template>

<script setup lang="ts">
/**
 * GtS3PolicyChange.vue — S3 会计政策变更、前期差错更正、会计估计变更底稿主入口
 *
 * 由外层 GtWpRenderer 的 componentType 's3-policy-change' 路由到此组件。
 * 组件接收 sheetName prop，v-if 分发到 8 个内部子组件（无内部 el-tabs）。
 *
 * sheetName 映射关系：
 *   审定表                                    → adjudication  → GtS3Adjudication
 *   会计政策变更和前期差错更正S3-1             → S3-1         → GtS3PolicyError
 *   会计估计变更审计程序S3-2                   → S3-2         → GtS3EstimateChange
 *   首次执行新金融工具准则的调整S3-4           → S3-4         → GtS3Ifrs9Adjust
 *   首次执行新收入准则的调整S3-6               → S3-6         → GtS3Ifrs15Adjust
 *   首次执行新租赁准则的调整S3-8               → S3-8         → GtS3Ifrs16Adjust
 *   简化的追溯调整法（1）S3-9                  → S3-9         → GtS3SimplifiedRetro1
 *   简化的追溯调整法（2）S3-10                 → S3-10        → GtS3SimplifiedRetro2
 *
 * 核心特性：
 * - NO internal el-tabs — 仅 sheetName v-if 分发
 * - selfLoad: htmlData 为 null 时自行调 render-config 加载数据
 * - S3-1 区分三类事项：会计政策变更 / 前期差错更正 / 会计估计变更
 * - 非经常性损益标注（Req 6.4）
 * - 使用 useS3AdjustmentEngine composable 进行 reactive 计算
 * - S3 参考sheet（1979公式）保留为 OO fallback
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 4.4
 * Requirements: 1.5, 6.2, 6.3, 6.4
 */
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'

// ─── Lazy-loaded child components ────────────────────────────────────────────

const GtS3Adjudication = defineAsyncComponent(() => import('./GtS3Adjudication.vue'))
const GtS3PolicyError = defineAsyncComponent(() => import('./GtS3PolicyError.vue'))
const GtS3EstimateChange = defineAsyncComponent(() => import('./GtS3EstimateChange.vue'))
const GtS3Ifrs9Adjust = defineAsyncComponent(() => import('./GtS3Ifrs9Adjust.vue'))
const GtS3Ifrs15Adjust = defineAsyncComponent(() => import('./GtS3Ifrs15Adjust.vue'))
const GtS3Ifrs16Adjust = defineAsyncComponent(() => import('./GtS3Ifrs16Adjust.vue'))
const GtS3SimplifiedRetro1 = defineAsyncComponent(() => import('./GtS3SimplifiedRetro1.vue'))
const GtS3SimplifiedRetro2 = defineAsyncComponent(() => import('./GtS3SimplifiedRetro2.vue'))

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
 * GtWpRenderer 传入完整 sheetName（如"审定表"），正则匹配后路由。
 *
 * 映射表：
 *   审定表                                    → adjudication
 *   会计政策变更和前期差错更正S3-1             → S3-1
 *   会计估计变更审计程序S3-2                   → S3-2
 *   首次执行新金融工具准则的调整S3-4           → S3-4
 *   首次执行新收入准则的调整S3-6               → S3-6
 *   首次执行新租赁准则的调整S3-8               → S3-8
 *   简化的追溯调整法（1）S3-9                  → S3-9
 *   简化的追溯调整法（2）S3-10                 → S3-10
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // GT_Custom → skip
  if (name === 'GT_Custom') return 'skip'

  // S3-10 先匹配（避免被 S3-1 匹配吞掉）
  if (name.match(/S3-10/) || name.includes('简化的追溯调整法（2）')) return 'S3-10'

  // S3-9
  if (name.match(/S3-9/) || name.includes('简化的追溯调整法（1）')) return 'S3-9'

  // S3-8
  if (name.match(/S3-8/) || name.includes('新租赁准则')) return 'S3-8'

  // S3-6
  if (name.match(/S3-6/) || name.includes('新收入准则')) return 'S3-6'

  // S3-4
  if (name.match(/S3-4/) || name.includes('新金融工具准则')) return 'S3-4'

  // S3-2
  if (name.match(/S3-2/) || name.includes('会计估计变更')) return 'S3-2'

  // S3-1
  if (name.match(/S3-1/) || name.includes('会计政策变更和前期差错')) return 'S3-1'

  // 审定表
  if (name.includes('审定表')) return 'adjudication'

  // 表头 → skip
  if (name.includes('表头') || name.includes('请先填写')) return 'skip'

  // 参考sheet → OO fallback（1979公式）
  if (name.includes('参考')) return name

  // 副本 S3-10 (2) → 合并入 S3-10
  if (name.includes('S3-10 (2)') || name.includes('简化的追溯调整法（2）S3-10 (2)')) return 'S3-10'

  // 空 sheetName → 默认显示审定表
  if (name === '' || name === 'S3') return 'adjudication'

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

/** 8 个内部 sheet 为 HTML sheet */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['adjudication', 'S3-1', 'S3-2', 'S3-4', 'S3-6', 'S3-8', 'S3-9', 'S3-10'].includes(s)
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
    console.warn('[GtS3PolicyChange] selfLoad failed:', err)
  }

  isLoading.value = false
}

provide('reloadWorkpaperData', selfLoad)

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
  wpCode: 'S3',
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onRefresh: () => selfLoad(),
  isReadonly,
})

// provide 给子组件用（S3-1 会计政策变更披露可发布披露文本）
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
.s3-policy-change {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.s3-toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
