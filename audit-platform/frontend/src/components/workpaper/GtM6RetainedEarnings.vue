<template>
  <div class="m6-retained-earnings">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- M6 底稿目录 -->
      <M6TabIndex
        v-if="currentSheet === 'index'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 M6A（复用 GtAProgramConsole） -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'procedure'"
        :wp-id="props.wpId"
        sheet-name="M6A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- M6-1 审定表（权益类贷方！期末=期初+贷方-借方） -->
      <M6TabAdjudication
        v-else-if="currentSheet === 'M6-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M6-2 明细表（利润分配结转公式链！核心！） -->
      <M6TabDetail
        v-else-if="currentSheet === 'M6-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M6-3 调整分录汇总（借贷平衡） -->
      <M6TabAdjustment
        v-else-if="currentSheet === 'M6-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- M6-4 未分配利润检查表 -->
      <M6TabRetainedCheck
        v-else-if="currentSheet === 'M6-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注披露信息（上市公司） -->
      <M6TabDisclosureListed
        v-else-if="currentSheet === 'disclosure-listed'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 附注披露信息（国有企业） -->
      <M6TabDisclosureSoe
        v-else-if="currentSheet === 'disclosure-soe'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- Q6A修订前 sheet → 跳过/fallback -->
      <div v-else-if="currentSheet === 'skip-q6a'" class="skip-sheet-placeholder">
        <el-empty description="Q6A修订前sheet已跳过（无需编制）" />
      </div>
      <!-- OnlyOffice fallback: 未迁移 sheet / 参考辅助 -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :sheet-name="props.sheetName"
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
      :related-data="{ wpCode: 'M6', projectId: props.projectId }"
    />

    <!-- 版本历史抽屉 -->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
  </div>
</template>

<script setup lang="ts">
/**
 * GtM6RetainedEarnings.vue — M6 未分配利润底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取编码（M6/M6A/M6-1~M6-4），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：4104 利润分配-未分配利润（**贷方/权益类！**）
 * 核心铁律：期末=期初+贷方-借方（本年净利润转入时贷方增加，分配时借方减少）
 * 特殊功能：①权益类贷方公式 ②利润分配结转核心公式链（期末=期初+净利润-盈余公积-股利）
 *           ③上游接收本年利润 ④下游驱动M5盈余公积计提+M1股利分配 ⑤TB回写(4104)
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated(4104) / 'm6:net-profit' / 'm6:profit-distributed'
 * - 订阅: 'm5:surplus-accrual' / 'm1:declared-confirmed' / adjustment:created
 * - 跨底稿联动: TB回写(4104) + M6净利润→M5计提基数 + M6分配股利→M1
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const M6TabIndex = defineAsyncComponent(() => import('./m6/core/M6TabIndex.vue'))
const M6TabAdjudication = defineAsyncComponent(() => import('./m6/core/M6TabAdjudication.vue'))
const M6TabDetail = defineAsyncComponent(() => import('./m6/core/M6TabDetail.vue'))
const M6TabAdjustment = defineAsyncComponent(() => import('./m6/core/M6TabAdjustment.vue'))
const M6TabDisclosureListed = defineAsyncComponent(() => import('./m6/core/M6TabDisclosureListed.vue'))
const M6TabDisclosureSoe = defineAsyncComponent(() => import('./m6/core/M6TabDisclosureSoe.vue'))

// Inspection
const M6TabRetainedCheck = defineAsyncComponent(() => import('./m6/inspection/M6TabRetainedCheck.vue'))

// Shared
const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtReviewDialog = defineAsyncComponent(() => import('@/components/collaboration/GtReviewDialog.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

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
  (e: 'navigate-sheet', sheetName: string): void
}>()

/**
 * M6TabIndex 目录行点击→通知外层 GtWpRenderer 切换 sheetName。
 * 注意：GtWpRenderer 监听 @navigate-sheet，故此处必须 emit 'navigate-sheet'。
 */
function handleNavigate(sheetName: string) {
  parentEmit('navigate-sheet', sheetName)
}

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

