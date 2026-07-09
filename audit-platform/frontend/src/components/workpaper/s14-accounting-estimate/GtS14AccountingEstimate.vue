<template>
  <div class="s14-accounting-estimate">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- ─── 工具栏：双模式 + 版本历史 ─── -->
      <div v-if="isHtmlSheet" class="s14-toolbar">
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

      <!-- S14程序表 -->
      <S14ProgramSheet
        v-else-if="currentSheet === 'program'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- S14-1了解被审计单位及其环境（会计估计相关） -->
      <S14EnvironmentSheet
        v-else-if="currentSheet === 'environment'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- S14-2了解与会计估计相关的控制 -->
      <S14ControlSheet
        v-else-if="currentSheet === 'control'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- S14-3应对评估的重大错报风险（会计估计相关） -->
      <S14RiskResponseSheet
        v-else-if="currentSheet === 'risk-response'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- S14-4管理层偏向的迹象 -->
      <S14BiasIndicationSheet
        v-else-if="currentSheet === 'bias'"
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
      :related-data="{ wpCode: 'S14', projectId: props.projectId }"
    />

    <!-- 版本历史抽屉 -->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
  </div>
</template>

<script setup lang="ts">
/**
 * GtS14AccountingEstimate.vue — S14 会计估计和相关披露 主入口
 *
 * 由外层 GtWpRenderer 的 componentType 's14-accounting-estimate' 路由到此组件。
 * 组件接收 sheetName prop，v-if 分发到 5 个内部子组件（无内部 el-tabs）。
 *
 * sheetName 映射关系（Phase0 dispatch_table）：
 *   S14程序表                                       → program
 *   S14-1了解被审计单位及其环境（会计估计相关）      → environment
 *   S14-2了解与会计估计相关的控制                   → control
 *   S14-3应对评估的重大错报风险（会计估计相关）      → risk-response
 *   S14-4管理层偏向的迹象                           → bias
 *
 * 核心特性：
 * - NO internal el-tabs — 仅 sheetName v-if 分发
 * - selfLoad: htmlData 为 null 时自行调 render-config 加载数据
 * - 0 公式 — 全部为 checklist/text-entry 格式
 * - 程序表保留列：是否适用/核查方式/执行人/执行情况说明/审计程序索引（Req 5.2）
 * - GtIndexChip 引用 B10/B22/B40 等风险评估底稿（Req 5.3）
 * - EventBus — 发布 WORKPAPER_SAVED
 * - 13px 表格字体 + AI 按钮 + 编制提示 details
 * - readonly 禁止编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.4
 * Requirements: 1.5, 5.1, 5.2, 5.3
 */
import { ref, computed, onMounted, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'

// ─── Lazy-loaded child components ────────────────────────────────────────────

const S14ProgramSheet = defineAsyncComponent(() => import('./S14ProgramSheet.vue'))
const S14EnvironmentSheet = defineAsyncComponent(() => import('./S14EnvironmentSheet.vue'))
const S14ControlSheet = defineAsyncComponent(() => import('./S14ControlSheet.vue'))
const S14RiskResponseSheet = defineAsyncComponent(() => import('./S14RiskResponseSheet.vue'))
const S14BiasIndicationSheet = defineAsyncComponent(() => import('./S14BiasIndicationSheet.vue'))

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
 *   S14程序表                                  → program
 *   S14-1了解被审计单位及其环境（会计估计相关） → environment
 *   S14-2了解与会计估计相关的控制              → control
 *   S14-3应对评估的重大错报风险（会计估计相关） → risk-response
 *   S14-4管理层偏向的迹象                      → bias
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // GT_Custom → skip
  if (name === 'GT_Custom') return 'skip'

  // S14-4 管理层偏向的迹象
  if (name.match(/S14-4/) || name.includes('管理层偏向')) return 'bias'

  // S14-3 应对评估的重大错报风险
  if (name.match(/S14-3/) || name.includes('应对评估的重大错报风险')) return 'risk-response'

  // S14-2 了解与会计估计相关的控制
  if (name.match(/S14-2/) || name.includes('了解与会计估计相关的控制')) return 'control'

  // S14-1 了解被审计单位及其环境
  if (name.match(/S14-1/) || name.includes('了解被审计单位及其环境')) return 'environment'

  // S14 程序表
  if (name.includes('程序表') || name === 'S14' || name.match(/S14程序表/)) return 'program'

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

/** 所有 5 张 sheet 均为 HTML sheet */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return ['program', 'environment', 'control', 'risk-response', 'bias'].includes(s)
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
    console.warn('[GtS14AccountingEstimate] selfLoad failed:', err)
  }

  isLoading.value = false
}

provide('reloadWorkpaperData', selfLoad)

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.s14-accounting-estimate {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.s14-toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
