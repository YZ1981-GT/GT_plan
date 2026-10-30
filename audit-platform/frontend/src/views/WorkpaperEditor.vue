<template>
  <!-- [platform-ui-editing-consistency MVP-4]
       TODO: Replace manual dirty/saving state with useEditStateMachine() -->
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

  <!-- useStaleRefresh：上游变更事件横幅 -->
  <div v-if="wpStaleRefresh.isStale.value" class="gt-stale-banner" style="margin: 4px 12px 8px">
    <span class="gt-stale-text">上游数据已变更，底稿取数可能过时</span>
    <el-button size="small" type="primary" @click="wpStaleRefresh.refresh()">刷新数据</el-button>
  </div>

  <!-- V3 Req 11.6: 时光机面板 -->
  <TimeMachineDrawer ref="tmDrawerRef" module="workpaper" :instance-id="wpId" @restored="onTimeMachineRestored" />

  <!-- 主内容区 + WorkpaperCapabilityShell（rail/location/capability 唯一 owner） -->
  <WorkpaperCapabilityShell
    class="gt-wp-editor-with-guidance"
    :owner-epoch="shellOwnerEpoch"
    :capability-epoch="shellCapabilityEpoch"
    :snapshot="shellCapabilitySnapshot"
    :location="shellLocation"
    :guidance-controller="shellGuidanceController"
    :open-review="onShellOpenReview"
    :close-review="onShellCloseReview"
    :shell-error="shellError"
    :open-dsh="openShellDsh"
    :close-dsh="closeShellDsh"
  >
    <!-- 主内容区（flex: 1） -->
    <div class="gt-wp-editor-main">
      <!-- 底稿标题栏（HTML 渲染器路径）。导出/导入移至各 sheet 内工具栏；
           底稿切换由 GtWpRenderer 内「🗂️ 切换底稿」树形弹窗承载，此处不再冗余。 -->
      <div v-if="useHtmlRenderer && wpDetail && projectYear != null" class="gt-wp-io-toolbar">
        <el-button text @click="goBack">← 返回</el-button>
        <span class="gt-wp-editor-code">{{ wpDetail.wp_code }}</span>
        <span class="gt-wp-editor-name">{{ displayWpName }}</span>
        <div class="gt-wp-io-toolbar__actions">
          <!-- 函证枢纽（D0/E0/F0/G0/H0/K0/L0）：底稿内逐 sheet 编制，台账由此入口跳转。 -->
          <el-button
            v-if="isConfirmationHubWorkbook"
            size="small"
            type="primary"
            plain
            @click="goConfirmationHub"
          >
            ✉️ 函证管理中心
          </el-button>
          <el-button size="small" @click="onShowVersions">
            <el-icon><Clock /></el-icon> 版本历史
          </el-button>
          <!-- HTML 路径此前无「面板」入口；SidePanel/AttachmentTabPanel 仅挂在 Univer 分支会导致 Drawer_Host 不可达 -->
          <el-button size="small" plain @click="onOpenLedgerWindow" title="在独立窗口打开查账">📊 查账</el-button>
          <el-badge :value="fineCheckFailCount" :max="99" :hidden="fineCheckFailCount === 0" type="danger">
            <el-button size="small" @click="showSidePanel = !showSidePanel">📋 面板</el-button>
          </el-badge>
        </div>
      </div>

      <!-- HTML 渲染器路由分发（A/B/C/D/E/H/skip 优先级最高） -->
      <GtWpRenderer
        ref="wpRendererRef"
        v-if="useHtmlRenderer && projectYear != null"
        :wp-id="wpId"
        :audit-year="projectYear"
        :readonly="editLock.forcedReadonly.value || isArchived"
        :initial-sheet="initialSheetFromQuery"
        :initial-cell="typeof route.query.cell === 'string' ? route.query.cell : undefined"
        @save-success="onChildSaved"
        @saved-notify="onChildSaved"
        @trigger-procedure-trimming-suggestion="onHtmlTrimmingSuggestion"
        @cross-ref-update="onHtmlCrossRefUpdate"
        @sync-to-disclosure-notes="onHtmlSyncToDisclosureNotes"
        @jump-to-reference="onHtmlJumpToReference"
        @open-attachment="onOpenAttachment"
        @sheet-change="onHtmlSheetChange"
      />

      <!-- 默认 Univer 编辑器（component_type='univer' 或未配置时） -->
      <div v-else-if="projectYear != null" class="gt-wp-editor gt-fade-in">
    <!-- 顶部工具栏 -->
    <div class="gt-wp-editor-toolbar">
      <div class="gt-wp-editor-toolbar-left">
        <el-button text @click="goBack">← 返回</el-button>
        <span class="gt-wp-editor-code" v-if="wpDetail">{{ wpDetail.wp_code }}</span>
        <span class="gt-wp-editor-name" v-if="wpDetail">{{ displayWpName }}</span>
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
        <el-button size="small" plain @click="onOpenLedgerWindow" title="在独立窗口打开查账">📊 查账</el-button>
        <WpExportButton
          v-if="wpDetail"
          :project-id="projectId"
          :wp-id="wpId"
          size="small"
          button-type=""
          label="导出"
        />
        <el-button size="small" @click="showWpImportEnhanced = true">导入</el-button>
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
        <!-- 复核对话入口 -->
        <el-popover
          placement="bottom"
          :width="260"
          trigger="click"
          popper-class="review-thread-popover"
        >
          <template #reference>
            <el-badge :value="reviewThreadCount" :max="9" :hidden="reviewThreadCount === 0" type="warning">
              <el-button size="small">📝 复核对话</el-button>
            </el-badge>
          </template>
          <div class="review-thread-list">
            <div v-if="reviewThreadList.length === 0" class="review-thread-empty">暂无活跃复核对话</div>
            <div
              v-for="item in reviewThreadList"
              :key="item.section_id"
              class="review-thread-item"
              @click="onOpenReviewThread(item)"
            >
              <span class="review-thread-dot" :class="item.has_unread ? 'dot-red' : 'dot-blue'" />
              <span class="review-thread-label">{{ item.section_id }}</span>
              <span v-if="item.has_unread" class="review-thread-unread">未读</span>
            </div>
          </div>
        </el-popover>
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
            :data-testid="btn.key === 'formulaManager' ? 'formula-manager-open' : undefined"
            :type="btn.dynamicType || btn.type"
            :plain="btn.plain"
            :loading="btn.loading"
            :disabled="btn.disabled || (btn.key === 'formulaManager' && shellCapabilitySnapshot.formulaView.allowed !== true)"
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

    <!-- Univer 编辑器核心：归类加载完再挂（HTML 册不先挂再卸载），取到的详情交回 Shell（R1） -->
    <UniverEditorCore
      v-if="modeResolved"
      ref="univerEditorCoreRef"
      :project-id="projectId" :project-year="projectYear"
      :wp-id="wpId"
      :wp-detail="wpDetail!"
      :can-edit="effectiveCanEdit"
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
      @update:wp-detail="onCoreWpDetail"
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

      </div>
      <AuditYearMissingResult v-else :loading="!projectMeta && !projectMetaFailed" :failed="projectMetaFailed"
        @retry="loadProjectMeta" @back="goBack" />
    </div><!-- /gt-wp-editor-main -->

    <!-- 编制说明面板内容（trigger/placement 由 shell 拥有；G-RAIL adapter） -->
    <template #guidance-panel>
      <WpGuidancePanel
        v-if="wpDetail && projectYear != null"
        shell-owned
        :wp-id="wpId"
        :wp-code="wpDetail.wp_code || ''"
        :wp-name="wpDetail.wp_name || ''"
        :component-type="componentType || ''"
        :project-id="projectId"
        :year="projectYear"
        :sheet-code="activeSheetContext.sheetCode"
        :sheet-name="activeSheetContext.sheetName"
        :sheet-uid="activeSheetContext.sheetUid"
        :sheet-uid-null-reason="activeSheetContext.sheetUidNullReason"
        :host="activeSheetContext.host"
        :whole-workbook="activeSheetContext.wholeWorkbook"
        :owner-epoch="activeSheetContext.ownerEpoch ?? 0"
        :context-revision="activeSheetContext.contextRevision ?? 0"
      />
    </template>

    <!-- 底稿复核：Shell trigger 仅开关 GtReviewDialog drawer，panel slot 留空不占位 -->
    <template #review-panel>
      <span />
    </template>
  </WorkpaperCapabilityShell>

  <!-- 底稿复核对话 Drawer（由 useReviewDialogProvider 驱动，子组件 inject 触发） -->
  <GtReviewDialogLazy
    v-if="reviewPanelOpen && reviewActivation"
    :wp-id="reviewActivation.wpId || wpId"
    :section-id="reviewActivation.sectionId"
    :section-label="reviewActivation.sectionLabel"
    :current-user="reviewActivation.currentUser"
    :related-data="reviewActivation.relatedData"
    @closed="onShellCloseReview"
  />

  <!-- 弹窗/抽屉（条件渲染，不占主布局） -->
  <CycleDialogHost
    v-if="wpDetail && projectYear != null"
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

  <!-- 非 HTML 编辑器仍使用编辑器级 Host；HTML 路径由 GtWpRenderer Runtime Boundary 唯一承载。 -->
  <GtWpVersionTrail
    v-if="!useHtmlRenderer && projectYear != null"
    ref="versionTrailRef"
    :workpaper-id="wpId"
    :project-id="projectId"
    @rollback-completed="onVersionTrailRollbackCompleted"
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

  <WpImportDialog
    v-model="showWpImportEnhanced"
    :project-id="projectId"
    @imported="onWpImportEnhanced"
  />

  <!-- R7-S3-05 Task 25：底稿右栏面板（抽屉模式）— 提到 HTML/Univer 共用，供 AttachmentTabPanel → Drawer_Host -->
  <el-drawer
    v-model="showSidePanel"
    title="底稿面板"
    direction="rtl"
    size="400px"
    :with-header="true"
    :modal="false"
    append-to-body
  >
    <WorkpaperSidePanel
      v-if="projectYear != null"
      :project-id="projectId"
      :wp-id="wpId"
      :year="projectYear"
      :wp-code="wpDetail?.wp_code"
      :decision-trace="renderConfig?.decision_trace ?? null"
      @finecheck-update="fineCheckFailCount = $event"
    />
  </el-drawer>
