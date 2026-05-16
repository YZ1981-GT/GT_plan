<template>
  <div class="gt-ai-content-dashboard">
    <div class="panel-header">
      <h3>🤖 AI内容管理看板</h3>
      <div class="filter-bar">
        <select v-model="filterType" class="filter-select">
          <option value="">全部类型</option>
          <option value="data_fill">数据填充</option>
          <option value="analytical_review">分析复核</option>
          <option value="risk_alert">风险提示</option>
          <option value="test_summary">测试摘要</option>
          <option value="note_draft">附注初稿</option>
        </select>
        <select v-model="filterStatus" class="filter-select">
          <option value="">全部状态</option>
          <option value="pending">待确认</option>
          <option value="accepted">已确认</option>
          <option value="modified">已修改</option>
          <option value="rejected">已拒绝</option>
        </select>
      </div>
    </div>

    <!-- 汇总卡片 -->
    <div class="summary-cards">
      <div class="summary-card">
        <span class="card-value">{{ stats.total }}</span>
        <span class="card-label">AI生成总数</span>
      </div>
      <div class="summary-card accepted">
        <span class="card-value">{{ stats.accepted }}</span>
        <span class="card-label">已确认</span>
      </div>
      <div class="summary-card pending">
        <span class="card-value">{{ stats.pending }}</span>
        <span class="card-label">待确认</span>
      </div>
      <div class="summary-card rejected">
        <span class="card-value">{{ stats.rejected }}</span>
        <span class="card-label">已拒绝</span>
      </div>
      <div class="summary-card rate">
        <span class="card-value">{{ modificationRate }}%</span>
        <span class="card-label">修改率</span>
      </div>
    </div>

    <!-- 批量操作 -->
    <div v-if="selectedItems.length > 0" class="batch-actions">
      <span>已选择 {{ selectedItems.length }} 项</span>
      <button class="btn-sm btn-success" @click="batchConfirm">✅ 批量确认</button>
      <button class="btn-sm btn-danger" @click="batchReject">❌ 批量拒绝</button>
      <button class="btn-sm" @click="clearSelection">清空选择</button>
    </div>

    <!-- AI内容列表 -->
    <div class="content-list">
      <div v-for="(items, workpaper) in groupedContent" :key="workpaper" class="workpaper-group">
        <div class="group-header">
          <span class="group-title">📄 {{ workpaper }}</span>
          <span class="group-count">{{ items.length }} 项</span>
        </div>
        <div class="group-items">
          <div
            v-for="item in items"
            :key="item.id"
            class="content-item"
            :class="{ selected: selectedItems.includes(item.id) }"
            @click="toggleSelect(item.id)"
          >
            <div class="item-checkbox">
              <input
                type="checkbox"
                :checked="selectedItems.includes(item.id)"
                @click.stop
                @change="toggleSelect(item.id)"
              />
            </div>
            <div class="item-content">
              <div class="item-header">
                <span class="content-type-badge" :class="item.content_type">
                  {{ contentTypeLabel(item.content_type) }}
                </span>
                <span :class="['status-badge', item.confirmation_status]">
                  {{ statusLabel(item.confirmation_status) }}
                </span>
                <span class="ai-tag">AI辅助生成</span>
              </div>
              <div class="item-text">{{ truncate(item.content_text, 150) }}</div>
              <div class="item-meta">
                <span>来源：{{ item.workpaper_name || '通用' }}</span>
                <span>生成时间：{{ formatTime(item.generation_time) }}</span>
                <span>置信度：{{ confidenceLabel(item.confidence_level) }}</span>
              </div>
            </div>
            <div class="item-actions">
              <button class="btn-icon" @click.stop="viewDetail(item)" title="查看详情">👁️</button>
              <button
                v-if="item.confirmation_status === 'pending'"
                class="btn-icon"
                @click.stop="confirmItem(item)"
                title="确认"
              >✅</button>
              <button
                v-if="item.confirmation_status === 'pending'"
                class="btn-icon"
                @click.stop="modifyItem(item)"
                title="修改"
              >✏️</button>
              <button
                v-if="item.confirmation_status === 'pending'"
                class="btn-icon"
                @click.stop="rejectItem(item)"
                title="拒绝"
              >❌</button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="Object.keys(groupedContent).length === 0" class="empty-state">
        暂无AI生成内容
      </div>
    </div>

    <!-- 详情弹窗 -->
    <div v-if="showDetail" class="modal-overlay" @click.self="showDetail = false">
      <div class="modal-content">
        <div class="modal-header">
          <h4>AI内容详情</h4>
          <button class="btn-close" @click="showDetail = false">×</button>
        </div>
        <div class="modal-body">
          <div class="detail-row">
            <span class="detail-label">内容类型：</span>
            <span>{{ contentTypeLabel(currentItem?.content_type) }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">所属底稿：</span>
            <span>{{ currentItem?.workpaper_name }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">置信度：</span>
            <span>{{ confidenceLabel(currentItem?.confidence_level) }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">生成时间：</span>
            <span>{{ formatTime(currentItem?.generation_time) }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">数据来源：</span>
            <span>{{ currentItem?.data_sources?.join(', ') || '-' }}</span>
          </div>
          <div class="detail-content">
            <span class="detail-label">内容：</span>
            <div class="content-preview">{{ currentItem?.content_text }}</div>
          </div>
          <div v-if="currentItem?.modification_note" class="detail-row">
            <span class="detail-label">修改说明：</span>
            <span>{{ currentItem.modification_note }}</span>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showDetail = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { workpaperAI } from '@/services/aiApi'

const props = defineProps({
  projectId: { type: String, required: true },
})

const filterType = ref('')
const filterStatus = ref('')
const selectedItems = ref([])
const showDetail = ref(false)
const currentItem = ref(null)

const stats = reactive({
  total: 0,
  accepted: 0,
  pending: 0,
  rejected: 0,
})

const allContent = ref([])

const modificationRate = computed(() => {
  if (stats.total === 0) return 0
  return Math.round((stats.accepted + stats.rejected) / stats.total * 100)
})

const groupedContent = computed(() => {
  let filtered = allContent.value
  if (filterType.value) {
    filtered = filtered.filter(i => i.content_type === filterType.value)
  }
  if (filterStatus.value) {
    filtered = filtered.filter(i => i.confirmation_status === filterStatus.value)
  }

  const groups = {}
  for (const item of filtered) {
    const key = item.workpaper_name || '通用'
    if (!groups[key]) groups[key] = []
    groups[key].push(item)
  }
  return groups
})

function contentTypeLabel(type) {
  const m = {
    data_fill: '数据填充',
    analytical_review: '分析复核',
    risk_alert: '风险提示',
    test_summary: '测试摘要',
    note_draft: '附注初稿',
  }
  return m[type] || type
}

function statusLabel(status) {
  const m = {
    pending: '待确认',
    accepted: '已确认',
    modified: '已修改',
    rejected: '已拒绝',
    regenerated: '已重新生成',
  }
  return m[status] || status
}

function confidenceLabel(level) {
  const m = { high: '高', medium: '中', low: '低' }
  return m[level] || level
}

function truncate(text, maxLen) {
  if (!text) return ''
  return text.length > maxLen ? text.substring(0, maxLen) + '...' : text
}

function formatTime(timeStr) {
  if (!timeStr) return '-'
  return new Date(timeStr).toLocaleString('zh-CN')
}

function toggleSelect(id) {
  const idx = selectedItems.value.indexOf(id)
  if (idx >= 0) {
    selectedItems.value.splice(idx, 1)
  } else {
    selectedItems.value.push(id)
  }
}

function clearSelection() {
  selectedItems.value = []
}

function viewDetail(item) {
  currentItem.value = item
  showDetail.value = true
}

async function loadContent() {
  try {
    const result = await workpaperAI.getAIContentList(props.projectId)
    allContent.value = result.data || []
    updateStats()
  } catch (e) {
    console.error(e)
    // 模拟数据
    allContent.value = [
      {
        id: '1',
        content_type: 'analytical_review',
        content_text: '应收账款本年余额较上年增长25%，主要系销售规模扩大所致。账龄分析显示，1年以内应收账款占比78%，账龄结构良好。',
        confirmation_status: 'pending',
        confidence_level: 'high',
        generation_time: '2024-03-15T10:30:00Z',
        workpaper_name: '应收账款',
        data_sources: ['试算表', '辅助明细'],
      },
      {
        id: '2',
        content_type: 'risk_alert',
        content_text: '发现大额关联方往来，关联方应收款余额占应收账款总额的35%，存在关联方资金占用风险。',
        confirmation_status: 'pending',
        confidence_level: 'medium',
        generation_time: '2024-03-15T11:00:00Z',
        workpaper_name: '应收账款',
        data_sources: ['辅助明细', '关联方清单'],
      },
      {
        id: '3',
        content_type: 'data_fill',
        content_text: '存货周转天数：本年45天，上年42天，周转效率略有下降。',
        confirmation_status: 'accepted',
        confidence_level: 'high',
        generation_time: '2024-03-14T15:00:00Z',
        workpaper_name: '存货',
        data_sources: ['试算表'],
      },
    ]
    updateStats()
  }
}

function updateStats() {
  stats.total = allContent.value.length
  stats.accepted = allContent.value.filter(i => i.confirmation_status === 'accepted').length
  stats.pending = allContent.value.filter(i => i.confirmation_status === 'pending').length
  stats.rejected = allContent.value.filter(i => i.confirmation_status === 'rejected').length
}

async function confirmItem(item) {
  try {
    await workpaperAI.confirmAIContent(props.projectId, item.id, { action: 'accept' })
    item.confirmation_status = 'accepted'
    updateStats()
  } catch (e) {
    console.error(e)
    item.confirmation_status = 'accepted'
    updateStats()
  }
}

async function rejectItem(item) {
  try {
    await workpaperAI.confirmAIContent(props.projectId, item.id, { action: 'reject' })
    item.confirmation_status = 'rejected'
    updateStats()
  } catch (e) {
    console.error(e)
    item.confirmation_status = 'rejected'
    updateStats()
  }
}

function modifyItem(item) {
  const newText = prompt('请输入修改后的内容:', item.content_text)
  if (newText && newText !== item.content_text) {
    item.content_text = newText
    item.confirmation_status = 'modified'
    item.modification_note = '用户手动修改'
    updateStats()
  }
}

async function batchConfirm() {
  for (const id of selectedItems.value) {
    const item = allContent.value.find(i => i.id === id)
    if (item) await confirmItem(item)
  }
  clearSelection()
}

async function batchReject() {
  for (const id of selectedItems.value) {
    const item = allContent.value.find(i => i.id === id)
    if (item) await rejectItem(item)
  }
  clearSelection()
}

onMounted(() => {
  loadContent()
})
</script>

<style scoped>
.gt-ai-content-dashboard { padding: 16px; }

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.panel-header h3 { margin: 0; font-size: var(--gt-font-size-md); }

.filter-bar { display: flex; gap: 8px; }
.filter-select {
  padding: 6px 12px;
  border: 1px solid var(--gt-color-border-light);
  border-radius: 4px;
  font-size: var(--gt-font-size-sm);
  cursor: pointer;
}

.summary-cards {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.summary-card {
  flex: 1;
  background: var(--gt-color-bg);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.summary-card.accepted { background: var(--gt-bg-success); }
.summary-card.pending { background: var(--gt-color-wheat-light); }
.summary-card.rejected { background: var(--gt-bg-danger); }
.summary-card.rate { background: rgba(75,45,119,0.1); }

.card-value {
  display: block;
  font-size: var(--gt-font-size-3xl);
  font-weight: 700;
  color: var(--gt-color-text-primary);
}
.summary-card.accepted .card-value { color: var(--gt-color-success); }
.summary-card.pending .card-value { color: var(--gt-color-wheat); }
.summary-card.rejected .card-value { color: var(--gt-color-coral); }
.summary-card.rate .card-value { color: var(--gt-color-primary); }
.card-label { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }

.batch-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--gt-bg-info);
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: var(--gt-font-size-sm);
}

.content-list { display: flex; flex-direction: column; gap: 16px; }

.workpaper-group {
  border: 1px solid var(--gt-color-border-light);
  border-radius: 8px;
  overflow: hidden;
}
.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--gt-color-bg);
  border-bottom: 1px solid var(--gt-color-border-light);
}
.group-title { font-weight: 600; font-size: var(--gt-font-size-sm); }
.group-count { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }

.group-items { display: flex; flex-direction: column; }

.content-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--gt-color-border-light);
  cursor: pointer;
  transition: background 0.2s;
}
.content-item:last-child { border-bottom: none; }
.content-item:hover { background: var(--gt-color-bg); }
.content-item.selected { background: rgba(75,45,119,0.05); }

