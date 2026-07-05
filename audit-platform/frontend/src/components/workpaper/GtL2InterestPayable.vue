<template>
  <div class="l2-interest-payable">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <div v-if="isProcedureSheet" class="l2-procedure-toolbar">
        <el-segmented
          v-model="procedureDualMode.currentMode.value"
          :options="procedureDualMode.modeOptions.value"
          size="small"
          @change="procedureDualMode.onModeChange"
        />
        <el-tag v-if="!procedureDualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="isProcedureSheet && procedureDualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || 'L2A'"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- L2 主sheet 底稿目录 -->
      <L2TabIndex
        v-else-if="currentSheet === 'L2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 L2A -->
      <CycleTabProcedure
        v-else-if="currentSheet === 'L2A'"
        sheet-code="L2A"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L2-1 审定表 -->
      <L2TabAdjudication
        v-else-if="currentSheet === 'L2-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L2-2 明细表 -->
      <L2TabDetail
        v-else-if="currentSheet === 'L2-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L2-3 调整分录 -->
      <L2TabAdjustment
        v-else-if="currentSheet === 'L2-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- L2-4 应付利息检查表 -->
      <L2TabInterestCheck
        v-else-if="currentSheet === 'L2-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- 附注（上市/国企） -->
      <L2TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <L2TabDisclosureSoe
        v-else-if="currentSheet === '附注国企'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- OnlyOffice fallback: 未迁移 sheet -->
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
      :related-data="{ wpCode: 'L2', projectId: props.projectId }"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * GtL2InterestPayable.vue — L2 应付利息底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取末尾编码（L2/L2-1~L2-4/L2A），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：2231 应付利息（贷方/负债类！期末=期初+贷方-借方）
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成：
 * - EventBus: substantive:adjudicated / l1:interest-calculated / l3:interest-calculated
 * - 跨底稿联动: 接收L1/L3利息测算，联动L8财务费用
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, onMounted, provide, defineAsyncComponent, toRef } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import { useCycleHtmlOoDualMode } from './composables/useCycleHtmlOoDualMode'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import useVersionTrail from './composables/useVersionTrail'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const L2TabIndex = defineAsyncComponent(() => import('./l2/core/L2TabIndex.vue'))
const L2TabAdjudication = defineAsyncComponent(() => import('./l2/core/L2TabAdjudication.vue'))
const L2TabDetail = defineAsyncComponent(() => import('./l2/core/L2TabDetail.vue'))
const L2TabAdjustment = defineAsyncComponent(() => import('./l2/core/L2TabAdjustment.vue'))
const L2TabDisclosureListed = defineAsyncComponent(() => import('./l2/core/L2TabDisclosureListed.vue'))
const L2TabDisclosureSoe = defineAsyncComponent(() => import('./l2/core/L2TabDisclosureSoe.vue'))

// Inspection
const L2TabInterestCheck = defineAsyncComponent(() => import('./l2/inspection/L2TabInterestCheck.vue'))

// Shared
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtReviewDialog = defineAsyncComponent(() => import('@/components/collaboration/GtReviewDialog.vue'))

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

/**
 * L2TabIndex 目录行点击→通知外层 GtWpRenderer 切换 sheetName。
 * 外层通过 sheet 目录行 chips 控制 sheetName prop，此处 emit 向上传递请求。
 */
function handleNavigate(sheetName: string) {
  parentEmit('navigate', sheetName)
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

/**
 * 当前激活的 sheet（由外层 GtWpRenderer 通过 sheetName prop 控制）。
 * GtWpRenderer 传入完整 sheet_name（如"审定表L2-1"），
 * 正则提取末尾编码（L2/L2-1~L2-4/L2A）来匹配子组件。
 */
const currentSheet = computed(() => {
  const name = props.sheetName || 'L2'
  // 提取末尾的L2编码（L2/L2A/L2-1~L2-4）
  const match = name.match(/L2(?:-\d+)?[A-Z]?$|L2$/)
  if (match) return match[0]
  // 附注特殊匹配
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企')) return '附注国企'
  return name
})

const isProcedureSheet = computed(() => currentSheet.value === 'L2A')
const procedureDualMode = useCycleHtmlOoDualMode({
  wpId: toRef(props, 'wpId') as any,
  storagePrefix: 'l2-proc:',
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

// ─── 版本追踪 useVersionTrail (autoSnapshot) ────────────────────────────────

const versionTrail = useVersionTrail({
  projectId: toRef(props, 'projectId') as any,
  workpaperId: toRef(props, 'wpId') as any,
})

provide('versionTrail', versionTrail)

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
    console.warn('[GtL2InterestPayable] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.l2-interest-payable {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.l2-procedure-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
</style>
