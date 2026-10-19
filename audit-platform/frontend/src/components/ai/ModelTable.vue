<template>
  <el-table :data="models" v-loading="loading" stripe size="small" class="model-table">
    <el-table-column label="模型名称" prop="model_name" min-width="170">
      <template #default="{ row }">
        <span class="model-name">{{ row.model_name }}</span>
        <el-tag v-if="row.preset_key" type="info" size="small" class="active-tag">企业预设</el-tag>
        <el-tag v-if="row.is_active" type="success" size="small" class="active-tag">{{ activeTagText(row, models) }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="部署" prop="deployment" width="80" align="center">
      <template #default="{ row }">
        <el-tag :type="row.deployment === 'local' ? 'primary' : 'info'" size="small" effect="plain">
          {{ deploymentLabel(row.deployment) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="供应商" prop="provider" width="165">
      <template #default="{ row }">
        <el-tag :type="providerTag(row.provider) || undefined" size="small" effect="plain">
          {{ providerLabel(row.provider) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="API Key" width="105" align="center">
      <template #default="{ row }">
        <el-tag v-if="row.has_api_key" type="success" size="small">已配置</el-tag>
        <span v-else class="muted">未配置</span>
      </template>
    </el-table-column>
    <el-table-column label="上下文" prop="context_window" width="90" align="center">
      <template #default="{ row }">{{ row.context_window ? `${(row.context_window / 1024).toFixed(0)}K` : '-' }}</template>
    </el-table-column>
    <el-table-column label="端点" prop="endpoint_url" min-width="210" show-overflow-tooltip>
      <template #default="{ row }"><span class="endpoint-text">{{ row.endpoint_url ? `${row.endpoint_url}${row.api_path || ''}` : '本地引擎' }}</span></template>
    </el-table-column>
    <el-table-column label="备注" prop="performance_notes" min-width="150" show-overflow-tooltip />
    <el-table-column label="操作" width="250" fixed="right">
      <template #default="{ row }">
        <el-button
          size="small" link :loading="testingId === row.id"
          @click="emit('test', row)"
        >测试连接</el-button>
        <el-button
          v-if="!row.is_active" type="primary" size="small" link :loading="switchingId === row.id"
          @click="emit('activate', row)"
        >启用</el-button>
        <el-button
          v-else size="small" link :loading="switchingId === row.id"
          @click="emit('deactivate', row)"
        >停用</el-button>
        <el-button size="small" link @click="emit('edit', row)">{{ row.preset_key && !row.has_api_key ? '录入 Key' : '编辑' }}</el-button>
        <el-button
          type="danger" size="small" link :disabled="row.is_active || !!row.preset_key"
          :title="row.is_active ? '已启用的模型不能删除，请先停用' : row.preset_key ? '企业预设模型不能删除' : ''"
          @click="emit('delete', row)"
        >删除</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { AIDeployment, AIModel, AIProvider } from '@/services/aiModelApi'
import { DEPLOYMENT_LABELS, activeTagText } from './modelRouteView'

const props = withDefaults(defineProps<{
  models: AIModel[]
  loading: boolean
  testingId?: string
  switchingId?: string
  providerLabels?: Partial<Record<AIProvider, string>>
}>(), { testingId: '', switchingId: '', providerLabels: () => ({}) })

function providerLabel(p: AIProvider): string {
  return props.providerLabels[p] || p
}

function deploymentLabel(d: AIDeployment | null | undefined): string {
  return d ? DEPLOYMENT_LABELS[d] ?? '-' : '-'
}

const emit = defineEmits<{
  (e: 'activate', model: AIModel): void
  (e: 'deactivate', model: AIModel): void
  (e: 'edit', model: AIModel): void
  (e: 'delete', model: AIModel): void
  (e: 'test', model: AIModel): void
}>()

function providerTag(p: AIProvider): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const map: Partial<Record<AIProvider, 'success' | 'warning' | 'info' | 'danger' | 'primary'>> = {
    deepseek: 'primary', qwen: 'success', zhipu: 'warning', azure_openai: 'info',
    openai_compatible: 'warning', custom: 'info', paddleocr: 'info',
  }
  return map[p] || ''
}
</script>

<style scoped>
.model-table { margin-top: var(--gt-space-2); }
.model-name { font-weight: 500; }
.active-tag { margin-left: 8px; }
.endpoint-text, .muted { color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-xs); }
</style>
