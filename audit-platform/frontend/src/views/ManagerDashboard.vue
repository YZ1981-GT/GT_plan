<template>
  <div class="gt-manager-dashboard gt-fade-in">
    <!-- 页面头部 -->
    <div class="gt-page-banner">
      <div class="gt-banner-content">
        <h2>📊 项目经理工作台</h2>
        <span class="gt-banner-sub">
          <template v-if="overview">
            {{ overview.projects.length }} 个项目 · {{ crossTodoTotal }} 项待办
          </template>
        </span>
      </div>
      <div class="gt-banner-actions">
        <span class="gt-last-update" v-if="lastUpdateTime">
          上次更新 {{ elapsedText }} 前
        </span>
        <el-button size="small" :loading="loading" @click="loadOverview">
          刷新
        </el-button>
      </div>
    </div>

    <!-- 区块一：项目总览（卡片网格） -->
    <section class="gt-section">
      <h3 class="gt-section-title">项目总览</h3>
      <div class="gt-project-grid" v-if="overview && overview.projects.length">
        <div
          v-for="proj in overview.projects"
          :key="proj.project_id"
          class="gt-project-card"
          @click="goToProject(proj.project_id)"
        >
          <div class="gt-card-header">
            <span class="gt-card-name">{{ proj.project_name }}</span>
            <el-tag
              :type="riskTagType(proj.risk_level)"
              size="small"
            >
              {{ riskLabel(proj.risk_level) }}
            </el-tag>
          </div>
          <div class="gt-card-body">
            <div class="gt-card-stat">
              <span class="gt-stat-label">完成率</span>
              <el-progress
                :percentage="proj.completion_rate"
                :stroke-width="8"
                :color="progressColor(proj.completion_rate)"
                style="flex: 1"
              />
            </div>
            <div v-if="proj.budget_hours" class="gt-card-stat gt-cost-stat">
              <span class="gt-stat-label">工时</span>
              <div class="gt-cost-bar-wrapper">
                <el-progress
                  :percentage="Math.min(costPercentage(proj), 100)"
                  :stroke-width="8"
                  :color="costBarColor(proj)"
                  style="flex: 1"
                />
                <span
                  :class="['gt-cost-text', {
                    'gt-cost-warning': costPercentage(proj) > 90 && costPercentage(proj) <= 100,
                    'gt-cost-danger gt-cost-blink': costPercentage(proj) > 100,
                  }]"
                >
                  {{ proj.actual_hours ?? 0 }} / {{ proj.budget_hours }}h
                </span>
              </div>
            </div>
            <div class="gt-card-metrics">
              <div class="gt-metric" @click.stop="goToReviewInbox(proj.project_id)">
                <span class="gt-metric-value">{{ proj.pending_review }}</span>
                <span class="gt-metric-label">待复核</span>
              </div>
              <div class="gt-metric" @click.stop="goToUnassigned(proj.project_id)">
                <span class="gt-metric-value">{{ proj.pending_assign }}</span>
                <span class="gt-metric-label">待分配</span>
              </div>
              <div class="gt-metric">
                <span class="gt-metric-value gt-metric-overdue">{{ proj.overdue_count }}</span>
                <span class="gt-metric-label">逾期</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <el-empty v-else-if="!loading" :image-size="60" description="暂无项目数据" />

      <!-- 跨项目合并简报导出 -->
      <CrossProjectBriefExporter
        v-if="overview && overview.projects.length > 0"
        :projects="briefProjects"
        class="gt-brief-exporter"
      />
    </section>

    <!-- 区块二：跨项目待办 -->
    <section class="gt-section">
      <h3 class="gt-section-title">跨项目待办</h3>
      <el-tabs v-model="crossTodoTab" class="gt-cross-todo-tabs">
        <el-tab-pane label="待办概览" name="overview">
          <el-row :gutter="16" v-if="overview">
            <el-col :span="8">
              <div class="gt-todo-card" @click="goToReviewInbox()">
                <div class="gt-todo-icon">📋</div>
                <div class="gt-todo-info">
                  <span class="gt-todo-count">{{ overview.cross_todos.pending_review }}</span>
                  <span class="gt-todo-label">待复核</span>
                </div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="gt-todo-card" @click="goToUnassigned()">
                <div class="gt-todo-icon">📝</div>
                <div class="gt-todo-info">
                  <span class="gt-todo-count">{{ overview.cross_todos.pending_assign }}</span>
                  <span class="gt-todo-label">待分配</span>
                </div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="gt-todo-card" @click="goToWorkHoursApprove()">
                <div class="gt-todo-icon">⏱️</div>
                <div class="gt-todo-info">
                  <span class="gt-todo-count">{{ overview.cross_todos.pending_approve }}</span>
                  <span class="gt-todo-label">待审批工时</span>
                </div>
              </div>
            </el-col>
          </el-row>
        </el-tab-pane>
        <el-tab-pane name="commitments">
          <template #label>
            客户承诺
            <el-badge
              v-if="overdueCommitments.length"
              :value="overdueCommitments.length"
              type="danger"
              class="gt-commitment-badge"
            />
          </template>
          <el-table
            v-if="filteredCommitments.length"
            :data="filteredCommitments"
            stripe
            style="width: 100%"
            :header-cell-style="{ background: '#f5f7fa', fontWeight: '600' }"
          >
            <el-table-column prop="project_name" label="项目" min-width="160" />
            <el-table-column prop="content" label="承诺内容" min-width="240" />
            <el-table-column label="到期日" min-width="120">
              <template #default="{ row }">
                <span :class="{ 'gt-overdue-text': row.is_overdue }">
                  {{ row.due_date || '—' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="状态" min-width="100">
              <template #default="{ row }">
                <el-tag v-if="row.is_overdue" type="danger" size="small">逾期</el-tag>
                <el-tag v-else-if="row.status === 'done'" type="success" size="small">已完成</el-tag>
                <el-tag v-else type="warning" size="small">待完成</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" min-width="120">
              <template #default="{ row }">
                <el-button
                  v-if="row.status !== 'done'"
                  type="primary"
                  size="small"
                  :loading="row._completing"
                  @click="completeCommitment(row)"
                >
                  已完成
                </el-button>
                <span v-else class="gt-status-normal">—</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty
            v-else-if="!commitmentsLoading"
            :image-size="50"
            description="暂无 7 天内到期或逾期的客户承诺"
          />
          <div v-if="commitmentsLoading" class="gt-loading-hint">加载中...</div>
        </el-tab-pane>
      </el-tabs>
    </section>

    <!-- 区块：近期委派状态 -->
    <section class="gt-section">
      <h3 class="gt-section-title">近期委派</h3>
      <el-table
        v-if="assignmentStatusList.length"
        :data="assignmentStatusList"
        stripe
        style="width: 100%"
        :header-cell-style="{ background: '#f5f7fa', fontWeight: '600' }"
      >
        <el-table-column prop="wp_code" label="底稿编号" min-width="160" />
        <el-table-column prop="assignee_name" label="被委派人" min-width="120" />
        <el-table-column label="委派时间" min-width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.assigned_at) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="200">
          <template #default="{ row }">
            <span v-if="row.notification_read_at" class="gt-status-read">
              ✅ 已读 {{ formatDateTime(row.notification_read_at) }}
            </span>
            <span v-else class="gt-status-unread">
              🔵 未读
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作提示" min-width="180">
          <template #default="{ row }">
            <el-tag
              v-if="row.is_overdue_unread"
              type="danger"
              size="small"
              class="gt-overdue-tag"
            >
              建议当面跟进
            </el-tag>
            <span v-else class="gt-status-normal">—</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else-if="!assignmentStatusLoading" :image-size="50" description="近 7 天无委派记录" />
    </section>

    <!-- 区块三：本周关键动作 -->
    <section class="gt-section">
      <h3 class="gt-section-title">本周关键动作</h3>
      <div class="gt-actions-list" v-if="weeklyActions.length">
        <div v-for="(action, idx) in weeklyActions" :key="idx" class="gt-action-item">
          <span class="gt-action-index">{{ idx + 1 }}</span>
          <span class="gt-action-text">{{ action.description }}</span>
          <el-tag :type="actionTagType(action.priority)" size="small">
            {{ action.priority === 'high' ? '紧急' : action.priority === 'medium' ? '重要' : '一般' }}
          </el-tag>
        </div>
      </div>
      <el-empty v-else-if="!loading" :image-size="50" description="本周暂无关键动作" />
    </section>

    <!-- 区块四：团队负载 -->
    <section class="gt-section">
      <h3 class="gt-section-title">团队负载</h3>
      <el-table
        v-if="overview && overview.team_load.length"
        :data="overview.team_load"
        stripe
        style="width: 100%"
        :header-cell-style="{ background: '#f5f7fa', fontWeight: '600' }"
      >
        <el-table-column prop="staff_name" label="姓名" min-width="120" />
        <el-table-column prop="title" label="职级" min-width="100" />
        <el-table-column prop="project_count" label="参与项目数" min-width="120" align="center" />
        <el-table-column prop="week_hours" label="本周工时" min-width="120" align="center">
          <template #default="{ row }">
            <span :class="{ 'gt-hours-warning': row.week_hours > 50 }">
              {{ row.week_hours }}h
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="total_hours" label="累计工时" min-width="120" align="center">
          <template #default="{ row }">
            {{ row.total_hours }}h
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else-if="!loading" :image-size="50" description="暂无团队负载数据" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/apiProxy'
import http from '@/utils/http'
import { ElMessage } from 'element-plus'
import { listCommunications } from '@/services/pmApi'
import type { CommitmentEntry, CommunicationRecord } from '@/services/pmApi'
import CrossProjectBriefExporter from '@/components/pm/CrossProjectBriefExporter.vue'
import type { BriefProject } from '@/components/pm/CrossProjectBriefExporter.vue'

const router = useRouter()

// ── 数据状态 ──
interface ProjectCard {
  project_id: string
  project_name: string
  completion_rate: number
  pending_review: number
  pending_assign: number
  overdue_count: number
  risk_level: string
  budget_hours?: number | null
  actual_hours?: number | null
}

interface CrossTodos {
  pending_review: number
  pending_assign: number
  pending_approve: number
}

interface TeamLoadItem {
  staff_name: string
  title: string
  project_count: number
  week_hours: number
  total_hours: number
}

interface WeeklyAction {
  description: string
  priority: 'high' | 'medium' | 'low'
}

interface AssignmentStatusItem {
  wp_code: string
  assignee_name: string
  assigned_at: string
  notification_read_at: string | null
  is_overdue_unread: boolean
}

interface ManagerOverview {
  projects: ProjectCard[]
  cross_todos: CrossTodos
  team_load: TeamLoadItem[]
  weekly_actions?: WeeklyAction[]
}

const overview = ref<ManagerOverview | null>(null)
const loading = ref(false)
const lastUpdateTime = ref<Date | null>(null)
const elapsedText = ref('')

// 近期委派状态
const assignmentStatusList = ref<AssignmentStatusItem[]>([])
const assignmentStatusLoading = ref(false)

// 客户承诺 Tab
const crossTodoTab = ref('overview')
const commitmentsLoading = ref(false)

interface CommitmentDisplayItem {
  project_id: string
  project_name: string
  comm_id: string
  commitment_id: string
  content: string
  due_date: string | null
  status: string
  is_overdue: boolean
  _completing: boolean
}

const allCommitments = ref<CommitmentDisplayItem[]>([])

// 逾期承诺（到期日 < 今天 且 status != 'done'）
const overdueCommitments = computed(() =>
  allCommitments.value.filter(c => c.is_overdue)
)

// 过滤后的承诺列表：逾期置顶，其余按到期日升序
const filteredCommitments = computed(() => {
  const items = [...allCommitments.value]
  items.sort((a, b) => {
    // 逾期置顶
    if (a.is_overdue && !b.is_overdue) return -1
    if (!a.is_overdue && b.is_overdue) return 1
    // 同类按到期日升序
    if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date)
    if (a.due_date && !b.due_date) return -1
    if (!a.due_date && b.due_date) return 1
    return 0
  })
  return items
})