</template>

<script setup lang="ts">
// [platform-context-permission-foundation P0-6.1]
// ProjectContext + PermissionMatrix facade 已接入
// TODO(P1): 逐步替换下方 route.params 直接解析为 projectContext 读取

/**
 * WorkpaperEditor — 底稿编辑器 Shell 容器
 *
 * 职责：路由解析 + 模式分发（HTML/Univer/子编辑器）+ 子 SFC 编排 + provide context
 * 不持有 Univer 实例化 / 保存逻辑 / 弹窗渲染（已下沉到子 SFC + composable）
 *
 * @see .kiro/specs/workpaper-editor-shrink-phase2/design.md §4.2
 */
import { ref, computed, provide, onMounted, onUnmounted, watch, inject, defineAsyncComponent } from 'vue'
import { useProjectStore } from '@/stores/project'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { confirmLeave } from '@/utils/confirm'
import { eventBus, type WorkpaperSavedPayload } from '@/utils/eventBus'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { useAuditContext } from '@/composables/useAuditContext'
import { useA13MisstatementBridge } from '@/composables/useA13MisstatementBridge'
import { useStaleRefresh } from '@/composables/useStaleRefresh'
import { useCycleType } from '@/composables/useCycleType'
import { useEditorMode } from '@/composables/useEditorMode'
import {
  resolveUniverSheetContext,
  useWpRenderer,
  type RenderConfig,
  type SheetRenderConfig,
  type WorkpaperSheetContext,
} from '@/composables/useWpRenderer'
import { createHtmlStableContextEmitter } from '@/composables/htmlStableContextEmitter'
import { useEditorToolbar } from '@/composables/useEditorToolbar'
import { useEditorCycles } from '@/composables/useEditorCycles'
import { useSheetNavFacade } from '@/composables/useSheetNavFacade'
import { useEditingLock } from '@/composables/useEditingLock'
import { useStepMapping } from '@/composables/useStepMapping'
import { useStaleImpact, type StaleAffectedItem } from '@/composables/useStaleImpact'
import { warnIgnoredPrograms } from '@/composables/useProgramRowControl'
import { prerequisiteWpCode, usePrerequisiteStatus } from '@/composables/usePrerequisiteStatus'
import { useWorkpaperRefresh } from '@/composables/useWorkpaperRefresh'
import { useWorkpaperReviewMarkers, type ReviewMarkerTicket } from '@/composables/useWorkpaperReviewMarkers'
import { useReviewDialogProvider } from '@/composables/useReviewDialogProvider'
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
import WpExportButton from '@/components/workpaper/WpExportButton.vue'
import WpImportDialog from '@/components/workpaper/WpImportDialog.vue'
import WpGuidancePanel from '@/components/workpaper/WpGuidancePanel.vue'
import AuditYearMissingResult from '@/components/common/AuditYearMissingResult.vue'
const GtReviewDialogLazy = defineAsyncComponent(() => import('@/components/collaboration/GtReviewDialog.vue'))
import GtWpVersionTrail from '@/components/workpaper/version-trail/GtWpVersionTrail.vue'
import WorkpaperCapabilityShell from '@/shell/formula/WorkpaperCapabilityShell.vue'
import { GC0_CONTRACT_VERSION, type CanonicalWorkpaperLocation } from '@/shared/contracts/gc0'
import { DSH_ASSIST_BRIDGE_KEY } from '@/shell/formula/dshAssistBridge'
import { openFormulaManagerFromLocation } from '@/shell/formula/openFormulaManagerFromLocation'
import { FORMULA_MANAGER_CAPABILITY_CONTEXT } from '@/shell/formula/formulaManagerCapabilityContext'
import { useGuidancePanelStore } from '@/stores/guidancePanelStore'
import { Clock } from '@element-plus/icons-vue'
import { openLedgerWindow } from '@/utils/openLedgerWindow'
import { useWorkpaperProjectMeta } from './workpaper-editor/useWorkpaperProjectMeta'
import { useShellCapability } from './workpaper-editor/useShellCapability'

