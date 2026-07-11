<template>
  <div class="m8-general-risk-reserve">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 行业守卫：非金融企业提示 -->
    <div v-else-if="!isFinancialEntity" class="industry-guard">
      <el-empty description="一般风险准备仅适用金融企业（银行、证券、保险等）">
        <el-button type="primary" @click="markNotApplicable">标记为不适用</el-button>
      </el-empty>
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- 双模式切换（HTML / OnlyOffice） -->
      <div v-if="currentSheet !== 'index' && currentSheet !== 'procedure'" class="mode-toggle-bar">
        <el-segmented v-model="viewMode" :options="modeOptions" size="small" />
      </div>

      <!-- HTML 结构化模式 -->
      <template v-if="viewMode === 'html'">
        <!-- M8 底稿目录 -->
        <M8TabIndex
          v-if="currentSheet === 'index'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          @navigate="handleNavigate"
        />
        <!-- 程序表 M8A（复用 GtAProgramConsole） -->
        <GtAProgramConsole
          v-else-if="currentSheet === 'procedure'"
          :wp-id="props.wpId"
          sheet-name="M8A"
          :schema="{ columns: [], rows: [] }"
          :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
          :readonly="isReadonly"
        />
        <!-- M8-1 审定表（权益类贷方！期末=期初+贷方-借方） -->
        <M8TabAdjudication
          v-else-if="currentSheet === 'M8-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          @navigate="handleNavigate"
        />
        <!-- M8-2 明细表（22公式，权益类计提明细） -->
        <M8TabDetail
          v-else-if="currentSheet === 'M8-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          @navigate="handleNavigate"
        />
        <!-- M8-3 调整分录汇总（借贷平衡） -->
        <M8TabAdjustment
          v-else-if="currentSheet === 'M8-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          @navigate="handleNavigate"
        />
        <!-- M8-4 一般风险准备测试表（风险资产计提测试，13公式） -->
        <M8TabRiskTest
          v-else-if="currentSheet === 'M8-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          @navigate="handleNavigate"
        />
        <!-- 附注披露信息（上市公司） -->
        <M8TabDisclosureListed
          v-else-if="currentSheet === 'disclosure-listed'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          @navigate="handleNavigate"
        />
        <!-- 附注披露信息（国有企业） -->
        <M8TabDisclosureSoe
          v-else-if="currentSheet === 'disclosure-soe'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
          @navigate="handleNavigate"
        />
        <!-- OnlyOffice fallback: 未迁移 sheet / Q8A修订前 / 针对性测试删除 -->
        <GtOnlyOfficeSheet
          v-else
          :wp-id="props.wpId"
          :sheet-name="props.sheetName"
          style="height: 100%; min-height: 600px"
        />
      </template>

      <!-- OnlyOffice 原始模式 -->
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
      :related-data="{ wpCode: 'M8', projectId: props.projectId }"
    />

    <!-- 版本历史抽屉 -->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
  </div>
</template>

<script setup lang="ts">
/**
 * GtM8GeneralRiskReserve.vue — M8 一般风险准备底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，正则提取编码（M8/M8A/M8-1~M8-4），v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题）。
 *
 * 科目覆盖：4104 一般风险准备（**贷方/权益类！**）
 * 核心铁律：期末=期初+贷方-借方（计提时贷方增加，转回/使用时借方减少）
 * 特殊功能：①权益类贷方公式 ②金融企业行业守卫 ③按风险资产期末余额计提测试（1.5%）
 *
 * selfLoad: 当 htmlData 为 null 时自行调 render-config 加载数据。
 * 行业守卫: 非金融企业（银行/证券/保险）不适用，可标记不适用。
 *
 * 集成（Phase 6）：
 * - EventBus: substantive:adjudicated(4104) / adjustment:created
 * - 跨底稿联动: TB回写(4104一般风险准备)
 * - 版本追踪: useVersionTrail(autoSnapshot)
 * - 复核对话: provide openReviewDialog → 子组件 inject
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'

// ─── Lazy-loaded child components ────────────────────────────────────────────

// Core
const M8TabIndex = defineAsyncComponent(() => import('./m8/core/M8TabIndex.vue'))
const M8TabAdjudication = defineAsyncComponent(() => import('./m8/core/M8TabAdjudication.vue'))
const M8TabDetail = defineAsyncComponent(() => import('./m8/core/M8TabDetail.vue'))
const M8TabAdjustment = defineAsyncComponent(() => import('./m8/core/M8TabAdjustment.vue'))
const M8TabDisclosureListed = defineAsyncComponent(() => import('./m8/core/M8TabDisclosureListed.vue'))
const M8TabDisclosureSoe = defineAsyncComponent(() => import('./m8/core/M8TabDisclosureSoe.vue'))

// Calc
const M8TabRiskTest = defineAsyncComponent(() => import('./m8/calc/M8TabRiskTest.vue'))

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
 * M8TabIndex 目录行点击→通知外层 GtWpRenderer 切换 sheetName。
 * 注意：GtWpRenderer 监听 @navigate-sheet，故此处必须 emit 'navigate-sheet'。
 */
function handleNavigate(sheetName: string) {
  parentEmit('navigate-sheet', sheetName)
}

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

