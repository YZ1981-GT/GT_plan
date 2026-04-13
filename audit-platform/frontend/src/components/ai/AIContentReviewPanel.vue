<template>
  <div class="gt-ai-content-review-panel">
    <div class="panel-header">
      <h3>🤖 AI内容审核确认</h3>
      <div class="filter-bar">
        <select v-model="filterWorkpaper" class="filter-select">
          <option value="">全部底稿</option>
          <option v-for="wp in workpaperOptions" :key="wp.id" :value="wp.id">
            {{ wp.name }}
          </option>
        </select>
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

    <!-- 统计卡片 -->
    <div class="stats-bar">
      <div class="stat-item">
        <span class="stat-value">{{ stats.total }}</span>
        <span class="stat-label">总计</span>
      </div>
      <div class="stat-item pending">
        <span class="stat-value">{{ stats.pending }}</span>
        <span class="stat-label">待确认</span>
      </div>
      <div class="stat-item confirmed">
        <span class="stat-value">{{ stats.confirmed }}</span>
        <span class="stat-label">已确认</span>
      </div>
      <div class="stat-item rejected">
        <span class="stat-value">{{ stats.rejected }}</span>
        <span class="stat-label">已拒绝</span>
      </div>
      <div class="stat-item modified">
        <span class="stat-value">{{ stats.modified }}</span>
        <span class="stat-label">已修改</span>
      </div>
    </div>

    <!-- 按底稿分组的内容 -->
    <div class="content-groups">
      <div
        v-for="(items, workpaperName) in groupedContent"
        :key="workpaperName"
        class="workpaper-group"
      >
        <div class="group-header" @click="toggleGroup(workpaperName)">
          <span class="group-toggle">{{ expandedGroups[workpaperName] ? '▼' : '▶' }}</span>
          <span class="group-title">📄 {{ workpaperName }}</span>
          <span class="group-badge">{{ items.length }}</span>
          <span class="group-pending" v-if="pendingCount(items) > 0">
            {{ pendingCount(items) }} 待确认
          </span>
        </div>

        <div v-if="expandedGroups[workpaperName]" class="group-items">
          <!-- 按内容类型分 Tab -->
          <div class="type-tabs">
            <button
              v-for="type in contentTypeOptions"
              :key="type.value"
              :class="['type-tab', { active: activeTypes[workpaperName] === type.value }]"
              @click="setActiveType(workpaperName, type.value)"
            >
              {{ type.label }}
              <span class="type-count">{{ countByType(items, type.value) }}</span>
            </button>
          </div>

          <div class="items-list">
            <div
              v-for="item in filteredItems(items, workpaperName)"
              :key="item.id"
              class="content-card"
              :class="[`status-${item.confirmation_status}`, { editing: editingId === item.id }]"
            >
              <!-- 卡片头部 -->
              <div class="card-header">
                <div class="card-badges">
                  <span class="type-badge" :class="item.content_type">
                    {{ contentTypeLabel(item.content_type) }}
                  </span>
                  <span class="confidence-badge" :class="confidenceClass(item.confidence_level)">
                    置信度：{{ confidenceLabel(item.confidence_level) }}
                  </span>
                  <span v-if="isLowConfidence(item)" class="low-confidence-tag">⚠️ 低置信度</span>
                  <span class="ai-tag">AI辅助-待确认</span>
                </div>
                <div class="card-meta">
                  <span class="meta-time">{{ formatTime(item.generation_time) }}</span>
                  <span :class="['status-tag', item.confirmation_status]">
                    {{ statusLabel(item.confirmation_status) }}
                  </span>
                </div>
              </div>

              <!-- 内容预览（可编辑） -->
              <div class="card-body">
                <div v-if="editingId !== item.id" class="content-text" @click="startEdit(item)">
                  {{ truncate(item.content_text, 300) }}
                  <span v-if="item.content_text.length > 300" class="expand-hint">点击展开编辑</span>
                </div>
                <div v-else class="content-editor">
                  <textarea
                    v-model="editText"
                    class="edit-textarea"
                    rows="6"
                    placeholder="请输入修改后的内容..."
                  ></textarea>
                  <div class="edit-actions">
                    <button class="btn-save" @click="saveEdit(item)">💾 保存</button>
                    <button class="btn-cancel-edit" @click="cancelEdit">取消</button>
                  </div>
                </div>
              </div>

              <!-- 数据来源 -->
              <div v-if="item.data_sources && item.data_sources.length" class="card-sources">
                <span class="sources-label">📚 数据来源：</span>
                <span v-for="(src, idx) in item.data_sources" :key="idx" class="source-tag">
                  {{ src }}
                </span>
              </div>

              <!-- 操作按钮 -->
              <div class="card-actions" v-if="editingId !== item.id">
                <button
                  v-if="item.confirmation_status === 'pending'"
                  class="btn-confirm-action"
                  @click="confirmItem(item)"
                  title="确认"
                >
                  ✅ 确认
                </button>
                <button
                  v-if="item.confirmation_status === 'pending'"
                  class="btn-edit-action"
                  @click="startEdit(item)"
                  title="修改"
                >
                  ✏️ 修改
                </button>
                <button
                  v-if="item.confirmation_status === 'pending'"
                  class="btn-reject-action"
                  @click="rejectItem(item)"
                  title="拒绝"
                >
                  ❌ 拒绝
                </button>
                <button
                  v-if="item.confirmation_status === 'pending'"
                  class="btn-regenerate-action"
                  @click="regenerateItem(item)"
                  title="重新生成"
                >
                  🔄 重新生成
                </button>
                <span v-if="item.confirmation_status !== 'pending'" class="action-done">
                  已处理
                </span>
              </div>

              <!-- 拒绝原因弹窗 -->
              <div v-if="rejectingId === item.id" class="reject-dialog">
                <div class="reject-reason">
                  <label>拒绝原因：</label>
                  <textarea
                    v-model="rejectReason"
                    rows="3"
                    placeholder="请输入拒绝原因（可选）..."
                    class="reason-textarea"
                  ></textarea>
                </div>
                <div class="reject-actions">
                  <button class="btn-confirm-reject" @click="submitReject(item)">确认拒绝</button>
                  <button class="btn-cancel-reject" @click="cancelReject">取消</button>
                </div>
              </div>
            </div>

            <div v-if="filteredItems(items, workpaperName).length === 0" class="empty-type">
              该类型暂无内容
            </div>
          </div>
        </div>
      </div>

      <div v-if="Object.keys(groupedContent).length === 0" class="empty-state">
        暂无AI生成内容
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