// ─── 路由解析 ────────────────────────────────────────────────────────────────
const route = useRoute()
const router = useRouter()
const { canEdit, isArchived } = useAuditContext()

// ─── 全局复核对话 provider（驱动右侧面板 + GtWpReviewRail + 子组件 inject） ──
const { isOpen: reviewPanelOpen, activationParams: reviewActivation, openReviewDialog: openReview, closeReviewDialog: closeReview } = useReviewDialogProvider()

/** Shell 右侧 rail trigger 点击时触发复核对话 Drawer */
function onShellOpenReview(): void {
  openReview({
    wpId: wpId.value,
    sectionId: 'general',
    sectionLabel: wpDetail.value?.wp_name || '底稿复核',
    currentUser: { id: '', name: 'admin', role: '审计助理' },
    relatedData: { wpCode: wpDetail.value?.wp_code, projectId: projectId.value },
  })
}

/** Shell / GtReviewDialog 关闭时同步清理 */
function onShellCloseReview(): void {
  closeReview()
}
const projectId = computed(() => route.params.projectId as string)
const wpId = computed(() => route.params.wpId as string)
const { renderConfig } = useWpRenderer(wpId, { silent: true }) // 只给侧栏 decision_trace，失败不弹全局提示（R10）
// 深链 ?sheet= 初始激活底稿页签（无 ?cell= 的纯 Tab 导航，如附注→披露表跳转）。
// GtWpRenderer 仅 initialSheet + locate-cell 事件切页；此前未接线导致纯 ?sheet= 被忽略回退底稿目录。
const initialSheetFromQuery = computed<string | undefined>(() => {
  const q = route.query.sheet
  const v = Array.isArray(q) ? q[0] : q
  return v ? String(v) : undefined
})

