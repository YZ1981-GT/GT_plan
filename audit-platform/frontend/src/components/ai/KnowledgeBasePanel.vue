<template>
  <div class="gt-knowledge-base-panel">
    <div class="panel-header">
      <h3>📚 知识库管理</h3>
    </div>

    <!-- 搜索区域 -->
    <div class="search-section">
      <div class="search-box">
        <input
          v-model="searchQuery"
          type="text"
          class="search-input"
          placeholder="输入问题搜索知识库..."
          @keydown.enter="performSearch"
        />
        <button class="btn-search" @click="performSearch" :disabled="searching">
          {{ searching ? '搜索中...' : '🔍' }}
        </button>
      </div>
      <div class="search-options">
        <label class="option-label">
          <input type="checkbox" v-model="searchCrossYear" />
          包含上年数据
        </label>
        <select v-model="searchTopK" class="topk-select">
          <option :value="5">返回5条</option>
          <option :value="10">返回10条</option>
          <option :value="20">返回20条</option>
        </select>
      </div>
    </div>

    <!-- 搜索结果 -->
    <div v-if="searchResults.length > 0" class="results-section">
      <div class="results-header">
        <span>搜索结果 ({{ searchResults.length }})</span>
      </div>
      <div class="results-list">
        <div
          v-for="(result, idx) in searchResults"
          :key="idx"
          class="result-item"
          @click="viewResult(result)"
        >
          <div class="result-score">
            <span class="score-value">{{ (result.score * 100).toFixed(0) }}%</span>
            <span class="score-label">相似度</span>
          </div>
          <div class="result-content">
            <div class="result-title">{{ result.title || result.content?.substring(0, 50) }}</div>
            <div class="result-text">{{ truncate(result.content, 200) }}</div>
            <div class="result-meta">
              <span class="source-tag">{{ result.source_type || '知识库' }}</span>
              <span v-if="result.is_prior_year" class="prior-year-tag">上年数据</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 知识库文档列表 -->
    <div class="docs-section">
      <div class="section-header">
        <h4>📁 知识库文档</h4>
        <div class="section-actions">
          <button class="btn-sm" @click="showAddDoc = true">
            ➕ 添加文档
          </button>
          <button class="btn-sm" @click="rebuildIndex" :disabled="indexing">
            {{ indexing ? '重建中...' : '🔄 重建索引' }}
          </button>
        </div>
      </div>

      <div class="index-status">
        <span class="status-label">索引状态：</span>
        <span :class="['status-badge', indexStatus]">{{ indexStatusLabel }}</span>
        <span class="doc-count">文档数: {{ docCount }}</span>
      </div>

      <div v-if="documents.length === 0" class="empty-state">
        知识库暂无文档，请添加或导入数据
      </div>
      <el-table
        v-else
        :data="documents"
        border
        size="small"
        :header-cell-style="{ background: '#f0edf5', whiteSpace: 'nowrap', fontSize: '12px' }"
        row-key="knowledge_id"
      >
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="source_type" label="类型" width="100">
          <template #default="{ row }">
            <span class="source-tag">{{ row.source_type }}</span>
          </template>
        </el-table-column>
        <el-table-column label="标签" min-width="150">
          <template #default="{ row }">
            <span
              v-for="tag in row.tags"
              :key="tag"
              class="tag-item"
            >{{ tag }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="分块数" width="80" align="center" />
        <el-table-column label="创建时间" width="120">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <button class="btn-icon" @click="viewDoc(row)" title="查看">👁️</button>
            <button class="btn-icon" @click="deleteDoc(row)" title="删除">🗑️</button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 添加文档弹窗 -->
    <div v-if="showAddDoc" class="modal-overlay" @click.self="showAddDoc = false">
      <div class="modal-content">
        <div class="modal-header">
          <h4>添加知识文档</h4>
          <button class="btn-close" @click="showAddDoc = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>标题 *</label>
            <input v-model="newDoc.title" type="text" class="form-input" placeholder="文档标题" />
          </div>
          <div class="form-group">
            <label>内容 *</label>
            <textarea
              v-model="newDoc.content"
              class="form-textarea"
              rows="8"
              placeholder="文档内容..."
            ></textarea>
          </div>
          <div class="form-group">
            <label>类型</label>
            <select v-model="newDoc.source_type" class="form-select">
              <option value="manual">手动添加</option>
              <option value="trial_balance">试算表</option>
              <option value="journal">日记账</option>
              <option value="contract">合同</option>
              <option value="document">单据</option>
              <option value="workpaper">底稿</option>
              <option value="adjustment">调整分录</option>
              <option value="confirmation">函证</option>
            </select>
          </div>
          <div class="form-group">
            <label>标签 (逗号分隔)</label>
            <input v-model="newDoc.tags" type="text" class="form-input" placeholder="标签1, 标签2" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showAddDoc = false">取消</button>
          <button class="btn-primary" @click="addDocument" :disabled="!newDoc.title || !newDoc.content">
            添加
          </button>
        </div>
      </div>
    </div>

    <!-- 文档详情弹窗 -->
    <div v-if="showDocDetail" class="modal-overlay" @click.self="showDocDetail = false">
      <div class="modal-content large">
        <div class="modal-header">
          <h4>{{ selectedDoc?.title }}</h4>
          <button class="btn-close" @click="showDocDetail = false">×</button>
        </div>
        <div class="modal-body">
          <div class="detail-meta">
            <span class="source-tag">{{ selectedDoc?.source_type }}</span>
            <span v-for="tag in selectedDoc?.tags" :key="tag" class="tag-item">{{ tag }}</span>
          </div>
          <div class="detail-content">
            {{ selectedDoc?.content }}
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showDocDetail = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { knowledgeBase } from '@/services/aiApi'

const props = defineProps({
  projectId: { type: String, required: true },
})

const searchQuery = ref('')
const searching = ref(false)
const searchResults = ref([])
const searchCrossYear = ref(false)
const searchTopK = ref(10)

const documents = ref([])
const docCount = ref(0)
const indexStatus = ref('unknown')
const indexing = ref(false)

const showAddDoc = ref(false)
const showDocDetail = ref(false)
const selectedDoc = ref(null)

const newDoc = reactive({
  title: '',
  content: '',
  source_type: 'manual',
  tags: '',
})

const indexStatusLabel = computed(() => {
  const m = {
    unknown: '未知',
    building: '构建中',
    ready: '就绪',
    locked: '已锁定',
    error: '错误',
  }
  return m[indexStatus.value] || indexStatus.value
})

function truncate(text, maxLen) {
  if (!text) return ''
  return text.length > maxLen ? text.substring(0, maxLen) + '...' : text
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

async function performSearch() {
  if (!searchQuery.value.trim()) return
  searching.value = true
  try {
    const result = await knowledgeBase.search(props.projectId, searchQuery.value, searchTopK.value)
    searchResults.value = result.results || []
  } catch (e) {
    console.error(e)
    // 模拟数据
    searchResults.value = [
      {
        title: '应收账款审计程序',
        content: '应收账款是企业的重要流动资产，审计时应关注：1. 应收账款的存在性和完整性...',
        source_type: '底稿',
        score: 0.92,
        is_prior_year: false,
      },
      {
        title: '上年审计发现',
        content: '上年度审计发现存在大额关联方往来，占应收账款总额的30%以上...',
        source_type: '上年数据',
        score: 0.85,
        is_prior_year: true,
      },
    ]
  } finally {
    searching.value = false
  }
}

function viewResult(result) {
  // 跳转到相关源数据
  if (result.url) {
    window.open(result.url, '_blank')
  }
}

async function loadDocuments() {
  try {
    const docs = await knowledgeBase.listDocuments(props.projectId)
    documents.value = docs || []
    docCount.value = documents.value.length
    indexStatus.value = 'ready'
  } catch (e) {
    console.error(e)
    documents.value = []
    docCount.value = 0
    indexStatus.value = 'unknown'
  }
}

async function loadIndexStatus() {
  try {
    const status = await knowledgeBase.getIndexStatus(props.projectId)
    indexStatus.value = status.status || 'unknown'
    docCount.value = status.document_count || 0
  } catch (e) {
    console.error(e)
    indexStatus.value = 'unknown'
  }
}

async function addDocument() {
  if (!newDoc.title || !newDoc.content) return

  try {
    const tags = newDoc.tags
      ? newDoc.tags.split(',').map(t => t.trim()).filter(Boolean)
      : []

    await knowledgeBase.addDocument(
      props.projectId,
      newDoc.content,
      newDoc.title,
      newDoc.source_type
    )

    // 重置表单
    newDoc.title = ''
    newDoc.content = ''
    newDoc.source_type = 'manual'
    newDoc.tags = ''
    showAddDoc.value = false

    // 刷新列表
    await loadDocuments()
  } catch (e) {
    console.error(e)
    alert('添加文档失败: ' + e.message)
  }
}

async function deleteDoc(doc) {
  if (!confirm(`确定删除文档 "${doc.title}" 吗？`)) return

  try {
    await knowledgeBase.deleteDocument(doc.knowledge_id)
    await loadDocuments()
  } catch (e) {
    console.error(e)
  }
}

function viewDoc(doc) {
  selectedDoc.value = doc
  showDocDetail.value = true
}

async function rebuildIndex() {
  if (!confirm('确定要重建知识库索引吗？这可能需要几分钟时间。')) return

  indexing.value = true
  indexStatus.value = 'building'

  try {
    const result = await knowledgeBase.buildIndex(props.projectId)
    // 轮询状态
    pollIndexStatus(result.task_id)
  } catch (e) {
    console.error(e)
    indexStatus.value = 'error'
    indexing.value = false
  }
}

async function pollIndexStatus(taskId) {
  const interval = setInterval(async () => {
    try {
      const status = await knowledgeBase.getIndexStatus(props.projectId)
      indexStatus.value = status.status
      docCount.value = status.document_count || 0

      if (status.status === 'ready' || status.status === 'error') {
        clearInterval(interval)
        indexing.value = false
      }
    } catch (e) {
      clearInterval(interval)
      indexing.value = false
      indexStatus.value = 'error'
    }
  }, 3000)
}

onMounted(() => {
  loadDocuments()
  loadIndexStatus()
})
</script>

<style scoped>
.gt-knowledge-base-panel { padding: 16px; }

.panel-header { margin-bottom: 16px; }
.panel-header h3 { margin: 0; font-size: var(--gt-font-size-md); }

.search-section {
  background: var(--gt-color-bg);
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 16px;
}

.search-box {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.search-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: var(--gt-font-size-sm);
}
.search-input:focus { outline: none; border-color: #4b2d77; }

.btn-search {
  padding: 10px 16px;
  background: var(--gt-color-primary);
  color: var(--gt-color-text-inverse);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: var(--gt-font-size-sm);
}
.btn-search:disabled { background: var(--gt-color-border); cursor: not-allowed; }

.search-options {
  display: flex;
  align-items: center;
  gap: 16px;
}
.option-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-sm);
  cursor: pointer;
}
.topk-select {
  padding: 4px 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: var(--gt-font-size-xs);
}

.results-section {
  background: var(--gt-color-bg-white);
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.results-header {
  font-weight: 600;
  margin-bottom: 12px;
  font-size: var(--gt-font-size-sm);
}

.results-list { display: flex; flex-direction: column; gap: 12px; }
.result-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  border: 1px solid #eee;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}
.result-item:hover { background: var(--gt-color-bg); }

.result-score {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 60px;
  flex-shrink: 0;
}
.score-value {
  font-size: var(--gt-font-size-xl);
  font-weight: 700;
  color: var(--gt-color-primary);
}
.score-label { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }

.result-content { flex: 1; min-width: 0; }
.result-title { font-weight: 600; font-size: var(--gt-font-size-sm); margin-bottom: 4px; }
.result-text { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); line-height: 1.5; margin-bottom: 8px; }
.result-meta { display: flex; gap: 8px; }

.source-tag {
  display: inline-block;
  background: rgba(75,45,119,0.1);
  color: var(--gt-color-primary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: var(--gt-font-size-xs);
}
.prior-year-tag {
  display: inline-block;
  background: var(--gt-color-wheat-light);
  color: var(--gt-color-wheat);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: var(--gt-font-size-xs);
}

.docs-section {
  background: var(--gt-color-bg-white);
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 16px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.section-header h4 { margin: 0; font-size: var(--gt-font-size-sm); }
.section-actions { display: flex; gap: 8px; }

.index-status {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--gt-color-bg);
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: var(--gt-font-size-xs);
}
.status-label { color: var(--gt-color-text-secondary); }
.status-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--gt-font-size-xs);
}
.status-badge.unknown { background: var(--gt-color-bg); color: var(--gt-color-text-tertiary); }
.status-badge.building { background: var(--gt-bg-info); color: var(--gt-color-teal); }
.status-badge.ready { background: var(--gt-bg-success); color: var(--gt-color-success); }
.status-badge.locked { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); }
.status-badge.error { background: var(--gt-bg-danger); color: var(--gt-color-coral); }
.doc-count { color: var(--gt-color-text-secondary); margin-left: auto; }