// 简报导出用项目列表
const briefProjects = computed<BriefProject[]>(() => {
  if (!overview.value) return []
  return overview.value.projects.map(p => ({
    id: p.project_id,
    name: p.project_name,
  }))
})

// 计算跨项目待办总数
const crossTodoTotal = computed(() => {
  if (!overview.value) return 0
  const t = overview.value.cross_todos
  return t.pending_review + t.pending_assign + t.pending_approve
})

// 本周关键动作（从 overview 或独立计算）
const weeklyActions = computed<WeeklyAction[]>(() => {
  if (!overview.value) return []
  // 如果后端返回了 weekly_actions 直接用
  if (overview.value.weekly_actions?.length) {
    return overview.value.weekly_actions.slice(0, 5)
  }
  // 否则根据项目数据自动生成 Top 5
  const actions: WeeklyAction[] = []
  const todos = overview.value.cross_todos
  if (todos.pending_review > 0) {
    actions.push({ description: `${todos.pending_review} 张底稿待复核`, priority: 'high' })
  }
  if (todos.pending_assign > 0) {
    actions.push({ description: `${todos.pending_assign} 张底稿待分配`, priority: 'high' })
  }
  if (todos.pending_approve > 0) {
    actions.push({ description: `${todos.pending_approve} 条工时待审批`, priority: 'medium' })
  }
  const overdueProjects = overview.value.projects.filter(p => p.overdue_count > 0)
  for (const p of overdueProjects.slice(0, 2)) {
    actions.push({ description: `${p.project_name} 有 ${p.overdue_count} 张逾期底稿需催办`, priority: 'high' })
  }
  return actions.slice(0, 5)
})

