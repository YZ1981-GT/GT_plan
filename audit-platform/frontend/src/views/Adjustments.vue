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
        <GtToolbar :show-export="perms.export" :show-import="perms.import" export-label="导出汇总" @export="actions.exportSummary()" @import="openImport">
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
            <el-button size="small" type="primary" @click="openCreate()" :disabled="!perms.writable || !perms.create"
              :title="perms.writable ? (perms.create ? '' : '没有新建调整分录的权限') : '项目已归档，无法编辑'">+ 新建分录</el-button>
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
    <el-alert v-if="yearLoadFailed" type="error" :closable="false" show-icon style="margin-bottom: 8px">
      <template #title>
        <span>读取项目审计年度失败，无法加载调整数据。</span>
        <el-button size="small" text type="primary" @click="reloadAdjustmentContext">重试</el-button>
      </template>
    </el-alert>
    <el-alert v-else-if="yearResolved && year == null" type="warning" :closable="false" show-icon :title="MISSING_AUDIT_YEAR_MESSAGE" style="margin-bottom: 8px" />

    <section v-if="resourceFailures.length" class="gt-adj-resource-errors" aria-live="polite" aria-label="数据读取状态">
      <el-alert v-for="item in resourceFailures" :key="item.key" type="error" :closable="false" show-icon>
        <template #title>
          <div class="gt-adj-resource-error-row">
            <span>{{ item.label }}：{{ item.error }}</span>
            <span v-if="item.lastSuccessAt" class="gt-adj-resource-stale">
              当前保留上次成功数据（{{ lastSuccessText(item.lastSuccessAt) }}）
            </span>
            <el-button size="small" text type="primary" :loading="item.loading" @click="retryResource(item.key)">重试</el-button>
          </div>
        </template>
      </el-alert>
    </section>

    <!-- AI 内容 pending 顶部 banner（spec global-refinement-v3 Task 6.4） -->
    <AiContentPendingBanner :project-id="projectId" />

    <ClientBookingSuggestionBar :suggestions="bookingSuggestions" :can-edit="perms.writable && perms.edit" @review="openBookingSuggestion" />

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
        <span v-if="approvedImpact.workpaperReady" class="gt-summary-sub">另有 {{ approvedImpact.workpaperReady }} 笔底稿来源分录已批准、等待来源审定表发布</span>
        <span class="gt-summary-sub">
          手工分录批准后计入；底稿来源分录批准后允许来源审定表显式发布
          <el-button size="small" text type="primary" @click="router.push(`/projects/${projectId}/trial-balance`)">查看试算表 →</el-button>
        </span>
      </div>
      <el-button style="margin-left: auto; align-self: flex-start" type="primary" plain :icon="Reading" @click="showHandbook = true">使用手册</el-button>
    </div>

    <!-- 空态引导 -->
    <div v-if="entriesResource.status.value === 'success' && summaryResource.status.value === 'success' && entries.length === 0 && summary && (summary.aje_count + summary.rje_count === 0)" class="gt-adj-empty-guide">
      <div class="gt-adj-empty-guide__header">
        <h3>开始编制调整分录</h3>
        <p>分录先存为草稿并提交复核。手工分录批准后计入试算表；底稿来源分录批准后允许来源审定表显式发布，随后联动报表与附注。选择一种方式开始：</p>
      </div>
      <div class="gt-adj-empty-guide__cards">
        <button type="button" class="gt-adj-guide-card" @click="onGuideSyncFromWp">
          <span class="gt-adj-guide-card__icon">📥</span>
          <span class="gt-adj-guide-card__title">从底稿同步</span>
          <span class="gt-adj-guide-card__desc">把各科目底稿里编好的调整分录汇聚到这里统一复核</span>
        </button>
        <button type="button" class="gt-adj-guide-card" @click="openCreate()">
          <span class="gt-adj-guide-card__icon">✏️</span>
          <span class="gt-adj-guide-card__title">手工新建</span>
          <span class="gt-adj-guide-card__desc">直接录入，支持常用模板（坏账 / 折旧 / 重分类等）和从 Excel 粘贴</span>
        </button>
        <button type="button" class="gt-adj-guide-card" @click="openImport">
          <span class="gt-adj-guide-card__icon">📊</span>
          <span class="gt-adj-guide-card__title">Excel 导入</span>
          <span class="gt-adj-guide-card__desc">下载国企版 / 上市版模板填写，预检通过后批量导入</span>
        </button>
        <button type="button" class="gt-adj-guide-card" @click="showHandbook = true">
          <span class="gt-adj-guide-card__icon">📖</span>
          <span class="gt-adj-guide-card__title">查看使用手册</span>
          <span class="gt-adj-guide-card__desc">录入规则、复核流程、通知与联动</span>
        </button>
      </div>
    </div>
    <div v-else-if="summaryResource.status.value === 'success' && !summary" class="gt-adj-handbook-fallback">
      <el-button type="primary" plain :icon="Reading" @click="showHandbook = true">使用手册</el-button>
    </div>

    <!-- 筛选 -->
    <div class="gt-adj-tabs-row">
      <el-tabs v-model="activeTab" class="gt-adj-tabs" @tab-change="adjPage = 1">
        <el-tab-pane label="全部" name="all" />
        <el-tab-pane label="审计调整" name="aje" />
        <el-tab-pane label="重分类" name="rje" />
      </el-tabs>
      <el-input v-model="searchText" clearable size="small" placeholder="搜索编号、摘要、科目" style="width: 210px"
        @keyup.enter="applyServerFilters" @clear="applyServerFilters" />
      <el-segmented v-model="originFilter" :options="ORIGIN_FILTER_OPTIONS" size="small" class="gt-adj-origin-filter" @change="adjPage = 1">
        <template #default="{ item }">
          <el-tooltip :content="item.tip" placement="top" :disabled="!item.tip" :show-after="200">
            <span>{{ item.label }}</span>
          </el-tooltip>
        </template>
      </el-segmented>
      <el-select v-model="phaseFilter" size="small" style="width: 112px" @change="adjPage = 1">
        <el-option label="全部阶段" value="all" />
        <el-option label="预审提出" value="preliminary" />
        <el-option label="年审提出" value="final" />
      </el-select>
      <el-select v-model="bookingFilter" size="small" style="width: 168px" @change="adjPage = 1">
        <el-option label="全部最终处理" value="all" />
        <el-option label="纳入工作试算表" value="included" />
        <el-option label="客户已入账" value="effective" />
        <el-option label="已入账但未生效" value="inactive" />
        <el-option label="不予更正" value="unadjusted" />
        <el-option label="待形成处理" value="pending" />
      </el-select>
      <el-select v-model="sortKey" size="small" style="width: 118px" @change="applyServerFilters">
        <el-option label="编号排序" value="adjustment_no" />
        <el-option label="金额排序" value="amount" />
        <el-option label="创建时间" value="created_at" />
        <el-option label="复核状态" value="review_status" />
      </el-select>
      <el-button size="small" plain @click="toggleSortOrder">{{ sortOrder === 'asc' ? '升序 ↑' : '降序 ↓' }}</el-button>
      <el-button size="small" type="success" plain @click="onGuideSyncFromWp" title="底稿里编的调整分录如何汇聚到这里">📥 从底稿同步</el-button>
      <el-select v-if="entries.length > 0" v-model="creatorFilter" placeholder="全部编制人" clearable size="small" style="width: 140px" @change="adjPage = 1">
        <el-option v-for="person in creatorOptions" :key="person.id" :label="person.name" :value="person.id" />
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
      <span v-if="myReviewTasks.length" class="gt-adj-status-hint">有 {{ myReviewTasks.length }} 笔分配给你复核</span>
      <span v-else-if="statusCounts.pending_review && perms.review" class="gt-adj-status-team-hint">团队待复核 {{ statusCounts.pending_review }} 笔</span>
    </div>

    <!-- 科目过滤提示（从试算表跳转时显示） -->
    <el-alert v-if="filterAccount" type="info" show-icon :closable="true" style="margin-bottom: 12px" @close="filterAccount = ''">
      <template #title>
        <span>当前仅显示科目 <strong>{{ filterAccount }}</strong> 的相关分录</span>
        <el-button size="small" text type="primary" style="margin-left: 8px" @click="filterAccount = ''">查看全部</el-button>
      </template>
    </el-alert>
    <el-alert v-if="entriesResource.status.value === 'success' && entries.length > 0 && filteredEntries.length === 0" type="info" show-icon :closable="false" style="margin-bottom: 12px"
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
      :accounts-ready="accountsReady" :can-edit="perms.writable && (perms.create || perms.edit)" @saved="onEntrySaved" />
    <AdjustmentSubmitReviewDialog ref="submitDialogRef" :project-id="projectId" @done="reloadLists" />
    <AdjustmentReasonDialog ref="reasonDialogRef" />
    <AdjustmentImportDialog ref="importDialogRef" :project-id="projectId" :year="year" :template-type="currentTemplateType"
      :can-edit="perms.writable && perms.import" @download-template="onDownloadTemplate"
      @imported="reloadLists" @submit-review="onSubmitImported" />

    <el-dialog v-model="impactVisible" :title="`影响范围 · ${impactRow?.adjustment_no || ''}`" width="640px" append-to-body>
      <p class="gt-adj-impact-tip">按本分录的科目与金额测算对报表行、底稿的影响（批准后才计入；草稿只是预览）。</p>
      <AdjustmentImpactPreview v-if="impactVisible && impactRow" :project-id="projectId" :year="year"
        :adjustment-type="String(impactRow.adjustment_type || 'aje').toLowerCase() === 'rje' ? 'rje' : 'aje'"
        :line-items="impactRow.line_items || []" />
    </el-dialog>
    <el-dialog v-model="relatedVisible" title="关联底稿" width="480px" append-to-body>
      <button v-for="w in relatedWps" :key="w.id" type="button" class="gt-adj-related-item" @click="openWorkpaper(w.id)">
        <span class="gt-adj-related-code">{{ w.wp_code }}</span> {{ w.wp_name }}
      </button>
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
      :can-edit="perms.writable && perms.edit"
      @updated="onCollabUpdated"
    />

    <!-- 待我协作 收件箱 -->
    <el-drawer v-model="inboxDrawerVisible" title="待我协作的调整分录" size="420px" append-to-body>
      <el-alert v-if="collabResource.status.value === 'error'" type="error" :closable="false" show-icon :title="collabResource.error.value">
        <template #default>
          <el-button size="small" text type="primary" @click="refreshCollabInbox">重试</el-button>
        </template>
      </el-alert>
      <div v-else-if="collabResource.status.value === 'loading'" class="gt-adj-inbox-loading">正在加载协作事项…</div>
      <el-empty v-else-if="collabResource.status.value === 'success' && collabInbox.length === 0" description="暂无待我协作的分录组" :image-size="80" />
      <div v-else-if="collabInbox.length" class="gt-adj-inbox-list">
        <button v-for="it in collabInbox" :key="it.id" type="button" class="gt-adj-inbox-item" @click="openCollabFromInbox(it)">
          <div class="gt-adj-inbox-row">
            <span class="gt-adj-inbox-no">{{ entryNo(it.entry_group_id) }}</span>
            <el-tag size="small" :type="it.status === 'contributed' ? 'primary' : (it.status === 'acknowledged' ? 'warning' : 'info')">
              {{ COLLAB_STATUS_LABELS[it.status] || it.status }}
            </el-tag>
            <span class="gt-adj-inbox-round">第 {{ it.round }} 轮</span>
          </div>
          <div v-if="it.note" class="gt-adj-inbox-note">📝 {{ it.note }}</div>
        </button>
      </div>
    </el-drawer>

    <ClientBookingDialog ref="bookingDialogRef" :project-id="projectId" :year="year" @updated="reloadAdjustmentContext" />
    <AdjustmentTreatmentDialog ref="treatmentDialogRef" :project-id="projectId" :year="year" @updated="reloadAdjustmentContext" />
    <AdjustmentEvidenceDialog ref="evidenceDialogRef" :project-id="projectId" :year="year" />
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
  getAccountDropdown, getAdjustmentSummary, getCollaborationInbox, listAdjustmentBookingSuggestions,
  listAdjustmentReviewTasks, listAdjustments,
  type AccountOption, type AdjustmentBookingSuggestion, type AdjustmentListPage,
  type AdjustmentReviewTask, type AdjustmentSummary,
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
import { ADJUSTMENT_SHEET_ALIAS } from '@/utils/normalizeSheetName'
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
import ClientBookingDialog from '@/components/adjustment/ClientBookingDialog.vue'
import AdjustmentTreatmentDialog from '@/components/adjustment/AdjustmentTreatmentDialog.vue'
import AdjustmentEvidenceDialog from '@/components/adjustment/AdjustmentEvidenceDialog.vue'
import ClientBookingSuggestionBar from '@/components/adjustment/ClientBookingSuggestionBar.vue'
import { resolveSuggestionEntry } from '@/components/adjustment/clientBookingVoucher'
import AdjustmentImpactPreview from '@/components/adjustment/AdjustmentImpactPreview.vue'
import { parsePastedLines, type EditableLine, type EntrySavedPayload } from '@/components/adjustment/adjustmentLineRules'
import {
  skipMessage, splitEligible, useAdjustmentHallActions, withDescriptions,
  type HallAction, type HallEntry, type HallPerms,
} from '@/composables/useAdjustmentHallActions'
import { useAdjustmentHallResource } from '@/composables/useAdjustmentHallResource'
import { buildAdjustmentRouteTarget, parseAdjustmentRouteTarget } from '@/utils/adjustmentRouteTarget'

