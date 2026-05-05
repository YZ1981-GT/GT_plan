<template>
  <div class="issue-ticket-list">
    <div class="issue-toolbar">
      <el-select v-model="filters.status" placeholder="状态" clearable size="small" style="width:120px">
        <el-option label="待处理" value="open" />
        <el-option label="修复中" value="in_fix" />
        <el-option label="待复验" value="pending_recheck" />
        <el-option label="已关闭" value="closed" />
        <el-option label="已驳回" value="rejected" />
      </el-select>
      <el-select v-model="filters.severity" placeholder="严重度" clearable size="small" style="width:120px">
        <el-option label="阻断" value="blocker" />
        <el-option label="重大" value="major" />
        <el-option label="一般" value="minor" />
        <el-option label="建议" value="suggestion" />
      </el-select>
      <el-select v-model="filters.source" placeholder="来源" clearable size="small" style="width:140px">
        <el-option label="L2" value="L2" />
        <el-option label="L3" value="L3" />
        <el-option label="Q" value="Q" />
        <el-option label="复核意见" value="review_comment" />
      </el-select>
      <el-button size="small" @click="loadData">刷新</el-button>
    </div>

    <el-table :data="issues" border size="small" stripe @row-click="handleRowClick">
      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
      <el-table-column prop="source" label="来源" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="sourceTagType(row.source)" size="small">{{ sourceLabel(row.source) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="severity" label="严重度" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="severityTagType(row.severity)" size="small">{{ severityLabel(row.severity) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="SLA 倒计时" width="120" align="center">
        <template #default="{ row }">
          <span :class="slaClass(row.due_at)">{{ slaCountdown(row.due_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="160">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next"
      @current-change="handlePageChange"
      style="margin-top:12px;justify-content:flex-end"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listIssues, type IssueTicket } from '@/services/governanceApi'

const route = useRoute()
const projectId = route.params.projectId as string

const filters = reactive({ status: '', severity: '', source: '' })
const issues = ref<IssueTicket[]>([])
const page = ref(1)
const pageSize = 50
const total = ref(0)
let slaTimer: ReturnType<typeof setInterval> | null = null

async function loadData() {
  try {
    const result = await listIssues({
      project_id: projectId,
      status: filters.status || undefined,
      severity: filters.severity || undefined,
      source: filters.source || undefined,
      page: page.value,
      page_size: pageSize,
    })
    issues.value = result.items || []
    total.value = result.total || 0
  } catch (e: any) {
    ElMessage.error('加载问题单失败')
  }
}

function handlePageChange(p: number) { page.value = p; loadData() }
function handleRowClick(_row: IssueTicket) {
  // TODO: 打开问题单详情弹窗
}

function sourceTagType(s: string) {
  if (s === 'Q') return 'danger'
  if (s === 'L3') return 'warning'
  if (s === 'review_comment') return 'info'
  return ''
}
function sourceLabel(s: string): string {
  const m: Record<string, string> = {
    L2: 'L2',
    L3: 'L3',
    Q: 'Q',
    review_comment: '复核意见',
    consistency: '一致性',
    ai: 'AI',
    reminder: '催办',
    client_commitment: '客户承诺',
    pbc: 'PBC',
    confirmation: '函证',
    qc_inspection: '质控抽查',
  }
  return m[s] || s
}
function severityTagType(s: string) {
  if (s === 'blocker') return 'danger'
  if (s === 'major') return 'warning'
  return 'info'
}
function severityLabel(s: string) {
  const m: Record<string, string> = { blocker: '阻断', major: '重大', minor: '一般', suggestion: '建议' }
  return m[s] || s
}
function statusTagType(s: string) {
  if (s === 'closed') return 'success'
  if (s === 'rejected') return 'danger'
  if (s === 'open') return 'warning'
  return 'info'
}
function statusLabel(s: string) {
  const m: Record<string, string> = { open: '待处理', in_fix: '修复中', pending_recheck: '待复验', closed: '已关闭', rejected: '已驳回' }
  return m[s] || s
}

function slaCountdown(dueAt: string | undefined): string {
  if (!dueAt) return '--'
  const diff = new Date(dueAt).getTime() - Date.now()
  if (diff <= 0) return '已超时'
  const hours = Math.floor(diff / 3600000)
  const mins = Math.floor((diff % 3600000) / 60000)
  return `${hours}h ${mins}m`
}
function slaClass(dueAt: string | undefined): string {
  if (!dueAt) return ''
  const diff = new Date(dueAt).getTime() - Date.now()
  if (diff <= 0) return 'sla-expired'
  if (diff < 4 * 3600000) return 'sla-urgent'
  if (diff < 24 * 3600000) return 'sla-warning'
  return ''
}
function formatTime(t: string | undefined) {
  if (!t) return '--'
  return new Date(t).toLocaleString('zh-CN')
}

onMounted(() => {
  loadData()
  // SLA 倒计时每分钟刷新
  slaTimer = setInterval(() => { issues.value = [...issues.value] }, 60000)
})
onUnmounted(() => { if (slaTimer) clearInterval(slaTimer) })
</script>

<style scoped>
.issue-ticket-list { padding: 16px; }
.issue-toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.sla-expired { color: var(--el-color-danger); font-weight: 600; }
.sla-urgent { color: var(--el-color-danger); }
.sla-warning { color: var(--el-color-warning); }
</style>
