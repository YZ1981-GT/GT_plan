<template>
  <div class="review-workstation">
    <div class="gt-page-banner gt-page-banner--purple">
      <h2>复核工作台</h2>
      <p>AI预审辅助 · 连续复核多张底稿</p>
    </div>
    <div class="workstation-body">
      <!-- 左栏：待复核队列 -->
      <div class="queue-panel">
        <h3>待复核队列 <el-badge :value="queue.length" type="warning" /></h3>
        <el-input v-model="searchKw" placeholder="搜索底稿编号/名称" clearable size="small" style="margin-bottom:8px" />
        <div v-for="item in filteredQueue" :key="item.id"
             class="queue-item" :class="{ active: selectedWpId === item.id }"
             @click="selectWp(item)">
          <span class="wp-code">{{ item.wp_code }}</span>
          <span class="wp-name">{{ item.wp_name }}</span>
          <el-tag size="small" :type="item.is_resubmit ? 'warning' : 'info'">
            {{ item.is_resubmit ? '退回重提' : '首次提交' }}
          </el-tag>
        </div>
        <el-empty v-if="!filteredQueue.length" description="暂无待复核底稿" />
      </div>

      <!-- 中栏：底稿预览 -->
      <div class="preview-panel">
        <template v-if="selectedWp">
          <h3>{{ selectedWp.wp_code }} — {{ selectedWp.wp_name }}</h3>
          <div class="data-cards">
            <div class="data-card">
              <label>审定数</label>
              <span :class="{ 'text-danger': selectedWp.has_diff }">
                {{ formatAmount(selectedWp.audited_amount) }}
              </span>
            </div>
            <div class="data-card">
              <label>审计说明</label>
              <span>{{ selectedWp.explanation_preview || '—' }}</span>
            </div>
          </div>
        </template>
        <el-empty v-else description="选择左侧底稿查看预览" />
      </div>

      <!-- 右栏：AI预审 + 复核操作 -->
      <div class="review-panel">
        <template v-if="selectedWpId">
          <h3>AI预审结果</h3>
          <div v-if="aiLoading" class="ai-loading">
            <el-icon class="is-loading"><Loading /></el-icon> 正在预审...
          </div>
          <div v-for="(issue, idx) in aiIssues" :key="idx" class="ai-issue"
               :class="issue.severity">
            <el-icon><WarningFilled /></el-icon>
            <span>{{ issue.description }}</span>
            <small v-if="issue.suggested_action">建议：{{ issue.suggested_action }}</small>
          </div>
          <el-divider />
          <h3>复核意见</h3>
          <el-input v-model="reviewComment" type="textarea" :rows="3" placeholder="输入复核意见..." />
          <div class="review-actions">
            <el-button type="success" @click="approveWp" :disabled="hasBlocking">
              通过 <small>(Ctrl+Enter)</small>
            </el-button>
            <el-button type="danger" @click="rejectWp">
              退回 <small>(Ctrl+Shift+Enter)</small>
            </el-button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { Loading, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import * as workpaperApi from '@/services/workpaperApi'
import { fmtAmount } from '@/utils/formatters'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)

const queue = ref<any[]>([])
const searchKw = ref('')
const selectedWpId = ref('')
const selectedWp = ref<any>(null)
const aiIssues = ref<workpaperApi.ReviewIssue[]>([])
const aiLoading = ref(false)
const reviewComment = ref('')

const filteredQueue = computed(() => {
  if (!searchKw.value) return queue.value
  const kw = searchKw.value.toLowerCase()
  return queue.value.filter(q => q.wp_code?.toLowerCase().includes(kw) || q.wp_name?.toLowerCase().includes(kw))
})

const hasBlocking = computed(() => aiIssues.value.some(i => i.severity === 'blocking'))

const formatAmount = fmtAmount