const showHandbook = ref(false)
const route = useRoute()
const router = useRouter()
const { isArchived, onContextChange } = useAuditContext()
const projectStore = useProjectStore()

const projectId = computed(() => projectStore.projectId)
const selectedProjectId = ref(projectStore.projectId)
const projectOptions = computed(() => projectStore.projectOptions)
const selectedYear = ref<number | null>(projectStore.year)

// 权限：项目可写（未归档）× 项目内权限（编辑 / 复核调整分录）
const { projectCan } = useProjectRole(computed(() => projectId.value || ''))
const perms = computed<HallPerms>(() => ({
  writable: !isArchived.value,
  create: projectCan('adjustment:create'),
  edit: projectCan('adjustment:edit'),
  submit: projectCan('adjustment:submit'),
  review: projectCan('adjustment:review'),
  approve: projectCan('adjustment:approve'),
  delete: projectCan('adjustment:delete'),
  import: projectCan('adjustment:import'),
  export: projectCan('adjustment:export'),
}))

// ─── useStaleRefresh：试算表变更 / 底稿推送 / 复核状态变化后自动刷新 ───────────
useStaleRefresh(projectId, {
  events: ['trial-balance:updated', 'adjustment:sync-arrived', 'adjustment:review-changed', 'adjustment:client-booking-changed', 'adjustment:treatment-changed'],
  mode: 'auto',
  onRefresh: () => { void reloadLists() },
})

