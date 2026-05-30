<template>
  <!-- 横幅区（归档/AI/冲突/信任度/状态机/编辑锁/前置状态/stale） -->
  <EditorBanners
    :project-id="projectId"
    :wp-id="wpId"
    :wp-detail="wpDetail"
    :cycle-type="cycleType"
    :edit-lock="editLock"
    :prerequisite-banner="prerequisiteBanner"
    :stale-impact="staleImpact"
    :show-stale-impact-panel="showStaleImpactPanel"
    @conflict-resolved="onConflictResolved"
    @stale-item-click="onStaleItemClick"
    @jump-to-prereq="onJumpToPrereq"
    @update:show-stale-impact-panel="showStaleImpactPanel = $event"
  />

  <!-- V3 Req 11.6: 时光机面板 -->
  <TimeMachineDrawer ref="tmDrawerRef" module="workpaper" :instance-id="wpId" @restored="onTimeMachineRestored" />

  <!-- HTML 渲染器路由分发（A/B/C/D/E/H/skip 优先级最高） -->
  <GtWpRenderer
    v-if="useHtmlRenderer"
    :wp-id="wpId"
    @save-success="onChildSaved"
    @trigger-procedure-trimming-suggestion="onHtmlTrimmingSuggestion"
    @cross-ref-update="onHtmlCrossRefUpdate"
    @sync-to-disclosure-notes="onHtmlSyncToDisclosureNotes"
    @jump-to-reference="onHtmlJumpToReference"
  />

  <!-- 默认 Univer 编辑器（component_type='univer' 或未配置时） -->
  <div v-else class="gt-wp-editor gt-fade-in">
    <!-- 顶部工具栏 -->
    <div class="gt-wp-editor-toolbar">
      <div class="gt-wp-editor-toolbar-left">
        <el-button text @click="goBack">← 返回</el-button>
        <span class="gt-wp-editor-code" v-if="wpDetail">{{ wpDetail.wp_code }}</span>
        <span class="gt-wp-editor-name" v-if="wpDetail">{{ wpDetail.wp_name }}</span>
        <el-tag v-if="wpDetail" :type="(statusTagType(wpDetail.status)) || undefined" size="small">
          {{ statusLabel(wpDetail.status) }}
        </el-tag>
        <span v-if="dirty" class="gt-dirty-indicator">● 有未保存的变更</span>
      </div>
      <div class="gt-wp-editor-toolbar-right">
        <!-- 复核状态 badge -->
        <ReviewLayerBadges
          v-if="wpDetail?.wp_code?.startsWith('E1')"
          :project-id="projectId"
          :wp-id="wpId"
          :wp-code="wpDetail?.wp_code"
        />
        <!-- 审计导航图入口 -->
        <el-button
          v-if="hasAuditNav"
          size="small"
          @click="showAuditNavDrawer = true"
          style="margin-right: 8px"
        >🧭 审计导航图</el-button>
        <!-- 关键操作组：保存 / 一键填充 / 提交复核 — V3 Req 12.1.1 配置驱动 -->
        <el-button-group class="gt-wp-toolbar-primary">
          <el-tooltip
            v-for="btn in toolbarButtons.filter((b) => b.group === 'primary')"
            :key="btn.key"
            placement="bottom"
            :content="btn.tooltip || ''"
            :disabled="!btn.tooltip"
          >
            <el-button
              size="small"
              :type="btn.dynamicType || btn.type"
              :plain="btn.plain"
              :loading="btn.loading"
              :disabled="btn.disabled"
              :title="btn.title"
              @click="handleToolbarAction(btn.action)"
            >{{ btn.dynamicLabel || btn.label }}</el-button>
          </el-tooltip>
        </el-button-group>

        <!-- 次要操作：更多 dropdown -->
        <el-dropdown trigger="click" placement="bottom-end">
          <el-button size="small" plain>更多 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <template v-for="item in toolbarDropdownItems" :key="item.key">
                <el-dropdown-item
                  v-if="item.permission"
                  :divided="item.divided"
                  v-permission="item.permission"
                  @click="handleToolbarAction(item.action)"
                >{{ item.label }}</el-dropdown-item>
                <el-dropdown-item
                  v-else
                  :divided="item.divided"
                  @click="handleToolbarAction(item.action)"
                >{{ item.label }}</el-dropdown-item>
              </template>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <!-- 面板按钮 -->
        <el-badge :value="fineCheckFailCount" :max="99" :hidden="fineCheckFailCount === 0" type="danger">
          <el-button size="small" @click="showSidePanel = !showSidePanel">📋 面板</el-button>
        </el-badge>
        <!-- 独立按钮组（刷新取数等） -->
        <el-tooltip
          v-for="btn in toolbarButtons.filter((b) => b.group === 'standalone')"
          :key="btn.key"
          placement="bottom"
          :content="btn.tooltip || ''"
          :disabled="!btn.tooltip"
        >
          <el-button
            size="small"
            :type="btn.dynamicType || btn.type"
            :plain="btn.plain"
            :loading="btn.loading"
            :disabled="btn.disabled"
            :title="btn.title"
            @click="handleToolbarAction(btn.action)"
          >{{ btn.dynamicLabel || btn.label }}</el-button>
        </el-tooltip>
      </div>
    </div>

    <!-- Step Navigation Bar -->
    <div v-if="stepMapping.data.value?.steps?.length" class="gt-step-nav">
      <div class="gt-step-nav__progress">
        <span class="gt-step-nav__label">
          步骤 {{ stepMapping.currentStepIndex.value + 1 }}/{{ stepMapping.totalSteps.value }}
        </span>
        <span class="gt-step-nav__name">{{ stepMapping.currentStep.value?.step_name }}</span>
        <span v-if="stepMapping.currentTargetSheets.value?.length" class="gt-step-nav__sheet">
          → {{ stepMapping.currentTargetSheets.value[0] }}
        </span>
      </div>
      <div class="gt-step-nav__actions">
        <el-button size="small" :disabled="stepMapping.currentStepIndex.value === 0" @click="stepMapping.prevStep()">上一步</el-button>
        <el-button size="small" type="primary" :disabled="stepMapping.currentStepIndex.value >= stepMapping.totalSteps.value - 1" @click="stepMapping.nextStep()">下一步</el-button>
      </div>
    </div>

    <!-- Univer 编辑器核心 -->
    <UniverEditorCore
      ref="univerEditorCoreRef"
      :project-id="projectId"
      :wp-id="wpId"
      :wp-detail="wpDetail!"
      :can-edit="canEdit"
      :sheet-nav-facade="sheetNavFacade"
      :cycle-type="cycleType"
      :cycle-dialogs="cycleDialogs"
      :i-cycle="iCycle"
      :g-cycle="gCycle"
      :k-cycle="kCycle"
      :l-cycle="lCycle"
      :m-cycle="mCycle"
      :n-cycle="nCycle"
      :f-cycle="fCycle"
      @saved="onChildSaved"
      @dirty-change="onDirtyChange"
      @sheet-switch="onSwitchSheet"
      @locate-cell="onLocateCell"
    />

    <!-- Sprint 5.5: 查看公式详情弹窗 -->
    <CellFormulaDetail
      :visible="showCellFormulaDetail"
      :wp-code="wpDetail?.wp_code || ''"
      :sheet-name="cellDetailSheet"
      :label="cellDetailLabel"
      @update:visible="showCellFormulaDetail = $event"
      @navigate="onCellDetailNavigate"
    />

    <!-- R7-S3-05 Task 25：底稿右栏面板（抽屉模式） -->
    <el-drawer
      v-model="showSidePanel"
      direction="rtl"
      size="400px"
      :with-header="false"
      :modal="false"
      append-to-body
    >
      <WorkpaperSidePanel
        :project-id="projectId"
        :wp-id="wpId"
        :wp-code="wpDetail?.wp_code"
        @finecheck-update="fineCheckFailCount = $event"
      />
    </el-drawer>
  </div>

  <!-- 弹窗/抽屉（条件渲染，不占主布局） -->
  <CycleDialogHost
    v-if="wpDetail"
    :project-id="projectId"
    :wp-id="wpId"
    :wp-detail="wpDetail"
    :sheet-nav-active-id="sheetNavActiveId"
    :cycle-type="cycleType"
    :cycle-dialogs="cycleDialogs"
    @saved="onChildSaved"
    @applied="onDialogApplied"
  />

  <VersionHistoryDrawer
    :wp-id="wpId"
    :visible="showVersionDrawer"
    @update:visible="showVersionDrawer = $event"
    @jump="onVersionSearchJump"
  />

  <AuditNavDialog
    :project-id="projectId"
    :wp-id="wpId"
    :wp-code="wpDetail?.wp_code || ''"
    :visible="showAuditNavDrawer"
    @update:visible="showAuditNavDrawer = $event"
  />

  <ReviewMarkDialog
    :project-id="projectId"
    :wp-id="wpId"
    :visible="showReviewDialog"
    :cell="reviewDialogCell"
    @update:visible="showReviewDialog = $event"
    @marked="onReviewMarked"
  />

  <!-- 非 Univer 编辑器的侧面板（共享） -->
  <el-drawer
    v-if="!useHtmlRenderer && componentType && componentType !== 'univer'"
    v-model="showSidePanel"
    direction="rtl"
    size="400px"
    :with-header="false"
    :modal="false"
    append-to-body
  >
    <WorkpaperSidePanel
      :project-id="projectId"
      :wp-id="wpId"
      :wp-code="wpDetail?.wp_code"
      @finecheck-update="fineCheckFailCount = $event"
    />
  </el-drawer>
