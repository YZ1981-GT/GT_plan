<template>
  <div class="gt-adjustments gt-fade-in">
    <!-- 页面横幅 -->
    <GtPageHeader title="调整分录" @back="router.push('/projects')">
      <GtInfoBar
        :show-unit="true"
        :show-year="true"
        :unit-value="selectedProjectId"
        :year-value="selectedYear"
        :badges="[
          { value: `审计调整 ${summary?.aje_count || 0} 笔 · 重分类 ${summary?.rje_count || 0} 笔` },
          ...(currentTemplateType ? [{ value: currentTemplateType === 'soe' ? '📘 国企版' : '📗 上市版', type: (currentTemplateType === 'soe' ? 'warning' : 'primary') as 'warning' | 'primary' }] : []),
        ]"
        @unit-change="onProjectChange"
        @year-change="onYearChange"
      />
      <template #actions>
        <GtToolbar :show-export="true" :show-import="true" export-label="导出汇总" @export="actions.exportSummary()" @import="openImport">
          <template #right-extra>
            <el-dropdown @command="(t: 'soe' | 'listed') => actions.exportTemplate(t, currentTemplateType)">
              <el-button size="small" plain>
                📋 导出模板
                <el-icon style="margin-left: 4px"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="soe" :class="{ 'is-current-version': currentTemplateType === 'soe' }">
                    📘 国企版模板 (致同 SOE){{ currentTemplateType === 'soe' ? ' ✓ 当前项目' : '' }}
                  </el-dropdown-item>
                  <el-dropdown-item command="listed" :class="{ 'is-current-version': currentTemplateType === 'listed' }">
                    📗 上市版模板 (致同 Listed){{ currentTemplateType === 'listed' ? ' ✓ 当前项目' : '' }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
          <template #left>
            <el-button size="small" type="primary" v-permission="'adjustment:create'" @click="openCreate()" :disabled="!perms.writable || !perms.edit"
              :title="perms.writable ? (perms.edit ? '' : '没有编辑调整分录的权限') : '项目已归档，无法编辑'">+ 新建分录</el-button>
            <el-badge :value="collabInboxCount" :max="99" :hidden="collabInboxCount === 0" class="gt-adj-inbox-badge">
              <el-button size="small" plain @click="inboxDrawerVisible = true" title="转派给我、待我补充/确认的调整分录协作">
                🤝 待我协作
              </el-button>
            </el-badge>
          </template>
        </GtToolbar>
      </template>
    </GtPageHeader>

    <!-- 归档 / 合并锁定 / 缺审计年度 -->
    <ArchivedBanner />
    <ConsolLockedBanner />
    <el-alert v-if="yearResolved && year == null" type="warning" :closable="false" show-icon :title="MISSING_AUDIT_YEAR_MESSAGE" style="margin-bottom: 8px" />

    <!-- AI 内容 pending 顶部 banner（spec global-refinement-v3 Task 6.4） -->
    <AiContentPendingBanner :project-id="projectId" />

    <!-- 跨模块冲突 banner（spec global-refinement-v3 Task 7.5） -->
    <ConflictBanner :project-id="projectId" @view="conflictPanelVisible = true" />
    <ConflictResolutionPanel v-model="conflictPanelVisible" :project-id="projectId" />

    <TrustScorePanel ref="trustScorePanelRef" :project-id="projectId" />
    <StatusMachinePanel ref="smPanelRef" module="adjustment" :instance-id="selectedAdjId" />
    <TimeMachineDrawer ref="tmDrawerRef" module="adjustment" :instance-id="selectedAdjId" @restored="reloadLists" />

    <!-- 在线成员 [enterprise-linkage 3.2] -->
    <PresenceAvatars :project-id="projectId" view-name="adjustments" />

    <!-- 汇总面板（有分录时显示） -->
    <div class="gt-summary-panel" v-if="summary && (summary.aje_count + summary.rje_count > 0)">
      <div class="gt-summary-card">
        <span class="gt-summary-label">审计调整</span>
        <span class="gt-summary-value">{{ summary.aje_count }} 笔</span>
        <span class="gt-summary-sub">借 {{ fmtAmount(summary.aje_total_debit) }} / 贷 {{ fmtAmount(summary.aje_total_credit) }}</span>
      </div>
      <div class="gt-summary-card">
        <span class="gt-summary-label">重分类</span>
        <span class="gt-summary-value">{{ summary.rje_count }} 笔</span>
        <span class="gt-summary-sub">借 {{ fmtAmount(summary.rje_total_debit) }} / 贷 {{ fmtAmount(summary.rje_total_credit) }}</span>
      </div>
      <div class="gt-summary-card gt-summary-card--impact">
        <span class="gt-summary-label">已计入试算表</span>
        <span class="gt-summary-value gt-summary-value--sm">{{ approvedImpact.entries }} 笔 · {{ approvedImpact.accounts }} 个科目</span>
        <span class="gt-summary-sub">
          只有已批准的分录计入审定数
          <el-button size="small" text type="primary" @click="router.push(`/projects/${projectId}/trial-balance`)">查看试算表 →</el-button>
        </span>
      </div>
      <el-button style="margin-left: auto; align-self: flex-start" type="primary" plain :icon="Reading" @click="showHandbook = true">使用手册</el-button>
    </div>

    <!-- 空态引导 -->
    <div v-if="!loading && entries.length === 0 && summary && (summary.aje_count + summary.rje_count === 0)" class="gt-adj-empty-guide">
      <div class="gt-adj-empty-guide__header">
        <h3>开始编制调整分录</h3>
        <p>分录先存为草稿，提交复核并批准后计入试算表审定数，报表与附注随之更新。选择一种方式开始：</p>
      </div>
      <div class="gt-adj-empty-guide__cards">
        <div class="gt-adj-guide-card" @click="onGuideSyncFromWp">
          <span class="gt-adj-guide-card__icon">📥</span>
          <span class="gt-adj-guide-card__title">从底稿同步</span>
          <span class="gt-adj-guide-card__desc">把各科目底稿里编好的调整分录汇聚到这里统一复核</span>
        </div>
        <div class="gt-adj-guide-card" @click="openCreate()">
          <span class="gt-adj-guide-card__icon">✏️</span>
          <span class="gt-adj-guide-card__title">手工新建</span>
          <span class="gt-adj-guide-card__desc">直接录入，支持常用模板（坏账 / 折旧 / 重分类等）和从 Excel 粘贴</span>
        </div>
        <div class="gt-adj-guide-card" @click="openImport">
          <span class="gt-adj-guide-card__icon">📊</span>
          <span class="gt-adj-guide-card__title">Excel 导入</span>
          <span class="gt-adj-guide-card__desc">下载国企版 / 上市版模板填写，预检通过后批量导入</span>
        </div>
        <div class="gt-adj-guide-card" @click="showHandbook = true">
          <span class="gt-adj-guide-card__icon">📖</span>
          <span class="gt-adj-guide-card__title">查看使用手册</span>
          <span class="gt-adj-guide-card__desc">录入规则、复核流程、通知与联动</span>
        </div>
      </div>
    </div>
    <div v-else-if="!summary" class="gt-adj-handbook-fallback">
      <el-button type="primary" plain :icon="Reading" @click="showHandbook = true">使用手册</el-button>
    </div>

    <!-- 筛选 -->
    <div class="gt-adj-tabs-row">
      <el-tabs v-model="activeTab" class="gt-adj-tabs" @tab-change="adjPage = 1">
        <el-tab-pane label="全部" name="all" />
        <el-tab-pane label="审计调整" name="aje" />
        <el-tab-pane label="重分类" name="rje" />
      </el-tabs>
      <el-segmented v-model="originFilter" :options="ORIGIN_FILTER_OPTIONS" size="small" class="gt-adj-origin-filter" @change="adjPage = 1">
        <template #default="{ item }">
          <el-tooltip :content="item.tip" placement="top" :disabled="!item.tip" :show-after="200">
            <span>{{ item.label }}</span>
          </el-tooltip>
        </template>
      </el-segmented>
      <el-button size="small" type="success" plain @click="onGuideSyncFromWp" title="底稿里编的调整分录如何汇聚到这里">📥 从底稿同步</el-button>
      <el-select v-if="entries.length > 0" v-model="creatorFilter" placeholder="全部编制人" clearable size="small" style="width: 140px" @change="adjPage = 1">
        <el-option v-for="name in creatorOptions" :key="name" :label="name" :value="name" />
      </el-select>
      <el-checkbox v-if="entries.length > 0" v-model="collabOnly" size="small" @change="adjPage = 1">仅看协作中</el-checkbox>
      <el-tooltip content="全屏查看（ESC 退出）" placement="bottom">
        <el-button size="small" plain class="gt-adj-fs-btn" @click="hallTableRef?.toggleFullscreen()">⛶ 全屏</el-button>
      </el-tooltip>
    </div>
    <div v-if="entries.length > 0" class="gt-adj-status-row">
      <el-radio-group v-model="statusFilter" size="small" @change="adjPage = 1">
        <el-radio-button v-for="s in STATUS_FILTERS" :key="s.value" :value="s.value">{{ s.label }} {{ statusCounts[s.value] || 0 }}</el-radio-button>
      </el-radio-group>
      <span v-if="statusCounts.pending_review && perms.review" class="gt-adj-status-hint">有 {{ statusCounts.pending_review }} 笔待你复核</span>
    </div>

    <!-- 科目过滤提示（从试算表跳转时显示） -->
    <el-alert v-if="filterAccount" type="info" show-icon :closable="true" style="margin-bottom: 12px" @close="filterAccount = ''">
      <template #title>
        <span>当前仅显示科目 <strong>{{ filterAccount }}</strong> 的相关分录</span>
        <el-button size="small" text type="primary" style="margin-left: 8px" @click="filterAccount = ''">查看全部</el-button>
      </template>
    </el-alert>
    <el-alert v-if="!loading && entries.length > 0 && filteredEntries.length === 0" type="info" show-icon :closable="false" style="margin-bottom: 12px"
      title="当前筛选条件下没有分录，切换类型 / 状态或清除筛选查看全部。" />

    <!-- 批量操作栏 -->
    <div v-if="selectedRows.length > 0" class="gt-adj-batch-actions">
      <span>已选 {{ selectedRows.length }} 笔</span>
      <el-button v-for="b in batchButtons" :key="b.action" size="small" :type="b.type" :disabled="!b.count || !!actions.busy.value"
        :loading="actions.isBusy(b.action)" @click="onBatch(b.action)">{{ b.label }} ({{ b.count }})</el-button>
      <el-button size="small" text @click="hallTableRef?.clearSelection()">取消选择</el-button>
    </div>

    <!-- 分录列表（点表格后粘贴 Excel 多行 ⇒ 打开新建弹窗预填；tabindex 让点表格时焦点落在这里，粘贴事件才到得了） -->
    <div class="gt-adj-paste-zone" tabindex="0" @paste="onHallPaste">
      <AdjustmentHallTable
        ref="hallTableRef"
        :rows="pagedEntries"
        :loading="loading"
        :perms="perms"
        :busy="actions.busy.value"
        :focus-id="focusId"
        :stale-misstatement-ids="missStaleIdSet"
        @selection-change="(rows: any[]) => (selectedRows = rows)"
        @action="onRowAction"
      />
    </div>
    <div class="gt-pagination" v-if="adjTotal > adjPageSize">
      <el-pagination v-model:current-page="adjPage" :page-size="adjPageSize" :total="adjTotal" layout="total, prev, pager, next" background small />
    </div>

    <!-- 弹窗 -->
    <AdjustmentEntryDialog ref="entryDialogRef" :project-id="projectId" :year="year" :account-options="accountOptions"
      :accounts-ready="accountsReady" :can-edit="perms.writable && perms.edit" @saved="onEntrySaved" />
    <AdjustmentSubmitReviewDialog ref="submitDialogRef" :project-id="projectId" @done="reloadLists" />
    <AdjustmentReasonDialog ref="reasonDialogRef" />
    <AdjustmentImportDialog ref="importDialogRef" :project-id="projectId" :year="year" :template-type="currentTemplateType"
      :can-edit="perms.writable && perms.edit" @download-template="onDownloadTemplate"
      @imported="reloadLists" @submit-review="onSubmitImported" />

    <el-dialog v-model="impactVisible" :title="`影响范围 · ${impactRow?.adjustment_no || ''}`" width="640px" append-to-body>
      <p class="gt-adj-impact-tip">按本分录的科目与金额测算对报表行、底稿的影响（批准后才计入；草稿只是预览）。</p>
      <AdjustmentImpactPreview v-if="impactVisible && impactRow" :project-id="projectId" :year="year"
        :line-items="impactRow.line_items || []" />
    </el-dialog>
    <el-dialog v-model="relatedVisible" title="关联底稿" width="480px" append-to-body>
      <div v-for="w in relatedWps" :key="w.id" class="gt-adj-related-item" @click="openWorkpaper(w.id)">
        <span class="gt-adj-related-code">{{ w.wp_code }}</span> {{ w.wp_name }}
      </div>
    </el-dialog>

    <!-- 调整分录协作接力（adjustment-collaboration-and-propagation） -->
    <AdjustmentCollaborationDialog
      v-model="collabDialogVisible"
      :project-id="projectId"
      :year="selectedYear ?? year"
      :entry-group-id="collabRow?.entry_group_id || ''"
      :adjustment-no="collabRow?.adjustment_no"
      :account-options="accountOptions"
      :line-items="collabLineItems"
      :can-edit="perms.writable"
      @updated="onCollabUpdated"
    />

    <!-- 待我协作 收件箱 -->
    <el-drawer v-model="inboxDrawerVisible" title="待我协作的调整分录" size="420px" append-to-body>
      <el-empty v-if="collabInbox.length === 0" description="暂无待我协作的分录组" :image-size="80" />
      <div v-else class="gt-adj-inbox-list">
        <div v-for="it in collabInbox" :key="it.id" class="gt-adj-inbox-item" @click="openCollabFromInbox(it)">
          <div class="gt-adj-inbox-row">
            <span class="gt-adj-inbox-no">{{ entryNo(it.entry_group_id) }}</span>
            <el-tag size="small" :type="it.status === 'contributed' ? 'primary' : (it.status === 'acknowledged' ? 'warning' : 'info')">
              {{ COLLAB_STATUS_LABELS[it.status] || it.status }}
            </el-tag>
            <span class="gt-adj-inbox-round">第 {{ it.round }} 轮</span>
          </div>
          <div v-if="it.note" class="gt-adj-inbox-note">📝 {{ it.note }}</div>
        </div>
      </div>
    </el-drawer>

    <AdjustmentsHandbookDialog v-model="showHandbook" />
  </div>
</template>

<script setup lang="ts">
/**
 * 调整分录大厅（spec adjustment-hall-entry-review-closure 需求 5）。
 *
 * 录入 / 导入 / 提交复核 / 驳回 / 撤回等弹窗在 components/adjustment，写操作在 useAdjustmentHallActions；
 * 本页负责取数（全部分页）、筛选与计数、深链（?focus= 定位高亮、?group= 打开协作、?account= 按科目过滤）与 SSE 刷新。
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown, Reading } from '@element-plus/icons-vue'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'
import AdjustmentsHandbookDialog from '@/views/adjustments/AdjustmentsHandbookDialog.vue'
import {
  getAccountDropdown, getAdjustmentSummary, getCollaborationInbox, getProjectAuditYear, listAllAdjustments,
  type AccountOption, type AdjustmentSummary,
} from '@/services/auditPlatformApi'
import { COLLAB_STATUS_LABELS } from '@/components/workpaper/composables/useAdjustmentCollaboration'
import { useProjectStore } from '@/stores/project'
import { fmtAmount } from '@/utils/formatters'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import PresenceAvatars from '@/components/PresenceAvatars.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import { useProjectRole } from '@/composables/useProjectRole'
import { useStaleSummaryFull } from '@/composables/useStaleSummaryFull'
import { handleApiError } from '@/utils/errorHandler'
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'
import { ADJUSTMENT_STATUS, ADJUSTMENT_STATUS_LABELS } from '@/constants/statusEnum'
import { useAuditContext } from '@/composables/useAuditContext'
import { useStaleRefresh } from '@/composables/useStaleRefresh'
import { subscribeProjectEvent, type ProjectEventSubscription } from '@/services/sse/projectEventStream'
import { eventBus } from '@/utils/eventBus'
import ArchivedBanner from '@/components/common/ArchivedBanner.vue'
import ConsolLockedBanner from '@/components/common/ConsolLockedBanner.vue'
import AiContentPendingBanner from '@/components/ai/AiContentPendingBanner.vue'
import ConflictBanner from '@/components/conflict/ConflictBanner.vue'
import ConflictResolutionPanel from '@/components/conflict/ConflictResolutionPanel.vue'
import TrustScorePanel from '@/components/trust/TrustScorePanel.vue'
import StatusMachinePanel from '@/components/status_machine/StatusMachinePanel.vue'
import TimeMachineDrawer from '@/components/time_machine/TimeMachineDrawer.vue'
import AdjustmentCollaborationDialog from '@/components/adjustment/AdjustmentCollaborationDialog.vue'
import AdjustmentHallTable from '@/components/adjustment/AdjustmentHallTable.vue'
import AdjustmentEntryDialog from '@/components/adjustment/AdjustmentEntryDialog.vue'
import AdjustmentSubmitReviewDialog from '@/components/adjustment/AdjustmentSubmitReviewDialog.vue'
import AdjustmentReasonDialog from '@/components/adjustment/AdjustmentReasonDialog.vue'
import AdjustmentImportDialog from '@/components/adjustment/AdjustmentImportDialog.vue'
import AdjustmentImpactPreview from '@/components/adjustment/AdjustmentImpactPreview.vue'
import { parsePastedLines, type EditableLine, type EntrySavedPayload } from '@/components/adjustment/adjustmentLineRules'
import {
  skipMessage, splitEligible, useAdjustmentHallActions, withDescriptions,
  type HallAction, type HallEntry, type HallPerms,
} from '@/composables/useAdjustmentHallActions'

const showHandbook = ref(false)
const route = useRoute()
const router = useRouter()
const { canEdit, onContextChange } = useAuditContext()
const projectStore = useProjectStore()

const projectId = computed(() => projectStore.projectId)
const selectedProjectId = ref(projectStore.projectId)
const projectOptions = computed(() => projectStore.projectOptions)
const selectedYear = ref<number | null>(projectStore.year)

// 权限：项目可写（未归档）× 项目内权限（编辑 / 复核调整分录）
const { projectCan } = useProjectRole(computed(() => projectId.value || ''))
const perms = computed<HallPerms>(() => ({
  writable: canEdit.value,
  edit: projectCan('adjustment:edit'),
  review: projectCan('adjustment:review'),
}))

// ─── useStaleRefresh：试算表变更 / 底稿推送 / 复核状态变化后自动刷新 ───────────
useStaleRefresh(projectId, {
  events: ['trial-balance:updated', 'adjustment:sync-arrived', 'adjustment:review-changed'],
  mode: 'auto',
  onRefresh: () => { void reloadLists() },
})

// ─── SSE → mitt 桥接：broadcast_raw 事件经 SSE 到达，转发到 mitt 供 useStaleRefresh 消费 ──
const _sseSubs: ProjectEventSubscription[] = []
const SSE_BRIDGE_EVENTS = ['adjustment:review-changed', 'adjustment:sync-arrived'] as const
function _refreshAdjustmentsAfterReconnect() {
  // 两个事件走 broadcast_raw、没有 typed replay id；barrier 完成后按当前项目全量校准。
  void fetchEntries()
  void fetchSummary()
  void refreshCollabInbox()
}
function _setupSseBridge(pid: string) {
  _teardownSseBridge()
  if (!pid) return
  for (const evt of SSE_BRIDGE_EVENTS) {
    _sseSubs.push(subscribeProjectEvent(pid, evt, (data) => {
      eventBus.emit(evt as any, { ...(data as Record<string, unknown> || {}), projectId: pid })
    }, { onReconnect: _refreshAdjustmentsAfterReconnect }))
  }
}
function _teardownSseBridge() {
  for (const s of _sseSubs.splice(0)) s.close()
}
watch(projectId, (pid) => _setupSseBridge(pid || ''), { immediate: true })

const conflictPanelVisible = ref(false)

function onProjectChange(pid: string) {
  // 换项目只带年度（定位 / 协作 / 科目过滤参数属于原项目）
  router.push({ path: `/projects/${pid}/adjustments`, query: route.query.year ? { year: route.query.year } : {} })
}
function onYearChange(y: number) {
  selectedYear.value = y
  projectStore.changeYear(y)
  router.push({ path: route.path, query: { year: String(y) } })
}

const routeYear = computed(() => {
  const value = Number(route.query.year)
  return Number.isFinite(value) && value > 2000 ? value : null
})
const projectYear = ref<number | null>(null)
const year = computed<number | null>(() => routeYear.value ?? projectYear.value ?? null)
/** 已问过项目审计年度（问之前不提示「未设置」，免得加载期间闪一下） */
const yearResolved = ref(false)

// Spec A R1：错报阈值变化时，已转错报的分录标「建议重新评估」
const { misstatements: missStaleSummary } = useStaleSummaryFull(computed(() => projectId.value || ''), year)
const missStaleIdSet = computed(() => new Set<string>(missStaleSummary.value.items.map((it: any) => it.id)))

// ─── 数据 ────────────────────────────────────────────────────────────────────
const loading = ref(false)
const entries = ref<any[]>([])
const summary = ref<AdjustmentSummary | null>(null)
const selectedRows = ref<any[]>([])
const accountOptions = ref<AccountOption[]>([])
const accountsReady = ref(false)
const currentTemplateType = ref<'soe' | 'listed' | ''>('')

function queryText(key: string): string {
  const v = route.query[key]
  return typeof v === 'string' ? v : ''
}

// ─── 筛选（客户端：已取全部分录）与状态计数 ─────────────────────────────────
const activeTab = ref('all')
const ORIGIN_FILTER_OPTIONS = [
  { label: '全部来源', value: 'all', tip: '显示手工录入与底稿汇聚的全部调整分录' },
  { label: '手工录入', value: 'manual', tip: '在本模块直接新建 / 导入的调整分录' },
  { label: '底稿汇聚', value: 'workpaper', tip: '从各科目底稿点「同步到调整分录」汇聚而来的分录' },
]
const originFilter = ref('all')
const STATUS_FILTERS = [
  { value: 'all', label: '全部' },
  ...Object.values(ADJUSTMENT_STATUS).map((s) => ({ value: s, label: ADJUSTMENT_STATUS_LABELS[s].label })),
]
const statusFilter = ref('all')
const creatorFilter = ref('')
const collabOnly = ref(false)
const filterAccount = ref(queryText('account'))

const creatorOptions = computed<string[]>(() => {
  const s = new Set<string>()
  for (const e of entries.value) if (e.creator_name) s.add(e.creator_name)
  return [...s].sort((a, b) => a.localeCompare(b, 'zh-CN'))
})
const touchesAccount = (e: any, code: string) =>
  (e.line_items || []).some((li: any) => li.standard_account_code === code || li.detail_account_code === code)
/** 除状态外的筛选（状态计数按它算，计数与列表同口径） */
const baseFiltered = computed(() => entries.value.filter((e: any) =>
  (activeTab.value === 'all' || String(e.adjustment_type).toLowerCase() === activeTab.value)
  && (originFilter.value === 'all' || (originFilter.value === 'workpaper') === (e.origin === 'workpaper'))
  && (!creatorFilter.value || e.creator_name === creatorFilter.value)
  && (!collabOnly.value || e.has_active_collaboration)
  && (!filterAccount.value || touchesAccount(e, filterAccount.value)),
))
const statusCounts = computed(() => {
  const counts: Record<string, number> = { all: baseFiltered.value.length }
  for (const e of baseFiltered.value) counts[e.review_status] = (counts[e.review_status] || 0) + 1
  return counts
})
const filteredEntries = computed(() => (statusFilter.value === 'all'
  ? baseFiltered.value
  : baseFiltered.value.filter((e: any) => e.review_status === statusFilter.value)))

const adjPage = ref(1)
const adjPageSize = 50
const adjTotal = computed(() => filteredEntries.value.length)
const pagedEntries = computed(() => filteredEntries.value.slice((adjPage.value - 1) * adjPageSize, adjPage.value * adjPageSize))
watch(adjTotal, (n) => {
  const max = Math.max(1, Math.ceil(n / adjPageSize))
  if (adjPage.value > max) adjPage.value = max
})

/** 已批准（计入试算表）的笔数与科目数 —— 草稿 / 待复核 / 已驳回不进审定数 */
const approvedImpact = computed(() => {
  const approved = entries.value.filter((e: any) => e.review_status === ADJUSTMENT_STATUS.APPROVED)
  const codes = new Set<string>()
  for (const e of approved) for (const li of e.line_items || []) if (li.standard_account_code) codes.add(li.standard_account_code)
  return { entries: approved.length, accounts: codes.size }
})

// ─── 取数 ────────────────────────────────────────────────────────────────────
async function ensureProjectYear() {
  try {
    if (routeYear.value !== null) {
      projectYear.value = null
      return
    }
    try {
      projectYear.value = await getProjectAuditYear(projectId.value)
    } catch {
      projectYear.value = null
    }
  } finally {
    yearResolved.value = true
  }
}

async function fetchProjectMeta() {
  // 项目模板类型（国企 / 上市）：顶部 badge + 导出模板默认版本
  if (!projectId.value) {
    currentTemplateType.value = ''
    return
  }
  try {
    const data = await api.get(P.projects.detail(projectId.value))
    const tt = data?.template_type || data?.basic_info?.template_type || ''
    currentTemplateType.value = (tt === 'soe' || tt === 'listed') ? tt : ''
  } catch {
    currentTemplateType.value = ''
  }
}

async function fetchEntries() {
  // 项目没填审计年度：页头横幅已说明，不发请求
  if (year.value == null) { entries.value = []; return }
  loading.value = true
  try {
    entries.value = await listAllAdjustments(projectId.value, year.value)
  } catch {
    /* 全局拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function fetchSummary() {
  if (year.value == null) return
  try {
    summary.value = await getAdjustmentSummary(projectId.value, year.value)
  } catch { /* ignore */ }
}

async function fetchAccountOptions() {
  accountsReady.value = false
  try {
    accountOptions.value = await getAccountDropdown(projectId.value, undefined, year.value)
    accountsReady.value = true
  } catch {
    accountOptions.value = []
  }
}

async function reloadLists() {
  await Promise.all([fetchEntries(), fetchSummary(), refreshCollabInbox()])
}

async function reloadAdjustmentContext() {
  await ensureProjectYear()
  await fetchProjectMeta()
  projectStore.syncFromRoute(route)
  selectedYear.value = year.value
  filterAccount.value = queryText('account')
  await Promise.all([fetchEntries(), fetchSummary(), fetchAccountOptions(), refreshCollabInbox()])
  if (!projectOptions.value.length) projectStore.loadProjectOptions()
  void applyRouteTargets()
}

// ─── 深链 ────────────────────────────────────────────────────────────────────
// 参数留在地址栏：本页按 fullPath 重挂（routeViewKey），改 query 会整页重挂、把刚打开的弹窗冲掉
// （原先清掉 ?group= 的那一下正是如此，协作通知点进来对话框一闪就没了）
const focusId = ref('')
let focusTimer: ReturnType<typeof setTimeout> | null = null
let routeTargetsApplied = false

async function applyRouteTargets() {
  if (routeTargetsApplied || year.value == null) return
  routeTargetsApplied = true
  const group = queryText('group')
  if (group) openCollabDialog(entries.value.find((e: any) => e.entry_group_id === group) || { entry_group_id: group, line_items: [] })
  const target = queryText('focus') || queryText('highlight')
  if (target) await focusEntry(target, queryText('status'))
}

async function focusEntry(target: string, status: string) {
  const row = entries.value.find((e: any) => e.entry_group_id === target
    || (e.line_items || []).some((li: any) => li.id === target))
  if (!row) {
    ElMessage.info('没有找到要定位的分录（可能已删除、不在当前审计年度或不在你的可见范围）')
    return
  }
  activeTab.value = 'all'
  originFilter.value = 'all'
  creatorFilter.value = ''
  collabOnly.value = false
  filterAccount.value = ''
  statusFilter.value = status && status === row.review_status ? status : 'all'
  const idx = filteredEntries.value.findIndex((e: any) => e.entry_group_id === row.entry_group_id)
  adjPage.value = Math.floor(Math.max(idx, 0) / adjPageSize) + 1
  focusId.value = row.entry_group_id
  await nextTick()
  await hallTableRef.value?.reveal(row.entry_group_id)
  if (focusTimer) clearTimeout(focusTimer)
  focusTimer = setTimeout(() => { focusId.value = '' }, 8000)
}

// ─── 操作 ────────────────────────────────────────────────────────────────────
const hallTableRef = ref<InstanceType<typeof AdjustmentHallTable> | null>(null)
const entryDialogRef = ref<InstanceType<typeof AdjustmentEntryDialog> | null>(null)
const submitDialogRef = ref<InstanceType<typeof AdjustmentSubmitReviewDialog> | null>(null)
const reasonDialogRef = ref<InstanceType<typeof AdjustmentReasonDialog> | null>(null)
const importDialogRef = ref<InstanceType<typeof AdjustmentImportDialog> | null>(null)
const trustScorePanelRef = ref<InstanceType<typeof TrustScorePanel> | null>(null)
const smPanelRef = ref<InstanceType<typeof StatusMachinePanel> | null>(null)
const tmDrawerRef = ref<InstanceType<typeof TimeMachineDrawer> | null>(null)
const selectedAdjId = ref('')

const actions = useAdjustmentHallActions({ projectId, year, onChanged: reloadLists })

function openCreate(prefill?: { lines?: EditableLine[]; description?: string; problems?: string[] }) {
  if (year.value == null) {
    ElMessage.warning(MISSING_AUDIT_YEAR_MESSAGE)
    return
  }
  entryDialogRef.value?.openCreate(prefill)
}

function openImport() {
  if (year.value == null) {
    ElMessage.warning(MISSING_AUDIT_YEAR_MESSAGE)
    return
  }
  importDialogRef.value?.open()
}

function onDownloadTemplate(type: 'soe' | 'listed') {
  void actions.exportTemplate(type, currentTemplateType.value)
}

/** 导入结果里「提交复核（本次 N 笔）」：导入回执只有编号，摘要从刚刷新的列表里补齐 */
async function onSubmitImported(rows: Array<{ entry_group_id: string; adjustment_no: string | null }>) {
  await reloadLists()
  submitDialogRef.value?.open(withDescriptions(rows, entries.value))
}

async function onEntrySaved(p: EntrySavedPayload) {
  await reloadLists()
  if (!p.submit) return
  submitDialogRef.value?.open(
    withDescriptions([{ entry_group_id: p.entryGroupId, adjustment_no: p.adjustmentNo }], entries.value),
  )
}

/** 表格上粘贴 Excel 多行：打开新建弹窗预填，由用户确认保存（原先直接按 AJE 建分录） */
function onHallPaste(e: ClipboardEvent) {
  const text = e.clipboardData?.getData('text/plain') || ''
  if (!text.includes('\t') || !perms.value.writable || !perms.value.edit) return
  if ((e.target as HTMLElement | null)?.closest?.('input, textarea')) return
  const parsed = parsePastedLines(text, accountOptions.value)
  if (!parsed.lines.length) return
  e.preventDefault()
  openCreate({ lines: parsed.lines, description: parsed.summary, problems: parsed.problems })
}

function openReason(mode: 'reject' | 'revoke', rows: HallEntry[]) {
  reasonDialogRef.value?.open(mode, rows, async ({ reason, reasons }) => {
    const ok = mode === 'reject' ? await actions.reject(rows, reason, reasons) : await actions.revoke(rows, reason)
    if (ok) hallTableRef.value?.clearSelection()
    return ok
  })
}

const BATCH_DEFS: Array<{ action: HallAction; label: string; type: 'primary' | 'success' | 'danger' | 'warning' }> = [
  { action: 'submit', label: '提交复核', type: 'primary' },
  { action: 'approve', label: '通过', type: 'success' },
  { action: 'reject', label: '驳回', type: 'danger' },
  { action: 'revoke', label: '撤回复核', type: 'warning' },
  { action: 'delete', label: '删除', type: 'danger' },
]
const batchButtons = computed(() => BATCH_DEFS
  .map((d) => ({ ...d, count: splitEligible(selectedRows.value, d.action, perms.value).eligible.length }))
  .filter((d) => d.count > 0))

async function onBatch(action: HallAction) {
  const { eligible, skipped } = splitEligible(selectedRows.value, action, perms.value)
  if (!eligible.length) return
  if (skipped) ElMessage.info(skipMessage(action, skipped))
  if (action === 'submit') submitDialogRef.value?.open(eligible)
  else if (action === 'reject' || action === 'revoke') openReason(action, eligible)
  else if (action === 'approve') { if (await actions.approve(eligible)) hallTableRef.value?.clearSelection() }
  else if (action === 'delete') { await actions.removeMany(eligible); hallTableRef.value?.clearSelection() }
}

// 影响范围 / 关联底稿
const impactVisible = ref(false)
const impactRow = ref<any>(null)
const relatedVisible = ref(false)
const relatedWps = ref<Array<{ id: string; wp_code: string; wp_name: string }>>([])

async function showRelatedWorkpapers(row: any) {
  try {
    const data: any = await api.get(P.adjustments.relatedWorkpapers(projectId.value, row.entry_group_id))
    const wps = data?.workpapers || []
    if (!wps.length) {
      ElMessage.info('该分录涉及的科目暂无对应底稿')
      return
    }
    if (wps.length === 1) {
      openWorkpaper(wps[0].id)
      return
    }
    relatedWps.value = wps
    relatedVisible.value = true
  } catch (e) {
    handleApiError(e, '查看关联底稿')
  }
}

function openWorkpaper(wpId: string) {
  relatedVisible.value = false
  router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId } })
}