// ── 时间戳更新 ──
let elapsedTimer: ReturnType<typeof setInterval> | null = null
// Batch 2 P2: 1 小时无用户交互后停止 timer，减少 CPU 空转
const INACTIVITY_TIMEOUT_MS = 60 * 60 * 1000 // 1 hour
let lastInteractionTime = Date.now()
let timerStopped = false

function updateElapsed() {
  if (!lastUpdateTime.value) { elapsedText.value = ''; return }
  const diff = Math.floor((Date.now() - lastUpdateTime.value.getTime()) / 1000)
  if (diff < 60) elapsedText.value = `${diff}s`
  else if (diff < 3600) elapsedText.value = `${Math.floor(diff / 60)}m`
  else elapsedText.value = `${Math.floor(diff / 3600)}h`

  // 检查是否超过 1 小时无交互
  if (Date.now() - lastInteractionTime > INACTIVITY_TIMEOUT_MS) {
    stopElapsedTimer()
  }
}

function stopElapsedTimer() {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
    timerStopped = true
  }
}

function resumeElapsedTimer() {
  lastInteractionTime = Date.now()
  if (timerStopped) {
    timerStopped = false
    elapsedTimer = setInterval(updateElapsed, 1000)
    updateElapsed()
  }
}

function onUserActivity() {
  lastInteractionTime = Date.now()
  if (timerStopped) {
    resumeElapsedTimer()
  }
}

