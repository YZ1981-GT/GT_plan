<template>
  <div class="gt-review-panel">
    <!-- 复核意见列表 -->
    <div class="panel-header">
      <span class="panel-title">复核意见</span>
      <el-button type="primary" size="small" @click="openCreateDialog">
        新建意见
      </el-button>
    </div>

    <el-table
      :data="sortedReviews"
      stripe
      class="review-table"
      empty-text="暂无复核意见"
    >
      <el-table-column label="复核级别" width="120">
        <template #default="{ row }">
          <el-tag :type="(levelTagType(row.review_level)) || undefined" size="small">
            {{ levelName(row.review_level) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag
            :type="(statusTagType(row.review_status)) || undefined"
            size="small"
          >
            {{ statusName(row.review_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="comments" label="意见内容" min-width="200" />
      <el-table-column label="复核时间" width="160">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="回复" width="80">
        <template #default="{ row }">
          <el-button
            v-if="row.reply_text"
            type="success"
            size="small"
            text
            @click="showReply(row)"
          >
            查看
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 复核历史时间线 -->
    <div v-if="timelineItems.length > 0" class="timeline-section">
      <div class="section-title">复核历史</div>
      <el-timeline>
        <el-timeline-item
          v-for="item in timelineItems"
          :key="item.id"
          :timestamp="formatDate(item.created_at)"
          :color="item.review_status === 'approved' ? '#67c23a' : item.review_status === 'rejected' ? '#f56c6c' : '#909399'"
        >
          <p class="timeline-level">{{ levelName(item.review_level) }}</p>
          <p class="timeline-status">{{ statusName(item.review_status) }}</p>
          <p v-if="item.comments" class="timeline-comment">{{ item.comments }}</p>
          <p v-if="item.reply_text" class="timeline-reply">
            <strong>回复：</strong>{{ item.reply_text }}
          </p>
        </el-timeline-item>
      </el-timeline>
    </div>

    <!-- 新建复核意见对话框 -->
    <el-dialog append-to-body v-model="createDialogVisible" title="新建复核意见" width="500px">
      <el-form :model="reviewForm" label-width="100px">
        <el-form-item label="复核级别" required>
          <el-select v-model="reviewForm.review_level" placeholder="选择复核级别" style="width: 100%">
            <el-option label="一级复核（经理）" :value="2" />
            <el-option label="二级复核（合伙人）" :value="3" />
          </el-select>
        </el-form-item>
        <el-form-item label="意见内容" required>
          <el-input
            v-model="reviewForm.comments"
            type="textarea"
            :rows="4"
            placeholder="请输入复核意见..."
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitReview">提交</el-button>
      </template>
    </el-dialog>

    <!-- 回复对话框 -->
    <el-dialog append-to-body v-model="replyDialogVisible" title="编制人回复" width="500px">
      <div v-if="selectedReview" class="reply-section">
        <p class="reply-label">复核意见：</p>
        <p class="reply-content">{{ selectedReview.comments }}</p>
        <el-divider />
        <p class="reply-label">回复内容：</p>
        <el-input
          v-model="replyForm.response_content"
          type="textarea"
          :rows="3"
          placeholder="请输入回复..."
        />
      </div>
      <template #footer>
        <el-button @click="replyDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitReply">提交回复</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { reviewApi } from '@/services/collaborationApi'

interface ReviewRecord {
  id: string
  workpaper_id: string
  project_id: string
  reviewer_id?: string
  review_level: number
  review_status: string
  comments?: string
  reply_text?: string
  created_at: string
  updated_at: string
}

const props = defineProps<{
  workpaperId: string
  projectId: string
}>()

const reviews = ref<ReviewRecord[]>([])
const createDialogVisible = ref(false)
const replyDialogVisible = ref(false)
const selectedReview = ref<ReviewRecord | null>(null)

const reviewForm = ref({
  review_level: 2 as number,
  comments: '',
})

const replyForm = ref({
  response_content: '',
})

// 未解决意见置顶排序
const sortedReviews = computed(() => {
  return [...reviews.value].sort((a, b) => {
    const aUnresolved = a.review_status !== 'approved' ? 0 : 1
    const bUnresolved = b.review_status !== 'approved' ? 0 : 1
    if (aUnresolved !== bUnresolved) return aUnresolved - bUnresolved
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
})

// 时间线数据（从复核记录生成）
const timelineItems = computed(() => {
  return reviews.value
    .filter(r => r.review_status === 'approved' || r.review_status === 'rejected')
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
})

function levelName(level: number): string {
  const names: Record<number, string> = {
    1: '审计自复',
    2: '一级复核',
    3: '二级复核',
  }
  return names[level] || `L${level}`
}

function levelTagType(level: number): 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const types: Record<number, 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    1: 'info',
    2: 'warning',
    3: 'danger',
  }
  return types[level] || 'info'
}

function statusName(status: string): string {
  const names: Record<string, string> = {
    draft: '草稿',
    pending_review: '待复核',
    approved: '已通过',
    rejected: '已退回',
    resolved: '已解决',
  }
  return names[status] || status
}

function statusTagType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const types: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    draft: 'info',
    pending_review: 'warning',
    approved: 'success',
    rejected: 'danger',
    resolved: 'success',
  }
  return types[status] || 'info'
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function loadReviews() {
  try {
    const { data } = await reviewApi.list(props.workpaperId)
    reviews.value = data || []
  } catch (e) {
    console.error('加载复核记录失败', e)
    ElMessage.error('加载复核记录失败')
  }
}

function openCreateDialog() {
  reviewForm.value = { review_level: 2, comments: '' }
  createDialogVisible.value = true
}

async function submitReview() {
  if (!reviewForm.value.comments.trim()) {
    ElMessage.warning('请填写复核意见')
    return
  }
  try {
    await reviewApi.create({
      workpaper_id: props.workpaperId,
      project_id: props.projectId,
      review_level: reviewForm.value.review_level,
    } as any)
    ElMessage.success('复核意见已提交')
    createDialogVisible.value = false
    await loadReviews()
  } catch (e) {
    console.error('提交复核意见失败', e)
    ElMessage.error('提交失败')
  }
}

function showReply(row: ReviewRecord) {
  selectedReview.value = row
  replyForm.value.response_content = row.reply_text || ''
  replyDialogVisible.value = true
}

async function submitReply() {
  if (!selectedReview.value) return
  try {
    await (reviewApi as any).respondToReview(
      selectedReview.value.id,
      { response_content: replyForm.value.response_content }
    )
    ElMessage.success('回复已提交')
    replyDialogVisible.value = false
    await loadReviews()
  } catch (e) {
    console.error('提交回复失败', e)
    ElMessage.error('提交回复失败')
  }
}

onMounted(() => {
  loadReviews()
})
</script>

<style scoped>
.gt-review-panel {
  padding: 12px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.review-table {
  margin-bottom: 16px;
}

.timeline-section {
  margin-top: 16px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 12px;
}

.timeline-level {
  font-weight: 600;
  margin: 0 0 4px;
  color: #409eff;
}

.timeline-status {
  margin: 0 0 4px;
  color: #909399;
  font-size: 12px;
}

.timeline-comment {
  margin: 4px 0 0;
  color: #606266;
  font-size: 13px;
}

.timeline-reply {
  margin: 8px 0 0;
  color: #67c23a;
  font-size: 13px;
}

.reply-section {
  padding: 8px 0;
}

.reply-label {
  font-size: 13px;
  color: #909399;
  margin: 0 0 8px;
}

.reply-content {
  color: #303133;
  margin: 0 0 12px;
  line-height: 1.6;
}
</style>