/**
 * 来源底稿：source_ref='{wp_id}:{item_id}'；item_id 前缀编码（如 K9-3）作 ?sheet= 定位调整分录页签。
 * 只带 ?sheet=（编辑器读它切页签）；item_id 是核对表行键，编辑器没有按它定位的通路，
 * 别再塞编辑器不读的 ?highlight=（看着像能定位到行，其实原样被忽略）。
 */
function jumpToSourceWorkpaper(row: any) {
  const ref = String(row?.source_ref || '')
  const cut = ref.indexOf(':')
  const wpId = cut >= 0 ? ref.slice(0, cut) : ''
  if (!wpId || row.source_missing) {
    ElMessage.info(row.source_missing ? '来源底稿已删除；如这笔分录已无用，可直接删除' : '没有来源底稿信息')
    return
  }
  const sheet = ref.slice(cut + 1).match(/^[A-Z]\d+(?:-\d+)?/)?.[0] || ''
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: projectId.value, wpId },
    query: sheet ? { sheet } : {},
  })
}

function goMisstatements() {
  router.push({ name: 'Misstatements', params: { projectId: projectId.value } })
}

async function onRowAction(action: string, row: any) {
  switch (action) {
    case 'edit': entryDialogRef.value?.openEdit(row); break
    case 'submit': submitDialogRef.value?.open([row]); break
    case 'withdraw': await actions.withdraw(row); break
    case 'approve': await actions.approve([row]); break
    case 'reject':
    case 'revoke': openReason(action, [row]); break
    case 'delete': await actions.remove(row); break
    case 'convert': if (await actions.convert(row)) goMisstatements(); break
    case 'misstatement': goMisstatements(); break
    case 'source': jumpToSourceWorkpaper(row); break
    case 'collab': openCollabDialog(row); break
    case 'related': await showRelatedWorkpapers(row); break
    case 'impact': impactRow.value = row; impactVisible.value = true; break
    case 'trust': trustScorePanelRef.value?.open(`adj:${row.adjustment_type || 'aje'}|${row.line_items?.[0]?.standard_account_code || ''}`); break
    case 'history':
    case 'status-machine':
      selectedAdjId.value = row.entry_group_id
      await nextTick()
      if (action === 'history') tmDrawerRef.value?.open()
      else smPanelRef.value?.open()
      break
  }
}