// ─── Auth (for review dialog) ────────────────────────────────────────────────

const authStore = useAuthStore()
const currentUser = computed(() => ({
  id: authStore.userId || '',
  name: authStore.user?.full_name || authStore.username || '',
  role: (authStore.user?.role || '审计助理') as any,
}))

// ─── sheetName → 子组件分发 ──────────────────────────────────────────────────

/**
 * 当前激活的 sheet（由外层 GtWpRenderer 通过 sheetName prop 控制）。
 * GtWpRenderer 传入完整 sheet_name（如"审定表M6-1"），
 * 正则提取编码来匹配子组件。
 *
 * 映射关系：
 *   底稿目录                         → index              → M6TabIndex
 *   未分配利润实质性程序表M6A        → procedure          → GtAProgramConsole (复用)
 *   审定表M6-1                       → M6-1               → M6TabAdjudication（权益类贷方！）
 *   明细表M6-2                       → M6-2               → M6TabDetail（利润分配结转公式链！）
 *   调整分录汇总M6-3                 → M6-3               → M6TabAdjustment
 *   未分配利润检查表M6-4             → M6-4               → M6TabRetainedCheck
 *   附注披露信息（上市公司）         → disclosure-listed  → M6TabDisclosureListed
 *   附注披露信息（国有企业）         → disclosure-soe     → M6TabDisclosureSoe
 *   Q6A修订前                        → skip-q6a           → placeholder (跳过)
 *   参考－会计规定                   → OO fallback        → GtOnlyOfficeSheet
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // Q6A修订前 sheet → 跳过
  if (name.includes('Q6A') && name.includes('修订前')) return 'skip-q6a'

  // 提取 M6-N 编码（M6-1 ~ M6-4）
  const codeMatch = name.match(/M6-[1-4]/)
  if (codeMatch) return codeMatch[0]

  // 程序表 M6A
  if (name.match(/M6A/) || name.includes('实质性程序表')) return 'procedure'

  // 附注特殊匹配
  if (name.includes('上市公司')) return 'disclosure-listed'
  if (name.includes('国有企业')) return 'disclosure-soe'

  // 底稿目录（默认）
  if (name.includes('底稿目录') || name === 'M6' || name === '') return 'index'

  // 未匹配（会计规定辅助等）→ OO fallback
  return name
})

// ─── Provide openReviewDialog ────────────────────────────────────────────────

/** 复核对话状态 */
const reviewDialogVisible = ref(false)
const reviewDialogSectionId = ref('')
const reviewDialogSectionLabel = ref('')

/**
 * 子组件 inject 后在 section 标题栏右侧放复核按钮。
 * 点击调用 openReviewDialog(sectionId, sectionLabel?) 打开复核对话面板。
 */
function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  reviewDialogSectionId.value = sectionId
  reviewDialogSectionLabel.value = sectionLabel || sectionId
  reviewDialogVisible.value = true
}

provide('openReviewDialog', openReviewDialog)

// ─── 版本追踪 useWorkpaperVersionToolbar (autoSnapshot on save) ──────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar

provide('versionTrail', versionToolbar)
provide('openVersionHistory', () => versionToolbar.openVersionHistory())

// ─── 监听 m6:save-items → 保存后自动快照 ────────────────────────────────────

function handleM6SaveItems(_e: Event): void {
  versionToolbar.scheduleAutoSnapshot()
}

// ─── selfLoad ────────────────────────────────────────────────────────────────

async function selfLoad() {
  if (props.htmlData) {
    // 从 props 提供的数据初始化
    isLoading.value = false
    return
  }

  // 当 htmlData 为空时（bundle 内嵌场景），自行加载 render-config
  try {
    await http.get(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
  } catch (err) {
    console.warn('[GtM6RetainedEarnings] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  window.addEventListener('m6:save-items', handleM6SaveItems)
  selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('m6:save-items', handleM6SaveItems)
})
</script>

<style scoped>
.m6-retained-earnings {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.skip-sheet-placeholder {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
}
</style>