async function loadQueue() {
  try {
    const wps = await workpaperApi.listWorkpapers(projectId.value, { status: 'under_review' })
    queue.value = (Array.isArray(wps) ? wps : []).map((w: any) => ({
      id: w.id, wp_code: w.wp_code || w.index_code, wp_name: w.wp_name || w.index_name,
      is_resubmit: w.review_status === 'level1_rejected' || w.review_status === 'level2_rejected',
      audited_amount: w.parsed_data?.audited_amount,
      explanation_preview: (w.parsed_data?.audit_explanation || '').slice(0, 100),
      has_diff: w.consistency_status === 'inconsistent',
    }))
  } catch { queue.value = [] }
}

async function selectWp(item: any) {
  selectedWpId.value = item.id
  selectedWp.value = item
  aiLoading.value = true
  aiIssues.value = []
  try {
    const res = await workpaperApi.reviewContent(projectId.value, item.id)
    aiIssues.value = res.issues || []
  } catch { /* silent */ }
  aiLoading.value = false
}

async function approveWp() {
  try {
    await workpaperApi.updateReviewStatus(projectId.value, selectedWpId.value, 'level1_passed')
    ElMessage.success('复核通过')
    queue.value = queue.value.filter(q => q.id !== selectedWpId.value)
    selectedWpId.value = ''
    selectedWp.value = null
  } catch (e: any) { ElMessage.error(e.message || '操作失败') }
}

async function rejectWp() {
  try {
    await workpaperApi.updateReviewStatus(projectId.value, selectedWpId.value, 'level1_rejected', reviewComment.value)
    ElMessage.warning('已退回修改')
    queue.value = queue.value.filter(q => q.id !== selectedWpId.value)
    selectedWpId.value = ''
    selectedWp.value = null
    reviewComment.value = ''
  } catch (e: any) { ElMessage.error(e.message || '操作失败') }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.shiftKey && e.key === 'Enter') { rejectWp(); e.preventDefault() }
  else if (e.ctrlKey && e.key === 'Enter') { if (!hasBlocking.value) approveWp(); e.preventDefault() }
}

onMounted(() => { loadQueue(); document.addEventListener('keydown', handleKeydown) })
onUnmounted(() => { document.removeEventListener('keydown', handleKeydown) })
</script>

<style scoped>
.review-workstation { padding: 16px; }
.workstation-body { display: flex; gap: 12px; min-height: 600px; }
.queue-panel { width: 260px; flex-shrink: 0; border-right: 1px solid var(--el-border-color-lighter); padding-right: 12px; }
.preview-panel { flex: 1; padding: 0 12px; }
.review-panel { width: 320px; flex-shrink: 0; border-left: 1px solid var(--el-border-color-lighter); padding-left: 12px; }
.queue-item { padding: 8px; cursor: pointer; border-radius: 6px; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }
.queue-item:hover { background: var(--el-fill-color-light); }
.queue-item.active { background: var(--gt-primary-lighter, #f0ebf8); }
.wp-code { font-weight: 600; font-size: 13px; }
.wp-name { flex: 1; font-size: 12px; color: var(--el-text-color-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.data-cards { display: flex; gap: 12px; margin: 12px 0; }
.data-card { background: var(--el-fill-color-lighter); padding: 12px; border-radius: 8px; flex: 1; }
.data-card label { display: block; font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.text-danger { color: var(--el-color-danger); font-weight: 600; }
.ai-issue { padding: 6px 8px; margin-bottom: 6px; border-radius: 6px; display: flex; align-items: flex-start; gap: 6px; font-size: 13px; }
.ai-issue.warning { background: #fff8e6; }
.ai-issue.blocking { background: #fef0f0; }
.ai-issue small { display: block; color: var(--el-text-color-secondary); font-size: 11px; }
.review-actions { display: flex; gap: 8px; margin-top: 12px; }
.ai-loading { text-align: center; padding: 20px; color: var(--el-text-color-secondary); }
</style>