// ─── SSE → mitt 桥接：broadcast_raw 事件经 SSE 到达，转发到 mitt 供 useStaleRefresh 消费 ──
const _sseSubs: ProjectEventSubscription[] = []
const SSE_BRIDGE_EVENTS = ['adjustment:review-changed', 'adjustment:sync-arrived', 'adjustment:client-booking-changed', 'adjustment:treatment-changed'] as const
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
  router.push(buildAdjustmentRouteTarget(pid, null, { year: routeYear.value }))
}
function onYearChange(y: number) {
  selectedYear.value = y
  projectStore.changeYear(y)
  router.push(buildAdjustmentRouteTarget(projectId.value, null, { year: y }))
}

const parsedRouteTarget = computed(() => parseAdjustmentRouteTarget(route.query as Record<string, unknown>))
const routeYear = computed(() => parsedRouteTarget.value.year)
const year = computed<number | null>(() => routeYear.value ?? projectStore.year ?? null)
/** 项目 store 已解析年度后才显示“未设置”，读取失败与业务空值分开。 */
const yearResolved = computed(() => projectStore.yearStatus !== 'loading')
const yearLoadFailed = computed(() => projectStore.yearStatus === 'failed')

// Spec A R1：错报阈值变化时，已转错报的分录标「建议重新评估」
const { misstatements: missStaleSummary } = useStaleSummaryFull(computed(() => projectId.value || ''), year)
const missStaleIdSet = computed(() => new Set<string>(missStaleSummary.value.items.map((it: any) => it.id)))