// ── 加载数据 ──
async function loadOverview() {
  loading.value = true
  try {
    const data = await api.get('/api/dashboard/manager/overview')
    overview.value = data as ManagerOverview
    lastUpdateTime.value = new Date()
    updateElapsed()
    // Batch 1 Fix 1.7: budget_hours/actual_hours 已包含在 overview 响应中，无需 N+1
  } catch (err: any) {
    const msg = err?.detail?.message || err?.message || '加载失败'
    ElMessage.error(`加载经理看板失败：${msg}`)
  } finally {
    loading.value = false
  }
}

// ── 加载近期委派状态 ──
async function loadAssignmentStatus() {
  assignmentStatusLoading.value = true
  try {
    const data = await api.get('/api/dashboard/manager/assignment-status?days=7')
    assignmentStatusList.value = (data as AssignmentStatusItem[]) || []
  } catch (err: any) {
    const msg = err?.detail?.message || err?.message || '加载失败'
    ElMessage.error(`加载委派状态失败：${msg}`)
  } finally {
    assignmentStatusLoading.value = false
  }
}

// ── 加载客户承诺 ──
async function loadCommitments() {
  if (!overview.value || !overview.value.projects.length) return
  commitmentsLoading.value = true
  try {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const sevenDaysLater = new Date(today)
    sevenDaysLater.setDate(sevenDaysLater.getDate() + 7)

    const items: CommitmentDisplayItem[] = []

    // 并行获取所有项目的沟通记录
    const results = await Promise.allSettled(
      overview.value.projects.map(async (proj) => {
        const comms = await listCommunications(proj.project_id)
        return { proj, comms }
      })
    )

    for (const result of results) {
      if (result.status !== 'fulfilled') continue
      const { proj, comms } = result.value
      for (const comm of comms) {
        const commitments = normalizeCommitments(comm.commitments)
        for (const c of commitments) {
          if (c.status === 'done') continue
          const dueDate = c.due_date ? new Date(c.due_date) : null
          if (!dueDate) continue // 无到期日的不显示

          const isOverdue = dueDate < today
          const isWithin7Days = dueDate >= today && dueDate <= sevenDaysLater

          if (isOverdue || isWithin7Days) {
            items.push({
              project_id: proj.project_id,
              project_name: proj.project_name,
              comm_id: comm.id,
              commitment_id: c.id || '',
              content: c.content,
              due_date: c.due_date,
              status: isOverdue ? 'overdue' : (c.status || 'pending'),
              is_overdue: isOverdue,
              _completing: false,
            })
          }
        }
      }
    }

    allCommitments.value = items
  } catch (err: any) {
    const msg = err?.detail?.message || err?.message || '加载失败'
    ElMessage.error(`加载客户承诺失败：${msg}`)
  } finally {
    commitmentsLoading.value = false
  }
}