// ─── P0-6.1: ProjectContext + PermissionMatrix facade ────────────────────────
const projectStore = useProjectStore()
const projectContext = computed(() => projectStore.currentProjectContext)
const { can: canOp, whyCannot } = usePermissionMatrix()
// DEPRECATED: 旧 canEdit 仍保留，后续逐步替换为 canOp('wp:edit')


// ─── A13 错报推送桥：底稿"推送错报至A13错报汇总"事件的唯一消费者 ──────────────
// 各底稿子组件 emit('a13:push-misstatement') → 本桥归一化后写入未更正错报汇总表 + 溯源。
useA13MisstatementBridge()

// ─── useStaleRefresh：试算表/调整变更后提示底稿数据可能过时 ──────────────────
const wpStaleRefresh = useStaleRefresh(projectId, {
  events: ['trial-balance:updated', 'adjustment:saved'],
  mode: 'prompt',
  onRefresh: () => onManualRefresh(),
})

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
const showWpImportEnhanced = ref(false)

// ─── 复核对话线程列表（工具栏 popover）──────────────────────────────────────
const reviewThreadList = ref<{ section_id: string; has_unread: boolean }[]>([])
const reviewThreadCount = computed(() => reviewThreadList.value.length)

async function loadReviewThreadList() {
  if (!wpId.value) return
  try {
    const res = await httpApi.get('/api/review-threads/active', {
      params: { wp_id: wpId.value },
      _silent: true,
    } as any)
    const data = res?.data?.data || res?.data || []
    if (Array.isArray(data)) {
      reviewThreadList.value = data
    }
  } catch { /* silent */ }
}

function onOpenReviewThread(item: { section_id: string }) {
  // 触发 provide 下的 openReviewDialog（通过 eventBus）
  eventBus.emit('review-dialog:open', {
    wpId: wpId.value,
    sectionId: item.section_id,
    sectionLabel: item.section_id,
  })
}
const univerEditorCoreRef = ref<InstanceType<typeof UniverEditorCore> | null>(null)
const wpRendererRef = ref<InstanceType<typeof GtWpRenderer> | null>(null)
const versionTrailRef = ref<InstanceType<typeof GtWpVersionTrail> | null>(null)

function onWpImportEnhanced() {
  showWpImportEnhanced.value = false
  eventBus.emit('workpaper-refresh')
}

// ─── 模式分发（useEditorMode） ──────────────────────────────────────────────
const {
  componentType,
  useHtmlRenderer,
  wpClassification,
  fetchComponentType,
} = useEditorMode({ wpId, projectId, wpDetail })
const modeResolved = ref(false) // 归类加载完（成功或失败）才挂 Univer 核心（R1）
const onCoreWpDetail = (d: WorkpaperDetail) => { wpDetail.value = d }