// ─── 数据：五类读取各自保留状态、错误、最后成功时间和请求代际 ───────────────
type TemplateType = 'soe' | 'listed' | ''
type CollabInboxItem = { id: string; entry_group_id: string; status: string; round: number; note?: string | null }

const contextEpoch = ref(0)
const resourceContextKey = () => `${contextEpoch.value}:${projectId.value}:${year.value ?? 'none'}`
const entriesResource = useAdjustmentHallResource<AdjustmentListPage>(() => ({
  items: [], total: 0, page: 1, page_size: 50, has_more: false, status_counts: {},
}), resourceContextKey)
const summaryResource = useAdjustmentHallResource<AdjustmentSummary | null>(() => null, resourceContextKey)
const accountsResource = useAdjustmentHallResource(() => [] as AccountOption[], resourceContextKey)
const templateResource = useAdjustmentHallResource<TemplateType>(() => '', resourceContextKey)
const collabResource = useAdjustmentHallResource(() => [] as CollabInboxItem[], resourceContextKey)
const reviewTaskResource = useAdjustmentHallResource(() => [] as AdjustmentReviewTask[], resourceContextKey)
const bookingSuggestionResource = useAdjustmentHallResource(() => [] as AdjustmentBookingSuggestion[], resourceContextKey)

const entries = computed<any[]>(() => entriesResource.data.value.items)
const summary = summaryResource.data
const accountOptions = accountsResource.data
const currentTemplateType = templateResource.data
const collabInbox = collabResource.data
const myReviewTasks = reviewTaskResource.data
const bookingSuggestions = bookingSuggestionResource.data
const loading = computed(() => entriesResource.status.value === 'loading')
const accountsReady = computed(() => accountsResource.status.value === 'success')
const selectedRows = ref<any[]>([])

