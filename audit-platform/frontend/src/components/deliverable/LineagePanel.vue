<!--
  LineagePanel.vue — 出品物溯源面板

  Spec:    deliverable-lineage-and-writeback Task 5.2/5.3/10.1
  Design:  前端设计「Lineage_Panel 组件」
  Reqs:    3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.5, 5.5, 11.4

  功能：
    - 展示当前章节的数据来源清单（来源类型/标识/编辑状态）
    - OnlyOffice 书签 → section_code → 调 trace 端点
    - 跨层跳转（复用 LinkageContract.route）
    - 无锚点降级提示（旧版本出品物）
    - 复用 useLinkageTraceDrawer 抽屉状态，不新建并行面板
    - stale 章节提示"源数据已变更"+ "刷新本章节"/"刷新所有过期"按钮
    - 终态出品物只读：signed/confirmed/archived 禁用刷新按钮
    - SSE LINKAGE_STALE_CHANGED 实时更新 stale 徽标

  UI 规范：全中文化（技术术语保留英文）+ GT 紫令牌
-->
<template>
  <div class="lineage-panel">
    <!-- 面板头部 -->
    <div class="lineage-panel__header">
      <span class="lineage-panel__title">数据溯源</span>
      <el-button
        v-if="currentSectionCode"
        text
        size="small"
        class="lineage-panel__refresh-btn"
        :loading="loading"
        @click="refresh"
      >
        刷新
      </el-button>
    </div>

    <!-- 手动章节溯源（章节列表来自后端 section-states，不依赖 OnlyOffice；允许手动输入兜底旧交付物） -->
    <div v-if="!noAnchorAvailable" class="lineage-panel__manual">
      <el-select
        v-model="manualInput"
        filterable
        allow-create
        clearable
        default-first-option
        size="small"
        placeholder="选择或输入章节号溯源"
        class="lineage-panel__manual-select"
        @change="onManualTrace"
      >
        <el-option
          v-for="opt in sectionOptions"
          :key="opt.code"
          :value="opt.code"
          :label="opt.code"
        >
          <span class="lineage-panel__opt-code">{{ opt.code }}</span>
          <el-tag
            v-if="opt.isStale"
            size="small"
            type="warning"
            effect="light"
            class="lineage-panel__opt-stale"
          >
            已变更
          </el-tag>
        </el-option>
      </el-select>
      <el-button
        size="small"
        :loading="loading"
        class="lineage-panel__manual-btn"
        @click="onManualTrace"
      >
        溯源
      </el-button>
    </div>

    <!-- 无锚点降级提示（需求 3.5） -->
    <div v-if="noAnchorAvailable" class="lineage-panel__no-anchor">
      <el-icon class="lineage-panel__no-anchor-icon"><InfoFilled /></el-icon>
      <span>该出品物版本不支持溯源，请重新生成</span>
    </div>

    <!-- 未选中章节（提示用户输入章节号） -->
    <div v-else-if="!currentSectionCode && !noAnchorAvailable" class="lineage-panel__hint">
      <el-icon><Document /></el-icon>
      <span>请在上方输入章节号后点「溯源」，查看该章节的数据来源</span>
    </div>

    <!-- 加载中 -->
    <div v-else-if="loading" class="lineage-panel__loading">
      <el-skeleton :rows="3" animated />
    </div>

    <!-- 错误提示 -->
    <div v-else-if="error" class="lineage-panel__error">
      <el-alert :title="error" type="warning" :closable="false" show-icon />
    </div>

    <!-- 溯源结果列表 -->
    <div v-else class="lineage-panel__content">
      <!-- 当前章节信息 -->
      <div class="lineage-panel__section-info">
        <span class="lineage-panel__section-label">当前章节</span>
        <span class="lineage-panel__section-code">{{ currentSectionCode }}</span>
        <el-tag
          v-if="sectionState?.is_stale"
          type="warning"
          size="small"
          class="lineage-panel__stale-badge"
        >
          源数据已变更
        </el-tag>
      </div>

      <!-- 刷新操作栏（需求 4.5/5.5/11.4） -->
      <div v-if="currentSectionCode" class="lineage-panel__refresh-toolbar">
        <el-tooltip
          :content="terminalStateTooltip"
          :disabled="!isTerminalState"
          placement="top"
        >
          <span class="lineage-panel__refresh-btn-wrapper">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isTerminalState || refreshingSingle"
              :loading="refreshingSingle"
              class="lineage-panel__action-btn"
              @click="onRefreshSection"
            >
              刷新本章节
            </el-button>
          </span>
        </el-tooltip>
        <el-tooltip
          :content="terminalStateTooltip"
          :disabled="!isTerminalState"
          placement="top"
        >
          <span class="lineage-panel__refresh-btn-wrapper">
            <el-button
              size="small"
              type="warning"
              plain
              :disabled="isTerminalState || refreshingAll"
              :loading="refreshingAll"
              class="lineage-panel__action-btn"
              @click="onRefreshAllStale"
            >
              刷新所有过期
            </el-button>
          </span>
        </el-tooltip>
      </div>

      <!-- 来源列表 -->
      <div v-if="contracts.length > 0" class="lineage-panel__sources">
        <div
          v-for="(contract, idx) in contracts"
          :key="idx"
          class="lineage-panel__source-item"
          @click="onNavigate(contract)"
        >
          <div class="lineage-panel__source-header">
            <el-tag
              :type="getSourceTagType(contract.target_type)"
              size="small"
              class="lineage-panel__source-type"
            >
              {{ getTypeLabel(contract.target_type) }}
            </el-tag>
            <el-tag
              v-if="contract.status === 'stale'"
              type="warning"
              size="small"
              effect="light"
            >
              已过期
            </el-tag>
            <el-tag
              v-else-if="contract.status === 'conflict'"
              type="danger"
              size="small"
              effect="light"
            >
              冲突
            </el-tag>
          </div>
          <div class="lineage-panel__source-body">
            <span class="lineage-panel__source-id">{{ contract.basis || contract.target_id }}</span>
            <el-icon class="lineage-panel__source-jump"><Right /></el-icon>
          </div>
        </div>
      </div>

      <!-- 无来源 -->
      <div v-else class="lineage-panel__empty">
        <span>暂无关联数据来源</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { InfoFilled, Document, Right } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import type { LinkageContract, TargetType } from '@/types/linkageContract'