// ─── 函证枢纽（D0/E0/F0/G0/H0/K0/L0） ──────────────────────────────────────
// workbook 级 componentType 为 confirmation-hub：底稿在编辑器内按源模板逐 sheet 编制
// （底稿目录 / X0A 程序表 / X0-1 汇总 / X0-2~X0-8），函证管理中心台账由入口按钮跳转，
// 二者通过 X0-1「同步到函证中心」与回函 confirmation:received 事件双向联动。
const isConfirmationHubWorkbook = computed<boolean>(() =>
  componentType.value === 'confirmation-hub'
  || wpClassification.componentType?.value === 'confirmation-hub',
)

function goConfirmationHub() {
  router.push({ name: 'ConfirmationHub', params: { projectId: projectId.value } })
}

// ─── 循环类型 ────────────────────────────────────────────────────────────────
const cycleType = useCycleType(wpDetail)
const { isDCycle, isFCycle, isGCycle, isHCycle, isICycle, isKCycle, isLCycle, isMCycle, isNCycle } = cycleType

// ─── 底稿标题规范化（多 sheet 科目底稿显示纯科目名） ─────────────────────────
// D~N 多 sheet 底稿（如 D2 含 目录/程序表/审定表/明细/附注）是整个科目的工作底稿集合，
// 标题应显示科目名（如"应收账款"）而非单个 sheet 名（"应收账款审定表"）。
// 去掉常见的 sheet 级后缀，保留科目主体。
const displayWpName = computed(() => {
  const raw = wpDetail.value?.wp_name || ''
  if (!raw) return ''
  return raw
    .replace(/审定表及明细表$/, '')
    .replace(/及明细表$/, '')
    .replace(/审定表$/, '')
    .replace(/明细表$/, '')
    .trim() || raw
})

// ─── Sheet 导航 facade ──────────────────────────────────────────────────────
const univerAPIRef = ref<any>(null)
const { projectMeta, projectYear, projectMetaFailed, loadProjectMeta } = useWorkpaperProjectMeta(projectId)
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
const univerRenderSheets = ref<SheetRenderConfig[]>([])
const univerSheetIdentityReady = ref(false)
const univerWpCode = ref<string | null>(null)
/** Univer/OnlyOffice host shares the same revision-owner contract as HTML Task 11. */
const univerContextEmitter = createHtmlStableContextEmitter()
let univerIdentityRequestId = 0

/** Univer 不挂载 GtWpRenderer，故单独读取同一 render-config identity 目录。 */
async function loadUniverSheetIdentityCatalog(): Promise<void> {
  const requestId = ++univerIdentityRequestId
  const requestedWpId = wpId.value
  univerRenderSheets.value = []
  univerWpCode.value = null
  univerSheetIdentityReady.value = false
  if (!requestedWpId || useHtmlRenderer.value) return
  try {
    const config = await httpApi.get<RenderConfig>(
      `/api/workpapers/${requestedWpId}/render-config`, { _silent: true, _dedupe: false } as any, // 失败有回退，不弹全局提示（R10）
    )
    if (requestId !== univerIdentityRequestId || requestedWpId !== wpId.value) return
    univerRenderSheets.value = Array.isArray(config?.sheets) ? config.sheets : []
    univerWpCode.value = config?.wp_code ?? null
  } catch {
    if (requestId !== univerIdentityRequestId || requestedWpId !== wpId.value) return
    // 目录不可用时仍允许以真实 engine name 请求，后端 guidance membership 继续 fail-closed。
    univerRenderSheets.value = []
    univerWpCode.value = null
  } finally {
    if (requestId === univerIdentityRequestId && requestedWpId === wpId.value) {
      univerSheetIdentityReady.value = true
    }
  }
}

// 路由复用同一 Shell 时重建目录；切回 HTML 时使在途 Univer 响应失效。
watch([wpId, useHtmlRenderer], ([, isHtml], [oldWpId, wasHtml]) => {
  if (isHtml) {
    univerIdentityRequestId += 1
    univerRenderSheets.value = []
    univerSheetIdentityReady.value = false
  } else if (wpId.value !== oldWpId || wasHtml) {
    void loadUniverSheetIdentityCatalog()
  }
})

// ─── useEditorCycles 实例化 ─────────────────────────────────────────────────
const { cycleDialogs, fCycle, iCycle, gCycle, kCycle, lCycle, mCycle, nCycle } = useEditorCycles({
  wpDetail,
  projectId,
  wpId,
  sheetNavActiveId,
  sheetNavFacade,
  cycleType, projectYear,
})