function normalizeCommitments(commitments: CommitmentEntry[] | string): CommitmentEntry[] {
  if (!commitments) return []
  if (typeof commitments === 'string') {
    if (!commitments.trim()) return []
    return [{ content: commitments, due_date: null, status: 'pending' }]
  }
  return commitments
}

// ── 标记承诺已完成 ──
async function completeCommitment(row: CommitmentDisplayItem) {
  if (!row.commitment_id) {
    ElMessage.warning('该承诺无法标记完成（缺少 ID）')
    return
  }
  row._completing = true
  try {
    await http.patch(
      `/api/projects/${row.project_id}/communications/${row.comm_id}/commitments/${row.commitment_id}`,
      { status: 'done' }
    )
    ElMessage.success(`承诺"${row.content}"已标记完成`)
    // 从列表中移除或更新状态
    row.status = 'done'
    allCommitments.value = allCommitments.value.filter(c => c !== row)
  } catch (err: any) {
    const msg = err?.response?.data?.detail?.message || err?.message || '操作失败'
    ElMessage.error(`标记完成失败：${msg}`)
  } finally {
    row._completing = false
  }
}

// ── 格式化日期时间 ──
function formatDateTime(isoStr: string): string {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ── 导航跳转 ──
function goToProject(projectId: string) {
  router.push(`/projects/${projectId}/progress-board`)
}

function goToReviewInbox(projectId?: string) {
  if (projectId) {
    router.push(`/projects/${projectId}/review-inbox`)
  } else {
    router.push('/review-inbox')
  }
}

function goToUnassigned(projectId?: string) {
  if (projectId) {
    router.push({ path: `/projects/${projectId}/workpapers`, query: { filter_assigned: 'unassigned' } })
  } else {
    // 跳到第一个有待分配的项目
    const proj = overview.value?.projects.find(p => p.pending_assign > 0)
    if (proj) {
      router.push({ path: `/projects/${proj.project_id}/workpapers`, query: { filter_assigned: 'unassigned' } })
    }
  }
}

function goToWorkHoursApprove() {
  router.push('/work-hours/approve')
}

// ── 辅助函数 ──
function riskTagType(level: string): 'danger' | 'warning' | 'success' | 'info' {
  if (level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  if (level === 'low') return 'success'
  return 'info'
}

function riskLabel(level: string): string {
  if (level === 'high') return '高风险'
  if (level === 'medium') return '中风险'
  if (level === 'low') return '低风险'
  return '未评估'
}

function progressColor(rate: number): string {
  if (rate >= 80) return '#67c23a'
  if (rate >= 50) return '#e6a23c'
  return '#f56c6c'
}

function costPercentage(proj: ProjectCard): number {
  if (!proj.budget_hours || proj.budget_hours <= 0) return 0
  return Math.round(((proj.actual_hours ?? 0) / proj.budget_hours) * 100)
}

function costBarColor(proj: ProjectCard): string {
  const pct = costPercentage(proj)
  if (pct > 100) return '#f56c6c'
  if (pct > 90) return '#e6a23c'
  return '#409eff'
}

function actionTagType(priority: string): 'danger' | 'warning' | 'info' {
  if (priority === 'high') return 'danger'
  if (priority === 'medium') return 'warning'
  return 'info'
}

// ── 生命周期 ──
onMounted(() => {
  loadOverview()
  loadAssignmentStatus()
  elapsedTimer = setInterval(updateElapsed, 1000)
  // 监听用户交互以重启 timer
  document.addEventListener('click', onUserActivity)
  document.addEventListener('keydown', onUserActivity)
  document.addEventListener('mousemove', onUserActivity)
})

// 切换到客户承诺 tab 时加载数据
watch(crossTodoTab, (val) => {
  if (val === 'commitments' && allCommitments.value.length === 0 && !commitmentsLoading.value) {
    loadCommitments()
  }
})

// overview 加载完成后如果已在 commitments tab 则自动加载
watch(overview, (val) => {
  if (val && crossTodoTab.value === 'commitments') {
    loadCommitments()
  }
})

onBeforeUnmount(() => {
  if (elapsedTimer) clearInterval(elapsedTimer)
  document.removeEventListener('click', onUserActivity)
  document.removeEventListener('keydown', onUserActivity)
  document.removeEventListener('mousemove', onUserActivity)
})
</script>

<style scoped>
.gt-manager-dashboard {
  padding: var(--gt-space-4);
  max-width: 1400px;
}

/* 页面头部 */
.gt-page-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding: 16px 20px;
  background: linear-gradient(135deg, #f8f6fb 0%, #eee8f5 100%);
  border-radius: var(--gt-radius-md);
}
.gt-banner-content h2 {
  margin: 0 0 4px;
  font-size: 20px;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-banner-sub {
  font-size: 13px;
  color: var(--gt-color-text-secondary);
}
.gt-banner-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.gt-last-update {
  font-size: 12px;
  color: var(--gt-color-text-tertiary);
}

/* 区块标题 */
.gt-section {
  margin-bottom: 28px;
}
.gt-section-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 12px;
  color: var(--gt-color-text);
}

/* 项目卡片网格 */
.gt-project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
.gt-project-card {
  background: #fff;
  border: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-md);
  padding: 16px;
  cursor: pointer;
  transition: all var(--gt-transition-fast);
  box-shadow: var(--gt-shadow-sm);
}
.gt-project-card:hover {
  border-color: var(--gt-color-primary-lighter, #c4b0d9);
  box-shadow: 0 4px 12px rgba(75, 45, 119, 0.1);
  transform: translateY(-1px);
}
.gt-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.gt-card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}
.gt-card-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gt-card-stat {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-stat-label {
  font-size: 12px;
  color: var(--gt-color-text-secondary);
  white-space: nowrap;
}
.gt-card-metrics {
  display: flex;
  gap: 16px;
}

/* 工时成本进度条 */
.gt-cost-stat {
  margin-top: 4px;
}
.gt-cost-bar-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}
.gt-cost-text {
  font-size: 11px;
  color: var(--gt-color-text-secondary);
  white-space: nowrap;
}
.gt-cost-warning {
  color: #e6a23c;
  font-weight: 600;
}
.gt-cost-danger {
  color: #f56c6c;
  font-weight: 700;
}
.gt-cost-blink {
  animation: gt-blink 1s ease-in-out infinite;
}
@keyframes gt-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.gt-metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--gt-radius-sm);
  transition: background var(--gt-transition-fast);
}
.gt-metric:hover {
  background: var(--gt-color-primary-bg, #f8f6fb);
}
.gt-metric-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-metric-overdue {
  color: var(--el-color-danger, #f56c6c);
}
.gt-metric-label {
  font-size: 11px;
  color: var(--gt-color-text-tertiary);
}

/* 跨项目简报导出 */
.gt-brief-exporter {
  margin-top: 16px;
}

/* 跨项目待办卡片 */
.gt-todo-card {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  border: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-md);
  padding: 16px;
  cursor: pointer;
  transition: all var(--gt-transition-fast);
}
.gt-todo-card:hover {
  border-color: var(--gt-color-primary-lighter, #c4b0d9);
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.08);
}
.gt-todo-icon {
  font-size: 24px;
}
.gt-todo-info {
  display: flex;
  flex-direction: column;
}
.gt-todo-count {
  font-size: 22px;
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-todo-label {
  font-size: 12px;
  color: var(--gt-color-text-secondary);
}

/* 本周关键动作 */
.gt-actions-list {
  background: #fff;
  border: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-md);
  overflow: hidden;
}
.gt-action-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid #f5f5f5;
}
.gt-action-item:last-child {
  border-bottom: none;
}
.gt-action-index {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gt-color-primary-bg, #f8f6fb);
  color: var(--gt-color-primary, #4b2d77);
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.gt-action-text {
  flex: 1;
  font-size: 13px;
  color: var(--gt-color-text);
}

/* 团队负载 */
.gt-hours-warning {
  color: var(--el-color-danger, #f56c6c);
  font-weight: 600;
}

/* 近期委派状态 */
.gt-status-read {
  color: var(--el-color-success, #67c23a);
  font-size: 13px;
}
.gt-status-unread {
  color: var(--el-color-primary, #409eff);
  font-size: 13px;
  font-weight: 500;
}
.gt-overdue-tag {
  font-weight: 600;
}
.gt-status-normal {
  color: var(--gt-color-text-tertiary);
  font-size: 13px;
}

/* 跨项目待办 Tabs */
.gt-cross-todo-tabs {
  margin-top: 4px;
}
.gt-cross-todo-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
.gt-commitment-badge {
  margin-left: 6px;
}
.gt-commitment-badge :deep(.el-badge__content) {
  font-size: 10px;
}
.gt-overdue-text {
  color: var(--el-color-danger, #f56c6c);
  font-weight: 600;
}
.gt-loading-hint {
  text-align: center;
  padding: 24px;
  color: var(--gt-color-text-tertiary);
  font-size: 13px;
}
</style>