import {
  useDeliverableLineage,
  anchorNameFromSectionCode,
} from '@/composables/useDeliverableLineage'
import { subscribeProjectEvent } from '@/services/sse/projectEventStream'
import { api } from '@/services/apiProxy'

/** 终态状态列表（signed/confirmed/archived）— 需求 11.4 */
const TERMINAL_STATUSES = ['signed', 'confirmed', 'archived'] as const

const props = defineProps<{
  projectId: string
  wordExportTaskId: string
  /** 是否明确无锚点（旧版本出品物，由父组件判定） */
  hasNoAnchors?: boolean
  /** 出品物当前状态（用于终态检测，需求 11.4） */
  deliverableStatus?: string
  /** 项目年度（刷新接口所需） */
  year?: number
}>()

const wordExportTaskIdRef = computed(() => props.wordExportTaskId)
const projectIdRef = computed(() => props.projectId)

const {
  currentSectionCode,
  contracts,
  sectionState,
  loading,
  error,
  traceFromAnchor,
  traceSection,
  navigateToSource,
  clearSection,
} = useDeliverableLineage(wordExportTaskIdRef, projectIdRef)

/** 是否为无锚点状态（旧版本出品物，需求 3.5） */
const noAnchorAvailable = ref(false)

/** 手动溯源输入（章节号，如「五、1」） */
const manualInput = ref('')

/** 章节下拉候选（来自后端 section-states，含 stale 标记） */
interface SectionOption {
  code: string
  isStale: boolean
}
const sectionOptions = ref<SectionOption[]>([])

/**
 * 加载本交付物的章节列表（section-states 端点），供手动溯源下拉选择。
 * 后端权威、与 OnlyOffice 无关；fail-open：拿不到时下拉为空，仍可手动输入章节号（allow-create）。
 */
async function loadSections(): Promise<void> {
  if (!props.projectId || !props.wordExportTaskId) return
  try {
    const url = `/api/projects/${props.projectId}/deliverables/${props.wordExportTaskId}/section-states`
    const data = await api.get<{ sections: Array<{ section_code: string; is_stale: boolean }> }>(url)
    sectionOptions.value = (data?.sections || [])
      .filter((s) => s.section_code)
      .map((s) => ({ code: s.section_code, isStale: !!s.is_stale }))
  } catch {
    sectionOptions.value = []
  }
}

/**
 * 手动章节溯源：审计师输入/选择章节号后直接调 trace 端点（后端按 section_code 查询，
 * 不依赖 OnlyOffice 连接器/书签，必然可用）。currentSectionCode 是 composable 返回的
 * 响应式 ref，设置 .value 即驱动「当前章节」展示与刷新工具栏。
 */
async function onManualTrace(): Promise<void> {
  const code = manualInput.value.trim()
  if (!code) return
  noAnchorAvailable.value = false
  currentSectionCode.value = code
  await traceSection(code)
}

/** 终态检测（需求 11.4） */
const isTerminalState = computed(() => {
  if (!props.deliverableStatus) return false
  return TERMINAL_STATUSES.includes(props.deliverableStatus as any)
})