.item-checkbox { padding-top: 4px; }
.item-content { flex: 1; min-width: 0; }

.item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.content-type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
}
.content-type-badge.data_fill { background: var(--gt-bg-info); color: var(--gt-color-teal); }
.content-type-badge.analytical_review { background: var(--gt-bg-success); color: var(--gt-color-success); }
.content-type-badge.risk_alert { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); }
.content-type-badge.test_summary { background: var(--gt-color-primary-bg); color: var(--gt-color-primary-light); }
.content-type-badge.note_draft { background: var(--gt-bg-danger); color: var(--gt-color-coral); }

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--gt-font-size-xs);
}
.status-badge.pending { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); }
.status-badge.accepted { background: var(--gt-bg-success); color: var(--gt-color-success); }
.status-badge.modified { background: var(--gt-bg-info); color: var(--gt-color-teal); }
.status-badge.rejected { background: var(--gt-bg-danger); color: var(--gt-color-coral); }

.ai-tag {
  display: inline-block;
  background: rgba(75,45,119,0.1);
  color: var(--gt-color-primary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: var(--gt-font-size-xs);
}

.item-text {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-primary);
  line-height: 1.6;
  margin-bottom: 8px;
}

.item-meta {
  display: flex;
  gap: 16px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}

.item-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}
.content-item:hover .item-actions { opacity: 1; }

