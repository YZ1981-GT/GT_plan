<template>
  <el-table :data="plugins" v-loading="loading" stripe size="small" style="width: 100%">
    <el-table-column prop="plugin_name" label="插件名称" min-width="180">
      <template #default="{ row }">
        <span>{{ row.plugin_name }}</span>
        <el-tag v-if="isStub(row.plugin_id)" type="info" size="small" style="margin-left: 8px">即将上线</el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="version" label="版本" width="80" align="center" />
    <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
    <el-table-column label="状态" width="100" align="center">
      <template #default="{ row }">
        <el-switch
          :model-value="row.is_enabled"
          @change="(v: string | number | boolean) => togglePlugin(row, !!v)"
          :loading="row._toggling"
          active-text="启用"
          inactive-text="禁用"
          inline-prompt
          size="small"
        />
      </template>
    </el-table-column>
    <el-table-column label="操作" width="160" fixed="right">
      <template #default="{ row }">
        <el-tooltip :content="isStub(row.plugin_id) ? '该插件正在开发中' : ''" :disabled="!isStub(row.plugin_id)" placement="top">
          <el-button link type="primary" size="small" :disabled="isStub(row.plugin_id)" @click="$emit('execute', row)">执行</el-button>
        </el-tooltip>
        <el-button link type="primary" size="small" @click="$emit('config', row)">配置</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { aiPlugins as P_aip } from '@/services/apiPaths'

defineProps<{
  plugins: any[]
  loading: boolean
  isStub: (id: string) => boolean
}>()

const emit = defineEmits<{
  (e: 'config', plugin: any): void
  (e: 'toggled'): void
  (e: 'execute', plugin: any): void
}>()

async function togglePlugin(plugin: any, enabled: boolean) {
  plugin._toggling = true
  try {
    const action = enabled ? 'enable' : 'disable'
    await api.post(`${P_aip.list}/${plugin.id}/${action}`)
    plugin.is_enabled = enabled
    ElMessage.success(`插件已${enabled ? '启用' : '禁用'}`)
    emit('toggled')
  } catch { ElMessage.error('操作失败') }
  finally { plugin._toggling = false }
}
</script>