/** 终态时悬浮提示文案 */
const terminalStateTooltip = '该出品物已签字/确认/归档，不可回填或刷新'

/** 刷新加载状态 */
const refreshingSingle = ref(false)
const refreshingAll = ref(false)

// 如果父组件明确标记无锚点
watch(
  () => props.hasNoAnchors,
  (val) => {
    if (val) {
      noAnchorAvailable.value = true
      clearSection()
    }
  },
  { immediate: true },
)

/**
 * 来源类型 → 中文标签（需求 3.6）
 */
function getTypeLabel(type: TargetType | string): string {
  const map: Record<string, string> = {
    note: '附注',
    report: '报表',
    trial_balance: '审定表',
    adjustment: '调整分录',
    workpaper: '底稿',
    ledger: '序时账',
    audit_sheet: '审计表',
    attachment: '附件',
    ai: 'AI',
  }
  return map[type] || type
}

/**
 * 来源类型 → el-tag type
 */
function getSourceTagType(type: TargetType | string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  switch (type) {
    case 'note': return 'primary'
    case 'report': return 'success'
    case 'trial_balance': return 'warning'
    case 'adjustment': return 'danger'
    default: return 'info'
  }
}

/**
 * 跨层跳转（需求 3.3）
 * 复用 LinkageContract.route 经 vue-router 导航
 */
async function onNavigate(contract: LinkageContract): Promise<void> {
  await navigateToSource(contract)
}

/**
 * 刷新当前章节溯源数据
 */
function refresh(): void {
  if (currentSectionCode.value) {
    traceSection(currentSectionCode.value)
  }
}

/**
 * "刷新本章节"按钮回调（需求 5.5：覆盖人工编辑前弹确认）
 * 调用 Task 9 端点 POST .../refresh-section
 */