/** 底稿编的分录如何汇聚到这里 */
function onGuideSyncFromWp() {
  ElMessage.info({
    message: '到各科目底稿的「调整分录」页签点「同步到调整分录」，分录会以草稿汇聚到这里（来源列显示底稿编码），再在这里提交复核。',
    duration: 6000,
    showClose: true,
  })
}

// ─── 协作接力（adjustment-collaboration-and-propagation）与待我协作收件箱 ─────
const collabDialogVisible = ref(false)
const collabRow = ref<any>(null)
const collabLineItems = computed<Array<{ standard_account_code?: string; account_name?: string; debit_amount: number; credit_amount: number }>>(() =>
  (collabRow.value?.line_items || []).map((li: any) => ({
    standard_account_code: li.standard_account_code,
    account_name: li.account_name,
    debit_amount: Number(li.debit_amount) || 0,
    credit_amount: Number(li.credit_amount) || 0,
  })),
)
function openCollabDialog(row: any): void {
  collabRow.value = row
  collabDialogVisible.value = true
}
async function onCollabUpdated(): Promise<void> {
  await Promise.all([fetchEntries(), refreshCollabInbox()])
}

const collabInbox = ref<Array<{ id: string; entry_group_id: string; status: string; round: number; note?: string | null }>>([])
const inboxDrawerVisible = ref(false)
const collabInboxCount = computed(() => collabInbox.value.length)