</template>

<script setup lang="ts">
/**
 * WorkpaperEditor — 底稿编辑器 Shell 容器
 *
 * 职责：路由解析 + 模式分发（HTML/Univer/子编辑器）+ 子 SFC 编排 + provide context
 * 不持有 Univer 实例化 / 保存逻辑 / 弹窗渲染（已下沉到子 SFC + composable）
 *
 * @see .kiro/specs/workpaper-editor-shrink-phase2/design.md §4.2
 */
import { ref, computed, provide, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { confirmLeave } from '@/utils/confirm'
import { eventBus, type WorkpaperSavedPayload } from '@/utils/eventBus'
import { useAuditContext } from '@/composables/useAuditContext'
import { useCycleType } from '@/composables/useCycleType'
import { useEditorMode } from '@/composables/useEditorMode'
import { useEditorToolbar } from '@/composables/useEditorToolbar'
import { useEditorCycles } from '@/composables/useEditorCycles'
import { useSheetNavFacade } from '@/composables/useSheetNavFacade'
import { useEditingLock } from '@/composables/useEditingLock'
import { useStepMapping } from '@/composables/useStepMapping'
import { useStaleImpact, type StaleAffectedItem } from '@/composables/useStaleImpact'
import { usePrerequisiteStatus } from '@/composables/usePrerequisiteStatus'
import { useWorkpaperRefresh } from '@/composables/useWorkpaperRefresh'
import { useWorkpaperReviewMarkers, type ReviewMarkerTicket } from '@/composables/useWorkpaperReviewMarkers'
import { EDITOR_CONTEXT_KEY, type EditorContextData } from '@/composables/useEditorContext'
import { getWorkpaper, type WorkpaperDetail } from '@/services/workpaperApi'
import { api as httpApi } from '@/services/apiProxy'

// ─── 子 SFC imports ─────────────────────────────────────────────────────────
import GtWpRenderer from '@/components/workpaper/GtWpRenderer.vue'
import WorkpaperSidePanel from '@/components/workpaper/WorkpaperSidePanel.vue'
import ReviewLayerBadges from '@/components/workpaper/ReviewLayerBadges.vue'
import CellFormulaDetail from '@/components/CellFormulaDetail.vue'
import TimeMachineDrawer from '@/components/time_machine/TimeMachineDrawer.vue'
import UniverEditorCore from './workpaper-editor/UniverEditorCore.vue'
import EditorBanners from './workpaper-editor/EditorBanners.vue'
import CycleDialogHost from './workpaper-editor/CycleDialogHost.vue'
import VersionHistoryDrawer from './workpaper-editor/VersionHistoryDrawer.vue'
import AuditNavDialog from './workpaper-editor/AuditNavDialog.vue'
import ReviewMarkDialog from './workpaper-editor/ReviewMarkDialog.vue'

// ─── 路由解析 ────────────────────────────────────────────────────────────────
const route = useRoute()
const router = useRouter()
const { canEdit } = useAuditContext()
const projectId = computed(() => route.params.projectId as string)
const wpId = computed(() => route.params.wpId as string)

// ─── 核心数据 ref ────────────────────────────────────────────────────────────
const wpDetail = ref<WorkpaperDetail | null>(null)
const loading = ref(true)
const dirty = ref(false)
const showSidePanel = ref(false)
const fineCheckFailCount = ref(0)
const showVersionDrawer = ref(false)
const showAuditNavDrawer = ref(false)
const showReviewDialog = ref(false)
const reviewDialogCell = ref<{ sheet: string; cellRef: string }>({ sheet: '', cellRef: '' })
const showCellFormulaDetail = ref(false)
const cellDetailSheet = ref('')
const cellDetailLabel = ref('')
const showStaleImpactPanel = ref(false)
const univerEditorCoreRef = ref<InstanceType<typeof UniverEditorCore> | null>(null)

// ─── 模式分发（useEditorMode） ──────────────────────────────────────────────
const {
  componentType,
  useHtmlRenderer,
  wpClassification,
  fetchComponentType,
} = useEditorMode({ wpId, projectId, wpDetail })

// ─── 循环类型 ────────────────────────────────────────────────────────────────
const cycleType = useCycleType(wpDetail)
const { isDCycle, isFCycle, isGCycle, isHCycle, isICycle, isKCycle, isLCycle, isMCycle, isNCycle } = cycleType

// ─── Sheet 导航 facade ──────────────────────────────────────────────────────
const univerAPIRef = ref<any>(null)
const projectMeta = ref<{ scenario: string; has_foreign_currency: boolean; measurement_model?: string } | null>(null)
const scenarioFilter = computed(() => {
  if (!projectMeta.value) return null
  return {
    scenario: projectMeta.value.scenario || 'normal',
    hasForeignCurrency: !!projectMeta.value.has_foreign_currency,
  }
})
const measurementModelRef = computed(() => projectMeta.value?.measurement_model || 'cost')
const sheetNavFacade = useSheetNavFacade(univerAPIRef, wpDetail, cycleType, scenarioFilter, measurementModelRef)
const sheetNavActiveId = sheetNavFacade.activeSheetId

// ─── useEditorCycles 实例化 ─────────────────────────────────────────────────
const { cycleDialogs, fCycle, iCycle, gCycle, kCycle, lCycle, mCycle, nCycle } = useEditorCycles({
  wpDetail,
  projectId,
  wpId,
  sheetNavActiveId,
  sheetNavFacade,
  cycleType,
})

// ─── 编辑锁 ─────────────────────────────────────────────────────────────────
const editLock = useEditingLock({
  resourceId: computed(() => wpId.value || ''),
})

// ─── 前置状态横幅 ────────────────────────────────────────────────────────────
const prerequisiteCycleCode = computed(() => {
  if (isHCycle.value) return wpDetail.value?.wp_code || 'H1'
  if (isICycle.value) return wpDetail.value?.wp_code || 'I1'
  if (isGCycle.value) return wpDetail.value?.wp_code || 'G1'
  if (isLCycle.value) return wpDetail.value?.wp_code || 'L1'
  if (isMCycle.value) return wpDetail.value?.wp_code || 'M2'
  if (isNCycle.value) return wpDetail.value?.wp_code || 'N2'
  if (isFCycle.value) return wpDetail.value?.wp_code || 'F2'
  if (isDCycle.value) return wpDetail.value?.wp_code || 'D2'
  return 'E1'
})
const prerequisiteStatus = usePrerequisiteStatus(projectId.value, prerequisiteCycleCode.value)
const prerequisiteBanner = computed(() => prerequisiteStatus.banner.value)

// ─── Stale 影响 ─────────────────────────────────────────────────────────────
const staleImpact = useStaleImpact(computed(() => wpDetail.value?.wp_code?.split('-')[0] || ''))

// ─── Step Mapping ───────────────────────────────────────────────────────────
const stepMapping = useStepMapping(wpId.value || '')

// ─── 数据刷新 ───────────────────────────────────────────────────────────────
const manualRefreshing = ref(false)
const wpRefresh = useWorkpaperRefresh({
  projectId: () => projectId.value,
  wpId: () => wpId.value,
  onRefresh: async () => {
    if (manualRefreshing.value) return
    manualRefreshing.value = true
    try {
      await httpApi.post(
        `/api/projects/${projectId.value}/workpapers/${wpId.value}/template-file/init`,
        {},
      ).catch(() => null)
    } finally {
      manualRefreshing.value = false
    }
  },
})
// 防止 unused 警告
void wpRefresh

// ─── 复核红点 ───────────────────────────────────────────────────────────────
const reviewMarkers = useWorkpaperReviewMarkers({
  projectId: () => projectId.value,
  wpId: () => wpId.value,
  onJumpToIssue: (ticket: ReviewMarkerTicket) => {
    router.push({
      name: 'IssueTicketList',
      params: { projectId: projectId.value },
      query: { highlight_id: ticket.id },
    })
  },
})

// ─── 审计导航图 ─────────────────────────────────────────────────────────────
const hasAuditNav = computed(() => {
  const code = wpDetail.value?.wp_code || ''
  return !!code && (
    code.startsWith('E1') ||
    isDCycle.value || isFCycle.value || isHCycle.value || isICycle.value ||
    isGCycle.value || isKCycle.value || isLCycle.value || isMCycle.value || isNCycle.value
  )
})

// ─── 时光机 ─────────────────────────────────────────────────────────────────
const tmDrawerRef = ref<InstanceType<typeof TimeMachineDrawer> | null>(null)
function onTimeMachineRestored(_snap: any) {
  window.location.reload()
}

// ─── useEditorToolbar 实例化 ────────────────────────────────────────────────
// saving/submitting/prefillLoading 由 UniverEditorCore expose 同步
// 使用 computed 包装 UniverEditorCore 暴露的 ref（toolbar 需要 Ref 接口）
const saving = ref(false)
const submitting = ref(false)
const prefillLoading = ref(false)
const hasPrefillMapping = ref(true)
const wpStatusComputed = computed(() => wpDetail.value?.status)

const { availableButtons: toolbarButtons, dropdownItems: toolbarDropdownItems, handleAction: handleToolbarAction } = useEditorToolbar(
  {
    canEdit,
    saving,
    dirty,
    submitting,
    prefillLoading,
    hasPrefillMapping,
    fineCheckFailCount,
    wpStatus: wpStatusComputed,
    manualRefreshing,
  },
  {
    onSave: async () => {
      saving.value = true
      try { await univerEditorCoreRef.value?.onSave() } finally { saving.value = false }
    },
    onRefreshPrefill: async () => {
      prefillLoading.value = true
      try { await univerEditorCoreRef.value?.onRefreshPrefill() } finally { prefillLoading.value = false }
    },
    onSubmitForReview: async () => {
      submitting.value = true
      try { await univerEditorCoreRef.value?.onSubmitForReview() } finally { submitting.value = false }
    },
    onSyncStructure: () => { univerEditorCoreRef.value?.onSyncStructure() },
    onShowVersions: () => { onShowVersions() },
    onDownload: () => { univerEditorCoreRef.value?.onDownload() },
    onExportPdf: () => { univerEditorCoreRef.value?.onExportPdf() },
    onUpload: () => { onUpload() },
    onManualRefresh: () => { onManualRefresh() },
  },
)

// ─── provide(EDITOR_CONTEXT_KEY) ────────────────────────────────────────────
provide(EDITOR_CONTEXT_KEY, {
  projectId,
  wpId,
  wpDetail,
  canEdit,
  componentType,
  cycleType,
  cycleDialogs,
  sheetNavActiveId,
} as EditorContextData)

// ─── Event handlers ─────────────────────────────────────────────────────────

function onChildSaved() {
  eventBus.emit('workpaper:saved', {
    projectId: projectId.value,
    wpId: wpId.value,
  } as WorkpaperSavedPayload)
  // 刷新 wpDetail
  getWorkpaper(projectId.value, wpId.value).then((d) => {
    if (d) wpDetail.value = d
  }).catch(() => { /* ignore */ })
}

function onDirtyChange(val: boolean) {
  dirty.value = val
}

function onSwitchSheet(_sheetId: string) {
  // Sheet 切换由 UniverEditorCore 内部处理
}

function onLocateCell(_payload: { sheetName?: string; cellRef: string }) {
  // 定位由 UniverEditorCore 内部处理
}

function onDialogApplied(_sheet: string) {
  // dialog applied 后刷新
  onChildSaved()
}

function onShowVersions() {
  showVersionDrawer.value = true
}

function onVersionSearchJump(payload: { versionId: string; sheet: string; cellRef: string }) {
  if (!payload.cellRef || !wpId.value) return
  eventBus.emit('workpaper:locate-cell', {
    wpId: wpId.value,
    sheetName: payload.sheet || undefined,
    cellRef: payload.cellRef,
  })
  showVersionDrawer.value = false
}

function onReviewMarked() {
  eventBus.emit('review-mark:changed', { projectId: projectId.value, wpId: wpId.value })
}

function onConflictResolved(_id: string, _resolution: string) {
  // 调解后 banner 自动从列表移除
}

function onStaleItemClick(item: StaleAffectedItem) {
  if (item.target_module === 'disclosure_notes' && item.note_section_code) {
    router.push(`/projects/${projectId.value}/disclosure-notes?section=${item.note_section_code}`)
  } else if (item.target_module === 'audit_report') {
    router.push(`/projects/${projectId.value}/audit-report`)
  } else if (item.target_module === 'financial_report' && item.report_row_code) {
    router.push(`/projects/${projectId.value}/reports?row=${item.report_row_code}`)
  } else if (item.target_module === 'trial_balance') {
    router.push(`/projects/${projectId.value}/trial-balance`)
  } else if (item.target_module === 'adjustments') {
    router.push(`/projects/${projectId.value}/adjustments`)
  } else if (item.wp_code) {
    router.push({
      name: 'WorkpaperList',
      params: { projectId: projectId.value },
      query: { highlight: item.wp_code },
    })
  }
}

function onJumpToPrereq() {
  const target = prerequisiteStatus.items.value.find((i) => i.state !== 'completed')
  if (!target) return
  router.push({
    name: 'WorkpaperList',
    params: { projectId: projectId.value },
    query: { highlight: target.wp_code },
  })
}

// ─── HTML 渲染器事件桥接 ────────────────────────────────────────────────────

function onHtmlTrimmingSuggestion(payload: Record<string, any>) {
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.debug('[WorkpaperEditor] procedure trimming suggestion from HTML renderer:', payload)
  }
}