async function onRefreshSection(): Promise<void> {
  if (!currentSectionCode.value || isTerminalState.value) return

  // 需求 5.5：人工编辑覆盖确认
  try {
    await ElMessageBox.confirm(
      '刷新本章节将用最新源数据覆盖当前内容，如您有手动编辑的内容可能被覆盖。是否继续？',
      '确认刷新本章节',
      {
        confirmButtonText: '确认刷新',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    // 用户取消
    return
  }

  refreshingSingle.value = true
  try {
    const url = `/api/projects/${props.projectId}/deliverables/${props.wordExportTaskId}/refresh-section`
    await api.post(url, {
      year: props.year || new Date().getFullYear(),
      section_code: currentSectionCode.value,
      confirm_overwrite: true,
    })
    ElMessage.success('章节已刷新')
    // 刷新溯源数据
    refresh()
  } catch (e: any) {
    if (e?.response?.status === 403) {
      ElMessage.error('权限不足：需要编辑权限')
    } else if (e?.response?.status === 409) {
      ElMessage.warning(e?.response?.data?.message || e?.response?.data?.detail || '该出品物已终态，不可刷新')
    } else {
      ElMessage.error(e?.response?.data?.message || e?.message || '刷新失败')
    }
  } finally {
    refreshingSingle.value = false
  }
}

/**
 * "刷新所有过期"按钮回调
 * 调用 Task 9 端点 POST .../refresh-stale
 */
async function onRefreshAllStale(): Promise<void> {
  if (isTerminalState.value) return

  refreshingAll.value = true
  try {
    const url = `/api/projects/${props.projectId}/deliverables/${props.wordExportTaskId}/refresh-stale`
    await api.post(url, {
      year: props.year || new Date().getFullYear(),
      confirm_overwrite: true,
    })
    ElMessage.success('所有过期章节已刷新')
    refresh()
  } catch (e: any) {
    if (e?.response?.status === 403) {
      ElMessage.error('权限不足：需要编辑权限')
    } else if (e?.response?.status === 409) {
      ElMessage.warning(e?.response?.data?.message || e?.response?.data?.detail || '该出品物已终态，不可刷新')
    } else {
      ElMessage.error(e?.response?.data?.message || e?.message || '批量刷新失败')
    }
  } finally {
    refreshingAll.value = false
  }
}

/**
 * SSE LINKAGE_STALE_CHANGED 实时监听（需求 4.5）
 * 当上游数据变更级联标记章节 stale 时，后端推 SSE 事件，前端实时更新徽标。
 *
 * 迁移到项目事件流单例总线（frontend-sse-connection-consolidation）：订阅共享的、经
 * Authorization header 鉴权的连接（每项目一条），断线重连/退避由总线统一负责。
 * 🔴 附带修复：原 `useSSEReconnect` 用 native EventSource 无 token → 端点鉴权后恒 401 降级，
 * 实时徽标其实从未生效；迁移后 LINKAGE_STALE_CHANGED 首次真正送达。
 */
const _lineageSub = subscribeProjectEvent(
  props.projectId,
  'LINKAGE_STALE_CHANGED',
  () => {
    // 当前章节可能变 stale → 刷新溯源徽标 + 刷新下拉 stale 标记
    if (currentSectionCode.value) {
      traceSection(currentSectionCode.value)
    }
    loadSections()
  },
)

onMounted(loadSections)
function closeSSE(): void {
  _lineageSub.close()
}
onUnmounted(closeSSE)

/**
 * 供父组件调用：从 OnlyOffice 获取的书签名触发溯源
 */
function onBookmarkDetected(anchorName: string): void {
  if (!anchorName) {
    // 无法解析锚点
    if (props.hasNoAnchors) {
      noAnchorAvailable.value = true
    }
    clearSection()
    return
  }
  noAnchorAvailable.value = false
  // 优先与已加载的权威章节列表精确匹配：避免 anchor→section_code 逆映射对多分隔符
  // 章节（如「五、12·1」→ sec_五_12_1 → 无法还原·）失真，并天然忽略非本文档的杂散 Tag。
  const match = sectionOptions.value.find(
    (o) => anchorNameFromSectionCode(o.code) === anchorName,
  )
  if (match) {
    currentSectionCode.value = match.code
    manualInput.value = match.code // 同步下拉，反映当前光标所在章节
    traceSection(match.code)
    return
  }
  // 回退：未加载章节列表或未匹配到 → 逆映射解析（单顿号章节可靠）
  traceFromAnchor(anchorName)
}

/**
 * 供父组件调用：当检测到文档无任何 sec_ 书签时标记降级
 */
function setNoAnchors(): void {
  noAnchorAvailable.value = true
  clearSection()
}

// 暴露给父组件
defineExpose({
  onBookmarkDetected,
  setNoAnchors,
  traceSection,
  refresh,
  onRefreshSection,
  onRefreshAllStale,
  isTerminalState,
  closeSSE,
})
</script>

<style scoped>
.lineage-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.lineage-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  background: var(--gt-color-primary-bg, #f4f0fa);
}

.lineage-panel__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.lineage-panel__refresh-btn {
  color: var(--gt-color-primary, #4b2d77);
}

.lineage-panel__manual {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.lineage-panel__manual-select {
  flex: 1;
  min-width: 0;
}

.lineage-panel__manual-btn {
  flex-shrink: 0;
}

.lineage-panel__opt-code {
  font-variant-numeric: tabular-nums;
}

.lineage-panel__opt-stale {
  margin-left: 8px;
}

.lineage-panel__no-anchor {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
  color: var(--el-text-color-secondary);
  gap: 8px;
}

.lineage-panel__no-anchor-icon {
  font-size: 24px;
  color: var(--el-color-warning);
}

.lineage-panel__hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
  color: var(--el-text-color-secondary);
  gap: 8px;
}

.lineage-panel__loading {
  padding: 16px;
}

.lineage-panel__error {
  padding: 16px;
}

.lineage-panel__content {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}

.lineage-panel__section-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 12px;
}

.lineage-panel__section-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.lineage-panel__section-code {
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.lineage-panel__stale-badge {
  margin-left: auto;
}

.lineage-panel__refresh-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 12px;
}

.lineage-panel__refresh-btn-wrapper {
  display: inline-flex;
}

.lineage-panel__action-btn {
  font-size: 12px;
}

.lineage-panel__action-btn:not(.is-disabled) {
  --el-button-text-color: var(--gt-color-primary, #4b2d77);
  --el-button-border-color: var(--gt-color-border-purple-light, #d8b8ee);
  --el-button-bg-color: var(--gt-color-primary-bg, #f4f0fa);
}

.lineage-panel__action-btn:not(.is-disabled):hover {
  --el-button-hover-text-color: var(--gt-color-primary, #4b2d77);
  --el-button-hover-border-color: var(--gt-color-primary, #4b2d77);
  --el-button-hover-bg-color: var(--gt-color-primary-bg, #f4f0fa);
}

.lineage-panel__sources {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lineage-panel__source-item {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.lineage-panel__source-item:hover {
  border-color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
  box-shadow: 0 1px 4px rgba(75, 45, 119, 0.08);
}

.lineage-panel__source-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.lineage-panel__source-type {
  font-size: 11px;
}

.lineage-panel__source-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.lineage-panel__source-id {
  font-size: 13px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.lineage-panel__source-jump {
  color: var(--gt-color-primary, #4b2d77);
  font-size: 14px;
  flex-shrink: 0;
}

.lineage-panel__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: var(--el-text-color-secondary);
}
</style>
