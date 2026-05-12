<template>
  <div class="review-workbench">
    <GtPageHeader title="复核工作台" :show-back="false">
      <template #actions>
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="workbench">三栏视图</el-radio-button>
          <el-radio-button value="batch">批量模式</el-radio-button>
        </el-radio-group>
      </template>
    </GtPageHeader>

    <!-- 筛选条 -->
    <div class="filter-bar">
      <el-select
        v-if="isGlobal"
        v-model="filterProjectId"
        placeholder="项目"
        clearable
        size="small"
        style="width: 180px"
      >
        <el-option
          v-for="p in projectOptions"
          :key="p.id"
          :label="p.name"
          :value="p.id"
        />
      </el-select>
      <el-select
        v-model="filterCycle"
        placeholder="审计循环"
        clearable
        size="small"
        style="width: 140px"
      >
        <el-option
          v-for="c in cycleOptions"
          :key="c"
          :label="c"
          :value="c"
        />
      </el-select>
      <el-select
        v-model="filterResubmit"
        placeholder="是否退回重提"
        clearable
        size="small"
        style="width: 140px"
      >
        <el-option label="首次提交" value="first" />
        <el-option label="退回重提" value="resubmit" />
      </el-select>
      <el-select
        v-model="filterAssignee"
        placeholder="提交人"
        clearable
        size="small"
        style="width: 160px"
      >
        <el-option
          v-for="a in assigneeOptions"
          :key="a"
          :label="a"
          :value="a"
        />
      </el-select>
      <el-input
        v-model="searchKw"
        placeholder="搜索底稿编号/名称"
        clearable
        size="small"
        style="width: 220px; margin-left: auto"
      />
    </div>

    <!-- ── 批量模式：表格视图 ── -->
    <div v-if="viewMode === 'batch'" class="batch-view">
      <div class="batch-actions">
        <el-button
          :disabled="!selectedIds.length"
          type="success"
          @click="handleBatchApprove"
        >
          ✅ 批量通过 ({{ selectedIds.length }})
        </el-button>
        <el-button
          :disabled="!selectedIds.length"
          type="warning"
          @click="showRejectDialog = true"
        >
          ↩️ 批量退回 ({{ selectedIds.length }})
        </el-button>
      </div>

      <el-table
        :data="filteredItems"
        v-loading="loading"
        @selection-change="onSelectionChange"
        stripe
        style="width: 100%"
        row-key="id"
      >
        <el-table-column type="selection" width="45" />
        <el-table-column label="项目" prop="project_name" width="160" v-if="isGlobal" />
        <el-table-column label="底稿编号" prop="wp_code" width="120" sortable />
        <el-table-column label="底稿名称" prop="wp_name" min-width="200" />
        <el-table-column label="审计循环" prop="audit_cycle" width="100" />
        <el-table-column label="版本" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="isResubmitRow(row) ? 'warning' : 'info'">
              v{{ row.file_version }}{{ isResubmitRow(row) ? ' · 退回重提' : '' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="复核状态" width="120">
          <template #default="{ row }">
            <el-tag
              :type="row.review_status === 'pending_level1' ? 'warning' : 'danger'"
              size="small"
            >
              {{ reviewStatusLabel(row.review_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提交人" prop="assigned_to" width="140" />
        <el-table-column label="提交时间" width="160">
          <template #default="{ row }">
            {{ row.submitted_at ? new Date(row.submitted_at).toLocaleString('zh-CN') : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openEditor(row)">查看</el-button>
            <el-button size="small" type="success" link @click="handleSingleApprove(row)">通过</el-button>
            <el-button size="small" type="warning" link @click="handleSingleReject(row)">退回</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="gt-pagination" v-if="total > pageSize">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadData"
        />
      </div>
    </div>

    <!-- ── 三栏工作台模式 ── -->
    <div v-else class="workbench-body">
      <!-- 左栏：队列 -->
      <div class="queue-panel">
        <div class="panel-header">
          <span>待复核队列</span>
          <el-badge :value="filteredItems.length" type="warning" />
        </div>
        <div class="queue-list" v-loading="loading">
          <div
            v-for="item in filteredItems"
            :key="item.id"
            class="queue-item"
            :class="{ active: selectedWpId === item.id }"
            @click="selectItem(item)"
          >
            <div class="queue-item-header">
              <span class="wp-code">{{ item.wp_code }}</span>
              <el-tag size="small" :type="isResubmitRow(item) ? 'warning' : 'info'">
                {{ isResubmitRow(item) ? '退回重提' : '首次提交' }}
              </el-tag>
            </div>
            <div class="wp-name">{{ item.wp_name }}</div>
            <div class="wp-meta">
              <span v-if="isGlobal">{{ item.project_name }}</span>
              <span>{{ item.audit_cycle }}</span>
              <span v-if="item.assigned_to">{{ item.assigned_to }}</span>
            </div>
          </div>
          <el-empty v-if="!loading && !filteredItems.length" description="暂无待复核底稿" />
        </div>
      </div>

      <!-- 中栏：只读预览（Univer 只读实例） -->
      <div class="preview-panel">
        <template v-if="selectedItem">
          <div class="panel-header">
            <span>{{ selectedItem.wp_code }} — {{ selectedItem.wp_name }}</span>
            <el-button size="small" type="primary" link @click="openEditor(selectedItem)">
              打开完整编辑器 →
            </el-button>
          </div>
          <div class="preview-meta">
            <div class="meta-row">
              <label>项目：</label><span>{{ selectedItem.project_name }}</span>
            </div>
            <div class="meta-row">
              <label>审计循环：</label><span>{{ selectedItem.audit_cycle }}</span>
            </div>
            <div class="meta-row">
              <label>编制人：</label><span>{{ selectedItem.assigned_to || '-' }}</span>
            </div>
            <div class="meta-row">
              <label>提交版本：</label><span>v{{ selectedItem.file_version }}</span>
            </div>
            <div class="meta-row">
              <label>提交时间：</label>
              <span>
                {{ selectedItem.submitted_at
                  ? new Date(selectedItem.submitted_at).toLocaleString('zh-CN')
                  : '-' }}
              </span>
            </div>
            <div class="meta-row">
              <label>复核状态：</label>
              <el-tag
                :type="selectedItem.review_status === 'pending_level1' ? 'warning' : 'danger'"
                size="small"
              >
                {{ reviewStatusLabel(selectedItem.review_status) }}
              </el-tag>
            </div>
          </div>
          <!-- Univer 只读底稿预览 -->
          <div class="univer-readonly-container" v-if="wpSnapshot">
            <div ref="univerContainerRef" class="univer-sheet-host" />
          </div>
          <el-alert
            v-else
            type="info"
            :closable="false"
            show-icon
            title="底稿预览"
            description="正在加载底稿数据..."
          />
        </template>
        <el-empty v-else description="请从左侧选择底稿" />
      </div>

      <!-- 右栏：AI 预审 + 复核意见 -->
      <div class="review-panel">
        <template v-if="selectedWpId">
          <div class="panel-header">
            <span>AI 预审</span>
            <el-tag v-if="blockingCount > 0" type="danger" size="small">
              {{ blockingCount }} 项阻断
            </el-tag>
          </div>
          <div v-if="aiLoading" class="ai-loading">
            <el-icon class="is-loading"><Loading /></el-icon>
            正在预审...
          </div>
          <div v-else-if="!aiIssues.length" class="ai-empty">
            <el-icon color="#67c23a"><CircleCheck /></el-icon>
            AI 预审未发现问题
          </div>
          <div v-else class="ai-issues">
            <div
              v-for="(issue, idx) in aiIssues"
              :key="idx"
              class="ai-issue"
              :class="severityClass(issue.severity)"
            >
              <el-icon><WarningFilled /></el-icon>
              <div class="ai-issue-body">
                <div class="ai-issue-desc">{{ issue.description }}</div>
                <small v-if="issue.suggested_action">建议：{{ issue.suggested_action }}</small>
              </div>
            </div>
          </div>

          <el-divider />

          <div class="panel-header">
            <span>复核意见</span>
          </div>
          <el-input
            v-model="reviewComment"
            type="textarea"
            :rows="4"
            placeholder="输入复核意见（退回时将作为退回原因）..."
            @keydown.stop
          />

          <div class="review-actions">
            <el-tooltip
              :disabled="blockingCount === 0"
              :content="`请先处理 ${blockingCount} 项阻断问题`"
              placement="top"
            >
              <el-button
                type="success"
                :disabled="blockingCount > 0 || actioning"
                :loading="actioning && pendingAction === 'approve'"
                @click="approveCurrent"
              >
                通过 <small>(Ctrl+Enter)</small>
              </el-button>
            </el-tooltip>
            <el-button
              type="danger"
              :disabled="actioning"
              :loading="actioning && pendingAction === 'reject'"
              @click="rejectCurrent"
            >
              退回 <small>(Ctrl+Shift+Enter)</small>
            </el-button>
          </div>
          <div class="shortcut-hint">
            ↑/↓ 切换队列上/下一项
          </div>
        </template>
        <el-empty v-else description="请从左侧选择底稿开始复核" />
      </div>
    </div>

    <!-- 批量退回弹窗 -->
    <el-dialog v-model="showRejectDialog" title="退回原因" width="480" append-to-body>
      <el-input
        v-model="rejectComment"
        type="textarea"
        :rows="3"
        placeholder="请输入退回原因（可选）"
      />
      <template #footer>
        <el-button @click="showRejectDialog = false">取消</el-button>
        <el-button type="warning" @click="handleBatchReject">确认退回</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, WarningFilled, CircleCheck } from '@element-plus/icons-vue'
import { confirmBatch, confirmDangerous } from '@/utils/confirm'
import {
  getGlobalReviewInbox,
  getProjectReviewInbox,
  batchReview,
  type ReviewInboxItem,
} from '@/services/pmApi'
import { reviewContent, updateReviewStatus, type ReviewIssue } from '@/services/workpaperApi'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const router = useRouter()

const projectId = computed(() => route.params.projectId as string | undefined)
const isGlobal = computed(() => !projectId.value)
const projectName = ref('')

const viewMode = ref<'workbench' | 'batch'>('workbench')

const items = ref<ReviewInboxItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)

// 批量模式状态
const selectedIds = ref<string[]>([])
const showRejectDialog = ref(false)
const rejectComment = ref('')

// 三栏模式状态
const selectedWpId = ref<string>('')
const aiIssues = ref<ReviewIssue[]>([])
const aiLoading = ref(false)
const reviewComment = ref('')
const actioning = ref(false)
const pendingAction = ref<'approve' | 'reject' | null>(null)

// Univer 只读预览
const wpSnapshot = ref<any>(null)
const univerContainerRef = ref<HTMLElement | null>(null)
const reviewMarkers = ref<any[]>([])

// 筛选条件
const filterProjectId = ref('')
const filterCycle = ref('')
const filterResubmit = ref('')
const filterAssignee = ref('')
const searchKw = ref('')

// ── 计算属性 ──

const selectedItem = computed<ReviewInboxItem | null>(
  () => items.value.find((i) => i.id === selectedWpId.value) ?? null,
)

const blockingCount = computed(
  () => aiIssues.value.filter((i) => i.severity === 'blocking').length,
)

function isResubmitRow(row: ReviewInboxItem): boolean {
  return (row.file_version ?? 1) > 1
}

function reviewStatusLabel(s: string): string {
  if (s === 'pending_level1') return '待一级复核'
  if (s === 'pending_level2') return '待二级复核'
  if (s === 'level1_rejected') return '一级退回'
  if (s === 'level2_rejected') return '二级退回'
  return s
}

function severityClass(s: string): string {
  if (s === 'blocking') return 'blocking'
  if (s === 'warning') return 'warning'
  return 'info'
}

const projectOptions = computed(() => {
  const map = new Map<string, { id: string; name: string }>()
  for (const it of items.value) {
    if (it.project_id && !map.has(it.project_id)) {
      map.set(it.project_id, { id: it.project_id, name: it.project_name })
    }
  }
  return Array.from(map.values())
})

const cycleOptions = computed(() => {
  const set = new Set<string>()
  for (const it of items.value) {
    if (it.audit_cycle) set.add(it.audit_cycle)
  }
  return Array.from(set)
})

const assigneeOptions = computed(() => {
  const set = new Set<string>()
  for (const it of items.value) {
    if (it.assigned_to) set.add(it.assigned_to)
  }
  return Array.from(set)
})

const filteredItems = computed<ReviewInboxItem[]>(() => {
  let list = items.value
  if (filterProjectId.value) {
    list = list.filter((i) => i.project_id === filterProjectId.value)
  }
  if (filterCycle.value) {
    list = list.filter((i) => i.audit_cycle === filterCycle.value)
  }
  if (filterResubmit.value === 'resubmit') {
    list = list.filter(isResubmitRow)
  } else if (filterResubmit.value === 'first') {
    list = list.filter((i) => !isResubmitRow(i))
  }
  if (filterAssignee.value) {
    list = list.filter((i) => i.assigned_to === filterAssignee.value)
  }
  if (searchKw.value) {
    const kw = searchKw.value.toLowerCase()
    list = list.filter(
      (i) =>
        i.wp_code?.toLowerCase().includes(kw) ||
        i.wp_name?.toLowerCase().includes(kw),
    )
  }
  return list
})

// ── 数据加载 ──

async function loadData() {
  loading.value = true
  try {
    const result = isGlobal.value
      ? await getGlobalReviewInbox(page.value, pageSize)
      : await getProjectReviewInbox(projectId.value!, page.value, pageSize)
    items.value = result.items || []
    total.value = result.total || 0
    if (items.value.length > 0 && !isGlobal.value) {
      projectName.value = items.value[0].project_name
    }
    // 三栏模式：默认选中第一项
    if (viewMode.value === 'workbench') {
      const still = selectedWpId.value && items.value.some((i) => i.id === selectedWpId.value)
      if (!still && filteredItems.value.length > 0) {
        selectItem(filteredItems.value[0])
      } else if (still) {
        // 保持选中项不变
      } else {
        selectedWpId.value = ''
      }
    }
  } catch (e: any) {
    handleApiError(e, '加载复核数据')
  } finally {
    loading.value = false
  }
}

// ── 三栏模式：选中项 + AI 预审 ──

async function selectItem(item: ReviewInboxItem) {
  selectedWpId.value = item.id
  reviewComment.value = ''
  aiIssues.value = []
  wpSnapshot.value = null
  aiLoading.value = true
  try {
    const res: any = await reviewContent(item.project_id, item.id)
    aiIssues.value = res.issues || []
    // Load workpaper snapshot for Univer readonly preview
    wpSnapshot.value = res.univer_data || res.snapshot || { sheets: {} }
    reviewMarkers.value = res.review_markers || []
  } catch {
    aiIssues.value = []
    wpSnapshot.value = null
  } finally {
    aiLoading.value = false
  }
}

function selectAdjacent(offset: 1 | -1) {
  const list = filteredItems.value
  if (!list.length) return
  const idx = list.findIndex((i) => i.id === selectedWpId.value)
  let next = idx + offset
  if (next < 0) next = 0
  if (next >= list.length) next = list.length - 1
  if (list[next] && list[next].id !== selectedWpId.value) {
    selectItem(list[next])
  }
}

function pickNextAfterRemoval(removedId: string) {
  const list = filteredItems.value
  if (!list.length) {
    selectedWpId.value = ''
    aiIssues.value = []
    reviewComment.value = ''
    return
  }
  // 选中当前索引位置的项（被删除后，原索引位置即下一项）
  const idx = list.findIndex((i) => i.id !== removedId)
  const target = list[Math.min(idx < 0 ? 0 : idx, list.length - 1)]
  if (target) selectItem(target)
}

// ── 三栏模式：通过 / 退回 ──

async function approveCurrent() {
  const item = selectedItem.value
  if (!item || actioning.value) return
  if (blockingCount.value > 0) {
    ElMessage.warning(`请先处理 ${blockingCount.value} 项阻断问题`)
    return
  }
  actioning.value = true
  pendingAction.value = 'approve'
  try {
    const nextStatus =
      item.review_status === 'pending_level2' ? 'level2_passed' : 'level1_passed'
    await updateReviewStatus(item.project_id, item.id, nextStatus)
    ElMessage.success('复核通过')
    items.value = items.value.filter((i) => i.id !== item.id)
    total.value = Math.max(0, total.value - 1)
    pickNextAfterRemoval(item.id)
  } catch (e: any) {
    handleApiError(e, '操作')
  } finally {
    actioning.value = false
    pendingAction.value = null
  }
}

async function rejectCurrent() {
  const item = selectedItem.value
  if (!item || actioning.value) return
  actioning.value = true
  pendingAction.value = 'reject'
  try {
    const nextStatus =
      item.review_status === 'pending_level2' ? 'level2_rejected' : 'level1_rejected'
    await updateReviewStatus(item.project_id, item.id, nextStatus, reviewComment.value)
    ElMessage.warning('已退回修改')
    items.value = items.value.filter((i) => i.id !== item.id)
    total.value = Math.max(0, total.value - 1)
    reviewComment.value = ''
    pickNextAfterRemoval(item.id)
  } catch (e: any) {
    handleApiError(e, '操作')
  } finally {
    actioning.value = false
    pendingAction.value = null
  }
}

// ── 批量模式：沿用 ReviewInbox 原能力 ──

function onSelectionChange(rows: ReviewInboxItem[]) {
  selectedIds.value = rows.map((r) => r.id)
}

function openEditor(row: ReviewInboxItem) {
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: row.project_id, wpId: row.id },
  })
}

async function handleSingleApprove(row: ReviewInboxItem) {
  await confirmDangerous(`确认通过底稿 ${row.wp_code} ${row.wp_name}？`, '通过确认')
  await doBatchReview([row.id], 'approve', row.project_id)
}

async function handleSingleReject(row: ReviewInboxItem) {
  const { value } = await ElMessageBox.prompt('请输入退回原因（可选）', '退回底稿', {
    inputType: 'textarea',
  })
  await doBatchReview([row.id], 'reject', row.project_id, value || '')
}

async function handleBatchApprove() {
  if (!selectedIds.value.length) return
  await confirmBatch('通过', selectedIds.value.length)
  const pid = projectId.value || items.value[0]?.project_id
  if (!pid) return
  await doBatchReview(selectedIds.value, 'approve', pid)
}

async function handleBatchReject() {
  const pid = projectId.value || items.value[0]?.project_id
  if (!pid) return
  await doBatchReview(selectedIds.value, 'reject', pid, rejectComment.value)
  showRejectDialog.value = false
  rejectComment.value = ''
}

async function doBatchReview(
  ids: string[],
  action: 'approve' | 'reject',
  pid: string,
  comment = '',
) {
  try {
    const result = await batchReview(pid, ids, action, comment)
    const label = action === 'approve' ? '通过' : '退回'
    ElMessage.success(
      `${label}成功 ${result.succeeded_count} 个` +
        (result.skipped_count > 0 ? `，跳过 ${result.skipped_count} 个` : ''),
    )
    await loadData()
  } catch (e: any) {
    handleApiError(e, '操作')
  }
}

// ── 快捷键 ──

function isTypingTarget(el: EventTarget | null): boolean {
  if (!el || !(el instanceof HTMLElement)) return false
  const tag = el.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return true
  if (el.isContentEditable) return true
  return false
}

function handleKeydown(e: KeyboardEvent) {
  // 批量模式不启用快捷键
  if (viewMode.value !== 'workbench') return

  // Ctrl+Enter / Ctrl+Shift+Enter：即使焦点在输入框也生效（复核意见即是 comment）
  if (e.ctrlKey && e.key === 'Enter') {
    e.preventDefault()
    if (e.shiftKey) {
      rejectCurrent()
    } else if (blockingCount.value === 0) {
      approveCurrent()
    } else {
      ElMessage.warning(`请先处理 ${blockingCount.value} 项阻断问题`)
    }
    return
  }

  // ↑/↓：仅在非输入框聚焦时切换
  if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && !isTypingTarget(e.target)) {
    e.preventDefault()
    selectAdjacent(e.key === 'ArrowDown' ? 1 : -1)
  }
}

// 切换模式时清理批量选中
watch(viewMode, (v) => {
  if (v === 'batch') {
    selectedWpId.value = ''
    aiIssues.value = []
  } else {
    selectedIds.value = []
    // 进入三栏模式时自动选中第一项
    if (!selectedWpId.value && filteredItems.value.length > 0) {
      selectItem(filteredItems.value[0])
    }
  }
})

onMounted(() => {
  loadData()
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.review-workbench {
  padding: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.filter-bar {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-wrap: wrap;
}

/* 批量模式 */
.batch-view {
  padding: 12px;
}
.batch-actions {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
}
.gt-pagination {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

/* 三栏模式 */
.workbench-body {
  display: flex;
  gap: 12px;
  flex: 1;
  padding: 12px;
  min-height: 0;
}

.queue-panel {
  width: 300px;
  flex-shrink: 0;
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  padding-right: 12px;
  min-height: 0;
}

.queue-list {
  flex: 1;
  overflow-y: auto;
}

.preview-panel {
  flex: 1;
  min-width: 0;
  padding: 0 12px;
  overflow-y: auto;
}

.review-panel {
  width: 360px;
  flex-shrink: 0;
  border-left: 1px solid var(--el-border-color-lighter);
  padding-left: 12px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.queue-item {
  padding: 10px;
  cursor: pointer;
  border-radius: 6px;
  margin-bottom: 6px;
  border: 1px solid transparent;
  transition: all 0.15s ease;
}
.queue-item:hover {
  background: var(--el-fill-color-light);
}
.queue-item.active {
  background: var(--gt-primary-lighter, #f0ebf8);
  border-color: var(--gt-color-primary, #6e3fd4);
}
.queue-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.wp-code {
  font-weight: 600;
  font-size: 13px;
}
.wp-name {
  font-size: 12px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 4px;
}
.wp-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  flex-wrap: wrap;
}

.preview-meta {
  margin: 12px 0;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}

.univer-readonly-container {
  flex: 1;
  min-height: 300px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  overflow: hidden;
  margin-top: 12px;
}
.univer-sheet-host {
  width: 100%;
  height: 400px;
}
.meta-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 6px;
  align-items: center;
}
.meta-row label {
  min-width: 80px;
  color: var(--el-text-color-secondary);
}

.ai-loading,
.ai-empty {
  text-align: center;
  padding: 16px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
}

.ai-issues {
  max-height: 280px;
  overflow-y: auto;
}
.ai-issue {
  padding: 8px;
  margin-bottom: 6px;
  border-radius: 6px;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
}
.ai-issue.blocking {
  background: #fef0f0;
  color: var(--el-color-danger);
}
.ai-issue.warning {
  background: #fff8e6;
  color: var(--el-color-warning);
}
.ai-issue.info {
  background: #f4f4f5;
  color: var(--el-text-color-regular);
}
.ai-issue-body {
  flex: 1;
}
.ai-issue-desc {
  font-weight: 500;
}
.ai-issue small {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 11px;
  margin-top: 2px;
}

.review-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.shortcut-hint {
  margin-top: 8px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  text-align: center;
}
</style>