function onHtmlCrossRefUpdate(payload: { source_wp_code: string; target_wp_code: string; cell: string }) {
  eventBus.emit('cross-ref:updated', {
    projectId: projectId.value,
    targetWpCode: payload.target_wp_code,
    changedSheets: [],
  } as any)
}

function onHtmlSyncToDisclosureNotes(_payload: Record<string, any>) {
  // C 附注组件已直接调用 API，此处仅占位
}

function onHtmlJumpToReference(refCode: string) {
  if (!refCode) return
  router.push({
    name: 'WorkpaperList',
    params: { projectId: projectId.value },
    query: { highlight: refCode },
  })
}

// ─── Toolbar action helpers ─────────────────────────────────────────────────

async function onManualRefresh() {
  manualRefreshing.value = true
  try {
    univerEditorCoreRef.value?.onRefreshPrefill()
  } finally {
    manualRefreshing.value = false
  }
}

function onUpload() {
  router.push({
    name: 'WorkpaperList',
    params: { projectId: projectId.value },
    query: { upload: wpId.value },
  })
}

// ─── Cell formula detail ────────────────────────────────────────────────────

function onCellDetailNavigate(uri: string) {
  showCellFormulaDetail.value = false
  const parts = uri.split(':')
  const mod = parts[0]?.toUpperCase()
  if (mod === 'REPORT') {
    router.push({ name: 'ReportView', params: { id: projectId.value } })
  } else if (mod === 'NOTE') {
    router.push({ name: 'DisclosureEditor', params: { id: projectId.value } })
  } else if (mod === 'WP' && parts[1]) {
    router.push({ name: 'WorkpaperEditor', params: { id: projectId.value }, query: { wp: parts[1] } })
  }
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function statusTagType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    not_started: 'info', in_progress: 'warning', draft: 'warning',
    draft_complete: '', edit_complete: '', review_passed: 'success', archived: 'info',
  }
  return m[s] || 'info'
}

