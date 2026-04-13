<template>
  <el-table :data="plugins" v-loading="loading" stripe size="small" style="width: 100%">
    <el-table-column prop="plugin_name" label="插件名称" min-width="180" />
    <el-table-column prop="version" label="版本" width="80" align="center" />
    <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
    <el-table-column label="状态" width="100" align="center">
      <template #default="{ row }">
        <el-switch
          :model-value="row.is_enabled"
          @change="(v: boolean) => togglePlugin(row, v)"
          :loading="row._toggling"
          active-text="启用"
          inactive-text="禁用"
          inline-prompt
          size="small"
        />
      </template>
    </el-table-column>
    <el-table-column label="操作" width="100" fixed="right">
      <template #default="{ row }">
        <el-button link type="primary" size="small" @click="$emit('config', row)">配置</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

defineProps<{
  plugins: any[]
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'config', plugin: any): void
  (e: 'toggled'): void
}>()

async function togglePlugin(plugin: any, enabled: boolean) {
  plugin._toggling = true
  try {
    const action = enabled ? 'enable' : 'disable'
    await http.post(`/api/ai-plugins/${plugin.id}/${action}`)
    plugin.is_enabled = enabled
    ElMessage.success(`插件已${enabled ? '启用' : '禁用'}`)
    emit('toggled')
  } catch { ElMessage.error('操作失败') }
  finally { plugin._toggling = false }
}
</script>