async function refreshCollabInbox() {
  try {
    collabInbox.value = await getCollaborationInbox(projectId.value)
  } catch { collabInbox.value = [] }
}

function entryNo(entryGroupId: string): string {
  return entries.value.find((e: any) => e.entry_group_id === entryGroupId)?.adjustment_no || entryGroupId.slice(0, 8)
}

function openCollabFromInbox(item: { entry_group_id: string }) {
  inboxDrawerVisible.value = false
  openCollabDialog(entries.value.find((e: any) => e.entry_group_id === item.entry_group_id)
    || { entry_group_id: item.entry_group_id, line_items: [] })
}

onBeforeUnmount(() => {
  _teardownSseBridge()
  if (focusTimer) clearTimeout(focusTimer)
})

// 初次加载
reloadAdjustmentContext()

// V3 Req 5.1：上下文（projectId/year）变化时自动重载
onContextChange(() => {
  reloadAdjustmentContext()
})
</script>

<style scoped>
.gt-adjustments { padding: var(--gt-space-5); }

/* 导出模板下拉: 当前项目版本高亮 */
:deep(.is-current-version) {
  font-weight: 600;
  color: var(--gt-color-primary);
  background: var(--gt-bg-primary-light);
}

/* 汇总面板 */
.gt-summary-panel { display: flex; gap: var(--gt-space-3); margin-bottom: var(--gt-space-5); flex-wrap: wrap; }
.gt-summary-card {
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  padding: var(--gt-space-4) var(--gt-space-5);
  box-shadow: var(--gt-shadow-sm); min-width: 140px; text-align: center;
  border: 1px solid rgba(75, 45, 119, 0.04);
}
.gt-summary-label { display: block; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); font-weight: 500; letter-spacing: 0.5px; }
.gt-summary-value { display: block; font-size: var(--gt-font-size-2xl); font-weight: 800; color: var(--gt-color-primary); margin: 4px 0; letter-spacing: -0.5px; }
.gt-summary-value--sm { font-size: var(--gt-font-size-lg) !important; }
.gt-summary-sub { display: block; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 2px; }
.gt-summary-card--impact { border-left: 3px solid var(--gt-color-success); }