// ─── 编辑锁 ─────────────────────────────────────────────────────────────────
const editLock = useEditingLock({
  resourceId: computed(() => wpId.value || ''),
  enabled: canEdit, // 只读身份不取锁（取锁被拒会留拒绝记录、还可能把要编辑的人挤成只读，R2）
})

// 多窗口门禁（spec: multi-window-ledger-workbench Phase 3 Task 18）：编辑锁冲突时覆盖 canEdit，禁用所有保存/编辑操作
const effectiveCanEdit = computed(() => canEdit.value && !editLock.forcedReadonly.value)

// ─── 前置状态横幅 ────────────────────────────────────────────────────────────
// 按当前底稿编码请求：详情加载 / 换底稿后重取，没有前置环节的循环不请求（原先 setup 时取值 ⇒ 恒按 E1，R9）
const prerequisiteStatus = usePrerequisiteStatus(() => projectId.value, () => prerequisiteWpCode(wpDetail.value?.wp_code))
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
    canEdit: effectiveCanEdit,
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
    onFormulaManager: () => { onFormulaManager() },
  },
)

// ─── provide(EDITOR_CONTEXT_KEY) ────────────────────────────────────────────
provide(EDITOR_CONTEXT_KEY, {
  projectId,
  wpId,
  wpDetail,
  canEdit: effectiveCanEdit,
  componentType,
  cycleType,
  cycleDialogs,
  sheetNavActiveId,
} as EditorContextData)

// ─── Event handlers ─────────────────────────────────────────────────────────

function onChildSaved(payload?: { sheet_name: string; html_data: Record<string, any>; schema_version?: string }) {
  // HTML 渲染器（A~E 类）保存：持久化 html_data 到后端 parsed_data
  // （Univer/子编辑器走自身保存通道，调用本函数时不带 payload，仅刷新）
  if (payload && payload.sheet_name) {
    httpApi.post(`/api/workpapers/${wpId.value}/save`, {
      sheet_name: payload.sheet_name,
      html_data: payload.html_data,
      schema_version: payload.schema_version || 'v2025-R5',
    }).then(warnIgnoredPrograms).catch((e) => {
      // 409 是业务状态冲突，必须给用户明确指引；其余失败静默告警不阻断 UI。
      // 🔴 原先这里只有 console.warn，用户会以为「保存成功」—— 实际数据一行都没落库
      // （D2-2 这类已绑定 OO 的双向底稿，走本通道必然 409）。
      const status = e?.response?.status ?? e?.status
      const detail = e?.response?.data?.detail
      if (status === 409) {
        ElMessage.error(detail?.message || '该底稿已绑定在线编辑，请切换到「在线编辑」模式保存')
      } else {
        console.warn('[WorkpaperEditor] HTML 底稿保存失败:', e)
      }
    })
  }
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
  // 复盘 P1-2：forcedReadonly 时不接受 dirty 状态，避免弹"有未保存变更"但无法保存的矛盾
  if (val && editLock.forcedReadonly.value) return
  dirty.value = val
}

function updateUniverSheetContext(sheetId: string) {
  if (!univerSheetIdentityReady.value) return
  const context = resolveUniverSheetContext(
    sheetNavFacade.flatSheets.value,
    sheetId,
    univerRenderSheets.value,
    wpDetail.value?.wp_code || univerWpCode.value || null,
  )
  if (!context) return
  // Univer native/custom/locate converge here — same revision owner as HTML emitter contract.
  const publication = univerContextEmitter.publish(context)
  if (publication) activeSheetContext.value = publication.context
}

function onSwitchSheet(sheetId: string) {
  // Must publish; no-op would leave guidance/shell on stale sheet (Req 10.3).
  updateUniverSheetContext(sheetId)
}

function onDialogApplied(_sheet: string) {
  // dialog applied 后刷新
  onChildSaved()
}

function onShowVersions() {
  // HTML 路径委托 Runtime Boundary，非 HTML 路径保留编辑器级 Host。
  if (useHtmlRenderer.value) wpRendererRef.value?.openVersionHistory()
  else versionTrailRef.value?.openDrawer()
}

