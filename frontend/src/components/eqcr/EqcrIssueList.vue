<template>
  <div class="eqcr-issue-list">
    <!-- Summary cards -->
    <div class="summary-cards">
      <el-card class="summary-card open">
        <div class="card-value">{{ summary.open }}</div>
        <div class="card-label">待处理</div>
      </el-card>
      <el-card class="summary-card in-fix">
        <div class="card-value">{{ summary.in_fix }}</div>
        <div class="card-label">整改中</div>
      </el-card>
      <el-card class="summary-card closed">
        <div class="card-value">{{ summary.closed }}</div>
        <div class="card-label">已关闭</div>
      </el-card>
    </div>

    <!-- Toolbar -->
    <div class="toolbar">
      <el-button type="primary" @click="showCreateDialog = true">
        新建问题单
      </el-button>
    </div>

    <!-- Issue list -->
    <el-table :data="issues" stripe @row-click="handleRowClick">
      <el-table-column label="严重程度" width="120">
        <template #default="{ row }">
          <el-tag :type="severityTagType(row.severity)" size="small">
            {{ severityLabel(row.severity) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="200" />
      <el-table-column prop="category" label="分类" width="140" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="关联底稿" width="120">
        <template #default="{ row }">
          <el-link
            v-if="row.wp_id"
            type="primary"
            @click.stop="emit('navigate-to-wp', row.wp_id)"
          >
            {{ row.wp_id?.substring(0, 8) }}...
          </el-link>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="160">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>
    </el-table>

    <!-- Create issue dialog -->
    <el-dialog v-model="showCreateDialog" title="新建 EQCR 问题单" width="600px">
      <el-form label-position="top">
        <el-form-item label="严重程度" required>
          <el-select v-model="newIssue.severity" placeholder="选择严重程度">
            <el-option label="阻断 (Blocker)" value="blocker" />
            <el-option label="重要 (Major)" value="major" />
            <el-option label="一般 (Minor)" value="minor" />
            <el-option label="建议 (Suggestion)" value="suggestion" />
          </el-select>
        </el-form-item>
        <el-form-item label="分类" required>
          <el-input v-model="newIssue.category" placeholder="如：data_mismatch" />
        </el-form-item>
        <el-form-item label="标题" required>
          <el-input v-model="newIssue.title" placeholder="问题标题" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newIssue.description" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="关联底稿">
          <el-input v-model="newIssue.wp_id" placeholder="底稿 ID（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- Reply dialog -->
    <el-dialog v-model="showReplyDialog" title="回复问题单" width="500px">
      <div v-if="selectedIssue" class="reply-context">
        <p><strong>{{ selectedIssue.title }}</strong></p>
        <p class="desc">{{ selectedIssue.description }}</p>
      </div>
      <el-input
        v-model="replyContent"
        type="textarea"
        :rows="4"
        placeholder="输入回复内容..."
      />
      <template #footer>
        <el-button @click="showReplyDialog = false">取消</el-button>
        <el-button type="primary" @click="handleReply">回复</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { handleApiError } from '@/utils/errorHandler'

interface EqcrIssue {
  id: string
  project_id: string
  severity: string
  category: string
  title: string
  description: string | null
  status: string
  owner_id: string
  wp_id: string | null
  created_at: string | null
  updated_at: string | null
}

interface Props {
  projectId: string
}

interface Emits {
  (e: 'issue-created', issue: EqcrIssue): void
  (e: 'navigate-to-wp', wpId: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const issues = ref<EqcrIssue[]>([])
const summary = ref({ open: 0, in_fix: 0, closed: 0 })
const showCreateDialog = ref(false)
const showReplyDialog = ref(false)
const selectedIssue = ref<EqcrIssue | null>(null)
const replyContent = ref('')

const newIssue = ref({
  severity: '',
  category: '',
  title: '',
  description: '',
  wp_id: '',
})

onMounted(async () => {
  await loadIssues()
})

async function loadIssues() {
  try {
    const res = await axios.get(`/api/projects/${props.projectId}/eqcr-issues`)
    issues.value = res.data.items || []
    summary.value = res.data.summary || { open: 0, in_fix: 0, closed: 0 }
  } catch (e: any) {
    handleApiError(e, '加载问题单')
  }
}

async function handleCreate() {
  if (!newIssue.value.severity || !newIssue.value.category || !newIssue.value.title) {
    ElMessage.warning('请填写必填字段')
    return
  }

  try {
    const res = await axios.post(
      `/api/projects/${props.projectId}/eqcr-issues`,
      newIssue.value,
    )
    ElMessage.success('问题单已创建')
    showCreateDialog.value = false
    emit('issue-created', res.data)
    await loadIssues()
    // Reset form
    newIssue.value = { severity: '', category: '', title: '', description: '', wp_id: '' }
  } catch (err: any) {
    handleApiError(err, '创建问题单')
  }
}

function handleRowClick(row: EqcrIssue) {
  selectedIssue.value = row
  showReplyDialog.value = true
}

async function handleReply() {
  if (!replyContent.value.trim() || !selectedIssue.value) return

  try {
    await axios.post(
      `/api/projects/${props.projectId}/eqcr-issues/${selectedIssue.value.id}/reply`,
      { content: replyContent.value },
    )
    ElMessage.success('回复已发送')
    showReplyDialog.value = false
    replyContent.value = ''
  } catch (err: any) {
    handleApiError(err, '回复问题单')
  }
}

function severityTagType(severity: string) {
  const map: Record<string, string> = {
    blocker: 'danger',
    major: 'warning',
    minor: 'info',
    suggestion: '',
  }
  return map[severity] || ''
}

function severityLabel(severity: string) {
  const map: Record<string, string> = {
    blocker: '阻断',
    major: '重要',
    minor: '一般',
    suggestion: '建议',
  }
  return map[severity] || severity
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    open: 'danger',
    in_fix: 'warning',
    closed: 'success',
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    open: '待处理',
    in_fix: '整改中',
    closed: '已关闭',
  }
  return map[status] || status
}

function formatDate(dateStr: string | null) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}
</script>

<style scoped>
.eqcr-issue-list {
  padding: 16px;
}

.summary-cards {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.summary-card {
  flex: 1;
  text-align: center;
}

.summary-card .card-value {
  font-size: 28px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  font-family: 'Arial Narrow', Arial, sans-serif;
}

.summary-card .card-label {
  color: #909399;
  font-size: 13px;
  margin-top: 4px;
}

.summary-card.open .card-value { color: #F56C6C; }
.summary-card.in-fix .card-value { color: #E6A23C; }
.summary-card.closed .card-value { color: #67C23A; }

.toolbar {
  margin-bottom: 12px;
}

.reply-context {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
}

.reply-context .desc {
  color: #606266;
  font-size: 13px;
  margin-top: 4px;
}
</style>