const resourceFailures = computed(() => [
  { key: 'entries', label: '分录列表', resource: entriesResource },
  { key: 'summary', label: '汇总数据', resource: summaryResource },
  { key: 'accounts', label: '科目数据', resource: accountsResource },
  { key: 'template', label: '模板类型', resource: templateResource },
  { key: 'collaboration', label: '协作事项', resource: collabResource },
  { key: 'reviewTasks', label: '我的复核任务', resource: reviewTaskResource },
  { key: 'bookingSuggestions', label: '客户已入账建议', resource: bookingSuggestionResource },
].filter(({ resource }) => resource.status.value === 'error').map(({ key, label, resource }) => ({
  key,
  label,
  error: resource.error.value,
  lastSuccessAt: resource.lastSuccessAt.value,
  loading: resource.status.value === 'loading',
})))

function lastSuccessText(value: number | null): string {
  if (value == null) return ''
  return new Date(value).toLocaleTimeString('zh-CN', { hour12: false })
}

// ─── 筛选（客户端：已取全部分录）与状态计数 ─────────────────────────────────
const activeTab = ref('all')
const ORIGIN_FILTER_OPTIONS = [
  { label: '全部来源', value: 'all', tip: '显示手工录入与底稿汇聚的全部调整分录' },
  { label: '手工录入', value: 'manual', tip: '在本模块直接新建 / 导入的调整分录' },
  { label: '底稿汇聚', value: 'workpaper', tip: '从各科目底稿点「同步到调整分录」汇聚而来的分录' },
]
const originFilter = ref('all')
const phaseFilter = ref('all')
const bookingFilter = ref('all')
const searchText = ref('')
const sortKey = ref<'adjustment_no' | 'amount' | 'created_at' | 'review_status'>('adjustment_no')
const sortOrder = ref<'asc' | 'desc'>('asc')
const STATUS_FILTERS = [
  { value: 'all', label: '全部' },
  ...Object.values(ADJUSTMENT_STATUS).map((s) => ({ value: s, label: ADJUSTMENT_STATUS_LABELS[s].label })),
]
const statusFilter = ref('all')
const creatorFilter = ref('')
const collabOnly = ref(false)
const filterAccount = ref(parsedRouteTarget.value.account)

const creatorOptions = computed<Array<{ id: string; name: string }>>(() => {
  const byId = new Map<string, string>()
  for (const entry of entries.value) {
    if (entry.created_by && entry.creator_name) byId.set(entry.created_by, entry.creator_name)
  }
  return [...byId].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
})
/** 服务端已完成类型、状态、来源、阶段、处理、科目和人员过滤；协作筛选仍只作用于当前页。 */
const filteredEntries = computed(() => collabOnly.value
  ? entries.value.filter((entry: any) => entry.has_active_collaboration)
  : entries.value)
const serverTotal = computed(() => entriesResource.data.value.total)
const serverStatusCounts = computed(() => entriesResource.data.value.status_counts || {})
const statusCounts = computed(() => ({ all: serverTotal.value, ...serverStatusCounts.value }))

const adjPage = ref(1)
const adjPageSize = 50
const adjTotal = computed(() => serverTotal.value)
const pagedEntries = computed(() => filteredEntries.value)
watch(adjTotal, (n) => {
  const max = Math.max(1, Math.ceil(n / adjPageSize))
  if (adjPage.value > max) adjPage.value = max
})

function applyServerFilters(): void {
  if (adjPage.value !== 1) adjPage.value = 1
  else void fetchEntries()
}
function toggleSortOrder(): void {
  sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
}
watch(
  [activeTab, originFilter, phaseFilter, bookingFilter, statusFilter, creatorFilter, filterAccount, sortKey, sortOrder],
  () => { applyServerFilters() },
)
let syncingServerPage = false
watch(adjPage, () => {
  if (syncingServerPage) { syncingServerPage = false; return }
  void fetchEntries()
})

/** 已批准（计入试算表）的笔数与科目数 —— 草稿 / 待复核 / 已驳回不进审定数 */
const approvedImpact = computed(() => {
  const approved = entries.value.filter((e: any) => e.review_status === ADJUSTMENT_STATUS.APPROVED)
  const applied = approved.filter((e: any) => e.origin !== 'workpaper'
    && (e.treatment?.status || 'include_in_working_tb') === 'include_in_working_tb')
  const codes = new Set<string>()
  for (const e of applied) for (const li of e.line_items || []) if (li.standard_account_code) codes.add(li.standard_account_code)
  return {
    entries: applied.length,
    accounts: codes.size,
    workpaperReady: approved.length - applied.length,
  }
})

