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

    <!-- 无锚点降级提示（需求 3.5） -->
    <div v-if="noAnchorAvailable" class="lineage-panel__no-anchor">
      <el-icon class="lineage-panel__no-anchor-icon"><InfoFilled /></el-icon>
      <span>该出品物版本不支持溯源，请重新生成</span>
    </div>

    <!-- 未选中章节（提示用户选中） -->
    <div v-else-if="!currentSectionCode && !noAnchorAvailable" class="lineage-panel__hint">
      <el-icon><Document /></el-icon>
      <span>请在文档中选中章节以查看溯源信息</span>
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
import { computed, ref, watch } from 'vue'
import { InfoFilled, Document, Right } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import type { LinkageContract, TargetType } from '@/types/linkageContract'
import { useDeliverableLineage, sectionCodeFromAnchor } from '@/composables/useDeliverableLineage'
import { useSSEReconnect } from '@/composables/useSSEReconnect'
import { api } from '@/services/apiProxy'

/** 终态状态列表（signed/confirmed/archived）— 需求 11.4 */
const TERMINAL_STATUSES = ['signed', 'confirmed', 'archived'] as const

const props = defineProps<{
  projectId: string
  wordExportTaskId: string
  /** OnlyOffice 编辑器实例引用，用于获取书签信息 */
  editorInstance?: any
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
 * 当上游数据变更级联标记章节 stale 时，后端推 SSE 事件，前端实时更新徽标
 *
 * 复用 useSSEReconnect（断线重连 + 退避），连到项目级事件流 /events/stream
 * （EventSource 无法携带自定义 header，与 ImportProgress.vue 同一 /stream 模式，
 *  项目 SSE 端点经现有设置工作，URL 不带 token）
 */
const { close: closeSSE } = useSSEReconnect({
  url: () => `/api/projects/${props.projectId}/events/stream`,
  onMessage: (data: any) => {
    // 只处理 LINKAGE_STALE_CHANGED 相关事件
    if (data?.event_type === 'LINKAGE_STALE_CHANGED' || data?.extra) {
      // 当前章节变 stale，刷新溯源
      if (currentSectionCode.value) {
        traceSection(currentSectionCode.value)
      }
    }
  },
  pollFallback: async () => 'running', // SSE 用于实时更新，无终态概念，始终 running
  maxAttempts: 10,
})

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
