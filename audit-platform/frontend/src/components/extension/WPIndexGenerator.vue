<template>
  <div class="gt-wp-index-gen">
    <div class="gt-gen-header">
      <el-button type="primary" size="small" @click="generateIndex" :loading="generating" :disabled="!projectId">
        <el-icon><DocumentAdd /></el-icon> 生成底稿索引
      </el-button>
      <span v-if="indexData.length" class="gt-gen-count">共 {{ indexData.length }} 项</span>
    </div>

    <el-table v-if="indexData.length" :data="indexData" size="small" stripe style="width: 100%; margin-top: 12px">
      <el-table-column prop="code" label="编号" width="100" />
      <el-table-column prop="name" label="底稿名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="wp_type" label="类型" width="120">
        <template #default="{ row }">
          <el-tag size="small">{{ row.wp_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="cycle" label="审计循环" width="140" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { DocumentAdd } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { projects as P_proj } from '@/services/apiPaths'

const props = defineProps<{
  projectId: string
}>()

const generating = ref(false)
const indexData = ref<any[]>([])

async function generateIndex() {
  if (!props.projectId) return
  generating.value = true
  try {
    const data = await api.post(`${P_proj.detail(props.projectId)}/generate-index`)
    indexData.value = data ?? []
    ElMessage.success(`已生成 ${indexData.value.length} 项底稿索引`)
  } catch { ElMessage.error('生成失败') }
  finally { generating.value = false }
}
</script>

<style scoped>
.gt-wp-index-gen { padding: var(--gt-space-2); }
.gt-gen-header { display: flex; align-items: center; gap: var(--gt-space-3); }
.gt-gen-count { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }
</style>