// ─── 取数 ────────────────────────────────────────────────────────────────────
function resetReadResources(): void {
  entriesResource.reset()
  summaryResource.reset()
  accountsResource.reset()
  templateResource.reset()
  collabResource.reset()
  reviewTaskResource.reset()
  bookingSuggestionResource.reset()
  selectedRows.value = []
}

async function fetchProjectMeta(): Promise<boolean> {
  const pid = projectId.value
  if (!pid) return false
  return templateResource.load(async () => {
    const data = await api.get(P.projects.detail(pid))
    const tt = data?.template_type || data?.basic_info?.template_type || ''
    return tt === 'soe' || tt === 'listed' ? tt : ''
  }, '读取项目模板类型失败，请重试')
}

async function fetchEntries(): Promise<boolean> {
  const pid = projectId.value
  const requestedYear = year.value
  if (!pid || requestedYear == null) return false
  const treatmentStatus = {
    included: 'include_in_working_tb',
    effective: 'client_booked',
    inactive: 'client_booked_inactive',
    unadjusted: 'unadjusted_misstatement',
    pending: 'pending',
  }[bookingFilter.value]
  const ok = await entriesResource.load(
    () => listAdjustments(pid, requestedYear, {
      page: adjPage.value,
      page_size: adjPageSize,
      adjustment_type: activeTab.value === 'all' ? undefined : activeTab.value,
      review_status: statusFilter.value === 'all' ? undefined : statusFilter.value,
      origin: originFilter.value === 'all' ? undefined : originFilter.value,
      audit_phase: phaseFilter.value === 'all' ? undefined : phaseFilter.value,
      treatment_status: treatmentStatus,
      focus_entry_group_id: parsedRouteTarget.value.focus || undefined,
      account_code: filterAccount.value || undefined,
      created_by: creatorFilter.value || undefined,
      search: searchText.value.trim() || undefined,
      sort_by: sortKey.value,
      sort_order: sortOrder.value,
    }),
    '读取分录列表失败，请重试',
  )
  if (ok && entriesResource.data.value.page !== adjPage.value) {
    syncingServerPage = true
    adjPage.value = entriesResource.data.value.page
  }
  return ok
}

async function fetchSummary(): Promise<boolean> {
  const pid = projectId.value
  const requestedYear = year.value
  if (!pid || requestedYear == null) return false
  return summaryResource.load(
    () => getAdjustmentSummary(pid, requestedYear),
    '读取汇总数据失败，请重试',
  )
}

async function fetchAccountOptions(): Promise<boolean> {
  const pid = projectId.value
  const requestedYear = year.value
  if (!pid || requestedYear == null) return false
  return accountsResource.load(
    () => getAccountDropdown(pid, undefined, requestedYear),
    '读取科目数据失败，请重试',
  )
}

async function refreshCollabInbox(): Promise<boolean> {
  const pid = projectId.value
  if (!pid) return false
  return collabResource.load(
    () => getCollaborationInbox(pid),
    '读取协作事项失败，请重试',
  )
}

async function refreshReviewTasks(): Promise<boolean> {
  const pid = projectId.value
  const requestedYear = year.value
  if (!pid || requestedYear == null) return false
  return reviewTaskResource.load(
    () => listAdjustmentReviewTasks(pid, requestedYear, true),
    '读取我的复核任务失败，请重试',
  )
}

async function refreshBookingSuggestions(): Promise<boolean> {
  const pid = projectId.value
  const requestedYear = year.value
  if (!pid || requestedYear == null) return false
  return bookingSuggestionResource.load(
    () => listAdjustmentBookingSuggestions(pid, requestedYear),
    '读取客户已入账建议失败，请重试',
  )
}

function retryResource(key: string): void {
  if (key === 'entries') void fetchEntries().then((ok) => { if (ok) void applyRouteTargets() })
  else if (key === 'summary') void fetchSummary()
  else if (key === 'accounts') void fetchAccountOptions()
  else if (key === 'template') void fetchProjectMeta()
  else if (key === 'collaboration') void refreshCollabInbox()
  else if (key === 'reviewTasks') void refreshReviewTasks()
  else if (key === 'bookingSuggestions') void refreshBookingSuggestions()
}

async function reloadLists() {
  await Promise.all([fetchEntries(), fetchSummary(), refreshCollabInbox(), refreshReviewTasks(), refreshBookingSuggestions()])
}

