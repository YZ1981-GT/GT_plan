<template>
  <div class="ai-model-config">
    <!-- 顶部状态栏 -->
    <div class="ai-header">
      <h3 class="ai-title">AI 模型配置</h3>
      <div class="ai-header-actions">
        <el-button size="small" @click="refreshHealth" :loading="healthLoading">
          <el-icon><Refresh /></el-icon>检测状态
        </el-button>
        <el-button size="small" type="primary" @click="showCreateDialog = true">
          <el-icon><Plus /></el-icon>新增模型
        </el-button>
      </div>
    </div>

    <!-- 健康状态卡片 -->
    <div class="ai-health-cards" v-if="health">
      <div class="health-card" :class="health.ollama_status === 'healthy' ? 'ok' : 'err'">
        <span class="health-dot" />
        <span class="health-label">Ollama</span>
        <span class="health-val">{{ health.ollama_status }}</span>
      </div>
      <div class="health-card" :class="health.paddleocr_status === 'healthy' ? 'ok' : 'err'">
        <span class="health-dot" />
        <span class="health-label">PaddleOCR</span>
        <span class="health-val">{{ health.paddleocr_status }}</span>
      </div>
      <div class="health-card" :class="health.chromadb_status === 'healthy' ? 'ok' : 'err'">
        <span class="health-dot" />
        <span class="health-label">ChromaDB</span>
        <span class="health-val">{{ health.chromadb_status }}</span>
      </div>
    </div>

    <!-- 模型分类 Tabs -->
    <el-tabs v-model="activeTab" class="ai-tabs">
      <el-tab-pane label="对话模型" name="chat">
        <ModelTable :models="chatModels" :loading="loading" @activate="onActivate" @edit="onEdit" @delete="onDelete" />
      </el-tab-pane>
      <el-tab-pane label="嵌入模型" name="embedding">
        <ModelTable :models="embeddingModels" :loading="loading" @activate="onActivate" @edit="onEdit" @delete="onDelete" />
      </el-tab-pane>
      <el-tab-pane label="OCR 引擎" name="ocr">
        <ModelTable :models="ocrModels" :loading="loading" @activate="onActivate" @edit="onEdit" @delete="onDelete" />
      </el-tab-pane>
    </el-tabs>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingModel ? '编辑模型' : '新增模型'"
      width="520px"
      destroy-on-close
    >
      <el-form :model="form" label-width="100px" ref="formRef" :rules="formRules">
        <el-form-item label="模型名称" prop="model_name">
          <el-input v-model="form.model_name" placeholder="如 qwen2.5:7b" />
        </el-form-item>
        <el-form-item label="模型类型" prop="model_type">
          <el-select v-model="form.model_type" :disabled="!!editingModel" style="width: 100%">
            <el-option label="对话模型" value="chat" />
            <el-option label="嵌入模型" value="embedding" />
            <el-option label="OCR 引擎" value="ocr" />
          </el-select>
        </el-form-item>
        <el-form-item label="供应商" prop="provider">
          <el-select v-model="form.provider" style="width: 100%">
            <el-option label="Ollama" value="ollama" />
            <el-option label="OpenAI 兼容" value="openai_compatible" />
            <el-option label="PaddleOCR" value="paddleocr" />
          </el-select>
        </el-form-item>
        <el-form-item label="端点 URL">
          <el-input v-model="form.endpoint_url" placeholder="留空使用默认地址" />
        </el-form-item>
        <el-form-item label="上下文窗口">
          <el-input-number v-model="form.context_window" :min="1024" :step="1024" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.performance_notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="onSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus } from '@element-plus/icons-vue'
import ModelTable from '@/components/ai/ModelTable.vue'
import type { AIModel, AIModelCreate, AIHealthStatus } from '@/services/aiModelApi'
import {
  getAIModels, createAIModel, updateAIModel, deleteAIModel,
  activateAIModel, getAIHealth,
} from '@/services/aiModelApi'

const loading = ref(false)
const healthLoading = ref(false)
const submitting = ref(false)
const models = ref<AIModel[]>([])
const health = ref<AIHealthStatus | null>(null)
const activeTab = ref('chat')
const showCreateDialog = ref(false)
const editingModel = ref<AIModel | null>(null)
const formRef = ref()

const chatModels = computed(() => models.value.filter(m => m.model_type === 'chat'))
const embeddingModels = computed(() => models.value.filter(m => m.model_type === 'embedding'))
const ocrModels = computed(() => models.value.filter(m => m.model_type === 'ocr'))

const form = ref<AIModelCreate>({
  model_name: '',
  model_type: 'chat',
  provider: 'ollama',
  endpoint_url: '',
  context_window: 8192,
  performance_notes: '',
})

const formRules = {
  model_name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  model_type: [{ required: true, message: '请选择模型类型', trigger: 'change' }],
  provider: [{ required: true, message: '请选择供应商', trigger: 'change' }],
}

async function fetchModels() {
  loading.value = true
  try {
    models.value = await getAIModels()
  } finally {
    loading.value = false
  }
}

async function refreshHealth() {
  healthLoading.value = true
  try {
    health.value = await getAIHealth()
  } finally {
    healthLoading.value = false
  }
}

async function onActivate(model: AIModel) {
  try {
    await activateAIModel(model.id)
    ElMessage.success(`已激活: ${model.model_name}`)
    await fetchModels()
  } catch { /* error handled by interceptor */ }
}

function onEdit(model: AIModel) {
  editingModel.value = model
  form.value = {
    model_name: model.model_name,
    model_type: model.model_type,
    provider: model.provider,
    endpoint_url: model.endpoint_url ?? '',
    context_window: model.context_window ?? 8192,
    performance_notes: model.performance_notes ?? '',
  }
  showCreateDialog.value = true
}

async function onDelete(model: AIModel) {
  await ElMessageBox.confirm(`确定删除模型「${model.model_name}」？`, '确认删除', {
    type: 'warning',
  })
  try {
    await deleteAIModel(model.id)
    ElMessage.success('已删除')
    await fetchModels()
  } catch { /* error handled by interceptor */ }
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (editingModel.value) {
      await updateAIModel(editingModel.value.id, {
        model_name: form.value.model_name,
        endpoint_url: form.value.endpoint_url || null,
        context_window: form.value.context_window,
        performance_notes: form.value.performance_notes || null,
      })
      ElMessage.success('已更新')
    } else {
      await createAIModel(form.value)
      ElMessage.success('已创建')
    }
    showCreateDialog.value = false
    editingModel.value = null
    await fetchModels()
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  fetchModels()
  refreshHealth()
})
</script>

<style scoped>
.ai-model-config {
  padding: var(--gt-space-4);
  height: 100%;
  overflow-y: auto;
}
.ai-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--gt-space-4);
}
.ai-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--gt-color-text);
  margin: 0;
}
.ai-header-actions {
  display: flex;
  gap: var(--gt-space-2);
}
.ai-health-cards {
  display: flex;
  gap: var(--gt-space-3);
  margin-bottom: var(--gt-space-4);
}
.health-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: var(--gt-radius-md);
  background: var(--gt-color-bg);
  border: 1px solid var(--gt-color-border-light);
  font-size: 13px;
}
.health-card.ok { border-color: #67c23a; }
.health-card.err { border-color: #f56c6c; }
.health-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.health-card.ok .health-dot { background: #67c23a; }
.health-card.err .health-dot { background: #f56c6c; }
.health-label {
  font-weight: 500;
  color: var(--gt-color-text);
}
.health-val {
  color: var(--gt-color-text-secondary);
}
.ai-tabs {
  margin-top: var(--gt-space-2);
}
</style>
