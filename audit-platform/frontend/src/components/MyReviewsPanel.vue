<template>
  <div class="my-reviews-panel">
    <!-- 统计摘要卡片 -->
    <div class="summary-cards">
      <div class="summary-card must-fix">
        <span class="count">{{ summary.must_fix }}</span>
        <span class="label">必须修改</span>
      </div>
      <div class="summary-card suggest">
        <span class="count">{{ summary.suggest }}</span>
        <span class="label">建议修改</span>
      </div>
      <div class="summary-card info">
        <span class="count">{{ summary.info }}</span>
        <span class="label">仅供参考</span>
      </div>
    </div>

    <!-- 批注列表 -->
    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="5" animated />
    </div>
    <div v-else-if="items.length === 0" class="empty-state">
      <el-empty description="暂无待回复批注" />
    </div>
    <div v-else class="review-list">
      <div
        v-for="item in items"
        :key="item.review_id"
        class="review-item"
        :class="'priority-' + item.priority"
        @click="handleNavigate(item)"
      >
        <div class="review-header">
          <el-tag
            :type="priorityTagType(item.priority)"
            size="small"
            effect="dark"
          >
            {{ priorityLabel(item.priority) }}
          </el-tag>
          <span class="wp-code">{{ item.wp_code }}</span>
          <span class="wp-name">{{ item.wp_name }}</span>
        </div>
        <div class="review-body">
          <p class="comment-text">{{ item.comment_text }}</p>
          <div class="review-meta">
            <span class="commenter">{{ item.commenter_name }}</span>
            <span v-if="item.cell_reference" class="cell-ref">{{ item.cell_reference }}</span>
            <span class="time">{{ formatTime(item.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import http from '@/utils/http'

interface ReviewItem {
  review_id: string
  wp_code: string
  wp_name: string
  wp_id: string
  cell_reference: string | null
  comment_text: string
  commenter_name: string
  priority: string
  created_at: string | null
}

interface Summary {
  must_fix: number
  suggest: number
  info: number
  total: number
}

const props = defineProps<{
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'navigate', payload: { wpId: string; cellRef: string }): void
}>()

const items = ref<ReviewItem[]>([])
const summary = ref<Summary>({ must_fix: 0, suggest: 0, info: 0, total: 0 })
const loading = ref(false)

async function fetchReviews() {
  if (!props.projectId) return
  loading.value = true
  try {
    const resp = await http.get(`/api/projects/${props.projectId}/my-reviews`, {
      params: { status: 'open' },
    })
    items.value = resp.data.items
    summary.value = resp.data.summary
  } catch (err) {
    console.warn('[MyReviewsPanel] 获取批注失败', err)
  } finally {
    loading.value = false
  }
}

function handleNavigate(item: ReviewItem) {
  emit('navigate', {
    wpId: item.wp_id,
    cellRef: item.cell_reference || '',
  })
}

function priorityTagType(priority: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' | undefined {
  switch (priority) {
    case 'must_fix': return 'danger'
    case 'suggest': return 'warning'
    case 'info': return 'info'
    default: return undefined
  }
}

function priorityLabel(priority: string): string {
  switch (priority) {
    case 'must_fix': return '必须修改'
    case 'suggest': return '建议修改'
    case 'info': return '仅供参考'
    default: return priority
  }
}

function formatTime(isoStr: string | null): string {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

watch(() => props.projectId, () => fetchReviews())
onMounted(() => fetchReviews())
</script>

<style scoped>
.my-reviews-panel {
  padding: 16px;
}

.summary-cards {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.summary-card {
  flex: 1;
  padding: 12px 16px;
  border-radius: 8px;
  text-align: center;
}

.summary-card .count {
  display: block;
  font-size: 24px;
  font-weight: 600;
}

.summary-card .label {
  font-size: 12px;
  color: #666;
}

.summary-card.must-fix {
  background: #fef0f0;
  color: #f56c6c;
}

.summary-card.suggest {
  background: #fdf6ec;
  color: #e6a23c;
}

.summary-card.info {
  background: #f4f4f5;
  color: #909399;
}

.review-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.review-item {
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.review-item:hover {
  background: #f5f7fa;
}

.review-item.priority-must_fix {
  border-left: 3px solid #f56c6c;
}

.review-item.priority-suggest {
  border-left: 3px solid #e6a23c;
}

.review-item.priority-info {
  border-left: 3px solid #909399;
}

.review-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.wp-code {
  font-weight: 500;
  font-size: 13px;
}

.wp-name {
  color: #666;
  font-size: 12px;
}

.comment-text {
  margin: 0 0 6px;
  font-size: 13px;
  line-height: 1.5;
  color: #303133;
}

.review-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #909399;
}

.cell-ref {
  font-family: 'Arial Narrow', monospace;
}

.loading-state,
.empty-state {
  padding: 40px 0;
  text-align: center;
}
</style>
