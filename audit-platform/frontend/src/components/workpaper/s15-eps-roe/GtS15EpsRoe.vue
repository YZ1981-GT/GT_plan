<template>
  <div class="s15-eps-roe">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- ─── 工具栏：双模式 + 版本历史 ─── -->
      <div v-if="isHtmlSheet" class="s15-toolbar">
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

      <!-- 审定表 S15-1 -->
      <GtS15Adjudication
        v-else-if="currentSheet === 'adjudication'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- 审计程序 S15 -->
      <GtS15Program
        v-else-if="currentSheet === 'program'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- S15-2 基本每股收益计算表 -->
      <GtS15BasicEps
        v-else-if="currentSheet === 'S15-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- S15-3 稀释每股收益计算表 -->
      <GtS15DilutedEps
        v-else-if="currentSheet === 'S15-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- S15-4 净资产收益率计算 -->
      <GtS15Roe
        v-else-if="currentSheet === 'S15-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
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
      :related-data="{ wpCode: 'S15', projectId: props.projectId }"
    />

    <!-- 版本历史抽屉 -->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
  </div>
</template>

<script setup lang="ts">
/**
 * GtS15EpsRoe.vue — S15 每股收益和净资产收益率底稿主入口
 *
 * 由外层 GtWpRenderer 的 componentType 's15-eps-roe' 路由到此组件。
 * 组件接收 sheetName prop，v-if 分发到 5 个内部子组件（无内部 el-tabs）。
 *
 * sheetName 映射关系：
 *   审定表S15-1           → adjudication  → GtS15Adjudication
 *   审计程序S15           → program       → GtS15Program
 *   基本每股收益计算表S15-2 → S15-2        → GtS15BasicEps
 *   稀释每股收益计算表S15-3 → S15-3        → GtS15DilutedEps
 *   净资产收益率计算S15-4   → S15-4        → GtS15Roe
 *
 * 核心特性：
 * - NO internal el-tabs — 仅 sheetName v-if 分发
 * - selfLoad: htmlData 为 null 时自行调 render-config 加载数据
 * - S15-2/S15-3/S15-4 同屏对比展示本年/上年两期（Req 3.4）
 * - 公式单元格只读不可手工覆盖（Req 2.5）
 * - eEnd=0 显示"不可计算"（Req 3.5）
 * - 使用 useS15FormulaEngine composable 进行 reactive 计算
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 4.1
 * Requirements: 1.5, 2.5, 3.4, 3.5
 */
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'

// ─── Lazy-loaded child components ────────────────────────────────────────────

const GtS15Adjudication = defineAsyncComponent(() => import('./GtS15Adjudication.vue'))
const GtS15Program = defineAsyncComponent(() => import('./GtS15Program.vue'))
const GtS15BasicEps = defineAsyncComponent(() => import('./GtS15BasicEps.vue'))
const GtS15DilutedEps = defineAsyncComponent(() => import('./GtS15DilutedEps.vue'))
const GtS15Roe = defineAsyncComponent(() => import('./GtS15Roe.vue'))

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
 * GtWpRenderer 传入完整 sheetName（如"审定表S15-1"），正则匹配后路由。
 *
 * 映射表：
 *   审定表S15-1                    → adjudication
 *   审计程序S15                    → program
 *   基本每股收益计算表S15-2        → S15-2
 *   稀释每股收益计算表S15-3        → S15-3
 *   净资产收益率计算S15-4          → S15-4
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // GT_Custom → skip
  if (name === 'GT_Custom') return 'skip'

  // S15-2 ~ S15-4 精确匹配编码
  const codeMatch = name.match(/S15-([2-4])/)
  if (codeMatch) return `S15-${codeMatch[1]}`

  // 审定表
  if (name.includes('审定表') || name.match(/S15-1/)) return 'adjudication'

  // 审计程序
  if (name.includes('审计程序') || name.includes('程序S15')) return 'program'

  // 表头 → skip
  if (name.includes('表头') || name.includes('请先填写')) return 'skip'

  // 空 sheetName → 默认显示审定表
  if (name === '' || name === 'S15') return 'adjudication'

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

/** S15-1 ~ S15-4 + program 为 HTML sheet */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['adjudication', 'program', 'S15-2', 'S15-3', 'S15-4'].includes(s)
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
    console.warn('[GtS15EpsRoe] selfLoad failed:', err)
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
  wpCode: 'S15',
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onRefresh: () => selfLoad(),
  isReadonly,
})

// provide 给子组件用（S15-4 净资产收益率计算可发布披露文本）
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
.s15-eps-roe {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.s15-toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