function statusLabel(s: string) {
  const m: Record<string, string> = {
    not_started: '未开始', in_progress: '编制中', draft: '草稿',
    draft_complete: '初稿完成', edit_complete: '编辑完成',
    review_passed: '复核通过', archived: '已归档',
  }
  return m[s] || s
}

function goBack() {
  if (dirty.value) {
    if (!confirm('有未保存的修改，确定离开？')) return
  }
  router.push({ name: 'WorkpaperList', params: { projectId: projectId.value } })
}

// ─── onBeforeRouteLeave dirty 检查 ──────────────────────────────────────────

onBeforeRouteLeave(async (_to, _from, next) => {
  if (!dirty.value) { next(); return }
  try {
    await confirmLeave('底稿')
    next()
  } catch {
    next(false)
  }
})

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  ;(async () => {
    await fetchComponentType()
    try {
      await wpClassification.load()
    } catch { /* 静默：归类失败回退到 Univer/子编辑器路径 */ }

    if (useHtmlRenderer.value) {
      loading.value = false
      return
    }
    if (componentType.value === 'univer' || !componentType.value) {
      // UniverEditorCore 内部处理 initUniver
      loading.value = false
    } else {
      loading.value = false
    }
  })()

  // 加载程序步骤映射
  stepMapping.loadMapping()

  // 加载项目元数据
  loadProjectMeta()

  // 订阅 workpaper:locate-cell 事件
  eventBus.on('workpaper:locate-cell', onLocateCellEvent)

  // wp-locate-foundation Task 4.2: 读 route.query.sheet / cell → 触发定位
  // 使用 nextTick + 短延迟确保 GtWpRenderer 已挂载
  const querySheet = route.query.sheet as string | undefined
  const queryCell = route.query.cell as string | undefined
  if (querySheet || queryCell) {
    nextTick(() => {
      setTimeout(() => {
        eventBus.emit('workpaper:locate-cell', {
          wpId: wpId.value,
          sheetName: querySheet || undefined,
          cellRef: queryCell || '',
        })
      }, 300)
    })
  }

  // 浏览器关闭/刷新前警告
  window.addEventListener('beforeunload', onBeforeUnload)
})