async function reloadAdjustmentContext() {
  const generation = ++contextEpoch.value
  resetReadResources()
  await projectStore.syncFromRoute(route)
  if (generation !== contextEpoch.value) return
  selectedProjectId.value = projectId.value
  selectedYear.value = year.value
  filterAccount.value = parsedRouteTarget.value.account
  await Promise.all([fetchEntries(), fetchSummary(), fetchAccountOptions(), fetchProjectMeta(), refreshCollabInbox(), refreshReviewTasks(), refreshBookingSuggestions()])
  if (generation !== contextEpoch.value) return
  if (!projectOptions.value.length) void projectStore.loadProjectOptions()
  void applyRouteTargets()
}

// ─── 深链 ────────────────────────────────────────────────────────────────────
const focusId = ref('')
let focusTimer: ReturnType<typeof setTimeout> | null = null
let appliedRouteSignature = ''

function findEntryTarget(target: string): any | null {
  return entries.value.find((entry: any) => entry.entry_group_id === target
    || entry.adjustment_no === target
    || (entry.line_items || []).some((line: any) => line.id === target)) || null
}

async function applyRouteTargets() {
  if (year.value == null || entriesResource.status.value !== 'success') return
  const target = parsedRouteTarget.value
  const signature = JSON.stringify(target)
  if (signature === appliedRouteSignature) return
  appliedRouteSignature = signature

  if (target.group) {
    openCollabDialog(findEntryTarget(target.group) || { entry_group_id: target.group, line_items: [] })
  }
  if (target.impact) {
    const row = findEntryTarget(target.impact)
    if (row) {
      impactRow.value = row
      impactVisible.value = true
    } else {
      ElMessage.info('没有找到要查看影响的分录（可能已删除、不在当前审计年度或不在你的可见范围）')
    }
  }
  if (target.focus) await focusEntry(target.focus, target.status)
}

async function focusEntry(target: string, _status: string): Promise<boolean> {
  const row = findEntryTarget(target)
  if (!row) {
    ElMessage.info('没有找到要定位的分录（可能已删除、不在当前审计年度或不在你的可见范围）')
    return false
  }
  focusId.value = row.entry_group_id
  await nextTick()
  await hallTableRef.value?.reveal(row.entry_group_id)
  if (focusTimer) clearTimeout(focusTimer)
  focusTimer = setTimeout(() => { focusId.value = '' }, 8000)
  return true
}

// ─── 操作 ────────────────────────────────────────────────────────────────────
const hallTableRef = ref<InstanceType<typeof AdjustmentHallTable> | null>(null)
const entryDialogRef = ref<InstanceType<typeof AdjustmentEntryDialog> | null>(null)
const submitDialogRef = ref<InstanceType<typeof AdjustmentSubmitReviewDialog> | null>(null)
const reasonDialogRef = ref<InstanceType<typeof AdjustmentReasonDialog> | null>(null)
const importDialogRef = ref<InstanceType<typeof AdjustmentImportDialog> | null>(null)
const bookingDialogRef = ref<InstanceType<typeof ClientBookingDialog> | null>(null)
const treatmentDialogRef = ref<InstanceType<typeof AdjustmentTreatmentDialog> | null>(null)
const evidenceDialogRef = ref<InstanceType<typeof AdjustmentEvidenceDialog> | null>(null)
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
 * 跳转到来源底稿的调整分录页（source_ref='{wp_id}:{item_id}'，前缀即 wp_id）。
 * ?sheet=@adjustment：该底稿名称含「调整分录」的那张表（item_id 前缀落不到它：D1-entry-rows → 审定表、L1-adj-AJE → 程序表）；
 * ?highlight=source_ref：来源页签认领分录组并切到对应类型（spec wp-deeplink-locate-residual-closure 需求 1，
 * 守卫 adjustmentEntryGroupWiring.spec.ts）。来源底稿已删除时只提示、不跳转。
 */
function jumpToSourceWorkpaper(row: any) {
  const ref = String(row?.source_ref || '')
  const wpId = ref.indexOf(':') >= 0 ? ref.slice(0, ref.indexOf(':')) : ''
  if (!wpId || row?.source_missing) {
    ElMessage.info(row?.source_missing ? '来源底稿已删除；如这笔分录已无用，可直接删除' : '没有来源底稿信息')
    return
  }
  router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId }, query: { sheet: ADJUSTMENT_SHEET_ALIAS, highlight: ref } })
}

function goMisstatements() {
  router.push({ name: 'Misstatements', params: { projectId: projectId.value } })
}