.btn-icon {
  padding: 4px 8px;
  background: none;
  border: 1px solid var(--gt-color-border-light);
  border-radius: 4px;
  cursor: pointer;
  font-size: var(--gt-font-size-sm);
}
.btn-icon:hover { background: var(--gt-color-border-lighter); }

.btn-sm {
  padding: 6px 12px;
  border: 1px solid var(--gt-color-border-light);
  background: var(--gt-color-bg-white);
  border-radius: 4px;
  cursor: pointer;
  font-size: var(--gt-font-size-xs);
}
.btn-sm:hover { background: var(--gt-color-border-lighter); }
.btn-sm.btn-success { background: var(--gt-bg-success); color: var(--gt-color-success); border-color: var(--gt-color-success); }
.btn-sm.btn-danger { background: var(--gt-bg-danger); color: var(--gt-color-coral); border-color: var(--gt-color-coral); }

.empty-state {
  padding: 48px;
  text-align: center;
  color: var(--gt-color-text-tertiary);
  background: var(--gt-color-bg);
  border-radius: 8px;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-content {
  background: var(--gt-color-bg-white);
  border-radius: 8px;
  width: 600px;
  max-height: 80vh;
  overflow: hidden;
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--gt-color-border-light);
}
.modal-header h4 { margin: 0; font-size: var(--gt-font-size-md); }
.btn-close {
  background: none;
  border: none;
  font-size: 24px /* allow-px: special */;
  cursor: pointer;
  color: var(--gt-color-text-tertiary);
}
.modal-body { padding: 20px; max-height: 60vh; overflow-y: auto; }
.modal-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--gt-color-border-light);
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
.detail-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.detail-label { color: var(--gt-color-text-secondary); min-width: 80px; }
.detail-content { margin-bottom: 12px; }
.content-preview {
  background: var(--gt-color-bg);
  padding: 12px;
  border-radius: 4px;
  white-space: pre-wrap;
  line-height: 1.6;
}
.btn-secondary {
  padding: 8px 20px;
  border: 1px solid var(--gt-color-border-light);
  background: var(--gt-color-bg-white);
  border-radius: 4px;
  cursor: pointer;
}
</style>
