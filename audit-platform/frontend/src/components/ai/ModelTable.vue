<template>
  <el-table :data="models" v-loading="loading" stripe size="small" class="model-table">
    <el-table-column label="模型名称" prop="model_name" min-width="160">
      <template #default="{ row }">
        <span class="model-name">{{ row.model_name }}</span>
        <el-tag v-if="row.is_active" type="success" size="small" class="active-tag">当前激活</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="供应商" prop="provider" width="130">
      <template #default="{ row }">
        <el-tag :type="(providerTag(row.provider)) || undefined" size="small" effect="plain">
          {{ providerLabel(row.provider) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="上下文窗口" prop="context_window" width="110" align="center">
      <template #default="{ row }">
        {{ row.context_window ? (row.context_window / 1024).toFixed(0) + 'K' : '-' }}
      </template>
    </el-table-column>
    <el-table-column label="端点" prop="endpoint_url" min-width="180" show-overflow-tooltip>
      <template #default="{ row }">
        <span class="endpoint-text">{{ row.endpoint_url || '默认' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="备注" prop="performance_notes" min-width="180" show-overflow-tooltip />
    <el-table-column label="操作" width="200" fixed="right">
      <template #default="{ row }">
        <el-button
          v-if="!row.is_active"
          type="primary"
          size="small"
          link
          @click="emit('activate', row)"
        >激活</el-button>
        <el-button size="small" link @click="emit('edit', row)">编辑</el-button>
        <el-button
          type="danger"
          size="small"
          link
          :disabled="row.is_active"
          @click="emit('delete', row)"
        >删除</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { AIModel, AIProvider } from '@/services/aiModelApi'

defineProps<{
  models: AIModel[]
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'activate', model: AIModel): void
  (e: 'edit', model: AIModel): void
  (e: 'delete', model: AIModel): void
}>()

function providerLabel(p: AIProvider): string {
  const map: Record<string, string> = {
    ollama: 'Ollama',
    openai_compatible: 'OpenAI 兼容',
    paddleocr: 'PaddleOCR',
  }
  return map[p] ?? p
}

function providerTag(p: AIProvider): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    ollama: '',
    openai_compatible: 'warning',
    paddleocr: 'info',
  }
  return map[p] ?? ''
}
</script>

<style scoped>
.model-table {
  margin-top: var(--gt-space-2);
}
.model-name {
  font-weight: 500;
}
.active-tag {
  margin-left: 8px;
}
.endpoint-text {
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-xs);
}
</style>