async function openBookingSuggestion(suggestion: AdjustmentBookingSuggestion): Promise<void> {
  const pid = projectId.value
  const requestedYear = year.value
  if (!pid || requestedYear == null) return
  // 不在当前页也能打开（R5.3）：按 focus 取本组所在页，每页 1 条即本组
  const target = await resolveSuggestionEntry(suggestion.entry_group_id, entries.value as HallEntry[],
    (groupId) => listAdjustments(pid, requestedYear, { page_size: 1, focus_entry_group_id: groupId }))
  if (pid !== projectId.value || requestedYear !== year.value || target === undefined) return
  if (target === null) { ElMessage.info('分录已删除或不在本年度'); return }
  bookingDialogRef.value?.open(target, suggestion.candidates, false)
}

function openClientBooking(row: HallEntry, revoke = false): void {
  const suggestion = bookingSuggestions.value.find((item) => item.entry_group_id === row.entry_group_id)
  bookingDialogRef.value?.open(row, suggestion?.candidates || [], revoke)
}

async function onRowAction(action: string, row: any) {
  switch (action) {
    case 'client-booking': openClientBooking(row); break
    case 'client-booking-revoke': openClientBooking(row, true); break
    case 'treatment': await treatmentDialogRef.value?.open(row); break
    case 'evidence': await evidenceDialogRef.value?.open(row); break
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

const inboxDrawerVisible = ref(false)
const collabInboxCount = computed(() => collabInbox.value.length)

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
.gt-adj-tabs-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.gt-adj-tabs-row :deep(.el-tabs) { flex: 1; margin-bottom: 0; }
.gt-adj-tabs-row :deep(.el-tabs__header) { margin-bottom: 0; }
:deep(.el-tabs__item.is-active) { font-weight: 600; }
.gt-adj-fs-btn { flex-shrink: 0; }
.gt-adj-status-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.gt-adj-status-hint { font-size: var(--gt-font-size-xs); color: var(--el-color-warning-dark-2); font-weight: 600; }
.gt-adj-status-team-hint { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }

/* 批量操作 */
.gt-adj-batch-actions {
  display: flex; align-items: center; gap: var(--gt-space-3); flex-wrap: wrap;
  margin-bottom: var(--gt-space-3);
  padding: var(--gt-space-2) var(--gt-space-4);
  background: var(--gt-color-primary-bg);
  border-radius: var(--gt-radius-md);
  border: 1px solid rgba(75, 45, 119, 0.08);
}
.gt-pagination { margin-top: 12px; display: flex; justify-content: flex-end; }

.gt-adj-impact-tip { margin: 0 0 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-adj-related-item { display: block; width: 100%; padding: 6px 8px; cursor: pointer; border: 0; background: transparent; text-align: left; font: inherit; border-radius: var(--gt-radius-sm); }
.gt-adj-related-item:hover { background: var(--gt-color-primary-bg); }
.gt-adj-related-item:focus-visible { outline: 2px solid var(--gt-color-primary); outline-offset: 1px; }
.gt-adj-related-code { font-weight: 600; color: var(--gt-color-primary); margin-right: 6px; }

/* 待我协作 */
.gt-adj-inbox-item { display: block; width: 100%; padding: 10px 12px; margin-bottom: 8px; cursor: pointer; border: 1px solid var(--gt-color-border-light); background: transparent; text-align: left; font: inherit; border-radius: var(--gt-radius-md); }
.gt-adj-inbox-item:hover { background: var(--gt-color-primary-bg); }
.gt-adj-inbox-item:focus-visible { outline: 2px solid var(--gt-color-primary); outline-offset: 1px; }
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
  cursor: pointer; transition: all 0.2s; font: inherit; color: inherit;
}
.gt-adj-guide-card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(75, 45, 119, 0.12); border-color: var(--gt-color-primary); }
.gt-adj-guide-card:focus-visible { outline: 2px solid var(--gt-color-primary); outline-offset: 2px; }
.gt-adj-guide-card__icon { font-size: var(--gt-font-size-3xl); margin-bottom: 10px; }
.gt-adj-guide-card__title { font-size: var(--gt-font-size-base); font-weight: 600; color: var(--gt-color-text); margin-bottom: 6px; }
.gt-adj-guide-card__desc { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); line-height: 1.5; }
.gt-adj-resource-errors { display: grid; gap: 6px; margin-bottom: 8px; }
.gt-adj-resource-error-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gt-adj-resource-stale { color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs); }
.gt-adj-inbox-loading { padding: 16px; color: var(--gt-color-text-tertiary); text-align: center; }
.gt-adj-paste-zone:focus-visible { outline: 2px solid var(--gt-color-primary); outline-offset: 2px; }
</style>