// ─── Filters ───
const filterWorkpaper = ref('')
const filterType = ref('')
const filterStatus = ref('')

// ─── Data ───
const allContent = ref([])
const workpaperOptions = ref([])

// ─── Stats ───
const stats = reactive({
  total: 0,
  pending: 0,
  confirmed: 0,
  rejected: 0,
  modified: 0,
})

// ─── Group expansion ───
const expandedGroups = reactive({})
const activeTypes = reactive({})

// ─── Editing ───
const editingId = ref(null)
const editText = ref('')
const originalText = ref('')

// ─── Rejecting ───
const rejectingId = ref(null)
const rejectReason = ref('')

// ─── Computed: grouped by workpaper ───
const groupedContent = computed(() => {
  let filtered = allContent.value
  if (filterType.value) {
    filtered = filtered.filter(i => i.content_type === filterType.value)
  }
  if (filterStatus.value) {
    filtered = filtered.filter(i => i.confirmation_status === filterStatus.value)
  }
  if (filterWorkpaper.value) {
    filtered = filtered.filter(i => i.workpaper_id === filterWorkpaper.value)
  }

  const groups = {}
  for (const item of filtered) {
    const key = item.workpaper_name || item.workpaper_id || '通用'
    if (!groups[key]) groups[key] = []
    groups[key].push(item)
  }
  return groups
})

// ─── Options ───
const contentTypeOptions = [
  { label: '全部', value: '' },
  { label: '数据填充', value: 'data_fill' },
  { label: '分析复核', value: 'analytical_review' },
  { label: '风险提示', value: 'risk_alert' },
  { label: '测试摘要', value: 'test_summary' },
  { label: '附注初稿', value: 'note_draft' },
]

// ─── Helpers ───
function pendingCount(items) {
  return items.filter(i => i.confirmation_status === 'pending').length
}

function countByType(items, type) {
  if (!type) return items.length
  return items.filter(i => i.content_type === type).length
}

function filteredItems(items, workpaperName) {
  const type = activeTypes[workpaperName] || ''
  if (!type) return items
  return items.filter(i => i.content_type === type)
}

function toggleGroup(name) {
  expandedGroups[name] = !expandedGroups[name]
}

function setActiveType(workpaperName, type) {
  activeTypes[workpaperName] = type
}

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

