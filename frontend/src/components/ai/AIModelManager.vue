<template>
  <div class="ai-admin">
    <div class="page-header">
      <h2>AI 模型管理</h2>
      <button class="btn-primary" @click="showCreateModal = true">
        + 添加模型
      </button>
    </div>

    <!-- 统计概览 -->
    <div class="stats-grid" v-if="usageStats">
      <div class="stat-card">
        <div class="stat-value">{{ usageStats.total_requests || 0 }}</div>
        <div class="stat-label">总调用次数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ usageStats.total_tokens || 0 }}</div>
        <div class="stat-label">总 Token 消耗</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ activeModels.length }}</div>
        <div class="stat-label">已配置模型</div>
      </div>
    </div>

    <!-- 模型列表 -->
    <div class="models-grid">
      <div v-for="model in models" :key="model.model_id" class="model-card">
        <div class="model-header">
          <span class="model-name">{{ model.model_name }}</span>
          <span class="provider-badge">{{ model.provider }}</span>
        </div>
        <div class="model-info">
          <div class="info-row">
            <span class="info-label">类型:</span>
            <span class="info-value">{{ model.model_type }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">端点:</span>
            <span class="info-value endpoint">{{ model.endpoint }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">状态:</span>
            <span class="status-badge" :class="model.status">{{ model.status }}</span>
          </div>
        </div>
        <div class="model-actions">
          <button class="btn-sm" @click="testModel(model.model_id)">测试</button>
          <button class="btn-sm" @click="editModel(model)">编辑</button>
          <button class="btn-sm btn-danger" @click="deleteModel(model.model_id)">删除</button>
        </div>
      </div>
    </div>

    <!-- 创建/编辑弹窗 -->
    <div class="modal-overlay" v-if="showCreateModal || editingModel" @click.self="closeModal">
      <div class="modal">
        <h3>{{ editingModel ? '编辑模型' : '添加模型' }}</h3>
        <form @submit.prevent="saveModel">
          <div class="form-group">
            <label>模型名称</label>
            <input v-model="form.model_name" required />
          </div>
          <div class="form-group">
            <label>模型标识</label>
            <input v-model="form.model_id" :disabled="!!editingModel" />
          </div>
          <div class="form-group">
            <label>提供商</label>
            <select v-model="form.provider">
              <option value="ollama">Ollama</option>
              <option value="openai">OpenAI</option>
              <option value="azure">Azure OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="custom">自定义</option>
            </select>
          </div>
          <div class="form-group">
            <label>模型类型</label>
            <select v-model="form.model_type">
              <option value="chat">对话模型</option>
              <option value="embedding">嵌入模型</option>
              <option value="vision">多模态模型</option>
            </select>
          </div>
          <div class="form-group">
            <label>API 端点</label>
            <input v-model="form.endpoint" placeholder="http://localhost:11434" />
          </div>
          <div class="form-group">
            <label>API Key</label>
            <input v-model="form.api_key" type="password" />
          </div>
          <div class="form-group">
            <label>默认系统提示</label>
            <textarea v-model="form.system_prompt" rows="3"></textarea>
          </div>
          <div class="form-actions">
            <button type="button" class="btn-sm" @click="closeModal">取消</button>
            <button type="submit" class="btn-primary">{{ editingModel ? '保存' : '创建' }}</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAIAdmin } from '@/composables/useAI'

const {
  models,
  loading,
  error,
  fetchModels,
  createModel,
  updateModel,
  deleteModel,
  testModel: testModelApi,
} = useAIAdmin()

const showCreateModal = ref(false)
const editingModel = ref(null)
const usageStats = ref(null)
const form = ref({
  model_name: '',
  model_id: '',
  provider: 'ollama',
  model_type: 'chat',
  endpoint: 'http://localhost:11434',
  api_key: '',
  system_prompt: '你是一名专业审计师。',
})

onMounted(async () => {
  await fetchModels()
  // 加载使用统计
  const { aiAdmin } = await import('@/api')
  try {
    usageStats.value = await aiAdmin.getUsageStats()
  } catch (e) {
    console.warn('Usage stats unavailable:', e)
  }
})

function editModel(model) {
  editingModel.value = model
  form.value = { ...model }
}

function closeModal() {
  showCreateModal.value = false
  editingModel.value = null
  form.value = {
    model_name: '',
    model_id: '',
    provider: 'ollama',
    model_type: 'chat',
    endpoint: 'http://localhost:11434',
    api_key: '',
    system_prompt: '你是一名专业审计师。',
  }
}

async function saveModel() {
  if (editingModel.value) {
    await updateModel(editingModel.value.model_id, form.value)
  } else {
    await createModel(form.value)
  }
  closeModal()
}

async function testModel(modelId) {
  if (!confirm('确定要测试此模型连接吗？')) return
  try {
    const result = await testModelApi(modelId)
    alert(result.success ? `连接成功！响应时间: ${result.latency_ms}ms` : `连接失败: ${result.error}`)
  } catch (e) {
    alert('测试失败: ' + e.message)
  }
}

async function deleteModel(modelId) {
  if (!confirm('确定要删除此模型配置吗？')) return
  await deleteModel(modelId)
}

const activeModels = computed(() => models.value.filter(m => m.status === 'active'))
</script>

<style scoped>
.ai-admin {
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  color: #303133;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: #fff;
  padding: 20px;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #409eff;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 4px;
}

.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.model-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
}

.model-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.model-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.provider-badge {
  padding: 2px 8px;
  background: #ecf5ff;
  color: #409eff;
  border-radius: 10px;
  font-size: 12px;
}

.model-info {
  margin-bottom: 12px;
}

.info-row {
  display: flex;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 13px;
}

.info-label {
  color: #909399;
  min-width: 50px;
}

.info-value {
  color: #606266;
}

.info-value.endpoint {
  font-size: 12px;
  word-break: break-all;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
}

.status-badge.active { background: #e7f7e7; color: #67c23a; }
.status-badge.inactive { background: #f0f0f0; color: #909399; }
.status-badge.error { background: #fef0f0; color: #f56c6c; }

.model-actions {
  display: flex;
  gap: 8px;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  width: 480px;
  max-width: 90vw;
}

.modal h3 {
  margin: 0 0 20px;
  font-size: 18px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  color: #606266;
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}

.btn-primary {
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 8px 16px;
  cursor: pointer;
  font-size: 14px;
}

.btn-sm {
  padding: 6px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}

.btn-danger {
  color: #f56c6c;
  border-color: #f56c6c;
}
</style>