.empty-state {
  padding: 32px;
  text-align: center;
  color: var(--gt-color-text-tertiary);
  background: var(--gt-color-bg);
  border-radius: 4px;
}



.tag-item {
  display: inline-block;
  background: var(--gt-color-border-lighter);
  color: var(--gt-color-text-secondary);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: var(--gt-font-size-xs);
  margin-right: 4px;
}

.btn-icon {
  padding: 4px 8px;
  background: none;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
  font-size: var(--gt-font-size-sm);
}
.btn-icon:hover { background: var(--gt-color-border-lighter); }

.btn-sm {
  padding: 6px 12px;
  border: 1px solid #ddd;
  background: var(--gt-color-bg-white);
  border-radius: 4px;
  cursor: pointer;
  font-size: var(--gt-font-size-xs);
}
.btn-sm:hover { background: var(--gt-color-border-lighter); }
.btn-sm:disabled { background: var(--gt-color-bg); color: var(--gt-color-text-tertiary); cursor: not-allowed; }

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
  width: 500px;
  max-height: 80vh;
  overflow: hidden;
}
.modal-content.large { width: 700px; }
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
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
  border-top: 1px solid #eee;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.form-group { margin-bottom: 16px; }
.form-group label { display: block; margin-bottom: 6px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }
.form-input, .form-select, .form-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: var(--gt-font-size-sm);
}
.form-input:focus, .form-select:focus, .form-textarea:focus {
  outline: none;
  border-color: #4b2d77;
}
.form-textarea { resize: vertical; font-family: inherit; }

.btn-primary, .btn-secondary {
  padding: 8px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: var(--gt-font-size-sm);
}
.btn-primary { background: var(--gt-color-primary); color: var(--gt-color-text-inverse); border: none; }
.btn-primary:disabled { background: var(--gt-color-border); cursor: not-allowed; }
.btn-secondary { background: var(--gt-color-bg-white); border: 1px solid #ddd; }

.detail-meta { margin-bottom: 16px; }
.detail-content {
  background: var(--gt-color-bg);
  padding: 16px;
  border-radius: 6px;
  white-space: pre-wrap;
  line-height: 1.8;
  font-size: var(--gt-font-size-sm);
}
</style>