function isLowConfidence(item) {
  return item.confidence_level === 'low'
}

function confidenceClass(level) {
  return {
    high: 'conf-high',
    medium: 'conf-medium',
    low: 'conf-low',
  }
}

function truncate(text, maxLen) {
  if (!text) return ''
  return text.length > maxLen ? text.substring(0, maxLen) + '...' : text
}

function formatTime(timeStr) {
  if (!timeStr) return '-'
  return new Date(timeStr).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

// ─── Load data ───
async function loadContent() {
  try {
    const result = await workpaperAI.getAIContentList(props.projectId)
    allContent.value = result.data || []
    updateStats()
  } catch (e) {
    console.error('Load AI content error:', e)
    // 模拟数据
    allContent.value = generateMockData()
    updateStats()
  }
}

function generateMockData() {
  const types = ['data_fill', 'analytical_review', 'risk_alert', 'test_summary', 'note_draft']
  const wps = [
    { id: 'wp1', name: '应收账款', items: [] },
    { id: 'wp2', name: '存货', items: [] },
    { id: 'wp3', name: '固定资产', items: [] },
  ]
  const result = []
  for (const wp of wps) {
    const count = Math.floor(Math.random() * 3) + 2
    for (let i = 0; i < count; i++) {
      const type = types[Math.floor(Math.random() * types.length)]
      const statuses = ['pending', 'pending', 'pending', 'accepted', 'modified']
      result.push({
        id: `${wp.id}-${i}`,
        workpaper_id: wp.id,
        workpaper_name: wp.name,
        content_type: type,
        content_text: getMockContent(type, wp.name),
        confirmation_status: statuses[Math.floor(Math.random() * statuses.length)],
        confidence_level: ['high', 'high', 'medium', 'low'][Math.floor(Math.random() * 4)],
        generation_time: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString(),
        data_sources: ['试算表', '辅助明细', '记账凭证'],
      })
    }
  }
  return result
}

function getMockContent(type, wpName) {
  const map = {
    data_fill: `${wpName}本年期末余额较上年增长15%，主要系销售规模扩大所致。存货周转天数45天，同比增加3天。`,
    analytical_review: `${wpName}本年发生额较上年同期增长25%，其中Q4增幅最大，占全年45%。前五大客户集中度60%，同比上升5个百分点。`,
    risk_alert: `⚠️ 发现异常：${wpName}中存在大额关联方往来，占该科目总额35%，存在关联方资金占用风险，建议扩大函证范围。`,
    test_summary: `${wpName}测试样本量30笔，金额覆盖率75%。其中28笔未发现错报，2笔小额差异已确认系合理口径差异。`,
    note_draft: `${wpName}：本年余额人民币XXX元，上年余额人民币XXX元，变动额XXX元，变动率XX%。变动原因主要为...`,
  }
  return map[type] || `${wpName} AI生成内容...`
}

function updateStats() {
  stats.total = allContent.value.length
  stats.pending = allContent.value.filter(i => i.confirmation_status === 'pending').length
  stats.confirmed = allContent.value.filter(i => i.confirmation_status === 'accepted').length
  stats.rejected = allContent.value.filter(i => i.confirmation_status === 'rejected').length
  stats.modified = allContent.value.filter(i => i.confirmation_status === 'modified').length
}

// ─── Edit ───
function startEdit(item) {
  editingId.value = item.id
  editText.value = item.content_text
  originalText.value = item.content_text
}

function cancelEdit() {
  editingId.value = null
  editText.value = ''
  originalText.value = ''
}

async function saveEdit(item) {
  if (!editText.value.trim()) return
  try {
    await workpaperAI.confirmAIContent(props.projectId, item.id, {
      action: 'modify',
      modification_note: '用户手动修改',
    })
    item.content_text = editText.value
    item.confirmation_status = 'modified'
    updateStats()
    cancelEdit()
  } catch (e) {
    console.error('Save edit error:', e)
    item.content_text = editText.value
    item.confirmation_status = 'modified'
    updateStats()
    cancelEdit()
  }
}

// ─── Confirm / Reject / Regenerate ───
async function confirmItem(item) {
  try {
    await workpaperAI.confirmAIContent(props.projectId, item.id, { action: 'accept' })
    item.confirmation_status = 'accepted'
    updateStats()
  } catch (e) {
    console.error('Confirm error:', e)
    item.confirmation_status = 'accepted'
    updateStats()
  }
}

function rejectItem(item) {
  rejectingId.value = item.id
  rejectReason.value = ''
}

function cancelReject() {
  rejectingId.value = null
  rejectReason.value = ''
}

async function submitReject(item) {
  try {
    await workpaperAI.confirmAIContent(props.projectId, item.id, {
      action: 'reject',
      modification_note: rejectReason.value,
    })
    item.confirmation_status = 'rejected'
    updateStats()
  } catch (e) {
    console.error('Reject error:', e)
    item.confirmation_status = 'rejected'
    updateStats()
  }
  cancelReject()
}

async function regenerateItem(item) {
  try {
    await workpaperAI.confirmAIContent(props.projectId, item.id, { action: 'regenerate' })
    item.confirmation_status = 'regenerated'
    updateStats()
  } catch (e) {
    console.error('Regenerate error:', e)
  }
}

// ─── Init ───
onMounted(async () => {
  await loadContent()
  // 展开所有分组
  for (const key of Object.keys(groupedContent.value)) {
    expandedGroups[key] = true
    activeTypes[key] = ''
  }
})
</script>

<style scoped>
.gt-ai-content-review-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: #fafafa;
}

