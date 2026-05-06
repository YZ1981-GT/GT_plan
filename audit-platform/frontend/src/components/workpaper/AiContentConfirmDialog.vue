<template>
  <el-dialog
    v-model="visible"
    title="AI 生成内容确认"
    width="520px"
    :close-on-click-modal="false"
    @close="onClose"
  >
    <!-- AI 内容详情 -->
    <div class="ai-content-detail">
      <div class="detail-header">
        <el-tag type="warning" effect="dark" size="small">🤖 AI 生成</el-tag>
        <span class="cell-ref">单元格: {{ cellRef }}</span>
      </div>

      <el-descriptions :column="1" border size="small" class="detail-desc">
        <el-descriptions-item label="AI 模型">
          {{ sourceModel || '未知' }}
        </el-descriptions-item>
        <el-descriptions-item label="置信度">
          <el-progress
            :percentage="Math.round((confidence || 0) * 100)"
            :color="confidenceColor"
            :stroke-width="14"
            style="width: 200px;"
          />
        </el-descriptions-item>
        <el-descriptions-item label="生成内容">
          <div class="ai-value-box">{{ generatedValue || '—' }}</div>
        </el-descriptions-item>
      </el-descriptions>

      <!-- 修订输入框（仅修订模式显示） -->
      <div v-if="showReviseInput" class="revise-section">
        <el-divider content-position="left">修订内容</el-divider>
        <el-input
          v-model="revisedValue"
          type="textarea"
          :rows="3"
          placeholder="请输入修订后的内容..."
        />
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="onClose">取消</el-button>
        <el-button type="danger" @click="onReject" :loading="loading">
          拒绝
        </el-button>
        <el-button type="warning" @click="onRevise" :loading="loading">
          修订
        </el-button>
        <el-button type="primary" @click="onAccept" :loading="loading">
          采纳
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Props & Emits ──────────────────────────────────────────────────────────

interface Props {
  modelValue: boolean
  projectId: string
  wpId: string
  cellRef: string
  sourceModel?: string
  confidence?: number
  generatedValue?: string
}

const props = withDefaults(defineProps<Props>(), {
  sourceModel: '',
  confidence: 0,
  generatedValue: '',
})

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'confirmed', payload: { cellRef: string; action: string }): void
}>()

// ─── State ──────────────────────────────────────────────────────────────────

const visible = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit('update:modelValue', val),
})

const loading = ref(false)
const showReviseInput = ref(false)
const revisedValue = ref('')

// Reset revise state when dialog opens
watch(visible, (val) => {
  if (val) {
    showReviseInput.value = false
    revisedValue.value = ''
  }
})

// ─── Computed ───────────────────────────────────────────────────────────────

const confidenceColor = computed(() => {
  const c = props.confidence || 0
  if (c >= 0.8) return '#67c23a'
  if (c >= 0.6) return '#e6a23c'
  return '#f56c6c'
})

// ─── Actions ────────────────────────────────────────────────────────────────

async function callConfirmApi(action: 'accept' | 'reject' | 'revise') {
  loading.value = true
  try {
    const payload: Record<string, string> = {
      cell_ref: props.cellRef,
      action,
    }
    if (action === 'revise' && revisedValue.value) {
      payload.revised_value = revisedValue.value
    }

    await api.patch(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/ai-confirm`,
      payload,
    )

    const labels: Record<string, string> = {
      accept: '采纳',
      reject: '拒绝',
      revise: '修订',
    }
    ElMessage.success(`AI 内容已${labels[action]}`)
    emit('confirmed', { cellRef: props.cellRef, action })
    visible.value = false
  } catch {
    ElMessage.error('操作失败，请重试')
  } finally {
    loading.value = false
  }
}

function onAccept() {
  callConfirmApi('accept')
}

function onReject() {
  callConfirmApi('reject')
}

function onRevise() {
  if (!showReviseInput.value) {
    // 第一次点击：展开修订输入框
    showReviseInput.value = true
    return
  }
  // 第二次点击：提交修订
  if (!revisedValue.value.trim()) {
    ElMessage.warning('请输入修订后的内容')
    return
  }
  callConfirmApi('revise')
}

function onClose() {
  visible.value = false
}
</script>

<style scoped>
.ai-content-detail {
  padding: 0;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.cell-ref {
  font-family: monospace;
  color: #606266;
  font-size: 13px;
}

.detail-desc {
  margin-bottom: 12px;
}

.ai-value-box {
  background: #f5f0ff;
  border: 1px dashed #b39ddb;
  border-radius: 4px;
  padding: 8px 12px;
  font-size: 13px;
  line-height: 1.6;
  color: #333;
  max-height: 120px;
  overflow-y: auto;
  white-space: pre-wrap;
}

.revise-section {
  margin-top: 8px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