onUnmounted(() => {
  eventBus.off('workpaper:locate-cell', onLocateCellEvent)
  window.removeEventListener('beforeunload', onBeforeUnload)
})

async function loadProjectMeta() {
  try {
    const proj: any = await httpApi.get(`/api/projects/${projectId.value}`, {
      validateStatus: (s: number) => s < 600,
    })
    projectMeta.value = {
      scenario: proj?.scenario || 'normal',
      has_foreign_currency: !!proj?.has_foreign_currency,
      measurement_model: proj?.measurement_model || 'cost',
    }
  } catch {
    projectMeta.value = { scenario: 'normal', has_foreign_currency: false, measurement_model: 'cost' }
  }
}

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}

function onLocateCellEvent(payload: { wpId: string; sheetName?: string; cellRef: string }) {
  if (payload.wpId !== wpId.value) return
  // 委托给 UniverEditorCore 处理
}
</script>

<style scoped>
.gt-wp-editor {
  display: flex; flex-direction: column; height: 100vh;
  background: var(--gt-color-bg);
}
.gt-step-nav {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 16px; background: var(--gt-color-bg-light, #f8f7fc);
  border-bottom: 1px solid var(--gt-color-border, #e8e5f0); font-size: 13px;
}
.gt-step-nav__progress { display: flex; align-items: center; gap: 4px; }
.gt-step-nav__label { color: var(--gt-color-text-secondary); margin-right: 8px; }
.gt-step-nav__name { font-weight: 600; color: var(--gt-color-primary); }
.gt-step-nav__sheet { color: var(--gt-color-text-tertiary); margin-left: 8px; font-size: 12px; }
.gt-step-nav__actions { display: flex; gap: 8px; }
.gt-wp-editor-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--gt-space-2) var(--gt-space-4);
  background: var(--gt-color-bg-white); box-shadow: var(--gt-shadow-sm); z-index: 10;
  flex-wrap: wrap; row-gap: 6px;
}
.gt-wp-editor-toolbar-left { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
.gt-wp-editor-toolbar-right { display: flex; align-items: center; gap: var(--gt-space-2); flex-shrink: 0; }
.gt-wp-toolbar-primary { margin-right: 4px; }
.gt-wp-editor-code { font-weight: 700; color: var(--gt-color-primary); font-size: var(--gt-font-size-md); white-space: nowrap; }
.gt-wp-editor-name { color: var(--gt-color-text); font-size: var(--gt-font-size-md); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 320px; }
.gt-dirty-indicator { color: var(--gt-color-wheat); font-size: var(--gt-font-size-xs); font-weight: 500; }
</style>

<!-- 全局样式（dialog append-to-body 脱离 scoped 作用域） -->
<style>
.gt-review-marker-dot {
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--gt-color-coral);
  box-shadow: 0 0 0 2px rgba(230, 68, 62, 0.18), 0 1px 3px rgba(0, 0, 0, 0.15);
  cursor: pointer; transition: transform 0.15s ease;
}
.gt-review-marker-dot:hover { transform: scale(1.2); }
.gt-review-marker-popover { padding: 12px !important; }
.gt-audit-nav-dialog .el-dialog {
  resize: both; overflow: hidden; min-width: 700px; min-height: 500px;
  display: flex; flex-direction: column; border-radius: 12px;
}
.gt-audit-nav-dialog .el-dialog__header {
  margin: 0; padding: 14px 20px;
  background: linear-gradient(135deg, #6750A4 0%, #8b5cf6 100%);
  border-radius: 12px 12px 0 0;
}
.gt-audit-nav-dialog .el-dialog__body {
  flex: 1; overflow: auto; padding: 0 !important; background: #fafafa;
}
.gt-audit-nav-dialog.is-fullscreen .el-dialog { resize: none; border-radius: 0; }
.gt-audit-nav-dialog.is-fullscreen .el-dialog__header { border-radius: 0; }
.gt-audit-nav-dialog .gt-audit-nav-header { display: none !important; }
.gt-audit-nav-dialog .gt-audit-nav { border: none !important; box-shadow: none !important; background: transparent !important; }
.gt-audit-nav-dialog .gt-audit-nav-body { padding: 16px 20px; }
.gt-audit-nav-dialog__header { display: flex; align-items: center; gap: 12px; }
.gt-audit-nav-dialog__title { display: flex; align-items: center; gap: 10px; flex: 1; color: #fff; font-size: 15px; font-weight: 600; }
.gt-audit-nav-dialog__icon { font-size: 18px; }
.gt-audit-nav-dialog__code { padding: 2px 8px; background: rgba(255,255,255,0.25); border-radius: 4px; font-size: 12px; font-weight: 700; }
.gt-audit-nav-dialog__name { font-size: 13px; font-weight: 400; color: rgba(255,255,255,0.9); }
.gt-audit-nav-dialog__actions { display: flex; gap: 4px; }
.gt-audit-nav-dialog__actions .el-button { color: #fff !important; }
.gt-audit-nav-dialog__actions .el-button:hover { background: rgba(255,255,255,0.15) !important; }
</style>