.panel-header {
  padding: 16px 20px 12px;
  background: #fff;
  border-bottom: 1px solid #eee;
  flex-shrink: 0;
}

.panel-header h3 {
  margin: 0 0 12px;
  font-size: 16px;
  color: #333;
}

.filter-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-select {
  padding: 5px 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 12px;
  background: #fff;
  cursor: pointer;
  outline: none;
}
.filter-select:focus {
  border-color: #4b2d77;
}

/* Stats bar */
.stats-bar {
  display: flex;
  gap: 8px;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #eee;
  flex-shrink: 0;
}

.stat-item {
  flex: 1;
  text-align: center;
  padding: 8px;
  border-radius: 6px;
  background: #f5f5f5;
}

.stat-item.pending { background: #fff7e6; }
.stat-item.confirmed { background: #f6ffed; }
.stat-item.rejected { background: #fff2f0; }
.stat-item.modified { background: #e6f7ff; }

.stat-value {
  display: block;
  font-size: 22px;
  font-weight: 700;
  color: #333;
  line-height: 1.2;
}

.stat-item.pending .stat-value { color: #fa8c16; }
.stat-item.confirmed .stat-value { color: #52c41a; }
.stat-item.rejected .stat-value { color: #ff4d4f; }
.stat-item.modified .stat-value { color: #1890ff; }

.stat-label {
  font-size: 11px;
  color: #888;
}

/* Content groups */
.content-groups {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}

.workpaper-group {
  margin-bottom: 12px;
  border: 1px solid #eee;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #f9f9f9;
  cursor: pointer;
  user-select: none;
  font-size: 13px;
}

.group-header:hover { background: #f0f0f0; }

.group-toggle { color: #999; font-size: 10px; }
.group-title { font-weight: 600; color: #333; }
.group-badge {
  background: #e8e8e8;
  color: #666;
  padding: 1px 6px;
  border-radius: 10px;
  font-size: 11px;
}
.group-pending {
  margin-left: auto;
  color: #fa8c16;
  font-size: 12px;
}

/* Type tabs */
.type-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 14px;
  border-bottom: 1px solid #f0f0f0;
  overflow-x: auto;
}

.type-tab {
  padding: 3px 10px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.type-tab.active { background: #4b2d77; color: #fff; border-color: #4b2d77; }

.type-count {
  background: rgba(0,0,0,0.1);
  padding: 0 4px;
  border-radius: 8px;
  font-size: 10px;
}
.type-tab.active .type-count { background: rgba(255,255,255,0.2); }

/* Content cards */
.items-list { padding: 8px 14px; display: flex; flex-direction: column; gap: 8px; }

.content-card {
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 12px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.content-card:hover { border-color: #4b2d77; box-shadow: 0 2px 6px rgba(75,45,119,0.08); }
.content-card.status-accepted { border-left: 3px solid #52c41a; }
.content-card.status-rejected { border-left: 3px solid #ff4d4f; }
.content-card.status-modified { border-left: 3px solid #1890ff; }
.content-card.editing { border-color: #4b2d77; background: #fcfafe; }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 6px;
}

.card-badges { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }

.type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.type-badge.data_fill { background: #e6f7ff; color: #1890ff; }
.type-badge.analytical_review { background: #f6ffed; color: #52c41a; }
.type-badge.risk_alert { background: #fff7e6; color: #fa8c16; }
.type-badge.test_summary { background: #f9f0ff; color: #722ed1; }
.type-badge.note_draft { background: #fff1f0; color: #eb2f96; }

.confidence-badge {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}
.conf-high { background: #f6ffed; color: #52c41a; }
.conf-medium { background: #fff7e6; color: #fa8c16; }
.conf-low { background: #fff2f0; color: #ff4d4f; }

.low-confidence-tag {
  color: #ff4d4f;
  font-size: 11px;
  font-weight: 600;
}

.ai-tag {
  background: rgba(75,45,119,0.1);
  color: #4b2d77;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: #999;
}

.status-tag {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}
.status-tag.pending { background: #fff7e6; color: #fa8c16; }
.status-tag.accepted { background: #f6ffed; color: #52c41a; }
.status-tag.modified { background: #e6f7ff; color: #1890ff; }
.status-tag.rejected { background: #fff2f0; color: #ff4d4f; }

/* Content text */
.card-body { margin-bottom: 8px; }

.content-text {
  font-size: 13px;
  line-height: 1.7;
  color: #333;
  cursor: text;
  padding: 4px 0;
  white-space: pre-wrap;
}
.content-text:hover { background: #f5f5f5; border-radius: 4px; }
.expand-hint {
  color: #4b2d77;
  font-size: 11px;
  cursor: pointer;
  display: block;
  margin-top: 4px;
}

.content-editor { display: flex; flex-direction: column; gap: 8px; }

.edit-textarea {
  width: 100%;
  border: 1px solid #4b2d77;
  border-radius: 4px;
  padding: 8px;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
  font-family: inherit;
  outline: none;
}
.edit-textarea:focus { border-color: #722ed1; }

.edit-actions { display: flex; gap: 8px; }

.btn-save, .btn-cancel-edit {
  padding: 4px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  border: none;
}
.btn-save { background: #52c41a; color: #fff; }
.btn-save:hover { background: #389e0d; }
.btn-cancel-edit { background: #f0f0f0; color: #666; }
.btn-cancel-edit:hover { background: #e0e0e0; }

/* Sources */
.card-sources {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
  font-size: 11px;
}
.sources-label { color: #999; }
.source-tag {
  background: #f0f0f0;
  color: #666;
  padding: 1px 6px;
  border-radius: 4px;
}

/* Actions */
.card-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding-top: 8px;
  border-top: 1px solid #f5f5f5;
}

.btn-confirm-action,
.btn-edit-action,
.btn-reject-action,
.btn-regenerate-action {
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  border: 1px solid;
  background: #fff;
}
.btn-confirm-action { border-color: #52c41a; color: #52c41a; }
.btn-confirm-action:hover { background: #f6ffed; }
.btn-edit-action { border-color: #1890ff; color: #1890ff; }
.btn-edit-action:hover { background: #e6f7ff; }
.btn-reject-action { border-color: #ff4d4f; color: #ff4d4f; }
.btn-reject-action:hover { background: #fff2f0; }
.btn-regenerate-action { border-color: #722ed1; color: #722ed1; }
.btn-regenerate-action:hover { background: #f9f0ff; }

.action-done { color: #999; font-size: 12px; align-self: center; }

/* Reject dialog */
.reject-dialog {
  margin-top: 8px;
  padding: 10px;
  background: #fff2f0;
  border-radius: 6px;
  border: 1px solid #ffccc7;
}

.reject-reason { display: flex; flex-direction: column; gap: 6px; margin-bottom: 8px; }
.reject-reason label { font-size: 12px; color: #666; font-weight: 600; }

.reason-textarea {
  width: 100%;
  border: 1px solid #ffccc7;
  border-radius: 4px;
  padding: 6px;
  font-size: 12px;
  resize: vertical;
  font-family: inherit;
  outline: none;
}

.reject-actions { display: flex; gap: 8px; }

.btn-confirm-reject, .btn-cancel-reject {
  padding: 4px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  border: none;
}
.btn-confirm-reject { background: #ff4d4f; color: #fff; }
.btn-confirm-reject:hover { background: #d93636; }
.btn-cancel-reject { background: #f0f0f0; color: #666; }

.empty-state {
  padding: 48px;
  text-align: center;
  color: #999;
  background: #fff;
  border-radius: 8px;
}

.empty-type {
  padding: 16px;
  text-align: center;
  color: #bbb;
  font-size: 12px;
}
</style>