/* 筛选行 */
.gt-adj-tabs-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.gt-adj-tabs-row :deep(.el-tabs) { flex: 1; margin-bottom: 0; }
.gt-adj-tabs-row :deep(.el-tabs__header) { margin-bottom: 0; }
:deep(.el-tabs__item.is-active) { font-weight: 600; }
.gt-adj-fs-btn { flex-shrink: 0; }
.gt-adj-status-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.gt-adj-status-hint { font-size: var(--gt-font-size-xs); color: var(--el-color-warning-dark-2); font-weight: 600; }

/* 批量操作 */
.gt-adj-batch-actions {
  display: flex; align-items: center; gap: var(--gt-space-3);
  margin-bottom: var(--gt-space-3);
  padding: var(--gt-space-2) var(--gt-space-4);
  background: var(--gt-color-primary-bg);
  border-radius: var(--gt-radius-md);
  border: 1px solid rgba(75, 45, 119, 0.08);
}
.gt-pagination { margin-top: 12px; display: flex; justify-content: flex-end; }

.gt-adj-impact-tip { margin: 0 0 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-adj-related-item { padding: 6px 8px; cursor: pointer; border-radius: var(--gt-radius-sm); }
.gt-adj-related-item:hover { background: var(--gt-color-primary-bg); }
.gt-adj-related-code { font-weight: 600; color: var(--gt-color-primary); margin-right: 6px; }

/* 待我协作 */
.gt-adj-inbox-item { padding: 10px 12px; margin-bottom: 8px; cursor: pointer; border: 1px solid var(--gt-color-border-light); border-radius: var(--gt-radius-md); }
.gt-adj-inbox-item:hover { background: var(--gt-color-primary-bg); }
.gt-adj-inbox-row { display: flex; align-items: center; gap: 8px; }
.gt-adj-inbox-no { font-weight: 600; }
.gt-adj-inbox-round, .gt-adj-inbox-note { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-adj-inbox-note { margin-top: 4px; }

/* 空态引导卡片 */
.gt-adj-empty-guide {
  background: linear-gradient(135deg, #faf8fc 0%, #f4f0fa 100%);
  border: 1px solid rgba(75, 45, 119, 0.08);
  border-radius: var(--gt-radius-lg, 12px);
  padding: 32px;
  margin-bottom: 20px;
}
.gt-adj-empty-guide__header { text-align: center; margin-bottom: 24px; }
.gt-adj-empty-guide__header h3 { font-size: var(--gt-font-size-xl); font-weight: 700; color: var(--gt-color-primary); margin: 0 0 8px; }
.gt-adj-empty-guide__header p { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); margin: 0; }
.gt-adj-empty-guide__cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
.gt-adj-guide-card {
  display: flex; flex-direction: column; align-items: center; text-align: center;
  padding: 20px 16px; background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md, 8px); border: 1px solid rgba(75, 45, 119, 0.06);
  cursor: pointer; transition: all 0.2s;
}
.gt-adj-guide-card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(75, 45, 119, 0.12); border-color: var(--gt-color-primary); }
.gt-adj-guide-card__icon { font-size: var(--gt-font-size-3xl); margin-bottom: 10px; }
.gt-adj-guide-card__title { font-size: var(--gt-font-size-base); font-weight: 600; color: var(--gt-color-text); margin-bottom: 6px; }
.gt-adj-guide-card__desc { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); line-height: 1.5; }
.gt-adj-paste-zone:focus { outline: none; }
</style>
