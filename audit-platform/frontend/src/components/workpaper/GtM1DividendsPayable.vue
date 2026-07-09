<template>
  <div class="m1-dividends-payable">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- M1 底稿目录 -->
      <M1TabIndex
        v-if="currentSheet === 'index'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @navigate="handleNavigate"
      />
      <!-- 程序表 M1A（复用 GtAProgramConsole） -->
      <GtAProgramConsole
        v-else-if="currentSheet === 'procedure'"
        :wp-id="props.wpId"
        sheet-name="M1A"
        :schema="{ columns: [], rows: [] }"
        :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
        :readonly="isReadonly"
      />
      <!-- M1-1 审定表（负债类贷方+按股东分类+小计） -->
      <M1TabAdjudication
        v-else-if="currentSheet === 'M1-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- 附注披露信息（上市公司） -->
      <M1TabDisclosureListed
        v-else-if="currentSheet === 'disclosure-listed'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- 附注披露信息（国有企业） -->
      <M1TabDisclosureSoe
        v-else-if="currentSheet === 'disclosure-soe'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- M1-2 明细表（按股东列示，27列区段Tab） -->
      <M1TabDetail
        v-else-if="currentSheet === 'M1-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- M1-3 调整分录汇总（借贷平衡） -->
      <M1TabAdjustment
        v-else-if="currentSheet === 'M1-3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- M1-4 外币汇率测算表（13公式） -->
      <M1TabFxRate
        v-else-if="currentSheet === 'M1-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- M1-5 应付股利（利润）测算表（接收M6，13公式） -->
      <M1TabDividendCalc
        v-else-if="currentSheet === 'M1-5'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />
      <!-- M1-6 应付股利（利润）检查表 -->
      <M1TabDividendCheck
        v-else-if="currentSheet === 'M1-6'"
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
      :related-data="{ wpCode: 'M1', projectId: props.projectId }"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * GtM1DividendsPayable.vue — M1 应付股利（利润）底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取编码（M1/M1A/M1-1~M1-6），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：2232 应付股利（贷方/负债类！期末=期初+贷方-借方）
 * M股东权益循环唯一负债类科目，宣告分配在贷方增加，实际支付在借方减少。
 * 特殊功能：①外币汇率折算(M1-4) ②接收M6利润分配股利联动(M1-5) ③按股东分类
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated(2232) / adjustment:created / m6:profit-distributed(订阅)
 * - 跨底稿联动: TB回写(2232) + M6利润分配→股利测算核对
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, onMounted, provide, defineAsyncComponent, toRef } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import useVersionTrail from './composables/useVersionTrail'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const M1TabIndex = defineAsyncComponent(() => import('./m1/core/M1TabIndex.vue'))
const M1TabAdjudication = defineAsyncComponent(() => import('./m1/core/M1TabAdjudication.vue'))
const M1TabDetail = defineAsyncComponent(() => import('./m1/core/M1TabDetail.vue'))
const M1TabAdjustment = defineAsyncComponent(() => import('./m1/core/M1TabAdjustment.vue'))
const M1TabDisclosureListed = defineAsyncComponent(() => import('./m1/core/M1TabDisclosureListed.vue'))
const M1TabDisclosureSoe = defineAsyncComponent(() => import('./m1/core/M1TabDisclosureSoe.vue'))

// Calc (外币汇率 + 股利测算)
const M1TabFxRate = defineAsyncComponent(() => import('./m1/calc/M1TabFxRate.vue'))
const M1TabDividendCalc = defineAsyncComponent(() => import('./m1/calc/M1TabDividendCalc.vue'))

// Inspection (检查表)
const M1TabDividendCheck = defineAsyncComponent(() => import('./m1/inspection/M1TabDividendCheck.vue'))

// Shared
const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))
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
 * M1TabIndex 目录行点击→通知外层 GtWpRenderer 切换 sheetName。
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

// ─── sheetName → 子组件分发 ──────────────────────────────────────────────────

/**
 * 当前激活的 sheet（由外层 GtWpRenderer 通过 sheetName prop 控制）。
 * GtWpRenderer 传入完整 sheet_name（如"审定表M1-1"），
 * 正则提取编码来匹配子组件。
 *
 * 映射关系：
 *   底稿目录                    → index    → M1TabIndex
 *   应付股利实质性程序表M1      → procedure → GtAProgramConsole (复用)
 *   审定表M1-1                  → M1-1     → M1TabAdjudication
 *   附注披露信息（上市公司）    → disclosure-listed → M1TabDisclosureListed
 *   附注披露信息（国有企业）    → disclosure-soe    → M1TabDisclosureSoe
 *   明细表M1-2                  → M1-2     → M1TabDetail
 *   调整分录汇总M1-3            → M1-3     → M1TabAdjustment
 *   外币汇率测算表M1-4          → M1-4     → M1TabFxRate
 *   应付股利（利润）测算表M1-5  → M1-5     → M1TabDividendCalc
 *   应付股利（利润）检查表M1-6  → M1-6     → M1TabDividendCheck
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // 提取 M1-N 编码（M1-1 ~ M1-6）
  const codeMatch = name.match(/M1-[1-6]/)
  if (codeMatch) return codeMatch[0]

  // 程序表 M1A
  if (name.match(/M1A/) || name.includes('实质性程序表')) return 'procedure'

  // 附注特殊匹配
  if (name.includes('上市公司')) return 'disclosure-listed'
  if (name.includes('国有企业')) return 'disclosure-soe'

  // 底稿目录（默认）
  if (name.includes('底稿目录') || name === 'M1' || name === '') return 'index'

  // 未匹配 → OO fallback
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
    console.warn('[GtM1DividendsPayable] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.m1-dividends-payable {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}
</style>