// ─── 双模式切换 ──────────────────────────────────────────────────────────────

const viewMode = ref<'html' | 'oo'>('html')
const modeOptions = [
  { label: '结构化', value: 'html' },
  { label: 'OnlyOffice', value: 'oo' },
]

// ─── 行业守卫（金融企业适用性） ──────────────────────────────────────────────

/**
 * 判断当前审计项目是否为金融企业（银行、证券、保险等）。
 * 从 render-config 返回的 project_info 或 checklist_responses 中读取行业属性。
 * 默认假设适用（避免阻塞加载），在 selfLoad 后根据实际数据更新。
 */
const isFinancialEntity = ref(true)
const FINANCIAL_INDUSTRIES = ['金融', '银行', '证券', '保险', '信托', '基金', '期货', '金融租赁']

function checkIndustryApplicability(projectInfo: any): boolean {
  if (!projectInfo) return true // 无数据时默认适用
  const industry = projectInfo.industry || projectInfo.client_industry || ''
  return FINANCIAL_INDUSTRIES.some((keyword) => industry.includes(keyword))
}

function markNotApplicable() {
  // 标记为不适用（保存到 checklist_responses）
  // item_id 与 useM8CrossSheet 读取的 'M8-industry-guard' 一致
  // conclusion 存储 "not-applicable"，useM8CrossSheet 降级判断时读取此值
  http
    .put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: 'M8-industry-guard', conclusion: 'not-applicable', remark: null }],
    })
    .catch(() => {})
}

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
 * GtWpRenderer 传入完整 sheet_name（如"审定表M8-1"），
 * 正则提取编码来匹配子组件。
 *
 * 映射关系：
 *   底稿目录                              → index             → M8TabIndex
 *   一般风险准备实质性程序表M8A           → procedure         → GtAProgramConsole (复用)
 *   审定表M8-1                            → M8-1              → M8TabAdjudication（权益类贷方！）
 *   明细表M8-2                            → M8-2              → M8TabDetail（计提明细22公式）
 *   调整分录汇总M8-3                      → M8-3              → M8TabAdjustment
 *   一般风险准备测试表M8-4                → M8-4              → M8TabRiskTest（风险资产计提测试13公式）
 *   附注披露信息（上市公司）              → disclosure-listed → M8TabDisclosureListed
 *   附注披露信息（国有企业）              → disclosure-soe    → M8TabDisclosureSoe
 *   Q8A修订前/针对性测试删除/参考        → OO fallback       → GtOnlyOfficeSheet
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // 提取 M8-N 编码（M8-1 ~ M8-4）
  const codeMatch = name.match(/M8-[1-4]/)
  if (codeMatch) return codeMatch[0]

  // 程序表 M8A
  if (name.match(/M8A/) || name.includes('实质性程序表')) return 'procedure'

  // 附注特殊匹配
  if (name.includes('上市公司')) return 'disclosure-listed'
  if (name.includes('国有企业')) return 'disclosure-soe'

  // 底稿目录（默认）
  if (name.includes('底稿目录') || name === 'M8' || name === '') return 'index'

  // 未匹配（Q8A修订前/针对性测试删除/会计规定辅助等）→ OO fallback
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

// ─── 监听 m8:save-items → 保存后自动快照 ────────────────────────────────────

function handleM8SaveItems(_e: Event): void {
  versionToolbar.scheduleAutoSnapshot()
}

// ─── selfLoad ────────────────────────────────────────────────────────────────

async function selfLoad() {
  if (props.htmlData) {
    // 从 props 提供的数据初始化
    // props.htmlData 来自 GtWpRenderer 传入的当前 sheet 的 html_data
    // M8 renderer 返回 { component_type, sheets, project_info, tb_snapshot, ... }
    const projectInfo = props.htmlData?.project_info
    isFinancialEntity.value = checkIndustryApplicability(projectInfo)
    isLoading.value = false
    return
  }

  // 当 htmlData 为空时（bundle 内嵌场景），自行加载 render-config
  try {
    const res = await http.get(
      `/api/workpapers/${props.wpId}/render-config?force_component_type=m8-general-risk-reserve`,
      { _silent: true } as any,
    )
    const data = (res as any)?.data ?? res
    // render-config 返回 { sheets: [{ html_data: { project_info, ... } }] }
    const firstSheet = data?.sheets?.[0]?.html_data
    const projectInfo = firstSheet?.project_info || data?.project_info
    isFinancialEntity.value = checkIndustryApplicability(projectInfo)
  } catch (err) {
    console.warn('[GtM8GeneralRiskReserve] selfLoad failed:', err)
  }

  isLoading.value = false
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  window.addEventListener('m8:save-items', handleM8SaveItems)
  selfLoad()
})

onBeforeUnmount(() => {
  window.removeEventListener('m8:save-items', handleM8SaveItems)
})
</script>

<style scoped>
.m8-general-risk-reserve {
  padding: 12px;
}

.loading-container {
  padding: 24px;
}

.industry-guard {
  padding: 48px 24px;
  text-align: center;
}

.mode-toggle-bar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
  padding: 0 4px;
}
</style>