/** 版本回滚完成后刷新底稿数据 */
async function onVersionTrailRollbackCompleted() {
  // 重新加载底稿详情
  try {
    const d = await getWorkpaper(projectId.value, wpId.value)
    if (d) wpDetail.value = d
  } catch { /* ignore */ }
  // 通知子组件/事件总线刷新
  eventBus.emit('workpaper-refresh')
  eventBus.emit('workpaper:saved', {
    projectId: projectId.value,
    wpId: wpId.value,
  } as WorkpaperSavedPayload)
  ElMessage.success('底稿数据已刷新')
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

// ─── 结构化 sheet 上下文（guidance/公式/导航共用）────────────────────────────
const activeSheetContext = ref<WorkpaperSheetContext>({
  sheetName: '',
  sheetCode: null,
  sheetUid: null,
  sheetUidNullReason: 'sheet_uid_unavailable',
  host: 'univer',
  wholeWorkbook: false,
  ownerEpoch: 1,
  contextRevision: 0,
})

/** Task 12 shell bridge — live capability snapshot（useShellCapability）。 */
const { shellOwnerEpoch, shellCapabilityEpoch, shellError, shellCapabilitySnapshot } =
  useShellCapability({ wpId, projectId, activeSheetContext })

const shellLocation = computed<CanonicalWorkpaperLocation | null>(() => {
  if (!wpDetail.value || projectYear.value == null) return null // 未设置审计年度：页面不渲染底稿，没有可定位的年度
  const ctx = activeSheetContext.value
  const host = (ctx.host === 'onlyoffice' || ctx.host === 'word' || ctx.host === 'grid' || ctx.host === 'html' || ctx.host === 'univer')
    ? ctx.host
    : 'html'
  // G-ID: never invent sheetUid from display name; fall back to page/whole-workbook.
  const sheetUid = ctx.sheetUid?.trim() || null
  return {
    contractVersion: GC0_CONTRACT_VERSION,
    organizationId: projectId.value,
    projectId: projectId.value,
    fiscalYear: projectYear.value,
    wpId: wpId.value,
    wpCode: wpDetail.value.wp_code || '',
    entryId: null,
    host,
    anchor: ctx.wholeWorkbook
      ? { kind: 'whole_workbook' }
      : sheetUid
        ? { kind: 'sheet', sheetUid, sheetCode: ctx.sheetCode }
        : { kind: 'page' },
    display: { sheetName: ctx.sheetName || null, sectionLabel: null },
    ownerEpoch: ctx.ownerEpoch ?? shellOwnerEpoch.value,
    contextRevision: ctx.contextRevision ?? 1,
  }
})

provide(FORMULA_MANAGER_CAPABILITY_CONTEXT, {
  capability: shellCapabilitySnapshot,
  location: shellLocation,
})

const guidancePanelStore = useGuidancePanelStore()
const shellGuidanceController = computed(() => ({
  isOpen: guidancePanelStore.isOpen,
  hasDraft: false,
  guidanceVersion: guidancePanelStore.guidanceData?.guidance_version ?? null,
  open: () => guidancePanelStore.open(),
  close: (_opts: { preserveDraft: boolean }) => guidancePanelStore.close(),
}))

const dshBridge = inject(DSH_ASSIST_BRIDGE_KEY, null)

function openShellDsh(): void {
  dshBridge?.open()
}

function closeShellDsh(opts: { preserveDraft: boolean }): void {
  dshBridge?.close(opts)
}

function onHtmlSheetChange(context: WorkpaperSheetContext) {
  activeSheetContext.value = context
}

// Univer custom nav、原生 tab 与 locate 最终都会更新 facade.activeSheetId；
// engine id/name 在此与 render-config identity 目录合流，禁止前端正则猜 code。
watch(
  () => [
    useHtmlRenderer.value,
    univerSheetIdentityReady.value,
    sheetNavActiveId.value,
    sheetNavFacade.flatSheets.value.map((sheet) => `${sheet.id}:${sheet.name}`).join('|'),
    univerRenderSheets.value.map((sheet) => `${sheet.sheet_name}:${sheet.sheet_code ?? ''}`).join('|'),
  ] as const,
  ([isHtml, identityReady, activeId]) => {
    if (!isHtml && identityReady && activeId) updateUniverSheetContext(activeId)
  },
  { immediate: true },
)

watch(wpId, (nextId) => {
  univerContextEmitter.resetOwner(`wp:${nextId || 'pending'}`)
  activeSheetContext.value = {
    sheetName: '',
    sheetCode: null,
    sheetUid: null,
    sheetUidNullReason: 'sheet_uid_unavailable',
    host: useHtmlRenderer.value ? 'html' : 'univer',
    wholeWorkbook: false,
    ownerEpoch: univerContextEmitter.getOwnerEpoch(),
    contextRevision: 0,
  }
})

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

// ─── 公式管理（ADR-FMC-03 统一 primary outlet，Univer 主路径）──────────────────
// 原 Univer 工具栏只有「同步公式」、无公式管理入口。此处经统一命令校验后提交完整
// CanonicalWorkpaperLocation（取自 shellLocation 的 canonical 身份，不发 nodeKey）。
function onFormulaManager() {
  const loc = shellLocation.value
  const ctx = activeSheetContext.value
  const outcome = openFormulaManagerFromLocation({
    projectId: projectId.value,
    wpId: wpId.value,
    wpCode: loc?.wpCode || wpDetail.value?.wp_code || '',
    year: loc?.fiscalYear ?? projectYear.value,
    sheetName: ctx.wholeWorkbook ? '' : (ctx.sheetName || ''),
    host: 'univer',
    scope: 'workpaper',
    ownerEpoch: loc?.ownerEpoch,
    contextRevision: loc?.contextRevision,
  }, shellCapabilitySnapshot.value, loc)
  if (!outcome.ok) {
    ElMessage.warning(outcome.detail)
  }
}

function onUpload() {
  router.push({
    name: 'WorkpaperList',
    params: { projectId: projectId.value },
    query: { upload: wpId.value },
  })
}

// ─── HTML 渲染器附件/证据打开（open-attachment 事件）──────────────────────

function onOpenAttachment(_payload: { wpId: string; sheetName: string; rowRef: string }) {
  // 打开侧面板（附件 Tab 由 WorkpaperSidePanel 内部管理）
  showSidePanel.value = true
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

// 在独立窗口打开查账（multi-window-ledger-workbench Phase 1 Task 4）；年度 = 本底稿所属项目的审计年度，没有就不带（查账窗口按项目审计年度取）
function onOpenLedgerWindow() {
  openLedgerWindow(projectId.value, projectYear.value ?? undefined)
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

    // 先加载归类：detail 端点不返回 component_type（fetchComponentType 会回退成 'univer'），
    // 函证枢纽等的真实 componentType 需由归类结果派生（derive_component_type 应用
    // _WP_CODE_OVERRIDE，E0/D0/F0/G0/H0/K0/L0 → confirmation-hub）。必须在
    // useHtmlRenderer 判定之前完成，否则 confirmation-hub 会落 Univer 路径。
    try {
      await wpClassification.load()
    } catch { /* 静默：归类失败回退到 Univer/子编辑器路径 */ }
    modeResolved.value = true

    // D0/E0/F0/G0/H0/K0/L0 函证枢纽：**不再整体重定向到函证管理中心**。
    // 这些底稿是多 sheet 工作簿（底稿目录 / X0A 程序表 / X0-1 函证结果汇总 /
    // X0-2 核实被函证单位 / X0-3 跟函过程控制 / X0-4 差异调节 / X0-5·X0-6 替代程序 /
    // X0-7 回函可靠性 / X0-8 舞弊风险），每个 sheet 都有已注册的专属组件，
    // 须在底稿编辑器内按源模板逐 sheet 编制；函证管理中心台账改由标题栏入口按钮跳转。
    // （confirmation-hub 已加入 HTML_RENDERER_ROUTE_SET，故 useHtmlRenderer 为 true。）

    if (useHtmlRenderer.value) {
      loading.value = false
      return
    }

    await loadUniverSheetIdentityCatalog()
    if (componentType.value === 'univer' || !componentType.value) {
      // UniverEditorCore 内部处理 initUniver
      loading.value = false
    } else {
      loading.value = false
    }
    // 深链 ?cell=：HTML 路径由 GtWpRenderer 的 initial-cell 处理；Univer 路径在模式判定后才发（spec wp-deeplink-cell-locate-closure）
    const queryCell = typeof route.query.cell === 'string' ? route.query.cell : ''
    if (queryCell) setTimeout(() => eventBus.emit('workpaper:locate-cell', { wpId: wpId.value, sheetName: (route.query.sheet as string) || undefined, cellRef: queryCell }), 300)
  })()

  // 加载程序步骤映射
  stepMapping.loadMapping()

  // 加载项目元数据
  loadProjectMeta()

  // 加载复核对话线程列表
  loadReviewThreadList()

  // 浏览器关闭/刷新前警告
  window.addEventListener('beforeunload', onBeforeUnload)
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
})

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
</script>

<style scoped>
.gt-wp-editor-with-guidance {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
}
.gt-wp-editor-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: margin-right 0.3s ease;
}
.gt-wp-io-toolbar {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 16px; background: var(--gt-color-bg-light, #f8f7fc);
  border-bottom: 1px solid var(--gt-color-border, #e8e5f0);
}
.gt-wp-io-toolbar__actions { margin-left: auto; display: flex; gap: 8px; align-items: center; }
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

/* 复核对话线程 popover */
.review-thread-list { max-height: 240px; overflow-y: auto; }
.review-thread-empty { text-align: center; color: #999; font-size: 13px; padding: 12px 0; }
.review-thread-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; cursor: pointer; border-radius: 4px;
  font-size: 13px; transition: background 0.15s;
}
.review-thread-item:hover { background: #f5f7fa; }
.review-thread-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.review-thread-dot.dot-blue { background: #409eff; }
.review-thread-dot.dot-red { background: #f56c6c; }
.review-thread-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #303133; }
.review-thread-unread { font-size: 11px; color: #f56c6c; flex-shrink: 0; }
</style>
